"""
Background daemon for Gruhanaksha Layer Crash Recovery.

Freeze-safe design (all heavy work off the QGIS main thread or chunked):
- EDIT triggers capture only the incremental edit-buffer patch and write it
  to SQLite on a worker thread (no full layer scans while editing).
- COMMIT/SAVE/INIT/TIMER snapshots extract features in chunks via a timer so
  the UI pumps between batches, then write on the worker thread.
- MANUAL / PRE_ROLLBACK captures run synchronously (destructive operations
  depend on them) but are still chunked with UI event processing.
- Retention pruning, size enforcement and VACUUM run on the worker thread,
  throttled, never on the GUI thread.
"""
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Set, Tuple, Any

from qgis.PyQt.QtCore import QObject, QTimer, QThread, pyqtSignal
from qgis.PyQt.QtWidgets import QApplication
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsWkbTypes, QgsMessageLog, Qgis
)

from .crash_recovery_db import CrashRecoveryDB
from .crash_recovery_worker import SnapshotWorker

# Chunked extraction: features pulled per scan per timer tick / per event pump
SCAN_CHUNK = 4000
SCAN_TICK_MS = 100
MAX_FEATURES_PER_TICK = 8000

# Triggers that must complete synchronously before returning
SYNC_TRIGGERS = ("MANUAL", "PRE_ROLLBACK")


def _log(msg: str, level=Qgis.MessageLevel.Info):
    """Visible diagnostics in QGIS Log Messages panel."""
    try:
        QgsMessageLog.logMessage(msg, "Gruhanaksha Recovery", level)
    except Exception:
        return


class _ScanState:
    """In-progress chunked feature extraction for one layer."""
    __slots__ = ("layer_id", "iterator", "fields", "features", "trigger_type",
                 "summary", "meta")

    def __init__(self, layer_id: str, iterator, fields, trigger_type: str,
                 summary: str, meta: Dict[str, Any]):
        self.layer_id = layer_id
        self.iterator = iterator
        self.fields = fields
        self.features: List[Tuple[int, bytes, Dict[str, Any]]] = []
        self.trigger_type = trigger_type
        self.summary = summary
        self.meta = meta


class CrashRecoveryDaemon(QObject):
    """Silent background worker managing automatic layer snapshots and crash tracking."""

    # Signals
    snapshotCreated = pyqtSignal(int, str, str)  # snapshot_id, layer_id, trigger_type
    uncleanSessionDetected = pyqtSignal(str, list)  # project_id, crashed_sessions_list
    statusChanged = pyqtSignal(bool)  # enabled state
    jobReady = pyqtSignal(dict)  # queued to worker thread

    _instance: Optional['CrashRecoveryDaemon'] = None

    @classmethod
    def instance(cls, db_path: Optional[str] = None) -> 'CrashRecoveryDaemon':
        if cls._instance is None:
            cls._instance = CrashRecoveryDaemon(db_path=db_path)
        return cls._instance

    def __init__(self, parent=None, db_path: Optional[str] = None):
        super().__init__(parent)
        self.db = CrashRecoveryDB(db_path=db_path)

        # Worker thread for all snapshot writes + maintenance
        self._thread = QThread(self)
        self.worker = SnapshotWorker(self.db)
        self.worker.moveToThread(self._thread)
        self.jobReady.connect(self.worker.process)  # auto queued cross-thread
        self.worker.snapshotCreated.connect(self._on_worker_snapshot)
        self.worker.snapshotProcessed.connect(self._on_snapshot_processed)
        self._thread.start()

        # State
        self.current_project_id: Optional[str] = None
        self.current_session_id: Optional[str] = None
        self.monitored_layer_ids: Set[str] = set()
        self.connected_signal_layers: Set[str] = set()

        # Settings
        self.auto_enabled: bool = True
        self.debounce_delay_ms: int = 2500  # 2.5 seconds debounce on edits
        self.interval_minutes: int = 5       # 5 minutes periodic snapshot
        self.max_snapshots_per_layer: int = 50
        self.max_db_size_mb: float = 100.0  # Max database size cap
        self.retention_days: int = 14       # Max retention in days
        self.min_cooldown_seconds: float = 1.5  # Rate limit: minimum cooldown between writes

        # State tracking
        self.last_snapshot_times: Dict[str, float] = {}
        self._dirty_layers: Set[str] = set()          # edited since last checkpoint
        self._snapshotted_this_session: Set[str] = set()
        self._scan_queue: 'OrderedDict[str, _ScanState]' = OrderedDict()

        # Timers
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.setInterval(15000)  # 15s heartbeat
        self.heartbeat_timer.timeout.connect(self._on_heartbeat)

        self.interval_timer = QTimer(self)
        self.interval_timer.timeout.connect(self._on_interval_tick)

        self.scan_timer = QTimer(self)
        self.scan_timer.setInterval(SCAN_TICK_MS)
        self.scan_timer.timeout.connect(self._pump_scans)

        # Per-layer debounce timers: {layer_id: QTimer}
        self.debounce_timers: Dict[str, QTimer] = {}

        # Connect QgsProject lifecycle
        self._init_project_connections()

    # --- Worker plumbing ---

    def _submit_job(self, job: Dict[str, Any]):
        self.jobReady.emit(job)

    def _on_worker_snapshot(self, snapshot_id: int, layer_id: str, trigger_type: str):
        """Runs on main thread; re-emit for dialog/plugin listeners."""
        self.snapshotCreated.emit(snapshot_id, layer_id, trigger_type)

    def _on_snapshot_processed(self, layer_id: str):
        """Runs on main thread after every job (written or deduped)."""
        self._snapshotted_this_session.add(layer_id)

    def start(self):
        """Start silent background monitoring."""
        self._on_project_read()
        self.heartbeat_timer.start()
        self.scan_timer.start()
        self._update_interval_timer()

    def stop(self):
        """Gracefully stop background monitoring and mark session clean."""
        self.heartbeat_timer.stop()
        self.interval_timer.stop()
        self.scan_timer.stop()

        # Flush pending debounced edits as patch jobs before shutdown
        for layer_id in list(self.debounce_timers.keys()):
            timer = self.debounce_timers.pop(layer_id)
            timer.stop()
            if self.auto_enabled:
                self._process_debounced_edit(layer_id)

        if self.current_session_id:
            self.db.close_session_cleanly(self.current_session_id)
            self.current_session_id = None

        self._disconnect_all_layer_signals()

        # Shut worker down; queued jobs (incl. flushes above) process first
        self._submit_job({"kind": "shutdown"})
        self._thread.quit()
        if not self._thread.wait(5000):
            _log("Worker thread did not stop cleanly", Qgis.MessageLevel.Warning)

    # --- Project Lifecycle Connections ---

    def _init_project_connections(self):
        """Hook into QGIS Project signals."""
        proj = QgsProject.instance()
        proj.readProject.connect(self._on_project_read)
        proj.projectSaved.connect(self._on_project_saved)
        proj.cleared.connect(self._on_project_cleared)
        proj.layersAdded.connect(self._on_layers_added)
        proj.layerWillBeRemoved.connect(self._on_layer_removed)

    def _on_project_read(self):
        """Fired when a project is loaded or opened."""
        proj = QgsProject.instance()
        proj_path = proj.fileName() or proj.absoluteFilePath() or "Untitled_Project"
        proj_name = proj.baseName() or "Untitled"

        # Close old session if any
        if self.current_session_id:
            self.db.close_session_cleanly(self.current_session_id)

        self.current_project_id = self.db.register_project(proj_path, proj_name)

        # Check for previous crashed sessions silently
        unclean_sessions = self.db.check_unclean_sessions(self.current_project_id)
        if unclean_sessions:
            self.uncleanSessionDetected.emit(self.current_project_id, unclean_sessions)

        # Start new session
        self.current_session_id = self.db.start_session(self.current_project_id)
        self._snapshotted_this_session.clear()

        # Re-attach layer listeners
        self._sync_project_layers()

    def _on_project_saved(self):
        """Project saved: queue checkpoint scans of modified layers (non-blocking)."""
        if not self.auto_enabled or not self.current_session_id:
            return
        proj = QgsProject.instance()
        proj_path = proj.fileName() or proj.absoluteFilePath()
        if proj_path:
            self.current_project_id = self.db.register_project(proj_path, proj.baseName())

        for layer_id in list(self.monitored_layer_ids):
            layer = proj.mapLayer(layer_id)
            if isinstance(layer, QgsVectorLayer) and layer.isValid():
                self._schedule_scan(layer, trigger_type="SAVE", summary="Project Saved")

    def _on_project_cleared(self):
        """Project closed or new project initialized."""
        if self.current_session_id:
            self.db.close_session_cleanly(self.current_session_id)
            self.current_session_id = None
        self._scan_queue.clear()
        self._disconnect_all_layer_signals()

    # --- Layer Monitoring ---

    def _sync_project_layers(self):
        """Attach listeners to all existing vector layers and ensure baselines."""
        self._disconnect_all_layer_signals()
        proj = QgsProject.instance()
        for layer in proj.mapLayers().values():
            if isinstance(layer, QgsVectorLayer) and layer.isValid():
                self._attach_layer_signals(layer)
                # Backfill baseline for layers without any snapshot yet
                # (covers layersAdded firing before the session existed).
                if self.auto_enabled and layer.id() not in self._scan_queue:
                    if not self.db.get_latest_snapshot_id(layer.id()):
                        self._schedule_scan(layer, trigger_type="INIT",
                                            summary="Layer Initialized")

    def _on_layers_added(self, layers):
        """Fired when layers are added to project."""
        for layer in layers:
            if isinstance(layer, QgsVectorLayer) and layer.isValid():
                self._attach_layer_signals(layer)
                # Queue initial baseline snapshot (chunked, non-blocking)
                if self.auto_enabled and self.current_session_id:
                    self._schedule_scan(layer, trigger_type="INIT",
                                        summary="Layer Initialized")

    def _on_layer_removed(self, layer_id: str):
        """Fired before a layer is removed."""
        self.monitored_layer_ids.discard(layer_id)
        self.connected_signal_layers.discard(layer_id)
        self._dirty_layers.discard(layer_id)
        self._snapshotted_this_session.discard(layer_id)
        self._scan_queue.pop(layer_id, None)
        if layer_id in self.debounce_timers:
            self.debounce_timers[layer_id].stop()
            del self.debounce_timers[layer_id]

    def _attach_layer_signals(self, layer: QgsVectorLayer):
        """Attach edit and modification signals to a vector layer."""
        layer_id = layer.id()
        self.monitored_layer_ids.add(layer_id)

        if layer_id in self.connected_signal_layers:
            return

        try:
            # Edit buffer signals (real-time drafting)
            if hasattr(layer, 'featureAdded'):
                layer.featureAdded.connect(lambda fid, lid=layer_id: self._on_layer_edited(lid))
            if hasattr(layer, 'featureDeleted'):
                layer.featureDeleted.connect(lambda fid, lid=layer_id: self._on_layer_edited(lid))
            if hasattr(layer, 'geometryChanged'):
                layer.geometryChanged.connect(lambda fid, geom, lid=layer_id: self._on_layer_edited(lid))
            if hasattr(layer, 'attributeValueChanged'):
                layer.attributeValueChanged.connect(lambda fid, idx, val, lid=layer_id: self._on_layer_edited(lid))

            # Commit / Rollback signals (Note: QGIS signal is beforeRollBack with capital B)
            if hasattr(layer, 'afterCommitChanges'):
                layer.afterCommitChanges.connect(lambda lid=layer_id: self._on_layer_committed(lid))
            if hasattr(layer, 'beforeRollBack'):
                layer.beforeRollBack.connect(lambda lid=layer_id: self._on_layer_before_rollback(lid))
            elif hasattr(layer, 'beforeRollback'):
                layer.beforeRollback.connect(lambda lid=layer_id: self._on_layer_before_rollback(lid))

            self.connected_signal_layers.add(layer_id)
        except (RuntimeError, TypeError, AttributeError):
            # Underlying C++ object is deleted, disconnected, or missing signal
            pass

    def _disconnect_all_layer_signals(self):
        """Disconnect all layer listeners safely."""
        self.monitored_layer_ids.clear()
        self.connected_signal_layers.clear()

    # --- Debounce & Edit Handlers ---

    def _on_layer_edited(self, layer_id: str):
        """Triggered on every feature add/edit/delete. Debounces for 2.5s."""
        if not self.auto_enabled or not self.current_session_id:
            return
        self._dirty_layers.add(layer_id)

        if layer_id not in self.debounce_timers:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda lid=layer_id: self._process_debounced_edit(lid))
            self.debounce_timers[layer_id] = timer

        # Reset debounce timer
        self.debounce_timers[layer_id].stop()
        self.debounce_timers[layer_id].start(self.debounce_delay_ms)

    def _build_edit_patch(self, layer: QgsVectorLayer
                          ) -> Optional[Tuple[List[Tuple[int, bytes, Dict[str, Any]]], List[int]]]:
        """
        Extract the current edit buffer as (upserts, deleted_fids).
        Tiny payload regardless of layer size; returns None when empty/invalid.
        """
        try:
            buf = layer.editBuffer()
            if buf is None:
                return None

            deleted = [int(f) for f in buf.deletedFeatureIds()]
            changed_geoms = buf.changedGeometries() or {}
            changed_attrs = buf.changedAttributeValues() or {}
            added = buf.addedFeatures() or {}

            fields = list(layer.fields())
            upserts: List[Tuple[int, bytes, Dict[str, Any]]] = []
            seen: Set[int] = set()

            for feat in added.values():  # carries final buffered geometry+attrs
                upserts.append(self._serialize_feature(feat, fields))
                seen.add(int(feat.id()))

            fids = {int(f) for f in changed_geoms.keys()}
            fids.update(int(f) for f in changed_attrs.keys())
            for fid in fids:
                if fid in seen:
                    continue
                feat = layer.getFeature(fid)  # reflects buffered state
                if feat.isValid():
                    upserts.append(self._serialize_feature(feat, fields))

            if not upserts and not deleted:
                return None
            return upserts, deleted
        except RuntimeError:
            return None

    def _process_debounced_edit(self, layer_id: str):
        """Called when user pauses editing for debounce_delay_ms. Sends tiny patch job."""
        if layer_id in self.debounce_timers:
            self.debounce_timers[layer_id].stop()
            del self.debounce_timers[layer_id]

        if not self.auto_enabled or not self.current_session_id:
            return

        proj = QgsProject.instance()
        layer = proj.mapLayer(layer_id)
        if not isinstance(layer, QgsVectorLayer) or not layer.isValid():
            return

        now_ts = time.time()
        last_time = self.last_snapshot_times.get(layer_id, 0.0)
        if now_ts - last_time < self.min_cooldown_seconds:
            return  # rate-limited; next edit event re-debounces anyway

        # Patches merge onto the latest snapshot; without a baseline they
        # would be silently dropped. Fall back to a full scan instead.
        if not self.db.get_latest_snapshot_id(layer_id):
            _log(f"No baseline for '{layer.name()}'; scheduling full scan "
                 f"instead of edit patch", Qgis.MessageLevel.Warning)
            if layer_id not in self._scan_queue:
                self._schedule_scan(layer, trigger_type="INIT",
                                    summary="Baseline Snapshot")
            return

        patch = self._build_edit_patch(layer)
        if patch is None:
            # Buffer empty (e.g. fired right after commit): ensure full checkpoint
            if layer_id not in self._scan_queue:
                self._schedule_scan(layer, trigger_type="COMMIT", summary="Edits Committed")
            return

        upserts, deleted_fids = patch
        self.last_snapshot_times[layer_id] = now_ts
        self._submit_job({
            "kind": "snapshot_patch",
            "session_id": self.current_session_id,
            "project_id": self.current_project_id,
            "layer_id": layer_id,
            "layer_name": layer.name(),
            "geom_type": self._geom_type_str(layer),
            "crs_authid": self._crs_str(layer),
            "fields_schema": self._fields_schema(layer),
            "upserts": upserts,
            "deleted_fids": deleted_fids,
            "trigger_type": "EDIT",
            "summary": "Layer Edited",
            "max_keep": self.max_snapshots_per_layer,
            "retention_days": self.retention_days,
            "max_db_mb": self.max_db_size_mb,
        })

    def _on_layer_committed(self, layer_id: str):
        """After commit FIDs remap negative->positive; queue full rescan (chunked)."""
        self._dirty_layers.discard(layer_id)
        if not self.auto_enabled or not self.current_session_id:
            return
        proj = QgsProject.instance()
        layer = proj.mapLayer(layer_id)
        if isinstance(layer, QgsVectorLayer) and layer.isValid():
            self._schedule_scan(layer, trigger_type="COMMIT", summary="Edits Committed")

    def _on_layer_before_rollback(self, layer_id: str):
        """Snapshot the about-to-be-discarded buffer state right before rollback."""
        if not self.current_session_id:
            return
        proj = QgsProject.instance()
        layer = proj.mapLayer(layer_id)
        if not isinstance(layer, QgsVectorLayer) or not layer.isValid():
            return

        patch = self._build_edit_patch(layer)
        if patch is None:
            return
        upserts, deleted_fids = patch
        self._submit_job({
            "kind": "snapshot_patch",
            "session_id": self.current_session_id,
            "project_id": self.current_project_id,
            "layer_id": layer_id,
            "layer_name": layer.name(),
            "geom_type": self._geom_type_str(layer),
            "crs_authid": self._crs_str(layer),
            "fields_schema": self._fields_schema(layer),
            "upserts": upserts,
            "deleted_fids": deleted_fids,
            "trigger_type": "PRE_ROLLBACK",
            "summary": "Before Rollback",
            "max_keep": self.max_snapshots_per_layer,
            "retention_days": self.retention_days,
            "max_db_mb": self.max_db_size_mb,
        })

    # --- Periodic Timer & Heartbeat ---

    def _on_heartbeat(self):
        """Queue session heartbeat update on worker thread."""
        if self.current_session_id:
            self._submit_job({"kind": "heartbeat",
                              "session_id": self.current_session_id})

    def _on_interval_tick(self):
        """Periodic checkpoint tick: rescan dirty layers or layers without baseline."""
        if not self.auto_enabled or not self.current_session_id:
            return

        proj = QgsProject.instance()
        for layer_id in list(self.monitored_layer_ids):
            needs = layer_id in self._dirty_layers or \
                layer_id not in self._snapshotted_this_session
            if not needs or layer_id in self._scan_queue:
                continue
            layer = proj.mapLayer(layer_id)
            if isinstance(layer, QgsVectorLayer) and layer.isValid():
                self._dirty_layers.discard(layer_id)
                self._schedule_scan(layer, trigger_type="TIMER",
                                    summary="Interval Auto-Save")

    def _update_interval_timer(self):
        """Apply current interval settings."""
        if self.interval_minutes > 0:
            self.interval_timer.start(self.interval_minutes * 60 * 1000)
        else:
            self.interval_timer.stop()

    def set_enabled(self, enabled: bool):
        """Enable or disable background auto-logging."""
        self.auto_enabled = enabled
        if not enabled:
            self.interval_timer.stop()
            for timer in self.debounce_timers.values():
                timer.stop()
            self._scan_queue.clear()
        else:
            self._update_interval_timer()
        self.statusChanged.emit(enabled)

    def set_settings(self, auto_enabled: bool, debounce_delay_ms: int,
                     interval_minutes: int, max_snapshots: int,
                     max_db_size_mb: float = 100.0, retention_days: int = 14):
        """Update runtime settings."""
        self.debounce_delay_ms = debounce_delay_ms
        self.interval_minutes = interval_minutes
        self.max_snapshots_per_layer = max_snapshots
        self.max_db_size_mb = max_db_size_mb
        self.retention_days = retention_days
        self.set_enabled(auto_enabled)
        self._update_interval_timer()

    # --- Serialization helpers ---

    @staticmethod
    def _geom_type_str(layer: QgsVectorLayer) -> str:
        try:
            return QgsWkbTypes.displayString(layer.wkbType())
        except Exception:
            return "Unknown"

    @staticmethod
    def _crs_str(layer: QgsVectorLayer) -> str:
        try:
            crs = layer.crs()
            return crs.authid() if crs.isValid() else "EPSG:4326"
        except Exception:
            return "EPSG:4326"

    @staticmethod
    def _fields_schema(layer: QgsVectorLayer) -> List[Dict[str, Any]]:
        return [
            {"name": f.name(), "type": f.typeName(), "length": f.length(),
             "precision": f.precision()}
            for f in layer.fields()
        ]

    @staticmethod
    def _serialize_feature(feat, fields) -> Tuple[int, bytes, Dict[str, Any]]:
        fid = feat.id()
        geom = feat.geometry()
        wkb_bytes = bytes(geom.asWkb()) if geom and not geom.isEmpty() else b""

        attrs: Dict[str, Any] = {}
        for idx, field in enumerate(fields):
            val = feat.attribute(idx)
            if val is None or str(val) == "NULL":
                attrs[field.name()] = None
            elif isinstance(val, (int, float, str, bool)):
                attrs[field.name()] = val
            else:
                attrs[field.name()] = str(val)
        return (fid, wkb_bytes, attrs)

    def _capture_meta(self, layer: QgsVectorLayer) -> Dict[str, Any]:
        return {
            "layer_id": layer.id(),
            "layer_name": layer.name(),
            "geom_type": self._geom_type_str(layer),
            "crs_authid": self._crs_str(layer),
            "fields_schema": self._fields_schema(layer),
            "project_id": self.current_project_id,
            "max_keep": self.max_snapshots_per_layer,
            "retention_days": self.retention_days,
            "max_db_mb": self.max_db_size_mb,
        }

    # --- Core Snapshot Creation ---

    def create_snapshot_silent(self, layer: QgsVectorLayer,
                               trigger_type: str = "EDIT",
                               summary: str = "") -> Optional[int]:
        """
        Public API kept compatible with dialog callers.
        MANUAL/PRE_ROLLBACK run synchronously (chunked, UI pumped) and return
        the new snapshot id. All other triggers queue non-blocking work and
        return None immediately.
        """
        if not layer or not layer.isValid():
            return None

        if trigger_type in SYNC_TRIGGERS:
            return self._snapshot_synchronous(layer, trigger_type, summary)

        # Async path: INIT / TIMER / COMMIT / SAVE / anything else
        self._ensure_session()
        if not self.current_session_id:
            return None
        self._schedule_scan(layer, trigger_type=trigger_type, summary=summary)
        return None

    def _ensure_session(self):
        """Guarantee an active project session exists."""
        if self.current_session_id:
            return
        proj = QgsProject.instance()
        proj_path = proj.fileName() or "Untitled_Project"
        proj_name = proj.baseName() or "Untitled"
        self.current_project_id = self.db.register_project(proj_path, proj_name)
        self.current_session_id = self.db.start_session(self.current_project_id)

    def _schedule_scan(self, layer: QgsVectorLayer, trigger_type: str, summary: str):
        """Queue a chunked, non-blocking full-feature scan of the layer."""
        layer_id = layer.id()
        if layer_id in self._scan_queue:
            return  # already scanning
        try:
            meta = self._capture_meta(layer)
            state = _ScanState(
                layer_id=layer_id,
                iterator=iter(layer.getFeatures()),
                fields=list(layer.fields()),
                trigger_type=trigger_type,
                summary=summary,
                meta=meta,
            )
            self._scan_queue[layer_id] = state
            _log(f"Queued {trigger_type} scan of '{layer.name()}'")
        except RuntimeError:
            _log(f"Scan schedule failed for layer id {layer_id}", Qgis.MessageLevel.Warning)

    def _pump_scans(self):
        """Timer tick: advance every active scan by a bounded chunk, then yield to UI."""
        budget = MAX_FEATURES_PER_TICK
        for layer_id in list(self._scan_queue.keys()):
            if budget <= 0:
                break
            state = self._scan_queue.get(layer_id)
            if state is None:
                continue
            allowance = min(SCAN_CHUNK, budget)
            done = False
            try:
                count = 0
                while count < allowance:
                    feat = next(state.iterator)
                    state.features.append(self._serialize_feature(feat, state.fields))
                    count += 1
                    budget -= 1
            except StopIteration:
                done = True
            except RuntimeError:
                # Layer deleted mid-scan: abort silently
                self._scan_queue.pop(layer_id, None)
                continue

            if done and layer_id in self._scan_queue:
                del self._scan_queue[layer_id]
                self._finish_scan(state)

    def _finish_scan(self, state: _ScanState):
        """Hand completed extraction to the worker thread for writing."""
        self._ensure_session()
        if not self.current_session_id:
            return
        meta = state.meta
        self._submit_job({
            "kind": "snapshot_full",
            "session_id": self.current_session_id,
            "project_id": meta["project_id"],
            "layer_id": meta["layer_id"],
            "layer_name": meta["layer_name"],
            "geom_type": meta["geom_type"],
            "crs_authid": meta["crs_authid"],
            "fields_schema": meta["fields_schema"],
            "features_data": state.features,
            "trigger_type": state.trigger_type,
            "summary": state.summary,
            "max_keep": meta["max_keep"],
            "retention_days": meta["retention_days"],
            "max_db_mb": meta["max_db_mb"],
        })

    def _snapshot_synchronous(self, layer: QgsVectorLayer, trigger_type: str,
                              summary: str) -> Optional[int]:
        """
        Blocking capture for MANUAL / PRE_ROLLBACK triggers where ordering with
        a subsequent destructive operation matters. Extraction is chunked with
        UI event pumping so large layers no longer freeze QGIS.
        """
        self._ensure_session()
        if not self.current_session_id:
            return None

        layer_id = layer.id()
        now_ts = time.time()
        last_time = self.last_snapshot_times.get(layer_id, 0.0)
        if trigger_type != "MANUAL" and (now_ts - last_time < self.min_cooldown_seconds):
            return None

        try:
            meta = self._capture_meta(layer)
            fields = list(layer.fields())
            features_data: List[Tuple[int, bytes, Dict[str, Any]]] = []
            iterator = iter(layer.getFeatures())

            exhausted = False
            while not exhausted:
                count = 0
                try:
                    while count < SCAN_CHUNK:
                        feat = next(iterator)
                        features_data.append(self._serialize_feature(feat, fields))
                        count += 1
                except StopIteration:
                    exhausted = True
                # Keep the UI responsive during long extractions
                QApplication.processEvents()

            snapshot_id = self.db.save_snapshot(
                session_id=self.current_session_id,
                project_id=meta["project_id"],
                layer_id=meta["layer_id"],
                layer_name=meta["layer_name"],
                geom_type=meta["geom_type"],
                crs_authid=meta["crs_authid"],
                fields_schema=meta["fields_schema"],
                features_data=features_data,
                trigger_type=trigger_type,
                summary=summary,
                max_keep=meta["max_keep"],
            )
            if snapshot_id:
                self.last_snapshot_times[layer_id] = now_ts
                self._snapshotted_this_session.add(layer_id)
                self.snapshotCreated.emit(snapshot_id, layer_id, trigger_type)
            return snapshot_id
        except Exception as e:
            _log(f"Error snapshotting {layer.name()}: {e}", Qgis.MessageLevel.Critical)
            return None

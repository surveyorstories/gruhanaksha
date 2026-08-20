"""
Background daemon for Gruhanaksha Layer Crash Recovery.
Runs completely silently in background without blocking QGIS UI.
Monitors layer edits (debounced), time-based interval snapshots, and session heartbeats.
"""
import os
import json
import time
from typing import Dict, Set, Optional, List, Tuple, Any

from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsWkbTypes, Qgis, QgsFeature, QgsGeometry
)
from qgis.utils import iface

from .crash_recovery_db import CrashRecoveryDB


class CrashRecoveryDaemon(QObject):
    """Silent background worker managing automatic layer snapshots and crash tracking."""

    # Signals
    snapshotCreated = pyqtSignal(int, str, str)  # snapshot_id, layer_id, trigger_type
    uncleanSessionDetected = pyqtSignal(str, list)  # project_id, crashed_sessions_list
    statusChanged = pyqtSignal(bool)  # enabled state

    _instance: Optional['CrashRecoveryDaemon'] = None

    @classmethod
    def instance(cls, db_path: Optional[str] = None) -> 'CrashRecoveryDaemon':
        if cls._instance is None:
            cls._instance = CrashRecoveryDaemon(db_path=db_path)
        return cls._instance

    def __init__(self, parent=None, db_path: Optional[str] = None):
        super().__init__(parent)
        self.db = CrashRecoveryDB(db_path=db_path)

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

        # Timers
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.setInterval(15000)  # 15s heartbeat
        self.heartbeat_timer.timeout.connect(self._on_heartbeat)

        self.interval_timer = QTimer(self)
        self.interval_timer.timeout.connect(self._on_interval_tick)

        # Per-layer debounce timers: {layer_id: QTimer}
        self.debounce_timers: Dict[str, QTimer] = {}

        # Connect QgsProject lifecycle
        self._init_project_connections()

    def start(self):
        """Start silent background monitoring."""
        self._on_project_read()
        self.heartbeat_timer.start()
        self._update_interval_timer()

    def stop(self):
        """Gracefully stop background monitoring and mark session clean."""
        self.heartbeat_timer.stop()
        self.interval_timer.stop()

        for timer in self.debounce_timers.values():
            timer.stop()
        self.debounce_timers.clear()

        if self.current_session_id:
            self.db.close_session_cleanly(self.current_session_id)
            self.current_session_id = None

        self._disconnect_all_layer_signals()

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

        # Re-attach layer listeners
        self._sync_project_layers()

    def _on_project_saved(self):
        """Project saved: trigger immediate checkpoint snapshot on modified layers."""
        if not self.auto_enabled or not self.current_session_id:
            return
        proj = QgsProject.instance()
        proj_path = proj.fileName() or proj.absoluteFilePath()
        if proj_path:
            self.current_project_id = self.db.register_project(proj_path, proj.baseName())

        for layer_id in list(self.monitored_layer_ids):
            layer = proj.mapLayer(layer_id)
            if isinstance(layer, QgsVectorLayer) and layer.isValid():
                self.create_snapshot_silent(layer, trigger_type="SAVE", summary="Project Saved")

    def _on_project_cleared(self):
        """Project closed or new project initialized."""
        if self.current_session_id:
            self.db.close_session_cleanly(self.current_session_id)
            self.current_session_id = None
        self._disconnect_all_layer_signals()

    # --- Layer Monitoring ---

    def _sync_project_layers(self):
        """Attach listeners to all existing vector layers in project."""
        self._disconnect_all_layer_signals()
        proj = QgsProject.instance()
        for layer in proj.mapLayers().values():
            if isinstance(layer, QgsVectorLayer) and layer.isValid():
                self._attach_layer_signals(layer)

    def _on_layers_added(self, layers):
        """Fired when layers are added to project."""
        for layer in layers:
            if isinstance(layer, QgsVectorLayer) and layer.isValid():
                self._attach_layer_signals(layer)
                # Take initial baseline snapshot
                if self.auto_enabled and self.current_session_id:
                    self.create_snapshot_silent(layer, trigger_type="INIT", summary="Layer Initialized")

    def _on_layer_removed(self, layer_id: str):
        """Fired before a layer is removed."""
        if layer_id in self.monitored_layer_ids:
            self.monitored_layer_ids.remove(layer_id)
        if layer_id in self.connected_signal_layers:
            self.connected_signal_layers.remove(layer_id)
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
        """Triggered on every feature add/edit/delete. Debounces for 2.5s before saving."""
        if not self.auto_enabled or not self.current_session_id:
            return

        if layer_id not in self.debounce_timers:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda lid=layer_id: self._process_debounced_edit(lid))
            self.debounce_timers[layer_id] = timer

        # Reset debounce timer
        self.debounce_timers[layer_id].stop()
        self.debounce_timers[layer_id].start(self.debounce_delay_ms)

    def _process_debounced_edit(self, layer_id: str):
        """Called when user pauses editing for debounce_delay_ms."""
        proj = QgsProject.instance()
        layer = proj.mapLayer(layer_id)
        if isinstance(layer, QgsVectorLayer) and layer.isValid():
            self.create_snapshot_silent(layer, trigger_type="EDIT", summary="Layer Edited")

    def _on_layer_committed(self, layer_id: str):
        """Immediately snapshot committed edits."""
        proj = QgsProject.instance()
        layer = proj.mapLayer(layer_id)
        if isinstance(layer, QgsVectorLayer) and layer.isValid():
            self.create_snapshot_silent(layer, trigger_type="COMMIT", summary="Edits Committed")

    def _on_layer_before_rollback(self, layer_id: str):
        """Snapshot right before rollback so discarded edits can still be recovered if accidental."""
        proj = QgsProject.instance()
        layer = proj.mapLayer(layer_id)
        if isinstance(layer, QgsVectorLayer) and layer.isValid():
            self.create_snapshot_silent(layer, trigger_type="PRE_ROLLBACK", summary="Before Rollback")

    # --- Periodic Timer & Heartbeat ---

    def _on_heartbeat(self):
        """Update session heartbeat in SQLite silently."""
        if self.current_session_id:
            self.db.heartbeat(self.current_session_id)

    def _on_interval_tick(self):
        """Periodic snapshot tick."""
        if not self.auto_enabled or not self.current_session_id:
            return

        proj = QgsProject.instance()
        for layer_id in list(self.monitored_layer_ids):
            layer = proj.mapLayer(layer_id)
            if isinstance(layer, QgsVectorLayer) and layer.isValid():
                self.create_snapshot_silent(layer, trigger_type="TIMER", summary="Interval Auto-Save")

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

    # --- Core Snapshot Creation (Fast & Silent) ---

    def create_snapshot_silent(self, layer: QgsVectorLayer,
                               trigger_type: str = "EDIT",
                               summary: str = "") -> Optional[int]:
        """
        Extract features into binary WKB and attributes, write to SQLite without blocking UI.
        Enforces cooldown rate limiting and max database size.
        """
        if not layer or not layer.isValid():
            return None

        layer_id = layer.id()

        # Enforce rate-limiting cooldown per layer (skip if rapid fire except for manual/commit/init)
        now_ts = time.time()
        last_time = self.last_snapshot_times.get(layer_id, 0.0)
        if trigger_type not in ["MANUAL", "COMMIT", "INIT", "SAVE"] and (now_ts - last_time < self.min_cooldown_seconds):
            return None

        if not self.current_session_id:
            proj = QgsProject.instance()
            proj_path = proj.fileName() or "Untitled_Project"
            proj_name = proj.baseName() or "Untitled"
            self.current_project_id = self.db.register_project(proj_path, proj_name)
            self.current_session_id = self.db.start_session(self.current_project_id)

        try:
            layer_name = layer.name()
            geom_type = QgsWkbTypes.displayString(layer.wkbType())
            crs_authid = layer.crs().authid() if layer.crs().isValid() else "EPSG:4326"

            # Fields schema
            fields_schema = [
                {"name": f.name(), "type": f.typeName(), "length": f.length(), "precision": f.precision()}
                for f in layer.fields()
            ]

            # Fast feature extraction
            features_data: List[Tuple[int, bytes, Dict[str, Any]]] = []
            for feat in layer.getFeatures():
                fid = feat.id()
                geom = feat.geometry()
                wkb_bytes = bytes(geom.asWkb()) if geom and not geom.isEmpty() else b""

                # Attributes
                attrs: Dict[str, Any] = {}
                for idx, field in enumerate(layer.fields()):
                    val = feat.attribute(idx)
                    # Convert non-serializable objects
                    if val is None or str(val) == "NULL":
                        attrs[field.name()] = None
                    elif isinstance(val, (int, float, str, bool)):
                        attrs[field.name()] = val
                    else:
                        attrs[field.name()] = str(val)

                features_data.append((fid, wkb_bytes, attrs))

            # Save in SQLite
            snapshot_id = self.db.save_snapshot(
                session_id=self.current_session_id,
                layer_id=layer_id,
                project_id=self.current_project_id,
                layer_name=layer_name,
                geom_type=geom_type,
                crs_authid=crs_authid,
                fields_schema=fields_schema,
                features_data=features_data,
                trigger_type=trigger_type,
                summary=summary,
                max_keep=self.max_snapshots_per_layer
            )

            if snapshot_id:
                self.last_snapshot_times[layer_id] = now_ts
                self.snapshotCreated.emit(snapshot_id, layer_id, trigger_type)

                # Background database maintenance (rate-limited size & retention pruning)
                self.db.purge_old_snapshots(self.retention_days)
                self.db.enforce_max_database_size(self.max_db_size_mb)

            return snapshot_id

        except Exception as e:
            # Silent logging without crashing UI
            print(f"[Gruhanaksha Crash Recovery] Error snapshotting {layer.name()}: {e}")
            return None

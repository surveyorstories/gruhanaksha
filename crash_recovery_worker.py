"""
Background worker thread for Gruhanaksha Layer Crash Recovery.
Owns all snapshot hashing, diffing, SQLite writes and maintenance so the
QGIS main/UI thread never blocks on disk I/O or VACUUM.
"""
import time
from typing import Any, Dict, Optional

from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.core import QgsMessageLog, Qgis


# Run retention pruning / size enforcement at most this often (seconds)
MAINTENANCE_INTERVAL_S = 300.0
# ...and at least this many snapshots between maintenance runs
MAINTENANCE_MIN_SNAPSHOTS = 20

_TAG = "Gruhanaksha Recovery"


def _log(msg: str, level=Qgis.MessageLevel.Info):
    try:
        QgsMessageLog.logMessage(msg, _TAG, level)
    except Exception:
        return


class SnapshotWorker(QObject):
    """Processes snapshot jobs queued from the GUI thread."""

    # snapshot_id, layer_id, trigger_type
    snapshotCreated = pyqtSignal(int, str, str)
    # layer_id — fired for every processed job, written or not
    snapshotProcessed = pyqtSignal(str)

    def __init__(self, db):
        super().__init__()
        self.db = db
        self._last_maintenance_ts = 0.0
        self._snapshots_since_maintenance = 0

    def process(self, job: Dict[str, Any]):
        """Slot: runs on worker thread via queued connection."""
        kind = job.get("kind")
        try:
            if kind == "snapshot_full":
                self._do_full(job)
            elif kind == "snapshot_patch":
                self._do_patch(job)
            elif kind == "heartbeat":
                self.db.heartbeat(job["session_id"])
            elif kind == "maintenance":
                self._run_maintenance(job.get("retention_days", 14),
                                      job.get("max_db_mb", 100.0))
            elif kind == "shutdown":
                self.db.close_thread_connection()
        except Exception as e:
            _log(f"Worker error ({kind}): {e}", Qgis.MessageLevel.Critical)

    def _emit(self, snapshot_id: Optional[int], job: Dict[str, Any]):
        layer_id = job["layer_id"]
        if snapshot_id:
            self.snapshotCreated.emit(int(snapshot_id), layer_id, job["trigger_type"])
            _log(f"Snapshot #{snapshot_id} written for layer {layer_id} "
                 f"({job['trigger_type']})")
            self._snapshots_since_maintenance += 1
            now = time.time()
            if (now - self._last_maintenance_ts > MAINTENANCE_INTERVAL_S
                    and self._snapshots_since_maintenance >= MAINTENANCE_MIN_SNAPSHOTS):
                self._run_maintenance(job.get("retention_days", 14),
                                      job.get("max_db_mb", 100.0))
        else:
            _log(f"No new snapshot needed for layer {layer_id} "
                 f"(unchanged or skipped)", Qgis.MessageLevel.Info)
        self.snapshotProcessed.emit(layer_id)

    def _do_full(self, job: Dict[str, Any]):
        snapshot_id = self.db.save_snapshot(
            session_id=job["session_id"],
            layer_id=job["layer_id"],
            project_id=job["project_id"],
            layer_name=job["layer_name"],
            geom_type=job["geom_type"],
            crs_authid=job["crs_authid"],
            fields_schema=job["fields_schema"],
            features_data=job["features_data"],
            trigger_type=job["trigger_type"],
            summary=job["summary"],
            max_keep=job["max_keep"],
        )
        self._emit(snapshot_id, job)

    def _do_patch(self, job: Dict[str, Any]):
        snapshot_id = self.db.apply_patch_save(
            session_id=job["session_id"],
            layer_id=job["layer_id"],
            project_id=job["project_id"],
            layer_name=job["layer_name"],
            geom_type=job["geom_type"],
            crs_authid=job["crs_authid"],
            fields_schema=job["fields_schema"],
            upserts=job["upserts"],
            deleted_fids=job["deleted_fids"],
            trigger_type=job["trigger_type"],
            summary=job["summary"],
            max_keep=job["max_keep"],
        )
        self._emit(snapshot_id, job)

    def _run_maintenance(self, retention_days: int, max_db_mb: float):
        try:
            self.db.purge_old_snapshots(retention_days)
            self.db.enforce_max_database_size(max_db_mb)  # may VACUUM; off UI thread now
            self._last_maintenance_ts = time.time()
            self._snapshots_since_maintenance = 0
        except Exception as e:
            _log(f"Maintenance error: {e}", Qgis.MessageLevel.Warning)

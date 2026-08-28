"""
SQLite storage engine for Gruhanaksha Layer Crash Recovery & Restore Points.
High-durability WAL mode, fast binary WKB geometry serialization, and transaction safety.
"""
import os
import sqlite3
import json
import uuid
import datetime
import hashlib
import threading
from typing import List, Dict, Any, Optional, Tuple


class CrashRecoveryDB:
    """Manages SQLite storage for layer snapshots, transactions, and session heartbeats."""

    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            user_dir = os.path.join(os.path.expanduser("~"), ".gruhanaksha")
            os.makedirs(user_dir, exist_ok=True)
            self.db_path = os.path.join(user_dir, "crash_recovery.db")
        else:
            self.db_path = db_path
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

        self._local = threading.local()

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a persistent per-thread connection configured with WAL and busy timeout."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            return conn

        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 30000;")
        self._local.conn = conn
        return conn

    def close_thread_connection(self):
        """Close the calling thread's persistent connection (used at worker shutdown)."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
            self._local.conn = None

    def _init_db(self):
        """Create tables and indices if not present."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Projects table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    project_path TEXT,
                    name TEXT,
                    last_updated TEXT
                )
            """)

            # Sessions table for crash tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    project_id TEXT,
                    start_time TEXT,
                    last_heartbeat TEXT,
                    is_crashed INTEGER DEFAULT 1,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
                )
            """)

            # Layers table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS layers (
                    layer_id TEXT PRIMARY KEY,
                    project_id TEXT,
                    layer_name TEXT,
                    geom_type TEXT,
                    crs_authid TEXT,
                    fields_json TEXT,
                    last_updated TEXT,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
                )
            """)

            # Restore Points (Snapshots)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS restore_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    layer_id TEXT,
                    timestamp TEXT,
                    trigger_type TEXT,
                    feature_count INTEGER,
                    added_count INTEGER DEFAULT 0,
                    deleted_count INTEGER DEFAULT 0,
                    modified_count INTEGER DEFAULT 0,
                    summary TEXT,
                    layer_hash TEXT,
                    is_pinned INTEGER DEFAULT 0,
                    tag TEXT DEFAULT '',
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE SET NULL,
                    FOREIGN KEY (layer_id) REFERENCES layers(layer_id) ON DELETE CASCADE
                )
            """)

            # Migrations for existing DBs
            try:
                cursor.execute("ALTER TABLE restore_points ADD COLUMN is_pinned INTEGER DEFAULT 0;")
            except sqlite3.OperationalError:
                # Column already exists
                pass

            try:
                cursor.execute("ALTER TABLE restore_points ADD COLUMN tag TEXT DEFAULT '';")
            except sqlite3.OperationalError:
                # Column already exists
                pass

            # Features binary & attribute storage
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS features_snapshot (
                    snapshot_id INTEGER,
                    fid INTEGER,
                    geom_wkb BLOB,
                    attributes_json TEXT,
                    PRIMARY KEY (snapshot_id, fid),
                    FOREIGN KEY (snapshot_id) REFERENCES restore_points(id) ON DELETE CASCADE
                )
            """)

            # Indices
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_rp_layer_id ON restore_points(layer_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_rp_timestamp ON restore_points(timestamp);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_rp_pinned ON restore_points(is_pinned);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_feat_snapshot ON features_snapshot(snapshot_id);")
            conn.commit()

    # --- Project & Session Tracking ---

    def register_project(self, project_path: str, name: str) -> str:
        """Register or update a project by path hash."""
        norm_path = os.path.normpath(project_path) if project_path else "Untitled"
        project_id = hashlib.sha256(norm_path.encode('utf-8')).hexdigest()[:16]
        now = datetime.datetime.now().isoformat()

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO projects (project_id, project_path, name, last_updated)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    project_path = excluded.project_path,
                    name = excluded.name,
                    last_updated = excluded.last_updated
            """, (project_id, norm_path, name, now))
            conn.commit()
        return project_id

    def start_session(self, project_id: str) -> str:
        """Start a new session with is_crashed=1 until clean exit."""
        session_id = str(uuid.uuid4())
        now = datetime.datetime.now().isoformat()

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO sessions (session_id, project_id, start_time, last_heartbeat, is_crashed)
                VALUES (?, ?, ?, ?, 1)
            """, (session_id, project_id, now, now))
            conn.commit()
        return session_id

    def heartbeat(self, session_id: str):
        """Update last heartbeat timestamp silently."""
        now = datetime.datetime.now().isoformat()
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE sessions SET last_heartbeat = ? WHERE session_id = ?
                """, (now, session_id))
                conn.commit()
        except sqlite3.Error:
            pass

    def close_session_cleanly(self, session_id: str):
        """Mark session as cleanly terminated."""
        now = datetime.datetime.now().isoformat()
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE sessions SET last_heartbeat = ?, is_crashed = 0 WHERE session_id = ?
                """, (now, session_id))
                conn.commit()
        except sqlite3.Error:
            pass

    def check_unclean_sessions(self, project_id: str) -> List[Dict[str, Any]]:
        """Find past sessions that crashed (is_crashed=1) for this project."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.session_id, s.start_time, s.last_heartbeat, COUNT(rp.id) as point_count
                FROM sessions s
                LEFT JOIN restore_points rp ON s.session_id = rp.session_id
                WHERE s.project_id = ? AND s.is_crashed = 1
                GROUP BY s.session_id
                HAVING point_count > 0
                ORDER BY s.last_heartbeat DESC
            """, (project_id,))
            return [dict(row) for row in cursor.fetchall()]

    # --- Layer & Snapshot Operations ---

    def register_layer(self, layer_id: str, project_id: str, layer_name: str,
                       geom_type: str, crs_authid: str, fields_schema: List[Dict[str, str]]):
        """Register or update layer metadata and schema."""
        now = datetime.datetime.now().isoformat()
        fields_json = json.dumps(fields_schema)

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO layers (layer_id, project_id, layer_name, geom_type, crs_authid, fields_json, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(layer_id) DO UPDATE SET
                    layer_name = excluded.layer_name,
                    geom_type = excluded.geom_type,
                    crs_authid = excluded.crs_authid,
                    fields_json = excluded.fields_json,
                    last_updated = excluded.last_updated
            """, (layer_id, project_id, layer_name, geom_type, crs_authid, fields_json, now))
            conn.commit()

    def get_latest_layer_hash(self, layer_id: str) -> Optional[str]:
        """Fetch the most recent layer content hash to prevent duplicate identical snapshots."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT layer_hash FROM restore_points
                WHERE layer_id = ?
                ORDER BY id DESC LIMIT 1
            """, (layer_id,))
            row = cursor.fetchone()
            return row["layer_hash"] if row else None

    @staticmethod
    def compute_features_diff(
        prev_features: List[Tuple[int, Optional[bytes], Dict[str, Any]]],
        curr_features: List[Tuple[int, Optional[bytes], Dict[str, Any]]]
    ) -> Tuple[int, int, int, Dict[str, List[Tuple[int, Optional[bytes], Dict[str, Any]]]]]:
        """
        Computes added, deleted, and modified features between two snapshots.
        Handles positive FIDs, temporary negative edit FIDs, and geometry matching.
        """
        prev_by_fid = {f[0]: f for f in prev_features}
        curr_by_fid = {f[0]: f for f in curr_features}

        prev_by_wkb = {f[1]: f for f in prev_features if f[1]}
        curr_by_wkb = {f[1]: f for f in curr_features if f[1]}

        matched_prev_fids = set()
        matched_curr_fids = set()

        added = []
        deleted = []
        modified = []
        unchanged = []

        # 1. Match positive stable FIDs
        for fid, curr_wkb, curr_attrs in curr_features:
            if fid > 0 and fid in prev_by_fid:
                prev_fid, prev_wkb, prev_attrs = prev_by_fid[fid]
                matched_prev_fids.add(fid)
                matched_curr_fids.add(fid)
                if prev_wkb == curr_wkb and prev_attrs == curr_attrs:
                    unchanged.append((fid, curr_wkb, curr_attrs))
                else:
                    modified.append((fid, curr_wkb, curr_attrs))

        # 2. Match exact WKB geometries for remaining features (handles commit of negative FIDs to positive)
        for fid, curr_wkb, curr_attrs in curr_features:
            if fid not in matched_curr_fids and curr_wkb and curr_wkb in prev_by_wkb:
                prev_f = prev_by_wkb[curr_wkb]
                prev_fid = prev_f[0]
                if prev_fid not in matched_prev_fids:
                    matched_prev_fids.add(prev_fid)
                    matched_curr_fids.add(fid)
                    if curr_attrs == prev_f[2]:
                        unchanged.append((fid, curr_wkb, curr_attrs))
                    else:
                        modified.append((fid, curr_wkb, curr_attrs))

        # 3. Match negative FIDs by identical negative FID if not matched yet
        for fid, curr_wkb, curr_attrs in curr_features:
            if fid not in matched_curr_fids and fid < 0 and fid in prev_by_fid:
                prev_fid, prev_wkb, prev_attrs = prev_by_fid[fid]
                if prev_fid not in matched_prev_fids:
                    matched_prev_fids.add(prev_fid)
                    matched_curr_fids.add(fid)
                    if prev_wkb == curr_wkb and prev_attrs == curr_attrs:
                        unchanged.append((fid, curr_wkb, curr_attrs))
                    else:
                        modified.append((fid, curr_wkb, curr_attrs))

        # 4. Any remaining in curr_features is strictly ADDED
        for fid, curr_wkb, curr_attrs in curr_features:
            if fid not in matched_curr_fids:
                added.append((fid, curr_wkb, curr_attrs))

        # 5. Any remaining in prev_features is strictly DELETED
        for fid, prev_wkb, prev_attrs in prev_features:
            if fid not in matched_prev_fids:
                deleted.append((fid, prev_wkb, prev_attrs))

        return len(added), len(deleted), len(modified), {
            'added': added,
            'deleted': deleted,
            'modified': modified,
            'unchanged': unchanged
        }

    def compute_features_hash(self, features_data) -> str:
        """Compute robust content hash over full feature set."""
        hasher = hashlib.sha256()
        hasher.update(str(len(features_data)).encode('utf-8'))
        for fid, wkb, attrs in features_data:
            hasher.update(str(fid).encode('utf-8'))
            if wkb:
                hasher.update(wkb)
            hasher.update(json.dumps(attrs, sort_keys=True).encode('utf-8'))
        return hasher.hexdigest()

    def _save_core(self, session_id: str, layer_id: str, project_id: str,
                   layer_name: str, geom_type: str, crs_authid: str,
                   fields_schema: List[Dict[str, str]],
                   features_data: List[Tuple[int, Optional[bytes], Dict[str, Any]]],
                   trigger_type: str, summary: str, max_keep: int,
                   skip_hash_check: bool = False) -> Optional[int]:
        """Write one atomic snapshot of the given full feature set."""
        now = datetime.datetime.now().isoformat()
        layer_hash = self.compute_features_hash(features_data)

        # Check if identical to last snapshot
        if not skip_hash_check:
            last_hash = self.get_latest_layer_hash(layer_id)
            if last_hash == layer_hash and trigger_type != "MANUAL":
                return None  # No changes, skip duplicate

        # Register layer metadata first
        self.register_layer(layer_id, project_id, layer_name, geom_type, crs_authid, fields_schema)

        # Calculate diff counts if previous snapshot exists
        added_count = 0
        deleted_count = 0
        modified_count = 0

        prev_snapshot = self.get_latest_snapshot_id(layer_id)
        if prev_snapshot:
            prev_features = self.get_snapshot_features(prev_snapshot)
            added_count, deleted_count, modified_count, _ = self.compute_features_diff(
                prev_features, features_data
            )
        else:
            added_count = len(features_data)

        feature_count = len(features_data)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO restore_points (
                    session_id, layer_id, timestamp, trigger_type, feature_count,
                    added_count, deleted_count, modified_count, summary, layer_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id, layer_id, now, trigger_type, feature_count,
                added_count, deleted_count, modified_count, summary, layer_hash
            ))
            snapshot_id = cursor.lastrowid

            # Insert all features in batch
            feature_rows = [
                (snapshot_id, fid, sqlite3.Binary(wkb) if wkb else None, json.dumps(attrs))
                for fid, wkb, attrs in features_data
            ]
            cursor.executemany("""
                INSERT INTO features_snapshot (snapshot_id, fid, geom_wkb, attributes_json)
                VALUES (?, ?, ?, ?)
            """, feature_rows)

            conn.commit()

        # Prune old snapshots exceeding limit
        self.prune_snapshots(layer_id, max_keep=max_keep)
        return snapshot_id

    def save_snapshot(self, session_id: str, layer_id: str, project_id: str,
                      layer_name: str, geom_type: str, crs_authid: str,
                      fields_schema: List[Dict[str, str]],
                      features_data: List[Tuple[int, bytes, Dict[str, Any]]],
                      trigger_type: str = "EDIT",
                      summary: str = "",
                      max_keep: int = 50) -> Optional[int]:
        """
        Save a full atomic snapshot of a layer in SQLite.
        features_data: List of (fid, wkb_bytes, attributes_dict)
        Computes delta counts compared to previous snapshot.
        """
        return self._save_core(
            session_id, layer_id, project_id, layer_name, geom_type, crs_authid,
            fields_schema, features_data, trigger_type, summary, max_keep
        )

    def apply_patch_save(self, session_id: str, layer_id: str, project_id: str,
                         layer_name: str, geom_type: str, crs_authid: str,
                         fields_schema: List[Dict[str, str]],
                         upserts: List[Tuple[int, Optional[bytes], Dict[str, Any]]],
                         deleted_fids: List[int],
                         trigger_type: str = "EDIT",
                         summary: str = "",
                         max_keep: int = 50) -> Optional[int]:
        """
        Apply an incremental edit-buffer patch onto the latest snapshot and store result.
        upserts: (fid, wkb, attrs) for added/modified features; deleted_fids: fids to remove.
        Runs entirely on worker thread; no QGIS objects involved.
        """
        prev_snapshot = self.get_latest_snapshot_id(layer_id)
        if not prev_snapshot:
            return None  # No baseline yet; caller must schedule a full scan

        base = {fid: (wkb, attrs) for fid, wkb, attrs in self.get_snapshot_features(prev_snapshot)}

        for fid in deleted_fids:
            base.pop(fid, None)
        for fid, wkb, attrs in upserts:
            base[fid] = (wkb, attrs)

        merged = [(fid, wkb, attrs) for fid, (wkb, attrs) in sorted(base.items())]
        if not merged and not upserts and not deleted_fids:
            return None

        return self._save_core(
            session_id, layer_id, project_id, layer_name, geom_type, crs_authid,
            fields_schema, merged, trigger_type, summary, max_keep
        )

    def get_latest_snapshot_id(self, layer_id: str) -> Optional[int]:
        """Get latest snapshot ID for a layer."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM restore_points WHERE layer_id = ? ORDER BY id DESC LIMIT 1
            """, (layer_id,))
            row = cursor.fetchone()
            return row["id"] if row else None

    def get_previous_snapshot_id(self, snapshot_id: int, layer_id: str) -> Optional[int]:
        """Get the snapshot ID that immediately preceded this one for the same layer."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM restore_points
                WHERE layer_id = ? AND id < ?
                ORDER BY id DESC LIMIT 1
            """, (layer_id, snapshot_id))
            row = cursor.fetchone()
            return row["id"] if row else None

    def toggle_pin_snapshot(self, snapshot_id: int) -> bool:
        """Toggle is_pinned between 0 and 1. Returns new pinned state."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_pinned FROM restore_points WHERE id = ?", (snapshot_id,))
            row = cursor.fetchone()
            if not row:
                return False
            new_pinned = 0 if row["is_pinned"] else 1
            cursor.execute("UPDATE restore_points SET is_pinned = ? WHERE id = ?", (new_pinned, snapshot_id))
            conn.commit()
            return bool(new_pinned)

    def set_snapshot_tag(self, snapshot_id: int, tag: str):
        """Set custom label/name tag on a restore point."""
        with self._get_connection() as conn:
            conn.execute("UPDATE restore_points SET tag = ? WHERE id = ?", (tag, snapshot_id))
            conn.commit()

    def get_restore_points(self, layer_id: Optional[str] = None,
                           project_id: Optional[str] = None,
                           limit: int = 150) -> List[Dict[str, Any]]:
        """Retrieve list of restore points sorted descending by timestamp."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT rp.id, rp.session_id, rp.layer_id, rp.timestamp, rp.trigger_type,
                       rp.feature_count, rp.added_count, rp.deleted_count, rp.modified_count,
                       rp.summary, rp.is_pinned, rp.tag, l.layer_name, l.geom_type, l.crs_authid
                FROM restore_points rp
                JOIN layers l ON rp.layer_id = l.layer_id
                WHERE 1=1
            """
            params: List[Any] = []
            if layer_id:
                query += " AND rp.layer_id = ?"
                params.append(layer_id)
            elif project_id:
                query += " AND l.project_id = ?"
                params.append(project_id)

            query += " ORDER BY rp.is_pinned DESC, rp.id DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_snapshot_info(self, snapshot_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed metadata for a specific snapshot."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT rp.*, l.layer_name, l.geom_type, l.crs_authid, l.fields_json
                FROM restore_points rp
                JOIN layers l ON rp.layer_id = l.layer_id
                WHERE rp.id = ?
            """, (snapshot_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_snapshot_features(self, snapshot_id: int) -> List[Tuple[int, Optional[bytes], Dict[str, Any]]]:
        """Fetch all features for a snapshot as list of (fid, wkb_bytes, attributes_dict)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT fid, geom_wkb, attributes_json
                FROM features_snapshot
                WHERE snapshot_id = ?
                ORDER BY fid ASC
            """, (snapshot_id,))
            results = []
            for row in cursor.fetchall():
                fid = row["fid"]
                geom_wkb = bytes(row["geom_wkb"]) if row["geom_wkb"] is not None else None
                attrs = json.loads(row["attributes_json"]) if row["attributes_json"] else {}
                results.append((fid, geom_wkb, attrs))
            return results

    def get_snapshot_features_dict(self, snapshot_id: int) -> Dict[int, Tuple[Optional[bytes], Dict[str, Any]]]:
        """Fetch features as dict keyed by fid: {fid: (wkb_bytes, attrs)}."""
        features = self.get_snapshot_features(snapshot_id)
        return {fid: (wkb, attrs) for fid, wkb, attrs in features}

    def prune_snapshots(self, layer_id: str, max_keep: int = 50):
        """Retain only the latest max_keep unpinned snapshots for a layer."""
        if max_keep <= 0:
            return
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM restore_points
                WHERE layer_id = ? AND is_pinned = 0 AND id NOT IN (
                    SELECT id FROM restore_points
                    WHERE layer_id = ?
                    ORDER BY id DESC LIMIT ?
                )
            """, (layer_id, layer_id, max_keep))
            conn.commit()

    def delete_snapshot(self, snapshot_id: int):
        """Delete a single snapshot and its features."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM restore_points WHERE id = ?", (snapshot_id,))
            conn.commit()

    def clear_layer_history(self, layer_id: str):
        """Delete all snapshots and registration for one layer."""
        with self._get_connection() as conn:
            conn.execute("""
                DELETE FROM features_snapshot WHERE snapshot_id IN (
                    SELECT id FROM restore_points WHERE layer_id = ?
                )
            """, (layer_id,))
            conn.execute("DELETE FROM restore_points WHERE layer_id = ?", (layer_id,))
            conn.execute("DELETE FROM layers WHERE layer_id = ?", (layer_id,))
            conn.commit()

    def get_database_size_bytes(self) -> int:
        """Get total size of SQLite DB file including WAL and SHM files."""
        total = 0
        for suffix in ["", "-wal", "-shm"]:
            path = self.db_path + suffix
            if os.path.exists(path):
                try:
                    total += os.path.getsize(path)
                except OSError:
                    pass
        return total

    def get_database_size_mb(self) -> float:
        """Get database size formatted in megabytes."""
        return round(self.get_database_size_bytes() / (1024 * 1024), 2)

    def purge_old_snapshots(self, max_days: int = 14) -> int:
        """Delete unpinned snapshots older than max_days."""
        if max_days <= 0:
            return 0
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=max_days)).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM restore_points WHERE timestamp < ? AND is_pinned = 0", (cutoff,))
            deleted = cursor.rowcount
            conn.commit()
            return deleted

    def enforce_max_database_size(self, max_size_mb: float = 100.0) -> bool:
        """
        Enforce max database file size. If exceeded, delete oldest unpinned snapshots until under limit.
        """
        max_bytes = max_size_mb * 1024 * 1024
        curr_bytes = self.get_database_size_bytes()
        if curr_bytes <= max_bytes:
            return False

        # Purge oldest 25 unpinned snapshots in loop until size is under limit
        with self._get_connection() as conn:
            cursor = conn.cursor()
            while self.get_database_size_bytes() > max_bytes:
                cursor.execute("""
                    DELETE FROM restore_points WHERE id IN (
                        SELECT id FROM restore_points WHERE is_pinned = 0 ORDER BY id ASC LIMIT 25
                    )
                """)
                if cursor.rowcount == 0:
                    break
                conn.commit()

        self.vacuum()
        return True

    def clear_entire_database(self):
        """Wipe all tables, reset SQLite database completely, and vacuum."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM features_snapshot;")
            conn.execute("DELETE FROM restore_points;")
            conn.execute("DELETE FROM layers;")
            conn.execute("DELETE FROM sessions;")
            conn.execute("DELETE FROM projects;")
            conn.commit()
        self.vacuum()

    def vacuum(self):
        """Reclaim space in SQLite database."""
        try:
            conn = self._get_connection()
            # VACUUM cannot run inside a transaction
            conn.commit()
            conn.execute("VACUUM;")
            conn.commit()
        except sqlite3.Error:
            pass



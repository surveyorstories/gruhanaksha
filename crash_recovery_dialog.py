"""
Clean, modern Crash Recovery & Layer Time-Travel Dialog for Gruhanaksha.
Includes interactive Map Canvas visual diff preview, attribute inspector,
in-place rollback, new layer creation, and export tools.
"""
import os
import json
import datetime
from typing import Dict, List, Optional, Tuple, Any

from qgis.PyQt.QtCore import Qt, QSize, QTimer
from qgis.PyQt.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QTabWidget,
    QComboBox, QLineEdit, QGroupBox, QSpinBox, QCheckBox, QMessageBox,
    QFileDialog, QFrame, QToolButton, QAbstractItemView, QSlider, QInputDialog
)
from qgis.PyQt.QtGui import QColor, QFont, QIcon, QPalette
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsField,
    QgsFields, QgsCoordinateReferenceSystem, QgsWkbTypes,
    QgsRuleBasedRenderer, QgsFillSymbol, QgsLineSymbol, QgsMarkerSymbol,
    QgsVectorFileWriter, QgsCoordinateTransformContext, Qgis
)
from qgis.gui import QgsMapCanvas, QgsMapToolPan, QgsMapToolZoom
from qgis.utils import iface

from .qt_compat import QtCompat
from .crash_recovery_db import CrashRecoveryDB
from .crash_recovery_daemon import CrashRecoveryDaemon


def get_icon(name: str) -> QIcon:
    """Load icon from images folder or return empty."""
    plugin_dir = os.path.dirname(__file__)
    icon_path = os.path.join(plugin_dir, "images", name)
    return QIcon(icon_path) if os.path.exists(icon_path) else QIcon()


class CrashRecoveryDialog(QDialog):
    """Modern interactive Crash Recovery & Layer Time-Travel manager."""

    def __init__(self, parent=None, db_path: Optional[str] = None):
        super().__init__(parent or (iface.mainWindow() if iface else None))
        self.db = CrashRecoveryDB(db_path=db_path)
        self.daemon = CrashRecoveryDaemon.instance(db_path=db_path)

        self.setWindowTitle("Layer Data Recovery - Gruhanaksha")
        self.resize(1080, 680)
        self.setMinimumSize(850, 500)
        self.setWindowIcon(get_icon("recovery_shield.svg"))

        # State
        self.current_project_id = self.daemon.current_project_id or ""
        self.selected_snapshot_id: Optional[int] = None
        self.preview_layer: Optional[QgsVectorLayer] = None

        self._setup_ui()
        self._populate_layer_selector()
        self.load_restore_points()

        # Connect daemon signal for real-time refresh
        self.daemon.snapshotCreated.connect(self._on_snapshot_created_externally)

    def _setup_ui(self):
        """Construct a clean, responsive layout using native QGIS styles."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # Header Bar
        header_layout = QHBoxLayout()
        self.title_label = QLabel("🛡️ Layer Crash Recovery & Time Travel")
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        header_layout.addWidget(self.title_label)

        header_layout.addStretch()

        self.btn_instant_snapshot = QPushButton("📸 Create Snapshot Now")
        self.btn_instant_snapshot.setToolTip("Immediately capture a manual restore point for selected layer")
        self.btn_instant_snapshot.clicked.connect(self._create_manual_snapshot)
        header_layout.addWidget(self.btn_instant_snapshot)

        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.clicked.connect(self.load_restore_points)
        header_layout.addWidget(self.btn_refresh)

        main_layout.addLayout(header_layout)

        # Main Splitter (Left: Timeline Table | Right: Interactive Preview & Diff)
        splitter = QSplitter(QtCompat.horizontal())
        main_layout.addWidget(splitter, 1)

        # --- LEFT PANEL: Layer Selector & Timeline ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        # Filter & Selector Bar
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("Layer:"))
        self.layer_combo = QComboBox()
        self.layer_combo.currentIndexChanged.connect(self.load_restore_points)
        selector_layout.addWidget(self.layer_combo, 1)

        left_layout.addLayout(selector_layout)

        # Search / filter box
        search_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 Filter restore points...")
        self.search_edit.textChanged.connect(self._filter_table)
        search_layout.addWidget(self.search_edit)
        left_layout.addLayout(search_layout)

        # Restore Points Table (With Pin & Tag columns)
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["📌", "ID", "Layer", "Tag / Name", "Time", "Trigger", "Features", "Changes"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QtCompat.resize_to_contents())
        self.table.horizontalHeader().setSectionResizeMode(
            1, QtCompat.resize_to_contents())
        self.table.horizontalHeader().setSectionResizeMode(
            2, QtCompat.resize_to_contents())
        self.table.horizontalHeader().setSectionResizeMode(
            3, QtCompat.resize_to_contents())
        self.table.horizontalHeader().setSectionResizeMode(
            4, QtCompat.resize_to_contents())
        self.table.horizontalHeader().setSectionResizeMode(
            5, QtCompat.resize_to_contents())
        self.table.horizontalHeader().setSectionResizeMode(
            6, QtCompat.resize_to_contents())
        self.table.horizontalHeader().setSectionResizeMode(7, QtCompat.stretch())
        self.table.setSelectionBehavior(QtCompat.select_rows())
        self.table.setSelectionMode(QtCompat.single_selection())
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(
            self._on_table_selection_changed)
        self.table.cellDoubleClicked.connect(self._on_table_double_clicked)
        left_layout.addWidget(self.table)

        # Table quick action buttons (Pin & Tag)
        table_btn_layout = QHBoxLayout()
        self.btn_pin = QPushButton("📌 Pin / Unpin")
        self.btn_pin.setToolTip(
            "Pin snapshot so it is never deleted by auto-prune or size limits")
        self.btn_pin.clicked.connect(self._toggle_pin)
        table_btn_layout.addWidget(self.btn_pin)

        self.btn_tag = QPushButton("🏷️ Name Tag...")
        self.btn_tag.setToolTip(
            "Assign a custom bookmark name (e.g., 'Before Splitting')")
        self.btn_tag.clicked.connect(self._set_tag)
        table_btn_layout.addWidget(self.btn_tag)

        table_btn_layout.addStretch()
        left_layout.addLayout(table_btn_layout)

        # Bottom stats under table
        self.lbl_table_stats = QLabel("0 restore points found")
        stats_font = QFont()
        stats_font.setPointSize(9)
        self.lbl_table_stats.setFont(stats_font)
        left_layout.addWidget(self.lbl_table_stats)

        splitter.addWidget(left_widget)

        # --- RIGHT PANEL: Visual Map Diff & Attribute Inspector ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self.tabs = QTabWidget()
        right_layout.addWidget(self.tabs, 1)

        # Tab 1: Visual Map Canvas Preview
        tab_preview = QWidget()
        preview_layout = QVBoxLayout(tab_preview)
        preview_layout.setContentsMargins(4, 4, 4, 4)

        # Map Canvas toolbar
        map_tools_bar = QHBoxLayout()
        self.lbl_preview_info = QLabel("Select a restore point to preview changes")
        preview_font = QFont()
        preview_font.setBold(True)
        self.lbl_preview_info.setFont(preview_font)
        map_tools_bar.addWidget(self.lbl_preview_info)
        map_tools_bar.addStretch()

        self.btn_zoom_extent = QToolButton()
        self.btn_zoom_extent.setText("🔍 Fit Extent")
        self.btn_zoom_extent.setToolTip("Zoom to layer extent")
        self.btn_zoom_extent.clicked.connect(self._zoom_preview_extent)
        map_tools_bar.addWidget(self.btn_zoom_extent)

        self.btn_pan = QToolButton()
        self.btn_pan.setText("✋ Pan")
        self.btn_pan.setCheckable(True)
        self.btn_pan.clicked.connect(self._activate_pan_tool)
        map_tools_bar.addWidget(self.btn_pan)

        preview_layout.addLayout(map_tools_bar)

        # Color legend bar
        legend_layout = QHBoxLayout()
        legend_layout.setSpacing(12)
        legend_layout.addWidget(QLabel("🟢 Added"))
        legend_layout.addWidget(QLabel("🔴 Deleted"))
        legend_layout.addWidget(QLabel("🟠 Modified"))
        legend_layout.addWidget(QLabel("🔵 Unchanged"))
        legend_layout.addStretch()
        preview_layout.addLayout(legend_layout)

        # Map Canvas Widget
        self.canvas = QgsMapCanvas(self)
        self.canvas.enableAntiAliasing(True)
        self.map_tool_pan = QgsMapToolPan(self.canvas)
        self.map_tool_zoom = QgsMapToolZoom(self.canvas, False)
        self.canvas.setMapTool(self.map_tool_pan)
        preview_layout.addWidget(self.canvas, 1)

        # Time-Travel History Scrubber Slider
        scrubber_layout = QHBoxLayout()
        scrubber_layout.addWidget(QLabel("⏪ History Scrubber:"))
        self.slider_time = QSlider(QtCompat.horizontal())
        self.slider_time.setMinimum(0)
        self.slider_time.setMaximum(0)
        self.slider_time.valueChanged.connect(self._on_slider_scrubbed)
        scrubber_layout.addWidget(self.slider_time, 1)

        self.lbl_slider_time = QLabel("Step: 0/0")
        slider_time_font = QFont()
        slider_time_font.setBold(True)
        self.lbl_slider_time.setFont(slider_time_font)
        scrubber_layout.addWidget(self.lbl_slider_time)
        preview_layout.addLayout(scrubber_layout)

        self.tabs.addTab(tab_preview, "🗺️ Visual Map Diff")

        # Tab 2: Feature & Attribute Inspector (With Selective Restore)
        tab_attrs = QWidget()
        attrs_layout = QVBoxLayout(tab_attrs)
        attrs_layout.setContentsMargins(4, 4, 4, 4)

        # Selective restore action bar
        selective_bar = QHBoxLayout()
        self.btn_select_all = QPushButton("Select All")
        self.btn_select_all.clicked.connect(self._select_all_features)
        selective_bar.addWidget(self.btn_select_all)

        self.btn_select_none = QPushButton("Select None")
        self.btn_select_none.clicked.connect(self._select_no_features)
        selective_bar.addWidget(self.btn_select_none)

        selective_bar.addStretch()

        self.btn_selective_restore = QPushButton(
            "🎯 Restore Checked Features to Layer")
        self.btn_selective_restore.setToolTip(
            "Restore ONLY the checked features without altering the rest of layer")
        self.btn_selective_restore.clicked.connect(
            self._restore_selected_features)
        selective_bar.addWidget(self.btn_selective_restore)

        attrs_layout.addLayout(selective_bar)

        self.attr_table = QTableWidget()
        self.attr_table.setAlternatingRowColors(True)
        self.attr_table.setSelectionBehavior(QtCompat.select_rows())
        attrs_layout.addWidget(self.attr_table)

        self.tabs.addTab(tab_attrs, "📋 Selective Attribute Inspector")

        # Tab 3: Settings & Auto-Save Options
        tab_settings = QWidget()
        self._setup_settings_tab(tab_settings)
        self.tabs.addTab(tab_settings, "⚙️ Settings")

        splitter.addWidget(right_widget)
        splitter.setSizes([430, 650])

        # --- BOTTOM ACTION BAR ---
        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)

        self.btn_delete = QPushButton("🗑️ Delete Snapshot")
        self.btn_delete.clicked.connect(self._delete_selected_snapshot)
        action_bar.addWidget(self.btn_delete)

        self.btn_clear_history = QPushButton("Clear Layer History")
        self.btn_clear_history.clicked.connect(self._clear_layer_history)
        action_bar.addWidget(self.btn_clear_history)

        action_bar.addStretch()

        self.btn_export = QPushButton("💾 Export to File...")
        self.btn_export.setToolTip(
            "Export selected restore point to GeoPackage/Shapefile/GeoJSON")
        self.btn_export.clicked.connect(self._export_snapshot)
        action_bar.addWidget(self.btn_export)

        self.btn_restore_as_new = QPushButton("➕ Restore as New Layer")
        self.btn_restore_as_new.setToolTip(
            "Add recovered state as a new layer in current project")
        self.btn_restore_as_new.clicked.connect(self._restore_as_new_layer)
        action_bar.addWidget(self.btn_restore_as_new)

        self.btn_restore_inplace = QPushButton("🔄 Restore Active Layer")
        self.btn_restore_inplace.setToolTip(
            "Roll back current layer to this restore point state")
        self.btn_restore_inplace.clicked.connect(self._restore_inplace)
        action_bar.addWidget(self.btn_restore_inplace)

        main_layout.addLayout(action_bar)

    def _create_legend_badge(self, text: str, color_hex: str) -> QWidget:
        """Helper to create a small color badge for visual diff legend."""
        badge = QLabel(text)
        badge.setStyleSheet(f"""
            QLabel {{
                background-color: {color_hex};
                color: #FFFFFF;
                font-weight: bold;
                font-size: 11px;
                padding: 2px 6px;
                border-radius: 3px;
            }}
        """)
        return badge

    def _setup_settings_tab(self, parent_widget: QWidget):
        """Construct the settings tab."""
        layout = QVBoxLayout(parent_widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        grp = QGroupBox("Silent Background Recovery Settings")
        grp_layout = QVBoxLayout(grp)

        self.chk_auto_enable = QCheckBox(
            "Enable silent background auto-logging")
        self.chk_auto_enable.setChecked(self.daemon.auto_enabled)
        grp_layout.addWidget(self.chk_auto_enable)

        # Interval
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Time-Slot Interval:"))
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(1, 120)
        self.spin_interval.setValue(self.daemon.interval_minutes)
        self.spin_interval.setSuffix(" minutes")
        h1.addWidget(self.spin_interval)
        h1.addStretch()
        grp_layout.addLayout(h1)

        # Debounce
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Edit Debounce Delay:"))
        self.spin_debounce = QSpinBox()
        self.spin_debounce.setRange(500, 10000)
        self.spin_debounce.setSingleStep(500)
        self.spin_debounce.setValue(self.daemon.debounce_delay_ms)
        self.spin_debounce.setSuffix(" ms")
        h2.addWidget(self.spin_debounce)
        h2.addStretch()
        grp_layout.addLayout(h2)

        # Retention snapshot count
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("Max Snapshots per Layer:"))
        self.spin_max_snapshots = QSpinBox()
        self.spin_max_snapshots.setRange(5, 500)
        self.spin_max_snapshots.setValue(self.daemon.max_snapshots_per_layer)
        h3.addWidget(self.spin_max_snapshots)
        h3.addStretch()
        grp_layout.addLayout(h3)

        # Retention days
        h_days = QHBoxLayout()
        h_days.addWidget(QLabel("Snapshot Retention Period:"))
        self.spin_retention_days = QSpinBox()
        self.spin_retention_days.setRange(1, 90)
        self.spin_retention_days.setValue(self.daemon.retention_days)
        self.spin_retention_days.setSuffix(" days")
        h_days.addWidget(self.spin_retention_days)
        h_days.addStretch()
        grp_layout.addLayout(h_days)

        # Max Database Size Cap
        h_size = QHBoxLayout()
        h_size.addWidget(QLabel("Max SQLite Database Size:"))
        self.spin_max_db_size = QSpinBox()
        self.spin_max_db_size.setRange(10, 5000)
        self.spin_max_db_size.setValue(int(self.daemon.max_db_size_mb))
        self.spin_max_db_size.setSuffix(" MB")
        h_size.addWidget(self.spin_max_db_size)
        h_size.addStretch()
        grp_layout.addLayout(h_size)

        # DB Current Size & Path info
        self.lbl_db_size = QLabel(
            f"📦 Current Database Size: {self.db.get_database_size_mb()} MB")
        db_size_font = QFont()
        db_size_font.setBold(True)
        self.lbl_db_size.setFont(db_size_font)
        grp_layout.addWidget(self.lbl_db_size)

        h4 = QHBoxLayout()
        h4.addWidget(QLabel(f"SQLite Storage Path: {self.db.db_path}"))
        grp_layout.addLayout(h4)

        btn_box = QHBoxLayout()
        btn_save_settings = QPushButton("💾 Save Settings")
        btn_save_settings.clicked.connect(self._save_settings)
        btn_box.addWidget(btn_save_settings)

        btn_vacuum = QPushButton("🧹 Vacuum & Optimize DB")
        btn_vacuum.setToolTip(
            "Reclaim deleted space and shrink database file size")
        btn_vacuum.clicked.connect(self._vacuum_db)
        btn_box.addWidget(btn_vacuum)

        btn_wipe = QPushButton("🧨 Wipe Entire Database")
        btn_wipe.setToolTip(
            "Completely delete all snapshots and reset SQLite database")
        btn_wipe.clicked.connect(self._wipe_entire_database)
        btn_box.addWidget(btn_wipe)

        btn_box.addStretch()
        grp_layout.addLayout(btn_box)

        layout.addWidget(grp)
        layout.addStretch()

    def _vacuum_db(self):
        """Clean and vacuum the SQLite database."""
        self.db.purge_old_snapshots(self.spin_retention_days.value())
        self.db.vacuum()
        size_mb = self.db.get_database_size_mb()
        self.lbl_db_size.setText(f"📦 Current Database Size: {size_mb} MB")
        QMessageBox.information(
            self, "Database Optimized", f"SQLite database vacuumed successfully.\nCurrent Size: {size_mb} MB")

    def _wipe_entire_database(self):
        """Confirm and wipe entire recovery database."""
        reply = QMessageBox.question(
            self, "Wipe Entire Database",
            "⚠️ WARNING: This will permanently delete ALL snapshots, recovery logs, and history for ALL layers and projects.\n\nAre you sure you want to completely empty the database?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.clear_entire_database()
            self.load_restore_points()
            self.attr_table.clear()
            self.attr_table.setRowCount(0)
            if self.preview_layer:
                self.canvas.setLayers([])
                self.canvas.refresh()
            self.lbl_preview_info.setText(
                "Database wiped. Select a restore point to preview.")
            self.lbl_db_size.setText(
                f"📦 Current Database Size: {self.db.get_database_size_mb()} MB")
            QMessageBox.information(
                self, "Database Wiped", "Entire crash recovery database has been emptied.")

    def _save_settings(self):
        """Save settings back to daemon."""
        self.daemon.set_settings(
            auto_enabled=self.chk_auto_enable.isChecked(),
            debounce_delay_ms=self.spin_debounce.value(),
            interval_minutes=self.spin_interval.value(),
            max_snapshots=self.spin_max_snapshots.value(),
            max_db_size_mb=float(self.spin_max_db_size.value()),
            retention_days=self.spin_retention_days.value()
        )
        self.lbl_db_size.setText(
            f"📦 Current Database Size: {self.db.get_database_size_mb()} MB")
        QMessageBox.information(
            self, "Settings Saved", "Crash recovery rate limiting and size settings updated successfully.")

    # --- Data Loading & UI Sync ---

    def _populate_layer_selector(self):
        """Fill layer combo with project vector layers."""
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        self.layer_combo.addItem("📂 All Project Layers", None)

        proj = QgsProject.instance()
        for layer in proj.mapLayers().values():
            if isinstance(layer, QgsVectorLayer) and layer.isValid():
                self.layer_combo.addItem(f"🗺️ {layer.name()}", layer.id())

        self.layer_combo.blockSignals(False)

    def load_restore_points(self):
        """Load restore points from SQLite into the table."""
        layer_id = self.layer_combo.currentData()
        records = self.db.get_restore_points(
            layer_id=layer_id,
            project_id=self.daemon.current_project_id,
            limit=150
        )

        self.table.setRowCount(len(records))
        self.slider_time.blockSignals(True)
        self.slider_time.setRange(0, max(0, len(records) - 1))
        self.slider_time.blockSignals(False)

        for row, r in enumerate(records):
            # Pin Star
            is_pinned = bool(r.get("is_pinned", 0))
            pin_item = QTableWidgetItem("⭐" if is_pinned else "")
            pin_item.setTextAlignment(QtCompat.align_center())

            # ID
            id_item = QTableWidgetItem(str(r["id"]))
            id_item.setData(QtCompat.user_role(), r["id"])

            # Layer name
            layer_item = QTableWidgetItem(f"🗺️ {r.get('layer_name', '')}")

            # Custom Tag / Bookmark Name
            tag_text = r.get("tag", "") or ""
            tag_item = QTableWidgetItem(tag_text)
            if tag_text:
                font = tag_item.font()
                font.setBold(True)
                tag_item.setFont(font)

            # Time formatted
            try:
                dt = datetime.datetime.fromisoformat(r["timestamp"])
                time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                time_str = r["timestamp"]
            time_item = QTableWidgetItem(time_str)

            # Trigger badge
            trigger_icons = {
                "EDIT": "✏️ Edit",
                "TIMER": "⏱️ Timer",
                "COMMIT": "💾 Commit",
                "SAVE": "📁 Save",
                "MANUAL": "📌 Manual",
                "INIT": "⚡ Init",
                "PRE_ROLLBACK": "⏪ Pre-Rollback"
            }
            trigger_text = trigger_icons.get(
                r["trigger_type"], r["trigger_type"])
            trigger_item = QTableWidgetItem(trigger_text)

            # Feature count
            feat_item = QTableWidgetItem(str(r["feature_count"]))

            # Changes summary (+Added, -Deleted, ~Modified)
            diff_parts = []
            if r["added_count"] > 0:
                diff_parts.append(f"+{r['added_count']}")
            if r["deleted_count"] > 0:
                diff_parts.append(f"-{r['deleted_count']}")
            if r["modified_count"] > 0:
                diff_parts.append(f"~{r['modified_count']}")

            diff_str = " ".join(diff_parts) if diff_parts else "No change"
            if r["summary"]:
                diff_str += f" ({r['summary']})"
            diff_item = QTableWidgetItem(diff_str)

            self.table.setItem(row, 0, pin_item)
            self.table.setItem(row, 1, id_item)
            self.table.setItem(row, 2, layer_item)
            self.table.setItem(row, 3, tag_item)
            self.table.setItem(row, 4, time_item)
            self.table.setItem(row, 5, trigger_item)
            self.table.setItem(row, 6, feat_item)
            self.table.setItem(row, 7, diff_item)

        self.lbl_table_stats.setText(f"{len(records)} restore points recorded")

        # Auto-select first row if available
        if len(records) > 0:
            self.table.selectRow(0)
        else:
            self.lbl_slider_time.setText("Step: 0/0")

    def _toggle_pin(self):
        """Toggle pinned status for selected snapshot."""
        if not self.selected_snapshot_id:
            return
        new_state = self.db.toggle_pin_snapshot(self.selected_snapshot_id)
        self.load_restore_points()

    def _set_tag(self):
        """Set a bookmark name/tag on the selected snapshot."""
        if not self.selected_snapshot_id:
            return
        snap_info = self.db.get_snapshot_info(self.selected_snapshot_id)
        current_tag = snap_info.get("tag", "") if snap_info else ""
        text, ok = QInputDialog.getText(
            self, "Bookmark Snapshot",
            "Enter bookmark name / tag for this restore point:",
            QtCompat.echo_normal(), current_tag
        )
        if ok:
            self.db.set_snapshot_tag(self.selected_snapshot_id, text.strip())
            self.load_restore_points()

    def _on_table_double_clicked(self, row: int, col: int):
        """Double click to toggle pin or edit tag."""
        if col == 0:
            self._toggle_pin()
        elif col == 3:
            self._set_tag()

    def _on_slider_scrubbed(self, value: int):
        """Sync table selection when user moves timeline slider."""
        if 0 <= value < self.table.rowCount():
            self.table.selectRow(value)

    def _filter_table(self, query: str):
        """Filter table rows based on search text."""
        query = query.strip().lower()
        for row in range(self.table.rowCount()):
            match = False
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item and query in item.text().lower():
                    match = True
                    break
            self.table.setRowHidden(row, not match)

    def _on_snapshot_created_externally(self, snapshot_id: int, layer_id: str, trigger_type: str):
        """Live update when background daemon records a snapshot."""
        if self.isVisible():
            self.load_restore_points()

    # --- Interactive Map Canvas Preview & Diff Engine ---

    def _on_table_selection_changed(self):
        """Triggered when user clicks a restore point in the table."""
        selected_rows = self.table.selectedItems()
        if not selected_rows:
            self.selected_snapshot_id = None
            return

        row = self.table.currentRow()
        id_item = self.table.item(row, 1)
        if not id_item:
            return

        snapshot_id = int(id_item.text())
        self.selected_snapshot_id = snapshot_id

        self.slider_time.blockSignals(True)
        self.slider_time.setValue(row)
        self.slider_time.blockSignals(False)
        self.lbl_slider_time.setText(
            f"Step: {row + 1}/{self.table.rowCount()}")

        self._render_snapshot_preview(snapshot_id)

    def _render_snapshot_preview(self, snapshot_id: int):
        """Build and render color-coded visual diff on embedded map canvas."""
        snap_info = self.db.get_snapshot_info(snapshot_id)
        if not snap_info:
            return

        layer_name = snap_info["layer_name"]
        geom_type = snap_info["geom_type"]
        crs_authid = snap_info["crs_authid"]
        fields_schema = json.loads(
            snap_info["fields_json"]) if snap_info["fields_json"] else []

        features_data = self.db.get_snapshot_features(snapshot_id)
        self.lbl_preview_info.setText(
            f"Preview: {layer_name} ({len(features_data)} features) @ {snap_info['timestamp'][:19]}"
        )

        # Get previous snapshot for accurate timeline diff
        prev_snapshot_id = self.db.get_previous_snapshot_id(
            snapshot_id, snap_info["layer_id"])
        if prev_snapshot_id:
            prev_features = self.db.get_snapshot_features(prev_snapshot_id)
            _, _, _, diff_data = self.db.compute_features_diff(
                prev_features, features_data)
        else:
            diff_data = {
                'added': features_data,
                'deleted': [],
                'modified': [],
                'unchanged': []
            }

        # Map geometry type to QGIS URI
        geom_uri = "Polygon"
        if "Line" in geom_type:
            geom_uri = "LineString"
        elif "Point" in geom_type:
            geom_uri = "Point"

        # Create temporary memory layer for rendering
        uri = f"{geom_uri}?crs={crs_authid}&field=_diff_status:string"
        for fld in fields_schema:
            uri += f"&field={fld['name']}:string"

        mem_layer = QgsVectorLayer(uri, f"Preview_{layer_name}", "memory")
        if not mem_layer.isValid():
            return

        dp = mem_layer.dataProvider()
        new_feats = []

        # Total rows in inspector = added + modified + unchanged + deleted
        total_items = (len(diff_data['added']) + len(diff_data['modified']) +
                       len(diff_data['unchanged']) + len(diff_data['deleted']))

        self.attr_table.clear()
        self.attr_table.setColumnCount(len(fields_schema) + 3)
        headers = ["Restore", "FID", "Diff Status"] + [f["name"]
                                                       for f in fields_schema]
        self.attr_table.setHorizontalHeaderLabels(headers)
        self.attr_table.setRowCount(total_items)
        self.current_inspector_features = []

        row_idx = 0

        # Helper to process diff category
        def add_category_features(feats_list, status_name):
            nonlocal row_idx
            for fid, wkb_bytes, attrs in feats_list:
                self.current_inspector_features.append(
                    (fid, wkb_bytes, attrs, status_name))

                feat = QgsFeature(mem_layer.fields())
                if wkb_bytes:
                    geom = QgsGeometry()
                    geom.fromWkb(wkb_bytes)
                    feat.setGeometry(geom)

                feat.setAttribute("_diff_status", status_name)
                for fld in fields_schema:
                    feat.setAttribute(fld["name"], str(
                        attrs.get(fld["name"], "")))

                new_feats.append(feat)

                # Checkbox item for selective restore
                chk_item = QTableWidgetItem()
                chk_item.setFlags(QtCompat.item_is_user_checkable(
                ) | QtCompat.item_is_enabled() | QtCompat.item_is_selectable())
                chk_item.setCheckState(
                    QtCompat.checked() if status_name != 'deleted' else QtCompat.unchecked())

                # Inspector table row
                fid_item = QTableWidgetItem(str(fid))
                status_item = QTableWidgetItem(status_name.upper())
                font = status_item.font()
                font.setBold(True)
                status_item.setFont(font)

                self.attr_table.setItem(row_idx, 0, chk_item)
                self.attr_table.setItem(row_idx, 1, fid_item)
                self.attr_table.setItem(row_idx, 2, status_item)
                for col_idx, fld in enumerate(fields_schema):
                    val_item = QTableWidgetItem(
                        str(attrs.get(fld["name"], "")))
                    self.attr_table.setItem(row_idx, col_idx + 3, val_item)

                row_idx += 1

        # Add categories in order
        add_category_features(diff_data['added'], "added")
        add_category_features(diff_data['modified'], "modified")
        add_category_features(diff_data['deleted'], "deleted")
        add_category_features(diff_data['unchanged'], "unchanged")

        dp.addFeatures(new_feats)
        mem_layer.updateExtents()

        # Apply Rule-Based Styling with vibrant diff colors
        self._apply_diff_styling(mem_layer, geom_uri)

        # Update Map Canvas
        self.preview_layer = mem_layer
        crs = QgsCoordinateReferenceSystem(crs_authid)
        if crs.isValid():
            self.canvas.setDestinationCrs(crs)
        self.canvas.setLayers([self.preview_layer])
        self.canvas.setExtent(self.preview_layer.extent())
        self.canvas.refresh()

    def _apply_diff_styling(self, layer: QgsVectorLayer, geom_type: str):
        """Apply rule-based color rendering for diff states."""
        root_rule = QgsRuleBasedRenderer.Rule(None)

        diff_colors = {
            # Green
            "added": ("\"_diff_status\" = 'added'", QColor(46, 125, 50, 180), "#2E7D32"),
            # Orange
            "modified": ("\"_diff_status\" = 'modified'", QColor(239, 108, 0, 180), "#EF6C00"),
            # Red
            "deleted": ("\"_diff_status\" = 'deleted'", QColor(198, 40, 40, 180), "#C62828"),
            # Blue
            "unchanged": ("\"_diff_status\" = 'unchanged'", QColor(33, 150, 243, 120), "#1976D2")
        }

        for status, (filter_expr, fill_color, stroke_hex) in diff_colors.items():
            fill_rgba_str = f"{fill_color.red()},{fill_color.green()},{fill_color.blue()},{fill_color.alpha()}"
            if "Polygon" in geom_type:
                symbol = QgsFillSymbol.createSimple({
                    'color': fill_rgba_str,
                    'color_border': stroke_hex,
                    'width_border': '1.2'
                })
            elif "Line" in geom_type:
                symbol = QgsLineSymbol.createSimple({
                    'color': stroke_hex,
                    'width': '2.0'
                })
            else:  # Point
                symbol = QgsMarkerSymbol.createSimple({
                    'color': fill_rgba_str,
                    'color_border': stroke_hex,
                    'size': '4.0',
                    'width_border': '1.0'
                })

            rule = QgsRuleBasedRenderer.Rule(symbol)
            rule.setFilterExpression(filter_expr)
            rule.setLabel(status.capitalize())
            root_rule.appendChild(rule)

        renderer = QgsRuleBasedRenderer(root_rule)
        layer.setRenderer(renderer)
        layer.triggerRepaint()

    def _zoom_preview_extent(self):
        """Fit preview canvas to layer extent."""
        if self.preview_layer:
            self.canvas.setExtent(self.preview_layer.extent())
            self.canvas.refresh()

    def _activate_pan_tool(self):
        """Toggle pan tool on canvas."""
        self.canvas.setMapTool(self.map_tool_pan)

    def _select_all_features(self):
        """Check all feature rows in inspector table."""
        for r in range(self.attr_table.rowCount()):
            item = self.attr_table.item(r, 0)
            if item:
                item.setCheckState(QtCompat.checked())

    def _select_no_features(self):
        """Uncheck all feature rows in inspector table."""
        for r in range(self.attr_table.rowCount()):
            item = self.attr_table.item(r, 0)
            if item:
                item.setCheckState(QtCompat.unchecked())

    def _restore_selected_features(self):
        """Restore only the checked features into the active QGIS layer without altering the rest of layer."""
        if not self.selected_snapshot_id:
            QMessageBox.warning(self, "No Selection",
                                "Please select a restore point first.")
            return

        snap_info = self.db.get_snapshot_info(self.selected_snapshot_id)
        if not snap_info:
            return

        layer_id = snap_info["layer_id"]
        layer_name = snap_info["layer_name"]
        target_layer = QgsProject.instance().mapLayer(layer_id)
        if not target_layer or not isinstance(target_layer, QgsVectorLayer) or not target_layer.isValid():
            QMessageBox.critical(
                self, "Layer Not Found", f"Layer '{layer_name}' is not currently loaded in project.")
            return

        # Collect checked rows
        selected_items = []
        for r in range(self.attr_table.rowCount()):
            item = self.attr_table.item(r, 0)
            if item and item.checkState() == QtCompat.checked():
                if r < len(getattr(self, 'current_inspector_features', [])):
                    selected_items.append(self.current_inspector_features[r])

        if not selected_items:
            QMessageBox.information(
                self, "No Features Checked", "Please check at least one feature in the table to restore.")
            return

        reply = QMessageBox.question(
            self, "Restore Selected Features",
            f"Restore {len(selected_items)} selected feature(s) into active layer '{layer_name}'?",
            QtCompat.btn_yes() | QtCompat.btn_no(), QtCompat.btn_yes()
        )
        if reply != QtCompat.btn_yes():
            return

        was_editing = target_layer.isEditable()
        if not was_editing:
            target_layer.startEditing()

        try:
            existing_fids = {f.id(): f for f in target_layer.getFeatures()}
            restored_count = 0

            for fid, wkb_bytes, attrs, status_name in selected_items:
                geom = QgsGeometry()
                if wkb_bytes:
                    geom.fromWkb(wkb_bytes)

                if fid in existing_fids:
                    # Update geometry & attributes on existing feature
                    if not geom.isEmpty():
                        target_layer.changeGeometry(fid, geom)
                    for fld_name, val in attrs.items():
                        idx = target_layer.fields().indexOf(fld_name)
                        if idx >= 0:
                            target_layer.changeAttributeValue(fid, idx, val)
                else:
                    # Add as new feature
                    new_f = QgsFeature(target_layer.fields())
                    if not geom.isEmpty():
                        new_f.setGeometry(geom)
                    for fld_name, val in attrs.items():
                        idx = target_layer.fields().indexOf(fld_name)
                        if idx >= 0:
                            new_f.setAttribute(idx, val)
                    target_layer.addFeature(new_f)

                restored_count += 1

            if not was_editing:
                target_layer.commitChanges()

            target_layer.updateExtents()
            target_layer.triggerRepaint()

            if iface and iface.messageBar():
                iface.messageBar().pushMessage(
                    "Data Recovery",
                    f"Restored {restored_count} feature(s) into '{layer_name}'.",
                    Qgis.MessageLevel.Success,
                    3
                )
            QMessageBox.information(
                self, "Restore Completed", f"Successfully restored {restored_count} feature(s) to '{layer_name}'.")

        except Exception as e:
            if not was_editing:
                target_layer.rollBack()
            QMessageBox.critical(self, "Restore Error",
                                 f"Error selectively restoring features: {e}")

    # --- Restoration & Export Handlers ---

    def _restore_inplace(self):
        """Rollback active layer in-place to the selected restore point state."""
        if not self.selected_snapshot_id:
            QMessageBox.warning(self, "No Selection", "Please select a restore point to restore.")
            return

        snap_info = self.db.get_snapshot_info(self.selected_snapshot_id)
        if not snap_info:
            return

        layer_id = snap_info["layer_id"]
        layer_name = snap_info["layer_name"]
        proj = QgsProject.instance()
        target_layer = proj.mapLayer(layer_id)

        if not isinstance(target_layer, QgsVectorLayer) or not target_layer.isValid():
            reply = QMessageBox.question(
                self, "Layer Not Found in Project",
                f"Layer '{layer_name}' is not currently loaded in project.\nDo you want to restore it as a new layer?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._restore_as_new_layer()
            return

        confirm = QMessageBox.question(
            self, "Confirm In-Place Restore",
            f"Are you sure you want to restore layer '{layer_name}' to state at {snap_info['timestamp'][:19]}?\n"
            f"Current edits will be replaced.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        # Snapshot current state right before rollback just in case
        self.daemon.create_snapshot_silent(target_layer, trigger_type="PRE_ROLLBACK", summary="Before Restore")

        features_data = self.db.get_snapshot_features(self.selected_snapshot_id)

        # Perform atomic feature replacement inside edit buffer
        was_editing = target_layer.isEditable()
        if not was_editing:
            target_layer.startEditing()

        try:
            # Delete all existing features
            existing_fids = [f.id() for f in target_layer.getFeatures()]
            if existing_fids:
                target_layer.deleteFeatures(existing_fids)

            # Insert snapshot features
            new_features = []
            for fid, wkb_bytes, attrs in features_data:
                feat = QgsFeature(target_layer.fields())
                if wkb_bytes:
                    geom = QgsGeometry()
                    geom.fromWkb(wkb_bytes)
                    feat.setGeometry(geom)
                for field in target_layer.fields():
                    if field.name() in attrs:
                        feat.setAttribute(field.name(), attrs[field.name()])
                new_features.append(feat)

            target_layer.addFeatures(new_features)

            if not was_editing:
                target_layer.commitChanges()

            target_layer.updateExtents()
            target_layer.triggerRepaint()

            if iface and iface.messageBar():
                iface.messageBar().pushMessage(
                    "Crash Recovery",
                    f"Successfully restored '{layer_name}' to {snap_info['timestamp'][:19]} ({len(new_features)} features)",
                    Qgis.MessageLevel.Success,
                    4
                )

            QMessageBox.information(
                self, "Restore Completed",
                f"Layer '{layer_name}' restored successfully ({len(new_features)} features)."
            )

        except Exception as e:
            if not was_editing:
                target_layer.rollBack()
            QMessageBox.critical(self, "Restore Failed", f"Error restoring layer: {e}")

    def _restore_as_new_layer(self):
        """Restore snapshot as a new memory or GeoPackage layer in current project."""
        if not self.selected_snapshot_id:
            QMessageBox.warning(self, "No Selection", "Please select a restore point.")
            return

        snap_info = self.db.get_snapshot_info(self.selected_snapshot_id)
        if not snap_info:
            return

        layer_name = snap_info["layer_name"]
        geom_type = snap_info["geom_type"]
        crs_authid = snap_info["crs_authid"]
        fields_schema = json.loads(snap_info["fields_json"]) if snap_info["fields_json"] else []
        features_data = self.db.get_snapshot_features(self.selected_snapshot_id)

        geom_uri = "Polygon"
        if "Line" in geom_type:
            geom_uri = "LineString"
        elif "Point" in geom_type:
            geom_uri = "Point"

        time_slug = snap_info["timestamp"][:19].replace(":", "-").replace("T", "_")
        recovered_name = f"[Recovered] {layer_name}_{time_slug}"

        uri = f"{geom_uri}?crs={crs_authid}"
        for fld in fields_schema:
            uri += f"&field={fld['name']}:{fld['type']}"

        new_layer = QgsVectorLayer(uri, recovered_name, "memory")
        if not new_layer.isValid():
            QMessageBox.critical(self, "Error", "Could not create recovered memory layer.")
            return

        dp = new_layer.dataProvider()
        new_feats = []
        for fid, wkb_bytes, attrs in features_data:
            feat = QgsFeature(new_layer.fields())
            if wkb_bytes:
                geom = QgsGeometry()
                geom.fromWkb(wkb_bytes)
                feat.setGeometry(geom)
            for fld in fields_schema:
                feat.setAttribute(fld["name"], attrs.get(fld["name"], None))
            new_feats.append(feat)

        dp.addFeatures(new_feats)
        new_layer.updateExtents()

        QgsProject.instance().addMapLayer(new_layer)

        if iface and iface.messageBar():
            iface.messageBar().pushMessage(
                "Crash Recovery",
                f"Added '{recovered_name}' to project.",
                Qgis.MessageLevel.Success,
                3
            )

    def _export_snapshot(self):
        """Export snapshot features directly to Shapefile or GeoPackage."""
        if not self.selected_snapshot_id:
            QMessageBox.warning(self, "No Selection", "Please select a restore point to export.")
            return

        snap_info = self.db.get_snapshot_info(self.selected_snapshot_id)
        if not snap_info:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Restore Point Layer",
            f"{snap_info['layer_name']}_recovery.gpkg",
            "GeoPackage (*.gpkg);;ESRI Shapefile (*.shp);;GeoJSON (*.geojson)"
        )
        if not file_path:
            return

        # Use preview layer or temporary memory layer
        if not self.preview_layer:
            self._render_snapshot_preview(self.selected_snapshot_id)

        driver = "GPKG"
        if file_path.endswith(".shp"):
            driver = "ESRI Shapefile"
        elif file_path.endswith(".geojson"):
            driver = "GeoJSON"

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = driver
        transform_context = QgsProject.instance().transformContext()

        error, msg = QgsVectorFileWriter.writeAsVectorFormatV3(
            self.preview_layer, file_path, transform_context, options
        )

        if error == QgsVectorFileWriter.WriterError.NoError:
            QMessageBox.information(self, "Export Success", f"Layer exported to:\n{file_path}")
        else:
            QMessageBox.critical(self, "Export Failed", f"Export failed: {msg}")

    def _create_manual_snapshot(self):
        """Capture an instant manual checkpoint for selected layer or all layers."""
        layer_id = self.layer_combo.currentData()
        proj = QgsProject.instance()

        if layer_id:
            layer = proj.mapLayer(layer_id)
            if isinstance(layer, QgsVectorLayer) and layer.isValid():
                snap_id = self.daemon.create_snapshot_silent(layer, trigger_type="MANUAL", summary="Manual Snapshot")
                if snap_id:
                    self.load_restore_points()
                    QMessageBox.information(self, "Snapshot Created", f"Manual restore point created for '{layer.name()}'.")
        else:
            count = 0
            for lyr in proj.mapLayers().values():
                if isinstance(lyr, QgsVectorLayer) and lyr.isValid():
                    self.daemon.create_snapshot_silent(lyr, trigger_type="MANUAL", summary="Manual Snapshot")
                    count += 1
            self.load_restore_points()
            QMessageBox.information(self, "Snapshots Created", f"Manual restore points created for {count} layers.")

    def _delete_selected_snapshot(self):
        """Delete selected restore point."""
        if not self.selected_snapshot_id:
            return
        reply = QMessageBox.question(
            self, "Delete Restore Point",
            "Are you sure you want to delete this restore point?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_snapshot(self.selected_snapshot_id)
            self.load_restore_points()

    def _clear_layer_history(self):
        """Clear all history for the selected layer."""
        layer_id = self.layer_combo.currentData()
        if not layer_id:
            QMessageBox.warning(self, "Select Layer", "Please select a specific layer from dropdown first.")
            return

        reply = QMessageBox.question(
            self, "Clear Layer History",
            "Are you sure you want to clear all recovery history for this layer?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.clear_layer_history(layer_id)
            self.load_restore_points()

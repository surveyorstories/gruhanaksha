# Qt5/Qt6 compatibility layer
from qgis.PyQt.QtGui import QDoubleValidator, QIntValidator
from qgis.PyQt.QtCore import QVariant, pyqtSignal, Qt, QTimer
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QTableWidget, QTableWidgetItem, QComboBox, QMessageBox,
    QGroupBox, QRadioButton, QWidget, QProgressBar, QCheckBox, QSpinBox,
    QSplitter, QTextEdit, QTabWidget, QFrame, QGridLayout, QScrollArea, QApplication,
    QLayout
)
import re
import os
import csv
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsProject,
    QgsCoordinateReferenceSystem, QgsFields, QgsField, QgsVectorFileWriter,
    QgsWkbTypes, QgsCoordinateTransform, QgsRectangle, Qgis
)
from qgis.gui import QgsProjectionSelectionWidget
from .qt_compat import QtCompat

# Local compatibility layer removed


# --- Configurable height ---
WIDGET_HEIGHT = 20


class PointInputDialog(QDialog):
    dialogClosed = pyqtSignal()

    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        # Force it as a top-level window that stays on top of QGIS
        self.setWindowFlags(
            QtCompat.Window
            | QtCompat.WindowTitleHint
            | QtCompat.CustomizeWindowHint
            | QtCompat.WindowCloseButtonHint
        )
        self.iface = iface
        self.setWindowTitle("Enhanced Points Creator")
        self.setMinimumSize(350, 600)
        self.setMaximumHeight(600)  # Prevent excessive expansion
        self.layer_name = None
        # Get project CRS
        self.project_crs = QgsProject.instance().crs()
        self.csv_headers = []
        self.csv_data = []
        self.preview_limit = 1000
        # Validation timer
        self.validation_timer = QTimer()
        self.validation_timer.timeout.connect(self.validate_inputs)
        self.validation_timer.setSingleShot(True)
        self._processing_paste = False
        self.setup_ui()
        self.setup_validation()

    def set_widget_min_height(self, widget):
        """Utility: set minimum height on widget if not window or layout"""
        if not widget.isWindow() and not isinstance(widget, QLayout):
            widget.setMinimumHeight(WIDGET_HEIGHT)

    def setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(6)

        # --- STANDALONE CRS SELECTOR AT TOP ---
        crs_group = QGroupBox("Target Coordinate Reference System")
        self.set_widget_min_height(crs_group)
        crs_layout = QVBoxLayout()
        crs_layout.setContentsMargins(2, 2, 2, 2)
        crs_layout.setSpacing(2)
        self.crs_selector = QgsProjectionSelectionWidget()
        self.crs_selector.setCrs(self.project_crs if self.project_crs.isValid(
        ) else QgsCoordinateReferenceSystem("EPSG:4326"))
        self.set_widget_min_height(self.crs_selector)
        self.crs_info_label = QLabel()
        crs_layout.addWidget(self.crs_selector)
        crs_layout.addWidget(self.crs_info_label)
        self.update_crs_info()
        crs_group.setLayout(crs_layout)
        main_layout.addWidget(crs_group)

        # --- TAB WIDGET ---
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # Tab 0: Manual Input
        manual_tab = self.create_manual_input_tab()
        self.tab_widget.addTab(manual_tab, "Manual Input")

        # Tab 1: CSV Import
        csv_tab = self.create_csv_import_tab()
        self.tab_widget.addTab(csv_tab, "CSV Import")

        # Status, progress section
        self.create_status_section(main_layout)

        # Action buttons
        self.create_action_buttons(main_layout)

        self.setLayout(main_layout)
        self.connect_signals()

    def create_manual_input_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)

        # Coordinate format selection
        format_group = QGroupBox("Coordinate Format")
        self.set_widget_min_height(format_group)
        format_layout = QHBoxLayout()
        self.utm_radio = QRadioButton("UTM Coordinates")
        self.dd_radio = QRadioButton("Decimal Degrees (DD)")
        self.dms_radio = QRadioButton("Degrees Minutes Seconds (DMS)")
        self.utm_radio.setChecked(True)
        format_layout.addWidget(self.utm_radio)
        format_layout.addWidget(self.dd_radio)
        format_layout.addWidget(self.dms_radio)
        format_group.setLayout(format_layout)
        layout.addWidget(format_group)

        # UTM Source CRS selector (now separate)
        self.utm_crs_group = self.create_utm_crs_group()
        layout.addWidget(self.utm_crs_group)

        # Coordinate input sections
        self.create_coordinate_inputs(layout)

        # Batch input section
        self.create_batch_input_section(layout)

        tab.setLayout(layout)
        return tab

    def create_utm_crs_group(self):
        """Creates the UTM source CRS selection group box."""
        utm_crs_group = QGroupBox("UTM Source Coordinate System")
        utm_crs_layout = QVBoxLayout()
        utm_crs_layout.setContentsMargins(2, 2, 2, 2)
        utm_crs_layout.setSpacing(2)
        self.utm_crs_selector = QgsProjectionSelectionWidget()
        # Set default to a common UTM zone (UTM Zone 33N - EPSG:32633)
        default_utm_crs = QgsCoordinateReferenceSystem("EPSG:32633")
        self.utm_crs_selector.setCrs(default_utm_crs)
        self.set_widget_min_height(self.utm_crs_selector)
        self.utm_crs_info_label = QLabel()
        utm_crs_layout.addWidget(self.utm_crs_selector)
        utm_crs_layout.addWidget(self.utm_crs_info_label)
        utm_crs_group.setLayout(utm_crs_layout)
        return utm_crs_group

    def create_coordinate_inputs(self, layout):
        self.coord_container = QWidget()
        self.set_widget_min_height(self.coord_container)
        coord_layout = QVBoxLayout()
        coord_layout.setContentsMargins(0, 0, 0, 0)
        coord_layout.setSpacing(2)

        # DD inputs
        self.dd_widget = QWidget()
        self.set_widget_min_height(self.dd_widget)
        dd_layout = QGridLayout()
        dd_layout.setContentsMargins(0, 0, 0, 0)
        dd_layout.setSpacing(2)
        dd_layout.addWidget(QLabel("X (Longitude/Easting):"), 0, 0)
        self.x_input = QLineEdit()
        self.x_input.setPlaceholderText("e.g., 78.12345 or -122.4194")
        self.set_widget_min_height(self.x_input)
        self.x_validation_label = QLabel()
        dd_layout.addWidget(self.x_input, 0, 1)
        dd_layout.addWidget(self.x_validation_label, 0, 2)
        dd_layout.addWidget(QLabel("Y (Latitude/Northing):"), 1, 0)
        self.y_input = QLineEdit()
        self.y_input.setPlaceholderText("e.g., 12.34567 or 37.7749")
        self.set_widget_min_height(self.y_input)
        self.y_validation_label = QLabel()
        dd_layout.addWidget(self.y_input, 1, 1)
        dd_layout.addWidget(self.y_validation_label, 1, 2)
        example_label = QLabel("Examples: 78.12345, -122.4194")
        example_label.setStyleSheet("color: gray; font-style: italic;")
        dd_layout.addWidget(example_label, 2, 0, 1, 3)
        self.dd_widget.hide()
        self.dd_widget.setLayout(dd_layout)
        coord_layout.addWidget(self.dd_widget)

        # DMS inputs
        self.dms_widget = QWidget()
        self.set_widget_min_height(self.dms_widget)
        dms_layout = QGridLayout()
        dms_layout.setContentsMargins(0, 0, 0, 0)
        dms_layout.setSpacing(2)
        dms_layout.addWidget(QLabel("X/Longitude:"), 0, 0)
        self.x_deg = QLineEdit()
        self.set_widget_min_height(self.x_deg)
        self.x_min = QLineEdit()
        self.set_widget_min_height(self.x_min)
        self.x_sec = QLineEdit()
        self.set_widget_min_height(self.x_sec)
        self.x_deg.setPlaceholderText("Deg")
        dms_layout.addWidget(self.x_deg, 0, 1)
        dms_layout.addWidget(QLabel("°"), 0, 2)
        dms_layout.addWidget(self.x_min, 0, 3)
        dms_layout.addWidget(QLabel("'"), 0, 4)
        dms_layout.addWidget(self.x_sec, 0, 5)
        dms_layout.addWidget(QLabel("\""), 0, 6)

        dms_layout.addWidget(QLabel("Y/Latitude:"), 1, 0)
        self.y_deg = QLineEdit()
        self.set_widget_min_height(self.y_deg)
        self.y_deg.setPlaceholderText("Deg")
        self.y_min = QLineEdit()
        self.set_widget_min_height(self.y_min)
        self.y_min.setPlaceholderText("Min")
        self.y_sec = QLineEdit()
        self.set_widget_min_height(self.y_sec)
        self.y_sec.setPlaceholderText("Sec")
        dms_layout.addWidget(self.y_deg, 1, 1)
        dms_layout.addWidget(QLabel("°"), 1, 2)
        dms_layout.addWidget(self.y_min, 1, 3)
        dms_layout.addWidget(QLabel("'"), 1, 4)
        dms_layout.addWidget(self.y_sec, 1, 5)
        dms_layout.addWidget(QLabel("\""), 1, 6)

        self.dms_widget.setLayout(dms_layout)
        self.dms_widget.hide()
        coord_layout.addWidget(self.dms_widget)

        # UTM inputs
        self.utm_widget = QWidget()
        self.set_widget_min_height(self.utm_widget)
        utm_layout = QVBoxLayout()
        utm_layout.setContentsMargins(0, 0, 0, 0)
        utm_layout.setSpacing(4)

        # UTM coordinate inputs
        coord_inputs_widget = QWidget()
        coord_inputs_layout = QGridLayout()
        coord_inputs_layout.setContentsMargins(0, 0, 0, 0)
        coord_inputs_layout.setSpacing(2)
        coord_inputs_layout.addWidget(QLabel("Easting (X):"), 0, 0)
        self.utm_x_input = QLineEdit()
        self.set_widget_min_height(self.utm_x_input)
        self.utm_x_input.setPlaceholderText("e.g., 500000")
        coord_inputs_layout.addWidget(self.utm_x_input, 0, 1)
        coord_inputs_layout.addWidget(QLabel("Northing (Y):"), 1, 0)
        self.utm_y_input = QLineEdit()
        self.set_widget_min_height(self.utm_y_input)
        self.utm_y_input.setPlaceholderText("e.g., 4500000")
        coord_inputs_layout.addWidget(self.utm_y_input, 1, 1)
        coord_inputs_widget.setLayout(coord_inputs_layout)
        utm_layout.addWidget(coord_inputs_widget)

        self.utm_widget.setLayout(utm_layout)
        coord_layout.addWidget(self.utm_widget)

        self.coord_container.setLayout(coord_layout)
        layout.addWidget(self.coord_container)

        # Update UTM CRS info initially
        self.update_utm_crs_info()

    def create_batch_input_section(self, layout):
        batch_group = QGroupBox("Batch Point Creation")
        self.set_widget_min_height(batch_group)
        batch_layout = QVBoxLayout()
        batch_layout.setContentsMargins(0, 0, 0, 0)
        batch_layout.setSpacing(2)
        self.enable_batch = QCheckBox("Enable batch input (paste coordinates)")

        # Add coordinate format info label
        self.batch_format_label = QLabel()
        self.batch_format_label.setStyleSheet(
            "color: blue; font-weight: bold; font-style: italic;")
        self.batch_format_label.setWordWrap(True)

        self.batch_text = QTextEdit()
        self.batch_text.setMinimumHeight(80)
        self.batch_text.setMaximumHeight(150)
        self.batch_text.setPlaceholderText(
            "Paste coordinates here, one per line:\n"
            "Format: X,Y or X Y or X\tY\n"
            "Example:\n78.123,12.345\n79.456 13.678\n80.789\t14.012"
        )
        self.batch_text.hide()
        batch_layout.addWidget(self.enable_batch)
        batch_layout.addWidget(self.batch_format_label)
        batch_layout.addWidget(self.batch_text)
        self.batch_count_label = QLabel("Points to create: 0")
        self.batch_count_label.hide()
        batch_layout.addWidget(self.batch_count_label)
        batch_group.setLayout(batch_layout)
        layout.addWidget(batch_group)

        # Initialize format label
        self.update_batch_format_label()

    def create_csv_import_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        # File selection group
        csv_group = QGroupBox("CSV File Selection")
        self.set_widget_min_height(csv_group)
        csv_layout = QVBoxLayout()
        csv_layout.setContentsMargins(2, 2, 2, 2)
        csv_layout.setSpacing(2)
        file_layout = QHBoxLayout()
        file_layout.setSpacing(2)
        self.csv_path = QLineEdit()
        self.set_widget_min_height(self.csv_path)
        self.csv_path.setPlaceholderText("Select a CSV file...")
        self.csv_button = QPushButton("Browse CSV...")
        self.set_widget_min_height(self.csv_button)
        file_layout.addWidget(self.csv_path)
        file_layout.addWidget(self.csv_button)
        csv_layout.addLayout(file_layout)

        # CSV options
        options_layout = QHBoxLayout()
        options_layout.setSpacing(2)
        self.csv_delimiter_combo = QComboBox()
        self.set_widget_min_height(self.csv_delimiter_combo)
        self.csv_delimiter_combo.addItems([",", ";", "\t", "|"])
        self.csv_delimiter_combo.setCurrentText(",")
        self.csv_has_header = QCheckBox("First row contains headers")
        self.csv_has_header.setChecked(True)
        self.csv_encoding_combo = QComboBox()
        self.set_widget_min_height(self.csv_encoding_combo)
        self.csv_encoding_combo.addItems(["utf-8", "latin-1", "cp1252"])
        options_layout.addWidget(QLabel("Delimiter:"))
        options_layout.addWidget(self.csv_delimiter_combo)
        options_layout.addWidget(self.csv_has_header)
        options_layout.addWidget(QLabel("Encoding:"))
        options_layout.addWidget(self.csv_encoding_combo)
        csv_layout.addLayout(options_layout)
        csv_group.setLayout(csv_layout)
        layout.addWidget(csv_group)

        # Field mapping group
        mapping_group = QGroupBox("Field Mapping")
        self.set_widget_min_height(mapping_group)
        mapping_layout = QGridLayout()
        mapping_layout.setContentsMargins(2, 2, 2, 2)
        mapping_layout.setSpacing(2)
        mapping_layout.addWidget(QLabel("X/Longitude Field:"), 0, 0)
        self.x_field_combo = QComboBox()
        self.set_widget_min_height(self.x_field_combo)
        mapping_layout.addWidget(self.x_field_combo, 0, 1)
        mapping_layout.addWidget(QLabel("Y/Latitude Field:"), 0, 2)
        self.y_field_combo = QComboBox()
        self.set_widget_min_height(self.y_field_combo)
        mapping_layout.addWidget(self.y_field_combo, 0, 3)
        self.auto_detect_btn = QPushButton("Auto-detect coordinate fields")
        self.set_widget_min_height(self.auto_detect_btn)
        mapping_layout.addWidget(self.auto_detect_btn, 1, 0, 1, 4)
        mapping_group.setLayout(mapping_layout)
        layout.addWidget(mapping_group)

        # Preview controls
        preview_controls = QHBoxLayout()
        preview_controls.setSpacing(2)
        self.preview_limit_spin = QSpinBox()
        self.set_widget_min_height(self.preview_limit_spin)
        self.preview_limit_spin.setRange(10, 10000)
        self.preview_limit_spin.setValue(self.preview_limit)
        self.preview_limit_spin.setSuffix(" rows")
        self.refresh_preview_btn = QPushButton("Refresh Preview")
        self.set_widget_min_height(self.refresh_preview_btn)
        preview_controls.addWidget(QLabel("Preview limit:"))
        preview_controls.addWidget(self.preview_limit_spin)
        preview_controls.addWidget(self.refresh_preview_btn)
        layout.addLayout(preview_controls)

        # Table inside a scroll area
        scroll = QScrollArea()
        table_container = QWidget()
        self.set_widget_min_height(table_container)
        table_layout = QVBoxLayout()
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        table_layout.addWidget(self.table)
        table_container.setLayout(table_layout)
        scroll.setWidget(table_container)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)

        tab.setLayout(layout)
        return tab

    def create_status_section(self, parent_layout):
        status_group = QGroupBox("Status")
        self.set_widget_min_height(status_group)
        status_layout = QVBoxLayout()
        status_layout.setContentsMargins(2, 2, 2, 2)
        status_layout.setSpacing(2)
        self.coord_count_label = QLabel("Ready to create points")
        self.coord_count_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(self.coord_count_label)
        self.progress_bar = QProgressBar()
        self.set_widget_min_height(self.progress_bar)
        self.progress_bar.hide()
        status_layout.addWidget(self.progress_bar)
        self.status_text = QLabel("")
        self.status_text.setWordWrap(True)
        status_layout.addWidget(self.status_text)
        status_group.setLayout(status_layout)
        parent_layout.addWidget(status_group)

    def create_action_buttons(self, parent_layout):
        button_layout = QHBoxLayout()
        button_layout.setSpacing(2)
        self.clear_btn = QPushButton("Clear All")
        self.set_widget_min_height(self.clear_btn)
        self.preview_btn = QPushButton("Preview Points")
        self.set_widget_min_height(self.preview_btn)
        self.preview_btn.setToolTip("Preview points before creation")
        self.create_button = QPushButton("Create Points")
        self.set_widget_min_height(self.create_button)
        self.create_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 3px 10px;
                border: none;
                border-radius: 2px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        button_layout.addWidget(self.clear_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.preview_btn)
        button_layout.addWidget(self.create_button)
        parent_layout.addLayout(button_layout)

    def _trim_sender_text_on_change(self):
        sender = self.sender()
        if sender and isinstance(sender, QLineEdit):
            original_text = sender.text()
            trimmed_text = original_text.strip()
            if original_text != trimmed_text:
                # Block signals to prevent recursion
                sender.blockSignals(True)
                sender.setText(trimmed_text)
                sender.blockSignals(False)

    def _handle_coordinate_paste(self, text, x_widget, y_widget):
        # Check a flag to prevent re-entry and loops.
        if getattr(self, '_processing_paste', False):
            return
        # Regex to find floating point numbers in the text.
        numbers = re.findall(r"[-+]?\d*\.?\d+", text)
        # If we find at least two numbers, we assume they are a coordinate pair.
        if len(numbers) >= 2:
            self._processing_paste = True
            try:
                # Block signals to prevent textChanged from firing again recursively.
                x_widget.blockSignals(True)
                y_widget.blockSignals(True)
                # Set the extracted numbers to the widgets.
                x_widget.setText(numbers[0])
                y_widget.setText(numbers[1])
            finally:
                # Always unblock signals and reset the flag.
                x_widget.blockSignals(False)
                y_widget.blockSignals(False)
                self._processing_paste = False
            # Manually trigger validation and move focus.
            self.start_validation_timer()
            y_widget.setFocus()
            return
        # If not a pair, just trim the current field.
        sender_widget = self.sender()
        if sender_widget:
            original_text = sender_widget.text()
            trimmed_text = original_text.strip()
            if original_text != trimmed_text:
                self._processing_paste = True
                try:
                    sender_widget.blockSignals(True)
                    sender_widget.setText(trimmed_text)
                finally:
                    sender_widget.blockSignals(False)
                    self._processing_paste = False
        self.start_validation_timer()

    def setup_validation(self):
        # Validators removed to allow pasting coordinate pairs with separators
        pass

    def connect_signals(self):
        self.csv_button.clicked.connect(self.browse_csv)
        self.create_button.clicked.connect(self.create_points)
        self.preview_btn.clicked.connect(self.preview_points)
        self.clear_btn.clicked.connect(self.clear_all)
        self.dd_radio.toggled.connect(self.toggle_coordinate_format)
        self.dms_radio.toggled.connect(self.toggle_coordinate_format)
        self.utm_radio.toggled.connect(self.toggle_coordinate_format)
        self.x_input.textChanged.connect(
            lambda text: self._handle_coordinate_paste(text, self.x_input, self.y_input))
        self.y_input.textChanged.connect(
            lambda text: self._handle_coordinate_paste(text, self.x_input, self.y_input))
        self.utm_x_input.textChanged.connect(
            lambda text: self._handle_coordinate_paste(text, self.utm_x_input, self.utm_y_input))
        self.utm_y_input.textChanged.connect(
            lambda text: self._handle_coordinate_paste(text, self.utm_x_input, self.utm_y_input))
        self.x_deg.textChanged.connect(self._trim_sender_text_on_change)
        self.x_deg.textChanged.connect(self.start_validation_timer)
        self.x_min.textChanged.connect(self._trim_sender_text_on_change)
        self.x_min.textChanged.connect(self.start_validation_timer)
        self.x_sec.textChanged.connect(self._trim_sender_text_on_change)
        self.x_sec.textChanged.connect(self.start_validation_timer)
        self.y_deg.textChanged.connect(self._trim_sender_text_on_change)
        self.y_deg.textChanged.connect(self.start_validation_timer)
        self.y_min.textChanged.connect(self._trim_sender_text_on_change)
        self.y_min.textChanged.connect(self.start_validation_timer)
        self.y_sec.textChanged.connect(self._trim_sender_text_on_change)
        self.y_sec.textChanged.connect(self.start_validation_timer)
        self.enable_batch.toggled.connect(self.toggle_batch_input)
        self.batch_text.textChanged.connect(self.update_batch_count)
        self.csv_delimiter_combo.currentTextChanged.connect(
            self.reload_csv_preview)
        self.csv_has_header.toggled.connect(self.reload_csv_preview)
        self.csv_encoding_combo.currentTextChanged.connect(
            self.reload_csv_preview)
        self.auto_detect_btn.clicked.connect(
            self.auto_detect_coordinate_fields)
        self.refresh_preview_btn.clicked.connect(self.reload_csv_preview)
        self.preview_limit_spin.valueChanged.connect(self.update_preview_limit)
        self.crs_selector.crsChanged.connect(self.update_crs_info)
        self.utm_crs_selector.crsChanged.connect(self.update_utm_crs_info)

    def start_validation_timer(self):
        self.validation_timer.start(500)

    def validate_inputs(self):
        if self.tab_widget.currentIndex() == 0:
            # Manual input tab
            if self.enable_batch.isChecked():
                inputs_valid = self.validate_batch_input()
            else:
                # Check which format is selected
                if self.dd_radio.isChecked():
                    x_valid = self.validate_coordinate_input(
                        self.x_input, self.x_validation_label, "X")
                    y_valid = self.validate_coordinate_input(
                        self.y_input, self.y_validation_label, "Y")
                    inputs_valid = x_valid and y_valid
                elif self.utm_radio.isChecked():
                    # Validate UTM coordinates
                    x_text = self.utm_x_input.text().strip()
                    y_text = self.utm_y_input.text().strip()
                    inputs_valid = False
                    if x_text and y_text:
                        try:
                            x = float(x_text)
                            y = float(y_text)
                            # Basic validation - UTM coordinates should be positive and reasonable
                            inputs_valid = (
                                x > 0 and y > 0 and x < 1000000 and y < 10000000)
                        except ValueError:
                            inputs_valid = False
                elif self.dms_radio.isChecked():
                    # Validate DMS coordinates
                    x_deg = self.x_deg.text().strip()
                    x_min = self.x_min.text().strip()
                    x_sec = self.x_sec.text().strip()
                    y_deg = self.y_deg.text().strip()
                    y_min = self.y_min.text().strip()
                    y_sec = self.y_sec.text().strip()

                    inputs_valid = False
                    if x_deg and y_deg:  # At minimum, degrees must be present
                        try:
                            x_dd = self.dms_to_dd(x_deg, x_min, x_sec)
                            y_dd = self.dms_to_dd(y_deg, y_min, y_sec)
                            # Validate range
                            inputs_valid = (-180 <= x_dd <=
                                            180) and (-90 <= y_dd <= 90)
                        except (ValueError, TypeError):
                            inputs_valid = False
                else:
                    inputs_valid = False
        else:
            # CSV import tab
            inputs_valid = bool(self.csv_data and self.x_field_combo.currentText(
            ) and self.y_field_combo.currentText())

        self.create_button.setEnabled(inputs_valid)

    def validate_coordinate_input(self, widget, label, coord_type):
        text = widget.text().strip()
        if not text:
            label.setText("")
            return False
        try:
            value = float(text)
            if coord_type == "X" and (value < -180 or value > 180):
                label.setText("⚠ Out of range")
                label.setStyleSheet("color: orange;")
                return False
            elif coord_type == "Y" and (value < -90 or value > 90):
                label.setText("⚠ Out of range")
                label.setStyleSheet("color: orange;")
                return False
            label.setText("✓")
            label.setStyleSheet("color: green;")
            return True
        except ValueError:
            label.setText("✗ Invalid")
            label.setStyleSheet("color: red;")
            return False

    def validate_batch_input(self):
        text = self.batch_text.toPlainText().strip()
        if not text:
            return False
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        valid = any(
            any(
                len(parts) >= 2 and all(
                    p.strip().replace(".", "", 1).lstrip("-").isdigit()
                    for p in parts[:2]
                )
                for parts in [line.split(sep) for sep in (",", " ", "\t", ";")]
            )
            for line in lines
        )
        return valid

    def update_batch_count(self):
        if not self.enable_batch.isChecked():
            return
        text = self.batch_text.toPlainText().strip()
        if not text:
            self.batch_count_label.setText("Points to create: 0")
            return
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        valid = 0
        warnings = []

        for line in lines:
            for sep in [',', ' ', '\t', ';']:
                parts = [p.strip() for p in line.split(sep) if p.strip()]
                if len(parts) >= 2:
                    try:
                        x = float(parts[0])
                        y = float(parts[1])

                        # Validate coordinate ranges based on format
                        if self.dd_radio.isChecked() or self.dms_radio.isChecked():
                            # DD/DMS should be in WGS84 range
                            if abs(x) > 180 or abs(y) > 90:
                                warnings.append(
                                    f"Line '{line}': Values out of DD range (-180 to 180, -90 to 90)")
                                break
                        elif self.utm_radio.isChecked():
                            # UTM coordinates are typically larger values
                            if abs(x) < 180 and abs(y) < 90:
                                warnings.append(
                                    f"Line '{line}': Values look like DD, but UTM format is selected")
                                break

                        valid += 1
                        break
                    except (ValueError, TypeError):
                        continue

        label_text = f"Points to create: {valid}"
        if warnings and len(warnings) <= 3:
            label_text += f"\n⚠ {'; '.join(warnings[:3])}"
        elif warnings:
            label_text += f"\n⚠ {len(warnings)} coordinate warnings detected"

        self.batch_count_label.setText(label_text)

    def toggle_coordinate_format(self):
        is_utm = self.utm_radio.isChecked()
        self.dd_widget.setVisible(self.dd_radio.isChecked())
        self.dms_widget.setVisible(self.dms_radio.isChecked())
        self.utm_widget.setVisible(is_utm)
        self.utm_crs_group.setVisible(is_utm)

        # Update batch format label and placeholder
        self.update_batch_format_label()

        # Update batch input placeholder based on coordinate format
        if self.utm_radio.isChecked():
            self.batch_text.setPlaceholderText(
                "Paste UTM coordinates here, one per line:\n"
                "Format: Easting,Northing or Easting Northing or Easting\tNorthing\n"
                "Example:\n"
                "194691.154,2049609.412\n"
                "500000 4500000\n"
                "600000\t5000000\n"
                "Note: Uses UTM Source CRS selected above"
            )
        elif self.dd_radio.isChecked():
            self.batch_text.setPlaceholderText(
                "Paste Decimal Degree coordinates here, one per line:\n"
                "Format: Longitude,Latitude or X,Y\n"
                "Example:\n"
                "78.123,12.345\n"
                "79.456 13.678\n"
                "80.789\t14.012\n"
                "Note: Expected in WGS84 (EPSG:4326)"
            )
        else:  # DMS
            self.batch_text.setPlaceholderText(
                "Paste coordinates here, one per line:\n"
                "For batch DMS input, use Decimal Degrees format\n"
                "Format: Longitude,Latitude\n"
                "Example:\n"
                "78.123,12.345\n"
                "79.456 13.678\n"
                "Note: DMS strings not supported in batch mode"
            )

    def update_batch_format_label(self):
        """Update the batch format info label based on selected coordinate format"""
        if self.utm_radio.isChecked():
            utm_crs = self.utm_crs_selector.crs()
            self.batch_format_label.setText(
                f"📍 Batch Mode: UTM Coordinates (Source: {utm_crs.authid() if utm_crs.isValid() else 'Not set'})"
            )
        elif self.dd_radio.isChecked():
            self.batch_format_label.setText(
                "📍 Batch Mode: Decimal Degrees (WGS84 / EPSG:4326)")
        else:  # DMS
            self.batch_format_label.setText(
                "📍 Batch Mode: Use Decimal Degrees format (DMS strings not supported)")

    def toggle_batch_input(self, enabled):
        self.batch_text.setVisible(enabled)
        self.batch_count_label.setVisible(enabled)
        self.batch_format_label.setVisible(enabled)
        self.coord_container.setVisible(not enabled)

        # Update UTM CRS info when UTM radio button is selected
        if self.utm_radio.isChecked():
            self.update_utm_crs_info()

        if enabled:
            self.update_batch_format_label()

        # Force layout recalculation to prevent UI expansion
        QApplication.processEvents()
        self.tab_widget.currentWidget().updateGeometry()
        self.updateGeometry()

    def update_crs_info(self):
        crs = self.crs_selector.crs()
        if crs.isValid():
            info = f"Target: EPSG:{crs.postgisSrid()} - {crs.description()}"
            info += " (Geographic)" if crs.isGeographic() else " (Projected)"
            self.crs_info_label.setText(info)
        else:
            self.crs_info_label.setText("Invalid target CRS selected")

    def update_utm_crs_info(self):
        """Update the UTM CRS information label"""
        crs = self.utm_crs_selector.crs()
        if crs.isValid():
            info = f"Source: {crs.authid()} - {crs.description()}"
            if crs.isGeographic():
                info += " (Geographic - not suitable for UTM coordinates)"
                self.utm_crs_info_label.setStyleSheet(
                    "color: red; font-style: italic;")
            else:
                info += " (Projected)"
                self.utm_crs_info_label.setStyleSheet(
                    "color: gray; font-style: italic;")
            self.utm_crs_info_label.setText(info)
        else:
            self.utm_crs_info_label.setText("Invalid source CRS selected")
            self.utm_crs_info_label.setStyleSheet(
                "color: red; font-style: italic;")

        # Update batch format label if UTM is selected
        if hasattr(self, 'batch_format_label') and self.utm_radio.isChecked():
            self.update_batch_format_label()

    def update_preview_limit(self, value):
        self.preview_limit = value
        if self.csv_data:
            self.update_table_display()

    def browse_csv(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select CSV file", "", "CSV files (*.csv);;Text files (*.txt);;All files (*.*)"
        )
        if filename:
            self.csv_path.setText(filename)
            self.load_csv_preview(filename)

    def load_csv_preview(self, filename):
        if not filename or not os.path.exists(filename):
            self.show_status_message("No valid CSV file selected", "warning")
            return
        try:
            self.progress_bar.show()
            self.progress_bar.setRange(0, 0)
            self.csv_headers = []
            self.csv_data = []
            self.table.clear()
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.x_field_combo.clear()
            self.y_field_combo.clear()
            delimiter = "\t" if self.csv_delimiter_combo.currentText(
            ) == "\t" else self.csv_delimiter_combo.currentText()
            encoding = self.csv_encoding_combo.currentText()
            has_header = self.csv_has_header.isChecked()
            with open(filename, 'r', encoding=encoding) as f:
                reader = csv.reader(f, delimiter=delimiter)
                first_row = next(reader)
                if not first_row:
                    raise ValueError("Empty CSV")
                if has_header:
                    self.csv_headers = [col.strip() for col in first_row]
                else:
                    self.csv_headers = [
                        f"Column_{i+1}" for i in range(len(first_row))]
                for row in reader:
                    if len(self.csv_data) >= self.preview_limit:
                        break
                    if len(row) == len(self.csv_headers) and any(cell.strip() for cell in row):
                        self.csv_data.append([cell.strip() for cell in row])
                if not self.csv_data:
                    raise ValueError("No data rows found in CSV")
                self.update_table_display()
                self.update_field_combos()
                self.auto_detect_coordinate_fields()
                self.coord_count_label.setText(
                    f"Loaded {len(self.csv_data)} rows")
                self.show_status_message("CSV loaded successfully", "success")
        except Exception as e:
            self.show_status_message(f"Failed to load CSV: {str(e)}", "error")
        finally:
            self.progress_bar.hide()

    def reload_csv_preview(self):
        if self.csv_path.text():
            self.load_csv_preview(self.csv_path.text())

    def update_table_display(self):
        if not self.csv_data:
            return
        self.table.setColumnCount(len(self.csv_headers))
        self.table.setHorizontalHeaderLabels(self.csv_headers)
        display_rows = min(len(self.csv_data), self.preview_limit)
        self.table.setRowCount(display_rows)
        for i in range(display_rows):
            for j, value in enumerate(self.csv_data[i]):
                item = QTableWidgetItem(str(value))
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()

    def update_field_combos(self):
        self.x_field_combo.clear()
        self.y_field_combo.clear()
        self.x_field_combo.addItems(self.csv_headers)
        self.y_field_combo.addItems(self.csv_headers)

    def auto_detect_coordinate_fields(self):
        if not self.csv_headers:
            return
        x_patterns = ['x', 'lon', 'long', 'longitude', 'easting', 'east']
        y_patterns = ['y', 'lat', 'latitude', 'northing', 'north']
        x_field = y_field = None
        for header in self.csv_headers:
            h = header.lower().strip()
            if any(p in h for p in x_patterns):
                x_field = header
            elif any(p in h for p in y_patterns):
                y_field = header
        if x_field:
            idx = self.x_field_combo.findText(x_field)
            if idx >= 0:
                self.x_field_combo.setCurrentIndex(idx)
        if y_field:
            idx = self.y_field_combo.findText(y_field)
            if idx >= 0:
                self.y_field_combo.setCurrentIndex(idx)

    def show_status_message(self, message, level="info"):
        colors = {
            "success": "color: green;",
            "warning": "color: orange;",
            "error": "color: red;",
            "info": "color: black;"
        }
        self.status_text.setText(message)
        self.status_text.setStyleSheet(colors.get(level, colors["info"]))

        # Map level strings to QGIS message bar levels
        try:
            if level == "error":
                try:
                    msg_level = Qgis.MessageLevel.Critical
                except AttributeError:
                    msg_level = getattr(Qgis, 'Critical', 2)
                self.iface.messageBar().pushMessage("Error", message, msg_level, 5)
            elif level == "success":
                try:
                    msg_level = Qgis.MessageLevel.Success
                except AttributeError:
                    msg_level = getattr(Qgis, 'Success', 3)
                self.iface.messageBar().pushMessage("Success", message, msg_level, 3)
            elif level == "warning":
                try:
                    msg_level = Qgis.MessageLevel.Warning
                except AttributeError:
                    msg_level = getattr(Qgis, 'Warning', 1)
                self.iface.messageBar().pushMessage("Warning", message, msg_level, 4)
        except Exception:  # nosec B110
            pass

    def clear_all(self):
        reply = QtCompat.message_box_question(
            self, 'Clear All', 'Are you sure you want to clear all inputs?',
            QtCompat.Yes | QtCompat.No, QtCompat.No
        )
        if reply == QtCompat.Yes:
            self.x_input.clear()
            self.y_input.clear()
            self.x_deg.clear()
            self.x_min.clear()
            self.x_sec.clear()
            self.y_deg.clear()
            self.y_min.clear()
            self.y_sec.clear()
            self.utm_x_input.clear()
            self.utm_y_input.clear()
            self.batch_text.clear()
            self.enable_batch.setChecked(False)
            self.csv_path.clear()
            self.csv_data = []
            self.csv_headers = []
            self.table.clear()
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.coord_count_label.setText("Ready to create points")
            self.status_text.clear()
            self.tab_widget.setCurrentIndex(0)

    def preview_points(self):
        points = self.get_coordinate_points()
        if not points:
            self.show_status_message(
                "No valid coordinates to preview", "warning")
            return
        preview_dialog = QDialog(self)
        preview_dialog.setWindowTitle("Point Preview")
        preview_dialog.setModal(True)
        preview_dialog.setMinimumSize(400, 200)
        layout = QVBoxLayout()
        info_label = QLabel(f"Ready to create {len(points)} points")
        info_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(info_label)
        table = QTableWidget()
        table.setMinimumHeight(120)
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(['X', 'Y'])
        display_count = min(20, len(points))
        table.setRowCount(display_count)
        for i in range(display_count):
            x, y = points[i][:2]
            table.setItem(i, 0, QTableWidgetItem(f"{x:.6f}"))
            table.setItem(i, 1, QTableWidgetItem(f"{y:.6f}"))
        layout.addWidget(table)
        if len(points) > display_count:
            more_label = QLabel(
                f"... and {len(points) - display_count} more points")
            layout.addWidget(more_label)
        button_layout = QHBoxLayout()
        close_btn = QPushButton("Close")
        create_btn = QPushButton("Create Points")
        button_layout.addWidget(close_btn)
        button_layout.addWidget(create_btn)
        layout.addLayout(button_layout)
        preview_dialog.setLayout(layout)
        close_btn.clicked.connect(preview_dialog.close)
        create_btn.clicked.connect(
            lambda: [preview_dialog.close(), self.create_points()])
        preview_dialog.exec()

    def get_coordinate_points(self):
        if self.tab_widget.currentIndex() == 0:
            if self.enable_batch.isChecked():
                points = self.parse_batch_coordinates()
            else:
                point = self.get_single_coordinate()
                points = [point] if point else []
        else:
            points = self.get_csv_coordinates()
        return points

    def parse_batch_coordinates(self):
        text = self.batch_text.toPlainText().strip()
        if not text:
            return []
        points = []
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        # Determine coordinate format from radio buttons
        is_utm = self.utm_radio.isChecked()
        is_dd = self.dd_radio.isChecked()
        is_dms = self.dms_radio.isChecked()

        # Setup transformation only for DD/DMS (geographic coordinates)
        transform = None
        if is_dd or is_dms:
            source_crs = QgsCoordinateReferenceSystem("EPSG:4326")
            target_crs = self.crs_selector.crs()
            if source_crs.isValid() and target_crs.isValid() and source_crs.authid() != target_crs.authid():
                transform = QgsCoordinateTransform(
                    source_crs, target_crs, QgsProject.instance())

        for line in lines:
            for sep in [',', ' ', '\t', ';']:
                parts = [p.strip() for p in line.split(sep) if p.strip()]
                if len(parts) >= 2:
                    try:
                        x = float(parts[0])
                        y = float(parts[1])

                        # Handle different coordinate formats
                        if is_utm:
                            # UTM coordinates - transform from UTM source CRS to target CRS
                            x, y = self.transform_utm_coordinates(x, y)
                        elif is_dms:
                            # DMS format - for batch, we expect decimal values, not DMS strings
                            if transform:
                                pt = transform.transform(QgsPointXY(x, y))
                                x, y = pt.x(), pt.y()
                        elif is_dd:
                            # Decimal Degrees - transform from WGS84 to target CRS
                            if transform:
                                pt = transform.transform(QgsPointXY(x, y))
                                x, y = pt.x(), pt.y()

                        points.append((x, y))
                        break
                    except (ValueError, TypeError) as e:
                        print(
                            f"Skipping batch line '{line}' due to error: {e}")
                        continue
        return points

    def get_single_coordinate(self):
        try:
            source_crs = None
            x, y = None, None
            if self.dd_radio.isChecked() or self.dms_radio.isChecked():
                source_crs = QgsCoordinateReferenceSystem("EPSG:4326")
                if self.dd_radio.isChecked():
                    x = float(self.x_input.text().strip()
                              ) if self.x_input.text() else None
                    y = float(self.y_input.text().strip()
                              ) if self.y_input.text() else None
                else:
                    x = self.dms_to_dd(self.x_deg.text(),
                                       self.x_min.text(), self.x_sec.text())
                    y = self.dms_to_dd(self.y_deg.text(),
                                       self.y_min.text(), self.y_sec.text())
            else:
                utm_x = float(self.utm_x_input.text().strip()
                              ) if self.utm_x_input.text() else None
                utm_y = float(self.utm_y_input.text().strip()
                              ) if self.utm_y_input.text() else None
                if utm_x is not None and utm_y is not None:
                    x, y = self.transform_utm_coordinates(utm_x, utm_y)
                else:
                    return None
            if x is not None and y is not None:
                if source_crs:
                    target_crs = self.crs_selector.crs()
                    if not target_crs.isValid():
                        raise ValueError("Invalid target CRS selected")
                    if source_crs.authid() != target_crs.authid():
                        transform = QgsCoordinateTransform(
                            source_crs, target_crs, QgsProject.instance())
                        source_point = QgsPointXY(x, y)
                        transformed_point = transform.transform(source_point)
                        return (transformed_point.x(), transformed_point.y())
                return (x, y)
        except (ValueError, TypeError) as e:
            self.show_status_message(f"Coordinate error: {e}", "error")
            return None

    def transform_utm_coordinates(self, utm_x, utm_y):
        """Transform UTM coordinates from source CRS to target CRS"""
        try:
            source_crs = self.utm_crs_selector.crs()
            if not source_crs.isValid():
                raise ValueError("Invalid source CRS selected")
            target_crs = self.crs_selector.crs()
            if not target_crs.isValid():
                raise ValueError("Invalid target CRS selected")
            if source_crs.authid() == target_crs.authid():
                return utm_x, utm_y
            transform = QgsCoordinateTransform(
                source_crs, target_crs, QgsProject.instance())
            source_point = QgsPointXY(utm_x, utm_y)
            transformed_point = transform.transform(source_point)
            return transformed_point.x(), transformed_point.y()
        except Exception as e:
            raise ValueError(f"Failed to transform coordinates: {str(e)}")

    def dms_to_dd(self, deg, min_, sec):
        try:
            deg_f = float(deg) if deg else 0
            min_f = float(min_) if min_ else 0
            sec_f = float(sec) if sec else 0
            if not -180 <= deg_f <= 180 or not 0 <= min_f < 60 or not 0 <= sec_f < 60:
                raise ValueError("Invalid DMS value")
            dd = deg_f + (min_f / 60.0) + (sec_f / 3600.0)
            if deg_f < 0:
                dd = deg_f - (min_f / 60.0) - (sec_f / 3600.0)
            return dd
        except (ValueError, TypeError):
            raise ValueError("Invalid DMS values")

    def get_csv_coordinates(self):
        csv_file = self.csv_path.text()
        if not csv_file or not os.path.exists(csv_file):
            self.show_status_message("No valid CSV file selected", "warning")
            return []
        x_field = self.x_field_combo.currentText()
        y_field = self.y_field_combo.currentText()
        if not x_field or not y_field:
            self.show_status_message(
                "Please select X and Y coordinate fields", "warning")
            return []
        if not self.csv_headers:
            self.show_status_message("CSV headers not loaded", "error")
            return []
        try:
            x_idx = self.csv_headers.index(x_field)
            y_idx = self.csv_headers.index(y_field)
        except ValueError:
            self.show_status_message(
                "Selected fields not found in CSV headers", "error")
            return []
        delimiter = "\t" if self.csv_delimiter_combo.currentText(
        ) == "\t" else self.csv_delimiter_combo.currentText()
        encoding = self.csv_encoding_combo.currentText()
        has_header = self.csv_has_header.isChecked()
        points = []
        failed_rows = []
        total_rows = 0
        try:
            with open(csv_file, 'r', encoding=encoding) as f:
                reader = csv.reader(f, delimiter=delimiter)
                if has_header:
                    next(reader)
                for row_num, row in enumerate(reader):
                    total_rows += 1
                    if len(row) <= max(x_idx, y_idx):
                        failed_rows.append(
                            f"Row {row_num + 1}: insufficient columns")
                        continue
                    x_val = row[x_idx] if x_idx < len(row) else ""
                    y_val = row[y_idx] if y_idx < len(row) else ""
                    if not x_val.strip() or not y_val.strip():
                        continue
                    try:
                        x = self.parse_coordinate_value(x_val)
                        y = self.parse_coordinate_value(y_val)
                        crs = self.crs_selector.crs()
                        if crs.isGeographic() and (x < -180 or x > 180 or y < -90 or y > 90):
                            failed_rows.append(
                                f"Row {row_num + 1}: coordinates out of geographic range")
                            continue
                        points.append((x, y, row))
                    except ValueError as e:
                        failed_rows.append(f"Row {row_num + 1}: {str(e)}")
                self.coord_count_label.setText(
                    f"Processed {total_rows} rows, found {len(points)} valid points")
                if failed_rows:
                    if len(failed_rows) < 10:
                        self.show_status_message(
                            "Failed to parse some rows:\n" + "\n".join(failed_rows[:5]) +
                            (f"\n... and {len(failed_rows) - 5} more" if len(
                                failed_rows) > 5 else ""),
                            "warning"
                        )
                    else:
                        self.show_status_message(
                            f"Failed to parse {len(failed_rows)} rows out of {total_rows}", "warning")
                if not points:
                    self.show_status_message(
                        "No valid coordinate pairs found in CSV data", "error")
                return points
        except Exception as e:
            self.show_status_message(
                f"Error processing CSV file: {str(e)}", "error")
            return []

    def parse_coordinate_value(self, value):
        if value is None or str(value).strip() == "":
            raise ValueError("Empty coordinate value")
        value = str(value).strip()
        if value.lower() in ['', 'null', 'none', 'n/a', '#n/a', 'nan']:
            raise ValueError("Invalid coordinate value")
        try:
            return float(value)
        except ValueError:
            pass
        dms_pat = r"(\d+)[°°]\s*(\d+)[\'′]\s*([\d.]+)[\"″]?"
        m = re.match(dms_pat, value)
        if m:
            deg, min_, sec = m.groups()
            return self.dms_to_dd(deg, min_, sec)
        parts = value.replace('°', ' ').replace(
            "'", ' ').replace('"', ' ').split()
        if len(parts) >= 3:
            try:
                return self.dms_to_dd(parts[0], parts[1], parts[2])
            except ValueError:
                pass
        cleaned = re.sub(r'[^\d.-]', '', value)
        if cleaned:
            try:
                return float(cleaned)
            except ValueError:
                pass
        raise ValueError(f"Could not parse coordinate: '{value}'")

    def get_or_create_layer(self):
        crs = self.crs_selector.crs()

        # Determine required fields based on current input mode
        required_fields = QgsFields()
        if self.csv_headers and self.tab_widget.currentIndex() == 1:
            for field in self.csv_headers:
                required_fields.append(QgsField(field, QVariant.String))
            layer_name = f"Points_CSV_{crs.authid().replace(':', '_')}"
        else:
            required_fields.append(QgsField("X", QVariant.Double))
            required_fields.append(QgsField("Y", QVariant.Double))
            layer_name = f"Points_Manual_{crs.authid().replace(':', '_')}"

        # Check for existing compatible layer
        for layer in QgsProject.instance().mapLayers().values():
            if (layer.name() == layer_name and
                    layer.type() == QtCompat.VectorLayer and
                    layer.crs() == crs):
                # Verify field structure matches
                existing_fields = layer.fields()
                if existing_fields.count() == required_fields.count():
                    fields_match = True
                    for i in range(required_fields.count()):
                        if (required_fields[i].name() != existing_fields[i].name() or
                                required_fields[i].type() != existing_fields[i].type()):
                            fields_match = False
                            break
                    if fields_match:
                        return layer

        # Create new layer with appropriate fields
        layer = QgsVectorLayer(
            f"Point?crs={crs.authid()}", layer_name, "memory")
        prov = layer.dataProvider()
        prov.addAttributes(required_fields)
        layer.updateFields()
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            return layer
        return None

    def create_points(self):
        try:
            layer = self.get_or_create_layer()
            if not layer:
                self.show_status_message(
                    "Failed to create layer—check CRS settings", "error")
                return
            points = self.get_coordinate_points()
            if not points:
                self.show_status_message(
                    "No valid coordinates found—check input format", "warning")
                return
            if len(points) > 100:
                self.progress_bar.show()
                self.progress_bar.setRange(0, len(points))
                self.progress_bar.setValue(0)
            features = []
            failed_count = 0
            error_details = []
            layer.startEditing()
            for i, point_data in enumerate(points):
                try:
                    feat = QgsFeature(layer.fields())
                    if len(point_data) == 2:
                        x, y = point_data
                        if abs(x) < 1e-10 and abs(y) < 1e-10:
                            error_details.append(
                                f"Point {i+1}: Both X and Y are zero")
                            failed_count += 1
                            continue
                        feat.setGeometry(
                            QgsGeometry.fromPointXY(QgsPointXY(x, y)))
                        feat.setAttribute("X", x)
                        feat.setAttribute("Y", y)
                    else:
                        if len(point_data) == 3:
                            x, y, row = point_data
                            feat.setGeometry(
                                QgsGeometry.fromPointXY(QgsPointXY(x, y)))
                            for j, val in enumerate(row):
                                if j < len(self.csv_headers) and j < len(layer.fields()):
                                    feat.setAttribute(self.csv_headers[j], val)
                        else:
                            error_details.append(
                                f"Point {i+1}: Invalid CSV point data")
                            failed_count += 1
                            continue
                    features.append(feat)
                    if len(points) > 100 and i % 50 == 0:
                        self.progress_bar.setValue(i)
                        QApplication.processEvents()
                except Exception as e:
                    error_details.append(f"Point {i+1}: {str(e)}")
                    failed_count += 1
            if features:
                success = layer.dataProvider().addFeatures(features)
                if success:
                    layer.commitChanges()
                    layer.updateExtents()

                    # Zoom to created points with proper CRS transformation
                    layer_extent = layer.extent()
                    canvas = self.iface.mapCanvas()

                    if not layer_extent.isNull() and not layer_extent.isEmpty():
                        layer_crs = layer.crs()
                        canvas_crs = canvas.mapSettings().destinationCrs()

                        # Transform extent if CRS differs
                        if layer_crs.authid() != canvas_crs.authid():
                            try:
                                transform = QgsCoordinateTransform(
                                    layer_crs,
                                    canvas_crs,
                                    QgsProject.instance()
                                )
                                transformed_extent = transform.transformBoundingBox(
                                    layer_extent)

                                # Add buffer for single points or small extents
                                if len(features) == 1 or transformed_extent.width() < 100 or transformed_extent.height() < 100:
                                    buffer = max(1000, transformed_extent.width(
                                    ) * 0.1, transformed_extent.height() * 0.1)
                                    transformed_extent.grow(buffer)

                                canvas.setExtent(transformed_extent)
                                canvas.refresh()
                            except Exception as transform_error:
                                print(f"Transform error: {transform_error}")
                                buffer = max(1000, layer_extent.width(
                                ) * 0.1, layer_extent.height() * 0.1)
                                layer_extent.grow(buffer)
                                canvas.setExtent(layer_extent)
                                canvas.refresh()
                        else:
                            # Same CRS, just add buffer for single points
                            if len(features) == 1 or layer_extent.width() < 100 or layer_extent.height() < 100:
                                buffer = max(1000, layer_extent.width(
                                ) * 0.1, layer_extent.height() * 0.1)
                                layer_extent.grow(buffer)
                            canvas.setExtent(layer_extent)
                            canvas.refresh()
                    else:
                        # Extent is null/empty - try to zoom to first point
                        if features:
                            first_geom = features[0].geometry()
                            if first_geom and not first_geom.isNull():
                                point = first_geom.asPoint()
                                buffer_size = 1000
                                extent = QgsRectangle(
                                    point.x() - buffer_size,
                                    point.y() - buffer_size,
                                    point.x() + buffer_size,
                                    point.y() + buffer_size
                                )

                                layer_crs = layer.crs()
                                canvas_crs = canvas.mapSettings().destinationCrs()
                                if layer_crs.authid() != canvas_crs.authid():
                                    try:
                                        transform = QgsCoordinateTransform(
                                            layer_crs,
                                            canvas_crs,
                                            QgsProject.instance()
                                        )
                                        extent = transform.transformBoundingBox(
                                            extent)
                                    except Exception:  # nosec B110
                                        pass

                                canvas.setExtent(extent)
                                canvas.refresh()

                    msg = f"Successfully created {len(features)} points"
                    if failed_count > 0:
                        msg += f" ({failed_count} failed)"
                        if len(error_details) <= 5:
                            QMessageBox.warning(
                                self, "Warnings", "\n".join(error_details[:5]))
                    self.show_status_message(msg, "success")
                    self.coord_count_label.setText(msg)
                else:
                    layer.rollBack()
                    self.show_status_message(
                        "Failed to add features to layer", "error")
            else:
                layer.rollBack()
                if error_details:
                    detail = "\n".join(error_details[:10]) + \
                        (f"\n... and {len(error_details)-10} more" if len(
                            error_details) > 10 else "")
                    QMessageBox.critical(self, "Failed", detail)
                self.show_status_message(
                    "No valid points could be created", "error")
        except Exception as e:
            self.show_status_message(f"Unexpected error: {str(e)}", "error")
        finally:
            self.progress_bar.hide()

    def closeEvent(self, event):
        temp_layers = []
        for layer in QgsProject.instance().mapLayers().values():
            if (layer.providerType() == "memory"
                    and layer.geometryType() == QgsWkbTypes.GeometryType.PointGeometry
                    and layer.name().startswith("Points_")):
                temp_layers.append(layer)
        if temp_layers:
            for temp_layer in temp_layers:
                reply = QtCompat.message_box_question(
                    self,
                    'Save Layer',
                    f'Do you want to save the layer "{temp_layer.name()}" permanently?',
                    QtCompat.Yes | QtCompat.No | QtCompat.Cancel,
                    QtCompat.No
                )
                if reply == QtCompat.Yes:
                    # Implement save_temp_layer() if you want export
                    pass
                elif reply == QtCompat.Cancel:
                    event.ignore()
                    return
        self.dialogClosed.emit()
        event.accept()


# Usage example (uncomment to run):
# dialog = PointInputDialog(iface)
# dialog.show()

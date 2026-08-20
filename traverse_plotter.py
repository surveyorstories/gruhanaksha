import math
import re
from qgis.PyQt.QtCore import Qt, pyqtSignal, QTimer, QVariant
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QMessageBox, QGroupBox,
    QWidget, QGridLayout, QCheckBox, QHeaderView
)
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsFields, QgsField, QgsCoordinateReferenceSystem, QgsMessageLog, Qgis
)
from qgis.gui import QgsMapToolEmitPoint
from qgis.utils import iface
from .qt_compat import QtCompat

# Conversion factors to Meters
UNIT_FACTORS = {
    "Meters": 1.0,
    "Feet": 0.3048,
    "Gunter's Links": 0.201168,
    "Metric Links": 0.2
}

def parse_angle(text):
    """
    Parses angles in decimal degrees or DMS format (e.g. 136 02 00, 136°02', 136.033).
    """
    text = text.strip()
    if not text:
        return 0.0
    # Extract all numbers
    parts = re.findall(r'[-+]?\d+(?:\.\d+)?', text)
    if not parts:
        raise ValueError(f"Invalid angle format: {text}")
    
    sign = -1.0 if text.startswith('-') else 1.0
    val = abs(float(parts[0]))
    if len(parts) >= 2:
        val += float(parts[1]) / 60.0
    if len(parts) >= 3:
        val += float(parts[2]) / 3600.0
    return sign * val

def parse_dd_mmss(text):
    """
    Parses survey angles in DD.MMSS or DD.MM format (e.g., 136.02 -> 136°02', 164.35 -> 164°35').
    """
    text = text.strip()
    if not text:
        return 0.0
    try:
        val = float(text)
    except ValueError:
        raise ValueError(f"Invalid numeric format for DD.MMSS: {text}")
    
    sign = -1.0 if val < 0 else 1.0
    val = abs(val)
    
    degrees = int(val)
    frac = val - degrees
    
    # Multiply by 100 to extract minutes and seconds
    mm_ss = round(frac * 100.0, 4)
    minutes = int(mm_ss)
    seconds = round((mm_ss - minutes) * 100.0, 4)
    
    return sign * (degrees + (minutes / 60.0) + (seconds / 3600.0))

class TraversePlotterDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.setWindowTitle("Traverse Plotter")
        self.setMinimumSize(500, 500)
        self.setWindowFlags(QtCompat.Window | QtCompat.WindowCloseButtonHint)
        self.setup_ui()
        self.previous_map_tool = None

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # 1. Starting Parameters Group
        start_group = QGroupBox("1. Starting Parameters")
        start_layout = QGridLayout(start_group)
        
        start_layout.addWidget(QLabel("Start X (Easting):"), 0, 0)
        self.txt_start_x = QLineEdit("0.0")
        start_layout.addWidget(self.txt_start_x, 0, 1)

        start_layout.addWidget(QLabel("Start Y (Northing):"), 1, 0)
        self.txt_start_y = QLineEdit("0.0")
        start_layout.addWidget(self.txt_start_y, 1, 1)

        self.btn_pick = QPushButton("Pick on Canvas")
        self.btn_pick.clicked.connect(self.pick_coordinate)
        start_layout.addWidget(self.btn_pick, 0, 2, 2, 1)

        start_layout.addWidget(QLabel("Initial Bearing (Deg from North):"), 2, 0)
        self.txt_init_bearing = QLineEdit("0.0")
        start_layout.addWidget(self.txt_init_bearing, 2, 1)

        layout.addWidget(start_group)

        # 2. Options Group
        opts_group = QGroupBox("2. Plotting Settings")
        opts_layout = QGridLayout(opts_group)

        opts_layout.addWidget(QLabel("Angle Input Mode:"), 0, 0)
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["Azimuth / Bearing", "Angle to Right (Clockwise)", "Deflection Angle"])
        self.cmb_mode.setToolTip(
            "Azimuth / Bearing: Absolute angle measured clockwise from North.\n"
            "Angle to Right: Relative angle measured clockwise from back-sight line.\n"
            "Deflection Angle: Relative angle turned left or right from extension of previous line."
        )
        opts_layout.addWidget(self.cmb_mode, 0, 1)

        opts_layout.addWidget(QLabel("Angle Format:"), 0, 2)
        self.cmb_angle_format = QComboBox()
        self.cmb_angle_format.addItems([
            "Decimal Degrees / Spaced DMS",
            "DD.MMSS / DD.MM (Surveyor DMS)"
        ])
        self.cmb_angle_format.setToolTip(
            "Decimal Degrees / Spaced DMS: Normal floats (e.g. 136.5) or space-separated values (e.g. 136 30).\n"
            "DD.MMSS / DD.MM: Surveyor format where decimal digits represent minutes and seconds (e.g. 136.02 represents 136°02')."
        )
        opts_layout.addWidget(self.cmb_angle_format, 0, 3)

        opts_layout.addWidget(QLabel("Distance Unit:"), 1, 0)
        self.cmb_unit = QComboBox()
        self.cmb_unit.addItems(["Gunter's Links", "Meters", "Feet", "Metric Links"])
        self.cmb_unit.setToolTip("Unit used for distances in table. Automatically converted to project coordinate system units.")
        opts_layout.addWidget(self.cmb_unit, 1, 1)

        self.chk_closed = QCheckBox("Draw as Closed Polygon")
        self.chk_closed.setChecked(True)
        self.chk_closed.setToolTip("Connects the last station to the first station to form a closed polygon.")
        opts_layout.addWidget(self.chk_closed, 2, 0)

        self.chk_adjust = QCheckBox("Apply Bowditch Adjustment")
        self.chk_adjust.setChecked(True)
        self.chk_adjust.setToolTip("Apply Compass Rule (Bowditch method) to distribute linear closure error proportionally.")
        opts_layout.addWidget(self.chk_adjust, 2, 1)

        layout.addWidget(opts_group)

        # 3. Table Group
        table_group = QGroupBox("3. Traverse Courses")
        table_layout = QVBoxLayout(table_group)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["From", "To", "Angle (DMS/DD)", "Distance"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.cellChanged.connect(self.on_cell_changed)
        table_layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("Add Row")
        self.btn_add.clicked.connect(self.add_row)
        btn_layout.addWidget(self.btn_add)

        self.btn_remove = QPushButton("Remove Row")
        self.btn_remove.clicked.connect(self.remove_row)
        btn_layout.addWidget(self.btn_remove)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self.clear_table)
        btn_layout.addWidget(self.btn_clear)

        table_layout.addLayout(btn_layout)
        layout.addWidget(table_group)

        # 4. Action Buttons
        actions_layout = QHBoxLayout()
        self.btn_plot = QPushButton("Plot Traverse")
        self.btn_plot.clicked.connect(self.plot_traverse)
        self.btn_plot.setStyleSheet("background-color: #2ca02c; color: white; font-weight: bold;")
        actions_layout.addWidget(self.btn_plot)

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.close)
        actions_layout.addWidget(self.btn_close)

        layout.addLayout(actions_layout)

        # Prepopulate with a few rows
        for _ in range(4):
            self.add_row()

    def add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        # Determine default station names
        from_letter = chr(65 + row) if row < 26 else f"A{row}"
        to_letter = chr(65 + row + 1) if row + 1 < 26 else f"A{row+1}"
        
        self.table.setItem(row, 0, QTableWidgetItem(from_letter))
        self.table.setItem(row, 1, QTableWidgetItem(to_letter))
        self.table.setItem(row, 2, QTableWidgetItem("0.0"))
        self.table.setItem(row, 3, QTableWidgetItem("0.0"))

    def remove_row(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)
        else:
            self.table.removeRow(self.table.rowCount() - 1)

    def clear_table(self):
        self.table.setRowCount(0)
        for _ in range(4):
            self.add_row()

    def pick_coordinate(self):
        canvas = iface.mapCanvas()
        self.previous_map_tool = canvas.mapTool()
        self.map_tool = QgsMapToolEmitPoint(canvas)
        self.map_tool.canvasClicked.connect(self.on_canvas_clicked)
        canvas.setMapTool(self.map_tool)
        iface.messageBar().pushMessage("Info", "Click on the map canvas to set start coordinate", level=Qgis.Info, duration=3)

    def on_canvas_clicked(self, point, button):
        self.txt_start_x.setText(f"{point.x():.3f}")
        self.txt_start_y.setText(f"{point.y():.3f}")
        canvas = iface.mapCanvas()
        # Delay restoring the tool to prevent the click from propagating to active editing tool
        QTimer.singleShot(100, lambda: canvas.setMapTool(self.previous_map_tool))

    def on_cell_changed(self, row, column):
        if column != 2:
            return
        
        item = self.table.item(row, column)
        if not item:
            return
            
        text = item.text().strip()
        if not text or "°" in text or "'" in text:
            return
            
        self.table.blockSignals(True)
        try:
            if self.cmb_angle_format.currentText() == "DD.MMSS / DD.MM (Surveyor DMS)":
                try:
                    val = float(text)
                    sign_str = "-" if val < 0 else ""
                    val = abs(val)
                    degrees = int(val)
                    frac = val - degrees
                    mm_ss = round(frac * 100.0, 4)
                    minutes = int(mm_ss)
                    seconds = round((mm_ss - minutes) * 100.0, 4)
                    
                    if seconds > 0:
                        formatted = f"{sign_str}{degrees}°{minutes:02d}'{seconds:02g}\""
                    else:
                        formatted = f"{sign_str}{degrees}°{minutes:02d}'"
                    item.setText(formatted)
                except ValueError:
                    pass
            else:
                try:
                    parts = re.findall(r'[-+]?\d+(?:\.\d+)?', text)
                    if parts and len(parts) >= 2:
                        sign_str = "-" if text.startswith('-') else ""
                        deg = abs(int(float(parts[0])))
                        min_val = int(float(parts[1]))
                        sec_val = float(parts[2]) if len(parts) >= 3 else 0.0
                        
                        if sec_val > 0:
                            formatted = f"{sign_str}{deg}°{min_val:02d}'{sec_val:02g}\""
                        else:
                            formatted = f"{sign_str}{deg}°{min_val:02d}'"
                        item.setText(formatted)
                except (ValueError, IndexError):
                    pass
        finally:
            self.table.blockSignals(False)

    def calculate_traverse(self):
        try:
            start_x = float(self.txt_start_x.text())
            start_y = float(self.txt_start_y.text())
            init_bearing = float(self.txt_init_bearing.text())
        except ValueError:
            QMessageBox.critical(self, "Error", "Invalid starting coordinates or bearing.")
            return None

        mode = self.cmb_mode.currentText()
        unit = self.cmb_unit.currentText()
        factor = UNIT_FACTORS.get(unit, 1.0)

        # We will compute coords of each station
        coords = [QgsPointXY(start_x, start_y)]
        station_names = []
        
        current_bearing = init_bearing
        row_count = self.table.rowCount()
        if row_count == 0:
            return None

        # Add the first station name
        first_from = self.table.item(0, 0).text().strip()
        station_names.append(first_from if first_from else "A")

        for i in range(row_count):
            to_item = self.table.item(i, 1)
            angle_item = self.table.item(i, 2)
            dist_item = self.table.item(i, 3)

            to_name = to_item.text().strip() if to_item else f"Station {i+2}"
            station_names.append(to_name)

            try:
                angle_text = angle_item.text().strip() if angle_item else "0.0"
                if "°" in angle_text or "'" in angle_text:
                    angle_val = parse_angle(angle_text)
                elif self.cmb_angle_format.currentText() == "DD.MMSS / DD.MM (Surveyor DMS)":
                    angle_val = parse_dd_mmss(angle_text)
                else:
                    angle_val = parse_angle(angle_text)
                distance_val = float(dist_item.text()) if dist_item else 0.0
            except ValueError as e:
                QMessageBox.critical(self, "Error", f"Error on row {i+1}: {str(e)}")
                return None

            # Calculate direction
            if mode == "Azimuth / Bearing":
                current_bearing = angle_val
            elif mode == "Angle to Right (Clockwise)":
                if i == 0:
                    current_bearing = init_bearing
                else:
                    current_bearing = (current_bearing + 180.0 + angle_val) % 360.0
            elif mode == "Deflection Angle":
                if i == 0:
                    current_bearing = init_bearing + angle_val
                else:
                    current_bearing = (current_bearing + angle_val) % 360.0

            # Convert bearing to radians (North is 0, clockwise)
            rad = math.radians(current_bearing)
            dx = (distance_val * factor) * math.sin(rad)
            dy = (distance_val * factor) * math.cos(rad)

            prev_pt = coords[-1]
            new_pt = QgsPointXY(prev_pt.x() + dx, prev_pt.y() + dy)
            coords.append(new_pt)

        # Apply Bowditch adjustment if closed and requested
        is_closed = self.chk_closed.isChecked()
        apply_adjust = self.chk_adjust.isChecked()

        # If it closed back to first station name
        if is_closed and apply_adjust and len(coords) > 2:
            start_pt = coords[0]
            end_pt = coords[-1]
            dx_err = end_pt.x() - start_pt.x()
            dy_err = end_pt.y() - start_pt.y()

            # Calculate total length
            lengths = []
            for i in range(row_count):
                dist_item = self.table.item(i, 3)
                try:
                    lengths.append(float(dist_item.text()) * factor)
                except ValueError:
                    lengths.append(0.0)
            
            total_len = sum(lengths)
            if total_len > 0:
                cum_len = 0.0
                adjusted_coords = [coords[0]]
                for i in range(1, len(coords)):
                    cum_len += lengths[i-1]
                    ratio = cum_len / total_len
                    adj_x = coords[i].x() - (dx_err * ratio)
                    adj_y = coords[i].y() - (dy_err * ratio)
                    adjusted_coords.append(QgsPointXY(adj_x, adj_y))
                coords = adjusted_coords

        return coords, station_names

    def plot_traverse(self):
        res = self.calculate_traverse()
        if not res:
            return
        
        coords, station_names = res
        is_closed = self.chk_closed.isChecked()

        # Determine geometry type
        geom_type = "Polygon" if is_closed else "LineString"
        crs = QgsProject.instance().crs()
        auth_id = crs.authid() if crs.isValid() else "EPSG:4326"

        layer = QgsVectorLayer(f"{geom_type}?crs={auth_id}", "Survey Traverse", "memory")
        provider = layer.dataProvider()

        # Add fields
        fields = QgsFields()
        fields.append(QgsField("name", QVariant.String))
        provider.addAttributes(fields)
        layer.updateFields()

        # Create geometry
        if is_closed:
            # For a polygon, ensure it is closed and create QgsGeometry
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            geometry = QgsGeometry.fromPolygonXY([coords])
        else:
            geometry = QgsGeometry.fromPolylineXY(coords)

        feat = QgsFeature(layer.fields())
        feat.setGeometry(geometry)
        feat.setAttribute("name", "Traverse Plot")
        provider.addFeatures([feat])

        # Also create a point layer for stations
        point_layer = QgsVectorLayer(f"Point?crs={auth_id}", "Traverse Stations", "memory")
        pt_provider = point_layer.dataProvider()
        pt_provider.addAttributes(fields)
        point_layer.updateFields()

        pt_features = []
        for i, pt in enumerate(coords[:-1] if is_closed else coords):
            # Avoid repeating first point if closed
            pt_feat = QgsFeature(point_layer.fields())
            pt_feat.setGeometry(QgsGeometry.fromPointXY(pt))
            pt_name = station_names[i] if i < len(station_names) else f"ST{i}"
            pt_feat.setAttribute("name", pt_name)
            pt_features.append(pt_feat)
        
        pt_provider.addFeatures(pt_features)

        # Add layers to legend
        QgsProject.instance().addMapLayer(layer)
        QgsProject.instance().addMapLayer(point_layer)
        
        iface.mapCanvas().refresh()
        QMessageBox.information(self, "Success", "Traverse successfully plotted to map!")
        self.accept()

import math
from qgis.PyQt.QtCore import QTimer, Qt, QVariant
from qgis.PyQt.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                 QPushButton, QDoubleSpinBox, QComboBox,
                                 QTabWidget, QMessageBox, QFileDialog, QDialog,
                                 QDialogButtonBox)
from qgis.PyQt.QtGui import QColor
from qgis.gui import QgsRubberBand, QgsVertexMarker, QgsMapTool
from qgis.core import (QgsWkbTypes, QgsPointXY, QgsGeometry,
                       QgsVectorLayer, QgsField, QgsFeature, QgsProject,
                       QgsMarkerSymbol, QgsRendererCategory, QgsCategorizedSymbolRenderer,
                       QgsVectorFileWriter, QgsRectangle, QgsSnappingConfig,
                       QgsTolerance, QgsPointLocator, QgsMapLayer)
from qgis.utils import iface
from .addon_functions import TOOL_WINDOW_FLAGS, STAY_ON_TOP_FLAG

# Qt5/Qt6 Compatibility Helper


class QtCompat:
    """Helper class for Qt5/Qt6 compatibility"""

    @staticmethod
    def get_pen_style(style_name):
        """Get pen style compatible with both Qt5 and Qt6"""
        try:
            # Qt6 style
            return getattr(Qt.PenStyle, style_name)
        except AttributeError:
            # Qt5 style
            return getattr(Qt, style_name)

    @staticmethod
    def get_cursor_shape(shape_name):
        """Get cursor shape compatible with both Qt5 and Qt6"""
        try:
            # Qt6 style
            return getattr(Qt.CursorShape, shape_name)
        except AttributeError:
            # Qt5 style
            return getattr(Qt, shape_name)

    @staticmethod
    def get_key(key_name):
        """Get key constant compatible with both Qt5 and Qt6"""
        try:
            # Qt6 style
            return getattr(Qt.Key, key_name)
        except AttributeError:
            # Qt5 style
            return getattr(Qt, key_name)

    @staticmethod
    def get_mouse_button(button_name):
        """Get mouse button constant compatible with both Qt5 and Qt6"""
        try:
            # Qt6 style
            return getattr(Qt.MouseButton, button_name)
        except AttributeError:
            # Qt5 style
            return getattr(Qt, button_name)

    @staticmethod
    def get_alignment(alignment_name):
        """Get alignment constant compatible with both Qt5 and Qt6"""
        try:
            # Qt6 style
            return getattr(Qt.AlignmentFlag, alignment_name)
        except AttributeError:
            # Qt5 style
            return getattr(Qt, alignment_name)


# Constants
UNIT_CONVERSIONS = {
    "Meters": {"factor": 1.0, "abbrev": "m"},
    "Metric Links": {"factor": 0.2, "abbrev": "ml"},
    "Gunter's Links": {"factor": 0.201168, "abbrev": "links"},
    "Feet": {"factor": 0.3048, "abbrev": "ft"},
    "Yards": {"factor": 0.9144, "abbrev": "yd"}
}

POINT_CATEGORIES = [
    {'name': 'Cut Point', 'color': 'orange', 'size': 2},
    {'name': "Offset Point", 'color': 'blue', 'size': 2},
    {'name': "Bisect Point", 'color': '#F736F6', 'size': 2},
    {'name': "Extended Point", 'color': 'purple', 'size': 2},

]

# Utility Classes


class UnitConverter:
    @staticmethod
    def to_meters(value, unit): return value * \
        UNIT_CONVERSIONS.get(unit, {"factor": 1.0})["factor"]

    @staticmethod
    def from_meters(value, unit): return value / \
        UNIT_CONVERSIONS.get(unit, {"factor": 1.0})["factor"]

    @staticmethod
    def get_abbreviation(unit): return UNIT_CONVERSIONS.get(
        unit, {"abbrev": "m"})["abbrev"]


class GeometryHelper:
    @staticmethod
    def get_line_endpoints(geometry):
        try:
            points = geometry.asMultiPolyline(
            )[0] if geometry.isMultipart() else geometry.asPolyline()
            return QgsPointXY(points[0]), QgsPointXY(points[-1]) if points else (None, None)
        except Exception:
            return None, None

    @staticmethod
    def calculate_distance(point1, point2):
        dx, dy = point2.x() - point1.x(), point2.y() - point1.y()
        return math.sqrt(dx**2 + dy**2)

    @staticmethod
    def calculate_triangle_apex(start_point, end_point, start_length, end_length, orientation):
        try:
            dx, dy = end_point.x() - start_point.x(), end_point.y() - start_point.y()
            base_length = math.sqrt(dx**2 + dy**2)
            if base_length == 0 or not (start_length + end_length > base_length and start_length + base_length > end_length and end_length + base_length > start_length):
                return None
            ux, uy = dx / base_length, dy / base_length
            perp_ux, perp_uy = (-uy,
                                ux) if orientation == "Right" else (uy, -ux)
            angle_start = math.acos(
                (start_length**2 + base_length**2 - end_length**2) / (2 * start_length * base_length))
            apex_x = start_point.x() + start_length * (ux * math.cos(angle_start) -
                                                       perp_ux * math.sin(angle_start))
            apex_y = start_point.y() + start_length * (uy * math.cos(angle_start) -
                                                       perp_uy * math.sin(angle_start))
            return QgsPointXY(apex_x, apex_y)
        except (ValueError, ZeroDivisionError):
            return None


class LayerManager:
    @staticmethod
    def save_temp_layer(parent, layer):
        if layer.providerType() != "memory":
            return True
        file_path, _ = QFileDialog.getSaveFileName(parent, f"Save {layer.name()}", layer.name(
        ), "ESRI Shapefile (*.shp);;GeoJSON (*.geojson);;GPKG (*.gpkg)")
        if not file_path:
            return False
        format_map = {".shp": "ESRI Shapefile",
                      ".geojson": "GeoJSON", ".gpkg": "GPKG"}
        format_name = next(
            (fmt for ext, fmt in format_map.items() if file_path.endswith(ext)), None)
        if not format_name:
            QMessageBox.critical(parent, "Error", "Unsupported file format.")
            return False
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = format_name
        options.fileEncoding = "UTF-8"
        error = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer, file_path, QgsProject.instance().transformContext(), options)
        if error[0] != QgsVectorFileWriter.WriterError.NoError:
            QMessageBox.critical(parent, "Save Error",
                                 f"Error saving layer. Error code: {error[0]}")
            return False
        QMessageBox.information(parent, "Save Successful",
                                f"Layer saved successfully at {file_path}!")
        new_layer = QgsVectorLayer(file_path, layer.name(), "ogr")
        if new_layer.isValid():
            new_layer.setRenderer(layer.renderer().clone())
            QgsProject.instance().addMapLayer(new_layer)
            QgsProject.instance().removeMapLayer(layer.id())
            return True
        QMessageBox.warning(
            parent, "Warning", "Failed to reload the saved layer into the project.")
        return False

    @staticmethod
    def apply_categorized_symbology(layer, categories_info):
        categories = [QgsRendererCategory(info['name'], QgsMarkerSymbol.createSimple({'name': 'circle', 'color': info['color'], 'size': str(
            info['size']), 'outline_color': '0,0,0,255', 'outline_width': '0.2'}), info['name']) for info in categories_info]
        layer.setRenderer(QgsCategorizedSymbolRenderer('Type', categories))

    @staticmethod
    def get_or_create_layer(layer_name, geometry_type, crs, fields):
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() == layer_name and lyr.geometryType() == geometry_type:
                return lyr
        geom_type_str = "LineString" if geometry_type == QgsWkbTypes.LineGeometry else "Point"
        layer = QgsVectorLayer(
            f"{geom_type_str}?crs={crs.toWkt()}", layer_name, "memory")
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()
        QgsProject.instance().addMapLayer(layer)
        layer.updateExtents()
        return layer

    @staticmethod
    def update_layer_extent(layer):
        provider = layer.dataProvider()
        if provider:
            provider.updateExtents()
        layer.updateExtents()
        layer.reload()
        layer.triggerRepaint()
        iface.mapCanvas().refresh()


class MarkerFactory:
    @staticmethod
    def create_vertex_marker(canvas, point, color, fill_color=None, size=8):
        marker = QgsVertexMarker(canvas)
        marker.setCenter(point)
        marker.setColor(color)
        if fill_color:
            marker.setFillColor(fill_color)
        marker.setIconSize(size)
        marker.setIconType(QgsVertexMarker.ICON_CIRCLE)
        marker.setPenWidth(2)
        return marker

    @staticmethod
    def create_snap_marker(canvas):
        marker = QgsVertexMarker(canvas)
        marker.setIconType(QgsVertexMarker.ICON_CROSS)
        marker.setColor(QColor(255, 0, 255))
        marker.setPenWidth(3)
        marker.setIconSize(12)
        marker.hide()
        return marker

# Line Endpoint Manager


class LineEndpointManager:
    def __init__(self):
        self.map_canvas = iface.mapCanvas()
        self.current_layer = None
        self.is_active = False
        self.start_point_marker = None
        self.end_point_marker = None
        self.manual_mode = False  # Flag to indicate manual segment display

    def activate(self):
        if self.is_active:
            return
        self.is_active = True
        # Only connect to layer changes if not in manual mode
        if not self.manual_mode:
            iface.layerTreeView().currentLayerChanged.connect(self.on_layer_changed)
            current_layer = iface.activeLayer()
            if current_layer:
                self.on_layer_changed(current_layer)

    def deactivate(self):
        if not self.is_active:
            return
        self.is_active = False
        self.manual_mode = False
        try:
            iface.layerTreeView().currentLayerChanged.disconnect(self.on_layer_changed)
        except (TypeError, AttributeError):
            pass
        if self.current_layer:
            try:
                self.current_layer.selectionChanged.disconnect(
                    self.update_display)
            except (TypeError, AttributeError):
                pass
        self.clear_display()
        self.current_layer = None

    def on_layer_changed(self, layer):
        if not self.is_active or self.manual_mode:
            return

        # Check if layer is a vector layer and is a line layer
        if not layer or layer.type() != QgsMapLayer.VectorLayer:
            self.current_layer = None
            self.clear_display()
            return

        if self.current_layer:
            try:
                self.current_layer.selectionChanged.disconnect(
                    self.update_display)
            except (TypeError, AttributeError):
                pass

        self.current_layer = layer
        self.clear_display()

        if layer.wkbType() in [QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString]:
            layer.selectionChanged.connect(self.update_display)
            self.update_display()
        else:
            self.current_layer = None

    def update_display(self):
        """Update endpoint markers based on selected line features"""
        if not self.is_active or self.manual_mode:
            return
        self.clear_display()
        if not self.current_layer or self.current_layer.wkbType() not in [QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString]:
            return
        selected_features = list(self.current_layer.selectedFeatures())
        if len(selected_features) != 1:
            return
        geom = selected_features[0].geometry()
        if geom.isNull():
            return
        start_point, end_point = GeometryHelper.get_line_endpoints(geom)
        if start_point and end_point:
            self.start_point_marker = MarkerFactory.create_vertex_marker(
                self.map_canvas, start_point, QColor(0, 0, 0), QColor(0, 255, 0, 200), 11)
            self.start_point_marker.setPenWidth(1)
            self.start_point_marker.show()  # Explicitly show marker

            self.end_point_marker = MarkerFactory.create_vertex_marker(
                self.map_canvas, end_point, QColor(0, 0, 0), QColor(255, 0, 0, 200), 11)
            self.end_point_marker.setPenWidth(1)
            self.end_point_marker.show()  # Explicitly show marker

            self.map_canvas.refresh()

    def clear_display(self):
        """Clear endpoint markers from canvas"""
        if self.start_point_marker:
            try:
                self.start_point_marker.hide()
                self.map_canvas.scene().removeItem(self.start_point_marker)
            except:
                pass
            self.start_point_marker = None
        if self.end_point_marker:
            try:
                self.end_point_marker.hide()
                self.map_canvas.scene().removeItem(self.end_point_marker)
            except:
                pass
            self.end_point_marker = None

    def display_segment_endpoints(self, start_point, end_point):
        """Display markers at segment endpoints - MANUAL MODE"""
        # Enter manual mode to prevent automatic updates from clearing these
        self.manual_mode = True

        # Disconnect from layer changes temporarily
        try:
            iface.layerTreeView().currentLayerChanged.disconnect(self.on_layer_changed)
        except (TypeError, AttributeError):
            pass
        if self.current_layer:
            try:
                self.current_layer.selectionChanged.disconnect(
                    self.update_display)
            except (TypeError, AttributeError):
                pass

        # Clear old markers
        self.clear_display()

        # Create new markers
        if start_point and end_point:
            self.start_point_marker = MarkerFactory.create_vertex_marker(
                self.map_canvas, start_point, QColor(0, 0, 0), QColor(0, 255, 0, 200), 11)
            self.start_point_marker.setPenWidth(1)
            self.start_point_marker.show()

            self.end_point_marker = MarkerFactory.create_vertex_marker(
                self.map_canvas, end_point, QColor(0, 0, 0), QColor(255, 0, 0, 200), 11)
            self.end_point_marker.setPenWidth(1)
            self.end_point_marker.show()

            # Force markers to stay on top
            self.map_canvas.scene().update()

    def cleanup(self):
        self.deactivate()
        self.map_canvas.refresh()

# Triangle Point Tool


class TrianglePointTool(QgsMapTool):
    def __init__(self, canvas, triangle_widget):
        super().__init__(canvas)
        self.canvas = canvas
        self.triangle_widget = triangle_widget
        self.first_point = None
        self.markers = []
        self.use_fixed_length = False
        self.is_selecting = False
        self.base_line = QgsRubberBand(canvas, QgsWkbTypes.LineGeometry)
        self.base_line.setColor(QColor(0, 0, 255, 150))
        self.base_line.setWidth(2)
        self.temp_line = QgsRubberBand(canvas, QgsWkbTypes.LineGeometry)
        self.temp_line.setColor(QColor(0, 0, 255, 100))
        self.temp_line.setWidth(1)

        # Qt5/Qt6 compatible pen style and cursor
        self.temp_line.setLineStyle(QtCompat.get_pen_style('DashLine'))
        self.setCursor(QtCompat.get_cursor_shape('CrossCursor'))

        self.snapping_utils = canvas.snappingUtils()
        self.snap_marker = MarkerFactory.create_snap_marker(canvas)

    def activate(self):
        super().activate()
        self.is_selecting = True
        self.canvas.setCursor(QtCompat.get_cursor_shape('CrossCursor'))

    def deactivate(self):
        had_first_point = self.first_point is not None
        self.snap_marker.hide()
        self.temp_line.reset()
        if not had_first_point or self.is_selecting:
            self.is_selecting = False
            for marker in self.markers:
                self.canvas.scene().removeItem(marker)
            self.markers = []
            self.base_line.reset()
            self.first_point = None
            self.use_fixed_length = False
            self.triangle_widget.select_points_button.setEnabled(True)
            self.triangle_widget.select_points_button.setText("Select Points")
            self.triangle_widget.status_label.setText(
                "Click 'Select Points' to start")
        super().deactivate()

    def keyPressEvent(self, event):
        if event.key() == QtCompat.get_key('Key_L') and self.first_point is not None:
            self.use_fixed_length = True
            self.show_length_dialog()
        elif event.key() == QtCompat.get_key('Key_Escape'):
            self.clear()
            self.triangle_widget.status_label.setText(
                "Operation cancelled. Click 'Select Points' to start.")
            self.triangle_widget.clear_points()
        else:
            super().keyPressEvent(event)

    def show_length_dialog(self):
        dialog = QDialog(self.triangle_widget)
        dialog.setWindowTitle("Enter Base Line Length")
        dialog.setModal(True)
        layout = QVBoxLayout()
        length_layout = QHBoxLayout()
        length_layout.addWidget(QLabel("Length:"))
        length_input = QDoubleSpinBox()
        length_input.setDecimals(3)
        length_input.setRange(0.001, 1000000)
        length_input.setValue(self.triangle_widget.fixed_base_length)
        length_input.setMinimumWidth(150)
        length_layout.addWidget(length_input)
        layout.addLayout(length_layout)
        unit_layout = QHBoxLayout()
        unit_layout.addWidget(QLabel("Unit:"))
        unit_combo = QComboBox()
        unit_combo.addItems(list(UNIT_CONVERSIONS.keys()))
        unit_combo.setCurrentText(
            self.triangle_widget.unit_combo.currentText())
        unit_combo.setMinimumWidth(150)
        unit_layout.addWidget(unit_combo)
        layout.addLayout(unit_layout)
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        dialog.setLayout(layout)
        length_input.setFocus()
        length_input.selectAll()
        if dialog.exec() == QDialog.Accepted:
            length = length_input.value()
            unit = unit_combo.currentText()
            self.triangle_widget.fixed_base_length = length
            self.triangle_widget.unit_combo.setCurrentText(unit)
            unit_abbrev = UnitConverter.get_abbreviation(unit)
            self.triangle_widget.status_label.setText(
                f"Length set to {length:.3f} {unit_abbrev}. Click to set direction.")
        else:
            self.use_fixed_length = False

    def canvasMoveEvent(self, event):
        if not self.is_selecting:
            return
        match = self.snapping_utils.snapToMap(event.pos())
        current_point = match.point() if match.isValid(
        ) else self.toMapCoordinates(event.pos())
        if match.isValid():
            self.snap_marker.setCenter(current_point)
            self.snap_marker.show()
        else:
            self.snap_marker.hide()
        if self.first_point is not None:
            self.temp_line.reset()
            self.temp_line.addPoint(self.first_point, False)
            if self.use_fixed_length:
                distance = GeometryHelper.calculate_distance(
                    self.first_point, current_point)
                if distance > 0:
                    base_length = UnitConverter.to_meters(
                        self.triangle_widget.fixed_base_length, self.triangle_widget.unit_combo.currentText())
                    dx = current_point.x() - self.first_point.x()
                    dy = current_point.y() - self.first_point.y()
                    unit_dx, unit_dy = dx / distance, dy / distance
                    preview_end = QgsPointXY(self.first_point.x(
                    ) + unit_dx * base_length, self.first_point.y() + unit_dy * base_length)
                    self.temp_line.addPoint(preview_end, True)
            else:
                self.temp_line.addPoint(current_point, True)

    def canvasPressEvent(self, event):
        if not self.is_selecting:
            return

        if event.button() == QtCompat.get_mouse_button('RightButton'):
            # Only reset if first point exists
            if self.first_point is not None:
                # Reset but keep tool active in both cases
                self.clear()
                self.is_selecting = True
                self.triangle_widget.status_label.setText(
                    "Click first point on canvas")
            return

        match = self.snapping_utils.snapToMap(event.pos())
        point = match.point() if match.isValid() else self.toMapCoordinates(event.pos())
        if self.first_point is None:
            self.first_point = point
            marker = MarkerFactory.create_vertex_marker(
                self.canvas, point, QColor(0, 255, 0), QColor(0, 255, 0, 200))
            self.markers.append(marker)
            self.triangle_widget.status_label.setText(
                "Press 'L' for fixed length or click second point (Right-click to reset)")
        else:
            if self.use_fixed_length:
                base_length = UnitConverter.to_meters(
                    self.triangle_widget.fixed_base_length, self.triangle_widget.unit_combo.currentText())
                if base_length <= 0:
                    QMessageBox.warning(
                        self.triangle_widget, "Invalid Length", "Base line length must be greater than 0.")
                    return
                distance = GeometryHelper.calculate_distance(
                    self.first_point, point)
                if distance == 0:
                    QMessageBox.warning(self.triangle_widget, "Invalid Direction",
                                        "Second point must be different from first point.")
                    return
                dx = point.x() - self.first_point.x()
                dy = point.y() - self.first_point.y()
                unit_dx, unit_dy = dx / distance, dy / distance
                second_point = QgsPointXY(self.first_point.x(
                ) + unit_dx * base_length, self.first_point.y() + unit_dy * base_length)
            else:
                base_length = GeometryHelper.calculate_distance(
                    self.first_point, point)
                if base_length == 0:
                    QMessageBox.warning(self.triangle_widget, "Invalid Point",
                                        "Second point must be different from first point.")
                    return
                second_point = point
                current_unit = self.triangle_widget.unit_combo.currentText()
                self.triangle_widget.fixed_base_length = UnitConverter.from_meters(
                    base_length, current_unit)
            marker = MarkerFactory.create_vertex_marker(
                self.canvas, second_point, QColor(255, 0, 0), QColor(255, 0, 0, 200))
            self.markers.append(marker)
            self.base_line.reset()
            self.base_line.addPoint(self.first_point, False)
            self.base_line.addPoint(second_point, True)
            self.temp_line.reset()
            actual_length = GeometryHelper.calculate_distance(
                self.first_point, second_point)
            current_unit = self.triangle_widget.unit_combo.currentText()
            display_length = UnitConverter.from_meters(
                actual_length, current_unit)
            unit_abbrev = UnitConverter.get_abbreviation(current_unit)
            self.use_fixed_length = False
            self.is_selecting = False
            self.triangle_widget.set_points(self.first_point, second_point)
            self.triangle_widget.status_label.setText(
                f"Base line set ({display_length:.3f} {unit_abbrev}). Ready to draw triangle.")
            self.triangle_widget.select_points_button.setEnabled(True)
            self.triangle_widget.select_points_button.setText("Select Points")
            self.snap_marker.hide()
            iface.mapCanvas().unsetMapTool(self)

    def clear(self):
        self.first_point = None
        self.use_fixed_length = False
        self.is_selecting = False
        for marker in self.markers:
            self.canvas.scene().removeItem(marker)
        self.markers = []
        self.base_line.reset()
        self.temp_line.reset()
        self.snap_marker.hide()
        self.canvas.refresh()

# Triangle Widget


class TriangleWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220)
        self.start_point = None
        self.end_point = None
        self.fixed_base_length = 10.0
        self.lines_drawn = False
        self.point_tool = TrianglePointTool(iface.mapCanvas(), self)
        self.triangle_rubber_band = QgsRubberBand(
            iface.mapCanvas(), QgsWkbTypes.LineGeometry)
        self.triangle_rubber_band.setColor(QColor(255, 0, 0, 150))
        self.triangle_rubber_band.setWidth(3)
        self.preview_timer = QTimer()
        self.preview_timer.timeout.connect(self.update_triangle_preview)
        self.preview_timer.setSingleShot(True)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.status_label = QLabel("Click 'Select Points' to start")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "QLabel { color: #F736F6; font-weight: bold; padding: 5px; }")
        self.status_label.setMinimumHeight(40)
        self.status_label.setAlignment(QtCompat.get_alignment('AlignTop'))
        layout.addWidget(self.status_label)
        button_layout = QHBoxLayout()
        self.select_points_button = QPushButton("Select Points")
        self.select_points_button.clicked.connect(self.start_point_selection)
        button_layout.addWidget(self.select_points_button)
        self.clear_points_button = QPushButton("Clear Points")
        self.clear_points_button.clicked.connect(self.clear_points)
        self.clear_points_button.setEnabled(False)
        button_layout.addWidget(self.clear_points_button)
        layout.addLayout(button_layout)
        layout.addWidget(QLabel("Units:"))
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(list(UNIT_CONVERSIONS.keys()))
        self.unit_combo.currentTextChanged.connect(
            self.schedule_preview_update)
        layout.addWidget(self.unit_combo)
        layout.addWidget(QLabel("🟢 Start Side Length:"))
        self.start_length_input = QDoubleSpinBox()
        self.start_length_input.setDecimals(3)
        self.start_length_input.setRange(0, 1000000)
        self.start_length_input.valueChanged.connect(
            self.schedule_preview_update)
        layout.addWidget(self.start_length_input)
        layout.addWidget(QLabel("🔴 End Side Length:"))
        self.end_length_input = QDoubleSpinBox()
        self.end_length_input.setDecimals(3)
        self.end_length_input.setRange(0, 1000000)
        self.end_length_input.valueChanged.connect(
            self.schedule_preview_update)
        layout.addWidget(self.end_length_input)
        layout.addWidget(QLabel("Orientation:"))
        self.orientation_combo = QComboBox()
        self.orientation_combo.addItems(["Left", "Right"])
        self.orientation_combo.currentTextChanged.connect(
            self.schedule_preview_update)
        layout.addWidget(self.orientation_combo)
        self.draw_button = QPushButton("Draw Triangle")
        self.draw_button.clicked.connect(self.draw_triangle)
        self.draw_button.setEnabled(False)
        layout.addWidget(self.draw_button)
        layout.setAlignment(QtCompat.get_alignment('AlignTop'))
        self.setLayout(layout)

    def start_point_selection(self):
        self.clear_points()
        self.status_label.setText("Click first point on canvas")
        iface.mapCanvas().setMapTool(self.point_tool)
        self.select_points_button.setEnabled(False)
        self.select_points_button.setText("Selecting...")
        self.activateWindow()
        self.raise_()

    def set_points(self, start_point, end_point):
        self.start_point = start_point
        self.end_point = end_point
        self.draw_button.setEnabled(True)
        self.clear_points_button.setEnabled(True)
        self.select_points_button.setEnabled(True)
        self.select_points_button.setText("Select Points")
        self.schedule_preview_update()
        self.activateWindow()
        self.raise_()

    def clear_points(self):
        self.start_point = None
        self.end_point = None
        self.point_tool.clear()
        self.triangle_rubber_band.reset()
        self.draw_button.setEnabled(False)
        self.clear_points_button.setEnabled(False)
        self.select_points_button.setEnabled(True)
        self.select_points_button.setText("Select Points")
        self.status_label.setText("Click 'Select Points' to start")
        if iface.mapCanvas().mapTool() == self.point_tool:
            iface.mapCanvas().unsetMapTool(self.point_tool)
        iface.mapCanvas().refresh()

    def deactivate(self):
        if hasattr(self, 'point_tool') and not self.point_tool.is_selecting:
            self.select_points_button.setEnabled(True)
            self.select_points_button.setText("Select Points")
        if iface.mapCanvas().mapTool() == self.point_tool and self.start_point is None and self.end_point is None:
            iface.mapCanvas().unsetMapTool(self.point_tool)

    def schedule_preview_update(self):
        if self.start_point is None or self.end_point is None:
            return
        self.preview_timer.stop()
        self.preview_timer.start(200)

    def update_triangle_preview(self):
        self.triangle_rubber_band.reset()
        if self.start_point is None or self.end_point is None:
            return
        start_length = UnitConverter.to_meters(
            self.start_length_input.value(), self.unit_combo.currentText())
        end_length = UnitConverter.to_meters(
            self.end_length_input.value(), self.unit_combo.currentText())
        if start_length <= 0 or end_length <= 0:
            return
        apex_point = GeometryHelper.calculate_triangle_apex(
            self.start_point, self.end_point, start_length, end_length, self.orientation_combo.currentText())
        if apex_point:
            self.triangle_rubber_band.addPoint(self.start_point, False)
            self.triangle_rubber_band.addPoint(apex_point, False)
            self.triangle_rubber_band.addPoint(self.end_point, False)
            self.triangle_rubber_band.addPoint(self.start_point, True)

    def draw_triangle(self):
        if self.start_point is None or self.end_point is None:
            QMessageBox.critical(
                self, "Error", "Please select two points first.")
            return
        layer = iface.activeLayer()
        if layer is None:
            QMessageBox.critical(
                self, "Error", "No active layer to determine CRS.")
            return
        start_length = UnitConverter.to_meters(
            self.start_length_input.value(), self.unit_combo.currentText())
        end_length = UnitConverter.to_meters(
            self.end_length_input.value(), self.unit_combo.currentText())
        apex_point = GeometryHelper.calculate_triangle_apex(
            self.start_point, self.end_point, start_length, end_length, self.orientation_combo.currentText())
        if not apex_point:
            QMessageBox.critical(
                self, "Error", "Invalid side lengths. Triangle cannot be formed.")
            return
        line_layer = LayerManager.get_or_create_layer(
            "Triangle Lines", QgsWkbTypes.LineGeometry, layer.crs(), [QgsField("Type", QVariant.String)])
        line_layer.startEditing()

        def add_line(start, end, line_type):
            feature = QgsFeature(line_layer.fields())
            geom = QgsGeometry.fromPolylineXY([start, end])
            if not geom.isNull() and geom.isGeosValid():
                feature.setGeometry(geom)
                feature.setAttributes([line_type])
                return line_layer.addFeature(feature)
            return False
        add_line(self.start_point, apex_point, "Start Side")
        add_line(self.end_point, apex_point, "End Side")
        add_line(self.start_point, self.end_point, "Base Line")
        if not line_layer.commitChanges():
            errors = line_layer.commitErrors()
            QMessageBox.warning(
                self, "Warning", f"Some features may not have been saved: {errors}")
        LayerManager.update_layer_extent(line_layer)
        iface.setActiveLayer(layer)
        self.triangle_rubber_band.reset()
        self.lines_drawn = True
        self.clear_points()

    def cleanup(self):
        if iface.mapCanvas().mapTool() == self.point_tool:
            iface.mapCanvas().unsetMapTool(self.point_tool)
        self.point_tool.clear()
        self.triangle_rubber_band.reset()
        self.preview_timer.stop()

# Segment Select Tool


class SegmentSelectTool(QgsMapTool):
    def __init__(self, canvas, plotter_widget):
        super().__init__(canvas)
        self.canvas = canvas
        self.plotter_widget = plotter_widget
        self.snapping_utils = None  # Initialize as None, set in activate
        self.snap_marker = None  # Initialize as None, set in activate
        self.is_selecting = False
        self.is_active = False

    def activate(self):
        super().activate()
        self.is_active = True
        self.is_selecting = True

        # Reinitialize snapping utilities
        self.snapping_utils = self.canvas.snappingUtils()

        # Reinitialize snap marker
        if self.snap_marker:
            try:
                self.canvas.scene().removeItem(self.snap_marker)
            except:
                pass
        self.snap_marker = MarkerFactory.create_snap_marker(self.canvas)

        self.canvas.setCursor(QtCompat.get_cursor_shape('CrossCursor'))
        self.plotter_widget.status_label.setText(
            "Click on a line segment to add endpoints.")
        self.plotter_widget.select_segment_button.setEnabled(False)
        self.plotter_widget.select_segment_button.setText("Selecting...")
        self.plotter_widget.clear_segment_button.setEnabled(True)
        self.canvas.refresh()

    def deactivate(self):
        self.is_active = False
        self.is_selecting = False
        if self.snap_marker:
            self.snap_marker.hide()
        self.canvas.unsetCursor()
        if hasattr(self, 'plotter_widget'):
            self.plotter_widget.select_segment_button.setEnabled(True)
            self.plotter_widget.select_segment_button.setText("Select Segment")
        self.canvas.refresh()
        super().deactivate()

    def cleanup(self):
        self.is_active = False
        self.is_selecting = False
        if self.snap_marker:
            try:
                self.canvas.scene().removeItem(self.snap_marker)
            except:
                pass
            self.snap_marker = None
        self.snapping_utils = None
        self.canvas.unsetCursor()
        self.canvas.refresh()

    def canvasMoveEvent(self, event):
        if not self.is_active or not self.is_selecting:
            return

        snap_config = QgsProject.instance().snappingConfig()
        snapping_enabled = snap_config.enabled()

        if snapping_enabled and self.snapping_utils:
            match = self.snapping_utils.snapToMap(event.pos())
            if match.isValid() and match.type() == QgsPointLocator.Edge:
                self.snap_marker.setCenter(match.point())
                self.snap_marker.show()
            else:
                self.snap_marker.hide()
        else:
            self.snap_marker.hide()

    def canvasPressEvent(self, event):
        if not self.is_active or not self.is_selecting:
            return

        if event.button() == QtCompat.get_mouse_button('RightButton'):
            if self.plotter_widget.current_segment is not None:
                self.plotter_widget.current_layer = None
                self.plotter_widget.current_segment = None
                self.plotter_widget.plot_button.setEnabled(False)
                self.plotter_widget.endpoint_manager.clear_display()
                self.plotter_widget.status_label.setText(
                    "Last endpoint cleared. Click on a line segment to add more.")
            self.is_selecting = True
            self.canvas.setCursor(QtCompat.get_cursor_shape('CrossCursor'))
            self.plotter_widget.select_segment_button.setEnabled(False)
            self.plotter_widget.select_segment_button.setText("Selecting...")
            self.plotter_widget.clear_segment_button.setEnabled(True)
            if self.snap_marker:
                self.snap_marker.hide()
            self.canvas.refresh()
            return

        if event.button() != QtCompat.get_mouse_button('LeftButton'):
            return

        snap_config = QgsProject.instance().snappingConfig()
        snapping_enabled = snap_config.enabled()
        click_point = self.toMapCoordinates(event.pos())

        if snapping_enabled and self.snapping_utils:
            match = self.snapping_utils.snapToMap(event.pos())
            if match.isValid() and match.type() == QgsPointLocator.Edge:
                selected_feature = self._get_feature_from_snap(match)
                if selected_feature:
                    layer, feature, snapped_xy = selected_feature
                    start_pt, end_pt = self._find_closest_segment(
                        feature.geometry(), snapped_xy)
                    if start_pt and end_pt:
                        self.plotter_widget.set_selected_segment(
                            layer, start_pt, end_pt)
                        if self.snap_marker:
                            self.snap_marker.hide()
                        self.plotter_widget.status_label.setText(
                            "Endpoint added. Click another segment to add more (Right-click to clear last, Escape to finish).")
                        self.canvas.refresh()
                        self.is_selecting = True
                        self.canvas.setCursor(
                            QtCompat.get_cursor_shape('CrossCursor'))
                        return
            self.plotter_widget.status_label.setText(
                "No valid line segment found at click location. Check snapping settings.")
        else:
            # Fallback to tolerance-based selection when snapping is disabled
            selected_feature = self._find_feature_at_point(click_point)
            if selected_feature:
                layer, feature, closest_point = selected_feature
                start_pt, end_pt = self._find_closest_segment(
                    feature.geometry(), closest_point)
                if start_pt and end_pt:
                    self.plotter_widget.set_selected_segment(
                        layer, start_pt, end_pt)
                    if self.snap_marker:
                        self.snap_marker.hide()
                    self.plotter_widget.status_label.setText(
                        "Endpoint added (snapping disabled). Click another segment to add more (Right-click to clear last, Escape to finish).")
                    self.canvas.refresh()
                    self.is_selecting = True
                    self.canvas.setCursor(
                        QtCompat.get_cursor_shape('CrossCursor'))
                    return
            self.plotter_widget.status_label.setText(
                "No line segment found at click location (snapping disabled).")

        if self.snap_marker:
            self.snap_marker.hide()
        self.canvas.refresh()

    def keyPressEvent(self, event):
        if not self.is_active:
            return
        if event.key() == QtCompat.get_key('Key_Escape'):
            self.deactivate()
            if iface.mapCanvas().mapTool() == self:
                iface.mapCanvas().unsetMapTool(self)
            return
        super().keyPressEvent(event)

    def _get_feature_from_snap(self, match):
        layer = match.layer()
        if not layer or not isinstance(layer, QgsVectorLayer) or layer.geometryType() != QgsWkbTypes.LineGeometry:
            return None
        feature = layer.getFeature(match.featureId())
        if not feature.isValid():
            return None
        return layer, feature, match.point()

    def _find_feature_at_point(self, point):
        # Use a reasonable pixel tolerance for non-snapping selection
        tolerance_pixels = 10  # Adjust as needed
        pixel_tolerance = tolerance_pixels * self.canvas.mapUnitsPerPixel()
        rect = QgsRectangle(
            point.x() - pixel_tolerance,
            point.y() - pixel_tolerance,
            point.x() + pixel_tolerance,
            point.y() + pixel_tolerance
        )

        candidates = []
        for layer in QgsProject.instance().mapLayers().values():
            if not (layer.type() == QgsMapLayer.VectorLayer and layer.geometryType() == QgsWkbTypes.LineGeometry):
                continue
            layer.selectByRect(rect)
            selected_features = list(layer.selectedFeatures())
            layer.removeSelection()
            for feature in selected_features:
                geom = feature.geometry()
                dist_sq, closest_point, _, _ = geom.closestSegmentWithContext(
                    point, 1e-8)
                if dist_sq < pixel_tolerance ** 2:
                    candidates.append((dist_sq, layer, feature, closest_point))

        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0])
        _, layer, feature, closest_point = candidates[0]
        return layer, feature, closest_point

    def _find_closest_segment(self, geom, snapped_xy):
        if geom.isMultipart():
            multi = geom.constGet()
            min_dist = float('inf')
            selected_start_pt = None
            selected_end_pt = None
            for p in range(multi.numGeometries()):
                part_geom = QgsGeometry(multi.geometryN(p).clone())
                part_dist_sq, _, part_next_v, _ = part_geom.closestSegmentWithContext(
                    snapped_xy, 1e-8)
                if part_dist_sq < min_dist:
                    min_dist = part_dist_sq
                    vertices = part_geom.asPolyline()
                    seg_start_idx = part_next_v - 1
                    if seg_start_idx >= 0 and seg_start_idx + 1 < len(vertices):
                        selected_start_pt = vertices[seg_start_idx]
                        selected_end_pt = vertices[seg_start_idx + 1]
            return selected_start_pt, selected_end_pt
        else:
            dist_sq, _, next_v, _ = geom.closestSegmentWithContext(
                snapped_xy, 1e-8)
            if next_v < 0:
                return None, None
            vertices = geom.asPolyline()
            seg_start_idx = next_v - 1
            if seg_start_idx < 0 or seg_start_idx + 1 >= len(vertices):
                return None, None
            return vertices[seg_start_idx], vertices[seg_start_idx + 1]


# Plotter Widget


class PlotterWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220)
        self.endpoint_manager = LineEndpointManager()
        self.segment_tool = SegmentSelectTool(iface.mapCanvas(), self)
        self.current_layer = None
        self.current_segment = None
        self.points_drawn = False
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.status_label = QLabel("Click 'Select Segment' to start.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "QLabel { color: #F736F6; font-weight: bold; padding: 5px; }")
        layout.addWidget(self.status_label)
        button_layout = QHBoxLayout()
        self.select_segment_button = QPushButton("Select Segment")
        self.select_segment_button.clicked.connect(
            self.start_segment_selection)
        button_layout.addWidget(self.select_segment_button)
        self.clear_segment_button = QPushButton("Clear Segment")
        self.clear_segment_button.clicked.connect(self.clear_segment)
        self.clear_segment_button.setEnabled(False)
        button_layout.addWidget(self.clear_segment_button)
        layout.addLayout(button_layout)
        layout.addWidget(QLabel("Units:"))
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(list(UNIT_CONVERSIONS.keys()))
        layout.addWidget(self.unit_combo)
        layout.addWidget(QLabel("Choose Point:"))
        self.point_combo = QComboBox()
        self.point_combo.addItems(["🟢 Start Point", "🔴 End Point"])
        layout.addWidget(self.point_combo)
        layout.addWidget(QLabel("Cut Point Length:"))
        self.cut_point_input = QDoubleSpinBox()
        self.cut_point_input.setDecimals(3)
        self.cut_point_input.setRange(-1000000, 1000000)
        layout.addWidget(self.cut_point_input)
        layout.addWidget(QLabel("Offset Length:"))
        self.offset_input = QDoubleSpinBox()
        self.offset_input.setDecimals(3)
        self.offset_input.setRange(-1000000, 1000000)
        layout.addWidget(self.offset_input)
        self.plot_button = QPushButton("Plot")
        self.plot_button.clicked.connect(self.plot)
        self.plot_button.setEnabled(False)
        layout.addWidget(self.plot_button)
        layout.setAlignment(QtCompat.get_alignment('AlignTop'))
        self.setLayout(layout)

    def start_segment_selection(self):
        self.status_label.setText("Click on a line segment on the canvas.")
        self.segment_tool.activate()
        iface.mapCanvas().setMapTool(self.segment_tool)
        self.select_segment_button.setEnabled(False)
        self.select_segment_button.setText("Selecting...")
        self.clear_segment_button.setEnabled(True)
        self.activateWindow()
        self.raise_()

    def set_selected_segment(self, layer, start_pt, end_pt):
        """Set the selected segment and display endpoints"""
        self.current_layer = layer
        self.current_segment = [start_pt, end_pt]
        length = GeometryHelper.calculate_distance(start_pt, end_pt)
        current_unit = self.unit_combo.currentText()
        display_length = UnitConverter.from_meters(length, current_unit)
        unit_abbrev = UnitConverter.get_abbreviation(current_unit)

        # CRITICAL: Display the segment endpoints with markers
        # This will set manual_mode = True to prevent auto-clearing
        self.endpoint_manager.display_segment_endpoints(start_pt, end_pt)

        # Update status AFTER displaying markers
        self.status_label.setText(
            f"Segment selected. Length: {display_length:.3f} {unit_abbrev}")

        # Update button states
        self.clear_segment_button.setEnabled(True)
        self.plot_button.setEnabled(True)
        self.select_segment_button.setEnabled(True)
        self.select_segment_button.setText("Select Segment")

        # Bring widget to front
        self.activateWindow()
        self.raise_()

    def clear_segment(self):
        """Clear the current segment selection"""
        self.current_layer = None
        self.current_segment = None
        self.plot_button.setEnabled(False)
        self.status_label.setText("Click 'Select Segment' to start.")

        # Clear endpoint display and reset manual mode
        self.endpoint_manager.clear_display()
        self.endpoint_manager.manual_mode = False

        self.clear_segment_button.setEnabled(False)

        # Properly deactivate the tool if active
        if iface.mapCanvas().mapTool() == self.segment_tool:
            self.segment_tool.deactivate()
            iface.mapCanvas().unsetMapTool(self.segment_tool)

        iface.mapCanvas().refresh()

    def activate(self):
        self.endpoint_manager.activate()

    def deactivate(self):
        """Deactivate the plotter widget and clean up all states"""
        # Properly deactivate the segment tool
        if iface.mapCanvas().mapTool() == self.segment_tool:
            self.segment_tool.deactivate()
            iface.mapCanvas().unsetMapTool(self.segment_tool)

        # Clear all internal states
        self.current_layer = None
        self.current_segment = None
        self.plot_button.setEnabled(False)
        self.select_segment_button.setEnabled(True)
        self.select_segment_button.setText("Select Segment")
        self.clear_segment_button.setEnabled(False)
        self.status_label.setText("Click 'Select Segment' to start.")

        # Deactivate endpoint manager
        self.endpoint_manager.deactivate()

        iface.mapCanvas().refresh()

    def plot(self):
        if not self.current_segment:
            QMessageBox.critical(
                self, "Error", "Please select a segment first.")
            return

        point_layer = LayerManager.get_or_create_layer(
            "Plotted Points", QgsWkbTypes.PointGeometry, self.current_layer.crs(), [QgsField("Type", QVariant.String)])
        LayerManager.apply_categorized_symbology(point_layer, POINT_CATEGORIES)

        # Points are automatically snappable if project snapping is enabled
        # No need to override user's snapping preferences

        point_layer.startEditing()
        current_unit = self.unit_combo.currentText()
        offset_meters = UnitConverter.to_meters(
            self.offset_input.value(), current_unit)
        cut_point_meters = UnitConverter.to_meters(
            self.cut_point_input.value(), current_unit)
        start_end_choice_index = self.point_combo.currentIndex()
        self._process_line_part(self.current_segment, point_layer,
                                cut_point_meters, offset_meters, start_end_choice_index)
        if not point_layer.commitChanges():
            QMessageBox.warning(
                self, "Warning", f"Some points may not have been saved: {point_layer.commitErrors()}")
        LayerManager.update_layer_extent(point_layer)
        self.points_drawn = True

    def _process_line_part(self, part, point_layer, cut_point_meters, offset_meters, start_end_choice_index):
        start_point = QgsPointXY(part[0])
        end_point = QgsPointXY(part[-1])
        base_point = start_point if start_end_choice_index == 0 else end_point
        direction_point = part[1] if start_end_choice_index == 0 and len(
            part) > 1 else (part[-2] if len(part) > 1 else None)
        line_length = QgsGeometry.fromPolylineXY(part).length()
        if cut_point_meters < 0 or cut_point_meters > line_length:
            self._handle_extended_point(base_point, direction_point, cut_point_meters,
                                        offset_meters, part, start_end_choice_index, point_layer)
        else:
            self._handle_normal_cut_point(
                part, cut_point_meters, offset_meters, start_end_choice_index, point_layer)

    def _handle_extended_point(self, base_point, direction_point, cut_point_meters, offset_meters, part, start_end_choice_index, point_layer):
        if not direction_point:
            return
        dx = base_point.x() - \
            direction_point.x() if cut_point_meters < 0 else direction_point.x() - base_point.x()
        dy = base_point.y() - \
            direction_point.y() if cut_point_meters < 0 else direction_point.y() - base_point.y()
        direction_length = math.sqrt(dx**2 + dy**2)
        if direction_length == 0:
            QMessageBox.warning(
                self, "Warning", "Direction vector has zero length, cannot extend line.")
            return
        unit_dx, unit_dy = dx / direction_length, dy / direction_length
        extension_distance = abs(cut_point_meters)
        extended_point = QgsPointXY(base_point.x(
        ) + unit_dx * extension_distance, base_point.y() + unit_dy * extension_distance)
        point_type = "Bisect Point" if offset_meters == 0 else "Extended Point"
        self._add_point(point_layer, extended_point, point_type)
        if offset_meters != 0 and len(part) > 1:
            offset_point = self._calculate_offset_point(
                extended_point, part, start_end_choice_index, offset_meters)
            if offset_point:
                self._add_point(point_layer, offset_point, "Offset Point")

    def _handle_normal_cut_point(self, part, cut_point_meters, offset_meters, start_end_choice_index, point_layer):
        cut_point_geom = QgsGeometry.fromPolylineXY(part).interpolate(
            cut_point_meters) if start_end_choice_index == 0 else QgsGeometry.fromPolylineXY(part[::-1]).interpolate(cut_point_meters)
        if cut_point_geom.isNull():
            return
        cut_point = cut_point_geom.asPoint()
        point_type = "Bisect Point" if offset_meters == 0 else "Cut Point"
        self._add_point(point_layer, cut_point, point_type)
        if offset_meters != 0 and len(part) > 1:
            offset_point = self._calculate_offset_point(
                cut_point, part, start_end_choice_index, offset_meters)
            if offset_point:
                self._add_point(point_layer, offset_point, "Offset Point")

    def _calculate_offset_point(self, base_point, part, start_end_choice_index, offset_meters):
        dx = part[1].x(
        ) - part[0].x() if start_end_choice_index == 0 else part[-2].x() - part[-1].x()
        dy = part[1].y(
        ) - part[0].y() if start_end_choice_index == 0 else part[-2].y() - part[-1].y()
        length = math.sqrt(dx**2 + dy**2)
        if length == 0:
            QMessageBox.warning(
                self, "Warning", "Line segment has zero length, cannot calculate offset.")
            return None
        perp_dx, perp_dy = -dy / length, dx / length
        return QgsPointXY(base_point.x() + perp_dx * offset_meters, base_point.y() + perp_dy * offset_meters)

    def _add_point(self, layer, point, point_type):
        feature = QgsFeature(layer.fields())
        geom = QgsGeometry.fromPointXY(point)
        if not geom.isNull() and geom.isGeosValid():
            feature.setGeometry(geom)
            feature.setAttributes([point_type])
            return layer.addFeature(feature)
        return False

    def cleanup(self):
        """Complete cleanup of the plotter widget"""
        # Ensure proper cleanup of segment tool
        if iface.mapCanvas().mapTool() == self.segment_tool:
            self.segment_tool.deactivate()
            iface.mapCanvas().unsetMapTool(self.segment_tool)

        # Cleanup the segment tool itself
        if hasattr(self.segment_tool, 'cleanup'):
            self.segment_tool.cleanup()

        # Clear all states
        self.current_layer = None
        self.current_segment = None
        self.plot_button.setEnabled(False)
        self.select_segment_button.setEnabled(True)
        self.select_segment_button.setText("Select Segment")
        self.clear_segment_button.setEnabled(False)
        self.status_label.setText("Click 'Select Segment' to start.")

        # Cleanup endpoint manager
        self.endpoint_manager.cleanup()

        iface.mapCanvas().refresh()

# Combined Main Widget


class CombinedMainWidget(QWidget):
    def __init__(self, parent=iface.mainWindow()):
        super().__init__(parent)
        self.setWindowTitle('Plotter')
        self.setGeometry(900, 250, 250, 350)
        self.setWindowFlags(TOOL_WINDOW_FLAGS)
        self.tab_widget = QTabWidget()
        self.triangle_widget = TriangleWidget()
        self.plotter_widget = PlotterWidget()
        self.tab_widget.addTab(self.triangle_widget, "Triangle")
        self.tab_widget.addTab(self.plotter_widget, "Plotter")
        layout = QVBoxLayout()
        layout.addWidget(self.tab_widget)
        self.setLayout(layout)
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        self.has_been_activated = False

    def showEvent(self, event):
        """Handle widget show event - reset states when reopened"""
        super().showEvent(event)

        # Only reset if widget was previously closed (not just hidden)
        if not self.has_been_activated:
            # Reset all widget states when showing for first time or after close
            self.triangle_widget.clear_points()
            self.plotter_widget.clear_segment()

        # Activate the current widget
        current_widget = self.tab_widget.currentWidget()
        if hasattr(current_widget, 'activate'):
            current_widget.activate()

        self.has_been_activated = True

    def on_tab_changed(self, index):
        if not self.has_been_activated:
            return

        # Deactivate all widgets
        for widget in [self.triangle_widget, self.plotter_widget]:
            if hasattr(widget, 'deactivate'):
                widget.deactivate()

        # # Additional cleanup for triangle widget
        # self.triangle_widget.clear_points()
        # self.triangle_widget.point_tool.clear()

        # # Additional cleanup for plotter widget
        # self.plotter_widget.clear_segment()
        # self.plotter_widget.segment_tool.cleanup()

        # Unset current map tool
        current_tool = iface.mapCanvas().mapTool()
        if current_tool == self.triangle_widget.point_tool:
            self.triangle_widget.point_tool.deactivate()
            iface.mapCanvas().unsetMapTool(self.triangle_widget.point_tool)
        elif current_tool == self.plotter_widget.segment_tool:
            self.plotter_widget.segment_tool.deactivate()
            iface.mapCanvas().unsetMapTool(self.plotter_widget.segment_tool)

        # Activate current widget
        current_widget = self.tab_widget.currentWidget()
        if hasattr(current_widget, 'activate'):
            current_widget.activate()
        if current_widget == self.triangle_widget and hasattr(self.triangle_widget, 'schedule_preview_update'):
            self.triangle_widget.schedule_preview_update()
        iface.mapCanvas().refresh()

    def closeEvent(self, event):
        """Handle widget close event with proper cleanup"""
        # First, properly deactivate and unset all map tools
        current_tool = iface.mapCanvas().mapTool()
        if current_tool == self.triangle_widget.point_tool:
            self.triangle_widget.point_tool.deactivate()
            iface.mapCanvas().unsetMapTool(self.triangle_widget.point_tool)
        elif current_tool == self.plotter_widget.segment_tool:
            self.plotter_widget.segment_tool.deactivate()
            iface.mapCanvas().unsetMapTool(self.plotter_widget.segment_tool)

        # Deactivate all widgets
        self.triangle_widget.deactivate()
        self.plotter_widget.deactivate()

        # Check for unsaved Triangle Lines layer
        if self.triangle_widget.lines_drawn:
            line_layer = next((lyr for lyr in QgsProject.instance().mapLayers().values() if lyr.name(
            ) == "Triangle Lines" and lyr.geometryType() == QgsWkbTypes.LineGeometry), None)
            if line_layer and line_layer.providerType() == "memory":
                reply = QMessageBox.question(self, 'Save Triangle Lines', "Do you want to save the Triangle Lines Layer before closing?",
                                             QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Cancel)
                if reply == QMessageBox.Yes:
                    if not LayerManager.save_temp_layer(self, line_layer):
                        event.ignore()
                        return
                elif reply == QMessageBox.Cancel:
                    event.ignore()
                    return

        # Check for unsaved Plotted Points layer
        if self.plotter_widget.points_drawn:
            point_layer = next((lyr for lyr in QgsProject.instance().mapLayers().values() if lyr.name(
            ) == "Plotted Points" and lyr.geometryType() == QgsWkbTypes.PointGeometry), None)
            if point_layer and point_layer.providerType() == "memory":
                reply = QMessageBox.question(self, 'Save Plotted Points', "Do you want to save the Plotted Points Layer before closing?",
                                             QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Cancel)
                if reply == QMessageBox.Yes:
                    if not LayerManager.save_temp_layer(self, point_layer):
                        event.ignore()
                        return
                elif reply == QMessageBox.Cancel:
                    event.ignore()
                    return

        # Final cleanup - completely reset all states
        self.triangle_widget.cleanup()
        self.plotter_widget.cleanup()

        # Reset the activation flag
        self.has_been_activated = False

        iface.mapCanvas().refresh()
        event.accept()


# Main Execution
main_widget = CombinedMainWidget()
# main_widget.show() '

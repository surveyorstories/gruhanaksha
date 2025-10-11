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
                       QgsTolerance, QgsPointLocator)
from qgis.utils import iface
from qgis.core import QgsMapLayer

from .addon_functions import TOOL_WINDOW_FLAGS

# ==============================================================================
# CONSTANTS AND CONFIGURATION
# ==============================================================================

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
    {'name': "Extended Point", 'color': 'purple', 'size': 2},
    {'name': "Bisect Point", 'color': 'green', 'size': 2},
]

# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================


class UnitConverter:
    """Handles unit conversions"""

    @staticmethod
    def to_meters(value, unit):
        """Convert value to meters"""
        return value * UNIT_CONVERSIONS.get(unit, {"factor": 1.0})["factor"]

    @staticmethod
    def from_meters(value, unit):
        """Convert value from meters to specified unit"""
        factor = UNIT_CONVERSIONS.get(unit, {"factor": 1.0})["factor"]
        return value / factor if factor != 0 else value

    @staticmethod
    def get_abbreviation(unit):
        """Get unit abbreviation"""
        return UNIT_CONVERSIONS.get(unit, {"abbrev": "m"})["abbrev"]


class GeometryHelper:
    """Helper functions for geometry calculations"""

    @staticmethod
    def get_line_endpoints(geometry):
        """Extract start and end points from line geometry"""
        try:
            if geometry.isMultipart():
                points = geometry.asMultiPolyline()
                if points and len(points) > 0 and len(points[0]) > 0:
                    return QgsPointXY(points[0][0]), QgsPointXY(points[-1][-1])
            else:
                points = geometry.asPolyline()
                if points and len(points) > 0:
                    return QgsPointXY(points[0]), QgsPointXY(points[-1])
        except Exception:
            pass
        return None, None

    @staticmethod
    def calculate_distance(point1, point2):
        """Calculate distance between two points"""
        dx = point2.x() - point1.x()
        dy = point2.y() - point1.y()
        return math.sqrt(dx**2 + dy**2)

    @staticmethod
    def calculate_triangle_apex(start_point, end_point, start_length, end_length, orientation):
        """Calculate the apex point of a triangle"""
        try:
            dx = end_point.x() - start_point.x()
            dy = end_point.y() - start_point.y()
            base_length = math.sqrt(dx**2 + dy**2)

            if base_length == 0:
                return None

            # Triangle inequality check
            if not (start_length + end_length > base_length and
                    start_length + base_length > end_length and
                    end_length + base_length > start_length):
                return None

            # Normalize direction vector
            ux = dx / base_length
            uy = dy / base_length

            # Perpendicular vector based on orientation
            if orientation == "Right":
                perp_ux, perp_uy = -uy, ux
            else:  # Left
                perp_ux, perp_uy = uy, -ux

            # Law of Cosines
            angle_start = math.acos(
                (start_length**2 + base_length**2 - end_length**2) /
                (2 * start_length * base_length)
            )

            # Calculate apex
            apex_x = start_point.x() + start_length * (ux * math.cos(angle_start) -
                                                       perp_ux * math.sin(angle_start))
            apex_y = start_point.y() + start_length * (uy * math.cos(angle_start) -
                                                       perp_uy * math.sin(angle_start))

            return QgsPointXY(apex_x, apex_y)

        except (ValueError, ZeroDivisionError):
            return None


class LayerManager:
    """Manages layer operations"""

    @staticmethod
    def save_temp_layer(parent, layer):
        """Save or update a temporary layer"""
        try:
            if layer.providerType() != "memory":
                return True

            file_path, _ = QFileDialog.getSaveFileName(
                parent, f"Save {layer.name()}", layer.name(),
                "ESRI Shapefile (*.shp);;GeoJSON (*.geojson);;GPKG (*.gpkg)"
            )

            if not file_path:
                return False

            # Determine format
            format_map = {
                ".shp": "ESRI Shapefile",
                ".geojson": "GeoJSON",
                ".gpkg": "GPKG"
            }

            format_name = next(
                (fmt for ext, fmt in format_map.items() if file_path.endswith(ext)), None)
            if not format_name:
                QMessageBox.critical(
                    parent, "Error", "Unsupported file format.")
                return False

            # Save layer
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = format_name
            options.fileEncoding = "UTF-8"

            error = QgsVectorFileWriter.writeAsVectorFormatV3(
                layer, file_path, QgsProject.instance().transformContext(), options
            )

            if error[0] == QgsVectorFileWriter.WriterError.NoError:
                QMessageBox.information(parent, "Save Successful",
                                        f"Layer saved successfully at {file_path}!")

                # Reload layer
                new_layer = QgsVectorLayer(file_path, layer.name(), "ogr")
                if new_layer.isValid():
                    new_layer.setRenderer(layer.renderer().clone())
                    QgsProject.instance().addMapLayer(new_layer)
                    QgsProject.instance().removeMapLayer(layer.id())
                    return True
                else:
                    QMessageBox.warning(parent, "Warning",
                                        "Failed to reload the saved layer into the project.")
            else:
                QMessageBox.critical(parent, "Save Error",
                                     f"Error saving layer. Error code: {error[0]}")
            return False

        except Exception as e:
            QMessageBox.critical(parent, "Unexpected Error",
                                 f"An unexpected error occurred: {e}")
            return False

    @staticmethod
    def apply_categorized_symbology(layer, categories_info):
        """Apply categorized symbology to a layer"""
        categories = []
        for category_info in categories_info:
            symbol = QgsMarkerSymbol.createSimple({
                'name': 'circle',
                'color': category_info['color'],
                'size': str(category_info['size']),
                'outline_color': '0,0,0,255',
                'outline_width': '0.2'
            })
            category = QgsRendererCategory(
                category_info['name'], symbol, category_info['name'])
            categories.append(category)

        renderer = QgsCategorizedSymbolRenderer('Type', categories)
        layer.setRenderer(renderer)

    @staticmethod
    def get_or_create_layer(layer_name, geometry_type, crs, fields):
        """Get existing layer or create new one"""
        # Check for existing layer
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() == layer_name and lyr.geometryType() == geometry_type:
                return lyr

        # Create new layer
        geom_type_str = "LineString" if geometry_type == QgsWkbTypes.GeometryType.LineGeometry else "Point"
        layer = QgsVectorLayer(
            f"{geom_type_str}?crs={crs.toWkt()}", layer_name, "memory")
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()
        QgsProject.instance().addMapLayer(layer)

        # Update layer extent immediately
        layer.updateExtents()

        return layer

    @staticmethod
    def update_layer_extent(layer):
        """Force update layer extent and refresh canvas"""
        try:
            # Force recalculate extent from features
            provider = layer.dataProvider()
            if provider:
                provider.updateExtents()

            # Update layer extent
            layer.updateExtents()

            # Reload the layer to ensure spatial index is built
            layer.reload()

            # Trigger repaint
            layer.triggerRepaint()

            # Refresh canvas and snapping cache
            canvas = iface.mapCanvas()
            canvas.refresh()
            canvas.snappingUtils().clearCache()

            # Force snapping config update
            QgsProject.instance().snappingConfig()

        except Exception:
            pass


class MarkerFactory:
    """Factory for creating map markers"""

    @staticmethod
    def create_vertex_marker(canvas, point, color, fill_color=None, size=8):
        """Create a vertex marker"""
        marker = QgsVertexMarker(canvas)
        marker.setCenter(point)
        marker.setColor(color)
        if fill_color:
            marker.setFillColor(fill_color)
        marker.setIconSize(size)
        marker.setIconType(QgsVertexMarker.IconType.ICON_CIRCLE)
        marker.setPenWidth(2)
        return marker

    @staticmethod
    def create_snap_marker(canvas):
        """Create a snap indicator marker"""
        marker = QgsVertexMarker(canvas)
        marker.setIconType(QgsVertexMarker.ICON_CROSS)
        marker.setColor(QColor(255, 0, 255))
        marker.setPenWidth(3)
        marker.setIconSize(12)
        marker.hide()
        return marker


# ==============================================================================
# LINE ENDPOINT MANAGER
# ==============================================================================

class LineEndpointManager:
    """Manages the display of line start and end points"""

    def __init__(self):
        self.map_canvas = iface.mapCanvas()
        self.current_layer = None
        self.is_active = False
        self.start_point_marker = None
        self.end_point_marker = None

    def activate(self):
        """Activate the endpoint manager"""
        if self.is_active:
            return

        self.is_active = True
        try:
            iface.layerTreeView().currentLayerChanged.connect(self.on_layer_changed)
            current_layer = iface.activeLayer()
            if current_layer:
                self.on_layer_changed(current_layer)
        except Exception:
            pass

    def deactivate(self):
        """Deactivate the endpoint manager"""
        if not self.is_active:
            return

        self.is_active = False

        try:
            iface.layerTreeView().currentLayerChanged.disconnect(self.on_layer_changed)
        except (TypeError, AttributeError):
            pass

        try:
            if self.current_layer:
                self.current_layer.selectionChanged.disconnect(
                    self.update_display)
        except (TypeError, AttributeError):
            pass

        self.clear_display()
        self.current_layer = None

    def on_layer_changed(self, layer):
        """Handle layer change"""
        if not self.is_active:
            return

        # Disconnect previous layer
        if self.current_layer:
            try:
                self.current_layer.selectionChanged.disconnect(
                    self.update_display)
            except (TypeError, AttributeError):
                pass

        self.current_layer = layer
        self.clear_display()

        if layer and hasattr(layer, 'wkbType') and layer.wkbType() in [
            QgsWkbTypes.Type.LineString, QgsWkbTypes.Type.MultiLineString
        ]:
            try:
                layer.selectionChanged.connect(self.update_display)
                self.update_display()
            except Exception:
                pass

    def update_display(self):
        """Update start and end points display"""
        if not self.is_active:
            return

        self.clear_display()

        if not self.current_layer or not hasattr(self.current_layer, 'wkbType'):
            return

        if self.current_layer.wkbType() not in [
            QgsWkbTypes.Type.LineString, QgsWkbTypes.Type.MultiLineString
        ]:
            return

        try:
            selected_features = list(self.current_layer.selectedFeatures())
            if len(selected_features) != 1:
                return

            feature = selected_features[0]
            geom = feature.geometry()
            if not geom or geom.isNull():
                return

            start_point, end_point = GeometryHelper.get_line_endpoints(geom)
            if start_point and end_point:
                self.start_point_marker = MarkerFactory.create_vertex_marker(
                    self.map_canvas, start_point,
                    QColor(0, 0, 0), QColor(0, 255, 0, 200), 11
                )
                self.start_point_marker.setPenWidth(1)

                self.end_point_marker = MarkerFactory.create_vertex_marker(
                    self.map_canvas, end_point,
                    QColor(0, 0, 0), QColor(255, 0, 0, 200), 11
                )
                self.end_point_marker.setPenWidth(1)

                self.map_canvas.refresh()

        except Exception:
            pass

    def clear_display(self):
        """Clear markers"""
        try:
            if self.start_point_marker:
                self.map_canvas.scene().removeItem(self.start_point_marker)
                self.start_point_marker = None
            if self.end_point_marker:
                self.map_canvas.scene().removeItem(self.end_point_marker)
                self.end_point_marker = None
        except Exception:
            pass

    def display_segment_endpoints(self, start_point, end_point):
        """Display endpoints for a specific segment"""
        self.clear_display()
        if start_point and end_point:
            self.start_point_marker = MarkerFactory.create_vertex_marker(
                self.map_canvas, start_point,
                QColor(0, 0, 0), QColor(0, 255, 0, 200), 11
            )
            self.start_point_marker.setPenWidth(1)

            self.end_point_marker = MarkerFactory.create_vertex_marker(
                self.map_canvas, end_point,
                QColor(0, 0, 0), QColor(255, 0, 0, 200), 11
            )
            self.end_point_marker.setPenWidth(1)

            self.map_canvas.refresh()

    def cleanup(self):
        """Clean up"""
        self.deactivate()
        try:
            self.map_canvas.refresh()
        except Exception:
            pass


# ==============================================================================
# TRIANGLE POINT TOOL
# ==============================================================================

class TrianglePointTool(QgsMapTool):
    """Map tool for selecting triangle base points"""

    def __init__(self, canvas, triangle_widget):
        super().__init__(canvas)
        self.canvas = canvas
        self.triangle_widget = triangle_widget
        self.first_point = None
        self.markers = []
        self.use_fixed_length = False
        self.is_selecting = False

        # Rubber bands
        self.base_line = QgsRubberBand(
            canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.base_line.setColor(QColor(0, 0, 255, 150))
        self.base_line.setWidth(2)

        self.temp_line = QgsRubberBand(
            canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.temp_line.setColor(QColor(0, 0, 255, 100))
        self.temp_line.setWidth(1)
        self.temp_line.setLineStyle(Qt.PenStyle.DashLine)

        self.setCursor(Qt.CursorShape.CrossCursor)
        self.snapping_utils = canvas.snappingUtils()
        self.snap_marker = MarkerFactory.create_snap_marker(canvas)

    def keyPressEvent(self, event):
        """Handle keyboard input"""
        if event.key() == Qt.Key.Key_L and self.first_point is not None:
            self.use_fixed_length = True
            self.show_length_dialog()
        elif event.key() == Qt.Key.Key_Escape:
            self.clear()
            self.triangle_widget.status_label.setText(
                "Operation cancelled. Click 'Select Points' to start.")
            self.triangle_widget.clear_points()
        else:
            super().keyPressEvent(event)

    def show_length_dialog(self):
        """Show dialog to enter length with unit selection"""
        dialog = QDialog(self.triangle_widget)
        dialog.setWindowTitle("Enter Base Line Length")
        dialog.setModal(True)

        layout = QVBoxLayout()

        # Length input
        length_layout = QHBoxLayout()
        length_layout.addWidget(QLabel("Length:"))
        length_input = QDoubleSpinBox()
        length_input.setDecimals(3)
        length_input.setRange(0.001, 1000000)
        length_input.setValue(self.triangle_widget.fixed_base_length)
        length_input.setMinimumWidth(150)
        length_layout.addWidget(length_input)
        layout.addLayout(length_layout)

        # Unit selection
        unit_layout = QHBoxLayout()
        unit_layout.addWidget(QLabel("Unit:"))
        unit_combo = QComboBox()
        unit_combo.addItems(list(UNIT_CONVERSIONS.keys()))
        unit_combo.setCurrentText(
            self.triangle_widget.unit_combo.currentText())
        unit_combo.setMinimumWidth(150)
        unit_layout.addWidget(unit_combo)
        layout.addLayout(unit_layout)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                      QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)
        length_input.setFocus()
        length_input.selectAll()

        if dialog.exec() == QDialog.DialogCode.Accepted:
            length = length_input.value()
            unit = unit_combo.currentText()

            self.triangle_widget.fixed_base_length = length
            self.triangle_widget.unit_combo.setCurrentText(unit)

            unit_abbrev = UnitConverter.get_abbreviation(unit)
            self.triangle_widget.status_label.setText(
                f"Length set to {length:.3f} {unit_abbrev}. Click to set direction."
            )
        else:
            self.use_fixed_length = False

    def canvasMoveEvent(self, event):
        """Show snap marker and preview line direction"""
        if not self.is_selecting:
            return

        match = self.snapping_utils.snapToMap(event.pos())

        if match.isValid():
            self.snap_marker.setCenter(match.point())
            self.snap_marker.show()
            current_point = match.point()
        else:
            self.snap_marker.hide()
            current_point = self.toMapCoordinates(event.pos())

        if self.first_point is not None:
            self.temp_line.reset()
            self.temp_line.addPoint(self.first_point, False)

            if self.use_fixed_length:
                distance = GeometryHelper.calculate_distance(
                    self.first_point, current_point)

                if distance > 0:
                    base_length = UnitConverter.to_meters(
                        self.triangle_widget.fixed_base_length,
                        self.triangle_widget.unit_combo.currentText()
                    )
                    dx = current_point.x() - self.first_point.x()
                    dy = current_point.y() - self.first_point.y()
                    unit_dx = dx / distance
                    unit_dy = dy / distance

                    preview_end = QgsPointXY(
                        self.first_point.x() + unit_dx * base_length,
                        self.first_point.y() + unit_dy * base_length
                    )
                    self.temp_line.addPoint(preview_end, True)
            else:
                self.temp_line.addPoint(current_point, True)

    def canvasPressEvent(self, event):
        """Handle mouse click"""
        if not self.is_selecting:
            return

        if event.button() == Qt.MouseButton.RightButton:
            if self.first_point is not None:
                self.clear()
                self.triangle_widget.status_label.setText(
                    "Reset. Click first point to start again.")
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        match = self.snapping_utils.snapToMap(event.pos())
        point = match.point() if match.isValid() else self.toMapCoordinates(event.pos())

        if self.first_point is None:
            self.first_point = point
            marker = MarkerFactory.create_vertex_marker(
                self.canvas, point, QColor(0, 255, 0), QColor(0, 255, 0, 200)
            )
            self.markers.append(marker)
            self.triangle_widget.status_label.setText(
                "Press 'L' for fixed length or click second point (Right-click to reset)"
            )
        else:
            # Calculate second point
            if self.use_fixed_length:
                base_length = UnitConverter.to_meters(
                    self.triangle_widget.fixed_base_length,
                    self.triangle_widget.unit_combo.currentText()
                )

                if base_length <= 0:
                    QMessageBox.warning(self.triangle_widget, "Invalid Length",
                                        "Base line length must be greater than 0.")
                    return

                distance = GeometryHelper.calculate_distance(
                    self.first_point, point)
                if distance == 0:
                    QMessageBox.warning(self.triangle_widget, "Invalid Direction",
                                        "Second point must be different from first point.")
                    return

                dx = point.x() - self.first_point.x()
                dy = point.y() - self.first_point.y()
                unit_dx = dx / distance
                unit_dy = dy / distance

                second_point = QgsPointXY(
                    self.first_point.x() + unit_dx * base_length,
                    self.first_point.y() + unit_dy * base_length
                )
            else:
                base_length = GeometryHelper.calculate_distance(
                    self.first_point, point)
                if base_length == 0:
                    QMessageBox.warning(self.triangle_widget, "Invalid Point",
                                        "Second point must be different from first point.")
                    return

                second_point = point
                current_unit = self.triangle_widget.unit_combo.currentText()
                display_length = UnitConverter.from_meters(
                    base_length, current_unit)
                self.triangle_widget.fixed_base_length = display_length

            # Create second point marker
            marker = MarkerFactory.create_vertex_marker(
                self.canvas, second_point, QColor(
                    255, 0, 0), QColor(255, 0, 0, 200)
            )
            self.markers.append(marker)

            # Draw base line
            self.base_line.reset()
            self.base_line.addPoint(self.first_point, False)
            self.base_line.addPoint(second_point, True)
            self.temp_line.reset()

            # Update status with correct units
            actual_length = GeometryHelper.calculate_distance(
                self.first_point, second_point)
            current_unit = self.triangle_widget.unit_combo.currentText()
            display_length = UnitConverter.from_meters(
                actual_length, current_unit)
            unit_abbrev = UnitConverter.get_abbreviation(current_unit)

            # Stop selecting and update widget BEFORE unsetting tool
            self.use_fixed_length = False
            self.is_selecting = False

            # Update widget with points and status
            self.triangle_widget.set_points(self.first_point, second_point)
            self.triangle_widget.status_label.setText(
                f"Base line set ({display_length:.3f} {unit_abbrev}). Ready to draw triangle."
            )
            self.triangle_widget.select_points_button.setEnabled(True)
            self.triangle_widget.select_points_button.setText("Select Points")

            self.snap_marker.hide()

            # Unset tool last
            iface.mapCanvas().unsetMapTool(self)

    def activate(self):
        """Called when tool is activated"""
        super().activate()
        self.is_selecting = True
        self.canvas.setCursor(Qt.CursorShape.CrossCursor)

    def deactivate(self):
        """Clean up when tool is deactivated"""
        # Store state before cleanup
        had_first_point = self.first_point is not None

        # Always hide temporary visual elements
        if hasattr(self, 'snap_marker'):
            self.snap_marker.hide()
        if hasattr(self, 'temp_line'):
            self.temp_line.reset()

        # Only full reset if we don't have both points set
        if not had_first_point or self.is_selecting:
            # Reset selection state when tool is changed
            self.is_selecting = False

            # Clear all markers and rubber bands only if incomplete
            for marker in self.markers:
                try:
                    self.canvas.scene().removeItem(marker)
                except:
                    pass
            self.markers = []

            self.base_line.reset()
            self.first_point = None
            self.use_fixed_length = False

            # Update widget UI
            self.triangle_widget.select_points_button.setEnabled(True)
            self.triangle_widget.select_points_button.setText("Select Points")
            self.triangle_widget.status_label.setText(
                "Click 'Select Points' to start")

        super().deactivate()

    def clear(self):
        """Clear all points and markers"""
        self.first_point = None
        self.use_fixed_length = False
        self.is_selecting = False

        # Remove all markers from canvas
        for marker in self.markers:
            try:
                self.canvas.scene().removeItem(marker)
            except:
                pass
        self.markers = []

        # Reset all rubber bands
        self.base_line.reset()
        self.temp_line.reset()

        # Hide snap marker
        if hasattr(self, 'snap_marker'):
            self.snap_marker.hide()

        # Refresh canvas to clear visuals
        self.canvas.refresh()


# ==============================================================================
# TRIANGLE WIDGET
# ==============================================================================

class TriangleWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Triangle')
        self.setGeometry(50, 200, 200, 200)
        self.setMinimumWidth(220)

        self.start_point = None
        self.end_point = None
        self.fixed_base_length = 10.0
        self.lines_drawn = False

        self.point_tool = TrianglePointTool(iface.mapCanvas(), self)

        self.triangle_rubber_band = QgsRubberBand(
            iface.mapCanvas(), QgsWkbTypes.GeometryType.LineGeometry)
        self.triangle_rubber_band.setColor(QColor(255, 0, 0, 150))
        self.triangle_rubber_band.setWidth(3)

        self.preview_timer = QTimer()
        self.preview_timer.timeout.connect(self.update_triangle_preview)
        self.preview_timer.setSingleShot(True)

        self.setup_ui()

    def setup_ui(self):
        """Setup user interface"""
        layout = QVBoxLayout()

        # Status Label
        self.status_label = QLabel("Click 'Select Points' to start")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "QLabel { color: blue; font-weight: bold; padding: 5px; }")
        self.status_label.setMinimumHeight(40)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.status_label)

        # Buttons
        button_layout = QHBoxLayout()
        self.select_points_button = QPushButton("Select Points")
        self.select_points_button.clicked.connect(self.start_point_selection)
        button_layout.addWidget(self.select_points_button)

        self.clear_points_button = QPushButton("Clear Points")
        self.clear_points_button.clicked.connect(self.clear_points)
        self.clear_points_button.setEnabled(False)
        button_layout.addWidget(self.clear_points_button)
        layout.addLayout(button_layout)

        # Unit Selection
        layout.addWidget(QLabel("Units:"))
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(list(UNIT_CONVERSIONS.keys()))
        self.unit_combo.setCurrentIndex(0)
        self.unit_combo.currentTextChanged.connect(
            self.schedule_preview_update)
        layout.addWidget(self.unit_combo)

        # Length Inputs
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

        # Orientation
        layout.addWidget(QLabel("Orientation:"))
        self.orientation_combo = QComboBox()
        self.orientation_combo.addItems(["Left", "Right"])
        self.orientation_combo.setCurrentIndex(0)
        self.orientation_combo.currentTextChanged.connect(
            self.schedule_preview_update)
        layout.addWidget(self.orientation_combo)

        # Draw Button
        self.draw_button = QPushButton("Draw Triangle")
        self.draw_button.clicked.connect(self.draw_triangle)
        self.draw_button.setEnabled(False)
        layout.addWidget(self.draw_button)

        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setLayout(layout)

    def start_point_selection(self):
        """Activate the point selection tool"""
        self.clear_points()
        self.status_label.setText("Click first point on canvas")
        iface.mapCanvas().setMapTool(self.point_tool)
        self.select_points_button.setEnabled(False)
        self.select_points_button.setText("Selecting...")
        self.activateWindow()
        self.raise_()

    def set_points(self, start_point, end_point):
        """Set the start and end points"""
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
        """Clear selected points and reset"""
        self.start_point = None
        self.end_point = None

        # Clear the point tool's state
        self.point_tool.clear()

        # Clear triangle rubber band preview
        self.triangle_rubber_band.reset()

        # Update UI state
        self.draw_button.setEnabled(False)
        self.clear_points_button.setEnabled(False)
        self.select_points_button.setEnabled(True)
        self.select_points_button.setText("Select Points")
        self.status_label.setText("Click 'Select Points' to start")

        # Unset map tool if it's currently active
        if iface.mapCanvas().mapTool() == self.point_tool:
            iface.mapCanvas().unsetMapTool(self.point_tool)

        # Refresh canvas to ensure all visuals are cleared
        iface.mapCanvas().refresh()

    def activate(self):
        """Activate the triangle widget"""
        pass

    def deactivate(self):
        """Deactivate the triangle widget"""
        # Reset button state when deactivating
        if hasattr(self, 'point_tool') and not self.point_tool.is_selecting:
            self.select_points_button.setEnabled(True)
            self.select_points_button.setText("Select Points")

        # Only unset tool if no points have been set yet
        if (iface.mapCanvas().mapTool() == self.point_tool and
                self.start_point is None and self.end_point is None):
            iface.mapCanvas().unsetMapTool(self.point_tool)

    def schedule_preview_update(self):
        """Schedule preview update with delay"""
        if self.start_point is None or self.end_point is None:
            return
        self.preview_timer.stop()
        self.preview_timer.start(200)

    def update_triangle_preview(self):
        """Update rubber band preview"""
        self.triangle_rubber_band.reset()

        if self.start_point is None or self.end_point is None:
            return

        try:
            start_length = UnitConverter.to_meters(
                self.start_length_input.value(),
                self.unit_combo.currentText()
            )
            end_length = UnitConverter.to_meters(
                self.end_length_input.value(),
                self.unit_combo.currentText()
            )

            if start_length <= 0 or end_length <= 0:
                return

            apex_point = GeometryHelper.calculate_triangle_apex(
                self.start_point, self.end_point, start_length, end_length,
                self.orientation_combo.currentText()
            )

            if apex_point:
                self.triangle_rubber_band.addPoint(self.start_point, False)
                self.triangle_rubber_band.addPoint(apex_point, False)
                self.triangle_rubber_band.addPoint(self.end_point, False)
                self.triangle_rubber_band.addPoint(self.start_point, True)

        except Exception:
            pass

    def draw_triangle(self):
        """Draw triangle using selected points"""
        try:
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
                self.start_length_input.value(),
                self.unit_combo.currentText()
            )
            end_length = UnitConverter.to_meters(
                self.end_length_input.value(),
                self.unit_combo.currentText()
            )

            apex_point = GeometryHelper.calculate_triangle_apex(
                self.start_point, self.end_point, start_length, end_length,
                self.orientation_combo.currentText()
            )

            if not apex_point:
                QMessageBox.critical(self, "Error",
                                     "Invalid side lengths. Triangle cannot be formed.")
                return

            # Get or create layer
            line_layer = LayerManager.get_or_create_layer(
                "Triangle Lines",
                QgsWkbTypes.GeometryType.LineGeometry,
                layer.crs(),
                [QgsField("Type", QVariant.String)]
            )

            # Start editing
            line_layer.startEditing()

            # Add line features with explicit geometry validation
            def add_line(start, end, line_type):
                feature = QgsFeature(line_layer.fields())
                geom = QgsGeometry.fromPolylineXY([start, end])

                # Validate geometry
                if not geom.isNull() and geom.isGeosValid():
                    feature.setGeometry(geom)
                    feature.setAttributes([line_type])
                    success = line_layer.addFeature(feature)
                    return success
                return False

            # Add all three lines
            add_line(self.start_point, apex_point, "Start Side")
            add_line(self.end_point, apex_point, "End Side")
            add_line(self.start_point, self.end_point, "Base Line")

            # Commit changes
            if not line_layer.commitChanges():
                errors = line_layer.commitErrors()
                QMessageBox.warning(
                    self, "Warning", f"Some features may not have been saved: {errors}")

            # Force extent update
            LayerManager.update_layer_extent(line_layer)

            iface.setActiveLayer(layer)
            self.triangle_rubber_band.reset()

            self.lines_drawn = True
            self.clear_points()

        except Exception as e:
            QMessageBox.critical(self, "Unexpected Error",
                                 f"An unexpected error occurred: {e}")

    def cleanup(self):
        """Clean up resources"""
        try:
            if iface.mapCanvas().mapTool() == self.point_tool:
                iface.mapCanvas().unsetMapTool(self.point_tool)
            if hasattr(self, 'point_tool'):
                self.point_tool.clear()
            if hasattr(self, 'triangle_rubber_band'):
                self.triangle_rubber_band.reset()
            if hasattr(self, 'preview_timer'):
                self.preview_timer.stop()
        except Exception:
            pass


# ==============================================================================
# SEGMENT SELECT TOOL
# ==============================================================================

class SegmentSelectTool(QgsMapTool):
    """Map tool for selecting a line segment"""

    def __init__(self, canvas, plotter_widget):
        super().__init__(canvas)
        self.canvas = canvas
        self.plotter_widget = plotter_widget
        self.snapping_utils = canvas.snappingUtils()
        self.snap_marker = MarkerFactory.create_snap_marker(canvas)
        self.is_selecting = False
        self.is_active = False

    def activate(self):
        """Called when tool is activated"""
        super().activate()
        self.is_active = True
        self.is_selecting = True

        # Use existing snapping configuration
        self.canvas.setCursor(Qt.CursorShape.CrossCursor)
        self.plotter_widget.status_label.setText(
            "Click on a line segment on the canvas.")
        self.plotter_widget.select_segment_button.setEnabled(False)
        self.plotter_widget.select_segment_button.setText("Selecting...")

    def deactivate(self):
        """Called when tool is deactivated"""
        self.reset_selection_state()
        self.snap_marker.hide()
        self.canvas.unsetCursor()
        self.is_active = False
        self.is_selecting = False
        self.plotter_widget.select_segment_button.setEnabled(True)
        self.plotter_widget.select_segment_button.setText("Select Segment")
        self.canvas.refresh()
        super().deactivate()

    def canvasMoveEvent(self, event):
        """Handle mouse movement"""
        if not self.is_active or not self.is_selecting:
            return

        match = self.snapping_utils.snapToMap(event.pos())
        if match.isValid() and match.type() == QgsPointLocator.Edge:
            self.snap_marker.setCenter(match.point())
            self.snap_marker.show()
        else:
            self.snap_marker.hide()

    def canvasPressEvent(self, event):
        """Handle mouse click"""
        if not self.is_active or not self.is_selecting:
            return

        if event.button() == Qt.MouseButton.RightButton:
            self.cancel_selection()
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        match = self.snapping_utils.snapToMap(event.pos())
        if not match.isValid() or match.type() != QgsPointLocator.Edge:
            # If snapping is off or no snap match, try manual feature detection
            point = self.toMapCoordinates(event.pos())
            selected_feature = self._find_feature_at_point(point)
            if not selected_feature:
                self.plotter_widget.status_label.setText(
                    "Click on a line segment.")
                return
        else:
            selected_feature = self._get_feature_from_snap(match)
            if not selected_feature:
                self.plotter_widget.status_label.setText(
                    "Click on a line segment.")
                return

        layer, feature, snapped_xy = selected_feature
        start_pt, end_pt = self._find_closest_segment(
            feature.geometry(), snapped_xy)
        if not start_pt or not end_pt:
            self.plotter_widget.status_label.setText(
                "Invalid segment selection.")
            return

        self.is_selecting = False
        self.plotter_widget.set_selected_segment(layer, start_pt, end_pt)
        self.snap_marker.hide()
        iface.mapCanvas().unsetMapTool(self)

    def keyPressEvent(self, event):
        """Handle keyboard input"""
        if not self.is_active:
            super().keyPressEvent(event)
            return

        if event.key() == Qt.Key.Key_Escape:
            self.cancel_selection()
        else:
            super().keyPressEvent(event)

    def cancel_selection(self):
        """Cancel the current selection"""
        self.reset_selection_state()
        self.plotter_widget.status_label.setText(
            "Selection cancelled. Click 'Select Segment' to start.")
        self.plotter_widget.clear_segment()
        iface.mapCanvas().unsetMapTool(self)

    def reset_selection_state(self):
        """Reset all selection state"""
        self.is_selecting = False
        self.snap_marker.hide()
        if self.plotter_widget.current_segment:
            length = GeometryHelper.calculate_distance(
                self.plotter_widget.current_segment[0], self.plotter_widget.current_segment[1])
            current_unit = self.plotter_widget.unit_combo.currentText()
            display_length = UnitConverter.from_meters(length, current_unit)
            unit_abbrev = UnitConverter.get_abbreviation(current_unit)
            self.plotter_widget.status_label.setText(
                f"Segment selected. Length: {display_length:.3f} {unit_abbrev}"
            )
        else:
            self.plotter_widget.status_label.setText(
                "Click 'Select Segment' to start.")
        self.plotter_widget.select_segment_button.setEnabled(True)
        self.plotter_widget.select_segment_button.setText("Select Segment")
        self.canvas.refresh()

    def _get_feature_from_snap(self, match):
        """Get feature from snap match"""
        layer = match.layer()
        if not layer or not isinstance(layer, QgsVectorLayer) or layer.geometryType() != QgsWkbTypes.LineGeometry:
            return None
        feature = layer.getFeature(match.featureId())
        if not feature.isValid():
            return None
        return layer, feature, match.point()

    def _find_feature_at_point(self, point):
        """Find line feature at given point when snapping is off"""
        tolerance = 10  # Pixel tolerance for selection
        rect = QgsRectangle(
            point.x() - tolerance, point.y() - tolerance,
            point.x() + tolerance, point.y() + tolerance
        )

        for layer in QgsProject.instance().mapLayers().values():
            if not (layer.type() == QgsMapLayer.VectorLayer and
                    layer.geometryType() == QgsWkbTypes.LineGeometry):
                continue

            layer.selectByRect(rect)
            selected_features = list(layer.selectedFeatures())
            layer.removeSelection()

            if not selected_features:
                continue

            feature = selected_features[0]
            geom = feature.geometry()
            dist_sq, closest_point, next_v, _ = geom.closestSegmentWithContext(
                point, 1e-8)
            if dist_sq < (tolerance * self.canvas.mapUnitsPerPixel()) ** 2:
                return layer, feature, closest_point

        return None

    def _find_closest_segment(self, geom, snapped_xy):
        """Find the closest line segment to the snapped point"""
        try:
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

        except Exception:
            return None, None

    def isActive(self):
        """Check if tool is active"""
        return self.is_active

    def isSelecting(self):
        """Check if currently selecting"""
        return self.is_selecting


# ==============================================================================
# PLOTTER WIDGET
# ==============================================================================


class PlotterWidget(QWidget):
    def __init__(self, parent=None):
        super(PlotterWidget, self).__init__(parent)
        self.setWindowTitle('Plotter')
        self.setGeometry(50, 550, 200, 200)
        self.setMinimumWidth(220)

        self.endpoint_manager = LineEndpointManager()
        self.segment_tool = SegmentSelectTool(iface.mapCanvas(), self)
        self.current_layer = None
        self.current_segment = None
        self.points_drawn = False
        self.setup_ui()

    def setup_ui(self):
        """Setup user interface"""
        layout = QVBoxLayout()

        # Status Label
        self.status_label = QLabel("Click 'Select Segment' to start.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "QLabel { color: blue; font-weight: bold; padding: 5px; }")
        layout.addWidget(self.status_label)

        # Select Segment Button
        self.select_segment_button = QPushButton("Select Segment")
        self.select_segment_button.clicked.connect(
            self.start_segment_selection)
        layout.addWidget(self.select_segment_button)

        # Clear Segment Button
        self.clear_segment_button = QPushButton("Clear Segment")
        self.clear_segment_button.clicked.connect(self.clear_segment)
        self.clear_segment_button.setEnabled(False)
        layout.addWidget(self.clear_segment_button)

        # Unit Selection
        layout.addWidget(QLabel("Units:"))
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(list(UNIT_CONVERSIONS.keys()))
        self.unit_combo.setCurrentIndex(0)
        layout.addWidget(self.unit_combo)

        # Point Selection
        layout.addWidget(QLabel("Choose Point:"))
        self.point_combo = QComboBox()
        self.point_combo.addItems(["🟢 Start Point", "🔴 End Point"])
        self.point_combo.setCurrentIndex(0)
        layout.addWidget(self.point_combo)

        # Cut Point Length
        layout.addWidget(QLabel("Cut Point Length:"))
        self.cut_point_input = QDoubleSpinBox()
        self.cut_point_input.setDecimals(3)
        self.cut_point_input.setRange(-1000000, 1000000)
        self.cut_point_input.setValue(0.0)
        layout.addWidget(self.cut_point_input)

        # Offset Length
        layout.addWidget(QLabel("Offset Length:"))
        self.offset_input = QDoubleSpinBox()
        self.offset_input.setDecimals(3)
        self.offset_input.setRange(-1000000, 1000000)
        self.offset_input.setValue(0.0)
        layout.addWidget(self.offset_input)

        # Plot Button
        self.plot_button = QPushButton("Plot")
        self.plot_button.clicked.connect(self.plot)
        layout.addWidget(self.plot_button)

        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setLayout(layout)

    def start_segment_selection(self):
        """Activate the segment selection tool"""
        # Clear any previous selection
        self.clear_segment()

        # Activate tool
        self.status_label.setText("Click on a line segment on the canvas.")
        iface.mapCanvas().setMapTool(self.segment_tool)

        # Disable button during selection
        self.select_segment_button.setEnabled(False)
        self.select_segment_button.setText("Selecting...")

        # Bring widget to front
        self.activateWindow()
        self.raise_()

    def set_selected_segment(self, layer, start_pt, end_pt):
        """Set the selected segment"""
        self.current_layer = layer
        self.current_segment = [start_pt, end_pt]

        length = GeometryHelper.calculate_distance(start_pt, end_pt)
        current_unit = self.unit_combo.currentText()
        display_length = UnitConverter.from_meters(length, current_unit)
        unit_abbrev = UnitConverter.get_abbreviation(current_unit)

        self.status_label.setText(
            f"Segment selected. Length: {display_length:.3f} {unit_abbrev}")
        self.endpoint_manager.display_segment_endpoints(start_pt, end_pt)
        self.clear_segment_button.setEnabled(True)
        self.plot_button.setEnabled(True)

        # Re-enable select button for new selection
        self.select_segment_button.setEnabled(True)
        self.select_segment_button.setText("Select Segment")

        self.activateWindow()
        self.raise_()

    def clear_segment(self):
        """Clear the selected segment"""
        self.current_layer = None
        self.current_segment = None
        self.plot_button.setEnabled(False)

        self.status_label.setText("Click 'Select Segment' to start.")
        self.endpoint_manager.clear_display()
        self.clear_segment_button.setEnabled(False)

        # Deactivate tool if active
        if iface.mapCanvas().mapTool() == self.segment_tool:
            self.segment_tool.deactivate()
            iface.mapCanvas().unsetMapTool(self.segment_tool)

        iface.mapCanvas().refresh()

    def activate(self):
        """Activate the plotter widget"""
        if self.endpoint_manager:
            self.endpoint_manager.activate()

    def deactivate(self):
        """Deactivate the plotter widget"""
        # Force unset the tool if it's active
        if iface.mapCanvas().mapTool() == self.segment_tool:
            self.segment_tool.deactivate()
            iface.mapCanvas().unsetMapTool(self.segment_tool)

        if self.endpoint_manager:
            self.endpoint_manager.deactivate()

    def plot(self):
        """Plot cut point and offset point"""
        try:
            if self.current_segment is None:
                QMessageBox.critical(
                    self, "Error", "Please select a segment first.")
                return

            # Get or create point layer
            point_layer = LayerManager.get_or_create_layer(
                "Plotted Points",
                QgsWkbTypes.GeometryType.PointGeometry,
                self.current_layer.crs(),
                [QgsField("Type", QVariant.String)]
            )

            # Apply symbology
            LayerManager.apply_categorized_symbology(
                point_layer, POINT_CATEGORIES)

            # Start editing
            point_layer.startEditing()

            # Convert to meters
            current_unit = self.unit_combo.currentText()
            offset_meters = UnitConverter.to_meters(
                self.offset_input.value(), current_unit)
            cut_point_meters = UnitConverter.to_meters(
                self.cut_point_input.value(), current_unit)

            start_end_choice_index = self.point_combo.currentIndex()

            # Process the selected segment
            self._process_line_part(
                self.current_segment, point_layer, cut_point_meters,
                offset_meters, start_end_choice_index
            )

            # Commit changes
            if not point_layer.commitChanges():
                errors = point_layer.commitErrors()
                QMessageBox.warning(
                    self, "Warning", f"Some points may not have been saved: {errors}")

            # Force extent update
            LayerManager.update_layer_extent(point_layer)

            self.points_drawn = True

        except Exception as e:
            QMessageBox.critical(self, "Unexpected Error",
                                 f"An unexpected error occurred: {e}")

    def _process_line_part(self, part, point_layer, cut_point_meters,
                           offset_meters, start_end_choice_index):
        """Process a single line part"""
        start_point = QgsPointXY(part[0])
        end_point = QgsPointXY(part[-1])

        # Select base point and direction
        if start_end_choice_index == 0:
            base_point = start_point
            direction_point = part[1] if len(part) > 1 else None
        else:  # End Point
            base_point = end_point
            direction_point = part[-2] if len(part) > 1 else None

        line_length = QgsGeometry.fromPolylineXY(part).length()

        # Handle negative or excessive cut point
        if cut_point_meters < 0 or cut_point_meters > line_length:
            self._handle_extended_point(
                base_point, direction_point, cut_point_meters,
                offset_meters, part, start_end_choice_index, point_layer
            )
        else:
            # Normal cut point
            self._handle_normal_cut_point(
                part, cut_point_meters, offset_meters,
                start_end_choice_index, point_layer
            )

    def _handle_extended_point(self, base_point, direction_point, cut_point_meters,
                               offset_meters, part, start_end_choice_index, point_layer):
        """Handle extended point beyond line"""
        if not direction_point:
            return

        dx = base_point.x() - direction_point.x() if cut_point_meters < 0 else \
            direction_point.x() - base_point.x()
        dy = base_point.y() - direction_point.y() if cut_point_meters < 0 else \
            direction_point.y() - base_point.y()

        direction_length = math.sqrt(dx**2 + dy**2)

        if direction_length == 0:
            QMessageBox.warning(self, "Warning",
                                "Direction vector has zero length, cannot extend line.")
            return

        # Normalize and extend
        unit_dx = dx / direction_length
        unit_dy = dy / direction_length

        extension_distance = abs(cut_point_meters)
        extended_point = QgsPointXY(
            base_point.x() + unit_dx * extension_distance,
            base_point.y() + unit_dy * extension_distance
        )

        # Add extended point
        point_type = "Bisect Point" if offset_meters == 0 else "Extended Point"
        self._add_point(point_layer, extended_point, point_type)

        # Calculate offset for extended point
        if offset_meters != 0 and len(part) > 1:
            offset_point = self._calculate_offset_point(
                extended_point, part, start_end_choice_index, offset_meters
            )
            if offset_point:
                self._add_point(point_layer, offset_point, "Offset Point")

    def _handle_normal_cut_point(self, part, cut_point_meters, offset_meters,
                                 start_end_choice_index, point_layer):
        """Handle normal cut point within line"""
        if start_end_choice_index == 0:
            cut_point_geom = QgsGeometry.fromPolylineXY(
                part).interpolate(cut_point_meters)
        else:  # End Point
            reversed_geom = QgsGeometry.fromPolylineXY(part[::-1])
            cut_point_geom = reversed_geom.interpolate(cut_point_meters)

        if cut_point_geom.isNull():
            return

        cut_point = cut_point_geom.asPoint()
        point_type = "Bisect Point" if offset_meters == 0 else "Cut Point"
        self._add_point(point_layer, cut_point, point_type)

        # Calculate offset
        if offset_meters != 0 and len(part) > 1:
            offset_point = self._calculate_offset_point(
                cut_point, part, start_end_choice_index, offset_meters
            )
            if offset_point:
                self._add_point(point_layer, offset_point, "Offset Point")

    def _calculate_offset_point(self, base_point, part, start_end_choice_index, offset_meters):
        """Calculate offset point perpendicular to line"""
        if start_end_choice_index == 0:
            dx = part[1].x() - part[0].x()
            dy = part[1].y() - part[0].y()
        else:  # End Point
            dx = part[-2].x() - part[-1].x()
            dy = part[-2].y() - part[-1].y()

        length = math.sqrt(dx**2 + dy**2)

        if length == 0:
            QMessageBox.warning(self, "Warning",
                                "Line segment has zero length, cannot calculate offset.")
            return None

        # Perpendicular vector
        perp_dx = -dy / length
        perp_dy = dx / length

        return QgsPointXY(
            base_point.x() + perp_dx * offset_meters,
            base_point.y() + perp_dy * offset_meters
        )

    def _add_point(self, layer, point, point_type):
        """Add a point feature to the layer"""
        feature = QgsFeature(layer.fields())
        geom = QgsGeometry.fromPointXY(point)

        # Validate geometry
        if not geom.isNull() and geom.isGeosValid():
            feature.setGeometry(geom)
            feature.setAttributes([point_type])
            success = layer.addFeature(feature)
            return success
        return False

    def cleanup(self):
        """Clean up resources"""
        try:
            # Force deactivate tool
            if iface.mapCanvas().mapTool() == self.segment_tool:
                self.segment_tool.deactivate()
                iface.mapCanvas().unsetMapTool(self.segment_tool)

            if hasattr(self, 'endpoint_manager'):
                self.endpoint_manager.cleanup()
        except Exception:
            pass


# ==============================================================================
# COMBINED MAIN WIDGET
# ==============================================================================

class CombinedMainWidget(QWidget):
    def __init__(self, parent=iface.mainWindow()):
        super().__init__(parent)
        self.setWindowTitle('Plotter')
        self.setGeometry(900, 250, 250, 350)
        self.setWindowFlags(TOOL_WINDOW_FLAGS)

        # Create tab widget
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
        """Handle widget show event"""
        super().showEvent(event)
        current_widget = self.tab_widget.currentWidget()
        if hasattr(current_widget, 'activate'):
            current_widget.activate()
        self.has_been_activated = True

    def on_tab_changed(self, index):
        """Handle tab changes"""
        if not self.has_been_activated:
            return

        try:
            # Deactivate all tools and widgets
            if hasattr(self.triangle_widget, 'deactivate'):
                self.triangle_widget.deactivate()
            if hasattr(self.plotter_widget, 'deactivate'):
                self.plotter_widget.deactivate()

            # Deactivate any active map tools
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

            # Update triangle preview if switching to triangle tab
            if (current_widget == self.triangle_widget and
                    hasattr(self.triangle_widget, 'schedule_preview_update')):
                self.triangle_widget.schedule_preview_update()

            iface.mapCanvas().refresh()

        except Exception:
            pass

    def closeEvent(self, event):
        """Handle widget close event"""
        try:
            # Check if triangle lines need saving
            if self.triangle_widget.lines_drawn:
                line_layer = None
                for lyr in QgsProject.instance().mapLayers().values():
                    if lyr.name() == "Triangle Lines" and lyr.geometryType() == QgsWkbTypes.GeometryType.LineGeometry:
                        line_layer = lyr
                        break

                if line_layer and line_layer.providerType() == "memory":
                    reply = QMessageBox.question(
                        self, 'Save Triangle Lines',
                        "Do you want to save the Triangle Lines Layer before closing?",
                        QMessageBox.StandardButton.Yes |
                        QMessageBox.StandardButton.No |
                        QMessageBox.StandardButton.Cancel,
                        QMessageBox.StandardButton.Cancel
                    )

                    if reply == QMessageBox.StandardButton.Yes:
                        saved = LayerManager.save_temp_layer(self, line_layer)
                        if not saved:
                            event.ignore()
                            return
                    elif reply == QMessageBox.StandardButton.Cancel:
                        event.ignore()
                        return

            # Check if plotted points need saving
            if self.plotter_widget.points_drawn:
                point_layer = None
                for lyr in QgsProject.instance().mapLayers().values():
                    if lyr.name() == "Plotted Points" and lyr.geometryType() == QgsWkbTypes.GeometryType.PointGeometry:
                        point_layer = lyr
                        break

                if point_layer and point_layer.providerType() == "memory":
                    reply = QMessageBox.question(
                        self, 'Save Plotted Points',
                        "Do you want to save the Plotted Points Layer before closing?",
                        QMessageBox.StandardButton.Yes |
                        QMessageBox.StandardButton.No |
                        QMessageBox.StandardButton.Cancel,
                        QMessageBox.StandardButton.Cancel
                    )

                    if reply == QMessageBox.StandardButton.Yes:
                        saved = LayerManager.save_temp_layer(self, point_layer)
                        if not saved:
                            event.ignore()
                            return
                    elif reply == QMessageBox.StandardButton.Cancel:
                        event.ignore()
                        return

            # Clean up both widgets and their tools
            current_tool = iface.mapCanvas().mapTool()
            if current_tool == self.triangle_widget.point_tool:
                self.triangle_widget.point_tool.deactivate()
                iface.mapCanvas().unsetMapTool(self.triangle_widget.point_tool)
            elif current_tool == self.plotter_widget.segment_tool:
                self.plotter_widget.segment_tool.deactivate()
                iface.mapCanvas().unsetMapTool(self.plotter_widget.segment_tool)

            if hasattr(self, 'triangle_widget'):
                self.triangle_widget.cleanup()
            if hasattr(self, 'plotter_widget'):
                self.plotter_widget.cleanup()

            iface.mapCanvas().refresh()

        except Exception:
            pass

        event.accept()


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

# Create and show the main widget
main_widget = CombinedMainWidget()
# main_widget.show()

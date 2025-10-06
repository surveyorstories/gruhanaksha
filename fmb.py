import math
from qgis.PyQt.QtCore import QTimer, Qt
from qgis.PyQt.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                 QPushButton, QDoubleSpinBox, QComboBox,
                                 QTabWidget, QMessageBox, QFileDialog)
from qgis.PyQt.QtGui import QColor, QIcon, QCursor
from qgis.gui import QgsRubberBand, QgsVertexMarker, QgsMapTool
from qgis.core import (QgsWkbTypes, QgsPointXY, QgsGeometry,
                       QgsVectorLayer, QgsField, QgsFeature, QgsProject,
                       QgsMarkerSymbol, QgsRendererCategory, QgsCategorizedSymbolRenderer,
                       QgsVectorFileWriter)
from qgis.utils import iface
from qgis.PyQt.QtCore import QVariant

# make top level widget
from .addon_functions import TOOL_WINDOW_FLAGS, STAY_ON_TOP_FLAG


def save_temp_layer(parent, layer):
    """Save or update the layer, maintaining the same name."""
    try:
        # Check if the layer is temporary (memory layer)
        if layer.providerType() == "memory":
            # Prompt the user to save the layer to disk
            file_path, _ = QFileDialog.getSaveFileName(
                parent, f"Save {layer.name()}", layer.name(),
                "ESRI Shapefile (*.shp);;GeoJSON (*.geojson);;GPKG (*.gpkg)"
            )
            if not file_path:
                return False  # User canceled the dialog

            # Determine the file format from the file extension
            if file_path.endswith(".shp"):
                format_name = "ESRI Shapefile"
            elif file_path.endswith(".geojson"):
                format_name = "GeoJSON"
            elif file_path.endswith(".gpkg"):
                format_name = "GPKG"
            else:
                QMessageBox.critical(
                    parent, "Error", "Unsupported file format.")
                return False

            # Set up save options
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = format_name
            options.fileEncoding = "UTF-8"

            # Save the layer
            error = QgsVectorFileWriter.writeAsVectorFormatV3(
                layer, file_path, QgsProject.instance().transformContext(), options
            )

            if error[0] == QgsVectorFileWriter.WriterError.NoError:
                QMessageBox.information(
                    parent, "Save Successful", f"Layer saved successfully at {file_path}!"
                )
                # Reload the saved layer and keep the same name
                new_layer = QgsVectorLayer(
                    file_path, layer.name(), "ogr")
                if new_layer.isValid():
                    # Preserve the existing symbology
                    new_layer.setRenderer(layer.renderer().clone())
                    QgsProject.instance().addMapLayer(new_layer)
                    QgsProject.instance().removeMapLayer(layer.id())
                    return True
                else:
                    QMessageBox.warning(
                        parent, "Warning", "Failed to reload the saved layer into the project."
                    )
                    return False
            else:
                QMessageBox.critical(
                    parent, "Save Error", f"Error saving layer. Error code: {error[0]}"
                )
                return False

    except Exception as e:
        QMessageBox.critical(parent, "Unexpected Error",
                             f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        return False


categories_info = [
    {'name': 'Cut Point', 'color': 'orange', 'size': 2, 'opacity': 1},
    {'name': "Offset Point", 'color': 'blue', 'size': 2, 'opacity': 1},
    {'name': "Extended Point", 'color': 'purple', 'size': 2, 'opacity': 1},
]


def apply_categorized_symbology(layer, categories_info=categories_info):
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


class LineEndpointManager:
    """Manages the display of line start and end points using vertex markers"""

    def __init__(self):
        self.map_canvas = iface.mapCanvas()
        self.current_layer = None
        self.is_active = False  # Track activation state

        # Initialize vertex markers for start/end points
        self.start_point_marker = None
        self.end_point_marker = None

        # Don't initialize connections here - wait for activation

    def activate(self):
        """Activate the endpoint manager - connect signals and initialize display"""
        if self.is_active:
            return

        self.is_active = True

        # Connect to layer changes
        try:
            iface.layerTreeView().currentLayerChanged.connect(self.on_layer_changed)
        except Exception as e:
            print(f"Error connecting layer change signal: {e}")

        # Initialize with current layer
        current_layer = iface.activeLayer()
        if current_layer:
            self.on_layer_changed(current_layer)

    def deactivate(self):
        """Deactivate the endpoint manager - disconnect signals and clear display"""
        if not self.is_active:
            return

        self.is_active = False

        # Disconnect signals
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

        # Clear display
        self.clear_display()
        self.current_layer = None

    def create_start_marker(self, point):
        """Create a filled green start point marker"""
        if self.start_point_marker:
            self.map_canvas.scene().removeItem(self.start_point_marker)

        self.start_point_marker = QgsVertexMarker(self.map_canvas)
        self.start_point_marker.setCenter(point)
        self.start_point_marker.setColor(QColor(0, 0, 0))  # Bright Green
        self.start_point_marker.setFillColor(
            QColor(0, 255, 0, 200))  # Filled green
        self.start_point_marker.setIconSize(9)
        self.start_point_marker.setIconType(
            QgsVertexMarker.IconType.ICON_CIRCLE)
        self.start_point_marker.setPenWidth(1)

    def create_end_marker(self, point):
        """Create a filled red end point marker"""
        if self.end_point_marker:
            self.map_canvas.scene().removeItem(self.end_point_marker)

        self.end_point_marker = QgsVertexMarker(self.map_canvas)
        self.end_point_marker.setCenter(point)
        self.end_point_marker.setColor(QColor(0, 0, 0))  # Bright Red
        self.end_point_marker.setFillColor(
            QColor(255, 0, 0, 200))  # Filled red
        self.end_point_marker.setIconSize(9)
        self.end_point_marker.setIconType(QgsVertexMarker.IconType.ICON_CIRCLE)
        self.end_point_marker.setPenWidth(1)

    def on_layer_changed(self, layer):
        """Handle layer change to update start/end points display"""
        if not self.is_active:
            return

        # Disconnect previous layer's selection changed signal
        if self.current_layer:
            try:
                self.current_layer.selectionChanged.disconnect(
                    self.update_display)
            except (TypeError, AttributeError):
                pass

        self.current_layer = layer

        # Clear display first
        self.clear_display()

        if layer and hasattr(layer, 'wkbType') and layer.wkbType() in [QgsWkbTypes.Type.LineString, QgsWkbTypes.Type.MultiLineString]:
            try:
                layer.selectionChanged.connect(self.update_display)
                self.update_display()
            except Exception as e:
                print(f"Error connecting selection changed signal: {e}")

    def update_display(self):
        """Update start and end points display when selection changes"""
        if not self.is_active:
            return

        # Always clear first
        self.clear_display()

        if not self.current_layer or not hasattr(self.current_layer, 'wkbType'):
            return

        if self.current_layer.wkbType() not in [QgsWkbTypes.Type.LineString, QgsWkbTypes.Type.MultiLineString]:
            return

        try:
            selected_features = list(self.current_layer.selectedFeatures())
            if len(selected_features) != 1:
                return

            feature = selected_features[0]
            geom = feature.geometry()
            if not geom or geom.isNull():
                return

            # Extract start and end points
            start_point, end_point = self.get_line_endpoints(geom)
            if start_point and end_point:
                print(
                    f"Creating markers at start: {start_point.x()}, {start_point.y()}")
                print(
                    f"Creating markers at end: {end_point.x()}, {end_point.y()}")

                # Create vertex markers
                self.create_start_marker(start_point)
                self.create_end_marker(end_point)

                # Force canvas refresh
                self.map_canvas.refresh()

                print("Vertex markers should now be visible")

        except Exception as e:
            print(f"Error updating display: {e}")
            import traceback
            traceback.print_exc()

    def get_line_endpoints(self, geometry):
        """Extract start and end points from line geometry"""
        try:
            if geometry.isMultipart():
                points = geometry.asMultiPolyline()
                if points and len(points) > 0 and len(points[0]) > 0:
                    start_point = QgsPointXY(points[0][0])
                    end_point = QgsPointXY(points[-1][-1])
                    return start_point, end_point
            else:
                points = geometry.asPolyline()
                if points and len(points) > 0:
                    start_point = QgsPointXY(points[0])
                    end_point = QgsPointXY(points[-1])
                    return start_point, end_point
        except Exception as e:
            print(f"Error extracting endpoints: {e}")
        return None, None

    def clear_display(self):
        """Clear start and end points display"""
        try:
            if self.start_point_marker:
                self.map_canvas.scene().removeItem(self.start_point_marker)
                self.start_point_marker = None

            if self.end_point_marker:
                self.map_canvas.scene().removeItem(self.end_point_marker)
                self.end_point_marker = None

        except Exception as e:
            print(f"Error clearing display: {e}")

    def cleanup(self):
        """Clean up markers and disconnect signals"""
        self.deactivate()

        # Force canvas refresh
        try:
            self.map_canvas.refresh()
        except Exception as e:
            print(f"Error refreshing canvas during cleanup: {e}")


class TrianglePointTool(QgsMapTool):
    """Map tool for clicking two points on the canvas"""

    def __init__(self, canvas, triangle_widget):
        super().__init__(canvas)
        self.canvas = canvas
        self.triangle_widget = triangle_widget
        self.points = []
        self.markers = []
        self.temp_line = QgsRubberBand(
            canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.temp_line.setColor(QColor(0, 255, 0, 150))
        self.temp_line.setWidth(2)
        self.setCursor(Qt.CursorShape.CrossCursor)

        # Get snapping utils from canvas
        self.snapping_utils = canvas.snappingUtils()

        # Create snap marker
        self.snap_marker = QgsVertexMarker(self.canvas)
        self.snap_marker.setIconType(QgsVertexMarker.ICON_CROSS)
        self.snap_marker.setColor(QColor(255, 0, 255))
        self.snap_marker.setPenWidth(3)
        self.snap_marker.setIconSize(12)
        self.snap_marker.hide()

    def canvasMoveEvent(self, event):
        """Show snap marker when hovering over snap points"""
        match = self.snapping_utils.snapToMap(event.pos())

        if match.isValid():
            # Show snap marker at snapped location
            self.snap_marker.setCenter(match.point())
            self.snap_marker.show()
        else:
            # Hide snap marker when not snapping
            self.snap_marker.hide()

    def canvasPressEvent(self, event):
        """Handle mouse click on canvas"""
        # Get point with snapping
        match = self.snapping_utils.snapToMap(event.pos())

        if match.isValid():
            # Use snapped point
            point = match.point()
        else:
            # Use clicked point without snapping
            point = self.toMapCoordinates(event.pos())

        if len(self.points) < 2:
            self.points.append(point)

            # Create marker for clicked point
            marker = QgsVertexMarker(self.canvas)
            marker.setCenter(point)

            # First point: Green, Second point: Red
            if len(self.points) == 1:
                marker.setColor(QColor(0, 255, 0))  # Green for first point
                marker.setFillColor(QColor(0, 255, 0, 200))
            else:
                marker.setColor(QColor(255, 0, 0))  # Red for second point
                marker.setFillColor(QColor(255, 0, 0, 200))

            marker.setIconSize(12)
            marker.setIconType(QgsVertexMarker.IconType.ICON_CIRCLE)
            marker.setPenWidth(2)
            self.markers.append(marker)

            if len(self.points) == 1:
                self.triangle_widget.status_label.setText("Click second point")
            elif len(self.points) == 2:
                # Draw temporary line between points
                self.temp_line.reset()
                self.temp_line.addPoint(self.points[0], False)
                self.temp_line.addPoint(self.points[1], True)

                self.triangle_widget.status_label.setText(
                    "Two points selected. Ready to draw triangle.")
                self.triangle_widget.set_points(self.points[0], self.points[1])

                # Hide snap marker after second point
                self.snap_marker.hide()

    def activate(self):
        """Called when tool is activated"""
        super().activate()
        self.canvas.setCursor(Qt.CursorShape.CrossCursor)

    def deactivate(self):
        """Clean up when tool is deactivated"""
        # Hide snap marker
        if hasattr(self, 'snap_marker'):
            self.snap_marker.hide()
        super().deactivate()

    def clear(self):
        """Clear all points and markers"""
        self.points = []

        # Remove markers
        for marker in self.markers:
            self.canvas.scene().removeItem(marker)
        self.markers = []

        # Clear temporary line
        self.temp_line.reset()

        # Hide snap marker
        if hasattr(self, 'snap_marker'):
            self.snap_marker.hide()


class TriangleWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Triangle')
        self.setGeometry(50, 200, 200, 200)
        self.setMinimumWidth(220)

        # Points for triangle base
        self.start_point = None
        self.end_point = None

        # Initialize map tool for point selection
        self.point_tool = TrianglePointTool(iface.mapCanvas(), self)

        # Initialize rubber band for triangle preview
        self.triangle_rubber_band = QgsRubberBand(
            iface.mapCanvas(), QgsWkbTypes.GeometryType.LineGeometry)
        self.triangle_rubber_band.setColor(QColor(255, 0, 0, 150))
        self.triangle_rubber_band.setWidth(3)

        # Timer for live preview
        self.preview_timer = QTimer()
        self.preview_timer.timeout.connect(self.update_triangle_preview)
        self.preview_timer.setSingleShot(True)

        # Status Label
        self.status_label = QLabel("Click 'Select Points' to start")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "QLabel { color: blue; font-weight: bold; }")

        # Select Points Button
        self.select_points_button = QPushButton("Select Points")
        self.select_points_button.clicked.connect(self.start_point_selection)

        # Clear Points Button
        self.clear_points_button = QPushButton("Clear Points")
        self.clear_points_button.clicked.connect(self.clear_points)
        self.clear_points_button.setEnabled(False)

        # Length Inputs
        self.start_length_input = QDoubleSpinBox()
        self.start_length_input.setDecimals(3)
        self.start_length_input.setRange(0, 1000000)
        self.start_length_input.valueChanged.connect(
            self.schedule_preview_update)

        self.end_length_input = QDoubleSpinBox()
        self.end_length_input.setDecimals(3)
        self.end_length_input.setRange(0, 1000000)
        self.end_length_input.valueChanged.connect(
            self.schedule_preview_update)

        # Orientation Combobox
        self.orientation_combo = QComboBox()
        self.orientation_combo.addItems(["Left", "Right"])
        self.orientation_combo.setCurrentIndex(0)
        self.orientation_combo.currentTextChanged.connect(
            self.schedule_preview_update)

        # Unit Selection ComboBox
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["Meters", "Metric Links", "Gunter's Links"])
        self.unit_combo.setCurrentIndex(0)
        self.unit_combo.currentTextChanged.connect(
            self.schedule_preview_update)

        # Draw Button
        self.draw_button = QPushButton("Draw Triangle")
        self.draw_button.clicked.connect(self.draw_triangle)
        self.draw_button.setEnabled(False)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.status_label)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.select_points_button)
        button_layout.addWidget(self.clear_points_button)
        layout.addLayout(button_layout)

        layout.addWidget(QLabel("Start Length:"))
        layout.addWidget(self.start_length_input)
        layout.addWidget(QLabel("End Length:"))
        layout.addWidget(self.end_length_input)
        layout.addWidget(QLabel("Orientation:"))
        layout.addWidget(self.orientation_combo)
        layout.addWidget(QLabel("Units:"))
        layout.addWidget(self.unit_combo)
        layout.addWidget(self.draw_button)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setLayout(layout)

        self.triangle_drawn = False

    def start_point_selection(self):
        """Activate the point selection tool"""
        self.clear_points()
        self.status_label.setText("Click first point on canvas")
        iface.mapCanvas().setMapTool(self.point_tool)
        self.select_points_button.setEnabled(False)
        self.select_points_button.setText("Selecting...")
        # Keep the widget on top and visible
        self.activateWindow()
        self.raise_()

    def set_points(self, start_point, end_point):
        """Set the start and end points for the triangle base"""
        self.start_point = start_point
        self.end_point = end_point
        self.draw_button.setEnabled(True)
        self.clear_points_button.setEnabled(True)
        self.select_points_button.setEnabled(True)
        self.select_points_button.setText("Select Points")
        self.schedule_preview_update()
        # Ensure widget stays visible
        self.activateWindow()
        self.raise_()

    def clear_points(self):
        """Clear selected points and reset"""
        self.start_point = None
        self.end_point = None
        self.point_tool.clear()
        self.triangle_rubber_band.reset()
        self.draw_button.setEnabled(False)
        self.clear_points_button.setEnabled(False)
        self.select_points_button.setEnabled(True)
        self.select_points_button.setText("Select Points")
        self.status_label.setText("Click 'Select Points' to start")
        # Deactivate tool if active
        if iface.mapCanvas().mapTool() == self.point_tool:
            iface.mapCanvas().unsetMapTool(self.point_tool)

    def activate(self):
        """Activate the triangle widget"""
        pass

    def deactivate(self):
        """Deactivate the triangle widget"""
        # Make sure to unset the map tool if it's active
        if iface.mapCanvas().mapTool() == self.point_tool:
            iface.mapCanvas().unsetMapTool(self.point_tool)

    def schedule_preview_update(self):
        """Schedule preview update with a small delay to avoid excessive updates"""
        if self.start_point is None or self.end_point is None:
            return
        self.preview_timer.stop()
        self.preview_timer.start(200)

    def update_triangle_preview(self):
        """Update the rubber band preview of triangle formation"""
        self.triangle_rubber_band.reset()

        if self.start_point is None or self.end_point is None:
            return

        try:
            # Get input values
            start_length = self.convert_length(self.start_length_input.value())
            end_length = self.convert_length(self.end_length_input.value())

            if start_length <= 0 or end_length <= 0:
                return

            # Calculate triangle apex
            apex_point = self.calculate_triangle_apex(
                self.start_point, self.end_point, start_length, end_length)
            if apex_point:
                # Draw preview triangle
                self.triangle_rubber_band.addPoint(self.start_point, False)
                self.triangle_rubber_band.addPoint(apex_point, False)
                self.triangle_rubber_band.addPoint(self.end_point, False)
                self.triangle_rubber_band.addPoint(
                    self.start_point, True)  # Close and update

        except Exception as e:
            print(f"Triangle preview error: {e}")

    def calculate_triangle_apex(self, start_point, end_point, start_length, end_length):
        """Calculate the apex point of the triangle"""
        try:
            dx = end_point.x() - start_point.x()
            dy = end_point.y() - start_point.y()
            base_length = math.sqrt(dx**2 + dy**2)

            if base_length == 0:
                return None

            # Check triangle inequality
            if not (start_length + end_length > base_length and
                    start_length + base_length > end_length and
                    end_length + base_length > start_length):
                return None

            # Normalize direction vector
            ux = dx / base_length
            uy = dy / base_length

            # Determine perpendicular vector based on orientation
            if self.orientation_combo.currentText() == "Right":
                perp_ux = -uy
                perp_uy = ux
            else:  # Left
                perp_ux = uy
                perp_uy = -ux

            # Law of Cosines for angle at start
            angle_start = math.acos(
                (start_length**2 + base_length**2 - end_length**2) / (2 * start_length * base_length))

            # Calculate apex point
            apex_x = start_point.x() + start_length * (ux * math.cos(angle_start) -
                                                       perp_ux * math.sin(angle_start))
            apex_y = start_point.y() + start_length * (uy * math.cos(angle_start) -
                                                       perp_uy * math.sin(angle_start))

            return QgsPointXY(apex_x, apex_y)

        except (ValueError, ZeroDivisionError):
            return None

    def convert_length(self, length):
        """Convert the length to meters based on selected units."""
        unit = self.unit_combo.currentText()
        if unit == "Meters":
            return length
        elif unit == "Metric Links":
            return length * 0.2
        elif unit == "Gunter's Links":
            return length * 0.201168
        else:
            return length

    def draw_triangle(self):
        """Draw a triangle using the clicked points as the base."""
        try:
            if self.start_point is None or self.end_point is None:
                QMessageBox.critical(
                    self, "Error", "Please select two points first.")
                return

            # Get the active layer for CRS reference
            layer = iface.activeLayer()
            if layer is None:
                QMessageBox.critical(
                    self, "Error", "No active layer to determine CRS.")
                return

            # Input lengths
            start_length = self.convert_length(self.start_length_input.value())
            end_length = self.convert_length(self.end_length_input.value())

            # Calculate apex point
            apex_point = self.calculate_triangle_apex(
                self.start_point, self.end_point, start_length, end_length)
            if not apex_point:
                QMessageBox.critical(
                    self, "Error", "Invalid side lengths. Triangle cannot be formed.")
                return

            # Check if a layer named "Triangle Lines" exists
            line_layer_name = "Triangle Lines"
            line_layer = None
            for lyr in QgsProject.instance().mapLayers().values():
                if lyr.name() == line_layer_name and lyr.geometryType() == QgsWkbTypes.GeometryType.LineGeometry:
                    line_layer = lyr
                    break

            # Create a new layer if not found
            if line_layer is None:
                layer_crs = layer.crs()
                line_layer = QgsVectorLayer(
                    f"LineString?crs={layer_crs.toWkt()}", line_layer_name, "memory")
                line_layer.dataProvider().addAttributes(
                    [QgsField("Type", QVariant.String)])
                line_layer.updateFields()
                QgsProject.instance().addMapLayer(line_layer)

            # Add line features for the triangle
            def add_line(start, end, line_type):
                feature = QgsFeature()
                feature.setGeometry(QgsGeometry.fromPolylineXY([start, end]))
                feature.setAttributes([line_type])
                line_layer.dataProvider().addFeature(feature)

            # Draw the three sides of the triangle
            add_line(self.start_point, apex_point, "Start Side")
            add_line(self.end_point, apex_point, "End Side")
            add_line(self.start_point, self.end_point, "Base Line")

            line_layer.triggerRepaint()
            iface.setActiveLayer(layer)

            # Clear the rubber band preview
            self.triangle_rubber_band.reset()

            QMessageBox.information(
                self, "Success", "Triangle drawn successfully!")
            self.triangle_drawn = True

            # Clear points after drawing
            self.clear_points()

        except Exception as e:
            QMessageBox.critical(self, "Unexpected Error",
                                 f"An unexpected error occurred: {e}")
            import traceback
            traceback.print_exc()

    def cleanup(self):
        """Clean up rubber bands and disconnect signals"""
        try:
            # Unset map tool if active
            if iface.mapCanvas().mapTool() == self.point_tool:
                iface.mapCanvas().unsetMapTool(self.point_tool)

            # Clear point tool
            if hasattr(self, 'point_tool'):
                self.point_tool.clear()

            # Clear triangle rubber band
            if hasattr(self, 'triangle_rubber_band'):
                self.triangle_rubber_band.reset()

            # Stop timer
            if hasattr(self, 'preview_timer'):
                self.preview_timer.stop()

        except Exception as e:
            print(f"Triangle cleanup error: {e}")


class PlotterWidget(QWidget):
    def __init__(self, parent=None):
        super(PlotterWidget, self).__init__(parent)
        self.setWindowTitle('Plotter')
        self.setGeometry(50, 550, 200, 200)
        self.setMinimumWidth(220)

        # Initialize endpoint manager but don't activate it yet
        self.endpoint_manager = LineEndpointManager()

        # Offset and Cut Point Inputs
        self.offset_input = QDoubleSpinBox()
        self.offset_input.setDecimals(3)
        self.offset_input.setRange(-1000000, 1000000)
        self.offset_input.setValue(0.0)

        self.cut_point_input = QDoubleSpinBox()
        self.cut_point_input.setDecimals(3)
        self.cut_point_input.setRange(-1000000, 1000000)
        self.cut_point_input.setValue(0.0)

        # Units Combo Box
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["Meters", "Metric Links", "Gunter's Links"])
        self.unit_combo.setCurrentIndex(0)

        # Choose Point Combo Box (Start or End)
        self.point_combo = QComboBox()
        self.point_combo.addItems(["Start Point", "End Point"])
        self.point_combo.setCurrentIndex(0)

        # Plot Button
        self.plot_button = QPushButton("Plot")
        self.plot_button.clicked.connect(self.plot)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Units:"))
        layout.addWidget(self.unit_combo)
        layout.addWidget(QLabel("Choose Point:"))
        layout.addWidget(self.point_combo)
        layout.addWidget(QLabel("Cut Point Length:"))
        layout.addWidget(self.cut_point_input)
        layout.addWidget(QLabel("Offset Length:"))
        layout.addWidget(self.offset_input)
        layout.addWidget(self.plot_button)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setLayout(layout)

        self.points_drawn = False

    def activate(self):
        """Activate the plotter widget and its endpoint manager"""
        if self.endpoint_manager:
            self.endpoint_manager.activate()

    def deactivate(self):
        """Deactivate the plotter widget and its endpoint manager"""
        if self.endpoint_manager:
            self.endpoint_manager.deactivate()

    def convert_length(self, length):
        """Convert the length to meters based on selected units."""
        unit = self.unit_combo.currentText()
        if unit == "Meters":
            return length
        elif unit == "Metric Links":
            return length * 0.2
        elif unit == "Gunter's Links":
            return length * 0.201168
        else:
            return length

    def plot(self):
        """Plot the cut point and offset point based on the selected line."""
        try:
            # Get the active layer
            layer = iface.activeLayer()
            if layer is None:
                QMessageBox.critical(self, "Error", "Please select a layer.")
                return

            if layer.wkbType() not in [QgsWkbTypes.Type.LineString, QgsWkbTypes.Type.MultiLineString]:
                QMessageBox.critical(
                    self, "Error", "The selected layer is not a line layer.")
                return

            selected_features = list(layer.selectedFeatures())
            if len(selected_features) != 1:
                QMessageBox.critical(
                    self, "Error", "Please select exactly one line feature.")
                return

            feature = selected_features[0]
            geom = feature.geometry()

            if geom is None or geom.isNull():
                QMessageBox.critical(
                    self, "Error", "Selected feature has no geometry.")
                return

            offset_input = self.offset_input.value()
            cut_point_input = self.cut_point_input.value()

            # Convert units to meters
            offset_meters = self.convert_length(offset_input)
            cut_point_meters = self.convert_length(cut_point_input)

            # Choose starting point based on user's selection
            start_end_choice = self.point_combo.currentText()

            # Prepare or fetch the point layer
            point_layer_name = "Plotted Points"
            existing_layer = None
            for lyr in QgsProject.instance().mapLayers().values():
                if lyr.name() == point_layer_name and lyr.geometryType() == QgsWkbTypes.GeometryType.PointGeometry:
                    existing_layer = lyr
                    break

            if existing_layer:
                point_layer = existing_layer
            else:
                point_layer = QgsVectorLayer(
                    f"Point?crs={layer.crs().toWkt()}", point_layer_name, "memory")
                point_layer.dataProvider().addAttributes(
                    [QgsField("Type", QVariant.String)])
                point_layer.updateFields()
                QgsProject.instance().addMapLayer(point_layer)

            # Apply Categorized Symbology to the point layer
            apply_categorized_symbology(point_layer, categories_info)

            def add_point(point, point_type):
                """Add a point feature to the point layer."""
                feature = QgsFeature()
                feature.setGeometry(QgsGeometry.fromPointXY(point))
                feature.setAttributes([point_type])
                point_layer.dataProvider().addFeature(feature)

            # Handle MultiLineString geometry by breaking it into single parts
            if geom.isMultipart():
                single_parts = geom.asMultiPolyline()
            else:
                single_parts = [geom.asPolyline()]

            for part in single_parts:
                if not part:
                    QMessageBox.warning(
                        self, "Warning", "A part of the geometry is empty. Skipping.")
                    continue

                # Start Point and End Point
                start_point = QgsPointXY(part[0])
                end_point = QgsPointXY(part[-1])

                # Correct point selection based on user choice (Start or End)
                if start_end_choice == "Start Point":
                    base_point = start_point
                    direction_point = part[1] if len(part) > 1 else None
                elif start_end_choice == "End Point":
                    base_point = end_point
                    direction_point = part[-2] if len(part) > 1 else None

                # If the line length is less than the cut point length, extend the line
                line_length = QgsGeometry.fromPolylineXY(part).length()
                if cut_point_meters < 0:
                    # If the cut point length is negative, extend the line backward
                    if direction_point:
                        dx = base_point.x() - direction_point.x()
                        dy = base_point.y() - direction_point.y()
                        direction_length = (dx**2 + dy**2)**0.5

                        if direction_length != 0:
                            # Normalize the direction vector and extend it backward
                            unit_dx = dx / direction_length
                            unit_dy = dy / direction_length

                            # Extended point coordinates (backward extension)
                            extended_x = base_point.x() + unit_dx * abs(cut_point_meters)
                            extended_y = base_point.y() + unit_dy * abs(cut_point_meters)
                            extended_point = QgsPointXY(extended_x, extended_y)

                            # Add the extended point
                            add_point(extended_point, "Extended Point")

                            # Now calculate the offset for the extended point
                            if len(part) > 1:
                                # Calculate direction vector based on chosen point
                                if start_end_choice == "Start Point":
                                    dx = part[1].x() - part[0].x()
                                    dy = part[1].y() - part[0].y()
                                elif start_end_choice == "End Point":
                                    # Use last two points to calculate direction vector
                                    dx = part[-2].x() - part[-1].x()
                                    dy = part[-2].y() - part[-1].y()

                                length = (dx**2 + dy**2)**0.5

                                # Normalize direction vector and find perpendicular offset vector
                                if length == 0:
                                    QMessageBox.warning(
                                        self, "Warning", "Line segment has zero length, cannot calculate offset.")
                                    continue
                                perp_dx = -dy / length
                                perp_dy = dx / length

                                # Offset for the extended point
                                offset_x = extended_point.x() + perp_dx * offset_meters
                                offset_y = extended_point.y() + perp_dy * offset_meters
                                offset_point = QgsPointXY(offset_x, offset_y)

                                add_point(offset_point, "Offset Point")

                elif cut_point_meters > line_length and direction_point:
                    dx = direction_point.x() - base_point.x()
                    dy = direction_point.y() - base_point.y()
                    direction_length = (dx**2 + dy**2)**0.5

                    if direction_length != 0:
                        # Normalize the direction vector
                        unit_dx = dx / direction_length
                        unit_dy = dy / direction_length

                        # Calculate extension distance (beyond existing line)
                        extension_distance = cut_point_meters

                        # Extended point coordinates
                        extended_x = base_point.x() + unit_dx * extension_distance
                        extended_y = base_point.y() + unit_dy * extension_distance
                        extended_point = QgsPointXY(extended_x, extended_y)

                        # Add the extended point
                        add_point(extended_point, "Extended Point")

                        # Now calculate the offset for the extended point
                        if len(part) > 1:
                            # Calculate direction vector based on chosen point
                            if start_end_choice == "Start Point":
                                dx = part[1].x() - part[0].x()
                                dy = part[1].y() - part[0].y()
                            elif start_end_choice == "End Point":
                                # Use last two points to calculate direction vector
                                dx = part[-2].x() - part[-1].x()
                                dy = part[-2].y() - part[-1].y()

                            length = (dx**2 + dy**2)**0.5

                            # Normalize direction vector and find perpendicular offset vector
                            if length == 0:
                                QMessageBox.warning(
                                    self, "Warning", "Line segment has zero length, cannot calculate offset.")
                                continue
                            perp_dx = -dy / length
                            perp_dy = dx / length

                            # Offset for the extended point
                            offset_x = extended_point.x() + perp_dx * offset_meters
                            offset_y = extended_point.y() + perp_dy * offset_meters
                            offset_point = QgsPointXY(offset_x, offset_y)

                            add_point(offset_point, "Offset Point")

                    else:
                        QMessageBox.warning(
                            self, "Warning", "Direction vector has zero length, cannot extend line.")
                else:
                    # Normal cut point calculation
                    if start_end_choice == "Start Point":
                        cut_point_geom = QgsGeometry.fromPolylineXY(
                            part).interpolate(cut_point_meters)
                    elif start_end_choice == "End Point":
                        reversed_geom = QgsGeometry.fromPolylineXY(part[::-1])
                        cut_point_geom = reversed_geom.interpolate(
                            cut_point_meters)

                    if cut_point_geom.isNull():
                        continue

                    cut_point = cut_point_geom.asPoint()
                    add_point(cut_point, "Cut Point")

                    # Offset Point - Calculate the perpendicular offset
                    if len(part) > 1:
                        # Calculate direction vector based on chosen point
                        if start_end_choice == "Start Point":
                            dx = part[1].x() - part[0].x()
                            dy = part[1].y() - part[0].y()
                        elif start_end_choice == "End Point":
                            # Use last two points to calculate direction vector
                            dx = part[-2].x() - part[-1].x()
                            dy = part[-2].y() - part[-1].y()

                        length = (dx**2 + dy**2)**0.5

                        # Normalize direction vector and find perpendicular offset vector
                        if length == 0:
                            QMessageBox.warning(
                                self, "Warning", "Line segment has zero length, cannot calculate offset.")
                            continue
                        perp_dx = -dy / length
                        perp_dy = dx / length

                        offset_x = cut_point.x() + perp_dx * offset_meters
                        offset_y = cut_point.y() + perp_dy * offset_meters
                        offset_point = QgsPointXY(offset_x, offset_y)
                        add_point(offset_point, "Offset Point")

            point_layer.triggerRepaint()

            # Ensure the active layer doesn't change
            iface.setActiveLayer(layer)
            self.points_drawn = True

        except Exception as e:
            QMessageBox.critical(self, "Unexpected Error",
                                 f"An unexpected error occurred: {e}")
            import traceback
            traceback.print_exc()

    def cleanup(self):
        """Clean up rubber bands and disconnect signals"""
        try:
            if hasattr(self, 'endpoint_manager'):
                self.endpoint_manager.cleanup()
        except Exception as e:
            print(f"Plotter cleanup error: {e}")


class CombinedMainWidget(QWidget):
    def __init__(self, parent=iface.mainWindow()):
        super().__init__(parent)
        self.setWindowTitle('Plotter')
        self.setGeometry(900, 250, 250, 350)
        # Keep window on top and always visible

        self.setWindowFlags(TOOL_WINDOW_FLAGS)

        # Create the tab widget
        self.tab_widget = QTabWidget()

        # Create instances of the widgets
        self.triangle_widget = TriangleWidget()
        self.plotter_widget = PlotterWidget()

        # Add widgets to the tab widget
        self.tab_widget.addTab(self.triangle_widget, "Triangle")
        self.tab_widget.addTab(self.plotter_widget, "Plotter")

        # Layout for the main widget
        layout = QVBoxLayout()
        layout.addWidget(self.tab_widget)
        self.setLayout(layout)

        # Connect to tab changes
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

        # Track if the widget has been shown
        self.has_been_activated = False

    def showEvent(self, event):
        """Handle widget show event - activate endpoint managers when shown"""
        super().showEvent(event)
        # Always activate the currently visible tab's endpoint manager when widget is shown
        current_widget = self.tab_widget.currentWidget()
        if hasattr(current_widget, 'activate'):
            current_widget.activate()
        self.has_been_activated = True

    def on_tab_changed(self, index):
        """Handle tab changes to ensure proper display updates."""
        if not self.has_been_activated:
            return

        try:
            # Deactivate all endpoint managers first
            if hasattr(self.triangle_widget, 'deactivate'):
                self.triangle_widget.deactivate()
            if hasattr(self.plotter_widget, 'deactivate'):
                self.plotter_widget.deactivate()

            # Activate the current tab's endpoint manager
            current_widget = self.tab_widget.currentWidget()
            if hasattr(current_widget, 'activate'):
                current_widget.activate()

            # Update triangle preview if it's the triangle tab
            if (current_widget == self.triangle_widget and
                    hasattr(self.triangle_widget, 'schedule_preview_update')):
                self.triangle_widget.schedule_preview_update()

        except Exception as e:
            print(f"Tab change error: {e}")

    def closeEvent(self, event):
        """Handle widget close event with proper cleanup"""
        try:
            # Check if plotted points were drawn and ask user to save
            if hasattr(self, 'plotter_widget') and self.plotter_widget.points_drawn:
                # Find the plotted points layer
                point_layer = None
                for lyr in QgsProject.instance().mapLayers().values():
                    if lyr.name() == "Plotted Points" and lyr.geometryType() == QgsWkbTypes.GeometryType.PointGeometry:
                        point_layer = lyr
                        break

                if point_layer and point_layer.providerType() == "memory":
                    reply = QMessageBox.question(
                        self, 'Save Plotted Points',
                        "Do you want to save the Plotted Points Layer before closing?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                        QMessageBox.StandardButton.Cancel
                    )

                    if reply == QMessageBox.StandardButton.Yes:
                        saved = save_temp_layer(self, point_layer)
                        if not saved:
                            # If save failed or was cancelled, don't close
                            event.ignore()
                            return
                    elif reply == QMessageBox.StandardButton.Cancel:
                        event.ignore()
                        return
                    # If No, continue with closing

            # Clean up both widgets
            if hasattr(self, 'triangle_widget'):
                self.triangle_widget.cleanup()

            if hasattr(self, 'plotter_widget'):
                self.plotter_widget.cleanup()

            # Force canvas refresh to ensure rubber bands are visually cleared
            iface.mapCanvas().refresh()

        except Exception as e:
            print(f"Main widget cleanup error: {e}")

        event.accept()


# Create and show the main widget
main_widget = CombinedMainWidget()
# main_widget.show()

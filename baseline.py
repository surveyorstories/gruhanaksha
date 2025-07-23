import os
import math
import inspect
from qgis.PyQt.QtCore import Qt, QPoint
from qgis.utils import iface
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton, QRadioButton, QHBoxLayout
from qgis.core import (QgsPointXY, QgsGeometry, QgsSnappingConfig, QgsTolerance, QgsField,
                       QgsProject, QgsVectorLayer, QgsFeature, QgsLineString, QgsWkbTypes, Qgis)
from qgis.gui import QgsMapTool, QgsRubberBand, QgsSnapIndicator
from qgis.PyQt.QtGui import QDoubleValidator
from PyQt5.QtCore import QVariant
from qgis.PyQt.QtGui import QIcon
cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]
baseline_icon = QIcon(os.path.join(
    os.path.join(cmd_folder, 'images/baseline.svg')))


class LengthInputDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Enter Distance")
        self.setMinimumWidth(180)
        self.setWindowIcon(QIcon(baseline_icon))

        # Layout
        layout = QVBoxLayout(self)

        # Unit selection dropdown
        self.unit_label = QLabel("Select Unit:")
        layout.addWidget(self.unit_label)

        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["Meters", "Metric Links", "Gunturs Links"])
        layout.addWidget(self.unit_combo)

        # Input field for distance
        self.label = QLabel("Enter Distance:")
        layout.addWidget(self.label)

        self.distance_input = QLineEdit()
        self.distance_input.setPlaceholderText("Enter distance value")

        # Restrict to decimal values using QDoubleValidator
        validator = QDoubleValidator(0.00, 10000.00, 2, self)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.distance_input.setValidator(validator)

        layout.addWidget(self.distance_input)

        # Set focus to distance input and select all text
        self.distance_input.setFocus()
        self.distance_input.selectAll()

        # Add geometry type selection with radio buttons
        self.geom_label = QLabel("Select Geometry:")
        layout.addWidget(self.geom_label)

        # Horizontal layout for radio buttons
        radio_layout = QHBoxLayout()

        self.line_radio = QRadioButton("Line")
        self.circle_radio = QRadioButton("Circle")
        self.line_radio.setChecked(True)  # Set Line as default

        radio_layout.addWidget(self.line_radio)
        radio_layout.addWidget(self.circle_radio)
        layout.addLayout(radio_layout)

        # OK and Cancel buttons
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.validate_input)
        layout.addWidget(self.ok_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(self.cancel_button)

    def validate_input(self):
        """Validate input before closing dialog."""
        distance_text = self.distance_input.text()
        if not distance_text:
            iface.messageBar().pushMessage(
                "Invalid input", "Distance cannot be blank", level=Qgis.Warning, duration=3)
        else:
            distance = float(distance_text)
            if distance <= 0:
                iface.messageBar().pushMessage(
                    "Invalid input", "Distance must be greater than 0", level=Qgis.Warning, duration=3)
            else:
                self.accept()

    def get_distance_and_unit(self):
        """Return the entered distance and selected unit."""
        distance = float(self.distance_input.text())
        unit = self.unit_combo.currentText()
        return distance, unit


class BaselineTool(QgsMapTool):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.start_point = None
        self.entered_distance = None
        self.geometry_type = "Line"  # Default geometry type
        self.circle_points = []  # Store points for circle segments
        self.field_index = -1  # Add field_index initialization

        # Get or create baseline layer
        # self.temp_layer = self.get_or_create_layer()

        # Rubber band for line preview
        self.line_rubber_band = QgsRubberBand(
            self.canvas, QgsWkbTypes.LineGeometry)
        self.line_rubber_band.setColor(Qt.gray)
        self.line_rubber_band.setWidth(1)
        self.line_rubber_band.setLineStyle(Qt.DashLine)

        # Rubber band for first point
        self.start_point_rubber_band = QgsRubberBand(
            self.canvas, QgsWkbTypes.PointGeometry)
        self.start_point_rubber_band.setColor(Qt.green)
        self.start_point_rubber_band.setWidth(4)
        self.start_point_rubber_band.setIconSize(4)

        # Rubber band for fixed distance point
        self.point_rubber_band = QgsRubberBand(
            self.canvas, QgsWkbTypes.PointGeometry)
        self.point_rubber_band.setColor(Qt.blue)
        self.point_rubber_band.setWidth(4)
        self.point_rubber_band.setIconSize(4)

        # Add circle preview rubber band
        self.circle_rubber_band = QgsRubberBand(
            self.canvas, QgsWkbTypes.LineGeometry)
        self.circle_rubber_band.setColor(Qt.gray)
        self.circle_rubber_band.setWidth(1)
        self.circle_rubber_band.setLineStyle(Qt.DashLine)

        # Setup snapping using existing project settings
        self.snapping_utils = canvas.snappingUtils()
        self.snap_indicator = QgsSnapIndicator(canvas)

    def activate(self):
        """Called when the tool is activated"""
        # Simply use existing snapping settings
        super().activate()

    def get_or_create_layer(self):
        """Get existing baseline layer or create new one"""
        try:
            # Check if layer exists
            layers = QgsProject.instance().mapLayersByName("Baseline")
            if layers:
                layer = layers[0]
            else:
                # Create new layer if doesn't exist
                layer = QgsVectorLayer("LineString?crs={}".format(
                    self.canvas.mapSettings().destinationCrs().authid()),
                    "Baseline", "memory")

                # Add Length field
                layer.dataProvider().addAttributes(
                    [QgsField("Length", QVariant.Double)])
                layer.updateFields()

                QgsProject.instance().addMapLayer(layer)

            # Ensure editing mode
            if not layer.isEditable():
                layer.startEditing()

            return layer

        except Exception as e:
            iface.messageBar().pushMessage(
                "Error", f"Error in get_or_create_layer: {e}", level=Qgis.Warning, duration=3)
            return None

    def create_circle_points(self, center, radius, segments=36):
        """Create points for a circle with given center and radius"""
        points = []
        for i in range(segments + 1):
            angle = i * (2 * math.pi / segments)
            x = center.x() + radius * math.cos(angle)
            y = center.y() + radius * math.sin(angle)
            points.append(QgsPointXY(x, y))
        return points

    def canvasPressEvent(self, event):
        self.temp_layer = self.get_or_create_layer()
        try:
            # Right click cancels the operation
            if event.button() == Qt.RightButton:
                self.reset()
                return

            # Left-click creates points
            if event.button() == Qt.LeftButton:
                snap_match = self.snapping_utils.snapToMap(event.pos())
                point = snap_match.point() if snap_match.isValid(
                ) else self.toMapCoordinates(event.pos())

                if self.start_point is None:
                    self.start_point = point
                    self.start_point_rubber_band.reset(
                        QgsWkbTypes.PointGeometry)
                    self.start_point_rubber_band.addPoint(point)
                    self.start_point_rubber_band.show()

                    # Open custom dialog for length input
                    dialog = LengthInputDialog()
                    if dialog.exec_():
                        distance, unit = dialog.get_distance_and_unit()
                        self.geometry_type = "Line" if dialog.line_radio.isChecked() else "Circle"
                        if distance is not None:
                            # Convert to meters if needed
                            self.entered_distance = self.convert_to_meters(
                                distance, unit)
                    else:

                        self.reset()

                else:
                    if self.entered_distance:
                        if self.geometry_type == "Line":
                            end_point = self.calculate_endpoint(self.start_point,
                                                                self.entered_distance,
                                                                snap_match.point() if snap_match.isValid() else event.pos())
                            self.create_line_feature(
                                self.start_point, end_point)
                        else:  # Circle
                            self.circle_points = self.create_circle_points(
                                self.start_point, self.entered_distance)
                            self.create_circle_feature(self.circle_points)
                        self.reset()
        except Exception as e:
            iface.messageBar().pushMessage(
                "Error", f"Error in canvasPressEvent: {e}", level=Qgis.Warning, duration=3)

    def canvasMoveEvent(self, event):
        try:
            snap_match = self.snapping_utils.snapToMap(event.pos())
            self.snap_indicator.setMatch(snap_match)

            if self.start_point and self.entered_distance:
                cursor_point = snap_match.point() if snap_match.isValid(
                ) else self.toMapCoordinates(event.pos())

                if self.geometry_type == "Line":
                    end_point = self.calculate_endpoint(
                        self.start_point, self.entered_distance, cursor_point)

                    self.line_rubber_band.reset(QgsWkbTypes.LineGeometry)
                    self.line_rubber_band.addPoint(self.start_point)
                    self.line_rubber_band.addPoint(cursor_point)
                    self.line_rubber_band.show()

                    self.point_rubber_band.reset(QgsWkbTypes.PointGeometry)
                    self.point_rubber_band.addPoint(end_point)
                    self.point_rubber_band.show()
                else:  # Circle preview
                    self.circle_rubber_band.reset(QgsWkbTypes.LineGeometry)
                    circle_points = self.create_circle_points(
                        self.start_point, self.entered_distance)
                    for point in circle_points:
                        self.circle_rubber_band.addPoint(point)
                    self.circle_rubber_band.show()
        except Exception as e:
            iface.messageBar().pushMessage(
                "Error", f"Error in canvasMoveEvent: {e}", level=Qgis.Warning, duration=3)

    def create_line_feature(self, start_point, end_point):
        """Creates a line feature between start_point and end_point"""
        try:
            if not self.temp_layer:
                return

            # Create the feature
            feature = QgsFeature(self.temp_layer.fields())
            line = QgsLineString(
                [QgsPointXY(start_point), QgsPointXY(end_point)])
            feature.setGeometry(QgsGeometry.fromPolyline(line))

            # Set the Length attribute
            length_idx = self.temp_layer.fields().indexOf("Length")
            if length_idx != -1:
                feature.setAttribute(length_idx, self.entered_distance)

            # Add feature to layer
            self.temp_layer.addFeature(feature)

            # Commit changes and restart editing
            if self.temp_layer.commitChanges():
                self.temp_layer.startEditing()

                # Update snapping
                project = QgsProject.instance()
                config = project.snappingConfig()
                config.setEnabled(True)
                self.temp_layer.triggerRepaint()

            else:
                iface.messageBar().pushMessage(
                    "Error", "Failed to commit changes", level=Qgis.Warning, duration=3)

        except Exception as e:
            iface.messageBar().pushMessage(
                "Error", f"Error in create_line_feature: {e}", level=Qgis.Warning, duration=3)

    def create_circle_feature(self, points):
        """Creates a circle feature using line segments"""
        try:
            if not self.temp_layer:
                return

            # Create the feature
            feature = QgsFeature(self.temp_layer.fields())
            line = QgsLineString([QgsPointXY(p) for p in points])
            feature.setGeometry(QgsGeometry.fromPolyline(line))

            # Set the Length attribute (circumference)
            length_idx = self.temp_layer.fields().indexOf("Length")
            if length_idx != -1:
                if self.entered_distance is not None:
                    circumference = 2 * math.pi * self.entered_distance
                else:
                    circumference = 0
                feature.setAttribute(length_idx, circumference)

            # Add feature to layer
            self.temp_layer.addFeature(feature)

            # Commit changes and restart editing
            if self.temp_layer.commitChanges():
                self.temp_layer.startEditing()

                # Update snapping
                project = QgsProject.instance()
                config = project.snappingConfig()
                config.setEnabled(True)
                self.temp_layer.triggerRepaint()

            else:
                iface.messageBar().pushMessage(
                    "Error", "Failed to commit changes", level=Qgis.Warning, duration=3)

        except Exception as e:
            iface.messageBar().pushMessage(
                "Error", f"Error in create_circle_feature: {e}", level=Qgis.Warning, duration=3)

    def reset(self):
        """Reset tool state and clear rubber bands"""
        try:
            self.start_point = None
            self.entered_distance = None
            self.geometry_type = "Line"
            self.line_rubber_band.reset(QgsWkbTypes.LineGeometry)
            self.circle_rubber_band.reset(QgsWkbTypes.LineGeometry)
            self.point_rubber_band.reset(QgsWkbTypes.PointGeometry)
            self.start_point_rubber_band.reset(QgsWkbTypes.PointGeometry)
        except Exception as e:
            iface.messageBar().pushMessage(
                "Error", f"Error in reset: {e}", level=Qgis.Warning, duration=3)

    def deactivate(self):
        """Clean up the map tool properly"""
        try:
            if self.snap_indicator:
                self.snap_indicator.setVisible(False)
            self.line_rubber_band.reset(
                QgsWkbTypes.LineGeometry)  # Changed reference
            self.circle_rubber_band.reset(QgsWkbTypes.LineGeometry)
            self.point_rubber_band.reset(QgsWkbTypes.PointGeometry)
            self.start_point = None
            self.entered_distance = None
            super().deactivate()
        except Exception as e:
            iface.messageBar().pushMessage(
                "Error", f"Error in deactivate: {e}", level=Qgis.Warning, duration=3)

    def calculate_endpoint(self, start_point, distance, cursor_pos):
        """Calculate end point based on start point, distance and cursor position"""
        try:
            # Handle cursor_pos based on type
            if isinstance(cursor_pos, QPoint):
                cursor_point = self.toMapCoordinates(cursor_pos)
            else:
                cursor_point = cursor_pos  # Already a QgsPointXY

            # Calculate angle between start point and cursor
            dx = cursor_point.x() - start_point.x()
            dy = cursor_point.y() - start_point.y()
            angle = math.atan2(dy, dx)

            # Calculate end point coordinates using distance and angle
            end_x = start_point.x() + distance * math.cos(angle)
            end_y = start_point.y() + distance * math.sin(angle)

            return QgsPointXY(end_x, end_y)
        except Exception as e:
            iface.messageBar().pushMessage(
                "Error", f"Error in calculate_endpoint: {e}", level=Qgis.Warning, duration=3)
            return start_point

    def convert_to_meters(self, distance, unit):
        """Convert distance to meters based on the selected unit."""
        try:
            if unit == "Meters":
                return distance
            elif unit == "Metric Links":
                return distance * 0.2  # 1 metric link = 0.2 meters
            elif unit == "Gunturs Links":
                return distance * 0.201168  # 1 guntur link = 0.66 meters
            else:
                return distance  # Default case
        except Exception as e:
            iface.messageBar().pushMessage(
                "Error", f"Error in convert_to_meters: {e}", level=Qgis.Warning, duration=3)
            return distance


def baseline_activator():
    canvas = iface.mapCanvas()
    tool = BaselineTool(canvas)
    canvas.setMapTool(tool)
    return tool  # Return the tool instance so it's not garbage collected


# baseline_activator()

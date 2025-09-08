
from PyQt5.QtWidgets import (QWidget, QDoubleSpinBox, QPushButton, QFileDialog, QTabWidget,
                             QVBoxLayout, QLabel, QMessageBox, QComboBox)
import math
from PyQt5.QtWidgets import QWidget, QDoubleSpinBox, QPushButton, QVBoxLayout, QLabel, QMessageBox, QComboBox, QFileDialog
from PyQt5.QtCore import Qt
from .addon_functions import apply_categorized_symbology
from qgis.core import (QgsProject, QgsPointXY, QgsGeometry, QgsVectorLayer,
                       QgsFeature, QgsField, QgsWkbTypes, QgsSymbol, QgsCategorizedSymbolRenderer,
                       QgsRendererCategory, QgsVectorFileWriter)
from qgis.PyQt.QtCore import QVariant
from PyQt5.QtGui import QColor
from qgis.utils import iface
from qgis.PyQt.QtGui import QIcon
from .addon_functions import save_temp_layer
import os
import inspect
from qgis.PyQt.QtGui import QIcon
cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]
plotter_icon = QIcon(os.path.join(
    os.path.join(cmd_folder, 'images/plotter.svg')))
bisector_icon = QIcon(os.path.join(
    os.path.join(cmd_folder, 'images/bisector.svg')))


class TriangleWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Triangle')
        self.setGeometry(50, 200, 200, 200)
        self.setMinimumWidth(220)

        # Length Inputs
        self.start_length_input = QDoubleSpinBox()
        self.start_length_input.setDecimals(3)
        self.start_length_input.setRange(0, 1000000)

        self.end_length_input = QDoubleSpinBox()
        self.end_length_input.setDecimals(3)
        self.end_length_input.setRange(0, 1000000)

        # Orientation Combobox
        self.orientation_combo = QComboBox()
        self.orientation_combo.addItems(["Left", "Right"])
        self.orientation_combo.setCurrentIndex(0)  # Default to "Left"

        # Unit Selection ComboBox
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["Meters", "Metric Links", "Gunter's Links"])
        self.unit_combo.setCurrentIndex(0)  # Default to "Meters"

        # Draw Button
        self.draw_button = QPushButton("Draw Triangle")
        self.draw_button.clicked.connect(self.draw_triangle)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Start Length:"))
        layout.addWidget(self.start_length_input)
        layout.addWidget(QLabel("End Length:"))
        layout.addWidget(self.end_length_input)
        layout.addWidget(QLabel("Orientation:"))
        layout.addWidget(self.orientation_combo)
        layout.addWidget(QLabel("Units:"))
        layout.addWidget(self.unit_combo)
        layout.addWidget(self.draw_button)
        layout.setAlignment(Qt.AlignTop)
        self.setLayout(layout)

        # Create point layer with categorized symbology for start and end points
        # self.create_point_layer()
        self.triangle_drawn = False

    def convert_length(self, length):
        """Convert the length to meters based on selected units."""
        unit = self.unit_combo.currentText()
        if unit == "Meters":
            return length  # No conversion needed for meters
        elif unit == "Metric Links":
            return length * 0.2  # 1 Metric Link = 0.2 meters
        elif unit == "Gunter's Links":
            return length * 0.201168  # 1 Gunter's Link = 0.201168 meters
        else:
            return length

    def draw_triangle(self):
        """Draw a triangle using the selected line as the base and orientation."""
        try:
            layer = iface.activeLayer()
            if layer is None:
                QMessageBox.critical(
                    self, "Error", "Please select a line layer.")
                return

            if layer.wkbType() not in [QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString]:
                QMessageBox.critical(
                    self, "Error", "The active layer is not a line layer.")
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

            # Extract start and end points of the base line
            if geom.isMultipart():
                points = geom.asMultiPolyline()
                start_point = QgsPointXY(points[0][0])
                end_point = QgsPointXY(points[-1][-1])
            else:
                points = geom.asPolyline()
                if not points:
                    QMessageBox.critical(self, "Error", "Geometry is empty.")
                    return
                start_point = QgsPointXY(points[0])
                end_point = QgsPointXY(points[-1])

            # Input lengths
            start_length = self.start_length_input.value()
            end_length = self.end_length_input.value()

            # Convert lengths to meters based on selected unit
            start_length = self.convert_length(start_length)
            end_length = self.convert_length(end_length)

            # Calculate the base length and direction
            dx = end_point.x() - start_point.x()
            dy = end_point.y() - start_point.y()
            base_length = math.sqrt(dx**2 + dy**2)

            if base_length == 0:  # Handle zero base length
                raise ValueError("Base line has zero length.")

            if start_length <= 0 or end_length <= 0:
                raise ValueError("Side lengths must be greater than zero.")

            # Check for triangle inequality theorem (a + b > c)
            if not (start_length + end_length > base_length and
                    start_length + base_length > end_length and
                    end_length + base_length > start_length):
                raise ValueError(
                    "Invalid side lengths. Triangle cannot be formed.")

            # Normalize direction vector
            ux = dx / base_length
            uy = dy / base_length

            # Determine perpendicular vector based on orientation
            if self.orientation_combo.currentText() == "Right":
                perp_ux = -uy
                perp_uy = ux
            else:  # Right
                perp_ux = uy
                perp_uy = -ux

            # Law of Cosines for angle at start and end
            try:
                angle_start = math.acos(
                    (start_length**2 + base_length**2 - end_length**2) / (2 * start_length * base_length))
                angle_end = math.acos(
                    (end_length**2 + base_length**2 - start_length**2) / (2 * end_length * base_length))
            except ValueError:
                raise ValueError(
                    "Invalid side lengths. Triangle cannot be formed.")

            # Apex point calculation using angles
            apex_x = start_point.x() + start_length * (ux * math.cos(angle_start) -
                                                       perp_ux * math.sin(angle_start))
            apex_y = start_point.y() + start_length * (uy * math.cos(angle_start) -
                                                       perp_uy * math.sin(angle_start))
            apex_point = QgsPointXY(apex_x, apex_y)

            # Check if a layer named "Triangle Lines" exists
            line_layer_name = "Triangle Lines"
            line_layer = None
            for lyr in QgsProject.instance().mapLayers().values():
                if lyr.name() == line_layer_name and lyr.geometryType() == QgsWkbTypes.LineGeometry:
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
            add_line(start_point, apex_point, "Start Side")
            add_line(end_point, apex_point, "End Side")
            add_line(start_point, end_point, "Base Line")

            line_layer.triggerRepaint()
            iface.setActiveLayer(layer)
            QMessageBox.information(
                self, "Success", "Triangle drawn successfully!")
            self.triangle_drawn = True

        except ValueError as ve:
            QMessageBox.critical(self, "Input Error", str(ve))
        except Exception as e:
            QMessageBox.critical(self, "Unexpected Error",
                                 f"An unexpected error occurred: {e}")
            import traceback
            traceback.print_exc()  # Print the full traceback for debugging


widget = TriangleWidget()


class PlotterWidget(QWidget):
    def __init__(self, parent=None):

        super(PlotterWidget, self).__init__(parent)
        self.setWindowTitle('Plotter')
        self.setGeometry(50, 550, 200, 200)
        self.setMinimumWidth(220)

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
        layout.setAlignment(Qt.AlignTop)
        self.setLayout(layout)

        # Initialize and show start and end points
        # self.display_start_end_points()
        self.points_drawn = False

    def plot(self):
        """Plot the cut point and offset point based on the selected line."""
        try:
            # Get the active layer
            layer = iface.activeLayer()
            if layer is None:
                QMessageBox.critical(self, "Error", "Please select a layer.")
                return

            if layer.wkbType() not in [QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString]:
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
            unit = self.unit_combo.currentText()

            # Convert units to meters
            offset_meters = offset_input
            cut_point_meters = cut_point_input

            if unit == "Metric Links":
                offset_meters = offset_input * 0.20
                cut_point_meters = cut_point_input * 0.20
            elif unit == "Gunter's Links":
                offset_meters = offset_input * 0.201168
                cut_point_meters = cut_point_input * 0.201168

            # Choose starting point based on user's selection
            start_end_choice = self.point_combo.currentText()

            # Prepare or fetch the point layer
            point_layer_name = "Plotted Points"
            existing_layer = None
            for lyr in QgsProject.instance().mapLayers().values():
                if lyr.name() == point_layer_name and lyr.geometryType() == QgsWkbTypes.PointGeometry:
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
            # Define the categories with their properties
            categories_info = [
                {'name': 'Cut Point', 'color': 'orange', 'size': 2, 'opacity': 1},
                {'name': "Offset Point", 'color': 'blue',
                    'size': 2, 'opacity': 1},
                {'name': "Extended Point", 'color': 'purple',
                    'size': 2, 'opacity': 1},
                # {'name': 'Route', 'color': 'blue', 'line_width': 2, 'opacity': 0.7},
                # {'name': 'Area', 'color': 'yellow', 'opacity': 0.5},
                # Add more categories as needed
            ]

            # Assuming 'layer' is a QgsVectorLayer containing point, line, or polygon features
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

                if cut_point_meters > line_length and direction_point:
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
                        #                        QMessageBox.warning(
                        #                            self, "Warning", "Cut point could not be calculated for a part. Skipping.")
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
                        if cut_point_input < 0:
                            # Extend the line backward
                            if start_end_choice == "Start Point":
                                dx = part[0].x() - part[1].x()
                                dy = part[0].y() - part[1].y()
                            elif start_end_choice == "End Point":
                                dx = part[-1].x() - part[-2].x()
                                dy = part[-1].y() - part[-2].y()

                            direction_length = (dx**2 + dy**2)**0.5

                            if direction_length != 0:
                                # Normalize the direction vector
                                unit_dx = dx / direction_length
                                unit_dy = dy / direction_length

                                # Calculate extension distance (backward)
                                extension_distance = abs(cut_point_meters)

                                # Extended point coordinates
                                extended_x = base_point.x() + unit_dx * extension_distance
                                extended_y = base_point.y() + unit_dy * extension_distance
                                extended_point = QgsPointXY(
                                    extended_x, extended_y)

                                # Add the extended point
                                add_point(extended_point, "Extended Point")

                                # Now calculate the offset for the extended point
                                perp_dx = -dy / direction_length
                                perp_dy = dx / direction_length

                                offset_x = extended_point.x() + perp_dx * offset_meters
                                offset_y = extended_point.y() + perp_dy * offset_meters
                                offset_point = QgsPointXY(offset_x, offset_y)

                                add_point(offset_point, "Offset Point")
                            else:
                                QMessageBox.warning(
                                    self, "Warning", "Direction vector has zero length, cannot extend line.")
                        else:
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


widget = PlotterWidget()


class BisectorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Bisector')
        self.setGeometry(250, 250, 200, 200)
        self.setWindowIcon(QIcon(bisector_icon))
        self.setMinimumWidth(220)
        self.bisector_points_drawn = False
        # Length Inputs
        self.length_input = QDoubleSpinBox()
        self.length_input.setDecimals(3)
        self.length_input.setRange(0, 1000000)

        # Orientation Combobox
        self.orientation_combo = QComboBox()
        self.orientation_combo.addItems(["Start Point", "End Point"])
        self.orientation_combo.setCurrentIndex(0)  # Default to "Left"

        # Unit Selection ComboBox
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["Meters", "Metric Links", "Gunter's Links"])
        self.unit_combo.setCurrentIndex(0)  # Default to "Meters"

        # Draw Button
        self.draw_button = QPushButton("Split")
        self.draw_button.clicked.connect(self.split_line)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Length:"))
        layout.addWidget(self.length_input)
        layout.addWidget(QLabel("from:"))
        layout.addWidget(self.orientation_combo)
        layout.addWidget(QLabel("Units:"))
        layout.addWidget(self.unit_combo)
        layout.addWidget(self.draw_button)
        layout.setAlignment(Qt.AlignTop)
        self.setLayout(layout)

        # Create point layer with categorized symbology for start and end points
        # self.create_point_layer()

    def convert_length(self, length):
        """Convert the length to meters based on selected units."""
        unit = self.unit_combo.currentText()
        if unit == "Meters":
            return length  # No conversion needed for meters
        elif unit == "Metric Links":
            return length * 0.2  # 1 Metric Link = 0.2 meters
        elif unit == "Gunter's Links":
            return length * 0.201168  # 1 Gunter's Link = 0.201168 meters
        else:
            return length

    def split_line(self):
        try:
            # Get active layer
            layer = iface.activeLayer()
            if layer is None or layer.wkbType() not in [QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString]:
                raise ValueError("Please select a valid line layer.")

            # Get the length to split the lines into
            split_length = self.convert_length(self.length_input.value())
            if split_length <= 0:
                raise ValueError("Split length must be greater than 0.")

            # Start editing the layer
            layer.startEditing()

            # Check if any features are selected
            if not layer.selectedFeatureCount():
                raise ValueError("No features selected.")

            # Determine the orientation (from Start Point or End Point)
            orientation = self.orientation_combo.currentText()

            # Check if the temporary layer already exists
            layer_crs = layer.crs()  # Get the CRS of the active layer
            temp_layer_name = "Bisection Points"
            existing_layer = None

            for lyr in QgsProject.instance().mapLayers().values():
                if lyr.name() == temp_layer_name and lyr.geometryType() == QgsWkbTypes.PointGeometry:
                    existing_layer = lyr
                    break

            if existing_layer:
                temp_layer = existing_layer
            else:
                # Create a new temporary point layer
                temp_layer = QgsVectorLayer(
                    f"Point?crs={layer_crs.toWkt()}", temp_layer_name, "memory")
                temp_layer.dataProvider().addAttributes(
                    [QgsField("ID", QVariant.Int)])
                temp_layer.updateFields()
                QgsProject.instance().addMapLayer(temp_layer)
                self.bisector_points_drawn = True

            # Add points to the layer
            for feature in layer.selectedFeatures():
                geom = feature.geometry()
                length = geom.length()  # Get the total length of the line

                # Check if the line is long enough for the specified split
                if split_length >= length:
                    raise ValueError(
                        "The split length is greater than or equal to the line length.")

                # Determine the split position based on orientation
                if orientation == "Start Point":
                    split_point = geom.interpolate(
                        split_length)  # From the start
                elif orientation == "End Point":
                    split_point = geom.interpolate(
                        length - split_length)  # From the end

                # Add the bisection point to the layer
                bisection_feature = QgsFeature()
                bisection_feature.setGeometry(split_point)
                bisection_feature.setAttributes([feature.id()])
                temp_layer.dataProvider().addFeature(bisection_feature)

            # Trigger repaint and refresh
            iface.setActiveLayer(layer)
            temp_layer.triggerRepaint()
            iface.mapCanvas().refresh()

            QMessageBox.information(
                self, "Success", "Lines split and points added successfully.")

        except ValueError as e:
            QMessageBox.critical(self, "Input Error", str(e))

        except Exception as e:
            QMessageBox.critical(self, "Unexpected Error",
                                 f"An unexpected error occurred: {e}")

    def closeEvent(self, event):
        """Handle widget close event with save prompt."""
        if self.bisector_points_drawn:  # Check if a Start and End Pointshas been drawn
            point_layer = None
            for point_layer in QgsProject.instance().mapLayers().values():
                if point_layer.name() == "Bisection Points" and point_layer.geometryType() == QgsWkbTypes.PointGeometry:

                    break

            if point_layer:
                # Check if the layer is temporary or permanent
                if point_layer.providerType() == "memory":
                    reply = QMessageBox.question(self, 'Save Bisection Points',
                                                 "Do you want to save the Bisection Points Layer before closing?",
                                                 QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Cancel)
                    if reply == QMessageBox.Yes:
                        save_temp_layer(self, point_layer)
                    elif reply == QMessageBox.Cancel:
                        event.ignore()  # Prevent closing if user cancels
                        return
                else:
                    save_temp_layer(self, point_layer)
            else:
                QMessageBox.warning(
                    self, "Warning", "Plotted Points Layer not found. Cannot Save")
                event.ignore()  # Do not close if the layer is not found or cannot be saved

            # Remove the Start and End Points layer
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() == "Start and End Points":
                QgsProject.instance().removeMapLayer(lyr.id())
                break

        event.accept()
        canvas = iface.mapCanvas()
        canvas.refresh()


widget = BisectorWidget()


class CombinedMainWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Plotter')
        self.setGeometry(300, 250, 200, 200)
        self.setWindowIcon(QIcon(plotter_icon))
        # Create the tab widget
        self.tab_widget = QTabWidget()

        # Create instances of the widgets
        self.triangle_widget = TriangleWidget()
        self.plotter_widget = PlotterWidget()
        self.bisector_widget = BisectorWidget()

        # Add widgets to the tab widget

        self.tab_widget.addTab(self.triangle_widget, "Triangle")
        self.tab_widget.addTab(self.plotter_widget, "Plotter")
        # self.tab_widget.addTab(self.bisector_widget, "Bisector")
        # Layout for the main widget
        layout = QVBoxLayout()
        layout.addWidget(self.tab_widget)
        self.setLayout(layout)

    def closeEvent(self, event):
        """Handle widget close event with save prompt."""
        if self.plotter_widget.points_drawn:  # Check if a Start and End Pointshas been drawn
            point_layer = None
            for point_layer in QgsProject.instance().mapLayers().values():
                if point_layer.name() == "Plotted Points" and point_layer.geometryType() == QgsWkbTypes.PointGeometry:

                    break

            if point_layer:
                # Check if the layer is temporary or permanent
                if point_layer.providerType() == "memory":
                    reply = QMessageBox.question(self, 'Save Plotted Points',
                                                 "Do you want to save the Plotted Points Layer before closing?",
                                                 QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Cancel)
                    if reply == QMessageBox.Yes:
                        save_temp_layer(self, point_layer)
                    elif reply == QMessageBox.Cancel:
                        event.ignore()  # Prevent closing if user cancels
                        return
                else:
                    save_temp_layer(self, point_layer)
            else:
                QMessageBox.warning(
                    self, "Warning", "Plotted Points Layer not found. Cannot Save")
                event.ignore()  # Do not close if the layer is not found or cannot be saved

        # Remove the Start and End Points layer
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() == "Start and End Points":
                QgsProject.instance().removeMapLayer(lyr.id())
                break

        event.accept()
        canvas = iface.mapCanvas()
        canvas.refresh()

        """Handle widget close event with save prompt."""
        if self.triangle_widget.triangle_drawn:  # Check if a triangle has been drawn
            line_layer = None
            for lyr in QgsProject.instance().mapLayers().values():
                if lyr.name() == "Triangle Lines" and lyr.geometryType() == QgsWkbTypes.LineGeometry:
                    line_layer = lyr
                    break

            if line_layer:
                # Check if the layer is temporary or permanent
                if line_layer.providerType() == "memory":
                    reply = QMessageBox.question(self, 'Save Triangle',
                                                 "Do you want to save the Triangle Layer before closing?",
                                                 QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Cancel)
                    if reply == QMessageBox.Yes:
                        save_temp_layer(self, line_layer)
                    elif reply == QMessageBox.Cancel:
                        event.ignore()  # Prevent closing if user cancels
                        return
                else:
                    save_temp_layer(self, line_layer)
            else:
                QMessageBox.warning(
                    self, "Warning", "Triangle Layer not found. Cannot Save")
                event.ignore()  # Do not close if the layer is not found or cannot be saved


# Create and show the main widget
main_widget = CombinedMainWidget()
# main_widget.show()

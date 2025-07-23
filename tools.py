from PyQt5.QtGui import QColor
from qgis.PyQt.QtCore import QVariant
from qgis.core import (QgsPointXY, QgsGeometry,
                       QgsFeature,  QgsSymbol, QgsCategorizedSymbolRenderer,
                       QgsRendererCategory, )
from PyQt5.QtWidgets import QDoubleSpinBox,   QLabel, QFileDialog
import math
from qgis.PyQt.QtGui import QIcon
from qgis.gui import QgsMapLayerComboBox
import inspect
import sys
import processing
import os
from PyQt5 import QtCore
from PyQt5.QtCore import QVariant
from qgis.utils import iface
from qgis.PyQt.QtWidgets import qApp
from qgis.core import QgsVectorLayer, QgsRasterLayer, QgsMapLayerProxyModel, QgsProject, QgsMapLayer, QgsWkbTypes, QgsVectorFileWriter, QgsField, QgsFillSymbol, QgsSingleSymbolRenderer, QgsMapLayerType, QgsProcessing, QgsProcessingContext, QgsProcessingFeedback, QgsExpressionContextUtils
from qgis.PyQt.QtWidgets import QAction
from PyQt5.QtWidgets import QCheckBox, QSpinBox,  QVBoxLayout, QWidget, QPushButton, QMessageBox, QHBoxLayout, QComboBox, QGroupBox, QProgressBar
from PyQt5.QtCore import Qt

from typing import Optional, Dict, List
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QSpinBox, QComboBox, QPushButton, QProgressBar,
                             QApplication as qApp)
from qgis.core import (QgsVectorLayer, QgsMapLayerProxyModel, QgsFeature,
                       QgsMessageLog, QgsVectorDataProvider)
from typing import Optional, Dict
from typing import Optional, Dict, List, Tuple
from .fmb import TriangleWidget, PlotterWidget, BisectorWidget, CombinedMainWidget
from .baseline import baseline_activator
from .addon_functions import apply_categorized_symbology
from .polygon_adjuster import activate_unified_tool


triangle_window = TriangleWidget()
plotter_window = PlotterWidget()
bisector_window = BisectorWidget()
combined_window = CombinedMainWidget()
# adjuster_window = PolygonAdjusterWidget()


cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]
icon = QIcon(os.path.join(os.path.join(cmd_folder, 'images/topo.svg')))

project = QgsProject.instance()
project_folder = project.readPath("./")


# Get the main QGIS window and set it as the parent for the widget
qgis_main_window = iface.mainWindow()

triangle_window.setParent(qgis_main_window, Qt.Window)
combined_window.setParent(qgis_main_window, Qt.Window)


class ToolWidget(QWidget):
    def __init__(self, parent=None):
        super(ToolWidget, self).__init__(parent)
        self.setWindowTitle("Tool Panel")
        self.setGeometry(220, 150, 230, 200)
        # self.setWindowFlags(Qt.Window)  # Make it a standalone window
        self.setAttribute(Qt.WA_DeleteOnClose)  # Allow cleanup when closed
        self.resize(300, 100)
        self.function_completed = False
        self.setWindowIcon(QIcon(icon))

        main_layout = QVBoxLayout(self)

        # Group box named "Tool"
        group_box = QGroupBox("Tools")
        group_layout = QHBoxLayout()

        # Buttons
        self.baseline_button = QPushButton(
            QIcon(os.path.join(cmd_folder, 'images/baseline2.svg')), 'DrawLine')
        self.baseline_button.setToolTip("Open Baseline Tool")
        self.baseline_button.setStyleSheet(
            "background-color: #020507 ; color: white")
        self.plotter_button = QPushButton(
            QIcon(os.path.join(cmd_folder, 'images/plotter.svg')), 'Plotter')
        self.plotter_button.setToolTip("Open Plotter Tool")
        self.plotter_button.setStyleSheet(
            "background-color: #020507 ; color: white")
        self.adjuster_button = QPushButton(
            QIcon(os.path.join(cmd_folder, 'images/aligner.svg')), 'Adjuster')
        self.adjuster_button.setToolTip("Open Polygon Adjuster Tool")
        self.adjuster_button.setStyleSheet(
            "background-color: #020507 ; color: white")

        # Connect button actions
        self.baseline_button.clicked.connect(self.baseline_button_clicked)
        self.plotter_button.clicked.connect(self.combined_button_clicked)
        self.adjuster_button.clicked.connect(self.adjuster_button_clicked)

        # Horizontal layout with spacing
        group_layout.addStretch(1)
        group_layout.addWidget(self.baseline_button)
        group_layout.addStretch(1)
        group_layout.addWidget(self.plotter_button)
        group_layout.addStretch(1)
        group_layout.addWidget(self.adjuster_button)
        group_layout.addStretch(1)

        group_box.setLayout(group_layout)
        main_layout.addWidget(group_box)

    def adjuster_button_clicked(self):
        print("Button 3 clicked")
        activate_unified_tool()

    def baseline_button_clicked(self):

        try:
            self.baseline_tool = baseline_activator()
        except Exception as e:
            iface.messageBar().pushMessage(
                "Error", f"Failed to initialize Baseline: {str(e)}", level=2, duration=2)

    def combined_button_clicked(self):
        try:
            self.display_start_end_points()
            if self.function_completed:
                combined_window.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {e}")

    def bisector_button_clicked(self):

        try:
            self.create_point_layer()
            if self.function_completed:
                bisector_window.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {e}")

    def display_start_end_points(self):
        """Display the start and end points of the selected line feature."""
        try:
            layer = iface.activeLayer()
            if layer is None or not isinstance(layer, QgsVectorLayer):
                QMessageBox.critical(
                    self, "Error", "Please select a valid vector Line layer.")
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

            # Handle MultiLineString by using the first and last points of all parts
            if geom.isMultipart():
                points = geom.asMultiPolyline()
                # First point of the first part
                start_point = QgsPointXY(points[0][0])
                # Last point of the last part
                end_point = QgsPointXY(points[-1][-1])
            else:
                points = geom.asPolyline()
                if not points:
                    QMessageBox.critical(self, "Error", "Geometry is empty.")
                    return
                start_point = QgsPointXY(points[0])  # First point
                end_point = QgsPointXY(points[-1])  # Last point

            # Create or fetch a point layer
            layer_crs = layer.crs()
            point_layer_name = "Start and End Points"
            existing_layer = None
            for lyr in QgsProject.instance().mapLayers().values():
                if lyr.name() == point_layer_name and lyr.geometryType() == QgsWkbTypes.PointGeometry:
                    existing_layer = lyr
                    break

            if existing_layer:
                point_layer = existing_layer
            else:
                point_layer = QgsVectorLayer(
                    f"Point?crs={layer_crs.toWkt()}", point_layer_name, "memory")
                point_layer.dataProvider().addAttributes(
                    [QgsField("Type", QVariant.String)])
                point_layer.updateFields()
                QgsProject.instance().addMapLayer(point_layer)

            # Add start and end points with a 'Type' attribute
            def add_point(point, point_type):
                """Add a styled point feature."""
                feature = QgsFeature()
                feature.setGeometry(QgsGeometry.fromPointXY(point))
                feature.setAttributes([point_type])
                point_layer.dataProvider().addFeature(feature)

            add_point(start_point, "Start Point")
            add_point(end_point, "End Point")

            # Apply Categorized Symbology to the point layer
            # Define the categories with their properties
            categories_info = [
                {'name': 'Start Point', 'color': 'green', 'size': 3, 'opacity': 0.5},
                {'name': 'End Point', 'color': 'red', 'size': 2, 'opacity': 0.5},
                # {'name': 'Route', 'color': 'blue', 'line_width': 2, 'opacity': 0.7},
                # {'name': 'Area', 'color': 'yellow', 'opacity': 0.5},
                # Add more categories as needed
            ]

            # Assuming 'layer' is a QgsVectorLayer containing point, line, or polygon features
            apply_categorized_symbology(point_layer, categories_info)

            point_layer.triggerRepaint()

            # Ensure the active layer doesn't change
            iface.setActiveLayer(layer)
            self.function_completed = True

        except Exception as e:
            QMessageBox.critical(self, "Unexpected Error",
                                 f"An unexpected error occurred: {e}")

    def create_point_layer(self):
        """Create a point layer for displaying start and end points with categorized symbology."""
        try:
            layer = iface.activeLayer()
            if layer is None or not isinstance(layer, QgsVectorLayer):
                QMessageBox.critical(
                    self, "Error", "Please select a valid vector Line layer.")
                return

            if layer.wkbType() not in [QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString]:
                QMessageBox.critical(
                    self, "Error", "The active layer is not a line layer.")
                return

            selected_features = list(layer.selectedFeatures())
            if len(selected_features) == 0:
                QMessageBox.critical(
                    self, "No feature selected", "Please select at least one line feature.")
                return

            # Create or fetch the point layer
            point_layer_name = "Start and End Points"
            existing_layer = None
            for lyr in QgsProject.instance().mapLayers().values():
                if lyr.name() == point_layer_name and lyr.geometryType() == QgsWkbTypes.PointGeometry:
                    existing_layer = lyr
                    break

            if existing_layer:
                point_layer = existing_layer
            else:
                layer_crs = layer.crs()
                point_layer = QgsVectorLayer(
                    f"Point?crs={layer_crs.toWkt()}", point_layer_name, "memory")
                point_layer.dataProvider().addAttributes(
                    [QgsField("Type", QVariant.String)])
                point_layer.updateFields()
                QgsProject.instance().addMapLayer(point_layer)

            # Loop through all selected features and extract start and end points
            def add_point(point, point_type):
                """Add a styled point feature."""
                feature = QgsFeature()
                feature.setGeometry(QgsGeometry.fromPointXY(point))
                feature.setAttributes([point_type])
                point_layer.dataProvider().addFeature(feature)

            for feature in selected_features:
                geom = feature.geometry()
                if geom is None or geom.isNull():
                    continue  # Skip features with no valid geometry

                # Extract start and end points of the line
                if geom.isMultipart():
                    points = geom.asMultiPolyline()
                    start_point = QgsPointXY(points[0][0])
                    end_point = QgsPointXY(points[-1][-1])
                else:
                    points = geom.asPolyline()
                    if not points:
                        continue  # Skip if the polyline is empty
                    start_point = QgsPointXY(points[0])
                    end_point = QgsPointXY(points[-1])

                # Add points to the layer
                add_point(start_point, "Start Point")
                add_point(end_point, "End Point")

            # Apply Categorized Symbology
            # Define the categories with their properties
            categories_info = [
                {'name': 'Start Point', 'color': 'green', 'size': 3, 'opacity': 0.5},
                {'name': 'End Point', 'color': 'red', 'size': 2, 'opacity': 0.5},
                # {'name': 'Route', 'color': 'blue', 'line_width': 2, 'opacity': 0.7},
                # {'name': 'Area', 'color': 'yellow', 'opacity': 0.5},
                # Add more categories as needed
            ]

            # Assuming 'layer' is a QgsVectorLayer containing point, line, or polygon features
            apply_categorized_symbology(point_layer, categories_info)

            point_layer.triggerRepaint()
            iface.setActiveLayer(layer)
            self.function_completed = True

        except Exception as e:
            QMessageBox.critical(self, "Unexpected Error",
                                 f"An unexpected error occurred: {e}")

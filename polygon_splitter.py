# This tool is built upon the Split Features On Steroids plugin, featuring enhancements and adaptations tailored to resurvey requirements.
from __future__ import absolute_import
from .marker_tool import MarkerMapTool
from qgis.gui import QgsMapToolEmitPoint, QgsMapCanvas, QgsMapToolPan, QgsMapToolZoom, QgsSnapIndicator
from qgis.core import QgsRectangle, QgsFeatureRequest, QgsProcessingUtils, QgsMapLayer, QgsSnappingConfig, QgsTolerance
from .qt_compat import Qt, QtCompat, QEvent, QSize, QVariant, pyqtSignal, QPointF
import inspect
# 2017 - Antonio Carlon
# from PyQt5.QtCore import pyqtSignal (removed)
from builtins import str, range, object

from qgis.PyQt.QtCore import QObject
from .qt_compat import QIcon, QColor
from qgis.PyQt.QtGui import QPen, QBrush
from .qt_compat import (
    QAction, QMessageBox, QGraphicsTextItem, QMainWindow, QVBoxLayout,
    QWidget, QToolBar, QSizePolicy, QPushButton, QDialog, QCheckBox,
    QLabel, QComboBox, QLineEdit, QHBoxLayout
)
from math import sqrt, sin, cos, pi, pow
import inspect
import threading
import qgis.utils
from .addon_functions import undo, redo
from qgis.core import QgsVectorLayer, QgsProject, QgsDistanceArea, QgsPoint, QgsPointXY, QgsGeometry, QgsWkbTypes
from qgis.gui import QgsMessageBar, QgsMapToolEdit, QgsRubberBand
from qgis.utils import iface
import sys
import os

cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]
icon = QIcon(os.path.join(os.path.join(
    cmd_folder, 'images/canvas_one/splitwindow.svg')))

name = "Start Spliting"
moveVerticesName = "Move Vertices"
addVerticesName = "Add Vertices"
removeVerticesName = "Remove Vertices"
moveSegmentName = "Move segment"
closeLineName = "Close line"
openLineName = "Open line"
moveLineName = "Move line"
maxDistanceHitTest = 5


UNIT_CONVERSIONS = {
    "Acres": {"factor": 0.000247105381, "label": "ac", "linear_factor": 1.0, "linear_label": "m"},
    "Hectares": {"factor": 0.0001, "label": "ha", "linear_factor": 1.0, "linear_label": "m"},
    "Sq Meters": {"factor": 1.0, "label": "m²", "linear_factor": 1.0, "linear_label": "m"},
    "Sq Feet": {"factor": 10.7639104, "label": "ft²", "linear_factor": 3.28084, "linear_label": "ft"},
    "Sq Yards": {"factor": 1.19599005, "label": "yd²", "linear_factor": 1.09361, "linear_label": "yd"},
    "Guntas": {"factor": 0.0098842, "label": "gunta", "linear_factor": 1.0, "linear_label": "m"}
}


class MessageBar(QgsMessageBar):
    def __init__(self, parent=None):
        super(MessageBar, self).__init__(parent)
        self.parent().installEventFilter(self)

    def showEvent(self, event):
        self.resize(
            QSize(self.parent().geometry().size().width(), self.height()))
        self.move(0, self.parent().geometry().size().height() - self.height())
        self.raise_()

    def eventFilter(self, object, event):
        if event.type() == QEvent.Resize:
            self.showEvent(None)

        return super(MessageBar, self).eventFilter(object, event)


class FeatureSelectMapTool(QgsMapToolEmitPoint):
    def __init__(self, canvas):
        self.canvas = canvas
        QgsMapToolEmitPoint.__init__(self, self.canvas)
        self.setCursor(QtCompat.arrow_cursor())

    def canvasPressEvent(self, e):
        """
        Handle mouse press events on the canvas.
        Performs feature selection based on the click location.
        """
        point = self.toMapCoordinates(e.pos())

        # Define a search radius around the click point (in map units)
        searchRadius = 0.01

        # Create a rectangle around the click point to use as a search area
        rect = self.createRect(point, searchRadius)

        # Create a QgsFeatureRequest to define the search area
        request = QgsFeatureRequest().setFilterRect(rect)

        # Get the active layer in QGIS (you might want to adjust this depending on your layers)
        activeLayer = iface.activeLayer()

        # Check if the Ctrl key is pressed
        ctrlPressed = e.modifiers() == QtCompat.ControlModifier

        # Perform the selection
        # Perform the selection
        if activeLayer and isinstance(activeLayer, QgsVectorLayer):
            if not ctrlPressed:
                # Clear existing selection if Ctrl is not pressed
                activeLayer.removeSelection()

            selectedFeatures = activeLayer.getFeatures(request)
            for feature in selectedFeatures:
                # Add the feature to the selection if Ctrl is pressed
                if ctrlPressed:
                    activeLayer.select(feature.id())
                else:
                    activeLayer.selectByIds([feature.id()])

    def createRect(self, point, radius):
        # Create a rectangle around the click point for the search area
        return QgsRectangle(point.x() - radius, point.y() - radius, point.x() + radius, point.y() + radius)


class AreaAdjustDialog(QDialog):
    def __init__(self, current_areas, unit_label="ac"):
        super().__init__()
        self.setWindowTitle(f"Adjust Area ({unit_label})")
        self.layout = QVBoxLayout()

        self.areas = current_areas  # List of (index, area_value)
        self.unit_label = unit_label

        # Part Selector
        self.part_label = QLabel("Select Part to Adjust:")
        self.part_combo = QComboBox()
        for i, area in enumerate(self.areas):
            self.part_combo.addItem(
                f"Part {i+1} (Current: {area:.3f} {self.unit_label})", i)

        # Target Area Input
        self.target_label = QLabel(f"Target Area ({self.unit_label}):")
        self.target_input = QLineEdit()

        self.layout.addWidget(self.part_label)
        self.layout.addWidget(self.part_combo)
        self.layout.addWidget(self.target_label)
        self.layout.addWidget(self.target_input)

        # Buttons
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("Adjust")
        self.cancel_button = QPushButton("Cancel")

        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        self.layout.addLayout(button_layout)

        self.setLayout(self.layout)

    def get_values(self):
        try:
            target_area = float(self.target_input.text())
            part_index = self.part_combo.currentData()
            return part_index, target_area
        except ValueError:
            return None, None


class LayerSelectDialog(QDialog):

    def __init__(self, layers, selected_layers):
        super().__init__()

        self.selected_layers = selected_layers
        self.setWindowTitle("Select Layers")
        self.layout = QVBoxLayout()

        # Get layers from the Layer Tree to maintain the order as in the Layers Panel
        layer_tree = QgsProject.instance().layerTreeRoot()
        layers_in_panel_order = [layer.layer() for layer in layer_tree.children(
        ) if isinstance(layer.layer(), QgsMapLayer)]

        # Add checkboxes for each layer in the same order as the layer panel
        for layer in layers_in_panel_order:
            if layer.isValid() and layer.type() in [QgsMapLayer.VectorLayer, QgsMapLayer.RasterLayer]:
                checkbox = QCheckBox(layer.name())
                checkbox.setChecked(layer in selected_layers)
                checkbox.setProperty("layer", layer)
                self.layout.addWidget(checkbox)

        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept)
        self.layout.addWidget(self.ok_button)

        self.setLayout(self.layout)

    # def accept(self):
    #     self.selected_layers = [checkbox.property(
    #         "layer") for checkbox in self.findChildren(QCheckBox) if checkbox.isChecked()]
    #     super().accept()

    def accept(self):
        self.selected_layers = [checkbox.property(
            "layer") for checkbox in self.findChildren(QCheckBox) if checkbox.isChecked()]
        super().accept()


class MyWnd(QMainWindow):

    mapTool = None

    def __init__(self, iface):
        self.iface = iface

        QMainWindow.__init__(self, iface.mainWindow())
        self.setWindowTitle(' Gruhanaksha Polygon Splitter ')
        self.setWindowIcon(QIcon(icon))
        self.canvas = QgsMapCanvas()
        self.canvas.setCanvasColor(QColor("white"))
        self.setMinimumSize(1000, 500)

        # Set the custom map tool for feature selection
        self.featureSelectTool = FeatureSelectMapTool(self.canvas)
        self.canvas.setMapTool(self.featureSelectTool)
        self.canvas.setSelectionColor(QColor("yellow"))

        # Initialize default units
        self.current_unit_factor = UNIT_CONVERSIONS["Acres"]["factor"]
        self.current_unit_label = UNIT_CONVERSIONS["Acres"]["label"]
        self.current_unit_linear_factor = UNIT_CONVERSIONS["Acres"]["linear_factor"]
        self.current_unit_linear_label = UNIT_CONVERSIONS["Acres"]["linear_label"]
        self.current_unit_linear_factor = UNIT_CONVERSIONS["Acres"]["linear_factor"]
        self.current_unit_linear_label = UNIT_CONVERSIONS["Acres"]["linear_label"]

        # Set the initial extent of the custom canvas to match the main canvas
        main_canvas_extent = self.iface.mapCanvas().extent()
        self.canvas.setExtent(main_canvas_extent)
        # Set the CRS of the custom canvas to match the main canvas
        main_canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        self.canvas.setDestinationCrs(main_canvas_crs)

        self.layers = QgsProject.instance().mapLayers().values()
        # Store selected layers
        self.selected_layers = []

        # self.btn_layers = QPushButton("Select Layers")
        # self.btn_layers.setStyleSheet(
        #     "background-color: #020507 ; color: white")
        # self.btn_layers.clicked.connect(self.showLayerSelectDialog)

        main_layout = QVBoxLayout()
#        main_layout.addWidget(self.btn_layers)
        main_layout.addWidget(self.canvas)

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        self.createCanvasActions()

        # Initialize markers state
        self.markers = []
        self.markerItems = []
        self.canvas.extentsChanged.connect(self.redrawMarkers)

        self.on_config_changed()
    # setting snap modes by checking the main canvas snap status
        # Connecting the signal to the function without invoking it
        iface.mapCanvas().snappingUtils().configChanged.connect(self.on_config_changed)

        # Connect signals for project loading and layer changes
        QgsProject.instance().layersAdded.connect(self.updateLayers)
        QgsProject.instance().layersRemoved.connect(self.updateLayers)
        QgsProject.instance().readProject.connect(self.projectLoaded)

        # Call the initial method to set up layers
        self.updateLayers()

        # Connect signal for current layer change
        self.iface.currentLayerChanged.connect(self.activecurrentLayerChanged)

        # Get the initially active layer and add it to selected_layers
        active_layer = iface.activeLayer()
        if active_layer:
            self.selected_layers.append(active_layer)
            self.updateCanvasLayers()
            self.activecurrentLayerChanged(active_layer)
        self.iface.mapCanvas().extentsChanged.connect(self.syncCanvasExtent)

    def closeEvent(self, event):
        # Deactivate tools when window is closed
        if self.mapTool:
            if hasattr(self.mapTool, 'stopCapturing'):
                self.mapTool.stopCapturing()
            if hasattr(self.mapTool, 'deactivate'):
                self.mapTool.deactivate()
            self.canvas.unsetMapTool(self.mapTool)
            self.mapTool = None

        # Reset markers
        self.reset_markers()

        super(MyWnd, self).closeEvent(event)

    def syncCanvasExtent(self):
        # Update the custom canvas extent to match the main canvas extent
        main_canvas_extent = self.iface.mapCanvas().extent()
        self.canvas.setExtent(main_canvas_extent)
        self.canvas.refresh()

    def on_config_changed(self):
        self.canvasSnap_status = self.canvas.snappingUtils().config().enabled()
        self.snap_status = iface.mapCanvas().snappingUtils().config().enabled()

        if self.canvasSnap_status is True:
            self.actionSnapToggle.setChecked(True)

            # self.canvas.snappingUtils().toggleEnabled()
        else:
            self.actionSnapToggle.setChecked(False)

        # self.canvas.snappingUtils().setCurrentLayer(iface.activeLayer())

    def projectLoaded(self):
        # Update layers when the project is loaded
        self.updateLayers()
        self.on_config_changed()

    def updateLayers(self):
        # Include both vector and raster layers
        self.layers = [layer for layer in QgsProject.instance().mapLayers().values()
                       if layer.type() in [QgsMapLayer.VectorLayer, QgsMapLayer.RasterLayer]]

    def toggleFeatureTool(self):
        # Toggle between the FeatureSelectMapTool and other map tools
        self.canvas.setMapTool(self.toolselect)

    def toggleSnapping(self):

        self.canvas.snappingUtils().toggleEnabled()
        # print(self.canvas.snappingUtils().config().enabled())

    def reset_markers(self):
        self.markers = []
        self.redrawMarkers()

    def activecurrentLayerChanged(self, layer):
        # Update selected layers
        if layer and layer.isValid() and layer.type() == QgsMapLayer.VectorLayer:
            self.selected_layers = [layer]
            self.updateCanvasLayers()

        self.reset_markers()

        if self.mapTool:
            if hasattr(self.mapTool, 'stopCapturing'):
                self.mapTool.stopCapturing()

            # Explicitly clear captured points if present (redundant but safe)
            if hasattr(self.mapTool, 'capturedPoints'):
                self.mapTool.capturedPoints = []
                if hasattr(self.mapTool, 'redrawRubberBand'):
                    self.mapTool.redrawRubberBand()

            if hasattr(self.mapTool, 'map_tool_reset'):
                self.mapTool.map_tool_reset()

        # Disconnect previous
        prev = getattr(self, 'previous_layer', None)
        try:
            if prev:
                prev.selectionChanged.disconnect(self.onSelectionChanged)
        except (RuntimeError, Exception):
            # Layer might be deleted
            pass

        if layer and isinstance(layer, QgsVectorLayer):
            layer.selectionChanged.connect(self.onSelectionChanged)
            self.previous_layer = layer
        else:
            self.previous_layer = None

    def onSelectionChanged(self, selected, deselected, clearAndSelect):
        self.markers = []
        self.redrawMarkers()

        if self.mapTool:
            if hasattr(self.mapTool, 'stopCapturing'):
                self.mapTool.stopCapturing()
            self.canvas.refresh()

    def zoomIn(self):
        self.canvas.setMapTool(self.toolZoomIn)

    def zoomOut(self):
        self.canvas.setMapTool(self.toolZoomOut)

    def pan(self):
        self.canvas.setMapTool(self.toolPan)

    def point(self):
        self.canvas.setMapTool(self.toolPoint)

    def showLayerSelectDialog(self):
        dialog = LayerSelectDialog(self.layers, self.selected_layers)
        if QtCompat.exec(dialog) == QtCompat.DialogAccepted:
            self.selected_layers = dialog.selected_layers
            self.updateCanvasLayers()

    # def updateCanvasLayers(self):
    #     if self.selected_layers:
    #         map_layers = [layer for layer in self.selected_layers]
    #         extent = self.iface.mapCanvas().extent()
    #         self.canvas.setExtent(extent)
    #         self.canvas.setLayers(map_layers)
    def updateCanvasLayers(self):
        if self.selected_layers:
            self.canvas.setLayers(self.selected_layers)

            # If needed, adjust the extent to the main canvas
            # if not self.canvas.layers():
            main_canvas_extent = self.iface.mapCanvas().extent()
            self.canvas.setExtent(main_canvas_extent)
            self.canvas.refresh()

    def createCanvasActions(self):
        # Add a button for toggling different map tools
        self.feature_selection = QAction(QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/canvas_one/arrow.svg'))), 'Select Features', )
        self.feature_selection.setCheckable(True)
        self.feature_selection.triggered.connect(self.toggleFeatureTool)

        actionZoomIn = QAction(QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/canvas_one/zoomin.svg'))), 'Zoom In',  self)
        actionZoomOut = QAction(QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/canvas_one/zoomout.svg'))), 'Zoom Out',  self)
        actionPan = QAction(QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/canvas_one/pan.svg'))), 'Pan',  self)
        actionPoint = QAction("Point", self)
        actionPoint.setCheckable(True)
        actionZoomIn.setCheckable(True)
        actionZoomOut.setCheckable(True)
        actionPan.setCheckable(True)
        actionSelectLayers = QAction("Select Layers", self)

        actionZoomIn.triggered.connect(self.zoomIn)
        actionZoomOut.triggered.connect(self.zoomOut)
        actionPan.triggered.connect(self.pan)
        actionPoint.triggered.connect(self.point)
        actionSelectLayers.triggered.connect(self.showLayerSelectDialog)
        # Add "Select Layers" button
        self.select_layers_button = QPushButton("Select Layers", self)
        self.select_layers_button.setFixedSize(120, 30)  # Button size
        self.select_layers_button.setStyleSheet(
            "background-color: #4CAF50; color: white; border: none; border-radius: 5px;")
        self.select_layers_button.clicked.connect(self.showLayerSelectDialog)
        # Add spacer between Zoom In and Zoom Out
        spacer = QWidget()
        spacer.setSizePolicy(QtCompat.size_policy_minimum(),
                             QtCompat.size_policy_preferred())

        # Add button to the toolbar
        self.toolbar = self.addToolBar("Canvas actions")
        self.toolbar.setStyleSheet(
            "QToolBar { padding: 5px; } QPushButton { margin-right: 15px; }")

        self.toolbar.addWidget(self.select_layers_button)

        # Unit Selection Combo
        self.unit_combo = QComboBox()
        for unit_name in UNIT_CONVERSIONS.keys():
            self.unit_combo.addItem(unit_name)
        self.unit_combo.setCurrentText("Acres")
        self.unit_combo.currentIndexChanged.connect(self.changeUnit)
        self.toolbar.addWidget(self.unit_combo)
        # self.toolbar.addWidget(spacer)
        self.toolbar.addAction(self.feature_selection)
        self.toolbar.addAction(actionZoomIn)
        self.toolbar.addAction(actionZoomOut)
        self.toolbar.addAction(actionPan)
        # self.toolbar.addWidget(spacer)
        # self.toolbar.addAction(actionPoint)
        # self.toolbar.addAction(actionSelectLayers)
        self.toolPan = QgsMapToolPan(self.canvas)
        self.toolPan.setAction(actionPan)
        self.toolZoomIn = QgsMapToolZoom(self.canvas, False)
        self.toolZoomIn.setAction(actionZoomIn)
        self.toolZoomOut = QgsMapToolZoom(self.canvas, True)
        self.toolZoomOut.setAction(actionZoomOut)
        # self.toolPoint = PointMapTool(self.canvas)
        # self.toolPoint.setAction(actionPoint)
        # self.pan()
        self.toolselect = FeatureSelectMapTool(self.canvas)
        self.toolselect.setAction(self.feature_selection)

        icon = QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/canvas_one/cut.svg')))
        self.action = QAction(icon, name)
        self.action.setCheckable(True)
        self.action.triggered.connect(self.onClick)
        self.toolbar.addAction(self.action)

        self.actionMoveVertices = QAction(QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/canvas_one/movevertex.svg'))), moveVerticesName, )
        self.actionMoveVertices.setCheckable(True)
        self.actionMoveVertices.triggered.connect(self.onClickMoveVertices)
        self.toolbar.addAction(self.actionMoveVertices)

        self.actionAddVertices = QAction(QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/canvas_one/addvertex.svg'))), addVerticesName, )
        self.actionAddVertices.setCheckable(True)
        self.actionAddVertices.triggered.connect(self.onClickAddVertices)
        self.toolbar.addAction(self.actionAddVertices)

        self.actionRemoveVertices = QAction(QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/canvas_one/removevertex.svg'))), removeVerticesName, )
        self.actionRemoveVertices.setCheckable(True)
        self.actionRemoveVertices.triggered.connect(self.onClickRemoveVertices)
        self.toolbar.addAction(self.actionRemoveVertices)

        self.actionMoveSegment = QAction(QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/canvas_one/movesegment.svg'))), moveSegmentName, )
        self.actionMoveSegment.setCheckable(True)
        self.actionMoveSegment.triggered.connect(self.onClickMoveSegment)
        self.toolbar.addAction(self.actionMoveSegment)

        self.actionLineClose = QAction(QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/canvas_one/line_close.svg'))), closeLineName, )
        self.actionLineClose.setCheckable(False)
        self.actionLineClose.triggered.connect(self.onClickLineClose)
        self.toolbar.addAction(self.actionLineClose)

        self.actionLineOpen = QAction(QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/canvas_one/line_open.svg'))), openLineName, )
        self.actionLineOpen.setCheckable(False)
        self.actionLineOpen.triggered.connect(self.onClickLineOpen)
        self.toolbar.addAction(self.actionLineOpen)

        self.actionMoveLine = QAction(QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/canvas_one/moveline.svg'))), moveLineName, )
        self.actionMoveLine.setCheckable(True)
        self.actionMoveLine.triggered.connect(self.onClickMoveLine)
        self.toolbar.addAction(self.actionMoveLine)

        self.actionAreaAdjust = QAction(QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/canvas_one/area_adjust.svg'))), "Adjust Area", )
        self.actionAreaAdjust.setCheckable(False)
        self.actionAreaAdjust.triggered.connect(self.openAreaAdjuster)
        self.toolbar.addAction(self.actionAreaAdjust)

        self.iface.currentLayerChanged.connect(self.currentLayerChanged)

        # Create a toolbar button to toggle snapping mode
        self.actionSnapToggle = QAction(QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/canvas_one/snap.svg'))), "Snap", )
        self.actionSnapToggle.setCheckable(True)
        # self.actionSnapToggle.changed.connect(self.toggleSnapping)
        self.actionSnapToggle.triggered.connect(self.toggleSnapping)

        # Action for Adding Markers
        self.actionAddMarker = QAction(QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/canvas_one/point.svg'))), "Add Marker", )
        self.actionAddMarker.setCheckable(True)
        self.actionAddMarker.triggered.connect(self.onClickAddMarker)
        self.toolbar.addAction(self.actionAddMarker)

        # Add the button to the toolbar
        self.toolbar.addAction(self.actionSnapToggle)

        self.enableTool()

    def changeUnit(self):
        unit_name = self.unit_combo.currentText()
        if unit_name in UNIT_CONVERSIONS:
            data = UNIT_CONVERSIONS[unit_name]
            self.current_unit_factor = data["factor"]
            self.current_unit_label = data["label"]
            self.current_unit_linear_factor = data["linear_factor"]
            self.current_unit_linear_label = data["linear_label"]

            if self.mapTool is not None:
                if isinstance(self.mapTool, SplitMapTool):
                    self.mapTool.update_unit(
                        self.current_unit_factor, self.current_unit_label, self.current_unit_linear_factor, self.current_unit_linear_label)
                elif isinstance(self.mapTool, MarkerMapTool):
                    self.mapTool.update_unit(
                        self.current_unit_factor, self.current_unit_label, self.current_unit_linear_factor, self.current_unit_linear_label)

    def openAreaAdjuster(self):
        if self.mapTool is None or not isinstance(self.mapTool, SplitMapTool):
            QMessageBox.warning(self, "Area Adjust",
                                "Please start splitting first.")
            return

        current_areas = self.mapTool.get_current_areas()
        if not current_areas:
            QMessageBox.warning(self, "Area Adjust",
                                "No areas calculated yet. Draw a split line first.")
            return

        dialog = AreaAdjustDialog(current_areas, self.current_unit_label)
        if QtCompat.exec(dialog) == QtCompat.DialogAccepted:
            part_index, target_area = dialog.get_values()
            if part_index is not None and target_area is not None:
                self.mapTool.adjust_split_line(part_index, target_area)

    def disableAll(self):
        self.actionMoveVertices.setChecked(False)
        self.actionMoveVertices.setEnabled(False)
        self.actionAddVertices.setChecked(False)
        self.actionAddVertices.setEnabled(False)
        self.actionRemoveVertices.setChecked(False)
        self.actionRemoveVertices.setEnabled(False)
        self.actionMoveSegment.setChecked(False)
        self.actionMoveSegment.setEnabled(False)
        self.actionLineClose.setEnabled(False)
        self.actionLineOpen.setEnabled(False)
        self.actionMoveLine.setChecked(False)
        self.actionMoveLine.setChecked(False)
        self.actionMoveLine.setEnabled(False)
        self.actionMoveLine.setEnabled(False)
        self.actionAreaAdjust.setEnabled(False)
        self.actionAddMarker.setChecked(False)
        self.actionAddMarker.setEnabled(False)

    def onClick(self):
        # print("onclick")
        self.disableAll()
        if not self.action.isChecked():
            if self.mapTool != None and hasattr(self.mapTool, 'capturedPoints') and len(self.mapTool.capturedPoints) >= 2:
                reply = QtCompat.message_box_question(self.canvas, "Cancel splitting line?", "Your splitting line has " + str(
                    len(self.mapTool.capturedPoints)) + " points. Do you want to remove it?", QtCompat.Yes, QtCompat.No)
                if reply == QMessageBox.No:
                    self.action.setChecked(True)
                    self.mapTool.restoreAction()
                    return

            if self.mapTool != None:
                if hasattr(self.mapTool, 'deactivate'):
                    self.mapTool.deactivate()
                self.mapTool.stopCapturing()

            self.canvas.unsetMapTool(self.mapTool)
            self.mapTool = None
            self.actionAddMarker.setChecked(False)  # Turn off Marker button
            return
        layer = self.iface.activeLayer()
        if layer == None or not isinstance(layer, QgsVectorLayer) or (layer.wkbType() != QgsWkbTypes.Polygon and layer.wkbType() != QgsWkbTypes.MultiPolygon and layer.wkbType() != QgsWkbTypes.Polygon25D and layer.wkbType() != QgsWkbTypes.MultiPolygon25D):
            # self.canvas.messageBar().pushMessage("No Polygon Vectorial Layer Selected",
            #                                      "Select a Polygon Vectorial Layer first", level=QgsMessageBar.WARNING)

            messagebar = MessageBar(self.canvas)
            messagebar.pushMessage(
                "No Polygon Vectorial Layer Selected",
                "Select a Polygon Vectorial Layer first", 1, 3)

            self.action.setChecked(False)
            return
        selectedFeatures = layer.selectedFeatures()
        if selectedFeatures == None or len(selectedFeatures) == 0:

            messagebar = MessageBar(self.canvas)
            messagebar.pushMessage(
                "No Features Selected", "Select some features first", 1, 3)

        self.action.setChecked(True)
        self.actionAddMarker.setChecked(False)  # Mutual exclusion

        # Deactivate previous tool properly
        if self.mapTool:
            if hasattr(self.mapTool, 'deactivate'):
                self.mapTool.deactivate()
            # Also stop capturing if needed
            if hasattr(self.mapTool, 'stopCapturing'):
                self.mapTool.stopCapturing()
            self.canvas.unsetMapTool(self.mapTool)

        self.enableTool()
        self.mapTool = SplitMapTool(self.canvas, layer, self.actionMoveVertices, self.actionAddVertices,
                                    self.actionRemoveVertices, self.actionMoveSegment, self.actionLineClose, self.actionLineOpen, self.actionMoveLine, self.actionAreaAdjust, self.actionAddMarker, markers=self.markers, on_split=self.reset_markers)
        self.mapTool.setAction(self.action)
        self.canvas.setMapTool(self.mapTool)
        self.mapTool.setAction(self.action)
        self.canvas.setMapTool(self.mapTool)
        self.mapTool.update_unit(
            self.current_unit_factor, self.current_unit_label, self.current_unit_linear_factor, self.current_unit_linear_label)
        self.mapTool.redrawActions()

    def onClickMoveVertices(self):
        if not self.actionMoveVertices.isChecked():
            if self.mapTool != None:
                self.mapTool.stopMovingVertices()
            return

        self.mapTool.startMovingVertices()

    def onClickAddVertices(self):
        if not self.actionAddVertices.isChecked():
            if self.mapTool != None:
                self.mapTool.stopAddingVertices()
            return

        self.actionAddVertices.setChecked(True)
        self.mapTool.startAddingVertices()

    def onClickRemoveVertices(self):
        if not self.actionRemoveVertices.isChecked():
            if self.mapTool != None:
                self.mapTool.stopRemovingVertices()
            return

        self.actionRemoveVertices.setChecked(True)
        self.mapTool.startRemovingVertices()

    def onClickMoveSegment(self):
        if not self.actionMoveSegment.isChecked():
            if self.mapTool != None:
                self.mapTool.stopMovingSegment()
            return

        self.actionMoveSegment.setChecked(True)
        self.mapTool.startMovingSegment()

    def onClickLineClose(self):
        self.mapTool.lineClose()

    def onClickLineOpen(self):
        self.mapTool.lineOpen()

    def onClickMoveLine(self):
        if not self.actionMoveLine.isChecked():
            if self.mapTool != None:
                self.mapTool.stopMovingLine()
            return

        self.actionMoveLine.setChecked(True)
        self.mapTool.startMovingLine()

    def redrawMarkers(self):
        # Clear existing visual markers
        for item in self.markerItems:
            if item.scene() == self.canvas.scene():
                self.canvas.scene().removeItem(item)
        self.markerItems = []

        unit = getattr(self, "current_unit_linear_label", "m")

        for marker in self.markers:
            pt = marker['point']
            dist = marker['dist']
            dist2 = marker.get('dist2')
            ref = marker.get('ref')
            ref2 = marker.get('ref2')

            canvas_pt = self.canvas.getCoordinateTransform().transform(pt)

            rect = self.canvas.scene().addRect(canvas_pt.x() - 4, canvas_pt.y() -
                                               4, 8, 8, QPen(QColor("red")), QBrush(QColor("red")))
            self.markerItems.append(rect)

            # Draw Labels
            if dist2 is not None and ref is not None and ref2 is not None:
                # Label 1 (Marker <-> Ref)
                mid1 = QgsPointXY((pt.x() + ref.x()) / 2,
                                  (pt.y() + ref.y()) / 2)
                canvas_mid1 = self.canvas.getCoordinateTransform().transform(mid1)

                label1 = QGraphicsTextItem()
                label1.setHtml(
                    f"<div style='background-color: white; border: 1px solid red; padding: 1px; font-size: 10px;'>{dist:.2f} {unit}</div>")
                # Set text color for Qt6 compatibility
                label1.setDefaultTextColor(QColor("red"))
                label1.setPos(canvas_mid1.x(), canvas_mid1.y())
                self.canvas.scene().addItem(label1)
                self.markerItems.append(label1)

                # Label 2 (Marker <-> Ref2)
                mid2 = QgsPointXY((pt.x() + ref2.x()) / 2,
                                  (pt.y() + ref2.y()) / 2)
                canvas_mid2 = self.canvas.getCoordinateTransform().transform(mid2)

                label2 = QGraphicsTextItem()
                label2.setHtml(
                    f"<div style='background-color: white; border: 1px solid red; padding: 1px; font-size: 10px;'>{dist2:.2f} {unit}</div>")
                # Set text color for Qt6 compatibility
                label2.setDefaultTextColor(QColor("red"))
                label2.setPos(canvas_mid2.x(), canvas_mid2.y())
                self.canvas.scene().addItem(label2)
                self.markerItems.append(label2)

            else:
                label = QGraphicsTextItem()
                if dist2 is not None:
                    content = f"{dist:.2f} {unit} <br> {dist2:.2f} {unit}"
                else:
                    content = f"{dist:.2f} {unit}"

                label.setHtml(
                    f"<div style='background-color: white; border: 1px solid red; padding: 1px; font-size: 10px;'>{content}</div>")
                # Set text color for Qt6 compatibility
                label.setDefaultTextColor(QColor("red"))
                label.setPos(canvas_pt.x() + 8, canvas_pt.y() + 8)
                self.canvas.scene().addItem(label)
                self.markerItems.append(label)

    def onClickAddMarker(self):
        if not self.actionAddMarker.isChecked():
            # Deactivate tool if needed, switch to Pan or previous
            if self.mapTool:
                self.mapTool.deactivate()
            self.canvas.unsetMapTool(self.mapTool)
            return

        self.disableAll()
        self.actionAddMarker.setChecked(True)
        self.action.setChecked(False)  # Mutual exclusion

        # Deactivate previous tool properly
        if self.mapTool:
            if hasattr(self.mapTool, 'deactivate'):
                self.mapTool.deactivate()
            if hasattr(self.mapTool, 'stopCapturing'):
                self.mapTool.stopCapturing()
            self.canvas.unsetMapTool(self.mapTool)

        layer = self.iface.activeLayer()
        if layer and isinstance(layer, QgsVectorLayer):
            # Initialize Marker Tool
            # Pass current linear units
            linear_factor = getattr(self, "current_unit_linear_factor", 1.0)
            linear_label = getattr(self, "current_unit_linear_label", "m")

            self.mapTool = MarkerMapTool(
                self.canvas, layer, self.markers, unit_factor=linear_factor, unit_label=linear_label)
            # Callback to update UI when marker added
            self.mapTool.redraw_callback = self.redrawMarkers

            self.canvas.setMapTool(self.mapTool)
            self.mapTool.activate()

            self.redrawMarkers()
        else:
            self.actionAddMarker.setChecked(False)

    def currentLayerChanged(self):
        if self.mapTool != None:
            self.mapTool.stopCapturing()

        layer = self.iface.activeLayer()
        if layer != None:
            try:
                layer.editingStarted.disconnect(self.layerEditingChanged)
            except:
                pass
            try:
                layer.editingStopped.disconnect(self.layerEditingChanged)
            except:
                pass
            try:
                layer.selectionChanged .disconnect(self.layerEditingChanged)
            except:
                pass

            if isinstance(layer, QgsVectorLayer):
                layer.editingStarted.connect(self.layerEditingChanged)
                layer.editingStopped.connect(self.layerEditingChanged)
                layer.selectionChanged.connect(self.layerSelectionChanged)

        self.enableTool()

    def layerEditingChanged(self):
        if self.mapTool != None:
            self.mapTool.stopCapturing()
        self.enableTool()

    def layerSelectionChanged(self):
        if self.mapTool != None:
            self.mapTool.stopCapturing()
        self.enableTool()

    def enableTool(self):
        self.disableAll()
        self.action.setEnabled(True)
        layer = self.iface.activeLayer()

        if layer != None and isinstance(layer, QgsVectorLayer):
            selectedFeatures = layer.selectedFeatures()
            isPolygon = (layer.wkbType() == QgsWkbTypes.Polygon or layer.wkbType() == QgsWkbTypes.MultiPolygon or layer.wkbType(
            ) == QgsWkbTypes.Polygon25D or layer.wkbType() == QgsWkbTypes.MultiPolygon25D)
            hasSelection = selectedFeatures is not None and len(
                selectedFeatures) > 0

            if isPolygon and hasSelection:
                self.actionAddMarker.setEnabled(True)
                # Keep action enabled logic consistent
                if layer.isEditable():
                    self.action.setEnabled(True)


class SplitMapTool(QgsMapToolEdit):
    snapClicked = pyqtSignal(QgsPointXY, int)

    def __init__(self, canvas, layer, actionMoveVertices, actionAddVertices, actionRemoveVertices, actionMoveSegment, actionLineClose, actionLineOpen, actionMoveLine, actionAreaAdjust, actionAddMarker, markers=None, on_split=None):
        super(SplitMapTool, self).__init__(canvas)
        self.markers = markers if markers is not None else []
        self.on_split = on_split
        self.canvas = canvas

        self.snapIndicator = QgsSnapIndicator(canvas)
        self.snapper = canvas.snappingUtils()
        self.scene = canvas.scene()
        self.layer = layer
        self.actionMoveVertices = actionMoveVertices
        self.actionAddVertices = actionAddVertices
        self.actionRemoveVertices = actionRemoveVertices
        self.actionMoveSegment = actionMoveSegment
        self.actionLineClose = actionLineClose
        self.actionLineOpen = actionLineOpen
        self.actionMoveLine = actionMoveLine
        self.actionMoveLine = actionMoveLine
        self.actionAreaAdjust = actionAreaAdjust
        self.actionAddMarker = actionAddMarker
        self.movingLineInitialPoint = None
        self.initialize()

    def initialize(self):
        try:
            self.canvas.renderStarting.disconnect(self.mapCanvasChanged)
        except:
            pass
        self.canvas.renderStarting.connect(self.mapCanvasChanged)
        try:
            self.layer.editingStopped.disconnect(self.stopCapturing)
        except:
            pass
        self.layer.editingStopped.connect(self.stopCapturing)

        self.selectedFeatures = self.layer.selectedFeatures()
        self.rubberBand = None
        self.tempRubberBand = None
        self.capturedPoints = []
        self.capturing = False
        self.setCursor(QtCompat.cross_cursor())
        self.proj = QgsProject.instance()
        self.labels = []
        self.segmentLabels = []
        self.vertices = []
        self.calculator = QgsDistanceArea()
        self.calculator.setSourceCrs(self.layer.dataProvider(
        ).crs(), QgsProject.instance().transformContext())
        # self.layer.dataProvider().crs().ellipsoidAcronym()
        self.calculator.setEllipsoid(None)
        self.drawingLine = False
        self.movingVertices = False
        self.addingVertices = False
        self.removingVertices = False
        self.movingSegment = False
        self.movingLine = False
        self.showingVertices = False
        self.movingVertex = -1
        self.movingSegm = -1
        self.movingLineInitialPoint = None
        self.lineClosed = False
        self.unit_factor = 0.000247105381  # default Acres
        self.unit_label = "ac"
        self.unit_linear_factor = 3.28084
        self.unit_linear_label = "ft"

        self.unit_linear_label = "ft"

    def update_unit(self, factor, label, linear_factor=1.0, linear_label="m"):
        self.unit_factor = factor
        self.unit_label = label
        self.unit_linear_factor = linear_factor
        self.unit_linear_label = linear_label
        self.redrawAreas()

    def restoreAction(self):
        self.addingVertices = False
        self.removingVertices = False
        self.movingVertices = False
        self.movingSegment = False
        self.movingLine = False
        self.showingVertices = False
        self.showingVertices = False
        self.drawingLine = True
        self.movingVertex = -1
        self.movingLineInitialPoint = None
        self.deleteVertices()
        self.redrawRubberBand()
        self.redrawTempRubberBand()
        self.canvas.scene().addItem(self.tempRubberBand)
        self.redrawActions()

    def mapCanvasChanged(self):
        self.redrawAreas()

        if self.showingVertices:
            self.redrawVertices()

    def canvasMoveEvent(self, event):
        snapMatch = self.snapper.snapToMap(event.pos())
        self.snapIndicator.setMatch(snapMatch)

        if self.drawingLine and not self.lineClosed:
            if self.tempRubberBand is not None and self.capturing:
                if snapMatch.type():
                    mapPoint = snapMatch.point()
                else:
                    mapPoint = self.toMapCoordinates(event.pos())

                self.tempRubberBand.movePoint(mapPoint)
                self.redrawAreas(event.pos())

        if self.movingVertices and self.movingVertex >= 0:
            snapped = False
            layerPoint = None

            # 1. Try snapping to markers
            xform = self.canvas.mapSettings().layerTransform(self.layer)
            mouse_canvas_pt = event.pos()
            for marker in self.markers:
                marker_layer_pt = marker['point']
                marker_map_pt = xform.transform(marker_layer_pt)
                marker_canvas_pt = self.toCanvasCoordinates(marker_map_pt)
                dist = sqrt((marker_canvas_pt.x() - mouse_canvas_pt.x())**2 +
                            (marker_canvas_pt.y() - mouse_canvas_pt.y())**2)
                if dist < 10:
                    layerPoint = marker_layer_pt
                    snapped = True
                    break

            # 2. Try standard snapping if no marker snap
            if not snapped:
                if snapMatch.type():
                    layerPoint = snapMatch.point()
                else:
                    layerPoint = self.toLayerCoordinates(
                        self.layer, event.pos())

            self.capturedPoints[self.movingVertex] = layerPoint

            if self.lineClosed and self.movingVertex == 0:
                self.capturedPoints[len(self.capturedPoints) - 1] = layerPoint

            self.redrawRubberBand()
            self.redrawVertices()
            self.redrawAreas()

        if self.movingSegment and self.movingSegm >= 0:
            # print('movingSegment')

            currentPoint = self.toLayerCoordinates(self.layer, event.pos())
            if snapMatch.type():
                snappedPoint = snapMatch.point()
                currentPoint = snappedPoint
            distance = self.distancePoint(
                currentPoint, self.movingLineInitialPoint)
            bearing = self.movingLineInitialPoint.azimuth(currentPoint)

            self.capturedPoints[self.movingSegm] = self.projectPoint(
                self.capturedPoints[self.movingSegm], distance, bearing)
            self.capturedPoints[self.movingSegm + 1] = currentPoint

            if self.lineClosed:
                if self.movingSegm == 0:
                    self.capturedPoints[len(self.capturedPoints) - 1] = self.projectPoint(
                        self.capturedPoints[len(self.capturedPoints) - 1], distance, bearing)
                elif self.movingSegm == len(self.capturedPoints) - 2:
                    self.capturedPoints[0] = self.projectPoint(
                        self.capturedPoints[0], distance, bearing)

            self.redrawRubberBand()
            self.redrawVertices()
            self.redrawAreas()
            self.movingLineInitialPoint = currentPoint

        if self.movingLine and self.movingLineInitialPoint != None:
            currentPoint = self.toLayerCoordinates(self.layer, event.pos())
            if snapMatch.type():
                snappedPoint = snapMatch.point()
                currentPoint = snappedPoint

            distance = self.distancePoint(
                currentPoint, self.movingLineInitialPoint)
            bearing = self.movingLineInitialPoint.azimuth(currentPoint)

            for i in range(len(self.capturedPoints)):
                self.capturedPoints[i] = self.projectPoint(
                    self.capturedPoints[i], distance, bearing)
            self.redrawRubberBand()
            self.redrawAreas()
            self.movingLineInitialPoint = currentPoint

        # Check snap to markers when drawing split line
        if self.drawingLine and self.capturing:
            xform = self.canvas.mapSettings().layerTransform(self.layer)
            mouse_canvas_pt = event.pos()
            snapped = False

            for marker in self.markers:
                marker_layer_pt = marker['point']
                marker_map_pt = xform.transform(marker_layer_pt)
                marker_canvas_pt = self.toCanvasCoordinates(marker_map_pt)

                dist = sqrt((marker_canvas_pt.x() - mouse_canvas_pt.x())**2 +
                            (marker_canvas_pt.y() - mouse_canvas_pt.y())**2)

                if dist < 10:  # Snap tolerance in pixels
                    self.tempRubberBand.movePoint(marker_map_pt)
                    snapped = True
                    break

            if snapped:
                return

    def projectPoint(self, point, distance, bearing):
        rads = bearing * pi / 180.0
        dx = distance * sin(rads)
        dy = distance * cos(rads)
        return QgsPointXY(point.x() + dx, point.y() + dy)

    def get_segments_set(self, geometry):
        segments = set()
        if not geometry:
            return segments

        # Handle Multipart
        if geometry.isMultipart():
            for part in geometry.asGeometryCollection():
                segments.update(self.get_segments_set(part))
            return segments

        poly = geometry.asPolygon()
        if not poly:
            return segments

        ring = poly[0]
        for i in range(len(ring) - 1):
            p1 = ring[i]
            p2 = ring[i+1]
            # Create a frozen set of coordinate pairs rounded to 4 decimals for robust comparison
            # Order independent (p1, p2) is same segment as (p2, p1)
            pt1 = (round(p1.x(), 4), round(p1.y(), 4))
            pt2 = (round(p2.x(), 4), round(p2.y(), 4))
            segments.add(frozenset([pt1, pt2]))

        return segments

    def redrawAreas(self, mousePos=None):
        self.deleteLabels()

        if self.capturing and len(self.capturedPoints) > 0:
            for i, feature in enumerate(self.selectedFeatures):
                geometry = QgsGeometry(feature.geometry())

                # Capture original segments before split
                original_segments = self.get_segments_set(geometry)

                movingPoints = list(self.capturedPoints)

                skip_segments = set()
                if mousePos != None:
                    movingPoints.append(
                        self.toLayerCoordinates(self.layer, mousePos))

                    # Identify dynamic segment to skip labeling
                    if len(movingPoints) > 1:
                        p_last = movingPoints[-1]
                        p_prev = movingPoints[-2]
                        pt1 = (round(p_last.x(), 4), round(p_last.y(), 4))
                        pt2 = (round(p_prev.x(), 4), round(p_prev.y(), 4))
                        skip_segments.add(frozenset([pt1, pt2]))

                result, newGeometries, topoTestPoints = geometry.splitGeometry(
                    movingPoints, self.proj.topologicalEditing())

                self.addLabel(geometry)
                self.addSegmentLabels(
                    geometry, original_segments, skip_segments)
                if newGeometries != None and len(newGeometries) > 0:
                    for geometry in newGeometries:
                        self.addLabel(geometry)
                        self.addSegmentLabels(
                            geometry, original_segments)

    def addLabel(self, geometry):
        area = self.calculator.measureArea(geometry) * self.unit_factor
        labelPoint = geometry.pointOnSurface().vertexAt(0)
        label = QGraphicsTextItem("%.3f" % area)
        # Set BEFORE setHtml for Qt6
        label.setDefaultTextColor(QColor("white"))
        label.setHtml("<div style=\"background:#111111;padding:5px\">"
                      + "%.3f" % area + " " + self.unit_label
                      + "</div>")
        point = self.toMapCoordinatesV2(self.layer, labelPoint)

        canvas_point = self.toCanvasCoordinates(
            QgsPointXY(point.x(), point.y()))
        label.setPos(QPointF(canvas_point.x(), canvas_point.y()))
        #  # print(area)
        self.scene.addItem(label)
        self.labels.append(label)

    def addSegmentLabels(self, geometry, original_segments=None, skip_segments=None):
        if not geometry:
            return

        # Handle Multipart
        if geometry.isMultipart():
            for part in geometry.asGeometryCollection():
                self.addSegmentLabels(part, original_segments)
            return

        # Extract vertices. Iterating ring.
        poly = geometry.asPolygon()
        if not poly:
            return

        # Outer ring
        ring = poly[0]
        # Iterate points, drawing label for each segment
        for i in range(len(ring) - 1):
            p1 = ring[i]
            p2 = ring[i+1]

            # Check filtering
            if original_segments is not None:
                pt1 = (round(p1.x(), 4), round(p1.y(), 4))
                pt2 = (round(p2.x(), 4), round(p2.y(), 4))
                seg_id = frozenset([pt1, pt2])
                if seg_id in original_segments:
                    continue  # Skip this segment as it is from original geometry

            if skip_segments is not None:
                pt1 = (round(p1.x(), 4), round(p1.y(), 4))
                pt2 = (round(p2.x(), 4), round(p2.y(), 4))
                seg_id = frozenset([pt1, pt2])
                if seg_id in skip_segments:
                    continue

            # Distance in meters (assumed measureLine default)
            dist_val = self.calculator.measureLine(p1, p2)
            dist = dist_val * self.unit_linear_factor

            # Midpoint calculation for label placement
            mid_x = (p1.x() + p2.x()) / 2
            mid_y = (p1.y() + p2.y()) / 2
            mid_point = QgsPointXY(mid_x, mid_y)

            label = QGraphicsTextItem("%.2f" % dist)
            # Set BEFORE setHtml for Qt6
            label.setDefaultTextColor(QColor("white"))
            label.setHtml("<div style=\"background:#111111;padding:3px\">"
                          + "%.2f" % dist + " " + self.unit_linear_label
                          + "</div>")

            # Position on canvas
            canvas_pt = self.toCanvasCoordinates(mid_point)
            label.setPos(QPointF(canvas_pt))

            self.scene.addItem(label)
            self.segmentLabels.append(label)

    def deleteLabels(self):
        for label in self.labels:
            self.scene.removeItem(label)
        self.labels = []
        for label in self.segmentLabels:
            self.scene.removeItem(label)
        self.segmentLabels = []

    def canvasPressEvent(self, event):
        snapMatch = self.snapIndicator.match()

        if self.movingVertices:
            # Find the vertex to move by checking distance to cursor
            for i, layerPt in enumerate(self.capturedPoints):
                mapPt = self.toMapCoordinates(self.layer, layerPt)
                canvasPt = self.toCanvasCoordinates(
                    QgsPointXY(mapPt.x(), mapPt.y()))

                if self.distancePoint(event.pos(), canvasPt) <= maxDistanceHitTest:
                    self.movingVertex = i
                    break

        if self.movingSegment:

            for i in range(len(self.capturedPoints) - 1):
                vertex1 = self.toMapCoordinates(
                    self.layer, self.capturedPoints[i])
                currentVertex1 = self.toCanvasCoordinates(
                    QgsPointXY(vertex1.x(), vertex1.y()))
                vertex2 = self.toMapCoordinates(
                    self.layer, self.capturedPoints[i + 1])
                currentVertex2 = self.toCanvasCoordinates(
                    QgsPointXY(vertex2.x(), vertex2.y()))
                if self.distancePointLine(event.pos().x(), event.pos().y(), currentVertex1.x(), currentVertex1.y(), currentVertex2.x(), currentVertex2.y()) <= maxDistanceHitTest:
                    self.movingSegm = i
                    break

        self.movingLineInitialPoint = self.toLayerCoordinates(
            self.layer, event.pos())

    def distancePoint(self, eventPos, vertexPos):
        return sqrt((eventPos.x() - vertexPos.x())**2 + (eventPos.y() - vertexPos.y())**2)

    def canvasReleaseEvent(self, event):
        # print("canvas relase event")
        if self.movingVertices or self.movingSegment or self.movingLine:
            if event.button() == QtCompat.RightButton:
                self.finishOperation()
        elif self.addingVertices:
            if event.button() == QtCompat.LeftButton:
                self.addVertex(event.pos())
            elif event.button() == QtCompat.RightButton:
                self.finishOperation()
        elif self.removingVertices:
            if event.button() == QtCompat.LeftButton:
                self.removeVertex(event.pos())
            elif event.button() == QtCompat.RightButton:
                self.finishOperation()

        else:
            if event.button() == QtCompat.LeftButton:
                if not self.lineClosed:
                    if not self.capturing:
                        self.startCapturing()
                    self.addEndingVertex(event.pos())
            elif event.button() == QtCompat.RightButton:
                self.finishOperation()

        self.movingVertex = -1
        self.movingSegm = -1
        self.movingLineInitialPoint = None
        self.redrawActions()

    def keyReleaseEvent(self, event):
        if event.key() == QtCompat.Key_Escape:
            self.stopCapturing()
        if event.key() == QtCompat.Key_Backspace or event.key() == QtCompat.Key_Delete:
            self.removeLastVertex()
        if event.key() == QtCompat.Key_Return or event.key() == QtCompat.Key_Enter:
            self.finishOperation()

        event.accept()
        self.redrawActions()

    def finishOperation(self):
        self.doSplit()
        self.stopCapturing()
        if self.on_split:
            self.on_split()
        self.initialize()
        self.startCapturing()

    def doSplit(self):
        if self.capturedPoints != None:
            # Check if layer is in edit mode
            if not self.layer.isEditable():
                self.layer.startEditing()
                if not self.layer.isEditable():
                    # If still not editable (e.g. failed to start editing), return
                    return

            self.layer.splitFeatures(
                self.capturedPoints, self.proj.topologicalEditing())

    def startCapturing(self):
        self.prepareRubberBand()
        self.prepareTempRubberBand()

        self.drawingLine = True
        self.capturing = True

        self.redrawActions()

    def prepareRubberBand(self):
        color = QColor("red")
        color.setAlphaF(0.78)

        self.rubberBand = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.rubberBand.setWidth(1)
        self.rubberBand.setColor(color)
        self.rubberBand.show()

    def prepareTempRubberBand(self):
        color = QColor("red")
        color.setAlphaF(0.78)

        self.tempRubberBand = QgsRubberBand(
            self.canvas, QgsWkbTypes.LineGeometry)
        self.tempRubberBand.setWidth(1)
        self.tempRubberBand.setColor(color)
        self.tempRubberBand.setLineStyle(QtCompat.DotLine)
        self.tempRubberBand.show()

    def redrawRubberBand(self):
        self.canvas.scene().removeItem(self.rubberBand)
        self.prepareRubberBand()
        for i, point in enumerate(self.capturedPoints):
            if point.__class__ == QgsPoint:
                vertexCoord = self.toMapCoordinatesV2(
                    self.layer, self.capturedPoints[i])
                vertexCoord = QgsPointXY(vertexCoord.x(), vertexCoord.y())
            else:
                vertexCoord = self.toMapCoordinates(
                    self.layer, self.capturedPoints[i])

            self.rubberBand.addPoint(vertexCoord)

    def redrawTempRubberBand(self):
        if self.tempRubberBand != None:
            self.tempRubberBand.reset(QgsWkbTypes.LineGeometry)
            self.tempRubberBand.addPoint(self.toMapCoordinates(
                self.layer, self.capturedPoints[len(self.capturedPoints) - 1]))

    def deactivate(self):
        self.stopCapturing()
        super(SplitMapTool, self).deactivate()

    def stopCapturing(self):
        self.deleteLabels()
        self.deleteVertices()
        if self.rubberBand:
            self.canvas.scene().removeItem(self.rubberBand)
            self.rubberBand = None
        if self.tempRubberBand:
            self.canvas.scene().removeItem(self.tempRubberBand)
            self.tempRubberBand = None
        self.drawingLine = False
        self.movingVertices = False
        self.showingVertices = False
        self.capturing = False
        self.capturedPoints = []
        self.canvas.refresh()

        self.redrawActions()

    def addEndingVertex(self, canvasPoint):
        # print('addend')
        xform = self.canvas.mapSettings().layerTransform(self.layer)
        snapped_marker_pt = None

        for marker in self.markers:
            marker_layer_pt = marker['point']
            marker_map_pt = xform.transform(marker_layer_pt)
            marker_canvas_pt = self.toCanvasCoordinates(marker_map_pt)
            dist = sqrt((marker_canvas_pt.x() - canvasPoint.x())**2 +
                        (marker_canvas_pt.y() - canvasPoint.y())**2)
            if dist < 10:
                snapped_marker_pt = marker_map_pt
                break

        if snapped_marker_pt:
            mapPoint = snapped_marker_pt
        else:
            snapMatch = self.snapper.snapToMap(canvasPoint)
            if snapMatch.type():
                mapPoint = snapMatch.point()
            else:
                mapPoint = self.toMapCoordinates(canvasPoint)

        layerPoint = self.toLayerCoordinates(self.layer, mapPoint)

        self.rubberBand.addPoint(mapPoint)
        self.capturedPoints.append(layerPoint)

        self.tempRubberBand.reset(QgsWkbTypes.LineGeometry)
        self.tempRubberBand.addPoint(mapPoint)

    def removeLastVertex(self):
        if not self.capturing:
            return

        rubberBandSize = self.rubberBand.numberOfVertices()
        tempRubberBandSize = self.tempRubberBand.numberOfVertices()
        numPoints = len(self.capturedPoints)

        if rubberBandSize < 1 or numPoints < 1:
            return

        self.rubberBand.removePoint(-1)

        if rubberBandSize > 1:
            if tempRubberBandSize > 1:
                point = self.rubberBand.getPoint(0, rubberBandSize-2)
                self.tempRubberBand.movePoint(tempRubberBandSize-2, point)
        else:
            self.tempRubberBand.reset(self.bandType())

        del self.capturedPoints[-1]

    def addVertex(self, pos):
        # print('addvertex')
        newCapturedPoints = []
        for i in range(len(self.capturedPoints) - 1):
            newCapturedPoints.append(self.capturedPoints[i])
            vertex1 = self.toMapCoordinates(self.layer, self.capturedPoints[i])
            currentVertex1 = self.toCanvasCoordinates(
                QgsPointXY(vertex1.x(), vertex1.y()))
            vertex2 = self.toMapCoordinates(
                self.layer, self.capturedPoints[i + 1])
            currentVertex2 = self.toCanvasCoordinates(
                QgsPointXY(vertex2.x(), vertex2.y()))

            distance = self.distancePointLine(pos.x(), pos.y(), currentVertex1.x(
            ), currentVertex1.y(), currentVertex2.x(), currentVertex2.y())
            if distance <= maxDistanceHitTest:
                layerPoint = self.toLayerCoordinates(self.layer, pos)
                newCapturedPoints.append(layerPoint)

        newCapturedPoints.append(
            self.capturedPoints[len(self.capturedPoints) - 1])
        self.capturedPoints = newCapturedPoints

        self.redrawRubberBand()
        self.redrawVertices()
        self.redrawAreas()
        self.redrawActions()

    def removeVertex(self, pos):
        deletedFirst = False
        deletedLast = False
        newCapturedPoints = []
        for i, point in enumerate(self.capturedPoints):
            vertex = self.toMapCoordinates(self.layer, point)
            currentVertex = self.toCanvasCoordinates(
                QgsPointXY(vertex.x(), vertex.y()))
            if not self.distancePoint(pos, currentVertex) <= maxDistanceHitTest:
                newCapturedPoints.append(point)
            elif i == 0:
                deletedFirst = True
            elif i == len(self.capturedPoints) - 1:
                deletedLast = True

        self.capturedPoints = newCapturedPoints

        if deletedFirst and deletedLast:
            self.lineClosed = False

        self.redrawRubberBand()
        self.redrawVertices()
        self.redrawAreas()
        self.redrawActions()

        if len(self.capturedPoints) <= 2:
            self.stopRemovingVertices()

    def startMovingVertices(self):
        self.stopMovingLine()
        self.stopAddingVertices()
        self.stopRemovingVertices()
        self.stopMovingSegment()

        self.actionMoveVertices.setChecked(True)
        self.movingVertices = True
        self.showingVertices = True
        self.drawingLine = False
        self.canvas.scene().removeItem(self.tempRubberBand)
        self.redrawVertices()
        self.redrawAreas()
        self.redrawActions()

    def stopMovingVertices(self):
        self.movingVertices = False
        self.actionMoveVertices.setChecked(False)
        self.restoreAction()

    def startAddingVertices(self):
        self.stopMovingVertices()
        self.stopRemovingVertices()
        self.stopMovingLine()
        self.stopMovingSegment()

        self.actionAddVertices.setChecked(True)
        self.addingVertices = True
        self.showingVertices = True
        self.drawingLine = False
        self.canvas.scene().removeItem(self.tempRubberBand)
        self.redrawVertices()
        self.redrawAreas()
        self.redrawActions()

    def stopAddingVertices(self):
        self.addVertices = False
        self.actionAddVertices.setChecked(False)
        self.restoreAction()

    def startRemovingVertices(self):
        self.stopMovingVertices()
        self.stopAddingVertices()
        self.stopMovingLine()
        self.stopMovingSegment()

        self.actionRemoveVertices.setChecked(True)
        self.removingVertices = True
        self.showingVertices = True
        self.drawingLine = False
        self.canvas.scene().removeItem(self.tempRubberBand)
        self.redrawVertices()
        self.redrawAreas()
        self.redrawActions()

    def stopRemovingVertices(self):
        self.removingVertices = False
        self.actionRemoveVertices.setChecked(False)
        self.restoreAction()

    def startMovingSegment(self):
        self.stopMovingVertices()
        self.stopMovingLine()
        self.stopAddingVertices()
        self.stopRemovingVertices()

        self.actionMoveSegment.setChecked(True)
        self.movingSegment = True
        self.showingVertices = True
        self.drawingLine = False
        self.canvas.scene().removeItem(self.tempRubberBand)
        self.redrawVertices()
        self.redrawAreas()
        self.redrawActions()

    def stopMovingSegment(self):
        self.movingSegment = False
        self.actionMoveSegment.setChecked(False)
        self.restoreAction()

    def startMovingLine(self):
        self.stopMovingVertices()
        self.stopAddingVertices()
        self.stopRemovingVertices()
        self.stopMovingSegment()

        self.actionMoveLine.setChecked(True)
        self.movingLine = True
        self.showingVertices = True
        self.drawingLine = False
        self.canvas.scene().removeItem(self.tempRubberBand)
        self.redrawAreas()
        self.redrawActions()

    def stopMovingLine(self):
        self.actionMoveLine.setChecked(False)
        self.restoreAction()

    def lineClose(self):
        self.lineClosed = True
        self.capturedPoints.append(self.capturedPoints[0])
        self.redrawRubberBand()
        self.redrawTempRubberBand()
        self.redrawAreas()
        self.redrawActions()

    def lineOpen(self):
        self.lineClosed = False
        del self.capturedPoints[-1]
        self.redrawRubberBand()
        self.redrawTempRubberBand()
        self.redrawAreas()
        self.redrawActions()

    def showVertices(self):
        for i, point in enumerate(self.capturedPoints):
            vertexc = self.toMapCoordinates(self.layer, point)
            vertexCoords = self.toCanvasCoordinates(
                QgsPointXY(vertexc.x(), vertexc.y()))
            if i == self.movingVertex:
                vertex = self.scene.addRect(vertexCoords.x(
                ) - 5, vertexCoords.y() - 5, 10, 10, QPen(QColor("green")), QBrush(QColor("green")))
                self.vertices.append(vertex)
            elif i == len(self.capturedPoints) - 1 and self.movingVertex == 0 and self.lineClosed:
                vertex = self.scene.addRect(vertexCoords.x(
                ) - 5, vertexCoords.y() - 5, 10, 10, QPen(QColor("green")), QBrush(QColor("green")))
                self.vertices.append(vertex)
            else:
                vertex = self.scene.addRect(vertexCoords.x(
                ) - 4, vertexCoords.y() - 4, 8, 8, QPen(QColor("red")), QBrush(QColor("red")))
                self.vertices.append(vertex)

    def deleteVertices(self):
        for i in range(len(self.vertices)):
            self.scene.removeItem(self.vertices[i])
        self.vertices = []

    def lineMagnitude(self, x1, y1, x2, y2):
        return sqrt(pow((x2 - x1), 2) + pow((y2 - y1), 2))

    def distancePointLine(self, px, py, x1, y1, x2, y2):
        magnitude = self.lineMagnitude(x1, y1, x2, y2)

        if magnitude < 0.00000001:
            distance = 9999
            return distance

        u1 = (((px - x1) * (x2 - x1)) + ((py - y1) * (y2 - y1)))
        u = u1 / (magnitude * magnitude)

        if (u < 0.00001) or (u > 1):
            ix = self.lineMagnitude(px, py, x1, y1)
            iy = self.lineMagnitude(px, py, x2, y2)
            if ix > iy:
                distance = iy
            else:
                distance = ix
        else:
            ix = x1 + u * (x2 - x1)
            iy = y1 + u * (y2 - y1)
            distance = self.lineMagnitude(px, py, ix, iy)

        return distance

    def redrawVertices(self):
        self.deleteVertices()
        self.showVertices()

    def redrawActions(self):
        self.redrawActionMoveVertices()
        self.redrawActionAddVertices()
        self.redrawActionRemoveVertices()
        self.redrawActionMoveSegment()
        self.redrawActionLineClose()
        self.redrawActionLineOpen()
        self.redrawActionMoveLine()
        self.redrawActionAreaAdjust()

    def redrawActionAreaAdjust(self):
        self.actionAreaAdjust.setEnabled(False)
        if len(self.capturedPoints) >= 2:
            self.actionAreaAdjust.setEnabled(True)

    def redrawActionMoveVertices(self):
        """Enable or disable the Move Vertices action based on captured points."""
        self.actionMoveVertices.setEnabled(False)
        if len(self.capturedPoints) > 0:
            self.actionMoveVertices.setEnabled(True)

    def redrawActionAddVertices(self):
        self.actionAddVertices.setEnabled(False)
        if len(self.capturedPoints) >= 2:
            self.actionAddVertices.setEnabled(True)

    def redrawActionRemoveVertices(self):
        self.actionRemoveVertices.setEnabled(False)
        if len(self.capturedPoints) > 2:
            self.actionRemoveVertices.setEnabled(True)

    def redrawActionMoveSegment(self):
        self.actionMoveSegment.setEnabled(False)
        if len(self.capturedPoints) > 2:
            self.actionMoveSegment.setEnabled(True)

    def redrawActionLineClose(self):
        self.actionLineClose.setEnabled(False)
        if not self.lineClosed and len(self.capturedPoints) >= 3:
            self.actionLineClose.setEnabled(True)

    def redrawActionLineOpen(self):
        self.actionLineOpen.setEnabled(False)
        if self.lineClosed:
            self.actionLineOpen.setEnabled(True)

    def redrawActionMoveLine(self):
        self.actionMoveLine.setEnabled(False)
        if len(self.capturedPoints) > 0:
            self.actionMoveLine.setEnabled(True)

    def keyPressEvent(self, event):
        # Detect key press events here
        if event.key() == QtCompat.Key_Z and event.modifiers() == QtCompat.ControlModifier:

            undo(self.layer)
        if event.key() == QtCompat.Key_Y and event.modifiers() == QtCompat.ControlModifier:

            redo(self.layer)

        else:
            super().keyPressEvent(event)

    def get_current_areas(self):
        """Calculates and returns the areas of the potential split parts."""
        if not self.capturing or len(self.capturedPoints) < 2:
            return []

        areas = []
        # Use the first selected feature for calculation (consistent with redrawAreas logic)
        if len(self.selectedFeatures) > 0:
            geometry = QgsGeometry(self.selectedFeatures[0].geometry())
            result, newGeometries, topoTestPoints = geometry.splitGeometry(
                self.capturedPoints, self.proj.topologicalEditing())

            # Add the original geometry (now modified to be one part)
            areas.append(self.calculator.measureArea(
                geometry) * self.unit_factor)

            # Add new geometries (other parts)
            if newGeometries:
                for geom in newGeometries:
                    areas.append(self.calculator.measureArea(
                        geom) * self.unit_factor)

        return areas

    def adjust_split_line(self, part_index, target_area):
        """Adjusts the split line to achieve the target area for the specified part."""
        if not self.capturing or len(self.capturedPoints) < 2 or len(self.selectedFeatures) == 0:
            return

        original_geometry = QgsGeometry(self.selectedFeatures[0].geometry())
        current_points = list(self.capturedPoints)

        # Iteration parameters
        max_iterations = 50
        tolerance = 0.001

        # Calculate initial shift direction (perpendicular to the line)
        p1 = current_points[0]
        p2 = current_points[-1]
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()

        # Normalize direction vector
        length = sqrt(dx*dx + dy*dy)
        if length == 0:
            return
        nx, ny = -dy/length, dx/length  # Perpendicular vector

        # 1. Measure current error
        current_area_val = self.measure_split_area(
            original_geometry, current_points, part_index)
        if current_area_val is None:
            QMessageBox.warning(self.canvas.window(
            ), "Error", "Could not calculate initial area. Ensure split line is valid.")
            return

        current_error = current_area_val - target_area

        if abs(current_error) < tolerance:
            return

        # 2. Measure error at a small offset to estimate gradient
        delta = 0.5  # map units
        offset_points = self.shift_points(
            current_points, nx * delta, ny * delta)
        offset_area_val = self.measure_split_area(
            original_geometry, offset_points, part_index)

        if offset_area_val is None:
            # Try opposite direction if first failed
            delta = -0.5
            offset_points = self.shift_points(
                current_points, nx * delta, ny * delta)
            offset_area_val = self.measure_split_area(
                original_geometry, offset_points, part_index)
            if offset_area_val is None:
                QMessageBox.warning(self.canvas.window(
                ), "Error", "Could not calculate gradient. Split configuration might be invalid.")
                return

        offset_error = offset_area_val - target_area

        if offset_error == current_error:
            return  # Gradient zero, cannot adjust

        gradient = (offset_error - current_error) / delta

        # 3. Newton-Raphson-ish steps
        current_shift = 0

        for k in range(max_iterations):
            area = self.measure_split_area(
                original_geometry, current_points, part_index)
            if area is None:
                break

            error = area - target_area
            if abs(error) < tolerance:
                break

            if gradient == 0:
                break

            step = - error / gradient

            # Dampen step to avoid overshooting wildy
            if abs(step) > 20:
                step = 20 * (step/abs(step))

            current_shift += step
            current_points = self.shift_points(
                list(self.capturedPoints), nx * current_shift, ny * current_shift)

        # Apply the final points
        self.capturedPoints = current_points
        self.redrawRubberBand()
        self.redrawVertices()
        self.redrawAreas()
        self.redrawTempRubberBand()

    def measure_split_area(self, original_geometry, points, part_index):
        geom = QgsGeometry(original_geometry)
        result, newGeometries, _ = geom.splitGeometry(
            points, self.proj.topologicalEditing())
        if result != 0:
            return None  # Split failed

        parts = [geom] + (newGeometries if newGeometries else [])
        if part_index < len(parts):
            return self.calculator.measureArea(parts[part_index]) * self.unit_factor
        return None

    def shift_points(self, points, dx, dy):
        new_points = []
        for p in points:
            new_points.append(QgsPointXY(p.x() + dx, p.y() + dy))
        return new_points


split_window = MyWnd(iface)
qgis_main_window = iface.mainWindow()
split_window.setParent(qgis_main_window, QtCompat.Window)


def show_polygon_splitter():
    split_window.show()

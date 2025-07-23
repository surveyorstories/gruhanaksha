# -*- coding: utf-8 -*-
"""
Unified QGIS Polygon Editor with Deferred Panel:
1. User clicks polygon
2. User clicks any vertex of that polygon
3. Mode/length dialog appears (choose operation & enter value)
4. Click direction; confirm & apply
Right-click resets. Layer must be in edit mode.
"""

from qgis.PyQt.QtCore import Qt
from qgis.utils import iface
from qgis.PyQt.QtGui import QColor, QCursor
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QRadioButton, QPushButton,
    QDoubleSpinBox, QLabel, QMessageBox
)
from qgis.core import (
    QgsProject, QgsGeometry, QgsPointXY, QgsWkbTypes, QgsVectorLayer
)
from qgis.gui import QgsMapTool, QgsRubberBand, QgsVertexMarker
import math

# ---- Custom Dialog ----


class LengthInputDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Operation & Length")
        layout = QVBoxLayout(self)
        self.mode_move = QRadioButton("Move Vertex by Distance (±length)")
        self.mode_side = QRadioButton("Set Polygon Side Length")
        self.mode_move.setChecked(True)
        layout.addWidget(self.mode_move)
        layout.addWidget(self.mode_side)
        layout.addWidget(QLabel("Enter length (map units):"))
        self.length_input = QDoubleSpinBox()
        self.length_input.setDecimals(6)
        self.length_input.setRange(-999999.0, 999999.0)
        self.length_input.setValue(1.0)
        layout.addWidget(self.length_input)
        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("OK")
        self.cancel_btn = QPushButton("Cancel")
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

    def get_values(self):
        mode = 'move' if self.mode_move.isChecked() else 'side'
        length = self.length_input.value()
        return mode, length


class UnifiedPolygonEditTool(QgsMapTool):
    def __init__(self, canvas):
        QgsMapTool.__init__(self, canvas)
        self.canvas = canvas
        self.setCursor(QCursor(Qt.CrossCursor))
        self.snappingUtils = self.canvas.snappingUtils()
        self.setupVisuals()
        self.resetTool(first=True)

    def setupVisuals(self):
        self.rubberBand = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.rubberBand.setColor(QColor(255, 0, 0, 180))
        self.rubberBand.setWidth(3)
        self.rubberBand.setLineStyle(Qt.DashLine)
        self.previewBand = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.previewBand.setColor(QColor(0, 150, 255, 120))
        self.previewBand.setWidth(2)
        self.previewBand.setLineStyle(Qt.DotLine)
        self.featureBand = QgsRubberBand(
            self.canvas, QgsWkbTypes.PolygonGeometry)
        self.featureBand.setColor(QColor(0, 0, 255, 40))
        self.featureBand.setWidth(2)
        self.vertexMarker = QgsVertexMarker(self.canvas)
        self.vertexMarker.setColor(QColor(0, 255, 0))
        self.vertexMarker.setIconSize(12)
        self.vertexMarker.setIconType(QgsVertexMarker.ICON_CIRCLE)
        self.vertexMarker.setPenWidth(3)
        self.hoverMarker = QgsVertexMarker(self.canvas)
        self.hoverMarker.setColor(QColor(255, 0, 0))
        self.hoverMarker.setIconSize(10)
        self.hoverMarker.setIconType(QgsVertexMarker.ICON_CROSS)
        self.hoverMarker.setPenWidth(2)
        self.hoverMarker.hide()
        self.directionMarker = QgsVertexMarker(self.canvas)
        self.directionMarker.setColor(QColor(255, 100, 0))
        self.directionMarker.setIconSize(10)
        self.directionMarker.setIconType(QgsVertexMarker.ICON_X)
        self.directionMarker.setPenWidth(3)
        self.directionMarker.hide()

    def canvasPressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.state == "SELECT_POLYGON":
                self.handlePolygonSelection(event)
            elif self.state == "SELECT_VERTEX":
                self.handleVertexSelection(event)
            elif self.state == "SHOW_PANEL":
                self.showLengthPanel()
            elif self.state == "SELECT_DIRECTION":
                self.handleDirectionSelection(event)
        elif event.button() == Qt.RightButton:
            self.resetTool()

    def handlePolygonSelection(self, event):
        point = self.toMapCoordinates(event.pos())
        layers = [
            lyr for lyr in QgsProject.instance().mapLayers().values()
            if isinstance(lyr, QgsVectorLayer)
            and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.PolygonGeometry
        ]
        active = iface.activeLayer()
        if active and active in layers:
            layers.remove(active)
            layers.insert(0, active)
        found = False
        for layer in layers:
            for f in layer.getFeatures():
                if f.geometry() and f.geometry().contains(point):
                    if not layer.isEditable():
                        iface.messageBar().pushMessage(
                            "Layer Not Editable",
                            "Selected layer is not in editing mode. Please toggle editing first.",
                            duration=2
                        )
                        return
                    self.selectedFeature, self.selectedLayer = f, layer
                    found = True
                    break
            if found:
                break
        if found:
            self.featureBand.reset(QgsWkbTypes.PolygonGeometry)
            self.featureBand.setToGeometry(
                self.selectedFeature.geometry(), self.selectedLayer)
            self.state = "SELECT_VERTEX"
            iface.messageBar().pushMessage(
                "Select Vertex",
                "Polygon selected. Now click a vertex of this polygon.",
                duration=2
            )
        else:
            iface.messageBar().pushMessage(
                "Info", "No polygon found. Make sure you are editing a polygon layer.", duration=2
            )

    def handleVertexSelection(self, event):
        point = self.toMapCoordinates(event.pos())
        geom = self.selectedFeature.geometry()
        min_dist, closest_vertex, closest_index = None, None, None
        vertices = [QgsPointXY(pt) for pt in geom.vertices()]
        for i, v in enumerate(vertices):
            d = math.hypot(point.x() - v.x(), point.y() - v.y())
            if (min_dist is None) or (d < min_dist):
                min_dist = d
                closest_vertex = v
                closest_index = i
        threshold = self.canvas.mapUnitsPerPixel() * 8
        if min_dist is not None and min_dist <= threshold:
            self.selectedVertex = closest_vertex
            self.vertexIndex = closest_index
            self.vertexMarker.setCenter(closest_vertex)
            self.vertexMarker.show()
            self.state = "SHOW_PANEL"
            self.showLengthPanel()
        else:
            iface.messageBar().pushMessage(
                "Info", "No vertex found at clicked location.", duration=2)

    def showLengthPanel(self):
        dlg = LengthInputDialog()
        if dlg.exec_():
            self.mode, length = dlg.get_values()
            if self.mode == 'move' and abs(length) < 1e-10:
                iface.messageBar().pushMessage("Error", "Distance must be nonzero.", duration=3)
                self.resetTool()
                return
            if self.mode == 'side' and length <= 0:
                iface.messageBar().pushMessage("Error", "Side length must be positive.", duration=3)
                self.resetTool()
                return
            self.moveDistance = length if self.mode == 'move' else None
            self.targetLength = abs(length) if self.mode == 'side' else None
            self.state = "SELECT_DIRECTION"
            iface.messageBar().pushMessage(
                "Select Direction",
                (
                    "Click to set move direction (move mode)" if self.mode == "move"
                    else "Click to select side direction (side length mode)"
                ),
                duration=2
            )
        else:
            self.resetTool()

    def handleDirectionSelection(self, event):
        point = self.toMapCoordinates(event.pos())
        snap = self.getSnapResult(point)
        direction_point = snap['point'] if snap else point
        if self.mode == "move":
            self.handleDirectionSelection_move(direction_point)
        elif self.mode == "side":
            self.handleDirectionSelection_side(direction_point)
        else:
            self.resetTool()

    def handleDirectionSelection_move(self, direction_point):
        dx = self.selectedVertex.x() - direction_point.x()
        dy = self.selectedVertex.y() - direction_point.y()
        norm = math.hypot(dx, dy)
        if norm < 1e-10:
            iface.messageBar().pushMessage("Info", "Direction not defined.", duration=2)
            return
        unit_x, unit_y = dx / norm, dy / norm
        new_point = QgsPointXY(
            self.selectedVertex.x() + self.moveDistance * unit_x,
            self.selectedVertex.y() + self.moveDistance * unit_y
        )
        angle_degrees = math.degrees(math.atan2(unit_y, unit_x))
        if angle_degrees < 0:
            angle_degrees += 360
        self.showMovementPreview(new_point)
        self.confirmVertexMove(new_point, self.moveDistance, angle_degrees)

    def showMovementPreview(self, new_point):
        self.rubberBand.reset(QgsWkbTypes.LineGeometry)
        self.rubberBand.addPoint(self.selectedVertex, False)
        self.rubberBand.addPoint(new_point, True)
        self.rubberBand.show()
        self.previewBand.hide()

    def confirmVertexMove(self, new_point, distance, angle):
        reply = QMessageBox.question(
            None, "Confirm Vertex Move",
            f"Move vertex {distance:+.3f} units at {angle:.2f}° from original?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            self.moveVertex(new_point)
        else:
            self.resetTool()

    def moveVertex(self, new_point):
        try:
            geom = self.selectedFeature.geometry()
            geom.moveVertex(new_point.x(), new_point.y(), self.vertexIndex)
            self.selectedLayer.changeGeometry(self.selectedFeature.id(), geom)
            self.canvas.refresh()
            iface.messageBar().pushMessage("Success", "Vertex moved!", duration=1)
        except Exception as e:
            iface.messageBar().pushMessage(
                "Error", f"Move failed: {str(e)}", duration=2)
        finally:
            self.resetTool()

    def handleDirectionSelection_side(self, direction_point):
        geom = self.selectedFeature.geometry()
        vertices = [QgsPointXY(pt) for pt in geom.vertices()]
        prev_index = (self.vertexIndex - 1) % len(vertices)
        next_index = (self.vertexIndex + 1) % len(vertices)
        prev_vertex, next_vertex = vertices[prev_index], vertices[next_index]
        dx_click = direction_point.x() - self.selectedVertex.x()
        dy_click = direction_point.y() - self.selectedVertex.y()
        dx_prev = prev_vertex.x() - self.selectedVertex.x()
        dy_prev = prev_vertex.y() - self.selectedVertex.y()
        dx_next = next_vertex.x() - self.selectedVertex.x()
        dy_next = next_vertex.y() - self.selectedVertex.y()
        dot_prev = dx_click * dx_prev + dy_click * dy_prev
        dot_next = dx_click * dx_next + dy_click * dy_next
        if dot_prev > dot_next:
            fixed_index, moving_index = prev_index, self.vertexIndex
        else:
            fixed_index, moving_index = next_index, self.vertexIndex
        self.adjustSideLength(fixed_index, moving_index, self.targetLength)

    def adjustSideLength(self, fixed_vertex_index, moving_vertex_index, target_length):
        geom = self.selectedFeature.geometry()
        vertices = [QgsPointXY(pt) for pt in geom.vertices()]
        fixed_pt = vertices[fixed_vertex_index]
        moving_pt = vertices[moving_vertex_index]
        dx = moving_pt.x() - fixed_pt.x()
        dy = moving_pt.y() - fixed_pt.y()
        current_length = math.hypot(dx, dy)
        if current_length < 1e-10:
            iface.messageBar().pushMessage("Error", "Invalid side length.", duration=3)
            self.resetTool()
            return
        unit_x, unit_y = dx / current_length, dy / current_length
        new_moving_x = fixed_pt.x() + unit_x * target_length
        new_moving_y = fixed_pt.y() + unit_y * target_length
        new_moving_point = QgsPointXY(new_moving_x, new_moving_y)
        self.showSideLengthPreview(
            fixed_pt, new_moving_point, current_length, target_length, moving_pt)
        self.confirmSideLengthChange(
            moving_vertex_index, new_moving_point, current_length, target_length)

    def showSideLengthPreview(self, start_pt, new_end_pt, current_length, target_length, current_end_pt):
        self.rubberBand.reset(QgsWkbTypes.LineGeometry)
        self.rubberBand.addPoint(start_pt, False)
        self.rubberBand.addPoint(new_end_pt, True)
        self.rubberBand.show()
        self.previewBand.reset(QgsWkbTypes.LineGeometry)
        self.previewBand.addPoint(start_pt, False)
        self.previewBand.addPoint(current_end_pt, True)
        self.previewBand.show()

    def confirmSideLengthChange(self, vertex_index, new_point, current_length, target_length):
        reply = QMessageBox.question(
            None, "Confirm Side Length Change",
            f"Change side length from {current_length:.3f} to {target_length:.3f} units?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            self.moveSideVertex(vertex_index, new_point)
        else:
            self.resetTool()

    def moveSideVertex(self, vertex_index, new_point):
        try:
            geometry = self.selectedFeature.geometry()
            geometry.moveVertex(new_point.x(), new_point.y(), vertex_index)
            self.selectedLayer.changeGeometry(
                self.selectedFeature.id(), geometry)
            self.canvas.refresh()
            iface.messageBar().pushMessage(
                "Success", f"Side length set to {self.targetLength:.3f} units!", duration=3)
        except Exception as e:
            iface.messageBar().pushMessage(
                "Error", f"Failed to move vertex: {str(e)}", duration=3)
        finally:
            self.resetTool()

    def getSnapResult(self, point):
        if not QgsProject.instance().snappingConfig().enabled():
            return None
        match = self.snappingUtils.snapToMap(point)
        if match.isValid():
            layer = match.layer()
            if isinstance(layer, QgsVectorLayer) and layer.isEditable():
                feature = layer.getFeature(match.featureId())
                if feature:
                    return {
                        'point': match.point(),
                        'feature': feature,
                        'layer': layer,
                        'vertex_index': match.vertexIndex(),
                        'type': match.type()
                    }
        return None

    def canvasMoveEvent(self, event):
        point = self.toMapCoordinates(event.pos())
        if self.state == "SELECT_VERTEX":
            geom = self.selectedFeature.geometry()
            vertices = [QgsPointXY(pt) for pt in geom.vertices()]
            min_dist, closest_vertex = None, None
            for v in vertices:
                d = math.hypot(point.x() - v.x(), point.y() - v.y())
                if (min_dist is None) or (d < min_dist):
                    min_dist = d
                    closest_vertex = v
            threshold = self.canvas.mapUnitsPerPixel() * 8
            if min_dist is not None and min_dist <= threshold:
                self.hoverMarker.setCenter(closest_vertex)
                self.hoverMarker.show()
            else:
                self.hoverMarker.hide()
        elif self.state == "SELECT_DIRECTION" and self.selectedVertex:
            snap = self.getSnapResult(point)
            if snap:
                direction_point = snap['point']
                self.directionMarker.setCenter(direction_point)
                self.directionMarker.show()
            else:
                direction_point = point
                self.directionMarker.hide()
            self.previewBand.reset(QgsWkbTypes.LineGeometry)
            self.previewBand.addPoint(self.selectedVertex, False)
            self.previewBand.addPoint(direction_point, True)
            self.previewBand.show()
        elif self.state == "SELECT_POLYGON":
            pass

    def resetTool(self, first=False):
        if self.rubberBand:
            self.rubberBand.hide()
        if self.previewBand:
            self.previewBand.hide()
        if self.featureBand:
            self.featureBand.hide()
        if self.vertexMarker:
            self.vertexMarker.hide()
        if self.hoverMarker:
            self.hoverMarker.hide()
        if self.directionMarker:
            self.directionMarker.hide()
        self.selectedVertex = None
        self.selectedFeature = None
        self.selectedLayer = None
        self.vertexIndex = None
        self.moveDistance = None
        self.targetLength = None
        self.mode = None
        self.state = "SELECT_POLYGON"
        self.setCursor(QCursor(Qt.CrossCursor))
        if not first:
            iface.messageBar().pushMessage(
                "Adjuster Tool",
                "Ready. Right-click to reset, or left-click to start new operation.",
                duration=2
            )

    def deactivate(self):
        self.resetTool()
        QgsMapTool.deactivate(self)
        print("Unified Polygon Editing Tool deactivated")


def activate_unified_tool():
    global unified_edit_tool
    canvas = iface.mapCanvas()
    unified_edit_tool = UnifiedPolygonEditTool(canvas)
    canvas.setMapTool(unified_edit_tool)
    iface.messageBar().pushMessage(
        "Unified Polygon Edit Tool Activated",
        "Click polygon, then click a vertex, then follow prompts.",
        duration=3
    )


def deactivate_unified_tool():
    canvas = iface.mapCanvas()
    canvas.unsetMapTool(canvas.mapTool())

# activate_unified_tool()

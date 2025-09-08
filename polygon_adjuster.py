from PyQt5.QtGui import QColor, QPen
from PyQt5.QtWidgets import QGraphicsTextItem
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QRadioButton,
    QLabel, QDoubleSpinBox, QMessageBox, QGraphicsTextItem, QComboBox
)

from qgis.utils import iface
from PyQt5.QtGui import QColor, QCursor
from PyQt5.QtCore import Qt
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsWkbTypes, QgsPointXY, QgsUnitTypes
)
from qgis.gui import (
    QgsMapTool, QgsRubberBand, QgsVertexMarker
)
import math


class UnitConverter:
    """Handles unit conversions for the geometry editing tool"""

    # Conversion factors to meters
    UNIT_TO_METERS = {
        'meters': 1.0,
        'feet': 0.3048,
        'yards': 0.9144,
        'metric_links': 0.2,  # 20 cm
        'gunter_links': 0.66 * 0.3048,  # 0.66 feet = 20.1168 cm
        'inches': 0.0254,

    }

    UNIT_NAMES = {
        'meters': 'm',
        'feet': 'ft',
        'yards': 'yd',
        'metric_links': 'lnk (M)',
        'gunter_links': 'lnk (G)',
        'inches': 'in',

    }

    @classmethod
    def convert_to_map_units(cls, value, from_unit, map_crs):
        """Convert value from specified unit to map units"""
        # First convert to meters
        value_in_meters = value * cls.UNIT_TO_METERS.get(from_unit, 1.0)

        # Get map units
        map_units = map_crs.mapUnits()

        # Convert from meters to map units
        if map_units == QgsUnitTypes.DistanceMeters:
            return value_in_meters
        elif map_units == QgsUnitTypes.DistanceFeet:
            return value_in_meters / 0.3048
        elif map_units == QgsUnitTypes.DistanceYards:
            return value_in_meters / 0.9144

        elif map_units == QgsUnitTypes.DistanceInches:
            return value_in_meters / 0.0254
        else:
            # For degrees or unknown units, assume meters
            return value_in_meters

    @classmethod
    def convert_from_map_units(cls, value, to_unit, map_crs):
        """Convert value from map units to specified unit"""
        # Get map units
        map_units = map_crs.mapUnits()

        # Convert from map units to meters first
        if map_units == QgsUnitTypes.DistanceMeters:
            value_in_meters = value
        elif map_units == QgsUnitTypes.DistanceFeet:
            value_in_meters = value * 0.3048
        elif map_units == QgsUnitTypes.DistanceYards:
            value_in_meters = value * 0.9144
        elif map_units == QgsUnitTypes.DistanceInches:
            value_in_meters = value * 0.0254
        else:
            # For degrees or unknown units, assume meters
            value_in_meters = value

        # Convert from meters to target unit
        return value_in_meters / cls.UNIT_TO_METERS.get(to_unit, 1.0)

    @classmethod
    def get_map_units_name(cls, map_crs):
        """Get the name of map units"""
        map_units = map_crs.mapUnits()

        unit_names = {
            QgsUnitTypes.DistanceMeters: 'm',
            QgsUnitTypes.DistanceFeet: 'ft',
            QgsUnitTypes.DistanceYards: 'yd',
            QgsUnitTypes.DistanceKilometers: 'km',
            QgsUnitTypes.DistanceMiles: 'mi',
            QgsUnitTypes.DistanceMillimeters: 'mm',
            QgsUnitTypes.DistanceCentimeters: 'cm',
            QgsUnitTypes.DistanceInches: 'in',
            QgsUnitTypes.DistanceDegrees: '°',
            QgsUnitTypes.DistanceUnknownUnit: 'units'
        }

        return unit_names.get(map_units, 'units')


class LengthInputDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Operation, Length & Units")
        self.setMinimumWidth(350)
        layout = QVBoxLayout(self)

        # Operation mode selection
        mode_group = QVBoxLayout()
        mode_label = QLabel("<b>Operation Mode:</b>")
        mode_group.addWidget(mode_label)

        self.mode_move = QRadioButton("Move Vertex by Distance (±length)")
        self.mode_side = QRadioButton("Set Segment Length")
        self.mode_move.setChecked(True)
        mode_group.addWidget(self.mode_move)
        mode_group.addWidget(self.mode_side)
        layout.addLayout(mode_group)

        # Length input
        length_layout = QVBoxLayout()
        length_label = QLabel("<b>Length Input:</b>")
        length_layout.addWidget(length_label)

        input_layout = QHBoxLayout()
        self.length_input = QDoubleSpinBox()
        self.length_input.setDecimals(6)
        self.length_input.setRange(-999999.0, 999999.0)
        self.length_input.setValue(1.0)
        self.length_input.setMinimumWidth(150)
        input_layout.addWidget(self.length_input)

        # Units combo box
        self.units_combo = QComboBox()
        self.units_combo.setMinimumWidth(120)

        # Populate units
        units = [
            ('meters', 'Meters (m)'),
            ('feet', 'Feet (ft)'),
            ('yards', 'Yards (yd)'),
            
            ('metric_links', 'Metric Links (lnk M)'),
            ('gunter_links', 'Gunter Links (lnk G)'),
          
            ('inches', 'Inches (in)'),
       
        ]

        for unit_key, unit_display in units:
            self.units_combo.addItem(unit_display, unit_key)

        # Set default to meters
        self.units_combo.setCurrentIndex(0)

        input_layout.addWidget(self.units_combo)
        length_layout.addLayout(input_layout)
        layout.addLayout(length_layout)

        # Map units info
        try:
            map_crs = QgsProject.instance().crs()
            map_units_name = UnitConverter.get_map_units_name(map_crs)
            info_label = QLabel(f"<i>Map units: {map_units_name}</i>")
            info_label.setStyleSheet("color: #666666;")
            layout.addWidget(info_label)
        except Exception:
            pass  # Skip if unable to get map units

        # Conversion preview
        self.conversion_label = QLabel("")
        self.conversion_label.setStyleSheet(
            "color: #0066cc; font-style: italic;")
        layout.addWidget(self.conversion_label)

        # Connect signals for real-time conversion display
        self.length_input.valueChanged.connect(self.update_conversion_preview)
        self.units_combo.currentTextChanged.connect(
            self.update_conversion_preview)

        # Update initial preview
        self.update_conversion_preview()

        # Buttons
        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("OK")
        self.cancel_btn = QPushButton("Cancel")
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

    def update_conversion_preview(self):
        """Update the conversion preview label"""
        try:
            value = self.length_input.value()
            selected_unit = self.units_combo.currentData()

            if value != 0 and selected_unit:
                map_crs = QgsProject.instance().crs()
                map_value = UnitConverter.convert_to_map_units(
                    value, selected_unit, map_crs)
                map_units_name = UnitConverter.get_map_units_name(map_crs)

                # Format the conversion text
                unit_name = UnitConverter.UNIT_NAMES.get(
                    selected_unit, selected_unit)
                self.conversion_label.setText(
                    f"≈ {map_value:.4f} {map_units_name} (map units)"
                )
            else:
                self.conversion_label.setText("")
        except Exception:
            self.conversion_label.setText("")

    def get_values(self):
        mode = 'move' if self.mode_move.isChecked() else 'side'
        length = self.length_input.value()
        unit = self.units_combo.currentData()

        # Convert to map units
        try:
            map_crs = QgsProject.instance().crs()
            length_in_map_units = UnitConverter.convert_to_map_units(
                length, unit, map_crs)
        except Exception:
            length_in_map_units = length  # Fallback to original value

        return mode, length_in_map_units, length, unit


class BufferedTextItem(QGraphicsTextItem):
    def __init__(self, text, main_color=QColor(255, 0, 150), buffer_color=QColor('white'), buffer_width=3):
        super().__init__(text)
        self.main_color = main_color
        self.buffer_color = buffer_color
        self.buffer_width = buffer_width

    def paint(self, painter, option, widget=None):
        painter.save()
        # Draw buffer by offsetting in a circle
        for dx in range(-self.buffer_width, self.buffer_width+1):
            for dy in range(-self.buffer_width, self.buffer_width+1):
                if dx*dx + dy*dy <= self.buffer_width*self.buffer_width and (dx != 0 or dy != 0):
                    painter.setPen(QPen(self.buffer_color))
                    painter.drawText(self.boundingRect().translated(
                        dx, dy), self.toPlainText())
        # Draw main text
        painter.setPen(QPen(self.main_color))
        painter.drawText(self.boundingRect(), self.toPlainText())
        painter.restore()


class UnifiedGeometryEditTool(QgsMapTool):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.setCursor(QCursor(Qt.CrossCursor))
        self.snappingUtils = self.canvas.snappingUtils()
        self.setupVisuals()

        self.dimension_labels = []
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

        # For line features
        self.lineBand = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.lineBand.setColor(QColor(0, 255, 0, 120))
        self.lineBand.setWidth(3)

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
            if self.state == "SELECT_FEATURE":
                self.handleFeatureSelection(event)
            elif self.state == "SELECT_VERTEX":
                self.handleVertexSelection(event)
            elif self.state == "SHOW_PANEL":
                self.showLengthPanel()
            elif self.state == "SELECT_DIRECTION":
                self.handleDirectionSelection(event)
        elif event.button() == Qt.RightButton:
            self.resetTool()

    def handleFeatureSelection(self, event):
        point = self.toMapCoordinates(event.pos())

        # Get both polygon and line layers
        layers = [
            lyr for lyr in QgsProject.instance().mapLayers().values()
            if isinstance(lyr, QgsVectorLayer)
            and QgsWkbTypes.geometryType(lyr.wkbType()) in [QgsWkbTypes.PolygonGeometry, QgsWkbTypes.LineGeometry]
        ]

        # Prioritize active layer
        active = iface.activeLayer()
        if active and active in layers:
            layers.remove(active)
            layers.insert(0, active)

        found = False
        tolerance = self.canvas.mapUnitsPerPixel() * 5  # Tolerance for line selection

        for layer in layers:
            for f in layer.getFeatures():
                if not f.geometry():
                    continue

                # For polygons, check contains
                if QgsWkbTypes.geometryType(layer.wkbType()) == QgsWkbTypes.PolygonGeometry:
                    if f.geometry().contains(point):
                        if not layer.isEditable():
                            iface.messageBar().pushMessage(
                                "Layer Not Editable",
                                "Selected layer is not in editing mode. Please toggle editing first.",
                                duration=2
                            )
                            return
                        self.selectedFeature, self.selectedLayer = f, layer
                        self.geometryType = "polygon"
                        found = True
                        break

                # For lines, check distance
                elif QgsWkbTypes.geometryType(layer.wkbType()) == QgsWkbTypes.LineGeometry:
                    from qgis.core import QgsGeometry
                    point_geom = QgsGeometry.fromPointXY(point)
                    distance = f.geometry().distance(point_geom)
                    if distance <= tolerance:
                        if not layer.isEditable():
                            iface.messageBar().pushMessage(
                                "Layer Not Editable",
                                "Selected layer is not in editing mode. Please toggle editing first.",
                                duration=2
                            )
                            return
                        self.selectedFeature, self.selectedLayer = f, layer
                        self.geometryType = "line"
                        found = True
                        break
            if found:
                break

        if found:
            # Display the selected feature
            if self.geometryType == "polygon":
                self.featureBand.reset(QgsWkbTypes.PolygonGeometry)
                self.featureBand.setToGeometry(
                    self.selectedFeature.geometry(), self.selectedLayer)
                self.featureBand.show()
                self.lineBand.hide()
            else:  # line
                self.lineBand.reset(QgsWkbTypes.LineGeometry)
                self.lineBand.setToGeometry(
                    self.selectedFeature.geometry(), self.selectedLayer)
                self.lineBand.show()
                self.featureBand.hide()

            self.state = "SELECT_VERTEX"
            self.update_dimension_labels()

            feature_type = "polygon" if self.geometryType == "polygon" else "line"
            iface.messageBar().pushMessage(
                "Select Vertex",
                f"{feature_type.title()} selected. Now click a vertex of this {feature_type}.",
                duration=2
            )
        else:
            iface.messageBar().pushMessage(
                "Info", "No polygon or line found. Make sure you are editing a polygon or line layer.", duration=2
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
            self.mode, length_map_units, original_length, selected_unit = dlg.get_values()

            # Store both original and converted values for user feedback
            self.originalLength = original_length
            self.selectedUnit = selected_unit

            if self.mode == 'move' and abs(length_map_units) < 1e-10:
                iface.messageBar().pushMessage("Error", "Distance must be nonzero.", duration=2)
                self.resetTool()
                return
            if self.mode == 'side' and length_map_units <= 0:
                iface.messageBar().pushMessage(
                    "Error", "Segment length must be positive.", duration=2)
                self.resetTool()
                return

            self.moveDistance = length_map_units if self.mode == 'move' else None
            self.targetLength = abs(
                length_map_units) if self.mode == 'side' else None
            self.state = "SELECT_DIRECTION"

            segment_text = "side" if self.geometryType == "polygon" else "segment"
            unit_display = UnitConverter.UNIT_NAMES.get(
                selected_unit, selected_unit)

            iface.messageBar().pushMessage(
                "Select Direction",
                (
                    f"Click to set move direction ({original_length:.3f} {unit_display} = {length_map_units:.3f} map units)"
                    if self.mode == "move"
                    else f"Click to select {segment_text} direction (target: {original_length:.3f} {unit_display})"
                ),
                duration=3
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
            self.handleDirectionSelection_segment(direction_point)
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
        unit_display = UnitConverter.UNIT_NAMES.get(
            self.selectedUnit, self.selectedUnit)
        reply = QMessageBox.question(
            None, "Confirm Vertex Move",
            f"Move vertex {self.originalLength:+.3f} {unit_display} ({distance:+.3f} map units) at {angle:.2f}° from original?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            self.moveVertexTopologically(new_point)
        else:
            self.resetTool()

    def findCoincidentVertices(self, point, tolerance=None):
        """Find all vertices that coincide with the given point across all editable layers"""
        if tolerance is None:
            # Small tolerance for coincident vertices
            tolerance = self.canvas.mapUnitsPerPixel() * 2

        coincident_vertices = []

        # Get all polygon and line layers that are editable
        layers = [
            lyr for lyr in QgsProject.instance().mapLayers().values()
            if isinstance(lyr, QgsVectorLayer)
            and QgsWkbTypes.geometryType(lyr.wkbType()) in [QgsWkbTypes.PolygonGeometry, QgsWkbTypes.LineGeometry]
            and lyr.isEditable()
        ]

        for layer in layers:
            for feature in layer.getFeatures():
                if not feature.geometry():
                    continue

                vertices = [QgsPointXY(pt)
                            for pt in feature.geometry().vertices()]

                for vertex_index, vertex in enumerate(vertices):
                    distance = math.hypot(
                        vertex.x() - point.x(), vertex.y() - point.y())
                    if distance <= tolerance:
                        coincident_vertices.append({
                            'layer': layer,
                            'feature': feature,
                            'vertex_index': vertex_index,
                            'vertex': vertex
                        })

        return coincident_vertices

    def moveVertexTopologically(self, new_point):
        """Move vertex considering topological editing"""
        try:
            # Check if topological editing is enabled
            project = QgsProject.instance()
            topo_editing = project.topologicalEditing()

            if topo_editing:
                # Find all coincident vertices
                coincident_vertices = self.findCoincidentVertices(
                    self.selectedVertex)

                if len(coincident_vertices) > 1:
                    iface.messageBar().pushMessage(
                        "Topological Edit",
                        f"Moving {len(coincident_vertices)} coincident vertices together.",
                        duration=2
                    )

                # Move all coincident vertices
                for vertex_info in coincident_vertices:
                    layer = vertex_info['layer']
                    feature = vertex_info['feature']
                    vertex_index = vertex_info['vertex_index']

                    geom = feature.geometry()
                    geom.moveVertex(new_point.x(), new_point.y(), vertex_index)
                    layer.changeGeometry(feature.id(), geom)
            else:
                # Just move the selected vertex
                geom = self.selectedFeature.geometry()
                geom.moveVertex(new_point.x(), new_point.y(), self.vertexIndex)
                self.selectedLayer.changeGeometry(
                    self.selectedFeature.id(), geom)

            self.canvas.refresh()
            self.update_dimension_labels()
            unit_display = UnitConverter.UNIT_NAMES.get(
                self.selectedUnit, self.selectedUnit)
            iface.messageBar().pushMessage(
                "Success",
                f"Vertex moved {self.originalLength:+.3f} {unit_display}!",
                duration=2
            )

        except Exception as e:
            iface.messageBar().pushMessage(
                "Error", f"Move failed: {str(e)}", duration=2)
        finally:
            self.resetTool()

    def handleDirectionSelection_segment(self, direction_point):
        geom = self.selectedFeature.geometry()
        vertices = [QgsPointXY(pt) for pt in geom.vertices()]

        # For polygons, remove closing duplicate if polygon is closed
        if self.geometryType == "polygon" and vertices[0] == vertices[-1]:
            vertices = vertices[:-1]

        n = len(vertices)

        # Find adjacent vertices
        if self.geometryType == "polygon":
            # For polygons, both previous and next vertices exist (circular)
            prev_index = (self.vertexIndex - 1) % n
            next_index = (self.vertexIndex + 1) % n
            prev_vertex, next_vertex = vertices[prev_index], vertices[next_index]
        else:
            # For lines, check if vertex is at start, middle, or end
            if self.vertexIndex == 0:
                # Start vertex - only next vertex available
                if n < 2:
                    iface.messageBar().pushMessage(
                        "Error", "Line must have at least 2 vertices.", duration=2)
                    self.resetTool()
                    return
                next_index = 1
                next_vertex = vertices[next_index]
                self.adjustSegmentLength(
                    self.vertexIndex, next_index, self.targetLength)
                return
            elif self.vertexIndex == n - 1:
                # End vertex - only previous vertex available
                prev_index = n - 2
                prev_vertex = vertices[prev_index]
                self.adjustSegmentLength(
                    prev_index, self.vertexIndex, self.targetLength)
                return
            else:
                # Middle vertex - both previous and next available
                prev_index = self.vertexIndex - 1
                next_index = self.vertexIndex + 1
                prev_vertex, next_vertex = vertices[prev_index], vertices[next_index]

        # Determine which segment to adjust based on click direction
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

        self.adjustSegmentLength(fixed_index, moving_index, self.targetLength)

    def adjustSegmentLength(self, fixed_vertex_index, moving_vertex_index, target_length):
        geom = self.selectedFeature.geometry()
        vertices = [QgsPointXY(pt) for pt in geom.vertices()]

        # For polygons, remove closing duplicate if polygon closed
        if self.geometryType == "polygon" and vertices[0] == vertices[-1]:
            vertices = vertices[:-1]

        fixed_pt = vertices[fixed_vertex_index]
        moving_pt = vertices[moving_vertex_index]

        dx = moving_pt.x() - fixed_pt.x()
        dy = moving_pt.y() - fixed_pt.y()
        current_length = math.hypot(dx, dy)

        if current_length < 1e-10:
            segment_text = "side" if self.geometryType == "polygon" else "segment"
            iface.messageBar().pushMessage(
                "Error", f"Invalid {segment_text} length ({segment_text} too short).", duration=2)
            self.resetTool()
            return

        unit_x, unit_y = dx / current_length, dy / current_length
        new_moving_x = fixed_pt.x() + unit_x * target_length
        new_moving_y = fixed_pt.y() + unit_y * target_length
        new_moving_point = QgsPointXY(new_moving_x, new_moving_y)

        self.showSegmentLengthPreview(
            fixed_pt, new_moving_point, current_length, target_length, moving_pt)
        self.confirmSegmentLengthChange(
            moving_vertex_index, new_moving_point, current_length, target_length)

    def showSegmentLengthPreview(self, start_pt, new_end_pt, current_length, target_length, current_end_pt):
        self.rubberBand.reset(QgsWkbTypes.LineGeometry)
        self.rubberBand.addPoint(start_pt, False)
        self.rubberBand.addPoint(new_end_pt, True)
        self.rubberBand.show()

        self.previewBand.reset(QgsWkbTypes.LineGeometry)
        self.previewBand.addPoint(start_pt, False)
        self.previewBand.addPoint(current_end_pt, True)
        self.previewBand.show()

    def confirmSegmentLengthChange(self, vertex_index, new_point, current_length, target_length):
        segment_text = "side" if self.geometryType == "polygon" else "segment"
        unit_display = UnitConverter.UNIT_NAMES.get(
            self.selectedUnit, self.selectedUnit)

        # Convert current length to display units for user feedback
        try:
            map_crs = QgsProject.instance().crs()
            current_length_display = UnitConverter.convert_from_map_units(
                current_length, self.selectedUnit, map_crs)
        except Exception:
            current_length_display = current_length

        reply = QMessageBox.question(
            None, f"Confirm {segment_text.title()} Length Change",
            f"Change {segment_text} length from {current_length_display:.3f} to {self.originalLength:.3f} {unit_display}?\n"
            f"(Map units: {current_length:.3f} to {target_length:.3f})",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            self.moveSegmentVertexTopologically(vertex_index, new_point)
        else:
            self.resetTool()

    def moveSegmentVertexTopologically(self, vertex_index, new_point):
        """Move segment vertex considering topological editing"""
        try:
            # Get the vertex position to check for coincident vertices
            geom = self.selectedFeature.geometry()
            vertices = [QgsPointXY(pt) for pt in geom.vertices()]
            if self.geometryType == "polygon" and vertices[0] == vertices[-1]:
                vertices = vertices[:-1]

            old_vertex_point = vertices[vertex_index]

            # Check if topological editing is enabled
            project = QgsProject.instance()
            topo_editing = project.topologicalEditing()

            if topo_editing:
                # Find all coincident vertices
                coincident_vertices = self.findCoincidentVertices(
                    old_vertex_point)

                if len(coincident_vertices) > 1:
                    iface.messageBar().pushMessage(
                        "Topological Edit",
                        f"Moving {len(coincident_vertices)} coincident vertices together.",
                        duration=2
                    )

                # Move all coincident vertices
                for vertex_info in coincident_vertices:
                    layer = vertex_info['layer']
                    feature = vertex_info['feature']
                    vertex_idx = vertex_info['vertex_index']

                    geom = feature.geometry()
                    geom.moveVertex(new_point.x(), new_point.y(), vertex_idx)
                    layer.changeGeometry(feature.id(), geom)
            else:
                # Just move the selected vertex
                geom = self.selectedFeature.geometry()
                geom.moveVertex(new_point.x(), new_point.y(), vertex_index)
                self.selectedLayer.changeGeometry(
                    self.selectedFeature.id(), geom)

            self.canvas.refresh()
            self.update_dimension_labels()
            segment_text = "side" if self.geometryType == "polygon" else "segment"
            unit_display = UnitConverter.UNIT_NAMES.get(
                self.selectedUnit, self.selectedUnit)
            iface.messageBar().pushMessage(
                "Success",
                f"{segment_text.title()} length set to {self.originalLength:.3f} {unit_display}!",
                duration=2
            )

        except Exception as e:
            iface.messageBar().pushMessage(
                "Error", f"Failed to move vertex: {str(e)}", duration=2)
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

    def update_dimension_labels(self):
        # Remove old labels and disconnect signal
        if hasattr(self, 'dimension_labels'):
            for item, _ in self.dimension_labels:
                self.canvas.scene().removeItem(item)
        self.dimension_labels = []

        if hasattr(self, "labels_sync_conn"):
            try:
                self.canvas.extentsChanged.disconnect(
                    self.refresh_dimension_labels)
            except Exception:
                pass  # Not connected

        if not getattr(self, "selectedFeature", None):
            return

        geom = self.selectedFeature.geometry()
        vertices = [QgsPointXY(pt) for pt in geom.vertices()]

        if self.geometryType == "polygon" and vertices[0] == vertices[-1]:
            vertices = vertices[:-1]

        n = len(vertices)
        if n < 2:
            return

        # Get map units for display
        try:
            map_crs = QgsProject.instance().crs()
            map_units_name = UnitConverter.get_map_units_name(map_crs)
        except Exception:
            map_units_name = 'units'

        # For polygons, show all segments (closed loop)
        # For lines, show segments between consecutive vertices (open)
        segment_count = n if self.geometryType == "polygon" else n - 1

        for i in range(segment_count):
            start = vertices[i]
            if self.geometryType == "polygon":
                end = vertices[(i + 1) % n]
            else:
                end = vertices[i + 1]

            if start == end:
                continue

            mid_x = (start.x() + end.x()) / 2
            mid_y = (start.y() + end.y()) / 2
            length = math.hypot(end.x() - start.x(), end.y() - start.y())
            scene_pt = self.canvas.getCoordinateTransform().transform(QgsPointXY(mid_x, mid_y))

            # Display length with units
            txt_item = BufferedTextItem(
                f"{length:.2f} {map_units_name}",
                main_color=QColor(255, 255, 255),
                buffer_color=QColor('black'),
                buffer_width=3
            )
            txt_item.setPos(scene_pt.x() - 25, scene_pt.y() - 10)
            self.canvas.scene().addItem(txt_item)
            self.dimension_labels.append((txt_item, QgsPointXY(mid_x, mid_y)))

        # On every canvas move/zoom, update label positions
        self.canvas.extentsChanged.connect(self.refresh_dimension_labels)
        self.refresh_dimension_labels()

    def canvasMoveEvent(self, event):
        point = self.toMapCoordinates(event.pos())

        if self.state == "SELECT_VERTEX":
            if not hasattr(self, 'selectedFeature') or not self.selectedFeature:
                return

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
        elif self.state == "SELECT_FEATURE":
            pass

    def refresh_dimension_labels(self):
        if not hasattr(self, 'dimension_labels'):
            return
        for txt_item, map_pt in self.dimension_labels:
            scene_pt = self.canvas.getCoordinateTransform().transform(map_pt)
            txt_item.setPos(scene_pt.x() - 25, scene_pt.y() - 10)

    def resetTool(self, first=False):
        if self.rubberBand:
            self.rubberBand.hide()
        if self.previewBand:
            self.previewBand.hide()
        if self.featureBand:
            self.featureBand.hide()
        if hasattr(self, 'lineBand') and self.lineBand:
            self.lineBand.hide()
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
        self.geometryType = None
        self.originalLength = None
        self.selectedUnit = None
        self.state = "SELECT_FEATURE"
        self.setCursor(QCursor(Qt.CrossCursor))

        if not first:
            iface.messageBar().pushMessage(
                "Geometry Edit Tool",
                "Ready. Right-click to reset, or left-click to start new operation.",
                duration=2
            )

        # Remove dimension labels
        for item, _ in getattr(self, "dimension_labels", []):
            self.canvas.scene().removeItem(item)
        self.dimension_labels = []
        try:
            self.canvas.extentsChanged.disconnect(
                self.refresh_dimension_labels)
        except Exception:
            pass

    def deactivate(self):
        self.resetTool()
        QgsMapTool.deactivate(self)
        print("Unified Geometry Editing Tool deactivated")


# Activate the tool (run this in your QGIS Python console)
def activate_unified_tool():
    global unified_edit_tool
    canvas = iface.mapCanvas()
    unified_edit_tool = UnifiedGeometryEditTool(canvas)
    canvas.setMapTool(unified_edit_tool)
    iface.messageBar().pushMessage(
        "Enhanced Geometry Edit Tool Activated",
        "Click polygon or line, then click a vertex, then follow prompts. Now supports multiple units!",
        duration=3
    )

# Optional deactivate function


def deactivate_unified_tool():
    canvas = iface.mapCanvas()
    canvas.unsetMapTool(canvas.mapTool())


# Uncomment this line to activate on script run:
# activate_unified_tool()

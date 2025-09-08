
import math
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QPen, QFont, QColor, QPainterPath, QFontMetrics

from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                 QDoubleSpinBox, QPushButton, QFormLayout,
                                 QCheckBox, QGraphicsSimpleTextItem, QGraphicsTextItem, QMessageBox,
                                 QComboBox)

from qgis.core import (QgsVectorLayer, QgsRasterLayer, QgsGeometry, QgsPointXY, QgsWkbTypes,
                       QgsProject, QgsDistanceArea, QgsFeatureRequest, QgsRectangle,
                       QgsPointLocator, QgsVectorLayerEditUtils)

from qgis.gui import (QgsMapTool, QgsRubberBand,
                      QgsVertexMarker, QgsSnapIndicator)
from qgis.utils import iface


# Units conversion factors (to meters)
UNITS = {
    'metres': {'factor': 1.0, 'suffix': ' m', 'decimals': 3},
    'feet': {'factor': 0.3048, 'suffix': ' ft', 'decimals': 3},
    'yards': {'factor': 0.9144, 'suffix': ' yd', 'decimals': 3},
    'metric_links': {'factor': 0.2, 'suffix': ' ml', 'decimals': 3},
    'gunter_links': {'factor': 0.201168, 'suffix': ' gl', 'decimals': 3}
}

UNIT_ORDER = ['metres', 'feet', 'yards', 'metric_links', 'gunter_links']


def convert_length(value, from_unit, to_unit):
    """Convert a length value between two units.

    Args:
        value (float): Length value in from_unit.
        from_unit (str): Source unit (e.g., 'metres', 'feet').
        to_unit (str): Target unit (e.g., 'metres', 'feet').

    Returns:
        float: Converted length value.

    Raises:
        ValueError: If units are invalid or value is non-positive.
    """
    if value <= 0:
        raise ValueError("Length must be greater than 0")
    if from_unit not in UNITS or to_unit not in UNITS:
        raise ValueError("Invalid unit specified")
    meters = value * UNITS[from_unit]['factor']
    return meters / UNITS[to_unit]['factor']


class BufferedTextItem(QGraphicsTextItem):
    def __init__(self, text, main_color=QColor(255, 0, 150), buffer_color=QColor('white'),
                 buffer_width=3, font_family="calibri", font_size=9, font_weight=QFont.Bold):
        super().__init__(text)
        self.main_color = main_color
        self.buffer_color = buffer_color
        self.buffer_width = buffer_width

        # Set up font
        font = QFont(font_family, font_size, font_weight)
        self.setFont(font)

    def paint(self, painter, option, widget=None):
        painter.save()
        # Draw buffer by offsetting in a circle
        for dx in range(-self.buffer_width, self.buffer_width+1):
            for dy in range(-self.buffer_width, self.buffer_width+1):
                if dx*dx + dy*dy <= self.buffer_width*self.buffer_width and (dx != 0 or dy != 0):
                    painter.setPen(QPen(self.buffer_color))
                    painter.setFont(self.font())
                    painter.drawText(self.boundingRect().translated(
                        dx, dy), self.toPlainText())
        # Draw main text
        painter.setPen(QPen(self.main_color))
        painter.setFont(self.font())
        painter.drawText(self.boundingRect(), self.toPlainText())
        painter.restore()


class LengthInputDialog(QDialog):
    def __init__(self, vertex_index, sides, map_tool, current_unit, parent=None):
        super().__init__(parent)
        self.vertex_index = vertex_index
        self.sides = sides
        self.map_tool = map_tool
        self.current_unit = current_unit
        self.new_lengths = {}
        self.original_lengths = {}
        self.auto_adjusting = False

        self.setWindowTitle(f"Adjust Lengths - Vertex {vertex_index}")
        self.setModal(True)
        self.resize(380, 220)

        self._setup_ui()
        self._setup_connections()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        header_layout = QHBoxLayout()
        header = QLabel(f"Vertex {self.vertex_index} Connected Sides:")
        header.setStyleSheet("font-weight: bold;")
        header.setToolTip(
            "Adjust lengths of sides connected to the selected vertex")
        unit_layout = QHBoxLayout()
        unit_label = QLabel("Unit:")
        self.unit_combo = QComboBox()
        for unit in UNIT_ORDER:
            display_name = unit.replace('_', ' ').title()
            self.unit_combo.addItem(display_name, unit)
        current_index = UNIT_ORDER.index(self.current_unit)
        self.unit_combo.setCurrentIndex(current_index)
        self.unit_combo.setToolTip("Select the unit for length measurements")
        unit_layout.addWidget(unit_label)
        unit_layout.addWidget(self.unit_combo)
        unit_layout.addStretch()
        header_layout.addWidget(header)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        layout.addLayout(unit_layout)
        form = QFormLayout()
        unit_info = UNITS[self.current_unit]
        for side in self.sides:
            spinbox = QDoubleSpinBox()
            spinbox.setRange(0.001, 999999.999)
            spinbox.setDecimals(unit_info['decimals'])
            length_in_unit = side['length'] / unit_info['factor']
            spinbox.setValue(length_in_unit)
            spinbox.setSuffix(unit_info['suffix'])
            spinbox.setToolTip(
                f"Set length for {side['name']} in {self.current_unit}")
            side['input'] = spinbox
            self.original_lengths[side['name']] = length_in_unit
            form.addRow(f"{side['name']}:", spinbox)
        layout.addLayout(form)
        if len(self.sides) == 2:
            self.auto_adjust_cb = QCheckBox(
                "Auto-adjust other side to maintain valid triangle")
            self.auto_adjust_cb.setChecked(False)
            self.auto_adjust_cb.setToolTip(
                "Automatically adjust one side to ensure triangle inequality")
            layout.addWidget(self.auto_adjust_cb)
        self.preview_cb = QCheckBox("Show preview")
        self.preview_cb.setChecked(True)
        self.preview_cb.setToolTip(
            "Toggle real-time preview of vertex adjustments")
        layout.addWidget(self.preview_cb)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        layout.addWidget(self.status_label)
        buttons = QHBoxLayout()
        apply_btn = QPushButton("Apply")
        reset_btn = QPushButton("Reset")
        cancel_btn = QPushButton("Cancel")
        apply_btn.clicked.connect(self.accept)
        reset_btn.clicked.connect(self._reset_lengths)
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(apply_btn)
        buttons.addWidget(reset_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

    def _setup_connections(self):
        for side in self.sides:
            side['input'].valueChanged.connect(self._on_change)
        self.preview_cb.stateChanged.connect(self._on_change)
        self.unit_combo.currentTextChanged.connect(self._on_unit_changed)
        if len(self.sides) == 2:
            self.auto_adjust_cb.stateChanged.connect(self._on_change)
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._update_preview)

    def _on_unit_changed(self):
        new_unit = self.unit_combo.currentData()
        if new_unit == self.current_unit:
            return
        for side in self.sides:
            current_value = side['input'].value()
            try:
                new_value = convert_length(
                    current_value, self.current_unit, new_unit)
                side['input'].setDecimals(UNITS[new_unit]['decimals'])
                side['input'].setSuffix(UNITS[new_unit]['suffix'])
                side['input'].setValue(new_value)
            except ValueError as e:
                self.status_label.setText(f"⚠ {str(e)}")
        self.current_unit = new_unit
        self._on_change()

    def _on_change(self):
        if self.auto_adjusting:
            return
        self.timer.stop()
        if len(self.sides) == 2 and self.auto_adjust_cb.isChecked() and not self.auto_adjusting:
            self._handle_auto_adjustment()
        self.timer.start(200)

    def _handle_auto_adjustment(self):
        try:
            self.auto_adjusting = True
            vertices = self.map_tool.get_vertices()
            s1, s2 = self.sides
            unit_info = UNITS[self.current_unit]
            l1_unit = s1['input'].value()
            l2_unit = s2['input'].value()
            l1_meters = l1_unit * unit_info['factor']
            base_meters = self.map_tool.distance_area.measureLine(
                vertices[s1['start_vertex']], vertices[s2['end_vertex']])
            min_l2_meters = abs(l1_meters - base_meters) + 0.001
            max_l2_meters = l1_meters + base_meters - 0.001
            min_l2_unit = min_l2_meters / unit_info['factor']
            max_l2_unit = max_l2_meters / unit_info['factor']
            if l2_unit < min_l2_unit:
                s2['input'].setValue(min_l2_unit)
            elif l2_unit > max_l2_unit:
                s2['input'].setValue(max_l2_unit)
        except Exception as e:
            pass
        finally:
            self.auto_adjusting = False

    def _update_preview(self):
        if not self.preview_cb.isChecked():
            self._clear_preview()
            self.status_label.setText("")
            return
        try:
            self._get_new_lengths()
            vertices = self.map_tool.get_vertices()
            if len(self.sides) == 1:
                new_vertices = self.map_tool._adjust_single_side(
                    vertices, self.vertex_index, self.sides[0],
                    self.new_lengths[self.sides[0]['name']])
                self.status_label.setText("")
            else:
                triangle_valid, message = self._check_triangle_validity()
                if not triangle_valid:
                    if self.auto_adjust_cb.isChecked():
                        self.status_label.setText(
                            "✓ Auto-adjusted for valid triangle")
                    else:
                        self.status_label.setText(f"⚠ {message}")
                        self._clear_preview()
                        return
                else:
                    self.status_label.setText("✓ Valid triangle")
                new_vertices = self.map_tool._adjust_two_sides(
                    vertices, self.vertex_index, self.sides, self.new_lengths)
            if new_vertices:
                self._show_preview(new_vertices)
            else:
                self._clear_preview()
                if self.status_label.text() == "":
                    self.status_label.setText(
                        "⚠ Cannot calculate new position")
        except Exception as e:
            self._clear_preview()
            self.status_label.setText(f"⚠ Preview error: {str(e)}")

    def _check_triangle_validity(self):
        if len(self.sides) != 2:
            return True, ""
        try:
            vertices = self.map_tool.get_vertices()
            s1, s2 = self.sides
            base_meters = self.map_tool.distance_area.measureLine(
                vertices[s1['start_vertex']], vertices[s2['end_vertex']])
            l1_meters = self.new_lengths[s1['name']]
            l2_meters = self.new_lengths[s2['name']]
            unit_info = UNITS[self.current_unit]
            l1_display = l1_meters / unit_info['factor']
            l2_display = l2_meters / unit_info['factor']
            base_display = base_meters / unit_info['factor']
            if base_meters == 0:
                return False, "Base vertices are coincident"
            area = abs(l1_meters + l2_meters - base_meters) < 1e-10 or \
                abs(l1_meters + base_meters - l2_meters) < 1e-10 or \
                l2_meters + base_meters - l1_meters < 1e-10
            if area:
                return False, "Triangle has zero area (collinear points)"
            valid = (l1_meters + l2_meters > base_meters and
                     l1_meters + base_meters > l2_meters and
                     l2_meters + base_meters > l1_meters)
            if not valid:
                if l1_meters + l2_meters <= base_meters:
                    return False, f"Sides too short: {l1_display:.{unit_info['decimals']}f} + {l2_display:.{unit_info['decimals']}f} ≤ {base_display:.{unit_info['decimals']}f}{unit_info['suffix']}"
                elif l1_meters + base_meters <= l2_meters:
                    return False, f"Side {s1['name']} too short: {l1_display:.{unit_info['decimals']}f} + {base_display:.{unit_info['decimals']}f} ≤ {l2_display:.{unit_info['decimals']}f}{unit_info['suffix']}"
                else:
                    return False, f"Side {s2['name']} too short: {l2_display:.{unit_info['decimals']}f} + {base_display:.{unit_info['decimals']}f} ≤ {l1_display:.{unit_info['decimals']}f}{unit_info['suffix']}"
            return True, "Triangle inequality satisfied"
        except Exception as e:
            return False, f"Cannot validate triangle: {str(e)}"

    def _show_preview(self, vertices):
        rb = self.map_tool.preview_rubber_band
        rb.reset()
        if self.map_tool.layer.geometryType() == QgsWkbTypes.PolygonGeometry:
            for v in vertices + [vertices[0]]:
                rb.addPoint(v)
            rb.closePoints()
        else:
            for v in vertices:
                rb.addPoint(v)
        self.map_tool._update_length_labels(vertices)

    def _clear_preview(self):
        self.map_tool.preview_rubber_band.reset()
        self.map_tool._update_length_labels()

    def _get_new_lengths(self):
        self.new_lengths = {}
        for side in self.sides:
            try:
                meters_value = convert_length(
                    side['input'].value(), self.current_unit, 'metres')
                self.new_lengths[side['name']] = meters_value
            except ValueError as e:
                raise ValueError(f"Side {side['name']}: {str(e)}")
        return self.new_lengths

    def _reset_lengths(self):
        unit_info = UNITS[self.current_unit]
        for side in self.sides:
            length_in_unit = self.original_lengths[side['name']]
            side['input'].setValue(length_in_unit)
        self._on_change()

    def accept(self):
        self._get_new_lengths()
        if len(self.sides) == 2:
            triangle_valid, message = self._check_triangle_validity()
            if not triangle_valid and not self.auto_adjust_cb.isChecked():
                QMessageBox.warning(self, "Invalid Triangle",
                                    f"Triangle inequality not satisfied:\n{message}\n\n"
                                    "Please adjust the lengths or enable auto-adjustment.")
                return
        self._clear_preview()
        super().accept()

    def reject(self):
        self._clear_preview()
        super().reject()


class VertexTool(QgsMapTool):
    preferred_unit = 'metres'

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.layer = None
        self.feature = None
        self.geometry = None
        self.selected_vertex = -1
        self.dragging = False
        self.current_unit = VertexTool.preferred_unit
        self.vertex_markers = []
        self.length_labels = []
        self._init_rubber_bands()
        self.distance_area = QgsDistanceArea()
        self.snap_indicator = QgsSnapIndicator(canvas)
        self._setup_distance_area()

    def _init_rubber_bands(self):
        self.vertex_rubber_band = QgsRubberBand(
            self.canvas, QgsWkbTypes.PointGeometry)
        self.vertex_rubber_band.setColor(QColor(255, 0, 0, 180))
        self.vertex_rubber_band.setWidth(3)
        self.preview_rubber_band = QgsRubberBand(
            self.canvas, QgsWkbTypes.LineGeometry)
        self.preview_rubber_band.setColor(QColor(255, 0, 0, 120))
        self.preview_rubber_band.setWidth(2)

    def _setup_distance_area(self):
        try:
            self.distance_area.setSourceCrs(
                self.canvas.mapSettings().destinationCrs(),
                QgsProject.instance().transformContext())
        except Exception as e:
            iface.messageBar().pushMessage("CRS Error", str(e), level=1, duration=1)

    def activate(self):
        super().activate()
        self.canvas.setCursor(Qt.CrossCursor)
        iface.currentLayerChanged.connect(self._on_layer_changed)
        self.canvas.mapCanvasRefreshed.connect(self._on_canvas_refresh)
        if not self._check_layer():
            return
        topo_enabled = QgsProject.instance().topologicalEditing(
        ) and QgsProject.instance().snappingConfig().enabled()
        topo_msg = "enabled (with snapping)" if topo_enabled else "disabled (enable snapping and topological editing in QGIS settings)"
        iface.messageBar().pushMessage("Vertex Tool",
                                       f"Click feature → drag vertex or Ctrl+click for length dialog ({topo_msg})", level=0, duration=1)

    def deactivate(self):
        try:
            iface.currentLayerChanged.disconnect(self._on_layer_changed)
            self.canvas.mapCanvasRefreshed.disconnect(self._on_canvas_refresh)
        except:
            pass
        self._reset()
        super().deactivate()

    def _check_layer(self):
        layer = iface.activeLayer()
        if not layer:
            iface.messageBar().pushMessage("Error", "No layer selected", level=1, duration=1)
            return False
        if isinstance(layer, QgsRasterLayer):
            iface.messageBar().pushMessage(
                "Error", "Raster layers not supported", level=1, duration=1)
            return False
        if not isinstance(layer, QgsVectorLayer):
            iface.messageBar().pushMessage("Error", "Select a vector layer", level=1, duration=1)
            return False
        if layer.geometryType() == QgsWkbTypes.PointGeometry:
            iface.messageBar().pushMessage(
                "Error", "Point layers not supported", level=1, duration=1)
            return False
        if layer.geometryType() not in (QgsWkbTypes.PolygonGeometry, QgsWkbTypes.LineGeometry):
            iface.messageBar().pushMessage(
                "Error", "Line or polygon layer required", level=1, duration=1)
            return False
        if layer != self.layer:
            self._reset()
            self.layer = layer
            if not layer.isEditable():
                layer.startEditing()
        return True

    def _on_layer_changed(self):
        self._check_layer()

    def _on_canvas_refresh(self):
        if self.feature:
            self._update_length_labels()

    def canvasPressEvent(self, event):
        if not self._check_layer():
            return
        if event.button() == Qt.LeftButton:
            point = self._snap_point(event.pos())
            if not self.feature:
                self._select_feature(point)
            else:
                vertex_idx = self._get_vertex_at_point(point)
                if vertex_idx >= 0:
                    self.selected_vertex = vertex_idx
                    self._highlight_vertex(vertex_idx)
                    if event.modifiers() & Qt.ControlModifier:
                        self._show_length_dialog(vertex_idx)
                    else:
                        self.dragging = True
        elif event.button() == Qt.RightButton:
            self._reset()

    def canvasMoveEvent(self, event):
        if self.dragging and self.selected_vertex >= 0:
            point = self._snap_point(event.pos())
            self._preview_vertex_move(self.selected_vertex, point)

    def canvasReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            if self.selected_vertex >= 0:
                point = self._snap_point(event.pos())
                self._move_vertex(self.selected_vertex, point)
            self.snap_indicator.setMatch(QgsPointLocator.Match())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self.dragging:
                self._cancel_drag()
            else:
                self._reset()
        elif event.key() == Qt.Key_Q:
            self._cycle_units()

    def _cycle_units(self):
        current_index = UNIT_ORDER.index(self.current_unit)
        next_index = (current_index + 1) % len(UNIT_ORDER)
        self.current_unit = UNIT_ORDER[next_index]
        VertexTool.preferred_unit = self.current_unit
        unit_name = self.current_unit.replace('_', ' ').title()
        iface.messageBar().pushMessage(
            "Units Changed",
            f"Current unit: {unit_name}",
            level=0,
            duration=1
        )
        if self.feature:
            self._show_length_labels()

    def _snap_point(self, mouse_pos):
        match = self.canvas.snappingUtils().snapToMap(mouse_pos)
        self.snap_indicator.setMatch(match)
        return match.point() if match.isValid() else self.toMapCoordinates(mouse_pos)

    def _select_feature(self, point):
        radius = self.canvas.mapSettings().mapUnitsPerPixel() * 10
        rect = QgsRectangle(point.x() - radius, point.y() - radius,
                            point.x() + radius, point.y() + radius)
        for feature in self.layer.getFeatures(QgsFeatureRequest().setFilterRect(rect)):
            if feature.geometry().intersects(QgsGeometry.fromRect(rect)):
                self.feature = feature
                self.geometry = feature.geometry()
                self._show_vertices()
                self._show_length_labels()
                return

    def _show_vertices(self):
        self._clear_vertex_markers()
        for vertex in self.get_vertices():
            marker = QgsVertexMarker(self.canvas)
            marker.setCenter(vertex)
            marker.setColor(QColor(255, 0, 0))
            marker.setIconSize(8)
            marker.setIconType(QgsVertexMarker.ICON_CIRCLE)
            marker.setPenWidth(2)
            self.vertex_markers.append(marker)

    def _show_length_labels(self):
        self._clear_length_labels()
        vertices = self.get_vertices()
        if len(vertices) < 2:
            return
        is_polygon = self.layer.geometryType() == QgsWkbTypes.PolygonGeometry
        segments = len(vertices) if is_polygon else len(vertices) - 1
        unit_info = UNITS[self.current_unit]
        for i in range(segments):
            start = vertices[i]
            end = vertices[(i + 1) % len(vertices)
                           ] if is_polygon else vertices[i + 1]
            length_meters = self.distance_area.measureLine(start, end)
            length_in_unit = length_meters / unit_info['factor']
            mid = QgsPointXY((start.x() + end.x()) / 2,
                             (start.y() + end.y()) / 2)
            canvas_point = self.toCanvasCoordinates(mid)
            # label = QGraphicsSimpleTextItem(f"{length_in_unit:.{unit_info['decimals']}f}{unit_info['suffix']}")
            # label.setFont(QFont("Arial", 9, QFont.Bold))
            # label.setBrush(QColor(1, 231, 208))
            # label.setPen(QColor(0, 0, 0),2)
            #   # black outline for better contrast

            label = BufferedTextItem(
                f"{length_in_unit:.{unit_info['decimals']}f}{unit_info['suffix']}",
                main_color=QColor(255, 255, 255),
                buffer_color=QColor('black'),
                buffer_width=3,
                font_weight=QFont.Normal             # halo thickness
            )

            label.setPos(canvas_point.x() - label.boundingRect().width() / 2,
                         canvas_point.y() - label.boundingRect().height() / 2)
            self.canvas.scene().addItem(label)
            self.length_labels.append(label)

    def get_vertices(self):
        if not self.geometry:
            return []
        vertices = []
        geom_type = self.layer.geometryType()
        try:
            if geom_type == QgsWkbTypes.PolygonGeometry:
                if self.geometry.isMultipart():
                    for part in self.geometry.asMultiPolygon():
                        for ring in part:
                            vertices.extend(QgsPointXY(p) for p in ring[:-1])
                else:
                    for ring in self.geometry.asPolygon():
                        vertices.extend(QgsPointXY(p) for p in ring[:-1])
            else:
                if self.geometry.isMultipart():
                    for part in self.geometry.asMultiPolyline():
                        vertices.extend(QgsPointXY(p) for p in part)
                else:
                    vertices.extend(QgsPointXY(p)
                                    for p in self.geometry.asPolyline())
        except:
            pass
        return vertices

    def _get_vertex_at_point(self, point):
        vertices = self.get_vertices()
        radius = self.canvas.mapSettings().mapUnitsPerPixel() * 15
        for i, vertex in enumerate(vertices):
            if point.distance(vertex) <= radius:
                return i
        return -1

    def _highlight_vertex(self, idx):
        vertices = self.get_vertices()
        if 0 <= idx < len(vertices):
            self.vertex_rubber_band.reset()
            self.vertex_rubber_band.addPoint(vertices[idx])

    def _get_connected_sides(self, vertex_idx):
        vertices = self.get_vertices()
        if not vertices or vertex_idx >= len(vertices):
            return []
        sides = []
        is_line = self.layer.geometryType() == QgsWkbTypes.LineGeometry
        if is_line:
            if vertex_idx > 0:
                prev_idx = vertex_idx - 1
                length = self.distance_area.measureLine(
                    vertices[prev_idx], vertices[vertex_idx])
                sides.append({
                    'name': f'Side {prev_idx}-{vertex_idx}',
                    'length': length,
                    'start_vertex': prev_idx,
                    'end_vertex': vertex_idx
                })
            if vertex_idx < len(vertices) - 1:
                next_idx = vertex_idx + 1
                length = self.distance_area.measureLine(
                    vertices[vertex_idx], vertices[next_idx])
                sides.append({
                    'name': f'Side {vertex_idx}-{next_idx}',
                    'length': length,
                    'start_vertex': vertex_idx,
                    'end_vertex': next_idx
                })
        else:
            prev_idx = (vertex_idx - 1) % len(vertices)
            next_idx = (vertex_idx + 1) % len(vertices)
            prev_length = self.distance_area.measureLine(
                vertices[prev_idx], vertices[vertex_idx])
            sides.append({
                'name': f'Side {prev_idx}-{vertex_idx}',
                'length': prev_length,
                'start_vertex': prev_idx,
                'end_vertex': vertex_idx
            })
            next_length = self.distance_area.measureLine(
                vertices[vertex_idx], vertices[next_idx])
            sides.append({
                'name': f'Side {vertex_idx}-{next_idx}',
                'length': next_length,
                'start_vertex': vertex_idx,
                'end_vertex': next_idx
            })
        return sides

    def _show_length_dialog(self, vertex_idx):
        sides = self._get_connected_sides(vertex_idx)
        if not sides:
            return
        dialog = LengthInputDialog(
            vertex_idx, sides, self, self.current_unit, iface.mainWindow())
        if dialog.exec_() == QDialog.Accepted:
            self._apply_length_changes(vertex_idx, sides, dialog.new_lengths)

    def _apply_length_changes(self, vertex_idx, sides, new_lengths):
        try:
            vertices = self.get_vertices()
            if len(sides) == 1:
                new_vertices = self._adjust_single_side(
                    vertices, vertex_idx, sides[0], new_lengths[sides[0]['name']])
            else:
                new_vertices = self._adjust_two_sides(
                    vertices, vertex_idx, sides, new_lengths)
            if new_vertices:
                self._move_vertex(vertex_idx, new_vertices[vertex_idx])
                # iface.messageBar().pushMessage("Success", "Length changes applied", level=0, duration=1)
            else:
                iface.messageBar().pushMessage(
                    "Error", "Could not apply changes", level=1, duration=1)
        except Exception as e:
            iface.messageBar().pushMessage("Error", str(e), level=1, duration=1)

    def _adjust_single_side(self, vertices, vertex_idx, side, new_length):
        """Adjust a single side by moving the vertex to achieve the specified length.

        Args:
            vertices (list): List of QgsPointXY vertices.
            vertex_idx (int): Index of the vertex to adjust.
            side (dict): Side information including start/end vertex indices and name.
            new_length (float): Desired length in meters.

        Returns:
            list: Updated vertices, or None if adjustment fails.
        """
        try:
            if new_length <= 0:
                raise ValueError("Side length must be greater than 0")
            new_vertices = vertices.copy()
            current = vertices[vertex_idx]
            other_idx = side['start_vertex'] if side['end_vertex'] == vertex_idx else side['end_vertex']
            other = vertices[other_idx]
            dx = current.x() - other.x()
            dy = current.y() - other.y()
            current_length = math.sqrt(dx**2 + dy**2)
            if current_length == 0:
                raise ValueError("Cannot adjust: vertices are coincident")
            scale = new_length / current_length
            new_vertices[vertex_idx] = QgsPointXY(
                other.x() + dx * scale,
                other.y() + dy * scale
            )
            return new_vertices
        except Exception as e:
            iface.messageBar().pushMessage(
                "Error", f"Single side adjustment failed: {str(e)}", level=1, duration=1)
            return None

    def _adjust_two_sides(self, vertices, vertex_idx, sides, new_lengths):
        """Adjust two sides by moving the vertex to satisfy both lengths using the law of cosines.

        Args:
            vertices (list): List of QgsPointXY vertices.
            vertex_idx (int): Index of the vertex to adjust.
            sides (list): List of two side dictionaries with start/end vertex indices and names.
            new_lengths (dict): Desired lengths in meters for each side.

        Returns:
            list: Updated vertices, or None if adjustment fails.
        """
        try:
            new_vertices = vertices.copy()
            prev_idx = sides[0]['start_vertex']
            next_idx = sides[1]['end_vertex']
            prev_vertex = vertices[prev_idx]
            next_vertex = vertices[next_idx]
            target_prev = new_lengths[sides[0]['name']]
            target_next = new_lengths[sides[1]['name']]
            if target_prev <= 0 or target_next <= 0:
                raise ValueError("Side lengths must be greater than 0")
            base_length = self.distance_area.measureLine(
                prev_vertex, next_vertex)
            if base_length == 0:
                raise ValueError("Cannot adjust: base vertices are coincident")
            cos_angle = (target_prev**2 + base_length**2 -
                         target_next**2) / (2 * target_prev * base_length)
            if abs(cos_angle) > 1.0 - 1e-10:
                raise ValueError("Cannot adjust: vertices are collinear")
            cos_angle = max(-1.0, min(1.0, cos_angle))
            angle = math.acos(cos_angle)
            dx = next_vertex.x() - prev_vertex.x()
            dy = next_vertex.y() - prev_vertex.y()
            base_angle = math.atan2(dy, dx)
            pos1 = QgsPointXY(
                prev_vertex.x() + target_prev * math.cos(base_angle + angle),
                prev_vertex.y() + target_prev * math.sin(base_angle + angle)
            )
            pos2 = QgsPointXY(
                prev_vertex.x() + target_prev * math.cos(base_angle - angle),
                prev_vertex.y() + target_prev * math.sin(base_angle - angle)
            )
            current = vertices[vertex_idx]
            new_vertices[vertex_idx] = pos1 if current.distance(
                pos1) <= current.distance(pos2) else pos2
            return new_vertices
        except Exception as e:
            iface.messageBar().pushMessage(
                "Error", f"Two-side adjustment failed: {str(e)}", level=1, duration=1)
            return None

    def _preview_vertex_move(self, vertex_idx, new_position):
        try:
            vertices = self.get_vertices()
            preview_vertices = vertices.copy()
            preview_vertices[vertex_idx] = new_position
            self.preview_rubber_band.reset()
            is_polygon = self.layer.geometryType() == QgsWkbTypes.PolygonGeometry
            if is_polygon:
                for vertex in preview_vertices + [preview_vertices[0]]:
                    self.preview_rubber_band.addPoint(vertex)
                self.preview_rubber_band.closePoints()
            else:
                for vertex in preview_vertices:
                    self.preview_rubber_band.addPoint(vertex)
            self._update_length_labels(preview_vertices)
        except:
            pass

    def _move_vertex(self, vertex_idx, new_position):
        if not self.layer or not self.layer.isEditable():
            iface.messageBar().pushMessage("Error", "Layer is not editable", level=1, duration=1)
            return
        self.layer.beginEditCommand("Move Vertex")
        try:
            edit_utils = QgsVectorLayerEditUtils(self.layer)
            topological_editing = QgsProject.instance().topologicalEditing(
            ) and QgsProject.instance().snappingConfig().enabled()
            original_position = self.get_vertices()[vertex_idx]
            affected_features = []
            success = edit_utils.moveVertex(new_position.x(), new_position.y(),
                                            self.feature.id(), vertex_idx)
            if not success:
                raise Exception("Failed to move vertex in main feature")
            affected_features.append(self.feature.id())
            if topological_editing:
                search_radius = self.canvas.mapSettings().mapUnitsPerPixel() * 20
                snap_tolerance = 0.0001
                search_rect = QgsRectangle(
                    original_position.x() - search_radius,
                    original_position.y() - search_radius,
                    original_position.x() + search_radius,
                    original_position.y() + search_radius
                )
                for feature in self.layer.getFeatures(QgsFeatureRequest().setFilterRect(search_rect)):
                    if feature.id() == self.feature.id():
                        continue
                    other_vertices = self._get_feature_vertices(feature)
                    for idx, vertex in enumerate(other_vertices):
                        distance = vertex.distance(original_position)
                        if distance <= snap_tolerance:
                            shared_success = edit_utils.moveVertex(
                                new_position.x(), new_position.y(),
                                feature.id(), idx
                            )
                            if shared_success:
                                affected_features.append(feature.id())
                            else:
                                iface.messageBar().pushMessage("Warning",
                                                               f"Failed to update shared vertex in feature {feature.id()}", level=1, duration=1)
                # iface.messageBar().pushMessage(
                #     "Topological Edit",
                #     f"Updated {len(affected_features)} feature(s)",
                #     level=0, duration=1
                # )
            if affected_features:
                self.layer.endEditCommand()
                for fid in set(affected_features):
                    updated_feature = self.layer.getFeature(fid)
                    if updated_feature.isValid():
                        self.layer.updateFeature(updated_feature)
                    else:
                        iface.messageBar().pushMessage("Warning",
                                                       f"Failed to refresh feature {fid}", level=1, duration=1)
                self.feature = self.layer.getFeature(self.feature.id())
                self.geometry = self.feature.geometry()
                self._show_vertices()
                self._show_length_labels()
                self.preview_rubber_band.reset()
                self.layer.triggerRepaint()
                self.canvas.refresh()
            else:
                raise Exception("No features were updated")
        except Exception as e:
            self.layer.destroyEditCommand()
            iface.messageBar().pushMessage(
                "Error", f"Vertex move failed: {str(e)}", level=1, duration=1)

    def _get_feature_vertices(self, feature):
        """Get unique vertices for a specific feature.

        Args:
            feature: QgsFeature to extract vertices from.

        Returns:
            list: List of unique QgsPointXY vertices.
        """
        vertices = []
        geometry = feature.geometry()
        if not geometry:
            return vertices
        try:
            geom_type = self.layer.geometryType()
            seen_vertices = set()
            if geom_type == QgsWkbTypes.PolygonGeometry:
                if geometry.isMultipart():
                    for part in geometry.asMultiPolygon():
                        for ring in part:
                            for p in ring[:-1]:
                                vertex = QgsPointXY(p)
                                vertex_tuple = (vertex.x(), vertex.y())
                                if vertex_tuple not in seen_vertices:
                                    vertices.append(vertex)
                                    seen_vertices.add(vertex_tuple)
                else:
                    for ring in geometry.asPolygon():
                        for p in ring[:-1]:
                            vertex = QgsPointXY(p)
                            vertex_tuple = (vertex.x(), vertex.y())
                            if vertex_tuple not in seen_vertices:
                                vertices.append(vertex)
                                seen_vertices.add(vertex_tuple)
            else:
                if geometry.isMultipart():
                    for part in geometry.asMultiPolyline():
                        for p in part:
                            vertex = QgsPointXY(p)
                            vertex_tuple = (vertex.x(), vertex.y())
                            if vertex_tuple not in seen_vertices:
                                vertices.append(vertex)
                                seen_vertices.add(vertex_tuple)
                else:
                    for p in geometry.asPolyline():
                        vertex = QgsPointXY(p)
                        vertex_tuple = (vertex.x(), vertex.y())
                        if vertex_tuple not in seen_vertices:
                            vertices.append(vertex)
                            seen_vertices.add(vertex_tuple)
        except Exception as e:
            iface.messageBar().pushMessage(
                "Warning", f"Failed to extract vertices: {str(e)}", level=1, duration=1)
        return vertices

    def _update_length_labels(self, preview_vertices=None):
        vertices = preview_vertices if preview_vertices else self.get_vertices()
        if not vertices or len(vertices) < 2 or not self.length_labels:
            return
        is_polygon = self.layer.geometryType() == QgsWkbTypes.PolygonGeometry
        segments = len(vertices) if is_polygon else len(vertices) - 1
        unit_info = UNITS[self.current_unit]
        segment_data = []
        for i in range(segments):
            start = vertices[i]
            end = vertices[(i + 1) % len(vertices)
                           ] if is_polygon else vertices[i + 1]
            length_meters = self.distance_area.measureLine(start, end)
            length_in_unit = length_meters / unit_info['factor']
            mid = QgsPointXY((start.x() + end.x()) / 2,
                             (start.y() + end.y()) / 2)
            segment_data.append((length_in_unit, mid))
        for i, label in enumerate(self.length_labels[:segments]):
            length_in_unit, mid = segment_data[i]
            canvas_point = self.toCanvasCoordinates(mid)
            label.setPlainText(  # Changed from setText to setPlainText
                f"{length_in_unit:.{unit_info['decimals']}f}{unit_info['suffix']}")
            label.setPos(canvas_point.x() - label.boundingRect().width() / 2,
                         canvas_point.y() - label.boundingRect().height() / 2)

    def _cancel_drag(self):
        self.dragging = False
        self.selected_vertex = -1
        self.preview_rubber_band.reset()
        self.vertex_rubber_band.reset()
        self.snap_indicator.setMatch(QgsPointLocator.Match())
        self._show_length_labels()

    def _clear_vertex_markers(self):
        for marker in self.vertex_markers:
            self.canvas.scene().removeItem(marker)
        self.vertex_markers.clear()

    def _clear_length_labels(self):
        for label in self.length_labels:
            self.canvas.scene().removeItem(label)
        self.length_labels.clear()

    def _reset(self):
        if self.dragging:
            self._cancel_drag()
        self._clear_vertex_markers()
        self._clear_length_labels()
        if self.vertex_rubber_band:
            self.vertex_rubber_band.reset()
        if self.preview_rubber_band:
            self.preview_rubber_band.reset()
        self.snap_indicator.setMatch(QgsPointLocator.Match())
        self.feature = None
        self.geometry = None
        self.selected_vertex = -1
        self.dragging = False


def activate_vertex_tool():
    """
    Activate the vertex editing tool with multi-unit support.

    Features:
    - Multi-unit support (Q key to cycle)
    - Triangle constraint options in length dialog
    - Topological editing follows QGIS snapping and project settings
    """
    layer = iface.activeLayer()
    if not layer:
        iface.messageBar().pushMessage("Error", "No layer selected", level=1, duration=1)
        return None
    if isinstance(layer, QgsRasterLayer):
        iface.messageBar().pushMessage(
            "Error", "Raster layers not supported", level=1, duration=1)
        return None
    if not isinstance(layer, QgsVectorLayer):
        iface.messageBar().pushMessage("Error", "Select a vector layer", level=1, duration=1)
        return None
    if layer.geometryType() == QgsWkbTypes.PointGeometry:
        iface.messageBar().pushMessage(
            "Error", "Point layers not supported", level=1, duration=1)
        return None
    if layer.geometryType() not in (QgsWkbTypes.PolygonGeometry, QgsWkbTypes.LineGeometry):
        iface.messageBar().pushMessage(
            "Error", "Line or polygon layer required", level=1, duration=1)
        return None
    canvas = iface.mapCanvas()
    tool = VertexTool(canvas)
    canvas.setMapTool(tool)
    topo_enabled = QgsProject.instance().topologicalEditing(
    ) and QgsProject.instance().snappingConfig().enabled()
    status = "enabled (with snapping)" if topo_enabled else "disabled (enable snapping and topological editing in QGIS settings)"
    # iface.messageBar().pushMessage(
    #     "Vertex Tool",
    #     f"Unit: {tool.current_unit.replace('_', ' ').title()} - Topo: {status} (Q=units)",
    #     level=0,
    #     duration=1
    # )
    return tool


# Activate the tool
# tool = activate_vertex_tool()

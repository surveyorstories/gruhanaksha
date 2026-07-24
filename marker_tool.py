from qgis.gui import QgsMapToolEdit, QgsSnapIndicator
from qgis.core import QgsDistanceArea, QgsProject, QgsPointXY, QgsExpression
from .qt_compat import Qt, QtCompat, QGraphicsTextItem, QInputDialog, QDialog, QLabel, QLineEdit, QVBoxLayout, QDialogButtonBox, QPointF
import math


class MarkerMapTool(QgsMapToolEdit):
    def __init__(self, canvas, layer, markers, unit_factor=1.0, unit_label="m"):
        super(MarkerMapTool, self).__init__(canvas)
        self.canvas = canvas
        self.layer = layer
        self.markers = markers  # Reference to the shared list
        self.unit_factor = unit_factor
        self.unit_label = unit_label
        self.markerLabel = None
        self.redraw_callback = None
        self.updating_inputs = False
        self.cursor = QtCompat.cross_cursor()

        self.rubberBand = None
        self.snapIndicator = QgsSnapIndicator(canvas)
        self.setCursor(self.cursor)

        # Dragging state
        self.draggingMarker = False
        self.draggedMarkerIndex = -1

        # Geometry engine for distance calcs
        self.calculator = QgsDistanceArea()
        self.calculator.setSourceCrs(
            self.layer.crs(), QgsProject.instance().transformContext())
        if self.layer.crs().isGeographic():
            self.calculator.setEllipsoid(QgsProject.instance().ellipsoid())
        else:
            self.calculator.setEllipsoid('')

    def update_unit(self, factor, label, linear_factor=1.0, linear_label="m"):
        self.unit_factor = linear_factor
        self.unit_label = linear_label

    def canvasMoveEvent(self, event):
        try:
            if self.markerLabel:
                self.canvas.scene().removeItem(self.markerLabel)
                self.markerLabel = None

            layerPoint = self.toLayerCoordinates(self.layer, event.pos())
        except (RuntimeError, Exception):
            return

        # Dragging Logic
        if self.draggingMarker and self.draggedMarkerIndex != -1:
            snapped_point, dist, dist2, ref_vertex, ref_vertex2 = self.snapToBoundary(
                layerPoint)
            if snapped_point:
                self.markers[self.draggedMarkerIndex] = {
                    'point': snapped_point,
                    'dist': dist,
                    'dist2': dist2,
                    'ref': ref_vertex,
                    'ref2': ref_vertex2
                }
                if hasattr(self, 'redraw_callback'):
                    self.redraw_callback()
            return

        # Ghost Marker Logic (Not dragging)
        snapped_point, dist, dist2, ref_vertex, ref_vertex2 = self.snapToBoundary(
            layerPoint)

        if snapped_point:
            # Visual feedback
            label_text = f"{dist:.2f} {self.unit_label}\n{dist2:.2f} {self.unit_label}"
            label = QGraphicsTextItem(label_text)
            label.setHtml(
                f"<div style='background-color: white; border: 1px solid black; padding: 2px; color: black; font-size: 10px;'>{dist:.2f} {self.unit_label} <br> {dist2:.2f} {self.unit_label}</div>")

            canvas_pt = QPointF(self.toCanvasCoordinates(snapped_point))
            label.setPos(canvas_pt.x() + 10, canvas_pt.y() + 10)
            self.canvas.scene().addItem(label)
            self.markerLabel = label

    def canvasPressEvent(self, event):
        try:
            layerPoint = self.toLayerCoordinates(self.layer, event.pos())
        except (RuntimeError, Exception):
            return

        # Check for existing marker hit
        # Use canvas coordinates for hit test (pixel distance)
        canvas_click = event.pos()
        hit_threshold = 10  # pixels

        clicked_marker_idx = -1
        for i, marker in enumerate(self.markers):
            marker_pt = marker['point']
            marker_canvas_pt = self.toCanvasCoordinates(marker_pt)

            # Simple distance in pixels
            dx = marker_canvas_pt.x() - canvas_click.x()
            dy = marker_canvas_pt.y() - canvas_click.y()
            if math.sqrt(dx*dx + dy*dy) < hit_threshold:
                clicked_marker_idx = i
                break

        if event.button() == QtCompat.LeftButton:
            if clicked_marker_idx != -1:
                # Start Dragging
                self.draggingMarker = True
                self.draggedMarkerIndex = clicked_marker_idx
                self.setCursor(QtCompat.closed_hand_cursor())
            else:
                # Add New Marker
                # ... (rest of add marker logic)
                snapped_point, dist, dist2, ref_vertex, ref_vertex2 = self.snapToBoundary(
                    layerPoint)

                if snapped_point:
                    self.markers.append({
                        'point': snapped_point,
                        'dist': dist,
                        'dist2': dist2,
                        'ref': ref_vertex,
                        'ref2': ref_vertex2
                    })
                    if hasattr(self, 'redraw_callback'):
                        self.redraw_callback()

        elif event.button() == QtCompat.RightButton:
            if clicked_marker_idx != -1:
                self.editMarkerDistance(clicked_marker_idx)

    def editMarkerDistance(self, index):
        marker = self.markers[index]
        dist = marker['dist']
        dist2 = marker.get('dist2', 0.0)
        unit = self.unit_label

        # Custom Dialog
        dialog = QDialog()
        dialog.setWindowTitle("Edit Marker Distance")
        layout = QVBoxLayout(dialog)

        # Input 1
        label1 = QLabel(f"Distance from Start ({unit}):")
        input1 = QLineEdit(f"{dist:.2f}")
        layout.addWidget(label1)
        layout.addWidget(input1)

        # Input 2
        label2 = QLabel(f"Distance from End ({unit}):")
        input2 = QLineEdit(f"{dist2:.2f}")
        layout.addWidget(label2)
        layout.addWidget(input2)

        # Calculate Total Length for live updates
        ref = marker.get('ref')
        ref2 = marker.get('ref2')
        total_len = 0.0
        if ref and ref2:
            total_len = self.calculator.measureLine(
                ref, ref2) * self.unit_factor

        # Live Update Logic
        self.updating_inputs = False

        def update_input2(text):
            if self.updating_inputs:
                return
            self.updating_inputs = True
            try:
                val1 = float(text)
                val2 = max(0, total_len - val1)
                input2.setText(f"{val2:.2f}")
            except ValueError:
                pass
            self.updating_inputs = False

        def update_input1(text):
            if self.updating_inputs:
                return
            self.updating_inputs = True
            try:
                val2 = float(text)
                val1 = max(0, total_len - val2)
                input1.setText(f"{val1:.2f}")
            except ValueError:
                pass
            self.updating_inputs = False

        input1.textEdited.connect(update_input2)
        input2.textEdited.connect(update_input1)

        # Buttons
        buttons = QDialogButtonBox(
            QtCompat.DialogOk | QtCompat.DialogCancel)

        # Add Delete Button
        delete_btn = buttons.addButton(
            "Delete Marker", QtCompat.DialogButtonDestructiveRole)

        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        def delete_action():
            dialog.done(2)  # Custom return code for delete

        delete_btn.clicked.connect(delete_action)

        layout.addWidget(buttons)

        result = QtCompat.exec(dialog)

        if result == 2:  # Delete triggered
            del self.markers[index]
            if hasattr(self, 'redraw_callback'):
                self.redraw_callback()
            return

        if result == QtCompat.DialogAccepted:
            try:
                # Safe eval function
                def safe_eval(expr):
                    # Use QgsExpression for safe evaluation of math
                    exp = QgsExpression(expr)
                    if exp.hasParserError():
                        raise ValueError(exp.parserErrorString())
                    result = exp.evaluate()
                    if exp.hasEvalError():
                        raise ValueError(exp.evalErrorString())
                    return float(result)

                new_dist = safe_eval(input1.text())
                new_dist2 = safe_eval(input2.text())

                # Check what changed
                epsilon = 0.001

                ref = marker.get('ref')
                ref2 = marker.get('ref2')

                if not ref or not ref2:
                    return

                dx = ref2.x() - ref.x()
                dy = ref2.y() - ref.y()
                full_len_display = self.calculator.measureLine(
                    ref, ref2) * self.unit_factor

                target_dist = -1

                if abs(new_dist - dist) > epsilon:
                    target_dist = new_dist
                elif abs(new_dist2 - dist2) > epsilon:
                    target_dist = full_len_display - new_dist2

                if target_dist != -1:
                    target_dist = max(0, min(full_len_display, target_dist))

                    if full_len_display > 0:
                        t = target_dist / full_len_display

                        new_x = ref.x() + t * dx
                        new_y = ref.y() + t * dy
                        new_point = QgsPointXY(new_x, new_y)

                        self.markers[index]['point'] = new_point
                        self.markers[index]['dist'] = target_dist
                        self.markers[index]['dist2'] = full_len_display - \
                            target_dist

                        if hasattr(self, 'redraw_callback'):
                            self.redraw_callback()

            except Exception:  # nosec B110
                pass

    def canvasReleaseEvent(self, event):
        if self.draggingMarker:
            self.draggingMarker = False
            self.draggedMarkerIndex = -1
            self.setCursor(self.cursor)

    def snapToBoundary(self, layerPoint):
        # Snap to nearest polygon segment
        min_dist = float('inf')
        snapped_point = None
        ref_vertex = None
        ref_vertex2 = None

        ref_vertex2 = None

        try:
            selectedFeatures = []
            if self.layer:
                selectedFeatures = self.layer.selectedFeatures()
            if len(selectedFeatures) > 0:
                geom = selectedFeatures[0].geometry()
                polygons = []
                if geom.isMultipart():
                    polygons = geom.asMultiPolygon()
                else:
                    p = geom.asPolygon()
                    if p:
                        polygons = [p]

                for poly in polygons:
                    if not poly:
                        continue
                    ring = poly[0]
                    for i in range(len(ring) - 1):
                        p1 = ring[i]
                        p2 = ring[i+1]

                        dist_to_segment = self.distancePointLine(
                            layerPoint.x(), layerPoint.y(), p1.x(), p1.y(), p2.x(), p2.y())

                        if dist_to_segment < min_dist:
                            min_dist = dist_to_segment
                            vx, vy = p2.x() - p1.x(), p2.y() - p1.y()
                            mag_sq = vx*vx + vy*vy
                            if mag_sq > 0:
                                u = ((layerPoint.x() - p1.x()) * vx +
                                     (layerPoint.y() - p1.y()) * vy) / mag_sq
                                u = max(0, min(1, u))
                                snapped_point = QgsPointXY(
                                    p1.x() + u*vx, p1.y() + u*vy)
                                ref_vertex = p1
                                ref_vertex2 = p2
                            else:
                                snapped_point = p1
                                ref_vertex = p1
                                ref_vertex2 = p2

        except (RuntimeError, Exception):
            pass

        dist = 0
        dist2 = 0
        if snapped_point and ref_vertex:
            # Ensure ref_vertex is QgsPointXY if implicit conversion needed,
            # but QgsGeometry.asPolygon returns lists of QgsPointXY usually.
            dist_val = self.calculator.measureLine(ref_vertex, snapped_point)
            dist = dist_val * self.unit_factor

            if ref_vertex2:
                dist2_val = self.calculator.measureLine(
                    ref_vertex2, snapped_point)
                dist2 = dist2_val * self.unit_factor

        return snapped_point, dist, dist2, ref_vertex, ref_vertex2

    def distancePointLine(self, px, py, x1, y1, x2, y2):
        # ... logic ...
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0 and dy == 0:
            return math.sqrt((px - x1)**2 + (py - y1)**2)
        t = ((px - x1) * dx + (py - y1) * dy) / (dx*dx + dy*dy)
        t = max(0, min(1, t))
        x = x1 + t * dx
        y = y1 + t * dy
        return math.sqrt((px - x)**2 + (py - y)**2)

    def stopCapturing(self):
        self.draggingMarker = False
        self.draggedMarkerIndex = -1
        self.setCursor(self.cursor)

    def deactivate(self):
        if self.markerLabel:
            self.canvas.scene().removeItem(self.markerLabel)
        super(MarkerMapTool, self).deactivate()

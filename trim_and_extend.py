# === Trim/Extend Tool for QGIS (Lines + Polygon Trim Support) ===
# Works in QGIS 3.26–3.38
# ENHANCED: Detects if cursor is near vertex (moves vertex) or near side (moves side)
# NEW: Layer change detection and multi-trim when dragging with free streaming curve

from qgis.gui import QgsMapTool, QgsRubberBand
from qgis.core import (
    QgsPointXY, QgsGeometry, QgsRectangle, QgsFeatureRequest,
    QgsWkbTypes, QgsProject, QgsMapLayer, QgsVectorLayer, QgsFeature, QgsMessageLog, Qgis
)
from qgis.PyQt.QtCore import Qt, pyqtSignal, QObject
from qgis.PyQt.QtGui import QCursor, QColor
from .qt_compat import QtCompat
import math


# ---------- Utility Helpers ----------
def _dist(a: QgsPointXY, b: QgsPointXY) -> float:
    return math.hypot(a.x() - b.x(), a.y() - b.y())


def _normalize(dx: float, dy: float) -> tuple[float, float]:
    L = math.hypot(dx, dy) or 1.0
    return dx / L, dy / L


def _extract_points(geom: QgsGeometry) -> list[QgsPointXY]:
    pts = []
    if not geom or geom.isEmpty():
        return pts
    try:
        t = geom.type()
        if t == QgsWkbTypes.GeometryType.PointGeometry:
            if geom.isMultipart():
                for p in geom.asMultiPoint():
                    pts.append(QgsPointXY(p.x(), p.y()))
            else:
                p = geom.asPoint()
                pts.append(QgsPointXY(p.x(), p.y()))
        elif t == QgsWkbTypes.GeometryType.LineGeometry:
            if geom.isMultipart():
                for line in geom.asMultiPolyline():
                    for p in line:
                        pts.append(QgsPointXY(p.x(), p.y()))
            else:
                for v in geom.vertices():
                    pts.append(QgsPointXY(v.x(), v.y()))
        elif t == QgsWkbTypes.GeometryType.PolygonGeometry:
            # For polygons, we might want boundary vertices
            if geom.isMultipart():
                for poly in geom.asMultiPolygon():
                    for ring in poly:
                        for p in ring:
                            pts.append(QgsPointXY(p.x(), p.y()))
            else:
                for ring in geom.asPolygon():
                    for p in ring:
                        pts.append(QgsPointXY(p.x(), p.y()))
        else:
            # Fallback for collection or other
            for part in geom.asGeometryCollection():
                pts.extend(_extract_points(part))
        return pts
    except Exception as e:
        QgsMessageLog.logMessage(
            f"Error extracting points: {e}", "TrimExtendTool", Qgis.MessageLevel.Warning)
        return []


# ---------- Main Tool ----------
class TrimExtendTool(QgsMapTool):
    def __init__(self, iface, canvas, layer: QgsVectorLayer, pixel_tolerance=15):
        super().__init__(canvas)
        self.iface = iface
        self.canvas = canvas
        self.layer = layer
        if not self.layer:
            raise ValueError("No active layer.")
        if self.layer.geometryType() not in (QgsWkbTypes.GeometryType.LineGeometry, QgsWkbTypes.GeometryType.PolygonGeometry):
            raise ValueError("Layer must be Line or Polygon type.")
        if not self.layer.isEditable():
            raise ValueError("Layer must be in editing mode (startEditing()).")

        self.is_polygon_layer = (
            self.layer.geometryType() == QgsWkbTypes.GeometryType.PolygonGeometry)
        self.pixel_tolerance = max(5, min(50, int(pixel_tolerance)))

        # State
        self.reference_geom = None
        self.reference_layer = None
        self.reference_fid = None
        self.waiting_for_reference = True

        # Drag state for multi-trim
        self.is_dragging = False
        self.drag_path = []  # List of points in the drag path
        self.drag_features = []  # Features along the drag path
        self.drag_rubber = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.drag_rubber.setColor(QColor(0, 0, 255, 150))
        self.drag_rubber.setWidth(2)

        # Cursor & visuals
        self.setCursor(QtCompat.cross_cursor())

        self.reference_rubber = QgsRubberBand(
            self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.reference_rubber.setColor(QColor(255, 0, 0, 200))
        self.reference_rubber.setWidth(3)

        self.preview_rubber = QgsRubberBand(
            self.canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.preview_rubber.setColor(QColor(0, 255, 0, 120))
        self.preview_rubber.setFillColor(QColor(0, 255, 0, 50))
        self.preview_rubber.setWidth(2)

        self.trim_rubber = QgsRubberBand(
            self.canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.trim_rubber.setColor(QColor(255, 60, 60, 180))
        self.trim_rubber.setFillColor(QColor(255, 60, 60, 80))
        self.trim_rubber.setWidth(2)

        self.press_point = None

        # Connect to layer change signals
        QgsProject.instance().layersAdded.connect(self._on_layers_changed)
        QgsProject.instance().layersRemoved.connect(self._on_layers_changed)
        QgsProject.instance().layerWasAdded.connect(self._on_layers_changed)
        QgsProject.instance().layerWillBeRemoved.connect(self._on_layers_changed)
        self.iface.currentLayerChanged.connect(self._on_current_layer_changed)

    # ---------- Lifecycle ----------
    def activate(self):
        super().activate()
        if self.is_polygon_layer:
            self.iface.messageBar().pushMessage("Trim/Extend",
                                                "Click to select reference line/polygon (red), then click polygon vertex or side.", level=Qgis.MessageLevel.Info)
            print("Trim/Extend tool activated. Click to select reference line/polygon (red), then click polygon vertex or side.")
        else:
            self.iface.messageBar().pushMessage("Trim/Extend",
                                                "Click to select reference (red), hover near line ends to preview.", level=Qgis.MessageLevel.Info)
            print(
                "Trim/Extend tool activated. Click to select reference (red), hover near line ends to preview.")

    def deactivate(self):
        super().deactivate()
        self._reset()
        print("Tool deactivated.")

        # Disconnect signals
        try:
            QgsProject.instance().layersAdded.disconnect(self._on_layers_changed)
            QgsProject.instance().layersRemoved.disconnect(self._on_layers_changed)
            QgsProject.instance().layerWasAdded.disconnect(self._on_layers_changed)
            QgsProject.instance().layerWillBeRemoved.disconnect(self._on_layers_changed)
            self.iface.currentLayerChanged.disconnect(
                self._on_current_layer_changed)
        except Exception:  # nosec B110
            pass

    def keyPressEvent(self, event):
        if event.key() == QtCompat.Key_Escape:
            self.canvas.unsetMapTool(self)

    def _reset(self):
        self.reference_geom = None
        self.reference_layer = None
        self.reference_fid = None
        self.waiting_for_reference = True
        self.is_dragging = False
        self.press_point = None
        self.drag_path = []
        self.drag_features = []
        self.reference_rubber.reset(QgsWkbTypes.GeometryType.LineGeometry)
        self.preview_rubber.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        self.trim_rubber.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        self.drag_rubber.reset(QgsWkbTypes.GeometryType.LineGeometry)

        # Check if current layer is still valid
        current_layer = self.iface.activeLayer()
        if current_layer != self.layer:
            self._update_layer(current_layer)

    # ---------- Layer Change Detection ----------
    def _on_layers_changed(self):
        """Handle when layers are added or removed"""
        current_layer = self.iface.activeLayer()
        if current_layer != self.layer:
            self._update_layer(current_layer)

    def _on_current_layer_changed(self, layer):
        """Handle when the current layer changes"""
        if layer != self.layer:
            self._update_layer(layer)

    def _update_layer(self, new_layer):
        """Update the tool to work with a new layer"""
        if not new_layer or new_layer.type() != QgsMapLayer.LayerType.VectorLayer:
            self.canvas.unsetMapTool(self)
            self.iface.messageBar().pushMessage(
                "Error", "The active layer is not a vector layer. Tool deactivated.", level=Qgis.MessageLevel.Critical)
            return

        if new_layer.geometryType() not in (QgsWkbTypes.GeometryType.LineGeometry, QgsWkbTypes.GeometryType.PolygonGeometry):
            self.canvas.unsetMapTool(self)
            self.iface.messageBar().pushMessage("Error",
                                                "The active layer is not a line or polygon layer. Tool deactivated.", level=Qgis.MessageLevel.Critical)
            return

        if not new_layer.isEditable():
            self.canvas.unsetMapTool(self)
            self.iface.messageBar().pushMessage(
                "Error", "The active layer is not in edit mode. Tool deactivated.", level=Qgis.MessageLevel.Critical)
            return

        # Update layer and reset state
        self.layer = new_layer
        self.is_polygon_layer = (
            self.layer.geometryType() == QgsWkbTypes.GeometryType.PolygonGeometry)
        self._reset()

        # Update rubber bands
        if self.is_polygon_layer:
            self.preview_rubber.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            self.trim_rubber.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        else:
            self.preview_rubber.reset(QgsWkbTypes.GeometryType.LineGeometry)
            self.trim_rubber.reset(QgsWkbTypes.GeometryType.LineGeometry)

        print(f"Switched to layer: {new_layer.name()}")
        self.activate()

    # ---------- ENHANCED: Robust feature lookup for overlapping polygons ----------
    def _get_closest_feature(self, point: QgsPointXY, exclude_reference=False) -> QgsFeature:
        """Get closest feature, with improved handling for overlapping polygons"""
        tol_map = self.canvas.mapSettings().mapUnitsPerPixel() * self.pixel_tolerance
        search_rect = QgsRectangle.fromCenterAndSize(
            point, tol_map * 2, tol_map * 2)
        req = QgsFeatureRequest().setFilterRect(search_rect)

        # Get all features in the search area
        all_features = []
        for f in self.layer.getFeatures(req):
            if exclude_reference and self.reference_layer == self.layer and f.id() == self.reference_fid:
                continue

            g = f.geometry()
            if not g or g.isEmpty():
                continue

            # Calculate distance based on geometry type
            if g.type() == QgsWkbTypes.GeometryType.PolygonGeometry:
                # For polygons, check if point is inside first
                if g.contains(QgsGeometry.fromPointXY(point)):
                    # Point is inside polygon - very high priority
                    all_features.append((f, 0))
                else:
                    # Point is outside - find distance to boundary
                    boundary = g.convertToType(QgsWkbTypes.GeometryType.LineGeometry, True)
                    nearest = boundary.nearestPoint(
                        QgsGeometry.fromPointXY(point)).asPoint()
                    d = math.hypot(nearest.x() - point.x(),
                                   nearest.y() - point.y())
                    if d <= tol_map:
                        all_features.append((f, d))
            else:
                # For lines, find nearest point
                np = g.nearestPoint(QgsGeometry.fromPointXY(point)).asPoint()
                d = math.hypot(np.x() - point.x(), np.y() - point.y())
                if d <= tol_map:
                    all_features.append((f, d))

        if not all_features:
            return None

        # Separate features by distance (0 for inside polygon)
        inside_features = [f for f, d in all_features if d == 0]
        outside_features = [f for f, d in all_features if d > 0]

        # If we have polygons that contain the point, select the one with highest ID
        # (assuming higher IDs are drawn later/on top)
        if inside_features:
            best_feature = max(inside_features, key=lambda f: f.id())
            return best_feature

        # Otherwise, select the closest one
        if outside_features:
            # Sort by distance and then by ID (higher ID wins ties)
            outside_features.sort(key=lambda f: (all_features[next(
                i for i, (feat, _) in enumerate(all_features) if feat.id() == f.id())][1], -f.id()))
            return outside_features[0]

        return None

    # ---------- Get features along drag path ----------
    def _get_features_along_path(self, drag_path: list[QgsPointXY]) -> list[QgsFeature]:
        """Get all features that intersect with the drag path"""
        if not self.layer or len(drag_path) < 2:
            return []

        # Create a line from the drag path
        path_geom = QgsGeometry.fromPolylineXY(drag_path)

        # Buffer the path to catch nearby features
        buffer_dist = self.canvas.mapSettings().mapUnitsPerPixel() * \
            self.pixel_tolerance * 2
        buffered_path = path_geom.buffer(buffer_dist, 5)

        search_rect = buffered_path.boundingBox()
        req = QgsFeatureRequest().setFilterRect(search_rect)

        features = []
        for f in self.layer.getFeatures(req):
            # Skip reference feature
            if self.reference_layer == self.layer and f.id() == self.reference_fid:
                continue

            g = f.geometry()
            if not g or g.isEmpty():
                continue

            # Check if feature intersects with buffered path
            if buffered_path.intersects(g):
                features.append(f)

        return features

    # ---------- Get drag direction ----------
    def _get_drag_direction(self, drag_path: list[QgsPointXY]):
        """Get the overall drag direction from first to last point"""
        if len(drag_path) < 2:
            return None, None

        start = drag_path[0]
        end = drag_path[-1]

        dx = end.x() - start.x()
        dy = end.y() - start.y()

        return dx, dy

    # ---------- Snap helper ----------
    def _snap_to_reference(self, point_xy: QgsPointXY):
        if not self.reference_geom:
            return point_xy
        snapped = self.reference_geom.nearestPoint(
            QgsGeometry.fromPointXY(point_xy)).asPoint()
        return QgsPointXY(snapped.x(), snapped.y())

    # ---------- NEW: Detect if cursor is near vertex or side ----------
    def _detect_vertex_or_side(self, geom: QgsGeometry, click_point: QgsPointXY):
        """
        Returns: ('vertex', vertex_index, vertex_point) OR ('side', side_index, (p1, p2))
        """
        verts = [QgsPointXY(v.x(), v.y()) for v in geom.vertices()]
        if len(verts) > 1 and verts[0] == verts[-1]:
            verts = verts[:-1]  # Remove closing point

        if len(verts) < 3:
            return None, None, None

        vertex_tol = self.canvas.mapSettings().mapUnitsPerPixel() * self.pixel_tolerance

        # Check vertices first (higher priority)
        for i, v in enumerate(verts):
            if _dist(click_point, v) < vertex_tol:
                return 'vertex', i, v

        # Check sides
        best_dist = float('inf')
        best_side = None
        best_idx = None

        n = len(verts)
        for i in range(n):
            p1 = verts[i]
            p2 = verts[(i + 1) % n]

            seg = QgsGeometry.fromPolylineXY([p1, p2])
            nearest = seg.nearestPoint(
                QgsGeometry.fromPointXY(click_point)).asPoint()
            dist = _dist(click_point, QgsPointXY(nearest.x(), nearest.y()))

            if dist < best_dist:
                best_dist = dist
                best_side = (p1, p2)
                best_idx = i

        if best_dist < vertex_tol * 1.5:  # Slightly larger tolerance for sides
            return 'side', best_idx, best_side

        return None, None, None

    # ---------- NEW: Move vertex while maintaining angles ----------
    def _move_vertex_with_angles(self, geom: QgsGeometry, vertex_idx: int, click_point: QgsPointXY):
        """
        Move a vertex to the reference line while maintaining the angles
        of the two adjacent sides
        """
        if not self.reference_geom:
            return None, "vertex_move"

        verts = [QgsPointXY(v.x(), v.y()) for v in geom.vertices()]
        if len(verts) > 1 and verts[0] == verts[-1]:
            verts = verts[:-1]

        n = len(verts)
        if n < 3:
            return None, "vertex_move"

        # Get the vertex and its neighbors
        v_curr = verts[vertex_idx]
        v_prev = verts[(vertex_idx - 1) % n]
        v_next = verts[(vertex_idx + 1) % n]

        # Calculate the two direction vectors from adjacent sides
        dx_prev = v_curr.x() - v_prev.x()
        dy_prev = v_curr.y() - v_prev.y()
        len_prev = math.hypot(dx_prev, dy_prev)

        dx_next = v_curr.x() - v_next.x()
        dy_next = v_curr.y() - v_next.y()
        len_next = math.hypot(dx_next, dy_next)

        if len_prev < 1e-9 or len_next < 1e-9:
            return None, "vertex_move"

        # Normalize directions
        dir_prev_x, dir_prev_y = dx_prev / len_prev, dy_prev / len_prev
        dir_next_x, dir_next_y = dx_next / len_next, dy_next / len_next

        # Create rays from previous and next vertices
        ray_len = max(self.canvas.extent().width(),
                      self.canvas.extent().height()) * 3.0

        # Ray from v_prev in the direction of the side
        ray_prev_end = QgsPointXY(v_prev.x() + dir_prev_x * ray_len,
                                  v_prev.y() + dir_prev_y * ray_len)
        ray_prev = QgsGeometry.fromPolylineXY([v_prev, ray_prev_end])

        # Ray from v_next in the direction of the side
        ray_next_end = QgsPointXY(v_next.x() + dir_next_x * ray_len,
                                  v_next.y() + dir_next_y * ray_len)
        ray_next = QgsGeometry.fromPolylineXY([v_next, ray_next_end])

        # Find intersections with reference
        inter_prev = ray_prev.intersection(self.reference_geom)
        inter_next = ray_next.intersection(self.reference_geom)

        pts_prev = _extract_points(inter_prev)
        pts_next = _extract_points(inter_next)

        # Find valid intersection points (in the correct direction)
        valid_prev = []
        for pt in pts_prev:
            to_pt_x = pt.x() - v_prev.x()
            to_pt_y = pt.y() - v_prev.y()
            dot = to_pt_x * dir_prev_x + to_pt_y * dir_prev_y
            if dot > 1e-6:
                valid_prev.append((pt, _dist(v_prev, pt)))

        valid_next = []
        for pt in pts_next:
            to_pt_x = pt.x() - v_next.x()
            to_pt_y = pt.y() - v_next.y()
            dot = to_pt_x * dir_next_x + to_pt_y * dir_next_y
            if dot > 1e-6:
                valid_next.append((pt, _dist(v_next, pt)))

        if not valid_prev and not valid_next:
            return None, "vertex_move"

        # Choose the closest intersection point
        new_vertex = None
        if valid_prev and valid_next:
            closest_prev = min(valid_prev, key=lambda x: x[1])
            closest_next = min(valid_next, key=lambda x: x[1])
            # Use the one closer to original vertex
            if _dist(v_curr, closest_prev[0]) < _dist(v_curr, closest_next[0]):
                new_vertex = closest_prev[0]
            else:
                new_vertex = closest_next[0]
        elif valid_prev:
            new_vertex = min(valid_prev, key=lambda x: x[1])[0]
        else:
            new_vertex = min(valid_next, key=lambda x: x[1])[0]

        if not new_vertex:
            return None, "vertex_move"

        # Snap to reference
        new_vertex = self._snap_to_reference(new_vertex)

        # Create new vertex list
        new_verts = []
        for i in range(n):
            if i == vertex_idx:
                new_verts.append(new_vertex)
            else:
                new_verts.append(verts[i])

        # Close polygon
        new_verts.append(new_verts[0])

        new_geom = QgsGeometry.fromPolygonXY([new_verts])

        if new_geom.isEmpty() or not new_geom.isGeosValid():
            return None, "vertex_move"

        return new_geom, "vertex_move"

    # ---------- Move entire side ----------
    def _move_side(self, geom: QgsGeometry, side_idx: int, click_point: QgsPointXY):
        """
        Move an entire side of the polygon to the reference line
        (existing functionality)
        """
        if not self.reference_geom:
            return None, "side_move"

        verts = [QgsPointXY(v.x(), v.y()) for v in geom.vertices()]
        if len(verts) > 1 and verts[0] == verts[-1]:
            verts = verts[:-1]

        n = len(verts)
        idx_p1 = side_idx
        idx_p2 = (side_idx + 1) % n

        p1 = verts[idx_p1]
        p2 = verts[idx_p2]

        # Get adjacent vertices
        idx_prev_p1 = (idx_p1 - 1) % n
        idx_next_p2 = (idx_p2 + 1) % n

        prev_p1 = verts[idx_prev_p1]
        next_p2 = verts[idx_next_p2]

        # Try to extend both endpoints
        ray_len = max(self.canvas.extent().width(),
                      self.canvas.extent().height()) * 3.0

        # --- Try extending p1 ---
        new_p1 = None
        dx1 = p1.x() - prev_p1.x()
        dy1 = p1.y() - prev_p1.y()
        len1 = math.hypot(dx1, dy1)

        if len1 > 1e-9:
            dir1_x, dir1_y = dx1 / len1, dy1 / len1
            ray1_end = QgsPointXY(p1.x() + dir1_x * ray_len,
                                  p1.y() + dir1_y * ray_len)
            ray1 = QgsGeometry.fromPolylineXY([p1, ray1_end])

            inter1 = ray1.intersection(self.reference_geom)
            pts1 = _extract_points(inter1)

            valid1 = []
            for pt in pts1:
                to_pt_x = pt.x() - p1.x()
                to_pt_y = pt.y() - p1.y()
                dot = to_pt_x * dir1_x + to_pt_y * dir1_y
                if dot > 1e-6:
                    valid1.append((pt, _dist(p1, pt)))

            if valid1:
                new_p1 = self._snap_to_reference(
                    min(valid1, key=lambda x: x[1])[0])

        # --- Try extending p2 ---
        new_p2 = None
        dx2 = p2.x() - next_p2.x()
        dy2 = p2.y() - next_p2.y()
        len2 = math.hypot(dx2, dy2)

        if len2 > 1e-9:
            dir2_x, dir2_y = dx2 / len2, dy2 / len2
            ray2_end = QgsPointXY(p2.x() + dir2_x * ray_len,
                                  p2.y() + dir2_y * ray_len)
            ray2 = QgsGeometry.fromPolylineXY([p2, ray2_end])

            inter2 = ray2.intersection(self.reference_geom)
            pts2 = _extract_points(inter2)

            valid2 = []
            for pt in pts2:
                to_pt_x = pt.x() - p2.x()
                to_pt_y = pt.y() - p2.y()
                dot = to_pt_x * dir2_x + to_pt_y * dir2_y
                if dot > 1e-6:
                    valid2.append((pt, _dist(p2, pt)))

            if valid2:
                new_p2 = self._snap_to_reference(
                    min(valid2, key=lambda x: x[1])[0])

        # Update vertices based on results
        if new_p1 and new_p2:
            new_verts = []
            for i in range(n):
                if i == idx_p1:
                    new_verts.append(new_p1)
                elif i == idx_p2:
                    new_verts.append(new_p2)
                else:
                    new_verts.append(verts[i])
        elif new_p1:
            new_verts = []
            for i in range(n):
                if i == idx_p1:
                    new_verts.append(new_p1)
                else:
                    new_verts.append(verts[i])
        elif new_p2:
            new_verts = []
            for i in range(n):
                if i == idx_p2:
                    new_verts.append(new_p2)
                else:
                    new_verts.append(verts[i])
        else:
            return None, "side_move"

        # Close the polygon
        new_verts.append(new_verts[0])

        new_geom = QgsGeometry.fromPolygonXY([new_verts])

        if new_geom.isEmpty() or not new_geom.isGeosValid():
            return None, "side_move"

        return new_geom, "side_move"

    # ---------- Polygon Trim ----------
    def _trim_polygon(self, geom: QgsGeometry, click_point: QgsPointXY, drag_path=None, drag_dx=None, drag_dy=None):
        """Split polygon by reference line and keep the part based on drag direction or path"""
        if not self.reference_geom:
            return None, None

        try:
            # Buffer the reference line to create a splitting polygon
            # IMPORTANT: Use a small buffer relative to the map scale/coordinates
            # Using mapUnitsPerPixel ensures it adapts to the zoom level if in canvas units,
            # but ideally we want a small fix epsilon.
            # 0.0001 is often too small for projected CRS, but might be ok.
            # Lets try to derive it safely.
            buffer_width = 0.000001
            buffered = self.reference_geom.buffer(buffer_width, 1)

            # Try difference operation
            difference = geom.difference(buffered)

            if difference.isEmpty():
                return None, None

            # If result is multipolygon, find which part to keep
            parts = []
            if difference.isMultipart():
                for part in difference.asGeometryCollection():
                    if part.type() == QgsWkbTypes.GeometryType.PolygonGeometry:
                        parts.append(part)
            else:
                parts = [difference]

            if not parts:
                return None, None

            # Determine which part to keep based on drag approach
            if drag_path and len(drag_path) > 1:
                # DRAG PATH APPROACH: Trim parts that intersect with drag path
                drag_geom = QgsGeometry.fromPolylineXY(drag_path)

                # Find parts that DON'T intersect with the drag path
                kept_parts = []

                for part in parts:
                    if not drag_geom.intersects(part):
                        # This part should be kept
                        kept_parts.append(part)

                # Combine all kept parts
                if kept_parts:
                    result = kept_parts[0]
                    for part in kept_parts[1:]:
                        result = result.combine(part)
                    return result, None
                else:
                    # If nothing to keep, return None
                    return None, None

            elif drag_dx is not None and drag_dy is not None:
                # DIRECTION APPROACH: Keep the part in the drag direction
                # Find centroid of each part
                best_part = None
                best_dot = -float('inf')

                for part in parts:
                    centroid = part.centroid().asPoint()
                    # Vector from click point to centroid
                    to_centroid_x = centroid.x() - click_point.x()
                    to_centroid_y = centroid.y() - click_point.y()
                    # Dot product to check if centroid is in drag direction
                    dot = to_centroid_x * drag_dx + to_centroid_y * drag_dy

                    if dot > best_dot:
                        best_dot = dot
                        best_part = part

                if best_part:
                    return best_part, None
            else:
                # FALLBACK: Keep the part that does NOT contain the click point
                kept_part = None
                removed_part = None

                for part in parts:
                    if part.contains(QgsGeometry.fromPointXY(click_point)):
                        removed_part = part
                    else:
                        if kept_part is None:
                            kept_part = part
                        else:
                            kept_part = kept_part.combine(part)

                if kept_part and not kept_part.isEmpty():
                    return kept_part, removed_part

            return None, None

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Polygon trim error: {e}", "TrimExtendTool", Qgis.MessageLevel.Warning)
            return None, None

    # ---------- NEW: Main polygon modification dispatcher ----------
    def _modify_polygon(self, geom, click_point, drag_path=None, drag_dx=None, drag_dy=None):
        """Decide whether to trim, move vertex, or move side"""
        if not self.reference_geom:
            return None, None

        # Check if polygon intersects with reference (TRIM mode)
        if geom.intersects(self.reference_geom):
            kept, removed = self._trim_polygon(
                geom, click_point, drag_path, drag_dx, drag_dy)
            return kept, "trim"

        # EXTEND mode - detect vertex or side
        detection_type, idx, data = self._detect_vertex_or_side(
            geom, click_point)

        if detection_type == 'vertex':
            # Move vertex with angle preservation
            return self._move_vertex_with_angles(geom, idx, click_point)
        elif detection_type == 'side':
            # Move entire side
            return self._move_side(geom, idx, click_point)
        else:
            return None, None

    # ---------- Trim/Extend for Lines ----------
    def _modify_line(self, geom, click_point, drag_path=None, drag_dx=None, drag_dy=None):
        """Trim/extend line based on drag path or direction"""
        if not self.reference_geom:
            return None, None

        verts = [QgsPointXY(v.x(), v.y()) for v in geom.vertices()]
        if len(verts) < 2:
            return None, None

        # If we have a drag path, use it to determine which parts to trim
        if drag_path and len(drag_path) > 1:
            # Create a geometry from the drag path
            drag_geom = QgsGeometry.fromPolylineXY(drag_path)

            # Find intersections between line and reference
            inter = geom.intersection(self.reference_geom)
            pts = _extract_points(inter)

            if pts:
                # We have intersections, so we'll trim
                op = "trim"

                # Find the intersection points that are closest to the drag path
                best_start = None
                best_end = None
                best_start_dist = float('inf')
                best_end_dist = float('inf')

                for pt in pts:
                    # Check if this point is near the drag path
                    nearest = drag_geom.nearestPoint(
                        QgsGeometry.fromPointXY(pt)).asPoint()
                    dist = _dist(pt, nearest)

                    # Determine if this point is closer to start or end of line
                    dist_to_start = _dist(pt, verts[0])
                    dist_to_end = _dist(pt, verts[-1])

                    if dist_to_start < dist_to_end:
                        if dist < best_start_dist:
                            best_start_dist = dist
                            best_start = pt
                    else:
                        if dist < best_end_dist:
                            best_end_dist = dist
                            best_end = pt

                # Apply trim
                if best_start:
                    verts[0] = self._snap_to_reference(best_start)
                if best_end:
                    verts[-1] = self._snap_to_reference(best_end)

                return QgsGeometry.fromPolylineXY(verts), op
            else:
                # No intersections, so we'll extend
                op = "extend"

                # Determine which end to extend based on proximity to drag path
                nearest_to_start = drag_geom.nearestPoint(
                    QgsGeometry.fromPointXY(verts[0])).asPoint()
                nearest_to_end = drag_geom.nearestPoint(
                    QgsGeometry.fromPointXY(verts[-1])).asPoint()

                dist_to_start = _dist(verts[0], nearest_to_start)
                dist_to_end = _dist(verts[-1], nearest_to_end)

                # Extend the end closer to the drag path
                if dist_to_start < dist_to_end:
                    # Extend start
                    dx, dy = verts[0].x() - \
                        verts[1].x(), verts[0].y() - verts[1].y()
                    nx, ny = _normalize(dx, dy)
                    ray_len = max(self.canvas.extent().width(),
                                  self.canvas.extent().height()) * 2.0
                    ray_end = QgsPointXY(
                        verts[0].x() + nx * ray_len, verts[0].y() + ny * ray_len)
                    ray = QgsGeometry.fromPolylineXY([verts[0], ray_end])

                    ipts = _extract_points(
                        ray.intersection(self.reference_geom))
                    if ipts:
                        best_pt = min(ipts, key=lambda p: _dist(verts[0], p))
                        verts[0] = self._snap_to_reference(best_pt)
                else:
                    # Extend end
                    dx, dy = verts[-1].x() - \
                        verts[-2].x(), verts[-1].y() - verts[-2].y()
                    nx, ny = _normalize(dx, dy)
                    ray_len = max(self.canvas.extent().width(),
                                  self.canvas.extent().height()) * 2.0
                    ray_end = QgsPointXY(
                        verts[-1].x() + nx * ray_len, verts[-1].y() + ny * ray_len)
                    ray = QgsGeometry.fromPolylineXY([verts[-1], ray_end])

                    ipts = _extract_points(
                        ray.intersection(self.reference_geom))
                    if ipts:
                        best_pt = min(ipts, key=lambda p: _dist(verts[-1], p))
                        verts[-1] = self._snap_to_reference(best_pt)

                return QgsGeometry.fromPolylineXY(verts), op

        # Fallback to original behavior if no drag path
        start, end = verts[0], verts[-1]
        is_start = _dist(start, click_point) < _dist(end, click_point)
        end_idx = 0 if is_start else len(verts) - 1
        clicked = verts[end_idx]
        EPS = self.canvas.mapSettings().mapUnitsPerPixel() * 3

        # Try TRIM
        inter = geom.intersection(self.reference_geom)
        pts = _extract_points(inter)
        if pts:
            op = "trim"
            best_pt, best_d = None, float('inf')
            for p in pts:
                d = _dist(clicked, p)
                if d > EPS * 0.1 and d < best_d:
                    best_d, best_pt = d, p
            if not best_pt:
                return None, None
            verts[end_idx] = self._snap_to_reference(best_pt)
            return QgsGeometry.fromPolylineXY(verts), op

        # EXTEND
        op = "extend"
        if is_start:
            dx, dy = clicked.x() - verts[1].x(), clicked.y() - verts[1].y()
        else:
            dx, dy = clicked.x() - verts[-2].x(), clicked.y() - verts[-2].y()
        nx, ny = _normalize(dx, dy)
        ray_len = max(self.canvas.extent().width(),
                      self.canvas.extent().height()) * 2.0
        ray_end = QgsPointXY(clicked.x() + nx * ray_len,
                             clicked.y() + ny * ray_len)
        ray = QgsGeometry.fromPolylineXY([clicked, ray_end])

        ipts = _extract_points(ray.intersection(self.reference_geom))
        if not ipts:
            return None, None
        best_pt, best_d = None, float('inf')
        for p in ipts:
            d = _dist(clicked, p)
            if d > EPS * 0.1 and d < best_d:
                best_d, best_pt = d, p
        if not best_pt:
            return None, None
        verts[end_idx] = self._snap_to_reference(best_pt)
        return QgsGeometry.fromPolylineXY(verts), op

    # ---------- Hover Preview ----------
    def canvasMoveEvent(self, event):
        if self.waiting_for_reference or not self.reference_geom:
            return

        pt = self.toMapCoordinates(event.pos())

        # Detect if mouse has moved enough to be considered a drag
        if hasattr(self, 'press_point') and self.press_point and not self.is_dragging:
            # Check if mouse moved beyond threshold (5 pixels in map units)
            threshold = self.canvas.mapSettings().mapUnitsPerPixel() * 5
            if _dist(self.press_point, pt) > threshold:
                self.is_dragging = True
                print("Drag detected - multi-trim/extend mode active")

        # Handle dragging for multi-trim
        if self.is_dragging:
            # Add current point to drag path (with minimum distance to avoid too many points)
            if len(self.drag_path) == 0 or _dist(self.drag_path[-1], pt) > 5:
                self.drag_path.append(pt)

            # Update drag rubber band with the full path
            self.drag_rubber.reset(QgsWkbTypes.GeometryType.LineGeometry)
            if len(self.drag_path) > 1:
                self.drag_rubber.addGeometry(
                    QgsGeometry.fromPolylineXY(self.drag_path), None)

            # Update features along drag path
            self.drag_features = self._get_features_along_path(self.drag_path)

            # Get drag direction
            drag_dx, drag_dy = self._get_drag_direction(self.drag_path)

            # Set rubber band types based on layer geometry
            if self.is_polygon_layer:
                self.preview_rubber.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
                self.trim_rubber.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            else:
                self.preview_rubber.reset(QgsWkbTypes.GeometryType.LineGeometry)
                self.trim_rubber.reset(QgsWkbTypes.GeometryType.LineGeometry)

            # Preview modifications for all drag features
            for f in self.drag_features:
                g = f.geometry()
                if g and not g.isEmpty():
                    if g.type() == QgsWkbTypes.GeometryType.PolygonGeometry and self.is_polygon_layer:
                        new_g, op = self._modify_polygon(
                            g, pt, self.drag_path, drag_dx, drag_dy)
                        if new_g and not new_g.isEmpty():
                            if op == "trim":
                                self.preview_rubber.addGeometry(new_g, None)
                                try:
                                    removed = g.difference(new_g)
                                    if not removed.isEmpty():
                                        self.trim_rubber.addGeometry(
                                            removed, None)
                                except Exception:  # nosec B110
                                    pass
                            elif op in ("vertex_move", "side_move"):
                                self.trim_rubber.addGeometry(g, None)
                                try:
                                    extension = new_g.difference(g)
                                    if not extension.isEmpty():
                                        self.preview_rubber.addGeometry(
                                            extension, None)
                                except Exception:
                                    self.preview_rubber.addGeometry(
                                        new_g, None)
                    elif g.type() == QgsWkbTypes.GeometryType.LineGeometry and not self.is_polygon_layer:
                        new_g, op = self._modify_line(
                            g, pt, self.drag_path, drag_dx, drag_dy)
                        if new_g and not new_g.isEmpty():
                            self.preview_rubber.addGeometry(new_g, None)

            return

        f = self._get_closest_feature(pt, exclude_reference=True)

        self.preview_rubber.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        self.trim_rubber.reset(QgsWkbTypes.GeometryType.PolygonGeometry)

        if not f:
            return

        g = f.geometry()

        # Handle polygon preview
        if g.type() == QgsWkbTypes.GeometryType.PolygonGeometry and self.is_polygon_layer:
            new_g, op = self._modify_polygon(g, pt)
            if new_g and not new_g.isEmpty():
                if op == "trim":
                    self.preview_rubber.setToGeometry(new_g, None)
                    try:
                        removed = g.difference(new_g)
                        if not removed.isEmpty():
                            self.trim_rubber.setToGeometry(removed, None)
                    except Exception:  # nosec B110
                        pass
                elif op in ("vertex_move", "side_move"):
                    self.trim_rubber.setToGeometry(g, None)
                    try:
                        extension = new_g.difference(g)
                        if not extension.isEmpty():
                            self.preview_rubber.setToGeometry(extension, None)
                    except Exception:
                        self.preview_rubber.setToGeometry(new_g, None)
            return

        # Handle line preview
        if g.type() != QgsWkbTypes.GeometryType.LineGeometry:
            return

        new_g, op = self._modify_line(g, pt)
        if not new_g or new_g.isEmpty():
            return

        old_pts = [QgsPointXY(v.x(), v.y()) for v in g.vertices()]
        new_pts = [QgsPointXY(v.x(), v.y()) for v in new_g.vertices()]

        self.preview_rubber.reset(QgsWkbTypes.GeometryType.LineGeometry)
        self.trim_rubber.reset(QgsWkbTypes.GeometryType.LineGeometry)

        if op == "trim":
            if old_pts[0] != new_pts[0]:
                self.trim_rubber.addGeometry(
                    QgsGeometry.fromPolylineXY([old_pts[0], new_pts[0]]), None)
            else:
                self.trim_rubber.addGeometry(
                    QgsGeometry.fromPolylineXY([old_pts[-1], new_pts[-1]]), None)
            self.preview_rubber.addGeometry(new_g, None)
        elif op == "extend":
            if old_pts[0] != new_pts[0]:
                self.preview_rubber.addGeometry(
                    QgsGeometry.fromPolylineXY([new_pts[0], old_pts[0]]), None)
            else:
                self.preview_rubber.addGeometry(
                    QgsGeometry.fromPolylineXY([old_pts[-1], new_pts[-1]]), None)

    # ---------- Apply Edit ----------

    def canvasPressEvent(self, event):
        if event.button() == QtCompat.LeftButton and not self.waiting_for_reference and self.reference_geom:
            # Store press point to detect drag vs click
            self.press_point = self.toMapCoordinates(event.pos())
            self.is_dragging = False  # Will be set to True only if mouse moves
            self.drag_path = [self.press_point]
            self.drag_features = []

    def canvasReleaseEvent(self, event):
        if event.button() == QtCompat.RightButton:
            self._reset()
            self.iface.messageBar().pushMessage("Trim/Extend",
                                                "Reference cleared. Click to select a new reference.", level=Qgis.MessageLevel.Info)
            print("Reference cleared. Click to select a new reference.")
            return

        pt = self.toMapCoordinates(event.pos())
        tol_map = self.canvas.mapSettings().mapUnitsPerPixel() * self.pixel_tolerance

        # Pick reference first
        if self.waiting_for_reference:
            root = QgsProject.instance().layerTreeRoot()
            layers = [n.layer() for n in root.findLayers()
                      if n.layer() and n.isVisible()]
            best_layer, best_feat, best_d = None, None, float('inf')
            rect = QgsRectangle.fromCenterAndSize(pt, tol_map * 2, tol_map * 2)
            req = QgsFeatureRequest().setFilterRect(rect)

            for lyr in layers:
                if lyr.type() != QgsMapLayer.LayerType.VectorLayer:
                    continue
                if lyr.geometryType() not in (QgsWkbTypes.GeometryType.LineGeometry, QgsWkbTypes.GeometryType.PolygonGeometry):
                    continue
                for f in lyr.getFeatures(req):
                    gg = f.geometry()
                    if not gg or gg.isEmpty():
                        continue

                    # Check for containment (polygon)
                    pt_geom = QgsGeometry.fromPointXY(pt)
                    if lyr.geometryType() == QgsWkbTypes.GeometryType.PolygonGeometry and gg.contains(pt_geom):
                        # Priority match: click is inside the polygon
                        d = -1.0
                    else:
                        # Fallback match: distance to boundary
                        test = gg.convertToType(QgsWkbTypes.GeometryType.LineGeometry, True) if gg.type(
                        ) == QgsWkbTypes.GeometryType.PolygonGeometry else gg
                        np = test.nearestPoint(pt_geom).asPoint()
                        d = math.hypot(np.x() - pt.x(), np.y() - pt.y())

                    if d <= tol_map and d < best_d:
                        best_d, best_layer, best_feat = d, lyr, f

            if not best_feat:
                self.iface.messageBar().pushMessage(
                    "Trim/Extend", "No line/polygon edge found near click.", level=Qgis.MessageLevel.Warning)
                print("No line/polygon edge found near click.")
                return

            g_ref = best_feat.geometry()
            if g_ref.type() == QgsWkbTypes.GeometryType.PolygonGeometry:
                g_ref = g_ref.convertToType(QgsWkbTypes.GeometryType.LineGeometry, True)

            self.reference_geom = g_ref
            self.reference_layer = best_layer
            self.reference_fid = best_feat.id()
            self.waiting_for_reference = False

            self.reference_rubber.reset(QgsWkbTypes.GeometryType.LineGeometry)
            self.reference_rubber.addGeometry(g_ref, None)

            if self.is_polygon_layer:
                self.iface.messageBar().pushMessage("Trim/Extend",
                                                    f"Reference set (red) - Feature ID {best_feat.id()}. Click near vertex to move vertex, or near side to move side. Drag to multi-trim.", level=Qgis.MessageLevel.Info)
                print(
                    f"Reference set (red) - Feature ID {best_feat.id()}. Click near vertex to move vertex, or near side to move side. Drag to multi-trim.")
            else:
                self.iface.messageBar().pushMessage("Trim/Extend",
                                                    f"Reference set (red) - Feature ID {best_feat.id()}. Hover near line ends to preview, click to apply. Drag to multi-trim.", level=Qgis.MessageLevel.Info)
                print(
                    f"Reference set (red) - Feature ID {best_feat.id()}. Hover near line ends to preview, click to apply. Drag to multi-trim.")
            return

        # Check if this was a drag operation (mouse moved significantly)
        threshold = self.canvas.mapSettings().mapUnitsPerPixel() * 5
        is_drag = (hasattr(self, 'press_point') and self.press_point and
                   _dist(self.press_point, pt) > threshold and self.is_dragging)

        # Handle drag release for multi-trim
        if is_drag and len(self.drag_path) > 1:
            self.drag_rubber.reset(QgsWkbTypes.GeometryType.LineGeometry)

            # Add final point to path
            if len(self.drag_path) > 0 and (len(self.drag_path) == 1 or _dist(self.drag_path[-1], pt) > 5):
                self.drag_path.append(pt)

            if not self.drag_features:
                self.iface.messageBar().pushMessage(
                    "Trim/Extend", "No features found along drag path.", level=Qgis.MessageLevel.Warning)
                print("No features found along drag path.")
                self.drag_path = []
                self.is_dragging = False
                self.press_point = None
                return

            # Get drag direction
            drag_dx, drag_dy = self._get_drag_direction(self.drag_path)

            # Apply modifications to all drag features
            self.layer.beginEditCommand(
                f"Multi-Trim/Extend ({len(self.drag_features)} features)")

            success_count = 0
            for f in self.drag_features:
                g = f.geometry()

                # Handle polygon trim/extend/vertex/side operations
                if g.type() == QgsWkbTypes.GeometryType.PolygonGeometry and self.is_polygon_layer:
                    new_g, op = self._modify_polygon(
                        g, pt, self.drag_path, drag_dx, drag_dy)
                    if new_g and not new_g.isEmpty():
                        if self.layer.changeGeometry(f.id(), new_g):
                            success_count += 1

                # Handle line trim/extend
                elif g.type() == QgsWkbTypes.GeometryType.LineGeometry and not self.is_polygon_layer:
                    new_g, op = self._modify_line(
                        g, pt, self.drag_path, drag_dx, drag_dy)
                    if new_g and not new_g.isEmpty():
                        if self.layer.changeGeometry(f.id(), new_g):
                            success_count += 1

            if success_count > 0:
                self.layer.endEditCommand()
                self.iface.messageBar().pushMessage("Trim/Extend",
                                                    f"Multi-Trim/Extend applied to {success_count} features. Undo/Redo available.", level=Qgis.MessageLevel.Success)
                print(
                    f"Multi-Trim/Extend applied to {success_count} features. Undo/Redo available.")
            else:
                self.layer.destroyEditCommand()
                self.iface.messageBar().pushMessage(
                    "Trim/Extend", "Multi-Trim/Extend failed.", level=Qgis.MessageLevel.Warning)
                print("Multi-Trim/Extend failed.")

            self.canvas.refresh()
            self.drag_features = []
            self.drag_path = []
            self.is_dragging = False
            self.press_point = None
            return

        # Reset drag state for single click
        self.is_dragging = False
        self.drag_path = []
        self.drag_features = []
        self.press_point = None
        self.drag_rubber.reset(QgsWkbTypes.GeometryType.LineGeometry)

        # Apply single feature edit (regular click behavior)
        f = self._get_closest_feature(pt, exclude_reference=True)
        if not f:
            self.iface.messageBar().pushMessage("Trim/Extend",
                                                "No nearby feature found (excluding reference).", level=Qgis.MessageLevel.Warning)
            print("No nearby feature found (excluding reference).")
            return

        g = f.geometry()

        # Handle polygon trim/extend/vertex/side operations
        if g.type() == QgsWkbTypes.GeometryType.PolygonGeometry and self.is_polygon_layer:
            new_g, op = self._modify_polygon(g, pt)
            if not new_g or new_g.isEmpty():
                if g.intersects(self.reference_geom):
                    self.iface.messageBar().pushMessage(
                        "Trim/Extend", "No valid trim result.", level=Qgis.MessageLevel.Warning)
                    print("No valid trim result.")
                else:
                    detection_type, _, _ = self._detect_vertex_or_side(g, pt)
                    if detection_type == 'vertex':
                        self.iface.messageBar().pushMessage("Trim/Extend",
                                                            "No valid vertex move. Ensure the adjacent sides can reach the reference.", level=Qgis.MessageLevel.Warning)
                        print(
                            "No valid vertex move. Ensure the adjacent sides can reach the reference.")
                    elif detection_type == 'side':
                        self.iface.messageBar().pushMessage("Trim/Extend",
                                                            "No valid side move. Ensure the side endpoints can reach the reference.", level=Qgis.MessageLevel.Warning)
                        print(
                            "No valid side move. Ensure the side endpoints can reach the reference.")
                    else:
                        self.iface.messageBar().pushMessage(
                            "Trim/Extend", "Click closer to a vertex or side edge.", level=Qgis.MessageLevel.Warning)
                        print("Click closer to a vertex or side edge.")
                return

            op_name = {
                "trim": "Trim",
                "vertex_move": "Vertex Move",
                "side_move": "Side Move"
            }.get(op, op.capitalize())

            self.layer.beginEditCommand(f"Polygon {op_name}")
            ok = self.layer.changeGeometry(f.id(), new_g)
            if ok:
                self.layer.endEditCommand()
                self.iface.messageBar().pushMessage("Trim/Extend",
                                                    f"Polygon {op_name.upper()} applied to feature {f.id()}. Undo/Redo available.", level=Qgis.MessageLevel.Success)
                print(
                    f"Polygon {op_name.upper()} applied to feature {f.id()}. Undo/Redo available.")
            else:
                self.layer.destroyEditCommand()
                self.iface.messageBar().pushMessage(
                    "Trim/Extend", f"Polygon {op_name} failed.", level=Qgis.MessageLevel.Warning)
                print(f"Polygon {op_name} failed.")
            self.canvas.refresh()
            return

        # Handle line trim/extend
        if g.type() != QgsWkbTypes.GeometryType.LineGeometry:
            self.iface.messageBar().pushMessage("Trim/Extend",
                                                "Feature is not a line. Switch to line layer to edit lines.", level=Qgis.MessageLevel.Warning)
            print("Feature is not a line. Switch to line layer to edit lines.")
            return

        new_g, op = self._modify_line(g, pt)
        if not new_g or new_g.isEmpty():
            self.iface.messageBar().pushMessage(
                "Trim/Extend", "No valid intersection found.", level=Qgis.MessageLevel.Warning)
            print("No valid intersection found.")
            return

        self.layer.beginEditCommand(f"Trim/Extend ({op})")
        ok = self.layer.changeGeometry(f.id(), new_g)
        if ok:
            self.layer.endEditCommand()
            print(f"{op.upper()} applied to feature {f.id()}. Undo/Redo available.")
            self.iface.messageBar().pushMessage("Trim/Extend",
                                                f"{op.upper()} applied to feature {f.id()}. Undo/Redo available.", level=Qgis.MessageLevel.Success)
        else:
            self.layer.destroyEditCommand()
            self.iface.messageBar().pushMessage(
                "Trim/Extend", "Edit failed.", level=Qgis.MessageLevel.Critical)
            print("Edit failed.")
        self.canvas.refresh()


# === RUN TOOL ===
def activate_trim_extend_tool():
    """Activate the Trim/Extend tool on the canvas"""
    from qgis.utils import iface
    layer = iface.activeLayer()
    if not isinstance(layer, QgsVectorLayer):
        iface.messageBar().pushMessage(
            "Error", "Select a vector layer", level=Qgis.MessageLevel.Critical)
        return

    if layer.geometryType() not in (QgsWkbTypes.GeometryType.LineGeometry, QgsWkbTypes.GeometryType.PolygonGeometry):
        iface.messageBar().pushMessage(
            "Error", "Select an editable Line/Polygon layer.", level=Qgis.MessageLevel.Critical)
        return

    if not layer.isEditable():
        iface.messageBar().pushMessage(
            "Error", "Layer must be in edit mode.", level=Qgis.MessageLevel.Critical)
        return

    canvas = iface.mapCanvas()
    tool = TrimExtendTool(iface, canvas, layer, pixel_tolerance=15)
    canvas.setMapTool(tool)


# For testing when running script directly
if __name__ == "__main__":
    activate_trim_extend_tool()

import math
from qgis.PyQt.QtCore import QTimer, Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDoubleSpinBox, QComboBox, QTabWidget, QMessageBox,
    QFileDialog, QDialog, QDialogButtonBox
)
from qgis.PyQt.QtGui import QColor
from qgis.gui import QgsRubberBand, QgsVertexMarker, QgsMapTool
from qgis.core import (
    QgsWkbTypes, QgsPointXY, QgsGeometry, QgsVectorLayer, QgsDistanceArea,
    QgsField, QgsFeature, QgsProject, QgsMarkerSymbol,
    QgsRendererCategory, QgsCategorizedSymbolRenderer,
    QgsVectorFileWriter, QgsRectangle, QgsSnappingConfig,
    QgsTolerance, QgsPointLocator, QgsMapLayer, QgsFeatureRequest,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsUnitTypes
)
from qgis.utils import iface
from .addon_functions import TOOL_WINDOW_FLAGS

# ======================
# Qt5/Qt6 Compatibility
# ======================


class QtCompat:
    @staticmethod
    def _get_attr(obj, name, fallback_obj=None):
        try:
            return getattr(obj, name)
        except AttributeError:
            if fallback_obj is not None:
                return getattr(fallback_obj, name)
            raise

    @staticmethod
    def get_pen_style(style_name):
        return QtCompat._get_attr(Qt.PenStyle if hasattr(Qt, 'PenStyle') else Qt, style_name)

    @staticmethod
    def get_cursor_shape(shape_name):
        return QtCompat._get_attr(Qt.CursorShape if hasattr(Qt, 'CursorShape') else Qt, shape_name)

    @staticmethod
    def get_key(key_name):
        return QtCompat._get_attr(Qt.Key if hasattr(Qt, 'Key') else Qt, key_name)

    @staticmethod
    def get_mouse_button(button_name):
        return QtCompat._get_attr(Qt.MouseButton if hasattr(Qt, 'MouseButton') else Qt, button_name)

    @staticmethod
    def get_alignment(alignment_name):
        return QtCompat._get_attr(Qt.AlignmentFlag if hasattr(Qt, 'AlignmentFlag') else Qt, alignment_name)

    @staticmethod
    def get_standard_button(button_name):
        return QtCompat._get_attr(
            QDialogButtonBox.StandardButton if hasattr(
                QDialogButtonBox, 'StandardButton') else QDialogButtonBox,
            button_name
        )

    @staticmethod
    def get_message_box_button(button_name):
        return QtCompat._get_attr(
            QMessageBox.StandardButton if hasattr(
                QMessageBox, 'StandardButton') else QMessageBox,
            button_name
        )

    @staticmethod
    def exec_dialog(dialog):
        return dialog.exec() if hasattr(dialog, 'exec') else dialog.exec_()


# ======================
# Constants & Utilities
# ======================

UNIT_CONVERSIONS = {
    "Meters": {"factor": 1.0, "abbrev": "m"},
    "Metric Links": {"factor": 0.2, "abbrev": "ml"},
    "Gunter's Links": {"factor": 0.201168, "abbrev": "links"},
    "Feet": {"factor": 0.3048, "abbrev": "ft"},
    "Yards": {"factor": 0.9144, "abbrev": "yd"}
}

POINT_CATEGORIES = [
    {'name': 'Cut Point', 'color': 'orange', 'size': 2},
    {'name': "Offset Point", 'color': 'blue', 'size': 2},
    {'name': "Bisect Point", 'color': '#F736F6', 'size': 2},
    {'name': "Extended Point", 'color': 'purple', 'size': 2},
]


class UnitConverter:
    @staticmethod
    def to_meters(value, unit):
        return value * UNIT_CONVERSIONS.get(unit, {"factor": 1.0})["factor"]

    @staticmethod
    def from_meters(value, unit):
        return value / UNIT_CONVERSIONS.get(unit, {"factor": 1.0})["factor"]

    @staticmethod
    def get_abbreviation(unit):
        return UNIT_CONVERSIONS.get(unit, {"abbrev": "m"})["abbrev"]


class GeometryHelper:
    @staticmethod
    def get_line_endpoints(geometry):
        if not geometry:
            return None, None
        try:
            points = geometry.asMultiPolyline(
            )[0] if geometry.isMultipart() else geometry.asPolyline()
            return (QgsPointXY(points[0]), QgsPointXY(points[-1])) if points else (None, None)
        except Exception:
            return None, None

    @staticmethod
    def calculate_distance(p1, p2, crs):
        """Uses cartesian calculation for meter-based UTMs and ellipsoidal for degree-based systems"""
        # Check if the CRS is in meters
        if crs.mapUnits() == QgsUnitTypes.DistanceMeters:
            # Use cartesian calculation for meter-based systems
            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            return math.sqrt(dx * dx + dy * dy)
        else:
            # Use ellipsoidal calculation for degree-based systems
            da = QgsDistanceArea()
            da.setSourceCrs(crs, QgsProject.instance().transformContext())
            da.setEllipsoid(crs.ellipsoidAcronym())
            return da.measureLine(p1, p2)

    @staticmethod
    def calculate_triangle_apex(start, end, len1, len2, orientation, crs):
        """✅ ACCURATE TRIANGLE CALCULATION ON WGS84"""
        try:
            # ✅ STEP 1: Get ACCURATE base distance
            base = GeometryHelper.calculate_distance(start, end, crs)
            if base == 0:
                return None

            # ✅ STEP 2: Triangle inequality check
            if not (len1 + len2 > base and abs(len1 - len2) < base):
                return None

            # ✅ STEP 3: Transform to LOCAL UTM for calculations
            if crs.isGeographic():
                avg = QgsPointXY((start.x() + end.x()) / 2,
                                 (start.y() + end.y()) / 2)
                utm_crs = GeometryHelper.get_local_utm_crs(avg, crs)
                tr_fwd = QgsCoordinateTransform(
                    crs, utm_crs, QgsProject.instance())
                tr_back = QgsCoordinateTransform(
                    utm_crs, crs, QgsProject.instance())
                startu = tr_fwd.transform(start)
                endu = tr_fwd.transform(end)
            else:
                startu, endu = start, end
                tr_back = None

            # ✅ STEP 4: Calculate in FLAT UTM space
            dx, dy = endu.x() - startu.x(), endu.y() - startu.y()
            ux, uy = dx / base, dy / base
            perp = (-uy, ux) if orientation == "Right" else (uy, -ux)

            cos_a = (len1**2 + base**2 - len2**2) / (2 * len1 * base)
            if not -1 <= cos_a <= 1:
                return None
            angle = math.acos(cos_a)

            apex_x = startu.x() + len1 * (ux * math.cos(angle) -
                                          perp[0] * math.sin(angle))
            apex_y = startu.y() + len1 * (uy * math.cos(angle) -
                                          perp[1] * math.sin(angle))
            apex_u = QgsPointXY(apex_x, apex_y)

            # ✅ STEP 5: Transform back to ORIGINAL CRS
            if crs.isGeographic():
                # tr_back can be None in some static analysis or unexpected flows; guard against it.
                return tr_back.transform(apex_u) if tr_back is not None else apex_u
            else:
                return apex_u

        except (ValueError, ZeroDivisionError):
            return None

    @staticmethod
    def get_local_utm_crs(point, crs):
        """✅ Get precise UTM zone for point"""
        if not crs.isGeographic():
            return crs
        lon = point.x()
        lat = point.y()
        zone = math.floor((lon + 180) / 6) + 1
        epsg = 32600 + zone if lat >= 0 else 32700 + zone
        return QgsCoordinateReferenceSystem(f"EPSG:{epsg}")

    @staticmethod
    def interpolate_line(start, end, distance, crs):
        """✅ FIXED: Handles NEGATIVE distances correctly"""
        total_len = GeometryHelper.calculate_distance(start, end, crs)
        if total_len == 0:
            return start

        # ✅ FIXED: Allow negative distances for extension before start
        if distance < 0:
            # Extend BEYOND START (negative direction)
            extend_dist = abs(distance)
            if crs.mapUnits() == QgsUnitTypes.DistanceMeters:
                # Cartesian
                dx = end.x() - start.x()
                dy = end.y() - start.y()
                ratio = extend_dist / total_len
                return QgsPointXY(start.x() - dx * ratio, start.y() - dy * ratio)
            else:
                # Ellipsoidal - reverse bearing
                da = QgsDistanceArea()
                da.setSourceCrs(crs, QgsProject.instance().transformContext())
                da.setEllipsoid(crs.ellipsoidAcronym())
                bearing = da.bearing(start, end)
                reverse_bearing = bearing + math.pi  # 180° opposite
                return da.computeSpheroidProject(start, extend_dist, reverse_bearing)
        else:
            # Normal interpolation (0 to total_len) or beyond end
            # Cap at 2x for reasonable extension
            distance = min(distance, total_len * 2)
            if crs.mapUnits() == QgsUnitTypes.DistanceMeters:
                # Cartesian
                dx = end.x() - start.x()
                dy = end.y() - start.y()
                ratio = distance / total_len
                return QgsPointXY(start.x() + dx * ratio, start.y() + dy * ratio)
            else:
                # Ellipsoidal
                da = QgsDistanceArea()
                da.setSourceCrs(crs, QgsProject.instance().transformContext())
                da.setEllipsoid(crs.ellipsoidAcronym())
                bearing = da.bearing(start, end)
                return da.computeSpheroidProject(start, distance, bearing)

    @staticmethod
    def project_perpendicular(base, line_start, line_end, perp_distance, crs):
        """✅ ULTIMATE FIX: Uses ORIGINAL line_start→line_end bearing AT ANY base point"""
        if crs.mapUnits() == QgsUnitTypes.DistanceMeters:
            # ✅ UTM: Cartesian perpendicular using ORIGINAL direction
            dx = line_end.x() - line_start.x()
            dy = line_end.y() - line_start.y()
            length = math.hypot(dx, dy)
            if length == 0:
                return base
            # Perpendicular: (-dy, dx) = LEFT, (dy, -dx) = RIGHT
            sign = 1 if perp_distance >= 0 else -1
            px, py = (-dy * sign / length, dx * sign / length)
            return QgsPointXY(
                base.x() + px * abs(perp_distance),
                base.y() + py * abs(perp_distance)
            )
        else:
            # ✅ WGS84: Ellipsoidal using ORIGINAL bearing
            da = QgsDistanceArea()
            da.setSourceCrs(crs, QgsProject.instance().transformContext())
            da.setEllipsoid(crs.ellipsoidAcronym())
            # ORIGINAL line direction!
            bearing = da.bearing(line_start, line_end)

            # +90° LEFT, -90° RIGHT
            perp_bearing = bearing - (math.pi / 2) * \
                (1 if perp_distance >= 0 else -1)
            perp_bearing = (perp_bearing + math.pi) % (2 * math.pi) - math.pi
            return da.computeSpheroidProject(base, abs(perp_distance), perp_bearing)


class LayerManager:
    @staticmethod
    def get_project_crs():
        # ✅ PROJECT CRS AS FIRST PREFERENCE
        project_crs = QgsProject.instance().crs()
        if project_crs.isValid():
            return project_crs

        # Fallback: active layer
        layer = iface.activeLayer()
        if layer and hasattr(layer, 'crs') and layer.crs().isValid():
            return layer.crs()

        # Fallback: first spatial vector layer
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsVectorLayer) and lyr.isSpatial() and lyr.crs().isValid():
                return lyr.crs()

        # Final fallback: WGS84
        return QgsCoordinateReferenceSystem("EPSG:4326")

    @staticmethod
    def get_or_create_layer(name, geom_type, crs, fields):
        # ✅ CHECK EXISTING LAYER
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() == name and lyr.geometryType() == geom_type:
                return lyr

        # ✅ CREATE NEW LAYER WITH BUILT-IN SNAPPING
        if not crs or not crs.isValid():
            crs = LayerManager.get_project_crs()
        geom_str = "LineString" if geom_type == QgsWkbTypes.LineGeometry else "Point"
        layer = QgsVectorLayer(f"{geom_str}?crs={crs.toWkt()}", name, "memory")
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()
        QgsProject.instance().addMapLayer(layer)
        return layer

    @staticmethod
    def apply_categorized_symbology(layer, categories_info):
        categories = []
        for info in categories_info:
            symbol = QgsMarkerSymbol.createSimple({
                'name': 'circle',
                'color': info['color'],
                'size': str(info['size']),
                'outline_color': '0,0,0,255',
                'outline_width': '0.2'
            })
            categories.append(QgsRendererCategory(
                info['name'], symbol, info['name']))
        layer.setRenderer(QgsCategorizedSymbolRenderer('Type', categories))

    @staticmethod
    def update_layer_extent(layer):
        provider = layer.dataProvider()
        if provider:
            provider.updateExtents()
        layer.updateExtents()
        layer.reload()
        layer.triggerRepaint()

    @staticmethod
    def save_temp_layer(parent, layer):
        if layer.providerType() != "memory":
            return True
        if layer.isEditable():
            reply = QMessageBox.question(
                parent, 'Unsaved Changes',
                f"The layer '{layer.name()}' has unsaved changes. Save before exporting?",
                QtCompat.get_message_box_button('Yes') |
                QtCompat.get_message_box_button('No') |
                QtCompat.get_message_box_button('Cancel'),
                QtCompat.get_message_box_button('Yes')
            )
            if reply == QtCompat.get_message_box_button('Cancel'):
                return False
            elif reply == QtCompat.get_message_box_button('Yes'):
                if not layer.commitChanges():
                    QMessageBox.warning(
                        parent, "Commit Error", f"Failed: {layer.commitErrors()}")
                    return False
            else:
                layer.rollBack()

        path, _ = QFileDialog.getSaveFileName(
            parent, f"Save {layer.name()}", layer.name(),
            "ESRI Shapefile (*.shp);;GeoJSON (*.geojson);;GPKG (*.gpkg)"
        )
        if not path:
            return False

        fmt_map = {".shp": "ESRI Shapefile",
                   ".geojson": "GeoJSON", ".gpkg": "GPKG"}
        fmt = next((v for k, v in fmt_map.items() if path.endswith(k)), None)
        if not fmt:
            QMessageBox.critical(parent, "Error", "Unsupported format.")
            return False

        opts = QgsVectorFileWriter.SaveVectorOptions()
        opts.driverName = fmt
        opts.fileEncoding = "UTF-8"
        err = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer, path, QgsProject.instance().transformContext(), opts
        )
        if err[0] != QgsVectorFileWriter.NoError:
            QMessageBox.critical(parent, "Save Error", f"Error code: {err[0]}")
            return False

        QMessageBox.information(parent, "Success", f"Saved to {path}!")
        new_layer = QgsVectorLayer(path, layer.name(), "ogr")
        if new_layer.isValid():
            new_layer.setRenderer(layer.renderer().clone())
            QgsProject.instance().addMapLayer(new_layer)
            QgsProject.instance().removeMapLayer(layer.id())
            return True
        QMessageBox.warning(parent, "Warning", "Failed to reload saved layer.")
        return False


class MarkerFactory:
    @staticmethod
    def create_vertex_marker(canvas, point, color, fill_color=None, size=8):
        marker = QgsVertexMarker(canvas)
        marker.setCenter(point)
        marker.setColor(color)
        if fill_color:
            marker.setFillColor(fill_color)
        marker.setIconSize(size)
        marker.setIconType(QgsVertexMarker.ICON_CIRCLE)
        marker.setPenWidth(2)
        return marker

    @staticmethod
    def create_snap_marker(canvas):
        marker = QgsVertexMarker(canvas)
        marker.setIconType(QgsVertexMarker.ICON_CROSS)
        marker.setColor(QColor(255, 0, 255))
        marker.setPenWidth(3)
        marker.setIconSize(12)
        marker.hide()
        return marker


# ======================
# Managers & Tools
# ======================

class LineEndpointManager:
    def __init__(self):
        self.map_canvas = iface.mapCanvas()
        self.current_layer = None
        self.is_active = False
        self.start_point_marker = None
        self.end_point_marker = None
        self.manual_mode = False

    def activate(self):
        if self.is_active:
            return
        self.is_active = True
        if not self.manual_mode:
            iface.layerTreeView().currentLayerChanged.connect(self.on_layer_changed)
            lyr = iface.activeLayer()
            if lyr:
                self.on_layer_changed(lyr)

    def deactivate(self):
        if not self.is_active:
            return
        self.is_active = False
        self.manual_mode = False
        try:
            iface.layerTreeView().currentLayerChanged.disconnect(self.on_layer_changed)
        except (TypeError, AttributeError):
            pass
        if self.current_layer:
            try:
                self.current_layer.selectionChanged.disconnect(
                    self.update_display)
            except (TypeError, AttributeError):
                pass
        self.clear_display()
        self.current_layer = None

    def on_layer_changed(self, layer):
        if not self.is_active or self.manual_mode:
            return
        if not layer or layer.type() != QgsMapLayer.VectorLayer:
            self.clear_display()
            self.current_layer = None
            return
        if self.current_layer:
            try:
                self.current_layer.selectionChanged.disconnect(
                    self.update_display)
            except (TypeError, AttributeError):
                pass
        self.current_layer = layer
        self.clear_display()
        if layer.wkbType() in (QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString):
            layer.selectionChanged.connect(self.update_display)
            self.update_display()
        else:
            self.current_layer = None

    def update_display(self):
        if not self.is_active or self.manual_mode:
            return
        self.clear_display()
        if not self.current_layer or self.current_layer.wkbType() not in (QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString):
            return
        feats = list(self.current_layer.selectedFeatures())
        if len(feats) != 1:
            return
        geom = feats[0].geometry()
        if geom.isNull():
            return
        start, end = GeometryHelper.get_line_endpoints(geom)
        if start and end:
            self.start_point_marker = MarkerFactory.create_vertex_marker(
                self.map_canvas, start, QColor(0, 0, 0), QColor(0, 255, 0, 200), 11)
            self.start_point_marker.setPenWidth(1)
            self.start_point_marker.show()
            self.end_point_marker = MarkerFactory.create_vertex_marker(
                self.map_canvas, end, QColor(0, 0, 0), QColor(255, 0, 0, 200), 11)
            self.end_point_marker.setPenWidth(1)
            self.end_point_marker.show()
            self.map_canvas.refresh()

    def clear_display(self):
        for marker in [self.start_point_marker, self.end_point_marker]:
            if marker:
                try:
                    marker.hide()
                    self.map_canvas.scene().removeItem(marker)
                except Exception:
                    pass
        self.start_point_marker = self.end_point_marker = None

    def display_segment_endpoints(self, start, end):
        self.manual_mode = True
        try:
            iface.layerTreeView().currentLayerChanged.disconnect(self.on_layer_changed)
        except (TypeError, AttributeError):
            pass
        if self.current_layer:
            try:
                self.current_layer.selectionChanged.disconnect(
                    self.update_display)
            except (TypeError, AttributeError):
                pass
        self.clear_display()
        if start and end:
            self.start_point_marker = MarkerFactory.create_vertex_marker(
                self.map_canvas, start, QColor(0, 0, 0), QColor(0, 255, 0, 200), 11)
            self.start_point_marker.setPenWidth(1)
            self.start_point_marker.show()
            self.end_point_marker = MarkerFactory.create_vertex_marker(
                self.map_canvas, end, QColor(0, 0, 0), QColor(255, 0, 0, 200), 11)
            self.end_point_marker.setPenWidth(1)
            self.end_point_marker.show()
            self.map_canvas.scene().update()

    def cleanup(self):
        self.deactivate()
        self.map_canvas.refresh()


# ======================
# Map Tools
# ======================

class TrianglePointTool(QgsMapTool):
    def __init__(self, canvas, widget):
        super().__init__(canvas)
        self.canvas = canvas
        self.widget = widget
        self.first_point = None
        self.markers = []
        self.use_fixed_length = False
        self.is_selecting = False
        self.base_line = QgsRubberBand(canvas, QgsWkbTypes.LineGeometry)
        self.base_line.setColor(QColor(0, 0, 255, 150))
        self.base_line.setWidth(2)
        self.temp_line = QgsRubberBand(canvas, QgsWkbTypes.LineGeometry)
        self.temp_line.setColor(QColor(0, 0, 255, 100))
        self.temp_line.setWidth(1)
        self.temp_line.setLineStyle(QtCompat.get_pen_style('DashLine'))
        self.setCursor(QtCompat.get_cursor_shape('CrossCursor'))
        self.snapping_utils = canvas.snappingUtils()
        self.snap_marker = MarkerFactory.create_snap_marker(canvas)

    def activate(self):
        super().activate()
        self.is_selecting = True
        self.canvas.setCursor(QtCompat.get_cursor_shape('CrossCursor'))
        self.snapping_utils = self.canvas.snappingUtils()

    def deactivate(self):
        had_first = self.first_point is not None
        self.snap_marker.hide()
        self.temp_line.reset()
        if not had_first or self.is_selecting:
            self.is_selecting = False
            for m in self.markers:
                self.canvas.scene().removeItem(m)
            self.markers = []
            self.base_line.reset()
            self.first_point = None
            self.use_fixed_length = False
            w = self.widget
            w.select_points_button.setEnabled(True)
            w.select_points_button.setText("Select Points")
            w.status_label.setText("Click 'Select Points' to start")
        super().deactivate()

    def keyPressEvent(self, event):
        key = event.key()
        enter_keys = [QtCompat.get_key(
            'Key_Enter'), QtCompat.get_key('Key_Return')]
        if key in enter_keys and self.widget.draw_button.isEnabled():
            self.widget.draw_triangle()
        elif key == QtCompat.get_key('Key_L') and self.first_point is not None:
            self.show_length_dialog()
        else:
            super().keyPressEvent(event)

    def show_length_dialog(self):
        dialog = QDialog(self.widget)
        dialog.setWindowTitle("Set Fixed Base Length")
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Enter base length:"))
        length_input = QDoubleSpinBox()
        length_input.setDecimals(3)
        length_input.setRange(0, 1e6)
        length_input.setValue(self.widget.fixed_base_length)
        unit_combo = QComboBox()
        unit_combo.addItems(list(UNIT_CONVERSIONS.keys()))
        unit_combo.setCurrentText(self.widget.unit_combo.currentText())
        layout.addWidget(length_input)
        layout.addWidget(unit_combo)
        btn_box = QDialogButtonBox(QtCompat.get_standard_button(
            'Ok') | QtCompat.get_standard_button('Cancel'))
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)
        dialog.setLayout(layout)
        length_input.setFocus()
        length_input.selectAll()
        if QtCompat.exec_dialog(dialog):
            self.widget.fixed_base_length = length_input.value()
            self.widget.unit_combo.setCurrentText(unit_combo.currentText())
            self.use_fixed_length = True
            self.widget.status_label.setText(
                "Fixed length set. Click second point (Right-click to reset)")
            self.widget.start_length_input.setFocus()
            self.widget.start_length_input.selectAll()

    def canvasMoveEvent(self, event):
        if not self.is_selecting:
            return
        current_point = None
        if self.snapping_utils:
            match = self.snapping_utils.snapToMap(event.pos())
            if match.isValid():
                current_point = match.point()
                self.snap_marker.setCenter(current_point)
                self.snap_marker.show()
            else:
                current_point = self.toMapCoordinates(event.pos())
                self.snap_marker.hide()
        else:
            current_point = self.toMapCoordinates(event.pos())
            self.snap_marker.hide()

        if self.first_point and current_point:
            self.temp_line.reset()
            self.temp_line.addPoint(self.first_point, False)
            crs = self.canvas.mapSettings().destinationCrs()
            if self.use_fixed_length:
                dist = GeometryHelper.calculate_distance(
                    self.first_point, current_point, crs)
                if dist > 0:
                    base_len = UnitConverter.to_meters(
                        self.widget.fixed_base_length, self.widget.unit_combo.currentText()
                    )
                    if crs.isGeographic():
                        avg = QgsPointXY((self.first_point.x(
                        ) + current_point.x()) / 2, (self.first_point.y() + current_point.y()) / 2)
                        utm_crs = GeometryHelper.get_local_utm_crs(avg, crs)
                        tr = QgsCoordinateTransform(
                            crs, utm_crs, QgsProject.instance())
                        first_u = tr.transform(self.first_point)
                        current_u = tr.transform(current_point)
                        dx = current_u.x() - first_u.x()
                        dy = current_u.y() - first_u.y()
                        ux, uy = dx / dist, dy / dist
                        preview_u = QgsPointXY(
                            first_u.x() + ux * base_len, first_u.y() + uy * base_len)
                        tr_back = QgsCoordinateTransform(
                            utm_crs, crs, QgsProject.instance())
                        preview = tr_back.transform(preview_u)  # ✅ FIXED
                    else:
                        dx = current_point.x() - self.first_point.x()
                        dy = current_point.y() - self.first_point.y()
                        ux, uy = dx / dist, dy / dist
                        preview = QgsPointXY(self.first_point.x(
                        ) + ux * base_len, self.first_point.y() + uy * base_len)
                    self.temp_line.addPoint(preview, True)
            else:
                self.temp_line.addPoint(current_point, True)

    def canvasPressEvent(self, event):
        if not self.is_selecting:
            return
        if event.button() == QtCompat.get_mouse_button('RightButton'):
            if self.first_point:
                self.clear()
                self.is_selecting = True
                self.widget.status_label.setText("Click first point on canvas")
            return

        point = None
        if self.snapping_utils:
            match = self.snapping_utils.snapToMap(event.pos())
            point = match.point() if match.isValid() else self.toMapCoordinates(event.pos())
        else:
            point = self.toMapCoordinates(event.pos())

        if point is None:
            return

        if self.first_point is None:
            self.first_point = point
            marker = MarkerFactory.create_vertex_marker(
                self.canvas, point, QColor(0, 255, 0), QColor(0, 255, 0, 200))
            self.markers.append(marker)
            self.widget.status_label.setText(
                "Press 'L' for fixed length or click second point (Right-click to reset)")
        else:
            unit = self.widget.unit_combo.currentText()
            crs = self.canvas.mapSettings().destinationCrs()
            if self.use_fixed_length:
                base_len = UnitConverter.to_meters(
                    self.widget.fixed_base_length, unit)
                if base_len <= 0:
                    QMessageBox.warning(
                        self.widget, "Invalid Length", "Base length must be > 0.")
                    return
                dist = GeometryHelper.calculate_distance(
                    self.first_point, point, crs)
                if dist == 0:
                    QMessageBox.warning(
                        self.widget, "Invalid Direction", "Points must differ.")
                    return
                if crs.isGeographic():
                    avg = QgsPointXY(
                        (self.first_point.x() + point.x()) / 2, (self.first_point.y() + point.y()) / 2)
                    utm_crs = GeometryHelper.get_local_utm_crs(avg, crs)
                    tr = QgsCoordinateTransform(
                        crs, utm_crs, QgsProject.instance())
                    first_u = tr.transform(self.first_point)
                    point_u = tr.transform(point)
                    dx = point_u.x() - first_u.x()
                    dy = point_u.y() - first_u.y()
                    ux, uy = dx / dist, dy / dist
                    second_u = QgsPointXY(
                        first_u.x() + ux * base_len, first_u.y() + uy * base_len)
                    tr_back = QgsCoordinateTransform(
                        utm_crs, crs, QgsProject.instance())
                    second = tr_back.transform(second_u)  # ✅ FIXED
                else:
                    dx = point.x() - self.first_point.x()
                    dy = point.y() - self.first_point.y()
                    ux = dx / dist
                    uy = dy / dist
                    second = QgsPointXY(self.first_point.x(
                    ) + ux * base_len, self.first_point.y() + uy * base_len)
            else:
                dist = GeometryHelper.calculate_distance(
                    self.first_point, point, crs)
                if dist == 0:
                    QMessageBox.warning(
                        self.widget, "Invalid Point", "Points must differ.")
                    return
                second = point
                self.widget.fixed_base_length = UnitConverter.from_meters(
                    dist, unit)

            marker = MarkerFactory.create_vertex_marker(
                self.canvas, second, QColor(255, 0, 0), QColor(255, 0, 0, 200))
            self.markers.append(marker)
            self.base_line.reset()
            self.base_line.addPoint(self.first_point, False)
            self.base_line.addPoint(second, True)
            self.temp_line.reset()
            actual_len = GeometryHelper.calculate_distance(
                self.first_point, second, crs)
            display_len = UnitConverter.from_meters(actual_len, unit)
            abbrev = UnitConverter.get_abbreviation(unit)
            self.use_fixed_length = False
            self.is_selecting = False
            self.widget.set_points(self.first_point, second)
            self.widget.status_label.setText(
                f"Base line set ({display_len:.3f} {abbrev}). Ready to draw triangle.")
            self.widget.select_points_button.setEnabled(True)
            self.widget.select_points_button.setText("Select Points")
            self.snap_marker.hide()
            iface.mapCanvas().unsetMapTool(self)
            self.widget.start_length_input.setFocus()
            self.widget.start_length_input.selectAll()

    def clear(self):
        self.first_point = None
        self.use_fixed_length = False
        self.is_selecting = False
        for m in self.markers:
            self.canvas.scene().removeItem(m)
        self.markers = []
        self.base_line.reset()
        self.temp_line.reset()
        self.snap_marker.hide()
        self.canvas.refresh()


class SegmentSelectTool(QgsMapTool):
    def __init__(self, canvas, widget):
        super().__init__(canvas)
        self.canvas = canvas
        self.widget = widget
        self.snapping_utils = None
        self.snap_marker = None
        self.is_selecting = False
        self.is_active = False
        self.search_radius = 10  # pixels for searching nearby features when snapping is off

    def activate(self):
        super().activate()
        self.is_active = True
        self.is_selecting = True
        self.snapping_utils = self.canvas.snappingUtils()
        if self.snap_marker:
            try:
                self.canvas.scene().removeItem(self.snap_marker)
            except:
                pass
        self.snap_marker = MarkerFactory.create_snap_marker(self.canvas)
        self.canvas.setCursor(QtCompat.get_cursor_shape('CrossCursor'))
        w = self.widget
        w.status_label.setText("Click on a line segment to add endpoints.")
        w.select_segment_button.setEnabled(False)
        w.select_segment_button.setText("Selecting...")
        w.clear_segment_button.setEnabled(True)
        self.canvas.refresh()

    def deactivate(self):
        self.is_active = False
        self.is_selecting = False
        if self.snap_marker:
            self.snap_marker.hide()
        self.canvas.unsetCursor()
        w = self.widget
        w.select_segment_button.setEnabled(True)
        w.select_segment_button.setText("Select Segment")
        self.canvas.refresh()
        super().deactivate()

    def cleanup(self):
        self.is_active = False
        self.is_selecting = False
        if self.snap_marker:
            try:
                self.canvas.scene().removeItem(self.snap_marker)
            except:
                pass
            self.snap_marker = None
        self.snapping_utils = None
        self.canvas.unsetCursor()
        self.canvas.refresh()

    def canvasMoveEvent(self, event):
        if not (self.is_active and self.is_selecting):
            return
        if self.snapping_utils:
            match = self.snapping_utils.snapToMap(event.pos())
            if match.isValid() and match.type() == QgsPointLocator.Edge:
                self.snap_marker.setCenter(match.point())
                self.snap_marker.show()
            else:
                self.snap_marker.hide()
        else:
            self.snap_marker.hide()

    def canvasPressEvent(self, event):
        if not (self.is_active and self.is_selecting):
            return
        if event.button() == QtCompat.get_mouse_button('RightButton'):
            w = self.widget
            if w.current_segment:
                w.current_layer = w.current_segment = None
                w.plot_button.setEnabled(False)
                w.endpoint_manager.clear_display()
                w.status_label.setText(
                    "Last endpoint cleared. Click on a line segment to add more.")
            self.is_selecting = True
            self.canvas.setCursor(QtCompat.get_cursor_shape('CrossCursor'))
            w.select_segment_button.setEnabled(False)
            w.select_segment_button.setText("Selecting...")
            w.clear_segment_button.setEnabled(True)
            if self.snap_marker:
                self.snap_marker.hide()
            self.canvas.refresh()
            return

        if event.button() != QtCompat.get_mouse_button('LeftButton'):
            return

        # Try snapping first if enabled
        snapped_feat = None
        if self.snapping_utils:
            match = self.snapping_utils.snapToMap(event.pos())
            if match.isValid() and match.type() == QgsPointLocator.Edge:
                snapped_feat = self._get_feature_from_snap(match)

        # If snapping didn't work or is disabled, try searching nearby
        if not snapped_feat:
            map_point = self.toMapCoordinates(event.pos())
            tolerance = self.search_radius * self.canvas.mapUnitsPerPixel()
            rect = QgsRectangle(
                map_point.x() - tolerance,
                map_point.y() - tolerance,
                map_point.x() + tolerance,
                map_point.y() + tolerance
            )
            for layer in self.canvas.layers():
                if not isinstance(layer, QgsVectorLayer) or layer.geometryType() != QgsWkbTypes.LineGeometry:
                    continue

                request = QgsFeatureRequest()
                request.setFilterRect(rect)
                request.setNoAttributes()

                closest_dist = float('inf')
                closest_feature = None
                closest_point = None

                for feature in layer.getFeatures(request):
                    geom = feature.geometry()
                    if not geom:
                        continue

                    point_on_line = geom.nearestPoint(
                        QgsGeometry.fromPointXY(map_point))
                    if not point_on_line:
                        continue

                    dist = point_on_line.distance(
                        QgsGeometry.fromPointXY(map_point))
                    if dist < closest_dist and dist <= tolerance:
                        closest_dist = dist
                        closest_feature = feature
                        closest_point = point_on_line.asPoint()

                if closest_feature:
                    snapped_feat = (layer, closest_feature, closest_point)
                    break

        if snapped_feat:
            layer, feature, pt = snapped_feat
            start, end = self._find_closest_segment(feature.geometry(), pt)
            if start and end:
                self.widget.set_selected_segment(layer, start, end)
                if self.snap_marker:
                    self.snap_marker.hide()
                self.widget.status_label.setText(
                    "Endpoint added. Click another segment to add more (Right-click to clear last, Escape to finish)."
                )
                self.canvas.refresh()
                self.is_selecting = True
                self.canvas.setCursor(QtCompat.get_cursor_shape('CrossCursor'))
                return

        self.widget.status_label.setText(
            "No valid line segment found nearby. Try clicking closer to a line."
        )
        if self.snap_marker:
            self.snap_marker.hide()
        self.canvas.refresh()

    def keyPressEvent(self, event):
        if not self.is_active:
            return
        if event.key() == QtCompat.get_key('Key_Escape'):
            self.deactivate()
            if iface.mapCanvas().mapTool() == self:
                iface.mapCanvas().unsetMapTool(self)
            return
        super().keyPressEvent(event)

    def _get_feature_from_snap(self, match):
        layer = match.layer()
        if not layer or not isinstance(layer, QgsVectorLayer) or layer.geometryType() != QgsWkbTypes.LineGeometry:
            return None
        feature = layer.getFeature(match.featureId())
        return (layer, feature, match.point()) if feature.isValid() else None

    def _find_closest_segment(self, geom, snapped_xy):
        vertices = geom.asPolyline() if not geom.isMultipart() else None
        if vertices is None:
            multi = geom.constGet()
            min_dist = float('inf')
            best_start = best_end = None
            for i in range(multi.numGeometries()):
                part = QgsGeometry(multi.geometryN(i).clone())
                part_vertices = part.asPolyline()
                _, _, next_v, _ = part.closestSegmentWithContext(
                    snapped_xy, 1e-8)
                if next_v > 0 and next_v <= len(part_vertices):
                    seg_start = part_vertices[next_v - 1]
                    seg_end = part_vertices[next_v] if next_v < len(
                        part_vertices) else None
                    if seg_end:
                        dist_sq = (seg_start.x() - snapped_xy.x())**2 + \
                            (seg_start.y() - snapped_xy.y())**2
                        if dist_sq < min_dist:
                            min_dist = dist_sq
                            best_start, best_end = seg_start, seg_end
            return best_start, best_end
        else:
            _, _, next_v, _ = geom.closestSegmentWithContext(snapped_xy, 1e-8)
            if 0 < next_v < len(vertices):
                return vertices[next_v - 1], vertices[next_v]
        return None, None


# ======================
# Widgets
# ======================

class TriangleWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220)
        self.start_point = None
        self.end_point = None
        self.fixed_base_length = 10.0
        self.lines_drawn = False
        self.point_tool = TrianglePointTool(iface.mapCanvas(), self)
        self.triangle_rubber_band = QgsRubberBand(
            iface.mapCanvas(), QgsWkbTypes.LineGeometry)
        self.triangle_rubber_band.setColor(QColor(255, 0, 0, 150))
        self.triangle_rubber_band.setWidth(3)
        self.preview_timer = QTimer()
        self.preview_timer.timeout.connect(self.update_triangle_preview)
        self.preview_timer.setSingleShot(True)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.status_label = QLabel("Click 'Select Points' to start")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "QLabel { color: #F736F6; font-weight: bold; padding: 5px; }")
        self.status_label.setMinimumHeight(40)
        self.status_label.setAlignment(QtCompat.get_alignment('AlignTop'))
        layout.addWidget(self.status_label)

        btn_layout = QHBoxLayout()
        self.select_points_button = QPushButton("Select Points")
        self.select_points_button.clicked.connect(self.start_point_selection)
        btn_layout.addWidget(self.select_points_button)
        self.clear_points_button = QPushButton("Clear Points")
        self.clear_points_button.clicked.connect(self.clear_points)
        self.clear_points_button.setEnabled(False)
        btn_layout.addWidget(self.clear_points_button)
        layout.addLayout(btn_layout)

        layout.addWidget(QLabel("Units:"))
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(list(UNIT_CONVERSIONS.keys()))
        self.unit_combo.currentTextChanged.connect(
            self.schedule_preview_update)
        layout.addWidget(self.unit_combo)

        layout.addWidget(QLabel("🟢 Start Side Length:"))
        self.start_length_input = QDoubleSpinBox()
        self.start_length_input.setDecimals(3)
        self.start_length_input.setRange(0, 1e6)

        self.start_length_input.valueChanged.connect(
            self.schedule_preview_update)
        layout.addWidget(self.start_length_input)

        layout.addWidget(QLabel("🔴 End Side Length:"))
        self.end_length_input = QDoubleSpinBox()
        self.end_length_input.setDecimals(3)
        self.end_length_input.setRange(0, 1e6)
        self.end_length_input.valueChanged.connect(
            self.schedule_preview_update)
        layout.addWidget(self.end_length_input)

        layout.addWidget(QLabel("Orientation:"))
        self.orientation_combo = QComboBox()
        self.orientation_combo.addItems(["Left", "Right"])
        self.orientation_combo.currentTextChanged.connect(
            self.schedule_preview_update)
        layout.addWidget(self.orientation_combo)

        self.draw_button = QPushButton("Draw Triangle")
        self.draw_button.clicked.connect(self.draw_triangle)
        self.draw_button.setEnabled(False)
        layout.addWidget(self.draw_button)

        layout.setAlignment(QtCompat.get_alignment('AlignTop'))
        self.setLayout(layout)
        self.clearFocus()

    def start_point_selection(self):
        self.clear_points()
        self.status_label.setText("Click first point on canvas")
        iface.mapCanvas().setMapTool(self.point_tool)
        self.select_points_button.setEnabled(False)
        self.select_points_button.setText("Selecting...")
        self.activateWindow()
        self.raise_()

    def set_points(self, start, end):
        self.start_point, self.end_point = start, end
        self.draw_button.setEnabled(True)
        self.clear_points_button.setEnabled(True)
        self.select_points_button.setEnabled(True)
        self.select_points_button.setText("Select Points")
        self.schedule_preview_update()
        self.activateWindow()
        self.raise_()

    def clear_points(self):
        self.start_point = self.end_point = None
        self.point_tool.clear()
        self.triangle_rubber_band.reset()
        self.draw_button.setEnabled(False)
        self.clear_points_button.setEnabled(False)
        self.select_points_button.setEnabled(True)
        self.select_points_button.setText("Select Points")
        self.status_label.setText("Click 'Select Points' to start")
        if iface.mapCanvas().mapTool() == self.point_tool:
            iface.mapCanvas().unsetMapTool(self.point_tool)
        iface.mapCanvas().refresh()

    def deactivate(self):
        if hasattr(self, 'point_tool') and not self.point_tool.is_selecting:
            self.select_points_button.setEnabled(True)
            self.select_points_button.setText("Select Points")
        if iface.mapCanvas().mapTool() == self.point_tool and not (self.start_point or self.end_point):
            iface.mapCanvas().unsetMapTool(self.point_tool)

    def schedule_preview_update(self):
        if self.start_point is None or self.end_point is None:
            return
        self.preview_timer.stop()
        self.preview_timer.start(200)

    def update_triangle_preview(self):
        self.triangle_rubber_band.reset()
        if self.start_point is None or self.end_point is None:
            return
        len1 = UnitConverter.to_meters(
            self.start_length_input.value(), self.unit_combo.currentText())
        len2 = UnitConverter.to_meters(
            self.end_length_input.value(), self.unit_combo.currentText())
        if len1 <= 0 or len2 <= 0:
            return
        crs = LayerManager.get_project_crs()
        apex = GeometryHelper.calculate_triangle_apex(
            self.start_point, self.end_point, len1, len2, self.orientation_combo.currentText(), crs
        )
        if apex:
            rb = self.triangle_rubber_band
            rb.addPoint(self.start_point, False)
            rb.addPoint(apex, False)
            rb.addPoint(self.end_point, False)
            rb.addPoint(self.start_point, True)

    def draw_triangle(self):
        if self.start_point is None or self.end_point is None:
            QMessageBox.critical(
                self, "Error", "Please select two points first.")
            return

        crs = LayerManager.get_project_crs()
        len1 = UnitConverter.to_meters(
            self.start_length_input.value(), self.unit_combo.currentText())
        len2 = UnitConverter.to_meters(
            self.end_length_input.value(), self.unit_combo.currentText())
        apex = GeometryHelper.calculate_triangle_apex(
            self.start_point, self.end_point, len1, len2, self.orientation_combo.currentText(), crs
        )
        if not apex:
            QMessageBox.critical(
                self, "Error", "Invalid side lengths. Triangle cannot be formed.")
            return

        # ✅ NO CANVAS EXTENT MANIPULATION — VIEW REMAINS UNCHANGED
        layer = LayerManager.get_or_create_layer(
            "Triangle Lines", QgsWkbTypes.LineGeometry, crs, [
                QgsField("Type", QVariant.String)]
        )
        if not layer.isEditable():
            layer.startEditing()

        def add_line(start, end, line_type):
            feat = QgsFeature(layer.fields())
            geom = QgsGeometry.fromPolylineXY([start, end])
            if geom.isNull() or not geom.isGeosValid():
                return False
            feat.setGeometry(geom)
            feat.setAttributes([line_type])
            return layer.addFeature(feat)

        add_line(self.start_point, apex, "Start Side")
        add_line(self.end_point, apex, "End Side")
        add_line(self.start_point, self.end_point, "Base Line")

        LayerManager.update_layer_extent(layer)
        self.triangle_rubber_band.reset()
        self.lines_drawn = True
        self.start_length_input.setValue(0.0)
        self.end_length_input.setValue(0.0)
        # self.unit_combo.setCurrentText("Meters")
        # self.orientation_combo.setCurrentText("Left")
        self.clear_points()
        self.status_label.setText("Triangle added to 'Triangle Lines' layer.")
        self.start_length_input.setFocus()
        self.start_length_input.selectAll()
        layer.triggerRepaint()

    def keyPressEvent(self, event):
        if event.key() in [QtCompat.get_key('Key_Enter'), QtCompat.get_key('Key_Return')] and self.draw_button.isEnabled():
            self.draw_triangle()
        else:
            super().keyPressEvent(event)

    def cleanup(self):
        if iface.mapCanvas().mapTool() == self.point_tool:
            iface.mapCanvas().unsetMapTool(self.point_tool)
        self.point_tool.clear()
        self.triangle_rubber_band.reset()
        self.preview_timer.stop()


class PlotterWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220)
        self.endpoint_manager = LineEndpointManager()
        self.segment_tool = SegmentSelectTool(iface.mapCanvas(), self)
        self.current_layer = None
        self.current_segment = None
        self.points_drawn = False
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.status_label = QLabel("Click 'Select Segment' to start.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "QLabel { color: #F736F6; font-weight: bold; padding: 5px; }")
        layout.addWidget(self.status_label)

        btn_layout = QHBoxLayout()
        self.select_segment_button = QPushButton("Select Segment")
        self.select_segment_button.clicked.connect(
            self.start_segment_selection)
        btn_layout.addWidget(self.select_segment_button)
        self.clear_segment_button = QPushButton("Clear Segment")
        self.clear_segment_button.clicked.connect(self.clear_segment)
        self.clear_segment_button.setEnabled(False)
        btn_layout.addWidget(self.clear_segment_button)
        layout.addLayout(btn_layout)

        layout.addWidget(QLabel("Units:"))
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(list(UNIT_CONVERSIONS.keys()))
        layout.addWidget(self.unit_combo)

        layout.addWidget(QLabel("Choose Point:"))
        self.point_combo = QComboBox()
        self.point_combo.addItems(["🟢 Start Point", "🔴 End Point"])
        layout.addWidget(self.point_combo)

        layout.addWidget(QLabel("Cut Point Length:"))
        self.cut_point_input = QDoubleSpinBox()
        self.cut_point_input.setDecimals(3)
        self.cut_point_input.setRange(-1e6, 1e6)
        layout.addWidget(self.cut_point_input)

        layout.addWidget(QLabel("Offset Length:"))
        self.offset_input = QDoubleSpinBox()
        self.offset_input.setDecimals(3)
        self.offset_input.setRange(-1e6, 1e6)
        layout.addWidget(self.offset_input)

        self.plot_button = QPushButton("Plot")
        self.plot_button.clicked.connect(self.plot)
        self.plot_button.setEnabled(False)
        layout.addWidget(self.plot_button)

        layout.setAlignment(QtCompat.get_alignment('AlignTop'))
        self.setLayout(layout)
        self.clearFocus()

    def start_segment_selection(self):
        self.status_label.setText("Click on a line segment on the canvas.")
        self.segment_tool.activate()
        iface.mapCanvas().setMapTool(self.segment_tool)
        self.select_segment_button.setEnabled(False)
        self.select_segment_button.setText("Selecting...")
        self.clear_segment_button.setEnabled(True)
        self.activateWindow()
        self.raise_()

    def set_selected_segment(self, layer, start, end):
        self.current_layer = layer
        self.current_segment = [start, end]
        crs = LayerManager.get_project_crs()
        length = GeometryHelper.calculate_distance(start, end, crs)
        unit = self.unit_combo.currentText()
        display_len = UnitConverter.from_meters(length, unit)
        abbrev = UnitConverter.get_abbreviation(unit)
        self.endpoint_manager.display_segment_endpoints(start, end)
        self.status_label.setText(
            f"Segment selected. Length: {display_len:.3f} {abbrev}")
        self.clear_segment_button.setEnabled(True)
        self.plot_button.setEnabled(True)
        self.select_segment_button.setEnabled(True)
        self.select_segment_button.setText("Select Segment")
        self.activateWindow()
        self.raise_()

    def clear_segment(self):
        self.current_layer = self.current_segment = None
        self.plot_button.setEnabled(False)
        self.status_label.setText("Click 'Select Segment' to start.")
        self.endpoint_manager.clear_display()
        self.endpoint_manager.manual_mode = False
        self.clear_segment_button.setEnabled(False)
        if iface.mapCanvas().mapTool() == self.segment_tool:
            self.segment_tool.deactivate()
            iface.mapCanvas().unsetMapTool(self.segment_tool)
        iface.mapCanvas().refresh()

    def activate(self):
        self.endpoint_manager.activate()

    def deactivate(self):
        if iface.mapCanvas().mapTool() == self.segment_tool:
            self.segment_tool.deactivate()
            iface.mapCanvas().unsetMapTool(self.segment_tool)
        self.current_layer = self.current_segment = None
        self.plot_button.setEnabled(False)
        self.select_segment_button.setEnabled(True)
        self.select_segment_button.setText("Select Segment")
        self.clear_segment_button.setEnabled(False)
        self.status_label.setText("Click 'Select Segment' to start.")
        self.endpoint_manager.deactivate()
        iface.mapCanvas().refresh()

    def plot(self):
        if not self.current_segment:
            QMessageBox.critical(
                self, "Error", "Please select a segment first.")
            return

        layer = LayerManager.get_or_create_layer(
            "Plotted Points", QgsWkbTypes.PointGeometry, LayerManager.get_project_crs(), [
                QgsField("Type", QVariant.String)]
        )
        LayerManager.apply_categorized_symbology(layer, POINT_CATEGORIES)
        if not layer.isEditable():
            layer.startEditing()

        unit = self.unit_combo.currentText()
        offset_m = UnitConverter.to_meters(self.offset_input.value(), unit)
        cut_m = UnitConverter.to_meters(self.cut_point_input.value(), unit)
        choice = self.point_combo.currentIndex()

        self._process_line_part(self.current_segment,
                                layer, cut_m, offset_m, choice)
        LayerManager.update_layer_extent(layer)
        self.points_drawn = True

        self.cut_point_input.setValue(0.0)
        self.offset_input.setValue(0.0)
        # self.unit_combo.setCurrentText("Meters")
        # self.point_combo.setCurrentIndex(0)
        self.status_label.setText("Points added to 'Plotted Points' layer.")
        self.cut_point_input.setFocus()
        self.cut_point_input.selectAll()

    def _process_line_part(self, part, layer, cut_m, offset_m, choice_idx):
        crs = LayerManager.get_project_crs()
        start, end = part[0], part[-1]
        if choice_idx == 1:
            start, end = end, start  # Reverse for end point choice
        line_len = GeometryHelper.calculate_distance(start, end, crs)

        if cut_m < 0 or cut_m > line_len:
            self._handle_extended_point(
                start, end, cut_m, offset_m, line_len, layer, crs)
        else:
            self._handle_normal_cut_point(
                start, end, cut_m, offset_m, layer, crs)

    def _handle_normal_cut_point(self, start, end, cut_m, offset_m, layer, crs):
        cut_pt = GeometryHelper.interpolate_line(start, end, cut_m, crs)
        ptype = "Bisect Point" if offset_m == 0 else "Cut Point"
        self._add_point(layer, cut_pt, ptype)

        if offset_m != 0:
            offset_pt = GeometryHelper.project_perpendicular(
                cut_pt, start, end, offset_m, crs)
            self._add_point(layer, offset_pt, "Offset Point")

    def _handle_extended_point(self, start, end, cut_m, offset_m, line_len, layer, crs):
        if line_len == 0:
            return

        extended = GeometryHelper.interpolate_line(start, end, cut_m, crs)
        ptype = "Bisect Point" if offset_m == 0 else "Extended Point"
        self._add_point(layer, extended, ptype)

        if offset_m != 0:
            offset_pt = GeometryHelper.project_perpendicular(
                extended, start, end, offset_m, crs)
            self._add_point(layer, offset_pt, "Offset Point")

    def _add_point(self, layer, point, ptype):
        feat = QgsFeature(layer.fields())
        geom = QgsGeometry.fromPointXY(point)
        if geom.isNull() or not geom.isGeosValid():
            return False
        feat.setGeometry(geom)
        feat.setAttributes([ptype])
        return layer.addFeature(feat)

    def keyPressEvent(self, event):
        if event.key() in [QtCompat.get_key('Key_Enter'), QtCompat.get_key('Key_Return')] and self.plot_button.isEnabled():
            self.plot()
        else:
            super().keyPressEvent(event)

    def cleanup(self):
        if iface.mapCanvas().mapTool() == self.segment_tool:
            self.segment_tool.deactivate()
            iface.mapCanvas().unsetMapTool(self.segment_tool)
        if hasattr(self.segment_tool, 'cleanup'):
            self.segment_tool.cleanup()
        self.current_layer = self.current_segment = None
        self.plot_button.setEnabled(False)
        self.select_segment_button.setEnabled(True)
        self.select_segment_button.setText("Select Segment")
        self.clear_segment_button.setEnabled(False)
        self.status_label.setText("Click 'Select Segment' to start.")
        self.endpoint_manager.cleanup()
        iface.mapCanvas().refresh()


# ======================
# Main Widget
# ======================

class CombinedMainWidget(QWidget):
    def __init__(self, parent=iface.mainWindow()):
        super().__init__(parent)
        self.setWindowTitle('Plotter')
        self.setGeometry(900, 250, 250, 350)
        self.setWindowFlags(TOOL_WINDOW_FLAGS)
        self.tab_widget = QTabWidget()
        self.triangle_widget = TriangleWidget()
        self.plotter_widget = PlotterWidget()
        self.tab_widget.addTab(self.triangle_widget, "Triangle")
        self.tab_widget.addTab(self.plotter_widget, "Plotter")
        layout = QVBoxLayout()
        layout.addWidget(self.tab_widget)
        self.setLayout(layout)
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        self.has_been_activated = False

    def showEvent(self, event):
        super().showEvent(event)
        if not self.has_been_activated:
            self.triangle_widget.clear_points()
            self.plotter_widget.clear_segment()
        current = self.tab_widget.currentWidget()
        if hasattr(current, 'activate'):
            current.activate()
        self.has_been_activated = True

    def on_tab_changed(self, index):
        if not self.has_been_activated:
            return
        for w in [self.triangle_widget, self.plotter_widget]:
            if hasattr(w, 'deactivate'):
                w.deactivate()
        current_tool = iface.mapCanvas().mapTool()
        tools = [self.triangle_widget.point_tool,
                 self.plotter_widget.segment_tool]
        for tool in tools:
            if current_tool == tool:
                tool.deactivate()
                iface.mapCanvas().unsetMapTool(tool)
        current = self.tab_widget.currentWidget()
        if hasattr(current, 'activate'):
            current.activate()
        if current == self.triangle_widget:
            self.triangle_widget.schedule_preview_update()
        iface.mapCanvas().refresh()

    def closeEvent(self, event):
        current_tool = iface.mapCanvas().mapTool()
        tools = [self.triangle_widget.point_tool,
                 self.plotter_widget.segment_tool]
        for tool in tools:
            if current_tool == tool:
                tool.deactivate()
                iface.mapCanvas().unsetMapTool(tool)

        self.triangle_widget.deactivate()
        self.plotter_widget.deactivate()

        layers_to_check = [
            {'drawn': self.triangle_widget.lines_drawn,
                'name': "Triangle Lines", 'type': QgsWkbTypes.LineGeometry},
            {'drawn': self.plotter_widget.points_drawn,
                'name': "Plotted Points", 'type': QgsWkbTypes.PointGeometry}
        ]

        for info in layers_to_check:
            if not info['drawn']:
                continue
            layer = next((
                lyr for lyr in QgsProject.instance().mapLayers().values()
                if lyr.name() == info['name'] and lyr.geometryType() == info['type']
            ), None)
            if layer and layer.providerType() == "memory":
                reply = QMessageBox.question(
                    self, f"Save {info['name']}",
                    f"Do you want to save the {info['name']} Layer before closing?",
                    QtCompat.get_message_box_button('Yes') |
                    QtCompat.get_message_box_button('No') |
                    QtCompat.get_message_box_button('Cancel'),
                    QtCompat.get_message_box_button('Cancel')
                )
                if reply == QtCompat.get_message_box_button('Yes'):
                    if not LayerManager.save_temp_layer(self, layer):
                        event.ignore()
                        return
                elif reply == QtCompat.get_message_box_button('Cancel'):
                    event.ignore()
                    return

        self.triangle_widget.cleanup()
        self.plotter_widget.cleanup()
        self.has_been_activated = False
        iface.mapCanvas().refresh()
        event.accept()


# ======================
# Entry Point
# ======================

main_widget = CombinedMainWidget()
# main_widget.show()

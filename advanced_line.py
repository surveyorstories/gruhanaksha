import math
import time
from qgis.PyQt.QtCore import Qt, pyqtSignal, QPointF, QTimer
from qgis.PyQt.QtGui import QColor, QPainter
from qgis.PyQt.QtWidgets import *
from qgis.core import *
from qgis.gui import QgsMapTool, QgsRubberBand, QgsVertexMarker, QgsSnapIndicator
from qgis.utils import iface


class CursorInfo(QWidget):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.text_lines = []
        self.is_active = True

        if hasattr(Qt, 'WindowType'):
            self.setWindowFlags(
                Qt.WindowType.Tool |
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.WindowDoesNotAcceptFocus |
                Qt.WindowType.WindowTransparentForInput
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        else:
            self.setWindowFlags(
                Qt.Tool |
                Qt.FramelessWindowHint |
                Qt.WindowStaysOnTopHint |
                Qt.WindowDoesNotAcceptFocus |
                Qt.WindowTransparentForInput
            )
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setAttribute(Qt.WA_DeleteOnClose)
            self.setAttribute(Qt.WA_ShowWithoutActivating)
            self.setAttribute(Qt.WA_TransparentForMouseEvents)

        self.setStyleSheet(
            "QWidget{background:rgba(240,248,255,230);border:2px solid #2E86AB;border-radius:6px;padding:6px;font:bold 10pt Consolas;color:#FC0FC0}")

        self.cleanup_timer = QTimer(self)
        self.cleanup_timer.setSingleShot(True)
        self.cleanup_timer.timeout.connect(self.safe_hide)

        # Remove focus change connection - it's causing the problem
        # app = QApplication.instance()
        # if app:
        #     app.focusChanged.connect(self.on_focus_changed)
        self.hide()

    # Remove or comment out the on_focus_changed method entirely
    # def on_focus_changed(self, old_widget, new_widget):
    #     ...

    def _is_canvas_widget(self, widget):
        try:
            while widget:
                if widget is self.canvas:
                    return True
                parent = getattr(widget, "parent", None)
                widget = parent() if callable(parent) else parent
            return False
        except Exception:
            return False

    def safe_hide(self):
        if self.isVisible():
            self.hide()
            self.is_active = False

    def safe_show(self):
        self.is_active = True
        self.show()
        self.cleanup_timer.start(10000)

    def updateInfo(self, length=None, angle=None, coordinates=None, mode="", canvas_pos=None, label="Length", unit_suffix="m", width=None, height=None):
        self.text_lines = []
        if length is not None:
            if length < 1:
                self.text_lines.append(f"{label}: {length:.4f}{unit_suffix}")
            elif length < 1000:
                self.text_lines.append(f"{label}: {length:.3f}{unit_suffix}")
            else:
                if unit_suffix == "m":
                    self.text_lines.append(f"{label}: {length/1000:.4f}km")
                else:
                    self.text_lines.append(
                        f"{label}: {length:.3f}{unit_suffix}")

        if width is not None:
            if width < 1:
                self.text_lines.append(f"Width: {width:.4f}{unit_suffix}")
            elif width < 1000:
                self.text_lines.append(f"Width: {width:.3f}{unit_suffix}")
            else:
                if unit_suffix == "m":
                    self.text_lines.append(f"Width: {width/1000:.4f}km")
                else:
                    self.text_lines.append(f"Width: {width:.3f}{unit_suffix}")

        if height is not None:
            if height < 1:
                self.text_lines.append(f"Height: {height:.4f}{unit_suffix}")
            elif height < 1000:
                self.text_lines.append(f"Height: {height:.3f}{unit_suffix}")
            else:
                if unit_suffix == "m":
                    self.text_lines.append(f"Height: {height/1000:.4f}km")
                else:
                    self.text_lines.append(
                        f"Height: {height:.3f}{unit_suffix}")

        if angle is not None:
            self.text_lines.append(
                f"Angle: {math.degrees(angle) % 360:.1f}° (N=0° CW)")
        if mode:
            self.text_lines.append(f"Mode: {mode}")

        if self.text_lines and canvas_pos:
            fm = self.fontMetrics()
            w = max(fm.horizontalAdvance(line)
                    for line in self.text_lines) + 20
            h = (fm.height() + 2) * len(self.text_lines) + 10
            if hasattr(canvas_pos, "toPoint"):
                pos = self.canvas.mapToGlobal(canvas_pos.toPoint())
            else:
                pos = self.canvas.mapToGlobal(canvas_pos)

            self.resize(w, h)
            self.move(pos.x() + 15, pos.y() - h - 5)
            self.safe_show()
            self.update()
        else:
            self.safe_hide()

    def paintEvent(self, event):
        if not (self.text_lines and self.is_active):
            return
        painter = QPainter(self)
        y = 15
        for line in self.text_lines:
            painter.drawText(10, y, line)
            y += self.fontMetrics().height() + 2

    def closeEvent(self, event):
        self.is_active = False
        # Remove cleanup of focus change connection since we're not using it
        # app = QApplication.instance()
        # if app:
        #     try:
        #         app.focusChanged.disconnect(self.on_focus_changed)
        #     except TypeError:
        #         pass
        event.accept()


class ParameterDialog(QDialog):
    parametersEntered = pyqtSignal(float, float, bool, bool)

    def __init__(self, units_dict, current_unit_key='m'):
        super().__init__()
        self.units = units_dict
        self.current_unit_key = current_unit_key
        self.is_rectangle_mode = False
        self.setWindowTitle("Line Parameters")
        self.setModal(False)

        layout = QVBoxLayout(self)

        unit_layout = QHBoxLayout()
        unit_layout.addWidget(QLabel("Unit:"))
        self.unit_combo = QComboBox()
        for key, unit_info in self.units.items():
            self.unit_combo.addItem(unit_info['name'], key)
        self.unit_combo.setCurrentText(self.units[current_unit_key]['name'])
        self.unit_combo.currentTextChanged.connect(self.on_unit_changed)
        unit_layout.addWidget(self.unit_combo)
        layout.addLayout(unit_layout)

        first_layout = QHBoxLayout()
        self.use_first_cb = QCheckBox("Use Length")
        self.use_first_cb.setChecked(True)
        self.first_input = QDoubleSpinBox()
        self.first_input.setDecimals(4)
        self.first_input.setRange(0.0001, 999999)
        self.first_input.setValue(10.0)
        self.update_first_suffix()
        self.use_first_cb.toggled.connect(self.first_input.setEnabled)
        first_layout.addWidget(self.use_first_cb)
        first_layout.addWidget(self.first_input)
        layout.addLayout(first_layout)

        second_layout = QHBoxLayout()
        self.use_second_cb = QCheckBox("Use Angle")
        self.use_second_cb.setChecked(False)
        self.second_input = QDoubleSpinBox()
        self.second_input.setDecimals(1)
        self.second_input.setRange(0.0, 359.9)
        self.second_input.setValue(0.0)
        self.second_input.setSuffix("° (N=0° CW)")
        self.second_input.setEnabled(False)
        self.use_second_cb.toggled.connect(self.second_input.setEnabled)
        second_layout.addWidget(self.use_second_cb)
        second_layout.addWidget(self.second_input)
        layout.addLayout(second_layout)

        self.angle_buttons_widget = QWidget()
        self.grid = QGridLayout(self.angle_buttons_widget)
        for i, angle in enumerate([0, 45, 90, 135, 180, 225, 270, 315]):
            btn = QPushButton(f"{angle}°")
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _, a=angle: self.set_quick_angle(a))
            self.grid.addWidget(btn, i // 4, i % 4)
        layout.addWidget(self.angle_buttons_widget)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("Apply")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept_parameters)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(QPushButton("Cancel", clicked=self.close))
        layout.addLayout(btn_layout)

        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet("color: red; font-weight: bold;")
        self.warning_label.hide()
        layout.addWidget(self.warning_label)

    def set_rectangle_mode(self, is_rectangle):
        self.is_rectangle_mode = is_rectangle

        if is_rectangle:
            self.setWindowTitle("Rectangle Parameters")
            self.use_first_cb.setText("Use Width")
            self.use_second_cb.setText("Use Height")
            self.second_input.setSuffix("")
            self.second_input.setRange(0.0001, 999999)
            self.second_input.setDecimals(4)
            self.update_second_suffix()
            self.angle_buttons_widget.hide()
        else:
            self.setWindowTitle("Line Parameters")
            self.use_first_cb.setText("Use Length")
            self.use_second_cb.setText("Use Angle")
            self.second_input.setSuffix("° (N=0° CW)")
            self.second_input.setRange(0.0, 359.9)
            self.second_input.setDecimals(1)
            self.angle_buttons_widget.show()

    def on_unit_changed(self):
        selected_unit_key = self.unit_combo.currentData()
        if selected_unit_key and selected_unit_key != self.current_unit_key:
            old_factor = self.units[self.current_unit_key]['factor']
            new_factor = self.units[selected_unit_key]['factor']

            current_value = self.first_input.value()
            meters_value = current_value * old_factor
            new_value = meters_value / new_factor
            self.first_input.setValue(new_value)

            if self.is_rectangle_mode:
                current_value = self.second_input.value()
                meters_value = current_value * old_factor
                new_value = meters_value / new_factor
                self.second_input.setValue(new_value)

            self.current_unit_key = selected_unit_key
            self.update_first_suffix()
            if self.is_rectangle_mode:
                self.update_second_suffix()

    def update_first_suffix(self):
        suffix = f" {self.units[self.current_unit_key]['suffix']}"
        self.first_input.setSuffix(suffix)

    def update_second_suffix(self):
        if self.is_rectangle_mode:
            suffix = f" {self.units[self.current_unit_key]['suffix']}"
            self.second_input.setSuffix(suffix)

    def set_quick_angle(self, angle):
        if not self.is_rectangle_mode:
            self.use_second_cb.setChecked(True)
            self.second_input.setValue(angle)

    def accept_parameters(self):
        use_first = self.use_first_cb.isChecked()
        use_second = self.use_second_cb.isChecked()

        if not use_first and not use_second:
            param_names = "Width or Height" if self.is_rectangle_mode else "Length or Angle"
            self.warning_label.setText(f"Please select at least {param_names}")
            self.warning_label.show()
            return

        if use_first and self.first_input.value() <= 0:
            param_name = "Width" if self.is_rectangle_mode else "Length"
            self.warning_label.setText(f"{param_name} must be greater than 0")
            self.warning_label.show()
            return

        if self.is_rectangle_mode and use_second and self.second_input.value() <= 0:
            self.warning_label.setText("Height must be greater than 0")
            self.warning_label.show()
            return

        self.warning_label.hide()

        first_in_input_units = self.first_input.value()
        first_in_meters = first_in_input_units * \
            self.units[self.current_unit_key]['factor']

        if self.is_rectangle_mode:
            second_in_input_units = self.second_input.value()
            second_in_meters = second_in_input_units * \
                self.units[self.current_unit_key]['factor']
        else:
            second_in_meters = math.radians(
                self.second_input.value()) if use_second else 0

        self.parametersEntered.emit(
            first_in_meters, second_in_meters, use_first, use_second)
        self.hide()

    def show_dialog(self, cur_len_meters=10.0, cur_width_meters=10.0):
        if self.is_rectangle_mode:
            width_in_display_units = cur_len_meters / \
                self.units[self.current_unit_key]['factor']
            height_in_display_units = cur_width_meters / \
                self.units[self.current_unit_key]['factor']
            self.first_input.setValue(width_in_display_units)
            self.second_input.setValue(height_in_display_units)
            self.use_first_cb.setChecked(True)
            self.use_second_cb.setChecked(True)
        else:
            length_in_display_units = cur_len_meters / \
                self.units[self.current_unit_key]['factor']
            self.first_input.setValue(length_in_display_units)
            self.use_first_cb.setChecked(True)
            self.use_second_cb.setChecked(False)

        self.warning_label.hide()
        self.show()
        QTimer.singleShot(50, lambda: (
            self.first_input.setFocus(), self.first_input.lineEdit().selectAll()))

    def closeEvent(self, event):
        self.hide()
        event.ignore()


def create_marker(canvas, point, color=QColor(0, 255, 0), is_snappable=False):
    marker = QgsVertexMarker(canvas)
    marker.setCenter(point)
    marker.setColor(color)
    marker.setIconType(QgsVertexMarker.IconType.ICON_BOX)
    marker.setIconSize(12)
    marker.setPenWidth(2)
    marker.setData(0, is_snappable)
    return marker


def show_msg(msg, duration=2, level=Qgis.MessageLevel.Info):
    if iface and iface.messageBar():
        iface.messageBar().pushMessage("📐 Line Tool", msg, level=level, duration=duration)


class ProfessionalLineTool(QgsMapTool):

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.reset_state()

        self.rubber_band = QgsRubberBand(
            canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.rubber_band.setColor(QColor("#f462ab"))
        self.rubber_band.setWidth(1)

        self.snapped_segment_rubber_band = QgsRubberBand(
            canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.snapped_segment_rubber_band.setColor(QColor("red"))
        self.snapped_segment_rubber_band.setWidth(2)

        self.cursor_info = CursorInfo(canvas)
        self.snapping = canvas.snappingUtils()
        self.snap_indicator = QgsSnapIndicator(canvas)

        # Unit conversion - Only 5 specified units
        self.units = {
            'm': {'name': 'Meters', 'factor': 1.0, 'suffix': 'm'},
            'mli': {'name': 'Metric Links', 'factor': 0.2, 'suffix': 'Metric'},
            'li': {'name': 'Gunter Links', 'factor': 0.201168, 'suffix': 'Gunter'},
            'ft': {'name': 'Feet', 'factor': 0.3048, 'suffix': 'ft'},
            'yd': {'name': 'Yards', 'factor': 0.9144, 'suffix': 'yd'},
        }
        self.current_unit_key = 'm'
        self.unit_keys = list(self.units.keys())
        self.current_unit_index = 0

        self.dialog = ParameterDialog(self.units, self.current_unit_key)
        try:
            self.dialog.setParent(iface.mainWindow(), Qt.WindowType.Window)
        except AttributeError:
            self.dialog.setParent(iface.mainWindow(), Qt.Window)
        self.dialog.parametersEntered.connect(self.set_parameters)

        # Initialize distance calculator
        self.dist_calc = QgsDistanceArea()
        self._update_distance_calculator()

    def _update_distance_calculator(self):
        """Update the distance calculator with current CRS settings"""
        layer_crs = self._get_layer_crs()
        self.dist_calc.setSourceCrs(
            layer_crs, QgsProject.instance().transformContext())

        if layer_crs.isGeographic():
            self.dist_calc.setEllipsoid(layer_crs.ellipsoidAcronym())
        else:
            self.dist_calc.setEllipsoid(QgsProject.instance().ellipsoid())

    def _get_layer_crs(self):
        """Get the CRS of the active layer"""
        layer = iface.activeLayer()
        if layer:
            return layer.crs()
        return self.canvas.mapSettings().destinationCrs()

    def _get_project_crs(self):
        """Get the CRS of the project/map canvas"""
        return self.canvas.mapSettings().destinationCrs()

    def _get_crs_transform_to_layer(self):
        """Get coordinate transform from project CRS to layer CRS"""
        layer_crs = self._get_layer_crs()
        project_crs = self._get_project_crs()

        if layer_crs != project_crs:
            return QgsCoordinateTransform(project_crs, layer_crs, QgsProject.instance())
        return None

    def _get_crs_transform_to_project(self):
        """Get coordinate transform from layer CRS to project CRS"""
        layer_crs = self._get_layer_crs()
        project_crs = self._get_project_crs()

        if layer_crs != project_crs:
            return QgsCoordinateTransform(layer_crs, project_crs, QgsProject.instance())
        return None

    def _transform_point_to_layer(self, point):
        """Transform a point from project CRS to layer CRS"""
        transform = self._get_crs_transform_to_layer()
        if transform:
            try:
                return transform.transform(point)
            except Exception:
                return point
        return point

    def _transform_point_to_project(self, point):
        """Transform a point from layer CRS to project CRS"""
        transform = self._get_crs_transform_to_project()
        if transform:
            try:
                return transform.transform(point)
            except Exception:
                return point
        return point

    def _calculate_distance_in_layer_crs(self, p1, p2):
        """Calculate distance between two points in layer CRS, returns distance in METERS"""
        return self.dist_calc.measureLine(p1, p2)

    def _meters_to_crs_units(self, meters, direction_x=1.0, direction_y=0.0, reference_point=None):
        """Convert meters to CRS units for drawing geometry using accurate ellipsoidal calculations

        Args:
            meters: Distance in meters
            direction_x: X component of direction vector (normalized)
            direction_y: Y component of direction vector (normalized)
            reference_point: Reference point for calculations (required for geographic CRS)

        Returns:
            Distance in CRS units
        """
        layer_crs = self._get_layer_crs()

        if layer_crs.isGeographic():
            # For geographic CRS, use iterative approach to find correct offset
            if not reference_point:
                reference_point = QgsPointXY(0, 0)

            # Normalize direction
            length = math.sqrt(direction_x**2 + direction_y**2)
            if length > 0:
                direction_x /= length
                direction_y /= length

            # Initial estimate using simple approximation
            lat = reference_point.y()
            meters_per_degree_lat = 111320.0
            meters_per_degree_lon = 111320.0 * math.cos(math.radians(lat))

            # Initial guess
            initial_offset = math.sqrt(
                (meters * direction_y / meters_per_degree_lat)**2 +
                (meters * direction_x / meters_per_degree_lon)**2
            )

            # Iterative refinement to match ellipsoidal distance
            offset = initial_offset
            tolerance = 0.001  # 1mm tolerance
            max_iterations = 10

            for _ in range(max_iterations):
                test_point = QgsPointXY(
                    reference_point.x() + offset * direction_x,
                    reference_point.y() + offset * direction_y
                )

                actual_distance = self.dist_calc.measureLine(
                    reference_point, test_point)
                error = actual_distance - meters

                if abs(error) < tolerance:
                    break

                # Adjust offset proportionally
                if actual_distance > 0:
                    correction_factor = meters / actual_distance
                    offset *= correction_factor

            return offset
        else:
            # For projected CRS, get the units factor
            units = layer_crs.mapUnits()

            # Convert from QgsUnitTypes to meters factor
            if units == QgsUnitTypes.DistanceMeters:
                return meters
            elif units == QgsUnitTypes.DistanceKilometers:
                return meters / 1000.0
            elif units == QgsUnitTypes.DistanceFeet:
                return meters / 0.3048
            elif units == QgsUnitTypes.DistanceYards:
                return meters / 0.9144
            elif units == QgsUnitTypes.DistanceMiles:
                return meters / 1609.344
            elif units == QgsUnitTypes.DistanceNauticalMiles:
                return meters / 1852.0
            elif units == QgsUnitTypes.DistanceCentimeters:
                return meters * 100.0
            elif units == QgsUnitTypes.DistanceMillimeters:
                return meters * 1000.0
            else:
                # Default to meters if unknown
                return meters

    def _set_current_unit(self, key):
        if key in self.units:
            self.current_unit_key = key
            self.current_unit_index = self.unit_keys.index(key)
            self.dialog.current_unit_key = key
            self.dialog.unit_combo.setCurrentText(self.units[key]['name'])
            self.dialog.update_first_suffix()
            if self.dialog.is_rectangle_mode:
                self.dialog.update_second_suffix()
            show_msg(f"Unit set to: {self.units[key]['name']}", 1)
        else:
            show_msg(f"Unknown unit: {key}", 1, Qgis.MessageLevel.Warning)

    def _next_unit(self):
        self.current_unit_index = (
            self.current_unit_index + 1) % len(self.unit_keys)
        new_key = self.unit_keys[self.current_unit_index]
        self._set_current_unit(new_key)

    def reset_state(self):
        self.is_drawing = False
        self.ortho_mode = False
        self.points = []
        self.start_point = None
        self.current_point = None
        self.current_snap_point = None
        self.is_vertex_snap = False
        self.is_segment_snap = False
        self.markers = []
        self.preview_length = 0
        self.preview_angle = 0
        self.length_mode = False
        self.angle_mode = False
        self.last_angle = 0
        self.angle_lock = {'active': False, 'index': 0,
                           'angles': [math.pi/2, math.pi], 'last_press': 0}

        self.circle_mode = False
        self.circle_center = None
        self.circle_radius = 0

        self.rectangle_mode = False
        self.rect_points = []
        self.rect_width = 0
        self.rect_height = 0
        self.rect_width_mode = False
        self.rect_height_mode = False
        self.rect_angle_lock = True

    def activate(self):
        self.canvas.setCursor(Qt.CursorShape.CrossCursor)
        self._update_distance_calculator()
        layer_crs = self._get_layer_crs()
        project_crs = self._get_project_crs()
        if layer_crs != project_crs:
            show_msg(
                f"Layer CRS: {layer_crs.authid()} | Project CRS: {project_crs.authid()}", 3)

    def canvasPressEvent(self, event):
        if not self._valid_layer():
            return

        snap_point, _ = self._get_snap_point(event.pos())
        point_project = snap_point or self.toMapCoordinates(event.pos())

        point = self._transform_point_to_layer(point_project)

        if self.circle_mode:
            self._handle_circle_click(point, event.pos(), event)
            return

        if self.rectangle_mode:
            self._handle_rectangle_click(point, event.pos(), event)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            if (self.length_mode or self.angle_mode) and not self.start_point:
                self._start_line(point, event.pos())
                show_msg("Move mouse and click to confirm")
            elif self.length_mode or self.angle_mode:
                self._confirm_preview()
            elif not self.is_drawing:
                self._start_line(point, event.pos())
            else:
                self._add_point(point)
        elif event.button() == Qt.MouseButton.RightButton:
            self._handle_right_click()

    def _handle_rectangle_click(self, point, canvas_pos, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if len(self.rect_points) == 0:
                self.rect_points.append(point)
                point_project = self._transform_point_to_project(point)
                self.markers.append(create_marker(
                    self.canvas, point_project, QColor(255, 165, 0), is_snappable=True))
                show_msg("Rectangle corner set. Click second corner.", 2)
            elif len(self.rect_points) == 1:
                if self.rect_width_mode or self.rect_height_mode:
                    self.rect_points.append(point)
                    rect_geom = self._create_rectangle_from_params(point)
                    if rect_geom:
                        self._add_rectangle_to_layer(rect_geom)
                        show_msg("Rectangle added!", 1)
                    self._reset_rectangle()
                else:
                    self.rect_points.append(point)
                    point_project = self._transform_point_to_project(point)
                    self.markers.append(create_marker(
                        self.canvas, point_project, QColor(255, 255, 0), is_snappable=True))
                    show_msg(
                        "Second corner set. Click third corner to complete rectangle.", 2)
            elif len(self.rect_points) == 2:
                if self.rect_width_mode or self.rect_height_mode:
                    rect_geom = self._create_rectangle_from_constraints()
                    if rect_geom:
                        self._add_rectangle_to_layer(rect_geom)
                        show_msg("Rectangle added!", 1)
                else:
                    self.rect_points.append(point)
                    rect_geom = self._create_rectangle_from_points()
                    if rect_geom:
                        self._add_rectangle_to_layer(rect_geom)
                        show_msg("Rectangle completed!", 1)
                self._reset_rectangle()
        elif event.button() == Qt.MouseButton.RightButton:
            if self.rect_points:
                self._reset_rectangle()
                show_msg("Rectangle cancelled", 1)

    def _handle_circle_click(self, point, canvas_pos, event):
        if self.circle_center is None:
            self.circle_center = point
            if self.circle_radius:
                circle_geom = self._create_circle_geometry(
                    self.circle_center, self.circle_radius)
                self._add_circle_to_layer(circle_geom)
                self.circle_center = None
                self.circle_radius = 0
                self.rubber_band.reset()
                show_msg("Circle added!", 1)
            else:
                show_msg(
                    "Circle center set. Move and click to set radius or press L.", 2)
        else:
            radius = self._calculate_distance_in_layer_crs(
                self.circle_center, point)
            circle_geom = self._create_circle_geometry(
                self.circle_center, radius)
            self._add_circle_to_layer(circle_geom)
            self.circle_center = None
            self.circle_radius = 0
            self.rubber_band.reset()
            show_msg("Circle added!", 2)

    def canvasMoveEvent(self, event):
        snap_point, snap_details = self._get_snap_point(event.pos())

        self.is_vertex_snap = False
        self.is_segment_snap = False

        if snap_details:
            self.is_vertex_snap = snap_details.get('snap_type') == 'vertex'
            self.is_segment_snap = snap_details.get('snap_type') == 'segment'
            qgis_match = snap_details.get('match')
            if qgis_match and hasattr(qgis_match, 'isValid') and qgis_match.isValid():
                self.snap_indicator.setMatch(qgis_match)
            else:
                self.snap_indicator.setMatch(QgsPointLocator.Match())
        else:
            self.snap_indicator.setMatch(QgsPointLocator.Match())

        map_point_project = self.toMapCoordinates(event.pos())
        point_project = snap_point or map_point_project

        # Transform to layer CRS
        point = self._transform_point_to_layer(point_project)

        self.current_snap_point = snap_point
        self.current_point = point  # Store in layer CRS

        if self.circle_mode and self.circle_center:
            self._handle_circle_move(event)
            return

        if self.rectangle_mode:
            self._handle_rectangle_move(event)
            return

        if self.length_mode or self.angle_mode:
            self._update_parameter_preview()
        elif self.is_drawing and self.start_point:
            self._update_drawing_preview()
        self._update_cursor_info(event.pos())

    def _handle_rectangle_move(self, event):
        snap_point, snap_details = self._get_snap_point(event.pos())

        # Update snap status based on snap_details
        self.is_vertex_snap = False
        self.is_segment_snap = False

        if snap_details:
            self.is_vertex_snap = snap_details.get('snap_type') == 'vertex'
            self.is_segment_snap = snap_details.get('snap_type') == 'segment'
            qgis_match = snap_details.get('match')
            if qgis_match and hasattr(qgis_match, 'isValid') and qgis_match.isValid():
                self.snap_indicator.setMatch(qgis_match)
            else:
                self.snap_indicator.setMatch(QgsPointLocator.Match())
        else:
            self.snap_indicator.setMatch(QgsPointLocator.Match())

        point_project = snap_point or self.toMapCoordinates(event.pos())
        point = self._transform_point_to_layer(point_project)
        self.current_point = point

        if self.rect_width_mode or self.rect_height_mode:
            if len(self.rect_points) == 1:
                rect_pts = self._calculate_rectangle_preview(point)
                if rect_pts:
                    self.rubber_band.reset()
                    for pt in rect_pts:
                        pt_project = self._transform_point_to_project(pt)
                        self.rubber_band.addPoint(pt_project)
                    pt_project = self._transform_point_to_project(rect_pts[0])
                    self.rubber_band.addPoint(pt_project)
            elif len(self.rect_points) == 2:
                rect_pts = self._get_constrained_rectangle_preview()
                if rect_pts:
                    self.rubber_band.reset()
                    for pt in rect_pts:
                        pt_project = self._transform_point_to_project(pt)
                        self.rubber_band.addPoint(pt_project)
                    pt_project = self._transform_point_to_project(rect_pts[0])
                    self.rubber_band.addPoint(pt_project)
        else:
            if len(self.rect_points) == 1:
                self.rubber_band.reset()
                pt_project = self._transform_point_to_project(
                    self.rect_points[0])
                self.rubber_band.addPoint(pt_project)
                self.rubber_band.addPoint(point_project)
            elif len(self.rect_points) == 2:
                rect_pts = self._calculate_partial_rectangle_with_constraints(
                    point)
                if rect_pts:
                    self.rubber_band.reset()
                    for pt in rect_pts:
                        pt_project = self._transform_point_to_project(pt)
                        self.rubber_band.addPoint(pt_project)
                    pt_project = self._transform_point_to_project(rect_pts[0])
                    self.rubber_band.addPoint(pt_project)

        self._update_rectangle_cursor_info(event.pos())

    def _handle_circle_move(self, event):
        config = QgsProject.instance().snappingConfig()

        snap_match = None
        if config.enabled():
            self.snapping.setConfig(config)
            snap_match = self.snapping.snapToMap(
                self.toMapCoordinates(event.pos()))

            if snap_match.isValid():
                self.snap_indicator.setMatch(snap_match)
            else:
                self.snap_indicator.setMatch(QgsPointLocator.Match())
        else:
            self.snap_indicator.setMatch(QgsPointLocator.Match())

        point_project = snap_match.point() if (snap_match and snap_match.isValid()
                                               ) else self.toMapCoordinates(event.pos())
        point = self._transform_point_to_layer(point_project)

        radius = self._calculate_distance_in_layer_crs(
            self.circle_center, point)
        circle_pts = self._create_circle_geometry(
            self.circle_center, radius, preview_only=True)
        self.rubber_band.reset()
        for pt in circle_pts:
            pt_project = self._transform_point_to_project(pt)
            self.rubber_band.addPoint(pt_project)

        radius_in_display_units = radius / \
            self.units[self.current_unit_key]['factor']
        unit_suffix = self.units[self.current_unit_key]['suffix']

        self.cursor_info.updateInfo(
            length=radius,
            angle=None,
            coordinates=point,
            mode=f"Circle | Snap: {'ON' if config.enabled() else 'OFF'}",
            canvas_pos=event.pos(),
            label="Radius",
            unit_suffix=unit_suffix
        )

    def _calculate_rectangle_preview(self, current_point):
        if not self.rect_points:
            return None

        corner1 = self.rect_points[0]

        # Calculate distance and direction
        dist = self._calculate_distance_in_layer_crs(corner1, current_point)

        dx = current_point.x() - corner1.x()
        dy = current_point.y() - corner1.y()

        if abs(dx) < 1e-10 and abs(dy) < 1e-10:
            return None

        crs_dist = math.hypot(dx, dy)
        if crs_dist < 1e-10:
            return None

        dir_x = dx / crs_dist
        dir_y = dy / crs_dist
        perp_x = -dir_y
        perp_y = dir_x

        # Width and height are already in meters from parameters
        width_meters = self.rect_width if self.rect_width_mode else dist
        height_meters = self.rect_height if self.rect_height_mode else dist * 0.5

        # Convert meters to CRS units for drawing
        width_crs = self._meters_to_crs_units(
            width_meters, dir_x, dir_y, corner1)
        height_crs = self._meters_to_crs_units(
            height_meters, perp_x, perp_y, corner1)

        corner2 = QgsPointXY(corner1.x() + width_crs * dir_x,
                             corner1.y() + width_crs * dir_y)
        corner3 = QgsPointXY(corner2.x() + height_crs *
                             perp_x, corner2.y() + height_crs * perp_y)
        corner4 = QgsPointXY(corner1.x() + height_crs *
                             perp_x, corner1.y() + height_crs * perp_y)

        return [corner1, corner2, corner3, corner4]

    def _calculate_partial_rectangle_with_constraints(self, third_point):
        if len(self.rect_points) < 2:
            return None

        p1, p2 = self.rect_points[0], self.rect_points[1]

        if self.rect_width_mode or self.rect_height_mode:
            # Get direction from p1 to p2
            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            edge1_length_crs = math.hypot(dx, dy)

            if edge1_length_crs < 1e-10:
                return None

            dir_x = dx / edge1_length_crs
            dir_y = dy / edge1_length_crs
            perp_x = -dir_y
            perp_y = dir_x

            # Width and height are in meters, need to convert to CRS units
            width_meters = self.rect_width if self.rect_width_mode else self._calculate_distance_in_layer_crs(
                p1, p2)
            height_meters = self.rect_height if self.rect_height_mode else width_meters * 0.6

            # Convert to CRS units using proper method
            width_crs = self._meters_to_crs_units(
                width_meters, dir_x, dir_y, p1)
            height_crs = self._meters_to_crs_units(
                height_meters, perp_x, perp_y, p1)

            if self.rect_width_mode:
                p2 = QgsPointXY(p1.x() + width_crs * dir_x,
                                p1.y() + width_crs * dir_y)

            p3 = QgsPointXY(p2.x() + height_crs * perp_x,
                            p2.y() + height_crs * perp_y)
            p4 = QgsPointXY(p1.x() + height_crs * perp_x,
                            p1.y() + height_crs * perp_y)

            return [p1, p2, p3, p4]

        p3 = third_point

        if self.rect_angle_lock:
            edge1_x = p2.x() - p1.x()
            edge1_y = p2.y() - p1.y()
            edge1_length = math.hypot(edge1_x, edge1_y)

            if edge1_length > 1e-10:
                edge1_dir_x = edge1_x / edge1_length
                edge1_dir_y = edge1_y / edge1_length
                perp_dir_x = -edge1_dir_y
                perp_dir_y = edge1_dir_x

                mouse_dx = p3.x() - p1.x()
                mouse_dy = p3.y() - p1.y()
                mouse_dist = math.hypot(mouse_dx, mouse_dy)

                if mouse_dist > 1e-10:
                    proj_length = mouse_dx * perp_dir_x + mouse_dy * perp_dir_y
                    p3 = QgsPointXY(p1.x() + proj_length * perp_dir_x,
                                    p1.y() + proj_length * perp_dir_y)

        v12_x = p2.x() - p1.x()
        v12_y = p2.y() - p1.y()
        v13_x = p3.x() - p1.x()
        v13_y = p3.y() - p1.y()

        p4 = QgsPointXY(p2.x() + v13_x, p2.y() + v13_y)

        return [p1, p2, p4, p3]

    def _create_rectangle_from_points(self):
        if len(self.rect_points) != 3:
            return None

        p1, p2, p3 = self.rect_points

        if self.rect_width_mode or self.rect_height_mode:
            return self._create_rectangle_from_params(p3)

        if self.rect_angle_lock:
            edge1_x = p2.x() - p1.x()
            edge1_y = p2.y() - p1.y()
            edge1_length = math.hypot(edge1_x, edge1_y)

            if edge1_length > 1e-10:
                edge1_dir_x = edge1_x / edge1_length
                edge1_dir_y = edge1_y / edge1_length
                perp_dir_x = -edge1_dir_y
                perp_dir_y = edge1_dir_x

                orig_dx = p3.x() - p1.x()
                orig_dy = p3.y() - p1.y()
                proj_length = orig_dx * perp_dir_x + orig_dy * perp_dir_y

                p3 = QgsPointXY(p1.x() + proj_length * perp_dir_x,
                                p1.y() + proj_length * perp_dir_y)

        v12_x = p2.x() - p1.x()
        v12_y = p2.y() - p1.y()
        v13_x = p3.x() - p1.x()
        v13_y = p3.y() - p1.y()

        p4 = QgsPointXY(p2.x() + v13_x, p2.y() + v13_y)

        rectangle_points = [p1, p2, p4, p3, p1]
        return QgsGeometry.fromPolylineXY(rectangle_points)

    def _get_constrained_rectangle_preview(self):
        if len(self.rect_points) != 2:
            return None

        p1, p2 = self.rect_points[0], self.rect_points[1]

        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        edge1_length_crs = math.hypot(dx, dy)

        if edge1_length_crs < 1e-10:
            return None

        dir_x = dx / edge1_length_crs
        dir_y = dy / edge1_length_crs
        perp_x = -dir_y
        perp_y = dir_x

        # Width and height in meters
        width_meters = self.rect_width if self.rect_width_mode else self._calculate_distance_in_layer_crs(
            p1, p2)
        height_meters = self.rect_height if self.rect_height_mode else width_meters * 0.6

        # Convert to CRS units using proper method
        width_crs = self._meters_to_crs_units(width_meters, dir_x, dir_y, p1)
        height_crs = self._meters_to_crs_units(
            height_meters, perp_x, perp_y, p1)

        if self.rect_width_mode:
            p2 = QgsPointXY(p1.x() + width_crs * dir_x,
                            p1.y() + width_crs * dir_y)

        p3 = QgsPointXY(p2.x() + height_crs * perp_x,
                        p2.y() + height_crs * perp_y)
        p4 = QgsPointXY(p1.x() + height_crs * perp_x,
                        p1.y() + height_crs * perp_y)

        return [p1, p2, p3, p4]

    def _create_rectangle_from_constraints(self):
        if len(self.rect_points) != 2:
            return None

        p1, p2 = self.rect_points[0], self.rect_points[1]

        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        edge1_length_crs = math.hypot(dx, dy)

        if edge1_length_crs < 1e-10:
            return None

        dir_x = dx / edge1_length_crs
        dir_y = dy / edge1_length_crs
        perp_x = -dir_y
        perp_y = dir_x

        # Width and height in meters
        width_meters = self.rect_width if self.rect_width_mode else self._calculate_distance_in_layer_crs(
            p1, p2)
        height_meters = self.rect_height if self.rect_height_mode else width_meters * 0.6

        # Convert to CRS units using proper method
        width_crs = self._meters_to_crs_units(width_meters, dir_x, dir_y, p1)
        height_crs = self._meters_to_crs_units(
            height_meters, perp_x, perp_y, p1)

        if self.rect_width_mode:
            p2 = QgsPointXY(p1.x() + width_crs * dir_x,
                            p1.y() + width_crs * dir_y)

        p3 = QgsPointXY(p2.x() + height_crs * perp_x,
                        p2.y() + height_crs * perp_y)
        p4 = QgsPointXY(p1.x() + height_crs * perp_x,
                        p1.y() + height_crs * perp_y)

        rectangle_points = [p1, p2, p3, p4, p1]
        return QgsGeometry.fromPolylineXY(rectangle_points)

    def _create_rectangle_from_params(self, second_point):
        if not self.rect_points:
            return None

        corner1 = self.rect_points[0]

        dx = second_point.x() - corner1.x()
        dy = second_point.y() - corner1.y()
        dist_crs = math.hypot(dx, dy)

        if dist_crs < 1e-10:
            return None

        dir_x = dx / dist_crs
        dir_y = dy / dist_crs
        perp_x = -dir_y
        perp_y = dir_x

        # Calculate dimensions in meters
        if self.rect_width_mode and self.rect_height_mode:
            width_meters = self.rect_width
            height_meters = self.rect_height
        elif self.rect_width_mode:
            width_meters = self.rect_width
            mouse_perp_proj = (second_point.x() - corner1.x()) * \
                perp_x + (second_point.y() - corner1.y()) * perp_y
            height_meters = abs(mouse_perp_proj) or self._calculate_distance_in_layer_crs(
                corner1, second_point) * 0.6
        elif self.rect_height_mode:
            height_meters = self.rect_height
            width_meters = self._calculate_distance_in_layer_crs(
                corner1, second_point)
        else:
            dist = self._calculate_distance_in_layer_crs(corner1, second_point)
            width_meters = dist
            height_meters = dist * 0.6

        # Convert to CRS units using proper method
        width_crs = self._meters_to_crs_units(
            width_meters, dir_x, dir_y, corner1)
        height_crs = self._meters_to_crs_units(
            height_meters, perp_x, perp_y, corner1)

        corner2 = QgsPointXY(corner1.x() + width_crs * dir_x,
                             corner1.y() + width_crs * dir_y)
        corner3 = QgsPointXY(corner2.x() + height_crs *
                             perp_x, corner2.y() + height_crs * perp_y)
        corner4 = QgsPointXY(corner1.x() + height_crs *
                             perp_x, corner1.y() + height_crs * perp_y)

        rectangle_points = [corner1, corner2, corner3, corner4, corner1]
        return QgsGeometry.fromPolylineXY(rectangle_points)

    def _add_rectangle_to_layer(self, geometry):
        layer = iface.activeLayer()
        if not (layer and layer.isEditable()):
            show_msg("Need editable line layer", 1, Qgis.MessageLevel.Critical)
            return False
        feature = QgsFeature(layer.fields())
        feature.setGeometry(geometry)
        if layer.addFeature(feature):
            layer.updateExtents()
            layer.triggerRepaint()
            self.canvas.refresh()
            return True
        return False

    def _reset_rectangle(self):
        self.rect_points = []
        self.rect_width_mode = False
        self.rect_height_mode = False
        self.rect_width = 0
        self.rect_height = 0
        self.rubber_band.reset()
        for marker in self.markers:
            if marker.color() in [QColor(255, 165, 0), QColor(255, 255, 0), QColor(0, 255, 255)]:
                marker.hide()

    def _update_rectangle_cursor_info(self, canvas_pos):
        config = QgsProject.instance().snappingConfig()
        snap_status = "ON" if config.enabled() else "OFF"
        if self.is_vertex_snap:
            snap_status += " + Vertex"
        unit_suffix = self.units[self.current_unit_key]['suffix']

        width = height = length = angle = None

        if self.current_point and self.rect_points:
            if self.rect_width_mode or self.rect_height_mode:
                if len(self.rect_points) == 1:
                    corner1 = self.rect_points[0]
                    dx = self.current_point.x() - corner1.x()
                    dy = self.current_point.y() - corner1.y()
                    dist = math.hypot(dx, dy)

                    width_meters = self.rect_width if self.rect_width_mode else dist
                    height_meters = self.rect_height if self.rect_height_mode else dist * 0.5

                    width = width_meters / \
                        self.units[self.current_unit_key]['factor']
                    height = height_meters / \
                        self.units[self.current_unit_key]['factor']
                    angle = math.atan2(dx, dy)
            else:
                if len(self.rect_points) == 1:
                    corner1 = self.rect_points[0]
                    dx = self.current_point.x() - corner1.x()
                    dy = self.current_point.y() - corner1.y()
                    length_meters = math.hypot(dx, dy)
                    length = length_meters / \
                        self.units[self.current_unit_key]['factor']
                    angle = math.atan2(dx, dy)
                elif len(self.rect_points) == 2:
                    p1, p2 = self.rect_points[0], self.rect_points[1]
                    width_meters = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
                    height_meters = math.hypot(
                        self.current_point.x() - p1.x(), self.current_point.y() - p1.y())

                    width = width_meters / \
                        self.units[self.current_unit_key]['factor']
                    height = height_meters / \
                        self.units[self.current_unit_key]['factor']

        mode_parts = ["Rectangle"]
        if self.rect_width_mode and self.rect_height_mode:
            mode_parts.append("W&H Fixed")
        elif self.rect_width_mode:
            mode_parts.append("Width Fixed")
        elif self.rect_height_mode:
            mode_parts.append("Height Fixed")

        if len(self.rect_points) == 1:
            mode_parts.append("Set 2nd corner")
        elif len(self.rect_points) == 2:
            lock_status = "ON" if self.rect_angle_lock else "OFF"
            mode_parts.append(f"A: Toggle 90° - {lock_status})")

        mode = " | ".join(mode_parts)

        self.cursor_info.updateInfo(
            length=length, angle=angle, coordinates=self.current_point,
            width=width, height=height,
            mode=f"{mode} | Snap: {snap_status} | Unit: {self.units[self.current_unit_key]['name']}",
            canvas_pos=QPointF(canvas_pos), unit_suffix=unit_suffix
        )

    def _cancel_constraints(self):
        if self.length_mode or self.angle_mode:
            self.length_mode = False
            self.angle_mode = False
            self.preview_length = 0
            self.preview_angle = 0

            if self.is_drawing:
                self._update_drawing_preview()
            else:
                self.rubber_band.reset()

            show_msg("Constraints cancelled - free drawing mode", 2)
            return True
        elif self.rect_width_mode or self.rect_height_mode:
            self.rect_width_mode = False
            self.rect_height_mode = False
            self.rect_width = 0
            self.rect_height = 0
            show_msg("Rectangle constraints cancelled - freehand mode", 2)
            return True
        return False

    def keyPressEvent(self, event):
        if self.circle_mode and event.key() == Qt.Key.Key_L:
            try:
                self.dialog.parametersEntered.disconnect()
            except Exception:
                pass
            self.dialog.parametersEntered.connect(self._apply_circle_radius)
            self.dialog.set_rectangle_mode(False)
            self.dialog.setWindowTitle("Circle Parameters")
            self.dialog.first_input.setPrefix("Radius: ")
            self.dialog.use_second_cb.hide()
            self.dialog.second_input.hide()
            self.dialog.angle_buttons_widget.hide()
            self.dialog.show_dialog(self.circle_radius or 10.0)
            return
        elif self.rectangle_mode and event.key() == Qt.Key.Key_L:
            try:
                self.dialog.parametersEntered.disconnect()
            except Exception:
                pass
            self.dialog.parametersEntered.connect(self._apply_rectangle_params)
            self.dialog.set_rectangle_mode(True)
            self.dialog.show_dialog(
                self.rect_width or 10.0, self.rect_height or 10.0)
            return
        else:
            self.dialog.set_rectangle_mode(False)
            self.dialog.setWindowTitle("Line Parameters")
            self.dialog.first_input.setPrefix("")
            self.dialog.use_second_cb.show()
            self.dialog.second_input.show()
            self.dialog.angle_buttons_widget.show()
            try:
                self.dialog.parametersEntered.disconnect()
            except Exception:
                pass
            self.dialog.parametersEntered.connect(self.set_parameters)

        key_actions = {
            Qt.Key.Key_Escape: self._handle_escape,
            Qt.Key.Key_L: lambda: self._handle_parameter_dialog(),
            Qt.Key.Key_O: self._toggle_ortho,
            Qt.Key.Key_Enter: self._finish_current_operation,
            Qt.Key.Key_Return: self._finish_current_operation,
            Qt.Key.Key_U: self._undo_point,
            Qt.Key.Key_Backspace: self._undo_point,
            Qt.Key.Key_S: self._toggle_snap,
            Qt.Key.Key_C: self._close_line,
            Qt.Key.Key_A: self._handle_angle_lock,
            Qt.Key.Key_R: self._toggle_shape_mode,
            Qt.Key.Key_Q: self._next_unit,
        }
        if event.key() in key_actions:
            key_actions[event.key()]()

    def _handle_parameter_dialog(self):
        if self.rectangle_mode:
            self.dialog.show_dialog(
                self.rect_width or 10.0, self.rect_height or 10.0)
        else:
            self.dialog.show_dialog(self._current_length())

    def _finish_current_operation(self):
        if self.rectangle_mode:
            if len(self.rect_points) >= 2:
                if self.current_point:
                    if len(self.rect_points) == 2:
                        self.rect_points.append(self.current_point)
                    rect_geom = self._create_rectangle_from_points()
                    if rect_geom:
                        self._add_rectangle_to_layer(rect_geom)
                        show_msg("Rectangle completed!", 1)
                    self._reset_rectangle()
        else:
            self._finish_line()

    def _toggle_rectangle_mode(self):
        self.rectangle_mode = not self.rectangle_mode
        mode = "Rectangle" if self.rectangle_mode else "Line"
        show_msg(f"Mode: {mode}", 2)
        self._reset_rectangle()
        self._safe_reset(rectangle_toggle=True)

    def _apply_rectangle_params(self, width, height, use_width, use_height):
        self.rect_width = width if use_width else 0
        self.rect_height = height if use_height else 0
        self.rect_width_mode = use_width
        self.rect_height_mode = use_height

        mode_parts = []
        if use_width and use_height:
            mode_parts.append("Width & Height fixed")
        elif use_width:
            mode_parts.append("Width fixed")
        elif use_height:
            mode_parts.append("Height fixed")
        else:
            mode_parts.append("Freehand rectangle")

        mode_desc = " | ".join(mode_parts)
        show_msg(f"Rectangle mode: {mode_desc} | Click first corner")

    def _toggle_circle_mode(self):
        self.circle_mode = not self.circle_mode
        mode = "Circle" if self.circle_mode else "Line"
        show_msg(f"Mode: {mode}", 2)
        self.circle_center = None
        self.circle_radius = 0
        self.rubber_band.reset()
        self._safe_reset(circle_toggle=True)

    def _toggle_shape_mode(self):
        if self.circle_mode:
            self.circle_mode = False
            self.rectangle_mode = True
            show_msg("Mode: Rectangle", 2)
            self._reset_rectangle()
            self._safe_reset(rectangle_toggle=True)
        elif self.rectangle_mode:
            self.rectangle_mode = False
            show_msg("Mode: Line", 2)
            self._safe_reset()
        else:
            self.circle_mode = True
            show_msg("Mode: Circle", 2)
            self.circle_center = None
            self.circle_radius = 0
            self.rubber_band.reset()
            self._safe_reset(circle_toggle=True)

    def _handle_escape(self):
        if self._cancel_constraints():
            return

        if self.rectangle_mode:
            if self.rect_points:
                self._reset_rectangle()
                show_msg("Rectangle cancelled", 2)
            return

        if self.circle_mode:
            self.circle_center = None
            self.circle_radius = 0
            self.rubber_band.reset()
            show_msg("Circle cancelled", 2)
            return

        self._safe_reset()
        show_msg("Operation cancelled", 2)

    def _toggle_ortho(self):
        self.ortho_mode = not self.ortho_mode

    def _handle_angle_lock(self):
        if self.rectangle_mode:
            self.rect_angle_lock = not self.rect_angle_lock
            status = "ON" if self.rect_angle_lock else "OFF"
            show_msg(f"Rectangle 90° lock: {status}", 1)
            return

        current_time = time.time()
        al = self.angle_lock

        if current_time - al['last_press'] < 0.5:
            if al['active']:
                al['active'] = False
                al['index'] = 0
                show_msg("Angle lock cancelled")
        else:
            if not al['active']:
                al['active'] = True
                al['index'] = 0
                show_msg(f"Angle lock: {int(math.degrees(al['angles'][0]))}°")
            elif al['index'] == 0:
                al['index'] = 1
                show_msg(f"Angle lock: {int(math.degrees(al['angles'][1]))}°")
            else:
                al['active'] = False
                al['index'] = 0
                show_msg("Angle lock cancelled")

        al['last_press'] = current_time

    def _start_line(self, point, pixel_pos):
        self.start_point = point  # In layer CRS
        self.points = [point]
        self.is_drawing = True
        point_project = self._transform_point_to_project(point)
        self.markers.append(create_marker(
            self.canvas, point_project, is_snappable=True))
        self.rubber_band.reset()
        self.rubber_band.addPoint(point_project)
        show_msg("Line started. Click next point or press L")

    def _apply_circle_radius(self, radius, angle, use_length, use_angle):
        self.circle_radius = radius

        self.dialog.set_rectangle_mode(False)
        self.dialog.use_second_cb.show()
        self.dialog.second_input.show()
        self.dialog.setWindowTitle("Line Parameters")
        self.dialog.first_input.setPrefix("")

        if self.circle_center:
            circle_geom = self._create_circle_geometry(
                self.circle_center, self.circle_radius)
            self._add_circle_to_layer(circle_geom)
            self.circle_center = None
            self.circle_radius = 0
            self.rubber_band.reset()
            show_msg("Circle added!", 1)
        else:
            show_msg("Click to set circle center", 1)

    def _add_circle_to_layer(self, geometry):
        layer = iface.activeLayer()
        if not (layer and layer.isEditable()):
            show_msg("Need editable line layer", 1, Qgis.MessageLevel.Critical)
            return False
        feature = QgsFeature(layer.fields())
        feature.setGeometry(geometry)
        if layer.addFeature(feature):
            layer.updateExtents()
            layer.triggerRepaint()
            self.canvas.refresh()
            return True
        return False

    def _create_circle_geometry(self, center, radius, num_points=64, preview_only=False):
        """Create circle geometry in layer CRS (radius is in meters)"""
        pts = []

        for i in range(num_points + 1):
            angle = 2 * math.pi * i / num_points
            dir_x = math.cos(angle)
            dir_y = math.sin(angle)

            # Convert radius from meters to CRS units for this direction
            radius_crs = self._meters_to_crs_units(
                radius, dir_x, dir_y, center)

            pts.append(QgsPointXY(center.x() + radius_crs *
                       dir_x, center.y() + radius_crs * dir_y))

        if not preview_only:
            return QgsGeometry.fromPolylineXY(pts)
        return pts

    def _add_point(self, point):
        if not self.is_drawing:
            return

        if self.angle_lock['active'] and self.points:
            point = self._apply_angle_lock(point)
        elif self.ortho_mode and self.points:
            point = self._apply_ortho(point)

        self.points.append(point)  # Store in layer CRS
        point_project = self._transform_point_to_project(point)
        self.markers.append(create_marker(
            self.canvas, point_project, is_snappable=True))
        self.rubber_band.addPoint(point_project)
        self.start_point = point

    def _apply_angle_lock(self, point):
        """Apply angle lock with bidirectional support (points in layer CRS)"""
        prev = self.points[-1]

        dx_mouse = point.x() - prev.x()
        dy_mouse = point.y() - prev.y()
        mouse_angle = math.atan2(dx_mouse, dy_mouse)
        cursor_distance = math.hypot(dx_mouse, dy_mouse) or 10.0

        locked_delta = self.angle_lock['angles'][self.angle_lock['index']]

        if len(self.points) < 2:
            if locked_delta == math.pi/2:
                cardinal_angles = [0, math.pi/2, math.pi, 3*math.pi/2]
                normalized_mouse = (mouse_angle + 2*math.pi) % (2*math.pi)

                best_angle = cardinal_angles[0]
                min_diff = float('inf')

                for cardinal in cardinal_angles:
                    diff = abs((normalized_mouse - cardinal + math.pi) %
                               (2*math.pi) - math.pi)
                    if diff < min_diff:
                        min_diff = diff
                        best_angle = cardinal

                final_angle = best_angle

            else:
                normalized_mouse = (mouse_angle + 2*math.pi) % (2*math.pi)
                ns_angles = [math.pi/2, 3*math.pi/2]
                ew_angles = [0, math.pi]

                min_ns_diff = min(abs((normalized_mouse - ang + math.pi) %
                                  (2*math.pi) - math.pi) for ang in ns_angles)
                min_ew_diff = min(abs((normalized_mouse - ang + math.pi) %
                                  (2*math.pi) - math.pi) for ang in ew_angles)

                if min_ns_diff < min_ew_diff:
                    final_angle = math.pi/2 if abs((normalized_mouse - math.pi/2 + math.pi) % (2*math.pi) - math.pi) < abs(
                        (normalized_mouse - 3*math.pi/2 + math.pi) % (2*math.pi) - math.pi) else 3*math.pi/2
                else:
                    final_angle = 0 if abs((normalized_mouse - 0 + math.pi) % (2*math.pi) - math.pi) < abs(
                        (normalized_mouse - math.pi + math.pi) % (2*math.pi) - math.pi) else math.pi

        else:
            prev_prev = self.points[-2]
            dx_ref = prev.x() - prev_prev.x()
            dy_ref = prev.y() - prev_prev.y()
            reference_angle = math.atan2(dx_ref, dy_ref)

            if locked_delta == math.pi/2:
                angle_positive = (reference_angle + math.pi/2) % (2 * math.pi)
                angle_negative = (reference_angle - math.pi/2) % (2 * math.pi)
                normalized_mouse = (mouse_angle + 2*math.pi) % (2*math.pi)

                diff_positive = abs(
                    (normalized_mouse - angle_positive + math.pi) % (2 * math.pi) - math.pi)
                diff_negative = abs(
                    (normalized_mouse - angle_negative + math.pi) % (2 * math.pi) - math.pi)

                final_angle = angle_positive if diff_positive < diff_negative else angle_negative

            else:
                angle_same = reference_angle % (2 * math.pi)
                angle_opposite = (reference_angle + math.pi) % (2 * math.pi)
                normalized_mouse = (mouse_angle + 2*math.pi) % (2*math.pi)

                diff_same = abs((normalized_mouse - angle_same +
                                math.pi) % (2 * math.pi) - math.pi)
                diff_opposite = abs(
                    (normalized_mouse - angle_opposite + math.pi) % (2 * math.pi) - math.pi)

                final_angle = angle_same if diff_same < diff_opposite else angle_opposite

        angle_diff = abs((mouse_angle - final_angle + math.pi) %
                         (2 * math.pi) - math.pi)
        segment_length = cursor_distance * math.cos(angle_diff)
        segment_length = max(segment_length, 0.1)

        return QgsPointXY(
            prev.x() + segment_length * math.sin(final_angle),
            prev.y() + segment_length * math.cos(final_angle)
        )

    def _apply_ortho(self, point):
        """Apply orthogonal snapping (points in layer CRS)"""
        ref = self.start_point
        dx, dy = point.x() - ref.x(), point.y() - ref.y()
        if abs(dx) < 1e-10 and abs(dy) < 1e-10:
            return point

        angle = math.atan2(dx, dy)
        snap_angle = round(angle / (math.pi / 4)) * (math.pi / 4)
        dist = math.hypot(dx, dy)

        return QgsPointXY(
            ref.x() + dist * math.sin(snap_angle),
            ref.y() + dist * math.cos(snap_angle)
        )

    def _update_drawing_preview(self):
        """Update drawing preview (transform to project CRS for display)"""
        if not (self.rubber_band and self.current_point):
            return

        preview_point = self.current_point

        if self.ortho_mode:
            preview_point = self._apply_ortho(preview_point)

        if self.angle_lock['active'] and self.points:
            preview_point = self._apply_angle_lock(preview_point)

        self.rubber_band.reset()
        for pt in self.points:
            pt_project = self._transform_point_to_project(pt)
            self.rubber_band.addPoint(pt_project)

        preview_project = self._transform_point_to_project(preview_point)
        self.rubber_band.addPoint(preview_project)

    def _update_parameter_preview(self):
        if not self.start_point:
            return
        end_point = self._calc_preview_end()
        self.rubber_band.reset()
        for pt in self.points:
            pt_project = self._transform_point_to_project(pt)
            self.rubber_band.addPoint(pt_project)
        end_project = self._transform_point_to_project(end_point)
        self.rubber_band.addPoint(end_project)

    def _calc_preview_end(self):
        """Calculate preview endpoint based on active constraints (in layer CRS)"""
        ref = self.points[-1] if len(self.points) > 1 else self.start_point

        if self.angle_mode and not self.angle_lock['active']:
            final_angle = self.preview_angle
        elif self.angle_lock['active']:
            if len(self.points) > 1:
                dx = self.points[-1].x() - self.points[-2].x()
                dy = self.points[-1].y() - self.points[-2].y()
                base_angle = math.atan2(dx, dy)
            else:
                base_angle = 0.0

            locked_delta = self.angle_lock['angles'][self.angle_lock['index']]

            if self.current_point:
                dx_mouse = self.current_point.x() - ref.x()
                dy_mouse = self.current_point.y() - ref.y()
                mouse_angle = math.atan2(dx_mouse, dy_mouse)

                if locked_delta == math.pi/2:
                    angle_positive = (base_angle + math.pi/2) % (2 * math.pi)
                    angle_negative = (base_angle - math.pi/2) % (2 * math.pi)
                    normalized_mouse = (mouse_angle + 2*math.pi) % (2*math.pi)
                    diff_positive = abs(
                        (normalized_mouse - angle_positive + math.pi) % (2 * math.pi) - math.pi)
                    diff_negative = abs(
                        (normalized_mouse - angle_negative + math.pi) % (2 * math.pi) - math.pi)
                    final_angle = angle_positive if diff_positive < diff_negative else angle_negative
                else:
                    angle_same = base_angle % (2 * math.pi)
                    angle_opposite = (base_angle + math.pi) % (2 * math.pi)
                    normalized_mouse = (mouse_angle + 2*math.pi) % (2*math.pi)
                    diff_same = abs(
                        (normalized_mouse - angle_same + math.pi) % (2 * math.pi) - math.pi)
                    diff_opposite = abs(
                        (normalized_mouse - angle_opposite + math.pi) % (2 * math.pi) - math.pi)
                    final_angle = angle_same if diff_same < diff_opposite else angle_opposite
            else:
                final_angle = (base_angle + locked_delta) % (2*math.pi)
        else:
            if self.current_point:
                dx = self.current_point.x() - ref.x()
                dy = self.current_point.y() - ref.y()
                final_angle = math.atan2(
                    dx, dy) if math.hypot(dx, dy) > 0 else 0.0
            else:
                final_angle = 0.0

        # Determine length in meters
        if self.length_mode:
            length_meters = self.preview_length
        else:
            if self.current_point:
                length_meters = self._calculate_distance_in_layer_crs(
                    ref, self.current_point) or 10.0
            else:
                length_meters = 10.0

        # Convert length from meters to CRS units
        dir_x = math.sin(final_angle)
        dir_y = math.cos(final_angle)
        length_crs = self._meters_to_crs_units(
            length_meters, dir_x, dir_y, ref)

        return QgsPointXY(
            ref.x() + length_crs * dir_x,
            ref.y() + length_crs * dir_y
        )

    def _check_vertex_snap(self, canvas_pos):
        """Check for snapping to custom vertices (markers)"""
        config = QgsProject.instance().snappingConfig()

        if not config.enabled() or not self.markers:
            return None

        snap_tolerance = config.tolerance()
        if snap_tolerance <= 0:
            snap_tolerance = 12

        map_pos = self.toMapCoordinates(canvas_pos)
        min_distance = float('inf')
        snap_point = None

        for marker in self.markers:
            if not marker.data(0):
                continue

            if not marker.isVisible():
                continue

            marker_pos = marker.center()
            marker_pixel = self.toCanvasCoordinates(marker_pos)
            pixel_distance = math.hypot(
                canvas_pos.x() - marker_pixel.x(),
                canvas_pos.y() - marker_pixel.y()
            )

            if pixel_distance < snap_tolerance:
                distance = math.hypot(
                    map_pos.x() - marker_pos.x(),
                    map_pos.y() - marker_pos.y()
                )

                if distance < min_distance:
                    min_distance = distance
                    snap_point = marker_pos

        return snap_point

    def _get_snap_point(self, canvas_pos):
        """Get snapped point using QGIS snapping (returns point in project CRS)"""
        config = QgsProject.instance().snappingConfig()

        if not config.enabled():
            return None, None

        self.snapping.setConfig(config)
        map_pos = self.toMapCoordinates(canvas_pos)
        snap_match = self.snapping.snapToMap(map_pos)

        snaps = []

        if snap_match.isValid():
            snap_type = 'vertex' if snap_match.type() == QgsPointLocator.Vertex else 'segment'
            snaps.append({'point': snap_match.point(
            ), 'match': snap_match, 'source': 'layer', 'snap_type': snap_type})

        marker_snap_point = self._check_vertex_snap(canvas_pos)
        if marker_snap_point:
            snaps.append({'point': marker_snap_point, 'match': None,
                         'source': 'marker', 'snap_type': 'vertex'})

        # add this  'config.selfSnapping() != 0 and'    to control via snapping  self snapping  option
        if self.is_drawing and len(self.points) > 1:
            # Transform points to project CRS for self-snapping check
            points_project = [self._transform_point_to_project(
                pt) for pt in self.points]
            current_line_geom = QgsGeometry.fromPolylineXY(points_project)

            if not current_line_geom.isEmpty():
                dist_sq, closest_pt, after_vertex, _ = current_line_geom.closestSegmentWithContext(
                    map_pos)

                # Use pixel-based tolerance for better accuracy in all CRS types
                tolerance_pixels = config.tolerance()
                closest_canvas = self.toCanvasCoordinates(closest_pt)
                pixel_dist = math.hypot(
                    canvas_pos.x() - closest_canvas.x(),
                    canvas_pos.y() - closest_canvas.y()
                )

                if pixel_dist < tolerance_pixels:
                    is_vertex = False
                    vertex_tolerance_pixels = tolerance_pixels * 0.8  # Slightly tighter for vertices

                    for p in points_project:
                        p_canvas = self.toCanvasCoordinates(p)
                        p_pixel_dist = math.hypot(
                            closest_canvas.x() - p_canvas.x(),
                            closest_canvas.y() - p_canvas.y()
                        )
                        if p_pixel_dist < vertex_tolerance_pixels:
                            is_vertex = True
                            break

                    snap_type = 'vertex' if is_vertex else 'segment'

                    # Only add if not snapping to the last segment being drawn
                    if after_vertex < len(points_project) - 1:
                        snaps.append(
                            {'point': closest_pt, 'match': None, 'source': 'self', 'snap_type': snap_type})
                    elif after_vertex == len(points_project) - 1:
                        # Check if we're not snapping to the current drawing point
                        last_point_canvas = self.toCanvasCoordinates(
                            points_project[-1])
                        dist_to_last = math.hypot(
                            closest_canvas.x() - last_point_canvas.x(),
                            closest_canvas.y() - last_point_canvas.y()
                        )
                        if dist_to_last > 2:  # More than 2 pixels away from last point
                            snaps.append(
                                {'point': closest_pt, 'match': None, 'source': 'self', 'snap_type': snap_type})

        if not snaps:
            return None, None

        closest_snap = None
        min_dist_sq = float('inf')

        # Use pixel distance for comparison
        for snap in snaps:
            snap_canvas_pos = self.toCanvasCoordinates(snap['point'])
            dist_sq = (snap_canvas_pos.x() - canvas_pos.x()) ** 2 + \
                (snap_canvas_pos.y() - canvas_pos.y()) ** 2

            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_snap = snap

        if closest_snap:
            return closest_snap.get('point'), closest_snap

        return None, None

    def _update_cursor_info(self, canvas_pos):
        """Update cursor info display"""
        config = QgsProject.instance().snappingConfig()
        snap_status = "ON" if config.enabled() else "OFF"
        if self.is_vertex_snap:
            snap_status += " + Vertex"
        elif self.is_segment_snap:
            snap_status += " + Segment"

        length = angle = None
        unit_suffix = self.units[self.current_unit_key]['suffix']

        if self.start_point and self.current_point:
            if self.length_mode or self.angle_mode:
                end_point = self._calc_preview_end()
                ref_point = self.points[-1] if len(
                    self.points) > 1 else self.start_point
                # Use proper distance calculation
                length_meters = self._calculate_distance_in_layer_crs(
                    ref_point, end_point)
                length = length_meters / \
                    self.units[self.current_unit_key]['factor']
                # Angle calculation is OK with simple math
                dx = end_point.x() - ref_point.x()
                dy = end_point.y() - ref_point.y()
                angle = math.atan2(dx, dy)
            else:
                ref_point = self.points[-1] if self.is_drawing and len(
                    self.points) > 1 else self.start_point
                # Use proper distance calculation
                length_meters = self._calculate_distance_in_layer_crs(
                    ref_point, self.current_point)
                length = length_meters / \
                    self.units[self.current_unit_key]['factor']
                dx = self.current_point.x() - ref_point.x()
                dy = self.current_point.y() - ref_point.y()
                angle = math.atan2(dx, dy) if length_meters > 0 else 0

        mode_parts = []

        if self.length_mode and self.angle_mode:
            mode_parts.append("L&A Preview")
        elif self.length_mode:
            mode_parts.append("Length Preview")
        elif self.angle_mode:
            mode_parts.append("Angle Preview")
        elif self.ortho_mode:
            mode_parts.append("Ortho")
        elif self.is_drawing:
            mode_parts.append("Drawing")
        else:
            mode_parts.append("Ready")

        if self.angle_lock['active']:
            lock_deg = int(math.degrees(
                self.angle_lock['angles'][self.angle_lock['index']]))
            mode_parts.append(f"Lock{lock_deg}°")

        if self.length_mode or self.angle_mode:
            mode_parts.append("(Esc/RClick to cancel)")

        mode = " | ".join(mode_parts)

        self.cursor_info.updateInfo(
            length=length, angle=angle, coordinates=self.current_point,
            mode=f"{mode} | Snap: {snap_status} | Unit: {self.units[self.current_unit_key]['name']}",
            canvas_pos=QPointF(canvas_pos), unit_suffix=unit_suffix
        )

    def set_parameters(self, length_meters, angle, use_length, use_angle):
        """Handle parameter input"""
        if not self.start_point:
            self.preview_length = length_meters if use_length else 0
            self.preview_angle = angle if use_angle else 0
            self.length_mode = use_length
            self.angle_mode = use_angle

            if use_angle:
                self.angle_lock['active'] = False
                show_msg("Angle lock cleared - using input angle")

            mode_parts = []
            if use_length and use_angle:
                mode_parts.append("Length & Angle")
            elif use_length:
                mode_parts.append("Length only")
            elif use_angle:
                mode_parts.append("Angle only")

            mode_desc = " | ".join(
                mode_parts) if mode_parts else "Free drawing"
            show_msg(f"Mode: {mode_desc} | Click to set start point")
            return

        self.preview_length = length_meters if use_length else 0
        self.preview_angle = angle if use_angle else 0
        self.length_mode = use_length
        self.angle_mode = use_angle

        if use_angle:
            self.angle_lock['active'] = False
            show_msg("Angle lock cleared - using input angle")

        show_msg("Move mouse and click to confirm | Right-click or Esc to cancel")

    def _confirm_preview(self):
        if not self.start_point:
            return
        end_point = self._calc_preview_end()
        dx, dy = end_point.x() - self.start_point.x(), end_point.y() - self.start_point.y()
        self.last_angle = math.atan2(dx, dy)

        self.points.append(end_point)
        end_project = self._transform_point_to_project(end_point)
        self.markers.append(create_marker(
            self.canvas, end_project, is_snappable=True))
        self.start_point = end_point

        # Use proper distance calculation
        length_meters = self._calculate_distance_in_layer_crs(
            self.points[-2], end_point)
        length_display = length_meters / \
            self.units[self.current_unit_key]['factor']
        unit_suffix = self.units[self.current_unit_key]['suffix']
        show_msg(f"Point added! Length: {length_display:.3f}{unit_suffix}", 1)

        self._cancel_preview()

    def _cancel_preview(self):
        self.length_mode = self.angle_mode = False
        self.preview_length = self.preview_angle = 0
        if self.is_drawing:
            self._update_drawing_preview()
        else:
            self.rubber_band.reset()

    def _finish_line(self):
        if not (self.is_drawing and len(self.points) >= 2):
            self._safe_reset()
            return

        if self._add_to_layer():
            total_meters = sum(
                self._calculate_distance_in_layer_crs(
                    self.points[i], self.points[i+1])
                for i in range(len(self.points)-1)
            )
            total_display = total_meters / \
                self.units[self.current_unit_key]['factor']
            unit_suffix = self.units[self.current_unit_key]['suffix']
            show_msg(
                f"Line completed. Length: {total_display:.3f}{unit_suffix}", 1)
        else:
            show_msg("Failed to add line", 1, Qgis.MessageLevel.Critical)
        self._safe_reset()

    def _add_to_layer(self):
        """Add line to layer (points already in layer CRS)"""
        layer = iface.activeLayer()
        if not (layer and layer.type() == QgsMapLayer.LayerType.VectorLayer and
                layer.geometryType() == QgsWkbTypes.GeometryType.LineGeometry and layer.isEditable()) or len(self.points) < 2:
            return False

        # Points are already in layer CRS, so create geometry directly
        geometry = QgsGeometry.fromPolylineXY(self.points)
        if geometry.isEmpty():
            return False

        feature = QgsFeature(layer.fields())
        feature.setGeometry(geometry)

        if layer.addFeature(feature):
            layer.updateExtents()
            self.canvas.refresh()

            layer_crs = layer.crs()
            project_crs = self._get_project_crs()
            if layer_crs != project_crs:
                show_msg(
                    f"Line added in layer CRS: {layer_crs.authid()}", 3, Qgis.MessageLevel.Info)

            return True
        return False

    def _close_line(self):
        if self.is_drawing and len(self.points) >= 3:
            self.points.append(self.points[0])
            point_project = self._transform_point_to_project(self.points[0])
            self.markers.append(create_marker(
                self.canvas, point_project, QColor(255, 255, 0), is_snappable=True))
            self._finish_line()

    def _undo_point(self):
        if self.rectangle_mode and self.rect_points:
            self.rect_points.pop()
            if self.markers:
                marker = self.markers.pop()
                if marker.color() in [QColor(255, 165, 0), QColor(255, 255, 0), QColor(0, 255, 255)]:
                    marker.hide()
            self.rubber_band.reset()
            show_msg(
                f"Rectangle point removed. {len(self.rect_points)} points remaining.", 1)
        elif self.is_drawing and len(self.points) > 1:
            self.points.pop()
            if self.markers:
                self.markers.pop().hide()
            self.rubber_band.reset()
            for pt in self.points:
                pt_project = self._transform_point_to_project(pt)
                self.rubber_band.addPoint(pt_project)
            self.start_point = self.points[-1]
            show_msg("Point removed", 1)

    def _toggle_snap(self):
        """Toggle QGIS snapping on/off"""
        project = QgsProject.instance()
        config = project.snappingConfig()
        config.setEnabled(not config.enabled())
        project.setSnappingConfig(config)
        self.snapping.setConfig(config)
        show_msg(f"Snap: {'ON' if config.enabled() else 'OFF'}", 2)

    def _handle_right_click(self):
        """Context-sensitive right-click behavior"""
        if self.length_mode or self.angle_mode or self.rect_width_mode or self.rect_height_mode:
            self._cancel_constraints()
        elif self.rectangle_mode and len(self.rect_points) >= 2:
            self._finish_current_operation()
        elif self.is_drawing:
            self._finish_line()
        else:
            self._handle_parameter_dialog()

    def _current_length(self):
        if self.start_point and self.current_point:
            return self._calculate_distance_in_layer_crs(self.start_point, self.current_point)
        return 10.0

    def _valid_layer(self):
        layer = iface.activeLayer()
        if not (layer and layer.type() == QgsMapLayer.LayerType.VectorLayer and
                layer.geometryType() == QgsWkbTypes.GeometryType.LineGeometry and layer.isEditable()):
            show_msg("Need editable line layer", 1, Qgis.MessageLevel.Critical)
            return False
        return True

    def _safe_reset(self, circle_toggle=False, rectangle_toggle=False):
        if hasattr(self, 'cursor_info'):
            self.cursor_info.safe_hide()
        if hasattr(self, 'rubber_band'):
            self.rubber_band.reset()
        for m in getattr(self, 'markers', []):
            m.hide()

        if hasattr(self, 'snap_indicator'):
            self.snap_indicator.setMatch(QgsPointLocator.Match())

        self.is_drawing = False
        self.ortho_mode = False
        self.points = []
        self.start_point = None
        self.current_point = None
        self.current_snap_point = None
        self.markers = []
        self.length_mode = False
        self.angle_mode = False
        self.preview_length = 0
        self.preview_angle = 0
        self.last_angle = 0
        self.angle_lock = {
            'active': False,
            'index': 0,
            'angles': [math.pi/2, math.pi],
            'last_press': 0
        }
        if not circle_toggle:
            self.circle_mode = False
            self.circle_center = None
            self.circle_radius = 0
        if not rectangle_toggle:
            self.rectangle_mode = False
            self.rect_points = []
            self.rect_width = 0
            self.rect_height = 0
            self.rect_width_mode = False
            self.rect_height_mode = False
            self.rect_angle_lock = True

    def deactivate(self):
        self._safe_reset()
        if hasattr(self, 'cursor_info'):
            self.cursor_info.close()
        if hasattr(self, 'dialog'):
            self.dialog.close()
        if hasattr(self, 'snap_indicator'):
            self.snap_indicator.setMatch(QgsPointLocator.Match())
        super().deactivate()


def activate_tool():
    layer = iface.activeLayer()
    if not (layer and layer.type() == QgsMapLayer.LayerType.VectorLayer and
            layer.geometryType() == QgsWkbTypes.GeometryType.LineGeometry and layer.isEditable()):
        show_msg("Need editable line layer", 1, Qgis.MessageLevel.Critical)
        return None

    canvas = iface.mapCanvas()
    tool = ProfessionalLineTool(canvas)
    canvas.setMapTool(tool)
    snap = "ON" if QgsProject.instance().snappingConfig().enabled() else "OFF"
    show_msg(
        f"🖱️ Left: Add | Right: Finish | L: Params | O: Ortho | Q: Toggle Units | U: Undo | C: Close | S: Snap({snap}) | A: Angle Lock | R: Circle, Rectangle | Esc: Cancel", 2, Qgis.MessageLevel.Success)
    return tool


# activate_tool()

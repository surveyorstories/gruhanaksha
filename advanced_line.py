import math
import time
from qgis.PyQt.QtCore import Qt, pyqtSignal, QPointF, QTimer
from qgis.PyQt.QtGui import QColor, QPainter
from qgis.PyQt.QtWidgets import *
from qgis.core import *
from qgis.gui import QgsMapTool, QgsRubberBand, QgsVertexMarker
from qgis.utils import iface


class CursorInfo(QWidget):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.text_lines = []
        self.is_active = True

        # Qt5/Qt6 compatible window flags
        if hasattr(Qt, 'WindowType'):
            # Qt6
            self.setWindowFlags(
                Qt.WindowType.Tool |
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.WindowDoesNotAcceptFocus
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        else:
            # Qt5
            self.setWindowFlags(
                Qt.Tool |
                Qt.FramelessWindowHint |
                Qt.WindowStaysOnTopHint |
                Qt.WindowDoesNotAcceptFocus
            )
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setAttribute(Qt.WA_DeleteOnClose)

        self.setStyleSheet(
            "QWidget{background:rgba(240,248,255,230);border:2px solid #2E86AB;border-radius:6px;padding:6px;font:bold 10pt Consolas;color:#3dfcff}")

        # Focus tracking
        self.cleanup_timer = QTimer(self)
        self.cleanup_timer.setSingleShot(True)
        self.cleanup_timer.timeout.connect(self.safe_hide)

        app = QApplication.instance()
        if app:
            app.focusChanged.connect(self.on_focus_changed)
        self.hide()

    def on_focus_changed(self, old_widget, new_widget):
        try:
            if new_widget is not None and self._is_canvas_widget(new_widget):
                if self.text_lines and self.is_active:
                    self.show()
            else:
                self.safe_hide()
        except Exception:
            pass

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

        # Add width and height for rectangles
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
        app = QApplication.instance()
        if app:
            try:
                app.focusChanged.disconnect(self.on_focus_changed)
            except TypeError:
                pass
        event.accept()


qgis_main_window = iface.mainWindow()


class ParameterDialog(QDialog):
    # For lines: length, angle, use_length, use_angle
    # For rectangles: width, height, use_width, use_height
    parametersEntered = pyqtSignal(float, float, bool, bool)

    def __init__(self, units_dict, current_unit_key='m'):
        super().__init__()
        self.units = units_dict
        self.current_unit_key = current_unit_key
        self.is_rectangle_mode = False
        self.setWindowTitle("Line Parameters")
        self.setModal(False)

        layout = QVBoxLayout(self)

        # Unit selection
        unit_layout = QHBoxLayout()
        unit_layout.addWidget(QLabel("Unit:"))
        self.unit_combo = QComboBox()
        for key, unit_info in self.units.items():
            self.unit_combo.addItem(unit_info['name'], key)
        self.unit_combo.setCurrentText(self.units[current_unit_key]['name'])
        self.unit_combo.currentTextChanged.connect(self.on_unit_changed)
        unit_layout.addWidget(self.unit_combo)
        layout.addLayout(unit_layout)

        # First parameter input with checkbox (Length/Width)
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

        # Second parameter input with checkbox (Angle/Height)
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

        # Quick angle buttons (only visible in line mode)
        self.angle_buttons_widget = QWidget()
        self.grid = QGridLayout(self.angle_buttons_widget)
        for i, angle in enumerate([0, 45, 90, 135, 180, 225, 270, 315]):
            btn = QPushButton(f"{angle}°")
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _, a=angle: self.set_quick_angle(a))
            self.grid.addWidget(btn, i // 4, i % 4)
        layout.addWidget(self.angle_buttons_widget)

        # Buttons
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("Apply")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept_parameters)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(QPushButton("Cancel", clicked=self.close))
        layout.addLayout(btn_layout)

        # Validation warning label
        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet("color: red; font-weight: bold;")
        self.warning_label.hide()
        layout.addWidget(self.warning_label)

    def set_rectangle_mode(self, is_rectangle):
        """Switch between line and rectangle parameter modes"""
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

            # Convert first input
            current_value = self.first_input.value()
            meters_value = current_value * old_factor
            new_value = meters_value / new_factor
            self.first_input.setValue(new_value)

            # Convert second input if it's a dimension (rectangle mode)
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
            first_in_meters,
            second_in_meters,
            use_first,
            use_second
        )
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


def create_marker(canvas, point, color=QColor(0, 255, 0)):
    marker = QgsVertexMarker(canvas)
    marker.setCenter(point)
    marker.setColor(color)
    marker.setIconType(QgsVertexMarker.IconType.ICON_BOX)
    marker.setIconSize(12)
    marker.setPenWidth(2)
    return marker


def show_msg(msg, duration=2, level=Qgis.MessageLevel.Info):
    if iface and iface.messageBar():
        iface.messageBar().pushMessage("📐 Line Tool", msg, level=level, duration=duration)


class ProfessionalLineTool(QgsMapTool):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.reset_state()

        # UI Components
        self.rubber_band = QgsRubberBand(
            canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.rubber_band.setColor(QColor("brown"))
        self.rubber_band.setWidth(1.5)
        self.rubber_band.setLineStyle(Qt.PenStyle.DashLine)

        self.snap_marker = QgsVertexMarker(canvas)
        self.snap_marker.setIconType(QgsVertexMarker.IconType.ICON_BOX)
        self.snap_marker.setColor(QColor(255, 0, 255))
        self.snap_marker.setPenWidth(3)
        self.snap_marker.setIconSize(12)
        self.snap_marker.hide()

        self.cursor_info = CursorInfo(canvas)
        self.snapping = QgsSnappingUtils()
        self.snapping.setMapSettings(self.canvas.mapSettings())
        self.snapping.setCurrentLayer(None)

        # Snap tolerance for custom vertex snapping (in pixels)
        self.vertex_snap_tolerance = 15

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

        # Create dialog with units support
        self.dialog = ParameterDialog(self.units, self.current_unit_key)
        try:
            # For Qt6
            self.dialog.setParent(iface.mainWindow(), Qt.WindowType.Window)
        except AttributeError:
            # For Qt5
            self.dialog.setParent(iface.mainWindow(), Qt.Window)
        self.dialog.parametersEntered.connect(self.set_parameters)

    def _set_current_unit(self, key):
        if key in self.units:
            self.current_unit_key = key
            self.current_unit_index = self.unit_keys.index(key)
            # Update dialog's current unit
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
        self.markers = []
        self.preview_length = 0
        self.preview_angle = 0
        self.length_mode = False
        self.angle_mode = False
        self.last_angle = 0
        # Updated angle_lock with only 90° and 180° options
        self.angle_lock = {'active': False, 'index': 0, 'angles': [
            math.pi/2, math.pi], 'last_press': 0}

        # Circle mode props
        self.circle_mode = False
        self.circle_center = None
        self.circle_radius = 0

        # Rectangle mode props
        self.rectangle_mode = False
        self.rect_points = []  # Will store 1-3 points for rectangle construction
        self.rect_width = 0
        self.rect_height = 0
        self.rect_width_mode = False
        self.rect_height_mode = False
        self.rect_angle_lock = True  # Start with angle lock ON for rectangles

    def activate(self):
        self.canvas.setCursor(Qt.CursorShape.CrossCursor)

    def canvasPressEvent(self, event):
        if not self._valid_layer():
            return

        point = self._get_snap_point(
            event.pos()) or self.toMapCoordinates(event.pos())

        if self.circle_mode:
            self._handle_circle_click(point, event.pos(), event)
            return

        if self.rectangle_mode:
            self._handle_rectangle_click(point, event.pos(), event)
            return

        # Regular line mode handling
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
        """Handle rectangle drawing with 3-point method or parameter constraints"""
        if event.button() == Qt.MouseButton.LeftButton:
            if len(self.rect_points) == 0:
                # First point
                self.rect_points.append(point)
                self.markers.append(create_marker(
                    self.canvas, point, QColor(255, 165, 0)))
                show_msg("Rectangle corner set. Click second corner.", 2)
            elif len(self.rect_points) == 1:
                # Second point - check if we should use parameter-driven mode
                if self.rect_width_mode or self.rect_height_mode:
                    # Parameter-driven rectangle - create immediately
                    # Temporarily add second point
                    self.rect_points.append(point)
                    rect_geom = self._create_rectangle_from_params(point)
                    if rect_geom:
                        self._add_rectangle_to_layer(rect_geom)
                        show_msg("Rectangle added!", 1)
                    self._reset_rectangle()
                else:
                    # Freehand mode - add second point and wait for third
                    self.rect_points.append(point)
                    self.markers.append(create_marker(
                        self.canvas, point, QColor(255, 255, 0)))
                    show_msg(
                        "Second corner set. Click third corner to complete rectangle.", 2)
            elif len(self.rect_points) == 2:
                # Third point - complete rectangle
                if self.rect_width_mode or self.rect_height_mode:
                    # If constraints were applied after placing 2 points, use parameter mode
                    rect_geom = self._create_rectangle_from_constraints()
                    if rect_geom:
                        self._add_rectangle_to_layer(rect_geom)
                        show_msg("Rectangle added!", 1)
                else:
                    # Normal 3-point completion
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
        """Handle circle drawing clicks"""
        if self.circle_center is None:
            self.circle_center = point
            if self.circle_radius:  # If radius is already known, create immediately
                circle_geom = self._create_circle_geometry(
                    self.circle_center, self.circle_radius)
                self._add_circle_to_layer(circle_geom)
                # Reset circle parameters after creating circle
                self.circle_center = None
                self.circle_radius = 0
                self.rubber_band.reset()
                show_msg("Circle added!", 1)
            else:
                show_msg(
                    "Circle center set. Move and click to set radius or press L.", 2)
        else:
            radius = math.hypot(
                point.x() - self.circle_center.x(), point.y() - self.circle_center.y())
            circle_geom = self._create_circle_geometry(
                self.circle_center, radius)
            self._add_circle_to_layer(circle_geom)
            # Reset circle parameters after creating circle
            self.circle_center = None
            self.circle_radius = 0
            self.rubber_band.reset()
            show_msg("Circle added!", 2)

    def canvasMoveEvent(self, event):
        if self.circle_mode and self.circle_center:
            self._handle_circle_move(event)
            return

        if self.rectangle_mode:
            self._handle_rectangle_move(event)
            return

        # Handle snapping for line mode
        self.snap_marker.hide()
        config = QgsProject.instance().snappingConfig()
        self.snapping.setConfig(config)
        self.snapping.setMapSettings(self.canvas.mapSettings())

        # Get both snapped and unsnapped points
        snap_point = self._get_snap_point(
            event.pos()) if config.enabled() else None
        map_point = self.toMapCoordinates(event.pos())

        # Store both points for use in drawing
        self.current_snap_point = snap_point
        self.current_point = snap_point or map_point

        if snap_point:
            self.snap_marker.setCenter(snap_point)
            self.snap_marker.show()

        if self.length_mode or self.angle_mode:
            self._update_parameter_preview()
        elif self.is_drawing and self.start_point:
            self._update_drawing_preview()
        self._update_cursor_info(event.pos())

    def _handle_rectangle_move(self, event):
        """Handle mouse movement in rectangle mode"""
        point = self._get_snap_point(
            event.pos()) or self.toMapCoordinates(event.pos())
        self.current_point = point

        # Update snap marker
        snap_point = self._get_snap_point(event.pos())
        if snap_point:
            self.snap_marker.setCenter(snap_point)
            self.snap_marker.show()
        else:
            self.snap_marker.hide()

        if self.rect_width_mode or self.rect_height_mode:
            # Parameter-driven rectangle preview
            if len(self.rect_points) == 1:
                rect_pts = self._calculate_rectangle_preview(point)
                if rect_pts:
                    self.rubber_band.reset()
                    for pt in rect_pts:
                        self.rubber_band.addPoint(pt)
                    self.rubber_band.addPoint(
                        rect_pts[0])  # Close the rectangle
            elif len(self.rect_points) == 2:
                # Show constrained preview from existing 2 points
                rect_pts = self._get_constrained_rectangle_preview()
                if rect_pts:
                    self.rubber_band.reset()
                    for pt in rect_pts:
                        self.rubber_band.addPoint(pt)
                    self.rubber_band.addPoint(
                        rect_pts[0])  # Close the rectangle
        else:
            # Freehand rectangle preview
            if len(self.rect_points) == 1:
                # Preview line from first point to current
                self.rubber_band.reset()
                self.rubber_band.addPoint(self.rect_points[0])
                self.rubber_band.addPoint(point)
            elif len(self.rect_points) == 2:
                # Preview rectangle from 2 points
                rect_pts = self._calculate_partial_rectangle_with_constraints(
                    point)
                if rect_pts:
                    self.rubber_band.reset()
                    for pt in rect_pts:
                        self.rubber_band.addPoint(pt)
                    self.rubber_band.addPoint(
                        rect_pts[0])  # Close the rectangle

        self._update_rectangle_cursor_info(event.pos())

    def _handle_circle_move(self, event):
        """Handle mouse movement in circle mode"""
        point = self._get_snap_point(
            event.pos()) or self.toMapCoordinates(event.pos())
        radius = math.hypot(point.x() - self.circle_center.x(),
                            point.y() - self.circle_center.y())
        circle_pts = self._create_circle_geometry(
            self.circle_center, radius, preview_only=True)
        self.rubber_band.reset()
        for pt in circle_pts:
            self.rubber_band.addPoint(pt)
        # Show radius in current units
        radius_in_display_units = radius / \
            self.units[self.current_unit_key]['factor']
        unit_suffix = self.units[self.current_unit_key]['suffix']

        # But pass the radius in meters to updateInfo for internal consistency
        self.cursor_info.updateInfo(
            length=radius,
            angle=None,
            coordinates=point,
            mode=f"Circle | Snap: {'ON' if QgsProject.instance().snappingConfig().enabled() else 'OFF'}",
            canvas_pos=event.pos(),
            label="Radius",
            unit_suffix=unit_suffix
        )

    def _calculate_rectangle_preview(self, current_point):
        """Calculate rectangle points for parameter-driven mode"""
        if not self.rect_points:
            return None

        corner1 = self.rect_points[0]

        # Calculate direction from first corner to current point
        dx = current_point.x() - corner1.x()
        dy = current_point.y() - corner1.y()

        if abs(dx) < 1e-10 and abs(dy) < 1e-10:
            return None

        # Normalize direction
        dist = math.hypot(dx, dy)
        if dist < 1e-10:
            return None

        dir_x = dx / dist
        dir_y = dy / dist

        # Perpendicular direction
        perp_x = -dir_y
        perp_y = dir_x

        # Use specified width and height or current mouse position
        width = self.rect_width if self.rect_width_mode else dist
        height = self.rect_height if self.rect_height_mode else dist * \
            0.5  # Default aspect ratio

        # Calculate rectangle corners
        corner2 = QgsPointXY(corner1.x() + width * dir_x,
                             corner1.y() + width * dir_y)
        corner3 = QgsPointXY(corner2.x() + height * perp_x,
                             corner2.y() + height * perp_y)
        corner4 = QgsPointXY(corner1.x() + height * perp_x,
                             corner1.y() + height * perp_y)

        return [corner1, corner2, corner3, corner4]

    def _calculate_partial_rectangle_with_constraints(self, third_point):
        """Calculate rectangle from 2 points + constraints, handling parameter mode"""
        if len(self.rect_points) < 2:
            return None

        p1, p2 = self.rect_points[0], self.rect_points[1]

        # If width/height constraints are active, use parameter-driven calculation
        if self.rect_width_mode or self.rect_height_mode:
            # Get the first edge vector (p1 to p2)
            edge1_x = p2.x() - p1.x()
            edge1_y = p2.y() - p1.y()
            edge1_length = math.hypot(edge1_x, edge1_y)

            if edge1_length < 1e-10:
                return None

            # Normalize first edge direction
            dir_x = edge1_x / edge1_length
            dir_y = edge1_y / edge1_length

            # Perpendicular direction
            perp_x = -dir_y
            perp_y = dir_x

            # Use constraints or current edge length
            width = self.rect_width if self.rect_width_mode else edge1_length
            height = self.rect_height if self.rect_height_mode else edge1_length * 0.6

            # Recalculate p2 if width is constrained
            if self.rect_width_mode:
                p2 = QgsPointXY(p1.x() + width * dir_x, p1.y() + width * dir_y)

            # Calculate other corners based on constraints
            p3 = QgsPointXY(p2.x() + height * perp_x, p2.y() + height * perp_y)
            p4 = QgsPointXY(p1.x() + height * perp_x, p1.y() + height * perp_y)

            return [p1, p2, p3, p4]

        # Regular freehand mode with angle lock
        p3 = third_point

        # Apply angle lock constraint if active for rectangles
        if self.rect_angle_lock:
            # Get the first edge vector (p1 to p2)
            edge1_x = p2.x() - p1.x()
            edge1_y = p2.y() - p1.y()
            edge1_length = math.hypot(edge1_x, edge1_y)

            if edge1_length > 1e-10:
                # Normalize first edge
                edge1_dir_x = edge1_x / edge1_length
                edge1_dir_y = edge1_y / edge1_length

                # Calculate perpendicular direction (90 degrees)
                perp_dir_x = -edge1_dir_y
                perp_dir_y = edge1_dir_x

                # Get mouse direction from p1
                mouse_dx = p3.x() - p1.x()
                mouse_dy = p3.y() - p1.y()
                mouse_dist = math.hypot(mouse_dx, mouse_dy)

                if mouse_dist > 1e-10:
                    # Project mouse direction onto the perpendicular
                    proj_length = mouse_dx * perp_dir_x + mouse_dy * perp_dir_y

                    # Constrain p3 to be perpendicular to the first edge
                    p3 = QgsPointXY(
                        p1.x() + proj_length * perp_dir_x,
                        p1.y() + proj_length * perp_dir_y
                    )

        # Calculate the fourth corner to make a rectangle
        # Vector from p1 to p2
        v12_x = p2.x() - p1.x()
        v12_y = p2.y() - p1.y()

        # Vector from p1 to p3
        v13_x = p3.x() - p1.x()
        v13_y = p3.y() - p1.y()

        # Fourth point is p2 + vector from p1 to p3
        p4 = QgsPointXY(p2.x() + v13_x, p2.y() + v13_y)

        return [p1, p2, p4, p3]

    def _create_rectangle_from_points(self):
        """Create rectangle geometry from 3 points with constraints and angle lock support"""
        if len(self.rect_points) != 3:
            return None

        p1, p2, p3 = self.rect_points

        # If width/height constraints are active, recalculate using constraints
        if self.rect_width_mode or self.rect_height_mode:
            return self._create_rectangle_from_params(p3)

        # Apply angle lock constraint to p3 if it was active when p3 was placed
        if self.rect_angle_lock:
            # Get the first edge vector (p1 to p2)
            edge1_x = p2.x() - p1.x()
            edge1_y = p2.y() - p1.y()
            edge1_length = math.hypot(edge1_x, edge1_y)

            if edge1_length > 1e-10:
                # Normalize first edge
                edge1_dir_x = edge1_x / edge1_length
                edge1_dir_y = edge1_y / edge1_length

                # Calculate perpendicular direction (90 degrees)
                perp_dir_x = -edge1_dir_y
                perp_dir_y = edge1_dir_x

                # Get original direction from p1 to p3
                orig_dx = p3.x() - p1.x()
                orig_dy = p3.y() - p1.y()

                # Project onto perpendicular direction
                proj_length = orig_dx * perp_dir_x + orig_dy * perp_dir_y

                # Constrain p3 to be perpendicular
                p3 = QgsPointXY(
                    p1.x() + proj_length * perp_dir_x,
                    p1.y() + proj_length * perp_dir_y
                )

        # Calculate fourth corner
        v12_x = p2.x() - p1.x()
        v12_y = p2.y() - p1.y()
        v13_x = p3.x() - p1.x()
        v13_y = p3.y() - p1.y()

        p4 = QgsPointXY(p2.x() + v13_x, p2.y() + v13_y)

        # Create closed polygon
        rectangle_points = [p1, p2, p4, p3, p1]  # Close the polygon
        return QgsGeometry.fromPolylineXY(rectangle_points)

    def _get_constrained_rectangle_preview(self):
        """Get constrained rectangle preview from 2 existing points"""
        if len(self.rect_points) != 2:
            return None

        p1, p2 = self.rect_points[0], self.rect_points[1]

        # Get the first edge vector (p1 to p2)
        edge1_x = p2.x() - p1.x()
        edge1_y = p2.y() - p1.y()
        edge1_length = math.hypot(edge1_x, edge1_y)

        if edge1_length < 1e-10:
            return None

        # Normalize first edge direction
        dir_x = edge1_x / edge1_length
        dir_y = edge1_y / edge1_length

        # Perpendicular direction
        perp_x = -dir_y
        perp_y = dir_x

        # Use constraints or existing edge length
        width = self.rect_width if self.rect_width_mode else edge1_length
        height = self.rect_height if self.rect_height_mode else edge1_length * 0.6

        # Recalculate p2 if width is constrained
        if self.rect_width_mode:
            p2 = QgsPointXY(p1.x() + width * dir_x, p1.y() + width * dir_y)

        # Calculate other corners based on constraints
        p3 = QgsPointXY(p2.x() + height * perp_x, p2.y() + height * perp_y)
        p4 = QgsPointXY(p1.x() + height * perp_x, p1.y() + height * perp_y)

        return [p1, p2, p3, p4]

    def _create_rectangle_from_constraints(self):
        """Create rectangle from 2 existing points + current constraints"""
        if len(self.rect_points) != 2:
            return None

        p1, p2 = self.rect_points[0], self.rect_points[1]

        # Get the first edge vector (p1 to p2)
        edge1_x = p2.x() - p1.x()
        edge1_y = p2.y() - p1.y()
        edge1_length = math.hypot(edge1_x, edge1_y)

        if edge1_length < 1e-10:
            return None

        # Normalize first edge direction
        dir_x = edge1_x / edge1_length
        dir_y = edge1_y / edge1_length

        # Perpendicular direction
        perp_x = -dir_y
        perp_y = dir_x

        # Use constraints or existing edge length
        width = self.rect_width if self.rect_width_mode else edge1_length
        height = self.rect_height if self.rect_height_mode else edge1_length * 0.6

        # Recalculate p2 if width is constrained
        if self.rect_width_mode:
            p2 = QgsPointXY(p1.x() + width * dir_x, p1.y() + width * dir_y)

        # Calculate other corners based on constraints
        p3 = QgsPointXY(p2.x() + height * perp_x, p2.y() + height * perp_y)
        p4 = QgsPointXY(p1.x() + height * perp_x, p1.y() + height * perp_y)

        # Create closed polygon
        rectangle_points = [p1, p2, p3, p4, p1]
        return QgsGeometry.fromPolylineXY(rectangle_points)

    def _create_rectangle_from_params(self, second_point):
        """Create rectangle from parameters and two corner points"""
        if not self.rect_points:
            return None

        corner1 = self.rect_points[0]

        # Calculate direction from first to second corner
        dx = second_point.x() - corner1.x()
        dy = second_point.y() - corner1.y()
        dist = math.hypot(dx, dy)

        if dist < 1e-10:
            return None

        dir_x = dx / dist
        dir_y = dy / dist
        perp_x = -dir_y
        perp_y = dir_x

        # Use specified dimensions or calculated values
        if self.rect_width_mode and self.rect_height_mode:
            # Both dimensions specified
            width = self.rect_width
            height = self.rect_height
        elif self.rect_width_mode:
            # Only width specified, use mouse distance for height
            width = self.rect_width
            # Calculate height from mouse position projection onto perpendicular
            mouse_perp_proj = (second_point.x() - corner1.x()) * \
                perp_x + (second_point.y() - corner1.y()) * perp_y
            height = abs(mouse_perp_proj) or dist * 0.6
        elif self.rect_height_mode:
            # Only height specified, use mouse distance for width
            height = self.rect_height
            width = dist
        else:
            # No constraints - use mouse position
            width = dist
            height = dist * 0.6

        # Calculate all corners
        corner2 = QgsPointXY(corner1.x() + width * dir_x,
                             corner1.y() + width * dir_y)
        corner3 = QgsPointXY(corner2.x() + height * perp_x,
                             corner2.y() + height * perp_y)
        corner4 = QgsPointXY(corner1.x() + height * perp_x,
                             corner1.y() + height * perp_y)

        # Create closed polygon
        rectangle_points = [corner1, corner2, corner3, corner4, corner1]
        return QgsGeometry.fromPolylineXY(rectangle_points)

    def _add_rectangle_to_layer(self, geometry):
        """Add rectangle geometry to the current layer"""
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
        """Reset rectangle drawing state"""
        self.rect_points = []
        self.rect_width_mode = False
        self.rect_height_mode = False
        self.rect_width = 0
        self.rect_height = 0
        self.rubber_band.reset()
        # Hide rectangle-specific markers
        for marker in self.markers:
            if marker.color() in [QColor(255, 165, 0), QColor(255, 255, 0), QColor(0, 255, 255)]:
                marker.hide()

    def _update_rectangle_cursor_info(self, canvas_pos):
        """Update cursor info for rectangle mode"""
        config = QgsProject.instance().snappingConfig()
        snap_status = "ON" if config.enabled() else "OFF"
        unit_suffix = self.units[self.current_unit_key]['suffix']

        # Calculate current dimensions if applicable
        width = height = length = angle = None

        if self.current_point and self.rect_points:
            if self.rect_width_mode or self.rect_height_mode:
                # Parameter-driven mode
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
                # Freehand mode
                if len(self.rect_points) == 1:
                    corner1 = self.rect_points[0]
                    dx = self.current_point.x() - corner1.x()
                    dy = self.current_point.y() - corner1.y()
                    length = math.hypot(
                        dx, dy) / self.units[self.current_unit_key]['factor']
                    angle = math.atan2(dx, dy)
                elif len(self.rect_points) == 2:
                    # Show dimensions of partial rectangle
                    p1, p2 = self.rect_points[0], self.rect_points[1]
                    width_meters = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
                    height_meters = math.hypot(
                        self.current_point.x() - p1.x(), self.current_point.y() - p1.y())

                    width = width_meters / \
                        self.units[self.current_unit_key]['factor']
                    height = height_meters / \
                        self.units[self.current_unit_key]['factor']

        # Build mode description
        mode_parts = ["Rectangle"]
        if self.rect_width_mode and self.rect_height_mode:
            mode_parts.append("W&H Fixed")
        elif self.rect_width_mode:
            mode_parts.append("Width Fixed")
        elif self.rect_height_mode:
            mode_parts.append("Height Fixed")

        # Add angle lock status for rectangles
        # if self.rect_angle_lock and len(self.rect_points) >= 1:
        #     mode_parts.append("90° Lock ON")
        # elif len(self.rect_points) >= 1:
        #     mode_parts.append("90° Lock OFF")

        if len(self.rect_points) == 1:
            mode_parts.append("Set 2nd corner")
        elif len(self.rect_points) == 2:
            lock_status = "ON" if self.rect_angle_lock else "OFF"
            mode_parts.append(
                f"A: Toggle 90° - {lock_status})")

        mode = " | ".join(mode_parts)

        self.cursor_info.updateInfo(
            length=length, angle=angle, coordinates=self.current_point,
            width=width, height=height,
            mode=f"{mode} | Snap: {snap_status} | Unit: {self.units[self.current_unit_key]['name']}",
            canvas_pos=QPointF(canvas_pos), unit_suffix=unit_suffix
        )

    def _cancel_constraints(self):
        """Cancel any active length, angle, or rectangle constraints"""
        if self.length_mode or self.angle_mode:
            self.length_mode = False
            self.angle_mode = False
            self.preview_length = 0
            self.preview_angle = 0

            # Reset rubber band to normal drawing mode
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
        """Enhanced key handling with constraint cancellation and rectangle support"""
        if self.circle_mode and event.key() == Qt.Key.Key_L:
            # Handle circle mode L key (existing code)
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
            # Handle rectangle mode L key
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
            # Restore dialog for line mode
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
            Qt.Key.Key_Escape: self._handle_escape,  # Enhanced escape handling
            Qt.Key.Key_L: lambda: self._handle_parameter_dialog(),
            Qt.Key.Key_O: self._toggle_ortho,
            Qt.Key.Key_Enter: self._finish_current_operation,
            Qt.Key.Key_Return: self._finish_current_operation,
            Qt.Key.Key_U: self._undo_point,
            Qt.Key.Key_Backspace: self._undo_point,
            Qt.Key.Key_S: self._toggle_snap,
            Qt.Key.Key_C: self._close_line,
            Qt.Key.Key_A: self._handle_angle_lock,
            Qt.Key.Key_R: self._toggle_circle_mode,
            Qt.Key.Key_T: self._toggle_rectangle_mode,  # T for recTangle
            Qt.Key.Key_Q: self._next_unit,
        }
        if event.key() in key_actions:
            key_actions[event.key()]()

    def _handle_parameter_dialog(self):
        """Handle L key press based on current mode"""
        if self.rectangle_mode:
            self.dialog.show_dialog(
                self.rect_width or 10.0, self.rect_height or 10.0)
        else:
            self.dialog.show_dialog(self._current_length())

    def _finish_current_operation(self):
        """Finish current operation based on mode"""
        if self.rectangle_mode:
            if len(self.rect_points) >= 2:
                # Try to complete rectangle with current mouse position
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
        """Toggle rectangle drawing mode"""
        self.rectangle_mode = not self.rectangle_mode
        mode = "Rectangle" if self.rectangle_mode else "Line"
        show_msg(f"Mode: {mode}", 2)

        # Reset rectangle parameters when toggling modes
        self._reset_rectangle()
        self._safe_reset(rectangle_toggle=True)

    def _apply_rectangle_params(self, width, height, use_width, use_height):
        """Apply width and height parameters for rectangle creation"""
        self.rect_width = width if use_width else 0
        self.rect_height = height if use_height else 0
        self.rect_width_mode = use_width
        self.rect_height_mode = use_height

        # Build mode description
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
        # Reset circle parameters when toggling modes
        self.circle_center = None
        self.circle_radius = 0
        self.rubber_band.reset()
        self._safe_reset(circle_toggle=True)

    def _handle_escape(self):
        """Enhanced escape handling with hierarchical cancellation"""
        # First priority: Cancel active constraints
        if self._cancel_constraints():
            return

        # Second priority: Handle rectangle mode
        if self.rectangle_mode:
            if self.rect_points:
                self._reset_rectangle()
                show_msg("Rectangle cancelled", 2)
            return

        # Third priority: Handle circle mode
        if self.circle_mode:
            self.circle_center = None
            self.circle_radius = 0
            self.rubber_band.reset()
            show_msg("Circle cancelled", 2)
            return

        # Fourth priority: Reset entire operation
        self._safe_reset()
        show_msg("Operation cancelled", 2)

    def _toggle_ortho(self):
        self.ortho_mode = not self.ortho_mode

    def _handle_angle_lock(self):
        """Handle angle lock with different behavior for rectangles vs lines"""
        if self.rectangle_mode:
            # Simple toggle for rectangles
            self.rect_angle_lock = not self.rect_angle_lock
            status = "ON" if self.rect_angle_lock else "OFF"
            show_msg(f"Rectangle 90° lock: {status}", 1)
            return

        # Original behavior for lines
        current_time = time.time()
        al = self.angle_lock

        if current_time - al['last_press'] < 0.5:  # Double press
            if al['active']:
                al['active'] = False
                al['index'] = 0
                show_msg("Angle lock cancelled")
        else:  # Single press
            if not al['active']:
                # First press - activate with 90°
                al['active'] = True
                al['index'] = 0
                show_msg(f"Angle lock: {int(math.degrees(al['angles'][0]))}°")
            elif al['index'] == 0:
                # Second press - switch to 180°
                al['index'] = 1
                show_msg(f"Angle lock: {int(math.degrees(al['angles'][1]))}°")
            else:
                # Third press - cancel angle lock
                al['active'] = False
                al['index'] = 0
                show_msg("Angle lock cancelled")

        al['last_press'] = current_time

    def _start_line(self, point, pixel_pos):
        self.start_point = point
        self.points = [point]
        self.is_drawing = True
        self.markers.append(create_marker(self.canvas, point))
        self.rubber_band.reset()
        self.rubber_band.addPoint(point)
        show_msg("Line started. Click next point or press L")

    def _apply_circle_radius(self, radius, angle, use_length, use_angle):
        """Apply radius for circle creation (only uses radius parameter)"""
        self.circle_radius = radius  # radius is already in meters

        # Restore dialog for line mode
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
        pts = []
        for i in range(num_points + 1):
            angle = 2 * math.pi * i / num_points
            x = center.x() + radius * math.cos(angle)
            y = center.y() + radius * math.sin(angle)
            pts.append(QgsPointXY(x, y))
        if not preview_only:
            return QgsGeometry.fromPolylineXY(pts)
        return pts  # for preview

    def _add_point(self, point):
        if not self.is_drawing:
            return

        if self.angle_lock['active'] and self.points:
            point = self._apply_angle_lock(point)
        elif self.ortho_mode and self.points:
            point = self._apply_ortho(point)

        self.points.append(point)
        self.markers.append(create_marker(self.canvas, point))
        self.rubber_band.addPoint(point)
        self.start_point = point

    def _apply_angle_lock(self, point):
        """Apply angle lock with bidirectional support based on cursor position"""
        prev = self.points[-1]

        # Calculate mouse direction for determining which locked direction to use
        dx_mouse = point.x() - prev.x()
        dy_mouse = point.y() - prev.y()
        mouse_angle = math.atan2(dx_mouse, dy_mouse)
        cursor_distance = math.hypot(dx_mouse, dy_mouse) or 10.0

        # Get the locked angle delta (90° or 180°)
        locked_delta = self.angle_lock['angles'][self.angle_lock['index']]

        if len(self.points) < 2:
            # First point - lock to grid coordinates (N, E, S, W for 90°; N-S, E-W for 180°)
            if locked_delta == math.pi/2:  # 90° lock - snap to cardinal directions
                # Cardinal directions: North=π/2, East=0, South=3π/2, West=π
                cardinal_angles = [0, math.pi/2,
                                   math.pi, 3*math.pi/2]  # E, N, W, S

                # Find closest cardinal direction to mouse angle
                # Normalize mouse_angle to [0, 2π]
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

            else:  # 180° lock - snap to N-S or E-W axis
                # For 180°, we have two main axes: N-S (π/2, 3π/2) and E-W (0, π)
                # Calculate which axis is closer to mouse direction
                normalized_mouse = (mouse_angle + 2*math.pi) % (2*math.pi)

                # Check distance to N-S axis (vertical)
                ns_angles = [math.pi/2, 3*math.pi/2]  # North, South
                ew_angles = [0, math.pi]  # East, West

                # Find closest angle for each axis
                min_ns_diff = min(abs((normalized_mouse - ang + math.pi) %
                                  (2*math.pi) - math.pi) for ang in ns_angles)
                min_ew_diff = min(abs((normalized_mouse - ang + math.pi) %
                                  (2*math.pi) - math.pi) for ang in ew_angles)

                if min_ns_diff < min_ew_diff:
                    # Closer to N-S axis
                    final_angle = math.pi/2 if abs((normalized_mouse - math.pi/2 + math.pi) % (2*math.pi) - math.pi) < abs(
                        (normalized_mouse - 3*math.pi/2 + math.pi) % (2*math.pi) - math.pi) else 3*math.pi/2
                else:
                    # Closer to E-W axis
                    final_angle = 0 if abs((normalized_mouse - 0 + math.pi) % (2*math.pi) - math.pi) < abs(
                        (normalized_mouse - math.pi + math.pi) % (2*math.pi) - math.pi) else math.pi

        else:
            # Multiple points - lock relative to last segment
            prev_prev = self.points[-2]

            # Calculate the reference angle of the last segment
            dx_ref = prev.x() - prev_prev.x()
            dy_ref = prev.y() - prev_prev.y()
            reference_angle = math.atan2(dx_ref, dy_ref)

            if locked_delta == math.pi/2:  # 90° lock
                # Calculate both perpendicular directions
                angle_positive = (reference_angle + math.pi/2) % (2 * math.pi)
                angle_negative = (reference_angle - math.pi/2) % (2 * math.pi)

                # Determine which direction is closer to mouse direction
                normalized_mouse = (mouse_angle + 2*math.pi) % (2*math.pi)

                diff_positive = abs(
                    (normalized_mouse - angle_positive + math.pi) % (2 * math.pi) - math.pi)
                diff_negative = abs(
                    (normalized_mouse - angle_negative + math.pi) % (2 * math.pi) - math.pi)

                # Choose the angle closest to mouse direction
                final_angle = angle_positive if diff_positive < diff_negative else angle_negative

            else:  # 180° lock
                # For 180°, we can go in the same direction or opposite direction
                angle_same = reference_angle % (2 * math.pi)
                angle_opposite = (reference_angle + math.pi) % (2 * math.pi)

                # Determine which direction is closer to mouse direction
                normalized_mouse = (mouse_angle + 2*math.pi) % (2*math.pi)

                diff_same = abs((normalized_mouse - angle_same +
                                math.pi) % (2 * math.pi) - math.pi)
                diff_opposite = abs(
                    (normalized_mouse - angle_opposite + math.pi) % (2 * math.pi) - math.pi)

                # Choose the angle closest to mouse direction
                final_angle = angle_same if diff_same < diff_opposite else angle_opposite

        # Return the locked point using the projected segment length
        # Calculate the segment length by projecting cursor distance onto the locked direction
        angle_diff = abs((mouse_angle - final_angle + math.pi) %
                         (2 * math.pi) - math.pi)

        # Project the cursor distance onto the locked angle direction
        segment_length = cursor_distance * math.cos(angle_diff)

        # Ensure minimum length to prevent zero-length segments
        segment_length = max(segment_length, 0.1)

        return QgsPointXY(
            prev.x() + segment_length * math.sin(final_angle),
            prev.y() + segment_length * math.cos(final_angle)
        )

    def _apply_ortho(self, point):
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
        if not (self.rubber_band and self.current_point):
            return

        # Use the current point (which includes snapping) for the preview
        preview_point = self.current_point

        # Apply ortho mode if enabled
        if self.ortho_mode:
            preview_point = self._apply_ortho(preview_point)

        # Apply angle lock if active
        if self.angle_lock['active'] and self.points:
            preview_point = self._apply_angle_lock(preview_point)

        self.rubber_band.reset()
        for pt in self.points:
            self.rubber_band.addPoint(pt)
        self.rubber_band.addPoint(preview_point)

    def _update_parameter_preview(self):
        if not self.start_point:
            return
        end_point = self._calc_preview_end()
        self.rubber_band.reset()
        for pt in self.points:
            self.rubber_band.addPoint(pt)
        self.rubber_band.addPoint(end_point)

    def _calc_preview_end(self):
        """Calculate preview endpoint based on active constraints"""
        ref = self.points[-1] if len(self.points) > 1 else self.start_point

        # Determine angle based on current constraints and locks
        if self.angle_mode and not self.angle_lock['active']:
            # User specified angle takes precedence
            final_angle = self.preview_angle
        elif self.angle_lock['active']:
            # Angle lock is active - calculate locked angle
            if len(self.points) > 1:
                dx = self.points[-1].x() - self.points[-2].x()
                dy = self.points[-1].y() - self.points[-2].y()
                base_angle = math.atan2(dx, dy)
            else:
                base_angle = 0.0

            locked_delta = self.angle_lock['angles'][self.angle_lock['index']]

            # Determine direction based on mouse position for any mode with angle lock
            if self.current_point:
                dx_mouse = self.current_point.x() - ref.x()
                dy_mouse = self.current_point.y() - ref.y()
                mouse_angle = math.atan2(dx_mouse, dy_mouse)

                if locked_delta == math.pi/2:  # 90° lock
                    angle_positive = (base_angle + math.pi/2) % (2 * math.pi)
                    angle_negative = (base_angle - math.pi/2) % (2 * math.pi)
                    normalized_mouse = (mouse_angle + 2*math.pi) % (2*math.pi)
                    diff_positive = abs(
                        (normalized_mouse - angle_positive + math.pi) % (2 * math.pi) - math.pi)
                    diff_negative = abs(
                        (normalized_mouse - angle_negative + math.pi) % (2 * math.pi) - math.pi)
                    final_angle = angle_positive if diff_positive < diff_negative else angle_negative
                else:  # 180° lock
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
            # No angle constraints - follow mouse direction
            if self.current_point:
                dx = self.current_point.x() - ref.x()
                dy = self.current_point.y() - ref.y()
                final_angle = math.atan2(
                    dx, dy) if math.hypot(dx, dy) > 0 else 0.0
            else:
                final_angle = 0.0

        # Determine length based on constraints
        if self.length_mode:
            # Use specified length
            length = self.preview_length
        else:
            # Follow mouse distance (for angle-only mode or free drawing)
            if self.current_point:
                length = math.hypot(
                    self.current_point.x() - ref.x(),
                    self.current_point.y() - ref.y()
                ) or 10.0
            else:
                length = 10.0

        return QgsPointXY(
            ref.x() + length * math.sin(final_angle),
            ref.y() + length * math.cos(final_angle)
        )

    def _check_vertex_snap(self, canvas_pos):
        """Check for snapping to custom vertices (markers) - only when snapping is enabled"""
        config = QgsProject.instance().snappingConfig()

        # Only snap to vertices if QGIS snapping is enabled
        if not config.enabled() or not self.markers:
            return None

        # Get the snapping tolerance from QGIS snapping configuration
        snap_tolerance = config.tolerance()
        if snap_tolerance <= 0:
            snap_tolerance = 12  # Default fallback if somehow invalid

        # Convert canvas position to map coordinates for distance calculation
        map_pos = self.toMapCoordinates(canvas_pos)
        min_distance = float('inf')
        snap_point = None

        for marker in self.markers:
            if not marker.isVisible():
                continue

            marker_pos = marker.center()

            # Convert to pixel distance for tolerance check
            marker_pixel = self.toCanvasCoordinates(marker_pos)
            pixel_distance = math.hypot(
                canvas_pos.x() - marker_pixel.x(),
                canvas_pos.y() - marker_pixel.y()
            )

            # Use QGIS snapping tolerance
            if pixel_distance < snap_tolerance:
                # Calculate distance in map units for finding closest point
                distance = math.hypot(
                    map_pos.x() - marker_pos.x(),
                    map_pos.y() - marker_pos.y()
                )

                if distance < min_distance:
                    min_distance = distance
                    snap_point = marker_pos

        return snap_point

    def _get_snap_point(self, canvas_pos):
        """Enhanced snapping that includes custom vertices"""
        config = QgsProject.instance().snappingConfig()

        # Only proceed if snapping is enabled
        if not config.enabled():
            return None

        # First, try custom vertex snapping (only when snapping is enabled)
        custom_snap = self._check_vertex_snap(canvas_pos)
        if custom_snap:
            return custom_snap

        # Then try regular QGIS snapping
        self.snapping.setConfig(config)
        self.snapping.setMapSettings(self.canvas.mapSettings())
        snap = self.snapping.snapToMap(self.toMapCoordinates(canvas_pos))
        if snap.isValid():
            return snap.point()

        return None

    def _update_cursor_info(self, canvas_pos):
        """Update cursor info with enhanced constraint status display"""
        config = QgsProject.instance().snappingConfig()
        snap_status = "ON" if config.enabled() else "OFF"

        # Check if we're snapping to custom vertex
        custom_snap = self._check_vertex_snap(canvas_pos)
        if custom_snap:
            snap_status += "+Vertex"

        length = angle = None
        unit_suffix = self.units[self.current_unit_key]['suffix']

        # Calculate live length based on current context
        if self.start_point and self.current_point:
            if self.length_mode or self.angle_mode:
                # In preview mode, show the preview length/angle
                end_point = self._calc_preview_end()
                ref_point = self.points[-1] if len(
                    self.points) > 1 else self.start_point
                dx = end_point.x() - ref_point.x()
                dy = end_point.y() - ref_point.y()
                length_meters = math.hypot(dx, dy)
                length = length_meters / \
                    self.units[self.current_unit_key]['factor']
                angle = math.atan2(dx, dy)
            else:
                # Normal drawing mode
                ref_point = self.points[-1] if self.is_drawing and len(
                    self.points) > 1 else self.start_point
                dx = self.current_point.x() - ref_point.x()
                dy = self.current_point.y() - ref_point.y()
                length_meters = math.hypot(dx, dy)
                length = length_meters / \
                    self.units[self.current_unit_key]['factor']
                angle = math.atan2(dx, dy) if length_meters > 0 else 0

        # Build enhanced mode display
        mode_parts = []

        # Primary mode
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

        # Angle lock status
        if self.angle_lock['active']:
            lock_deg = int(math.degrees(
                self.angle_lock['angles'][self.angle_lock['index']]))
            mode_parts.append(f"Lock{lock_deg}°")

        # Cancellation hint for constraints
        if self.length_mode or self.angle_mode:
            mode_parts.append("(Esc/RClick to cancel)")

        mode = " | ".join(mode_parts)

        self.cursor_info.updateInfo(
            length=length, angle=angle, coordinates=self.current_point,
            mode=f"{mode} | Snap: {snap_status} | Unit: {self.units[self.current_unit_key]['name']}",
            canvas_pos=QPointF(canvas_pos), unit_suffix=unit_suffix
        )

    def set_parameters(self, length_meters, angle, use_length, use_angle):
        """Handle parameter input with support for length-only, angle-only, or both"""

        if not self.start_point:
            self.preview_length = length_meters if use_length else 0
            self.preview_angle = angle if use_angle else 0
            self.length_mode = use_length
            self.angle_mode = use_angle

            # Clear angle lock when user inputs angle
            if use_angle:
                self.angle_lock['active'] = False
                show_msg("Angle lock cleared - using input angle")

            # Build mode description
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

        # Set parameters for existing line
        self.preview_length = length_meters if use_length else 0
        self.preview_angle = angle if use_angle else 0
        self.length_mode = use_length
        self.angle_mode = use_angle

        # Clear angle lock when user inputs angle
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

        # FIXED: Add point to current line instead of creating new feature
        self.points.append(end_point)
        self.markers.append(create_marker(self.canvas, end_point))
        self.start_point = end_point  # Update start point for next segment

        # Show length in current display units
        length_meters = math.hypot(dx, dy)
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
            total_meters = sum(math.hypot(self.points[i+1].x()-self.points[i].x(),
                                          self.points[i+1].y()-self.points[i].y())
                               for i in range(len(self.points)-1))
            # Show total length in current display units
            total_display = total_meters / \
                self.units[self.current_unit_key]['factor']
            unit_suffix = self.units[self.current_unit_key]['suffix']
            show_msg(
                f"Line completed. Length: {total_display:.3f}{unit_suffix}", 1)
        else:
            show_msg("Failed to add line", 1, Qgis.MessageLevel.Critical)
        self._safe_reset()

    def _add_to_layer(self):
        layer = iface.activeLayer()
        if not (layer and layer.type() == QgsMapLayer.LayerType.VectorLayer and
                layer.geometryType() == QgsWkbTypes.GeometryType.LineGeometry and layer.isEditable()) or len(self.points) < 2:
            return False

        geometry = QgsGeometry.fromPolylineXY(self.points)
        if geometry.isEmpty():
            return False

        feature = QgsFeature(layer.fields())
        feature.setGeometry(geometry)

        if layer.addFeature(feature):
            layer.updateExtents()
            layer.triggerRepaint()
            self.canvas.refresh()
            return True
        return False

    def _close_line(self):
        if self.is_drawing and len(self.points) >= 3:
            self.points.append(self.points[0])
            self.markers.append(create_marker(
                self.canvas, self.points[0], QColor(255, 255, 0)))
            self._finish_line()

    def _undo_point(self):
        if self.rectangle_mode and self.rect_points:
            # Undo last rectangle point
            self.rect_points.pop()
            if self.markers:
                marker = self.markers.pop()
                if marker.color() in [QColor(255, 165, 0), QColor(255, 255, 0), QColor(0, 255, 255)]:
                    marker.hide()
            self.rubber_band.reset()
            show_msg(
                f"Rectangle point removed. {len(self.rect_points)} points remaining.", 1)
        elif self.is_drawing and len(self.points) > 1:
            # Undo last line point
            self.points.pop()
            if self.markers:
                self.markers.pop().hide()
            self.rubber_band.reset()
            for pt in self.points:
                self.rubber_band.addPoint(pt)
            self.start_point = self.points[-1]
            show_msg("Point removed", 1)

    def _toggle_snap(self):
        project = QgsProject.instance()
        config = project.snappingConfig()
        config.setEnabled(not config.enabled())
        project.setSnappingConfig(config)
        self.snapping.setConfig(config)
        if not config.enabled():
            self.snap_marker.hide()
        show_msg(f"Snap: {'ON' if config.enabled() else 'OFF'}", 2)

    def _handle_right_click(self):
        """Context-sensitive right-click behavior"""
        # If constraints are active, cancel them first
        if self.length_mode or self.angle_mode or self.rect_width_mode or self.rect_height_mode:
            self._cancel_constraints()
        # If in rectangle mode with points, finish rectangle
        elif self.rectangle_mode and len(self.rect_points) >= 2:
            self._finish_current_operation()
        # If drawing a line, finish it
        elif self.is_drawing:
            self._finish_line()
        # Otherwise, open parameter dialog
        else:
            self._handle_parameter_dialog()

    def _current_length(self):
        if self.start_point and self.current_point:
            return math.hypot(self.current_point.x() - self.start_point.x(),
                              self.current_point.y() - self.start_point.y())
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
        if hasattr(self, 'snap_marker'):
            self.snap_marker.hide()
        # Reset flags and variables
        self.is_drawing = False
        self.ortho_mode = False
        self.points = []
        self.start_point = None
        self.current_point = None
        self.current_snap_point = None  # Reset snap point tracking
        self.markers = []
        self.length_mode = False
        self.angle_mode = False
        self.preview_length = 0
        self.preview_angle = 0
        self.last_angle = 0
        # Updated angle_lock with only 90° and 180° options
        self.angle_lock = {
            'active': False,
            'index': 0,
            'angles': [math.pi/2, math.pi],  # Only 90° and 180°
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
            self.rect_angle_lock = True  # Reset to default ON state

    def deactivate(self):
        self._safe_reset()
        if hasattr(self, 'cursor_info'):
            self.cursor_info.close()
        if hasattr(self, 'dialog'):
            self.dialog.close()
        super().deactivate()


def activate_tool():
    canvas = iface.mapCanvas()
    tool = ProfessionalLineTool(canvas)
    canvas.setMapTool(tool)
    snap = "ON" if QgsProject.instance().snappingConfig().enabled() else "OFF"
    show_msg(
        f"🖱️ Left: Add | Right: Finish | L: Params | O: Ortho | Q: Toggle Units | U: Undo | C: Close | S: Snap({snap}) | A: Angle Lock | R: Circle | T: Rectangle | Esc: Cancel", 2, Qgis.MessageLevel.Success)
    return tool


# activate_tool()

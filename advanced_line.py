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
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
                            Qt.Tool | Qt.WindowDoesNotAcceptFocus)
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

    def updateInfo(self, length=None, angle=None, coordinates=None, mode="", canvas_pos=None, label="Length", unit_suffix="m"):
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
    parametersEntered = pyqtSignal(float, float, bool)

    def __init__(self, units_dict, current_unit_key='m'):
        super().__init__()
        self.units = units_dict
        self.current_unit_key = current_unit_key
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

        # Length input
        length_layout = QHBoxLayout()
        self.length_input = QDoubleSpinBox()
        self.length_input.setDecimals(4)
        self.length_input.setRange(0.0001, 999999)
        self.length_input.setValue(10.0)
        self.update_length_suffix()
        length_layout.addWidget(QLabel("Length:"))
        length_layout.addWidget(self.length_input)
        layout.addLayout(length_layout)

        # Angle input
        angle_layout = QHBoxLayout()
        self.use_angle_cb = QCheckBox("Use Angle")
        self.angle_input = QDoubleSpinBox()
        self.angle_input.setDecimals(1)
        self.angle_input.setRange(0.0, 359.9)
        self.angle_input.setValue(0.0)
        self.angle_input.setSuffix("° (N=0° CW)")
        self.angle_input.setEnabled(False)
        self.use_angle_cb.toggled.connect(self.angle_input.setEnabled)
        angle_layout.addWidget(self.use_angle_cb)
        angle_layout.addWidget(self.angle_input)
        layout.addLayout(angle_layout)

        # Quick angle buttons
        self.grid = QGridLayout()
        for i, angle in enumerate([0, 45, 90, 135, 180, 225, 270, 315]):
            btn = QPushButton(f"{angle}°")
            btn.setFocusPolicy(Qt.NoFocus)
            btn.clicked.connect(lambda _, a=angle: self.set_quick_angle(a))
            self.grid.addWidget(btn, i // 4, i % 4)
        layout.addLayout(self.grid)

        # Buttons
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("Apply")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept_parameters)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(QPushButton("Cancel", clicked=self.close))
        layout.addLayout(btn_layout)

    def on_unit_changed(self):
        # Get the selected unit key
        selected_unit_key = self.unit_combo.currentData()
        if selected_unit_key and selected_unit_key != self.current_unit_key:
            # Convert current length value to new unit
            old_factor = self.units[self.current_unit_key]['factor']
            new_factor = self.units[selected_unit_key]['factor']

            # Convert: old_unit_value * old_factor = meters, meters / new_factor = new_unit_value
            current_value = self.length_input.value()
            meters_value = current_value * old_factor
            new_value = meters_value / new_factor

            self.current_unit_key = selected_unit_key
            self.length_input.setValue(new_value)
            self.update_length_suffix()

    def update_length_suffix(self):
        suffix = f" {self.units[self.current_unit_key]['suffix']}"
        self.length_input.setSuffix(suffix)

    def hide_angle_buttons(self):
        for i in range(self.grid.count()):
            widget = self.grid.itemAt(i).widget()
            if widget:
                widget.hide()

    def show_angle_buttons(self):
        for i in range(self.grid.count()):
            widget = self.grid.itemAt(i).widget()
            if widget:
                widget.show()

    def set_quick_angle(self, angle):
        self.use_angle_cb.setChecked(True)
        self.angle_input.setValue(angle)

    def accept_parameters(self):
        if self.length_input.value() <= 0:
            return

        # Convert input length to meters for internal calculations
        length_in_input_units = self.length_input.value()
        length_in_meters = length_in_input_units * \
            self.units[self.current_unit_key]['factor']

        self.parametersEntered.emit(
            length_in_meters,  # Always emit length in meters
            math.radians(self.angle_input.value()
                         ) if self.use_angle_cb.isChecked() else 0,
            self.use_angle_cb.isChecked()
        )
        self.hide()

    def show_dialog(self, cur_len_meters=10.0):
        # Convert current length from meters to display unit
        length_in_display_units = cur_len_meters / \
            self.units[self.current_unit_key]['factor']
        self.length_input.setValue(length_in_display_units)
        self.use_angle_cb.setChecked(False)
        self.show()
        QTimer.singleShot(50, lambda: (
            self.length_input.setFocus(), self.length_input.lineEdit().selectAll()))

    def closeEvent(self, event):
        self.hide()
        event.ignore()


def create_marker(canvas, point, color=QColor(0, 255, 0)):
    marker = QgsVertexMarker(canvas)
    marker.setCenter(point)
    marker.setColor(color)
    marker.setIconType(QgsVertexMarker.ICON_BOX)
    marker.setIconSize(12)
    marker.setPenWidth(2)
    return marker


def show_msg(msg, duration=2, level=Qgis.Info):
    if iface and iface.messageBar():
        iface.messageBar().pushMessage("📐 Line Tool", msg, level=level, duration=duration)


class ProfessionalLineTool(QgsMapTool):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.reset_state()

        # UI Components
        self.rubber_band = QgsRubberBand(canvas, QgsWkbTypes.LineGeometry)
        self.rubber_band.setColor(QColor("brown"))
        self.rubber_band.setWidth(1.5)
        self.rubber_band.setLineStyle(Qt.DashLine)

        self.snap_marker = QgsVertexMarker(canvas)
        self.snap_marker.setIconType(QgsVertexMarker.ICON_BOX)
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
        self.dialog.setParent(iface.mainWindow(), Qt.Window)
        self.dialog.parametersEntered.connect(self.set_parameters)

    def _set_current_unit(self, key):
        if key in self.units:
            self.current_unit_key = key
            self.current_unit_index = self.unit_keys.index(key)
            # Update dialog's current unit
            self.dialog.current_unit_key = key
            self.dialog.unit_combo.setCurrentText(self.units[key]['name'])
            self.dialog.update_length_suffix()
            show_msg(f"Unit set to: {self.units[key]['name']}", 1)
        else:
            show_msg(f"Unknown unit: {key}", 1, Qgis.Warning)

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

    def activate(self):
        self.canvas.setCursor(Qt.CrossCursor)

    def canvasPressEvent(self, event):
        if not self._valid_layer():
            return

        if self.circle_mode:
            point = self._get_snap_point(
                event.pos()) or self.toMapCoordinates(event.pos())
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
            return

        # Regular line mode handling
        point = self._get_snap_point(
            event.pos()) or self.toMapCoordinates(event.pos())
        if event.button() == Qt.LeftButton:
            if (self.length_mode or self.angle_mode) and not self.start_point:
                self._start_line(point, event.pos())
                show_msg("Move mouse and click to confirm")
            elif self.length_mode or self.angle_mode:
                self._confirm_preview()
            elif not self.is_drawing:
                self._start_line(point, event.pos())
            else:
                self._add_point(point)
        elif event.button() == Qt.RightButton:
            self._handle_right_click()

    def canvasMoveEvent(self, event):
        if self.circle_mode and self.circle_center:
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

    def keyPressEvent(self, event):
        if self.circle_mode and event.key() == Qt.Key_L:
            # Disconnect any prior receiver to avoid multiple emissions
            try:
                self.dialog.parametersEntered.disconnect()
            except Exception:
                pass
            self.dialog.parametersEntered.connect(self._apply_circle_radius)

            # Update dialog for circle mode
            self.dialog.setWindowTitle("Circle Parameters")
            self.dialog.length_input.setPrefix("Radius: ")

            # Hide angle controls in circle mode
            self.dialog.use_angle_cb.hide()
            self.dialog.angle_input.hide()
            self.dialog.hide_angle_buttons()  # Hide the quick angle buttons

            # Show with current radius in display units
            radius_in_display_units = self.circle_radius / \
                self.units[self.current_unit_key]['factor'] if self.circle_radius else 10.0
            self.dialog.show_dialog(self.circle_radius or 10.0)
            return
        else:
            # Restore dialog for line mode
            self.dialog.setWindowTitle("Line Parameters")
            self.dialog.length_input.setPrefix("")
            self.dialog.use_angle_cb.show()
            self.dialog.angle_input.show()
            self.dialog.show_angle_buttons()
            # Reconnect for line mode
            try:
                self.dialog.parametersEntered.disconnect()
            except Exception:
                pass
            self.dialog.parametersEntered.connect(self.set_parameters)

        key_actions = {
            Qt.Key_Escape: self._handle_escape,
            Qt.Key_L: lambda: self.dialog.show_dialog(self._current_length()),
            Qt.Key_O: self._toggle_ortho,
            Qt.Key_Enter: self._finish_line,
            Qt.Key_Return: self._finish_line,
            Qt.Key_U: self._undo_point,
            Qt.Key_Backspace: self._undo_point,
            Qt.Key_S: self._toggle_snap,
            Qt.Key_C: self._close_line,
            Qt.Key_A: self._handle_angle_lock,
            Qt.Key_R: self._toggle_circle_mode,
            Qt.Key_Q: self._next_unit,
        }
        if event.key() in key_actions:
            key_actions[event.key()]()

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
        if self.length_mode or self.angle_mode:
            self._cancel_preview()
        else:
            # Clear circle parameters when escaping
            if self.circle_mode:
                self.circle_center = None
                self.circle_radius = 0
                self.rubber_band.reset()
                show_msg("Circle cancelled", 2)
            else:
                self._safe_reset()
                show_msg("Cancelled", 2)

    def _toggle_ortho(self):
        self.ortho_mode = not self.ortho_mode

    def _handle_angle_lock(self):
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

    def _apply_circle_radius(self, radius, angle, use_angle):
        self.circle_radius = radius  # radius is already in meters
        # Restore dialog for line mode usability:
        self.dialog.use_angle_cb.show()
        self.dialog.angle_input.show()
        self.dialog.setWindowTitle("Line Parameters")
        self.dialog.length_input.setPrefix("")
        if self.circle_center:
            circle_geom = self._create_circle_geometry(
                self.circle_center, self.circle_radius)
            self._add_circle_to_layer(circle_geom)
            # Reset circle parameters after creating circle
            self.circle_center = None
            self.circle_radius = 0
            self.rubber_band.reset()
            show_msg("Circle added!", 1)
        else:
            show_msg("Click to set circle center.", 1)

    def _add_circle_to_layer(self, geometry):
        layer = iface.activeLayer()
        if not (layer and layer.isEditable()):
            show_msg("Need editable line layer", 1, Qgis.Critical)
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
        ref = self.points[-1] if len(self.points) > 1 else self.start_point

        # Determine angle - FIXED: Clear angle lock when user inputs angle
        if self.angle_mode and not self.angle_lock['active']:
            # User specified angle - use it directly
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

            # For length mode with angle lock, we need to determine direction based on mouse
            if self.length_mode and self.current_point:
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
        else:  # length_mode without angle lock
            if self.current_point:
                dx = self.current_point.x() - ref.x()
                dy = self.current_point.y() - ref.y()
                final_angle = math.atan2(
                    dx, dy) if math.hypot(dx, dy) > 0 else 0.0
            else:
                final_angle = 0.0

        # Determine length (preview_length is always in meters)
        if self.length_mode:
            length = self.preview_length
        else:  # angle_mode
            length = math.hypot(self.current_point.x() - ref.x(),
                                self.current_point.y() - ref.y()) or 10.0

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
                # Convert to display units
                length = length_meters / \
                    self.units[self.current_unit_key]['factor']
                angle = math.atan2(dx, dy)
            else:
                # Normal drawing mode, show current mouse distance
                ref_point = self.points[-1] if self.is_drawing and len(
                    self.points) > 1 else self.start_point
                dx = self.current_point.x() - ref_point.x()
                dy = self.current_point.y() - ref_point.y()
                length_meters = math.hypot(dx, dy)
                # Convert to display units
                length = length_meters / \
                    self.units[self.current_unit_key]['factor']
                angle = math.atan2(dx, dy) if length_meters > 0 else 0

        mode_map = {
            (True, False): "Length Preview",
            (False, True): "Angle Preview",
            (False, False): "Ortho Mode" if self.ortho_mode else "Drawing" if self.is_drawing else f"Ready"
        }
        mode = mode_map.get((self.length_mode, self.angle_mode), "Ready")

        if self.angle_lock['active']:
            lock_deg = int(math.degrees(
                self.angle_lock['angles'][self.angle_lock['index']]))
            mode = f"Lock {lock_deg}° | {mode}"

        self.cursor_info.updateInfo(
            length=length, angle=angle, coordinates=self.current_point,
            mode=f"{mode} | Snap: {snap_status} | Unit: {self.units[self.current_unit_key]['name']}",
            canvas_pos=QPointF(canvas_pos), unit_suffix=unit_suffix
        )

    def set_parameters(self, length_meters, angle, use_angle):
        if not self.start_point:
            self.preview_length = length_meters  # Store in meters
            self.preview_angle = angle
            self.length_mode = not use_angle
            self.angle_mode = use_angle

            # FIXED: Clear angle lock when user inputs angle
            if use_angle:
                self.angle_lock['active'] = False
                show_msg("Angle lock cleared - using input angle")

            show_msg("Click to set start point")
            return

        self.preview_length = length_meters  # Store in meters
        self.preview_angle = angle
        self.length_mode = not use_angle
        self.angle_mode = use_angle

        # FIXED: Clear angle lock when user inputs angle
        if use_angle:
            self.angle_lock['active'] = False
            show_msg("Angle lock cleared - using input angle")

        show_msg("Move mouse and click to confirm")

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
            show_msg("Failed to add line", 1, Qgis.Critical)
        self._safe_reset()

    def _add_to_layer(self):
        layer = iface.activeLayer()
        if not (layer and layer.type() == QgsMapLayer.VectorLayer and
                layer.geometryType() == QgsWkbTypes.LineGeometry and layer.isEditable()) or len(self.points) < 2:
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
        if self.is_drawing and len(self.points) > 1:
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
        if self.length_mode or self.angle_mode:
            self._cancel_preview()
        elif self.is_drawing:
            self._finish_line()
        else:
            self.dialog.show_dialog(self._current_length())

    def _current_length(self):
        if self.start_point and self.current_point:
            return math.hypot(self.current_point.x() - self.start_point.x(),
                              self.current_point.y() - self.start_point.y())
        return 10.0

    def _valid_layer(self):
        layer = iface.activeLayer()
        if not (layer and layer.type() == QgsMapLayer.VectorLayer and
                layer.geometryType() == QgsWkbTypes.LineGeometry and layer.isEditable()):
            show_msg("Need editable line layer", 1, Qgis.Critical)
            return False
        return True

    def _safe_reset(self, circle_toggle=False):
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
        f"🖱️ Left: Add | Right: Finish | L: Params | O: Ortho | Q: Toggle Units | U: Undo | C: Close | S: Snap({snap}) | A: Angle Lock | R: Circle | Esc: Cancel", 2, Qgis.Success)
    return tool


# activate_tool()

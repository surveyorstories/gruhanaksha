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
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setStyleSheet("QWidget{background:rgba(240,248,255,230);border:2px solid #2E86AB;border-radius:6px;padding:6px;font:bold 10pt Consolas;color:#1B4965}")
        
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

    def updateInfo(self, length=None, angle=None, coordinates=None, mode="", canvas_pos=None, label="Length"):
        self.text_lines = []
        if length is not None:
            if length < 1:
                self.text_lines.append(f"{label}: {length:.4f}m")
            elif length < 1000:
                self.text_lines.append(f"{label}: {length:.3f}m")
            else:
                self.text_lines.append(f"{label}: {length/1000:.4f}km")
        if angle is not None:
            self.text_lines.append(f"Angle: {math.degrees(angle)%360:.1f}° (N=0° CW)")
        # if coordinates:
        #     self.text_lines.extend([f"X: {coordinates.x():.3f}", f"Y: {coordinates.y():.3f}"])
        if mode:
            self.text_lines.append(f"Mode: {mode}")

        if self.text_lines and canvas_pos:
            fm = self.fontMetrics()
            w = max(fm.horizontalAdvance(line) for line in self.text_lines) + 20
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
        if not (self.text_lines and self.is_active): return
        painter = QPainter(self)
        y = 20
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

class ParameterDialog(QDialog):
    parametersEntered = pyqtSignal(float, float, bool)
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Line Parameters")
        self.setModal(False)
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        
        layout = QVBoxLayout(self)
        
        # Length input
        length_layout = QHBoxLayout()
        self.length_input = QDoubleSpinBox()
        self.length_input.setDecimals(4)
        self.length_input.setRange(0.0001, 999999)
        self.length_input.setValue(10.0)
        self.length_input.setSuffix(" m")
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
        for i, angle in enumerate([0,45,90,135,180,225,270,315]):
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
        if self.length_input.value() <= 0: return
        self.parametersEntered.emit(
            self.length_input.value(),
            math.radians(self.angle_input.value()) if self.use_angle_cb.isChecked() else 0,
            self.use_angle_cb.isChecked()
        )
        self.hide()

    def show_dialog(self, cur_len=10.0):
        self.length_input.setValue(cur_len)
        self.use_angle_cb.setChecked(False)
        self.show()
        QTimer.singleShot(50, lambda: (self.length_input.setFocus(), self.length_input.lineEdit().selectAll()))

    def closeEvent(self, event):
        self.hide()
        event.ignore()

def create_marker(canvas, point, color=QColor(0,255,0)):
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
        self.rubber_band.setColor(QColor('grey'))
        self.rubber_band.setWidth(1)
        self.rubber_band.setLineStyle(Qt.DashLine)
        
        self.snap_marker = QgsVertexMarker(canvas)
        self.snap_marker.setIconType(QgsVertexMarker.ICON_BOX)
        self.snap_marker.setColor(QColor(255,0,255))
        self.snap_marker.setPenWidth(3)
        self.snap_marker.setIconSize(12)
        self.snap_marker.hide()
        
        self.cursor_info = CursorInfo(canvas)
        self.snapping = QgsSnappingUtils()
        self.dialog = ParameterDialog()
        self.dialog.parametersEntered.connect(self.set_parameters)

    def reset_state(self):
        self.is_drawing = False
        self.ortho_mode = False
        self.points = []
        self.start_point = None
        self.current_point = None
        self.markers = []
        self.preview_length = 0
        self.preview_angle = 0
        self.length_mode = False
        self.angle_mode = False
        self.last_angle = 0
        self.angle_lock = {'active': False, 'index': 0, 'angles': [math.pi/2, math.pi, 3*math.pi/2, 2*math.pi], 'last_press': 0}

        # Circle mode props
        self.circle_mode = False
        self.circle_center = None
        self.circle_radius = 0


    def activate(self):
        self.canvas.setCursor(Qt.CrossCursor)
        show_msg("L: params | R: Circle |O: ortho | S: snap | U: undo | C: close | A: angle lock | Esc: cancel",3)


    def canvasPressEvent(self, event):
        if not self._valid_layer():
            return

        if self.circle_mode:
            point = self._get_snap_point(event.pos()) or self.toMapCoordinates(event.pos())
            if self.circle_center is None:
                self.circle_center = point
                if self.circle_radius:  # If radius is already known, create immediately
                    circle_geom = self._create_circle_geometry(self.circle_center, self.circle_radius)
                    self._add_circle_to_layer(circle_geom)
                    self._safe_reset(circle_toggle=True)
                    show_msg("Circle added!", 1)
                else:
                    show_msg("Circle center set. Move and click to set radius or press L.", 2)
            else:
                radius = math.hypot(point.x() - self.circle_center.x(), point.y() - self.circle_center.y())
                circle_geom = self._create_circle_geometry(self.circle_center, radius)
                self._add_circle_to_layer(circle_geom)
                self._safe_reset(circle_toggle=True)
                show_msg("Circle added!", 2)
            return
        # else: regular line mode handling
        point = self._get_snap_point(event.pos()) or self.toMapCoordinates(event.pos())
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
            point = self._get_snap_point(event.pos()) or self.toMapCoordinates(event.pos())
            radius = math.hypot(point.x() - self.circle_center.x(), point.y() - self.circle_center.y())
            circle_pts = self._create_circle_geometry(self.circle_center, radius, preview_only=True)
            self.rubber_band.reset()
            for pt in circle_pts:
                self.rubber_band.addPoint(pt)
            # SHOW RADIUS IN TOOLTIP OVERLAY:
            self.cursor_info.updateInfo(
            length=radius,
            angle=None,
            coordinates=point,
            mode=f"Circle | Snap: {'ON' if QgsProject.instance().snappingConfig().enabled() else 'OFF'}",
            canvas_pos=event.pos(),
            label="Radius"
        )
            return
        # else: normal line move
        self.snap_marker.hide()
        config = QgsProject.instance().snappingConfig()
        self.snapping.setConfig(config)
        self.snapping.setMapSettings(self.canvas.mapSettings())
        snap_point = self._get_snap_point(event.pos()) if config.enabled() else None
        self.current_point = snap_point or self.toMapCoordinates(event.pos())
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
            try: self.dialog.parametersEntered.disconnect()
            except Exception: pass
            self.dialog.parametersEntered.connect(self._apply_circle_radius)

            # Update dialog for circle mode
            self.dialog.setWindowTitle("Circle Parameters")
            self.dialog.length_input.setSuffix(" m")
            self.dialog.length_input.setDecimals(4)
            self.dialog.length_input.setMinimum(0.0001)
            self.dialog.length_input.setMaximum(999999)
            self.dialog.length_input.setValue(self.circle_radius or 10.0)
            self.dialog.length_input.setPrefix("Radius: ")

            # Hide angle controls in circle mode
            self.dialog.use_angle_cb.hide()
            self.dialog.angle_input.hide()
            self.dialog.hide_angle_buttons() # Hide the quick angle buttons
            self.dialog.show()
            
            QTimer.singleShot(50, lambda: (self.dialog.length_input.setFocus(), self.dialog.length_input.lineEdit().selectAll()))
            return
        else: 
            self.dialog.setWindowTitle("Line Parameters")
            self.dialog.length_input.setPrefix("Length: ")
            self.dialog.show_angle_buttons()

        key_actions = {
            Qt.Key_Escape: self._handle_escape,
            Qt.Key_L: lambda: self.dialog.show_dialog(self._current_length()),
            Qt.Key_O: self._toggle_ortho,
            Qt.Key_Enter: self._finish_line,
            Qt.Key_Return: self._finish_line,
            Qt.Key_U: self._undo_point,
            Qt.Key_S: self._toggle_snap,
            Qt.Key_C: self._close_line,
            Qt.Key_A: self._handle_angle_lock,
            Qt.Key_R: self._toggle_circle_mode,
        }
        if event.key() in key_actions:
            key_actions[event.key()]()

    def _toggle_circle_mode(self):
        self.circle_mode = not self.circle_mode
        mode = "Circle" if self.circle_mode else "Line"
        show_msg(f"Mode: {mode}", 2)
        self._safe_reset(circle_toggle=True)

    def _handle_escape(self):
        if self.length_mode or self.angle_mode:
            self._cancel_preview()
        else:
            self._safe_reset()
            show_msg("Cancelled", 2)

    def _toggle_ortho(self):
        self.ortho_mode = not self.ortho_mode
        # show_msg(f"Ortho: {'ON' if self.ortho_mode else 'OFF'}", 2)

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
                al['active'] = True
                al['index'] = 0
                show_msg(f"Angle lock: {int(math.degrees(al['angles'][0]))}°")
            else:
                al['index'] = (al['index'] + 1) % len(al['angles'])
                show_msg(f"Angle lock: {int(math.degrees(al['angles'][al['index']]))}°")
        
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
        self.circle_radius = radius
        # Restore dialog for line mode usability:
        self.dialog.use_angle_cb.show()
        self.dialog.angle_input.show()
        self.dialog.setWindowTitle("Line Parameters")
        self.dialog.length_input.setPrefix("")
        if self.circle_center:
            circle_geom = self._create_circle_geometry(self.circle_center, self.circle_radius)
            self._add_circle_to_layer(circle_geom)
            self._safe_reset(circle_toggle=True)
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
        if not self.is_drawing: return
        
        if self.angle_lock['active'] and self.points:
            point = self._apply_angle_lock(point)
        elif self.ortho_mode and self.points:
            point = self._apply_ortho(point)
        
        self.points.append(point)
        self.markers.append(create_marker(self.canvas, point))
        self.rubber_band.addPoint(point)
        self.start_point = point

    def _apply_angle_lock(self, point):
        prev = self.points[-1]
        segment_length = math.hypot(point.x() - prev.x(), point.y() - prev.y()) or 10.0
        
        if len(self.points) > 1:
            dx = prev.x() - self.points[-2].x()
            dy = prev.y() - self.points[-2].y()
            base_angle = math.atan2(dx, dy)
        else:
            base_angle = 0.0
        
        locked_delta = self.angle_lock['angles'][self.angle_lock['index']]
        final_angle = (base_angle + locked_delta) % (2*math.pi)
        
        return QgsPointXY(
            prev.x() + segment_length * math.sin(final_angle),
            prev.y() + segment_length * math.cos(final_angle)
        )

    def _apply_ortho(self, point):
        ref = self.start_point
        dx, dy = point.x() - ref.x(), point.y() - ref.y()
        if abs(dx) < 1e-10 and abs(dy) < 1e-10: return point
        
        angle = math.atan2(dx, dy)
        snap_angle = round(angle / (math.pi / 4)) * (math.pi / 4)
        dist = math.hypot(dx, dy)
        
        return QgsPointXY(
            ref.x() + dist * math.sin(snap_angle),
            ref.y() + dist * math.cos(snap_angle)
        )

    def _update_drawing_preview(self):
        if not (self.rubber_band and self.current_point): return
        p = self._apply_ortho(self.current_point) if self.ortho_mode else self.current_point
        self.rubber_band.reset()
        for pt in self.points:
            self.rubber_band.addPoint(pt)
        self.rubber_band.addPoint(p)

    def _update_parameter_preview(self):
        if not self.start_point: return
        end_point = self._calc_preview_end()
        self.rubber_band.reset()
        for pt in self.points:
            self.rubber_band.addPoint(pt)
        self.rubber_band.addPoint(end_point)

    def _calc_preview_end(self):
        ref = self.points[-1] if len(self.points) > 1 else self.start_point
        
        # Determine angle
        if self.angle_lock['active']:
            if len(self.points) > 1:
                dx = self.points[-1].x() - self.points[-2].x()
                dy = self.points[-1].y() - self.points[-2].y()
                base_angle = math.atan2(dx, dy)
            else:
                base_angle = 0.0
            locked_delta = self.angle_lock['angles'][self.angle_lock['index']]
            final_angle = (base_angle + locked_delta) % (2*math.pi)
        elif self.angle_mode:
            final_angle = self.preview_angle
        else:  # length_mode
            dx = self.current_point.x() - ref.x()
            dy = self.current_point.y() - ref.y()
            final_angle = math.atan2(dx, dy) if math.hypot(dx, dy) > 0 else 0.0
        
        # Determine length
        if self.length_mode:
            length = self.preview_length
        else:  # angle_mode
            length = math.hypot(self.current_point.x() - ref.x(), self.current_point.y() - ref.y()) or 10.0
        
        return QgsPointXY(
            ref.x() + length * math.sin(final_angle),
            ref.y() + length * math.cos(final_angle)
        )

    def _update_cursor_info(self, canvas_pos):
        config = QgsProject.instance().snappingConfig()
        snap_status = "ON" if config.enabled() else "OFF"
        
        length = angle = None
        # Calculate live length based on current context
        if self.start_point and self.current_point:
            if self.length_mode or self.angle_mode:
                # In preview mode, show the preview length/angle
                end_point = self._calc_preview_end()
                ref_point = self.points[-1] if len(self.points) > 1 else self.start_point
                dx = end_point.x() - ref_point.x()
                dy = end_point.y() - ref_point.y()
                length = math.hypot(dx, dy)
                angle = math.atan2(dx, dy)
            else:
                # Normal drawing mode, show current mouse distance
                ref_point = self.points[-1] if self.is_drawing and len(self.points) > 1 else self.start_point
                dx = self.current_point.x() - ref_point.x()
                dy = self.current_point.y() - ref_point.y()
                length = math.hypot(dx, dy)
                angle = math.atan2(dx, dy) if length > 0 else 0
        
        mode_map = {
            (True, False): "Length Preview",
            (False, True): "Angle Preview",
            (False, False): "Ortho Mode" if self.ortho_mode else "Drawing" if self.is_drawing else f"Ready"
        }
        mode = mode_map.get((self.length_mode, self.angle_mode), "Ready")
        
        if self.angle_lock['active']:
            lock_deg = int(math.degrees(self.angle_lock['angles'][self.angle_lock['index']]))
            mode = f"Lock {lock_deg}° | {mode}"
        
        self.cursor_info.updateInfo(
            length=length, angle=angle, coordinates=self.current_point,
            mode=f"{mode} | Snap: {snap_status}", canvas_pos=QPointF(canvas_pos)
        )

    def set_parameters(self, length, angle, use_angle):
        if not self.start_point:
            self.preview_length = length
            self.preview_angle = angle
            self.length_mode = not use_angle
            self.angle_mode = use_angle
            show_msg("Click to set start point")
            return
        
        self.preview_length = length
        self.preview_angle = angle
        self.length_mode = not use_angle
        self.angle_mode = use_angle
        show_msg("Move mouse and click to confirm")

    def _confirm_preview(self):
        if not self.start_point: return
        end_point = self._calc_preview_end()
        dx, dy = end_point.x() - self.start_point.x(), end_point.y() - self.start_point.y()
        self.last_angle = math.atan2(dx, dy)
        self.points.append(end_point)
        
        if self._add_to_layer():
            show_msg("Line added!", 1)
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
            total = sum(math.hypot(self.points[i+1].x()-self.points[i].x(), self.points[i+1].y()-self.points[i].y()) 
                       for i in range(len(self.points)-1))
            show_msg(f"Line completed. Length: {total:.3f}m", 1)
        else:
            show_msg("Failed to add line", 1, Qgis.Critical)
        self._safe_reset()

    def _add_to_layer(self):
        layer = iface.activeLayer()
        if not (layer and layer.type() == QgsMapLayer.VectorLayer and 
                layer.geometryType() == QgsWkbTypes.LineGeometry and layer.isEditable()) or len(self.points) < 2:
            return False
        
        geometry = QgsGeometry.fromPolylineXY(self.points)
        if geometry.isEmpty(): return False
        
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
            self.markers.append(create_marker(self.canvas, self.points[0], QColor(255,255,0)))
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

    def _get_snap_point(self, canvas_pos):
        config = QgsProject.instance().snappingConfig()
        self.snapping.setConfig(config)
        self.snapping.setMapSettings(self.canvas.mapSettings())
        if not config.enabled(): return None
        
        snap = self.snapping.snapToMap(self.toMapCoordinates(canvas_pos))
        return snap.point() if snap.isValid() else None

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
        # Most of previous _safe_reset body...
        if hasattr(self, 'cursor_info'):
            self.cursor_info.safe_hide()
        if hasattr(self, 'rubber_band'):
            self.rubber_band.reset()
        for m in getattr(self, 'markers', []):
            m.hide()
        if hasattr(self, 'snap_marker'):
            self.snap_marker.hide()
        self.is_drawing = False
        self.ortho_mode = False
        self.points = []
        self.start_point = None
        self.current_point = None
        self.markers = []
        self.length_mode = False
        self.angle_mode = False
        self.preview_length = 0
        self.preview_angle = 0
        self.last_angle = 0
        self.angle_lock = {'active': False, 'index': 0, 'angles': [math.pi/2, math.pi, 3*math.pi/2, 2*math.pi], 'last_press': 0}
        if circle_toggle or not self.circle_mode:
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
    # show_msg(f"🖱️ Left: Add | Right: Finish | L: Params | O: Ortho | U: Undo | C: Close | S: Snap({snap}) | A: Angle Lock | Esc: Cancel", 3, Qgis.Success)
    return tool

# activate_tool()
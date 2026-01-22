from .addon_functions import enable_label, rule_based_symbology, undo, redo
from .qt_compat import Qt, QtCompat, QColor
from qgis.PyQt.QtCore import QPointF
from qgis.gui import QgsMapTool, QgsRubberBand, QgsMapToolZoom, QgsMapCanvas, QgsMapToolPan
from qgis.gui import QgsMapTool, QgsMapMouseEvent
from qgis.PyQt.QtGui import QPainter, QIcon

from qgis.core import QgsSymbol, QgsGeometry, QgsPointXY, QgsRuleBasedRenderer, QgsRectangle, QgsWkbTypes, QgsFeatureRequest, QgsSpatialIndex, QgsField, QgsSingleSymbolRenderer, QgsExpression, Qgis, QgsMapLayer, NULL, QgsAggregateCalculator


from qgis.gui import QgsMessageBar
from .qt_compat import QVBoxLayout, QMainWindow, QWidget, QSizePolicy, QInputDialog
from qgis.utils import iface
from qgis.gui import *
from qgis.core import *
from qgis.core import QgsApplication
from .qt_compat import QEvent, QSize, QVariant
from .qt_compat import (
    QMainWindow, QVBoxLayout, QWidget, QPushButton, QAction, QDialog,
    QCheckBox, QMessageBox, QLabel, QComboBox, QSpinBox, QDialogButtonBox,
    QFormLayout, QActionGroup, QListWidget, QListWidgetItem
)
import sys
import os
import inspect
from qgis.core import QgsMapLayerStyle, QgsProject
from qgis.gui import QgsMapToolIdentify
cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]
icon = QIcon(os.path.join(os.path.join(cmd_folder, 'images/crosshair.svg')))


class DeleteAttributesDialog(QDialog):
    def __init__(self, layer, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Delete Fields")
        self.layer = layer
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.list_widget = QListWidget()

        # Populate with existing fields
        for field in self.layer.fields():
            item = QListWidgetItem(field.name())
            item.setFlags(item.flags() | QtCompat.ItemIsUserCheckable)
            item.setCheckState(QtCompat.unchecked())
            self.list_widget.addItem(item)

        layout.addWidget(self.list_widget)

        button_box = QDialogButtonBox(
            QtCompat.DialogOk | QtCompat.DialogCancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def get_selected_indexes(self):
        selected_indexes = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == QtCompat.checked():
                # Find index of field with this name
                # (Robust against field order changes if we used names, but list is built from fields)
                # However, layer.deleteAttributes takes indexes.
                idx = self.layer.fields().indexFromName(item.text())
                if idx != -1:
                    selected_indexes.append(idx)
        return selected_indexes


class AutoNumberDialog(QDialog):
    def __init__(self, layer, parent=None):
        super().__init__(parent)
        self.layer = layer
        self.setWindowTitle("Auto Number Settings")
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # Field Selection
        self.field_combo = QComboBox()
        self.field_combo.setEditable(True)  # Allow typing new field name

        # Populate with existing fields
        fields = [f.name() for f in self.layer.fields()]
        self.field_combo.addItems(fields)

        # Set default to LP_NO if exists, else first item
        index = self.field_combo.findText("LP_NO")
        if index >= 0:
            self.field_combo.setCurrentIndex(index)
        else:
            self.field_combo.setEditText("LP_NO")

        form_layout.addRow("Field Name:", self.field_combo)

        # Start Number
        self.start_num_spin = QSpinBox()
        self.start_num_spin.setRange(1, 999999)
        self.start_num_spin.setValue(1)
        form_layout.addRow("Start Number:", self.start_num_spin)

        layout.addLayout(form_layout)

        # Buttons
        button_box = QDialogButtonBox(
            QtCompat.DialogOk | QtCompat.DialogCancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Connect signals
        self.field_combo.currentTextChanged.connect(self.update_start_number)
        self.field_combo.editTextChanged.connect(self.update_start_number)

        # Initial update
        self.update_start_number()

    def update_start_number(self):
        field_name = self.field_combo.currentText()
        idx = self.layer.fields().indexFromName(field_name)

        max_val = 0
        if idx != -1:
            try:
                # Use aggregate to find max value
                max_val = self.layer.aggregate(
                    QgsAggregateCalculator.Max, field_name)[0]
                if max_val is None:
                    max_val = 0
                max_val = int(max_val)
            except:
                max_val = 0

        self.start_num_spin.setValue(max_val + 1)

        if idx != -1:
            try:
                # Efficiently collect all values
                request = QgsFeatureRequest().setFlags(
                    QgsFeatureRequest.NoGeometry).setSubsetOfAttributes([idx])

                existing_values = []
                for f in self.layer.getFeatures(request):
                    val = f[idx]
                    if val is not None:
                        try:
                            # Handle string numbers
                            int_val = int(val)
                            if int_val > 0:
                                existing_values.append(int_val)
                        except (ValueError, TypeError):
                            continue

                val_count = len(existing_values)
                unique_values = set(existing_values)
            except:
                val_count = 0
                unique_values = set()

            # Enhanced validation checking (Check earlier)
            from collections import Counter
            counts = Counter(existing_values)
            duplicate_values = {k for k, v in counts.items() if v > 1}
            has_duplicates = len(duplicate_values) > 0

            # Guard Clause: Check for mismatch OR internal duplicates (e.g. 1, 3, 3)
            if max_val != val_count or has_duplicates:
                # Mismatch detected! Prepare warning.
                # Avoid showing this if user is just typing characters?
                # Ideally only on combo box selection change, not necessarily every keystroke.
                # But signals are connected. We can rely on user interaction.

                msg = QMessageBox(self)
                msg.setIcon(QtCompat.Warning)

                # Pre-calculate duplicate string for both cases
                if has_duplicates:
                    dupes = [f"{k} ({v}x)" for k, v in counts.items() if v > 1]
                    dupes.sort()
                    dupe_str = ", ".join(dupes[:5])
                    if len(dupes) > 5:
                        dupe_str += f", ... (+{len(dupes)-5} more)"
                else:
                    dupe_str = ""

                if max_val > val_count:
                    # Case 1: Gaps Detected
                    all_nums = set(range(1, max_val + 1))
                    gaps = sorted(list(all_nums - unique_values))

                    gap_str = ", ".join(map(str, gaps[:10]))
                    if len(gaps) > 10:
                        gap_str += f", ... (+{len(gaps)-10} more)"

                    first_gap = gaps[0] if gaps else val_count + 1

                    msg.setWindowTitle("Sequence Gaps Detected")

                    text = (f"Highest value is <b>{max_val}</b>, but only <b>{val_count}</b> features are labeled.<br>"
                            f"Missing numbers: <b style='color:red;'>{gap_str}</b><br>")

                    if has_duplicates:
                        text += (f"<br><b>Warning: {len(duplicate_values)} duplicates also detected.</b><br>"
                                 f"Duplicate values: <b style='color:orange;'>{dupe_str}</b><br>")

                    text += "<br>How would you like to continue?"

                    btn_max_text = f"Continue from {max_val + 1} (Append)"
                    btn_count_text = f"Fill Gap (Start from {first_gap})"

                else:
                    # Case 2: Duplicates Detected (or just mismatch logic failed to catch gap?)
                    # If max_val <= val_count but max_val != val_count implies what?
                    # actually invalid state if strictly 1..N.
                    # Standard duplicate logic:
                    dupes = [f"{k} ({v}x)" for k, v in counts.items() if v > 1]
                    dupes.sort()

                    dupe_str = ", ".join(dupes[:5])
                    if len(dupes) > 5:
                        dupe_str += f", ... (+{len(dupes)-5} more)"

                    msg.setWindowTitle("Sequence Duplicates Detected")
                    text = (f"Highest value is <b>{max_val}</b>, but <b>{val_count}</b> features are labeled.<br>"
                            f"Duplicates found: <b style='color:orange;'>{dupe_str}</b><br><br>"
                            "How would you like to continue?")

                    btn_max_text = f"Continue from {max_val + 1} (Recommended)"
                    btn_count_text = f"Continue from {val_count + 1} (Skip/Jump)"

                msg.setText(text)

                btn_max = QPushButton(btn_max_text)
                btn_count = QPushButton(btn_count_text)
                btn_clear = None

                if has_duplicates:
                    btn_clear = QPushButton("Clear Duplicates (Set NULL)")

                btn_cancel = QPushButton("Cancel")

                msg.addButton(btn_max, QtCompat.AcceptRole)
                msg.addButton(btn_count, QtCompat.AcceptRole)
                if btn_clear:
                    msg.addButton(btn_clear, QtCompat.DestructiveRole)
                msg.addButton(btn_cancel, QtCompat.RejectRole)
                msg.setDefaultButton(btn_max)

                QtCompat.exec(msg)

                if msg.clickedButton() == btn_max:
                    self.start_num_spin.setValue(max_val + 1)
                elif msg.clickedButton() == btn_count:
                    # For Gaps: Start from first gap
                    if max_val > val_count:
                        self.start_num_spin.setValue(first_gap)
                    else:
                        self.start_num_spin.setValue(val_count + 1)

                elif btn_clear and msg.clickedButton() == btn_clear:
                    # Clear duplicate values
                    if not self.layer.isEditable():
                        self.layer.startEditing()

                    idx = self.layer.fields().indexFromName(field_name)  # Ensure idx is available
                    status_idx = self.layer.fields().indexFromName('STATUS')

                    cleared_count = 0
                    for f in self.layer.getFeatures():
                        val = f[idx]
                        if val is not None:
                            try:
                                int_val = int(val)
                                if int_val in duplicate_values:
                                    self.layer.changeAttributeValue(
                                        f.id(), idx, None)
                                    cleared_count += 1
                                    if status_idx != -1:
                                        self.layer.changeAttributeValue(
                                            f.id(), status_idx, 'cleared')
                            except:
                                continue

                    self.start_num_spin.setValue(max_val + 1)
                    QMessageBox.information(self, "Duplicates Cleared",
                                            f"Successfully cleared {cleared_count} duplicate values.\\nFeatures marked as 'cleared' (Blue).")

    def get_values(self):
        return self.field_combo.currentText(), self.start_num_spin.value()


class SmartSelectionTool(QgsMapTool):
    def __init__(self, canvas, parent):
        super().__init__(canvas)
        self.canvas = canvas
        self.parent = parent
        self.rubberBand = None
        self.startPoint = None
        self.isEmittingPoint = False

    def canvasPressEvent(self, e):
        if e.button() != QtCompat.LeftButton:
            return

        self.startPoint = self.toMapCoordinates(e.pos())
        self.rubberBand = QgsRubberBand(
            self.canvas, QgsWkbTypes.PolygonGeometry)
        self.rubberBand.setColor(QColor(255, 0, 0, 65))
        self.rubberBand.setWidth(1)
        self.isEmittingPoint = True

    def canvasMoveEvent(self, e):
        if not self.isEmittingPoint:
            return

        endPoint = self.toMapCoordinates(e.pos())
        point1 = QgsPointXY(self.startPoint.x(), self.startPoint.y())
        point2 = QgsPointXY(endPoint.x(), self.startPoint.y())
        point3 = QgsPointXY(endPoint.x(), endPoint.y())
        point4 = QgsPointXY(self.startPoint.x(), endPoint.y())

        self.rubberBand.reset(QgsWkbTypes.PolygonGeometry)
        self.rubberBand.addPoint(point1, False)
        self.rubberBand.addPoint(point2, False)
        self.rubberBand.addPoint(point3, False)
        self.rubberBand.addPoint(point4, True)
        self.rubberBand.show()

    def canvasReleaseEvent(self, e):
        self.isEmittingPoint = False

        # Left Click - Selection Logic
        if self.rubberBand:
            rect = self.rubberBand.asGeometry().boundingBox()
            self.rubberBand.reset(QgsWkbTypes.PolygonGeometry)
            self.rubberBand = None

            layer = self.parent.layer
            if not layer:
                return

            # Check for modifiers
            modifiers = e.modifiers()
            is_ctrl = modifiers & QtCompat.ControlModifier

            # Check if it's a point click (or very small drag)
            # Use a small tolerance to distinguish click from drag
            tolerance = self.canvas.mapUnitsPerPixel() * 2
            is_point_click = rect.width() < tolerance and rect.height() < tolerance

            if is_point_click:
                # Point Selection - Toggle
                point = self.toMapCoordinates(e.pos())
                # Use a small buffer for point selection to make it easier to hit features
                search_rect = QgsRectangle(
                    point.x(), point.y(), point.x(), point.y())
                search_rect.grow(self.canvas.mapUnitsPerPixel() * 3)

                request = QgsFeatureRequest().setFilterRect(search_rect).setFlags(
                    QgsFeatureRequest.NoGeometry).setLimit(1)
                ids = [f.id() for f in layer.getFeatures(request)]

                if ids:
                    fid = ids[0]
                    if fid in layer.selectedFeatureIds():
                        layer.deselect(fid)
                    else:
                        layer.select(fid)
            else:
                # Drag Selection
                if is_ctrl:
                    # Ctrl + Drag -> Remove from selection
                    layer.selectByRect(
                        rect, QgsVectorLayer.RemoveFromSelection)
                else:
                    # Drag -> Add to selection (Default to allow building selection)
                    layer.selectByRect(rect, QgsVectorLayer.AddToSelection)


class LabelIncrementer(QgsMapToolIdentify):
    def __init__(self, canvas, layer):
        super().__init__(canvas)
        self.canvas = canvas
        self.layer = layer  # Just store the layer without checking
        self.label = 'LP_NO'
        self.max_label_value = 0

        # Drawing state
        self.isDrawing = False
        self.startPoint = None
        self.endPoint = None
        self.points = []

        # Initialize rubber band
        self.rubberBand = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.rubberBand.setColor(QColor("red"))
        self.rubberBand.setWidth(1)

        self.setCursor(QtCompat.pointing_hand_cursor())
        self.right_mouse_button_pressed = False
        self.left_mouse_button_pressed = False

        # Remove layer type checking from init

        # if self.layer:
        #     self.initializeFields()
        #     self.updateMaxLabelValue()

    def activate(self):
        """Called when tool is activated"""
        super().activate()
        if self.layer:
            self.initializeFields()
            self.updateMaxLabelValue()

    def initializeFields(self):
        """Initialize required fields"""
        if not self.layer or self.layer.type() != QgsMapLayer.VectorLayer:
            return

        try:
            # Get existing field names
            existing_fields = [field.name() for field in self.layer.fields()]

            # Check and create LP_NO field if it doesn't exist
            if self.label not in existing_fields:
                if not self.layer.isEditable():
                    self.layer.startEditing()

                self.layer.addAttribute(QgsField(self.label, QVariant.Int))
                print(f"Created field: {self.label}")

            # Check and create STATUS field if it doesn't exist
            if 'STATUS' not in existing_fields:
                if not self.layer.isEditable():
                    self.layer.startEditing()

                self.layer.addAttribute(QgsField('STATUS', QVariant.String))
                print(f"Created field: STATUS")

            if self.layer.isEditable():
                self.layer.commitChanges()

            # Apply default styling
            self.apply_styling()

        except Exception as e:
            print(f"Error creating fields: {str(e)}")
            if self.layer.isEditable():
                self.layer.rollBack()

    def canvasPressEvent(self, event):
        if not self.layer:
            return

        point = self.toMapCoordinates(event.pos())
        modifiers = event.modifiers()

        if event.button() == QtCompat.LeftButton and modifiers == QtCompat.AltModifier:
            self.edit_label(point)
        elif event.button() == QtCompat.LeftButton and modifiers == QtCompat.ControlModifier:
            # Start left-click+control drag operation
            self.left_mouse_button_pressed = True
            self.isDrawing = True
            self.startPoint = point
            self.points = [point]
        elif event.button() == QtCompat.LeftButton and not modifiers:
            self.addNewLabel(point)
        elif event.button() == QtCompat.RightButton:
            # Start right-click drag operation
            self.right_mouse_button_pressed = True
            self.isDrawing = True
            self.startPoint = point
            self.points = [point]

    def createRect(self, point, radius):
        """Create search rectangle around point"""
        return QgsRectangle(
            point.x() - radius,
            point.y() - radius,
            point.x() + radius,
            point.y() + radius
        )

    def keyPressEvent(self, event):
        # Detect key press events here
        if event.key() == QtCompat.Key_Z and event.modifiers() == QtCompat.ControlModifier:
            undo(self.layer)
            # Update max label value after undo without showing validation
            self.updateMaxLabelValue(show_validation=False)
        elif event.key() == QtCompat.Key_Y and event.modifiers() == QtCompat.ControlModifier:
            redo(self.layer)
            # Update max label value after redo without showing validation
            self.updateMaxLabelValue(show_validation=False)
        else:
            super().keyPressEvent(event)

    def canvasMoveEvent(self, event):
        if self.layer is None:
            return

        current_point = self.toMapCoordinates(event.pos())

        if (self.right_mouse_button_pressed or
                (self.left_mouse_button_pressed and event.modifiers() == QtCompat.ControlModifier)) and self.isDrawing:
            # Add current point to rubber band
            self.points.append(current_point)
            self.drawRubberBand()

            # Label features under the rubber band
            if len(self.points) > 1:
                # Create geometry from rubber band points
                line = QgsGeometry.fromPolylineXY(
                    [QgsPointXY(p) for p in self.points])
                # Small buffer around the line
                buffer = line.buffer(0.00001, 5)

                # Find features intersecting with the buffer
                request = QgsFeatureRequest().setFilterRect(buffer.boundingBox())
                for feature in self.layer.getFeatures(request):
                    if feature.geometry().intersects(buffer):
                        self.addNewLabel(
                            feature.geometry().centroid().asPoint(),
                            silent=True,
                            refresh=False
                        )

                # Trigger repaint once after processing batch
                self.layer.triggerRepaint()

        elif self.left_mouse_button_pressed and not event.modifiers():
            self.addNewLabel(current_point)

    def canvasReleaseEvent(self, event):
        if event.button() == QtCompat.RightButton and self.isDrawing:
            self.right_mouse_button_pressed = False
            self.isDrawing = False
            self.startPoint = None
            self.points = []
            self.removeRubberBand()
        elif event.button() == QtCompat.LeftButton and self.isDrawing:
            self.left_mouse_button_pressed = False
            self.isDrawing = False
            self.startPoint = None
            self.points = []
            self.removeRubberBand()

        # Reset drawing state
        self.isDrawing = False
        self.startPoint = None
        self.endPoint = None
        self.points = []

        # Clear the rubber band
        self.removeRubberBand()

    def drawRubberBand(self):
        if len(self.points) > 1:
            # Clear existing points and add new ones
            self.rubberBand.reset(QgsWkbTypes.LineGeometry)
            line = [QgsPointXY(point) for point in self.points]
            self.rubberBand.setToGeometry(
                QgsGeometry.fromPolylineXY(line), None)
            self.rubberBand.show()

    def removeRubberBand(self):
        if self.rubberBand:
            self.rubberBand.reset(QgsWkbTypes.LineGeometry)
            self.rubberBand.hide()

    def deactivate(self):
        self.isDrawing = False
        self.startPoint = None
        self.endPoint = None
        self.points = []
        self.removeRubberBand()
        super().deactivate()

    def createLPNField(self):
        if self.layer:
            # Check if 'LPM_NO' field exists
            field_names = [field.name() for field in self.layer.fields()]
            if self.label not in field_names:
                self.layer.startEditing()
                self.layer.addAttribute(QgsField(self.label, QVariant.Int))

    def createStatusFields(self):
        """Create fields to track label status"""
        if self.layer:
            self.layer.startEditing()
            field_names = [field.name() for field in self.layer.fields()]

            if 'STATUS' not in field_names:
                self.layer.addAttribute(QgsField('STATUS', QVariant.String))

    def apply_styling(self):
        """Apply rule-based styling for status visualization"""
        if not self.layer or not self.layer.isValid():
            return

        try:
            # Check if STATUS field exists
            if self.layer.fields().indexFromName('STATUS') == -1:
                return

            # Helper to create rules
            def create_rule(label, expression, color_hex):
                symbol = QgsSymbol.defaultSymbol(self.layer.geometryType())
                if symbol:
                    symbol.setColor(QColor(color_hex))
                rule = QgsRuleBasedRenderer.Rule(symbol)
                rule.setLabel(label)
                rule.setFilterExpression(expression)
                return rule

            # Define rules
            root_rule = QgsRuleBasedRenderer.Rule(None)

            # Rule 1: Duplicates (Red)
            root_rule.appendChild(create_rule(
                "Duplicate", "\"STATUS\" = 'duplicate'", "#FF4444"))

            # Rule 2: Edited (Orange)
            root_rule.appendChild(create_rule(
                "Edited", "\"STATUS\" = 'edited'", "#FFAA00"))

            # Rule 3: Auto Numbered (Green)
            root_rule.appendChild(create_rule(
                "Auto Numbered", "\"STATUS\" = 'auto_numbered'", "#44AA44"))

            # Rule 4: Cleared / Null (Blue/Purple)
            # Match 'cleared' status OR null values in the label field if we want
            # user asked for 'cleared duplicates', so specific status is better.
            root_rule.appendChild(create_rule(
                "Cleared", "\"STATUS\" = 'cleared'", "#4444FF"))

            # Rule 5: Default (Else)
            default_symbol = QgsSymbol.defaultSymbol(self.layer.geometryType())
            default_rule = QgsRuleBasedRenderer.Rule(default_symbol)
            default_rule.setLabel("Other")
            default_rule.setIsElse(True)
            root_rule.appendChild(default_rule)

            # Apply renderer
            renderer = QgsRuleBasedRenderer(root_rule)
            self.layer.setRenderer(renderer)
            self.layer.triggerRepaint()
            self.canvas.refresh()

        except Exception as e:
            print(f"Error applying styling: {e}")

    def updateMaxLabelValue(self, show_validation=True):
        """Update maximum label value with enhanced validation UI (no icons)"""
        if not self.layer:
            self.max_label_value = 0
            return

        # Check if LP_NO field exists
        field_names = [field.name() for field in self.layer.fields()]
        if self.label not in field_names:
            self.max_label_value = 0
            return

        try:
            # OPTIMIZATION: Fast Path using QGIS Aggregates
            label_idx = self.layer.fields().indexFromName(self.label)
            if label_idx == -1:
                return

            # Get Max Value (Fast C++)
            max_val_agg = self.layer.aggregate(
                QgsAggregateCalculator.Max, self.label)
            if isinstance(max_val_agg, tuple):
                max_val = max_val_agg[0]
            else:
                max_val = max_val_agg

            if max_val is None or max_val == NULL:
                max_val = 0
            else:
                max_val = int(max_val)

            self.max_label_value = max_val

            # Get Feature Count (Fast)
            # Using aggregate Count is safer
            labeled_count_agg = self.layer.aggregate(
                QgsAggregateCalculator.Count, self.label)
            if isinstance(labeled_count_agg, tuple):
                labeled_count = labeled_count_agg[0]
            else:
                labeled_count = labeled_count_agg

            if labeled_count is None:
                labeled_count = 0

            # Get Unique Values Count (Fast-ish)
            unique_values_set = self.layer.uniqueValues(label_idx)
            # Filter out NULLs
            unique_values = {
                v for v in unique_values_set if v is not None and v != NULL and str(v).strip() != ""}
            unique_count = len(unique_values)

            # HAPPY PATH: Sequence is perfect [1..N]
            # No duplicates (labeled_count == unique_count) AND No gaps (max_val == unique_count)
            # Assumption: Min value is 1. If min > 1, this check implies gaps.
            # If max_val == unique_count and labeled_count == unique_count:
            # It means we have 'unique_count' distinct values, and the max value is 'unique_count'.
            # Therefore values must be 1..N.

            if max_val == unique_count and labeled_count == unique_count:
                # Data is clean. No need to scan.
                return

            # SLOW PATH: Issues detected (Duplicates or Gaps).
            # We must identify duplicates to mark them.

            values = []
            duplicates = set()

            # First pass: collect values and find duplicates
            for feat in self.layer.getFeatures():
                val = feat[self.label]
                if val is not None and str(val).strip() not in ("", "NULL"):
                    try:
                        int_val = int(val)
                        if int_val in values:
                            duplicates.add(int_val)
                        values.append(int_val)
                    except (ValueError, TypeError):
                        continue

            # Second pass: mark duplicates if found
            if duplicates:
                if not self.layer.isEditable():
                    self.layer.startEditing()

                status_idx = self.layer.fields().indexFromName('STATUS')
                label_idx = self.layer.fields().indexFromName(self.label)

                for feat in self.layer.getFeatures():
                    val = feat[self.label]
                    if val is not None and str(val).strip() not in ("", "NULL"):
                        try:
                            if int(val) in duplicates:
                                self.layer.changeAttributeValue(
                                    feat.id(), status_idx, 'duplicate')
                        except (ValueError, TypeError):
                            continue

            # Enhanced validation UI
            # Ensure has_duplicates is calculated BEFORE the check
            from collections import Counter
            counts = Counter(values)
            duplicate_values = {k for k, v in counts.items() if v > 1}
            has_duplicates = len(duplicate_values) > 0

            # Enhanced validation UI without icons
            if (max_val != labeled_count or has_duplicates) and show_validation:
                msg = QMessageBox()
                msg.setIcon(QtCompat.Warning)

                unique_values = set(values)

                # Pre-calculate duplicate string for both cases
                if has_duplicates:
                    dupes = [f"{k} ({v}x)" for k, v in counts.items() if v > 1]
                    dupes.sort()
                    dupe_str = ", ".join(dupes[:5])
                    if len(dupes) > 5:
                        dupe_str += f", ... (+{len(dupes)-5} more)"
                else:
                    dupe_str = ""

                if max_val > labeled_count:
                    # Case 1: Gaps Detected
                    all_nums = set(range(1, max_val + 1))
                    gaps = sorted(list(all_nums - unique_values))

                    gap_str = ", ".join(map(str, gaps[:10]))
                    if len(gaps) > 10:
                        gap_str += f", ... (+{len(gaps)-10} more)"

                    first_gap = gaps[0] if gaps else int(labeled_count) + 1

                    msg.setWindowTitle("Sequence Gaps Detected")

                    text = (f"Highest value is <b>{max_val}</b>, but only <b>{int(labeled_count)}</b> features are labeled.<br>"
                            f"Missing numbers: <b style='color:red;'>{gap_str}</b><br>")

                    if has_duplicates:
                        text += (f"<br><b>Warning: {len(duplicate_values)} duplicates also detected.</b><br>"
                                 f"Duplicate values: <b style='color:orange;'>{dupe_str}</b><br>")

                    text += "<br>How would you like to continue?"

                    btn_max_text = f"Continue from {max_val + 1} (Append)"
                    btn_count_text = f"Fill Gap (Start from {first_gap})"

                else:
                    # Case 2: Duplicates Detected
                    msg.setWindowTitle("Sequence Duplicates Detected")
                    text = (f"Highest value is <b>{max_val}</b>, but <b>{int(labeled_count)}</b> features are labeled.<br>"
                            f"Duplicates found: <b style='color:orange;'>{dupe_str}</b><br><br>"
                            "How would you like to continue?")

                    btn_max_text = f"Continue from {max_val + 1} (Recommended)"
                    btn_count_text = f"Continue from {int(labeled_count) + 1} (Skip)"

                msg.setText(text)

                btn_max = QPushButton(btn_max_text)
                btn_count = QPushButton(btn_count_text)
                btn_clear = None

                if has_duplicates:
                    btn_clear = QPushButton("Clear Duplicates (Set NULL)")

                btn_cancel = QPushButton("Cancel")

                msg.addButton(btn_max, QtCompat.AcceptRole)
                msg.addButton(btn_count, QtCompat.AcceptRole)
                if btn_clear:
                    msg.addButton(btn_clear, QtCompat.DestructiveRole)
                msg.addButton(btn_cancel, QtCompat.RejectRole)
                msg.setDefaultButton(btn_max)

                QtCompat.exec(msg)

                if msg.clickedButton() == btn_max:
                    self.max_label_value = max_val
                elif msg.clickedButton() == btn_count:
                    # For Gaps: Start from first gap
                    if max_val > labeled_count:
                        self.max_label_value = first_gap - 1  # Manual logic: logic adds +1
                    else:
                        self.max_label_value = labeled_count

                elif btn_clear and msg.clickedButton() == btn_clear:
                    # Clear duplicate values
                    if not self.layer.isEditable():
                        self.layer.startEditing()

                    idx = self.layer.fields().indexFromName(self.label)
                    status_idx = self.layer.fields().indexFromName('STATUS')

                    cleared_count = 0
                    for f in self.layer.getFeatures():
                        val = f[idx]
                        if val is not None:
                            try:
                                int_val = int(val)
                                if int_val in duplicate_values:
                                    self.layer.changeAttributeValue(
                                        f.id(), idx, None)
                                    cleared_count += 1
                                    if status_idx != -1:
                                        self.layer.changeAttributeValue(
                                            f.id(), status_idx, 'cleared')
                            except:
                                continue
                    self.max_label_value = max_val
                    QMessageBox.information(self.canvas.window(), "Duplicates Cleared",
                                            f"Successfully cleared {cleared_count} duplicate values.\nFeatures marked as 'cleared' (Blue).")
                else:  # Cancel
                    return
            else:
                self.max_label_value = max_val

            # Update symbology to reflect any duplicate markings
            self.updateSymbology()

        except KeyError:
            self.max_label_value = 0

    def addNewLabel(self, point, silent=False, refresh=True):
        """Add new label to feature"""
        if not self.layer:
            return

        # Check if LP_NO field exists, if not recreate it
        if self.label not in [field.name() for field in self.layer.fields()]:
            messagebar = MessageBar(self.canvas)
            messagebar.pushMessage(
                "Warning",
                f"'{self.label}' field was missing. Recreating field...",
                Qgis.Warning,
                2
            )
            self.initializeFields()
            if not self.layer.isEditable():
                self.layer.startEditing()

        # Find feature at click point
        searchRadius = 0.00001
        rect = self.createRect(point, searchRadius)
        request = QgsFeatureRequest().setFilterRect(rect)

        try:
            for feature in self.layer.getFeatures(request):
                if feature.geometry().contains(point):
                    current_value = feature[self.label]

                    if current_value is None or str(current_value).strip() in ("", "NULL"):
                        self.max_label_value += 1
                        new_val = self.max_label_value

                        if not self.layer.isEditable():
                            self.layer.startEditing()

                        # Check for duplicates (robustness)
                        is_duplicate = False
                        duplicate_feat_id = None
                        expr = QgsExpression(f'"{self.label}" = {new_val}')
                        req = QgsFeatureRequest(expr)
                        for other_feat in self.layer.getFeatures(req):
                            if other_feat.id() != feature.id():
                                is_duplicate = True
                                duplicate_feat_id = other_feat.id()
                                break

                        self.layer.changeAttributeValue(
                            feature.id(),
                            self.layer.fields().indexFromName(self.label),
                            new_val
                        )

                        # Update status
                        status_idx = self.layer.fields().indexFromName('STATUS')
                        if status_idx != -1:
                            if is_duplicate:
                                self.layer.changeAttributeValue(
                                    feature.id(), status_idx, 'duplicate')
                                if duplicate_feat_id:
                                    self.layer.changeAttributeValue(
                                        duplicate_feat_id, status_idx, 'duplicate')
                            else:
                                # Leave status blank for new manual numbering
                                self.layer.changeAttributeValue(
                                    feature.id(), status_idx, '')

                        # self.layer.commitChanges()
                        print(
                            f"Feature {feature.id()} labeled with: {new_val}")

                        if not silent:
                            messagebar = MessageBar(self.canvas)
                            if is_duplicate:
                                messagebar.pushMessage(
                                    "Duplicate", f"Labeled with {new_val} (Duplicate!)", Qgis.Warning, 2)
                            else:
                                messagebar.pushMessage(
                                    "Success", f"Feature labeled with {new_val}", Qgis.Success, 2)
                    else:
                        if not silent:
                            messagebar = MessageBar(self.canvas)
                            messagebar.pushMessage(
                                "Already Labeled",
                                "Feature already has a label. Hold Alt and click to edit!",
                                Qgis.Warning,
                                2
                            )

                    if refresh:
                        self.layer.triggerRepaint()
                    return

        except KeyError:
            messagebar = MessageBar(self.canvas)
            messagebar.pushMessage(
                "Error",
                f"Failed to access '{self.label}' field. Please check layer fields.",
                Qgis.Critical,
                3
            )
            return

        print("No feature found at click location")

    def edit_label(self, point):
        """Edit existing label"""
        if not self.layer:
            return

        # Check if LP_NO field exists, if not recreate it
        if self.label not in [field.name() for field in self.layer.fields()]:
            messagebar = MessageBar(self.canvas)
            messagebar.pushMessage(
                "Warning",
                f"'{self.label}' field was missing. Recreating field...",
                Qgis.Warning,
                2
            )
            self.initializeFields()
            if not self.layer.isEditable():
                self.layer.startEditing()

        try:
            # Find feature at click point
            searchRadius = 0.00001
            rect = self.createRect(point, searchRadius)
            request = QgsFeatureRequest().setFilterRect(rect)

            for feature in self.layer.getFeatures(request):
                if feature.geometry().contains(point):
                    current_value = feature[self.label]

                    if current_value is not None and str(current_value).strip() not in ("", "NULL"):
                        new_value, ok = QInputDialog.getInt(
                            None,
                            "Edit Label",
                            f"Current value: {current_value}\nEnter new value:",
                            value=current_value,
                            min=1
                        )

                        if ok:
                            old_value = current_value

                            if not self.layer.isEditable():
                                self.layer.startEditing()

                            # Check for duplicates using efficient request
                            is_duplicate = False
                            duplicate_feat_id = None

                            # Search for ANY feature with this new value
                            expr = QgsExpression(
                                f'"{self.label}" = {new_value}')
                            req = QgsFeatureRequest(expr)
                            # We only need to know if ONE exists, and which one
                            for other_feat in self.layer.getFeatures(req):
                                if other_feat.id() != feature.id():
                                    is_duplicate = True
                                    duplicate_feat_id = other_feat.id()
                                    break

                            # Update label
                            self.layer.changeAttributeValue(
                                feature.id(),
                                self.layer.fields().indexFromName(self.label),
                                new_value
                            )

                            # Update status
                            status_idx = self.layer.fields().indexFromName('STATUS')
                            if is_duplicate:
                                self.layer.changeAttributeValue(
                                    feature.id(), status_idx, 'duplicate')
                                if duplicate_feat_id:
                                    self.layer.changeAttributeValue(
                                        duplicate_feat_id, status_idx, 'duplicate')
                            else:
                                self.layer.changeAttributeValue(
                                    feature.id(), status_idx, 'edited')

                            if new_value > self.max_label_value:
                                self.max_label_value = new_value

                            # Trigger repaint to show red status immediately
                            self.layer.triggerRepaint()
                            # self.updateSymbology()

                            # --- Fix for updating previous duplicates ---
                            if old_value is not None:
                                try:
                                    # Find remaining features with the old value
                                    expr_old = QgsExpression(
                                        f'"{self.label}" = {old_value}')
                                    req_old = QgsFeatureRequest(expr_old)
                                    old_peers = [
                                        f for f in self.layer.getFeatures(req_old)]

                                    # If exactly one remains, it is now unique
                                    if len(old_peers) == 1:
                                        peer = old_peers[0]
                                        # Only update if it was marked as duplicate
                                        if peer['STATUS'] == 'duplicate':
                                            if status_idx != -1:
                                                self.layer.changeAttributeValue(
                                                    peer.id(), status_idx, 'cleared')
                                except Exception as e:
                                    print(
                                        f"Error updating old peer status: {e}")
                            # --------------------------------------------

                            messagebar = MessageBar(self.canvas)
                            if is_duplicate:
                                messagebar.pushMessage(
                                    "Duplicate Value",
                                    f"Value {new_value} marked as duplicate",
                                    Qgis.Warning,
                                    2
                                )
                            else:
                                messagebar.pushMessage(
                                    "Success",
                                    f"Label updated from {current_value} to {new_value}",
                                    Qgis.Success,
                                    2
                                )
                    return

        except KeyError:
            messagebar = MessageBar(self.canvas)
            messagebar.pushMessage(
                "Error",
                f"Failed to access '{self.label}' field. Please check layer fields.",
                Qgis.Critical,
                3
            )
            return

        print("No feature found at click location")

    def updateSymbology(self):
        """Update layer symbology"""
        if not self.layer:
            return

        rules = (
            ('Has_Value', f'"{self.label}" >= 1', '#97ee3a', None),
            ('Blank', 'ELSE', '#93b8c3', None),
            ('Edited', '"STATUS" = \'edited\'', '#ffff00', None),
            ('Duplicate', '"STATUS" = \'duplicate\'', '#ff0000', None),
            ('Cleared', '"STATUS" = \'cleared\'', '#0000ff', None),
        )

        rule_based_symbology(self.layer, rules, False)
        # Removed triggerRepaint() - QGIS will auto-refresh

    def updateStatusValues(self):
        """Update status values for all features based on their labels"""
        if not self.layer or not self.layer.isEditable():
            return

        try:
            status_idx = self.layer.fields().indexFromName('STATUS')
            label_idx = self.layer.fields().indexFromName(self.label)

            # Dictionary to track label values
            label_counts = {}

            # First pass: count occurrences of each label value
            for feature in self.layer.getFeatures():
                label_value = feature[self.label]
                if label_value is not None and str(label_value).strip() not in ("", "NULL"):
                    if label_value in label_counts:
                        label_counts[label_value] += 1
                    else:
                        label_counts[label_value] = 1

            # Second pass: update status for each feature
            for feature in self.layer.getFeatures():
                label_value = feature[self.label]

                if label_value is None or str(label_value).strip() in ("", "NULL"):
                    self.layer.changeAttributeValue(
                        feature.id(), status_idx, '')
                elif label_counts[label_value] > 1:
                    self.layer.changeAttributeValue(
                        feature.id(), status_idx, 'duplicate')
                else:
                    current_status = feature['STATUS']
                    # If it was duplicate, mark as cleared.
                    # If it was cleared or edited, preserve it.
                    if current_status == 'duplicate':
                        self.layer.changeAttributeValue(
                            feature.id(), status_idx, 'cleared')
                    elif current_status in ('edited', 'cleared'):
                        # Preserve existing special status
                        pass
                    else:
                        # Otherwise reset to normal (empty status)
                        self.layer.changeAttributeValue(
                            feature.id(), status_idx, '')

            # Removed triggerRepaint() - QGIS will auto-refresh

        except Exception as e:
            print(f"Error updating status values: {str(e)}")


class MessageBar(QgsMessageBar):
    def __init__(self, parent=None):
        super(MessageBar, self).__init__(parent)
        self.parent().installEventFilter(self)

    def showEvent(self, event):
        self.resize(
            QSize(self.parent().geometry().size().width(), self.height()))
        self.move(0, self.parent().geometry().size().height() - self.height())
        self.raise_()

    # def showEvent(self, event):
    #     """
    #     Ensure the active layer is updated when the widget is shown.
    #     """
    #     super().showEvent(event)
    #     self.layer = iface.activeLayer()
    #     if self.layer:
    #         print(f"Active layer updated: {self.layer.name()}")
    #         self.canvas.setLayers([self.layer])

    def eventFilter(self, object, event):
        if event.type() == QtCompat.Resize:
            self.showEvent(None)

        return super(MessageBar, self).eventFilter(object, event)


class LpmCanvas(QMainWindow):
    def __init__(self, iface):
        self.iface = iface
        QMainWindow.__init__(self, iface.mainWindow())
        self.setWindowTitle('Land Parcel Numbering')
        self.setWindowIcon(QIcon(icon))
        self.label = 'LP_NO'

        # Setup canvas
        self.canvas = QgsMapCanvas()
        self.canvas.setCanvasColor(QColor("white"))

        # Enable caching to prevent white screen flash during zoom/pan
        self.canvas.setCachingEnabled(True)
        self.canvas.setParallelRenderingEnabled(True)

        self.setMinimumSize(1000, 500)

        # Setup layout
        self.main_layout = QVBoxLayout()
        self.main_layout.addWidget(self.canvas)
        self.central_widget = QWidget()
        self.central_widget.setLayout(self.main_layout)
        self.setCentralWidget(self.central_widget)

        # Initialize layer
        self.layer = None
        self.label_incrementer = None

        # Remove connection from init
        # self.iface.currentLayerChanged.connect(self.activelyrchanged)

        # Create canvas actions
        self.createCanvasActions()

        # Initial layer setup - get the current active layer
        # Initial layer setup
        self.activelyrchanged()

    def showEvent(self, event):
        """Ensure the active layer is loaded when the window is shown"""
        super().showEvent(event)
        # Connect to layer changes when window opens
        try:
            self.iface.currentLayerChanged.disconnect(self.activelyrchanged)
        except:
            pass
        self.iface.currentLayerChanged.connect(self.activelyrchanged)

        # Trigger update if needed
        self.activelyrchanged()

    def activelyrchanged(self):
        """Handle active layer changes"""
        new_layer = self.iface.activeLayer()

        # Only proceed if layer is vector
        if new_layer and new_layer.type() == QgsMapLayer.VectorLayer:
            # Check if layer actually changed
            if self.layer and self.layer.id() == new_layer.id():
                # Only return if canvas actually has THIS layer loaded
                current_layers = self.canvas.layers()
                if current_layers and current_layers[0].id() == new_layer.id():
                    return

            self.layer = new_layer

            # Set the layer in canvas
            self.canvas.setLayers([self.layer])

            # Set the extent to the layer's extent
            self.canvas.setExtent(self.layer.extent())
            self.canvas.refresh()
        elif self.layer:
            # If new_layer is None but we have a layer, DO NOT clear it.
            pass

    def closeEvent(self, event):
        """Handle window close event"""
        # Safely disconnect from layer changes when window closes
        try:
            self.iface.currentLayerChanged.disconnect(self.activelyrchanged)
        except TypeError:
            pass  # Connection didn't exist, ignore error

        if not self.layer:
            event.accept()
            return

        label_field = self.label
        total = self.layer.featureCount()
        expression = QgsExpression(f"\"{label_field}\" IS NOT NULL")
        request = QgsFeatureRequest(expression)
        fvalues = sum(1 for _ in self.layer.getFeatures(request))
        leftover_labels = total - fvalues

        if leftover_labels > 0:
            msg = (f"Are you sure you want to exit?<br><br>"
                   f"Unlock the Mystery: <b>{leftover_labels}</b> Features are still waiting for their identity! 🌟")

            confirm = QtCompat.message_box_question(self, "Confirmation", msg,
                                                    QtCompat.Yes | QtCompat.No,
                                                    QtCompat.No)
            if confirm != QtCompat.Yes:
                event.ignore()
                return

        # Proceed with exit
        if self.layer.isEditable():
            self.layer.commitChanges()
        self.canvas.setMapTool(self.toolPan)

        # Reset layer symbology
        symbol = QgsSymbol.defaultSymbol(self.layer.geometryType())
        renderer = QgsSingleSymbolRenderer(symbol)
        self.layer.setRenderer(renderer)
        self.layer.triggerRepaint()

        event.accept()

    def createCanvasActions(self):
        """Create canvas toolbar actions"""
        self.toolbar = self.addToolBar("Canvas Actions")

        # Zoom In
        actionZoomIn = QAction(QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/canvas_one/zoomin.svg'))), 'Zoom In', self)
        actionZoomIn.setCheckable(True)
        actionZoomIn.triggered.connect(self.zoomIn)
        self.toolbar.addAction(actionZoomIn)

        # Zoom Out
        actionZoomOut = QAction(QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/canvas_one/zoomout.svg'))), 'Zoom Out', self)
        actionZoomOut.setCheckable(True)
        actionZoomOut.triggered.connect(self.zoomOut)
        self.toolbar.addAction(actionZoomOut)

        # Pan
        actionPan = QAction(QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/canvas_one/pan.svg'))), 'Pan', self)
        actionPan.setCheckable(True)
        actionPan.triggered.connect(self.pan)
        self.toolbar.addAction(actionPan)

        # Smart Select Tool
        actionSmartSelect = QAction(QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/canvas_one/select.svg'))), 'Smart Select', self)
        actionSmartSelect.setCheckable(True)
        actionSmartSelect.triggered.connect(self.activate_select_tool)
        self.toolbar.addAction(actionSmartSelect)

        # Native Deselect Action
        actionDeselect = QAction(QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/canvas_one/deselect.svg'))), 'Deselect Features', self)
        actionDeselect.triggered.connect(self.deselect_features)
        self.toolbar.addAction(actionDeselect)

        actionAutoNumber = QAction(QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/canvas_one/snake_smart.svg'))), 'Auto Number (Serpentine - Smart)', self)
        actionAutoNumber.triggered.connect(self.auto_number_serpentine)
        self.toolbar.addAction(actionAutoNumber)

        # Auto Number (Original)
        actionAutoNumberOrig = QAction(QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/canvas_one/snake_original.svg'))), 'Auto Number (Original)', self)
        actionAutoNumberOrig.triggered.connect(self.auto_number_original)
        self.toolbar.addAction(actionAutoNumberOrig)

        # Manual Numbering Tool
        actionPoint = QAction(QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/crosshair.svg'))), 'Manual Numbering', self)
        actionPoint.setCheckable(True)
        actionPoint.triggered.connect(self.point)
        self.toolbar.addAction(actionPoint)

        # Add Spacer to push next buttons to the right
        spacer = QWidget()
        spacer.setSizePolicy(QtCompat.size_policy_expanding(),
                             QtCompat.size_policy_preferred())
        self.toolbar.addWidget(spacer)

        # Open Attribute Table
        actionOpenTable = QAction(QgsApplication.getThemeIcon(
            '/mActionOpenTable.svg'), 'Open Attribute Table', self)
        actionOpenTable.triggered.connect(
            lambda: iface.showAttributeTable(self.layer))
        self.toolbar.addAction(actionOpenTable)

        # Delete Label Field
        actionDeleteField = QAction(QgsApplication.getThemeIcon(
            '/mActionDeleteAttribute.svg'), 'Delete Label Field', self)
        actionDeleteField.triggered.connect(self.delete_label_field)
        self.toolbar.addAction(actionDeleteField)

        # Group checkable actions
        self.action_group = QActionGroup(self)
        self.action_group.addAction(actionZoomIn)
        self.action_group.addAction(actionZoomOut)
        self.action_group.addAction(actionPan)
        self.action_group.addAction(actionSmartSelect)
        self.action_group.addAction(actionPoint)

        # Initialize label incrementer
        self.label_incrementer = LabelIncrementer(self.canvas, self.layer)
        self.label_incrementer.setAction(actionPoint)

        # Initialize map tools
        self.toolPan = QgsMapToolPan(self.canvas)
        self.toolPan.setAction(actionPan)

        self.toolZoomIn = QgsMapToolZoom(self.canvas, False)
        self.toolZoomIn.setAction(actionZoomIn)

        self.toolZoomOut = QgsMapToolZoom(self.canvas, True)
        self.toolZoomOut.setAction(actionZoomOut)

        # Set default tool
        self.canvas.setMapTool(self.toolPan)

    def drawLine(self):
        self.canvas.setMapTool(self.toolLineDrawing)

    def zoomIn(self):
        self.canvas.setMapTool(self.toolZoomIn)

    def zoomOut(self):
        self.canvas.setMapTool(self.toolZoomOut)

    def pan(self):
        self.canvas.setMapTool(self.toolPan)

    def deselect_features(self):
        if self.layer:
            self.layer.removeSelection()
            # self.canvas.refresh()

    def activate_select_tool(self):
        if self.layer:
            self.select_tool = SmartSelectionTool(self.canvas, self)
            self.canvas.setMapTool(self.select_tool)

    def point(self):
        current_layer = self.iface.activeLayer()

        # Check if there's a layer selected
        if not current_layer:
            QMessageBox.warning(
                self, "Warning", "Please select a layer first!")
            return

        # Check if it's a vector layer
        if current_layer.type() != QgsMapLayer.VectorLayer:
            QMessageBox.warning(
                self, "Warning", "Please select a vector layer!")
            return

        # Ask user to select field for numbering
        fields = [f.name() for f in current_layer.fields() if f.type() in [
            QVariant.Int, QVariant.LongLong, QVariant.String]]

        # Create a simple dialog with editable combo box
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Field for Manual Numbering")
        layout = QVBoxLayout(dialog)

        label = QLabel("Choose existing field or type new field name:")
        layout.addWidget(label)

        field_combo = QComboBox()
        field_combo.setEditable(True)  # Allow typing new field names
        field_combo.addItems(fields)

        # Set default to LP_NO if exists
        if 'LP_NO' in fields:
            field_combo.setCurrentText('LP_NO')
        else:
            field_combo.setEditText('LP_NO')

        layout.addWidget(field_combo)

        button_box = QDialogButtonBox(
            QtCompat.DialogOk | QtCompat.DialogCancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        if QtCompat.exec(dialog) != QtCompat.DialogAccepted:
            return

        field_name = field_combo.currentText().strip()
        if not field_name:
            QMessageBox.warning(self, "Warning", "Please enter a field name!")
            return

        # Update the label field
        self.label = field_name

        # Update the layer reference
        self.layer = current_layer
        if self.label_incrementer:
            self.label_incrementer.layer = current_layer
            # Ensure incrementer uses the selected label field
            self.label_incrementer.label = self.label
            self.label_incrementer.initializeFields()
            # Update max label value with validation when starting numbering

            # Start editing if not already in edit mode
            if not self.layer.isEditable():
                reply = QtCompat.message_box_question(self.canvas.window(), "Edit Mode",
                                                      "Layer is not in edit mode. Start editing for manual numbering?",
                                                      QtCompat.Yes | QtCompat.No, QtCompat.Yes)
                if reply == QtCompat.Yes:
                    self.layer.startEditing()
                else:
                    return

            # Update status values when tool is activated
            self.label_incrementer.updateStatusValues()

        # Set the tool and update display
        self.canvas.setMapTool(self.label_incrementer)
        self.canvas.setLayers([self.layer])
        # self.canvas.refresh()

        # Enable labeling
        enable_label(self.layer.id(), 'Verdana', 8, self.label, 50, False,
                     placement_index=1, font_color='#000')

        # Set symbology rules
        rules = (
            ('Has_Value', f'"{self.label}" >= 1', '#97ee3a', None),
            ('Blank', 'ELSE', '#93b8c3', None),
            ('Auto_Numbered', '"STATUS" = \'auto_numbered\'', '#00ff00', None),
            ('Edited', '"STATUS" = \'edited\'', '#ffff00', None),
            ('Duplicate', '"STATUS" = \'duplicate\'', '#ff0000', None),
        )
        rule_based_symbology(self.layer, rules, False)

    def sort_features_spatially(self, features, pattern='z', algorithm='smart'):
        """
        Sort features using Adjacency-Guided Spatial Sort (Topological Sort).
        1. Rank features spatially (Hybrid Snake Pattern).
        2. Traverse graph greedily: from current feature, pick unvisited neighbor with lowest rank.
        """
        if not features:
            return []

        # --- Step 1: Spatial Ranking ---
        # Use the existing Hybrid Sorting logic to assign a "Rank" to each feature.

        # Calculate centroids and average height
        feature_infos = []
        total_height = 0
        valid_height_count = 0

        for feat in features:
            geom = feat.geometry()
            if not geom:
                continue
            bbox = geom.boundingBox()
            # Use Pole of Inaccessibility for better visual center (handles U-shapes)
            try:
                # Tolerance can be small, e.g., 10% of bbox width (Optimized for performance)
                tolerance = bbox.width() * 0.10
                visual_center_geom = geom.poleOfInaccessibility(tolerance)
                if visual_center_geom:
                    visual_center = visual_center_geom.asPoint()
                else:
                    visual_center = geom.pointOnSurface().asPoint()
            except:
                # Fallback to pointOnSurface or centroid
                visual_center = geom.pointOnSurface().asPoint()

            height = bbox.height()

            # Robustly handle visual_center type (QgsPointXY, QgsPoint, or tuple)
            if hasattr(visual_center, 'x'):
                vx = visual_center.x()
                vy = visual_center.y()
            elif isinstance(visual_center, (tuple, list)) and len(visual_center) >= 2:
                vx = visual_center[0]
                vy = visual_center[1]
            else:
                # Absolute fallback
                center = bbox.center()
                vx = center.x()
                vy = center.y()

            feature_infos.append({
                'feature': feat,
                'id': feat.id(),
                'x': vx,
                'y': vy,
                'bbox_top': bbox.yMaximum(),
                'height': height,
                'geometry': geom
            })

            if height > 0:
                total_height += height
                valid_height_count += 1

        if not feature_infos:
            return []

        # Calculate average height
        if valid_height_count > 0:
            avg_height = total_height / valid_height_count
        else:
            # Handle points or zero-height features
            total_bounds = QgsRectangle(
                feature_infos[0]['x'], feature_infos[0]['y'], feature_infos[0]['x'], feature_infos[0]['y'])
            for info in feature_infos:
                total_bounds.combineExtentWith(QgsGeometry(
                    info['x'], info['y'], info['x'], info['y']).boundingBox())

            import math
            avg_height = total_bounds.height() / math.sqrt(len(features)
                                                           ) if len(features) > 0 else 0
            if avg_height == 0:
                avg_height = 1.0

        # Hybrid Logic for Ranking
        large_feature_threshold = avg_height * 1.5
        for info in feature_infos:
            if info['height'] > large_feature_threshold:
                info['y'] = info['bbox_top'] - (avg_height * 0.5)

        row_tolerance = avg_height * 0.75

        # Sort by bbox_top descending (highest feature first), then by X ascending (left to right)
        # This ensures the topmost feature is ALWAYS first, regardless of hybrid logic adjustments
        feature_infos.sort(key=lambda k: (-k['bbox_top'], k['x']))

        # Overlap-Based Row Grouping
        # Use bbox_top for grouping to maintain correct top-to-bottom order
        # The adjusted 'y' values are only used for graph traversal, not initial ranking

        rows = []
        current_row = []

        if feature_infos:
            current_row_top = feature_infos[0]['bbox_top']
            current_row_height = feature_infos[0]['height']

            # Tolerance: 0.75 * avg_height.
            # 0.5 was too strict (split wavy rows). 1.0 was too loose (merged rows).
            row_tolerance = avg_height * 0.75

            for info in feature_infos:
                # Check vertical distance from the row's top edge
                # Use bbox_top to maintain correct ordering
                if abs(info['bbox_top'] - current_row_top) <= row_tolerance:
                    current_row.append(info)
                    # Update running average top to follow the row's drift
                    sum_top = sum(item['bbox_top'] for item in current_row)
                    current_row_top = sum_top / len(current_row)
                else:
                    rows.append(current_row)
                    current_row = [info]
                    current_row_top = info['bbox_top']
            if current_row:
                rows.append(current_row)

        # Create Ranked List
        ranked_features = []
        for i, row in enumerate(rows):
            row.sort(key=lambda k: k['x'])
            if pattern == 'snake' and i % 2 == 1:
                row.reverse()
            for info in row:
                ranked_features.append(info)

        # Assign Rank
        for rank, info in enumerate(ranked_features):
            info['rank'] = rank

        # --- Step 2: Graph Traversal ---

        # Build spatial index for fast neighbor lookup
        spatial_index = QgsSpatialIndex()
        id_to_info = {info['id']: info for info in feature_infos}
        for info in feature_infos:
            spatial_index.addFeature(info['feature'])

        sorted_features = []
        visited_ids = set()

        # Start with the feature that has Rank 0 (Top-Left-most)
        current_info = ranked_features[0]

        while len(sorted_features) < len(features):
            sorted_features.append(current_info['feature'])
            visited_ids.add(current_info['id'])

            if len(sorted_features) == len(features):
                break

            # Find unvisited neighbors
            # Use intersection with a small buffer to handle touching boundaries
            geom = current_info['geometry']
            # Buffer slightly to ensure intersection with touching neighbors
            # Use a relative buffer size based on avg_height
            buffer_dist = avg_height * 0.05
            search_geom = geom.buffer(buffer_dist, 5)

            neighbor_ids = spatial_index.intersects(search_geom.boundingBox())

            candidates = []
            for nid in neighbor_ids:
                if nid == current_info['id'] or nid in visited_ids:
                    continue

                neighbor_info = id_to_info[nid]
                # Verify actual intersection
                intersection = geom.intersection(neighbor_info['geometry'])
                if not intersection.isEmpty():
                    # Calculate shared length to distinguish Edge vs Vertex sharing
                    shared_length = intersection.length()
                    candidates.append({
                        'info': neighbor_info,
                        'shared_length': shared_length,
                        'rank': neighbor_info['rank']
                    })

            if candidates:
                edge_tolerance = avg_height * 0.01

                if algorithm == 'smart':
                    # --- SMART ALGORITHM ---
                    # 1. Sort by Rank ONLY to find the "Snake" direction baseline
                    candidates.sort(key=lambda k: k['rank'])
                    best_rank = candidates[0]['rank']

                    # 2. Define a "Local Window" (e.g., 5 ranks)
                    rank_tolerance = 5
                    local_candidates = [
                        c for c in candidates if c['rank'] <= best_rank + rank_tolerance]

                    # 3. Pick the best connected feature from the local group
                    local_candidates.sort(
                        key=lambda k: k['shared_length'], reverse=True)
                    next_info = local_candidates[0]['info']

                else:
                    # --- ORIGINAL ALGORITHM (STRICT SNAKE) ---
                    # Priority: Strict Snake Pattern (Rank) > Shared Length
                    candidates.sort(key=lambda k: k['rank'])
                    next_info = candidates[0]['info']

            else:
                # Dead End: Jump to the unvisited feature with the lowest Rank
                next_info = None
                for info in ranked_features:
                    if info['id'] not in visited_ids:
                        next_info = info
                        break

            if next_info:
                current_info = next_info
            else:
                break  # Should not happen if loop condition is correct
        return sorted_features

    def auto_number_serpentine(self):
        """
        Trigger auto-numbering on the current selection (Smart Algorithm).
        """
        if not self.layer:
            return

        selected_features = self.layer.selectedFeatures()
        if selected_features:
            self.perform_auto_numbering(
                selected_features, pattern='snake', algorithm='smart')
        else:
            reply = QtCompat.message_box_question(self.canvas.window(), "Auto Number",
                                                  "No features selected. Number all features in the layer?",
                                                  QtCompat.Yes | QtCompat.No, QtCompat.No)
            if reply == QtCompat.Yes:
                self.perform_auto_numbering(
                    list(self.layer.getFeatures()), pattern='snake', algorithm='smart')

    def auto_number_original(self):
        """
        Trigger auto-numbering on the current selection (Original Algorithm).
        """
        if not self.layer:
            return

        selected_features = self.layer.selectedFeatures()
        if selected_features:
            self.perform_auto_numbering(
                selected_features, pattern='snake', algorithm='original')
        else:
            reply = QtCompat.message_box_question(self.canvas.window(), "Auto Number",
                                                  "No features selected. Number all features in the layer?",
                                                  QtCompat.Yes | QtCompat.No, QtCompat.No)
            if reply == QtCompat.Yes:
                self.perform_auto_numbering(
                    list(self.layer.getFeatures()), pattern='snake', algorithm='original')

    def perform_auto_numbering(self, features, pattern='snake', algorithm='smart'):
        """
        Execute auto numbering logic on provided features.
        """
        if not self.layer.isEditable():
            reply = QtCompat.message_box_question(self.canvas.window(), "Edit Mode",
                                                  "Layer is not in edit mode. Start editing?",
                                                  QtCompat.Yes | QtCompat.No, QtCompat.Yes)
            if reply == QtCompat.Yes:
                self.layer.startEditing()
            else:
                return

        if not features:
            return

        # Custom Dialog for Field Name and Start Number
        dialog = AutoNumberDialog(self.layer, self.canvas.window())
        if QtCompat.exec(dialog) != QtCompat.DialogAccepted:
            return

        field_name, start_num = dialog.get_values()

        # Update class-level label so manual tool uses it too
        self.label = field_name
        idx = self.layer.fields().indexFromName(field_name)
        if idx == -1:
            # Ensure layer is in edit mode before creating field
            if not self.layer.isEditable():
                self.layer.startEditing()

            # Create field immediately
            self.layer.addAttribute(QgsField(field_name, QVariant.Int))
            # Verify creation
            idx = self.layer.fields().indexFromName(field_name)
            if idx == -1:
                QMessageBox.critical(self.canvas.window(
                ), "Error", f"Failed to create field '{field_name}'.")
                return

        # Ensure STATUS field exists for tracking
        status_idx = self.layer.fields().indexFromName('STATUS')
        if status_idx == -1:
            # Ensure layer is in edit mode before creating field
            if not self.layer.isEditable():
                self.layer.startEditing()

            self.layer.addAttribute(QgsField('STATUS', QVariant.String))
            print("Created STATUS field for auto-numbering")

        # Check for existing values in the selected features
        existing_values_count = 0
        for feat in features:
            attrs = feat.attributes()
            if idx < len(attrs):
                val = attrs[idx]
                if val != None and val != NULL:  # Check for NULL/None
                    try:
                        if int(val) > 0:
                            existing_values_count += 1
                    except:
                        pass
            else:
                pass

        skip_existing = False
        if existing_values_count > 0:
            msg = f"{existing_values_count} features already have values in '{field_name}'.\nDo you want to overwrite them?"
            reply = QtCompat.message_box_question(self.canvas.window(), "Existing Values", msg,
                                                  QtCompat.Yes | QtCompat.No | QtCompat.Cancel, QtCompat.No)

            if reply == QtCompat.Cancel:
                return
            elif reply == QtCompat.No:
                skip_existing = True
                # Filter features to only those without values (or 0/NULL)
                features_to_number = []
                for feat in features:
                    val = feat.attributes()[idx]
                    is_valid = False
                    try:
                        if val != None and val != NULL and int(val) > 0:
                            is_valid = True
                    except:
                        pass

                    if not is_valid:
                        features_to_number.append(feat)

                features = features_to_number
                if not features:
                    QMessageBox.information(self.canvas.window(
                    ), "Info", "No features to number after skipping existing values.")
                    return

        # Sort features
        sorted_features = self.sort_features_spatially(
            features, pattern, algorithm)

        # Apply numbering
        self.layer.beginEditCommand(f"Auto Number ({pattern})")
        try:
            current_num = start_num

            # Ensure we have the latest field index
            idx = self.layer.fields().indexFromName(field_name)
            status_idx = self.layer.fields().indexFromName('STATUS')

            # 1. Pre-scan existing values (O(N))
            # Map value -> list of feature IDs
            existing_values = {}

            # Get IDs of features we are about to re-number to exclude their OLD values
            ids_to_renumber = set(f.id() for f in sorted_features)

            # Scan ALL features in layer
            all_feats = self.layer.getFeatures(
                QgsFeatureRequest().setSubsetOfAttributes([idx, status_idx]))
            for f in all_feats:
                if f.id() in ids_to_renumber:
                    continue  # Skip features we are about to change

                val = f.attributes()[idx]  # index of label field
                if val != None and val != NULL:
                    try:
                        v_int = int(val)
                        if v_int not in existing_values:
                            existing_values[v_int] = []
                        existing_values[v_int].append(f.id())
                    except:
                        pass

            # 2. Assign and Validate
            for feat in sorted_features:
                # Set the new number
                self.layer.changeAttributeValue(feat.id(), idx, current_num)

                # Check for duplicates
                status = 'auto_numbered'
                if current_num in existing_values:
                    status = 'duplicate'
                    # Mark the conflicting existing features as duplicate too!
                    if status_idx != -1:
                        for conflict_id in existing_values[current_num]:
                            self.layer.changeAttributeValue(
                                conflict_id, status_idx, 'duplicate')

                # Update current feature status
                if status_idx != -1:
                    self.layer.changeAttributeValue(
                        feat.id(), status_idx, status)

                # Add this assignment to our map for future collisions in this same loop
                if current_num not in existing_values:
                    existing_values[current_num] = []
                existing_values[current_num].append(feat.id())

                current_num += 1

            self.layer.triggerRepaint()

            # Enable labeling for the newly numbered features
            enable_label(self.layer.id(), 'Verdana', 8, self.label, 50, False,
                         placement_index=1, font_color='#000')

            self.layer.endEditCommand()
            # self.canvas.refresh()
            QMessageBox.information(
                self.canvas.window(), "Success", "Auto-numbering completed.")

        except Exception as e:
            self.layer.destroyEditCommand()
            QMessageBox.critical(self.canvas.window(),
                                 "Error", f"An error occurred: {str(e)}")

    def delete_label_field(self):
        if not self.layer:
            return

        # Check if editable
        if not self.layer.isEditable():
            reply = QtCompat.message_box_question(self.canvas.window(), "Edit Mode",
                                                  "Layer is not in edit mode. Start editing to delete fields?",
                                                  QtCompat.Yes | QtCompat.No, QtCompat.Yes)
            if reply == QtCompat.Yes:
                self.layer.startEditing()
            else:
                return

        dialog = DeleteAttributesDialog(self.layer, self.canvas.window())
        if QtCompat.exec(dialog) == QtCompat.DialogAccepted:
            indexes = dialog.get_selected_indexes()
            if indexes:
                reply = QtCompat.message_box_question(self.canvas.window(), "Delete Fields",
                                                      f"Are you sure you want to delete {len(indexes)} field(s)?",
                                                      QtCompat.Yes | QtCompat.No, QtCompat.No)
                if reply == QtCompat.Yes:
                    self.layer.deleteAttributes(indexes)
                    self.layer.updateFields()
            else:
                QMessageBox.information(
                    self.canvas.window(), "Info", "No fields selected.")


lpno = LpmCanvas(iface)

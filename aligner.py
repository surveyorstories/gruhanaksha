from qgis.gui import QgsMapTool, QgsRubberBand, QgsSnapIndicator
from qgis.core import (QgsWkbTypes, QgsGeometry, QgsPointXY, QgsProject,
                       QgsSnappingConfig, Qgis, QgsMapLayer, QgsTolerance)
from qgis.PyQt import QtCore
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QInputDialog, QMessageBox, QToolBar, QAction
import math
from qgis.utils import iface

# Qt5/Qt6 compatibility layer
try:
    # Qt6
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtGui import QColor
    QT_VERSION = 6
    
    # Qt6 enum access
    class QtCompat:
        LeftButton = Qt.MouseButton.LeftButton
        RightButton = Qt.MouseButton.RightButton
        CrossCursor = Qt.CursorShape.CrossCursor
        DashLine = Qt.PenStyle.DashLine
        Yes = QMessageBox.StandardButton.Yes
        No = QMessageBox.StandardButton.No
except AttributeError:
    # Qt5
    QT_VERSION = 5
    
    # Qt5 enum access
    class QtCompat:
        LeftButton = Qt.LeftButton
        RightButton = Qt.RightButton
        CrossCursor = Qt.CrossCursor
        DashLine = Qt.DashLine
        Yes = QMessageBox.Yes
        No = QMessageBox.No


class AlignTool(QgsMapTool):
    def __init__(self, iface, source_layer):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.source_layer = source_layer
        self.project = QgsProject.instance()

        # Tool state management
        self.is_active = False
        self.operation_in_progress = False
        self.signals_connected = False

        # Store current snapping state
        self.snapping_enabled = self.project.snappingConfig().enabled()

        # Use QGIS default snap indicator
        self.snap_indicator = QgsSnapIndicator(self.canvas)

        # Rubber bands for visual feedback
        self.point_band = QgsRubberBand(self.canvas, QgsWkbTypes.PointGeometry)
        self.point_band.setColor(QColor(255, 0, 0, 150))
        self.point_band.setWidth(5)

        self.mapping_band_1 = QgsRubberBand(
            self.canvas, QgsWkbTypes.LineGeometry)
        self.mapping_band_1.setColor(QColor(0, 0, 255, 150))
        self.mapping_band_1.setWidth(1)
        self.mapping_band_1.setLineStyle(QtCompat.DashLine)

        self.mapping_band_2 = QgsRubberBand(
            self.canvas, QgsWkbTypes.LineGeometry)
        self.mapping_band_2.setColor(QColor(0, 0, 255, 150))
        self.mapping_band_2.setWidth(1)
        self.mapping_band_2.setLineStyle(QtCompat.DashLine)

        self.selected_points = []
        self.selected_vertices = []
        self.selected_feature = None
        self.step = 0
        self.snapped_point = None
        self.cancel_operation = False

    def activate(self):
        """Called when tool is activated"""
        super().activate()
        self.is_active = True
        self.reset_tool_state()

        # Connect signals only when tool is activated
        self.connect_signals()

        # Show initial instruction
        self.iface.messageBar().pushMessage(
            "Align Tool",
            f"Tool activated on layer '{self.source_layer.name()}'. Left-click to select points, right-click to reset.",
            Qgis.Info, 3)

        # Set cursor
        self.canvas.setCursor(QtCompat.CrossCursor)

    def connect_signals(self):
        """Connect to QGIS signals"""
        if not self.signals_connected:
            try:
                self.project.snappingConfigChanged.connect(
                    self.on_snapping_config_changed)
                self.signals_connected = True
            except Exception as e:
                print(f"Failed to connect signals: {e}")

    def disconnect_signals(self):
        """Disconnect from QGIS signals"""
        if self.signals_connected:
            try:
                self.project.snappingConfigChanged.disconnect(
                    self.on_snapping_config_changed)
                self.signals_connected = False
            except Exception as e:
                print(f"Failed to disconnect signals: {e}")

    def on_snapping_config_changed(self):
        """Handle snapping configuration changes - only when tool is active"""
        if not self.is_active:
            return

        new_snapping_state = self.project.snappingConfig().enabled()

        if new_snapping_state != self.snapping_enabled:
            self.snapping_enabled = new_snapping_state
            status = "enabled" if self.snapping_enabled else "disabled"
            self.iface.messageBar().pushMessage(
                "Align Tool", f"Snapping {status}", Qgis.Info, 2)

            # Clear any existing snap indicator when snapping is disabled
            if not self.snapping_enabled:
                self.snap_indicator.setVisible(False)

    def get_project_snapping_config(self):
        """Get the current project snapping configuration without modifying it"""
        project = QgsProject.instance()
        return project.snappingConfig()

    def canvasPressEvent(self, event):
        # Handle right-click to reset
        if event.button() == QtCompat.RightButton and self.is_active:
            self.reset_operation()
            self.iface.messageBar().pushMessage(
                "Align Tool", "Operation reset. Click to select the first source vertex.", Qgis.Info, 3)
            return
        
        if event.button() != QtCompat.LeftButton or not self.is_active:
            return

        # Prevent new operations while one is in progress
        if self.operation_in_progress:
            self.iface.messageBar().pushMessage(
                "Align Tool", "Operation in progress. Please wait...", Qgis.Warning, 2)
            return

        # Use the existing project snapping configuration
        snapping_utils = self.canvas.snappingUtils()
        snap_match = snapping_utils.snapToMap(event.pos())
        click_point = snap_match.point() if snap_match.isValid(
        ) else self.toMapCoordinates(event.pos())

        if self.step == 0:
            # Step 0: First source vertex selection - prioritize source layer
            source_vertex_match = self.find_source_layer_vertex(click_point)

            if source_vertex_match:
                vertex, feature = source_vertex_match
                self.selected_vertices.append(vertex)
                self.point_band.addPoint(vertex)
                self.selected_feature = feature
                self.step += 1
                detection_method = "snapped" if (snap_match.isValid(
                ) and snap_match.layer() == self.source_layer) else "detected"
                self.iface.messageBar().pushMessage(
                    "Align Tool", f"First source vertex {detection_method} from source layer. Select the corresponding target point.", Qgis.Info, 3)
            else:
                if snap_match.isValid() and snap_match.layer() != self.source_layer:
                    layer_name = snap_match.layer().name() if snap_match.layer() else "unknown"
                    self.iface.messageBar().pushMessage(
                        "Align Tool", f"Snapped to layer '{layer_name}'. Please select a vertex from source layer '{self.source_layer.name()}'.", Qgis.Warning, 3)
                else:
                    self.iface.messageBar().pushMessage(
                        "Align Tool", "No vertex found from source layer. Click closer to a vertex.", Qgis.Warning, 3)

        elif self.step == 1:
            # Step 1: First target point selection - can snap to any layer
            self.selected_points.append(click_point)
            self.mapping_band_1.reset(QgsWkbTypes.LineGeometry)
            self.mapping_band_1.addPoint(self.selected_vertices[0])
            self.mapping_band_1.addPoint(click_point)
            self.step += 1
            snap_info = f" (snapped to {snap_match.layer().name()})" if snap_match.isValid(
            ) else ""
            self.iface.messageBar().pushMessage(
                "Align Tool", f"First target point selected{snap_info}. Select the second source vertex from source layer.", Qgis.Info, 2)

        elif self.step == 2:
            # Step 2: Second source vertex selection - prioritize source layer
            source_vertex_match = self.find_source_layer_vertex(click_point)

            if source_vertex_match:
                vertex, feature = source_vertex_match
                self.selected_vertices.append(vertex)
                self.point_band.addPoint(vertex)
                self.step += 1
                detection_method = "snapped" if (snap_match.isValid(
                ) and snap_match.layer() == self.source_layer) else "detected"
                self.iface.messageBar().pushMessage(
                    "Align Tool", f"Second source vertex {detection_method} from source layer. Select the second target point.", Qgis.Info, 2)
            else:
                if snap_match.isValid() and snap_match.layer() != self.source_layer:
                    layer_name = snap_match.layer().name() if snap_match.layer() else "unknown"
                    self.iface.messageBar().pushMessage(
                        "Align Tool", f"Snapped to layer '{layer_name}'. Please select a vertex from source layer '{self.source_layer.name()}'.", Qgis.Warning, 3)
                else:
                    self.iface.messageBar().pushMessage(
                        "Align Tool", "No vertex found from source layer. Click closer to a vertex.", Qgis.Warning, 3)

        elif self.step == 3:
            # Step 3: Second target point selection - can snap to any layer
            self.selected_points.append(click_point)
            self.mapping_band_2.reset(QgsWkbTypes.LineGeometry)
            self.mapping_band_2.addPoint(self.selected_vertices[1])
            self.mapping_band_2.addPoint(click_point)
            self.prompt_user_for_alignment()

    def find_source_layer_vertex(self, click_point):
        """Find the best vertex match from the source layer, prioritizing snapped points"""
        # First, check if we have a valid snap from the source layer
        snapping_utils = self.canvas.snappingUtils()
        snap_match = snapping_utils.snapToMap(self.canvas.mouseLastXY())

        if snap_match.isValid() and snap_match.layer() == self.source_layer:
            feature = snap_match.layer().getFeature(snap_match.featureId())
            return (snap_match.point(), feature)

        # If no snap or snap is from wrong layer, do manual detection
        # Get tolerance from snapping settings or use default
        tolerance = 10  # map units - could make this configurable
        if self.snapping_enabled:
            snap_config = self.project.snappingConfig()
            if snap_config.tolerance() > 0:
                tolerance = snap_config.tolerance()
                if snap_config.units() == QgsTolerance.Pixels:
                    tolerance = tolerance * self.canvas.mapUnitsPerPixel()

        closest_feature = None
        closest_vertex = None
        min_distance = tolerance

        # Search all features in source layer
        for feature in self.source_layer.getFeatures():
            vertices = self.extract_vertices(feature.geometry())
            for vertex in vertices:
                distance = math.sqrt((click_point.x() - vertex.x())**2 +
                                     (click_point.y() - vertex.y())**2)
                if distance < min_distance:
                    min_distance = distance
                    closest_vertex = vertex
                    closest_feature = feature

        if closest_vertex and closest_feature:
            return (closest_vertex, closest_feature)

        return None

    def canvasMoveEvent(self, event):
        if not self.is_active or self.operation_in_progress:
            return

        # Only show snap indicator if snapping is enabled
        if not self.snapping_enabled:
            self.snap_indicator.setVisible(False)
            return

        # Use QGIS default snap indicator
        mouse_pos = event.pos()
        snapping_utils = self.canvas.snappingUtils()
        snap_match = snapping_utils.snapToMap(mouse_pos)

        # Let QGIS handle the snap indicator display
        if snap_match.isValid():
            self.snap_indicator.setMatch(snap_match)
            self.snap_indicator.setVisible(True)
        else:
            self.snap_indicator.setVisible(False)

    def get_closest_feature(self, point):
        """Find the closest feature in the source layer"""
        closest_feature = None
        min_distance = float('inf')
        point_geom = QgsGeometry.fromPointXY(point)

        for feature in self.source_layer.getFeatures():
            distance = feature.geometry().distance(point_geom)
            if distance < min_distance:
                min_distance = distance
                closest_feature = feature

        return closest_feature

    def get_closest_vertex(self, vertices, point):
        """Find the closest vertex to a given point"""
        closest_vertex = None
        min_distance = float('inf')
        point_geom = QgsGeometry.fromPointXY(point)

        for vertex in vertices:
            vertex_geom = QgsGeometry.fromPointXY(vertex)
            distance = vertex_geom.distance(point_geom)
            if distance < min_distance:
                min_distance = distance
                closest_vertex = vertex

        return closest_vertex

    def extract_vertices(self, geometry):
        """Extract all vertices from a geometry"""
        vertices = []

        if geometry.isMultipart():
            for part in geometry.constParts():
                vertices.extend(part.vertices())
        else:
            vertices.extend(geometry.vertices())

        return [QgsPointXY(v.x(), v.y()) for v in vertices]

    def transform_geometry(self, geometry, dx1, dy1, rotation_angle, scale_factor=1.0):
        """Transform a geometry using translation, rotation, and scaling"""
        if geometry.isMultipart():
            parts = []
            for part in geometry.constParts():
                transformed_part = self.transform_part(
                    part, dx1, dy1, rotation_angle, scale_factor)
                parts.append(transformed_part)

            if geometry.type() == QgsWkbTypes.LineGeometry:
                return QgsGeometry.fromMultiPolylineXY(parts)
            elif geometry.type() == QgsWkbTypes.PolygonGeometry:
                return QgsGeometry.fromMultiPolygonXY([parts])
        else:
            transformed_part = self.transform_part(
                geometry.constGet(), dx1, dy1, rotation_angle, scale_factor)

            if geometry.type() == QgsWkbTypes.LineGeometry:
                return QgsGeometry.fromPolylineXY(transformed_part)
            elif geometry.type() == QgsWkbTypes.PolygonGeometry:
                return QgsGeometry.fromPolygonXY([transformed_part])

    def transform_part(self, part, dx1, dy1, rotation_angle, scale_factor):
        """Transform a single geometry part"""
        transformed_vertices = []
        for v in part.vertices():
            vertex = QgsPointXY(v.x(), v.y())

            # Transform relative to first selected vertex
            rel_x = vertex.x() - self.selected_vertices[0].x()
            rel_y = vertex.y() - self.selected_vertices[0].y()

            # Scale
            scaled_x = rel_x * scale_factor
            scaled_y = rel_y * scale_factor

            # Translate
            translated = QgsPointXY(
                scaled_x + self.selected_vertices[0].x() + dx1,
                scaled_y + self.selected_vertices[0].y() + dy1
            )

            # Rotate
            rotated = self.rotate_point(
                translated, self.selected_points[0], rotation_angle)
            transformed_vertices.append(rotated)

        return transformed_vertices

    def rotate_point(self, point, origin, angle):
        """Rotate a point around an origin by a given angle"""
        cos_angle = math.cos(angle)
        sin_angle = math.sin(angle)
        dx = point.x() - origin.x()
        dy = point.y() - origin.y()
        new_x = cos_angle * dx - sin_angle * dy + origin.x()
        new_y = sin_angle * dx + cos_angle * dy + origin.y()
        return QgsPointXY(new_x, new_y)

    def prompt_user_for_alignment(self):
        """Prompt user to choose between scaling and alignment only"""
        self.operation_in_progress = True

        options = ["Scale", "Align Only", "Cancel"]
        choice, ok = QInputDialog.getItem(
            self.iface.mainWindow(),
            "Align Tool",
            "Choose alignment operation:",
            options,
            0,
            False)

        if ok and choice:
            if choice == "Scale":
                self.scale_feature()
            elif choice == "Align Only":
                self.align_feature()
            else:  # Cancel
                self.reset_operation()
        else:
            self.reset_operation()

    def process_selected_features(self):
        """Calculate transformation parameters from selected points and vertices"""
        dx1 = self.selected_points[0].x() - self.selected_vertices[0].x()
        dy1 = self.selected_points[0].y() - self.selected_vertices[0].y()

        original_angle = math.atan2(
            self.selected_vertices[1].y() - self.selected_vertices[0].y(),
            self.selected_vertices[1].x() - self.selected_vertices[0].x()
        )
        target_angle = math.atan2(
            self.selected_points[1].y() - self.selected_points[0].y(),
            self.selected_points[1].x() - self.selected_points[0].x()
        )
        rotation_angle = target_angle - original_angle

        return dx1, dy1, rotation_angle

    def align_feature(self):
        """Align feature without scaling"""
        if not (len(self.selected_points) == 2 and len(self.selected_vertices) == 2):
            self.reset_operation()
            return

        try:
            dx1, dy1, rotation_angle = self.process_selected_features()

            self.source_layer.startEditing()
            features_to_process = self.source_layer.selectedFeatures() or [
                self.selected_feature]

            processed_count = 0
            for feature in features_to_process:
                if feature is not None:
                    new_geom = self.transform_geometry(
                        feature.geometry(), dx1, dy1, rotation_angle)
                    if new_geom and new_geom.isGeosValid():
                        self.source_layer.changeGeometry(
                            feature.id(), new_geom)
                        processed_count += 1

            self.iface.messageBar().pushMessage(
                "Align Tool", f"Successfully aligned {processed_count} feature(s). Ready for next alignment.", Qgis.Success, 3)

            # Automatically reset for next operation
            self.reset_operation()

        except Exception as e:
            self.iface.messageBar().pushMessage(
                "Align Tool", f"Error during alignment: {str(e)}", Qgis.Critical, 5)
            self.reset_operation()

    def scale_feature(self):
        """Scale and align feature"""
        if not (len(self.selected_points) == 2 and len(self.selected_vertices) == 2):
            self.reset_operation()
            return

        try:
            dx1, dy1, rotation_angle = self.process_selected_features()

            original_distance = math.sqrt(
                (self.selected_vertices[1].x() - self.selected_vertices[0].x())**2 +
                (self.selected_vertices[1].y() -
                 self.selected_vertices[0].y())**2
            )
            target_distance = math.sqrt(
                (self.selected_points[1].x() - self.selected_points[0].x())**2 +
                (self.selected_points[1].y() - self.selected_points[0].y())**2
            )

            scale_factor = target_distance / original_distance if original_distance != 0 else 1

            self.source_layer.startEditing()
            features_to_process = self.source_layer.selectedFeatures() or [
                self.selected_feature]

            processed_count = 0
            for feature in features_to_process:
                if feature is not None:
                    new_geom = self.transform_geometry(
                        feature.geometry(), dx1, dy1, rotation_angle, scale_factor)
                    if new_geom and new_geom.isGeosValid():
                        self.source_layer.changeGeometry(
                            feature.id(), new_geom)
                        processed_count += 1

            self.iface.messageBar().pushMessage(
                "Align Tool", f"Successfully scaled and aligned {processed_count} feature(s). Scale factor: {scale_factor:.3f}. Ready for next alignment.", Qgis.Success, 4)

            # Automatically reset for next operation
            self.reset_operation()

        except Exception as e:
            self.iface.messageBar().pushMessage(
                "Align Tool", f"Error during scaling: {str(e)}", Qgis.Critical, 5)
            self.reset_operation()

    def ask_continue_or_finish(self):
        """Ask user if they want to continue with another alignment or finish"""
        reply = QMessageBox.question(
            self.iface.mainWindow(),
            "Align Tool - Operation Complete",
            "Alignment completed successfully!\n\nDo you want to perform another alignment?",
            QtCompat.Yes | QtCompat.No,
            QtCompat.Yes
        )

        if reply == QtCompat.Yes:
            self.reset_operation()
            self.iface.messageBar().pushMessage(
                "Align Tool", "Ready for next alignment. Click to select the first source vertex.", Qgis.Info, 3)
        else:
            self.finish_tool()

    def reset_operation(self):
        """Reset current operation but keep tool active"""
        self.operation_in_progress = False
        self.clear_visual_feedback()
        self.selected_points.clear()
        self.selected_vertices.clear()
        self.selected_feature = None
        self.step = 0
        self.snapped_point = None

    def reset_tool_state(self):
        """Reset all tool state on activation"""
        self.operation_in_progress = False
        self.reset_operation()

    def clear_visual_feedback(self):
        """Clear all rubber bands and visual indicators"""
        self.snap_indicator.setVisible(False)
        self.point_band.reset(QgsWkbTypes.PointGeometry)
        self.mapping_band_1.reset(QgsWkbTypes.LineGeometry)
        self.mapping_band_2.reset(QgsWkbTypes.LineGeometry)

    def finish_tool(self):
        """Properly finish and deactivate the tool"""
        self.iface.messageBar().pushMessage(
            "Align Tool", "Tool finished. Select another tool to continue.", Qgis.Info, 3)

        # Properly disconnect signals before deactivating
        self.disconnect_signals()

        # Deactivate this tool and return to default pan tool
        self.canvas.unsetMapTool(self)

    def deactivate(self):
        """Called when tool is deactivated"""
        print("AlignTool deactivating...")  # Debug message

        self.is_active = False
        self.operation_in_progress = False

        # Disconnect signals first
        self.disconnect_signals()

        # Clear all visual feedback
        self.clear_visual_feedback()
        self.reset_operation()

        # Restore default cursor
        self.canvas.unsetCursor()

        print("AlignTool deactivated successfully")  # Debug message
        super().deactivate()

    def reset(self):
        """Legacy method - now calls reset_operation for compatibility"""
        self.reset_operation()


def init_align_tool():
    """Initialize the align tool with the active layer"""
    active_layer = iface.activeLayer()

    try:
        if active_layer and active_layer.type() == QgsMapLayer.VectorLayer:
            # Print active layer information
            print(f"Active Layer Name: {active_layer.name()}")
            print(f"Active Layer ID: {active_layer.id()}")
            print(
                f"Geometry Type: {QgsWkbTypes.geometryDisplayString(active_layer.geometryType())}")

            # Check if the layer is either a line or polygon
            if active_layer.geometryType() in (QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry):
                # Deactivate any existing align tool first
                current_tool = iface.mapCanvas().mapTool()
                if isinstance(current_tool, AlignTool):
                    print("Deactivating existing AlignTool...")
                    current_tool.deactivate()

                tool = AlignTool(iface, active_layer)
                iface.mapCanvas().setMapTool(tool)
                layer_type = "Line" if active_layer.geometryType(
                ) == QgsWkbTypes.LineGeometry else "Polygon"

                # Check snapping status
                project = QgsProject.instance()
                snap_config = project.snappingConfig()
                snap_status = "enabled" if snap_config.enabled() else "disabled"

                iface.messageBar().pushMessage(
                    "Align Tool",
                    f"{layer_type} layer selected. Alignment tool activated. Snapping is {snap_status}.",
                    level=Qgis.Info, duration=2)

                if not snap_config.enabled():
                    iface.messageBar().pushMessage(
                        "Tip",
                        "Enable snapping in Project > Snapping Options for easier vertex selection.",
                        level=Qgis.Info, duration=5)
            else:
                geometry_type_name = QgsWkbTypes.geometryDisplayString(
                    active_layer.geometryType())
                iface.messageBar().pushMessage(
                    f"Selected layer is of type '{geometry_type_name}', which is neither a line nor a polygon. Tool not initialized.",
                    level=Qgis.Warning, duration=3)
        else:
            raise ValueError("No active vector layer selected.")

    except Exception as e:
        QMessageBox.critical(iface.mainWindow(), "Error", str(e))

# # Initialize the tool
# init_align_tool()
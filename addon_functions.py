from qgis.core import (
    QgsProject, QgsMapLayer, Qgis, QgsTextFormat, QgsTextBufferSettings, QgsLabelPlacementSettings,
    QgsSymbol, QgsRuleBasedRenderer, QgsStyle, QgsWkbTypes, QgsRendererCategory, QgsCategorizedSymbolRenderer,
    QgsVectorLayer, QgsPalLayerSettings, QgsVectorLayerSimpleLabeling, QgsFeatureRequest,
    QgsPrintLayout, QgsLayoutItemMap, QgsLayoutItemLabel, QgsLayoutItemPage, QgsReadWriteContext,
    QgsLayoutSize, QgsLayoutPoint, QgsUnitTypes, QgsVectorFileWriter, QgsField, QgsFeature, QgsMarkerSymbol,
    QgsLayoutItemManualTable, QgsTableCell
)
from qgis.PyQt.QtGui import QFont, QColor
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QMessageBox
from qgis.PyQt.QtXml import QDomDocument
from qgis.utils import iface
import os

from .qt_compat import QtCompat

# making a top level widgets
TOOL_WINDOW_FLAGS = QtCompat.tool_window_flags()
STAY_ON_TOP_FLAG = QtCompat.stay_on_top()


def rule_based_symbology(inputlayer, rules, outline_status, symbol_xml_path=None, symbol_name=None, opacity=1.0):
    """
    Apply rule-based symbology to a layer, with optional custom symbol and opacity.

    :param inputlayer: QgsVectorLayer
    :param rules: list of tuples (label, expression, color_name, scale)
    :param outline_status: bool
    :param symbol_xml_path: str or None
    :param symbol_name: str or None
    :param opacity: float (0.0 to 1.0)
    """
    try:
        custom_symbol = None
        if symbol_xml_path and symbol_name:
            style = QgsStyle.defaultStyle()
            success = style.importXml(symbol_xml_path)
            if not success:
                print(f"Failed to import symbols from {symbol_xml_path}")
            else:
                custom_symbol = style.symbol(symbol_name)
                if not custom_symbol:
                    print(
                        f"Symbol '{symbol_name}' not found in {symbol_xml_path}")
        if rules:
            symbol = custom_symbol.clone() if custom_symbol else QgsSymbol.defaultSymbol(
                inputlayer.geometryType())
            symbol.setOpacity(opacity)
            renderer = QgsRuleBasedRenderer(symbol)
            root_rule = renderer.rootRule()
            for label, expression, color_name, scale in rules:
                rule_symbol = custom_symbol.clone(
                ) if custom_symbol else QgsSymbol.defaultSymbol(inputlayer.geometryType())
                rule_symbol.setOpacity(opacity)
                if outline_status:
                    symbol_layer = rule_symbol.symbolLayer(0)
                    symbol_layer.setColor(QColor(color_name))
                    if inputlayer.geometryType() == QgsWkbTypes.GeometryType.LineGeometry:
                        symbol_layer.setWidth(0.46)
                    elif inputlayer.geometryType() == QgsWkbTypes.GeometryType.PolygonGeometry:
                        symbol_layer.setStrokeColor(QColor(color_name))
                        symbol_layer.setStrokeWidth(0.46)
                        symbol_layer.setBrushStyle(QtCompat.NoBrush)
                else:
                    rule_symbol.setColor(QColor(color_name))
                rule = QgsRuleBasedRenderer.Rule(rule_symbol)
                rule.setLabel(label)
                rule.setFilterExpression(expression)
                if scale:
                    rule.setScaleMinDenom(scale[0])
                    rule.setScaleMaxDenom(scale[1])
                root_rule.appendChild(rule)
            # Remove the default rule if present
            if root_rule.children():
                root_rule.removeChildAt(0)
            inputlayer.setRenderer(renderer)
            inputlayer.setOpacity(opacity)
            inputlayer.triggerRepaint()
    except Exception as e:
        print(f'Error in rule_based_symbology: {e}')


def enable_label(layer_id, font, font_size, field_name, font_weight, is_expression, placement_index, font_color):

    # layer = QgsProject.instance().mapLayersByName(layer)[0]
    # Array of label placements
    placements = [
        QgsPalLayerSettings.AroundPoint,
        QgsPalLayerSettings.Horizontal,
        QgsPalLayerSettings.Free,
        QgsPalLayerSettings.OverPoint,
        QgsPalLayerSettings.OnLine,
        QgsPalLayerSettings.Curved,

    ]
    # Get the selected placement from the array
    selected_placement = placements[placement_index]
    layer = QgsProject.instance().mapLayer(layer_id)
    label_settings = QgsPalLayerSettings()
    # Set label placement
    label_settings.placement = selected_placement
    text_format = QgsTextFormat()
    label_settings.isExpression = bool(is_expression)
    text_format.setFont(QFont(str(font), 10, font_weight))
    text_format.setSize(font_size)
    text_format.setColor(QColor(font_color))
    label_settings.fieldName = field_name
    # QFont::Light	25
    # QFont::Normal	50
    # QFont::DemiBold 63
    # QFont::Bold75
    # QFont::Black	87
    buffer_settings = QgsTextBufferSettings()
    # buffer_settings.setEnabled(True)
    buffer_settings.setSize(0)
    # buffer_settings.setColor(QColor("white"))

    text_format.setBuffer(buffer_settings)
    label_settings.setFormat(text_format)

    # Configure placement settings and allow degraded placement
    placement_settings = QgsLabelPlacementSettings()
    placement_settings.setAllowDegradedPlacement(True)
    placement_settings.setOverlapHandling(
        Qgis.LabelOverlapHandling.AllowOverlapIfRequired)
    label_settings.setPlacementSettings(placement_settings)
    # overlaphandling
    # Qgis.LabelOverlapHandling.AllowOverlapIfRequired
    # Qgis.LabelOverlapHandling.PreventOverlap
    # Qgis.LabelOverlapHandling.AllowOverlapAtNoCost

    label_settings.enabled = True
    label_settings = QgsVectorLayerSimpleLabeling(label_settings)
    layer.setLabelsEnabled(True)
    layer.setLabeling(label_settings)
    layer.triggerRepaint()


def undo(layer):
    undo_action = [a for a in iface.digitizeToolBar(
    ).actions() if a.objectName() == "mActionUndo"][0]
    if undo_action:
        undo_action.trigger()
        layer.triggerRepaint()


def redo(layer):
    redo_action = [a for a in iface.digitizeToolBar(
    ).actions() if a.objectName() == "mActionRedo"][0]
    if redo_action:
        redo_action.trigger()
        layer.triggerRepaint()


def apply_custom_symbol(layer: QgsVectorLayer, symbol_xml_path: str, symbol_name: str) -> bool:
    """
    Applies a symbol from an XML style file to a QGIS vector layer.

    Parameters:
    - layer: QgsVectorLayer to which the symbol should be applied.
    - symbol_xml_path: File path to the QGIS XML style file.
    - symbol_name: The name of the symbol to apply.

    Returns:
    - True if the symbol was applied successfully, False otherwise.
    """
    if not layer or not layer.isValid():
        print("Invalid layer")
        return False

    style = QgsStyle.defaultStyle()
    success = style.importXml(symbol_xml_path)

    if not success:
        print(f"Failed to import style from {symbol_xml_path}")
        return False

    symbol = style.symbol(symbol_name)
    if symbol is None:
        print(f"Symbol '{symbol_name}' not found in style file")
        return False

    renderer = layer.renderer().clone()
    renderer.setSymbol(symbol.clone())
    layer.setRenderer(renderer)
    layer.triggerRepaint()
    print(
        f"Symbol '{symbol_name}' applied successfully to layer '{layer.name()}'")
    return True


def load_template_and_setup_atlas_with_text(
    template_path, template_name,
    coverage_layer, page_name_field,
    text1="Label 1", text2="Label 2", text3="Label 3",
    f1=None, f2=None, f3=None
):
    """
    Loads a layout template (.qpt), sets up atlas, and adds two text items (with provided text).
    If a layout with the same name already exists, it will be removed and replaced.

    :param template_path: str - Full path to the .qpt template file
    :param template_name: str - Name to assign to the loaded layout
    :param coverage_layer: QgsVectorLayer - Coverage layer for atlas
    :param page_name_field: str - Field name to use for atlas page name
    :param text1: str - Text to display in the first label
    :param text2: str - Text to display in the second label
    """
    try:
        project = QgsProject.instance()
        layout_manager = project.layoutManager()

        # If layout with same name exists, remove it
        existing_layout = layout_manager.layoutByName(template_name)
        if existing_layout:
            layout_manager.removeLayout(existing_layout)
            print(f"Existing layout '{template_name}' removed.")

        # Load template XML
        with open(template_path, 'r', encoding='utf-8') as file:
            template_content = file.read()

        doc = QDomDocument()
        if not doc.setContent(template_content):
            print(f"Error parsing template file at {template_path}")
            return

        # Load layout from template
        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        layout.loadFromTemplate(doc, QgsReadWriteContext())
        layout.setName(template_name)
        layout_manager.addLayout(layout)

        # Set up Atlas
        atlas = layout.atlas()
        atlas.setEnabled(True)
        atlas.setCoverageLayer(coverage_layer)
        atlas.setFilterFeatures(False)
        atlas.setSortFeatures(True)
        atlas.setSortExpression(f'"{page_name_field}"')
        atlas.setPageNameExpression(f'"{page_name_field}"')

        # Add first text item
        text_item1 = QgsLayoutItemLabel(layout)
        text_item1.setText(text1)
        text_item1.setFont(QFont("Verdana", 12))
        text_item1.adjustSizeToText()
        text_item1.attemptMove(QgsLayoutPoint(
            75, 33, QgsUnitTypes.LayoutUnit.LayoutMillimeters))
        layout.addLayoutItem(text_item1)

        # Add second text item
        text_item2 = QgsLayoutItemLabel(layout)
        text_item2.setText(text2)
        text_item2.setFont(QFont("Verdana", 10))
        text_item2.adjustSizeToText()
        # Set fixed size for the text item (in millimeters)
        text_item2.setFixedSize(QgsLayoutSize(
            100, 13, QgsUnitTypes.LayoutUnit.LayoutMillimeters))
        text_item2.attemptMove(QgsLayoutPoint(
            75, 39.60, QgsUnitTypes.LayoutUnit.LayoutMillimeters))
        layout.addLayoutItem(text_item2)

        # Add third text item
        text_item3 = QgsLayoutItemLabel(layout)
        text_item3.setText(text3)
        text_item3.setFont(QFont("Verdana", 10))
        text_item3.adjustSizeToText()
        # Set fixed size for the text item (in millimeters)
        text_item3.setFixedSize(QgsLayoutSize(
            100, 13, QgsUnitTypes.LayoutUnit.LayoutMillimeters))
        text_item3.attemptMove(QgsLayoutPoint(
            75, 45.60, QgsUnitTypes.LayoutUnit.LayoutMillimeters))
        layout.addLayoutItem(text_item3)

        layout.refresh()
        print(
            f"Layout '{template_name}' loaded from template, atlas set up, and text labels added.")

    except Exception as e:
        print(f"Error in load_template_and_setup_atlas_with_text: {e}")


def apply_polygon_labels(layer, field_name):
    """
    Apply bold, underlined labels inside a polygon layer using the specified field.
    """
    if not layer or layer.geometryType() != 2:  # 2 = Polygon
        print("Invalid layer or not a polygon layer.")
        return

    label_settings = QgsPalLayerSettings()
    label_settings.fieldName = field_name
    label_settings.enabled = True
    label_settings.displayAll = True
    label_settings.priority = 10

    # Try setting placement if supported (QGIS 3.28+)
    try:
        label_settings.placement = QgsPalLayerSettings.OverPolygon
    except AttributeError:
        pass  # Safe fallback for older QGIS versions

    # Obstacle settings
    try:
        obstacle_settings = label_settings.obstacleSettings()
        obstacle_settings.setIsObstacle(False)
        label_settings.setObstacleSettings(obstacle_settings)
    except AttributeError:
        pass  # For older versions where this is not available

    # Font: Bold + Underline
    font = QFont("Verdana", 10)
    font.setBold(True)
    font.setUnderline(True)

    text_format = QgsTextFormat()
    text_format.setFont(font)
    text_format.setSize(10)

    # Optional buffer (halo)
    # buffer_settings = QgsTextBufferSettings()
    # buffer_settings.setEnabled(False)
    # buffer_settings.setSize(0.5)
    # buffer_settings.setColor(QColor("white"))
    # text_format.setBuffer(buffer_settings)

    label_settings.setFormat(text_format)

    labeling = QgsVectorLayerSimpleLabeling(label_settings)
    layer.setLabeling(labeling)
    layer.setLabelsEnabled(True)
    layer.triggerRepaint()


def delete_short_lines(layer, length_threshold=0.2, lfield="Length"):
    """
    Delete line features with Length field value less than threshold

    Args:
        layer: QgsVectorLayer object
        length_threshold: float, minimum length value to keep
    """

    # Check if layer is valid
    if not layer.isValid():
        print("Layer is not valid")
        return False

    # Check if layer is editable
    if not layer.isEditable():
        if not layer.startEditing():
            print("Could not start editing session")
            return False

    # Check if Length field exists
    field_names = [field.name() for field in layer.fields()]
    if lfield not in field_names:
        print("Field 'Length' not found in layer")
        return False

    # Get features to delete
    request = QgsFeatureRequest()
    request.setFilterExpression(f'"Length" < {length_threshold}')

    ids_to_delete = []
    for feature in layer.getFeatures(request):
        ids_to_delete.append(feature.id())

    if not ids_to_delete:
        # Fixed: added 'f' prefix
        print(f"No features found with Length < {length_threshold}")
        return True

    # Delete features
    success = layer.deleteFeatures(ids_to_delete)

    if success:
        # Commit changes
        layer.commitChanges()
        print(f"Successfully deleted {len(ids_to_delete)} features")
        return True
    else:
        print("Failed to delete features")
        layer.rollBack()
        return False
# Execute the function
# delete_short_lines(layer, 0.2,"Length")


def districtlist():
    districts_eng = [
        'Alluri Sitharama Raju', 'Anakapalli', 'Anantapuram', 'Annamayya', 'Bapatla', 'Chittoor', 'East Godavari',
        'Eluru', 'Guntur', 'Kakinada', 'Dr. B. R. Ambedkar Konaseema', 'Krishna', 'Kurnool', 'Nandyal', 'NTR',
        'Palnadu', 'Parvathipuram Manyam', 'Prakasam', 'Sri Potti Sriramulu Nellore', 'Sri Sathya Sai',
        'Srikakulam', 'Tirupati', 'Visakhapatnam', 'Vizianagaram', 'West Godavari', 'YSR Kadapa'
    ]
    return districts_eng


def districttuple():
    districts_dup = {'Alluri Sitharama Raju': 'అల్లూరి సీతారామ రాజు', 'Anakapalli': 'అనకాపల్లి',  'Anantapuram': 'అనంతపురం',  'Annamayya': 'అన్నమయ్య',  'Bapatla': 'బాపట్ల',  'Chittoor': 'చిత్తూరు',  'East Godavari': 'తూర్పు గోదావరి',  'Eluru': 'ఏలూరు',  'Guntur': 'గుంటూరు ',  'Kakinada': 'కాకినాడ',  'Dr. B. R. Ambedkar Konaseema': 'కోనసీమ',  'Krishna': 'కృష్ణా', 'Kurnool': 'కర్నూలు',
                     'Nandyal': 'నంద్యాల',  'NTR': 'యన్.టి.ఆర్',  'Palnadu': 'పల్నాడు',  'Parvathipuram Manyam': 'పార్వతీపురం మన్యం',  'Prakasam': 'ప్రకాశం ',  'Sri Potti Sriramulu Nellore': 'నెల్లూరు',  'Sri Sathya Sai': 'శ్రీ సత్య సాయి',  'Srikakulam': 'శ్రీకాకుళం ',  'Tirupati': 'తిరుపతి',  'Visakhapatnam': 'విశాఖపట్నం ',  'Vizianagaram': 'విజయనగరం ',  'West Godavari': 'పశ్చిమ గోదావరి',  'YSR Kadapa': 'వై.యస్.ర్ కడప'}
    return districts_dup


def apply_categorized_symbology(layer, categories_info):
    """Apply categorized symbology to differentiate multiple categories for point, line, or polygon layers.

    Args:
        layer: The layer to which the symbology will be applied (can be point, line, or polygon).
        categories_info: A list of dictionaries containing category information.
                         Each dictionary should have 'name', 'color', 'size', 'opacity', and optionally 'line_width' for lines.
    """
    # Check if categories_info is empty
    if not categories_info:
        raise ValueError("categories_info must not be empty.")

    # Check if the 'Type' attribute exists in the layer
    if layer.fields().indexOf("Type") == -1:
        raise ValueError("The attribute 'Type' does not exist in the layer.")

    # Initialize the categories list
    categories = []

    # Loop through the provided category information
    for category_info in categories_info:
        # Ensure required keys are present
        for key in ['name', 'color', 'opacity']:
            if key not in category_info:
                raise ValueError(f"Missing key '{key}' in category_info.")

        # Create a symbol based on the geometry type
        geometry_type = layer.geometryType()
        symbol = QgsSymbol.defaultSymbol(geometry_type)

        # Set common properties
        symbol.setColor(QColor(category_info['color']))
        symbol.setOpacity(category_info['opacity'])

        # Set specific properties based on geometry type
        if geometry_type == QgsWkbTypes.GeometryType.PointGeometry:
            # For point layers, set size
            if 'size' in category_info:
                symbol.setSize(category_info['size'])
            else:
                raise ValueError("Missing key 'size' for point category.")

        elif geometry_type == QgsWkbTypes.GeometryType.LineGeometry:
            # For line layers, set width
            if 'line_width' in category_info:
                symbol.setWidth(category_info['line_width'])
            else:
                raise ValueError("Missing key 'line_width' for line category.")

        elif geometry_type == QgsWkbTypes.GeometryType.PolygonGeometry:
            # For polygon layers, set fill style and outline
            symbol.setFillColor(QColor(category_info['color']))  # Fill color
            symbol.setStrokeColor(
                QColor(category_info['color']))  # Outline color
            # Default stroke width, can be customized
            symbol.setStrokeWidth(0.5)

        # Create a QgsRendererCategory for the category
        category = QgsRendererCategory(
            category_info['name'], symbol, category_info['name'])
        categories.append(category)

    # Create the Categorized Symbol Renderer
    renderer = QgsCategorizedSymbolRenderer("Type", categories)

    # Set the renderer to the layer
    layer.setRenderer(renderer)
    layer.triggerRepaint()


def save_temp_layer(self, layer):
    """Save or update the Start and End Points layer, maintaining the same name."""
    try:
        # Check if the layer is temporary (memory layer)
        if layer.providerType() == "memory":
            # Prompt the user to save the layer to disk
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Plotted Points", layer.name(),
                "ESRI Shapefile (*.shp);;GeoJSON (*.geojson);;GPKG (*.gpkg)"
            )
            if not file_path:
                return False  # User canceled the dialog

            # Determine the file format from the file extension
            if file_path.endswith(".shp"):
                format_name = "ESRI Shapefile"
            elif file_path.endswith(".geojson"):
                format_name = "GeoJSON"
            elif file_path.endswith(".gpkg"):
                format_name = "GPKG"
            else:
                QMessageBox.critical(
                    self, "Error", "Unsupported file format.")
                return False

            # Set up save options
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = format_name
            options.fileEncoding = "UTF-8"

            # Save the layer
            error = QgsVectorFileWriter.writeAsVectorFormatV3(
                layer, file_path, QgsProject.instance().transformContext(), options
            )

            if error[0] == QgsVectorFileWriter.WriterError.NoError:
                QMessageBox.information(
                    self, "Save Successful", f"Layer saved successfully at {file_path}!"
                )
                # Reload the saved layer and keep the same name
                new_layer = QgsVectorLayer(
                    file_path, layer.name(), "ogr")
                if new_layer.isValid():
                    QgsProject.instance().addMapLayer(new_layer)
                    QgsProject.instance().removeMapLayer(layer.id())
                else:
                    QMessageBox.warning(
                        self, "Warning", "Failed to reload the saved layer into the project."
                    )
            else:
                QMessageBox.critical(
                    self, "Save Error", f"Error saving layer. Error code: {error[0]}"
                )

    except Exception as e:
        QMessageBox.critical(self, "Unexpected Error",
                             f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


def toggle_layervisibility(layer_id, action):
    # Get the layer ID
    layer_id = layer_id
    layer = QgsProject.instance().mapLayer(layer_id)
    layer.commitChanges()
    # Get the layer tree root
    root = QgsProject.instance().layerTreeRoot()

    # Find the layer node based on the layer ID
    layer_node = root.findLayer(layer_id)

    if layer_node:
        # Disable or enable the layer
        layer_node.setItemVisibilityChecked(bool(action))  # Disable the layer
        # layer_node.setItemVisibilityChecked(True)  # Enable the layer
    else:
        print("Layer not found in the layer tree.")


def delete_small_parcels(layer_name: str, area_threshold: float = 0.02):
    """
    Deletes features in a polygon layer whose area is less than the given threshold.

    Parameters:
        layer_name (str): Name of the polygon layer in QGIS.
        area_threshold (float): Area threshold in square meters (default = 0.02).
    """
    from qgis.utils import iface

    # Get message bar instance
    message_bar = iface.messageBar()

    # Get layer by name
    layers = QgsProject.instance().mapLayersByName(layer_name)
    if not layers:
        message_bar.pushMessage(
            "Error", f"Layer '{layer_name}' not found.", level=Qgis.MessageLevel.Critical)
        return

    layer = layers[0]

    # Check if layer is a vector layer and has polygon geometry
    if layer.type() != QgsMapLayer.LayerType.VectorLayer:
        message_bar.pushMessage(
            "Error", f"Layer '{layer_name}' is not a vector layer.", level=Qgis.MessageLevel.Critical)
        return

    if layer.geometryType() != QgsWkbTypes.GeometryType.PolygonGeometry:
        message_bar.pushMessage(
            "Error", f"Layer '{layer_name}' does not contain polygon geometries.", level=Qgis.MessageLevel.Critical)
        return

    # Start editing if not already in edit mode
    if not layer.isEditable():
        if not layer.startEditing():
            message_bar.pushMessage(
                "Error", f"Could not start editing layer '{layer_name}'.", level=Qgis.MessageLevel.Critical)
            return

    try:
        # Get features with area less than threshold
        ids_to_delete = []
        for feature in layer.getFeatures():
            if feature.geometry() and feature.geometry().isGeosValid():
                area = feature.geometry().area()
                if area < area_threshold:
                    ids_to_delete.append(feature.id())

        if ids_to_delete:
            # Delete features
            if layer.deleteFeatures(ids_to_delete):
                if layer.commitChanges():
                    message_bar.pushMessage(
                        "Success", f"Successfully deleted {len(ids_to_delete)} parcels with area < {area_threshold} sq.m", level=Qgis.MessageLevel.Success)
                else:
                    message_bar.pushMessage(
                        "Error", "Failed to commit changes.", level=Qgis.MessageLevel.Critical)
                    layer.rollBack()
            else:
                message_bar.pushMessage(
                    "Error", "Failed to delete features.", level=Qgis.MessageLevel.Critical)
                layer.rollBack()
        else:
            message_bar.pushMessage(
                "Info", "No parcels found with area below the threshold.", level=Qgis.MessageLevel.Info)
            # Only commit if we actually made changes, otherwise just stop editing
            layer.rollBack()

    except Exception as e:
        message_bar.pushMessage(
            "Error", f"Error occurred: {str(e)}", level=Qgis.MessageLevel.Critical)
        layer.rollBack()

    # Ensure we're not left in editing mode
    if layer.isEditable():
        layer.rollBack()


def asksaveProject():
    """
    Version that uses QGIS built-in save functionality.

    Returns:
        bool: True if project was saved successfully, False otherwise.
    """
    project = QgsProject.instance()

    if project.fileName():
        # Project has filename, save directly
        return project.write()
    else:
        # Use QGIS built-in save as functionality
        from qgis.utils import iface
        iface.actionSaveProjectAs().trigger()  # This opens the Save As dialog

        # Check if project now has a filename (user saved it)
        if project.fileName():
            iface.messageBar().pushMessage("Success", "Project saved successfully.",
                                           level=Qgis.MessageLevel.Success, duration=2)
            return True
        else:
            iface.messageBar().pushMessage("Warning", "Project was not saved.",
                                           level=Qgis.MessageLevel.Warning, duration=2)
            return False

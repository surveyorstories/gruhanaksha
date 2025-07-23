"""
Model exported as python.
Name : ppm new model
Group : 
With QGIS : 32815
"""

from .addon_functions import districtlist, districttuple, rule_based_symbology, apply_polygon_labels, delete_small_parcels, toggle_layervisibility, apply_custom_symbol, load_template_and_setup_atlas_with_text, delete_short_lines
from qgis.core import (
    QgsSymbol, QgsRuleBasedRenderer, QgsStyle, QgsWkbTypes,
    QgsProcessing, QgsProcessingAlgorithm, QgsProcessingMultiStepFeedback,
    QgsProcessingParameterVectorLayer, QgsProcessingParameterField, QgsExpressionContextUtils,
    QgsProcessingParameterString, QgsProcessingParameterFeatureSink,
    QgsProcessingException, QgsProject, QgsVectorLayer, QgsProcessingParameterEnum,
    QgsPalLayerSettings, QgsVectorLayerSimpleLabeling
)
from qgis.PyQt.QtGui import QColor
import processing
from PyQt5.QtGui import QFont
import os
import inspect
from qgis.core import QgsPalLayerSettings, QgsVectorLayerSimpleLabeling
# Get the path to the current project folder
from qgis.utils import iface
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QAction
)
project = QgsProject.instance()
project_folder = project.readPath("./")
assets_folder = os.path.dirname(__file__)+"/assets"
save_action = iface.mainWindow().findChild(QAction, 'mActionSaveProject')


class SvamitvaPPMAlgorithm(QgsProcessingAlgorithm):

    def icon(self):

        cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]
        icon = QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/ppm.svg')))
        return icon

    def flags(self):
        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading

    def initAlgorithm(self, config=None):
        if QgsExpressionContextUtils.globalScope().variable('district_eng'):
            options = districtlist()
            dname = QgsExpressionContextUtils.globalScope().variable('district_eng')
            dname = options.index(dname)
        else:
            dname = None
        self.addParameter(QgsProcessingParameterVectorLayer('choose_plot_shapefile',
                          'Choose <b>Plot Area</b> Shapefile ', types=[QgsProcessing.TypeVectorPolygon], defaultValue=None))

        self.addParameter(QgsProcessingParameterField('property_parcel_number', 'Choose <b>Property Parcel Number</b>',
                          type=QgsProcessingParameterField.Any, parentLayerParameterName='choose_plot_shapefile', allowMultiple=False, defaultValue='prop_id'))
        self.addParameter(QgsProcessingParameterField('plot_area_in_square_yards', 'Choose <b> Plot Area in Square Yards </b>',
                          type=QgsProcessingParameterField.Any, parentLayerParameterName='choose_plot_shapefile', allowMultiple=False, defaultValue='AREA_SQYRD'))
        self.addParameter(QgsProcessingParameterField('plot_area_in_square_metres', 'Choose <b> Plot Area in Square Metres </b>',
                          type=QgsProcessingParameterField.Any, parentLayerParameterName='choose_plot_shapefile', allowMultiple=False, defaultValue='SHAPE_Area'))

        self.addParameter(QgsProcessingParameterVectorLayer('choose_plinth_shapefile',
                          'Choose <b>Builtup (Plinth) Area </b> Shapefile', types=[QgsProcessing.TypeVectorPolygon], defaultValue=None))
        self.addParameter(QgsProcessingParameterEnum('district_name_eng', 'Choose Your <b>District</b>',
                          options=districtlist(), allowMultiple=False, usesStaticStrings=False, defaultValue=dname))
        self.addParameter(QgsProcessingParameterString(
            'name_of_the_mandal', 'Name Of The <b>Mandal</b>', multiLine=False, defaultValue=''))

        self.addParameter(QgsProcessingParameterString(
            'name_of_the_grama_panchayat', 'Name Of The <b>Grama Panchayat</b>', multiLine=False, defaultValue=''))

        self.addParameter(QgsProcessingParameterString(
            'gram_panchayat_code', 'Grama <b>Panchayat Code </b>', multiLine=False, defaultValue=''))
        self.addParameter(QgsProcessingParameterString(
            'village_code_lgd_code', 'Village Code <b>(LGD CODE)</b>  ', multiLine=False, defaultValue=''))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(17, model_feedback)
        results = {}
        outputs = {}

        # Retrieve the first vector layer from the parameters
        village_layer = self.parameterAsVectorLayer(
            parameters, 'choose_plot_shapefile', context)
        if not village_layer:
            raise QgsProcessingException(
                "Habitation Final Shape File is required")

        # Retrieve the second vector layer from the parameters
        another_layer = self.parameterAsVectorLayer(
            parameters, 'choose_plinth_shapefile', context)
        if not another_layer:
            raise QgsProcessingException(
                "Village Final Shape File is required")

        # Get the CRS of both layers and the project
        layer_crs_village = village_layer.crs()
        layer_crs_another = another_layer.crs()
        project_crs = context.project().crs()

        # Check if both layers have the same CRS as the project
        if layer_crs_village != project_crs:
            raise QgsProcessingException(
                "CRS Mismatch: Plot Final Shape File CRS ({}) does not match Project CRS ({})."
                .format(layer_crs_village.authid(), project_crs.authid())
            )

        if layer_crs_another != project_crs:
            raise QgsProcessingException(
                "CRS Mismatch: Builtup Final Shape File Layer CRS ({}) does not match Project CRS ({})."
                .format(layer_crs_another.authid(), project_crs.authid())
            )

        # Check if both layers have the same CRS
        if layer_crs_village != layer_crs_another:
            raise QgsProcessingException(
                "CRS Mismatch: Plot Final Shape File CRS ({}) does not match Builtup Final Shape File CRS ({})."
                .format(layer_crs_village.authid(), layer_crs_another.authid())
            )

        feedback.pushInfo(
            "CRS Validation Passed: Both layers have the same CRS ({}) and match the Project CRS ({})."
            .format(layer_crs_village.authid(), project_crs.authid())
        )

        # # Trigger the save action
        save_action.trigger()
        project = QgsProject.instance()
        project_folder = project.readPath("./")
        map_scales = [100, 150, 250, 500, 1000, 1500, 2000,
                      2500, 3000, 3500, 4000, 4500, 5000, 5500, 6000, 6500, 7000]
        project.setMapScales(map_scales)
        project.setUseProjectScales(True)
        root = project.layerTreeRoot()
        # Get the layer from the input parameter
        param_value = parameters['choose_plot_shapefile']
        lpm_param_value = parameters['choose_plinth_shapefile']
        layer_names = ['Builtup_ExplodeLines', 'Plot_Shapefile', 'Builtup_Shapefile', 'Plot_ExplodeLines', 'Plot_Vertices',
                       'Exploded_Lines', 'Boundary', ]

        # --- Begin input validation checks ---

        def _get_layer_name(layer_ref):
            # Try to get layer name from id or path
            lyr = project.mapLayer(layer_ref)
            if lyr:
                return lyr.name()
            elif isinstance(layer_ref, str) and os.path.exists(layer_ref):
                try:
                    lyr = QgsVectorLayer(layer_ref, '', 'ogr')
                    return lyr.name()
                except Exception:
                    return None
            return None

        def _reserved_layer_exists_in_project_dir(name):
            # Check for .shp and .gpkg in project folder
            for ext in ('.shp', '.gpkg'):
                candidate_path = os.path.join(project_folder, f"{name}{ext}")
                if os.path.exists(candidate_path):
                    layers_to_remove = project.mapLayersByName(name)
                    for lyr in layers_to_remove:
                        # Only if the data source matches the candidate path
                        if os.path.abspath(lyr.dataProvider().dataSourceUri().split('|')[0]) == os.path.abspath(candidate_path):
                            return True
            return False

        def _remove_reserved_layer_if_created(name):
            for ext in ('.shp', '.gpkg'):
                candidate_path = os.path.join(project_folder, f"{name}{ext}")
                if os.path.exists(candidate_path):
                    layers_to_remove = project.mapLayersByName(name)
                    for lyr in layers_to_remove:
                        if os.path.abspath(lyr.dataProvider().dataSourceUri().split('|')[0]) == os.path.abspath(candidate_path):
                            root.removeLayer(lyr)

        plot_layer_name = _get_layer_name(param_value)
        plinth_layer_name = _get_layer_name(lpm_param_value)
        reserved_names = set(layer_names)

        # If reserved name and file exists in project dir, block usage (renaming won't help)
        if plot_layer_name in reserved_names and _reserved_layer_exists_in_project_dir(plot_layer_name):
            _remove_reserved_layer_if_created(plot_layer_name)
            raise QgsProcessingException(
                f"Input Plot Area layer name '{plot_layer_name}' is reserved and a file with this name exists in the project directory. Please remove from project directory and rename the file before proceeding."
            )
        if plinth_layer_name in reserved_names and _reserved_layer_exists_in_project_dir(plinth_layer_name):
            _remove_reserved_layer_if_created(plinth_layer_name)
            raise QgsProcessingException(
                f"Input Builtup (Plinth) Area layer name '{plinth_layer_name}' is reserved and a file with this name exists in the project directory. Please remove from project directory and rename the file before proceeding."
            )

        # 2. Prevent same layer for both inputs (by id or path)
        if param_value == lpm_param_value:
            raise QgsProcessingException(
                "You cannot use the same layer for both Plot Area and Builtup (Plinth) Area inputs."
            )
        if (
            isinstance(param_value, str) and isinstance(lpm_param_value, str)
            and os.path.exists(param_value) and os.path.exists(lpm_param_value)
            and os.path.abspath(param_value) == os.path.abspath(lpm_param_value)
        ):
            raise QgsProcessingException(
                "You cannot use the same file for both Plot Area and Builtup (Plinth) Area inputs."
            )
        # --- End input validation checks ---

        layers = project.mapLayers().values()

        # Loop through the layers and remove any that are not the layer you want to keep
        for name in layer_names:
            layers_to_remove = project.mapLayersByName(name)
            for layer in layers_to_remove:
                root.removeLayer(layer)

        # create ppm layer variables inside the project
        layer = project.mapLayer(param_value)
        if layer:
            layer_name = layer.name()
        else:

            layer = QgsVectorLayer(
                param_value, 'Plot_Shapefile', 'ogr')
            project.addMapLayer(layer, True)
            layer_name = layer.name()

            param_value = layer.id()

        layer = project.mapLayer(lpm_param_value)
        if layer:
            layer_name = layer.name()
        else:

            layer = QgsVectorLayer(
                lpm_param_value, 'Plilnth_Shapefile', 'ogr')
            project.addMapLayer(layer, True)
            layer_name = layer.name()

            lpm_param_value = layer.id()

        # District Name eng
        # Set district project variable variable
        district_list = districttuple()

        # Convert dictionary items to a list
        items_list = list(district_list.items())
        index = parameters['district_name_eng']
        if index < len(items_list):
            key, value = items_list[index]

            # District_Name enlish
            QgsExpressionContextUtils.setGlobalVariable(
                'district_eng', key)

            # District_Name telugu
            QgsExpressionContextUtils.setGlobalVariable(
                'District_Name', value)

        else:
            print("Invalid index")

         # Set panchyat code variable
        alg_params = {
            'NAME': 'Panchyat_Code',
            'VALUE': parameters['gram_panchayat_code']
        }
        outputs['SetPanchyatCodeVariable'] = processing.run(
            'native:setprojectvariable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        if feedback.isCanceled():
            return {}

        # Set panchayat name variable
        alg_params = {
            'NAME': 'Panchyat_eng',
            'VALUE': parameters['name_of_the_grama_panchayat'].title()
        }
        outputs['SetPanchayatNameVariable'] = processing.run(
            'native:setprojectvariable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        if feedback.isCanceled():
            return {}

        # Set mandal name variable
        alg_params = {
            'NAME': 'Mandal_Name_eng',
            'VALUE': parameters['name_of_the_mandal'].title()
        }
        outputs['SetMandalNameVariable'] = processing.run(
            'native:setprojectvariable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # Set LGD code variable
        alg_params = {
            'NAME': 'P_LGD_Code',
            'VALUE': parameters['village_code_lgd_code']
        }
        outputs['SetLgdCodeVariable'] = processing.run(
            'native:setprojectvariable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        if feedback.isCanceled():
            return {}

        # Fix geometries of plot area
        alg_params = {
            'INPUT': parameters['choose_plot_shapefile'],
            'METHOD': 1,  # Structure
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['FixGeometries_plot'] = processing.run(
            'native:fixgeometries', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # Fix geometries of plinth area
        alg_params = {
            'INPUT': parameters['choose_plinth_shapefile'],
            'METHOD': 1,  # Structure
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['FixGeometries_plinth'] = processing.run(
            'native:fixgeometries', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

     # Create spatial index plot
        alg_params = {
            'INPUT': outputs['FixGeometries_plot']['OUTPUT']
        }
        outputs['CreateSpatialIndexPlot'] = processing.run(
            'native:createspatialindex', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}
     # Create spatial index plinth area
        alg_params = {
            'INPUT': outputs['FixGeometries_plinth']['OUTPUT']
        }
        outputs['CreateSpatialIndexPlinthArea'] = processing.run(
            'native:createspatialindex', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        if feedback.isCanceled():
            return {}

        # Ref_Col Calcluation

        alg_params = {
            'INPUT': outputs['CreateSpatialIndexPlot']['OUTPUT'],
            'FIELD_LENGTH': 10,
            'FIELD_NAME': 'Ref_Col',
            'FIELD_PRECISION': 0,
            'FIELD_TYPE': 1,  # Integer (32 bit)
            'FORMULA': '\"{}\"'.format(parameters['property_parcel_number']),
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Ref_colCalcluation_plot'] = processing.run(
            'native:fieldcalculator', alg_params, context=context,  is_child_algorithm=True)

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # Save Plot_shapefile vector features to file
        alg_params = {
            'DATASOURCE_OPTIONS': '',
            'INPUT': outputs['Ref_colCalcluation_plot']['OUTPUT'],
            'LAYER_NAME': 'Plot_Shapefile',
            'LAYER_OPTIONS': '',
            'OUTPUT': project_folder + '/Plot_Shapefile.shp'
        }
        outputs['Save_plot_shapefile'] = processing.run(
            'native:savefeatures', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        # Boundary plot area
        alg_params = {
            'INPUT': outputs['Ref_colCalcluation_plot']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['BoundaryPlotArea'] = processing.run(
            'native:boundary', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # Save Plot_Boundary vector features to file
        alg_params = {
            'DATASOURCE_OPTIONS': '',
            'INPUT': outputs['BoundaryPlotArea']['OUTPUT'],
            'LAYER_NAME': 'Plot_Boundary',
            'LAYER_OPTIONS': '',
            'OUTPUT': project_folder + '/Plot_Boundary.shp'
        }
        outputs['Save_plot_boundary_VectorFeaturesToFile'] = processing.run(
            'native:savefeatures', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        # Explode lines plot area
        alg_params = {
            'INPUT': outputs['BoundaryPlotArea']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['ExplodeLinesPlotArea'] = processing.run(
            'native:explodelines', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}

        # Intersection
        alg_params = {
            'GRID_SIZE': None,
            'INPUT': parameters['choose_plinth_shapefile'],
            'INPUT_FIELDS': [''],
            'OVERLAY': outputs['Ref_colCalcluation_plot']['OUTPUT'],
            'OVERLAY_FIELDS': [''],
            'OVERLAY_FIELDS_PREFIX': '',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['IntersectionofPlinthPlot'] = processing.run(
            'native:intersection', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(6)
        if feedback.isCanceled():
            return {}

        # Create spatial index
        alg_params = {
            'INPUT': outputs['IntersectionofPlinthPlot']['OUTPUT']
        }
        outputs['CreateSpatialIndex'] = processing.run(
            'native:createspatialindex', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # area calculation
        alg_params = {
            'INPUT': outputs['IntersectionofPlinthPlot']['OUTPUT'],
            'FIELD_LENGTH': 10,
            'FIELD_NAME': 'Area',
            'FIELD_PRECISION': 2,
            'FIELD_TYPE': 0,  # Decimal (double)
            'FORMULA': 'area( $geometry )',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Ref_colCalcluation_plinth'] = processing.run(
            'native:fieldcalculator', alg_params, context=context,  is_child_algorithm=True)

        # Save Builtup_Shapefile vector features to file
        alg_params = {
            'DATASOURCE_OPTIONS': '',
            'INPUT': outputs['Ref_colCalcluation_plinth']['OUTPUT'],
            'LAYER_NAME': 'Builtup_Shapefile',
            'LAYER_OPTIONS': '',
            'OUTPUT': project_folder + '/Builtup_Shapefile.shp'
        }
        outputs['Save_builtup_shapefile'] = processing.run(
            'native:savefeatures', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(8)
        if feedback.isCanceled():
            return {}

        # Load plot layer into project
        newplot_layer = QgsVectorLayer(
            outputs['Save_plot_shapefile']['OUTPUT'], 'Plot_Shapefile', 'ogr')
        project.addMapLayer(newplot_layer, True)
        toggle_layervisibility(param_value, False)

        # Load builtup layer into project
        newbuiltup_layer = QgsVectorLayer(
            outputs['Save_builtup_shapefile']['OUTPUT'], 'Builtup_Shapefile', 'ogr')
        project.addMapLayer(newbuiltup_layer, True)

        delete_small_parcels('Builtup_Shapefile', 1)
        toggle_layervisibility(lpm_param_value, False)

        # Create spatial index
        alg_params = {
            'INPUT': outputs['Save_builtup_shapefile']['OUTPUT']
        }
        outputs['CreateSpatialIndex'] = processing.run(
            'native:createspatialindex', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # Boundary plinth area
        alg_params = {
            # outputs['MergeIntersectionAndDiffrence']['OUTPUT'],
            'INPUT': outputs['Save_builtup_shapefile']['OUTPUT'],
            'OUTPUT':  QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['BoundaryPlinthArea'] = processing.run(
            'native:boundary', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # Save Builtup_Boundary vector features to file
        alg_params = {
            'DATASOURCE_OPTIONS': '',
            'INPUT': outputs['BoundaryPlinthArea']['OUTPUT'],
            'LAYER_NAME': 'Builtup_Boundary',
            'LAYER_OPTIONS': '',
            'OUTPUT': project_folder + '/Builtup_Boundary.shp'
        }
        outputs['SaveVectorFeaturesToFile'] = processing.run(
            'native:savefeatures', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(9)
        if feedback.isCanceled():
            return {}

        # Explode lines plinth area
        alg_params = {
            'INPUT': outputs['BoundaryPlinthArea']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['ExplodeLinesPlinthArea'] = processing.run(
            'native:explodelines', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(10)
        if feedback.isCanceled():
            return {}

        # Refactor plot Exploded Lines
        alg_params = {
            'FIELDS_MAPPING': [{'expression': '"Ref_Col"', 'length': 10, 'name': 'Ref_Col', 'precision': 0, 'sub_type': 0, 'type': 2, 'type_name': 'integer'}, {'expression': 'length3D( $geometry)', 'length': 10, 'name': 'Length', 'precision': 1, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'}],
            'INPUT': outputs['ExplodeLinesPlotArea']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['RefactorplotExplodedLines'] = processing.run(
            'native:refactorfields', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # Save Plot_ExplodeLines vector features to file
        alg_params = {
            'DATASOURCE_OPTIONS': '',
            'INPUT': outputs['RefactorplotExplodedLines']['OUTPUT'],
            'LAYER_NAME': 'Plot_ExplodeLines',
            'LAYER_OPTIONS': '',
            'OUTPUT': project_folder + '/Plot_ExplodeLines.shp'
        }
        outputs['Save_Plot_ExplodeLines'] = processing.run(
            'native:savefeatures', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(11)
        if feedback.isCanceled():
            return {}

        # Refactor builtup Exploded Lines
        alg_params = {
            'FIELDS_MAPPING': [{'expression': '"Ref_Col"', 'length': 10, 'name': 'Ref_Col', 'precision': 0, 'sub_type': 0, 'type': 2, 'type_name': 'integer'}, {'expression': 'length3D( $geometry)', 'length': 10, 'name': 'Length', 'precision': 1, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'}],
            'INPUT': outputs['ExplodeLinesPlinthArea']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,

        }
        outputs['RefactorplinthExplodedLines'] = processing.run(
            'native:refactorfields', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # Save Builtup_ExplodeLines vector features to file
        alg_params = {
            'DATASOURCE_OPTIONS': '',
            'INPUT': outputs['RefactorplinthExplodedLines']['OUTPUT'],
            'LAYER_NAME': 'Builtup_ExplodeLines',
            'LAYER_OPTIONS': '',
            'OUTPUT': project_folder + '/Builtup_ExplodeLines.shp'
        }
        outputs['Save_Builtup_ExplodeLines'] = processing.run(
            'native:savefeatures', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        plinth_explode_layer = QgsVectorLayer(
            outputs['Save_Builtup_ExplodeLines']['OUTPUT'], 'Builtup_ExplodeLines', 'ogr')
        project.addMapLayer(plinth_explode_layer, True)

        # Load plot explode lines into project
        alg_params = {
            'INPUT': outputs['Save_Plot_ExplodeLines']['OUTPUT'],
            'NAME': 'Plot_ExplodeLines'
        }
        outputs['load_Plot_ExplodeLines'] = processing.run(
            'native:loadlayer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(12)
        if feedback.isCanceled():
            return {}

        # Extract vertices of plot
        alg_params = {
            'INPUT': outputs['Ref_colCalcluation_plot']['OUTPUT'],
            'OUTPUT': project_folder + '/Plot_Vertices.shp'
        }
        outputs['ExtractVerticesof_plot'] = processing.run(
            'native:extractvertices', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # Load vertices into project

        alg_params = {
            'INPUT': outputs['ExtractVerticesof_plot']['OUTPUT'],
            'NAME': 'Plot_Vertices'
        }
        outputs['load_Plot_Vertices'] = processing.run(
            'native:loadlayer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(13)
        if feedback.isCanceled():
            return {}

        # Set Plot explode style
        alg_params = {
            'INPUT': outputs['load_Plot_ExplodeLines']['OUTPUT'],
            'STYLE': assets_folder + "/Plot_Explode_Style.qml"
        }
        outputs['Plot_Explode_Style'] = processing.run(
            'native:setlayerstyle', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        print("lokesh")
        feedback.setCurrentStep(14)
        if feedback.isCanceled():
            return {}

        # Set Builtup explode style
        alg_params = {
            'INPUT': plinth_explode_layer,
            'STYLE': assets_folder + "/Builtup_Explode_Style.qml"
        }
        outputs['Builtup_Explode_Style'] = processing.run(
            'native:setlayerstyle', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        print("lokesh")
        feedback.setCurrentStep(15)
        if feedback.isCanceled():
            return {}

        # Set Builtup style
        alg_params = {
            'INPUT': newbuiltup_layer,
            'STYLE': assets_folder + "/Builtup_Style.qml"
        }
        outputs['Builtup_Style'] = processing.run(
            'native:setlayerstyle', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        print("lokesh")
        feedback.setCurrentStep(16)
        if feedback.isCanceled():
            return {}

        # Set Plot Vertices style
        alg_params = {
            'INPUT': outputs['load_Plot_Vertices']['OUTPUT'],
            'STYLE': assets_folder + "/Plot_Vertices_Style.qml"
        }
        outputs['Plot_Vertices_Style'] = processing.run(
            'native:setlayerstyle', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        print("lokesh")
        feedback.setCurrentStep(17)
        if feedback.isCanceled():
            return {}

        feedback.pushWarning(
            '\n Hey there! Are you ready to celebrate? 🤩🤩🎉 I\'m just about to finish adding some beautiful templates for you.')
        if feedback.isCanceled():
            return {}

        # Set label for choose_plot_shapefile layer using property_parcel_number field
        # plot_layer = project.mapLayer(param_value)
        if newplot_layer:

            apply_polygon_labels(
                newplot_layer, parameters['property_parcel_number'])
            # Rule-based symbology using helper function
            ppmsymbol = os.path.join(assets_folder, "PPM_SYMBOL.xml")
            if not os.path.exists(ppmsymbol):
                feedback.reportError(f"Symbol file not found: {ppmsymbol}")
                return {}

            field_name = parameters['property_parcel_number']
            rules = [
                (
                    'Plot Area',
                    f'"{field_name}" = @atlas_pagename',
                    '#016fff',  # Color name
                    None    # Scale (optional)
                )
            ]
            rule_based_symbology(
                newplot_layer,
                rules,
                outline_status=True,
                symbol_xml_path=None,
                symbol_name=None,  # Use the correct symbol name from XML
                opacity=1
            )

        coverage_layer = newplot_layer

        load_template_and_setup_atlas_with_text(
            template_path=assets_folder + "/A4_PPM_TEMPLATE.qpt",
            template_name="A4_PPM_TEMPLATE",
            coverage_layer=coverage_layer,
            page_name_field=parameters['property_parcel_number'],
            text1=': [% \"{}\" %]'.format(
                parameters['property_parcel_number']),
            text2=': [% \"{}\" %]'.format(
                parameters['plot_area_in_square_yards']),
            text3=': [% round(\"{}\" ,3) %]'.format(
                parameters['plot_area_in_square_metres'])
        )

        QgsProject.instance().write()
        return {}

    def name(self):
        return 'ppm_new_model'

    def displayName(self):
        return 'PPM Generation'

    def group(self):
        return ''

    def groupId(self):
        return ''

    def shortHelpString(self):
        return """<html><p><a href="https://codes.ap.gov.in/panchayats" target="_blank">Know Your Panchayat Code</a></p>
        <p><a href="https://lgdirectory.gov.in/demo/globalviewvillageforcitizen.do?" target="_blank">Know Your LGD Code</a></p>
        </html>"""

    def createInstance(self):
        return SvamitvaPPMAlgorithm()

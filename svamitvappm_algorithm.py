"""
Model exported as python.
Name : ppm new model
Group : 
With QGIS : 32815
"""

from .addon_functions import districtlist, districttuple, rule_based_symbology, apply_polygon_labels, delete_small_parcels, toggle_layervisibility, apply_custom_symbol, load_template_and_setup_atlas_with_text, delete_short_lines
from qgis.core import (

    QgsProcessing, QgsProcessingAlgorithm, QgsProcessingMultiStepFeedback,
    QgsProcessingParameterVectorLayer, QgsProcessingParameterField, QgsExpressionContextUtils,
    QgsProcessingParameterString,
    QgsProcessingException, QgsProject, QgsVectorLayer, QgsProcessingParameterEnum,

)

import processing

import os
import gc
import inspect
import time

# Get the path to the current project folder
from qgis.utils import iface
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import (
    QAction
)
assets_folder = os.path.dirname(__file__)+"/assets"
save_action = iface.mainWindow().findChild(QAction, 'mActionSaveProject')


SHP_EXTS = ('.shp', '.shx', '.dbf', '.prj', '.cpg', '.qpj', '.shp.xml')


def _release_shp_layers(project, base_path):
    """Remove QGIS layers and print layouts that reference *base_path* from the
    project, then run GC + processEvents so Qt C++ objects are destroyed.
    Does NOT touch files on disk."""
    from qgis.PyQt.QtWidgets import QApplication

    norm_base = os.path.normcase(os.path.abspath(base_path))

    to_remove_ids = []
    for lyr in list(project.mapLayers().values()):
        try:
            ds = lyr.dataProvider().dataSourceUri().split('|')[0]
            if os.path.normcase(os.path.abspath(ds)).startswith(norm_base):
                to_remove_ids.append(lyr.id())
        except Exception:
            pass

    lm = project.layoutManager()
    for layout in list(lm.layouts()):
        try:
            atlas = layout.atlas()
            if atlas and atlas.coverageLayer() and atlas.coverageLayer().id() in to_remove_ids:
                lm.removeLayout(layout)
        except Exception:
            pass

    for lid in to_remove_ids:
        project.removeMapLayer(lid)

    QApplication.processEvents()
    gc.collect()
    QApplication.processEvents()


def _atomic_overwrite_shp(src_base, dst_base):
    """Atomically replace dst shapefile components with src ones.

    Uses os.replace() which on Windows calls MoveFileExW(MOVEFILE_REPLACE_EXISTING).
    This succeeds even when the destination is opened by GDAL/OGR because GDAL
    opens files with FILE_SHARE_DELETE, allowing atomic replacement while handles
    remain open. The old file goes into a 'delete-pending' state and is removed
    once the last handle is closed (when the old QGIS layer is unloaded).
    """
    for ext in SHP_EXTS:
        src = src_base + ext
        dst = dst_base + ext
        if os.path.isfile(src):
            try:
                # atomic even over locked files on Windows
                os.replace(src, dst)
            except Exception:
                pass
        elif os.path.isfile(dst):
            try:
                os.remove(dst)
            except Exception:
                pass


class SvamitvaPPMAlgorithm(QgsProcessingAlgorithm):

    def icon(self):

        cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]
        icon = QIcon(os.path.join(os.path.join(
            cmd_folder, 'images/ppm.svg')))
        return icon

    def flags(self):
        return super().flags() | QgsProcessingAlgorithm.Flag.FlagNoThreading

    def initAlgorithm(self, config=None):
        if QgsExpressionContextUtils.globalScope().variable('district_eng'):
            options = districtlist()
            dname = QgsExpressionContextUtils.globalScope().variable('district_eng')
            dname = options.index(dname)
        else:
            dname = None
        self.addParameter(QgsProcessingParameterVectorLayer('choose_plot_shapefile',
                          'Choose <b>Plot Area</b> Shapefile ', types=[QgsProcessing.SourceType.TypeVectorPolygon], defaultValue=None))

        self.addParameter(QgsProcessingParameterField('property_parcel_number', 'Choose <b>Property Parcel Number</b>',
                          type=QgsProcessingParameterField.DataType.Any, parentLayerParameterName='choose_plot_shapefile', allowMultiple=False, defaultValue='prop_id'))
        self.addParameter(QgsProcessingParameterField('plot_area_in_square_yards', 'Choose <b> Plot Area in Square Yards </b>',
                          type=QgsProcessingParameterField.DataType.Any, parentLayerParameterName='choose_plot_shapefile', allowMultiple=False, defaultValue='AREA_SQYRD'))
        self.addParameter(QgsProcessingParameterField('plot_area_in_square_metres', 'Choose <b> Plot Area in Square Metres </b>',
                          type=QgsProcessingParameterField.DataType.Any, parentLayerParameterName='choose_plot_shapefile', allowMultiple=False, defaultValue='SHAPE_Area'))

        self.addParameter(QgsProcessingParameterVectorLayer('choose_plinth_shapefile',
                          'Choose <b>Builtup (Plinth) Area </b> Shapefile', types=[QgsProcessing.SourceType.TypeVectorPolygon], defaultValue=None))
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
        feedback = QgsProcessingMultiStepFeedback(22, model_feedback)
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

        # Release references to input layers early to avoid holding locks
        village_layer = None
        another_layer = None

        # Remove the PPM print layout from a previous run BEFORE any file
        # operations. The layout holds Qt-level C++ references (atlas coverage
        # layer + map item layer lists) that keep the shapefile handles open on
        # Windows even after project.removeMapLayer(). Destroying the full
        # layout here releases those refs so files can be deleted/overwritten.
        from qgis.PyQt.QtWidgets import QApplication
        _ppm_layout = QgsProject.instance().layoutManager().layoutByName('A4_PPM_TEMPLATE')
        if _ppm_layout:
            QgsProject.instance().layoutManager().removeLayout(_ppm_layout)
            _ppm_layout = None
        QApplication.processEvents()
        gc.collect()
        QApplication.processEvents()

        # # Trigger the save action
        save_action.trigger()
        project = QgsProject.instance()
        project_path = project.fileName()

        if project_path:
            # Project is saved — get its directory
            project_folder = os.path.dirname(project_path)
        else:
            # Project not saved — fallback to QGIS default working directory
            project_folder = QgsProject.instance().homePath() or os.path.expanduser("~")
        map_scales = [100, 150, 250, 500, 1000, 1500, 2000,
                      2500, 3000, 3500, 4000, 4500, 5000, 5500, 6000, 6500, 7000]
        project.setMapScales(map_scales)
        project.setUseProjectScales(True)
        root = project.layerTreeRoot()
        # Get the layer from the input parameter
        param_value = parameters['choose_plot_shapefile']
        lpm_param_value = parameters['choose_plinth_shapefile']

        # create ppm layer variables inside the project (Handle QgsVectorLayer objects)
        if isinstance(param_value, QgsVectorLayer):
            layer = param_value
            param_value = layer.id()
            layer_name = layer.name()
        else:
            layer = project.mapLayer(param_value)
            if layer:
                layer_name = layer.name()
            else:
                layer = QgsVectorLayer(param_value, 'Plot_Shapefile', 'ogr')
                project.addMapLayer(layer, True)
                layer_name = layer.name()
                param_value = layer.id()

        if isinstance(lpm_param_value, QgsVectorLayer):
            layer = lpm_param_value
            lpm_param_value = layer.id()
            layer_name = layer.name()
        else:
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

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # Set mandal name variable
        alg_params = {
            'NAME': 'Mandal_Name_eng',
            'VALUE': parameters['name_of_the_mandal'].title()
        }
        outputs['SetMandalNameVariable'] = processing.run(
            'native:setprojectvariable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # Set LGD code variable
        alg_params = {
            'NAME': 'P_LGD_Code',
            'VALUE': parameters['village_code_lgd_code']
        }
        outputs['SetLgdCodeVariable'] = processing.run(
            'native:setprojectvariable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        # Set ppm_no variable
        alg_params = {
            'NAME': 'ppm_no',
            'VALUE': '"{}"'.format(parameters['property_parcel_number'])
        }
        outputs['SetPpmNoVariable'] = processing.run(
            'native:setprojectvariable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        if feedback.isCanceled():
            return {}

        # Set sqyds variable
        alg_params = {
            'NAME': 'sqyds',
            'VALUE': '"{}"'.format(parameters['plot_area_in_square_yards'])
        }
        outputs['SetSqydsVariable'] = processing.run(
            'native:setprojectvariable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        if feedback.isCanceled():
            return {}

        # Set sqmts variable
        alg_params = {
            'NAME': 'sqmts',
            'VALUE': '"{}"'.format(parameters['plot_area_in_square_metres'])
        }
        outputs['SetSqmtsVariable'] = processing.run(
            'native:setprojectvariable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        if feedback.isCanceled():
            return {}

        # Fix geometries of plot area
        alg_params = {
            'INPUT': param_value,
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
            'INPUT': lpm_param_value,
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
            'native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # Save Plot_shapefile vector features to file
        # Use normpath to fix mixed forward/backslash separators that confuse OGR
        plot_output_path = os.path.normpath(
            os.path.join(project_folder, 'Plot_Shapefile.shp'))
        plot_base_path = plot_output_path[:-4]  # Remove .shp extension

        # Ensure the parent directory exists
        os.makedirs(os.path.dirname(plot_output_path), exist_ok=True)

        # Save Plot_Shapefile — write to temp first, then atomically swap over any
        # existing (possibly locked) files using os.replace() / MoveFileExW.
        plot_tmp_base = plot_base_path + '_tmp'
        plot_tmp_path = plot_tmp_base + '.shp'
        for _ext in SHP_EXTS:  # clean leftover temps from previous failed runs
            _fp = plot_tmp_base + _ext
            if os.path.isfile(_fp):
                try:
                    os.remove(_fp)
                except Exception:
                    pass

        alg_params = {
            'DATASOURCE_OPTIONS': '',
            'INPUT': outputs['Ref_colCalcluation_plot']['OUTPUT'],
            'LAYER_NAME': 'Plot_Shapefile',
            'LAYER_OPTIONS': '',
            'OUTPUT': plot_tmp_path
        }
        outputs['Save_plot_shapefile'] = processing.run(
            'native:savefeatures', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # Release QGIS layer refs, then replace target with temp atomically
        _release_shp_layers(project, plot_base_path)
        _atomic_overwrite_shp(plot_tmp_base, plot_base_path)
        # Point output to the final (target) path for downstream layer loading
        outputs['Save_plot_shapefile'] = {'OUTPUT': plot_output_path}

        feedback.setCurrentStep(9)
        if feedback.isCanceled():
            return {}

        # Boundary plot area
        alg_params = {
            'INPUT': outputs['Ref_colCalcluation_plot']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['BoundaryPlotArea'] = processing.run(
            'native:boundary', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(10)
        if feedback.isCanceled():
            return {}

        # Save Plot_Boundary vector features to file
        plot_boundary_output = os.path.normpath(os.path.join(
            project_folder, 'Plot_Boundary.shp'))
        plot_boundary_base = plot_boundary_output[:-4]

        plot_bdry_tmp_base = plot_boundary_base + '_tmp'
        plot_bdry_tmp_path = plot_bdry_tmp_base + '.shp'
        for _ext in SHP_EXTS:
            _fp = plot_bdry_tmp_base + _ext
            if os.path.isfile(_fp):
                try:
                    os.remove(_fp)
                except Exception:
                    pass

        alg_params = {
            'DATASOURCE_OPTIONS': '',
            'INPUT': outputs['BoundaryPlotArea']['OUTPUT'],
            'LAYER_NAME': 'Plot_Boundary',
            'LAYER_OPTIONS': '',
            'OUTPUT': plot_bdry_tmp_path
        }
        outputs['Save_plot_boundary_VectorFeaturesToFile'] = processing.run(
            'native:savefeatures', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        _release_shp_layers(project, plot_boundary_base)
        _atomic_overwrite_shp(plot_bdry_tmp_base, plot_boundary_base)
        outputs['Save_plot_boundary_VectorFeaturesToFile'] = {
            'OUTPUT': plot_boundary_output}

        feedback.setCurrentStep(11)
        if feedback.isCanceled():
            return {}

        # Explode lines plot area
        alg_params = {
            'INPUT': outputs['BoundaryPlotArea']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['ExplodeLinesPlotArea'] = processing.run(
            'native:explodelines', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(12)
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

        feedback.setCurrentStep(13)
        if feedback.isCanceled():
            return {}

        # Create spatial index
        alg_params = {
            'INPUT': outputs['IntersectionofPlinthPlot']['OUTPUT']
        }
        outputs['CreateSpatialIndex'] = processing.run(
            'native:createspatialindex', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(14)
        if feedback.isCanceled():
            return {}

        # Calculate b_sqmts from Builtup_Shapefile geometry
        alg_params = {
            'INPUT': outputs['IntersectionofPlinthPlot']['OUTPUT'],
            'FIELD_LENGTH': 15,
            'FIELD_NAME': 'b_sqmts',
            'FIELD_PRECISION': 3,
            'FIELD_TYPE': 0,  # Decimal (double)
            'FORMULA': 'area( $geometry )',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Ref_colCalcluation_plinth'] = processing.run(
            'native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(15)
        if feedback.isCanceled():
            return {}

        # Save Builtup_Shapefile vector features to file
        builtup_output_path = os.path.normpath(os.path.join(
            project_folder, 'Builtup_Shapefile.shp'))
        builtup_base_path = builtup_output_path[:-4]

        builtup_tmp_base = builtup_base_path + '_tmp'
        builtup_tmp_path = builtup_tmp_base + '.shp'
        for _ext in SHP_EXTS:
            _fp = builtup_tmp_base + _ext
            if os.path.isfile(_fp):
                try:
                    os.remove(_fp)
                except Exception:
                    pass

        alg_params = {
            'DATASOURCE_OPTIONS': '',
            'INPUT': outputs['Ref_colCalcluation_plinth']['OUTPUT'],
            'LAYER_NAME': 'Builtup_Shapefile',
            'LAYER_OPTIONS': '',
            'OUTPUT': builtup_tmp_path
        }
        outputs['Save_builtup_shapefile'] = processing.run(
            'native:savefeatures', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        _release_shp_layers(project, builtup_base_path)
        _atomic_overwrite_shp(builtup_tmp_base, builtup_base_path)
        outputs['Save_builtup_shapefile'] = {'OUTPUT': builtup_output_path}

        feedback.setCurrentStep(16)
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

        feedback.setCurrentStep(17)
        if feedback.isCanceled():
            return {}

        # Set build_area_sqmts project variable
        alg_params = {
            'NAME': 'build_area_sqmts',
            'VALUE': 'b_sqmts'
        }
        outputs['SetBuildAreaVariable'] = processing.run(
            'native:setprojectvariable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        if feedback.isCanceled():
            return {}

        delete_small_parcels('Builtup_Shapefile', 1)
        toggle_layervisibility(lpm_param_value, False)

        feedback.setCurrentStep(18)
        if feedback.isCanceled():
            return {}

        # Boundary plinth area
        alg_params = {
            # outputs['MergeIntersectionAndDiffrence']['OUTPUT'],
            'INPUT': outputs['Save_builtup_shapefile']['OUTPUT'],
            'OUTPUT':  QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['BoundaryPlinthArea'] = processing.run(
            'native:boundary', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # Save Builtup_Boundary vector features to file
        builtup_bdry_base = os.path.normpath(
            os.path.join(project_folder, 'Builtup_Boundary'))
        builtup_bdry_tmp_base = builtup_bdry_base + '_tmp'
        alg_params = {
            'DATASOURCE_OPTIONS': '',
            'INPUT': outputs['BoundaryPlinthArea']['OUTPUT'],
            'LAYER_NAME': 'Builtup_Boundary',
            'LAYER_OPTIONS': '',
            'OUTPUT': builtup_bdry_tmp_base + '.shp'
        }
        outputs['SaveVectorFeaturesToFile'] = processing.run(
            'native:savefeatures', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        _release_shp_layers(project, builtup_bdry_base)
        _atomic_overwrite_shp(builtup_bdry_tmp_base, builtup_bdry_base)
        outputs['SaveVectorFeaturesToFile'] = {
            'OUTPUT': builtup_bdry_base + '.shp'}

        feedback.setCurrentStep(19)
        if feedback.isCanceled():
            return {}

        # Explode lines plinth area
        alg_params = {
            'INPUT': outputs['BoundaryPlinthArea']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['ExplodeLinesPlinthArea'] = processing.run(
            'native:explodelines', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(20)
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
        plot_expl_base = os.path.normpath(
            os.path.join(project_folder, 'Plot_ExplodeLines'))
        plot_expl_tmp_base = plot_expl_base + '_tmp'
        alg_params = {
            'DATASOURCE_OPTIONS': '',
            'INPUT': outputs['RefactorplotExplodedLines']['OUTPUT'],
            'LAYER_NAME': 'Plot_ExplodeLines',
            'LAYER_OPTIONS': '',
            'OUTPUT': plot_expl_tmp_base + '.shp'
        }
        outputs['Save_Plot_ExplodeLines'] = processing.run(
            'native:savefeatures', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        _release_shp_layers(project, plot_expl_base)
        _atomic_overwrite_shp(plot_expl_tmp_base, plot_expl_base)
        outputs['Save_Plot_ExplodeLines'] = {'OUTPUT': plot_expl_base + '.shp'}

        feedback.setCurrentStep(21)
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
        builtup_expl_base = os.path.normpath(
            os.path.join(project_folder, 'Builtup_ExplodeLines'))
        builtup_expl_tmp_base = builtup_expl_base + '_tmp'
        alg_params = {
            'DATASOURCE_OPTIONS': '',
            'INPUT': outputs['RefactorplinthExplodedLines']['OUTPUT'],
            'LAYER_NAME': 'Builtup_ExplodeLines',
            'LAYER_OPTIONS': '',
            'OUTPUT': builtup_expl_tmp_base + '.shp'
        }
        outputs['Save_Builtup_ExplodeLines'] = processing.run(
            'native:savefeatures', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        _release_shp_layers(project, builtup_expl_base)
        _atomic_overwrite_shp(builtup_expl_tmp_base, builtup_expl_base)
        outputs['Save_Builtup_ExplodeLines'] = {
            'OUTPUT': builtup_expl_base + '.shp'}

        plinth_explode_layer = QgsVectorLayer(
            outputs['Save_Builtup_ExplodeLines']['OUTPUT'], 'Builtup_ExplodeLines', 'ogr')
        project.addMapLayer(plinth_explode_layer, True)

        # Load plot explode lines into project
        plot_explode_layer = QgsVectorLayer(
            outputs['Save_Plot_ExplodeLines']['OUTPUT'], 'Plot_ExplodeLines', 'ogr')
        project.addMapLayer(plot_explode_layer, True)

        feedback.setCurrentStep(12)
        if feedback.isCanceled():
            return {}

        # Extract vertices of plot
        vertices_base = os.path.normpath(
            os.path.join(project_folder, 'Plot_Vertices'))
        vertices_tmp_base = vertices_base + '_tmp'
        alg_params = {
            'INPUT': outputs['Ref_colCalcluation_plot']['OUTPUT'],
            'OUTPUT': vertices_tmp_base + '.shp'
        }
        outputs['ExtractVerticesof_plot'] = processing.run(
            'native:extractvertices', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        _release_shp_layers(project, vertices_base)
        _atomic_overwrite_shp(vertices_tmp_base, vertices_base)
        outputs['ExtractVerticesof_plot'] = {'OUTPUT': vertices_base + '.shp'}

        # Load vertices into project
        plot_vertices_layer = QgsVectorLayer(
            outputs['ExtractVerticesof_plot']['OUTPUT'], 'Plot_Vertices', 'ogr')
        project.addMapLayer(plot_vertices_layer, True)

        feedback.setCurrentStep(13)
        if feedback.isCanceled():
            return {}

        # Set Plot explode style
        alg_params = {
            'INPUT': plot_explode_layer,
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
            'INPUT': plot_vertices_layer,
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
            template_path=assets_folder + "/templates/PPM_Template.qpt",
            template_name="A4_PPM_TEMPLATE",
            coverage_layer=coverage_layer,
            page_name_field=parameters['property_parcel_number'],
            text1=None,
            text2=None,
            text3=None,

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
        <p><a href="https://lgdirectory.gov.in/demo/globalviewvillageforcitizen.do?" target="_blank">Know Your Revenue LGD Code</a></p>
        </html>"""

    def createInstance(self):
        return SvamitvaPPMAlgorithm()

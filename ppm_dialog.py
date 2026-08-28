# -*- coding: utf-8 -*-
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QComboBox, QLineEdit,
                                 QPushButton, QMessageBox, QFormLayout, QDialogButtonBox, QProgressBar, QTabWidget, QWidget, QLabel)
from qgis.core import QgsProject, QgsMapLayerProxyModel, QgsExpressionContextUtils, QgsProcessingFeedback
from qgis.gui import QgsMapLayerComboBox, QgsFieldComboBox
from qgis.PyQt.QtCore import QCoreApplication
from .addon_functions import districtlist, asksaveProject
from .qt_compat import QtCompat
import processing
import os


class PPMDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PPM Generation")
        self.resize(500, 480)
        self.setup_ui()
        self.load_defaults()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Create Tab Widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # --- Tab 1: Village Data ---
        self.village_tab = QWidget()
        village_layout = QFormLayout()

        # 6. District
        self.district_cb = QComboBox()
        self.district_cb.addItems(districtlist())
        village_layout.addRow("District:", self.district_cb)

        # 7. Mandal
        self.mandal_edit = QLineEdit()
        village_layout.addRow("Mandal Name:", self.mandal_edit)

        # Revenue Village Name (New)
        self.village_name_edit = QLineEdit()
        village_layout.addRow("Revenue Village Name:", self.village_name_edit)

        # 8. Grama Panchayat
        self.panchayat_edit = QLineEdit()
        village_layout.addRow("Grama Panchayat Name:", self.panchayat_edit)

        # 10. Village Code (LGD)
        self.lgd_code_edit = QLineEdit()
        village_layout.addRow(
            "Revenue Village Code (LGD):", self.lgd_code_edit)

        # 9. Panchayat Code
        self.panchayat_code_edit = QLineEdit()
        village_layout.addRow("Grama Panchayat Code:",
                              self.panchayat_code_edit)

        # Save Button
        self.btn_save_village = QPushButton("Save Village Data")
        self.btn_save_village.clicked.connect(self.save_village_data_only)
        village_layout.addRow(self.btn_save_village)

        self.village_tab.setLayout(village_layout)
        self.tab_widget.addTab(self.village_tab, "Village Data")

        # --- Tab 2: PPM Generation ---
        self.ppm_tab = QWidget()
        ppm_main_layout = QVBoxLayout()
        ppm_form_layout = QFormLayout()

        # 1. Plot Shapefile
        self.plot_layer_cb = QgsMapLayerComboBox()
        self.plot_layer_cb.setFilters(QgsMapLayerProxyModel.Filter.PolygonLayer)
        ppm_form_layout.addRow("Plot Shapefile:", self.plot_layer_cb)

        # 2. Property Parcel Number (Field)
        self.prop_field_cb = QgsFieldComboBox()
        self.prop_field_cb.setLayer(self.plot_layer_cb.currentLayer())
        self.plot_layer_cb.layerChanged.connect(self.prop_field_cb.setLayer)
        ppm_form_layout.addRow("Property Parcel Number:", self.prop_field_cb)

        # 3. Plot Area Sq Meters (Field)
        self.area_sqmt_cb = QgsFieldComboBox()
        self.area_sqmt_cb.setLayer(self.plot_layer_cb.currentLayer())
        self.plot_layer_cb.layerChanged.connect(self.area_sqmt_cb.setLayer)
        ppm_form_layout.addRow(
            "Plot Area In Sq Meters Field:", self.area_sqmt_cb)

        # 4. Plot Area Sq Yards (Field)
        self.area_sqyd_cb = QgsFieldComboBox()
        self.area_sqyd_cb.setLayer(self.plot_layer_cb.currentLayer())
        self.plot_layer_cb.layerChanged.connect(self.area_sqyd_cb.setLayer)
        ppm_form_layout.addRow("Plot Area Sq Yards Field:", self.area_sqyd_cb)

        # 5. Plinth Shapefile
        self.plinth_layer_cb = QgsMapLayerComboBox()
        self.plinth_layer_cb.setFilters(QgsMapLayerProxyModel.Filter.PolygonLayer)
        ppm_form_layout.addRow(
            "Builtup (Plinth) Shapefile:", self.plinth_layer_cb)

        ppm_main_layout.addLayout(ppm_form_layout)

        # PPM Run Button
        self.btn_run_ppm = QPushButton("Run PPM Generation")
        self.btn_run_ppm.clicked.connect(self.run_ppm_process)
        ppm_main_layout.addWidget(self.btn_run_ppm)

        self.ppm_tab.setLayout(ppm_main_layout)
        self.tab_widget.addTab(self.ppm_tab, "PPM Generation")

        # --- Other Tabs ---
        other_tabs = ["Habitation Map", "Correlation",
                      "Habitation ORI Map", "Traverse Map"]
        for name in other_tabs:
            tab = QWidget()
            tab_layout = QVBoxLayout()
            tab_layout.addWidget(QLabel("Coming Soon", alignment=QtCompat.AlignCenter))
            btn = QPushButton(f"Run {name}")
            btn.setEnabled(False)
            tab_layout.addWidget(btn)
            tab.setLayout(tab_layout)
            self.tab_widget.addTab(tab, name)

        # Close Button
        self.button_box = QDialogButtonBox(QtCompat.DialogClose)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def load_defaults(self):
        # Set default fields if they exist
        self.prop_field_cb.setField('prop_id')
        self.area_sqyd_cb.setField('area_sqyds')
        self.area_sqmt_cb.setField('area_sqmts')

        # Load variables from project scope
        project = QgsProject.instance()
        project_scope = QgsExpressionContextUtils.projectScope(project)

        # District
        district_eng = project_scope.variable('district_eng')
        if district_eng:
            index = self.district_cb.findText(district_eng)
            if index >= 0:
                self.district_cb.setCurrentIndex(index)
            else:
                self.district_cb.setCurrentIndex(-1)
        else:
            self.district_cb.setCurrentIndex(-1)

        # Mandal
        mandal = project_scope.variable('Mandal_Name_eng')
        self.mandal_edit.setText(str(mandal) if mandal else "")

        # Panchayat
        panchayat = project_scope.variable('Panchyat_eng')
        self.panchayat_edit.setText(str(panchayat) if panchayat else "")

        # Village Name
        v_name = project_scope.variable('Village_Name')
        self.village_name_edit.setText(str(v_name) if v_name else "")

        # Panchayat Code
        p_code = project_scope.variable('Panchyat_Code')
        self.panchayat_code_edit.setText(str(p_code) if p_code else "")

        # LGD Code
        lgd = project_scope.variable('P_LGD_Code')
        self.lgd_code_edit.setText(str(lgd) if lgd else "")

    def validate_village_data(self):
        if not self.district_cb.currentText():
            QMessageBox.warning(self, "Validation Error",
                                "Please select a District.")
            return False
        if not self.mandal_edit.text().strip():
            QMessageBox.warning(self, "Validation Error",
                                "Please enter Mandal Name.")
            return False
        if not self.panchayat_edit.text().strip():
            QMessageBox.warning(self, "Validation Error",
                                "Please enter Grama Panchayat Name.")
            return False
        if not self.village_name_edit.text().strip():
            QMessageBox.warning(self, "Validation Error",
                                "Please enter Revenue Village Name.")
            return False
        if not self.panchayat_code_edit.text().strip():
            QMessageBox.warning(self, "Validation Error",
                                "Please enter Grama Panchayat Code.")
            return False
        if not self.lgd_code_edit.text().strip():
            QMessageBox.warning(self, "Validation Error",
                                "Please enter Village Code (LGD).")
            return False
        return True

    def save_village_data(self):
        # Save village data to project variables
        project = QgsProject.instance()
        QgsExpressionContextUtils.setProjectVariable(
            project, 'district_eng', self.district_cb.currentText())
        QgsExpressionContextUtils.setProjectVariable(
            project, 'Mandal_Name_eng', self.mandal_edit.text())
        QgsExpressionContextUtils.setProjectVariable(
            project, 'Panchyat_eng', self.panchayat_edit.text())
        QgsExpressionContextUtils.setProjectVariable(
            project, 'Panchyat_Code', self.panchayat_code_edit.text())
        QgsExpressionContextUtils.setProjectVariable(
            project, 'P_LGD_Code', self.lgd_code_edit.text())
        QgsExpressionContextUtils.setProjectVariable(
            project, 'Village_Name', self.village_name_edit.text())

        # Also set globals for backward compatibility if needed by other parts
        QgsExpressionContextUtils.setGlobalVariable(
            'district_eng', self.district_cb.currentText())
        QgsExpressionContextUtils.setGlobalVariable(
            'Mandal_Name_eng', self.mandal_edit.text())
        QgsExpressionContextUtils.setGlobalVariable(
            'Panchyat_eng', self.panchayat_edit.text())
        QgsExpressionContextUtils.setGlobalVariable(
            'Panchyat_Code', self.panchayat_code_edit.text())
        QgsExpressionContextUtils.setGlobalVariable(
            'P_LGD_Code', self.lgd_code_edit.text())
        QgsExpressionContextUtils.setGlobalVariable(
            'Village_Name', self.village_name_edit.text())

    def save_village_data_only(self):
        if not self.validate_village_data():
            return
        self.save_village_data()
        QMessageBox.information(
            self, "Success", "Village Data Saved Successfully.")

    def run_ppm_process(self):
        # Ensure project is saved before running
        if not asksaveProject():
            return

        # Save village data first
        self.save_village_data()

        # Gather parameters
        plot_layer = self.plot_layer_cb.currentLayer()
        plinth_layer = self.plinth_layer_cb.currentLayer()

        if not plot_layer or not plinth_layer:
            QMessageBox.warning(self, "Warning", "Please select both layers.")
            return

        # --- Remove existing layers to prevent file locks ---
        project = QgsProject.instance()
        project_path = project.fileName()
        if project_path:
            project_folder = os.path.dirname(project_path)
        else:
            project_folder = QgsProject.instance().homePath() or os.path.expanduser("~")

        layer_names = ['Builtup_ExplodeLines', 'Plot_Shapefile', 'Builtup_Shapefile', 'Plot_ExplodeLines', 'Plot_Vertices',
                       'Exploded_Lines', 'Boundary', 'Plot_Boundary', 'Builtup_Boundary']
        target_files = {'Plot_Shapefile.shp', 'Plot_Boundary.shp', 'Builtup_Shapefile.shp', 'Builtup_Boundary.shp',
                        'Plot_ExplodeLines.shp', 'Builtup_ExplodeLines.shp', 'Plot_Vertices.shp'}

        ids_to_remove = set()

        # 1. By Name
        for name in layer_names:
            for lyr in project.mapLayersByName(name):
                ids_to_remove.add(lyr.id())

        # 2. By Source (file path in project folder)
        if project_folder:
            for lyr in project.mapLayers().values():
                if lyr.providerType() == 'ogr':
                    source = lyr.source()
                    path = source.split('|')[0]
                    if os.path.basename(path) in target_files:
                        try:
                            if os.path.abspath(os.path.dirname(path)) == os.path.abspath(project_folder):
                                ids_to_remove.add(lyr.id())
                        except Exception:  # nosec B110
                            pass

        # Exclude inputs
        if plot_layer:
            ids_to_remove.discard(plot_layer.id())
        if plinth_layer:
            ids_to_remove.discard(plinth_layer.id())

        if ids_to_remove:
            project.removeMapLayers(list(ids_to_remove))
            import gc
            gc.collect()
        # --------------------------------------------------

        params = {
            'choose_plot_shapefile': plot_layer,
            'property_parcel_number': self.prop_field_cb.currentField(),
            'plot_area_in_square_yards': self.area_sqyd_cb.currentField(),
            'plot_area_in_square_metres': self.area_sqmt_cb.currentField(),
            'choose_plinth_shapefile': plinth_layer,
            'district_name_eng': self.district_cb.currentIndex(),
            'name_of_the_mandal': self.mandal_edit.text(),
            'name_of_the_grama_panchayat': self.panchayat_edit.text(),
            'gram_panchayat_code': self.panchayat_code_edit.text(),
            'village_code_lgd_code': self.lgd_code_edit.text()
        }

        # Disable UI to prevent interference
        self.button_box.setEnabled(False)

        try:
            # Run the processing algorithm
            processing.run("Gruhanaksha:ppm_new_model",
                           params)
            QMessageBox.information(
                self, "Success", "PPM Generation Completed.")
            # self.accept() # Don't close automatically on run
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {e}")
        finally:
            self.btn_run_ppm.setEnabled(True)
            self.button_box.setEnabled(True)

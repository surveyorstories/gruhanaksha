
import math
from qgis.PyQt.QtGui import QIcon

import inspect
import sys
import processing
import os
from qgis.PyQt.QtCore import QVariant
from qgis.utils import iface
# Removed import of qApp as it is not available in qgis.PyQt.QtWidgets for Qt6
# from qgis.PyQt.QtWidgets import qApp
from qgis.core import QgsProject
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtWidgets import QCheckBox, QSpinBox,  QVBoxLayout, QWidget, QPushButton, QMessageBox, QHBoxLayout, QComboBox, QGroupBox, QProgressBar, QGridLayout
from qgis.PyQt.QtCore import Qt

from typing import Optional, Dict, List
from qgis.PyQt.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
                                 QSpinBox, QComboBox, QPushButton, QProgressBar,
                                 QApplication as qApp)

from typing import Optional, Dict
from typing import Optional, Dict, List, Tuple
from .fmb import TriangleWidget, PlotterWidget,  CombinedMainWidget
from .freehand_adjuster import activate_vertex_tool
from .autosaveandbackup import BackupPlugin
from .polygon_adjuster import activate_unified_tool
from .pointinput import PointInputDialog
from .aligner import init_align_tool
from .kmz import KMZExporterDialog
from .polygon_splitter import show_polygon_splitter
from .marker_tool import MarkerMapTool
from .trim_and_extend import activate_trim_extend_tool
from .topology_checker import TopologyCheckerDialog
from .traverse_plotter import TraversePlotterDialog
from . import lpm_canvas

# make top level widget
from .addon_functions import TOOL_WINDOW_FLAGS, STAY_ON_TOP_FLAG

triangle_window = TriangleWidget()
plotter_window = PlotterWidget()
# bisector_window = BisectorWidget()
combined_window = CombinedMainWidget()
# adjuster_window = PolygonAdjusterWidget()


cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]
icon = QIcon(os.path.join(os.path.join(cmd_folder, 'images/topo.svg')))

project = QgsProject.instance()
project_folder = project.readPath("./")


# Get the main QGIS window and set it as the parent for the widget
qgis_main_window = iface.mainWindow()


class ToolWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(iface.mainWindow())

        # Set window flags for title and close button only
        self.setWindowFlags(TOOL_WINDOW_FLAGS)
        # self.setWindowFlag(STAY_ON_TOP_FLAG, True)
        self.setWindowTitle("Tool Panel")
        self.setGeometry(220, 250, 230, 200)
        # self.setWindowFlags(Qt.Window)  # Make it a standalone window
        # self.setAttribute(Qt.WA_DeleteOnClose)  # Allow cleanup when closed
        self.resize(300, 100)
        self.function_completed = False
        self.setWindowIcon(QIcon(icon))

        # Initialize backup_plugin as None - will be created on first use
        self.backup_plugin = None

        # Initialize point_input_dialog as None
        self.point_input_dialog = None

        # Initialize kmz_dialog as None
        self.kmz_dialog = None

        # Initialize traverse_dialog as None
        self.traverse_dialog = None

        # Initialize topo_dialog as None
        self.topo_dialog = None

        # Initialize recovery_dialog as None
        self.recovery_dialog = None

        main_layout = QVBoxLayout(self)

        # Group box named "Tool"
        group_box = QGroupBox("Tools")
        group_layout = QVBoxLayout()

        # Buttons
        self.plotter_button = QPushButton(
            QIcon(os.path.join(cmd_folder, 'images/plotter.svg')), 'Plotter')
        self.plotter_button.setToolTip("Open Plotter Tool")
        self.plotter_button.setStyleSheet(
            "background-color: #020507 ; color: white")

        self.adjuster_button = QPushButton(
            QIcon(os.path.join(cmd_folder, 'images/aligner.svg')), 'Adjuster')
        self.adjuster_button.setToolTip("Open Adjuster Tool")
        self.adjuster_button.setStyleSheet(
            "background-color: #020507 ; color: white")

        self.free_adjuster_button = QPushButton(
            QIcon(os.path.join(cmd_folder, 'images/aligner.svg')), 'Free Adjuster')
        self.free_adjuster_button.setToolTip("Open Free Adjuster Tool")
        self.free_adjuster_button.setStyleSheet(
            "background-color: #020507 ; color: white")

        self.backup_button = QPushButton(
            QIcon(os.path.join(cmd_folder, 'images/autosave.svg')), 'Backup')
        self.backup_button.setToolTip("Open Backup Tool")
        self.backup_button.setStyleSheet(
            "background-color: #020507 ; color: white")

        self.aligner_button = QPushButton(
            QIcon(os.path.join(cmd_folder, 'images/aligner.svg')), 'Aligner')
        self.aligner_button.setToolTip("Open Aligner Tool")
        self.aligner_button.setStyleSheet(
            "background-color: #020507 ; color: white")

        self.point_input_button = QPushButton(
            QIcon(os.path.join(cmd_folder, 'images/add_point.svg')), 'Point Input')
        self.point_input_button.setToolTip("Open Point Input Tool")
        self.point_input_button.setStyleSheet(
            "background-color: #020507 ; color: white")

        self.kmz_button = QPushButton(
            QIcon(os.path.join(cmd_folder, 'images/export.svg')), 'KMZ')
        self.kmz_button.setToolTip("Open KMZ Exporter Tool")
        self.kmz_button.setStyleSheet(
            "background-color: #020507 ; color: white")

        self.splitter_button = QPushButton(
            QIcon(os.path.join(cmd_folder, 'images/splitter.svg')), 'Polygon Splitter')
        self.splitter_button.setToolTip("Split polygon by area")
        self.splitter_button.setStyleSheet(
            "background-color: #020507 ; color: white")

        self.trim_extend_button = QPushButton(
            QIcon(os.path.join(cmd_folder, 'images/canvas_one/cut.svg')), 'Trim/Extend')
        self.trim_extend_button.setToolTip("Trim or Extend Lines/Polygons")
        self.trim_extend_button.setStyleSheet(
            "background-color: #020507 ; color: white")

        self.auto_numbering_button = QPushButton(
            QIcon(os.path.join(cmd_folder, 'images/snake_original.svg')), 'Auto Numbering')
        self.auto_numbering_button.setToolTip("Open Auto Numbering Tool")
        self.auto_numbering_button.setStyleSheet(
            "background-color: #020507 ; color: white")

        self.topo_checker_button = QPushButton(
            QIcon(os.path.join(cmd_folder, 'images/topo.svg')), 'Topology Checker')
        self.topo_checker_button.setToolTip("Open Topology Checker Tool")
        self.topo_checker_button.setStyleSheet(
            "background-color: #020507 ; color: white")

        self.traverse_plotter_button = QPushButton(
            QIcon(os.path.join(cmd_folder, 'images/plotter.svg')), 'Traverse Plotter')
        self.traverse_plotter_button.setToolTip("Open Traverse Plotter Tool")
        self.traverse_plotter_button.setStyleSheet(
            "background-color: #020507 ; color: white")

        # Connect button actions
        self.plotter_button.clicked.connect(self.combined_button_clicked)
        self.adjuster_button.clicked.connect(self.adjuster_button_clicked)
        self.free_adjuster_button.clicked.connect(
            self.free_adjuster_button_clicked)
        self.backup_button.clicked.connect(self.backup_button_clicked)
        self.aligner_button.clicked.connect(self.aligner_button_clicked)
        self.point_input_button.clicked.connect(
            self.point_input_button_clicked)
        self.kmz_button.clicked.connect(self.kmz_button_clicked)
        self.splitter_button.clicked.connect(self.splitter_button_clicked)
        self.trim_extend_button.clicked.connect(
            self.trim_extend_button_clicked)
        self.auto_numbering_button.clicked.connect(
            self.auto_numbering_button_clicked)
        self.topo_checker_button.clicked.connect(
            self.topo_checker_button_clicked)
        self.traverse_plotter_button.clicked.connect(
            self.traverse_plotter_button_clicked)

        # GridLayout for buttons
        grid_layout = QGridLayout()

        # Row 1
        grid_layout.addWidget(self.plotter_button, 0, 0)
        grid_layout.addWidget(self.adjuster_button, 0, 1)
        grid_layout.addWidget(self.free_adjuster_button, 0, 2)

        # Row 2
        grid_layout.addWidget(self.backup_button, 1, 0)
        grid_layout.addWidget(self.aligner_button, 1, 1)
        grid_layout.addWidget(self.point_input_button, 1, 2)

        # Row 3
        grid_layout.addWidget(self.kmz_button, 2, 0)
        grid_layout.addWidget(self.splitter_button, 2, 1)
        grid_layout.addWidget(self.trim_extend_button, 2, 2)
        grid_layout.addWidget(self.auto_numbering_button, 3, 0)
        grid_layout.addWidget(self.topo_checker_button, 3, 1)
        grid_layout.addWidget(self.traverse_plotter_button, 3, 2)

        # Add grid to the main group layout
        group_layout.addLayout(grid_layout)

        group_box.setLayout(group_layout)
        main_layout.addWidget(group_box)

    def closeEvent(self, event):
        self.hide()
        event.ignore()

    def backup_button_clicked(self):
        try:
            # Create the backup plugin only once, then reuse it
            if self.backup_plugin is None:
                self.backup_plugin = BackupPlugin(iface)

            # Show and activate the widget inside the plugin
            widget = self.backup_plugin.widget

            # If minimized, restore it first
            if widget.isMinimized():
                widget.showNormal()
            else:
                widget.show()

            widget.raise_()
            widget.activateWindow()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {e}")


    def adjuster_button_clicked(self):
        activate_unified_tool()

    def free_adjuster_button_clicked(self):
        activate_vertex_tool()

    def aligner_button_clicked(self):
        init_align_tool()

    def point_input_button_clicked(self):
        try:
            # Create dialog if it doesn't exist or has been closed
            if self.point_input_dialog is None or not self.point_input_dialog.isVisible():
                self.point_input_dialog = PointInputDialog(iface)
            self.point_input_dialog.show()
            self.point_input_dialog.activateWindow()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {e}")

    def combined_button_clicked(self):
        try:
            combined_window.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {e}")

    def kmz_button_clicked(self):
        try:
            if self.kmz_dialog is None or not self.kmz_dialog.isVisible():
                self.kmz_dialog = KMZExporterDialog()
            self.kmz_dialog.show()
            self.kmz_dialog.raise_()
            self.kmz_dialog.activateWindow()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {e}")

    def bisector_button_clicked(self):
        try:
            bisector_window.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {e}")

    def splitter_button_clicked(self):
        try:
            show_polygon_splitter()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {e}")

    def trim_extend_button_clicked(self):
        try:
            activate_trim_extend_tool()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {e}")

    def auto_numbering_button_clicked(self):
        try:
            if lpm_canvas.lpno.isMinimized():
                lpm_canvas.lpno.showNormal()
            else:
                lpm_canvas.lpno.show()
            lpm_canvas.lpno.raise_()
            lpm_canvas.lpno.activateWindow()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {e}")

    def topo_checker_button_clicked(self):
        try:
            if self.topo_dialog is None:
                self.topo_dialog = TopologyCheckerDialog(iface=iface)
            self.topo_dialog.show()
            self.topo_dialog.raise_()
            self.topo_dialog.activateWindow()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {e}")

    def traverse_plotter_button_clicked(self):
        try:
            if self.traverse_dialog is None or not self.traverse_dialog.isVisible():
                self.traverse_dialog = TraversePlotterDialog(self)
            self.traverse_dialog.show()
            self.traverse_dialog.raise_()
            self.traverse_dialog.activateWindow()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {e}")

    def recovery_button_clicked(self):
        try:
            from .crash_recovery_dialog import CrashRecoveryDialog
            if self.recovery_dialog is None or not self.recovery_dialog.isVisible():
                self.recovery_dialog = CrashRecoveryDialog(self)
            self.recovery_dialog.show()
            self.recovery_dialog.raise_()
            self.recovery_dialog.activateWindow()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {e}")

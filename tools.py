
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
from qgis.PyQt.QtWidgets import QCheckBox, QSpinBox,  QVBoxLayout, QWidget, QPushButton, QMessageBox, QHBoxLayout, QComboBox, QGroupBox, QProgressBar
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

        # Connect button actions
        self.plotter_button.clicked.connect(self.combined_button_clicked)
        self.adjuster_button.clicked.connect(self.adjuster_button_clicked)
        self.free_adjuster_button.clicked.connect(
            self.free_adjuster_button_clicked)
        self.backup_button.clicked.connect(self.backup_button_clicked)

        # Layout for the first row of buttons
        row1_layout = QHBoxLayout()
        row1_layout.addWidget(self.plotter_button)
        row1_layout.addWidget(self.adjuster_button)
        row1_layout.addWidget(self.free_adjuster_button)

        # Layout for the second row of buttons
        row2_layout = QHBoxLayout()
        row2_layout.addWidget(self.backup_button)

        # Add rows to the main group layout
        group_layout.addLayout(row1_layout)
        group_layout.addLayout(row2_layout)

        group_box.setLayout(group_layout)
        main_layout.addWidget(group_box)

    def closeEvent(self, event):
        self.hide()
        event.ignore()

    def backup_button_clicked(self):
        try:
            self.backup_plugin = BackupPlugin(iface)
            self.backup_plugin.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {e}")

    def adjuster_button_clicked(self):
        activate_unified_tool()

    def free_adjuster_button_clicked(self):
        activate_vertex_tool()

    def combined_button_clicked(self):
        try:

            combined_window.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {e}")

    def bisector_button_clicked(self):

        try:
            bisector_window.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {e}")

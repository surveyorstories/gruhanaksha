from PyQt5.QtGui import QColor
from qgis.PyQt.QtCore import QVariant
from qgis.core import (QgsPointXY, QgsGeometry,
                       QgsFeature,  QgsSymbol, QgsCategorizedSymbolRenderer,
                       QgsRendererCategory, )
from PyQt5.QtWidgets import QDoubleSpinBox,   QLabel, QFileDialog
import math
from qgis.PyQt.QtGui import QIcon
from qgis.gui import QgsMapLayerComboBox
import inspect
import sys
import processing
import os
from PyQt5 import QtCore
from PyQt5.QtCore import QVariant
from qgis.utils import iface
from qgis.PyQt.QtWidgets import qApp
from qgis.core import QgsVectorLayer, QgsRasterLayer, QgsMapLayerProxyModel, QgsProject, QgsMapLayer, QgsWkbTypes, QgsVectorFileWriter, QgsField, QgsFillSymbol, QgsSingleSymbolRenderer, QgsMapLayerType, QgsProcessing, QgsProcessingContext, QgsProcessingFeedback, QgsExpressionContextUtils
from qgis.PyQt.QtWidgets import QAction
from PyQt5.QtWidgets import QCheckBox, QSpinBox,  QVBoxLayout, QWidget, QPushButton, QMessageBox, QHBoxLayout, QComboBox, QGroupBox, QProgressBar
from PyQt5.QtCore import Qt

from typing import Optional, Dict, List
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QSpinBox, QComboBox, QPushButton, QProgressBar,
                             QApplication as qApp)
from qgis.core import (QgsVectorLayer, QgsMapLayerProxyModel, QgsFeature,
                       QgsMessageLog, QgsVectorDataProvider)
from typing import Optional, Dict
from typing import Optional, Dict, List, Tuple
from .fmb import TriangleWidget, PlotterWidget,  CombinedMainWidget
from .freehand_adjuster import activate_vertex_tool

from .polygon_adjuster import activate_unified_tool


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

triangle_window.setParent(qgis_main_window, Qt.Window)
combined_window.setParent(qgis_main_window, Qt.Window)


class ToolWidget(QWidget):
    def __init__(self, parent=None):
        super(ToolWidget, self).__init__(parent)
        self.setWindowTitle("Tool Panel")
        self.setGeometry(220, 150, 230, 200)
        # self.setWindowFlags(Qt.Window)  # Make it a standalone window
        # self.setAttribute(Qt.WA_DeleteOnClose)  # Allow cleanup when closed
        self.resize(300, 100)
        self.function_completed = False
        self.setWindowIcon(QIcon(icon))

        main_layout = QVBoxLayout(self)

        # Group box named "Tool"
        group_box = QGroupBox("Tools")
        group_layout = QHBoxLayout()

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
        

        # Connect button actions

        self.plotter_button.clicked.connect(self.combined_button_clicked)
        self.adjuster_button.clicked.connect(self.adjuster_button_clicked)
        self.free_adjuster_button.clicked.connect(self.free_adjuster_button_clicked)

        # Horizontal layout with spacing
        group_layout.addStretch(1)

        group_layout.addStretch(1)
        group_layout.addWidget(self.plotter_button)
        group_layout.addStretch(1)
        group_layout.addWidget(self.adjuster_button)
        group_layout.addStretch(1)
        group_layout.addWidget(self.free_adjuster_button)
        group_layout.addStretch(1)

        group_box.setLayout(group_layout)
        main_layout.addWidget(group_box)

    def closeEvent(self, event):
        self.hide()
        event.ignore()

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

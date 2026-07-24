from qgis.PyQt.QtWidgets import (QDialog, QMainWindow, QVBoxLayout, QHBoxLayout, QPushButton,
                                  QListWidget, QLabel, QFileDialog, QWidget, QToolBar, QAction, QMenu, QMessageBox)
from qgis.PyQt.QtCore import Qt, QSize
from qgis.PyQt.QtGui import QPixmap, QImage
from qgis.PyQt.QtPrintSupport import QPrinter
from qgis.utils import iface
from qgis.core import QgsProject, QgsRectangle, QgsFeatureRequest, QgsMapLayer
from qgis.gui import (QgsLayerTreeView, QgsMapCanvas, QgsMapTool, QgsMapToolEmitPoint, QgsRubberBand,
                      QgsVertexMarker, QgsLayerTreeMapCanvasBridge, QgsLayerTreeViewMenuProvider, QgsLayerTreeViewDefaultActions)
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import QTextEdit
from .qt_compat import QtCompat


class PresenterMenuProvider(QgsLayerTreeViewMenuProvider):
    def __init__(self, view, canvas):
        super().__init__()
        self.view = view
        self.canvas = canvas
        self.actions = QgsLayerTreeViewDefaultActions(self.view)

    def createContextMenu(self):
        node = self.view.currentNode()
        if not node:
            return None

        menu = QMenu()
        
        from qgis.core import QgsLayerTreeLayer, QgsLayerTreeGroup
        
        if isinstance(node, QgsLayerTreeLayer):
            layer = node.layer()
            if layer:
                # Zoom to Layer
                menu.addAction(self.actions.actionZoomToLayers(self.canvas))
                # Show Feature Count
                menu.addAction(self.actions.actionShowFeatureCount())
                menu.addSeparator()
                
                # Toggle Editing (for vector layers)
                from qgis.core import QgsVectorLayer
                if isinstance(layer, QgsVectorLayer):
                    edit_act = menu.addAction("Toggle Editing")
                    edit_act.setCheckable(True)
                    edit_act.setChecked(layer.isEditable())
                    edit_act.triggered.connect(lambda: self.toggle_editing(layer))
                
                # Remove
                remove_act = menu.addAction("Remove Layer")
                remove_act.triggered.connect(lambda: QgsProject.instance().removeMapLayer(layer.id()))
                
                menu.addSeparator()
                # Properties
                properties_act = menu.addAction("Properties...")
                properties_act.triggered.connect(lambda: iface.showLayerProperties(layer))
                
        elif isinstance(node, QgsLayerTreeGroup):
            menu.addAction(self.actions.actionRenameGroupOrLayer())
            menu.addAction(self.actions.actionAddGroup())
            menu.addAction(self.actions.actionRemoveGroupOrLayer())
            
        return menu

    def toggle_editing(self, layer):
        if layer.isEditable():
            if not layer.commitChanges():
                QMessageBox.warning(self.view.window(), "Editing", f"Could not commit changes: {layer.commitErrors()}")
        else:
            layer.startEditing()


class DraggableOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.drag_position = None

    def mousePressEvent(self, event):
        if event.button() == QtCompat.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == QtCompat.LeftButton and self.drag_position is not None:
            self.move(event.globalPos() - self.drag_position)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.drag_position = None
        super().mouseReleaseEvent(event)




class PresentationDialog(QDialog):
    """Simple presentation dialog that captures map canvas slides and shows them fullscreen."""

    def __init__(self, parent=None):
        super(PresentationDialog, self).__init__(parent)
        self.setWindowTitle('Presentation')
        self.slides = []  # list of QPixmap

        self.list = QListWidget()
        # Live preview canvas
        self.preview = QgsMapCanvas()
        self.preview.setCanvasColor(QtCompat.white)
        self.preview_bridge = QgsLayerTreeMapCanvasBridge(QgsProject.instance().layerTreeRoot(), self.preview)
        self.preview_bridge.setCanvasLayers()
        self.preview.setExtent(iface.mapCanvas().extent())


        btn_capture = QPushButton('Capture Slide')
        btn_remove = QPushButton('Remove Slide')
        btn_show = QPushButton('Start Presentation')
        btn_export = QPushButton('Export to PDF')
        btn_live = QPushButton('Present Live')

        btn_capture.clicked.connect(self.capture_slide)
        btn_remove.clicked.connect(self.remove_selected)
        btn_show.clicked.connect(self.start_presentation)
        btn_export.clicked.connect(self.export_pdf)
        btn_live.clicked.connect(self.present_live)

        # Layer panel (shows layer tree with visibility controls)
        self.layer_view = QgsLayerTreeView()
        
        # Configure Drag & Drop, Reordering and Selection
        self.layer_view.setDragEnabled(True)
        self.layer_view.setAcceptDrops(True)
        self.layer_view.setDropIndicatorShown(True)
        self.layer_view.setSelectionMode(QtCompat.ExtendedSelection)

        # Prefer the project's existing layer tree model from the main layer panel
        model = None
        try:
            model = iface.layerTreeView().layerTreeModel()
        except Exception:  # nosec B110
            pass
        if model is None:
            try:
                from qgis.gui import QgsLayerTreeModel
                model = QgsLayerTreeModel(QgsProject.instance().layerTreeRoot())
            except Exception:
                model = None
        if model is not None:
            self.layer_view.setModel(model)
            try:
                self.layer_view.setRootIndex(iface.layerTreeView().rootIndex())
                self.layer_view.setSelectionModel(iface.layerTreeView().selectionModel())
            except Exception:  # nosec B110
                pass
            self.layer_view.expandAll()

        # Set up menu provider
        self.menu_provider = PresenterMenuProvider(self.layer_view, self.preview)
        self.layer_view.setMenuProvider(self.menu_provider)

        # Connect double-click to show layer properties
        self.layer_view.doubleClicked.connect(self.on_layer_double_clicked)

        # Create a toolbar for the layers tree view
        layer_toolbar = QToolBar()
        layer_toolbar.setIconSize(QSize(16, 16))
        actions = QgsLayerTreeViewDefaultActions(self.layer_view)
        layer_toolbar.addAction(actions.actionAddGroup())
        
        act_expand = QAction("Expand All", self)
        act_expand.triggered.connect(self.layer_view.expandAll)
        layer_toolbar.addAction(act_expand)
        
        act_collapse = QAction("Collapse All", self)
        act_collapse.triggered.connect(self.layer_view.collapseAll)
        layer_toolbar.addAction(act_collapse)
        
        layer_toolbar.addAction(actions.actionRemoveGroupOrLayer())

        # Compose left column: layer panel above slide list
        left = QVBoxLayout()
        left.addWidget(QLabel('Layers'))
        left.addWidget(layer_toolbar)
        left.addWidget(self.layer_view, 3)
        left.addWidget(self.list, 2)
        left.addWidget(btn_capture)
        left.addWidget(btn_remove)

        right = QVBoxLayout()
        right.addWidget(self.preview, 4)
        right.addWidget(btn_show)
        right.addWidget(btn_live)
        right.addWidget(btn_export)

        main = QHBoxLayout()
        main.addLayout(left, 1)
        main.addLayout(right, 2)

        self.setLayout(main)

        self.list.currentRowChanged.connect(self.show_preview)

    def capture_slide(self):
        """Capture current map view as a dynamic slide (store extent/scale)."""
        canvas = iface.mapCanvas()
        if not canvas:
            return
        extent = QgsRectangle(canvas.extent())
        scale = canvas.scale()
        slide = {'extent': extent, 'scale': scale}
        self.slides.append(slide)
        self.list.addItem(f'Slide {len(self.slides)}')
        self.list.setCurrentRow(len(self.slides) - 1)

    def on_layer_double_clicked(self, index):
        node = self.layer_view.model().index2node(index)
        from qgis.core import QgsLayerTreeLayer
        if isinstance(node, QgsLayerTreeLayer):
            layer = node.layer()
            if layer:
                iface.showLayerProperties(layer)


    def present_live(self):
        """Start presenter showing the current live canvas extent immediately."""
        canvas = iface.mapCanvas()
        if not canvas:
            return
        extent = QgsRectangle(canvas.extent())
        scale = canvas.scale()
        slide = {'extent': extent, 'scale': scale}
        try:
            w = FullscreenPresenter([slide])
            w.show()
            w.raise_()
            w.activateWindow()
        except Exception as e:
            from qgis.PyQt.QtWidgets import QMessageBox
            import traceback
            tb = traceback.format_exc()
            QMessageBox.critical(self, 'Presentation Error', f'Failed to start presenter:\n{e}\n\nSee Python Console for details')
            print(tb)

    def show_preview(self, idx):
        if idx < 0 or idx >= len(self.slides):
            return
        slide = self.slides[idx]
        if isinstance(self.preview, QgsMapCanvas):
            self.preview.setExtent(slide['extent'])
            self.preview.refresh()

    def remove_selected(self):
        idx = self.list.currentRow()
        if idx < 0:
            return
        del self.slides[idx]
        self.list.takeItem(idx)

    def start_presentation(self):
        if not self.slides:
            # auto-capture current view if no slides
            canvas = iface.mapCanvas()
            if canvas:
                extent = QgsRectangle(canvas.extent())
                scale = canvas.scale()
                self.slides.append({'extent': extent, 'scale': scale})
        try:
            w = FullscreenPresenter(self.slides)
            w.show()
            w.raise_()
            w.activateWindow()
        except Exception as e:
            from qgis.PyQt.QtWidgets import QMessageBox
            import traceback
            tb = traceback.format_exc()
            QMessageBox.critical(self, 'Presentation Error', f'Failed to start presenter:\n{e}\n\nSee Python Console for details')
            print(tb)

    def export_pdf(self):
        if not self.slides:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export Presentation', '', 'PDF Files (*.pdf)')
        if not path:
            return
        printer = QPrinter(QtCompat.PrinterResolution)
        printer.setOutputFormat(QtCompat.PdfFormat)
        printer.setOutputFileName(path)

        painter = None
        try:
            from qgis.PyQt.QtGui import QPainter
            painter = QPainter()
            painter.begin(printer)
            for i, slide in enumerate(self.slides):
                # render the preview canvas at the slide extent and grab image
                if isinstance(self.preview, QgsMapCanvas):
                    self.preview.setExtent(slide['extent'])
                    self.preview.refresh()
                    pix = self.preview.grab()
                    img = pix.toImage()
                    rect = painter.viewport()
                    img = img.scaled(rect.size(), QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)
                    painter.drawImage(0, 0, img)
                if i != len(self.slides) - 1:
                    printer.newPage()
            painter.end()
        except Exception:
            if painter and painter.isActive():
                painter.end()


class FullscreenPresenter(QMainWindow):
    """Window that shows slides fullscreen and allows keyboard navigation."""

    def __init__(self, slides, parent=None):
        super(FullscreenPresenter, self).__init__(None)
        self.overlay = None
        self.toolbar_widget = None
        self.slides = slides
        self.index = 0
        self.rubberbands = []
        self.setWindowFlags(QtCompat.FramelessWindowHint | QtCompat.stay_on_top() | QtCompat.CustomizeWindowHint)
        self.setWindowState(QtCompat.WindowFullScreen)
        self.setAttribute(QtCompat.WA_DeleteOnClose, True)

        # Live canvas used for presentation (interactive)
        self.canvas = QgsMapCanvas()
        self.canvas.setCanvasColor(QtCompat.white)
        self.canvas.setExtent(self.slides[self.index]['extent'])
        self.canvas.setFocus()

        # Connect the canvas to the project layer tree so symbology and visibility stay live.
        self.bridge = QgsLayerTreeMapCanvasBridge(QgsProject.instance().layerTreeRoot(), self.canvas)
        self.bridge.setCanvasLayers()

        # Feature detail panel
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMinimumWidth(240)

        # Layer panel for fullscreen presentation
        self.layer_view = QgsLayerTreeView()
        
        # Configure Drag & Drop, Reordering and Selection
        self.layer_view.setDragEnabled(True)
        self.layer_view.setAcceptDrops(True)
        self.layer_view.setDropIndicatorShown(True)
        self.layer_view.setSelectionMode(QtCompat.ExtendedSelection)

        model = None
        try:
            model = iface.layerTreeView().layerTreeModel()
        except Exception:  # nosec B110
            pass
        if model is None:
            try:
                from qgis.gui import QgsLayerTreeModel
                model = QgsLayerTreeModel(QgsProject.instance().layerTreeRoot())
            except Exception:
                model = None
        if model is not None:
            self.layer_view.setModel(model)
            try:
                self.layer_view.setRootIndex(iface.layerTreeView().rootIndex())
                self.layer_view.setSelectionModel(iface.layerTreeView().selectionModel())
            except Exception:  # nosec B110
                pass
            self.layer_view.expandAll()

        # Set up menu provider
        self.menu_provider = PresenterMenuProvider(self.layer_view, self.canvas)
        self.layer_view.setMenuProvider(self.menu_provider)

        # Connect double-click to show layer properties
        self.layer_view.doubleClicked.connect(self.on_layer_double_clicked)

        # Create a toolbar for the layers tree view in fullscreen
        layer_toolbar = QToolBar()
        layer_toolbar.setIconSize(QSize(16, 16))
        actions = QgsLayerTreeViewDefaultActions(self.layer_view)
        layer_toolbar.addAction(actions.actionAddGroup())
        
        act_expand = QAction("Expand All", self)
        act_expand.triggered.connect(self.layer_view.expandAll)
        layer_toolbar.addAction(act_expand)
        
        act_collapse = QAction("Collapse All", self)
        act_collapse.triggered.connect(self.layer_view.collapseAll)
        layer_toolbar.addAction(act_collapse)
        
        layer_toolbar.addAction(actions.actionRemoveGroupOrLayer())

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self.canvas)
        self.setCentralWidget(container)

        self.overlay = DraggableOverlay(self)
        self.overlay.setObjectName('presentationOverlay')
        self.overlay.setStyleSheet(
            '#presentationOverlay { background: rgba(40,40,40,220); color: white; border-radius: 10px; }'
        )
        self.overlay.setAttribute(QtCompat.WA_TranslucentBackground, True)
        self.overlay.setWindowFlags(QtCompat.Tool | QtCompat.FramelessWindowHint)

        self.overlay_layout = QVBoxLayout()
        self.overlay_layout.setContentsMargins(10, 10, 10, 10)
        self.overlay.setLayout(self.overlay_layout)

        self.overlay_layout.addWidget(QLabel('Presenter Controls'))
        self.overlay_layout.addWidget(QLabel('Layers'))
        self.overlay_layout.addWidget(layer_toolbar)
        self.overlay_layout.addWidget(self.layer_view, 3)
        self.overlay_layout.addWidget(QLabel('Feature Details'))
        self.overlay_layout.addWidget(self.detail, 2)

        btn_hide_overlay = QPushButton('Hide Controls')
        btn_hide_overlay.clicked.connect(self.overlay.hide)
        self.overlay_layout.addWidget(btn_hide_overlay)

        btn_exit = QPushButton('Exit Presentation')
        btn_exit.clicked.connect(self.close)
        self.overlay_layout.addWidget(btn_exit)

        self.overlay.show()

        self._create_tools()
        self.update_slide()

    def _create_tools(self):
        class PointerTool(QgsMapTool):
            def __init__(self, canvas, parent):
                super().__init__(canvas)
                self.canvas = canvas
                self.parent = parent
                self.marker = QgsVertexMarker(canvas)
                self.marker.setColor(QtCompat.red)
                self.marker.setIconSize(10)
                self.marker.setIconType(QgsVertexMarker.IconType.ICON_CROSS)
                self.marker.setPenWidth(2)
                self.marker.hide()

            def canvasMoveEvent(self, event):
                pt = self.toMapCoordinates(event.pos())
                self.marker.setCenter(pt)
                self.marker.show()

            def canvasPressEvent(self, event):
                pass

            def deactivate(self):
                self.marker.hide()

        class DrawTool(QgsMapTool):
            def __init__(self, canvas, parent):
                super().__init__(canvas)
                self.canvas = canvas
                self.parent = parent
                self.rb = None

            def canvasPressEvent(self, event):
                self.rb = QgsRubberBand(self.canvas, False)
                self.rb.setColor(QtCompat.cyan)
                self.rb.setWidth(2)
                self.rb.addPoint(self.toMapCoordinates(event.pos()))

            def canvasMoveEvent(self, event):
                if self.rb:
                    self.rb.addPoint(self.toMapCoordinates(event.pos()))

            def canvasReleaseEvent(self, event):
                if self.rb:
                    self.parent.rubberbands.append(self.rb)
                    self.rb = None

        class IdentifyTool(QgsMapToolEmitPoint):
            def __init__(self, canvas, parent):
                super().__init__(canvas)
                self.canvas = canvas
                self.parent = parent

            def canvasReleaseEvent(self, event):
                pt = self.toMapCoordinates(event.pos())
                tol_px = 5
                tol_map = tol_px * self.canvas.mapUnitsPerPixel()
                rect = QgsRectangle(pt.x() - tol_map, pt.y() - tol_map,
                                    pt.x() + tol_map, pt.y() + tol_map)
                for layer in QgsProject.instance().mapLayers().values():
                    if layer.type() != QgsMapLayer.LayerType.VectorLayer:
                        continue
                    try:
                        req = QgsFeatureRequest().setFilterRect(rect)
                        for f in layer.getFeatures(req):
                            attrs = {field.name(): f[field.name()] for field in layer.fields()}
                            self.parent.detail.setPlainText(
                                f'Layer: {layer.name()}\n' + '\n'.join(f'{k}: {v}' for k, v in attrs.items())
                            )
                            return
                    except Exception:  # nosec B110
                        pass

        self.pointer_tool = PointerTool(self.canvas, self)
        self.draw_tool = DrawTool(self.canvas, self)
        self.identify_tool = IdentifyTool(self.canvas, self)

        self.default_tool = self.canvas.mapTool()

        from qgis.PyQt.QtWidgets import QToolBar
        tb = QToolBar(self)
        tb.setWindowFlags(QtCompat.Tool | QtCompat.FramelessWindowHint)
        tb.setStyleSheet('background: rgba(60,60,60,220); color: white;')
        btn_pointer = tb.addAction('Pointer')
        btn_draw = tb.addAction('Draw')
        btn_identify = tb.addAction('Identify')
        btn_undo = tb.addAction('Undo')
        btn_clear = tb.addAction('Clear')
        btn_controls = tb.addAction('Controls')
        btn_exit = tb.addAction('Exit')

        def set_pointer():
            self.canvas.setMapTool(self.pointer_tool)

        def set_draw():
            self.canvas.setMapTool(self.draw_tool)

        def set_identify():
            self.canvas.setMapTool(self.identify_tool)

        def undo_ann():
            if self.rubberbands:
                rb = self.rubberbands.pop()
                rb.reset(True)
                self.canvas.refresh()

        def clear_ann():
            while self.rubberbands:
                rb = self.rubberbands.pop()
                rb.reset(True)
            self.canvas.refresh()

        def show_controls():
            self.overlay.show()

        def exit_presentation():
            self.close()

        btn_pointer.triggered.connect(set_pointer)
        btn_draw.triggered.connect(set_draw)
        btn_identify.triggered.connect(set_identify)
        btn_undo.triggered.connect(undo_ann)
        btn_clear.triggered.connect(clear_ann)
        btn_controls.triggered.connect(show_controls)
        btn_exit.triggered.connect(exit_presentation)

        self.toolbar_widget = tb
        self.toolbar_widget.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        h = self.height()
        ow = min(380, int(w * 0.28))
        oh = min(620, int(h * 0.8))
        if getattr(self, 'overlay', None) is not None:
            if not hasattr(self, '_overlay_initialized'):
                self.overlay.setGeometry(16, 16, ow, oh)
                self._overlay_initialized = True
            else:
                self.overlay.resize(ow, oh)
        if getattr(self, 'toolbar_widget', None) is not None:
            self.toolbar_widget.setGeometry((w - 360) // 2, 12, 360, 38)

    def update_slide(self):
        slide = self.slides[self.index]
        if isinstance(self.canvas, QgsMapCanvas):
            self.canvas.setExtent(slide['extent'])
            self.canvas.refresh()

    def on_layer_double_clicked(self, index):
        node = self.layer_view.model().index2node(index)
        from qgis.core import QgsLayerTreeLayer
        if isinstance(node, QgsLayerTreeLayer):
            layer = node.layer()
            if layer:
                iface.showLayerProperties(layer)


    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, 'bridge'):
            try:
                self.bridge.setCanvasLayers()
            except Exception:  # nosec B110
                pass
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        if self.toolbar_widget is not None:
            self.toolbar_widget.show()
            self.toolbar_widget.raise_()
        if self.overlay is not None:
            self.overlay.show()
            self.overlay.raise_()

    def keyPressEvent(self, event):
        if event.key() in (QtCompat.get_key("Key_Right"), QtCompat.get_key("Key_Space")):
            self.index = min(self.index + 1, len(self.slides) - 1)
            self.update_slide()
        elif event.key() == QtCompat.get_key("Key_Left"):
            self.index = max(self.index - 1, 0)
            self.update_slide()
        elif event.key() in (QtCompat.Key_Escape, QtCompat.get_key("Key_Q")):
            self.close()
        elif event.key() == QtCompat.get_key("Key_L"):
            if self.overlay.isVisible():
                self.overlay.hide()
            else:
                self.overlay.show()

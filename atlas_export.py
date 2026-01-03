# -*- coding: utf-8 -*-
"""
Enhanced Atlas Export Tool
~~~~~~~~~~~~~~~~~~~~~~~~~~
A full-featured dialog for exporting QGIS print-layouts / atlas pages
with live preview, progress feedback and a lot of export options.

Author:  Your Name
"""

# ----------------------------------------------------------------------
# Imports
# ----------------------------------------------------------------------
import os
import re
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass
from enum import Enum

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton,
    QLabel, QLineEdit, QSpinBox, QComboBox, QCheckBox, QProgressBar,
    QGroupBox, QRadioButton, QButtonGroup, QFileDialog, QMessageBox,
    QTextEdit, QSplitter, QFrame, QSlider, QScrollArea, QWidget,
    QToolBar, QAction, QGraphicsItem, QGraphicsView, QGraphicsScene
)
from qgis.PyQt.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, QSize, QPointF, QRectF
)
from qgis.PyQt.QtGui import (
    QFont, QPalette, QPixmap, QIcon, QPainter, QImage,
    QCursor
)

from qgis.core import (
    QgsProject,  QgsPrintLayout, QgsLayoutExporter,

    Qgis,
    QgsFeatureRequest,
    QgsWkbTypes
)
from qgis.gui import QgsMessageBar
from qgis.utils import iface

from .qt_compat import QtCompat
# Qt5/Qt6 compatibility for enums
try:
    # Qt6 style
    ScrollBarAlwaysOff = Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    KeepAspectRatio = Qt.AspectRatioMode.KeepAspectRatio
    SmoothTransformation = Qt.TransformationMode.SmoothTransformation
    ScrollHandDrag = QGraphicsView.DragMode.ScrollHandDrag
    AnchorUnderMouse = QGraphicsView.ViewportAnchor.AnchorUnderMouse
    AnchorViewCenter = QGraphicsView.ViewportAnchor.AnchorViewCenter
    ControlModifier = Qt.KeyboardModifier.ControlModifier
    ItemIsMovable = QGraphicsItem.GraphicsItemFlag.ItemIsMovable
    Antialiasing = QPainter.RenderHint.Antialiasing
    SmoothPixmapTransform = QPainter.RenderHint.SmoothPixmapTransform
    WhiteColor = Qt.GlobalColor.white
    PointingHandCursor = Qt.CursorShape.PointingHandCursor
    AlignCenter = Qt.AlignmentFlag.AlignCenter
except AttributeError:
    # Qt5 style
    ScrollBarAlwaysOff = Qt.ScrollBarAlwaysOff
    KeepAspectRatio = Qt.KeepAspectRatio
    SmoothTransformation = Qt.SmoothTransformation
    ScrollHandDrag = QGraphicsView.ScrollHandDrag
    AnchorUnderMouse = QGraphicsView.AnchorUnderMouse
    AnchorViewCenter = QGraphicsView.AnchorViewCenter
    ControlModifier = Qt.ControlModifier
    ItemIsMovable = QGraphicsItem.ItemIsMovable
    Antialiasing = QPainter.Antialiasing
    SmoothPixmapTransform = QPainter.SmoothPixmapTransform
    WhiteColor = Qt.white
    PointingHandCursor = Qt.PointingHandCursor
    AlignCenter = Qt.AlignCenter
# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------


class PreviewConfig:
    MAX_PREVIEW_FIELDS = 8
    MAX_FIELD_VALUE_LENGTH = 50
    PREVIEW_WIDTH = 3600
    PREVIEW_HEIGHT = 2700
    MAX_FILENAME_LENGTH = 255


class ExportFormat(Enum):
    PDF = "pdf"
    PNG = "png"
    JPG = "jpg"
    TIFF = "tiff"
    SVG = "svg"


class ExportMode(Enum):
    ALL = "all"
    CUSTOM = "custom"
    SINGLE = "single"


@dataclass
class ExportSettings:
    """Configuration for atlas export"""
    output_dir: str
    filename_pattern: str
    export_format: ExportFormat
    export_mode: ExportMode
    custom_pages: Optional[List[int]] = None
    dpi: int = 300
    quality: int = 95
    width: Optional[int] = None
    height: Optional[int] = None
    include_metadata: bool = True
    create_subdirs: bool = False
    is_atlas_layout: bool = True
    export_as_single_pdf: bool = False

    # Advanced options
    force_vector: bool = False
    rasterize_whole: bool = False
    text_render: str = "Always outlines"
    pdf_image_compression: str = "Lossy (JPEG)"
    pdf_jpeg_quality: int = 90
    png_tiff_compression: int = 6


# ----------------------------------------------------------------------
# Simple preview generator (synchronous, safe)
# ----------------------------------------------------------------------
class SimplePreviewGenerator:
    @staticmethod
    def generate_preview_info(layout: QgsPrintLayout, page_index: int = 0,
                              is_atlas: bool = True) -> str:
        try:
            if not layout:
                return "No layout provided"

            if not is_atlas:
                return (f"Regular Layout: {layout.name()}\n"
                        f"Single page export\n"
                        f"No atlas configuration")

            atlas = layout.atlas()
            if not atlas:
                return "Atlas object not available"

            if not atlas.enabled():
                coverage = atlas.coverageLayer()
                if coverage and coverage.isValid():
                    cnt = SimplePreviewGenerator._get_safe_feature_count(
                        atlas, coverage)
                    return (f"Atlas configured but not enabled\n"
                            f"Coverage layer: {coverage.name()}\n"
                            f"Features: {cnt}")
                return "Atlas not enabled and no coverage layer configured"

            coverage = atlas.coverageLayer()
            if not coverage or not coverage.isValid():
                return "Atlas enabled but coverage layer is invalid"

            total = SimplePreviewGenerator._get_safe_feature_count(
                atlas, coverage)
            if total == 0:
                return (f"Atlas enabled but coverage layer '{coverage.name()}' "
                        f"has 0 features\n(check layer filters or data)")

            if page_index >= total:
                return f"Invalid page index: {page_index + 1} (maximum: {total})"

            feature = SimplePreviewGenerator._get_safe_feature_at_index(
                coverage, page_index)

            info = f"ATLAS PAGE {page_index + 1} of {total}\n"
            info += f"Layout: {layout.name()}\n"
            info += f"Coverage Layer: {coverage.name()}\n"

            # Geometry type
            try:
                geom_type = coverage.geometryType()
                info += f"Layer Type: {QgsWkbTypes.geometryDisplayString(geom_type)}\n"
            except Exception:
                info += "Layer Type: Unknown\n"

            # Feature attributes
            if feature and feature.isValid() and coverage.fields():
                info += f"\nFEATURE ATTRIBUTES (Page {page_index + 1}):\n"
                info += "-" * 40 + "\n"
                fields = coverage.fields()
                for i, fld in enumerate(fields):
                    if i >= PreviewConfig.MAX_PREVIEW_FIELDS:
                        info += f" ... and {len(fields) - PreviewConfig.MAX_PREVIEW_FIELDS} more fields\n"
                        break
                    try:
                        val = feature[fld.name()]
                        txt = str(val)
                        if len(txt) > PreviewConfig.MAX_FIELD_VALUE_LENGTH:
                            txt = txt[:PreviewConfig.MAX_FIELD_VALUE_LENGTH - 3] + "..."
                        info += f" {fld.name()}: {txt}\n"
                    except Exception:
                        info += f" {fld.name()}: <error reading value>\n"
            else:
                info += f"\nNo feature data available for page {page_index + 1}"
            return info

        except Exception as e:
            return f"Preview generation error: {str(e)}\nLayout: {layout.name() if layout else 'None'}"

    # ------------------------------------------------------------------
    @staticmethod
    def _get_safe_feature_count(atlas, coverage_layer) -> int:
        if not coverage_layer:
            return 0
        try:
            if atlas and atlas.enabled():
                cnt = atlas.count()
                if cnt > 0:
                    return cnt
        except Exception:
            pass
        try:
            if coverage_layer.isValid():
                cnt = coverage_layer.featureCount()
                if cnt >= 0:
                    return cnt
        except Exception:
            pass
        try:
            return len(list(coverage_layer.getFeatures()))
        except Exception:
            pass
        try:
            if coverage_layer.dataProvider():
                cnt = coverage_layer.dataProvider().featureCount()
                if cnt >= 0:
                    return cnt
        except Exception:
            pass
        return 0

    # ------------------------------------------------------------------
    @staticmethod
    def _get_safe_feature_at_index(coverage_layer, index: int):
        if not coverage_layer or not coverage_layer.isValid() or index < 0:
            return None
        try:
            feats = list(coverage_layer.getFeatures())
            if index < len(feats):
                return feats[index]
        except Exception:
            pass
        try:
            req = QgsFeatureRequest()
            feats = list(coverage_layer.getFeatures(req))
            if index < len(feats):
                return feats[index]
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    @staticmethod
    def generate_simple_preview_image(layout: QgsPrintLayout,
                                      page_index: int = 0,
                                      is_atlas: bool = True) -> QPixmap:
        try:
            exporter = QgsLayoutExporter(layout)
            size = QSize(PreviewConfig.PREVIEW_WIDTH,
                         PreviewConfig.PREVIEW_HEIGHT)
            img = QImage(size, QImage.Format.Format_ARGB32)
            img.fill(WhiteColor)

            if is_atlas:
                atlas = layout.atlas()
                if not atlas.enabled() or not atlas.coverageLayer():
                    pm = QPixmap(size)
                    pm.fill(WhiteColor)
                    p = QPainter(pm)
                    p.drawText(QRectF(0, 0, size.width(), size.height()),
                               AlignCenter,
                               "Atlas not configured")
                    p.end()
                    return pm

                if not atlas.beginRender():
                    raise RuntimeError("Could not begin atlas rendering")
                try:
                    if not atlas.seekTo(page_index):
                        raise RuntimeError(
                            f"Could not seek to page {page_index + 1}")
                    p = QPainter(img)
                    res = exporter.renderPage(p, 0)
                    p.end()
                    if res not in (None, QgsLayoutExporter.ExportResult.Success):
                        raise RuntimeError(f"Render error code {res}")
                finally:
                    atlas.endRender()
            else:
                p = QPainter(img)
                res = exporter.renderPage(p, 0)
                p.end()
                if res not in (None, QgsLayoutExporter.ExportResult.Success):
                    raise RuntimeError(f"Render error code {res}")

            return QPixmap.fromImage(img)

        except Exception as e:
            pm = QPixmap(PreviewConfig.PREVIEW_WIDTH,
                         PreviewConfig.PREVIEW_HEIGHT)
            pm.fill(WhiteColor)
            p = QPainter(pm)
            p.drawText(QRectF(0, 0, PreviewConfig.PREVIEW_WIDTH,
                              PreviewConfig.PREVIEW_HEIGHT),
                       AlignCenter,
                       f"Preview Error:\n{str(e)}")
            p.end()
            return pm


# ----------------------------------------------------------------------
# Standalone preview dialog – FULL QUALITY zoom & pan
# ----------------------------------------------------------------------
class StandalonePreviewDialog(QDialog):
    """Preview dialog with high-quality zoom & pan. Image stays sharp."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Standalone Layout Preview")
        self.resize(1000, 800)

        self.current_layout = None
        self.is_atlas_layout = False
        self.current_page = 0
        self.current_pixmap = None
        self._zoom_factor = 1.0
        self._pan_offset = QPointF(0, 0)

        self._setup_ui()

    # ------------------------------------------------------------------
    def _setup_ui(self):
        main = QVBoxLayout(self)

        # Toolbar
        tb = QToolBar()
        tb.setMovable(False)
        tb.addWidget(QLabel("Page:"))
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.valueChanged.connect(self.update_preview)
        tb.addWidget(self.page_spin)

        refresh = QAction("Refresh", self)
        refresh.triggered.connect(self.update_preview)
        tb.addAction(refresh)

        # Zoom controls
        tb.addSeparator()
        tb.addWidget(QLabel("Zoom:"))
        self.zoom_spin = QSpinBox()
        self.zoom_spin.setRange(10, 500)
        self.zoom_spin.setSuffix("%")
        self.zoom_spin.setValue(100)
        self.zoom_spin.valueChanged.connect(self._apply_zoom_from_spin)
        tb.addWidget(self.zoom_spin)

        fit_btn = QAction("Fit to Window", self)
        fit_btn.triggered.connect(self._fit_to_window)
        tb.addAction(fit_btn)

        main.addWidget(tb)

        # Graphics view
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHints(Antialiasing | SmoothPixmapTransform)
        self.view.setDragMode(ScrollHandDrag)
        self.view.setTransformationAnchor(AnchorUnderMouse)
        self.view.setResizeAnchor(AnchorViewCenter)
        self.view.setHorizontalScrollBarPolicy(ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(ScrollBarAlwaysOff)
        self.view.setBackgroundBrush(WhiteColor)

        # Mouse wheel zoom
        self.view.wheelEvent = self._wheel_event

        main.addWidget(self.view, 1)

        self.status_lbl = QLabel("Ready")
        main.addWidget(self.status_lbl)

    # ------------------------------------------------------------------
    def set_layout(self, layout, is_atlas_layout=False, page=0):
        self.current_layout = layout
        self.is_atlas_layout = is_atlas_layout
        self.current_page = page

        if is_atlas_layout:
            atlas = layout.atlas()
            if atlas and atlas.enabled():
                self.page_spin.setMaximum(atlas.count())
            else:
                self.page_spin.setMaximum(1)
        else:
            self.page_spin.setMaximum(1)

        self.page_spin.setValue(page + 1)
        self.update_preview()

    # ------------------------------------------------------------------
    def update_preview(self):
        if not self.current_layout:
            return

        page_idx = self.page_spin.value() - 1
        self.current_page = page_idx

        pix = SimplePreviewGenerator.generate_simple_preview_image(
            self.current_layout, page_idx, self.is_atlas_layout)

        if pix.isNull():
            self.status_lbl.setText("Failed to generate preview")
            return

        self.current_pixmap = pix
        self.scene.clear()

        # Add pixmap item with high-quality scaling
        self._pixmap_item = self.scene.addPixmap(pix)
        self._pixmap_item.setTransformationMode(SmoothTransformation)
        self._pixmap_item.setFlag(ItemIsMovable, False)

        self._fit_to_window()
        self.status_lbl.setText(f"Page {page_idx + 1} – Zoom: 100%")

    # ------------------------------------------------------------------
    def _fit_to_window(self):
        """Fit image to view while preserving quality."""
        if not self.current_pixmap:
            return

        self.view.resetTransform()
        self.view.fitInView(self.scene.sceneRect(), KeepAspectRatio)

        # Extract effective zoom from view transform
        self._zoom_factor = self.view.transform().m11()
        self.zoom_spin.blockSignals(True)
        self.zoom_spin.setValue(int(self._zoom_factor * 100))
        self.zoom_spin.blockSignals(False)

        self.status_lbl.setText(
            f"Page {self.current_page + 1} – Zoom: {int(self._zoom_factor*100)}%")

    # ------------------------------------------------------------------
    def _apply_zoom_from_spin(self, percent: int):
        """Apply zoom from spinbox."""
        if not self.current_pixmap:
            return

        factor = percent / 100.0
        self.view.resetTransform()
        self.view.scale(factor, factor)
        self._zoom_factor = factor
        self.status_lbl.setText(
            f"Page {self.current_page + 1} – Zoom: {percent}%")

    # ------------------------------------------------------------------
    def _wheel_event(self, event):
        """Ctrl + wheel = zoom, else pan."""
        if event.modifiers() & ControlModifier:
            delta = event.angleDelta().y()
            zoom_in = delta > 0
            factor = 1.25 if zoom_in else 0.8
            new_zoom = self._zoom_factor * factor
            new_zoom = max(0.1, min(5.0, new_zoom))

            self.view.scale(factor, factor)
            self._zoom_factor = new_zoom

            self.zoom_spin.blockSignals(True)
            self.zoom_spin.setValue(int(new_zoom * 100))
            self.zoom_spin.blockSignals(False)

            self.status_lbl.setText(
                f"Page {self.current_page + 1} – Zoom: {int(new_zoom*100)}%")
        else:
            super(QGraphicsView, self.view).wheelEvent(event)


# ----------------------------------------------------------------------
# Export worker (runs in a separate thread)
# ----------------------------------------------------------------------


class AtlasExportWorker(QThread):
    progress_updated = pyqtSignal(int, str)
    export_finished = pyqtSignal(bool, str)
    page_exported = pyqtSignal(int, str)

    def __init__(self, layout: QgsPrintLayout, settings: ExportSettings):
        super().__init__()
        self.layout = layout
        self.settings = settings
        self.cancelled = False

    # ------------------------------------------------------------------
    def run(self):
        try:
            if not self.settings.is_atlas_layout:
                self._export_single_layout()
                return

            atlas = self.layout.atlas()
            if not atlas.enabled():
                self.export_finished.emit(False,
                                          "Atlas is not enabled in the layout")
                return

            export_cfg = self._create_export_settings()

            # Single-PDF shortcut
            if (self.settings.export_format == ExportFormat.PDF and
                    self.settings.export_as_single_pdf):
                self._export_atlas_as_single_pdf(atlas,
                                                 QgsLayoutExporter(
                                                     self.layout),
                                                 export_cfg)
                return

            pages = self._get_pages_to_export(atlas)
            total = len(pages)
            if total == 0:
                self.export_finished.emit(False, "No pages to export")
                return

            os.makedirs(self.settings.output_dir, exist_ok=True)
            exported = []
            exporter = QgsLayoutExporter(self.layout)

            if not atlas.beginRender():
                self.export_finished.emit(False,
                                          "Failed to begin atlas rendering")
                return

            try:
                for i, pg_idx in enumerate(pages):
                    if self.cancelled:
                        break

                    if not atlas.seekTo(pg_idx):
                        self.export_finished.emit(
                            False,
                            f"Failed to seek to page {pg_idx + 1}")
                        return

                    filename = self._generate_filename(pg_idx, atlas)
                    filepath = os.path.join(self.settings.output_dir, filename)

                    res = self._export_page(exporter, filepath, export_cfg)
                    if res == QgsLayoutExporter.ExportResult.Success:
                        exported.append(filepath)
                        self.page_exported.emit(pg_idx + 1, filename)
                    else:
                        self.export_finished.emit(
                            False,
                            f"Failed to export page {pg_idx + 1}: "
                            f"{self._get_export_error(res)}")
                        return

                    prog = int((i + 1) * 100 / total)
                    self.progress_updated.emit(
                        prog, f"Exported {i + 1}/{total} pages")
            finally:
                atlas.endRender()

            if not self.cancelled:
                self.export_finished.emit(
                    True,
                    f"Successfully exported {len(exported)} pages")
            else:
                self.export_finished.emit(
                    False,
                    f"Export cancelled. {len(exported)} pages were exported.")
        except Exception as e:
            self.export_finished.emit(False, f"Export failed: {str(e)}")

    # ------------------------------------------------------------------
    def cancel(self):
        self.cancelled = True

    # ------------------------------------------------------------------
    def _export_single_layout(self):
        try:
            os.makedirs(self.settings.output_dir, exist_ok=True)
            cfg = self._create_export_settings()
            exporter = QgsLayoutExporter(self.layout)

            filename = self.settings.filename_pattern
            filename = filename.replace("{page}", "001")
            filename = filename.replace("{index}", "0")
            filename += f".{self.settings.export_format.value}"
            filepath = os.path.join(self.settings.output_dir, filename)

            self.progress_updated.emit(50, "Exporting layout...")
            res = self._export_page(exporter, filepath, cfg)

            if res == QgsLayoutExporter.ExportResult.Success:
                self.progress_updated.emit(100, "Export complete")
                self.export_finished.emit(True,
                                          f"Successfully exported layout to {filename}")
            else:
                self.export_finished.emit(
                    False,
                    f"Failed to export layout: {self._get_export_error(res)}")
        except Exception as e:
            self.export_finished.emit(
                False, f"Single layout export failed: {str(e)}")

    # ------------------------------------------------------------------
    def _export_atlas_as_single_pdf(self, atlas, exporter, export_cfg):
        try:
            filename = self.settings.filename_pattern
            if not filename.lower().endswith('.pdf'):
                filename += '.pdf'
            filepath = os.path.join(self.settings.output_dir, filename)
            os.makedirs(self.settings.output_dir, exist_ok=True)

            self.progress_updated.emit(10, "Starting single PDF export...")
            res = exporter.exportToPdf(atlas, filepath, export_cfg)

            if res == QgsLayoutExporter.ExportResult.Success:
                self.progress_updated.emit(100, "Export complete")
                self.export_finished.emit(
                    True,
                    f"Successfully exported atlas to single PDF: {filename}")
            else:
                self.export_finished.emit(
                    False,
                    f"Failed to export atlas PDF: {self._get_export_error(res)}")
        except Exception as e:
            self.export_finished.emit(
                False, f"Single PDF export failed: {str(e)}")

    # ------------------------------------------------------------------
    def _create_export_settings(self):
        fmt = self.settings.export_format
        if fmt == ExportFormat.PDF:
            s = QgsLayoutExporter.PdfExportSettings()
            s.forceVectorOutput = (self.settings.force_vector and
                                   not self.settings.rasterize_whole)
            s.rasterizeWholeImage = self.settings.rasterize_whole

            tr = (self.settings.text_render or "Always outlines").lower()
            if "prefer" in tr:
                s.textRenderFormat = Qgis.TextRenderFormat.PreferText
            elif "always text" in tr:
                s.textRenderFormat = Qgis.TextRenderFormat.AlwaysText
            else:
                s.textRenderFormat = Qgis.TextRenderFormat.AlwaysOutlines

            comp = (self.settings.pdf_image_compression or "Lossy (JPEG)").lower()
            if hasattr(s, "imageCompression"):
                try:
                    ImgComp = getattr(QgsLayoutExporter.PdfExportSettings,
                                      "ImageCompression")
                    if "lossy" in comp or "jpeg" in comp:
                        s.imageCompression = ImgComp.Jpeg
                        if hasattr(s, "jpegQuality"):
                            s.jpegQuality = self.settings.pdf_jpeg_quality
                    else:
                        s.imageCompression = ImgComp.Lossless
                except Exception:
                    s.imageCompression = 1 if (
                        "lossy" in comp or "jpeg" in comp) else 0
                    if hasattr(s, "jpegQuality"):
                        s.jpegQuality = self.settings.pdf_jpeg_quality
            else:
                if hasattr(s, "jpegQuality") and ("lossy" in comp or "jpeg" in comp):
                    s.jpegQuality = self.settings.pdf_jpeg_quality
            return s

        elif fmt in (ExportFormat.PNG, ExportFormat.JPG, ExportFormat.TIFF):
            s = QgsLayoutExporter.ImageExportSettings()
            s.dpi = self.settings.dpi
            if self.settings.width and self.settings.height:
                s.imageSize = QSize(self.settings.width, self.settings.height)
            if hasattr(s, "quality"):
                s.quality = self.settings.quality
            if hasattr(s, "compressionLevel"):
                s.compressionLevel = self.settings.png_tiff_compression
            return s

        else:  # SVG
            s = QgsLayoutExporter.SvgExportSettings()
            tr = (self.settings.text_render or "Always outlines").lower()
            if hasattr(s, "textRenderFormat"):
                if "prefer" in tr:
                    s.textRenderFormat = Qgis.TextRenderFormat.PreferText
                elif "always text" in tr:
                    s.textRenderFormat = Qgis.TextRenderFormat.AlwaysText
                else:
                    s.textRenderFormat = Qgis.TextRenderFormat.AlwaysOutlines
            if hasattr(s, "rasterizeWholeImage"):
                s.rasterizeWholeImage = self.settings.rasterize_whole
            return s

    # ------------------------------------------------------------------
    def _get_pages_to_export(self, atlas) -> List[int]:
        total = atlas.count()
        if total <= 0:
            return []
        if self.settings.export_mode == ExportMode.ALL:
            return list(range(total))
        if self.settings.export_mode == ExportMode.CUSTOM:
            out = []
            for p in (self.settings.custom_pages or []):
                i = p - 1
                if 0 <= i < total:
                    out.append(i)
            return out
        return []

    # ------------------------------------------------------------------
    def _sanitize_filename_value(self, value: str) -> str:
        value = re.sub(r'[<>:"/\\|?*]', '_', value)
        value = ''.join(c for c in value if ord(c) >= 32)
        value = ''.join(c for c in value if c.isalnum() or c in '._- ')
        value = value[:100]
        value = value.strip('. ')
        return value or 'unnamed'

    # ------------------------------------------------------------------
    def _generate_filename(self, page_index: int, atlas=None) -> str:
        fn = self.settings.filename_pattern
        fn = fn.replace("{page}", str(page_index + 1).zfill(3))
        fn = fn.replace("{index}", str(page_index))

        if atlas and self.settings.is_atlas_layout:
            cov = atlas.coverageLayer()
            if cov:
                feat = atlas.feature()
                if feat and feat.isValid():
                    for fld in cov.fields():
                        ph = "{" + fld.name() + "}"
                        if ph in fn:
                            try:
                                val = str(feat[fld.name()])
                                val = self._sanitize_filename_value(val)
                                fn = fn.replace(ph, val)
                            except Exception:
                                fn = fn.replace(ph, "error")
        fn += f".{self.settings.export_format.value}"

        if len(fn) > PreviewConfig.MAX_FILENAME_LENGTH:
            name = fn[:PreviewConfig.MAX_FILENAME_LENGTH - 10]
            ext = f".{self.settings.export_format.value}"
            fn = name + ext
        return fn

    # ------------------------------------------------------------------
    def _export_page(self, exporter, filepath, export_cfg):
        fmt = self.settings.export_format
        if fmt == ExportFormat.PDF:
            return exporter.exportToPdf(filepath, export_cfg)
        if fmt in (ExportFormat.PNG, ExportFormat.JPG, ExportFormat.TIFF):
            return exporter.exportToImage(filepath, export_cfg)
        if fmt == ExportFormat.SVG:
            return exporter.exportToSvg(filepath, export_cfg)

    # ------------------------------------------------------------------
    def _get_export_error(self, code):
        msgs = {
            QgsLayoutExporter.ExportResult.Success: "Success",
            QgsLayoutExporter.ExportResult.Canceled: "Export was canceled",
            QgsLayoutExporter.ExportResult.MemoryError: "Not enough memory",
            QgsLayoutExporter.ExportResult.FileError: "Could not write to file",
            QgsLayoutExporter.ExportResult.PrintError: "Print error",
            QgsLayoutExporter.ExportResult.SvgLayerError: "SVG layer error",
            QgsLayoutExporter.ExportResult.IteratorError: "Iterator error"
        }
        return msgs.get(code, f"Unknown error (code: {code})")


# ----------------------------------------------------------------------
# Main dialog
# ----------------------------------------------------------------------
class EnhancedAtlasExportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_layout = None
        self.export_worker = None
        self.is_atlas_layout = False
        self.standalone_preview = None

        self.setWindowTitle("Enhanced Atlas Export Tool")
        self.setMinimumSize(800, 600)
        self.resize(900, 700)

        self._setup_ui()
        self.load_layouts()

    # ------------------------------------------------------------------
    def _setup_ui(self):
        main = QVBoxLayout(self)
        main.setSpacing(8)
        main.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main.addWidget(splitter)

        # ----- LEFT PANEL (settings) -----
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(400)
        left_panel = self._create_settings_panel()
        left_scroll.setWidget(left_panel)
        splitter.addWidget(left_scroll)

        # ----- RIGHT PANEL (preview + log) -----
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setMinimumWidth(300)
        right_panel = self._create_preview_panel()
        right_scroll.setWidget(right_panel)
        splitter.addWidget(right_scroll)

        splitter.setSizes([500, 300])
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(25)
        main.addWidget(self.progress_bar)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.preview_btn = QPushButton("Preview")
        self.export_btn = QPushButton("Export")
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setVisible(False)

        for b in (self.preview_btn, self.export_btn, self.cancel_btn):
            b.setMinimumHeight(32)
            b.setMinimumWidth(100)

        self.preview_btn.clicked.connect(self.preview_export)
        self.export_btn.clicked.connect(self.start_export)
        self.cancel_btn.clicked.connect(self.cancel_export)

        btn_layout.addStretch()
        btn_layout.addWidget(self.preview_btn)
        btn_layout.addWidget(self.export_btn)
        btn_layout.addWidget(self.cancel_btn)
        main.addLayout(btn_layout)

    # ------------------------------------------------------------------
    def _create_settings_panel(self) -> QFrame:
        panel = QFrame()
        lay = QVBoxLayout(panel)
        lay.setSpacing(6)
        lay.setContentsMargins(4, 4, 4, 4)

        # Layout selection
        grp = QGroupBox("Layout Selection")
        form = QGridLayout(grp)
        form.addWidget(QLabel("Print Layout:"), 0, 0)
        self.layout_combo = QComboBox()
        self.layout_combo.currentTextChanged.connect(self.on_layout_changed)
        form.addWidget(self.layout_combo, 0, 1)

        self.enable_atlas_btn = QPushButton("Enable Atlas")
        self.enable_atlas_btn.clicked.connect(self.toggle_atlas)
        self.enable_atlas_btn.setVisible(False)
        self.enable_atlas_btn.setMaximumWidth(120)
        form.addWidget(self.enable_atlas_btn, 0, 2)

        self.atlas_info_lbl = QLabel("Atlas: Not enabled")
        self.atlas_info_lbl.setWordWrap(True)
        form.addWidget(self.atlas_info_lbl, 1, 0, 1, 3)
        lay.addWidget(grp)

        # Export mode
        self.mode_group_box = QGroupBox("Export Mode")
        mode_lay = QVBoxLayout(self.mode_group_box)
        self.mode_group = QButtonGroup()
        self.single_radio = QRadioButton("Export Single Layout")
        self.all_radio = QRadioButton("Export All Pages")
        self.custom_radio = QRadioButton("Export Custom Pages")
        self.all_radio.setChecked(True)

        for rb, idx in zip((self.single_radio, self.all_radio, self.custom_radio),
                           (2, 0, 1)):
            self.mode_group.addButton(rb, idx)
            mode_lay.addWidget(rb)

        self.custom_radio.toggled.connect(
            lambda c: self.custom_pages_edit.setEnabled(
                c and self.is_atlas_layout))

        cust_lay = QHBoxLayout()
        cust_lay.addWidget(QLabel("Pages:"))
        self.custom_pages_edit = QLineEdit()
        self.custom_pages_edit.setPlaceholderText(
            "Examples: 1,3,5 or 1-5,8,10-12")
        cust_lay.addWidget(self.custom_pages_edit)
        mode_lay.addLayout(cust_lay)
        lay.addWidget(self.mode_group_box)

        # Output settings
        out_grp = QGroupBox("Output Settings")
        out_lay = QGridLayout(out_grp)
        out_lay.addWidget(QLabel("Output Directory:"), 0, 0)
        self.output_dir_edit = QLineEdit()
        out_lay.addWidget(self.output_dir_edit, 0, 1)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.browse_output_dir)
        browse.setMaximumWidth(80)
        out_lay.addWidget(browse, 0, 2)

        out_lay.addWidget(QLabel("Filename Pattern:"), 1, 0)
        self.filename_edit = QLineEdit("atlas_{page}")
        self.filename_edit.setToolTip(
            "Available placeholders: {page}, {index}, {field_name}")
        out_lay.addWidget(self.filename_edit, 1, 1, 1, 2)

        out_lay.addWidget(QLabel("Format:"), 2, 0)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["PDF", "PNG", "JPG", "TIFF", "SVG"])
        self.format_combo.currentTextChanged.connect(self.on_format_changed)
        out_lay.addWidget(self.format_combo, 2, 1)

        self.single_pdf_check = QCheckBox("Export as single PDF")
        self.single_pdf_check.toggled.connect(self.on_single_pdf_toggled)
        out_lay.addWidget(self.single_pdf_check, 3, 0, 1, 3)
        lay.addWidget(out_grp)

        # Quality settings
        qual_grp = QGroupBox("Quality Settings")
        qual_lay = QGridLayout(qual_grp)

        qual_lay.addWidget(QLabel("DPI:"), 0, 0)
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 1200)
        self.dpi_spin.setValue(300)
        self.dpi_spin.setMaximumWidth(80)
        qual_lay.addWidget(self.dpi_spin, 0, 1)

        qual_lay.addWidget(QLabel("JPG Quality:"), 0, 2)
        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(1, 100)
        self.quality_slider.setValue(95)
        qual_lay.addWidget(self.quality_slider, 0, 3)

        self.quality_lbl = QLabel("95%")
        self.quality_slider.valueChanged.connect(
            lambda v: self.quality_lbl.setText(f"{v}%"))
        qual_lay.addWidget(self.quality_lbl, 0, 4)

        qual_lay.addWidget(QLabel("Width (px):"), 1, 0)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(0, 20000)
        self.width_spin.setSpecialValueText("Auto")
        self.width_spin.setMaximumWidth(80)
        qual_lay.addWidget(self.width_spin, 1, 1)

        qual_lay.addWidget(QLabel("Height (px):"), 1, 2)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(0, 20000)
        self.height_spin.setSpecialValueText("Auto")
        self.height_spin.setMaximumWidth(80)
        qual_lay.addWidget(self.height_spin, 1, 3)

        self.png_tiff_comp_lbl = QLabel("PNG/TIFF compression:")
        qual_lay.addWidget(self.png_tiff_comp_lbl, 2, 0)
        self.png_tiff_comp = QSlider(Qt.Orientation.Horizontal)
        self.png_tiff_comp.setRange(0, 9)
        self.png_tiff_comp.setValue(6)
        qual_lay.addWidget(self.png_tiff_comp, 2, 1, 1, 3)

        self.png_tiff_comp_val = QLabel("6")
        self.png_tiff_comp.valueChanged.connect(
            lambda v: self.png_tiff_comp_val.setText(str(v)))
        qual_lay.addWidget(self.png_tiff_comp_val, 2, 4)
        lay.addWidget(qual_grp)

        # Advanced options
        adv_grp = QGroupBox("Advanced Options")
        adv_lay = QGridLayout(adv_grp)

        self.metadata_check = QCheckBox("Include Metadata")
        adv_lay.addWidget(self.metadata_check, 0, 0)

        self.subdir_check = QCheckBox("Create Subdirectories")
        adv_lay.addWidget(self.subdir_check, 0, 1)

        self.force_vector_check = QCheckBox("Export as vectors")
        self.force_vector_check.setChecked(True)
        self.rasterize_check = QCheckBox("Rasterize whole layout")
        self.force_vector_check.toggled.connect(
            lambda c: self.rasterize_check.setChecked(False) if c else None)
        self.rasterize_check.toggled.connect(
            lambda c: self.force_vector_check.setChecked(False) if c else None)
        adv_lay.addWidget(self.force_vector_check, 1, 0)
        adv_lay.addWidget(self.rasterize_check, 1, 1)

        self.text_export_lbl = QLabel("Text export:")
        adv_lay.addWidget(self.text_export_lbl, 2, 0)
        self.text_export_combo = QComboBox()
        self.text_export_combo.addItems(["Always outlines", "Always text"])
        adv_lay.addWidget(self.text_export_combo, 2, 1)

        self.pdf_compress_lbl = QLabel("PDF compression:")
        adv_lay.addWidget(self.pdf_compress_lbl, 3, 0)
        self.pdf_compress_combo = QComboBox()
        self.pdf_compress_combo.addItems(["Lossless/None", "Lossy (JPEG)"])
        adv_lay.addWidget(self.pdf_compress_combo, 3, 1)

        self.pdf_jpeg_quality_lbl = QLabel("PDF JPEG quality:")
        adv_lay.addWidget(self.pdf_jpeg_quality_lbl, 4, 0)
        self.pdf_jpeg_quality = QSlider(Qt.Orientation.Horizontal)
        self.pdf_jpeg_quality.setRange(1, 100)
        self.pdf_jpeg_quality.setValue(90)
        adv_lay.addWidget(self.pdf_jpeg_quality, 4, 1)

        self.pdf_jpeg_quality_val = QLabel("90")
        self.pdf_jpeg_quality.valueChanged.connect(
            lambda v: self.pdf_jpeg_quality_val.setText(str(v)))
        adv_lay.addWidget(self.pdf_jpeg_quality_val, 4, 2)

        # Show / hide logic
        def update_controls():
            is_pdf = self.format_combo.currentText().upper() == "PDF"
            self.pdf_compress_lbl.setVisible(is_pdf)
            self.pdf_compress_combo.setVisible(is_pdf)
            lossy = self.pdf_compress_combo.currentText().lower().startswith("lossy")
            self.pdf_jpeg_quality_lbl.setVisible(is_pdf and lossy)
            self.pdf_jpeg_quality.setVisible(is_pdf and lossy)
            self.pdf_jpeg_quality_val.setVisible(is_pdf and lossy)

            is_svg = self.format_combo.currentText().upper() == "SVG"
            for w in (self.force_vector_check, self.rasterize_check,
                      self.text_export_lbl, self.text_export_combo):
                w.setVisible(is_pdf or is_svg)

            fmt = self.format_combo.currentText().upper()
            show_png_tiff = fmt in ("PNG", "TIFF")
            self.png_tiff_comp_lbl.setVisible(show_png_tiff)
            self.png_tiff_comp.setVisible(show_png_tiff)
            self.png_tiff_comp_val.setVisible(show_png_tiff)

            is_raster = fmt in ("PNG", "JPG", "TIFF")
            self.dpi_spin.setEnabled(is_raster)
            self.quality_slider.setEnabled(fmt == "JPG")
            self.width_spin.setEnabled(is_raster)
            self.height_spin.setEnabled(is_raster)

        self.format_combo.currentTextChanged.connect(
            lambda _: update_controls())
        self.pdf_compress_combo.currentTextChanged.connect(
            lambda _: update_controls())
        update_controls()

        lay.addWidget(adv_grp)
        lay.addStretch()
        return panel

    # ------------------------------------------------------------------
    def _create_preview_panel(self) -> QFrame:
        panel = QFrame()
        lay = QVBoxLayout(panel)
        lay.setSpacing(6)

        # Preview group
        grp = QGroupBox("Layout Preview")
        grp_lay = QVBoxLayout(grp)

        self.preview_check = QCheckBox("Enable Preview Rendering")
        self.preview_check.setChecked(False)
        grp_lay.addWidget(self.preview_check)

        self.preview_container = QWidget()
        cont_lay = QVBoxLayout(self.preview_container)

        ctrl_lay = QHBoxLayout()
        ctrl_lay.addWidget(QLabel("Page:"))
        self.preview_page_spin = QSpinBox()
        self.preview_page_spin.setMinimum(1)
        self.preview_page_spin.setValue(1)
        self.preview_page_spin.setMaximumWidth(70)
        self.preview_page_spin.valueChanged.connect(self.update_preview_info)
        ctrl_lay.addWidget(self.preview_page_spin)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.update_preview_info)
        refresh_btn.setMaximumWidth(70)
        ctrl_lay.addWidget(refresh_btn)

        stand_btn = QPushButton("Open Standalone")
        stand_btn.clicked.connect(self.open_standalone_preview)
        stand_btn.setMaximumWidth(120)
        ctrl_lay.addWidget(stand_btn)
        ctrl_lay.addStretch()
        cont_lay.addLayout(ctrl_lay)

        self.preview_lbl = QLabel("Select a layout")
        self.preview_lbl.setAlignment(AlignCenter)
        self.preview_lbl.setMinimumHeight(200)
        self.preview_lbl.setStyleSheet(
            "border: 1px solid gray; background-color: white; padding: 5px;")
        self.preview_lbl.setScaledContents(False)
        self.preview_lbl.setWordWrap(True)
        self.preview_lbl.setCursor(QCursor(PointingHandCursor))
        self.preview_lbl.mousePressEvent = self.on_preview_label_click
        cont_lay.addWidget(self.preview_lbl)

        grp_lay.addWidget(self.preview_container)

        self.preview_info = QTextEdit()
        self.preview_info.setMinimumHeight(120)
        self.preview_info.setReadOnly(True)
        self.preview_info.setPlainText("Select a layout")
        grp_lay.addWidget(self.preview_info)

        self.preview_check.toggled.connect(self.preview_container.setVisible)
        self.preview_check.toggled.connect(
            lambda c: self.update_preview_info() if c else None)
        self.preview_container.setVisible(False)

        lay.addWidget(grp)

        # Log
        log_grp = QGroupBox("Export Log")
        log_lay = QVBoxLayout(log_grp)
        self.log_text = QTextEdit()
        self.log_text.setMinimumHeight(100)
        self.log_text.setReadOnly(True)
        log_lay.addWidget(self.log_text)
        lay.addWidget(log_grp)

        return panel

    # ------------------------------------------------------------------
    def on_preview_label_click(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_standalone_preview()

    # ------------------------------------------------------------------
    def open_standalone_preview(self):
        if not self.current_layout:
            QMessageBox.warning(self, "Warning", "No layout selected")
            return

        if not self.standalone_preview:
            self.standalone_preview = StandalonePreviewDialog(self)

        page = max(0, self.preview_page_spin.value() - 1)
        self.standalone_preview.set_layout(self.current_layout,
                                           self.is_atlas_layout,
                                           page)
        self.standalone_preview.show()

    # ------------------------------------------------------------------
    def load_layouts(self):
        self.layout_combo.blockSignals(True)
        self.layout_combo.clear()

        proj = QgsProject.instance()
        mgr = proj.layoutManager()
        layouts = mgr.printLayouts()

        if not layouts:
            self.layout_combo.addItem("No layouts available")
            self.layout_combo.setItemData(0, None)
            self.current_layout = None
            self.is_atlas_layout = False
            self.atlas_info_lbl.setText("No print layouts found in project")
            self.preview_info.setPlainText(
                "No print layouts available.\nPlease create a print layout first.")
            self.preview_lbl.setText("No layouts available")
            self.export_btn.setEnabled(False)
            self.layout_combo.blockSignals(False)
            return

        for l in layouts:
            self.layout_combo.addItem(l.name())

        self.layout_combo.blockSignals(False)
        self.export_btn.setEnabled(True)
        self.layout_combo.setCurrentIndex(0)
        self.on_layout_changed(layouts[0].name())

    # ------------------------------------------------------------------
    def on_layout_changed(self, name: str):
        proj = QgsProject.instance()
        layout = proj.layoutManager().layoutByName(name)
        if not layout:
            self.current_layout = None
            self.is_atlas_layout = False
            self.atlas_info_lbl.setText("No layout selected")
            self.preview_info.setPlainText("No layout selected")
            self.preview_lbl.setText("No layout selected")
            self.enable_atlas_btn.setVisible(False)
            self.update_export_mode_visibility()
            return

        self.current_layout = layout
        atlas = layout.atlas()

        # Refresh atlas if possible
        try:
            if hasattr(atlas, 'updateFeatures'):
                atlas.updateFeatures()
            elif hasattr(atlas, 'refresh'):
                atlas.refresh()
        except Exception as e:
            self.log_text.append(f"Note: Atlas refresh warning: {e}")

        cov = atlas.coverageLayer()
        has_cov = cov and cov.isValid()
        enabled = atlas.enabled()
        self.is_atlas_layout = enabled and has_cov
        self.update_export_mode_visibility()

        if has_cov and not enabled:
            cnt = self._get_safe_feature_count_from_layer(cov)
            self.atlas_info_lbl.setText(
                f"Atlas: Configured but not enabled ({cnt} features from '{cov.name()}')")
            self.enable_atlas_btn.setText("Enable Atlas")
            self.enable_atlas_btn.setVisible(True)
            self.preview_info.setPlainText(
                f"Atlas is configured but not enabled.\n"
                f"Coverage layer: {cov.name()} ({cnt} features)\n"
                f"Click 'Enable Atlas' to activate it.")
            self.preview_lbl.setText(
                "Atlas configured but not enabled.\nClick 'Enable Atlas' to activate.")
        elif enabled and has_cov:
            cnt = self._get_safe_feature_count_from_layer(cov)
            self.atlas_info_lbl.setText(
                f"Atlas: Enabled ({cnt} features from '{cov.name()}')")
            self.enable_atlas_btn.setText("Disable Atlas")
            self.enable_atlas_btn.setVisible(True)

            max_p = max(1, cnt)
            self.preview_page_spin.setMaximum(max_p)
            if self.preview_page_spin.value() > max_p:
                self.preview_page_spin.setValue(1)

            self._update_filename_tooltip(cov)
            self.update_preview_info()
        elif enabled and not has_cov:
            self.atlas_info_lbl.setText(
                "Atlas: Enabled but no coverage layer set")
            self.enable_atlas_btn.setText("Disable Atlas")
            self.enable_atlas_btn.setVisible(True)
            self.preview_info.setPlainText(
                "Atlas enabled but no coverage layer configured.\n"
                "Please set a coverage layer in the atlas properties.")
            self.preview_lbl.setText(
                "Atlas enabled but no coverage layer configured.")
        else:
            self.atlas_info_lbl.setText(
                "Regular Layout: No atlas configuration")
            self.enable_atlas_btn.setVisible(False)
            self.preview_info.setPlainText(
                f"Regular layout: {layout.name()}\n"
                f"Single page export available\n"
                f"No atlas configuration found.")
            self.preview_lbl.setText("Regular layout\n(single page export)")
            self.single_radio.setChecked(True)
            self.preview_page_spin.setMaximum(1)
            self.preview_page_spin.setValue(1)
            self.update_preview_info()

    # ------------------------------------------------------------------
    def _get_safe_feature_count_from_layer(self, layer):
        if not layer or not layer.isValid():
            return 0
        try:
            return layer.featureCount()
        except Exception:
            pass
        try:
            return len(list(layer.getFeatures()))
        except Exception:
            pass
        try:
            if layer.dataProvider():
                return layer.dataProvider().featureCount()
        except Exception:
            pass
        return 0

    # ------------------------------------------------------------------
    def _update_filename_tooltip(self, coverage_layer):
        try:
            if coverage_layer and coverage_layer.fields():
                fields = [f.name() for f in coverage_layer.fields()][:5]
                tip = "Available placeholders: {page}, {index}"
                if fields:
                    tip += ", " + ", ".join(f"{{{n}}}" for n in fields)
                    if len(coverage_layer.fields()) > 5:
                        tip += ", ..."
                self.filename_edit.setToolTip(tip)
        except Exception:
            self.filename_edit.setToolTip(
                "Available placeholders: {page}, {index}")

    # ------------------------------------------------------------------
    def update_export_mode_visibility(self):
        if self.is_atlas_layout:
            self.all_radio.setText("Export All Atlas Pages")
            self.custom_radio.setText("Export Custom Atlas Pages")
            self.single_radio.setText("Export Single Page (N/A for Atlas)")
            self.single_radio.setEnabled(False)
            self.all_radio.setEnabled(True)
            self.custom_radio.setEnabled(True)
            if self.single_radio.isChecked():
                self.all_radio.setChecked(True)
            self.custom_pages_edit.setEnabled(self.custom_radio.isChecked())
        else:
            self.all_radio.setText("Export All Pages (N/A)")
            self.custom_radio.setText("Export Custom Pages (N/A)")
            self.single_radio.setText("Export Single Layout")
            self.single_radio.setEnabled(True)
            self.all_radio.setEnabled(False)
            self.custom_radio.setEnabled(False)
            self.single_radio.setChecked(True)
            self.custom_pages_edit.setEnabled(False)

    # ------------------------------------------------------------------
    def toggle_atlas(self):
        if not self.current_layout:
            QMessageBox.warning(self, "Warning", "No layout selected")
            return

        atlas = self.current_layout.atlas()
        try:
            if atlas.enabled():
                atlas.setEnabled(False)
                self.log_text.append("Atlas disabled")
            else:
                cov = atlas.coverageLayer()
                if not cov or not cov.isValid():
                    QMessageBox.warning(
                        self, "Warning",
                        "Cannot enable atlas: No valid coverage layer configured.\n"
                        "Please configure the atlas coverage layer in the layout settings first.")
                    return

                cnt = self._get_safe_feature_count_from_layer(cov)
                if cnt == 0:
                    reply = QtCompat.message_box_question(
                        self, "Warning",
                        f"The coverage layer '{cov.name()}' appears to have no features.\n"
                        "Do you want to enable the atlas anyway?",
                        QtCompat.Yes | QtCompat.No,
                        QtCompat.No)
                    if reply != QtCompat.Yes:
                        return

                atlas.setEnabled(True)
                try:
                    if hasattr(atlas, 'updateFeatures'):
                        atlas.updateFeatures()
                    elif hasattr(atlas, 'refresh'):
                        atlas.refresh()
                except Exception as e:
                    self.log_text.append(f"Atlas refresh warning: {e}")

                self.log_text.append(
                    f"Atlas enabled with coverage layer: {cov.name()} ({cnt} features)")

            self.on_layout_changed(self.current_layout.name())
        except Exception as e:
            QMessageBox.critical(self, "Error",
                                 f"Failed to toggle atlas state: {e}")
            self.log_text.append(f"Error toggling atlas: {e}")

    # ------------------------------------------------------------------
    def update_preview_info(self):
        if not self.current_layout:
            self.preview_info.setPlainText("No layout selected")
            return

        try:
            page = max(0, self.preview_page_spin.value() - 1)
            txt = SimplePreviewGenerator.generate_preview_info(
                self.current_layout, page, self.is_atlas_layout)

            fmt = self.format_combo.currentText().upper()
            sett = f"\n{'='*50}\nEXPORT SETTINGS\n{'='*50}\n"
            sett += f"Format: {fmt}\n"

            if fmt in ("PDF", "SVG"):
                sett += f"Export as vectors: {'Yes' if self.force_vector_check.isChecked() else 'No'}\n"
                sett += f"Rasterize layout: {'Yes' if self.rasterize_check.isChecked() else 'No'}\n"
                sett += f"Text export: {self.text_export_combo.currentText()}\n"
                if fmt == "PDF":
                    sett += f"PDF compression: {self.pdf_compress_combo.currentText()}\n"
                    if self.pdf_compress_combo.currentText().lower().startswith("lossy"):
                        sett += f"JPEG quality: {self.pdf_jpeg_quality.value()}%\n"
            else:
                sett += f"DPI: {self.dpi_spin.value()}\n"
                if fmt == "JPG":
                    sett += f"Quality: {self.quality_slider.value()}%\n"
                elif fmt in ("PNG", "TIFF"):
                    sett += f"Compression: {self.png_tiff_comp.value()}\n"

            if self.width_spin.value() > 0 or self.height_spin.value() > 0:
                w = self.width_spin.value() if self.width_spin.value() > 0 else "Auto"
                h = self.height_spin.value() if self.height_spin.value() > 0 else "Auto"
                sett += f"Custom size: {w} × {h} px\n"

            self.preview_info.setPlainText(txt + sett)

            if self.preview_check.isChecked():
                self.update_preview_image()
        except Exception as e:
            self.preview_info.setPlainText(f"Preview update error: {e}")
            self.log_text.append(f"Preview error: {e}")

    # ------------------------------------------------------------------
    def update_preview_image(self):
        if not self.current_layout or not self.preview_check.isChecked():
            return

        page = self.preview_page_spin.value() - 1
        pix = SimplePreviewGenerator.generate_simple_preview_image(
            self.current_layout, page, self.is_atlas_layout)

        if not pix.isNull():
            target = self.preview_lbl.size() - QSize(20, 20)
            scaled = pix.scaled(target,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
            self.preview_lbl.setPixmap(scaled)
            self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.preview_lbl.setToolTip("Click to open standalone preview")
        else:
            self.preview_lbl.setText("Could not generate preview image")
            self.preview_lbl.setToolTip("")

    # ------------------------------------------------------------------
    def on_single_pdf_toggled(self, checked):
        is_pdf = self.format_combo.currentText().upper() == "PDF"
        self.filename_edit.setEnabled(not (checked and is_pdf))
        if checked and is_pdf:
            self.filename_edit.setToolTip(
                "Filename is automatically generated for single PDF export.")
        else:
            self._update_filename_tooltip(
                self.current_layout.atlas().coverageLayer()
                if self.is_atlas_layout else None)

    # ------------------------------------------------------------------
    def on_format_changed(self, fmt_name: str):
        is_raster = fmt_name in ["PNG", "JPG", "TIFF"]
        self.dpi_spin.setEnabled(is_raster)
        self.quality_slider.setEnabled(fmt_name == "JPG")
        self.width_spin.setEnabled(is_raster)
        self.height_spin.setEnabled(is_raster)

        is_pdf = fmt_name.upper() == "PDF"
        self.single_pdf_check.setVisible(is_pdf and self.is_atlas_layout)
        self.on_single_pdf_toggled(self.single_pdf_check.isChecked())
        self.update_preview_info()

    # ------------------------------------------------------------------
    def browse_output_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Output Directory")
        if path:
            try:
                real = os.path.realpath(path)
                if os.path.isdir(real):
                    self.output_dir_edit.setText(real)
                else:
                    QMessageBox.warning(self, "Invalid Directory",
                                        "Selected path is not a valid directory")
            except Exception as e:
                QMessageBox.warning(self, "Invalid Path",
                                    f"Cannot use selected directory: {e}")

    # ------------------------------------------------------------------
    def preview_export(self):
        if not self.current_layout:
            QMessageBox.warning(self, "Warning", "Please select a layout")
            return

        settings = self.get_export_settings()
        if not settings:
            return

        if settings.is_atlas_layout:
            atlas = self.current_layout.atlas()
            if not atlas.enabled():
                QMessageBox.warning(self, "Warning",
                                    "Atlas is not enabled. Enable it first to see export preview.")
                return

            worker = AtlasExportWorker(self.current_layout, settings)
            pages = worker._get_pages_to_export(atlas)

            txt = f"""Export Preview:
{'━'*60}
Layout: {self.current_layout.name()} (Atlas Mode)
Coverage Layer: {atlas.coverageLayer().name()}
{'━'*60}
Export Mode: {settings.export_mode.value.upper()}
Pages to export: {len(pages)} pages
"""
            if len(pages) <= 20:
                txt += f"Page numbers: {', '.join(str(p+1) for p in pages)}\n"
            else:
                first = ', '.join(str(p+1) for p in pages[:10])
                last = ', '.join(str(p+1) for p in pages[-10:])
                txt += f"Page numbers: {first} ... {last}\n"
        else:
            txt = f"""Export Preview:
{'━'*60}
Layout: {self.current_layout.name()} (Single Layout Mode)
{'━'*60}
Export Mode: SINGLE LAYOUT
Pages to export: 1 page
"""

        txt += f"""{'━'*60}
Output Settings:
  Directory: {settings.output_dir}
  Format: {settings.export_format.value.upper()}
  Filename pattern: {settings.filename_pattern}
  DPI: {settings.dpi}
  JPG Quality: {settings.quality}%
"""
        if settings.width and settings.height:
            txt += f" Custom size: {settings.width} × {settings.height} px\n"

        fmt = settings.export_format.value.upper()
        if fmt in ("PDF", "SVG"):
            txt += "Advanced (Vector/Text):\n"
            txt += f" Export as vectors: {'Yes' if settings.force_vector else 'No'}\n"
            txt += f" Rasterize whole layout: {'Yes' if settings.rasterize_whole else 'No'}\n"
            txt += f" Text export: {settings.text_render}\n"
            if fmt == "PDF":
                txt += f" PDF compression: {settings.pdf_image_compression}\n"
                if settings.pdf_image_compression.lower().startswith("lossy"):
                    txt += f" PDF JPEG quality: {settings.pdf_jpeg_quality}\n"
        else:
            if fmt in ("PNG", "TIFF"):
                txt += f"PNG/TIFF compression level: {settings.png_tiff_compression}\n"

        txt += f"{'━'*60}\n"

        if settings.is_atlas_layout:
            txt += "Sample filenames (first 3 pages):\n"
            try:
                atlas = self.current_layout.atlas()
                cov = atlas.coverageLayer()
                for i, pg in enumerate(pages[:3]):
                    fn = settings.filename_pattern
                    fn = fn.replace("{page}", str(pg + 1).zfill(3))
                    fn = fn.replace("{index}", str(pg))
                    feat = SimplePreviewGenerator._get_safe_feature_at_index(
                        cov, pg)
                    if feat and feat.isValid() and cov:
                        for f in cov.fields():
                            ph = "{" + f.name() + "}"
                            if ph in fn:
                                try:
                                    val = str(feat[f.name()])
                                    val = re.sub(r'[<>:"/\\|?*]', '_', val)
                                    val = ''.join(
                                        c for c in val if ord(c) >= 32)
                                    val = ''.join(
                                        c for c in val if c.isalnum() or c in '._- ')
                                    fn = fn.replace(ph, val)
                                except Exception:
                                    fn = fn.replace(ph, "error")
                    fn += f".{settings.export_format.value}"
                    txt += f" Page {pg + 1}: {fn}\n"
            except Exception as e:
                txt += f" Error generating sample filenames: {e}\n"
        else:
            fn = settings.filename_pattern
            fn = fn.replace("{page}", "001")
            fn = fn.replace("{index}", "0")
            fn += f".{settings.export_format.value}"
            txt += f"Output filename: {fn}\n"

        txt += f"{'━'*60}"
        self.log_text.setPlainText(txt)

    # ------------------------------------------------------------------
    def get_export_settings(self) -> Optional[ExportSettings]:
        out_dir = self.output_dir_edit.text().strip()
        if not out_dir:
            QMessageBox.warning(
                self, "Warning", "Please specify an output directory")
            return None

        mode_id = self.mode_group.checkedId()
        if mode_id == 2 and self.is_atlas_layout:
            QMessageBox.warning(
                self, "Warning",
                "Single page export is not available for atlas layouts. "
                "Please select 'All Pages' or 'Custom Pages'.")
            return None

        if mode_id == 2 or not self.is_atlas_layout:
            export_mode = ExportMode.SINGLE
            custom = []
        elif mode_id == 0:
            export_mode = ExportMode.ALL
            custom = []
        else:
            export_mode = ExportMode.CUSTOM
            txt = self.custom_pages_edit.text().strip()
            if not txt:
                QMessageBox.warning(self, "Warning",
                                    "Please specify pages to export in custom mode")
                return None
            custom = []
            try:
                for part in txt.split(','):
                    part = part.strip()
                    if '-' in part:
                        s, e = map(int, part.split('-'))
                        custom.extend(range(s, e + 1))
                    else:
                        custom.append(int(part))
            except ValueError:
                QMessageBox.warning(
                    self, "Warning",
                    "Invalid custom pages format. Use: 1,3,5-8,10")
                return None

        fmt = ExportFormat(self.format_combo.currentText().lower())
        return ExportSettings(
            output_dir=out_dir,
            filename_pattern=self.filename_edit.text(),
            export_format=fmt,
            export_mode=export_mode,
            custom_pages=custom,
            dpi=self.dpi_spin.value(),
            quality=self.quality_slider.value(),
            width=self.width_spin.value() if self.width_spin.value() > 0 else None,
            height=self.height_spin.value() if self.height_spin.value() > 0 else None,
            include_metadata=self.metadata_check.isChecked(),
            create_subdirs=self.subdir_check.isChecked(),
            is_atlas_layout=self.is_atlas_layout,
            export_as_single_pdf=self.single_pdf_check.isChecked(),
            force_vector=self.force_vector_check.isChecked(),
            rasterize_whole=self.rasterize_check.isChecked(),
            text_render=self.text_export_combo.currentText(),
            pdf_image_compression=self.pdf_compress_combo.currentText(),
            pdf_jpeg_quality=self.pdf_jpeg_quality.value(),
            png_tiff_compression=self.png_tiff_comp.value()
        )

    # ------------------------------------------------------------------
    def start_export(self):
        if not self.current_layout:
            QMessageBox.warning(self, "Warning", "Please select a layout")
            return

        settings = self.get_export_settings()
        if not settings:
            return

        if settings.is_atlas_layout:
            if not self.current_layout.atlas().enabled():
                QMessageBox.warning(self, "Warning",
                                    "Atlas is not enabled in the selected layout")
                return

        self._reset_export_ui(True)
        self.log_text.clear()
        self.log_text.append(
            "Starting atlas export..." if settings.is_atlas_layout else
            "Starting layout export...")

        self.export_worker = AtlasExportWorker(self.current_layout, settings)
        self.export_worker.progress_updated.connect(self.on_progress_updated)
        self.export_worker.page_exported.connect(self.on_page_exported)
        self.export_worker.export_finished.connect(self.on_export_finished)
        self.export_worker.start()

    # ------------------------------------------------------------------
    def _reset_export_ui(self, exporting: bool):
        if exporting:
            self.export_btn.setEnabled(False)
            self.export_btn.setText("Exporting...")
            self.cancel_btn.setVisible(True)
            self.cancel_btn.setEnabled(True)
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
        else:
            self.export_btn.setEnabled(True)
            self.export_btn.setText("Export")
            self.cancel_btn.setVisible(False)
            self.progress_bar.setVisible(False)
            self.progress_bar.setValue(0)

    # ------------------------------------------------------------------
    def cancel_export(self):
        if self.export_worker:
            self.export_worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.cancel_btn.setText("Cancelling...")
            self.log_text.append("Cancelling export...")

    # ------------------------------------------------------------------
    def on_progress_updated(self, prog: int, msg: str):
        self.progress_bar.setValue(prog)

    # ------------------------------------------------------------------
    def on_page_exported(self, page: int, filename: str):
        self.log_text.append(f"Exported page {page}: {filename}")

    # ------------------------------------------------------------------
    def on_export_finished(self, success: bool, msg: str):
        self._reset_export_ui(False)
        if success:
            self.log_text.append(f"Success: {msg}")
            QMessageBox.information(self, "Export Complete", msg)
        else:
            self.log_text.append(f"Failed: {msg}")
            if "cancel" in msg.lower():
                QMessageBox.information(self, "Export Cancelled", msg)
            else:
                QMessageBox.warning(self, "Export Failed", msg)

        if self.export_worker:
            self.export_worker.deleteLater()
        self.export_worker = None


# ----------------------------------------------------------------------
# Plugin entry point
# ----------------------------------------------------------------------
def show_atlas_export_dialog():
    """Show the dialog (call from QGIS Python console or plugin)"""
    dlg = EnhancedAtlasExportDialog(iface.mainWindow())
    dlg.show()
    return dlg


# Uncomment to test directly:
# show_atlas_export_dialog()

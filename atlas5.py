

import os
import sys
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass
from enum import Enum

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton,
    QLabel, QLineEdit, QSpinBox, QComboBox, QCheckBox, QProgressBar,
    QGroupBox, QRadioButton, QButtonGroup, QFileDialog, QMessageBox,
    QTextEdit, QSplitter, QFrame, QSlider, QScrollArea
)
from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from qgis.PyQt.QtGui import QFont, QPalette, QPixmap, QIcon, QPainter

from qgis.core import (
    QgsProject, QgsLayoutManager, QgsPrintLayout, QgsLayoutExporter,
    QgsLayoutItemMap, QgsRectangle, QgsCoordinateReferenceSystem,
    QgsLayoutSize, QgsUnitTypes, QgsApplication, Qgis, QgsVectorLayer,
    QgsLayoutRenderContext, QgsMapSettings, QgsFeatureRequest
)
from qgis.PyQt.QtWidgets import *
from qgis.gui import QgsMessageBar
from qgis.utils import iface


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

    # Advanced options
    force_vector: bool = False
    rasterize_whole: bool = False
    text_render: str = "Always outlines"
    pdf_image_compression: str = "Lossy (JPEG)"
    pdf_jpeg_quality: int = 90
    png_tiff_compression: int = 6


class SimplePreviewGenerator:
    """Simple synchronous preview generator to avoid threading issues"""

    @staticmethod
    def generate_preview_info(layout: QgsPrintLayout, page_index: int = 0, is_atlas: bool = True) -> str:
        """Generate preview information text without rendering images"""
        try:
            if not is_atlas:
                return f"Regular Layout: {layout.name()}\nSingle page export\nNo atlas configuration"

            atlas = layout.atlas()
            if not atlas.enabled():
                return "Atlas not enabled"

            coverage_layer = atlas.coverageLayer()
            if not coverage_layer:
                return "Atlas enabled but no coverage layer configured"

            # FIXED: Better feature count handling with fallbacks
            total_pages = SimplePreviewGenerator._get_safe_feature_count(
                atlas, coverage_layer)
            if total_pages == 0:
                return "Atlas has 0 pages (check coverage layer or filters)"

            if page_index >= total_pages:
                return f"Invalid page index: {page_index + 1} (max: {total_pages})"

            # FIXED: Safe feature retrieval
            feature = SimplePreviewGenerator._get_safe_feature_at_index(
                coverage_layer, page_index)

            info = f"Page {page_index + 1} of {total_pages}\n"
            info += f"Layer: {coverage_layer.name()}\n"

            if feature and feature.isValid() and coverage_layer.fields():
                info += "Attributes:\n"
                for i, field in enumerate(coverage_layer.fields()):
                    if i >= 5:  # Limit to first 5 fields
                        info += "  ...\n"
                        break
                    try:
                        value = feature[field.name()]
                        info += f"  {field.name()}: {value}\n"
                    except Exception:
                        info += f"  {field.name()}: <error reading value>\n"

            return info

        except Exception as e:
            return f"Preview error: {str(e)}"

    @staticmethod
    def _get_safe_feature_count(atlas, coverage_layer) -> int:
        """Safely get feature count with multiple fallback methods"""
        try:
            # Method 1: Try atlas.count() if properly initialized
            if atlas.enabled():
                count = atlas.count()
                if count > 0:
                    return count
        except Exception:
            pass

        try:
            # Method 2: Get from coverage layer directly
            if coverage_layer:
                return coverage_layer.featureCount()
        except Exception:
            pass

        return 0

    @staticmethod
    def _get_safe_feature_at_index(coverage_layer, index: int):
        """Safely get feature at specific index"""
        try:
            if not coverage_layer:
                return None

            # Get features with proper error handling
            features = list(coverage_layer.getFeatures())
            if index < len(features):
                return features[index]
        except Exception:
            pass

        return None

    @staticmethod
    def generate_simple_preview_image(layout: QgsPrintLayout, page_index: int = 0, is_atlas: bool = True) -> QPixmap:
        """Render an actual preview image of the layout/atlas page"""
        try:
            from qgis.PyQt.QtGui import QImage, QPainter
            from qgis.PyQt.QtCore import QSize, QRectF

            exporter = QgsLayoutExporter(layout)
            size = QSize(800, 600)
            image = QImage(size, QImage.Format_ARGB32)
            image.fill(Qt.white)

            if is_atlas:
                atlas = layout.atlas()
                if not atlas.enabled() or not atlas.coverageLayer():
                    pm = QPixmap(size)
                    pm.fill(Qt.white)
                    painter = QPainter(pm)
                    painter.drawText(QRectF(0, 0, size.width(), size.height(
                    )), Qt.AlignCenter, "Atlas not configured")
                    painter.end()
                    return pm

                if not atlas.beginRender():
                    raise Exception("Could not begin atlas rendering")

                if not atlas.seekTo(page_index):
                    atlas.endRender()
                    raise Exception(f"Could not seek to page {page_index+1}")

                painter = QPainter(image)
                result = exporter.renderPage(painter, 0)
                painter.end()
                atlas.endRender()

                if result not in (None, QgsLayoutExporter.Success):
                    raise Exception(f"Render error code {result}")

            else:
                painter = QPainter(image)
                result = exporter.renderPage(painter, 0)
                painter.end()

                if result not in (None, QgsLayoutExporter.Success):
                    raise Exception(f"Render error code {result}")

            return QPixmap.fromImage(image)

        except Exception as e:
            pm = QPixmap(800, 600)
            pm.fill(Qt.white)
            painter = QPainter(pm)
            from qgis.PyQt.QtCore import QRectF
            painter.drawText(QRectF(0, 0, 800, 600),
                             Qt.AlignCenter, f"Preview Error:\n{str(e)}")
            painter.end()
            return pm


class AtlasExportWorker(QThread):
    """Worker thread for atlas export operations"""

    progress_updated = pyqtSignal(int, str)
    export_finished = pyqtSignal(bool, str)
    page_exported = pyqtSignal(int, str)

    def __init__(self, layout: QgsPrintLayout, settings: ExportSettings):
        super().__init__()
        self.layout = layout
        self.settings = settings
        self.cancelled = False

    def run(self):
        """Execute the export process"""
        try:
            if not self.settings.is_atlas_layout:
                # Export single layout (non-atlas)
                self._export_single_layout()
                return

            # Atlas export
            atlas = self.layout.atlas()
            if not atlas.enabled():
                self.export_finished.emit(
                    False, "Atlas is not enabled in the layout")
                return

            export_settings = self._create_export_settings()

            # Get pages to export (0-based)
            pages_to_export = self._get_pages_to_export(atlas)
            total_pages = len(pages_to_export)
            if total_pages == 0:
                self.export_finished.emit(False, "No pages to export")
                return

            os.makedirs(self.settings.output_dir, exist_ok=True)

            exported_files = []
            exporter = QgsLayoutExporter(self.layout)

            # Begin atlas rendering once
            if not atlas.beginRender():
                self.export_finished.emit(
                    False, "Failed to begin atlas rendering")
                return

            try:
                for i, page_index in enumerate(pages_to_export):
                    if self.cancelled:
                        break

                    # Seek to the specific feature/page
                    if not atlas.seekTo(page_index):
                        self.export_finished.emit(
                            False, f"Failed to seek to page {page_index + 1}")
                        return

                    # Generate filename
                    filename = self._generate_filename(page_index, atlas)
                    filepath = os.path.join(self.settings.output_dir, filename)

                    # Export page
                    result = self._export_page(
                        exporter, filepath, export_settings)

                    if result == QgsLayoutExporter.Success:
                        exported_files.append(filepath)
                        self.page_exported.emit(page_index + 1, filename)
                    else:
                        self.export_finished.emit(
                            False, f"Failed to export page {page_index + 1}: {self._get_export_error(result)}"
                        )
                        return

                    progress = int((i + 1) * 100 / total_pages)
                    self.progress_updated.emit(
                        progress, f"Exported {i + 1}/{total_pages} pages")
            finally:
                atlas.endRender()

            if not self.cancelled:
                self.export_finished.emit(
                    True, f"Successfully exported {len(exported_files)} pages")
            else:
                self.export_finished.emit(
                    False, f"Export cancelled. {len(exported_files)} pages were exported before cancellation.")

        except Exception as e:
            self.export_finished.emit(False, f"Export failed: {str(e)}")

    def _export_single_layout(self):
        """Export a single non-atlas layout"""
        try:
            os.makedirs(self.settings.output_dir, exist_ok=True)

            export_settings = self._create_export_settings()
            exporter = QgsLayoutExporter(self.layout)

            # Generate filename for single layout
            filename = self.settings.filename_pattern
            filename = filename.replace("{page}", "001")
            filename = filename.replace("{index}", "0")
            filename += f".{self.settings.export_format.value}"

            filepath = os.path.join(self.settings.output_dir, filename)

            self.progress_updated.emit(50, "Exporting layout...")

            # Export the layout
            result = self._export_page(exporter, filepath, export_settings)

            if result == QgsLayoutExporter.Success:
                self.page_exported.emit(1, filename)
                self.progress_updated.emit(100, "Export complete")
                if not self.cancelled:
                    self.export_finished.emit(
                        True, f"Successfully exported layout: {filename}")
                else:
                    self.export_finished.emit(False, "Export cancelled")
            else:
                self.export_finished.emit(
                    False, f"Failed to export layout: {self._get_export_error(result)}")

        except Exception as e:
            self.export_finished.emit(False, f"Export failed: {str(e)}")

    def cancel(self):
        """Cancel the export process"""
        self.cancelled = True

    def _create_export_settings(self):
        """Create appropriate export settings based on format"""
        # PDF
        if self.settings.export_format == ExportFormat.PDF:
            s = QgsLayoutExporter.PdfExportSettings()

            # Vector vs rasterization
            # Mutually exclusive: if rasterize_whole is True, it overrides force_vector.
            s.forceVectorOutput = bool(
                self.settings.force_vector and not self.settings.rasterize_whole)
            s.rasterizeWholeImage = bool(self.settings.rasterize_whole)

            # Text export (PDF)
            # Map UI string to Qgis.TextRenderFormat
            fmt = (self.settings.text_render or "Always outlines").lower()
            if "prefer" in fmt:
                s.textRenderFormat = Qgis.TextRenderFormat.PreferText
            elif "always text" in fmt:
                s.textRenderFormat = Qgis.TextRenderFormat.AlwaysText
            else:
                s.textRenderFormat = Qgis.TextRenderFormat.AlwaysOutlines

            # Image compression for embedded rasters in PDF
            comp = (self.settings.pdf_image_compression or "Lossy (JPEG)").lower()
            # Some QGIS versions use enums inside PdfExportSettings; use getattr with fallback.
            # Jpeg / Lossless modes:
            if hasattr(s, "imageCompression"):
                # Try to resolve enum values dynamically, fallback to int codes when needed
                try:
                    ImageCompression = getattr(
                        QgsLayoutExporter.PdfExportSettings, "ImageCompression")
                    if "lossy" in comp or "jpeg" in comp:
                        s.imageCompression = ImageCompression.Jpeg
                        if hasattr(s, "jpegQuality"):
                            s.jpegQuality = int(self.settings.pdf_jpeg_quality)
                    else:
                        s.imageCompression = ImageCompression.Lossless
                except Exception:
                    # Fallback: 0 lossless, 1 jpeg
                    s.imageCompression = 1 if (
                        "lossy" in comp or "jpeg" in comp) else 0
                    if hasattr(s, "jpegQuality"):
                        s.jpegQuality = int(self.settings.pdf_jpeg_quality)
            else:
                # Older versions may only support jpegQuality as hint
                if hasattr(s, "jpegQuality") and ("lossy" in comp or "jpeg" in comp):
                    s.jpegQuality = int(self.settings.pdf_jpeg_quality)

            return s

        # Raster images
        elif self.settings.export_format in [ExportFormat.PNG, ExportFormat.JPG, ExportFormat.TIFF]:
            s = QgsLayoutExporter.ImageExportSettings()
            s.dpi = self.settings.dpi
            # Correct way to set imageSize is via QSize assignment
            if self.settings.width and self.settings.height:
                s.imageSize = QSize(self.settings.width, self.settings.height)

            # Apply quality for JPEG (and where supported)
            if hasattr(s, "quality"):
                s.quality = int(self.settings.quality)

            # PNG/TIFF compression level if supported by QGIS/Qt/GDAL backend
            if hasattr(s, "compressionLevel"):
                s.compressionLevel = int(self.settings.png_tiff_compression)

            return s

        # SVG
        else:
            s = QgsLayoutExporter.SvgExportSettings()
            # Where available, map text render format similarly to PDF (some versions expose this)
            fmt = (self.settings.text_render or "Always outlines").lower()
            if hasattr(s, "textRenderFormat"):
                if "prefer" in fmt:
                    s.textRenderFormat = Qgis.TextRenderFormat.PreferText
                elif "always text" in fmt:
                    s.textRenderFormat = Qgis.TextRenderFormat.AlwaysText
                else:
                    s.textRenderFormat = Qgis.TextRenderFormat.AlwaysOutlines

            # Vector emphasis: SVG is vector by default. If a version exposes rasterizeWholeImage or similar flags,
            # map the rasterize_whole toggle; otherwise rely on defaults.
            if hasattr(s, "rasterizeWholeImage"):
                s.rasterizeWholeImage = bool(self.settings.rasterize_whole)

            return s

    def _get_pages_to_export(self, atlas) -> List[int]:
        """Get list of 0-based page indices to export, respecting atlas filters/sorting"""
        total_pages = atlas.count()
        if total_pages <= 0:
            return []

        if self.settings.export_mode == ExportMode.ALL:
            return list(range(total_pages))
        elif self.settings.export_mode == ExportMode.CUSTOM:
            # custom_pages are 1-based from UI; convert and clamp
            out = []
            for p in (self.settings.custom_pages or []):
                i = p - 1
                if 0 <= i < total_pages:
                    out.append(i)
            return out

        return []

    def _generate_filename(self, page_index: int, atlas=None) -> str:
        """Generate filename for the current page"""
        filename = self.settings.filename_pattern
        filename = filename.replace("{page}", str(page_index + 1).zfill(3))
        filename = filename.replace("{index}", str(page_index))

        if atlas and self.settings.is_atlas_layout:
            coverage_layer = atlas.coverageLayer()
            feature = None

            if coverage_layer:
                features = list(coverage_layer.getFeatures())
                if page_index < len(features):
                    feature = features[page_index]

            if feature and feature.isValid() and coverage_layer:
                for field in coverage_layer.fields():
                    placeholder = "{" + field.name() + "}"
                    if placeholder in filename:
                        value = str(feature[field.name()])
                        value = "".join(
                            c for c in value if c.isalnum() or c in "._- ")
                        filename = filename.replace(placeholder, value)

        filename += f".{self.settings.export_format.value}"
        return filename

    def _export_page(self, exporter, filepath, export_settings):
        """Export a single page"""
        if self.settings.export_format == ExportFormat.PDF:
            return exporter.exportToPdf(filepath, export_settings)
        elif self.settings.export_format == ExportFormat.PNG:
            return exporter.exportToImage(filepath, export_settings)
        elif self.settings.export_format == ExportFormat.JPG:
            return exporter.exportToImage(filepath, export_settings)
        elif self.settings.export_format == ExportFormat.TIFF:
            return exporter.exportToImage(filepath, export_settings)
        elif self.settings.export_format == ExportFormat.SVG:
            return exporter.exportToSvg(filepath, export_settings)

    def _get_export_error(self, error_code):
        """Get human-readable error message from export result code"""
        error_messages = {
            QgsLayoutExporter.Success: "Success",
            QgsLayoutExporter.Canceled: "Export was canceled",
            QgsLayoutExporter.MemoryError: "Not enough memory for export",
            QgsLayoutExporter.FileError: "Could not write to file",
            QgsLayoutExporter.PrintError: "Print error",
            QgsLayoutExporter.SvgLayerError: "SVG layer error",
            QgsLayoutExporter.IteratorError: "Iterator error"
        }
        return error_messages.get(error_code, f"Unknown error (code: {error_code})")


class EnhancedAtlasExportDialog(QDialog):
    """Enhanced Atlas Export Dialog with improved UI and scrollable components"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_layout = None
        self.export_worker = None
        self.is_atlas_layout = False
        self.setWindowTitle("Enhanced Atlas Export Tool")

        self.setMinimumSize(800, 600)
        self.resize(900, 700)

        self.setup_ui()
        self.load_layouts()

    def setup_ui(self):
        """Setup the user interface with scrollable components"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # Left panel with scroll area
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        left_scroll.setMinimumWidth(400)

        left_panel = self.create_settings_panel()
        left_scroll.setWidget(left_panel)
        splitter.addWidget(left_scroll)

        # Right panel with scroll area
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        right_scroll.setMinimumWidth(300)

        right_panel = self.create_preview_panel()
        right_scroll.setWidget(right_panel)
        splitter.addWidget(right_scroll)

        splitter.setSizes([500, 300])
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(25)
        main_layout.addWidget(self.progress_bar)

        # Button layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        self.preview_btn = QPushButton("Preview")
        self.export_btn = QPushButton("Export")
        self.export_btn.setStyleSheet("background-color: black; color: white;")
        self.preview_btn.setStyleSheet(
            "background-color: brown; color: white;")

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet(
            "background-color: #aa0000; color: white;")
        self.cancel_btn.setVisible(False)

        for btn in [self.preview_btn, self.export_btn, self.cancel_btn]:
            btn.setMinimumHeight(32)
            btn.setMinimumWidth(100)

        self.preview_btn.clicked.connect(self.preview_export)
        self.export_btn.clicked.connect(self.start_export)
        self.cancel_btn.clicked.connect(self.cancel_export)

        button_layout.addStretch()
        button_layout.addWidget(self.preview_btn)
        button_layout.addWidget(self.export_btn)
        button_layout.addWidget(self.cancel_btn)

        main_layout.addLayout(button_layout)

    def create_settings_panel(self) -> QFrame:
        """Create the settings panel with compact layout"""
        panel = QFrame()
        layout = QVBoxLayout(panel)
        layout.setSpacing(6)
        layout.setContentsMargins(4, 4, 4, 4)

        # Layout selection
        layout_group = QGroupBox("Layout Selection")
        layout_form = QGridLayout(layout_group)
        layout_form.setSpacing(4)

        layout_form.addWidget(QLabel("Print Layout:"), 0, 0)
        self.layout_combo = QComboBox()
        self.layout_combo.currentTextChanged.connect(self.on_layout_changed)
        layout_form.addWidget(self.layout_combo, 0, 1)

        self.enable_atlas_btn = QPushButton("Enable Atlas")
        self.enable_atlas_btn.clicked.connect(self.toggle_atlas)
        self.enable_atlas_btn.setVisible(False)
        self.enable_atlas_btn.setMaximumWidth(120)
        layout_form.addWidget(self.enable_atlas_btn, 0, 2)

        layout_form.setColumnStretch(0, 0)
        layout_form.setColumnStretch(1, 1)
        layout_form.setColumnStretch(2, 0)

        self.atlas_info_label = QLabel("Atlas: Not enabled")
        self.atlas_info_label.setWordWrap(True)
        layout_form.addWidget(self.atlas_info_label, 1, 0, 1, 3)

        layout.addWidget(layout_group)

        # Export mode
        self.mode_group_box = QGroupBox("Export Mode")
        mode_layout = QVBoxLayout(self.mode_group_box)
        mode_layout.setSpacing(4)

        self.mode_group = QButtonGroup()
        self.single_radio = QRadioButton("Export Single Layout")
        self.all_radio = QRadioButton("Export All Pages")
        self.custom_radio = QRadioButton("Export Custom Pages")
        self.all_radio.setChecked(True)

        self.mode_group.addButton(self.all_radio, 0)
        self.mode_group.addButton(self.custom_radio, 1)
        self.mode_group.addButton(self.single_radio, 2)

        mode_layout.addWidget(self.single_radio)
        mode_layout.addWidget(self.all_radio)
        mode_layout.addWidget(self.custom_radio)

        self.custom_radio.toggled.connect(
            lambda checked: self.custom_pages_edit.setEnabled(checked and self.is_atlas_layout))

        custom_layout = QHBoxLayout()
        custom_layout.setSpacing(4)
        custom_layout.addWidget(QLabel("Pages:"))
        self.custom_pages_edit = QLineEdit()
        self.custom_pages_edit.setPlaceholderText(
            "Examples: 1,3,5 or 1-5,8,10-12")
        custom_layout.addWidget(self.custom_pages_edit)
        mode_layout.addLayout(custom_layout)

        layout.addWidget(self.mode_group_box)

        # Output settings
        output_group = QGroupBox("Output Settings")
        output_layout = QGridLayout(output_group)
        output_layout.setSpacing(4)

        output_layout.addWidget(QLabel("Output Directory:"), 0, 0)
        self.output_dir_edit = QLineEdit()
        output_layout.addWidget(self.output_dir_edit, 0, 1)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self.browse_output_dir)
        self.browse_btn.setMaximumWidth(80)
        output_layout.addWidget(self.browse_btn, 0, 2)

        output_layout.addWidget(QLabel("Filename Pattern:"), 1, 0)
        self.filename_edit = QLineEdit("atlas_{page}")
        self.filename_edit.setToolTip(
            "Available placeholders: {page}, {index}, {field_name}")
        output_layout.addWidget(self.filename_edit, 1, 1, 1, 2)

        output_layout.addWidget(QLabel("Format:"), 2, 0)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["PDF", "PNG", "JPG", "TIFF", "SVG"])
        self.format_combo.currentTextChanged.connect(self.on_format_changed)
        output_layout.addWidget(self.format_combo, 2, 1)

        layout.addWidget(output_group)

        # Quality settings - use more compact layout
        quality_group = QGroupBox("Quality Settings")
        quality_layout = QGridLayout(quality_group)
        quality_layout.setSpacing(4)

        quality_layout.addWidget(QLabel("DPI:"), 0, 0)
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 1200)
        self.dpi_spin.setValue(300)
        self.dpi_spin.setMaximumWidth(80)
        quality_layout.addWidget(self.dpi_spin, 0, 1)

        quality_layout.addWidget(QLabel("JPG Quality:"), 0, 2)
        self.quality_slider = QSlider(Qt.Horizontal)
        self.quality_slider.setRange(1, 100)
        self.quality_slider.setValue(95)
        quality_layout.addWidget(self.quality_slider, 0, 3)

        self.quality_label = QLabel("95%")
        self.quality_label.setMinimumWidth(35)
        self.quality_slider.valueChanged.connect(
            lambda v: self.quality_label.setText(f"{v}%"))
        quality_layout.addWidget(self.quality_label, 0, 4)

        quality_layout.addWidget(QLabel("Width (px):"), 1, 0)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(0, 20000)
        self.width_spin.setSpecialValueText("Auto")
        self.width_spin.setMaximumWidth(80)
        quality_layout.addWidget(self.width_spin, 1, 1)

        quality_layout.addWidget(QLabel("Height (px):"), 1, 2)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(0, 20000)
        self.height_spin.setSpecialValueText("Auto")
        self.height_spin.setMaximumWidth(80)
        quality_layout.addWidget(self.height_spin, 1, 3)

        self.png_tiff_comp_label = QLabel("PNG/TIFF compression:")
        quality_layout.addWidget(self.png_tiff_comp_label, 2, 0)

        self.png_tiff_comp = QSlider(Qt.Horizontal)
        self.png_tiff_comp.setRange(0, 9)
        self.png_tiff_comp.setValue(6)
        quality_layout.addWidget(self.png_tiff_comp, 2, 1, 1, 3)

        self.png_tiff_comp_value = QLabel("6")
        self.png_tiff_comp_value.setMinimumWidth(25)
        self.png_tiff_comp.valueChanged.connect(
            lambda v: self.png_tiff_comp_value.setText(str(v)))
        quality_layout.addWidget(self.png_tiff_comp_value, 2, 4)

        layout.addWidget(quality_group)

        # Advanced options with more compact layout
        advanced_group = QGroupBox("Advanced Options")
        advanced_layout = QGridLayout(advanced_group)
        advanced_layout.setSpacing(4)

        # Metadata and subdirs checkboxes
        self.metadata_check = QCheckBox("Include Metadata")
        advanced_layout.addWidget(self.metadata_check, 0, 0)

        self.subdir_check = QCheckBox("Create Subdirectories")
        advanced_layout.addWidget(self.subdir_check, 0, 1)

        # Vector/rasterization toggles (mutually exclusive)
        self.force_vector_check = QCheckBox("Export as vectors")
        self.force_vector_check.setChecked(True)
        self.rasterize_check = QCheckBox("Rasterize whole layout")

        # Make them mutually exclusive
        self.force_vector_check.toggled.connect(
            lambda v: self.rasterize_check.setChecked(False) if v else None
        )
        self.rasterize_check.toggled.connect(
            lambda v: self.force_vector_check.setChecked(False) if v else None
        )

        advanced_layout.addWidget(self.force_vector_check, 1, 0)
        advanced_layout.addWidget(self.rasterize_check, 1, 1)

        # Text export and PDF compression
        self.text_export_label = QLabel("Text export:")
        advanced_layout.addWidget(self.text_export_label, 2, 0)

        self.text_export_combo = QComboBox()
        self.text_export_combo.addItems(["Always outlines", "Always text"])
        advanced_layout.addWidget(self.text_export_combo, 2, 1)

        self.pdf_compress_label = QLabel("PDF compression:")
        advanced_layout.addWidget(self.pdf_compress_label, 3, 0)

        self.pdf_compress_combo = QComboBox()
        self.pdf_compress_combo.addItems(["Lossless/None", "Lossy (JPEG)"])
        advanced_layout.addWidget(self.pdf_compress_combo, 3, 1)

        # PDF JPEG quality
        self.pdf_jpeg_quality_label = QLabel("PDF JPEG quality:")
        advanced_layout.addWidget(self.pdf_jpeg_quality_label, 4, 0)

        self.pdf_jpeg_quality = QSlider(Qt.Horizontal)
        self.pdf_jpeg_quality.setRange(1, 100)
        self.pdf_jpeg_quality.setValue(90)
        advanced_layout.addWidget(self.pdf_jpeg_quality, 4, 1)

        self.pdf_jpeg_quality_value = QLabel("90")
        self.pdf_jpeg_quality_value.setMinimumWidth(25)
        self.pdf_jpeg_quality.valueChanged.connect(
            lambda v: self.pdf_jpeg_quality_value.setText(str(v))
        )
        advanced_layout.addWidget(self.pdf_jpeg_quality_value, 4, 2)

        # Toggle visibility based on format and settings
        def update_pdf_controls():
            is_pdf = self.format_combo.currentText().upper() == "PDF"
            self.pdf_compress_label.setVisible(is_pdf)
            self.pdf_compress_combo.setVisible(is_pdf)
            lossy = (self.pdf_compress_combo.currentText(
            ).lower().startswith("lossy"))
            self.pdf_jpeg_quality_label.setVisible(is_pdf and lossy)
            self.pdf_jpeg_quality.setVisible(is_pdf and lossy)
            self.pdf_jpeg_quality_value.setVisible(is_pdf and lossy)

            is_svg = self.format_combo.currentText().upper() == "SVG"
            # Text export and vector/raster toggles apply to PDF/SVG
            for w in [self.force_vector_check, self.rasterize_check,
                      self.text_export_label, self.text_export_combo]:
                w.setVisible(is_pdf or is_svg)

            # PNG/TIFF compression only relevant for PNG/TIFF
            fmt = self.format_combo.currentText().upper()
            show_png_tiff = fmt in ("PNG", "TIFF")
            self.png_tiff_comp.setVisible(show_png_tiff)
            self.png_tiff_comp_label.setVisible(show_png_tiff)
            self.png_tiff_comp_value.setVisible(show_png_tiff)

            # Enable/disable controls based on format
            is_raster = fmt in ("PNG", "JPG", "TIFF")
            self.dpi_spin.setEnabled(is_raster)
            self.quality_slider.setEnabled(fmt == "JPG")
            self.width_spin.setEnabled(is_raster)
            self.height_spin.setEnabled(is_raster)

        self.format_combo.currentTextChanged.connect(
            lambda _: update_pdf_controls())
        self.pdf_compress_combo.currentTextChanged.connect(
            lambda _: update_pdf_controls())
        update_pdf_controls()

        layout.addWidget(advanced_group)
        layout.addStretch()
        return panel

    def create_preview_panel(self) -> QFrame:
        """Create the preview panel with compact layout"""
        panel = QFrame()
        layout = QVBoxLayout(panel)
        layout.setSpacing(6)

        # Preview group
        preview_group = QGroupBox("Layout Preview")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setSpacing(4)

        # Checkbox to enable/disable preview rendering
        self.preview_checkbox = QCheckBox("Enable Preview Rendering")
        self.preview_checkbox.setChecked(False)
        preview_layout.addWidget(self.preview_checkbox)

        # Container for preview controls + image only
        self.preview_container = QWidget()
        container_layout = QVBoxLayout(self.preview_container)
        container_layout.setSpacing(4)
        container_layout.setContentsMargins(0, 0, 0, 0)

        # Preview controls
        preview_controls = QHBoxLayout()
        preview_controls.setSpacing(4)
        preview_controls.addWidget(QLabel("Page:"))

        self.preview_page_spin = QSpinBox()
        self.preview_page_spin.setMinimum(1)
        self.preview_page_spin.setValue(1)
        self.preview_page_spin.setMaximumWidth(70)
        self.preview_page_spin.valueChanged.connect(self.update_preview_info)
        preview_controls.addWidget(self.preview_page_spin)

        self.refresh_preview_btn = QPushButton("Refresh")
        self.refresh_preview_btn.clicked.connect(self.update_preview_info)
        self.refresh_preview_btn.setMaximumWidth(70)
        self.refresh_preview_btn.setMaximumHeight(28)
        preview_controls.addWidget(self.refresh_preview_btn)

        preview_controls.addStretch()
        container_layout.addLayout(preview_controls)

        # Preview image area - FIXED: Remove fixed minimum size and improve layout
        self.preview_label = QLabel("Select a layout")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(200)
        self.preview_label.setStyleSheet(
            "border: 1px solid gray; background-color: white; padding: 5px;"
        )
        self.preview_label.setScaledContents(False)
        self.preview_label.setWordWrap(True)

        container_layout.addWidget(self.preview_label)

        # Add the preview container (hidden by checkbox)
        preview_layout.addWidget(self.preview_container)

        # Preview info text area (always visible!)
        self.preview_info = QTextEdit()
        self.preview_info.setMinimumHeight(120)
        self.preview_info.setReadOnly(True)
        self.preview_info.setPlainText("Select a layout")
        preview_layout.addWidget(self.preview_info)

        # Show/hide container based on checkbox
        self.preview_checkbox.toggled.connect(
            self.preview_container.setVisible)

        # Also trigger an immediate refresh when enabling
        def _on_preview_toggled(checked: bool):
            if checked:
                self.update_preview_info()

        self.preview_checkbox.toggled.connect(_on_preview_toggled)

        # Start hidden
        self.preview_container.setVisible(False)

        layout.addWidget(preview_group)

        # Log group
        log_group = QGroupBox("Export Log")
        log_layout = QVBoxLayout(log_group)
        log_layout.setSpacing(4)

        self.log_text = QTextEdit()
        self.log_text.setMinimumHeight(100)
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)

        layout.addWidget(log_group)

        return panel

    def load_layouts(self):
        """Load available print layouts"""
        self.layout_combo.clear()
        project = QgsProject.instance()
        layout_manager = project.layoutManager()
        layouts = layout_manager.printLayouts()
        for layout in layouts:
            self.layout_combo.addItem(layout.name(), layout)
        if layouts:
            self.on_layout_changed(layouts[0].name())

    def on_layout_changed(self, layout_name: str):
        """FIXED: Handle layout selection change with better atlas initialization"""
        layout = self.layout_combo.currentData()
        if layout:
            self.current_layout = layout
            atlas = layout.atlas()

            # FIXED: Force atlas refresh on layout change
            try:
                atlas.refresh()
            except Exception:
                pass

            has_coverage_layer = atlas.coverageLayer() is not None
            is_enabled = atlas.enabled()
            self.is_atlas_layout = is_enabled and has_coverage_layer

            # Update export mode visibility based on layout type
            self.update_export_mode_visibility()

            if has_coverage_layer and not is_enabled:
                layer_name = atlas.coverageLayer().name()
                # FIXED: Better feature count with fallback methods
                count = SimplePreviewGenerator._get_safe_feature_count(
                    atlas, atlas.coverageLayer())

                self.atlas_info_label.setText(
                    f"Atlas: Configured but not enabled ({count} features from '{layer_name}')")
                self.enable_atlas_btn.setText("Enable Atlas")
                self.enable_atlas_btn.setVisible(True)
                self.preview_info.setPlainText(
                    "Atlas is configured but not enabled.\nClick 'Enable Atlas' to activate it.")
                self.preview_label.setText(
                    "Atlas configured but not enabled.\nClick 'Enable Atlas' to activate.")

            elif is_enabled and has_coverage_layer:
                # FIXED: Better feature count handling
                count = SimplePreviewGenerator._get_safe_feature_count(
                    atlas, atlas.coverageLayer())
                layer_name = atlas.coverageLayer().name()

                self.atlas_info_label.setText(
                    f"Atlas: Enabled ({count} features from '{layer_name}')")
                self.enable_atlas_btn.setText("Disable Atlas")
                self.enable_atlas_btn.setVisible(True)

                self.preview_page_spin.setMaximum(max(1, count))

                # FIXED: Better field name handling
                if atlas.coverageLayer() and atlas.coverageLayer().fields():
                    try:
                        field_names = [field.name()
                                       for field in atlas.coverageLayer().fields()]
                        tooltip = f"Available placeholders: {{page}}, {{index}}, " + ", ".join(
                            [f"{{{name}}}" for name in field_names[:5]]
                        )
                        if len(field_names) > 5:
                            tooltip += ", ..."
                        self.filename_edit.setToolTip(tooltip)
                    except Exception:
                        self.filename_edit.setToolTip(
                            "Available placeholders: {page}, {index}")

                self.update_preview_info()

            elif is_enabled and not has_coverage_layer:
                self.atlas_info_label.setText(
                    "Atlas: Enabled but no coverage layer set")
                self.enable_atlas_btn.setText("Disable Atlas")
                self.enable_atlas_btn.setVisible(True)
                self.preview_info.setPlainText(
                    "Atlas enabled but no coverage layer configured.")
                self.preview_label.setText(
                    "Atlas enabled but no coverage layer configured.")

            else:
                # Regular layout (no atlas)
                self.atlas_info_label.setText(
                    "Regular Layout: No atlas configuration")
                self.enable_atlas_btn.setVisible(False)
                self.preview_info.setPlainText(
                    f"Regular layout: {layout.name()}\nSingle page export available")
                self.preview_label.setText(
                    "Regular layout\n(single page export)")
                self.single_radio.setChecked(True)
                self.update_preview_info()

    def update_export_mode_visibility(self):
        """Update visibility of export mode options based on layout type"""
        if self.is_atlas_layout:
            self.all_radio.setText("Export All Atlas Pages")
            self.custom_radio.setText("Export Custom Atlas Pages")
            self.single_radio.setText(
                "Export Single Page (Disabled for Atlas)")

            # Disable single page option for atlas layouts
            self.single_radio.setEnabled(False)

            # If single page was selected, switch to "All Pages"
            if self.single_radio.isChecked():
                self.all_radio.setChecked(True)

            self.all_radio.setEnabled(True)
            self.custom_radio.setEnabled(True)
        else:
            self.all_radio.setText("Export All Pages (N/A)")
            self.custom_radio.setText("Export Custom Pages (N/A)")
            self.single_radio.setText("Export Single Layout")

            # Enable single page option for regular layouts
            self.single_radio.setEnabled(True)

            self.all_radio.setEnabled(False)
            self.custom_radio.setEnabled(False)
            self.single_radio.setChecked(True)

        self.custom_pages_edit.setEnabled(
            self.is_atlas_layout and self.custom_radio.isChecked())

    def toggle_atlas(self):
        """FIXED: Toggle atlas enabled/disabled state with better refresh"""
        if not self.current_layout:
            return
        atlas = self.current_layout.atlas()

        if atlas.enabled():
            atlas.setEnabled(False)
            self.log_text.append("Atlas disabled")
        else:
            if atlas.coverageLayer():
                atlas.setEnabled(True)
                # FIXED: Force refresh after enabling
                try:
                    atlas.refresh()
                except Exception:
                    pass
                self.log_text.append(
                    f"Atlas enabled with coverage layer: {atlas.coverageLayer().name()}")
            else:
                QMessageBox.warning(
                    self, "Warning",
                    "Cannot enable atlas: No coverage layer configured.\n"
                    "Please configure the atlas coverage layer in the layout settings first."
                )
                return

        # FIXED: Force layout refresh after atlas toggle
        self.on_layout_changed(self.current_layout.name())

    def update_preview_info(self):
        """Update the layout preview information and image"""
        if not self.current_layout:
            return

        page_index = self.preview_page_spin.value() - 1
        preview_text = SimplePreviewGenerator.generate_preview_info(
            self.current_layout, page_index, self.is_atlas_layout)

        # Add current format settings summary
        fmt = self.format_combo.currentText().upper()
        settings_info = f"\nExport Format: {fmt}\n"

        if fmt in ("PDF", "SVG"):
            settings_info += f"Export as vectors: {'Yes' if self.force_vector_check.isChecked() else 'No'}\n"
            settings_info += f"Rasterize layout: {'Yes' if self.rasterize_check.isChecked() else 'No'}\n"
            settings_info += f"Text export: {self.text_export_combo.currentText()}\n"
            if fmt == "PDF":
                settings_info += f"PDF compression: {self.pdf_compress_combo.currentText()}\n"
                if self.pdf_compress_combo.currentText().lower().startswith("lossy"):
                    settings_info += f"JPEG quality: {self.pdf_jpeg_quality.value()}\n"
        else:
            settings_info += f"DPI: {self.dpi_spin.value()}\n"
            if fmt == "JPG":
                settings_info += f"Quality: {self.quality_slider.value()}%\n"
            elif fmt in ("PNG", "TIFF"):
                settings_info += f"Compression: {self.png_tiff_comp.value()}\n"

        self.preview_info.setPlainText(preview_text + settings_info)

        # Update preview image
        if "error" not in preview_text.lower():
            self.update_preview_image()

    def update_preview_image(self):
        """Update the preview image"""
        if not self.current_layout or not self.preview_checkbox.isChecked():
            return

        page_index = self.preview_page_spin.value() - 1
        pixmap = SimplePreviewGenerator.generate_simple_preview_image(
            self.current_layout, page_index, self.is_atlas_layout
        )
        if not pixmap.isNull():
            target_size = self.preview_label.size() - QSize(20, 20)
            scaled_pixmap = pixmap.scaled(
                target_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.preview_label.setPixmap(scaled_pixmap)
            self.preview_label.setAlignment(Qt.AlignCenter)
        else:
            self.preview_label.setText("Could not generate preview image")

    def on_format_changed(self, format_name: str):
        """Handle format change"""
        is_raster = format_name in ["PNG", "JPG", "TIFF"]
        self.dpi_spin.setEnabled(is_raster)
        self.quality_slider.setEnabled(format_name == "JPG")
        self.width_spin.setEnabled(is_raster)
        self.height_spin.setEnabled(is_raster)
        self.update_preview_info()

    def browse_output_dir(self):
        """Browse for output directory"""
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Output Directory")
        if dir_path:
            self.output_dir_edit.setText(dir_path)

    def preview_export(self):
        """Preview the export settings"""
        if not self.current_layout:
            QMessageBox.warning(self, "Warning", "Please select a layout")
            return

        settings = self.get_export_settings()
        if not settings:
            return

        if settings.is_atlas_layout:
            atlas = self.current_layout.atlas()
            if not atlas.enabled():
                QMessageBox.warning(
                    self, "Warning", "Atlas is not enabled. Enable it first to see export preview.")
                return

            worker = AtlasExportWorker(self.current_layout, settings)
            pages = worker._get_pages_to_export(atlas)

            preview_text = f"""Export Preview:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Layout: {self.current_layout.name()} (Atlas Mode)
Coverage Layer: {atlas.coverageLayer().name()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Export Mode: {settings.export_mode.value.upper()}
Pages to export: {len(pages)} pages
"""
            if len(pages) <= 20:
                preview_text += f"Page numbers: {', '.join(map(lambda p: str(p+1), pages))}\n"
            else:
                first_10 = ', '.join(map(lambda p: str(p+1), pages[:10]))
                last_10 = ', '.join(map(lambda p: str(p+1), pages[-10:]))
                preview_text += f"Page numbers: {first_10} ... {last_10}\n"
        else:
            preview_text = f"""Export Preview:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Layout: {self.current_layout.name()} (Single Layout Mode)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Export Mode: SINGLE LAYOUT
Pages to export: 1 page
"""

        preview_text += f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Output Settings:
  Directory: {settings.output_dir}
  Format: {settings.export_format.value.upper()}
  Filename pattern: {settings.filename_pattern}
  DPI: {settings.dpi}
  JPG Quality: {settings.quality}%
"""
        if settings.width and settings.height:
            preview_text += f"  Custom size: {settings.width} × {settings.height} px\n"

        # Advanced section
        fmt = settings.export_format.value.upper()
        if fmt in ("PDF", "SVG"):
            preview_text += "Advanced (Vector/Text):\n"
            preview_text += f"  Export as vectors: {'Yes' if settings.force_vector else 'No'}\n"
            preview_text += f"  Rasterize whole layout: {'Yes' if settings.rasterize_whole else 'No'}\n"
            preview_text += f"  Text export: {settings.text_render}\n"
            if fmt == "PDF":
                preview_text += f"  PDF compression: {settings.pdf_image_compression}\n"
                if settings.pdf_image_compression.lower().startswith("lossy"):
                    preview_text += f"  PDF JPEG quality: {settings.pdf_jpeg_quality}\n"
        else:
            if fmt in ("PNG", "TIFF"):
                preview_text += f"PNG/TIFF compression level: {settings.png_tiff_compression}\n"

        preview_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

        if settings.is_atlas_layout:
            preview_text += "Sample filenames (first 3 pages):"
            try:
                atlas = self.current_layout.atlas()
                coverage_layer = atlas.coverageLayer()
                # FIXED: Use safe feature retrieval
                for i, page_idx in enumerate(pages[:3]):
                    filename = settings.filename_pattern
                    filename = filename.replace(
                        "{page}", str(page_idx + 1).zfill(3))
                    filename = filename.replace("{index}", str(page_idx))

                    feature = SimplePreviewGenerator._get_safe_feature_at_index(
                        coverage_layer, page_idx)
                    if feature and feature.isValid() and coverage_layer:
                        for field in coverage_layer.fields():
                            placeholder = "{" + field.name() + "}"
                            if placeholder in filename:
                                try:
                                    value = str(feature[field.name()])
                                    value = "".join(
                                        c for c in value if c.isalnum() or c in "._- ")
                                    filename = filename.replace(
                                        placeholder, value)
                                except Exception:
                                    filename = filename.replace(
                                        placeholder, "error")

                    filename += f".{settings.export_format.value}"
                    preview_text += f"\n  Page {page_idx + 1}: {filename}"
            except Exception as e:
                preview_text += f"\n  Error generating sample filenames: {str(e)}"
        else:
            filename = settings.filename_pattern
            filename = filename.replace("{page}", "001")
            filename = filename.replace("{index}", "0")
            filename += f".{settings.export_format.value}"
            preview_text += f"Output filename: {filename}"

        preview_text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

        self.log_text.setPlainText(preview_text)

    def get_export_settings(self) -> Optional[ExportSettings]:
        """Get current export settings"""
        output_dir = self.output_dir_edit.text().strip()
        if not output_dir:
            QMessageBox.warning(
                self, "Warning", "Please specify an output directory")
            return None

        mode_id = self.mode_group.checkedId()

        # UPDATED: Prevent single mode for atlas layouts
        if mode_id == 2 and self.is_atlas_layout:
            QMessageBox.warning(
                self, "Warning", "Single page export is not available for atlas layouts. Please select 'All Pages' or 'Custom Pages'.")
            return None

        if mode_id == 2 or not self.is_atlas_layout:
            export_mode = ExportMode.SINGLE
            custom_pages = []
        elif mode_id == 0:
            export_mode = ExportMode.ALL
            custom_pages = []
        else:
            export_mode = ExportMode.CUSTOM
            try:
                custom_text = self.custom_pages_edit.text().strip()
                if not custom_text:
                    QMessageBox.warning(
                        self, "Warning", "Please specify pages to export in custom mode")
                    return None
                custom_pages = []
                for part in custom_text.split(','):
                    part = part.strip()
                    if '-' in part:
                        start, end = map(int, part.split('-'))
                        custom_pages.extend(range(start, end + 1))
                    else:
                        custom_pages.append(int(part))
            except ValueError:
                QMessageBox.warning(
                    self, "Warning", "Invalid custom pages format. Use: 1,3,5-8,10")
                return None

        fmt = ExportFormat(self.format_combo.currentText().lower())

        settings = ExportSettings(
            output_dir=output_dir,
            filename_pattern=self.filename_edit.text(),
            export_format=fmt,
            export_mode=export_mode,
            custom_pages=custom_pages,
            dpi=self.dpi_spin.value(),
            quality=self.quality_slider.value(),
            width=self.width_spin.value() if self.width_spin.value() > 0 else None,
            height=self.height_spin.value() if self.height_spin.value() > 0 else None,
            include_metadata=self.metadata_check.isChecked(),
            create_subdirs=self.subdir_check.isChecked(),
            is_atlas_layout=self.is_atlas_layout,
            force_vector=self.force_vector_check.isChecked(),
            rasterize_whole=self.rasterize_check.isChecked(),
            text_render=self.text_export_combo.currentText(),
            pdf_image_compression=self.pdf_compress_combo.currentText(),
            pdf_jpeg_quality=self.pdf_jpeg_quality.value(),
            png_tiff_compression=self.png_tiff_comp.value()
        )
        return settings

    def start_export(self):
        """Start the export process"""
        if not self.current_layout:
            QMessageBox.warning(self, "Warning", "Please select a layout")
            return

        settings = self.get_export_settings()
        if not settings:
            return

        if settings.is_atlas_layout:
            atlas = self.current_layout.atlas()
            if not atlas.enabled():
                QMessageBox.warning(
                    self, "Warning", "Atlas is not enabled in the selected layout")
                return

        self.reset_export_ui_state(True)

        self.log_text.clear()
        if settings.is_atlas_layout:
            self.log_text.append("Starting atlas export...")
        else:
            self.log_text.append("Starting layout export...")

        self.export_worker = AtlasExportWorker(self.current_layout, settings)
        self.export_worker.progress_updated.connect(self.on_progress_updated)
        self.export_worker.page_exported.connect(self.on_page_exported)
        self.export_worker.export_finished.connect(self.on_export_finished)
        self.export_worker.start()

    def reset_export_ui_state(self, exporting: bool):
        """Reset UI state for export operations"""
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
            self.cancel_btn.setEnabled(True)
            self.progress_bar.setVisible(False)
            self.progress_bar.setValue(0)

    def cancel_export(self):
        """Cancel the export process"""
        if self.export_worker:
            self.export_worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.cancel_btn.setText("Cancelling...")
            self.log_text.append("Cancelling export...")

    def on_progress_updated(self, progress: int, message: str):
        """Handle progress update"""
        self.progress_bar.setValue(progress)

    def on_page_exported(self, page_num: int, filename: str):
        """Handle page export completion"""
        self.log_text.append(f"Exported page {page_num}: {filename}")

    def on_export_finished(self, success: bool, message: str):
        """Handle export completion"""
        self.reset_export_ui_state(False)

        if success:
            self.log_text.append(f"✓ {message}")
            QMessageBox.information(self, "Export Complete", message)
        else:
            self.log_text.append(f"✗ {message}")
            if "cancel" in message.lower():
                QMessageBox.information(self, "Export Cancelled", message)
            else:
                QMessageBox.warning(self, "Export Failed", message)

        if self.export_worker:
            self.export_worker.deleteLater()
        self.export_worker = None


def show_atlas_export_dialog():
    """Show the Enhanced Atlas Export Dialog"""
    dialog = EnhancedAtlasExportDialog(iface.mainWindow())
    dialog.show()
    return dialog


# Plugin entry point
# show_atlas_export_dialog()

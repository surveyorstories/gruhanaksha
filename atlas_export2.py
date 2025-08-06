# enhanced_atlas_export_dialog.py - Complete Refactored Version

from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Tuple
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QSplitter,
    QScrollArea, QFrame, QGroupBox, QLabel, QComboBox, QPushButton,
    QRadioButton, QButtonGroup, QLineEdit, QSpinBox, QSlider,
    QCheckBox, QTextEdit, QProgressBar, QMessageBox, QFileDialog,
    QWidget, QSizePolicy
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import QSize
from qgis.core import QgsProject
from qgis.utils import iface

# ===== DATA MODELS =====


class ExportFormat(Enum):
    PDF = "pdf"
    PNG = "png"
    JPG = "jpg"
    TIFF = "tiff"
    SVG = "svg"


class ExportMode(Enum):
    SINGLE = "single"
    ALL = "all"
    CUSTOM = "custom"


@dataclass
class ExportSettings:
    output_dir: str
    filename_pattern: str
    export_format: ExportFormat
    export_mode: ExportMode
    custom_pages: List[int]
    dpi: int = 300
    quality: int = 95
    width: Optional[int] = None
    height: Optional[int] = None
    include_metadata: bool = False
    create_subdirs: bool = False
    is_atlas_layout: bool = False
    force_vector: bool = True
    rasterize_whole: bool = False
    text_render: str = "Always outlines"
    pdf_image_compression: str = "Lossless/None"
    pdf_jpeg_quality: int = 90
    png_tiff_compression: int = 6


# ===== UI COMPONENTS FACTORY =====
class UIComponentsFactory:
    """Factory class for creating UI components"""

    @staticmethod
    def create_layout_selection_group(dialog) -> QGroupBox:
        """Create layout selection group"""
        group = QGroupBox("Layout Selection")
        layout = QGridLayout(group)
        layout.setSpacing(4)

        layout.addWidget(QLabel("Print Layout:"), 0, 0)
        dialog.layout_combo = QComboBox()
        dialog.layout_combo.currentTextChanged.connect(
            dialog.on_layout_changed)
        layout.addWidget(dialog.layout_combo, 0, 1)

        dialog.enable_atlas_btn = QPushButton("Enable Atlas")
        dialog.enable_atlas_btn.clicked.connect(dialog.toggle_atlas)
        dialog.enable_atlas_btn.setVisible(False)
        dialog.enable_atlas_btn.setMaximumWidth(120)
        layout.addWidget(dialog.enable_atlas_btn, 0, 2)

        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 0)

        dialog.atlas_info_label = QLabel("Atlas: Not enabled")
        dialog.atlas_info_label.setWordWrap(True)
        layout.addWidget(dialog.atlas_info_label, 1, 0, 1, 3)

        return group

    @staticmethod
    def create_export_mode_group(dialog) -> QGroupBox:
        """Create export mode selection group"""
        group = QGroupBox("Export Mode")
        layout = QVBoxLayout(group)
        layout.setSpacing(4)

        dialog.mode_group = QButtonGroup()
        dialog.single_radio = QRadioButton("Export Single Layout")
        dialog.all_radio = QRadioButton("Export All Pages")
        dialog.custom_radio = QRadioButton("Export Custom Pages")
        dialog.all_radio.setChecked(True)

        dialog.mode_group.addButton(dialog.all_radio, 0)
        dialog.mode_group.addButton(dialog.custom_radio, 1)
        dialog.mode_group.addButton(dialog.single_radio, 2)

        for radio in [dialog.single_radio, dialog.all_radio, dialog.custom_radio]:
            layout.addWidget(radio)

        # Custom pages input
        custom_layout = QHBoxLayout()
        custom_layout.setSpacing(4)
        custom_layout.addWidget(QLabel("Pages:"))
        dialog.custom_pages_edit = QLineEdit()
        dialog.custom_pages_edit.setPlaceholderText(
            "Examples: 1,3,5 or 1-5,8,10-12")
        custom_layout.addWidget(dialog.custom_pages_edit)
        layout.addLayout(custom_layout)

        dialog.custom_radio.toggled.connect(
            lambda checked: dialog.custom_pages_edit.setEnabled(
                checked and dialog.is_atlas_layout))

        return group

    @staticmethod
    def create_output_settings_group(dialog) -> QGroupBox:
        """Create output settings group"""
        group = QGroupBox("Output Settings")
        layout = QGridLayout(group)
        layout.setSpacing(4)

        layout.addWidget(QLabel("Output Directory:"), 0, 0)
        dialog.output_dir_edit = QLineEdit()
        layout.addWidget(dialog.output_dir_edit, 0, 1)

        dialog.browse_btn = QPushButton("Browse...")
        dialog.browse_btn.clicked.connect(dialog.browse_output_dir)
        dialog.browse_btn.setMaximumWidth(80)
        layout.addWidget(dialog.browse_btn, 0, 2)

        layout.addWidget(QLabel("Filename Pattern:"), 1, 0)
        dialog.filename_edit = QLineEdit("atlas_{page}")
        dialog.filename_edit.setToolTip(
            "Available placeholders: {page}, {index}, {field_name}")
        layout.addWidget(dialog.filename_edit, 1, 1, 1, 2)

        layout.addWidget(QLabel("Format:"), 2, 0)
        dialog.format_combo = QComboBox()
        dialog.format_combo.addItems(["PDF", "PNG", "JPG", "TIFF", "SVG"])
        dialog.format_combo.currentTextChanged.connect(
            dialog.on_format_changed)
        layout.addWidget(dialog.format_combo, 2, 1)

        return group

    @staticmethod
    def create_quality_settings_group(dialog) -> QGroupBox:
        """Create quality settings group"""
        group = QGroupBox("Quality Settings")
        layout = QGridLayout(group)
        layout.setSpacing(4)

        # DPI
        layout.addWidget(QLabel("DPI:"), 0, 0)
        dialog.dpi_spin = QSpinBox()
        dialog.dpi_spin.setRange(72, 1200)
        dialog.dpi_spin.setValue(300)
        dialog.dpi_spin.setMaximumWidth(80)
        layout.addWidget(dialog.dpi_spin, 0, 1)

        # JPG Quality
        layout.addWidget(QLabel("JPG Quality:"), 0, 2)
        dialog.quality_slider = QSlider(Qt.Horizontal)
        dialog.quality_slider.setRange(1, 100)
        dialog.quality_slider.setValue(95)
        layout.addWidget(dialog.quality_slider, 0, 3)

        dialog.quality_label = QLabel("95%")
        dialog.quality_label.setMinimumWidth(35)
        dialog.quality_slider.valueChanged.connect(
            lambda v: dialog.quality_label.setText(f"{v}%"))
        layout.addWidget(dialog.quality_label, 0, 4)

        # Dimensions
        layout.addWidget(QLabel("Width (px):"), 1, 0)
        dialog.width_spin = QSpinBox()
        dialog.width_spin.setRange(0, 20000)
        dialog.width_spin.setSpecialValueText("Auto")
        dialog.width_spin.setMaximumWidth(80)
        layout.addWidget(dialog.width_spin, 1, 1)

        layout.addWidget(QLabel("Height (px):"), 1, 2)
        dialog.height_spin = QSpinBox()
        dialog.height_spin.setRange(0, 20000)
        dialog.height_spin.setSpecialValueText("Auto")
        dialog.height_spin.setMaximumWidth(80)
        layout.addWidget(dialog.height_spin, 1, 3)

        # PNG/TIFF compression
        dialog.png_tiff_comp_label = QLabel("PNG/TIFF compression:")
        layout.addWidget(dialog.png_tiff_comp_label, 2, 0)

        dialog.png_tiff_comp = QSlider(Qt.Horizontal)
        dialog.png_tiff_comp.setRange(0, 9)
        dialog.png_tiff_comp.setValue(6)
        layout.addWidget(dialog.png_tiff_comp, 2, 1, 1, 3)

        dialog.png_tiff_comp_value = QLabel("6")
        dialog.png_tiff_comp_value.setMinimumWidth(25)
        dialog.png_tiff_comp.valueChanged.connect(
            lambda v: dialog.png_tiff_comp_value.setText(str(v)))
        layout.addWidget(dialog.png_tiff_comp_value, 2, 4)

        return group

    @staticmethod
    def create_advanced_options_group(dialog) -> QGroupBox:
        """Create advanced options group"""
        group = QGroupBox("Advanced Options")
        layout = QGridLayout(group)
        layout.setSpacing(4)

        # Basic checkboxes
        dialog.metadata_check = QCheckBox("Include Metadata")
        layout.addWidget(dialog.metadata_check, 0, 0)

        dialog.subdir_check = QCheckBox("Create Subdirectories")
        layout.addWidget(dialog.subdir_check, 0, 1)

        # Vector/rasterization toggles
        dialog.force_vector_check = QCheckBox("Export as vectors")
        dialog.force_vector_check.setChecked(True)
        dialog.rasterize_check = QCheckBox("Rasterize whole layout")

        # Make them mutually exclusive
        dialog.force_vector_check.toggled.connect(
            lambda v: dialog.rasterize_check.setChecked(False) if v else None)
        dialog.rasterize_check.toggled.connect(
            lambda v: dialog.force_vector_check.setChecked(False) if v else None)

        layout.addWidget(dialog.force_vector_check, 1, 0)
        layout.addWidget(dialog.rasterize_check, 1, 1)

        # Text export
        dialog.text_export_label = QLabel("Text export:")
        layout.addWidget(dialog.text_export_label, 2, 0)
        dialog.text_export_combo = QComboBox()
        dialog.text_export_combo.addItems(["Always outlines", "Always text"])
        layout.addWidget(dialog.text_export_combo, 2, 1)

        # PDF compression
        dialog.pdf_compress_label = QLabel("PDF compression:")
        layout.addWidget(dialog.pdf_compress_label, 3, 0)
        dialog.pdf_compress_combo = QComboBox()
        dialog.pdf_compress_combo.addItems(["Lossless/None", "Lossy (JPEG)"])
        layout.addWidget(dialog.pdf_compress_combo, 3, 1)

        # PDF JPEG quality
        dialog.pdf_jpeg_quality_label = QLabel("PDF JPEG quality:")
        layout.addWidget(dialog.pdf_jpeg_quality_label, 4, 0)
        dialog.pdf_jpeg_quality = QSlider(Qt.Horizontal)
        dialog.pdf_jpeg_quality.setRange(1, 100)
        dialog.pdf_jpeg_quality.setValue(90)
        layout.addWidget(dialog.pdf_jpeg_quality, 4, 1)
        dialog.pdf_jpeg_quality_value = QLabel("90")
        dialog.pdf_jpeg_quality_value.setMinimumWidth(25)
        dialog.pdf_jpeg_quality.valueChanged.connect(
            lambda v: dialog.pdf_jpeg_quality_value.setText(str(v)))
        layout.addWidget(dialog.pdf_jpeg_quality_value, 4, 2)

        return group

    @staticmethod
    def create_preview_panel(dialog) -> QFrame:
        """Create preview panel"""
        panel = QFrame()
        layout = QVBoxLayout(panel)
        layout.setSpacing(6)

        # Preview group
        preview_group = QGroupBox("Layout Preview")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setSpacing(4)

        dialog.preview_checkbox = QCheckBox("Enable Preview Rendering")
        dialog.preview_checkbox.setChecked(False)
        preview_layout.addWidget(dialog.preview_checkbox)

        # Preview controls container
        dialog.preview_container = QWidget()
        container_layout = QVBoxLayout(dialog.preview_container)
        container_layout.setSpacing(4)
        container_layout.setContentsMargins(0, 0, 0, 0)

        # Preview controls
        controls = QHBoxLayout()
        controls.setSpacing(4)
        controls.addWidget(QLabel("Page:"))

        dialog.preview_page_spin = QSpinBox()
        dialog.preview_page_spin.setMinimum(1)
        dialog.preview_page_spin.setValue(1)
        dialog.preview_page_spin.setMaximumWidth(70)
        dialog.preview_page_spin.valueChanged.connect(
            dialog.update_preview_info)
        controls.addWidget(dialog.preview_page_spin)

        dialog.refresh_preview_btn = QPushButton("Refresh")
        dialog.refresh_preview_btn.clicked.connect(dialog.update_preview_info)
        dialog.refresh_preview_btn.setMaximumWidth(70)
        dialog.refresh_preview_btn.setMaximumHeight(28)
        controls.addWidget(dialog.refresh_preview_btn)
        controls.addStretch()

        container_layout.addLayout(controls)

        # Preview image
        dialog.preview_label = QLabel("Select a layout")
        dialog.preview_label.setAlignment(Qt.AlignCenter)
        dialog.preview_label.setMinimumHeight(200)
        dialog.preview_label.setStyleSheet(
            "border: 1px solid gray; background-color: white; padding: 5px;")
        dialog.preview_label.setScaledContents(False)
        dialog.preview_label.setWordWrap(True)
        container_layout.addWidget(dialog.preview_label)

        preview_layout.addWidget(dialog.preview_container)

        # Preview info (always visible)
        dialog.preview_info = QTextEdit()
        dialog.preview_info.setMinimumHeight(120)
        dialog.preview_info.setReadOnly(True)
        dialog.preview_info.setPlainText("Select a layout")
        preview_layout.addWidget(dialog.preview_info)

        dialog.preview_checkbox.toggled.connect(
            dialog.preview_container.setVisible)
        dialog.preview_checkbox.toggled.connect(
            lambda checked: dialog.update_preview_info() if checked else None)
        dialog.preview_container.setVisible(False)

        layout.addWidget(preview_group)

        # Log group
        log_group = QGroupBox("Export Log")
        log_layout = QVBoxLayout(log_group)
        log_layout.setSpacing(4)
        dialog.log_text = QTextEdit()
        dialog.log_text.setMinimumHeight(100)
        dialog.log_text.setReadOnly(True)
        log_layout.addWidget(dialog.log_text)
        layout.addWidget(log_group)

        return panel


# ===== ATLAS MANAGER =====
class AtlasManager:
    """Handles atlas-specific operations"""

    @staticmethod
    def get_atlas_info(layout) -> dict:
        """Get comprehensive atlas information"""
        atlas = layout.atlas()
        coverage_layer = atlas.coverageLayer()

        info = {
            'has_coverage_layer': coverage_layer is not None,
            'is_enabled': atlas.enabled(),
            'layer_name': coverage_layer.name() if coverage_layer else None,
            'feature_count': 0
        }

        if coverage_layer:
            try:
                atlas.refresh()
                # Use safe feature count method (assuming it exists)
                if hasattr(SimplePreviewGenerator, '_get_safe_feature_count'):
                    info['feature_count'] = SimplePreviewGenerator._get_safe_feature_count(
                        atlas, coverage_layer)
                else:
                    info['feature_count'] = coverage_layer.featureCount()
            except Exception:
                info['feature_count'] = coverage_layer.featureCount()

        return info

    @staticmethod
    def toggle_atlas_state(layout) -> Tuple[bool, str]:
        """Toggle atlas enabled state"""
        atlas = layout.atlas()

        if atlas.enabled():
            atlas.setEnabled(False)
            return True, "Atlas disabled"
        else:
            if atlas.coverageLayer():
                atlas.setEnabled(True)
                try:
                    atlas.refresh()
                except Exception:
                    pass
                return True, f"Atlas enabled with coverage layer: {atlas.coverageLayer().name()}"
            else:
                return False, "Cannot enable atlas: No coverage layer configured.\nPlease configure the atlas coverage layer in the layout settings first."

    @staticmethod
    def update_field_placeholders(layout, filename_edit):
        """Update filename field placeholders tooltip"""
        atlas = layout.atlas()
        coverage_layer = atlas.coverageLayer()

        if coverage_layer and coverage_layer.fields():
            try:
                field_names = [field.name()
                               for field in coverage_layer.fields()]
                tooltip = "Available placeholders: {page}, {index}, " + ", ".join(
                    [f"{{{name}}}" for name in field_names[:5]])
                if len(field_names) > 5:
                    tooltip += ", ..."
                filename_edit.setToolTip(tooltip)
            except Exception:
                filename_edit.setToolTip(
                    "Available placeholders: {page}, {index}")


# ===== FORMAT MANAGER =====
class FormatManager:
    """Manages format-specific UI updates"""

    @staticmethod
    def update_format_controls(dialog):
        """Update UI controls based on selected format"""
        fmt = dialog.format_combo.currentText().upper()
        is_pdf = fmt == "PDF"
        is_svg = fmt == "SVG"
        is_raster = fmt in ("PNG", "JPG", "TIFF")

        # PDF-specific controls
        dialog.pdf_compress_label.setVisible(is_pdf)
        dialog.pdf_compress_combo.setVisible(is_pdf)

        lossy = dialog.pdf_compress_combo.currentText().lower().startswith("lossy")
        dialog.pdf_jpeg_quality_label.setVisible(is_pdf and lossy)
        dialog.pdf_jpeg_quality.setVisible(is_pdf and lossy)
        dialog.pdf_jpeg_quality_value.setVisible(is_pdf and lossy)

        # Vector/text controls for PDF and SVG
        for widget in [dialog.force_vector_check, dialog.rasterize_check,
                       dialog.text_export_label, dialog.text_export_combo]:
            widget.setVisible(is_pdf or is_svg)

        # PNG/TIFF compression
        show_png_tiff = fmt in ("PNG", "TIFF")
        dialog.png_tiff_comp.setVisible(show_png_tiff)
        dialog.png_tiff_comp_label.setVisible(show_png_tiff)
        dialog.png_tiff_comp_value.setVisible(show_png_tiff)

        # Enable/disable controls based on format
        dialog.dpi_spin.setEnabled(is_raster)
        dialog.quality_slider.setEnabled(fmt == "JPG")
        dialog.width_spin.setEnabled(is_raster)
        dialog.height_spin.setEnabled(is_raster)


# ===== EXPORT PREVIEW GENERATOR =====
class ExportPreviewGenerator:
    """Generates export preview text"""

    @staticmethod
    def generate_preview_text(layout, settings: ExportSettings) -> str:
        """Generate export preview text"""
        if settings.is_atlas_layout:
            return ExportPreviewGenerator._generate_atlas_preview(layout, settings)
        else:
            return ExportPreviewGenerator._generate_single_preview(layout, settings)

    @staticmethod
    def _generate_atlas_preview(layout, settings: ExportSettings) -> str:
        """Generate atlas export preview"""
        atlas = layout.atlas()
        # Note: AtlasExportWorker would need to be imported or defined elsewhere
        # For now, we'll create a simplified version
        try:
            pages = ExportPreviewGenerator._get_pages_to_export(
                atlas, settings)
        except:
            pages = list(
                range(atlas.count() if hasattr(atlas, 'count') else 0))

        preview_text = f"""Export Preview:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Layout: {layout.name()} (Atlas Mode)
Coverage Layer: {atlas.coverageLayer().name()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Export Mode: {settings.export_mode.value.upper()}
Pages to export: {len(pages)} pages
"""

        if len(pages) <= 20:
            page_numbers = ', '.join(str(p + 1) for p in pages)
            preview_text += f"Page numbers: {page_numbers}\n"
        else:
            first_10 = ', '.join(str(p + 1) for p in pages[:10])
            last_10 = ', '.join(str(p + 1) for p in pages[-10:])
            preview_text += f"Page numbers: {first_10} ... {last_10}\n"

        preview_text += ExportPreviewGenerator._generate_common_settings(
            settings)
        preview_text += ExportPreviewGenerator._generate_atlas_filenames(
            layout, settings, pages)

        return preview_text

    @staticmethod
    def _generate_single_preview(layout, settings: ExportSettings) -> str:
        """Generate single layout export preview"""
        preview_text = f"""Export Preview:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Layout: {layout.name()} (Single Layout Mode)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Export Mode: SINGLE LAYOUT
Pages to export: 1 page
"""

        preview_text += ExportPreviewGenerator._generate_common_settings(
            settings)

        filename = settings.filename_pattern
        filename = filename.replace("{page}", "001")
        filename = filename.replace("{index}", "0")
        filename += f".{settings.export_format.value}"
        preview_text += f"Output filename: {filename}"
        preview_text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

        return preview_text

    @staticmethod
    def _generate_common_settings(settings: ExportSettings) -> str:
        """Generate common settings section"""
        text = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Output Settings:
  Directory: {settings.output_dir}
  Format: {settings.export_format.value.upper()}
  Filename pattern: {settings.filename_pattern}
  DPI: {settings.dpi}
  JPG Quality: {settings.quality}%
"""

        if settings.width and settings.height:
            text += f"  Custom size: {settings.width} × {settings.height} px\n"

        # Format-specific settings
        fmt = settings.export_format.value.upper()
        if fmt in ("PDF", "SVG"):
            text += "Advanced (Vector/Text):\n"
            text += f"  Export as vectors: {'Yes' if settings.force_vector else 'No'}\n"
            text += f"  Rasterize whole layout: {'Yes' if settings.rasterize_whole else 'No'}\n"
            text += f"  Text export: {settings.text_render}\n"
            if fmt == "PDF":
                text += f"  PDF compression: {settings.pdf_image_compression}\n"
                if settings.pdf_image_compression.lower().startswith("lossy"):
                    text += f"  PDF JPEG quality: {settings.pdf_jpeg_quality}\n"
        else:
            if fmt in ("PNG", "TIFF"):
                text += f"PNG/TIFF compression level: {settings.png_tiff_compression}\n"

        text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        return text

    @staticmethod
    def _generate_atlas_filenames(layout, settings: ExportSettings, pages: List[int]) -> str:
        """Generate sample atlas filenames"""
        text = "Sample filenames (first 3 pages):"

        try:
            atlas = layout.atlas()
            coverage_layer = atlas.coverageLayer()

            for i, page_idx in enumerate(pages[:3]):
                filename = settings.filename_pattern
                filename = filename.replace(
                    "{page}", str(page_idx + 1).zfill(3))
                filename = filename.replace("{index}", str(page_idx))

                # Add field values if available
                try:
                    if hasattr(SimplePreviewGenerator, '_get_safe_feature_at_index'):
                        feature = SimplePreviewGenerator._get_safe_feature_at_index(
                            coverage_layer, page_idx)
                    else:
                        # Fallback method
                        features = list(coverage_layer.getFeatures())
                        feature = features[page_idx] if page_idx < len(
                            features) else None

                    if feature and feature.isValid() and coverage_layer:
                        for field in coverage_layer.fields():
                            placeholder = "{" + field.name() + "}"
                            if placeholder in filename:
                                try:
                                    value = str(feature[field.name()])
                                    # Sanitize filename
                                    value = "".join(
                                        c for c in value if c.isalnum() or c in "._- ")
                                    filename = filename.replace(
                                        placeholder, value)
                                except Exception:
                                    filename = filename.replace(
                                        placeholder, "error")
                except Exception:
                    pass

                filename += f".{settings.export_format.value}"
                text += f"\n  Page {page_idx + 1}: {filename}"

        except Exception as e:
            text += f"\n  Error generating sample filenames: {str(e)}"

        text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        return text

    @staticmethod
    def _get_pages_to_export(atlas, settings: ExportSettings) -> List[int]:
        """Get list of page indices to export"""
        if settings.export_mode == ExportMode.ALL:
            try:
                count = atlas.count() if hasattr(atlas, 'count') else 0
                return list(range(count))
            except:
                return []
        elif settings.export_mode == ExportMode.CUSTOM:
            # Convert to 0-based
            return [p - 1 for p in settings.custom_pages if p > 0]
        else:
            return [0]  # Single page


# ===== SETTINGS VALIDATOR =====
class SettingsValidator:
    """Validates export settings"""

    @staticmethod
    def validate_settings(settings: ExportSettings, is_atlas_layout: bool) -> Tuple[bool, str]:
        """Validate export settings"""
        if not settings.output_dir.strip():
            return False, "Please specify an output directory"

        if settings.export_mode == ExportMode.SINGLE and is_atlas_layout:
            return False, "Single page export is not available for atlas layouts. Please select 'All Pages' or 'Custom Pages'."

        if settings.export_mode == ExportMode.CUSTOM and not settings.custom_pages:
            return False, "Please specify pages to export in custom mode"

        return True, ""


# ===== MAIN DIALOG CLASS =====
class EnhancedAtlasExportDialog(QDialog):
    """Enhanced Atlas Export Dialog - Refactored Version"""

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
        """Setup the main UI structure"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # Left panel (settings) with scroll
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        left_scroll.setMinimumWidth(400)
        left_scroll.setWidget(self.create_settings_panel())
        splitter.addWidget(left_scroll)

        # Right panel (preview) with scroll
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        right_scroll.setMinimumWidth(300)
        right_scroll.setWidget(UIComponentsFactory.create_preview_panel(self))
        splitter.addWidget(right_scroll)

        splitter.setSizes([500, 300])
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(25)
        main_layout.addWidget(self.progress_bar)

        # Buttons
        self.setup_buttons(main_layout)

    def create_settings_panel(self) -> QFrame:
        """Create settings panel using UI components"""
        panel = QFrame()
        layout = QVBoxLayout(panel)
        layout.setSpacing(6)
        layout.setContentsMargins(4, 4, 4, 4)

        # Add all setting groups
        layout.addWidget(
            UIComponentsFactory.create_layout_selection_group(self))
        self.mode_group_box = UIComponentsFactory.create_export_mode_group(
            self)
        layout.addWidget(self.mode_group_box)
        layout.addWidget(
            UIComponentsFactory.create_output_settings_group(self))
        layout.addWidget(
            UIComponentsFactory.create_quality_settings_group(self))

        advanced_group = UIComponentsFactory.create_advanced_options_group(
            self)
        layout.addWidget(advanced_group)

        # Setup format change handling
        self.setup_format_handlers()

        layout.addStretch()
        return panel

    def setup_format_handlers(self):
        """Setup format-specific handlers"""
        FormatManager.update_format_controls(self)
        self.format_combo.currentTextChanged.connect(
            lambda: FormatManager.update_format_controls(self))
        self.pdf_compress_combo.currentTextChanged.connect(
            lambda: FormatManager.update_format_controls(self))

    def setup_buttons(self, main_layout):
        """Setup button layout"""
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        self.preview_btn = QPushButton("Preview")
        self.export_btn = QPushButton("Export")
        self.cancel_btn = QPushButton("Cancel")

        # Button styling
        self.export_btn.setStyleSheet("background-color: black; color: white;")
        self.preview_btn.setStyleSheet(
            "background-color: brown; color: white;")
        self.cancel_btn.setStyleSheet(
            "background-color: #aa0000; color: white;")
        self.cancel_btn.setVisible(False)

        for btn in [self.preview_btn, self.export_btn, self.cancel_btn]:
            btn.setMinimumHeight(32)
            btn.setMinimumWidth(100)

        # Button connections
        self.preview_btn.clicked.connect(self.preview_export)
        self.export_btn.clicked.connect(self.start_export)
        self.cancel_btn.clicked.connect(self.cancel_export)

        button_layout.addStretch()
        button_layout.addWidget(self.preview_btn)
        button_layout.addWidget(self.export_btn)
        button_layout.addWidget(self.cancel_btn)
        main_layout.addLayout(button_layout)

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
        """Handle layout selection change"""
        layout = self.layout_combo.currentData()
        if not layout:
            return

        self.current_layout = layout
        atlas_info = AtlasManager.get_atlas_info(layout)

        self.is_atlas_layout = atlas_info['is_enabled'] and atlas_info['has_coverage_layer']
        self.update_export_mode_visibility()
        self.update_atlas_ui(atlas_info)

        if atlas_info['has_coverage_layer'] and atlas_info['is_enabled']:
            self.preview_page_spin.setMaximum(
                max(1, atlas_info['feature_count']))
            AtlasManager.update_field_placeholders(layout, self.filename_edit)

        self.update_preview_info()

    def update_atlas_ui(self, atlas_info: dict):
        """Update atlas-related UI elements"""
        if atlas_info['has_coverage_layer'] and not atlas_info['is_enabled']:
            self.atlas_info_label.setText(
                f"Atlas: Configured but not enabled ({atlas_info['feature_count']} "
                f"features from '{atlas_info['layer_name']}')")
            self.enable_atlas_btn.setText("Enable Atlas")
            self.enable_atlas_btn.setVisible(True)
            self.preview_info.setPlainText(
                "Atlas is configured but not enabled.\nClick 'Enable Atlas' to activate it.")
            self.preview_label.setText(
                "Atlas configured but not enabled.\nClick 'Enable Atlas' to activate.")

        elif atlas_info['is_enabled'] and atlas_info['has_coverage_layer']:
            self.atlas_info_label.setText(
                f"Atlas: Enabled ({atlas_info['feature_count']} "
                f"features from '{atlas_info['layer_name']}')")
            self.enable_atlas_btn.setText("Disable Atlas")
            self.enable_atlas_btn.setVisible(True)

        elif atlas_info['is_enabled'] and not atlas_info['has_coverage_layer']:
            self.atlas_info_label.setText(
                "Atlas: Enabled but no coverage layer set")
            self.enable_atlas_btn.setText("Disable Atlas")
            self.enable_atlas_btn.setVisible(True)
            self.preview_info.setPlainText(
                "Atlas enabled but no coverage layer configured.")
            self.preview_label.setText(
                "Atlas enabled but no coverage layer configured.")

        else:
            self.atlas_info_label.setText(
                "Regular Layout: No atlas configuration")
            self.enable_atlas_btn.setVisible(False)
            self.single_radio.setChecked(True)
            self.preview_info.setPlainText(
                f"Regular layout: {self.current_layout.name()}\nSingle page export available")
            self.preview_label.setText("Regular layout\n(single page export)")

    def update_export_mode_visibility(self):
        """Update export mode options based on layout type"""
        if self.is_atlas_layout:
            self.all_radio.setText("Export All Atlas Pages")
            self.custom_radio.setText("Export Custom Atlas Pages")
            self.single_radio.setText(
                "Export Single Page (Disabled for Atlas)")
            self.single_radio.setEnabled(False)

            if self.single_radio.isChecked():
                self.all_radio.setChecked(True)

            self.all_radio.setEnabled(True)
            self.custom_radio.setEnabled(True)
        else:
            self.all_radio.setText("Export All Pages (N/A)")
            self.custom_radio.setText("Export Custom Pages (N/A)")
            self.single_radio.setText("Export Single Layout")
            self.single_radio.setEnabled(True)
            self.all_radio.setEnabled(False)
            self.custom_radio.setEnabled(False)
            self.single_radio.setChecked(True)

        self.custom_pages_edit.setEnabled(
            self.is_atlas_layout and self.custom_radio.isChecked())

    def toggle_atlas(self):
        """Toggle atlas enabled/disabled state"""
        if not self.current_layout:
            return

        success, message = AtlasManager.toggle_atlas_state(self.current_layout)
        self.log_text.append(message)

        if not success:
            QMessageBox.warning(self, "Warning", message)
            return

        self.on_layout_changed(self.current_layout.name())

    def update_preview_info(self):
        """Update preview information"""
        if not self.current_layout:
            return

        page_index = self.preview_page_spin.value() - 1

        # Generate basic preview info (you may need to implement this method)
        if hasattr(self, 'SimplePreviewGenerator'):
            preview_text = SimplePreviewGenerator.generate_preview_info(
                self.current_layout, page_index, self.is_atlas_layout)
        else:
            # Fallback preview text
            if self.is_atlas_layout:
                preview_text = f"Atlas Layout: {self.current_layout.name()}\nPage {page_index + 1}"
            else:
                preview_text = f"Regular Layout: {self.current_layout.name()}"

        # Add format settings
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

        if "error" not in preview_text.lower():
            self.update_preview_image()

    def update_preview_image(self):
        """Update preview image"""
        if not self.current_layout or not self.preview_checkbox.isChecked():
            return

        page_index = self.preview_page_spin.value() - 1

        # Generate preview image (you may need to implement this method)
        if hasattr(self, 'SimplePreviewGenerator'):
            pixmap = SimplePreviewGenerator.generate_simple_preview_image(
                self.current_layout, page_index, self.is_atlas_layout)
        else:
            # Create a placeholder pixmap
            pixmap = QPixmap(200, 150)
            pixmap.fill()

        if not pixmap.isNull():
            target_size = self.preview_label.size() - QSize(20, 20)
            scaled_pixmap = pixmap.scaled(
                target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.preview_label.setPixmap(scaled_pixmap)
            self.preview_label.setAlignment(Qt.AlignCenter)
        else:
            self.preview_label.setText("Could not generate preview image")

    def on_format_changed(self, format_name: str):
        """Handle format change"""
        FormatManager.update_format_controls(self)
        self.update_preview_info()

    def browse_output_dir(self):
        """Browse for output directory"""
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Output Directory")
        if dir_path:
            self.output_dir_edit.setText(dir_path)

    def get_export_settings(self) -> Optional[ExportSettings]:
        """Get current export settings"""
        output_dir = self.output_dir_edit.text().strip()
        if not output_dir:
            QMessageBox.warning(
                self, "Warning", "Please specify an output directory")
            return None

        mode_id = self.mode_group.checkedId()

        # Parse export mode and custom pages
        export_mode, custom_pages = self._parse_export_mode(mode_id)
        if export_mode is None:
            return None

        # Validate settings
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

        # Final validation
        is_valid, error_msg = SettingsValidator.validate_settings(
            settings, self.is_atlas_layout)
        if not is_valid:
            QMessageBox.warning(self, "Warning", error_msg)
            return None

        return settings

    def _parse_export_mode(self, mode_id: int) -> Tuple[Optional[ExportMode], List[int]]:
        """Parse export mode and custom pages"""
        if mode_id == 2 or not self.is_atlas_layout:
            return ExportMode.SINGLE, []
        elif mode_id == 0:
            return ExportMode.ALL, []
        else:  # Custom mode
            try:
                custom_text = self.custom_pages_edit.text().strip()
                if not custom_text:
                    QMessageBox.warning(
                        self, "Warning", "Please specify pages to export in custom mode")
                    return None, []

                custom_pages = []
                for part in custom_text.split(','):
                    part = part.strip()
                    if '-' in part:
                        start, end = map(int, part.split('-'))
                        custom_pages.extend(range(start, end + 1))
                    else:
                        custom_pages.append(int(part))

                return ExportMode.CUSTOM, custom_pages
            except ValueError:
                QMessageBox.warning(
                    self, "Warning", "Invalid custom pages format. Use: 1,3,5-8,10")
                return None, []

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
                    self, "Warning",
                    "Atlas is not enabled. Enable it first to see export preview.")
                return

        preview_text = ExportPreviewGenerator.generate_preview_text(
            self.current_layout, settings)
        self.log_text.setPlainText(preview_text)

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

        self._start_export_worker(settings)

    def _start_export_worker(self, settings: ExportSettings):
        """Start the export worker thread"""
        self.reset_export_ui_state(True)
        self.log_text.clear()

        if settings.is_atlas_layout:
            self.log_text.append("Starting atlas export...")
        else:
            self.log_text.append("Starting layout export...")

        # Note: AtlasExportWorker needs to be implemented separately
        # This is a placeholder for the worker initialization
        try:
            self.export_worker = AtlasExportWorker(
                self.current_layout, settings)
            self.export_worker.progress_updated.connect(
                self.on_progress_updated)
            self.export_worker.page_exported.connect(self.on_page_exported)
            self.export_worker.export_finished.connect(self.on_export_finished)
            self.export_worker.start()
        except NameError:
            # If AtlasExportWorker is not available, show a message
            QMessageBox.information(
                self, "Export Worker",
                "AtlasExportWorker class needs to be implemented separately.\n"
                "This refactored version focuses on the UI structure.")
            self.reset_export_ui_state(False)

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
            try:
                self.export_worker.cancel()
                self.cancel_btn.setEnabled(False)
                self.cancel_btn.setText("Cancelling...")
                self.log_text.append("Cancelling export...")
            except AttributeError:
                pass

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


# ===== WORKER THREAD PLACEHOLDER =====
class AtlasExportWorker(QThread):
    """
    Placeholder for the export worker thread.
    This would need to be implemented with the actual export logic.
    """
    progress_updated = pyqtSignal(int, str)
    page_exported = pyqtSignal(int, str)
    export_finished = pyqtSignal(bool, str)

    def __init__(self, layout, settings: ExportSettings):
        super().__init__()
        self.layout = layout
        self.settings = settings
        self.cancelled = False

    def cancel(self):
        """Cancel the export operation"""
        self.cancelled = True

    def run(self):
        """Run the export process"""
        try:
            # This is where the actual export logic would go
            # For now, just simulate some progress
            for i in range(101):
                if self.cancelled:
                    self.export_finished.emit(
                        False, "Export cancelled by user")
                    return

                self.progress_updated.emit(i, f"Processing... {i}%")
                self.msleep(50)  # Simulate work

            self.export_finished.emit(True, "Export completed successfully!")

        except Exception as e:
            self.export_finished.emit(False, f"Export failed: {str(e)}")


# ===== SIMPLE PREVIEW GENERATOR PLACEHOLDER =====
class SimplePreviewGenerator:
    """
    Placeholder for preview generation methods.
    These would need to be implemented with actual QGIS layout rendering.
    """

    @staticmethod
    def generate_preview_info(layout, page_index: int, is_atlas: bool) -> str:
        """Generate preview information text"""
        if is_atlas:
            return f"Atlas Layout: {layout.name()}\nPage: {page_index + 1}\nAtlas enabled"
        else:
            return f"Regular Layout: {layout.name()}\nSingle page layout"

    @staticmethod
    def generate_simple_preview_image(layout, page_index: int, is_atlas: bool) -> QPixmap:
        """Generate a simple preview image"""
        # This would contain the actual rendering logic
        pixmap = QPixmap(300, 200)
        pixmap.fill()
        return pixmap

    @staticmethod
    def _get_safe_feature_count(atlas, layer) -> int:
        """Get safe feature count"""
        try:
            return layer.featureCount()
        except:
            return 0

    @staticmethod
    def _get_safe_feature_at_index(layer, index: int):
        """Get feature at specific index safely"""
        try:
            features = list(layer.getFeatures())
            return features[index] if index < len(features) else None
        except:
            return None


# ===== USAGE =====

def show_atlas_export_dialog():
    """Show the Enhanced Atlas Export Dialog"""
    dialog = EnhancedAtlasExportDialog(iface.mainWindow())
    dialog.show()
    return dialog

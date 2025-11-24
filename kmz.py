# -*- coding: utf-8 -*-
"""
KMZ Exporter Pro – Modular, maintainable plugin for QGIS
Compatible with both Qt5 and Qt6
Features: 
- Custom/QGIS Symbology
- Multi-field Labels
- Selective Description Fields
- Dynamic Layer Settings Loading
- Standard Visual Styles
"""
import os
import zipfile
import tempfile
import shutil
import html
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
from qgis.utils import iface
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsWkbTypes, QgsCoordinateReferenceSystem,
    QgsCoordinateTransform, QgsVectorLayerSimpleLabeling
)
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal, QUrl
from qgis.PyQt.QtGui import QColor, QPalette, QDesktopServices

# ==============================================================================
# Constants & Utils
# ==============================================================================


# ==============================================================================
# Qt5/Qt6 Compatibility Layer
# ==============================================================================
try:
    from qgis.PyQt.QtCore import QT_VERSION_STR
    QT_VERSION = int(QT_VERSION_STR.split('.')[0])
except:
    QT_VERSION = 5

if QT_VERSION >= 6:
    TOOL_WINDOW_FLAGS = Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.Tool
else:
    TOOL_WINDOW_FLAGS = Qt.Window | Qt.WindowCloseButtonHint | Qt.Tool


class QtCompat:
    @staticmethod
    def checkstate(checked=True):
        if hasattr(Qt, 'CheckState'):
            return Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        else:
            return Qt.Checked if checked else Qt.Unchecked

    @staticmethod
    def user_role():
        return Qt.ItemDataRole.UserRole if QT_VERSION >= 6 else Qt.UserRole

    @staticmethod
    def item_flag(flag_name):
        return getattr(Qt.ItemFlag if QT_VERSION >= 6 else Qt, flag_name)

    @staticmethod
    def orientation(horizontal=True):
        return Qt.Orientation.Horizontal if QT_VERSION >= 6 and horizontal else (Qt.Horizontal if horizontal else Qt.Vertical)

    @staticmethod
    def text_format(rich_text=True):
        return Qt.TextFormat.RichText if QT_VERSION >= 6 and rich_text else (Qt.RichText if rich_text else Qt.PlainText)

    @staticmethod
    def cursor_shape(cursor_type='pointing'):
        return Qt.CursorShape.PointingHandCursor if QT_VERSION >= 6 and cursor_type == 'pointing' else (Qt.PointingHandCursor if cursor_type == 'pointing' else Qt.ArrowCursor)

    @staticmethod
    def size_policy(policy='minimum'):
        policies = {'minimum': QSizePolicy.Policy.Minimum,
                    'expanding': QSizePolicy.Policy.Expanding, 'fixed': QSizePolicy.Policy.Fixed}
        cls = QSizePolicy if QT_VERSION < 6 else QSizePolicy.Policy
        return policies.get(policy, cls.Minimum)

    @staticmethod
    def palette_role(role_name):
        if QT_VERSION >= 6:
            roles = {
                'window': QPalette.ColorRole.Window, 'window_text': QPalette.ColorRole.WindowText,
                'base': QPalette.ColorRole.Base, 'alternate_base': QPalette.ColorRole.AlternateBase,
                'text': QPalette.ColorRole.Text, 'button': QPalette.ColorRole.Button,
                'button_text': QPalette.ColorRole.ButtonText, 'highlight': QPalette.ColorRole.Highlight,
                'highlighted_text': QPalette.ColorRole.HighlightedText
            }
            return roles.get(role_name)
        roles = {
            'window': QPalette.Window, 'window_text': QPalette.WindowText, 'base': QPalette.Base,
            'alternate_base': QPalette.AlternateBase, 'text': QPalette.Text, 'button': QPalette.Button,
            'button_text': QPalette.ButtonText, 'highlight': QPalette.Highlight, 'highlighted_text': QPalette.HighlightedText
        }
        return roles.get(role_name)

    @staticmethod
    def color_dialog_options(show_alpha=True):
        if QT_VERSION >= 6:
            return QColorDialog.ColorDialogOption.ShowAlphaChannel if show_alpha else QColorDialog.ColorDialogOption(0)
        return QColorDialog.ShowAlphaChannel if show_alpha else QColorDialog.ColorDialogOptions()

    @staticmethod
    def tab_position(position='north'):
        return QTabWidget.TabPosition.North if QT_VERSION >= 6 and position == 'north' else (QTabWidget.North if position == 'north' else QTabWidget.South)

    @staticmethod
    def message_box_button(button='yes'):
        buttons = {'yes': QMessageBox.StandardButton.Yes, 'no': QMessageBox.StandardButton.No,
                   'ok': QMessageBox.StandardButton.Ok, 'cancel': QMessageBox.StandardButton.Cancel}
        return buttons.get(button) if QT_VERSION >= 6 else getattr(QMessageBox, button.title())

    @staticmethod
    def brush_style(style='no_brush'):
        return Qt.BrushStyle.NoBrush if QT_VERSION >= 6 and style == 'no_brush' else (Qt.NoBrush if style == 'no_brush' else Qt.SolidPattern)

    @staticmethod
    def non_modal():
        if hasattr(Qt, 'WindowModality'):
            return Qt.WindowModality.NonModal
        elif hasattr(Qt, 'NonModal'):
            return Qt.NonModal
        else:
            return 0

    @staticmethod
    def frame_shape(shape='hline'):
        if QT_VERSION >= 6:
            shapes = {'hline': QFrame.Shape.HLine, 'vline': QFrame.Shape.VLine, 'box': QFrame.Shape.Box,
                      'panel': QFrame.Shape.Panel, 'styledpanel': QFrame.Shape.StyledPanel}
            return shapes.get(shape, QFrame.Shape.NoFrame)
        shapes = {'hline': QFrame.HLine, 'vline': QFrame.VLine, 'box': QFrame.Box,
                  'panel': QFrame.Panel, 'styledpanel': QFrame.StyledPanel}
        return shapes.get(shape, QFrame.NoFrame)

    @staticmethod
    def frame_shadow(shadow='sunken'):
        if QT_VERSION >= 6:
            shadows = {'sunken': QFrame.Shadow.Sunken,
                       'raised': QFrame.Shadow.Raised, 'plain': QFrame.Shadow.Plain}
            return shadows.get(shadow, QFrame.Shadow.Plain)
        shadows = {'sunken': QFrame.Sunken,
                   'raised': QFrame.Raised, 'plain': QFrame.Plain}
        return shadows.get(shadow, QFrame.Plain)

    @staticmethod
    def alignment(align='center'):
        if QT_VERSION >= 6:
            aligns = {'center': Qt.AlignmentFlag.AlignCenter,
                      'left': Qt.AlignmentFlag.AlignLeft, 'right': Qt.AlignmentFlag.AlignRight}
            return aligns.get(align)
        return Qt.AlignCenter if align == 'center' else (Qt.AlignLeft if align == 'left' else Qt.AlignRight)

# ==============================================================================
# Color Picker Widget
# ==============================================================================


class ColorPickerWidget(QWidget):
    colorChanged = pyqtSignal(QColor)

    def __init__(self, initial_color=QColor(255, 255, 255), show_alpha=True, parent=None):
        super().__init__(parent)
        self.current_color = initial_color
        self.show_alpha = show_alpha
        self._setup_ui()
        self._update_display()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.btn_preview = QPushButton()
        self.btn_preview.setFixedSize(40, 25)
        self.btn_preview.clicked.connect(self._open_color_dialog)
        layout.addWidget(self.btn_preview)
        self.le_hex = QLineEdit()
        self.le_hex.setFixedWidth(80)
        self.le_hex.setPlaceholderText("#RRGGBB")
        self.le_hex.textChanged.connect(self._on_hex_changed)
        layout.addWidget(self.le_hex)
        if self.show_alpha:
            self.lbl_alpha = QLabel("Opacity:")
            self.slider_alpha = QSlider(QtCompat.orientation(horizontal=True))
            self.slider_alpha.setRange(0, 255)
            self.slider_alpha.setValue(255)
            self.slider_alpha.setFixedWidth(100)
            self.slider_alpha.valueChanged.connect(self._on_alpha_changed)
            self.lbl_alpha_val = QLabel("100%")
            self.lbl_alpha_val.setFixedWidth(40)
            layout.addWidget(self.lbl_alpha)
            layout.addWidget(self.slider_alpha)
            layout.addWidget(self.lbl_alpha_val)
        layout.addStretch()

    def _update_display(self):
        if self.show_alpha:
            alpha = self.current_color.alpha()
            self.btn_preview.setStyleSheet(
                f"background-color: rgba({self.current_color.red()}, {self.current_color.green()}, {self.current_color.blue()}, {alpha / 255.0}); border: 1px solid #999;")
        else:
            self.btn_preview.setStyleSheet(
                f"background-color: {self.current_color.name()}; border: 1px solid #999;")
        self.le_hex.blockSignals(True)
        self.le_hex.setText(self.current_color.name().upper())
        self.le_hex.blockSignals(False)
        if self.show_alpha:
            self.slider_alpha.blockSignals(True)
            self.slider_alpha.setValue(self.current_color.alpha())
            self.slider_alpha.blockSignals(False)
            alpha_percent = int(self.current_color.alpha() / 255.0 * 100)
            self.lbl_alpha_val.setText(f"{alpha_percent}%")

    def _on_hex_changed(self, text):
        if not text:
            return
        if not text.startswith('#'):
            text = '#' + text
        if len(text) >= 7:
            color = QColor(text)
            if color.isValid():
                if self.show_alpha:
                    color.setAlpha(self.current_color.alpha())
                self.current_color = color
                self._update_display()
                self.colorChanged.emit(self.current_color)

    def _on_alpha_changed(self, value):
        self.current_color.setAlpha(value)
        self._update_display()
        self.colorChanged.emit(self.current_color)

    def _open_color_dialog(self):
        options = QtCompat.color_dialog_options(self.show_alpha)
        color = QColorDialog.getColor(
            self.current_color, self, "Choose Color", options)
        if color.isValid():
            self.current_color = color
            self._update_display()
            self.colorChanged.emit(self.current_color)

    def get_color(self): return self.current_color

    def set_color(self, color):
        self.current_color = color
        self._update_display()

# ==============================================================================
# KML/KMZ Logic
# ==============================================================================


class KMLBuilder:
    @staticmethod
    def create_root():
        k = Element("kml")
        k.set("xmlns", "http://www.opengis.net/kml/2.2")
        return k

    @staticmethod
    def write_kml(root, path):
        rough = tostring(root, encoding='utf-8')
        pretty = minidom.parseString(rough).toprettyxml(
            indent=" ", encoding='utf-8')
        with open(path, 'wb') as f:
            f.write(pretty)

    @staticmethod
    def create_kmz(folder, kmz_path):
        with zipfile.ZipFile(kmz_path, 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(os.path.join(folder, "doc.kml"), "doc.kml")

    @staticmethod
    def color_to_kml(color):
        return f"{color.alpha():02x}{color.blue():02x}{color.green():02x}{color.red():02x}"


class StyleManager:
    def __init__(self, symbology_settings, label_settings):
        self.symbology_settings = symbology_settings
        self.label_settings = label_settings

    def create_style(self, doc, style_id, layer):
        custom_sym = self.symbology_settings.get(layer.id(), {})
        custom_lbl = self.label_settings.get(layer.id(), {})
        style = SubElement(doc, "Style", id=style_id)
        self._add_label_style(style, custom_lbl)
        geom = layer.geometryType()
        if geom == QgsWkbTypes.PointGeometry:
            self._add_point_style(style, layer, custom_sym)
        elif geom == QgsWkbTypes.LineGeometry:
            self._add_line_style(style, layer, custom_sym)
        elif geom == QgsWkbTypes.PolygonGeometry:
            self._add_polygon_style(style, layer, custom_sym)
        self._create_label_only_style(doc, style_id, custom_lbl)

    def _add_label_style(self, style, custom_lbl):
        lbl_scale = custom_lbl.get('scale', 1.0)
        lbl_color = custom_lbl.get('color', QColor(255, 255, 255))
        ls = SubElement(style, "LabelStyle")
        SubElement(ls, "scale").text = str(lbl_scale)
        SubElement(ls, "color").text = KMLBuilder.color_to_kml(lbl_color)

    def _add_point_style(self, style, layer, custom_sym):
        ic = SubElement(style, "IconStyle")
        if custom_sym.get('use_qgis', True):
            sym = layer.renderer().symbol() if hasattr(
                layer.renderer(), 'symbol') else None
            col = sym.color() if sym else QColor(255, 255, 0)
            scale = sym.size() / 10.0 if sym else 1.0
            href = "http://maps.google.com/mapfiles/kml/pushpin/ylw-pushpin.png"
        else:
            col = custom_sym.get('color', QColor(255, 255, 0))
            scale = custom_sym.get('size', 1.0)
            href = custom_sym.get(
                'icon_url', "http://maps.google.com/mapfiles/kml/pushpin/ylw-pushpin.png")
        SubElement(ic, "scale").text = str(scale)
        SubElement(ic, "color").text = KMLBuilder.color_to_kml(col)
        SubElement(SubElement(ic, "Icon"), "href").text = href

    def _add_line_style(self, style, layer, custom_sym):
        ln = SubElement(style, "LineStyle")
        if custom_sym.get('use_qgis', True):
            sym = layer.renderer().symbol() if hasattr(
                layer.renderer(), 'symbol') else None
            col = sym.color() if sym else QColor(255, 255, 0)
            w = sym.width() if sym else 2.0
        else:
            col = custom_sym.get('color', QColor(255, 255, 0))
            w = custom_sym.get('width', 2.0)
        SubElement(ln, "color").text = KMLBuilder.color_to_kml(col)
        SubElement(ln, "width").text = str(w)

    def _add_polygon_style(self, style, layer, custom_sym):
        poly = SubElement(style, "PolyStyle")
        ln = SubElement(style, "LineStyle")
        if custom_sym.get('use_qgis', True):
            fill_color, outline_color, outline_width, has_fill = self._extract_polygon_symbology(
                layer)
        else:
            fill_color = custom_sym.get('fill_color', QColor(255, 255, 0, 128))
            outline_color = custom_sym.get(
                'outline_color', QColor(255, 255, 0))
            outline_width = custom_sym.get('outline_width', 1.0)
            has_fill = fill_color.alpha() > 0
        SubElement(poly, "color").text = KMLBuilder.color_to_kml(fill_color)
        SubElement(poly, "fill").text = "1" if has_fill else "0"
        SubElement(poly, "outline").text = "1"
        SubElement(ln, "color").text = KMLBuilder.color_to_kml(outline_color)
        SubElement(ln, "width").text = str(outline_width)

    def _extract_polygon_symbology(self, layer):
        has_fill = False
        fill_color = QColor(0, 0, 0, 0)
        outline_color = QColor(0, 0, 0)
        outline_width = 1.0
        sym = layer.renderer().symbol() if hasattr(
            layer.renderer(), 'symbol') else None
        if sym and sym.symbolLayerCount() > 0:
            for i in range(sym.symbolLayerCount()):
                sl = sym.symbolLayer(i)
                if sl.layerType() == "SimpleFill":
                    if hasattr(sl, 'color') and sl.color().alpha() > 0:
                        has_fill = True
                        fill_color = sl.color()
                    if hasattr(sl, 'strokeColor'):
                        outline_color = sl.strokeColor()
                    if hasattr(sl, 'strokeWidth'):
                        outline_width = sl.strokeWidth()
                    if hasattr(sl, 'brushStyle') and sl.brushStyle() == QtCompat.brush_style('no_brush'):
                        has_fill = False
                        fill_color = QColor(0, 0, 0, 0)
                elif sl.layerType() == "SimpleLine":
                    if hasattr(sl, 'color'):
                        outline_color = sl.color()
                    if hasattr(sl, 'width'):
                        outline_width = sl.width()
        return fill_color, outline_color, outline_width, has_fill

    def _create_label_only_style(self, doc, style_id, custom_lbl):
        lbl_scale = custom_lbl.get('scale', 1.0)
        lbl_color = custom_lbl.get('color', QColor(255, 255, 255))
        lbl_style = SubElement(doc, "Style", id=f"{style_id}_lbl")
        ls = SubElement(lbl_style, "LabelStyle")
        SubElement(ls, "scale").text = str(lbl_scale)
        SubElement(ls, "color").text = KMLBuilder.color_to_kml(lbl_color)
        ic = SubElement(lbl_style, "IconStyle")
        SubElement(ic, "scale").text = "0"
        SubElement(SubElement(ic, "Icon"), "href").text = ""


class FeatureProcessor:
    def __init__(self, label_field_map, desc_field_map, separator=" |  "):
        self.label_field_map = label_field_map
        self.desc_field_map = desc_field_map
        self.separator = separator

    def get_label_text(self, feature, layer):
        if layer.id() in self.label_field_map:
            field_names = self.label_field_map[layer.id()]
            if field_names:
                values = []
                for fn in field_names:
                    if fn in feature.fields().names():
                        v = feature[fn]
                        if v is not None and v != 'NULL':
                            values.append(str(v))
                if values:
                    return self.separator.join(values)
        if layer.labelsEnabled():
            lbl = layer.labeling()
            if isinstance(lbl, QgsVectorLayerSimpleLabeling):
                fn = lbl.settings().fieldName
                if fn and fn in feature.fields().names():
                    return str(feature[fn])
        for fld in feature.fields():
            if fld.typeName() in ('String', 'text'):
                v = feature[fld.name()]
                if v not in (None, '', 'NULL'):
                    return str(v)
        return f"Feature {feature.id()}"

    def create_description_html_for_layer(self, feature, layer_id, label=None):
        html_parts = []
        if label:
            safe_label = html.escape(str(label))
            html_parts.append(
                f"<div style='font-weight:bold;font-size:16px;margin-bottom:12px;color:#333;'>{safe_label}</div>")
        html_parts.append(
            "<table border='1' cellpadding='8' cellspacing='0' style='border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:13px;border:1px solid #ddd;'>"
            "<thead><tr style='background-color:#4CAF50;color:white;'>"
            "<th style='padding:10px;text-align:left;border:1px solid #ddd;min-width:150px;'>Field</th>"
            "<th style='padding:10px;text-align:left;border:1px solid #ddd;'>Value</th>"
            "</tr></thead><tbody>"
        )
        allowed_fields = self.desc_field_map.get(layer_id)
        row_count = 0
        for fld in feature.fields():
            if allowed_fields is not None and fld.name() not in allowed_fields:
                continue
            val = feature[fld.name()]
            if val is None or (isinstance(val, str) and val.upper() == 'NULL'):
                display_val = "<span style='color:#999;font-style:italic;'>NULL</span>"
            elif isinstance(val, float):
                display_val = f"{val:.6f}".rstrip('0').rstrip('.')
            else:
                display_val = html.escape(str(val))
            safe_name = html.escape(fld.name())
            bg_color = '#f9f9f9' if row_count % 2 == 0 else '#ffffff'
            html_parts.append(
                f"<tr style='background-color:{bg_color};'><td style='padding:8px;font-weight:bold;border:1px solid #ddd;color:#555;word-wrap:break-word;'>{safe_name}</td><td style='padding:8px;border:1px solid #ddd;word-wrap:break-word;'>{display_val}</td></tr>")
            row_count += 1
        html_parts.append("</tbody></table>")
        return "".join(html_parts)


class GeometryConverter:
    @staticmethod
    def to_kml(placemark, geometry, folder, style_id, label_mode, label, feature, processor, desc):
        geom_type = geometry.type()
        if geom_type == QgsWkbTypes.PointGeometry:
            GeometryConverter._point_to_kml(placemark, geometry)
        elif geom_type == QgsWkbTypes.LineGeometry:
            GeometryConverter._line_to_kml(
                placemark, geometry, folder, style_id, label_mode, label, feature, processor, desc)
        elif geom_type == QgsWkbTypes.PolygonGeometry:
            GeometryConverter._polygon_to_kml(
                placemark, geometry, folder, style_id, label_mode, label, feature, processor, desc)

    @staticmethod
    def _point_to_kml(placemark, geometry):
        p = SubElement(placemark, "Point")
        c = geometry.asPoint()
        SubElement(p, "coordinates").text = f"{c.x()},{c.y()},0"

    @staticmethod
    def _line_to_kml(placemark, geometry, folder, style_id, label_mode, label, feature, processor, desc):
        ls = SubElement(placemark, "LineString")
        SubElement(ls, "tessellate").text = "1"
        coords = []
        if geometry.isMultipart():
            for part in geometry.asMultiPolyline():
                coords.extend([f"{pt.x()},{pt.y()},0" for pt in part])
        else:
            coords = [f"{pt.x()},{pt.y()},0" for pt in geometry.asPolyline()]
        SubElement(ls, "coordinates").text = " ".join(coords)
        if label_mode in ('name', 'both') and label:
            GeometryConverter._add_line_label(
                folder, feature, geometry, label, style_id, processor, desc)

    @staticmethod
    def _polygon_to_kml(placemark, geometry, folder, style_id, label_mode, label, feature, processor, desc):
        polygons = geometry.asMultiPolygon() if geometry.isMultipart() else [
            geometry.asPolygon()]
        for idx, polygon in enumerate(polygons):
            if idx == 0:
                current_pm = placemark
            else:
                current_pm = SubElement(folder, "Placemark")
                if label_mode in ('name', 'both') and label:
                    SubElement(current_pm, "name").text = str(label)
                SubElement(current_pm, "description").text = desc
                SubElement(current_pm, "visibility").text = "1"
                SubElement(current_pm, "styleUrl").text = f"#{style_id}"
            poly_elem = SubElement(current_pm, "Polygon")
            SubElement(poly_elem, "tessellate").text = "1"
            outer = SubElement(poly_elem, "outerBoundaryIs")
            lr = SubElement(outer, "LinearRing")
            coords = " ".join(f"{pt.x()},{pt.y()},0" for pt in polygon[0])
            SubElement(lr, "coordinates").text = coords
            for inner in polygon[1:]:
                i = SubElement(poly_elem, "innerBoundaryIs")
                lr = SubElement(i, "LinearRing")
                coords = " ".join(f"{pt.x()},{pt.y()},0" for pt in inner)
                SubElement(lr, "coordinates").text = coords
            if label_mode in ('name', 'both') and label and idx == 0:
                GeometryConverter._add_polygon_label(
                    folder, feature, geometry, label, style_id, processor, desc)

    @staticmethod
    def _add_polygon_label(folder, feature, geometry, label, style_id, processor, desc):
        pt = GeometryConverter._get_label_point(geometry)
        if pt is None:
            return
        pm = SubElement(folder, "Placemark")
        SubElement(pm, "name").text = str(label)
        SubElement(pm, "description").text = desc
        SubElement(pm, "styleUrl").text = f"#{style_id}_lbl"
        p = SubElement(pm, "Point")
        SubElement(p, "coordinates").text = f"{pt.x()},{pt.y()},0"

    @staticmethod
    def _add_line_label(folder, feature, geometry, label, style_id, processor, desc):
        pt = GeometryConverter._get_label_point(geometry)
        if pt is None:
            return
        pm = SubElement(folder, "Placemark")
        SubElement(pm, "name").text = str(label)
        SubElement(pm, "description").text = desc
        SubElement(pm, "styleUrl").text = f"#{style_id}_lbl"
        p = SubElement(pm, "Point")
        SubElement(p, "coordinates").text = f"{pt.x()},{pt.y()},0"

    @staticmethod
    def _get_label_point(geometry):
        try:
            if hasattr(geometry, 'poleOfInaccessibility'):
                pole = geometry.poleOfInaccessibility(0.000001)
                if pole and not pole.isEmpty():
                    return pole.asPoint()
        except:
            pass
        centroid = geometry.centroid()
        if centroid and not centroid.isEmpty():
            return centroid.asPoint()
        return None


class KMZExporter:
    def __init__(self):
        self.crs_wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        self.label_field_map = {}
        self.desc_field_map = {}
        self.symbology_settings = {}
        self.label_settings = {}
        self.separator = " | "

    def set_label_fields(self, d): self.label_field_map = d
    def set_description_fields(self, d): self.desc_field_map = d
    def set_separator(self, sep): self.separator = sep
    def set_symbology_settings(self, d): self.symbology_settings = d
    def set_label_settings(self, d): self.label_settings = d

    def export_layers(self, layers, output_path, label_modes, selected_only=False, progress_callback=None):
        tmp = tempfile.mkdtemp()
        kml_path = os.path.join(tmp, "doc.kml")
        try:
            kml = KMLBuilder.create_root()
            doc = SubElement(kml, "Document")
            file_name = os.path.basename(output_path).replace('.kmz', '')
            SubElement(doc, "name").text = file_name
            n = len(layers)
            for i, layer in enumerate(layers):
                if progress_callback:
                    progress_callback(
                        int(i / n * 90), f"Processing {layer.name()}")
                if isinstance(layer, QgsVectorLayer):
                    mode = label_modes.get(layer.id(), 'name')
                    self._export_vector_layer(layer, doc, mode, selected_only)
            if progress_callback:
                progress_callback(95, "Writing KML…")
            KMLBuilder.write_kml(kml, kml_path)
            if progress_callback:
                progress_callback(98, "Building KMZ…")
            KMLBuilder.create_kmz(tmp, output_path)
            if progress_callback:
                progress_callback(100, "Done!")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _export_vector_layer(self, layer, doc, label_mode, selected_only):
        folder = SubElement(doc, "Folder")
        SubElement(folder, "name").text = layer.name()
        style_id = f"s_{layer.id()}"
        style_manager = StyleManager(
            self.symbology_settings, self.label_settings)
        style_manager.create_style(doc, style_id, layer)
        transform = None
        if layer.crs() != self.crs_wgs84:
            transform = QgsCoordinateTransform(
                layer.crs(), self.crs_wgs84, QgsProject.instance())
        processor = FeatureProcessor(
            self.label_field_map, self.desc_field_map, self.separator)
        features = layer.selectedFeatures(
        ) if selected_only and layer.selectedFeatureCount() > 0 else layer.getFeatures()
        for feature in features:
            self._export_feature(feature, folder, style_id,
                                 transform, layer, label_mode, processor)

    def _export_feature(self, feature, folder, style_id, transform, layer, label_mode, processor):
        geometry = feature.geometry()
        if not geometry or geometry.isNull() or not geometry.constGet():
            return
        if transform:
            geometry.transform(transform)
        label = processor.get_label_text(feature, layer)
        placemark = SubElement(folder, "Placemark")
        if label_mode in ('name', 'both') and label:
            SubElement(placemark, "name").text = str(label)
        if label_mode == 'description':
            desc = processor.create_description_html_for_layer(
                feature, layer.id(), label=label)
        elif label_mode == 'both':
            desc = processor.create_description_html_for_layer(
                feature, layer.id(), label=label)
        else:
            desc = processor.create_description_html_for_layer(
                feature, layer.id())
        SubElement(placemark, "description").text = desc
        SubElement(placemark, "visibility").text = "1"
        SubElement(placemark, "styleUrl").text = f"#{style_id}"
        GeometryConverter.to_kml(
            placemark, geometry, folder, style_id, label_mode, label, feature, processor, desc)


class ExportThread(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, layers, out_path, label_mode_map, label_fields, desc_fields, separator, sym_settings, lbl_settings, selected_only):
        super().__init__()
        self.layers = layers
        self.out_path = out_path
        self.label_mode_map = label_mode_map
        self.label_fields = label_fields
        self.desc_fields = desc_fields
        self.separator = separator
        self.sym_settings = sym_settings
        self.lbl_settings = lbl_settings
        self.selected_only = selected_only

    def run(self):
        try:
            exporter = KMZExporter()
            exporter.set_label_fields(self.label_fields)
            exporter.set_description_fields(self.desc_fields)
            exporter.set_separator(self.separator)
            exporter.set_symbology_settings(self.sym_settings)
            exporter.set_label_settings(self.lbl_settings)
            exporter.export_layers(
                self.layers, self.out_path, self.label_mode_map, self.selected_only, self._progress)
            self.finished.emit(True, "KMZ created successfully")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished.emit(False, str(e))

    def _progress(self, val, txt): self.progress.emit(val, txt)


class SymbologyWidget:
    @staticmethod
    def create_point_widget(save_callback):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        h = QHBoxLayout()
        h.addWidget(QLabel("Icon:"))
        cb_icon = QComboBox()
        icons = [("Yellow pushpin", "http://maps.google.com/mapfiles/kml/pushpin/ylw-pushpin.png"), ("Red pushpin", "http://maps.google.com/mapfiles/kml/pushpin/red-pushpin.png"),
                 ("Blue pushpin", "http://maps.google.com/mapfiles/kml/pushpin/blue-pushpin.png"), ("Green pushpin", "http://maps.google.com/mapfiles/kml/pushpin/grn-pushpin.png")]
        for txt, url in icons:
            cb_icon.addItem(txt, url)
        cb_icon.currentIndexChanged.connect(save_callback)
        h.addWidget(cb_icon)
        h.addStretch()
        layout.addLayout(h)
        h = QHBoxLayout()
        h.addWidget(QLabel("Size:"))
        sp_size = QDoubleSpinBox()
        sp_size.setRange(0.5, 3.0)
        sp_size.setSingleStep(0.1)
        sp_size.setValue(1.0)
        sp_size.valueChanged.connect(save_callback)
        h.addWidget(sp_size)
        h.addStretch()
        layout.addLayout(h)
        layout.addWidget(QLabel("Color:"))
        picker = ColorPickerWidget(QColor(255, 255, 0), show_alpha=False)
        picker.colorChanged.connect(lambda: save_callback())
        layout.addWidget(picker)
        widget.cb_icon = cb_icon
        widget.sp_size = sp_size
        widget.picker = picker
        return widget

    @staticmethod
    def create_line_widget(save_callback):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        h = QHBoxLayout()
        h.addWidget(QLabel("Width:"))
        sp_width = QDoubleSpinBox()
        sp_width.setRange(0.5, 10.0)
        sp_width.setSingleStep(0.5)
        sp_width.setValue(2.0)
        sp_width.valueChanged.connect(save_callback)
        h.addWidget(sp_width)
        h.addStretch()
        layout.addLayout(h)
        layout.addWidget(QLabel("Color:"))
        picker = ColorPickerWidget(QColor(255, 255, 0), show_alpha=False)
        picker.colorChanged.connect(lambda: save_callback())
        layout.addWidget(picker)
        widget.sp_width = sp_width
        widget.picker = picker
        return widget

    @staticmethod
    def create_polygon_widget(save_callback):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("Fill color:"))
        picker_fill = ColorPickerWidget(
            QColor(255, 255, 0, 128), show_alpha=True)
        picker_fill.colorChanged.connect(lambda: save_callback())
        layout.addWidget(picker_fill)
        h = QHBoxLayout()
        h.addWidget(QLabel("Outline width:"))
        sp_width = QDoubleSpinBox()
        sp_width.setRange(0.5, 10.0)
        sp_width.setSingleStep(0.5)
        sp_width.setValue(1.0)
        sp_width.valueChanged.connect(save_callback)
        h.addWidget(sp_width)
        h.addStretch()
        layout.addLayout(h)
        layout.addWidget(QLabel("Outline color:"))
        picker_outline = ColorPickerWidget(QColor(255, 0, 0), show_alpha=False)
        picker_outline.colorChanged.connect(lambda: save_callback())
        layout.addWidget(picker_outline)
        widget.picker_fill = picker_fill
        widget.sp_width = sp_width
        widget.picker_outline = picker_outline
        return widget

# ==============================================================================
# KMZ Exporter Dialog (UI)
# ==============================================================================


class KMZExporterDialog(QDialog):
    def __init__(self, parent=iface.mainWindow()):
        super().__init__(parent)
        self.setWindowModality(QtCompat.non_modal())
        self.setWindowTitle("KMZ Exporter")
        self.setWindowFlags(TOOL_WINDOW_FLAGS)
        self.resize(550, 650)
        self.layers_dict = {}

        self.label_field_map = {}
        self.desc_field_map = {}
        self.label_mode_map = {}
        self.symbology_settings = {}
        self.label_settings = {}
        self.output_path = ""

        self._updating_ui = False
        self._setup_style()
        self._build_ui()
        self._load_layers()

    def _setup_style(self):
        palette = QPalette()
        colors = {
            'window_text': QColor(33, 37, 41), 'base': QColor(255, 255, 255),
            'alternate_base': QColor(237, 240, 244), 'text': QColor(33, 37, 41),
            'button': QColor(230, 234, 239), 'button_text': QColor(33, 37, 41),
            'highlight': QColor(0, 123, 255), 'highlighted_text': QColor(255, 255, 255)
        }
        for role_name, color in colors.items():
            palette.setColor(QtCompat.palette_role(role_name), color)
        self.setPalette(palette)
        self.setStyleSheet("""
            QGroupBox { font-weight: bold; border: 1px solid #ced4da; border-radius: 6px; margin-top: 8px; padding-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QPushButton { background-color: #000; color: white; border: none; padding: 6px 12px; border-radius: 4px; font-weight: 500; }
            QPushButton:hover { background-color: #0056b3; }
            QPushButton:pressed { background-color: #004085; }
            QPushButton#closeBtn { background-color: #6c757d; }
            QPushButton#closeBtn:hover { background-color: #5a6268; }
            QPushButton#cancelBtn { background-color: #dc3545; }
            QPushButton#cancelBtn:hover { background-color: #c82333; }
            QProgressBar { border: 1px solid #ced4da; border-radius: 4px; text-align: center; }
            QProgressBar::chunk { background-color: #28a745; }
            QLabel#status { color: #6c757d; font-style: italic; }
            QTabWidget::pane { border: 1px solid #ced4da; }
            QTabBar::tab { padding: 8px 16px; margin-right: 2px; }
            QTabBar::tab:selected { background: #000; color: white; }
            QLineEdit { padding: 6px; border: 1px solid #ced4da; border-radius: 4px; }
        """)

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setSpacing(12)
        main.setContentsMargins(16, 16, 16, 16)
        main.addWidget(self._create_layer_selection_group())
        main.addWidget(self._create_settings_group())
        main.addWidget(self._create_output_group())
        self.chk_selected_only = QCheckBox("Export only selected features")
        self.chk_selected_only.setToolTip(
            "If checked, only selected features in each layer will be exported.")
        main.addWidget(self.chk_selected_only)
        self.prog = QProgressBar()
        self.prog.setTextVisible(True)
        main.addWidget(self.prog)
        self.prog.hide()
        self.stat = QLabel("")
        self.stat.setObjectName("status")
        main.addWidget(self.stat)
        self.stat.hide()
        main.addLayout(self._create_button_layout())

    def _create_layer_selection_group(self):
        group = QGroupBox("Layers to export")
        layout = QVBoxLayout()
        btn_layout = QHBoxLayout()
        self.btn_all = QPushButton("Select All")
        self.btn_none = QPushButton("Select None")
        self.btn_all.clicked.connect(self._select_all)
        self.btn_none.clicked.connect(self._select_none)
        btn_layout.addWidget(self.btn_all)
        btn_layout.addWidget(self.btn_none)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        self.lst_layers = QListWidget()
        self.lst_layers.setMaximumHeight(120)
        self.lst_layers.setStyleSheet("QListWidget::item { padding: 4px; }")
        # CHANGED: Use itemClicked to toggle check state and sync UI
        self.lst_layers.itemClicked.connect(self._on_layer_item_clicked)
        self.lst_layers.itemChanged.connect(self._refresh_settings_combo)
        layout.addWidget(self.lst_layers)
        group.setLayout(layout)
        return group

    def _create_settings_group(self):
        group = QGroupBox("Layer Settings")
        layout = QVBoxLayout()
        h = QHBoxLayout()
        h.addWidget(QLabel("Current Layer:"))
        self.settings_layer_combo = QComboBox()
        self.settings_layer_combo.currentIndexChanged.connect(
            self._on_settings_layer_changed)
        h.addWidget(self.settings_layer_combo, 1)
        layout.addLayout(h)
        tabs = QTabWidget()
        tabs.setTabPosition(QtCompat.tab_position('north'))
        tabs.addTab(self._create_label_tab(), "Labels")
        tabs.addTab(self._create_symbology_tab(), "Symbology")
        tabs.addTab(self._create_description_tab(), "Description Fields")
        layout.addWidget(tabs)
        group.setLayout(layout)
        return group

    def _create_label_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)
        layout.addWidget(QLabel("Label Mode:"))
        grid = QGridLayout()
        self.r_name = QRadioButton("Map")
        self.r_desc = QRadioButton("Popup Only")
        self.r_both = QRadioButton("Map + Popup")
        self.r_none = QRadioButton("None")
        self.r_name.setChecked(True)
        for radio in [self.r_name, self.r_desc, self.r_both, self.r_none]:
            radio.toggled.connect(self._on_label_mode_changed)
        grid.addWidget(self.r_name, 0, 0)
        grid.addWidget(self.r_desc, 0, 1)
        grid.addWidget(self.r_both, 1, 0)
        grid.addWidget(self.r_none, 1, 1)
        layout.addLayout(grid)
        line = QFrame()
        line.setFrameShape(QtCompat.frame_shape('hline'))
        line.setFrameShadow(QtCompat.frame_shadow('sunken'))
        layout.addWidget(line)
        h_sep = QHBoxLayout()
        h_sep.addWidget(QLabel("<b>Label Fields (Multi-select):</b>"))
        h_sep.addStretch()
        h_sep.addWidget(QLabel("Separator:"))
        self.le_separator = QLineEdit("|")
        self.le_separator.setFixedWidth(50)
        self.le_separator.setAlignment(QtCompat.alignment('center'))
        h_sep.addWidget(self.le_separator)
        layout.addLayout(h_sep)
        self.lst_label_fields = QListWidget()
        self.lst_label_fields.setMaximumHeight(120)
        self.lst_label_fields.setToolTip(
            "Check fields to combine into the label")
        self.lst_label_fields.itemChanged.connect(self._save_label_fields)
        layout.addWidget(self.lst_label_fields)
        h_style = QHBoxLayout()
        h_style.addWidget(QLabel("Size:"))
        self.sp_lbl_scale = QDoubleSpinBox()
        self.sp_lbl_scale.setRange(0.5, 5.0)
        self.sp_lbl_scale.setSingleStep(0.1)
        self.sp_lbl_scale.setValue(1.0)
        self.sp_lbl_scale.valueChanged.connect(self._save_label_style)
        h_style.addWidget(self.sp_lbl_scale)
        h_style.addWidget(QLabel("Color:"))
        self.picker_lbl = ColorPickerWidget(show_alpha=False)
        self.picker_lbl.colorChanged.connect(lambda: self._save_label_style())
        h_style.addWidget(self.picker_lbl)
        h_style.addStretch()
        layout.addLayout(h_style)
        return tab

    def _create_description_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        lbl = QLabel(
            "Select fields to include in the Popup info window.\nIf none selected, all fields are shown.")
        lbl.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(lbl)
        btn_layout = QHBoxLayout()
        btn_all = QPushButton("Select All")
        btn_none = QPushButton("Select None")
        btn_all.clicked.connect(lambda: self._toggle_desc_fields(True))
        btn_none.clicked.connect(lambda: self._toggle_desc_fields(False))
        btn_layout.addWidget(btn_all)
        btn_layout.addWidget(btn_none)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        self.lst_desc_fields = QListWidget()
        self.lst_desc_fields.setAlternatingRowColors(True)
        self.lst_desc_fields.itemChanged.connect(self._save_desc_fields)
        layout.addWidget(self.lst_desc_fields)
        return tab

    def _create_symbology_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)
        self.chk_qgis = QCheckBox("Use QGIS layer symbology")
        self.chk_qgis.setChecked(True)
        self.chk_qgis.toggled.connect(self._toggle_custom_symbology)
        layout.addWidget(self.chk_qgis)
        self.w_custom = QWidget()
        custom_layout = QVBoxLayout(self.w_custom)
        custom_layout.setContentsMargins(20, 0, 0, 0)
        self.w_pt = SymbologyWidget.create_point_widget(self._save_symbology)
        self.w_ln = SymbologyWidget.create_line_widget(self._save_symbology)
        self.w_poly = SymbologyWidget.create_polygon_widget(
            self._save_symbology)
        custom_layout.addWidget(self.w_pt)
        custom_layout.addWidget(self.w_ln)
        custom_layout.addWidget(self.w_poly)
        layout.addWidget(self.w_custom)
        self.w_pt.hide()
        self.w_ln.hide()
        self.w_poly.hide()
        self.w_custom.setEnabled(False)
        layout.addSpacerItem(QSpacerItem(20, 10, QtCompat.size_policy(
            'minimum'), QtCompat.size_policy('expanding')))
        return tab

    def _create_output_group(self):
        group = QGroupBox("Output KMZ")
        layout = QVBoxLayout()
        h = QHBoxLayout()
        self.le_path = QLineEdit()
        self.le_path.setPlaceholderText(
            "Click to open folder, or type/paste path here")
        self.le_path.textChanged.connect(self._on_path_changed)
        h.addWidget(self.le_path, 1)
        self.btn_browse = QPushButton("Browse…")
        self.btn_browse.clicked.connect(self._browse_output)
        h.addWidget(self.btn_browse)
        layout.addLayout(h)
        self.lbl_link = QLabel()
        self.lbl_link.setTextFormat(QtCompat.text_format(rich_text=True))
        self.lbl_link.setOpenExternalLinks(False)
        self.lbl_link.linkActivated.connect(self._open_folder)
        self.lbl_link.setStyleSheet(
            "QLabel { color: #007bff; text-decoration: underline; }")
        self.lbl_link.setCursor(QtCompat.cursor_shape('pointing'))
        layout.addWidget(self.lbl_link)
        group.setLayout(layout)
        return group

    def _create_button_layout(self):
        layout = QHBoxLayout()
        layout.addStretch()
        self.btn_export = QPushButton("Export")
        self.btn_export.setMinimumWidth(120)
        self.btn_export.clicked.connect(self._start_export)
        layout.addWidget(self.btn_export)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("cancelBtn")
        self.btn_cancel.setMinimumWidth(120)
        self.btn_cancel.clicked.connect(self._cancel_export)
        self.btn_cancel.hide()
        layout.addWidget(self.btn_cancel)
        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("closeBtn")
        self.btn_close.setMinimumWidth(120)
        self.btn_close.clicked.connect(self.close)
        layout.addWidget(self.btn_close)
        return layout

    def _load_layers(self):
        project = QgsProject.instance()
        self.lst_layers.blockSignals(True)
        for layer_id, layer in project.mapLayers().items():
            if not isinstance(layer, QgsVectorLayer):
                continue
            item = QListWidgetItem(layer.name())
            item.setData(QtCompat.user_role(), layer_id)
            item.setFlags(item.flags() | QtCompat.item_flag(
                'ItemIsUserCheckable'))
            node = project.layerTreeRoot().findLayer(layer_id)
            item.setCheckState(QtCompat.checkstate(node and node.isVisible()))
            self.lst_layers.addItem(item)
            self.layers_dict[layer_id] = layer
            self.label_mode_map[layer_id] = 'name'
        self.lst_layers.blockSignals(False)
        self._refresh_settings_combo()

    def _refresh_settings_combo(self, item=None):
        if self._updating_ui:
            return
        self._updating_ui = True

        current_layer_id = self.settings_layer_combo.currentData()
        self.settings_layer_combo.clear()

        for i in range(self.lst_layers.count()):
            list_item = self.lst_layers.item(i)
            if list_item.checkState() == QtCompat.checkstate(True):
                layer_id = list_item.data(QtCompat.user_role())
                if layer_id in self.layers_dict:
                    self.settings_layer_combo.addItem(
                        self.layers_dict[layer_id].name(), layer_id)

        if current_layer_id:
            idx = self.settings_layer_combo.findData(current_layer_id)
            if idx >= 0:
                self.settings_layer_combo.setCurrentIndex(idx)

        self._updating_ui = False
        self._on_settings_layer_changed()

    def _on_layer_item_clicked(self, item):
        if self._updating_ui:
            return

        is_checked_before_toggle = item.checkState() == QtCompat.checkstate(True)
        item.setCheckState(QtCompat.checkstate(not is_checked_before_toggle))

        layer_id = item.data(QtCompat.user_role())

        if not is_checked_before_toggle:
            idx = self.settings_layer_combo.findData(layer_id)
            if idx != -1:
                self.settings_layer_combo.setCurrentIndex(idx)

    def _on_settings_layer_changed(self):
        layer_id = self.settings_layer_combo.currentData()

        if not layer_id:
            self.lst_label_fields.clear()
            self.lst_desc_fields.clear()
            return

        self.lst_label_fields.blockSignals(True)
        self.lst_desc_fields.blockSignals(True)
        self.lst_label_fields.clear()
        self.lst_desc_fields.clear()

        if layer_id in self.layers_dict:
            layer = self.layers_dict[layer_id]
            fields = layer.fields()
            saved_lbl_fields = self.label_field_map.get(layer_id, [])
            for field in fields:
                item = QListWidgetItem(field.name())
                item.setFlags(item.flags() | QtCompat.item_flag(
                    'ItemIsUserCheckable'))
                is_checked = field.name() in saved_lbl_fields
                item.setCheckState(QtCompat.checkstate(is_checked))
                self.lst_label_fields.addItem(item)
            if layer_id not in self.desc_field_map:
                saved_desc_fields = [f.name() for f in fields]
                self.desc_field_map[layer_id] = saved_desc_fields
            else:
                saved_desc_fields = self.desc_field_map[layer_id]
            for field in fields:
                item = QListWidgetItem(field.name())
                item.setFlags(item.flags() | QtCompat.item_flag(
                    'ItemIsUserCheckable'))
                is_checked = field.name() in saved_desc_fields
                item.setCheckState(QtCompat.checkstate(is_checked))
                self.lst_desc_fields.addItem(item)
            self._load_label_style()
            self._load_label_mode()
            self._update_symbology_widgets()
        self.lst_label_fields.blockSignals(False)
        self.lst_desc_fields.blockSignals(False)

    def _select_all(self):
        self.lst_layers.blockSignals(True)
        for i in range(self.lst_layers.count()):
            self.lst_layers.item(i).setCheckState(QtCompat.checkstate(True))
        self.lst_layers.blockSignals(False)
        self._refresh_settings_combo()

    def _select_none(self):
        self.lst_layers.blockSignals(True)
        for i in range(self.lst_layers.count()):
            self.lst_layers.item(i).setCheckState(QtCompat.checkstate(False))
        self.lst_layers.blockSignals(False)
        self._refresh_settings_combo()

    def _save_label_fields(self, item=None):
        layer_id = self.settings_layer_combo.currentData()
        if not layer_id:
            return
        selected = []
        for i in range(self.lst_label_fields.count()):
            it = self.lst_label_fields.item(i)
            if it.checkState() == QtCompat.checkstate(True):
                selected.append(it.text())
        self.label_field_map[layer_id] = selected

    def _save_desc_fields(self, item=None):
        layer_id = self.settings_layer_combo.currentData()
        if not layer_id:
            return
        selected = []
        for i in range(self.lst_desc_fields.count()):
            it = self.lst_desc_fields.item(i)
            if it.checkState() == QtCompat.checkstate(True):
                selected.append(it.text())
        self.desc_field_map[layer_id] = selected

    def _toggle_desc_fields(self, check):
        self.lst_desc_fields.blockSignals(True)
        state = QtCompat.checkstate(check)
        for i in range(self.lst_desc_fields.count()):
            self.lst_desc_fields.item(i).setCheckState(state)
        self.lst_desc_fields.blockSignals(False)
        self._save_desc_fields()

    def _load_label_mode(self):
        layer_id = self.settings_layer_combo.currentData()
        if not layer_id:
            return
        mode = self.label_mode_map.get(layer_id, 'name')
        mode_map = {'name': self.r_name, 'description': self.r_desc,
                    'both': self.r_both, 'none': self.r_none}
        if mode in mode_map:
            mode_map[mode].setChecked(True)

    def _on_label_mode_changed(self):
        layer_id = self.settings_layer_combo.currentData()
        if not layer_id:
            return
        if self.r_name.isChecked():
            self.label_mode_map[layer_id] = 'name'
        elif self.r_desc.isChecked():
            self.label_mode_map[layer_id] = 'description'
        elif self.r_both.isChecked():
            self.label_mode_map[layer_id] = 'both'
        elif self.r_none.isChecked():
            self.label_mode_map[layer_id] = 'none'

    def _load_label_style(self):
        layer_id = self.settings_layer_combo.currentData()
        if not layer_id:
            return
        settings = self.label_settings.get(layer_id, {})
        self.sp_lbl_scale.setValue(settings.get('scale', 1.0))
        self.picker_lbl.set_color(settings.get('color', QColor(255, 255, 255)))

    def _save_label_style(self):
        layer_id = self.settings_layer_combo.currentData()
        if layer_id:
            self.label_settings[layer_id] = {
                'scale': self.sp_lbl_scale.value(), 'color': self.picker_lbl.get_color()}

    def _update_symbology_widgets(self):
        layer_id = self.settings_layer_combo.currentData()
        if not layer_id or layer_id not in self.layers_dict:
            return
        layer = self.layers_dict[layer_id]
        geom_type = layer.geometryType()
        self.w_pt.hide()
        self.w_ln.hide()
        self.w_poly.hide()
        if geom_type == QgsWkbTypes.PointGeometry:
            self.w_pt.show()
            self._load_point_symbology(layer_id)
        elif geom_type == QgsWkbTypes.LineGeometry:
            self.w_ln.show()
            self._load_line_symbology(layer_id)
        elif geom_type == QgsWkbTypes.PolygonGeometry:
            self.w_poly.show()
            self._load_polygon_symbology(layer_id)
        use_qgis = self.symbology_settings.get(
            layer_id, {}).get('use_qgis', True)
        self.chk_qgis.setChecked(use_qgis)
        self._toggle_custom_symbology(use_qgis)

    def _load_point_symbology(self, layer_id):
        if layer_id in self.symbology_settings:
            s = self.symbology_settings[layer_id]
            idx = self.w_pt.cb_icon.findData(s.get('icon_url'))
            if idx >= 0:
                self.w_pt.cb_icon.setCurrentIndex(idx)
            self.w_pt.sp_size.setValue(s.get('size', 1.0))
            self.w_pt.picker.set_color(s.get('color', QColor(255, 255, 0)))

    def _load_line_symbology(self, layer_id):
        if layer_id in self.symbology_settings:
            s = self.symbology_settings[layer_id]
            self.w_ln.sp_width.setValue(s.get('width', 2.0))
            self.w_ln.picker.set_color(s.get('color', QColor(255, 255, 0)))

    def _load_polygon_symbology(self, layer_id):
        if layer_id in self.symbology_settings:
            s = self.symbology_settings[layer_id]
            self.w_poly.picker_fill.set_color(
                s.get('fill_color', QColor(255, 255, 0, 128)))
            self.w_poly.picker_outline.set_color(
                s.get('outline_color', QColor(255, 255, 0)))
            self.w_poly.sp_width.setValue(s.get('outline_width', 1.0))

    def _toggle_custom_symbology(self, use_qgis): self.w_custom.setEnabled(
        not use_qgis); self._save_symbology()

    def _save_symbology(self):
        layer_id = self.settings_layer_combo.currentData()
        if not layer_id:
            return
        layer = self.layers_dict[layer_id]
        geom_type = layer.geometryType()
        settings = {'use_qgis': self.chk_qgis.isChecked()}
        if not settings['use_qgis']:
            if geom_type == QgsWkbTypes.PointGeometry:
                settings.update({'icon_url': self.w_pt.cb_icon.currentData(
                ), 'size': self.w_pt.sp_size.value(), 'color': self.w_pt.picker.get_color()})
            elif geom_type == QgsWkbTypes.LineGeometry:
                settings.update(
                    {'width': self.w_ln.sp_width.value(), 'color': self.w_ln.picker.get_color()})
            elif geom_type == QgsWkbTypes.PolygonGeometry:
                settings.update({'fill_color': self.w_poly.picker_fill.get_color(
                ), 'outline_color': self.w_poly.picker_outline.get_color(), 'outline_width': self.w_poly.sp_width.value()})
        self.symbology_settings[layer_id] = settings

    def _on_path_changed(self, text):
        self.output_path = text.strip()
        self._update_link_label()

    def _update_link_label(self):
        if not self.output_path:
            self.lbl_link.setText("")
            return
        folder = os.path.dirname(self.output_path)
        if os.path.exists(folder):
            self.lbl_link.setText(
                f'<a href="file:///{folder}">Open folder: {folder}</a>')
        else:
            self.lbl_link.setText(
                f'<span style="color:#dc3545;">Folder does not exist: {folder}</span>')

    def _open_folder(self, url):
        folder = os.path.dirname(self.output_path)
        if os.path.exists(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        else:
            QMessageBox.warning(self, "Invalid Path",
                                "The folder does not exist yet.")

    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save KMZ", self.output_path or "", "KMZ files (*.kmz)")
        if path:
            if not path.lower().endswith('.kmz'):
                path += '.kmz'
            self.le_path.setText(path)

    def _start_export(self):
        selected_layers = []
        for idx in range(self.lst_layers.count()):
            item = self.lst_layers.item(idx)
            if item.checkState() == QtCompat.checkstate(True):
                layer_id = item.data(QtCompat.user_role())
                if layer_id in self.layers_dict:
                    selected_layers.append(self.layers_dict[layer_id])

        if not selected_layers:
            QMessageBox.warning(self, "No layers",
                                "Select at least one vector layer.")
            return
        if not self.output_path:
            QMessageBox.warning(
                self, "No file", "Enter or choose an output KMZ file.")
            return
        if not self.output_path.lower().endswith('.kmz'):
            self.output_path += '.kmz'
            self.le_path.setText(self.output_path)

        folder = os.path.dirname(self.output_path)
        if not os.path.exists(folder):
            reply = QMessageBox.question(self, "Create folder?", f"The folder does not exist:\n{folder}\nCreate it?", QtCompat.message_box_button(
                'yes') | QtCompat.message_box_button('no'))
            if reply == QtCompat.message_box_button('yes'):
                try:
                    os.makedirs(folder, exist_ok=True)
                except Exception as e:
                    QMessageBox.critical(
                        self, "Error", f"Cannot create folder:\n{e}")
                    return
            else:
                return

        self.prog.setValue(0)
        self.stat.setText("")
        self.prog.show()
        self.stat.show()
        self.btn_export.setEnabled(False)
        self.btn_browse.setEnabled(False)
        self.lst_layers.setEnabled(False)
        self.btn_cancel.show()

        self.thread = ExportThread(selected_layers, self.output_path, self.label_mode_map, self.label_field_map, self.desc_field_map,
                                   self.le_separator.text(), self.symbology_settings, self.label_settings, self.chk_selected_only.isChecked())
        self.thread.progress.connect(self._on_progress)
        self.thread.finished.connect(self._on_export_finished)
        self.thread.start()

    def _cancel_export(self):
        if hasattr(self, 'thread') and self.thread.isRunning():
            self.thread.terminate()
            self.thread.wait(3000)
            self._on_export_finished(False, "Export cancelled by user")

    def _on_progress(self, value, text): self.prog.setValue(
        value); self.stat.setText(text)

    def _on_export_finished(self, success, message):
        self.btn_export.setEnabled(True)
        self.btn_browse.setEnabled(True)
        self.lst_layers.setEnabled(True)
        self.btn_cancel.hide()
        self.prog.hide()
        self.prog.setValue(0)
        self.stat.setText("")
        if success:
            QMessageBox.information(self, "Success", message)
        else:
            QMessageBox.critical(self, "Error", f"Export failed:\n{message}")


# ==============================================================================
# Run Dialog
# ==============================================================================
# dlg = KMZExporterDialog()
# dlg.show()

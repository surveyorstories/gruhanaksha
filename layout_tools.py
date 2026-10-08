# -*- coding: utf-8 -*-
"""
Layout Designer Tools
~~~~~~~~~~~~~~~~~~~~~
Injects buttons into QGIS Print Layout Designer to insert images and customizable Excel tables.
Zero freezing via streaming reader, bounding-box termination, and custom row/column geometry.
"""
import os
import tempfile
import time
from qgis.PyQt.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QFileDialog, QMessageBox, QRadioButton, QButtonGroup, QFrame
)
try:
    from qgis.PyQt.QtWidgets import QAction
except ImportError:
    from qgis.PyQt.QtGui import QAction
from qgis.PyQt.QtGui import QIcon, QFont, QColor, QImage, QTextDocument, QPainter
from qgis.PyQt.QtCore import Qt
from qgis.core import (
    QgsApplication,
    QgsLayoutItemPicture,
    QgsLayoutItemManualTable,
    QgsLayoutFrame,
    QgsTableCell,
    QgsTextFormat,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsUnitTypes,
    QgsVectorLayer
)


class ExcelImportDialog(QDialog):
    """Customization dialog for importing Excel tables into QGIS layout."""

    def __init__(self, parent, file_path, sheets):
        super().__init__(parent)
        self.file_path = file_path
        self.sheets = sheets
        self.all_rows = []
        self.setWindowTitle("Import Excel Table to Layout")
        self.setMinimumSize(620, 500)
        self._init_ui()
        self._on_sheet_changed()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # 1. Sheet selection & row limits
        top_group = QGroupBox("Source Data")
        top_layout = QGridLayout(top_group)

        top_layout.addWidget(QLabel("Sheet:"), 0, 0)
        self.combo_sheet = QComboBox()
        self.combo_sheet.addItems(self.sheets)
        self.combo_sheet.currentIndexChanged.connect(self._on_sheet_changed)
        top_layout.addWidget(self.combo_sheet, 0, 1)

        self.lbl_stats = QLabel("Rows found: 0")
        self.lbl_stats.setStyleSheet("font-weight: bold; color: #2c3e50;")
        top_layout.addWidget(self.lbl_stats, 0, 2)

        top_layout.addWidget(QLabel("Start Row:"), 1, 0)
        self.spin_start_row = QSpinBox()
        self.spin_start_row.setRange(1, 10000)
        self.spin_start_row.setValue(1)
        self.spin_start_row.valueChanged.connect(self._update_preview)
        top_layout.addWidget(self.spin_start_row, 1, 1)

        top_layout.addWidget(QLabel("End Row:"), 1, 2)
        self.spin_end_row = QSpinBox()
        self.spin_end_row.setRange(1, 10000)
        self.spin_end_row.setValue(100)
        self.spin_end_row.valueChanged.connect(self._update_preview)
        top_layout.addWidget(self.spin_end_row, 1, 3)

        layout.addWidget(top_group)

        # 2. Adjustments group (Row height, column width, font)
        adjust_group = QGroupBox("Table Dimensions & Style Adjustments")
        adjust_layout = QGridLayout(adjust_group)

        adjust_layout.addWidget(QLabel("Row Height (mm):"), 0, 0)
        self.spin_row_h = QDoubleSpinBox()
        self.spin_row_h.setRange(3.0, 50.0)
        self.spin_row_h.setValue(7.0)
        self.spin_row_h.setSingleStep(0.5)
        adjust_layout.addWidget(self.spin_row_h, 0, 1)

        adjust_layout.addWidget(QLabel("Header Height (mm):"), 0, 2)
        self.spin_header_h = QDoubleSpinBox()
        self.spin_header_h.setRange(3.0, 50.0)
        self.spin_header_h.setValue(8.5)
        self.spin_header_h.setSingleStep(0.5)
        adjust_layout.addWidget(self.spin_header_h, 0, 3)

        adjust_layout.addWidget(QLabel("Font Size (pt):"), 1, 0)
        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(6, 24)
        self.spin_font_size.setValue(9)
        adjust_layout.addWidget(self.spin_font_size, 1, 1)

        self.chk_header = QCheckBox("First row as styled header")
        self.chk_header.setChecked(True)
        adjust_layout.addWidget(self.chk_header, 1, 2, 1, 2)

        adjust_layout.addWidget(QLabel("Column Width:"), 2, 0)
        self.radio_col_auto = QRadioButton("Auto-fit content")
        self.radio_col_fixed = QRadioButton("Fixed width (mm):")
        self.radio_col_auto.setChecked(True)
        self.col_btn_group = QButtonGroup(self)
        self.col_btn_group.addButton(self.radio_col_auto)
        self.col_btn_group.addButton(self.radio_col_fixed)

        self.spin_col_w = QDoubleSpinBox()
        self.spin_col_w.setRange(5.0, 120.0)
        self.spin_col_w.setValue(25.0)
        self.spin_col_w.setEnabled(False)
        self.radio_col_fixed.toggled.connect(self.spin_col_w.setEnabled)

        col_h_box = QHBoxLayout()
        col_h_box.addWidget(self.radio_col_auto)
        col_h_box.addWidget(self.radio_col_fixed)
        col_h_box.addWidget(self.spin_col_w)
        adjust_layout.addLayout(col_h_box, 2, 1, 1, 3)

        layout.addWidget(adjust_group)

        # 3. Data Preview Table
        layout.addWidget(QLabel("Preview (first 10 rows):"))
        self.table_preview = QTableWidget()
        self.table_preview.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_preview.setAlternatingRowColors(True)
        layout.addWidget(self.table_preview)

        # 4. Dialog Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_insert = QPushButton("Insert into Layout")
        self.btn_insert.setStyleSheet("font-weight: bold; background-color: #27ae60; color: white; padding: 6px 16px;")
        self.btn_insert.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_insert)

        layout.addLayout(btn_layout)

    def _on_sheet_changed(self):
        """Read data safely with fast streaming bounding-box."""
        sheet_name = self.combo_sheet.currentText()
        self.all_rows = LayoutDesignerToolsManager.load_sheet_rows_safe(self.file_path, sheet_name)
        total = len(self.all_rows)
        self.lbl_stats.setText(f"Rows found: {total}")
        self.spin_start_row.setValue(1)
        self.spin_end_row.setMaximum(max(total, 1))
        self.spin_end_row.setValue(min(total, 100))
        self._update_preview()

    def _update_preview(self):
        """Update live preview table with selected range."""
        if not self.all_rows:
            self.table_preview.setRowCount(0)
            self.table_preview.setColumnCount(0)
            return

        s_idx = max(0, self.spin_start_row.value() - 1)
        e_idx = min(len(self.all_rows), self.spin_end_row.value())
        selected = self.all_rows[s_idx:e_idx]

        preview_rows = selected[:10]
        col_count = len(self.all_rows[0]) if self.all_rows else 0

        self.table_preview.setRowCount(len(preview_rows))
        self.table_preview.setColumnCount(col_count)

        for r_idx, r in enumerate(preview_rows):
            for c_idx, val in enumerate(r):
                item = QTableWidgetItem(str(val))
                if r_idx == 0 and self.chk_header.isChecked() and s_idx == 0:
                    item.setBackground(QColor(230, 235, 245))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                self.table_preview.setItem(r_idx, c_idx, item)

        self.table_preview.resizeColumnsToContents()

    def get_selected_data(self):
        """Return slice of rows chosen by user."""
        s_idx = max(0, self.spin_start_row.value() - 1)
        e_idx = min(len(self.all_rows), self.spin_end_row.value())
        return self.all_rows[s_idx:e_idx]


class LayoutDesignerToolsManager:
    """Manages injection of Gruhanaksha actions into QGIS Layout Designer windows."""

    def __init__(self, iface):
        self.iface = iface
        # ponytail: map designer instance -> list of injected QActions for clean teardown
        self._connected_designers = {}

    def enable(self):
        """Connect to layout designer lifecycle signals."""
        self.iface.layoutDesignerOpened.connect(self._on_designer_opened)
        self.iface.layoutDesignerWillBeClosed.connect(self._on_designer_closed)

    def disable(self):
        """Disconnect signals and clean up any open layout windows."""
        try:
            self.iface.layoutDesignerOpened.disconnect(self._on_designer_opened)
        except Exception:  # nosec B110
            pass
        try:
            self.iface.layoutDesignerWillBeClosed.disconnect(self._on_designer_closed)
        except Exception:  # nosec B110
            pass

        for designer, actions in list(self._connected_designers.items()):
            toolbar = designer.actionsToolbar()
            if toolbar:
                for act in actions:
                    toolbar.removeAction(act)
        self._connected_designers.clear()

    def _on_designer_opened(self, designer):
        """Inject excel table and clipboard paste actions into designer toolbar."""
        toolbar = designer.actionsToolbar()
        if not toolbar:
            return

        win = designer.window()

        icon_tbl = QgsApplication.getThemeIcon("mActionAddTable.svg")
        act_table = QAction(icon_tbl, "Add Excel Table", win)
        act_table.setToolTip("Gruhanaksha: Add Excel Table with Custom Row Heights & Columns")
        act_table.triggered.connect(lambda: self._insert_excel(designer))

        icon_paste = QgsApplication.getThemeIcon("mActionEditPaste.svg")
        act_paste = QAction(icon_paste, "Paste as Image", win)
        act_paste.setToolTip("Gruhanaksha: Paste Clipboard as Image (from Excel, screenshot, or web page)")
        act_paste.triggered.connect(lambda: self._paste_clipboard_image(designer))

        sep = toolbar.addSeparator()
        toolbar.addAction(act_table)
        toolbar.addAction(act_paste)

        self._connected_designers[designer] = [sep, act_table, act_paste]

    def _on_designer_closed(self, designer):
        """Remove actions when designer closes."""
        self._connected_designers.pop(designer, None)

    def _paste_clipboard_image(self, designer):
        """Paste image or copied Excel table directly from clipboard as layout picture item."""
        cb = QApplication.clipboard()
        img = cb.image()

        # Try pixmap if direct QImage is null
        if img.isNull():
            pix = cb.pixmap()
            if not pix.isNull():
                img = pix.toImage()

        # If still null, check for HTML or TSV table from Excel
        if img.isNull():
            mime = cb.mimeData()
            html_text = ""
            if mime.hasHtml():
                raw_html = mime.html()
                # Clean Microsoft Excel clipboard fragment metadata
                if "<!--StartFragment-->" in raw_html and "<!--EndFragment-->" in raw_html:
                    s = raw_html.find("<!--StartFragment-->") + len("<!--StartFragment-->")
                    e = raw_html.find("<!--EndFragment-->")
                    html_text = raw_html[s:e].strip()
                elif "<table" in raw_html.lower():
                    s = raw_html.lower().find("<table")
                    e = raw_html.lower().rfind("</table>") + len("</table>")
                    html_text = raw_html[s:e].strip()
                else:
                    html_text = raw_html
            elif mime.hasText() and "\t" in mime.text():
                # Raw TSV cells copied from Excel/Calc -> wrap into styled HTML table
                rows = [line.split("\t") for line in mime.text().strip().split("\n")]
                html_parts = [
                    "<table border='1' cellspacing='0' cellpadding='6' "
                    "style='border-collapse:collapse; font-family:Arial, sans-serif; font-size:13px; color:#222;'>"
                ]
                for r_idx, r in enumerate(rows):
                    bg = "background-color:#f2f5f9; font-weight:bold;" if r_idx == 0 else "background-color:#ffffff;"
                    html_parts.append(
                        f"<tr style='{bg}'>" + "".join(f"<td style='padding:5px 10px; border:1px solid #ccc;'>{c.strip()}</td>" for c in r) + "</tr>"
                    )
                html_parts.append("</table>")
                html_text = "".join(html_parts)

            if html_text:
                full_html = (
                    "<html><body style='margin:0; padding:4px; font-family:Arial, sans-serif;'>"
                    + html_text
                    + "</body></html>"
                )
                doc = QTextDocument()
                doc.setHtml(full_html)
                doc.setTextWidth(doc.idealWidth())
                w = max(int(doc.idealWidth()), 200)
                h = max(int(doc.size().height()), 60)
                scale = 3.0  # Crisp 3x render for print layout
                img = QImage(int(w * scale), int(h * scale), QImage.Format_ARGB32)
                img.fill(Qt.white)
                p = QPainter(img)
                p.scale(scale, scale)
                doc.drawContents(p)
                p.end()

        if img.isNull():
            QMessageBox.information(
                designer.window(),
                "Paste Image",
                "No image or table found on clipboard.\n\n"
                "Please copy cells in Excel (Ctrl+C) or copy an image first."
            )
            return

        layout = designer.layout()
        if not layout:
            return

        # Save to dedicated cache directory
        save_dir = os.path.join(tempfile.gettempdir(), "gruhanaksha_clipboard_images")
        os.makedirs(save_dir, exist_ok=True)
        img_path = os.path.join(save_dir, f"clipboard_paste_{int(time.time() * 1000)}.png")
        if not img.save(img_path, "PNG"):
            QMessageBox.warning(designer.window(), "Paste Error", "Failed to save clipboard image.")
            return

        # Insert as native QgsLayoutItemPicture
        pic = QgsLayoutItemPicture(layout)
        pic.setPicturePath(img_path)

        # Calculate proportional size (default width 110mm, bounded height)
        w_px = img.width()
        h_px = img.height()
        w_mm = 110.0
        h_mm = (h_px / w_px) * w_mm if w_px > 0 else 60.0
        if h_mm > 180.0:
            h_mm = 180.0
            w_mm = (w_px / h_px) * h_mm if h_px > 0 else 110.0

        pic.attemptMove(QgsLayoutPoint(20, 20, QgsUnitTypes.LayoutMillimeters))
        pic.attemptResize(QgsLayoutSize(w_mm, h_mm, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(pic)
        layout.setSelectedItem(pic)
        layout.refresh()

    def _insert_excel(self, designer):
        """Pick Excel file, configure adjustments in dialog, and insert QgsLayoutItemManualTable."""
        path, _ = QFileDialog.getOpenFileName(
            designer.window(),
            "Select Excel File to Insert",
            "",
            "Excel Files (*.xlsx *.xls);;All Files (*.*)"
        )
        if not path:
            return

        layout = designer.layout()
        if not layout:
            return

        sheets = self._get_sheet_names(path)
        if not sheets:
            QMessageBox.warning(designer.window(), "Excel Import", "Could not read sheets from file.")
            return

        dialog = ExcelImportDialog(designer.window(), path, sheets)
        if dialog.exec_() != QDialog.Accepted:
            return

        rows = dialog.get_selected_data()
        if not rows:
            QMessageBox.warning(designer.window(), "Excel Import", "No data rows selected.")
            return

        # User chosen adjustments
        row_h = dialog.spin_row_h.value()
        header_h = dialog.spin_header_h.value()
        font_sz = dialog.spin_font_size.value()
        has_header = dialog.chk_header.isChecked()
        is_fixed_col = dialog.radio_col_fixed.isChecked()
        fixed_col_w = dialog.spin_col_w.value()

        # Build font formats
        fmt_body = QgsTextFormat()
        fmt_body.setFont(QFont("Arial", font_sz))

        fmt_header = QgsTextFormat()
        f_head = QFont("Arial", font_sz)
        f_head.setBold(True)
        fmt_header.setFont(f_head)

        num_cols = len(rows[0]) if rows else 1
        num_rows = len(rows)

        # Convert to QgsTableCell matrix with custom styles
        table_contents = []
        for r_idx, r in enumerate(rows):
            is_header_row = (r_idx == 0 and has_header)
            row_cells = []
            for val in r:
                cell = QgsTableCell(str(val))
                cell.setTextFormat(fmt_header if is_header_row else fmt_body)
                if is_header_row:
                    cell.setBackgroundColor(QColor(230, 235, 245))
                row_cells.append(cell)
            table_contents.append(row_cells)

        # Create layout manual table
        table = QgsLayoutItemManualTable.create(layout)
        layout.addMultiFrame(table)
        table.setTableContents(table_contents)

        # Apply custom row heights
        if has_header and num_rows > 1:
            row_heights = [header_h] + [row_h] * (num_rows - 1)
        else:
            row_heights = [row_h] * num_rows
        table.setRowHeights(row_heights)

        # Apply custom column widths
        if is_fixed_col:
            col_widths = [fixed_col_w] * num_cols
        else:
            # Auto-calculate width based on max character length in column
            col_widths = []
            for c_idx in range(num_cols):
                max_chars = max(len(str(rows[r][c_idx])) for r in range(min(num_rows, 50)))
                w = max(min(max_chars * 2.8 + 6.0, 90.0), 16.0)
                col_widths.append(w)
        table.setColumnWidths(col_widths)

        # Exact bounding frame sizing
        total_w = sum(col_widths)
        total_h = sum(row_heights)

        frame = QgsLayoutFrame(layout, table)
        frame.attemptMove(QgsLayoutPoint(20, 20, QgsUnitTypes.LayoutMillimeters))
        frame.attemptResize(QgsLayoutSize(total_w, total_h, QgsUnitTypes.LayoutMillimeters))
        table.addFrame(frame)
        layout.setSelectedItem(frame)
        layout.refresh()

    def _get_sheet_names(self, file_path):
        """Retrieve sheet names quickly without loading full document."""
        if file_path.lower().endswith(".xlsx"):
            try:
                import openpyxl
                wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
                names = wb.sheetnames
                wb.close()
                return names
            except Exception:  # nosec B110
                pass

        # Fallback to OGR layer check
        vlayer = QgsVectorLayer(file_path, "probe", "ogr")
        if vlayer.isValid():
            return ["Sheet1"]
        return []

    @staticmethod
    def load_sheet_rows_safe(file_path, sheet_name, max_rows=500):
        """
        Fast non-freezing row reader:
        - Uses openpyxl read_only streaming.
        - Stops after 10 consecutive empty rows (prevents 1,048,576 row loop freeze).
        - Hard-capped at max_rows.
        - Normalizes jagged column grids.
        """
        rows = []
        if file_path.lower().endswith(".xlsx"):
            try:
                import openpyxl
                wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
                ws = wb[sheet_name]
                empty_consecutive = 0
                max_cols = 0

                for row in ws.iter_rows(values_only=True):
                    vals = [("" if v is None else str(v).strip()) for v in row]
                    if any(vals):
                        empty_consecutive = 0
                        # strip trailing empty cells
                        while vals and vals[-1] == "":
                            vals.pop()
                        max_cols = max(max_cols, len(vals))
                        rows.append(vals)
                    else:
                        empty_consecutive += 1
                        if empty_consecutive >= 10 and len(rows) > 0:
                            break  # ponytail: stop immediately when content ends

                    if len(rows) >= max_rows:
                        break

                wb.close()

                # Normalize grid
                for r in rows:
                    if len(r) < max_cols:
                        r.extend([""] * (max_cols - len(r)))

                if rows:
                    return rows
            except Exception:  # nosec B110
                pass

        # Fallback to OGR vector layer (for .xls)
        try:
            vlayer = QgsVectorLayer(f"{file_path}|layername={sheet_name}", "excel_layer", "ogr")
            if not vlayer.isValid():
                vlayer = QgsVectorLayer(file_path, "excel_layer", "ogr")

            if vlayer.isValid():
                headers = [f.name() for f in vlayer.fields()]
                rows = [headers]
                count = 0
                for feat in vlayer.getFeatures():
                    rows.append([("" if feat[f.name()] is None else str(feat[f.name()])) for f in vlayer.fields()])
                    count += 1
                    if count >= max_rows:
                        break
        except Exception:  # nosec B110
            pass

        return rows

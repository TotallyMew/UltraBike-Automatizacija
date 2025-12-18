"""
Batch Upload Screen - Complete Redesign
Fluent Design System with Space Indigo/Lavender color scheme
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QFrame
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent
from qfluentwidgets import (
    LineEdit, ComboBox, CheckBox, PrimaryPushButton, PushButton,
    BodyLabel, TitleLabel, StrongBodyLabel, CaptionLabel,
    TransparentToolButton, FluentIcon, InfoBar, InfoBarPosition,
    ScrollArea, CardWidget, PillPushButton, isDarkTheme, TransparentPushButton, IconWidget
)
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from Managers.DescriptionManager import DescriptionManager
from GUI_Qt.styles.theme_config import COLORS, FONTS


# Removed old ProductRow CardWidget class - replaced with modern table


class DropZoneWidget(QWidget):
    """Drag and drop zone for Excel files"""
    file_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        # Icon
        icon = IconWidget(FluentIcon.DOCUMENT)
        icon.setFixedSize(96, 96)

        # Title
        title = StrongBodyLabel("Drop your Excel file here")
        title.setStyleSheet(f"font-size: 16px; color: {COLORS['lavender_grey']};")

        # Subtitle
        subtitle = CaptionLabel("or click to browse")
        subtitle.setStyleSheet(f"color: {COLORS['text_secondary']};")

        layout.addStretch()
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

        # Style
        self.setStyleSheet("""
            DropZoneWidget {
                background-color: transparent;
                border: 2px dashed #8D99AE;
                border-radius: 12px;
            }
            DropZoneWidget:hover {
                border-color: #2B2D42;
                background-color: rgba(139, 153, 174, 0.05);
            }
        """)

        # Make clickable
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1 and urls[0].toLocalFile().endswith('.xlsx'):
                event.acceptProposedAction()
                self.setStyleSheet("""
                    DropZoneWidget {
                        background-color: rgba(139, 153, 174, 0.1);
                        border: 2px solid #2B2D42;
                        border-radius: 12px;
                    }
                """)

    def dragLeaveEvent(self, event):
        self.setStyleSheet("""
            DropZoneWidget {
                background-color: transparent;
                border: 2px dashed #8D99AE;
                border-radius: 12px;
            }
            DropZoneWidget:hover {
                border-color: #2B2D42;
                background-color: rgba(139, 153, 174, 0.05);
            }
        """)

    def dropEvent(self, event: QDropEvent):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        if files and files[0].endswith('.xlsx'):
            self.file_dropped.emit(files[0])
        self.setStyleSheet("""
            DropZoneWidget {
                background-color: transparent;
                border: 2px dashed #8D99AE;
                border-radius: 12px;
            }
            DropZoneWidget:hover {
                border-color: #2B2D42;
                background-color: rgba(139, 153, 174, 0.05);
            }
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.file_dropped.emit("__browse__")  # Signal to open file dialog


class BatchUploadScreen(QWidget):
    """Complete redesign with Fluent Design System"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.current_mode = "manual"
        self.row_counter = 0

        # Load descriptions
        desc_manager = DescriptionManager(main_window.db)
        self.descriptions = [d['name'] for d in desc_manager.list_descriptions()]

        # Brands
        self.brands = [
            "KROSS", "Pinarello", "Basso", "Factor",
            "TREK", "Rondo", "Octane", "Rascal", "Lee Cougan"
        ]

        self._init_ui()

    def _init_ui(self):
        """Initialize UI with proper Fluent Design"""
        # Apply background color and font
        is_dark = isDarkTheme()
        bg_color = '#16172b' if is_dark else COLORS['platinum']

        self.setStyleSheet(f"""
            BatchUploadScreen {{
                background-color: {bg_color};
                font-family: {FONTS['family']};
            }}
        """)
        self.setAutoFillBackground(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)  # Reduced margins for better screen fit
        layout.setSpacing(20)

        # === HEADER SECTION ===
        header = QHBoxLayout()

        # Title
        title_label = TitleLabel("Batch Upload")
        header.addWidget(title_label)
        header.addStretch()

        # Mode pills (Fluent Design style)
        mode_container = QWidget()
        mode_layout = QHBoxLayout(mode_container)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(8)
        mode_container.setStyleSheet("background: transparent;")

        self.manual_pill = PillPushButton("Manual Entry")
        self.manual_pill.setCheckable(True)
        self.manual_pill.setChecked(True)
        self.manual_pill.clicked.connect(lambda: self._switch_mode("manual"))

        self.excel_pill = PillPushButton("Excel Upload")
        self.excel_pill.setCheckable(True)
        self.excel_pill.clicked.connect(lambda: self._switch_mode("excel"))

        mode_layout.addWidget(self.manual_pill)
        mode_layout.addWidget(self.excel_pill)

        header.addWidget(mode_container)
        layout.addLayout(header)

        # === TOOLBAR SECTION ===
        toolbar_card = CardWidget()
        toolbar_card.setBorderRadius(8)
        toolbar_layout = QHBoxLayout(toolbar_card)
        toolbar_layout.setContentsMargins(20, 16, 20, 16)

        # Manual toolbar
        self.manual_toolbar = QWidget()
        manual_tb_layout = QHBoxLayout(self.manual_toolbar)
        manual_tb_layout.setContentsMargins(0, 0, 0, 0)
        manual_tb_layout.setSpacing(12)

        add_btn = PushButton("Add Row")
        add_btn.setIcon(FluentIcon.ADD)
        add_btn.clicked.connect(self._add_row)

        clear_btn = TransparentPushButton("Clear All")
        clear_btn.setIcon(FluentIcon.DELETE)
        clear_btn.clicked.connect(self._clear_all)

        # Bulk selectors
        bulk_label = CaptionLabel("Bulk select:")
        bulk_label.setStyleSheet(f"color: {COLORS['text_secondary']}; margin-left: 20px;")

        frameset_bulk = CheckBox("Frameset")
        frameset_bulk.setToolTip("Select all Pinarello framesets")
        frameset_bulk.stateChanged.connect(self._toggle_all_framesets)

        disclaimer_bulk = CheckBox("Disclaimer")
        disclaimer_bulk.setToolTip("Select all disclaimers")
        disclaimer_bulk.stateChanged.connect(self._toggle_all_disclaimers)

        manual_tb_layout.addWidget(add_btn)
        manual_tb_layout.addWidget(clear_btn)
        manual_tb_layout.addStretch()
        manual_tb_layout.addWidget(bulk_label)
        manual_tb_layout.addWidget(frameset_bulk)
        manual_tb_layout.addWidget(disclaimer_bulk)

        # Excel toolbar
        self.excel_toolbar = QWidget()
        excel_tb_layout = QHBoxLayout(self.excel_toolbar)
        excel_tb_layout.setContentsMargins(0, 0, 0, 0)
        excel_tb_layout.setSpacing(12)

        browse_btn = PushButton("Browse Excel File")
        browse_btn.setIcon(FluentIcon.FOLDER)
        browse_btn.clicked.connect(self._browse_excel)

        template_btn = TransparentPushButton("Download Template")
        template_btn.setIcon(FluentIcon.DOWNLOAD)
        template_btn.clicked.connect(self._download_template)

        self.excel_file_label = BodyLabel("No file selected")
        self.excel_file_label.setStyleSheet(f"color: {COLORS['text_secondary']}; margin-left: 20px;")

        excel_tb_layout.addWidget(browse_btn)
        excel_tb_layout.addWidget(template_btn)
        excel_tb_layout.addStretch()
        excel_tb_layout.addWidget(self.excel_file_label)

        self.excel_toolbar.setVisible(False)

        toolbar_layout.addWidget(self.manual_toolbar)
        toolbar_layout.addWidget(self.excel_toolbar)
        layout.addWidget(toolbar_card)

        # === CONTENT AREA ===
        content_card = CardWidget()
        content_card.setBorderRadius(8)
        content_layout = QVBoxLayout(content_card)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(16)

        # Modern Fluent table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["Brand", "Product Code", "URL / Code", "Description", "Frameset", "Disclaimer", ""])
        self.table.setRowCount(5)

        # Apply table styling
        self._update_table_theme()

        # Table settings
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setMinimumHeight(48)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(56)  # Taller rows for better alignment
        self.table.setShowGrid(True)

        # Enable corner clipping for rounded borders
        self.table.setCornerButtonEnabled(False)

        # Column widths
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 160)  # Brand (wider)
        self.table.setColumnWidth(1, 150)  # Code (wider)
        # Column 2 stretches (URL)
        self.table.setColumnWidth(3, 180)  # Description (wider)
        self.table.setColumnWidth(4, 100)  # Frameset (wider)
        self.table.setColumnWidth(5, 110)  # Disclaimer (wider)
        self.table.setColumnWidth(6, 60)   # Delete (wider)

        # Populate initial rows
        for row in range(5):
            self._setup_table_row(row)

        content_layout.addWidget(self.table, 1)

        # Excel drop zone
        self.excel_empty = DropZoneWidget()
        self.excel_empty.file_dropped.connect(self._handle_file_drop)
        self.excel_empty.setVisible(False)
        content_layout.addWidget(self.excel_empty, 1)

        layout.addWidget(content_card, 1)

        # === STATUS BAR ===
        status_card = CardWidget()
        status_card.setBorderRadius(8)
        status_layout = QHBoxLayout(status_card)
        status_layout.setContentsMargins(20, 14, 20, 14)

        self.status_label = BodyLabel("Ready to start")
        self.status_label.setStyleSheet(f"color: {COLORS['text_secondary']};")

        status_layout.addWidget(self.status_label)
        status_layout.addStretch()

        layout.addWidget(status_card)

        # === ACTION BAR ===
        actions = QHBoxLayout()
        actions.addStretch()

        self.start_btn = PrimaryPushButton("Start Batch Upload")
        self.start_btn.setIcon(FluentIcon.PLAY)
        self.start_btn.setEnabled(False)
        self.start_btn.setFixedHeight(40)
        self.start_btn.clicked.connect(self._start_upload)

        actions.addWidget(self.start_btn)
        layout.addLayout(actions)

    def _setup_table_row(self, row):
        """Setup widgets for a table row"""
        # Helper to create centered container
        def create_centered_widget(widget):
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            layout = QHBoxLayout(container)
            layout.setContentsMargins(8, 4, 8, 4)
            layout.addWidget(widget)
            return container

        # Brand combo
        brand_combo = ComboBox()
        brand_combo.addItems(self.brands)
        brand_combo.setPlaceholderText("Select brand")
        brand_combo.setFixedHeight(36)
        brand_combo.currentTextChanged.connect(lambda brand, r=row: self._on_brand_change(r, brand))
        brand_combo.currentTextChanged.connect(self._validate)
        self.table.setCellWidget(row, 0, create_centered_widget(brand_combo))

        # Product code
        code_field = LineEdit()
        code_field.setPlaceholderText("UB-XXXX")
        code_field.setFixedHeight(36)
        code_field.textChanged.connect(lambda text, field=code_field: self._on_code_changed(text, field))
        self.table.setCellWidget(row, 1, create_centered_widget(code_field))

        # URL
        url_field = LineEdit()
        url_field.setPlaceholderText("https://... or product code")
        url_field.setFixedHeight(36)
        url_field.textChanged.connect(lambda text, field=url_field: self._on_url_changed(text, field))
        self.table.setCellWidget(row, 2, create_centered_widget(url_field))

        # Description
        desc_combo = ComboBox()
        desc_combo.addItem("")
        desc_combo.addItems(self.descriptions)
        desc_combo.setPlaceholderText("Optional")
        desc_combo.setFixedHeight(36)
        desc_combo.currentTextChanged.connect(self._validate)
        self.table.setCellWidget(row, 3, create_centered_widget(desc_combo))

        # Frameset checkbox - centered with fixed approach
        frameset_check = CheckBox("")
        frameset_check.setVisible(False)
        frameset_check.stateChanged.connect(self._validate)
        frameset_check.setFixedSize(40, 40)  # Fixed size to force centering
        frameset_container = QWidget()
        frameset_container.setStyleSheet("background: transparent;")
        frameset_layout = QVBoxLayout(frameset_container)  # Use VBox for better control
        frameset_layout.setContentsMargins(0, 0, 0, 0)
        frameset_layout.setSpacing(0)
        frameset_layout.addWidget(frameset_check, 0, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self.table.setCellWidget(row, 4, frameset_container)

        # Disclaimer checkbox - centered with fixed approach
        disclaimer_check = CheckBox("")
        disclaimer_check.stateChanged.connect(self._validate)
        disclaimer_check.setFixedSize(40, 40)  # Fixed size to force centering
        disclaimer_container = QWidget()
        disclaimer_container.setStyleSheet("background: transparent;")
        disclaimer_layout = QVBoxLayout(disclaimer_container)  # Use VBox for better control
        disclaimer_layout.setContentsMargins(0, 0, 0, 0)
        disclaimer_layout.setSpacing(0)
        disclaimer_layout.addWidget(disclaimer_check, 0, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self.table.setCellWidget(row, 5, disclaimer_container)

        # Delete button
        delete_btn = TransparentToolButton(FluentIcon.DELETE)
        delete_btn.setToolTip("Remove row")
        delete_btn.setFixedSize(36, 36)
        delete_btn.clicked.connect(lambda: self._remove_row(row))
        delete_container = QWidget()
        delete_container.setStyleSheet("background: transparent;")
        delete_layout = QHBoxLayout(delete_container)
        delete_layout.setContentsMargins(0, 0, 0, 0)
        delete_layout.addWidget(delete_btn)
        delete_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setCellWidget(row, 6, delete_container)

    def _get_widget_from_cell(self, row, col, widget_type):
        """Helper to get widget from table cell (handles containers)"""
        cell_widget = self.table.cellWidget(row, col)
        if not cell_widget:
            return None
        # If it's a container, find the actual widget
        widget = cell_widget.findChild(widget_type)
        return widget if widget else (cell_widget if isinstance(cell_widget, widget_type) else None)

    def _on_brand_change(self, row, brand):
        """Handle brand change to show/hide frameset checkbox"""
        checkbox = self._get_widget_from_cell(row, 4, CheckBox)
        if checkbox:
            is_pinarello = brand == "Pinarello"
            checkbox.setVisible(is_pinarello)
            if not is_pinarello:
                checkbox.setChecked(False)

    def _switch_mode(self, mode):
        """Switch between manual and Excel mode"""
        self.current_mode = mode

        # Update pills
        self.manual_pill.setChecked(mode == "manual")
        self.excel_pill.setChecked(mode == "excel")

        # Update toolbars
        self.manual_toolbar.setVisible(mode == "manual")
        self.excel_toolbar.setVisible(mode == "excel")

        # Update content visibility
        has_data = self._has_valid_rows()
        if mode == "excel" and not has_data:
            self.table.setVisible(False)
            self.excel_empty.setVisible(True)
        else:
            self.table.setVisible(True)
            self.excel_empty.setVisible(False)

    def _has_valid_rows(self):
        """Check if table has any valid data"""
        for row in range(self.table.rowCount()):
            brand_widget = self._get_widget_from_cell(row, 0, ComboBox)
            code_widget = self._get_widget_from_cell(row, 1, LineEdit)
            url_widget = self._get_widget_from_cell(row, 2, LineEdit)

            if (brand_widget and brand_widget.currentText() and
                code_widget and code_widget.text().strip() and
                url_widget and url_widget.text().strip()):
                return True
        return False

    def _add_row(self):
        """Add new row to table"""
        current_rows = self.table.rowCount()
        self.table.setRowCount(current_rows + 1)
        self._setup_table_row(current_rows)
        self._validate()

    def _remove_row(self, row):
        """Remove a row from table"""
        if self.table.rowCount() > 1:
            self.table.removeRow(row)
            self._validate()

    def _clear_all(self):
        """Clear all rows"""
        self.table.setRowCount(5)
        for row in range(5):
            self._setup_table_row(row)
        self._validate()

    def _toggle_all_framesets(self, state):
        """Toggle all frameset checkboxes"""
        checked = state == Qt.CheckState.Checked.value
        for row in range(self.table.rowCount()):
            brand_widget = self._get_widget_from_cell(row, 0, ComboBox)
            if brand_widget and brand_widget.currentText() == "Pinarello":
                checkbox = self._get_widget_from_cell(row, 4, CheckBox)
                if checkbox and checkbox.isVisible():
                    checkbox.setChecked(checked)

    def _toggle_all_disclaimers(self, state):
        """Toggle all disclaimer checkboxes"""
        checked = state == Qt.CheckState.Checked.value
        for row in range(self.table.rowCount()):
            checkbox = self._get_widget_from_cell(row, 5, CheckBox)
            if checkbox:
                checkbox.setChecked(checked)

    def _on_code_changed(self, text, field):
        """Handle product code field change with validation"""
        # Apply visual feedback
        if text.strip():
            field.setStyleSheet(f"""
                LineEdit {{
                    border-left: 3px solid {COLORS['success']};
                }}
            """)
        elif text:  # Has text but only whitespace
            field.setStyleSheet(f"""
                LineEdit {{
                    border-left: 3px solid {COLORS['error']};
                }}
            """)
        else:  # Empty
            field.setStyleSheet("")

        self._validate()

    def _on_url_changed(self, text, field):
        """Handle URL field change with validation"""
        # Apply visual feedback
        if text.strip():
            field.setStyleSheet(f"""
                LineEdit {{
                    border-left: 3px solid {COLORS['success']};
                }}
            """)
        elif text:  # Has text but only whitespace
            field.setStyleSheet(f"""
                LineEdit {{
                    border-left: 3px solid {COLORS['error']};
                }}
            """)
        else:  # Empty
            field.setStyleSheet("")

        self._validate()

    def _validate(self):
        """Validate all rows"""
        valid_count = 0
        for row in range(self.table.rowCount()):
            brand_widget = self._get_widget_from_cell(row, 0, ComboBox)
            code_widget = self._get_widget_from_cell(row, 1, LineEdit)
            url_widget = self._get_widget_from_cell(row, 2, LineEdit)

            if (brand_widget and brand_widget.currentText() and
                code_widget and code_widget.text().strip() and
                url_widget and url_widget.text().strip()):
                valid_count += 1

        self.start_btn.setEnabled(valid_count > 0)

        if valid_count > 0:
            self.status_label.setText(f"✓ {valid_count} product{'s' if valid_count != 1 else ''} ready")
            self.status_label.setStyleSheet(f"color: {COLORS['success']}; font-weight: 500;")
        else:
            self.status_label.setText("Add at least one product to continue")
            self.status_label.setStyleSheet(f"color: {COLORS['text_secondary']};")

    def _handle_file_drop(self, filepath):
        """Handle file drop or click on drop zone"""
        if filepath == "__browse__":
            self._browse_excel()
        else:
            self._load_excel(filepath)

    def _browse_excel(self):
        """Browse for Excel file"""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Excel File",
            "",
            "Excel files (*.xlsx);;All files (*.*)"
        )

        if filename:
            self._load_excel(filename)

    def _load_excel(self, filename):
        """Load Excel file"""
        try:
            wb = openpyxl.load_workbook(filename)
            ws = wb.active

            # Find header
            header_row = None
            for idx, row in enumerate(ws.iter_rows(min_row=1, max_row=5), start=1):
                values = [str(c.value).lower() if c.value else "" for c in row]
                if any("brand" in v for v in values):
                    header_row = idx
                    break

            if not header_row:
                raise Exception("Could not find header row in Excel file")

            # Count data rows first
            data_rows = []
            for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
                if any(row):
                    data_rows.append(row)

            # Set table row count
            self.table.setRowCount(len(data_rows))

            # Load rows into table
            valid_count = 0
            invalid_count = 0

            for table_row, excel_row in enumerate(data_rows):
                brand = str(excel_row[0]) if len(excel_row) > 0 and excel_row[0] else ""
                code = str(excel_row[1]) if len(excel_row) > 1 and excel_row[1] else ""
                url = str(excel_row[2]) if len(excel_row) > 2 and excel_row[2] else ""
                desc = str(excel_row[3]).strip() if len(excel_row) > 3 and excel_row[3] else ""

                frameset_raw = excel_row[4] if len(excel_row) > 4 else False
                frameset = str(frameset_raw).lower() in ("yes", "true", "1") if isinstance(frameset_raw, str) else bool(frameset_raw)

                disclaimer_raw = excel_row[5] if len(excel_row) > 5 else False
                disclaimer = str(disclaimer_raw).lower() in ("yes", "true", "1") if isinstance(disclaimer_raw, str) else bool(disclaimer_raw)

                # Setup row
                self._setup_table_row(table_row)

                # Set data using helper
                brand_widget = self._get_widget_from_cell(table_row, 0, ComboBox)
                if brand_widget and brand:
                    brand_widget.setCurrentText(brand)

                code_widget = self._get_widget_from_cell(table_row, 1, LineEdit)
                if code_widget:
                    code_widget.setText(code)

                url_widget = self._get_widget_from_cell(table_row, 2, LineEdit)
                if url_widget:
                    url_widget.setText(url)

                desc_widget = self._get_widget_from_cell(table_row, 3, ComboBox)
                if desc_widget and desc:
                    desc_widget.setCurrentText(desc)

                frameset_checkbox = self._get_widget_from_cell(table_row, 4, CheckBox)
                if frameset_checkbox:
                    frameset_checkbox.setChecked(frameset)

                disclaimer_checkbox = self._get_widget_from_cell(table_row, 5, CheckBox)
                if disclaimer_checkbox:
                    disclaimer_checkbox.setChecked(disclaimer)

                if brand and code and url:
                    valid_count += 1
                else:
                    invalid_count += 1

            wb.close()

            # Update UI
            import os
            self.excel_file_label.setText(os.path.basename(filename))
            self.table.setVisible(True)
            self.excel_empty.setVisible(False)

            # Update status
            if invalid_count > 0:
                self.status_label.setText(f"⚠ {valid_count} valid, {invalid_count} invalid rows - fix errors to continue")
                self.status_label.setStyleSheet(f"color: {COLORS['warning']}; font-weight: 500;")
                self.start_btn.setEnabled(False)
            else:
                self.status_label.setText(f"✓ {valid_count} product{'s' if valid_count != 1 else ''} ready from Excel")
                self.status_label.setStyleSheet(f"color: {COLORS['success']}; font-weight: 500;")
                self.start_btn.setEnabled(valid_count > 0)

        except Exception as ex:
            InfoBar.error(
                title="Error",
                content=f"Failed to load Excel: {str(ex)}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self
            )

    def _download_template(self):
        """Download Excel template"""
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Template",
            "ultrabike_batch_template.xlsx",
            "Excel files (*.xlsx)"
        )

        if not filename:
            return

        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Batch Upload"

            # Headers
            headers = ["Brand", "Product Code", "URL or Code", "Description", "Frameset", "Append Disclaimer"]
            ws.append(headers)

            # Examples
            ws.append(["KROSS", "UB-1234", "https://kross.pl/product1", "Mountain Bike", "No", "Yes"])
            ws.append(["Pinarello", "UB-5678", "https://pinarello.com/product2", "Road Bike", "Yes", "No"])

            # Style with our colors
            for cell in ws[1]:
                cell.font = Font(bold=True, color="FFFFFF", size=11)
                cell.fill = PatternFill(start_color="8D99AE", end_color="8D99AE", fill_type="solid")
                cell.alignment = Alignment(horizontal="center", vertical="center")

            # Auto-width
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = 20

            wb.save(filename)
            wb.close()

            InfoBar.success(
                title="Success",
                content="Template downloaded successfully",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

        except Exception as ex:
            InfoBar.error(
                title="Error",
                content=f"Failed to save template: {str(ex)}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self
            )

    def _start_upload(self):
        """Start batch upload"""
        items = []

        # Collect data from table using helper
        for row in range(self.table.rowCount()):
            brand_widget = self._get_widget_from_cell(row, 0, ComboBox)
            code_widget = self._get_widget_from_cell(row, 1, LineEdit)
            url_widget = self._get_widget_from_cell(row, 2, LineEdit)

            if not (brand_widget and code_widget and url_widget):
                continue

            brand = brand_widget.currentText()
            code = code_widget.text().strip()
            url = url_widget.text().strip()

            if not (brand and code and url):
                continue

            desc_widget = self._get_widget_from_cell(row, 3, ComboBox)
            desc = desc_widget.currentText() if desc_widget else ""

            frameset_checkbox = self._get_widget_from_cell(row, 4, CheckBox)
            frameset = frameset_checkbox.isChecked() if frameset_checkbox else False

            disclaimer_checkbox = self._get_widget_from_cell(row, 5, CheckBox)
            disclaimer = disclaimer_checkbox.isChecked() if disclaimer_checkbox else False

            items.append({
                'brand': brand,
                'code': code,
                'url': url,
                'description_name': desc,
                'frameset_only': frameset,
                'append_disclaimer': disclaimer
            })

        if not items:
            return

        # Process
        from Utilities.BatchProcessor import BatchProcessor

        batch_processor = BatchProcessor(
            driver=self.main.driver,
            db_manager=self.main.db,
            logger=self.main.logger
        )

        InfoBar.info(
            title="Batch Upload Started",
            content=f"Processing {len(items)} products...",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self
        )

        batch_processor.process_batch(items)

        InfoBar.success(
            title="Batch Complete",
            content="Check history for results",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self
        )

    def _update_table_theme(self):
        """Update table styling based on current theme"""
        is_dark = isDarkTheme()
        bg_color = COLORS['bg_dark'] if is_dark else COLORS['bg_light']
        alt_bg = COLORS['bg_alt_dark'] if is_dark else COLORS['bg_alt_light']
        border_color = COLORS['border_dark'] if is_dark else COLORS['border_light']
        header_bg = COLORS['space_indigo']
        text_color = COLORS['text_primary_dark'] if is_dark else COLORS['text_primary_light']

        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {bg_color};
                alternate-background-color: {alt_bg};
                border: 1px solid {border_color};
                border-radius: 8px;
                gridline-color: {border_color};
                selection-background-color: rgba(139, 153, 174, 0.2);
                color: {text_color};
            }}
            QTableWidget::item {{
                padding: 8px 12px;
                color: {text_color};
                border: none;
            }}
            QTableWidget::item:selected {{
                background-color: rgba(139, 153, 174, 0.15);
            }}
            QHeaderView::section {{
                background-color: {header_bg};
                color: {COLORS['lavender_grey']};
                padding: 12px 12px;
                border: none;
                font-weight: 600;
                font-size: 11px;
                letter-spacing: 0.5px;
                text-transform: uppercase;
            }}
            QHeaderView::section:first {{
                border-top-left-radius: 8px;
            }}
            QHeaderView::section:last {{
                border-top-right-radius: 8px;
            }}

            /* Custom scrollbar styling */
            QScrollBar:vertical {{
                background: transparent;
                width: 12px;
                margin: 0px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {'rgba(141, 153, 174, 0.3)' if is_dark else 'rgba(43, 45, 66, 0.2)'};
                border-radius: 6px;
                min-height: 30px;
                margin: 0px 2px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {'rgba(141, 153, 174, 0.5)' if is_dark else 'rgba(43, 45, 66, 0.3)'};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                border: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}

            QScrollBar:horizontal {{
                background: transparent;
                height: 12px;
                margin: 0px;
                border: none;
            }}
            QScrollBar::handle:horizontal {{
                background: {'rgba(141, 153, 174, 0.3)' if is_dark else 'rgba(43, 45, 66, 0.2)'};
                border-radius: 6px;
                min-width: 30px;
                margin: 2px 0px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {'rgba(141, 153, 174, 0.5)' if is_dark else 'rgba(43, 45, 66, 0.3)'};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
                border: none;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}
        """)

"""
Batch Upload Dialog
Modal dialog for uploading multiple products via manual entry or Excel import
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QScrollArea,
    QPushButton, QTabWidget, QFileDialog, QLabel
)
from PySide6.QtCore import Qt, Signal
from qfluentwidgets import (
    LineEdit, ComboBox, CheckBox, PrimaryPushButton, PushButton,
    BodyLabel, StrongBodyLabel, TransparentToolButton, FluentIcon,
    MessageBox, InfoBar, InfoBarPosition
)
import openpyxl
from openpyxl.styles import Font, PatternFill
from Managers.DescriptionManager import DescriptionManager


class BatchRowWidget(QWidget):
    """Single row for batch upload entry"""
    deleted = Signal(object)  # Emits self when deleted
    changed = Signal()  # Emits when any value changes

    def __init__(self, brands, descriptions, parent=None):
        super().__init__(parent)
        self.brands = brands
        self.descriptions = descriptions
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)

        # Brand dropdown
        self.brand_combo = ComboBox()
        self.brand_combo.addItems(self.brands)
        self.brand_combo.setPlaceholderText("Brand")
        self.brand_combo.setFixedWidth(120)
        self.brand_combo.currentTextChanged.connect(self._on_brand_change)
        self.brand_combo.currentTextChanged.connect(self.changed.emit)

        # Product code
        self.code_field = LineEdit()
        self.code_field.setPlaceholderText("UB-XXXX")
        self.code_field.setFixedWidth(120)
        self.code_field.textChanged.connect(self.changed.emit)

        # URL/Code
        self.url_field = LineEdit()
        self.url_field.setPlaceholderText("https://... or code")
        self.url_field.setFixedWidth(280)
        self.url_field.textChanged.connect(self.changed.emit)

        # Description
        self.desc_combo = ComboBox()
        self.desc_combo.addItem("")  # Empty option
        self.desc_combo.addItems(self.descriptions)
        self.desc_combo.setPlaceholderText("Description (optional)")
        self.desc_combo.setFixedWidth(200)
        self.desc_combo.currentTextChanged.connect(self.changed.emit)

        # Frameset checkbox (hidden by default)
        self.frameset_check = CheckBox()
        self.frameset_check.setToolTip("Pinarello: Frameset only")
        self.frameset_check.setVisible(False)
        self.frameset_check.setFixedWidth(70)
        self.frameset_check.stateChanged.connect(self.changed.emit)

        # Disclaimer checkbox
        self.disclaimer_check = CheckBox()
        self.disclaimer_check.setToolTip("Append disclaimer")
        self.disclaimer_check.setFixedWidth(50)
        self.disclaimer_check.stateChanged.connect(self.changed.emit)

        # Delete button
        delete_btn = TransparentToolButton(FluentIcon.DELETE, self)
        delete_btn.setToolTip("Remove row")
        delete_btn.clicked.connect(lambda: self.deleted.emit(self))
        delete_btn.setFixedWidth(32)

        layout.addWidget(self.brand_combo)
        layout.addWidget(self.code_field)
        layout.addWidget(self.url_field)
        layout.addWidget(self.desc_combo)
        layout.addWidget(self.frameset_check)
        layout.addWidget(self.disclaimer_check)
        layout.addWidget(delete_btn)
        layout.addStretch()

    def _on_brand_change(self, brand):
        """Show/hide frameset checkbox based on brand"""
        is_pinarello = brand == "Pinarello"
        self.frameset_check.setVisible(is_pinarello)
        if not is_pinarello:
            self.frameset_check.setChecked(False)

    def is_valid(self):
        """Check if row has required data"""
        return bool(
            self.brand_combo.currentText() and
            self.code_field.text().strip() and
            self.url_field.text().strip()
        )

    def get_data(self):
        """Get row data as dict"""
        return {
            'brand': self.brand_combo.currentText(),
            'code': self.code_field.text().strip(),
            'url': self.url_field.text().strip(),
            'description_name': self.desc_combo.currentText(),
            'frameset_only': self.frameset_check.isChecked(),
            'append_disclaimer': self.disclaimer_check.isChecked()
        }

    def set_data(self, data):
        """Set row data from dict"""
        if 'brand' in data:
            self.brand_combo.setCurrentText(data['brand'])
        if 'code' in data:
            self.code_field.setText(data['code'])
        if 'url' in data:
            self.url_field.setText(data['url'])
        if 'description_name' in data and data['description_name']:
            self.desc_combo.setCurrentText(data['description_name'])
        if 'frameset_only' in data:
            self.frameset_check.setChecked(data['frameset_only'])
        if 'append_disclaimer' in data:
            self.disclaimer_check.setChecked(data['append_disclaimer'])


class BatchUploadDialog(QDialog):
    """Batch upload dialog with manual and Excel entry"""
    batch_started = Signal(list)  # Emits list of items to process

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.setWindowTitle("Batch Upload")
        self.resize(1100, 650)

        # Load descriptions
        desc_manager = DescriptionManager(main_window.db)
        self.descriptions = [d['name'] for d in desc_manager.list_descriptions()]

        # Brands list
        self.brands = [
            "KROSS", "Pinarello", "Basso", "Factor",
            "TREK", "Rondo", "Octane", "Rascal", "Lee Cougan"
        ]

        self._init_ui()

    def _init_ui(self):
        """Initialize UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Title
        title = StrongBodyLabel("Batch Upload")
        title.setStyleSheet("font-size: 20px;")
        layout.addWidget(title)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_manual_tab(), "Manual Entry")
        self.tabs.addTab(self._create_excel_tab(), "Excel Upload")
        layout.addWidget(self.tabs)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = PushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        self.start_btn = PrimaryPushButton("Start Batch Upload")
        self.start_btn.setIcon(FluentIcon.PLAY)
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._handle_start)

        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(self.start_btn)
        layout.addLayout(button_layout)

    def _create_manual_tab(self):
        """Create manual entry tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        # Header row
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setSpacing(8)
        header_layout.setContentsMargins(0, 0, 0, 0)

        header_layout.addWidget(BodyLabel("Brand"))
        header_layout.addWidget(BodyLabel("Product Code"), 0, Qt.AlignmentFlag.AlignLeft)
        header_layout.addWidget(BodyLabel("URL or Code"), 0, Qt.AlignmentFlag.AlignLeft)
        header_layout.addWidget(BodyLabel("Description"), 0, Qt.AlignmentFlag.AlignLeft)

        # Frameset select-all
        frameset_col = QWidget()
        frameset_col_layout = QVBoxLayout(frameset_col)
        frameset_col_layout.setSpacing(2)
        frameset_col_layout.setContentsMargins(0, 0, 0, 0)
        frameset_label = BodyLabel("Frameset")
        frameset_label.setToolTip("Pinarello only")
        self.frameset_select_all = CheckBox()
        self.frameset_select_all.setToolTip("Select/Deselect all")
        self.frameset_select_all.stateChanged.connect(self._toggle_all_framesets)
        frameset_col_layout.addWidget(frameset_label)
        frameset_col_layout.addWidget(self.frameset_select_all)
        frameset_col.setFixedWidth(70)
        header_layout.addWidget(frameset_col)

        # Disclaimer select-all
        disc_col = QWidget()
        disc_col_layout = QVBoxLayout(disc_col)
        disc_col_layout.setSpacing(2)
        disc_col_layout.setContentsMargins(0, 0, 0, 0)
        disc_label = BodyLabel("Disc")
        disc_label.setToolTip("Append disclaimer")
        self.disc_select_all = CheckBox()
        self.disc_select_all.setToolTip("Select/Deselect all")
        self.disc_select_all.stateChanged.connect(self._toggle_all_disclaimers)
        disc_col_layout.addWidget(disc_label)
        disc_col_layout.addWidget(self.disc_select_all)
        disc_col.setFixedWidth(50)
        header_layout.addWidget(disc_col)

        header_layout.addSpacing(32)  # Space for delete button
        header_layout.addStretch()

        layout.addWidget(header)

        # Scroll area for rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        rows_container = QWidget()
        self.manual_rows_layout = QVBoxLayout(rows_container)
        self.manual_rows_layout.setSpacing(8)
        self.manual_rows_layout.addStretch()

        scroll.setWidget(rows_container)
        layout.addWidget(scroll, 1)

        # Add initial rows
        for _ in range(10):
            self._add_manual_row()

        # Action buttons
        actions = QHBoxLayout()
        add_btn = PushButton("Add Row")
        add_btn.setIcon(FluentIcon.ADD)
        add_btn.clicked.connect(self._add_manual_row)

        clear_btn = PushButton("Clear All")
        clear_btn.setIcon(FluentIcon.DELETE)
        clear_btn.clicked.connect(self._clear_manual_rows)

        actions.addWidget(add_btn)
        actions.addWidget(clear_btn)
        actions.addStretch()
        layout.addLayout(actions)

        return widget

    def _create_excel_tab(self):
        """Create Excel upload tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        # File selection
        file_row = QHBoxLayout()
        browse_btn = PushButton("Browse Excel File")
        browse_btn.setIcon(FluentIcon.FOLDER)
        browse_btn.clicked.connect(self._browse_excel)

        template_btn = PushButton("Download Template")
        template_btn.setIcon(FluentIcon.DOWNLOAD)
        template_btn.clicked.connect(self._download_template)

        file_row.addWidget(browse_btn)
        file_row.addWidget(template_btn)
        file_row.addStretch()
        layout.addLayout(file_row)

        self.excel_filename_label = BodyLabel("No file selected")
        self.excel_filename_label.setStyleSheet("color: #9CA3AF;")
        layout.addWidget(self.excel_filename_label)

        # Empty state
        self.excel_empty_state = QWidget()
        empty_layout = QVBoxLayout(self.excel_empty_state)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon = BodyLabel("📤")
        empty_icon.setStyleSheet("font-size: 64px;")
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_text1 = BodyLabel("Upload an Excel file to begin")
        empty_text1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_text2 = BodyLabel("or download the template to get started")
        empty_text2.setStyleSheet("color: #9CA3AF;")
        empty_text2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon)
        empty_layout.addWidget(empty_text1)
        empty_layout.addWidget(empty_text2)
        layout.addWidget(self.excel_empty_state, 1)

        # Preview (hidden initially)
        self.excel_preview_widget = QWidget()
        self.excel_preview_widget.setVisible(False)
        preview_layout = QVBoxLayout(self.excel_preview_widget)
        preview_layout.setSpacing(8)

        preview_layout.addWidget(StrongBodyLabel("Preview"))

        # Preview scroll
        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        preview_container = QWidget()
        self.excel_rows_layout = QVBoxLayout(preview_container)
        self.excel_rows_layout.setSpacing(8)
        self.excel_rows_layout.addStretch()

        preview_scroll.setWidget(preview_container)
        preview_layout.addWidget(preview_scroll, 1)

        self.excel_status_label = BodyLabel("")
        preview_layout.addWidget(self.excel_status_label)

        layout.addWidget(self.excel_preview_widget, 1)

        return widget

    def _add_manual_row(self):
        """Add a manual entry row"""
        row = BatchRowWidget(self.brands, self.descriptions, self)
        row.deleted.connect(self._remove_row)
        row.changed.connect(self._validate_manual)
        self.manual_rows_layout.insertWidget(self.manual_rows_layout.count() - 1, row)
        self._validate_manual()

    def _remove_row(self, row):
        """Remove a row"""
        self.manual_rows_layout.removeWidget(row)
        row.deleteLater()
        self._validate_manual()

    def _clear_manual_rows(self):
        """Clear all manual rows"""
        while self.manual_rows_layout.count() > 1:  # Keep the stretch
            item = self.manual_rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add 10 new rows
        for _ in range(10):
            self._add_manual_row()

    def _toggle_all_framesets(self, state):
        """Toggle all frameset checkboxes"""
        checked = state == Qt.CheckState.Checked.value
        for i in range(self.manual_rows_layout.count() - 1):
            widget = self.manual_rows_layout.itemAt(i).widget()
            if isinstance(widget, BatchRowWidget):
                if widget.brand_combo.currentText() == "Pinarello":
                    widget.frameset_check.setChecked(checked)

    def _toggle_all_disclaimers(self, state):
        """Toggle all disclaimer checkboxes"""
        checked = state == Qt.CheckState.Checked.value
        for i in range(self.manual_rows_layout.count() - 1):
            widget = self.manual_rows_layout.itemAt(i).widget()
            if isinstance(widget, BatchRowWidget):
                widget.disclaimer_check.setChecked(checked)

    def _validate_manual(self):
        """Validate manual entry rows"""
        valid_count = 0
        for i in range(self.manual_rows_layout.count() - 1):
            widget = self.manual_rows_layout.itemAt(i).widget()
            if isinstance(widget, BatchRowWidget) and widget.is_valid():
                valid_count += 1

        # Only update button if it exists (avoid error during initialization)
        if hasattr(self, 'start_btn'):
            self.start_btn.setEnabled(valid_count > 0)

    def _browse_excel(self):
        """Browse for Excel file"""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Excel File",
            "",
            "Excel files (*.xlsx);;All files (*.*)"
        )

        if filename:
            self.excel_filename_label.setText(filename)
            self._load_excel_preview(filename)

    def _load_excel_preview(self, filename):
        """Load and preview Excel file"""
        try:
            wb = openpyxl.load_workbook(filename)
            ws = wb.active

            # Clear existing preview
            while self.excel_rows_layout.count() > 1:
                item = self.excel_rows_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            # Find header row
            header_row = None
            for idx, row in enumerate(ws.iter_rows(min_row=1, max_row=5), start=1):
                values = [str(c.value).lower() if c.value else "" for c in row]
                if any("brand" in v for v in values):
                    header_row = idx
                    break

            if not header_row:
                self.excel_status_label.setText("Could not find header row")
                self.excel_status_label.setStyleSheet("color: #F59E0B;")
                self.start_btn.setEnabled(False)
                wb.close()
                return

            valid_count = 0
            invalid_count = 0

            # Process rows
            for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
                if not any(row):
                    continue

                brand = str(row[0]) if len(row) > 0 and row[0] else ""
                code = str(row[1]) if len(row) > 1 and row[1] else ""
                url = str(row[2]) if len(row) > 2 and row[2] else ""
                desc = str(row[3]).strip() if len(row) > 3 and row[3] and str(row[3]).strip() else ""

                # Parse frameset (column 4)
                frameset_raw = row[4] if len(row) > 4 and row[4] else False
                if isinstance(frameset_raw, str):
                    frameset = frameset_raw.strip().lower() in ("yes", "true", "1", "frameset")
                else:
                    frameset = bool(frameset_raw)

                # Parse disclaimer (column 5)
                disclaimer_raw = row[5] if len(row) > 5 and row[5] else False
                if isinstance(disclaimer_raw, str):
                    disclaimer = disclaimer_raw.strip().lower() in ("yes", "true", "1")
                else:
                    disclaimer = bool(disclaimer_raw)

                # Create row widget
                row_widget = BatchRowWidget(self.brands, self.descriptions, self)
                row_widget.set_data({
                    'brand': brand,
                    'code': code,
                    'url': url,
                    'description_name': desc,
                    'frameset_only': frameset,
                    'append_disclaimer': disclaimer
                })
                row_widget.changed.connect(self._validate_excel)

                if row_widget.is_valid():
                    valid_count += 1
                    row_widget.setStyleSheet("background-color: #ECFDF5; border-radius: 4px; padding: 4px;")
                else:
                    invalid_count += 1
                    row_widget.setStyleSheet("background-color: #FEF2F2; border-radius: 4px; padding: 4px;")

                self.excel_rows_layout.insertWidget(self.excel_rows_layout.count() - 1, row_widget)

            # Update status
            if invalid_count > 0:
                self.excel_status_label.setText(f"{valid_count} valid, {invalid_count} invalid rows")
                self.excel_status_label.setStyleSheet("color: #F59E0B;")
                self.start_btn.setEnabled(False)
            else:
                self.excel_status_label.setText(f"{valid_count} valid rows ready")
                self.excel_status_label.setStyleSheet("color: #10B981;")
                self.start_btn.setEnabled(valid_count > 0)

            # Show preview, hide empty state
            self.excel_empty_state.setVisible(False)
            self.excel_preview_widget.setVisible(True)

            wb.close()

        except Exception as ex:
            self.excel_status_label.setText(f"Error: {str(ex)}")
            self.excel_status_label.setStyleSheet("color: #EF4444;")
            self.start_btn.setEnabled(False)

    def _validate_excel(self):
        """Validate Excel preview rows"""
        valid_count = 0
        invalid_count = 0

        for i in range(self.excel_rows_layout.count() - 1):
            widget = self.excel_rows_layout.itemAt(i).widget()
            if isinstance(widget, BatchRowWidget):
                if widget.is_valid():
                    valid_count += 1
                    widget.setStyleSheet("background-color: #ECFDF5; border-radius: 4px; padding: 4px;")
                else:
                    invalid_count += 1
                    widget.setStyleSheet("background-color: #FEF2F2; border-radius: 4px; padding: 4px;")

        # Only update if widgets exist
        if hasattr(self, 'excel_status_label'):
            if invalid_count > 0:
                self.excel_status_label.setText(f"{valid_count} valid, {invalid_count} invalid rows")
                self.excel_status_label.setStyleSheet("color: #F59E0B;")
            else:
                self.excel_status_label.setText(f"{valid_count} valid rows ready")
                self.excel_status_label.setStyleSheet("color: #10B981;")

        if hasattr(self, 'start_btn'):
            if invalid_count > 0:
                self.start_btn.setEnabled(False)
            else:
                self.start_btn.setEnabled(valid_count > 0)

    def _download_template(self):
        """Download Excel template"""
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Template As",
            "ultrabike_batch_template.xlsx",
            "Excel files (*.xlsx)"
        )

        if not filename:
            return

        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Batch Upload"

            # Header
            ws.append(["Brand", "Product Code", "URL or Code", "Description", "Frameset", "Append Disclaimer"])

            # Examples
            ws.append(["KROSS", "UB-1234", "https://kross.pl/product1", "Mountain Bike", "No", "Yes"])
            ws.append(["Pinarello", "UB-5678", "https://pinarello.com/product2", "Road Bike", "Yes", "No"])

            # Style header
            for cell in ws[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")

            wb.save(filename)
            wb.close()

            InfoBar.success(
                title="Success",
                content=f"Template saved to {filename}",
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
                duration=3000,
                parent=self
            )

    def _handle_start(self):
        """Handle start batch upload"""
        items = []

        if self.tabs.currentIndex() == 0:  # Manual entry
            for i in range(self.manual_rows_layout.count() - 1):
                widget = self.manual_rows_layout.itemAt(i).widget()
                if isinstance(widget, BatchRowWidget) and widget.is_valid():
                    items.append(widget.get_data())
        else:  # Excel
            for i in range(self.excel_rows_layout.count() - 1):
                widget = self.excel_rows_layout.itemAt(i).widget()
                if isinstance(widget, BatchRowWidget) and widget.is_valid():
                    items.append(widget.get_data())

        if items:
            self.batch_started.emit(items)
            self.accept()

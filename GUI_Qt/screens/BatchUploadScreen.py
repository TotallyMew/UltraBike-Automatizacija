"""
Batch Upload Screen - Complete Redesign
Fluent Design System with Space Indigo/Lavender color scheme
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Signal, QTimer, QEvent
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent
from qfluentwidgets import (
    LineEdit, ComboBox, CheckBox, PrimaryPushButton, PushButton,
    BodyLabel, TitleLabel, StrongBodyLabel, CaptionLabel,
    TransparentToolButton, FluentIcon, InfoBar, InfoBarPosition,
    ScrollArea, CardWidget, PillPushButton, isDarkTheme, TransparentPushButton, IconWidget, qconfig
)
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from Managers.DescriptionManager import DescriptionManager
from GUI_Qt.styles.theme_config import COLORS, FONTS, COMPONENT_COLORS


# Removed old ProductRow CardWidget class - replaced with modern table


class DropZoneWidget(QWidget):
    """Drag and drop zone for Excel files"""
    file_dropped = Signal(str)

    def __init__(self, tr, parent=None):
        super().__init__(parent)
        self.tr = tr
        self.title_label = None
        self.subtitle_label = None
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
        self.title_label = StrongBodyLabel("")
        title = self.title_label
        title.setStyleSheet(f"font-size: 16px; color: {COLORS['lavender_grey']};")

        # Subtitle
        self.subtitle_label = CaptionLabel("")
        subtitle = self.subtitle_label
        subtitle.setStyleSheet(f"color: {COLORS['text_secondary']};")

        layout.addStretch()
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

        # Style (theme-consistent)
        self._apply_style()

        # Make clickable
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.retranslate_ui()

    def retranslate_ui(self):
        if self.title_label is not None:
            self.title_label.setText(self.tr("batch.drop.title"))
        if self.subtitle_label is not None:
            self.subtitle_label.setText(self.tr("batch.drop.subtitle"))

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1 and urls[0].toLocalFile().endswith('.xlsx'):
                event.acceptProposedAction()
                self._apply_style(is_drag_active=True)

    def dragLeaveEvent(self, event):
        self._apply_style()

    def dropEvent(self, event: QDropEvent):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        if files and files[0].endswith('.xlsx'):
            self.file_dropped.emit(files[0])
        self._apply_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.file_dropped.emit("__browse__")  # Signal to open file dialog

    def _apply_style(self, is_drag_active: bool = False):
        is_dark = isDarkTheme()
        border = COLORS['lavender_grey'] if is_dark else COLORS['space_indigo']
        dashed = COLORS['lavender_grey']
        hover_bg = f"rgba(141, 153, 174, {0.10 if is_dark else 0.06})"

        if is_drag_active:
            # Stronger visual state when file is being dragged over
            self.setStyleSheet(f"""
                DropZoneWidget {{
                    background-color: {hover_bg};
                    border: 2px solid {border};
                    border-radius: 12px;
                }}
            """)
            return

        self.setStyleSheet(f"""
            DropZoneWidget {{
                background-color: transparent;
                border: 2px dashed {dashed};
                border-radius: 12px;
            }}
            DropZoneWidget:hover {{
                border-color: {border};
                background-color: {hover_bg};
            }}
        """)


class BatchUploadScreen(QWidget):
    """Complete redesign with Fluent Design System"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.current_mode = "manual"
        self.row_counter = 0
        self._base_table_rows = 5

        # Load descriptions
        desc_manager = DescriptionManager(main_window.db)
        self.descriptions = [d['name'] for d in desc_manager.list_descriptions()]

        # Brands
        self.brands = [
            "KROSS", "Pinarello", "Basso", "Factor",
            "TREK", "Rondo", "Octane", "Rascal", "Lee Cougan"
        ]

        self._init_ui()

        # Connect to theme change signal
        qconfig.themeChangedFinished.connect(self._on_theme_changed)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._ensure_table_fills_viewport)

    def eventFilter(self, obj, event):
        if hasattr(self, "table") and obj is self.table.viewport() and event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self._ensure_table_fills_viewport)
        return super().eventFilter(obj, event)

    def _ensure_table_fills_viewport(self):
        """Add empty rows so the table fills its visible height.

        This prevents a large blank area under the last row on big windows.
        """
        if not hasattr(self, "table"):
            return
        if not self.table.isVisible():
            return
        if hasattr(self, "excel_empty") and self.excel_empty.isVisible():
            return

        viewport = self.table.viewport()
        if viewport is None:
            return
        viewport_height = viewport.height()
        if viewport_height <= 0:
            return

        row_height = self.table.verticalHeader().defaultSectionSize() or 56
        target_rows = (viewport_height + row_height - 1) // row_height + 1
        target_rows = max(self._base_table_rows, int(target_rows))
        target_rows = min(target_rows, 50)

        current_rows = self.table.rowCount()
        if current_rows >= target_rows:
            return

        self.table.setRowCount(target_rows)
        for row in range(current_rows, target_rows):
            self._setup_table_row(row)

    def _find_row_for_sender(self, column: int, widget_type):
        sender = self.sender()
        if sender is None:
            return None
        for row in range(self.table.rowCount()):
            cell = self.table.cellWidget(row, column)
            if not cell:
                continue
            w = cell.findChild(widget_type)
            if w is sender:
                return row
        return None

    def _init_ui(self):
        """Initialize UI with proper Fluent Design"""
        # Apply background color and font
        is_dark = isDarkTheme()
        bg_color = COLORS['space_indigo'] if is_dark else COLORS['platinum']

        self.setStyleSheet(f"""
            BatchUploadScreen {{
                background-color: {bg_color};
                font-family: {FONTS['family']};
            }}
        """)
        self.setAutoFillBackground(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 20, 40, 20)  # Fluent standard: 40px sides
        layout.setSpacing(20)

        # === HEADER SECTION ===
        header = QHBoxLayout()

        # Title
        self.title_label = TitleLabel("")
        header.addWidget(self.title_label)
        header.addStretch()

        # Mode pills (Fluent Design style)
        mode_container = QWidget()
        mode_layout = QHBoxLayout(mode_container)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(8)
        mode_container.setStyleSheet("background: transparent;")

        self.manual_pill = PillPushButton("")
        self.manual_pill.setCheckable(True)
        self.manual_pill.setChecked(True)
        self.manual_pill.clicked.connect(lambda: self._switch_mode("manual"))

        self.excel_pill = PillPushButton("")
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

        self.add_btn = PushButton("")
        add_btn = self.add_btn
        add_btn.setIcon(FluentIcon.ADD)
        add_btn.clicked.connect(self._add_row)

        self.clear_btn = TransparentPushButton("")
        clear_btn = self.clear_btn
        clear_btn.setIcon(FluentIcon.DELETE)
        clear_btn.clicked.connect(self._clear_all)

        # Bulk selectors
        self.bulk_label = CaptionLabel("")
        bulk_label = self.bulk_label
        bulk_label.setStyleSheet(f"color: {COLORS['text_secondary']}; margin-left: 20px;")

        self.frameset_bulk = CheckBox("")
        frameset_bulk = self.frameset_bulk
        frameset_bulk.stateChanged.connect(self._toggle_all_framesets)

        self.disclaimer_bulk = CheckBox("")
        disclaimer_bulk = self.disclaimer_bulk
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

        self.browse_btn = PushButton("")
        browse_btn = self.browse_btn
        browse_btn.setIcon(FluentIcon.FOLDER)
        browse_btn.clicked.connect(self._browse_excel)

        self.template_btn = TransparentPushButton("")
        template_btn = self.template_btn
        template_btn.setIcon(FluentIcon.DOWNLOAD)
        template_btn.clicked.connect(self._download_template)

        self.excel_file_label = BodyLabel("")
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
        content_layout.setContentsMargins(24, 20, 24, 20)  # Fluent standard card padding
        content_layout.setSpacing(16)

        # Modern Fluent table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["", "", "", "", "", "", ""])
        self.table.setRowCount(self._base_table_rows)

        # Apply table styling
        self._update_table_theme()

        # Table settings
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setMinimumHeight(48)
        self.table.verticalHeader().setVisible(False)
        # Slightly taller rows prevent border clipping on high-DPI systems
        self.table.verticalHeader().setDefaultSectionSize(60)
        self.table.setShowGrid(True)

        # Auto-fill rows when the table viewport resizes
        self.table.viewport().installEventFilter(self)

        # Enable corner clipping for rounded borders
        self.table.setCornerButtonEnabled(False)

        # Column widths - responsive design
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Brand - flexible
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)    # Code - fixed
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # URL - flexible
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)  # Description - flexible
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Frameset - auto
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Disclaimer - auto
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)    # Delete - fixed

        # Set minimum widths for stretching columns
        self.table.setColumnWidth(0, 180)  # Brand minimum (avoid placeholder truncation)
        self.table.setColumnWidth(1, 140)  # Code fixed
        self.table.setColumnWidth(3, 200)  # Description minimum
        self.table.setColumnWidth(6, 60)   # Delete fixed

        # Populate initial rows
        for row in range(self._base_table_rows):
            self._setup_table_row(row)

        # Fill remaining visible area with extra empty rows (useful on 1080p+).
        QTimer.singleShot(0, self._ensure_table_fills_viewport)

        # Table container with max-width for better layout on large screens
        table_container = QWidget()
        table_container.setStyleSheet("background: transparent;")
        table_container_layout = QVBoxLayout(table_container)
        table_container_layout.setContentsMargins(0, 0, 0, 0)
        table_container_layout.addWidget(self.table, 1)

        content_layout.addWidget(table_container, 1)

        # Excel drop zone
        self.excel_empty = DropZoneWidget(self.main.i18n.tr)
        self.excel_empty.file_dropped.connect(self._handle_file_drop)
        self.excel_empty.setVisible(False)
        content_layout.addWidget(self.excel_empty, 1)

        layout.addWidget(content_card, 1)

        # === ACTION BAR ===
        actions = QHBoxLayout()
        self.status_label = BodyLabel("")
        self.status_label.setStyleSheet(f"color: {COLORS['text_secondary']};")

        actions.addWidget(self.status_label)
        actions.addStretch()

        self.start_btn = PrimaryPushButton("")
        self.start_btn.setIcon(FluentIcon.PLAY)
        self.start_btn.setEnabled(False)
        self.start_btn.setFixedHeight(40)
        self.start_btn.clicked.connect(self._start_upload)

        actions.addWidget(self.start_btn)
        layout.addLayout(actions)

        self.retranslate_ui()

    def retranslate_ui(self):
        tr = self.main.i18n.tr

        self.title_label.setText(tr("batch.title"))
        self.manual_pill.setText(tr("batch.mode.manual"))
        self.excel_pill.setText(tr("batch.mode.excel"))

        self.add_btn.setText(tr("batch.add_row"))
        self.clear_btn.setText(tr("batch.clear_all"))
        self.bulk_label.setText(tr("batch.bulk_select"))
        self.frameset_bulk.setText(tr("batch.bulk.frameset"))
        self.frameset_bulk.setToolTip(tr("batch.bulk.frameset.tip"))
        self.disclaimer_bulk.setText(tr("batch.bulk.disclaimer"))
        self.disclaimer_bulk.setToolTip(tr("batch.bulk.disclaimer.tip"))

        self.browse_btn.setText(tr("batch.browse_excel"))
        self.template_btn.setText(tr("batch.download_template"))
        self.excel_file_label.setText(tr("batch.no_file"))

        self.status_label.setText(tr("batch.status.ready"))
        self.start_btn.setText(tr("batch.start"))

        # Table headers
        self.table.setHorizontalHeaderLabels([
            tr("batch.table.brand"),
            tr("batch.table.code"),
            tr("batch.table.url"),
            tr("batch.table.desc"),
            tr("batch.table.frameset"),
            tr("batch.table.disclaimer"),
            "",
        ])

        # Drop-zone text
        if hasattr(self, "excel_empty") and hasattr(self.excel_empty, "retranslate_ui"):
            self.excel_empty.retranslate_ui()

        # Update placeholders for existing table row widgets
        for row in range(self.table.rowCount()):
            brand_cell = self.table.cellWidget(row, 0)
            if brand_cell:
                brand_combo = brand_cell.findChild(ComboBox)
                if brand_combo:
                    brand_combo.setPlaceholderText(tr("batch.select_brand"))

            code_cell = self.table.cellWidget(row, 1)
            if code_cell:
                code_field = code_cell.findChild(LineEdit)
                if code_field:
                    code_field.setPlaceholderText(tr("upload.code.placeholder"))

            url_cell = self.table.cellWidget(row, 2)
            if url_cell:
                url_field = url_cell.findChild(LineEdit)
                if url_field:
                    url_field.setPlaceholderText(tr("upload.url.placeholder"))

            desc_cell = self.table.cellWidget(row, 3)
            if desc_cell:
                desc_combo = desc_cell.findChild(ComboBox)
                if desc_combo:
                    desc_combo.setPlaceholderText(tr("batch.optional"))

    def _setup_table_row(self, row):
        """Setup widgets for a table row"""
        # Helper to create centered container
        def create_centered_widget(widget):
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            container.setProperty("ubTableCell", True)
            layout = QHBoxLayout(container)
            # Inset widgets from gridlines so their borders are never clipped/overdrawn
            layout.setContentsMargins(10, 6, 10, 6)
            layout.setSpacing(0)
            layout.addWidget(widget, 1)
            layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            return container

        # Brand combo
        brand_combo = ComboBox()
        brand_combo.addItems(self.brands)
        brand_combo.setPlaceholderText(self.main.i18n.tr("batch.select_brand"))
        brand_combo.setMinimumHeight(36)
        brand_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        brand_combo.setMinimumWidth(160)
        brand_combo.currentTextChanged.connect(self._on_brand_change)
        brand_combo.currentTextChanged.connect(self._validate)
        self.table.setCellWidget(row, 0, create_centered_widget(brand_combo))

        # Product code
        code_field = LineEdit()
        code_field.setPlaceholderText(self.main.i18n.tr("upload.code.placeholder"))
        code_field.setMinimumHeight(36)
        code_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        code_field.textChanged.connect(lambda text, field=code_field: self._on_code_changed(text, field))
        self.table.setCellWidget(row, 1, create_centered_widget(code_field))

        # URL
        url_field = LineEdit()
        url_field.setPlaceholderText(self.main.i18n.tr("upload.url.placeholder"))
        url_field.setMinimumHeight(36)
        url_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        url_field.textChanged.connect(lambda text, field=url_field: self._on_url_changed(text, field))
        self.table.setCellWidget(row, 2, create_centered_widget(url_field))

        # Description
        desc_combo = ComboBox()
        desc_combo.addItem("")
        desc_combo.addItems(self.descriptions)
        desc_combo.setPlaceholderText(self.main.i18n.tr("batch.optional"))
        desc_combo.setMinimumHeight(36)
        desc_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
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
        delete_btn.setToolTip(self.main.i18n.tr("batch.row.remove.tip"))
        delete_btn.setFixedSize(36, 36)
        delete_btn.clicked.connect(self._remove_row)
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

    def _on_brand_change(self, brand):
        """Handle brand change to show/hide frameset checkbox"""
        row = self._find_row_for_sender(0, ComboBox)
        if row is None:
            return
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
            QTimer.singleShot(0, self._ensure_table_fills_viewport)

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
        QTimer.singleShot(0, self._ensure_table_fills_viewport)
        self._validate()

    def _remove_row(self):
        """Remove a row from table"""
        row = self._find_row_for_sender(6, TransparentToolButton)
        if row is None:
            return
        if self.table.rowCount() > 1:
            self.table.removeRow(row)
            QTimer.singleShot(0, self._ensure_table_fills_viewport)
            self._validate()

    def _clear_all(self):
        """Clear all rows"""
        self.table.setRowCount(self._base_table_rows)
        for row in range(self._base_table_rows):
            self._setup_table_row(row)
        QTimer.singleShot(0, self._ensure_table_fills_viewport)
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
        self._validate()

    def _on_url_changed(self, text, field):
        """Handle URL field change with validation"""
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
            key = "batch.status.ready_one" if valid_count == 1 else "batch.status.ready_many"
            self.status_label.setText(self.main.i18n.tr(key, count=valid_count))
            self.status_label.setStyleSheet(f"color: {COLORS['success']}; font-weight: 500;")
        else:
            self.status_label.setText(self.main.i18n.tr("batch.status.need_one"))
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
            self.main.i18n.tr("batch.file.select_excel.title"),
            "",
            self.main.i18n.tr("batch.file.select_excel.filter")
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
                raise Exception(self.main.i18n.tr("batch.excel.header_missing_in_file"))

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
                self.status_label.setText(
                    self.main.i18n.tr(
                        "batch.excel.rows_fix_errors",
                        valid=valid_count,
                        invalid=invalid_count,
                    )
                )
                self.status_label.setStyleSheet(f"color: {COLORS['warning']}; font-weight: 500;")
                self.start_btn.setEnabled(False)
            else:
                key = "batch.excel.ready_from_excel_one" if valid_count == 1 else "batch.excel.ready_from_excel_many"
                self.status_label.setText(self.main.i18n.tr(key, count=valid_count))
                self.status_label.setStyleSheet(f"color: {COLORS['success']}; font-weight: 500;")
                self.start_btn.setEnabled(valid_count > 0)

        except Exception as ex:
            InfoBar.error(
                title=self.main.i18n.tr("common.error"),
                content=self.main.i18n.tr("batch.excel.load_failed", error=str(ex)),
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
            self.main.i18n.tr("batch.template.save.title"),
            self.main.i18n.tr("batch.template.default_name"),
            self.main.i18n.tr("batch.template.filter"),
        )

        if not filename:
            return

        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = self.main.i18n.tr("batch.title")

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
                title=self.main.i18n.tr("common.success"),
                content=self.main.i18n.tr("batch.template.downloaded"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

        except Exception as ex:
            InfoBar.error(
                title=self.main.i18n.tr("common.error"),
                content=self.main.i18n.tr("batch.template.save_failed", error=str(ex)),
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

        # If batch includes brands that use external credentials, ensure master is unlocked
        master_password = getattr(self.main, "_unlocked_master_password", None)
        try:
            needs_master = False
            for it in items:
                if it.get('brand') == 'Basso':
                    if not self.main.credential_manager.has_external_credentials('basso'):
                        InfoBar.error(
                            title=self.main.i18n.tr("common.error"),
                            content=self.main.i18n.tr("account.brand_missing", brand='Basso'),
                            orient=Qt.Orientation.Horizontal,
                            isClosable=True,
                            position=InfoBarPosition.TOP,
                            duration=5000,
                            parent=self
                        )
                        return
                    needs_master = True

                if it.get('brand') == 'Lee Cougan':
                    if not self.main.credential_manager.has_external_credentials('leecougan'):
                        InfoBar.error(
                            title=self.main.i18n.tr("common.error"),
                            content=self.main.i18n.tr("account.brand_missing", brand='Lee Cougan'),
                            orient=Qt.Orientation.Horizontal,
                            isClosable=True,
                            position=InfoBarPosition.TOP,
                            duration=5000,
                            parent=self
                        )
                        return
                    needs_master = True

                if needs_master:
                    break
            if needs_master:
                master_password = self.main.get_unlocked_master_password(parent=self)
                if not master_password:
                    InfoBar.error(
                        title=self.main.i18n.tr("common.error"),
                        content=self.main.i18n.tr("master.invalid.content"),
                        orient=Qt.Orientation.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP,
                        duration=4000,
                        parent=self
                    )
                    return
        except Exception:
            pass

        # Process
        from Utilities.BatchProcessor import BatchProcessor

        batch_processor = BatchProcessor(
            driver=self.main.driver,
            db_manager=self.main.db,
            logger=self.main.logger
        )

        InfoBar.info(
            title=self.main.i18n.tr("batch.run.started.title"),
            content=self.main.i18n.tr("batch.run.started.content", count=len(items)),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self
        )

        batch_processor.process_batch(items, master_password=master_password)

        InfoBar.success(
            title=self.main.i18n.tr("batch.run.complete.title"),
            content=self.main.i18n.tr("batch.run.complete.content"),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self
        )

    def _update_table_theme(self):
        """Update table styling based on current theme"""
        is_dark = isDarkTheme()
        table_colors = COMPONENT_COLORS['table']
        # Use slightly-tinted base rows so white inputs don't blend into the table.
        bg_color = table_colors['row_alt_bg_dark'] if is_dark else table_colors['row_alt_bg_light']
        alt_bg = table_colors['row_bg_dark'] if is_dark else table_colors['row_bg_light']
        border_color = table_colors['border_dark'] if is_dark else table_colors['border_light']

        # Header colors: lavender_grey for dark mode, space_indigo for light mode
        header_bg = COLORS['lavender_grey'] if is_dark else COLORS['space_indigo']
        header_text = COLORS['space_indigo'] if is_dark else COLORS['text_white']

        text_color = COLORS['text_primary_dark'] if is_dark else COLORS['text_primary_light']

        # Stronger default borders for inputs embedded inside the table.
        # This avoids "border disappears" issues against light table backgrounds.
        embedded_input_border = (
            "rgba(141, 153, 174, 0.55)" if is_dark else "rgba(43, 45, 66, 0.30)"
        )

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
                background-color: {COLORS['lavender_grey']};
                color: {COLORS['space_indigo'] if is_dark else COLORS['text_white']};
            }}
            QHeaderView::section {{
                background-color: {header_bg};
                color: {header_text};
                padding: 12px 12px;
                border: none;
                font-weight: 600;
                font-size: 13px;
                letter-spacing: 0.5px;
                text-transform: uppercase;
            }}
            QHeaderView::section:first {{
                border-top-left-radius: 8px;
            }}
            QHeaderView::section:last {{
                border-top-right-radius: 8px;
            }}

            /* Inputs inside table cells: add contrast + prevent gridline overlap */
            QTableWidget QWidget[ubTableCell="true"] LineEdit,
            QTableWidget QWidget[ubTableCell="true"] PasswordLineEdit,
            QTableWidget QWidget[ubTableCell="true"] SearchLineEdit,
            QTableWidget QWidget[ubTableCell="true"] QLineEdit,
            QTableWidget QWidget[ubTableCell="true"] ComboBox,
            QTableWidget QWidget[ubTableCell="true"] QComboBox {{
                border: 1px solid {embedded_input_border};
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

    def _on_theme_changed(self):
        """Handle theme change event"""
        is_dark = isDarkTheme()
        bg_color = COLORS['space_indigo'] if is_dark else COLORS['platinum']

        self.setStyleSheet(f"""
            BatchUploadScreen {{
                background-color: {bg_color};
                font-family: {FONTS['family']};
            }}
        """)

        # Update table theme
        self._update_table_theme()

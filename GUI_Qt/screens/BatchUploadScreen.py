"""
Batch Upload Screen - Complete Redesign
Fluent Design System with Space Indigo/Lavender color scheme
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Signal, QTimer, QEvent
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QStandardItemModel
from qfluentwidgets import (
    LineEdit, ComboBox, CheckBox, PrimaryPushButton, PushButton,
    BodyLabel, TitleLabel, StrongBodyLabel, CaptionLabel,
    TransparentToolButton, FluentIcon, InfoBar, InfoBarPosition,
    ScrollArea, CardWidget, PillPushButton, isDarkTheme, TransparentPushButton, IconWidget, qconfig
)
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from Managers.DescriptionManager import DescriptionManager
from GUI_Qt.styles.theme_config import COLORS, FONTS, COMPONENT_COLORS, RADII, PADDINGS, SIZES, SPACING
from GUI_Qt.styles.screen_theme import PAGE_MARGINS, PAGE_SPACING, CARD_MARGINS, CARD_SPACING, ICON_TEXT_GAP, ROW_SPACING, TOOLBAR_MARGINS, CONTENT_SPACING
from GUI_Qt.styles.screen_theme import TABLE_CELL_MARGINS


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
        layout.setSpacing(PAGE_SPACING)

        # Icon
        icon = IconWidget(FluentIcon.DOCUMENT)
        icon.setFixedSize(SIZES['icon_huge'], SIZES['icon_huge'])

        # Title
        self.title_label = StrongBodyLabel("")
        title = self.title_label
        title.setStyleSheet(f"font-size: {FONTS['size_subtitle_2']}; color: {COLORS['lavender_grey']};")

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
        from GUI_Qt.styles.theme_config import get_hover_bg
        hover_bg = get_hover_bg(is_dark)

        if is_drag_active:
            # Stronger visual state when file is being dragged over
            self.setStyleSheet(f"""
                DropZoneWidget {{
                    background-color: {hover_bg};
                    border: 2px solid {border};
                    border-radius: {RADII['lg']}px;
                }}
            """)
            return

        self.setStyleSheet(f"""
            DropZoneWidget {{
                background-color: transparent;
                border: 2px dashed {dashed};
                border-radius: {RADII['lg']}px;
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
        layout.setContentsMargins(*PAGE_MARGINS)
        layout.setSpacing(PAGE_SPACING)

        # === HEADER SECTION ===
        header = QHBoxLayout()

        # Title with icon
        title_container = QHBoxLayout()
        title_container.setSpacing(ICON_TEXT_GAP)

        title_icon = TransparentToolButton(FluentIcon.SYNC, self)
        title_icon.setFixedSize(SIZES['icon_lg'], SIZES['icon_lg'])
        title_icon.setEnabled(False)

        self.title_label = TitleLabel("")
        title_container.addWidget(title_icon)
        title_container.addWidget(self.title_label)

        header.addLayout(title_container)
        header.addStretch()

        # Mode pills (Fluent Design style)
        mode_container = QWidget()
        mode_layout = QHBoxLayout(mode_container)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(ROW_SPACING)
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
        toolbar_card.setBorderRadius(RADII['md'])
        toolbar_layout = QHBoxLayout(toolbar_card)
        toolbar_layout.setContentsMargins(*TOOLBAR_MARGINS)
        toolbar_layout.setSpacing(CARD_SPACING)

        self.add_btn = PushButton("")
        add_btn = self.add_btn
        add_btn.setIcon(FluentIcon.ADD.icon())
        add_btn.clicked.connect(self._add_row)

        self.clear_btn = PushButton("")
        clear_btn = self.clear_btn
        clear_btn.setIcon(FluentIcon.DELETE.icon())
        clear_btn.clicked.connect(self._clear_all)

        # Bulk selectors
        self.bulk_label = CaptionLabel("")
        bulk_label = self.bulk_label
        bulk_label.setStyleSheet(f"color: {COLORS['text_secondary']};")

        self.frameset_bulk = CheckBox("")
        frameset_bulk = self.frameset_bulk
        frameset_bulk.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        frameset_bulk.stateChanged.connect(self._toggle_all_framesets)

        self.disclaimer_bulk = CheckBox("")
        disclaimer_bulk = self.disclaimer_bulk
        disclaimer_bulk.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        disclaimer_bulk.stateChanged.connect(self._toggle_all_disclaimers)

        # Spacer between Clear and Bulk Select (hide/show with manual controls)
        self._manual_sep = QWidget()
        self._manual_sep.setStyleSheet("background: transparent;")
        self._manual_sep.setFixedWidth(ROW_SPACING)

        # Status + Start (kept in the top toolbar for parity with other batch screens)
        self.status_label = BodyLabel("")
        self.status_label.setStyleSheet(f"color: {COLORS['text_secondary']};")

        self.start_btn = PrimaryPushButton("")
        self.start_btn.setIcon(FluentIcon.PLAY)
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._start_upload)

        self.browse_btn = PushButton("")
        browse_btn = self.browse_btn
        browse_btn.setIcon(FluentIcon.FOLDER_ADD.icon())
        browse_btn.clicked.connect(self._browse_excel)

        self.template_btn = PushButton("")
        template_btn = self.template_btn
        template_btn.setIcon(FluentIcon.DOWNLOAD.icon())
        template_btn.clicked.connect(self._download_template)

        self.excel_file_label = CaptionLabel("")
        self.excel_file_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self.excel_file_label.setMinimumWidth(0)
        # Keep the excel controls packed to the right (like other batch screens).
        # If this label expands, it pushes the buttons left and looks "offset".
        self.excel_file_label.setMaximumWidth(SIZES['col_w_260'])
        self.excel_file_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

        # Spacer between excel file label and status (hide/show with excel controls)
        self._excel_status_sep = QWidget()
        self._excel_status_sep.setStyleSheet("background: transparent;")
        self._excel_status_sep.setFixedWidth(CONTENT_SPACING)

        # Expandable spacer that pushes status/start to the right.
        # This keeps the Excel controls on the left in Excel mode.
        self._toolbar_spacer = QWidget()
        self._toolbar_spacer.setStyleSheet("background: transparent;")
        self._toolbar_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # Keep status messages from squeezing the bulk checkboxes.
        # (Long validation text should clip inside this area, not steal toolbar space.)
        self.status_label.setMinimumWidth(0)
        self.status_label.setMaximumWidth(SIZES['col_w_160'])
        self.status_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

        # Match the other batch screens: a single toolbar layout.
        toolbar_layout.addWidget(add_btn)
        toolbar_layout.addWidget(clear_btn)
        toolbar_layout.addWidget(self._manual_sep)
        toolbar_layout.addWidget(bulk_label)
        toolbar_layout.addWidget(frameset_bulk)
        toolbar_layout.addWidget(disclaimer_bulk)
        toolbar_layout.addWidget(template_btn)
        toolbar_layout.addWidget(browse_btn)
        toolbar_layout.addWidget(self.excel_file_label)
        toolbar_layout.addWidget(self._excel_status_sep)
        toolbar_layout.addWidget(self._toolbar_spacer)
        toolbar_layout.addWidget(self.status_label)
        toolbar_layout.addWidget(self.start_btn)
        layout.addWidget(toolbar_card)

        # === CONTENT AREA ===
        content_card = CardWidget()
        content_card.setBorderRadius(RADII['md'])
        content_layout = QVBoxLayout(content_card)
        # Keep content flush so the table doesn't sit inside a larger card background.
        # Other batch tables don't have the extra padded background.
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

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
        self.table.horizontalHeader().setMinimumHeight(SIZES['table_header_height'])
        self.table.verticalHeader().setVisible(False)
        # Slightly taller rows prevent border/focus clipping on high-DPI systems
        self.table.verticalHeader().setDefaultSectionSize(SIZES['table_row_height_lg'])
        # Show column separators to make the table easier to scan.
        self.table.setShowGrid(True)

        # Auto-fill rows when the table viewport resizes
        self.table.viewport().installEventFilter(self)

        # Enable corner clipping for rounded borders
        self.table.setCornerButtonEnabled(False)

        # Column widths - responsive design
        header = self.table.horizontalHeader()
        # Disable manual column resizing (no interactive splitters).
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)    # Brand
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)    # Code - fixed
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # URL - flexible
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)  # Description - flexible
        # NOTE: ResizeToContents can inflate the table's minimum width after hide/show,
        # which in turn can make the main window grow when toggling Excel ↔ Manual.
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)    # Frameset - fixed
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)    # Disclaimer - fixed
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)    # Delete - fixed

        # Set minimum widths for stretching columns
        self.table.setColumnWidth(0, SIZES['col_w_200'])  # Brand default (placeholder fits without squeezing others)
        self.table.setColumnWidth(1, SIZES['col_w_140'])  # Code fixed
        self.table.setColumnWidth(3, SIZES['col_w_200'])  # Description minimum
        self.table.setColumnWidth(4, SIZES['check_col_width'])  # Frameset
        self.table.setColumnWidth(5, SIZES['check_col_width_sm'])  # Disclaimer
        self.table.setColumnWidth(6, SIZES['col_w_60'])   # Delete fixed

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

        self.retranslate_ui()

        # Ensure initial toolbar visibility matches the active mode.
        # Without this, excel-mode controls can appear in manual mode until the user toggles pills.
        self._switch_mode(self.current_mode)

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
        self._set_excel_file_text(tr("batch.no_file"))

        self._set_status_text(tr("batch.status.ready"))
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
                    self._ensure_combo_placeholder_item(brand_combo, tr("batch.select_brand"), self.brands)

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
            container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

            # Allow embedded widgets to shrink to the available cell width.
            # Without this, QComboBox can keep a large implicit minimum width and get clipped.
            try:
                widget.setMinimumWidth(0)
            except Exception:
                pass
            try:
                widget.setSizePolicy(QSizePolicy.Policy.Expanding, widget.sizePolicy().verticalPolicy())
            except Exception:
                pass

            layout = QHBoxLayout(container)
            # Inset widgets from gridlines so their borders are never clipped/overdrawn
            # Extra vertical padding avoids clipping bottom borders/focus rings
            layout.setContentsMargins(*TABLE_CELL_MARGINS)
            layout.setSpacing(0)
            layout.addWidget(widget, 1, Qt.AlignmentFlag.AlignVCenter)
            return container

        # Brand combo
        brand_combo = ComboBox()
        self._ensure_combo_placeholder_item(
            brand_combo,
            self.main.i18n.tr("batch.select_brand"),
            self.brands,
            force_placeholder=True,
        )
        brand_combo.setMinimumHeight(SIZES['input_height'])
        brand_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        brand_combo.currentTextChanged.connect(self._on_brand_change)
        brand_combo.currentTextChanged.connect(self._validate)
        self.table.setCellWidget(row, 0, create_centered_widget(brand_combo))

        # Product code
        code_field = LineEdit()
        code_field.setPlaceholderText(self.main.i18n.tr("upload.code.placeholder"))
        code_field.setMinimumHeight(SIZES['input_height'])
        code_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        code_field.textChanged.connect(lambda text, field=code_field: self._on_code_changed(text, field))
        self.table.setCellWidget(row, 1, create_centered_widget(code_field))

        # URL
        url_field = LineEdit()
        url_field.setPlaceholderText(self.main.i18n.tr("upload.url.placeholder"))
        url_field.setMinimumHeight(SIZES['input_height'])
        url_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        url_field.textChanged.connect(lambda text, field=url_field: self._on_url_changed(text, field))
        self.table.setCellWidget(row, 2, create_centered_widget(url_field))

        # Description
        desc_combo = ComboBox()
        desc_combo.addItem("")
        desc_combo.addItems(self.descriptions)
        desc_combo.setPlaceholderText(self.main.i18n.tr("batch.optional"))
        desc_combo.setMinimumHeight(SIZES['input_height'])
        desc_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        desc_combo.currentTextChanged.connect(self._validate)
        self.table.setCellWidget(row, 3, create_centered_widget(desc_combo))

        # Frameset checkbox - centered with fixed approach
        frameset_check = CheckBox("")
        frameset_check.setProperty("ubTableCheck", True)
        frameset_check.setVisible(False)
        frameset_check.stateChanged.connect(self._validate)
        # Let the checkbox use its natural size; the container layout will center it.
        frameset_container = QWidget()
        frameset_container.setStyleSheet("background: transparent;")
        frameset_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        frameset_layout = QHBoxLayout(frameset_container)
        frameset_layout.setContentsMargins(SPACING['xs'], 0, SPACING['xs'], 0)
        frameset_layout.setSpacing(0)
        frameset_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frameset_layout.addWidget(frameset_check)
        self.table.setCellWidget(row, 4, frameset_container)

        # Disclaimer checkbox - centered with fixed approach
        disclaimer_check = CheckBox("")
        disclaimer_check.setProperty("ubTableCheck", True)
        disclaimer_check.stateChanged.connect(self._validate)
        # Let the checkbox use its natural size; the container layout will center it.
        disclaimer_container = QWidget()
        disclaimer_container.setStyleSheet("background: transparent;")
        disclaimer_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        disclaimer_layout = QHBoxLayout(disclaimer_container)
        disclaimer_layout.setContentsMargins(SPACING['xs'], 0, SPACING['xs'], 0)
        disclaimer_layout.setSpacing(0)
        disclaimer_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        disclaimer_layout.addWidget(disclaimer_check)
        self.table.setCellWidget(row, 5, disclaimer_container)

        # Delete button
        delete_btn = TransparentToolButton(FluentIcon.DELETE)
        delete_btn.setToolTip(self.main.i18n.tr("batch.row.remove.tip"))
        delete_btn.setFixedSize(SIZES['button_height_sm'], SIZES['button_height_sm'])
        delete_btn.clicked.connect(self._remove_row)
        delete_container = QWidget()
        delete_container.setStyleSheet("background: transparent;")
        delete_layout = QHBoxLayout(delete_container)
        # Tight margins so the icon isn't pushed into the table border/scrollbar.
        delete_layout.setContentsMargins(SPACING['xs'], 0, SPACING['xs'], 0)
        delete_layout.addStretch(1)
        delete_layout.addWidget(delete_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        delete_layout.addStretch(1)
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
        # Batch Upload has a weird sizing interaction on some systems where toggling
        # Excel → Manual causes the top-level window to grow horizontally.
        # To avoid that, temporarily lock the window width during the mode switch,
        # then restore the previous min/max constraints once the layout settles.
        win = self.window()
        lock_w = None
        prev_min_w = None
        prev_max_w = None
        try:
            if win is not None and win.isWindow() and not win.isMaximized():
                lock_w = int(win.width())
                prev_min_w = int(win.minimumWidth())
                prev_max_w = int(win.maximumWidth())
                win.setMinimumWidth(lock_w)
                win.setMaximumWidth(lock_w)
        except Exception:
            lock_w = None

        self.current_mode = mode

        # Update pills
        self.manual_pill.setChecked(mode == "manual")
        self.excel_pill.setChecked(mode == "excel")

        # Update toolbar groups
        is_manual = mode == "manual"
        self.add_btn.setVisible(is_manual)
        self.clear_btn.setVisible(is_manual)
        self.bulk_label.setVisible(is_manual)
        self.frameset_bulk.setVisible(is_manual)
        self.disclaimer_bulk.setVisible(is_manual)
        self._manual_sep.setVisible(is_manual)

        is_excel = mode == "excel"
        self.browse_btn.setVisible(is_excel)
        self.template_btn.setVisible(is_excel)
        self.excel_file_label.setVisible(is_excel)
        self._excel_status_sep.setVisible(is_excel)

        # Update content visibility
        has_data = self._has_valid_rows()
        if mode == "excel" and not has_data:
            self.table.setVisible(False)
            self.excel_empty.setVisible(True)
        else:
            self.table.setVisible(True)
            self.excel_empty.setVisible(False)
            QTimer.singleShot(0, self._ensure_table_fills_viewport)

        if lock_w is not None:
            def _unlock_width(window=win, min_w=prev_min_w, max_w=prev_max_w):
                try:
                    if window is None or (not window.isWindow()) or window.isMaximized():
                        return
                    # Restore previous constraints.
                    if min_w is not None:
                        window.setMinimumWidth(int(min_w))
                    if max_w is not None:
                        window.setMaximumWidth(int(max_w))
                except Exception:
                    pass

            # Give Qt a moment to process pending layout/resizes.
            QTimer.singleShot(120, _unlock_width)

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

    def _set_status_text(self, text: str) -> None:
        """Set status label text without allowing it to steal toolbar space."""
        if not hasattr(self, "status_label") or self.status_label is None:
            return

        # Keep full text accessible on hover.
        try:
            self.status_label.setToolTip(text)
        except Exception:
            pass

        # Elide to the label's max width so it can't expand the toolbar.
        try:
            max_w = int(self.status_label.maximumWidth() or 0)
        except Exception:
            max_w = 0
        if max_w <= 0:
            max_w = SIZES['col_w_160']

        try:
            fm = self.status_label.fontMetrics()
            self.status_label.setText(fm.elidedText(text, Qt.TextElideMode.ElideRight, max_w))
        except Exception:
            self.status_label.setText(text)

    def _set_excel_file_text(self, text: str) -> None:
        """Set excel file label without letting it stretch the toolbar."""
        if not hasattr(self, "excel_file_label") or self.excel_file_label is None:
            return

        try:
            self.excel_file_label.setToolTip(text)
        except Exception:
            pass

        try:
            max_w = int(self.excel_file_label.maximumWidth() or 0)
        except Exception:
            max_w = 0
        if max_w <= 0:
            max_w = SIZES['col_w_260']

        try:
            fm = self.excel_file_label.fontMetrics()
            self.excel_file_label.setText(fm.elidedText(text, Qt.TextElideMode.ElideRight, max_w))
        except Exception:
            self.excel_file_label.setText(text)

    def _validate(self):
        """Validate all rows"""
        valid_count = 0
        for row in range(self.table.rowCount()):
            brand_widget = self._get_widget_from_cell(row, 0, ComboBox)
            code_widget = self._get_widget_from_cell(row, 1, LineEdit)
            url_widget = self._get_widget_from_cell(row, 2, LineEdit)

            brand = brand_widget.currentText().strip() if brand_widget else ""

            if (brand in self.brands and
                code_widget and code_widget.text().strip() and
                url_widget and url_widget.text().strip()):
                valid_count += 1

        self.start_btn.setEnabled(valid_count > 0)

        if valid_count > 0:
            key = "batch.status.ready_one" if valid_count == 1 else "batch.status.ready_many"
            self._set_status_text(self.main.i18n.tr(key, count=valid_count))
            self.status_label.setStyleSheet(f"color: {COLORS['success']}; font-weight: 500;")
        else:
            # Don't nag the user; keep Start disabled quietly.
            self._set_status_text("")
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

    @staticmethod
    def _normalize_code(raw: str) -> str:
        """Normalize product code to always include UB- prefix.

        Mirrors BatchTitles behavior: users can type codes without the prefix,
        but uploads will always use UB-<code>.
        """
        code = (raw or "").strip()
        if not code:
            return ""
        if code.upper().startswith("UB-"):
            return code
        return f"UB-{code}"

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
            self._set_excel_file_text(os.path.basename(filename))
            self.table.setVisible(True)
            self.excel_empty.setVisible(False)

            # Update status
            if invalid_count > 0:
                self._set_status_text(
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
                self._set_status_text(self.main.i18n.tr(key, count=valid_count))
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
            code_raw = code_widget.text().strip()
            code = self._normalize_code(code_raw)
            url = url_widget.text().strip()

            if not (brand in self.brands and code and url):
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

    def _ensure_combo_placeholder_item(
        self,
        combo: ComboBox,
        placeholder_text: str,
        valid_values: list[str],
        force_placeholder: bool = False,
    ) -> None:
        """Ensure a visible, disabled placeholder item at index 0.

        QComboBox placeholderText behavior can be inconsistent across styles/widgets.
        This approach avoids a blank selectable row and prevents defaulting to a real brand.
        """

        combo.blockSignals(True)
        try:
            current = combo.currentText().strip()
            keep_current = (not force_placeholder) and (current in valid_values)

            combo.clear()
            combo.addItem(placeholder_text)
            combo.addItems(valid_values)

            try:
                model = combo.model()
                if isinstance(model, QStandardItemModel):
                    item = model.item(0)
                    if item is not None:
                        item.setEnabled(False)
            except Exception:
                pass

            if keep_current:
                combo.setCurrentText(current)
            else:
                combo.setCurrentIndex(0)
        finally:
            combo.blockSignals(False)

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

        from GUI_Qt.styles.theme_config import (
            get_embedded_input_border,
            get_scrollbar_handle_bg,
            get_scrollbar_handle_hover_bg,
            get_selection_bg,
        )

        # Stronger default borders for inputs embedded inside the table.
        # This avoids "border disappears" issues against light table backgrounds.
        embedded_input_border = get_embedded_input_border(is_dark)
        embedded_input_bg = COMPONENT_COLORS['input']['bg_dark'] if is_dark else COMPONENT_COLORS['input']['bg_light']


        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {bg_color};
                alternate-background-color: {alt_bg};
                border: 1px solid {border_color};
                border-radius: {RADII['md']}px;
                gridline-color: {border_color};
                selection-background-color: {get_selection_bg()};
                color: {text_color};
            }}
            QTableWidget::viewport {{
                background-color: {bg_color};
                border-bottom-left-radius: {RADII['md']}px;
                border-bottom-right-radius: {RADII['md']}px;
            }}
            QAbstractScrollArea::corner {{
                background: transparent;
            }}
            QTableWidget::item {{
                padding: {PADDINGS['table_cell']};
                color: {text_color};
                border: none;
            }}
            QTableWidget::item:focus {{
                outline: none;
            }}
            QTableWidget:focus {{
                outline: none;
            }}
            QTableView::item:focus, QAbstractItemView::item:focus {{
                outline: none;
            }}
            QTableWidget QWidget:focus {{
                outline: none;
            }}
            QTableWidget::item:selected {{
                background-color: {get_selection_bg()};
                color: {text_color};
            }}
            QHeaderView::section {{
                background-color: {header_bg};
                color: {header_text};
                padding: {PADDINGS['table_header']};
                border: none;
                border-bottom: 1px solid {border_color};
                font-weight: 600;
                font-size: {FONTS['size_body_sm']};
                letter-spacing: 0.5px;
                text-transform: uppercase;
            }}
            QHeaderView {{
                background: transparent;
                border: none;
            }}
            QHeaderView::section {{
                border-right: 1px solid {border_color};
            }}
            QHeaderView::section:last {{
                border-right: none;
            }}
            QHeaderView::section:first {{
                border-top-left-radius: {RADII['md']}px;
            }}
            QHeaderView::section:last {{
                border-top-right-radius: {RADII['md']}px;
            }}
            QHeaderView::section:horizontal:first {{
                border-top-left-radius: {RADII['md']}px;
            }}
            QHeaderView::section:horizontal:last {{
                border-top-right-radius: {RADII['md']}px;
            }}

            /* Inputs inside table cells: add contrast + prevent gridline overlap */
            QTableWidget QWidget[ubTableCell="true"] LineEdit,
            QTableWidget QWidget[ubTableCell="true"] PasswordLineEdit,
            QTableWidget QWidget[ubTableCell="true"] SearchLineEdit,
            QTableWidget QWidget[ubTableCell="true"] QLineEdit,
            QTableWidget QWidget[ubTableCell="true"] ComboBox,
            QTableWidget QWidget[ubTableCell="true"] QComboBox {{
                background-color: {embedded_input_bg};
                border: 1px solid {embedded_input_border};
                border-bottom: 2px solid {embedded_input_border};
                border-radius: {RADII['sm']}px;
                padding: {PADDINGS['combo']};
                outline: none;
            }}

            /* Custom scrollbar styling */
            QScrollBar:vertical {{
                background: transparent;
                width: {SIZES['scrollbar_thickness']}px;
                margin: {SPACING['xxs']}px {SPACING['xxs']}px {SPACING['xxs']}px 0px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {get_scrollbar_handle_bg(is_dark)};
                border-radius: {RADII['sm']}px;
                min-height: {SIZES['scrollbar_handle_min']}px;
                margin: 0px {SPACING['xxs']}px;
                border: none;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {get_scrollbar_handle_hover_bg(is_dark)};
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
                height: {SIZES['scrollbar_thickness']}px;
                margin: 0px {SPACING['xxs']}px {SPACING['xxs']}px {SPACING['xxs']}px;
                border: none;
            }}
            QScrollBar::handle:horizontal {{
                background: {get_scrollbar_handle_bg(is_dark)};
                border-radius: {RADII['sm']}px;
                min-width: {SIZES['scrollbar_handle_min']}px;
                margin: {SPACING['xxs']}px 0px;
                border: none;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {get_scrollbar_handle_hover_bg(is_dark)};
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

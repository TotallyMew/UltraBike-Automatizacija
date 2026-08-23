"""
Upload Screen - Fluent Design System
Single product upload with Space Indigo/Lavender Grey color scheme
"""

import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QSizePolicy,
)
from PySide6.QtCore import Qt, QThread, Signal, QEvent, QTimer
from PySide6.QtGui import QFont, QStandardItemModel, QKeySequence, QShortcut
from qfluentwidgets import (
    LineEdit, ComboBox, CheckBox, PrimaryPushButton, PushButton,
    IndeterminateProgressRing, BodyLabel, TitleLabel, CaptionLabel,
    InfoBar, InfoBarPosition, MessageBox, TransparentToolButton, FluentIcon,
    CardWidget, isDarkTheme, StrongBodyLabel, qconfig, ScrollArea, IconWidget
)
from GUI_Qt.dialogs.AttributeOptionsDialog import (
    AttributeOptionsDialog, load_attribute_options, save_attribute_options,
)
from uploaderFactory import getUploaderClass
from Managers.DescriptionManager import DescriptionManager
from Managers.PimboProductEditor import PimboProductEditor, PimPreparationResult, PimPreparationStatus
from GUI_Qt.widgets.ResponsiveWidget import ResponsiveWidget
from GUI_Qt.components.validation import RequiredValidator, URLValidator
from GUI_Qt.components.accessibility import KeyboardNavigationMixin
from GUI_Qt.components.dialogs import DestructiveActionDialog
from GUI_Qt.styles.theme_config import (
    COLORS, COMPONENT_COLORS, FONTS, RADII, SIZES, SPACING,
    rgba_from_hex, get_accent_colors, get_input_style, get_status_text_color,
)
from GUI_Qt.styles.screen_theme import (
    PAGE_MARGINS,
    PAGE_SPACING,
    ICON_TEXT_GAP,
    CARD_MARGINS_LARGE,
    CARD_SPACING_LARGE,
    ROW_SPACING,
    CONTENT_SPACING,
    TOOLBAR_MARGINS,
    TIGHT_SPACING,
    apply_screen_theme,
    get_responsive_margins,
    get_responsive_spacing,
    _normalize_label_widget,
)


# Predefined attribute names from the Dviračiai template with field types.
# "options" = react-select dropdown; "text" = plain text input.
ATTRIBUTE_DEFINITIONS = [
    {"name": "Modelis", "field": "text"},
    {"name": "Modelis (vidinis)", "field": "text"},
    {"name": "Rėmo tipas", "field": "options"},
    {"name": "Rėmo medžiaga", "field": "options"},
    {"name": "Ratų dydis", "field": "options"},
    {"name": "Pavarų skaičius", "field": "options"},
    {"name": "Stabdžių tipas", "field": "options"},
    {"name": "Komplektacija", "field": "options"},
    {"name": "Spalva", "field": "options"},
]


class UploadWorker(QThread):
    """Background worker for upload process with non-blocking retry support"""
    completed = Signal(object)  # PimPreparationResult
    progress = Signal(str)  # status updates
    retry_request = Signal(str)  # operation_name
    retry_response = Signal(object)  # result from dialog (True, False, or new code)

    def __init__(self, uploader, tr):
        super().__init__()
        self.uploader = uploader
        self.tr = tr
        self._retry_result = None
        self._waiting_for_retry = False
        self._cancel_requested = False
        self.retry_response.connect(self._on_retry_response)

    def run(self):
        """Perform upload in background thread, using non-blocking retry."""
        try:
            self.progress.emit(self.tr("upload.status.starting"))
            # Patch uploader and navigation handler to use our non-blocking retry
            self.uploader.set_retry_callback(self._request_retry)
            self.uploader.set_progress_callback(self.progress.emit)
            result = self.uploader.run()
            if self._cancel_requested:
                result = PimPreparationResult(
                    product_code=str(getattr(self.uploader, "ultraBikeCode", "") or ""),
                    status=PimPreparationStatus.DISCARDED,
                    error=self.tr("upload.cancel.content"),
                )
            if not isinstance(result, PimPreparationResult):
                result = PimPreparationResult(
                    product_code=str(getattr(self.uploader, "ultraBikeCode", "") or ""),
                    status=PimPreparationStatus.FAILED,
                    error=self.tr("upload.result.invalid"),
                )
            self.completed.emit(result)
        except Exception as e:
            self.completed.emit(
                PimPreparationResult(
                    product_code=str(getattr(self.uploader, "ultraBikeCode", "") or ""),
                    status=PimPreparationStatus.FAILED,
                    error=self.tr("upload.failed", error=str(e)),
                )
            )

    def _request_retry(self, operation_name):
        """Called by uploader/navigation handler when a retry is needed."""
        self._retry_result = None
        self._waiting_for_retry = True
        self.retry_request.emit(operation_name)
        # Wait for response from GUI, but yield to event loop
        while self._waiting_for_retry:
            if self._cancel_requested or self.isInterruptionRequested():
                self._retry_result = False
                self._waiting_for_retry = False
                break
            self.msleep(50)
        return self._retry_result

    def _on_retry_response(self, result):
        self._retry_result = result
        self._waiting_for_retry = False

    def request_stop(self) -> None:
        """Request a safe stop without force-terminating Python or Selenium."""
        self._cancel_requested = True
        self.requestInterruption()
        self._retry_result = False
        self._waiting_for_retry = False


class UploadScreen(ResponsiveWidget, KeyboardNavigationMixin):
    """Main upload screen with Fluent Design and responsive scaling"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        # Connect upload worker retry signal to dialog handler
        self._active_retry_dialog = None
        self.main = main_window
        self.upload_worker = None
        self.description_manager = DescriptionManager(self.main.db)

        # Available brands
        self.brands = [
            "KROSS", "Pinarello", "Basso", "Factor",
            "TREK", "Rondo", "Octane", "Rascal", "Lee Cougan"
        ]

        # Store references for responsive scaling
        self.form_card = None
        self.current_scale = 1.0
        self._form_grid = None
        self._field_blocks = []
        self._attr_entries = []
        self.scroll = None
        self.content_widget = None

        self._init_ui()
        self._load_descriptions()
        self._setup_shortcuts()

        # Connect to theme change signal
        qconfig.themeChangedFinished.connect(self._on_theme_changed)

    def _init_ui(self):
        """Initialize UI with Fluent Design"""
        # Root layout (for ScrollArea container)
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Create ScrollArea
        self.scroll = ScrollArea(self)
        self.scroll.setWidgetResizable(True)
        root_layout.addWidget(self.scroll)

        # Content widget (inside ScrollArea)
        self.content_widget = QWidget()
        self.scroll.setWidget(self.content_widget)

        # Main layout (on content widget)
        main_layout = QVBoxLayout(self.content_widget)
        main_layout.setContentsMargins(*PAGE_MARGINS)
        main_layout.setSpacing(PAGE_SPACING)

        # Apply theme
        apply_screen_theme(
            self,
            "UploadScreen",
            scroll=self.scroll,
            content=self.content_widget
        )

        # === HEADER SECTION ===
        header = QHBoxLayout()

        # Title with icon
        title_container = QHBoxLayout()
        title_container.setSpacing(ICON_TEXT_GAP)

        title_icon = IconWidget(FluentIcon.UP)
        title_icon.setFixedSize(SIZES['icon_lg'], SIZES['icon_lg'])

        self.title_label = TitleLabel("")
        title_label = self.title_label

        title_container.addWidget(title_icon)
        title_container.addWidget(title_label)

        header.addLayout(title_container)
        header.addStretch()

        main_layout.addLayout(header)

        # === FORM CARD ===
        self.form_card = CardWidget()
        self.form_card.setBorderRadius(RADII['md'])
        self.form_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        # Keep the form readable on very wide windows (1920+)
        self.form_card.setMaximumWidth(SIZES['form_card_max_width'])

        card_layout = QVBoxLayout(self.form_card)
        card_layout.setContentsMargins(*CARD_MARGINS_LARGE)
        card_layout.setSpacing(CARD_SPACING_LARGE)

        # Form grid (responsive: 1 column on small widths, 2 columns on wide widths)
        self._form_grid = QGridLayout()
        form_grid = self._form_grid
        form_grid.setSpacing(PAGE_SPACING)
        form_grid.setVerticalSpacing(PAGE_SPACING)
        form_grid.setColumnStretch(0, 0)
        form_grid.setColumnStretch(1, 1)
        form_grid.setColumnStretch(2, 0)
        form_grid.setColumnStretch(3, 1)

        def _label_block(label_widget, caption_widget):
            block = QWidget()
            block.setStyleSheet("background: transparent;")
            block.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
            v = QVBoxLayout(block)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(TIGHT_SPACING)
            v.addWidget(label_widget)
            v.addWidget(caption_widget)
            return block

        # Brand selection
        self.brand_label = BodyLabel("")
        brand_label = self.brand_label
        self.brand_caption = CaptionLabel("")
        brand_caption = self.brand_caption
        self._brand_block = _label_block(brand_label, brand_caption)

        self.brand_combo = ComboBox()
        self._ensure_brand_placeholder(self.brand_combo)
        self.brand_combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.brand_combo.currentTextChanged.connect(self._on_brand_change)
        # Accessibility
        self.brand_combo.setAccessibleName(self.main.i18n.tr("upload.brand.label"))
        self.brand_combo.setAccessibleDescription(self.main.i18n.tr("upload.brand.caption"))

        # Product code
        self.code_label = BodyLabel("")
        code_label = self.code_label
        self.code_caption = CaptionLabel("")
        code_caption = self.code_caption
        self._code_block = _label_block(code_label, code_caption)

        # Code field with validation
        code_input_widget = QWidget()
        code_input_widget.setStyleSheet("background: transparent;")
        code_input_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        code_input_widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        code_input_row = QHBoxLayout(code_input_widget)
        code_input_row.setContentsMargins(0, 0, 0, 0)
        code_input_row.setSpacing(8)

        self.code_field = LineEdit()
        self.code_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.code_field.textChanged.connect(self._on_code_changed)
        # Accessibility
        self.code_field.setAccessibleName(self.main.i18n.tr("upload.code.label"))
        self.code_field.setAccessibleDescription(self.main.i18n.tr("upload.code.caption"))

        self.code_validation_icon = TransparentToolButton(FluentIcon.ACCEPT, self)
        self.code_validation_icon.setFixedSize(20, 20)
        self.code_validation_icon.setEnabled(False)
        self.code_validation_icon.setVisible(False)

        code_input_row.addWidget(self.code_field)
        code_input_row.addWidget(self.code_validation_icon)

        # URL/Code input
        self.url_label = BodyLabel("")
        url_label = self.url_label
        self.url_caption = CaptionLabel("")
        url_caption = self.url_caption
        self._url_block = _label_block(url_label, url_caption)

        # URL field with validation
        url_input_widget = QWidget()
        url_input_widget.setStyleSheet("background: transparent;")
        url_input_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        url_input_widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        url_input_row = QHBoxLayout(url_input_widget)
        url_input_row.setContentsMargins(0, 0, 0, 0)
        url_input_row.setSpacing(8)

        self.url_field = LineEdit()
        self.url_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.url_field.textChanged.connect(self._on_url_changed)
        # Accessibility
        self.url_field.setAccessibleName(self.main.i18n.tr("upload.url.label"))
        self.url_field.setAccessibleDescription(self.main.i18n.tr("upload.url.caption"))

        self.url_validation_icon = TransparentToolButton(FluentIcon.ACCEPT, self)
        self.url_validation_icon.setFixedSize(20, 20)
        self.url_validation_icon.setEnabled(False)
        self.url_validation_icon.setVisible(False)

        url_input_row.addWidget(self.url_field)
        url_input_row.addWidget(self.url_validation_icon)

        # Description dropdown
        desc_label_row = QHBoxLayout()
        self.desc_label = BodyLabel("")
        desc_label = self.desc_label

        self.refresh_desc_button = TransparentToolButton(FluentIcon.SYNC, self)
        self.refresh_desc_button.setFixedSize(SIZES['icon_md'], SIZES['icon_md'])
        self.refresh_desc_button.clicked.connect(self._load_descriptions)

        desc_label_row.addWidget(desc_label)
        desc_label_row.addWidget(self.refresh_desc_button)
        desc_label_row.addStretch()

        self.desc_caption = CaptionLabel("")
        desc_caption = self.desc_caption

        self.description_combo = ComboBox()
        self.description_combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.description_combo.currentTextChanged.connect(self._on_description_changed)
        # Accessibility
        self.description_combo.setAccessibleName(self.main.i18n.tr("upload.description.label"))
        self.description_combo.setAccessibleDescription(self.main.i18n.tr("upload.description.caption"))

        desc_label_widget = QWidget()
        desc_label_widget.setStyleSheet("background: transparent;")
        desc_label_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        desc_label_layout = QVBoxLayout(desc_label_widget)
        desc_label_layout.setContentsMargins(0, 0, 0, 0)
        desc_label_layout.setSpacing(TIGHT_SPACING)
        desc_label_layout.addLayout(desc_label_row)
        desc_label_layout.addWidget(desc_caption)

        self._desc_block = desc_label_widget

        self._field_blocks = [
            (self._brand_block, self.brand_combo),
            (self._code_block, code_input_widget),
            (self._url_block, url_input_widget),
            (self._desc_block, self.description_combo),
        ]

        card_layout.addLayout(form_grid)

        # === OPTIONS SECTION ===
        self.options_card = CardWidget()
        options_card = self.options_card
        options_card.setBorderRadius(RADII['sm'])
        options_card.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        # Keep options compact on wide (2-column) layouts
        options_card.setMaximumWidth(SIZES['options_card_max_width'])
        self._apply_options_card_theme()

        options_layout = QVBoxLayout(options_card)
        options_layout.setContentsMargins(*TOOLBAR_MARGINS)
        options_layout.setSpacing(CONTENT_SPACING)

        self.options_title = StrongBodyLabel("")
        options_title = self.options_title
        options_layout.addWidget(options_title)

        # Disclaimer checkbox
        disclaimer_row = QHBoxLayout()
        disclaimer_row.setSpacing(ROW_SPACING)

        self.disclaimer_checkbox = CheckBox("")
        self.disclaimer_checkbox.setStyleSheet("QCheckBox { background: transparent; } QCheckBox::indicator { background: transparent; }")
        disclaimer_info = TransparentToolButton(FluentIcon.INFO, self)
        self.disclaimer_info_btn = disclaimer_info
        disclaimer_info.setFixedSize(SIZES['icon_sm'], SIZES['icon_sm'])
        disclaimer_info.clicked.connect(self._show_disclaimer_info)

        disclaimer_row.addWidget(self.disclaimer_checkbox)
        disclaimer_row.addWidget(disclaimer_info)
        disclaimer_row.addStretch()

        options_layout.addLayout(disclaimer_row)

        # Frameset checkbox (conditional - only for Pinarello)
        self.frameset_row = QWidget()
        self.frameset_row.setStyleSheet("background: transparent;")
        self.frameset_row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        frameset_layout = QHBoxLayout(self.frameset_row)
        frameset_layout.setContentsMargins(0, 0, 0, 0)
        frameset_layout.setSpacing(ROW_SPACING)

        self.frameset_checkbox = CheckBox("")
        self.frameset_checkbox.setStyleSheet("QCheckBox { background: transparent; } QCheckBox::indicator { background: transparent; }")
        frameset_info = TransparentToolButton(FluentIcon.INFO, self)
        self.frameset_info_btn = frameset_info
        frameset_info.setFixedSize(SIZES['icon_sm'], SIZES['icon_sm'])

        frameset_layout.addWidget(self.frameset_checkbox)
        frameset_layout.addWidget(frameset_info)
        frameset_layout.addStretch()

        options_layout.addWidget(self.frameset_row)
        self.frameset_row.setVisible(False)

        options_wrapper = QHBoxLayout()
        options_wrapper.addWidget(options_card)
        options_wrapper.addStretch(1)
        card_layout.addLayout(options_wrapper)

        # === ATTRIBUTES SECTION ===
        self.attr_card = CardWidget()
        self.attr_card.setBorderRadius(RADII['sm'])
        self.attr_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.attr_card.setMaximumWidth(SIZES['form_card_max_width'])

        attr_layout = QVBoxLayout(self.attr_card)
        attr_layout.setContentsMargins(*TOOLBAR_MARGINS)
        attr_layout.setSpacing(CONTENT_SPACING)

        self.attr_title = StrongBodyLabel("")
        attr_layout.addWidget(self.attr_title)

        # Two-column grid of attributes: [Label | ComboBox | Edit] [Label | ComboBox | Edit]
        self.attr_card.setUpdatesEnabled(False)

        self._attr_grid = QGridLayout()
        self._attr_grid.setSpacing(ROW_SPACING)
        self._attr_grid.setColumnStretch(0, 0)  # label left
        self._attr_grid.setColumnStretch(1, 1)  # combo left
        self._attr_grid.setColumnStretch(2, 0)  # edit btn left
        self._attr_grid.setColumnStretch(3, 0)  # label right
        self._attr_grid.setColumnStretch(4, 1)  # combo right
        self._attr_grid.setColumnStretch(5, 0)  # edit btn right

        self._attr_widgets = {}  # {attr_name: {"combo": ComboBox}}
        for i, defn in enumerate(ATTRIBUTE_DEFINITIONS):
            name = defn["name"]
            grid_row = i // 2
            col_offset = (i % 2) * 3  # 0 for left column, 3 for right column

            label = BodyLabel(name)
            label.setFixedWidth(140)
            _normalize_label_widget(label)

            combo = ComboBox()
            combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            combo.setAccessibleName(name)
            self._load_attr_combo_options(name, combo)

            edit_btn = TransparentToolButton(FluentIcon.EDIT, self)
            edit_btn.setFixedSize(SIZES['icon_md'], SIZES['icon_md'])
            edit_btn.setToolTip(self.main.i18n.tr("upload.attr.edit_options"))
            edit_btn.setAccessibleName(
                f"{self.main.i18n.tr('upload.attr.edit_options')}: {name}"
            )
            edit_btn.clicked.connect(lambda checked=False, n=name: self._open_attr_options_dialog(n))

            self._attr_grid.addWidget(label, grid_row, col_offset)
            self._attr_grid.addWidget(combo, grid_row, col_offset + 1)
            self._attr_grid.addWidget(edit_btn, grid_row, col_offset + 2)

            self._attr_widgets[name] = {"combo": combo}
            self._attr_entries.append((label, combo, edit_btn))

        attr_layout.addLayout(self._attr_grid)

        self.attr_card.setUpdatesEnabled(True)
        card_layout.addWidget(self.attr_card)

        # Use remaining vertical space better on fullscreen by centering the card.
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addStretch(1)
        content_layout.addWidget(self.form_card)
        content_layout.addStretch(2)

        main_layout.addLayout(content_layout, 1)

        # === STICKY ACTION FOOTER (outside ScrollArea) ===
        self.action_bar = QWidget()
        self.action_bar.setFixedHeight(SIZES['button_height'] + SPACING['lg'] * 2)
        action_row = QHBoxLayout(self.action_bar)
        action_row.setContentsMargins(SPACING['xxxl'], SPACING['sm'], SPACING['xxxl'], SPACING['sm'])
        action_row.setSpacing(CONTENT_SPACING)

        self.upload_button = PrimaryPushButton("")
        self.upload_button.setIcon(FluentIcon.UP)
        self.upload_button.setEnabled(False)
        self.upload_button.setFixedHeight(SIZES['button_height'])
        self.upload_button.clicked.connect(self._handle_upload)
        self.upload_button.setAccessibleName(self.main.i18n.tr("upload.button") + " (Ctrl+Enter)")
        self.upload_button.setAccessibleDescription("Upload product to the website")

        self.clear_button = PushButton("")
        self.clear_button.setIcon(FluentIcon.DELETE)
        self.clear_button.setFixedHeight(SIZES['button_height'])
        self.clear_button.clicked.connect(self._clear_form)
        self.clear_button.setAccessibleName(self.main.i18n.tr("upload.clear"))
        self.clear_button.setAccessibleDescription("Clear all form fields")

        self.progress_ring = IndeterminateProgressRing()
        self.progress_ring.setFixedSize(SIZES['progress_ring_lg'], SIZES['progress_ring_lg'])
        self.progress_ring.setVisible(False)

        self.status_label = BodyLabel("")

        action_row.addWidget(self.upload_button)
        action_row.addWidget(self.clear_button)
        action_row.addWidget(self.progress_ring)
        action_row.addWidget(self.status_label)
        action_row.addStretch()

        root_layout.addWidget(self.action_bar)

        self._apply_text_theme()
        self._apply_attr_card_theme()
        self._apply_action_bar_theme()

        self.retranslate_ui()

    def showEvent(self, event):
        super().showEvent(event)
        # Trigger initial layout (after widgets are created)
        QTimer.singleShot(0, lambda: self._on_breakpoint_changed(self.get_current_breakpoint() or 'lg'))

    def _on_breakpoint_changed(self, breakpoint: str):
        """Respond to breakpoint changes - adjust layout and margins."""
        # Update column count based on breakpoint
        col_count = self.get_column_count()
        form_columns = 1 if breakpoint in ('xs', 'sm', 'md', 'lg') else 2
        self._apply_form_layout_mode(form_columns)
        attr_columns = 1 if breakpoint in ('xs', 'sm', 'md', 'lg') else 2
        self._apply_attribute_layout_mode(attr_columns)

        # Adjust margins based on breakpoint
        margins = get_responsive_margins(breakpoint)
        spacing = get_responsive_spacing(breakpoint)
        if hasattr(self, 'content_widget') and self.content_widget.layout():
            self.content_widget.layout().setContentsMargins(*margins)
            self.content_widget.layout().setSpacing(spacing)

    def _apply_form_layout_mode(self, columns: int):
        """Apply grid layout based on column count (1, 2, or 3).

        Args:
            columns: Number of columns (1, 2, or 3)
        """
        if not self._form_grid:
            return
        grid = self._form_grid

        # Clear layout items (widgets are reused)
        while grid.count():
            item = grid.takeAt(0)
            if item is None:
                break

        if columns == 1:
            # Compact desktop: label/caption above the control. Long translated
            # captions can otherwise force the whole page wider than the window.
            for row, (label_block, field_widget) in enumerate(self._field_blocks):
                grid.addWidget(label_block, row * 2, 0)
                grid.addWidget(field_widget, row * 2 + 1, 0)
            return

        # 2-column (or 3-column treated as 2 for upload screen): two fields per row
        pairs = [
            (self._field_blocks[0], self._field_blocks[1]),
            (self._field_blocks[2], self._field_blocks[3]),
        ]

        for row, (left, right) in enumerate(pairs):
            left_label, left_widget = left
            right_label, right_widget = right
            grid.addWidget(left_label, row, 0)
            grid.addWidget(left_widget, row, 1)
            grid.addWidget(right_label, row, 2)
            grid.addWidget(right_widget, row, 3)

    def _apply_attribute_layout_mode(self, columns: int) -> None:
        """Keep the attribute editor usable without page-level horizontal scrolling."""
        if not self._attr_grid:
            return

        while self._attr_grid.count():
            self._attr_grid.takeAt(0)

        compact = columns == 1
        for index, (label, combo, edit_button) in enumerate(self._attr_entries):
            if compact:
                label.setFixedWidth(140)
                row, column = index, 0
            else:
                label.setFixedWidth(140)
                row, column = index // 2, (index % 2) * 3
            self._attr_grid.addWidget(label, row, column)
            self._attr_grid.addWidget(combo, row, column + 1)
            self._attr_grid.addWidget(edit_button, row, column + 2)

        for column in range(6):
            self._attr_grid.setColumnStretch(column, 0)
        self._attr_grid.setColumnStretch(1, 1)
        if not compact:
            self._attr_grid.setColumnStretch(4, 1)

    def retranslate_ui(self):
        tr = self.main.i18n.tr
        self.title_label.setText(tr("upload.title"))

        self.brand_label.setText(tr("upload.brand.label"))
        self.brand_caption.setText(tr("upload.brand.caption"))
        self._ensure_brand_placeholder(self.brand_combo)

        self.code_label.setText(tr("upload.code.label"))
        self.code_caption.setText(tr("upload.code.caption"))
        self.code_field.setPlaceholderText(tr("upload.code.placeholder"))

        self.url_label.setText(tr("upload.url.label"))
        self.url_caption.setText(tr("upload.url.caption"))
        self.url_field.setPlaceholderText(tr("upload.url.placeholder"))

        self.desc_label.setText(tr("upload.desc.label"))
        self.desc_caption.setText(tr("upload.desc.caption"))
        self.refresh_desc_button.setToolTip(tr("upload.desc.refresh"))

        self.options_title.setText(tr("upload.options.title"))
        self.disclaimer_checkbox.setText(tr("upload.disclaimer"))
        self.disclaimer_info_btn.setToolTip(tr("upload.disclaimer.tip"))
        self.frameset_checkbox.setText(tr("upload.frameset"))
        self.frameset_info_btn.setToolTip(tr("upload.frameset.tip"))

        self.attr_title.setText(tr("upload.attr.title"))
        for name, widgets in self._attr_widgets.items():
            widgets["combo"].setAccessibleName(name)
        self.upload_button.setText(f"{tr('upload.button')} (Ctrl+Enter)")
        self.clear_button.setText(tr("upload.clear"))
        self.clear_button.setToolTip(tr("upload.clear.tip"))

    def _ensure_brand_placeholder(self, combo: ComboBox) -> None:
        auto_label = self.main.i18n.tr("upload.brand.auto")

        combo.blockSignals(True)
        try:
            current = combo.currentText()
            combo.clear()
            combo.addItem(auto_label)
            combo.addItems(self.brands)

            # Default to Auto unless a valid brand is already selected.
            if current in self.brands:
                combo.setCurrentText(current)
            else:
                combo.setCurrentIndex(0)
        finally:
            combo.blockSignals(False)

    def _detect_brand_from_url(self, url: str) -> str | None:
        u = (url or "").strip().lower()
        if not u:
            return None

        # Prefer URL parsing by recognizable tokens.
        # Keep ordering from most specific to least.
        token_map = [
            ("lee cougan", "Lee Cougan"),
            ("lee-cougan", "Lee Cougan"),
            ("leecougan", "Lee Cougan"),
            ("pinarello", "Pinarello"),
            ("kross", "KROSS"),
            ("basso", "Basso"),
            ("factor", "Factor"),
            ("trek", "TREK"),
            ("rondo", "Rondo"),
            ("octane", "Octane"),
            ("rascal", "Rascal"),
        ]
        for token, brand in token_map:
            if token in u:
                return brand
        return None

    def _auto_set_brand_from_url(self) -> None:
        """If brand is Auto, try to select a detected brand from URL."""
        try:
            current = (self.brand_combo.currentText() or "").strip()
        except Exception:
            current = ""

        if current in self.brands:
            return

        detected = self._detect_brand_from_url(self.url_field.text())
        if detected and detected in self.brands:
            try:
                self.brand_combo.setCurrentText(detected)
            except Exception:
                pass

    def _load_descriptions(self):
        """Load descriptions from database"""
        try:
            descriptions = self.description_manager.list_descriptions()
            self.description_combo.clear()
            self.description_combo.addItem(self.main.i18n.tr("upload.desc.select"))

            for desc in descriptions:
                self.description_combo.addItem(desc['name'])

            self.description_combo.setCurrentIndex(0)

        except Exception as e:
            InfoBar.error(
                title=self.main.i18n.tr("upload.load_failed.title"),
                content=self.main.i18n.tr("upload.load_failed.content", error=str(e)),
                parent=self,
                position=InfoBarPosition.TOP
            )

    def _setup_shortcuts(self):
        """Setup keyboard shortcuts for upload screen"""
        # Ctrl+Enter to start upload
        start_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        start_shortcut.activated.connect(self._handle_start_shortcut)

        # Escape to cancel upload (if running)
        cancel_shortcut = QShortcut(QKeySequence("Escape"), self)
        cancel_shortcut.activated.connect(self._handle_cancel_shortcut)

    def _handle_start_shortcut(self):
        """Handle Ctrl+Enter shortcut to start upload"""
        if self.upload_button.isEnabled():
            self._start_upload()

    def _handle_cancel_shortcut(self):
        """Handle Escape shortcut to cancel upload"""
        if self.upload_worker is not None and self.upload_worker.isRunning():
            self.upload_worker.request_stop()
            if self._active_retry_dialog is not None:
                self._active_retry_dialog.close()
            self.upload_button.setEnabled(False)
            self.clear_button.setEnabled(False)
            self.status_label.setText(self.main.i18n.tr("upload.cancel.stopping"))
            self.status_label.setStyleSheet(
                f"color: {get_status_text_color('warning', isDarkTheme())}; "
                "background: transparent; background-color: transparent;"
            )
            InfoBar.warning(
                title=self.main.i18n.tr("upload.cancel.title"),
                content=self.main.i18n.tr("upload.cancel.safe_wait"),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=4000,
            )

    def _on_brand_change(self, brand):
        """Handle brand selection change"""
        # Show frameset checkbox only for Pinarello
        is_pinarello = brand == "Pinarello"
        self.frameset_row.setVisible(is_pinarello)
        self._check_form_valid()

    def _on_code_changed(self, text):
        """Handle product code field change with validation"""
        # Validate product code format
        is_valid = self._validate_product_code(text)
        self._update_validation_icon(self.code_validation_icon, is_valid, text)
        self._check_form_valid()

    def _on_url_changed(self, text):
        """Handle URL field change with validation"""
        # Validate URL format
        is_valid = self._validate_url(text)
        self._update_validation_icon(self.url_validation_icon, is_valid, text)
        self._auto_set_brand_from_url()
        self._check_form_valid()

    def _validate_product_code(self, code: str) -> bool:
        """Validate product code format (should start with UB- or be non-empty)"""
        code = code.strip()
        if not code:
            return False
        # Valid if it starts with UB- or is at least 3 characters
        return code.startswith("UB-") or len(code) >= 3

    def _validate_url(self, url: str) -> bool:
        """Validate URL format (should be a valid HTTP/HTTPS URL)"""
        return URLValidator(self.main.i18n.tr).validate(url.strip()).valid

    def _update_validation_icon(self, icon_widget, is_valid: bool, text: str):
        """Update validation icon based on validation result"""
        if not text.strip():
            # Hide icon when field is empty
            icon_widget.setVisible(False)
        else:
            icon_widget.setVisible(True)
            if is_valid:
                # Green checkmark for valid input
                icon_widget.setIcon(FluentIcon.ACCEPT)
                color = get_status_text_color("success", isDarkTheme())
            else:
                # Red X for invalid input
                icon_widget.setIcon(FluentIcon.CLOSE)
                color = get_status_text_color("error", isDarkTheme())
            icon_widget.setStyleSheet(
                f"color: {color}; background: transparent; background-color: transparent;"
            )

    def _on_description_changed(self, text):
        """Handle description dropdown change with validation"""
        self._check_form_valid()

    def _check_form_valid(self):
        """Check if form is valid and enable/disable upload button"""
        brand = self.brand_combo.currentText().strip()
        code = self.code_field.text().strip()
        url = self.url_field.text().strip()
        description = self.description_combo.currentText()

        # Description is optional - require code + url + (brand selected OR detectable from URL)
        brand_ok = (brand in self.brands) or (self._detect_brand_from_url(url) in self.brands)
        is_valid = bool(code and url and brand_ok)

        # Debug logging
        # Debug: Validation check and button state

        self.upload_button.setEnabled(is_valid)

        # Debug: Button enabled after and end of validation

    def _show_disclaimer_info(self):
        """Show disclaimer information"""
        InfoBar.info(
            title=self.main.i18n.tr("upload.disclaimer.info.title"),
            content=self.main.i18n.tr("upload.disclaimer.info.content"),
            parent=self,
            position=InfoBarPosition.TOP,
            duration=4000
        )

    def _handle_upload(self):
        """Handle upload button click"""
        if self.upload_worker and self.upload_worker.isRunning():
            InfoBar.warning(
                title=self.main.i18n.tr("upload.in_progress.title"),
                content=self.main.i18n.tr("upload.in_progress.content"),
                parent=self,
                position=InfoBarPosition.TOP
            )
            return

        # Get form data
        brand = self.brand_combo.currentText()
        code = self.code_field.text().strip()
        url = self.url_field.text().strip()

        # Validate form fields before upload
        validation_errors = []

        if not brand or brand not in self.brands:
            validation_errors.append(f"Brand: {self.main.i18n.tr('validation.required')}")

        if not code:
            validation_errors.append(f"Code: {self.main.i18n.tr('validation.required')}")

        if not url:
            validation_errors.append(f"URL: {self.main.i18n.tr('validation.required')}")
        else:
            url_validator = URLValidator(self.main.i18n.tr)
            url_result = url_validator.validate(url)
            if not url_result.valid:
                validation_errors.append(f"URL: {url_result.error}")

        # Show validation errors if any
        if validation_errors:
            error_message = "\n".join(validation_errors)
            InfoBar.error(
                title=self.main.i18n.tr("batch.validation.errors_title"),
                content=error_message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self
            )
            return
        description = self.description_combo.currentText()
        # Description is optional. Convert placeholder to "no selection".
        try:
            if self.description_combo.currentIndex() == 0:
                description = None
            elif description == self.main.i18n.tr("upload.desc.select"):
                description = None
        except Exception:
            pass
        include_disclaimer = self.disclaimer_checkbox.isChecked()
        is_frameset = self.frameset_checkbox.isChecked() if self.frameset_row.isVisible() else False

        # Resolve brand (Auto -> detect from URL)
        brand = (brand or "").strip()
        if brand not in self.brands:
            detected = self._detect_brand_from_url(url)
            if detected and detected in self.brands:
                brand = detected
                try:
                    self.brand_combo.setCurrentText(brand)
                except Exception:
                    pass
            else:
                InfoBar.error(
                    title=self.main.i18n.tr("upload.invalid_brand.title"),
                    content=self.main.i18n.tr("upload.brand.detect_failed"),
                    parent=self,
                    position=InfoBarPosition.TOP,
                    duration=6000,
                )
                return

        # Get uploader class
        try:
            uploader_class = getUploaderClass(brand)
        except ValueError as e:
            InfoBar.error(
                title=self.main.i18n.tr("upload.invalid_brand.title"),
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP
            )
            return

        # Create uploader instance
        try:
            master_password = getattr(self.main, "_unlocked_master_password", None)
            if brand in ("Basso", "Lee Cougan"):
                service = "basso" if brand == "Basso" else "leecougan"
                try:
                    if not self.main.credential_manager.has_external_credentials(service):
                        InfoBar.error(
                            title=self.main.i18n.tr("common.error"),
                            content=self.main.i18n.tr("account.brand_missing", brand=brand),
                            parent=self,
                            position=InfoBarPosition.TOP
                        )
                        return

                    master_password = self.main.get_unlocked_master_password(parent=self)
                    if not master_password:
                        InfoBar.error(
                            title=self.main.i18n.tr("common.error"),
                            content=self.main.i18n.tr("master.invalid.content"),
                            parent=self,
                            position=InfoBarPosition.TOP
                        )
                        return
                except Exception:
                    pass

            # Collect attribute selections from UI
            attribute_values = self._get_attribute_values()

            # Build brand_options dictionary
            brand_options = {
                'description_name': description if description else None,
                'append_disclaimer': include_disclaimer,
                'attribute_values': attribute_values,
            }

            # Add brand-specific options
            if brand == "Pinarello":
                brand_options['frameset_only'] = is_frameset

            uploader = uploader_class(
                driver=self.main.driver,
                brand_name=brand,
                product_code=code,
                url_or_code=url,
                db_manager=self.main.db,
                brand_options=brand_options,
                logger=self.main.logger,
                master_password=master_password,
                settings_manager=self.main.settings
            )
        except Exception as e:
            InfoBar.error(
                title=self.main.i18n.tr("upload.uploader_error.title"),
                content=self.main.i18n.tr("upload.uploader_error.content", error=str(e)),
                parent=self,
                position=InfoBarPosition.TOP
            )
            return

        # Start upload in background
        self.upload_worker = UploadWorker(uploader, self.main.i18n.tr)
        self.upload_worker.progress.connect(self._on_upload_progress)
        self.upload_worker.completed.connect(self._on_upload_finished)
        self.upload_worker.retry_request.connect(self._on_retry_request)

        # UI updates
        self.upload_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        self.progress_ring.setVisible(True)
        self.status_label.setText(self.main.i18n.tr("upload.status.uploading"))
        self.status_label.setStyleSheet(
            f"color: {get_accent_colors(isDarkTheme())['base']}; "
            "background: transparent; background-color: transparent;"
        )

        if hasattr(self.main, "track_worker"):
            self.main.track_worker(self.upload_worker, "upload", "upload")
        self.upload_worker.start()

    def _on_retry_request(self, operation_name):
        # Show non-blocking Fluent dialog for retry with code entry
        if self._active_retry_dialog:
            self._active_retry_dialog.close()
        from qfluentwidgets import MessageBox
        from PySide6.QtWidgets import QLineEdit
        dialog = MessageBox(
            self.main.i18n.tr("upload.retry.title"),
            self.main.i18n.tr("upload.retry.content"),
            self
        )
        # Remove default content label and add input
        try:
            dialog.textLayout.removeWidget(dialog.contentLabel)
            dialog.contentLabel.deleteLater()
        except Exception:
            pass
        input_widget = QLineEdit()
        input_widget.setPlaceholderText(self.main.i18n.tr("upload.retry.placeholder"))
        input_widget.setMinimumWidth(SIZES['panel_min_width'])
        input_widget.setStyleSheet(get_input_style(isDarkTheme()) + f"""
            font-size: {FONTS['size_body_lg']};
            font-family: {FONTS['family']};
            margin-top: {SPACING['sm']}px;
        """)
        dialog.textLayout.addWidget(input_widget)
        dialog.yesButton.setText(self.main.i18n.tr("upload.retry.yes"))
        dialog.cancelButton.setText(self.main.i18n.tr("upload.retry.cancel"))

        def _on_finished(result_code):
            from PySide6.QtWidgets import QDialog
            if result_code == QDialog.Accepted:
                new_code = input_widget.text().strip()
                if new_code:
                    self.upload_worker.retry_response.emit(new_code)
                else:
                    self.upload_worker.retry_response.emit(True)
            else:
                self.upload_worker.retry_response.emit(False)
            self._active_retry_dialog = None

        dialog.finished.connect(_on_finished)
        dialog.show()
        self._active_retry_dialog = dialog

    def _on_upload_progress(self, message):
        """Handle upload progress updates"""
        self.status_label.setText(message)

    def _on_upload_finished(self, result: PimPreparationResult):
        """Handle upload completion"""
        self.progress_ring.setVisible(False)
        self.clear_button.setEnabled(True)
        self._check_form_valid()

        if self.upload_worker is not None and self.upload_worker._cancel_requested:
            message = self.main.i18n.tr("upload.cancel.content")
            self.status_label.setText(message)
            self.status_label.setStyleSheet(
                f"color: {get_status_text_color('warning', isDarkTheme())}; "
                "background: transparent; background-color: transparent;"
            )
            InfoBar.warning(
                title=self.main.i18n.tr("upload.cancel.title"),
                content=message,
                parent=self,
                position=InfoBarPosition.TOP,
                duration=4000,
            )
            return

        if result.status == PimPreparationStatus.READY_FOR_REVIEW:
            message = self.main.i18n.tr("upload.review.ready")
            self.status_label.setText(message)
            self.status_label.setStyleSheet(
                f"color: {get_status_text_color('warning', isDarkTheme())}; "
                "background: transparent; background-color: transparent;"
            )

            InfoBar.info(
                title=self.main.i18n.tr("upload.review.ready.title"),
                content=message,
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000
            )

            # Keep form values after successful upload
            QTimer.singleShot(0, lambda saved_result=result: self._confirm_regular_save(saved_result))

        elif result.status == PimPreparationStatus.BLOCKED_NON_DRAFT:
            message = result.error or self.main.i18n.tr("upload.review.blocked")
            self.status_label.setText(message)
            self.status_label.setStyleSheet(
                f"color: {get_status_text_color('warning', isDarkTheme())}; "
                "background: transparent; background-color: transparent;"
            )
            InfoBar.warning(
                title=self.main.i18n.tr("upload.review.blocked.title"),
                content=message,
                parent=self,
                position=InfoBarPosition.TOP,
                duration=4000,
            )
        else:
            message = result.error or self.main.i18n.tr("upload.review.failed")
            self.status_label.setText(message)
            self.status_label.setStyleSheet(
                f"color: {get_status_text_color('error', isDarkTheme())}; "
                "background: transparent; background-color: transparent;"
            )

            InfoBar.error(
                title=self.main.i18n.tr("upload.failed.title"),
                content=message,
                parent=self,
                position=InfoBarPosition.TOP,
                duration=5000
            )

    def _confirm_regular_save(self, result: PimPreparationResult) -> None:
        """Verify the human PIMBO save before offering an earning entry."""
        dialog = MessageBox(
            self.main.i18n.tr("upload.save_confirm.title"),
            self.main.i18n.tr("upload.save_confirm.content"),
            self,
        )
        dialog.yesButton.setText(self.main.i18n.tr("upload.save_confirm.yes"))
        dialog.cancelButton.setText(self.main.i18n.tr("upload.save_confirm.skip"))
        if not dialog.exec():
            return
        try:
            verified = PimboProductEditor(
                self.main.driver,
                getattr(self.main, "logger", None),
            ).verify_manual_save(result)
            if verified.status != PimPreparationStatus.SAVED_MANUALLY:
                InfoBar.warning(
                    title=self.main.i18n.tr("upload.save_verify.failed.title"),
                    content=verified.error or self.main.i18n.tr("upload.save_verify.failed.content"),
                    parent=self,
                    position=InfoBarPosition.TOP,
                    duration=6000,
                )
                return

            row = self.main.db.conn.execute(
                """
                SELECT id, details_json FROM processing_history
                WHERE product_code=? AND status='ready_for_review'
                ORDER BY id DESC LIMIT 1
                """,
                (result.product_code,),
            ).fetchone()
            history_id = None
            if row is not None:
                history_id = int(row["id"])
                try:
                    details = json.loads(row["details_json"] or "{}") or {}
                except Exception:
                    details = {}
                details["pim_preparation"] = verified.to_dict()
                self.main.db.conn.execute(
                    "UPDATE processing_history SET status='saved_manually', details_json=? WHERE id=?",
                    (json.dumps(details, ensure_ascii=False), history_id),
                )
                self.main.db.conn.commit()

            self.status_label.setText(self.main.i18n.tr("upload.save_verify.saved"))
            self.status_label.setStyleSheet(
                f"color: {get_status_text_color('success', isDarkTheme())}; "
                "background: transparent; background-color: transparent;"
            )
            product_type = (
                "frameset"
                if self.brand_combo.currentText() == "Pinarello" and self.frameset_checkbox.isChecked()
                else "bicycle"
            )
            self.main.prompt_earning_items(
                [{
                    "sku": result.product_code,
                    "brand": self.brand_combo.currentText(),
                    "product_type": product_type,
                    "source": "regular_upload",
                    "processing_history_id": history_id,
                }],
                parent=self,
            )
        except Exception as error:
            InfoBar.error(
                title=self.main.i18n.tr("upload.save_verify.error.title"),
                content=str(error),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=6000,
            )

    # -- Attribute helpers ------------------------------------------------------

    def _load_attr_combo_options(self, attr_name: str, combo: ComboBox):
        """Populate a combo box with saved options from the database."""
        options = load_attribute_options(self.main.settings, attr_name)
        combo.clear()
        combo.addItem("")  # empty / no selection
        for opt in options:
            combo.addItem(opt)

    def _open_attr_options_dialog(self, attr_name: str):
        """Open the dialog to manage dropdown values for an attribute."""
        current = load_attribute_options(self.main.settings, attr_name)
        dlg = AttributeOptionsDialog(attr_name, current, self.main.i18n.tr, parent=self)
        if dlg.exec():
            new_options = dlg.get_options()
            save_attribute_options(self.main.settings, attr_name, new_options)
            # Refresh combo while preserving selection
            combo = self._attr_widgets[attr_name]["combo"]
            prev = combo.currentText()
            self._load_attr_combo_options(attr_name, combo)
            if prev:
                combo.setCurrentText(prev)
            InfoBar.success(
                title=self.main.i18n.tr("upload.attr.saved_title"),
                content=self.main.i18n.tr("upload.attr.saved", name=attr_name, count=len(new_options)),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2000,
            )

    def _get_attribute_values(self) -> list[dict]:
        """Collect attribute values from all attribute combos for the uploader."""
        result = []
        for defn in ATTRIBUTE_DEFINITIONS:
            name = defn["name"]
            combo = self._attr_widgets[name]["combo"]
            value = combo.currentText().strip()
            if not value:
                continue
            result.append({"name": name, "value": value, "field": defn["field"]})
        return result

    def _clear_form(self) -> None:
        """Clear user-editable fields with confirmation dialog (keeps selected brand)."""
        confirmed = DestructiveActionDialog.ask(
            title=self.main.i18n.tr("common.confirm"),
            message=self.main.i18n.tr("upload.clear.confirm"),
            action_text=self.main.i18n.tr("upload.clear"),
            parent=self,
            tr_func=self.main.i18n.tr,
        )
        if confirmed:
            self.code_field.clear()
            self.url_field.clear()
            self.description_combo.setCurrentIndex(0)
            self.disclaimer_checkbox.setChecked(False)
            self.frameset_checkbox.setChecked(False)
            for widgets in self._attr_widgets.values():
                widgets["combo"].setCurrentIndex(0)
            self.status_label.setText("")
            self._check_form_valid()

    def shutdown(self, wait_ms: int = 5000) -> bool:
        """Request a safe upload stop before the shared browser is closed."""
        worker = self.upload_worker
        if worker is None or not worker.isRunning():
            return True
        worker.request_stop()
        if self._active_retry_dialog is not None:
            self._active_retry_dialog.close()
        return bool(worker.wait(max(0, int(wait_ms))))

    def _on_theme_changed(self):
        """Handle theme change event"""
        apply_screen_theme(
            self,
            "UploadScreen",
            scroll=self.scroll,
            content=self.content_widget
        )

        self._apply_options_card_theme()
        self._apply_attr_card_theme()
        self._apply_action_bar_theme()
        self._apply_text_theme()

    def _apply_options_card_theme(self) -> None:
        if not hasattr(self, 'options_card') or self.options_card is None:
            return
        is_dark = isDarkTheme()
        self.options_card.setStyleSheet(f"""
            CardWidget {{
                background-color: {rgba_from_hex(COLORS['text_white'], 0.03) if is_dark else rgba_from_hex(COLORS['space_indigo'], 0.03)};
                border: 1px solid {COLORS['border_dark'] if is_dark else COLORS['border_light']};
            }}
        """)

    def _apply_attr_card_theme(self) -> None:
        if not hasattr(self, 'attr_card') or self.attr_card is None:
            return
        is_dark = isDarkTheme()
        self.attr_card.setStyleSheet(f"""
            CardWidget {{
                background-color: {rgba_from_hex(COLORS['text_white'], 0.03) if is_dark else rgba_from_hex(COLORS['space_indigo'], 0.03)};
                border: 1px solid {COLORS['border_dark'] if is_dark else COLORS['border_light']};
            }}
        """)

    def _apply_action_bar_theme(self) -> None:
        if not hasattr(self, 'action_bar') or self.action_bar is None:
            return
        is_dark = isDarkTheme()
        bg = COLORS['bg_dark'] if is_dark else COLORS['bg_light']
        border = COLORS['border_dark'] if is_dark else COLORS['border_light']
        self.action_bar.setStyleSheet(f"""
            QWidget {{
                background-color: {bg};
                border-top: 1px solid {border};
            }}
        """)

    def _apply_text_theme(self):
        is_dark = isDarkTheme()
        # Make labels readable on light theme (avoid faint grey-on-white)
        label_color = COLORS['text_primary_dark'] if is_dark else COLORS['text_primary_light']
        caption_color = COLORS['lavender_grey'] if is_dark else COLORS['text_secondary']

        # Title
        if hasattr(self, 'title_label') and self.title_label is not None:
            _normalize_label_widget(self.title_label)

        for label in (self.brand_label, self.code_label, self.url_label, self.desc_label):
            label.setStyleSheet(f"font-weight: 600; color: {label_color};")
            label.setAutoFillBackground(False)
            _normalize_label_widget(label)

        for caption in (self.brand_caption, self.code_caption, self.url_caption, self.desc_caption):
            caption.setStyleSheet(f"color: {caption_color};")
            caption.setAutoFillBackground(False)
            _normalize_label_widget(caption)

        # Attribute section title
        if hasattr(self, 'attr_title') and self.attr_title is not None:
            self.attr_title.setStyleSheet(f"color: {label_color};")
            self.attr_title.setAutoFillBackground(False)
            _normalize_label_widget(self.attr_title)

        # Options title + default status text
        if hasattr(self, 'options_title') and self.options_title is not None:
            self.options_title.setStyleSheet(f"color: {label_color};")
            self.options_title.setAutoFillBackground(False)
            _normalize_label_widget(self.options_title)
        if hasattr(self, 'status_label') and self.status_label is not None:
            self.status_label.setStyleSheet(f"color: {caption_color};")
            self.status_label.setAutoFillBackground(False)
            _normalize_label_widget(self.status_label)

"""
Dialog for managing dropdown options for a product attribute.
Users can add, edit, and remove values that appear in the attribute ComboBox.
Follows Fluent Design standards with proper theming and notifications.
"""

import json

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QDialog, QWidget,
)
from PySide6.QtCore import Qt
from qfluentwidgets import (
    LineEdit, PushButton, PrimaryPushButton, BodyLabel, TitleLabel, CaptionLabel,
    TransparentToolButton, FluentIcon, InfoBar, InfoBarPosition,
    CardWidget, isDarkTheme,
)
from GUI_Qt.components.dialogs import DestructiveActionDialog

from GUI_Qt.styles.theme_config import (
    COLORS, FONTS, RADII, SIZES, SPACING, rgba_from_hex,
)
from GUI_Qt.styles.screen_theme import (
    ROW_SPACING, CONTENT_SPACING, TOOLBAR_MARGINS, TIGHT_SPACING,
    _normalize_label_widget,
)


# ---------------------------------------------------------------------------
# Persistence helpers (settings table, JSON-encoded lists)
# ---------------------------------------------------------------------------

def _settings_key(attr_name: str) -> str:
    return f"attr_options_{attr_name}"


def load_attribute_options(settings_manager, attr_name: str) -> list[str]:
    """Load saved dropdown options for *attr_name* from the DB."""
    raw = settings_manager.get(_settings_key(attr_name), "[]")
    try:
        opts = json.loads(raw)
        return opts if isinstance(opts, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def save_attribute_options(settings_manager, attr_name: str, options: list[str]):
    """Persist dropdown options for *attr_name* to the DB."""
    settings_manager.set(_settings_key(attr_name), json.dumps(options, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class AttributeOptionsDialog(QDialog):
    """Modal dialog to add / edit / remove values for one attribute."""

    def __init__(self, attr_name: str, current_options: list[str], tr, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("upload.attr.manage_title", name=attr_name))
        self.setMinimumWidth(400)
        self.setMinimumHeight(420)
        self._attr_name = attr_name
        self._options = list(current_options)
        self._tr = tr

        self._init_ui()
        self._apply_theme()

    # -- UI ----------------------------------------------------------------

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING['xl'], SPACING['xl'], SPACING['xl'], SPACING['xl'])
        layout.setSpacing(CONTENT_SPACING)

        # Header
        title = TitleLabel(self._attr_name)
        layout.addWidget(title)

        subtitle = CaptionLabel(self._tr("upload.attr.manage_subtitle"))
        layout.addWidget(subtitle)

        layout.addSpacing(SPACING['xs'])

        # Input card
        input_card = CardWidget()
        input_card.setBorderRadius(RADII['sm'])
        self._input_card = input_card
        input_card_layout = QVBoxLayout(input_card)
        input_card_layout.setContentsMargins(*TOOLBAR_MARGINS)
        input_card_layout.setSpacing(ROW_SPACING)

        input_label = BodyLabel(self._tr("upload.attr.add_label"))
        self._input_label = input_label
        input_card_layout.addWidget(input_label)

        input_row = QHBoxLayout()
        input_row.setSpacing(ROW_SPACING)

        self._input = LineEdit()
        self._input.setPlaceholderText(self._tr("upload.attr.add_placeholder"))
        self._input.setFixedHeight(SIZES['input_height'])
        self._input.returnPressed.connect(self._add_value)
        input_row.addWidget(self._input)

        self._add_btn = PrimaryPushButton(self._tr("upload.attr.add_btn"))
        self._add_btn.setIcon(FluentIcon.ADD)
        self._add_btn.setFixedHeight(SIZES['button_height'])
        self._add_btn.clicked.connect(self._add_value)
        input_row.addWidget(self._add_btn)

        input_card_layout.addLayout(input_row)
        layout.addWidget(input_card)

        # Values list card
        list_card = CardWidget()
        list_card.setBorderRadius(RADII['sm'])
        self._list_card = list_card
        list_card_layout = QVBoxLayout(list_card)
        list_card_layout.setContentsMargins(*TOOLBAR_MARGINS)
        list_card_layout.setSpacing(ROW_SPACING)

        list_header = QHBoxLayout()
        list_header.setSpacing(ROW_SPACING)

        values_label = BodyLabel(self._tr("upload.attr.values_label"))
        self._values_label = values_label
        list_header.addWidget(values_label)

        list_header.addStretch()

        self._count_label = CaptionLabel("")
        self._count_caption = self._count_label
        list_header.addWidget(self._count_label)

        list_card_layout.addLayout(list_header)

        self._list = QListWidget()
        self._list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        for opt in self._options:
            self._list.addItem(opt)
        self._list.itemDoubleClicked.connect(self._edit_value)
        list_card_layout.addWidget(self._list)

        self._update_count()

        # List action buttons
        list_actions = QHBoxLayout()
        list_actions.setSpacing(ROW_SPACING)

        self._remove_btn = PushButton(self._tr("upload.attr.remove_selected"))
        self._remove_btn.setIcon(FluentIcon.DELETE)
        self._remove_btn.setFixedHeight(SIZES['button_height_sm'])
        self._remove_btn.clicked.connect(self._remove_selected)
        list_actions.addWidget(self._remove_btn)

        list_actions.addStretch()

        edit_hint = CaptionLabel(self._tr("upload.attr.edit_hint"))
        self._edit_hint = edit_hint
        list_actions.addWidget(edit_hint)

        list_card_layout.addLayout(list_actions)
        layout.addWidget(list_card, 1)

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(ROW_SPACING)
        btn_row.addStretch()

        cancel_btn = PushButton(self._tr("common.cancel"))
        cancel_btn.setFixedHeight(SIZES['button_height'])
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        ok_btn = PrimaryPushButton(self._tr("upload.attr.save_btn"))
        ok_btn.setIcon(FluentIcon.SAVE)
        ok_btn.setFixedHeight(SIZES['button_height'])
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)

        layout.addLayout(btn_row)

    # -- Theme -------------------------------------------------------------

    def _apply_theme(self):
        is_dark = isDarkTheme()
        bg = COLORS['bg_dark'] if is_dark else COLORS['bg_light']
        text_color = COLORS['text_primary_dark'] if is_dark else COLORS['text_primary_light']
        caption_color = COLORS['text_secondary_dark'] if is_dark else COLORS['text_secondary_light']
        card_bg = rgba_from_hex(COLORS['text_white'], 0.03) if is_dark else rgba_from_hex(COLORS['space_indigo'], 0.03)
        card_border = COLORS['border_dark'] if is_dark else COLORS['border_light']
        list_bg = COLORS['bg_alt_dark'] if is_dark else COLORS['bg_alt_light']
        list_border = COLORS['border_dark'] if is_dark else COLORS['border_light']
        list_item_hover = rgba_from_hex(COLORS['lavender_grey'], 0.15) if is_dark else rgba_from_hex(COLORS['space_indigo'], 0.06)
        list_selected = rgba_from_hex(COLORS['lavender_grey'], 0.25) if is_dark else rgba_from_hex(COLORS['space_indigo'], 0.12)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {bg};
            }}
        """)

        for card in (self._input_card, self._list_card):
            card.setStyleSheet(f"""
                CardWidget {{
                    background-color: {card_bg};
                    border: 1px solid {card_border};
                }}
            """)

        self._list.setStyleSheet(f"""
            QListWidget {{
                background-color: {list_bg};
                color: {text_color};
                border: 1px solid {list_border};
                border-radius: {RADII['sm']}px;
                font-family: {FONTS['family']};
                font-size: {FONTS['size_body']};
                padding: {SPACING['xs']}px;
            }}
            QListWidget::item {{
                padding: {SPACING['sm']}px {SPACING['md']}px;
                border-radius: {RADII['xs']}px;
            }}
            QListWidget::item:hover {{
                background-color: {list_item_hover};
            }}
            QListWidget::item:selected {{
                background-color: {list_selected};
                color: {text_color};
            }}
        """)

        for label in (self._input_label, self._values_label):
            label.setStyleSheet(f"font-weight: 600; color: {text_color};")
            _normalize_label_widget(label)

        for caption in (self._count_caption, self._edit_hint):
            caption.setStyleSheet(f"color: {caption_color};")
            _normalize_label_widget(caption)

    # -- Actions -----------------------------------------------------------

    def _add_value(self):
        text = self._input.text().strip()
        if not text:
            InfoBar.warning(
                title=self._tr("upload.attr.add_empty_title"),
                content=self._tr("upload.attr.add_empty"),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2000,
            )
            return

        # Check duplicates
        for i in range(self._list.count()):
            if self._list.item(i).text().strip().lower() == text.lower():
                InfoBar.warning(
                    title=self._tr("upload.attr.duplicate_title"),
                    content=self._tr("upload.attr.duplicate_value", value=text),
                    parent=self,
                    position=InfoBarPosition.TOP,
                    duration=2000,
                )
                return

        self._list.addItem(text)
        self._input.clear()
        self._input.setFocus()
        self._update_count()

        InfoBar.success(
            title=self._tr("upload.attr.added_title"),
            content=self._tr("upload.attr.added", value=text),
            parent=self,
            position=InfoBarPosition.TOP,
            duration=1500,
        )

    def _remove_selected(self):
        selected = self._list.selectedItems()
        if not selected:
            InfoBar.warning(
                title=self._tr("upload.attr.no_selection_title"),
                content=self._tr("upload.attr.no_selection"),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2000,
            )
            return

        names = ", ".join(item.text() for item in selected)
        confirmed = DestructiveActionDialog.ask(
            title=self._tr("upload.attr.confirm_remove_title"),
            message=self._tr("upload.attr.confirm_remove", values=names),
            action_text=self._tr("upload.attr.remove_selected"),
            parent=self,
            tr_func=self._tr,
        )
        if not confirmed:
            return

        for item in selected:
            self._list.takeItem(self._list.row(item))
        self._update_count()

        InfoBar.success(
            title=self._tr("upload.attr.removed_title"),
            content=self._tr("upload.attr.removed", values=names),
            parent=self,
            position=InfoBarPosition.TOP,
            duration=1500,
        )

    def _edit_value(self, item: QListWidgetItem):
        """Allow inline editing on double-click."""
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self._list.editItem(item)

    def _update_count(self):
        count = self._list.count()
        self._count_label.setText(
            self._tr("upload.attr.count", count=count)
        )

    # -- Result ------------------------------------------------------------

    def get_options(self) -> list[str]:
        """Return the final ordered list of options after the dialog is closed."""
        result = []
        for i in range(self._list.count()):
            text = self._list.item(i).text().strip()
            if text and text not in result:
                result.append(text)
        return result

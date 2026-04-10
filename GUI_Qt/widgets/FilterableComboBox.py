"""
GUI_Qt/widgets/FilterableComboBox.py

Ghost-style filterable combo box for table cells.

When unfocused: no border, no background — plain text on the row (Notion/Airtable style).
On hover: subtle background.
On focus/click: border appears, text becomes editable, popup list opens with fuzzy filtering.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QFocusEvent, QKeyEvent, QPainter, QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import isDarkTheme

from GUI_Qt.styles.theme_config import COLORS, COMPONENT_COLORS, RADII


class _PopupList(QWidget):
    """Frameless popup that shows filtered items."""

    item_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.list_widget = QListWidget()
        self.list_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget)

        self.setMinimumWidth(160)
        self.setMaximumHeight(240)

    def _on_item_clicked(self, item: QListWidgetItem):
        self.item_selected.emit(item.text())
        self.hide()

    def select_current(self):
        item = self.list_widget.currentItem()
        if item:
            self.item_selected.emit(item.text())
            self.hide()

    def move_selection(self, delta: int):
        lw = self.list_widget
        count = lw.count()
        if count == 0:
            return
        current = lw.currentRow()
        new_row = max(0, min(count - 1, current + delta))
        lw.setCurrentRow(new_row)

    def update_style(self):
        is_dark = isDarkTheme()
        bg = COMPONENT_COLORS["input"]["bg_dark"] if is_dark else COMPONENT_COLORS["input"]["bg_light"]
        border = COLORS["lavender_grey"] if is_dark else COLORS["space_indigo"]
        text = COLORS["text_primary_dark"] if is_dark else COLORS["text_primary_light"]
        sel_bg = "rgba(43, 45, 66, 0.12)" if not is_dark else "rgba(141, 153, 174, 0.20)"

        self.setStyleSheet(f"""
            _PopupList {{
                background: {bg};
                border: 1px solid {border};
                border-radius: {RADII['sm']}px;
            }}
            QListWidget {{
                background: {bg};
                border: none;
                outline: none;
                color: {text};
                font-size: 13px;
            }}
            QListWidget::item {{
                padding: 6px 10px;
            }}
            QListWidget::item:selected {{
                background: {sel_bg};
            }}
            QListWidget::item:hover {{
                background: {sel_bg};
            }}
        """)


class FilterableComboBox(QWidget):
    """Ghost-style combo box with type-to-filter for use in table cells.

    Signals:
        currentTextChanged(str): emitted when the selected value changes.
    """

    currentTextChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[str] = []
        self._selected_text: str = ""
        self._placeholder: str = ""
        self._editing = False
        self._in_event = False  # guard against re-entrant eventFilter calls

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._edit = QLineEdit()
        self._edit.setFrame(False)
        self._edit.installEventFilter(self)
        layout.addWidget(self._edit)

        # Small dropdown arrow hint
        self._arrow = QLabel("▾")
        self._arrow.setFixedWidth(16)
        self._arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._arrow.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent; font-size: 11px;")
        layout.addWidget(self._arrow)

        self._popup = _PopupList()
        self._popup.item_selected.connect(self._on_popup_selected)

        self._apply_ghost_style()

    # -- Public API (ComboBox-compatible subset) --

    def addItem(self, text: str):
        if text and text not in self._items:
            self._items.append(text)

    def addItems(self, texts):
        for t in texts:
            self.addItem(t)

    def clear(self):
        self._items.clear()
        self._selected_text = ""
        self._edit.clear()

    def setPlaceholderText(self, text: str):
        self._placeholder = text
        self._edit.setPlaceholderText(text)

    def currentText(self) -> str:
        return self._selected_text

    def setCurrentIndex(self, index: int):
        if 0 <= index < len(self._items):
            self._set_value(self._items[index])

    def setCurrentText(self, text: str):
        self._set_value(text)

    def findText(self, text: str) -> int:
        try:
            return self._items.index(text)
        except ValueError:
            return -1

    def currentIndex(self) -> int:
        return self.findText(self._selected_text)

    def setMinimumHeight(self, h: int):
        super().setMinimumHeight(h)
        self._edit.setMinimumHeight(h)

    # -- Internal --

    def _set_value(self, text: str):
        old = self._selected_text
        self._selected_text = text
        self._edit.setText(text)
        self._edit.setCursorPosition(0)
        if text != old:
            self.currentTextChanged.emit(text)

    def _on_popup_selected(self, text: str):
        self._set_value(text)
        self._editing = False
        self._apply_ghost_style()
        self._edit.clearFocus()

    def _show_popup(self):
        self._editing = True
        self._filter_items("")
        self._popup.update_style()

        # Position below this widget
        pos = self.mapToGlobal(QPoint(0, self.height()))
        self._popup.setFixedWidth(max(self.width(), 160))
        self._popup.move(pos)
        self._popup.show()

    def _hide_popup(self):
        self._popup.hide()

    def _filter_items(self, query: str):
        lw = self._popup.list_widget
        lw.clear()
        q = query.lower()
        for item in self._items:
            if not item:
                continue
            if not q or q in item.lower():
                lw.addItem(item)
        if lw.count() > 0:
            lw.setCurrentRow(0)

    # -- Ghost styling --

    def _apply_ghost_style(self):
        is_dark = isDarkTheme()
        text = COLORS["text_primary_dark"] if is_dark else COLORS["text_primary_light"]
        placeholder = COLORS["text_secondary"]

        # Ghost: no border, no background
        self._edit.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {text};
                padding: 2px 4px;
            }}
            QLineEdit::placeholder {{
                color: {placeholder};
            }}
        """)

    def _apply_focus_style(self):
        is_dark = isDarkTheme()
        text = COLORS["text_primary_dark"] if is_dark else COLORS["text_primary_light"]
        placeholder = COLORS["text_secondary"]
        eib_bg = COMPONENT_COLORS["input"]["bg_dark"] if is_dark else COMPONENT_COLORS["input"]["bg_light"]
        border = COLORS["lavender_grey"] if is_dark else COLORS["space_indigo"]

        self._edit.setStyleSheet(f"""
            QLineEdit {{
                background: {eib_bg};
                border: 1px solid {border};
                border-radius: {RADII['sm']}px;
                color: {text};
                padding: 2px 4px;
            }}
            QLineEdit::placeholder {{
                color: {placeholder};
            }}
        """)

    # -- Events --

    def eventFilter(self, obj, event):
        if obj is not self._edit:
            return False
        if self._in_event:
            return False
        self._in_event = True
        try:
            return self._handle_event(event)
        finally:
            self._in_event = False

    def _handle_event(self, event):
        if event.type() == QEvent.Type.FocusIn:
            self._apply_focus_style()
            self._edit.setText("")
            self._edit.setPlaceholderText(
                self._selected_text if self._selected_text else self._placeholder
            )
            self._show_popup()
            return False

        if event.type() == QEvent.Type.FocusOut:
            # Delay hide so popup click can register
            if not self._popup.isVisible() or not self._popup.underMouse():
                self._editing = False
                self._edit.setText(self._selected_text)
                self._edit.setPlaceholderText(self._placeholder)
                self._apply_ghost_style()
                self._hide_popup()
            return False

        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self._edit.setText(self._selected_text)
                self._edit.clearFocus()
                self._hide_popup()
                return True
            if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
                self._popup.select_current()
                return True
            if key == Qt.Key.Key_Down:
                self._popup.move_selection(1)
                return True
            if key == Qt.Key.Key_Up:
                self._popup.move_selection(-1)
                return True
            # Text changed — filter after key is processed
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._filter_items(self._edit.text()))
            return False

        return False

    def enterEvent(self, event):
        if not self._editing:
            is_dark = isDarkTheme()
            eib_bg = COMPONENT_COLORS["input"]["bg_dark"] if is_dark else COMPONENT_COLORS["input"]["bg_light"]
            text = COLORS["text_primary_dark"] if is_dark else COLORS["text_primary_light"]
            from GUI_Qt.styles.theme_config import get_embedded_input_border
            eib = get_embedded_input_border(is_dark)
            self._edit.setStyleSheet(f"""
                QLineEdit {{
                    background: {eib_bg};
                    border: 1px solid {eib};
                    border-radius: {RADII['sm']}px;
                    color: {text};
                    padding: 2px 4px;
                }}
            """)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._editing and not self._edit.hasFocus():
            self._apply_ghost_style()
        super().leaveEvent(event)

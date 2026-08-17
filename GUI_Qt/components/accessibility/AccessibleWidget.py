"""
Accessible Widget Base Class
Provides accessibility helpers for WCAG 2.1 AA compliance
"""

import re

from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QComboBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QDoubleSpinBox,
    QTextEdit,
    QWidget,
)
from PySide6.QtCore import QTimer
from PySide6.QtGui import QAccessibleEvent
from PySide6.QtCore import Qt


class AccessibleWidget(QWidget):
    """Base widget with accessibility features for screen readers and keyboard navigation"""

    def __init__(self, accessible_name=None, accessible_description=None, parent=None):
        super().__init__(parent)

        if accessible_name:
            self.setAccessibleName(accessible_name)
        if accessible_description:
            self.setAccessibleDescription(accessible_description)

    def announce_to_screen_reader(self, message: str):
        """
        Announce a message to screen readers (NVDA, JAWS, etc.)

        Uses the QAccessible Alert event to trigger screen reader announcements.
        The message is temporarily set as the accessible description and then
        restored after a short delay.

        Args:
            message: The text to announce to screen readers
        """
        if not message:
            return

        # Store old description
        old_description = self.accessibleDescription()

        # Set new message as accessible description
        self.setAccessibleDescription(message)

        # Trigger accessibility event
        try:
            from PySide6.QtGui import QAccessible
            event = QAccessibleEvent(self, QAccessible.Event.Alert)
            QAccessible.updateAccessibility(event)
        except Exception:
            pass  # Accessibility API not available

        # Restore old description after announcement
        QTimer.singleShot(100, lambda: self.setAccessibleDescription(old_description))

    def set_accessible_properties(self, name=None, description=None, role=None):
        """
        Set multiple accessibility properties at once

        Args:
            name: Accessible name (short label)
            description: Accessible description (detailed explanation)
            role: Accessible role (for advanced use cases)
        """
        if name:
            self.setAccessibleName(name)
        if description:
            self.setAccessibleDescription(description)
        # Role setting would require more complex QAccessibleInterface implementation


_INTERNAL_BUTTON_CLASSES = {"ArrowButton", "Indicator", "LineEditButton"}
_INTERNAL_OBJECT_NAMES = {"lineEditButton", "qt_tableview_cornerbutton"}


def _clean_control_text(text: str) -> str:
    """Normalize visible control text for use by assistive technologies."""
    value = re.sub(r"\s+", " ", (text or "").replace("&", "")).strip()
    return value.rstrip(":")


def _nearby_label_text(widget: QWidget) -> str:
    """Return the closest preceding label in the widget's immediate layout."""
    parent = widget.parentWidget()
    while parent is not None:
        layout = parent.layout()
        if layout is not None:
            widget_index = -1
            for index in range(layout.count()):
                item = layout.itemAt(index)
                if item is not None and item.widget() is widget:
                    widget_index = index
                    break
            if widget_index >= 0:
                for index in range(widget_index - 1, -1, -1):
                    candidate = layout.itemAt(index).widget()
                    if isinstance(candidate, QLabel):
                        text = _clean_control_text(candidate.text())
                        if text:
                            return text
                break
        widget = parent
        parent = parent.parentWidget()
    return ""


def _screen_title(root: QWidget) -> str:
    labels = root.findChildren(QLabel)
    for label in labels:
        if type(label).__name__ in {"TitleLabel", "LargeTitleLabel"}:
            text = _clean_control_text(label.text())
            if text:
                return text
    return _clean_control_text(root.windowTitle())


def apply_accessibility_defaults(root: QWidget) -> None:
    """Fill missing accessible metadata without overriding explicit labels.

    Qt exposes standard widgets to Windows accessibility APIs, but custom
    Fluent controls still need useful names.  This pass derives conservative
    defaults from visible labels, placeholders, tooltips, and table headers.
    """
    if root is None:
        return

    title = _screen_title(root)
    editable_types = (QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit)

    for child in root.findChildren(QWidget):
        try:
            class_name = type(child).__name__
            object_name = child.objectName() or ""

            if isinstance(child, QAbstractButton):
                if class_name in _INTERNAL_BUTTON_CLASSES or object_name in _INTERNAL_OBJECT_NAMES:
                    continue
                if not child.accessibleName():
                    visible_text = _clean_control_text(child.text())
                    tooltip = _clean_control_text(child.toolTip())
                    if isinstance(child, QComboBox):
                        visible_text = _clean_control_text(child.currentText()) or visible_text
                    name = visible_text or tooltip
                    if name:
                        child.setAccessibleName(name)
                if child.toolTip() and not child.accessibleDescription():
                    child.setAccessibleDescription(_clean_control_text(child.toolTip()))
                continue

            is_fluent_combo = class_name in {"ComboBox", "EditableComboBox"} and hasattr(child, "currentText")
            if isinstance(child, editable_types) or is_fluent_combo:
                if not child.accessibleName():
                    label = _nearby_label_text(child)
                    placeholder = ""
                    if hasattr(child, "placeholderText"):
                        placeholder = _clean_control_text(child.placeholderText())
                        if placeholder and set(placeholder) <= {"•", "*"}:
                            placeholder = ""
                    fallback = f"{title} field" if title else "Input field"
                    child.setAccessibleName(label or placeholder or fallback)
                continue

            if isinstance(child, QAbstractItemView) and not child.accessibleName():
                view_kind = "table" if "Table" in class_name else "list"
                child.setAccessibleName(f"{title} {view_kind}".strip().capitalize())
        except Exception:
            # Accessibility metadata should never make a screen unusable.
            continue

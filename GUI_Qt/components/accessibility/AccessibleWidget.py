"""
Accessible Widget Base Class
Provides accessibility helpers for WCAG 2.1 AA compliance
"""

from PySide6.QtWidgets import QWidget
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

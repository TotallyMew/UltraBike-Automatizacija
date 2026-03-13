"""
Keyboard Navigation Mixin
Provides consistent keyboard shortcuts across the application
"""

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeySequence, QShortcut


class KeyboardNavigationMixin:
    """
    Mixin class to add consistent keyboard shortcuts to screens

    Usage:
        class MyScreen(ResponsiveWidget, KeyboardNavigationMixin):
            def __init__(self, ...):
                super().__init__(...)
                self.setup_keyboard_shortcuts()

            def on_save_shortcut(self):
                # Handle Ctrl+S
                pass
    """

    def setup_keyboard_shortcuts(self, save_callback=None, cancel_callback=None, help_callback=None):
        """
        Setup standard keyboard shortcuts for the screen

        Args:
            save_callback: Function to call on Ctrl+S (save)
            cancel_callback: Function to call on Escape (cancel)
            help_callback: Function to call on F1 (help)
        """
        # Ctrl+S - Save
        if save_callback:
            save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
            save_shortcut.activated.connect(save_callback)

        # Escape - Cancel
        if cancel_callback:
            cancel_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
            cancel_shortcut.activated.connect(cancel_callback)

        # F1 - Help
        if help_callback:
            help_shortcut = QShortcut(QKeySequence.StandardKey.HelpContents, self)
            help_shortcut.activated.connect(help_callback)

    def setup_custom_shortcut(self, key_sequence, callback):
        """
        Add a custom keyboard shortcut

        Args:
            key_sequence: QKeySequence or string (e.g., "Ctrl+N")
            callback: Function to call when shortcut is activated
        """
        if isinstance(key_sequence, str):
            key_sequence = QKeySequence(key_sequence)

        shortcut = QShortcut(key_sequence, self)
        shortcut.activated.connect(callback)
        return shortcut

    def get_shortcut_hints(self):
        """
        Get a dictionary of active keyboard shortcuts for display in help/tooltips

        Returns:
            Dict mapping shortcut names to key sequences
        """
        return {
            "save": "Ctrl+S",
            "cancel": "Escape",
            "help": "F1",
        }


def add_focus_indicator_style(widget, focus_color='#8D99AE', offset=2, width=3):
    """
    Add visible focus indicator to a widget for accessibility

    Args:
        widget: The QWidget to add focus indicator to
        focus_color: Color of the focus ring (default: lavender grey)
        offset: Offset from widget border in pixels
        width: Width of focus ring in pixels

    Example:
        add_focus_indicator_style(self.login_button)
    """
    current_style = widget.styleSheet()
    focus_style = f"""
        QWidget:focus {{
            outline: {width}px solid {focus_color};
            outline-offset: {offset}px;
        }}
    """
    widget.setStyleSheet(current_style + focus_style)

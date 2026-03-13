"""
DestructiveActionDialog - Confirmation dialog for destructive actions.

Provides a red-styled action button to visually warn users about destructive operations
like Delete, Clear, or Remove.
"""

from typing import Optional, Callable
from PySide6.QtWidgets import QWidget
from qfluentwidgets import MessageBox


class DestructiveActionDialog(MessageBox):
    """Confirmation dialog with red-styled button for destructive actions."""

    def __init__(
        self,
        title: str,
        message: str,
        action_text: str,
        parent: Optional[QWidget] = None,
        tr_func: Optional[Callable] = None
    ):
        """
        Initialize destructive action dialog.

        Args:
            title: Dialog title
            message: Warning message explaining what will be deleted/removed
            action_text: Text for the destructive action button (e.g., "Delete", "Clear All")
            parent: Parent widget
            tr_func: Translation function
        """
        self.tr = tr_func if tr_func else lambda key, **kwargs: key

        super().__init__(
            title=title,
            content=message,
            parent=parent
        )

        # Set button text
        self.yesButton.setText(action_text)
        self.cancelButton.setText(self.tr("confirm.cancel"))

        # Style the action button as red/destructive
        self.yesButton.setStyleSheet("""
            QPushButton {
                background-color: #C81D25;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #A01720;
            }
            QPushButton:pressed {
                background-color: #8B1419;
            }
        """)

    @staticmethod
    def ask(
        title: str,
        message: str,
        action_text: str,
        parent: Optional[QWidget] = None,
        tr_func: Optional[Callable] = None
    ) -> bool:
        """
        Show destructive action dialog and return user choice.

        Args:
            title: Dialog title
            message: Warning message
            action_text: Text for the destructive action button
            parent: Parent widget
            tr_func: Translation function

        Returns:
            True if user confirmed the destructive action, False otherwise
        """
        dialog = DestructiveActionDialog(title, message, action_text, parent, tr_func)
        return dialog.exec()

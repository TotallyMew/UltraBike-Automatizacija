"""
ConfirmationDialog - Standard confirmation dialog for user actions.

Provides a consistent way to ask for user confirmation before proceeding with an action.
"""

from typing import Optional, Callable
from PySide6.QtWidgets import QWidget
from qfluentwidgets import MessageBox


class ConfirmationDialog(MessageBox):
    """Standard confirmation dialog with Yes/Cancel buttons."""

    def __init__(
        self,
        title: str,
        message: str,
        parent: Optional[QWidget] = None,
        tr_func: Optional[Callable] = None
    ):
        """
        Initialize confirmation dialog.

        Args:
            title: Dialog title
            message: Confirmation message
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
        self.yesButton.setText(self.tr("confirm.yes"))
        self.cancelButton.setText(self.tr("confirm.cancel"))

    @staticmethod
    def ask(
        title: str,
        message: str,
        parent: Optional[QWidget] = None,
        tr_func: Optional[Callable] = None
    ) -> bool:
        """
        Show confirmation dialog and return user choice.

        Args:
            title: Dialog title
            message: Confirmation message
            parent: Parent widget
            tr_func: Translation function

        Returns:
            True if user confirmed (Yes), False otherwise (Cancel/Close)
        """
        dialog = ConfirmationDialog(title, message, parent, tr_func)
        return dialog.exec()

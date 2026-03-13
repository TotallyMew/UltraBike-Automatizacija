"""
UnsavedChangesDialog - Three-way choice dialog for unsaved changes.

Provides Save/Discard/Cancel options when the user has unsaved changes and
attempts to close a form or navigate away.
"""

from typing import Optional, Callable
from PySide6.QtWidgets import QWidget, QDialog, QVBoxLayout, QHBoxLayout
from qfluentwidgets import MessageBox, PrimaryPushButton, PushButton


class UnsavedChangesDialog(QDialog):
    """Dialog for handling unsaved changes with Save/Discard/Cancel options."""

    # Return values
    SAVE = 1
    DISCARD = 2
    CANCEL = 0

    def __init__(
        self,
        title: str,
        message: str,
        parent: Optional[QWidget] = None,
        tr_func: Optional[Callable] = None
    ):
        """
        Initialize unsaved changes dialog.

        Args:
            title: Dialog title
            message: Message explaining unsaved changes
            parent: Parent widget
            tr_func: Translation function
        """
        super().__init__(parent)
        self.tr = tr_func if tr_func else lambda key, **kwargs: key
        self.result_value = self.CANCEL

        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        self._init_ui(message)

    def _init_ui(self, message: str):
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(24, 24, 24, 24)

        # Message
        from PySide6.QtWidgets import QLabel
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        layout.addWidget(message_label)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        button_layout.addStretch()

        # Cancel button
        self.cancel_button = PushButton(self.tr("confirm.unsaved.cancel"))
        self.cancel_button.clicked.connect(lambda: self._set_result(self.CANCEL))
        button_layout.addWidget(self.cancel_button)

        # Discard button
        self.discard_button = PushButton(self.tr("confirm.unsaved.discard"))
        self.discard_button.clicked.connect(lambda: self._set_result(self.DISCARD))
        # Style as warning/destructive
        self.discard_button.setStyleSheet("""
            QPushButton {
                color: #C81D25;
                border: 2px solid #C81D25;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: rgba(200, 29, 37, 0.1);
            }
        """)
        button_layout.addWidget(self.discard_button)

        # Save button (primary)
        self.save_button = PrimaryPushButton(self.tr("confirm.unsaved.save"))
        self.save_button.clicked.connect(lambda: self._set_result(self.SAVE))
        button_layout.addWidget(self.save_button)

        layout.addLayout(button_layout)

    def _set_result(self, result: int):
        """Set result and close dialog."""
        self.result_value = result
        if result == self.CANCEL:
            self.reject()
        else:
            self.accept()

    def get_result(self) -> int:
        """
        Get the user's choice.

        Returns:
            SAVE (1), DISCARD (2), or CANCEL (0)
        """
        return self.result_value

    @staticmethod
    def ask(
        parent: Optional[QWidget] = None,
        tr_func: Optional[Callable] = None,
        title: Optional[str] = None,
        message: Optional[str] = None
    ) -> int:
        """
        Show unsaved changes dialog and return user choice.

        Args:
            parent: Parent widget
            tr_func: Translation function
            title: Custom title (uses default if None)
            message: Custom message (uses default if None)

        Returns:
            SAVE (1), DISCARD (2), or CANCEL (0)
        """
        _tr = tr_func if tr_func else lambda key, **kwargs: key

        # Use default messages if not provided
        if title is None:
            title = _tr("confirm.unsaved.title")
        if message is None:
            message = _tr("confirm.unsaved.message")

        dialog = UnsavedChangesDialog(title, message, parent, tr_func)
        dialog.exec()
        return dialog.get_result()

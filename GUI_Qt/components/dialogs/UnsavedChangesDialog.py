"""
UnsavedChangesDialog - Three-way choice dialog for unsaved changes.

Provides Save/Discard/Cancel options when the user has unsaved changes and
attempts to close a form or navigate away.
"""

from typing import Optional, Callable
from PySide6.QtWidgets import QWidget, QDialog, QVBoxLayout, QHBoxLayout
from qfluentwidgets import PrimaryPushButton, PushButton, isDarkTheme
from GUI_Qt.styles.theme_config import (
    RADII,
    get_accent_colors,
    get_focus_color,
    get_hover_bg,
    get_pressed_bg,
    get_semantic_colors,
    get_surface_color,
    get_text_color,
    rgba_from_hex,
)


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

        self.setObjectName("unsavedChangesDialog")
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        self._init_ui(message)

    def _init_ui(self, message: str):
        """Initialize UI components."""
        is_dark = isDarkTheme()
        surface = get_surface_color(is_dark)
        surface_alt = get_surface_color(is_dark, "alternate")
        disabled_surface = get_surface_color(is_dark, "disabled")
        stroke = get_surface_color(is_dark, "stroke")
        text = get_text_color(is_dark, "primary")
        disabled_text = get_text_color(is_dark, "disabled")
        hover = get_hover_bg(is_dark)
        pressed = get_pressed_bg(is_dark)
        focus = get_focus_color(is_dark)
        accent = get_accent_colors(is_dark)
        error = get_semantic_colors("error", is_dark)

        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(24, 24, 24, 24)

        # Message
        from PySide6.QtWidgets import QLabel
        self.message_label = QLabel(message)
        self.message_label.setObjectName("unsavedChangesMessage")
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        button_layout.addStretch()

        # Cancel button
        self.cancel_button = PushButton(self.tr("confirm.unsaved.cancel"))
        self.cancel_button.setObjectName("unsavedCancelButton")
        self.cancel_button.clicked.connect(lambda: self._set_result(self.CANCEL))
        button_layout.addWidget(self.cancel_button)

        # Discard button
        self.discard_button = PushButton(self.tr("confirm.unsaved.discard"))
        self.discard_button.setObjectName("unsavedDiscardButton")
        self.discard_button.clicked.connect(lambda: self._set_result(self.DISCARD))
        button_layout.addWidget(self.discard_button)

        # Save button (primary)
        self.save_button = PrimaryPushButton(self.tr("confirm.unsaved.save"))
        self.save_button.setObjectName("unsavedSaveButton")
        self.save_button.clicked.connect(lambda: self._set_result(self.SAVE))
        button_layout.addWidget(self.save_button)

        # QDialog otherwise keeps the native light palette even when Fluent is
        # dark, producing white text on a white surface.  Scope every role to
        # this dialog so its surface and foregrounds always move together.
        self.setStyleSheet(f"""
            QDialog#unsavedChangesDialog {{
                background-color: {surface};
                color: {text};
            }}
            QLabel#unsavedChangesMessage {{
                color: {text};
                background: transparent;
                border: none;
            }}
        """)

        # Fluent buttons carry their own widget-level stylesheets, which take
        # precedence over inherited QDialog rules. Apply the same role tokens
        # directly so their visible states cannot fall back to the library's
        # unrelated default accent.
        self.cancel_button.setStyleSheet(f"""
            QPushButton, PushButton {{
                color: {text};
                background-color: {surface_alt};
                border: 1px solid {stroke};
                border-radius: {RADII['sm']}px;
                padding: 8px 16px;
            }}
            QPushButton:hover, PushButton:hover {{ background-color: {hover}; }}
            QPushButton:pressed, PushButton:pressed {{ background-color: {pressed}; }}
            QPushButton:focus, PushButton:focus {{ border: 2px solid {focus}; }}
            QPushButton:disabled, PushButton:disabled {{
                color: {disabled_text};
                background-color: {disabled_surface};
                border: 1px solid {stroke};
            }}
        """)
        self.discard_button.setStyleSheet(f"""
            QPushButton, PushButton {{
                color: {error['text']};
                background: transparent;
                border: 2px solid {error['text']};
                border-radius: {RADII['sm']}px;
                padding: 8px 16px;
                font-weight: 600;
            }}
            QPushButton:hover, PushButton:hover {{
                background-color: {error['background']};
            }}
            QPushButton:pressed, PushButton:pressed {{
                background-color: {rgba_from_hex(error['fill'], 0.20)};
            }}
            QPushButton:focus, PushButton:focus {{ border: 2px solid {focus}; }}
            QPushButton:disabled, PushButton:disabled {{
                color: {disabled_text};
                background-color: {disabled_surface};
                border: 1px solid {stroke};
            }}
        """)
        self.save_button.setStyleSheet(f"""
            QPushButton, PrimaryPushButton {{
                color: {accent['text']};
                background-color: {accent['base']};
                border: 1px solid {accent['base']};
                border-radius: {RADII['sm']}px;
                padding: 8px 16px;
                font-weight: 600;
            }}
            QPushButton:hover, PrimaryPushButton:hover {{
                background-color: {accent['hover']};
                border-color: {accent['hover']};
            }}
            QPushButton:pressed, PrimaryPushButton:pressed {{
                background-color: {accent['pressed']};
                border-color: {accent['pressed']};
            }}
            QPushButton:focus, PrimaryPushButton:focus {{ border: 2px solid {focus}; }}
            QPushButton:disabled, PrimaryPushButton:disabled {{
                color: {disabled_text};
                background-color: {disabled_surface};
                border: 1px solid {stroke};
            }}
        """)

        self.cancel_button.setDefault(True)
        self.cancel_button.setFocus()

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

"""
ValidatedLineEdit component - LineEdit with inline validation and error display.

Provides visual feedback for validation state:
- Red border + error text + X icon for errors
- Green checkmark icon for valid input
- Yellow warning text + info icon for warnings
"""

from typing import List, Optional, Callable
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtGui import QIcon, QPixmap
from qfluentwidgets import LineEdit
from qfluentwidgets import FluentIcon as FIF

from .validators import BaseValidator, ValidationResult
from GUI_Qt.styles.theme_config import COLORS


class ValidatedLineEdit(QWidget):
    """LineEdit with inline validation and error display."""

    # Signals
    validationChanged = Signal(bool)  # Emitted when validation state changes
    textChanged = Signal(str)  # Emitted when text changes

    def __init__(
        self,
        validators: Optional[List[BaseValidator]] = None,
        validate_on: str = 'blur',
        placeholder: str = "",
        parent: Optional[QWidget] = None,
        tr_func: Optional[Callable] = None
    ):
        """
        Initialize ValidatedLineEdit.

        Args:
            validators: List of validators to apply
            validate_on: When to validate ('blur', 'change', 'manual')
                        - 'blur': Validate on focus loss (default)
                        - 'change': Validate on every keystroke
                        - 'manual': Only validate when validate() is called
            placeholder: Placeholder text
            parent: Parent widget
            tr_func: Translation function
        """
        super().__init__(parent)
        self.validators = validators or []
        self.validate_on = validate_on
        self.tr = tr_func if tr_func else lambda key, **kwargs: key
        self._is_valid = True
        self._last_validation_result = ValidationResult(valid=True)

        self._init_ui(placeholder)
        self._connect_signals()

    def _init_ui(self, placeholder: str):
        """Initialize UI components."""
        # Main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(4)

        # Input row (LineEdit + validation icon)
        self.input_layout = QHBoxLayout()
        self.input_layout.setContentsMargins(0, 0, 0, 0)
        self.input_layout.setSpacing(8)

        # LineEdit
        self.line_edit = LineEdit(self)
        if placeholder:
            self.line_edit.setPlaceholderText(placeholder)
        self.input_layout.addWidget(self.line_edit, 1)

        # Validation icon
        self.validation_icon = QLabel(self)
        self.validation_icon.setFixedSize(20, 20)
        self.validation_icon.hide()
        self.input_layout.addWidget(self.validation_icon)

        self.main_layout.addLayout(self.input_layout)

        # Error/warning label
        self.error_label = QLabel(self)
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        self.main_layout.addWidget(self.error_label)

    def _connect_signals(self):
        """Connect internal signals."""
        # Connect validation triggers based on validate_on setting
        if self.validate_on == 'blur':
            # Validate on focus loss
            self.line_edit.editingFinished.connect(self._on_editing_finished)
        elif self.validate_on == 'change':
            # Validate on every text change
            self.line_edit.textChanged.connect(lambda: self.validate())

        # Always forward textChanged signal
        self.line_edit.textChanged.connect(self.textChanged.emit)

    def _on_editing_finished(self):
        """Handle editing finished (focus loss)."""
        self.validate()

    def validate(self) -> bool:
        """
        Validate the current value against all validators.

        Returns:
            True if validation passed, False otherwise
        """
        value = self.line_edit.text()

        # Run all validators
        for validator in self.validators:
            result = validator.validate(value)
            if not result.valid:
                self._show_error(result.error)
                self._set_valid_state(False)
                self._last_validation_result = result
                return False

            # Check for warnings
            if result.warning:
                self._show_warning(result.warning)
                self._set_valid_state(True)
                self._last_validation_result = result
                return True

        # All validations passed
        self._show_success()
        self._set_valid_state(True)
        self._last_validation_result = ValidationResult(valid=True)
        return True

    def _set_valid_state(self, is_valid: bool):
        """Update internal valid state and emit signal if changed."""
        if self._is_valid != is_valid:
            self._is_valid = is_valid
            self.validationChanged.emit(is_valid)

    def _show_error(self, error_message: str):
        """Display error state."""
        # Set error border on LineEdit
        self.line_edit.setStyleSheet(f"""
            LineEdit {{
                border: 2px solid {COLORS['error']};
                border-radius: 6px;
            }}
        """)

        # Show error icon (X)
        self.validation_icon.setText("✗")
        self.validation_icon.setStyleSheet(f"color: {COLORS['error']}; font-weight: bold; font-size: 16px;")
        self.validation_icon.show()

        # Show error message
        self.error_label.setText(error_message)
        self.error_label.setStyleSheet(f"color: {COLORS['error']}; font-size: 12px;")
        self.error_label.show()

    def _show_warning(self, warning_message: str):
        """Display warning state."""
        # No border change for warnings
        self.line_edit.setStyleSheet("")

        # Show warning icon (!)
        self.validation_icon.setText("⚠")
        self.validation_icon.setStyleSheet(f"color: {COLORS['warning']}; font-weight: bold; font-size: 16px;")
        self.validation_icon.show()

        # Show warning message
        self.error_label.setText(warning_message)
        self.error_label.setStyleSheet(f"color: {COLORS['warning']}; font-size: 12px;")
        self.error_label.show()

    def _show_success(self):
        """Display success state."""
        # Remove any error styling
        self.line_edit.setStyleSheet("")

        # Show success icon (checkmark) only if field has content
        if self.line_edit.text().strip():
            self.validation_icon.setText("✓")
            self.validation_icon.setStyleSheet(f"color: {COLORS['success']}; font-weight: bold; font-size: 16px;")
            self.validation_icon.show()
        else:
            self.validation_icon.hide()

        # Hide error message
        self.error_label.hide()

    def clear_validation(self):
        """Clear validation state and messages."""
        self.line_edit.setStyleSheet("")
        self.validation_icon.hide()
        self.error_label.hide()
        self._is_valid = True
        self._last_validation_result = ValidationResult(valid=True)

    # Public API - mirrors LineEdit interface

    def text(self) -> str:
        """Get current text value."""
        return self.line_edit.text()

    def setText(self, text: str):
        """Set text value."""
        self.line_edit.setText(text)
        if self.validate_on == 'change':
            self.validate()

    def clear(self):
        """Clear the text."""
        self.line_edit.clear()
        self.clear_validation()

    def setPlaceholderText(self, text: str):
        """Set placeholder text."""
        self.line_edit.setPlaceholderText(text)

    def placeholderText(self) -> str:
        """Get placeholder text."""
        return self.line_edit.placeholderText()

    def setReadOnly(self, read_only: bool):
        """Set read-only state."""
        self.line_edit.setReadOnly(read_only)

    def isReadOnly(self) -> bool:
        """Check if read-only."""
        return self.line_edit.isReadOnly()

    def setEnabled(self, enabled: bool):
        """Set enabled state."""
        super().setEnabled(enabled)
        self.line_edit.setEnabled(enabled)

    def setFocus(self):
        """Set focus to the input field."""
        self.line_edit.setFocus()

    # Validation API

    def is_valid(self) -> bool:
        """
        Check if current value is valid.

        Returns:
            True if valid, False otherwise
        """
        return self._is_valid

    def get_validation_result(self) -> ValidationResult:
        """
        Get the last validation result.

        Returns:
            Last ValidationResult from validation
        """
        return self._last_validation_result

    def add_validator(self, validator: BaseValidator):
        """Add a validator to the list."""
        self.validators.append(validator)

    def remove_validator(self, validator: BaseValidator):
        """Remove a validator from the list."""
        if validator in self.validators:
            self.validators.remove(validator)

    def clear_validators(self):
        """Clear all validators."""
        self.validators.clear()

    # Accessibility

    def setAccessibleName(self, name: str):
        """Set accessible name."""
        super().setAccessibleName(name)
        self.line_edit.setAccessibleName(name)

    def setAccessibleDescription(self, description: str):
        """Set accessible description."""
        super().setAccessibleDescription(description)
        self.line_edit.setAccessibleDescription(description)

"""
ValidatedComboBox component - ComboBox with inline validation and error display.

Similar to ValidatedLineEdit but wraps ComboBox for dropdown selections.
"""

from typing import List, Optional, Callable
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from qfluentwidgets import ComboBox

from .validators import BaseValidator, ValidationResult
from GUI_Qt.styles.theme_config import COLORS


class ValidatedComboBox(QWidget):
    """ComboBox with inline validation and error display."""

    # Signals
    validationChanged = Signal(bool)  # Emitted when validation state changes
    currentTextChanged = Signal(str)  # Emitted when selection changes
    currentIndexChanged = Signal(int)  # Emitted when index changes

    def __init__(
        self,
        validators: Optional[List[BaseValidator]] = None,
        validate_on: str = 'change',
        parent: Optional[QWidget] = None,
        tr_func: Optional[Callable] = None
    ):
        """
        Initialize ValidatedComboBox.

        Args:
            validators: List of validators to apply
            validate_on: When to validate ('change', 'manual')
                        - 'change': Validate on selection change (default)
                        - 'manual': Only validate when validate() is called
            parent: Parent widget
            tr_func: Translation function
        """
        super().__init__(parent)
        self.validators = validators or []
        self.validate_on = validate_on
        self.tr = tr_func if tr_func else lambda key, **kwargs: key
        self._is_valid = True
        self._last_validation_result = ValidationResult(valid=True)

        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        """Initialize UI components."""
        # Main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(4)

        # Input row (ComboBox + validation icon)
        self.input_layout = QHBoxLayout()
        self.input_layout.setContentsMargins(0, 0, 0, 0)
        self.input_layout.setSpacing(8)

        # ComboBox
        self.combo_box = ComboBox(self)
        self.input_layout.addWidget(self.combo_box, 1)

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
        if self.validate_on == 'change':
            # Validate on selection change
            self.combo_box.currentTextChanged.connect(lambda: self.validate())

        # Always forward signals
        self.combo_box.currentTextChanged.connect(self.currentTextChanged.emit)
        self.combo_box.currentIndexChanged.connect(self.currentIndexChanged.emit)

    def validate(self) -> bool:
        """
        Validate the current value against all validators.

        Returns:
            True if validation passed, False otherwise
        """
        value = self.combo_box.currentText()

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
        # Set error border on ComboBox
        self.combo_box.setStyleSheet(f"""
            ComboBox {{
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
        self.combo_box.setStyleSheet("")

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
        self.combo_box.setStyleSheet("")

        # Show success icon (checkmark) only if a selection is made
        if self.combo_box.currentText():
            self.validation_icon.setText("✓")
            self.validation_icon.setStyleSheet(f"color: {COLORS['success']}; font-weight: bold; font-size: 16px;")
            self.validation_icon.show()
        else:
            self.validation_icon.hide()

        # Hide error message
        self.error_label.hide()

    def clear_validation(self):
        """Clear validation state and messages."""
        self.combo_box.setStyleSheet("")
        self.validation_icon.hide()
        self.error_label.hide()
        self._is_valid = True
        self._last_validation_result = ValidationResult(valid=True)

    # Public API - mirrors ComboBox interface

    def addItem(self, text: str, userData=None):
        """Add an item to the combo box."""
        self.combo_box.addItem(text, userData)

    def addItems(self, texts: List[str]):
        """Add multiple items to the combo box."""
        self.combo_box.addItems(texts)

    def clear(self):
        """Clear all items."""
        self.combo_box.clear()
        self.clear_validation()

    def currentText(self) -> str:
        """Get current text value."""
        return self.combo_box.currentText()

    def currentIndex(self) -> int:
        """Get current index."""
        return self.combo_box.currentIndex()

    def setCurrentText(self, text: str):
        """Set current text."""
        self.combo_box.setCurrentText(text)
        if self.validate_on == 'change':
            self.validate()

    def setCurrentIndex(self, index: int):
        """Set current index."""
        self.combo_box.setCurrentIndex(index)
        if self.validate_on == 'change':
            self.validate()

    def count(self) -> int:
        """Get number of items."""
        return self.combo_box.count()

    def itemText(self, index: int) -> str:
        """Get text of item at index."""
        return self.combo_box.itemText(index)

    def setEnabled(self, enabled: bool):
        """Set enabled state."""
        super().setEnabled(enabled)
        self.combo_box.setEnabled(enabled)

    def setFocus(self):
        """Set focus to the combo box."""
        self.combo_box.setFocus()

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
        self.combo_box.setAccessibleName(name)

    def setAccessibleDescription(self, description: str):
        """Set accessible description."""
        super().setAccessibleDescription(description)
        self.combo_box.setAccessibleDescription(description)

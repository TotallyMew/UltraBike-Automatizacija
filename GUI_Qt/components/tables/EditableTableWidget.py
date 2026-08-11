"""
EditableTableWidget - Table with inline cell editing and validation.

Features:
- Double-click to edit cells
- Tab/Enter navigation between editable cells
- Per-column validation with visual feedback
- Invalid cells show red border + tooltip with error
- Valid cells show green checkmark icon
"""

from typing import List, Dict, Optional, Callable
from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QLineEdit, QWidget,
    QHeaderView, QAbstractItemView
)
from PySide6.QtGui import QIcon, QColor, QBrush

from ..validation.validators import BaseValidator, ValidationResult
from GUI_Qt.widgets import enable_table_copy


class EditableTableWidget(QTableWidget):
    """Table widget with inline editing and validation support."""

    # Signals
    cellValidationChanged = Signal(int, int, bool)  # row, col, is_valid
    editingFinished = Signal(int, int, str)  # row, col, new_value

    def __init__(
        self,
        columns: List[str],
        editable_columns: Optional[List[int]] = None,
        validators: Optional[Dict[int, List[BaseValidator]]] = None,
        parent: Optional[QWidget] = None,
        tr_func: Optional[Callable] = None
    ):
        """
        Initialize EditableTableWidget.

        Args:
            columns: List of column headers
            editable_columns: List of column indices that are editable (None = all)
            validators: Dict mapping column index to list of validators
            parent: Parent widget
            tr_func: Translation function
        """
        super().__init__(parent)
        self.tr = tr_func if tr_func else lambda key, **kwargs: key
        self.columns = columns
        self.editable_columns = editable_columns if editable_columns is not None else list(range(len(columns)))
        self.validators = validators or {}
        self._validation_errors: Dict[tuple, str] = {}  # (row, col) -> error message
        self._current_editor: Optional[QLineEdit] = None
        self._editor_row: int = -1
        self._editor_col: int = -1

        self._init_ui()
        self._setup_signals()

    def _init_ui(self):
        """Initialize UI components."""
        # Set columns
        self.setColumnCount(len(self.columns))
        self.setHorizontalHeaderLabels(self.columns)

        # Table settings
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        enable_table_copy(self)

        # Header settings
        header = self.horizontalHeader()
        header.setStretchLastSection(True)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # Enable sorting
        self.setSortingEnabled(True)

    def _setup_signals(self):
        """Setup internal signals."""
        self.itemDoubleClicked.connect(self._on_item_double_clicked)

    def _on_item_double_clicked(self, item: QTableWidgetItem):
        """Handle double-click to start editing."""
        if item is None:
            return

        row = item.row()
        col = item.column()

        # Check if column is editable
        if col not in self.editable_columns:
            return

        self._start_editing(row, col)

    def _start_editing(self, row: int, col: int):
        """Start editing a cell."""
        # Close any existing editor
        if self._current_editor is not None:
            self._finish_editing()

        # Get current value
        item = self.item(row, col)
        current_value = item.text() if item else ""

        # Create editor
        editor = QLineEdit(self)
        editor.setText(current_value)
        editor.selectAll()
        editor.setFocus()

        # Position editor over cell
        self.setCellWidget(row, col, editor)

        # Store editor info
        self._current_editor = editor
        self._editor_row = row
        self._editor_col = col

        # Connect signals
        editor.editingFinished.connect(self._finish_editing)
        editor.installEventFilter(self)

    def _finish_editing(self):
        """Finish editing and validate."""
        if self._current_editor is None:
            return

        # Get new value
        new_value = self._current_editor.text()
        row = self._editor_row
        col = self._editor_col

        # Remove editor
        self.removeCellWidget(row, col)
        self._current_editor = None
        self._editor_row = -1
        self._editor_col = -1

        # Update item
        item = self.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.setItem(row, col, item)

        old_value = item.text()
        if new_value != old_value:
            item.setText(new_value)

            # Validate
            self._validate_cell(row, col)

            # Emit signal
            self.editingFinished.emit(row, col, new_value)

    def eventFilter(self, obj: QWidget, event: QEvent) -> bool:
        """Filter events for editor."""
        if obj == self._current_editor and event.type() == QEvent.Type.KeyPress:
            key = event.key()

            # Tab - move to next editable cell
            if key == Qt.Key.Key_Tab:
                self._finish_editing()
                self._move_to_next_editable_cell()
                return True

            # Enter/Return - finish editing
            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._finish_editing()
                return True

            # Escape - cancel editing
            elif key == Qt.Key.Key_Escape:
                if self._current_editor:
                    self.removeCellWidget(self._editor_row, self._editor_col)
                    self._current_editor = None
                    self._editor_row = -1
                    self._editor_col = -1
                return True

        return super().eventFilter(obj, event)

    def _move_to_next_editable_cell(self):
        """Move focus to next editable cell."""
        if self._editor_row < 0 or self._editor_col < 0:
            return

        row = self._editor_row
        col = self._editor_col

        # Find next editable column in same row
        for next_col in range(col + 1, self.columnCount()):
            if next_col in self.editable_columns:
                self._start_editing(row, next_col)
                return

        # Move to next row, first editable column
        if row + 1 < self.rowCount() and self.editable_columns:
            first_editable = min(self.editable_columns)
            self._start_editing(row + 1, first_editable)

    def _validate_cell(self, row: int, col: int) -> bool:
        """
        Validate a cell and update visual feedback.

        Args:
            row: Row index
            col: Column index

        Returns:
            True if valid, False otherwise
        """
        item = self.item(row, col)
        if item is None:
            return True

        value = item.text()

        # Get validators for this column
        column_validators = self.validators.get(col, [])
        if not column_validators:
            # No validators - clear any error state
            self._clear_cell_error(row, col)
            return True

        # Run validators
        for validator in column_validators:
            result = validator.validate(value)
            if not result.valid:
                self._set_cell_error(row, col, result.error)
                self.cellValidationChanged.emit(row, col, False)
                return False

        # All validations passed
        self._set_cell_valid(row, col)
        self.cellValidationChanged.emit(row, col, True)
        return True

    def _set_cell_error(self, row: int, col: int, error_message: str):
        """Mark cell as invalid with error styling."""
        item = self.item(row, col)
        if item is None:
            return

        # Store error
        self._validation_errors[(row, col)] = error_message

        # Set red background
        item.setBackground(QBrush(QColor(200, 29, 37, 30)))  # Light red tint

        # Set tooltip with error
        item.setToolTip(f"❌ {error_message}")

        # Set text color to error
        item.setForeground(QBrush(QColor(200, 29, 37)))

    def _set_cell_valid(self, row: int, col: int):
        """Mark cell as valid with success styling."""
        item = self.item(row, col)
        if item is None:
            return

        # Clear error
        if (row, col) in self._validation_errors:
            del self._validation_errors[(row, col)]

        # Set light green background
        item.setBackground(QBrush(QColor(16, 185, 129, 20)))  # Light green tint

        # Set tooltip with checkmark
        item.setToolTip("✓ Valid")

        # Reset text color
        item.setForeground(QBrush(QColor(0, 0, 0)))

    def _clear_cell_error(self, row: int, col: int):
        """Clear error state from cell."""
        item = self.item(row, col)
        if item is None:
            return

        # Clear error
        if (row, col) in self._validation_errors:
            del self._validation_errors[(row, col)]

        # Clear background
        item.setBackground(QBrush(Qt.GlobalColor.transparent))

        # Clear tooltip
        item.setToolTip("")

        # Reset text color
        item.setForeground(QBrush(QColor(0, 0, 0)))

    def validate_row(self, row: int) -> bool:
        """
        Validate all editable cells in a row.

        Args:
            row: Row index

        Returns:
            True if all cells are valid, False otherwise
        """
        is_valid = True
        for col in self.editable_columns:
            if not self._validate_cell(row, col):
                is_valid = False
        return is_valid

    def validate_all(self) -> bool:
        """
        Validate all editable cells in the table.

        Returns:
            True if all cells are valid, False otherwise
        """
        is_valid = True
        for row in range(self.rowCount()):
            if not self.validate_row(row):
                is_valid = False
        return is_valid

    def get_row_errors(self, row: int) -> List[str]:
        """
        Get all validation errors for a row.

        Args:
            row: Row index

        Returns:
            List of error messages
        """
        errors = []
        for col in self.editable_columns:
            if (row, col) in self._validation_errors:
                errors.append(f"{self.columns[col]}: {self._validation_errors[(row, col)]}")
        return errors

    def get_all_errors(self) -> Dict[int, List[str]]:
        """
        Get all validation errors grouped by row.

        Returns:
            Dict mapping row index to list of error messages
        """
        errors_by_row = {}
        for (row, col), error in self._validation_errors.items():
            if row not in errors_by_row:
                errors_by_row[row] = []
            errors_by_row[row].append(f"{self.columns[col]}: {error}")
        return errors_by_row

    def clear_all_validation(self):
        """Clear all validation states."""
        for row in range(self.rowCount()):
            for col in range(self.columnCount()):
                self._clear_cell_error(row, col)
        self._validation_errors.clear()

    def is_cell_editable(self, row: int, col: int) -> bool:
        """Check if a cell is editable."""
        return col in self.editable_columns

    def get_row_data(self, row: int) -> List[str]:
        """
        Get all cell values in a row.

        Args:
            row: Row index

        Returns:
            List of cell values as strings
        """
        data = []
        for col in range(self.columnCount()):
            item = self.item(row, col)
            data.append(item.text() if item else "")
        return data

    def set_row_data(self, row: int, data: List[str]):
        """
        Set all cell values in a row.

        Args:
            row: Row index
            data: List of values to set
        """
        for col, value in enumerate(data):
            if col >= self.columnCount():
                break
            item = self.item(row, col)
            if item is None:
                item = QTableWidgetItem()
                self.setItem(row, col, item)
            item.setText(str(value))

        # Validate editable cells
        for col in self.editable_columns:
            if col < len(data):
                self._validate_cell(row, col)

"""
BulkActionsToolbar - Toolbar for batch table operations.

Features:
- Select All / Deselect All buttons
- Delete Selected (count) button
- Retry Failed button (for batch operations)
- Auto-enable/disable based on selection
"""

from typing import Optional, Callable
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QTableWidget, QAbstractItemView
)
from qfluentwidgets import PushButton, TransparentToolButton, FluentIcon as FIF


class BulkActionsToolbar(QWidget):
    """Toolbar widget for batch table operations."""

    # Signals
    selectAllClicked = Signal()
    deselectAllClicked = Signal()
    deleteSelectedClicked = Signal()
    retryFailedClicked = Signal()

    def __init__(
        self,
        table: Optional[QTableWidget] = None,
        show_retry: bool = True,
        parent: Optional[QWidget] = None,
        tr_func: Optional[Callable] = None
    ):
        """
        Initialize BulkActionsToolbar.

        Args:
            table: Table widget to manage (can be set later with set_table)
            show_retry: Whether to show "Retry Failed" button
            parent: Parent widget
            tr_func: Translation function
        """
        super().__init__(parent)
        self.tr = tr_func if tr_func else lambda key, **kwargs: key
        self.table = table
        self.show_retry = show_retry

        self._init_ui()
        if table:
            self._connect_table(table)

    def _init_ui(self):
        """Initialize UI components."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Select All button
        self.select_all_button = PushButton(self.tr("batch.select_all"), self)
        self.select_all_button.setIcon(FIF.CHECKBOX.icon())
        self.select_all_button.clicked.connect(self._on_select_all)
        layout.addWidget(self.select_all_button)

        # Deselect All button
        self.deselect_all_button = PushButton(self.tr("batch.deselect_all"), self)
        self.deselect_all_button.setIcon(FIF.CANCEL.icon())
        self.deselect_all_button.clicked.connect(self._on_deselect_all)
        self.deselect_all_button.setEnabled(False)
        layout.addWidget(self.deselect_all_button)

        # Delete Selected button
        self.delete_selected_button = PushButton(
            self.tr("batch.delete_selected", count=0),
            self
        )
        self.delete_selected_button.setIcon(FIF.DELETE.icon())
        self.delete_selected_button.clicked.connect(self._on_delete_selected)
        self.delete_selected_button.setEnabled(False)
        # Style as warning/destructive
        self.delete_selected_button.setStyleSheet("""
            QPushButton {
                color: #C81D25;
                border: 1px solid #C81D25;
            }
            QPushButton:hover {
                background-color: rgba(200, 29, 37, 0.1);
            }
            QPushButton:disabled {
                color: #9CA3AF;
                border-color: #9CA3AF;
            }
        """)
        layout.addWidget(self.delete_selected_button)

        # Retry Failed button (optional)
        if self.show_retry:
            self.retry_failed_button = PushButton(self.tr("batch.retry_failed"), self)
            self.retry_failed_button.setIcon(FIF.SYNC.icon())
            self.retry_failed_button.clicked.connect(self._on_retry_failed)
            layout.addWidget(self.retry_failed_button)

        layout.addStretch()

    def _connect_table(self, table: QTableWidget):
        """Connect to table's selection model."""
        if table is None:
            return

        selection_model = table.selectionModel()
        if selection_model:
            selection_model.selectionChanged.connect(self._on_selection_changed)

    def set_table(self, table: QTableWidget):
        """
        Set the table widget to manage.

        Args:
            table: Table widget
        """
        self.table = table
        self._connect_table(table)
        self._update_button_states()

    def _on_select_all(self):
        """Handle Select All button click."""
        if self.table:
            self.table.selectAll()
        self.selectAllClicked.emit()

    def _on_deselect_all(self):
        """Handle Deselect All button click."""
        if self.table:
            self.table.clearSelection()
        self.deselectAllClicked.emit()

    def _on_delete_selected(self):
        """Handle Delete Selected button click."""
        self.deleteSelectedClicked.emit()

    def _on_retry_failed(self):
        """Handle Retry Failed button click."""
        self.retryFailedClicked.emit()

    def _on_selection_changed(self):
        """Handle table selection change."""
        self._update_button_states()

    def _update_button_states(self):
        """Update button enabled states based on selection."""
        if not self.table:
            return

        selected_rows = self.get_selected_row_count()
        total_rows = self.table.rowCount()

        # Deselect All: enabled when something is selected
        self.deselect_all_button.setEnabled(selected_rows > 0)

        # Delete Selected: enabled when something is selected
        self.delete_selected_button.setEnabled(selected_rows > 0)
        self.delete_selected_button.setText(
            self.tr("batch.delete_selected", count=selected_rows)
        )

        # Select All: always enabled if there are rows
        self.select_all_button.setEnabled(total_rows > 0)

    def get_selected_row_count(self) -> int:
        """
        Get the number of selected rows.

        Returns:
            Number of selected rows
        """
        if not self.table:
            return 0

        selected_indexes = self.table.selectionModel().selectedRows()
        return len(selected_indexes)

    def get_selected_rows(self) -> list:
        """
        Get list of selected row indices.

        Returns:
            List of row indices (sorted)
        """
        if not self.table:
            return []

        selected_indexes = self.table.selectionModel().selectedRows()
        return sorted([index.row() for index in selected_indexes])

    def delete_selected_rows(self):
        """
        Delete selected rows from the table.

        Note: Deletes from bottom to top to maintain indices.
        """
        if not self.table:
            return

        selected_rows = self.get_selected_rows()

        # Delete from bottom to top to maintain indices
        for row in reversed(selected_rows):
            self.table.removeRow(row)

        self._update_button_states()

    def refresh(self):
        """Refresh button states (call after table data changes)."""
        self._update_button_states()

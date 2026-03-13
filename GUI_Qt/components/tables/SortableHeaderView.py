"""
SortableHeaderView - Header view with visual sort indicators.

Features:
- Click column header to sort
- Visual indicator (up/down arrow)
- Cycle: unsorted → ascending → descending → unsorted
"""

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHeaderView, QStyleOptionHeader, QStyle
from PySide6.QtGui import QPainter


class SortableHeaderView(QHeaderView):
    """Header view with enhanced sorting capabilities and visual indicators."""

    # Signal emitted when sort order changes
    sortOrderChanged = Signal(int, Qt.SortOrder)  # column, order

    def __init__(self, orientation: Qt.Orientation, parent=None):
        """
        Initialize SortableHeaderView.

        Args:
            orientation: Qt.Horizontal or Qt.Vertical
            parent: Parent widget
        """
        super().__init__(orientation, parent)
        self._sort_column = -1
        self._sort_order = Qt.SortOrder.AscendingOrder
        self._sort_enabled = True

        # Make sections clickable
        self.setSectionsClickable(True)
        self.sectionClicked.connect(self._on_section_clicked)

        # Visual settings
        self.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setHighlightSections(True)

    def _on_section_clicked(self, logical_index: int):
        """Handle section click to toggle sort order."""
        if not self._sort_enabled:
            return

        # Determine new sort order
        if self._sort_column == logical_index:
            # Same column - cycle through sort orders
            if self._sort_order == Qt.SortOrder.AscendingOrder:
                # Ascending → Descending
                self._sort_order = Qt.SortOrder.DescendingOrder
            elif self._sort_order == Qt.SortOrder.DescendingOrder:
                # Descending → Unsorted (no sorting)
                self._sort_column = -1
                self._sort_order = Qt.SortOrder.AscendingOrder
        else:
            # New column - start with ascending
            self._sort_column = logical_index
            self._sort_order = Qt.SortOrder.AscendingOrder

        # Emit signal
        if self._sort_column >= 0:
            self.sortOrderChanged.emit(self._sort_column, self._sort_order)

        # Update display
        self.viewport().update()

    def paintSection(self, painter: QPainter, rect, logical_index: int):
        """Override to draw sort indicator."""
        # Draw default header
        super().paintSection(painter, rect, logical_index)

        # Draw sort indicator if this is the sorted column
        if logical_index == self._sort_column:
            # Draw arrow
            arrow_size = 8
            center_y = rect.center().y()
            right_x = rect.right() - 10

            painter.save()
            painter.setPen(Qt.GlobalColor.black)
            painter.setBrush(Qt.GlobalColor.black)

            if self._sort_order == Qt.SortOrder.AscendingOrder:
                # Draw up arrow (▲)
                points = [
                    (right_x, center_y + arrow_size // 2),
                    (right_x - arrow_size, center_y + arrow_size // 2),
                    (right_x - arrow_size // 2, center_y - arrow_size // 2)
                ]
            else:
                # Draw down arrow (▼)
                points = [
                    (right_x, center_y - arrow_size // 2),
                    (right_x - arrow_size, center_y - arrow_size // 2),
                    (right_x - arrow_size // 2, center_y + arrow_size // 2)
                ]

            from PySide6.QtGui import QPolygon
            from PySide6.QtCore import QPoint
            polygon = QPolygon([QPoint(x, y) for x, y in points])
            painter.drawPolygon(polygon)

            painter.restore()

    def get_sort_column(self) -> int:
        """
        Get the currently sorted column.

        Returns:
            Column index, or -1 if no sorting
        """
        return self._sort_column

    def get_sort_order(self) -> Qt.SortOrder:
        """
        Get the current sort order.

        Returns:
            Qt.AscendingOrder or Qt.DescendingOrder
        """
        return self._sort_order

    def set_sort_indicator(self, column: int, order: Qt.SortOrder):
        """
        Programmatically set the sort indicator.

        Args:
            column: Column index (-1 for no sorting)
            order: Qt.AscendingOrder or Qt.DescendingOrder
        """
        self._sort_column = column
        self._sort_order = order
        self.viewport().update()

    def clear_sort_indicator(self):
        """Clear the sort indicator."""
        self._sort_column = -1
        self._sort_order = Qt.SortOrder.AscendingOrder
        self.viewport().update()

    def set_sort_enabled(self, enabled: bool):
        """
        Enable or disable sorting.

        Args:
            enabled: True to enable sorting, False to disable
        """
        self._sort_enabled = enabled
        self.setSectionsClickable(enabled)

    def is_sort_enabled(self) -> bool:
        """
        Check if sorting is enabled.

        Returns:
            True if sorting is enabled, False otherwise
        """
        return self._sort_enabled

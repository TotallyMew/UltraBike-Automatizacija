"""
GUI_Qt/widgets/DragFillHandle.py

Excel-like drag fill handle for QTableWidget.

When a table cell is selected, a small square handle appears at its bottom-right
corner.  Dragging the handle downward copies the source cell's value into every
cell in the drag range within the same column.

Usage:
    handle = DragFillHandle(table)
    # The handle installs itself as an event filter and manages its own visibility.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QTableWidget,
    QWidget,
)
from qfluentwidgets import CheckBox as FluentCheckBox, ComboBox, LineEdit, isDarkTheme

from GUI_Qt.widgets.FilterableComboBox import FilterableComboBox

_COMBO_TYPES = (ComboBox, FilterableComboBox)

from GUI_Qt.styles.theme_config import COLORS

_HANDLE_SIZE = 10


class DragFillHandle(QWidget):
    """Small square overlay that enables Excel-style fill-down on a QTableWidget."""

    def __init__(self, table: QTableWidget, parent: QWidget | None = None):
        super().__init__(table.viewport() if parent is None else parent)
        self._table = table
        self._dragging = False
        self._source_row: int = -1
        self._source_col: int = -1
        self._current_row: int = -1
        self._highlight_rows: list[int] = []

        self.setFixedSize(_HANDLE_SIZE, _HANDLE_SIZE)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setToolTip("Drag to fill cells")
        self.hide()

        # Listen for selection and scroll changes on the table viewport.
        table.viewport().installEventFilter(self)
        table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        table.verticalScrollBar().valueChanged.connect(self._reposition)
        table.horizontalScrollBar().valueChanged.connect(self._reposition)

    # -- Painting ------------------------------------------------------------

    def paintEvent(self, event):
        p = QPainter(self)
        accent = QColor(COLORS.get("space_indigo", "#2B2D42"))
        if isDarkTheme():
            accent = QColor(COLORS.get("lavender_grey", "#8D99AE"))
        p.fillRect(self.rect(), accent)
        p.end()

    # -- Positioning ---------------------------------------------------------

    def _on_selection_changed(self):
        sel = self._table.selectedIndexes()
        if len(sel) == 1:
            idx = sel[0]
            self._source_row = idx.row()
            self._source_col = idx.column()
            # Only show for editable columns with cell widgets
            if self._table.cellWidget(self._source_row, self._source_col) is not None:
                self._reposition()
                self.show()
                self.raise_()
                return
        self.hide()

    def _reposition(self):
        if self._source_row < 0 or self._source_col < 0:
            self.hide()
            return

        rect = self._table.visualRect(
            self._table.model().index(self._source_row, self._source_col)
        )
        if rect.isNull():
            self.hide()
            return

        # Bottom-right corner of the cell, inset by 1px
        x = rect.right() - _HANDLE_SIZE + 1
        y = rect.bottom() - _HANDLE_SIZE + 1
        self.move(x, y)

    # -- Drag interaction ----------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._source_row >= 0:
            self._dragging = True
            self._current_row = self._source_row
            self._highlight_rows = []
            self.grabMouse()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self._dragging:
            return
        # Map to viewport coordinates
        vp_pos = self.mapToParent(event.pos())
        idx = self._table.indexAt(vp_pos)
        if idx.isValid() and idx.column() == self._source_col:
            target_row = idx.row()
        else:
            target_row = self._current_row

        if target_row != self._current_row:
            self._current_row = target_row
            # Highlight range
            start = min(self._source_row + 1, target_row)
            end = max(self._source_row + 1, target_row)
            self._highlight_rows = list(range(start, end + 1))
            self._apply_highlight()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if not self._dragging:
            return
        self._dragging = False
        self.releaseMouse()
        self._clear_highlight()

        if self._current_row > self._source_row:
            self._fill_range(self._source_row, self._source_col,
                             self._source_row + 1, self._current_row)
        elif self._current_row < self._source_row:
            self._fill_range(self._source_row, self._source_col,
                             self._current_row, self._source_row - 1)
        event.accept()

    # -- Fill logic ----------------------------------------------------------

    def _fill_range(self, src_row: int, col: int, start_row: int, end_row: int):
        """Copy value from *src_row* into rows *start_row..end_row* (inclusive)."""
        src_widget = self._get_inner_widget(src_row, col)
        if src_widget is None:
            return

        src_value = self._read_value(src_widget)
        if src_value is None:
            return

        for row in range(start_row, end_row + 1):
            dst_widget = self._get_inner_widget(row, col)
            if dst_widget is not None:
                self._write_value(dst_widget, src_value)

    def _get_inner_widget(self, row: int, col: int) -> QWidget | None:
        """Return the actual input widget inside the table cell container."""
        container = self._table.cellWidget(row, col)
        if container is None:
            return None
        # Cells use a container QWidget with a QHBoxLayout wrapping the real widget.
        layout = container.layout()
        if layout is not None and layout.count() > 0:
            inner = layout.itemAt(0).widget()
            if inner is not None:
                return inner
        return container

    @staticmethod
    def _read_value(widget: QWidget):
        """Read a value from a cell widget."""
        if isinstance(widget, _COMBO_TYPES):
            return ("combo", widget.currentIndex(), widget.currentText())
        if isinstance(widget, LineEdit):
            return ("text", widget.text())
        if isinstance(widget, (QCheckBox, FluentCheckBox)):
            return ("check", widget.isChecked())
        return None

    @staticmethod
    def _write_value(widget: QWidget, value):
        """Write a value into a cell widget."""
        kind = value[0]
        if kind == "combo" and isinstance(widget, _COMBO_TYPES):
            idx = widget.findText(value[2])
            if idx >= 0:
                widget.setCurrentIndex(idx)
            else:
                # Value not in this combo's items — skip
                pass
        elif kind == "text" and isinstance(widget, LineEdit):
            widget.setText(value[1])
        elif kind == "check" and isinstance(widget, (QCheckBox, FluentCheckBox)):
            widget.setChecked(value[1])

    # -- Visual highlight ----------------------------------------------------

    def _apply_highlight(self):
        for row in range(self._table.rowCount()):
            widget = self._table.cellWidget(row, self._source_col)
            if widget is None:
                continue
            if row in self._highlight_rows:
                accent = COLORS.get("space_indigo", "#2B2D42")
                if isDarkTheme():
                    accent = COLORS.get("lavender_grey", "#8D99AE")
                widget.setStyleSheet(
                    f"background: rgba({QColor(accent).red()}, "
                    f"{QColor(accent).green()}, {QColor(accent).blue()}, 30);"
                )
            else:
                widget.setStyleSheet("")

    def _clear_highlight(self):
        for row in self._highlight_rows:
            widget = self._table.cellWidget(row, self._source_col)
            if widget is not None:
                widget.setStyleSheet("")
        self._highlight_rows = []

    # -- Event filter --------------------------------------------------------

    def eventFilter(self, obj, event):
        if obj is self._table.viewport():
            if event.type() == QEvent.Type.Resize:
                self._reposition()
        return False

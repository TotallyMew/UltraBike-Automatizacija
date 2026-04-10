"""
GUI_Qt/widgets/FrozenColumnTableWidget.py

Provides a frozen-column overlay on top of a QTableWidget.

The widget consists of a *main* QTableWidget (the one the caller already owns)
and a lightweight *frozen* QTableWidget that floats over the left edge.

Vertical scrolling is pixel-perfectly synchronised via scroll-bar value
signals (with a guard flag to prevent infinite loops).

Horizontal scrolling of the main table triggers a shadow line at the
frozen boundary to give a visual depth cue.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QSizePolicy,
    QTableWidget,
    QWidget,
)

from qfluentwidgets import isDarkTheme


class FrozenColumnOverlay(QWidget):
    """Overlay widget that houses a frozen-column QTableWidget.

    Parameters
    ----------
    main_table : QTableWidget
        The primary (scrollable) table.
    frozen_cols : list[int]
        Column indices to freeze (leftmost columns).
    parent : QWidget | None
    """

    def __init__(self, main_table: QTableWidget, frozen_cols: list[int], parent=None):
        super().__init__(parent)
        self._main = main_table
        self._frozen_cols = sorted(frozen_cols)
        self._syncing = False  # guard for scroll sync

        # -- Build frozen table --
        self.frozen = QTableWidget(self._main.rowCount(), self._main.columnCount(), self)
        self.frozen.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.frozen.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.frozen.verticalHeader().setVisible(False)
        self.frozen.horizontalHeader().setVisible(False)
        self.frozen.setShowGrid(False)
        self.frozen.setAlternatingRowColors(True)
        self.frozen.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.frozen.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.frozen.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Match main table's row height mode
        self.frozen.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._sync_row_heights()

        # Hide all non-frozen columns in the frozen table
        for c in range(self._main.columnCount()):
            if c not in self._frozen_cols:
                self.frozen.setColumnHidden(c, True)
            else:
                self.frozen.setColumnWidth(c, self._main.columnWidth(c))

        # Match frozen table styling to main
        self.frozen.setStyleSheet(self._main.styleSheet())

        # -- Scroll sync --
        self._main.verticalScrollBar().valueChanged.connect(self._on_main_vscroll)
        self.frozen.verticalScrollBar().valueChanged.connect(self._on_frozen_vscroll)

        # -- Shadow state --
        self._show_shadow = False
        self._main.horizontalScrollBar().valueChanged.connect(self._on_main_hscroll)

        # Let mouse events pass through to the main table underneath
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.frozen.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        # Initial geometry (deferred — parent layout may not be ready yet)
        QTimer.singleShot(0, self._reposition)
        self.raise_()
        self.show()

    # --------------------------------------------------------------- Sync

    def _on_main_vscroll(self, value: int):
        if self._syncing:
            return
        self._syncing = True
        self.frozen.verticalScrollBar().setValue(value)
        self._syncing = False

    def _on_frozen_vscroll(self, value: int):
        if self._syncing:
            return
        self._syncing = True
        self._main.verticalScrollBar().setValue(value)
        self._syncing = False

    def _on_main_hscroll(self, value: int):
        should_show = value > 0
        if should_show != self._show_shadow:
            self._show_shadow = should_show
            self.update()

    def _sync_row_heights(self):
        h = self._main.verticalHeader().defaultSectionSize()
        self.frozen.verticalHeader().setDefaultSectionSize(h)

    def sync_row_count(self):
        """Call after rows are added/removed from the main table."""
        self.frozen.setRowCount(self._main.rowCount())
        self._sync_row_heights()

    def sync_column_widths(self):
        """Call after column widths change in the main table."""
        for c in self._frozen_cols:
            self.frozen.setColumnWidth(c, self._main.columnWidth(c))
        self._reposition()

    def sync_density(self):
        """Call after density toggle changes row heights."""
        self._sync_row_heights()

    def update_theme(self, stylesheet: str):
        self.frozen.setStyleSheet(stylesheet)
        self.frozen.setAlternatingRowColors(True)
        self.update()

    # ----------------------------------------------------------- Geometry

    def _frozen_width(self) -> int:
        w = 0
        for c in self._frozen_cols:
            if not self._main.isColumnHidden(c):
                w += self._main.columnWidth(c)
        return w

    def _reposition(self):
        """Place frozen overlay exactly over the left frozen columns of the main table."""
        vp = self._main.viewport()
        parent = self.parentWidget()
        if parent is None:
            return

        # Safe mapTo — the viewport must be a descendant of our parent
        try:
            vp_pos = vp.mapTo(parent, vp.rect().topLeft())
        except Exception:
            return

        fw = self._frozen_width()

        self.setGeometry(
            vp_pos.x(),
            vp_pos.y(),
            fw,
            vp.height(),
        )
        self.frozen.setGeometry(0, 0, fw, self.height())

    # ----------------------------------------------------------- Paint

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._show_shadow:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            # Draw a 4px gradient shadow on the right edge
            w = self.width()
            h = self.height()
            base = QColor(0, 0, 0, 40) if not isDarkTheme() else QColor(0, 0, 0, 80)
            for i in range(4):
                alpha = base.alpha() * (4 - i) // 4
                c = QColor(0, 0, 0, alpha)
                painter.setPen(c)
                painter.drawLine(w - 1 - i, 0, w - 1 - i, h)
            painter.end()

    # ----------------------------------------------------------- Events

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.frozen.setGeometry(0, 0, self.width(), self.height())

    def reposition(self):
        """Public method to recalculate geometry (call on parent resize)."""
        self._reposition()

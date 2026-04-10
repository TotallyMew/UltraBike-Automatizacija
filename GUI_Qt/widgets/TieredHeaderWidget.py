"""
GUI_Qt/widgets/TieredHeaderWidget.py

Two-tier category header bar for the batch table.

Renders color-coded category labels above column groups (e.g. "Product Info",
"Attributes", "Titles").  The labels stay centered within the *visible* portion
of each category span when the table scrolls horizontally.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QTableWidget, QWidget
from qfluentwidgets import isDarkTheme

from GUI_Qt.screens.batch_columns import COL, COLUMN_GROUPS, COLUMNS
from GUI_Qt.styles.theme_config import COLORS, FONTS, RADII

# Height of the tier bar
_TIER_HEIGHT = 26

# Category colors: i18n_key → (light_color, dark_color)
_CATEGORY_COLORS: dict[str, tuple[str, str]] = {
    "batch.colgroup.product_info": (COLORS["space_indigo"], COLORS["lavender_grey"]),
    "batch.colgroup.attributes": (COLORS.get("lavender_grey", "#8D99AE"), COLORS.get("space_indigo", "#2B2D42")),
    "batch.colgroup.titles": (COLORS.get("success", "#10B981"), COLORS.get("success", "#10B981")),
}


class TieredHeaderWidget(QWidget):
    """Horizontal bar showing color-coded category spans above table columns."""

    def __init__(self, table: QTableWidget, parent=None):
        super().__init__(parent)
        self._table = table
        # (label, color_str, col_indices) — positions computed live in paintEvent
        self._spans: list[tuple[str, str, list[int]]] = []
        self.setFixedHeight(_TIER_HEIGHT)

        # Repaint on horizontal scroll so spans track column positions
        table.horizontalScrollBar().valueChanged.connect(self.update)

    def update_spans(self, visible_columns: set[str], tr=None):
        """Recalculate which category spans are active based on visible columns."""
        self._spans = []
        is_dark = isDarkTheme()

        for group_i18n, keys in COLUMN_GROUPS:
            visible_keys = [k for k in keys if k in visible_columns]
            if not visible_keys:
                continue

            col_indices = [COL[k] for k in visible_keys if k in COL]
            if not col_indices:
                continue

            label = tr(group_i18n) if tr else group_i18n
            light_c, dark_c = _CATEGORY_COLORS.get(
                group_i18n, (COLORS["space_indigo"], COLORS["lavender_grey"])
            )
            color = dark_c if is_dark else light_c

            self._spans.append((label, color, col_indices))

        self.update()

    def paintEvent(self, event):
        if not self._spans:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_dark = isDarkTheme()

        font = QFont()
        font.setPixelSize(11)
        font.setWeight(QFont.Weight.DemiBold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        painter.setFont(font)
        fm = QFontMetrics(font)

        # Account for vertical header width (0 since hidden) + frame
        offset_x = self._table.verticalHeader().width() + self._table.frameWidth()

        viewport_left = 0
        viewport_right = self._table.viewport().width()

        table = self._table
        for label, color_str, col_indices in self._spans:
            # Compute pixel positions LIVE from current column positions
            x_positions = []
            for ci in col_indices:
                if table.isColumnHidden(ci):
                    continue
                x = table.columnViewportPosition(ci)
                w = table.columnWidth(ci)
                x_positions.append((x, x + w))

            if not x_positions:
                continue

            span_left = min(p[0] for p in x_positions)
            span_right = max(p[1] for p in x_positions)

            # Apply offset and clip to visible viewport
            draw_left = span_left + offset_x
            draw_right = span_right + offset_x

            vis_left = max(draw_left, offset_x + viewport_left)
            vis_right = min(draw_right, offset_x + viewport_right)

            if vis_right <= vis_left:
                continue

            color = QColor(color_str)

            # Top color bar (2px)
            painter.fillRect(vis_left, 0, vis_right - vis_left, 2, color)

            # Background tint
            tint = QColor(color)
            tint.setAlpha(25 if not is_dark else 20)
            painter.fillRect(vis_left, 2, vis_right - vis_left, _TIER_HEIGHT - 4, tint)

            # Bottom color bar (2px)
            bottom_color = QColor(color)
            bottom_color.setAlpha(120)
            painter.fillRect(vis_left, _TIER_HEIGHT - 2, vis_right - vis_left, 2, bottom_color)

            # Label — centered in visible portion, elided if needed
            text_color = QColor(color_str)
            text_color.setAlpha(220 if not is_dark else 200)
            painter.setPen(QPen(text_color))

            available_w = vis_right - vis_left - 8  # 4px padding each side
            if available_w < 20:
                continue

            elided = fm.elidedText(label.upper(), Qt.TextElideMode.ElideRight, available_w)
            text_w = fm.horizontalAdvance(elided)
            text_x = vis_left + (vis_right - vis_left - text_w) // 2
            text_y = 2 + (_TIER_HEIGHT - 2 - fm.height()) // 2 + fm.ascent()

            painter.drawText(text_x, text_y, elided)

        painter.end()

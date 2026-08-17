"""
GUI_Qt/screens/batch_inspector.py

Right-side inspector / detail panel for the unified batch screen.
Shows all fields for the currently selected row in a vertical form layout,
with collapsible sections per category.  Two-way binding: edits in the
inspector update the table, edits in the table update the inspector.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    CheckBox,
    ComboBox,
    FluentIcon,
    GroupHeaderCardWidget,
    LineEdit,
    StrongBodyLabel,
    TransparentToolButton,
    isDarkTheme,
)

from GUI_Qt.widgets.FilterableComboBox import FilterableComboBox
from GUI_Qt.screens.batch_columns import COL, COLUMNS, COLUMN_GROUPS
from GUI_Qt.styles.theme_config import COLORS, RADII, SPACING, get_text_color


# Fields shown per section.  Key = section i18n key, value = list of column keys.
_SECTIONS = [
    ("batch.inspector.core", ["brand", "code"]),
    ("batch.inspector.product_info", ["url", "description", "frameset", "disclaimer"]),
    ("batch.inspector.attributes", [
        "attr_modelis", "attr_modelis_v", "attr_remo_tipas", "attr_remo_medz",
        "attr_ratu_dydis", "attr_pavaru_sk", "attr_stabdziu", "attr_komplekt",
        "attr_spalva",
    ]),
    ("batch.inspector.titles", ["title_lt", "title_en"]),
]


class BatchInspectorPanel(QWidget):
    """Vertical detail panel for the selected table row."""

    # Emitted when the user edits a field: (row, col_index, new_value)
    field_changed = Signal(int, int, str)
    # Emitted when prev/next buttons are clicked: delta (-1 or +1)
    navigate_row = Signal(int)
    # Emitted when close button is clicked
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_row = -1
        self._suppressing = False  # guard against feedback loops
        self._visible_columns: set[str] = set()
        self._field_widgets: dict[str, QWidget] = {}  # col_key -> inner widget
        self._group_items: dict[str, object] = {}  # col_key -> CardGroupWidget (for retranslate)
        self._build_ui()

    # ------------------------------------------------------------------ Build
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Wrapper card
        self._card = CardWidget()
        self._card.setBorderRadius(RADII["md"])
        card_lay = QVBoxLayout(self._card)
        card_lay.setContentsMargins(SPACING["base"], SPACING["md"], SPACING["base"], SPACING["base"])
        card_lay.setSpacing(SPACING["md"])

        # --- Header row: title + nav + close
        header = QHBoxLayout()
        header.setSpacing(SPACING["sm"])
        header.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._btn_prev = TransparentToolButton(FluentIcon.LEFT_ARROW)
        self._btn_prev.setFixedSize(28, 28)
        self._btn_prev.clicked.connect(lambda: self.navigate_row.emit(-1))

        self._btn_next = TransparentToolButton(FluentIcon.RIGHT_ARROW)
        self._btn_next.setFixedSize(28, 28)
        self._btn_next.clicked.connect(lambda: self.navigate_row.emit(1))

        self._title_label = StrongBodyLabel("")
        self._title_label.setStyleSheet("background: transparent;")

        self._btn_close = TransparentToolButton(FluentIcon.CLOSE)
        self._btn_close.setFixedSize(28, 28)
        self._btn_close.clicked.connect(self.close_requested.emit)

        header.addWidget(self._btn_prev)
        header.addWidget(self._btn_next)
        header.addWidget(self._title_label, 1)
        header.addWidget(self._btn_close)
        card_lay.addLayout(header)

        # --- Scroll area for sections
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        self._sections_layout = QVBoxLayout(scroll_content)
        self._sections_layout.setContentsMargins(0, 0, 0, 0)
        self._sections_layout.setSpacing(SPACING["sm"])

        # Status section (always at top, minimal)
        self._status_dot = QWidget()
        self._status_dot.setFixedSize(10, 10)
        self._status_dot.setStyleSheet(
            f"background: {get_text_color(isDarkTheme(), 'tertiary')}; border-radius: 5px;"
        )
        self._status_text = BodyLabel("")
        self._status_text.setStyleSheet("background: transparent;")
        status_row = QHBoxLayout()
        status_row.setSpacing(SPACING["xs"])
        status_row.addWidget(self._status_dot)
        status_row.addWidget(self._status_text, 1)
        self._sections_layout.addLayout(status_row)

        # Build each collapsible section
        self._section_cards: list[tuple[str, GroupHeaderCardWidget, list[str]]] = []
        for section_key, col_keys in _SECTIONS:
            group = GroupHeaderCardWidget()
            group.setTitle("")  # Set in retranslate
            group.setBorderRadius(RADII["sm"])

            for col_key in col_keys:
                cdef = COLUMNS[COL[col_key]]
                widget = self._create_field_widget(col_key, cdef.widget_factory)
                self._field_widgets[col_key] = widget

                # Use header_i18n as initial title (translated in retranslate)
                initial_title = cdef.header_i18n or col_key
                group_item = group.addGroup(
                    icon=None,
                    title=initial_title,
                    content="",
                    widget=widget,
                )
                # Hide the 20x20 icon widget since we pass no icon
                group_item.iconWidget.hide()
                self._group_items[col_key] = group_item

            self._section_cards.append((section_key, group, col_keys))
            self._sections_layout.addWidget(group)

        self._sections_layout.addStretch(1)
        scroll.setWidget(scroll_content)
        card_lay.addWidget(scroll, 1)

        root.addWidget(self._card, 1)

    _INSPECTOR_FIELD_HEIGHT = 36

    def _create_field_widget(self, col_key: str, factory: str) -> QWidget:
        """Create an inspector-side widget matching the table cell type."""
        if factory in ("brand_combo", "desc_combo", "attr_combo"):
            w = FilterableComboBox()
            w.setMinimumHeight(self._INSPECTOR_FIELD_HEIGHT)
            w.currentTextChanged.connect(
                lambda text, k=col_key: self._on_field_edited(k, text)
            )
            return w
        elif factory == "checkbox":
            w = CheckBox()
            w.stateChanged.connect(
                lambda state, k=col_key: self._on_field_edited(
                    k, "true" if state else "false"
                )
            )
            return w
        elif factory in ("line_edit", "url_edit", "code_edit"):
            w = LineEdit()
            w.setMinimumHeight(self._INSPECTOR_FIELD_HEIGHT)
            w.textChanged.connect(
                lambda text, k=col_key: self._on_field_edited(k, text)
            )
            return w
        else:
            # Fallback: read-only label (status_label, error_edit, etc.)
            lbl = BodyLabel("")
            lbl.setStyleSheet("background: transparent;")
            return lbl

    # --------------------------------------------------------- Public API

    # Core fields (brand, code) are always visible regardless of column config
    _ALWAYS_VISIBLE = {"brand", "code"}

    def set_visible_columns(self, visible: set[str]):
        """Show/hide sections based on which columns are active."""
        self._visible_columns = visible | self._ALWAYS_VISIBLE
        for section_key, group, col_keys in self._section_cards:
            any_visible = any(k in self._visible_columns for k in col_keys)
            group.setVisible(any_visible)

    def load_row(self, row: int, read_cell_fn, tr_fn):
        """Populate inspector fields from the given table row.

        *read_cell_fn(row, col_index)* returns the current string value.
        *tr_fn* is the i18n translate function.
        """
        self._current_row = row
        self._suppressing = True
        try:
            brand = read_cell_fn(row, COL["brand"])
            code = read_cell_fn(row, COL["code"])
            self._title_label.setText(f"{brand} — {code}" if (brand or code) else tr_fn("batch.inspector.no_selection"))

            # Status dot — read the dot state property from the table cell
            # (the read_cell_fn returns "" for the styled dot widget, so we skip it)

            for col_key, widget in self._field_widgets.items():
                if col_key not in self._visible_columns:
                    continue
                col_idx = COL[col_key]
                value = read_cell_fn(row, col_idx)
                self._set_widget_value(widget, value)
        finally:
            self._suppressing = False

        # Nav button state
        # (caller can update these if needed)

    def update_field(self, col_key: str, value: str):
        """Update a single inspector field (called when table cell changes)."""
        if col_key not in self._field_widgets:
            return
        self._suppressing = True
        try:
            self._set_widget_value(self._field_widgets[col_key], value)
        finally:
            self._suppressing = False

    def update_status(self, state: str = "draft", text: str = ""):
        color = {
            "draft": get_text_color(isDarkTheme(), "tertiary"),
            "incomplete": COLORS["warning"],
            "ready": COLORS["success"],
        }.get(state, get_text_color(isDarkTheme(), "tertiary"))
        self._status_dot.setStyleSheet(f"background: {color}; border-radius: 5px;")
        self._status_text.setText(text)

    def clear(self):
        """Clear all fields (no row selected)."""
        self._current_row = -1
        self._title_label.setText("")
        self._status_dot.setStyleSheet(
            f"background: {get_text_color(isDarkTheme(), 'tertiary')}; border-radius: 5px;"
        )
        self._status_text.setText("")
        self._suppressing = True
        try:
            for widget in self._field_widgets.values():
                self._set_widget_value(widget, "")
        finally:
            self._suppressing = False

    @property
    def current_row(self) -> int:
        return self._current_row

    # -------------------------------------------------------- Retranslate

    def retranslate(self, tr):
        self._btn_prev.setToolTip(tr("batch.inspector.prev"))
        self._btn_next.setToolTip(tr("batch.inspector.next"))
        self._btn_close.setToolTip(tr("batch.inspector.close"))
        if self._current_row < 0:
            self._title_label.setText(tr("batch.inspector.no_selection"))

        for section_key, group, col_keys in self._section_cards:
            group.setTitle(tr(section_key))

        # Translate individual field labels
        for col_key, group_item in self._group_items.items():
            cdef = COLUMNS[COL[col_key]]
            if cdef.header_i18n:
                translated = tr(cdef.header_i18n)
                group_item.setTitle(translated)

    # -------------------------------------------------------- Internal

    def _on_field_edited(self, col_key: str, value: str):
        if self._suppressing or self._current_row < 0:
            return
        col_idx = COL[col_key]
        self.field_changed.emit(self._current_row, col_idx, value)

    @staticmethod
    def _set_widget_value(widget, value: str):
        if isinstance(widget, FilterableComboBox):
            idx = widget.findText(value)
            if idx >= 0:
                widget.setCurrentIndex(idx)
            else:
                widget.setCurrentText(value)
        elif isinstance(widget, ComboBox):
            idx = widget.findText(value)
            if idx >= 0:
                widget.setCurrentIndex(idx)
        elif isinstance(widget, CheckBox):
            widget.setChecked(value.lower() in ("true", "1", "yes"))
        elif isinstance(widget, LineEdit):
            widget.setText(value or "")
        elif isinstance(widget, BodyLabel):
            widget.setText(value or "")

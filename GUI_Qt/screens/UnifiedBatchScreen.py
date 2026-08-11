"""GUI_Qt/screens/UnifiedBatchScreen.py

Unified batch operations screen — replaces BatchUploadScreen,
BatchDescriptionsScreen and BatchTitlesScreen with a single
customisable table whose columns adapt to the selected operation.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    CheckBox,
    ComboBox,
    FluentIcon,
    Flyout,
    FlyoutViewBase,
    IconWidget,
    IndeterminateProgressRing,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    MessageBox,
    PillPushButton,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    TitleLabel,
    TransparentPushButton,
    TransparentToolButton,
    isDarkTheme,
    qconfig,
)

from GUI_Qt.widgets.ResponsiveWidget import ResponsiveWidget
from GUI_Qt.widgets.DropZoneWidget import DropZoneWidget
from GUI_Qt.widgets.DragFillHandle import DragFillHandle
from GUI_Qt.widgets.TieredHeaderWidget import TieredHeaderWidget
from GUI_Qt.widgets.FrozenColumnTableWidget import FrozenColumnOverlay
from GUI_Qt.widgets.FilterableComboBox import FilterableComboBox
from GUI_Qt.widgets import enable_table_copy
from GUI_Qt.screens.batch_inspector import BatchInspectorPanel
from GUI_Qt.styles.theme_config import (
    COLORS,
    COMPONENT_COLORS,
    FONTS,
    PADDINGS,
    RADII,
    SIZES,
    SPACING,
)
from GUI_Qt.styles.screen_theme import (
    PAGE_MARGINS,
    PAGE_SPACING,
    ICON_TEXT_GAP,
    ROW_SPACING,
    TOOLBAR_MARGINS,
    CONTENT_SPACING,
    TABLE_CELL_MARGINS,
    apply_screen_theme,
    enforce_transparent_labels,
    get_responsive_margins,
    get_responsive_spacing,
)
from GUI_Qt.screens.batch_columns import (
    ATTR_COL_MAP,
    COL,
    COLUMN_GROUPS,
    COLUMNS,
    NUM_COLUMNS,
    PRESETS,
)
from GUI_Qt.screens.batch_strategies import STRATEGIES
from GUI_Qt.screens.UploadScreen import ATTRIBUTE_DEFINITIONS
from GUI_Qt.dialogs.AttributeOptionsDialog import (
    AttributeOptionsDialog,
    load_attribute_options,
)
from Managers.DescriptionManager import DescriptionManager
from Utilities.ExcelHandler import ExcelHandler

_SETTINGS_KEY_COLUMNS = "batch_visible_columns"

# Tuple of combo-like widget types for isinstance checks
_COMBO_TYPES = (ComboBox, FilterableComboBox)


# ---------------------------------------------------------------------------
# Cell focus filter — syncs table selection when a cell widget gets focus
# ---------------------------------------------------------------------------

class _CellFocusFilter(QWidget):
    """Event filter that sets the table's current cell when a child widget gains focus.

    Cell containers must have dynamic properties ``_ub_row`` and ``_ub_col``
    set by the screen when the row is created.
    """

    def __init__(self, table: QTableWidget, parent=None):
        super().__init__(parent)
        self._table = table

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.FocusIn:
            self._sync_cell(obj)
        return False

    def _sync_cell(self, widget):
        """Walk up from *widget* to its container to read stored row/col."""
        w = widget
        while w is not None:
            row = w.property("_ub_row")
            col = w.property("_ub_col")
            if row is not None and col is not None:
                self._table.setCurrentCell(row, col)
                return
            parent = w.parentWidget()
            if parent is self._table or parent is self._table.viewport():
                break
            w = parent


# Non-editable widget factories (skip these in tab navigation)
_NON_EDITABLE_FACTORIES = frozenset({"status_dot", "status_label", "error_edit", "delete_btn"})


class _TabNavigationFilter(QWidget):
    """Intercepts Tab / Shift+Tab to navigate between editable cells in the table.

    - Tab at last editable column → first editable column of next row.
    - Shift+Tab at first editable column → last editable column of previous row.
    - Tab on last row's last column → add a new row and move to it.
    """

    def __init__(self, table: QTableWidget, add_row_callback, parent=None):
        super().__init__(parent)
        self._table = table
        self._add_row = add_row_callback

    def eventFilter(self, obj, event):
        if event.type() != QEvent.Type.KeyPress:
            return False
        if event.key() != Qt.Key.Key_Tab and event.key() != Qt.Key.Key_Backtab:
            return False

        forward = event.key() == Qt.Key.Key_Tab
        row = self._table.currentRow()
        col = self._table.currentColumn()
        if row < 0:
            return False

        editable = self._editable_columns()
        if not editable:
            return False

        try:
            idx = editable.index(col)
        except ValueError:
            idx = 0 if forward else len(editable) - 1

        if forward:
            if idx + 1 < len(editable):
                self._focus_cell(row, editable[idx + 1])
            else:
                # Wrap to next row
                next_row = row + 1
                if next_row >= self._table.rowCount():
                    self._add_row()
                    next_row = self._table.rowCount() - 1
                self._focus_cell(next_row, editable[0])
        else:
            if idx - 1 >= 0:
                self._focus_cell(row, editable[idx - 1])
            else:
                # Wrap to previous row
                prev_row = row - 1
                if prev_row < 0:
                    return True  # Already at first cell
                self._focus_cell(prev_row, editable[-1])

        return True  # Consume the event

    def _editable_columns(self) -> list[int]:
        """Return sorted list of visible, editable column indices."""
        result = []
        for i, cdef in enumerate(COLUMNS):
            if self._table.isColumnHidden(i):
                continue
            if cdef.widget_factory in _NON_EDITABLE_FACTORIES:
                continue
            result.append(i)
        return result

    def _focus_cell(self, row: int, col: int):
        """Set table current cell and focus the inner widget."""
        self._table.setCurrentCell(row, col)
        container = self._table.cellWidget(row, col)
        if container is None:
            return
        layout = container.layout()
        if layout is not None and layout.count() > 0:
            inner = layout.itemAt(0).widget()
            if inner is not None:
                inner.setFocus()
                return
        container.setFocus()


# ---------------------------------------------------------------------------
# Column picker flyout
# ---------------------------------------------------------------------------

class _ColumnPickerView(FlyoutViewBase):
    """Flyout content showing grouped column checkboxes."""

    columns_changed = Signal(set)  # emits new visible-key set

    def __init__(self, visible: set[str], tr, parent=None):
        super().__init__(parent)
        self._visible = set(visible)
        self._tr = tr
        self._checks: dict[str, CheckBox] = {}
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(ROW_SPACING)

        title = StrongBodyLabel(self._tr("batch.colpicker.title"))
        root.addWidget(title)

        for group_i18n, keys in COLUMN_GROUPS:
            grp_label = CaptionLabel(self._tr(group_i18n))
            grp_label.setStyleSheet(f"color: {COLORS['text_secondary']}; margin-top: 4px;")
            root.addWidget(grp_label)

            row_layout = QGridLayout()
            row_layout.setSpacing(ROW_SPACING)
            for i, key in enumerate(keys):
                cdef = COLUMNS[COL[key]]
                label = self._tr(cdef.header_i18n) if "." in cdef.header_i18n else cdef.header_i18n
                cb = CheckBox(label)
                cb.setChecked(key in self._visible)
                cb.stateChanged.connect(lambda state, k=key: self._toggle(k, state))
                row_layout.addWidget(cb, i // 3, i % 3)
                self._checks[key] = cb
            root.addLayout(row_layout)

        # Preset buttons
        root.addWidget(CaptionLabel(self._tr("batch.colpicker.presets")))
        btn_row = QHBoxLayout()
        btn_row.setSpacing(ROW_SPACING)
        for preset_name in ("upload", "descriptions", "titles"):
            btn = PushButton(self._tr(f"batch.preset.{preset_name}"))
            btn.clicked.connect(lambda checked=False, p=preset_name: self._apply_preset(p))
            btn_row.addWidget(btn)
        root.addLayout(btn_row)

        self.setFixedWidth(460)

    def _toggle(self, key: str, state: int):
        if state == Qt.CheckState.Checked.value:
            self._visible.add(key)
        else:
            self._visible.discard(key)
        self.columns_changed.emit(self._visible)

    def _apply_preset(self, name: str):
        self._visible = set(PRESETS[name])
        for key, cb in self._checks.items():
            cb.blockSignals(True)
            cb.setChecked(key in self._visible)
            cb.blockSignals(False)
        self.columns_changed.emit(self._visible)


# ---------------------------------------------------------------------------
# Setup card presets
# ---------------------------------------------------------------------------

_PRESET_INFO = [
    ("upload", FluentIcon.SYNC, "batch.preset.upload", "batch.preset.upload.desc"),
    ("descriptions", FluentIcon.DOCUMENT, "batch.preset.descriptions", "batch.preset.descriptions.desc"),
    ("titles", FluentIcon.EDIT, "batch.preset.titles", "batch.preset.titles.desc"),
    ("fresh", FluentIcon.ADD, "batch.preset.fresh", "batch.preset.fresh.desc"),
]


# ---------------------------------------------------------------------------
# Main screen
# ---------------------------------------------------------------------------

class UnifiedBatchScreen(ResponsiveWidget):
    """Single batch screen for Upload, Descriptions and Titles operations."""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.worker = None
        self.session_manager = None
        self.current_input_mode = "manual"
        self._base_table_rows = 3
        self._current_processing_row = None
        self._is_busy = False
        self._pending_reviews: list[tuple[str, int, str, str, str]] = []
        self._active_review: tuple[str, int, str, str, str] | None = None
        self._show_status_cols = False
        self._visible_columns: set[str] = set()
        self._density: str = "standard"  # "compact" or "standard"
        self._earning_batch_candidates: list[dict] = []
        self._earning_batch_started_at: str | None = None

        self.brands = [
            "KROSS", "Pinarello", "Basso", "Factor",
            "TREK", "Rondo", "Octane", "Rascal", "Lee Cougan",
        ]
        desc_manager = DescriptionManager(main_window.db)
        self.descriptions = [d["name"] for d in desc_manager.list_descriptions()]

        self.scroll = None
        self.content_widget = None

        self._init_ui()
        self._setup_shortcuts()
        self._load_saved_column_config()

        qconfig.themeChangedFinished.connect(self._on_theme_changed)

    # ------------------------------------------------------------------ UI
    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.scroll = self._build_scroll_area()
        root.addWidget(self.scroll)
        self.retranslate_ui()

    def _build_scroll_area(self):
        scroll = QWidget()
        scroll_layout = QVBoxLayout(scroll)
        scroll_layout.setContentsMargins(*PAGE_MARGINS)
        scroll_layout.setSpacing(PAGE_SPACING)
        self.content_widget = scroll

        self._build_header(scroll_layout)
        self._build_toolbar(scroll_layout)
        self._build_setup_card(scroll_layout)
        self._build_table(scroll_layout)
        self._build_dropzone(scroll_layout)

        apply_screen_theme(self, "UnifiedBatchScreen", scroll=None, content=scroll)
        return scroll

    # -- Header --
    def _build_header(self, parent_layout):
        row = QHBoxLayout()
        row.setSpacing(ICON_TEXT_GAP)

        icon = IconWidget(FluentIcon.SYNC)
        icon.setFixedSize(SIZES["icon_lg"], SIZES["icon_lg"])
        self.title_label = TitleLabel("")
        self.gear_btn = TransparentToolButton(FluentIcon.SETTING, self)
        self.gear_btn.setFixedSize(SIZES["button_height_sm"], SIZES["button_height_sm"])
        self.gear_btn.setToolTip("Columns")
        self.gear_btn.clicked.connect(self._open_column_picker)

        row.addWidget(icon)
        row.addWidget(self.title_label)
        row.addStretch()
        row.addWidget(self.gear_btn)
        parent_layout.addLayout(row)

    # -- Toolbar --
    def _build_toolbar(self, parent_layout):
        card = CardWidget()
        card.setBorderRadius(RADII["md"])
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        outer = QVBoxLayout(card)
        outer.setContentsMargins(*TOOLBAR_MARGINS)
        outer.setSpacing(SPACING["sm"])

        # ---- Top row: preset + input mode + start/stop ----
        top_row = QHBoxLayout()
        top_row.setSpacing(ROW_SPACING)

        # Preset selector
        self.preset_combo = ComboBox()
        self.preset_combo.setMinimumWidth(SIZES.get("col_w_180", 180))
        self._preset_keys = ["upload", "descriptions", "titles", "fresh"]
        for key in self._preset_keys:
            self.preset_combo.addItem("", userData=key)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_combo_changed)
        top_row.addWidget(self.preset_combo)

        # Input mode pills
        self.manual_pill = PillPushButton("")
        self.manual_pill.setCheckable(True)
        self.manual_pill.setChecked(True)
        self.manual_pill.clicked.connect(lambda: self._switch_input_mode("manual"))
        self.excel_pill = PillPushButton("")
        self.excel_pill.setCheckable(True)
        self.excel_pill.clicked.connect(lambda: self._switch_input_mode("excel"))
        top_row.addWidget(self.manual_pill)
        top_row.addWidget(self.excel_pill)

        top_row.addStretch()

        # Status / progress (right side of top row)
        self.status_label = CaptionLabel("")
        self.status_label.setMaximumWidth(SIZES["col_w_260"])
        top_row.addWidget(self.status_label)

        self.elapsed_label = CaptionLabel("")
        self.elapsed_label.hide()
        top_row.addWidget(self.elapsed_label)

        self.progress_ring = IndeterminateProgressRing()
        self.progress_ring.setFixedSize(24, 24)
        self.progress_ring.hide()
        top_row.addWidget(self.progress_ring)

        # Start / retry
        self.start_btn = PrimaryPushButton("")
        self.start_btn.setEnabled(False)
        self.start_btn.setFixedHeight(SIZES["button_height_sm"])
        self.start_btn.clicked.connect(self._start_batch)
        top_row.addWidget(self.start_btn)

        self.retry_btn = PushButton("")
        self.retry_btn.setFixedHeight(SIZES["button_height_sm"])
        self.retry_btn.hide()
        self.retry_btn.clicked.connect(self._retry_failed)
        top_row.addWidget(self.retry_btn)

        self.review_saved_btn = PrimaryPushButton("Išsaugota — tęsti")
        self.review_saved_btn.setIcon(FluentIcon.ACCEPT)
        self.review_saved_btn.clicked.connect(self._confirm_review_saved)
        self.review_saved_btn.hide()
        top_row.addWidget(self.review_saved_btn)

        self.review_discard_btn = PushButton("Atmesti pakeitimus")
        self.review_discard_btn.setIcon(FluentIcon.CANCEL)
        self.review_discard_btn.clicked.connect(self._confirm_review_discard)
        self.review_discard_btn.hide()
        top_row.addWidget(self.review_discard_btn)

        outer.addLayout(top_row)

        # ---- Bottom row: table actions ----
        bot_row = QHBoxLayout()
        bot_row.setSpacing(ROW_SPACING)

        # Manual controls
        self.add_btn = TransparentToolButton(FluentIcon.ADD, self)
        self.add_btn.clicked.connect(self._add_row)
        self.clear_btn = TransparentToolButton(FluentIcon.DELETE, self)
        self.clear_btn.clicked.connect(self._clear_all)
        bot_row.addWidget(self.add_btn)
        bot_row.addWidget(self.clear_btn)

        # Disclaimer bulk toggle
        self.disclaimer_bulk = CheckBox("")
        self.disclaimer_bulk.stateChanged.connect(self._toggle_disclaimer_all)
        bot_row.addWidget(self.disclaimer_bulk)

        # Excel controls
        self.browse_btn = PushButton("")
        self.browse_btn.clicked.connect(self._browse_excel)
        self.template_btn = TransparentToolButton(FluentIcon.DOWNLOAD, self)
        self.template_btn.clicked.connect(self._download_template)
        self.excel_file_label = CaptionLabel("")
        self.excel_file_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self.excel_file_label.setMaximumWidth(SIZES["col_w_260"])

        bot_row.addWidget(self.browse_btn)
        bot_row.addWidget(self.template_btn)
        bot_row.addWidget(self.excel_file_label)

        bot_row.addStretch()

        # Export
        self.export_btn = TransparentToolButton(FluentIcon.SAVE, self)
        self.export_btn.clicked.connect(self._export_table_data)
        bot_row.addWidget(self.export_btn)

        # Density toggle
        self.density_compact_btn = TransparentToolButton(FluentIcon.MINIMIZE, self)
        self.density_compact_btn.setFixedSize(SIZES["button_height_sm"], SIZES["button_height_sm"])
        self.density_compact_btn.clicked.connect(lambda: self._set_density("compact"))
        self.density_standard_btn = TransparentToolButton(FluentIcon.ALIGNMENT, self)
        self.density_standard_btn.setFixedSize(SIZES["button_height_sm"], SIZES["button_height_sm"])
        self.density_standard_btn.clicked.connect(lambda: self._set_density("standard"))
        bot_row.addWidget(self.density_compact_btn)
        bot_row.addWidget(self.density_standard_btn)

        # Inspector toggle
        self.inspector_btn = TransparentToolButton(FluentIcon.MARKET, self)
        self.inspector_btn.setFixedSize(SIZES["button_height_sm"], SIZES["button_height_sm"])
        self.inspector_btn.clicked.connect(self._toggle_inspector)
        bot_row.addWidget(self.inspector_btn)

        outer.addLayout(bot_row)

        self.toolbar_card = card
        parent_layout.addWidget(card)

        # Initial visibility
        self._switch_input_mode("manual")
        # Density toggle: standard is default, so disable standard btn
        self.density_standard_btn.setEnabled(False)

    # -- Setup card (first-run presets) --
    def _build_setup_card(self, parent_layout):
        self.setup_card = CardWidget()
        self.setup_card.setBorderRadius(RADII["lg"])
        layout = QVBoxLayout(self.setup_card)
        layout.setSpacing(PAGE_SPACING)
        padding = SIZES["col_w_56"]
        layout.setContentsMargins(padding, padding, padding, padding)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = StrongBodyLabel("")
        self.setup_title = title
        subtitle = CaptionLabel("")
        self.setup_subtitle = subtitle
        subtitle.setStyleSheet(f"color: {COLORS['text_secondary']};")
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle, alignment=Qt.AlignmentFlag.AlignCenter)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(CONTENT_SPACING)
        self._preset_cards: dict[str, CardWidget] = {}

        for key, icon_enum, title_key, desc_key in _PRESET_INFO:
            c = CardWidget()
            c.setBorderRadius(RADII["md"])
            c.setFixedSize(220, 160)
            c.setCursor(Qt.CursorShape.PointingHandCursor)
            cl = QVBoxLayout(c)
            cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cl.setSpacing(ROW_SPACING)
            ic = IconWidget(icon_enum)
            ic.setFixedSize(SIZES["icon_lg"], SIZES["icon_lg"])
            lbl = StrongBodyLabel("")
            lbl.setProperty("_i18n_key", title_key)
            desc = CaptionLabel("")
            desc.setProperty("_i18n_key", desc_key)
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color: {COLORS['text_secondary']};")
            cl.addWidget(ic, alignment=Qt.AlignmentFlag.AlignCenter)
            cl.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignCenter)
            cl.addWidget(desc, alignment=Qt.AlignmentFlag.AlignCenter)
            c.mousePressEvent = lambda e, k=key: self._on_preset_card_clicked(k)
            cards_row.addWidget(c)
            self._preset_cards[key] = c

        layout.addLayout(cards_row)
        parent_layout.addWidget(self.setup_card, 1)
        self.setup_card.hide()  # shown only when no saved config

    # -- Table --
    def _build_table(self, parent_layout):
        # Card wrapper for visual framing
        self.table_card = CardWidget()
        self.table_card.setBorderRadius(RADII["md"])
        card_layout = QVBoxLayout(self.table_card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        self.table = QTableWidget()
        self.table.setColumnCount(NUM_COLUMNS)
        self.table.setRowCount(self._base_table_rows)

        self._update_table_theme()

        self.table.setAlternatingRowColors(True)
        # SelectItems (not SelectRows) so DragFillHandle can detect single-cell selection
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setMinimumHeight(SIZES["table_header_height"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(self._DENSITY_CONFIG[self._density]["row_height"])
        self.table.setShowGrid(False)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setCornerButtonEnabled(False)
        enable_table_copy(self.table)

        try:
            self.table.verticalScrollBar().setSingleStep(12)
            self.table.horizontalScrollBar().setSingleStep(12)
        except Exception:
            pass

        # Fixed column widths
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        for i, cdef in enumerate(COLUMNS):
            self.table.setColumnWidth(i, SIZES.get(cdef.width_key, 160))

        # Context menu on attribute headers
        self.table.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(self._on_header_context_menu)

        # Cell focus filter — must exist before _setup_table_row
        self._cell_focus_filter = _CellFocusFilter(self.table, self)

        # Tab navigation filter — intercepts Tab/Shift+Tab for cell-to-cell nav
        self._tab_filter = _TabNavigationFilter(self.table, self._add_row_silent, self)
        self.table.installEventFilter(self._tab_filter)

        # Populate initial rows
        for row in range(self._base_table_rows):
            self._setup_table_row(row)

        # Drag fill handle
        self._fill_handle = DragFillHandle(self.table)

        # Two-tier category header above the table
        self.tiered_header = TieredHeaderWidget(self.table, self.table_card)
        card_layout.addWidget(self.tiered_header)

        card_layout.addWidget(self.table, 1)

        # Frozen columns disabled — overlay approach doesn't work well with
        # editable cell widgets (covers interactive combos/edits with mirrors).
        self._frozen_cols = []

        # "Start Fresh" empty state (hidden by default)
        self.fresh_empty_state = QWidget()
        empty_layout = QVBoxLayout(self.fresh_empty_state)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(CONTENT_SPACING)
        empty_icon = IconWidget(FluentIcon.SETTING)
        empty_icon.setFixedSize(SIZES["icon_huge"], SIZES["icon_huge"])
        self._fresh_title = StrongBodyLabel("")
        self._fresh_subtitle = CaptionLabel("")
        self._fresh_subtitle.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self._fresh_btn = PushButton("")
        self._fresh_btn.setIcon(FluentIcon.SETTING)
        self._fresh_btn.clicked.connect(self._open_column_picker)
        empty_layout.addWidget(empty_icon, alignment=Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self._fresh_title, alignment=Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self._fresh_subtitle, alignment=Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self._fresh_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self.fresh_empty_state.hide()
        card_layout.addWidget(self.fresh_empty_state, 1)

        # Size policy: expand horizontally, fit content vertically
        self.table_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Inspector panel (right side, hidden by default)
        self.inspector = BatchInspectorPanel()
        self.inspector.hide()
        self.inspector.field_changed.connect(self._on_inspector_field_changed)
        self.inspector.navigate_row.connect(self._on_inspector_navigate)
        self.inspector.close_requested.connect(self._toggle_inspector)

        # Splitter: table (65%) | inspector (35%)
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.addWidget(self.table_card)
        self._splitter.addWidget(self.inspector)
        self._splitter.setSizes([650, 350])
        self._splitter.setStyleSheet("QSplitter::handle { background: transparent; width: 4px; }")

        # Double-click row to toggle inspector
        self.table.doubleClicked.connect(self._on_table_double_click)
        # Row selection updates inspector
        self.table.selectionModel().currentRowChanged.connect(self._on_current_row_changed)

        parent_layout.addWidget(self._splitter, 1)

    # -- Drop zone --
    def _build_dropzone(self, parent_layout):
        self.drop_zone = DropZoneWidget(self.main.i18n.tr, self)
        self.drop_zone.file_dropped.connect(self._handle_file_drop)
        self.drop_zone.hide()
        parent_layout.addWidget(self.drop_zone, 1)

    # ------------------------------------------------------------ Row setup
    def _wrap_widget(self, widget, row: int = -1, col: int = -1):
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setProperty("ubTableCell", True)
        container.setProperty("_ub_row", row)
        container.setProperty("_ub_col", col)
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        try:
            widget.setMinimumWidth(0)
        except Exception:
            pass
        try:
            widget.setSizePolicy(
                QSizePolicy.Policy.Expanding, widget.sizePolicy().verticalPolicy()
            )
        except Exception:
            pass
        layout = QHBoxLayout(container)
        layout.setContentsMargins(*TABLE_CELL_MARGINS)
        layout.setSpacing(0)
        layout.addWidget(widget, 1, Qt.AlignmentFlag.AlignVCenter)

        # When the inner widget gets focus, sync the table's current cell
        # so DragFillHandle sees a single selected index.
        if hasattr(self, "_cell_focus_filter"):
            widget.installEventFilter(self._cell_focus_filter)
        if hasattr(self, "_tab_filter"):
            widget.installEventFilter(self._tab_filter)

        return container

    def _wrap_checkbox(self, cb):
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(SPACING["xs"], 0, SPACING["xs"], 0)
        layout.setSpacing(0)
        layout.addWidget(cb, 0, Qt.AlignmentFlag.AlignCenter)
        if hasattr(self, "_tab_filter"):
            cb.installEventFilter(self._tab_filter)
        return container

    @property
    def _input_height(self) -> int:
        return self._DENSITY_CONFIG[self._density]["input_height"]

    def _setup_table_row(self, row: int):
        tr = self.main.i18n.tr
        ih = self._input_height

        # Row status dot (first column) — use a styled QWidget circle, not emoji
        status_dot = QWidget()
        status_dot.setFixedSize(10, 10)
        status_dot.setStyleSheet(
            "background: #ccc; border-radius: 5px;"
        )
        status_dot.setProperty("_dot_state", "draft")
        dot_container = QWidget()
        dot_container.setStyleSheet("background: transparent;")
        dl = QHBoxLayout(dot_container)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(0)
        dl.addWidget(status_dot, 0, Qt.AlignmentFlag.AlignCenter)
        self.table.setCellWidget(row, COL["row_status"], dot_container)

        # Brand
        brand_combo = FilterableComboBox()
        brand_combo.addItems(self.brands)
        brand_combo.setPlaceholderText(tr("batch.select_brand"))
        brand_combo.setMinimumHeight(ih)
        brand_combo.currentTextChanged.connect(self._on_brand_change)
        brand_combo.currentTextChanged.connect(self._validate)
        brand_combo.currentTextChanged.connect(lambda _t, r=row: self._sync_frozen_cell(r, COL["brand"]))
        brand_combo.currentTextChanged.connect(lambda t, r=row: self._on_table_cell_changed(r, "brand", t))
        self.table.setCellWidget(row, COL["brand"], self._wrap_widget(brand_combo, row, COL["brand"]))

        # Code
        code_edit = LineEdit()
        code_edit.setPlaceholderText(tr("upload.code.placeholder"))
        code_edit.setMinimumHeight(ih)
        code_edit.textChanged.connect(self._validate)
        code_edit.textChanged.connect(lambda _t, r=row: self._sync_frozen_cell(r, COL["code"]))
        code_edit.textChanged.connect(lambda t, r=row: self._on_table_cell_changed(r, "code", t))
        self.table.setCellWidget(row, COL["code"], self._wrap_widget(code_edit, row, COL["code"]))

        # URL
        url_edit = LineEdit()
        url_edit.setPlaceholderText(tr("upload.url.placeholder"))
        url_edit.setMinimumHeight(ih)
        url_edit.textChanged.connect(self._validate)
        url_edit.textChanged.connect(lambda t, r=row: self._on_table_cell_changed(r, "url", t))
        self.table.setCellWidget(row, COL["url"], self._wrap_widget(url_edit, row, COL["url"]))

        # Description
        desc_combo = FilterableComboBox()
        desc_combo.addItems(self.descriptions)
        desc_combo.setPlaceholderText(tr("batch.optional"))
        desc_combo.setMinimumHeight(ih)
        desc_combo.currentTextChanged.connect(lambda t, r=row: self._on_table_cell_changed(r, "description", t))
        self.table.setCellWidget(row, COL["description"], self._wrap_widget(desc_combo, row, COL["description"]))

        # Frameset (4)
        frameset_cb = CheckBox("")
        frameset_cb.setVisible(False)
        frameset_cb.stateChanged.connect(
            lambda st, r=row: self._on_table_cell_changed(r, "frameset", "true" if st else "false")
        )
        self.table.setCellWidget(row, COL["frameset"], self._wrap_checkbox(frameset_cb))

        # Disclaimer (5)
        disclaimer_cb = CheckBox("")
        disclaimer_cb.stateChanged.connect(
            lambda st, r=row: self._on_table_cell_changed(r, "disclaimer", "true" if st else "false")
        )
        self.table.setCellWidget(row, COL["disclaimer"], self._wrap_checkbox(disclaimer_cb))

        # Attributes
        for attr_name, col_idx in ATTR_COL_MAP.items():
            combo = FilterableComboBox()
            combo.setMinimumHeight(ih)
            combo.setPlaceholderText(attr_name)
            self._load_attr_combo_options(attr_name, combo)
            col_key = COLUMNS[col_idx].key
            combo.currentTextChanged.connect(
                lambda t, r=row, k=col_key: self._on_table_cell_changed(r, k, t)
            )
            self.table.setCellWidget(row, col_idx, self._wrap_widget(combo, row, col_idx))

        # Title LT
        title_lt = LineEdit()
        title_lt.setPlaceholderText("Pavadinimas (LT)")
        title_lt.setMinimumHeight(ih)
        title_lt.textChanged.connect(self._validate)
        title_lt.textChanged.connect(lambda t, r=row: self._on_table_cell_changed(r, "title_lt", t))
        self.table.setCellWidget(row, COL["title_lt"], self._wrap_widget(title_lt, row, COL["title_lt"]))

        # Title EN
        title_en = LineEdit()
        title_en.setPlaceholderText("Title (EN)")
        title_en.setMinimumHeight(ih)
        title_en.textChanged.connect(self._validate)
        title_en.textChanged.connect(lambda t, r=row: self._on_table_cell_changed(r, "title_en", t))
        self.table.setCellWidget(row, COL["title_en"], self._wrap_widget(title_en, row, COL["title_en"]))

        # Status
        status_lbl = BodyLabel("")
        status_lbl.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self.table.setCellWidget(row, COL["status"], self._wrap_widget(status_lbl, row, COL["status"]))

        # Error
        error_edit = LineEdit()
        error_edit.setReadOnly(True)
        error_edit.setMinimumHeight(ih)
        self.table.setCellWidget(row, COL["error"], self._wrap_widget(error_edit, row, COL["error"]))

        # Delete (19)
        del_btn = TransparentToolButton(FluentIcon.DELETE, self)
        del_btn.setFixedSize(SIZES["button_height_sm"], SIZES["button_height_sm"])
        del_btn.clicked.connect(self._remove_row)
        del_container = QWidget()
        del_container.setStyleSheet("background: transparent;")
        dl = QHBoxLayout(del_container)
        dl.setContentsMargins(SPACING["xs"], 0, SPACING["xs"], 0)
        dl.setSpacing(0)
        dl.addWidget(del_btn, 0, Qt.AlignmentFlag.AlignCenter)
        self.table.setCellWidget(row, COL["delete"], del_container)

    # --------------------------------------------------------- Widget access
    def _get_inner_widget(self, row: int, col: int):
        container = self.table.cellWidget(row, col)
        if container is None:
            return None
        layout = container.layout()
        if layout and layout.count() > 0:
            w = layout.itemAt(0).widget()
            if w is not None:
                return w
        return container

    # -------------------------------------------------------- Column config
    def _load_saved_column_config(self):
        try:
            raw = self.main.db.get_setting(_SETTINGS_KEY_COLUMNS)
            if raw:
                keys = json.loads(raw)
                self._visible_columns = set(keys)
                self._apply_column_config()
                self.setup_card.hide()
                self.toolbar_card.show()
                self.table_card.show()
                # Sync preset combo to matching preset
                for pkey, pcols in PRESETS.items():
                    if self._visible_columns == set(pcols):
                        self._sync_preset_combo(pkey)
                        break
                return
        except Exception:
            pass
        # No saved config — show setup card, hide work area
        self.setup_card.show()
        self.toolbar_card.hide()
        self.table_card.hide()

    def _save_column_config(self):
        try:
            self.main.db.save_setting(
                _SETTINGS_KEY_COLUMNS,
                json.dumps(sorted(self._visible_columns)),
            )
        except Exception:
            pass

    _STATUS_COLS = {"status", "error"}

    def _apply_column_config(self):
        for i, cdef in enumerate(COLUMNS):
            if cdef.lockable:
                # brand, code, delete — always visible
                self.table.setColumnHidden(i, False)
            elif cdef.key in self._STATUS_COLS:
                # status/error — only visible when batch has run
                self.table.setColumnHidden(i, not self._show_status_cols)
            else:
                self.table.setColumnHidden(i, cdef.key not in self._visible_columns)

        # "Start Fresh" empty state: no user-selected columns
        has_user_cols = bool(self._visible_columns)
        if hasattr(self, "fresh_empty_state"):
            self.fresh_empty_state.setVisible(not has_user_cols)
            self.table.setVisible(has_user_cols)

        self._update_header_labels()
        self._update_toolbar_visibility()
        self._save_column_config()
        self._adjust_column_sizing()
        if hasattr(self, "tiered_header"):
            self.tiered_header.update_spans(self._visible_columns, self.main.i18n.tr)
        if hasattr(self, "inspector"):
            self.inspector.set_visible_columns(self._visible_columns)
        self._validate()

    def _update_header_labels(self):
        tr = self.main.i18n.tr
        labels = []
        for cdef in COLUMNS:
            if cdef.header_i18n:
                text = tr(cdef.header_i18n) if "." in cdef.header_i18n else cdef.header_i18n
            else:
                text = ""
            labels.append(text)
        self.table.setHorizontalHeaderLabels(labels)

    def _update_toolbar_visibility(self):
        is_upload = "url" in self._visible_columns
        is_desc = "description" in self._visible_columns
        self.disclaimer_bulk.setVisible(is_upload or is_desc)

    def _adjust_column_sizing(self):
        """Stretch columns proportionally when they fit in viewport, else use fixed widths."""
        if not hasattr(self, "table"):
            return
        visible = [i for i in range(NUM_COLUMNS) if not self.table.isColumnHidden(i)]
        if not visible:
            return
        total_natural = sum(SIZES.get(COLUMNS[i].width_key, 160) for i in visible)
        viewport_w = self.table.viewport().width()
        if viewport_w <= 0:
            viewport_w = self.table.width() - 2  # fallback: table width minus border

        if total_natural < viewport_w and viewport_w > 0:
            # Stretch proportionally
            ratio = viewport_w / total_natural
            for i in visible:
                natural = SIZES.get(COLUMNS[i].width_key, 160)
                self.table.setColumnWidth(i, int(natural * ratio))
        else:
            # Scroll mode: use natural widths
            for i in visible:
                self.table.setColumnWidth(i, SIZES.get(COLUMNS[i].width_key, 160))

        # Update tiered header spans after column widths change
        if hasattr(self, "tiered_header"):
            self.tiered_header.update_spans(self._visible_columns, self.main.i18n.tr)

        # Sync frozen overlay column widths
        if hasattr(self, "_frozen_overlay"):
            self._frozen_overlay.sync_column_widths()

    # --------------------------------------------------------- Density toggle
    _DENSITY_CONFIG = {
        "compact": {"row_height": 40, "font_size": "12px", "input_height": 30},
        "standard": {"row_height": 56, "font_size": "14px", "input_height": 36},
    }

    def _set_density(self, density: str):
        if density == self._density:
            return
        self._density = density
        cfg = self._DENSITY_CONFIG[density]

        self.table.verticalHeader().setDefaultSectionSize(cfg["row_height"])

        # Update minimum heights on existing cell widgets
        for row in range(self.table.rowCount()):
            for col in range(NUM_COLUMNS):
                w = self._get_inner_widget(row, col)
                if w is not None and hasattr(w, "setMinimumHeight"):
                    try:
                        w.setMinimumHeight(cfg["input_height"])
                    except Exception:
                        pass

        # Visual feedback on toggle buttons
        self.density_compact_btn.setEnabled(density != "compact")
        self.density_standard_btn.setEnabled(density != "standard")
        self._adjust_column_sizing()
        if hasattr(self, "_frozen_overlay"):
            self._frozen_overlay.sync_density()

    # -------------------------------------------------------- Frozen columns
    def _mirror_frozen_row(self, row: int):
        """Create read-only mirror widgets in the frozen overlay for one row."""
        if not hasattr(self, "_frozen_overlay"):
            return
        ft = self._frozen_overlay.frozen
        for col in self._frozen_cols:
            cdef = COLUMNS[col]
            if cdef.widget_factory == "status_dot":
                lbl = BodyLabel("⚪")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setStyleSheet("background: transparent;")
                ft.setCellWidget(row, col, self._wrap_frozen_widget(lbl))
            elif cdef.widget_factory == "brand_combo":
                lbl = BodyLabel("")
                lbl.setStyleSheet("background: transparent;")
                ft.setCellWidget(row, col, self._wrap_frozen_widget(lbl))
            elif cdef.widget_factory == "code_edit":
                lbl = BodyLabel("")
                lbl.setStyleSheet("background: transparent;")
                ft.setCellWidget(row, col, self._wrap_frozen_widget(lbl))

    def _wrap_frozen_widget(self, widget):
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(*TABLE_CELL_MARGINS)
        layout.setSpacing(0)
        layout.addWidget(widget, 1, Qt.AlignmentFlag.AlignVCenter)
        return container

    def _sync_frozen_cell(self, row: int, col: int):
        """Copy value from main table cell to the frozen mirror."""
        if not hasattr(self, "_frozen_overlay"):
            return
        if col not in self._frozen_cols:
            return
        value = self._read_cell_value(row, col)
        ft = self._frozen_overlay.frozen
        container = ft.cellWidget(row, col)
        if container is None:
            return
        layout = container.layout()
        if layout and layout.count() > 0:
            lbl = layout.itemAt(0).widget()
            if lbl is not None and isinstance(lbl, BodyLabel):
                lbl.setText(value)

    # --------------------------------------------------------- Inspector panel
    def _toggle_inspector(self):
        """Show/hide the inspector panel."""
        vis = not self.inspector.isVisible()
        self.inspector.setVisible(vis)
        if vis:
            self.inspector.set_visible_columns(self._visible_columns)
            row = self.table.currentRow()
            if row >= 0:
                self._load_inspector_row(row)

    def _on_table_double_click(self, index):
        if not self.inspector.isVisible():
            self._toggle_inspector()

    def _on_current_row_changed(self, current, _previous):
        if self.inspector.isVisible() and current.isValid():
            self._load_inspector_row(current.row())

    def _load_inspector_row(self, row: int):
        self.inspector.load_row(row, self._read_cell_value, self.main.i18n.tr)
        # Sync status dot state
        container = self.table.cellWidget(row, COL["row_status"])
        if container and container.layout() and container.layout().count() > 0:
            dot = container.layout().itemAt(0).widget()
            if dot is not None:
                state = dot.property("_dot_state") or "draft"
                self.inspector.update_status(state)
        # Sync combo items for inspector fields
        self._sync_inspector_combos(row)

    def _read_cell_value(self, row: int, col: int) -> str:
        """Read the string value of a table cell widget."""
        w = self._get_inner_widget(row, col)
        if w is None:
            return ""
        if isinstance(w, _COMBO_TYPES):
            return w.currentText()
        if isinstance(w, CheckBox):
            return "true" if w.isChecked() else "false"
        if isinstance(w, LineEdit):
            return w.text()
        if isinstance(w, BodyLabel):
            return w.text()
        return ""

    def _sync_inspector_combos(self, row: int):
        """Copy combo items from table cells to inspector combo fields."""
        for col_key, widget in self.inspector._field_widgets.items():
            if not isinstance(widget, (FilterableComboBox, ComboBox)):
                continue
            col_idx = COL[col_key]
            table_w = self._get_inner_widget(row, col_idx)
            if table_w is None or not isinstance(table_w, _COMBO_TYPES):
                continue
            # Copy items
            items = []
            if isinstance(table_w, FilterableComboBox):
                items = table_w._items[:]
            elif isinstance(table_w, ComboBox):
                items = [table_w.itemText(i) for i in range(table_w.count())]
            widget.clear()
            widget.addItems(items)
            # Set current value
            current = table_w.currentText()
            idx = widget.findText(current)
            if idx >= 0:
                widget.setCurrentIndex(idx)

    def _on_inspector_field_changed(self, row: int, col: int, value: str):
        """Inspector field changed — update the table cell."""
        w = self._get_inner_widget(row, col)
        if w is None:
            return
        if isinstance(w, _COMBO_TYPES):
            idx = w.findText(value)
            if idx >= 0:
                if isinstance(w, FilterableComboBox):
                    w.setCurrentIndex(idx)
                else:
                    w.setCurrentIndex(idx)
        elif isinstance(w, CheckBox):
            w.setChecked(value.lower() in ("true", "1", "yes"))
        elif isinstance(w, LineEdit):
            w.setText(value)

    def _on_table_cell_changed(self, row: int, col_key: str, value: str):
        """A table cell value changed — push the new value to the inspector."""
        if hasattr(self, "inspector") and self.inspector.isVisible():
            if self.inspector.current_row == row:
                self.inspector.update_field(col_key, value)

    def _on_inspector_navigate(self, delta: int):
        """Prev/Next in inspector."""
        row = self.inspector.current_row + delta
        if 0 <= row < self.table.rowCount():
            self.table.setCurrentCell(row, self.table.currentColumn())
            self._load_inspector_row(row)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "table"):
            self._adjust_column_sizing()
        if hasattr(self, "_frozen_overlay"):
            self._frozen_overlay.reposition()

    # ------------------------------------------------------------ Presets
    def _on_preset_card_clicked(self, key: str):
        if key == "fresh":
            self._visible_columns = set()
        else:
            self._visible_columns = set(PRESETS[key])
        self._apply_column_config()
        self.setup_card.hide()
        self.toolbar_card.show()
        self.table_card.show()
        # Sync combo without triggering change handler
        self._sync_preset_combo(key)

    def _sync_preset_combo(self, key: str):
        """Update the preset combo to reflect current selection without triggering switch."""
        try:
            idx = self._preset_keys.index(key)
            self.preset_combo.blockSignals(True)
            self.preset_combo.setCurrentIndex(idx)
            self.preset_combo.blockSignals(False)
        except ValueError:
            pass

    def _on_preset_combo_changed(self, index: int):
        """User picked a different preset from the toolbar combo."""
        if index < 0 or index >= len(self._preset_keys):
            return
        key = self._preset_keys[index]
        if key == "fresh":
            new_cols = set()
        else:
            new_cols = set(PRESETS.get(key, set()))
        # Use import-aware switching if there's data
        if self._has_data_in_table():
            self._apply_preset_with_import(key)
        else:
            self._visible_columns = new_cols
            self._apply_column_config()

    def _apply_preset_with_import(self, preset_name: str):
        """Switch to a preset, optionally importing compatible data."""
        new_cols = set(PRESETS.get(preset_name, set()))

        if self._has_data_in_table():
            dlg = MessageBox(
                self.main.i18n.tr("batch.switch.title"),
                self.main.i18n.tr("batch.switch.body"),
                self,
            )
            if dlg.exec():
                # Import compatible data (brand + code + shared columns)
                self._switch_columns_preserve(new_cols)
            else:
                self._visible_columns = new_cols
                self._clear_table_data()
                self._apply_column_config()
        else:
            self._visible_columns = new_cols
            self._apply_column_config()

    def _switch_columns_preserve(self, new_cols: set[str]):
        """Change visible columns while keeping Brand, Code and shared column data."""
        old_cols = set(self._visible_columns)
        shared = old_cols & new_cols  # columns present in both configs

        # Read current data
        saved_rows = []
        for row in range(self.table.rowCount()):
            row_data = {}
            brand_w = self._get_inner_widget(row, COL["brand"])
            code_w = self._get_inner_widget(row, COL["code"])
            if brand_w and isinstance(brand_w, _COMBO_TYPES):
                row_data["brand"] = brand_w.currentText()
            if code_w and isinstance(code_w, LineEdit):
                row_data["code"] = code_w.text()

            for key in shared:
                col_idx = COL[key]
                w = self._get_inner_widget(row, col_idx)
                if w is None:
                    continue
                if isinstance(w, _COMBO_TYPES):
                    row_data[key] = w.currentText()
                elif isinstance(w, LineEdit):
                    row_data[key] = w.text()
                elif isinstance(w, CheckBox):
                    row_data[key] = w.isChecked()
            saved_rows.append(row_data)

        # Apply new columns
        self._visible_columns = new_cols
        self._apply_column_config()

        # Restore data
        while self.table.rowCount() < len(saved_rows):
            self._add_row_silent()
        for row, data in enumerate(saved_rows):
            brand_w = self._get_inner_widget(row, COL["brand"])
            if brand_w and isinstance(brand_w, _COMBO_TYPES) and data.get("brand"):
                idx = brand_w.findText(data["brand"])
                if idx >= 0:
                    brand_w.setCurrentIndex(idx)
            code_w = self._get_inner_widget(row, COL["code"])
            if code_w and isinstance(code_w, LineEdit):
                code_w.setText(data.get("code", ""))

            for key in shared:
                col_idx = COL[key]
                w = self._get_inner_widget(row, col_idx)
                val = data.get(key)
                if w is None or val is None:
                    continue
                if isinstance(w, _COMBO_TYPES) and isinstance(val, str):
                    idx = w.findText(val)
                    if idx >= 0:
                        w.setCurrentIndex(idx)
                elif isinstance(w, LineEdit) and isinstance(val, str):
                    w.setText(val)
                elif isinstance(w, CheckBox) and isinstance(val, bool):
                    w.setChecked(val)

    # ------------------------------------------------------- Column picker
    def _open_column_picker(self):
        view = _ColumnPickerView(self._visible_columns, self.main.i18n.tr, self)

        def _on_cols_changed(new_set):
            if self._has_data_in_table():
                self._switch_columns_preserve(new_set)
            else:
                self._visible_columns = new_set
                self._apply_column_config()

        view.columns_changed.connect(_on_cols_changed)
        Flyout.make(view, self.gear_btn, self)

    # ------------------------------------------------------ Strategy inference
    def _infer_strategy(self):
        if "url" in self._visible_columns:
            return STRATEGIES["upload"]
        if "title_lt" in self._visible_columns or "title_en" in self._visible_columns:
            return STRATEGIES["titles"]
        return STRATEGIES["descriptions"]

    # ----------------------------------------------------------- Validation
    def _validate(self):
        strategy = self._infer_strategy()
        count = 0
        for row in range(self.table.rowCount()):
            row_valid = strategy.validate_row(self, row)
            if row_valid:
                count += 1
            self._update_row_status(row, strategy, row_valid)
        self.start_btn.setEnabled(count > 0 and not self._is_busy)

    _DOT_COLORS = {
        "draft": "#ccc",
        "incomplete": "#f0ad4e",
        "ready": "#5cb85c",
    }

    def _update_row_status(self, row: int, strategy=None, row_valid: bool | None = None):
        """Update the status dot for a row: grey=Draft, yellow=Incomplete, green=Ready."""
        container = self.table.cellWidget(row, COL["row_status"])
        if container is None:
            return
        layout = container.layout()
        if layout is None or layout.count() == 0:
            return
        dot_widget = layout.itemAt(0).widget()
        if dot_widget is None:
            return

        brand_w = self._get_inner_widget(row, COL["brand"])
        code_w = self._get_inner_widget(row, COL["code"])
        has_brand = brand_w and isinstance(brand_w, _COMBO_TYPES) and brand_w.currentText()
        has_code = code_w and isinstance(code_w, LineEdit) and code_w.text().strip()

        if not has_brand and not has_code:
            state = "draft"
        elif row_valid if row_valid is not None else (strategy and strategy.validate_row(self, row)):
            state = "ready"
        else:
            state = "incomplete"

        color = self._DOT_COLORS[state]
        dot_widget.setStyleSheet(f"background: {color}; border-radius: 5px;")
        dot_widget.setProperty("_dot_state", state)

    def _has_data_in_table(self) -> bool:
        if not hasattr(self, "table"):
            return False
        for row in range(self.table.rowCount()):
            brand_w = self._get_inner_widget(row, COL["brand"])
            code_w = self._get_inner_widget(row, COL["code"])
            if brand_w and isinstance(brand_w, _COMBO_TYPES) and brand_w.currentText():
                return True
            if code_w and isinstance(code_w, LineEdit) and code_w.text().strip():
                return True
        return False

    # ------------------------------------------------------ Table operations
    def _add_row(self):
        row = self.table.rowCount()
        self.table.setRowCount(row + 1)
        self._setup_table_row(row)
        if hasattr(self, "_frozen_overlay"):
            self._frozen_overlay.sync_row_count()
            self._mirror_frozen_row(row)

    def _add_row_silent(self):
        """Add a row without triggering validation."""
        row = self.table.rowCount()
        self.table.setRowCount(row + 1)
        self._setup_table_row(row)
        if hasattr(self, "_frozen_overlay"):
            self._frozen_overlay.sync_row_count()
            self._mirror_frozen_row(row)

    def _remove_row(self):
        btn = self.sender()
        if btn is None:
            return
        for row in range(self.table.rowCount()):
            container = self.table.cellWidget(row, COL["delete"])
            if container is None:
                continue
            layout = container.layout()
            if layout and layout.count() > 0:
                if layout.itemAt(0).widget() is btn:
                    if self.table.rowCount() <= 1:
                        return
                    self.table.removeRow(row)
                    if hasattr(self, "_frozen_overlay"):
                        self._frozen_overlay.frozen.removeRow(row)
                    self._validate()
                    return

    def _clear_all(self):
        if not self._has_data_in_table():
            return
        dlg = MessageBox(
            self.main.i18n.tr("batch.clear.title"),
            self.main.i18n.tr("batch.clear.body"),
            self,
        )
        if dlg.exec():
            self._clear_table_data()

    def _clear_table_data(self):
        self.table.setRowCount(0)
        self.table.setRowCount(self._base_table_rows)
        for row in range(self._base_table_rows):
            self._setup_table_row(row)
        if hasattr(self, "_frozen_overlay"):
            self._frozen_overlay.sync_row_count()
            for row in range(self._base_table_rows):
                self._mirror_frozen_row(row)
        self._show_status_cols = False
        self._apply_column_config()
        self._validate()

    def _on_brand_change(self, text: str):
        """Show/hide frameset checkbox based on brand."""
        sender = self.sender()
        if sender is None:
            return
        for row in range(self.table.rowCount()):
            brand_w = self._get_inner_widget(row, COL["brand"])
            if brand_w is sender:
                fs_w = self._get_inner_widget(row, COL["frameset"])
                if fs_w and isinstance(fs_w, CheckBox):
                    fs_w.setVisible(text == "Pinarello")
                break

    def _toggle_disclaimer_all(self, state):
        checked = state == Qt.CheckState.Checked.value
        for row in range(self.table.rowCount()):
            w = self._get_inner_widget(row, COL["disclaimer"])
            if w and isinstance(w, CheckBox):
                w.setChecked(checked)

    # -------------------------------------------------- Viewport auto-fill
    # ----------------------------------------------- Attribute combo helpers
    def _load_attr_combo_options(self, attr_name: str, combo):
        combo.clear()
        combo.addItem("")
        try:
            options = load_attribute_options(self.main.settings, attr_name)
            for opt in options:
                combo.addItem(opt)
        except Exception:
            pass

    def _on_header_context_menu(self, pos):
        col = self.table.horizontalHeader().logicalIndexAt(pos)
        if col < 0 or col >= len(COLUMNS):
            return
        cdef = COLUMNS[col]
        if cdef.widget_factory != "attr_combo" or cdef.attr_name is None:
            return

        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        action = menu.addAction(self.main.i18n.tr("upload.attr.edit_options"))
        action.triggered.connect(lambda: self._manage_attr_options(cdef.attr_name, col))
        menu.exec(self.table.horizontalHeader().mapToGlobal(pos))

    def _manage_attr_options(self, attr_name: str, col: int):
        current = load_attribute_options(self.main.settings, attr_name)
        dlg = AttributeOptionsDialog(attr_name, current, self.main.i18n.tr, self)
        if dlg.exec():
            # Refresh all combos in this column
            for row in range(self.table.rowCount()):
                combo = self._get_inner_widget(row, col)
                if combo and isinstance(combo, _COMBO_TYPES):
                    current = combo.currentText()
                    self._load_attr_combo_options(attr_name, combo)
                    idx = combo.findText(current)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)

    # ---------------------------------------------------------- Code helper
    @staticmethod
    def _normalize_code(raw: str) -> str:
        code = (raw or "").strip()
        if not code:
            return ""
        if code.upper().startswith("UB-"):
            return code
        return f"UB-{code}"

    # -------------------------------------------------- Input mode switching
    def _switch_input_mode(self, mode: str):
        self.current_input_mode = mode
        is_manual = mode == "manual"
        is_excel = mode == "excel"

        self.manual_pill.setChecked(is_manual)
        self.excel_pill.setChecked(is_excel)

        self.add_btn.setVisible(is_manual)
        self.clear_btn.setVisible(is_manual)
        self.export_btn.setVisible(is_manual)

        self.browse_btn.setVisible(is_excel)
        self.template_btn.setVisible(is_excel)
        self.excel_file_label.setVisible(is_excel)

        has_data = self._has_data_in_table()
        if hasattr(self, "table") and hasattr(self, "drop_zone"):
            if is_excel and not has_data:
                self.table_card.hide()
                self.drop_zone.show()
            else:
                self.table_card.show()
                self.drop_zone.hide()

    # ----------------------------------------------------------- Excel I/O
    def _handle_file_drop(self, path: str):
        if path == "__browse__":
            self._browse_excel()
        else:
            self._load_excel(path)

    def _browse_excel(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            self.main.i18n.tr("batch.file.select_excel.title"),
            "",
            self.main.i18n.tr("batch.file.select_excel.filter"),
        )
        if filename:
            self._load_excel(filename)

    def _load_excel(self, filename: str):
        tr = self.main.i18n.tr
        strategy = self._infer_strategy()
        try:
            wb = openpyxl.load_workbook(filename, read_only=True)
            ws = wb.active

            # Find header row
            header_row = None
            for row_idx, row_data in enumerate(ws.iter_rows(max_row=10, values_only=True), start=1):
                if row_data and any(
                    str(c).strip().lower() == "brand"
                    for c in row_data
                    if c is not None
                ):
                    header_row = row_idx
                    break

            if header_row is None:
                raise Exception(tr("batch.excel.header_missing_in_file"))

            data_rows = []
            for row_data in ws.iter_rows(min_row=header_row + 1, values_only=True):
                if any(c is not None and str(c).strip() for c in row_data):
                    data_rows.append(row_data)

            wb.close()

            if not data_rows:
                raise Exception(tr("batch.excel.no_data"))

            self.table.setRowCount(len(data_rows))
            for table_row, excel_row in enumerate(data_rows):
                self._setup_table_row(table_row)
                parsed = strategy.parse_excel_row(excel_row, tr)
                self._populate_row_from_dict(table_row, parsed)

            self.excel_file_label.setText(os.path.basename(filename))
            self.excel_file_label.setToolTip(filename)
            self.table_card.show()
            self.drop_zone.hide()
            self._validate()

            InfoBar.success(
                title=tr("common.success"),
                content=tr("batch.excel.loaded", count=len(data_rows)),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
        except Exception as ex:
            InfoBar.error(
                title=tr("common.error"),
                content=str(ex),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )

    def _populate_row_from_dict(self, row: int, data: dict):
        """Fill row widgets from a parsed Excel dict."""
        brand = data.get("brand", "")
        brand_w = self._get_inner_widget(row, COL["brand"])
        if brand_w and isinstance(brand_w, _COMBO_TYPES) and brand:
            idx = brand_w.findText(brand)
            if idx >= 0:
                brand_w.setCurrentIndex(idx)

        code = data.get("code", "")
        code_w = self._get_inner_widget(row, COL["code"])
        if code_w and isinstance(code_w, LineEdit):
            code_w.setText(code)

        url = data.get("url", "")
        url_w = self._get_inner_widget(row, COL["url"])
        if url_w and isinstance(url_w, LineEdit) and url:
            url_w.setText(url)

        desc = data.get("description", "")
        desc_w = self._get_inner_widget(row, COL["description"])
        if desc_w and isinstance(desc_w, _COMBO_TYPES) and desc:
            idx = desc_w.findText(desc)
            if idx >= 0:
                desc_w.setCurrentIndex(idx)

        fs = data.get("frameset", False)
        fs_w = self._get_inner_widget(row, COL["frameset"])
        if fs_w and isinstance(fs_w, CheckBox):
            fs_w.setChecked(bool(fs))

        disc = data.get("disclaimer", False)
        disc_w = self._get_inner_widget(row, COL["disclaimer"])
        if disc_w and isinstance(disc_w, CheckBox):
            disc_w.setChecked(bool(disc))

        # Attributes
        for defn in ATTRIBUTE_DEFINITIONS:
            val = data.get(f"attr_{defn['name']}", "")
            if not val:
                continue
            col_idx = ATTR_COL_MAP.get(defn["name"])
            if col_idx is None:
                continue
            combo = self._get_inner_widget(row, col_idx)
            if combo and isinstance(combo, _COMBO_TYPES):
                idx = combo.findText(val)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

        # Titles
        for key in ("title_lt", "title_en"):
            val = data.get(key, "")
            if not val:
                continue
            w = self._get_inner_widget(row, COL[key])
            if w and isinstance(w, LineEdit):
                w.setText(val)

    def _download_template(self):
        tr = self.main.i18n.tr
        strategy = self._infer_strategy()
        headers = strategy.get_template_headers(tr)
        example = strategy.get_template_example(tr)

        default_name = f"batch_template_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filename, _ = QFileDialog.getSaveFileName(
            self, tr("batch.template.save_title"), default_name, "Excel (*.xlsx)"
        )
        if not filename:
            return

        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Template"

            # Header styling
            for col_idx, h in enumerate(headers, start=1):
                cell = ws.cell(row=1, column=col_idx, value=h)
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill(start_color="2B2D42", end_color="2B2D42", fill_type="solid")
                cell.alignment = Alignment(horizontal="center")

            # Example row
            for col_idx, val in enumerate(example, start=1):
                ws.cell(row=2, column=col_idx, value=val)

            # Auto-width
            for col_idx in range(1, len(headers) + 1):
                ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = 20

            wb.save(filename)
            InfoBar.success(
                title=tr("common.success"),
                content=tr("batch.template.saved"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
        except Exception as ex:
            InfoBar.error(
                title=tr("common.error"),
                content=str(ex),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )

    def _export_table_data(self):
        tr = self.main.i18n.tr
        strategy = self._infer_strategy()
        headers = strategy.get_template_headers(tr) + [tr("batch.table.status"), tr("batch.table.error")]

        rows_data = []
        for row in range(self.table.rowCount()):
            brand_w = self._get_inner_widget(row, COL["brand"])
            if not brand_w or not isinstance(brand_w, _COMBO_TYPES) or not brand_w.currentText():
                continue
            row_vals = []
            # Use strategy headers to determine which columns to export
            # Simpler: export all non-hidden, non-locked columns + status + error
            for i, cdef in enumerate(COLUMNS):
                if self.table.isColumnHidden(i) and not cdef.lockable:
                    continue
                if cdef.key in ("delete",):
                    continue
                w = self._get_inner_widget(row, i)
                if w is None:
                    row_vals.append("")
                elif isinstance(w, _COMBO_TYPES):
                    row_vals.append(w.currentText())
                elif isinstance(w, LineEdit):
                    row_vals.append(w.text())
                elif isinstance(w, CheckBox):
                    row_vals.append("Yes" if w.isChecked() else "No")
                elif isinstance(w, BodyLabel):
                    row_vals.append(w.text())
                else:
                    row_vals.append("")
            rows_data.append(row_vals)

        if not rows_data:
            return

        default_name = f"batch_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filename, _ = QFileDialog.getSaveFileName(
            self, tr("batch.export.title"), default_name, "Excel (*.xlsx)"
        )
        if filename:
            try:
                # Build actual headers from visible columns
                vis_headers = []
                for i, cdef in enumerate(COLUMNS):
                    if self.table.isColumnHidden(i) and not cdef.lockable:
                        continue
                    if cdef.key == "delete":
                        continue
                    text = tr(cdef.header_i18n) if "." in cdef.header_i18n else cdef.header_i18n
                    vis_headers.append(text or cdef.key)
                ExcelHandler.export_table_data(vis_headers, rows_data, filename, "Batch Data")
                InfoBar.success(
                    title=tr("common.success"),
                    content=tr("batch.export.saved"),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )
            except Exception as ex:
                InfoBar.error(
                    title=tr("common.error"),
                    content=str(ex),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=5000,
                    parent=self,
                )

    # --------------------------------------------------- Batch start / stop
    def _start_batch(self):
        # Show status/error columns for batch progress
        self._show_status_cols = True
        self._apply_column_config()

        strategy = self._infer_strategy()

        # Collect valid rows
        valid_rows = []
        for row in range(self.table.rowCount()):
            if strategy.validate_row(self, row):
                valid_rows.append(row)
        if not valid_rows:
            return

        items = strategy.collect_items(self, valid_rows)
        if not items:
            return

        if isinstance(strategy, type(STRATEGIES["upload"])):
            self._earning_batch_started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._earning_batch_candidates = [
                {**item, "table_row": table_row}
                for item, table_row in zip(items, valid_rows)
            ]
        else:
            self._earning_batch_candidates = []
            self._earning_batch_started_at = None

        # Master password check for upload mode with external brands
        if isinstance(strategy, type(STRATEGIES["upload"])):
            master_password = getattr(self.main, "_unlocked_master_password", None)
            for it in items:
                brand = it.get("brand", "")
                if brand == "Basso":
                    if not self.main.credential_manager.has_external_credentials("basso"):
                        InfoBar.error(
                            title=self.main.i18n.tr("common.error"),
                            content=self.main.i18n.tr("account.brand_missing", brand="Basso"),
                            orient=Qt.Orientation.Horizontal,
                            isClosable=True,
                            position=InfoBarPosition.TOP,
                            duration=5000,
                            parent=self,
                        )
                        return
                if brand == "Lee Cougan":
                    if not self.main.credential_manager.has_external_credentials("leecougan"):
                        InfoBar.error(
                            title=self.main.i18n.tr("common.error"),
                            content=self.main.i18n.tr("account.brand_missing", brand="Lee Cougan"),
                            orient=Qt.Orientation.Horizontal,
                            isClosable=True,
                            position=InfoBarPosition.TOP,
                            duration=5000,
                            parent=self,
                        )
                        return

        # Reset status for valid rows
        for row in valid_rows:
            status_w = self._get_inner_widget(row, COL["status"])
            if status_w and isinstance(status_w, BodyLabel):
                status_w.setText("Pending")
                status_w.setStyleSheet(f"color: {COLORS['text_secondary']};")
            error_w = self._get_inner_widget(row, COL["error"])
            if error_w and isinstance(error_w, LineEdit):
                error_w.setText("")

        # Multi-session detection
        multi_session = self.main.settings.get("multi_session_enabled", False)
        session_mgr = None
        if multi_session:
            if self.session_manager is None or not self.session_manager.is_ready():
                try:
                    from Config.LoginConfig.LoginHandler import LoginHandler
                    from Config.Selectors import LoginSelectors
                    from Managers.BrowserSessionManager import BrowserSessionManager
                    browser_count = self.main.settings.get("browser_count", 2)
                    browser_type = self.main.settings.get("browser_choice", "chrome")
                    self.session_manager = BrowserSessionManager(
                        browser_type, browser_count, self.main.logger
                    )
                    email, password = self.main.credential_manager.get_saved_credentials()

                    def initialize_session(driver):
                        if not email or not password:
                            return False
                        driver.get(LoginSelectors.URL)
                        handler = LoginHandler(
                            driver,
                            self.main.credential_manager,
                            logger=self.main.logger,
                        )
                        return handler.attempt_login(email, password)

                    self.session_manager.set_session_initializer(initialize_session)
                    if not self.session_manager.initialize_pool():
                        self.session_manager = None
                except Exception:
                    self.session_manager = None
            session_mgr = self.session_manager if self.session_manager and self.session_manager.is_ready() else None

        # Create worker
        self.worker = strategy.create_worker(
            self, items, valid_rows,
            multi_session=bool(session_mgr),
            session_manager=session_mgr,
        )

        # Connect signals
        self.worker.row_update.connect(self._on_row_update)
        self.worker.done.connect(self._on_done)
        if hasattr(self.worker, "progress_update"):
            self.worker.progress_update.connect(self._on_progress_update)
        if hasattr(self.worker, "log"):
            self.worker.log.connect(self._on_log)
        if hasattr(self.worker, "session_status"):
            self.worker.session_status.connect(self._on_session_status)
        if hasattr(self.worker, "review_required"):
            self.worker.review_required.connect(self._on_review_required)

        self._set_busy(True)
        self.worker.start()

    def _on_review_required(
        self,
        token: str,
        row: int,
        code: str,
        url: str,
        mode: str,
    ):
        request = (token, row, code, url, mode)
        if token not in {item[0] for item in self._pending_reviews} and (
            self._active_review is None or self._active_review[0] != token
        ):
            self._pending_reviews.append(request)
        self._show_next_review()

    def _show_next_review(self):
        if self._active_review is None and self._pending_reviews:
            self._active_review = self._pending_reviews.pop(0)
        active = self._active_review
        visible = active is not None
        self.review_saved_btn.setVisible(
            visible and active is not None and active[4] == "review"
        )
        self.review_discard_btn.setVisible(visible)
        if active:
            _token, row, code, _url, mode = active
            if mode == "discard_only":
                self.status_label.setText(
                    f"{code}: paruošimas nepavyko. Patvirtinkite pakeitimų atmetimą."
                )
                self._on_row_update(
                    row,
                    "Nepavyko — laukiama atmetimo",
                    "PIMBO forma nebus uždaroma be jūsų patvirtinimo",
                )
            else:
                self.status_label.setText(
                    f"{code}: paruošta peržiūrai. PIMBO lange spauskite Save."
                )
                self._on_row_update(row, "Paruošta peržiūrai", "Laukiama rankinio Save")

    def _send_review_action(self, action: str):
        if self._active_review is None or self.worker is None:
            return
        token, _row, _code, _url, _mode = self._active_review
        self._active_review = None
        self.review_saved_btn.hide()
        self.review_discard_btn.hide()
        self.worker.review_response.emit(token, action)
        self._show_next_review()

    def _confirm_review_saved(self):
        if self._active_review is None or self._active_review[4] != "review":
            return
        self._send_review_action("saved")

    def _confirm_review_discard(self):
        if self._active_review is None:
            return
        _token, _row, code, _url, _mode = self._active_review
        dialog = MessageBox(
            "Atmesti neišsaugotus pakeitimus?",
            f"{code} forma bus perkrauta, o neišsaugoti pakeitimai bus prarasti.",
            self,
        )
        dialog.yesButton.setText("Atmesti ir tęsti")
        dialog.cancelButton.setText("Grįžti į peržiūrą")
        if dialog.exec():
            self._send_review_action("discard")

    def _set_busy(self, busy: bool):
        self._is_busy = busy
        self.start_btn.setEnabled(not busy)
        self.add_btn.setEnabled(not busy)
        self.clear_btn.setEnabled(not busy)
        self.retry_btn.hide()

        if busy:
            self.progress_ring.show()
            self.progress_ring.start()
            self._start_time = time.time()
            self._elapsed_timer = QTimer(self)
            self._elapsed_timer.timeout.connect(self._update_elapsed)
            self._elapsed_timer.start(1000)
            self.elapsed_label.show()
            self._update_elapsed()
        else:
            self.progress_ring.stop()
            self.progress_ring.hide()
            if hasattr(self, "_elapsed_timer"):
                self._elapsed_timer.stop()
            self.elapsed_label.hide()
            if not self._pending_reviews and self._active_review is None:
                self.review_saved_btn.hide()
                self.review_discard_btn.hide()

    def _update_elapsed(self):
        if not hasattr(self, "_start_time"):
            return
        elapsed = int(time.time() - self._start_time)
        mins, secs = divmod(elapsed, 60)
        self.elapsed_label.setText(f"Elapsed: {mins:02d}:{secs:02d}")

    def _on_row_update(self, row: int, status_text: str, error_text: str):
        # Clear previous processing highlight
        if self._current_processing_row is not None and self._current_processing_row != row:
            self._set_row_bg(self._current_processing_row, QColor(0, 0, 0, 0))

        # Determine color
        if "Processing" in status_text:
            bg = QColor(255, 182, 193, 100)
            self._current_processing_row = row
        elif "Paruošta peržiūrai" in status_text:
            bg = QColor(255, 215, 0, 90)
            self._current_processing_row = row
        elif "Išsaugota rankiniu" in status_text:
            bg = QColor(144, 238, 144, 120)
        elif "Atmesta" in status_text or "Ne Draft" in status_text:
            bg = QColor(211, 211, 211, 100)
        elif "Success" in status_text or "✓" in status_text or "ok" in status_text.lower():
            bg = QColor(144, 238, 144, 120)
        elif "Failed" in status_text or "Nepavyko" in status_text or "✗" in status_text:
            bg = QColor(255, 99, 71, 100)
        else:
            bg = QColor(0, 0, 0, 0)

        self._set_row_bg(row, bg)

        # Update status
        status_w = self._get_inner_widget(row, COL["status"])
        if status_w and isinstance(status_w, BodyLabel):
            status_w.setText(status_text)

        # Update error
        error_w = self._get_inner_widget(row, COL["error"])
        if error_w and isinstance(error_w, LineEdit):
            error_w.setText(error_text)

    def _set_row_bg(self, row: int, color: QColor):
        for col in range(NUM_COLUMNS):
            item = self.table.item(row, col)
            if item is None:
                item = QTableWidgetItem()
                self.table.setItem(row, col, item)
            item.setBackground(color)

    def _on_done(self, ok: int, total: int):
        self._set_busy(False)
        self._current_processing_row = None
        tr = self.main.i18n.tr

        failed = total - ok
        if failed > 0:
            self.retry_btn.show()
            InfoBar.warning(
                title=tr("batch.done.title"),
                content=tr("batch.done.partial", ok=ok, total=total, failed=failed),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )
        else:
            InfoBar.success(
                title=tr("batch.done.title"),
                content=tr("batch.done.success", ok=ok, total=total),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )
        self._validate()
        if self._earning_batch_candidates:
            QTimer.singleShot(0, self._prompt_completed_batch_earnings)

    def _prompt_completed_batch_earnings(self):
        """Offer one review list containing only products verified as saved."""
        candidates = self._earning_batch_candidates
        started_at = self._earning_batch_started_at
        self._earning_batch_candidates = []
        self._earning_batch_started_at = None
        if not candidates or not started_at:
            return
        saved_items = []
        for candidate in candidates:
            row = self.main.db.conn.execute(
                """
                SELECT id FROM processing_history
                WHERE brand=? AND product_code=? AND status='saved_manually'
                  AND processed_at>=?
                ORDER BY id DESC LIMIT 1
                """,
                (candidate.get("brand", ""), candidate.get("code", ""), started_at),
            ).fetchone()
            if row is None:
                continue
            saved_items.append({
                "sku": candidate.get("code", ""),
                "brand": candidate.get("brand", ""),
                "product_type": "frameset" if candidate.get("frameset_only") else "bicycle",
                "source": "batch_upload",
                "processing_history_id": int(row["id"]),
            })
        if saved_items:
            self.main.prompt_earning_items(saved_items, parent=self)

    def _on_progress_update(self, current, total, speed, eta_seconds):
        mins, secs = divmod(int(eta_seconds), 60)
        self.status_label.setText(f"{current}/{total} • ETA {mins:02d}:{secs:02d}")

    def _on_log(self, *args):
        msg = " ".join(str(a) for a in args)
        if hasattr(self.main, "logger"):
            self.main.logger.log("Batch", msg)

    def _on_session_status(self, stats: dict):
        busy = stats.get("busy", 0)
        total = stats.get("total", 0)
        self.status_label.setText(f"Browsers: {busy}/{total}")

    # ---------------------------------------------------------- Retry
    def _retry_failed(self):
        strategy = self._infer_strategy()
        failed_rows = []
        for row in range(self.table.rowCount()):
            status_w = self._get_inner_widget(row, COL["status"])
            if status_w and isinstance(status_w, BodyLabel):
                text = status_w.text()
                if "✗" in text or "Failed" in text:
                    failed_rows.append(row)
        if not failed_rows:
            return

        items = strategy.collect_items(self, failed_rows)
        if not items:
            return

        if isinstance(strategy, type(STRATEGIES["upload"])):
            self._earning_batch_started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._earning_batch_candidates = [
                {**item, "table_row": table_row}
                for item, table_row in zip(items, failed_rows)
            ]
        else:
            self._earning_batch_candidates = []
            self._earning_batch_started_at = None

        # Reset failed row statuses
        for row in failed_rows:
            status_w = self._get_inner_widget(row, COL["status"])
            if status_w and isinstance(status_w, BodyLabel):
                status_w.setText("Pending")
            error_w = self._get_inner_widget(row, COL["error"])
            if error_w and isinstance(error_w, LineEdit):
                error_w.setText("")
            self._set_row_bg(row, QColor(0, 0, 0, 0))

        # Multi-session
        multi_session = self.main.settings.get("multi_session_enabled", False)
        session_mgr = self.session_manager if (
            multi_session and self.session_manager and self.session_manager.is_ready()
        ) else None

        self.worker = strategy.create_worker(
            self, items, failed_rows,
            multi_session=bool(session_mgr),
            session_manager=session_mgr,
        )
        self.worker.row_update.connect(self._on_row_update)
        self.worker.done.connect(self._on_done)
        if hasattr(self.worker, "progress_update"):
            self.worker.progress_update.connect(self._on_progress_update)
        if hasattr(self.worker, "log"):
            self.worker.log.connect(self._on_log)
        if hasattr(self.worker, "session_status"):
            self.worker.session_status.connect(self._on_session_status)
        if hasattr(self.worker, "review_required"):
            self.worker.review_required.connect(self._on_review_required)

        self._set_busy(True)
        self.worker.start()

    # ---------------------------------------------------------- Shortcuts
    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+Return"), self, self._start_batch)
        QShortcut(QKeySequence("Ctrl+R"), self, self._retry_failed)
        QShortcut(QKeySequence("Escape"), self, self._handle_cancel)

    def _handle_cancel(self):
        if self._active_review is not None:
            InfoBar.warning(
                title="Reikia užbaigti peržiūrą",
                content="Pirmiausia išsaugokite arba atmeskite atidaryto produkto pakeitimus.",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self,
            )
            return
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            InfoBar.warning(
                title=self.main.i18n.tr("batch.stop.title"),
                content=self.main.i18n.tr("batch.stop.body"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )

    # ---------------------------------------------------------- Theme
    def _update_table_theme(self):
        is_dark = isDarkTheme()
        tc = COMPONENT_COLORS["table"]
        bg = tc["row_alt_bg_dark"] if is_dark else tc["row_alt_bg_light"]
        alt_bg = tc["row_bg_dark"] if is_dark else tc["row_bg_light"]
        border = tc["border_dark"] if is_dark else tc["border_light"]
        header_bg = COLORS["lavender_grey"] if is_dark else COLORS["space_indigo"]
        header_text = COLORS["space_indigo"] if is_dark else COLORS["text_white"]
        text_color = COLORS["text_primary_dark"] if is_dark else COLORS["text_primary_light"]

        from GUI_Qt.styles.theme_config import (
            get_embedded_input_border,
            get_scrollbar_handle_bg,
            get_scrollbar_handle_hover_bg,
            get_selection_bg,
        )

        eib = get_embedded_input_border(is_dark)
        eib_bg = COMPONENT_COLORS["input"]["bg_dark"] if is_dark else COMPONENT_COLORS["input"]["bg_light"]

        # Row focus tint
        row_focus = "rgba(43, 45, 66, 0.04)" if not is_dark else "rgba(141, 153, 174, 0.08)"

        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {bg};
                alternate-background-color: {alt_bg};
                border: none;
                selection-background-color: {get_selection_bg()};
                color: {text_color};
            }}
            QTableWidget::viewport {{
                background-color: {bg};
            }}
            QAbstractScrollArea::corner {{
                background: transparent;
            }}
            QTableWidget::item {{
                padding: {PADDINGS['table_cell']};
                color: {text_color};
                border: none;
                border-bottom: 1px solid {border};
            }}
            QTableWidget::item:focus {{
                outline: none;
            }}
            QTableWidget:focus {{
                outline: none;
            }}
            QTableView::item:focus, QAbstractItemView::item:focus {{
                outline: none;
            }}
            QTableWidget QWidget:focus {{
                outline: none;
            }}
            QTableWidget::item:selected {{
                background-color: {row_focus};
                color: {text_color};
            }}
            QHeaderView::section {{
                background-color: {header_bg};
                color: {header_text};
                padding: {PADDINGS['table_header']};
                border: none;
                border-bottom: 2px solid {border};
                font-weight: 600;
                font-size: {FONTS['size_body_sm']};
                letter-spacing: 0.5px;
                text-transform: uppercase;
            }}
            QHeaderView {{
                background: transparent;
                border: none;
            }}
            QHeaderView::section:first {{
                border-top-left-radius: {RADII['md']}px;
            }}
            QHeaderView::section:horizontal:last {{
                border-top-right-radius: {RADII['md']}px;
            }}

            /* Ghost inputs: borderless by default, reveal on hover/focus */
            QTableWidget QWidget[ubTableCell="true"] LineEdit,
            QTableWidget QWidget[ubTableCell="true"] QLineEdit,
            QTableWidget QWidget[ubTableCell="true"] ComboBox,
            QTableWidget QWidget[ubTableCell="true"] QComboBox {{
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: {RADII['sm']}px;
                padding: {PADDINGS['combo']};
                outline: none;
                color: {text_color};
            }}
            QTableWidget QWidget[ubTableCell="true"] LineEdit:hover,
            QTableWidget QWidget[ubTableCell="true"] QLineEdit:hover,
            QTableWidget QWidget[ubTableCell="true"] ComboBox:hover,
            QTableWidget QWidget[ubTableCell="true"] QComboBox:hover {{
                background-color: {eib_bg};
                border: 1px solid {eib};
            }}
            QTableWidget QWidget[ubTableCell="true"] LineEdit:focus,
            QTableWidget QWidget[ubTableCell="true"] QLineEdit:focus,
            QTableWidget QWidget[ubTableCell="true"] ComboBox:focus,
            QTableWidget QWidget[ubTableCell="true"] QComboBox:focus {{
                background-color: {eib_bg};
                border: 1px solid {eib};
                border-bottom: 2px solid {COLORS['lavender_grey']};
            }}

            QScrollBar:vertical {{
                background: transparent;
                width: {SIZES['scrollbar_thickness']}px;
                margin: {SPACING['xxs']}px {SPACING['xxs']}px {SPACING['xxs']}px 0px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {get_scrollbar_handle_bg(is_dark)};
                border-radius: {RADII['sm']}px;
                min-height: {SIZES['scrollbar_handle_min']}px;
                margin: 0px {SPACING['xxs']}px;
                border: none;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {get_scrollbar_handle_hover_bg(is_dark)};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                border: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
            QScrollBar:horizontal {{
                background: transparent;
                height: {SIZES['scrollbar_thickness']}px;
                margin: 0px {SPACING['xxs']}px {SPACING['xxs']}px {SPACING['xxs']}px;
                border: none;
            }}
            QScrollBar::handle:horizontal {{
                background: {get_scrollbar_handle_bg(is_dark)};
                border-radius: {RADII['sm']}px;
                min-width: {SIZES['scrollbar_handle_min']}px;
                margin: {SPACING['xxs']}px 0px;
                border: none;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {get_scrollbar_handle_hover_bg(is_dark)};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
                border: none;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}
        """)

    def _on_theme_changed(self):
        apply_screen_theme(
            self, "UnifiedBatchScreen",
            scroll=None, content=self.content_widget,
        )
        enforce_transparent_labels(self)
        self._update_table_theme()
        if hasattr(self, "_frozen_overlay"):
            self._frozen_overlay.update_theme(self.table.styleSheet())

    # -------------------------------------------------------- Retranslate
    def retranslate_ui(self):
        tr = self.main.i18n.tr
        self.title_label.setText(tr("batch.unified.title"))

        # Preset combo labels
        self.preset_combo.blockSignals(True)
        for i, key in enumerate(self._preset_keys):
            self.preset_combo.setItemText(i, tr(f"batch.preset.{key}"))
        self.preset_combo.blockSignals(False)

        self.manual_pill.setText(tr("batch.mode.manual"))
        self.excel_pill.setText(tr("batch.mode.excel"))
        self.add_btn.setToolTip(tr("batch.add_row"))
        self.clear_btn.setToolTip(tr("batch.clear_all"))
        self.browse_btn.setText(tr("batch.browse_excel"))
        self.template_btn.setToolTip(tr("batch.download_template"))
        self.export_btn.setToolTip(tr("batch.export"))
        self.start_btn.setText(f"{tr('batch.start')} (Ctrl+Enter)")
        self.retry_btn.setText(f"{tr('batch.retry_failed')} (Ctrl+R)")
        self.disclaimer_bulk.setText(tr("batch.disclaimer_all"))
        self.density_compact_btn.setToolTip(tr("batch.density.compact"))
        self.density_standard_btn.setToolTip(tr("batch.density.standard"))
        self.inspector_btn.setToolTip(tr("batch.inspector.toggle"))

        # Inspector panel
        if hasattr(self, "inspector"):
            self.inspector.retranslate(tr)

        # Setup card
        self.setup_title.setText(tr("batch.setup.title"))
        self.setup_subtitle.setText(tr("batch.setup.subtitle"))
        for key, card in self._preset_cards.items():
            for child in card.findChildren(StrongBodyLabel):
                i18n_key = child.property("_i18n_key")
                if i18n_key:
                    child.setText(tr(i18n_key))
            for child in card.findChildren(CaptionLabel):
                i18n_key = child.property("_i18n_key")
                if i18n_key:
                    child.setText(tr(i18n_key))

        self._update_header_labels()

        # Fresh empty state
        if hasattr(self, "_fresh_title"):
            self._fresh_title.setText(tr("batch.fresh.hint"))
            self._fresh_subtitle.setText(tr("batch.fresh.subhint"))
            self._fresh_btn.setText(tr("batch.fresh.btn"))

        # Drop zone
        if hasattr(self.drop_zone, "retranslate_ui"):
            self.drop_zone.retranslate_ui()

    # ------------------------------------------------------- Lifecycle
    def hideEvent(self, event):
        super().hideEvent(event)
        if self.session_manager is not None:
            try:
                self.session_manager.shutdown_all()
                self.session_manager = None
            except Exception:
                pass

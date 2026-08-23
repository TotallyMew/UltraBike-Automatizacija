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
from GUI_Qt.components.dialogs import DestructiveActionDialog
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
from GUI_Qt.batch.execution import BatchExecutionController
from GUI_Qt.batch.table import BatchTableController
from GUI_Qt.batch.workbook import BatchWorkbookIO

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
    _STATUS_COLS = BatchTableController._STATUS_COLS
    _DENSITY_CONFIG = BatchTableController._DENSITY_CONFIG
    _wrap_widget = BatchTableController._wrap_widget
    _wrap_checkbox = BatchTableController._wrap_checkbox
    _input_height = BatchTableController._input_height
    _setup_table_row = BatchTableController._setup_table_row
    _get_inner_widget = BatchTableController._get_inner_widget
    _load_saved_column_config = BatchTableController._load_saved_column_config
    _save_column_config = BatchTableController._save_column_config
    _apply_column_config = BatchTableController._apply_column_config
    _update_header_labels = BatchTableController._update_header_labels
    _update_toolbar_visibility = BatchTableController._update_toolbar_visibility
    _adjust_column_sizing = BatchTableController._adjust_column_sizing
    _set_density = BatchTableController._set_density
    _mirror_frozen_row = BatchTableController._mirror_frozen_row
    _wrap_frozen_widget = BatchTableController._wrap_frozen_widget
    _sync_frozen_cell = BatchTableController._sync_frozen_cell
    _toggle_inspector = BatchTableController._toggle_inspector
    _on_table_double_click = BatchTableController._on_table_double_click
    _on_current_row_changed = BatchTableController._on_current_row_changed
    _load_inspector_row = BatchTableController._load_inspector_row
    _read_cell_value = BatchTableController._read_cell_value
    _sync_inspector_combos = BatchTableController._sync_inspector_combos
    _on_inspector_field_changed = BatchTableController._on_inspector_field_changed
    _on_table_cell_changed = BatchTableController._on_table_cell_changed
    _on_inspector_navigate = BatchTableController._on_inspector_navigate
    resizeEvent = BatchTableController.resizeEvent
    _on_preset_card_clicked = BatchTableController._on_preset_card_clicked
    _sync_preset_combo = BatchTableController._sync_preset_combo
    _on_preset_combo_changed = BatchTableController._on_preset_combo_changed
    _apply_preset_with_import = BatchTableController._apply_preset_with_import
    _switch_columns_preserve = BatchTableController._switch_columns_preserve
    _open_column_picker = BatchTableController._open_column_picker
    _infer_strategy = BatchTableController._infer_strategy
    _validate = BatchTableController._validate
    _update_row_status = BatchTableController._update_row_status
    _has_data_in_table = BatchTableController._has_data_in_table
    _add_row = BatchTableController._add_row
    _add_row_silent = BatchTableController._add_row_silent
    _remove_row = BatchTableController._remove_row
    _clear_all = BatchTableController._clear_all
    _clear_table_data = BatchTableController._clear_table_data
    _on_brand_change = BatchTableController._on_brand_change
    _toggle_disclaimer_all = BatchTableController._toggle_disclaimer_all
    _load_attr_combo_options = BatchTableController._load_attr_combo_options
    _on_header_context_menu = BatchTableController._on_header_context_menu
    _manage_attr_options = BatchTableController._manage_attr_options
    _normalize_code = staticmethod(BatchTableController._normalize_code)
    _switch_input_mode = BatchTableController._switch_input_mode

    _handle_file_drop = BatchWorkbookIO._handle_file_drop
    _browse_excel = BatchWorkbookIO._browse_excel
    _load_excel = BatchWorkbookIO._load_excel
    _populate_row_from_dict = BatchWorkbookIO._populate_row_from_dict
    _download_template = BatchWorkbookIO._download_template
    _export_table_data = BatchWorkbookIO._export_table_data

    _start_batch = BatchExecutionController._start_batch
    _on_review_required = BatchExecutionController._on_review_required
    _show_next_review = BatchExecutionController._show_next_review
    _send_review_action = BatchExecutionController._send_review_action
    _confirm_review_saved = BatchExecutionController._confirm_review_saved
    _confirm_review_discard = BatchExecutionController._confirm_review_discard
    _set_busy = BatchExecutionController._set_busy
    _update_elapsed = BatchExecutionController._update_elapsed
    _on_row_update = BatchExecutionController._on_row_update
    _set_row_bg = BatchExecutionController._set_row_bg
    _on_done = BatchExecutionController._on_done
    _prompt_completed_batch_earnings = BatchExecutionController._prompt_completed_batch_earnings
    _on_progress_update = BatchExecutionController._on_progress_update
    _on_log = BatchExecutionController._on_log
    _on_session_status = BatchExecutionController._on_session_status
    _retry_failed = BatchExecutionController._retry_failed
    _setup_shortcuts = BatchExecutionController._setup_shortcuts
    _handle_cancel = BatchExecutionController._handle_cancel

    def _update_table_theme(self):
        is_dark = isDarkTheme()
        tc = COMPONENT_COLORS["table"]
        bg = tc["row_bg_dark"] if is_dark else tc["row_bg_light"]
        alt_bg = tc["row_alt_bg_dark"] if is_dark else tc["row_alt_bg_light"]
        border = tc["border_dark"] if is_dark else tc["border_light"]
        header_bg = tc["header_bg_dark" if is_dark else "header_bg_light"]
        header_text = tc["header_text_dark" if is_dark else "header_text_light"]
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
        self.review_saved_btn.setText(tr("batch.review.saved.action"))
        self.review_discard_btn.setText(tr("batch.review.discard.button"))

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

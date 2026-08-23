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
    get_text_color,
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

class BatchTableController:
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
        status_lbl.setStyleSheet(f"color: {get_text_color(isDarkTheme(), 'secondary')};")
        self.table.setCellWidget(row, COL["status"], self._wrap_widget(status_lbl, row, COL["status"]))

        # Error
        error_edit = LineEdit()
        error_edit.setReadOnly(True)
        error_edit.setMinimumHeight(ih)
        self.table.setCellWidget(row, COL["error"], self._wrap_widget(error_edit, row, COL["error"]))

        # Delete (19)
        del_btn = TransparentToolButton(FluentIcon.DELETE, self)
        del_btn.setFixedSize(SIZES["button_height_sm"], SIZES["button_height_sm"])
        del_btn.setToolTip(self.main.i18n.tr("batch.row.remove.tip"))
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
        # This controller's methods are attached to UnifiedBatchScreen rather
        # than inherited through BatchTableController. Zero-argument super()
        # therefore resolves against the wrong class and raises inside Qt's
        # resize/event-filter chain. Call the screen's real QWidget base
        # explicitly so responsive breakpoint handling still runs.
        ResponsiveWidget.resizeEvent(self, event)
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

        color = {
            "draft": COLORS["text_tertiary_dark"] if isDarkTheme() else COLORS["text_tertiary_light"],
            "incomplete": COLORS["warning"],
            "ready": COLORS["success"],
        }[state]
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
        confirmed = DestructiveActionDialog.ask(
            title=self.main.i18n.tr("batch.clear.title"),
            message=self.main.i18n.tr("batch.clear.body"),
            action_text=self.main.i18n.tr("batch.clear_all"),
            parent=self,
            tr_func=self.main.i18n.tr,
        )
        if confirmed:
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

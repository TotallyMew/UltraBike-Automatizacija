"""Grouped bike rows with one source choice per TTCC model."""
from __future__ import annotations

import math

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup, QHeaderView, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)
from qfluentwidgets import CaptionLabel, CheckBox, PushButton, RadioButton, isDarkTheme

from GUI_Qt.styles.screen_theme import enforce_transparent_labels
from GUI_Qt.styles.theme_config import get_text_color


class ModelCopyGroupTable(QTableWidget):
    source_selected = Signal(str, str)
    groups_selected = Signal()
    BASE, SOURCE, SKU, NAME, STATUS = range(5)

    def __init__(self, translate, status_text, parent=None):
        super().__init__(0, 5, parent)
        self._t, self._status_text = translate, status_text
        self.groups = []
        self._checks = {}
        self._source_buttons = {}
        self._clear_buttons = {}
        self._button_groups = []
        self._group_rows = {}
        self._group_cells = {}
        self._filter = ""
        self._busy = False
        self.setObjectName("orbeaModelCopyGroups")
        self.setMinimumHeight(500)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.setWordWrap(True)
        self.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.setShowGrid(False)
        self.verticalHeader().hide()
        self.horizontalHeader().setMinimumHeight(46)
        for column, width in ((self.BASE, 165), (self.SOURCE, 82), (self.SKU, 125), (self.STATUS, 110)):
            self.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.setColumnWidth(column, width)
        self.horizontalHeader().setSectionResizeMode(self.NAME, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().sectionResized.connect(lambda *_: self._queue_row_sizes())
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._resize_bike_rows)

    @staticmethod
    def eligible(group):
        return bool(group.source_sku and group.targets and not group.workbook_error)

    def group_check(self, ttcc):
        return self._checks[ttcc]

    def source_button(self, ttcc, sku):
        return self._source_buttons[(ttcc, sku)]

    def selected_codes(self, *, visible_only=True):
        return tuple(group.ttcc for group in self.groups
                     if self._checks[group.ttcc].isChecked() and self.eligible(group)
                     and (not visible_only or not self.isRowHidden(self._group_rows[group.ttcc][0])))

    def set_groups(self, groups, results=(), *, preserve_selection=False):
        selected = set(self.selected_codes(visible_only=False)) if preserve_selection else None
        scroll = self.verticalScrollBar().value()
        for buttons in self._button_groups:
            buttons.deleteLater()
        self.groups = groups
        self._checks, self._source_buttons, self._clear_buttons = {}, {}, {}
        self._button_groups, self._group_rows, self._group_cells = [], {}, {}
        self.clearSpans()
        self.clearContents()
        self.setRowCount(sum(len(group.rows) for group in groups))
        result_lookup = {(result.ttcc, result.sku): result for result in results}
        row_index = 0
        for group in groups:
            rows = tuple(range(row_index, row_index + len(group.rows)))
            self._group_rows[group.ttcc] = rows
            cell = QWidget()
            cell.setObjectName("orbeaModelCopyGroupCell")
            cell.setStyleSheet("#orbeaModelCopyGroupCell { background: transparent; }")
            box = QVBoxLayout(cell)
            box.setContentsMargins(10, 12, 10, 12)
            box.setSpacing(6)
            box.setAlignment(Qt.AlignmentFlag.AlignTop)
            check = CheckBox(group.ttcc)
            check.setToolTip(self._t("group_check", "Include {ttcc} in this run", ttcc=group.ttcc))
            check.setChecked(self.eligible(group) and (selected is None or group.ttcc in selected))
            check.toggled.connect(lambda *_: self.groups_selected.emit())
            self._checks[group.ttcc] = check
            box.addWidget(check)
            count = CaptionLabel(self._t("group_count", "{bikes} bikes · {targets} targets", bikes=len(group.rows), targets=max(0, len(group.rows) - 1)))
            count.setWordWrap(True)
            box.addWidget(count)
            status = CaptionLabel(self._status_text(group.status))
            status.setWordWrap(True)
            box.addWidget(status)
            if group.error:
                error = CaptionLabel(group.error)
                error.setWordWrap(True)
                error.setToolTip(group.error)
                box.addWidget(error)
            clear = PushButton(self._t("clear_source", "Clear source"))
            clear.setFixedHeight(28)
            clear.setVisible(bool(group.source_sku))
            clear.clicked.connect(lambda _checked=False, code=group.ttcc: self.source_selected.emit(code, ""))
            self._clear_buttons[group.ttcc] = clear
            box.addWidget(clear)
            cell.setToolTip(group.error)
            self._group_cells[group.ttcc] = cell
            if len(rows) > 1:
                self.setSpan(row_index, self.BASE, len(rows), 1)
            self.setCellWidget(row_index, self.BASE, cell)
            buttons = QButtonGroup(self)
            buttons.setExclusive(True)
            self._button_groups.append(buttons)
            for bike in group.rows:
                source = bike.sku == group.source_sku
                button = RadioButton()
                button.setChecked(source)
                button.setAccessibleName(self._t("source_choice", "Use {sku} as source for {ttcc}", sku=bike.sku, ttcc=group.ttcc))
                button.setToolTip(self._t("source_help", "Choose the bike you have prepared and saved in Pimbo. Its data will be copied to the other bikes in this group."))
                buttons.addButton(button)
                button.clicked.connect(lambda _checked=False, code=group.ttcc, sku=bike.sku: self.source_selected.emit(code, sku))
                self._source_buttons[(group.ttcc, bike.sku)] = button
                wrapper = QWidget()
                wrapper.setObjectName("orbeaModelCopyChoice")
                wrapper.setStyleSheet("#orbeaModelCopyChoice { background: transparent; }")
                choice_box = QHBoxLayout(wrapper)
                choice_box.setContentsMargins(0, 0, 0, 0)
                choice_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
                choice_box.addWidget(button)
                self.setCellWidget(row_index, self.SOURCE, wrapper)
                result = result_lookup.get((group.ttcc, bike.sku))
                name = (group.template.title if source and group.template else
                        result.title if result and result.status == "saved" and result.title else bike.title)
                role = (self._t("source_role", "Source") if source else self._status_text(result.status) if result else
                        self._t("target_role", "Target") if group.source_sku else self._t("bike_role", "Bike"))
                for column, text in ((self.SKU, bike.sku), (self.NAME, name), (self.STATUS, role)):
                    item = QTableWidgetItem(text)
                    item.setToolTip(result.error if result and result.error and column == self.STATUS else text)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                    if column == self.SKU:
                        font = item.font()
                        font.setBold(source)
                        item.setFont(font)
                    self.setItem(row_index, column, item)
                self.setRowHeight(row_index, 64)
                row_index += 1
        enforce_transparent_labels(self)
        self._apply_filter()
        self.set_busy(self._busy)
        self._queue_row_sizes()
        self.verticalScrollBar().setValue(scroll)

    def set_busy(self, busy):
        self._busy = busy
        for group in self.groups:
            can_choose = not busy and not group.workbook_error and len(group.rows) > 1
            self._checks[group.ttcc].setEnabled(not busy and self.eligible(group))
            self._clear_buttons[group.ttcc].setEnabled(can_choose)
            for bike in group.rows:
                self._source_buttons[(group.ttcc, bike.sku)].setEnabled(can_choose)

    def set_filter(self, text):
        self._filter = text.strip().casefold()
        self._apply_filter()
        self.groups_selected.emit()

    def _apply_filter(self):
        for group in self.groups:
            text = " ".join([group.ttcc] + [f"{bike.sku} {bike.title}" for bike in group.rows])
            text += " " + " ".join(self.item(row, self.NAME).text() for row in self._group_rows[group.ttcc])
            hidden = bool(self._filter and self._filter not in text.casefold())
            for row in self._group_rows[group.ttcc]:
                self.setRowHidden(row, hidden)

    def visible_groups(self):
        return tuple(group for group in self.groups if not self.isRowHidden(self._group_rows[group.ttcc][0]))

    def select_visible(self, checked):
        if self._busy:
            return
        for group in self.visible_groups():
            if self.eligible(group):
                self._checks[group.ttcc].setChecked(checked)
        self.groups_selected.emit()

    def _queue_row_sizes(self):
        if hasattr(self, "_resize_timer"):
            self._resize_timer.start(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._queue_row_sizes()

    def showEvent(self, event):
        super().showEvent(event)
        self._queue_row_sizes()

    def _resize_bike_rows(self):
        width = max(80, self.columnWidth(self.NAME) - 24)
        metrics = self.fontMetrics()
        for group in self.groups:
            rows = self._group_rows[group.ttcc]
            cell = self._group_cells[group.ttcc]
            cell_height = max(cell.sizeHint().height(), cell.heightForWidth(self.columnWidth(self.BASE)))
            minimum = math.ceil(cell_height / max(1, len(rows)))
            for row in rows:
                text = self.item(row, self.NAME).text()
                height = metrics.boundingRect(QRect(0, 0, width, 1000), Qt.TextFlag.TextWordWrap, text).height()
                self.setRowHeight(row, max(56, minimum, height + metrics.lineSpacing() + 24))

    def apply_theme(self, style):
        self.setStyleSheet(style)
        dark = isDarkTheme()
        for row in range(self.rowCount()):
            for column in (self.SKU, self.NAME, self.STATUS):
                item = self.item(row, column)
                if item:
                    item.setForeground(QColor(get_text_color(dark, "primary")))
        self._queue_row_sizes()

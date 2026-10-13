"""An explicit colour mapping editor in the copy workspace."""
import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem
from qfluentwidgets import CaptionLabel

from tools.orbea_automation.colour_attributes import load_colour_mapping
from .tabs import OrbeaDisclosure


class OrbeaColourAttributePanel(OrbeaDisclosure):
    changed = Signal()

    def __init__(self, screen, translate, parent=None):
        super().__init__(parent)
        self.screen, self.translate = screen, translate
        self.catalogue = load_colour_mapping()
        stored = screen._setting_get("orbea_colour_attribute_overrides", {})
        try:
            self.overrides = json.loads(stored) if isinstance(stored, str) else dict(stored)
        except (TypeError, ValueError):
            self.overrides = {}
        self.mapping, self.error = None, ""
        self.hint = CaptionLabel("")
        self.hint.setWordWrap(True)
        self.summary = CaptionLabel("")
        self.summary.setWordWrap(True)
        self.body_layout.addWidget(self.hint)
        self.body_layout.addWidget(self.summary)
        self.table = QTableWidget(len(self.catalogue.entries), 2)
        self.table.setMinimumHeight(250)
        self.table.setMaximumHeight(380)
        self.table.setWordWrap(False)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.blockSignals(True)
        for row, entry in enumerate(self.catalogue.entries):
            original = QTableWidgetItem(entry.orbea_colour)
            original.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            original.setData(Qt.ItemDataRole.UserRole, entry.id)
            self.table.setItem(row, 0, original)
            values = self.overrides.get(entry.id, entry.attribute_values)
            self.table.setItem(row, 1, QTableWidgetItem("; ".join(values) if isinstance(values, (list, tuple)) else ""))
        self.table.blockSignals(False)
        self.table.itemChanged.connect(self._changed)
        self.body_layout.addWidget(self.table)
        self.refresh_mapping()
        self.retranslate_ui()

    def refresh_mapping(self):
        try:
            self.mapping = load_colour_mapping(self.overrides)
            self.error = ""
        except (TypeError, ValueError) as error:
            self.mapping, self.error = None, str(error)
        self._summary()

    def _changed(self, item):
        if item.column() != 1:
            return
        identifier = self.table.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)
        self.overrides[identifier] = list(dict.fromkeys(value.strip() for value in item.text().split(";") if value.strip()))
        self.screen._setting_set("orbea_colour_attribute_overrides", json.dumps(self.overrides, ensure_ascii=False))
        self.refresh_mapping()
        self.changed.emit()

    def _summary(self):
        if self.error:
            self.summary.setText(self.error)
        else:
            self.summary.setText(self.translate("colours_summary", "{mapped} of {total} colours mapped. Unmapped colour attributes stay unchanged.",
                mapped=self.mapping.mapped_count, total=len(self.catalogue.entries)))

    def retranslate_ui(self):
        self.set_title(self.translate("colours_title", "Orbea colour → Spalva attribute"))
        self.hint.setText(self.translate("colours_hint", "Enter existing Pimbo attribute choices; separate multiple values with ;. Specification Spalva is never changed. Dash spacing and C. View spelling are normalised. Gloss/Matt labels distinguish finishes with different assignments; missing labels match only unambiguous paints."))
        self.table.setHorizontalHeaderLabels((self.translate("orbea_colour", "Orbea colour"),
                                              self.translate("colour_attribute", "Spalva attribute")))
        self._summary()

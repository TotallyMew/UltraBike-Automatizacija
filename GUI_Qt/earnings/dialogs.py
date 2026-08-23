"""Earnings entry, goal, settings, brand, and upload dialogs."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from PySide6.QtCore import QDate, QEvent, QPoint, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QTextCharFormat
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QCalendarWidget,
    QCheckBox,
    QDateEdit,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QSlider,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTabBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTableView,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    BodyLabel,
    CaptionLabel,
    CheckBox,
    ComboBox,
    DateEdit as FluentDateEdit,
    DoubleSpinBox as FluentDoubleSpinBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    MessageBox,
    PrimaryPushButton,
    PushButton,
    RoundMenu,
    ScrollArea,
    SegmentedWidget,
    SpinBox as FluentSpinBox,
    StrongBodyLabel,
    TitleLabel,
    isDarkTheme,
    qconfig,
)

from GUI_Qt.styles.screen_theme import apply_screen_theme
from GUI_Qt.styles.theme_config import (
    COLORS,
    COMPONENT_COLORS,
    FONTS,
    PADDINGS,
    RADII,
    SIZES,
    SPACING,
    get_dialog_button_style,
    get_dialog_danger_button_style,
    get_dialog_section_style,
    get_dialog_table_style,
    get_calendar_popup_style,
    get_form_dialog_style,
    get_form_input_style,
    get_selection_bg,
    get_status_text_color,
    get_subtle_border,
    get_subtle_item_hover_bg,
    get_text_color,
    rgba_from_hex,
)
from GUI_Qt.widgets.ResponsiveWidget import ResponsiveWidget
from Managers.EarningsManager import (
    ActiveGoalError,
    ActiveSessionError,
    EarningsManager,
    GoalStatus,
    ProductType,
    QuestKind,
)


from GUI_Qt.earnings.presentation import PRODUCT_TYPES, duration, goal_progress_state, local_datetime, money
from GUI_Qt.earnings.widgets import FluentCalendarWidget, apply_earnings_datetime_theme, configure_earnings_datetime_edit

class EarningEntryDialog(QDialog):
    def __init__(self, service: EarningsManager, entry=None, parent=None):
        super().__init__(parent)
        self.service = service
        self.entry = entry
        self.setWindowTitle("Edit earning" if entry else "Add earning")
        self.setMinimumWidth(440)
        layout = QFormLayout(self)
        self.sku = LineEdit()
        self.name = LineEdit()
        self.brand = ComboBox()
        self.type = ComboBox()
        self.when = QDateTimeEdit(datetime.now())
        configure_earnings_datetime_edit(self.when)
        self._populate_brands()
        for key, label in PRODUCT_TYPES:
            self.type.addItem(label, userData=key)
        layout.addRow("SKU *", self.sku)
        layout.addRow("Name", self.name)
        layout.addRow("Brand", self.brand)
        layout.addRow("Product type", self.type)
        layout.addRow("Earned at", self.when)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        qconfig.themeChangedFinished.connect(self._apply_theme)
        if entry:
            self.sku.setText(entry["sku"])
            self.name.setText(entry.get("product_name") or "")
            idx = self.brand.findData(entry.get("brand_id"))
            self.brand.setCurrentIndex(max(0, idx))
            idx = self.type.findData(entry["product_type"])
            self.type.setCurrentIndex(max(0, idx))
            parsed = datetime.fromisoformat(entry["earned_at"].replace("Z", "+00:00")).astimezone()
            self.when.setDateTime(parsed)

    def _apply_theme(self):
        apply_earnings_datetime_theme(self.when)

    def _populate_brands(self):
        self.brand.clear()
        self.brand.addItem("No brand", userData=None)
        for brand in self.service.list_brands():
            self.brand.addItem(brand["name"], userData=brand["id"])

    def _accept(self):
        if not self.sku.text().strip():
            QMessageBox.warning(self, "Missing SKU", "SKU is required.")
            return
        self.accept()

    def values(self) -> dict[str, Any]:
        return {
            "sku": self.sku.text().strip(),
            "product_name": self.name.text().strip() or None,
            "brand_id": self.brand.currentData(),
            "product_type": self.type.currentData(),
            "earned_at": self.when.dateTime().toPython(),
        }


class BulkEarningEditDialog(QDialog):
    """Choose shared fields to apply to a multi-row earnings selection."""

    def __init__(
        self,
        service: EarningsManager,
        selected_count: int,
        parent=None,
        translate=None,
    ):
        super().__init__(parent)
        self.service = service
        self.selected_count = max(1, int(selected_count))
        self._translate = translate
        self.setWindowTitle(
            self._t(
                "earnings.bulk.title",
                "Edit {count} earnings",
                count=self.selected_count,
            )
        )
        self.setObjectName("earningsBulkEditDialog")
        self.setModal(True)
        self.setFixedWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"]
        )
        layout.setSpacing(SPACING["md"])

        heading = StrongBodyLabel(
            self._t(
                "earnings.bulk.heading",
                "Update selected earnings",
            )
        )
        intro = CaptionLabel(
            self._t(
                "earnings.bulk.intro",
                "Choose only the fields you want to change. Unchecked fields remain untouched.",
            )
        )
        intro.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(intro)

        section = QWidget()
        section.setObjectName("earningsDialogSection")
        section.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        grid = QGridLayout(section)
        grid.setContentsMargins(
            SPACING["md"], SPACING["md"], SPACING["md"], SPACING["md"]
        )
        grid.setHorizontalSpacing(SPACING["md"])
        grid.setVerticalSpacing(SPACING["md"])
        grid.setColumnStretch(1, 1)

        self.brand_toggle = CheckBox(
            self._t("earnings.bulk.brand", "Change brand")
        )
        self.brand = ComboBox()
        self.brand.addItem(
            self._t("earnings.brand.none", "No brand"), userData=None
        )
        for brand in self.service.list_brands():
            self.brand.addItem(brand["name"], userData=brand["id"])
        self.brand.setEnabled(False)
        self.brand.setAccessibleName(
            self._t("earnings.field.brand", "Brand")
        )

        self.type_toggle = CheckBox(
            self._t("earnings.bulk.type", "Change product type")
        )
        self.type = ComboBox()
        for key, label in PRODUCT_TYPES:
            self.type.addItem(label, userData=key)
        self.type.setEnabled(False)
        self.type.setAccessibleName(
            self._t("earnings.field.type", "Product type")
        )

        self.date_toggle = CheckBox(
            self._t("earnings.bulk.date", "Change date and time")
        )
        self.when = QDateTimeEdit(datetime.now())
        configure_earnings_datetime_edit(self.when)
        self.when.setEnabled(False)

        for row, (toggle, control) in enumerate(
            (
                (self.brand_toggle, self.brand),
                (self.type_toggle, self.type),
                (self.date_toggle, self.when),
            )
        ):
            grid.addWidget(toggle, row, 0)
            grid.addWidget(control, row, 1)
        layout.addWidget(section)

        self.safety_note = CaptionLabel(
            self._t(
                "earnings.bulk.preserve",
                "Historical earning amounts, SKUs, names, sources, and work-session links are preserved.",
            )
        )
        self.safety_note.setWordWrap(True)
        layout.addWidget(self.safety_note)

        footer = QHBoxLayout()
        footer.setSpacing(SPACING["sm"])
        footer.addStretch(1)
        self.cancel_button = PushButton(self._t("common.cancel", "Cancel"))
        self.save_button = PrimaryPushButton(
            self._t(
                "earnings.bulk.action",
                "Update {count} earnings",
                count=self.selected_count,
            )
        )
        for button in (self.cancel_button, self.save_button):
            button.setFixedHeight(SIZES["button_height"])
            button.setMinimumWidth(104)
        self.cancel_button.setAutoDefault(False)
        self.save_button.setAutoDefault(True)
        self.save_button.setDefault(True)
        self.save_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.save_button)
        layout.addLayout(footer)

        for toggle, control in (
            (self.brand_toggle, self.brand),
            (self.type_toggle, self.type),
            (self.date_toggle, self.when),
        ):
            toggle.toggled.connect(control.setEnabled)
            toggle.toggled.connect(self._update_save_state)
        qconfig.themeChangedFinished.connect(self._apply_theme)
        self._apply_theme()
        self.adjustSize()
        self.setFixedSize(560, self.sizeHint().height())

    def _t(self, key: str, fallback: str, **kwargs) -> str:
        if callable(self._translate):
            value = self._translate(key, **kwargs)
            if value != key:
                return value
        return fallback.format(**kwargs)

    def _update_save_state(self, _checked=False) -> None:
        self.save_button.setEnabled(
            any(
                toggle.isChecked()
                for toggle in (
                    self.brand_toggle,
                    self.type_toggle,
                    self.date_toggle,
                )
            )
        )

    def _apply_theme(self) -> None:
        dark = isDarkTheme()
        self.setStyleSheet(get_form_dialog_style(dark, self.objectName()))
        section_style = get_dialog_section_style(dark)
        for section in self.findChildren(QWidget, "earningsDialogSection"):
            section.setStyleSheet(section_style)
        apply_earnings_datetime_theme(self.when)
        self.cancel_button.setStyleSheet(
            get_dialog_button_style(dark, primary=False)
        )
        self.save_button.setStyleSheet(
            get_dialog_button_style(dark, primary=True)
        )

    def values(self) -> dict[str, Any]:
        return {
            "update_brand": self.brand_toggle.isChecked(),
            "brand_id": self.brand.currentData(),
            "product_type": (
                self.type.currentData() if self.type_toggle.isChecked() else None
            ),
            "earned_at": (
                self.when.dateTime().toPython()
                if self.date_toggle.isChecked()
                else None
            ),
        }


class GoalDialog(QDialog):
    def __init__(self, goal=None, parent=None):
        super().__init__(parent)
        existing_deadline = None
        if goal and goal.get("deadline_date"):
            existing_deadline = datetime.fromisoformat(goal["deadline_date"]).date()
        self.setWindowTitle("Edit money goal" if goal else "Create money goal")
        self.setObjectName("earningsGoalDialog")
        self.setModal(True)
        self.setFixedWidth(440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["xl"], SPACING["xl"], SPACING["xl"], SPACING["xl"])
        layout.setSpacing(0)

        amount_group = QVBoxLayout()
        amount_group.setSpacing(SPACING["sm"])
        amount_label = BodyLabel("Target amount")
        self.amount = FluentDoubleSpinBox()
        self.amount.setObjectName("goalAmountInput")
        self.amount.setFixedHeight(SIZES["input_height"])
        self.amount.setSymbolVisible(False)
        self.amount.setRange(0.01, 1_000_000)
        self.amount.setDecimals(2)
        self.amount.setPrefix("€")
        self.amount.setAccessibleName("Target amount")
        amount_label.setBuddy(self.amount)
        amount_group.addWidget(amount_label)
        amount_group.addWidget(self.amount)
        layout.addLayout(amount_group)

        layout.addSpacing(SPACING["base"])
        self.deadline_enabled = CheckBox("Use a deadline")
        self.deadline_enabled.setAccessibleName("Use a deadline")
        layout.addWidget(self.deadline_enabled)

        layout.addSpacing(SPACING["base"])
        deadline_group = QVBoxLayout()
        deadline_group.setSpacing(SPACING["sm"])
        deadline_label = BodyLabel("Deadline")
        self.deadline = FluentDateEdit()
        self.deadline.setObjectName("goalDeadlineInput")
        self.deadline.setFixedHeight(SIZES["input_height"])
        self.deadline.setSymbolVisible(False)
        self.deadline.setCalendarPopup(True)
        self.deadline.setDisplayFormat("dd MMM yyyy")
        today = datetime.now().date()
        self.deadline.setMinimumDate(min(today, existing_deadline or today))
        self.deadline.setDate(datetime.now().date())
        self.deadline.setEnabled(False)
        self.deadline.setAccessibleName("Deadline")
        deadline_label.setBuddy(self.deadline)
        self.deadline_enabled.toggled.connect(self.deadline.setEnabled)
        deadline_group.addWidget(deadline_label)
        deadline_group.addWidget(self.deadline)
        layout.addLayout(deadline_group)

        layout.addSpacing(SPACING["xl"])
        footer = QHBoxLayout()
        footer.setSpacing(SPACING["sm"])
        footer.addStretch(1)
        self.cancel_button = PushButton("Cancel")
        self.save_button = PrimaryPushButton("Save")
        self.cancel_button.setObjectName("goalCancelButton")
        self.save_button.setObjectName("goalSaveButton")
        self.cancel_button.setFixedHeight(SIZES["button_height"])
        self.save_button.setFixedHeight(SIZES["button_height"])
        self.cancel_button.setMinimumWidth(96)
        self.save_button.setMinimumWidth(96)
        self.cancel_button.setAutoDefault(False)
        self.save_button.setAutoDefault(True)
        self.save_button.setDefault(True)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.save_button)
        layout.addLayout(footer)

        if goal:
            self.amount.setValue(int(goal["target_cents"]) / 100)
            if existing_deadline:
                self.deadline_enabled.setChecked(True)
                self.deadline.setDate(existing_deadline)

        self.setTabOrder(self.amount, self.deadline_enabled)
        self.setTabOrder(self.deadline_enabled, self.deadline)
        self.setTabOrder(self.deadline, self.cancel_button)
        self.setTabOrder(self.cancel_button, self.save_button)
        qconfig.themeChangedFinished.connect(self._apply_theme)
        self._apply_theme()
        self.adjustSize()
        self.setFixedSize(440, self.sizeHint().height())

    def _apply_theme(self):
        dark = isDarkTheme()
        self.setStyleSheet(get_form_dialog_style(dark, self.objectName()))
        self.amount.setStyleSheet(get_form_input_style(dark, "QDoubleSpinBox"))
        self.deadline.setStyleSheet(get_form_input_style(dark, "QDateEdit", calendar=True))
        self.cancel_button.setStyleSheet(get_dialog_button_style(dark, primary=False))
        self.save_button.setStyleSheet(get_dialog_button_style(dark, primary=True))
        self.amount.setCustomFocusedBorderColor(
            COLORS["focus_ring_light"], COLORS["focus_ring_dark"]
        )
        self.deadline.setCustomFocusedBorderColor(
            COLORS["focus_ring_light"], COLORS["focus_ring_dark"]
        )
        self.deadline_enabled.setCheckedColor(
            COLORS["lavender_grey"], COLORS["lavender_grey"]
        )

    def values(self):
        return int(round(self.amount.value() * 100)), (
            self.deadline.date().toPython() if self.deadline_enabled.isChecked() else None
        )


class GoalAdjustmentDialog(QDialog):
    """Capture progress that belongs to a goal but not to Earnings."""

    ADD_AMOUNT = "add_amount"
    SET_TOTAL = "set_total"

    def __init__(self, parent=None, translate=None, current_progress_cents: int = 0):
        super().__init__(parent)
        self._translate = translate
        self.current_progress_cents = max(0, int(current_progress_cents))
        self._mode = self.ADD_AMOUNT
        self.setWindowTitle(self._t("earnings.goal.adjust.dialog.title", "Add goal progress"))
        self.setObjectName("earningsGoalAdjustmentDialog")
        self.setModal(True)
        self.setFixedWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["xl"], SPACING["xl"], SPACING["xl"], SPACING["xl"])
        layout.setSpacing(SPACING["md"])

        explanation = CaptionLabel(
            self._t(
                "earnings.goal.adjust.explanation",
                "Choose whether to add an amount or set the new current total. Only goal progress changes; earnings and analytics stay unchanged.",
            )
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        self.mode_selector = SegmentedWidget(self)
        self.mode_selector.addItem(
            self.ADD_AMOUNT,
            self._t("earnings.goal.adjust.mode.add", "Add an amount"),
            onClick=lambda: self._set_mode(self.ADD_AMOUNT),
        )
        self.mode_selector.addItem(
            self.SET_TOTAL,
            self._t("earnings.goal.adjust.mode.total", "Set current total"),
            onClick=lambda: self._set_mode(self.SET_TOTAL),
        )
        self.mode_selector.setCurrentItem(self.ADD_AMOUNT)
        layout.addWidget(self.mode_selector)

        self.amount_label = BodyLabel(
            self._t("earnings.goal.adjust.amount.add", "Amount to add")
        )
        self.amount = FluentDoubleSpinBox()
        self.amount.setObjectName("goalAdjustmentAmount")
        self.amount.setFixedHeight(SIZES["input_height"])
        self.amount.setSymbolVisible(False)
        self.amount.setRange(0.01, 1_000_000)
        self.amount.setDecimals(2)
        self.amount.setPrefix("€")
        self.amount_label.setBuddy(self.amount)
        layout.addWidget(self.amount_label)
        layout.addWidget(self.amount)

        self.amount_hint = CaptionLabel("")
        self.amount_hint.setWordWrap(True)
        layout.addWidget(self.amount_hint)

        note_label = BodyLabel(self._t("earnings.goal.adjust.note", "Note (optional)"))
        self.note = LineEdit()
        self.note.setObjectName("goalAdjustmentNote")
        self.note.setFixedHeight(SIZES["input_height"])
        self.note.setPlaceholderText(
            self._t("earnings.goal.adjust.note.placeholder", "For example: opening balance")
        )
        note_label.setBuddy(self.note)
        layout.addWidget(note_label)
        layout.addWidget(self.note)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self.cancel_button = PushButton(self._t("common.cancel", "Cancel"))
        self.save_button = PrimaryPushButton(
            self._t("earnings.goal.adjust.save", "Add to goal")
        )
        for button in (self.cancel_button, self.save_button):
            button.setFixedHeight(SIZES["button_height"])
            button.setMinimumWidth(104)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self._accept_if_valid)
        self.save_button.setDefault(True)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.save_button)
        layout.addLayout(footer)

        qconfig.themeChangedFinished.connect(self._apply_theme)
        self.amount.valueChanged.connect(self._update_amount_hint)
        self._update_mode_ui()
        self._apply_theme()
        self.adjustSize()
        self.setFixedSize(460, self.sizeHint().height())

    def _t(self, key: str, fallback: str, **values) -> str:
        if callable(self._translate):
            translated = self._translate(key, **values)
            if translated != key:
                return translated
        return fallback.format(**values)

    def _apply_theme(self):
        dark = isDarkTheme()
        self.setStyleSheet(get_form_dialog_style(dark, self.objectName()))
        self.amount.setStyleSheet(get_form_input_style(dark, "QDoubleSpinBox"))
        self.note.setStyleSheet(get_form_input_style(dark, "LineEdit"))
        self.cancel_button.setStyleSheet(get_dialog_button_style(dark, primary=False))
        self.save_button.setStyleSheet(get_dialog_button_style(dark, primary=True))

    def _set_mode(self, mode: str) -> None:
        if mode not in (self.ADD_AMOUNT, self.SET_TOTAL) or mode == self._mode:
            return
        entered_cents = int(round(self.amount.value() * 100))
        if mode == self.SET_TOTAL:
            next_cents = self.current_progress_cents + entered_cents
        else:
            next_cents = max(1, entered_cents - self.current_progress_cents)
        self._mode = mode
        self._update_mode_ui(next_cents)

    def _update_mode_ui(self, value_cents: int | None = None) -> None:
        if self._mode == self.SET_TOTAL:
            self.amount_label.setText(
                self._t("earnings.goal.adjust.amount.total", "New current total")
            )
            self.save_button.setText(
                self._t("earnings.goal.adjust.save.total", "Set current total")
            )
        else:
            self.amount_label.setText(
                self._t("earnings.goal.adjust.amount.add", "Amount to add")
            )
            self.save_button.setText(
                self._t("earnings.goal.adjust.save.add", "Add to goal")
            )
        if value_cents is not None:
            self.amount.setValue(value_cents / 100)
        self._update_amount_hint()

    def _update_amount_hint(self, *_args) -> None:
        entered_cents = int(round(self.amount.value() * 100))
        if self._mode == self.SET_TOTAL:
            difference_cents = entered_cents - self.current_progress_cents
            if difference_cents > 0:
                text = self._t(
                    "earnings.goal.adjust.hint.total",
                    "Current progress: {current}. The app will add {difference}.",
                    current=money(self.current_progress_cents),
                    difference=money(difference_cents),
                )
            else:
                text = self._t(
                    "earnings.goal.adjust.hint.total.invalid",
                    "Enter a total greater than the current {current}.",
                    current=money(self.current_progress_cents),
                )
            self.save_button.setEnabled(difference_cents > 0)
        else:
            text = self._t(
                "earnings.goal.adjust.hint.add",
                "Current progress: {current}. New progress: {total}.",
                current=money(self.current_progress_cents),
                total=money(self.current_progress_cents + entered_cents),
            )
            self.save_button.setEnabled(entered_cents > 0)
        self.amount_hint.setText(text)

    def _accept_if_valid(self) -> None:
        if self.save_button.isEnabled():
            self.accept()

    def values(self) -> tuple[str, int, str | None]:
        return (
            self._mode,
            int(round(self.amount.value() * 100)),
            " ".join(self.note.text().split()) or None,
        )


class QuestPickerDialog(QDialog):
    """Editable adaptive quest presets shown before a new session starts."""

    def __init__(self, service: EarningsManager, parent=None, translate=None):
        super().__init__(parent)
        self.service = service
        self.tr = translate or (lambda key, **kwargs: key.format(**kwargs))
        self._selected_kind: str | None = None
        self.setWindowTitle(self.tr("earnings.quest.choose.title"))
        self.setObjectName("earningsQuestPickerDialog")
        self.setModal(True)
        self.setFixedWidth(590)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["xl"], SPACING["xl"], SPACING["xl"], SPACING["xl"])
        layout.setSpacing(SPACING["md"])
        title = TitleLabel(self.tr("earnings.quest.choose.title"))
        intro = CaptionLabel(self.tr("earnings.quest.choose.body"))
        intro.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(intro)

        presets = service.quest_presets()
        self.quest_controls: dict[str, QWidget] = {}
        rows = (
            (
                QuestKind.SKU.value,
                self.tr("earnings.quest.sku.title"),
                self.tr("earnings.quest.sku.description"),
            ),
            (
                QuestKind.EARNINGS.value,
                self.tr("earnings.quest.earnings.title"),
                self.tr("earnings.quest.earnings.description"),
            ),
            (
                QuestKind.FOCUS.value,
                self.tr("earnings.quest.focus.title"),
                self.tr("earnings.quest.focus.description"),
            ),
        )
        for kind, heading, description in rows:
            section, section_layout = EarningsSettingsDialog._section(heading, description)
            controls = QHBoxLayout()
            controls.setContentsMargins(0, 0, 0, 0)
            controls.setSpacing(SPACING["sm"])
            if kind == QuestKind.EARNINGS.value:
                control = FluentDoubleSpinBox()
                control.setRange(0.01, 1_000_000.0)
                control.setDecimals(2)
                control.setPrefix("€")
                control.setValue(int(presets[kind]["target_value"]) / 100.0)
            else:
                control = FluentSpinBox()
                if kind == QuestKind.SKU.value:
                    control.setRange(1, 1000)
                    control.setSuffix(" SKU")
                    control.setValue(int(presets[kind]["target_value"]))
                else:
                    control.setRange(1, 24 * 60)
                    control.setSuffix(" min")
                    control.setValue(int(presets[kind]["target_value"]) // 60)
            control.setFixedHeight(SIZES["input_height"])
            control.setMinimumWidth(170)
            control.setAccessibleName(heading)
            choose = PrimaryPushButton(self.tr("earnings.quest.choose.action"))
            choose.setFixedHeight(SIZES["button_height"])
            choose.clicked.connect(lambda _=False, selected=kind: self._choose(selected))
            controls.addWidget(control)
            controls.addStretch(1)
            controls.addWidget(choose)
            section_layout.addLayout(controls)
            self.quest_controls[kind] = control
            layout.addWidget(section)

        footer = QHBoxLayout()
        footer.setSpacing(SPACING["sm"])
        self.no_quest_button = PushButton(self.tr("earnings.quest.none.action"))
        self.cancel_button = PushButton(self.tr("earnings.common.cancel"))
        self.no_quest_button.clicked.connect(self._choose_no_quest)
        self.cancel_button.clicked.connect(self.reject)
        footer.addWidget(self.no_quest_button)
        footer.addStretch(1)
        footer.addWidget(self.cancel_button)
        layout.addLayout(footer)
        qconfig.themeChangedFinished.connect(self._apply_theme)
        self._apply_theme()

    def _choose(self, kind: str) -> None:
        self._selected_kind = kind
        self.accept()

    def _choose_no_quest(self) -> None:
        self._selected_kind = None
        self.accept()

    def values(self) -> tuple[str | None, int | None]:
        kind = self._selected_kind
        if kind is None:
            return None, None
        control = self.quest_controls[kind]
        if kind == QuestKind.EARNINGS.value:
            return kind, int(round(control.value() * 100))
        if kind == QuestKind.FOCUS.value:
            return kind, int(control.value()) * 60
        return kind, int(control.value())

    def _apply_theme(self) -> None:
        dark = isDarkTheme()
        self.setStyleSheet(get_form_dialog_style(dark, self.objectName()))
        style = get_dialog_section_style(dark)
        for section in self.findChildren(QWidget, "earningsDialogSection"):
            section.setStyleSheet(style)


class SessionRecapDialog(QDialog):
    """Positive session summary with qualified personal-record callouts."""

    def __init__(self, recap: dict[str, Any], parent=None, translate=None):
        super().__init__(parent)
        self.recap = recap
        self.tr = translate or (lambda key, **kwargs: key.format(**kwargs))
        self.start_another = False
        self.setWindowTitle(self.tr("earnings.recap.title"))
        self.setObjectName("earningsSessionRecapDialog")
        self.setModal(True)
        self.setFixedWidth(610)

        session = recap["session"]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["xl"], SPACING["xl"], SPACING["xl"], SPACING["xl"])
        layout.setSpacing(SPACING["md"])
        title = TitleLabel(self.tr("earnings.recap.title"))
        subtitle = CaptionLabel(self.tr("earnings.recap.subtitle"))
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        metrics = QWidget()
        metrics.setObjectName("earningsDialogSection")
        metrics.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        grid = QGridLayout(metrics)
        grid.setContentsMargins(SPACING["md"], SPACING["md"], SPACING["md"], SPACING["md"])
        grid.setHorizontalSpacing(SPACING["lg"])
        grid.setVerticalSpacing(SPACING["md"])
        values = (
            (self.tr("earnings.recap.time"), duration(session["elapsed_seconds"])),
            (self.tr("earnings.recap.skus"), f"{session['product_count']:,}"),
            (self.tr("earnings.recap.earnings"), money(session["earned_cents"])),
            (
                self.tr("earnings.recap.hourly"),
                money(session["hourly_cents"]) if session["hourly_cents"] is not None else "—",
            ),
        )
        for index, (label_text, value_text) in enumerate(values):
            box = QVBoxLayout()
            box.setSpacing(2)
            box.addWidget(CaptionLabel(label_text))
            box.addWidget(StrongBodyLabel(value_text))
            grid.addLayout(box, index // 2, index % 2)
        layout.addWidget(metrics)

        quest = recap.get("quest")
        if quest is None:
            quest_text = self.tr("earnings.recap.quest.none")
        elif quest["complete"]:
            quest_text = self.tr("earnings.recap.quest.complete")
        else:
            quest_text = self.tr(
                "earnings.recap.quest.progress", percent=int(round(quest["percent"]))
            )
        self.quest_result = BodyLabel(quest_text)
        self.quest_result.setWordWrap(True)
        layout.addWidget(self.quest_result)

        contribution = recap.get("goal_contribution")
        if contribution is not None:
            goal_text = self.tr(
                "earnings.recap.goal_contribution",
                amount=money(contribution["contribution_cents"]),
            )
            goal_label = CaptionLabel(goal_text)
            goal_label.setWordWrap(True)
            layout.addWidget(goal_label)

        callouts = recap.get("record_callouts", [])
        if callouts:
            records = QWidget()
            records.setObjectName("earningsDialogSection")
            records.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            record_layout = QVBoxLayout(records)
            record_layout.setContentsMargins(SPACING["md"], SPACING["md"], SPACING["md"], SPACING["md"])
            record_layout.setSpacing(SPACING["sm"])
            record_layout.addWidget(StrongBodyLabel(self.tr("earnings.recap.records.title")))
            for record in callouts:
                value = record["value"]
                rendered = f"{int(value):,}" if record["key"] == "products" else money(value)
                key = f"earnings.recap.records.{record['key']}.{record['status']}"
                label = BodyLabel(self.tr(key, value=rendered))
                label.setWordWrap(True)
                record_layout.addWidget(label)
            layout.addWidget(records)

        footer = QHBoxLayout()
        footer.setSpacing(SPACING["sm"])
        footer.addStretch(1)
        another = PushButton(self.tr("earnings.recap.start_another"))
        done = PrimaryPushButton(self.tr("earnings.recap.done"))
        another.clicked.connect(self._start_another)
        done.clicked.connect(self.accept)
        footer.addWidget(another)
        footer.addWidget(done)
        layout.addLayout(footer)
        qconfig.themeChangedFinished.connect(self._apply_theme)
        self._apply_theme()

    def _start_another(self) -> None:
        self.start_another = True
        self.accept()

    def _apply_theme(self) -> None:
        dark = isDarkTheme()
        self.setStyleSheet(get_form_dialog_style(dark, self.objectName()))
        section_style = get_dialog_section_style(dark)
        for section in self.findChildren(QWidget, "earningsDialogSection"):
            section.setStyleSheet(section_style)


class EarningsSettingsDialog(QDialog):
    def __init__(self, service: EarningsManager, parent=None, translate=None):
        super().__init__(parent)
        self.service = service
        self.tr = translate or (lambda key, **kwargs: key.format(**kwargs))
        self.setWindowTitle("Earnings settings")
        self.setObjectName("earningsSettingsDialog")
        self.setModal(True)
        self.setFixedWidth(680)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"])
        layout.setSpacing(SPACING["md"])

        payout_section, payout_layout = self._section(
            "Product payouts",
            "New earnings use these amounts. Existing records are never changed retroactively.",
        )
        payout_grid = QGridLayout()
        payout_grid.setContentsMargins(0, 0, 0, 0)
        payout_grid.setHorizontalSpacing(SPACING["md"])
        payout_grid.setVerticalSpacing(SPACING["md"])
        self.rates = {}
        self._settings_controls = []
        for column, (key, label) in enumerate(PRODUCT_TYPES):
            spin = FluentDoubleSpinBox()
            spin.setRange(0, 10000)
            spin.setDecimals(2)
            spin.setPrefix("€")
            spin.setValue(service.get_rate_cents(key) / 100)
            self._prepare_spin(spin, f"{label} payout")
            self.rates[key] = spin
            payout_grid.addWidget(self._field(f"{label} payout", spin), 0, column)
        payout_layout.addLayout(payout_grid)
        layout.addWidget(payout_section)

        target_section, target_layout = self._section(
            "Performance targets",
            "Use zero to disable an individual target.",
        )
        target_grid = QGridLayout()
        target_grid.setContentsMargins(0, 0, 0, 0)
        target_grid.setHorizontalSpacing(SPACING["md"])
        target_grid.setVerticalSpacing(SPACING["md"])
        targets = service.performance_targets()
        self.daily_money = self._money_spin(targets["daily_earning_goal_cents"])
        self.weekly_money = self._money_spin(targets["weekly_earning_goal_cents"])
        self.daily_minutes = self._minutes_spin(targets["daily_work_goal_minutes"])
        self.weekly_minutes = self._minutes_spin(targets["weekly_work_goal_minutes"])
        target_fields = (
            ("Daily earnings target", self.daily_money),
            ("Weekly earnings target", self.weekly_money),
            ("Daily work target", self.daily_minutes),
            ("Weekly work target", self.weekly_minutes),
        )
        for index, (label, control) in enumerate(target_fields):
            self._prepare_spin(control, label)
            target_grid.addWidget(self._field(label, control), index // 2, index % 2)
        target_layout.addLayout(target_grid)
        layout.addWidget(target_section)

        schedule_section, schedule_layout = self._section(
            "Income projection schedule",
            "This schedule is used only for forward-looking projections.",
        )
        schedule_grid = QGridLayout()
        schedule_grid.setContentsMargins(0, 0, 0, 0)
        schedule_grid.setHorizontalSpacing(SPACING["md"])
        schedule_grid.setVerticalSpacing(SPACING["md"])
        schedule = service.work_schedule()
        self.workday_hours = FluentDoubleSpinBox()
        self.workday_hours.setRange(0.25, 24.0)
        self.workday_hours.setDecimals(2)
        self.workday_hours.setSingleStep(0.25)
        self.workday_hours.setSuffix(" h")
        self.workday_hours.setValue(schedule["workday_minutes"] / 60.0)
        self.workdays_per_week = FluentSpinBox()
        self.workdays_per_week.setRange(1, 7)
        self.workdays_per_week.setSuffix(" days")
        self.workdays_per_week.setValue(schedule["workdays_per_week"])
        for column, (label, control) in enumerate(
            (("Normal workday", self.workday_hours), ("Workdays per week", self.workdays_per_week))
        ):
            self._prepare_spin(control, label)
            schedule_grid.addWidget(self._field(label, control), 0, column)
        schedule_layout.addLayout(schedule_grid)
        layout.addWidget(schedule_section)

        feedback_section, feedback_layout = self._section(
            self.tr("earnings.settings.feedback.title"),
            self.tr("earnings.settings.feedback.description"),
        )
        feedback_row = QHBoxLayout()
        feedback_row.setContentsMargins(0, 0, 0, 0)
        feedback_row.setSpacing(SPACING["lg"])
        engagement = service.engagement_settings()
        self.celebration_animations = CheckBox(
            self.tr("earnings.settings.feedback.animations")
        )
        self.celebration_sound = CheckBox(
            self.tr("earnings.settings.feedback.sound")
        )
        self.celebration_animations.setChecked(engagement["animations_enabled"])
        self.celebration_sound.setChecked(engagement["sound_enabled"])
        self.celebration_animations.setAccessibleName(
            self.tr("earnings.settings.feedback.animations")
        )
        self.celebration_sound.setAccessibleName(
            self.tr("earnings.settings.feedback.sound")
        )
        feedback_row.addWidget(self.celebration_animations)
        feedback_row.addWidget(self.celebration_sound)
        self.sound_volume_title = CaptionLabel(
            self.tr("earnings.settings.feedback.volume")
        )
        self.sound_volume = QSlider(Qt.Orientation.Horizontal)
        self.sound_volume.setRange(0, 100)
        self.sound_volume.setSingleStep(5)
        self.sound_volume.setPageStep(10)
        self.sound_volume.setValue(service.celebration_sound_volume())
        self.sound_volume.setAccessibleName(
            self.tr("earnings.settings.feedback.volume")
        )
        self.sound_volume_value = CaptionLabel("")
        self.sound_volume_value.setMinimumWidth(44)
        self.sound_volume_value.setAlignment(Qt.AlignmentFlag.AlignRight)

        def _update_volume(value: int) -> None:
            self.sound_volume_value.setText(
                self.tr("earnings.settings.feedback.volume.value", value=int(value))
            )

        self.sound_volume.valueChanged.connect(_update_volume)
        self.celebration_sound.toggled.connect(self.sound_volume.setEnabled)
        self.celebration_sound.toggled.connect(self.sound_volume_title.setEnabled)
        self.celebration_sound.toggled.connect(self.sound_volume_value.setEnabled)
        self.sound_volume.setEnabled(self.celebration_sound.isChecked())
        self.sound_volume_title.setEnabled(self.celebration_sound.isChecked())
        self.sound_volume_value.setEnabled(self.celebration_sound.isChecked())
        _update_volume(self.sound_volume.value())
        feedback_row.addSpacing(SPACING["sm"])
        feedback_row.addWidget(self.sound_volume_title)
        feedback_row.addWidget(self.sound_volume, 1)
        feedback_row.addWidget(self.sound_volume_value)
        feedback_layout.addLayout(feedback_row)
        layout.addWidget(feedback_section)
        self._settings_controls.extend(
            [self.celebration_animations, self.celebration_sound, self.sound_volume]
        )

        footer = QHBoxLayout()
        footer.setSpacing(SPACING["sm"])
        footer.addStretch(1)
        self.cancel_button = PushButton("Cancel")
        self.save_button = PrimaryPushButton("Save")
        for button in (self.cancel_button, self.save_button):
            button.setFixedHeight(SIZES["button_height"])
            button.setMinimumWidth(96)
        self.cancel_button.setAutoDefault(False)
        self.save_button.setAutoDefault(True)
        self.save_button.setDefault(True)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.save_button)
        layout.addLayout(footer)

        controls = self._settings_controls + [self.cancel_button, self.save_button]
        for current, following in zip(controls, controls[1:]):
            self.setTabOrder(current, following)
        qconfig.themeChangedFinished.connect(self._apply_theme)
        self._apply_theme()
        self.adjustSize()
        self.setFixedSize(680, min(640, self.sizeHint().height()))

    @staticmethod
    def _section(title: str, description: str):
        section = QWidget()
        section.setObjectName("earningsDialogSection")
        section.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(
            SPACING["md"], SPACING["md"], SPACING["md"], SPACING["md"]
        )
        layout.setSpacing(SPACING["sm"])
        heading = StrongBodyLabel(title)
        body = CaptionLabel(description)
        body.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(body)
        return section, layout

    @staticmethod
    def _field(label_text: str, control: QWidget) -> QWidget:
        wrapper = QWidget()
        wrapper.setObjectName("earningsDialogField")
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["sm"])
        label = CaptionLabel(label_text)
        label.setBuddy(control)
        layout.addWidget(label)
        layout.addWidget(control)
        return wrapper

    def _prepare_spin(self, spin, accessible_name: str) -> None:
        spin.setFixedHeight(SIZES["input_height"])
        spin.setAccessibleName(accessible_name)
        spin.setCustomFocusedBorderColor(
            COLORS["focus_ring_light"], COLORS["focus_ring_dark"]
        )
        self._settings_controls.append(spin)

    @staticmethod
    def _money_spin(cents):
        spin = FluentDoubleSpinBox()
        spin.setRange(0, 1_000_000)
        spin.setDecimals(2)
        spin.setPrefix("€")
        spin.setValue(cents / 100)
        return spin

    @staticmethod
    def _minutes_spin(minutes):
        spin = FluentSpinBox()
        spin.setRange(0, 10080)
        spin.setSuffix(" min")
        spin.setValue(minutes)
        return spin

    def _apply_theme(self):
        dark = isDarkTheme()
        self.setStyleSheet(get_form_dialog_style(dark, self.objectName()))
        section_style = get_dialog_section_style(dark)
        for section in self.findChildren(QWidget, "earningsDialogSection"):
            section.setStyleSheet(section_style)
        for spin in self._settings_controls:
            selector = "QDoubleSpinBox" if isinstance(spin, QDoubleSpinBox) else "QSpinBox"
            spin.setStyleSheet(get_form_input_style(dark, selector))
        self.cancel_button.setStyleSheet(get_dialog_button_style(dark, primary=False))
        self.save_button.setStyleSheet(get_dialog_button_style(dark, primary=True))

    def save(self):
        for key, spin in self.rates.items():
            self.service.set_rate_cents(key, int(round(spin.value() * 100)))
        self.service.set_performance_targets(
            daily_earning_goal_cents=int(round(self.daily_money.value() * 100)),
            weekly_earning_goal_cents=int(round(self.weekly_money.value() * 100)),
            daily_work_goal_minutes=self.daily_minutes.value(),
            weekly_work_goal_minutes=self.weekly_minutes.value(),
        )
        self.service.set_work_schedule(
            workday_minutes=int(round(self.workday_hours.value() * 60)),
            workdays_per_week=self.workdays_per_week.value(),
        )
        self.service.set_engagement_settings(
            animations_enabled=self.celebration_animations.isChecked(),
            sound_enabled=self.celebration_sound.isChecked(),
        )
        self.service.set_celebration_sound_volume(self.sound_volume.value())


class BrandNameDialog(QDialog):
    def __init__(self, current_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rename brand")
        self.setObjectName("earningsBrandNameDialog")
        self.setModal(True)
        self.setFixedWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["xl"], SPACING["xl"], SPACING["xl"], SPACING["xl"])
        layout.setSpacing(SPACING["sm"])
        label = BodyLabel("Brand name")
        self.name_input = LineEdit()
        self.name_input.setText(current_name)
        self.name_input.selectAll()
        self.name_input.setFixedHeight(SIZES["input_height"])
        self.name_input.setAccessibleName("Brand name")
        label.setBuddy(self.name_input)
        layout.addWidget(label)
        layout.addWidget(self.name_input)
        layout.addSpacing(SPACING["base"])
        footer = QHBoxLayout()
        footer.setSpacing(SPACING["sm"])
        footer.addStretch(1)
        self.cancel_button = PushButton("Cancel")
        self.save_button = PrimaryPushButton("Rename")
        for button in (self.cancel_button, self.save_button):
            button.setFixedHeight(SIZES["button_height"])
            button.setMinimumWidth(96)
        self.cancel_button.setAutoDefault(False)
        self.save_button.setDefault(True)
        self.save_button.setAutoDefault(True)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)
        self.name_input.returnPressed.connect(self.accept)
        self.name_input.textChanged.connect(
            lambda text: self.save_button.setEnabled(bool(text.strip()))
        )
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.save_button)
        layout.addLayout(footer)
        self.setTabOrder(self.name_input, self.cancel_button)
        self.setTabOrder(self.cancel_button, self.save_button)
        qconfig.themeChangedFinished.connect(self._apply_theme)
        self._apply_theme()
        self.adjustSize()
        self.setFixedSize(420, self.sizeHint().height())

    def _apply_theme(self):
        dark = isDarkTheme()
        self.setStyleSheet(get_form_dialog_style(dark, self.objectName()))
        self.name_input.setStyleSheet(get_form_input_style(dark, "LineEdit"))
        self.cancel_button.setStyleSheet(get_dialog_button_style(dark, primary=False))
        self.save_button.setStyleSheet(get_dialog_button_style(dark, primary=True))

    def value(self) -> str:
        return self.name_input.text().strip()


class BrandManagerDialog(QDialog):
    def __init__(self, service: EarningsManager, parent=None):
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("Manage earning brands")
        self.setObjectName("earningsBrandManagerDialog")
        self.setModal(True)
        self.resize(660, 520)
        self.setMinimumSize(620, 460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["xl"], SPACING["xl"], SPACING["xl"], SPACING["xl"])
        layout.setSpacing(SPACING["base"])

        header = QHBoxLayout()
        header_text = QVBoxLayout()
        header_text.setSpacing(SPACING["xs"])
        heading = StrongBodyLabel("Earning brands")
        description = CaptionLabel(
            "Custom brands can be renamed or archived. Built-in scraper brands are protected."
        )
        description.setWordWrap(True)
        header_text.addWidget(heading)
        header_text.addWidget(description)
        header.addLayout(header_text, 1)
        self.count_label = CaptionLabel("")
        header.addWidget(self.count_label, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        add_section = QWidget()
        add_section.setObjectName("earningsDialogSection")
        add_section.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        add_layout = QVBoxLayout(add_section)
        add_layout.setContentsMargins(
            SPACING["base"], SPACING["base"], SPACING["base"], SPACING["base"]
        )
        add_layout.setSpacing(SPACING["sm"])
        add_label = CaptionLabel("Add custom brand")
        add_layout.addWidget(add_label)
        add_row = QHBoxLayout()
        add_row.setSpacing(SPACING["sm"])
        self.new_name = LineEdit()
        self.new_name.setPlaceholderText("New brand name")
        self.new_name.setAccessibleName("New brand name")
        self.new_name.setFixedHeight(SIZES["input_height"])
        self.add_button = PrimaryPushButton("Add brand")
        self.add_button.setFixedHeight(SIZES["button_height"])
        self.add_button.setMinimumWidth(112)
        self.add_button.setEnabled(False)
        self.add_button.clicked.connect(self._add)
        self.new_name.returnPressed.connect(self._add)
        self.new_name.textChanged.connect(
            lambda text: self.add_button.setEnabled(bool(text.strip()))
        )
        add_row.addWidget(self.new_name, 1)
        add_row.addWidget(self.add_button)
        add_layout.addLayout(add_row)
        layout.addWidget(add_section)

        self.table = QTableWidget(0, 3)
        self.table.setObjectName("earningsBrandsTable")
        self.table.setAccessibleName("Earning brands")
        self.table.setHorizontalHeaderLabels(["Brand", "Type", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(SIZES["table_row_height"])
        self.table.setMinimumHeight(230)
        self.table.itemSelectionChanged.connect(self._update_actions)
        self.table.doubleClicked.connect(self._rename)
        layout.addWidget(self.table)

        actions = QHBoxLayout()
        actions.setSpacing(SPACING["sm"])
        self.rename_button = PushButton("Rename")
        self.archive_button = PushButton("Archive")
        for button in (self.rename_button, self.archive_button):
            button.setFixedHeight(SIZES["button_height"])
            button.setMinimumWidth(96)
        self.rename_button.clicked.connect(self._rename)
        self.archive_button.clicked.connect(self._archive)
        actions.addWidget(self.rename_button)
        actions.addWidget(self.archive_button)
        actions.addStretch()
        self.close_button = PushButton("Close")
        self.close_button.setFixedHeight(SIZES["button_height"])
        self.close_button.setMinimumWidth(96)
        self.close_button.clicked.connect(self.accept)
        actions.addWidget(self.close_button)
        layout.addLayout(actions)
        self.setTabOrder(self.new_name, self.add_button)
        self.setTabOrder(self.add_button, self.table)
        self.setTabOrder(self.table, self.rename_button)
        self.setTabOrder(self.rename_button, self.archive_button)
        self.setTabOrder(self.archive_button, self.close_button)
        qconfig.themeChangedFinished.connect(self._apply_theme)
        self._apply_theme()
        self._reload()

    def _reload(self):
        selected = self._selected()
        selected_id = selected["id"] if selected else None
        rows = self.service.list_brands(active_only=False)
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            item = QTableWidgetItem(row["name"])
            item.setData(Qt.ItemDataRole.UserRole, row)
            self.table.setItem(i, 0, item)
            type_item = QTableWidgetItem("Built-in scraper" if row["is_builtin"] else "Custom")
            status_item = QTableWidgetItem("Active" if row["is_active"] else "Archived")
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 1, type_item)
            self.table.setItem(i, 2, status_item)
            if row["id"] == selected_id:
                self.table.selectRow(i)
        if rows and self.table.currentRow() < 0:
            self.table.selectRow(0)
        self.count_label.setText(f"{len(rows)} brand{'s' if len(rows) != 1 else ''}")
        self._apply_row_theme()
        self._update_actions()

    def _selected(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _update_actions(self):
        row = self._selected()
        editable = bool(row and not row["is_builtin"])
        self.rename_button.setEnabled(editable)
        self.archive_button.setEnabled(bool(editable and row["is_active"]))
        if row and row["is_builtin"]:
            explanation = "Built-in scraper brands are protected"
            self.rename_button.setToolTip(explanation)
            self.archive_button.setToolTip(explanation)
        else:
            self.rename_button.setToolTip("Rename selected brand" if editable else "Select a custom brand")
            self.archive_button.setToolTip(
                "Archive selected brand" if editable and row["is_active"] else "Select an active custom brand"
            )

    def _add(self):
        try:
            self.service.add_brand(self.new_name.text())
            self.new_name.clear()
            self._reload()
        except Exception as error:
            QMessageBox.warning(self, "Could not add brand", str(error))

    def _rename(self, *_args):
        row = self._selected()
        if not row or row["is_builtin"]:
            return
        dialog = BrandNameDialog(row["name"], self)
        if dialog.exec():
            try:
                self.service.rename_brand(row["id"], dialog.value())
                self._reload()
            except Exception as error:
                QMessageBox.warning(self, "Could not rename brand", str(error))

    def _archive(self):
        row = self._selected()
        if not row or row["is_builtin"] or not row["is_active"]:
            return
        confirm = MessageBox(
            "Archive brand?",
            f"{row['name']} will no longer be available for new earnings. Existing history is preserved.",
            self,
        )
        confirm.yesButton.setText("Archive")
        if confirm.exec():
            try:
                self.service.archive_brand(row["id"])
                self._reload()
            except Exception as error:
                QMessageBox.warning(self, "Could not archive brand", str(error))

    def _apply_row_theme(self):
        dark = isDarkTheme()
        secondary = QColor(get_text_color(dark, "secondary"))
        active = QColor(get_status_text_color("success", dark))
        archived = QColor(get_text_color(dark, "tertiary"))
        for row in range(self.table.rowCount()):
            data = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            self.table.item(row, 1).setForeground(QBrush(secondary))
            self.table.item(row, 2).setForeground(QBrush(active if data["is_active"] else archived))

    def _apply_theme(self):
        dark = isDarkTheme()
        self.setStyleSheet(get_form_dialog_style(dark, self.objectName()))
        section_style = get_dialog_section_style(dark)
        for section in self.findChildren(QWidget, "earningsDialogSection"):
            section.setStyleSheet(section_style)
        self.new_name.setStyleSheet(get_form_input_style(dark, "LineEdit"))
        self.table.setStyleSheet(get_dialog_table_style(dark))
        self.add_button.setStyleSheet(get_dialog_button_style(dark, primary=True))
        self.rename_button.setStyleSheet(get_dialog_button_style(dark, primary=False))
        self.archive_button.setStyleSheet(get_dialog_danger_button_style(dark))
        self.close_button.setStyleSheet(get_dialog_button_style(dark, primary=False))
        self._apply_row_theme()


class UploadEarningsDialog(QDialog):
    """One compact review for saved regular or batch upload products."""

    def __init__(self, service: EarningsManager, items: list[dict[str, Any]], parent=None):
        super().__init__(parent)
        self.service = service
        self.items = [item for item in items if not item.get("processing_history_id") or not service.is_processing_imported(item["processing_history_id"])]
        self.setWindowTitle("Add saved products to earnings")
        self.resize(880, 420)
        layout = QVBoxLayout(self)
        label = BodyLabel("Review the saved products to count as earnings. Uncheck any test or unpaid item.")
        label.setWordWrap(True)
        layout.addWidget(label)
        self.table = QTableWidget(len(self.items), 5)
        self.table.setHorizontalHeaderLabels(["Include", "SKU", "Name", "Brand", "Type"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        brands = service.list_brands()
        for row, item in enumerate(self.items):
            include = QCheckBox()
            include.setChecked(True)
            self.table.setCellWidget(row, 0, include)
            sku = LineEdit()
            sku.setText(str(item.get("sku") or ""))
            self.table.setCellWidget(row, 1, sku)
            name = LineEdit()
            name.setText(str(item.get("product_name") or ""))
            self.table.setCellWidget(row, 2, name)
            brand = ComboBox()
            brand.addItem("No brand", userData=None)
            for candidate in brands:
                brand.addItem(candidate["name"], userData=candidate["id"])
            wanted = str(item.get("brand") or "")
            for index in range(brand.count()):
                if brand.itemText(index).casefold() == wanted.casefold():
                    brand.setCurrentIndex(index)
                    break
            self.table.setCellWidget(row, 3, brand)
            ptype = ComboBox()
            for key, product_label in PRODUCT_TYPES:
                ptype.addItem(product_label, userData=key)
            index = ptype.findData(item.get("product_type", ProductType.BICYCLE.value))
            ptype.setCurrentIndex(max(0, index))
            self.table.setCellWidget(row, 4, ptype)
        layout.addWidget(self.table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save_entries(self) -> int:
        count = 0
        for row, item in enumerate(self.items):
            include = self.table.cellWidget(row, 0)
            if not include.isChecked():
                continue
            sku = self.table.cellWidget(row, 1).text().strip()
            if not sku:
                continue
            self.service.create_entry(
                sku, self.table.cellWidget(row, 4).currentData(),
                product_name=self.table.cellWidget(row, 2).text().strip() or None,
                brand_id=self.table.cellWidget(row, 3).currentData(),
                source=item.get("source", "upload"),
                processing_history_id=item.get("processing_history_id"),
            )
            count += 1
        return count

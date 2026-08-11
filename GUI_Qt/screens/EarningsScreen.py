"""Earnings tracker UI: entries, timer, goals, forecasts, and exports."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
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
    QMenu,
    QMessageBox,
    QProgressBar,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTabBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ComboBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    MessageBox,
    PrimaryPushButton,
    PushButton,
    ScrollArea,
    StrongBodyLabel,
    TitleLabel,
    isDarkTheme,
    qconfig,
)

from GUI_Qt.styles.screen_theme import apply_screen_theme
from GUI_Qt.styles.theme_config import COLORS, FONTS, PADDINGS, RADII, SIZES, SPACING
from GUI_Qt.widgets.ResponsiveWidget import ResponsiveWidget
from Managers.EarningsManager import (
    ActiveGoalError,
    ActiveSessionError,
    EarningsManager,
    GoalStatus,
    ProductType,
)


PRODUCT_TYPES = (
    (ProductType.BICYCLE.value, "Bicycle"),
    (ProductType.FRAMESET.value, "Frameset"),
    (ProductType.OTHER.value, "Other"),
)


def money(cents: float | int | None) -> str:
    if cents is None:
        return "—"
    return f"€{float(cents) / 100:,.2f}"


def duration(seconds: float | int | None) -> str:
    seconds = max(0, int(seconds or 0))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def local_datetime(raw: str | None) -> str:
    if not raw:
        return ""
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


class EarningsChart(QWidget):
    """Compact theme-aware bar chart with hover values."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data: list[dict[str, Any]] = []
        self._bar_rects: list[QRectF] = []
        self.setMinimumHeight(160)
        self.setMouseTracking(True)

    def set_data(self, data: list[dict[str, Any]]) -> None:
        self.data = data
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = QColor(COLORS["text_primary_dark"] if isDarkTheme() else COLORS["text_primary_light"])
        secondary = QColor(COLORS["text_secondary"])
        accent = QColor(COLORS.get("primary", COLORS["space_indigo"]))
        grid = QColor(COLORS["border_dark"] if isDarkTheme() else COLORS["border_light"])
        plot = self.rect().adjusted(54, 16, -16, -42)
        self._bar_rects = []
        if not self.data:
            painter.setPen(secondary)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No earning data yet")
            return
        maximum = max(1, max(int(item.get("cents", 0)) for item in self.data))
        painter.setPen(QPen(grid, 1))
        for i in range(5):
            y = plot.bottom() - plot.height() * i / 4
            painter.drawLine(plot.left(), int(y), plot.right(), int(y))
            painter.setPen(secondary)
            painter.drawText(2, int(y) - 8, 48, 18, Qt.AlignmentFlag.AlignRight, money(maximum * i / 4))
            painter.setPen(QPen(grid, 1))
        slot = plot.width() / max(1, len(self.data))
        bar_width = max(3.0, min(28.0, slot * 0.66))
        label_step = max(1, math.ceil(len(self.data) / 10))
        for index, item in enumerate(self.data):
            value = int(item.get("cents", 0))
            height = plot.height() * value / maximum
            x = plot.left() + index * slot + (slot - bar_width) / 2
            rect = QRectF(x, plot.bottom() - height, bar_width, max(1.5, height))
            self._bar_rects.append(rect)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(accent)
            painter.drawRoundedRect(rect, 3, 3)
            if index % label_step == 0 or index == len(self.data) - 1:
                painter.setPen(text)
                painter.save()
                font = painter.font()
                font.setPointSize(8)
                painter.setFont(font)
                painter.drawText(
                    QRectF(x - slot / 2, plot.bottom() + 8, slot * 2, 24),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                    str(item.get("label", "")),
                )
                painter.restore()

    def mouseMoveEvent(self, event):  # noqa: N802
        point = event.position()
        for index, rect in enumerate(self._bar_rects):
            if rect.contains(point):
                item = self.data[index]
                QToolTip.showText(
                    event.globalPosition().toPoint(),
                    f"{item.get('label', '')}\n{money(item.get('cents', 0))} • {item.get('count', 0)} products",
                    self,
                )
                return
        QToolTip.hideText()


class MetricCard(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("earningsMetric")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 11)
        layout.setSpacing(3)
        self.title = CaptionLabel(title)
        self.title.setWordWrap(True)
        self.value = QLabel("—")
        self.value.setFont(QFont(FONTS["family"], 27, QFont.Weight.DemiBold))
        self.subtitle = CaptionLabel("")
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.subtitle)

    def set_values(self, value: str, subtitle: str = "") -> None:
        self.value.setText(value)
        self.subtitle.setText(subtitle)


class ProjectionMetric(QWidget):
    """Borderless value used inside the income-projection surface."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(68)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 10, 3)
        layout.setSpacing(2)
        self.title = CaptionLabel(title)
        self.value = QLabel("—")
        self.value.setFont(QFont(FONTS["family"], 22, QFont.Weight.DemiBold))
        self.subtitle = CaptionLabel("")
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.subtitle)

    def set_values(self, value: str, subtitle: str = "") -> None:
        self.value.setText(value)
        self.subtitle.setText(subtitle)
        self.setAccessibleName(f"{self.title.text()}: {value}. {subtitle}")


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
        self.when.setCalendarPopup(True)
        self.when.setDisplayFormat("yyyy-MM-dd HH:mm")
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
        if entry:
            self.sku.setText(entry["sku"])
            self.name.setText(entry.get("product_name") or "")
            idx = self.brand.findData(entry.get("brand_id"))
            self.brand.setCurrentIndex(max(0, idx))
            idx = self.type.findData(entry["product_type"])
            self.type.setCurrentIndex(max(0, idx))
            parsed = datetime.fromisoformat(entry["earned_at"].replace("Z", "+00:00")).astimezone()
            self.when.setDateTime(parsed)

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


class GoalDialog(QDialog):
    def __init__(self, goal=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit money goal" if goal else "Create money goal")
        self.setMinimumWidth(400)
        form = QFormLayout(self)
        self.amount = QDoubleSpinBox()
        self.amount.setRange(0.01, 1_000_000)
        self.amount.setDecimals(2)
        self.amount.setPrefix("€")
        self.deadline_enabled = QCheckBox("Use a deadline")
        self.deadline = QDateEdit()
        self.deadline.setCalendarPopup(True)
        self.deadline.setMinimumDate(datetime.now().date())
        self.deadline.setDate(datetime.now().date())
        self.deadline.setEnabled(False)
        self.deadline_enabled.toggled.connect(self.deadline.setEnabled)
        form.addRow("Target amount", self.amount)
        form.addRow(self.deadline_enabled)
        form.addRow("Deadline", self.deadline)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        if goal:
            self.amount.setValue(int(goal["target_cents"]) / 100)
            if goal.get("deadline_date"):
                self.deadline_enabled.setChecked(True)
                self.deadline.setDate(datetime.fromisoformat(goal["deadline_date"]).date())

    def values(self):
        return int(round(self.amount.value() * 100)), (
            self.deadline.date().toPython() if self.deadline_enabled.isChecked() else None
        )


class EarningsSettingsDialog(QDialog):
    def __init__(self, service: EarningsManager, parent=None):
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("Earnings settings")
        self.setMinimumWidth(480)
        form = QFormLayout(self)
        self.rates = {}
        for key, label in PRODUCT_TYPES:
            spin = QDoubleSpinBox()
            spin.setRange(0, 10000)
            spin.setDecimals(2)
            spin.setPrefix("€")
            spin.setValue(service.get_rate_cents(key) / 100)
            self.rates[key] = spin
            form.addRow(f"{label} payout", spin)
        targets = service.performance_targets()
        self.daily_money = self._money_spin(targets["daily_earning_goal_cents"])
        self.weekly_money = self._money_spin(targets["weekly_earning_goal_cents"])
        self.daily_minutes = self._minutes_spin(targets["daily_work_goal_minutes"])
        self.weekly_minutes = self._minutes_spin(targets["weekly_work_goal_minutes"])
        form.addRow("Daily earnings target", self.daily_money)
        form.addRow("Weekly earnings target", self.weekly_money)
        form.addRow("Daily work target", self.daily_minutes)
        form.addRow("Weekly work target", self.weekly_minutes)
        schedule = service.work_schedule()
        schedule_heading = StrongBodyLabel("Income projection schedule")
        form.addRow(schedule_heading)
        self.workday_hours = QDoubleSpinBox()
        self.workday_hours.setRange(0.25, 24.0)
        self.workday_hours.setDecimals(2)
        self.workday_hours.setSingleStep(0.25)
        self.workday_hours.setSuffix(" h")
        self.workday_hours.setValue(schedule["workday_minutes"] / 60.0)
        self.workdays_per_week = QSpinBox()
        self.workdays_per_week.setRange(1, 7)
        self.workdays_per_week.setSuffix(" days")
        self.workdays_per_week.setValue(schedule["workdays_per_week"])
        form.addRow("Normal workday", self.workday_hours)
        form.addRow("Workdays per week", self.workdays_per_week)
        note = CaptionLabel(
            "Set a target to zero to disable it. Income projections use the schedule above. "
            "Existing earning payouts never change retroactively."
        )
        note.setWordWrap(True)
        form.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    @staticmethod
    def _money_spin(cents):
        spin = QDoubleSpinBox()
        spin.setRange(0, 1_000_000)
        spin.setPrefix("€")
        spin.setValue(cents / 100)
        return spin

    @staticmethod
    def _minutes_spin(minutes):
        spin = QSpinBox()
        spin.setRange(0, 10080)
        spin.setSuffix(" min")
        spin.setValue(minutes)
        return spin

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


class BrandManagerDialog(QDialog):
    def __init__(self, service: EarningsManager, parent=None):
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("Manage earning brands")
        self.resize(540, 430)
        layout = QVBoxLayout(self)
        add_row = QHBoxLayout()
        self.new_name = LineEdit()
        self.new_name.setPlaceholderText("New brand name")
        add = PrimaryPushButton("Add brand")
        add.clicked.connect(self._add)
        add_row.addWidget(self.new_name, 1)
        add_row.addWidget(add)
        layout.addLayout(add_row)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Brand", "Type", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)
        actions = QHBoxLayout()
        rename = PushButton("Rename")
        archive = PushButton("Archive")
        rename.clicked.connect(self._rename)
        archive.clicked.connect(self._archive)
        actions.addWidget(rename)
        actions.addWidget(archive)
        actions.addStretch()
        close = PushButton("Close")
        close.clicked.connect(self.accept)
        actions.addWidget(close)
        layout.addLayout(actions)
        self._reload()

    def _reload(self):
        rows = self.service.list_brands(active_only=False)
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            item = QTableWidgetItem(row["name"])
            item.setData(Qt.ItemDataRole.UserRole, row)
            self.table.setItem(i, 0, item)
            self.table.setItem(i, 1, QTableWidgetItem("Scraper" if row["is_builtin"] else "Custom"))
            self.table.setItem(i, 2, QTableWidgetItem("Active" if row["is_active"] else "Archived"))

    def _selected(self):
        row = self.table.currentRow()
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) if row >= 0 else None

    def _add(self):
        try:
            self.service.add_brand(self.new_name.text())
            self.new_name.clear()
            self._reload()
        except Exception as error:
            QMessageBox.warning(self, "Could not add brand", str(error))

    def _rename(self):
        row = self._selected()
        if not row:
            return
        from PySide6.QtWidgets import QInputDialog
        name, accepted = QInputDialog.getText(self, "Rename brand", "Brand name", text=row["name"])
        if accepted:
            try:
                self.service.rename_brand(row["id"], name)
                self._reload()
            except Exception as error:
                QMessageBox.warning(self, "Could not rename brand", str(error))

    def _archive(self):
        row = self._selected()
        if not row:
            return
        try:
            self.service.archive_brand(row["id"])
            self._reload()
        except Exception as error:
            QMessageBox.warning(self, "Could not archive brand", str(error))


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


class EarningsScreen(ResponsiveWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.service: EarningsManager = getattr(
            main_window, "earnings_manager", EarningsManager(main_window.db, main_window.settings)
        )
        self._entries: list[dict[str, Any]] = []
        self._sessions_count = 0
        self._last_expired_session = None
        self._init_ui()
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._timer_tick)
        self._tick_timer.start(500)
        qconfig.themeChangedFinished.connect(self._apply_theme)
        self.refresh_all()
        self.retranslate_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.scroll = ScrollArea(self)
        self.scroll.setWidgetResizable(True)
        root.addWidget(self.scroll)
        self.content = QWidget()
        self.scroll.setWidget(self.content)
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(24, 20, 28, 28)
        layout.setSpacing(10)

        self.header_layout = QGridLayout()
        self.header_layout.setHorizontalSpacing(8)
        self.header_layout.setVerticalSpacing(8)
        self.title = TitleLabel("Earnings")
        self.brands_button = PushButton("Brands")
        self.brands_button.setObjectName("earningsHeaderAction")
        self.brands_button.clicked.connect(self._manage_brands)
        self.settings_button = PushButton("Settings")
        self.settings_button.setObjectName("earningsHeaderAction")
        self.settings_button.clicked.connect(self._settings)
        self.export_button = PushButton("Export")
        self.export_button.setObjectName("earningsHeaderAction")
        menu = QMenu(self.export_button)
        self.export_filtered_action = menu.addAction("Export filtered records", lambda: self._export(True))
        self.export_all_action = menu.addAction("Export all records", lambda: self._export(False))
        self.export_button.setMenu(menu)
        self.header_action_buttons = (self.brands_button, self.settings_button, self.export_button)
        for button in self.header_action_buttons:
            button.setMinimumHeight(36)
            button.setMaximumHeight(36)
        self._arrange_header(compact=False)
        layout.addLayout(self.header_layout)

        self.section_tabs = QTabBar(self)
        self.section_tabs.setObjectName("earningsTabs")
        self.section_tabs.setDrawBase(False)
        self.section_tabs.setExpanding(False)
        self.section_tabs.setMovable(False)
        self.section_keys = ("logging", "analytics", "history")
        self.section_tabs.addTab("Logging")
        self.section_tabs.addTab("Analytics")
        self.section_tabs.addTab("History")
        layout.addWidget(self.section_tabs)

        self.logging_page = QWidget()
        self.logging_page.setObjectName("earningsLoggingPage")
        logging_layout = QVBoxLayout(self.logging_page)
        logging_layout.setContentsMargins(0, 0, 0, 0)
        logging_layout.setSpacing(10)

        self.metrics_layout = QGridLayout()
        self.metrics_layout.setSpacing(8)
        self.metric_today = MetricCard("Today")
        self.metric_week = MetricCard("This week")
        self.metric_all = MetricCard("All time")
        self.metric_rate = MetricCard("Effective hourly rate")
        self.metric_cards = (self.metric_today, self.metric_week, self.metric_all, self.metric_rate)
        self._arrange_metrics(compact=False)
        logging_layout.addLayout(self.metrics_layout)

        self.live_tools_layout = QGridLayout()
        self.live_tools_layout.setSpacing(10)
        self.entry_panel = self._entry_card()
        self.timer_panel = self._timer_card()
        self._arrange_live_tools(compact=False)
        logging_layout.addLayout(self.live_tools_layout)
        logging_layout.addStretch()
        layout.addWidget(self.logging_page)

        self.analytics_page = QWidget()
        self.analytics_page.setObjectName("earningsAnalyticsPage")
        analytics_layout = QVBoxLayout(self.analytics_page)
        analytics_layout.setContentsMargins(0, 0, 0, 0)
        analytics_layout.setSpacing(10)

        self.analytics_metrics_layout = QGridLayout()
        self.analytics_metrics_layout.setSpacing(8)
        self.analytics_total = MetricCard("Total earnings")
        self.analytics_products = MetricCard("Products")
        self.analytics_hours = MetricCard("Tracked hours")
        self.analytics_rate = MetricCard("Effective hourly rate")
        self.analytics_metric_cards = (
            self.analytics_total,
            self.analytics_products,
            self.analytics_hours,
            self.analytics_rate,
        )
        self._arrange_analytics_metrics(compact=False)
        analytics_layout.addLayout(self.analytics_metrics_layout)
        self.projection_panel = self._projection_card()
        analytics_layout.addWidget(self.projection_panel)
        analytics_layout.addWidget(self._analytics_card())

        self.analytics_config_layout = QGridLayout()
        self.analytics_config_layout.setSpacing(10)
        self.goal_panel = self._goal_card()
        self.performance_panel = self._performance_card()
        self._arrange_analytics_config(compact=False)
        analytics_layout.addLayout(self.analytics_config_layout)
        analytics_layout.addStretch()
        self.analytics_page.hide()
        layout.addWidget(self.analytics_page)

        self.history_page = QWidget()
        self.history_page.setObjectName("earningsHistoryPage")
        history_layout = QVBoxLayout(self.history_page)
        history_layout.setContentsMargins(0, 0, 0, 0)
        history_layout.setSpacing(8)
        self.history_panel = self._history_card()
        history_layout.addWidget(self.history_panel)
        history_layout.addStretch()
        self.history_page.hide()
        layout.addWidget(self.history_page)

        self.section_tabs.currentChanged.connect(
            lambda index: self._switch_section(self.section_keys[index])
        )
        self.section_tabs.setCurrentIndex(0)
        QTimer.singleShot(0, self.sku_input.setFocus)
        self._apply_theme()

    @staticmethod
    def _surface() -> QWidget:
        surface = QWidget()
        surface.setObjectName("earningsSurface")
        surface.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        return surface

    def _switch_section(self, route_key: str) -> None:
        if route_key not in self.section_keys:
            route_key = "logging"
        self.logging_page.setVisible(route_key == "logging")
        self.analytics_page.setVisible(route_key == "analytics")
        self.history_page.setVisible(route_key == "history")
        target_index = self.section_keys.index(route_key)
        if self.section_tabs.currentIndex() != target_index:
            self.section_tabs.setCurrentIndex(target_index)
        self.scroll.verticalScrollBar().setValue(0)
        if route_key == "analytics":
            self._refresh_analytics()
        elif route_key == "history":
            self._refresh_entries()
            self._refresh_sessions()
        else:
            QTimer.singleShot(0, self.sku_input.setFocus)

    @staticmethod
    def _clear_grid(layout: QGridLayout) -> None:
        while layout.count():
            layout.takeAt(0)

    def _arrange_metrics(self, *, compact: bool) -> None:
        self._clear_grid(self.metrics_layout)
        columns = 2 if compact else 4
        for index, card in enumerate(self.metric_cards):
            self.metrics_layout.addWidget(card, index // columns, index % columns)
        for column in range(4):
            self.metrics_layout.setColumnStretch(column, 1 if column < columns else 0)

    def _arrange_analytics_metrics(self, *, compact: bool) -> None:
        self._clear_grid(self.analytics_metrics_layout)
        columns = 2 if compact else 4
        for index, card in enumerate(self.analytics_metric_cards):
            self.analytics_metrics_layout.addWidget(card, index // columns, index % columns)
        for column in range(4):
            self.analytics_metrics_layout.setColumnStretch(column, 1 if column < columns else 0)

    def _arrange_projection_metrics(self, *, compact: bool) -> None:
        self._clear_grid(self.projection_metrics_layout)
        columns = 2 if compact else 4
        for index, metric in enumerate(self.projection_metrics):
            self.projection_metrics_layout.addWidget(metric, index // columns, index % columns)
        for column in range(4):
            self.projection_metrics_layout.setColumnStretch(column, 1 if column < columns else 0)

    def _arrange_analytics_config(self, *, compact: bool) -> None:
        self._clear_grid(self.analytics_config_layout)
        if compact:
            self.analytics_config_layout.addWidget(self.goal_panel, 0, 0)
            self.analytics_config_layout.addWidget(self.performance_panel, 1, 0)
            self.analytics_config_layout.setColumnStretch(0, 1)
            self.analytics_config_layout.setColumnStretch(1, 0)
        else:
            self.analytics_config_layout.addWidget(self.goal_panel, 0, 0)
            self.analytics_config_layout.addWidget(self.performance_panel, 0, 1)
            self.analytics_config_layout.setColumnStretch(0, 1)
            self.analytics_config_layout.setColumnStretch(1, 1)

    def _arrange_header(self, *, compact: bool) -> None:
        self._clear_grid(self.header_layout)
        for column in range(4):
            self.header_layout.setColumnStretch(column, 0)
        if compact:
            self.header_layout.addWidget(self.title, 0, 0, 1, 3)
            for column, button in enumerate(self.header_action_buttons):
                self.header_layout.addWidget(button, 1, column)
                self.header_layout.setColumnStretch(column, 1)
        else:
            self.header_layout.addWidget(self.title, 0, 0)
            self.header_layout.setColumnStretch(0, 1)
            for offset, button in enumerate(self.header_action_buttons, start=1):
                self.header_layout.addWidget(button, 0, offset)

    def _arrange_live_tools(self, *, compact: bool) -> None:
        self._clear_grid(self.live_tools_layout)
        if compact:
            self.live_tools_layout.addWidget(self.entry_panel, 0, 0)
            self.live_tools_layout.addWidget(self.timer_panel, 1, 0)
            self.live_tools_layout.setColumnStretch(0, 1)
            self.live_tools_layout.setColumnStretch(1, 0)
        else:
            self.live_tools_layout.addWidget(self.entry_panel, 0, 0)
            self.live_tools_layout.addWidget(self.timer_panel, 0, 1)
            self.live_tools_layout.setColumnStretch(0, 3)
            self.live_tools_layout.setColumnStretch(1, 2)

    def _on_breakpoint_changed(self, breakpoint: str):
        compact = breakpoint in ("xs", "sm")
        self._update_header_labels(compact=compact)
        self._arrange_header(compact=compact)
        self._arrange_metrics(compact=compact)
        self._arrange_analytics_metrics(compact=compact)
        self._arrange_projection_metrics(compact=compact)
        self._arrange_analytics_config(compact=compact)
        self._arrange_live_tools(compact=compact)
        self._arrange_history_toolbar(compact=compact)
        margins = (16, 14, 18, 20) if compact else (24, 20, 28, 28)
        self.content.layout().setContentsMargins(*margins)

    def _update_header_labels(self, *, compact: bool | None = None) -> None:
        if compact is None:
            compact = self.get_current_breakpoint() in ("xs", "sm")
        tr = self.main.i18n.tr
        labels = (
            (self.brands_button, tr("earnings.brands")),
            (self.settings_button, tr("earnings.settings")),
            (self.export_button, tr("earnings.export")),
        )
        for button, label in labels:
            button.setAccessibleName(label)
            button.setToolTip("")
            button.setText(label)
            button.setMinimumWidth(0)
            button.setMaximumWidth(16777215)

    def _entry_card(self):
        card = self._surface()
        grid = QGridLayout(card)
        grid.setContentsMargins(14, 10, 14, 12)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(7)
        self.entry_heading = StrongBodyLabel("Add earning")
        grid.addWidget(self.entry_heading, 0, 0, 1, 2)
        self.sku_input = LineEdit()
        self.sku_input.setPlaceholderText("SKU (required)")
        self.name_input = LineEdit()
        self.name_input.setPlaceholderText("Optional product name")
        self.brand_input = ComboBox()
        self.type_input = ComboBox()
        for key, label in PRODUCT_TYPES:
            self.type_input.addItem(label, userData=key)
        self.date_input = QDateTimeEdit(datetime.now())
        self.date_input.setCalendarPopup(True)
        self.date_input.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.add_button = PrimaryPushButton("Add earning")
        self.add_button.setObjectName("earningsPrimaryAction")
        self.add_button.setFixedSize(150, 38)
        self.add_button.clicked.connect(self._add_entry)
        self.sku_input.returnPressed.connect(self._add_entry)
        self.sku_label = CaptionLabel("SKU *")
        self.name_label = CaptionLabel("Product name")
        self.brand_label = CaptionLabel("Brand")
        self.type_label = CaptionLabel("Product type")
        self.date_label = CaptionLabel("Date and time")

        def field(label: QLabel, control: QWidget) -> QWidget:
            wrapper = QWidget()
            wrapper.setObjectName("earningsField")
            wrapper.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            wrapper.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            box = QVBoxLayout(wrapper)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(5)
            box.addWidget(label)
            box.addWidget(control)
            return wrapper

        grid.addWidget(field(self.sku_label, self.sku_input), 1, 0)
        grid.addWidget(field(self.name_label, self.name_input), 1, 1)
        grid.addWidget(field(self.brand_label, self.brand_input), 2, 0)
        grid.addWidget(field(self.type_label, self.type_input), 2, 1)
        grid.addWidget(field(self.date_label, self.date_input), 3, 0)
        button_wrapper = QWidget()
        button_wrapper.setObjectName("earningsField")
        button_wrapper.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        button_layout = QVBoxLayout(button_wrapper)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(5)
        button_layout.addSpacing(self.date_label.sizeHint().height())
        button_layout.addWidget(self.add_button, 0, Qt.AlignmentFlag.AlignRight)
        grid.addWidget(button_wrapper, 3, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        return card

    def _timer_card(self):
        card = self._surface()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(6)
        row = QHBoxLayout()
        self.timer_heading = StrongBodyLabel("Work timer")
        row.addWidget(self.timer_heading)
        row.addStretch()
        self.timer_mode = ComboBox()
        self.timer_mode.addItem("Stopwatch", userData="stopwatch")
        self.timer_mode.addItem("Countdown", userData="countdown")
        self.timer_mode.currentIndexChanged.connect(self._timer_mode_changed)
        row.addWidget(self.timer_mode)
        layout.addLayout(row)
        self.timer_display = QLabel("00:00:00")
        self.timer_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_display.setFont(QFont(FONTS["family"], 30, QFont.Weight.Bold))
        layout.addWidget(self.timer_display)
        self.timer_status = CaptionLabel("Ready")
        self.timer_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.timer_status)
        countdown = QHBoxLayout()
        self.countdown_minutes = QSpinBox()
        self.countdown_minutes.setRange(1, 24 * 60)
        self.countdown_minutes.setValue(25)
        self.countdown_minutes.setSuffix(" min")
        countdown.addWidget(self.countdown_minutes)
        for value in (25, 45, 60):
            button = PushButton(str(value))
            button.setToolTip(f"{value} minutes")
            button.clicked.connect(lambda _=False, minutes=value: self.countdown_minutes.setValue(minutes))
            countdown.addWidget(button)
        self.countdown_row = QWidget()
        self.countdown_row.setLayout(countdown)
        self.countdown_row.setVisible(False)
        layout.addWidget(self.countdown_row)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch()
        self.timer_start = PrimaryPushButton("Start", self)
        self.timer_pause = PrimaryPushButton("Pause", self)
        self.timer_finish = PushButton("Finish session", self)
        self.timer_reset = PushButton("Discard", self)
        self.timer_start.setObjectName("timerStart")
        self.timer_pause.setObjectName("timerStart")
        self.timer_finish.setObjectName("timerSecondary")
        self.timer_reset.setObjectName("earningsDangerAction")
        for button in (self.timer_start, self.timer_pause, self.timer_finish, self.timer_reset):
            button.setFixedHeight(36)
        self.timer_start.setMinimumWidth(96)
        self.timer_pause.setMinimumWidth(96)
        self.timer_finish.setMinimumWidth(132)
        self.timer_reset.setMinimumWidth(84)
        self.timer_start.clicked.connect(self._start_or_resume)
        self.timer_pause.clicked.connect(self._pause_timer)
        self.timer_finish.clicked.connect(self._finish_timer)
        self.timer_reset.clicked.connect(self._reset_timer)
        actions.addWidget(self.timer_start)
        actions.addWidget(self.timer_pause)
        actions.addWidget(self.timer_finish)
        actions.addWidget(self.timer_reset)
        actions.addStretch()
        layout.addLayout(actions)
        self._set_timer_action_labels("ready")
        return card

    def _projection_card(self):
        card = self._surface()
        card.setToolTip(
            "Estimates use your measured effective hourly rate and configured work schedule. "
            "They do not account for holidays, breaks, or changes in pace."
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)
        self.projection_heading = StrongBodyLabel("Income at your current pace")
        self.projection_basis = CaptionLabel("")
        self.projection_basis.setWordWrap(True)
        layout.addWidget(self.projection_heading)
        layout.addWidget(self.projection_basis)
        self.projection_metrics_layout = QGridLayout()
        self.projection_metrics_layout.setHorizontalSpacing(12)
        self.projection_metrics_layout.setVerticalSpacing(6)
        self.projection_day = ProjectionMetric("Work day")
        self.projection_week = ProjectionMetric("Work week")
        self.projection_month = ProjectionMetric("Average month")
        self.projection_year = ProjectionMetric("Work year")
        self.projection_metrics = (
            self.projection_day,
            self.projection_week,
            self.projection_month,
            self.projection_year,
        )
        self._arrange_projection_metrics(compact=False)
        layout.addLayout(self.projection_metrics_layout)
        return card

    def _goal_card(self):
        card = self._surface()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 9, 14, 10)
        layout.setSpacing(6)
        header = QHBoxLayout()
        self.goal_heading = StrongBodyLabel("Money goal and forecast")
        header.addWidget(self.goal_heading)
        header.addStretch()
        self.goal_create = PrimaryPushButton("Create goal")
        self.goal_create.setObjectName("earningsPrimaryAction")
        self.goal_create.setFixedSize(128, 34)
        self.goal_edit = PushButton("Edit")
        self.goal_archive = PushButton("Archive")
        self.goal_edit.setObjectName("earningsSecondaryAction")
        self.goal_archive.setObjectName("earningsSecondaryAction")
        self.goal_edit.setFixedHeight(34)
        self.goal_edit.setMinimumWidth(70)
        self.goal_archive.setFixedHeight(34)
        self.goal_archive.setMinimumWidth(82)
        self.goal_create.clicked.connect(self._create_goal)
        self.goal_edit.clicked.connect(self._edit_goal)
        self.goal_archive.clicked.connect(self._archive_goal)
        header.addWidget(self.goal_create)
        header.addWidget(self.goal_edit)
        header.addWidget(self.goal_archive)
        layout.addLayout(header)
        self.goal_title = BodyLabel("Create a money goal to see your forecast.")
        self.goal_title.setWordWrap(True)
        self.goal_progress = QProgressBar()
        self.goal_progress.setRange(0, 1000)
        self.goal_progress.setTextVisible(True)
        self.goal_forecast = CaptionLabel("")
        self.goal_forecast.setWordWrap(True)
        self.goal_deadline = CaptionLabel("")
        self.goal_deadline.setWordWrap(True)
        layout.addWidget(self.goal_title)
        layout.addWidget(self.goal_progress)
        layout.addWidget(self.goal_forecast)
        layout.addWidget(self.goal_deadline)
        return card

    def _analytics_card(self):
        card = self._surface()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(7)
        header = QHBoxLayout()
        self.analytics_heading = StrongBodyLabel("Earnings trend")
        header.addWidget(self.analytics_heading)
        header.addStretch()
        self.period = ComboBox()
        for label, key in (("Hourly", "hourly"), ("Daily", "daily"), ("Weekly", "weekly"),
                           ("Monthly", "monthly"), ("Quarterly", "quarterly"),
                           ("Yearly", "yearly"), ("All time", "all_time")):
            self.period.addItem(label, userData=key)
        self.period.setCurrentIndex(1)
        self.period.currentIndexChanged.connect(self._refresh_analytics)
        header.addWidget(self.period)
        layout.addLayout(header)
        self.chart = EarningsChart()
        self.analytics_empty = QWidget()
        self.analytics_empty.setObjectName("earningsEmptyState")
        self.analytics_empty.setMinimumHeight(118)
        self.analytics_empty.setMaximumHeight(132)
        empty_layout = QVBoxLayout(self.analytics_empty)
        empty_layout.setContentsMargins(12, 10, 12, 10)
        empty_layout.setSpacing(5)
        empty_layout.addStretch()
        self.analytics_empty_title = StrongBodyLabel("No earnings recorded yet")
        self.analytics_empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.analytics_empty_body = CaptionLabel(
            "Add your first earning to start seeing trends, hourly rate, brands, and product-type breakdowns."
        )
        self.analytics_empty_body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.analytics_empty_body.setWordWrap(True)
        self.analytics_empty_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.analytics_empty_add = PrimaryPushButton("Add earning")
        self.analytics_empty_add.setObjectName("earningsPrimaryAction")
        self.analytics_empty_add.setFixedSize(140, 34)
        self.analytics_empty_add.clicked.connect(self._go_to_logging)
        empty_layout.addWidget(self.analytics_empty_title)
        empty_layout.addWidget(self.analytics_empty_body)
        empty_layout.addWidget(self.analytics_empty_add, 0, Qt.AlignmentFlag.AlignCenter)
        empty_layout.addStretch()
        layout.addWidget(self.analytics_empty)
        layout.addWidget(self.chart)
        breakdown = QHBoxLayout()
        self.type_breakdown = CaptionLabel("")
        self.type_breakdown.setWordWrap(True)
        self.brand_breakdown = CaptionLabel("")
        self.brand_breakdown.setWordWrap(True)
        breakdown.addWidget(self.type_breakdown, 1)
        breakdown.addWidget(self.brand_breakdown, 1)
        layout.addLayout(breakdown)
        return card

    def _performance_card(self):
        card = self._surface()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 9, 14, 10)
        layout.setSpacing(6)
        header = QHBoxLayout()
        self.performance_heading = StrongBodyLabel("Daily and weekly targets")
        header.addWidget(self.performance_heading)
        header.addStretch()
        self.streak_label = CaptionLabel("")
        header.addWidget(self.streak_label)
        layout.addLayout(header)
        grid = QGridLayout()
        self.performance_widgets = {}
        definitions = (
            ("daily_money", "Daily earnings"),
            ("weekly_money", "Weekly earnings"),
            ("daily_time", "Daily work time"),
            ("weekly_time", "Weekly work time"),
        )
        for index, (key, label) in enumerate(definitions):
            wrapper = QWidget()
            box = QVBoxLayout(wrapper)
            box.setContentsMargins(0, 0, 0, 0)
            caption = CaptionLabel(label)
            progress = QProgressBar()
            progress.setRange(0, 1000)
            progress.setTextVisible(True)
            box.addWidget(caption)
            box.addWidget(progress)
            grid.addWidget(wrapper, index // 2, index % 2)
            self.performance_widgets[key] = (wrapper, progress)
        layout.addLayout(grid)
        self.no_performance_targets = CaptionLabel("Set targets in Earnings settings to see progress and streaks.")
        self.no_performance_targets.setWordWrap(True)
        layout.addWidget(self.no_performance_targets)
        return card

    def _history_card(self):
        card = QWidget()
        card.setObjectName("earningsFlatSection")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        heading_row = QHBoxLayout()
        self.history_heading = StrongBodyLabel("History")
        self.filtered_total = StrongBodyLabel("")
        heading_row.addWidget(self.history_heading)
        heading_row.addStretch()
        heading_row.addWidget(self.filtered_total)
        layout.addLayout(heading_row)

        self.search = LineEdit()
        self.search.setPlaceholderText("Search SKU, name, or brand")
        self.search.textChanged.connect(self._refresh_entries)
        self.filter_brand = ComboBox()
        self.filter_brand.currentIndexChanged.connect(self._refresh_entries)
        self.filter_type = ComboBox()
        self.filter_type.addItem("All types", userData=None)
        for key, label in PRODUCT_TYPES:
            self.filter_type.addItem(label, userData=key)
        self.filter_type.currentIndexChanged.connect(self._refresh_entries)
        self.filter_source = ComboBox()
        self.filter_source.addItem("All sources", userData=None)
        self.filter_source.addItem("Manual", userData="manual")
        self.filter_source.addItem("Regular upload", userData="regular_upload")
        self.filter_source.addItem("Batch upload", userData="batch_upload")
        self.filter_source.currentIndexChanged.connect(self._refresh_entries)
        self.filter_date = ComboBox()
        self.filter_date.addItem("All dates", userData=None)
        self.filter_date.addItem("Today", userData=1)
        self.filter_date.addItem("Last 7 days", userData=7)
        self.filter_date.addItem("Last 30 days", userData=30)
        self.filter_date.currentIndexChanged.connect(self._refresh_entries)
        self.clear_filters_button = PushButton("Clear filters")
        self.clear_filters_button.setObjectName("earningsSecondaryAction")
        self.clear_filters_button.clicked.connect(self._clear_history_filters)
        self.clear_filters_button.setVisible(False)
        self.edit_entry_button = PushButton("Edit")
        self.edit_entry_button.setObjectName("earningsSecondaryAction")
        self.edit_entry_button.setToolTip("Edit selected earning")
        self.edit_entry_button.clicked.connect(self._edit_selected_entry)
        self.edit_entry_button.setVisible(False)
        self.delete_entry_button = PushButton("Delete")
        self.delete_entry_button.setObjectName("earningsDangerAction")
        self.delete_entry_button.setToolTip("Delete selected earning")
        self.delete_entry_button.clicked.connect(self._delete_selected_entry)
        self.delete_entry_button.setVisible(False)
        for combo in (self.filter_brand, self.filter_type, self.filter_source, self.filter_date):
            combo.setMinimumWidth(90)
            combo.setMaximumWidth(150)
            combo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.edit_entry_button.setMinimumWidth(72)
        self.edit_entry_button.setMaximumWidth(110)
        self.edit_entry_button.setFixedHeight(34)
        self.delete_entry_button.setMinimumWidth(78)
        self.delete_entry_button.setMaximumWidth(110)
        self.delete_entry_button.setFixedHeight(34)
        self.clear_filters_button.setFixedHeight(34)

        self.history_toolbar = QWidget()
        self.history_toolbar.setObjectName("earningsToolbar")
        self.history_toolbar_layout = QGridLayout(self.history_toolbar)
        self.history_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        self.history_toolbar_layout.setHorizontalSpacing(8)
        self.history_toolbar_layout.setVerticalSpacing(8)
        self.history_toolbar_widgets = (
            self.search,
            self.filter_brand,
            self.filter_type,
            self.filter_source,
            self.filter_date,
            self.clear_filters_button,
            self.edit_entry_button,
            self.delete_entry_button,
        )
        self._arrange_history_toolbar(compact=False)
        layout.addWidget(self.history_toolbar)

        self.history_tabs = QTabWidget()
        self.entries_table = QTableWidget(0, 9)
        self.entries_table.setHorizontalHeaderLabels(
            ["Date", "SKU", "Name", "Brand", "Type", "Source", "Earning", "Session", "ID"]
        )
        self.entries_table.setColumnHidden(8, True)
        self.entries_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.entries_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.entries_table.setSortingEnabled(True)
        self.entries_table.doubleClicked.connect(self._edit_selected_entry)
        self.entries_table.itemSelectionChanged.connect(self._update_history_actions)
        self.entries_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        self.entries_empty_state = QWidget()
        self.entries_empty_state.setObjectName("earningsEmptyState")
        empty_layout = QVBoxLayout(self.entries_empty_state)
        empty_layout.setContentsMargins(16, 18, 16, 18)
        empty_layout.setSpacing(5)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.entries_empty_title = StrongBodyLabel("No earnings yet")
        self.entries_empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.entries_empty_body = CaptionLabel("Your logged products will appear here.")
        self.entries_empty_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.entries_empty_add = PrimaryPushButton("Add earning")
        self.entries_empty_add.setObjectName("earningsPrimaryAction")
        self.entries_empty_add.setFixedSize(140, 34)
        self.entries_empty_add.clicked.connect(self._go_to_logging)
        empty_layout.addWidget(self.entries_empty_title)
        empty_layout.addWidget(self.entries_empty_body)
        empty_layout.addWidget(self.entries_empty_add, 0, Qt.AlignmentFlag.AlignCenter)

        self.entries_stack = QStackedWidget()
        self.entries_stack.addWidget(self.entries_table)
        self.entries_stack.addWidget(self.entries_empty_state)
        entry_page = QWidget()
        entry_layout = QVBoxLayout(entry_page)
        entry_layout.setContentsMargins(0, 8, 0, 0)
        entry_layout.addWidget(self.entries_stack)
        self.history_tabs.addTab(entry_page, "Earnings")
        self.sessions_table = QTableWidget(0, 8)
        self.sessions_table.setHorizontalHeaderLabels(
            ["Started", "Mode", "Status", "Target", "Worked", "Products", "Earned", "€/hour"]
        )
        self.sessions_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sessions_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        self.sessions_empty_state = QWidget()
        self.sessions_empty_state.setObjectName("earningsEmptyState")
        sessions_empty_layout = QVBoxLayout(self.sessions_empty_state)
        sessions_empty_layout.setContentsMargins(16, 18, 16, 18)
        sessions_empty_layout.setSpacing(5)
        sessions_empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sessions_empty_title = StrongBodyLabel("No work sessions yet")
        self.sessions_empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sessions_empty_body = CaptionLabel("Start the timer to track your effective hourly rate.")
        self.sessions_empty_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sessions_empty_add = PrimaryPushButton("Open timer")
        self.sessions_empty_add.setObjectName("earningsPrimaryAction")
        self.sessions_empty_add.setFixedSize(140, 34)
        self.sessions_empty_add.clicked.connect(self._go_to_logging)
        sessions_empty_layout.addWidget(self.sessions_empty_title)
        sessions_empty_layout.addWidget(self.sessions_empty_body)
        sessions_empty_layout.addWidget(self.sessions_empty_add, 0, Qt.AlignmentFlag.AlignCenter)

        self.sessions_stack = QStackedWidget()
        self.sessions_stack.addWidget(self.sessions_table)
        self.sessions_stack.addWidget(self.sessions_empty_state)
        sessions_page = QWidget()
        sessions_layout = QVBoxLayout(sessions_page)
        sessions_layout.setContentsMargins(0, 8, 0, 0)
        sessions_layout.addWidget(self.sessions_stack)
        self.history_tabs.addTab(sessions_page, "Work sessions")
        self.history_tabs.setMinimumHeight(250)
        layout.addWidget(self.history_tabs)
        return card

    def _arrange_history_toolbar(self, *, compact: bool) -> None:
        layout = getattr(self, "history_toolbar_layout", None)
        if layout is None:
            return
        self._clear_grid(layout)
        if compact:
            layout.addWidget(self.search, 0, 0, 1, 3)
            layout.addWidget(self.clear_filters_button, 0, 3)
            layout.addWidget(self.edit_entry_button, 0, 4)
            layout.addWidget(self.delete_entry_button, 0, 5)
            layout.addWidget(self.filter_brand, 1, 0)
            layout.addWidget(self.filter_type, 1, 1)
            layout.addWidget(self.filter_source, 1, 2)
            layout.addWidget(self.filter_date, 1, 3, 1, 3)
            layout.setColumnStretch(0, 1)
            layout.setColumnStretch(1, 1)
            layout.setColumnStretch(2, 1)
            layout.setColumnStretch(3, 1)
            layout.setColumnStretch(4, 1)
            layout.setColumnStretch(5, 1)
        else:
            for column, widget in enumerate(self.history_toolbar_widgets):
                layout.addWidget(widget, 0, column)
            layout.setColumnStretch(0, 2)
            for column in range(1, len(self.history_toolbar_widgets)):
                layout.setColumnStretch(column, 0)

    def _go_to_logging(self) -> None:
        self._switch_section("logging")
        QTimer.singleShot(0, self.sku_input.setFocus)

    def _clear_history_filters(self) -> None:
        controls = (self.search, self.filter_brand, self.filter_type, self.filter_source, self.filter_date)
        for control in controls:
            control.blockSignals(True)
        self.search.clear()
        for combo in (self.filter_brand, self.filter_type, self.filter_source, self.filter_date):
            combo.setCurrentIndex(0)
        for control in controls:
            control.blockSignals(False)
        self._refresh_entries()

    def _history_filters_active(self) -> bool:
        return bool(
            self.search.text().strip()
            or self.filter_brand.currentData() is not None
            or self.filter_type.currentData() is not None
            or self.filter_source.currentData() is not None
            or self.filter_date.currentData() is not None
        )

    def _update_history_actions(self) -> None:
        selected = self._selected_entry() is not None
        self.edit_entry_button.setVisible(selected)
        self.delete_entry_button.setVisible(selected)

    # ------------------------------------------------------------- refresh/UI
    def refresh_all(self):
        self._reload_brands()
        self._refresh_metrics()
        self._refresh_goal()
        self._refresh_performance()
        self._refresh_analytics()
        self._refresh_entries()
        self._refresh_sessions()
        self._timer_tick()

    def _reload_brands(self):
        current = self.brand_input.currentData() if self.brand_input.count() else None
        self.brand_input.clear()
        self.brand_input.addItem("No brand", userData=None)
        self.filter_brand.blockSignals(True)
        self.filter_brand.clear()
        self.filter_brand.addItem("All brands", userData=None)
        for brand in self.service.list_brands():
            self.brand_input.addItem(brand["name"], userData=brand["id"])
            self.filter_brand.addItem(brand["name"], userData=brand["id"])
        index = self.brand_input.findData(current)
        self.brand_input.setCurrentIndex(max(0, index))
        self.filter_brand.blockSignals(False)

    def _refresh_metrics(self):
        values = self.service.summary()

        def activity_line(count: int, seconds: int, comparison: str = "") -> str:
            if not count and not seconds:
                return "No activity yet"
            parts = []
            if count:
                parts.append(f"{count} product{'s' if count != 1 else ''}")
            if seconds:
                parts.append(duration(seconds))
            if comparison:
                parts.append(comparison)
            return " • ".join(parts)

        today_delta = self._comparison(values["today_cents"], values["yesterday_cents"], "yesterday")
        week_delta = self._comparison(values["week_cents"], values["previous_week_cents"], "last week")
        self.metric_today.set_values(
            money(values["today_cents"]),
            activity_line(values["today_count"], values["today_seconds"], today_delta),
        )
        self.metric_week.set_values(
            money(values["week_cents"]),
            activity_line(values["week_count"], values["week_seconds"], week_delta),
        )
        self.metric_all.set_values(
            money(values["all_cents"]),
            activity_line(values["all_count"], values["all_seconds"]),
        )
        rate_subtitle = (
            "Earnings per tracked hour"
            if values["effective_hourly_cents"] is not None
            else "Track work time to calculate"
        )
        self.metric_rate.set_values(money(values["effective_hourly_cents"]), rate_subtitle)
        self.analytics_total.set_values(money(values["all_cents"]), "Across all recorded earnings")
        self.analytics_products.set_values(f"{values['all_count']:,}", "Paid products recorded")
        self.analytics_hours.set_values(f"{values['all_seconds'] / 3600:.1f} h", "Tracked work time")
        self.analytics_rate.set_values(money(values["effective_hourly_cents"]), rate_subtitle)
        self._refresh_projections(values)

    def _refresh_projections(self, summary: dict[str, Any] | None = None) -> None:
        summary = summary or self.service.summary()
        values = self.service.income_projections(
            effective_hourly_cents=summary["effective_hourly_cents"]
        )
        tr = self.main.i18n.tr

        def hours(value: float) -> str:
            return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.1f}"

        day_hours = hours(values["day_hours"])
        week_hours = hours(values["week_hours"])
        month_hours = hours(values["month_hours"])
        year_hours = hours(values["year_hours"])
        if values["effective_hourly_cents"] is None:
            self.projection_basis.setText(
                tr(
                    "earnings.projection.no_data",
                    day_hours=day_hours,
                    days=values["workdays_per_week"],
                )
            )
        else:
            self.projection_basis.setText(
                tr(
                    "earnings.projection.basis",
                    rate=money(values["effective_hourly_cents"]),
                    tracked_hours=f"{values['tracked_seconds'] / 3600:,.1f}",
                    day_hours=day_hours,
                    days=values["workdays_per_week"],
                )
            )
        self.projection_day.set_values(
            money(values["day_cents"]),
            tr("earnings.projection.day.subtitle", hours=day_hours),
        )
        self.projection_week.set_values(
            money(values["week_cents"]),
            tr(
                "earnings.projection.week.subtitle",
                days=values["workdays_per_week"],
                hours=week_hours,
            ),
        )
        self.projection_month.set_values(
            money(values["month_cents"]),
            tr("earnings.projection.month.subtitle", hours=month_hours),
        )
        self.projection_year.set_values(
            money(values["year_cents"]),
            tr("earnings.projection.year.subtitle", hours=year_hours),
        )

    @staticmethod
    def _comparison(current: int, previous: int, label: str) -> str:
        if previous <= 0:
            return ""
        delta = (current - previous) * 100.0 / previous
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        return f"{arrow} {abs(delta):.0f}% vs {label}"

    def _refresh_goal(self):
        forecast = self.service.goal_forecast()
        active = forecast is not None
        self.goal_create.setVisible(not active)
        self.goal_edit.setVisible(active)
        self.goal_archive.setVisible(active)
        self.goal_progress.setVisible(active)
        self.goal_forecast.setVisible(active)
        self.goal_deadline.setVisible(active)
        if not active:
            self.goal_panel.setMinimumHeight(92)
            self.goal_panel.setMaximumHeight(96)
            self.goal_title.setText("Create a money goal to see products and work-time predictions.")
            self.goal_forecast.setText("")
            self.goal_deadline.setText("")
            return
        self.goal_panel.setMinimumHeight(0)
        self.goal_panel.setMaximumHeight(16777215)
        goal = forecast["goal"]
        self.goal_title.setText(
            f"{money(forecast['earned_cents'])} of {money(goal['target_cents'])} • {money(forecast['remaining_cents'])} remaining"
        )
        self.goal_progress.setValue(int(round(forecast["percent"] * 10)))
        self.goal_progress.setFormat(f"{forecast['percent']:.1f}%")
        likely = str(forecast["likely_products"]) if forecast["likely_products"] is not None else "not enough history"
        hours = f"{forecast['estimated_hours']:.1f} work hours" if forecast["estimated_hours"] is not None else "track more time to unlock the time forecast"
        self.goal_forecast.setText(
            f"Likely: {likely} products and {hours}. Range: {forecast['optimistic_products']} products at the highest payout "
            f"to {forecast['conservative_products']} at the lowest. Based on {forecast['product_sample']} products "
            f"({forecast['product_basis'].replace('_', ' ')})."
        )
        deadline = forecast.get("deadline")
        if not deadline:
            self.goal_deadline.setText("")
        elif deadline["overdue"]:
            self.goal_deadline.setText(f"Deadline {deadline['date']} is overdue. Update the deadline or keep working toward the goal.")
        else:
            pace = f"{money(deadline['cents_per_day'])}/day or {money(deadline['cents_per_week'])}/week"
            if deadline["products_per_day"] is not None:
                pace += f" • {deadline['products_per_day']:.1f} products/day"
            if deadline["hours_per_week"] is not None:
                pace += f" • {deadline['hours_per_week']:.1f} work hours/week"
            self.goal_deadline.setText(f"Deadline {deadline['date']} • Required pace: {pace}")

    def _refresh_analytics(self):
        chart_data = self.service.trend_data(self.period.currentData() or "daily")
        has_data = any(
            int(item.get("cents", 0)) > 0 or int(item.get("count", 0)) > 0
            for item in chart_data
        )
        self.chart.set_data(chart_data if has_data else [])
        self.chart.setVisible(has_data)
        self.analytics_empty.setVisible(not has_data)
        self.type_breakdown.setVisible(has_data)
        self.brand_breakdown.setVisible(has_data)
        type_rows = self.service.type_breakdown()
        type_text = "Product types\n" + ("\n".join(
            f"{row['product_type'].title()}: {money(row['cents'])} ({row['count']})" for row in type_rows
        ) or "No data")
        brand_rows = self.service.brand_breakdown()
        brand_text = "Top brands\n" + ("\n".join(
            f"{row['brand']}: {money(row['cents'])} ({row['count']})" for row in brand_rows
        ) or "No data")
        self.type_breakdown.setText(type_text)
        self.brand_breakdown.setText(brand_text)

    def _refresh_performance(self):
        values = self.service.performance_progress()
        rows = {
            "daily_money": (values["daily_earned_cents"], values["daily_earning_goal_cents"], money),
            "weekly_money": (values["weekly_earned_cents"], values["weekly_earning_goal_cents"], money),
            "daily_time": (values["daily_work_minutes"], values["daily_work_goal_minutes"], lambda value: f"{float(value):.0f} min"),
            "weekly_time": (values["weekly_work_minutes"], values["weekly_work_goal_minutes"], lambda value: f"{float(value):.0f} min"),
        }
        any_enabled = False
        for key, (current, target, formatter) in rows.items():
            wrapper, progress = self.performance_widgets[key]
            enabled = target > 0
            wrapper.setVisible(enabled)
            if enabled:
                any_enabled = True
                ratio = min(1.0, float(current) / float(target))
                progress.setValue(int(round(ratio * 1000)))
                progress.setFormat(f"{formatter(current)} / {formatter(target)}")
        self.no_performance_targets.setVisible(not any_enabled)
        self.performance_panel.setMinimumHeight(0 if any_enabled else 92)
        self.performance_panel.setMaximumHeight(16777215 if any_enabled else 96)
        self.streak_label.setText(f"{values['streak']} day streak" if any_enabled else "")

    def _refresh_entries(self):
        if not hasattr(self, "entries_table"):
            return
        days = self.filter_date.currentData()
        start = datetime.now().astimezone() - timedelta(days=int(days)) if days else None
        if days == 1:
            local_now = datetime.now().astimezone()
            start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        self._entries = self.service.list_entries(
            search=self.search.text(), brand_id=self.filter_brand.currentData(),
            product_type=self.filter_type.currentData(), source=self.filter_source.currentData(),
            start=start,
        )
        self.entries_table.setSortingEnabled(False)
        self.entries_table.clearSelection()
        self.entries_table.setRowCount(len(self._entries))
        for row, entry in enumerate(self._entries):
            values = (
                local_datetime(entry["earned_at"]), entry["sku"], entry.get("product_name") or "",
                entry.get("brand_name") or "", entry["product_type"].title(),
                entry["source"].replace("_", " ").title(), money(entry["payout_cents"]),
                str(entry.get("session_id") or ""), str(entry["id"]),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, entry)
                self.entries_table.setItem(row, column, item)
        self.entries_table.setSortingEnabled(True)
        has_rows = bool(self._entries)
        self.entries_stack.setCurrentIndex(0 if has_rows else 1)
        self.entries_stack.setMaximumHeight(16777215 if has_rows else 210)
        filters_active = self._history_filters_active()
        tr = self.main.i18n.tr
        self.clear_filters_button.setVisible(filters_active)
        self.entries_empty_title.setText(
            tr("earnings.history.empty.filtered.title")
            if filters_active
            else tr("earnings.history.empty.title")
        )
        self.entries_empty_body.setText(
            tr("earnings.history.empty.filtered.body")
            if filters_active
            else tr("earnings.history.empty.body")
        )
        self.entries_empty_add.setVisible(not filters_active)
        self._update_history_actions()
        total = sum(int(row["payout_cents"]) for row in self._entries)
        self.filtered_total.setText(f"{len(self._entries)} records • {money(total)}")
        self._update_history_height()

    def _refresh_sessions(self):
        sessions = self.service.list_sessions()
        self._sessions_count = len(sessions)
        self.sessions_table.setRowCount(len(sessions))
        for row, session in enumerate(sessions):
            target = duration(session["target_seconds"]) if session["target_seconds"] else "—"
            values = (
                local_datetime(session["started_at"]), session["mode"].title(), session["status"].title(),
                target, duration(session["elapsed_seconds"]), session["product_count"],
                money(session["earned_cents"]), money(session["hourly_cents"]),
            )
            for column, value in enumerate(values):
                self.sessions_table.setItem(row, column, QTableWidgetItem(str(value)))
        has_sessions = bool(sessions)
        self.sessions_stack.setCurrentIndex(0 if has_sessions else 1)
        self.sessions_stack.setMaximumHeight(16777215 if has_sessions else 210)
        self._update_history_height()

    def _update_history_height(self) -> None:
        if not hasattr(self, "history_tabs"):
            return
        empty = not self._entries and self._sessions_count == 0
        self.history_tabs.setMaximumHeight(280 if empty else 16777215)

    # --------------------------------------------------------------- entries
    def _add_entry(self):
        sku = self.sku_input.text().strip()
        if not sku:
            InfoBar.warning(title="SKU required", content="Enter an SKU before adding the earning.", parent=self, position=InfoBarPosition.TOP)
            return
        if self.service.duplicate_sku_count(sku):
            dialog = MessageBox("Duplicate SKU", f"{sku} already exists. Add another paid record anyway?", self)
            dialog.yesButton.setText("Add anyway")
            dialog.cancelButton.setText("Cancel")
            if not dialog.exec():
                return
        try:
            self.service.create_entry(
                sku, self.type_input.currentData(), product_name=self.name_input.text(),
                brand_id=self.brand_input.currentData(), earned_at=self.date_input.dateTime().toPython(),
            )
            self.sku_input.clear()
            self.name_input.clear()
            self.date_input.setDateTime(datetime.now())
            self.refresh_all()
            InfoBar.success(title="Earning added", content=f"{sku} was added to your earnings.", parent=self, position=InfoBarPosition.TOP, duration=2500)
        except Exception as error:
            InfoBar.error(title="Could not add earning", content=str(error), parent=self, position=InfoBarPosition.TOP)

    def _selected_entry(self):
        row = self.entries_table.currentRow()
        item = self.entries_table.item(row, 0) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _edit_selected_entry(self):
        entry = self._selected_entry()
        if not entry:
            return
        dialog = EarningEntryDialog(self.service, entry, self)
        if dialog.exec():
            try:
                self.service.update_entry(entry["id"], **dialog.values())
                self.refresh_all()
            except Exception as error:
                QMessageBox.warning(self, "Could not update earning", str(error))

    def _delete_selected_entry(self):
        entry = self._selected_entry()
        if not entry:
            return
        dialog = MessageBox("Delete earning?", f"Delete {entry['sku']} and {money(entry['payout_cents'])} from your history?", self)
        dialog.yesButton.setText("Delete")
        if dialog.exec():
            self.service.delete_entry(entry["id"])
            self.refresh_all()

    # ---------------------------------------------------------------- timer
    def _timer_mode_changed(self):
        self.countdown_row.setVisible(self.timer_mode.currentData() == "countdown")

    def _set_timer_action_labels(self, state: str) -> None:
        tr = self.main.i18n.tr
        start_label = {
            "ready": tr("earnings.timer.start"),
            "paused": tr("earnings.timer.resume"),
            "running": tr("earnings.timer.running"),
            "overtime": tr("earnings.timer.overtime"),
        }.get(state, tr("earnings.timer.start"))
        controls = (
            (self.timer_start, start_label),
            (self.timer_pause, tr("earnings.timer.pause")),
            (self.timer_finish, tr("earnings.timer.finish")),
            (self.timer_reset, tr("earnings.timer.discard")),
        )
        for button, label in controls:
            button.setText(label)
            button.setToolTip(label)
            button.setAccessibleName(label)

    def _timer_tick(self):
        snapshot = self.service.timer_snapshot()
        active = snapshot is not None
        self.timer_mode.setEnabled(not active)
        self.countdown_minutes.setEnabled(not active)
        if not snapshot:
            self.timer_display.setText("00:00:00")
            self.timer_status.setText("Ready")
            self._set_timer_action_labels("ready")
            self.timer_start.setVisible(True)
            self.timer_pause.setVisible(False)
            self.timer_finish.setVisible(False)
            self.timer_reset.setVisible(False)
            self.timer_start.setEnabled(True)
            return
        shown = snapshot.remaining_seconds if snapshot.mode == "countdown" and not snapshot.allow_overtime else snapshot.elapsed_seconds
        self.timer_display.setText(duration(shown))
        self.timer_status.setText(
            "Overtime" if snapshot.allow_overtime and snapshot.status == "running" else snapshot.status.title()
        )
        finished_countdown = snapshot.mode == "countdown" and snapshot.remaining_seconds == 0 and not snapshot.allow_overtime
        action_state = "overtime" if finished_countdown else ("paused" if snapshot.status == "paused" else "running")
        self._set_timer_action_labels(action_state)
        self.timer_start.setVisible(snapshot.status == "paused")
        self.timer_pause.setVisible(snapshot.status == "running")
        self.timer_finish.setVisible(True)
        self.timer_reset.setVisible(True)
        if snapshot.expired and self._last_expired_session != snapshot.id:
            self._last_expired_session = snapshot.id
            InfoBar.info(title="Countdown complete", content="The timer paused at zero. Finish the session or start overtime.", parent=self, position=InfoBarPosition.TOP, duration=7000)
            self._refresh_sessions()

    def _start_or_resume(self):
        snapshot = self.service.timer_snapshot()
        try:
            if snapshot is None:
                target = self.countdown_minutes.value() * 60 if self.timer_mode.currentData() == "countdown" else None
                self.service.start_session(self.timer_mode.currentData(), target)
            else:
                overtime = snapshot.mode == "countdown" and snapshot.remaining_seconds == 0
                self.service.resume_session(overtime=overtime)
            self._timer_tick()
        except (ActiveSessionError, ValueError) as error:
            QMessageBox.warning(self, "Timer", str(error))

    def _pause_timer(self):
        self.service.pause_session()
        self._timer_tick()
        self._refresh_sessions()

    def _finish_timer(self):
        self.service.finish_session()
        self.refresh_all()

    def _reset_timer(self):
        dialog = MessageBox("Discard session?", "The work session will be removed. Linked earnings will remain and be detached.", self)
        dialog.yesButton.setText("Discard")
        if dialog.exec():
            self.service.reset_session()
            self.refresh_all()

    # ---------------------------------------------------------------- goals
    def _create_goal(self):
        dialog = GoalDialog(parent=self)
        if not dialog.exec():
            return
        target, deadline = dialog.values()
        try:
            self.service.create_goal(target, deadline)
            self.refresh_all()
        except ActiveGoalError:
            replace = MessageBox("Replace active goal?", "Archive the current goal and start this new one?", self)
            replace.yesButton.setText("Archive and replace")
            if replace.exec():
                self.service.create_goal(target, deadline, replace_status=GoalStatus.ARCHIVED)
                self.refresh_all()
        except Exception as error:
            QMessageBox.warning(self, "Could not create goal", str(error))

    def _edit_goal(self):
        goal = self.service.active_goal()
        if not goal:
            return
        dialog = GoalDialog(goal, self)
        if dialog.exec():
            target, deadline = dialog.values()
            self.service.update_goal(goal["id"], target, deadline)
            self.refresh_all()

    def _archive_goal(self):
        goal = self.service.active_goal()
        if not goal:
            return
        dialog = MessageBox("Archive goal?", "Its current result will be preserved in goal history.", self)
        dialog.yesButton.setText("Archive")
        if dialog.exec():
            self.service.close_goal(goal["id"], status=GoalStatus.ARCHIVED)
            self.refresh_all()

    # --------------------------------------------------------------- dialogs
    def _manage_brands(self):
        BrandManagerDialog(self.service, self).exec()
        self._reload_brands()

    def _settings(self):
        dialog = EarningsSettingsDialog(self.service, self)
        if dialog.exec():
            dialog.save()
            self.refresh_all()

    def prompt_upload_entries(self, items: list[dict[str, Any]]) -> int:
        dialog = UploadEarningsDialog(self.service, items, self)
        if not dialog.items or not dialog.exec():
            return 0
        try:
            count = dialog.save_entries()
            self.refresh_all()
            InfoBar.success(title="Earnings added", content=f"Added {count} saved product(s).", parent=self, position=InfoBarPosition.TOP, duration=3500)
            return count
        except Exception as error:
            QMessageBox.warning(self, "Could not add saved products", str(error))
            return 0

    # ---------------------------------------------------------------- export
    def _export(self, filtered: bool):
        default = str(Path.home() / "Desktop" / f"earnings_{datetime.now():%Y%m%d_%H%M%S}.xlsx")
        path, _ = QFileDialog.getSaveFileName(self, "Export earnings", default, "Excel workbook (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        entries = self._entries if filtered else self.service.list_entries()
        try:
            self._build_workbook(path, entries)
            InfoBar.success(title="Export complete", content=path, parent=self, position=InfoBarPosition.TOP, duration=5000)
        except Exception as error:
            InfoBar.error(title="Export failed", content=str(error), parent=self, position=InfoBarPosition.TOP)

    def _build_workbook(self, path: str, entries: list[dict[str, Any]]):
        workbook = openpyxl.Workbook()
        header_fill = PatternFill("solid", fgColor="2B2D42")
        header_font = Font(color="FFFFFF", bold=True)

        def sheet(name, headers):
            reuse_blank = (
                len(workbook.sheetnames) == 1
                and workbook.active.max_row == 1
                and workbook.active["A1"].value is None
            )
            ws = workbook.active if reuse_blank else workbook.create_sheet()
            ws.title = name
            if reuse_blank:
                for column, header in enumerate(headers, start=1):
                    ws.cell(1, column, header)
            else:
                ws.append(headers)
            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center")
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = f"A1:{openpyxl.utils.get_column_letter(len(headers))}1"
            return ws

        ws = sheet("Earnings", ["Date", "SKU", "Name", "Brand", "Product Type", "Source", "Earning", "Session ID"])
        for row in entries:
            ws.append([local_datetime(row["earned_at"]), row["sku"], row.get("product_name") or "", row.get("brand_name") or "",
                       row["product_type"].title(), row["source"], row["payout_cents"] / 100, row.get("session_id")])
            ws.cell(ws.max_row, 7).number_format = '€0.00'

        ws_sessions = sheet("Work Sessions", ["Started", "Completed", "Mode", "Status", "Target Hours", "Worked Hours", "Products", "Earned", "Effective €/Hour"])
        for row in self.service.list_sessions():
            ws_sessions.append([local_datetime(row["started_at"]), local_datetime(row.get("completed_at")), row["mode"], row["status"],
                                (row["target_seconds"] or 0) / 3600, row["elapsed_seconds"] / 3600,
                                row["product_count"], row["earned_cents"] / 100,
                                row["hourly_cents"] / 100 if row["hourly_cents"] is not None else None])
            ws_sessions.cell(ws_sessions.max_row, 8).number_format = '€0.00'
            ws_sessions.cell(ws_sessions.max_row, 9).number_format = '€0.00'

        ws_goals = sheet("Goal History", ["Started", "Deadline", "Status", "Target", "Completed", "Final Earned", "Products", "Tracked Hours"])
        for row in self.service.list_goals():
            ws_goals.append([local_datetime(row["started_at"]), row.get("deadline_date"), row["status"], row["target_cents"] / 100,
                             local_datetime(row.get("completed_at")), (row.get("final_earned_cents") or 0) / 100,
                             row.get("final_product_count") or 0, (row.get("final_tracked_seconds") or 0) / 3600])
            ws_goals.cell(ws_goals.max_row, 4).number_format = '€0.00'
            ws_goals.cell(ws_goals.max_row, 6).number_format = '€0.00'

        values = self.service.summary()
        ws_summary = sheet("Summary", ["Metric", "Value"])
        ws_summary.append(["Today earnings", values["today_cents"] / 100])
        ws_summary.append(["This week earnings", values["week_cents"] / 100])
        ws_summary.append(["All-time earnings", values["all_cents"] / 100])
        ws_summary.append(["All-time products", values["all_count"]])
        ws_summary.append(["Tracked hours", values["all_seconds"] / 3600])
        ws_summary.append(["Effective €/hour", values["effective_hourly_cents"] / 100 if values["effective_hourly_cents"] is not None else None])
        projections = self.service.income_projections(
            effective_hourly_cents=values["effective_hourly_cents"]
        )
        ws_summary.append(["Normal workday projection", projections["day_cents"] / 100 if projections["day_cents"] is not None else None])
        ws_summary.append(["Work-week projection", projections["week_cents"] / 100 if projections["week_cents"] is not None else None])
        ws_summary.append(["Average-month projection", projections["month_cents"] / 100 if projections["month_cents"] is not None else None])
        ws_summary.append(["Work-year projection", projections["year_cents"] / 100 if projections["year_cents"] is not None else None])
        ws_summary.append(["Normal workday hours", projections["day_hours"]])
        ws_summary.append(["Workdays per week", projections["workdays_per_week"]])
        for row in range(2, 5):
            ws_summary.cell(row, 2).number_format = '€0.00'
        for row in range(7, 12):
            ws_summary.cell(row, 2).number_format = '€0.00'
        for ws_current in workbook.worksheets:
            for column in ws_current.columns:
                letter = column[0].column_letter
                ws_current.column_dimensions[letter].width = min(45, max(12, max(len(str(cell.value or "")) for cell in column) + 2))
        workbook.save(path)

    def _apply_theme(self):
        apply_screen_theme(self, "EarningsScreen", scroll=self.scroll, content=self.content)
        dark = isDarkTheme()
        canvas = "#1B1E2B" if dark else "#E8EDF2"
        surface = "#242737" if dark else "#FFFFFF"
        metric_surface = "#292D40" if dark else "#FFFFFF"
        empty_surface = "#202332" if dark else "#F6F8FB"
        text = COLORS["text_primary_dark" if dark else "text_primary_light"]
        muted = COLORS["text_secondary_dark" if dark else "text_secondary_light"]
        outline = "#48506A" if dark else "#CBD5E1"
        card_border = "#343A52" if dark else "#DCE3EA"
        secondary_hover = "#34394E" if dark else "#EEF2F7"
        danger = "#FCA5A5" if dark else "#B42318"
        self.setStyleSheet(
            self.styleSheet()
            + f"""
            EarningsScreen QWidget#earningsSurface,
            EarningsScreen QWidget#earningsMetric {{
                background-color: {surface};
                border: 1px solid {card_border};
                border-radius: 12px;
            }}
            EarningsScreen QWidget#earningsMetric {{
                background-color: {metric_surface};
            }}
            EarningsScreen PrimaryPushButton#earningsPrimaryAction,
            EarningsScreen PrimaryPushButton#timerStart {{
                background-color: #2854C5;
                border: 1px solid #173B99;
                color: #FFFFFF;
                font-weight: 600;
                border-radius: 8px;
            }}
            EarningsScreen PrimaryPushButton#earningsPrimaryAction:hover,
            EarningsScreen PrimaryPushButton#timerStart:hover {{
                background-color: #1F46AD;
                border-color: #1F46AD;
            }}
            EarningsScreen PrimaryPushButton#earningsPrimaryAction:pressed,
            EarningsScreen PrimaryPushButton#timerStart:pressed {{
                background-color: #183889;
                border-color: #183889;
            }}
            EarningsScreen PrimaryPushButton#earningsPrimaryAction:disabled,
            EarningsScreen PrimaryPushButton#timerStart:disabled {{
                background-color: #94A3B8;
                border-color: #94A3B8;
                color: #F8FAFC;
            }}
            EarningsScreen PushButton#earningsSecondaryAction {{
                background: transparent;
                border: 1px solid {outline};
                color: {text};
                border-radius: 7px;
            }}
            EarningsScreen PushButton#earningsSecondaryAction:hover {{
                background-color: {secondary_hover};
                border-color: #2854C5;
            }}
            EarningsScreen PushButton#earningsHeaderAction {{
                background-color: {surface};
                border: 1px solid {outline};
                color: {muted};
                border-radius: 7px;
            }}
            EarningsScreen PushButton#earningsHeaderAction:hover {{
                background-color: {secondary_hover};
                border-color: #2854C5;
                color: {text};
            }}
            EarningsScreen PushButton#earningsDangerAction {{
                background: transparent;
                border: 1px solid {outline};
                color: {danger};
            }}
            EarningsScreen PushButton#earningsDangerAction:hover {{
                background-color: {'#442A32' if dark else '#FFF1F0'};
                border-color: {danger};
            }}
            EarningsScreen PushButton#timerSecondary {{
                background: transparent;
                border: 1px solid {outline};
                border-radius: 7px;
            }}
            EarningsScreen PushButton#timerSecondary:hover {{
                background-color: {secondary_hover};
                border-color: #2854C5;
            }}
            EarningsScreen QWidget#earningsEmptyState {{
                background-color: {empty_surface};
                border: 1px solid {card_border};
                border-radius: 10px;
            }}
            EarningsScreen QTabWidget::pane {{
                border: none;
                background: transparent;
            }}
            EarningsScreen QTableWidget {{
                border: 1px solid {outline};
                border-radius: 8px;
            }}
            """
        )
        self.content.setStyleSheet(f"background-color: {canvas};")
        self.scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background-color: {canvas}; }} "
            f"QScrollArea QWidget#qt_scrollarea_viewport {{ background-color: {canvas}; }}"
        )
        self.section_tabs.setStyleSheet(f"""
            QTabBar {{ background: transparent; border: none; }}
            QTabBar::tab {{
                background: transparent;
                color: {muted};
                border: none;
                border-bottom: 3px solid transparent;
                padding: 9px 20px 8px 20px;
                margin-right: 4px;
                font-weight: 500;
            }}
            QTabBar::tab:hover {{ background-color: {secondary_hover}; color: {text}; }}
            QTabBar::tab:selected {{
                background-color: {'#30364B' if dark else '#E4EBFA'};
                color: {'#FFFFFF' if dark else '#173B99'};
                border-bottom: 3px solid #2854C5;
                font-weight: 600;
            }}
        """)
        surface_style = f"""
            QWidget#earningsSurface {{
                background-color: {surface};
                border: 1px solid {card_border};
                border-radius: 12px;
            }}
        """
        metric_style = f"""
            QWidget#earningsMetric {{
                background-color: {metric_surface};
                border: 1px solid {card_border};
                border-radius: 12px;
            }}
        """
        for widget in self.findChildren(QWidget, "earningsSurface"):
            widget.setStyleSheet(surface_style)
        for widget in self.findChildren(QWidget, "earningsMetric"):
            widget.setStyleSheet(metric_style)
        for widget in self.findChildren(QWidget, "earningsField"):
            widget.setStyleSheet("QWidget#earningsField { background: transparent; border: none; }")
        for widget in self.findChildren(QWidget, "earningsEmptyState"):
            widget.setStyleSheet(
                f"QWidget#earningsEmptyState {{ background-color: {empty_surface}; border: 1px solid {card_border}; border-radius: 10px; }}"
            )

        primary_push_style = """
            PrimaryPushButton {
                background-color: #2854C5;
                border: 1px solid #173B99;
                border-radius: 8px;
                color: #FFFFFF;
                font-weight: 600;
                padding-left: 16px;
                padding-right: 16px;
            }
            PrimaryPushButton:hover { background-color: #1F46AD; border-color: #1F46AD; }
            PrimaryPushButton:pressed { background-color: #183889; border-color: #183889; }
            PrimaryPushButton:disabled { background-color: #94A3B8; border-color: #94A3B8; color: #F8FAFC; }
        """
        for button in (
            self.add_button,
            self.goal_create,
            self.analytics_empty_add,
            self.entries_empty_add,
            self.sessions_empty_add,
            self.timer_start,
            self.timer_pause,
        ):
            button.setStyleSheet(primary_push_style)
        secondary_style = f"""
            PushButton {{ background: transparent; border: 1px solid {outline}; border-radius: 7px; color: {text}; padding-left: 12px; padding-right: 12px; }}
            PushButton:hover {{ background-color: {secondary_hover}; border-color: #2854C5; }}
        """
        for button in (
            self.goal_edit,
            self.goal_archive,
            self.clear_filters_button,
            self.edit_entry_button,
            self.timer_finish,
        ):
            button.setStyleSheet(secondary_style)
        danger_style = f"""
            PushButton {{ background: transparent; border: 1px solid {outline}; border-radius: 7px; color: {danger}; padding-left: 12px; padding-right: 12px; }}
            PushButton:hover {{ background-color: {'#442A32' if dark else '#FFF1F0'}; border-color: {danger}; }}
        """
        self.delete_entry_button.setStyleSheet(danger_style)
        self.timer_reset.setStyleSheet(danger_style)
        header_style = f"""
            PushButton {{ background-color: {surface}; border: 1px solid {outline}; border-radius: 7px; color: {text}; padding-left: 12px; padding-right: 12px; }}
            PushButton:hover {{ background-color: {secondary_hover}; border-color: #2854C5; color: {text}; }}
        """
        for button in (self.brands_button, self.settings_button, self.export_button):
            button.setStyleSheet(header_style)
        self.chart.update()

    def retranslate_ui(self):
        tr = self.main.i18n.tr
        self.title.setText(tr("earnings.title"))
        self._update_header_labels()
        self.export_filtered_action.setText(tr("earnings.export.filtered"))
        self.export_all_action.setText(tr("earnings.export.all"))
        self.section_tabs.setTabText(0, tr("earnings.tab.logging"))
        self.section_tabs.setTabText(1, tr("earnings.tab.analytics"))
        self.section_tabs.setTabText(2, tr("earnings.tab.history"))
        self.metric_today.title.setText(tr("earnings.metric.today"))
        self.metric_week.title.setText(tr("earnings.metric.week"))
        self.metric_all.title.setText(tr("earnings.metric.all"))
        self.metric_rate.title.setText(tr("earnings.metric.rate"))
        self.analytics_total.title.setText(tr("earnings.metric.total_earnings"))
        self.analytics_products.title.setText(tr("earnings.metric.products"))
        self.analytics_hours.title.setText(tr("earnings.metric.hours"))
        self.analytics_rate.title.setText(tr("earnings.metric.rate"))
        self.entry_heading.setText(tr("earnings.add.title"))
        self.add_button.setText(tr("earnings.add.action"))
        self.timer_heading.setText(tr("earnings.timer.title"))
        self.goal_heading.setText(tr("earnings.goal.title"))
        self.performance_heading.setText(tr("earnings.performance.title"))
        self.analytics_heading.setText(tr("earnings.analytics.title"))
        self.projection_heading.setText(tr("earnings.projection.title"))
        self.projection_day.title.setText(tr("earnings.projection.day"))
        self.projection_week.title.setText(tr("earnings.projection.week"))
        self.projection_month.title.setText(tr("earnings.projection.month"))
        self.projection_year.title.setText(tr("earnings.projection.year"))
        self.history_heading.setText(tr("earnings.history.title"))
        self.sku_label.setText(tr("earnings.field.sku"))
        self.name_label.setText(tr("earnings.field.name"))
        self.brand_label.setText(tr("earnings.field.brand"))
        self.type_label.setText(tr("earnings.field.type"))
        self.date_label.setText(tr("earnings.field.date"))
        self.edit_entry_button.setText(tr("earnings.history.edit"))
        self.delete_entry_button.setText(tr("earnings.history.delete"))
        self.clear_filters_button.setText(tr("earnings.history.clear_filters"))
        self.analytics_empty_title.setText(tr("earnings.analytics.empty.title"))
        self.analytics_empty_body.setText(tr("earnings.analytics.empty.body"))
        self.analytics_empty_add.setText(tr("earnings.add.action"))
        self.entries_empty_title.setText(tr("earnings.history.empty.title"))
        self.entries_empty_body.setText(tr("earnings.history.empty.body"))
        self.entries_empty_add.setText(tr("earnings.add.action"))
        self.sessions_empty_title.setText(tr("earnings.sessions.empty.title"))
        self.sessions_empty_body.setText(tr("earnings.sessions.empty.body"))
        self.sessions_empty_add.setText(tr("earnings.sessions.empty.action"))
        self.history_tabs.setTabText(0, tr("earnings.history.earnings"))
        self.history_tabs.setTabText(1, tr("earnings.history.sessions"))
        self.sku_input.setPlaceholderText(tr("earnings.sku.placeholder"))
        self.name_input.setPlaceholderText(tr("earnings.name.placeholder"))
        self.search.setPlaceholderText(tr("earnings.search.placeholder"))
        self._refresh_projections()
        self._timer_tick()

"""Full-width live and finished Orbea run boards."""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QDialog, QHeaderView, QHBoxLayout, QLabel, QSizePolicy, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    CardWidget, CheckBox, ComboBox, FlowLayout, LineEdit,
    PlainTextEdit, PrimaryPushButton, ProgressBar, PushButton, ScrollArea,
    TitleLabel, isDarkTheme, qconfig,
)

from GUI_Qt.styles.theme_config import get_accent_colors, get_status_text_color, get_subtle_border, get_surface_color, get_text_color
from GUI_Qt.styles.screen_theme import apply_screen_palette
from tools.orbea_automation.run_report import STAGE_LABELS


def _clock(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}" if seconds >= 3600 else f"{seconds // 60:02d}:{seconds % 60:02d}"


class OrbeaRunReportDialog(QDialog):
    def __init__(self, panel):
        super().__init__(panel.screen)
        self.panel = panel
        self.report = None
        self.affected_keys = None
        self._visible_entries = []
        self._log_dirty = False
        self._labels = []
        self.setObjectName("orbeaRunReport")
        self.setWindowTitle(self._t("title", "Orbea upload run"))
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.resize(1220, 940)
        self.setMinimumSize(760, 600)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.scroll = ScrollArea(self)
        self.scroll.setWidgetResizable(True)
        root.addWidget(self.scroll)
        self.content = QWidget()
        self.content.setObjectName("orbeaReportContent")
        self.scroll.setWidget(self.content)
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)
        header = QHBoxLayout()
        self.title = TitleLabel(self._t("title", "Orbea upload run"))
        self.title.setWordWrap(True)
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        header.addWidget(self.title, 1)
        self.back = PushButton(self._t("back", "Back to automation"))
        self.back.clicked.connect(self.hide)
        header.addWidget(self.back)
        layout.addLayout(header)

        self.pages = QStackedWidget()
        layout.addWidget(self.pages)
        live, live_layout = self._card()
        self.pages.addWidget(live)
        self.live_heading = self._label("", 26, True)
        self.timing = self._label("")
        self.progress = ProgressBar()
        self.live_line = self._label("")
        self.stop = PushButton(self._t("stop", "Stop after current product"))
        self.stop.clicked.connect(panel.request_stop)
        for widget in (self.live_heading, self.timing, self.progress, self.live_line, self.stop):
            live_layout.addWidget(widget)
        finished, finished_layout = self._card()
        self.pages.addWidget(finished)
        self.outcome = self._label("", 26, True)
        self.reason = self._label("")
        self.finished_timing = self._label("")
        for widget in (self.outcome, self.reason, self.finished_timing):
            finished_layout.addWidget(widget)
        actions = FlowLayout()
        finished_layout.addLayout(actions)
        self.retry_failed = PrimaryPushButton(self._t("retry_failed", "Retry failed steps"))
        self.retry_pending = PushButton(self._t("retry_pending", "Run not-started products"))
        self.export = PushButton(self._t("export", "Export results to Excel"))
        self.retry_failed.clicked.connect(lambda: panel.retry_report_products("failed"))
        self.retry_pending.clicked.connect(lambda: panel.retry_report_products("not_started"))
        self.export.clicked.connect(panel.export_run_results)
        for button in (self.retry_failed, self.retry_pending, self.export):
            actions.addWidget(button)

        counters = QHBoxLayout()
        self.counters = {}
        for key, label in (("succeeded", "Succeeded"), ("failed", "Failed"), ("not_started", "Not started")):
            card, card_layout = self._card()
            card_layout.addWidget(self._label(self._t(key, label)))
            value = self._label("0", 28, True)
            card_layout.addWidget(value)
            self.counters[key] = value
            counters.addWidget(card, 1)
        layout.addLayout(counters)
        self.warning_subset = self._label("")
        layout.addWidget(self.warning_subset)

        self.failures_card, body = self._card()
        layout.addWidget(self.failures_card)
        body.addWidget(self._label(self._t("causes", "Failures grouped by step and cause"), 16, True))
        self.failures = self._table(("Step", "Products", "Cause"))
        self.failures.setMinimumHeight(130)
        self.failures.setMaximumHeight(260)
        self.failures.setColumnWidth(0, 240)
        self.failures.setColumnWidth(1, 90)
        self.failures.cellDoubleClicked.connect(self._show_group)
        body.addWidget(self.failures)
        self.advice = self._label("")
        body.addWidget(self.advice)
        body.addWidget(self._label(self._t("group_hint", "Double-click a cause to see its affected products."), 13))

        self.products_card, body = self._card()
        layout.addWidget(self.products_card)
        body.addWidget(self._label(self._t("products", "Product results"), 16, True))
        product_tools = FlowLayout()
        body.addLayout(product_tools)
        self.result_filter = ComboBox()
        for key, label in (("all", "All products"), ("failed", "Failed"), ("succeeded", "Succeeded"), ("not_started", "Not started"), ("warnings", "With warnings")):
            self.result_filter.addItem(self._t("filter_" + key, label), userData=key)
        self.result_filter.currentIndexChanged.connect(self._result_filter_changed)
        product_tools.addWidget(self.result_filter)
        self.product_search = LineEdit()
        self.product_search.setPlaceholderText(self._t("product_search", "Search SKU or product"))
        self.product_search.setMinimumWidth(240)
        self.product_search.textChanged.connect(self._refresh_products)
        product_tools.addWidget(self.product_search)
        self.products = self._table(("SKU", "Product", "Status", "Steps completed"))
        self.products.setMinimumHeight(190)
        self.products.setMaximumHeight(320)
        self.products.setColumnWidth(0, 130)
        self.products.setColumnWidth(1, 390)
        self.products.setColumnWidth(2, 170)
        self.products.cellClicked.connect(self._select_product_row)
        body.addWidget(self.products)

        card, body = self._card()
        layout.addWidget(card)
        self.now = self._label(self._t("now", "Current product"), 16, True)
        body.addWidget(self.now)
        self.step_product = ComboBox()
        self.step_product.currentIndexChanged.connect(self._refresh_steps)
        body.addWidget(self.step_product)
        step_widget = QWidget()
        self.step_layout = FlowLayout(step_widget)
        self.step_labels = {}
        for stage, label in STAGE_LABELS.items():
            chip = QLabel(label)
            chip.setProperty("ubAllowBg", True)
            self.step_labels[stage] = chip
            self.step_layout.addWidget(chip)
        body.addWidget(step_widget)
        self.step_note = self._label("", 13)
        body.addWidget(self.step_note)

        card, body = self._card()
        layout.addWidget(card)
        body.addWidget(self._label(self._t("log", "Run log"), 16, True))
        controls = FlowLayout()
        body.addLayout(controls)
        self.level = ComboBox()
        for key, label in (("all", "All levels"), ("info", "Info"), ("warning", "Warnings"), ("error", "Errors")):
            self.level.addItem(self._t("level_" + key, label), userData=key)
        self.search = LineEdit()
        self.search.setMinimumWidth(220)
        self.search.setPlaceholderText(self._t("search", "Search the log"))
        self.log_product = ComboBox()
        self.log_product.setMinimumWidth(150)
        self.order = ComboBox()
        self.order.addItem(self._t("by_time", "By time"), userData="time")
        self.order.addItem(self._t("by_product", "By product"), userData="product")
        self.auto_scroll = CheckBox(self._t("auto_scroll", "Auto-scroll"))
        self.auto_scroll.setChecked(True)
        self.copy = PushButton(self._t("copy", "Copy"))
        self.open_log = PushButton(self._t("open_log", "Open log file"))
        self.copy.clicked.connect(self._copy_log)
        self.open_log.clicked.connect(self._open_log)
        for widget in (self.level, self.search, self.log_product, self.order, self.auto_scroll, self.copy, self.open_log):
            controls.addWidget(widget)
        for combo in (self.level, self.log_product, self.order):
            combo.currentIndexChanged.connect(self._refresh_log)
        self.search.textChanged.connect(self._refresh_log)
        self.log = self._table(("Time", "Level", "SKU", "Step", "Message"))
        self.log.setMinimumHeight(420)
        self.log.setMaximumHeight(560)
        for column, width in enumerate((90, 85, 120, 210)):
            self.log.setColumnWidth(column, width)
        self._log_resize_timer = QTimer(self)
        self._log_resize_timer.setSingleShot(True)
        self._log_resize_timer.timeout.connect(self.log.resizeRowsToContents)
        self.log.viewport().installEventFilter(self)
        self.log.itemSelectionChanged.connect(self._log_selected)
        self.log.cellDoubleClicked.connect(lambda *_: self.technical_toggle.setChecked(not self.technical_toggle.isChecked()) if self.technical_toggle.isEnabled() else None)
        body.addWidget(self.log)
        self.technical_toggle = PushButton(self._t("technical", "Show technical details"))
        self.technical_toggle.setCheckable(True)
        self.technical_toggle.setEnabled(False)
        body.addWidget(self.technical_toggle)
        self.technical = PlainTextEdit()
        self.technical.setReadOnly(True)
        self.technical.setFixedHeight(180)
        self.technical.hide()
        self.technical_toggle.toggled.connect(self.technical.setVisible)
        body.addWidget(self.technical)
        self.log_count = self._label("", 13)
        body.addWidget(self.log_count)
        self.storage_status = self._label("", 13)
        layout.addWidget(self.storage_status)
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._tick)
        qconfig.themeChangedFinished.connect(self.apply_theme)
        self.apply_theme()

    def _t(self, key, fallback, **kwargs):
        return self.panel._t("report." + key, fallback, **kwargs)

    def _label(self, text, size=14, bold=False):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setStyleSheet(f"font-size: {size}px; font-weight: {'600' if bold else '400'}; background: transparent;")
        self._labels.append((label, size, bold))
        return label

    def _card(self):
        card = CardWidget()
        body = QVBoxLayout(card)
        body.setContentsMargins(18, 16, 18, 16)
        body.setSpacing(12)
        return card, body

    def _table(self, labels):
        table = QTableWidget(0, len(labels))
        table.setHorizontalHeaderLabels(labels)
        table.verticalHeader().hide()
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setSectionResizeMode(len(labels) - 1, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setDefaultSectionSize(34)
        table.setWordWrap(True)
        return table

    def apply_theme(self):
        dark = isDarkTheme()
        background = get_surface_color(dark, "canvas")
        text = get_text_color(dark)
        apply_screen_palette(self)
        apply_screen_palette(self.content)
        self.setStyleSheet(f"QDialog#orbeaRunReport {{background: {background}; color: {text};}}")
        self.content.setStyleSheet(f"QWidget#orbeaReportContent {{ background: {background}; color: {text}; }}")
        self.scroll.setStyleSheet(f"QScrollArea {{background: {background}; border: none;}} QScrollArea QWidget#qt_scrollarea_viewport {{background: {background};}}")
        for label, size, bold in self._labels:
            label.setStyleSheet(f"font-size: {size}px; font-weight: {'600' if bold else '400'}; color: {text}; background: transparent;")
        for table in (self.products, self.failures, self.log):
            table.setStyleSheet(f"QTableWidget {{ background: {get_surface_color(dark)}; color: {text}; gridline-color: {get_subtle_border(dark)}; font-size: 14px; border: 1px solid {get_subtle_border(dark)}; }} QHeaderView::section {{background: {get_surface_color(dark, 'alternate')}; color: {text}; padding: 8px; border: none;}}")
        self.log.setStyleSheet(self.log.styleSheet() + " QTableWidget {font-family: Consolas; font-size: 13px;} ")
        self.technical.setStyleSheet("font-family: Consolas; font-size: 13px;")
        if self.report:
            self._refresh_steps()
            self._refresh_log(force=True)

    def set_report(self, report):
        self.report = report
        self.affected_keys = None
        for combo in (self.step_product, self.log_product):
            combo.blockSignals(True)
            combo.clear()
        self.log_product.addItem(self._t("all_products", "All products"), userData="")
        for match in report.matches:
            self.step_product.addItem(f"{match.sku} · {match.pimbo_product_name or match.orbea_product_name}", userData=report.key(match))
        for sku in dict.fromkeys(match.sku for match in report.matches):
            self.log_product.addItem(sku, userData=sku)
        for combo in (self.step_product, self.log_product):
            combo.blockSignals(False)
        self.search.clear()
        self.product_search.clear()
        self.level.setCurrentIndex(0)
        self.result_filter.setCurrentIndex(0)
        self.auto_scroll.setChecked(not report.finished)
        self.technical_toggle.setChecked(False)
        self.pages.setCurrentIndex(1 if report.finished else 0)
        self._timer.start()
        self.refresh()
        self._refresh_log()

    def refresh(self):
        if not self.report:
            return
        report = self.report
        counts = report.counts
        just_finished = report.finished and self.pages.currentIndex() == 0
        self.pages.setCurrentIndex(1 if report.finished else 0)
        for key, label in self.counters.items():
            label.setText(str(counts[key]))
        self.warning_subset.setText(self._t("warnings_subset", "{warnings} product(s) with warnings — a subset of the succeeded / failed counts. {active} currently in progress.", warnings=counts["warnings"], active=counts["in_progress"]))
        total, done = len(report.matches), len(report.results)
        self.live_heading.setText(self._t("live_heading", "Product {current} of {total}", current=min(done + 1, total), total=total))
        if report.browser_count > 1:
            self.live_heading.setText(self.panel.screen._t("orbea.browsers.progress", "{active} products active · {done}/{total} finished",
                                                          active=counts["in_progress"], done=done, total=total))
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(done)
        self.stop.setEnabled(not report.stop_requested and not report.finished)
        self.stop.setText(self.panel.screen._t("orbea.browsers.stop", "Stop after active products") if report.browser_count > 1
                          else self._t("stop", "Stop after current product"))
        self.live_line.setText(self._t("live_counts", "{done} finished · {failed} failed · {left} remaining", done=done, failed=counts["failed"], left=total-done))
        if report.stop_requested and not report.finished:
            self.live_line.setText(self.panel.screen._t("orbea.browsers.stopping", "Stopping after active products…") if report.browser_count > 1
                                   else self._t("stopping", "Stopping after the current product…"))
        if report.finished:
            if just_finished:
                self.auto_scroll.setChecked(False)
                failed_key = next((key for key, result in report.results.items() if not result.succeeded), None)
                if failed_key:
                    self.step_product.setCurrentIndex(self.step_product.findData(failed_key))
            title, reason = report.outcome()
            self.outcome.setText(title)
            self.reason.setText(reason)
            self.finished_timing.setText(self._t("duration", "Started {start} · Duration {duration}", start=report.started_at, duration=_clock(report.elapsed)))
            self._timer.stop()
        elif report.current_key:
            self.step_product.setCurrentIndex(max(0, self.step_product.findData(report.current_key)))
        busy = self.panel.screen.is_running()
        self.retry_failed.setEnabled(report.finished and counts["failed"] > 0 and not busy)
        self.retry_pending.setEnabled(report.finished and counts["not_started"] > 0 and not busy)
        self.export.setEnabled(report.finished)
        self.failures_card.setVisible(report.finished and bool(counts["failed"]))
        self.products_card.setVisible(report.finished)
        if report.finished:
            self._refresh_failures()
            self._refresh_products()
        self._refresh_steps()
        self._log_dirty = True
        self.open_log.setEnabled(bool(report.log_path and report.log_path.is_file()))
        self.storage_status.setText(report.storage_error or (self._t("saved_log", "Full log: {path}", path=report.log_path) if report.log_path else ""))
        self._update_time()

    def _update_time(self):
        done = len(self.report.results)
        remaining = len(self.report.matches) - done
        estimate = _clock(self.report.elapsed / done * remaining) if done else self._t("estimating", "estimating…")
        self.timing.setText(self._t("elapsed", "Elapsed {elapsed} · About {remaining} left · Keep the browser open.", elapsed=_clock(self.report.elapsed), remaining=estimate))

    def _tick(self):
        if self.report and self.isVisible():
            self._update_time()
            if self._log_dirty:
                self._refresh_log()

    def _refresh_failures(self):
        groups = self.report.failure_groups()
        self.failures.setRowCount(len(groups))
        hidden_input = False
        for row, group in enumerate(groups):
            summary = group["summary"]
            for column, text in enumerate((STAGE_LABELS.get(summary.stage, summary.stage or "Product / preflight"), str(len(group["products"])), summary.headline)):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, group)
                self.failures.setItem(row, column, item)
            hidden_input |= summary.stage in {"geometry", "size_tables", "product_photos"} and any(token in (summary.headline + summary.technical).casefold() for token in ("element not interactable", "elementnotinteractable", "could not be scrolled into view"))
        self.failures.resizeRowsToContents()
        self.advice.setVisible(hidden_input)
        self.advice.setText(self._t("input_advice", "A file upload control could not be interacted with. This may need a selector or scrolling fix; retrying unchanged automation is unlikely to resolve it."))

    def _show_group(self, row, _column):
        self.result_filter.setCurrentIndex(self.result_filter.findData("failed"))
        self.affected_keys = self.failures.item(row, 0).data(Qt.ItemDataRole.UserRole)["products"]
        self.product_search.clear()
        self._refresh_products()
        self.scroll.ensureWidgetVisible(self.products_card)

    def _result_filter_changed(self, *_):
        self.affected_keys = None
        self._refresh_products()

    def _refresh_products(self, *_):
        if not self.report:
            return
        report, wanted = self.report, self.result_filter.currentData()
        rows = []
        for match in report.matches:
            key = report.key(match)
            result = report.results.get(key)
            status = "succeeded" if result and result.succeeded else "failed" if result else "in_progress" if key in report.started_products else "not_started"
            if self.affected_keys is not None and key not in self.affected_keys:
                continue
            if wanted == "warnings" and not (result and result.preparation.warnings):
                continue
            if wanted not in {"all", "warnings", status}:
                continue
            name = match.pimbo_product_name or match.orbea_product_name
            if self.product_search.text().casefold() not in f"{match.sku} {name}".casefold():
                continue
            steps = sum(value == "done" for value in report.states[key].values())
            rows.append((key, match.sku, name, status.replace("_", " ").capitalize(), f"{steps} / {len(report.selected_stages)}"))
        self.products.setRowCount(len(rows))
        for row, (key, *values) in enumerate(rows):
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, key)
                self.products.setItem(row, column, item)

    def _select_product_row(self, row, _column):
        self.step_product.setCurrentIndex(self.step_product.findData(self.products.item(row, 0).data(Qt.ItemDataRole.UserRole)))
        self.scroll.ensureWidgetVisible(self.step_product)

    def _refresh_steps(self, *_):
        if not self.report:
            return
        key = self.step_product.currentData()
        states = self.report.states.get(key, {})
        dark = isDarkTheme()
        symbols = {"done": "✓", "failed": "✗", "running": "●", "skipped": "–", "pending": "○"}
        for stage, label in self.step_labels.items():
            label.setVisible(stage in self.report.selected_stages)
            state = states.get(stage, "pending")
            color = get_status_text_color({"done": "success", "failed": "error", "running": "info"}.get(state, "pending"), dark)
            background = get_accent_colors(dark)["base"] if state == "running" else get_surface_color(dark)
            if state == "running":
                color = get_accent_colors(dark)["text"]
            label.setText(f"{symbols[state]} {self.panel._t('stage.' + stage, STAGE_LABELS[stage])}")
            label.setToolTip(state.capitalize())
            label.setStyleSheet(f"font-size: 13px; padding: 7px 10px; border-radius: 5px; border: 1px {'dashed' if state in {'pending', 'skipped'} else 'solid'} {get_subtle_border(dark)}; color: {color}; background: {background};")
        self.now.setText(self._t("steps", "Steps for {sku}", sku=self.step_product.currentText().split(" · ")[0]))
        self.step_note.setText(self._t("legend", "✓ Completed · ● Running · ✗ Failed · – Skipped · ○ Not started. Completed steps may still have unsaved changes; check the product result."))

    def _filtered_log(self):
        return self.report.filtered_entries(level=self.level.currentData() or "all", search=self.search.text(), product=self.log_product.currentData() or "", by_product=self.order.currentData() == "product")

    def _refresh_log(self, *_, force=False):
        if not self.report:
            return
        entries = self._filtered_log()
        scrollbar = self.log.verticalScrollBar()
        old_scroll = scrollbar.value()
        selected = self._visible_entries[self.log.currentRow()] if 0 <= self.log.currentRow() < len(self._visible_entries) else None
        previous = self._visible_entries
        self._visible_entries = entries[-2500:]
        reused = 0
        if previous and self._visible_entries and not force:
            try:
                overlap = self._visible_entries.index(previous[-1]) + 1
                if overlap <= len(previous) and previous[-overlap:] == self._visible_entries[:overlap]:
                    reused = overlap
            except ValueError:
                pass
        self.log.setUpdatesEnabled(False)
        self.log.blockSignals(True)
        if reused:
            for _ in range(len(previous) - reused):
                self.log.removeRow(0)
        self.log.setRowCount(len(self._visible_entries))
        for row in range(reused, len(self._visible_entries)):
            entry = self._visible_entries[row]
            values = (entry.timestamp[11:19], entry.level.capitalize(), entry.product or "Run", STAGE_LABELS.get(entry.stage, entry.stage), entry.message + ("  [technical details]" if entry.technical else ""))
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if entry.level != "info":
                    item.setForeground(QColor(get_status_text_color("error" if entry.level == "error" else "warning", isDarkTheme())))
                self.log.setItem(row, column, item)
            self.log.resizeRowToContents(row)
        if selected in self._visible_entries:
            self.log.selectRow(self._visible_entries.index(selected))
        else:
            self.log.clearSelection()
            self.log.setCurrentCell(-1, -1)
        self.log.blockSignals(False)
        self.log.setUpdatesEnabled(True)
        if self.auto_scroll.isChecked():
            self.log.scrollToBottom()
        else:
            scrollbar.setValue(old_scroll)
        self._log_selected()
        self.log_count.setText(self._t("log_count", "Showing {shown} of {matching} matching entries · {total} total. Stack traces are collapsed by default.", shown=len(self._visible_entries), matching=len(entries), total=len(self.report.entries)))
        self._log_dirty = False

    def _log_selected(self):
        row = self.log.currentRow()
        details = self._visible_entries[row].technical if 0 <= row < len(self._visible_entries) else ""
        self.technical_toggle.setEnabled(bool(details))
        self.technical.setPlainText(details)
        if not details:
            self.technical_toggle.setChecked(False)

    def _copy_log(self):
        QApplication.clipboard().setText("\n".join(entry.text() for entry in self._filtered_log()))

    def _open_log(self):
        if self.report.log_path and self.report.log_path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.report.log_path.resolve())))

    def showEvent(self, event):
        super().showEvent(event)
        if self.report:
            self.refresh()
            self._refresh_log()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "log"):
            return
        width = max(600, self.width() - 84)
        for column, value in enumerate((80, 72, 100, 150) if width < 1000 else (90, 85, 120, 210)):
            self.log.setColumnWidth(column, value)
        self.products.setColumnWidth(0, 110 if width < 1000 else 130)
        self.products.setColumnWidth(1, max(220, int(width * 0.36)))
        self.products.setColumnWidth(2, 120 if width < 1000 else 170)
        self.failures.setColumnWidth(0, 180 if width < 1000 else 240)
        self.failures.setColumnWidth(1, 80)
        self._log_resize_timer.start(0)

    def eventFilter(self, watched, event):
        if hasattr(self, "log") and watched is self.log.viewport() and event.type() == QEvent.Type.Resize:
            self._log_resize_timer.start(0)
        return super().eventFilter(watched, event)

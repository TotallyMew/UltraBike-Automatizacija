"""Excel-driven, multi-model copying through the shared Orbea job controller."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, LineEdit, PlainTextEdit, PrimaryPushButton, PushButton, StrongBodyLabel

from GUI_Qt.styles.screen_theme import CARD_SPACING
from GUI_Qt.styles.theme_config import get_dialog_table_style
from GUI_Qt.widgets.workspace import WorkspaceColumns

from tools.orbea_automation.model_copy import OrbeaModelCopyService, export_copy_results, load_copy_workbook
from .workers import OrbeaModelCopyWorker
from .model_copy_groups import ModelCopyGroupTable
from .colour_attributes import OrbeaColourAttributePanel


class OrbeaModelCopyPanel(QWidget):
    def __init__(self, screen, service_factory=None):
        super().__init__(screen)
        self.screen = screen
        self.service_factory = service_factory or OrbeaModelCopyService
        self.worker = None
        self._busy = False
        self._operation_id = None
        self._run_mode = None
        self._run_selection = ()
        self._completed_state = None
        self.state = None
        self.groups = []
        self.error = ""
        self._status_message = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(CARD_SPACING)
        self._workspace = WorkspaceColumns(sidebar_width=340)
        layout.addWidget(self._workspace)
        self.input_card, input_box = screen._card()
        self.input_card.setObjectName("orbeaModelCopyInputCard")
        self._workspace.main_layout.addWidget(self.input_card)
        self.title = StrongBodyLabel("")
        self.hint = CaptionLabel("")
        self.hint.setWordWrap(True)
        input_box.addWidget(self.title)
        input_box.addWidget(self.hint)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.path = LineEdit()
        self.browse = PushButton("")
        self.path.setMinimumHeight(38)
        self.browse.setMinimumHeight(38)
        row.addWidget(self.path, 1)
        row.addWidget(self.browse)
        input_box.addLayout(row)
        self.colours = OrbeaColourAttributePanel(screen, self._t, self)
        input_box.addWidget(self.colours)
        self.colours.changed.connect(self.update_state)

        self.groups_card, groups_box = screen._card()
        self.groups_card.setObjectName("orbeaModelCopyGroupsCard")
        self._workspace.main_layout.addWidget(self.groups_card)
        self.groups_title = StrongBodyLabel("")
        self.groups_hint = CaptionLabel("")
        self.groups_hint.setWordWrap(True)
        groups_box.addWidget(self.groups_title)
        groups_box.addWidget(self.groups_hint)
        self.search = LineEdit()
        self.search.setMinimumHeight(38)
        self.search.setClearButtonEnabled(True)
        groups_box.addWidget(self.search)
        selection_row = QHBoxLayout()
        self.select_all = PushButton("")
        self.clear_selection = PushButton("")
        selection_row.addWidget(self.select_all)
        selection_row.addWidget(self.clear_selection)
        selection_row.addStretch()
        groups_box.addLayout(selection_row)
        self.selection_summary = CaptionLabel("")
        self.selection_summary.setWordWrap(True)
        groups_box.addWidget(self.selection_summary)
        self.empty_hint = CaptionLabel("")
        self.empty_hint.setWordWrap(True)
        groups_box.addWidget(self.empty_hint)
        self.table = ModelCopyGroupTable(self._t, self._status_text, self)
        groups_box.addWidget(self.table)

        self.run_card, run_box = screen._card()
        self.run_card.setObjectName("orbeaModelCopyRunCard")
        self._workspace.side_layout.addWidget(self.run_card)
        self.run_title = StrongBodyLabel("")
        self.run_hint = CaptionLabel("")
        self.run_hint.setWordWrap(True)
        run_box.addWidget(self.run_title)
        run_box.addWidget(self.run_hint)
        self.status = CaptionLabel("")
        self.status.setWordWrap(True)
        run_box.addWidget(self.status)
        self.read = PushButton("")
        self.start = PrimaryPushButton("")
        self.resume = PushButton("")
        self.retry = PushButton("")
        self.stop = PushButton("")
        for button in (self.read, self.start, self.resume, self.retry, self.stop):
            button.setMinimumHeight(38)
            run_box.addWidget(button)

        self.results_card, results_box = screen._card()
        self.results_card.setObjectName("orbeaModelCopyResultsCard")
        self._workspace.main_layout.addWidget(self.results_card)
        results_heading = QHBoxLayout()
        self.results_title = StrongBodyLabel("")
        self.export = PushButton("")
        self.export.setMinimumHeight(34)
        results_heading.addWidget(self.results_title)
        results_heading.addStretch()
        results_heading.addWidget(self.export)
        results_box.addLayout(results_heading)
        self.results_empty = CaptionLabel("")
        self.results_empty.setWordWrap(True)
        results_box.addWidget(self.results_empty)
        self.results = QTableWidget(0, 7)
        self.results.setMinimumHeight(280)
        self.results.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results.setWordWrap(False)
        self.results.setShowGrid(False)
        self.results.verticalHeader().hide()
        self.results.verticalHeader().setDefaultSectionSize(46)
        self.results.horizontalHeader().setMinimumHeight(46)
        self.results.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        for column in (3, 5):
            self.results.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        results_box.addWidget(self.results)

        self.log_card, log_box = screen._card()
        self.log_card.setObjectName("orbeaModelCopyLogCard")
        self._workspace.side_layout.addWidget(self.log_card)
        self.log_title = StrongBodyLabel("")
        log_box.addWidget(self.log_title)
        self.log = PlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(140)
        self.log.setMaximumHeight(200)
        log_box.addWidget(self.log)
        for box in (input_box, groups_box, run_box, results_box, log_box):
            box.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._workspace.main_layout.addStretch()
        self._workspace.side_layout.addStretch()
        self.browse.clicked.connect(self._browse)
        self.path.textChanged.connect(self._path_changed)
        self.table.groups_selected.connect(self.update_state)
        self.table.source_selected.connect(self._source_changed)
        self.search.textChanged.connect(self.table.set_filter)
        self.select_all.clicked.connect(lambda: self.table.select_visible(True))
        self.clear_selection.clicked.connect(lambda: self.table.select_visible(False))
        self.read.clicked.connect(lambda: self.launch("capture"))
        self.start.clicked.connect(lambda: self.launch("copy"))
        self.resume.clicked.connect(lambda: self.launch("copy"))
        self.retry.clicked.connect(lambda: self.launch("retry"))
        self.stop.clicked.connect(self.request_stop)
        self.export.clicked.connect(self._export)
        self.retranslate_ui()
        self.path.setText(screen._setting_get("orbea_model_copy_excel", ""))
        self.update_state()

    def _t(self, key, fallback, **kwargs):
        return self.screen._t("orbea.model_copy." + key, fallback, **kwargs)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, self._t("title", "Model copying"), self.path.text(), "Excel (*.xlsx)")
        if path:
            if self.path.text() == path:
                self._path_changed()
            else:
                self.path.setText(path)

    def _path_changed(self):
        self.state, self.groups = None, []
        self.error = ""
        path = self.path.text().strip()
        if path:
            try:
                self.groups = load_copy_workbook(path)
                checkpoint = OrbeaModelCopyService.checkpoint_path(path)
                if checkpoint.is_file():
                    self.state = OrbeaModelCopyService.load_checkpoint(path)
                    self.groups = self.state.groups
                self.screen._setting_set("orbea_model_copy_excel", path)
                ready = sum(group.status == "ready" for group in self.groups)
                if self.state and ready:
                    self._set_status("checkpoint_loaded", "Loaded {ready} saved source groups. Select groups to copy unfinished bikes.", ready=ready)
                elif not any(group.source_sku for group in self.groups):
                    self._set_status("sources_unmarked", "Loaded {count} TTCC groups. Choose one prepared source bike in each group, then read sources.", count=len(self.groups))
                else:
                    self._set_status("loaded", "Loaded {count} TTCC groups. Read saved sources before copying.", count=len(self.groups))
            except (OSError, ValueError, KeyError, TypeError) as error:
                self._status_message = None
                self.status.setText(str(error))
        self._render()
        self.update_state()

    def _render(self, preserve_selection=False):
        values = self.state.results if self.state else []
        self.table.set_groups(self.groups, values, preserve_selection=preserve_selection)
        self.table.setVisible(bool(self.groups))
        self.empty_hint.setVisible(not self.groups)
        self.results_card.setVisible(self.state is not None)
        self.results.setVisible(bool(values))
        self.results_empty.setVisible(not values)
        self.results.setRowCount(len(values))
        for row, result in enumerate(values):
            for column, value in enumerate((result.sku, result.source_sku, self._status_text(result.status), result.title,
                                            self._t("stage." + result.failed_stage, result.failed_stage) if result.failed_stage else "", result.error,
                                            "; ".join(result.colour_attribute) or self._t("colour_unmapped", "No mapping — unchanged"))):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.results.setItem(row, column, item)
        self.update_state()

    @staticmethod
    def _eligible(group):
        return bool(group.source_sku and group.targets and not group.workbook_error)

    def _source_changed(self, ttcc, sku):
        if self.screen.is_running():
            return
        if any(group.ttcc == ttcc and group.source_sku == sku for group in self.groups):
            return
        selected = set(self.table.selected_codes(visible_only=False))
        try:
            self.state = OrbeaModelCopyService.select_source(self.path.text().strip(), ttcc, sku)
            self.groups = self.state.groups
            self.error = ""
            self._render(preserve_selection=True)
            # A newly chosen source makes its group available immediately.
            for group in self.groups:
                checked = self._eligible(group) and (group.ttcc in selected or (group.ttcc == ttcc and sku))
                self.table.group_check(group.ttcc).setChecked(bool(checked))
            if getattr(self.screen.main, "driver", None) is None:
                self._set_status("connect_to_read", "Source choices saved. Connect to Pimbo to read sources.")
            elif sku:
                self._set_status("source_chosen", "Source {sku} selected for {ttcc}. Read sources before copying.", sku=sku, ttcc=ttcc)
            else:
                self._set_status("sources_unmarked", "Loaded {count} TTCC groups. Choose one prepared source bike in each group, then read sources.", count=len(self.groups))
        except (OSError, ValueError, KeyError, TypeError) as error:
            self._render(preserve_selection=True)
            self._failed(str(error))
        self.update_state()

    def _status_text(self, status):
        return self._t("status." + status, status.replace("_", " "))

    def selected_ttcc(self, *, ready_only=True):
        selected = self.table.selected_codes()
        return tuple(group.ttcc for group in self.groups
                     if group.ttcc in selected
                     and self._eligible(group) and (not ready_only or (group.status == "ready" and group.template)))

    def update_state(self, *_args):
        controller = self.screen.workflow_controller
        activity = controller.activity()
        busy = activity.name != "idle"
        active = activity.name in {"model_copy_read", "model_copy"}
        connected = getattr(self.screen.main, "driver", None) is not None
        self.path.setEnabled(not busy)
        self.browse.setEnabled(not busy)
        self.search.setEnabled(not busy)
        self.colours.table.setEnabled(not busy)
        self.select_all.setEnabled(not busy and bool(self.groups))
        self.clear_selection.setEnabled(not busy and bool(self.groups))
        self.read.setEnabled(not busy and connected and bool(self.selected_ttcc(ready_only=False)))
        ready = bool(self.selected_ttcc()) and connected and self.state is not None and self.colours.mapping is not None
        for button in (self.start, self.resume):
            button.setEnabled(not busy and ready)
        self.resume.setVisible(self.state is not None)
        self.retry.setEnabled(not busy and ready and any(item.status == "failed" for item in self.state.results))
        self.stop.setVisible(active)
        self.stop.setEnabled(active and not activity.stopping)
        self.export.setEnabled(not busy and self.state is not None)
        self.table.set_busy(busy)
        selected = set(self.table.selected_codes())
        self.selection_summary.setText(self._t(
            "selection_summary", "{selected} selected groups · {targets} target bikes · Showing {visible} of {total} groups",
            selected=len(selected), targets=sum(len(group.targets) for group in self.groups if group.ttcc in selected),
            visible=len(self.table.visible_groups()), total=len(self.groups),
        ))

    def launch(self, mode):
        if self.screen.is_running() or getattr(self.screen.main, "driver", None) is None:
            return
        selected = self.selected_ttcc(ready_only=mode != "capture")
        if not selected:
            return
        if mode != "capture" and self.colours.mapping is None:
            self._failed(self.colours.error)
            return
        mapping = self.colours.mapping
        def factory(driver):
            service = self.service_factory(driver)
            configure = getattr(service, "set_colour_mapping", None)
            if mode != "capture" and callable(configure):
                configure(mapping)
            return service
        if not self.screen._acquire_browser():
            return
        self.error = ""
        self._busy = True
        self._run_mode, self._run_selection = mode, selected
        self._completed_state = None
        self.log.clear()
        self.screen.workflow_controller.start_job("model_copy_read" if mode == "capture" else "model_copy",
            lambda: OrbeaModelCopyWorker(factory, self.screen.main.driver, self.path.text().strip(), mode, selected),
            owner=self, attribute="worker", operation_attribute="_operation_id", kind="upload" if mode != "capture" else "orbea",
            details={"output_path": str(OrbeaModelCopyService.checkpoint_path(self.path.text()).parent)},
            signals={"succeeded": self._result, "failed": self._failed, "progress_changed": self._progress,
                     "item_finished": self._item_finished, "log_message": self.log.appendPlainText},
            finished=self._finished, failed=self._failed)

    def _item_finished(self, item):
        try:
            state = OrbeaModelCopyService.load_checkpoint(self.path.text().strip())
            self._result(state, completed=False)
            if self._run_mode == "capture":
                group = next(group for group in state.groups if group.ttcc == item.ttcc)
                if group.status == "ready" and group.template:
                    self._set_status("source_read", "Source {sku} ({ttcc}) read successfully: {categories} categories, {attributes} attributes, {specifications} specifications. Ready to copy.",
                        sku=group.source_sku, ttcc=group.ttcc, categories=len(group.template.categories),
                        attributes=len(group.template.attributes), specifications=len(group.template.specifications))
                else:
                    self._set_status("source_read_failed", "Source {sku} ({ttcc}) could not be read: {reason}",
                        sku=group.source_sku, ttcc=group.ttcc, reason=group.error)
                self.log.appendPlainText(self.status.text())
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.log.appendPlainText(str(error))

    def _progress(self, message):
        self._status_message = None
        self.status.setText(str(message))
        self.log.appendPlainText(str(message))

    def _result(self, state, *, completed=True):
        self.state, self.groups = state, state.groups
        self.error = state.error
        if completed:
            self._completed_state = state
        self._render(preserve_selection=True)

    def _failed(self, message):
        self.error = message
        self._status_message = None
        self.status.setText(message)
        self.log.appendPlainText(message)
        if not self.screen._closing:
            self.screen._error(self._t("title", "Model copying"), message)

    def _finished(self):
        state = self._completed_state
        stopped = bool(getattr(self.worker, "stop_requested", False) or (state and state.cancelled))
        groups = [group for group in self.groups if group.ttcc in self._run_selection]
        results = [item for item in self.state.results if item.ttcc in self._run_selection] if self.state else []
        if state:
            if self.error:
                self._set_status("run_failed", "Run stopped because of an error.")
            elif self._run_mode == "capture":
                ready = sum(group.status == "ready" and group.template is not None for group in groups)
                failed = sum(group.status in {"error", "source_changed"} for group in groups)
                key = "capture_stopped" if stopped else "capture_finished"
                fallback = ("Source reading stopped: {ready} ready, {failed} failed, {pending} unread." if stopped else
                            "Source reading finished: {ready} ready, {failed} failed, {pending} unread.")
                self._set_status(key, fallback, ready=ready, failed=failed, pending=len(groups) - ready - failed)
            else:
                saved = sum(item.status == "saved" for item in results)
                failed = sum(item.status == "failed" for item in results)
                if stopped:
                    self._set_status("copy_stopped", "Copying stopped. Saved: {saved}. Failed: {failed}.", saved=saved, failed=failed)
                else:
                    self._set_status("finished", "Saved: {saved}. Failed: {failed}. Source groups: {ready}.",
                        saved=saved, failed=failed, ready=sum(group.status == "ready" for group in groups))
            self.log.appendPlainText(self.status.text())
        tracker = getattr(self.screen.main, "operation_tracker", None)
        if tracker and self._operation_id:
            errors = bool(self.error or any(item.status == "failed" for item in results)
                          or any(group.status in {"error", "source_changed"} for group in groups))
            tracker.finish(self._operation_id, "cancelled" if stopped else "partial" if errors else "succeeded",
                           error_summary=self.error, output_path=str(OrbeaModelCopyService.checkpoint_path(self.path.text()).parent))
        self._busy = False

    def request_stop(self):
        self.screen.workflow_controller.request_stop()
        self._set_status("stopping", "Stopping after the current product…")

    def _set_status(self, key, fallback, **kwargs):
        self._status_message = (key, fallback, kwargs)
        self.status.setText(self._t(key, fallback, **kwargs) + ("\n" + self.error if self.error else ""))

    def _export(self):
        if self.state is None:
            return
        default = self.state.checkpoint_path.parent / "model-copy-results.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, self._t("export", "Export results"), str(default), "Excel (*.xlsx)")
        if path:
            try:
                if Path(path).resolve() == Path(self.path.text()).resolve():
                    raise ValueError("Choose a separate results file; do not overwrite the source workbook")
                actual = export_copy_results(self.state, path)
                if Path(actual) != Path(path):
                    message = self.screen._t(
                        "orbea.report.updated_copy",
                        "The original Excel was open or read-only. Updated results are saved in: {path}",
                        path=str(actual),
                    )
                    self.status.setText(message)
                    self.log.appendPlainText(message)
            except (OSError, ValueError) as error:
                self._failed(str(error))

    def apply_theme(self, *, primary_style=None, table_style=None):
        from qfluentwidgets import isDarkTheme
        existing_table = getattr(self.screen, "_table", None)
        style = table_style or (existing_table.styleSheet() if existing_table is not None else "") or get_dialog_table_style(isDarkTheme())
        self.table.apply_theme(style)
        self.results.setStyleSheet(style)
        self.colours.table.setStyleSheet(style)
        primary = getattr(self.screen, "_start_btn", None)
        primary_style = primary_style or (primary.styleSheet() if primary is not None else "")
        if primary_style:
            self.start.setStyleSheet(primary_style)

    def retranslate_ui(self):
        self.colours.retranslate_ui()
        self.title.setText(self._t("title", "Model copying"))
        self.hint.setText(self._t("hint", 'Load orbea_matches.xlsx, then choose one prepared source bike for each base code. Save the source in Pimbo before reading it. Excel Šaltinis/TAIP marks are also supported.'))
        self.path.setPlaceholderText(self._t("excel", "orbea_matches.xlsx or another Matches workbook"))
        for label, key, fallback in (
            (self.groups_title, "groups_title", "Choose source bikes"),
            (self.groups_hint, "groups_hint", "Each base code contains its matching bikes. Choose one saved source per group; its data will be copied to the other bikes. Actions apply to checked groups shown below."),
            (self.run_title, "run_title", "Run copying"),
            (self.run_hint, "run_hint", "Read the selected sources, then copy their saved data to the other bikes in each group."),
            (self.results_title, "results_title", "Copy results"),
            (self.results_empty, "results_empty", "Copied bikes and any errors will appear here."),
            (self.log_title, "log_title", "Activity log"),
            (self.empty_hint, "empty_hint", "Choose an Excel file to see its base codes and bikes."),
        ):
            label.setText(self._t(key, fallback))
        self.search.setPlaceholderText(self._t("search", "Search base code, SKU or bike name"))
        self.search.setAccessibleName(self._t("search", "Search base code, SKU or bike name"))
        self.log.setPlaceholderText(self._t("log_empty", "Progress and any errors will appear here."))
        for button, key, fallback in ((self.browse, "browse", "Choose Excel"), (self.read, "read", "Read sources"),
            (self.start, "start", "Copy and save"), (self.resume, "resume", "Continue"), (self.retry, "retry", "Retry failures"),
            (self.stop, "stop", "Stop after current product"), (self.export, "export", "Export results")):
            button.setText(self._t(key, fallback))
        self.select_all.setText(self._t("select_visible", "Select visible groups"))
        self.clear_selection.setText(self._t("clear_visible", "Clear visible groups"))
        self.table.setHorizontalHeaderLabels((self._t("base_code", "Base code"), self._t("source_role", "Source"), "SKU",
                                              self._t("name", "Name"), self._t("status", "Status")))
        self.results.setHorizontalHeaderLabels((self._t("target", "Target SKU"), self._t("source", "Source SKU"),
            self._t("status", "Status"), self._t("name", "Name"), self._t("stage", "Stage"), self._t("error", "Reason"),
            self._t("colour_attribute", "Spalva attribute")))
        self._render(preserve_selection=True)
        self.apply_theme()
        if self._status_message:
            key, fallback, kwargs = self._status_message
            self._set_status(key, fallback, **kwargs)

"""Collected Orbea products and the selectable PIMBO editing workflow."""
from __future__ import annotations

import json
from pathlib import Path
from Utilities.UploadResultsReport import result_record, upload_result_row, write_upload_results

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CaptionLabel, CheckBox, LineEdit, PlainTextEdit, PrimaryPushButton, PushButton

from GUI_Qt.kross.workers import KrossUploadWorker
from GUI_Qt.orbea.tabs import OrbeaDisclosure
from tools.orbea_automation.upload import OrbeaUploadService, OrbeaWorkflowOptions, OrbeaUploadResult


class OrbeaUploadWorker(KrossUploadWorker):
    completed = Signal(object)
    options_type = OrbeaWorkflowOptions
    result_type = OrbeaUploadResult

    def __init__(self, *args, retry_unfinished=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.retry_unfinished = retry_unfinished
        if retry_unfinished:
            self.matches = tuple(match for match in self.matches if not OrbeaUploadService.upload_finished(match))

    def _upload_one(self, service, match):
        if self.retry_unfinished:
            return service.upload_and_save(match, self.output_root, options=self.options,
                                           progress=self.progress_changed.emit, resume_completed=True)
        return super()._upload_one(service, match)

    def _emit_completed(self):
        ok = sum(result.succeeded for result in self.results)
        failed = len(self.results) - ok
        warnings = sum(bool(result.preparation.warnings) for result in self.results)
        pending = len(self.matches) - len(self.results)
        status = ("cancelled" if self._stop_requested and pending else
                  "failed" if self._batch_error or (not ok and (failed or pending)) else
                  "partial" if failed or warnings or pending else "succeeded")
        self.completed.emit({"status": status, "succeeded": ok, "failed": failed,
            "warnings": warnings, "unprocessed": pending,
            "error": self._batch_error or " | ".join(result.preparation.error for result in self.results if result.preparation.error),
            "output_path": str(self.output_root or (self.matches[0].local_folder if self.matches else ""))})


STAGE_LABELS = {
    "product_photos": "Upload product photos",
    "size_tables": "Upload size table",
    "geometry": "Upload geometry",
    "description_source": "Paste Orbea description",
    "description_magic_ai": "MagicAI description",
    "product_family": "Set family: Dviračiai",
    "brand": "Set brand: Orbea",
    "category_magic_ai": "MagicAI category",
    "translations": "Translate LT → EN / LV / EE",
    "save": "Save Draft product",
    "specifications_prefill": "Fill model, colour and frame sizes",
    "specifications_magic_ai": "MagicAI specifications",
}


class OrbeaUploadPanel(QWidget):
    def __init__(self, screen, service_factory=None):
        super().__init__(screen)
        self.screen = screen
        self.service_factory = service_factory or (lambda: OrbeaUploadService(screen.main.driver))
        self.worker = None
        self.matches = ()
        self.results = []
        self._busy = False
        self._operation_id = None
        self._config = []
        self._finished_uploads = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        self.products_card, layout = screen._card()
        self.products_card.setObjectName("orbeaSelectProductsCard")
        root.addWidget(self.products_card)
        self.title = BodyLabel(self)
        self.title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.hint = CaptionLabel(self)
        self.hint.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.hint)
        row = QHBoxLayout()
        self.folder = LineEdit(self)
        self.folder.setText(str(screen._setting_get("orbea_upload_root", "") or ""))
        self.folder.hide()
        self.browse = PushButton(self)
        self.load = PushButton(self)
        self.current = PushButton(self)
        self.current.hide()
        row.addWidget(self.load)
        row.addWidget(self.browse)
        row.addStretch(1)
        layout.addLayout(row)
        self._config.extend((self.folder, self.browse, self.load, self.current))
        row = QHBoxLayout()
        self.select_all = PushButton(self)
        self.clear = PushButton(self)
        row.addWidget(self.select_all)
        row.addWidget(self.clear)
        row.addStretch()
        layout.addLayout(row)
        self._config.extend((self.select_all, self.clear))
        self.source_label = CaptionLabel(self)
        self.source_label.setWordWrap(True)
        self.source_label.hide()
        layout.addWidget(self.source_label)
        self.empty_hint = CaptionLabel(self)
        self.empty_hint.setWordWrap(True)
        layout.addWidget(self.empty_hint)
        self.table = QTableWidget(0, 5, self)
        self.table.setMinimumHeight(230)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        self.table.hide()
        self._config.append(self.table)

        self.steps_card, layout = screen._card()
        self.steps_card.setObjectName("orbeaUpdatePimboCard")
        root.addWidget(self.steps_card)
        self.steps_title = BodyLabel(self)
        self.steps_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.steps_hint = CaptionLabel(self)
        self.steps_hint.setWordWrap(True)
        layout.addWidget(self.steps_title)
        layout.addWidget(self.steps_hint)
        row = QHBoxLayout()
        self.all_steps = PushButton(self)
        self.clear_steps = PushButton(self)
        row.addWidget(self.all_steps)
        row.addWidget(self.clear_steps)
        row.addStretch()
        layout.addLayout(row)
        self._config.extend((self.all_steps, self.clear_steps))
        grid = QGridLayout()
        self.checks = {}
        try:
            stored = screen._setting_get("orbea_workflow_options", {})
            stored = json.loads(stored) if isinstance(stored, str) else stored
            stored = stored if isinstance(stored, dict) else {}
        except (ValueError, TypeError):
            stored = {}
        ui_stages = tuple(stage for stage in OrbeaWorkflowOptions.STAGES if stage != "save") + ("save",)
        for index, stage in enumerate(ui_stages):
            check = CheckBox(self)
            value = stored.get(stage, True)
            check.setChecked(value if isinstance(value, bool) else str(value).casefold() in {"true", "1", "yes"})
            grid.addWidget(check, index // 3, index % 3)
            check.stateChanged.connect(self._options_changed)
            self.checks[stage] = check
        layout.addLayout(grid)
        self._config.extend(self.checks.values())
        row = QHBoxLayout()
        self.start = PrimaryPushButton(self)
        self.start.setMinimumSize(180, 38)
        self.stop = PushButton(self)
        self.retry_upload = PushButton(self)
        row.addWidget(self.start)
        row.addWidget(self.retry_upload)
        row.addWidget(self.stop)
        row.addStretch()
        layout.addLayout(row)
        export_row = QHBoxLayout()
        self.export_results = PushButton(self)
        self.export_results.clicked.connect(self._export_results)
        export_row.addWidget(self.export_results)
        export_row.addStretch()
        layout.addLayout(export_row)
        self.status = CaptionLabel(self)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.details = OrbeaDisclosure(self)
        layout.addWidget(self.details)
        self.log = PlainTextEdit(self)
        self.log.setReadOnly(True)
        self.log.setFixedHeight(140)
        self.log.setMaximumBlockCount(2500)
        self.details.body_layout.addWidget(self.log)
        self.browse.clicked.connect(self._browse)
        self.load.clicked.connect(self._load_saved)
        self.current.clicked.connect(self._load_current)
        self.select_all.clicked.connect(lambda: self._select(True))
        self.clear.clicked.connect(lambda: self._select(False))
        self.all_steps.clicked.connect(lambda: self._select_steps(True))
        self.clear_steps.clicked.connect(lambda: self._select_steps(False))
        self.table.itemChanged.connect(self.update_state)
        self.start.clicked.connect(self.start_upload)
        self.retry_upload.clicked.connect(self.retry_unfinished_uploads)
        self.stop.clicked.connect(self.request_stop)
        self.retranslate_ui()
        self.update_state()

    def _t(self, key, fallback, **kwargs):
        return self.screen._t(f"orbea.upload.{key}", fallback, **kwargs)

    def _status_text(self, status):
        return self._t(f"status.{status}", status.replace("_", " ").capitalize())

    def retranslate_ui(self):
        self.title.setText(self._t("title", "2. Choose products"))
        self.hint.setText(self._t("hint", "Collected products appear here automatically. Select the ones to update in Pimbo."))
        self.steps_title.setText(self._t("steps_title", "3. Update Pimbo"))
        self.steps_hint.setText(self._t("steps_hint", "Choose what to update, then upload. Each product is checked by its SKU; only Draft products are edited."))
        self.empty_hint.setText(self._t("empty", "Collect data above, or load products from a saved folder."))
        self.details.set_title(self._t("log", "Upload details and log"))
        self.folder.setPlaceholderText(self._t("folder", "Collected run or product folder"))
        for button, key, fallback in (
            (self.browse, "browse", "Choose another folder"), (self.load, "load", "Load saved products"),
            (self.current, "current", "Use current run"), (self.select_all, "select_all", "Select all products"),
            (self.clear, "clear", "Clear selection"), (self.start, "start", "Upload to Pimbo"),
            (self.stop, "stop", "Stop after current product"),
            (self.retry_upload, "retry_unfinished", "Retry failed and unprocessed uploads"),
            (self.export_results, "export_results", "Export upload results to Excel"),
            (self.all_steps, "all_steps", "Select all steps"), (self.clear_steps, "clear_steps", "Clear steps"),
        ):
            button.setText(self.screen.main.i18n.tr("layout.all" if key == "all_steps" else "layout.clear")
                if key in ("all_steps", "clear_steps") else self._t(key, fallback))
        self.retry_upload.setToolTip(self._t("retry_unfinished.tip", "Skip successful uploads and resume only unfinished steps on failed or unprocessed products."))
        self.table.setHorizontalHeaderLabels([self._t(key, label) for key, label in (
            ("selected", "Select"), ("sku", "SKU"), ("product", "Product"), ("status", "Status"), ("details", "Details"))])
        for stage, check in self.checks.items():
            check.setText(self._t(f"stage.{stage}", STAGE_LABELS[stage]))

    def options(self):
        return OrbeaWorkflowOptions(**{stage: check.isChecked() for stage, check in self.checks.items()})

    def _options_changed(self):
        self.screen._setting_set("orbea_workflow_options", json.dumps({stage: check.isChecked() for stage, check in self.checks.items()}))
        self.update_state()

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, self._t("folder", "Collected run or product folder"), self.folder.text())
        if folder:
            self.load_packages(folder)

    def _load_saved(self):
        root = self.screen._run_dir or self.screen._output_edit.text().strip() or self.folder.text().strip()
        if root:
            self.load_packages(root)

    def clear_products(self):
        self._finished_uploads = {}
        self.matches = ()
        self.results = []
        self.table.setRowCount(0)
        self.table.hide()
        self.empty_hint.show()
        self.source_label.hide()
        self.status.clear()
        self.update_state()

    def _load_current(self):
        root = self.screen._run_dir or self.screen._output_edit.text().strip()
        if root:
            self.load_packages(root)

    def load_packages(self, root):
        if self.is_running() or not root:
            return
        path = Path(root)
        if not path.is_dir():
            self.screen._warn(self._t("title", "Pimbo workflow"), self._t("invalid_folder", "Choose a folder containing collected Orbea products."))
            return
        try:
            self.matches = OrbeaUploadService.load_local_packages(path)
        except (OSError, ValueError) as error:
            self.screen._error(self._t("title", "Pimbo workflow"), str(error))
            return
        self.folder.setText(str(path))
        self.source_label.setText(str(path))
        self.source_label.show()
        self.screen._setting_set("orbea_upload_root", str(path))
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.matches))
        self._finished_uploads = {}
        for row, match in enumerate(self.matches):
            selection = QTableWidgetItem()
            selection.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled if match.ready else Qt.ItemFlag.NoItemFlags)
            finished = OrbeaUploadService.upload_finished(match) if match.ready else False
            self._finished_uploads[match.local_folder] = finished
            selection.setCheckState(Qt.CheckState.Checked if match.ready and not finished else Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, selection)
            prior = OrbeaUploadService.read_upload_result(match) if match.ready else None
            preparation = prior["preparation"] if prior else {}
            detail = " | ".join(filter(None, (match.note, preparation.get("error"), *preparation.get("warnings", []))))
            status = preparation.get("status") or match.status
            for column, value in enumerate((match.sku, match.pimbo_product_name or match.orbea_product_name, self._status_text(status), detail), start=1):
                item = QTableWidgetItem(value)
                item.setToolTip(f"{match.local_folder}\n{match.note}")
                self.table.setItem(row, column, item)
        self.table.blockSignals(False)
        self.table.setVisible(bool(self.matches))
        self.empty_hint.setVisible(not self.matches)
        self.results = []
        self._report_batch_error = ""
        self.status.setText(self._t("loaded", "{count} saved product(s) loaded", count=len(self.matches)))
        self.update_state()

    def _export_results(self):
        path, _ = QFileDialog.getSaveFileName(self, self._t("export_results", "Export upload results to Excel"),
                                             str(Path(self.folder.text()) / "orbea-upload-results.xlsx"), "Excel (*.xlsx)")
        if not path:
            return
        current = {result.match.local_folder: result_record(result) for result in self.results}
        try:
            rows = [upload_result_row(match, current.get(match.local_folder) or OrbeaUploadService.read_upload_result(match), brand="Orbea") for match in self.matches]
            write_upload_results(path, rows, context={"Collection folder": self.folder.text(),
                "Batch stop reason": getattr(self, "_report_batch_error", "")})
            self.status.setText(self._t("export_saved", "Upload results exported to {path}", path=path))
        except Exception as error:
            self.screen._error(self._t("export_results", "Export upload results to Excel"), str(error))

    def _select(self, checked):
        self.table.blockSignals(True)
        for row, match in enumerate(self.matches):
            if match.ready:
                self.table.item(row, 0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self.update_state()

    def retry_unfinished_uploads(self):
        if self.screen.is_running():
            return
        self.table.blockSignals(True)
        for row, match in enumerate(self.matches):
            finished = OrbeaUploadService.upload_finished(match) if match.ready else False
            self._finished_uploads[match.local_folder] = finished
            self.table.item(row, 0).setCheckState(Qt.CheckState.Checked if match.ready and not finished else Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self.update_state()
        self.start_upload(retry_unfinished=True)

    def _select_steps(self, checked):
        for check in self.checks.values():
            check.setChecked(checked)

    def selected_matches(self):
        return tuple(match for row, match in enumerate(self.matches) if match.ready
                     and self.table.item(row, 0).checkState() == Qt.CheckState.Checked)

    def is_running(self):
        return self._busy or bool(self.worker and self.worker.isRunning())

    def update_state(self, *_args):
        busy = self.is_running()
        other = any(worker and worker.isRunning() for worker in (
            self.screen._worker, self.screen._filter_worker, self.screen._description_worker,
            self.screen._photo_worker, self.screen._table_image_worker, self.screen._excel_sort_worker))
        for widget in self._config:
            widget.setEnabled(not busy and not other)
        self.start.setEnabled(bool(not busy and not other and getattr(self.screen.main, "driver", None) is not None
                                   and self.selected_matches() and self.options().any_selected))
        self.retry_upload.setEnabled(bool(not busy and not other and getattr(self.screen.main, "driver", None) is not None
                                          and self.options().save and self.options().any_selected
                                          and any(match.ready and not self._finished_uploads.get(match.local_folder, False) for match in self.matches)))
        self.export_results.setEnabled(bool(self.matches) and not busy and not other)
        self.stop.setEnabled(busy)
        self.stop.setVisible(busy)
        self.select_all.setVisible(bool(self.matches))
        self.clear.setVisible(bool(self.matches))

    def start_upload(self, *, retry_unfinished=False):
        if self.screen.is_running():
            return
        matches, options = self.selected_matches(), self.options()
        if not matches or not options.any_selected or getattr(self.screen.main, "driver", None) is None:
            return
        if len(matches) > 1 and not options.save:
            self.screen._warn(self._t("title", "Pimbo workflow"), self._t("single_unsaved", "Without Save, select only one product so you can review its changes."))
            return
        if options.specifications_magic_ai:
            try:
                stale_count = sum(OrbeaUploadService.specifications_need_recollection(match) for match in matches)
            except (OSError, ValueError) as error:
                self.screen._warn(self._t("title", "Pimbo workflow"), str(error))
                return
            if stale_count:
                message = self._t("specifications_recollect", "{count} selected product(s) have specifications from the old incomplete scrape. Use Retry matched downloads to recollect them, then reload the saved products.", count=stale_count)
                self.status.setText(message)
                self.screen._warn(self._t("title", "Pimbo workflow"), message)
                return
        if not self.screen._acquire_browser():
            return
        self.results = []
        self._report_batch_error = ""
        self.log.clear()
        self._busy = True
        self.worker = OrbeaUploadWorker(self.service_factory, matches, None, options, retry_unfinished=retry_unfinished)
        self.worker.progress_changed.connect(self._on_progress)
        self.worker.item_finished.connect(self._item_finished)
        self.worker.failed.connect(self._failed)
        self.worker.completed.connect(self._finish_activity)
        self.worker.finished.connect(self._finished)
        self.status.setText(self._t("running", "Running selected steps…"))
        if hasattr(self.screen.main, "track_worker"):
            record = self.screen.main.track_worker(self.worker, "upload", "orbea", output_path=self.folder.text())
            self._operation_id = getattr(record, "id", None)
        self.worker.start()
        self.screen._update_action_states()

    def _on_progress(self, message):
        self.log.appendPlainText(message)
        if self.worker._stop_requested:
            message = self._t("stopping", "Stopping after the current product…") + " " + message
        self.status.setText(message)

    def _item_finished(self, result):
        self.results.append(result)
        preparation = result.preparation
        self._finished_uploads[result.match.local_folder] = preparation.status.value in {"saved_automatically", "no_changes"}
        detail = " | ".join(filter(None, (preparation.error, *preparation.warnings)))
        self.log.appendPlainText(f"{result.match.sku}: {preparation.status.value}" + (f" — {detail}" if detail else ""))
        for row, match in enumerate(self.matches):
            if match.local_folder == result.match.local_folder:
                self.table.item(row, 3).setText(self._status_text(preparation.status.value))
                self.table.item(row, 4).setText(detail)
                if result.succeeded:
                    self.table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
                break
        self.status.setText(self._t("progress", "{done}/{total} product(s) finished", done=len(self.results), total=len(self.worker.matches)))

    def _failed(self, error):
        self._report_batch_error = error
        self.log.appendPlainText(error)
        self.screen._error(self._t("title", "Pimbo workflow"), error)

    def _finish_activity(self):
        tracker = getattr(self.screen.main, "operation_tracker", None)
        if tracker is None or not self._operation_id:
            return
        ok = sum(result.succeeded for result in self.results)
        failed = len(self.results) - ok
        warnings = sum(bool(result.preparation.warnings) for result in self.results)
        pending = len(self.worker.matches) - len(self.results)
        status = ("cancelled" if self.worker._stop_requested and pending else
                  "failed" if self.worker._batch_error or (not ok and (failed or pending)) else
                  "partial" if failed or warnings or pending else "succeeded")
        errors = self.worker._batch_error or " | ".join(result.preparation.error for result in self.results if result.preparation.error)
        tracker.finish(self._operation_id, status, summary={"succeeded": ok, "failed": failed,
            "warnings": warnings, "unprocessed": pending}, error_summary=errors, output_path=self.folder.text())

    def _finished(self):
        self._busy = False
        self.screen._release_browser()
        succeeded = sum(result.succeeded for result in self.results)
        warnings = sum(bool(result.preparation.warnings) for result in self.results)
        total = len(self.worker.matches)
        self.status.setText(self._t("finished", "Finished: {ok} successful, {failed} failed or blocked, {warnings} with warnings, {pending} unprocessed.",
            ok=succeeded, failed=len(self.results)-succeeded, warnings=warnings, pending=total-len(self.results)))
        reason = self.worker._batch_error or next((result.preparation.error for result in self.results if result.preparation.error), "")
        if reason:
            self.status.setText(self.status.text() + "\n" + self._t("failure_reason", "Reason: {reason}", reason=reason))
        self.screen._update_action_states()

    def request_stop(self):
        if self.worker and self.worker.isRunning():
            self.worker.request_stop()
            self.stop.setEnabled(False)
            self.status.setText(self._t("stopping", "Stopping after the current product…"))

"""Product-list actions for checking and repairing missing uploaded photos."""
from __future__ import annotations

from collections import Counter
from tools.orbea_automation.selected_downloads import product_identity, resolve_product_rows

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog

from .workers import OrbeaPimboPhotoScanWorker
from tools.orbea_automation.photo_scan import PimboPhotoScanService, load_photo_scan_collection


class OrbeaPhotoScanWorkflow:
    def __init__(self, panel):
        self.panel = panel
        self.screen = panel.screen
        self.scan_service_factory = lambda: PimboPhotoScanService(self.screen.main.driver)
        self.error = ""
        self.scanned = []

    def load_excel(self, path=None):
        if self.screen.is_running():
            return
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self.panel,
                self.panel._t("photo_scan.pick", "Select an Excel with product codes"),
                str(self.screen._setting_get("orbea_photo_scan_excel", self.screen._output_edit.text())), "Excel (*.xlsx)")
        if not path:
            return
        try:
            output = self.screen._output_edit.text().strip()
            if not output:
                raise ValueError("Choose the Orbea output folder first")
            _config, result = load_photo_scan_collection(path, output,
                browser_name=str(self.screen._setting_get("browser_choice", "Chrome") or "Chrome").lower())
            self.screen._run_dir = result.run_dir
            self.screen._workbook_path = result.workbook_path
            self.screen._download_selection = None
            self.screen._download_review_root = None
            self.screen._open_excel_btn.setEnabled(True)
            self.screen._open_folder_btn.setEnabled(True)
            self.panel.load_packages(result.run_dir)
            self.screen._setting_set("orbea_photo_scan_excel", str(path))
            self.panel.status.setText(self.panel._t("photo_scan.loaded",
                "{count} products loaded. Scan Pimbo to check their uploaded photos.", count=len(self.panel.matches)))
            self.screen._switch_section("upload")
            self.screen._update_action_states()
        except Exception as error:
            self.screen._error(self.panel._t("photo_scan.title", "Pimbo photo scan"), str(error))

    def select_missing(self):
        self.panel._select_by_status("no_photos")

    def scan(self):
        panel = self.panel
        if self.screen.is_running() or self.screen.main.driver is None:
            return
        matches = panel.selected_products()
        if not matches:
            return
        try:
            jobs = {}
            for config, row in resolve_product_rows(matches):
                jobs.setdefault(config.resume_run_dir, []).append(row["sku"])
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.screen._warn(panel._t("photo_scan.title", "Pimbo photo scan"), str(error))
            return
        if not self.screen._acquire_browser():
            return
        self._start(lambda: OrbeaPimboPhotoScanWorker(self.scan_service_factory,
                    jobs=tuple((root, tuple(skus)) for root, skus in jobs.items())))

    def download(self):
        self.screen._download_selected(mode="pimbo_photos")

    def _start(self, worker):
        panel = self.panel
        self.error, self.scanned = "", []
        self.selection = self.screen.workflow_controller.remember_selection(panel)
        panel._busy = True
        panel.log.clear()
        self.screen.workflow_controller.start_job("photo_scan", worker,
            owner=panel, attribute="worker", operation_attribute="_operation_id",
            details={"output_path": panel.folder.text()},
            signals={"progress_changed": self._progress, "log_message": panel.log.appendPlainText,
                     "failed": self._failed, "item_finished": self._item_finished},
            finished=self._finished, failed=self._failed)

    def _progress(self, update):
        message = getattr(update, "message", update)
        self.panel.status.setText(str(message))

    def _item_finished(self, result):
        self.scanned.append(result)
        panel = self.panel
        for row, match in enumerate(panel.matches):
            if match.sku == result.sku and (not result.checkpoint_path or match.checkpoint_path == result.checkpoint_path):
                panel._photo_statuses[match.local_folder] = vars(result)
                panel.table.item(row, 5).setText(panel._photo_status_text(vars(result)))
                panel.table.item(row, 5).setToolTip(result.error)
                if result.product_name:
                    panel.table.item(row, 2).setText(result.product_name)

    def _failed(self, message):
        self.error = message
        self.panel.log.appendPlainText(message)
        if not self.screen._closing:
            self.screen._error(self.panel._t("photo_scan.title", "Pimbo photo scan"), message)

    def _finished(self):
        panel = self.panel
        cancelled = panel.worker.stop_requested
        panel._busy = False
        panel.load_packages(panel.folder.text(), internal=True)
        self.screen._refresh_report_path(panel.folder.text())
        panel.table.blockSignals(True)
        for row, match in enumerate(panel.matches):
            panel.table.item(row, 0).setCheckState(self.selection.get(product_identity(match), Qt.CheckState.Unchecked))
        panel.table.blockSignals(False)
        counts = Counter(result.status for result in self.scanned)
        message = panel._t("photo_scan.finished",
            "Checked {checked}: {missing} no photos, {present} with photos, {not_found} not found, {errors} errors.",
            checked=len(self.scanned), missing=counts["no_photos"], present=counts["has_photos"],
            not_found=counts["not_found"], errors=counts["scan_error"])
        errors = counts["scan_error"] + counts["not_found"]
        if cancelled:
            message = panel._t("photo_scan.stopped", "Stopped. Completed checks and downloads are saved.") + " " + message
        if self.error:
            message = self.error
        panel.status.setText(message)
        tracker = getattr(self.screen.main, "operation_tracker", None)
        if tracker and panel._operation_id:
            tracker.finish(panel._operation_id, "cancelled" if cancelled else "failed" if self.error else "partial" if errors else "succeeded",
                           summary={"checked": len(self.scanned), "errors": errors}, error_summary=self.error,
                           output_path=panel.folder.text())
        self.screen._update_action_states()

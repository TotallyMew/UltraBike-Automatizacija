"""Check selected Pimbo bikes for missing required fields without editing them."""
from collections import Counter
from PySide6.QtCore import Qt

from tools.orbea_automation.content_scan import PimboContentScanService
from tools.orbea_automation.selected_downloads import product_identity, resolve_product_rows
from .workers import OrbeaPimboContentScanWorker


class OrbeaContentScanWorkflow:
    def __init__(self, panel):
        self.panel, self.screen = panel, panel.screen
        self.scan_service_factory = lambda: PimboContentScanService(self.screen.main.driver)
        self.error, self.scanned = "", []

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
            self.screen._warn(panel._t("content_scan.title", "Missing Pimbo data"), str(error))
            return
        if not self.screen._acquire_browser():
            return
        self.error, self.scanned = "", []
        self.selection = self.screen.workflow_controller.remember_selection(panel)
        panel._busy = True
        panel.log.clear()
        panel.details.show()
        self.screen.workflow_controller.start_job("content_scan",
            lambda: OrbeaPimboContentScanWorker(self.scan_service_factory,
                jobs=tuple((root, tuple(skus)) for root, skus in jobs.items())),
            owner=panel, attribute="worker", operation_attribute="_operation_id",
            details={"output_path": panel.folder.text()},
            signals={"progress_changed": self._progress, "log_message": panel.log.appendPlainText,
                     "failed": self._failed, "item_finished": self._item_finished},
            finished=self._finished, failed=self._failed)

    def _progress(self, update):
        self.panel.status.setText(str(getattr(update, "message", update)))

    def _item_finished(self, result):
        self.scanned.append(result)
        panel = self.panel
        for row, match in enumerate(panel.matches):
            if match.sku == result.sku and match.checkpoint_path == result.checkpoint_path:
                state = vars(result)
                panel._content_statuses[match.local_folder] = state
                panel.table.item(row, 6).setText(panel._content_status_text(state))
                panel.table.item(row, 6).setToolTip(panel._content_details(state))

    def _failed(self, message):
        self.error = message
        self.panel.log.appendPlainText(message)
        if not self.screen._closing:
            self.screen._error(self.panel._t("content_scan.title", "Missing Pimbo data"), message)

    def _finished(self):
        panel = self.panel
        cancelled = panel.worker.stop_requested
        panel._busy = False
        panel.load_packages(panel.folder.text(), internal=True)
        self.screen._refresh_report_path(panel.folder.text())
        blocked = panel.table.blockSignals(True)
        try:
            for row, match in enumerate(panel.matches):
                panel.table.item(row, 0).setCheckState(self.selection.get(product_identity(match), Qt.CheckState.Unchecked))
        finally:
            panel.table.blockSignals(blocked)
        counts = Counter(result.status for result in self.scanned)
        errors = counts["content_scan_error"] + counts["content_not_found"]
        message = panel._t("content_scan.finished", "Checked {checked}: {missing} missing data, {complete} complete, {errors} errors or not found.",
            checked=len(self.scanned), missing=counts["missing_content"], complete=counts["content_complete"], errors=errors)
        if cancelled:
            message = panel._t("content_scan.stopped", "Stopped. Completed checks are saved.") + " " + message
        panel.status.setText(self.error or message)
        tracker = getattr(self.screen.main, "operation_tracker", None)
        if tracker and panel._operation_id:
            tracker.finish(panel._operation_id, "cancelled" if cancelled else "failed" if self.error else "partial" if errors else "succeeded",
                summary={"checked": len(self.scanned), "errors": errors}, error_summary=self.error, output_path=panel.folder.text())
        self.screen._update_action_states()

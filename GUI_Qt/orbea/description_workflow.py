"""Orbea description job validation, progress and results."""

from pathlib import Path

from qfluentwidgets import FluentIcon

from .controller import _read
from .direct_workflow import OrbeaDirectWorkflow
from .workers import OrbeaDescriptionWorker


class DescriptionWorkflow(OrbeaDirectWorkflow):
    prefix = "description"
    output_attribute = "_description_output_dir"
    translation_prefix = "orbea.description"
    start_key = "orbea.description.extract"
    start_text = "Extract descriptions"
    starting_text = "Starting description extraction…"
    start_icon = FluentIcon.PLAY

    def start_stop(self):
        view = self.screen
        if view._description_worker and view._description_worker.isRunning():
            view._description_worker.request_stop()
            view._description_start_btn.setEnabled(False)
            view._description_status_label.setText(
                view._t("orbea.description.stopping", "Stopping safely…")
            )
            return
        if view.is_running() or not self.validate_inputs():
            return
        view._closing = False
        try:
            config = view._create_description_config()
        except Exception as exc:
            view._error(
                view._t("orbea.description.service_error.title", "Description extractor unavailable"),
                str(exc),
            )
            return

        view._save_description_output()
        view._description_output_dir = Path(view._description_output_edit.text().strip())
        view._description_open_btn.setEnabled(False)
        view._description_log.clear()
        view._description_progress.setValue(0)
        self.set_busy(True)
        worker = OrbeaDescriptionWorker(view._make_description_service, config)
        self.start_worker(worker)

    def validate_inputs(self) -> bool:
        view = self.screen
        if not view._description_urls():
            view._warn(
                view._t("orbea.description.urls_invalid.title", "Orbea URL required"),
                view._t(
                    "orbea.description.urls_invalid",
                    "Paste one or more www.orbea.com or cms.orbea.com product or model URLs.",
                ),
            )
            return False
        if not view._description_output_edit.text().strip():
            view._warn(
                view._t("orbea.description.output_invalid.title", "Output folder required"),
                view._t("orbea.description.output_invalid", "Choose where extracted text should be saved."),
            )
            return False
        return True

    def on_progress(self, update):
        view = self.screen
        status = str(_read(update, "status", "stage", default="Extracting") or "Extracting")
        current = int(_read(update, "current", "done", default=0) or 0)
        total = int(_read(update, "total", default=0) or 0)
        message = str(_read(update, "message", "url", default="") or "")
        succeeded = int(_read(update, "succeeded", default=0) or 0)
        failed = int(_read(update, "failed", default=0) or 0)
        view._description_status_label.setText(status.replace("_", " ").title())
        if message:
            view._description_progress_label.setText(message)
        elif total:
            view._description_progress_label.setText(
                view._t(
                    "orbea.description.progress",
                    "{current:,} / {total:,} URLs • {succeeded:,} saved • {failed:,} failed",
                    current=current,
                    total=total,
                    succeeded=succeeded,
                    failed=failed,
                )
            )
        view._description_progress.setValue(
            max(0, min(100, int(current * 100 / total))) if total else 0
        )

    def on_result(self, result):
        view = self.screen
        output_dir = _read(result, "output_dir", "output_root", default=None)
        if output_dir:
            view._description_output_dir = Path(output_dir)
        files = _read(result, "files", "written_files", "paths", default=()) or ()
        succeeded = int(_read(result, "succeeded", default=len(files)) or 0)
        failures = _read(result, "failures", default=()) or ()
        cancelled = bool(_read(result, "cancelled", default=False))
        if cancelled:
            view._description_status_label.setText(
                view._t("orbea.description.stopped", "Stopped — completed text files were kept")
            )
        elif failures:
            view._description_status_label.setText(
                view._t("orbea.description.partial", "Completed with some failed descriptions")
            )
            view._description_progress.setValue(100)
        else:
            view._description_status_label.setText(
                view._t("orbea.description.complete", "Description extraction complete")
            )
            view._description_progress.setValue(100)
        view._description_progress_label.setText(
            view._t(
                "orbea.description.result",
                "{succeeded:,} saved • {failed:,} failed",
                succeeded=succeeded,
                failed=len(failures),
            )
        )

        if failures and not cancelled:
            view._warn(
                view._t("orbea.description.partial.title", "Some descriptions were not extracted"),
                view._t(
                    "orbea.description.partial.detail",
                    "Completed text files were kept. Check the activity log for failed URLs.",
                ),
            )

    def on_error(self, message: str):
        view = self.screen
        view._description_status_label.setText(
            view._t("orbea.description.failed", "Description extraction failed")
        )
        view._append_description_log(message)
        if not view._closing:
            view._error(
                view._t("orbea.description.failed.title", "Description extraction failed"),
                message,
            )


"""Orbea photo job validation, progress and results."""

from pathlib import Path

from qfluentwidgets import FluentIcon

from .controller import _read
from .direct_workflow import OrbeaDirectWorkflow
from .workers import OrbeaPhotoWorker


class PhotoWorkflow(OrbeaDirectWorkflow):
    prefix = "photo"
    output_attribute = "_photo_output_dir"
    translation_prefix = "orbea.photo"
    start_key = "orbea.photo.download"
    start_text = "Download all colours"
    starting_text = "Reading product colours…"
    start_icon = FluentIcon.DOWNLOAD

    def start_stop(self):
        view = self.screen
        if view._photo_worker and view._photo_worker.isRunning():
            view._photo_worker.request_stop()
            view._photo_start_btn.setEnabled(False)
            view._photo_status_label.setText(
                view._t("orbea.photo.stopping", "Stopping safely…")
            )
            return
        if view.is_running() or not self.validate_inputs():
            return

        view._closing = False
        _unique, _duplicates, _invalid, entries = view._photo_link_state()
        output_dir = Path(view._photo_output_edit.text().strip())
        view._save_photo_output()
        view._photo_output_dir = output_dir
        view._photo_open_btn.setEnabled(False)
        view._photo_log.clear()
        view._photo_progress.setValue(0)
        self.set_busy(True)
        worker = OrbeaPhotoWorker(
            view._make_photo_service, entries, output_dir
        )
        self.start_worker(worker, total=len(entries))

    def validate_inputs(self) -> bool:
        view = self.screen
        urls, _duplicates, invalid, _entries = view._photo_link_state()
        if invalid:
            view._warn(
                view._t("orbea.photo.urls_invalid.title", "Some product links are invalid"),
                view._t(
                    "orbea.photo.urls_invalid",
                    "Fix or remove {count:,} invalid lines. Enter one Orbea product URL per line.",
                    count=len(invalid),
                ),
            )
            return False
        if not urls:
            view._warn(
                view._t("orbea.photo.url_invalid.title", "Orbea product URLs required"),
                view._t(
                    "orbea.photo.url_invalid",
                    "Paste one or more public cms.orbea.com bicycle product URLs.",
                ),
            )
            return False
        if not view._photo_output_edit.text().strip():
            view._warn(
                view._t("orbea.photo.output_invalid.title", "Output folder required"),
                view._t(
                    "orbea.photo.output_invalid",
                    "Choose where product photo folders should be saved.",
                ),
            )
            return False
        return True

    def on_progress(self, update):
        view = self.screen
        status = str(_read(update, "status", default="downloading") or "downloading")
        current = int(_read(update, "current", default=0) or 0)
        total = int(_read(update, "total", default=0) or 0)
        succeeded = int(_read(update, "succeeded", default=0) or 0)
        failed = int(_read(update, "failed", default=0) or 0)
        message = str(_read(update, "message", default="") or "")
        view._photo_status_label.setText(status.replace("_", " ").title())
        view._photo_progress.setValue(
            max(0, min(100, int(current * 100 / total))) if total else 0
        )
        view._photo_progress_label.setText(
            message
            or view._t(
                "orbea.photo.progress",
                "{current:,} / {total:,} images • {succeeded:,} saved • {failed:,} failed",
                current=current,
                total=total,
                succeeded=succeeded,
                failed=failed,
            )
        )

    def on_result(self, result):
        view = self.screen
        product_results = _read(result, "product_results", default=()) or ()
        product_dir = _read(result, "product_dir", default=None)
        if not product_dir and len(product_results) == 1:
            product_dir = _read(product_results[0], "product_dir", default=None)
        if not product_dir:
            product_dir = _read(result, "output_dir", default=None)
        if product_dir:
            view._photo_output_dir = Path(product_dir)
        files = _read(result, "files", default=()) or ()
        failures = _read(result, "failures", default=()) or ()
        unavailable = _read(result, "unavailable", default=()) or ()
        variants = int(_read(result, "variants", default=0) or 0)
        products = int(_read(result, "products", default=1 if files else 0) or 0)
        duplicates = int(_read(result, "duplicates", default=0) or 0)
        duplicate_summary = (
            view._t("orbea.photo.urls.duplicate.one", "1 duplicate ignored")
            if duplicates == 1
            else view._t(
                "orbea.photo.urls.duplicate.many",
                "{count:,} duplicates ignored",
                count=duplicates,
            )
        )
        cancelled = bool(_read(result, "cancelled", default=False))
        if cancelled:
            view._photo_status_label.setText(
                view._t("orbea.photo.stopped", "Stopped — completed photos were kept")
            )
        elif failures:
            view._photo_status_label.setText(
                view._t("orbea.photo.partial", "Completed with some failed photos")
            )
            view._photo_progress.setValue(100)
        else:
            view._photo_status_label.setText(
                view._t("orbea.photo.complete", "Photo download complete")
            )
            view._photo_progress.setValue(100)
        view._photo_progress_label.setText(
            view._t(
                "orbea.photo.result",
                "Products {products:,} • Colours {variants:,} • Photos saved {saved:,} • {duplicate_summary} • Unavailable {unavailable:,} • Failed {failed:,}",
                products=products,
                variants=variants,
                saved=len(files),
                duplicate_summary=duplicate_summary,
                unavailable=len(unavailable),
                failed=len(failures),
            )
        )
        if failures and not cancelled:
            view._warn(
                view._t("orbea.photo.partial.title", "Some photos were not downloaded"),
                view._t(
                    "orbea.photo.partial.detail",
                    "The successful photos were kept. Check the activity log for details.",
                ),
            )

    def on_error(self, message: str):
        view = self.screen
        view._photo_status_label.setText(
            view._t("orbea.photo.failed", "Photo download failed")
        )
        view._append_photo_log(message)
        if not view._closing:
            view._error(
                view._t("orbea.photo.failed.title", "Photo download failed"),
                message,
            )


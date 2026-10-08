"""Orbea table image job validation, progress and results."""

from pathlib import Path

from qfluentwidgets import FluentIcon

from .controller import _read
from .direct_workflow import OrbeaDirectWorkflow
from .workers import OrbeaTableImageWorker


class TableImageWorkflow(OrbeaDirectWorkflow):
    prefix = "table_image"
    output_attribute = "_table_output_dir"
    translation_prefix = "orbea.tables"
    start_key = "orbea.tables.download"
    start_text = "Download selected"
    starting_text = "Opening Orbea product pages…"
    start_icon = FluentIcon.DOWNLOAD

    def start_stop(self):
        view = self.screen
        if view._table_image_worker and view._table_image_worker.isRunning():
            view._table_image_worker.request_stop()
            view._table_image_start_btn.setEnabled(False)
            view._table_image_status_label.setText(
                view._t("orbea.tables.stopping", "Stopping safely…")
            )
            return
        if view.is_running() or not self.validate_inputs():
            return

        view._closing = False
        _unique, _duplicates, _invalid, entries = view._table_image_link_state()
        geometry, size_guide, product_photos = view._table_image_selection()
        output_dir = Path(view._table_image_output_edit.text().strip())
        view._save_table_image_output()
        view._table_output_dir = output_dir
        view._table_image_open_btn.setEnabled(False)
        view._table_image_log.clear()
        view._table_image_log.setVisible(True)
        view._table_image_progress.setValue(0)
        self.set_busy(True)
        worker = OrbeaTableImageWorker(
            view._make_table_image_service,
            entries,
            output_dir,
            download_geometry=geometry,
            download_size_guide=size_guide,
            download_product_photos=product_photos,
        )
        self.start_worker(worker, total=len(entries))

    def validate_inputs(self) -> bool:
        view = self.screen
        urls, _duplicates, invalid, _entries = view._table_image_link_state()
        if not any(view._table_image_selection()):
            view._warn(
                view._t(
                    "orbea.tables.selection_invalid.title",
                    "Choose what to download",
                ),
                view._t(
                    "orbea.tables.selection_invalid",
                    "Select geometry, the CM size guide, product photos, or any combination.",
                ),
            )
            return False
        if invalid:
            view._warn(
                view._t(
                    "orbea.tables.urls_invalid.title",
                    "Some product links are invalid",
                ),
                view._t(
                    "orbea.tables.urls_invalid",
                    "Fix or remove {count:,} invalid lines. Enter one Orbea product URL per line.",
                    count=len(invalid),
                ),
            )
            return False
        if not urls:
            view._warn(
                view._t(
                    "orbea.tables.url_invalid.title",
                    "Orbea product URLs required",
                ),
                view._t(
                    "orbea.tables.url_invalid",
                    "Paste one or more public Orbea bicycle product-page URLs.",
                ),
            )
            return False
        if not view._table_image_output_edit.text().strip():
            view._warn(
                view._t(
                    "orbea.tables.output_invalid.title",
                    "Output folder required",
                ),
                view._t(
                    "orbea.tables.output_invalid",
                    "Choose where the selected Orbea images should be saved.",
                ),
            )
            return False
        return True

    def on_progress(self, update):
        view = self.screen
        status = str(_read(update, "status", default="downloading") or "downloading")
        current = int(_read(update, "current", default=0) or 0)
        total = int(_read(update, "total", default=0) or 0)
        message = str(_read(update, "message", default="") or "")
        status_fallbacks = {
            "opening_page": "Opening product page…",
            "saved": "Images saved",
            "partial": "Some images could not be saved",
            "downloading": "Downloading images…",
            "product_photos": "Downloading product photos…",
        }
        view._table_image_status_label.setText(
            view._t(
                f"orbea.tables.status.{status}",
                status_fallbacks.get(status, status.replace("_", " ").title()),
            )
        )
        view._table_image_progress.setValue(
            max(0, min(100, int(current * 100 / total))) if total else 0
        )
        view._table_image_progress_label.setText(
            message
            or view._t(
                "orbea.tables.progress",
                "{current:,} / {total:,} products",
                current=current,
                total=total,
            )
        )

    def on_result(self, result):
        view = self.screen
        output_dir = _read(result, "output_dir", default=None)
        if output_dir:
            view._table_output_dir = Path(output_dir)
        files = _read(result, "files", default=()) or ()
        failures = _read(result, "failures", default=()) or ()
        unavailable = _read(result, "unavailable", default=()) or ()
        products = int(_read(result, "products", default=0) or 0)
        duplicates = int(_read(result, "duplicates", default=0) or 0)
        photo_variants = int(_read(result, "photo_variants", default=0) or 0)
        photo_views = int(_read(result, "photo_views", default=0) or 0)
        cancelled = bool(_read(result, "cancelled", default=False))
        if cancelled:
            view._table_image_status_label.setText(
                view._t(
                    "orbea.tables.stopped",
                    "Stopped — completed images were kept",
                )
            )
        elif failures:
            view._table_image_status_label.setText(
                view._t(
                    "orbea.tables.partial",
                    "Completed with some failed images",
                )
            )
            view._table_image_progress.setValue(100)
        else:
            view._table_image_status_label.setText(
                view._t("orbea.tables.complete", "Image download complete")
            )
            view._table_image_progress.setValue(100)
        view._table_image_progress_label.setText(
            view._t(
                "orbea.tables.result",
                "Products {products:,} • Images saved {saved:,} • Photo colours {photo_variants:,} • Photo views {photo_views:,} • Duplicates ignored {duplicates:,} • Unavailable {unavailable:,} • Failed {failed:,}",
                products=products,
                saved=len(files),
                photo_variants=photo_variants,
                photo_views=photo_views,
                duplicates=duplicates,
                unavailable=len(unavailable),
                failed=len(failures),
            )
        )
        if failures and not cancelled:
            view._warn(
                view._t(
                    "orbea.tables.partial.title",
                    "Some images were not downloaded",
                ),
                view._t(
                    "orbea.tables.partial.detail",
                    "Successful images were kept. Check the activity log for details.",
                ),
            )

    def on_error(self, message: str):
        view = self.screen
        view._table_image_status_label.setText(
            view._t("orbea.tables.failed", "Image download failed")
        )
        view._append_table_image_log(message)
        if not view._closing:
            view._error(
                view._t("orbea.tables.failed.title", "Image download failed"),
                message,
            )


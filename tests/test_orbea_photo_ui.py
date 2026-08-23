from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from GUI_Qt.screens.OrbeaScreen import OrbeaScreen
from tools.orbea_automation import (
    OrbeaPhotoBatchResult,
    OrbeaPhotoProgress,
    OrbeaPhotoRunResult,
    unique_orbea_product_urls,
)


class _Settings:
    def __init__(self, values):
        self.values = dict(values)

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


class _I18n:
    @staticmethod
    def tr(key, **_kwargs):
        return key


class _Main(QWidget):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.i18n = _I18n()
        self.driver = None


class _PhotoService:
    def cancel(self):
        pass

    def run(self, url, output_dir, *, progress, log, cancellation):
        product_dir = Path(output_dir) / "Kimu_27_H20_2027"
        product_dir.mkdir(parents=True, exist_ok=True)
        photo = product_dir / "J3_Cobalt_Blue" / "J3_side.png"
        photo.parent.mkdir(parents=True, exist_ok=True)
        photo.write_bytes(b"png")
        progress(
            OrbeaPhotoProgress(
                current=1,
                total=1,
                status="saved",
                message="Saved J3_side.png",
                variant="J3",
                view="side",
                succeeded=1,
            )
        )
        log("Saved J3_side.png")
        return OrbeaPhotoRunResult(
            output_dir=Path(output_dir),
            product_dir=product_dir,
            title="Kimu 27 H20 2027",
            variants=1,
            views=1,
            files=(photo,),
            failures=(),
            cancelled=False,
        )

    def run_many(self, urls, output_dir, *, progress, log, cancellation):
        unique, duplicates = unique_orbea_product_urls(urls)
        results = tuple(
            self.run(
                url,
                output_dir,
                progress=progress,
                log=log,
                cancellation=cancellation,
            )
            for url in unique
        )
        return OrbeaPhotoBatchResult(
            output_dir=Path(output_dir),
            product_results=results,
            requested=len(tuple(urls)),
            products=len(results),
            duplicates=len(duplicates),
            variants=sum(result.variants for result in results),
            views=sum(result.views for result in results),
            files=tuple(path for result in results for path in result.files),
            failures=(),
            unavailable=(),
            cancelled=False,
        )


class OrbeaPhotoUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        catalogue = root / "catalogue.xlsx"
        catalogue.touch()
        self.photo_output = root / "photos"
        self.settings = _Settings(
            {
                "orbea_catalogue_path": str(catalogue),
                "orbea_output_root": str(root / "runs"),
                "orbea_photo_output": str(self.photo_output),
            }
        )
        self.main = _Main(self.settings)
        self.screen = OrbeaScreen(
            self.main,
            photo_service_factory=_PhotoService,
        )
        self.app.processEvents()

    def tearDown(self):
        self.assertTrue(self.screen.shutdown())
        self.screen.deleteLater()
        self.main.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def _wait_for_worker(self, timeout=3.0):
        deadline = time.monotonic() + timeout
        while self.screen.is_running() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()
        self.assertFalse(self.screen.is_running())

    def test_download_runs_in_worker_and_opens_the_product_folder(self):
        self.screen._photo_url_edit.setPlainText(
            "cms.orbea.com/en-au/kimu-27-h20?unused=1"
        )
        self.app.processEvents()
        self.assertTrue(self.screen._photo_start_btn.isEnabled())

        self.screen._on_photo_start_stop()
        self._wait_for_worker()

        product_dir = self.photo_output / "Kimu_27_H20_2027"
        self.assertTrue((product_dir / "J3_Cobalt_Blue" / "J3_side.png").is_file())
        self.assertEqual(self.screen._photo_urls(), (PRODUCT_URL,))
        self.assertEqual(self.screen._photo_progress.value(), 100)
        self.assertIn("complete", self.screen._photo_status_label.text().lower())
        self.assertIn("unavailable", self.screen._photo_progress_label.text().lower())
        self.assertTrue(self.screen._photo_open_btn.isEnabled())
        self.assertEqual(self.screen._photo_output_dir, product_dir)
        self.assertEqual(
            self.settings.values["orbea_photo_output"], str(self.photo_output)
        )

    def test_duplicate_links_are_detected_and_do_not_block_the_batch(self):
        second = "https://cms.orbea.com/en-au/terra-h30"
        self.screen._photo_url_edit.setPlainText(
            f"{PRODUCT_URL}\n{PRODUCT_URL}/?tracking=1\n{second}"
        )
        self.app.processEvents()

        urls, duplicates, invalid, entries = self.screen._photo_link_state()
        self.assertEqual(urls, (PRODUCT_URL, second))
        self.assertEqual(duplicates, 1)
        self.assertFalse(invalid)
        self.assertEqual(len(entries), 3)
        self.assertIn("1 duplicate ignored", self.screen._photo_urls_hint.text())
        self.assertTrue(self.screen._photo_start_btn.isEnabled())

    def test_invalid_line_disables_download_without_hiding_valid_links(self):
        self.screen._photo_url_edit.setPlainText(
            f"{PRODUCT_URL}\nhttps://example.com/not-orbea"
        )
        self.app.processEvents()

        urls, duplicates, invalid, _entries = self.screen._photo_link_state()
        self.assertEqual(urls, (PRODUCT_URL,))
        self.assertEqual(duplicates, 0)
        self.assertEqual(len(invalid), 1)
        self.assertFalse(self.screen._photo_start_btn.isEnabled())

    def test_multi_product_worker_reports_ignored_duplicates(self):
        second = "https://cms.orbea.com/en-au/terra-h30"
        self.screen._photo_url_edit.setPlainText(
            f"{PRODUCT_URL}\n{PRODUCT_URL}/?tracking=1\n{second}"
        )
        self.app.processEvents()

        self.screen._on_photo_start_stop()
        self._wait_for_worker()

        summary = self.screen._photo_progress_label.text().lower()
        self.assertIn("products 2", summary)
        self.assertIn("1 duplicate ignored", summary)
        self.assertEqual(self.screen._photo_output_dir, self.photo_output)


PRODUCT_URL = "https://cms.orbea.com/en-au/kimu-27-h20"


if __name__ == "__main__":
    unittest.main()

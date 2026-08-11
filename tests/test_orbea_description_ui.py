from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from GUI_Qt.screens.OrbeaScreen import OrbeaScreen
from tools.orbea_automation import DescriptionProgress, DescriptionRunResult


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


class _DescriptionService:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def run(self, config, *, progress, log, cancellation):
        config.output_dir.mkdir(parents=True, exist_ok=True)
        destination = config.output_dir / "kemen-adv.txt"
        destination.write_text("Kemen ADV", encoding="utf-8")
        progress(
            DescriptionProgress(
                current=1,
                total=1,
                url=config.urls[0],
                status="saved",
                succeeded=1,
            )
        )
        log("Saved kemen-adv.txt")
        return DescriptionRunResult(
            output_dir=config.output_dir,
            files=(destination,),
            succeeded=1,
            failures=(),
            cancelled=False,
        )


class OrbeaDescriptionUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        catalogue = root / "catalogue.xlsx"
        catalogue.touch()
        self.description_output = root / "descriptions"
        self.settings = _Settings(
            {
                "orbea_catalogue_path": str(catalogue),
                "orbea_output_root": str(root / "runs"),
                "orbea_description_output": str(self.description_output),
                "browser_choice": "Edge",
            }
        )
        self.main = _Main(self.settings)
        self.screen = OrbeaScreen(
            self.main,
            description_service_factory=_DescriptionService,
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

    def test_config_uses_urls_saved_output_and_browser_choice(self):
        self.screen._description_urls_edit.setPlainText(
            "https://cms.orbea.com/en-au/m/kemen-adv\n"
            "https://cms.orbea.com/en-au/m/kemen-adv\n"
            "https://example.com/not-orbea"
        )
        config = self.screen._create_description_config()

        self.assertEqual(config.urls, ("https://cms.orbea.com/en-au/m/kemen-adv",))
        self.assertEqual(config.output_dir, self.description_output.resolve())
        self.assertEqual(config.browser_name, "edge")
        self.assertFalse(config.show_browser)

    def test_extract_runs_in_worker_and_enables_output_folder(self):
        self.screen._description_urls_edit.setPlainText(
            "https://cms.orbea.com/en-au/m/kemen-adv"
        )
        self.app.processEvents()
        self.assertTrue(self.screen._description_start_btn.isEnabled())

        self.screen._on_description_start_stop()
        self._wait_for_worker()

        self.assertTrue((self.description_output / "kemen-adv.txt").is_file())
        self.assertTrue(self.screen._description_open_btn.isEnabled())
        self.assertEqual(self.screen._description_progress.value(), 100)
        self.assertIn("complete", self.screen._description_status_label.text().lower())
        self.assertEqual(
            self.settings.values["orbea_description_output"],
            str(self.description_output),
        )


if __name__ == "__main__":
    unittest.main()

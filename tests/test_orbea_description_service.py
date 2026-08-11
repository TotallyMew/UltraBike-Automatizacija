from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.orbea_automation.descriptions import (
    DescriptionRunConfig,
    OrbeaDescriptionService,
)
from tools.orbea_automation.models import CancellationToken
from tools.orbea_description_extractor import DescriptionDocument


def _document(url: str, model: str) -> DescriptionDocument:
    return DescriptionDocument(
        url=url,
        model=model,
        main_lines=[model, f"Description for {model}."],
        expanded_sections=[["Expanded", f"More about {model}."]],
    )


class _FakeDriver:
    def __init__(self) -> None:
        self.quit_calls = 0

    def quit(self) -> None:
        self.quit_calls += 1


class OrbeaDescriptionServiceTests(unittest.TestCase):
    def test_config_normalizes_and_deduplicates_urls(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DescriptionRunConfig(
                urls=(
                    "cms.orbea.com/en-au/m/kemen-adv/?x=1",
                    "https://cms.orbea.com/en-au/m/kemen-adv",
                ),
                output_dir=Path(temp_dir),
                browser_name="Chrome",
            )
        self.assertEqual(
            config.urls, ("https://cms.orbea.com/en-au/m/kemen-adv",)
        )
        self.assertEqual(config.browser_name, "chrome")

    def test_run_saves_successes_and_failures_and_closes_owned_driver(self):
        driver = _FakeDriver()
        progress = []
        urls = (
            "https://cms.orbea.com/en-au/m/kemen-adv",
            "https://cms.orbea.com/en-au/m/rise-lt",
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "tools.orbea_automation.descriptions.extract_description",
            side_effect=[_document(urls[0], "Kemen Adv"), RuntimeError("render failed")],
        ):
            result = OrbeaDescriptionService(lambda *_: driver).run(
                DescriptionRunConfig(urls=urls, output_dir=Path(temp_dir)),
                progress=progress.append,
            )

            self.assertEqual(result.succeeded, 1)
            self.assertEqual(len(result.failures), 1)
            self.assertFalse(result.cancelled)
            self.assertEqual(driver.quit_calls, 1)
            self.assertTrue((Path(temp_dir) / "kemen-adv.txt").is_file())
            self.assertTrue(
                (Path(temp_dir) / "all_orbea_descriptions.txt").is_file()
            )
            errors = (Path(temp_dir) / "description_errors.txt").read_text(
                encoding="utf-8-sig"
            )
            self.assertIn("render failed", errors)
            status = (Path(temp_dir) / "description_run_status.txt").read_text(
                encoding="utf-8-sig"
            )
            self.assertIn("Descriptions saved: 1", status)
            self.assertEqual([event.status for event in progress], [
                "extracting", "saved", "extracting", "failed"
            ])

    def test_cancel_from_progress_keeps_completed_snapshot(self):
        driver = _FakeDriver()
        service = OrbeaDescriptionService(lambda *_: driver)
        urls = (
            "https://cms.orbea.com/en-au/m/kemen-adv",
            "https://cms.orbea.com/en-au/m/rise-lt",
        )

        def on_progress(event) -> None:
            if event.status == "saved":
                service.cancel()

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "tools.orbea_automation.descriptions.extract_description",
            return_value=_document(urls[0], "Kemen Adv"),
        ) as extractor:
            result = service.run(
                DescriptionRunConfig(urls=urls, output_dir=Path(temp_dir)),
                progress=on_progress,
            )

            self.assertTrue(result.cancelled)
            self.assertEqual(result.succeeded, 1)
            self.assertEqual(extractor.call_count, 1)
            self.assertEqual(driver.quit_calls, 1)
            content = (Path(temp_dir) / "kemen-adv.txt").read_text(
                encoding="utf-8-sig"
            )
            self.assertIn("Description for Kemen Adv.", content)
            status = (Path(temp_dir) / "description_run_status.txt").read_text(
                encoding="utf-8-sig"
            )
            self.assertIn("Status: Cancelled", status)

    def test_pre_cancelled_external_token_does_not_create_browser(self):
        token = CancellationToken()
        token.cancel()
        factory_calls = []
        with tempfile.TemporaryDirectory() as temp_dir:
            result = OrbeaDescriptionService(
                lambda *_: factory_calls.append(True)
            ).run(
                DescriptionRunConfig(
                    urls=("https://cms.orbea.com/en-au/m/kemen-adv",),
                    output_dir=Path(temp_dir),
                ),
                cancellation=token,
            )
            self.assertTrue(result.cancelled)
            self.assertEqual(result.succeeded, 0)
            self.assertFalse(factory_calls)
            self.assertEqual(
                {path.name for path in result.files},
                {"description_run_status.txt"},
            )

    def test_successful_run_removes_stale_error_report(self):
        driver = _FakeDriver()
        url = "https://cms.orbea.com/en-au/m/kemen-adv"
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "tools.orbea_automation.descriptions.extract_description",
            return_value=_document(url, "Kemen Adv"),
        ):
            stale = Path(temp_dir) / "description_errors.txt"
            stale.write_text("old failure", encoding="utf-8")
            result = OrbeaDescriptionService(lambda *_: driver).run(
                DescriptionRunConfig(urls=(url,), output_dir=Path(temp_dir))
            )

            self.assertEqual(result.succeeded, 1)
            self.assertFalse(result.failures)
            self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()

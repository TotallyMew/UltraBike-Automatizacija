from __future__ import annotations

import importlib.util
import io
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if (PROJECT_ROOT / "tools" / "orbea_table_image_downloader.py").is_file():
    sys.path.insert(0, str(PROJECT_ROOT))
    from tools import orbea_table_image_downloader as downloader
else:
    module_path = PROJECT_ROOT / "orbea_table_image_downloader.py"
    spec = importlib.util.spec_from_file_location(
        "orbea_table_image_downloader", module_path
    )
    assert spec and spec.loader
    downloader = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = downloader
    spec.loader.exec_module(downloader)


class FakeDriver:
    def __init__(self, navigation_error: Exception | None = None):
        self.navigation_error = navigation_error
        self.page_load_timeout = None
        self.urls: list[str] = []

    def set_page_load_timeout(self, timeout: float) -> None:
        self.page_load_timeout = timeout

    def get(self, url: str) -> None:
        self.urls.append(url)
        if self.navigation_error:
            raise self.navigation_error


def write_probe_png(path: Path, width: int = 300, height: int = 200) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
    path.write_bytes(header + struct.pack(">II", width, height) + b"x" * 1_100)


class CaptureAvailabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.geometry = self.root / "geometry.png"
        self.size = self.root / "size.png"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def capture(self, driver: FakeDriver, **kwargs):
        return downloader.capture_orbea_tables(
            driver,
            "https://cms.orbea.com/en-be/example",
            self.geometry,
            self.size,
            timeouts=downloader.CaptureTimeouts(),
            **kwargs,
        )

    def test_missing_controls_are_terminal_not_available(self) -> None:
        driver = FakeDriver()
        with patch.object(
            downloader,
            "discover_table_controls",
            return_value={"geometry": None, "size_guide": None},
        ), patch.object(downloader, "capture_geometry") as geometry_capture, patch.object(
            downloader, "capture_size_guide"
        ) as size_capture:
            result = self.capture(driver)

        self.assertEqual(result["geometry_status"], "not_available")
        self.assertEqual(result["size_guide_status"], "not_available")
        self.assertFalse(result["retryable"])
        geometry_capture.assert_not_called()
        size_capture.assert_not_called()
        self.assertEqual(driver.page_load_timeout, 25.0)

    def test_one_table_downloads_while_other_is_not_available(self) -> None:
        driver = FakeDriver()
        geometry_control = object()
        with patch.object(
            downloader,
            "discover_table_controls",
            return_value={"geometry": geometry_control, "size_guide": None},
        ), patch.object(
            downloader,
            "capture_geometry",
            return_value=(
                (640, 480),
                "Low",
                True,
                [
                    {
                        "size": "XS",
                        "wheel_size": '27.5"',
                        "filename": "geometry-xs.png",
                        "status": "downloaded",
                        "dimensions": [640, 480],
                        "position": "Low",
                        "error": "",
                    },
                    {
                        "size": "M",
                        "wheel_size": '29"',
                        "filename": "geometry-m.png",
                        "status": "downloaded",
                        "dimensions": [640, 480],
                        "position": "Low",
                        "error": "",
                    },
                ],
            ),
        ) as geometry_capture:
            result = self.capture(driver)

        self.assertEqual(result["geometry_status"], "downloaded")
        self.assertEqual(result["size_guide_status"], "not_available")
        self.assertFalse(result["retryable"])
        self.assertEqual(result["geometry_position"], "Low")
        self.assertTrue(result["geometry_size_selector_supported"])
        self.assertEqual(
            [variant["size"] for variant in result["geometry_variants"]],
            ["XS", "M"],
        )
        self.assertEqual(geometry_capture.call_args.kwargs["selector_timeout"], 5.0)
        self.assertEqual(geometry_capture.call_args.args[2], 8.0)

    def test_one_failed_geometry_size_keeps_the_page_retryable(self) -> None:
        driver = FakeDriver()
        with patch.object(
            downloader,
            "discover_table_controls",
            return_value={"geometry": object(), "size_guide": None},
        ), patch.object(
            downloader,
            "capture_geometry",
            return_value=(
                (640, 480),
                "",
                False,
                [
                    {
                        "size": "XS",
                        "filename": "geometry-xs.png",
                        "status": "downloaded",
                        "error": "",
                    },
                    {
                        "size": "M",
                        "filename": "geometry-m.png",
                        "status": "transient_error",
                        "error": "table did not update",
                    },
                ],
            ),
        ):
            result = self.capture(driver)

        self.assertEqual(result["geometry_status"], "transient_error")
        self.assertFalse(result["geometry_ok"])
        self.assertTrue(result["retryable"])
        self.assertIn("geometry M", result["geometry_error"])

    def test_geometry_variant_filename_is_marked_with_the_size(self) -> None:
        path = downloader.geometry_variant_path(
            self.root / "geometry.png", "S / M"
        )

        self.assertEqual(path.name, "geometry-s-m.png")

    def test_navigation_failure_is_retryable_for_both_tables(self) -> None:
        driver = FakeDriver(RuntimeError("network down"))
        result = self.capture(driver)

        self.assertEqual(result["geometry_status"], "transient_error")
        self.assertEqual(result["size_guide_status"], "transient_error")
        self.assertTrue(result["retryable"])
        self.assertIn("network down", " ".join(result["errors"]))

    def test_visible_control_render_failure_is_retryable_only_for_that_table(self) -> None:
        driver = FakeDriver()
        with patch.object(
            downloader,
            "discover_table_controls",
            return_value={"geometry": object(), "size_guide": None},
        ), patch.object(
            downloader, "capture_geometry", side_effect=RuntimeError("table stalled")
        ):
            result = self.capture(driver)

        self.assertEqual(result["geometry_status"], "transient_error")
        self.assertEqual(result["size_guide_status"], "not_available")
        self.assertTrue(result["retryable"])

    def test_existing_images_are_reported_downloaded_without_recapture(self) -> None:
        write_probe_png(self.geometry)
        write_probe_png(self.size)
        driver = FakeDriver()
        with patch.object(
            downloader, "discover_table_controls", return_value={"geometry": None, "size_guide": None}
        ) as discover:
            result = self.capture(
                driver, need_geometry=False, need_size_guide=False
            )

        self.assertEqual(result["geometry_status"], "downloaded")
        self.assertEqual(result["size_guide_status"], "downloaded")
        discover.assert_called_once_with(
            driver,
            need_geometry=False,
            need_size_guide=False,
            timeout=3.0,
        )


class CheckpointStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.record = {
            "geometry_image": "images/model/geometry.png",
            "size_guide_cm_image": "images/model/size-guide-cm.png",
            "geometry_capture_version": downloader.GEOMETRY_CAPTURE_VERSION,
            "geometry_position_requested": "low",
            "geometry_status": "not_available",
            "size_guide_status": "not_available",
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_current_not_available_checkpoint_does_not_retry(self) -> None:
        self.record["availability_probe_version"] = (
            downloader.AVAILABILITY_PROBE_VERSION
        )
        downloader.refresh_record_from_files(self.record, self.root, "low")

        self.assertEqual(self.record["status"], "complete")
        self.assertFalse(downloader.record_needs_processing(self.record))

    def test_old_not_available_checkpoint_is_probed_once_again(self) -> None:
        self.record["availability_probe_version"] = (
            downloader.AVAILABILITY_PROBE_VERSION - 1
        )
        downloader.refresh_record_from_files(self.record, self.root, "low")

        self.assertEqual(self.record["geometry_status"], "pending")
        self.assertEqual(self.record["size_guide_status"], "pending")
        self.assertTrue(downloader.record_needs_processing(self.record))

        downloader.apply_capture_result(
            self.record,
            {
                "availability_probe_version": downloader.AVAILABILITY_PROBE_VERSION,
                "geometry_status": "not_available",
                "size_guide_status": "not_available",
                "errors": [],
            },
            "low",
        )
        self.assertFalse(downloader.record_needs_processing(self.record))

    def test_valid_existing_files_are_preserved_as_complete(self) -> None:
        geometry = self.root / self.record["geometry_image"]
        size = self.root / self.record["size_guide_cm_image"]
        write_probe_png(geometry)
        write_probe_png(size)
        self.record["availability_probe_version"] = 0

        downloader.refresh_record_from_files(self.record, self.root, "low")

        self.assertEqual(self.record["geometry_status"], "downloaded")
        self.assertEqual(self.record["size_guide_status"], "downloaded")
        self.assertEqual(self.record["status"], "complete")
        self.assertFalse(downloader.record_needs_processing(self.record))
        self.assertTrue(geometry.exists())
        self.assertTrue(size.exists())

    def test_previous_single_geometry_capture_is_scheduled_for_upgrade(self) -> None:
        self.record["availability_probe_version"] = (
            downloader.AVAILABILITY_PROBE_VERSION
        )
        self.record["geometry_capture_version"] = (
            downloader.GEOMETRY_CAPTURE_VERSION - 1
        )
        self.record["geometry_status"] = "downloaded"

        self.assertTrue(downloader.record_needs_processing(self.record))

    def test_cli_allows_only_one_retry(self) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            downloader.parse_args(["--attempts", "3"])
        args = downloader.parse_args(["--attempts", "2"])
        self.assertEqual(args.attempts, 2)


if __name__ == "__main__":
    unittest.main()

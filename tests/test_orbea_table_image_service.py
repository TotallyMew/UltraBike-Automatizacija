from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from GUI_Qt.screens.OrbeaScreen import OrbeaScreen
from tools.orbea_automation import (
    OrbeaTableBatchResult,
    OrbeaTableImageService,
    OrbeaTableProductResult,
    OrbeaTableProgress,
    normalize_orbea_table_url,
)


PRODUCT_URL = "https://www.orbea.com/en-be/onna-20"


class _Driver:
    def __init__(self):
        self.quit_calls = 0
        self.page_source = "<html>current Orbea product</html>"

    def quit(self):
        self.quit_calls += 1


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


class _TableService:
    last_options = None

    def cancel(self):
        pass

    def run_many(
        self,
        urls,
        output_dir,
        *,
        progress,
        log,
        cancellation,
        download_geometry=True,
        download_size_guide=True,
        download_product_photos=False,
    ):
        type(self).last_options = (
            download_geometry,
            download_size_guide,
            download_product_photos,
        )
        output_dir = Path(output_dir)
        product_dir = output_dir / "onna-20"
        product_dir.mkdir(parents=True, exist_ok=True)
        names = []
        if download_geometry:
            names.extend(("geometry-xs.png", "geometry-m.png"))
        if download_size_guide:
            names.append("size-guide-cm.png")
        if download_product_photos:
            names.append("product-photos/J1_Red/J1_side.png")
        files = tuple(product_dir / name for name in names)
        for path in files:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"png")
        progress(
            OrbeaTableProgress(
                current=1,
                total=1,
                status="saved",
                message=f"{len(files)} images saved",
                succeeded=len(files),
            )
        )
        log(f"Saved {len(files)} images")
        photo_files = tuple(
            path for path in files if "product-photos" in path.parts
        )
        product = OrbeaTableProductResult(
            url=PRODUCT_URL,
            folder=product_dir,
            geometry_status="downloaded" if download_geometry else "not_selected",
            size_guide_status=(
                "downloaded" if download_size_guide else "not_selected"
            ),
            geometry_variants=(
                (
                    {"size": "XS", "filename": "geometry-xs.png"},
                    {"size": "M", "filename": "geometry-m.png"},
                )
                if download_geometry
                else ()
            ),
            files=files,
            errors=(),
            photo_files=photo_files,
            photo_variants=1 if photo_files else 0,
            photo_views=1 if photo_files else 0,
        )
        return OrbeaTableBatchResult(
            output_dir=output_dir,
            manifest_path=output_dir / "table_manifest.json",
            product_results=(product,),
            requested=len(tuple(urls)),
            products=1,
            duplicates=0,
            files=files,
            failures=(),
            unavailable=(),
            cancelled=False,
            photo_files=photo_files,
            photo_variants=1 if photo_files else 0,
            photo_views=1 if photo_files else 0,
        )


class OrbeaTableImageServiceTests(unittest.TestCase):
    def test_product_url_is_canonicalized_without_tracking_data(self):
        self.assertEqual(
            normalize_orbea_table_url(
                "www.orbea.com/en-be/onna-20/?colour=green#geometry"
            ),
            PRODUCT_URL,
        )
        with self.assertRaises(ValueError):
            normalize_orbea_table_url("https://example.com/en-be/onna-20")

    def test_only_supplied_pages_are_captured_and_duplicates_are_ignored(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "tables"
            driver = _Driver()
            captured_urls = []

            def capture(_driver, url, geometry_path, size_path, **_kwargs):
                captured_urls.append(url)
                geometry_path.parent.mkdir(parents=True, exist_ok=True)
                (geometry_path.parent / "geometry-xs.png").write_bytes(b"xs")
                (geometry_path.parent / "geometry-m.png").write_bytes(b"m")
                size_path.write_bytes(b"size")
                return {
                    "geometry_status": "downloaded",
                    "size_guide_status": "downloaded",
                    "geometry_variants": [
                        {
                            "size": "XS",
                            "wheel_size": '27.5"',
                            "filename": "geometry-xs.png",
                            "status": "downloaded",
                        },
                        {
                            "size": "M",
                            "wheel_size": '29"',
                            "filename": "geometry-m.png",
                            "status": "downloaded",
                        },
                    ],
                    "errors": [],
                }

            service = OrbeaTableImageService(lambda: driver)
            with patch(
                "tools.orbea_table_image_downloader.capture_orbea_tables",
                side_effect=capture,
            ):
                result = service.run_many(
                    [PRODUCT_URL, f"{PRODUCT_URL}/?tracking=1"], output
                )

            self.assertEqual(captured_urls, [PRODUCT_URL])
            self.assertEqual(driver.quit_calls, 1)
            self.assertEqual(result.products, 1)
            self.assertEqual(result.duplicates, 1)
            self.assertEqual(len(result.files), 3)
            self.assertEqual(result.manifest_path.name, "download_manifest.json")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["duplicates"], 1)
            self.assertEqual(
                [item["size"] for item in manifest["products"][0]["geometry_variants"]],
                ["XS", "M"],
            )

    def test_product_photos_can_be_downloaded_without_tables(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "images"
            driver = _Driver()
            capture_options = []
            photo_calls = []

            def capture(_driver, _url, _geometry_path, _size_path, **options):
                capture_options.append(options)
                return {
                    "geometry_status": "pending",
                    "size_guide_status": "pending",
                    "geometry_variants": [],
                    "errors": [],
                }

            class PhotoService:
                def run_from_html(
                    self, url, page_html, product_dir, *, product_folder, **_kwargs
                ):
                    photo_calls.append((url, page_html, product_folder))
                    photo = Path(product_dir) / product_folder / "J1_Red" / "J1_side.png"
                    photo.parent.mkdir(parents=True, exist_ok=True)
                    photo.write_bytes(b"photo")
                    return SimpleNamespace(
                        files=(photo,),
                        variants=1,
                        views=1,
                        failures=("J2 front failed",),
                        unavailable=("J3 back",),
                    )

            service = OrbeaTableImageService(
                lambda: driver,
                photo_service_factory=PhotoService,
            )
            with patch(
                "tools.orbea_table_image_downloader.capture_orbea_tables",
                side_effect=capture,
            ):
                result = service.run_many(
                    [PRODUCT_URL],
                    output,
                    download_geometry=False,
                    download_size_guide=False,
                    download_product_photos=True,
                )

            self.assertFalse(capture_options[0]["need_geometry"])
            self.assertFalse(capture_options[0]["need_size_guide"])
            self.assertEqual(
                photo_calls,
                [(PRODUCT_URL, driver.page_source, "product-photos")],
            )
            self.assertEqual(result.product_results[0].geometry_status, "not_selected")
            self.assertEqual(result.product_results[0].size_guide_status, "not_selected")
            self.assertEqual(result.photo_variants, 1)
            self.assertEqual(result.photo_views, 1)
            self.assertEqual(result.files, result.photo_files)
            self.assertEqual(len(result.failures), 1)
            self.assertEqual(len(result.unavailable), 1)


class OrbeaTableImageUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        _TableService.last_options = None
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.output = root / "tables"
        self.settings = _Settings(
            {
                "orbea_catalogue_path": str(root / "missing-catalogue.xlsx"),
                "orbea_table_output": str(self.output),
            }
        )
        self.main = _Main(self.settings)
        self.screen = OrbeaScreen(
            self.main,
            table_image_service_factory=_TableService,
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

    def test_table_download_does_not_require_pimbo_or_a_catalogue(self):
        self.assertIsNone(self.main.driver)
        self.assertFalse(Path(self.screen._catalogue_edit.text()).is_file())
        self.screen._table_image_url_edit.setPlainText(PRODUCT_URL)
        self.app.processEvents()

        self.assertTrue(self.screen._table_image_start_btn.isEnabled())
        self.screen._on_table_image_start_stop()
        self._wait_for_worker()

        product_dir = self.output / "onna-20"
        self.assertTrue((product_dir / "geometry-xs.png").is_file())
        self.assertTrue((product_dir / "geometry-m.png").is_file())
        self.assertTrue((product_dir / "size-guide-cm.png").is_file())
        self.assertEqual(_TableService.last_options, (True, True, False))
        self.assertEqual(self.screen._table_image_progress.value(), 100)
        self.assertIn("complete", self.screen._table_image_status_label.text().lower())
        self.assertTrue(self.screen._table_image_open_btn.isEnabled())
        self.assertEqual(self.settings.values["orbea_table_output"], str(self.output))

    def test_product_photos_can_be_selected_on_their_own(self):
        self.screen._table_image_url_edit.setPlainText(PRODUCT_URL)
        self.screen._table_geometry_check.setChecked(False)
        self.screen._table_size_guide_check.setChecked(False)
        self.screen._table_product_photos_check.setChecked(True)
        self.app.processEvents()

        self.assertTrue(self.screen._table_image_start_btn.isEnabled())
        self.screen._on_table_image_start_stop()
        self._wait_for_worker()

        photo = self.output / "onna-20" / "product-photos" / "J1_Red" / "J1_side.png"
        self.assertTrue(photo.is_file())
        self.assertEqual(_TableService.last_options, (False, False, True))
        self.assertFalse((self.output / "onna-20" / "geometry-xs.png").exists())


if __name__ == "__main__":
    unittest.main()

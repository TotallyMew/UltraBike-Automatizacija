from __future__ import annotations

import json
import shutil
from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest
from openpyxl import Workbook
from PySide6.QtWidgets import QApplication

from tests.test_orbea_collection import Website, Photos, URL, SKU, config, scan, service, tables
from tests.test_orbea_upload_ui import screen
from tools.orbea_automation.checkpoint import saved_run_config
from tools.orbea_automation.models import PimboFilterSpec
from tools.orbea_automation.service import OrbeaAutomationService
from tools.orbea_automation.saved_collection import open_saved_collection, collection_download_counts


def finished_collection(tmp_path):
    settings = config(tmp_path, download_product_photos=False)
    with patch("tools.orbea_automation.service.PimboBrowserClient.collect", scan), patch.object(OrbeaAutomationService, "_download_images", tables):
        result = service(Website(), Photos()).run(settings, resume=False)
    assert result.completed
    return result


def selected_photos(settings):
    return replace(settings, download_images=False, download_description=False,
                   download_specifications=False, download_product_photos=True)


def run_saved(website, photos, settings, **kwargs):
    worker = service(website, photos)
    worker.pimbo_driver = None
    with patch("tools.orbea_automation.service.PimboBrowserClient.collect", side_effect=AssertionError("must not rescan")), \
         patch.object(OrbeaAutomationService, "_lookup_products", side_effect=AssertionError("must use saved links")), \
         patch.object(OrbeaAutomationService, "_download_images", side_effect=AssertionError("tables already collected")):
        return worker.run(settings, resume=True, **kwargs)


@pytest.mark.parametrize("only_photos", [True, False])
def test_finished_excel_adds_photos_without_recollecting_or_losing_prior_data(tmp_path, only_photos):
    result = finished_collection(tmp_path)
    folder = result.run_dir / "products" / SKU
    files = [folder / "description.html", folder / "specifications.txt", *list((folder / "tables").iterdir())]
    original = {path: path.read_bytes() for path in files}
    ledger = folder / "orbea-upload-result.json"
    ledger.write_bytes(b'{"saved_upload_history":true}')
    settings, loaded = open_saved_collection(result.workbook_path, tmp_path / "unused-output")
    assert loaded.run_dir == result.run_dir and not (tmp_path / "unused-output").exists()
    assert collection_download_counts(result.run_dir) == {"total": 1, "photos": 0, "description": 1, "specifications": 1, "tables": 1}
    photos, website = Photos(), Website()
    def fetch(url):
        assert website.collect_description is False and website.collect_specifications is False
        website.fetches.append(url)
        return website.product
    website.fetch = fetch
    selected = selected_photos(settings) if only_photos else replace(settings, download_product_photos=True)
    added = run_saved(website, photos, selected, download_missing=True)
    assert added.completed and added.run_dir == result.run_dir and photos.calls == 1
    assert website.lookups == [] and set(website.fetches) == {URL}
    assert all(path.read_bytes() == content for path, content in original.items())
    assert ledger.read_bytes() == b'{"saved_upload_history":true}'
    metadata = json.loads((folder / "orbea-product.json").read_text())
    assert all(metadata["stages"][stage]["status"] == "downloaded" for stage in ("description", "specifications", "tables", "photos"))
    assert all(metadata["selected_stages"].values())
    assert collection_download_counts(result.run_dir)["photos"] == 1
    # An ordinary resume of the new choices must also skip all completed pages.
    website = Website()
    again = run_saved(website, photos, saved_run_config(result.run_dir))
    assert again.completed and website.fetches == [] and photos.calls == 1


def test_copied_excel_reconnects_to_the_original_collection(tmp_path):
    result = finished_collection(tmp_path)
    copied = tmp_path / "copied.xlsx"
    shutil.copyfile(result.workbook_path, copied)
    settings, loaded = open_saved_collection(copied, tmp_path / "elsewhere")
    assert loaded.run_dir == result.run_dir and settings.resume_run_dir == result.run_dir
    assert not (tmp_path / "elsewhere").exists()


def test_standalone_excel_imports_saved_links_without_changing_the_input(tmp_path):
    path = tmp_path / "finished.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.title = "Matches"
    sheet.append(["Variant SKU", "Pimbo Product", "Catalogue Code", "Year", "Orbea URL"])
    sheet.append([SKU, "Orbea ORCA M30i Black", "U107TTCC", 2027, URL])
    book.save(path)
    book.close()
    original = path.read_bytes()
    settings, loaded = open_saved_collection(path, tmp_path / "downloads")
    assert loaded.run_dir != path.parent and settings.downloads_only
    photos, website = Photos(), Website()
    result = run_saved(website, photos, selected_photos(settings), download_missing=True)
    assert result.completed and photos.calls == 1 and not website.lookups
    assert path.read_bytes() == original
    assert (result.run_dir / "products" / SKU / "photos" / "black-side.png").is_file()


def test_cancelled_added_photos_resume_with_new_choices_and_saved_sources(tmp_path):
    result = finished_collection(tmp_path)
    settings = selected_photos(saved_run_config(result.run_dir))
    photos = Photos()
    photos.cancel_run = True
    stopped = run_saved(Website(), photos, settings, download_missing=True)
    assert stopped.cancelled and not stopped.completed
    restored = saved_run_config(stopped.run_dir)
    assert restored.downloads_only and restored.download_product_photos
    assert not restored.download_specifications and not restored.download_images
    photos.cancel_run = False
    finished = run_saved(Website(), photos, restored)
    assert finished.completed and finished.run_dir == result.run_dir
    assert collection_download_counts(result.run_dir) == {"total": 1, "photos": 1, "description": 1, "specifications": 1, "tables": 1}


def test_missing_photo_file_is_downloaded_again_without_touching_sources(tmp_path):
    result = finished_collection(tmp_path)
    photos = Photos()
    settings = selected_photos(saved_run_config(result.run_dir))
    run_saved(Website(), photos, settings, download_missing=True)
    photo = result.run_dir / "products" / SKU / "photos" / "black-side.png"
    photo.unlink()
    assert collection_download_counts(result.run_dir)["photos"] == 0
    again = run_saved(Website(), photos, saved_run_config(result.run_dir))
    assert again.completed and photos.calls == 2 and photo.is_file()


def test_new_download_choices_do_not_allow_changing_the_saved_filter_set(tmp_path):
    result = finished_collection(tmp_path)
    settings = replace(selected_photos(saved_run_config(result.run_dir)), filters=PimboFilterSpec(statuses=("Published",)))
    with pytest.raises(ValueError, match="different catalogue or Pimbo filter"):
        run_saved(Website(), Photos(), settings, download_missing=True)


def test_invalid_report_link_does_not_create_a_collection(tmp_path):
    path = tmp_path / "bad.xlsx"
    book = Workbook()
    book.active.title = "Matches"
    book.active.append(["Variant SKU", "Orbea URL"])
    book.active.append([SKU, "https://example.com/unrelated-product"])
    book.save(path)
    book.close()
    with pytest.raises(ValueError, match="valid Orbea product URL"):
        open_saved_collection(path, tmp_path / "downloads")
    assert not (tmp_path / "downloads").exists()


def test_ui_opens_finished_excel_and_uses_current_choices_without_pimbo(screen, tmp_path):
    result = finished_collection(tmp_path)
    screen._load_saved_collection(result.workbook_path)
    assert screen._run_dir == result.run_dir
    assert screen._load_collection_btn.text() == "Open saved collection"
    assert "photos 0" in screen._saved_download_hint.text()
    assert "Pimbo login is not needed" in screen._resume_hint.text()
    for key, checkbox in screen._collection_checkboxes().items():
        checkbox.setChecked(key == "photos")
    website, photos = Website(), Photos()
    screen.workflow_controller.service_factory = lambda driver: OrbeaAutomationService(driver,
        website_client_factory=lambda *_: website, photo_service_factory=lambda: photos)
    screen.main.try_acquire_browser_lease = MagicMock(return_value=False)
    assert screen.main.driver is None and screen._download_missing_btn.isEnabled()
    with patch("tools.orbea_automation.service.PimboBrowserClient.collect", side_effect=AssertionError("must not rescan")), \
         patch.object(OrbeaAutomationService, "_lookup_products", side_effect=AssertionError("must use saved links")):
        screen._download_missing_btn.click()
        assert screen._worker.download_missing
        assert not screen._download_missing_btn.isEnabled() and not screen._load_collection_btn.isEnabled()
        assert screen._worker.wait(5000)
        QApplication.processEvents()
    assert photos.calls == 1 and screen._run_dir == result.run_dir
    assert screen._product_photos_check.isChecked() and not screen._specifications_check.isChecked()
    assert "photos 1" in screen._saved_download_hint.text()
    screen.main.try_acquire_browser_lease.assert_not_called()


def test_shared_model_cache_collects_sources_needed_by_a_later_product(tmp_path):
    from tests.test_orbea_collection import row
    def two_rows(client, catalogue, checkpoint, settings, **kwargs):
        checkpoint.upsert_result(row())
        checkpoint.upsert_result({**row(), "row_key": "p2", "product_id": "p2", "sku": "U10707SX"})
        checkpoint.data["scan_completed"] = True
        checkpoint.save()
    with patch("tools.orbea_automation.service.PimboBrowserClient.collect", two_rows), patch.object(OrbeaAutomationService, "_download_images", tables):
        result = service(Website(), Photos()).run(config(tmp_path, download_product_photos=False), resume=False)
    assert result.completed
    description = result.run_dir / "products" / "U107TTCC" / "U10707SX" / "description.html"
    description.unlink()
    class CachedWebsite(Website):
        cached = None
        def fetch(self, url):
            if self.cached is None:
                self.cached = replace(self.product, description_html=self.product.description_html if self.collect_description else "")
            return self.cached
    settings = replace(selected_photos(saved_run_config(result.run_dir)), download_description=True)
    photos = Photos()
    finished = run_saved(CachedWebsite(), photos, settings, download_missing=True)
    assert finished.completed and photos.calls == 1
    assert description.is_file() and "long days" in description.read_text()


def test_adding_photos_retains_an_unselected_specs_failure_for_later_retry(tmp_path):
    result = finished_collection(tmp_path)
    data = json.loads(result.checkpoint_path.read_text())
    data["results"][0]["collection_stages"]["specifications"].update(status="error", note="Temporary component error")
    result.checkpoint_path.write_text(json.dumps(data))
    finished = run_saved(Website(), Photos(), selected_photos(saved_run_config(result.run_dir)), download_missing=True)
    assert finished.completed  # The requested photos completed.
    metadata = json.loads((result.run_dir / "products" / SKU / "orbea-product.json").read_text())
    assert metadata["stages"]["photos"]["status"] == "downloaded"
    assert metadata["stages"]["specifications"]["status"] == "error" and metadata["status"] == "partial"
    assert "Temporary component error" in " | ".join(metadata["errors"])


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows checkpoint locking")
def test_checkpoint_save_retries_a_temporary_windows_reader_lock(tmp_path):
    from tools.orbea_automation.checkpoint import atomic_write_json
    path = tmp_path / "checkpoint.json"
    path.write_text('{"old":true}')
    import os
    actual_replace = os.replace
    attempts = []
    def locked_replace(source, destination):
        attempts.append(destination)
        if len(attempts) < 3:
            raise PermissionError("Checkpoint is temporarily held by a reader")
        actual_replace(source, destination)
    with patch("tools.orbea_automation.checkpoint.os.replace", side_effect=locked_replace), \
         patch("tools.orbea_automation.checkpoint.time.sleep"):
        atomic_write_json(path, {"new": True})
    assert json.loads(path.read_text()) == {"new": True} and len(attempts) == 3


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows checkpoint locking")
def test_checkpoint_save_still_reports_a_persistent_windows_write_failure(tmp_path):
    from tools.orbea_automation.checkpoint import atomic_write_json
    path = tmp_path / "checkpoint.json"
    with patch("tools.orbea_automation.checkpoint.os.replace", side_effect=PermissionError("Access denied")), \
         patch("tools.orbea_automation.checkpoint.time.sleep"):
        with pytest.raises(PermissionError, match="Access denied"):
            atomic_write_json(path, {"new": True})

from __future__ import annotations

import importlib
import inspect
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from PIL import Image

from Database.DatabaseManager import DatabaseManager
from Managers.PimboProductEditor import (
    PimAiStepResult, PimAutomationError, PimPreparationResult,
    PimPreparationStatus, PimboProductEditor,
)
from Managers.TranslationManager import TranslationManager
from Uploaders.BaseUploader import ProductUploader
from Utilities.BatchProcessor import BatchProcessor
from Utilities.FileHandler import FileHandler
from Utilities.ImageHandler import ImageHandler
from Utilities.ProductDataSafety import normalize_brand_options, validate_unique_products
from Utilities.ProductHistory import record_review_status
from Utilities.TranslationHandler import TranslationHandler


@pytest.fixture
def db(tmp_path):
    database = DatabaseManager(tmp_path / "safety.sqlite")
    database.conn.execute("DELETE FROM translations")
    database.conn.commit()
    yield database
    database.close()


@pytest.fixture(autouse=True)
def isolated_outputs(monkeypatch, tmp_path):
    monkeypatch.setattr("Managers.TranslationManager.get_data_dir", lambda: tmp_path)
    for name in ("show_error", "show_warning", "show_success"):
        monkeypatch.setattr(f"Utilities.ErrorManager.ErrorManager.{name}", Mock())


SCRAPERS = [
    ("KROSS", "KROSS", "scrapeAndTranslateToFileKROSS", {}),
    ("Pinarello", "Pinarello", "scrapeAndTranslateToFilePinarello", {"frameset_only": False}),
    ("Factor", "Factor", "scrapeAndTranslateToFileFactor", {}),
    ("Rondo", "Rondo", "scrapeAndTranslateToFileRondo", {}),
    ("Rascal", "Rascal", "scrapeAndTranslateToFileRascal", {"variant_index": 1}),
    ("Octane", "Octane", "scrapeAndTranslateToFileOctaneOne", {}),
    ("TREK", "TREK", "scrapeAndTranslateToFileTREK", {"preferred_size": "M"}),
    ("Basso", "Basso", "scrapeAndTranslateToFileBasso", {}),
    ("LeeCougan", "LeeCougan", "scrapeAndTranslateToFileLeeCougan", {}),
]


@pytest.mark.parametrize("uploader_name,scraper_name,function_name,options", SCRAPERS)
def test_every_uploader_calls_its_scraper_with_a_valid_contract(
    db, monkeypatch, uploader_name, scraper_name, function_name, options,
):
    module = importlib.import_module(f"Uploaders.{uploader_name}")
    scraper = getattr(importlib.import_module(f"Scrapers.{scraper_name}Scraper"), function_name)
    signature = inspect.signature(scraper)
    calls = []

    def scrape(**kwargs):
        signature.bind(**kwargs)
        calls.append(kwargs)
        Path(kwargs["outputFile"]).write_text("Rėmas: Carbon M\n", encoding="utf-8")

    scrape.__signature__ = signature
    monkeypatch.setattr(module, function_name, scrape)
    uploader = getattr(module, uploader_name)(
        driver=Mock(), brand_name=uploader_name, product_code="SKU-M",
        url_or_code="supplier-M", db_manager=db, brand_options=options,
        master_password="test-password",
    )
    uploader.session_manager = SimpleNamespace(get_external_credentials=lambda *args: ("test", "test"))
    uploader.scrape()
    assert uploader.translationManager.loadLT() == [{"Rėmas": "Carbon M"}]
    assert len(calls) == 1
    for key, value in options.items():
        assert calls[0][key] == value


def test_failed_scrape_cannot_reuse_previous_output(db):
    manager = TranslationManager("KROSS", db)
    for name in (manager.ltPath, manager.enPath):
        Path(name).write_text("Rėmas: Old bike\n", encoding="utf-8")

    def failed(url, outputFile, db_manager=None):
        return "Error: supplier is unavailable"

    with pytest.raises(FileNotFoundError):
        manager.prepareTranslationFiles(failed, "new-bike")
    assert manager.raw_source_text == ""
    assert not Path(manager.ltPath).exists()
    assert not Path(manager.enPath).exists()


def test_same_brand_jobs_keep_their_own_specifications(db):
    first, second = TranslationManager("KROSS", db), TranslationManager("KROSS", db)
    barrier = Barrier(2)

    def scrape(url, outputFile, db_manager=None):
        Path(outputFile).write_text(f"Rėmas: {url}\n", encoding="utf-8")
        barrier.wait(timeout=5)

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(manager.prepareTranslationFiles, scrape, code)
                for manager, code in ((first, "Bike A"), (second, "Bike B"))]
        for job in jobs:
            job.result(timeout=10)
    assert first.loadLT() == [{"Rėmas": "Bike A"}]
    assert second.loadLT() == [{"Rėmas": "Bike B"}]
    second.cleanup_generated_files()
    assert first.loadLT() == [{"Rėmas": "Bike A"}]


@pytest.mark.parametrize("content", ["", "\n", "Frame carbon\n", ": Carbon\n", "Frame: \n", "Frame: A\n\nFRAME: B\n"])
def test_incomplete_or_conflicting_specs_are_rejected(tmp_path, content):
    path = tmp_path / "specs.txt"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        FileHandler.read_translated_file(path)


@pytest.mark.parametrize("uploader,scraper,function,options", SCRAPERS[:7])
def test_http_failure_propagates(db, monkeypatch, tmp_path, uploader, scraper, function, options):
    module = importlib.import_module(f"Scrapers.{scraper}Scraper")
    monkeypatch.setattr(module.requests, "get", Mock(side_effect=requests.ConnectionError("offline")))
    with pytest.raises(RuntimeError, match="offline"):
        getattr(module, function)("https://supplier/bike", str(tmp_path / "specs.txt"), db_manager=db, **options)


def response(html):
    return SimpleNamespace(text=html, content=html.encode(), raise_for_status=lambda: None)


def test_rascal_requires_explicit_variant_and_preserves_selection(db, monkeypatch, tmp_path):
    from Scrapers.RascalScraper import scrapeAndTranslateToFileRascal
    html = '<ul class="list-unstyled product-params"><li><span>Frame</span><span>Small</span><span>Large</span></li></ul>'
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: response(html))
    path = str(tmp_path / "rascal.txt")
    with pytest.raises(RuntimeError, match="Multiple variants"):
        scrapeAndTranslateToFileRascal("url", path, db_manager=db)
    with pytest.raises(RuntimeError, match="does not exist"):
        scrapeAndTranslateToFileRascal("url", path, variant_index=2, db_manager=db)
    scrapeAndTranslateToFileRascal("url", path, variant_index=1, db_manager=db)
    assert FileHandler.read_translated_file(path) == [{"FRAME": "Large"}]


def test_pinarello_frameset_does_not_receive_complete_bike_parts(db, monkeypatch, tmp_path):
    from Scrapers.PinarelloScraper import scrapeAndTranslateToFilePinarello
    html = "".join(f'<div class="col-lg-4 p-3"><div class="text--small color--mid-dark-gray mb-2">{key}</div><div class="color--dark-gray">{value}</div></div>'
                   for key, value in [("Frame", "Carbon"), ("Tyres Disc", "Maxxis"), ("Axles Disc", "12mm")])
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: response(html))
    path = str(tmp_path / "pinarello.txt")
    scrapeAndTranslateToFilePinarello("url", path, frameset_only=True, db_manager=db)
    assert FileHandler.read_translated_file(path) == [{"FRAME": "Carbon"}]


def test_conflicting_rows_cannot_silently_overwrite_a_component(db, monkeypatch, tmp_path):
    from Scrapers.KROSSScraper import scrapeAndTranslateToFileKROSS
    html = '<div id="additional"><table class="additional-attributes-table"><tr><td>RAMA</td><td>Small</td></tr><tr><td>RAMA</td><td>Large</td></tr></table></div>'
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: response(html))
    with pytest.raises(RuntimeError, match="Conflicting supplier"):
        scrapeAndTranslateToFileKROSS("url", str(tmp_path / "kross.txt"), db_manager=db)


def test_kross_keeps_battery_and_motor_data(db, monkeypatch, tmp_path):
    from Scrapers.KROSSScraper import scrapeAndTranslateToFileKROSS
    html = '<div id="additional"><table class="additional-attributes-table"><tr><td>POJEMNOŚĆ BATERII</td><td>625 Wh</td></tr><tr><td>MOC SILNIKA</td><td>250 W</td></tr></table></div>'
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: response(html))
    path = str(tmp_path / "kross.txt")
    scrapeAndTranslateToFileKROSS("url", path, db_manager=db)
    assert FileHandler.read_translated_file(path) == [{"POJEMNOŚĆ BATERII": "625 Wh", "MOC SILNIKA": "250 W"}]


def test_trek_keeps_shared_specs_and_rejects_conflicting_size_data():
    from Scrapers.TREKScraper import extract_size_specific_data
    assert extract_size_specific_data({"Frame": [("", "Carbon")]}) == {"": {"Frame": "Carbon"}}
    assert extract_size_specific_data({"Crank": [("", "170"), ("M", "175")], "Frame": [("S", "Small")]}) == {
        "S": {"Crank": "170", "Frame": "Small"}, "M": {"Crank": "175"},
    }
    with pytest.raises(ValueError, match="Conflicting"):
        extract_size_specific_data({"Crank": [("M", "170"), ("M", "175")]})


def test_trek_does_not_choose_an_arbitrary_size(db, monkeypatch, tmp_path):
    from Scrapers.TREKScraper import scrapeAndTranslateToFileTREK
    html = '<div class="pdl-collapse-item is-active"><div class="flex items-center grow">Frameset</div><table class="sprocket__table spec"><tr><th>Frame</th><td><span>Size: S</span>Small</td></tr><tr><th>Frame</th><td><span>Size: M</span>Medium</td></tr></table></div>'
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: response(html))
    path = str(tmp_path / "trek.txt")
    with pytest.raises(RuntimeError, match="select preferred_size"):
        scrapeAndTranslateToFileTREK("url", path, db_manager=db)
    scrapeAndTranslateToFileTREK("url", path, preferred_size="M", db_manager=db)
    assert FileHandler.read_translated_file(path) == [{"Dydis": "M"}, {"Frame": "Medium"}]


def test_english_translation_does_not_translate_values_back_to_lithuanian(db, tmp_path):
    db.conn.executemany("INSERT INTO translations (source_term,target_term,source_lang,target_lang,category) VALUES (?,?,?,?,?)", [
        ("ANGLIES", "Carbon", "LT", "EN", "material"), ("CARBON", "Anglies", "EN", "LT", "material"),
    ])
    db.conn.commit()
    source, output = tmp_path / "lt.txt", tmp_path / "en.txt"
    source.write_text("Rėmas: Anglies frame\n", encoding="utf-8")
    TranslationHandler(db).translate_to_english(str(source), str(output))
    assert output.read_text(encoding="utf-8") == "Rėmas: Carbon frame\n"


@pytest.mark.parametrize("value", ["false", "FALSE", "no", "0", False, 0])
def test_false_batch_options_stay_false(value):
    assert normalize_brand_options({"frameset_only": value, "append_disclaimer": value})["frameset_only"] is False


def test_invalid_options_and_duplicate_products_stop_before_processing():
    with pytest.raises(ValueError):
        normalize_brand_options({"frameset_only": "maybe"})
    with pytest.raises(ValueError, match="not supported"):
        normalize_brand_options({"append_order_note": True})
    with pytest.raises(ValueError, match="more than once"):
        validate_unique_products([{"code": "SKU"}, {"code": " sku "}])


def test_images_are_current_validated_and_isolated(monkeypatch, tmp_path):
    buffer = BytesIO()
    Image.new("RGB", (2, 2)).save(buffer, format="PNG")
    png = buffer.getvalue()
    (tmp_path / "SKU").mkdir()
    (tmp_path / "SKU" / "old.jpg").write_bytes(b"old bike")
    page = response('<a class="orbitvu-gallery-item-link" data-big_src="/bike.png"></a>')
    monkeypatch.setattr(requests, "get", lambda url, **kwargs: page if url.endswith("product") else SimpleNamespace(content=png, raise_for_status=lambda: None))
    handler = ImageHandler(SimpleNamespace(get_kross_path=lambda: str(tmp_path)))
    first = handler.download_kross_images("https://supplier/product", "SKU")
    second = handler.download_kross_images("https://supplier/product", "SKU")
    assert first != second
    assert len(first) == len(second) == 1
    assert all(Path(path).read_bytes() == png for path in first + second)
    monkeypatch.setattr(requests, "get", lambda url, **kwargs: page if url.endswith("product") else SimpleNamespace(content=b"HTML login page", raise_for_status=lambda: None))
    with pytest.raises(RuntimeError, match="incomplete"):
        handler.download_kross_images("https://supplier/product", "SKU")


class Uploader(ProductUploader):
    def scrape(self):
        pass


@pytest.fixture
def uploader(db):
    instance = Uploader(driver=SimpleNamespace(current_url="https://pim.bo.ultrabike.lt/dashboard/products/p-1"),
        brand_name="KROSS", product_code="SKU", url_or_code="supplier", db_manager=db)
    instance.pim_editor = Mock()
    instance.pim_editor.product_id = "p-1"
    instance.pim_editor.photo_upload = {}
    return instance


def test_missing_selected_description_stops_before_browser_changes(uploader):
    uploader.description_name = "Deleted template"
    uploader.description_manager.prepare_description = Mock(return_value=None)
    uploader.openProduct = Mock()
    uploader.translate = Mock()
    result = uploader.run()
    assert result.status == PimPreparationStatus.FAILED
    assert result.failed_stage == "description_source"
    uploader.openProduct.assert_not_called()


def test_unmatched_specs_are_failed_not_reported_as_uploaded(uploader):
    uploader.translationManager.loadLT = Mock(return_value=[{"Rėmas": "Carbon", "Fork": "RockShox"}])
    uploader.pim_editor.set_specification.side_effect = [True, None]
    with pytest.raises(PimAutomationError, match="Fork"):
        uploader.uploadFeatures()
    assert uploader.features_uploaded == 1
    assert "specifications" in uploader._changed_fields


def test_failed_attribute_and_description_writes_are_not_swallowed(uploader):
    uploader.brand_options["attribute_values"] = [{"name": "Wheel size", "value": "29"}]
    uploader.pim_editor.set_attribute.return_value = None
    with pytest.raises(PimAutomationError, match="Wheel size"):
        uploader.uploadAttributes()
    uploader.description_name = "Template"
    uploader._prepared_descriptions = {"lt": "Text"}
    uploader.pim_editor.set_localized_descriptions.side_effect = RuntimeError("write failed")
    with pytest.raises(RuntimeError, match="write failed"):
        uploader.uploadDescription()


def test_failed_ai_result_stops_later_ai_actions(uploader):
    uploader._magicai_source_text = "Rėmas: Carbon"
    uploader.pim_editor.generate_product_name.return_value = PimAiStepResult("name", False, detail="wrong template")
    with pytest.raises(PimAutomationError, match="wrong template"):
        uploader.runMagicAi()
    uploader.pim_editor.generate_description.assert_not_called()


def test_stop_before_run_makes_no_product_changes(uploader):
    uploader.openProduct = Mock()
    uploader.request_stop()
    result = uploader.run()
    assert result.status == PimPreparationStatus.FAILED
    assert "stopped" in result.error
    assert result.product_id == ""
    uploader.openProduct.assert_not_called()


def test_changed_product_blocks_edits_and_finish():
    driver = SimpleNamespace(current_url="https://pim.bo.ultrabike.lt/dashboard/products/p-2", execute_script=Mock())
    editor = PimboProductEditor(driver)
    editor._bound_product_id = "p-1"
    element = Mock()
    with pytest.raises(PimAutomationError, match="different"):
        editor._set_input_value(element, "wrong bike")
    driver.execute_script.assert_not_called()
    result = editor.finish(PimPreparationResult(product_code="SKU", product_id="p-1"))
    assert result.status == PimPreparationStatus.FAILED


def test_failed_ai_step_cannot_be_finished_as_ready():
    editor = PimboProductEditor(SimpleNamespace(current_url="https://pim.bo.ultrabike.lt/dashboard/products/p-1"))
    result = editor.finish(PimPreparationResult(product_code="SKU", product_id="p-1"),
                           ai_steps=[PimAiStepResult("description", False, detail="failed")])
    assert result.status == PimPreparationStatus.FAILED


def test_review_updates_the_operation_not_the_latest_same_sku(uploader, db):
    uploader.preparation_result = PimPreparationResult(product_code="SKU", product_id="p-1", status=PimPreparationStatus.READY_FOR_REVIEW)
    uploader._record_success(1)
    first = uploader.preparation_result
    uploader.preparation_result = replace(first, product_id="p-2", history_id=None)
    uploader._record_success(1)
    second = uploader.preparation_result
    record_review_status(db, first.with_status(PimPreparationStatus.SAVED_MANUALLY))
    rows = db.conn.execute("SELECT id,status FROM processing_history ORDER BY id").fetchall()
    assert [(row["id"], row["status"]) for row in rows] == [
        (first.history_id, "saved_manually"), (second.history_id, "ready_for_review"),
    ]
    with pytest.raises(ValueError, match="another"):
        record_review_status(db, replace(first, product_id="wrong"))


def test_cancelled_batch_keeps_remaining_items_unprocessed(db):
    processor = BatchProcessor(driver=Mock(), db_manager=db)
    for code in ("A", "B", "C"):
        processor.add_to_queue("KROSS", code, "url")

    def run():
        processor.stop_batch()
        return PimPreparationResult(product_code="A", status=PimPreparationStatus.FAILED)

    result = processor.start_batch(lambda *args: SimpleNamespace(run=run))
    assert result["processed"] == 1
    assert result["remaining"] == 2
    assert result["cancelled"] is True
    current, total, percent = processor.get_progress()
    assert (current, total) == (1, 3)
    assert percent == pytest.approx(100 / 3)


def test_pool_does_not_close_dirty_product_or_double_release(monkeypatch):
    from Managers.BrowserSessionManager import BrowserSession, BrowserSessionManager
    manager = BrowserSessionManager(pool_size=1)
    driver = SimpleNamespace(current_url="https://pim.bo.ultrabike.lt/dashboard/products/p-1", quit=Mock())
    session = BrowserSession(0, driver, "Chrome")
    manager.sessions = [session]
    manager._initialized = True
    assert manager.acquire_session(timeout=0) is session
    manager.release_session(session)
    manager.release_session(session)
    assert manager.acquire_session(timeout=0) is session
    assert manager.acquire_session(timeout=0) is None
    monkeypatch.setattr(PimboProductEditor, "is_dirty", lambda self: True)
    assert manager.reset_session(session) is False
    driver.quit.assert_not_called()


def test_browser_lease_is_kept_for_running_or_dirty_work(monkeypatch):
    from GUI_Qt.services.product_work import acquire_product_browser, release_product_browser
    main = SimpleNamespace(driver=SimpleNamespace(current_url="https://pim.bo.ultrabike.lt/dashboard/products/p-1"),
        try_acquire_browser_lease=Mock(return_value=True), release_browser_lease=Mock())
    monkeypatch.setattr(PimboProductEditor, "is_dirty", lambda self: True)
    assert acquire_product_browser(main, "upload") is False
    assert release_product_browser(main, "upload") is False
    main.release_browser_lease.assert_not_called()
    monkeypatch.setattr(PimboProductEditor, "is_dirty", lambda self: False)
    assert release_product_browser(main, "upload", SimpleNamespace(isRunning=lambda: True)) is False
    assert release_product_browser(main, "upload", SimpleNamespace(isRunning=lambda: False)) is True


def prepare_mock_workflow(uploader):
    uploader.translationManager.raw_source_text = "Rėmas: Carbon"
    uploader.translationManager.loadLT = Mock(return_value=[{"Rėmas": "Carbon"}])
    uploader.translate = Mock()
    uploader.openProduct = Mock()
    uploader.settings_manager = SimpleNamespace(download_pictures_and_upload=lambda: False)
    uploader.pim_editor.begin.return_value = PimPreparationResult(
        "SKU", "p-1", initial_version=3, initial_fields={"product_name_lt": "Bike"},
    )
    uploader.pim_editor.collect_variant_sizes.return_value = []
    uploader.pim_editor.set_specification.return_value = True
    for name in ("generate_product_name", "generate_description", "suggest_category",
                 "fill_empty_specifications_with_ai", "translate_lt_to_all"):
        getattr(uploader.pim_editor, name).return_value = PimAiStepResult(name, True, True)
    uploader.pim_editor.finish.side_effect = lambda base, **kwargs: replace(
        base, status=PimPreparationStatus.READY_FOR_REVIEW,
        **{key: tuple(value) for key, value in kwargs.items()},
    )


def test_complete_valid_job_is_reviewable_and_tied_to_its_history(uploader, db):
    prepare_mock_workflow(uploader)
    result = uploader.run()
    assert result.status == PimPreparationStatus.READY_FOR_REVIEW
    assert result.product_id == "p-1" and result.initial_version == 3
    assert len(result.ai_steps) == 5
    assert uploader.features_uploaded == 1
    assert uploader.failed_stage == ""
    assert db.conn.execute("SELECT status FROM processing_history WHERE id=?", (result.history_id,)).fetchone()[0] == "ready_for_review"


def test_stop_after_partial_edit_preserves_result_and_skips_later_stages(uploader):
    prepare_mock_workflow(uploader)

    def description():
        uploader._changed_fields.append("description_lt")
        uploader.request_stop()

    uploader.uploadDescription = description
    result = uploader.run()
    assert result.status == PimPreparationStatus.FAILED
    assert result.product_id == "p-1" and result.initial_version == 3
    assert "description_lt" in result.changed_fields
    assert result.failed_stage == "description"
    uploader.pim_editor.set_brand.assert_not_called()
    uploader.pim_editor.set_specification.assert_not_called()
    uploader.pim_editor.generate_description.assert_not_called()




def test_orbea_stop_before_service_creation_survives_token_replacement():
    from GUI_Qt.orbea.workers import OrbeaRunWorker
    calls = []

    def run(config, **kwargs):
        calls.append(kwargs["cancellation"].is_cancelled())
        return None

    worker = OrbeaRunWorker(None, lambda driver: SimpleNamespace(run=run), None,
                            resume=False, retry_failed=False)
    worker.request_stop()
    worker.run()
    assert calls == [True]


def test_kross_rejects_conflicts_while_orbea_retains_component_rows_for_ai():
    from tools.orbea_automation.specifications import build_orbea_specification_plan
    from tools.kross_automation.specifications import build_kross_specification_plan
    plan = build_orbea_specification_plan("Orbea Orca", [], "Fork: Carbon\nFork: Suspension")
    assert "Fork: Carbon" in plan.magic_ai_source and "Fork: Suspension" in plan.magic_ai_source
    assert "Šakė" not in dict(plan.values)
    with pytest.raises(ValueError, match="Conflicting"):
        build_kross_specification_plan("KROSS", [], "Widelec: A\nWidelec: B")


def test_octane_does_not_invent_a_front_derailleur(db, monkeypatch, tmp_path):
    from Scrapers.OctaneScraper import scrapeAndTranslateToFileOctaneOne
    html = '<div class="div-spec-item"><div class="tb-spec-type">DERAILLEURS</div><div class="tb-spec-text">SRAM NX 1x11</div></div>'
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: response(html))
    with pytest.raises(RuntimeError, match="verify front and rear"):
        scrapeAndTranslateToFileOctaneOne("url", str(tmp_path / "octane.txt"), db_manager=db)


@pytest.mark.parametrize("value,expected", [("true", True), ("YES", True), ("1", True), (" false ", False), ("NO", False), ("", False), (None, False)])
def test_single_and_batch_option_normalization_agree(db, value, expected):
    processor = BatchProcessor(driver=Mock(), db_manager=db)
    processor.add_to_queue("Pinarello", "SKU", "url", {"frameset_only": value, "append_disclaimer": value})
    options = processor.queue[0]["brand_options"]
    assert options["frameset_only"] is expected and options["append_disclaimer"] is expected


def test_standard_image_stage_calls_the_download_and_editor_contract(uploader, tmp_path):
    path = tmp_path / "bike.png"
    Image.new("RGB", (2, 2)).save(path)
    uploader.image_handler.download_kross_images = Mock(return_value=[str(path)])
    uploader.pim_editor.upload_product_images.return_value = 1
    uploader.uploadImages()
    uploader.pim_editor.upload_product_images.assert_called_once_with([str(path)], skip_if_present=True)
    assert uploader.images_uploaded == 1 and "images" in uploader._changed_fields
    uploader.image_handler.download_kross_images.side_effect = RuntimeError("No current images")
    with pytest.raises(RuntimeError, match="No current images"):
        uploader.uploadImages()


def test_batch_preserves_supplier_selection_options(db, monkeypatch):
    module = importlib.import_module("Utilities.BatchProcessor")
    captured = []

    def constructor(**kwargs):
        captured.append(kwargs["brand_options"])
        return SimpleNamespace(run=lambda: PimPreparationResult("SKU", status=PimPreparationStatus.FAILED))

    monkeypatch.setattr(module, "getUploaderClass", lambda brand: constructor)
    BatchProcessor(Mock(), db).process_batch([{"brand": "Rascal", "code": "SKU", "url": "url", "variant_index": "1", "preferred_size": "M", "append_disclaimer": "false"}])
    assert captured[0]["variant_index"] == 1
    assert captured[0]["preferred_size"] == "M"
    assert captured[0]["append_disclaimer"] is False


def test_kross_source_wheel_size_takes_precedence_over_old_pimbo_title():
    from tools.kross_automation.specifications import build_kross_specification_plan
    plan = build_kross_specification_plan('KROSS LEVEL 29" Black (Matte)', ["M"], 'Rozmiar koła: 27.5"')
    assert dict(plan.values)["Ratų dydis"] == '27.5"'


def test_automatic_save_refuses_a_version_changed_since_preparation():
    editor = PimboProductEditor(SimpleNamespace(current_url="https://pim.bo.ultrabike.lt/dashboard/products/p-1"))
    editor.current_status = lambda: "Draft"
    editor.current_version = lambda: 5
    editor.save_button = Mock()
    editor._click = Mock()
    result = editor.save_and_verify(PimPreparationResult("SKU", "p-1", initial_version=4, status=PimPreparationStatus.READY_FOR_REVIEW))
    assert result.status == PimPreparationStatus.FAILED
    assert "version changed" in result.error
    editor._click.assert_not_called()


@pytest.mark.parametrize("module_name", ["Basso", "LeeCougan"])
def test_supplier_credential_errors_stop_before_scraping(db, module_name):
    module = importlib.import_module(f"Uploaders.{module_name}")
    uploader = getattr(module, module_name)(driver=Mock(), brand_name=module_name,
        product_code="SKU", url_or_code="supplier", db_manager=db, master_password="test")
    uploader.session_manager.get_external_credentials = Mock(side_effect=RuntimeError("unlock failed"))
    uploader.translationManager.prepareTranslationFiles = Mock()
    with pytest.raises(RuntimeError, match="unlock failed"):
        uploader.scrape()
    uploader.translationManager.prepareTranslationFiles.assert_not_called()


@pytest.mark.parametrize("alias", ["Le Grand", "LE GRAND", " le grand ", "legrand"])
def test_le_grand_alias_resolves_consistently(alias):
    from uploaderFactory import getUploaderClass
    from Uploaders.KROSS import KROSS
    assert getUploaderClass(alias) is KROSS


def test_trek_reads_injected_translations_independently_of_working_directory(db, monkeypatch, tmp_path):
    from Scrapers.TREKScraper import scrapeAndTranslateToFileTREK
    monkeypatch.chdir(tmp_path)
    html = '<div class="pdl-collapse-item is-active"><div class="flex items-center grow">Frameset</div><table class="sprocket__table spec"><tr><th>Frame</th><td>Carbon</td></tr></table></div>'
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: response(html))
    path = tmp_path / "trek.txt"
    scrapeAndTranslateToFileTREK("supplier", str(path), db_manager=db)
    assert FileHandler.read_translated_file(path) == [{"Frame": "Carbon"}]

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from Config.Selectors import LoginSelectors, ProductListSelectors
from Database.DatabaseManager import DatabaseManager
from Database.SettingsManager import SettingsManager
from Managers.PimboProductEditor import (
    PimAiStepResult,
    PimAutomationError,
    PimPreparationResult,
    PimPreparationStatus,
    PimboProductEditor,
    _is_lithuanian_copy,
)
from Managers.BrowserSessionManager import BrowserSessionManager
from tools.orbea_automation.pimbo import PimboBrowserClient
from Utilities.BatchProcessor import BatchProcessor


class _Driver:
    def __init__(self, url: str = "https://pim.bo.ultrabike.lt/dashboard/products/p-1"):
        self.current_url = url


class _DraftGuardEditor(PimboProductEditor):
    def __init__(self, status: str):
        super().__init__(_Driver())
        self.status = status
        self.capture_calls = 0

    def wait_ready(self):
        return None

    def external_id(self):
        return "SKU-1"

    def current_status(self):
        return self.status

    def current_version(self):
        return 8

    def capture_field_state(self):
        self.capture_calls += 1
        return {"status": self.status}


class _ReviewEditor(PimboProductEditor):
    def __init__(self, *, dirty: bool, version: int):
        super().__init__(_Driver(), timeout=0.05)
        self.dirty = dirty
        self.version = version

    @property
    def product_id(self):
        return "p-1"

    def external_id(self):
        return "SKU-1"

    def is_dirty(self):
        return self.dirty

    def current_version(self):
        return self.version


class _AutomaticSaveEditor(_ReviewEditor):
    def __init__(self):
        super().__init__(dirty=True, version=4)

    def current_status(self):
        return "Draft"

    def save_button(self):
        return self

    def is_enabled(self):
        return True

    def _click(self, _element):
        self.dirty = False
        self.version += 1


class _FileInput:
    def __init__(self):
        self.value = ""

    def is_displayed(self):
        return False

    def send_keys(self, value):
        self.value = value


class _FileDriver(_Driver):
    def __init__(self):
        super().__init__()
        self.file_input = _FileInput()

    def find_elements(self, by, value):
        if "input[type='file']" in value:
            return [self.file_input]
        return []


class _FileEditor(PimboProductEditor):
    def open_section(self, section):
        self.opened = section


class _GroupedFileInput(_FileInput):
    def __init__(self, context):
        super().__init__()
        self.context = context


class _GroupedFileDriver(_Driver):
    def __init__(self):
        super().__init__()
        self.inputs = [
            _GroupedFileInput("Product images"),
            _GroupedFileInput("Size tables"),
            _GroupedFileInput("Geometry"),
        ]

    def find_elements(self, by, value):
        if "input[type='file']" in value:
            return self.inputs
        return []


class _GroupedFileEditor(PimboProductEditor):
    def open_section(self, section):
        self.opened = section

    def _image_input_context(self, element):
        return element.context.casefold()


class _ValueInput:
    def get_attribute(self, name):
        return "" if name == "value" else None


class _ScriptCaptureDriver(_Driver):
    def __init__(self):
        super().__init__()
        self.scripts = []

    def execute_script(self, script, *args):
        self.scripts.append(script)
        return ""


class _ScriptCaptureEditor(PimboProductEditor):
    def open_section(self, section):
        return None

    def _find_visible(self, by, value):
        return _ValueInput()


class _MagicOrderEditor(PimboProductEditor):
    def __init__(self):
        super().__init__(_Driver())
        self.calls: list[str] = []

    def _step(self, name):
        self.calls.append(name)
        return PimAiStepResult(name, True, True)

    def generate_product_name(self):
        return self._step("product_name")

    def generate_description(self):
        return self._step("description")

    def suggest_category(self, family="Dviračiai"):
        self.calls.append(f"family:{family}")
        return PimAiStepResult("category", True, True)

    def fill_empty_specifications_with_ai(self, source_text):
        self.calls.append(f"source:{source_text}")
        return PimAiStepResult("specifications", True, True)

    def translate_lt_to_all(self, *, overwrite=True):
        self.calls.append(f"translate:{overwrite}")
        return PimAiStepResult("translation", True, True)

    def switch_locale(self, locale):
        self.calls.append(f"locale:{locale}")


class _LocalizedDescriptionEditor(PimboProductEditor):
    def __init__(self):
        super().__init__(_Driver())
        self.locale = "lt"
        self.calls = []

    def switch_locale(self, locale):
        self.locale = locale
        self.calls.append(f"locale:{locale}")

    def set_description_html(self, value):
        self.calls.append(f"description:{self.locale}:{value}")
        return self.locale != "en"


class _LocalizedNameFallbackEditor(PimboProductEditor):
    def __init__(self, *, lt_name="", en_name="KROSS Alta 4.0"):
        super().__init__(_Driver())
        self.locale = "lt"
        self.names = {"lt": lt_name, "en": en_name}
        self.calls = []

    def switch_locale(self, locale):
        self.locale = locale
        self.calls.append(f"locale:{locale}")

    def product_name(self):
        self.calls.append(f"read:{self.locale}")
        return self.names.get(self.locale, "")

    def set_product_name(self, value):
        self.calls.append(f"set:{self.locale}:{value}")
        self.names[self.locale] = value
        return True


class _FamilySelectionEditor(PimboProductEditor):
    def __init__(self, current):
        super().__init__(_Driver())
        self.current = current
        self.selected = []

    def open_section(self, section):
        return None

    def _find_visible(self, by, value):
        return object()

    def _combobox_value(self, placeholder):
        return self.current

    def _select_combobox(self, placeholder, value, *, required=True):
        self.selected.append((placeholder, value))
        self.current = value
        return True


class _EmptyDescriptionEditor(PimboProductEditor):
    def __init__(self):
        super().__init__(_Driver())
        self.clicked = False

    def switch_locale(self, locale):
        return None

    def open_section(self, section):
        return None

    def description_html(self):
        return "<p> </p>"

    def _click(self, element):
        self.clicked = True


class _NoSeoSnapshotEditor(PimboProductEditor):
    def __init__(self):
        super().__init__(_Driver())
        self.locale = "lt"

    def switch_locale(self, locale):
        self.locale = locale

    def product_name(self):
        return f"name-{self.locale}"

    def description_html(self):
        return f"<p>description-{self.locale}</p>"

    def seo_copy(self):
        raise AssertionError("SEO must never be opened during translation validation")


class _CategoryLeafEditor(PimboProductEditor):
    def __init__(self):
        super().__init__(_Driver())
        self.category_reads = 0
        self.clicks = 0

    def switch_locale(self, locale):
        return None

    def open_section(self, section):
        return None

    def _find_visible(self, by, value):
        return object()

    def _selected_category(self):
        self.category_reads += 1
        return "" if self.category_reads == 1 else "Miesto dviračiai"

    def _click(self, element):
        self.clicks += 1

    def _wait_until(self, predicate, message, timeout=None):
        result = predicate()
        if not result:
            raise AssertionError(message)
        return result


class _MagicElement:
    def __init__(self, name):
        self.name = name

    def is_displayed(self):
        return True


class _DescriptionMagicPanel:
    def __init__(self):
        self.generate = _MagicElement("generate")
        self.apply = _MagicElement("apply")

    def find_elements(self, by, value):
        if "Generate" in value or "Regenerate" in value:
            return [self.generate]
        if "Apply" in value:
            return [self.apply]
        return []


class _DescriptionMagicDriver(_Driver):
    def __init__(self):
        super().__init__()
        self.magic = _MagicElement("magic")

    def find_elements(self, by, value):
        return [self.magic] if "MagicAI" in value else []


class _PolishDescriptionMagicEditor(PimboProductEditor):
    SOURCE = "<p>Pełny opis produktu KROSS ze wszystkimi informacjami.</p>"

    def __init__(self):
        super().__init__(_DescriptionMagicDriver())
        self.current = self.SOURCE
        self.panel = _DescriptionMagicPanel()
        self.panel_open = False
        self.restored = []
        self.translated_sources = []

    def switch_locale(self, locale):
        return None

    def open_section(self, section):
        return None

    def description_html(self):
        return self.current

    def _magic_panel(self, title):
        return self.panel if self.panel_open else None

    def _choose_magic_template(self, panel, template):
        return None

    def _wait_magic_apply(self, panel):
        return None

    def _click(self, element):
        if element.name == "magic":
            self.panel_open = True
        elif element.name == "generate":
            self.current = "<p>Wygenerowany opis nadal jest po polsku.</p>"
        elif element.name == "apply":
            self.panel_open = False

    def _wait_until(self, predicate, message, timeout=None):
        result = predicate()
        if not result:
            raise AssertionError(message)
        return result

    def set_description_html(self, value):
        self.current = value
        self.restored.append(value)
        return True

    def translate_current_description_to_lt(self, generated_html):
        self.translated_sources.append(generated_html)
        self.current = (
            "<p>Šis išsamus KROSS dviračio aprašymas buvo išverstas į lietuvių "
            "kalbą ir išsaugo visas svarbiausias produkto savybes.</p>"
        )
        return self.current


class _FailedDescriptionTranslationEditor(_PolishDescriptionMagicEditor):
    def translate_current_description_to_lt(self, generated_html):
        self.translated_sources.append(generated_html)
        raise PimAutomationError("field translator unavailable")


class PimboWorkflowTests(unittest.TestCase):
    def test_current_routes_and_semantic_editor_selectors(self):
        self.assertTrue(LoginSelectors.URL.endswith("/dashboard/login"))
        self.assertTrue(ProductListSelectors.URL.endswith("/dashboard/products"))
        self.assertEqual(
            {"general", "variants", "attributes", "specifications", "seo", "metadata"},
            set(PimboProductEditor.SECTION_VALUES.values()),
        )
        self.assertEqual(("lt", "en", "lv", "ee"), PimboProductEditor.LOCALES)

    def test_non_draft_is_blocked_before_state_capture_or_mutation(self):
        editor = _DraftGuardEditor("Published")
        result = editor.begin("SKU-1")
        self.assertEqual(PimPreparationStatus.BLOCKED_NON_DRAFT, result.status)
        self.assertEqual(0, editor.capture_calls)
        self.assertEqual(8, result.initial_version)

    def test_draft_captures_initial_version_and_fields(self):
        editor = _DraftGuardEditor("Draft")
        result = editor.begin("SKU-1")
        self.assertEqual(8, result.initial_version)
        self.assertEqual({"status": "Draft"}, result.initial_fields)
        self.assertEqual(1, editor.capture_calls)

    def test_result_round_trip_preserves_structured_ai_data(self):
        original = PimPreparationResult(
            product_code="SKU-1",
            product_id="p-1",
            initial_version=4,
            initial_fields={"status": "Draft"},
            status=PimPreparationStatus.READY_FOR_REVIEW,
            changed_fields=("brand", "description"),
            ai_steps=(PimAiStepResult("description", True, True, 2, "ok"),),
            warnings=("missing attribute",),
            final_url="https://pim.bo.ultrabike.lt/dashboard/products/p-1",
        )
        restored = PimPreparationResult.from_dict(original.to_dict())
        self.assertEqual(original, restored)

    def test_finish_requires_enabled_manual_save(self):
        base = PimPreparationResult(
            product_code="SKU-1", product_id="p-1", initial_version=1
        )
        ready = _ReviewEditor(dirty=True, version=1).finish(
            base, changed_fields=("brand",)
        )
        self.assertEqual(PimPreparationStatus.READY_FOR_REVIEW, ready.status)
        clean = _ReviewEditor(dirty=False, version=1).finish(base)
        self.assertEqual(PimPreparationStatus.FAILED, clean.status)

    def test_manual_save_needs_clean_form_and_higher_version(self):
        ready = PimPreparationResult(
            product_code="SKU-1",
            product_id="p-1",
            initial_version=3,
            status=PimPreparationStatus.READY_FOR_REVIEW,
        )
        verified = _ReviewEditor(dirty=False, version=4).verify_manual_save(ready)
        self.assertEqual(PimPreparationStatus.SAVED_MANUALLY, verified.status)
        stale = _ReviewEditor(dirty=False, version=3).verify_manual_save(ready)
        self.assertEqual(PimPreparationStatus.FAILED, stale.status)

    def test_explicit_automatic_save_requires_a_ready_draft_and_version_increment(self):
        ready = PimPreparationResult(
            product_code="SKU-1",
            product_id="p-1",
            initial_version=4,
            status=PimPreparationStatus.READY_FOR_REVIEW,
        )
        saved = _AutomaticSaveEditor().save_and_verify(ready)
        self.assertEqual(PimPreparationStatus.SAVED_AUTOMATICALLY, saved.status)

        blocked = _AutomaticSaveEditor().save_and_verify(
            ready.with_status(PimPreparationStatus.FAILED)
        )
        self.assertEqual(PimPreparationStatus.FAILED, blocked.status)

    def test_localized_descriptions_use_one_editor_and_return_to_lt(self):
        editor = _LocalizedDescriptionEditor()
        changed = editor.set_localized_descriptions(
            {"lt": "<p>LT</p>", "en": "<p>EN</p>", "lv": ""}
        )
        self.assertEqual(("lt",), changed)
        self.assertEqual("lt", editor.locale)
        self.assertEqual(
            [
                "locale:lt",
                "description:lt:<p>LT</p>",
                "locale:en",
                "description:en:<p>EN</p>",
                "locale:lt",
            ],
            editor.calls,
        )

    def test_direct_file_input_upload_avoids_native_dialog(self):
        driver = _FileDriver()
        editor = _FileEditor(driver)
        count = editor.upload_product_images([r"C:\one.jpg", r"C:\two.png"])
        self.assertEqual(2, count)
        self.assertEqual("general", editor.opened)
        self.assertEqual("C:\\one.jpg\nC:\\two.png", driver.file_input.value)

    def test_table_images_are_routed_to_distinct_semantic_upload_areas(self):
        driver = _GroupedFileDriver()
        editor = _GroupedFileEditor(driver)

        editor.upload_product_images([r"C:\bike.jpg"], skip_if_present=False)
        editor.upload_size_table_images([r"C:\size.png"], skip_if_present=False)
        editor.upload_geometry_images([r"C:\geometry.png"], skip_if_present=False)

        self.assertEqual(r"C:\bike.jpg", driver.inputs[0].value)
        self.assertEqual(r"C:\size.png", driver.inputs[1].value)
        self.assertEqual(r"C:\geometry.png", driver.inputs[2].value)

    def test_table_upload_never_falls_back_to_product_photo_input(self):
        driver = _GroupedFileDriver()
        driver.inputs = [_GroupedFileInput("Product images")]
        editor = _GroupedFileEditor(driver)

        with self.assertRaisesRegex(PimAutomationError, "Size tables"):
            editor.upload_size_table_images([r"C:\size.png"], skip_if_present=False)
        self.assertEqual("", driver.inputs[0].value)

    def test_combobox_browser_script_keeps_newline_regex_on_one_line(self):
        driver = _ScriptCaptureDriver()
        editor = _ScriptCaptureEditor(driver)

        editor._combobox_value("Search brands...")

        script = driver.scripts[-1]
        self.assertIn(r"split(/\n/)", script)
        self.assertNotIn("split(/\n/)", script)

    def test_product_family_replaces_draft_instead_of_treating_it_as_family(self):
        editor = _FamilySelectionEditor("Draft")

        changed = editor.ensure_product_family("Dviračiai")

        self.assertTrue(changed)
        self.assertEqual(
            [("Search families...", "Dviračiai")],
            editor.selected,
        )

    def test_description_magicai_is_never_opened_for_an_empty_source(self):
        editor = _EmptyDescriptionEditor()

        with self.assertRaisesRegex(PimAutomationError, "source is empty"):
            editor.generate_description()

        self.assertFalse(editor.clicked)

    def test_localized_copy_snapshot_never_reads_or_opens_seo(self):
        editor = _NoSeoSnapshotEditor()

        snapshot = editor.localized_copy_snapshot("en")

        self.assertEqual(
            {"name": "name-en", "description": "<p>description-en</p>"},
            snapshot,
        )

    def test_empty_lithuanian_name_is_seeded_from_english_and_returns_to_lt(self):
        editor = _LocalizedNameFallbackEditor()

        changed = editor.ensure_lithuanian_name_from_english()

        self.assertTrue(changed)
        self.assertEqual("KROSS Alta 4.0", editor.names["lt"])
        self.assertEqual("lt", editor.locale)
        self.assertEqual(
            [
                "locale:lt", "read:lt", "locale:en", "read:en",
                "locale:lt", "set:lt:KROSS Alta 4.0", "read:lt",
            ],
            editor.calls,
        )

    def test_existing_lithuanian_name_is_never_replaced_from_english(self):
        editor = _LocalizedNameFallbackEditor(lt_name="KROSS Alta 4.0 LT")

        changed = editor.ensure_lithuanian_name_from_english()

        self.assertFalse(changed)
        self.assertEqual("KROSS Alta 4.0 LT", editor.names["lt"])
        self.assertNotIn("locale:en", editor.calls)

    def test_category_magicai_accepts_a_valid_leaf_category_in_one_click(self):
        editor = _CategoryLeafEditor()

        result = editor.suggest_category("Dviračiai")

        self.assertTrue(result.success)
        self.assertTrue(result.changed)
        self.assertEqual("Miesto dviračiai", result.detail)
        self.assertEqual(1, editor.clicks)

    def test_non_lithuanian_description_magicai_translates_current_field_to_lt(self):
        editor = _PolishDescriptionMagicEditor()

        result = editor.generate_description()

        self.assertTrue(result.success)
        self.assertTrue(result.changed)
        self.assertIn("Translate current field", result.detail)
        self.assertEqual(
            ["<p>Wygenerowany opis nadal jest po polsku.</p>"],
            editor.translated_sources,
        )
        self.assertIn("lietuvių kalbą", editor.current)
        self.assertEqual([], editor.restored)

    def test_failed_description_field_translation_restores_kross_source(self):
        editor = _FailedDescriptionTranslationEditor()

        result = editor.generate_description()

        self.assertTrue(result.success)
        self.assertFalse(result.changed)
        self.assertIn("translation failed", result.detail)
        self.assertEqual(editor.SOURCE, editor.current)
        self.assertEqual([editor.SOURCE], editor.restored)

    def test_magic_ai_orchestration_order_and_lt_return(self):
        editor = _MagicOrderEditor()
        steps = editor.run_full_magic_ai("raw supplier text")
        self.assertEqual(5, len(steps))
        self.assertEqual(
            [
                "product_name",
                "description",
                "family:Dviračiai",
                "source:raw supplier text",
                "translate:True",
                "locale:lt",
            ],
            editor.calls,
        )

    def test_specification_ai_transition_only_fills_empty_fields(self):
        filled, overwritten = PimboProductEditor.validate_specification_transition(
            ["Carbon", "", "12"],
            ["Carbon", "Shimano", "12"],
        )
        self.assertEqual(1, filled)
        self.assertEqual((), overwritten)
        _, overwritten = PimboProductEditor.validate_specification_transition(
            ["Carbon", ""], ["Aluminium", "Shimano"]
        )
        self.assertEqual((0,), overwritten)

    def test_translation_validation_never_requires_or_reads_seo(self):
        before = {
            code: {"name": "old", "description": "<p>old</p>", "seo": {"title": "old"}}
            for code in ("en", "lv", "ee")
        }
        after = {
            code: {"name": "new", "description": "<p>new</p>", "seo": {"title": "new"}}
            for code in ("en", "lv", "ee")
        }
        self.assertEqual("", PimboProductEditor._translation_validation_error(before, after))
        after["ee"]["seo"] = {}
        self.assertEqual("", PimboProductEditor._translation_validation_error(before, after))

    def test_description_guard_rejects_magicai_request_for_more_source_data(self):
        self.assertFalse(
            _is_lithuanian_copy(
                "Supratau. Prašau pateikti turimus produkto duomenis, aprašymą, "
                "specifikacijas ar kitą techninę informaciją, ir aš nedelsdamas "
                "sugeneruosiu struktūrizuotą HTML aprašymą pagal reikalavimus."
            )
        )

    def test_lithuanian_description_guard(self):
        self.assertTrue(
            _is_lithuanian_copy(
                "Šis dviratis yra skirtas ilgesnėms kelionėms ir turi lengvą rėmą, "
                "kuris užtikrina patogų bei stabilų važiavimą įvairiomis sąlygomis."
            )
        )
        self.assertFalse(_is_lithuanian_copy("A short English description."))

    def test_ready_batch_result_is_not_counted_as_success(self):
        class Uploader:
            def run(self):
                return PimPreparationResult(
                    product_code="SKU-1",
                    status=PimPreparationStatus.READY_FOR_REVIEW,
                )

        processor = BatchProcessor(_Driver(), object())
        processor.add_to_queue("KROSS", "SKU-1", "supplier")
        summary = processor.start_batch(lambda *args: Uploader())
        self.assertEqual(0, summary["success"])
        self.assertEqual(1, summary["ready_for_review"])

    def test_auto_save_setting_is_ignored_but_magic_templates_are_configurable(self):
        db = DatabaseManager(":memory:")
        try:
            settings = SettingsManager(db)
            settings.set("auto_save", True)
            settings.set("magicai_title_template", "Mano vardas")
            self.assertFalse(settings.is_auto_save_enabled())
            self.assertEqual("Mano vardas", settings.get_magicai_title_template())
            self.assertEqual("Aprašymas LT", settings.get_magicai_description_template())
        finally:
            db.close()

    def test_active_workflows_do_not_call_legacy_save_or_pywinauto(self):
        root = Path(__file__).resolve().parents[1]
        active_files = [
            root / "Uploaders" / "BaseUploader.py",
            root / "Utilities" / "BatchProcessor.py",
            root / "GUI_Qt" / "workers" / "batch_workers.py",
            root / "Utilities" / "ImageHandler.py",
        ]
        source = "\n".join(path.read_text(encoding="utf-8") for path in active_files)
        self.assertNotIn(".save_information(", source)
        self.assertNotIn("pywinauto", source.casefold())

    def test_legacy_pimbo_adapters_and_duplicate_selectors_are_removed(self):
        root = Path(__file__).resolve().parents[1]
        removed = [
            root / "Utilities" / "WebIntercationHandler.py",
            root / "Managers" / "AttributeUploader.py",
            root / "Managers" / "ImageUploader.py",
            root / "Managers" / "FeatureUploader" / "FeatureUploader.py",
            root / "Managers" / "FeatureUploader" / "FieldWriter.py",
            root / "Managers" / "FeatureUploader" / "LanguageSwitcher.py",
        ]
        self.assertTrue(all(not path.exists() for path in removed))
        selectors = (root / "Config" / "Selectors.py").read_text(encoding="utf-8")
        for old_class in (
            "ProductEditorSelectors",
            "BrandSelectors",
            "FeatureSelectors",
            "AttributeSelectors",
            "VariantSelectors",
            "ImageSelectors",
        ):
            self.assertNotIn(f"class {old_class}", selectors)

    def test_browser_pool_initializes_and_reinitializes_each_session(self):
        class Driver:
            def __init__(self, number):
                self.number = number
                self.quit_calls = 0

            def quit(self):
                self.quit_calls += 1

        manager = BrowserSessionManager(pool_size=1)
        created = []
        initialized = []

        def create(session_id):
            driver = Driver(len(created))
            created.append(driver)
            return driver

        manager._create_driver = create
        manager.set_session_initializer(
            lambda driver: initialized.append(driver.number) is None
        )
        self.assertTrue(manager.initialize_pool())
        self.assertEqual(1, manager.pool_size)
        self.assertEqual([0], initialized)
        self.assertTrue(manager.reset_session(manager.sessions[0]))
        self.assertEqual([0, 1], initialized)
        manager.shutdown_all()

    def test_orbea_read_only_client_refuses_to_discard_dirty_product(self):
        class Driver(_Driver):
            def __init__(self):
                super().__init__()
                self.navigation_calls = 0

            def get(self, _url):
                self.navigation_calls += 1

        driver = Driver()
        client = PimboBrowserClient(driver)
        with patch.object(PimboProductEditor, "is_dirty", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "will not discard"):
                client.ensure_products_page()
        self.assertEqual(0, driver.navigation_calls)

    def test_pimbo_safe_click_falls_back_when_sticky_toolbar_intercepts_pointer(self):
        class Element:
            def __init__(self):
                self.native_clicks = 0

            def click(self):
                self.native_clicks += 1
                raise RuntimeError("element click intercepted")

        class Driver(_Driver):
            def __init__(self):
                super().__init__()
                self.dom_clicks = 0

            def execute_script(self, script, _element):
                if "arguments[0].click" in script:
                    self.dom_clicks += 1

        driver = Driver()
        element = Element()
        clicked = PimboBrowserClient(driver)._safe_click(
            lambda: element,
            "covered control",
        )

        self.assertIs(element, clicked)
        self.assertEqual(1, element.native_clicks)
        self.assertEqual(1, driver.dom_clicks)


if __name__ == "__main__":
    unittest.main()

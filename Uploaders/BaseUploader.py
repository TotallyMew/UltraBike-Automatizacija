# Standard library
import json
import re
import time
from threading import Event
from abc import ABC, abstractmethod
from datetime import datetime
from dataclasses import replace

# Local application imports
from Database.DatabaseManager import DatabaseManager
from Database.SessionManager import SessionManager
from Database.SettingsManager import SettingsManager
from Managers.DescriptionManager import DescriptionManager
from Managers.PimboProductEditor import (
    PimAiStepResult,
    PimAutomationError,
    PimPreparationResult,
    PimPreparationStatus,
    PimboProductEditor,
)
from Managers.TranslationManager import TranslationManager
from Utilities.ErrorManager import ErrorManager
from Utilities.ImageHandler import ImageHandler
from Utilities.ProductNavigationHandler import ProductNavigationHandler
from Utilities.ProductDataSafety import normalize_brand_options
from Database.ConnectionAccess import with_database_lock

class ProductUploader(ABC):
    def set_retry_callback(self, callback):
        # Set callback for navigation manager and any other retry points
        if hasattr(self, 'navigation_manager') and self.navigation_manager:
            self.navigation_manager.set_retry_callback(callback)
        self._retry_callback = callback

    def set_progress_callback(self, callback):
        self._progress_callback = callback

    def _progress(self, message):
        callback = getattr(self, "_progress_callback", None)
        if callback:
            callback(str(message))

    def __init__(self, driver, brand_name, product_code=None, url_or_code=None,
                 db_manager=None, brand_options=None, logger=None, batch_id=None,
                 master_password=None, settings_manager=None):
        """Initialize ProductUploader with snake_case parameters.

        Args:
            driver: Selenium WebDriver instance
            brand_name: Brand name (e.g., "TREK", "Pinarello")
            product_code: UltraBike product code (optional if url_or_code provided)
            url_or_code: Brand-specific URL or code (optional if product_code provided)
            db_manager: Database manager instance (created if not provided)
            brand_options: Dict of brand-specific options (description_name, frameset_only, etc.)
            logger: Logger instance
            batch_id: Batch ID for batch processing
            master_password: Master password for decrypting credentials
            settings_manager: Settings manager instance (created if not provided)
        """
        # Validate required parameters
        if product_code is None and url_or_code is None:
            raise ValueError("Product identifier missing: provide 'product_code' or 'url_or_code'")

        # Assign core attributes
        self.driver = driver
        self.logger = logger
        self.brandName = brand_name
        self.brand_options = normalize_brand_options(brand_options)
        self._stop_requested = Event()
        self.batch_id = batch_id
        self.master_password = master_password

        # Product identifiers
        self.ultraBikeCode = product_code
        self.bicycleUrlOrCode = url_or_code

        # Counters
        self.features_uploaded = 0
        self.images_uploaded = 0

        # Handlers
        self.navigation_manager = ProductNavigationHandler(self.driver, self.logger)
        # Database setup
        if db_manager:
            self.db = db_manager
        else:
            self.db = DatabaseManager()

        # Settings manager
        try:
            self.session_manager = SessionManager(self.db)
            self.settings_manager = settings_manager or SettingsManager(self.db)
        except Exception as e:
            ErrorManager.show_error("UNEXPECTED_ERROR", error=str(e))
            self.session_manager = SessionManager(self.db)
            self.settings_manager = SettingsManager(self.db)

        self.translationManager = TranslationManager(self.brandName, self.db, self.logger)
        self.image_handler = ImageHandler(self.settings_manager, self.logger)
        self.pim_editor = PimboProductEditor(self.driver, self.logger)
        self.preparation_result = PimPreparationResult(
            product_code=self.ultraBikeCode or "",
        )
        self._changed_fields = []
        self._preparation_warnings = []
        self._ai_steps = []

        # Description handling - always initialize manager (needed for standalone disclaimer)
        self.description_manager = DescriptionManager(self.db, self.logger)
        self.description_name = self.brand_options.get('description_name', None)
        # Debug: description_name and manager init can be logged if needed
    
    def _log(self, message, **context):
        if self.logger:
            self.logger.log(f"{self.brandName}Uploader", message, **context)

    def _log_error(self, message, exception=None, **context):
        if self.logger:
            self.logger.error(f"{self.brandName}Uploader", message, exception=exception, **context)

    def request_stop(self):
        self._stop_requested.set()

    def _run_stage(self, stage, action, *args, **kwargs):
        self.failed_stage = stage
        if self._stop_requested.is_set():
            raise PimAutomationError("Upload stopped. Review or reload any unsaved PIMBO changes.")
        result = action(*args, **kwargs)
        if self._stop_requested.is_set():
            raise PimAutomationError("Upload stopped. Review or reload any unsaved PIMBO changes.")
        return result

    def run(self):
        """Main execution flow with database tracking"""
        self._log("Starting upload process", code=self.ultraBikeCode)
        self.start_time = time.time()

        try:
            # Main upload workflow
            print(f"[Upload] === Starting upload for {self.ultraBikeCode} ({self.brandName}) ===")
            print(f"[Upload] Step 1/9: Scraping...")
            self._progress("Renkami tiekėjo duomenys")
            self._run_stage("scrape", self.scrape)
            self._magicai_source_text = getattr(
                self.translationManager,
                "raw_source_text",
                "",
            )
            print(f"[Upload] Step 2/9: Translating...")
            self._run_stage("translate", self.translate)
            # Validate the selected copy before changing the product.
            self._run_stage("description_source", self._prepare_description)
            print(f"[Upload] Step 3/9: Opening product...")
            self._run_stage("open_product", self.openProduct)
            self.preparation_result = self._run_stage("begin", self.pim_editor.begin, self.ultraBikeCode)
            if self.preparation_result.status == PimPreparationStatus.BLOCKED_NON_DRAFT:
                duration = time.time() - self.start_time
                self._record_preparation(duration)
                ErrorManager.show_warning(
                    "Produktas nėra Draft — automatizacija jo nepakeitė."
                )
                return self.preparation_result

            if self._run_stage("product_family", self.pim_editor.ensure_product_family, "Dviračiai"):
                self._changed_fields.append("product_family")

            # === BASIC INFO TAB ===
            # Images
            if self.settings_manager.download_pictures_and_upload():
                print(f"[Upload] Step 4/9: Uploading images...")
                self._run_stage("images", self.uploadImages)
                print(f"[Upload] Images uploaded")
            else:
                print(f"[Upload] Step 4/9: Image upload disabled, skipping")

            # Description
            print(f"[Upload] Step 5/9: Uploading description...")
            self._run_stage("description", self.uploadDescription)
            print(f"[Upload] Description done")

            # Brand
            print(f"[Upload] Step 6/9: Uploading brand...")
            if self._run_stage("brand", self.uploadBrand):
                self._changed_fields.append("brand")
            print(f"[Upload] Brand done")

            # An existing PIM title can belong to an older configuration. Only
            # supplier data and explicitly selected attributes are authoritative.

            # === ATTRIBUTES TAB ===
            print(f"[Upload] Step 7/9: Uploading attributes...")
            self._run_stage("attributes", self.uploadAttributes)
            print(f"[Upload] Attributes done")

            # === VARIANTS TAB ===
            print(f"[Upload] Step 8/9: Collecting variant sizes...")
            self._run_stage("variants", self.collectVariantSizes)
            print(f"[Upload] Variant sizes done")

            # === SPECIFICATIONS TAB ===
            print(f"[Upload] Step 9/9: Uploading features...")
            self._run_stage("specifications", self.uploadFeatures)
            self._run_stage("variant_sizes", self.fillVariantSizesIntoSpecs)
            self._run_stage("groupset", self.extractKomplektacijaFromSpecs)
            print(f"[Upload] Features done")

            print("[Upload] Running current PIMBO MagicAI workflow...")
            self._progress("MagicAI: pradedamas produkto paruošimas")
            self._run_stage("magicai", self.runMagicAi)
            print("[Upload] MagicAI workflow done")

            self.preparation_result = self._run_stage("finish", self.pim_editor.finish,
                self.preparation_result,
                changed_fields=self._changed_fields,
                ai_steps=self._ai_steps,
                warnings=self._preparation_warnings,
            )
            if not self.preparation_result.ready_for_review:
                raise PimAutomationError(self.preparation_result.error)
            self.failed_stage = ""

            # Calculate duration
            duration = time.time() - self.start_time

            # Record the reviewable (not saved) result in database.
            self._record_success(duration)


            # Generated files are kept until the human Save is confirmed.
            self._log("Product ready for manual review", duration=f"{duration:.2f}s")
            ErrorManager.show_success(
                f"{self.ultraBikeCode} paruoštas peržiūrai — išsaugokite PIMBO lange."
            )
            return self.preparation_result

        except Exception as e:
            duration = time.time() - self.start_time if self.start_time else 0
            self.preparation_result = PimPreparationResult(
                product_code=self.ultraBikeCode or "",
                product_id=self.preparation_result.product_id,
                initial_version=getattr(self.preparation_result, "initial_version", None),
                initial_fields=self.preparation_result.initial_fields,
                status=PimPreparationStatus.FAILED,
                changed_fields=tuple(self._changed_fields),
                ai_steps=tuple(self._ai_steps),
                warnings=tuple(self._preparation_warnings),
                final_url=getattr(self.driver, "current_url", ""),
                failed_stage=str(getattr(self, "failed_stage", "") or ""),
                error=str(e),
                photo_upload=dict(getattr(self.pim_editor, "photo_upload", {}) or {}),
            )
            try:
                self._record_failure(str(e), duration)
            except Exception as history_error:
                self.preparation_result = replace(self.preparation_result,
                    warnings=self.preparation_result.warnings + (f"History could not be recorded: {history_error}",))
            self._log_error("Upload process failed", exception=e, code=self.ultraBikeCode)
            ErrorManager.show_error("UNEXPECTED_ERROR", error=str(e))
            return self.preparation_result

    @with_database_lock
    def _record_success(self, duration):
        """Record a prepared-for-review result (never an automatic save)."""
        cursor = self.db.conn.cursor()
        details_json = getattr(self, "_details_json", None)
        failed_stage = getattr(self, "failed_stage", None)
        status = self.preparation_result.status.value

        # Enrich details_json with workflow metadata (safe best-effort)
        workflow = "batch_upload" if self.batch_id else "regular_upload"
        try:
            details = {}
            if details_json:
                details = json.loads(details_json) or {}
            details.setdefault("workflow", workflow)
            details["pim_preparation"] = self.preparation_result.to_dict()
            if self.batch_id:
                details.setdefault("batch_id", self.batch_id)
            details_json = json.dumps(details, ensure_ascii=False)
        except Exception:
            pass
        cursor.execute("""
            INSERT INTO processing_history
            (brand, product_code, url_or_code, status, duration_seconds,
             features_uploaded, images_uploaded, failed_stage, batch_id, details_json, processed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            self.brandName,
            self.ultraBikeCode,
            self.bicycleUrlOrCode,
            status,
            duration,
            self.features_uploaded,
            self.images_uploaded,
            failed_stage,
            self.batch_id,
            details_json,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ))
        self.preparation_result = replace(self.preparation_result, history_id=cursor.lastrowid)
        self.db.conn.commit()
        self._log("Preparation result recorded in database", status=status)

    def _record_preparation(self, duration):
        self._record_success(duration)

    @with_database_lock
    def _record_failure(self, error_message, duration):
        """Record failed upload to database"""
        cursor = self.db.conn.cursor()
        details_json = getattr(self, "_details_json", None)
        failed_stage = getattr(self, "failed_stage", None)

        workflow = "batch_upload" if self.batch_id else "regular_upload"
        try:
            details = {}
            if details_json:
                details = json.loads(details_json) or {}
            details.setdefault("workflow", workflow)
            details["pim_preparation"] = self.preparation_result.to_dict()
            if self.batch_id:
                details.setdefault("batch_id", self.batch_id)
            details_json = json.dumps(details, ensure_ascii=False)
        except Exception:
            pass
        cursor.execute("""
            INSERT INTO processing_history
            (brand, product_code, url_or_code, status, error_message,
             duration_seconds, failed_stage, batch_id, details_json, processed_at)
            VALUES (?, ?, ?, 'failed', ?, ?, ?, ?, ?, ?)
        """, (
            self.brandName,
            self.ultraBikeCode,
            self.bicycleUrlOrCode,
            error_message,
            duration,
            failed_stage,
            self.batch_id,
            details_json,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ))
        self.preparation_result = replace(self.preparation_result, history_id=cursor.lastrowid)
        self.db.conn.commit()
        self._log("Failure recorded in database")


    @abstractmethod
    def scrape(self):
        """Each brand implements its own scraping logic"""
        pass

    def translate(self):
        """Translate scraped data to English"""
        self._log("Starting translation")
        try:
            self.translationManager.translateAll()
            self._log("Translation completed")
        except Exception as e:
            self._log_error("Translation failed", exception=e)
            ErrorManager.show_error("TRANSLATION_FAILED")
            raise

    def openProduct(self):
        """Navigate to product in admin panel"""
        self._log("Opening product", code=self.ultraBikeCode)
        try:
            self.pim_editor = self.navigation_manager.navigate_to_product(
                self.brandName,
                self.ultraBikeCode,
            )
            get_title_template = getattr(
                self.settings_manager,
                "get_magicai_title_template",
                lambda: self.settings_manager.get(
                    "magicai_title_template", "Prekės pavadinimas"
                ),
            )
            get_description_template = getattr(
                self.settings_manager,
                "get_magicai_description_template",
                lambda: self.settings_manager.get(
                    "magicai_description_template", "Aprašymas LT"
                ),
            )
            self.pim_editor.title_template = str(get_title_template()).strip()
            self.pim_editor.description_template = str(
                get_description_template()
            ).strip()
            self._log("Product opened successfully")
        except Exception as e:
            self._log_error("Failed to open product", exception=e, code=self.ultraBikeCode)
            ErrorManager.show_error("UPLOAD_PRODUCT_NOT_FOUND", code=self.ultraBikeCode)
            raise

    def uploadImages(self):
        self._log("Uploading images")
        try:
            if self.brandName.upper() != "KROSS":
                self._log("Image upload not implemented for brand", brand=self.brandName)
                ErrorManager.show_warning(
                    f"Nuotraukų siuntimas nėra sukurtas {self.brandName}"
                )
                raise PimAutomationError(f"Image upload is not supported for {self.brandName}; disable it or use the supplier workflow")
            image_paths = self.image_handler.download_kross_images(
                self.bicycleUrlOrCode,
                self.ultraBikeCode,
            )
            prepared = self._run_stage("images_upload", self.pim_editor.upload_product_images,
                image_paths,
                skip_if_present=True,
            )
            if prepared:
                self.images_uploaded = prepared
                self._changed_fields.append("images")
            self._log("Images uploaded successfully")
            ErrorManager.show_success("Nuotraukos sėkmingai įkeltos!")
        except Exception as e:
            self._log_error("Image upload failed", exception=e)
            ErrorManager.show_error("UPLOAD_IMAGE_FAILED")
            raise

    def _prepare_description(self):
        append_disclaimer = self.brand_options.get("append_disclaimer", False)
        if self.description_name:
            descriptions = self.description_manager.prepare_description(
                self.description_name, append_disclaimer=append_disclaimer, only_lt=True,
            )
            if not descriptions or not str(descriptions.get("lt") or "").strip():
                raise PimAutomationError(f"Selected description {self.description_name!r} is missing or empty")
        elif append_disclaimer:
            descriptions = self.description_manager.prepare_raw_description(
                "", "", "", append_disclaimer=True, only_lt=True,
            )
            if not descriptions or not str(descriptions.get("lt") or "").strip():
                raise PimAutomationError("Requested disclaimer is missing or empty")
        else:
            descriptions = None
        self._prepared_descriptions = descriptions
        return descriptions

    def uploadDescription(self):
        """Upload product description if provided."""

        append_disclaimer = self.brand_options.get('append_disclaimer', False)

        if not self.description_name:
            if append_disclaimer:
                self._log("No description selected, but disclaimer requested - uploading standalone disclaimer")
                try:
                    descriptions = self.description_manager.prepare_raw_description(
                        '', '', '',
                        append_disclaimer=True,
                        only_lt=True,
                    )
                    changed = self.pim_editor.set_localized_descriptions(descriptions)
                    if changed:
                        self._changed_fields.extend(
                            f"description_{locale}" for locale in changed
                        )
                        self._log("Standalone disclaimer uploaded successfully")
                        ErrorManager.show_success("Disclaimer įkeltas!")
                    else:
                        self._log("Standalone disclaimer already present")
                except Exception as e:
                    self._log_error("Standalone disclaimer upload failed", exception=e)
                    ErrorManager.show_warning(f"Disclaimer įkėlimo klaida: {str(e)}")
                    raise
                return

            self._log("No description to upload")
            return

        self._log("Uploading description", name=self.description_name, append_disclaimer=append_disclaimer)

        try:
            descriptions = getattr(self, "_prepared_descriptions", None)
            if descriptions is None:
                descriptions = self._prepare_description()
            if descriptions is None:
                self._log_error("Description was not found")
                ErrorManager.show_warning(f"Nepavyko įkelti aprašymo '{self.description_name}'")
                raise PimAutomationError(f"Selected description {self.description_name!r} could not be loaded")
            changed = self.pim_editor.set_localized_descriptions(descriptions)
            if changed:
                self._changed_fields.extend(
                    f"description_{locale}" for locale in changed
                )
                self._log("Description uploaded successfully")
                if append_disclaimer:
                    ErrorManager.show_success(f"Aprašymas '{self.description_name}' su disclaimer įkeltas!")
                else:
                    ErrorManager.show_success(f"Aprašymas '{self.description_name}' įkeltas!")
            else:
                self._log("Description already matched the selected template")

        except Exception as e:
            self._log_error("Description upload failed", exception=e)
            ErrorManager.show_warning(f"Aprašymo įkėlimo klaida: {str(e)}")
            raise


    def uploadFeatures(self):
        """Upload product specifications (LT + EN)."""
        self._log("Uploading features")
        try:
            ltData = self.translationManager.loadLT()

            self.features_uploaded = 0
            self._log("LT feature data loaded", lt_count=len(ltData))

            skipped, filled_count = self._set_specifications(ltData)
            self.features_uploaded = filled_count
            if filled_count:
                self._changed_fields.append("specifications")
            if skipped:
                details = {}
                if getattr(self, "_details_json", None):
                    try:
                        details = json.loads(self._details_json) or {}
                    except Exception:
                        details = {}
                details["skipped_features"] = skipped
                self._details_json = json.dumps(details, ensure_ascii=False)
                self._preparation_warnings.extend(
                    f"Specification {item.get('key')}: {item.get('reason')}"
                    for item in skipped
                )
                raise PimAutomationError("Required specifications were not found in PIMBO: " + ", ".join(item["key"] for item in skipped))

            self._log("Features uploaded successfully", count=self.features_uploaded)
        except Exception as e:
            self._log_error("Feature upload failed", exception=e)
            ErrorManager.show_error("UPLOAD_FEATURE_FAILED", feature="multiple")
            raise

    def _set_specifications(self, tables):
        """Fill existing Family specification rows through the current editor."""

        skipped = []
        filled_count = 0
        self.pim_editor.switch_locale("lt")
        self.pim_editor.open_section("specifications")
        for table in tables or []:
            for name, value in (table or {}).items():
                if self._stop_requested.is_set():
                    raise PimAutomationError("Upload stopped during specifications; review unsaved changes")
                if value in (None, ""):
                    continue
                changed = self.pim_editor.set_specification(
                    str(name),
                    str(value),
                    overwrite=True,
                )
                if changed is None:
                    skipped.append({"key": str(name), "reason": "not_found"})
                elif changed:
                    filled_count += 1
                    self.features_uploaded = filled_count
                    if "specifications" not in self._changed_fields:
                        self._changed_fields.append("specifications")
        return skipped, filled_count

    def _build_magic_source_text(self):
        """Build the unstructured source passed to specification MagicAI."""
        raw_source = str(getattr(self, "_magicai_source_text", "") or "").strip()
        parts = [raw_source] if raw_source else []
        if not raw_source:
            tables = self.translationManager.loadLT()
            for table in tables:
                for key, value in table.items():
                    parts.append(f"{key}: {value}")
        if not parts:
            raise PimAutomationError("Fresh supplier specifications are required before running MagicAI")
        if self.bicycleUrlOrCode:
            parts.append(f"Supplier source: {self.bicycleUrlOrCode}")
        source_text = "\n".join(str(part) for part in parts if str(part).strip())
        try:
            details = json.loads(getattr(self, "_details_json", "") or "{}") or {}
            details["magicai_specification_source"] = source_text
            self._details_json = json.dumps(details, ensure_ascii=False)
        except Exception:
            pass
        return source_text

    def runMagicAi(self):
        """Run all current product-page AI actions and leave them unsaved."""
        source_text = self._build_magic_source_text()
        actions = (
            ("pavadinimas", self.pim_editor.generate_product_name),
            ("aprašymas", self.pim_editor.generate_description),
            ("kategorija", self.pim_editor.suggest_category),
            (
                "specifikacijos",
                lambda: self.pim_editor.fill_empty_specifications_with_ai(source_text),
            ),
            ("vertimai LT → EN/LV/EE", self.pim_editor.translate_lt_to_all),
        )
        for stage, action in actions:
            self._progress(f"MagicAI: {stage}")
            try:
                step = self._run_stage(f"magicai_{stage}", action)
                if not isinstance(step, PimAiStepResult) or not step.success:
                    raise PimAutomationError(getattr(step, "detail", "") or f"MagicAI {stage} did not complete")
            except Exception as error:
                self.failed_stage = f"magicai_{stage}"
                self._ai_steps.append(
                    PimAiStepResult(
                        step=stage,
                        success=False,
                        changed=False,
                        attempts=2,
                        detail=str(error),
                    )
                )
                raise PimAutomationError(f"MagicAI etapas „{stage}“ nepavyko: {error}") from error
            self._ai_steps.append(step)
            if step.changed:
                self._changed_fields.append(step.step)
            if step.detail and not step.changed:
                self._preparation_warnings.append(step.detail)
        self.pim_editor.switch_locale("lt")
        return tuple(self._ai_steps)

    def collectVariantSizes(self):
        """Switch to Variants tab and collect all variant sizes (stored on self)."""
        self._collected_variant_sizes = None
        self._log("Collecting variant sizes")
        try:
            sizes = self.pim_editor.collect_variant_sizes()
            if sizes:
                sizes = self._sort_sizes(sizes)
                self._collected_variant_sizes = ", ".join(sizes)
                self._log("Variant sizes collected", sizes=self._collected_variant_sizes)
            else:
                self._log("No variant sizes found")

        except Exception as e:
            self._log_error("Failed to collect variant sizes", exception=e)
            raise

    def fillVariantSizesIntoSpecs(self):
        """Fill previously collected variant sizes into the 'Galimi rėmo dydžiai' spec field.

        Must be called while on the Specifications tab.
        """
        sizes_str = getattr(self, '_collected_variant_sizes', None)
        if not sizes_str:
            return

        self._log("Filling variant sizes into specs", value=sizes_str)
        try:
            changed = self.pim_editor.set_specification(
                "Galimi rėmo dydžiai",
                sizes_str,
                overwrite=True,
            )
            if changed is None:
                raise PimAutomationError("Specification 'Galimi rėmo dydžiai' was not found")
            elif changed:
                self._changed_fields.append("specification:Galimi rėmo dydžiai")
                self._log("Variant sizes filled", value=sizes_str)
        except Exception:
            raise

    @staticmethod
    def _sort_sizes(sizes):
        """Sort variant sizes: standard clothing sizes in order, numbers low-to-high, alpha fallback."""
        SIZE_ORDER = {
            'XXS': 0, '2XS': 0,
            'XS': 1,
            'S': 2,
            'M': 3,
            'L': 4,
            'XL': 5,
            'XXL': 6, '2XL': 6,
            'XXXL': 7, '3XL': 7,
            '4XL': 8, '5XL': 9,
        }

        def sort_key(size):
            upper = size.strip().upper()
            # Check standard clothing sizes
            if upper in SIZE_ORDER:
                return (0, SIZE_ORDER[upper], '')
            # Try numeric (int or float, e.g. "52", "27.5")
            try:
                return (1, float(size.strip()), '')
            except ValueError:
                pass
            # Alphabetical fallback
            return (2, 0, size.strip().lower())

        return sorted(sizes, key=sort_key)

    def extractWheelSizeFromTitle(self):
        """Extract wheel size (e.g. 28") from the product name and add to attributes."""
        self._log("Extracting wheel size from product title")
        try:
            title = self.pim_editor.product_name()

            if not title:
                self._log("Product name is empty, skipping wheel size extraction")
                return

            # Match a number (int or decimal) followed by " (inch mark: &quot; or literal ")
            match = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:"|&quot;|″)', title)
            if not match:
                self._log("No wheel size found in title", title=title)
                return

            wheel_size = match.group(1).replace(',', '.')
            # Normalize: drop .0 for whole numbers
            try:
                num = float(wheel_size)
                wheel_size = str(int(num)) if num == int(num) else str(num)
            except ValueError:
                pass

            wheel_value = f'{wheel_size}"'
            self._log("Wheel size extracted from title", wheel_size=wheel_value, title=title)

            # Inject into attribute_values so uploadAttributes() picks it up
            attr_values = self.brand_options.setdefault('attribute_values', [])
            # Don't duplicate if already set
            if not any(a.get('name') == 'Ratų dydis' for a in attr_values):
                attr_values.append({
                    'name': 'Ratų dydis',
                    'value': wheel_value,
                    'field': 'options',
                })
                self._log("Wheel size added to attributes", value=wheel_value)
            else:
                self._log("Ratų dydis already in attributes, skipping")

        except Exception as e:
            self._log_error("Failed to extract wheel size from title", exception=e)

    def extractKomplektacijaFromSpecs(self):
        """Read 'Pavarų sistema > Grupė' spec value and upload as 'Komplektacija' attribute.

        Must be called while on the Specifications tab (after uploadFeatures).
        Navigates to Attributes tab to fill the value, only if the user didn't
        already set Komplektacija from the GUI.
        """
        # Skip if user already set Komplektacija via the GUI
        attr_values = self.brand_options.get('attribute_values', [])
        if any(a.get('name') == 'Komplektacija' for a in attr_values):
            self._log("Komplektacija already set by user, skipping auto-fill")
            return

        self._log("Extracting Komplektacija from specs")
        try:
            # Do not derive attributes from an old PIMBO value left by a prior job.
            value = next((str(table["Grupė"]) for table in self.translationManager.loadLT()
                          if table.get("Grupė")), "")
            if not value:
                self._log("Grupė spec field is empty, skipping Komplektacija")
                return

            self._log("Komplektacija extracted, uploading attribute", value=value)
            skipped, changed_count = self._set_attributes(
                [{
                    'name': 'Komplektacija',
                    'value': value,
                    'field': 'options',
                }]
            )
            if changed_count:
                self._changed_fields.append("attribute:Komplektacija")
            if skipped:
                self._preparation_warnings.append(
                    "Attribute Komplektacija was not available in the current Family schema"
                )
                raise PimAutomationError("Supplier groupset could not be applied to Komplektacija")

        except Exception as e:
            self._log_error("Failed to extract Komplektacija", exception=e)
            raise

    def uploadBrand(self):
        """Set the uploader's brand through the current PIMBO editor."""
        return self.pim_editor.set_brand(self.brandName)

    def _set_attributes(self, attribute_values):
        """Update only existing Product Family attributes."""

        skipped = []
        changed_count = 0
        self.pim_editor.open_section("attributes")
        for attribute in attribute_values or []:
            if self._stop_requested.is_set():
                raise PimAutomationError("Upload stopped during attributes; review unsaved changes")
            name = str(attribute.get("name") or "").strip()
            value = str(attribute.get("value") or "").strip()
            if not name or not value:
                raise PimAutomationError("A selected attribute has an empty name or value")
            try:
                changed = self.pim_editor.set_attribute(name, value)
                if changed is None:
                    skipped.append({"key": name, "reason": "not_found"})
                elif changed:
                    changed_count += 1
            except Exception as error:
                skipped.append({"key": name, "reason": "option_not_found"})
                self._log(
                    "Attribute was not changed",
                    name=name,
                    error=str(error),
                )
        return skipped, changed_count

    def uploadAttributes(self):
        """Upload product-level attributes."""
        attribute_values = self.brand_options.get('attribute_values', [])

        if not attribute_values:
            self._log("No attributes to upload, skipping")
            return

        self._log("Uploading attributes", count=len(attribute_values))
        try:
            skipped, changed_count = self._set_attributes(attribute_values)
            if changed_count:
                self._changed_fields.append("attributes")
            if skipped:
                details = {}
                if getattr(self, "_details_json", None):
                    try:
                        details = json.loads(self._details_json) or {}
                    except Exception:
                        details = {}
                details["skipped_attributes"] = skipped
                self._details_json = json.dumps(details, ensure_ascii=False)
                self._preparation_warnings.extend(
                    f"Attribute {item.get('key')}: {item.get('reason')}"
                    for item in skipped
                )
                raise PimAutomationError("Selected attributes could not be applied: " + ", ".join(item["key"] for item in skipped))
            self._log("Attributes uploaded", skipped=len(skipped))
        except Exception as e:
            self._log_error("Attribute upload failed", exception=e)
            self._preparation_warnings.append(f"Attribute preparation failed: {e}")
            raise

    def __del__(self):
        """Cleanup database connection if we own it"""
        if hasattr(self, 'own_db') and self.own_db and hasattr(self, 'db'):
            self.db.close()

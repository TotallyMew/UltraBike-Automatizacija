# Standard library
import json
import time
from abc import ABC, abstractmethod
from datetime import datetime

# Local application imports
from Database.DatabaseManager import DatabaseManager
from Database.SessionManager import SessionManager
from Database.SettingsManager import SettingsManager
from Managers.DescriptionManager import DescriptionManager
from Managers.FeatureUploader.FeatureUploader import FeatureUploader
from Managers.ImageUploader import ImageUploader
from Managers.TranslationManager import TranslationManager
from Utilities.ErrorManager import ErrorManager
from Utilities.ProductNavigationHandler import ProductNavigationHandler
from Utilities.TranslationHandler import TranslationHandler
from Utilities.URLHandler import URLHandler
from Utilities.WebIntercationHandler import WebInteractionHandler

class ProductUploader(ABC):
    def set_retry_callback(self, callback):
        # Set callback for navigation manager and any other retry points
        if hasattr(self, 'navigation_manager') and self.navigation_manager:
            self.navigation_manager.set_retry_callback(callback)
        self._retry_callback = callback

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
        self.brand_options = brand_options or {}
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
        self.url_handler = URLHandler()
        self.web_handler = WebInteractionHandler(self.driver)
        self.translation_handler = TranslationHandler()

        # Database setup
        if db_manager:
            self.db = db_manager
        else:
            self.db = DatabaseManager()

        # Settings manager
        try:
            self.session_manager = SessionManager(self.db)
            self.settings_manager = SettingsManager(self.db)
        except Exception as e:
            ErrorManager.show_error("UNEXPECTED_ERROR", error=str(e))
            self.session_manager = SessionManager(self.db)
            self.settings_manager = SettingsManager(self.db)

        # Optional PrestaShop API client (configured via Settings)
        self.prestashop_api = None
        try:
            if bool(self.settings_manager.get('prestashop_api_enabled', False)):
                base_url = (self.settings_manager.get('prestashop_url', '') or '').strip()
                api_key = (self.settings_manager.get('prestashop_api_key', '') or '').strip()
                if base_url and api_key:
                    from Managers.PrestaShopAPI import PrestaShopAPI
                    self.prestashop_api = PrestaShopAPI(base_url, api_key, logger=self.logger)
        except Exception as e:
            self._log_error("Failed to initialize PrestaShop API client", exception=e)

        self.translationManager = TranslationManager(self.brandName, self.db, self.logger)
        self.imageUploader = ImageUploader(self.driver, self.brandName, self.logger, settings_manager=self.settings_manager)
        self.featureUploader = FeatureUploader(self.driver, self.logger)

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

    def run(self):
        """Main execution flow with database tracking"""
        self._log("Starting upload process", code=self.ultraBikeCode)
        self.start_time = time.time()

        try:
            # Main upload workflow
            self.scrape()
            self.translate()
            self.openProduct()

            # Optional image upload
            if self.settings_manager.download_pictures_and_upload():
                self.uploadImages()
                self.images_uploaded = True

            # Debug: about to call uploadDescription()

            # Upload description (if provided)
            self.uploadDescription()

            # Debug: uploadDescription() completed

            # Upload features
            self.uploadFeatures()

            # Upload brand
            self.uploadBrand()

            # Auto-save if enabled in settings
            if self.settings_manager.is_auto_save_enabled():
                self.saveUpdate()
            else:
                self._log("Auto-save disabled, skipping saveUpdate()")

            # Calculate duration
            duration = time.time() - self.start_time

            # Record success in database
            self._record_success(duration)

            # Add to recent products cache
            self._cache_recent_product()

            # Optional cleanup: delete generated pabaigta*.txt files
            try:
                if self.settings_manager.is_auto_delete_pabaigta_files_enabled():
                    self.translationManager.cleanup_generated_files()
            except Exception as e:
                # Cleanup must never turn a success into a failure
                self._log_error("Auto-delete pabaigta files failed", exception=e)

            self._log("Upload process completed successfully", duration=f"{duration:.2f}s")
            ErrorManager.show_success(f"Dviratis {self.ultraBikeCode} sėkmingai apdorotas!")

        except Exception as e:
            duration = time.time() - self.start_time if self.start_time else 0
            self._record_failure(str(e), duration)
            self._log_error("Upload process failed", exception=e, code=self.ultraBikeCode)
            ErrorManager.show_error("UNEXPECTED_ERROR", error=str(e))
            raise

    def _record_success(self, duration):
        """Record successful upload to database"""
        cursor = self.db.conn.cursor()
        details_json = getattr(self, "_details_json", None)
        failed_stage = getattr(self, "failed_stage", None)

        # Enrich details_json with workflow metadata (safe best-effort)
        workflow = "batch_upload" if self.batch_id else "regular_upload"
        try:
            details = {}
            if details_json:
                details = json.loads(details_json) or {}
            details.setdefault("workflow", workflow)
            if self.batch_id:
                details.setdefault("batch_id", self.batch_id)
            details_json = json.dumps(details, ensure_ascii=False)
        except Exception:
            pass
        cursor.execute("""
            INSERT INTO processing_history
            (brand, product_code, url_or_code, status, duration_seconds,
             features_uploaded, images_uploaded, failed_stage, batch_id, details_json, processed_at)
            VALUES (?, ?, ?, 'success', ?, ?, ?, ?, ?, ?, ?)
        """, (
            self.brandName,
            self.ultraBikeCode,
            self.bicycleUrlOrCode,
            duration,
            self.features_uploaded,
            self.images_uploaded,
            failed_stage,
            self.batch_id,
            details_json,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ))
        self.db.conn.commit()
        self._log("Success recorded in database")

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
        self.db.conn.commit()
        self._log("Failure recorded in database")

    def _cache_recent_product(self):
        """Add product to recent products cache"""
        cursor = self.db.conn.cursor()

        # Check if already exists
        existing = cursor.execute("""
            SELECT id, use_count FROM recent_products 
            WHERE brand = ? AND product_code = ?
        """, (self.brandName, self.ultraBikeCode)).fetchone()

        if existing:
            # Update existing
            cursor.execute("""
                UPDATE recent_products
                SET last_used = ?,
                    use_count = ?,
                    url_or_code = ?
                WHERE id = ?
            """, (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), existing['use_count'] + 1, self.bicycleUrlOrCode, existing['id']))
        else:
            # Insert new
            cursor.execute("""
                INSERT INTO recent_products
                (brand, product_code, url_or_code, last_used, use_count)
                VALUES (?, ?, ?, ?, 1)
            """, (self.brandName, self.ultraBikeCode, self.bicycleUrlOrCode, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

        self.db.conn.commit()

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
        """Navigate to product in PrestaShop"""
        self._log("Opening product", code=self.ultraBikeCode)
        try:
            self.navigation_manager.navigate_to_product(self.brandName, self.ultraBikeCode)
            self._log("Product opened successfully")
        except Exception as e:
            self._log_error("Failed to open product", exception=e, code=self.ultraBikeCode)
            ErrorManager.show_error("UPLOAD_PRODUCT_NOT_FOUND", code=self.ultraBikeCode)
            raise

    def uploadImages(self):
        self._log("Uploading images")
        try:
            # Get image count before upload
            import os
            from Utilities.FileHandler import FileHandler
        
            # Construct download path (same logic as ImageHandler)
            base_directory = self.settings_manager.get_kross_path()
            sanitized_name = FileHandler.sanitize_filename(self.ultraBikeCode)
            download_directory = os.path.join(base_directory, sanitized_name)
        
            # Count images if directory exists
            if os.path.exists(download_directory):
                self.images_uploaded = len([f for f in os.listdir(download_directory) 
                                            if f.lower().endswith(('.jpg', '.jpeg', '.png'))])

        
            self.imageUploader.uploadAll(self.bicycleUrlOrCode)
            self._log("Images uploaded successfully")
            ErrorManager.show_success("Nuotraukos sėkmingai įkeltos!")
        except Exception as e:
            self._log_error("Image upload failed", exception=e)
            ErrorManager.show_error("UPLOAD_IMAGE_FAILED")
            # Don't raise - continue without images

    def uploadDescription(self):
        """Upload product description if provided, or standalone disclaimer if checked"""
        # Debug: uploadDescription called, description_name = {self.description_name}

        # Get append_disclaimer flag from brand_options
        append_disclaimer = self.brand_options.get('append_disclaimer', False)
        append_order_note = self.brand_options.get('append_order_note', False)

        # If no description template selected, we can still run independent addons.
        if not self.description_name:
            did_anything = False

            if append_disclaimer:
                self._log("No description selected, but disclaimer requested - uploading standalone disclaimer")
                try:
                    success = self.description_manager.upload_to_prestashop_raw(
                        self.driver,
                        self.ultraBikeCode,
                        '',  # Empty LT content
                        '',  # Empty EN content
                        '',  # Empty LV content
                        append_disclaimer=True
                    )
                    did_anything = True

                    if success:
                        self._log("Standalone disclaimer uploaded successfully")
                        ErrorManager.show_success("Disclaimer įkeltas!")
                    else:
                        self._log_error("Standalone disclaimer upload returned False")
                        ErrorManager.show_warning("Nepavyko įkelti disclaimer")
                except Exception as e:
                    self._log_error("Standalone disclaimer upload failed", exception=e)
                    ErrorManager.show_warning(f"Disclaimer įkėlimo klaida: {str(e)}")

            if append_order_note:
                self._log("No description selected, but order note requested - appending to short description")
                try:
                    ok = self.description_manager.append_order_note_to_short_description(
                        self.driver,
                        product_code=self.ultraBikeCode,
                    )
                    did_anything = True
                    if ok:
                        ErrorManager.show_success("Užsakymo pastaba įkelta!")
                    else:
                        ErrorManager.show_warning("Nepavyko įkelti užsakymo pastabos")
                except Exception as e:
                    self._log_error("Order note upload failed", exception=e)
                    ErrorManager.show_warning(f"Užsakymo pastabos įkėlimo klaida: {str(e)}")

            if did_anything:
                return

        # If no description and no disclaimer, skip
        if not self.description_name:
            self._log("No description to upload")
            # Debug: No description name provided, skipping
            return

        # Upload description with optional disclaimer
        # Debug: Attempting to upload description: {self.description_name}, append_disclaimer={append_disclaimer}
        self._log("Uploading description", name=self.description_name, append_disclaimer=append_disclaimer)

        # Prefer API for description updates when enabled; fall back to browser automation on failure.
        if self.prestashop_api is not None:
            try:
                desc = self.description_manager.load_description(self.description_name)
                if desc:
                    lt_html = desc.get('description_lt', '') or ''
                    en_html = desc.get('description_en', '') or ''
                    lv_html = desc.get('description_lv', '') or ''
                    if append_disclaimer:
                        lt_html, en_html, lv_html = self.description_manager.append_disclaimer_if_missing(
                            lt_html, en_html, lv_html
                        )

                    lang_map = self.prestashop_api.get_language_id_map() or {}
                    en_id = str(lang_map.get('en') or '1')
                    lt_id = str(lang_map.get('lt') or '2')
                    lv_id = str(lang_map.get('lv') or '3')

                    payload = {}
                    if lt_html and lt_id:
                        payload[lt_id] = lt_html
                    if en_html and en_id:
                        payload[en_id] = en_html
                    if lv_html and lv_id:
                        payload[lv_id] = lv_html

                    if payload:
                        product_id = self.prestashop_api.search_product_by_reference(self.ultraBikeCode)
                        if product_id:
                            self._log("Updating description via API", code=self.ultraBikeCode)
                            ok_api = self.prestashop_api.update_product_description(int(product_id), payload)
                            if ok_api:
                                self._log("Description updated via API", code=self.ultraBikeCode)
                                ErrorManager.show_success(f"Aprašymas '{self.description_name}' įkeltas per API!")

                                # Order note still uses browser automation (short description), best-effort.
                                if append_order_note:
                                    try:
                                        self._log("Appending order note to short description", code=self.ultraBikeCode)
                                        ok_note = self.description_manager.append_order_note_to_short_description(
                                            self.driver,
                                            product_code=self.ultraBikeCode,
                                        )
                                        if ok_note:
                                            ErrorManager.show_success("Užsakymo pastaba įkelta!")
                                        else:
                                            ErrorManager.show_warning("Nepavyko įkelti užsakymo pastabos")
                                    except Exception as e:
                                        self._log_error("Order note upload failed", exception=e)
                                        ErrorManager.show_warning(f"Užsakymo pastabos įkėlimo klaida: {str(e)}")
                                return
                            else:
                                extra = (self.prestashop_api.last_error_summary() or '').strip()
                                self._log_error("API description update failed; falling back to browser", exception=None, error=extra)
                        else:
                            extra = (self.prestashop_api.last_error_summary() or '').strip()
                            self._log_error("Product not found via API; falling back to browser", exception=None, error=extra)
            except Exception as e:
                self._log_error("API description update crashed; falling back to browser", exception=e)

        try:
            success = self.description_manager.upload_to_prestashop(
                self.driver,
                self.ultraBikeCode,
                self.description_name,
                append_disclaimer=append_disclaimer
            )

            # Debug: upload_to_prestashop returned: {success}

            if success:
                self._log("Description uploaded successfully")
                if append_disclaimer:
                    ErrorManager.show_success(f"Aprašymas '{self.description_name}' su disclaimer įkeltas!")
                else:
                    ErrorManager.show_success(f"Aprašymas '{self.description_name}' įkeltas!")

                if append_order_note:
                    try:
                        self._log("Appending order note to short description", code=self.ultraBikeCode)
                        ok_note = self.description_manager.append_order_note_to_short_description(
                            self.driver,
                            product_code=self.ultraBikeCode,
                        )
                        if ok_note:
                            ErrorManager.show_success("Užsakymo pastaba įkelta!")
                        else:
                            ErrorManager.show_warning("Nepavyko įkelti užsakymo pastabos")
                    except Exception as e:
                        self._log_error("Order note upload failed", exception=e)
                        ErrorManager.show_warning(f"Užsakymo pastabos įkėlimo klaida: {str(e)}")
            else:
                self._log_error("Description upload returned False")
                ErrorManager.show_warning(f"Nepavyko įkelti aprašymo '{self.description_name}'")

        except Exception as e:
            import traceback
            # Debug: Exception in uploadDescription
            self._log_error("Description upload failed", exception=e)
            ErrorManager.show_warning(f"Aprašymo įkėlimo klaida: {str(e)}")


    def uploadFeatures(self):
        """Upload product features in all languages"""
        self._log("Uploading features")
        try:
            ltData = self.translationManager.loadLT()
            enData = self.translationManager.loadEN()
            lvData = self.translationManager.loadLV()
            
            # Count features
            self.features_uploaded = sum(len(table) for table in ltData)
            
            self._log("Feature data loaded", lt_count=len(ltData), en_count=len(enData))

            # Prefer API for feature associations when enabled; fall back to browser automation on failure.
            if self.prestashop_api is not None:
                try:
                    from Managers.PrestaShopFeatureSync import apply_features_from_tables

                    self._log("Uploading features via API", code=self.ultraBikeCode)
                    result = apply_features_from_tables(
                        self.prestashop_api,
                        product_reference=self.ultraBikeCode,
                        lt_tables=ltData,
                        en_tables=enData,
                        lv_tables=lvData,
                        logger=self.logger,
                    )
                    if result and result.get('ok'):
                        ErrorManager.show_success("Features įkelti per API!")
                        return

                    msg = (result or {}).get('message') or (self.prestashop_api.last_error_summary() or '')
                    self._log_error("API feature upload failed; falling back to browser", exception=None, error=str(msg))
                except Exception as e:
                    self._log_error("API feature upload crashed; falling back to browser", exception=e)

            skipped = self.featureUploader.uploadAllLanguages(ltData, enData, lvData)
            try:
                if skipped:
                    import json
                    details = {}
                    if getattr(self, "_details_json", None):
                        try:
                            details = json.loads(self._details_json) or {}
                        except Exception:
                            details = {}
                    details["skipped_features"] = skipped
                    self._details_json = json.dumps(details, ensure_ascii=False)
            except Exception as e:
                self._log_error("Failed to store skipped feature details", exception=e)
            self._log("Features uploaded successfully", count=self.features_uploaded)
        except Exception as e:
            self._log_error("Feature upload failed", exception=e)
            ErrorManager.show_error("UPLOAD_FEATURE_FAILED", feature="multiple")
            raise

    def uploadBrand(self):
        """Add brand name to product (implemented by child classes if needed)"""
        pass

    def saveUpdate(self):
        """Save product changes in PrestaShop"""
        self._log("Saving updates")
        try:
            self.web_handler.save_information()
            self._log("Updates saved successfully")
        except Exception as e:
            self._log_error("Save failed", exception=e)
            ErrorManager.show_error("UPLOAD_SAVE_FAILED")
            raise
    
    def __del__(self):
        """Cleanup database connection if we own it"""
        if hasattr(self, 'own_db') and self.own_db and hasattr(self, 'db'):
            self.db.close()
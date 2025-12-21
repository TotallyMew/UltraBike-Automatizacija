from abc import ABC, abstractmethod
import time
from datetime import datetime
from Database.DatabaseManager import DatabaseManager
from Database.SessionManager import SessionManager
from Database.SettingsManager import SettingsManager
from Managers.translationManager import TranslationManager
from Managers.imageUploader import ImageUploader
from Managers.FeatureUploader.featureUploader import FeatureUploader
from Managers.DescriptionManager import DescriptionManager
from Utilities.ProductNavigationHandler import ProductNavigationHandler
from Utilities.URLHandler import URLHandler
from Utilities.TranslationHandler import TranslationHandler
from Utilities.WebIntercationHandler import WebInteractionHandler
from Utilities.ErrorManager import ErrorManager

class ProductUploader(ABC):
    def set_retry_callback(self, callback):
        # Set callback for navigation manager and any other retry points
        if hasattr(self, 'navigation_manager') and self.navigation_manager:
            self.navigation_manager.set_retry_callback(callback)
        self._retry_callback = callback

    def __init__(self, *args, **kwargs):
        """Flexible initializer.

        Legacy positional signature is still accepted for compatibility:
            (driver, brandName, ultraBikeCode=None, bicycleUrlOrCode=None, ...)

        Preferred GUI style uses keyword args:
            driver=..., db=..., product_code=..., url_or_code=..., ...
        """

        # Detect legacy positional usage
        driver = None
        brandName = None
        db_manager = None
        brand_options = None
        logger = None
        batch_id = None

        if len(args) >= 2:
            # Legacy positional form
            driver = args[0]
            brandName = args[1]
            master_password = kwargs.pop('master_password', None)
            ultraBikeCode = kwargs.pop('ultraBikeCode', None)
            bicycleUrlOrCode = kwargs.pop('bicycleUrlOrCode', None)
            db_manager = kwargs.pop('db_manager', kwargs.pop('db', None))
            # Allow legacy callers to still pass GUI-style options.
            description_name = kwargs.pop('description_name', kwargs.pop('descriptionName', kwargs.pop('description', None)))
            include_disclaimer = kwargs.pop('include_disclaimer', kwargs.pop('includeDisclaimer', False))
            include_order_note = kwargs.pop('include_order_note', kwargs.pop('includeOrderNote', False))
            is_frameset = kwargs.pop('is_frameset', kwargs.pop('isFrameset', None))

            brand_options = kwargs.pop('brand_options', {}) or {}
            if description_name:
                brand_options.setdefault('description_name', description_name)
            if include_disclaimer:
                brand_options.setdefault('append_disclaimer', include_disclaimer)
            if include_order_note:
                brand_options.setdefault('append_order_note', include_order_note)
            if is_frameset is not None:
                brand_options.setdefault('frameset_only', is_frameset)
            logger = kwargs.pop('logger', None)
            batch_id = kwargs.pop('batch_id', None)
        else:
            # GUI-style kwargs
            db_manager = kwargs.pop('db', kwargs.pop('db_manager', None))
            logger = kwargs.pop('logger', None)
            settings_manager = kwargs.pop('settings_manager', None)

            # Optional master password for decrypting credentials during this run
            master_password = kwargs.pop('master_password', None)

            # Product identifiers
            ultraBikeCode = kwargs.pop('product_code', kwargs.pop('productCode', kwargs.pop('ultraBikeCode', None)))
            bicycleUrlOrCode = kwargs.pop('url_or_code', kwargs.pop('url', kwargs.pop('bicycleUrlOrCode', None)))

            # Description / options
            description_name = kwargs.pop('description_name', kwargs.pop('descriptionName', kwargs.pop('description', None)))
            include_disclaimer = kwargs.pop('include_disclaimer', kwargs.pop('includeDisclaimer', False))
            include_order_note = kwargs.pop('include_order_note', kwargs.pop('includeOrderNote', False))
            is_frameset = kwargs.pop('is_frameset', kwargs.pop('isFrameset', None))

            # Build brand options dict
            brand_options = kwargs.pop('brand_options', {}) or {}
            if description_name:
                brand_options.setdefault('description_name', description_name)
            if include_disclaimer:
                brand_options.setdefault('append_disclaimer', include_disclaimer)
            if include_order_note:
                brand_options.setdefault('append_order_note', include_order_note)
            if is_frameset is not None:
                brand_options.setdefault('frameset_only', is_frameset)

            # Determine brandName from uploader class name if not provided
            brandName = kwargs.pop('brandName', None) or self.__class__.__name__

            # If GUI provided a settings_manager or db_manager, use them; else create db manager
            if db_manager is None and settings_manager is not None:
                try:
                    db_manager = settings_manager.db
                except Exception as e:
                    ErrorManager.show_error("UNEXPECTED_ERROR", error=str(e))
                    db_manager = None

            # If driver not provided, try to create one using BrowserManager and settings
            driver = kwargs.pop('driver', None)
            if driver is None:
                try:
                    from Config.BrowserConfig.BrowserManager import BrowserManager
                    # Use provided settings_manager or create temporary SettingsManager
                    if settings_manager is None:
                        settings_manager = SettingsManager(db_manager or DatabaseManager())
                    browser_choice = settings_manager.get_browser_choice()
                    bm = BrowserManager()
                    # Provide a retry_callback that returns False to avoid CLI prompts
                    driver = bm.setup_browser(browser_choice, retry_callback=lambda: False)
                except Exception as e:
                    ErrorManager.show_error("UNEXPECTED_ERROR", error=str(e))
                    driver = None

        # Assign common attributes
        self.driver = driver
        self.logger = logger
        self.brandName = brandName
        self.brand_options = brand_options or {}
        self.batch_id = batch_id

        # Optional: used for decrypting external credentials (Basso / Lee Cougan)
        self.master_password = master_password if 'master_password' in locals() else None

        # Debug: brand_options can be logged if needed

        self.features_uploaded = 0
        self.images_uploaded = 0

        self.navigation_manager = ProductNavigationHandler(self.driver, self.logger)
        self.url_handler = URLHandler()
        self.web_handler = WebInteractionHandler(self.driver)
        self.translation_handler = TranslationHandler()

        if ultraBikeCode is None and bicycleUrlOrCode is None:
            raise ValueError("Product identifier missing: provide 'product_code' or 'url_or_code' when using GUI.")

        self.ultraBikeCode = ultraBikeCode
        self.bicycleUrlOrCode = bicycleUrlOrCode

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
        cursor.execute("""
            INSERT INTO processing_history 
            (brand, product_code, url_or_code, status, duration_seconds, 
             features_uploaded, images_uploaded, details_json, processed_at)
            VALUES (?, ?, ?, 'success', ?, ?, ?, ?, datetime('now'))
        """, (
            self.brandName, 
            self.ultraBikeCode, 
            self.bicycleUrlOrCode, 
            duration,
            self.features_uploaded,
            self.images_uploaded,
            details_json
        ))
        self.db.conn.commit()
        self._log("Success recorded in database")

    def _record_failure(self, error_message, duration):
        """Record failed upload to database"""
        cursor = self.db.conn.cursor()
        details_json = getattr(self, "_details_json", None)
        cursor.execute("""
            INSERT INTO processing_history 
            (brand, product_code, url_or_code, status, error_message, 
             duration_seconds, details_json, processed_at)
            VALUES (?, ?, ?, 'failed', ?, ?, ?, datetime('now'))
        """, (
            self.brandName, 
            self.ultraBikeCode, 
            self.bicycleUrlOrCode, 
            error_message,
            duration,
            details_json
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
                SET last_used = datetime('now'), 
                    use_count = ?,
                    url_or_code = ?
                WHERE id = ?
            """, (existing['use_count'] + 1, self.bicycleUrlOrCode, existing['id']))
        else:
            # Insert new
            cursor.execute("""
                INSERT INTO recent_products 
                (brand, product_code, url_or_code, last_used, use_count)
                VALUES (?, ?, ?, datetime('now'), 1)
            """, (self.brandName, self.ultraBikeCode, self.bicycleUrlOrCode))

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
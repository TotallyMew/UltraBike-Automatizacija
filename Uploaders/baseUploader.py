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

def getCode():
    """CLI helper for getting product code"""
    code = input("Iveskite koda: ")
    return code

class ProductUploader(ABC):
    def __init__(self, driver, brandName, ultraBikeCode=None, bicycleUrlOrCode=None, db_manager=None, brand_options=None, logger=None):
        print(f"DEBUG baseUploader.__init__: brand_options = {brand_options}")
        
        self.driver = driver
        self.logger = logger
        self.brandName = brandName
        self.brand_options = brand_options or {}
        
        print(f"DEBUG baseUploader.__init__: self.brand_options = {self.brand_options}")

        self.features_uploaded = 0
        self.images_uploaded = 0

        self.navigation_manager = ProductNavigationHandler(driver, logger)
        self.url_handler = URLHandler()
        self.web_handler = WebInteractionHandler(driver)
        self.translation_handler = TranslationHandler()

        self.ultraBikeCode = ultraBikeCode if ultraBikeCode is not None else getCode()
        self.bicycleUrlOrCode = bicycleUrlOrCode if bicycleUrlOrCode is not None else self.url_handler.get_brand_url(brandName)

        # Database setup
        if db_manager:
            self.db = db_manager
        else:
            self.db = DatabaseManager()

        self.session_manager = SessionManager(self.db)
        self.settings_manager = SettingsManager(self.db)

        self.translationManager = TranslationManager(brandName, self.db, logger)
        self.imageUploader = ImageUploader(driver, brandName, logger)
        self.featureUploader = FeatureUploader(driver, logger)

        # Description handling - always initialize manager (needed for standalone disclaimer)
        self.description_manager = DescriptionManager(self.db, logger)
        self.description_name = self.brand_options.get('description_name', None)
        print(f"DEBUG baseUploader.__init__: self.description_name = {self.description_name}")
        print(f"DEBUG baseUploader.__init__: DescriptionManager initialized")
    
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
            
            print("DEBUG run(): About to call uploadDescription()")
            
            # Upload description (if provided)
            self.uploadDescription()
            
            print("DEBUG run(): uploadDescription() completed")
            
            # Upload features
            self.uploadFeatures()
            
            # Upload brand
            self.uploadBrand()
            
            # Calculate duration
            duration = time.time() - self.start_time
            
            # Record success in database
            self._record_success(duration)
            
            # Add to recent products cache
            self._cache_recent_product()
            
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
        cursor.execute("""
            INSERT INTO processing_history 
            (brand, product_code, url_or_code, status, duration_seconds, 
             features_uploaded, images_uploaded, processed_at)
            VALUES (?, ?, ?, 'success', ?, ?, ?, datetime('now'))
        """, (
            self.brandName, 
            self.ultraBikeCode, 
            self.bicycleUrlOrCode, 
            duration,
            self.features_uploaded,
            self.images_uploaded
        ))
        self.db.conn.commit()
        self._log("Success recorded in database")
    
    def _record_failure(self, error_message, duration):
        """Record failed upload to database"""
        cursor = self.db.conn.cursor()
        cursor.execute("""
            INSERT INTO processing_history 
            (brand, product_code, url_or_code, status, error_message, 
             duration_seconds, processed_at)
            VALUES (?, ?, ?, 'failed', ?, ?, datetime('now'))
        """, (
            self.brandName, 
            self.ultraBikeCode, 
            self.bicycleUrlOrCode, 
            error_message,
            duration
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
        print(f"DEBUG: uploadDescription called, description_name = {self.description_name}")

        # Get append_disclaimer flag from brand_options
        append_disclaimer = self.brand_options.get('append_disclaimer', False)

        # If no description but disclaimer is checked, upload just the disclaimer
        if not self.description_name and append_disclaimer:
            self._log("No description selected, but disclaimer requested - uploading standalone disclaimer")
            print("DEBUG: No description name but disclaimer=True, uploading standalone disclaimer")
            try:
                # Upload disclaimer only (empty strings for base content)
                success = self.description_manager.upload_to_prestashop_raw(
                    self.driver,
                    self.ultraBikeCode,
                    '',  # Empty LT content
                    '',  # Empty EN content
                    '',  # Empty LV content
                    append_disclaimer=True
                )

                if success:
                    self._log("Standalone disclaimer uploaded successfully")
                    ErrorManager.show_success("Disclaimer įkeltas!")
                else:
                    self._log_error("Standalone disclaimer upload returned False")
                    ErrorManager.show_warning("Nepavyko įkelti disclaimer")

            except Exception as e:
                import traceback
                print(f"DEBUG: Exception in uploadDescription (standalone): {traceback.format_exc()}")
                self._log_error("Standalone disclaimer upload failed", exception=e)
                ErrorManager.show_warning(f"Disclaimer įkėlimo klaida: {str(e)}")
            return

        # If no description and no disclaimer, skip
        if not self.description_name:
            self._log("No description to upload")
            print("DEBUG: No description name provided, skipping")
            return

        # Upload description with optional disclaimer
        print(f"DEBUG: Attempting to upload description: {self.description_name}, append_disclaimer={append_disclaimer}")
        self._log("Uploading description", name=self.description_name, append_disclaimer=append_disclaimer)
        try:
            success = self.description_manager.upload_to_prestashop(
                self.driver,
                self.ultraBikeCode,
                self.description_name,
                append_disclaimer=append_disclaimer
            )

            print(f"DEBUG: upload_to_prestashop returned: {success}")

            if success:
                self._log("Description uploaded successfully")
                if append_disclaimer:
                    ErrorManager.show_success(f"Aprašymas '{self.description_name}' su disclaimer įkeltas!")
                else:
                    ErrorManager.show_success(f"Aprašymas '{self.description_name}' įkeltas!")
            else:
                self._log_error("Description upload returned False")
                ErrorManager.show_warning(f"Nepavyko įkelti aprašymo '{self.description_name}'")

        except Exception as e:
            import traceback
            print(f"DEBUG: Exception in uploadDescription: {traceback.format_exc()}")
            self._log_error("Description upload failed", exception=e)
            ErrorManager.show_warning(f"Aprašymo įkėlimo klaida: {str(e)}")
            # Don't raise - continue with features

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
            self.featureUploader.uploadAllLanguages(ltData, enData, lvData)
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
    
    def __del__(self):
        """Cleanup database connection if we own it"""
        if hasattr(self, 'own_db') and self.own_db and hasattr(self, 'db'):
            self.db.close()
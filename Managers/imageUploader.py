# managers/imageUploader.py

from Utilities.ImageHandler import ImageHandler
from Database.DatabaseManager import DatabaseManager
from Database.SettingsManager import SettingsManager
from Utilities.ErrorManager import ErrorManager


class ImageUploader:
    def __init__(self, driver, brandName, logger=None, settings_manager=None):
        self.driver = driver
        self.brandName = brandName
        self.logger = logger
        # Prefer DB-backed settings from GUI; fall back to DB defaults when used standalone.
        self.settings_manager = settings_manager or SettingsManager(DatabaseManager())
        self.image_handler = ImageHandler(self.settings_manager, logger)
    
    def _log(self, message, **context):
        if self.logger:
            self.logger.log("ImageUploader", message, **context)
    
    def _log_error(self, message, exception=None, **context):
        if self.logger:
            self.logger.error("ImageUploader", message, exception=exception, **context)

    def uploadAll(self, url):
        self._log("Starting image upload", brand=self.brandName, url=url)
        
        if self.brandName.upper() == "KROSS":
            try:
                self.image_handler.download_kross_images(url, self.driver)
                self.image_handler.upload_kross_images(self.driver)
                self._log("KROSS images uploaded successfully")
                ErrorManager.show_success("Nuotraukos sėkmingai įkeltos!")
            except Exception as e:
                self._log_error("Image upload failed", exception=e, brand=self.brandName)
                ErrorManager.show_error("UPLOAD_IMAGE_FAILED")
                raise
        else:
            self._log("Image upload not implemented for brand", brand=self.brandName)
            ErrorManager.show_warning(f"Nuotraukų siuntimas nėra sukurtas {self.brandName}")
# Uploaders/baseUploader.py

from abc import ABC, abstractmethod
from Managers.translationManager import TranslationManager
from Managers.imageUploader import ImageUploader
from Managers.FeatureUploader.featureUploader import FeatureUploader
from Config.Settings.SettingsManager import SettingsManager
from Utilities.ProductNavigationHandler import ProductNavigationHandler
from Utilities.URLHandler import URLHandler
from Utilities.TranslationHandler import TranslationHandler
from Utilities.WebIntercationHandler import WebInteractionHandler
from Utilities.ErrorManager import ErrorManager

settings_manager = SettingsManager()

def getCode():
    code = input("Iveskite koda: ")
    return code

class ProductUploader(ABC):
    def __init__(self, driver, brandName, ultraBikeCode=None, bicycleUrlOrCode=None, logger=None):
        self.driver = driver
        self.logger = logger
        self.brandName = brandName

        self.navigation_manager = ProductNavigationHandler(driver, logger)
        self.url_handler = URLHandler()
        self.web_handler = WebInteractionHandler(driver)
        self.translation_handler = TranslationHandler()

        self.ultraBikeCode = ultraBikeCode if ultraBikeCode is not None else getCode()
        self.bicycleUrlOrCode = bicycleUrlOrCode if bicycleUrlOrCode is not None else self.url_handler.get_brand_url(brandName)

        self.translationManager = TranslationManager(brandName, logger)
        self.imageUploader = ImageUploader(driver, brandName, logger)
        self.featureUploader = FeatureUploader(driver, logger)
    
    def _log(self, message, **context):
        if self.logger:
            self.logger.log(f"{self.brandName}Uploader", message, **context)
    
    def _log_error(self, message, exception=None, **context):
        if self.logger:
            self.logger.error(f"{self.brandName}Uploader", message, exception=exception, **context)

    def run(self):
        self._log("Starting upload process", code=self.ultraBikeCode)
        
        try:
            self.scrape()
            self.translate()
            self.openProduct()
            
            if settings_manager.download_pictures_and_upload():
                self.uploadImages()
            
            self.uploadFeatures()
            self.uploadBrand()
            self.uploadDescription()
            
            self._log("Upload process completed successfully")
            
        except Exception as e:
            self._log_error("Upload process failed", exception=e, code=self.ultraBikeCode)
            ErrorManager.show_error("UNEXPECTED_ERROR", error=str(e))
            raise

    @abstractmethod
    def scrape(self):
        pass

    def translate(self):
        self._log("Starting translation")
        try:
            self.translationManager.translateAll()
            self._log("Translation completed")
        except Exception as e:
            self._log_error("Translation failed", exception=e)
            ErrorManager.show_error("TRANSLATION_FAILED")
            raise

    def openProduct(self):
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
            self.imageUploader.uploadAll(self.bicycleUrlOrCode)
            self._log("Images uploaded successfully")
        except Exception as e:
            self._log_error("Image upload failed", exception=e)
            ErrorManager.show_error("UPLOAD_IMAGE_FAILED")
            # Don't raise - continue without images

    def uploadFeatures(self):
        self._log("Uploading features")
        try:
            ltData = self.translationManager.loadLT()
            enData = self.translationManager.loadEN()
            lvData = self.translationManager.loadLV()
            
            self._log("Feature data loaded", lt_count=len(ltData), en_count=len(enData))
            self.featureUploader.uploadAllLanguages(ltData, enData, lvData)
            self._log("Features uploaded successfully")
        except Exception as e:
            self._log_error("Feature upload failed", exception=e)
            ErrorManager.show_error("UPLOAD_FEATURE_FAILED", feature="multiple")
            raise

    def uploadBrand(self):
        pass

    def uploadDescription(self):
        pass

    def saveUpdate(self):
        self._log("Saving updates")
        try:
            self.web_handler.save_information()
            self._log("Updates saved successfully")
        except Exception as e:
            self._log_error("Save failed", exception=e)
            ErrorManager.show_error("UPLOAD_SAVE_FAILED")
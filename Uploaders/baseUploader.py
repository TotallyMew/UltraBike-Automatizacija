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

settings_manager = SettingsManager()

def getCode():
    code = input("Iveskite koda")
    return code
class ProductUploader(ABC):
    def __init__(self, driver, brandName, ultraBikeCode=None, bicycleUrlOrCode=None):

        self.driver = driver

        self.navigation_manager = ProductNavigationHandler(driver)
        self.url_handler = URLHandler()
        self.web_handler = WebInteractionHandler(driver)
        self.translation_handler = TranslationHandler()

        self.brandName = brandName
        self.ultraBikeCode = ultraBikeCode if ultraBikeCode is not None else getCode()
        self.bicycleUrlOrCode = bicycleUrlOrCode if bicycleUrlOrCode is not None else self.url_handler.get_brand_url(brandName)

        self.translationManager = TranslationManager(brandName)
        self.imageUploader = ImageUploader(driver, brandName)
        self.featureUploader = FeatureUploader(driver)

    def run(self): #Čia settings sumest
        self.scrape()
        self.translate()
        self.openProduct()
        if(settings_manager.download_pictures_and_upload()):
            self.uploadImages()
        self.uploadFeatures()
        self.uploadBrand()
        self.uploadDescription()
        self.saveUpdate()

    @abstractmethod
    def scrape(self):
        pass

    def translate(self):
        self.translationManager.translateAll()

    def openProduct(self):
        self.navigation_manager.navigate_to_product(self.brandName, self.ultraBikeCode)

    def uploadImages(self):
        self.imageUploader.uploadAll(self.bicycleUrlOrCode)

    def uploadFeatures(self):
        ltData = self.translationManager.loadLT()
        enData = self.translationManager.loadEN()
        lvData = self.translationManager.loadLV()
        self.featureUploader.uploadAllLanguages(ltData, enData, lvData)

    def uploadBrand(self):
        pass

    def uploadDescription(self):
        pass

    def saveUpdate(self):
       self.web_handler.save_information()

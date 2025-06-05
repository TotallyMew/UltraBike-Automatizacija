# Uploaders/baseUploader.py

from abc import ABC, abstractmethod
from Managers.translationManager import TranslationManager
from Managers.imageUploader import ImageUploader
from Managers.FeatureUploader.featureUploader import FeatureUploader
from Utilities.scrapeUtilities import getURL
from generalUtilities import prekesPaspaudimas, getCode
from Config.Settings.SettingsManager import SettingsManager

settings_manager = SettingsManager()

class ProductUploader(ABC):
    def __init__(self, driver, brandName, ultraBikeCode=None, bicycleUrlOrCode=None):
        self.driver = driver
        self.brandName = brandName
        self.ultraBikeCode = ultraBikeCode if ultraBikeCode is not None else getCode()
        self.bicycleUrlOrCode = bicycleUrlOrCode if bicycleUrlOrCode is not None else getURL(brandName)

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

    @abstractmethod
    def scrape(self):
        pass

    def translate(self):
        self.translationManager.translateAll()

    def openProduct(self):
        prekesPaspaudimas(self.driver, self.brandName, self.ultraBikeCode)

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

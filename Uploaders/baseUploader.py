from abc import ABC, abstractmethod
from Managers.translationManager import TranslationManager
from Managers.imageUploader import ImageUploader
from Managers.FeatureUploader.featureUploader import FeatureUploader
from Utilities.scrapeUtilities import getURL
from generalUtilities import getCode
from generalUtilities import prekesPaspaudimas

class ProductUploader(ABC):
    def __init__(self, driver, brandName):
        self.driver = driver
        self.brandName = brandName
        self.code = getCode()
        self.url = getURL(brandName)
        self.translationManager = TranslationManager(brandName)
        self.imageUploader = ImageUploader(driver, brandName)
        self.featureUploader = FeatureUploader(driver)

    def run(self):
        self.scrape()
        self.translate()
        self.openProduct()
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
        prekesPaspaudimas(self.driver, self.brandName, self.code)

    def uploadImages(self):
        self.imageUploader.uploadAll(self.url)

    def uploadFeatures(self):
        ltData = self.translationManager.loadLT()
        enData = self.translationManager.loadEN()
        lvData = self.translationManager.loadLV()
        self.featureUploader.uploadAllLanguages(ltData, enData, lvData)

    def uploadBrand(self):
        pass  # Optional override in brand-specific class

    def uploadDescription(self):
        pass  # Optional override in brand-specific class

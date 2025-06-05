# uploaders/KROSS.py

from Uploaders.baseUploader import ProductUploader
from Scrapers.KROSSScraper import scrapeAndTranslateToFileKROSS
from Managers.translationManager import TranslationManager
from Managers.imageUploader import ImageUploader
from generalUtilities import addBrandName, addDescription

class KROSS(ProductUploader):
    def scrape(self):
        # Performs scraping and writes to temporary files
        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFileKROSS,
            url=self.bicycleUrlOrCode
        )

    def uploadBrand(self):
        addBrandName(self.driver, self.brandName)

    def uploadDescription(self):
        #addDescription(self.driver, self.translationManager.getDescriptionFile())
        pass


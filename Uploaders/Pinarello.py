# uploaders/KROSS.py

from Uploaders.baseUploader import ProductUploader
from Scrapers.KROSSScraper import scrapeAndTranslateToFileKROSS
from Managers.translationManager import TranslationManager
from Managers.imageUploader import ImageUploader

from Uploaders.baseUploader import ProductUploader
from Scrapers.PinarelloScraper import scrapeAndTranslateToFilePinarello

class Pinarello(ProductUploader):
    def scrape(self):
        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFilePinarello,
            url=self.bicycleUrlOrCode
        )

    def uploadBrand(self):
        self.web_handler.add_brand_name(self.brandName)

    def uploadDescription(self):
        pass


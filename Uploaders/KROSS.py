# uploaders/KROSS.py

from Uploaders.BaseUploader import ProductUploader
from Scrapers.KROSSScraper import scrapeAndTranslateToFileKROSS
from Managers.TranslationManager import TranslationManager
from Managers.ImageUploader import ImageUploader

class KROSS(ProductUploader):
    def scrape(self):
        # Performs scraping and writes to temporary files
        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFileKROSS,
            url=self.bicycleUrlOrCode
        )

    def uploadBrand(self):
        self.web_handler.add_brand_name(self.brandName)



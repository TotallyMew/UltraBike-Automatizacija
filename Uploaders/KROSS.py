# uploaders/KROSS.py

from Uploaders.BaseUploader import ProductUploader
from Scrapers.KROSSScraper import scrapeAndTranslateToFileKROSS

class KROSS(ProductUploader):
    def scrape(self):
        # Performs scraping and writes to temporary files
        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFileKROSS,
            url=self.bicycleUrlOrCode
        )

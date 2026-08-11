from Uploaders.BaseUploader import ProductUploader
from Scrapers.RondoScraper import scrapeAndTranslateToFileRondo

class Rondo(ProductUploader):
    def scrape(self):
        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFileRondo,
            url=self.bicycleUrlOrCode  # ← Fixed
        )


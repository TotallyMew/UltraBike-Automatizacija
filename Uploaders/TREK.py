from Uploaders.BaseUploader import ProductUploader
from Scrapers.TREKScraper import scrapeAndTranslateToFileTREK

class TREK(ProductUploader):
    def scrape(self):
        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFileTREK,
            url=self.bicycleUrlOrCode  # ← Fixed
        )


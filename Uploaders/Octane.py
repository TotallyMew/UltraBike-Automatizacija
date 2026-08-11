from Uploaders.BaseUploader import ProductUploader
from Scrapers.OctaneScraper import scrapeAndTranslateToFileOctaneOne

class Octane(ProductUploader):
    def scrape(self):
        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFileOctaneOne,
            url=self.bicycleUrlOrCode  # ← Fixed
        )


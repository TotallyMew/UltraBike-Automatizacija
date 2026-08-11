from Uploaders.BaseUploader import ProductUploader
from Scrapers.FactorScraper import scrapeAndTranslateToFileFactor

class Factor(ProductUploader):
    def scrape(self):
        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFileFactor,
            url=self.bicycleUrlOrCode
        )



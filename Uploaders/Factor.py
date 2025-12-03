from Uploaders.baseUploader import ProductUploader
from Scrapers.FactorScraper import scrapeAndTranslateToFileFactor

class Factor(ProductUploader):
    def scrape(self):
        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFileFactor,
            url=self.bicycleUrlOrCode
        )

    def uploadBrand(self):
        self.web_handler.add_brand_name(self.brandName)

    def uploadDescription(self):
        pass

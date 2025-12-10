from Uploaders.baseUploader import ProductUploader
from Scrapers.OctaneScraper import scrapeAndTranslateToFileOctaneOne

class Octane(ProductUploader):
    def scrape(self):
        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFileOctaneOne,
            url=self.bicycleUrlOrCode  # ← Fixed
        )

    def uploadBrand(self):
        self.web_handler.add_brand_name(self.brandName)

    def uploadDescription(self):
        pass
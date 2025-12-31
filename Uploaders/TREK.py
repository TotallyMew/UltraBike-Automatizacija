from Uploaders.BaseUploader import ProductUploader
from Scrapers.TREKScraper import scrapeAndTranslateToFileTREK

class TREK(ProductUploader):
    def scrape(self):
        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFileTREK,
            url=self.bicycleUrlOrCode  # ← Fixed
        )

    def uploadBrand(self):
        self.web_handler.add_brand_name(self.brandName)


from Uploaders.baseUploader import ProductUploader
from Scrapers.LeeCouganScraper import scrapeAndTranslateToFileLeeCougan

class LeeCougan(ProductUploader):
    def scrape(self):
        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFileLeeCougan,
            url=self.bicycleUrlOrCode,  # ← Fixed
            driver=self.driver
        )

    def uploadBrand(self):
        self.web_handler.add_brand_name(self.brandName)


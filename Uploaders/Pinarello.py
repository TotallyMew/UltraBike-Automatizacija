# uploaders/Pinarello.py

from Uploaders.BaseUploader import ProductUploader
from Scrapers.PinarelloScraper import scrapeAndTranslateToFilePinarello

class Pinarello(ProductUploader):
    def scrape(self):
        # Get frameset_only option from brand_options
        frameset_only = self.brand_options.get('frameset_only', None)
        
        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFilePinarello,
            url=self.bicycleUrlOrCode,
            frameset_only=frameset_only  # ← Pass to scraper
        )

    def uploadBrand(self):
        self.web_handler.add_brand_name(self.brandName)

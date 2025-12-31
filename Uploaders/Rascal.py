from Uploaders.BaseUploader import ProductUploader
from Scrapers.RascalScraper import scrapeAndTranslateToFileRascal

class Rascal(ProductUploader):
    def scrape(self):
        # Get variant choice (if multiple variants exist)
        # GUI does not currently expose variant selection.
        # If the page contains multiple variants, the scraper will raise a clear error.
        variant_index = None
        
        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFileRascal,
            url=self.bicycleUrlOrCode,  # ← Fixed: removed double self
            variant_index=variant_index
        )

    def uploadBrand(self):
        self.web_handler.add_brand_name(self.brandName)

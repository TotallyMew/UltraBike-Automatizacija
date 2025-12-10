from Uploaders.baseUploader import ProductUploader
from Scrapers.RascalScraper import scrapeAndTranslateToFileRascal

class Rascal(ProductUploader):
    def scrape(self):
        # Get variant choice (if multiple variants exist)
        # For now, None = prompt user in scraper (CLI mode)
        # Later in GUI, this will come from dropdown
        variant_index = None  # Let scraper prompt user
        
        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFileRascal,
            url=self.bicycleUrlOrCode,  # ← Fixed: removed double self
            variant_index=variant_index
        )

    def uploadBrand(self):
        self.web_handler.add_brand_name(self.brandName)

    def uploadDescription(self):
        pass
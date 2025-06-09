from Uploaders.baseUploader import ProductUploader
from Scrapers.KROSSScraper import scrapeAndTranslateToFileKROSS
from Managers.translationManager import TranslationManager
from Managers.imageUploader import ImageUploader

class TREK(ProductUploader):
    def scrape(self):
        # Performs scraping and writes to temporary files
        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFileKROSS,
            url=self.self.bicycleUrlOrCode
        )

    def uploadBrand(self):
        self.web_handler.add_brand_name(self.brandName)

    def uploadDescription(self):
        # Optional: implement description logic using addDescriptionFromWord
        pass


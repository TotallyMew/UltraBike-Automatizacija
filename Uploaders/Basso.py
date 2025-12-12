# uploaders/Basso.py

from Uploaders.baseUploader import ProductUploader
from Scrapers.BassoScraper import scrapeAndTranslateToFileBasso
from Managers.translationManager import TranslationManager

class Basso(ProductUploader):
    def scrape(self):
        # Pass both ultraBikeCode and bassoConfigurationCode to the scrape function
        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFileBasso,
            url=self.bicycleUrlOrCode,
            driver=self.driver
        )

    def uploadBrand(self):
        self.web_handler.add_brand_name(self.brandName)





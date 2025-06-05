# uploaders/Basso.py

from Uploaders.baseUploader import ProductUploader
from Scrapers.BassoScraper import scrapeAndTranslateToFileBasso
from Managers.translationManager import TranslationManager
#from Managers.imageUploader import ImageUploader
from generalUtilities import addBrandName

class Basso(ProductUploader):
    def scrape(self):
        # Pass both ultraBikeCode and bassoConfigurationCode to the scrape function
        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFileBasso,
            url=self.bicycleUrlOrCode,
            driver=self.driver
        )

    def uploadBrand(self):
        addBrandName(self.driver, self.brandName)

    def uploadDescription(self):
        # Optional: implement description logic using addDescriptionFromWord
        pass



# uploaders/LeeCougan.py

from Uploaders.baseUploader import ProductUploader
from Scrapers.LeeCouganScraper import scrapeAndTranslateToFileLeeCougan
from Managers.translationManager import TranslationManager
#from Managers.imageUploader import ImageUploader
from generalUtilities import addBrandName

class LeeCougan(ProductUploader):
    def scrape(self):
        # Performs scraping and writes to temporary files
        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFileLeeCougan,
            url=self.url, driver=self.driver
        )

    def uploadBrand(self):
        addBrandName(self.driver, self.brandName)

    def uploadDescription(self):
        # Optional: implement description logic using addDescriptionFromWord
        pass



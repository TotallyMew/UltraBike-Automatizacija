# uploaders/Basso.py

from Uploaders.BaseUploader import ProductUploader
from Scrapers.BassoScraper import scrapeAndTranslateToFileBasso
from Managers.TranslationManager import TranslationManager

class Basso(ProductUploader):
    def scrape(self):
        if not self.master_password:
            raise ValueError("Unlock Basso credentials before collecting product data")
        user, pwd = self.session_manager.get_external_credentials('basso', self.master_password)
        if not user or not pwd:
            raise ValueError("Basso credentials are missing")
        credentials = (user, pwd)

        # Pass both ultraBikeCode and bassoConfigurationCode to the scrape function
        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFileBasso,
            url=self.bicycleUrlOrCode,
            driver=self.driver,
            credentials=credentials
        )


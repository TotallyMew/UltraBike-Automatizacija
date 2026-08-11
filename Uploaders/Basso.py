# uploaders/Basso.py

from Uploaders.BaseUploader import ProductUploader
from Scrapers.BassoScraper import scrapeAndTranslateToFileBasso
from Managers.TranslationManager import TranslationManager

class Basso(ProductUploader):
    def scrape(self):
        credentials = None
        try:
            if getattr(self, 'master_password', None):
                user, pwd = self.session_manager.get_external_credentials('basso', self.master_password)
                if user and pwd:
                    credentials = (user, pwd)
        except Exception:
            credentials = None

        # Pass both ultraBikeCode and bassoConfigurationCode to the scrape function
        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFileBasso,
            url=self.bicycleUrlOrCode,
            driver=self.driver,
            credentials=credentials
        )


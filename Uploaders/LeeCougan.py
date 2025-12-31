from Uploaders.BaseUploader import ProductUploader
from Scrapers.LeeCouganScraper import scrapeAndTranslateToFileLeeCougan

class LeeCougan(ProductUploader):
    def scrape(self):
        credentials = None
        try:
            if getattr(self, 'master_password', None):
                user, pwd = self.session_manager.get_external_credentials('leecougan', self.master_password)
                if user and pwd:
                    credentials = (user, pwd)
        except Exception:
            credentials = None

        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFileLeeCougan,
            url=self.bicycleUrlOrCode,  # ← Fixed
            driver=self.driver,
            credentials=credentials
        )

    def uploadBrand(self):
        self.web_handler.add_brand_name(self.brandName)


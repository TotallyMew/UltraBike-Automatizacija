from Uploaders.BaseUploader import ProductUploader
from Scrapers.LeeCouganScraper import scrapeAndTranslateToFileLeeCougan

class LeeCougan(ProductUploader):
    def scrape(self):
        if not self.master_password:
            raise ValueError("Unlock Lee Cougan credentials before collecting product data")
        user, pwd = self.session_manager.get_external_credentials('leecougan', self.master_password)
        if not user or not pwd:
            raise ValueError("Lee Cougan credentials are missing")
        credentials = (user, pwd)

        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFileLeeCougan,
            url=self.bicycleUrlOrCode,  # ← Fixed
            driver=self.driver,
            credentials=credentials
        )


# managers/imageUploader.py

from Utilities.scrapeUtilities import siustiNuotraukasKROSS, sukeltiNuotraukasKROSS

class ImageUploader:
    def __init__(self, driver, brandName):
        self.driver = driver
        self.brandName = brandName

    def uploadAll(self, url):
        if self.brandName.upper() == "KROSS":
            siustiNuotraukasKROSS(url, self.driver)
            sukeltiNuotraukasKROSS(self.driver)
            print("sukelta")
        else:
            print(f"Nuotraukų siuntimas nėra sukurtas {self.brandName}")


# managers/imageUploader.py

from Utilities.ImageHandler import ImageHandler
from Config.Settings.SettingsManager import SettingsManager


class ImageUploader:
    def __init__(self, driver, brandName):
        self.driver = driver
        self.brandName = brandName
        self.settings_manager = SettingsManager()
        self.image_handler = ImageHandler(self.settings_manager)

    def uploadAll(self, url):
        if self.brandName.upper() == "KROSS":
            self.image_handler.download_kross_images(url, self.driver)
            self.image_handler.upload_kross_images(self.driver)
            print("sukelta")
        else:
            print(f"Nuotraukų siuntimas nėra sukurtas {self.brandName}")


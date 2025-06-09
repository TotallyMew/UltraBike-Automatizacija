# managers/translationManager.py

import inspect
from Utilities.TranslationHandler import TranslationHandler
from Utilities.FileHandler import FileHandler

class TranslationManager:
    def __init__(self, brandName):
        self.brandName = brandName
        self.ltPath =  f"pabaigta{brandName}LT.txt"
        self.enPath = f"pabaigta{brandName}ENG.txt"
        self.engDictPath = "Assets/Translations/vertimasSavybesLT-ENG.txt"
        self.descriptionPath = "Assets/Translations/vertimasSavybesPL-LT.txt"
        self.translation_handler = TranslationHandler()
        self.file_handler = FileHandler()
    def prepareTranslationFiles(self, scrape_func, url, **kwargs):
        args = {
            "bicycleUrlOrCode": url,
            "outputFile": self.ltPath
        }

        # Only add 'driver' if the scrape_func supports it
        if 'driver' in inspect.signature(scrape_func).parameters:
            args["driver"] = kwargs.get("driver")

        scrape_func(**args)
        self.translation_handler.translate_to_english(self.ltPath, self.enPath, self.engDictPath)


    def translateAll(self):
        self.translation_handler.translate_to_english(self.ltPath, self.enPath, self.engDictPath)

    def loadLT(self):
        return self.file_handler.read_translated_file(self.ltPath)

    def loadEN(self):
        return self.file_handler.read_translated_file(self.enPath)

    def loadLV(self):
        return self.file_handler.read_translated_file(self.enPath)  # Assuming LV is the same as EN for now


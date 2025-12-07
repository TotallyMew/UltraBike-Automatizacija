# managers/translationManager.py

import inspect
from Utilities.TranslationHandler import TranslationHandler
from Utilities.FileHandler import FileHandler
from Utilities.ErrorManager import ErrorManager

class TranslationManager:
    def __init__(self, brandName, logger=None):
        self.brandName = brandName
        self.logger = logger
        self.ltPath =  f"pabaigta{brandName}LT.txt"
        self.enPath = f"pabaigta{brandName}ENG.txt"
        self.engDictPath = (r"D:\Iš desktop\Programavimas\Projects\Python\UltraBike_Automatizacija\Assets\Translations\vertimasSavybesLT-ENG.txt")
        self.descriptionPath = (r"D:\Iš desktop\Programavimas\Projects\Python\UltraBike_Automatizacija\Assets\Translations\vertimasSavybesPL-LT.txt")
        self.translation_handler = TranslationHandler()
        self.file_handler = FileHandler()
    
    def _log(self, message, **context):
        if self.logger:
            self.logger.log("TranslationManager", message, **context)
    
    def _log_error(self, message, exception=None, **context):
        if self.logger:
            self.logger.error("TranslationManager", message, exception=exception, **context)
    
    def prepareTranslationFiles(self, scrape_func, url, **kwargs):
        self._log("Preparing translation files", brand=self.brandName, url=url)
        
        args = {
            "bicycleUrlOrCode": url,
            "outputFile": self.ltPath
        }

        # Only add 'driver' if the scrape_func supports it
        if 'driver' in inspect.signature(scrape_func).parameters:
            args["driver"] = kwargs.get("driver")

        try:
            scrape_func(**args)
            self._log("Scraping completed", output_file=self.ltPath)
            
            self.translation_handler.translate_to_english(self.ltPath, self.enPath, self.engDictPath)
            self._log("Translation to English completed", output_file=self.enPath)
            
        except FileNotFoundError as e:
            self._log_error("Translation dictionary not found", exception=e, dict_path=self.engDictPath)
            ErrorManager.show_error("TRANSLATION_FILE_NOT_FOUND", file_path=self.engDictPath)
            raise
        except Exception as e:
            self._log_error("Translation preparation failed", exception=e, brand=self.brandName)
            ErrorManager.show_error("TRANSLATION_FAILED")
            raise

    def translateAll(self):
        self._log("Starting full translation")
        try:
            self.translation_handler.translate_to_english(self.ltPath, self.enPath, self.engDictPath)
            self._log("Translation completed successfully")
        except Exception as e:
            self._log_error("Translation failed", exception=e)
            raise

    def loadLT(self):
        self._log("Loading Lithuanian translations", file=self.ltPath)
        try:
            data = self.file_handler.read_translated_file(self.ltPath)
            self._log("Lithuanian data loaded", tables=len(data))
            return data
        except Exception as e:
            self._log_error("Failed to load Lithuanian data", exception=e, file=self.ltPath)
            ErrorManager.show_error("FILE_NOT_FOUND", path=self.ltPath)
            raise

    def loadEN(self):
        self._log("Loading English translations", file=self.enPath)
        try:
            data = self.file_handler.read_translated_file(self.enPath)
            self._log("English data loaded", tables=len(data))
            return data
        except Exception as e:
            self._log_error("Failed to load English data", exception=e, file=self.enPath)
            ErrorManager.show_error("FILE_NOT_FOUND", path=self.enPath)
            raise

    def loadLV(self):
        self._log("Loading Latvian translations (using EN)", file=self.enPath)
        return self.file_handler.read_translated_file(self.enPath)
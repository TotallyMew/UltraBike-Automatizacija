# Standard library
import inspect
from pathlib import Path

# Local
from Utilities.AppPaths import get_data_dir
from Utilities.ErrorManager import ErrorManager
from Utilities.FileHandler import FileHandler
from Utilities.TranslationHandler import TranslationHandler

class TranslationManager:
    def __init__(self, brandName, db_manager=None, logger=None):
        self.brandName = brandName
        self.logger = logger
        base = get_data_dir()
        self.ltPath = str(base / f"pabaigta{brandName}LT.txt")
        self.enPath = str(base / f"pabaigta{brandName}ENG.txt")
        self.translation_handler = TranslationHandler(db_manager)
        self.file_handler = FileHandler()
        self.db = db_manager
    
    def _log(self, message, **context):
        if self.logger:
            self.logger.log("TranslationManager", message, **context)
    
    def _log_error(self, message, exception=None, **context):
        if self.logger:
            self.logger.error("TranslationManager", message, exception=exception, **context)
        # Show error in GUI
        if exception:
            ErrorManager.show_error("UNEXPECTED_ERROR", error=str(exception))
        else:
            ErrorManager.show_error("UNEXPECTED_ERROR", error=message)
    
    def prepareTranslationFiles(self, scrape_func, url, **kwargs):
        self._log("Preparing translation files", brand=self.brandName, url=url)
    
        args = {
            "bicycleUrlOrCode": url,
            "outputFile": self.ltPath,
            'db_manager': self.db
        }

        # Get scraper's accepted parameters
        scraper_params = inspect.signature(scrape_func).parameters
    
        # Add kwargs that scraper accepts
        for key, value in kwargs.items():
            if key in scraper_params:
                args[key] = value
    
        # Only add 'driver' if scraper supports it
        if 'driver' in scraper_params:
            args["driver"] = kwargs.get("driver")

        

        try:
            scrape_func(**args)
            self._log("Scraping completed", output_file=self.ltPath)

            # Translate using database-powered translations (preferred)
            self.translation_handler.translate_to_english(self.ltPath, self.enPath)
            self._log("Translation to English completed", output_file=self.enPath)
        except Exception as e:
            self._log_error("Translation preparation failed", exception=e, brand=self.brandName)
            ErrorManager.show_error("TRANSLATION_FAILED")
            raise

    def translateAll(self):
        """
        Translate Lithuanian file to English
        Uses database-powered translation
        """
        self._log("Starting translation to English")
        try:
            self.translation_handler.translate_to_english(self.ltPath, self.enPath)
            self._log("Translation completed successfully")
        except Exception as e:
            self._log_error("Translation failed", exception=e)
            ErrorManager.show_error("TRANSLATION_FAILED")
            raise

    def loadLT(self):
        """Load Lithuanian translations from file"""
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
        """Load English translations from file"""
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
        """
        Load Latvian translations (uses English as base)
        """
        self._log("Loading Latvian translations (using EN)", file=self.enPath)
        return self.file_handler.read_translated_file(self.enPath)

    def cleanup_generated_files(self) -> None:
        """Delete generated pabaigta*.txt output files for this brand.

        Intended to be called after a successful run when the user enabled
        the corresponding setting.
        """
        for file_path in (self.ltPath, self.enPath):
            try:
                p = Path(file_path)
                if p.exists() and p.is_file():
                    p.unlink()
                    self._log("Deleted generated translation file", file=str(p))
            except Exception as e:
                # Do not fail the whole workflow due to cleanup issues.
                self._log_error("Failed to delete generated translation file", exception=e, file=file_path)
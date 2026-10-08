# Standard library
import inspect
import uuid
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
        self.work_dir = get_data_dir() / "product-runs" / uuid.uuid4().hex
        self.work_dir.mkdir(parents=True, exist_ok=False)
        self.ltPath = str(self.work_dir / "specifications-lt.txt")
        self.enPath = str(self.work_dir / "specifications-en.txt")
        self.translation_handler = TranslationHandler(db_manager)
        self.file_handler = FileHandler()
        self.db = db_manager
        self.raw_source_text = ""
    
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
    
        scraper_params = inspect.signature(scrape_func).parameters
        identifier = next((name for name in ("bicycleUrlOrCode", "url", "target_code")
                           if name in scraper_params), None)
        if identifier is None:
            raise TypeError("Scraper has no supported product identifier parameter")
        args = {identifier: url, "outputFile": self.ltPath}
        if "db_manager" in scraper_params:
            args["db_manager"] = self.db
        for key, value in kwargs.items():
            if key not in scraper_params:
                raise TypeError(f"Scraper does not support option {key!r}")
            args[key] = value
        inspect.signature(scrape_func).bind(**args)
        self.raw_source_text = ""
        for path in (self.ltPath, self.enPath):
            Path(path).unlink(missing_ok=True)
        try:
            scrape_func(**args)
            self.file_handler.read_translated_file(self.ltPath)
            self.raw_source_text = Path(self.ltPath).read_text(encoding="utf-8")
            self._log("Scraping completed", output_file=self.ltPath)

            # Translate using database-powered translations (preferred)
            self.translation_handler.translate_to_english(self.ltPath, self.enPath)
            self.file_handler.read_translated_file(self.enPath)
            self._log("Translation to English completed", output_file=self.enPath)
        except Exception as e:
            self.raw_source_text = ""
            for path in (self.ltPath, self.enPath):
                Path(path).unlink(missing_ok=True)
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
            self.file_handler.read_translated_file(self.ltPath)
            Path(self.enPath).unlink(missing_ok=True)
            self.translation_handler.translate_to_english(self.ltPath, self.enPath)
            self.file_handler.read_translated_file(self.enPath)
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
        """Delete this run's generated specification files.

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

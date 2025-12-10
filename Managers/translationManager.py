import inspect
from Utilities.TranslationHandler import TranslationHandler
from Utilities.FileHandler import FileHandler
from Utilities.ErrorManager import ErrorManager

class TranslationManager:
    def __init__(self, brandName, db_manager=None, logger=None):
        self.brandName = brandName
        self.logger = logger
        self.db_manager = db_manager
        
        # Output file paths (still needed for intermediate processing)
        self.ltPath = f"pabaigta{brandName}LT.txt"
        self.enPath = f"pabaigta{brandName}ENG.txt"
        
        # Initialize handlers
        self.translation_handler = TranslationHandler(db_manager)
        self.file_handler = FileHandler()
    
    def _log(self, message, **context):
        if self.logger:
            self.logger.log("TranslationManager", message, **context)
    
    def _log_error(self, message, exception=None, **context):
        if self.logger:
            self.logger.error("TranslationManager", message, exception=exception, **context)
    
    def prepareTranslationFiles(self, scrape_func, url, **kwargs):
        """
        Run scraper and prepare translation files
        
        Args:
            scrape_func: Scraper function to call
            url: URL or code to scrape
            **kwargs: Additional parameters for scraper (driver, frameset_only, etc.)
        """
        self._log("Preparing translation files", brand=self.brandName, url=url)
        
        # Build arguments for scraper
        args = {
            "bicycleUrlOrCode": url,
            "outputFile": self.ltPath
        }
        
        # Add any extra parameters the scraper accepts
        scraper_params = inspect.signature(scrape_func).parameters
        
        for key, value in kwargs.items():
            if key in scraper_params:
                args[key] = value
        
        try:
            # Run scraper
            result = scrape_func(**args)
            self._log("Scraping completed", output_file=self.ltPath, result=result)
            
            # Translate to English
            self.translation_handler.translate_to_english(self.ltPath, self.enPath)
            self._log("Translation to English completed", output_file=self.enPath)
            
        except FileNotFoundError as e:
            self._log_error("Translation file not found", exception=e)
            ErrorManager.show_error("TRANSLATION_FILE_NOT_FOUND", file_path=str(e))
            raise
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
from Uploaders.baseUploader import ProductUploader
from Scrapers.PinarelloScraper import scrapeAndTranslateToFilePinarello

class Pinarello(ProductUploader):
    def scrape(self):
        # Get frameset choice
        # For now, prompt user (CLI mode)
        # Later in GUI, this will come from checkbox
        frameset_only = self._get_frameset_choice()
        
        # Pass parameter to scraper
        self.translationManager.prepareTranslationFiles(
            scrape_func=scrapeAndTranslateToFilePinarello,
            url=self.bicycleUrlOrCode,
            frameset_only=frameset_only  # ← New parameter
        )

    def _get_frameset_choice(self):
        """
        Get user's choice for frameset vs full bike
        CLI mode: Prompts user
        GUI mode: Will be overridden to use checkbox value
        """
        print("\nPinarello scraper options:")
        print("1. Frameset only (Frame, Fork, Seatpost, Seat Clamp)")
        print("2. Full bike (all components)")
        
        while True:
            choice = input("Pasirinkite (1/2): ").strip()
            if choice == "1":
                return True  # Frameset only
            elif choice == "2":
                return False  # Full bike
            else:
                print("Neteisingas pasirinkimas. Įveskite 1 arba 2.")
    
    def uploadBrand(self):
        self.web_handler.add_brand_name(self.brandName)

    def uploadDescription(self):
        pass
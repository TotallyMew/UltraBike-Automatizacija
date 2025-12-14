class ErrorManager:
    """Manages user-facing error messages in Lithuanian"""
    
    # Error message templates
    ERRORS = {
        # Scraper errors
        "SCRAPER_PAGE_STRUCTURE_CHANGED": "Svetainės struktūra pasikeitė. Prašome atnaujinti programą.",
        "SCRAPER_URL_INVALID": "Neteisingas URL formatas. Patikrinkite adresą ir bandykite dar kartą.",
        "SCRAPER_WEBSITE_UNREACHABLE": "Svetainė nepasiekiama. Patikrinkite interneto ryšį.",
        "SCRAPER_HTTP_ERROR": "HTTP klaida: {status_code}. Svetainė grąžino klaidą.",
        "SCRAPER_TIMEOUT": "Užklausa baigėsi laiko limitu. Bandykite dar kartą.",
        "SCRAPER_NO_DATA": "Nerasta dviračio informacijos. Patikrinkite ar kodas/URL teisingas.",
        "SCRAPER_LOGIN_REQUIRED": "Reikalingas prisijungimas prie svetainės.",
        
        # Translation errors
        "TRANSLATION_FILE_NOT_FOUND": "Vertimo failas nerastas: {file_path}",
        "TRANSLATION_KEY_MISSING": "Nerasta vertimo rakto: {key}",
        "TRANSLATION_FAILED": "Vertimas nepavyko. Patikrinkite vertimo failus.",
        
        # Upload errors
        "UPLOAD_PRODUCT_NOT_FOUND": "Prekė nerasta su kodu: {code}",
        "UPLOAD_FEATURE_FAILED": "Nepavyko įkelti savybės: {feature}",
        "UPLOAD_IMAGE_FAILED": "Nepavyko įkelti nuotraukų.",
        "UPLOAD_BRAND_FAILED": "Nepavyko pridėti prekės ženklo.",
        "UPLOAD_SAVE_FAILED": "Nepavyko išsaugoti pakeitimų.",
        
        # File system errors
        "FILE_NOT_FOUND": "Failas nerastas: {path}",
        "FILE_PERMISSION_ERROR": "Neturite teisių pasiekti failo: {path}",
        "FILE_CREATE_ERROR": "Nepavyko sukurti failo: {path}",
        "FOLDER_CREATE_ERROR": "Nepavyko sukurti aplanko: {path}",
        
        # Browser errors
        "BROWSER_NOT_FOUND": "Naršyklė nerasta. Įdiekite {browser}.",
        "BROWSER_DRIVER_ERROR": "Naršyklės tvarkyklės klaida.",
        "BROWSER_ELEMENT_NOT_FOUND": "Elementas puslapyje nerastas.",
        "BROWSER_TIMEOUT": "Laukimo laikas baigėsi. Puslapis neatsiliepė.",
        
        # Login errors
        "LOGIN_FAILED": "Prisijungti nepavyko. Patikrinkite prisijungimo duomenis.",
        "LOGIN_TIMEOUT": "Prisijungimo laikas baigėsi.",
        
        # Settings errors
        "SETTINGS_FILE_ERROR": "Nustatymų failo klaida.",
        "SETTINGS_INVALID_PATH": "Neteisingas kelias: {path}",
        
        # Excel errors
        "EXCEL_FILE_NOT_FOUND": "Excel failas nerastas: {path}",
        "EXCEL_SHEET_NOT_FOUND": "Lapas nerastas: {sheet}",
        "EXCEL_READ_ERROR": "Nepavyko perskaityti Excel failo.",
        
        # General errors
        "UNKNOWN_ERROR": "Įvyko nežinoma klaida.",
        "NETWORK_ERROR": "Tinklo klaida. Patikrinkite interneto ryšį.",
        "UNEXPECTED_ERROR": "Netikėta klaida: {error}"
    }
    
    @staticmethod
    def show_error(error_code, **kwargs):
        """Display user-friendly error message"""
        template = ErrorManager.ERRORS.get(error_code, ErrorManager.ERRORS["UNKNOWN_ERROR"])
        message = template.format(**kwargs)
        print(f"\n[ERROR] KLAIDA: {message}\n")
    
    @staticmethod
    def show_warning(message):
        """Display warning message"""
        print(f"\n[WARNING] ISPEJIMAS: {message}\n")
    
    @staticmethod
    def show_info(message):
        """Display info message"""
        print(f"\n[INFO] {message}\n")
    
    @staticmethod
    def show_success(message):
        """Display success message"""
        print(f"\n[OK] {message}\n")
    
    @staticmethod
    def prompt_retry(operation_name="operacija"):
        """Ask user if they want to retry after error"""
        while True:
            response = input(f"Bandyti {operation_name} dar kartą? (T/N): ").strip().lower()
            if response == "t":
                return True
            elif response == "n":
                return False
            else:
                print("Įveskite 'T' arba 'N'.")
    
    @staticmethod
    def prompt_continue():
        """Ask user if they want to continue after error"""
        while True:
            response = input("Ar norite tęsti? (taip/ne): ").strip().lower()
            if response == "taip":
                return True
            elif response == "ne":
                return False
            else:
                print("Įveskite 'taip' arba 'ne'.")
    
    @staticmethod
    def prompt_exit_or_retry():
        """Ask user if they want to exit or retry"""
        while True:
            response = input("(1) Bandyti dar kartą, (2) Išeiti: ").strip()
            if response == "1":
                return "retry"
            elif response == "2":
                return "exit"
            else:
                print("Įveskite '1' arba '2'.")
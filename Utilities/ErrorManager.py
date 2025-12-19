import queue


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
        """Display user-friendly error message (GUI/log only)"""
        # GUI should handle displaying this error
        pass

    @staticmethod
    def show_warning(message):
        """Display warning message (GUI/log only)"""
        pass

    @staticmethod
    def show_info(message):
        """Display info message (GUI/log only)"""
        pass

    @staticmethod
    def show_success(message):
        """Display success message (GUI/log only)"""
        pass
    
    # Queue used to send prompt requests to the GUI. GUI should call `set_prompt_queue(q)` during startup.
    _prompt_queue = None

    @staticmethod
    def set_prompt_queue(q: "queue.Queue"):
        """Register a Queue.Queue instance that GUI will poll for prompt requests.

        Each prompt request is a tuple: (prompt_type, operation_name, response_queue)
        Where `response_queue` is a Queue used by GUI to send back the result.
        """
        ErrorManager._prompt_queue = q

    @staticmethod
    def prompt_retry(operation_name="operacija"):
        """Ask user if they want to retry after error.

        If a GUI prompt queue is registered, this will synchronously wait for the GUI
        to show a dialog and return the user's answer. Otherwise raises RuntimeError.
        """
        if ErrorManager._prompt_queue is None:
            raise RuntimeError("CLI prompts disabled: GUI must handle retry prompts for '" + operation_name + "'.")

        resp_q = queue.Queue()
        ErrorManager._prompt_queue.put(("retry", operation_name, resp_q))
        try:
            return resp_q.get()
        except Exception:
            raise RuntimeError("No GUI response for retry prompt")
    
    @staticmethod
    def prompt_continue():
        """Ask user if they want to continue after error (GUI-backed)."""
        if ErrorManager._prompt_queue is None:
            raise RuntimeError("CLI prompts disabled: GUI must handle continuation prompts.")

        resp_q = queue.Queue()
        ErrorManager._prompt_queue.put(("continue", None, resp_q))
        try:
            return resp_q.get()
        except Exception:
            raise RuntimeError("No GUI response for continue prompt")
    
    @staticmethod
    def prompt_exit_or_retry():
        """Ask user if they want to exit or retry (returns 'retry' or 'exit')."""
        if ErrorManager._prompt_queue is None:
            raise RuntimeError("CLI prompts disabled: GUI must handle exit/retry decisions.")

        resp_q = queue.Queue()
        ErrorManager._prompt_queue.put(("exit_or_retry", None, resp_q))
        try:
            return resp_q.get()
        except Exception:
            raise RuntimeError("No GUI response for exit/retry prompt")
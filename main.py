from Config.LoginConfig.LoginHandler import LoginHandler
from Config.LoginConfig.CredentialManager import CredentialManager
from uploaderFactory import getUploaderClass
from Utilities.ProductNavigationHandler import ProductNavigationHandler
from secondaryInput import process_codes_from_excel
from Config.BrowserConfig.BrowserManager import BrowserManager
from Config.Settings.SettingsManager import SettingsManager
from Utilities.FolderCreator import FolderCreator
from Utilities.SettingsMenu import SettingsMenu
from Utilities.Logger import Logger
from Utilities.ErrorManager import ErrorManager

def main():
    # Initialize logger at program start
    logger = Logger()
    logger.log("Main", "Program started")
    
    try:
        browser_manager = BrowserManager()
        settings_manager = SettingsManager()

        # Setup browser
        browserChoice = input("Pasirinkite naršyklę (Firefox (lėtai veikia!), Chrome, Edge): ")
        logger.log("Main", "Browser selected", browser=browserChoice)
        
        driver = browser_manager.setup_browser(browserChoice)
        
        if driver is None:
            logger.error("Main", "Failed to setup browser", browser=browserChoice)
            ErrorManager.show_error("BROWSER_NOT_FOUND", browser=browserChoice)
            logger.session_end()
            return
        
        logger.log("Main", "Browser setup successful")
        navigation_manager = ProductNavigationHandler(driver, logger)

        credential_manager = CredentialManager()
        login_handler = LoginHandler(driver, credential_manager, logger)
        
        logger.start_operation("Login")
        login_handler.login()
        logger.end_operation("Login", success=True)

        # Check if extended mode is enabled
        extended_mode = settings_manager.is_extended_mode_enabled()
        logger.log("Main", "Extended mode status", enabled=extended_mode)
        
        if extended_mode:
            # Extended mode: prompt for action choice
            print("\n=== Extended Mode Enabled ===")
            while True:
                action = input("Pasirinkite veiksmą: (1) Kurti aplankus, (2) Skraperis: ").strip().lower()
                
                # Check for settings command
                if action == "settings":
                    logger.log("Main", "Opening settings menu")
                    menu = SettingsMenu(settings_manager)
                    menu.display_menu()
                    # Reload extended mode status after settings change
                    extended_mode = settings_manager.is_extended_mode_enabled()
                    continue
                
                if action == "1":
                    # Folder creator mode
                    logger.start_operation("Folder Creator")
                    try:
                        folder_creator = FolderCreator(driver, logger)
                        folder_creator.run()
                        logger.end_operation("Folder Creator", success=True)
                        ErrorManager.show_success("Aplankų kūrimas baigtas!")
                    except Exception as e:
                        logger.end_operation("Folder Creator", success=False)
                        logger.error("Main", "Folder creator failed", exception=e)
                        ErrorManager.show_error("FOLDER_CREATE_ERROR", path=settings_manager.get_repository_path())
                    
                    # Ask if user wants to continue
                    if ErrorManager.prompt_continue():
                        continue
                    else:
                        driver.quit()
                        logger.log("Main", "Program ended by user")
                        logger.session_end()
                        return
                    
                elif action == "2":
                    # Normal scraper mode - break to continue with normal flow
                    logger.log("Main", "Switching to scraper mode")
                    break
                else:
                    ErrorManager.show_warning("Neteisingas pasirinkimas. Įveskite '1', '2', arba 'settings'.")

        # Normal scraper flow (either extended mode option 2, or normal mode)
        while True:
            brandInput = input("Įveskite tiekėją (KROSS, Rondo, Pinarello, Le Grand, Octane, Rascal, Basso, Lee Cougan, Factor) arba 'settings': ").strip()
            
            # Check for settings command
            if brandInput.lower() == "settings":
                logger.log("Main", "Opening settings menu")
                menu = SettingsMenu(settings_manager)
                menu.display_menu()
                continue
            
            logger.log("Main", "Brand selected", brand=brandInput)
            uploaderClass = getUploaderClass(brandInput)

            if uploaderClass is None:
                logger.error("Main", "Invalid brand selected", brand=brandInput)
                ErrorManager.show_error("UNKNOWN_ERROR")
                
                if not ErrorManager.prompt_retry("pasirinkimą"):
                    driver.quit()
                    logger.log("Main", "Program ended by user")
                    logger.session_end()
                    return
                continue

            input_mode = input("Pasirinkite įvedimo būdą: Rankinis (R) arba Excel (E): ").strip().upper()
            logger.log("Main", "Input mode selected", mode=input_mode)

            if input_mode == "R":
                # Manual input loop
                while True:
                    code = input("Įveskite prekės kodą (arba 'exit' išeiti, 'settings' nustatymams): ").strip()
                    
                    # Check for settings command
                    if code.lower() == "settings":
                        logger.log("Main", "Opening settings menu")
                        menu = SettingsMenu(settings_manager)
                        menu.display_menu()
                        continue
                    
                    if code.lower() == 'exit':
                        logger.log("Main", "Exiting manual input mode")
                        break
                    
                    logger.start_operation("Scrape Product", brand=brandInput, code=code)
                    try:
                        uploader = uploaderClass(driver, brandInput.upper(), code, logger)
                        uploader.run()
                        logger.end_operation("Scrape Product", success=True)
                        ErrorManager.show_success("Dviratis sėkmingai apdorotas!")
                    except Exception as e:
                        logger.end_operation("Scrape Product", success=False)
                        logger.error("Main", "Scraping failed", exception=e, brand=brandInput, code=code)
                        ErrorManager.show_error("UNEXPECTED_ERROR", error=str(e))
                        
                        if not ErrorManager.prompt_continue():
                            break

            elif input_mode == "E":
                file_path = "asdasdasdddd.xlsx"  # TODO: Get from settings
                sheet_name = input("Įveskite Excel lapo pavadinimą: ").strip()
                
                logger.start_operation("Excel Import", file=file_path, sheet=sheet_name)
                try:
                    result = process_codes_from_excel(file_path, sheet_name, uploaderClass, driver, brandInput.upper(), logger)
                    logger.end_operation("Excel Import", success=True)
                except FileNotFoundError:
                    logger.end_operation("Excel Import", success=False)
                    logger.error("Main", "Excel file not found", file=file_path)
                    ErrorManager.show_error("EXCEL_FILE_NOT_FOUND", path=file_path)
                except Exception as e:
                    logger.end_operation("Excel Import", success=False)
                    logger.error("Main", "Excel import failed", exception=e)
                    ErrorManager.show_error("EXCEL_READ_ERROR")

            else:
                ErrorManager.show_warning("Neteisingas įvedimo būdas. Bandykite dar kartą.")
                continue

            while True:
                continueInput = input("Darbas baigtas. Ar norite tęsti? (taip/ne/settings): ").lower()
                
                # Check for settings command
                if continueInput == "settings":
                    logger.log("Main", "Opening settings menu")
                    menu = SettingsMenu(settings_manager)
                    menu.display_menu()
                    continue
                
                if continueInput == "taip":
                    logger.log("Main", "User chose to continue")
                    navigation_manager.fix_invisible_products()
                    break
                elif continueInput == "ne":
                    driver.quit()
                    logger.log("Main", "Program ended by user")
                    logger.session_end()
                    return
                else:
                    ErrorManager.show_warning("Prašome įvesti 'taip', 'ne', arba 'settings'.")
    
    except KeyboardInterrupt:
        logger.log("Main", "Program interrupted by user (Ctrl+C)")
        ErrorManager.show_warning("Programa nutraukta vartotojo.")
        logger.session_end()
    
    except Exception as e:
        logger.error("Main", "Unexpected fatal error", exception=e)
        ErrorManager.show_error("UNEXPECTED_ERROR", error=str(e))
        logger.session_end()

if __name__ == "__main__":
    main()
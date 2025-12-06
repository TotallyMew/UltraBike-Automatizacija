from Config.LoginConfig.LoginHandler import LoginHandler
from Config.LoginConfig.CredentialManager import CredentialManager
from uploaderFactory import getUploaderClass
from Utilities.ProductNavigationHandler import ProductNavigationHandler
from secondaryInput import process_codes_from_excel
from Config.BrowserConfig.BrowserManager import BrowserManager
from Config.Settings.SettingsManager import SettingsManager
from Utilities.FolderCreator import FolderCreator

def main():
    browser_manager = BrowserManager()
    settings_manager = SettingsManager()

    # Setup browser
    browserChoice = input("Pasirinkite naršyklę (Firefox (lėtai veikia!), Chrome, Edge): ")
    driver = browser_manager.setup_browser(browserChoice)
    navigation_manager = ProductNavigationHandler(driver)

    credential_manager = CredentialManager()
    login_handler = LoginHandler(driver, credential_manager)
    login_handler.login()

    # Check if extended mode is enabled
    extended_mode = settings_manager.is_extended_mode_enabled()
    
    if extended_mode:
        # Extended mode: prompt for action choice
        print("\n=== Extended Mode Enabled ===")
        while True:
            action = input("Pasirinkite veiksmą: (1) Kurti aplankus, (2) Skraperis: ").strip()
            
            if action == "1":
                # Folder creator mode
                folder_creator = FolderCreator(driver)
                folder_creator.run()
                
                # Ask if user wants to continue
                continue_input = input("\nAr norite tęsti? (taip/ne): ").lower()
                if continue_input == "ne":
                    driver.quit()
                    print("Darbas baigtas.")
                    return
                continue
                
            elif action == "2":
                # Normal scraper mode - break to continue with normal flow
                break
            else:
                print("Neteisingas pasirinkimas. Įveskite '1' arba '2'.")

    # Normal scraper flow (either extended mode option 2, or normal mode)
    while True:
        brandInput = input("Įveskite tiekėją (KROSS, Rondo, Pinarello, Le Grand, Octane, Rascal, Basso, Lee Cougan, Factor): ").strip()
        uploaderClass = getUploaderClass(brandInput)

        if uploaderClass is None:
            retry = input("Neteisingas įvedimas. Ar norite bandyti dar kartą? (T/N): ").lower()
            if retry != "t":
                driver.quit()
                return
            continue

        input_mode = input("Pasirinkite įvedimo būdą: Rankinis (R) arba Excel (E): ").strip().upper()

        if input_mode == "R":
            # Manual input loop
            while True:
                code = input("Įveskite prekės kodą (arba 'exit' išeiti): ").strip()
                if code.lower() == 'exit':
                    break
                uploader = uploaderClass(driver, brandInput.upper(), code)
                uploader.run()

        elif input_mode == "E":
            file_path = "asdasdasdddd.xlsx" #is settings.txt paskui padaryt
            sheet_name = input("Įveskite Excel lapo pavadinimą: ").strip()
            result = process_codes_from_excel(file_path, sheet_name, uploaderClass, driver, brandInput.upper())

        else:
            print("Neteisingas įvedimo būdas. Bandykite dar kartą.")
            continue

        while True:
            continueInput = input("Darbas baigtas. Ar norite tęsti? (taip/ne): ").lower()
            if continueInput == "taip":
                navigation_manager.fix_invisible_products()
                break
            elif continueInput == "ne":
                driver.quit()
                print("Darbas baigtas.")
                return
            else:
                print("Prašome įvesti 'taip' arba 'ne'.")

if __name__ == "__main__":
    main()
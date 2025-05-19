from Config.config import read_settings, resource_path, setupBrowser
from Config.configLogin import login
from uploaderFactory import getUploaderClass
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from generalUtilities import perSkydeliPrekesNematomos

def main():
    read_settings(resource_path("settings.txt"))
    
    browserChoice = input("Pasirinkite naršyklę (Firefox (lėtai veikia!), Chrome, Edge): ")
    driver = setupBrowser(browserChoice)
    login(driver)

    while True:
        brandInput = input("Įveskite tiekėją (KROSS, Rondo, Pinarello, Le Grand, Octane, Rascal, Basso, Lee Cougan): ").strip()
        uploaderClass = getUploaderClass(brandInput)

        if uploaderClass is None:
            retry = input("Neteisingas įvedimas. Ar norite bandyti dar kartą? (T/N): ").lower()
            if retry != "t":
                driver.quit()
                return
            continue

        uploader = uploaderClass(driver, brandInput.upper())
        uploader.run()

        while True:
            continueInput = input("Darbas baigtas. Ar norite tęsti? (taip/ne): ").lower()
            if continueInput == "taip":
                try:
                    WebDriverWait(driver, 1).until(
                        EC.element_to_be_clickable((By.ID, "subtab-AdminProducts"))
                    ).click()
                except TimeoutException:
                    perSkydeliPrekesNematomos(driver)
                break
            elif continueInput == "ne":
                driver.quit()
                print("Darbas baigtas.")
                return
            else:
                print("Prašome įvesti 'taip' arba 'ne'.")

if __name__ == "__main__":
    main()


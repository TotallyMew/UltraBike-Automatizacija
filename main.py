from KROSS import mainKrossFunction
from Rondo import mainRondoFunction
from Pinarello import mainPinarelloFunction
from octane import mainOctaneFunction
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from generalUtilities import perSkydeliPrekesNematomos
from config import setupBrowser
from selenium.webdriver.common.by import By
from config import read_settings, settings, resource_path
from configLogin import login
from rascal import mainRascalFunction

def prekesVedimas(driver):
    while True:
        preke = input("Įveskite tiekėja (KROSS, Rondo, Pinarello, Le Grand, Octane, Rascal): ")
        
        if preke.lower() == "kross" or preke.lower() == "le grand":
            mainKrossFunction(driver, preke.upper())
            break
        elif preke.lower() == "rondo":
            mainRondoFunction(driver, preke.upper())
            break
        elif preke.lower() == "pinarello":
            mainPinarelloFunction(driver, preke.title())
            break
        elif preke.lower() == "octane":
            mainOctaneFunction(driver, preke.title())
            break
        elif preke.lower() == "rascal":
            mainRascalFunction(driver, preke.title())
            break
        else:
            while True:
                retry = input("Neteisingas įvedimas. Ar norite bandyti dar kartą? (T/N): ")
                if retry.lower() == "t":
                    break
                elif retry.lower() == "n":
                    print("Darbas baigiamas")
                    driver.quit()
                    exit()
                else:
                    print("Prašome įvesti T arba N")
                    
def main():

    global settings

    read_settings(resource_path("settings.txt"))
    
    browser_choice = input(
        "Pasirinkite naršyklę (Firefox (lėtai veikia!), Chrome, Edge):  "
    )

    driver = setupBrowser(browser_choice)

    login(driver)

    while True:
        prekesVedimas(driver)

        while True:
            testiDarba = input(
                "Darbas baigtas (pasitikrinkit ar išsaugojot), ar norite tęsti? (taip/ne): "
            )
            if testiDarba.lower() == "taip":
                try:
                    prekesMygtukas = WebDriverWait(driver, 1).until(EC.element_to_be_clickable((By.ID, "subtab-AdminProducts")))
                    prekesMygtukas.click()
                except TimeoutException:      
                    perSkydeliPrekesNematomos(driver)
                break  
            elif testiDarba.lower() == "ne":
                break 
            else:
                print("Prašome įvesti 'taip' arba 'ne'.")

        if testiDarba.lower() == "ne":
            break  


    driver.quit()
    print("Darbas baigtas.")


if __name__ == "__main__":
    main()


import os
import sys
import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from selenium.webdriver.common.by import By



def check_internet(url='http://www.google.com'):
    try:
        requests.get(url, timeout=5)
        return True
    except requests.ConnectionError:
        return False

settings = []

def read_settings(file_path):
    global settings  # Declare that we are using the global settings variable
    try:
        with open(file_path, 'r') as file:
            for line in file:
                stripped_line = line.strip()
                if stripped_line.lower() == 'true':
                    settings.append(True)
                elif stripped_line.lower() == 'false':
                    settings.append(False)
                else:
                    settings.append(stripped_line)    
    except FileNotFoundError:
        print(f"Error: The file at {file_path} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")
        
def resizeWindow(driver, element_id, max_width, max_height):
    try:
        element = driver.find_element(By.ID, element_id)  # Find the element

        # Get the size of the element
        element_size = element.size
        current_width = element_size['width']
        current_height = element_size['height']

        # Get current window size
        window_size = driver.get_window_size()
        window_width = window_size['width']
        window_height = window_size['height']

        # Calculate the necessary window size adjustments
        if current_width < max_width or current_height < max_height:
            new_width = int(window_width * (max_width / current_width)) if current_width > max_width else window_width
            new_height = int(window_height * (max_height / current_height)) if current_height > max_height else window_height

            driver.set_window_size(new_width, new_height)
            time.sleep(1)  # Wait for the window to resize

            # Verify the size of the element again after resizing
            element_size = element.size
            current_width = element_size['width']
            current_height = element_size['height']


    except Exception as e:
        print(f"An error occurred: {e}")
 
def resource_path(relative_path):

    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def setupBrowser(browser_choice):
    while True:
        if check_internet():
            try:
                if browser_choice.lower() == "chrome":
                    options = ChromeOptions()
                    options.add_experimental_option('excludeSwitches', ['enable-logging'])
                    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
                    # print(f"ChromeDriver path: {ChromeDriverManager().install()}")
                    return driver
                elif browser_choice.lower() == "firefox":
                    options = FirefoxOptions()
                    options.set_preference('browser.log.file', '/dev/null')
                    return webdriver.Firefox(service=FirefoxService(GeckoDriverManager().install()), options=options)
                elif browser_choice.lower() == "edge":
                    options = EdgeOptions()
                    options.use_chromium = True
                    options.add_experimental_option('excludeSwitches', ['enable-logging'])
                    return webdriver.Edge(service=EdgeService(EdgeChromiumDriverManager().install()), options=options)
                else:
                    print("Įvesta nepalaikoma naršyklė.")
                    while True:
                        retry = input("Ar norite bandyti vėl? (T/N): ").strip().lower()
                        if retry.lower() == 't':
                            browser_choice = input("Pasirinkite naršyklę (Firefox (lėtai veikia!), Chrome, Edge):").strip()
                            break
                        elif retry.lower() == 'n':
                            print("Darbas baigiamas")
                            exit()
                        else:
                            print("Prašome įvesti T arba N.")
                            
            except Exception as e:
                print(f"An error occurred: {e}")
                print("Darbas baigiamas, nerasta naršyklė.")
                exit()
        else:
            print("Jūs nesate prisijungęs prie interneto, ar norite bandyti vėl (T/N)?? ")
            answer = input().strip().lower()
            if answer != 't':
                print("Darbas baigiamas")
                return None

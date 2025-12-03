# Standard library imports
import os
import time
from urllib.parse import urlparse, urljoin

# Third-party imports
import requests
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from pywinauto.application import Application
from pywinauto.keyboard import send_keys

# Local application imports
from Config.Settings.SettingsManager import SettingsManager
from Config.BrowserConfig.WindowManager import WindowManager
from Utilities.FileHandler import FileHandler


class ImageHandler:
    def __init__(self, settings_manager):
        # Use the passed settings_manager instead of creating a new one
        self.settings_manager = settings_manager
        self.window_manager = WindowManager()

    def download_kross_images(self, url, driver):
        download_path = self._construct_directory(driver)

        try:
            response = requests.get(url)
            response.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"Klaida gaunant puslapio turinį: {e}")

        soup = BeautifulSoup(response.content, 'html.parser')
        image_elements = soup.select('a.orbitvu-gallery-item-link')

        if not image_elements:
            raise ValueError("Nuotraukos nerastos pateiktame tinklapyje")

        for element in image_elements:
            img_url = element.get('data-big_src')
            if not img_url:
                continue
            
            img_url = urljoin(url, img_url)
            img_name = os.path.basename(urlparse(img_url).path)

            if img_name.lower() == 'view.png':
                continue

            try:
                img_response = requests.get(img_url)
                img_response.raise_for_status()
            except requests.RequestException as e:
                print(f"Klaida siunčiant nuotrauką {img_url}: {e}")
                continue

            img_path = os.path.join(download_path, img_name)
            with open(img_path, 'wb') as img_file:
                img_file.write(img_response.content)

        print('Nuotraukos parsiųstos.')

    def upload_kross_images(self, driver):
        self.window_manager.resize_window(driver, 'add_feature_button', 160.07, 39.14)
        try:
            element = driver.find_element(By.CLASS_NAME, 'dz-preview.disabled.openfilemanager.dz-clickable')
            if element.is_displayed() and element.is_enabled():
                print("Nuotraukų jau yra sukelta, naujos nuotraukos nebus keliamos.")
                return
        except NoSuchElementException:
            print('Element not found, continuing with regular code')

        try:
            download_path = self._construct_directory(driver)
            upload_button = driver.find_element(By.ID, 'product-images-dropzone')
            driver.execute_script("arguments[0].scrollIntoView();", upload_button)
            upload_button.click()
            time.sleep(2)

            app = Application().connect(title_re='Open') 
            dialog = app.window(title_re='Open') 
            dialog['Edit'].set_text(download_path) 
            send_keys("{ENTER}")
            time.sleep(1) 

            tree_view = dialog.TreeView
            tree_view.set_focus()
            send_keys('^a') 
            time.sleep(1)
            send_keys('{ENTER}')

            print("Nuotraukos sukeltos.")
        except Exception as e:
            print(f"Error: {e}")

    def _construct_directory(self, driver):
        input_element = driver.find_element(By.ID, 'form_step1_name_2')
        value = input_element.get_attribute('value')
        base_directory = self.settings_manager.get_kross_path()
        sanitized_value = FileHandler.sanitize_filename(value)
        download_directory = os.path.join(base_directory, sanitized_value)
        os.makedirs(download_directory, exist_ok=True)
        return download_directory
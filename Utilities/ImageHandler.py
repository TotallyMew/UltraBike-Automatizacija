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
from Config.BrowserConfig.WindowManager import WindowManager
from Utilities.FileHandler import FileHandler
from Utilities.ErrorManager import ErrorManager


class ImageHandler:
    def __init__(self, settings_manager, logger=None):
        self.settings_manager = settings_manager
        self.logger = logger
        self.window_manager = WindowManager()
    
    def _log(self, message, **context):
        if self.logger:
            self.logger.log("ImageHandler", message, **context)
    
    def _log_error(self, message, exception=None, **context):
        if self.logger:
            self.logger.error("ImageHandler", message, exception=exception, **context)

    def download_kross_images(self, url, driver):
        self._log("Starting KROSS image download", url=url)
        download_path = self._construct_directory(driver)

        try:
            response = requests.get(url)
            response.raise_for_status()
        except requests.RequestException as e:
            self._log_error("Failed to fetch page", exception=e, url=url)
            ErrorManager.show_error("SCRAPER_WEBSITE_UNREACHABLE")
            raise RuntimeError(f"Klaida gaunant puslapio turinį: {e}")

        soup = BeautifulSoup(response.content, 'html.parser')
        image_elements = soup.select('a.orbitvu-gallery-item-link')

        if not image_elements:
            self._log_error("No images found on page", url=url)
            ErrorManager.show_error("SCRAPER_NO_DATA")
            raise ValueError("Nuotraukos nerastos pateiktame tinklapyje")

        downloaded_count = 0
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
                self._log_error("Failed to download image", exception=e, url=img_url)
                continue

            img_path = os.path.join(download_path, img_name)
            with open(img_path, 'wb') as img_file:
                img_file.write(img_response.content)
            downloaded_count += 1

        self._log("Images downloaded successfully", count=downloaded_count, path=download_path)
        ErrorManager.show_success(f"Parsiųsta {downloaded_count} nuotraukų")

    def upload_kross_images(self, driver):
        self._log("Starting KROSS image upload")
        self.window_manager.resize_window(driver, 'add_feature_button', 160.07, 39.14)
        
        try:
            element = driver.find_element(By.CLASS_NAME, 'dz-preview.disabled.openfilemanager.dz-clickable')
            if element.is_displayed() and element.is_enabled():
                self._log("Images already uploaded, skipping")
                ErrorManager.show_warning("Nuotraukų jau yra sukelta, naujos nuotraukos nebus keliamos.")
                return
        except NoSuchElementException:
            self._log("No existing images found, proceeding with upload")

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

            self._log("Images uploaded successfully")
            ErrorManager.show_success("Nuotraukos sukeltos!")
        except Exception as e:
            self._log_error("Image upload failed", exception=e)
            ErrorManager.show_error("UPLOAD_IMAGE_FAILED")
            raise

    def _construct_directory(self, driver):
        input_element = driver.find_element(By.ID, 'form_step1_name_2')
        value = input_element.get_attribute('value')
        base_directory = self.settings_manager.get_kross_path()
        sanitized_value = FileHandler.sanitize_filename(value)
        download_directory = os.path.join(base_directory, sanitized_value)
        os.makedirs(download_directory, exist_ok=True)
        return download_directory
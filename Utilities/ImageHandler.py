import os
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from Utilities.ErrorManager import ErrorManager
from Utilities.FileHandler import FileHandler


class ImageHandler:
    """Download supplier images and expose local paths to the PIMBO editor."""

    def __init__(self, settings_manager, logger=None):
        self.settings_manager = settings_manager
        self.logger = logger

    def _log(self, message, **context):
        if self.logger:
            self.logger.log("ImageHandler", message, **context)

    def _log_error(self, message, exception=None, **context):
        if self.logger:
            self.logger.error("ImageHandler", message, exception=exception, **context)

    def download_kross_images(self, url, product_code):
        """Download KROSS images and return their local paths."""

        self._log("Starting KROSS image download", url=url)
        download_path = self._construct_directory(product_code)
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as error:
            self._log_error("Failed to fetch page", exception=error, url=url)
            ErrorManager.show_error("SCRAPER_WEBSITE_UNREACHABLE")
            raise RuntimeError(f"Klaida gaunant puslapio turinį: {error}") from error

        soup = BeautifulSoup(response.content, "html.parser")
        image_elements = soup.select("a.orbitvu-gallery-item-link")
        if not image_elements:
            ErrorManager.show_error("SCRAPER_NO_DATA")
            raise ValueError("Nuotraukos nerastos pateiktame tinklapyje")

        downloaded = 0
        for element in image_elements:
            image_url = element.get("data-big_src")
            if not image_url:
                continue
            image_url = urljoin(url, image_url)
            image_name = os.path.basename(urlparse(image_url).path)
            if image_name.casefold() == "view.png":
                continue
            try:
                image_response = requests.get(image_url, timeout=30)
                image_response.raise_for_status()
                image_path = os.path.join(download_path, image_name)
                with open(image_path, "wb") as image_file:
                    image_file.write(image_response.content)
                downloaded += 1
            except requests.RequestException as error:
                self._log_error(
                    "Failed to download image",
                    exception=error,
                    url=image_url,
                )

        self._log("Images downloaded", count=downloaded, path=download_path)
        ErrorManager.show_success(f"Parsisiųsta {downloaded} nuotraukų")
        return self.kross_image_paths(product_code)

    def kross_image_paths(self, product_code):
        """Return downloaded image paths without interacting with PIMBO."""

        download_path = self._construct_directory(product_code)
        return sorted(
            os.path.join(download_path, name)
            for name in os.listdir(download_path)
            if name.casefold().endswith((".jpg", ".jpeg", ".png", ".webp"))
        )

    def _construct_directory(self, product_code):
        base_directory = self.settings_manager.get_kross_path()
        sanitized_value = FileHandler.sanitize_filename(str(product_code or ""))
        download_directory = os.path.join(base_directory, sanitized_value)
        os.makedirs(download_directory, exist_ok=True)
        return download_directory

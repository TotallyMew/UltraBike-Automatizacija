import os
import tempfile
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image
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
        download_path = Path(tempfile.mkdtemp(prefix="run-", dir=self._construct_directory(product_code)))
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

        paths = []
        failures = []
        seen = set()
        for element in image_elements:
            image_url = element.get("data-big_src")
            if not image_url:
                continue
            image_url = urljoin(url, image_url)
            if image_url in seen:
                continue
            seen.add(image_url)
            image_name = os.path.basename(urlparse(image_url).path)
            if image_name.casefold() == "view.png":
                continue
            try:
                image_response = requests.get(image_url, timeout=30)
                image_response.raise_for_status()
                with Image.open(BytesIO(image_response.content)) as picture:
                    picture.verify()
                safe_name = FileHandler.sanitize_filename(image_name)
                if not safe_name or Path(safe_name).suffix.casefold() not in {".jpg", ".jpeg", ".png", ".webp"}:
                    safe_name = "image.png"
                image_path = download_path / f"{len(paths) + 1:03}-{safe_name}"
                image_path.write_bytes(image_response.content)
                paths.append(str(image_path))
            except (requests.RequestException, OSError, ValueError) as error:
                failures.append(str(error))
                self._log_error(
                    "Failed to download image",
                    exception=error,
                    url=image_url,
                )

        if failures or not paths:
            raise RuntimeError(f"KROSS image download incomplete: {len(paths)} downloaded, {len(failures)} failed; review the source images")
        self._log("Images downloaded", count=len(paths), path=str(download_path))
        return paths

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
        if not sanitized_value or sanitized_value in {".", ".."}:
            raise ValueError("A valid product code is required for image download")
        download_directory = os.path.join(base_directory, sanitized_value)
        os.makedirs(download_directory, exist_ok=True)
        return download_directory

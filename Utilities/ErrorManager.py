"""Thread-safe user notifications and GUI-backed retry prompts."""

from __future__ import annotations

import queue
from typing import Callable


class ErrorManager:
    """Bridge legacy worker notifications into the Qt event loop and log."""

    _FALLBACK_ERRORS = {
        "SCRAPER_PAGE_STRUCTURE_CHANGED": "The website structure changed. Update the app and try again.",
        "SCRAPER_URL_INVALID": "The URL is invalid. Check it and try again.",
        "SCRAPER_WEBSITE_UNREACHABLE": "The website is unavailable. Check your internet connection.",
        "SCRAPER_HTTP_ERROR": "The website returned HTTP {status_code}.",
        "SCRAPER_TIMEOUT": "The website did not respond in time.",
        "SCRAPER_NO_DATA": "No product information was found.",
        "SCRAPER_LOGIN_REQUIRED": "The website requires a login.",
        "TRANSLATION_FILE_NOT_FOUND": "Translation file not found: {file_path}",
        "TRANSLATION_KEY_MISSING": "Translation key not found: {key}",
        "TRANSLATION_FAILED": "The local translation step failed.",
        "UPLOAD_PRODUCT_NOT_FOUND": "Product not found: {code}",
        "UPLOAD_FEATURE_FAILED": "Could not upload feature: {feature}",
        "UPLOAD_IMAGE_FAILED": "Could not upload the images.",
        "UPLOAD_BRAND_FAILED": "Could not set the brand.",
        "UPLOAD_SAVE_FAILED": "Could not save the changes.",
        "FILE_NOT_FOUND": "File not found: {path}",
        "FILE_FORMAT_ERROR": "Unsupported file entry: {line}",
        "FILE_PERMISSION_ERROR": "Permission denied: {path}",
        "FILE_CREATE_ERROR": "Could not create file: {path}",
        "FOLDER_CREATE_ERROR": "Could not create folder: {path}",
        "BROWSER_NOT_FOUND": "Browser not found: {browser}",
        "BROWSER_DRIVER_ERROR": "The browser driver could not be started.",
        "BROWSER_ELEMENT_NOT_FOUND": "The required page element was not found.",
        "BROWSER_TIMEOUT": "The browser operation timed out.",
        "LOGIN_FAILED": "Login failed. Check the saved credentials.",
        "LOGIN_TIMEOUT": "Login timed out.",
        "SETTINGS_FILE_ERROR": "The settings could not be loaded.",
        "SETTINGS_INVALID_PATH": "Invalid path: {path}",
        "EXCEL_FILE_NOT_FOUND": "Excel file not found: {path}",
        "EXCEL_SHEET_NOT_FOUND": "Excel sheet not found: {sheet}",
        "EXCEL_READ_ERROR": "The Excel workbook could not be read.",
        "UNKNOWN_ERROR": "An unknown error occurred.",
        "NETWORK_ERROR": "A network error occurred. Check the connection.",
        "UNEXPECTED_ERROR": "Unexpected error: {error}",
    }

    _prompt_queue: queue.Queue | None = None
    _notification_queue: queue.Queue | None = None
    _logger = None
    _translator: Callable[..., str] | None = None

    @classmethod
    def configure(cls, notification_queue=None, logger=None, translator=None) -> None:
        cls._notification_queue = notification_queue
        cls._logger = logger
        cls._translator = translator

    @classmethod
    def set_prompt_queue(cls, prompt_queue: queue.Queue) -> None:
        cls._prompt_queue = prompt_queue

    @classmethod
    def _format_error(cls, error_code: str, **kwargs) -> str:
        key = f"error.{error_code}"
        if cls._translator is not None:
            try:
                translated = cls._translator(key, **kwargs)
                if translated != key:
                    return translated
            except Exception:
                pass
        template = cls._FALLBACK_ERRORS.get(error_code, cls._FALLBACK_ERRORS["UNKNOWN_ERROR"])
        try:
            return template.format(**kwargs)
        except (KeyError, ValueError, IndexError):
            return template

    @classmethod
    def _notify(cls, level: str, message: str, *, code: str = "") -> str:
        text = str(message or "").strip() or cls._FALLBACK_ERRORS["UNKNOWN_ERROR"]
        logger = cls._logger
        if logger is not None:
            try:
                if level == "error":
                    logger.error("Notification", text, code=code)
                else:
                    logger.log("Notification", text, level=level, code=code)
            except Exception:
                pass
        if cls._notification_queue is not None:
            cls._notification_queue.put(("notification", level, text, code))
        return text

    @classmethod
    def show_error(cls, error_code, **kwargs):
        return cls._notify("error", cls._format_error(str(error_code), **kwargs), code=str(error_code))

    @classmethod
    def show_warning(cls, message):
        return cls._notify("warning", str(message))

    @classmethod
    def show_info(cls, message):
        return cls._notify("info", str(message))

    @classmethod
    def show_success(cls, message):
        return cls._notify("success", str(message))

    @classmethod
    def prompt_retry(cls, operation_name="operation"):
        if cls._prompt_queue is None:
            raise RuntimeError(f"GUI retry prompt is unavailable for {operation_name!r}")
        response = queue.Queue()
        cls._prompt_queue.put(("retry", operation_name, response))
        return response.get()

    @classmethod
    def prompt_continue(cls):
        if cls._prompt_queue is None:
            raise RuntimeError("GUI continuation prompt is unavailable")
        response = queue.Queue()
        cls._prompt_queue.put(("continue", None, response))
        return response.get()

    @classmethod
    def prompt_exit_or_retry(cls):
        if cls._prompt_queue is None:
            raise RuntimeError("GUI exit/retry prompt is unavailable")
        response = queue.Queue()
        cls._prompt_queue.put(("exit_or_retry", None, response))
        return response.get()

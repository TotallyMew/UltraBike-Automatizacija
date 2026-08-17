import ipaddress
import re
from urllib.parse import urlsplit

import requests

class URLHandler:
    @staticmethod
    def normalize_url(url: str) -> str:
        """Return a trimmed HTTP(S) URL, defaulting bare hosts to HTTPS."""
        value = str(url or "").strip()
        if value and "://" not in value:
            return f"https://{value}"
        return value

    @staticmethod
    def is_valid_url(url):
        value = str(url or "").strip()
        if not value or re.search(r"\s", value):
            return False
        candidate = URLHandler.normalize_url(value)
        try:
            parsed = urlsplit(candidate)
            if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
                return False
            if parsed.username is not None or parsed.password is not None:
                return False
            if parsed.port is not None and not 1 <= parsed.port <= 65535:
                return False

            host = parsed.hostname.rstrip(".")
            try:
                ipaddress.ip_address(host)
                return True
            except ValueError:
                pass

            ascii_host = host.encode("idna").decode("ascii")
            labels = ascii_host.split(".")
            if len(labels) < 2:
                return False
            return all(
                label
                and len(label) <= 63
                and not label.startswith("-")
                and not label.endswith("-")
                and re.fullmatch(r"[A-Za-z0-9-]+", label)
                for label in labels
            )
        except (UnicodeError, ValueError):
            return False

    @staticmethod
    def is_website_accessible(url):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
        }
        try:
            value = str(url or "").strip()
            if not URLHandler.is_valid_url(value):
                return False
            target = URLHandler.normalize_url(value)
            with requests.get(target, headers=headers, timeout=5, stream=True) as response:
                return 200 <= response.status_code < 400
        except requests.RequestException:
            return False


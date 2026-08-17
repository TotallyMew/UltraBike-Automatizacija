import os
import unittest
from unittest.mock import patch

from Utilities.Updater import download_to_temp, fetch_update_manifest
from Utilities.URLHandler import URLHandler


class _Response:
    def __init__(self, *, url="https://updates.example/app.exe", payload=b"data", manifest=None):
        self.url = url
        self.headers = {"Content-Length": str(len(payload))}
        self._payload = payload
        self._manifest = manifest or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def raise_for_status(self):
        return None

    def json(self):
        return self._manifest

    def iter_content(self, chunk_size):
        yield self._payload


class NetworkSafetyTest(unittest.TestCase):
    def test_url_validation_rejects_ambiguous_or_credentialed_urls(self):
        self.assertTrue(URLHandler.is_valid_url("example.com/product"))
        self.assertTrue(URLHandler.is_valid_url("https://sub.example.com:8443/item"))
        self.assertFalse(URLHandler.is_valid_url("javascript:alert(1)"))
        self.assertFalse(URLHandler.is_valid_url("https://user:secret@example.com"))
        self.assertFalse(URLHandler.is_valid_url("https://example.com/a b"))
        self.assertFalse(URLHandler.is_valid_url("localhost"))

    def test_manifest_requires_https_and_a_sha256_digest(self):
        with self.assertRaises(ValueError):
            fetch_update_manifest("http://updates.example/latest.json")

        response = _Response(
            manifest={"version": "2.0", "url": "https://updates.example/app.exe"}
        )
        with patch("Utilities.Updater.requests.get", return_value=response):
            with self.assertRaises(ValueError):
                fetch_update_manifest("https://updates.example/latest.json")

    def test_manifest_rejects_https_to_http_redirect(self):
        response = _Response(
            url="http://updates.example/latest.json",
            manifest={
                "version": "2.0",
                "url": "https://updates.example/app.exe",
                "sha256": "a" * 64,
            },
        )
        with patch("Utilities.Updater.requests.get", return_value=response):
            with self.assertRaises(ValueError):
                fetch_update_manifest("https://updates.example/latest.json")

    def test_update_download_uses_unique_exclusive_temp_files(self):
        paths = []
        try:
            with patch("Utilities.Updater.requests.get", return_value=_Response(payload=b"installer")):
                paths.append(download_to_temp("https://updates.example/app.exe", "setup.exe"))
                paths.append(download_to_temp("https://updates.example/app.exe", "setup.exe"))

            self.assertNotEqual(paths[0], paths[1])
            for path in paths:
                with open(path, "rb") as handle:
                    self.assertEqual(handle.read(), b"installer")
        finally:
            for path in paths:
                try:
                    os.remove(path)
                except OSError:
                    pass


if __name__ == "__main__":
    unittest.main()

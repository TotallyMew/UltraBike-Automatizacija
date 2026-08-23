"""Non-blocking Spotify authentication and API calls for the Qt UI."""

from __future__ import annotations

import html
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QThread, Signal


class SpotifyCallWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self.callback = callback

    def run(self) -> None:
        try:
            result = self.callback()
        except Exception as error:
            self.failed.emit(str(error))
        else:
            self.succeeded.emit(result)


class SpotifyAuthWorker(QThread):
    """Wait for Spotify's loopback OAuth callback without blocking Qt."""

    browser_url = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, spotify_manager, parent=None, timeout_seconds: int = 300):
        super().__init__(parent)
        self.spotify = spotify_manager
        self.timeout_seconds = max(30, int(timeout_seconds))
        self._server = None

    def request_stop(self) -> None:
        self.requestInterruption()

    def run(self) -> None:
        authorization = None
        result: dict[str, str] = {}
        worker = self

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - standard-library callback name
                parsed = urlparse(self.path)
                if parsed.path != "/callback":
                    self.send_error(404)
                    return
                query = parse_qs(parsed.query)
                result["code"] = str((query.get("code") or [""])[0])
                result["state"] = str((query.get("state") or [""])[0])
                result["error"] = str((query.get("error") or [""])[0])
                success = bool(result["code"]) and not result["error"]
                title = "Spotify connected" if success else "Spotify connection was not completed"
                message = (
                    "You can close this tab and return to UltraBike."
                    if success
                    else "Return to UltraBike and try connecting again."
                )
                body = (
                    "<!doctype html><html><head><meta charset='utf-8'>"
                    f"<title>{html.escape(title)}</title>"
                    "<style>body{font-family:Segoe UI,sans-serif;background:#f4f5f7;"
                    "color:#252735;display:grid;place-items:center;height:100vh;margin:0}"
                    ".card{background:white;padding:32px;border-radius:14px;max-width:480px;"
                    "box-shadow:0 8px 30px #0002}h1{margin-top:0}</style></head>"
                    f"<body><div class='card'><h1>{html.escape(title)}</h1>"
                    f"<p>{html.escape(message)}</p></div></body></html>"
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format, *_args):
                return

        try:
            authorization = self.spotify.begin_authorization()
            self._server = HTTPServer(("127.0.0.1", 43821), CallbackHandler)
            self._server.timeout = 0.5
            self.browser_url.emit(authorization.url)
            deadline = time.monotonic() + self.timeout_seconds
            while not result and time.monotonic() < deadline:
                if self.isInterruptionRequested():
                    return
                self._server.handle_request()
        except OSError as error:
            self.failed.emit(
                "UltraBike could not open the Spotify callback port 43821. "
                f"Close any other copy of the app and try again. ({error})"
            )
            return
        except Exception as error:
            self.failed.emit(str(error))
            return
        finally:
            if self._server is not None:
                try:
                    self._server.server_close()
                except Exception:
                    pass
                self._server = None

        if self.isInterruptionRequested():
            return
        if not result:
            self.failed.emit("Spotify login timed out. Try connecting again.")
            return
        if result.get("error"):
            self.failed.emit("Spotify access was not granted.")
            return
        if authorization is None or result.get("state") != authorization.state:
            self.failed.emit("Spotify login validation failed. Try connecting again.")
            return
        try:
            profile = self.spotify.complete_authorization(
                result.get("code", ""), authorization.code_verifier
            )
        except Exception as error:
            self.failed.emit(str(error))
        else:
            self.succeeded.emit(profile)

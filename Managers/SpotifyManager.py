"""Spotify Web API integration and local listening analytics.

The desktop app uses Authorization Code with PKCE, so the public client ID is
enough and no client secret is embedded.  Refresh tokens are protected with
the same current-Windows-user DPAPI mechanism already used by app sessions.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import requests


UTC = timezone.utc


class SpotifyError(RuntimeError):
    """Base error shown to the Spotify UI."""


class SpotifyNotConnectedError(SpotifyError):
    pass


class SpotifyApiError(SpotifyError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class SpotifyAuthorization:
    url: str
    state: str
    code_verifier: str


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class SpotifyManager:
    """Own Spotify authentication, playback commands, and listening history."""

    DEFAULT_CLIENT_ID = "fe9530444b434392b178a8874d9b5020"
    REDIRECT_URI = "http://127.0.0.1:43821/callback"
    AUTH_URL = "https://accounts.spotify.com/authorize"
    TOKEN_URL = "https://accounts.spotify.com/api/token"
    API_URL = "https://api.spotify.com/v1"
    SCOPES = (
        "user-read-private",
        "user-read-playback-state",
        "user-read-currently-playing",
        "user-modify-playback-state",
        "user-read-recently-played",
    )

    def __init__(
        self,
        database,
        settings=None,
        session_manager=None,
        *,
        http_session=None,
        client_id: str | None = None,
        now=None,
    ):
        self.db = database
        self.settings = settings
        self.session_manager = session_manager
        configured = (
            settings.get("spotify_client_id", self.DEFAULT_CLIENT_ID)
            if settings is not None
            else self.DEFAULT_CLIENT_ID
        )
        self.client_id = str(client_id or configured or self.DEFAULT_CLIENT_ID).strip()
        self.http = http_session or requests.Session()
        self._now = now or _utc_now
        self._access_token: str | None = None
        self._access_expires_at: datetime | None = None
        self._network_lock = threading.RLock()

    # ---------------------------------------------------------- authorization
    @staticmethod
    def _b64url(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    def begin_authorization(self) -> SpotifyAuthorization:
        if not self.client_id:
            raise SpotifyError("Spotify Client ID is missing")
        verifier = self._b64url(secrets.token_bytes(64))
        challenge = self._b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        state = secrets.token_urlsafe(24)
        query = urlencode(
            {
                "client_id": self.client_id,
                "response_type": "code",
                "redirect_uri": self.REDIRECT_URI,
                "scope": " ".join(self.SCOPES),
                "state": state,
                "code_challenge_method": "S256",
                "code_challenge": challenge,
                "show_dialog": "true",
            }
        )
        return SpotifyAuthorization(
            url=f"{self.AUTH_URL}?{query}",
            state=state,
            code_verifier=verifier,
        )

    def complete_authorization(self, code: str, code_verifier: str) -> dict[str, Any]:
        token = self._token_request(
            {
                "grant_type": "authorization_code",
                "code": str(code),
                "redirect_uri": self.REDIRECT_URI,
                "client_id": self.client_id,
                "code_verifier": str(code_verifier),
            }
        )
        refresh_token = str(token.get("refresh_token") or "")
        if not refresh_token:
            raise SpotifyError("Spotify did not return a refresh token")
        self._adopt_access_token(token)
        profile = self._request("GET", "/me", retry_auth=False) or {}
        self._save_connection(refresh_token, profile)
        return self.connection_info() or {}

    def _token_request(self, data: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.http.post(
                self.TOKEN_URL,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=(5, 12),
            )
        except requests.RequestException as error:
            raise SpotifyApiError(f"Could not reach Spotify: {error}") from error
        payload = self._json_payload(response)
        if not 200 <= int(response.status_code) < 300:
            message = self._error_message(payload, response.status_code)
            raise SpotifyApiError(message, status_code=int(response.status_code))
        return payload

    def _adopt_access_token(self, token: dict[str, Any]) -> None:
        access_token = str(token.get("access_token") or "")
        if not access_token:
            raise SpotifyError("Spotify did not return an access token")
        expires_in = max(60, int(token.get("expires_in") or 3600))
        self._access_token = access_token
        self._access_expires_at = self._now() + timedelta(seconds=max(30, expires_in - 30))

    def _protect(self, value: str) -> str:
        if self.session_manager is None:
            raise SpotifyError("Secure token storage is unavailable")
        return self.session_manager._encrypt(value)

    def _unprotect(self, value: str) -> str:
        if self.session_manager is None:
            raise SpotifyError("Secure token storage is unavailable")
        return self.session_manager._decrypt(value)

    def _save_connection(self, refresh_token: str, profile: dict[str, Any] | None = None) -> None:
        profile = profile or {}
        stamp = _utc_iso(self._now())
        encrypted = self._protect(refresh_token)
        image_url = ""
        images = profile.get("images") or []
        if images and isinstance(images[0], dict):
            image_url = str(images[0].get("url") or "")
        with self.db.write_lock, self.db.conn:
            self.db.conn.execute(
                """
                INSERT INTO spotify_auth
                    (singleton_id, encrypted_refresh_token, spotify_user_id,
                     display_name, image_url, connected_at, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    encrypted_refresh_token=excluded.encrypted_refresh_token,
                    spotify_user_id=COALESCE(NULLIF(excluded.spotify_user_id, ''), spotify_auth.spotify_user_id),
                    display_name=COALESCE(NULLIF(excluded.display_name, ''), spotify_auth.display_name),
                    image_url=COALESCE(NULLIF(excluded.image_url, ''), spotify_auth.image_url),
                    updated_at=excluded.updated_at
                """,
                (
                    encrypted,
                    str(profile.get("id") or ""),
                    str(profile.get("display_name") or ""),
                    image_url,
                    stamp,
                    stamp,
                ),
            )

    def _load_refresh_token(self) -> str:
        row = self.db.conn.execute(
            "SELECT encrypted_refresh_token FROM spotify_auth WHERE singleton_id=1"
        ).fetchone()
        if row is None:
            raise SpotifyNotConnectedError("Connect a Spotify account first")
        try:
            token = self._unprotect(str(row[0]))
        except Exception as error:
            raise SpotifyNotConnectedError(
                "The saved Spotify connection could not be unlocked; reconnect the account"
            ) from error
        if not token:
            raise SpotifyNotConnectedError("Connect a Spotify account first")
        return token

    def refresh_access_token(self, *, force: bool = False) -> str:
        with self._network_lock:
            if (
                not force
                and self._access_token
                and self._access_expires_at
                and self._now() < self._access_expires_at
            ):
                return self._access_token
            refresh_token = self._load_refresh_token()
            token = self._token_request(
                {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self.client_id,
                }
            )
            self._adopt_access_token(token)
            replacement = str(token.get("refresh_token") or "")
            if replacement and replacement != refresh_token:
                self._save_connection(replacement)
            return self._access_token or ""

    def is_connected(self) -> bool:
        return self.db.conn.execute(
            "SELECT 1 FROM spotify_auth WHERE singleton_id=1"
        ).fetchone() is not None

    def connection_info(self) -> dict[str, Any] | None:
        row = self.db.conn.execute(
            """
            SELECT spotify_user_id, display_name, image_url, connected_at, updated_at
            FROM spotify_auth WHERE singleton_id=1
            """
        ).fetchone()
        return dict(row) if row else None

    def disconnect(self) -> None:
        with self.db.write_lock, self.db.conn:
            self.db.conn.execute("DELETE FROM spotify_auth WHERE singleton_id=1")
        self._access_token = None
        self._access_expires_at = None

    # --------------------------------------------------------------- web API
    @staticmethod
    def _json_payload(response) -> dict[str, Any]:
        try:
            payload = response.json()
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _error_message(payload: dict[str, Any], status_code: int) -> str:
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("reason")
        else:
            message = payload.get("error_description") or error
        if message:
            return str(message)
        if int(status_code) == 403:
            return "Spotify denied this action. Premium or an active playback device may be required."
        if int(status_code) == 429:
            return "Spotify request quota reached. Wait a moment and try again."
        return f"Spotify request failed ({status_code})"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        retry_auth: bool = True,
    ) -> dict[str, Any] | None:
        with self._network_lock:
            token = self.refresh_access_token()
            try:
                response = self.http.request(
                    method,
                    f"{self.API_URL}{path}",
                    params=params,
                    json=json_body,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=(5, 12),
                )
            except requests.RequestException as error:
                raise SpotifyApiError(f"Could not reach Spotify: {error}") from error
            if int(response.status_code) == 401 and retry_auth:
                self.refresh_access_token(force=True)
                return self._request(
                    method,
                    path,
                    params=params,
                    json_body=json_body,
                    retry_auth=False,
                )
            if int(response.status_code) == 204:
                return None
            payload = self._json_payload(response)
            if not 200 <= int(response.status_code) < 300:
                raise SpotifyApiError(
                    self._error_message(payload, response.status_code),
                    status_code=int(response.status_code),
                )
            return payload

    def current_playback(self, *, record: bool = True) -> dict[str, Any] | None:
        # Spotify defaults this endpoint to tracks only.  Request episodes as
        # well so podcast playback reaches both the player UI and our local
        # work-session ledger.
        playback = self._request(
            "GET",
            "/me/player",
            params={"additional_types": "track,episode"},
        )
        if playback and record:
            self.record_current_playback(playback)
        return playback

    def devices(self) -> list[dict[str, Any]]:
        result = self._request("GET", "/me/player/devices") or {}
        return list(result.get("devices") or [])

    def play(self, *, device_id: str | None = None) -> None:
        params = {"device_id": device_id} if device_id else None
        self._request("PUT", "/me/player/play", params=params)

    def pause(self, *, device_id: str | None = None) -> None:
        params = {"device_id": device_id} if device_id else None
        self._request("PUT", "/me/player/pause", params=params)

    def next_track(self, *, device_id: str | None = None) -> None:
        params = {"device_id": device_id} if device_id else None
        self._request("POST", "/me/player/next", params=params)

    def previous_track(self, *, device_id: str | None = None) -> None:
        params = {"device_id": device_id} if device_id else None
        self._request("POST", "/me/player/previous", params=params)

    def set_volume(self, percent: int, *, device_id: str | None = None) -> None:
        params: dict[str, Any] = {"volume_percent": max(0, min(100, int(percent)))}
        if device_id:
            params["device_id"] = device_id
        self._request("PUT", "/me/player/volume", params=params)

    def transfer_playback(self, device_id: str, *, play: bool = False) -> None:
        if not str(device_id or "").strip():
            raise ValueError("Choose a Spotify device")
        self._request(
            "PUT",
            "/me/player",
            json_body={"device_ids": [str(device_id)], "play": bool(play)},
        )

    # --------------------------------------------------------- play history
    def sync_recently_played(self, limit: int = 50) -> int:
        payload = self._request(
            "GET",
            "/me/player/recently-played",
            params={"limit": max(1, min(50, int(limit)))},
        ) or {}
        inserted = 0
        for item in payload.get("items") or []:
            if self._record_play_item(item):
                inserted += 1
        return inserted

    def record_current_playback(self, playback: dict[str, Any]) -> bool:
        if not playback.get("is_playing") or not isinstance(playback.get("item"), dict):
            return False
        timestamp_ms = int(playback.get("timestamp") or self._now().timestamp() * 1000)
        progress_ms = max(0, int(playback.get("progress_ms") or 0))
        played_at = datetime.fromtimestamp((timestamp_ms - progress_ms) / 1000, tz=UTC)
        return self._record_play_item(
            {
                "track": playback["item"],
                "played_at": _utc_iso(played_at),
                "context": playback.get("context") or {},
            }
        )

    def _session_for_time(self, moment: datetime) -> int | None:
        stamp = _utc_iso(moment)
        row = self.db.conn.execute(
            """
            SELECT ws.id
            FROM work_segments segment
            JOIN work_sessions ws ON ws.id=segment.session_id
            WHERE segment.started_at <= ?
              AND COALESCE(segment.ended_at, ws.completed_at, '9999-12-31T23:59:59Z') > ?
            ORDER BY segment.started_at DESC
            LIMIT 1
            """,
            (stamp, stamp),
        ).fetchone()
        return int(row[0]) if row else None

    def _record_play_item(self, play: dict[str, Any]) -> bool:
        track = play.get("track") or play.get("item")
        if not isinstance(track, dict):
            return False
        track_id = str(track.get("id") or "").strip()
        track_name = str(track.get("name") or "").strip()
        played_raw = play.get("played_at")
        if not track_id or not track_name or not played_raw:
            return False
        played_at = _parse_time(played_raw)
        played_stamp = _utc_iso(played_at)
        session_id = self._session_for_time(played_at)
        # UltraBike analytics are deliberately session-only. Playback outside
        # a running work segment is neither stored nor shown in the app.
        if session_id is None:
            return False
        item_type = str(track.get("type") or "track").strip().lower()
        artists = [artist for artist in (track.get("artists") or []) if isinstance(artist, dict)]
        artist_display = ", ".join(
            str(artist.get("name") or "").strip()
            for artist in artists
            if str(artist.get("name") or "").strip()
        )
        album = track.get("album") if isinstance(track.get("album"), dict) else {}
        if item_type == "episode":
            show = track.get("show") if isinstance(track.get("show"), dict) else {}
            show_name = str(show.get("name") or "").strip()
            publisher = str(show.get("publisher") or "").strip()
            artist_display = show_name or publisher
            album = {"name": publisher or show_name}
        context = play.get("context") if isinstance(play.get("context"), dict) else {}

        # A current-playback poll and the later recently-played entry can differ
        # by a few seconds.  Merge those observations rather than double count.
        existing = self.db.conn.execute(
            """
            SELECT id, session_id FROM spotify_plays
            WHERE track_id=?
              AND ABS((julianday(played_at) - julianday(?)) * 86400.0) <= 30
            ORDER BY ABS((julianday(played_at) - julianday(?)) * 86400.0)
            LIMIT 1
            """,
            (track_id, played_stamp, played_stamp),
        ).fetchone()
        if existing:
            if session_id is not None and existing["session_id"] is None:
                with self.db.write_lock, self.db.conn:
                    self.db.conn.execute(
                        "UPDATE spotify_plays SET session_id=? WHERE id=?",
                        (session_id, int(existing["id"])),
                    )
            return False

        with self.db.write_lock, self.db.conn:
            cursor = self.db.conn.execute(
                """
                INSERT INTO spotify_plays
                    (track_id, track_name, artist_display, album_name, duration_ms,
                     played_at, session_id, context_uri, context_type, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    track_id,
                    track_name,
                    artist_display,
                    str(album.get("name") or ""),
                    max(0, int(track.get("duration_ms") or 0)),
                    played_stamp,
                    session_id,
                    str(context.get("uri") or ""),
                    str(context.get("type") or ""),
                    _utc_iso(self._now()),
                ),
            )
            play_id = int(cursor.lastrowid)
            for order, artist in enumerate(artists):
                name = str(artist.get("name") or "").strip()
                if not name:
                    continue
                self.db.conn.execute(
                    """
                    INSERT OR IGNORE INTO spotify_play_artists
                        (play_id, artist_id, artist_name, artist_order)
                    VALUES (?, ?, ?, ?)
                    """,
                    (play_id, str(artist.get("id") or ""), name, order),
                )
        return True

    # ------------------------------------------------------------- analytics
    @staticmethod
    def _period_where(days: int | None, now: datetime) -> tuple[str, list[Any]]:
        if days is None:
            return "", []
        threshold = _utc_iso(now - timedelta(days=max(1, int(days))))
        return "WHERE p.played_at >= ?", [threshold]

    def local_stats(self, *, days: int | None = None, limit: int = 10) -> dict[str, Any]:
        period, params = self._period_where(days, self._now())
        session_where = "WHERE p.session_id IS NOT NULL"
        if period:
            session_where += " AND p.played_at >= ?"
        summary = dict(
            self.db.conn.execute(
                f"""
                SELECT COUNT(*) AS work_plays,
                       COUNT(DISTINCT p.track_id) AS unique_work_tracks,
                       COUNT(DISTINCT p.session_id) AS work_sessions
                FROM spotify_plays p
                {session_where}
                """,
                params,
            ).fetchone()
        )
        work_tracks = [
            dict(row)
            for row in self.db.conn.execute(
                f"""
                SELECT p.track_id, p.track_name AS name, p.artist_display AS artists,
                       COUNT(*) AS play_count
                FROM spotify_plays p
                {session_where}
                GROUP BY p.track_id, p.track_name, p.artist_display
                ORDER BY play_count DESC, p.played_at DESC
                LIMIT ?
                """,
                [*params, max(1, int(limit))],
            ).fetchall()
        ]
        recent = [
            dict(row)
            for row in self.db.conn.execute(
                f"""
                SELECT p.track_name AS name, p.artist_display AS artists,
                       p.played_at, p.session_id
                FROM spotify_plays p
                {session_where}
                ORDER BY p.played_at DESC, p.id DESC
                LIMIT ?
                """,
                [*params, max(1, int(limit))],
            ).fetchall()
        ]
        return {
            "summary": summary,
            "work_tracks": work_tracks,
            "recent": recent,
            "best_session": self.best_session_soundtrack(),
        }

    def best_session_soundtrack(self) -> dict[str, Any] | None:
        row = self.db.conn.execute(
            """
            WITH play_totals AS (
                SELECT session_id, COUNT(*) AS play_count
                FROM spotify_plays
                WHERE session_id IS NOT NULL
                GROUP BY session_id
            ), earning_totals AS (
                SELECT session_id, COUNT(*) AS product_count,
                       COALESCE(SUM(payout_cents), 0) AS earned_cents
                FROM earning_entries
                WHERE session_id IS NOT NULL
                GROUP BY session_id
            ), elapsed AS (
                SELECT session_id,
                       COALESCE(SUM(
                           MAX(0, (julianday(COALESCE(ended_at, started_at)) - julianday(started_at)) * 86400.0)
                       ), 0) AS elapsed_seconds
                FROM work_segments
                GROUP BY session_id
            )
            SELECT ws.id AS session_id, ws.started_at, pt.play_count,
                   COALESCE(et.product_count, 0) AS product_count,
                   COALESCE(et.earned_cents, 0) AS earned_cents,
                   COALESCE(el.elapsed_seconds, 0) AS elapsed_seconds
            FROM work_sessions ws
            JOIN play_totals pt ON pt.session_id=ws.id
            LEFT JOIN earning_totals et ON et.session_id=ws.id
            LEFT JOIN elapsed el ON el.session_id=ws.id
            WHERE ws.status='completed'
            ORDER BY earned_cents DESC, product_count DESC, ws.completed_at DESC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["tracks"] = [
            dict(track)
            for track in self.db.conn.execute(
                """
                SELECT track_name AS name, artist_display AS artists, COUNT(*) AS play_count
                FROM spotify_plays
                WHERE session_id=?
                GROUP BY track_id, track_name, artist_display
                ORDER BY MIN(played_at), name
                """,
                (int(result["session_id"]),),
            ).fetchall()
        ]
        return result

    def dashboard_snapshot(self) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "connection": self.connection_info(),
            "playback": None,
            "devices": [],
            "local": self.local_stats(),
            "errors": {},
        }
        calls = (
            ("playback", lambda: self.current_playback(record=True)),
            ("devices", self.devices),
        )
        for key, callback in calls:
            try:
                snapshot[key] = callback()
            except SpotifyError as error:
                snapshot["errors"][key] = str(error)
        try:
            self.sync_recently_played()
            snapshot["local"] = self.local_stats()
        except SpotifyError as error:
            snapshot["errors"]["recent"] = str(error)
        return snapshot

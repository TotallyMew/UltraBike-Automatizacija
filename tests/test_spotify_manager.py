from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from Database.DatabaseManager import DatabaseManager
from Database.SettingsManager import SettingsManager
from Managers.EarningsManager import EarningsManager
from Managers.SpotifyManager import SpotifyManager


UTC = timezone.utc


class _SecretStore:
    def _encrypt(self, value: str) -> str:
        return f"protected:{value[::-1]}"

    def _decrypt(self, value: str) -> str:
        assert value.startswith("protected:")
        return value.removeprefix("protected:")[::-1]


class _Response:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _Http:
    def __init__(self):
        self.posts = []
        self.requests = []
        self.token_responses = [
            _Response(
                200,
                {
                    "access_token": "access-one",
                    "refresh_token": "refresh-one",
                    "expires_in": 3600,
                },
            )
        ]
        self.api = {
            ("GET", "/me"): _Response(
                200, {"id": "listener-1", "display_name": "Test Listener", "images": []}
            ),
        }

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return self.token_responses.pop(0)

    def request(self, method, url, **kwargs):
        path = urlparse(url).path.removeprefix("/v1") or "/"
        self.requests.append((method, path, kwargs))
        return self.api.get((method, path), _Response(204))


def _manager(now: datetime | None = None):
    database = DatabaseManager(":memory:")
    settings = SettingsManager(database)
    http = _Http()
    manager = SpotifyManager(
        database,
        settings,
        _SecretStore(),
        http_session=http,
        now=(lambda: now) if now is not None else None,
    )
    return database, settings, http, manager


def test_schema_v5_upgrades_v4_and_preserves_sessions(tmp_path: Path):
    path = tmp_path / "v4.db"
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE work_sessions (
            id INTEGER PRIMARY KEY,
            mode TEXT NOT NULL,
            target_seconds INTEGER,
            status TEXT NOT NULL,
            allow_overtime INTEGER NOT NULL DEFAULT 0,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            quest_kind TEXT,
            quest_target_value INTEGER,
            quest_completed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    stamp = "2026-08-01T09:00:00.000000Z"
    connection.execute(
        """
        INSERT INTO work_sessions
            (id, mode, status, started_at, created_at, updated_at)
        VALUES (7, 'stopwatch', 'completed', ?, ?, ?)
        """,
        (stamp, stamp, stamp),
    )
    connection.execute("PRAGMA user_version=4")
    connection.commit()
    connection.close()

    upgraded = DatabaseManager(path)
    try:
        assert upgraded.conn.execute("PRAGMA user_version").fetchone()[0] == 5
        assert upgraded.conn.execute("SELECT id FROM work_sessions").fetchone()[0] == 7
        for table in ("spotify_auth", "spotify_plays", "spotify_play_artists"):
            assert upgraded.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
    finally:
        upgraded.close()


def test_pkce_authorization_uses_loopback_and_no_client_secret():
    database, _settings, _http, manager = _manager()
    try:
        authorization = manager.begin_authorization()
        query = parse_qs(urlparse(authorization.url).query)
        assert query["client_id"] == [SpotifyManager.DEFAULT_CLIENT_ID]
        assert query["redirect_uri"] == [SpotifyManager.REDIRECT_URI]
        assert query["code_challenge_method"] == ["S256"]
        assert query["state"] == [authorization.state]
        assert "user-top-read" not in query["scope"][0]
        assert "user-modify-playback-state" in query["scope"][0]
        assert "client_secret" not in query
    finally:
        database.close()


def test_authorization_saves_only_protected_refresh_token():
    now = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
    database, _settings, http, manager = _manager(now)
    try:
        profile = manager.complete_authorization("auth-code", "verifier")
        assert profile["spotify_user_id"] == "listener-1"
        row = database.conn.execute(
            "SELECT encrypted_refresh_token, display_name FROM spotify_auth"
        ).fetchone()
        assert row["encrypted_refresh_token"].startswith("protected:")
        assert "refresh-one" not in row["encrypted_refresh_token"]
        assert row["display_name"] == "Test Listener"
        token_data = http.posts[0][1]["data"]
        assert token_data["code_verifier"] == "verifier"
        assert "client_secret" not in token_data
    finally:
        database.close()


def test_recent_plays_link_to_running_work_segments_and_deduplicate():
    started = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
    database, settings, _http, spotify = _manager(started + timedelta(minutes=30))
    earnings = EarningsManager(database, settings)
    try:
        session_id = earnings.start_session("stopwatch", now=started)
        play = {
            "played_at": (started + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
            "track": {
                "id": "track-1",
                "name": "Deep Focus",
                "duration_ms": 180_000,
                "artists": [{"id": "artist-1", "name": "Focus Artist"}],
                "album": {"name": "Work Album"},
            },
            "context": {"uri": "spotify:playlist:work", "type": "playlist"},
        }
        assert spotify._record_play_item(play)
        duplicate = dict(play)
        duplicate["played_at"] = (
            started + timedelta(minutes=5, seconds=15)
        ).isoformat().replace("+00:00", "Z")
        assert not spotify._record_play_item(duplicate)

        row = database.conn.execute("SELECT * FROM spotify_plays").fetchone()
        assert row["session_id"] == session_id
        assert row["track_name"] == "Deep Focus"
        artist = database.conn.execute("SELECT * FROM spotify_play_artists").fetchone()
        assert artist["artist_name"] == "Focus Artist"
        assert database.conn.execute("SELECT COUNT(*) FROM spotify_plays").fetchone()[0] == 1
    finally:
        database.close()


def test_local_stats_and_best_session_soundtrack_are_derived_from_ledger():
    started = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
    database, settings, _http, spotify = _manager(started + timedelta(hours=2))
    earnings = EarningsManager(database, settings)
    try:
        session_id = earnings.start_session("stopwatch", now=started)
        earnings.create_entry("SKU-1", "bicycle", now=started + timedelta(minutes=2))
        for offset, track_id, name in (
            (3, "track-1", "Deep Focus"),
            (7, "track-1", "Deep Focus"),
            (11, "track-2", "Momentum"),
        ):
            spotify._record_play_item(
                {
                    "played_at": (started + timedelta(minutes=offset)).isoformat(),
                    "track": {
                        "id": track_id,
                        "name": name,
                        "duration_ms": 180_000,
                        "artists": [{"id": "artist-1", "name": "Focus Artist"}],
                        "album": {"name": "Work Album"},
                    },
                }
            )
        earnings.finish_session(now=started + timedelta(minutes=30))

        # General listening is intentionally outside UltraBike's ledger.
        assert not spotify._record_play_item(
            {
                "played_at": (started + timedelta(minutes=90)).isoformat(),
                "track": {
                    "id": "track-personal",
                    "name": "Personal Listening",
                    "artists": [{"id": "artist-2", "name": "Off Hours"}],
                },
            }
        )

        stats = spotify.local_stats()
        assert stats["summary"] == {
            "work_plays": 3,
            "unique_work_tracks": 2,
            "work_sessions": 1,
        }
        assert stats["work_tracks"][0]["name"] == "Deep Focus"
        assert stats["work_tracks"][0]["play_count"] == 2
        assert "top_tracks" not in stats
        assert "top_artists" not in stats
        assert stats["best_session"]["session_id"] == session_id
        assert stats["best_session"]["earned_cents"] == 100
        assert stats["best_session"]["product_count"] == 1
    finally:
        database.close()


def test_dashboard_never_requests_account_wide_rankings():
    database, _settings, http, manager = _manager()
    try:
        manager.complete_authorization("auth-code", "verifier")
        snapshot = manager.dashboard_snapshot()

        assert "top_tracks" not in snapshot
        assert "top_artists" not in snapshot
        assert not any(path.startswith("/me/top/") for _method, path, _kwargs in http.requests)
    finally:
        database.close()


def test_playback_commands_target_spotify_connect_device_and_volume():
    database, _settings, http, manager = _manager()
    try:
        manager.complete_authorization("auth-code", "verifier")
        manager.set_volume(67, device_id="device-1")
        manager.transfer_playback("device-2", play=False)
        volume = http.requests[-2]
        transfer = http.requests[-1]
        assert volume[0:2] == ("PUT", "/me/player/volume")
        assert volume[2]["params"] == {"volume_percent": 67, "device_id": "device-1"}
        assert transfer[0:2] == ("PUT", "/me/player")
        assert transfer[2]["json"] == {"device_ids": ["device-2"], "play": False}
    finally:
        database.close()

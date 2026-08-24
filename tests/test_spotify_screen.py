from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from Database.DatabaseManager import DatabaseManager
from Database.SessionManager import SessionManager
from Database.SettingsManager import SettingsManager
from GUI_Qt.i18n import translate
from GUI_Qt.screens.SpotifyScreen import SpotifyScreen
from Managers.SpotifyManager import SpotifyManager


class _I18n:
    @staticmethod
    def tr(key, **values):
        return translate("en", key, **values)


class _Main(QWidget):
    def __init__(self, database, settings):
        super().__init__()
        self.db = database
        self.settings = settings
        self.i18n = _I18n()
        self.spotify_manager = SpotifyManager(
            database, settings, SessionManager(database)
        )


def test_disconnected_spotify_page_explains_connection_and_keeps_controls_inactive():
    app = QApplication.instance() or QApplication([])
    database = DatabaseManager(":memory:")
    try:
        settings = SettingsManager(database)
        main = _Main(database, settings)
        screen = SpotifyScreen(main)
        screen.resize(1100, 800)
        screen.show()
        app.processEvents()

        assert screen.title.text() == "Spotify Connect"
        assert screen.connect_button.isVisible()
        assert not screen.disconnect_button.isVisible()
        assert not screen.player_card.isEnabled()
        assert screen.connection_title.text() == "Connect your Spotify account"
        assert screen.analytics_title.text() == "Work-session listening"
        assert screen.plays_metric_value.text() == "0"
        assert screen.work_tracks.rowCount() == 0
        assert not hasattr(screen, "spotify_tracks")
        assert not hasattr(screen, "spotify_artists")
        assert not hasattr(screen, "local_tracks")
        assert not hasattr(screen, "time_range")
        assert not screen._poll_timer.isActive()

        screen._apply_local(
            {
                "summary": {
                    "work_plays": 4,
                    "unique_work_tracks": 2,
                    "work_sessions": 1,
                },
                "work_tracks": [
                    {
                        "name": "Deep Focus",
                        "artists": "Focus Artist",
                        "play_count": 3,
                    }
                ],
            }
        )
        assert screen.plays_metric_value.text() == "4"
        assert screen.tracks_metric_value.text() == "2"
        assert screen.sessions_metric_value.text() == "1"
        assert screen.work_tracks.rowCount() == 1

        assert screen.shutdown()
        screen.close()
        screen.deleteLater()
        main.deleteLater()
        app.processEvents()
    finally:
        database.close()


def test_foreground_activation_starts_fast_polling_and_live_progress(monkeypatch):
    app = QApplication.instance() or QApplication([])
    database = DatabaseManager(":memory:")
    try:
        settings = SettingsManager(database)
        main = _Main(database, settings)
        screen = SpotifyScreen(main)
        polls = []
        refreshes = []
        monkeypatch.setattr(screen.spotify, "is_connected", lambda: True)
        monkeypatch.setattr(screen, "_poll_playback", lambda: polls.append(True))
        monkeypatch.setattr(screen, "refresh_dashboard", lambda: refreshes.append(True))

        screen.on_activated()
        assert screen._poll_timer.isActive()
        assert screen._poll_timer.interval() == screen.FOREGROUND_POLL_INTERVAL_MS
        assert screen._playback_tick_timer.isActive()
        assert polls == [True]
        assert refreshes == [True]

        clock = iter((100.0, 103.0))
        monkeypatch.setattr("GUI_Qt.screens.SpotifyScreen.time.monotonic", lambda: next(clock))
        screen._apply_playback(
            {
                "is_playing": True,
                "progress_ms": 10_000,
                "timestamp": 0,
                "device": {"name": "Desktop", "volume_percent": 40},
                "item": {
                    "id": "track-1",
                    "name": "Live Track",
                    "duration_ms": 60_000,
                    "artists": [{"name": "Artist"}],
                    "album": {"name": "Album"},
                },
            }
        )
        screen._advance_playback_progress()
        assert screen.track_time.text() == "0:13 / 1:00"
        assert 215 <= screen.track_progress.value() <= 217

        screen._poll_timer.stop()
        screen._playback_tick_timer.stop()
        screen.close()
        screen.deleteLater()
        main.deleteLater()
        app.processEvents()
    finally:
        database.close()


def test_now_playing_renders_podcast_episode_show_and_publisher():
    app = QApplication.instance() or QApplication([])
    database = DatabaseManager(":memory:")
    try:
        settings = SettingsManager(database)
        main = _Main(database, settings)
        screen = SpotifyScreen(main)

        screen._apply_playback(
            {
                "is_playing": True,
                "currently_playing_type": "episode",
                "progress_ms": 120_000,
                "item": {
                    "id": "episode-1",
                    "name": "How Bikes Get Built",
                    "type": "episode",
                    "duration_ms": 2_400_000,
                    "show": {
                        "name": "The Workshop",
                        "publisher": "Ultra Media",
                    },
                },
            }
        )

        assert screen.track_name.text() == "How Bikes Get Built"
        assert screen.track_artists.text() == "The Workshop"
        assert screen.track_album.text() == "Ultra Media"

        screen.close()
        screen.deleteLater()
        main.deleteLater()
        app.processEvents()
    finally:
        database.close()


def test_volume_change_targets_selected_device_and_survives_playback_poll(monkeypatch):
    app = QApplication.instance() or QApplication([])
    database = DatabaseManager(":memory:")
    try:
        settings = SettingsManager(database)
        main = _Main(database, settings)
        screen = SpotifyScreen(main)
        commands = []
        volume_calls = []
        monkeypatch.setattr(screen.spotify, "is_connected", lambda: True)
        monkeypatch.setattr(
            screen.spotify,
            "set_volume",
            lambda percent, *, device_id=None: volume_calls.append((percent, device_id)),
        )

        def capture_command(name, callback):
            commands.append((name, callback))
            return True

        monkeypatch.setattr(screen, "_run_command", capture_command)
        screen.device_combo.addItem("Desktop", userData="device-1")
        screen.device_combo.setCurrentIndex(0)
        screen.player_card.setEnabled(True)
        screen.volume_slider.setEnabled(True)

        screen.volume_slider.setValue(67)
        assert screen._pending_volume == 67
        screen._volume_commit_timer.stop()

        # A stale playback poll must not replace the user's staged value.
        screen._apply_playback(
            {
                "is_playing": True,
                "progress_ms": 1_000,
                "item": {"id": "track-1", "name": "Track", "duration_ms": 60_000},
                "device": {
                    "id": "device-1",
                    "name": "Desktop",
                    "volume_percent": 40,
                    "supports_volume": True,
                },
            }
        )
        assert screen.volume_slider.value() == 67

        screen._commit_volume()
        assert screen._pending_volume is None
        assert commands[0][0] == "volume"
        commands[0][1]()
        assert volume_calls == [(67, "device-1")]

        screen.close()
        screen.deleteLater()
        main.deleteLater()
        app.processEvents()
    finally:
        database.close()

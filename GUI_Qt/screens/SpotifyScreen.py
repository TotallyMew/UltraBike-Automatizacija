"""Spotify Connect controls and work-session listening analytics."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from PySide6.QtCore import QSignalBlocker, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    ComboBox,
    FluentIcon,
    IconWidget,
    InfoBar,
    InfoBarPosition,
    MessageBox,
    PrimaryPushButton,
    PushButton,
    ScrollArea,
    StrongBodyLabel,
    TitleLabel,
    isDarkTheme,
    qconfig,
)

from GUI_Qt.styles.screen_theme import apply_screen_theme
from GUI_Qt.styles.theme_config import (
    COLORS,
    RADII,
    SPACING,
    get_subtle_border,
    get_surface_color,
)
from GUI_Qt.widgets.ResponsiveWidget import ResponsiveWidget
from GUI_Qt.workers.spotify_workers import SpotifyAuthWorker, SpotifyCallWorker
from Managers.SpotifyManager import SpotifyManager


class SpotifyScreen(ResponsiveWidget):
    FOREGROUND_POLL_INTERVAL_MS = 5_000
    BACKGROUND_POLL_INTERVAL_MS = 30_000
    RECENT_SYNC_INTERVAL_SECONDS = 300

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.spotify: SpotifyManager = main_window.spotify_manager
        self._auth_worker = None
        self._dashboard_worker = None
        self._poll_worker = None
        self._command_worker = None
        self._poll_count = 0
        self._last_recent_sync_at = 0.0
        self._last_snapshot: dict[str, Any] | None = None
        self._playback_clock_started = 0.0
        self._playback_base_progress_ms = 0
        self._playback_duration_ms = 0
        self._playback_is_playing = False
        self._init_ui()
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self.BACKGROUND_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll_playback)
        self._playback_tick_timer = QTimer(self)
        self._playback_tick_timer.setInterval(1_000)
        self._playback_tick_timer.timeout.connect(self._advance_playback_progress)
        qconfig.themeChangedFinished.connect(self._apply_theme)
        self._apply_theme()
        self.retranslate_ui()
        self._set_connected_state(self.spotify.is_connected())
        if self.spotify.is_connected():
            self._poll_timer.start()

    def _t(self, key: str, **kwargs) -> str:
        return self.main.i18n.tr(key, **kwargs)

    # ------------------------------------------------------------------ UI
    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.scroll = ScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(ScrollArea.Shape.NoFrame)
        root.addWidget(self.scroll)

        self.content = QWidget()
        self.scroll.setWidget(self.content)
        self.layout = QVBoxLayout(self.content)
        self.layout.setContentsMargins(24, 20, 30, 28)
        self.layout.setSpacing(SPACING["lg"])

        header = QHBoxLayout()
        header.setSpacing(SPACING["sm"])
        icon = IconWidget(FluentIcon.MUSIC)
        icon.setFixedSize(28, 28)
        self.title = TitleLabel("")
        self.refresh_button = PushButton("")
        self.refresh_button.setIcon(FluentIcon.SYNC)
        self.refresh_button.clicked.connect(self.refresh_dashboard)
        header.addWidget(icon)
        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.refresh_button)
        self.layout.addLayout(header)

        self.connection_card = self._card()
        connection_layout = QHBoxLayout(self.connection_card)
        connection_layout.setContentsMargins(20, 18, 20, 18)
        connection_layout.setSpacing(SPACING["md"])
        connection_text = QVBoxLayout()
        connection_text.setSpacing(SPACING["xs"])
        self.connection_title = StrongBodyLabel("")
        self.connection_detail = CaptionLabel("")
        self.connection_detail.setWordWrap(True)
        connection_text.addWidget(self.connection_title)
        connection_text.addWidget(self.connection_detail)
        self.connect_button = PrimaryPushButton("")
        self.connect_button.clicked.connect(self._connect)
        self.disconnect_button = PushButton("")
        self.disconnect_button.clicked.connect(self._disconnect)
        connection_layout.addLayout(connection_text, 1)
        connection_layout.addWidget(self.disconnect_button)
        connection_layout.addWidget(self.connect_button)
        self.layout.addWidget(self.connection_card)

        self.player_card = self._card()
        player = QVBoxLayout(self.player_card)
        player.setContentsMargins(20, 18, 20, 18)
        player.setSpacing(SPACING["md"])
        player_header = QHBoxLayout()
        self.now_playing_title = StrongBodyLabel("")
        self.device_label = CaptionLabel("")
        player_header.addWidget(self.now_playing_title)
        player_header.addStretch(1)
        player_header.addWidget(self.device_label)
        player.addLayout(player_header)
        self.track_name = QLabel("—")
        self.track_name.setObjectName("spotifyTrackName")
        self.track_name.setWordWrap(True)
        self.track_artists = BodyLabel("—")
        self.track_album = CaptionLabel("")
        player.addWidget(self.track_name)
        player.addWidget(self.track_artists)
        player.addWidget(self.track_album)

        self.track_progress = QProgressBar()
        self.track_progress.setRange(0, 1000)
        self.track_progress.setValue(0)
        self.track_progress.setTextVisible(False)
        self.track_progress.setFixedHeight(5)
        self.track_time = CaptionLabel("0:00 / 0:00")
        player.addWidget(self.track_progress)
        player.addWidget(self.track_time)

        controls = QHBoxLayout()
        controls.setSpacing(SPACING["sm"])
        self.previous_button = PushButton("")
        self.previous_button.setIcon(FluentIcon.LEFT_ARROW)
        self.play_button = PrimaryPushButton("")
        self.play_button.setIcon(FluentIcon.PLAY)
        self.next_button = PushButton("")
        self.next_button.setIcon(FluentIcon.RIGHT_ARROW)
        self.previous_button.clicked.connect(
            lambda: self._run_command("previous", self.spotify.previous_track)
        )
        self.play_button.clicked.connect(self._toggle_playback)
        self.next_button.clicked.connect(
            lambda: self._run_command("next", self.spotify.next_track)
        )
        controls.addWidget(self.previous_button)
        controls.addWidget(self.play_button)
        controls.addWidget(self.next_button)
        controls.addSpacing(SPACING["md"])
        self.device_combo = ComboBox()
        self.device_combo.setMinimumWidth(180)
        self.device_combo.currentIndexChanged.connect(self._device_changed)
        controls.addWidget(self.device_combo, 1)
        self.volume_title = CaptionLabel("")
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setSingleStep(5)
        self.volume_slider.setMinimumWidth(130)
        self.volume_slider.sliderReleased.connect(self._volume_released)
        self.volume_value = CaptionLabel("—")
        self.volume_value.setMinimumWidth(38)
        self.volume_slider.valueChanged.connect(
            lambda value: self.volume_value.setText(f"{int(value)}%")
        )
        controls.addWidget(self.volume_title)
        controls.addWidget(self.volume_slider)
        controls.addWidget(self.volume_value)
        player.addLayout(controls)
        self.layout.addWidget(self.player_card)

        analytics_toolbar = QHBoxLayout()
        analytics_toolbar.setSpacing(SPACING["sm"])
        self.analytics_title = StrongBodyLabel("")
        analytics_toolbar.addWidget(self.analytics_title)
        analytics_toolbar.addStretch(1)
        self.layout.addLayout(analytics_toolbar)

        self.metrics_grid = QGridLayout()
        self.metrics_grid.setSpacing(SPACING["md"])
        self.plays_metric, self.plays_metric_title, self.plays_metric_value = self._metric()
        self.tracks_metric, self.tracks_metric_title, self.tracks_metric_value = self._metric()
        self.sessions_metric, self.sessions_metric_title, self.sessions_metric_value = self._metric()
        for column, widget in enumerate(
            (self.plays_metric, self.tracks_metric, self.sessions_metric)
        ):
            self.metrics_grid.addWidget(widget, 0, column)
            self.metrics_grid.setColumnStretch(column, 1)
        self.layout.addLayout(self.metrics_grid)

        self.tables_grid = QGridLayout()
        self.tables_grid.setSpacing(SPACING["md"])
        self.work_tracks_card, self.work_tracks_title, self.work_tracks_note, self.work_tracks = self._ranking_card()
        self.tables_grid.addWidget(self.work_tracks_card, 0, 0)
        self.tables_grid.setColumnStretch(0, 1)
        self.layout.addLayout(self.tables_grid)

        self.best_card = self._card()
        best_layout = QVBoxLayout(self.best_card)
        best_layout.setContentsMargins(20, 18, 20, 18)
        best_layout.setSpacing(SPACING["xs"])
        self.best_title = StrongBodyLabel("")
        self.best_detail = BodyLabel("")
        self.best_detail.setWordWrap(True)
        self.best_tracks = CaptionLabel("")
        self.best_tracks.setWordWrap(True)
        best_layout.addWidget(self.best_title)
        best_layout.addWidget(self.best_detail)
        best_layout.addWidget(self.best_tracks)
        self.layout.addWidget(self.best_card)
        self.layout.addStretch(1)

    @staticmethod
    def _card() -> CardWidget:
        card = CardWidget()
        card.setBorderRadius(RADII["md"])
        return card

    def _metric(self):
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(SPACING["xs"])
        title = CaptionLabel("")
        value = QLabel("0")
        value.setObjectName("spotifyMetricValue")
        layout.addWidget(title)
        layout.addWidget(value)
        return card, title, value

    def _ranking_card(self):
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(SPACING["xs"])
        title = StrongBodyLabel("")
        note = CaptionLabel("")
        note.setWordWrap(True)
        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["#", "", ""])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.setMinimumHeight(250)
        layout.addWidget(title)
        layout.addWidget(note)
        layout.addWidget(table)
        return card, title, note, table

    # ---------------------------------------------------------- connection
    def _connect(self) -> None:
        if self._auth_worker is not None and self._auth_worker.isRunning():
            return
        self.connect_button.setEnabled(False)
        self.connection_detail.setText(self._t("spotify.connect.waiting"))
        worker = SpotifyAuthWorker(self.spotify, self)
        self._auth_worker = worker
        worker.browser_url.connect(lambda url: QDesktopServices.openUrl(QUrl(url)))
        worker.succeeded.connect(self._connected)
        worker.failed.connect(self._connection_failed)
        worker.finished.connect(lambda: self.connect_button.setEnabled(True))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _connected(self, profile: dict[str, Any]) -> None:
        self._auth_worker = None
        self._set_connected_state(True)
        self._poll_timer.setInterval(
            self.FOREGROUND_POLL_INTERVAL_MS
            if self.isVisible()
            else self.BACKGROUND_POLL_INTERVAL_MS
        )
        self._poll_timer.start()
        self._playback_tick_timer.start()
        name = profile.get("display_name") or profile.get("spotify_user_id") or "Spotify"
        InfoBar.success(
            title=self._t("spotify.connected.title"),
            content=self._t("spotify.connected.detail", name=name),
            parent=self,
            position=InfoBarPosition.TOP,
            duration=3500,
        )
        self.refresh_dashboard()

    def _connection_failed(self, message: str) -> None:
        self._auth_worker = None
        self._set_connected_state(self.spotify.is_connected())
        InfoBar.error(
            title=self._t("spotify.error.title"),
            content=message,
            parent=self,
            position=InfoBarPosition.TOP,
            duration=6000,
        )

    def _disconnect(self) -> None:
        dialog = MessageBox(
            self._t("spotify.disconnect.title"),
            self._t("spotify.disconnect.detail"),
            self,
        )
        dialog.yesButton.setText(self._t("spotify.disconnect.action"))
        dialog.cancelButton.setText(self._t("common.cancel"))
        if not dialog.exec():
            return
        self.spotify.disconnect()
        self._poll_timer.stop()
        self._playback_tick_timer.stop()
        self._last_snapshot = None
        self._set_connected_state(False)
        self._clear_data()

    def _set_connected_state(self, connected: bool) -> None:
        info = self.spotify.connection_info() if connected else None
        self.connect_button.setVisible(not connected)
        self.disconnect_button.setVisible(connected)
        self.refresh_button.setEnabled(connected)
        self.player_card.setEnabled(connected)
        if connected:
            name = (info or {}).get("display_name") or (info or {}).get("spotify_user_id") or "Spotify"
            self.connection_title.setText(self._t("spotify.connection.connected", name=name))
            self.connection_detail.setText(self._t("spotify.connection.connected.detail"))
        else:
            self.connection_title.setText(self._t("spotify.connection.disconnected"))
            self.connection_detail.setText(self._t("spotify.connection.disconnected.detail"))

    # ------------------------------------------------------------- workers
    def refresh_dashboard(self) -> None:
        if not self.spotify.is_connected():
            return
        if self._dashboard_worker is not None and self._dashboard_worker.isRunning():
            return
        self.refresh_button.setEnabled(False)
        worker = SpotifyCallWorker(
            self.spotify.dashboard_snapshot, self
        )
        self._dashboard_worker = worker
        worker.succeeded.connect(self._dashboard_ready)
        worker.failed.connect(lambda message: self._show_error(message, quiet=False))
        worker.finished.connect(self._dashboard_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _dashboard_finished(self) -> None:
        self._dashboard_worker = None
        self.refresh_button.setEnabled(self.spotify.is_connected())

    def _dashboard_ready(self, snapshot: dict[str, Any]) -> None:
        self._last_snapshot = snapshot
        self._apply_snapshot(snapshot)
        errors = snapshot.get("errors") or {}
        if errors and not snapshot.get("playback"):
            self._show_error(next(iter(errors.values())), quiet=True)

    def _poll_playback(self) -> None:
        if not self.spotify.is_connected():
            self._poll_timer.stop()
            return
        if self._poll_worker is not None and self._poll_worker.isRunning():
            return
        self._poll_count += 1
        now_monotonic = time.monotonic()
        sync_recent = (
            now_monotonic - self._last_recent_sync_at
            >= self.RECENT_SYNC_INTERVAL_SECONDS
        )
        refresh_local = self.isVisible()

        def _poll():
            playback = self.spotify.current_playback(record=True)
            inserted = self.spotify.sync_recently_played() if sync_recent else 0
            local = self.spotify.local_stats() if (refresh_local or inserted) else None
            return {"playback": playback, "local": local}

        worker = SpotifyCallWorker(_poll, self)
        self._poll_worker = worker
        worker.succeeded.connect(self._poll_ready)
        if sync_recent:
            worker.succeeded.connect(
                lambda _result, stamp=now_monotonic: setattr(
                    self, "_last_recent_sync_at", stamp
                )
            )
        worker.failed.connect(lambda message: self._show_error(message, quiet=True))
        worker.finished.connect(self._poll_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _poll_finished(self) -> None:
        self._poll_worker = None

    def _poll_ready(self, result: dict[str, Any]) -> None:
        self._apply_playback(result.get("playback"))
        if result.get("local"):
            self._apply_local(result["local"])

    def _run_command(self, _name: str, callback) -> None:
        if self._command_worker is not None and self._command_worker.isRunning():
            return
        for button in (self.previous_button, self.play_button, self.next_button):
            button.setEnabled(False)
        worker = SpotifyCallWorker(callback, self)
        self._command_worker = worker
        worker.succeeded.connect(lambda _result: QTimer.singleShot(350, self._poll_playback))
        worker.failed.connect(lambda message: self._show_error(message, quiet=False))
        worker.finished.connect(self._command_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _command_finished(self) -> None:
        self._command_worker = None
        for button in (self.previous_button, self.play_button, self.next_button):
            button.setEnabled(self.spotify.is_connected())

    def _toggle_playback(self) -> None:
        playback = (self._last_snapshot or {}).get("playback") or {}
        callback = self.spotify.pause if playback.get("is_playing") else self.spotify.play
        self._run_command("playback", callback)

    def _volume_released(self) -> None:
        self._run_command(
            "volume", lambda: self.spotify.set_volume(self.volume_slider.value())
        )

    def _device_changed(self, _index: int) -> None:
        device_id = self.device_combo.currentData()
        if not device_id or not self.spotify.is_connected():
            return
        active = ((self._last_snapshot or {}).get("playback") or {}).get("device") or {}
        if str(active.get("id") or "") == str(device_id):
            return
        self._run_command(
            "device", lambda: self.spotify.transfer_playback(str(device_id), play=False)
        )

    # ------------------------------------------------------------- rendering
    def _apply_snapshot(self, snapshot: dict[str, Any]) -> None:
        self._apply_playback(snapshot.get("playback"))
        self._populate_devices(snapshot.get("devices") or [], snapshot.get("playback"))
        self._apply_local(snapshot.get("local") or {})

    def _apply_playback(self, playback: dict[str, Any] | None) -> None:
        if self._last_snapshot is None:
            self._last_snapshot = {}
        self._last_snapshot["playback"] = playback
        if not playback or not isinstance(playback.get("item"), dict):
            self._playback_is_playing = False
            self._playback_base_progress_ms = 0
            self._playback_duration_ms = 0
            self._playback_clock_started = time.monotonic()
            self.track_name.setText(self._t("spotify.player.idle"))
            self.track_artists.setText(self._t("spotify.player.open_device"))
            self.track_album.setText("")
            self.device_label.setText("")
            self.track_progress.setValue(0)
            self.track_time.setText("0:00 / 0:00")
            self.play_button.setText(self._t("spotify.player.play"))
            self.play_button.setIcon(FluentIcon.PLAY)
            return
        track = playback["item"]
        item_type = str(
            track.get("type") or playback.get("currently_playing_type") or "track"
        )
        artists = ", ".join(
            str(artist.get("name") or "")
            for artist in track.get("artists") or []
            if isinstance(artist, dict)
        )
        album = track.get("album") if isinstance(track.get("album"), dict) else {}
        if item_type == "episode":
            show = track.get("show") if isinstance(track.get("show"), dict) else {}
            artists = str(show.get("name") or show.get("publisher") or "")
            album = {"name": str(show.get("publisher") or "")}
        progress = max(0, int(playback.get("progress_ms") or 0))
        duration = max(0, int(track.get("duration_ms") or 0))
        device = playback.get("device") if isinstance(playback.get("device"), dict) else {}
        self.track_name.setText(str(track.get("name") or "—"))
        self.track_artists.setText(artists or "—")
        self.track_album.setText(str(album.get("name") or ""))
        self.device_label.setText(str(device.get("name") or ""))
        is_playing = bool(playback.get("is_playing"))
        self._playback_base_progress_ms = progress
        self._playback_duration_ms = duration
        self._playback_is_playing = is_playing
        self._playback_clock_started = time.monotonic()
        self._render_playback_progress(progress, duration)
        self.play_button.setText(
            self._t("spotify.player.pause" if is_playing else "spotify.player.play")
        )
        self.play_button.setIcon(FluentIcon.PAUSE if is_playing else FluentIcon.PLAY)
        volume = device.get("volume_percent")
        if volume is not None:
            blocker = QSignalBlocker(self.volume_slider)
            self.volume_slider.setValue(int(volume))
            del blocker
            self.volume_value.setText(f"{int(volume)}%")
        supports_volume = bool(device.get("supports_volume", True))
        self.volume_slider.setEnabled(supports_volume)

    def _advance_playback_progress(self) -> None:
        if not self._playback_is_playing or self._playback_duration_ms <= 0:
            return
        elapsed_ms = int(
            max(0.0, time.monotonic() - self._playback_clock_started) * 1000
        )
        progress = min(
            self._playback_duration_ms,
            self._playback_base_progress_ms + elapsed_ms,
        )
        self._render_playback_progress(progress, self._playback_duration_ms)
        if progress >= self._playback_duration_ms:
            self._playback_is_playing = False
            QTimer.singleShot(150, self._poll_playback)

    def _render_playback_progress(self, progress_ms: int, duration_ms: int) -> None:
        self.track_progress.setValue(
            int(progress_ms * 1000 / duration_ms) if duration_ms else 0
        )
        self.track_time.setText(
            f"{self._clock(progress_ms)} / {self._clock(duration_ms)}"
        )

    def _populate_devices(self, devices: list[dict[str, Any]], playback) -> None:
        active_id = str(((playback or {}).get("device") or {}).get("id") or "")
        blocker = QSignalBlocker(self.device_combo)
        self.device_combo.clear()
        if not devices:
            self.device_combo.addItem(self._t("spotify.device.none"), userData=None)
        selected = 0
        for index, device in enumerate(devices):
            label = str(device.get("name") or self._t("spotify.device.unknown"))
            if device.get("is_active"):
                label = self._t("spotify.device.active", name=label)
            self.device_combo.addItem(label, userData=device.get("id"))
            if str(device.get("id") or "") == active_id:
                selected = index
        self.device_combo.setCurrentIndex(selected)
        del blocker

    def _apply_local(self, local: dict[str, Any]) -> None:
        summary = local.get("summary") or {}
        self.plays_metric_value.setText(str(summary.get("work_plays") or 0))
        self.tracks_metric_value.setText(str(summary.get("unique_work_tracks") or 0))
        self.sessions_metric_value.setText(str(summary.get("work_sessions") or 0))
        self._fill_table(
            self.work_tracks,
            [
                (
                    str(row.get("name") or "—"),
                    str(row.get("artists") or ""),
                    self._t("spotify.plays", count=int(row.get("play_count") or 0)),
                )
                for row in local.get("work_tracks") or []
            ],
            ranked=True,
        )
        self._apply_best_session(local.get("best_session"))

    def _apply_best_session(self, session: dict[str, Any] | None) -> None:
        if not session:
            self.best_detail.setText(self._t("spotify.best.empty"))
            self.best_tracks.setText(self._t("spotify.best.empty.detail"))
            return
        started = self._local_date(session.get("started_at"))
        earned = int(session.get("earned_cents") or 0) / 100
        products = int(session.get("product_count") or 0)
        self.best_detail.setText(
            self._t(
                "spotify.best.detail",
                date=started,
                amount=f"€{earned:,.2f}",
                products=products,
            )
        )
        tracks = session.get("tracks") or []
        self.best_tracks.setText(
            " · ".join(
                f"{row.get('name', '—')} — {row.get('artists', '')}" for row in tracks[:6]
            )
            or self._t("spotify.best.no_tracks")
        )

    @staticmethod
    def _fill_table(table: QTableWidget, rows, *, ranked: bool) -> None:
        table.setRowCount(len(rows))
        for index, (title, subtitle, value) in enumerate(rows):
            rank = QTableWidgetItem(str(index + 1) if ranked else "")
            name = QTableWidgetItem(str(title))
            if subtitle:
                name.setToolTip(str(subtitle))
                name.setText(f"{title}\n{subtitle}")
            metric = QTableWidgetItem(str(value))
            metric.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(index, 0, rank)
            table.setItem(index, 1, name)
            table.setItem(index, 2, metric)
            table.setRowHeight(index, 48 if subtitle else 38)

    def _clear_data(self) -> None:
        self._apply_playback(None)
        self.device_combo.clear()
        self.work_tracks.setRowCount(0)
        self._apply_local({})

    @staticmethod
    def _clock(milliseconds: int) -> str:
        seconds = max(0, int(milliseconds) // 1000)
        return f"{seconds // 60}:{seconds % 60:02d}"

    @staticmethod
    def _local_date(value) -> str:
        if not value:
            return "—"
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone()
            return parsed.strftime("%d %b %Y")
        except Exception:
            return str(value)

    def _show_error(self, message: str, *, quiet: bool) -> None:
        if quiet and not self.isVisible():
            return
        InfoBar.error(
            title=self._t("spotify.error.title"),
            content=str(message),
            parent=self,
            position=InfoBarPosition.TOP,
            duration=5000,
        )

    # ------------------------------------------------------- responsiveness
    @staticmethod
    def _take_grid(layout: QGridLayout) -> None:
        while layout.count():
            layout.takeAt(0)

    def _on_breakpoint_changed(self, breakpoint: str) -> None:
        self._take_grid(self.metrics_grid)
        metrics = (self.plays_metric, self.tracks_metric, self.sessions_metric)
        columns = 1 if breakpoint == "xs" else 2 if breakpoint == "sm" else 3
        for index, widget in enumerate(metrics):
            self.metrics_grid.addWidget(widget, index // columns, index % columns)
        self._take_grid(self.tables_grid)
        self.tables_grid.addWidget(self.work_tracks_card, 0, 0)

    # --------------------------------------------------------- translations
    def retranslate_ui(self) -> None:
        self.title.setText(self._t("spotify.title"))
        self.refresh_button.setText(self._t("spotify.refresh"))
        self.connect_button.setText(self._t("spotify.connect"))
        self.disconnect_button.setText(self._t("spotify.disconnect"))
        self.now_playing_title.setText(self._t("spotify.player.title"))
        self.previous_button.setText(self._t("spotify.player.previous"))
        self.next_button.setText(self._t("spotify.player.next"))
        self.volume_title.setText(self._t("spotify.player.volume"))
        self.analytics_title.setText(self._t("spotify.analytics.title"))
        self.plays_metric_title.setText(self._t("spotify.metric.work_plays"))
        self.tracks_metric_title.setText(self._t("spotify.metric.tracks"))
        self.sessions_metric_title.setText(self._t("spotify.metric.sessions"))
        self.work_tracks_title.setText(self._t("spotify.work.tracks"))
        self.work_tracks_note.setText(self._t("spotify.work.note"))
        self.best_title.setText(self._t("spotify.best.title"))
        self._set_connected_state(self.spotify.is_connected())
        self._apply_playback((self._last_snapshot or {}).get("playback"))
        if self._last_snapshot:
            self._apply_snapshot(self._last_snapshot)

    # ------------------------------------------------------------- lifecycle
    def on_activated(self) -> None:
        if self.spotify.is_connected():
            self._poll_timer.setInterval(self.FOREGROUND_POLL_INTERVAL_MS)
            self._poll_timer.start()
            self._playback_tick_timer.start()
            self._poll_playback()
            self.refresh_dashboard()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.spotify.is_connected():
            self._poll_timer.setInterval(self.FOREGROUND_POLL_INTERVAL_MS)
            self._poll_timer.start()
            self._playback_tick_timer.start()
            QTimer.singleShot(0, self._poll_playback)

    def hideEvent(self, event) -> None:
        if self.spotify.is_connected():
            self._poll_timer.setInterval(self.BACKGROUND_POLL_INTERVAL_MS)
            self._poll_timer.start()
        self._playback_tick_timer.stop()
        super().hideEvent(event)

    def shutdown(self, wait_ms: int = 5000) -> bool:
        self._poll_timer.stop()
        self._playback_tick_timer.stop()
        workers = (
            self._auth_worker,
            self._dashboard_worker,
            self._poll_worker,
            self._command_worker,
        )
        for worker in workers:
            if worker is not None and worker.isRunning():
                stopper = getattr(worker, "request_stop", None)
                if callable(stopper):
                    stopper()
                else:
                    worker.requestInterruption()
        deadline_each = max(250, int(wait_ms) // max(1, len(workers)))
        return all(
            worker is None or not worker.isRunning() or worker.wait(deadline_each)
            for worker in workers
        )

    def _apply_theme(self) -> None:
        apply_screen_theme(self, "SpotifyScreen", scroll=self.scroll, content=self.content)
        dark = isDarkTheme()
        text = COLORS["text_primary_dark" if dark else "text_primary_light"]
        muted = COLORS["text_secondary_dark" if dark else "text_secondary_light"]
        surface = get_surface_color(dark)
        alternate = get_surface_color(dark, "alternate")
        border = get_subtle_border(dark)
        accent = COLORS["lavender_grey" if dark else "space_indigo"]
        self.setStyleSheet(
            self.styleSheet()
            + f"""
            SpotifyScreen CardWidget {{
                background-color: {surface};
                border: 1px solid {border};
                border-radius: {RADII['md']}px;
            }}
            SpotifyScreen QLabel#spotifyTrackName {{
                color: {text}; font-size: 24px; font-weight: 700;
                background: transparent; border: none;
            }}
            SpotifyScreen QLabel#spotifyMetricValue {{
                color: {text}; font-size: 30px; font-weight: 700;
                background: transparent; border: none;
            }}
            SpotifyScreen QProgressBar {{
                background-color: {alternate}; border: none; border-radius: 2px;
            }}
            SpotifyScreen QProgressBar::chunk {{
                background-color: {accent}; border-radius: 2px;
            }}
            SpotifyScreen QTableWidget {{
                background-color: {surface}; alternate-background-color: {alternate};
                color: {text}; border: none;
            }}
            SpotifyScreen QHeaderView::section {{
                background-color: {alternate}; color: {muted}; border: none;
                padding: 6px;
            }}
            """
        )

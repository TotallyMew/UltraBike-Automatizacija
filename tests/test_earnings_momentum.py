from __future__ import annotations

import os
import sqlite3
import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from Database.DatabaseManager import DatabaseManager
from Database.SettingsManager import SettingsManager
from GUI_Qt.earnings.dialogs import QuestPickerDialog, SessionRecapDialog
from GUI_Qt.earnings.widgets import QuestCelebrationOverlay, QuestProgressWidget
from GUI_Qt.i18n import translate
from GUI_Qt.screens.EarningsScreen import EarningsScreen
from Managers.EarningsManager import EarningsManager


UTC = timezone.utc


class _I18n:
    @staticmethod
    def tr(key, **values):
        return translate("en", key, **values)


class _Main(QWidget):
    def __init__(self, db, settings, manager):
        super().__init__()
        self.db = db
        self.settings = settings
        self.earnings_manager = manager
        self.i18n = _I18n()


def moment(day: int, hour: int = 9, minute: int = 0) -> datetime:
    return datetime(2026, 8, day, hour, minute, tzinfo=UTC)


@pytest.fixture()
def manager_context():
    db = DatabaseManager(":memory:")
    settings = SettingsManager(db)
    manager = EarningsManager(db, settings, local_tz=UTC)
    try:
        yield db, settings, manager
    finally:
        db.close()


def complete_session(
    manager: EarningsManager,
    *,
    day: int,
    minutes: int,
    products: int,
    quest_kind: str | None = None,
    quest_target: int | None = None,
) -> int:
    started = moment(day)
    session_id = manager.start_session(
        "stopwatch",
        quest_kind=quest_kind,
        quest_target_value=quest_target,
        now=started,
    )
    for index in range(products):
        manager.create_entry(
            f"DAY-{day}-SKU-{index}",
            "bicycle",
            now=started + timedelta(seconds=index + 1),
        )
    manager.finish_session(now=started + timedelta(minutes=minutes))
    return session_id


def test_schema_v4_upgrades_a_v3_session_table_without_losing_rows(tmp_path: Path):
    path = tmp_path / "legacy-v3.db"
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE work_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mode TEXT NOT NULL,
            target_seconds INTEGER,
            status TEXT NOT NULL,
            allow_overtime INTEGER NOT NULL DEFAULT 0,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    stamp = "2026-08-01T09:00:00.000000Z"
    connection.execute(
        """
        INSERT INTO work_sessions
            (mode, status, allow_overtime, started_at, created_at, updated_at)
        VALUES ('stopwatch', 'completed', 0, ?, ?, ?)
        """,
        (stamp, stamp, stamp),
    )
    connection.execute("PRAGMA user_version = 3")
    connection.commit()
    connection.close()

    upgraded = DatabaseManager(path)
    try:
        assert upgraded.conn.execute("PRAGMA user_version").fetchone()[0] == 6
        row = upgraded.conn.execute("SELECT * FROM work_sessions WHERE id=1").fetchone()
        assert row["mode"] == "stopwatch"
        assert row["quest_kind"] is None
        assert row["quest_target_value"] is None
        assert row["quest_completed_at"] is None
    finally:
        upgraded.close()


def test_adaptive_quest_fallbacks_and_engagement_defaults(manager_context):
    _db, _settings, manager = manager_context
    presets = manager.quest_presets()

    assert presets["sku"]["target_value"] == 10
    assert presets["earnings"]["target_value"] == 1_000
    assert presets["focus"]["target_value"] == 45 * 60
    assert manager.engagement_settings() == {
        "animations_enabled": True,
        "sound_enabled": False,
    }

    manager.set_rate_cents("bicycle", 125)
    manager.set_rate_cents("frameset", 200)
    manager.set_rate_cents("other", 75)
    assert manager.quest_presets()["earnings"]["target_value"] == 1_500


def test_adaptive_quest_history_uses_productive_medians_rounding_and_clamps(manager_context):
    _db, _settings, manager = manager_context
    complete_session(manager, day=1, minutes=31, products=11)
    complete_session(manager, day=2, minutes=34, products=15)
    complete_session(manager, day=3, minutes=38, products=18)

    presets = manager.quest_presets(now=moment(4))
    assert presets["sku"]["target_value"] == 15
    assert presets["earnings"]["target_value"] == 1_500
    assert presets["focus"]["target_value"] == 35 * 60
    assert presets["sku"]["sample_size"] == 3


def test_sku_quest_progress_survives_pause_and_completes_only_once(manager_context):
    db, settings, manager = manager_context
    started = moment(1)
    session_id = manager.start_session(
        "stopwatch", quest_kind="sku", quest_target_value=4, now=started
    )
    manager.create_entry("ONE", "bicycle", now=started + timedelta(minutes=1))
    manager.pause_session(now=started + timedelta(minutes=2))
    manager.create_entry("PAUSED", "bicycle", now=started + timedelta(minutes=3))

    paused = manager.session_quest_progress(session_id, now=started + timedelta(minutes=4))
    assert paused["current_value"] == 1
    assert paused["reached_checkpoints"] == 1
    assert not paused["complete"]

    reopened = EarningsManager(db, settings, local_tz=UTC)
    reopened.resume_session(now=started + timedelta(minutes=5))
    for index in range(3):
        reopened.create_entry(
            f"MORE-{index}", "bicycle", now=started + timedelta(minutes=6 + index)
        )

    completed = reopened.session_quest_progress(
        session_id, now=started + timedelta(minutes=9)
    )
    assert completed["complete"]
    assert completed["newly_completed"]
    assert completed["bonus_target_value"] == 14
    assert completed["bonus_percent"] == 0
    completion_stamp = completed["completed_at"]

    repeated = reopened.session_quest_progress(
        session_id, now=started + timedelta(minutes=10)
    )
    assert repeated["completed_at"] == completion_stamp
    assert not repeated["newly_completed"]


def test_focus_quest_controls_countdown_and_waits_for_finish(manager_context):
    db, settings, manager = manager_context
    started = moment(1)
    session_id = manager.start_session(
        "stopwatch", quest_kind="focus", quest_target_value=25 * 60, now=started
    )
    snapshot = manager.timer_snapshot(now=started)
    assert snapshot.mode == "countdown"
    assert snapshot.target_seconds == 25 * 60

    manager.pause_session(now=started + timedelta(minutes=10))
    reopened = EarningsManager(db, settings, local_tz=UTC)
    paused = reopened.session_quest_progress(
        session_id, now=started + timedelta(minutes=20)
    )
    assert paused["current_value"] == 10 * 60

    reopened.resume_session(now=started + timedelta(minutes=20))
    expired = reopened.timer_snapshot(now=started + timedelta(minutes=36))
    assert expired.status == "paused"
    assert expired.remaining_seconds == 0
    assert reopened.get_session(session_id)["status"] == "paused"
    finished = reopened.finish_session(now=started + timedelta(minutes=36))
    assert finished["status"] == "completed"
    assert finished["quest_progress"]["complete"]


def test_recap_records_require_strict_improvement_and_qualified_hourly_rate(manager_context):
    _db, _settings, manager = manager_context
    first_id = complete_session(manager, day=1, minutes=10, products=5)
    first = manager.session_recap(first_id, now=moment(2))
    assert {item["key"] for item in first["record_callouts"]} == {
        "earnings",
        "products",
        "hourly_rate",
    }
    assert first["records"]["hourly_rate"]["status"] == "benchmark"

    tied_id = complete_session(manager, day=2, minutes=10, products=5)
    tied = manager.session_recap(tied_id, now=moment(3))
    assert tied["record_callouts"] == []

    short_id = complete_session(manager, day=3, minutes=5, products=4)
    short = manager.session_recap(short_id, now=moment(4))
    assert not short["records"]["hourly_rate"]["eligible"]
    assert short["records"]["hourly_rate"]["status"] is None

    best_id = complete_session(manager, day=4, minutes=12, products=7)
    best = manager.session_recap(best_id, now=moment(5))
    assert best["records"]["earnings"]["status"] == "record"
    assert best["records"]["products"]["status"] == "record"
    assert best["records"]["hourly_rate"]["status"] == "record"

    # Reopening an older recap compares it with sessions that existed at that
    # point in time, not with later work.
    historic_first = manager.session_recap(first_id, now=moment(6))
    assert historic_first["records"]["hourly_rate"]["status"] == "benchmark"


def test_recap_reports_the_sessions_money_goal_contribution(manager_context):
    _db, _settings, manager = manager_context
    manager.create_goal(10_000, now=moment(1, 8))
    session_id = complete_session(manager, day=1, minutes=20, products=3)

    recap = manager.session_recap(session_id, now=moment(2))
    assert recap["goal_contribution"] == {
        "goal_id": 1,
        "target_cents": 10_000,
        "contribution_cents": 300,
    }


def test_quest_and_recap_widgets_construct_and_animate(manager_context):
    app = QApplication.instance() or QApplication([])
    _db, _settings, manager = manager_context
    picker = QuestPickerDialog(manager)
    picker.quest_controls["sku"].setValue(25)
    picker._choose("sku")
    assert picker.values() == ("sku", 25)
    picker._choose_no_quest()
    assert picker.values() == (None, None)

    session_id = complete_session(
        manager, day=1, minutes=10, products=5, quest_kind="sku", quest_target=5
    )
    recap = manager.session_recap(session_id, now=moment(2))
    dialog = SessionRecapDialog(recap)
    assert dialog.recap["quest"]["complete"]

    host = QWidget()
    host.resize(480, 260)
    progress = QuestProgressWidget(host)
    progress.setGeometry(20, 20, 380, 90)
    progress.set_state(
        title="SKU quest",
        badge="50%",
        detail="5 of 10",
        percent=50,
        animated=False,
        complete=False,
    )
    overlay = QuestCelebrationOverlay(host)
    host.show()
    overlay.celebrate(completion=True, badge_text="Quest complete")
    app.processEvents()
    assert not overlay.isHidden()
    QTest.qWait(30)
    app.processEvents()

    for widget in (picker, dialog, host):
        widget.close()
        widget.deleteLater()
    app.processEvents()


def test_screen_starts_selected_focus_quest_and_shows_finish_recap(
    manager_context, monkeypatch
):
    app = QApplication.instance() or QApplication([])
    db, settings, manager = manager_context
    screen_module = importlib.import_module("GUI_Qt.screens.EarningsScreen")

    class FocusPicker:
        def __init__(self, *_args, **_kwargs):
            pass

        def exec(self):
            return 1

        @staticmethod
        def values():
            return "focus", 25 * 60

    captured = {}

    class Recap:
        def __init__(self, recap, *_args, **_kwargs):
            captured["recap"] = recap
            self.start_another = False

        @staticmethod
        def exec():
            return 1

    monkeypatch.setattr(screen_module, "QuestPickerDialog", FocusPicker)
    monkeypatch.setattr(screen_module, "SessionRecapDialog", Recap)
    main = _Main(db, settings, manager)
    screen = EarningsScreen(main)
    screen._start_or_resume()
    active = manager.timer_snapshot()

    assert active is not None
    assert active.mode == "countdown"
    assert active.target_seconds == 25 * 60
    assert manager.get_session(active.id)["quest_kind"] == "focus"
    assert not screen.quest_progress.isHidden()

    screen._finish_timer()
    assert captured["recap"]["session"]["status"] == "completed"
    assert manager.timer_snapshot() is None

    screen.close()
    screen.deleteLater()
    main.deleteLater()
    app.processEvents()


def test_screen_never_replays_existing_progress_and_respects_animation_toggle(
    manager_context
):
    app = QApplication.instance() or QApplication([])
    db, settings, manager = manager_context
    started = moment(1)
    session_id = manager.start_session(
        "stopwatch", quest_kind="sku", quest_target_value=4, now=started
    )
    manager.create_entry("ALREADY-SEEN", "bicycle", now=started + timedelta(minutes=1))
    main = _Main(db, settings, manager)
    screen = EarningsScreen(main)
    calls = []
    screen.quest_celebration.celebrate = lambda **values: calls.append(values)

    # Construction and refresh establish the persisted 25% state as a baseline.
    screen._timer_tick()
    screen.refresh_all()
    assert calls == []

    manager.set_engagement_settings(animations_enabled=False, sound_enabled=False)
    screen._engagement_settings = manager.engagement_settings()
    manager.create_entry("MUTED-CHECKPOINT", "bicycle", now=started + timedelta(minutes=2))
    screen._timer_tick()
    assert calls == []

    manager.set_engagement_settings(animations_enabled=True, sound_enabled=False)
    screen._engagement_settings = manager.engagement_settings()
    manager.create_entry("VISIBLE-CHECKPOINT", "bicycle", now=started + timedelta(minutes=3))
    screen._timer_tick()
    assert calls == [{"completion": False}]

    screen.close()
    screen.deleteLater()
    main.deleteLater()
    app.processEvents()

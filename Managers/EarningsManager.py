"""Persistent earnings, work-timer, goal, and forecasting services."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from typing import Any, Iterable


UTC = timezone.utc


class ProductType(str, Enum):
    BICYCLE = "bicycle"
    FRAMESET = "frameset"
    OTHER = "other"


class TimerMode(str, Enum):
    STOPWATCH = "stopwatch"
    COUNTDOWN = "countdown"


class SessionStatus(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"


class QuestKind(str, Enum):
    SKU = "sku"
    EARNINGS = "earnings"
    FOCUS = "focus"


class GoalStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"
    CANCELLED = "cancelled"


class ActiveSessionError(RuntimeError):
    pass


class ActiveGoalError(RuntimeError):
    pass


@dataclass(frozen=True)
class TimerSnapshot:
    id: int
    mode: str
    status: str
    target_seconds: int | None
    elapsed_seconds: float
    remaining_seconds: float | None
    allow_overtime: bool
    expired: bool = False


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_utc(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class EarningsManager:
    """Single boundary for earnings and timer state.

    The GUI intentionally delegates calculations to this class so the same
    behavior is testable with an in-memory SQLite database.
    """

    RATE_KEYS = {
        ProductType.BICYCLE.value: "earning_rate_bicycle_cents",
        ProductType.FRAMESET.value: "earning_rate_frameset_cents",
        ProductType.OTHER.value: "earning_rate_other_cents",
    }
    DEFAULT_RATES = {
        ProductType.BICYCLE.value: 100,
        ProductType.FRAMESET.value: 100,
        ProductType.OTHER.value: 75,
    }

    def __init__(self, db_manager, settings_manager=None, local_tz=None):
        self.db = db_manager
        self.settings = settings_manager
        self.local_tz = local_tz or datetime.now().astimezone().tzinfo or UTC

    # ------------------------------------------------------------------ settings
    def get_rate_cents(self, product_type: str | ProductType) -> int:
        key = self._product_type(product_type)
        setting_key = self.RATE_KEYS[key]
        if self.settings is not None:
            return max(0, int(self.settings.get(setting_key, self.DEFAULT_RATES[key])))
        row = self.db.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (setting_key,)
        ).fetchone()
        return max(0, int(row[0])) if row else self.DEFAULT_RATES[key]

    def set_rate_cents(self, product_type: str | ProductType, cents: int) -> None:
        key = self._product_type(product_type)
        cents = int(cents)
        if cents < 0:
            raise ValueError("Payout cannot be negative")
        setting_key = self.RATE_KEYS[key]
        if self.settings is not None:
            self.settings.set(setting_key, cents)
            return
        self._upsert_int_setting(setting_key, cents)

    def performance_targets(self) -> dict[str, int]:
        keys = (
            "daily_earning_goal_cents", "weekly_earning_goal_cents",
            "daily_work_goal_minutes", "weekly_work_goal_minutes",
        )
        return {key: max(0, int(self._setting(key, 0))) for key in keys}

    def set_performance_targets(self, **values: int) -> None:
        allowed = set(self.performance_targets())
        for key, value in values.items():
            if key not in allowed:
                raise KeyError(key)
            value = max(0, int(value))
            if self.settings is not None:
                self.settings.set(key, value)
            else:
                self._upsert_int_setting(key, value)

    def work_schedule(self) -> dict[str, int]:
        """Return the schedule used for effective-rate income projections."""
        workday_minutes = min(24 * 60, max(15, self._setting("standard_workday_minutes", 8 * 60)))
        workdays_per_week = min(7, max(1, self._setting("standard_workdays_per_week", 5)))
        return {
            "workday_minutes": workday_minutes,
            "workdays_per_week": workdays_per_week,
        }

    def set_work_schedule(self, *, workday_minutes: int, workdays_per_week: int) -> None:
        workday_minutes = int(workday_minutes)
        workdays_per_week = int(workdays_per_week)
        if not 15 <= workday_minutes <= 24 * 60:
            raise ValueError("A normal workday must be between 15 minutes and 24 hours")
        if not 1 <= workdays_per_week <= 7:
            raise ValueError("Workdays per week must be between 1 and 7")
        for key, value in (
            ("standard_workday_minutes", workday_minutes),
            ("standard_workdays_per_week", workdays_per_week),
        ):
            if self.settings is not None:
                self.settings.set(key, value)
            else:
                self._upsert_int_setting(key, value)

    def engagement_settings(self) -> dict[str, bool]:
        return {
            "animations_enabled": self._bool_setting(
                "earnings_celebration_animations", True
            ),
            "sound_enabled": self._bool_setting(
                "earnings_celebration_sound", False
            ),
        }

    def set_engagement_settings(
        self, *, animations_enabled: bool, sound_enabled: bool
    ) -> None:
        values = {
            "earnings_celebration_animations": bool(animations_enabled),
            "earnings_celebration_sound": bool(sound_enabled),
        }
        if self.settings is not None:
            self.settings.set_many(values)
            return
        for key, value in values.items():
            self._upsert_bool_setting(key, value)

    def celebration_sound_volume(self) -> int:
        """Return the local success-chime volume as a safe percentage."""

        return min(
            100,
            max(0, int(self._setting("earnings_celebration_sound_volume", 45))),
        )

    def set_celebration_sound_volume(self, percent: int) -> None:
        value = min(100, max(0, int(percent)))
        if self.settings is not None:
            self.settings.set("earnings_celebration_sound_volume", value)
        else:
            self._upsert_int_setting("earnings_celebration_sound_volume", value)

    def quest_presets(self, now: datetime | None = None) -> dict[str, dict[str, Any]]:
        """Return adaptive, editable quest targets based on recent productive sessions."""

        rows = self.db.conn.execute(
            """
            SELECT id FROM work_sessions
            WHERE status='completed'
            ORDER BY completed_at DESC, id DESC
            LIMIT 50
            """
        ).fetchall()
        recent: list[dict[str, Any]] = []
        for row in rows:
            session = self.get_session(int(row["id"]), now=now)
            if int(session["product_count"]) <= 0:
                continue
            recent.append(session)
            if len(recent) == 10:
                break

        if recent:
            sku_raw = float(statistics.median(row["product_count"] for row in recent))
            earnings_raw = float(statistics.median(row["earned_cents"] for row in recent))
            focus_raw = float(statistics.median(row["elapsed_seconds"] for row in recent))
        else:
            sku_raw = 10.0
            average_payout = statistics.mean(
                self.get_rate_cents(kind) for kind in self.RATE_KEYS
            )
            earnings_raw = average_payout * 10.0
            focus_raw = 45.0 * 60.0

        sku_target = min(100, max(10, self._round_up(sku_raw, 5)))
        earnings_target = max(1_000, self._round_up(earnings_raw, 500))
        focus_target = min(
            90 * 60,
            max(25 * 60, self._round_nearest(focus_raw, 5 * 60)),
        )
        return {
            QuestKind.SKU.value: {
                "kind": QuestKind.SKU.value,
                "target_value": sku_target,
                "sample_size": len(recent),
            },
            QuestKind.EARNINGS.value: {
                "kind": QuestKind.EARNINGS.value,
                "target_value": earnings_target,
                "sample_size": len(recent),
            },
            QuestKind.FOCUS.value: {
                "kind": QuestKind.FOCUS.value,
                "target_value": focus_target,
                "sample_size": len(recent),
            },
        }

    def income_projections(
        self,
        *,
        effective_hourly_cents: float | int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Project a standard day, week, month and year at the measured rate.

        A month is the average calendar month (52 weeks divided by 12), while
        a year is 52 configured work weeks. These are pace estimates, not
        guaranteed earnings.
        """
        summary = self.summary(now=now)
        rate = summary["effective_hourly_cents"] if effective_hourly_cents is None else effective_hourly_cents
        schedule = self.work_schedule()
        day_hours = schedule["workday_minutes"] / 60.0
        week_hours = day_hours * schedule["workdays_per_week"]
        month_hours = week_hours * 52.0 / 12.0
        year_hours = week_hours * 52.0

        def projected(hours: float) -> int | None:
            return int(round(float(rate) * hours)) if rate is not None else None

        return {
            "effective_hourly_cents": float(rate) if rate is not None else None,
            "tracked_seconds": summary["all_seconds"],
            **schedule,
            "day_hours": day_hours,
            "week_hours": week_hours,
            "month_hours": month_hours,
            "year_hours": year_hours,
            "day_cents": projected(day_hours),
            "week_cents": projected(week_hours),
            "month_cents": projected(month_hours),
            "year_cents": projected(year_hours),
        }

    def _setting(self, key: str, default: int) -> int:
        if self.settings is not None:
            return int(self.settings.get(key, default))
        row = self.db.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return int(row[0]) if row else default

    def _bool_setting(self, key: str, default: bool) -> bool:
        if self.settings is not None:
            return bool(self.settings.get(key, default))
        row = self.db.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        if not row:
            return bool(default)
        return str(row[0]).strip().lower() == "true"

    def _upsert_int_setting(self, key: str, value: int) -> None:
        now = to_utc_iso(utc_now())
        self.db.conn.execute(
            """
            INSERT INTO settings(key, value, value_type, category, description, default_value, updated_at)
            VALUES (?, ?, 'int', 'earnings', '', ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, str(value), str(value), now),
        )
        self.db.conn.commit()

    def _upsert_bool_setting(self, key: str, value: bool) -> None:
        now = to_utc_iso(utc_now())
        encoded = "true" if value else "false"
        self.db.conn.execute(
            """
            INSERT INTO settings(key, value, value_type, category, description, default_value, updated_at)
            VALUES (?, ?, 'bool', 'earnings', '', ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, encoded, encoded, now),
        )
        self.db.conn.commit()

    # -------------------------------------------------------------------- brands
    def list_brands(self, active_only: bool = True) -> list[dict[str, Any]]:
        where = "WHERE is_active = 1" if active_only else ""
        rows = self.db.conn.execute(
            f"SELECT * FROM earning_brands {where} ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [dict(row) for row in rows]

    def add_brand(self, name: str, now: datetime | None = None) -> int:
        name = " ".join(str(name or "").split())
        if not name:
            raise ValueError("Brand name is required")
        stamp = to_utc_iso(now or utc_now())
        existing = self.db.conn.execute(
            "SELECT id, is_active FROM earning_brands WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if existing:
            if not existing["is_active"]:
                self.db.conn.execute(
                    "UPDATE earning_brands SET is_active=1, updated_at=? WHERE id=?",
                    (stamp, existing["id"]),
                )
                self.db.conn.commit()
            return int(existing["id"])
        cursor = self.db.conn.execute(
            """
            INSERT INTO earning_brands(name, is_builtin, is_active, created_at, updated_at)
            VALUES (?, 0, 1, ?, ?)
            """,
            (name, stamp, stamp),
        )
        self.db.conn.commit()
        return int(cursor.lastrowid)

    def rename_brand(self, brand_id: int, name: str, now: datetime | None = None) -> None:
        row = self._brand(brand_id)
        if row["is_builtin"]:
            raise ValueError("Built-in scraper brands cannot be renamed")
        name = " ".join(str(name or "").split())
        if not name:
            raise ValueError("Brand name is required")
        self.db.conn.execute(
            "UPDATE earning_brands SET name=?, updated_at=? WHERE id=?",
            (name, to_utc_iso(now or utc_now()), brand_id),
        )
        self.db.conn.commit()

    def archive_brand(self, brand_id: int, now: datetime | None = None) -> None:
        row = self._brand(brand_id)
        if row["is_builtin"]:
            raise ValueError("Built-in scraper brands cannot be archived")
        self.db.conn.execute(
            "UPDATE earning_brands SET is_active=0, updated_at=? WHERE id=?",
            (to_utc_iso(now or utc_now()), brand_id),
        )
        self.db.conn.commit()

    def _brand(self, brand_id: int):
        row = self.db.conn.execute(
            "SELECT * FROM earning_brands WHERE id=?", (int(brand_id),)
        ).fetchone()
        if row is None:
            raise ValueError("Unknown brand")
        return row

    # ------------------------------------------------------------------- entries
    def duplicate_sku_count(self, sku: str, exclude_id: int | None = None) -> int:
        params: list[Any] = [str(sku or "").strip()]
        sql = "SELECT COUNT(*) FROM earning_entries WHERE sku = ? COLLATE NOCASE"
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(int(exclude_id))
        return int(self.db.conn.execute(sql, params).fetchone()[0])

    def create_entry(
        self,
        sku: str,
        product_type: str | ProductType,
        *,
        product_name: str | None = None,
        brand_id: int | None = None,
        earned_at: datetime | str | None = None,
        source: str = "manual",
        session_id: int | None = None,
        processing_history_id: int | None = None,
        now: datetime | None = None,
    ) -> int:
        sku = str(sku or "").strip()
        if not sku:
            raise ValueError("SKU is required")
        ptype = self._product_type(product_type)
        if brand_id is not None:
            brand = self._brand(brand_id)
            if not brand["is_active"]:
                raise ValueError("Archived brands cannot be used for new entries")
        stamp_dt = now or utc_now()
        stamp = to_utc_iso(stamp_dt)
        earned_stamp = self._normalize_user_datetime(earned_at, stamp_dt)
        if session_id is None:
            # A countdown may have expired since the last UI tick.  Sync it
            # before deciding whether this earning belongs to tracked work.
            self.sync_timer(now=stamp_dt)
            active = self._unfinished_session()
            session_id = (
                int(active["id"])
                if active and active["status"] == SessionStatus.RUNNING.value
                else None
            )
        if session_id is not None:
            self._session(int(session_id))
        if processing_history_id is not None and self.is_processing_imported(processing_history_id):
            raise ValueError("This upload has already been added to earnings")
        cursor = self.db.conn.execute(
            """
            INSERT INTO earning_entries
                (sku, product_name, brand_id, product_type, payout_cents, earned_at,
                 source, session_id, processing_history_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sku, self._optional(product_name), brand_id, ptype,
                self.get_rate_cents(ptype), earned_stamp, str(source or "manual"),
                session_id, processing_history_id, stamp, stamp,
            ),
        )
        self.db.conn.commit()
        self.complete_goal_if_reached(now=stamp_dt)
        return int(cursor.lastrowid)

    def update_entry(
        self,
        entry_id: int,
        *,
        sku: str,
        product_type: str | ProductType,
        product_name: str | None = None,
        brand_id: int | None = None,
        earned_at: datetime | str | None = None,
        now: datetime | None = None,
    ) -> None:
        existing = self.db.conn.execute(
            "SELECT * FROM earning_entries WHERE id=?", (int(entry_id),)
        ).fetchone()
        if existing is None:
            raise ValueError("Unknown earning entry")
        sku = str(sku or "").strip()
        if not sku:
            raise ValueError("SKU is required")
        ptype = self._product_type(product_type)
        if brand_id is not None:
            self._brand(brand_id)
        payout = int(existing["payout_cents"])
        if ptype != existing["product_type"]:
            payout = self.get_rate_cents(ptype)
        stamp_dt = now or utc_now()
        earned_stamp = existing["earned_at"] if earned_at is None else self._normalize_user_datetime(earned_at, stamp_dt)
        self.db.conn.execute(
            """
            UPDATE earning_entries
            SET sku=?, product_name=?, brand_id=?, product_type=?, payout_cents=?,
                earned_at=?, updated_at=?
            WHERE id=?
            """,
            (
                sku, self._optional(product_name), brand_id, ptype, payout,
                earned_stamp, to_utc_iso(stamp_dt), int(entry_id),
            ),
        )
        self.db.conn.commit()
        self.complete_goal_if_reached(now=stamp_dt)

    def bulk_update_entries(
        self,
        entry_ids: Iterable[int],
        *,
        update_brand: bool = False,
        brand_id: int | None = None,
        product_type: str | ProductType | None = None,
        earned_at: datetime | str | None = None,
        now: datetime | None = None,
    ) -> int:
        """Update shared metadata for several earnings in one transaction.

        Payouts are historical snapshots and are deliberately preserved when
        the product type is corrected in bulk.
        """

        ids = tuple(dict.fromkeys(int(entry_id) for entry_id in entry_ids))
        if not ids:
            raise ValueError("Select at least one earning entry")
        if not update_brand and product_type is None and earned_at is None:
            raise ValueError("Choose at least one field to update")

        if update_brand and brand_id is not None:
            brand = self._brand(int(brand_id))
            if not brand["is_active"]:
                raise ValueError("Archived brands cannot be applied in bulk")
            brand_id = int(brand_id)
        ptype = self._product_type(product_type) if product_type is not None else None
        stamp_dt = now or utc_now()
        earned_stamp = (
            self._normalize_user_datetime(earned_at, stamp_dt)
            if earned_at is not None
            else None
        )
        updated_stamp = to_utc_iso(stamp_dt)

        # Validate every target before starting any writes. This avoids a
        # partially edited selection if a stale UI row was removed elsewhere.
        for entry_id in ids:
            if self.db.conn.execute(
                "SELECT 1 FROM earning_entries WHERE id=?", (entry_id,)
            ).fetchone() is None:
                raise ValueError(f"Unknown earning entry: {entry_id}")

        assignments: list[str] = []
        values: list[Any] = []
        if update_brand:
            assignments.append("brand_id=?")
            values.append(brand_id)
        if ptype is not None:
            assignments.append("product_type=?")
            values.append(ptype)
        if earned_stamp is not None:
            assignments.append("earned_at=?")
            values.append(earned_stamp)
        assignments.append("updated_at=?")
        values.append(updated_stamp)

        sql = f"UPDATE earning_entries SET {', '.join(assignments)} WHERE id=?"
        with self.db.conn:
            self.db.conn.executemany(sql, [(*values, entry_id) for entry_id in ids])
        self.complete_goal_if_reached(now=stamp_dt)
        return len(ids)

    def delete_entry(self, entry_id: int) -> None:
        self.db.conn.execute("DELETE FROM earning_entries WHERE id=?", (int(entry_id),))
        self.db.conn.commit()

    def is_processing_imported(self, processing_history_id: int) -> bool:
        row = self.db.conn.execute(
            "SELECT 1 FROM earning_entries WHERE processing_history_id=?",
            (int(processing_history_id),),
        ).fetchone()
        return row is not None

    def list_entries(
        self,
        *,
        search: str = "",
        brand_id: int | None = None,
        product_type: str | None = None,
        source: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if search.strip():
            token = f"%{search.strip()}%"
            conditions.append("(e.sku LIKE ? OR e.product_name LIKE ? OR b.name LIKE ?)")
            params.extend((token, token, token))
        if brand_id is not None:
            conditions.append("e.brand_id=?")
            params.append(int(brand_id))
        if product_type:
            conditions.append("e.product_type=?")
            params.append(self._product_type(product_type))
        if source:
            conditions.append("e.source=?")
            params.append(source)
        if start:
            conditions.append("e.earned_at>=?")
            params.append(to_utc_iso(start))
        if end:
            conditions.append("e.earned_at<?")
            params.append(to_utc_iso(end))
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        rows = self.db.conn.execute(
            f"""
            SELECT e.*, b.name AS brand_name
            FROM earning_entries e
            LEFT JOIN earning_brands b ON b.id=e.brand_id
            {where}
            ORDER BY e.earned_at DESC, e.id DESC
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    # --------------------------------------------------------------------- timer
    def start_session(
        self,
        mode: str | TimerMode,
        target_seconds: int | None = None,
        *,
        quest_kind: str | QuestKind | None = None,
        quest_target_value: int | None = None,
        now: datetime | None = None,
    ) -> int:
        if self._unfinished_session() is not None:
            raise ActiveSessionError("Finish or reset the current session first")
        quest_value = self._quest_kind(quest_kind)
        if quest_value is None:
            if quest_target_value is not None:
                raise ValueError("A quest target requires a quest kind")
        else:
            quest_target_value = int(quest_target_value or 0)
            if quest_target_value <= 0:
                raise ValueError("Quest target must be greater than zero")
        mode_value = TimerMode(mode).value
        if quest_value == QuestKind.FOCUS.value:
            mode_value = TimerMode.COUNTDOWN.value
            target_seconds = quest_target_value
        if mode_value == TimerMode.COUNTDOWN.value:
            target_seconds = int(target_seconds or 0)
            if target_seconds <= 0:
                raise ValueError("Countdown duration must be greater than zero")
        else:
            target_seconds = None
        stamp = to_utc_iso(now or utc_now())
        cursor = self.db.conn.execute(
            """
            INSERT INTO work_sessions
                (mode, target_seconds, status, allow_overtime, started_at,
                 quest_kind, quest_target_value, created_at, updated_at)
            VALUES (?, ?, 'running', 0, ?, ?, ?, ?, ?)
            """,
            (
                mode_value,
                target_seconds,
                stamp,
                quest_value,
                quest_target_value,
                stamp,
                stamp,
            ),
        )
        session_id = int(cursor.lastrowid)
        self.db.conn.execute(
            "INSERT INTO work_segments(session_id, started_at) VALUES (?, ?)",
            (session_id, stamp),
        )
        self.db.conn.commit()
        return session_id

    def timer_snapshot(self, now: datetime | None = None) -> TimerSnapshot | None:
        now = now or utc_now()
        expired = self.sync_timer(now=now)
        row = self._unfinished_session()
        if row is None:
            return None
        elapsed = self.session_elapsed_seconds(int(row["id"]), now=now)
        target = int(row["target_seconds"]) if row["target_seconds"] is not None else None
        remaining = max(0.0, target - elapsed) if target is not None else None
        return TimerSnapshot(
            id=int(row["id"]), mode=row["mode"], status=row["status"],
            target_seconds=target, elapsed_seconds=elapsed,
            remaining_seconds=remaining, allow_overtime=bool(row["allow_overtime"]),
            expired=expired,
        )

    def sync_timer(self, now: datetime | None = None) -> bool:
        """Pause a non-overtime countdown exactly at zero. Returns True once."""
        row = self._unfinished_session()
        if row is None or row["status"] != SessionStatus.RUNNING.value:
            return False
        if row["mode"] != TimerMode.COUNTDOWN.value or row["allow_overtime"]:
            return False
        now = now or utc_now()
        target = float(row["target_seconds"] or 0)
        closed = self._closed_segment_seconds(int(row["id"]))
        remaining = max(0.0, target - closed)
        segment = self._open_segment(int(row["id"]))
        if segment is None:
            return False
        start = parse_utc(segment["started_at"])
        expiry = start + timedelta(seconds=remaining)
        if now < expiry:
            return False
        stamp = to_utc_iso(expiry)
        self.db.conn.execute("UPDATE work_segments SET ended_at=? WHERE id=?", (stamp, segment["id"]))
        self.db.conn.execute(
            "UPDATE work_sessions SET status='paused', updated_at=? WHERE id=?",
            (stamp, row["id"]),
        )
        self.db.conn.commit()
        return True

    def pause_session(self, now: datetime | None = None) -> TimerSnapshot:
        now = now or utc_now()
        self.sync_timer(now=now)
        row = self._unfinished_session()
        if row is None:
            raise ValueError("No active work session")
        if row["status"] == SessionStatus.RUNNING.value:
            segment = self._open_segment(int(row["id"]))
            if segment:
                self.db.conn.execute(
                    "UPDATE work_segments SET ended_at=? WHERE id=?",
                    (to_utc_iso(now), segment["id"]),
                )
            self.db.conn.execute(
                "UPDATE work_sessions SET status='paused', updated_at=? WHERE id=?",
                (to_utc_iso(now), row["id"]),
            )
            self.db.conn.commit()
        return self.timer_snapshot(now=now)  # type: ignore[return-value]

    def resume_session(self, *, overtime: bool = False, now: datetime | None = None) -> TimerSnapshot:
        now = now or utc_now()
        row = self._unfinished_session()
        if row is None:
            raise ValueError("No paused work session")
        if row["status"] == SessionStatus.RUNNING.value:
            return self.timer_snapshot(now=now)  # type: ignore[return-value]
        elapsed = self.session_elapsed_seconds(int(row["id"]), now=now)
        target = row["target_seconds"]
        if row["mode"] == TimerMode.COUNTDOWN.value and target is not None and elapsed >= float(target):
            if not overtime:
                raise ValueError("Countdown finished; resume as overtime")
            self.db.conn.execute(
                "UPDATE work_sessions SET allow_overtime=1 WHERE id=?", (row["id"],)
            )
        stamp = to_utc_iso(now)
        self.db.conn.execute(
            "INSERT INTO work_segments(session_id, started_at) VALUES (?, ?)",
            (row["id"], stamp),
        )
        self.db.conn.execute(
            "UPDATE work_sessions SET status='running', updated_at=? WHERE id=?",
            (stamp, row["id"]),
        )
        self.db.conn.commit()
        return self.timer_snapshot(now=now)  # type: ignore[return-value]

    def finish_session(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or utc_now()
        self.sync_timer(now=now)
        row = self._unfinished_session()
        if row is None:
            raise ValueError("No active work session")
        if row["status"] == SessionStatus.RUNNING.value:
            segment = self._open_segment(int(row["id"]))
            if segment:
                self.db.conn.execute(
                    "UPDATE work_segments SET ended_at=? WHERE id=?",
                    (to_utc_iso(now), segment["id"]),
                )
        stamp = to_utc_iso(now)
        self.db.conn.execute(
            "UPDATE work_sessions SET status='completed', completed_at=?, updated_at=? WHERE id=?",
            (stamp, stamp, row["id"]),
        )
        self.db.conn.commit()
        return self.get_session(int(row["id"]), now=now)

    def reset_session(self) -> None:
        row = self._unfinished_session()
        if row is None:
            return
        self.db.conn.execute("DELETE FROM work_sessions WHERE id=?", (row["id"],))
        self.db.conn.commit()

    def session_elapsed_seconds(self, session_id: int, now: datetime | None = None) -> float:
        now = now or utc_now()
        session = self._session(session_id)
        seconds = self._closed_segment_seconds(session_id)
        segment = self._open_segment(session_id)
        if segment:
            seconds += max(0.0, (now - parse_utc(segment["started_at"])).total_seconds())
        if session["mode"] == TimerMode.COUNTDOWN.value and not session["allow_overtime"]:
            seconds = min(seconds, float(session["target_seconds"] or 0))
        return seconds

    def get_session(self, session_id: int, now: datetime | None = None) -> dict[str, Any]:
        row = dict(self._session(session_id))
        row["elapsed_seconds"] = self.session_elapsed_seconds(session_id, now=now)
        totals = self._entry_stats(
            None,
            now,
            timed_only=True,
            session_id=session_id,
        )
        row["product_count"] = totals["count"]
        row["earned_cents"] = totals["earned_cents"]
        row["hourly_cents"] = (
            row["earned_cents"] * 3600.0 / row["elapsed_seconds"]
            if row["elapsed_seconds"] > 0 else None
        )
        row["quest_progress"] = self._quest_progress_from_values(
            row,
            product_count=row["product_count"],
            earned_cents=row["earned_cents"],
            elapsed_seconds=row["elapsed_seconds"],
            now=now,
        )
        return row

    def session_quest_progress(
        self, session_id: int, now: datetime | None = None
    ) -> dict[str, Any] | None:
        session = self.get_session(session_id, now=now)
        return session["quest_progress"]

    def _quest_progress_from_values(
        self,
        session: dict[str, Any],
        *,
        product_count: int,
        earned_cents: int,
        elapsed_seconds: float,
        now: datetime | None,
    ) -> dict[str, Any] | None:
        kind = session.get("quest_kind")
        target = session.get("quest_target_value")
        if not kind or target is None:
            return None
        kind = QuestKind(kind).value
        target = int(target)
        current = {
            QuestKind.SKU.value: int(product_count),
            QuestKind.EARNINGS.value: int(earned_cents),
            QuestKind.FOCUS.value: int(elapsed_seconds),
        }[kind]
        checkpoints = sorted(
            {
                max(1, int(math.ceil(target * fraction)))
                for fraction in (0.25, 0.50, 0.75, 1.0)
            }
        )
        reached = sum(1 for value in checkpoints if current >= value)
        complete = current >= target
        completed_at = session.get("quest_completed_at")
        newly_completed = False
        if complete and not completed_at:
            stamp = to_utc_iso(now or utc_now())
            self.db.conn.execute(
                """
                UPDATE work_sessions
                SET quest_completed_at=?, updated_at=?
                WHERE id=? AND quest_completed_at IS NULL
                """,
                (stamp, stamp, int(session["id"])),
            )
            self.db.conn.commit()
            completed_at = stamp
            session["quest_completed_at"] = stamp
            newly_completed = True

        next_checkpoint = next(
            (value for value in checkpoints if current < value), None
        )
        bonus_target = None
        bonus_complete = False
        bonus_percent = None
        if complete:
            step = {
                QuestKind.SKU.value: 10,
                QuestKind.EARNINGS.value: 1_000,
                QuestKind.FOCUS.value: 15 * 60,
            }[kind]
            bonus_target = target + step
            bonus_complete = current >= bonus_target
            bonus_percent = min(100.0, max(0, current - target) * 100.0 / step)
        return {
            "kind": kind,
            "target_value": target,
            "current_value": current,
            "percent": min(100.0, current * 100.0 / target),
            "checkpoints": checkpoints,
            "reached_checkpoints": reached,
            "next_checkpoint_value": next_checkpoint,
            "complete": complete,
            "completed_at": completed_at,
            "newly_completed": newly_completed,
            "bonus_target_value": bonus_target,
            "bonus_complete": bonus_complete,
            "bonus_percent": bonus_percent,
        }

    def session_recap(
        self, session_id: int, now: datetime | None = None
    ) -> dict[str, Any]:
        session = self.get_session(session_id, now=now)
        if session["status"] != SessionStatus.COMPLETED.value:
            raise ValueError("Only completed work sessions have a recap")

        prior_rows = self.db.conn.execute(
            """
            SELECT id FROM work_sessions
            WHERE status='completed'
              AND (
                    completed_at < ?
                    OR (completed_at = ? AND id < ?)
                  )
            ORDER BY completed_at DESC, id DESC
            """,
            (
                session["completed_at"],
                session["completed_at"],
                int(session_id),
            ),
        ).fetchall()
        prior = [self.get_session(int(row["id"]), now=now) for row in prior_rows]

        def record_state(
            key: str,
            value: float | int | None,
            candidates: list[float | int],
            *,
            eligible: bool = True,
        ) -> dict[str, Any]:
            previous_best = max(candidates) if candidates else None
            status = None
            if eligible and value is not None:
                if previous_best is None:
                    status = "benchmark"
                elif float(value) > float(previous_best):
                    status = "record"
            return {
                "key": key,
                "value": value,
                "eligible": eligible,
                "previous_best": previous_best,
                "status": status,
            }

        qualified = (
            int(session["product_count"]) >= 5
            and float(session["elapsed_seconds"]) >= 10 * 60
            and session["hourly_cents"] is not None
        )
        prior_qualified_rates = [
            float(item["hourly_cents"])
            for item in prior
            if int(item["product_count"]) >= 5
            and float(item["elapsed_seconds"]) >= 10 * 60
            and item["hourly_cents"] is not None
        ]
        records = {
            "earnings": record_state(
                "earnings",
                int(session["earned_cents"]),
                [int(item["earned_cents"]) for item in prior],
            ),
            "products": record_state(
                "products",
                int(session["product_count"]),
                [int(item["product_count"]) for item in prior],
            ),
            "hourly_rate": record_state(
                "hourly_rate",
                session["hourly_cents"],
                prior_qualified_rates,
                eligible=qualified,
            ),
        }
        return {
            "session": session,
            "quest": session["quest_progress"],
            "goal_contribution": self._session_goal_contribution(session),
            "records": records,
            "record_callouts": [
                value for value in records.values() if value["status"] is not None
            ],
        }

    def _session_goal_contribution(self, session: dict[str, Any]) -> dict[str, Any] | None:
        session_end = session.get("completed_at") or session.get("updated_at")
        goal = self.db.conn.execute(
            """
            SELECT id, target_cents, started_at, completed_at
            FROM earning_goals
            WHERE started_at<=?
              AND (completed_at IS NULL OR completed_at>=?)
            ORDER BY id DESC LIMIT 1
            """,
            (session_end, session["started_at"]),
        ).fetchone()
        if goal is None:
            return None
        row = self.db.conn.execute(
            """
            SELECT COALESCE(SUM(payout_cents), 0)
            FROM earning_entries
            WHERE session_id=? AND earned_at>=?
              AND (? IS NULL OR earned_at<=?)
            """,
            (
                int(session["id"]),
                goal["started_at"],
                goal["completed_at"],
                goal["completed_at"],
            ),
        ).fetchone()
        return {
            "goal_id": int(goal["id"]),
            "target_cents": int(goal["target_cents"]),
            "contribution_cents": int(row[0]),
        }

    def list_sessions(self, now: datetime | None = None) -> list[dict[str, Any]]:
        rows = self.db.conn.execute("SELECT id FROM work_sessions ORDER BY started_at DESC").fetchall()
        return [self.get_session(int(row["id"]), now=now) for row in rows]

    def _unfinished_session(self):
        return self.db.conn.execute(
            "SELECT * FROM work_sessions WHERE status IN ('running', 'paused') ORDER BY id DESC LIMIT 1"
        ).fetchone()

    def _session(self, session_id: int):
        row = self.db.conn.execute("SELECT * FROM work_sessions WHERE id=?", (int(session_id),)).fetchone()
        if row is None:
            raise ValueError("Unknown work session")
        return row

    def _open_segment(self, session_id: int):
        return self.db.conn.execute(
            "SELECT * FROM work_segments WHERE session_id=? AND ended_at IS NULL ORDER BY id DESC LIMIT 1",
            (int(session_id),),
        ).fetchone()

    def _closed_segment_seconds(self, session_id: int) -> float:
        rows = self.db.conn.execute(
            "SELECT started_at, ended_at FROM work_segments WHERE session_id=? AND ended_at IS NOT NULL",
            (int(session_id),),
        ).fetchall()
        return sum(max(0.0, (parse_utc(r["ended_at"]) - parse_utc(r["started_at"])).total_seconds()) for r in rows)

    # --------------------------------------------------------------------- goals
    def active_goal(self) -> dict[str, Any] | None:
        row = self.db.conn.execute(
            "SELECT * FROM earning_goals WHERE status='active' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def create_goal(
        self,
        target_cents: int,
        deadline_date: str | date | None = None,
        *,
        replace_status: str | GoalStatus | None = None,
        now: datetime | None = None,
    ) -> int:
        target_cents = int(target_cents)
        if target_cents <= 0:
            raise ValueError("Goal amount must be greater than zero")
        active = self.active_goal()
        if active:
            if replace_status is None:
                raise ActiveGoalError("An earnings goal is already active")
            status = GoalStatus(replace_status).value
            if status not in (GoalStatus.ARCHIVED.value, GoalStatus.CANCELLED.value):
                raise ValueError("Active goals can only be archived or cancelled")
            self.close_goal(int(active["id"]), status=status, now=now)
        deadline = self._deadline(deadline_date)
        stamp = to_utc_iso(now or utc_now())
        cursor = self.db.conn.execute(
            """
            INSERT INTO earning_goals
                (target_cents, started_at, deadline_date, status, created_at, updated_at)
            VALUES (?, ?, ?, 'active', ?, ?)
            """,
            (target_cents, stamp, deadline, stamp, stamp),
        )
        self.db.conn.commit()
        return int(cursor.lastrowid)

    def update_goal(
        self, goal_id: int, target_cents: int, deadline_date: str | date | None,
        *, now: datetime | None = None,
    ) -> None:
        row = self.db.conn.execute("SELECT status FROM earning_goals WHERE id=?", (goal_id,)).fetchone()
        if row is None or row["status"] != GoalStatus.ACTIVE.value:
            raise ValueError("Only the active goal can be edited")
        target_cents = int(target_cents)
        if target_cents <= 0:
            raise ValueError("Goal amount must be greater than zero")
        self.db.conn.execute(
            "UPDATE earning_goals SET target_cents=?, deadline_date=?, updated_at=? WHERE id=?",
            (target_cents, self._deadline(deadline_date), to_utc_iso(now or utc_now()), goal_id),
        )
        self.db.conn.commit()
        self.complete_goal_if_reached(now=now)

    def add_goal_adjustment(
        self,
        goal_id: int,
        amount_cents: int,
        note: str | None = None,
        *,
        now: datetime | None = None,
    ) -> int:
        """Add audited goal progress without creating an earnings entry."""

        amount_cents = int(amount_cents)
        if amount_cents <= 0:
            raise ValueError("Goal adjustment must be greater than zero")
        note = " ".join(str(note or "").split()) or None
        stamp = to_utc_iso(now or utc_now())
        with self.db.write_lock, self.db.conn:
            goal = self.db.conn.execute(
                "SELECT status FROM earning_goals WHERE id=?", (int(goal_id),)
            ).fetchone()
            if goal is None or goal["status"] != GoalStatus.ACTIVE.value:
                raise ValueError("Only the active goal can receive an adjustment")
            cursor = self.db.conn.execute(
                """
                INSERT INTO earning_goal_adjustments
                    (goal_id, amount_cents, note, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (int(goal_id), amount_cents, note, stamp),
            )
            adjustment_id = int(cursor.lastrowid)
        self.complete_goal_if_reached(now=now)
        return adjustment_id

    def add_goal_adjustment_to_total(
        self,
        goal_id: int,
        total_cents: int,
        note: str | None = None,
        *,
        now: datetime | None = None,
    ) -> tuple[int, int]:
        """Set a higher displayed goal total by recording only its difference.

        The adjustment remains auditable and does not create or alter an earnings
        entry. Returns ``(adjustment_id, difference_cents)``.
        """

        goal = self._goal(int(goal_id))
        if goal is None or goal["status"] != GoalStatus.ACTIVE.value:
            raise ValueError("Only the active goal can receive an adjustment")
        total_cents = int(total_cents)
        current_cents = int(self.goal_progress(int(goal_id), now=now)["earned_cents"])
        difference_cents = total_cents - current_cents
        if difference_cents <= 0:
            raise ValueError("New goal progress must be greater than current progress")
        adjustment_id = self.add_goal_adjustment(
            int(goal_id),
            difference_cents,
            note,
            now=now,
        )
        return adjustment_id, difference_cents

    def list_goal_adjustments(self, goal_id: int) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.db.conn.execute(
                """
                SELECT id, goal_id, amount_cents, note, created_at
                FROM earning_goal_adjustments
                WHERE goal_id=?
                ORDER BY created_at DESC, id DESC
                """,
                (int(goal_id),),
            ).fetchall()
        ]

    def close_goal(self, goal_id: int, *, status: str | GoalStatus, now: datetime | None = None) -> None:
        status_value = GoalStatus(status).value
        if status_value not in (GoalStatus.ARCHIVED.value, GoalStatus.CANCELLED.value):
            raise ValueError("Invalid goal close status")
        progress = self.goal_progress(goal_id, now=now)
        stamp = to_utc_iso(now or utc_now())
        self.db.conn.execute(
            """
            UPDATE earning_goals
            SET status=?, completed_at=?, final_earned_cents=?, final_product_count=?,
                final_tracked_seconds=?, updated_at=?
            WHERE id=? AND status='active'
            """,
            (
                status_value, stamp, progress["earned_cents"], progress["product_count"],
                progress["tracked_seconds"], stamp, goal_id,
            ),
        )
        self.db.conn.commit()

    def complete_goal_if_reached(self, now: datetime | None = None) -> bool:
        goal = self.active_goal()
        if not goal:
            return False
        progress = self.goal_progress(int(goal["id"]), now=now)
        if progress["earned_cents"] < int(goal["target_cents"]):
            return False
        stamp = to_utc_iso(now or utc_now())
        self.db.conn.execute(
            """
            UPDATE earning_goals
            SET status='completed', completed_at=?, final_earned_cents=?,
                final_product_count=?, final_tracked_seconds=?, updated_at=?
            WHERE id=? AND status='active'
            """,
            (
                stamp, progress["earned_cents"], progress["product_count"],
                progress["tracked_seconds"], stamp, goal["id"],
            ),
        )
        self.db.conn.commit()
        return True

    def goal_progress(self, goal_id: int, now: datetime | None = None) -> dict[str, Any]:
        row = self.db.conn.execute("SELECT * FROM earning_goals WHERE id=?", (goal_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown earnings goal")
        adjustment_row = self.db.conn.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM earning_goal_adjustments WHERE goal_id=?",
            (int(goal_id),),
        ).fetchone()
        adjustment_cents = int(adjustment_row[0] or 0)
        if row["status"] != GoalStatus.ACTIVE.value and row["final_earned_cents"] is not None:
            earned = int(row["final_earned_cents"])
            earnings_cents = max(0, earned - adjustment_cents)
            count = int(row["final_product_count"] or 0)
            tracked = float(row["final_tracked_seconds"] or 0)
        else:
            end = now or utc_now()
            totals = self.db.conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(payout_cents), 0) FROM earning_entries WHERE earned_at>=? AND earned_at<=?",
                (row["started_at"], to_utc_iso(end)),
            ).fetchone()
            count, earnings_cents = int(totals[0]), int(totals[1])
            earned = earnings_cents + adjustment_cents
            tracked = self.tracked_seconds_between(parse_utc(row["started_at"]), end)
        target = int(row["target_cents"])
        return {
            "goal": dict(row), "earned_cents": earned,
            "earnings_cents": earnings_cents,
            "adjustment_cents": adjustment_cents,
            "product_count": count,
            "tracked_seconds": tracked, "remaining_cents": max(0, target - earned),
            "percent": min(100.0, earned * 100.0 / target),
        }

    def goal_forecast(self, goal_id: int | None = None, now: datetime | None = None) -> dict[str, Any] | None:
        now = now or utc_now()
        goal = self.active_goal() if goal_id is None else self._goal(goal_id)
        if not goal:
            return None
        progress = self.goal_progress(int(goal["id"]), now=now)
        remaining = int(progress["remaining_cents"])
        recent_start = now - timedelta(days=30)
        recent_entries = self._entry_stats(recent_start, now)
        all_entries = self._entry_stats(None, now)
        recent_timed_entries = self._entry_stats(recent_start, now, timed_only=True)
        all_timed_entries = self._entry_stats(None, now, timed_only=True)
        product_stats = recent_entries if recent_entries["count"] >= 5 else all_entries
        product_basis = "last_30_days" if product_stats is recent_entries else "all_time"
        likely_products = None
        if product_stats["count"] > 0 and product_stats["earned_cents"] > 0:
            average = product_stats["earned_cents"] / product_stats["count"]
            likely_products = math.ceil(remaining / average) if remaining else 0
        rates = [value for value in (self.get_rate_cents(t) for t in self.RATE_KEYS) if value > 0]
        optimistic = math.ceil(remaining / max(rates)) if remaining and rates else 0
        conservative = math.ceil(remaining / min(rates)) if remaining and rates else 0

        recent_seconds = self.tracked_seconds_between(recent_start, now)
        recent_rate = recent_timed_entries["earned_cents"] * 3600.0 / recent_seconds if recent_seconds > 0 else 0.0
        all_seconds = self.tracked_seconds_between(None, now)
        all_rate = all_timed_entries["earned_cents"] * 3600.0 / all_seconds if all_seconds > 0 else 0.0
        if recent_seconds >= 3600 and recent_timed_entries["earned_cents"] > 0:
            rate, seconds_sample, time_basis = recent_rate, recent_seconds, "last_30_days"
        elif all_seconds >= 3600 and all_timed_entries["earned_cents"] > 0:
            rate, seconds_sample, time_basis = all_rate, all_seconds, "all_time"
        else:
            rate, seconds_sample, time_basis = 0.0, all_seconds, "insufficient"
        hours_remaining = remaining / rate if remaining and rate > 0 else (0.0 if not remaining else None)

        deadline = self._deadline_metrics(goal.get("deadline_date"), remaining, likely_products, hours_remaining, now)
        return {
            **progress,
            "likely_products": likely_products,
            "optimistic_products": optimistic,
            "conservative_products": conservative,
            "estimated_hours": hours_remaining,
            "average_payout_cents": (
                product_stats["earned_cents"] / product_stats["count"] if product_stats["count"] else None
            ),
            "product_basis": product_basis,
            "product_sample": product_stats["count"],
            "time_basis": time_basis,
            "time_sample_seconds": seconds_sample,
            "effective_hourly_cents": rate or None,
            "deadline": deadline,
        }

    def list_goals(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.conn.execute(
            """
            SELECT g.*,
                   COALESCE((
                       SELECT SUM(a.amount_cents)
                       FROM earning_goal_adjustments a
                       WHERE a.goal_id=g.id
                   ), 0) AS adjustment_cents
            FROM earning_goals g
            ORDER BY g.created_at DESC
            """
        ).fetchall()]

    def _goal(self, goal_id: int) -> dict[str, Any] | None:
        row = self.db.conn.execute("SELECT * FROM earning_goals WHERE id=?", (goal_id,)).fetchone()
        return dict(row) if row else None

    # --------------------------------------------------------------- analytics
    def summary(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or utc_now()
        local_now = now.astimezone(self.local_tz)
        day_start_local = datetime.combine(local_now.date(), time.min, self.local_tz)
        week_start_local = day_start_local - timedelta(days=day_start_local.weekday())
        day_start = day_start_local.astimezone(UTC)
        week_start = week_start_local.astimezone(UTC)
        today = self._entry_stats(day_start, now)
        week = self._entry_stats(week_start, now)
        yesterday = self._entry_stats(day_start - timedelta(days=1), day_start)
        previous_week = self._entry_stats(week_start - timedelta(days=7), week_start)
        all_time = self._entry_stats(None, now)
        timed_all_time = self._entry_stats(None, now, timed_only=True)
        today_seconds = self.tracked_seconds_between(day_start, now)
        week_seconds = self.tracked_seconds_between(week_start, now)
        all_seconds = self.tracked_seconds_between(None, now)
        return {
            "today_cents": today["earned_cents"], "today_count": today["count"],
            "week_cents": week["earned_cents"], "week_count": week["count"],
            "yesterday_cents": yesterday["earned_cents"],
            "previous_week_cents": previous_week["earned_cents"],
            "all_cents": all_time["earned_cents"], "all_count": all_time["count"],
            "timed_cents": timed_all_time["earned_cents"],
            "timed_count": timed_all_time["count"],
            "untimed_cents": all_time["earned_cents"] - timed_all_time["earned_cents"],
            "untimed_count": all_time["count"] - timed_all_time["count"],
            "today_seconds": today_seconds, "week_seconds": week_seconds,
            "all_seconds": all_seconds,
            "effective_hourly_cents": (
                timed_all_time["earned_cents"] * 3600.0 / all_seconds
                if all_seconds > 0 else None
            ),
        }

    def tracked_seconds_between(self, start: datetime | None, end: datetime | None) -> float:
        end = end or utc_now()
        self.sync_timer(now=end)
        start = start.astimezone(UTC) if start else None
        end = end.astimezone(UTC)
        rows = self.db.conn.execute(
            """
            SELECT s.started_at, s.ended_at, w.mode, w.target_seconds, w.allow_overtime
            FROM work_segments s JOIN work_sessions w ON w.id=s.session_id
            """
        ).fetchall()
        total = 0.0
        for row in rows:
            seg_start = parse_utc(row["started_at"])
            seg_end = parse_utc(row["ended_at"]) if row["ended_at"] else end
            overlap_start = max(seg_start, start) if start else seg_start
            overlap_end = min(seg_end, end)
            if overlap_end > overlap_start:
                total += (overlap_end - overlap_start).total_seconds()
        return total

    def trend_data(self, period: str, now: datetime | None = None) -> list[dict[str, Any]]:
        now = (now or utc_now()).astimezone(self.local_tz)
        period = period.lower()
        starts: list[datetime]
        formatter: Any
        advance: Any
        if period == "hourly":
            current = now.replace(minute=0, second=0, microsecond=0)
            starts = [current - timedelta(hours=i) for i in reversed(range(24))]
            formatter, advance = lambda d: d.strftime("%H:%M"), lambda d: d + timedelta(hours=1)
        elif period == "daily":
            current = datetime.combine(now.date(), time.min, self.local_tz)
            starts = [current - timedelta(days=i) for i in reversed(range(30))]
            formatter, advance = lambda d: d.strftime("%d %b"), lambda d: d + timedelta(days=1)
        elif period == "weekly":
            current = datetime.combine(now.date() - timedelta(days=now.weekday()), time.min, self.local_tz)
            starts = [current - timedelta(weeks=i) for i in reversed(range(12))]
            formatter, advance = lambda d: f"W{d.isocalendar().week}", lambda d: d + timedelta(weeks=1)
        elif period == "monthly":
            current = datetime(now.year, now.month, 1, tzinfo=self.local_tz)
            starts = [self._add_months(current, -i) for i in reversed(range(12))]
            formatter, advance = lambda d: d.strftime("%b %y"), lambda d: self._add_months(d, 1)
        elif period == "quarterly":
            current = datetime(now.year, ((now.month - 1) // 3) * 3 + 1, 1, tzinfo=self.local_tz)
            starts = [self._add_months(current, -3 * i) for i in reversed(range(8))]
            formatter = lambda d: f"Q{((d.month - 1) // 3) + 1} {d.year}"
            advance = lambda d: self._add_months(d, 3)
        elif period == "yearly":
            starts = [datetime(now.year - i, 1, 1, tzinfo=self.local_tz) for i in reversed(range(5))]
            formatter, advance = lambda d: str(d.year), lambda d: datetime(d.year + 1, 1, 1, tzinfo=self.local_tz)
        else:
            entries = self.list_entries()
            if not entries:
                return []
            first = parse_utc(entries[-1]["earned_at"]).astimezone(self.local_tz)
            span = (now - first).days
            if span <= 60:
                current = datetime.combine(first.date(), time.min, self.local_tz)
                starts = [current + timedelta(days=i) for i in range((now.date() - first.date()).days + 1)]
                formatter, advance = lambda d: d.strftime("%d %b"), lambda d: d + timedelta(days=1)
            elif span <= 1095:
                current = datetime(first.year, first.month, 1, tzinfo=self.local_tz)
                starts = []
                while current <= now:
                    starts.append(current)
                    current = self._add_months(current, 1)
                formatter, advance = lambda d: d.strftime("%b %y"), lambda d: self._add_months(d, 1)
            else:
                starts = [datetime(y, 1, 1, tzinfo=self.local_tz) for y in range(first.year, now.year + 1)]
                formatter, advance = lambda d: str(d.year), lambda d: datetime(d.year + 1, 1, 1, tzinfo=self.local_tz)
        result: list[dict[str, Any]] = []
        for bucket_start in starts:
            bucket_end = advance(bucket_start)
            stats = self._entry_stats(bucket_start.astimezone(UTC), bucket_end.astimezone(UTC))
            result.append({"label": formatter(bucket_start), "cents": stats["earned_cents"], "count": stats["count"]})
        return result

    def type_breakdown(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.conn.execute(
            """
            SELECT product_type, COUNT(*) AS count, COALESCE(SUM(payout_cents),0) AS cents
            FROM earning_entries GROUP BY product_type ORDER BY cents DESC
            """
        ).fetchall()]

    def brand_breakdown(self, limit: int = 8) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.conn.execute(
            """
            SELECT COALESCE(b.name, 'No brand') AS brand, COUNT(*) AS count,
                   COALESCE(SUM(e.payout_cents),0) AS cents
            FROM earning_entries e LEFT JOIN earning_brands b ON b.id=e.brand_id
            GROUP BY e.brand_id ORDER BY cents DESC LIMIT ?
            """,
            (int(limit),),
        ).fetchall()]

    def performance_progress(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or utc_now()
        summary = self.summary(now)
        targets = self.performance_targets()
        return {
            **targets,
            "daily_earned_cents": summary["today_cents"],
            "weekly_earned_cents": summary["week_cents"],
            "daily_work_minutes": summary["today_seconds"] / 60.0,
            "weekly_work_minutes": summary["week_seconds"] / 60.0,
            "streak": self._daily_streak(now, targets),
        }

    # ------------------------------------------------------------------ helpers
    def _entry_stats(
        self,
        start: datetime | None,
        end: datetime | None,
        *,
        timed_only: bool = False,
        session_id: int | None = None,
    ) -> dict[str, int]:
        conditions, params = [], []
        timestamp_column = "e.created_at" if timed_only else "e.earned_at"
        if start:
            conditions.append(f"{timestamp_column}>=?")
            params.append(to_utc_iso(start))
        if end:
            conditions.append(f"{timestamp_column}<?")
            params.append(to_utc_iso(end))
        if session_id is not None:
            conditions.append("e.session_id=?")
            params.append(int(session_id))
        if timed_only:
            conditions.append(
                """
                e.session_id IS NOT NULL AND EXISTS (
                    SELECT 1 FROM work_segments s
                    WHERE s.session_id=e.session_id
                      AND e.created_at>=s.started_at
                      AND (s.ended_at IS NULL OR e.created_at<=s.ended_at)
                )
                """
            )
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        row = self.db.conn.execute(
            f"SELECT COUNT(*), COALESCE(SUM(e.payout_cents),0) FROM earning_entries e {where}",
            params,
        ).fetchone()
        return {"count": int(row[0]), "earned_cents": int(row[1])}

    def _daily_streak(self, now: datetime, targets: dict[str, int]) -> int:
        earning_target = targets["daily_earning_goal_cents"]
        work_target = targets["daily_work_goal_minutes"]
        if earning_target <= 0 and work_target <= 0:
            return 0
        local_day = now.astimezone(self.local_tz).date()
        streak = 0
        for offset in range(3660):
            target_day = local_day - timedelta(days=offset)
            start_local = datetime.combine(target_day, time.min, self.local_tz)
            end_local = start_local + timedelta(days=1)
            earned = self._entry_stats(start_local.astimezone(UTC), end_local.astimezone(UTC))["earned_cents"]
            worked = self.tracked_seconds_between(start_local.astimezone(UTC), end_local.astimezone(UTC)) / 60.0
            met = (earning_target <= 0 or earned >= earning_target) and (work_target <= 0 or worked >= work_target)
            if met:
                streak += 1
                continue
            if offset == 0:  # An in-progress current day does not break yesterday's streak.
                continue
            break
        return streak

    def _deadline_metrics(self, raw, remaining, products, hours, now) -> dict[str, Any] | None:
        if not raw:
            return None
        deadline = date.fromisoformat(str(raw))
        today = now.astimezone(self.local_tz).date()
        days_delta = (deadline - today).days
        overdue = days_delta < 0
        days = max(1, days_delta + 1)
        return {
            "date": deadline.isoformat(), "overdue": overdue, "days_remaining": max(0, days_delta),
            "cents_per_day": remaining / days, "cents_per_week": remaining * 7 / days,
            "products_per_day": products / days if products is not None else None,
            "products_per_week": products * 7 / days if products is not None else None,
            "hours_per_day": hours / days if hours is not None else None,
            "hours_per_week": hours * 7 / days if hours is not None else None,
        }

    def _normalize_user_datetime(self, value, fallback: datetime) -> str:
        if value is None:
            return to_utc_iso(fallback)
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=self.local_tz)
        return to_utc_iso(value)

    @staticmethod
    def _optional(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _product_type(value: str | ProductType) -> str:
        return ProductType(value).value

    @staticmethod
    def _quest_kind(value: str | QuestKind | None) -> str | None:
        if value is None or value == "":
            return None
        return QuestKind(value).value

    @staticmethod
    def _round_up(value: float | int, step: int) -> int:
        return int(math.ceil(float(value) / step) * step)

    @staticmethod
    def _round_nearest(value: float | int, step: int) -> int:
        return int(math.floor(float(value) / step + 0.5) * step)

    @staticmethod
    def _deadline(value: str | date | None) -> str | None:
        if value is None or value == "":
            return None
        if isinstance(value, date):
            return value.isoformat()
        return date.fromisoformat(str(value)).isoformat()

    @staticmethod
    def _add_months(value: datetime, months: int) -> datetime:
        index = value.year * 12 + value.month - 1 + months
        return value.replace(year=index // 12, month=index % 12 + 1, day=1)

"""Persistent earnings, work-timer, goal, and forecasting services."""

from __future__ import annotations

import math
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
            active = self._unfinished_session()
            session_id = int(active["id"]) if active else None
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
        now: datetime | None = None,
    ) -> int:
        if self._unfinished_session() is not None:
            raise ActiveSessionError("Finish or reset the current session first")
        mode_value = TimerMode(mode).value
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
                (mode, target_seconds, status, allow_overtime, started_at, created_at, updated_at)
            VALUES (?, ?, 'running', 0, ?, ?, ?)
            """,
            (mode_value, target_seconds, stamp, stamp, stamp),
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
        totals = self.db.conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(payout_cents), 0) FROM earning_entries WHERE session_id=?",
            (session_id,),
        ).fetchone()
        row["product_count"] = int(totals[0])
        row["earned_cents"] = int(totals[1])
        row["hourly_cents"] = (
            row["earned_cents"] * 3600.0 / row["elapsed_seconds"]
            if row["elapsed_seconds"] > 0 else None
        )
        return row

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
        if row["status"] != GoalStatus.ACTIVE.value and row["final_earned_cents"] is not None:
            earned = int(row["final_earned_cents"])
            count = int(row["final_product_count"] or 0)
            tracked = float(row["final_tracked_seconds"] or 0)
        else:
            end = now or utc_now()
            totals = self.db.conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(payout_cents), 0) FROM earning_entries WHERE earned_at>=? AND earned_at<=?",
                (row["started_at"], to_utc_iso(end)),
            ).fetchone()
            count, earned = int(totals[0]), int(totals[1])
            tracked = self.tracked_seconds_between(parse_utc(row["started_at"]), end)
        target = int(row["target_cents"])
        return {
            "goal": dict(row), "earned_cents": earned, "product_count": count,
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
        recent_rate = recent_entries["earned_cents"] * 3600.0 / recent_seconds if recent_seconds > 0 else 0.0
        all_seconds = self.tracked_seconds_between(None, now)
        all_rate = all_entries["earned_cents"] * 3600.0 / all_seconds if all_seconds > 0 else 0.0
        if recent_seconds >= 3600 and recent_entries["earned_cents"] > 0:
            rate, seconds_sample, time_basis = recent_rate, recent_seconds, "last_30_days"
        elif all_seconds >= 3600 and all_entries["earned_cents"] > 0:
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
            "SELECT * FROM earning_goals ORDER BY created_at DESC"
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
        today_seconds = self.tracked_seconds_between(day_start, now)
        week_seconds = self.tracked_seconds_between(week_start, now)
        all_seconds = self.tracked_seconds_between(None, now)
        return {
            "today_cents": today["earned_cents"], "today_count": today["count"],
            "week_cents": week["earned_cents"], "week_count": week["count"],
            "yesterday_cents": yesterday["earned_cents"],
            "previous_week_cents": previous_week["earned_cents"],
            "all_cents": all_time["earned_cents"], "all_count": all_time["count"],
            "today_seconds": today_seconds, "week_seconds": week_seconds,
            "all_seconds": all_seconds,
            "effective_hourly_cents": (
                all_time["earned_cents"] * 3600.0 / all_seconds if all_seconds > 0 else None
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
    def _entry_stats(self, start: datetime | None, end: datetime | None) -> dict[str, int]:
        conditions, params = [], []
        if start:
            conditions.append("earned_at>=?")
            params.append(to_utc_iso(start))
        if end:
            conditions.append("earned_at<?")
            params.append(to_utc_iso(end))
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        row = self.db.conn.execute(
            f"SELECT COUNT(*), COALESCE(SUM(payout_cents),0) FROM earning_entries {where}", params
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

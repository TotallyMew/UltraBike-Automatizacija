"""Pure earnings formatting and goal presentation rules."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from Managers.EarningsManager import ProductType

PRODUCT_TYPES = (
    (ProductType.BICYCLE.value, "Bicycle"),
    (ProductType.FRAMESET.value, "Frameset"),
    (ProductType.OTHER.value, "Other"),
)


def money(cents: float | int | None) -> str:
    if cents is None:
        return "—"
    return f"€{float(cents) / 100:,.2f}"


def goal_progress_state(earned_cents: int, target_cents: int) -> dict[str, Any]:
    """Return safe textual and visual goal progress values.

    The actual percentage remains uncapped for an over-target summary while the
    progress-bar value is always constrained to its visual 0–100% range.
    """
    earned = max(0, int(earned_cents or 0))
    target = int(target_cents or 0)
    if target <= 0:
        return {
            "percent": 0.0,
            "visual_percent": 0.0,
            "reached": False,
            "remaining_cents": 0,
            "above_cents": 0,
        }
    percent = earned * 100.0 / target
    return {
        "percent": percent,
        "visual_percent": max(0.0, min(percent, 100.0)),
        "reached": earned >= target,
        "remaining_cents": max(0, target - earned),
        "above_cents": max(0, earned - target),
    }


def goal_level_state(
    earned_cents: int,
    target_cents: int,
    *,
    levels: int = 10,
) -> dict[str, Any]:
    """Split a money goal into level-like milestones without changing its value."""

    earned = max(0, int(earned_cents or 0))
    target = int(target_cents or 0)
    level_count = max(1, int(levels or 1))
    if target <= 0:
        return {
            "level": 0,
            "levels": level_count,
            "next_level": 1,
            "next_level_cents": 0,
            "complete": False,
        }
    if earned >= target:
        return {
            "level": level_count,
            "levels": level_count,
            "next_level": level_count,
            "next_level_cents": 0,
            "complete": True,
        }
    level = min(level_count - 1, (earned * level_count) // target)
    next_level = level + 1
    next_threshold = (target * next_level + level_count - 1) // level_count
    return {
        "level": level,
        "levels": level_count,
        "next_level": next_level,
        "next_level_cents": max(0, next_threshold - earned),
        "complete": False,
    }


def duration(seconds: float | int | None) -> str:
    seconds = max(0, int(seconds or 0))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def local_datetime(raw: str | None) -> str:
    if not raw:
        return ""
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone().strftime("%Y-%m-%d %H:%M")

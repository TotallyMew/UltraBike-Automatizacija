from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from Database.DatabaseManager import DatabaseManager
from Database.SettingsManager import SettingsManager
from Managers.EarningsManager import (
    ActiveGoalError,
    ActiveSessionError,
    EarningsManager,
    GoalStatus,
    ProductType,
)


UTC = timezone.utc


@pytest.fixture()
def manager():
    db = DatabaseManager(":memory:")
    settings = SettingsManager(db)
    service = EarningsManager(db, settings, local_tz=UTC)
    try:
        yield service
    finally:
        db.close()


def at(day: int, hour: int = 9, minute: int = 0) -> datetime:
    return datetime(2026, 8, day, hour, minute, tzinfo=UTC)


def test_schema_seeds_scraper_brands_idempotently():
    db = DatabaseManager(":memory:")
    try:
        names = [row["name"] for row in db.conn.execute("SELECT name FROM earning_brands")]
        assert set(names) == {
            "KROSS", "Pinarello", "Basso", "Factor", "TREK",
            "Rondo", "Octane", "Rascal", "Lee Cougan",
        }
        db._initialize_schema()
        assert db.conn.execute("SELECT COUNT(*) FROM earning_brands").fetchone()[0] == 9
    finally:
        db.close()


def test_entry_uses_rate_snapshot_and_allows_optional_fields(manager):
    first = manager.create_entry("SKU-1", ProductType.BICYCLE, now=at(1))
    manager.set_rate_cents(ProductType.BICYCLE, 125)
    second = manager.create_entry("SKU-2", ProductType.BICYCLE, now=at(2))
    rows = manager.list_entries()
    by_id = {row["id"]: row for row in rows}
    assert by_id[first]["payout_cents"] == 100
    assert by_id[first]["product_name"] is None
    assert by_id[first]["brand_name"] is None
    assert by_id[second]["payout_cents"] == 125


def test_duplicate_sku_warns_but_is_not_a_constraint(manager):
    manager.create_entry("same", "other", now=at(1))
    assert manager.duplicate_sku_count("SAME") == 1
    manager.create_entry("SAME", "other", now=at(2))
    assert manager.duplicate_sku_count("same") == 2


def test_custom_brand_can_be_archived_without_losing_history(manager):
    brand_id = manager.add_brand("Custom", now=at(1))
    manager.create_entry("SKU", "bicycle", brand_id=brand_id, now=at(1))
    manager.archive_brand(brand_id, now=at(2))
    assert all(row["id"] != brand_id for row in manager.list_brands())
    assert manager.list_entries()[0]["brand_name"] == "Custom"
    with pytest.raises(ValueError):
        manager.create_entry("SKU-2", "bicycle", brand_id=brand_id, now=at(2))


def test_bulk_edit_updates_shared_metadata_atomically_and_preserves_payouts(manager):
    first = manager.create_entry("ONE", "bicycle", now=at(1))
    second = manager.create_entry("TWO", "bicycle", now=at(2))
    brand_id = manager.add_brand("Bulk brand", now=at(3))
    manager.set_rate_cents("frameset", 275)

    updated = manager.bulk_update_entries(
        [first, second, first],
        update_brand=True,
        brand_id=brand_id,
        product_type="frameset",
        earned_at=at(4, 14, 30),
        now=at(5),
    )

    assert updated == 2
    rows = {row["id"]: row for row in manager.list_entries()}
    for entry_id in (first, second):
        assert rows[entry_id]["brand_id"] == brand_id
        assert rows[entry_id]["brand_name"] == "Bulk brand"
        assert rows[entry_id]["product_type"] == "frameset"
        assert rows[entry_id]["earned_at"] == "2026-08-04T14:30:00.000000Z"
        assert rows[entry_id]["payout_cents"] == 100

    with pytest.raises(ValueError, match="Unknown earning entry"):
        manager.bulk_update_entries(
            [first, 999_999], update_brand=True, brand_id=None, now=at(6)
        )
    assert manager.list_entries()[0]["brand_id"] == brand_id


def test_bulk_edit_requires_a_selection_and_a_field(manager):
    entry_id = manager.create_entry("ONE", "bicycle", now=at(1))
    with pytest.raises(ValueError, match="Select at least one"):
        manager.bulk_update_entries([], update_brand=True)
    with pytest.raises(ValueError, match="Choose at least one field"):
        manager.bulk_update_entries([entry_id])


def test_stopwatch_excludes_pauses_and_links_entries(manager):
    session_id = manager.start_session("stopwatch", now=at(1, 9))
    manager.pause_session(now=at(1, 10))
    manager.create_entry("PAUSED", "bicycle", now=at(1, 10, 30))
    manager.resume_session(now=at(1, 11))
    manager.create_entry("RUNNING", "bicycle", now=at(1, 11, 30))
    finished = manager.finish_session(now=at(1, 12, 30))
    assert finished["elapsed_seconds"] == pytest.approx(2.5 * 3600)
    assert finished["product_count"] == 1
    by_sku = {row["sku"]: row for row in manager.list_entries()}
    assert by_sku["PAUSED"]["session_id"] is None
    assert by_sku["RUNNING"]["session_id"] == session_id


def test_untimed_earnings_do_not_inflate_effective_hourly_rate(manager):
    manager.create_entry("UNTIMED-1", "bicycle", now=at(1, 8))
    manager.start_session("stopwatch", now=at(1, 9))
    manager.create_entry("TIMED", "bicycle", now=at(1, 9, 30))
    manager.finish_session(now=at(1, 10))
    manager.create_entry("UNTIMED-2", "bicycle", now=at(1, 11))

    summary = manager.summary(now=at(1, 12))
    assert summary["all_cents"] == 300
    assert summary["timed_cents"] == 100
    assert summary["untimed_cents"] == 200
    assert summary["untimed_count"] == 2
    assert summary["effective_hourly_cents"] == pytest.approx(100)


def test_expired_or_paused_timer_cannot_mark_earnings_as_timed(manager):
    countdown_id = manager.start_session("countdown", 1800, now=at(1, 9))
    manager.create_entry("EXPIRED", "bicycle", now=at(1, 10))
    expired = next(row for row in manager.list_entries() if row["sku"] == "EXPIRED")
    assert expired["session_id"] is None
    assert manager.get_session(countdown_id, now=at(1, 10))["product_count"] == 0
    manager.finish_session(now=at(1, 10))

    session_id = manager.start_session("stopwatch", now=at(2, 9))
    manager.pause_session(now=at(2, 10))
    manager.create_entry(
        "LEGACY-PAUSED", "bicycle", session_id=session_id, now=at(2, 10, 30)
    )
    manager.finish_session(now=at(2, 11))
    session = manager.get_session(session_id, now=at(2, 11))
    assert session["product_count"] == 0
    assert session["earned_cents"] == 0


def test_only_one_unfinished_session_and_reset_detaches_entries(manager):
    session_id = manager.start_session("stopwatch", now=at(1))
    manager.create_entry("SKU", "bicycle", now=at(1))
    with pytest.raises(ActiveSessionError):
        manager.start_session("stopwatch", now=at(1, 10))
    manager.reset_session()
    entry = manager.list_entries()[0]
    assert entry["session_id"] is None
    assert manager.db.conn.execute("SELECT 1 FROM work_sessions WHERE id=?", (session_id,)).fetchone() is None


def test_countdown_pauses_at_zero_and_can_resume_overtime(manager):
    manager.start_session("countdown", 1800, now=at(1, 9))
    snapshot = manager.timer_snapshot(now=at(1, 10))
    assert snapshot is not None
    assert snapshot.expired is True
    assert snapshot.status == "paused"
    assert snapshot.elapsed_seconds == pytest.approx(1800)
    with pytest.raises(ValueError):
        manager.resume_session(now=at(1, 10))
    manager.resume_session(overtime=True, now=at(1, 10))
    result = manager.finish_session(now=at(1, 10, 15))
    assert result["elapsed_seconds"] == pytest.approx(2700)


def test_goal_counts_only_entries_after_creation_and_completes(manager):
    manager.create_entry("OLD", "bicycle", now=at(1))
    goal_id = manager.create_goal(200, now=at(2))
    manager.create_entry("NEW1", "bicycle", now=at(3))
    progress = manager.goal_progress(goal_id, now=at(3, 10))
    assert progress["earned_cents"] == 100
    manager.create_entry("NEW2", "bicycle", now=at(4))
    goal = manager._goal(goal_id)
    assert goal["status"] == "completed"
    assert goal["final_earned_cents"] == 200
    assert goal["final_product_count"] == 2


def test_goal_replacement_requires_explicit_archive_or_cancel(manager):
    first = manager.create_goal(1000, now=at(1))
    with pytest.raises(ActiveGoalError):
        manager.create_goal(2000, now=at(2))
    second = manager.create_goal(2000, replace_status=GoalStatus.ARCHIVED, now=at(2))
    assert manager._goal(first)["status"] == "archived"
    assert manager._goal(second)["status"] == "active"


def test_goal_adjustment_changes_only_goal_progress(manager):
    goal_id = manager.create_goal(500, now=at(1, 8))
    manager.create_entry("PAID-PRODUCT", "bicycle", now=at(1, 9))

    adjustment_id = manager.add_goal_adjustment(
        goal_id, 200, "Opening balance", now=at(1, 10)
    )

    progress = manager.goal_progress(goal_id, now=at(1, 11))
    assert progress["earned_cents"] == 300
    assert progress["earnings_cents"] == 100
    assert progress["adjustment_cents"] == 200
    assert progress["product_count"] == 1
    assert manager.summary(now=at(1, 11))["all_cents"] == 100
    assert manager.list_goal_adjustments(goal_id) == [
        {
            "id": adjustment_id,
            "goal_id": goal_id,
            "amount_cents": 200,
            "note": "Opening balance",
            "created_at": "2026-08-01T10:00:00.000000Z",
        }
    ]


def test_goal_adjustment_can_complete_goal_but_requires_active_goal(manager):
    goal_id = manager.create_goal(250, now=at(1, 8))
    manager.add_goal_adjustment(goal_id, 250, now=at(1, 9))

    assert manager.active_goal() is None
    completed = manager._goal(goal_id)
    assert completed["status"] == "completed"
    assert completed["final_earned_cents"] == 250
    assert completed["final_product_count"] == 0
    assert manager.summary(now=at(1, 10))["all_cents"] == 0

    with pytest.raises(ValueError, match="active goal"):
        manager.add_goal_adjustment(goal_id, 100, now=at(1, 10))
    with pytest.raises(ValueError, match="greater than zero"):
        manager.add_goal_adjustment(goal_id, 0, now=at(1, 10))


def test_goal_adjustment_can_set_a_higher_current_total_from_the_difference(manager):
    goal_id = manager.create_goal(1_000, now=at(1, 8))
    manager.create_entry("PAID-PRODUCT", "bicycle", now=at(1, 9))
    manager.add_goal_adjustment(goal_id, 200, "Opening balance", now=at(1, 10))

    adjustment_id, difference_cents = manager.add_goal_adjustment_to_total(
        goal_id,
        450,
        "Updated account total",
        now=at(1, 11),
    )

    assert difference_cents == 150
    progress = manager.goal_progress(goal_id, now=at(1, 12))
    assert progress["earned_cents"] == 450
    assert progress["earnings_cents"] == 100
    assert progress["adjustment_cents"] == 350
    assert manager.list_goal_adjustments(goal_id)[0] == {
        "id": adjustment_id,
        "goal_id": goal_id,
        "amount_cents": 150,
        "note": "Updated account total",
        "created_at": "2026-08-01T11:00:00.000000Z",
    }

    with pytest.raises(ValueError, match="greater than current progress"):
        manager.add_goal_adjustment_to_total(goal_id, 450, now=at(1, 13))


def test_forecast_uses_recent_products_and_tracked_hourly_rate(manager):
    manager.create_goal(2000, now=at(1, 8))
    # Five recent bicycle entries unlock the recent-product forecast.
    for idx in range(5):
        started = at(2 + idx, 9)
        manager.start_session("stopwatch", now=started)
        manager.create_entry(f"SKU-{idx}", "bicycle", now=started + timedelta(minutes=30))
        manager.finish_session(now=started + timedelta(hours=1))
    forecast = manager.goal_forecast(now=at(10))
    assert forecast["earned_cents"] == 500
    assert forecast["remaining_cents"] == 1500
    assert forecast["likely_products"] == 15
    assert forecast["optimistic_products"] == 15
    assert forecast["conservative_products"] == 20
    assert forecast["estimated_hours"] == pytest.approx(15)
    assert forecast["product_basis"] == "last_30_days"
    assert forecast["time_basis"] == "last_30_days"


def test_forecast_without_history_uses_only_payout_bounds(manager):
    manager.create_goal(1000, now=at(1))
    forecast = manager.goal_forecast(now=at(1, 10))
    assert forecast["likely_products"] is None
    assert forecast["optimistic_products"] == 10
    assert forecast["conservative_products"] == 14
    assert forecast["estimated_hours"] is None
    assert forecast["time_basis"] == "insufficient"


def test_deadline_forecast_and_overdue_state(manager):
    manager.create_goal(700, deadline_date="2026-08-07", now=at(1))
    forecast = manager.goal_forecast(now=at(1))
    assert forecast["deadline"]["overdue"] is False
    assert forecast["deadline"]["cents_per_day"] == pytest.approx(100)
    overdue = manager.goal_forecast(now=at(8))
    assert overdue["deadline"]["overdue"] is True


def test_processing_history_import_is_deduplicated(manager):
    manager.create_entry("SKU", "bicycle", processing_history_id=42, now=at(1))
    assert manager.is_processing_imported(42)
    with pytest.raises(ValueError):
        manager.create_entry("SKU", "bicycle", processing_history_id=42, now=at(2))


def test_trend_windows_and_summary(manager):
    manager.create_entry("A", "bicycle", now=at(10, 8))
    manager.create_entry("B", "other", now=at(10, 9))
    summary = manager.summary(now=at(10, 12))
    assert summary["today_cents"] == 175
    assert summary["today_count"] == 2
    trend = manager.trend_data("hourly", now=at(10, 12))
    assert len(trend) == 24
    assert sum(bucket["cents"] for bucket in trend) == 175

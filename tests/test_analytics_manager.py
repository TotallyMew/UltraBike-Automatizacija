from datetime import datetime, timezone

from Database.DatabaseManager import DatabaseManager
from Database.SettingsManager import SettingsManager
from Managers.AnalyticsManager import AnalyticsManager
from Managers.EarningsManager import EarningsManager


UTC = timezone.utc


def _history(db, code, brand, status, processed_at, error=None):
    cursor = db.conn.execute(
        """
        INSERT INTO processing_history
            (brand, product_code, status, error_message, processed_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (brand, code, status, error, processed_at),
    )
    db.conn.commit()
    return int(cursor.lastrowid)


def test_snapshot_combines_manual_and_app_earnings_without_double_counting():
    db = DatabaseManager(":memory:")
    try:
        earnings = EarningsManager(db, SettingsManager(db), local_tz=UTC)
        basso = next(brand for brand in earnings.list_brands() if brand["name"] == "Basso")
        custom = earnings.add_brand("Outside brand", now=datetime(2026, 8, 19, tzinfo=UTC))
        history_id = _history(db, "APP-1", "Basso", "success", "2026-08-19 10:00:00")
        _history(db, "FAIL-1", "Basso", "failed", "2026-08-20 10:00:00", "Save failed")
        _history(db, "OLD", "Basso", "success", "2026-07-01 10:00:00")

        earnings.create_entry(
            "APP-1", "bicycle", brand_id=basso["id"], source="regular_upload",
            processing_history_id=history_id,
            earned_at=datetime(2026, 8, 19, 10, tzinfo=UTC),
            now=datetime(2026, 8, 19, 10, tzinfo=UTC),
        )
        earnings.create_entry(
            "OUTSIDE-1", "frameset", brand_id=custom,
            earned_at=datetime(2026, 8, 20, 11, tzinfo=UTC),
            now=datetime(2026, 8, 20, 11, tzinfo=UTC),
        )
        earnings.create_entry(
            "OLD-EARNING", "other", earned_at=datetime(2026, 7, 1, tzinfo=UTC),
            now=datetime(2026, 7, 1, tzinfo=UTC),
        )

        snapshot = AnalyticsManager(db).snapshot(
            days=7, now=datetime(2026, 8, 20, 12, tzinfo=UTC)
        )

        assert snapshot["earnings"] == {
            "product_count": 2,
            "earned_cents": 200,
            "manual_count": 1,
            "app_linked_count": 1,
        }
        assert snapshot["processing"]["total"] == 2
        assert snapshot["processing"]["succeeded"] == 1
        assert snapshot["processing"]["failed"] == 1
        assert snapshot["processing"]["success_rate"] == 50
        assert {row["label"]: row["count"] for row in snapshot["brands"]} == {
            "Basso": 1,
            "Outside brand": 1,
        }
        assert {row["label"]: row["count"] for row in snapshot["sources"]} == {
            "manual": 1,
            "regular_upload": 1,
        }
        assert {row["label"]: row["count"] for row in snapshot["product_types"]} == {
            "bicycle": 1,
            "frameset": 1,
        }
        assert [row["sku"] for row in snapshot["recent"]] == ["OUTSIDE-1", "APP-1"]
        assert snapshot["errors"] == [{"message": "Save failed", "count": 1}]
    finally:
        db.close()


def test_all_time_snapshot_includes_products_without_processing_history():
    db = DatabaseManager(":memory:")
    try:
        earnings = EarningsManager(db, SettingsManager(db), local_tz=UTC)
        earnings.create_entry(
            "EXTERNAL", "other", now=datetime(2025, 1, 1, tzinfo=UTC)
        )
        snapshot = AnalyticsManager(db).snapshot(days=None)
        assert snapshot["earnings"]["product_count"] == 1
        assert snapshot["earnings"]["manual_count"] == 1
        assert snapshot["processing"]["total"] == 0
    finally:
        db.close()

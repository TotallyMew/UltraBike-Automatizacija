"""Dependency-free regression tests for the earnings service."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from Database.DatabaseManager import DatabaseManager
from Database.SettingsManager import SettingsManager
from Managers.EarningsManager import ActiveGoalError, ActiveSessionError, EarningsManager


UTC = timezone.utc


class EarningsServiceTest(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.service = EarningsManager(self.db, SettingsManager(self.db), local_tz=UTC)

    def tearDown(self):
        self.db.close()

    @staticmethod
    def at(day, hour=9, minute=0):
        return datetime(2026, 8, day, hour, minute, tzinfo=UTC)

    def test_schema_brands_rates_and_optional_entry_fields(self):
        self.assertEqual(len(self.service.list_brands()), 9)
        first = self.service.create_entry("A", "bicycle", now=self.at(1))
        self.service.set_rate_cents("bicycle", 125)
        second = self.service.create_entry("B", "bicycle", now=self.at(2))
        rows = {row["id"]: row for row in self.service.list_entries()}
        self.assertEqual(rows[first]["payout_cents"], 100)
        self.assertEqual(rows[second]["payout_cents"], 125)
        self.assertIsNone(rows[first]["product_name"])
        self.assertIsNone(rows[first]["brand_id"])

    def test_effective_rate_income_projections_use_configured_schedule(self):
        empty = self.service.income_projections(now=self.at(1, 9))
        self.assertIsNone(empty["day_cents"])
        self.assertEqual(empty["workday_minutes"], 480)
        self.assertEqual(empty["workdays_per_week"], 5)

        self.service.set_rate_cents("bicycle", 3000)
        self.service.start_session("stopwatch", now=self.at(1, 9))
        self.service.create_entry("PROJECTION", "bicycle", now=self.at(1, 10))
        self.service.finish_session(now=self.at(1, 11))
        values = self.service.income_projections(now=self.at(1, 11))
        self.assertEqual(values["effective_hourly_cents"], 1500)
        self.assertEqual(values["day_cents"], 12000)
        self.assertEqual(values["week_cents"], 60000)
        self.assertEqual(values["month_cents"], 260000)
        self.assertEqual(values["year_cents"], 3120000)

        self.service.set_work_schedule(workday_minutes=360, workdays_per_week=4)
        custom = self.service.income_projections(now=self.at(1, 11))
        self.assertEqual(custom["day_cents"], 9000)
        self.assertEqual(custom["week_cents"], 36000)
        self.assertEqual(custom["month_cents"], 156000)
        self.assertEqual(custom["year_cents"], 1872000)

    def test_custom_brand_archival_preserves_history(self):
        brand_id = self.service.add_brand("Custom")
        self.service.create_entry("A", "other", brand_id=brand_id)
        self.service.archive_brand(brand_id)
        self.assertEqual(self.service.list_entries()[0]["brand_name"], "Custom")
        with self.assertRaises(ValueError):
            self.service.create_entry("B", "other", brand_id=brand_id)

    def test_stopwatch_pause_resume_and_reset_detach(self):
        session_id = self.service.start_session("stopwatch", now=self.at(1))
        self.service.pause_session(now=self.at(1, 10))
        self.service.create_entry("A", "bicycle", now=self.at(1, 10, 30))
        self.service.resume_session(now=self.at(1, 11))
        self.service.create_entry("A-TIMED", "bicycle", now=self.at(1, 11, 30))
        result = self.service.finish_session(now=self.at(1, 12, 30))
        self.assertAlmostEqual(result["elapsed_seconds"], 9000)
        self.assertEqual(result["product_count"], 1)
        by_sku = {row["sku"]: row for row in self.service.list_entries()}
        self.assertIsNone(by_sku["A"]["session_id"])
        self.assertEqual(by_sku["A-TIMED"]["session_id"], session_id)

        self.service.start_session("stopwatch", now=self.at(2))
        self.service.create_entry("B", "bicycle", now=self.at(2))
        with self.assertRaises(ActiveSessionError):
            self.service.start_session("stopwatch", now=self.at(2, 10))
        self.service.reset_session()
        entry_b = next(row for row in self.service.list_entries() if row["sku"] == "B")
        self.assertIsNone(entry_b["session_id"])

    def test_untimed_earnings_do_not_inflate_effective_hourly_rate(self):
        self.service.create_entry("UNTIMED-1", "bicycle", now=self.at(1, 8))
        self.service.start_session("stopwatch", now=self.at(1, 9))
        self.service.create_entry("TIMED", "bicycle", now=self.at(1, 9, 30))
        self.service.finish_session(now=self.at(1, 10))
        self.service.create_entry("UNTIMED-2", "bicycle", now=self.at(1, 11))

        summary = self.service.summary(now=self.at(1, 12))
        self.assertEqual(summary["all_cents"], 300)
        self.assertEqual(summary["timed_cents"], 100)
        self.assertEqual(summary["untimed_cents"], 200)
        self.assertEqual(summary["untimed_count"], 2)
        self.assertEqual(summary["effective_hourly_cents"], 100)

    def test_expired_or_paused_timer_cannot_mark_earnings_as_timed(self):
        countdown_id = self.service.start_session(
            "countdown", 1800, now=self.at(1, 9)
        )
        self.service.create_entry("EXPIRED", "bicycle", now=self.at(1, 10))
        expired = next(
            row for row in self.service.list_entries() if row["sku"] == "EXPIRED"
        )
        self.assertIsNone(expired["session_id"])
        self.assertEqual(
            self.service.get_session(countdown_id, now=self.at(1, 10))["product_count"],
            0,
        )
        self.service.finish_session(now=self.at(1, 10))

        session_id = self.service.start_session("stopwatch", now=self.at(2, 9))
        self.service.pause_session(now=self.at(2, 10))
        self.service.create_entry(
            "LEGACY-PAUSED",
            "bicycle",
            session_id=session_id,
            now=self.at(2, 10, 30),
        )
        self.service.finish_session(now=self.at(2, 11))
        session = self.service.get_session(session_id, now=self.at(2, 11))
        self.assertEqual(session["product_count"], 0)
        self.assertEqual(session["earned_cents"], 0)

    def test_countdown_stops_exactly_and_supports_overtime(self):
        self.service.start_session("countdown", 1800, now=self.at(1))
        snapshot = self.service.timer_snapshot(now=self.at(1, 10))
        self.assertTrue(snapshot.expired)
        self.assertEqual(snapshot.status, "paused")
        self.assertEqual(snapshot.elapsed_seconds, 1800)
        with self.assertRaises(ValueError):
            self.service.resume_session(now=self.at(1, 10))
        self.service.resume_session(overtime=True, now=self.at(1, 10))
        result = self.service.finish_session(now=self.at(1, 10, 15))
        self.assertAlmostEqual(result["elapsed_seconds"], 2700)

    def test_running_timer_recovers_after_database_reopen(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "earnings.db"
            first_db = DatabaseManager(path)
            first = EarningsManager(first_db, SettingsManager(first_db), local_tz=UTC)
            first.start_session("stopwatch", now=self.at(1))
            first_db.close()

            reopened_db = DatabaseManager(path)
            reopened = EarningsManager(reopened_db, SettingsManager(reopened_db), local_tz=UTC)
            snapshot = reopened.timer_snapshot(now=self.at(1, 10, 30))
            self.assertEqual(snapshot.status, "running")
            self.assertAlmostEqual(snapshot.elapsed_seconds, 5400)
            reopened_db.close()

    def test_goal_boundary_replacement_and_completion_snapshot(self):
        self.service.create_entry("OLD", "bicycle", now=self.at(1))
        goal_id = self.service.create_goal(200, now=self.at(2))
        with self.assertRaises(ActiveGoalError):
            self.service.create_goal(300, now=self.at(2))
        self.service.create_entry("N1", "bicycle", now=self.at(3))
        self.assertEqual(self.service.goal_progress(goal_id, now=self.at(3, 10))["earned_cents"], 100)
        self.service.create_entry("N2", "bicycle", now=self.at(4))
        goal = self.service._goal(goal_id)
        self.assertEqual(goal["status"], "completed")
        self.assertEqual(goal["final_product_count"], 2)

    def test_forecast_recent_data_fallbacks_and_deadline(self):
        self.service.create_goal(2000, deadline_date="2026-08-16", now=self.at(1, 8))
        for index in range(5):
            start = self.at(2 + index)
            self.service.start_session("stopwatch", now=start)
            self.service.create_entry(f"S{index}", "bicycle", now=start + timedelta(minutes=30))
            self.service.finish_session(now=start + timedelta(hours=1))
        forecast = self.service.goal_forecast(now=self.at(10))
        self.assertEqual(forecast["likely_products"], 15)
        self.assertEqual(forecast["conservative_products"], 20)
        self.assertAlmostEqual(forecast["estimated_hours"], 15)
        self.assertEqual(forecast["product_basis"], "last_30_days")
        self.assertFalse(forecast["deadline"]["overdue"])

    def test_no_history_forecast_and_upload_deduplication(self):
        self.service.create_goal(1000, now=self.at(1))
        forecast = self.service.goal_forecast(now=self.at(1, 10))
        self.assertIsNone(forecast["likely_products"])
        self.assertEqual(forecast["optimistic_products"], 10)
        self.assertEqual(forecast["conservative_products"], 14)
        self.assertIsNone(forecast["estimated_hours"])
        self.service.create_entry("A", "bicycle", processing_history_id=42, now=self.at(2))
        self.assertTrue(self.service.is_processing_imported(42))
        with self.assertRaises(ValueError):
            self.service.create_entry("A", "bicycle", processing_history_id=42, now=self.at(3))


if __name__ == "__main__":
    unittest.main()

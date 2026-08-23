"""Combined business and automation analytics for the dashboard."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


class AnalyticsManager:
    """Build one period-filtered view across earnings and processing history.

    Earnings records are the product ledger, including manually recorded work
    performed outside the app. Processing history is used only for automation
    reliability so importing a saved product into Earnings never doubles it.
    """

    SUCCESS_STATUSES = ("success", "saved_manually")

    def __init__(self, database):
        self.db = database

    @staticmethod
    def _threshold(days: int | None, now: datetime | None) -> str | None:
        if days is None:
            return None
        days = max(1, int(days))
        now = now or datetime.now(timezone.utc)
        return (now - timedelta(days=days - 1)).date().isoformat()

    @staticmethod
    def _where(column: str, threshold: str | None) -> tuple[str, list[str]]:
        if threshold is None:
            return "", []
        return f"WHERE DATE({column}) >= ?", [threshold]

    def snapshot(
        self,
        *,
        days: int | None = None,
        now: datetime | None = None,
        brand_limit: int = 8,
        recent_limit: int = 10,
        error_limit: int = 5,
    ) -> dict[str, Any]:
        threshold = self._threshold(days, now)
        earnings_where, earnings_params = self._where("e.earned_at", threshold)
        processing_where, processing_params = self._where("processed_at", threshold)

        earnings = dict(
            self.db.conn.execute(
                f"""
                SELECT COUNT(*) AS product_count,
                       COALESCE(SUM(e.payout_cents), 0) AS earned_cents,
                       COALESCE(SUM(CASE WHEN e.source='manual' THEN 1 ELSE 0 END), 0)
                           AS manual_count,
                       COALESCE(SUM(CASE WHEN e.source!='manual' THEN 1 ELSE 0 END), 0)
                           AS app_linked_count
                FROM earning_entries e
                {earnings_where}
                """,
                earnings_params,
            ).fetchone()
        )

        processing = dict(
            self.db.conn.execute(
                f"""
                SELECT COUNT(*) AS total,
                       COALESCE(SUM(CASE WHEN status IN ('success', 'saved_manually')
                                         THEN 1 ELSE 0 END), 0) AS succeeded,
                       COALESCE(SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END), 0)
                           AS failed
                FROM processing_history
                {processing_where}
                """,
                processing_params,
            ).fetchone()
        )
        processing["success_rate"] = (
            processing["succeeded"] * 100.0 / processing["total"]
            if processing["total"]
            else 0.0
        )

        brands = [
            dict(row)
            for row in self.db.conn.execute(
                f"""
                SELECT COALESCE(b.name, 'No brand') AS label,
                       COUNT(*) AS count,
                       COALESCE(SUM(e.payout_cents), 0) AS cents
                FROM earning_entries e
                LEFT JOIN earning_brands b ON b.id=e.brand_id
                {earnings_where}
                GROUP BY e.brand_id
                ORDER BY count DESC, cents DESC, label COLLATE NOCASE
                LIMIT ?
                """,
                [*earnings_params, max(1, int(brand_limit))],
            ).fetchall()
        ]
        sources = [
            dict(row)
            for row in self.db.conn.execute(
                f"""
                SELECT e.source AS label, COUNT(*) AS count,
                       COALESCE(SUM(e.payout_cents), 0) AS cents
                FROM earning_entries e
                {earnings_where}
                GROUP BY e.source
                ORDER BY count DESC, cents DESC, label
                """,
                earnings_params,
            ).fetchall()
        ]
        product_types = [
            dict(row)
            for row in self.db.conn.execute(
                f"""
                SELECT e.product_type AS label, COUNT(*) AS count,
                       COALESCE(SUM(e.payout_cents), 0) AS cents
                FROM earning_entries e
                {earnings_where}
                GROUP BY e.product_type
                ORDER BY count DESC, cents DESC, label
                """,
                earnings_params,
            ).fetchall()
        ]
        recent = [
            dict(row)
            for row in self.db.conn.execute(
                f"""
                SELECT e.sku, e.product_name, COALESCE(b.name, 'No brand') AS brand,
                       e.product_type, e.payout_cents, e.earned_at, e.source,
                       e.processing_history_id
                FROM earning_entries e
                LEFT JOIN earning_brands b ON b.id=e.brand_id
                {earnings_where}
                ORDER BY e.earned_at DESC, e.id DESC
                LIMIT ?
                """,
                [*earnings_params, max(1, int(recent_limit))],
            ).fetchall()
        ]

        error_join = "AND" if processing_where else "WHERE"
        errors = [
            dict(row)
            for row in self.db.conn.execute(
                f"""
                SELECT error_message AS message, COUNT(*) AS count
                FROM processing_history
                {processing_where}
                {error_join} status='failed'
                  AND error_message IS NOT NULL AND error_message!=''
                GROUP BY error_message
                ORDER BY count DESC, message
                LIMIT ?
                """,
                [*processing_params, max(1, int(error_limit))],
            ).fetchall()
        ]

        return {
            "days": days,
            "threshold": threshold,
            "earnings": earnings,
            "processing": processing,
            "brands": brands,
            "sources": sources,
            "product_types": product_types,
            "recent": recent,
            "errors": errors,
        }

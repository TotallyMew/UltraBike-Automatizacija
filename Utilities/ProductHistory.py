"""Persist product review decisions against the operation that produced them."""

import json
from contextlib import nullcontext


def record_review_status(db, result):
    if result.history_id is None:
        return None
    with getattr(db, "write_lock", nullcontext()):
        row = db.conn.execute(
            "SELECT id, product_code, details_json FROM processing_history WHERE id=?",
            (result.history_id,),
        ).fetchone()
        if row is None or row["product_code"] != result.product_code:
            raise ValueError("The preparation history entry no longer matches this product")
        details = json.loads(row["details_json"] or "{}") or {}
        previous = details.get("pim_preparation") or {}
        if previous.get("product_id") != result.product_id:
            raise ValueError("The preparation history entry belongs to another PIMBO product")
        details["pim_preparation"] = result.to_dict()
        db.conn.execute(
            "UPDATE processing_history SET status=?, details_json=? WHERE id=?",
            (result.status.value, json.dumps(details, ensure_ascii=False), result.history_id),
        )
        db.conn.commit()
        return result.history_id

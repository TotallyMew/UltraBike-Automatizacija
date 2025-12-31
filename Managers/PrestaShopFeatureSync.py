"""Managers/PrestaShopFeatureSync.py

Shared helper for syncing product features via PrestaShop Webservice API
from the translation tables produced by TranslationManager.

The translation tables are expected to be lists of dicts (tables), where each dict
contains feature_name -> feature_value pairs in that language.

This module intentionally contains no GUI code.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Tuple


def _log(logger, message: str, **context) -> None:
    try:
        if logger is not None:
            logger.log("PrestaShopFeatureSync", message, **context)
            return
    except Exception:
        pass


def _iter_feature_rows(
    lt_tables: List[Dict[str, Any]] | None,
    en_tables: List[Dict[str, Any]] | None,
    lv_tables: List[Dict[str, Any]] | None,
    emit: Callable[[str], None] | None = None,
) -> Iterable[Tuple[Dict[str, str], Dict[str, str]]]:
    """Yield (names_by_iso, values_by_iso) rows aligned by position.

    This mirrors the alignment approach used during earlier UI testing: we pair rows
    by index within each table, and fall back LV to EN when LV is missing.
    """

    def warn(msg: str) -> None:
        if emit:
            try:
                emit(msg)
            except Exception:
                pass

    for ti, lt_table in enumerate(lt_tables or []):
        en_table = (en_tables[ti] if ti < len(en_tables or []) else {}) or {}
        lv_table = (lv_tables[ti] if ti < len(lv_tables or []) else {}) or {}

        lt_items = list((lt_table or {}).items())
        en_items = list((en_table or {}).items())
        lv_items = list((lv_table or {}).items())

        if not lt_items:
            continue

        if not en_items:
            en_items = lt_items
        if not lv_items:
            lv_items = en_items

        n = min(len(lt_items), len(en_items), len(lv_items))
        if n <= 0:
            continue

        if len(en_items) != len(lt_items):
            warn(f"Warning: table {ti} row-count mismatch (LT={len(lt_items)} EN={len(en_items)}), using min={n}")
        if len(lv_items) != len(lt_items):
            warn(f"Warning: table {ti} row-count mismatch (LT={len(lt_items)} LV={len(lv_items)}), using min={n}")

        for ri in range(n):
            lt_name, lt_val = lt_items[ri]
            en_name, en_val = en_items[ri]
            lv_name, lv_val = lv_items[ri]

            names = {
                "lt": str(lt_name or "").strip(),
                "en": str(en_name or "").strip(),
                "lv": str(lv_name or "").strip(),
            }
            vals = {
                "lt": str(lt_val or "").strip(),
                "en": str(en_val or "").strip(),
                "lv": str(lv_val or "").strip(),
            }

            if not (names["lt"] or names["en"]):
                continue

            yield names, vals


def apply_features_from_tables(
    api,
    *,
    product_reference: str,
    lt_tables: List[Dict[str, Any]] | None,
    en_tables: List[Dict[str, Any]] | None,
    lv_tables: List[Dict[str, Any]] | None,
    logger=None,
    emit: Callable[[str], None] | None = None,
) -> Dict[str, Any]:
    """Resolve/create feature values and apply them to a product.

    Returns dict with keys:
      ok: bool
      message: str
      stats: dict
    """

    ref = (product_reference or "").strip()
    if not ref:
        return {"ok": False, "message": "Missing product reference", "stats": {}}

    _log(logger, "Starting feature sync via API", reference=ref)

    product_id = api.search_product_by_reference(ref)
    if not product_id:
        extra = ""
        try:
            extra = (api.last_error_summary() or "").strip()
        except Exception:
            extra = ""
        msg = f"Product not found by reference: {ref}" + (f" ({extra})" if extra else "")
        _log(logger, msg, reference=ref)
        return {"ok": False, "message": msg, "stats": {"reference": ref}}

    try:
        lang_map = api.get_language_id_map() or {}
    except Exception:
        lang_map = {}

    en_id = str(lang_map.get("en") or "1").strip()
    lt_id = str(lang_map.get("lt") or "2").strip()
    lv_id = str(lang_map.get("lv") or "3").strip()

    pairs: List[Tuple[str, str]] = []
    created_values = 0
    skipped_rows = 0
    missing_features = 0

    for names, vals in _iter_feature_rows(lt_tables, en_tables, lv_tables, emit=emit):
        names_by_lang_id: Dict[str, str] = {}
        values_by_lang_id: Dict[str, str] = {}

        if lt_id and names.get("lt"):
            names_by_lang_id[lt_id] = names["lt"]
            values_by_lang_id[lt_id] = vals.get("lt", "")
        if en_id and names.get("en"):
            names_by_lang_id[en_id] = names["en"]
            values_by_lang_id[en_id] = vals.get("en", "")
        if lv_id and names.get("lv"):
            names_by_lang_id[lv_id] = names["lv"]
            values_by_lang_id[lv_id] = vals.get("lv", "")

        feature_id = api.find_feature_id_by_names(names_by_lang_id)
        if not feature_id:
            missing_features += 1
            if emit:
                emit(f"Missing feature in shop (skipped): {names.get('en') or names.get('lt')}")
            continue

        value_id = api.find_feature_value_id_by_values(str(feature_id), values_by_lang_id)
        if not value_id:
            value_id = api.create_feature_value(str(feature_id), values_by_lang_id)
            if value_id:
                created_values += 1
                if emit:
                    emit(f"Created feature value: feature_id={feature_id} value_id={value_id}")
            else:
                skipped_rows += 1
                if emit:
                    emit(f"Missing value (could not create) for feature_id={feature_id}: {vals.get('en') or vals.get('lt')}")
                continue

        pairs.append((str(feature_id), str(value_id)))

    if not pairs:
        msg = f"No feature values to apply (missing_features={missing_features}, skipped_rows={skipped_rows})"
        _log(logger, msg, reference=ref)
        return {
            "ok": False,
            "message": msg,
            "stats": {
                "reference": ref,
                "product_id": int(product_id),
                "created_values": created_values,
                "missing_features": missing_features,
                "skipped_rows": skipped_rows,
                "pairs": 0,
            },
        }

    ok = api.update_product_feature_associations(int(product_id), pairs)
    if not ok:
        extra = ""
        try:
            extra = (api.last_error_summary() or "").strip()
        except Exception:
            extra = ""
        msg = f"API feature update failed for {ref}" + (f" ({extra})" if extra else "")
        _log(logger, msg, reference=ref, product_id=int(product_id))
        return {
            "ok": False,
            "message": msg,
            "stats": {
                "reference": ref,
                "product_id": int(product_id),
                "created_values": created_values,
                "missing_features": missing_features,
                "skipped_rows": skipped_rows,
                "pairs": len(pairs),
            },
        }

    msg = f"Applied features for {ref} (created_values={created_values}, missing_features={missing_features}, skipped_rows={skipped_rows})"
    _log(logger, msg, reference=ref, product_id=int(product_id), pairs=len(pairs))
    return {
        "ok": True,
        "message": msg,
        "stats": {
            "reference": ref,
            "product_id": int(product_id),
            "created_values": created_values,
            "missing_features": missing_features,
            "skipped_rows": skipped_rows,
            "pairs": len(pairs),
        },
    }

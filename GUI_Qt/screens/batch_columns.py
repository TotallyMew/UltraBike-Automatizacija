"""
GUI_Qt/screens/batch_columns.py

Central column definitions, index lookup, and presets for the unified batch screen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet


@dataclass(frozen=True)
class ColumnDef:
    key: str
    width_key: str          # key into SIZES dict (e.g. "col_w_240")
    header_i18n: str        # i18n key or literal header text
    widget_factory: str     # identifies how to create the cell widget
    lockable: bool          # True = always visible (brand, code, status, error, delete)
    attr_name: str | None   # For attribute columns, the ATTRIBUTE_DEFINITIONS name


# ---------------------------------------------------------------------------
# Column registry — order defines table column index
# ---------------------------------------------------------------------------

COLUMNS: list[ColumnDef] = [
    # -- Status dot (always visible, leftmost) --------------------------------
    ColumnDef("row_status",     "col_w_56",  "",                        "status_dot",    True,  None),

    # -- Core (always visible) -----------------------------------------------
    ColumnDef("brand",          "col_w_240", "batch.table.brand",       "brand_combo",   True,  None),
    ColumnDef("code",           "col_w_180", "batch.table.code",        "code_edit",     True,  None),

    # -- Product info (Upload / Descriptions) --------------------------------
    ColumnDef("url",            "col_w_420", "batch.table.url",         "url_edit",      False, None),
    ColumnDef("description",    "col_w_420", "batch.table.desc",        "desc_combo",    False, None),
    ColumnDef("frameset",       "col_w_120", "batch.table.frameset",    "checkbox",      False, None),
    ColumnDef("disclaimer",     "col_w_120", "batch.table.disclaimer",  "checkbox",      False, None),

    # -- Attributes (Upload only) --------------------------------------------
    ColumnDef("attr_modelis",    "col_w_200", "Modelis",              "attr_combo", False, "Modelis"),
    ColumnDef("attr_modelis_v",  "col_w_200", "Modelis (vidinis)",    "attr_combo", False, "Modelis (vidinis)"),
    ColumnDef("attr_remo_tipas", "col_w_160", "Rėmo tipas",          "attr_combo", False, "Rėmo tipas"),
    ColumnDef("attr_remo_medz",  "col_w_160", "Rėmo medžiaga",       "attr_combo", False, "Rėmo medžiaga"),
    ColumnDef("attr_ratu_dydis", "col_w_160", "Ratų dydis",          "attr_combo", False, "Ratų dydis"),
    ColumnDef("attr_pavaru_sk",  "col_w_160", "Pavarų skaičius",     "attr_combo", False, "Pavarų skaičius"),
    ColumnDef("attr_stabdziu",   "col_w_160", "Stabdžių tipas",      "attr_combo", False, "Stabdžių tipas"),
    ColumnDef("attr_komplekt",   "col_w_160", "Komplektacija",        "attr_combo", False, "Komplektacija"),
    ColumnDef("attr_spalva",     "col_w_160", "Spalva",               "attr_combo", False, "Spalva"),

    # -- Titles (Titles mode) ------------------------------------------------
    ColumnDef("title_lt",       "col_w_320", "batch.table.title_lt",   "line_edit",     False, None),
    ColumnDef("title_en",       "col_w_320", "batch.table.title_en",   "line_edit",     False, None),

    # -- Operational (always visible) ----------------------------------------
    ColumnDef("status",         "col_w_160", "batch.table.status",     "status_label",  False, None),
    ColumnDef("error",          "col_w_320", "batch.table.error",      "error_edit",    False, None),
    ColumnDef("delete",         "col_w_56",  "",                       "delete_btn",    True,  None),
]

NUM_COLUMNS = len(COLUMNS)

# Fast index lookup: COL["brand"] == 0, COL["url"] == 2, etc.
COL: dict[str, int] = {c.key: i for i, c in enumerate(COLUMNS)}

# Map attribute display names to column indices
ATTR_COL_MAP: dict[str, int] = {
    c.attr_name: i for i, c in enumerate(COLUMNS) if c.attr_name is not None
}

# ---------------------------------------------------------------------------
# Presets — sets of non-locked column keys to show
# ---------------------------------------------------------------------------

PRESETS: dict[str, frozenset[str]] = {
    "upload": frozenset({
        "url", "description", "frameset", "disclaimer",
        "attr_modelis", "attr_modelis_v", "attr_remo_tipas", "attr_remo_medz",
        "attr_ratu_dydis", "attr_pavaru_sk", "attr_stabdziu", "attr_komplekt",
        "attr_spalva",
    }),
    "descriptions": frozenset({
        "description", "disclaimer",
    }),
    "titles": frozenset({
        "title_lt", "title_en",
    }),
}

# Column keys grouped by category (for the column picker UI)
COLUMN_GROUPS: list[tuple[str, list[str]]] = [
    ("batch.colgroup.product_info", ["url", "description", "frameset", "disclaimer"]),
    ("batch.colgroup.attributes", [
        "attr_modelis", "attr_modelis_v", "attr_remo_tipas", "attr_remo_medz",
        "attr_ratu_dydis", "attr_pavaru_sk", "attr_stabdziu", "attr_komplekt",
        "attr_spalva",
    ]),
    ("batch.colgroup.titles", ["title_lt", "title_en"]),
]

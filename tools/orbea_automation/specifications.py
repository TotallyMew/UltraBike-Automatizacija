"""Fill Orbea name/size fields and pass component source text to MagicAI."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from tools.kross_automation.specifications import sort_kross_frame_sizes
from Utilities.ProductDataSafety import SpecificationMap
from .component_values import normalize_component_specifications


@dataclass(frozen=True)
class OrbeaSpecificationPlan:
    values: tuple[tuple[str, str], ...]
    magic_ai_source: str


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _fold(value):
    return "".join(c for c in unicodedata.normalize("NFKD", _clean(value).casefold())
                   if not unicodedata.combining(c))


MANUAL_SPECIFICATION_FIELDS = ("Ratų dydis", "Lako užbaigimas")
_MANUAL_SOURCE_LABELS = {
    *map(_fold, MANUAL_SPECIFICATION_FIELDS),
    "wheel size", "wheel diameter", "paint finish", "lacquer finish", "finish",
}


def parse_orbea_name(name, *, source_model=""):
    """Split the PIMBO model/year from its colour, using the source as fallback."""
    title = re.sub(r"^ORBEA\s+", "", _clean(name), flags=re.I)
    source_model = re.sub(r"^ORBEA\s+", "", _clean(source_model), flags=re.I)
    year = re.search(r"\b(?:19|20)\d{2}\b", title)
    model, color = source_model, ""
    if year:
        model, color = title[:year.end()], title[year.end():]
    elif source_model and title.casefold().startswith(source_model.casefold()) and (
        len(title) == len(source_model) or title[len(source_model)].isspace()
    ):
        model, color = title[:len(source_model)], title[len(source_model):]
    color = re.sub(r"\(\s*(?:Glossy?|Matte?)\s*\)", "", color, flags=re.I)
    color = re.sub(r"\s*[-–—]\s*", " - ", color)
    color = _clean(color).strip(" /-|")
    # PIMBO may append category/wheel text after a separate Custom colour
    # segment. Keep that explicit colour marker out of Spalva and MagicAI.
    if re.match(r"^custom(?:\s*[/|;]\s*|$)", color, flags=re.I):
        color = "Custom"
    return (f"Orbea {_clean(model)}" if model else "", color)


def build_orbea_specification_plan(name, sizes, text, *, translator=None, product=None):
    model, color = parse_orbea_name(name, source_model=getattr(product, "name", ""))
    values = SpecificationMap()
    if model:
        values["Modelis"] = model
    if color and color.casefold() != "custom":
        values["Spalva"] = color
    ordered_sizes = sort_kross_frame_sizes(sizes)
    if ordered_sizes:
        values["Galimi rėmo dydžiai"] = ", ".join(ordered_sizes)
    source_rows = []
    for line in normalize_component_specifications(text).splitlines():
        if ":" not in line:
            if _clean(line):
                source_rows.append(_clean(line))
            continue
        label, value = map(_clean, line.split(":", 1))
        if not label or not value:
            continue
        if _fold(label) in _MANUAL_SOURCE_LABELS or (
            color.casefold() == "custom" and _fold(label) in {"spalva", "color", "colour"}
        ):
            continue
        source_rows.append(f"{label}: {value}")
    # MagicAI uses PIMBO's real schema to place component values.
    # Name/size values alone are insufficient evidence for component AI.
    ai_source = "\n".join([*(f"{key}: {value}" for key, value in values.items()), *source_rows]) if source_rows else ""
    return OrbeaSpecificationPlan(tuple(values.items()), ai_source)

"""Explicit Orbea paint-name mappings for the Pimbo Spalva attribute only."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from Utilities.ResourcePaths import resource_path

CATALOGUE_PATH = resource_path("Assets/orbea_colour_attributes.json")
FINISH_WORDS = re.compile(r"\b(?:glossy?|matte?)\b", re.I)


def colour_key(value: str) -> str:
    value = FINISH_WORDS.sub("", str(value))
    value = re.sub(r"\([-–—\s]*\)", "", value)
    value = re.sub(r"\b(?:c\.?\s*view|carbon\s+view)\b", "carbon view", value, flags=re.I)
    value = re.sub(r"\s*[-–—]\s*", " - ", value)
    return re.sub(r"\s+", " ", value).strip().casefold()


def paint_key(value: str) -> tuple[str, tuple[str, ...]]:
    """Keep finish order so explicit Gloss and Matt assignments can differ."""
    finishes = tuple("gloss" if match.group().casefold().startswith("gloss") else "matt"
                     for match in FINISH_WORDS.finditer(str(value)))
    return colour_key(value), finishes


@dataclass(frozen=True)
class ColourAttributeEntry:
    id: str
    orbea_colour: str
    attribute_values: tuple[str, ...]


class ColourAttributeMapping:
    def __init__(self, entries):
        self.entries = tuple(entries)
        self._values = {}
        alternatives, first_values = {}, {}
        for entry in self.entries:
            key = paint_key(entry.orbea_colour)
            prior = self._values.get(key)
            if prior is not None and sorted(prior) != sorted(entry.attribute_values):
                raise ValueError(f"Conflicting Spalva mappings for the same Orbea colour: {entry.orbea_colour}")
            self._values[key] = entry.attribute_values
            alternatives.setdefault(key[0], set()).add(tuple(sorted(entry.attribute_values)))
            first_values.setdefault(key[0], entry.attribute_values)
        # Ignore missing/different finish labels only when the complete paint
        # combination has one unambiguous assignment across all finishes.
        self._fallback_values = {key: first_values[key] for key, values in alternatives.items() if len(values) == 1}

    def values_for(self, colour):
        key = paint_key(colour)
        return self._values.get(key, self._fallback_values.get(key[0], ()))

    def fingerprint_for(self, colour):
        values = self.values_for(colour)
        if not values:
            return ""
        return hashlib.sha256(json.dumps([paint_key(colour), sorted(values)], ensure_ascii=False).encode()).hexdigest()

    @property
    def mapped_count(self):
        return sum(bool(self.values_for(entry.orbea_colour)) for entry in self.entries)


def load_colour_mapping(overrides=None, *, path=CATALOGUE_PATH):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if data.get("version") != 1 or not isinstance(data.get("colours"), list):
        raise ValueError("Unsupported Orbea colour attribute catalogue")
    overrides = {} if overrides is None else dict(overrides)
    entries, seen = [], set()
    for item in data["colours"]:
        identifier, name = str(item["id"]), str(item["orbea_colour"]).strip()
        if identifier in seen or not name:
            raise ValueError("Duplicate or empty Orbea colour entry")
        seen.add(identifier)
        values = overrides.get(identifier, item.get("attribute_values", []))
        if not isinstance(values, (list, tuple)) or any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError(f"Spalva must contain existing dropdown values: {name}")
        entries.append(ColourAttributeEntry(identifier, name, tuple(dict.fromkeys(value.strip() for value in values))))
    if set(overrides) - seen:
        raise ValueError("An Orbea colour override is outside the colour catalogue")
    return ColourAttributeMapping(entries)

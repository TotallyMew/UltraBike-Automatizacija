"""Separate selected Orbea components from configurator prices and options."""
from __future__ import annotations

import re


_INCLUDED = re.compile(r"\s+Incl\.\s*$", re.I)
_PRICE = re.compile(r"\s+(?:[€£$]\s*\d[\d.,]*|\d[\d.,]*\s*[€£$])(?:\s+More information)?(?:\s+|$)", re.I)


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_component_specifications(text):
    """Retain an explicit included component instead of its option picker.

    Real conflicting components remain separate rows for upload validation.
    Unselected option menus are omitted rather than treated as fitted components.
    This also repairs saved packages without modifying their source files.
    """
    rows = []
    included = {}
    for raw in str(text or "").splitlines():
        if ":" not in raw:
            rows.append(("", _clean(raw), False))
            continue
        label, value = map(_clean, raw.split(":", 1))
        if not label:
            continue
        selected = bool(_INCLUDED.search(value))
        value = _INCLUDED.sub("", value).strip()
        rows.append((label, value, selected))
        if selected:
            included.setdefault(label.casefold(), set()).add(value.casefold())

    result = []
    for label, value, selected in rows:
        if re.fullmatch(r"(?:More information\s*)+", value, flags=re.I):
            continue
        choices = tuple(_clean(part) for part in _PRICE.split(value) if _clean(part))
        has_prices = bool(_PRICE.search(value))
        if has_prices and not selected:
            if included.get(label.casefold()) or len(choices) > 1 or re.match(r"Add\s+Delete\b", value, re.I):
                continue
            value = choices[0] if choices else ""
        if value:
            result.append(f"{label}: {value}" if label else value)
    return "\n".join(dict.fromkeys(result))

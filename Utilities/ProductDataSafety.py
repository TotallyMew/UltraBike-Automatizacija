"""Validation shared by single and batch product preparation."""

from collections.abc import Mapping


class SpecificationMap(dict):
    """Reject conflicting supplier rows instead of keeping the last value."""

    def __setitem__(self, key, value):
        existing_key = next((item for item in self if str(item).casefold() == str(key).casefold()), None)
        if existing_key is not None and self[existing_key] != value:
            raise ValueError(f"Conflicting supplier values for {key!r}; select the correct product variant")
        super().__setitem__(key, value)


def option_bool(value, *, name, default=False):
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "yes", "1", "taip"}:
            return True
        if normalized in {"false", "no", "0", "ne", ""}:
            return False
    elif isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise ValueError(f"Invalid value for {name}: expected True or False")


def normalize_brand_options(options):
    if options is not None and not isinstance(options, Mapping):
        raise ValueError("Brand options must be a mapping")
    result = dict(options or {})
    for name in ("append_disclaimer", "frameset_only", "append_order_note"):
        if name in result or name == "append_disclaimer":
            result[name] = option_bool(result.get(name), name=name)
    if result.get("append_order_note"):
        raise ValueError("Order-note upload is not supported; no product changes were started")
    description = result.get("description_name")
    result["description_name"] = (str(description).strip() or None) if description is not None else None
    if result.get("variant_index") is not None:
        value = result["variant_index"]
        if isinstance(value, bool):
            raise ValueError("variant_index must be a non-negative integer")
        try:
            parsed = int(value)
        except (ValueError, TypeError) as error:
            raise ValueError("variant_index must be a non-negative integer") from error
        if parsed < 0 or str(parsed) != str(value).strip():
            raise ValueError("variant_index must be a non-negative integer")
        result["variant_index"] = parsed
    return result


def validate_unique_products(items):
    seen = set()
    for item in items:
        code = str(item.get("code") or item.get("product_code") or "").strip().casefold()
        if code in seen:
            raise ValueError(f"Product {code!r} appears more than once; process it once to avoid conflicting changes")
        seen.add(code)

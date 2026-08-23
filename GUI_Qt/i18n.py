"""Strict, resource-backed localization for the Qt application."""

from __future__ import annotations

import json
from dataclasses import dataclass
from string import Formatter
from typing import Any, Dict, Iterable

from PySide6.QtCore import QObject, Signal

from Utilities.ResourcePaths import resource_path


_LANG_DISPLAY_TO_CODE = {
    "English": "en",
    "Lithuanian": "lt",
}
_LANG_CODE_TO_DISPLAY = {value: key for key, value in _LANG_DISPLAY_TO_CODE.items()}
_LANGUAGES = ("en", "lt")


def _unique_object(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate translation key: {key}")
        result[key] = value
    return result


def _placeholders(value: str) -> set[str]:
    return {
        field_name.split(".", 1)[0].split("[", 1)[0]
        for _literal, field_name, _format_spec, _conversion in Formatter().parse(value)
        if field_name
    }


def _load_catalog(language: str) -> Dict[str, str]:
    path = resource_path(f"Assets/i18n/{language}.json")
    try:
        data = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
        )
    except Exception as error:
        raise RuntimeError(f"Could not load translation catalog {path}: {error}") from error
    if not isinstance(data, dict) or not data:
        raise RuntimeError(f"Translation catalog {path} must be a non-empty object")
    invalid = [key for key, value in data.items() if not isinstance(key, str) or not isinstance(value, str)]
    if invalid:
        raise RuntimeError(f"Translation catalog {path} contains non-string values: {invalid[:5]}")
    return data


def validate_translation_catalogs(catalogs: Dict[str, Dict[str, str]]) -> None:
    """Require key and placeholder parity across every supported language."""

    english = catalogs.get("en", {})
    english_keys = set(english)
    for language in _LANGUAGES:
        current = catalogs.get(language, {})
        missing = sorted(english_keys - set(current))
        extra = sorted(set(current) - english_keys)
        if missing or extra:
            raise RuntimeError(
                f"Translation key mismatch for {language}: missing={missing[:10]}, extra={extra[:10]}"
            )
        for key, english_text in english.items():
            expected = _placeholders(english_text)
            actual = _placeholders(current[key])
            if expected != actual:
                raise RuntimeError(
                    f"Translation placeholder mismatch for {language}:{key}: "
                    f"expected={sorted(expected)}, actual={sorted(actual)}"
                )


def load_translations() -> Dict[str, Dict[str, str]]:
    catalogs = {language: _load_catalog(language) for language in _LANGUAGES}
    validate_translation_catalogs(catalogs)
    return catalogs


TRANSLATIONS = load_translations()


def normalize_language(value: Any, fallback: str = "en") -> str:
    """Normalize a stored or displayed language value to a language code."""

    if not value:
        return fallback
    if isinstance(value, str):
        normalized = value.strip()
        if normalized in TRANSLATIONS:
            return normalized
        if normalized in _LANG_DISPLAY_TO_CODE:
            return _LANG_DISPLAY_TO_CODE[normalized]
    return fallback


def translate(lang_code: str, key: str, **kwargs) -> str:
    """Translate a key using an explicit language code without side effects."""

    code = normalize_language(lang_code, "en")
    text = TRANSLATIONS.get(code, {}).get(key)
    if text is None:
        text = TRANSLATIONS["en"].get(key, key)
    try:
        return text.format(**kwargs)
    except (KeyError, ValueError, IndexError):
        return text


@dataclass(frozen=True)
class Language:
    code: str

    @property
    def display(self) -> str:
        return _LANG_CODE_TO_DISPLAY.get(self.code, "English")


class I18nManager(QObject):
    """Application localization state with a signal for live UI updates."""

    languageChanged = Signal(str)

    def __init__(self, settings_manager=None, default_language: str = "en"):
        super().__init__()
        self._settings = settings_manager
        self._language = normalize_language(
            settings_manager.get("language", None) if settings_manager else None,
            default_language,
        )

    @property
    def language(self) -> Language:
        return Language(self._language)

    def set_language(self, language: str, *, persist: bool = False) -> None:
        code = normalize_language(language, self._language)
        if code == self._language:
            if persist and self._settings:
                self._settings.set("language", Language(code).display)
            return
        self._language = code
        if persist and self._settings:
            self._settings.set("language", Language(code).display)
        self.languageChanged.emit(code)

    def tr(self, key: str, **kwargs) -> str:
        return translate(self._language, key, **kwargs)

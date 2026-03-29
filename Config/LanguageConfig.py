"""
Language Configuration - Central source of truth for language codes and mappings

This module provides consistent language code handling across the application.
All language-related constants and conversions should use this module.

Supported Languages:
- English (en)
- Lithuanian (lt)
- Latvian (lv)
"""

from enum import Enum
from typing import Dict


class LanguageCode(Enum):
    """ISO 639-1 language codes (lowercase)"""
    ENGLISH = "en"
    LITHUANIAN = "lt"
    LATVIAN = "lv"

    def __str__(self):
        return self.value

    @property
    def uppercase(self) -> str:
        """Get uppercase version (for DeepL API)"""
        return self.value.upper()

    @property
    def display_name(self) -> str:
        """Get display name for UI"""
        return LANG_CODE_TO_DISPLAY[self.value]


# Language code to display name mapping
LANG_CODE_TO_DISPLAY: Dict[str, str] = {
    "en": "English",
    "lt": "Lithuanian",
    "lv": "Latvian"
}

# Display name to language code mapping (for settings/UI)
LANG_DISPLAY_TO_CODE: Dict[str, str] = {
    "English": "en",
    "Lithuanian": "lt",
    "Latvian": "lv"
}

# Platform language ID mapping used by the admin system.
LANG_CODE_TO_PLATFORM_ID: Dict[str, str] = {
    "en": "1",
    "lt": "2",
    "lv": "3"
}

# All supported language codes (lowercase)
SUPPORTED_LANGUAGES = ["en", "lt", "lv"]

# All supported language codes (uppercase, for DeepL API)
SUPPORTED_LANGUAGES_UPPER = ["EN", "LT", "LV"]


def normalize_lang_code(lang_code: str) -> str:
    """
    Normalize language code to lowercase standard format.

    Args:
        lang_code: Language code in any format (en, EN, English, etc.)

    Returns:
        Normalized lowercase language code (en, lt, lv)

    Raises:
        ValueError: If language code is not supported
    """
    # Try direct lowercase match
    lower = lang_code.lower()
    if lower in SUPPORTED_LANGUAGES:
        return lower

    # Try uppercase match
    upper = lang_code.upper()
    if upper in SUPPORTED_LANGUAGES_UPPER:
        return upper.lower()

    # Try display name match
    if lang_code in LANG_DISPLAY_TO_CODE:
        return LANG_DISPLAY_TO_CODE[lang_code]

    raise ValueError(f"Unsupported language code: '{lang_code}'. Supported: {', '.join(SUPPORTED_LANGUAGES)}")


def get_platform_id(lang_code: str) -> str:
    """
    Get language ID for a given language code.

    Args:
        lang_code: Language code (en, EN, English, etc.)

    Returns:
        Platform language ID as string

    Raises:
        ValueError: If language code is not supported
    """
    normalized = normalize_lang_code(lang_code)
    return LANG_CODE_TO_PLATFORM_ID[normalized]


def get_display_name(lang_code: str) -> str:
    """
    Get display name for a language code.

    Args:
        lang_code: Language code (en, EN, etc.)

    Returns:
        Display name (English, Lithuanian, Latvian)

    Raises:
        ValueError: If language code is not supported
    """
    normalized = normalize_lang_code(lang_code)
    return LANG_CODE_TO_DISPLAY[normalized]


def to_uppercase(lang_code: str) -> str:
    """
    Convert language code to uppercase (for DeepL API).

    Args:
        lang_code: Language code in any format

    Returns:
        Uppercase language code (EN, LT, LV)

    Raises:
        ValueError: If language code is not supported
    """
    normalized = normalize_lang_code(lang_code)
    return normalized.upper()

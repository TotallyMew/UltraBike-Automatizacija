"""
DeepL Translation Manager
Automated translation for product descriptions (EN, LT, LV)
"""

# Standard library
from typing import Dict, List, Optional


class DeepLTranslator:
    """Translate descriptions using DeepL API (or simulation mode)."""

    def __init__(self, api_key: str, logger=None, strict_validation: bool = False):
        """
        Initialize DeepL translator.

        Args:
            api_key: DeepL API key (get from https://www.deepl.com/pro-api)
                    Free tier: 500k chars/month
                    Pro tier: Unlimited usage for $5.49/month
            logger: Optional logger instance
            strict_validation: If True, raise ValueError for invalid API keys instead of falling back to simulation mode

        Raises:
            ValueError: If strict_validation=True and API key is invalid/missing
            ImportError: If strict_validation=True and deepl package not installed
        """
        self.api_key = api_key
        self.translator = None
        self.simulation_mode = False
        self.logger = logger
        self.last_error: Optional[Dict] = None  # Track last error for debugging

        # Validate API key if strict mode enabled
        if strict_validation:
            if not api_key or api_key == "TEMPLATE_API_KEY_REPLACE_ME":
                raise ValueError("DeepL API key cannot be empty or template value")

        # Try to import deepl, fall back to simulation if not available
        try:
            import deepl
            if api_key and api_key != "TEMPLATE_API_KEY_REPLACE_ME":
                self.translator = deepl.Translator(api_key)
                self.simulation_mode = False
            else:
                if strict_validation:
                    raise ValueError("Invalid DeepL API key provided")
                self.simulation_mode = True
                self._log("Running in SIMULATION mode (template API key)")
        except ImportError as e:
            if strict_validation:
                raise ImportError("deepl package not installed. Install with: pip install deepl") from e
            self.simulation_mode = True
            self._log("Running in SIMULATION mode (deepl package not installed)")

    def _log(self, message, **context):
        """Log message if logger is available"""
        if self.logger:
            self.logger.log("DeepLTranslator", message, **context)

    def last_error_summary(self) -> Optional[str]:
        """Get human-readable summary of last error."""
        if not self.last_error:
            return None

        error_type = self.last_error.get('type', 'Unknown')
        error_msg = self.last_error.get('error', 'No details')
        operation = self.last_error.get('operation', 'operation')

        return f"{error_type} during {operation}: {error_msg}"

    def translate_text(
        self,
        text: str,
        source_lang: str,
        target_lang: str
    ) -> str:
        """
        Translate text from source to target language.

        Args:
            text: Text to translate
            source_lang: Source language code ("EN", "LT", "LV")
            target_lang: Target language code ("EN", "LT", "LV")

        Returns:
            Translated text
        """
        # Simulation mode - just add a prefix to show it "worked"
        if self.simulation_mode:
            self._log(f"Simulating translation from {source_lang} to {target_lang}")
            return f"[{target_lang} Translation] {text[:100]}..."

        # Real DeepL API call
        try:
            result = self.translator.translate_text(
                text,
                source_lang=source_lang.upper(),
                target_lang=target_lang.upper(),
                preserve_formatting=True,  # Keeps HTML tags intact
                tag_handling="html"  # Properly handles <p>, <strong>, etc.
            )
            self.last_error = None  # Clear error on success
            self._log(f"Successfully translated from {source_lang} to {target_lang}")
            return result.text
        except Exception as e:
            self.last_error = {
                'operation': 'translate_text',
                'source_lang': source_lang,
                'target_lang': target_lang,
                'error': str(e),
                'type': type(e).__name__
            }
            self._log(f"Translation failed: {str(e)}", error=str(e))
            raise

    def translate_description_all_languages(
        self,
        description_html: str,
        source_lang: str = "EN"
    ) -> Dict[str, str]:
        """
        Translate description to all supported languages.

        Args:
            description_html: HTML description from brand website
            source_lang: Source language ("EN", "LT", "LV")

        Returns:
            Dict with translations: {"en": "...", "lt": "...", "lv": "..."}
        """
        translations = {}

        # Keep source as-is
        translations[source_lang.lower()] = description_html

        # Translate to other languages
        target_languages = ["EN", "LT", "LV"]
        for target_lang in target_languages:
            if target_lang.upper() != source_lang.upper():
                try:
                    translated = self.translate_text(
                        description_html,
                        source_lang=source_lang,
                        target_lang=target_lang
                    )
                    translations[target_lang.lower()] = translated
                except Exception as e:
                    # Log error but continue with fallback
                    self._log(f"Error translating to {target_lang}: {str(e)}", error=str(e), target_lang=target_lang)
                    translations[target_lang.lower()] = f"<!-- Translation failed: {e} -->\n{description_html}"

        return translations

    def batch_translate_descriptions(
        self,
        descriptions: List[Dict],
        source_lang: str = "EN"
    ) -> List[Dict]:
        """
        Batch translate multiple descriptions.

        Args:
            descriptions: List of {"name": "...", "html": "...", "code": "..."}
            source_lang: Source language

        Returns:
            List of translated descriptions with all language versions
        """
        results = []

        for desc in descriptions:
            try:
                translations = self.translate_description_all_languages(
                    desc['html'],
                    source_lang=source_lang
                )

                results.append({
                    'name': desc['name'],
                    'code': desc.get('code'),
                    'translations': translations,
                    'status': 'success'
                })

            except Exception as e:
                results.append({
                    'name': desc['name'],
                    'code': desc.get('code'),
                    'error': str(e),
                    'status': 'failed'
                })

        return results

    def get_usage_stats(self) -> Dict:
        """Get current API usage statistics."""

        # Simulation mode - return fake stats
        if self.simulation_mode:
            return {
                'character_count': 0,
                'character_limit': 500000,  # Free tier limit
                'percentage_used': 0.0,
                'remaining': 500000,
                'simulation_mode': True
            }

        # Real DeepL API usage stats
        try:
            usage = self.translator.get_usage()

            return {
                'character_count': usage.character.count,
                'character_limit': usage.character.limit if usage.character.limit else 0,
                'percentage_used': (usage.character.count / usage.character.limit) * 100 if usage.character.limit else 0,
                'remaining': usage.character.limit - usage.character.count if usage.character.limit else "unlimited",
                'simulation_mode': False
            }
        except Exception as e:
            self._log(f"Error getting usage stats: {str(e)}", error=str(e))
            return {
                'character_count': 0,
                'character_limit': 0,
                'percentage_used': 0.0,
                'remaining': 'unknown',
                'simulation_mode': False,
                'error': str(e)
            }

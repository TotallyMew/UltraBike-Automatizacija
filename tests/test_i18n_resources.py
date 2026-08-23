import json
import unittest

from GUI_Qt.i18n import TRANSLATIONS, _unique_object, validate_translation_catalogs


class TranslationResourceTests(unittest.TestCase):
    def test_shipped_resources_have_strict_parity(self):
        validate_translation_catalogs(TRANSLATIONS)
        self.assertEqual(set(TRANSLATIONS["en"]), set(TRANSLATIONS["lt"]))

    def test_duplicate_keys_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate translation key"):
            json.loads('{"same":"one","same":"two"}', object_pairs_hook=_unique_object)

    def test_key_and_placeholder_mismatches_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "key mismatch"):
            validate_translation_catalogs({"en": {"a": "A"}, "lt": {"b": "B"}})
        with self.assertRaisesRegex(RuntimeError, "placeholder"):
            validate_translation_catalogs(
                {"en": {"a": "Hello {name}"}, "lt": {"a": "Labas {vardas}"}}
            )

    def test_sidebar_action_labels_are_localized_and_match_page_titles(self):
        expected = {
            "en": {
                "nav.group.insights": "Insights",
                "nav.spotify": "Spotify Connect",
                "nav.name_getter": "Names by code",
                "nav.code_getter": "Export product codes",
                "nav.product_name_getter": "Export product names",
                "nav.folders": "Build folder structure",
                "nav.spec_checker": "Check specifications",
            },
            "lt": {
                "nav.group.insights": "Įžvalgos",
                "nav.spotify": "Spotify Connect",
                "nav.name_getter": "Pavadinimai pagal kodus",
                "nav.code_getter": "Eksportuoti produktų kodus",
                "nav.product_name_getter": "Eksportuoti produktų pavadinimus",
                "nav.folders": "Sukurti aplankų struktūrą",
                "nav.spec_checker": "Tikrinti specifikacijas",
            },
        }
        page_title_keys = {
            "nav.spotify": "spotify.title",
            "nav.name_getter": "namegetter.title",
            "nav.code_getter": "codegetter.title",
            "nav.product_name_getter": "productnamegetter.title",
            "nav.folders": "folders.title",
            "nav.spec_checker": "speccheck.title",
        }

        for language, labels in expected.items():
            catalog = TRANSLATIONS[language]
            for key, value in labels.items():
                self.assertEqual(catalog[key], value)
            for nav_key, title_key in page_title_keys.items():
                self.assertEqual(catalog[nav_key], catalog[title_key])
            self.assertEqual(catalog["nav.folders"], catalog["info.folders.title"])

    def test_spotify_copy_is_session_only(self):
        obsolete_account_wide_keys = {
            "spotify.local.note",
            "spotify.local.tracks",
            "spotify.metric.plays",
            "spotify.range.long",
            "spotify.range.medium",
            "spotify.range.short",
            "spotify.top.artists",
            "spotify.top.note",
            "spotify.top.tracks",
        }
        for catalog in TRANSLATIONS.values():
            self.assertTrue(obsolete_account_wide_keys.isdisjoint(catalog))

        self.assertEqual(
            TRANSLATIONS["en"]["spotify.analytics.title"],
            "Work-session listening",
        )
        self.assertEqual(
            TRANSLATIONS["lt"]["spotify.analytics.title"],
            "Klausymas darbo sesijose",
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.orbea_description_extractor import (
    DescriptionDocument,
    clean_lines,
    normalize_orbea_url,
    render_document,
    write_documents,
)


class OrbeaDescriptionExtractorTests(unittest.TestCase):
    def test_normalize_url_removes_query_and_fragment(self):
        self.assertEqual(
            normalize_orbea_url(
                "cms.orbea.com/en-au/m/kemen-adv/?campaign=test#handling"
            ),
            "https://cms.orbea.com/en-au/m/kemen-adv",
        )

    def test_normalize_url_rejects_non_model_page(self):
        with self.assertRaises(ValueError):
            normalize_orbea_url("https://example.com/en-au/m/kemen-adv")
        with self.assertRaises(ValueError):
            normalize_orbea_url("https://cms.orbea.com/en-au/support")

    def test_clean_lines_filters_controls_numbers_and_duplicates(self):
        self.assertEqual(
            clean_lines(
                "Kemen Adv\nView content\n1\nAccesible text\n"
                "Trail compatible\nTrail compatible"
            ),
            ["Kemen Adv", "Trail compatible"],
        )

    def test_render_and_write_include_expanded_content(self):
        document = DescriptionDocument(
            url="https://cms.orbea.com/en-au/m/kemen-adv",
            model="Kemen Adv",
            main_lines=["Kemen Adv", "Escape the everyday", "Main description."],
            heading_keys={"escape the everyday"},
            expanded_sections=[["Assist switch", "Expanded description."]],
        )
        rendered = render_document(document)
        self.assertEqual(rendered.count("\nKemen Adv\n"), 0)
        self.assertIn("EXPANDED DETAILS", rendered)
        self.assertIn("Expanded description.", rendered)

        with tempfile.TemporaryDirectory() as temp_dir:
            written = write_documents([document], Path(temp_dir))
            self.assertEqual({path.name for path in written}, {
                "kemen-adv.txt",
                "all_orbea_descriptions.txt",
            })
            content = (Path(temp_dir) / "kemen-adv.txt").read_text(
                encoding="utf-8-sig"
            )
            self.assertIn("URL: https://cms.orbea.com/en-au/m/kemen-adv", content)


if __name__ == "__main__":
    unittest.main()

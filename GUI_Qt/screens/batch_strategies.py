"""
GUI_Qt/screens/batch_strategies.py

Mode-specific logic for the unified batch screen.
Each strategy knows how to collect items, create workers, and handle Excel I/O.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from qfluentwidgets import ComboBox, CheckBox, LineEdit

from GUI_Qt.screens.batch_columns import COL, COLUMNS, ATTR_COL_MAP
from GUI_Qt.screens.UploadScreen import ATTRIBUTE_DEFINITIONS


class BatchModeStrategy(ABC):
    """Base class for batch mode strategies."""

    @abstractmethod
    def collect_items(self, screen, valid_rows: list[int]) -> list[dict]:
        """Collect item data from the table for the given rows."""

    @abstractmethod
    def create_worker(self, screen, items: list[dict], table_row_indices: list[int],
                      multi_session: bool, session_manager):
        """Create and return the appropriate QThread worker."""

    @abstractmethod
    def get_template_headers(self, tr) -> list[str]:
        """Return Excel template column headers."""

    @abstractmethod
    def get_template_example(self, tr) -> list[str]:
        """Return one example row for the Excel template."""

    @abstractmethod
    def parse_excel_row(self, excel_row: tuple, tr) -> dict:
        """Parse an Excel row into a dict keyed by column keys."""

    def validate_row(self, screen, row: int) -> bool:
        """Check if a row has minimum required data."""
        brand_w = screen._get_inner_widget(row, COL["brand"])
        code_w = screen._get_inner_widget(row, COL["code"])
        if not brand_w or not code_w:
            return False
        brand = brand_w.currentText() if hasattr(brand_w, "currentText") else ""
        code = code_w.text().strip() if isinstance(code_w, LineEdit) else ""
        return bool(brand and brand in screen.brands and code)


class UploadStrategy(BatchModeStrategy):
    """Strategy for the Upload operation."""

    def collect_items(self, screen, valid_rows):
        items = []
        for row in valid_rows:
            brand = screen._get_inner_widget(row, COL["brand"]).currentText()
            code_raw = screen._get_inner_widget(row, COL["code"]).text().strip()
            code = screen._normalize_code(code_raw)
            url = screen._get_inner_widget(row, COL["url"]).text().strip() if screen._get_inner_widget(row, COL["url"]) else ""

            desc_w = screen._get_inner_widget(row, COL["description"])
            desc = desc_w.currentText() if desc_w and isinstance(desc_w, ComboBox) else ""

            frameset_w = screen._get_inner_widget(row, COL["frameset"])
            frameset = frameset_w.isChecked() if frameset_w and isinstance(frameset_w, CheckBox) else False

            disclaimer_w = screen._get_inner_widget(row, COL["disclaimer"])
            disclaimer = disclaimer_w.isChecked() if disclaimer_w and isinstance(disclaimer_w, CheckBox) else False

            # Collect per-row attributes
            attr_values = []
            for defn in ATTRIBUTE_DEFINITIONS:
                col_idx = ATTR_COL_MAP.get(defn["name"])
                if col_idx is None:
                    continue
                combo = screen._get_inner_widget(row, col_idx)
                if combo and isinstance(combo, ComboBox):
                    val = combo.currentText().strip()
                    if val:
                        attr_values.append({"name": defn["name"], "value": val, "field": defn["field"]})

            items.append({
                "brand": brand,
                "code": code,
                "url": url,
                "description_name": desc or None,
                "frameset_only": frameset,
                "append_disclaimer": disclaimer,
                "attribute_values": attr_values,
            })
        return items

    def create_worker(self, screen, items, table_row_indices, multi_session, session_manager):
        master_password = getattr(screen.main, "_unlocked_master_password", None)
        if multi_session and session_manager:
            from GUI_Qt.workers.batch_workers import ParallelBatchUploadWorker
            return ParallelBatchUploadWorker(
                items, session_manager, screen.main,
                master_password=master_password,
                table_row_indices=table_row_indices,
            )
        from GUI_Qt.workers.batch_workers import BatchUploadWorker
        return BatchUploadWorker(
            items, screen.main,
            master_password=master_password,
            table_row_indices=table_row_indices,
        )

    def validate_row(self, screen, row):
        if not super().validate_row(screen, row):
            return False
        url_w = screen._get_inner_widget(row, COL["url"])
        url = url_w.text().strip() if url_w and isinstance(url_w, LineEdit) else ""
        return bool(url)

    def get_template_headers(self, tr):
        headers = [
            tr("batch.table.brand"), tr("batch.table.code"), tr("batch.table.url"),
            tr("batch.table.desc"), tr("batch.table.frameset"), tr("batch.table.disclaimer"),
        ]
        for defn in ATTRIBUTE_DEFINITIONS:
            headers.append(defn["name"])
        return headers

    def get_template_example(self, tr):
        return ["KROSS", "12345", "https://example.com/product", "", "FALSE", "FALSE"] + [""] * len(ATTRIBUTE_DEFINITIONS)

    def parse_excel_row(self, excel_row, tr):
        def _str(val):
            return str(val).strip() if val else ""
        def _bool(val):
            return str(val).strip().lower() in ("true", "yes", "1", "taip") if val else False

        result = {
            "brand": _str(excel_row[0]) if len(excel_row) > 0 else "",
            "code": _str(excel_row[1]) if len(excel_row) > 1 else "",
            "url": _str(excel_row[2]) if len(excel_row) > 2 else "",
            "description": _str(excel_row[3]) if len(excel_row) > 3 else "",
            "frameset": _bool(excel_row[4]) if len(excel_row) > 4 else False,
            "disclaimer": _bool(excel_row[5]) if len(excel_row) > 5 else False,
        }
        # Optional attribute columns (indices 6..6+N)
        for i, defn in enumerate(ATTRIBUTE_DEFINITIONS):
            col = 6 + i
            if len(excel_row) > col and excel_row[col]:
                result[f"attr_{defn['name']}"] = _str(excel_row[col])
        return result


class DescriptionsStrategy(BatchModeStrategy):
    """Strategy for the Descriptions operation."""

    def collect_items(self, screen, valid_rows):
        items = []
        for row in valid_rows:
            brand = screen._get_inner_widget(row, COL["brand"]).currentText()
            code_raw = screen._get_inner_widget(row, COL["code"]).text().strip()
            code = screen._normalize_code(code_raw)

            desc_w = screen._get_inner_widget(row, COL["description"])
            desc = desc_w.currentText() if desc_w and isinstance(desc_w, ComboBox) else ""

            disclaimer_w = screen._get_inner_widget(row, COL["disclaimer"])
            disclaimer = disclaimer_w.isChecked() if disclaimer_w and isinstance(disclaimer_w, CheckBox) else False

            items.append({
                "row": row,
                "brand": brand,
                "code": code,
                "description": desc,
                "append_disclaimer": disclaimer,
            })
        return items

    def create_worker(self, screen, items, table_row_indices, multi_session, session_manager):
        if multi_session and session_manager:
            from GUI_Qt.workers.batch_workers import ParallelBatchDescriptionsWorker
            return ParallelBatchDescriptionsWorker(screen.main, session_manager, items)
        from GUI_Qt.workers.batch_workers import BatchDescriptionsWorker
        return BatchDescriptionsWorker(screen.main, items)

    def get_template_headers(self, tr):
        return [
            tr("batch.table.brand"), tr("batch.table.code"),
            tr("batch.table.desc"), tr("batch.table.disclaimer"),
        ]

    def get_template_example(self, tr):
        return ["KROSS", "12345", "", "FALSE"]

    def parse_excel_row(self, excel_row, tr):
        def _str(val):
            return str(val).strip() if val else ""
        def _bool(val):
            return str(val).strip().lower() in ("true", "yes", "1", "taip") if val else False

        return {
            "brand": _str(excel_row[0]) if len(excel_row) > 0 else "",
            "code": _str(excel_row[1]) if len(excel_row) > 1 else "",
            "description": _str(excel_row[2]) if len(excel_row) > 2 else "",
            "disclaimer": _bool(excel_row[3]) if len(excel_row) > 3 else False,
        }


class TitlesStrategy(BatchModeStrategy):
    """Strategy for the Titles operation."""

    def collect_items(self, screen, valid_rows):
        items = []
        for row in valid_rows:
            brand = screen._get_inner_widget(row, COL["brand"]).currentText()
            code_raw = screen._get_inner_widget(row, COL["code"]).text().strip()
            code = screen._normalize_code(code_raw)

            lt_w = screen._get_inner_widget(row, COL["title_lt"])
            en_w = screen._get_inner_widget(row, COL["title_en"])
            title_lt = lt_w.text().strip() if lt_w and isinstance(lt_w, LineEdit) else ""
            title_en = en_w.text().strip() if en_w and isinstance(en_w, LineEdit) else ""

            items.append({
                "row": row,
                "brand": brand,
                "code": code,
                "title_lt": title_lt,
                "title_en": title_en,
            })
        return items

    def create_worker(self, screen, items, table_row_indices, multi_session, session_manager):
        if multi_session and session_manager:
            from GUI_Qt.workers.batch_workers import ParallelBatchTitlesWorker
            return ParallelBatchTitlesWorker(screen.main, session_manager, items)
        from GUI_Qt.workers.batch_workers import BatchTitlesWorker
        return BatchTitlesWorker(screen.main, items)

    def validate_row(self, screen, row):
        if not super().validate_row(screen, row):
            return False
        lt_w = screen._get_inner_widget(row, COL["title_lt"])
        en_w = screen._get_inner_widget(row, COL["title_en"])
        lt = lt_w.text().strip() if lt_w and isinstance(lt_w, LineEdit) else ""
        en = en_w.text().strip() if en_w and isinstance(en_w, LineEdit) else ""
        return bool(lt or en)

    def get_template_headers(self, tr):
        return [
            tr("batch.table.brand"), tr("batch.table.code"),
            tr("batch.table.title_lt"), tr("batch.table.title_en"),
        ]

    def get_template_example(self, tr):
        return ["KROSS", "12345", "Dviratis KROSS Pavadinimas 2025", "Bicycle KROSS Name 2025"]

    def parse_excel_row(self, excel_row, tr):
        def _str(val):
            return str(val).strip() if val else ""

        return {
            "brand": _str(excel_row[0]) if len(excel_row) > 0 else "",
            "code": _str(excel_row[1]) if len(excel_row) > 1 else "",
            "title_lt": _str(excel_row[2]) if len(excel_row) > 2 else "",
            "title_en": _str(excel_row[3]) if len(excel_row) > 3 else "",
        }


# Strategy registry
STRATEGIES: dict[str, BatchModeStrategy] = {
    "upload": UploadStrategy(),
    "descriptions": DescriptionsStrategy(),
    "titles": TitlesStrategy(),
}

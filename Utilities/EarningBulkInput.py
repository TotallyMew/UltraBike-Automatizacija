"""Parse pasted SKUs or Excel's tab-separated SKU/name columns."""

from __future__ import annotations

import csv
import io


class BulkEarningInputError(ValueError):
    def __init__(self, reason: str, row: int = 0):
        self.reason = reason
        self.row = row
        super().__init__(f"{reason} on row {row}")


def parse_bulk_earning_input(text: str) -> list[dict[str, str | None]]:
    text = str(text or "").strip("\r\n\ufeff")
    if not text.strip():
        return []
    # A single SKU column is plain text; two Excel columns use TSV quoting,
    # including names containing embedded newlines or quote characters.
    if "\t" not in text:
        rows = [[line] for line in text.splitlines()]
    else:
        try:
            rows = list(csv.reader(io.StringIO(text), delimiter="\t", strict=True))
        except csv.Error as error:
            raise BulkEarningInputError("format") from error
    result = []
    first_product_row = True
    for index, row in enumerate(rows, 1):
        if not row or not any(value.strip() for value in row):
            continue
        if len(row) > 2:
            raise BulkEarningInputError("columns", index)
        sku = row[0].strip()
        is_first = first_product_row
        first_product_row = False
        if is_first and sku.casefold() == "sku":
            if len(row) == 1 or row[1].strip().casefold() in {
                "name", "product name", "product_name", "pavadinimas", "produkto pavadinimas",
            }:
                continue
        if not sku:
            raise BulkEarningInputError("sku", index)
        name = (row[1].strip() or None) if len(row) == 2 else None
        result.append({"sku": sku, "product_name": name})
    return result

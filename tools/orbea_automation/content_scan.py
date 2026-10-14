"""Read-only Pimbo completeness scans, persisted beside existing photo scans."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from Managers.PimboProductEditor import PimboProductEditor, PIMBO_PRODUCTS_URL
from tools.kross_automation.service import KrossPimboClient
from .checkpoint import CHECKPOINT_NAME, RunCheckpoint, atomic_write_json, utc_now
from .models import CancellationToken
from .report import write_report
from .service import PIMBO_AUTOMATION_LOCK


CONTENT_STATUSES = {"content_not_checked": "Data not checked", "missing_content": "Missing data",
                    "content_complete": "Required data complete", "content_not_found": "Not found in Pimbo",
                    "content_scan_error": "Data scan error"}


@dataclass(frozen=True)
class PimboContentScanResult:
    sku: str
    status: str
    product_id: str = ""
    product_name: str = ""
    product_url: str = ""
    missing_attributes: list[str] = field(default_factory=list)
    missing_specifications: list[str] = field(default_factory=list)
    attributes_checked: int | None = None
    specifications_checked: int | None = None
    error: str = ""
    checked_at: str = ""
    checkpoint_path: str = ""


def matches_content_status(state, status):
    if status == "missing_attributes":
        return state.get("status") == "missing_content" and bool(state.get("missing_attributes"))
    if status == "missing_general_specs":
        return state.get("status") == "missing_content" and bool(state.get("missing_specifications"))
    return state.get("status", "content_not_checked") == status


class PimboContentScanService:
    def __init__(self, driver, *, client_factory=KrossPimboClient, editor_factory=PimboProductEditor):
        self.driver, self.client_factory, self.editor_factory = driver, client_factory, editor_factory
        self._cancellation = CancellationToken()

    def cancel(self):
        self._cancellation.cancel()

    def run(self, run_dir, skus, *, cancellation=None, progress=None, log=None, item_finished=None):
        token = cancellation or self._cancellation
        self._cancellation = token
        path = Path(run_dir) / CHECKPOINT_NAME
        checkpoint = RunCheckpoint(path, json.loads(path.read_text(encoding="utf-8")), resumed=True)
        rows = {row["sku"]: row for row in checkpoint.results if row.get("sku")}
        skus = tuple(dict.fromkeys(skus))
        if not skus or not set(skus) <= rows.keys():
            raise ValueError("Select products from the loaded Excel or saved collection")
        if any(sum(row.get("sku") == sku for row in checkpoint.results) != 1 for sku in skus):
            raise ValueError("The saved collection has multiple products for a selected SKU")
        if not PIMBO_AUTOMATION_LOCK.acquire(blocking=False):
            raise RuntimeError("Another Orbea Pimbo operation is running")
        results = []
        try:
            guard = self.editor_factory(self.driver)
            if guard.product_id and guard.is_dirty():
                raise RuntimeError("Save or discard your unsaved Pimbo changes before scanning")
            client = self.client_factory(self.driver)
            for index, sku in enumerate(skus, 1):
                if token.is_cancelled():
                    break
                if progress:
                    progress(f"Checking required Pimbo data: {index}/{len(skus)} — {sku}")
                row, fatal = rows[sku], ""
                found = None
                try:
                    found = client.find_by_variant_sku(sku)
                    if found.status != "pimbo_found":
                        result = PimboContentScanResult(sku, "content_not_found", error=found.note)
                    else:
                        if row.get("product_id") and row["product_id"] != found.pimbo_product_id:
                            raise ValueError("The saved SKU now belongs to a different Pimbo product")
                        editor = self.editor_factory(self.driver)
                        fields = editor.inspect_missing_content(expected_product_id=found.pimbo_product_id)
                        missing = fields["missing_attributes"] or fields["missing_specifications"]
                        result = PimboContentScanResult(sku, "missing_content" if missing else "content_complete",
                            found.pimbo_product_id, found.pimbo_product_name, found.pimbo_product_url, **fields)
                        if row.get("local_folder"):
                            folder = (checkpoint.run_dir / row["local_folder"]).resolve()
                            if not folder.is_relative_to(checkpoint.run_dir.resolve()):
                                raise ValueError("The saved product folder is outside the collection")
                            metadata = folder / "orbea-product.json"
                            if metadata.is_file():
                                saved = json.loads(metadata.read_text(encoding="utf-8"))
                                if saved.get("sku") != sku or saved.get("pimbo_product_id") not in ("", None, result.product_id):
                                    raise ValueError("The local package belongs to a different Pimbo product")
                                saved.update(pimbo_product_id=result.product_id, pimbo_product_name=result.product_name,
                                             pimbo_url=result.product_url)
                                atomic_write_json(metadata, saved)
                        row.update(product_id=result.product_id, title=result.product_name, product_url=result.product_url)
                except Exception as error:
                    result = PimboContentScanResult(sku, "content_scan_error", error=str(error))
                finally:
                    try:
                        current = self.editor_factory(self.driver)
                        if found and found.status == "pimbo_found" and current.product_id != found.pimbo_product_id:
                            fatal = "Product identity changed; the content scan stopped without navigating away"
                        elif current.product_id and current.is_dirty():
                            fatal = "Product has unsaved changes; the content scan stopped without navigating away"
                        elif found and found.status == "pimbo_found":
                            self.driver.get(PIMBO_PRODUCTS_URL)
                        elif current.product_id:
                            fatal = "An unverified product is open; the content scan stopped without navigating away"
                    except Exception as recovery:
                        fatal = f"Could not safely leave the inspected product: {recovery}"
                if fatal:
                    result = PimboContentScanResult(sku, "content_scan_error", error=fatal)
                result = PimboContentScanResult(**{**asdict(result), "checked_at": utc_now(), "checkpoint_path": str(path.resolve())})
                row["pimbo_content_scan"] = asdict(result)
                checkpoint.save()
                results.append(result)
                if log:
                    detail = "; ".join(filter(None, (
                        "Attributes: " + ", ".join(result.missing_attributes) if result.missing_attributes else "",
                        "Bendra informacija: " + ", ".join(result.missing_specifications) if result.missing_specifications else "",
                        result.error)))
                    log(f"{sku}: {CONTENT_STATUSES[result.status]}" + (f" — {detail}" if detail else ""))
                if item_finished:
                    item_finished(result)
                if fatal:
                    raise RuntimeError(fatal)
            checkpoint.data["content_scan_cancelled"] = token.is_cancelled()
            checkpoint.save()
            return tuple(results)
        finally:
            try:
                write_report(checkpoint)
                if log and checkpoint.workbook_path.name != "orbea_matches.xlsx":
                    log(f"Excel report saved separately because the original was open or read-only: {checkpoint.workbook_path}")
            finally:
                PIMBO_AUTOMATION_LOCK.release()

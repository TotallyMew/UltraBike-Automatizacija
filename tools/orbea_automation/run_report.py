"""Presentation data for an Orbea upload run, independent of Qt and Selenium."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import time
from uuid import uuid4


STAGE_LABELS = {
    "product_photos": "Upload product photos",
    "photo_order": "Arrange photos: side → front → back",
    "size_tables": "Upload size table",
    "geometry": "Upload geometry",
    "description_source": "Paste Orbea description",
    "description_magic_ai": "MagicAI description",
    "product_family": "Set family: Dviračiai",
    "brand": "Set brand: Orbea",
    "category_magic_ai": "MagicAI category",
    "translations": "Translate LT → EN / LV / EE",
    "save": "Save Draft product",
    "specifications_prefill": "Fill model, colour and frame sizes",
    "specifications_magic_ai": "MagicAI specifications",
    "publish_products": "Publish products: Draft → Published",
}


def stage_key(value):
    value = str(value).strip().casefold().replace("–", "-")
    for key, label in STAGE_LABELS.items():
        if value in {key, label.casefold()}:
            return key
    aliases = {
        "product photos": "product_photos", "product photo order": "photo_order",
        "size tables": "size_tables", "geometry": "geometry",
        "description source": "description_source", "description magicai": "description_magic_ai",
        "product family": "product_family", "brand": "brand", "category magicai": "category_magic_ai",
        "translations": "translations", "first save": "save", "specifications save": "save",
        "automatic save": "save", "specifications magicai": "specifications_magic_ai",
        "publish products": "publish_products", "publication": "publish_products",
    }
    if "specification pre-fill" in value:
        return "specifications_prefill"
    return aliases.get(value, "")


@dataclass(frozen=True)
class ErrorSummary:
    stage: str
    headline: str
    technical: str = ""


def summarize_error(raw, stage=""):
    """Keep the readable cause separate from Selenium documentation/stack traces."""
    raw = str(raw or "").strip()
    prefix, separator, rest = raw.partition(":")
    inferred = stage_key(prefix) if separator else ""
    stage = stage_key(stage) or inferred or stage
    if inferred:
        raw = rest.strip()
    marker = re.search(r"For documentation on this error|Stacktrace:|Traceback \(most recent call last\):", raw, re.I)
    readable = raw[:marker.start()].strip(" ;\n") if marker else raw
    technical = raw[marker.start():].strip() if marker else ""
    lines = [line.strip() for line in readable.splitlines() if line.strip()]
    headline = re.sub(r"^Message:\s*", "", lines[0] if lines else "The selected steps did not complete", flags=re.I)
    if len(lines) > 1:
        technical = "\n".join(lines[1:] + ([technical] if technical else []))
    if len(headline) > 260:
        technical = readable + ("\n" + technical if technical else "")
        headline = headline[:257].rstrip() + "…"
    return ErrorSummary(str(stage or ""), headline, technical)


@dataclass(frozen=True)
class LogEntry:
    timestamp: str
    level: str
    product: str
    stage: str
    message: str
    technical: str = ""

    def text(self, technical=True):
        step = f" [{STAGE_LABELS.get(self.stage, self.stage)}]" if self.stage else ""
        line = f"{self.timestamp} {self.level.upper():7} {self.product or 'Run'}{step} — {self.message}"
        return line + ("\n" + self.technical if technical and self.technical else "")


class OrbeaRunReport:
    def __init__(self, matches, options, root=None, *, browser_count=1):
        self.matches = tuple(matches)
        self.options = options
        self.browser_count = browser_count
        self.root = Path(root) if root else None
        self.selected_stages = tuple(options.selected_stages)
        self.started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        self._started = time.monotonic()
        self.duration = None
        self.results = {}
        self.states = {self.key(match): {} for match in self.matches}
        self.started_products = set()
        self.current_key = None
        self.current_stage = ""
        self.active_stages = {}
        self.entries = []
        self.finished = False
        self.stop_requested = False
        self.batch_error = ""
        self.log_path = None
        self.snapshot_path = None
        self.storage_error = ""
        if self.root:
            stem = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
            self.log_path = self.root / "upload-reports" / f"orbea-{stem}.log"
            self.snapshot_path = self.log_path.with_suffix(".json")

    @staticmethod
    def key(match):
        return str(match.local_folder or f"{match.sku}:{match.pimbo_product_id}")

    @property
    def elapsed(self):
        return self.duration if self.duration is not None else time.monotonic() - self._started

    @property
    def counts(self):
        ok = sum(result.succeeded for result in self.results.values())
        return {"succeeded": ok, "failed": len(self.results) - ok,
                "not_started": len(self.matches) - len(self.started_products),
                "in_progress": len(self.started_products - self.results.keys()),
                "warnings": sum(bool(result.preparation.warnings) for result in self.results.values())}

    def start_product(self, match):
        self.current_key = self.key(match)
        self.started_products.add(self.current_key)
        self.current_stage = ""
        self.active_stages[self.current_key] = ""
        self.add_log("info", "Started product", match.sku)

    def stage_changed(self, match, stage, state, detail=""):
        key = self.key(match)
        stage = stage_key(stage)
        if not stage or stage not in self.selected_stages:
            return
        self.states[key][stage] = state
        if state == "running":
            self.active_stages[key] = stage
        elif self.active_stages.get(key) == stage:
            self.active_stages[key] = ""
        if key == self.current_key:
            self.current_stage = self.active_stages.get(key, "")
        summary = summarize_error(detail, stage) if detail else None
        message = summary.headline if summary else {"running": "Started", "done": "Completed", "failed": "Failed", "skipped": "Skipped"}.get(state, state)
        self.add_log("error" if state == "failed" else "info", message, match.sku, stage,
                     summary.technical if summary else "")

    def add_log(self, level, message, product="", stage="", technical=""):
        entry = LogEntry(datetime.now().astimezone().isoformat(timespec="seconds"), level, product, stage, str(message), technical)
        self.entries.append(entry)
        if self.log_path and not self.storage_error:
            try:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open("a", encoding="utf-8") as stream:
                    stream.write(entry.text() + "\n")
            except OSError as error:
                self.storage_error = f"Could not save the run log: {error}"
        return entry

    def add_result(self, result):
        key = self.key(result.match)
        self.started_products.add(key)
        self.results[key] = result
        state = self.states[key]
        failed = self.failure_summaries(result)
        skipped = {summarize_error(warning).stage for warning in result.preparation.warnings if 'skipped because' in warning.casefold()}
        for stage in self.selected_stages:
            if stage in skipped or state.get(stage) == "skipped":
                state[stage] = "skipped"
            elif any(summary.stage == stage for summary in failed):
                state[stage] = "failed"
            elif stage in result.completed_stages:
                state[stage] = "done"
            else:
                state[stage] = "skipped"
        self.active_stages.pop(key, None)
        if key == self.current_key:
            self.current_key = next(reversed(self.active_stages), None)
        self.current_stage = self.active_stages.get(self.current_key, "")
        if not result.succeeded:
            for summary in failed:
                self.add_log("error", summary.headline, result.match.sku, summary.stage, summary.technical)
        for warning in result.preparation.warnings:
            summary = summarize_error(warning)
            self.add_log("warning", summary.headline, result.match.sku, summary.stage, summary.technical)
        self.add_log("info" if result.succeeded else "error", result.preparation.status.value.replace("_", " "), result.match.sku)

    @staticmethod
    def failure_summaries(result):
        preparation = result.preparation
        if result.succeeded:
            return []
        summaries = [summarize_error(warning) for warning in preparation.warnings if 'skipped because' not in warning.casefold()]
        # Warnings are already the individual causes of the normalized aggregate error.
        if not summaries or (preparation.failed_stage and not any(item.stage == preparation.failed_stage for item in summaries)):
            summaries.append(summarize_error(preparation.error or "Product is blocked or did not complete", preparation.failed_stage))
        return list(dict.fromkeys(summaries))

    def failure_groups(self):
        groups = {}
        for key, result in self.results.items():
            for summary in self.failure_summaries(result):
                group = groups.setdefault((summary.stage, summary.headline.casefold()), {"summary": summary, "products": set()})
                group["products"].add(key)
        return sorted(groups.values(), key=lambda group: (-len(group["products"]), group["summary"].stage))

    def finish(self, *, stop_requested=False, batch_error=""):
        self.finished = True
        self.stop_requested = stop_requested
        self.batch_error = str(batch_error or "")
        self.duration = time.monotonic() - self._started
        self.add_log("error" if batch_error else "info", self.outcome()[1])
        self.save_snapshot()

    def outcome(self):
        counts = self.counts
        pending = len(self.matches) - len(self.results)
        if self.batch_error:
            return "Run stopped after an error", summarize_error(self.batch_error).headline + f" {pending} product(s) were not processed."
        if self.stop_requested and pending:
            return "Run stopped by you", f"Stop was requested. Active products finished; {pending} product(s) were not processed."
        if pending:
            return "Run ended before all products finished", f"{pending} product(s) were not processed. Review the log before continuing."
        if counts["failed"]:
            return "Run finished with failures", "All products were attempted. Review the grouped causes before retrying failed steps."
        if counts["warnings"]:
            return "Run finished with warnings", "All products were attempted. Review the warning subset below."
        return "Run finished successfully", "All selected products completed."

    def filtered_entries(self, *, level="all", search="", product="", by_product=False):
        query = search.casefold().strip()
        entries = [entry for entry in self.entries if (level == "all" or entry.level == level)
                   and (not product or entry.product == product) and (not query or query in entry.text().casefold())]
        return sorted(entries, key=lambda entry: (entry.product, entry.timestamp)) if by_product else entries

    def save_snapshot(self):
        if not self.snapshot_path:
            return
        try:
            from Utilities.UploadResultsReport import result_record
            data = {"started_at": self.started_at, "duration_seconds": self.elapsed,
                    "browser_count": self.browser_count,
                    "stop_requested": self.stop_requested, "batch_error": self.batch_error,
                    "selected_stages": self.selected_stages, "counts": self.counts,
                    "products": [{"sku": match.sku, "name": match.pimbo_product_name or match.orbea_product_name,
                                  "folder": match.local_folder, "states": self.states[self.key(match)],
                                  "result": result_record(self.results[self.key(match)]) if self.key(match) in self.results else None}
                                 for match in self.matches], "log": [asdict(entry) for entry in self.entries]}
            self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            self.snapshot_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as error:
            self.storage_error = f"Could not save the run report: {error}"

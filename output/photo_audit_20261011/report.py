"""Turn the read-only photo inspection into a readable diagnostic report."""
import collections
import json
from pathlib import Path

from tools.orbea_automation.photo_packages import pimbo_photo_colours

root = Path(__file__).parent
audit = json.loads((root / "audit.json").read_text(encoding="utf-8"))
errors = [r for r in audit["incomplete"] if r["photos_status"] == "error"]
pending = [r for r in audit["incomplete"] if r["photos_status"] == "pending"]
empty_colours = [r for r in errors if not pimbo_photo_colours(
    {"title": r["title"], "catalogue_model": r["model"]}, source_model=r["model"])]
pending_empty = [r for r in pending if not pimbo_photo_colours(
    {"title": r["title"], "catalogue_model": r["model"]}, source_model=r["model"])]
assert len(errors) == 21 and len(empty_colours) == 20
assert len(pending) == 24 and all(not r["selected"] and not r["actual_photos"] for r in pending)
assert len(pending_empty) == 24
assert not audit["file_issues"]
assert all({"side", "front", "back"} <= {
    Path(f["path"]).stem.rsplit("_", 1)[-1] for f in r["files"]
} for r in audit["records"] if r["photos_status"] == "downloaded")

lines = [
    "# Orbea photo download audit — 11 October 2026",
    "",
    f"Saved run: `{audit['checkpoint']}`",
    "",
    "The latest redownload ran from 01:39 to 02:53 on 11 October 2026 (Europe/Kiev) and finished with partial status.",
    "",
    "| Result | Matched products |",
    "| --- | ---: |",
    "| Downloaded and verified | 331 |",
    "| Colour matching error | 21 |",
    "| Pending, excluded from latest selection | 24 |",
    "| Total with a verified Orbea source match | 376 |",
    "",
    "All 1,108 checkpoint-listed PNG files exist, pass PNG integrity checks and full pixel decoding, and contain visible pixels. Every file is 4100 × 2310. Each downloaded product has side, front and back views; 66 products also have one or two detail views. There are 711 distinct physical files because some packages share storage through hard links.",
    "",
    "The latest batch selected 349 of the 376 matched rows: 328 selected rows now have photos and 21 failed. The 27 excluded rows comprise 24 WILD/M products without photos and three DENNA products that already have photos. The saved Pimbo scan records three uploaded photos for each of those DENNA products. This audit checks local download completion; it does not establish the current uploaded-photo status of every product in Pimbo.",
    "",
    "## Why 21 products failed",
    "",
    "The saved errors are all `Pimbo photo colour not found`, before any photo files were assigned to the affected packages. No HTTP download or image-decoding error was recorded for these 21 products.",
    "",
    "Twenty failures share a model-name parsing problem. `parse_orbea_name()` in `tools/orbea_automation/specifications.py` only separates the colour if the title has a year or starts with the exact source model followed by whitespace. `pimbo_photo_colours()` and `match_photo_colour()` in `tools/orbea_automation/photo_packages.py` depend on that split. Running the current splitter against the saved titles and source model names reproduces an empty candidate list for these 20 rows:",
    "",
    "| Pimbo naming | Orbea naming | Failed rows |",
    "| --- | --- | ---: |",
    "| RALLON 442 ENDURO / DH | Rallon Enduro / Rallon DH | 8 |",
    "| RALLON/M RS-LTD / RS-TEAM | Rallon RS-LTD Mullet / Rallon RS-TEAM Mullet | 6 |",
    "| OIZ OMX+IL SL R+K | Oiz OMX | 5 |",
    "| TERRA RACE M12 LTD 1X PWR | Terra Race M12eLTD 1X PWR | 1 |",
    "",
    "Six of these 20 rows are Custom. Their names do not split successfully, so the separate Your Design capture branch is never selected; they are mistakenly sent to matching against published regular colours.",
    "",
    "The remaining failure is `U14305GP`: Pimbo spells the colour `Nickel (Matt) - Metallic Cinnamon (Matt)` and Orbea spells it `Nickel (Matt) - Metallic Cinamon (Matt)`. The model splits successfully, but the strict colour-name comparison rejects the spelling difference. The Orbea browser page exposes colour code `GP`, matching this SKU's suffix.",
    "",
    "Browser verification confirmed representative source pages, visible configuration previews and the published colour choices:",
    "",
    "- [Rallon Enduro](https://www.orbea.com/en-be/rallon-enduro): M6, M7 and M8 are published; 442 mm corresponds to U911TTCC.",
    "- [Rallon RS-TEAM Mullet](https://www.orbea.com/en-be/rallon-rs-team-mullet): SV and SR are published for U303TTCC.",
    "- [Oiz OMX](https://www.orbea.com/en-be/oiz-omx): PJ, PK, PL and PM are published for U908TTCC. Its image template has side, front and back views.",
    "- [Terra Race M12eLTD 1X PWR](https://www.orbea.com/en-be/terra-race-m12eltd-1x-pwr): the heading contains the extra e and offers customizable colours.",
    "- [Terra M35TEAM](https://www.orbea.com/en-be/terra-m35team): GP is labelled Metallic Cinamon.",
    "- [Wild LT M20 Mullet](https://www.orbea.com/en-be/wild-lt-m20-mullet): X5, X6 and X7 are published for U317TTCC.",
    "",
    "Direct HTTP reads returned 403 security checks during this investigation; the browser loaded the product pages normally. Those investigation-time 403 responses are separate from the saved redownload's colour-matching errors.",
    "",
    "## Why the 24 WILD/M products still have no photos",
    "",
    "All 24 remain pending with zero PNGs in their current photos folders. None of their row keys occurs in the latest checkpoint's selected-download list. They were not attempted in the latest batch. The redownload UI collects only checked, currently visible products, and collection honours the saved row-key selection. The checkpoint cannot establish whether the user left them unchecked or a model filter hid them.",
    "",
    "Their Pimbo names use WILD/M LT while their source names use Wild LT … Mullet. The current title splitter also returns no colour candidates for all 24, so including them in another retry without fixing matching is likely to produce the same class of error.",
    "",
    "## Required correction",
    "",
    "Resolve the colour from the verified product/SKU colour code when that code exists in the source template, handle verified Custom SKUs through the separate default Your Design capture, and retain checks that the source model matches the SKU. This avoids relying on alias-heavy display names and spelling variations. Then retry the 21 failed rows and include the 24 excluded WILD/M rows. Repeating the same 349-row selection with the current matcher will leave these gaps.",
    "",
    "There are also 93 unmatched rows in the saved scan; they have no assigned photo packages and require an Orbea source match before collection. They are outside the 376 matched-product totals above.",
    "",
    "## Failed product list",
    "",
    "| SKU | Pimbo product | Reason |",
    "| --- | --- | --- |",
]
for row in errors:
    reason = "Cinnamon / Cinamon spelling" if row["sku"] == "U14305GP" else "Model alias prevents colour/Custom extraction"
    lines.append(f"| {row['sku']} | {row['title'].replace('|', '/')} | {reason} |")
lines += ["", "## Pending products excluded from the latest batch", "", "| Source model | SKUs |", "| --- | --- |"]
groups = collections.defaultdict(list)
for row in pending:
    groups[row["model"]].append(row["sku"])
for model, skus in sorted(groups.items()):
    lines.append(f"| {model} | {', '.join(skus)} |")
lines += ["", "Machine-readable file checks and row details are saved in `audit.json` beside this report.", ""]
(root / "report.md").write_text("\n".join(lines), encoding="utf-8")
print("Report written; integrity, required views, 20 parsing failures, and 24 excluded pending rows verified.")

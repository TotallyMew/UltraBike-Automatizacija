"""Read-only inspection of a saved Orbea photo run; write evidence locally."""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

from PIL import Image


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    checkpoint = Path(sys.argv[1])
    output = Path(__file__).parent
    run = checkpoint.parent
    data = json.loads(checkpoint.read_text(encoding="utf-8-sig"))
    selected = data.get("selected_download_row_keys")
    verified = {}
    issues = []
    records = []
    dimensions = collections.Counter()
    for row in data["results"]:
        stage = row.get("collection_stages", {}).get("photos", {})
        files = []
        for name in stage.get("files", []):
            path = run / name
            error = ""
            try:
                if not path.resolve().is_relative_to(run.resolve()):
                    raise ValueError("File is outside the saved run")
                stat = path.stat()
                key = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
                if key not in verified:
                    with Image.open(path) as img:
                        size, mode, fmt = img.size, img.mode, img.format
                        img.verify()
                    with Image.open(path) as img:
                        img.load()
                        visible = img.getchannel("A").getbbox() if "A" in img.getbands() else img.getbbox()
                        if not visible:
                            raise ValueError("Image has no visible pixels")
                    verified[key] = {"size": size, "mode": mode, "format": fmt}
                dimensions[str(verified[key]["size"])] += 1
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                issues.append({"sku": row.get("sku"), "file": name, "error": error})
            files.append({"path": name, "verified": not error, "error": error})
        folder = run / row["local_folder"] if row.get("local_folder") else None
        actual = sorted(str(p.relative_to(run)) for p in (folder / "photos").glob("*.png")) if folder else []
        records.append({
            "sku": row.get("sku"), "title": row.get("title"), "match_status": row.get("status"),
            "model": row.get("catalogue_model"), "url": row.get("catalogue_url"),
            "photos_status": stage.get("status", "absent"), "note": stage.get("note", ""),
            "capture_version": stage.get("capture_version"), "files": files,
            "selected": selected is None or row.get("row_key") in selected,
            "actual_photos": actual, "pimbo_photo_scan": row.get("pimbo_photo_scan", {}),
        })
    matched = [r for r in records if r["match_status"] == "code_match"]
    summary = {
        "checkpoint": str(checkpoint), "checkpoint_updated_at": data.get("updated_at"),
        "selected_rows": None if selected is None else len(selected), "matched_rows": len(matched),
        "matched_photo_statuses": dict(collections.Counter(r["photos_status"] for r in matched)),
        "all_row_match_statuses": dict(collections.Counter(r["match_status"] for r in records)),
        "all_row_photo_statuses": dict(collections.Counter(r["photos_status"] for r in records)),
        "matched_photo_file_references": sum(len(r["files"]) for r in matched),
        "all_photo_file_references": sum(len(r["files"]) for r in records),
        "verified_unique_files": len(verified), "file_issues": issues,
        "dimensions": dict(dimensions),
        "matched_file_counts": dict(collections.Counter(len(r["files"]) for r in matched if r["photos_status"] == "downloaded")),
        "nonmatched_rows_with_photos": [{k: r[k] for k in ("sku", "match_status", "title", "url")} for r in records if r["match_status"] != "code_match" and r["files"]],
        "incomplete": [r for r in matched if r["photos_status"] != "downloaded"],
        "records": records,
    }
    (output / "audit.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    compact = {k: v for k, v in summary.items() if k not in {"incomplete", "records", "nonmatched_rows_with_photos"}}
    compact["nonmatched_rows_with_photos"] = len(summary["nonmatched_rows_with_photos"])
    print(json.dumps(compact, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

"""
Standalone script: read image URLs from an Excel file and download images.

Requirements:
- pandas
- openpyxl
- requests
- beautifulsoup4

Install with:
    pip install pandas openpyxl requests

Usage example:
    python tools/download_images_from_excel.py \
        --excel input.xlsx --sheet Sheet1 --url-column image_url \
        --filename-column sku --outdir ./KROSS_images --concurrency 8

The script supports an optional `--filename-column` to name files from a column
(e.g., product SKU). If omitted, filenames are taken from the URL path or
fallback to an auto-incremented name.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# --- Edit these defaults directly in the script ---
# Change these values to set the defaults used when running from an IDE
# (you can still override them via command-line args).
DEFAULT_SHEET = 0  # sheet name or index (0 = first sheet)
DEFAULT_URL_COLUMN = "image_url"
DEFAULT_FILENAME_COLUMN = "sku"  # e.g. "sku" or None to use URL basenames
DEFAULT_OUTDIR = "C:/Users/User/Desktop/KrossUzbaigimas"
DEFAULT_CONCURRENCY = 8
DEFAULT_TIMEOUT = 15
DEFAULT_RETRIES = 2
# Excel file default: set this to the path of your Excel file so you can run
# the script from an IDE without entering arguments.
DEFAULT_EXCEL = "C:/Users/User/Desktop/Book1.xlsx"  # change to your file path or None

# Always group by this column (folder names taken from this column)
DEFAULT_GROUP_BY = DEFAULT_FILENAME_COLUMN
# ------------------------------------------------


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|]", "_", name)
    name = re.sub(r"\s+", "_", name)
    return name.strip("_. ")


def ext_from_url(url: str) -> str:
    parts = url.split("?")[0].split("#")[0].rsplit(".", 1)
    if len(parts) == 2 and 1 <= len(parts[1]) <= 5:
        return "." + re.sub(r"[^A-Za-z0-9]", "", parts[1])
    return ".jpg"


def download_image(url: str, dest: Path, timeout: int = 15, retries: int = 2) -> tuple[bool, str]:
    last_err = ""
    for attempt in range(1, retries + 2):
        try:
            resp = requests.get(url, stream=True, timeout=timeout)
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(8192):
                    if chunk:
                        f.write(chunk)
            return True, ""
        except Exception as e:
            last_err = str(e)
    return False, last_err


def process_row(index: int, url: str, filename_hint: Optional[str], outdir: Path, auto_index: int,
                timeout: int, retries: int, group_value: Optional[str] = None) -> dict:
    result = {
        "index": index,
        "url": url,
        "ok": False,
        "path": None,
        "error": None,
    }
    if not isinstance(url, str) or not url.strip():
        result["error"] = "empty URL"
        return result
    url = url.strip()

    # create group subfolder (folder names come from group_value)
    if group_value and isinstance(group_value, str) and group_value.strip():
        group_name = sanitize_filename(str(group_value))
        group_folder = outdir / group_name
        group_folder.mkdir(parents=True, exist_ok=True)
    else:
        group_folder = outdir

    # Always treat the URL as a product page: scrape image URLs and download them
    try:
        image_urls = scrape_image_urls(url, timeout=timeout)
    except Exception as e:
        result["error"] = f"scrape_failed: {e}"
        return result

    saved_any = False
    saved_paths = []
    for n, img_url in enumerate(image_urls, start=1):
        # derive filename per-image
        if filename_hint and isinstance(filename_hint, str) and filename_hint.strip():
            base_name = sanitize_filename(filename_hint)
            ext = ext_from_url(img_url)
            img_filename = f"{base_name}_{n}{ext}"
        else:
            img_basename = os.path.basename(img_url.split("?")[0].split("#")[0])
            if img_basename:
                img_filename = sanitize_filename(img_basename)
            else:
                img_filename = f"image_{auto_index:06d}_{n}.jpg"

        candidate = group_folder / img_filename
        if candidate.exists():
            stem, extension = os.path.splitext(candidate.name)
            i = 1
            while True:
                cand = candidate.parent / f"{stem}_{i}{extension}"
                if not cand.exists():
                    candidate = cand
                    break
                i += 1

        ok, err = download_image(img_url, candidate, timeout=timeout, retries=retries)
        if ok:
            saved_any = True
            saved_paths.append(str(candidate))

    if saved_any:
        result["ok"] = True
        result["path"] = ",".join(saved_paths)
        return result
    else:
        result["error"] = "no images downloaded"
        return result


def scrape_image_urls(page_url: str, timeout: int = 15) -> list:
    """Fetch a page and return a list of absolute image URLs found on it.

    Heuristics: <img src|data-src|srcset>, meta og:image, link rel=image_src.
    Filters common image extensions and resolves relative URLs.
    """
    resp = requests.get(page_url, timeout=timeout)
    resp.raise_for_status()
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")
    found = []

    # og:image and similar meta
    meta_og = soup.find("meta", property="og:image")
    if meta_og and meta_og.get("content"):
        found.append(meta_og["content"])

    link_img = soup.find("link", rel=lambda v: v and "image" in v)
    if link_img and link_img.get("href"):
        found.append(link_img["href"])

    # img tags
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original")
        if not src:
            srcset = img.get("srcset")
            if srcset:
                src = srcset.split(",")[0].strip().split(" ")[0]
        if src:
            found.append(src)

    # filter by extension and resolve relative URLs
    good = []
    seen = set()
    for src in found:
        if not src:
            continue
        abs_url = urljoin(page_url, src)
        parsed = urlparse(abs_url)
        if not parsed.scheme.startswith("http"):
            continue
        low = abs_url.lower()
        if any(ext in low for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"]):
            if abs_url not in seen:
                seen.add(abs_url)
                good.append(abs_url)

    return good


def main(argv=None):
    parser = argparse.ArgumentParser(description="Download images listed in an Excel sheet.")
    parser.add_argument("--excel", "-x", required=False, default=DEFAULT_EXCEL, help=f"Path to the Excel file (default: {DEFAULT_EXCEL})")
    parser.add_argument("--sheet", "-s", default=DEFAULT_SHEET, help=f"Sheet name or index (default: {DEFAULT_SHEET})")
    parser.add_argument("--url-column", "-u", default=DEFAULT_URL_COLUMN, help=f"Column name that contains image URLs (default: {DEFAULT_URL_COLUMN})")
    parser.add_argument("--filename-column", "-f", default=DEFAULT_FILENAME_COLUMN,
                        help=f"Optional column to use for output filenames (e.g., SKU). Default: {DEFAULT_FILENAME_COLUMN}")
    parser.add_argument("--outdir", "-o", default=DEFAULT_OUTDIR, help=f"Output directory (default: {DEFAULT_OUTDIR})")
    parser.add_argument("--concurrency", "-c", type=int, default=DEFAULT_CONCURRENCY, help=f"Number of download threads (default: {DEFAULT_CONCURRENCY})")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"HTTP timeout seconds (default: {DEFAULT_TIMEOUT})")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help=f"Download retries per URL (default: {DEFAULT_RETRIES})")
    parser.add_argument("--group-by", "-g", default=DEFAULT_GROUP_BY,
                        help=f"Optional column to create subfolders from (e.g. sku). Default: {DEFAULT_GROUP_BY}")

    args = parser.parse_args(argv)

    excel_path = Path(args.excel)
    if not excel_path.exists():
        print(f"Excel file not found: {excel_path}")
        return 2

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    try:
        df = pd.read_excel(excel_path, sheet_name=args.sheet, engine="openpyxl")
    except Exception as e:
        print(f"Failed to read Excel file: {e}")
        return 3

    url_col = args.url_column
    if url_col not in df.columns:
        print(f"URL column '{url_col}' not found in sheet. Available columns: {list(df.columns)}")
        return 4

    fname_col = args.filename_column if args.filename_column in df.columns else None
    if args.filename_column and not fname_col:
        print(f"Warning: filename column '{args.filename_column}' not found; falling back to URL basenames.")

    group_col = args.group_by if args.group_by in df.columns else None
    if args.group_by and not group_col:
        print(f"Warning: group-by column '{args.group_by}' not found; no subfolders will be created.")

    rows = list(df.itertuples(index=False, name=None))
    # map column indices for performance
    col_index_map = {name: i for i, name in enumerate(df.columns)}
    url_idx = col_index_map[url_col]
    fname_idx = col_index_map[fname_col] if fname_col else None
    group_idx = col_index_map[group_col] if group_col else None

    tasks = []
    auto_index = 1
    for i, row in enumerate(rows, start=1):
        url = row[url_idx]
        filename_hint = row[fname_idx] if fname_idx is not None else None
        group_value = row[group_idx] if group_idx is not None else None
        tasks.append((i, url, filename_hint, auto_index, group_value))
        auto_index += 1

    total = len(tasks)
    print(f"Found {total} rows to process. Starting downloads to: {outdir}")

    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as exe:
        futs = {}
        for t in tasks:
            idx, url, fname_hint, auto_i, group_val = t
            fut = exe.submit(process_row, idx, url, fname_hint, outdir, auto_i, args.timeout, args.retries, group_val)
            futs[fut] = t
        for fut in as_completed(futs):
            res = fut.result()
            results.append(res)
            if res["ok"]:
                print(f"OK  [{res['index']}] -> {res['path']}")
            else:
                print(f"ERR [{res['index']}] {res['url']} -> {res['error']}")

    ok_count = sum(1 for r in results if r["ok"]) if results else 0
    err_count = total - ok_count
    print(f"Done. Success: {ok_count}, Failed: {err_count}")
    return 0 if err_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

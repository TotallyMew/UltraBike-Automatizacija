#!/usr/bin/env python3
"""Pinarello Bike Image Downloader

This module replaces the previous Selenium-based implementation.

Behavior (based on the user's provided new script):
- Scrapes Pinarello product page HTML with requests + BeautifulSoup
- Groups images by color variant (per-variant folders)
- Puts unclassified/extra images into a shared `_extra` folder
- If an image exceeds 7000x4900, resizes by 50%
- Saves all downloaded images as PNG

The GUI and command-line entry point use ``PinarelloScraper`` directly.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from io import BytesIO
from typing import Callable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image


PINARELLO_BASE_URL = "https://pinarello.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Resize rule: First 3 images per variant - resize to 4000x2998 if BOTH dimensions exceed limits
RESIZE_W = 4000
RESIZE_H = 2998
RESIZE_SCALE = 0.5

DEFAULT_MAX_WORKERS = 8

# Requested rule: if saved file is larger than 8,000,000 bytes, move it into
# a separate folder for manual resizing.
OVERSIZE_BYTES = 8_000_000
OVERSIZE_FOLDER_NAME = "_needs_resize"


def _log(log: Callable[[str], None] | None, message: str) -> None:
    if log is None:
        print(message)
        return
    try:
        log(message)
    except Exception:
        print(message)


def _sanitize_filename(name: str) -> str:
    return re.sub(r"[^\w\s-]", "", (name or "")).strip().replace(" ", "_") or "pinarello"


def _make_absolute(url: str) -> str:
    if (url or "").startswith("http"):
        return url
    return urljoin(PINARELLO_BASE_URL, url)


def _extract_hash(url: str) -> str:
    try:
        return os.path.basename(urlparse(url).path)
    except Exception:
        return url


def _dedupe_destination_path(dest_path: str) -> str:
    if not os.path.exists(dest_path):
        return dest_path

    base, ext = os.path.splitext(dest_path)
    i = 1
    while True:
        candidate = f"{base}__dup{i}{ext}"
        if not os.path.exists(candidate):
            return candidate
        i += 1


def _move_if_oversize(filepath: str, *, product_dir: str, threshold_bytes: int = OVERSIZE_BYTES) -> str | None:
    try:
        if not filepath or not os.path.isfile(filepath):
            return None
        if os.path.getsize(filepath) <= int(threshold_bytes):
            return None

        rel = None
        try:
            rel = os.path.relpath(filepath, start=product_dir)
        except Exception:
            rel = os.path.basename(filepath)

        oversize_root = os.path.join(product_dir, OVERSIZE_FOLDER_NAME)
        dest_path = os.path.join(oversize_root, rel)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        dest_path = _dedupe_destination_path(dest_path)

        shutil.move(filepath, dest_path)
        return dest_path
    except Exception:
        return None


@dataclass(frozen=True)
class _ImageTask:
    url: str
    filepath: str
    label: str
    kind: str  # 'variant' | 'gallery'
    index: int = 0  # Image index (1-based) for variant images, 0 for gallery


class PinarelloScraper:
    def __init__(self, url: str, *, log: Callable[[str], None] | None = None, max_workers: int = DEFAULT_MAX_WORKERS):
        self.url = (url or "").strip()
        self._log_cb = log
        self.max_workers = int(max_workers) if max_workers else DEFAULT_MAX_WORKERS

        self.session = requests.Session()
        self.session.headers.update({'User-Agent': USER_AGENT})

        self.variants: dict[str, dict] = {}  # gallery_id -> {code, name, images: []}
        self.extra_gallery_images: list[str] = []
        self.bike_name: str = ""

    def fetch_page(self) -> str:
        resp = self.session.get(self.url, timeout=30)
        resp.raise_for_status()
        return resp.text

    def _extract_full_variant_url(self, srcset: str) -> str | None:
        match = re.search(r"/storage/thumbs/Variant/\d+__resize__([a-f0-9]+\.png)", srcset or "")
        if match:
            return f"{PINARELLO_BASE_URL}/storage/Variant/{match.group(1)}"
        match = re.search(r"(https://pinarello\.com/storage/Variant/[a-f0-9]+\.png)", srcset or "")
        if match:
            return match.group(1)
        return None

    def _extract_best_image_url(self, img) -> str | None:
        parent_a = img.find_parent('a')
        if parent_a:
            href = parent_a.get('href', '')
            if '/storage/' in href and (href.endswith('.jpg') or href.endswith('.png') or href.endswith('.webp')):
                return _make_absolute(href)

        srcset = img.get('srcset', '')
        if srcset:
            for storage_type in ['ProductGallery', 'Technology', 'Product', 'Editorial', 'Variant']:
                pattern = rf"/(?:thumbs/)?{storage_type}/(?:_?\d+_?_?resize_?_?)?([a-f0-9]+\.(jpg|png|webp))"
                match = re.search(pattern, srcset)
                if match:
                    return f"{PINARELLO_BASE_URL}/storage/{storage_type}/{match.group(1)}"

        src = img.get('src', '')
        if '/storage/' in src:
            for storage_type in ['ProductGallery', 'Technology', 'Product', 'Editorial', 'Variant']:
                pattern = rf"/(?:thumbs/)?{storage_type}/(?:_?\d+_?_?resize_?_?)?([a-f0-9]+\.(jpg|png|webp))"
                match = re.search(pattern, src)
                if match:
                    return f"{PINARELLO_BASE_URL}/storage/{storage_type}/{match.group(1)}"
            if '/thumbs/' not in src:
                return _make_absolute(src)

        return None

    def _extract_gallery_images(self, section, all_room_images: set[str]):
        seen_hashes: set[str] = set()

        for img in section.find_all('img'):
            img_url = self._extract_best_image_url(img)
            if not img_url:
                continue

            img_hash = _extract_hash(img_url)
            if img_hash in seen_hashes:
                continue
            seen_hashes.add(img_hash)

            if img_url not in all_room_images and img_url not in self.extra_gallery_images:
                self.extra_gallery_images.append(img_url)

        for a in section.find_all('a', href=True):
            href = a.get('href', '')
            if '/storage/' in href and (href.endswith('.jpg') or href.endswith('.png') or href.endswith('.webp')):
                img_url = _make_absolute(href)
                img_hash = _extract_hash(img_url)
                if img_hash in seen_hashes:
                    continue
                seen_hashes.add(img_hash)

                if img_url not in all_room_images and img_url not in self.extra_gallery_images:
                    self.extra_gallery_images.append(img_url)

    def parse_page(self, html: str):
        soup = BeautifulSoup(html, 'html.parser')

        h1 = soup.find('h1')
        if h1:
            self.bike_name = h1.get_text(strip=True)
        else:
            self.bike_name = self.url.rstrip('/').split('/')[-1].replace('-', ' ').title()
        self.bike_name = _sanitize_filename(self.bike_name)
        _log(self._log_cb, f"  {self.bike_name}")

        variant_divs = soup.find_all('div', {'data-variation': True})
        for div in variant_divs:
            gallery_id = div.get('data-variation')
            if not gallery_id:
                continue

            strong = div.find('strong')
            code = strong.get_text(strip=True) if strong else f"X{gallery_id}"

            text = div.get_text()
            name_match = re.search(r"-\s*([A-Z][A-Z\s]+?)(?:\s*$|\s*\n)", text)
            if name_match:
                name = name_match.group(1).strip()
            else:
                name_match = re.search(r"(?:Di2|105)\s*-\s*(.+?)(?:\s*$|\s*\n)", text)
                name = name_match.group(1).strip() if name_match else f"Color {gallery_id}"

            self.variants[gallery_id] = {'code': code, 'name': name, 'images': []}

        gallery_rooms = soup.find_all('div', class_='main-gallery__room')
        for room in gallery_rooms:
            room_id = room.get('id')
            if not room_id or room_id not in self.variants:
                continue

            for elem in room.find_all(attrs={'data-image': True}):
                img_url = elem.get('data-image')
                if img_url:
                    img_url = _make_absolute(img_url)
                    if img_url not in self.variants[room_id]['images']:
                        self.variants[room_id]['images'].append(img_url)

        for a in soup.find_all('a', {'data-gallery': True}):
            gallery_id = a.get('data-gallery')
            if gallery_id not in self.variants:
                continue

            img = a.find('img')
            if img:
                srcset = img.get('srcset', '')
                if '/storage/Variant/' in srcset or '/storage/thumbs/Variant/' in srcset:
                    full_url = self._extract_full_variant_url(srcset)
                    if full_url and full_url not in self.variants[gallery_id]['images']:
                        self.variants[gallery_id]['images'].insert(0, full_url)

        all_room_images: set[str] = set()
        for v in self.variants.values():
            all_room_images.update(v['images'])

        gallery_classes = [
            ('section', 'gallery-wrap'),
            ('section', 'editorial-gallery'),
            ('div', 'editorial-gallery__container'),
            ('div', 'editorial-gallery__wrap'),
        ]
        for tag, class_name in gallery_classes:
            sections = soup.find_all(tag, class_=class_name)
            for section in sections:
                self._extract_gallery_images(section, all_room_images)

        editorial_classes = [
            ('section', 'editorial-inn'),
            ('div', 'editorial-inn__imageWrap'),
        ]
        for tag, class_name in editorial_classes:
            sections = soup.find_all(tag, class_=class_name)
            for section in sections:
                for img in section.find_all('img'):
                    img_url = self._extract_best_image_url(img)
                    if img_url and '/storage/' in img_url:
                        if '/MenuVoice/' in img_url or '/Geometry/' in img_url:
                            continue
                        if img_url not in all_room_images and img_url not in self.extra_gallery_images:
                            self.extra_gallery_images.append(img_url)

        for img in soup.find_all('img'):
            src = (img.get('src', '') or '') + (img.get('srcset', '') or '')
            if '/storage/Technology/' in src or '/storage/Product/' in src or '/storage/Editorial/' in src:
                img_url = self._extract_best_image_url(img)
                if img_url:
                    if img_url not in all_room_images and img_url not in self.extra_gallery_images:
                        self.extra_gallery_images.append(img_url)

        for elem in soup.find_all(attrs={'data-image': True}):
            img_url = elem.get('data-image')
            if img_url:
                img_url = _make_absolute(img_url)
                if '/storage/ProductGallery/' in img_url:
                    if img_url not in all_room_images and img_url not in self.extra_gallery_images:
                        self.extra_gallery_images.append(img_url)

        for a in soup.find_all('a', {'data-full': True}):
            img_url = a.get('data-full')
            if img_url:
                img_url = _make_absolute(img_url)
                if '/storage/ProductGallery/' in img_url:
                    if img_url not in all_room_images and img_url not in self.extra_gallery_images:
                        self.extra_gallery_images.append(img_url)

        _log(self._log_cb, f"  Found {len(self.variants)} color variants")
        if self.extra_gallery_images:
            _log(self._log_cb, f"  Found {len(self.extra_gallery_images)} gallery images")

    def _download_and_save_png(self, url: str, filepath: str, is_first_three: bool = False) -> str | None:
        """Download image and save as PNG

        Args:
            url: Image URL to download
            filepath: Destination file path
            is_first_three: If True, resize to 4000x2998 if both dimensions exceed limits

        Returns:
            Status message or None on failure
        """
        session = None
        try:
            session = requests.Session()
            session.headers.update({'User-Agent': USER_AGENT})

            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            img_bytes = resp.content

            with Image.open(BytesIO(img_bytes)) as img:
                width, height = img.size

                if img.mode == 'P':
                    if 'transparency' in img.info:
                        img = img.convert('RGBA')
                    else:
                        img = img.convert('RGB')
                elif img.mode not in ('RGB', 'RGBA'):
                    if 'A' in img.getbands():
                        img = img.convert('RGBA')
                    else:
                        img = img.convert('RGB')

                status_parts: list[str] = []

                # Only resize first 3 images of variants if BOTH dimensions exceed limits
                if is_first_three and width > RESIZE_W and height > RESIZE_H:
                    img = img.resize((RESIZE_W, RESIZE_H), Image.Resampling.LANCZOS)
                    status_parts.append(f"resized {width}x{height}→{RESIZE_W}x{RESIZE_H}")

                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                img.save(filepath, format='PNG', compress_level=6)

                return f"({', '.join(status_parts)})" if status_parts else ""

        except Exception:
            return None
        finally:
            if session:
                try:
                    session.close()
                except Exception:
                    pass

    def preview_variants(self) -> dict:
        """Fetch and parse variants without downloading images"""
        if not self.url:
            raise ValueError("URL is required")

        _log(self._log_cb, f"\nLoading product page...")
        html = self.fetch_page()

        _log(self._log_cb, "Finding color variants...")
        self.parse_page(html)

        if not self.variants:
            raise RuntimeError("No color variants found")

        # Return variant information with preview images
        variants_info = []
        for gallery_id, data in self.variants.items():
            variant_info = {
                'id': gallery_id,
                'code': data['code'],
                'name': data['name'],
                'image_count': len(data['images']),
                'preview_url': data['images'][0] if data['images'] else None,  # First image as preview
            }
            variants_info.append(variant_info)

        return {
            'bike_name': self.bike_name,
            'variants': variants_info,
            'extra_count': len(self.extra_gallery_images),
        }

    def run(self, output_dir: str, selected_variant_ids: list[str] = None) -> dict:
        if not self.url:
            raise ValueError("URL is required")
        if not output_dir:
            raise ValueError("output_dir is required")

        _log(self._log_cb, f"\nLoading product page...")
        html = self.fetch_page()

        _log(self._log_cb, "Finding color variants...")
        self.parse_page(html)

        if not self.variants:
            raise RuntimeError("No color variants found")

        # Filter variants if selection is provided
        if selected_variant_ids is not None:
            original_count = len(self.variants)
            self.variants = {k: v for k, v in self.variants.items() if k in selected_variant_ids}
            _log(self._log_cb, f"Selected {len(self.variants)} of {original_count} color variants")

        # Create folder structure
        sanitized_bike_name = _sanitize_filename(self.bike_name)
        product_dir = os.path.join(output_dir, sanitized_bike_name)
        os.makedirs(product_dir, exist_ok=True)
        _log(self._log_cb, f"\nSaving to: {product_dir}")

        # Create gallery folder
        gallery_dir = os.path.join(product_dir, "gallery")
        os.makedirs(gallery_dir, exist_ok=True)

        tasks: list[_ImageTask] = []
        used_folders: dict[str, int] = defaultdict(int)

        # Process color variants - folders go directly in main product folder
        for gallery_id, data in self.variants.items():
            code = data['code']
            name = _sanitize_filename(data['name'])

            # Create folder name: Code_ColorName format
            base_folder = f"{code}_{name}" if name else str(code)

            # Handle duplicate folder names
            if base_folder in used_folders:
                used_folders[base_folder] += 1
                folder_name = f"{base_folder}_v{used_folders[base_folder]}"
            else:
                used_folders[base_folder] = 0
                folder_name = base_folder

            # Create variant folder directly in product_dir (not in variants/ subfolder)
            variant_dir = os.path.join(product_dir, folder_name)
            os.makedirs(variant_dir, exist_ok=True)

            # Add variant images with descriptive naming
            for i, img_url in enumerate(data['images'], 1):
                filename = f"{code}_{i:02d}.png"
                filepath = os.path.join(variant_dir, filename)
                tasks.append(_ImageTask(img_url, filepath, f"{folder_name}/{filename}", "variant", i))

        # Process extra gallery images
        if self.extra_gallery_images:
            for i, img_url in enumerate(self.extra_gallery_images, 1):
                filename = f"gallery_{i:02d}.png"
                filepath = os.path.join(gallery_dir, filename)
                tasks.append(_ImageTask(img_url, filepath, f"gallery/{filename}", "gallery", 0))

        _log(self._log_cb, f"\nDownloading {len(tasks)} images...")
        _log(self._log_cb, f"  {len(self.variants)} color variants")
        _log(self._log_cb, f"  {len(self.extra_gallery_images)} gallery images")

        variant_downloaded = 0
        gallery_downloaded = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit tasks with is_first_three flag for variant images (index 1-3)
            futures = {
                executor.submit(
                    self._download_and_save_png,
                    t.url,
                    t.filepath,
                    is_first_three=(t.kind == 'variant' and 1 <= t.index <= 3)
                ): t for t in tasks
            }

            completed = 0
            for future in as_completed(futures):
                task = futures[future]
                try:
                    result = future.result()
                    if result is not None:
                        completed += 1
                        if task.kind == 'variant':
                            variant_downloaded += 1
                        elif task.kind == 'gallery':
                            gallery_downloaded += 1

                        status = f" {result}" if result else ""

                        # Only move gallery images >8MB to needs_resize folder
                        if task.kind == 'gallery':
                            moved_to = _move_if_oversize(task.filepath, product_dir=product_dir)
                            if moved_to:
                                rel_moved = os.path.relpath(moved_to, start=product_dir)
                                status = f"{status} → moved to {rel_moved} (>8MB)"

                        _log(self._log_cb, f"  [{completed}/{len(tasks)}] {task.label}{status}")
                    else:
                        _log(self._log_cb, f"  ✗ Failed: {task.label}")
                except Exception as e:
                    _log(self._log_cb, f"  ✗ Failed: {task.label} - {e}")

            executor.shutdown(wait=True)

        _log(self._log_cb, "\n✓ Download complete!")
        _log(self._log_cb, f"\nResults:")
        _log(self._log_cb, f"  {self.bike_name}")
        _log(self._log_cb, f"  {len(self.variants)} color variants ({variant_downloaded} images)")
        _log(self._log_cb, f"  {gallery_downloaded} gallery images")
        _log(self._log_cb, f"  {completed} of {len(tasks)} images saved")
        _log(self._log_cb, f"\nSaved to: {product_dir}")

        return {
            "url": self.url,
            "title": self.bike_name,
            "product_dir": product_dir,
            "gallery_count": gallery_downloaded,
            "variants": len(self.variants),
            "variant_images": variant_downloaded,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Pinarello product images into per-color-variant folders.")
    parser.add_argument("url", help="Pinarello product URL")
    parser.add_argument("--out", default="_pinarello_images", help="Output directory")
    args = parser.parse_args()

    PinarelloScraper(args.url).run(output_dir=args.out)


if __name__ == "__main__":
    main()

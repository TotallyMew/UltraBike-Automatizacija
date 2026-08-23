from __future__ import annotations

import html
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

from tools.orbea_automation.photos import (
    OrbeaPhotoProgress,
    OrbeaPhotoRunResult,
    OrbeaPhotoService,
    normalize_orbea_product_url,
    parse_orbea_photo_product,
    unique_orbea_product_urls,
)


PRODUCT_URL = "https://cms.orbea.com/en-au/kimu-27-h20"
CURRENT_PRODUCT_URL = "https://www.orbea.com/en-be/onna-20"
ASSET_HASH = "023437d0-05f5-4a16-8833-db83b99ce8c2"
ASSET_ROOT = f"https://cms.orbea.com/custom/{ASSET_HASH}"


def _js_payload(value) -> str:
    return json.dumps(value, separators=(",", ":")).replace('"', "\\u0022")


def _page_html() -> str:
    template = {
        "id": 312,
        "name": "Kimu 27 H20 2027",
        "hash": ASSET_HASH,
        "views": [
            {"type": "front", "order": 2, "status": "published"},
            {"type": "side", "order": 1, "status": "published"},
            {"type": "back", "order": 3, "status": "published"},
        ],
        "zones": [
            {
                "identifier": "C1",
                "type": "frame",
                "default_color": "J4",
                "colors": [
                    {"color": {"code": "J5", "name": {"en": "Aloha Green"}, "status": "published"}},
                    {"color": {"code": "J3", "name": {"en": "Cobalt Blue"}, "status": "published"}},
                    {"color": {"code": "J4", "name": {"en": "Metallic Sun Set"}, "status": "published"}},
                ],
            }
        ],
    }
    initializer = (
        f"templates = JSON.parse('{_js_payload([template])}'); "
        "template = 312; "
        f"currentTemplate = JSON.parse('{_js_payload(template)}');"
    )
    return (
        "<html><body><h1>Kimu 27 H20</h1>"
        f'<div id="product-bike-detail" x-init="{html.escape(initializer, quote=True)}"></div>'
        "</body></html>"
    )


def _image_bytes(colour: tuple[int, int, int, int]) -> bytes:
    image = Image.new("RGBA", (8, 5), colour)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class _Response:
    def __init__(self, url: str, content: bytes, status: int = 200):
        self.url = url
        self.content = content
        self.status_code = status
        self.headers = {"Content-Length": str(len(content))}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size=1):
        for index in range(0, len(self.content), chunk_size):
            yield self.content[index : index + chunk_size]

    def close(self):
        pass


class _Session:
    def __init__(self, responses):
        self.responses = dict(responses)
        self.calls: list[str] = []

    def get(self, url, **_kwargs):
        self.calls.append(url)
        response = self.responses.get(url)
        if response is None:
            return _Response(url, b"missing", 404)
        return _Response(url, response)

    def close(self):
        pass


class OrbeaPhotoDownloaderTests(unittest.TestCase):
    def test_canonical_duplicate_urls_are_detected(self):
        second = "https://cms.orbea.com/en-au/terra-h30"
        unique, duplicates = unique_orbea_product_urls(
            [PRODUCT_URL, f"{PRODUCT_URL}/?campaign=1", second]
        )

        self.assertEqual(unique, (PRODUCT_URL, second))
        self.assertEqual(duplicates, (PRODUCT_URL,))

    def test_batch_downloads_each_unique_product_once(self):
        second = "https://cms.orbea.com/en-au/terra-h30"
        calls: list[str] = []
        updates = []

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = OrbeaPhotoService()

            def fake_run(url, output_dir, *, progress, log, cancellation):
                calls.append(url)
                product_dir = root / url.rstrip("/").split("/")[-1]
                product_dir.mkdir()
                photo = product_dir / "J1_side.png"
                photo.write_bytes(b"photo")
                progress(
                    OrbeaPhotoProgress(
                        current=1,
                        total=1,
                        status="saved",
                        message=photo.name,
                        succeeded=1,
                    )
                )
                return OrbeaPhotoRunResult(
                    output_dir=root,
                    product_dir=product_dir,
                    title=product_dir.name,
                    variants=1,
                    views=1,
                    files=(photo,),
                    failures=(),
                    cancelled=False,
                )

            service.run = fake_run
            result = service.run_many(
                [PRODUCT_URL, f"{PRODUCT_URL}/?campaign=1", second],
                root,
                progress=updates.append,
            )

        self.assertEqual(calls, [PRODUCT_URL, second])
        self.assertEqual(result.requested, 3)
        self.assertEqual(result.products, 2)
        self.assertEqual(result.duplicates, 1)
        self.assertEqual(len(result.files), 2)
        self.assertEqual(updates[-1].current, 1000)

    def test_transparent_orbea_placeholder_is_not_treated_as_a_photo(self):
        transparent = Image.new("RGBA", (4, 3), (0, 0, 0, 0))
        visible = Image.new("RGBA", (4, 3), (255, 255, 255, 1))

        self.assertFalse(OrbeaPhotoService._has_visible_pixels(transparent))
        self.assertTrue(OrbeaPhotoService._has_visible_pixels(visible))

    def test_url_is_restricted_to_public_orbea_https_pages(self):
        self.assertEqual(
            normalize_orbea_product_url("cms.orbea.com/en-au/kimu-27-h20?ignored=1"),
            PRODUCT_URL,
        )
        self.assertEqual(
            normalize_orbea_product_url(f"{CURRENT_PRODUCT_URL}/?ignored=1"),
            CURRENT_PRODUCT_URL,
        )
        for invalid in (
            "http://cms.orbea.com/en-au/kimu-27-h20",
            "https://example.com/en-au/kimu-27-h20",
            "https://cms.orbea.com/custom/hash",
            "https://user:pass@cms.orbea.com/en-au/kimu-27-h20",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                normalize_orbea_product_url(invalid)

    def test_parser_finds_all_colours_and_orders_views(self):
        product = parse_orbea_photo_product(_page_html(), PRODUCT_URL)

        self.assertEqual(product.title, "Kimu 27 H20 2027")
        self.assertEqual(product.asset_hash, ASSET_HASH)
        self.assertEqual(product.views, ("side", "front", "back"))
        self.assertEqual(
            [(variant.code, variant.name) for variant in product.variants],
            [
                ("J3", "Cobalt Blue"),
                ("J4", "Metallic Sun Set"),
                ("J5", "Aloha Green"),
            ],
        )

    def test_service_composites_every_colour_and_view_and_caches_layers(self):
        manifest = {
            "hash": ASSET_HASH,
            "base": {"side": ["base"], "front": ["base"], "back": ["base"]},
            "zones": {"C1": {"views": {"side": ["J3", "J4", "J5"]}}},
            "components": [],
        }
        responses = {
            PRODUCT_URL: _page_html().encode("utf-8"),
            f"{ASSET_ROOT}/manifest.json": json.dumps(manifest).encode("utf-8"),
            f"{ASSET_ROOT}/side/base/XL/base.webp": _image_bytes((255, 255, 255, 255)),
            f"{ASSET_ROOT}/front/base/XL/base.webp": _image_bytes((10, 20, 30, 255)),
            f"{ASSET_ROOT}/back/base/XL/base.webp": _image_bytes((40, 50, 60, 255)),
            f"{ASSET_ROOT}/side/C1/XL/C1-J3.webp": _image_bytes((0, 0, 255, 255)),
            f"{ASSET_ROOT}/side/C1/XL/C1-J4.webp": _image_bytes((255, 100, 0, 255)),
            f"{ASSET_ROOT}/side/C1/XL/C1-J5.webp": _image_bytes((0, 180, 120, 255)),
        }
        session = _Session(responses)
        progress = []

        with tempfile.TemporaryDirectory() as temp_dir:
            result = OrbeaPhotoService(session=session).run(
                PRODUCT_URL, temp_dir, progress=progress.append
            )

            self.assertFalse(result.cancelled)
            self.assertEqual(result.variants, 3)
            self.assertEqual(result.views, 3)
            self.assertEqual(len(result.files), 9)
            self.assertFalse(result.failures)
            self.assertTrue((result.product_dir / "download_manifest.json").is_file())
            self.assertEqual(progress[-1].current, 9)
            self.assertEqual(progress[-1].succeeded, 9)

            j3_side = result.product_dir / "J3_Cobalt_Blue" / "J3_side.png"
            with Image.open(j3_side) as image:
                self.assertEqual(image.size, (8, 5))
                self.assertEqual(image.convert("RGBA").getpixel((0, 0)), (0, 0, 255, 255))

        # The three base views are reused rather than downloaded once per colour.
        self.assertEqual(session.calls.count(f"{ASSET_ROOT}/side/base/XL/base.webp"), 1)
        self.assertEqual(session.calls.count(f"{ASSET_ROOT}/front/base/XL/base.webp"), 1)
        self.assertEqual(session.calls.count(f"{ASSET_ROOT}/back/base/XL/base.webp"), 1)

    def test_service_uses_selenium_html_for_current_orbea_pages(self):
        manifest = {
            "hash": ASSET_HASH,
            "base": {"side": ["base"], "front": ["base"], "back": ["base"]},
            "zones": {"C1": {"views": {"side": ["J3", "J4", "J5"]}}},
            "components": [],
        }
        responses = {
            f"{ASSET_ROOT}/manifest.json": json.dumps(manifest).encode("utf-8"),
            f"{ASSET_ROOT}/side/base/XL/base.webp": _image_bytes((255, 255, 255, 255)),
            f"{ASSET_ROOT}/front/base/XL/base.webp": _image_bytes((10, 20, 30, 255)),
            f"{ASSET_ROOT}/back/base/XL/base.webp": _image_bytes((40, 50, 60, 255)),
            f"{ASSET_ROOT}/side/C1/XL/C1-J3.webp": _image_bytes((0, 0, 255, 255)),
            f"{ASSET_ROOT}/side/C1/XL/C1-J4.webp": _image_bytes((255, 100, 0, 255)),
            f"{ASSET_ROOT}/side/C1/XL/C1-J5.webp": _image_bytes((0, 180, 120, 255)),
        }
        session = _Session(responses)

        with tempfile.TemporaryDirectory() as temp_dir:
            result = OrbeaPhotoService(session=session).run_from_html(
                CURRENT_PRODUCT_URL,
                _page_html(),
                temp_dir,
                product_folder="product-photos",
            )

            self.assertEqual(result.product_dir.name, "product-photos")
            self.assertEqual(len(result.files), 9)

        self.assertNotIn(CURRENT_PRODUCT_URL, session.calls)


if __name__ == "__main__":
    unittest.main()

"""Download full-resolution product photos from Orbea's live configurator.

Orbea product pages render a canvas from a small manifest of 4100x2310 WebP
layers.  This module reads the product metadata embedded in either the current
``www.orbea.com`` page or a legacy ``cms.orbea.com`` page, downloads only the
declared layers from ``cms.orbea.com``, and creates one PNG for every published
colour/view that contains visible image data.  No authenticated Pimbo browser
is used.
"""

from __future__ import annotations

import hashlib
import html as html_module
import json
import os
import re
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import quote, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from PIL import Image
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import CancellationToken


ORBEA_HOST = "cms.orbea.com"
ORBEA_PAGE_HOSTS = {ORBEA_HOST, "www.orbea.com"}
ORBEA_ASSET_ROOT = f"https://{ORBEA_HOST}/custom"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)
MAX_PAGE_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BYTES = 80 * 1024 * 1024
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_-]{1,96}$")


@dataclass(frozen=True)
class OrbeaPhotoVariant:
    code: str
    name: str
    zone: str


@dataclass(frozen=True)
class OrbeaPhotoProduct:
    source_url: str
    title: str
    asset_hash: str
    views: tuple[str, ...]
    variants: tuple[OrbeaPhotoVariant, ...]
    zone_defaults: Mapping[str, str]


@dataclass(frozen=True)
class OrbeaPhotoProgress:
    current: int
    total: int
    status: str
    message: str = ""
    variant: str = ""
    view: str = ""
    succeeded: int = 0
    failed: int = 0


@dataclass(frozen=True)
class OrbeaPhotoRunResult:
    output_dir: Path
    product_dir: Path
    title: str
    variants: int
    views: int
    files: tuple[Path, ...]
    failures: tuple[str, ...]
    cancelled: bool
    unavailable: tuple[str, ...] = ()


@dataclass(frozen=True)
class OrbeaPhotoBatchResult:
    output_dir: Path
    product_results: tuple[OrbeaPhotoRunResult, ...]
    requested: int
    products: int
    duplicates: int
    variants: int
    views: int
    files: tuple[Path, ...]
    failures: tuple[str, ...]
    unavailable: tuple[str, ...]
    cancelled: bool


ProgressCallback = Callable[[OrbeaPhotoProgress], None]
LogCallback = Callable[[str], None]


def normalize_orbea_product_url(value: str) -> str:
    """Return a canonical public Orbea product URL or raise ``ValueError``."""

    raw = str(value or "").strip()
    if raw and "://" not in raw:
        raw = f"https://{raw}"
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as error:
        raise ValueError("Enter a valid Orbea product URL") from error
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").rstrip(".").lower() not in ORBEA_PAGE_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        raise ValueError("Only public https://www.orbea.com product URLs are supported")
    path = re.sub(r"/{2,}", "/", parsed.path or "").rstrip("/")
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) < 2 or segments[0].lower() in {"api", "build", "custom"}:
        raise ValueError("Enter a public Orbea bicycle product URL")
    host = (parsed.hostname or "").rstrip(".").lower()
    return urlunsplit(("https", host, path, "", ""))


def unique_orbea_product_urls(
    values: Iterable[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Canonicalize URLs and return ``(unique, duplicate_occurrences)``."""

    unique: list[str] = []
    duplicates: list[str] = []
    seen: set[str] = set()
    for value in values:
        url = normalize_orbea_product_url(value)
        key = url.casefold()
        if key in seen:
            duplicates.append(url)
            continue
        seen.add(key)
        unique.append(url)
    return tuple(unique), tuple(duplicates)


def _safe_filename(value: str, fallback: str) -> str:
    text = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "-", str(value or "").strip())
    text = re.sub(r"\s+", "_", text).strip(" ._-")
    return text[:120] or fallback


def _decode_json_parse_value(raw: str) -> Any:
    """Decode the argument of the page's ``JSON.parse('...')`` assignment."""

    candidate = html_module.unescape(str(raw or "")).strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # Orbea encodes quotes as \u0022 inside a JavaScript single-quoted string.
    # Raw double quotes are escaped only for the temporary JSON string wrapper.
    wrapped_body = re.sub(r'(?<!\\)"', r'\\"', candidate)
    try:
        decoded = json.loads(f'"{wrapped_body}"')
        return json.loads(decoded)
    except (json.JSONDecodeError, TypeError) as error:
        raise ValueError("Orbea product configuration could not be decoded") from error


def _json_assignment(source: str, name: str) -> Any:
    match = re.search(
        rf"\b{re.escape(name)}\s*=\s*JSON\.parse\(\s*'(.+?)'\s*\)\s*;",
        source,
        flags=re.DOTALL,
    )
    if not match:
        return None
    return _decode_json_parse_value(match.group(1))


def _localized_name(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, Mapping):
        for key in ("en", "en-au", "es"):
            name = value.get(key)
            if isinstance(name, str) and name.strip():
                return name.strip()
        for name in value.values():
            if isinstance(name, str) and name.strip():
                return name.strip()
    return fallback


def _order_value(item: Mapping[str, Any]) -> int:
    try:
        return int(item.get("order") or 0)
    except (TypeError, ValueError):
        return 0


def parse_orbea_photo_product(page_html: str, source_url: str) -> OrbeaPhotoProduct:
    """Parse the published configurator template embedded in a product page."""

    source_url = normalize_orbea_product_url(source_url)
    soup = BeautifulSoup(str(page_html or ""), "html.parser")
    detail = soup.select_one("#product-bike-detail")
    if detail is None:
        raise ValueError("This page does not contain an Orbea product configurator")
    initializer = detail.get("x-init", "")
    current = _json_assignment(initializer, "currentTemplate")
    templates = _json_assignment(initializer, "templates")

    template: Mapping[str, Any] | None = current if isinstance(current, Mapping) else None
    if template is None and isinstance(templates, list):
        template_id_match = re.search(r"\btemplate\s*=\s*(\d+)\s*;", initializer)
        template_id = int(template_id_match.group(1)) if template_id_match else None
        choices = [item for item in templates if isinstance(item, Mapping)]
        template = next(
            (item for item in choices if template_id is not None and item.get("id") == template_id),
            choices[0] if choices else None,
        )
    if template is None:
        raise ValueError("No published Orbea image template was found on this page")

    asset_hash = str(template.get("hash") or "").strip()
    if not _SAFE_SEGMENT.fullmatch(asset_hash):
        raise ValueError("The Orbea image template has an invalid asset identifier")

    raw_views = template.get("views") or []
    view_items = [item for item in raw_views if isinstance(item, Mapping)]
    view_items.sort(key=lambda item: (_order_value(item), str(item.get("type") or "")))
    views: list[str] = []
    for item in view_items:
        view = str(item.get("type") or "").strip()
        if item.get("status") not in (None, "published") or not _SAFE_SEGMENT.fullmatch(view):
            continue
        if view not in views:
            views.append(view)
    if not views:
        raise ValueError("The Orbea image template has no published views")

    zones = [item for item in (template.get("zones") or []) if isinstance(item, Mapping)]
    colour_zones = [item for item in zones if item.get("colors")]
    primary_zone = next(
        (item for item in colour_zones if str(item.get("identifier") or "").upper() == "C1"),
        next((item for item in colour_zones if item.get("type") == "frame"), None),
    )
    if primary_zone is None:
        raise ValueError("No published Orbea colour variants were found on this page")

    primary_identifier = str(primary_zone.get("identifier") or "").strip()
    if not _SAFE_SEGMENT.fullmatch(primary_identifier):
        raise ValueError("The Orbea colour zone has an invalid identifier")

    variants: list[OrbeaPhotoVariant] = []
    seen_codes: set[str] = set()
    for item in primary_zone.get("colors") or []:
        if not isinstance(item, Mapping):
            continue
        colour = item.get("color") if isinstance(item.get("color"), Mapping) else item
        if colour.get("status") not in (None, "published"):
            continue
        code = str(colour.get("code") or "").strip()
        if not _SAFE_SEGMENT.fullmatch(code) or code.lower() in seen_codes:
            continue
        name = _localized_name(colour.get("name"), code)
        variants.append(OrbeaPhotoVariant(code=code, name=name, zone=primary_identifier))
        seen_codes.add(code.lower())
    variants.sort(key=lambda variant: variant.code.casefold())
    if not variants:
        raise ValueError("No published Orbea colour variants were found on this page")

    defaults: dict[str, str] = {}
    for zone in colour_zones:
        identifier = str(zone.get("identifier") or "").strip()
        if not _SAFE_SEGMENT.fullmatch(identifier):
            continue
        default = str(zone.get("default_color") or "").strip()
        available = []
        for item in zone.get("colors") or []:
            if isinstance(item, Mapping):
                colour = item.get("color") if isinstance(item.get("color"), Mapping) else item
                code = str(colour.get("code") or "").strip()
                if _SAFE_SEGMENT.fullmatch(code):
                    available.append(code)
        if default not in available and available:
            default = available[0]
        if default:
            defaults[identifier] = default

    h1 = soup.find("h1")
    fallback_title = source_url.rstrip("/").split("/")[-1].replace("-", " ").title()
    title = _localized_name(template.get("name"), "")
    if not title and h1 is not None:
        title = h1.get_text(" ", strip=True)
    title = title or fallback_title
    return OrbeaPhotoProduct(
        source_url=source_url,
        title=title,
        asset_hash=asset_hash,
        views=tuple(views),
        variants=tuple(variants),
        zone_defaults=defaults,
    )


class OrbeaPhotoService:
    """Fetch and composite every published colour/view for one Orbea product."""

    def __init__(self, session: requests.Session | None = None) -> None:
        self._external_session = session
        self._cancellation = CancellationToken()

    @staticmethod
    def _new_session() -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.4,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
        )
        session.mount("https://", HTTPAdapter(max_retries=retry))
        session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/json,image/avif,image/webp,image/png,*/*;q=0.8",
            }
        )
        return session

    @staticmethod
    def _callback(callback: Callable[[Any], None] | None, value: Any) -> None:
        if callback is None:
            return
        try:
            callback(value)
        except Exception:
            pass

    @staticmethod
    def _is_cancelled(token: Any) -> bool:
        if token is None:
            return False
        method = getattr(token, "is_cancelled", None)
        if callable(method):
            return bool(method())
        method = getattr(token, "is_set", None)
        return bool(method()) if callable(method) else False

    def _cancelled(self, token: Any) -> bool:
        return self._cancellation.is_cancelled() or self._is_cancelled(token)

    def cancel(self) -> None:
        self._cancellation.cancel()

    @staticmethod
    def _read_response(response: Any, *, max_bytes: int) -> bytes:
        response.raise_for_status()
        length = response.headers.get("Content-Length") if hasattr(response, "headers") else None
        if length:
            try:
                parsed_length = int(length)
            except (TypeError, ValueError):
                parsed_length = 0
            if parsed_length > max_bytes:
                raise ValueError("Orbea response was larger than the safe download limit")
        if hasattr(response, "iter_content"):
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_content(chunk_size=256 * 1024):
                if not chunk:
                    continue
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("Orbea response was larger than the safe download limit")
                chunks.append(chunk)
            return b"".join(chunks)
        content = bytes(getattr(response, "content", b""))
        if len(content) > max_bytes:
            raise ValueError("Orbea response was larger than the safe download limit")
        return content

    @staticmethod
    def _validate_response_host(
        response: Any,
        allowed_hosts: set[str] | frozenset[str] | None = None,
    ) -> None:
        final_url = str(getattr(response, "url", "") or "")
        if final_url:
            parsed = urlsplit(final_url)
            allowed = allowed_hosts or {ORBEA_HOST}
            if (
                parsed.scheme.lower() != "https"
                or (parsed.hostname or "").rstrip(".").lower() not in allowed
            ):
                raise ValueError("Orbea redirected the download to an unsupported host")

    def _get_bytes(
        self,
        session: Any,
        url: str,
        *,
        max_bytes: int,
        referer: str,
        allowed_hosts: set[str] | frozenset[str] | None = None,
    ) -> bytes:
        response = session.get(url, timeout=(10, 45), stream=True, headers={"Referer": referer})
        try:
            self._validate_response_host(response, allowed_hosts)
            return self._read_response(response, max_bytes=max_bytes)
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    @staticmethod
    def _manifest_url(product: OrbeaPhotoProduct) -> str:
        return f"{ORBEA_ASSET_ROOT}/{quote(product.asset_hash, safe='')}/manifest.json"

    @staticmethod
    def _layer_url(product: OrbeaPhotoProduct, view: str, group: str, layer: str) -> str:
        filename = layer if layer.lower().endswith(".webp") else f"{layer}.webp"
        layer_stem = filename[:-5]
        for segment in (view, group, layer_stem):
            if not _SAFE_SEGMENT.fullmatch(segment):
                raise ValueError("Orbea manifest contained an unsafe image path")
        return (
            f"{ORBEA_ASSET_ROOT}/{quote(product.asset_hash, safe='')}/"
            f"{quote(view, safe='')}/{quote(group, safe='')}/XL/{quote(filename, safe='')}"
        )

    @staticmethod
    def _manifest_layers(
        manifest: Mapping[str, Any],
        product: OrbeaPhotoProduct,
        variant: OrbeaPhotoVariant,
        view: str,
    ) -> list[tuple[str, str]]:
        layers: list[tuple[str, str]] = []
        base = manifest.get("base")
        base_values = base.get(view, []) if isinstance(base, Mapping) else []
        for name in base_values if isinstance(base_values, list) else []:
            layer = str(name or "").strip()
            if layer:
                layers.append(("base", layer))

        zones = manifest.get("zones")
        if isinstance(zones, Mapping):
            for zone, data in zones.items():
                zone = str(zone or "").strip()
                if not isinstance(data, Mapping) or not _SAFE_SEGMENT.fullmatch(zone):
                    continue
                view_map = data.get("views")
                available = view_map.get(view, []) if isinstance(view_map, Mapping) else []
                available_codes = {str(code) for code in available if code}
                selected = (
                    variant.code
                    if zone == variant.zone
                    else str(product.zone_defaults.get(zone, "") or "")
                )
                if selected and selected in available_codes:
                    layers.append((zone, f"{zone}-{selected}"))
        return layers

    def inspect_product(self, url: str) -> tuple[OrbeaPhotoProduct, Mapping[str, Any]]:
        """Fetch and return parsed product metadata plus the official manifest."""

        self._cancellation = CancellationToken()
        source_url = normalize_orbea_product_url(url)
        session = self._external_session or self._new_session()
        owns_session = self._external_session is None
        try:
            page_bytes = self._get_bytes(
                session,
                source_url,
                max_bytes=MAX_PAGE_BYTES,
                referer=source_url,
                allowed_hosts=ORBEA_PAGE_HOSTS,
            )
            product = parse_orbea_photo_product(page_bytes.decode("utf-8", errors="replace"), source_url)
            manifest_bytes = self._get_bytes(
                session,
                self._manifest_url(product),
                max_bytes=MAX_MANIFEST_BYTES,
                referer=source_url,
            )
            manifest = json.loads(manifest_bytes.decode("utf-8"))
            if not isinstance(manifest, Mapping) or manifest.get("hash") not in (None, product.asset_hash):
                raise ValueError("Orbea returned an invalid image manifest")
            return product, manifest
        finally:
            if owns_session:
                session.close()

    @staticmethod
    def _compose(images: list[Image.Image]) -> Image.Image:
        if not images:
            raise ValueError("No image layers were declared for this view")
        size = images[0].size
        canvas = Image.new("RGBA", size, (0, 0, 0, 0))
        for image in images:
            if image.size != size:
                raise ValueError("Orbea returned image layers with mismatched dimensions")
            canvas.alpha_composite(image.convert("RGBA"))
        return canvas

    @staticmethod
    def _has_visible_pixels(image: Image.Image) -> bool:
        """Return false for Orbea's transparent placeholder view layers."""

        alpha = image.getchannel("A") if image.mode == "RGBA" else None
        return alpha is None or alpha.getbbox() is not None

    @staticmethod
    def _atomic_save(image: Image.Image, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=f".{destination.stem}-",
                suffix=".tmp",
                dir=destination.parent,
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
            image.save(temporary, format="PNG", optimize=True)
            os.replace(temporary, destination)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    def run(
        self,
        url: str,
        output_dir: str | Path,
        *,
        progress: ProgressCallback | None = None,
        log: LogCallback | None = None,
        cancellation: Any = None,
        page_html: str | None = None,
        product_folder: str | None = None,
    ) -> OrbeaPhotoRunResult:
        """Download all colour variants and views, retaining successful files."""

        self._cancellation = CancellationToken()
        source_url = normalize_orbea_product_url(url)
        if not str(output_dir or "").strip():
            raise ValueError("Choose an output folder")
        output_root = Path(output_dir).expanduser().resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        session = self._external_session or self._new_session()
        owns_session = self._external_session is None
        files: list[Path] = []
        failures: list[str] = []
        unavailable: list[str] = []
        layer_cache: dict[str, Image.Image] = {}

        try:
            self._callback(log, f"Loading Orbea product: {source_url}")
            if page_html is None:
                page_bytes = self._get_bytes(
                    session,
                    source_url,
                    max_bytes=MAX_PAGE_BYTES,
                    referer=source_url,
                    allowed_hosts=ORBEA_PAGE_HOSTS,
                )
                product_html = page_bytes.decode("utf-8", errors="replace")
            else:
                product_html = str(page_html)
            product = parse_orbea_photo_product(product_html, source_url)
            manifest_bytes = self._get_bytes(
                session,
                self._manifest_url(product),
                max_bytes=MAX_MANIFEST_BYTES,
                referer=source_url,
            )
            manifest = json.loads(manifest_bytes.decode("utf-8"))
            if not isinstance(manifest, Mapping) or manifest.get("hash") not in (None, product.asset_hash):
                raise ValueError("Orbea returned an invalid image manifest")

            product_dir = output_root / _safe_filename(
                product_folder or product.title,
                "Orbea_product",
            )
            product_dir.mkdir(parents=True, exist_ok=True)
            total = len(product.variants) * len(product.views)
            completed = 0
            self._callback(
                log,
                f"Found {len(product.variants)} colours and {len(product.views)} views ({total} images)",
            )

            for variant in product.variants:
                if self._cancelled(cancellation):
                    break
                variant_folder = product_dir / _safe_filename(
                    f"{variant.code}_{variant.name}", variant.code
                )
                for view in product.views:
                    if self._cancelled(cancellation):
                        break
                    label = f"{variant.code} {variant.name} — {view}"
                    self._callback(
                        progress,
                        OrbeaPhotoProgress(
                            current=completed,
                            total=total,
                            status="downloading",
                            message=label,
                            variant=variant.code,
                            view=view,
                            succeeded=len(files),
                            failed=len(failures),
                        ),
                    )
                    try:
                        layer_specs = self._manifest_layers(manifest, product, variant, view)
                        if not layer_specs:
                            raise ValueError("No official image layers are available")
                        images: list[Image.Image] = []
                        for group, layer in layer_specs:
                            layer_url = self._layer_url(product, view, group, layer)
                            cached = layer_cache.get(layer_url)
                            if cached is None:
                                payload = self._get_bytes(
                                    session,
                                    layer_url,
                                    max_bytes=MAX_IMAGE_BYTES,
                                    referer=source_url,
                                )
                                with Image.open(BytesIO(payload)) as opened:
                                    if (
                                        opened.width <= 0
                                        or opened.height <= 0
                                        or opened.width * opened.height > 50_000_000
                                    ):
                                        raise ValueError("Orbea returned an unsafe image size")
                                    opened.load()
                                    cached = opened.convert("RGBA")
                                layer_cache[layer_url] = cached
                            images.append(cached)
                        composite = self._compose(images)
                        if not self._has_visible_pixels(composite):
                            status = "unavailable"
                            message = f"Skipped {label}: Orbea does not provide an image for this view"
                            unavailable.append(label)
                            self._callback(log, message)
                            completed += 1
                            self._callback(
                                progress,
                                OrbeaPhotoProgress(
                                    current=completed,
                                    total=total,
                                    status=status,
                                    message=message,
                                    variant=variant.code,
                                    view=view,
                                    succeeded=len(files),
                                    failed=len(failures),
                                ),
                            )
                            continue
                        destination = variant_folder / _safe_filename(
                            f"{variant.code}_{view}.png", f"{variant.code}.png"
                        )
                        self._atomic_save(composite, destination)
                        files.append(destination)
                        status = "saved"
                        message = f"Saved {destination.relative_to(product_dir)}"
                        self._callback(log, message)
                    except Exception as error:
                        status = "failed"
                        message = f"{label}: {type(error).__name__}: {error}"
                        failures.append(message)
                        self._callback(log, f"Failed {message}")
                    completed += 1
                    self._callback(
                        progress,
                        OrbeaPhotoProgress(
                            current=completed,
                            total=total,
                            status=status,
                            message=message,
                            variant=variant.code,
                            view=view,
                            succeeded=len(files),
                            failed=len(failures),
                        ),
                    )

            cancelled = self._cancelled(cancellation)
            metadata = {
                "source_url": product.source_url,
                "product": product.title,
                "asset_hash": product.asset_hash,
                "colours": [
                    {"code": item.code, "name": item.name} for item in product.variants
                ],
                "views": list(product.views),
                "files": [str(path.relative_to(product_dir)) for path in files],
                "failures": failures,
                "unavailable": unavailable,
                "cancelled": cancelled,
                "sha256": {
                    str(path.relative_to(product_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in files
                },
            }
            metadata_path = product_dir / "download_manifest.json"
            temporary_metadata = metadata_path.with_suffix(".json.tmp")
            try:
                temporary_metadata.write_text(
                    json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                os.replace(temporary_metadata, metadata_path)
            finally:
                if temporary_metadata.exists():
                    temporary_metadata.unlink()
            if not files and not cancelled:
                raise RuntimeError("No Orbea product photos could be saved")
            return OrbeaPhotoRunResult(
                output_dir=output_root,
                product_dir=product_dir,
                title=product.title,
                variants=len(product.variants),
                views=len(product.views),
                files=tuple(files),
                failures=tuple(failures),
                cancelled=cancelled,
                unavailable=tuple(unavailable),
            )
        finally:
            for image in layer_cache.values():
                try:
                    image.close()
                except Exception:
                    pass
            if owns_session:
                session.close()

    def run_from_html(
        self,
        url: str,
        page_html: str,
        output_dir: str | Path,
        *,
        product_folder: str = "product-photos",
        progress: ProgressCallback | None = None,
        log: LogCallback | None = None,
        cancellation: Any = None,
    ) -> OrbeaPhotoRunResult:
        """Download official photos using HTML already loaded by Selenium."""

        return self.run(
            url,
            output_dir,
            progress=progress,
            log=log,
            cancellation=cancellation,
            page_html=page_html,
            product_folder=product_folder,
        )

    def run_many(
        self,
        urls: Iterable[str],
        output_dir: str | Path,
        *,
        progress: ProgressCallback | None = None,
        log: LogCallback | None = None,
        cancellation: Any = None,
    ) -> OrbeaPhotoBatchResult:
        """Download several products, ignoring canonical duplicate URLs."""

        raw_urls = tuple(str(value or "").strip() for value in urls if str(value or "").strip())
        unique_urls, duplicates = unique_orbea_product_urls(raw_urls)
        if not unique_urls:
            raise ValueError("Enter at least one Orbea product URL")
        if not str(output_dir or "").strip():
            raise ValueError("Choose an output folder")
        output_root = Path(output_dir).expanduser().resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        self._cancellation = CancellationToken()

        product_results: list[OrbeaPhotoRunResult] = []
        files: list[Path] = []
        failures: list[str] = []
        unavailable: list[str] = []
        total_products = len(unique_urls)
        if duplicates:
            self._callback(
                log,
                f"Ignored {len(duplicates)} duplicate product URL"
                + ("s" if len(duplicates) != 1 else ""),
            )

        for product_index, url in enumerate(unique_urls, start=1):
            if self._cancelled(cancellation):
                break
            self._callback(log, f"Product {product_index}/{total_products}: {url}")
            files_before = len(files)
            failures_before = len(failures)

            def batch_progress(update: OrbeaPhotoProgress) -> None:
                child_total = max(1, int(update.total or 0))
                child_fraction = max(0.0, min(1.0, int(update.current or 0) / child_total))
                overall = ((product_index - 1) + child_fraction) / total_products
                self._callback(
                    progress,
                    OrbeaPhotoProgress(
                        current=int(overall * 1000),
                        total=1000,
                        status=update.status,
                        message=(
                            f"Product {product_index}/{total_products} • {update.message}"
                            if update.message
                            else f"Product {product_index}/{total_products}"
                        ),
                        variant=update.variant,
                        view=update.view,
                        succeeded=files_before + int(update.succeeded or 0),
                        failed=failures_before + int(update.failed or 0),
                    ),
                )

            try:
                result = self.run(
                    url,
                    output_root,
                    progress=batch_progress,
                    log=log,
                    cancellation=cancellation,
                )
            except Exception as error:
                message = f"{url}: {type(error).__name__}: {error}"
                failures.append(message)
                self._callback(log, f"Product failed: {message}")
                self._callback(
                    progress,
                    OrbeaPhotoProgress(
                        current=int(product_index * 1000 / total_products),
                        total=1000,
                        status="failed",
                        message=f"Product {product_index}/{total_products} failed",
                        succeeded=len(files),
                        failed=len(failures),
                    ),
                )
                continue

            product_results.append(result)
            files.extend(result.files)
            failures.extend(result.failures)
            unavailable.extend(result.unavailable)
            if result.cancelled:
                break

        cancelled = self._cancelled(cancellation) or any(
            result.cancelled for result in product_results
        )
        if not files and not cancelled:
            detail = failures[0] if failures else "No product photos were available"
            raise RuntimeError(f"No Orbea product photos could be saved. {detail}")
        return OrbeaPhotoBatchResult(
            output_dir=output_root,
            product_results=tuple(product_results),
            requested=len(raw_urls),
            products=len(product_results),
            duplicates=len(duplicates),
            variants=sum(result.variants for result in product_results),
            views=sum(result.views for result in product_results),
            files=tuple(files),
            failures=tuple(failures),
            unavailable=tuple(unavailable),
            cancelled=cancelled,
        )


def download_orbea_photos(
    url: str,
    output_dir: str | Path,
    *,
    progress: ProgressCallback | None = None,
    log: LogCallback | None = None,
    cancellation: Any = None,
) -> OrbeaPhotoRunResult:
    """Convenience wrapper used by command-line and desktop callers."""

    return OrbeaPhotoService().run(
        url,
        output_dir,
        progress=progress,
        log=log,
        cancellation=cancellation,
    )


def download_orbea_photo_batches(
    urls: Iterable[str],
    output_dir: str | Path,
    *,
    progress: ProgressCallback | None = None,
    log: LogCallback | None = None,
    cancellation: Any = None,
) -> OrbeaPhotoBatchResult:
    """Convenience wrapper for a deduplicated multi-product download."""

    return OrbeaPhotoService().run_many(
        urls,
        output_dir,
        progress=progress,
        log=log,
        cancellation=cancellation,
    )

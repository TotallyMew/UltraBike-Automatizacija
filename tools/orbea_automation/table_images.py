"""Direct Orbea image downloader for pasted product URLs."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit, urlunsplit

from .models import CancellationToken


ORBEA_TABLE_HOSTS = {"www.orbea.com", "cms.orbea.com"}


@dataclass(frozen=True)
class OrbeaTableProgress:
    current: int
    total: int
    status: str
    message: str = ""
    succeeded: int = 0
    failed: int = 0


@dataclass(frozen=True)
class OrbeaTableProductResult:
    url: str
    folder: Path
    geometry_status: str
    size_guide_status: str
    geometry_variants: tuple[dict[str, Any], ...]
    files: tuple[Path, ...]
    errors: tuple[str, ...]
    photo_files: tuple[Path, ...] = ()
    photo_variants: int = 0
    photo_views: int = 0


@dataclass(frozen=True)
class OrbeaTableBatchResult:
    output_dir: Path
    manifest_path: Path
    product_results: tuple[OrbeaTableProductResult, ...]
    requested: int
    products: int
    duplicates: int
    files: tuple[Path, ...]
    failures: tuple[str, ...]
    unavailable: tuple[str, ...]
    cancelled: bool
    photo_files: tuple[Path, ...] = ()
    photo_variants: int = 0
    photo_views: int = 0


ProgressCallback = Callable[[OrbeaTableProgress], None]
LogCallback = Callable[[str], None]


def normalize_orbea_table_url(value: str) -> str:
    """Return a canonical public Orbea product-page URL."""

    raw = str(value or "").strip()
    if raw and "://" not in raw:
        raw = f"https://{raw}"
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as error:
        raise ValueError("Enter a valid Orbea product URL") from error
    host = (parsed.hostname or "").rstrip(".").lower()
    if (
        parsed.scheme.lower() != "https"
        or host not in ORBEA_TABLE_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        raise ValueError("Only public https://www.orbea.com product URLs are supported")
    path = re.sub(r"/{2,}", "/", parsed.path or "").rstrip("/")
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) < 2 or segments[-1].casefold() in {
        "api",
        "build",
        "catalog",
        "custom",
        "m",
        "support",
    }:
        raise ValueError("Enter an Orbea bicycle product-page URL")
    return urlunsplit(("https", host, path, "", ""))


def unique_orbea_table_urls(
    values: Iterable[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    unique: list[str] = []
    duplicates: list[str] = []
    seen: set[str] = set()
    for value in values:
        url = normalize_orbea_table_url(value)
        key = url.casefold()
        if key in seen:
            duplicates.append(url)
            continue
        seen.add(key)
        unique.append(url)
    return tuple(unique), tuple(duplicates)


class OrbeaTableImageService:
    """Download selected Orbea images without Pimbo discovery or matching."""

    def __init__(
        self,
        driver_factory=None,
        *,
        browser_name: str = "chrome",
        photo_service_factory=None,
    ) -> None:
        self.driver_factory = driver_factory
        self.browser_name = str(browser_name or "chrome").strip().casefold()
        self.photo_service_factory = photo_service_factory
        self._cancellation = CancellationToken()
        self._photo_service = None

    @staticmethod
    def _callback(callback: Callable[[Any], None] | None, value: Any) -> None:
        if callback is not None:
            try:
                callback(value)
            except Exception:
                pass

    @staticmethod
    def _is_cancelled(token: Any) -> bool:
        if token is None:
            return False
        for name in ("is_cancelled", "is_set"):
            method = getattr(token, name, None)
            if callable(method):
                return bool(method())
        return False

    def _cancelled(self, token: Any) -> bool:
        return self._cancellation.is_cancelled() or self._is_cancelled(token)

    def cancel(self) -> None:
        self._cancellation.cancel()
        if self._photo_service is not None and hasattr(self._photo_service, "cancel"):
            try:
                self._photo_service.cancel()
            except Exception:
                pass

    def _create_driver(self):
        if self.driver_factory is not None:
            return self.driver_factory()
        from tools.orbea_table_image_downloader import create_driver

        return create_driver(self.browser_name, False)

    def _create_photo_service(self):
        factory = self.photo_service_factory
        if factory is None:
            from .photos import OrbeaPhotoService

            return OrbeaPhotoService()
        if not isinstance(factory, type) and hasattr(factory, "run_from_html"):
            return factory
        return factory()

    @staticmethod
    def _folder_name(url: str) -> str:
        from tools.orbea_table_image_downloader import slugify

        page = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
        return slugify(page, "orbea-bike")

    @staticmethod
    def _write_manifest(
        destination: Path,
        *,
        requested: int,
        duplicates: int,
        products: list[OrbeaTableProductResult],
        cancelled: bool,
    ) -> Path:
        payload = {
            "requested": requested,
            "duplicates": duplicates,
            "cancelled": cancelled,
            "products": [
                {
                    **asdict(product),
                    "folder": str(product.folder),
                    "files": [str(path) for path in product.files],
                    "photo_files": [str(path) for path in product.photo_files],
                }
                for product in products
            ],
        }
        temporary = destination.with_name(f".{destination.name}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)
        return destination

    def run_many(
        self,
        urls: Iterable[str],
        output_dir: str | Path,
        *,
        progress: ProgressCallback | None = None,
        log: LogCallback | None = None,
        cancellation: Any = None,
        download_geometry: bool = True,
        download_size_guide: bool = True,
        download_product_photos: bool = False,
    ) -> OrbeaTableBatchResult:
        """Download the selected official assets for supplied product pages."""

        from tools.orbea_table_image_downloader import (
            TABLE_STATUS_DOWNLOADED,
            TABLE_STATUS_NOT_AVAILABLE,
            CaptureTimeouts,
            capture_orbea_tables,
        )

        raw_urls = tuple(
            str(value or "").strip() for value in urls if str(value or "").strip()
        )
        unique_urls, duplicates = unique_orbea_table_urls(raw_urls)
        if not unique_urls:
            raise ValueError("Enter at least one Orbea product URL")
        if not str(output_dir or "").strip():
            raise ValueError("Choose an output folder")
        if not any(
            (download_geometry, download_size_guide, download_product_photos)
        ):
            raise ValueError("Select at least one Orbea image type")
        output_root = Path(output_dir).expanduser().resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        manifest_path = output_root / "download_manifest.json"
        self._cancellation = CancellationToken()

        products: list[OrbeaTableProductResult] = []
        files: list[Path] = []
        photo_files: list[Path] = []
        photo_variants = 0
        photo_views = 0
        failures: list[str] = []
        unavailable: list[str] = []
        driver = None
        self._photo_service = None
        total = len(unique_urls)
        if duplicates:
            self._callback(log, f"Ignored {len(duplicates)} duplicate product URL(s)")

        try:
            driver = self._create_driver()
            for index, url in enumerate(unique_urls, start=1):
                if self._cancelled(cancellation):
                    break
                folder = output_root / self._folder_name(url)
                geometry_path = folder / "geometry.png"
                size_path = folder / "size-guide-cm.png"
                folder.mkdir(parents=True, exist_ok=True)
                self._callback(log, f"Product {index}/{total}: {url}")
                self._callback(
                    progress,
                    OrbeaTableProgress(
                        current=index - 1,
                        total=total,
                        status="opening_page",
                        message=f"Opening product {index}/{total}",
                        succeeded=len(files),
                        failed=len(failures),
                    ),
                )
                result = capture_orbea_tables(
                    driver,
                    url,
                    geometry_path,
                    size_path,
                    need_geometry=download_geometry,
                    need_size_guide=download_size_guide,
                    geometry_position="low",
                    timeouts=CaptureTimeouts(),
                )
                product_files: list[Path] = []
                variants = (
                    tuple(result.get("geometry_variants", []) or [])
                    if download_geometry
                    else ()
                )
                if download_geometry and variants:
                    product_files.extend(
                        folder / str(variant.get("filename"))
                        for variant in variants
                        if variant.get("status") == TABLE_STATUS_DOWNLOADED
                        and variant.get("filename")
                    )
                elif (
                    download_geometry
                    and result.get("geometry_status") == TABLE_STATUS_DOWNLOADED
                ):
                    product_files.append(geometry_path)
                if (
                    download_size_guide
                    and result.get("size_guide_status") == TABLE_STATUS_DOWNLOADED
                ):
                    product_files.append(size_path)

                errors = [str(item) for item in result.get("errors", []) if item]
                if errors:
                    failures.extend(f"{url}: {item}" for item in errors)
                selected_tables = []
                if download_geometry:
                    selected_tables.append(("geometry", "geometry_status"))
                if download_size_guide:
                    selected_tables.append(("size guide", "size_guide_status"))
                for label, key in selected_tables:
                    if result.get(key) == TABLE_STATUS_NOT_AVAILABLE:
                        unavailable.append(f"{url}: {label} is not available")

                current_photo_files: tuple[Path, ...] = ()
                current_photo_variants = 0
                current_photo_views = 0
                if download_product_photos and not self._cancelled(cancellation):
                    try:
                        if self._photo_service is None:
                            self._photo_service = self._create_photo_service()

                        def photo_progress(update) -> None:
                            message = str(getattr(update, "message", "") or "")
                            self._callback(
                                progress,
                                OrbeaTableProgress(
                                    current=index - 1,
                                    total=total,
                                    status="product_photos",
                                    message=(
                                        f"Product {index}/{total} • {message}"
                                        if message
                                        else f"Product {index}/{total} • product photos"
                                    ),
                                    succeeded=len(files),
                                    failed=len(failures),
                                ),
                            )

                        photo_result = self._photo_service.run_from_html(
                            url,
                            str(getattr(driver, "page_source", "") or ""),
                            folder,
                            product_folder="product-photos",
                            progress=photo_progress,
                            log=log,
                            cancellation=cancellation,
                        )
                        current_photo_files = tuple(photo_result.files)
                        current_photo_variants = int(photo_result.variants)
                        current_photo_views = int(photo_result.views)
                        for item in tuple(
                            getattr(photo_result, "failures", ()) or ()
                        ):
                            detail = f"product photos: {item}"
                            errors.append(detail)
                            failures.append(f"{url}: {detail}")
                        for item in tuple(
                            getattr(photo_result, "unavailable", ()) or ()
                        ):
                            unavailable.append(
                                f"{url}: product photo is not available: {item}"
                            )
                        product_files.extend(current_photo_files)
                        photo_files.extend(current_photo_files)
                        photo_variants += current_photo_variants
                        photo_views += current_photo_views
                    except Exception as error:
                        detail = f"product photos: {type(error).__name__}: {error}"
                        errors.append(detail)
                        failure = f"{url}: {detail}"
                        failures.append(failure)
                        self._callback(log, f"Failed {failure}")

                product = OrbeaTableProductResult(
                    url=url,
                    folder=folder,
                    geometry_status=(
                        str(result.get("geometry_status", "pending"))
                        if download_geometry
                        else "not_selected"
                    ),
                    size_guide_status=(
                        str(result.get("size_guide_status", "pending"))
                        if download_size_guide
                        else "not_selected"
                    ),
                    geometry_variants=variants,
                    files=tuple(product_files),
                    errors=tuple(errors),
                    photo_files=current_photo_files,
                    photo_variants=current_photo_variants,
                    photo_views=current_photo_views,
                )
                products.append(product)
                files.extend(product_files)
                self._callback(
                    log,
                    f"Saved {len(product_files)} image(s) in {folder.name}",
                )
                self._callback(
                    progress,
                    OrbeaTableProgress(
                        current=index,
                        total=total,
                        status="saved" if not errors else "partial",
                        message=f"Product {index}/{total} • {len(product_files)} images saved",
                        succeeded=len(files),
                        failed=len(failures),
                    ),
                )
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass

        cancelled = self._cancelled(cancellation)
        self._write_manifest(
            manifest_path,
            requested=len(raw_urls),
            duplicates=len(duplicates),
            products=products,
            cancelled=cancelled,
        )
        if not files and not unavailable and not cancelled:
            detail = failures[0] if failures else "No selected Orbea images were available"
            raise RuntimeError(f"No Orbea images could be saved. {detail}")
        return OrbeaTableBatchResult(
            output_dir=output_root,
            manifest_path=manifest_path,
            product_results=tuple(products),
            requested=len(raw_urls),
            products=len(products),
            duplicates=len(duplicates),
            files=tuple(files),
            failures=tuple(failures),
            unavailable=tuple(unavailable),
            cancelled=cancelled,
            photo_files=tuple(photo_files),
            photo_variants=photo_variants,
            photo_views=photo_views,
        )

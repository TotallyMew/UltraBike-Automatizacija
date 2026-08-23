from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class FilterOption:
    """One live Pimbo select option, retaining its opaque backend value."""

    value: str
    label: str
    group: str = ""


@dataclass(frozen=True)
class PimboFilterOptions:
    statuses: tuple[FilterOption, ...] = ()
    families: tuple[FilterOption, ...] = ()
    categories: tuple[FilterOption, ...] = ()
    sources: tuple[FilterOption, ...] = ()
    stock: tuple[FilterOption, ...] = ()
    completeness_locales: tuple[FilterOption, ...] = ()
    completeness_buckets: tuple[FilterOption, ...] = ()
    sort: tuple[FilterOption, ...] = ()


@dataclass(frozen=True)
class PimboFilterSpec:
    """The Pimbo filters exposed by the Orbea tab.

    The search term and Brand control intentionally are not configurable. The
    service always searches for ``orbea`` and resets Brand to ``All brands``.
    Select values are the opaque values discovered from Pimbo, not labels.
    """

    statuses: tuple[str, ...] = ("Draft",)
    family_id: str = ""
    category_id: str = ""
    source_id: str = ""
    stock: str = "In stock"
    completeness_locale: str = "Overall"
    completeness_buckets: tuple[str, ...] = ()
    sort: str = "Recent"

    def __post_init__(self) -> None:
        statuses = tuple(
            dict.fromkeys(str(item).strip() for item in self.statuses if str(item).strip())
        )
        buckets = tuple(
            dict.fromkeys(
                str(item).strip()
                for item in self.completeness_buckets
                if str(item).strip()
            )
        )
        object.__setattr__(self, "statuses", statuses)
        object.__setattr__(self, "completeness_buckets", buckets)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["statuses"] = list(self.statuses)
        data["completeness_buckets"] = list(self.completeness_buckets)
        return data


@dataclass(frozen=True)
class OrbeaRunConfig:
    catalogue_path: Path
    output_root: Path
    filters: PimboFilterSpec = field(default_factory=PimboFilterSpec)
    all_products: bool = True
    download_images: bool = True
    download_product_photos: bool = False
    browser_name: str = "chrome"
    max_products: int | None = None
    navigation_timeout: float = 25.0
    control_discovery_timeout: float = 3.0
    table_render_timeout: float = 8.0
    selector_timeout: float = 5.0
    image_retry_limit: int = 1
    search: str = field(default="orbea", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "catalogue_path", Path(self.catalogue_path).expanduser().resolve()
        )
        object.__setattr__(
            self, "output_root", Path(self.output_root).expanduser().resolve()
        )
        if self.max_products is not None and self.max_products < 1:
            raise ValueError("max_products must be positive when supplied")
        for name in (
            "navigation_timeout",
            "control_discovery_timeout",
            "table_render_timeout",
            "selector_timeout",
        ):
            if float(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.image_retry_limit < 0:
            raise ValueError("image_retry_limit cannot be negative")

    def compatibility_dict(self, catalogue_sha256: str) -> dict[str, Any]:
        """Return fields that must match before an unfinished run can resume."""

        return {
            "catalogue_path": str(self.catalogue_path),
            "catalogue_sha256": catalogue_sha256,
            "filters": self.filters.as_dict(),
            "search": self.search,
            "all_products": self.all_products,
            "download_images": self.download_images,
            "download_product_photos": self.download_product_photos,
        }


@dataclass(frozen=True)
class RunProgress:
    stage: str
    current: int
    total: int | None
    message: str = ""
    counts: Mapping[str, int] = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    eta_seconds: float | None = None


@dataclass(frozen=True)
class OrbeaRunResult:
    run_dir: Path
    workbook_path: Path
    checkpoint_path: Path
    manifest_path: Path
    completed: bool
    cancelled: bool
    resumed: bool
    counts: Mapping[str, int] = field(default_factory=dict)


class CancellationToken:
    """Small adapter accepted by both Qt workers and command-line callers."""

    def __init__(self, event: threading.Event | None = None) -> None:
        self._event = event or threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def is_set(self) -> bool:
        return self._event.is_set()

    @property
    def event(self) -> threading.Event:
        return self._event


class RunCancelled(RuntimeError):
    """Internal control-flow exception used to produce a partial report."""

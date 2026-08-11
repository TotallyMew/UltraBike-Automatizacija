"""Reusable Orbea automation services for the UltraBike desktop app."""

from .catalogue import (
    CatalogueEntry,
    CatalogueIndex,
    MatchResult,
    extract_template_codes,
    normalize_code,
    select_representative_variant,
)
from .checkpoint import (
    RunCheckpoint,
    create_run_directory,
    find_latest_compatible_run,
)
from .descriptions import (
    DescriptionProgress,
    DescriptionRunConfig,
    DescriptionRunResult,
    OrbeaDescriptionService,
    run_description_extraction,
)
from .models import (
    CancellationToken,
    FilterOption,
    OrbeaRunConfig,
    OrbeaRunResult,
    PimboFilterOptions,
    PimboFilterSpec,
    RunCancelled,
    RunProgress,
)
from .service import OrbeaAutomationService, run_pipeline

__all__ = [
    "CancellationToken",
    "CatalogueEntry",
    "CatalogueIndex",
    "DescriptionProgress",
    "DescriptionRunConfig",
    "DescriptionRunResult",
    "FilterOption",
    "MatchResult",
    "OrbeaAutomationService",
    "OrbeaDescriptionService",
    "OrbeaRunConfig",
    "OrbeaRunResult",
    "PimboFilterOptions",
    "PimboFilterSpec",
    "RunCancelled",
    "RunCheckpoint",
    "RunProgress",
    "create_run_directory",
    "extract_template_codes",
    "find_latest_compatible_run",
    "normalize_code",
    "run_pipeline",
    "run_description_extraction",
    "select_representative_variant",
]

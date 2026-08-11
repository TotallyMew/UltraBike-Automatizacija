"""Reusable Orbea model-description extraction for the desktop application.

The service deliberately creates a separate Selenium browser.  It never
accepts or closes the authenticated Pimbo driver owned by the main window.
Successful pages are flushed to UTF-8-with-BOM text files after every URL so
that a cancelled or partially failed run still leaves useful Notepad output.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from tools.orbea_description_extractor import (
    DescriptionDocument,
    create_driver,
    extract_description,
    normalize_orbea_url,
    unique_preserving_order,
    write_documents,
)

from .models import CancellationToken


@dataclass(frozen=True)
class DescriptionRunConfig:
    """Inputs for one independent description-extraction run."""

    urls: tuple[str, ...]
    output_dir: Path
    browser_name: str = "chrome"
    show_browser: bool = False

    def __post_init__(self) -> None:
        normalized = unique_preserving_order(
            normalize_orbea_url(value) for value in self.urls
        )
        if not normalized:
            raise ValueError("At least one Orbea model URL is required")
        browser_name = str(self.browser_name or "").strip().lower()
        if browser_name not in {"chrome", "edge", "firefox"}:
            raise ValueError(f"Unsupported browser: {self.browser_name}")
        object.__setattr__(self, "urls", tuple(normalized))
        object.__setattr__(
            self, "output_dir", Path(self.output_dir).expanduser().resolve()
        )
        object.__setattr__(self, "browser_name", browser_name)


@dataclass(frozen=True)
class DescriptionProgress:
    """A small UI-neutral progress event emitted before and after each URL."""

    current: int
    total: int
    url: str
    status: str
    message: str = ""
    succeeded: int = 0
    failed: int = 0


@dataclass(frozen=True)
class DescriptionRunResult:
    output_dir: Path
    files: tuple[Path, ...]
    succeeded: int
    failures: tuple[str, ...]
    cancelled: bool


ProgressCallback = Callable[[DescriptionProgress], None]
LogCallback = Callable[[str], None]
BrowserFactory = Callable[..., Any]


class OrbeaDescriptionService:
    """Extract all visible and expanded copy from Orbea ``/m/`` pages.

    A browser supplied by ``browser_factory`` is considered created for and
    owned by this service, just like the default browser.  It is always closed
    after the run and may be closed early by :meth:`cancel`.
    """

    def __init__(self, browser_factory: BrowserFactory | None = None) -> None:
        self.browser_factory = browser_factory
        self._cancellation = CancellationToken()
        self._driver: Any = None

    @staticmethod
    def _callback(callback: Callable[[Any], None] | None, value: Any) -> None:
        if callback is None:
            return
        try:
            callback(value)
        except Exception:
            # A view callback must not turn a completed extraction into a
            # failed run or prevent the partial output snapshot from saving.
            pass

    @staticmethod
    def _is_cancelled(token: Any) -> bool:
        if token is None:
            return False
        if hasattr(token, "is_cancelled"):
            return bool(token.is_cancelled())
        if hasattr(token, "is_set"):
            return bool(token.is_set())
        return False

    def _cancelled(self, external_token: Any) -> bool:
        return self._cancellation.is_cancelled() or self._is_cancelled(
            external_token
        )

    def cancel(self) -> None:
        """Request cancellation and interrupt only the owned browser."""

        self._cancellation.cancel()
        driver, self._driver = self._driver, None
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    def _new_driver(self, config: DescriptionRunConfig) -> Any:
        if self.browser_factory is None:
            return create_driver(config.browser_name, config.show_browser)
        try:
            return self.browser_factory(config.browser_name, config.show_browser)
        except TypeError:
            try:
                return self.browser_factory(config.browser_name)
            except TypeError:
                return self.browser_factory()

    @staticmethod
    def _write_failures(output_dir: Path, failures: Iterable[str]) -> Path:
        destination = output_dir / "description_errors.txt"
        destination.write_text(
            "ORBEA DESCRIPTION EXTRACTION ERRORS\n\n"
            + "\n".join(f"- {failure}" for failure in failures)
            + "\n",
            encoding="utf-8-sig",
        )
        return destination

    @staticmethod
    def _write_status(
        output_dir: Path,
        *,
        requested: int,
        succeeded: int,
        failures: int,
        cancelled: bool,
    ) -> Path:
        destination = output_dir / "description_run_status.txt"
        status = "Cancelled" if cancelled else "Completed"
        destination.write_text(
            "ORBEA DESCRIPTION EXTRACTION STATUS\n\n"
            f"Status: {status}\n"
            f"Requested URLs: {requested}\n"
            f"Descriptions saved: {succeeded}\n"
            f"Failures: {failures}\n",
            encoding="utf-8-sig",
        )
        return destination

    def run(
        self,
        config: DescriptionRunConfig,
        *,
        progress: ProgressCallback | None = None,
        log: LogCallback | None = None,
        cancellation: Any = None,
    ) -> DescriptionRunResult:
        """Run the extraction and return normally for per-page/browser errors."""

        # A service instance can be used for another run after a prior stop.
        self._cancellation = CancellationToken()
        config.output_dir.mkdir(parents=True, exist_ok=True)
        # A clean run must not leave a previous run's fixed-name error report
        # looking current after every URL succeeds.
        stale_error_report = config.output_dir / "description_errors.txt"
        if stale_error_report.is_file():
            stale_error_report.unlink()
        documents: list[DescriptionDocument] = []
        failures: list[str] = []
        files: list[Path] = []
        cancelled = self._cancelled(cancellation)

        if not cancelled:
            try:
                self._driver = self._new_driver(config)
            except Exception as error:
                failures.append(
                    f"Browser startup: {type(error).__name__}: {error}"
                )

        try:
            if self._driver is not None:
                for index, url in enumerate(config.urls, start=1):
                    if self._cancelled(cancellation):
                        cancelled = True
                        break
                    self._callback(
                        progress,
                        DescriptionProgress(
                            current=index - 1,
                            total=len(config.urls),
                            url=url,
                            status="extracting",
                            message=f"Extracting {index} of {len(config.urls)}",
                            succeeded=len(documents),
                            failed=len(failures),
                        ),
                    )
                    self._callback(log, f"Description {index}/{len(config.urls)}: {url}")
                    try:
                        document = extract_description(self._driver, url)
                    except Exception as error:
                        if self._cancelled(cancellation):
                            cancelled = True
                            break
                        message = f"{url}: {type(error).__name__}: {error}"
                        failures.append(message)
                        self._callback(log, f"Description failed: {message}")
                        event_status = "failed"
                        event_message = message
                    else:
                        documents.append(document)
                        # Flush the whole successful set each time.  This also
                        # keeps the combined document valid if Stop is pressed.
                        files = write_documents(documents, config.output_dir)
                        event_status = "saved"
                        event_message = f"Saved {document.model}"
                    self._callback(
                        progress,
                        DescriptionProgress(
                            current=index,
                            total=len(config.urls),
                            url=url,
                            status=event_status,
                            message=event_message,
                            succeeded=len(documents),
                            failed=len(failures),
                        ),
                    )
        finally:
            driver, self._driver = self._driver, None
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass

        cancelled = cancelled or self._cancelled(cancellation)
        if documents:
            # Ensure the final successful snapshot exists after any error or
            # cancellation that occurred after the last progress event.
            files = write_documents(documents, config.output_dir)
        if failures:
            files.append(self._write_failures(config.output_dir, failures))
        files.append(
            self._write_status(
                config.output_dir,
                requested=len(config.urls),
                succeeded=len(documents),
                failures=len(failures),
                cancelled=cancelled,
            )
        )

        return DescriptionRunResult(
            output_dir=config.output_dir,
            files=tuple(files),
            succeeded=len(documents),
            failures=tuple(failures),
            cancelled=cancelled,
        )


def run_description_extraction(
    config: DescriptionRunConfig,
    *,
    browser_factory: BrowserFactory | None = None,
    progress: ProgressCallback | None = None,
    log: LogCallback | None = None,
    cancellation: Any = None,
) -> DescriptionRunResult:
    """Convenience wrapper for callers that do not need a service instance."""

    return OrbeaDescriptionService(browser_factory=browser_factory).run(
        config,
        progress=progress,
        log=log,
        cancellation=cancellation,
    )

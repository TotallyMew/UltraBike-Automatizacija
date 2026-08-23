"""Orbea model adaptation and workflow service construction."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Mapping

def _read(obj: Any, *names: str, default: Any = None) -> Any:
    """Read the first available mapping key or object attribute."""
    for name in names:
        if isinstance(obj, Mapping) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def _plain(value: Any) -> Any:
    if hasattr(value, "value"):
        value = value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return list(value)
    return value


def _create_model(model_type, values: dict[str, Any], aliases: dict[str, str]):
    """Construct a typed service model while tolerating API-compatible aliases."""
    parameters = inspect.signature(model_type).parameters
    kwargs: dict[str, Any] = {}
    for name, parameter in parameters.items():
        if name in ("self", "args", "kwargs"):
            continue
        canonical = aliases.get(name, name)
        if canonical in values:
            kwargs[name] = values[canonical]
        elif parameter.default is inspect.Parameter.empty:
            raise TypeError(f"{model_type.__name__} requires unsupported field '{name}'")
    return model_type(**kwargs)


def _service_factory(
    driver, image_driver_factory=None, photo_service_factory=None
):
    # Local import keeps the rest of the app importable in a partially-updated
    # installation and gives PyInstaller a normal Python module to collect.
    from tools.orbea_automation import OrbeaAutomationService

    return OrbeaAutomationService(
        driver,
        image_driver_factory=image_driver_factory,
        photo_service_factory=photo_service_factory,
    )


class OrbeaWorkflowController:
    """Own service construction and the shared authenticated-browser lease."""

    def __init__(
        self,
        screen,
        *,
        service_factory=None,
        image_driver_factory=None,
        description_service_factory=None,
        photo_service_factory=None,
        table_image_service_factory=None,
    ):
        self.screen = screen
        self.main = screen.main
        self.service_factory = service_factory
        self.image_driver_factory = image_driver_factory
        self.description_service_factory = description_service_factory
        self.photo_service_factory = photo_service_factory
        self.table_image_service_factory = table_image_service_factory
        self.owns_browser_lease = False

    def make_service(self, driver):
        factory = self.service_factory
        if factory is None:
            return _service_factory(
                driver, self.image_driver_factory, self.make_photo_service
            )
        if hasattr(factory, "run") and hasattr(factory, "discover_filter_options"):
            return factory
        return factory(driver)

    def make_description_service(self):
        factory = self.description_service_factory
        if factory is None:
            from tools.orbea_automation import OrbeaDescriptionService

            return OrbeaDescriptionService()
        if not inspect.isclass(factory) and hasattr(factory, "run"):
            return factory
        return factory()

    def make_photo_service(self):
        factory = self.photo_service_factory
        if factory is None:
            from tools.orbea_automation import OrbeaPhotoService

            return OrbeaPhotoService()
        if not inspect.isclass(factory) and hasattr(factory, "run"):
            return factory
        return factory()

    def make_table_image_service(self):
        factory = self.table_image_service_factory
        if factory is None:
            from tools.orbea_automation import OrbeaTableImageService

            settings = getattr(self.screen, "settings", None)
            browser_name = "chrome"
            if settings is not None:
                try:
                    browser_name = str(
                        settings.get("browser_choice", "Chrome") or "Chrome"
                    ).strip().casefold()
                except Exception:
                    pass
            return OrbeaTableImageService(
                self.image_driver_factory,
                browser_name=browser_name,
                photo_service_factory=self.make_photo_service,
            )
        if not inspect.isclass(factory) and hasattr(factory, "run_many"):
            return factory
        return factory()

    def acquire_browser(self) -> bool:
        acquire = getattr(self.main, "try_acquire_browser_lease", None)
        if callable(acquire) and not acquire(self.screen):
            return False
        self.owns_browser_lease = True
        navigation = getattr(self.main, "navigationInterface", None)
        if navigation is not None:
            navigation.setEnabled(False)
        return True

    def release_browser(self) -> None:
        if not self.owns_browser_lease:
            return
        release = getattr(self.main, "release_browser_lease", None)
        if callable(release):
            try:
                release(self.screen)
            except Exception:
                pass
        self.owns_browser_lease = False
        navigation = getattr(self.main, "navigationInterface", None)
        if navigation is not None:
            navigation.setEnabled(True)

"""Navigation compatibility and worker ownership after retiring generic workflows."""
from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QWidget
from GUI_Qt.i18n import translate
from GUI_Qt.routes import ROUTE_REGISTRY, resolve_route_key
from GUI_Qt.screens.ProductLookupScreen import ProductLookupScreen
from GUI_Qt.screens.NameGetterScreen import NameGetterScreen
from GUI_Qt.screens.CodeGetterScreen import CodeGetterScreen
from GUI_Qt.screens.ProductNameGetterScreen import ProductNameGetterScreen


@pytest.mark.parametrize("route", ("name_getter", "code_getter", "product_name_getter"))
def test_old_lookup_links_open_the_combined_screen(route):
    assert resolve_route_key(route) == "product_lookup"


class _Signal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self):
        for callback in self.callbacks:
            callback()


class _Worker:
    def __init__(self):
        self.running = True
        self.finished = _Signal()
        self.stop_requested = False
        self.wait_succeeds = True

    def isRunning(self):
        return self.running

    def request_stop(self):
        self.stop_requested = True

    def wait(self, timeout):
        if self.wait_succeeds:
            self.complete()
        return self.wait_succeeds

    def complete(self):
        self.running = False
        self.finished.emit()


@pytest.fixture
def lookup():
    app = QApplication.instance() or QApplication([])
    main = QWidget()
    main.i18n = SimpleNamespace(tr=lambda key, **values: translate("en", key, **values))
    main.settings = SimpleNamespace(get=lambda key, default=None: default)
    main.driver = None
    main.owner = None
    main.browser_lease_owner = lambda: main.owner

    def acquire(owner):
        if main.owner not in (None, owner):
            return False
        main.owner = owner
        return True

    def release(owner):
        if main.owner is owner:
            main.owner = None

    main.try_acquire_browser_lease = acquire
    main.release_browser_lease = release
    screen = ProductLookupScreen(main)
    yield screen
    assert screen.shutdown()
    screen.deleteLater()
    main.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


@pytest.mark.parametrize("index,base", (
    (0, NameGetterScreen), (1, CodeGetterScreen), (2, ProductNameGetterScreen),
))
def test_each_lookup_mode_locks_navigation_until_its_worker_finishes(lookup, monkeypatch, index, base):
    worker = _Worker()
    monkeypatch.setattr(base, "_on_start_stop", lambda panel: setattr(panel, "_worker", worker))
    lookup.panels[index]._on_start_stop()
    assert lookup.main.owner is lookup
    assert not lookup.request_navigation_away()
    assert not lookup.tabs.tabBar().isEnabled()
    worker.complete()
    assert lookup.main.owner is None
    assert lookup.request_navigation_away()
    assert lookup.tabs.tabBar().isEnabled()


def test_lookup_does_not_start_when_another_workflow_owns_the_browser(lookup, monkeypatch):
    calls = []
    monkeypatch.setattr(CodeGetterScreen, "_on_start_stop", lambda panel: calls.append(panel))
    monkeypatch.setattr("GUI_Qt.screens.ProductLookupScreen.InfoBar.warning", lambda **kwargs: None)
    other_owner = object()
    lookup.main.owner = other_owner
    lookup.panels[1]._on_start_stop()
    assert not calls
    assert lookup.main.owner is other_owner


def test_lookup_shutdown_keeps_ownership_until_worker_stops(lookup, monkeypatch):
    worker = _Worker()
    monkeypatch.setattr(CodeGetterScreen, "_on_start_stop", lambda panel: setattr(panel, "_worker", worker))
    lookup.panels[1]._on_start_stop()
    worker.wait_succeeds = False
    assert not lookup.shutdown(wait_ms=1)
    assert worker.stop_requested
    assert lookup.main.owner is lookup
    assert not lookup.request_navigation_away()
    worker.wait_succeeds = True
    assert lookup.shutdown(wait_ms=1)
    assert lookup.main.owner is None


def test_current_history_route_uses_detailed_records():
    assert "history" in ROUTE_REGISTRY
    assert all(route not in ROUTE_REGISTRY for route in ("upload", "batch", "descriptions", "folders"))

def test_lookup_modes_cannot_overlap_even_if_invoked_programmatically(lookup, monkeypatch):
    first_worker = _Worker()
    second_calls = []
    monkeypatch.setattr(NameGetterScreen, "_on_start_stop",
                        lambda panel: setattr(panel, "_worker", first_worker))
    monkeypatch.setattr(CodeGetterScreen, "_on_start_stop", lambda panel: second_calls.append(panel))
    monkeypatch.setattr("GUI_Qt.screens.ProductLookupScreen.InfoBar.warning", lambda **kwargs: None)
    lookup.panels[0]._on_start_stop()
    lookup.panels[1]._on_start_stop()
    assert not second_calls
    assert lookup._active_worker is first_worker
    first_worker.complete()

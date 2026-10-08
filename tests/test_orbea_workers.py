"""Contracts for Orbea service construction and cancellation handshakes."""

from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from GUI_Qt.orbea.controller import OrbeaWorkflowController
from GUI_Qt.orbea.workers import (
    OrbeaDescriptionWorker, OrbeaFilterWorker, OrbeaPhotoWorker,
    OrbeaRunWorker, OrbeaTableImageWorker,
)


def make_worker(kind, factory, tmp_path):
    if kind == "collection":
        return OrbeaRunWorker(None, lambda _: factory(), object(), resume=False, retry_failed=False)
    if kind == "description":
        return OrbeaDescriptionWorker(factory, object())
    if kind == "photos":
        return OrbeaPhotoWorker(factory, ("https://www.orbea.com/en-be/orca",), tmp_path)
    return OrbeaTableImageWorker(factory, ("https://www.orbea.com/en-be/orca",), tmp_path)


KINDS = ("collection", "description", "photos", "tables")


@pytest.mark.parametrize("kind", KINDS)
def test_stop_before_start_preserves_the_same_token_even_if_cleanup_raises(kind, tmp_path):
    seen = []
    def run(*args, cancellation, **kwargs):
        seen.append(cancellation)
        return SimpleNamespace(cancelled=cancellation.is_cancelled())
    service = SimpleNamespace(run=run, run_many=run, cancel=Mock(side_effect=RuntimeError("cleanup failed")))
    worker = make_worker(kind, lambda: service, tmp_path)
    original_token = worker._token
    results, errors = [], []
    worker.succeeded.connect(results.append)
    worker.failed.connect(errors.append)
    worker.request_stop()
    worker.run()
    assert seen == [original_token]
    assert original_token.is_cancelled() and worker.stop_requested
    service.cancel.assert_called_once()
    assert len(results) == 1 and results[0].cancelled
    assert not errors


@pytest.mark.parametrize("kind", KINDS)
def test_stop_during_factory_construction_reaches_the_service_once(kind, tmp_path):
    entered, release = Event(), Event()
    tokens = []
    def run(*args, cancellation, **kwargs):
        tokens.append(cancellation.is_cancelled())
    service = SimpleNamespace(run=run, run_many=run, cancel=Mock())
    def factory():
        entered.set()
        assert release.wait(3)
        return service
    worker = make_worker(kind, factory, tmp_path)
    thread = Thread(target=worker.run)
    thread.start()
    try:
        assert entered.wait(3)
        worker.request_stop()
        worker.request_stop()
    finally:
        release.set()
        thread.join(3)
    assert not thread.is_alive()
    assert tokens == [True]
    service.cancel.assert_called_once()


@pytest.mark.parametrize("kind", KINDS)
def test_repeated_stop_after_construction_keeps_completed_results(kind, tmp_path):
    def run(*args, cancellation, **kwargs):
        worker.request_stop()
        worker.request_stop()
        assert cancellation.is_cancelled()
        return {"cancelled": True, "files": ("already-saved",)}
    service = SimpleNamespace(run=run, run_many=run, cancel=Mock())
    worker = make_worker(kind, lambda: service, tmp_path)
    results = []
    worker.succeeded.connect(results.append)
    worker.run()
    service.cancel.assert_called_once()
    assert results == [{"cancelled": True, "files": ("already-saved",)}]


def test_filter_stop_before_start_does_not_construct_a_service():
    factory = Mock()
    worker = OrbeaFilterWorker(None, factory)
    worker.request_stop()
    worker.run()
    factory.assert_not_called()


def test_filter_stop_during_construction_cancels_without_discovery():
    service = SimpleNamespace(discover_filter_options=Mock(), cancel=Mock())
    def factory(_):
        worker.request_stop()
        return service
    worker = OrbeaFilterWorker(None, factory)
    worker.run()
    service.cancel.assert_called_once()
    service.discover_filter_options.assert_not_called()


@pytest.mark.parametrize("factory_kind", ("class", "function", "instance"))
def test_collection_factory_constructs_classes_and_retains_instances(factory_kind):
    class Service:
        def __init__(self, driver):
            self.driver = driver
        def run(self):
            pass
        def discover_filter_options(self):
            pass
    driver = object()
    instance = Service(driver)
    factory = {"class": Service, "function": lambda value: Service(value), "instance": instance}[factory_kind]
    controller = OrbeaWorkflowController(SimpleNamespace(main=object()), service_factory=factory)
    actual = controller.make_service(driver)
    assert isinstance(actual, Service) and actual.driver is driver
    if factory_kind == "instance":
        assert actual is instance


@pytest.mark.parametrize("method,factory_kw,operation", (
    ("make_description_service", "description_service_factory", "run"),
    ("make_photo_service", "photo_service_factory", "run_many"),
    ("make_table_image_service", "table_image_service_factory", "run_many"),
))
def test_direct_factories_support_service_classes_and_instances(method, factory_kw, operation):
    Service = type("Service", (), {operation: lambda self: None})
    instance = Service()
    screen = SimpleNamespace(main=object())
    constructed = getattr(OrbeaWorkflowController(screen, **{factory_kw: Service}), method)()
    assert isinstance(constructed, Service)
    actual = getattr(OrbeaWorkflowController(screen, **{factory_kw: instance}), method)()
    assert actual is instance

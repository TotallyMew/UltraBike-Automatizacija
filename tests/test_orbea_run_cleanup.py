"""Run cleanup must preserve partial reports and allow the next Orbea job."""

import json
from types import SimpleNamespace

import pytest

from tools.orbea_automation.models import OrbeaRunConfig, OrbeaRunFailure
from tools.orbea_automation.service import OrbeaAutomationService, PIMBO_AUTOMATION_LOCK


def empty_scan(client, catalogue, checkpoint, config, **kwargs):
    checkpoint.data["scan_completed"] = True
    checkpoint.save()


def make_service(*, close_error=False):
    def close():
        if close_error:
            raise RuntimeError("browser cleanup failed")
    website = SimpleNamespace(close=close)
    return OrbeaAutomationService(object(), website_client_factory=lambda *_: website)


def test_cleanup_error_keeps_partial_report_and_releases_the_run_lock(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.orbea_automation.service.PimboBrowserClient.collect", empty_scan)
    broken = make_service(close_error=True)
    config = OrbeaRunConfig(None, tmp_path, download_images=False)
    with pytest.raises(OrbeaRunFailure, match="browser cleanup failed") as raised:
        broken.run(config, resume=False)
    partial = raised.value.partial_result
    assert partial.workbook_path.is_file() and partial.manifest_path.is_file()
    assert not partial.completed
    assert not PIMBO_AUTOMATION_LOCK.locked()
    assert broken._website_client is None
    assert "browser cleanup failed" in json.loads(partial.checkpoint_path.read_text())["last_error"]
    assert make_service().run(config, resume=False).completed


def test_cleanup_error_does_not_replace_the_original_failure(tmp_path, monkeypatch):
    def fail_scan(*args, **kwargs):
        raise ValueError("original product scan failure")
    monkeypatch.setattr("tools.orbea_automation.service.PimboBrowserClient.collect", fail_scan)
    config = OrbeaRunConfig(None, tmp_path, download_images=False)
    with pytest.raises(OrbeaRunFailure, match="original product scan failure") as raised:
        make_service(close_error=True).run(config, resume=False)
    assert isinstance(raised.value.__cause__, ValueError)
    assert not PIMBO_AUTOMATION_LOCK.locked()
    assert raised.value.partial_result.workbook_path.is_file()


def test_final_report_error_does_not_leave_a_completed_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.orbea_automation.service.PimboBrowserClient.collect", empty_scan)
    from tools.orbea_automation import service as module
    actual = module.write_report
    calls = []
    def report(checkpoint):
        calls.append(None)
        if len(calls) == 2:
            raise OSError("final report unavailable")
        return actual(checkpoint)
    monkeypatch.setattr(module, "write_report", report)
    config = OrbeaRunConfig(None, tmp_path, download_images=False)
    with pytest.raises(OrbeaRunFailure, match="final report unavailable") as raised:
        make_service().run(config, resume=False)
    partial = raised.value.partial_result
    assert not partial.completed and partial.workbook_path.is_file()
    assert not json.loads(partial.checkpoint_path.read_text())["completed"]
    assert not PIMBO_AUTOMATION_LOCK.locked()


@pytest.mark.parametrize("accepts_browser", (False, True))
def test_browser_factories_support_both_call_signatures(tmp_path, accepts_browser):
    calls, driver = [], object()
    def named(browser):
        calls.append(browser)
        return driver
    def unnamed():
        calls.append(None)
        return driver
    service = OrbeaAutomationService(None, image_driver_factory=named if accepts_browser else unnamed)
    config = OrbeaRunConfig(None, tmp_path, browser_name="edge")
    assert service._new_image_driver(config) is driver
    assert calls == ["edge" if accepts_browser else None]


def test_internal_factory_type_error_is_preserved_without_retrying(tmp_path):
    calls = []
    def factory(browser="chrome"):
        calls.append(browser)
        raise TypeError("driver construction failed inside factory")
    service = OrbeaAutomationService(None, image_driver_factory=factory)
    config = OrbeaRunConfig(None, tmp_path, browser_name="edge")
    with pytest.raises(TypeError, match="inside factory"):
        service._new_image_driver(config)
    assert calls == ["edge"]

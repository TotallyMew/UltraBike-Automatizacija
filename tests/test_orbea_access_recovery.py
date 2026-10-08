from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from selenium.common.exceptions import TimeoutException

from tools.orbea_automation.models import CancellationToken, OrbeaRunConfig, OrbeaRunFailure, RunCancelled
from tools.orbea_automation.service import OrbeaAutomationService
from tools.orbea_automation.website import OrbeaAccessError, OrbeaWebsiteClient
from tools.orbea_table_image_downloader import capture_orbea_tables, create_driver


URL = "https://www.orbea.com/en-be/alma-carbon"
CHALLENGE = '<html><title>Just a moment...</title><h1>www.orbea.com</h1><p>Verify you are human</p></html>'
PRODUCT = '<main><h1>Alma Carbon</h1><div id="product-bike-detail" x-init="code = \'U907TTCC\';"></div></main>'
HOME = '<main><dialog id="zone-lang-show-all"><a href="https://www.orbea.com/en-be">English</a></dialog><form role="search"><input name="query"></form></main>'
RESULTS = '<main><form role="search"><input name="query"><div x-ref="searchScrollable"><a href="/en-be/alma-carbon"><span x-text="result.name">Alma Carbon</span><span x-text="result.model">U907TTCC</span></a></div><div x-show="waiting" style="display: none;"></div></form></main>'


class Browser:
    def __init__(self, pages, *, navigation_timeout=False, on_read=None):
        self.pages = iter(pages)
        self.last_page = CHALLENGE
        self.current_url = URL
        self.navigations = []
        self.navigation_timeout = navigation_timeout
        self.on_read = on_read

    def set_page_load_timeout(self, _timeout):
        pass

    def get(self, url):
        self.current_url = url
        self.navigations.append(url)
        if self.navigation_timeout:
            self.navigation_timeout = False
            raise TimeoutException("navigation is still verifying")

    @property
    def page_source(self):
        if self.on_read:
            self.on_read()
        self.last_page = next(self.pages, self.last_page)
        return self.last_page

    def find_elements(self, by, selector):
        if selector == 'form[role="search"] input[name="query"]':
            return [SimpleNamespace(is_displayed=lambda: True, clear=lambda: None, send_keys=lambda *_: None)]
        return [object()] if selector == "h1" and "Alma Carbon" in self.last_page else []


def client(browser, **kwargs):
    result = OrbeaWebsiteClient(lambda: browser, CancellationToken(), timeout=1, access_timeout=2, **kwargs)
    result.collect_description = result.collect_specifications = False
    return result


def test_verification_waits_through_blank_page_and_resumes_requested_product():
    browser = Browser([CHALLENGE, CHALLENGE, "<html></html>", PRODUCT, PRODUCT])
    website = client(browser)
    notifications = []
    website.access_progress = lambda waiting, message: notifications.append((waiting, message))
    product = website.fetch(URL)
    assert product.codes == ("U907TTCC",)
    assert browser.navigations == [URL]
    assert [waiting for waiting, _ in notifications] == [True, False]
    assert "automatically" in notifications[0][1]


def test_search_can_recover_verification_on_home_and_results():
    browser = Browser([CHALLENGE, HOME, CHALLENGE, RESULTS, RESULTS])
    website = client(browser)
    notifications = []
    website.access_progress = lambda waiting, _: notifications.append(waiting)
    assert website.lookup("U90709FJ").entry.product_link == URL
    assert browser.navigations == [website.HOME]
    assert notifications == [True, False, True, False]


def test_navigation_timeout_on_verification_waits_in_same_browser():
    browser = Browser([CHALLENGE, CHALLENGE, PRODUCT, PRODUCT], navigation_timeout=True)
    website = client(browser)
    assert website.fetch(URL).codes == ("U907TTCC",)
    assert browser.navigations == [URL]


def test_unresolved_check_times_out_with_correct_resume_label():
    browser = Browser([CHALLENGE])
    website = client(browser)
    website.access_timeout = 0
    with pytest.raises(OrbeaAccessError, match="Resume interrupted collection"):
        website.fetch(URL)
    assert browser.navigations == [URL]
    assert not website._products


def test_stop_cancels_verification_without_waiting_for_timeout():
    browser = Browser([CHALLENGE])
    website = client(browser)
    website.access_progress = lambda *_: website.cancellation.cancel()
    with pytest.raises(RunCancelled):
        website.fetch(URL)
    assert browser.navigations == [URL]


@pytest.mark.parametrize("browser_name,driver_name,manager", [
    ("chrome", "Chrome", "webdriver_manager.chrome.ChromeDriverManager"),
    ("edge", "Edge", "webdriver_manager.microsoft.EdgeChromiumDriverManager"),
    ("firefox", "Firefox", "webdriver_manager.firefox.GeckoDriverManager"),
])
def test_visible_browser_uses_same_dedicated_profile_across_runs(tmp_path, browser_name, driver_name, manager):
    config = OrbeaRunConfig(None, tmp_path, browser_name=browser_name)
    service = OrbeaAutomationService(object())
    with patch(f"selenium.webdriver.{driver_name}") as constructor, patch(f"{manager}.install", return_value="fixture-driver"):
        service._new_image_driver(config)
        profile = tmp_path / ".orbea-browser" / browser_name
        (profile / "existing-session").write_text("keep", encoding="utf-8")
        service._new_image_driver(config)
    assert (profile / "existing-session").read_text() == "keep"
    for call in constructor.call_args_list:
        arguments = call.kwargs["options"].arguments
        assert not any("headless" in argument for argument in arguments)
        if browser_name == "firefox":
            assert arguments[arguments.index("-profile") + 1] == str(profile)
        else:
            assert f"--user-data-dir={profile}" in arguments


def test_table_verification_error_leaves_controls_unclassified(tmp_path):
    def blocked():
        raise OrbeaAccessError("check still required")
    with patch("tools.orbea_table_image_downloader.discover_table_controls") as discover:
        with pytest.raises(OrbeaAccessError):
            capture_orbea_tables(MagicMock(), URL, tmp_path / "geometry.png", tmp_path / "sizes.png", after_navigation=blocked)
        discover.assert_not_called()


def test_worker_emits_saved_partial_then_website_blocked_without_failure(tmp_path):
    from GUI_Qt.orbea.workers import OrbeaRunWorker
    result = SimpleNamespace(workbook_path=tmp_path / "orbea_matches.xlsx")
    service = SimpleNamespace(run=MagicMock(side_effect=OrbeaRunFailure("verification required", result, reason="website_access")))
    worker = OrbeaRunWorker(object(), lambda _: service, object(), resume=True, retry_failed=False)
    events = []
    worker.partial_result.connect(lambda saved: events.append(("partial", saved)))
    worker.website_blocked.connect(lambda text: events.append(("blocked", text)))
    worker.failed.connect(lambda text: events.append(("failed", text)))
    worker.run()
    assert events == [("partial", result), ("blocked", "verification required")]


@pytest.mark.parametrize("stop", [False, True])
def test_service_saves_report_during_verification_and_can_continue_or_stop(tmp_path, stop):
    checkpoints, observations, progress = [], [], []
    token = CancellationToken()

    def scan(_client, _catalogue, checkpoint, _config, **_kwargs):
        checkpoints.append(checkpoint)
        checkpoint.upsert_result({"row_key": "alma", "product_id": "alma", "sku": "U90709FJ",
            "title": "Orbea ALMA CARBON Galactic Rainbow-Sunset C.View (Gloss)", "status": "code_match",
            "catalogue_url": URL, "catalogue_model": "ALMA CARBON", "page": 1, "row": 1})
        checkpoint.data["scan_completed"] = True
        checkpoint.save()

    def read():
        checkpoint = checkpoints[0]
        if checkpoint.data["phase"] == "website_access":
            observations.append(checkpoint.workbook_path.is_file())
            assert json.loads(checkpoint.path.read_text())["scan_completed"]
            if stop:
                token.cancel()

    browser = Browser([CHALLENGE, CHALLENGE if stop else HOME, RESULTS, RESULTS], on_read=read)
    website = client(browser)
    service = OrbeaAutomationService(object(), website_client_factory=lambda *_: website)
    config = OrbeaRunConfig(None, tmp_path, collect_product_data=True, download_images=False,
        download_product_photos=False, download_description=False, download_specifications=False)
    with patch("tools.orbea_automation.service.PimboBrowserClient.collect", scan):
        result = service.run(config, resume=False, cancellation=token, progress=progress.append)
    assert observations and all(observations)
    assert any(update.stage == "website_access" and "automatically" in update.message for update in progress)
    assert result.cancelled == stop and result.completed != stop
    assert result.workbook_path.is_file() and result.counts["scanned"] == 1
    assert browser.navigations == [website.HOME]

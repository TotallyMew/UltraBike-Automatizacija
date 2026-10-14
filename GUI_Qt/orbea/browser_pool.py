"""Owned Pimbo browsers and a small queue with one thread per browser."""
from __future__ import annotations

import inspect
import threading
from pathlib import Path

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CaptionLabel, ComboBox


class BrowserCountControl(QWidget):
    def __init__(self, screen, parent=None, *, downloads=False):
        super().__init__(parent)
        self.screen = screen
        self.downloads = downloads
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)
        row = QHBoxLayout()
        self.label = BodyLabel(self)
        self.combo = ComboBox(self)
        for count in range(1, 5):
            self.combo.addItem(str(count), userData=count)
        self.combo.setMinimumHeight(38)
        self.combo.setFixedWidth(80)
        try:
            count = max(1, min(4, int(screen._setting_get("orbea_browser_count", 1))))
        except (TypeError, ValueError):
            count = 1
        self.combo.setCurrentIndex(count - 1)
        row.addWidget(self.label)
        row.addWidget(self.combo)
        row.addStretch()
        box.addLayout(row)
        self.hint = CaptionLabel(self)
        self.hint.setWordWrap(True)
        box.addWidget(self.hint)
        self.combo.currentIndexChanged.connect(self._changed)
        self.retranslate_ui()

    @property
    def count(self):
        return self.combo.currentData() or 1

    def _changed(self):
        self.screen._setting_set("orbea_browser_count", self.count)
        # All Orbea workflows share the setting without changing an active run.
        for panel_name in ("_upload_panel", "_model_copy_panel", "_source_panel"):
            other = getattr(getattr(self.screen, panel_name, None), "browsers", None)
            if other is not None and other is not self:
                blocked = other.combo.blockSignals(True)
                other.combo.setCurrentIndex(self.count - 1)
                other.combo.blockSignals(blocked)
                update = getattr(other.parent(), "update_state", None)
                if callable(update):
                    update()
        update = getattr(self.parent(), "update_state", None)
        if callable(update):
            update()
        else:
            self.screen._update_action_states()

    def retranslate_ui(self):
        if self.downloads:
            self.label.setText(self.screen._t("orbea.browsers.download_label", "Orbea download browsers"))
            self.hint.setText(self.screen._t("orbea.browsers.download_hint", "Download different model pages in parallel. Bikes sharing one page stay together; each bike's selected items are collected in one pass."))
        else:
            self.label.setText(self.screen._t("orbea.browsers.label", "Pimbo browsers"))
            self.hint.setText(self.screen._t("orbea.browsers.hint", "Uploads, source reading and copying use separate signed-in browsers. Stop finishes active products before closing extra browsers."))


class PimboBrowserPool:
    """Borrow the app browser; create and close only the additional sessions."""
    def __init__(self, main, count, *, log, stopped, manager_factory=None):
        self.main, self.count = main, count
        self.log, self.stopped = log, stopped
        self.manager_factory = manager_factory
        self.manager = None
        self.drivers = ()
        self._preserved = set()

    def __enter__(self):
        if self.main.driver is None:
            raise RuntimeError("Connect to Pimbo before starting the run")
        self.drivers = (self.main.driver,)
        if self.count <= 1 or self.stopped():
            return self
        from Managers.BrowserSessionManager import BrowserSessionManager
        from Config.LoginConfig.LoginHandler import LoginHandler
        from Managers.PimboProductEditor import PIMBO_LOGIN_URL

        credentials = getattr(self.main, "credential_manager", None)
        email, password = credentials.get_saved_credentials() if credentials else ("", "")
        if not email or not password:
            raise RuntimeError("Saved Pimbo sign-in is unavailable. Sign in again or choose 1 browser.")
        browser_type = str(self.main.settings.get("browser_choice", "Chrome") or "Chrome").capitalize()
        factory = self.manager_factory or BrowserSessionManager
        self.manager = factory(browser_type=browser_type, pool_size=self.count - 1,
                               logger=getattr(self.main, "logger", None))

        def initialize(driver):
            if self.stopped():
                return False
            self.log("Signing in an additional Pimbo browser…")
            driver.get(PIMBO_LOGIN_URL)
            handler = LoginHandler(driver, credentials, logger=getattr(self.main, "logger", None))
            return handler.attempt_login(email, password, cancel_callback=self.stopped)

        self.manager.set_session_initializer(initialize)
        try:
            if not self.manager.initialize_pool():
                if self.stopped():
                    return self
                raise RuntimeError("Could not open and sign in all requested Pimbo browsers. No parallel products were started.")
            self.drivers += tuple(session.driver for session in self.manager.sessions)
            self.log(f"Using {len(self.drivers)} Pimbo browsers")
            return self
        except BaseException:
            self.close()
            raise

    def preserve(self, driver):
        self._preserved.add(id(driver))
        self.log("An unsafe browser was left open for review; no further products will start.")

    def close(self):
        if self.manager is not None:
            for session in self.manager.sessions:
                if id(session.driver) in self._preserved:
                    session.driver = None  # Leave this window open for manual recovery.
            self.manager.shutdown_all()
            self.manager = None

    def __exit__(self, *_args):
        self.close()


def driver_service(factory, driver):
    """Bind one service per driver, retaining zero-argument factory compatibility."""
    try:
        inspect.signature(factory).bind(driver)
    except TypeError:
        service = factory()
        if hasattr(service, "pimbo_driver"):
            service.pimbo_driver = driver
    else:
        service = factory(driver)
    return service


class BrowserTaskQueue:
    def __init__(self, tasks, stopped):
        self.tasks = list(tasks)
        self.stopped = stopped
        self.fatal = threading.Event()
        self.lock = threading.Lock()
        self.index = 0
        self.errors = []

    def is_cancelled(self):
        return self.fatal.is_set() or self.stopped()

    def run(self, drivers, execute):
        def work(number, driver):
            while True:
                with self.lock:
                    if self.is_cancelled() or self.index >= len(self.tasks):
                        return
                    task = self.tasks[self.index]
                    self.index += 1
                try:
                    execute(number, driver, task)
                except Exception as error:
                    with self.lock:
                        self.errors.append(str(error))
                        self.fatal.set()
                    return

        threads = [threading.Thread(target=work, args=(index + 1, driver),
                                    name=f"Orbea-Pimbo-{index + 1}")
                   for index, driver in enumerate(drivers)]
        started = []
        try:
            for thread in threads:
                thread.start()
                started.append(thread)
        except Exception:
            self.fatal.set()
            raise
        finally:
            for thread in started:
                thread.join()


class ProductClaims:
    def __init__(self, initial=()):
        self.lock = threading.Lock()
        self.owners = {value: None for value in initial if value}

    def claim(self, product_id, owner):
        if not product_id:
            raise RuntimeError("A parallel product has no verified Pimbo ID")
        with self.lock:
            if product_id in self.owners:
                return self.owners[product_id] == owner
            self.owners[product_id] = owner
            return True


def upload_tasks(matches):
    """Keep overlapping Pimbo identities, SKU aliases and package files in one task."""
    from tools.supplier_upload import SupplierUploadWorkflow, normalize_sku
    parents = list(range(len(matches)))
    seen = {}

    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    for index, match in enumerate(matches):
        product_id = match.pimbo_product_id or SupplierUploadWorkflow._pimbo_product_id(match.pimbo_product_url)
        resources = [("sku", normalize_sku(match.sku))]
        if product_id:
            resources.append(("product", product_id))
        if match.local_folder:
            resources.append(("package", str(Path(match.local_folder).resolve()).casefold()))
        for resource in resources:
            if resource in seen:
                parents[root(index)] = root(seen[resource])
            else:
                seen[resource] = index
    groups = {}
    for index, match in enumerate(matches):
        groups.setdefault(root(index), []).append(match)
    return tuple(groups.items())

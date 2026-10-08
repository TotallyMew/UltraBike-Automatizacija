"""Product lookup and exports in one guarded workspace."""
from PySide6.QtWidgets import QTabWidget, QVBoxLayout
from qfluentwidgets import InfoBar

from GUI_Qt.screens.NameGetterScreen import NameGetterScreen
from GUI_Qt.screens.CodeGetterScreen import CodeGetterScreen
from GUI_Qt.screens.ProductNameGetterScreen import ProductNameGetterScreen
from GUI_Qt.services.product_work import acquire_product_browser, release_product_browser
from GUI_Qt.widgets.ResponsiveWidget import ResponsiveWidget


class _GuardedLookupPanel:
    def __init__(self, main_window, host):
        self.lookup_host = host
        super().__init__(main_window)

    def _on_start_stop(self):
        if self._worker is not None and self._worker.isRunning():
            return super()._on_start_stop()
        host = self.lookup_host
        if not acquire_product_browser(self.main, host, worker=host._active_worker):
            InfoBar.warning(title=self.tr("common.warning"),
                            content=self.tr("kross.browser.busy"), parent=host)
            return
        try:
            super()._on_start_stop()
        except Exception:
            release_product_browser(self.main, host)
            raise
        worker = self._worker
        if worker is None:
            release_product_browser(self.main, host)
            return
        host._active_worker = worker
        host.tabs.tabBar().setEnabled(False)
        worker.finished.connect(lambda: host._worker_finished(worker))
        if not worker.isRunning():
            host._worker_finished(worker)


class _NamesByCodePanel(_GuardedLookupPanel, NameGetterScreen):
    pass


class _CodesPanel(_GuardedLookupPanel, CodeGetterScreen):
    pass


class _NamesPanel(_GuardedLookupPanel, ProductNameGetterScreen):
    pass


class ProductLookupScreen(ResponsiveWidget):
    """Retain input-code lookup, ERP export and list-name export as three modes."""
    PANEL_TYPES = (_NamesByCodePanel, _CodesPanel, _NamesPanel)
    LABEL_KEYS = ("nav.name_getter", "nav.code_getter", "nav.product_name_getter")

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self._active_worker = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget(self)
        self.panels = tuple(panel_type(main_window, self) for panel_type in self.PANEL_TYPES)
        for panel in self.panels:
            self.tabs.addTab(panel, "")
        layout.addWidget(self.tabs)
        self.retranslate_ui()

    def _worker_finished(self, worker):
        if self._active_worker is not worker or worker.isRunning():
            return
        self._active_worker = None
        release_product_browser(self.main, self)
        self.tabs.tabBar().setEnabled(True)

    def request_navigation_away(self):
        return self._active_worker is None or not self._active_worker.isRunning()

    def shutdown(self, wait_ms=5000):
        worker = self._active_worker
        if worker is not None and worker.isRunning():
            worker.request_stop()
            if not worker.wait(wait_ms):
                return False
            self._worker_finished(worker)
        return True

    def retranslate_ui(self):
        for index, (panel, key) in enumerate(zip(self.panels, self.LABEL_KEYS)):
            self.tabs.setTabText(index, self.main.i18n.tr(key))
            panel.retranslate_ui()

"""Brand-specific tools grouped in guarded, tabbed workspaces."""
from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QVBoxLayout
from qfluentwidgets import TitleLabel, CaptionLabel, InfoBar
from GUI_Qt.widgets.ResponsiveWidget import ResponsiveWidget
from GUI_Qt.widgets.workspace import WorkspaceTabs
from GUI_Qt.widgets.workspace import bind_text, connect_signal
from GUI_Qt.styles.screen_theme import PAGE_MARGINS, PAGE_SPACING, apply_screen_theme
from GUI_Qt.layouts.tools import arrange_table_tool, arrange_image_tool


class _GuardedBrandPanel:
    def __init__(self, main, host):
        self.workspace_host = host
        super().__init__(main)

    def _launch(self, action):
        host = self.workspace_host
        if any(worker not in vars(self).values() for worker in host.iter_workers()):
            InfoBar.warning(title=self.main.i18n.tr("common.warning"),
                content=self.main.i18n.tr("kross.browser.busy"), parent=host)
            return
        result = action()
        host._update_tab_guard()
        for worker in host.iter_workers():
            worker.finished.connect(host._update_tab_guard)
        return result

    def _on_start_stop(self):
        return self._launch(super()._on_start_stop)

    def _run(self):
        return self._launch(super()._run)

    def _preview_variants(self):
        if any(self.workspace_host.iter_workers()):
            InfoBar.warning(title=self.main.i18n.tr("common.warning"),
                content=self.main.i18n.tr("kross.browser.busy"), parent=self.workspace_host)
            return
        return self._launch(super()._preview_variants)


class BrandToolsScreen(ResponsiveWidget):
    PANEL_TYPES = ()
    LABELS = ()
    TITLE_KEY = ""
    SUBTITLE_KEY = ""
    IMAGE_TOOLS = False

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*PAGE_MARGINS)
        layout.setSpacing(PAGE_SPACING)
        self.title = bind_text(TitleLabel(), self.main, self.TITLE_KEY)
        self.subtitle = bind_text(CaptionLabel(), self.main, self.SUBTITLE_KEY)
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        self.tabs = WorkspaceTabs()
        self.tabs.setDocumentMode(True)
        self.panels = tuple(panel_type(self.main, self) for panel_type in self.PANEL_TYPES)
        for panel, label in zip(self.panels, self.LABELS):
            panel.setProperty("embeddedWorkspace", True)
            (arrange_image_tool if self.IMAGE_TOOLS else arrange_table_tool)(panel)
            self.tabs.addTab(panel, label)
        layout.addWidget(self.tabs, 1)
        apply_screen_theme(self, type(self).__name__)
        self._worker_watch = QTimer(self)
        self._worker_watch.setInterval(200)
        self._worker_watch.timeout.connect(self._update_tab_guard)
        self._worker_watch.start()

    def iter_workers(self):
        for panel in self.panels:
            for value in vars(panel).values():
                if isinstance(value, QThread) and value.isRunning():
                    yield value

    def _update_tab_guard(self):
        self.tabs.tabBar().setEnabled(not any(self.iter_workers()))

    def select_mode(self, index):
        if any(self.iter_workers()):
            return False
        self.tabs.setCurrentIndex(index)
        return True

    def request_navigation_away(self):
        if any(self.iter_workers()):
            InfoBar.warning(title=self.main.i18n.tr("common.warning"),
                content=self.main.i18n.tr("kross.browser.busy"), parent=self)
            return False
        return True

    def shutdown(self, wait_ms=5000):
        workers = list(self.iter_workers())
        for worker in workers:
            stop = getattr(worker, "request_stop", None) or getattr(worker, "stop", None)
            stop() if callable(stop) else worker.requestInterruption()
        return all(worker.wait(wait_ms) for worker in workers)

    def retranslate_ui(self):
        for panel in self.panels:
            panel.retranslate_ui()


from GUI_Qt.screens.AbusUrlGetterScreen import AbusUrlGetterScreen
from GUI_Qt.screens.CastelliUrlGetterScreen import CastelliUrlGetterScreen
from GUI_Qt.screens.OakleyUrlGetterScreen import OakleyUrlGetterScreen


class _AbusPanel(_GuardedBrandPanel, AbusUrlGetterScreen):
    pass


class _CastelliUrlPanel(_GuardedBrandPanel, CastelliUrlGetterScreen):
    pass


class _OakleyPanel(_GuardedBrandPanel, OakleyUrlGetterScreen):
    pass


class BrandUrlFinderScreen(BrandToolsScreen):
    PANEL_TYPES = (_AbusPanel, _CastelliUrlPanel, _OakleyPanel)
    LABELS = ("ABUS", "Castelli", "Oakley")
    TITLE_KEY = "layout.url_finder"
    SUBTITLE_KEY = "layout.url_subtitle"


from GUI_Qt.screens.BassoImageScreen import BassoImageScreen
from GUI_Qt.screens.PinarelloImageScreen import PinarelloImageScreen
from GUI_Qt.screens.CastelliImageDownloaderScreen import CastelliImageDownloaderScreen


class _BassoPanel(_GuardedBrandPanel, BassoImageScreen):
    pass


class _PinarelloPanel(_GuardedBrandPanel, PinarelloImageScreen):
    pass


class _CastelliImagePanel(_GuardedBrandPanel, CastelliImageDownloaderScreen):
    pass


class BrandImageDownloaderScreen(BrandToolsScreen):
    PANEL_TYPES = (_BassoPanel, _PinarelloPanel, _CastelliImagePanel)
    LABELS = ("Basso", "Pinarello", "Castelli")
    TITLE_KEY = "layout.image_downloader"
    SUBTITLE_KEY = "layout.image_subtitle"
    IMAGE_TOOLS = True

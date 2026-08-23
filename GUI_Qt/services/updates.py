"""Asynchronous update checking, verification, and installer launch."""

import os

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import QApplication
from qfluentwidgets import InfoBar, InfoBarPosition, MessageBox

from Utilities.Updater import (
    download_verified_update,
    fetch_update_manifest,
    is_newer_version,
    run_installer,
)
from Utilities.Version import get_app_version


class _UpdateCheckWorker(QThread):
    completed = Signal(bool, object, str)

    def __init__(self, manifest_url: str):
        super().__init__()
        self.manifest_url = manifest_url

    def run(self):
        try:
            self.completed.emit(True, fetch_update_manifest(self.manifest_url), "")
        except Exception as error:
            self.completed.emit(False, None, str(error))


class _DownloadWorker(QThread):
    completed = Signal(bool, str, str)

    def __init__(self, manifest):
        super().__init__()
        self.manifest = manifest

    def run(self):
        try:
            name = f"UltraBike_Automatizacija_Setup_{self.manifest.version}.exe"
            path = download_verified_update(self.manifest, name)
            self.completed.emit(True, path, "")
        except Exception as error:
            self.completed.emit(False, "", str(error))


class UpdateService:
    def __init__(self, main_window):
        self.main = main_window

    def schedule(self) -> None:
        main = self.main
        if main._update_check_scheduled:
            return
        main._update_check_scheduled = True
        if not bool(main.settings.get("update_check_enabled", True)):
            return
        if not str(main.settings.get("update_manifest_url", "") or "").strip():
            return
        QTimer.singleShot(2500, lambda: self.check(interactive=False))

    def check(self, interactive: bool = True) -> None:
        main = self.main
        url = str(main.settings.get("update_manifest_url", "") or "").strip()
        if not url:
            if interactive:
                self._show_error("Update manifest URL is not configured")
            return
        worker = _UpdateCheckWorker(url)
        worker.completed.connect(
            lambda ok, manifest, error: self._checked(
                ok, manifest, error, interactive
            )
        )
        worker.start()
        main._update_worker = worker

    def _checked(self, ok: bool, manifest, error: str, interactive: bool) -> None:
        main = self.main
        if not ok:
            self._show_error(error or "Failed to check for updates")
            return
        if not is_newer_version(get_app_version("0.0.0"), manifest.version):
            if interactive:
                InfoBar.success(
                    title=main.i18n.tr("update.uptodate.title"),
                    content=main.i18n.tr("update.uptodate.content"),
                    position=InfoBarPosition.TOP,
                    duration=2500,
                    parent=main,
                )
            return
        body = main.i18n.tr("update.available.content", version=manifest.version)
        if manifest.notes:
            body = f"{body}\n\n{manifest.notes}"
        dialog = MessageBox(main.i18n.tr("update.available.title"), body, main)
        dialog.yesButton.setText(main.i18n.tr("update.available.yes"))
        dialog.cancelButton.setText(main.i18n.tr("update.available.no"))
        if dialog.exec():
            self.download_and_install(manifest)

    def download_and_install(self, manifest) -> None:
        main = self.main
        main._show_loading(main.i18n.tr("update.downloading"))
        worker = _DownloadWorker(manifest)
        worker.completed.connect(self._downloaded)
        worker.start()
        main._update_worker = worker

    def _downloaded(self, ok: bool, path: str, error: str) -> None:
        main = self.main
        if not ok:
            main._show_loading("")
            self._show_error(error or "Failed to download update")
            return
        try:
            run_installer(path, silent=True)
        except Exception as launch_error:
            try:
                if path and os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass
            main._show_loading("")
            self._show_error(str(launch_error))
            return
        QTimer.singleShot(500, QApplication.instance().quit)

    def _show_error(self, message: str) -> None:
        InfoBar.error(
            title=self.main.i18n.tr("update.error.title"),
            content=message,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self.main,
        )

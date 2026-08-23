"""Cooperative worker discovery and shutdown for the main window."""

from PySide6.QtCore import QThread
from qfluentwidgets import MessageBox


class ShutdownService:
    SCREEN_ATTRIBUTES = (
        "upload_screen", "unified_batch_screen", "descriptions_screen",
        "folder_creator_screen", "basso_images_screen", "pinarello_images_screen",
        "spec_checker_screen", "name_getter_screen", "code_getter_screen",
        "castelli_url_getter_screen", "castelli_image_downloader_screen",
        "abus_url_getter_screen", "oakley_url_getter_screen",
        "product_name_getter_screen", "orbea_screen",
    )

    def __init__(self, main_window):
        self.main = main_window

    def iter_workers(self, include_orbea: bool = True):
        seen = set()
        for value in vars(self.main).values():
            if isinstance(value, QThread) and value.isRunning():
                seen.add(id(value))
                yield self.main, value
        for attribute in self.SCREEN_ATTRIBUTES:
            screen = getattr(self.main, attribute, None)
            if screen is None or (
                screen is getattr(self.main, "orbea_screen", None) and not include_orbea
            ):
                continue
            for value in vars(screen).values():
                if isinstance(value, QThread) and id(value) not in seen and value.isRunning():
                    seen.add(id(value))
                    yield screen, value
        login = getattr(self.main, "login_screen", None)
        if login is not None:
            for value in vars(login).values():
                if isinstance(value, QThread) and id(value) not in seen and value.isRunning():
                    seen.add(id(value))
                    yield login, value

    def confirm_stop(self) -> bool:
        if not any(True for _ in self.iter_workers(include_orbea=True)):
            return True
        dialog = MessageBox(
            self.main.i18n.tr("shutdown.confirm.title"),
            self.main.i18n.tr("shutdown.confirm.content"),
            self.main,
        )
        dialog.yesButton.setText(self.main.i18n.tr("shutdown.confirm.stop"))
        dialog.cancelButton.setText(self.main.i18n.tr("common.cancel"))
        try:
            dialog.cancelButton.setFocus()
        except Exception:
            pass
        return bool(dialog.exec())

    def stop_workers(self, wait_ms: int = 5000) -> bool:
        workers = list(self.iter_workers(include_orbea=False))
        for screen, worker in workers:
            if getattr(worker, "is_login_worker", False):
                try:
                    worker.request_stop()
                except Exception:
                    return False
                continue
            shutdown = getattr(screen, "shutdown", None)
            if callable(shutdown):
                try:
                    if not shutdown(wait_ms=wait_ms):
                        return False
                    continue
                except Exception:
                    return False
            stopper = getattr(worker, "request_stop", None) or getattr(worker, "stop", None)
            try:
                stopper() if callable(stopper) else worker.requestInterruption()
            except Exception:
                return False
        for _screen, worker in workers:
            if not worker.isRunning():
                continue
            login_worker = bool(getattr(worker, "is_login_worker", False))
            first_wait = min(max(0, int(wait_ms)), 1500) if login_worker else max(0, int(wait_ms))
            if worker.wait(first_wait):
                continue
            if not login_worker:
                return False

            # WebDriver startup/navigation can be inside an uninterruptible
            # native call.  During application shutdown this temporary login
            # worker owns no user data, so terminate it rather than trapping
            # the whole application behind that call.
            try:
                worker.terminate()
                if not worker.wait(1500):
                    return False
                logger = getattr(self.main, "logger", None)
                if logger is not None:
                    logger.log(
                        "ShutdownService",
                        "Forced a blocked PIMBO login check to stop during shutdown",
                    )
            except Exception:
                return False
        return True

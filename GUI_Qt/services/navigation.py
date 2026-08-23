"""Stable route navigation for the authenticated application shell."""

from PySide6.QtCore import Qt
from qfluentwidgets import InfoBar, InfoBarPosition


class NavigationService:
    def __init__(self, main_window):
        self.main = main_window

    def open(self, route_key: str) -> bool:
        main = self.main
        route_key = str(route_key or "")
        if route_key not in main.ROUTES:
            return False
        if not self.can_leave_current():
            self.restore_selection()
            return False
        try:
            screen = main._ensure_screen_created(route_key)
        except Exception as error:
            try:
                main.logger.error(
                    "Navigation", f"Could not open route {route_key}", exception=error
                )
            except Exception:
                pass
            InfoBar.error(
                title=main.i18n.tr("common.error"),
                content=main.i18n.tr("navigation.load_error"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=main,
            )
            self.restore_selection()
            return False
        main._show_screen(screen)
        main._current_route = route_key
        try:
            main.settings.set("last_authenticated_route", route_key)
        except Exception:
            pass
        try:
            main.navigationInterface.setCurrentItem(route_key)
        except Exception:
            pass
        return True

    def can_leave_current(self) -> bool:
        main = self.main
        stack = getattr(main, "content_stack", None)
        screen = stack.currentWidget() if stack is not None else None
        guard = getattr(screen, "request_navigation_away", None)
        if not callable(guard):
            return True
        try:
            return bool(guard())
        except Exception as error:
            try:
                main.logger.error(
                    "Navigation", "Unsaved-change guard failed", exception=error
                )
            except Exception:
                pass
            return False

    def restore_selection(self) -> None:
        route = self.main._current_route
        if not route:
            return
        try:
            self.main.navigationInterface.setCurrentItem(route)
        except Exception:
            pass

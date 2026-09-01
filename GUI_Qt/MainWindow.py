"""
Main Application Window
Manages navigation, state, and screen switching
"""

from PySide6.QtWidgets import QWidget, QStackedWidget, QHBoxLayout, QApplication, QMessageBox
from PySide6.QtCore import Qt, QEvent, QTimer, QThread
from PySide6.QtGui import QFont, QFontMetrics, QColor, QKeySequence, QShortcut
from qfluentwidgets import FluentWindow, NavigationDisplayMode, NavigationItemPosition, FluentIcon, MessageBox, InfoBar, InfoBarPosition, isDarkTheme

import threading
import time

from Config.LoginConfig.CredentialManager import CredentialManager
from Database.DatabaseManager import DatabaseManager
from Database.SettingsManager import SettingsManager
from Managers.EarningsManager import EarningsManager
from Managers.OperationTracker import OperationKind, OperationTracker
from Managers.SpotifyManager import SpotifyManager
from Utilities.Logger import Logger
from Utilities.Version import get_app_version
from Utilities.AppPaths import get_default_db_path, get_data_dir
from GUI_Qt.styles.theme_config import FONTS
from GUI_Qt.styles.theme_config import COLORS, get_surface_color, get_text_color
from GUI_Qt.styles.theme_config import SPACING
from GUI_Qt.styles.theme_config import RADII
from GUI_Qt.styles.theme_config import PADDINGS
from GUI_Qt.styles.theme_config import SIZES
from GUI_Qt.styles.screen_theme import (
    NAV_VERSION_MARGINS,
    NAV_VERSION_SPACING,
    apply_screen_palette,
    enforce_transparent_labels,
    enforce_responsive_text,
)
from GUI_Qt.components.accessibility import apply_accessibility_defaults
from GUI_Qt.i18n import I18nManager, translate
from GUI_Qt.routes import NAV_GROUPS, ROUTES, ROUTE_REGISTRY
from GUI_Qt.services import (
    ErrorPresentationService,
    NavigationService,
    ShutdownService,
    UpdateService,
)


class MainWindow(FluentWindow):
    """Main application window with Fluent Design navigation"""

    ROUTES = ROUTE_REGISTRY
    NAVIGATION_EXPAND_WIDTH = 240
    NAVIGATION_CLICK_GUARD_MS = 500

    def __init__(self):
        super().__init__()

        # QFluentWidgets can temporarily reparent its navigation panel directly
        # onto the window while choosing a display mode. Guard both the wrapper
        # and that detachable panel from the moment they are constructed.
        self._authenticated_shell_visible = False
        self.navigationInterface.installEventFilter(self)
        self.navigationInterface.panel.installEventFilter(self)
        self._apply_navigation_visibility()

        # Initialize backend managers
        self.driver = None
        self.current_user = None
        self.logger = Logger()
        # Selenium's shared authenticated driver is single-owner. Long-running
        # tools (notably Orbea automation) use this cooperative lease so two
        # screens cannot navigate Pimbo at the same time.
        self._browser_lease_lock = threading.Lock()
        self._browser_lease_owner = None

        # Database setup
        first_run = False
        try:
            first_run = not get_default_db_path().exists()
        except Exception:
            first_run = False

        self.db = DatabaseManager()
        self.settings = SettingsManager(self.db)
        self.earnings_manager = EarningsManager(self.db, self.settings)
        self.credential_manager = CredentialManager(self.db)
        self.spotify_manager = SpotifyManager(
            self.db,
            self.settings,
            self.credential_manager.session_manager,
        )
        self.operation_tracker = OperationTracker(self.db, self)

        # If installed via Inno Setup and this is a fresh install, start the app
        # in the language chosen in the installer wizard.
        if first_run:
            self._apply_installer_language_if_present()

        # Localization (read from DB settings)
        self.i18n = I18nManager(self.settings)
        self.i18n.languageChanged.connect(self._retranslate_ui)

        # Apply saved theme before UI initialization
        self._apply_saved_theme()

        # Configure window
        self.setWindowTitle(self.i18n.tr("app.title"))
        # Responsive design: support tablet-sized displays (900x700 minimum)
        # Screens use adaptive layouts and scrolling to remain usable at all sizes
        self.resize(1400, 900)
        self.setMinimumSize(900, 700)

        # Preserve the operating system's configured point size so Windows text
        # scaling remains effective. Prefer the modern UI family when present.
        app = QApplication.instance()
        if app is not None:
            app_font = app.font()
            app_font.setFamilies(["Segoe UI Variable", "Segoe UI"])
            app.setFont(app_font)

        # Restore a usable window placement, clamped to a connected monitor.
        self._restore_window_state()

        # Initialize screens (lazy loading)
        self.login_screen = None
        self._loading_widget = None

        # Cached for current run after master unlock/setup
        self._unlocked_master_password = None
        self.upload_screen = None
        self.unified_batch_screen = None
        self.history_screen = None
        self.earnings_screen = None
        self.spotify_screen = None
        self.activity_screen = None
        self._full_history_screen = None  # Full detailed history view (accessed from Analytics)
        self.translations_screen = None
        self.descriptions_screen = None
        self.folder_creator_screen = None
        self.basso_images_screen = None
        self.pinarello_images_screen = None
        self.account_screen = None
        self.settings_screen = None
        self.info_screen = None
        self.spec_checker_screen = None
        self.name_getter_screen = None
        self.code_getter_screen = None
        self.product_name_getter_screen = None
        self.castelli_url_getter_screen = None
        self.castelli_image_downloader_screen = None
        self.abus_url_getter_screen = None
        self.oakley_url_getter_screen = None
        self.orbea_screen = None
        self.kross_screen = None

        # Top bar reference
        self.top_bar = None
        self._main_container = None
        self.content_stack = None
        self._current_route = None
        self._last_navigation_compact = None
        self.navigation_service = NavigationService(self)
        self.shutdown_service = ShutdownService(self)
        self.update_service = UpdateService(self)
        self.error_service = ErrorPresentationService(self)

        # Update check (best-effort; won't block app startup)
        self._update_check_scheduled = False
        self._update_worker = None

        # Screen preloading (to avoid first-switch lag)
        self._screen_preload_active = False
        self._screen_preload_cancelled = False
        self._screen_preload_queue = []

        # Setup UI
        self._init_navigation()
        self._init_window()
        self._init_shortcuts()

        # The title-bar theme signal is connected in _init_window().
        self._apply_titlebar_theme()

        # Apply translations to any static UI created above
        self._retranslate_ui(self.i18n.language.code)

        # Hide navigation until logged in
        self._apply_navigation_visibility()

        # Check session and show appropriate screen
        self._check_session()

        # Setup GUI-backed prompt handling for ErrorManager
        self._init_prompt_handling()

    def _apply_installer_language_if_present(self) -> None:
        try:
            marker = get_data_dir() / "install_language.txt"
            if not marker.exists():
                return

            raw = marker.read_text(encoding="utf-8", errors="ignore").strip()
            if raw not in ("English", "Lithuanian"):
                return

            self.settings.set("language", raw)

            try:
                marker.unlink(missing_ok=True)
            except Exception:
                pass
        except Exception:
            pass

    def start_screen_preload(self) -> None:
        """Best-effort: eagerly construct heavy screens during login wait.

        Qt widgets must be created in the GUI thread, so we do it incrementally
        via QTimer while the Selenium login thread is running.
        """
        if self._screen_preload_active:
            return

        self._screen_preload_active = True
        self._screen_preload_cancelled = False

        # Only the heavy ones that typically lag on first visit.
        self._screen_preload_queue = [
            "orbea",
            "batch",
            "history",
            "translations",
            "descriptions",
            "activity",
            "spotify",
        ]

        def _step() -> None:
            if self._screen_preload_cancelled:
                self._screen_preload_active = False
                self._screen_preload_queue = []
                return

            if not self._screen_preload_queue:
                self._screen_preload_active = False
                return

            route_key = self._screen_preload_queue.pop(0)
            try:
                self._ensure_screen_created(route_key)
            except Exception:
                # Preloading is best-effort; never crash the login flow.
                pass

            # Let the event loop breathe between heavy widget builds.
            QTimer.singleShot(50, _step)

        QTimer.singleShot(0, _step)

    def cancel_screen_preload(self) -> None:
        """Cancel any in-progress screen preloading."""
        self._screen_preload_cancelled = True

    def _add_created_screens_to_stack(self) -> None:
        """If screens were constructed before content_stack existed, add them now."""
        try:
            # Only safe after show_main created self.content_stack.
            if not hasattr(self, 'content_stack'):
                return

            mapping = [
                (getattr(self, 'upload_screen', None), "nav.upload"),
                (getattr(self, 'unified_batch_screen', None), "nav.batch"),
                (getattr(self, 'history_screen', None), "nav.analytics"),
                (getattr(self, 'earnings_screen', None), "nav.earnings"),
                (getattr(self, 'spotify_screen', None), "nav.spotify"),
                (getattr(self, 'activity_screen', None), "nav.activity"),
                (getattr(self, 'translations_screen', None), "nav.translations"),
                (getattr(self, 'descriptions_screen', None), "nav.descriptions"),
                (getattr(self, 'folder_creator_screen', None), "nav.folders"),
                (getattr(self, 'basso_images_screen', None), "nav.basso_images"),
                (getattr(self, 'pinarello_images_screen', None), "nav.pinarello_images"),
                (getattr(self, 'account_screen', None), "nav.account"),
                (getattr(self, 'settings_screen', None), "nav.settings"),
                (getattr(self, 'info_screen', None), "nav.info"),
                (getattr(self, 'spec_checker_screen', None), "nav.spec_checker"),
                (getattr(self, 'name_getter_screen', None), "nav.name_getter"),
                (getattr(self, 'code_getter_screen', None), "nav.code_getter"),
                (getattr(self, 'product_name_getter_screen', None), "nav.product_name_getter"),
                (getattr(self, 'castelli_url_getter_screen', None), "nav.castelli_url_getter"),
                (getattr(self, 'castelli_image_downloader_screen', None), "nav.castelli_images"),
                (getattr(self, 'abus_url_getter_screen', None), "nav.abus_url_getter"),
                (getattr(self, 'oakley_url_getter_screen', None), "nav.oakley_url_getter"),
                (getattr(self, 'orbea_screen', None), "nav.orbea"),
                (getattr(self, 'kross_screen', None), "nav.kross"),
            ]

            for screen, key in mapping:
                if screen is not None:
                    self._add_screen_to_stack(screen, self.i18n.tr(key))
        except Exception:
            pass

    def _ensure_screen_created(self, route_key: str):
        """Create a registered page lazily and attach it to the content stack."""
        spec = self.ROUTES.get(str(route_key))
        if spec is None:
            raise KeyError(f"Unknown application route: {route_key}")
        screen = spec.screen_factory(self)
        self._add_screen_to_stack(screen, self.i18n.tr(spec.label_key))
        return screen

    def _init_prompt_handling(self):
        self.error_service.start()

    def _process_prompt_queue(self):
        self.error_service.process()

    def _center_on_screen(self):
        """Center the window on the screen"""
        from PySide6.QtGui import QScreen
        screen = QScreen.availableGeometry(QApplication.primaryScreen())
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def _restore_window_state(self) -> None:
        """Restore normal geometry without allowing an off-screen window."""
        try:
            width = max(self.minimumWidth(), int(self.settings.get("window_width", 1400)))
            height = max(self.minimumHeight(), int(self.settings.get("window_height", 900)))
            screens = list(QApplication.screens())
            primary = QApplication.primaryScreen()
            if not screens or primary is None:
                self.resize(width, height)
                return
            saved_x = int(self.settings.get("window_x", -1))
            saved_y = int(self.settings.get("window_y", -1))
            target = None
            if saved_x >= 0 and saved_y >= 0:
                from PySide6.QtCore import QPoint
                point = QPoint(saved_x, saved_y)
                target = next(
                    (screen for screen in screens if screen.availableGeometry().contains(point)),
                    None,
                )
            target = target or primary
            available = target.availableGeometry()
            width = min(width, available.width())
            height = min(height, available.height())
            self.resize(width, height)
            if saved_x < 0 or saved_y < 0 or target is primary and not available.contains(saved_x, saved_y):
                saved_x = available.x() + max(0, (available.width() - width) // 2)
                saved_y = available.y() + max(0, (available.height() - height) // 2)
            saved_x = max(available.left(), min(saved_x, available.right() - width + 1))
            saved_y = max(available.top(), min(saved_y, available.bottom() - height + 1))
            self.move(saved_x, saved_y)
            if bool(self.settings.get("window_maximized", False)):
                self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)
        except Exception:
            self.resize(1400, 900)
            self._center_on_screen()

    def _save_window_state(self) -> None:
        geometry = self.normalGeometry() if self.isMaximized() else self.geometry()
        self.settings.set_many(
            {
                "window_x": geometry.x(),
                "window_y": geometry.y(),
                "window_width": geometry.width(),
                "window_height": geometry.height(),
                "window_maximized": self.isMaximized(),
                "navigation_compact": bool(self._last_navigation_compact),
                "last_authenticated_route": self._current_route or "upload",
            }
        )

    def try_acquire_browser_lease(self, owner) -> bool:
        """Return True when *owner* may exclusively use the shared driver."""
        with self._browser_lease_lock:
            if self._browser_lease_owner in (None, owner):
                self._browser_lease_owner = owner
                return True
            return False

    def release_browser_lease(self, owner) -> None:
        """Release a lease held by *owner* without disturbing another tool."""
        with self._browser_lease_lock:
            if self._browser_lease_owner == owner:
                self._browser_lease_owner = None

    def browser_lease_owner(self):
        with self._browser_lease_lock:
            return self._browser_lease_owner

    def _init_navigation(self):
        """Initialize navigation sidebar"""

        # Keep references to nav items so we can update text when language changes
        self._nav_items = {}
        self._nav_item_last_click = {}

        def _set_route_emphasis(item, selected: bool) -> None:
            """Give the active route a strong accent and mute inactive routes."""
            if item is None:
                return
            try:
                if selected:
                    item.setTextColor(COLORS["space_indigo"], COLORS["text_white"])
                else:
                    item.setTextColor(
                        COLORS["text_secondary_light"],
                        COLORS["text_secondary_dark"],
                    )
                item.setIndicatorColor(
                    COLORS["focus_ring_light"],
                    COLORS["focus_ring_dark"],
                )
                font = item.font()
                font.setWeight(QFont.Weight.DemiBold if selected else QFont.Weight.Normal)
                item.setFont(font)
                self._refresh_nav_item_text(item)
                item.update()
            except Exception:
                pass

        def _add_group(
            route_key: str,
            icon,
            text_key: str,
            position=NavigationItemPosition.SCROLL,
        ):
            item = self.navigationInterface.addItem(
                routeKey=route_key,
                icon=icon,
                text=self.i18n.tr(text_key),
                selectable=False,
                position=position,
                tooltip=self.i18n.tr(text_key),
            )
            self._nav_items[route_key] = item
            MainWindow._install_navigation_item_click_guard(self, item, route_key)
            try:
                item.setTextColor(
                    COLORS["text_primary_light"],
                    COLORS["text_primary_dark"],
                )
                font = item.font()
                font.setWeight(QFont.Weight.DemiBold)
                item.setFont(font)
            except Exception:
                pass
            self._set_nav_item_text(route_key, self.i18n.tr(text_key))

        def _add_item(
            route_key: str,
            icon,
            text_key: str,
            parent_key: str | None,
            position=NavigationItemPosition.SCROLL,
        ):
            item = self.navigationInterface.addItem(
                routeKey=route_key,
                icon=icon,
                text=self.i18n.tr(text_key),
                # NavigationWidget.clicked emits ``triggered_by_user``. Keep
                # that Boolean separate from the route captured here.
                onClick=lambda _triggered=False, key=route_key: self.open_route(key),
                position=position,
                parentRouteKey=parent_key,
                tooltip=self.i18n.tr(text_key),
            )
            self._nav_items[route_key] = item
            MainWindow._install_navigation_item_click_guard(self, item, route_key)
            _set_route_emphasis(item, bool(getattr(item, "isSelected", False)))
            self._set_nav_item_text(route_key, self.i18n.tr(text_key))
            try:
                item.selectedChanged.connect(
                    lambda selected, nav_item=item: _set_route_emphasis(nav_item, bool(selected))
                )
            except Exception:
                pass

        for group in NAV_GROUPS:
            parent_key = f"nav_group_{group.key}"
            _add_group(parent_key, group.icon, group.label_key, group.position)
            for route in (item for item in ROUTES if item.group == group.key):
                _add_item(route.key, route.icon, route.label_key, parent_key, group.position)

        # System destinations stay permanently visible and one click away.
        for route in (item for item in ROUTES if item.group == "system"):
            _add_item(
                route.key,
                route.icon,
                route.label_key,
                None,
                position=NavigationItemPosition.BOTTOM,
            )

        # Major sections get more breathing room than the child rows inside
        # each native navigation tree. Keep a little trailing space so the
        # final Brand tools row scrolls fully clear of the pinned footer.
        try:
            scroll_layout = self.navigationInterface.panel.scrollLayout
            scroll_layout.setSpacing(SPACING["sm"])
            margins = scroll_layout.contentsMargins()
            scroll_layout.setContentsMargins(
                margins.left(),
                margins.top(),
                margins.right(),
                SPACING["sm"],
            )
        except Exception:
            pass

        # Version label in navigation footer (under everything)
        try:
            from PySide6.QtWidgets import QHBoxLayout
            from qfluentwidgets import BodyLabel, IconWidget
            from qfluentwidgets.components.navigation.navigation_widget import NavigationWidget
            self.navigationInterface.addSeparator(NavigationItemPosition.BOTTOM)

            version_widget = NavigationWidget(isSelectable=False)
            version_layout = QHBoxLayout(version_widget)
            version_layout.setContentsMargins(*NAV_VERSION_MARGINS)
            version_layout.setSpacing(NAV_VERSION_SPACING)

            version_icon = IconWidget()
            version_icon.setIcon(FluentIcon.APPLICATION)
            version_icon.setFixedSize(SIZES['icon_xs'], SIZES['icon_xs'])
            try:
                version_icon.setStyleSheet(f"color: {get_text_color(isDarkTheme(), 'secondary')};")
            except Exception:
                pass
            version_layout.addWidget(version_icon, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

            version_label = BodyLabel(get_app_version('2.0.0'))
            version_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            try:
                version_label.setStyleSheet(
                    f"color: {get_text_color(isDarkTheme(), 'secondary')};"
                )
            except Exception:
                pass
            version_layout.addWidget(version_label, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

            # Keep a reference in case we want to update later
            self._nav_items["version"] = version_label

            self.navigationInterface.addWidget(
                routeKey="version",
                widget=version_widget,
                onClick=None,
                position=NavigationItemPosition.BOTTOM,
            )
        except Exception:
            pass

    def _install_navigation_item_click_guard(self, item, route_key: str) -> None:
        """Make every navigation-tree click atomic and bounce-resistant."""
        try:
            # NavigationTreeWidget animates its geometry even for leaf routes.
            # Replacing that private toggler prevents both parent and child rows
            # from being left mid-animation by a duplicate mouse release.
            original_handler = item._onClicked
            item.itemWidget.itemClicked.disconnect(original_handler)
        except Exception:
            # Keep the library's normal behavior if its internal API changes.
            return

        try:
            callback = (
                lambda triggered=False, click_arrow=False, nav_item=item, key=route_key: (
                    MainWindow._on_navigation_item_clicked(
                        self,
                        nav_item,
                        key,
                        bool(triggered),
                        bool(click_arrow),
                    )
                )
            )
            item._ultrabike_click_guard = callback
            item.itemWidget.itemClicked.connect(callback)
        except Exception:
            # Never leave an item without a click handler if reconnecting fails.
            try:
                item.itemWidget.itemClicked.connect(original_handler)
            except Exception:
                pass

    def _on_navigation_item_clicked(
        self,
        item,
        route_key: str,
        triggered_by_user: bool,
        click_arrow: bool,
    ) -> None:
        """Handle a sidebar item once per physical double-click burst."""
        if triggered_by_user:
            now = time.monotonic()
            previous = self._nav_item_last_click.get(route_key, 0.0)
            guard_seconds = self.NAVIGATION_CLICK_GUARD_MS / 1000.0
            if now - previous < guard_seconds:
                return
            self._nav_item_last_click[route_key] = now

        # Leaf routes have nothing to expand. QFluentWidgets still starts a
        # geometry animation for them by default, which is the source of the
        # selected child row overlapping its parent in the reported screenshot.
        if not item.isCompacted and not item.isLeaf():
            if item.isSelectable and not item.isSelected and not click_arrow:
                item.setExpanded(True, ani=False)
            else:
                item.setExpanded(not item.isExpanded, ani=False)
            MainWindow._finalize_navigation_item_layout(self, item)

        if not click_arrow or item.isCompacted:
            item.clicked.emit(triggered_by_user)

    def _finalize_navigation_item_layout(self, item) -> None:
        """Snap tree children and parent geometry to one completed state."""
        try:
            for child in item.childItems():
                child.setVisible(item.isExpanded)
                if item.isExpanded:
                    child.setFixedSize(child.sizeHint())
            item.setFixedSize(item.sizeHint())
            item.updateGeometry()

            layout = item.parentWidget().layout()
            if layout is not None:
                layout.invalidate()
                layout.activate()
        except Exception:
            pass

    def apply_language_preview(self, lang_code: str) -> None:
        """Temporarily translate app chrome without changing persisted language.

        Intended for Settings preview. This does NOT modify self.i18n.language.
        """
        try:
            self.setWindowTitle(translate(lang_code, "app.title"))
            self._retranslate_navigation(lang_code)
        except Exception:
            pass

    def clear_language_preview(self) -> None:
        """Restore app chrome to the globally-applied language."""
        try:
            self._retranslate_ui(self.i18n.language.code)
        except Exception:
            pass

    def get_unlocked_master_password(self, parent=None):
        """Return cached master password, or prompt the user to unlock."""
        try:
            if self._unlocked_master_password and self.credential_manager.verify_master_password(self._unlocked_master_password):
                return self._unlocked_master_password
        except Exception:
            pass

        if not self.credential_manager.has_master_password():
            return None

        try:
            from qfluentwidgets import MessageBox, PasswordLineEdit

            dialog_parent = parent if parent is not None else self
            dialog = MessageBox(
                self.i18n.tr("master.prompt.title"),
                self.i18n.tr("master.prompt.subtitle"),
                dialog_parent,
            )

            pw = PasswordLineEdit()
            pw.setPlaceholderText(self.i18n.tr("master.password.placeholder"))
            pw.setMinimumWidth(SIZES['dialog_min_width'])
            pw.returnPressed.connect(lambda: dialog.accept())
            dialog.textLayout.addWidget(pw)
            dialog.yesButton.setText(self.i18n.tr("master.unlock"))
            dialog.cancelButton.setText(self.i18n.tr("common.cancel"))

            if not dialog.exec():
                return None

            candidate = pw.text()
            if self.credential_manager.verify_master_password(candidate):
                self._unlocked_master_password = candidate
                return candidate

            return None
        except Exception:
            return None

    def _apply_nav_item_text(self, item, text: str) -> None:
        """Apply full accessible text and a width-aware visible label."""

        full_text = str(text)
        try:
            item.setProperty("fullNavigationText", full_text)
        except Exception:
            pass
        try:
            setattr(item, "_full_navigation_text", full_text)
        except Exception:
            pass
        try:
            item.setAccessibleName(full_text)
        except Exception:
            pass
        try:
            item.setToolTip(full_text)
        except Exception:
            pass

        visible_text = full_text
        try:
            # QFluentWidgets draws expanded items 10 px narrower than the
            # panel. Its margins already include native tree indentation and
            # the group arrow allowance.
            item_width = self.NAVIGATION_EXPAND_WIDTH - 10
            margins = item._margins()
            icon = item.icon()
            left = 44 + margins.left() if not icon.isNull() else margins.left() + 16
            available = max(24, item_width - left - margins.right() - 13)
            visible_text = QFontMetrics(item.font()).elidedText(
                full_text,
                Qt.TextElideMode.ElideRight,
                available,
            )
        except Exception:
            pass

        if hasattr(item, "setText"):
            try:
                item.setText(visible_text)
            except Exception:
                pass

    def _refresh_nav_item_text(self, item) -> None:
        """Recalculate elision after a navigation item's font changes."""

        full_text = getattr(item, "_full_navigation_text", None)
        if full_text is None:
            try:
                full_text = item.property("fullNavigationText")
            except Exception:
                full_text = None
        if full_text is not None:
            self._apply_nav_item_text(item, full_text)

    def _set_nav_item_text(self, route_key: str, text: str) -> None:
        """Best-effort: update a navigation item's translated label."""
        item = getattr(self, "_nav_items", {}).get(route_key)
        if item is not None:
            self._apply_nav_item_text(item, text)
            return

        nav = getattr(self, "navigationInterface", None)
        if nav is not None and hasattr(nav, "setItemText"):
            try:
                nav.setItemText(route_key, text)
            except Exception:
                pass

    def _retranslate_navigation(self, lang_code: str | None = None) -> None:
        """Refresh every navigation label from the declarative registries."""

        def translated(key: str) -> str:
            return translate(lang_code, key) if lang_code else self.i18n.tr(key)

        for group in NAV_GROUPS:
            self._set_nav_item_text(
                f"nav_group_{group.key}",
                translated(group.label_key),
            )
        for route in ROUTES:
            self._set_nav_item_text(route.key, translated(route.label_key))

    def _retranslate_ui(self, _lang_code: str | None = None) -> None:
        """Update static UI strings when the application language changes."""
        try:
            self.setWindowTitle(self.i18n.tr("app.title"))
            self._retranslate_navigation()

            # Notify screens if they implement live retranslation
            for screen in (
                getattr(self, "top_bar", None),
                getattr(self, "upload_screen", None),
                getattr(self, "unified_batch_screen", None),
                getattr(self, "history_screen", None),
                getattr(self, "earnings_screen", None),
                getattr(self, "spotify_screen", None),
                getattr(self, "activity_screen", None),
                getattr(self, "translations_screen", None),
                getattr(self, "descriptions_screen", None),
                getattr(self, "folder_creator_screen", None),
                getattr(self, "basso_images_screen", None),
                getattr(self, "pinarello_images_screen", None),
                getattr(self, "account_screen", None),
                getattr(self, "settings_screen", None),
                getattr(self, "info_screen", None),
                getattr(self, "spec_checker_screen", None),
                getattr(self, "name_getter_screen", None),
                getattr(self, "code_getter_screen", None),
                getattr(self, "product_name_getter_screen", None),
                getattr(self, "castelli_url_getter_screen", None),
                getattr(self, "castelli_image_downloader_screen", None),
                getattr(self, "abus_url_getter_screen", None),
                getattr(self, "oakley_url_getter_screen", None),
                getattr(self, "orbea_screen", None),
                getattr(self, "kross_screen", None),
            ):
                if screen is not None and hasattr(screen, "retranslate_ui"):
                    try:
                        screen.retranslate_ui()
                    except Exception:
                        pass
        except Exception:
            # Localization must never crash the app
            pass

    def _init_window(self):
        """Initialize window layout"""
        # FluentWindow automatically handles navigation layout
        # Start with the compact icon rail. The user can expand it after the
        # authenticated shell becomes visible.
        self.navigationInterface.setExpandWidth(self.NAVIGATION_EXPAND_WIDTH)
        try:
            self.navigationInterface.setMinimumExpandWidth(1100)
        except Exception:
            pass
        self.navigationInterface.displayModeChanged.connect(
            self._on_navigation_display_mode_changed
        )

        # The NavigationInterface shows a return/back button by default.
        # In this app it isn't wired to a stack navigation action, so hide it.
        try:
            self.navigationInterface.panel.setReturnButtonVisible(False)
        except Exception:
            pass

        # Keep title bar buttons + title text readable in both themes
        try:
            from qfluentwidgets import qconfig
            qconfig.themeChangedFinished.connect(self._on_global_theme_changed)
        except Exception:
            pass
        self._apply_titlebar_theme()

    def _on_global_theme_changed(self):
        """Re-apply theme-dependent window chrome after theme switches."""
        try:
            from qfluentwidgets import isDarkTheme
            from GUI_Qt.styles.theme_config import set_mode_aware_theme

            # Normally Settings primes the accent before changing mode. This is
            # also a fallback for theme changes initiated elsewhere.
            set_mode_aware_theme(isDarkTheme(), lazy=True)
        except Exception:
            pass
        try:
            from GUI_Qt.styles.global_styles import get_global_stylesheet

            app = QApplication.instance()
            if app is not None:
                stylesheet = get_global_stylesheet()
                if app.styleSheet() != stylesheet:
                    app.setStyleSheet(stylesheet)
        except Exception:
            pass
        try:
            self.update_container_backgrounds()
        except Exception:
            pass
        self._apply_titlebar_theme()
        self._sync_navigation_for_width(force=True)

        # Restarting one owned timer coalesces any external rapid theme signals
        # and cannot leave callbacks behind after this window is destroyed.
        timer = getattr(self, "_theme_polish_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._polish_all_screens_after_theme)
            self._theme_polish_timer = timer
        timer.start(0)

    def _polish_all_screens_after_theme(self) -> None:
        """Finalize inherited palettes after all page-specific handlers."""
        try:
            stack = getattr(self, "content_stack", None)
            count = stack.count() if stack is not None else 0
        except RuntimeError:
            return
        for index in range(count):
            try:
                screen = stack.widget(index)
                if screen is None:
                    continue
                apply_screen_palette(screen)
                enforce_transparent_labels(screen)
            except RuntimeError:
                return

    def _init_shortcuts(self) -> None:
        """Install a compact set of predictable desktop keyboard shortcuts."""
        self._shortcuts = []

        def _add(sequence: str, callback) -> None:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)

        _add("Ctrl+,", lambda: self.open_route("settings"))
        _add("Ctrl+Shift+R", self.reconnect_browser)
        _add("F6", lambda: self._cycle_focus(False))
        _add("Shift+F6", lambda: self._cycle_focus(True))

    def _cycle_focus(self, backwards: bool = False) -> None:
        """Move focus between navigation, the top bar, and page content."""
        if not self.navigationInterface.isVisible():
            return
        targets = [
            self.navigationInterface,
            getattr(self, "top_bar", None),
            getattr(self, "content_stack", None),
        ]
        targets = [target for target in targets if target is not None and target.isVisible()]
        if not targets:
            return
        focused = QApplication.focusWidget()
        current = -1
        for index, target in enumerate(targets):
            if focused is target or (focused is not None and target.isAncestorOf(focused)):
                current = index
                break
        step = -1 if backwards else 1
        target = targets[(current + step) % len(targets)]
        if target is self.content_stack and self.content_stack.currentWidget() is not None:
            target = self.content_stack.currentWidget()
        target.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _sync_navigation_for_width(self, force: bool = False) -> None:
        """Keep the navigation usable without crowding minimum-size pages."""
        if not getattr(self, "_authenticated_shell_visible", False):
            self._apply_navigation_visibility()
            return

        compact = self.width() < 1120
        if force and not compact:
            try:
                compact = bool(self.settings.get("navigation_compact", True))
            except Exception:
                pass
        if not force and compact == self._last_navigation_compact:
            return
        self._last_navigation_compact = compact
        try:
            if compact:
                self.navigationInterface.panel.collapse()
            else:
                self.navigationInterface.panel.expand(useAni=False)
        except Exception:
            try:
                if compact:
                    self.navigationInterface.collapse()
                else:
                    self.navigationInterface.expand(useAni=False)
            except Exception:
                pass

    def _on_navigation_display_mode_changed(self, mode) -> None:
        """Remember a signed-in user's compact/expanded rail choice."""
        if not getattr(self, "_authenticated_shell_visible", False):
            return
        compact = mode != NavigationDisplayMode.EXPAND
        self._last_navigation_compact = compact
        try:
            self.settings.set("navigation_compact", compact)
        except Exception:
            pass

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_navigation_for_width()

    def showEvent(self, event) -> None:
        """Keep pre-authentication screens free of the application sidebar."""
        super().showEvent(event)
        self._apply_navigation_visibility()
        # Some FluentWindow layout work is queued until after showEvent. Reapply
        # the state once that work has completed so the rail cannot flash in.
        QTimer.singleShot(0, self._apply_navigation_visibility)

    def eventFilter(self, watched, event) -> bool:
        """Reject late navigation show events until authentication finishes."""
        navigation = getattr(self, "navigationInterface", None)
        panel = getattr(navigation, "panel", None) if navigation is not None else None
        is_navigation_part = watched is navigation or watched is panel
        if (
            is_navigation_part
            and event.type() == QEvent.Type.Show
            and not getattr(self, "_authenticated_shell_visible", False)
        ):
            watched.hide()
            return True
        return super().eventFilter(watched, event)

    def _apply_navigation_visibility(self) -> None:
        navigation = getattr(self, "navigationInterface", None)
        if navigation is not None:
            visible = bool(self._authenticated_shell_visible)
            navigation.setVisible(visible)
            panel = getattr(navigation, "panel", None)
            if panel is not None:
                panel.setVisible(visible)

    def _set_authenticated_shell_visible(self, visible: bool) -> None:
        self._authenticated_shell_visible = bool(visible)
        self._apply_navigation_visibility()

    @staticmethod
    def _qcolor(hex_color: str, alpha: int = 255) -> QColor:
        c = QColor(hex_color)
        c.setAlpha(alpha)
        return c

    def _apply_titlebar_theme(self) -> None:
        """Ensure window title bar text/buttons have sufficient contrast."""
        try:
            from qfluentwidgets import isDarkTheme
            is_dark = isDarkTheme()
        except Exception:
            return

        tb = getattr(self, 'titleBar', None)
        if tb is None:
            return

        title_color = COLORS['text_primary_dark'] if is_dark else COLORS['text_primary_light']

        # Add a bit of spacing between icon and title
        try:
            if hasattr(tb, 'titleLabel') and tb.titleLabel is not None:
                tb.titleLabel.setStyleSheet(
                    f"color: {title_color}; background: transparent; padding-left: {SPACING['sm']}px;"
                )
        except Exception:
            pass

        # Title bar buttons (min/max/close) come from qframelesswindow and default to black icons.
        fg = QColor(title_color)
        transparent = QColor(0, 0, 0, 0)

        hover_bg = self._qcolor(COLORS['lavender_grey' if is_dark else 'space_indigo'], 46 if is_dark else 26)
        pressed_bg = self._qcolor(COLORS['lavender_grey' if is_dark else 'space_indigo'], 78 if is_dark else 46)

        close_hover = self._qcolor(COLORS['flag_red'], 110 if is_dark else 70)
        close_pressed = self._qcolor(COLORS['flag_red'], 160 if is_dark else 110)

        for attr, is_close in (("minBtn", False), ("maxBtn", False), ("closeBtn", True)):
            btn = getattr(tb, attr, None)
            if btn is None:
                continue
            try:
                btn.setNormalColor(fg)
                btn.setHoverColor(fg)
                btn.setPressedColor(fg)

                btn.setNormalBackgroundColor(transparent)
                if is_close:
                    btn.setHoverBackgroundColor(close_hover)
                    btn.setPressedBackgroundColor(close_pressed)
                else:
                    btn.setHoverBackgroundColor(hover_bg)
                    btn.setPressedBackgroundColor(pressed_bg)

                # Some theme operations can reset qframelesswindow button colors
                # after initialization. Enforce them via qproperty styling too.
                try:
                    fmt = QColor.NameFormat.HexArgb
                    btn.setStyleSheet(
                        "\n".join([
                            f"qproperty-normalColor: {fg.name(fmt)};",
                            f"qproperty-hoverColor: {fg.name(fmt)};",
                            f"qproperty-pressedColor: {fg.name(fmt)};",
                            f"qproperty-normalBackgroundColor: {transparent.name(fmt)};",
                            f"qproperty-hoverBackgroundColor: {(close_hover if is_close else hover_bg).name(fmt)};",
                            f"qproperty-pressedBackgroundColor: {(close_pressed if is_close else pressed_bg).name(fmt)};",
                        ])
                    )
                except Exception:
                    pass
            except Exception:
                continue

        # Re-apply once more after the event loop runs. This guards against
        # late titleBar/button construction or theme updates that overwrite colors.
        # Guarded to avoid an infinite singleShot loop.
        try:
            if not getattr(self, "_titlebar_theme_deferred", False):
                self._titlebar_theme_deferred = True

                def _late_apply() -> None:
                    try:
                        # Keep the guard set during the call so this deferred
                        # pass cannot schedule itself forever.
                        self._apply_titlebar_theme()
                    finally:
                        self._titlebar_theme_deferred = False

                QTimer.singleShot(0, _late_apply)
        except Exception:
            pass
    def open_route(self, route_key: str) -> bool:
        """Open a stable application route by key."""
        return self.navigation_service.open(route_key)

    def track_worker(self, worker, kind, source_route: str, **metadata):
        """Attach a screen's QThread to the persistent Activity lifecycle."""
        record = self.operation_tracker.track_qthread(
            worker,
            kind if isinstance(kind, OperationKind) else str(kind),
            source_route,
            **metadata,
        )
        try:
            worker._operation_record_id = record.id
        except Exception:
            pass
        return record

    def _switch_to_screen(self, route_key: str):
        return self.open_route(route_key)

    def _can_leave_current_screen(self) -> bool:
        return self.navigation_service.can_leave_current()

    def _restore_current_navigation_selection(self) -> None:
        self.navigation_service.restore_selection()

    def _add_screen_to_stack(self, screen, name):
        """Add screen to content stack if not already added"""
        # Check if content_stack exists (after login)
        if getattr(self, 'content_stack', None) is None:
            return False

        # Check if screen already in stack
        for i in range(self.content_stack.count()):
            if self.content_stack.widget(i) == screen:
                return True

        # Add screen to stack
        self.content_stack.addWidget(screen)
        self._polish_screen(screen)
        return True

    def _polish_screen(self, screen) -> None:
        """Apply cross-screen responsive and assistive-technology defaults."""
        def _apply() -> None:
            apply_screen_palette(screen)
            enforce_transparent_labels(screen)
            enforce_responsive_text(screen)
            apply_accessibility_defaults(screen)

        _apply()
        QTimer.singleShot(0, _apply)

    def _show_screen(self, screen):
        """Show a specific screen in content stack"""
        if getattr(self, 'content_stack', None) is None:
            return

        # Verify screen is in stack before trying to show it
        is_in_stack = False
        for i in range(self.content_stack.count()):
            if self.content_stack.widget(i) == screen:
                is_in_stack = True
                break

        if is_in_stack:
            self.content_stack.setCurrentWidget(screen)
            self._polish_screen(screen)
            activated = getattr(screen, "on_activated", None)
            if callable(activated):
                QTimer.singleShot(0, activated)

    def _check_session(self):
        """Check for valid session and show appropriate screen"""

        if self.credential_manager.has_master_password():
            if self.credential_manager.session_manager.validate_session():
                # Valid session exists - auto-login
                email, password = self.credential_manager.get_saved_credentials()
                if email and password:
                    self._auto_login(email, password)
                    return

            # Master password exists but session expired
            self._show_master_password_prompt()
        else:
            # First run - setup master password
            self._show_master_password_setup()

    def _show_loading(self, message):
        """Show loading screen"""
        from GUI_Qt.widgets.LoadingWidget import LoadingWidget

        # Startup authentication uses the same loading widget as signed-in
        # operations such as update downloads. Respect the current shell state:
        # hidden before login, visible for an operation inside the main app.
        self._apply_navigation_visibility()
        if self._loading_widget is None:
            self._loading_widget = LoadingWidget(message, tr=self.i18n.tr)
            self.stackedWidget.addWidget(self._loading_widget)
        else:
            self._loading_widget.set_message(message)
        self.stackedWidget.setCurrentWidget(self._loading_widget)
        self._polish_screen(self._loading_widget)

    def _show_master_password_setup(self):
        """Show master password setup screen (first run)"""
        from GUI_Qt.dialogs.MasterPasswordDialog import MasterPasswordSetupDialog

        def on_complete(master_password):
            self._unlocked_master_password = master_password
            # Master password created, now show login
            self.show_login()

        setup_screen = MasterPasswordSetupDialog(self, on_complete)
        self.stackedWidget.addWidget(setup_screen)
        self.stackedWidget.setCurrentWidget(setup_screen)
        self._polish_screen(setup_screen)

    def _show_master_password_prompt(self):
        """Show master password prompt (session expired)"""
        from GUI_Qt.dialogs.MasterPasswordDialog import MasterPasswordPromptDialog

        def on_success(email, password):
            try:
                # Prompt dialog caches this too, but keep it here for safety
                if hasattr(self, "_unlocked_master_password") and self._unlocked_master_password:
                    pass
            except Exception:
                pass
            if email and password:
                # Master password verified, auto-login
                self._auto_login(email, password)
            else:
                self.show_login(prefill_email=email or "")

        prompt_screen = MasterPasswordPromptDialog(self, on_success)
        self.stackedWidget.addWidget(prompt_screen)
        self.stackedWidget.setCurrentWidget(prompt_screen)
        self._polish_screen(prompt_screen)

    def _auto_login(self, email, password):
        """Auto-login with saved credentials"""
        from GUI_Qt.workers.login_workers import PimboLoginWorker

        # Show loading
        self._show_loading(self.i18n.tr("loading.connecting"))

        # While the Selenium login thread runs, build the heavy screens so
        # switching later doesn't stutter.
        try:
            self.start_screen_preload()
        except Exception:
            pass

        # Start auto-login worker
        worker = PimboLoginWorker(
            email,
            password,
            self.settings.get_browser_choice() or "Chrome",
            self.credential_manager,
            self.i18n.tr,
        )

        def on_complete(success, _message, driver):
            if success:
                self.current_user = email
                self.driver = driver
                self.credential_manager.create_session(email, password)
                self.show_main()
            else:
                try:
                    self.cancel_screen_preload()
                except Exception:
                    pass
                self.show_login(
                    prefill_email=email,
                    saved_login_failed=True,
                )

        worker.result.connect(on_complete)
        worker.start()
        self._auto_login_worker = worker  # Keep reference

    def show_login(self, prefill_email: str = "", prefill_password: str = "", saved_login_failed: bool = False):
        """Show login screen"""
        from GUI_Qt.screens.LoginScreen import LoginScreen

        self._set_authenticated_shell_visible(False)
        if not self.login_screen:
            self.login_screen = LoginScreen(self)

        if self.stackedWidget.indexOf(self.login_screen) < 0:
            self.stackedWidget.addWidget(self.login_screen)
        self.stackedWidget.setCurrentWidget(self.login_screen)
        self._polish_screen(self.login_screen)
        try:
            self.login_screen.prefill_credentials(prefill_email, prefill_password)
            if saved_login_failed:
                self.login_screen.show_saved_login_failed_message()
        except Exception:
            pass

    def show_main(self):
        """Show main application with navigation"""
        from GUI_Qt.widgets.TopBar import TopBar
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QStackedWidget

        # Create top bar if not exists
        if not self.top_bar:
            self.top_bar = TopBar(
                self._get_topbar_user_text(),
                self.reconnect_browser,
                self.logout,
                self.i18n.tr,
                self,
                on_account=lambda: self.open_route("account"),
                on_settings=lambda: self.open_route("settings"),
                on_activity=lambda: self.open_route("activity"),
            )
            self.operation_tracker.runningCountChanged.connect(
                self.top_bar.update_running_jobs
            )
            self.top_bar.update_running_jobs(self.operation_tracker.running_count())
        else:
            try:
                self.top_bar.update_user(self._get_topbar_user_text())
            except Exception:
                pass

        # Build the authenticated shell once. Recreating it after every logout
        # leaked stacked widgets and discarded the current page state.
        if self._main_container is None:
            self._main_container = QWidget()
            self._main_container.setObjectName("mainContainer")
            main_layout = QVBoxLayout(self._main_container)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(0)
            main_layout.addWidget(self.top_bar)

            self.content_stack = QStackedWidget()
            self.content_stack.setObjectName("contentStack")
            main_layout.addWidget(self.content_stack, 1)
            self.stackedWidget.addWidget(self._main_container)

        # Apply background colors to containers
        from qfluentwidgets import isDarkTheme
        is_dark = isDarkTheme()
        bg_color = get_surface_color(is_dark, 'canvas')

        self._main_container.setStyleSheet(f"""
            #mainContainer {{
                background-color: {bg_color};
            }}
        """)
        self.content_stack.setStyleSheet(f"""
            #contentStack {{
                background-color: {bg_color};
            }}
        """)

        # ``FluentWindow`` uses an animated stack. Its default pop-out mode
        # leaves the loading widget as current until the animation finishes,
        # so revealing navigation immediately would expose two UI states at
        # once. Pop the authenticated shell in instead; this changes the
        # current widget synchronously before navigation becomes visible.
        self.stackedWidget.setCurrentWidget(self._main_container, popOut=False)
        if self._loading_widget is not None:
            self._loading_widget.hide()

        # Show navigation bar after the loading transition has been suppressed.
        self._set_authenticated_shell_visible(True)

        # If any screens were pre-constructed before content_stack existed, add them now.
        self._add_created_screens_to_stack()

        # Restore the last authenticated route when it is still registered.
        self._current_route = None
        saved_route = str(self.settings.get("last_authenticated_route", "upload") or "upload")
        self.open_route(saved_route if saved_route in self.ROUTES else "upload")
        self._sync_navigation_for_width(force=True)
        apply_accessibility_defaults(self._main_container)

        # Optional: check for updates after the UI is visible
        self._schedule_update_check()

    def _schedule_update_check(self) -> None:
        self.update_service.schedule()

    def check_for_updates(self, interactive: bool = True) -> None:
        self.update_service.check(interactive=interactive)

    def _download_and_install_update(self, manifest) -> None:
        self.update_service.download_and_install(manifest)

    def on_login_success(self, email, driver):
        """Called when login succeeds"""
        self.current_user = email
        self.driver = driver

        # Create session if login screen has password
        if hasattr(self, 'login_screen') and self.login_screen:
            password = getattr(self.login_screen, 'password', None)
            if password:
                self.credential_manager.create_session(email, password)

                # Persist encrypted credentials if master password is available
                master = self.get_unlocked_master_password(parent=self.login_screen)
                if master:
                    try:
                        self.credential_manager.save_credentials(email, password, master)
                    except Exception:
                        pass

        self.show_main()

    def _get_topbar_user_text(self) -> str:
        """Return what the top bar should display for the current user."""
        email = self.current_user or ""
        try:
            display_name = (self.settings.get('display_name', '') or '').strip()
        except Exception:
            display_name = ''
        if display_name:
            return display_name
        # Never show full email in the UI; fallback to local-part.
        if email and "@" in email:
            return (email.split("@", 1)[0] or "").strip()
        return email

    def refresh_topbar_user(self) -> None:
        """Refresh top bar label after settings changes."""
        if getattr(self, 'top_bar', None):
            try:
                self.top_bar.update_user(self._get_topbar_user_text())
            except Exception:
                pass

    def _is_driver_alive(self) -> bool:
        """Best-effort check whether the current Selenium driver is still usable."""
        if not self.driver:
            return False
        try:
            _ = self.driver.current_url
            return True
        except Exception:
            try:
                self.driver = None
            except Exception:
                pass
            return False

    def reconnect_browser(self):
        """Recreate Selenium driver and re-login using the 24h session, if available."""
        from qfluentwidgets import InfoBar, InfoBarPosition
        from PySide6.QtCore import Qt
        from Database.SessionManager import SessionManager
        from GUI_Qt.workers.login_workers import PimboLoginWorker

        if self._is_driver_alive():
            InfoBar.success(
                title=self.i18n.tr("topbar.reconnect.ok.title"),
                content=self.i18n.tr("topbar.reconnect.ok.content"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self,
            )
            return

        try:
            email, password = SessionManager(self.db).get_credentials_from_session()
        except Exception as error:
            email, password = "", ""
            session_error = str(error)
        else:
            session_error = ""
        if not (email and password):
            InfoBar.error(
                title=self.i18n.tr("topbar.reconnect.title"),
                content=session_error or self.i18n.tr("topbar.reconnect.no_session"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self,
            )
            return

        worker = PimboLoginWorker(
            email,
            password,
            self.settings.get_browser_choice() or "Chrome",
            self.credential_manager,
            self.i18n.tr,
        )

        def _done(success: bool, message: str, driver):
            if success:
                self.driver = driver
                self.current_user = email
                self.refresh_topbar_user()
                InfoBar.success(
                    title=self.i18n.tr("topbar.reconnect.title"),
                    content=message,
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=2500,
                    parent=self,
                )
            else:
                if message == self.i18n.tr("login.invalid_credentials"):
                    message = self.i18n.tr("topbar.reconnect.login_failed")
                InfoBar.error(
                    title=self.i18n.tr("topbar.reconnect.title"),
                    content=message,
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=4000,
                    parent=self,
                )

        worker.result.connect(_done)
        worker.start()
        self._reconnect_worker = worker

    def logout(self):
        """Logout and return to login"""
        if not self._can_leave_current_screen():
            self._restore_current_navigation_selection()
            return
        if not self._confirm_stop_active_work():
            return
        if not self._stop_orbea_automation_for_shutdown():
            InfoBar.warning(
                title=self.i18n.tr("orbea.shutdown.title"),
                content=self.i18n.tr("orbea.shutdown.wait"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )
            return
        if not self._stop_background_work():
            InfoBar.warning(
                title=self.i18n.tr("shutdown.wait.title"),
                content=self.i18n.tr("shutdown.wait.content"),
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )
            return
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
        self.current_user = None
        self._current_route = None

        # Hide navigation bar
        self._set_authenticated_shell_visible(False)

        self.show_login()

    def _stop_orbea_automation_for_shutdown(self, wait_ms: int = 5000) -> bool:
        """Ask the Orbea worker to checkpoint before its shared driver is closed."""
        screen = getattr(self, "orbea_screen", None)
        if screen is None or not hasattr(screen, "shutdown"):
            return True
        try:
            return bool(screen.shutdown(wait_ms=wait_ms))
        except Exception as error:
            try:
                self.logger.error(
                    "OrbeaAutomation",
                    "Could not stop Orbea automation cleanly",
                    exception=error,
                )
            except Exception:
                pass
            return False

    def _iter_background_workers(self, include_orbea: bool = True):
        yield from self.shutdown_service.iter_workers(include_orbea=include_orbea)

    def _confirm_stop_active_work(self) -> bool:
        return self.shutdown_service.confirm_stop()

    def _stop_background_work(self, wait_ms: int = 5000) -> bool:
        spotify = getattr(self, "spotify_screen", None)
        if spotify is not None and hasattr(spotify, "shutdown"):
            try:
                if not spotify.shutdown(wait_ms=wait_ms):
                    return False
            except Exception:
                return False
        return self.shutdown_service.stop_workers(wait_ms=wait_ms)

    def closeEvent(self, event):
        """Checkpoint long-running automation before closing application resources."""
        if not self._can_leave_current_screen():
            event.ignore()
            return
        if not self._confirm_stop_active_work():
            event.ignore()
            return
        try:
            snapshot = self.earnings_manager.timer_snapshot()
        except Exception:
            snapshot = None
        if snapshot is not None and snapshot.status == "running":
            dialog = QMessageBox(self)
            dialog.setWindowTitle(self.i18n.tr("earnings.exit.title"))
            dialog.setText(self.i18n.tr("earnings.exit.body"))
            keep_button = dialog.addButton(
                self.i18n.tr("earnings.exit.keep"), QMessageBox.ButtonRole.AcceptRole
            )
            pause_button = dialog.addButton(
                self.i18n.tr("earnings.exit.pause"), QMessageBox.ButtonRole.DestructiveRole
            )
            cancel_button = dialog.addButton(
                self.i18n.tr("common.cancel"), QMessageBox.ButtonRole.RejectRole
            )
            dialog.setDefaultButton(pause_button)
            dialog.exec()
            clicked = dialog.clickedButton()
            if clicked is cancel_button:
                event.ignore()
                return
            if clicked is pause_button:
                try:
                    self.earnings_manager.pause_session()
                except Exception:
                    event.ignore()
                    return
            # Keep-running deliberately leaves the persisted segment open.  On
            # next launch elapsed wall time is recovered from its UTC timestamp.
            _ = keep_button
        if not self._stop_orbea_automation_for_shutdown():
            event.ignore()
            return
        if not self._stop_background_work():
            InfoBar.warning(
                title=self.i18n.tr("shutdown.wait.title"),
                content=self.i18n.tr("shutdown.wait.content"),
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )
            event.ignore()
            return
        try:
            if self.driver:
                self.driver.quit()
                self.driver = None
        except Exception:
            pass
        try:
            self._save_window_state()
        except Exception:
            pass
        try:
            self.db.close()
        except Exception:
            pass
        super().closeEvent(event)

    def prompt_earning_items(self, items, parent=None) -> int:
        """Show one review dialog for verified saved products."""
        try:
            from GUI_Qt.screens.EarningsScreen import UploadEarningsDialog

            dialog_parent = parent if parent is not None else self
            dialog = UploadEarningsDialog(self.earnings_manager, list(items or []), dialog_parent)
            if not dialog.items or not dialog.exec():
                return 0
            count = dialog.save_entries()
            if self.earnings_screen is not None:
                self.earnings_screen.refresh_all()
            InfoBar.success(
                title=self.i18n.tr("earnings.upload.added.title"),
                content=self.i18n.tr("earnings.upload.added.body", count=count),
                parent=dialog_parent,
                position=InfoBarPosition.TOP,
                duration=3500,
            )
            return count
        except Exception as error:
            try:
                InfoBar.error(
                    title=self.i18n.tr("earnings.upload.error.title"),
                    content=str(error),
                    parent=parent if parent is not None else self,
                    position=InfoBarPosition.TOP,
                    duration=5000,
                )
            except Exception:
                pass
            return 0

    def start_batch_processing(self, items):
        """
        Start batch processing with collected items

        Args:
            items: List of {brand, code, url} dicts
        """
        # Switch to upload screen
        self.open_route("upload")

        # Trigger batch processing in upload screen
        if self.upload_screen:
            self.upload_screen.show_batch_processing(items)

    def _apply_saved_theme(self):
        """Apply saved theme from settings"""
        from qfluentwidgets import isDarkTheme
        from GUI_Qt.styles.global_styles import get_global_stylesheet
        from GUI_Qt.styles.theme_config import set_mode_aware_theme

        theme = self.settings.get('theme', 'light')
        desired_dark = theme == 'dark'
        # QFluentWidgets performs a full registered-widget style refresh even
        # when setTheme() receives the already-active theme. Avoid that costly
        # no-op, especially when this helper is called after Settings preview.
        if desired_dark != isDarkTheme():
            set_mode_aware_theme(desired_dark, lazy=True)

        # Apply global stylesheet for consistent styling (set at app-level so it
        # reliably affects all widgets/screens).
        try:
            app = QApplication.instance()
            stylesheet = get_global_stylesheet()
            if app is not None:
                if app.styleSheet() != stylesheet:
                    app.setStyleSheet(stylesheet)
            else:
                if self.styleSheet() != stylesheet:
                    self.setStyleSheet(stylesheet)
        except Exception:
            stylesheet = get_global_stylesheet()
            if self.styleSheet() != stylesheet:
                self.setStyleSheet(stylesheet)

    def update_container_backgrounds(self):
        """Update main container and content stack backgrounds when theme changes"""
        from qfluentwidgets import isDarkTheme
        if getattr(self, 'content_stack', None) is None:
            return

        is_dark = isDarkTheme()
        bg_color = get_surface_color(is_dark, 'canvas')

        # Find and update main container
        for i in range(self.stackedWidget.count()):
            widget = self.stackedWidget.widget(i)
            if widget.objectName() == "mainContainer":
                widget.setStyleSheet(f"""
                    #mainContainer {{
                        background-color: {bg_color};
                    }}
                """)
                break

        # Update content stack
        if hasattr(self, 'content_stack'):
            self.content_stack.setStyleSheet(f"""
                #contentStack {{
                    background-color: {bg_color};
                }}
            """)

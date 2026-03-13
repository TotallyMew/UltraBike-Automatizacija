"""
Main Application Window
Manages navigation, state, and screen switching
"""

from PySide6.QtWidgets import QWidget, QStackedWidget, QHBoxLayout, QApplication, QLineEdit
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor
from qfluentwidgets import FluentWindow, NavigationItemPosition, FluentIcon, MessageBox, InfoBar, InfoBarPosition

import queue
from Utilities.ErrorManager import ErrorManager

from Config.BrowserConfig.BrowserManager import BrowserManager
from Config.LoginConfig.CredentialManager import CredentialManager
from Database.DatabaseManager import DatabaseManager
from Database.SettingsManager import SettingsManager
from Utilities.Logger import Logger
from Utilities.Version import get_app_version
from Utilities.Updater import fetch_update_manifest, is_newer_version, download_to_temp, sha256_file, run_installer
from Utilities.AppPaths import get_default_db_path, get_data_dir
from GUI_Qt.styles.theme_config import FONTS
from GUI_Qt.styles.theme_config import COLORS
from GUI_Qt.styles.theme_config import SPACING
from GUI_Qt.styles.theme_config import RADII
from GUI_Qt.styles.theme_config import PADDINGS
from GUI_Qt.styles.theme_config import SIZES
from GUI_Qt.styles.screen_theme import NAV_VERSION_MARGINS, NAV_VERSION_SPACING
from GUI_Qt.i18n import I18nManager, translate


class MainWindow(FluentWindow):
    """Main application window with Fluent Design navigation"""

    def __init__(self):
        super().__init__()

        # Initialize backend managers
        self.driver = None
        self.current_user = None
        self.logger = Logger()

        # Database setup
        first_run = False
        try:
            first_run = not get_default_db_path().exists()
        except Exception:
            first_run = False

        self.db = DatabaseManager()
        self.settings = SettingsManager(self.db)
        self.credential_manager = CredentialManager(self.db)

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

        # Set application font
        app_font = QFont()
        app_font.setFamily("Segoe UI")
        app_font.setPointSize(10)
        QApplication.instance().setFont(app_font)

        # Center window on screen
        self._center_on_screen()

        # Initialize screens (lazy loading)
        self.login_screen = None

        # Cached for current run after master unlock/setup
        self._unlocked_master_password = None
        self.upload_screen = None
        self.batch_upload_screen = None
        self.history_screen = None
        self._full_history_screen = None  # Full detailed history view (accessed from Analytics)
        self.translations_screen = None
        self.descriptions_screen = None
        self.batch_descriptions_screen = None
        self.batch_titles_screen = None
        self.folder_creator_screen = None
        self.basso_images_screen = None
        self.pinarello_images_screen = None
        self.account_screen = None
        self.settings_screen = None
        self.info_screen = None
        self.gold_standard_table_screen = None

        # Top bar reference
        self.top_bar = None

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

        # Ensure the frameless title bar stays readable across themes
        try:
            from qfluentwidgets import qconfig
            qconfig.themeChangedFinished.connect(self._on_global_theme_changed)
        except Exception:
            pass
        self._apply_titlebar_theme()

        # Apply translations to any static UI created above
        self._retranslate_ui(self.i18n.language.code)

        # Hide navigation until logged in
        self.navigationInterface.setVisible(False)

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
            1,  # Batch Upload
            2,  # History
            3,  # Translations
            4,  # Descriptions
            5,  # Batch Descriptions
        ]

        def _step() -> None:
            if self._screen_preload_cancelled:
                self._screen_preload_active = False
                self._screen_preload_queue = []
                return

            if not self._screen_preload_queue:
                self._screen_preload_active = False
                return

            index = self._screen_preload_queue.pop(0)
            try:
                self._ensure_screen_created(index)
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
                (getattr(self, 'batch_upload_screen', None), "nav.batch"),
                (getattr(self, 'history_screen', None), "nav.analytics"),
                (getattr(self, 'translations_screen', None), "nav.translations"),
                (getattr(self, 'descriptions_screen', None), "nav.descriptions"),
                (getattr(self, 'batch_descriptions_screen', None), "nav.batch_descriptions"),
                (getattr(self, 'batch_titles_screen', None), "nav.batch_titles"),
                (getattr(self, 'folder_creator_screen', None), "nav.folders"),
                (getattr(self, 'basso_images_screen', None), "nav.basso_images"),
                (getattr(self, 'pinarello_images_screen', None), "nav.pinarello_images"),
                (getattr(self, 'account_screen', None), "nav.account"),
                (getattr(self, 'settings_screen', None), "nav.settings"),
                (getattr(self, 'info_screen', None), "nav.info"),
            ]

            for screen, key in mapping:
                if screen is not None:
                    self._add_screen_to_stack(screen, self.i18n.tr(key))
        except Exception:
            pass

    def _ensure_screen_created(self, index: int):
        """Create a screen if needed and add it to the content stack when possible.

        Screen mapping (reorganized):
        0: Upload
        1: Batch Upload
        2: Descriptions
        3: Batch Descriptions
        4: Batch Titles
        5: Folder Creator
        6: Translations
        7: Basso Images
        8: Pinarello Images
        9: History
        10: Account
        11: Settings
        12: Info
        13: Gold Standard Table
        """
        if index == 0:  # Upload
            if not self.upload_screen:
                from GUI_Qt.screens.UploadScreen import UploadScreen
                self.upload_screen = UploadScreen(self)
            self._add_screen_to_stack(self.upload_screen, self.i18n.tr("nav.upload"))
            return self.upload_screen

        if index == 1:  # Batch Upload
            if not self.batch_upload_screen:
                from GUI_Qt.screens.BatchUploadScreen import BatchUploadScreen
                self.batch_upload_screen = BatchUploadScreen(self)
            self._add_screen_to_stack(self.batch_upload_screen, self.i18n.tr("nav.batch"))
            return self.batch_upload_screen

        if index == 2:  # Descriptions
            if not self.descriptions_screen:
                from GUI_Qt.screens.DescriptionsScreen import DescriptionsScreen
                self.descriptions_screen = DescriptionsScreen(self)
            self._add_screen_to_stack(self.descriptions_screen, self.i18n.tr("nav.descriptions"))
            return self.descriptions_screen

        if index == 3:  # Batch Descriptions
            if not self.batch_descriptions_screen:
                from GUI_Qt.screens.BatchDescriptionsScreen import BatchDescriptionsScreen
                self.batch_descriptions_screen = BatchDescriptionsScreen(self)
            self._add_screen_to_stack(self.batch_descriptions_screen, self.i18n.tr("nav.batch_descriptions"))
            return self.batch_descriptions_screen

        if index == 4:  # Batch Titles
            if not self.batch_titles_screen:
                from GUI_Qt.screens.BatchTitlesScreen import BatchTitlesScreen
                self.batch_titles_screen = BatchTitlesScreen(self)
            self._add_screen_to_stack(self.batch_titles_screen, self.i18n.tr("nav.batch_titles"))
            return self.batch_titles_screen

        if index == 5:  # Folder Creator
            if not self.folder_creator_screen:
                from GUI_Qt.screens.FolderCreatorScreen import FolderCreatorScreen
                self.folder_creator_screen = FolderCreatorScreen(self)
            self._add_screen_to_stack(self.folder_creator_screen, self.i18n.tr("nav.folders"))
            return self.folder_creator_screen

        if index == 6:  # Translations
            if not self.translations_screen:
                from GUI_Qt.screens.TranslationsScreen import TranslationsScreen
                self.translations_screen = TranslationsScreen(self)
            self._add_screen_to_stack(self.translations_screen, self.i18n.tr("nav.translations"))
            return self.translations_screen

        if index == 7:  # Basso Images
            if not self.basso_images_screen:
                from GUI_Qt.screens.BassoImageScreen import BassoImageScreen
                self.basso_images_screen = BassoImageScreen(self)
            self._add_screen_to_stack(self.basso_images_screen, self.i18n.tr("nav.basso_images"))
            return self.basso_images_screen

        if index == 8:  # Pinarello Images
            if not self.pinarello_images_screen:
                from GUI_Qt.screens.PinarelloImageScreen import PinarelloImageScreen
                self.pinarello_images_screen = PinarelloImageScreen(self)
            self._add_screen_to_stack(self.pinarello_images_screen, self.i18n.tr("nav.pinarello_images"))
            return self.pinarello_images_screen

        if index == 9:  # Analytics (formerly History)
            if not self.history_screen:
                from GUI_Qt.screens.AnalyticsScreen import AnalyticsScreen
                self.history_screen = AnalyticsScreen(self)
            self._add_screen_to_stack(self.history_screen, self.i18n.tr("nav.analytics"))
            return self.history_screen

        if index == 10:  # Account
            if not self.account_screen:
                from GUI_Qt.screens.AccountScreen import AccountScreen
                self.account_screen = AccountScreen(self)
            self._add_screen_to_stack(self.account_screen, self.i18n.tr("nav.account"))
            return self.account_screen

        if index == 11:  # Settings
            if not self.settings_screen:
                from GUI_Qt.screens.SettingsScreen import SettingsScreen
                self.settings_screen = SettingsScreen(self)
            self._add_screen_to_stack(self.settings_screen, self.i18n.tr("nav.settings"))
            return self.settings_screen

        if index == 12:  # Info
            if not self.info_screen:
                from GUI_Qt.screens.InfoScreen import InfoScreen
                self.info_screen = InfoScreen(self)
            self._add_screen_to_stack(self.info_screen, self.i18n.tr("nav.info"))
            return self.info_screen

        if index == 13:  # Gold Standard Table
            if not self.gold_standard_table_screen:
                from GUI_Qt.screens.GoldStandardTableScreen import GoldStandardTableScreen
                self.gold_standard_table_screen = GoldStandardTableScreen(self)
            self._add_screen_to_stack(self.gold_standard_table_screen, "Gold Table")
            return self.gold_standard_table_screen

        return None

    def _init_prompt_handling(self):
        """Initialize a request queue polled by the GUI to answer background prompt requests."""
        self._prompt_queue = queue.Queue()
        ErrorManager.set_prompt_queue(self._prompt_queue)

        # Timer to poll the queue in the GUI thread
        self._prompt_timer = QTimer(self)
        self._prompt_timer.setInterval(150)  # 150ms polling
        self._prompt_timer.timeout.connect(self._process_prompt_queue)
        self._prompt_timer.start()

    def _process_prompt_queue(self):
        """Process pending prompt requests from background threads."""
        try:
            while not self._prompt_queue.empty():
                prompt_type, operation_name, resp_q = self._prompt_queue.get_nowait()

                if prompt_type == "retry":
                    # Provide a textbox to optionally enter a new code to retry with
                    dialog = MessageBox(
                        self.i18n.tr("prompt.retry.title"),
                        "",
                        self
                    )
                    # Replace default content with input field
                    try:
                        dialog.textLayout.removeWidget(dialog.contentLabel)
                        dialog.contentLabel.deleteLater()
                    except Exception:
                        pass
                    input_widget = QLineEdit()
                    input_widget.setPlaceholderText(self.i18n.tr("prompt.retry.placeholder"))
                    # Style input to match Fluent color scheme
                    input_widget.setStyleSheet(
                        f"background-color: {COLORS['lavender_grey']}; color: white; padding: {PADDINGS['input']}; border-radius: {RADII['sm']}px;"
                    )
                    input_widget.setMinimumWidth(SIZES['panel_min_width'])
                    dialog.textLayout.addWidget(input_widget)
                    dialog.yesButton.setText(self.i18n.tr("prompt.retry.yes"))
                    dialog.cancelButton.setText(self.i18n.tr("prompt.retry.cancel"))

                    # Non-blocking: show dialog and push result to resp_q when closed
                    def _on_finished(result_code, rq=resp_q, iw=input_widget):
                        try:
                            from PySide6.QtWidgets import QDialog
                            if result_code == QDialog.Accepted:
                                new_code = iw.text().strip()
                                if new_code:
                                    rq.put(new_code)
                                else:
                                    rq.put(True)
                            else:
                                rq.put(False)
                        except Exception:
                            rq.put(False)

                    dialog.finished.connect(_on_finished)
                    dialog.show()

                elif prompt_type == "continue":
                    dialog = MessageBox(
                        self.i18n.tr("prompt.continue.title"),
                        self.i18n.tr("prompt.continue.content"),
                        self
                    )
                    dialog.yesButton.setText(self.i18n.tr("prompt.continue.yes"))
                    dialog.cancelButton.setText(self.i18n.tr("prompt.continue.no"))
                    result = bool(dialog.exec())
                    resp_q.put(result)

                elif prompt_type == "exit_or_retry":
                    dialog = MessageBox(
                        self.i18n.tr("prompt.exit_or_retry.title"),
                        self.i18n.tr("prompt.exit_or_retry.content"),
                        self
                    )
                    dialog.yesButton.setText(self.i18n.tr("prompt.exit_or_retry.retry"))
                    dialog.cancelButton.setText(self.i18n.tr("prompt.exit_or_retry.exit"))
                    if dialog.exec():
                        resp_q.put("retry")
                    else:
                        resp_q.put("exit")
                else:
                    # Unknown prompt type
                    resp_q.put(False)

        except Exception:
            # Don't let prompt handling crash the GUI
            pass

    def _center_on_screen(self):
        """Center the window on the screen"""
        from PySide6.QtGui import QScreen
        screen = QScreen.availableGeometry(QApplication.primaryScreen())
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def _init_navigation(self):
        """Initialize navigation sidebar"""

        # Keep references to nav items so we can update text when language changes
        self._nav_items = {}

        # === TOP SECTION - Primary Operations ===
        # Upload operations
        self._nav_items["upload"] = self.navigationInterface.addItem(
            routeKey="upload",
            icon=FluentIcon.CLOUD_DOWNLOAD,
            text=self.i18n.tr("nav.upload"),
            onClick=lambda: self._switch_to_screen(0),
            position=NavigationItemPosition.TOP
        )

        self._nav_items["batch"] = self.navigationInterface.addItem(
            routeKey="batch",
            icon=FluentIcon.SYNC,
            text=self.i18n.tr("nav.batch"),
            onClick=lambda: self._switch_to_screen(1),
            position=NavigationItemPosition.TOP
        )

        # Content management
        self._nav_items["descriptions"] = self.navigationInterface.addItem(
            routeKey="descriptions",
            icon=FluentIcon.EDIT,
            text=self.i18n.tr("nav.descriptions"),
            onClick=lambda: self._switch_to_screen(2),
            position=NavigationItemPosition.TOP
        )

        self._nav_items["batch_descriptions"] = self.navigationInterface.addItem(
            routeKey="batch_descriptions",
            icon=FluentIcon.TAG,
            text=self.i18n.tr("nav.batch_descriptions"),
            onClick=lambda: self._switch_to_screen(3),
            position=NavigationItemPosition.TOP
        )

        self._nav_items["batch_titles"] = self.navigationInterface.addItem(
            routeKey="batch_titles",
            icon=FluentIcon.EDIT,
            text=self.i18n.tr("nav.batch_titles"),
            onClick=lambda: self._switch_to_screen(4),
            position=NavigationItemPosition.TOP
        )

        # Utilities
        self._nav_items["folders"] = self.navigationInterface.addItem(
            routeKey="folders",
            icon=FluentIcon.FOLDER,
            text=self.i18n.tr("nav.folders"),
            onClick=lambda: self._switch_to_screen(5),
            position=NavigationItemPosition.TOP
        )

        self._nav_items["translations"] = self.navigationInterface.addItem(
            routeKey="translations",
            icon=FluentIcon.LANGUAGE,
            text=self.i18n.tr("nav.translations"),
            onClick=lambda: self._switch_to_screen(6),
            position=NavigationItemPosition.TOP
        )

        # Brand-specific tools
        self._nav_items["basso_images"] = self.navigationInterface.addItem(
            routeKey="basso_images",
            icon=FluentIcon.PHOTO,
            text=self.i18n.tr("nav.basso_images"),
            onClick=lambda: self._switch_to_screen(7),
            position=NavigationItemPosition.TOP
        )

        self._nav_items["pinarello_images"] = self.navigationInterface.addItem(
            routeKey="pinarello_images",
            icon=FluentIcon.ALBUM,
            text=self.i18n.tr("nav.pinarello_images"),
            onClick=lambda: self._switch_to_screen(8),
            position=NavigationItemPosition.TOP
        )

        self._nav_items["history"] = self.navigationInterface.addItem(
            routeKey="history",
            icon=FluentIcon.PIE_SINGLE,
            text=self.i18n.tr("nav.analytics"),
            onClick=lambda: self._switch_to_screen(9),
            position=NavigationItemPosition.TOP
        )

        self._nav_items["gold_table"] = self.navigationInterface.addItem(
            routeKey="gold_table",
            icon=FluentIcon.DICTIONARY,
            text="Gold Table",
            onClick=lambda: self._switch_to_screen(13),
            position=NavigationItemPosition.TOP
        )

        # === BOTTOM SECTION - System ===
        self._nav_items["account"] = self.navigationInterface.addItem(
            routeKey="account",
            icon=FluentIcon.PEOPLE,
            text=self.i18n.tr("nav.account"),
            onClick=lambda: self._switch_to_screen(10),
            position=NavigationItemPosition.BOTTOM
        )

        self._nav_items["settings"] = self.navigationInterface.addItem(
            routeKey="settings",
            icon=FluentIcon.SETTING,
            text=self.i18n.tr("nav.settings"),
            onClick=lambda: self._switch_to_screen(11),
            position=NavigationItemPosition.BOTTOM
        )

        self._nav_items["info"] = self.navigationInterface.addItem(
            routeKey="info",
            icon=FluentIcon.INFO,
            text=self.i18n.tr("nav.info"),
            onClick=lambda: self._switch_to_screen(12),
            position=NavigationItemPosition.BOTTOM
        )

        # Version label in navigation footer (under everything)
        try:
            from PySide6.QtWidgets import QHBoxLayout
            from qfluentwidgets import BodyLabel, IconWidget
            from qfluentwidgets.components.navigation.navigation_widget import NavigationWidget
            from Utilities.Version import get_app_version

            self.navigationInterface.addSeparator(NavigationItemPosition.BOTTOM)

            version_widget = NavigationWidget(isSelectable=False)
            version_layout = QHBoxLayout(version_widget)
            version_layout.setContentsMargins(*NAV_VERSION_MARGINS)
            version_layout.setSpacing(NAV_VERSION_SPACING)

            version_icon = IconWidget()
            version_icon.setIcon(FluentIcon.APPLICATION)
            version_icon.setFixedSize(SIZES['icon_xs'], SIZES['icon_xs'])
            try:
                version_icon.setStyleSheet(f"color: {COLORS['text_secondary']};")
            except Exception:
                pass
            version_layout.addWidget(version_icon, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

            version_label = BodyLabel(get_app_version('1.1.0'))
            version_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            try:
                version_label.setStyleSheet(
                    f"color: {COLORS['text_secondary']};"
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

    def apply_language_preview(self, lang_code: str) -> None:
        """Temporarily translate app chrome without changing persisted language.

        Intended for Settings preview. This does NOT modify self.i18n.language.
        """
        try:
            self.setWindowTitle(translate(lang_code, "app.title"))
            self._set_nav_item_text("upload", translate(lang_code, "nav.upload"))
            self._set_nav_item_text("batch", translate(lang_code, "nav.batch"))
            self._set_nav_item_text("history", translate(lang_code, "nav.analytics"))
            self._set_nav_item_text("translations", translate(lang_code, "nav.translations"))
            self._set_nav_item_text("descriptions", translate(lang_code, "nav.descriptions"))
            self._set_nav_item_text("batch_descriptions", translate(lang_code, "nav.batch_descriptions"))
            self._set_nav_item_text("folders", translate(lang_code, "nav.folders"))
            self._set_nav_item_text("basso_images", translate(lang_code, "nav.basso_images"))
            self._set_nav_item_text("pinarello_images", translate(lang_code, "nav.pinarello_images"))
            self._set_nav_item_text("account", translate(lang_code, "nav.account"))
            self._set_nav_item_text("settings", translate(lang_code, "nav.settings"))
            self._set_nav_item_text("info", translate(lang_code, "nav.info"))
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

    def _set_nav_item_text(self, route_key: str, text: str) -> None:
        """Best-effort: update a navigation item's label text at runtime."""
        item = getattr(self, "_nav_items", {}).get(route_key)
        if item is not None and hasattr(item, "setText"):
            try:
                item.setText(text)
                return
            except Exception:
                pass

        nav = getattr(self, "navigationInterface", None)
        if nav is not None and hasattr(nav, "setItemText"):
            try:
                nav.setItemText(route_key, text)
            except Exception:
                pass

    def _retranslate_ui(self, _lang_code: str | None = None) -> None:
        """Update static UI strings when the application language changes."""
        try:
            self.setWindowTitle(self.i18n.tr("app.title"))

            self._set_nav_item_text("upload", self.i18n.tr("nav.upload"))
            self._set_nav_item_text("batch", self.i18n.tr("nav.batch"))
            self._set_nav_item_text("history", self.i18n.tr("nav.analytics"))
            self._set_nav_item_text("translations", self.i18n.tr("nav.translations"))
            self._set_nav_item_text("descriptions", self.i18n.tr("nav.descriptions"))
            self._set_nav_item_text("batch_descriptions", self.i18n.tr("nav.batch_descriptions"))
            self._set_nav_item_text("folders", self.i18n.tr("nav.folders"))
            self._set_nav_item_text("basso_images", self.i18n.tr("nav.basso_images"))
            self._set_nav_item_text("pinarello_images", self.i18n.tr("nav.pinarello_images"))
            self._set_nav_item_text("account", self.i18n.tr("nav.account"))
            self._set_nav_item_text("settings", self.i18n.tr("nav.settings"))
            self._set_nav_item_text("info", self.i18n.tr("nav.info"))

            # Notify screens if they implement live retranslation
            for screen in (
                getattr(self, "top_bar", None),
                getattr(self, "upload_screen", None),
                getattr(self, "batch_upload_screen", None),
                getattr(self, "history_screen", None),
                getattr(self, "translations_screen", None),
                getattr(self, "descriptions_screen", None),
                getattr(self, "batch_descriptions_screen", None),
                getattr(self, "batch_titles_screen", None),
                getattr(self, "folder_creator_screen", None),
                getattr(self, "basso_images_screen", None),
                getattr(self, "pinarello_images_screen", None),
                getattr(self, "account_screen", None),
                getattr(self, "settings_screen", None),
                getattr(self, "info_screen", None),
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
        # Make the navigation panel wider for better visibility
        self.navigationInterface.setExpandWidth(200)
        # Force navigation to stay expanded
        self.navigationInterface.expand(useAni=False)

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
            self.update_container_backgrounds()
        except Exception:
            pass
        self._apply_titlebar_theme()

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
                        self._titlebar_theme_deferred = False
                    except Exception:
                        pass
                    self._apply_titlebar_theme()

                QTimer.singleShot(0, _late_apply)
        except Exception:
            pass
    def _switch_to_screen(self, index):
        """Switch to a different screen"""
        screen = self._ensure_screen_created(index)
        if screen is not None:
            self._show_screen(screen)

    def _add_screen_to_stack(self, screen, name):
        """Add screen to content stack if not already added"""
        # Check if content_stack exists (after login)
        if not hasattr(self, 'content_stack'):
            return False

        # Check if screen already in stack
        for i in range(self.content_stack.count()):
            if self.content_stack.widget(i) == screen:
                return True

        # Add screen to stack
        self.content_stack.addWidget(screen)
        return True

    def _show_screen(self, screen):
        """Show a specific screen in content stack"""
        if not hasattr(self, 'content_stack'):
            return

        # Verify screen is in stack before trying to show it
        is_in_stack = False
        for i in range(self.content_stack.count()):
            if self.content_stack.widget(i) == screen:
                is_in_stack = True
                break

        if is_in_stack:
            self.content_stack.setCurrentWidget(screen)

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

        loading_widget = LoadingWidget(message, tr=self.i18n.tr)
        self.stackedWidget.addWidget(loading_widget)
        self.stackedWidget.setCurrentWidget(loading_widget)

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
            # Master password verified, auto-login
            self._auto_login(email, password)

        prompt_screen = MasterPasswordPromptDialog(self, on_success)
        self.stackedWidget.addWidget(prompt_screen)
        self.stackedWidget.setCurrentWidget(prompt_screen)

    def _auto_login(self, email, password):
        """Auto-login with saved credentials"""
        from GUI_Qt.widgets.LoadingWidget import LoadingWidget
        from PySide6.QtCore import QThread, Signal
        from Config.BrowserConfig.BrowserManager import BrowserManager
        from Config.LoginConfig.LoginHandler import LoginHandler

        class AutoLoginWorker(QThread):
            finished = Signal(bool, object)  # success, driver

            def __init__(self, email, password, settings, credential_manager):
                super().__init__()
                self.email = email
                self.password = password
                self.settings = settings
                self.credential_manager = credential_manager

            def run(self):
                try:
                    browser_choice = self.settings.get_browser_choice()
                    browser_manager = BrowserManager()
                    driver = browser_manager.setup_browser(
                        browser_choice,
                        retry_callback=lambda: False
                    )

                    if driver is None:
                        self.finished.emit(False, None)
                        return

                    login_handler = LoginHandler(driver, self.credential_manager)
                    success = login_handler.login(
                        credentials_callback=lambda: (self.email, self.password),
                        retry_callback=lambda: False,
                        max_attempts=1
                    )

                    if success:
                        self.finished.emit(True, driver)
                    else:
                        if driver:
                            driver.quit()
                        self.finished.emit(False, None)

                except Exception:
                    self.finished.emit(False, None)

        # Show loading
        self._show_loading(self.i18n.tr("loading.connecting"))

        # While the Selenium login thread runs, build the heavy screens so
        # switching later doesn't stutter.
        try:
            self.start_screen_preload()
        except Exception:
            pass

        # Start auto-login worker
        worker = AutoLoginWorker(email, password, self.settings, self.credential_manager)

        def on_complete(success, driver):
            if success:
                self.current_user = email
                self.driver = driver
                self.credential_manager.create_session(email, password)
                self.show_main()
            else:
                self.show_login()

        worker.finished.connect(on_complete)
        worker.start()
        self._auto_login_worker = worker  # Keep reference

    def show_login(self):
        """Show login screen"""
        from GUI_Qt.screens.LoginScreen import LoginScreen

        if not self.login_screen:
            self.login_screen = LoginScreen(self)

        self.stackedWidget.addWidget(self.login_screen)
        self.stackedWidget.setCurrentWidget(self.login_screen)

    def show_main(self):
        """Show main application with navigation"""
        from GUI_Qt.widgets.TopBar import TopBar
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QStackedWidget

        # Show navigation bar
        self.navigationInterface.setVisible(True)

        # Create top bar if not exists
        if not self.top_bar:
            self.top_bar = TopBar(self._get_topbar_user_text(), self.reconnect_browser, self.logout, self.i18n.tr, self)
        else:
            try:
                self.top_bar.update_user(self._get_topbar_user_text())
            except Exception:
                pass

        # Create main content container with top bar and content area
        main_container = QWidget()
        main_container.setObjectName("mainContainer")
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.top_bar)

        # Create our own stacked widget for content screens
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("contentStack")

        # Apply background colors to containers
        from qfluentwidgets import isDarkTheme
        from GUI_Qt.styles.theme_config import COLORS
        is_dark = isDarkTheme()
        bg_color = COLORS['space_indigo'] if is_dark else COLORS['platinum']

        main_container.setStyleSheet(f"""
            #mainContainer {{
                background-color: {bg_color};
            }}
        """)
        self.content_stack.setStyleSheet(f"""
            #contentStack {{
                background-color: {bg_color};
            }}
        """)

        main_layout.addWidget(self.content_stack, 1)

        # Add main container to FluentWindow's stackedWidget
        self.stackedWidget.addWidget(main_container)
        self.stackedWidget.setCurrentWidget(main_container)

        # If any screens were pre-constructed before content_stack existed, add them now.
        self._add_created_screens_to_stack()

        # Switch to upload screen by default
        self._switch_to_screen(0)

        # Optional: check for updates after the UI is visible
        self._schedule_update_check()

    def _schedule_update_check(self) -> None:
        if self._update_check_scheduled:
            return
        self._update_check_scheduled = True

        try:
            enabled = bool(self.settings.get('update_check_enabled', True))
        except Exception:
            enabled = True
        if not enabled:
            return

        try:
            url = (self.settings.get('update_manifest_url', '') or '').strip()
        except Exception:
            url = ''
        if not url:
            return

        QTimer.singleShot(2500, lambda: self.check_for_updates(interactive=False))

    def check_for_updates(self, interactive: bool = True) -> None:
        """Check update manifest and (if newer) prompt to download+install."""
        try:
            url = (self.settings.get('update_manifest_url', '') or '').strip()
        except Exception:
            url = ''
        if not url:
            return

        # If VERSION.txt is missing/corrupt, default low so updates still work.
        current = get_app_version('0.0.0')

        from PySide6.QtCore import QThread, Signal

        class _UpdateCheckWorker(QThread):
            finished = Signal(bool, object, str)  # ok, manifest, error

            def __init__(self, manifest_url: str):
                super().__init__()
                self.manifest_url = manifest_url

            def run(self):
                try:
                    manifest = fetch_update_manifest(self.manifest_url)
                    self.finished.emit(True, manifest, '')
                except Exception as e:
                    self.finished.emit(False, None, str(e))

        worker = _UpdateCheckWorker(url)

        def _on_checked(ok: bool, manifest, error: str):
            if not ok:
                if interactive:
                    InfoBar.error(
                        title=self.i18n.tr('update.error.title') if hasattr(self, 'i18n') else 'Update',
                        content=error or 'Failed to check for updates',
                        orient=Qt.Orientation.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP,
                        duration=4000,
                        parent=self,
                    )
                return

            if not is_newer_version(current, manifest.version):
                if interactive:
                    InfoBar.success(
                        title=self.i18n.tr('update.uptodate.title') if hasattr(self, 'i18n') else 'Update',
                        content=self.i18n.tr('update.uptodate.content') if hasattr(self, 'i18n') else 'You are up to date.',
                        orient=Qt.Orientation.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP,
                        duration=2500,
                        parent=self,
                    )
                return

            title = self.i18n.tr('update.available.title') if hasattr(self, 'i18n') else 'Update available'
            body = (self.i18n.tr('update.available.content', version=manifest.version)
                    if hasattr(self, 'i18n') else f'New version {manifest.version} is available. Download and install now?')
            if getattr(manifest, 'notes', None):
                body = f"{body}\n\n{manifest.notes}"

            dialog = MessageBox(title, body, self)
            dialog.yesButton.setText(self.i18n.tr('update.available.yes') if hasattr(self, 'i18n') else 'Update')
            dialog.cancelButton.setText(self.i18n.tr('update.available.no') if hasattr(self, 'i18n') else 'Later')
            if not dialog.exec():
                return

            self._download_and_install_update(manifest)

        worker.finished.connect(_on_checked)
        worker.start()
        self._update_worker = worker

    def _download_and_install_update(self, manifest) -> None:
        from PySide6.QtCore import QThread, Signal

        self._show_loading(self.i18n.tr('update.downloading') if hasattr(self, 'i18n') else 'Downloading update...')

        class _DownloadWorker(QThread):
            finished = Signal(bool, str, str)  # ok, path, error

            def __init__(self, m):
                super().__init__()
                self.m = m

            def run(self):
                try:
                    name = f"UltraBike_Automatizacija_Setup_{self.m.version}.exe"
                    path = download_to_temp(self.m.url, name)

                    # SHA256 verification is now mandatory (enforced in fetch_update_manifest)
                    # Always verify downloaded file matches manifest hash
                    actual = sha256_file(path)
                    if actual.lower() != str(self.m.sha256).lower():
                        raise RuntimeError('Downloaded update failed SHA256 verification')

                    self.finished.emit(True, path, '')
                except Exception as e:
                    self.finished.emit(False, '', str(e))

        worker = _DownloadWorker(manifest)

        def _done(ok: bool, path: str, error: str):
            if not ok:
                self._show_loading('')
                InfoBar.error(
                    title=self.i18n.tr('update.error.title') if hasattr(self, 'i18n') else 'Update',
                    content=error or 'Failed to download update',
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=5000,
                    parent=self,
                )
                return

            try:
                # Updates should be unattended: no destination/shortcut prompts and no immediate
                # post-install launch (which can race with AV/file locks and cause transient DLL errors).
                run_installer(path, silent=True)

                # CRITICAL FIX: Wait for installer to launch and UAC dialog to appear
                # Without this delay, app quits before UAC completes, causing installer to fail
                # This ensures the installer process is stable before parent app exits
                import time
                time.sleep(5.0)  # 5 seconds allows UAC dialog to appear and user to respond

            except Exception as e:
                InfoBar.error(
                    title=self.i18n.tr('update.error.title') if hasattr(self, 'i18n') else 'Update',
                    content=str(e),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=5000,
                    parent=self,
                )
                return

            # Exit so installer can replace files.
            try:
                QApplication.instance().quit()
            except Exception:
                pass

        worker.finished.connect(_done)
        worker.start()
        self._update_worker = worker

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
        from PySide6.QtCore import QThread, Signal

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

        class _ReconnectWorker(QThread):
            finished = Signal(bool, str, object, str)  # success, message, driver, email

            def __init__(self, main):
                super().__init__()
                self.main = main

            def run(self):
                driver = None
                try:
                    from Database.SessionManager import SessionManager
                    sm = SessionManager(self.main.db)
                    email, password = sm.get_credentials_from_session()
                    if not (email and password):
                        self.finished.emit(False, self.main.i18n.tr("topbar.reconnect.no_session"), None, "")
                        return

                    from Config.BrowserConfig.BrowserManager import BrowserManager
                    browser_choice = self.main.settings.get_browser_choice() or "Chrome"
                    bm = BrowserManager()
                    driver = bm.setup_browser(browser_choice, retry_callback=lambda: False)
                    if driver is None:
                        self.finished.emit(False, self.main.i18n.tr("login.browser_init_failed"), None, "")
                        return

                    from Config.LoginConfig.LoginHandler import LoginHandler
                    lh = LoginHandler(driver, self.main.credential_manager)
                    ok = lh.login(credentials_callback=lambda: (email, password), retry_callback=lambda: False, max_attempts=1)
                    if not ok:
                        try:
                            driver.quit()
                        except Exception:
                            pass
                        self.finished.emit(False, self.main.i18n.tr("topbar.reconnect.login_failed"), None, "")
                        return

                    self.finished.emit(True, self.main.i18n.tr("topbar.reconnect.done"), driver, email)
                except Exception as e:
                    try:
                        if driver:
                            driver.quit()
                    except Exception:
                        pass
                    self.finished.emit(False, str(e), None, "")

        worker = _ReconnectWorker(self)

        def _done(success: bool, message: str, driver, email: str):
            if success:
                self.driver = driver
                if email:
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
                InfoBar.error(
                    title=self.i18n.tr("topbar.reconnect.title"),
                    content=message,
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=4000,
                    parent=self,
                )

        worker.finished.connect(_done)
        worker.start()
        self._reconnect_worker = worker

    def logout(self):
        """Logout and return to login"""
        if self.driver:
            self.driver.quit()
            self.driver = None
        self.current_user = None

        # Hide navigation bar
        self.navigationInterface.setVisible(False)

        self.show_login()

    def start_batch_processing(self, items):
        """
        Start batch processing with collected items

        Args:
            items: List of {brand, code, url} dicts
        """
        # Switch to upload screen
        self._switch_to_screen(0)

        # Trigger batch processing in upload screen
        if self.upload_screen:
            self.upload_screen.show_batch_processing(items)

    def _apply_saved_theme(self):
        """Apply saved theme from settings"""
        from qfluentwidgets import setTheme, Theme
        from GUI_Qt.styles.global_styles import get_global_stylesheet

        theme = self.settings.get('theme', 'light')
        if theme == 'dark':
            setTheme(Theme.DARK)
        else:
            setTheme(Theme.LIGHT)

        # Apply global stylesheet for consistent styling (set at app-level so it
        # reliably affects all widgets/screens).
        try:
            app = QApplication.instance()
            if app is not None:
                app.setStyleSheet(get_global_stylesheet())
            else:
                self.setStyleSheet(get_global_stylesheet())
        except Exception:
            self.setStyleSheet(get_global_stylesheet())

    def update_container_backgrounds(self):
        """Update main container and content stack backgrounds when theme changes"""
        from qfluentwidgets import isDarkTheme
        from GUI_Qt.styles.theme_config import COLORS

        if not hasattr(self, 'content_stack'):
            return

        is_dark = isDarkTheme()
        bg_color = COLORS['space_indigo'] if is_dark else COLORS['platinum']

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

"""GUI_Qt/screens/UnifiedBatchScreen.py

Unified batch operations screen — replaces BatchUploadScreen,
BatchDescriptionsScreen and BatchTitlesScreen with a single
customisable table whose columns adapt to the selected operation.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    CheckBox,
    ComboBox,
    FluentIcon,
    Flyout,
    FlyoutViewBase,
    IconWidget,
    IndeterminateProgressRing,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    MessageBox,
    PillPushButton,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    TitleLabel,
    TransparentPushButton,
    TransparentToolButton,
    isDarkTheme,
    qconfig,
)

from GUI_Qt.widgets.ResponsiveWidget import ResponsiveWidget
from GUI_Qt.widgets.DropZoneWidget import DropZoneWidget
from GUI_Qt.widgets.DragFillHandle import DragFillHandle
from GUI_Qt.widgets.TieredHeaderWidget import TieredHeaderWidget
from GUI_Qt.widgets.FrozenColumnTableWidget import FrozenColumnOverlay
from GUI_Qt.widgets.FilterableComboBox import FilterableComboBox
from GUI_Qt.widgets import enable_table_copy
from GUI_Qt.components.dialogs import DestructiveActionDialog
from GUI_Qt.screens.batch_inspector import BatchInspectorPanel
from GUI_Qt.styles.theme_config import (
    COLORS,
    COMPONENT_COLORS,
    FONTS,
    PADDINGS,
    RADII,
    SIZES,
    SPACING,
    get_text_color,
)
from GUI_Qt.styles.screen_theme import (
    PAGE_MARGINS,
    PAGE_SPACING,
    ICON_TEXT_GAP,
    ROW_SPACING,
    TOOLBAR_MARGINS,
    CONTENT_SPACING,
    TABLE_CELL_MARGINS,
    apply_screen_theme,
    enforce_transparent_labels,
    get_responsive_margins,
    get_responsive_spacing,
)
from GUI_Qt.screens.batch_columns import (
    ATTR_COL_MAP,
    COL,
    COLUMN_GROUPS,
    COLUMNS,
    NUM_COLUMNS,
    PRESETS,
)
from GUI_Qt.screens.batch_strategies import STRATEGIES
from GUI_Qt.screens.UploadScreen import ATTRIBUTE_DEFINITIONS
from GUI_Qt.dialogs.AttributeOptionsDialog import (
    AttributeOptionsDialog,
    load_attribute_options,
)
from Managers.DescriptionManager import DescriptionManager
from Utilities.ExcelHandler import ExcelHandler

_SETTINGS_KEY_COLUMNS = "batch_visible_columns"

# Tuple of combo-like widget types for isinstance checks
_COMBO_TYPES = (ComboBox, FilterableComboBox)


# ---------------------------------------------------------------------------
# Cell focus filter — syncs table selection when a cell widget gets focus
# ---------------------------------------------------------------------------

class BatchExecutionController:
    def _start_batch(self):
        # Show status/error columns for batch progress
        self._show_status_cols = True
        self._apply_column_config()

        strategy = self._infer_strategy()

        # Collect valid rows
        valid_rows = []
        for row in range(self.table.rowCount()):
            if strategy.validate_row(self, row):
                valid_rows.append(row)
        if not valid_rows:
            return

        items = strategy.collect_items(self, valid_rows)
        if not items:
            return

        if isinstance(strategy, type(STRATEGIES["upload"])):
            self._earning_batch_started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._earning_batch_candidates = [
                {**item, "table_row": table_row}
                for item, table_row in zip(items, valid_rows)
            ]
        else:
            self._earning_batch_candidates = []
            self._earning_batch_started_at = None

        # Master password check for upload mode with external brands
        if isinstance(strategy, type(STRATEGIES["upload"])):
            master_password = getattr(self.main, "_unlocked_master_password", None)
            for it in items:
                brand = it.get("brand", "")
                if brand == "Basso":
                    if not self.main.credential_manager.has_external_credentials("basso"):
                        InfoBar.error(
                            title=self.main.i18n.tr("common.error"),
                            content=self.main.i18n.tr("account.brand_missing", brand="Basso"),
                            orient=Qt.Orientation.Horizontal,
                            isClosable=True,
                            position=InfoBarPosition.TOP,
                            duration=5000,
                            parent=self,
                        )
                        return
                if brand == "Lee Cougan":
                    if not self.main.credential_manager.has_external_credentials("leecougan"):
                        InfoBar.error(
                            title=self.main.i18n.tr("common.error"),
                            content=self.main.i18n.tr("account.brand_missing", brand="Lee Cougan"),
                            orient=Qt.Orientation.Horizontal,
                            isClosable=True,
                            position=InfoBarPosition.TOP,
                            duration=5000,
                            parent=self,
                        )
                        return

        # Reset status for valid rows
        for row in valid_rows:
            status_w = self._get_inner_widget(row, COL["status"])
            if status_w and isinstance(status_w, BodyLabel):
                status_w.setText("Pending")
                status_w.setStyleSheet(f"color: {get_text_color(isDarkTheme(), 'secondary')};")
            error_w = self._get_inner_widget(row, COL["error"])
            if error_w and isinstance(error_w, LineEdit):
                error_w.setText("")

        # Multi-session detection
        multi_session = self.main.settings.get("multi_session_enabled", False)
        session_mgr = None
        if multi_session:
            if self.session_manager is None or not self.session_manager.is_ready():
                try:
                    from Config.LoginConfig.LoginHandler import LoginHandler
                    from Config.Selectors import LoginSelectors
                    from Managers.BrowserSessionManager import BrowserSessionManager
                    browser_count = self.main.settings.get("browser_count", 2)
                    browser_type = self.main.settings.get("browser_choice", "chrome")
                    self.session_manager = BrowserSessionManager(
                        browser_type, browser_count, self.main.logger
                    )
                    email, password = self.main.credential_manager.get_saved_credentials()

                    def initialize_session(driver):
                        if not email or not password:
                            return False
                        driver.get(LoginSelectors.URL)
                        handler = LoginHandler(
                            driver,
                            self.main.credential_manager,
                            logger=self.main.logger,
                        )
                        return handler.attempt_login(email, password)

                    self.session_manager.set_session_initializer(initialize_session)
                    if not self.session_manager.initialize_pool():
                        self.session_manager = None
                except Exception:
                    self.session_manager = None
            session_mgr = self.session_manager if self.session_manager and self.session_manager.is_ready() else None

        # Create worker
        self.worker = strategy.create_worker(
            self, items, valid_rows,
            multi_session=bool(session_mgr),
            session_manager=session_mgr,
        )

        # Connect signals
        self.worker.row_update.connect(self._on_row_update)
        self.worker.done.connect(self._on_done)
        if hasattr(self.worker, "progress_update"):
            self.worker.progress_update.connect(self._on_progress_update)
        if hasattr(self.worker, "log"):
            self.worker.log.connect(self._on_log)
        if hasattr(self.worker, "session_status"):
            self.worker.session_status.connect(self._on_session_status)
        if hasattr(self.worker, "review_required"):
            self.worker.review_required.connect(self._on_review_required)

        self._set_busy(True)
        if hasattr(self.main, "track_worker"):
            self.main.track_worker(
                self.worker, "batch_variants", "batch", total=self.table.rowCount()
            )
        self.worker.start()

    def _on_review_required(
        self,
        token: str,
        row: int,
        code: str,
        url: str,
        mode: str,
    ):
        request = (token, row, code, url, mode)
        if token not in {item[0] for item in self._pending_reviews} and (
            self._active_review is None or self._active_review[0] != token
        ):
            self._pending_reviews.append(request)
        self._show_next_review()

    def _show_next_review(self):
        if self._active_review is None and self._pending_reviews:
            self._active_review = self._pending_reviews.pop(0)
        active = self._active_review
        visible = active is not None
        self.review_saved_btn.setVisible(
            visible and active is not None and active[4] == "review"
        )
        self.review_discard_btn.setVisible(visible)
        if active:
            _token, row, code, _url, mode = active
            if mode == "discard_only":
                self.status_label.setText(
                    f"{code}: paruošimas nepavyko. Patvirtinkite pakeitimų atmetimą."
                )
                self._on_row_update(
                    row,
                    "Nepavyko — laukiama atmetimo",
                    "PIMBO forma nebus uždaroma be jūsų patvirtinimo",
                )
            else:
                self.status_label.setText(
                    f"{code}: paruošta peržiūrai. PIMBO lange spauskite Save."
                )
                self._on_row_update(row, "Paruošta peržiūrai", "Laukiama rankinio Save")

    def _send_review_action(self, action: str):
        if self._active_review is None or self.worker is None:
            return
        token, _row, _code, _url, _mode = self._active_review
        self._active_review = None
        self.review_saved_btn.hide()
        self.review_discard_btn.hide()
        self.worker.review_response.emit(token, action)
        self._show_next_review()

    def _confirm_review_saved(self):
        if self._active_review is None or self._active_review[4] != "review":
            return
        self._send_review_action("saved")

    def _confirm_review_discard(self):
        if self._active_review is None:
            return
        _token, _row, code, _url, _mode = self._active_review
        confirmed = DestructiveActionDialog.ask(
            title=self.main.i18n.tr("batch.review.discard.title"),
            message=self.main.i18n.tr("batch.review.discard.content", code=code),
            action_text=self.main.i18n.tr("batch.review.discard.action"),
            parent=self,
            tr_func=self.main.i18n.tr,
        )
        if confirmed:
            self._send_review_action("discard")

    def _set_busy(self, busy: bool):
        self._is_busy = busy
        self.start_btn.setEnabled(not busy)
        self.add_btn.setEnabled(not busy)
        self.clear_btn.setEnabled(not busy)
        self.retry_btn.hide()

        if busy:
            self.progress_ring.show()
            self.progress_ring.start()
            self._start_time = time.time()
            self._elapsed_timer = QTimer(self)
            self._elapsed_timer.timeout.connect(self._update_elapsed)
            self._elapsed_timer.start(1000)
            self.elapsed_label.show()
            self._update_elapsed()
        else:
            self.progress_ring.stop()
            self.progress_ring.hide()
            if hasattr(self, "_elapsed_timer"):
                self._elapsed_timer.stop()
            self.elapsed_label.hide()
            if not self._pending_reviews and self._active_review is None:
                self.review_saved_btn.hide()
                self.review_discard_btn.hide()

    def _update_elapsed(self):
        if not hasattr(self, "_start_time"):
            return
        elapsed = int(time.time() - self._start_time)
        mins, secs = divmod(elapsed, 60)
        self.elapsed_label.setText(f"Elapsed: {mins:02d}:{secs:02d}")

    def _on_row_update(self, row: int, status_text: str, error_text: str):
        # Clear previous processing highlight
        if self._current_processing_row is not None and self._current_processing_row != row:
            self._set_row_bg(self._current_processing_row, QColor(0, 0, 0, 0))

        # Determine color
        if "Processing" in status_text:
            bg = QColor(255, 182, 193, 100)
            self._current_processing_row = row
        elif "Paruošta peržiūrai" in status_text:
            bg = QColor(255, 215, 0, 90)
            self._current_processing_row = row
        elif "Išsaugota rankiniu" in status_text:
            bg = QColor(144, 238, 144, 120)
        elif "Atmesta" in status_text or "Ne Draft" in status_text:
            bg = QColor(211, 211, 211, 100)
        elif "Success" in status_text or "✓" in status_text or "ok" in status_text.lower():
            bg = QColor(144, 238, 144, 120)
        elif "Failed" in status_text or "Nepavyko" in status_text or "✗" in status_text:
            bg = QColor(255, 99, 71, 100)
        else:
            bg = QColor(0, 0, 0, 0)

        self._set_row_bg(row, bg)

        # Update status
        status_w = self._get_inner_widget(row, COL["status"])
        if status_w and isinstance(status_w, BodyLabel):
            status_w.setText(status_text)

        # Update error
        error_w = self._get_inner_widget(row, COL["error"])
        if error_w and isinstance(error_w, LineEdit):
            error_w.setText(error_text)

    def _set_row_bg(self, row: int, color: QColor):
        for col in range(NUM_COLUMNS):
            item = self.table.item(row, col)
            if item is None:
                item = QTableWidgetItem()
                self.table.setItem(row, col, item)
            item.setBackground(color)

    def _on_done(self, ok: int, total: int):
        self._set_busy(False)
        self._current_processing_row = None
        tr = self.main.i18n.tr

        failed = total - ok
        if failed > 0:
            self.retry_btn.show()
            InfoBar.warning(
                title=tr("batch.done.title"),
                content=tr("batch.done.partial", ok=ok, total=total, failed=failed),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )
        else:
            InfoBar.success(
                title=tr("batch.done.title"),
                content=tr("batch.done.success", ok=ok, total=total),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )
        self._validate()
        if self._earning_batch_candidates:
            QTimer.singleShot(0, self._prompt_completed_batch_earnings)

    def _prompt_completed_batch_earnings(self):
        """Offer one review list containing only products verified as saved."""
        candidates = self._earning_batch_candidates
        started_at = self._earning_batch_started_at
        self._earning_batch_candidates = []
        self._earning_batch_started_at = None
        if not candidates or not started_at:
            return
        saved_items = []
        for candidate in candidates:
            row = self.main.db.conn.execute(
                """
                SELECT id FROM processing_history
                WHERE brand=? AND product_code=? AND status='saved_manually'
                  AND processed_at>=?
                ORDER BY id DESC LIMIT 1
                """,
                (candidate.get("brand", ""), candidate.get("code", ""), started_at),
            ).fetchone()
            if row is None:
                continue
            saved_items.append({
                "sku": candidate.get("code", ""),
                "brand": candidate.get("brand", ""),
                "product_type": "frameset" if candidate.get("frameset_only") else "bicycle",
                "source": "batch_upload",
                "processing_history_id": int(row["id"]),
            })
        if saved_items:
            self.main.prompt_earning_items(saved_items, parent=self)

    def _on_progress_update(self, current, total, speed, eta_seconds):
        mins, secs = divmod(int(eta_seconds), 60)
        self.status_label.setText(f"{current}/{total} • ETA {mins:02d}:{secs:02d}")

    def _on_log(self, *args):
        msg = " ".join(str(a) for a in args)
        if hasattr(self.main, "logger"):
            self.main.logger.log("Batch", msg)

    def _on_session_status(self, stats: dict):
        busy = stats.get("busy", 0)
        total = stats.get("total", 0)
        self.status_label.setText(f"Browsers: {busy}/{total}")

    # ---------------------------------------------------------- Retry
    def _retry_failed(self):
        strategy = self._infer_strategy()
        failed_rows = []
        for row in range(self.table.rowCount()):
            status_w = self._get_inner_widget(row, COL["status"])
            if status_w and isinstance(status_w, BodyLabel):
                text = status_w.text()
                if "✗" in text or "Failed" in text:
                    failed_rows.append(row)
        if not failed_rows:
            return

        items = strategy.collect_items(self, failed_rows)
        if not items:
            return

        if isinstance(strategy, type(STRATEGIES["upload"])):
            self._earning_batch_started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._earning_batch_candidates = [
                {**item, "table_row": table_row}
                for item, table_row in zip(items, failed_rows)
            ]
        else:
            self._earning_batch_candidates = []
            self._earning_batch_started_at = None

        # Reset failed row statuses
        for row in failed_rows:
            status_w = self._get_inner_widget(row, COL["status"])
            if status_w and isinstance(status_w, BodyLabel):
                status_w.setText("Pending")
            error_w = self._get_inner_widget(row, COL["error"])
            if error_w and isinstance(error_w, LineEdit):
                error_w.setText("")
            self._set_row_bg(row, QColor(0, 0, 0, 0))

        # Multi-session
        multi_session = self.main.settings.get("multi_session_enabled", False)
        session_mgr = self.session_manager if (
            multi_session and self.session_manager and self.session_manager.is_ready()
        ) else None

        self.worker = strategy.create_worker(
            self, items, failed_rows,
            multi_session=bool(session_mgr),
            session_manager=session_mgr,
        )
        self.worker.row_update.connect(self._on_row_update)
        self.worker.done.connect(self._on_done)
        if hasattr(self.worker, "progress_update"):
            self.worker.progress_update.connect(self._on_progress_update)
        if hasattr(self.worker, "log"):
            self.worker.log.connect(self._on_log)
        if hasattr(self.worker, "session_status"):
            self.worker.session_status.connect(self._on_session_status)
        if hasattr(self.worker, "review_required"):
            self.worker.review_required.connect(self._on_review_required)

        self._set_busy(True)
        if hasattr(self.main, "track_worker"):
            self.main.track_worker(
                self.worker, "batch_variants", "batch", total=self.table.rowCount()
            )
        self.worker.start()

    # ---------------------------------------------------------- Shortcuts
    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+Return"), self, self._start_batch)
        QShortcut(QKeySequence("Ctrl+R"), self, self._retry_failed)
        QShortcut(QKeySequence("Escape"), self, self._handle_cancel)

    def _handle_cancel(self):
        if self._active_review is not None:
            InfoBar.warning(
                title="Reikia užbaigti peržiūrą",
                content="Pirmiausia išsaugokite arba atmeskite atidaryto produkto pakeitimus.",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self,
            )
            return
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            InfoBar.warning(
                title=self.main.i18n.tr("batch.stop.title"),
                content=self.main.i18n.tr("batch.stop.body"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )

    # ---------------------------------------------------------- Theme

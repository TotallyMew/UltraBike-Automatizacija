"""Integrated Pimbo-to-Orbea catalogue, report, and table-image workflow."""

from __future__ import annotations

import inspect
import json
import re
import threading
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import openpyxl
from PySide6.QtCore import QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    ComboBox,
    FluentIcon,
    IconWidget,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PillPushButton,
    PlainTextEdit,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    ScrollArea,
    TitleLabel,
    FlowLayout,
    isDarkTheme,
)

from GUI_Qt.styles.screen_theme import (
    CARD_MARGINS,
    CARD_SPACING,
    CONTENT_SPACING,
    ICON_TEXT_GAP,
    PAGE_MARGINS,
    PAGE_SPACING,
    ROW_SPACING,
    apply_screen_theme,
    enforce_transparent_labels,
)
from GUI_Qt.styles.theme_config import COLORS, COMPONENT_COLORS, FONTS, PADDINGS, RADII, SIZES
from GUI_Qt.widgets import enable_table_copy
from GUI_Qt.widgets.ResponsiveWidget import ResponsiveWidget


CATALOGUE_SETTING = "orbea_catalogue_path"
OUTPUT_SETTING = "orbea_output_root"
FILTER_SETTING = "orbea_filter_preset"
DESCRIPTION_OUTPUT_SETTING = "orbea_description_output"
PREVIEW_LIMIT = 500


def _read(obj: Any, *names: str, default: Any = None) -> Any:
    """Read the first available mapping key or object attribute."""
    for name in names:
        if isinstance(obj, Mapping) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def _plain(value: Any) -> Any:
    if hasattr(value, "value"):
        value = value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return list(value)
    return value


def _create_model(model_type, values: dict[str, Any], aliases: dict[str, str]):
    """Construct a typed service model while tolerating API-compatible aliases."""
    parameters = inspect.signature(model_type).parameters
    kwargs: dict[str, Any] = {}
    for name, parameter in parameters.items():
        if name in ("self", "args", "kwargs"):
            continue
        canonical = aliases.get(name, name)
        if canonical in values:
            kwargs[name] = values[canonical]
        elif parameter.default is inspect.Parameter.empty:
            raise TypeError(f"{model_type.__name__} requires unsupported field '{name}'")
    return model_type(**kwargs)


def _service_factory(driver, image_driver_factory=None):
    # Local import keeps the rest of the app importable in a partially-updated
    # installation and gives PyInstaller a normal Python module to collect.
    from tools.orbea_automation import OrbeaAutomationService

    return OrbeaAutomationService(driver, image_driver_factory=image_driver_factory)


class OrbeaFilterWorker(QThread):
    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, driver, make_service: Callable[[Any], Any]):
        super().__init__()
        self.driver = driver
        self.make_service = make_service
        self._stopped = False
        self._service = None

    def request_stop(self):
        self._stopped = True
        self.requestInterruption()
        service = self._service
        if service is not None and hasattr(service, "cancel"):
            try:
                service.cancel()
            except Exception:
                pass

    def run(self):
        try:
            self._service = self.make_service(self.driver)
            options = self._service.discover_filter_options()
            if not self._stopped:
                self.loaded.emit(options)
        except Exception as exc:
            if not self._stopped:
                self.failed.emit(str(exc))


class OrbeaRunWorker(QThread):
    progress_changed = Signal(object)
    log_message = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        driver,
        make_service: Callable[[Any], Any],
        config,
        *,
        resume: bool,
        retry_failed: bool,
    ):
        super().__init__()
        self.driver = driver
        self.make_service = make_service
        self.config = config
        self.resume = resume
        self.retry_failed = retry_failed
        self._service = None
        self._token: Any = threading.Event()

    def request_stop(self):
        token = self._token
        for method_name in ("cancel", "set"):
            method = getattr(token, method_name, None)
            if callable(method):
                try:
                    method()
                    break
                except Exception:
                    pass
        service = self._service
        if service is not None and hasattr(service, "cancel"):
            try:
                service.cancel()
            except Exception:
                pass

    def run(self):
        try:
            self._service = self.make_service(self.driver)
            try:
                from tools.orbea_automation import CancellationToken

                self._token = CancellationToken()
            except Exception:
                self._token = threading.Event()

            result = self._service.run(
                self.config,
                progress=self.progress_changed.emit,
                log=self.log_message.emit,
                cancellation=self._token,
                resume=self.resume,
                retry_failed=self.retry_failed,
            )
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class OrbeaDescriptionWorker(QThread):
    """Run description extraction without touching the authenticated Pimbo browser."""

    progress_changed = Signal(object)
    log_message = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, make_service: Callable[[], Any], config):
        super().__init__()
        self.make_service = make_service
        self.config = config
        self._service = None
        self._token: Any = threading.Event()
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True
        token = self._token
        for method_name in ("cancel", "set"):
            method = getattr(token, method_name, None)
            if callable(method):
                try:
                    method()
                    break
                except Exception:
                    pass
        service = self._service
        if service is not None and hasattr(service, "cancel"):
            try:
                service.cancel()
            except Exception:
                pass

    def run(self):
        try:
            self._service = self.make_service()
            try:
                from tools.orbea_automation import CancellationToken

                self._token = CancellationToken()
            except Exception:
                self._token = threading.Event()

            if self._stop_requested:
                token = self._token
                for method_name in ("cancel", "set"):
                    method = getattr(token, method_name, None)
                    if callable(method):
                        method()
                        break
                if hasattr(self._service, "cancel"):
                    self._service.cancel()

            result = self._service.run(
                self.config,
                progress=self.progress_changed.emit,
                log=self.log_message.emit,
                cancellation=self._token,
            )
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class OrbeaExcelSortWorker(QThread):
    """Sort an existing Orbea match workbook without blocking the app window."""

    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, source_path: Path):
        super().__init__()
        self.source_path = source_path

    def request_stop(self):
        self.requestInterruption()

    def run(self):
        try:
            from tools.orbea_automation.report import sort_existing_match_workbook

            destination = sort_existing_match_workbook(self.source_path)
            if not self.isInterruptionRequested():
                self.succeeded.emit(str(destination))
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(str(exc))


class OrbeaScreen(ResponsiveWidget):
    """End-to-end Orbea automation UI backed by the authenticated Pimbo driver."""

    def __init__(
        self,
        main_window,
        *,
        settings_manager=None,
        service_factory: Callable[[Any], Any] | None = None,
        image_driver_factory: Callable[[], Any] | None = None,
        description_service_factory: Callable[[], Any] | None = None,
    ):
        super().__init__(main_window)
        self.main = main_window
        self.settings = settings_manager or getattr(main_window, "settings", None)
        self.tr = main_window.i18n.tr
        self._image_driver_factory = image_driver_factory
        self._external_service_factory = service_factory
        self._external_description_service_factory = description_service_factory
        self._worker: OrbeaRunWorker | None = None
        self._filter_worker: OrbeaFilterWorker | None = None
        self._description_worker: OrbeaDescriptionWorker | None = None
        self._excel_sort_worker: OrbeaExcelSortWorker | None = None
        self._owns_browser_lease = False
        self._restoring_filters = False
        self._closing = False
        self._workbook_path: Path | None = None
        self._run_dir: Path | None = None
        self._description_output_dir: Path | None = None
        self._status_buttons: dict[str, PillPushButton] = {}
        self._stock_buttons: dict[str, PillPushButton] = {}
        self._bucket_buttons: dict[str, PillPushButton] = {}
        self._status_group = None
        self._stock_group = None
        self._bucket_group = None
        self._config_widgets: list[QWidget] = []
        self._description_config_widgets: list[QWidget] = []
        self._saved_filter_state = self._load_filter_state()

        self.setObjectName("OrbeaScreen")
        self._build_ui()
        self._install_default_filters()
        self._load_paths()
        self.retranslate_ui()
        self._update_action_states()
        QTimer.singleShot(0, self._auto_refresh_filters)

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(*PAGE_MARGINS)
        root.setSpacing(PAGE_SPACING)

        self._scroll = ScrollArea()
        self._scroll.setWidgetResizable(True)
        root.addWidget(self._scroll)
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(CONTENT_SPACING)
        self._scroll.setWidget(self._container)
        apply_screen_theme(self, "OrbeaScreen", scroll=self._scroll, content=self._container)

        header = QHBoxLayout()
        header.setSpacing(ICON_TEXT_GAP)
        icon = IconWidget(FluentIcon.SYNC)
        icon.setFixedSize(SIZES["icon_lg"], SIZES["icon_lg"])
        header.addWidget(icon)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self._title = TitleLabel("")
        self._subtitle = CaptionLabel("")
        self._subtitle.setStyleSheet(f"color: {COLORS['text_secondary']};")
        title_col.addWidget(self._title)
        title_col.addWidget(self._subtitle)
        header.addLayout(title_col)
        header.addStretch()
        self._layout.addLayout(header)

        self._build_paths_card()
        self._build_filters_card()
        self._build_actions_card()
        self._build_progress_card()
        self._build_description_card()
        self._build_results_table()

        enforce_transparent_labels(self)

    def _card(self) -> tuple[CardWidget, QVBoxLayout]:
        card = CardWidget()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(*CARD_MARGINS)
        layout.setSpacing(CARD_SPACING)
        return card, layout

    def _build_paths_card(self):
        card, layout = self._card()
        self._paths_title = BodyLabel("")
        self._paths_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(self._paths_title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(CARD_SPACING)
        grid.setVerticalSpacing(ROW_SPACING)
        grid.setColumnStretch(1, 1)

        self._catalogue_label = BodyLabel("")
        self._catalogue_edit = LineEdit()
        self._catalogue_edit.setClearButtonEnabled(True)
        self._catalogue_edit.editingFinished.connect(self._paths_changed)
        self._catalogue_btn = PushButton(FluentIcon.DOCUMENT, "")
        self._catalogue_btn.clicked.connect(self._browse_catalogue)
        grid.addWidget(self._catalogue_label, 0, 0)
        grid.addWidget(self._catalogue_edit, 0, 1)
        grid.addWidget(self._catalogue_btn, 0, 2)

        self._output_label = BodyLabel("")
        self._output_edit = LineEdit()
        self._output_edit.setClearButtonEnabled(True)
        self._output_edit.editingFinished.connect(self._paths_changed)
        self._output_btn = PushButton(FluentIcon.FOLDER, "")
        self._output_btn.clicked.connect(self._browse_output)
        grid.addWidget(self._output_label, 1, 0)
        grid.addWidget(self._output_edit, 1, 1)
        grid.addWidget(self._output_btn, 1, 2)

        self._search_label = BodyLabel("")
        self._search_edit = LineEdit()
        self._search_edit.setText("orbea")
        self._search_edit.setReadOnly(True)
        self._search_edit.setEnabled(False)
        grid.addWidget(self._search_label, 2, 0)
        grid.addWidget(self._search_edit, 2, 1, 1, 2)
        layout.addLayout(grid)
        self._layout.addWidget(card)
        self._config_widgets.extend([
            self._catalogue_edit,
            self._catalogue_btn,
            self._output_edit,
            self._output_btn,
        ])

    def _build_filters_card(self):
        card, layout = self._card()
        top = QHBoxLayout()
        self._filters_title = BodyLabel("")
        self._filters_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self._filter_state_label = CaptionLabel("")
        self._filter_state_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self._refresh_btn = PushButton(FluentIcon.SYNC, "")
        self._refresh_btn.clicked.connect(self.refresh_filter_options)
        top.addWidget(self._filters_title)
        top.addWidget(self._filter_state_label, 1)
        top.addWidget(self._refresh_btn)
        layout.addLayout(top)

        self._status_label = BodyLabel("")
        layout.addWidget(self._status_label)
        self._status_layout = FlowLayout()
        self._status_layout.setHorizontalSpacing(ROW_SPACING)
        self._status_layout.setVerticalSpacing(ROW_SPACING)
        layout.addLayout(self._status_layout)

        grid = QGridLayout()
        grid.setHorizontalSpacing(CARD_SPACING)
        grid.setVerticalSpacing(ROW_SPACING)
        self._family_combo = ComboBox()
        self._category_combo = ComboBox()
        self._source_combo = ComboBox()
        self._locale_combo = ComboBox()
        self._sort_combo = ComboBox()
        self._family_field, self._family_label = self._combo_field(self._family_combo)
        self._category_field, self._category_label = self._combo_field(self._category_combo)
        self._source_field, self._source_label = self._combo_field(self._source_combo)
        self._locale_field, self._locale_label = self._combo_field(self._locale_combo)
        self._sort_field, self._sort_label = self._combo_field(self._sort_combo)
        grid.addWidget(self._family_field, 0, 0)
        grid.addWidget(self._category_field, 0, 1)
        grid.addWidget(self._source_field, 0, 2)
        grid.addWidget(self._locale_field, 1, 0)
        grid.addWidget(self._sort_field, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        layout.addLayout(grid)

        self._stock_label = BodyLabel("")
        layout.addWidget(self._stock_label)
        self._stock_layout = FlowLayout()
        self._stock_layout.setHorizontalSpacing(ROW_SPACING)
        self._stock_layout.setVerticalSpacing(ROW_SPACING)
        layout.addLayout(self._stock_layout)

        self._bucket_label = BodyLabel("")
        layout.addWidget(self._bucket_label)
        self._bucket_layout = FlowLayout()
        self._bucket_layout.setHorizontalSpacing(ROW_SPACING)
        self._bucket_layout.setVerticalSpacing(ROW_SPACING)
        layout.addLayout(self._bucket_layout)

        self._layout.addWidget(card)
        combos = [
            self._family_combo,
            self._category_combo,
            self._source_combo,
            self._locale_combo,
            self._sort_combo,
        ]
        for combo in combos:
            combo.currentIndexChanged.connect(self._filter_changed)
        self._config_widgets.extend([self._refresh_btn, *combos])

    def _combo_field(self, combo: ComboBox) -> tuple[QWidget, BodyLabel]:
        field = QWidget()
        box = QVBoxLayout(field)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)
        label = BodyLabel("")
        combo.setMinimumWidth(160)
        box.addWidget(label)
        box.addWidget(combo)
        return field, label

    def _build_actions_card(self):
        card, layout = self._card()
        actions = QGridLayout()
        actions.setHorizontalSpacing(ROW_SPACING)
        actions.setVerticalSpacing(ROW_SPACING)
        self._start_btn = PrimaryPushButton(FluentIcon.PLAY, "")
        self._start_btn.clicked.connect(self._on_start_stop)
        self._resume_btn = PushButton(FluentIcon.UPDATE, "")
        self._resume_btn.clicked.connect(
            lambda: self._start_run(resume=True, retry_failed=False, require_existing=True)
        )
        self._retry_btn = PushButton(FluentIcon.SYNC, "")
        self._retry_btn.clicked.connect(
            lambda: self._start_run(resume=True, retry_failed=True, require_existing=True)
        )
        self._open_excel_btn = PushButton(FluentIcon.DOCUMENT, "")
        self._open_excel_btn.setEnabled(False)
        self._open_excel_btn.clicked.connect(self._open_excel)
        self._open_folder_btn = PushButton(FluentIcon.FOLDER, "")
        self._open_folder_btn.setEnabled(False)
        self._open_folder_btn.clicked.connect(self._open_folder)
        self._excel_sort_btn = PushButton(FluentIcon.DOCUMENT, "")
        self._excel_sort_btn.clicked.connect(self._sort_existing_excel)
        actions.addWidget(self._start_btn, 0, 0)
        actions.addWidget(self._resume_btn, 0, 1)
        actions.addWidget(self._retry_btn, 1, 0)
        actions.addWidget(self._excel_sort_btn, 1, 1)
        actions.addWidget(self._open_excel_btn, 2, 0)
        actions.addWidget(self._open_folder_btn, 2, 1)
        for column in range(2):
            actions.setColumnStretch(column, 1)
        layout.addLayout(actions)
        self._layout.addWidget(card)
        self._config_widgets.append(self._excel_sort_btn)

    def _build_progress_card(self):
        card, layout = self._card()
        status_row = QHBoxLayout()
        self._stage_label = BodyLabel("")
        self._stage_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        self._eta_label = CaptionLabel("")
        self._eta_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        status_row.addWidget(self._stage_label, 1)
        status_row.addWidget(self._eta_label)
        layout.addLayout(status_row)
        self._progress = ProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        layout.addWidget(self._progress)
        self._progress_label = CaptionLabel("")
        self._progress_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        layout.addWidget(self._progress_label)

        stats = QGridLayout()
        stats.setHorizontalSpacing(CARD_SPACING)
        stats.setVerticalSpacing(ROW_SPACING)
        self._stat_values: dict[str, BodyLabel] = {}
        self._stat_labels: dict[str, CaptionLabel] = {}
        for index, key in enumerate(("scanned", "matched", "review", "images", "unavailable", "errors")):
            widget = QWidget()
            stat_layout = QVBoxLayout(widget)
            stat_layout.setContentsMargins(8, 4, 8, 4)
            stat_layout.setSpacing(2)
            label = CaptionLabel("")
            label.setStyleSheet(f"color: {COLORS['text_secondary']};")
            value = BodyLabel("0")
            value.setStyleSheet("font-size: 20px; font-weight: 600;")
            stat_layout.addWidget(label)
            stat_layout.addWidget(value)
            stats.addWidget(widget, index // 3, index % 3)
            self._stat_labels[key] = label
            self._stat_values[key] = value
        layout.addLayout(stats)

        self._log = PlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(130)
        layout.addWidget(self._log)
        self._layout.addWidget(card)

    def _build_description_card(self):
        card, layout = self._card()

        self._description_title = BodyLabel("")
        self._description_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self._description_subtitle = CaptionLabel("")
        self._description_subtitle.setStyleSheet(f"color: {COLORS['text_secondary']};")
        layout.addWidget(self._description_title)
        layout.addWidget(self._description_subtitle)

        self._description_urls_label = BodyLabel("")
        self._description_urls_edit = PlainTextEdit()
        self._description_urls_edit.setMinimumHeight(100)
        self._description_urls_edit.setMaximumHeight(170)
        self._description_urls_edit.textChanged.connect(self._update_action_states)
        layout.addWidget(self._description_urls_label)
        layout.addWidget(self._description_urls_edit)

        output_row = QGridLayout()
        output_row.setHorizontalSpacing(CARD_SPACING)
        output_row.setVerticalSpacing(ROW_SPACING)
        output_row.setColumnStretch(1, 1)
        self._description_output_label = BodyLabel("")
        self._description_output_edit = LineEdit()
        self._description_output_edit.setClearButtonEnabled(True)
        self._description_output_edit.editingFinished.connect(self._description_output_changed)
        self._description_output_btn = PushButton(FluentIcon.FOLDER, "")
        self._description_output_btn.clicked.connect(self._browse_description_output)
        output_row.addWidget(self._description_output_label, 0, 0, 1, 2)
        output_row.addWidget(self._description_output_edit, 1, 0)
        output_row.addWidget(self._description_output_btn, 1, 1)
        layout.addLayout(output_row)

        action_row = QVBoxLayout()
        action_row.setSpacing(ROW_SPACING)
        self._description_start_btn = PrimaryPushButton(FluentIcon.PLAY, "")
        self._description_start_btn.clicked.connect(self._on_description_start_stop)
        self._description_open_btn = PushButton(FluentIcon.FOLDER, "")
        self._description_open_btn.setEnabled(False)
        self._description_open_btn.clicked.connect(self._open_description_folder)
        action_row.addWidget(self._description_start_btn)
        action_row.addWidget(self._description_open_btn)
        layout.addLayout(action_row)

        self._description_status_label = BodyLabel("")
        self._description_status_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(self._description_status_label)
        self._description_progress = ProgressBar()
        self._description_progress.setRange(0, 100)
        self._description_progress.setValue(0)
        layout.addWidget(self._description_progress)
        self._description_progress_label = CaptionLabel("")
        self._description_progress_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        layout.addWidget(self._description_progress_label)

        self._description_log = PlainTextEdit()
        self._description_log.setReadOnly(True)
        self._description_log.setMaximumHeight(90)
        layout.addWidget(self._description_log)

        self._description_config_widgets.extend([
            self._description_urls_edit,
            self._description_output_edit,
            self._description_output_btn,
        ])
        self._layout.addWidget(card)

    def _build_results_table(self):
        self._results_label = CaptionLabel("")
        self._results_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self._layout.addWidget(self._results_label)
        self._table = QTableWidget(0, 6)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setMinimumHeight(280)
        enable_table_copy(self._table)
        self._layout.addWidget(self._table, 1)
        self._update_table_theme()

    # -------------------------------------------------------------- Filters

    def _install_default_filters(self):
        defaults = {
            "statuses": [("Draft", "Draft"), ("In Review", "In Review"), ("Published", "Published"), ("Disabled", "Disabled")],
            "families": [],
            "categories": [],
            "sources": [],
            "stock": [("Any", "Any"), ("In stock", "In stock"), ("Out of stock", "Out of stock")],
            "locales": [("Overall", "Overall"), ("LT", "LT"), ("EN", "EN"), ("LV", "LV"), ("EE", "EE")],
            "buckets": [("<40%", "<40%"), ("40–80%", "40–80%"), ("≥80%", "≥80%"), ("100%", "100%")],
            "sort": [("Recent", "Recent"), ("Least complete", "Least complete"), ("Most complete", "Most complete")],
        }
        self._apply_filter_options(defaults)

    def _normalise_options(self, raw: Any) -> list[tuple[str, Any]]:
        if raw is None:
            return []
        if isinstance(raw, Mapping):
            raw = list(raw.items())
        result: list[tuple[str, Any]] = []
        for item in raw:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                label, value = item[0], item[1]
            elif isinstance(item, str):
                label = value = item
            else:
                label = _read(item, "label", "name", "text", default="")
                value = _read(item, "value", "id", "key", default=label)
            label = str(label or value or "").strip()
            if label:
                result.append((label, _plain(value)))
        return result

    def _options(self, source: Any, *names: str) -> list[tuple[str, Any]]:
        return self._normalise_options(_read(source, *names, default=[]))

    def _apply_filter_options(self, options: Any):
        state = self._collect_filter_state() if self._status_buttons else dict(self._saved_filter_state)
        self._restoring_filters = True
        try:
            statuses = self._options(options, "statuses", "status_options") or self._normalise_options([
                ("Draft", "Draft"), ("In Review", "In Review"), ("Published", "Published"), ("Disabled", "Disabled")
            ])
            stock = self._options(options, "stock", "stock_options") or self._normalise_options([
                ("Any", "Any"), ("In stock", "In stock"), ("Out of stock", "Out of stock")
            ])
            buckets = self._options(options, "buckets", "completeness_buckets", "bucket_options") or self._normalise_options([
                ("<40%", "<40%"), ("40–80%", "40–80%"), ("≥80%", "≥80%"), ("100%", "100%")
            ])
            self._rebuild_multi_chips(self._status_layout, "_status_buttons", statuses, state.get("statuses", ["Draft"]))
            self._stock_group = self._rebuild_single_chips(self._stock_layout, "_stock_buttons", stock, state.get("stock", "In stock"))
            selected_buckets = state.get("completeness_buckets")
            if selected_buckets is None:
                legacy_bucket = state.get("completeness_bucket")
                selected_buckets = [legacy_bucket] if legacy_bucket and legacy_bucket != "any" else []
            self._rebuild_multi_chips(self._bucket_layout, "_bucket_buttons", buckets, selected_buckets)

            self._populate_combo(self._family_combo, self._options(options, "families", "family_options"), "All families", state.get("family_id"))
            self._populate_combo(self._category_combo, self._options(options, "categories", "category_options"), "All categories", state.get("category_id"))
            self._populate_combo(self._source_combo, self._options(options, "sources", "source_options"), "All sources", state.get("source_id"))
            locales = self._options(options, "locales", "completeness_locales", "locale_options") or self._normalise_options([
                ("Overall", "Overall"), ("LT", "LT"), ("EN", "EN"), ("LV", "LV"), ("EE", "EE")
            ])
            sorts = self._options(options, "sort", "sorts", "sort_options") or self._normalise_options([
                ("Recent", "Recent"), ("Least complete", "Least complete"), ("Most complete", "Most complete")
            ])
            self._populate_combo(self._locale_combo, locales, None, state.get("completeness_locale", "Overall"))
            self._populate_combo(self._sort_combo, sorts, None, state.get("sort", "Recent"))
        finally:
            self._restoring_filters = False
        self._save_filter_state()

    def _clear_chip_layout(self, layout, attr_name: str):
        buttons = getattr(self, attr_name, {})
        for button in buttons.values():
            layout.removeWidget(button)
            button.deleteLater()
            if button in self._config_widgets:
                self._config_widgets.remove(button)
        setattr(self, attr_name, {})

    def _rebuild_multi_chips(self, layout, attr_name, options, selected):
        self._clear_chip_layout(layout, attr_name)
        selected_keys = {str(_plain(value)).lower() for value in (selected or [])}
        buttons: dict[str, PillPushButton] = {}
        for label, value in options:
            key = str(_plain(value))
            button = PillPushButton()
            button.setText(label)
            button.setCheckable(True)
            button.setProperty("filterValue", value)
            button.setChecked(key.lower() in selected_keys or label.lower() in selected_keys)
            button.toggled.connect(self._filter_changed)
            layout.insertWidget(layout.count(), button)
            buttons[key] = button
            self._config_widgets.append(button)
        setattr(self, attr_name, buttons)

    def _rebuild_single_chips(self, layout, attr_name, options, selected):
        self._clear_chip_layout(layout, attr_name)
        group = QButtonGroup(self)
        group.setExclusive(True)
        selected_key = str(_plain(selected)).lower()
        buttons: dict[str, PillPushButton] = {}
        first = None
        for label, value in options:
            key = str(_plain(value))
            button = PillPushButton()
            button.setText(label)
            button.setCheckable(True)
            button.setProperty("filterValue", value)
            button.toggled.connect(self._filter_changed)
            group.addButton(button)
            layout.insertWidget(layout.count(), button)
            buttons[key] = button
            self._config_widgets.append(button)
            first = first or button
            if key.lower() == selected_key or label.lower() == selected_key:
                button.setChecked(True)
        if group.checkedButton() is None and first is not None:
            first.setChecked(True)
        setattr(self, attr_name, buttons)
        return group

    def _populate_combo(self, combo: ComboBox, options, all_label: str | None, selected):
        combo.clear()
        if all_label is not None:
            combo.addItem(all_label, userData=None)
        for label, value in options:
            if all_label is not None and (value in (None, "") or label.lower().startswith("all ")):
                continue
            combo.addItem(label, userData=value)
        target = str(_plain(selected)) if selected is not None else None
        if target is not None:
            for index in range(combo.count()):
                if (
                    str(_plain(combo.itemData(index))) == target
                    or combo.itemText(index).strip().lower() == target.strip().lower()
                ):
                    combo.setCurrentIndex(index)
                    break
        if combo.count() and combo.currentIndex() < 0:
            combo.setCurrentIndex(0)

    def _checked_value(self, group: QButtonGroup | None, default=None):
        button = group.checkedButton() if group else None
        return _plain(button.property("filterValue")) if button else default

    def _collect_filter_state(self) -> dict[str, Any]:
        return {
            "statuses": [_plain(button.property("filterValue")) for button in self._status_buttons.values() if button.isChecked()],
            "family_id": _plain(self._family_combo.currentData()) if hasattr(self, "_family_combo") else None,
            "category_id": _plain(self._category_combo.currentData()) if hasattr(self, "_category_combo") else None,
            "source_id": _plain(self._source_combo.currentData()) if hasattr(self, "_source_combo") else None,
            "stock": self._checked_value(self._stock_group, "In stock"),
            "completeness_locale": _plain(self._locale_combo.currentData()) if hasattr(self, "_locale_combo") else "Overall",
            "completeness_buckets": [
                _plain(button.property("filterValue"))
                for button in self._bucket_buttons.values()
                if button.isChecked()
            ],
            "sort": _plain(self._sort_combo.currentData()) if hasattr(self, "_sort_combo") else "Recent",
        }

    def _filter_changed(self, *_args):
        if not self._restoring_filters:
            self._save_filter_state()

    def _load_filter_state(self) -> dict[str, Any]:
        raw = self._setting_get(FILTER_SETTING, "")
        try:
            value = json.loads(raw) if raw else {}
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def _save_filter_state(self):
        if self._restoring_filters:
            return
        try:
            self._setting_set(FILTER_SETTING, json.dumps(self._collect_filter_state(), ensure_ascii=False))
        except Exception:
            pass

    # --------------------------------------------------------------- Service

    def _make_service(self, driver):
        factory = self._external_service_factory
        if factory is None:
            return _service_factory(driver, self._image_driver_factory)
        if hasattr(factory, "run") and hasattr(factory, "discover_filter_options"):
            return factory
        return factory(driver)

    def _create_run_config(self):
        from tools.orbea_automation import OrbeaRunConfig, PimboFilterSpec

        state = self._collect_filter_state()
        filter_values = {
            **state,
            "statuses": tuple(state.get("statuses") or ()),
            "family_id": state.get("family_id") or "",
            "category_id": state.get("category_id") or "",
            "source_id": state.get("source_id") or "",
            "stock": state.get("stock") or "Any",
            "completeness_locale": state.get("completeness_locale") or "Overall",
            "completeness_buckets": tuple(state.get("completeness_buckets") or ()),
            "sort": state.get("sort") or "Recent",
        }
        filter_aliases = {
            "status": "statuses",
            "status_values": "statuses",
            "family": "family_id",
            "family_value": "family_id",
            "category": "category_id",
            "category_value": "category_id",
            "source": "source_id",
            "source_value": "source_id",
            "stock_status": "stock",
            "locale": "completeness_locale",
            "completeness": "completeness_bucket",
            "sort_order": "sort",
        }
        filters = _create_model(PimboFilterSpec, filter_values, filter_aliases)
        config_values = {
            "catalogue_path": Path(self._catalogue_edit.text().strip()),
            "output_root": Path(self._output_edit.text().strip()),
            "filters": filters,
            "all_products": True,
            "download_images": True,
            "browser_name": str(self._setting_get("browser_choice", "Chrome") or "Chrome").strip().lower(),
        }
        config_aliases = {
            "catalogue": "catalogue_path",
            "catalog_path": "catalogue_path",
            "output_dir": "output_root",
            "filter_spec": "filters",
        }
        return _create_model(OrbeaRunConfig, config_values, config_aliases)

    def _make_description_service(self):
        factory = self._external_description_service_factory
        if factory is None:
            from tools.orbea_automation import OrbeaDescriptionService

            return OrbeaDescriptionService()
        if not inspect.isclass(factory) and hasattr(factory, "run"):
            return factory
        return factory()

    def _description_urls(self) -> tuple[str, ...]:
        candidates = re.findall(
            r"https?://[^\s,;]+",
            self._description_urls_edit.toPlainText(),
            flags=re.IGNORECASE,
        )
        urls: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            url = candidate.rstrip(".\"'()[]{}<>")
            if not re.match(r"^https?://cms\.orbea\.com/.+/m/[^/?#]+", url, re.IGNORECASE):
                continue
            key = url.lower()
            if key not in seen:
                urls.append(url)
                seen.add(key)
        return tuple(urls)

    def _create_description_config(self):
        from tools.orbea_automation import DescriptionRunConfig

        values = {
            "urls": self._description_urls(),
            "output_dir": Path(self._description_output_edit.text().strip()),
            "browser_name": str(self._setting_get("browser_choice", "Chrome") or "Chrome").strip().lower(),
            "show_browser": False,
            "headless": True,
        }
        aliases = {
            "orbea_urls": "urls",
            "input_urls": "urls",
            "output_root": "output_dir",
            "destination": "output_dir",
            "browser": "browser_name",
        }
        return _create_model(DescriptionRunConfig, values, aliases)

    def _auto_refresh_filters(self):
        if getattr(self.main, "driver", None) is not None and not self.is_running():
            self.refresh_filter_options(show_errors=False)

    def refresh_filter_options(self, *_args, show_errors=True):
        if self.is_running():
            return
        # ``shutdown()`` is also used during logout. A later login may reuse
        # this lazily-created screen, so a new user action re-enables callbacks.
        self._closing = False
        driver = getattr(self.main, "driver", None)
        if driver is None:
            if show_errors:
                self._warn(self._t("common.error", "Not connected"), self._t("batchdesc.no_session", "Log in to Pimbo first."))
            return
        if not self._acquire_browser():
            self._warn(self._t("orbea.browser.busy.title", "Browser busy"), self._t("orbea.browser.busy", "Another tool is using Pimbo."))
            return
        self._filter_state_label.setText(self._t("orbea.filters.loading", "Loading Pimbo filters…"))
        self._refresh_btn.setEnabled(False)
        self._filter_worker = OrbeaFilterWorker(driver, self._make_service)
        self._filter_worker.loaded.connect(self._filters_loaded)
        self._filter_worker.failed.connect(lambda message: self._filters_failed(message, show_errors))
        self._filter_worker.finished.connect(self._filter_finished)
        self._filter_worker.start()
        self._update_action_states()

    def _filters_loaded(self, options):
        if self._closing:
            return
        self._apply_filter_options(options)
        self._filter_state_label.setText(self._t("orbea.filters.loaded", "Filters loaded from Pimbo"))

    def _filters_failed(self, message: str, show_errors: bool):
        self._filter_state_label.setText(self._t("orbea.filters.defaults", "Using saved/default filters"))
        self._append_log(f"Filter discovery: {message}")
        if show_errors and not self._closing:
            self._warn(self._t("orbea.filters.error.title", "Could not load filters"), message)

    def _filter_finished(self):
        self._filter_worker = None
        self._refresh_btn.setEnabled(True)
        self._release_browser()
        self._update_action_states()

    # --------------------------------------------------------------- Running

    def _on_start_stop(self):
        if self._worker and self._worker.isRunning():
            self._worker.request_stop()
            self._start_btn.setEnabled(False)
            self._stage_label.setText(self._t("orbea.stopping", "Stopping safely…"))
            return
        # The primary action automatically resumes the newest compatible run.
        self._start_run(resume=True, retry_failed=False)

    def _start_run(
        self,
        *,
        resume: bool,
        retry_failed: bool,
        require_existing: bool = False,
    ):
        if self.is_running() or not self._validate_inputs():
            return
        self._closing = False
        driver = getattr(self.main, "driver", None)
        if driver is None:
            self._warn(self._t("common.error", "Not connected"), self._t("batchdesc.no_session", "Log in to Pimbo first."))
            return
        try:
            config = self._create_run_config()
        except Exception as exc:
            self._error(self._t("orbea.service.error.title", "Orbea service unavailable"), str(exc))
            return
        if require_existing:
            try:
                from tools.orbea_automation import find_latest_compatible_run

                existing = find_latest_compatible_run(
                    config,
                    include_completed_errors=retry_failed,
                )
            except Exception as exc:
                self._error(self._t("orbea.service.error.title", "Orbea service unavailable"), str(exc))
                return
            if existing is None:
                self._warn(
                    self._t("orbea.resume.none.title", "Nothing to resume"),
                    self._t(
                        "orbea.retry.none" if retry_failed else "orbea.resume.none",
                        "No compatible run with retryable errors was found."
                        if retry_failed
                        else "No compatible incomplete run was found.",
                    ),
                )
                return
        if not self._acquire_browser():
            self._warn(self._t("orbea.browser.busy.title", "Browser busy"), self._t("orbea.browser.busy", "Another tool is using Pimbo."))
            return

        self._save_paths()
        self._save_filter_state()
        self._table.setRowCount(0)
        self._workbook_path = None
        self._run_dir = None
        self._open_excel_btn.setEnabled(False)
        self._open_folder_btn.setEnabled(False)
        self._log.clear()
        self._progress.setValue(0)
        self._set_busy(True)
        self._worker = OrbeaRunWorker(
            driver,
            self._make_service,
            config,
            resume=resume,
            retry_failed=retry_failed,
        )
        self._worker.progress_changed.connect(self._on_progress)
        self._worker.log_message.connect(self._append_log)
        self._worker.succeeded.connect(self._on_result)
        self._worker.failed.connect(self._on_run_error)
        self._worker.finished.connect(self._run_thread_finished)
        self._worker.start()

    def _on_progress(self, update):
        stage = str(_plain(_read(update, "stage", "phase", default="Running")) or "Running")
        message = str(_read(update, "message", "detail", default="") or "")
        current = int(_read(update, "current", "done", default=0) or 0)
        total = int(_read(update, "total", default=0) or 0)
        eta = _read(update, "eta_seconds", "eta", default=None)
        self._stage_label.setText(stage.replace("_", " ").title())
        self._progress_label.setText(message or (f"{current:,} / {total:,}" if total else f"{current:,}"))
        self._progress.setValue(max(0, min(100, int(current * 100 / total)))) if total else self._progress.setValue(0)
        self._eta_label.setText(self._format_eta(eta))
        self._update_counts(_read(update, "counts", default={}) or {})

    def _on_result(self, result):
        workbook = _read(result, "workbook_path", "excel_path")
        run_dir = _read(result, "run_dir", "output_dir")
        self._workbook_path = Path(workbook) if workbook else None
        self._run_dir = Path(run_dir) if run_dir else (self._workbook_path.parent if self._workbook_path else None)
        self._update_counts(_read(result, "counts", default={}) or {})
        if self._workbook_path and self._workbook_path.exists():
            self._load_workbook_preview(self._workbook_path)
        cancelled = bool(_read(result, "cancelled", default=False))
        completed = bool(_read(result, "completed", default=not cancelled))
        if cancelled:
            self._stage_label.setText(self._t("orbea.cancelled", "Stopped — partial report saved"))
        elif completed:
            self._stage_label.setText(self._t("orbea.complete", "Complete"))
            self._progress.setValue(100)
        else:
            self._stage_label.setText(self._t("orbea.incomplete", "Incomplete — ready to resume"))

    def _on_run_error(self, message: str):
        self._stage_label.setText(self._t("orbea.failed", "Run failed — progress was checkpointed"))
        self._append_log(message)
        if not self._closing:
            self._error(self._t("orbea.failed.title", "Orbea automation failed"), message)

    def _run_thread_finished(self):
        self._worker = None
        self._set_busy(False)
        self._release_browser()
        self._open_excel_btn.setEnabled(bool(self._workbook_path and self._workbook_path.exists()))
        self._open_folder_btn.setEnabled(bool(self._run_dir and self._run_dir.exists()))
        self._update_action_states()

    def _sort_existing_excel(self):
        if self.is_running():
            return
        start = (
            self._workbook_path.parent
            if self._workbook_path and self._workbook_path.exists()
            else self._desktop_dir()
        )
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._t("orbea.excel_sort.pick", "Select Orbea match Excel"),
            str(start),
            "Excel (*.xlsx)",
        )
        if not path:
            return

        self._excel_sort_btn.setEnabled(False)
        self._stage_label.setText(
            self._t("orbea.excel_sort.running", "Sorting existing Excel…")
        )
        self._append_log(f"Sorting existing Excel: {path}")
        self._excel_sort_worker = OrbeaExcelSortWorker(Path(path))
        self._excel_sort_worker.succeeded.connect(self._on_excel_sorted)
        self._excel_sort_worker.failed.connect(self._on_excel_sort_error)
        self._excel_sort_worker.finished.connect(self._excel_sort_finished)
        self._excel_sort_worker.start()
        self._update_action_states()

    def _on_excel_sorted(self, path: str):
        self._workbook_path = Path(path)
        self._run_dir = self._workbook_path.parent
        self._load_workbook_preview(self._workbook_path)
        self._open_excel_btn.setEnabled(True)
        self._open_folder_btn.setEnabled(True)
        self._stage_label.setText(
            self._t("orbea.excel_sort.complete", "Excel sorted")
        )
        self._append_log(f"Sorted Excel saved: {self._workbook_path}")
        InfoBar.success(
            self._t("orbea.excel_sort.complete", "Excel sorted"),
            self._t(
                "orbea.excel_sort.saved",
                "A clean sorted copy was saved next to the selected file.",
            ),
            parent=self,
            position=InfoBarPosition.TOP,
            duration=4500,
        )

    def _on_excel_sort_error(self, message: str):
        self._stage_label.setText(
            self._t("orbea.excel_sort.failed", "Excel sorting failed")
        )
        self._append_log(message)
        if not self._closing:
            self._error(
                self._t("orbea.excel_sort.failed", "Excel sorting failed"),
                message,
            )

    def _excel_sort_finished(self):
        self._excel_sort_worker = None
        self._update_action_states()

    def _set_busy(self, busy: bool):
        for widget in self._config_widgets:
            widget.setEnabled(not busy)
        self._resume_btn.setEnabled(not busy)
        self._retry_btn.setEnabled(not busy)
        for widget in self._description_config_widgets:
            widget.setEnabled(not busy)
        self._description_start_btn.setEnabled(not busy)
        if busy:
            self._start_btn.setText(self._t("orbea.stop", "Stop"))
            self._start_btn.setIcon(FluentIcon.CLOSE)
            self._start_btn.setEnabled(True)
            self._stage_label.setText(self._t("orbea.starting", "Starting…"))
        else:
            self._start_btn.setText(self._t("orbea.start", "Start"))
            self._start_btn.setIcon(FluentIcon.PLAY)

    # --------------------------------------------------- Description extractor

    def _on_description_start_stop(self):
        if self._description_worker and self._description_worker.isRunning():
            self._description_worker.request_stop()
            self._description_start_btn.setEnabled(False)
            self._description_status_label.setText(
                self._t("orbea.description.stopping", "Stopping safely…")
            )
            return
        if self.is_running() or not self._validate_description_inputs():
            return
        self._closing = False
        try:
            config = self._create_description_config()
        except Exception as exc:
            self._error(
                self._t("orbea.description.service_error.title", "Description extractor unavailable"),
                str(exc),
            )
            return

        self._save_description_output()
        self._description_output_dir = Path(self._description_output_edit.text().strip())
        self._description_open_btn.setEnabled(False)
        self._description_log.clear()
        self._description_progress.setValue(0)
        self._set_description_busy(True)
        self._description_worker = OrbeaDescriptionWorker(self._make_description_service, config)
        self._description_worker.progress_changed.connect(self._on_description_progress)
        self._description_worker.log_message.connect(self._append_description_log)
        self._description_worker.succeeded.connect(self._on_description_result)
        self._description_worker.failed.connect(self._on_description_error)
        self._description_worker.finished.connect(self._description_thread_finished)
        self._description_worker.start()

    def _validate_description_inputs(self) -> bool:
        if not self._description_urls():
            self._warn(
                self._t("orbea.description.urls_invalid.title", "Orbea URL required"),
                self._t(
                    "orbea.description.urls_invalid",
                    "Paste one or more cms.orbea.com model URLs containing /m/.",
                ),
            )
            return False
        if not self._description_output_edit.text().strip():
            self._warn(
                self._t("orbea.description.output_invalid.title", "Output folder required"),
                self._t("orbea.description.output_invalid", "Choose where extracted text should be saved."),
            )
            return False
        return True

    def _on_description_progress(self, update):
        status = str(_read(update, "status", "stage", default="Extracting") or "Extracting")
        current = int(_read(update, "current", "done", default=0) or 0)
        total = int(_read(update, "total", default=0) or 0)
        message = str(_read(update, "message", "url", default="") or "")
        succeeded = int(_read(update, "succeeded", default=0) or 0)
        failed = int(_read(update, "failed", default=0) or 0)
        self._description_status_label.setText(status.replace("_", " ").title())
        if message:
            self._description_progress_label.setText(message)
        elif total:
            self._description_progress_label.setText(
                self._t(
                    "orbea.description.progress",
                    "{current:,} / {total:,} URLs • {succeeded:,} saved • {failed:,} failed",
                    current=current,
                    total=total,
                    succeeded=succeeded,
                    failed=failed,
                )
            )
        self._description_progress.setValue(
            max(0, min(100, int(current * 100 / total))) if total else 0
        )

    def _on_description_result(self, result):
        output_dir = _read(result, "output_dir", "output_root", default=None)
        if output_dir:
            self._description_output_dir = Path(output_dir)
        files = _read(result, "files", "written_files", "paths", default=()) or ()
        succeeded = int(_read(result, "succeeded", default=len(files)) or 0)
        failures = _read(result, "failures", default=()) or ()
        cancelled = bool(_read(result, "cancelled", default=False))
        if cancelled:
            self._description_status_label.setText(
                self._t("orbea.description.stopped", "Stopped — completed text files were kept")
            )
        else:
            self._description_status_label.setText(
                self._t("orbea.description.complete", "Description extraction complete")
            )
            self._description_progress.setValue(100)
        self._description_progress_label.setText(
            self._t(
                "orbea.description.result",
                "{succeeded:,} saved • {failed:,} failed",
                succeeded=succeeded,
                failed=len(failures),
            )
        )

    def _on_description_error(self, message: str):
        self._description_status_label.setText(
            self._t("orbea.description.failed", "Description extraction failed")
        )
        self._append_description_log(message)
        if not self._closing:
            self._error(
                self._t("orbea.description.failed.title", "Description extraction failed"),
                message,
            )

    def _description_thread_finished(self):
        self._description_worker = None
        self._set_description_busy(False)
        self._description_open_btn.setEnabled(
            bool(self._description_output_dir and self._description_output_dir.exists())
        )
        self._update_action_states()

    def _set_description_busy(self, busy: bool):
        for widget in self._config_widgets:
            widget.setEnabled(not busy)
        self._start_btn.setEnabled(not busy)
        self._resume_btn.setEnabled(not busy)
        self._retry_btn.setEnabled(not busy)
        for widget in self._description_config_widgets:
            widget.setEnabled(not busy)
        if busy:
            self._description_start_btn.setText(self._t("orbea.description.stop", "Stop"))
            self._description_start_btn.setIcon(FluentIcon.CLOSE)
            self._description_start_btn.setEnabled(True)
            self._description_status_label.setText(
                self._t("orbea.description.starting", "Starting description extraction…")
            )
        else:
            self._description_start_btn.setText(
                self._t("orbea.description.extract", "Extract descriptions")
            )
            self._description_start_btn.setIcon(FluentIcon.PLAY)

    def _update_counts(self, counts: Any):
        aliases = {
            "scanned": ("scanned", "products_scanned", "processed"),
            "matched": ("matched", "matches", "code_matches"),
            "review": ("review", "review_count", "needs_review"),
            "images": ("images", "images_downloaded", "downloaded"),
            "unavailable": ("unavailable", "not_available", "tables_not_available"),
            "errors": ("errors", "error_count", "transient_errors"),
        }
        for key, names in aliases.items():
            value = _read(counts, *names, default=None)
            if value is not None:
                self._stat_values[key].setText(str(value))

    # -------------------------------------------------------------- Results

    def _load_workbook_preview(self, path: Path):
        rows: list[list[str]] = []
        total_rows = 0
        try:
            workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
            for sheet_name, review_sheet in (("Matches", False), ("Review", True)):
                if sheet_name not in workbook.sheetnames:
                    continue
                sheet = workbook[sheet_name]
                iterator = sheet.iter_rows(values_only=True)
                headers = [str(value or "").strip() for value in next(iterator, ())]
                lookup = {name.lower(): index for index, name in enumerate(headers)}
                for source in iterator:
                    total_rows += 1
                    if len(rows) >= PREVIEW_LIMIT:
                        continue
                    rows.append([
                        self._cell(source, lookup, "variant sku", "pimbo sku", "sku"),
                        self._cell(source, lookup, "pimbo product", "product", "product title"),
                        self._cell(source, lookup, "match method", "status", "reason") or ("Review" if review_sheet else "Match"),
                        self._cell(source, lookup, "orbea url", "catalogue url"),
                        self._cell(source, lookup, "geometry status", "geometry", "geometry image"),
                        self._cell(source, lookup, "size guide status", "size status", "size guide", "size image"),
                    ])
            workbook.close()
        except Exception as exc:
            self._append_log(f"Could not preview workbook: {exc}")
            return

        self._table.setUpdatesEnabled(False)
        self._table.setRowCount(len(rows))
        for row_index, values in enumerate(rows):
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 2:
                    lower = value.lower()
                    item.setForeground(QColor(COLORS["success"] if "code" in lower or lower == "match" else COLORS["warning"]))
                self._table.setItem(row_index, column, item)
        self._table.setUpdatesEnabled(True)
        self._results_label.setText(
            self._t("orbea.results.preview", "Showing {shown:,} of {total:,} rows. Excel contains the complete report.", shown=len(rows), total=total_rows)
        )

    @staticmethod
    def _cell(row, lookup: dict[str, int], *names: str) -> str:
        for name in names:
            index = lookup.get(name.lower())
            if index is not None and index < len(row):
                return str(row[index] or "")
        return ""

    # --------------------------------------------------------------- Paths

    def _load_paths(self):
        catalogue = str(self._setting_get(CATALOGUE_SETTING, "") or "").strip()
        output = str(self._setting_get(OUTPUT_SETTING, "") or "").strip()
        description_output = str(
            self._setting_get(DESCRIPTION_OUTPUT_SETTING, "") or ""
        ).strip()
        if not catalogue:
            catalogue = self._detect_catalogue()
        if not output:
            output = str(self._desktop_dir() / "UltraBike Orbea Runs")
        if not description_output:
            description_output = str(self._desktop_dir() / "UltraBike Orbea Descriptions")
        self._catalogue_edit.setText(catalogue)
        self._output_edit.setText(output)
        self._description_output_edit.setText(description_output)
        candidate = Path(description_output)
        self._description_output_dir = candidate if candidate.exists() else None

    def _detect_catalogue(self) -> str:
        candidates = [
            self._desktop_dir() / "Orbea-Scraper" / "data" / "output" / "orbea_bicycle_catalogue.xlsx",
            Path.cwd() / "Orbea-Scraper" / "data" / "output" / "orbea_bicycle_catalogue.xlsx",
            Path(__file__).resolve().parents[2] / "data" / "output" / "orbea_bicycle_catalogue.xlsx",
        ]
        return str(next((path for path in candidates if path.is_file()), ""))

    @staticmethod
    def _desktop_dir() -> Path:
        candidates = [Path.home() / "Desktop", Path.home() / "OneDrive" / "Desktop"]
        return next((path for path in candidates if path.exists()), candidates[0])

    def _browse_catalogue(self):
        path, _ = QFileDialog.getOpenFileName(self, self._t("orbea.catalogue.pick", "Select Orbea catalogue"), self._catalogue_edit.text(), "Excel (*.xlsx)")
        if path:
            self._catalogue_edit.setText(path)
            self._paths_changed()

    def _browse_output(self):
        path = QFileDialog.getExistingDirectory(self, self._t("orbea.output.pick", "Select output folder"), self._output_edit.text())
        if path:
            self._output_edit.setText(path)
            self._paths_changed()

    def _browse_description_output(self):
        path = QFileDialog.getExistingDirectory(
            self,
            self._t("orbea.description.output.pick", "Select description output folder"),
            self._description_output_edit.text(),
        )
        if path:
            self._description_output_edit.setText(path)
            self._description_output_changed()

    def _description_output_changed(self):
        self._save_description_output()
        path = Path(self._description_output_edit.text().strip())
        self._description_output_dir = path if path.exists() else None
        self._description_open_btn.setEnabled(bool(self._description_output_dir))
        self._update_action_states()

    def _paths_changed(self):
        self._save_paths()
        self._update_action_states()

    def _save_paths(self):
        self._setting_set(CATALOGUE_SETTING, self._catalogue_edit.text().strip())
        self._setting_set(OUTPUT_SETTING, self._output_edit.text().strip())

    def _save_description_output(self):
        self._setting_set(
            DESCRIPTION_OUTPUT_SETTING,
            self._description_output_edit.text().strip(),
        )

    def _validate_inputs(self) -> bool:
        catalogue = Path(self._catalogue_edit.text().strip())
        if not catalogue.is_file() or catalogue.suffix.lower() != ".xlsx":
            self._warn(self._t("orbea.catalogue.invalid.title", "Catalogue required"), self._t("orbea.catalogue.invalid", "Choose the Orbea catalogue .xlsx file."))
            return False
        if not self._output_edit.text().strip():
            self._warn(self._t("orbea.output.invalid.title", "Output folder required"), self._t("orbea.output.invalid", "Choose where Orbea run folders should be saved."))
            return False
        return True

    def _open_excel(self):
        if self._workbook_path and self._workbook_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._workbook_path)))

    def _open_folder(self):
        if self._run_dir and self._run_dir.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._run_dir)))

    def _open_description_folder(self):
        if self._description_output_dir and self._description_output_dir.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._description_output_dir)))

    # ---------------------------------------------------------- App lifecycle

    def _acquire_browser(self) -> bool:
        acquire = getattr(self.main, "try_acquire_browser_lease", None)
        if callable(acquire) and not acquire(self):
            return False
        self._owns_browser_lease = True
        navigation = getattr(self.main, "navigationInterface", None)
        if navigation is not None:
            navigation.setEnabled(False)
        return True

    def _release_browser(self):
        if not self._owns_browser_lease:
            return
        release = getattr(self.main, "release_browser_lease", None)
        if callable(release):
            try:
                release(self)
            except Exception:
                pass
        self._owns_browser_lease = False
        navigation = getattr(self.main, "navigationInterface", None)
        if navigation is not None:
            navigation.setEnabled(True)

    def is_running(self) -> bool:
        return bool(
            (self._worker and self._worker.isRunning())
            or (self._filter_worker and self._filter_worker.isRunning())
            or (self._description_worker and self._description_worker.isRunning())
            or (self._excel_sort_worker and self._excel_sort_worker.isRunning())
        )

    def shutdown(self, wait_ms: int = 5000) -> bool:
        """Request a checkpointed stop and wait briefly; never terminate threads."""
        self._closing = True
        workers = [
            worker
            for worker in (
                self._worker,
                self._filter_worker,
                self._description_worker,
                self._excel_sort_worker,
            )
            if worker and worker.isRunning()
        ]
        for worker in workers:
            worker.request_stop()
        remaining = max(0, int(wait_ms))
        for worker in workers:
            if not worker.isRunning():
                continue
            slice_ms = remaining if len(workers) == 1 else max(1, remaining // len(workers))
            if not worker.wait(slice_ms):
                self._closing = False
                return False
            remaining = max(0, remaining - slice_ms)
        self._release_browser()
        return True

    # ------------------------------------------------------------- Utilities

    def _setting_get(self, key: str, default=None):
        try:
            return self.settings.get(key, default) if self.settings is not None else default
        except Exception:
            return default

    def _setting_set(self, key: str, value):
        try:
            if self.settings is not None:
                self.settings.set(key, value)
        except Exception:
            pass

    def _update_action_states(self):
        main_running = bool(self._worker and self._worker.isRunning())
        filter_running = bool(self._filter_worker and self._filter_worker.isRunning())
        excel_sort_running = self._excel_sort_worker is not None
        description_running = bool(
            self._description_worker and self._description_worker.isRunning()
        )
        if excel_sort_running:
            for widget in self._config_widgets:
                widget.setEnabled(False)
            for widget in self._description_config_widgets:
                widget.setEnabled(False)
            self._start_btn.setEnabled(False)
            self._resume_btn.setEnabled(False)
            self._retry_btn.setEnabled(False)
            self._description_start_btn.setEnabled(False)
            return
        if main_running:
            for widget in self._description_config_widgets:
                widget.setEnabled(False)
            self._description_start_btn.setEnabled(False)
            return
        if description_running:
            for widget in self._config_widgets:
                widget.setEnabled(False)
            for widget in self._description_config_widgets:
                widget.setEnabled(False)
            self._start_btn.setEnabled(False)
            self._resume_btn.setEnabled(False)
            self._retry_btn.setEnabled(False)
            self._description_start_btn.setEnabled(True)
            return

        for widget in self._config_widgets:
            widget.setEnabled(not filter_running)
        for widget in self._description_config_widgets:
            widget.setEnabled(not filter_running)
        valid = bool(
            getattr(self.main, "driver", None) is not None
            and Path(self._catalogue_edit.text().strip()).is_file()
            and self._output_edit.text().strip()
            and not filter_running
        )
        self._start_btn.setEnabled(valid)
        self._resume_btn.setEnabled(valid)
        self._retry_btn.setEnabled(valid)
        self._description_start_btn.setEnabled(
            bool(
                not filter_running
                and self._description_urls()
                and self._description_output_edit.text().strip()
            )
        )

    @staticmethod
    def _format_eta(seconds: Any) -> str:
        try:
            seconds = max(0, int(float(seconds)))
        except (TypeError, ValueError):
            return "ETA —"
        minutes, secs = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"ETA {hours}h {minutes:02d}m" if hours else f"ETA {minutes}m {secs:02d}s"

    def _append_log(self, message: str):
        if message:
            self._log.appendPlainText(str(message))

    def _append_description_log(self, message: str):
        if message:
            self._description_log.appendPlainText(str(message))

    def _t(self, key: str, fallback: str, **kwargs) -> str:
        value = self.tr(key, **kwargs)
        if value == key:
            try:
                return fallback.format(**kwargs)
            except Exception:
                return fallback
        return value

    def _warn(self, title: str, message: str):
        InfoBar.warning(title, message, parent=self, position=InfoBarPosition.TOP, duration=4500)

    def _error(self, title: str, message: str):
        InfoBar.error(title, message, parent=self, position=InfoBarPosition.TOP, duration=6000)

    def _update_table_theme(self):
        dark = isDarkTheme()
        table = COMPONENT_COLORS["table"]
        bg = table["row_alt_bg_dark"] if dark else table["row_alt_bg_light"]
        alt = table["row_bg_dark"] if dark else table["row_bg_light"]
        border = table["border_dark"] if dark else table["border_light"]
        text = COLORS["text_primary_dark"] if dark else COLORS["text_primary_light"]
        header_bg = COLORS["lavender_grey"] if dark else COLORS["space_indigo"]
        header_text = COLORS["space_indigo"] if dark else COLORS["text_white"]
        self._table.setStyleSheet(f"""
            QTableWidget {{ background: {bg}; alternate-background-color: {alt}; color: {text}; border: 1px solid {border}; border-radius: {RADII['md']}px; gridline-color: {border}; }}
            QTableWidget::item {{ padding: {PADDINGS['table_cell']}; }}
            QHeaderView::section {{ background: {header_bg}; color: {header_text}; padding: {PADDINGS['table_header']}; border: none; font-weight: 600; font-size: {FONTS['size_body_sm']}; }}
        """)

    def retranslate_ui(self):
        self.tr = self.main.i18n.tr
        self._title.setText(self._t("orbea.title", "Orbea Automation"))
        self._subtitle.setText(self._t("orbea.subtitle", "Match filtered Pimbo products and download Orbea geometry and CM size tables."))
        self._paths_title.setText(self._t("orbea.paths", "Catalogue and output"))
        self._catalogue_label.setText(self._t("orbea.catalogue", "Catalogue"))
        self._output_label.setText(self._t("orbea.output", "Output folder"))
        self._search_label.setText(self._t("orbea.search", "Fixed Pimbo search"))
        self._catalogue_btn.setText(self._t("common.browse", "Browse"))
        self._output_btn.setText(self._t("common.browse", "Browse"))
        self._filters_title.setText(self._t("orbea.filters", "Pimbo filters"))
        self._refresh_btn.setText(self._t("orbea.filters.refresh", "Refresh filters"))
        self._status_label.setText(self._t("orbea.filters.status", "Status (select any)"))
        self._family_label.setText(self._t("orbea.filters.family", "Family"))
        self._category_label.setText(self._t("orbea.filters.category", "Category"))
        self._source_label.setText(self._t("orbea.filters.source", "Source"))
        self._locale_label.setText(self._t("orbea.filters.locale", "Completeness locale"))
        self._sort_label.setText(self._t("orbea.filters.sort", "Sort"))
        self._stock_label.setText(self._t("orbea.filters.stock", "Stock"))
        self._bucket_label.setText(self._t("orbea.filters.completeness", "Completeness"))
        running = bool(self._worker and self._worker.isRunning())
        self._start_btn.setText(self._t("orbea.stop", "Stop") if running else self._t("orbea.start", "Start"))
        self._resume_btn.setText(self._t("orbea.resume", "Resume latest"))
        self._retry_btn.setText(self._t("orbea.retry", "Retry failed"))
        self._excel_sort_btn.setText(
            self._t("orbea.excel_sort", "Sort existing Excel")
        )
        self._excel_sort_btn.setToolTip(
            self._t(
                "orbea.excel_sort.tooltip",
                "Create a clean five-column copy sorted by Catalogue Model.",
            )
        )
        self._open_excel_btn.setText(self._t("orbea.open_excel", "Open Excel"))
        self._open_folder_btn.setText(self._t("orbea.open_folder", "Open folder"))
        self._description_title.setText(
            self._t("orbea.description.title", "Description extractor")
        )
        self._description_subtitle.setText(
            self._t(
                "orbea.description.subtitle",
                "Paste Orbea model URLs to save all visible, expanded, and carousel description text.",
            )
        )
        self._description_urls_label.setText(
            self._t("orbea.description.urls", "Orbea model URLs")
        )
        self._description_urls_edit.setPlaceholderText(
            self._t(
                "orbea.description.urls.placeholder",
                "One URL per line, for example:\nhttps://cms.orbea.com/en-au/m/kemen-adv",
            )
        )
        self._description_output_label.setText(
            self._t("orbea.description.output", "Description output folder")
        )
        self._description_output_btn.setText(self._t("common.browse", "Browse"))
        description_running = bool(
            self._description_worker and self._description_worker.isRunning()
        )
        self._description_start_btn.setText(
            self._t("orbea.description.stop", "Stop")
            if description_running
            else self._t("orbea.description.extract", "Extract descriptions")
        )
        self._description_open_btn.setText(
            self._t("orbea.description.open_folder", "Open descriptions folder")
        )
        if not self._description_status_label.text():
            self._description_status_label.setText(
                self._t("orbea.description.ready", "Description extractor ready")
            )
        if not self._description_progress_label.text():
            self._description_progress_label.setText(
                self._t(
                    "orbea.description.ready.detail",
                    "Paste one or more /m/ URLs, then extract.",
                )
            )
        if not self._stage_label.text():
            self._stage_label.setText(self._t("orbea.ready", "Ready"))
        if not self._eta_label.text():
            self._eta_label.setText("ETA —")
        if not self._progress_label.text():
            self._progress_label.setText(self._t("orbea.ready.detail", "Choose filters, then start the complete workflow."))
        stat_text = {
            "scanned": self._t("orbea.stat.scanned", "Scanned"),
            "matched": self._t("orbea.stat.matched", "Matched"),
            "review": self._t("orbea.stat.review", "Review"),
            "images": self._t("orbea.stat.images", "Images"),
            "unavailable": self._t("orbea.stat.unavailable", "Not available"),
            "errors": self._t("orbea.stat.errors", "Errors"),
        }
        for key, text in stat_text.items():
            self._stat_labels[key].setText(text)
        self._table.setHorizontalHeaderLabels([
            self._t("orbea.col.sku", "Variant SKU"),
            self._t("orbea.col.product", "Pimbo product"),
            self._t("orbea.col.match", "Match"),
            self._t("orbea.col.url", "Orbea URL"),
            self._t("orbea.col.geometry", "Geometry"),
            self._t("orbea.col.size", "Size guide"),
        ])
        if not self._results_label.text():
            self._results_label.setText(self._t("orbea.results.empty", "Results will appear here; Excel always contains the complete run."))
        self._update_table_theme()

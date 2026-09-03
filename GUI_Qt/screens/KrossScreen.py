"""Two-phase filtered PIMBO → KROSS collection and local upload screen."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QFileDialog, QGridLayout, QHBoxLayout,
    QHeaderView, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    BodyLabel, CaptionLabel, CardWidget, CheckBox, ComboBox, FlowLayout,
    FluentIcon, InfoBar, InfoBarPosition, LineEdit, PillPushButton, PlainTextEdit,
    PrimaryPushButton, ProgressBar, PushButton, ScrollArea, TitleLabel,
    isDarkTheme, qconfig,
)

from Managers.PimboProductEditor import PimPreparationStatus
from GUI_Qt.kross.workers import (
    KrossCollectionWorker, KrossFilterWorker, KrossSkuCollectionWorker,
    KrossUploadWorker,
)
from GUI_Qt.styles.screen_theme import (
    CARD_MARGINS, CARD_SPACING, CONTENT_SPACING, PAGE_MARGINS, PAGE_SPACING,
    ROW_SPACING, apply_screen_theme, enforce_transparent_labels,
)
from GUI_Qt.styles.theme_config import get_text_color
from GUI_Qt.widgets import enable_table_copy
from GUI_Qt.widgets.ResponsiveWidget import ResponsiveWidget
from tools.kross_automation import (
    KrossAutomationService, KrossCollectionOptions, KrossDiscoveryResult,
    KrossMatch, KrossUploadResult, KrossWorkflowOptions, parse_collection_targets,
)
from tools.orbea_automation import PimboFilterSpec


OUTPUT_SETTING = "kross_automation_output_root"
FILTER_SETTING = "kross_filter_preset"
STAGE_FIELDS = KrossWorkflowOptions.STAGES
COLLECTION_FIELDS = KrossCollectionOptions.STAGES


def _plain(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _read(value: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(value, Mapping) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
    return default


class KrossScreen(ResponsiveWidget):
    """Collect KROSS data first, then upload any selected stages from disk."""

    def __init__(
        self,
        main_window,
        *,
        settings_manager=None,
        service_factory: Callable[[Any], KrossAutomationService] | None = None,
    ) -> None:
        super().__init__(main_window)
        self.main = main_window
        self.settings = settings_manager or getattr(main_window, "settings", None)
        self.tr = main_window.i18n.tr
        self.service_factory = service_factory
        self._filter_worker: KrossFilterWorker | None = None
        self._collection_worker: KrossCollectionWorker | KrossSkuCollectionWorker | None = None
        self._upload_worker: KrossUploadWorker | None = None
        self._discovery_worker = None  # Compatibility alias for the former flow.
        self._owns_browser_lease = False
        self._matches: dict[str, KrossMatch] = {}
        self._row_by_sku: dict[str, int] = {}
        self._sku_by_row: dict[int, str] = {}
        self._closing = False
        self._upload_finished_count = 0
        self._upload_failed_count = 0
        self._upload_warning_count = 0
        self._active_upload_total = 0
        self._restoring_filters = False
        self._saved_filter_state = self._load_filter_state()
        self._status_buttons: dict[str, PillPushButton] = {}
        self._stock_buttons: dict[str, PillPushButton] = {}
        self._bucket_buttons: dict[str, PillPushButton] = {}
        self._stock_group: QButtonGroup | None = None
        self._filter_widgets: list[QWidget] = []
        self._auto_refreshed_driver_id: int | None = None

        self.setObjectName("KrossScreen")
        self._build_ui()
        self._install_default_filters()
        self._load_settings()
        self.retranslate_ui()
        qconfig.themeChangedFinished.connect(self._on_theme_changed)
        QTimer.singleShot(0, self._auto_refresh_filters)

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
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
        apply_screen_theme(self, "KrossScreen", scroll=self._scroll, content=self._container)

        header = QVBoxLayout()
        header.setSpacing(2)
        self._title = TitleLabel("")
        self._subtitle = CaptionLabel("")
        self._subtitle.setWordWrap(True)
        header.addWidget(self._title)
        header.addWidget(self._subtitle)
        self._layout.addLayout(header)

        self._build_storage_card()
        self._build_filters_card()
        self._build_collection_card()
        self._build_results_card()
        self._build_upload_card()
        self._build_log_card()
        self._layout.addStretch(1)
        enforce_transparent_labels(self)

    @staticmethod
    def _card() -> tuple[CardWidget, QVBoxLayout]:
        card = CardWidget()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(*CARD_MARGINS)
        layout.setSpacing(CARD_SPACING)
        return card, layout

    def _build_storage_card(self) -> None:
        card, layout = self._card()
        self._storage_title = BodyLabel("")
        self._storage_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self._storage_hint = CaptionLabel("")
        self._storage_hint.setWordWrap(True)
        layout.addWidget(self._storage_title)
        layout.addWidget(self._storage_hint)
        row = QGridLayout()
        row.setColumnStretch(1, 1)
        row.setHorizontalSpacing(CARD_SPACING)
        self._output_label = BodyLabel("")
        self._output_input = LineEdit()
        self._output_input.textChanged.connect(self._update_action_state)
        self._output_input.editingFinished.connect(self._save_settings)
        self._browse_output_button = PushButton(FluentIcon.FOLDER, "")
        self._browse_output_button.clicked.connect(self._browse_output)
        self._load_local_button = PushButton(FluentIcon.FOLDER, "")
        self._load_local_button.clicked.connect(self._load_local_packages)
        row.addWidget(self._output_label, 0, 0)
        row.addWidget(self._output_input, 0, 1)
        row.addWidget(self._browse_output_button, 0, 2)
        row.addWidget(self._load_local_button, 0, 3)
        layout.addLayout(row)
        self._layout.addWidget(card)

    def _build_filters_card(self) -> None:
        card, layout = self._card()
        top = QHBoxLayout()
        self._filters_title = BodyLabel("")
        self._filters_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self._filter_state_label = CaptionLabel("")
        self._refresh_filters_button = PushButton(FluentIcon.SYNC, "")
        self._refresh_filters_button.clicked.connect(self.refresh_filter_options)
        top.addWidget(self._filters_title)
        top.addWidget(self._filter_state_label, 1)
        top.addWidget(self._refresh_filters_button)
        layout.addLayout(top)

        self._status_label = BodyLabel("")
        self._status_layout = FlowLayout()
        self._status_layout.setHorizontalSpacing(ROW_SPACING)
        self._status_layout.setVerticalSpacing(ROW_SPACING)
        layout.addWidget(self._status_label)
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
        for column in range(3):
            grid.setColumnStretch(column, 1)
        layout.addLayout(grid)

        self._stock_label = BodyLabel("")
        self._stock_layout = FlowLayout()
        self._stock_layout.setHorizontalSpacing(ROW_SPACING)
        self._stock_layout.setVerticalSpacing(ROW_SPACING)
        self._bucket_label = BodyLabel("")
        self._bucket_layout = FlowLayout()
        self._bucket_layout.setHorizontalSpacing(ROW_SPACING)
        self._bucket_layout.setVerticalSpacing(ROW_SPACING)
        layout.addWidget(self._stock_label)
        layout.addLayout(self._stock_layout)
        layout.addWidget(self._bucket_label)
        layout.addLayout(self._bucket_layout)
        self._layout.addWidget(card)

        combos = (
            self._family_combo, self._category_combo, self._source_combo,
            self._locale_combo, self._sort_combo,
        )
        for combo in combos:
            combo.currentIndexChanged.connect(self._filter_changed)
        self._filter_widgets.extend((self._refresh_filters_button, *combos))

    @staticmethod
    def _combo_field(combo: ComboBox) -> tuple[QWidget, BodyLabel]:
        field = QWidget()
        layout = QVBoxLayout(field)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label = BodyLabel("")
        combo.setMinimumWidth(160)
        layout.addWidget(label)
        layout.addWidget(combo)
        return field, label

    def _build_collection_card(self) -> None:
        card, layout = self._card()
        self._collection_title = BodyLabel("")
        self._collection_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self._collection_hint = CaptionLabel("")
        self._collection_hint.setWordWrap(True)
        layout.addWidget(self._collection_title)
        layout.addWidget(self._collection_hint)
        options = FlowLayout()
        options.setHorizontalSpacing(CARD_SPACING)
        options.setVerticalSpacing(ROW_SPACING)
        self._collection_checks: dict[str, CheckBox] = {}
        for name in COLLECTION_FIELDS:
            checkbox = CheckBox("")
            checkbox.setChecked(True)
            self._collection_checks[name] = checkbox
            options.addWidget(checkbox)
        layout.addLayout(options)
        self._manual_skus_label = BodyLabel("")
        self._manual_skus_input = PlainTextEdit()
        self._manual_skus_input.setFixedHeight(92)
        self._manual_skus_input.textChanged.connect(self._update_action_state)
        layout.addWidget(self._manual_skus_label)
        layout.addWidget(self._manual_skus_input)
        actions = QHBoxLayout()
        self._collect_button = PrimaryPushButton(FluentIcon.SEARCH, "")
        self._collect_button.clicked.connect(self._start_collection)
        self._collect_skus_button = PushButton(FluentIcon.DOWNLOAD, "")
        self._collect_skus_button.clicked.connect(self._start_sku_collection)
        self._load_pasted_local_button = PushButton(FluentIcon.FOLDER, "")
        self._load_pasted_local_button.clicked.connect(
            self._load_pasted_local_packages
        )
        self._stop_button = PushButton(FluentIcon.CLOSE, "")
        self._stop_button.clicked.connect(self._request_stop)
        self._stop_button.setVisible(False)
        actions.addWidget(self._collect_button)
        actions.addWidget(self._collect_skus_button)
        actions.addWidget(self._load_pasted_local_button)
        actions.addWidget(self._stop_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self._layout.addWidget(card)

    def _build_results_card(self) -> None:
        card, layout = self._card()
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        top = QHBoxLayout()
        self._results_title = BodyLabel("")
        self._results_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self._open_kross_button = PushButton(FluentIcon.LINK, "")
        self._open_kross_button.clicked.connect(lambda: self._open_selected_url("kross"))
        self._open_pimbo_button = PushButton(FluentIcon.LINK, "")
        self._open_pimbo_button.clicked.connect(lambda: self._open_selected_url("pimbo"))
        top.addWidget(self._results_title)
        top.addStretch(1)
        top.addWidget(self._open_kross_button)
        top.addWidget(self._open_pimbo_button)
        layout.addLayout(top)
        self._results_hint = CaptionLabel("")
        self._results_hint.setWordWrap(True)
        layout.addWidget(self._results_hint)

        self._table = QTableWidget(0, 7)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.setWordWrap(False)
        self._table.setMinimumHeight(360)
        self._table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._table.verticalHeader().setDefaultSectionSize(40)
        self._table.itemChanged.connect(self._update_action_state)
        self._table.itemSelectionChanged.connect(self._update_action_state)
        header = self._table.horizontalHeader()
        header.setMinimumHeight(40)
        header.setHighlightSections(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for column in range(1, 6):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        for column, width in {1: 260, 2: 340, 3: 190, 4: 240, 5: 280, 6: 320}.items():
            self._table.setColumnWidth(column, width)
        enable_table_copy(self._table)
        layout.addWidget(self._table, 1)
        self._layout.addWidget(card, 1)

    def _build_upload_card(self) -> None:
        card, layout = self._card()
        self._upload_title = BodyLabel("")
        self._upload_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self._upload_hint = CaptionLabel("")
        self._upload_hint.setWordWrap(True)
        layout.addWidget(self._upload_title)
        layout.addWidget(self._upload_hint)
        stage_header = QHBoxLayout()
        self._stages_label = BodyLabel("")
        self._select_all_stages_button = PushButton(FluentIcon.ACCEPT, "")
        self._select_all_stages_button.clicked.connect(lambda: self._set_all_stages(True))
        self._clear_stages_button = PushButton(FluentIcon.CANCEL, "")
        self._clear_stages_button.clicked.connect(lambda: self._set_all_stages(False))
        stage_header.addWidget(self._stages_label)
        stage_header.addStretch(1)
        stage_header.addWidget(self._select_all_stages_button)
        stage_header.addWidget(self._clear_stages_button)
        layout.addLayout(stage_header)
        options = FlowLayout()
        options.setHorizontalSpacing(CARD_SPACING)
        options.setVerticalSpacing(ROW_SPACING)
        self._stage_checks: dict[str, CheckBox] = {}
        for stage in STAGE_FIELDS:
            checkbox = CheckBox("")
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self._update_action_state)
            self._stage_checks[stage] = checkbox
            options.addWidget(checkbox)
        layout.addLayout(options)
        self._stages_hint = CaptionLabel("")
        self._stages_hint.setWordWrap(True)
        layout.addWidget(self._stages_hint)
        bottom = QHBoxLayout()
        self._upload_button = PrimaryPushButton(FluentIcon.UP, "")
        self._upload_button.clicked.connect(self._start_upload)
        self._progress = ProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        self._progress_label = CaptionLabel("")
        bottom.addWidget(self._upload_button)
        bottom.addWidget(self._progress, 1)
        bottom.addWidget(self._progress_label)
        layout.addLayout(bottom)
        self._layout.addWidget(card)

    def _build_log_card(self) -> None:
        card, layout = self._card()
        self._log_title = BodyLabel("")
        self._log_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self._log = PlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFixedHeight(150)
        layout.addWidget(self._log_title)
        layout.addWidget(self._log)
        self._layout.addWidget(card)

    # ------------------------------------------------------------- Filters

    def _install_default_filters(self) -> None:
        self._apply_filter_options({
            "statuses": (("Draft", "Draft"), ("In Review", "In Review"),
                         ("Published", "Published"), ("Disabled", "Disabled")),
            "families": (), "categories": (), "sources": (),
            "stock": (("Any", "Any"), ("In stock", "In stock"),
                      ("Out of stock", "Out of stock")),
            "locales": (("Overall", "Overall"), ("LT", "LT"), ("EN", "EN"),
                        ("LV", "LV"), ("EE", "EE")),
            "buckets": (("<40%", "<40%"), ("40–80%", "40–80%"),
                        ("≥80%", "≥80%"), ("100%", "100%")),
            "sort": (("Recent", "Recent"), ("Least complete", "Least complete"),
                     ("Most complete", "Most complete")),
        })

    @staticmethod
    def _normalise_options(raw: Any) -> list[tuple[str, Any]]:
        if raw is None:
            return []
        if isinstance(raw, Mapping):
            raw = raw.items()
        result: list[tuple[str, Any]] = []
        for item in raw:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                label, value = item[0], item[1]
            else:
                label = _read(item, "label", "name", "text", default="")
                value = _read(item, "value", "id", "key", default=label)
            label = str(label or value or "").strip()
            if label:
                result.append((label, _plain(value)))
        return result

    def _options(self, source: Any, *names: str) -> list[tuple[str, Any]]:
        return self._normalise_options(_read(source, *names, default=()))

    def _apply_filter_options(self, options: Any) -> None:
        state = self._collect_filter_state() if self._status_buttons else dict(self._saved_filter_state)
        self._restoring_filters = True
        try:
            self._rebuild_multi(
                self._status_layout, "_status_buttons",
                self._options(options, "statuses", "status_options"),
                state.get("statuses", ("Draft",)),
            )
            self._stock_group = self._rebuild_single(
                self._stock_layout, "_stock_buttons",
                self._options(options, "stock", "stock_options"),
                state.get("stock", "In stock"),
            )
            self._rebuild_multi(
                self._bucket_layout, "_bucket_buttons",
                self._options(options, "buckets", "completeness_buckets", "bucket_options"),
                state.get("completeness_buckets", ()),
            )
            self._populate_combo(self._family_combo, self._options(options, "families", "family_options"), "All families", state.get("family_id"))
            self._populate_combo(self._category_combo, self._options(options, "categories", "category_options"), "All categories", state.get("category_id"))
            self._populate_combo(self._source_combo, self._options(options, "sources", "source_options"), "All sources", state.get("source_id"))
            self._populate_combo(self._locale_combo, self._options(options, "locales", "completeness_locales", "locale_options"), None, state.get("completeness_locale", "Overall"))
            self._populate_combo(self._sort_combo, self._options(options, "sort", "sorts", "sort_options"), None, state.get("sort", "Recent"))
        finally:
            self._restoring_filters = False
        self._save_filter_state()

    def _clear_chips(self, layout: FlowLayout, attribute: str) -> None:
        for button in getattr(self, attribute, {}).values():
            layout.removeWidget(button)
            button.deleteLater()
            if button in self._filter_widgets:
                self._filter_widgets.remove(button)
        setattr(self, attribute, {})

    def _rebuild_multi(self, layout, attribute: str, options, selected) -> None:
        self._clear_chips(layout, attribute)
        selected_values = {str(_plain(item)).casefold() for item in (selected or ())}
        buttons = {}
        for label, value in options:
            button = PillPushButton()
            button.setText(label)
            button.setCheckable(True)
            button.setProperty("filterValue", value)
            button.setChecked(str(_plain(value)).casefold() in selected_values)
            button.toggled.connect(self._filter_changed)
            layout.addWidget(button)
            buttons[str(_plain(value))] = button
            self._filter_widgets.append(button)
        setattr(self, attribute, buttons)

    def _rebuild_single(self, layout, attribute: str, options, selected) -> QButtonGroup:
        self._clear_chips(layout, attribute)
        group = QButtonGroup(self)
        group.setExclusive(True)
        target = str(_plain(selected)).casefold()
        buttons = {}
        first = None
        for label, value in options:
            button = PillPushButton()
            button.setText(label)
            button.setCheckable(True)
            button.setProperty("filterValue", value)
            button.toggled.connect(self._filter_changed)
            group.addButton(button)
            layout.addWidget(button)
            buttons[str(_plain(value))] = button
            self._filter_widgets.append(button)
            first = first or button
            if str(_plain(value)).casefold() == target:
                button.setChecked(True)
        if group.checkedButton() is None and first is not None:
            first.setChecked(True)
        setattr(self, attribute, buttons)
        return group

    @staticmethod
    def _populate_combo(combo: ComboBox, options, all_label: str | None, selected) -> None:
        combo.clear()
        if all_label is not None:
            combo.addItem(all_label, userData=None)
        for label, value in options:
            if all_label is not None and value in (None, ""):
                continue
            combo.addItem(label, userData=value)
        target = str(_plain(selected)) if selected is not None else None
        if target is not None:
            for index in range(combo.count()):
                if (
                    str(_plain(combo.itemData(index))) == target
                    or combo.itemText(index).strip().casefold() == target.strip().casefold()
                ):
                    combo.setCurrentIndex(index)
                    break
        if combo.count() and combo.currentIndex() < 0:
            combo.setCurrentIndex(0)

    def _checked_value(self, group: QButtonGroup | None, default: str) -> Any:
        button = group.checkedButton() if group else None
        return _plain(button.property("filterValue")) if button else default

    def _collect_filter_state(self) -> dict[str, Any]:
        return {
            "statuses": [_plain(button.property("filterValue")) for button in self._status_buttons.values() if button.isChecked()],
            "family_id": _plain(self._family_combo.currentData()),
            "category_id": _plain(self._category_combo.currentData()),
            "source_id": _plain(self._source_combo.currentData()),
            "stock": self._checked_value(self._stock_group, "In stock"),
            "completeness_locale": _plain(self._locale_combo.currentData()) or "Overall",
            "completeness_buckets": [_plain(button.property("filterValue")) for button in self._bucket_buttons.values() if button.isChecked()],
            "sort": _plain(self._sort_combo.currentData()) or "Recent",
        }

    def _filter_spec(self) -> PimboFilterSpec:
        state = self._collect_filter_state()
        return PimboFilterSpec(
            statuses=tuple(state["statuses"]),
            family_id=state["family_id"] or "",
            category_id=state["category_id"] or "",
            source_id=state["source_id"] or "",
            stock=state["stock"] or "Any",
            completeness_locale=state["completeness_locale"] or "Overall",
            completeness_buckets=tuple(state["completeness_buckets"]),
            sort=state["sort"] or "Recent",
        )

    def _filter_changed(self, *_args) -> None:
        if not self._restoring_filters:
            self._save_filter_state()

    def _load_filter_state(self) -> dict[str, Any]:
        if self.settings is None:
            return {}
        try:
            raw = self.settings.get(FILTER_SETTING, "")
            parsed = json.loads(raw) if raw else {}
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def _save_filter_state(self) -> None:
        if self.settings is not None and not self._restoring_filters:
            self.settings.set(FILTER_SETTING, json.dumps(self._collect_filter_state(), ensure_ascii=False))

    # -------------------------------------------------------------- Service

    def _service(self) -> KrossAutomationService:
        if self.main.driver is None:
            raise RuntimeError(self.tr("kross.browser.unavailable"))
        return (
            KrossAutomationService(
                self.main.driver,
                db_manager=getattr(self.main, "db", None),
            )
            if self.service_factory is None
            else self.service_factory(self.main.driver)
        )

    def _acquire_browser(self) -> bool:
        acquire = getattr(self.main, "try_acquire_browser_lease", None)
        if callable(acquire) and not acquire(self):
            self._show_error(self.tr("kross.browser.busy"))
            return False
        self._owns_browser_lease = True
        navigation = getattr(self.main, "navigationInterface", None)
        if navigation is not None:
            navigation.setEnabled(False)
        return True

    def _release_browser(self) -> None:
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

    def _auto_refresh_filters(self) -> None:
        driver = getattr(self.main, "driver", None)
        if driver is not None and id(driver) != self._auto_refreshed_driver_id and not self._is_busy():
            self._auto_refreshed_driver_id = id(driver)
            self.refresh_filter_options(show_errors=False)

    def refresh_filter_options(self, *_args, show_errors: bool = True) -> None:
        if self._is_busy():
            return
        if self.main.driver is None:
            if show_errors:
                self._show_error(self.tr("kross.browser.unavailable"))
            return
        if not self._acquire_browser():
            return
        self._filter_state_label.setText(self.tr("kross.filters.loading"))
        self._filter_worker = KrossFilterWorker(self._service)
        self._filter_worker.loaded.connect(self._on_filters_loaded)
        self._filter_worker.failed.connect(lambda message: self._on_filters_failed(message, show_errors))
        self._filter_worker.finished.connect(self._finish_filters)
        self._filter_worker.start()
        self._update_action_state()

    def _on_filters_loaded(self, options: Any) -> None:
        self._apply_filter_options(options)
        self._filter_state_label.setText(self.tr("kross.filters.loaded"))

    def _on_filters_failed(self, message: str, show_errors: bool) -> None:
        self._filter_state_label.setText(self.tr("kross.filters.defaults"))
        self._log_message(f"Filter discovery: {message}")
        if show_errors:
            self._show_error(message)

    def _finish_filters(self) -> None:
        self._filter_worker = None
        self._release_browser()
        self._update_action_state()

    # ------------------------------------------------------------ Collection

    def _collection_options(self) -> KrossCollectionOptions:
        return KrossCollectionOptions(**{name: self._collection_checks[name].isChecked() for name in COLLECTION_FIELDS})

    def _start_collection(self) -> None:
        output_text = self._output_input.text().strip()
        if not output_text:
            self._show_error(self.tr("kross.output.required"))
            return
        if self.main.driver is None:
            self._show_error(self.tr("kross.browser.unavailable"))
            return
        if not self._acquire_browser():
            return
        self._begin_collection(
            KrossCollectionWorker(
                self._service, self._filter_spec(), Path(output_text),
                self._collection_options(),
            ),
            self.tr("kross.collection.starting"),
            output_text,
        )

    def _manual_targets(self):
        return parse_collection_targets(self._manual_skus_input.toPlainText().splitlines())

    def _manual_skus(self) -> tuple[str, ...]:
        """Return SKU-bearing entries for compatibility with older callers."""

        return tuple(target.sku for target in self._manual_targets() if target.sku)

    def _start_sku_collection(self) -> None:
        output_text = self._output_input.text().strip()
        if not output_text:
            self._show_error(self.tr("kross.output.required"))
            return
        targets = self._manual_targets()
        if not targets:
            self._show_error(self.tr("kross.skus.required"))
            return
        if self.main.driver is None:
            self._show_error(self.tr("kross.browser.unavailable"))
            return
        if not self._acquire_browser():
            return
        self._begin_collection(
            KrossSkuCollectionWorker(
                self._service, targets, Path(output_text), self._collection_options(),
            ),
            self.tr("kross.manual.starting", count=len(targets)),
            output_text,
        )

    def _begin_collection(
        self,
        worker: KrossCollectionWorker | KrossSkuCollectionWorker,
        starting_message: str,
        output_text: str,
    ) -> None:
        self._save_settings()
        self._log.clear()
        self._table.setRowCount(0)
        self._matches.clear()
        self._row_by_sku.clear()
        self._sku_by_row.clear()
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._log_message(starting_message)
        self._collection_worker = worker
        self._discovery_worker = self._collection_worker
        self._collection_worker.progress_changed.connect(self._on_collection_progress)
        self._collection_worker.log_message.connect(self._log_message)
        self._collection_worker.succeeded.connect(self._on_collection_succeeded)
        self._collection_worker.failed.connect(self._on_worker_failed)
        self._collection_worker.finished.connect(self._finish_collection)
        if hasattr(self.main, "track_worker"):
            self.main.track_worker(self._collection_worker, "kross_collection", "kross", output_path=output_text)
        self._collection_worker.start()
        self._update_action_state()

    def _on_collection_progress(self, current: int, total: int, message: str) -> None:
        self._log_message(message)
        self._progress.setValue(int(current * 100 / total) if total else 0)
        self._progress_label.setText(f"{current}/{total}" if total else message)

    def _on_collection_succeeded(self, result: KrossDiscoveryResult) -> None:
        self._populate_table(result.matches)
        self._log_message(self.tr("kross.collection.complete", found=result.found, total=len(result.matches)))
        self._progress.setValue(100)
        self._progress_label.setText(self.tr("kross.discovery.done"))

    def _finish_collection(self) -> None:
        self._collection_worker = None
        self._discovery_worker = None
        self._release_browser()
        self._update_action_state()

    def _load_local_packages(self) -> None:
        output = self._output_input.text().strip()
        if not output:
            self._show_error(self.tr("kross.output.required"))
            return
        result = KrossAutomationService.load_local_packages(Path(output))
        if not result.matches:
            self._show_error(self.tr("kross.local.none"))
            return
        self._populate_table(result.matches)
        self._log_message(self.tr("kross.local.loaded", count=len(result.matches)))

    def _load_pasted_local_packages(self) -> None:
        """Load only pasted SKUs/URLs from already downloaded packages."""

        output = self._output_input.text().strip()
        if not output:
            self._show_error(self.tr("kross.output.required"))
            return
        targets = self._manual_targets()
        if not targets:
            self._show_error(self.tr("kross.skus.required"))
            return

        available = KrossAutomationService.load_local_packages(Path(output)).matches
        sku_matches: dict[str, KrossMatch] = {}
        url_matches: dict[str, KrossMatch] = {}
        for match in available:
            for sku in (match.sku, *match.variant_skus):
                normalized = str(sku or "").strip().upper()
                if normalized:
                    sku_matches.setdefault(normalized, match)
            if match.kross_url:
                url_matches.setdefault(match.kross_url.rstrip("/").casefold(), match)

        selected: list[KrossMatch] = []
        selected_skus: set[str] = set()
        missing: list[str] = []
        for target in targets:
            match = None
            if target.sku:
                match = sku_matches.get(target.sku)
            if match is None and target.url:
                match = url_matches.get(target.url.rstrip("/").casefold())
            if match is None:
                missing.append(target.label)
            elif match.sku not in selected_skus:
                selected_skus.add(match.sku)
                selected.append(match)

        if not selected:
            self._show_error(self.tr("kross.manual.local_none"))
            return
        self._populate_table(tuple(selected))
        self._log_message(
            self.tr(
                "kross.manual.loaded_local",
                count=len(selected),
                missing=len(missing),
            )
        )
        for value in missing:
            self._log_message(
                self.tr("kross.manual.local_missing", value=value)
            )

    # ---------------------------------------------------------------- Upload

    def _selected_ready_matches(self) -> tuple[KrossMatch, ...]:
        selected = []
        for sku, row in self._row_by_sku.items():
            item = self._table.item(row, 0)
            match = self._matches.get(sku)
            if match and match.ready and item and item.checkState() == Qt.CheckState.Checked:
                selected.append(match)
        return tuple(selected)

    def _workflow_options(self) -> KrossWorkflowOptions:
        return KrossWorkflowOptions(**{stage: self._stage_checks[stage].isChecked() for stage in STAGE_FIELDS})

    def _set_all_stages(self, checked: bool) -> None:
        for checkbox in self._stage_checks.values():
            checkbox.blockSignals(True)
            checkbox.setChecked(checked)
            checkbox.blockSignals(False)
        self._update_action_state()

    def _start_upload(self) -> None:
        selected = self._selected_ready_matches()
        if not selected:
            self._show_error(self.tr("kross.upload.none_selected"))
            return
        options = self._workflow_options()
        if not options.any_selected:
            self._show_error(self.tr("kross.stages.required"))
            return
        if len(selected) > 1 and not options.save:
            self._show_error(self.tr("kross.stages.multi_requires_save"))
            return
        output_text = self._output_input.text().strip()
        if not output_text:
            self._show_error(self.tr("kross.output.required"))
            return
        if self.main.driver is None:
            self._show_error(self.tr("kross.browser.unavailable"))
            return
        if not self._acquire_browser():
            return
        self._save_settings()
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._upload_finished_count = 0
        self._upload_failed_count = 0
        self._upload_warning_count = 0
        self._active_upload_total = len(selected)
        self._log_message(self.tr("kross.upload.starting", count=len(selected)))
        self._upload_worker = KrossUploadWorker(self._service, selected, Path(output_text), options)
        self._upload_worker.progress_changed.connect(self._on_upload_progress)
        self._upload_worker.item_finished.connect(self._on_upload_result)
        self._upload_worker.failed.connect(self._on_worker_failed)
        self._upload_worker.completed.connect(self._finish_upload)
        if hasattr(self.main, "track_worker"):
            self.main.track_worker(self._upload_worker, "kross_upload", "kross", output_path=output_text)
        self._upload_worker.start()
        self._update_action_state()

    def _on_upload_progress(self, message: str) -> None:
        self._log_message(message)
        self._progress_label.setText(message)

    def _on_upload_result(self, result: KrossUploadResult) -> None:
        row = self._row_by_sku.get(result.match.sku)
        if row is None:
            return
        status = result.preparation.status.value.replace("_", " ")
        if result.preparation.error:
            status = f"{status}: {result.preparation.error}"
            self._upload_failed_count += 1
        elif result.preparation.status == PimPreparationStatus.FAILED:
            self._upload_failed_count += 1
        if result.preparation.warnings:
            self._upload_warning_count += len(result.preparation.warnings)
            status = f"{status} ({len(result.preparation.warnings)} warning(s))"
        self._table.setItem(row, 6, QTableWidgetItem(status))
        if result.succeeded:
            selection = self._table.item(row, 0)
            if selection is not None:
                selection.setCheckState(Qt.CheckState.Unchecked)
        self._log_message(f"{result.match.sku}: {status}")
        if result.completed_stages:
            self._log_message(
                f"{result.match.sku}: completed — {', '.join(result.completed_stages)}"
            )
        for warning in result.preparation.warnings:
            self._log_message(f"{result.match.sku}: warning — {warning}")
        self._upload_finished_count += 1
        if self._active_upload_total:
            self._progress.setValue(int(self._upload_finished_count * 100 / self._active_upload_total))

    def _finish_upload(self) -> None:
        self._upload_worker = None
        self._release_browser()
        self._update_action_state()
        self._progress.setValue(100)
        self._progress_label.setText(self.tr("kross.upload.complete"))
        if self._upload_failed_count:
            InfoBar.error(
                title=self.tr("kross.error.title"),
                content=(
                    f"{self._upload_failed_count} of {self._active_upload_total} "
                    "KROSS product(s) failed. Check the run log."
                ),
                parent=self, position=InfoBarPosition.TOP, duration=7000,
            )
        elif self._upload_warning_count:
            InfoBar.warning(
                title=self.tr("kross.upload.complete.title"),
                content=(
                    f"KROSS upload completed with {self._upload_warning_count} warning(s). "
                    "Available stages were still processed; check the run log."
                ),
                parent=self, position=InfoBarPosition.TOP, duration=7000,
            )
        else:
            InfoBar.success(
                title=self.tr("kross.upload.complete.title"),
                content=self.tr("kross.upload.complete"),
                parent=self, position=InfoBarPosition.TOP, duration=4000,
            )

    # --------------------------------------------------------- Table / state

    def _populate_table(self, matches: tuple[KrossMatch, ...]) -> None:
        self._table.blockSignals(True)
        self._table.setRowCount(len(matches))
        self._matches.clear()
        self._row_by_sku.clear()
        self._sku_by_row.clear()
        for row, match in enumerate(matches):
            self._matches[match.sku] = match
            self._row_by_sku[match.sku] = row
            self._sku_by_row[row] = match.sku
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            check.setCheckState(Qt.CheckState.Checked if match.ready else Qt.CheckState.Unchecked)
            self._table.setItem(row, 0, check)
            self._table.setItem(row, 1, QTableWidgetItem(match.pimbo_product_name or match.pimbo_product_id))
            variants = ", ".join(match.variant_skus)
            variant_item = QTableWidgetItem(variants)
            variant_item.setToolTip("\n".join(match.variant_skus))
            self._table.setItem(row, 2, variant_item)
            self._table.setItem(row, 3, QTableWidgetItem(match.sku))
            self._table.setItem(row, 4, QTableWidgetItem(match.kross_product_name))
            folder = QTableWidgetItem(match.local_folder)
            folder.setToolTip(match.local_folder)
            self._table.setItem(row, 5, folder)
            status = QTableWidgetItem(match.note or match.status)
            status.setToolTip(match.note or match.status)
            self._table.setItem(row, 6, status)
        self._table.blockSignals(False)
        self._update_action_state()

    def _selected_match(self) -> KrossMatch | None:
        rows = self._table.selectionModel().selectedRows() if self._table.selectionModel() else []
        if not rows:
            return None
        return self._matches.get(self._sku_by_row.get(rows[0].row(), ""))

    def _open_selected_url(self, source: str) -> None:
        match = self._selected_match()
        if match is None:
            return
        value = match.kross_url if source == "kross" else match.pimbo_product_url
        if value:
            QDesktopServices.openUrl(QUrl(value))

    def _is_busy(self) -> bool:
        return any((self._filter_worker, self._collection_worker, self._upload_worker))

    def _update_action_state(self, *_args) -> None:
        busy = self._is_busy()
        has_output = bool(self._output_input.text().strip())
        self._collect_button.setEnabled(not busy and has_output)
        self._collect_skus_button.setEnabled(not busy and has_output and bool(self._manual_targets()))
        self._load_pasted_local_button.setEnabled(
            not busy and has_output and bool(self._manual_targets())
        )
        self._load_local_button.setEnabled(not busy and has_output)
        self._output_input.setEnabled(not busy)
        self._browse_output_button.setEnabled(not busy)
        self._manual_skus_input.setEnabled(not busy)
        self._upload_button.setEnabled(not busy and bool(self._selected_ready_matches()) and self._workflow_options().any_selected)
        for widget in self._filter_widgets:
            widget.setEnabled(not busy)
        for checkbox in (*self._collection_checks.values(), *self._stage_checks.values()):
            checkbox.setEnabled(not busy)
        self._select_all_stages_button.setEnabled(not busy)
        self._clear_stages_button.setEnabled(not busy)
        self._table.setEnabled(not busy)
        selected = self._selected_match()
        self._open_kross_button.setEnabled(bool(selected and selected.kross_url))
        self._open_pimbo_button.setEnabled(bool(selected and selected.pimbo_product_url))
        self._stop_button.setVisible(bool(self._collection_worker or self._upload_worker))

    def _request_stop(self) -> None:
        worker = self._collection_worker or self._upload_worker
        if worker is not None:
            worker.request_stop()
            self._progress_label.setText(self.tr("kross.stopping"))

    def _on_worker_failed(self, error: str) -> None:
        self._log_message(error)
        self._show_error(error)

    def _log_message(self, message: str) -> None:
        self._log.appendPlainText(str(message))

    def _show_error(self, message: str) -> None:
        InfoBar.error(
            title=self.tr("kross.error.title"), content=message, parent=self,
            position=InfoBarPosition.TOP, duration=7000,
        )

    # ---------------------------------------------------- Settings/lifecycle

    def _load_settings(self) -> None:
        if self.settings is None:
            return
        default = self.settings.get("kross_download_path", "")
        self._output_input.setText(self.settings.get(OUTPUT_SETTING, default))

    def _save_settings(self) -> None:
        if self.settings is not None:
            self.settings.set(OUTPUT_SETTING, self._output_input.text().strip())
            self._save_filter_state()

    def _browse_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, self.tr("kross.output.pick"), self._output_input.text().strip())
        if folder:
            self._output_input.setText(folder)
            self._save_settings()

    def _on_theme_changed(self) -> None:
        apply_screen_theme(self, "KrossScreen", scroll=self._scroll, content=self._container)
        self._subtitle.setStyleSheet(f"color: {get_text_color(isDarkTheme(), 'secondary')}; background: transparent;")
        enforce_transparent_labels(self)

    def retranslate_ui(self) -> None:
        self._title.setText(self.tr("kross.title"))
        self._subtitle.setText(self.tr("kross.subtitle"))
        self._storage_title.setText(self.tr("kross.storage.title"))
        self._storage_hint.setText(self.tr("kross.storage.hint"))
        self._output_label.setText(self.tr("kross.output.label"))
        self._output_input.setPlaceholderText(self.tr("kross.output.placeholder"))
        self._browse_output_button.setText(self.tr("kross.output.browse"))
        self._load_local_button.setText(self.tr("kross.local.load"))
        self._filters_title.setText(self.tr("kross.filters.title"))
        self._refresh_filters_button.setText(self.tr("kross.filters.refresh"))
        self._status_label.setText(self.tr("orbea.filters.status"))
        self._family_label.setText(self.tr("orbea.filters.family"))
        self._category_label.setText(self.tr("orbea.filters.category"))
        self._source_label.setText(self.tr("orbea.filters.source"))
        self._locale_label.setText(self.tr("orbea.filters.locale"))
        self._sort_label.setText(self.tr("orbea.filters.sort"))
        self._stock_label.setText(self.tr("orbea.filters.stock"))
        self._bucket_label.setText(self.tr("orbea.filters.completeness"))
        self._collection_title.setText(self.tr("kross.collection.title"))
        self._collection_hint.setText(self.tr("kross.collection.hint"))
        self._manual_skus_label.setText(self.tr("kross.manual.label"))
        self._manual_skus_input.setPlaceholderText(self.tr("kross.skus.placeholder"))
        for stage, checkbox in self._collection_checks.items():
            checkbox.setText(self.tr(f"kross.collect.{stage}"))
        self._collect_button.setText(self.tr("kross.collection.start"))
        self._collect_skus_button.setText(self.tr("kross.manual.start"))
        self._load_pasted_local_button.setText(
            self.tr("kross.manual.load_local")
        )
        self._stop_button.setText(self.tr("kross.stop"))
        self._results_title.setText(self.tr("kross.results.title"))
        self._results_hint.setText(self.tr("kross.results.hint"))
        self._open_kross_button.setText(self.tr("kross.results.open_kross"))
        self._open_pimbo_button.setText(self.tr("kross.results.open_pimbo"))
        self._table.setHorizontalHeaderLabels([
            self.tr("kross.col.select"), self.tr("kross.col.pimbo"), self.tr("kross.col.variants"),
            self.tr("kross.col.sku"), self.tr("kross.col.product"), self.tr("kross.col.local_folder"),
            self.tr("kross.col.status"),
        ])
        self._upload_title.setText(self.tr("kross.upload.title"))
        self._upload_hint.setText(self.tr("kross.upload.hint"))
        self._stages_label.setText(self.tr("kross.stages.label"))
        self._select_all_stages_button.setText(self.tr("common.select_all"))
        self._clear_stages_button.setText(self.tr("common.deselect_all"))
        self._stages_hint.setText(self.tr("kross.stages.hint"))
        for stage, checkbox in self._stage_checks.items():
            checkbox.setText(self.tr(f"kross.stage.{stage}"))
        self._upload_button.setText(self.tr("kross.upload.start"))
        self._log_title.setText(self.tr("kross.log.title"))
        if not self._filter_state_label.text():
            self._filter_state_label.setText(self.tr("kross.filters.defaults"))
        if not self._progress_label.text():
            self._progress_label.setText(self.tr("kross.ready"))
        self._update_action_state()

    def on_activated(self) -> None:
        self._closing = False
        self._auto_refresh_filters()

    def shutdown(self, wait_ms: int = 5000) -> bool:
        self._closing = True
        workers = (self._filter_worker, self._collection_worker, self._upload_worker)
        for worker in workers:
            if worker is not None and hasattr(worker, "request_stop"):
                worker.request_stop()
        for worker in workers:
            if worker is not None and worker.isRunning() and not worker.wait(max(0, int(wait_ms))):
                return False
        self._release_browser()
        return True

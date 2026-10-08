"""Integrated Pimbo-to-Orbea catalogue, report, and table-image workflow."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QSizePolicy,
    QTabBar,
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
    qconfig,
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
from GUI_Qt.styles.theme_config import (
    COLORS,
    COMPONENT_COLORS,
    FONTS,
    PADDINGS,
    RADII,
    get_accent_colors,
    get_selection_bg,
    get_status_text_color,
    get_subtle_border,
    get_subtle_item_hover_bg,
    get_text_color,
    rgba_from_hex,
)
from GUI_Qt.widgets import enable_table_copy
from GUI_Qt.widgets.ResponsiveWidget import ResponsiveWidget


CATALOGUE_SETTING = "orbea_catalogue_path"
OUTPUT_SETTING = "orbea_output_root"
FILTER_SETTING = "orbea_filter_preset"
DESCRIPTION_OUTPUT_SETTING = "orbea_description_output"
PHOTO_OUTPUT_SETTING = "orbea_photo_output"
TABLE_OUTPUT_SETTING = "orbea_table_output"
DIRECT_GEOMETRY_SETTING = "orbea_direct_geometry_images"
DIRECT_SIZE_GUIDE_SETTING = "orbea_direct_size_guide_image"
DIRECT_PRODUCT_PHOTOS_SETTING = "orbea_direct_product_photos"
TABLE_IMAGES_SETTING = "orbea_download_table_images"
PRODUCT_PHOTOS_SETTING = "orbea_download_product_photos"
COLLECTION_SETTING = "orbea_collection_options"
PREVIEW_LIMIT = 500


from GUI_Qt.orbea.actions import current_activity, set_controls_locked
from GUI_Qt.orbea.description_workflow import DescriptionWorkflow
from GUI_Qt.orbea.photo_workflow import PhotoWorkflow
from GUI_Qt.orbea.table_image_workflow import TableImageWorkflow
from GUI_Qt.orbea.controller import (
    OrbeaWorkflowController, _create_model, _plain, _read,
)
from GUI_Qt.orbea.workers import (
    OrbeaDescriptionWorker, OrbeaExcelSortWorker, OrbeaFilterWorker,
    OrbeaPhotoWorker, OrbeaRunWorker, OrbeaTableImageWorker,
)
from GUI_Qt.orbea.tabs import OrbeaDisclosure, OrbeaSectionPage, OrbeaSectionTabs
from GUI_Qt.orbea.upload import OrbeaUploadPanel

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
        photo_service_factory: Callable[[], Any] | None = None,
        table_image_service_factory: Callable[[], Any] | None = None,
        upload_service_factory: Callable[[], Any] | None = None,
    ):
        super().__init__(main_window)
        self.main = main_window
        self.settings = settings_manager or getattr(main_window, "settings", None)
        self.tr = main_window.i18n.tr
        self.workflow_controller = OrbeaWorkflowController(
            self,
            service_factory=service_factory,
            image_driver_factory=image_driver_factory,
            description_service_factory=description_service_factory,
            photo_service_factory=photo_service_factory,
            table_image_service_factory=table_image_service_factory,
        )
        self._worker: OrbeaRunWorker | None = None
        self._filter_worker: OrbeaFilterWorker | None = None
        self._description_worker: OrbeaDescriptionWorker | None = None
        self._photo_worker: OrbeaPhotoWorker | None = None
        self._table_image_worker: OrbeaTableImageWorker | None = None
        self._excel_sort_worker: OrbeaExcelSortWorker | None = None
        self._owns_browser_lease = False
        self._restoring_filters = False
        self._closing = False
        self._upload_service_factory = upload_service_factory
        self._workbook_path: Path | None = None
        self._run_dir: Path | None = None
        self._description_output_dir: Path | None = None
        self._photo_output_dir: Path | None = None
        self._table_output_dir: Path | None = None
        self._run_operation_id: str | None = None
        self._status_buttons: dict[str, PillPushButton] = {}
        self._stock_buttons: dict[str, PillPushButton] = {}
        self._bucket_buttons: dict[str, PillPushButton] = {}
        self._status_group = None
        self._stock_group = None
        self._bucket_group = None
        self._config_widgets: list[QWidget] = []
        self._description_config_widgets: list[QWidget] = []
        self._photo_config_widgets: list[QWidget] = []
        self._table_image_config_widgets: list[QWidget] = []
        self._saved_filter_state = self._load_filter_state()
        self._auto_refreshed_driver_id: int | None = None

        self.setObjectName("OrbeaScreen")
        self._build_ui()
        self._description_workflow = DescriptionWorkflow(self)
        self._photo_workflow = PhotoWorkflow(self)
        self._table_image_workflow = TableImageWorkflow(self)
        self._install_default_filters()
        self._load_paths()
        self.retranslate_ui()
        self._update_action_states()
        qconfig.themeChangedFinished.connect(self._on_theme_changed)
        QTimer.singleShot(0, self._auto_refresh_filters)

    def _on_theme_changed(self):
        apply_screen_theme(
            self, "OrbeaScreen", scroll=self._scroll, content=self._container
        )
        self._subtitle.setStyleSheet(
            f"color: {get_text_color(isDarkTheme(), 'secondary')}; "
            "background: transparent; border: none;"
        )
        self._update_table_theme()
        enforce_transparent_labels(self)

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
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self._title = TitleLabel("")
        self._subtitle = CaptionLabel("")
        self._subtitle.setWordWrap(True)
        self._subtitle.setStyleSheet(f"color: {get_text_color(isDarkTheme(), 'secondary')};")
        title_col.addWidget(self._title)
        title_col.addWidget(self._subtitle)
        header.addLayout(title_col, 1)
        self._layout.addLayout(header)

        self._section_tabs = OrbeaSectionTabs(self)
        self._section_keys = self._section_tabs.KEYS
        self._layout.addWidget(self._section_tabs)

        self._automation_page, self._automation_layout = self._section_page()
        self._tools_page, self._tools_layout = self._section_page()
        self._setup_page = self._progress_page = self._results_page = self._upload_page = self._automation_page
        self._setup_layout = self._progress_layout = self._upload_layout = self._automation_layout
        self._photos_page = self._descriptions_page = self._tools_page

        self._build_paths_card()
        self._build_filters_card()
        self._build_actions_card()
        self._build_progress_card()
        self._report_details = OrbeaDisclosure(self)
        self._report_details.hide()
        self._automation_layout.addWidget(self._report_details)
        self._results_layout = self._report_details.body_layout
        self._build_results_table()
        self._upload_panel = OrbeaUploadPanel(self, self._upload_service_factory)
        self._automation_layout.addWidget(self._upload_panel)
        self._automation_layout.addStretch()

        self._tools_hint = CaptionLabel("")
        self._tools_hint.setWordWrap(True)
        self._tools_layout.addWidget(self._tools_hint)
        self._image_tool = OrbeaDisclosure(self)
        self._description_tool = OrbeaDisclosure(self)
        self._excel_tool = OrbeaDisclosure(self)
        self._photos_layout = self._image_tool.body_layout
        self._descriptions_layout = self._description_tool.body_layout
        self._build_table_image_card()
        self._build_photo_card()
        self._build_description_card()
        self._excel_tool.body_layout.addWidget(self._excel_sort_btn)
        for tool in (self._image_tool, self._description_tool, self._excel_tool):
            self._tools_layout.addWidget(tool)
        self._tools_layout.addStretch()

        self._section_pages = {
            "automation": self._automation_page,
            "tools": self._tools_page,
        }
        for page in self._section_pages.values():
            self._layout.addWidget(page, 1)

        from GUI_Qt.layouts.automation import arrange_orbea
        arrange_orbea(self)

        self._section_tabs.keyChanged.connect(self._switch_section)
        self._switch_section("setup")

        enforce_transparent_labels(self)

    @staticmethod
    def _section_page() -> tuple[QWidget, QVBoxLayout]:
        page = OrbeaSectionPage()
        return page, page.content_layout

    def _switch_section(self, route_key: str) -> None:
        requested = route_key
        route_key = self._section_tabs.select_key(route_key)
        for key, page in self._section_pages.items():
            page.setVisible(key == route_key)
        self._scroll.verticalScrollBar().setValue(0)
        if requested in {"progress", "results"}:
            self._collection_progress_card.setVisible(True)
            QTimer.singleShot(0, lambda: self._scroll.ensureWidgetVisible(self._collection_progress_card))
        if requested in {"photos", "descriptions"}:
            self._image_tool.set_expanded(requested == "photos")
            self._description_tool.set_expanded(requested == "descriptions")

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

        self._output_label = BodyLabel("")
        self._output_edit = LineEdit()
        self._output_edit.setClearButtonEnabled(True)
        self._output_edit.editingFinished.connect(self._paths_changed)
        self._output_btn = PushButton(FluentIcon.FOLDER, "")
        self._output_btn.clicked.connect(self._browse_output)
        grid.addWidget(self._output_label, 0, 0)
        grid.addWidget(self._output_edit, 0, 1)
        grid.addWidget(self._output_btn, 0, 2)

        # The Pimbo query is intentionally fixed and is not an actionable
        # setting, so retain it for configuration/tests without spending a
        # full visible form row on a disabled control.
        self._search_label = BodyLabel("", card)
        self._search_edit = LineEdit(card)
        self._search_edit.setText("orbea")
        self._search_edit.setReadOnly(True)
        self._search_edit.setEnabled(False)
        self._search_label.setVisible(False)
        self._search_edit.setVisible(False)
        layout.addLayout(grid)

        self._downloads_label = BodyLabel("")
        layout.addWidget(self._downloads_label)
        download_options = FlowLayout()
        download_options.setHorizontalSpacing(CARD_SPACING)
        download_options.setVerticalSpacing(ROW_SPACING)
        self._table_images_check = CheckBox("")
        self._table_images_check.setChecked(True)
        self._table_images_check.stateChanged.connect(
            self._download_options_changed
        )
        self._product_photos_check = CheckBox("")
        self._product_photos_check.setChecked(True)
        self._product_photos_check.stateChanged.connect(
            self._download_options_changed
        )
        download_options.addWidget(self._table_images_check)
        download_options.addWidget(self._product_photos_check)
        self._description_check = CheckBox("")
        self._specifications_check = CheckBox("")
        for checkbox in (self._description_check, self._specifications_check):
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self._download_options_changed)
            download_options.addWidget(checkbox)
        layout.addLayout(download_options)
        self._downloads_hint = CaptionLabel("")
        self._downloads_hint.setWordWrap(True)
        self._downloads_hint.setStyleSheet(
            f"color: {get_text_color(isDarkTheme(), 'secondary')};"
        )
        layout.addWidget(self._downloads_hint)

        self._setup_layout.addWidget(card)
        self._config_widgets.extend([
            self._catalogue_edit,
            self._catalogue_btn,
            self._output_edit,
            self._output_btn,
            self._table_images_check,
            self._product_photos_check,
            self._description_check,
            self._specifications_check,
        ])

    def _build_filters_card(self):
        card, layout = self._card()
        top = QHBoxLayout()
        self._filters_title = BodyLabel("")
        self._filters_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self._filter_state_label = CaptionLabel("")
        self._filter_state_label.setStyleSheet(f"color: {get_text_color(isDarkTheme(), 'secondary')};")
        self._refresh_btn = PushButton(FluentIcon.SYNC, "")
        self._refresh_btn.clicked.connect(self.refresh_filter_options)
        top.addWidget(self._filters_title)
        top.addWidget(self._filter_state_label, 1)
        top.addWidget(self._refresh_btn)
        layout.addLayout(top)

        self._status_label = BodyLabel("")
        status_field = QWidget()
        status_box = QVBoxLayout(status_field)
        status_box.setContentsMargins(0, 0, 0, 0)
        status_box.setSpacing(4)
        status_box.addWidget(self._status_label)
        self._status_layout = FlowLayout()
        self._status_layout.setHorizontalSpacing(ROW_SPACING)
        self._status_layout.setVerticalSpacing(ROW_SPACING)
        status_box.addLayout(self._status_layout)

        grid = QGridLayout()
        grid.setHorizontalSpacing(CARD_SPACING)
        grid.setVerticalSpacing(ROW_SPACING)
        self._family_combo = ComboBox()
        self._category_combo = ComboBox()
        self._source_combo = ComboBox()
        self._locale_combo = ComboBox()
        self._sort_combo = ComboBox()
        self._code_prefix_edit = LineEdit()
        self._code_prefix_edit.setClearButtonEnabled(True)
        self._family_field, self._family_label = self._combo_field(self._family_combo)
        self._category_field, self._category_label = self._combo_field(self._category_combo)
        self._source_field, self._source_label = self._combo_field(self._source_combo)
        self._locale_field, self._locale_label = self._combo_field(self._locale_combo)
        self._sort_field, self._sort_label = self._combo_field(self._sort_combo)
        self._code_prefix_field, self._code_prefix_label = self._combo_field(self._code_prefix_edit)
        self._code_prefix_label.setBuddy(self._code_prefix_edit)
        grid.addWidget(self._family_field, 0, 0)
        grid.addWidget(self._category_field, 0, 1)
        grid.addWidget(self._source_field, 0, 2)
        grid.addWidget(self._locale_field, 1, 0)
        grid.addWidget(self._sort_field, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        layout.addWidget(self._code_prefix_field)

        self._stock_label = BodyLabel("")
        stock_field = QWidget()
        stock_box = QVBoxLayout(stock_field)
        stock_box.setContentsMargins(0, 0, 0, 0)
        stock_box.setSpacing(4)
        stock_box.addWidget(self._stock_label)
        self._stock_layout = FlowLayout()
        self._stock_layout.setHorizontalSpacing(ROW_SPACING)
        self._stock_layout.setVerticalSpacing(ROW_SPACING)
        stock_box.addLayout(self._stock_layout)
        basic = QGridLayout()
        basic.addWidget(status_field, 0, 0)
        basic.addWidget(stock_field, 0, 1)
        basic.setColumnStretch(0, 1)
        basic.setColumnStretch(1, 1)
        layout.addLayout(basic)

        self._more_filters = OrbeaDisclosure(self)
        layout.addWidget(self._more_filters)
        self._more_filters.body_layout.addLayout(grid)

        self._bucket_label = BodyLabel("")
        self._more_filters.body_layout.addWidget(self._bucket_label)
        self._bucket_layout = FlowLayout()
        self._bucket_layout.setHorizontalSpacing(ROW_SPACING)
        self._bucket_layout.setVerticalSpacing(ROW_SPACING)
        self._more_filters.body_layout.addLayout(self._bucket_layout)
        catalogue = QGridLayout()
        catalogue.setColumnStretch(1, 1)
        catalogue.addWidget(self._catalogue_label, 0, 0)
        catalogue.addWidget(self._catalogue_edit, 0, 1)
        catalogue.addWidget(self._catalogue_btn, 0, 2)
        self._more_filters.body_layout.addLayout(catalogue)

        self._setup_layout.addWidget(card)
        combos = [
            self._family_combo,
            self._category_combo,
            self._source_combo,
            self._locale_combo,
            self._sort_combo,
        ]
        for combo in combos:
            combo.currentIndexChanged.connect(self._filter_changed)
        self._code_prefix_edit.textChanged.connect(self._filter_changed)
        self._config_widgets.extend([self._refresh_btn, *combos, self._code_prefix_edit])

    def _combo_field(self, combo: ComboBox | LineEdit) -> tuple[QWidget, BodyLabel]:
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
        self._actions_title = BodyLabel("")
        self._actions_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self._actions_title.hide()
        actions = QGridLayout()
        actions.setHorizontalSpacing(ROW_SPACING)
        actions.setVerticalSpacing(ROW_SPACING)
        self._start_btn = PrimaryPushButton(FluentIcon.SEARCH, "")
        self._start_btn.setObjectName("orbeaPrimaryAction")
        self._start_btn.clicked.connect(self._on_start_stop)
        self._resume_btn = PushButton(FluentIcon.UPDATE, "")
        self._resume_btn.clicked.connect(
            lambda: self._start_run(resume=True, retry_failed=False, require_existing=True)
        )
        self._retry_btn = PushButton(FluentIcon.SYNC, "")
        self._retry_btn.clicked.connect(
            lambda: self._start_run(resume=True, retry_failed=True, require_existing=True)
        )
        self._retry_matched_btn = PushButton(FluentIcon.SYNC, "")
        self._retry_matched_btn.clicked.connect(
            lambda: self._start_run(resume=True, retry_failed=False, retry_matched=True, require_existing=True)
        )
        self._load_collection_btn = PushButton(FluentIcon.FOLDER, "")
        self._load_collection_btn.clicked.connect(lambda: self._load_saved_collection())
        self._download_missing_btn = PushButton(FluentIcon.DOWNLOAD, "")
        self._download_missing_btn.clicked.connect(self._download_saved_items)
        self._open_excel_btn = PushButton(FluentIcon.DOCUMENT, "")
        self._open_excel_btn.setEnabled(False)
        self._open_excel_btn.clicked.connect(self._open_excel)
        self._open_folder_btn = PushButton(FluentIcon.FOLDER, "")
        self._open_folder_btn.setEnabled(False)
        self._open_folder_btn.clicked.connect(self._open_folder)
        self._excel_sort_btn = PushButton(FluentIcon.DOCUMENT, "")
        self._excel_sort_btn.clicked.connect(self._sort_existing_excel)
        actions.addWidget(self._start_btn, 0, 0, 1, 2)
        actions.addWidget(self._resume_btn, 1, 0)
        actions.addWidget(self._retry_btn, 1, 1)
        actions.addWidget(self._retry_matched_btn, 2, 0, 1, 2)
        actions.addWidget(self._load_collection_btn, 3, 0)
        actions.addWidget(self._download_missing_btn, 3, 1)
        for button in (self._start_btn, self._resume_btn, self._retry_btn, self._retry_matched_btn):
            button.setMinimumHeight(38)
        for column in range(2):
            actions.setColumnStretch(column, 1)
        layout.addLayout(actions)
        self._resume_hint = CaptionLabel("")
        self._resume_hint.setWordWrap(True)
        self._resume_hint.setStyleSheet(f"color: {get_text_color(isDarkTheme(), 'secondary')};")
        layout.addWidget(self._resume_hint)
        self._saved_download_hint = CaptionLabel("")
        self._saved_download_hint.setWordWrap(True)
        layout.addWidget(self._saved_download_hint)
        self._setup_layout.addWidget(card)
        self._config_widgets.append(self._excel_sort_btn)

    def _build_progress_card(self):
        card, layout = self._card()
        self._collection_progress_card = card
        card.setVisible(False)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        status_row = QHBoxLayout()
        self._stage_label = BodyLabel("")
        self._stage_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        self._eta_label = CaptionLabel("")
        self._eta_label.setStyleSheet(f"color: {get_text_color(isDarkTheme(), 'secondary')};")
        self._progress_stop_btn = PushButton(FluentIcon.CLOSE, "")
        self._progress_stop_btn.setObjectName("orbeaDangerAction")
        self._progress_stop_btn.clicked.connect(self._on_start_stop)
        self._progress_stop_btn.setVisible(False)
        status_row.addWidget(self._stage_label, 1)
        status_row.addWidget(self._eta_label)
        status_row.addWidget(self._progress_stop_btn)
        layout.addLayout(status_row)
        self._progress = ProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        layout.addWidget(self._progress)
        self._progress_label = CaptionLabel("")
        self._progress_label.setWordWrap(True)
        self._progress_label.setStyleSheet(f"color: {get_text_color(isDarkTheme(), 'secondary')};")
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
            label.setStyleSheet(f"color: {get_text_color(isDarkTheme(), 'secondary')};")
            value = BodyLabel("0")
            value.setStyleSheet("font-size: 20px; font-weight: 600;")
            stat_layout.addWidget(label)
            stat_layout.addWidget(value)
            stats.addWidget(widget, index // 3, index % 3)
            self._stat_labels[key] = label
            self._stat_values[key] = value
        self._collection_details = OrbeaDisclosure(self)
        layout.addWidget(self._collection_details)
        self._collection_details.body_layout.addLayout(stats)

        self._log = PlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFixedHeight(140)
        self._collection_details.body_layout.addWidget(self._log)
        self._progress_layout.addWidget(card)

    def _build_description_card(self):
        card, layout = self._card()

        self._description_title = BodyLabel("")
        self._description_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self._description_subtitle = CaptionLabel("")
        self._description_subtitle.setStyleSheet(f"color: {get_text_color(isDarkTheme(), 'secondary')};")
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
        output_row.setColumnStretch(0, 1)
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
        self._description_start_btn.setObjectName("orbeaPrimaryAction")
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
        self._description_progress_label.setStyleSheet(f"color: {get_text_color(isDarkTheme(), 'secondary')};")
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
        self._descriptions_layout.addWidget(card)
        self._descriptions_layout.addStretch()

    def _build_table_image_card(self):
        card, layout = self._card()

        self._table_image_title = BodyLabel("")
        self._table_image_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self._table_image_subtitle = CaptionLabel("")
        self._table_image_subtitle.setWordWrap(True)
        self._table_image_subtitle.setStyleSheet(
            f"color: {get_text_color(isDarkTheme(), 'secondary')};"
        )
        layout.addWidget(self._table_image_title)
        layout.addWidget(self._table_image_subtitle)

        self._table_image_url_label = BodyLabel("")
        self._table_image_url_edit = PlainTextEdit()
        self._table_image_url_edit.setMinimumHeight(82)
        self._table_image_url_edit.setMaximumHeight(140)
        self._table_image_url_edit.textChanged.connect(
            self._on_table_image_urls_changed
        )
        layout.addWidget(self._table_image_url_label)
        layout.addWidget(self._table_image_url_edit)
        self._table_image_urls_hint = CaptionLabel("")
        self._table_image_urls_hint.setWordWrap(True)
        self._table_image_urls_hint.setStyleSheet(
            f"color: {get_text_color(isDarkTheme(), 'secondary')};"
        )
        layout.addWidget(self._table_image_urls_hint)

        self._table_image_types_label = BodyLabel("")
        layout.addWidget(self._table_image_types_label)
        image_types = FlowLayout()
        image_types.setHorizontalSpacing(CARD_SPACING)
        image_types.setVerticalSpacing(ROW_SPACING)
        self._table_geometry_check = CheckBox("")
        self._table_geometry_check.setChecked(True)
        self._table_size_guide_check = CheckBox("")
        self._table_size_guide_check.setChecked(True)
        self._table_product_photos_check = CheckBox("")
        self._table_product_photos_check.setChecked(False)
        for checkbox in (
            self._table_geometry_check,
            self._table_size_guide_check,
            self._table_product_photos_check,
        ):
            checkbox.stateChanged.connect(self._table_image_options_changed)
            image_types.addWidget(checkbox)
        layout.addLayout(image_types)

        output_row = QGridLayout()
        output_row.setHorizontalSpacing(CARD_SPACING)
        output_row.setVerticalSpacing(ROW_SPACING)
        output_row.setColumnStretch(0, 1)
        self._table_image_output_label = BodyLabel("")
        self._table_image_output_edit = LineEdit()
        self._table_image_output_edit.setClearButtonEnabled(True)
        self._table_image_output_edit.editingFinished.connect(
            self._table_image_output_changed
        )
        self._table_image_output_btn = PushButton(FluentIcon.FOLDER, "")
        self._table_image_output_btn.clicked.connect(
            self._browse_table_image_output
        )
        output_row.addWidget(self._table_image_output_label, 0, 0, 1, 2)
        output_row.addWidget(self._table_image_output_edit, 1, 0)
        output_row.addWidget(self._table_image_output_btn, 1, 1)
        layout.addLayout(output_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(ROW_SPACING)
        self._table_image_start_btn = PrimaryPushButton(FluentIcon.DOWNLOAD, "")
        self._table_image_start_btn.setObjectName("orbeaPrimaryAction")
        self._table_image_start_btn.clicked.connect(
            self._on_table_image_start_stop
        )
        self._table_image_open_btn = PushButton(FluentIcon.FOLDER, "")
        self._table_image_open_btn.setEnabled(False)
        self._table_image_open_btn.clicked.connect(
            self._open_table_image_folder
        )
        action_row.addWidget(self._table_image_start_btn)
        action_row.addWidget(self._table_image_open_btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        self._table_image_status_label = BodyLabel("")
        self._table_image_status_label.setStyleSheet(
            "font-size: 14px; font-weight: 600;"
        )
        layout.addWidget(self._table_image_status_label)
        self._table_image_progress = ProgressBar()
        self._table_image_progress.setRange(0, 100)
        self._table_image_progress.setValue(0)
        layout.addWidget(self._table_image_progress)
        self._table_image_progress_label = CaptionLabel("")
        self._table_image_progress_label.setWordWrap(True)
        self._table_image_progress_label.setStyleSheet(
            f"color: {get_text_color(isDarkTheme(), 'secondary')};"
        )
        layout.addWidget(self._table_image_progress_label)

        self._table_image_log = PlainTextEdit()
        self._table_image_log.setReadOnly(True)
        self._table_image_log.setMinimumHeight(80)
        self._table_image_log.setMaximumHeight(120)
        self._table_image_log.setVisible(False)
        layout.addWidget(self._table_image_log)

        self._table_image_config_widgets.extend(
            [
                self._table_image_url_edit,
                self._table_image_output_edit,
                self._table_image_output_btn,
                self._table_geometry_check,
                self._table_size_guide_check,
                self._table_product_photos_check,
            ]
        )
        self._photos_layout.addWidget(card)

    def _build_photo_card(self):
        card, layout = self._card()
        self._photo_card = card

        self._photo_title = BodyLabel("")
        self._photo_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self._photo_subtitle = CaptionLabel("")
        self._photo_subtitle.setWordWrap(True)
        self._photo_subtitle.setStyleSheet(f"color: {get_text_color(isDarkTheme(), 'secondary')};")
        layout.addWidget(self._photo_title)
        layout.addWidget(self._photo_subtitle)

        self._photo_url_label = BodyLabel("")
        self._photo_url_edit = PlainTextEdit()
        self._photo_url_edit.setMinimumHeight(92)
        self._photo_url_edit.setMaximumHeight(160)
        self._photo_url_edit.textChanged.connect(self._on_photo_urls_changed)
        layout.addWidget(self._photo_url_label)
        layout.addWidget(self._photo_url_edit)
        self._photo_urls_hint = CaptionLabel("")
        self._photo_urls_hint.setWordWrap(True)
        self._photo_urls_hint.setStyleSheet(f"color: {get_text_color(isDarkTheme(), 'secondary')};")
        layout.addWidget(self._photo_urls_hint)

        output_row = QGridLayout()
        output_row.setHorizontalSpacing(CARD_SPACING)
        output_row.setVerticalSpacing(ROW_SPACING)
        output_row.setColumnStretch(0, 1)
        self._photo_output_label = BodyLabel("")
        self._photo_output_edit = LineEdit()
        self._photo_output_edit.setClearButtonEnabled(True)
        self._photo_output_edit.editingFinished.connect(self._photo_output_changed)
        self._photo_output_btn = PushButton(FluentIcon.FOLDER, "")
        self._photo_output_btn.clicked.connect(self._browse_photo_output)
        output_row.addWidget(self._photo_output_label, 0, 0, 1, 2)
        output_row.addWidget(self._photo_output_edit, 1, 0)
        output_row.addWidget(self._photo_output_btn, 1, 1)
        layout.addLayout(output_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(ROW_SPACING)
        self._photo_start_btn = PrimaryPushButton(FluentIcon.DOWNLOAD, "")
        self._photo_start_btn.setObjectName("orbeaPrimaryAction")
        self._photo_start_btn.clicked.connect(self._on_photo_start_stop)
        self._photo_open_btn = PushButton(FluentIcon.FOLDER, "")
        self._photo_open_btn.setEnabled(False)
        self._photo_open_btn.clicked.connect(self._open_photo_folder)
        action_row.addWidget(self._photo_start_btn)
        action_row.addWidget(self._photo_open_btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        self._photo_status_label = BodyLabel("")
        self._photo_status_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(self._photo_status_label)
        self._photo_progress = ProgressBar()
        self._photo_progress.setRange(0, 100)
        self._photo_progress.setValue(0)
        layout.addWidget(self._photo_progress)
        self._photo_progress_label = CaptionLabel("")
        self._photo_progress_label.setWordWrap(True)
        self._photo_progress_label.setStyleSheet(f"color: {get_text_color(isDarkTheme(), 'secondary')};")
        layout.addWidget(self._photo_progress_label)

        self._photo_log = PlainTextEdit()
        self._photo_log.setReadOnly(True)
        self._photo_log.setMinimumHeight(150)
        layout.addWidget(self._photo_log, 1)

        self._photo_config_widgets.extend(
            [self._photo_url_edit, self._photo_output_edit, self._photo_output_btn]
        )
        # Product photography is intentionally not part of this workflow.
        # Keep the existing controls constructed for backward compatibility
        # with saved settings and older integrations, but do not expose a
        # second, competing downloader in the table-only interface.
        card.setVisible(False)
        self._photos_layout.addWidget(card)

    def _build_results_table(self):
        self._results_label = CaptionLabel("")
        self._results_label.setStyleSheet(f"color: {get_text_color(isDarkTheme(), 'secondary')};")
        toolbar = QGridLayout()
        toolbar.setHorizontalSpacing(ROW_SPACING)
        toolbar.setVerticalSpacing(ROW_SPACING)
        toolbar.addWidget(self._results_label, 0, 0, 1, 4)
        self._report_details.header_layout.addWidget(self._open_excel_btn)
        self._report_details.header_layout.addWidget(self._open_folder_btn)
        toolbar.setColumnStretch(0, 1)
        self._results_layout.addLayout(toolbar)
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
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.setWordWrap(False)
        self._table.verticalHeader().setDefaultSectionSize(36)
        self._table.horizontalHeader().setMinimumHeight(42)
        self._table.horizontalHeader().setHighlightSections(False)
        self._table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._table.setMinimumHeight(240)
        self._table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        enable_table_copy(self._table)
        self._results_layout.addWidget(self._table, 1)

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

    def _apply_filter_options(self, options: Any, *, state=None):
        if state is None:
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
            self._code_prefix_edit.setText(str(state.get("product_code_prefix") or ""))
        finally:
            self._restoring_filters = False
        self._save_filter_state()
        self._style_filter_buttons()

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
            "product_code_prefix": self._code_prefix_edit.text().strip(),
        }

    def _filter_changed(self, *_args):
        if not self._restoring_filters:
            self._save_filter_state()
            self._update_more_filters_title()

    def _update_more_filters_title(self):
        if not hasattr(self, "_more_filters"):
            return
        state = self._collect_filter_state()
        count = sum(bool(state.get(key)) for key in ("family_id", "category_id", "source_id", "completeness_buckets"))
        count += state.get("completeness_locale", "Overall") != "Overall"
        count += state.get("sort", "Recent") != "Recent"
        count += bool(self._catalogue_edit.text().strip())
        label = self._t("orbea.more_filters", "More filters and optional catalogue")
        if count:
            label += self._t("orbea.more_filters.active", " ({count} active)", count=count)
        self._more_filters.set_title(label)

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
        return self.workflow_controller.make_service(driver)

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
            "catalogue_path": Path(self._catalogue_edit.text().strip()) if self._catalogue_edit.text().strip() else None,
            "output_root": Path(self._output_edit.text().strip()),
            "filters": filters,
            "product_code_prefix": state.get("product_code_prefix", ""),
            "all_products": True,
            "download_images": self._table_images_check.isChecked(),
            "download_product_photos": self._product_photos_check.isChecked(),
            "collect_product_data": True,
            "download_description": self._description_check.isChecked(),
            "download_specifications": self._specifications_check.isChecked(),
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
        return self.workflow_controller.make_description_service()

    def _make_photo_service(self):
        return self.workflow_controller.make_photo_service()

    def _make_table_image_service(self):
        return self.workflow_controller.make_table_image_service()

    def _table_image_link_state(
        self,
    ) -> tuple[tuple[str, ...], int, tuple[str, ...], tuple[str, ...]]:
        from tools.orbea_automation import (
            normalize_orbea_table_url,
            unique_orbea_table_urls,
        )

        entries: list[str] = []
        invalid: list[str] = []
        for line in self._table_image_url_edit.toPlainText().splitlines():
            value = line.strip().rstrip(".\"'()[]{}<>")
            if not value:
                continue
            try:
                entries.append(normalize_orbea_table_url(value))
            except (TypeError, ValueError):
                invalid.append(line.strip())
        unique, duplicates = unique_orbea_table_urls(entries)
        return unique, len(duplicates), tuple(invalid), tuple(entries)

    def _table_image_urls(self) -> tuple[str, ...]:
        return self._table_image_link_state()[0]

    def _table_image_selection(self) -> tuple[bool, bool, bool]:
        return (
            self._table_geometry_check.isChecked(),
            self._table_size_guide_check.isChecked(),
            self._table_product_photos_check.isChecked(),
        )

    def _table_image_options_changed(self, _state=None):
        geometry, size_guide, product_photos = self._table_image_selection()
        self._setting_set(DIRECT_GEOMETRY_SETTING, geometry)
        self._setting_set(DIRECT_SIZE_GUIDE_SETTING, size_guide)
        self._setting_set(DIRECT_PRODUCT_PHOTOS_SETTING, product_photos)
        self._update_action_states()

    def _on_table_image_urls_changed(self):
        urls, duplicates, invalid, _entries = self._table_image_link_state()
        if duplicates == 1:
            duplicate_summary = self._t(
                "orbea.tables.urls.duplicate.one", "1 duplicate ignored"
            )
        else:
            duplicate_summary = self._t(
                "orbea.tables.urls.duplicate.many",
                "{count:,} duplicates ignored",
                count=duplicates,
            )
        if invalid:
            summary = self._t(
                "orbea.tables.urls.summary.invalid",
                "Products: {unique:,} • {duplicate_summary} • Invalid lines: {invalid:,}",
                unique=len(urls),
                duplicate_summary=duplicate_summary,
                invalid=len(invalid),
            )
        elif urls:
            summary = self._t(
                "orbea.tables.urls.summary",
                "Products: {unique:,} • {duplicate_summary}",
                unique=len(urls),
                duplicate_summary=duplicate_summary,
            )
        else:
            summary = self._t(
                "orbea.tables.urls.hint",
                "Paste one Orbea product-page URL per line. No Pimbo scan is used.",
            )
        self._table_image_urls_hint.setText(summary)
        self._update_action_states()

    def _photo_link_state(
        self,
    ) -> tuple[tuple[str, ...], int, tuple[str, ...], tuple[str, ...]]:
        from tools.orbea_automation import (
            normalize_orbea_product_url,
            unique_orbea_product_urls,
        )

        entries: list[str] = []
        invalid: list[str] = []
        for line in self._photo_url_edit.toPlainText().splitlines():
            value = line.strip().rstrip(".\"'()[]{}<>")
            if not value:
                continue
            try:
                entries.append(normalize_orbea_product_url(value))
            except (TypeError, ValueError):
                invalid.append(line.strip())
        unique, duplicates = unique_orbea_product_urls(entries)
        return unique, len(duplicates), tuple(invalid), tuple(entries)

    def _photo_urls(self) -> tuple[str, ...]:
        return self._photo_link_state()[0]

    def _photo_url(self) -> str:
        urls = self._photo_urls()
        return urls[0] if urls else ""

    def _on_photo_urls_changed(self):
        urls, duplicates, invalid, _entries = self._photo_link_state()
        duplicate_summary = (
            self._t("orbea.photo.urls.duplicate.one", "1 duplicate ignored")
            if duplicates == 1
            else self._t(
                "orbea.photo.urls.duplicate.many",
                "{count:,} duplicates ignored",
                count=duplicates,
            )
        )
        if invalid:
            summary = self._t(
                "orbea.photo.urls.summary.invalid",
                "Products: {unique:,} • {duplicate_summary} • Invalid lines: {invalid:,}",
                unique=len(urls),
                duplicate_summary=duplicate_summary,
                invalid=len(invalid),
            )
        elif urls:
            summary = self._t(
                "orbea.photo.urls.summary",
                "Products: {unique:,} • {duplicate_summary}",
                unique=len(urls),
                duplicate_summary=duplicate_summary,
            )
        else:
            summary = self._t(
                "orbea.photo.urls.hint",
                "Enter one product URL per line. Duplicate links are ignored automatically.",
            )
        self._photo_urls_hint.setText(summary)
        self._update_action_states()

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
            if not re.match(r"^https?://(?:cms|www)\.orbea\.com/[^?#\s]+", url, re.IGNORECASE):
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
        saved = self._saved_resume_config()
        if saved is not None and self._saved_scan_complete(saved):
            # Saved website collection has no dependency on Pimbo's filters.
            self._update_action_states()
            return
        driver = getattr(self.main, "driver", None)
        if (
            driver is not None
            and id(driver) != self._auto_refreshed_driver_id
            and not self.is_running()
        ):
            self._auto_refreshed_driver_id = id(driver)
            self.refresh_filter_options(show_errors=False)

    def on_activated(self) -> None:
        """Finish deferred browser setup after a login-time screen preload."""
        self._update_action_states()
        self._auto_refresh_filters()

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
        if hasattr(self.main, "track_worker"):
            self.main.track_worker(
                self._filter_worker, "orbea", "orbea", stage="Loading Pimbo filters"
            )
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
            self._progress_stop_btn.setEnabled(False)
            self._stage_label.setText(self._t("orbea.stopping", "Stopping safely…"))
            return
        # A new scan reads the current Pimbo products; Resume keeps saved work.
        self._start_run(resume=False, retry_failed=False)

    def _start_run(
        self,
        *,
        resume: bool,
        retry_failed: bool,
        retry_matched: bool = False,
        require_existing: bool = False,
        download_missing: bool = False,
        config_override=None,
    ):
        if self.is_running():
            return
        self._closing = False
        driver = getattr(self.main, "driver", None)
        try:
            config = config_override or (self._saved_resume_config(retry_failed=retry_failed, retry_matched=retry_matched) if require_existing else None)
            if require_existing and config is None:
                message = self._t("orbea.retry_matched.none", "No saved run with matched products was found in this output folder.") if retry_matched else self._t("orbea.resume.none", "No saved incomplete run was found in this output folder.")
                self._warn(self._t("orbea.resume.none.title", "Nothing to resume"), message)
                return
            if config is None:
                if not self._validate_inputs():
                    return
                config = self._create_run_config()
            saved_scan = bool(resume and config.resume_run_dir and (retry_matched or download_missing or config.downloads_only or self._saved_scan_complete(config)))
            if driver is None and not saved_scan:
                self._warn(self._t("common.error", "Not connected"), self._t("batchdesc.no_session", "Log in to Pimbo first."))
                return
            if require_existing:
                self._restore_run_controls(config)
        except Exception as exc:
            self._error(self._t("orbea.service.error.title", "Orbea service unavailable"), str(exc))
            return
        if not saved_scan and not self._acquire_browser():
            self._warn(self._t("orbea.browser.busy.title", "Browser busy"), self._t("orbea.browser.busy", "Another tool is using Pimbo."))
            return

        self._save_paths()
        self._save_filter_state()
        self._table.setRowCount(0)
        self._report_details.hide()
        self._upload_panel.clear_products()
        self._workbook_path = None
        self._run_dir = None
        self._open_excel_btn.setEnabled(False)
        self._open_folder_btn.setEnabled(False)
        self._log.clear()
        self._progress.setValue(0)
        self._switch_section("progress")
        self._set_busy(True)
        self._worker = OrbeaRunWorker(
            driver,
            self._make_service,
            config,
            resume=resume,
            retry_failed=retry_failed,
            retry_matched=retry_matched,
            **({"download_missing": True} if download_missing else {}),
        )
        self._worker.progress_changed.connect(self._on_progress)
        self._worker.log_message.connect(self._append_log)
        self._worker.succeeded.connect(self._on_result)
        self._worker.partial_result.connect(self._on_partial_result)
        self._worker.website_blocked.connect(self._on_website_blocked)
        self._worker.failed.connect(self._on_run_error)
        self._worker.finished.connect(self._run_thread_finished)
        if hasattr(self.main, "track_worker"):
            operation = self.main.track_worker(
                self._worker,
                "orbea",
                "orbea",
                output_path=str(config.output_root),
                resume_kind="orbea_checkpoint",
                resume_ref=str(config.output_root),
            )
            self._run_operation_id = operation.id
        self._worker.start()

    def _load_saved_collection(self, path=None):
        if self.is_running():
            return
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self,
                self._t("orbea.saved_collection.pick", "Select a finished Orbea Excel report"),
                str(self._setting_get("orbea_saved_collection_path", self._output_edit.text())), "Excel (*.xlsx)")
        if not path:
            return
        try:
            from tools.orbea_automation.saved_collection import open_saved_collection
            config, result = open_saved_collection(path, Path(self._output_edit.text().strip() or Path(path).parent),
                browser_name=str(self._setting_get("browser_choice", "Chrome") or "Chrome").lower())
            self._restore_run_controls(config)
            self._load_run_result(result)
            self._setting_set("orbea_saved_collection_path", str(path))
            self._open_excel_btn.setEnabled(self._workbook_path.is_file())
            self._open_folder_btn.setEnabled(True)
            self._stage_label.setText(self._t("orbea.saved_collection.loaded", "Saved collection loaded — choose items to download"))
            self._switch_section("setup")
            self._update_action_states()
        except Exception as exc:
            self._error(self._t("orbea.saved_collection.error", "Could not open saved collection"), str(exc))

    def _saved_download_config(self):
        try:
            from tools.orbea_automation.checkpoint import saved_run_config
            from tools.orbea_automation.saved_collection import collection_download_counts
            if self._run_dir and (self._run_dir / "run_checkpoint.json").is_file():
                if collection_download_counts(self._run_dir)["total"]:
                    return saved_run_config(self._run_dir)
            return self._saved_resume_config(retry_matched=True)
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _download_saved_items(self):
        if self.is_running():
            return
        config = self._saved_download_config()
        if config is None:
            return
        from dataclasses import replace
        checks = self._collection_checkboxes()
        config = replace(config, collect_product_data=True, downloads_only=True,
            download_images=checks["tables"].isChecked(), download_product_photos=checks["photos"].isChecked(),
            download_description=checks["description"].isChecked(), download_specifications=checks["specifications"].isChecked())
        self._start_run(resume=True, retry_failed=False, download_missing=True, config_override=config)

    def _saved_resume_config(self, *, retry_failed=False, retry_matched=False):
        if not hasattr(self, "_output_edit") or not self._output_edit.text().strip():
            return None
        try:
            from tools.orbea_automation import find_latest_saved_run, saved_run_config
            run_dir = find_latest_saved_run(Path(self._output_edit.text().strip()), include_completed_errors=retry_failed, matched_only=retry_matched)
            return saved_run_config(run_dir, browser_name=str(self._setting_get("browser_choice", "Chrome") or "Chrome").strip().lower()) if run_dir else None
        except (OSError, ValueError, KeyError, TypeError):
            return None

    @staticmethod
    def _saved_scan_complete(config) -> bool:
        if not config.resume_run_dir:
            return False
        try:
            data = json.loads((config.resume_run_dir / "run_checkpoint.json").read_text(encoding="utf-8"))
            return bool(data.get("scan_completed"))
        except (OSError, ValueError):
            return False

    def _restore_run_controls(self, config):
        self._catalogue_edit.setText(str(config.catalogue_path or ""))
        self._output_edit.setText(str(config.output_root))
        state = {**config.filters.as_dict(), "product_code_prefix": config.product_code_prefix}
        options = {}
        for key, field in (("families", "family_id"), ("categories", "category_id"), ("sources", "source_id")):
            if state[field]:
                options[key] = [(self._t("orbea.filters.saved_selection", "Saved selection"), state[field])]
        self._apply_filter_options(options, state=state)
        for key, selected in (("tables", config.download_images), ("photos", config.download_product_photos),
                              ("description", config.download_description), ("specifications", config.download_specifications)):
            self._collection_checkboxes()[key].setChecked(selected)

    def _on_progress(self, update):
        stage = str(_plain(_read(update, "stage", "phase", default="Running")) or "Running")
        message = str(_read(update, "message", "detail", default="") or "")
        current = int(_read(update, "current", "done", default=0) or 0)
        total = int(_read(update, "total", default=0) or 0)
        eta = _read(update, "eta_seconds", "eta", default=None)
        self._stage_label.setText(self._t(f"orbea.stage.{stage}", stage.replace("_", " ").title()))
        self._progress_label.setText(message or (f"{current:,} / {total:,}" if total else f"{current:,}"))
        self._progress.setValue(max(0, min(100, int(current * 100 / total)))) if total else self._progress.setValue(0)
        self._eta_label.setText(self._format_eta(eta))
        self._update_counts(_read(update, "counts", default={}) or {})

    def _load_run_result(self, result):
        workbook = _read(result, "workbook_path", "excel_path")
        run_dir = _read(result, "run_dir", "output_dir")
        self._workbook_path = Path(workbook) if workbook else None
        self._run_dir = Path(run_dir) if run_dir else (self._workbook_path.parent if self._workbook_path else None)
        self._update_counts(_read(result, "counts", default={}) or {})
        if self._workbook_path and self._workbook_path.exists():
            self._load_workbook_preview(self._workbook_path)
        if self._run_dir and self._run_dir.is_dir():
            self._report_details.show()
            self._upload_panel.load_packages(self._run_dir)

    def _on_partial_result(self, result):
        self._load_run_result(result)
        if self._run_operation_id and hasattr(self.main, "operation_tracker"):
            self.main.operation_tracker.update(
                self._run_operation_id,
                output_path=str(self._run_dir or ""),
                resume_ref=str(_read(result, "checkpoint_path", default="") or self._run_dir or ""),
            )
        self._switch_section("results")

    def _on_result(self, result):
        self._load_run_result(result)
        cancelled = bool(_read(result, "cancelled", default=False))
        completed = bool(_read(result, "completed", default=not cancelled))
        if self._run_operation_id and hasattr(self.main, "operation_tracker"):
            status = "cancelled" if cancelled else ("succeeded" if completed else "partial")
            checkpoint = _read(result, "checkpoint_path", default="")
            self.main.operation_tracker.update(
                self._run_operation_id,
                resume_ref=str(checkpoint or self._run_dir or ""),
            )
            self.main.operation_tracker.finish(
                self._run_operation_id,
                status,
                output_path=str(self._run_dir or self._workbook_path or ""),
                summary=dict(_read(result, "counts", default={}) or {}),
            )
        if cancelled:
            self._stage_label.setText(self._t("orbea.cancelled", "Stopped — partial report saved"))
        elif completed:
            self._stage_label.setText(self._t("orbea.complete", "Complete"))
            self._progress.setValue(100)
        else:
            self._stage_label.setText(self._t("orbea.incomplete", "Incomplete — ready to resume"))
        self._switch_section("results")

    def _on_run_error(self, message: str):
        if self._run_operation_id and hasattr(self.main, "operation_tracker"):
            self.main.operation_tracker.finish(
                self._run_operation_id, "failed", error_summary=message
            )
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

    def _on_website_blocked(self, message: str):
        if self._run_operation_id and hasattr(self.main, "operation_tracker"):
            self.main.operation_tracker.finish(
                self._run_operation_id, "partial", output_path=str(self._run_dir or ""),
                error_summary=message,
            )
        self._stage_label.setText(self._t("orbea.website.blocked", "Waiting for Orbea access — saved work is ready to resume"))
        self._progress_label.setText(message)
        self._append_log(message)
        self._switch_section("results")

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
        self._switch_section("progress")
        self._stage_label.setText(
            self._t("orbea.excel_sort.running", "Sorting existing Excel…")
        )
        self._append_log(f"Sorting existing Excel: {path}")
        self._excel_sort_worker = OrbeaExcelSortWorker(Path(path))
        self._excel_sort_worker.succeeded.connect(self._on_excel_sorted)
        self._excel_sort_worker.failed.connect(self._on_excel_sort_error)
        self._excel_sort_worker.finished.connect(self._excel_sort_finished)
        if hasattr(self.main, "track_worker"):
            self.main.track_worker(
                self._excel_sort_worker,
                "orbea",
                "orbea",
                output_path=str(Path(path).parent),
            )
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
        self._switch_section("results")
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
        set_controls_locked(self, busy, active_button=self._start_btn)
        if busy:
            self._collection_progress_card.show()
            self._resume_hint.setText(self._t("orbea.resume.running", "Collection is running. Use Stop to pause before resuming."))
        self._progress_stop_btn.setVisible(busy)
        self._progress_stop_btn.setEnabled(busy)
        if busy:
            self._start_btn.setText(self._t("orbea.stop", "Stop"))
            self._start_btn.setIcon(FluentIcon.CLOSE)
            self._start_btn.setEnabled(True)
            self._stage_label.setText(self._t("orbea.starting", "Starting…"))
        else:
            self._start_btn.setText(self._t("orbea.start", "Scan Pimbo and collect Orbea data"))
            self._start_btn.setIcon(FluentIcon.SEARCH)

    # --------------------------------------------------- Description extractor

    def _on_description_start_stop(self):
        self._description_workflow.start_stop()

    def _validate_description_inputs(self) -> bool:
        return self._description_workflow.validate_inputs()

    def _on_description_progress(self, update):
        self._description_workflow.on_progress(update)

    def _on_description_result(self, result):
        self._description_workflow.on_result(result)

    def _on_description_error(self, message: str):
        self._description_workflow.on_error(message)

    def _description_thread_finished(self):
        self._description_workflow.finished()

    def _set_description_busy(self, busy: bool):
        self._description_workflow.set_busy(busy)

    # ---------------------------------------------------- Direct table downloader

    def _on_table_image_start_stop(self):
        self._table_image_workflow.start_stop()

    def _validate_table_image_inputs(self) -> bool:
        return self._table_image_workflow.validate_inputs()

    def _on_table_image_progress(self, update):
        self._table_image_workflow.on_progress(update)

    def _on_table_image_result(self, result):
        self._table_image_workflow.on_result(result)

    def _on_table_image_error(self, message: str):
        self._table_image_workflow.on_error(message)

    def _table_image_thread_finished(self):
        self._table_image_workflow.finished()

    def _set_table_image_busy(self, busy: bool):
        self._table_image_workflow.set_busy(busy)

    # --------------------------------------------------------- Photo downloader

    def _on_photo_start_stop(self):
        self._photo_workflow.start_stop()

    def _validate_photo_inputs(self) -> bool:
        return self._photo_workflow.validate_inputs()

    def _on_photo_progress(self, update):
        self._photo_workflow.on_progress(update)

    def _on_photo_result(self, result):
        self._photo_workflow.on_result(result)

    def _on_photo_error(self, message: str):
        self._photo_workflow.on_error(message)

    def _photo_thread_finished(self):
        self._photo_workflow.finished()

    def _set_photo_busy(self, busy: bool):
        self._photo_workflow.set_busy(busy)

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
        self._report_details.show()
        rows: list[list[str]] = []
        total_rows = 0
        try:
            import openpyxl

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
                    status_role = "success" if "code" in lower or lower == "match" else "warning"
                    item.setForeground(QColor(get_status_text_color(status_role, isDarkTheme())))
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
        if catalogue:
            try:
                available = Path(catalogue).is_file()
            except OSError:
                available = False
            if not available:
                # The catalogue is optional. A stale saved path must not block
                # a fresh Pimbo scan followed by public website lookup.
                catalogue = ""
                self._setting_set(CATALOGUE_SETTING, "")
        output = str(self._setting_get(OUTPUT_SETTING, "") or "").strip()
        description_output = str(
            self._setting_get(DESCRIPTION_OUTPUT_SETTING, "") or ""
        ).strip()
        photo_output = str(self._setting_get(PHOTO_OUTPUT_SETTING, "") or "").strip()
        table_output = str(self._setting_get(TABLE_OUTPUT_SETTING, "") or "").strip()
        if not catalogue:
            catalogue = self._detect_catalogue()
        if not output:
            output = str(self._desktop_dir() / "UltraBike Orbea Runs")
        if not description_output:
            description_output = str(self._desktop_dir() / "UltraBike Orbea Descriptions")
        if not photo_output:
            photo_output = str(self._desktop_dir() / "UltraBike Orbea Photos")
        if not table_output:
            table_output = str(self._desktop_dir() / "UltraBike Orbea Downloads")
        self._catalogue_edit.setText(catalogue)
        self._output_edit.setText(output)
        self._description_output_edit.setText(description_output)
        self._photo_output_edit.setText(photo_output)
        self._table_image_output_edit.setText(table_output)
        self._table_geometry_check.setChecked(
            self._setting_bool(DIRECT_GEOMETRY_SETTING, True)
        )
        self._table_size_guide_check.setChecked(
            self._setting_bool(DIRECT_SIZE_GUIDE_SETTING, True)
        )
        self._table_product_photos_check.setChecked(
            self._setting_bool(DIRECT_PRODUCT_PHOTOS_SETTING, False)
        )
        choices = self._setting_get(COLLECTION_SETTING, {})
        if isinstance(choices, str):
            try:
                choices = json.loads(choices)
            except (ValueError, TypeError):
                choices = {}
        choices = choices if isinstance(choices, dict) else {}
        for key, checkbox in self._collection_checkboxes().items():
            checkbox.setChecked(bool(choices.get(key, True)))
        candidate = Path(description_output)
        self._description_output_dir = candidate if candidate.exists() else None
        photo_candidate = Path(photo_output)
        self._photo_output_dir = photo_candidate if photo_candidate.exists() else None
        self._photo_open_btn.setEnabled(bool(self._photo_output_dir))
        table_candidate = Path(table_output)
        self._table_output_dir = table_candidate if table_candidate.exists() else None
        self._table_image_open_btn.setEnabled(bool(self._table_output_dir))

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

    def _browse_photo_output(self):
        path = QFileDialog.getExistingDirectory(
            self,
            self._t("orbea.photo.output.pick", "Select photo output folder"),
            self._photo_output_edit.text(),
        )
        if path:
            self._photo_output_edit.setText(path)
            self._photo_output_changed()

    def _browse_table_image_output(self):
        path = QFileDialog.getExistingDirectory(
            self,
            self._t(
                "orbea.tables.output.pick",
                "Select table-image output folder",
            ),
            self._table_image_output_edit.text(),
        )
        if path:
            self._table_image_output_edit.setText(path)
            self._table_image_output_changed()

    def _description_output_changed(self):
        self._save_description_output()
        path = Path(self._description_output_edit.text().strip())
        self._description_output_dir = path if path.exists() else None
        self._description_open_btn.setEnabled(bool(self._description_output_dir))
        self._update_action_states()

    def _photo_output_changed(self):
        self._save_photo_output()
        value = self._photo_output_edit.text().strip()
        path = Path(value) if value else None
        self._photo_output_dir = path if path is not None and path.exists() else None
        self._photo_open_btn.setEnabled(bool(self._photo_output_dir))
        self._update_action_states()

    def _table_image_output_changed(self):
        self._save_table_image_output()
        value = self._table_image_output_edit.text().strip()
        path = Path(value) if value else None
        self._table_output_dir = path if path is not None and path.exists() else None
        self._table_image_open_btn.setEnabled(bool(self._table_output_dir))
        self._update_action_states()

    def _paths_changed(self):
        self._save_paths()
        self._update_action_states()

    def _download_options_changed(self, _state=None):
        self._setting_set(COLLECTION_SETTING, json.dumps({key: checkbox.isChecked() for key, checkbox in self._collection_checkboxes().items()}))
        self._setting_set(TABLE_IMAGES_SETTING, self._table_images_check.isChecked())
        self._setting_set(PRODUCT_PHOTOS_SETTING, self._product_photos_check.isChecked())
        self._update_action_states()

    def _collection_checkboxes(self):
        return {"tables": self._table_images_check, "photos": self._product_photos_check,
                "description": self._description_check, "specifications": self._specifications_check}

    def _save_paths(self):
        self._setting_set(CATALOGUE_SETTING, self._catalogue_edit.text().strip())
        self._setting_set(OUTPUT_SETTING, self._output_edit.text().strip())

    def _save_description_output(self):
        self._setting_set(
            DESCRIPTION_OUTPUT_SETTING,
            self._description_output_edit.text().strip(),
        )

    def _save_photo_output(self):
        self._setting_set(PHOTO_OUTPUT_SETTING, self._photo_output_edit.text().strip())

    def _save_table_image_output(self):
        self._setting_set(
            TABLE_OUTPUT_SETTING,
            self._table_image_output_edit.text().strip(),
        )

    def _validate_inputs(self) -> bool:
        catalogue = Path(self._catalogue_edit.text().strip())
        if self._catalogue_edit.text().strip() and (not catalogue.is_file() or catalogue.suffix.lower() != ".xlsx"):
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

    def _open_photo_folder(self):
        if self._photo_output_dir and self._photo_output_dir.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._photo_output_dir)))

    def _open_table_image_folder(self):
        if self._table_output_dir and self._table_output_dir.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._table_output_dir)))

    # ---------------------------------------------------------- App lifecycle

    def _acquire_browser(self) -> bool:
        acquired = self.workflow_controller.acquire_browser()
        self._owns_browser_lease = self.workflow_controller.owns_browser_lease
        return acquired

    def _release_browser(self):
        self.workflow_controller.release_browser()
        self._owns_browser_lease = self.workflow_controller.owns_browser_lease

    def is_running(self) -> bool:
        return current_activity(self).name != "idle"

    def shutdown(self, wait_ms: int = 5000) -> bool:
        """Request a checkpointed stop and wait briefly; never terminate threads."""
        self._closing = True
        workers = [
            worker
            for worker in (
                self._worker,
                self._filter_worker,
                self._description_worker,
                self._photo_worker,
                self._table_image_worker,
                self._excel_sort_worker,
                self._upload_panel.worker,
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

    def _setting_bool(self, key: str, default: bool) -> bool:
        value = self._setting_get(key, default)
        if isinstance(value, str):
            normalized = value.strip().casefold()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off", ""}:
                return False
        return bool(value)

    def _setting_set(self, key: str, value):
        try:
            if self.settings is not None:
                self.settings.set(key, value)
        except Exception:
            pass

    def _update_action_states(self):
        self._update_more_filters_title()
        self._upload_panel.update_state()
        activity = current_activity(self)
        filter_running = activity.name == "filters"
        if activity.name not in {"idle", "filters"}:
            buttons = {
                "collection": self._start_btn,
                "description": self._description_start_btn,
                "photos": self._photo_start_btn,
                "tables": self._table_image_start_btn,
            }
            set_controls_locked(
                self, True, active_button=buttons.get(activity.name),
                stopping=activity.stopping, upload_active=activity.name == "upload",
            )
            self._progress_stop_btn.setEnabled(
                activity.name == "collection" and not activity.stopping
            )
            return
        set_controls_locked(self, filter_running)
        catalogue = self._catalogue_edit.text().strip()
        try:
            catalogue_valid = not catalogue or (Path(catalogue).is_file() and Path(catalogue).suffix.lower() == ".xlsx")
        except OSError:
            catalogue_valid = False
        valid = bool(
            getattr(self.main, "driver", None) is not None
            and catalogue_valid
            and self._output_edit.text().strip()
            and not filter_running
        )
        self._start_btn.setEnabled(valid)
        if valid:
            self._start_btn.setToolTip("")
        elif filter_running:
            self._start_btn.setToolTip(self._t("orbea.filters.loading", "Loading Pimbo filters…"))
        elif getattr(self.main, "driver", None) is None:
            self._start_btn.setToolTip(self._t("batchdesc.no_session", "Log in to Pimbo first."))
        elif not catalogue_valid:
            self._start_btn.setToolTip(self._t("orbea.catalogue.invalid", "Choose a valid Orbea catalogue .xlsx file, or clear this field to search the website."))
        else:
            self._start_btn.setToolTip(self._t("orbea.output.invalid", "Choose an output folder."))
        saved = self._saved_resume_config()
        retry = self._saved_resume_config(retry_failed=True)
        connected = getattr(self.main, "driver", None) is not None
        can_resume = lambda config: bool(config and not filter_running and (connected or self._saved_scan_complete(config)))
        self._resume_btn.setEnabled(can_resume(saved))
        self._retry_btn.setEnabled(can_resume(retry))
        matched = self._saved_resume_config(retry_matched=True)
        self._retry_matched_btn.setEnabled(bool(matched and not filter_running))
        self._retry_matched_btn.setToolTip(
            self._t("orbea.retry_matched.ready", "Refresh the saved downloads for every matched product in run {run}, including successful downloads. Its download choices will be restored.", run=matched.resume_run_dir.name)
            if matched else self._t("orbea.retry_matched.none", "No saved run with matched products was found in this output folder.")
        )
        self._load_collection_btn.setEnabled(not filter_running)
        download_config = self._saved_download_config()
        self._download_missing_btn.setEnabled(bool(download_config and not filter_running and
            any(check.isChecked() for check in self._collection_checkboxes().values())))
        self._download_missing_btn.setToolTip(self._t("orbea.saved_collection.download_tip",
            "Use saved Orbea links and download only missing selected items. Completed files are kept."))
        if download_config:
            from tools.orbea_automation.saved_collection import collection_download_counts
            try:
                counts = collection_download_counts(download_config.resume_run_dir)
                self._saved_download_hint.setText(self._t("orbea.saved_collection.summary",
                    "Saved collection {run}: {total} matched products. Ready — photos {photos}, descriptions {description}, specifications {specifications}, tables {tables}.",
                    run=download_config.resume_run_dir.name, **counts))
            except (OSError, ValueError, TypeError):
                self._saved_download_hint.setText("")
        else:
            self._saved_download_hint.setText(self._t("orbea.saved_collection.hint",
                "Open a finished Orbea Excel report to add downloads using its saved product links."))
        for button, config in ((self._resume_btn, saved), (self._retry_btn, retry)):
            if can_resume(config):
                message = self._t("orbea.resume.ready", "Continue saved run {run}. Its filters and download choices will be restored.", run=config.resume_run_dir.name)
            elif config and not connected:
                message = self._t("orbea.resume.login", "Log in to Pimbo to finish the saved product scan.")
            elif filter_running:
                message = self._t("orbea.filters.loading", "Loading Pimbo filters…")
            else:
                message = self._t("orbea.resume.none", "No saved incomplete run was found in this output folder.")
            button.setToolTip(message)
        self._resume_hint.setText(self._t("orbea.saved_collection.continue",
            "Choose additional items above, then download missing items using the saved links. Pimbo login is not needed.")
            if download_config else self._resume_btn.toolTip())
        self._description_start_btn.setEnabled(
            bool(
                not filter_running
                and self._description_urls()
                and self._description_output_edit.text().strip()
            )
        )
        photo_urls, _duplicates, photo_invalid, _entries = self._photo_link_state()
        self._photo_start_btn.setEnabled(
            bool(
                not filter_running
                and photo_urls
                and not photo_invalid
                and self._photo_output_edit.text().strip()
            )
        )
        table_urls, _duplicates, table_invalid, _entries = (
            self._table_image_link_state()
        )
        self._table_image_start_btn.setEnabled(
            bool(
                not filter_running
                and table_urls
                and not table_invalid
                and any(self._table_image_selection())
                and self._table_image_output_edit.text().strip()
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

    def _append_photo_log(self, message: str):
        if message:
            self._photo_log.appendPlainText(str(message))

    def _append_table_image_log(self, message: str):
        if message:
            self._table_image_log.appendPlainText(str(message))

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
        bg = table["row_bg_dark"] if dark else table["row_bg_light"]
        alt = table["row_alt_bg_dark"] if dark else table["row_alt_bg_light"]
        border = table["border_dark"] if dark else table["border_light"]
        text = COLORS["text_primary_dark"] if dark else COLORS["text_primary_light"]
        muted = COLORS["text_secondary_dark"] if dark else COLORS["text_secondary_light"]
        header_bg = table["header_bg_dark" if dark else "header_bg_light"]
        header_text = table["header_text_dark" if dark else "header_text_light"]
        accent_colors = get_accent_colors(dark)
        accent = accent_colors["base"]
        accent_text = accent_colors["text"]
        accent_hover = accent_colors["hover"]
        accent_pressed = accent_colors["pressed"]
        accent_soft = rgba_from_hex(accent, 0.16 if dark else 0.07)
        outline = get_subtle_border(dark)
        hover = get_subtle_item_hover_bg(dark)
        disabled_bg = COLORS["disabled_surface_dark"] if dark else COLORS["disabled_surface_light"]
        danger = COLORS["error_text_dark"] if dark else COLORS["error_text_light"]

        self._section_tabs.setStyleSheet(f"""
            QTabBar::tab {{
                background: transparent;
                color: {muted};
                padding: {PADDINGS['tab']};
                border: none;
                border-bottom: 3px solid transparent;
            }}
            QTabBar::tab:hover {{
                background: {hover};
                color: {text};
            }}
            QTabBar::tab:selected {{
                background: {accent_soft};
                color: {accent};
                border-bottom: 3px solid {accent};
                font-weight: 600;
            }}
        """)
        primary_style = f"""
            PrimaryPushButton {{
                background-color: {accent};
                border: 1px solid {accent};
                color: {accent_text};
                font-weight: 600;
                border-radius: {RADII['md']}px;
                padding: 8px 14px;
                min-height: 20px;
            }}
            PrimaryPushButton[hasIcon=true] {{ padding-left: 36px; }}
            PrimaryPushButton:hover {{
                background-color: {accent_hover};
                border-color: {accent_hover};
            }}
            PrimaryPushButton:pressed {{
                background-color: {accent_pressed};
                border-color: {accent_pressed};
            }}
            PrimaryPushButton:disabled {{
                background-color: {disabled_bg};
                border-color: {border};
                color: {muted};
            }}
        """
        for button in (
            self._start_btn,
            self._description_start_btn,
            self._photo_start_btn,
            self._table_image_start_btn,
        ):
            button.setStyleSheet(primary_style)
        self._progress_stop_btn.setStyleSheet(f"""
            PushButton {{
                background: transparent;
                border: 1px solid {rgba_from_hex(danger, 0.65)};
                color: {danger};
                border-radius: {RADII['sm']}px;
            }}
            PushButton:hover {{ background: {rgba_from_hex(danger, 0.10)}; }}
        """)
        self._table.setStyleSheet(f"""
            QTableWidget {{ background: {bg}; alternate-background-color: {alt}; color: {text}; border: 1px solid {border}; border-radius: {RADII['md']}px; gridline-color: transparent; }}
            QTableWidget::viewport {{ background: {bg}; border-radius: {RADII['md']}px; }}
            QTableWidget::item {{ padding: {PADDINGS['table_cell']}; border: none; border-bottom: 1px solid {border}; }}
            QTableWidget::item:hover {{ background: {hover}; }}
            QTableWidget::item:selected {{ background: {get_selection_bg(dark)}; color: {text}; }}
            QHeaderView::section {{ background: {header_bg}; color: {header_text}; padding: {PADDINGS['table_header']}; border: none; font-weight: 600; font-size: {FONTS['size_body_sm']}; }}
        """)
        if hasattr(self, "_upload_panel"):
            self._upload_panel.table.setStyleSheet(self._table.styleSheet())
            self._upload_panel.start.setStyleSheet(primary_style)
        self._style_filter_buttons()

    def _style_filter_buttons(self) -> None:
        if not hasattr(self, "_status_buttons"):
            return
        dark = isDarkTheme()
        accent = COLORS["lavender_grey"] if dark else COLORS["space_indigo"]
        accent_text = COLORS["space_indigo"] if dark else COLORS["text_white"]
        text = COLORS["text_primary_dark"] if dark else COLORS["text_primary_light"]
        outline = get_subtle_border(dark)
        hover = get_subtle_item_hover_bg(dark)
        style = f"""
            PillPushButton {{
                background: transparent;
                border: 1px solid {outline};
                color: {text};
                border-radius: 14px;
                padding: 6px 12px;
                min-height: 16px;
            }}
            PillPushButton:hover {{ background: {hover}; }}
            PillPushButton:checked {{
                background: {accent};
                border-color: {accent};
                color: {accent_text};
                font-weight: 600;
            }}
        """
        for collection in (
            self._status_buttons,
            self._stock_buttons,
            self._bucket_buttons,
        ):
            for button in collection.values():
                button.setStyleSheet(style)

    def retranslate_ui(self):
        self.tr = self.main.i18n.tr
        self._title.setText(self._t("orbea.title", "Orbea Automation"))
        self._subtitle.setText(
            self._t(
                "orbea.subtitle",
                "Read products from Pimbo, collect Orbea data, then upload the selected updates.",
            )
        )
        self._section_tabs.setTabText(0, self._t("orbea.tab.automation", "Automation"))
        self._section_tabs.setTabText(1, self._t("orbea.tab.tools", "Extra tools"))
        self._collection_details.set_title(self._t("orbea.collection.log", "Collection details and log"))
        self._report_details.set_title(self._t("orbea.collection.report", "Collection report"))
        self._image_tool.set_title(self._t("orbea.tool.images", "Download images from a link"))
        self._description_tool.set_title(self._t("orbea.tool.descriptions", "Extract descriptions from a link"))
        self._excel_tool.set_title(self._t("orbea.tool.excel", "Sort an existing Excel report"))
        self._tools_hint.setText(self._t("orbea.tools.hint", "Optional shortcuts for individual links and existing reports. The main automation already collects images, descriptions and specs."))
        self._upload_panel.retranslate_ui()
        self._paths_title.setText(self._t("orbea.paths", "1. Get products from Pimbo"))
        self._catalogue_label.setText(self._t("orbea.catalogue", "Excel catalogue (optional)"))
        self._catalogue_edit.setPlaceholderText(self._t("orbea.catalogue.optional", "Optional — search the website if omitted"))
        self._output_label.setText(self._t("orbea.output", "Output folder"))
        self._downloads_label.setText(
            self._t("orbea.downloads", "Orbea data to download")
        )
        self._table_images_check.setText(
            self._t(
                "orbea.downloads.tables", "Geometry + CM size tables"
            )
        )
        self._product_photos_check.setText(
            self._t(
                "orbea.downloads.photos", "Product photos (all colours)"
            )
        )
        self._description_check.setText(self._t("orbea.downloads.description", "Source description"))
        self._specifications_check.setText(self._t("orbea.downloads.specifications", "Source specifications"))
        self._downloads_hint.setText(
            self._t(
                "orbea.downloads.hint",
                "Reads codes and full titles directly from Pimbo's product list, finds all URLs by exact TTCC code across Orbea regions, then saves the selected files. Upload changes in step 3.",
            )
        )
        self._search_label.setText(self._t("orbea.search", "Fixed Pimbo search"))
        self._catalogue_btn.setText(self._t("common.browse", "Browse"))
        self._output_btn.setText(self._t("common.browse", "Browse"))
        self._filters_title.setText(self._t("orbea.filters", "Choose Pimbo products"))
        self._refresh_btn.setText(self._t("orbea.filters.refresh", "Refresh filters"))
        self._status_label.setText(self._t("orbea.filters.status", "Status (select any)"))
        self._family_label.setText(self._t("orbea.filters.family", "Family"))
        self._category_label.setText(self._t("orbea.filters.category", "Category"))
        self._source_label.setText(self._t("orbea.filters.source", "Source"))
        self._locale_label.setText(self._t("orbea.filters.locale", "Completeness locale"))
        self._sort_label.setText(self._t("orbea.filters.sort", "Sort"))
        prefix_label = self._t("orbea.filters.code_prefix", "Product code starts with")
        prefix_hint = self._t(
            "orbea.filters.code_prefix.hint",
            "Uses the product code shown in the Pimbo list, ignoring letter case. Leave empty for all codes.",
        )
        self._code_prefix_label.setText(prefix_label)
        self._code_prefix_edit.setAccessibleName(prefix_label)
        self._code_prefix_edit.setAccessibleDescription(prefix_hint)
        self._code_prefix_edit.setToolTip(prefix_hint)
        self._code_prefix_edit.setPlaceholderText(
            self._t("orbea.filters.code_prefix.placeholder", "e.g. U or U107")
        )
        self._stock_label.setText(self._t("orbea.filters.stock", "Stock"))
        self._bucket_label.setText(self._t("orbea.filters.completeness", "Completeness"))
        self._actions_title.setText(
            self._t("orbea.actions", "Automatic product collection")
        )
        running = bool(self._worker and self._worker.isRunning())
        self._start_btn.setText(
            self._t("orbea.stop", "Stop")
            if running
            else self._t("orbea.start", "Scan Pimbo and collect Orbea data")
        )
        self._progress_stop_btn.setText(self._t("orbea.stop", "Stop"))
        self._resume_btn.setText(self._t("orbea.resume", "Resume latest"))
        self._retry_btn.setText(self._t("orbea.retry", "Retry failed"))
        self._retry_matched_btn.setText(self._t("orbea.retry_matched", "Retry matched downloads"))
        self._load_collection_btn.setText(self._t("orbea.saved_collection.open", "Open saved collection"))
        self._download_missing_btn.setText(self._t("orbea.saved_collection.download", "Download selected missing items"))
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
        self._table_image_title.setText(
            self._t("orbea.tables.title", "Orbea image downloader")
        )
        self._table_image_subtitle.setText(
            self._t(
                "orbea.tables.subtitle",
                "Choose geometry tables, the CM size guide, product photos, or any combination. Pimbo is not scanned.",
            )
        )
        self._table_image_url_label.setText(
            self._t("orbea.tables.url", "Orbea product URLs")
        )
        self._table_image_url_edit.setPlaceholderText(
            self._t(
                "orbea.tables.url.placeholder",
                "One product URL per line\nhttps://www.orbea.com/en-be/onna-20",
            )
        )
        self._table_image_types_label.setText(
            self._t("orbea.tables.types", "What to download")
        )
        self._table_geometry_check.setText(
            self._t(
                "orbea.tables.type.geometry",
                "Geometry — every frame size",
            )
        )
        self._table_size_guide_check.setText(
            self._t("orbea.tables.type.size_guide", "CM size guide")
        )
        self._table_product_photos_check.setText(
            self._t(
                "orbea.tables.type.product_photos",
                "Product photos — every colour and view",
            )
        )
        self._table_image_output_label.setText(
            self._t("orbea.tables.output", "Image output folder")
        )
        self._table_image_output_btn.setText(self._t("common.browse", "Browse"))
        table_running = bool(
            self._table_image_worker and self._table_image_worker.isRunning()
        )
        self._table_image_start_btn.setText(
            self._t("orbea.tables.stop", "Stop")
            if table_running
            else self._t("orbea.tables.download", "Download selected")
        )
        self._table_image_open_btn.setText(
            self._t("orbea.tables.open_folder", "Open download folder")
        )
        if not self._table_image_status_label.text():
            self._table_image_status_label.setText(
                self._t("orbea.tables.ready", "Orbea downloader ready")
            )
        if not self._table_image_progress_label.text():
            self._table_image_progress_label.setText(
                self._t(
                    "orbea.tables.ready.detail",
                    "Paste Orbea product pages, choose image types, then download.",
                )
            )
        self._on_table_image_urls_changed()
        self._photo_title.setText(
            self._t("orbea.photo.title", "Orbea product photos")
        )
        self._photo_subtitle.setText(
            self._t(
                "orbea.photo.subtitle",
                "Download every official colour as full-resolution images from Orbea’s product configurator.",
            )
        )
        self._photo_url_label.setText(
            self._t("orbea.photo.url", "Orbea product URLs")
        )
        self._photo_url_edit.setPlaceholderText(
            self._t(
                "orbea.photo.url.placeholder",
                "One product URL per line\nhttps://cms.orbea.com/en-au/kimu-27-h20",
            )
        )
        self._photo_output_label.setText(
            self._t("orbea.photo.output", "Photo output folder")
        )
        self._photo_output_btn.setText(self._t("common.browse", "Browse"))
        photo_running = bool(self._photo_worker and self._photo_worker.isRunning())
        self._photo_start_btn.setText(
            self._t("orbea.photo.stop", "Stop")
            if photo_running
            else self._t("orbea.photo.download", "Download all colours")
        )
        self._photo_open_btn.setText(
            self._t("orbea.photo.open_folder", "Open photos folder")
        )
        if not self._photo_status_label.text():
            self._photo_status_label.setText(
                self._t("orbea.photo.ready", "Photo downloader ready")
            )
        if not self._photo_progress_label.text():
            self._photo_progress_label.setText(
                self._t(
                    "orbea.photo.ready.detail",
                    "Paste one or more Orbea product URLs to download every published colour.",
                )
            )
        self._on_photo_urls_changed()
        self._description_title.setText(
            self._t("orbea.description.title", "Description extractor")
        )
        self._description_subtitle.setText(
            self._t(
                "orbea.description.subtitle",
                "Open the product's Features dialog and save its introduction and all feature cards. Older Orbea model pages are also supported.",
            )
        )
        self._description_urls_label.setText(
            self._t("orbea.description.urls", "Orbea product or model URLs")
        )
        self._description_urls_edit.setPlaceholderText(
            self._t(
                "orbea.description.urls.placeholder",
                "One URL per line, for example:\nhttps://www.orbea.com/es-es/orca-m11eltd-pwr",
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
            "images": self._t("orbea.stat.images", "Table images"),
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

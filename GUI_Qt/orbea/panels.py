"""Small presentation components for the Orbea workspace."""
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (Action, BodyLabel, CaptionLabel, CardWidget, CheckBox, ComboBox,
    DropDownPushButton, FlowLayout, FluentIcon, LineEdit, PlainTextEdit,
    PrimaryPushButton, ProgressBar, PushButton, RoundMenu, isDarkTheme)
from GUI_Qt.styles.screen_theme import CARD_MARGINS, CARD_SPACING, ROW_SPACING
from GUI_Qt.styles.theme_config import get_text_color
from .tabs import OrbeaDisclosure


STATUS_LABELS = (
    ("failed", "Failed"), ("no_changes", "No changes needed"),
    ("saved_automatically", "Saved"), ("ready_for_review", "Ready for review"),
    ("blocked_non_draft", "Blocked: not Draft"), ("unprocessed", "Not uploaded yet"),
    ("not_ready", "Not ready"), ("warnings", "With warnings"),
    ("no_photos", "No photos in Pimbo"), ("has_photos", "Has photos in Pimbo"),
    ("not_checked", "Photos not checked"), ("not_found", "Not found in Pimbo"),
    ("scan_error", "Photo scan error"),
    ("missing_content", "Missing required data"), ("missing_attributes", "Missing required attributes"),
    ("missing_general_specs", "Missing Bendra informacija specs"), ("content_complete", "Required data complete"),
    ("content_not_checked", "Data not checked"), ("content_scan_error", "Data scan error"),
    ("content_not_found", "Data scan: not found"),
)


def command(menu, callback):
    action = Action("", menu)
    action.triggered.connect(callback)
    menu.addAction(action)
    return action


def translate_choices(combo, choices, translate):
    previous = combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    for value, key, fallback in choices:
        combo.addItem(translate(key, fallback), userData=value)
    combo.setCurrentIndex(max(0, combo.findData(previous)))
    combo.blockSignals(False)


class StatusSelectionButton(DropDownPushButton):
    def __init__(self, labels, callback, parent=None):
        super().__init__(parent)
        self.labels = labels
        self.popup_menu = RoundMenu(parent=self)
        self.setMenu(self.popup_menu)
        self.status_actions = {status: command(self.popup_menu, lambda _checked=False, value=status: callback(value))
                               for status, _ in labels}
        self.setMinimumHeight(38)

    def retranslate_ui(self, translate, *, checked, status_prefix="status."):
        label = translate("select_status", "Select by status") if checked else translate("unselect_status", "Unselect by status")
        self.setText(label)
        self.popup_menu.setTitle(label)
        self.setToolTip(translate("status_selection_tip", "Changes matching visible rows only; other selections are retained."))
        for status, fallback in self.labels:
            self.status_actions[status].setText(translate(status_prefix + status, fallback))

    def set_available(self, enabled):
        self.setEnabled(enabled)
        for action in self.status_actions.values():
            action.setEnabled(enabled)


class ProductToolbar(QWidget):
    """Product loading, visible-row selection and prefix selection across the list."""
    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        row = FlowLayout()
        row.setHorizontalSpacing(8)
        row.setVerticalSpacing(8)
        self.load_button = DropDownPushButton(self)
        self.load_menu = RoundMenu(parent=self.load_button)
        self.load_button.setMenu(self.load_menu)
        self.load_excel = command(self.load_menu, lambda: panel.photo_scan.load_excel())
        self.browse = command(self.load_menu, panel._browse)
        self.reload = command(self.load_menu, panel._load_current)
        self.add_product = PushButton(FluentIcon.ADD, "", self)
        self.add_product.clicked.connect(lambda: panel.manual_products.open())
        self.edit_product = PushButton(FluentIcon.EDIT, "", self)
        self.edit_product.clicked.connect(lambda: panel.manual_products.open(edit=True))
        self.select_button = DropDownPushButton(self)
        self.select_menu = RoundMenu(parent=self.select_button)
        self.select_button.setMenu(self.select_menu)
        self.select_all = command(self.select_menu, lambda: panel._select(True))
        self.clear = command(self.select_menu, lambda: panel._select(False))
        self.select_status = StatusSelectionButton(STATUS_LABELS, panel._select_by_status, self)
        self.unselect_status = StatusSelectionButton(STATUS_LABELS, lambda status: panel._select_by_status(status, checked=False), self)
        self.status_menu = self.select_status.popup_menu
        self.status_actions = self.select_status.status_actions
        self.unselect_status_actions = self.unselect_status.status_actions
        self.scan_photos = PushButton(self)
        self.scan_photos.clicked.connect(panel.photo_scan.scan)
        self.scan_content = PushButton(self)
        self.scan_content.clicked.connect(panel.content_scan.scan)
        for control in (self.load_button, self.add_product, self.edit_product, self.select_button, self.select_status, self.unselect_status, self.scan_photos, self.scan_content):
            control.setMinimumHeight(38)
            row.addWidget(control)
        box.addLayout(row)
        row = QHBoxLayout()
        self.model_label = BodyLabel(self)
        self.model_filter = ComboBox(self)
        self.model_filter.setMinimumWidth(150)
        self.model_filter.setMinimumHeight(38)
        self.model_filter.currentIndexChanged.connect(panel._apply_model_filter)
        row.addWidget(self.model_label)
        row.addWidget(self.model_filter, 1)
        box.addLayout(row)
        self.exclusion = QWidget(self)
        exclusion_box = QVBoxLayout(self.exclusion)
        exclusion_box.setContentsMargins(0, 0, 0, 0)
        exclusion_box.setSpacing(4)
        self.exclusion_label = BodyLabel(self.exclusion)
        self.exclude_prefixes = LineEdit(self.exclusion)
        self.exclude_prefixes.setMinimumHeight(38)
        self.exclude_prefixes.setClearButtonEnabled(True)
        self.exclusion_label.setBuddy(self.exclude_prefixes)
        self.exclude_button = PushButton(self.exclusion)
        self.exclude_button.setMinimumHeight(38)
        self.exclude_button.clicked.connect(panel._exclude_by_code)
        self.include_button = PushButton(self.exclusion)
        self.include_button.setMinimumHeight(38)
        self.include_button.clicked.connect(panel._include_by_code)
        self.exclude_prefixes.returnPressed.connect(panel._exclude_by_code)
        self.exclude_prefixes.textChanged.connect(self._exclusion_changed)
        self.exclusion_hint = CaptionLabel(self.exclusion)
        self.exclusion_hint.setWordWrap(True)
        self.excluded_count = None
        self.included_count = None
        row = QHBoxLayout()
        row.addWidget(self.exclude_prefixes, 1)
        row.addWidget(self.include_button)
        row.addWidget(self.exclude_button)
        exclusion_box.addWidget(self.exclusion_label)
        exclusion_box.addLayout(row)
        exclusion_box.addWidget(self.exclusion_hint)
        box.addWidget(self.exclusion)

    def _exclusion_changed(self):
        self.excluded_count = None
        self.included_count = None
        self.refresh_exclusion_hint()
        self.panel.update_state()

    def refresh_exclusion_hint(self):
        tr = self.panel._t
        hint = tr("prefix_selection.hint", "Checks or unchecks matching bikes across the loaded list, including hidden rows. Separate prefixes with commas or spaces.")
        if self.excluded_count is not None:
            hint = tr("exclude.result", "{count} bikes unchecked.", count=self.excluded_count) + " " + hint
        elif self.included_count is not None:
            hint = tr("include.result", "{count} bikes checked.", count=self.included_count) + " " + hint
        self.exclusion_hint.setText(hint)

    def retranslate_ui(self):
        tr = self.panel._t
        for control, key, fallback in (
            (self.load_button, "load_menu", "Load products"), (self.load_excel, "load_excel", "Excel…"),
            (self.browse, "load_folder", "Saved folder…"), (self.reload, "reload", "Reload current source"),
            (self.add_product, "manual.add", "Add product"), (self.edit_product, "manual.edit", "Edit product"),
            (self.select_button, "selection", "Selection"), (self.select_all, "select_visible", "Select visible"),
            (self.clear, "clear_visible", "Clear visible"), (self.scan_photos, "photo_scan.scan", "Scan Pimbo photos"),
            (self.scan_content, "content_scan.scan", "Scan missing data"),
            (self.model_label, "model", "Model"),
            (self.exclusion_label, "prefix_selection.label", "Include / exclude by code prefix"),
            (self.include_button, "include.apply", "Include codes"),
            (self.exclude_button, "exclude.apply", "Exclude codes"),
        ):
            control.setText(tr(key, fallback))
        self.select_status.retranslate_ui(tr, checked=True)
        self.unselect_status.retranslate_ui(tr, checked=False)
        self.model_filter.setToolTip(tr("model.tip", "Actions apply only to checked products currently shown."))
        self.edit_product.setToolTip(tr("manual.edit_tip", "Select a row to correct its product name or Orbea link."))
        self.exclude_prefixes.setPlaceholderText(tr("exclude.placeholder", "e.g. U9, U3 or a full SKU"))
        self.refresh_exclusion_hint()
        self.scan_content.setToolTip(tr("content_scan.tip", "Checks required attributes except Ratų dydis/Spalva, and all Bendra informacija specifications. Reports empty fields without editing Pimbo."))


class _WorkflowPanel(CardWidget):
    """Build each card in its final layout; the controller locks explicit inputs."""
    def __init__(self, screen):
        super().__init__(screen)
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(*CARD_MARGINS)
        self.box.setSpacing(CARD_SPACING)


class SourcePanel(_WorkflowPanel):
    def __init__(self, screen):
        super().__init__(screen)
        card, layout = self, self.box
        screen._paths_title = BodyLabel("")
        screen._paths_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(screen._paths_title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(CARD_SPACING)
        grid.setVerticalSpacing(ROW_SPACING)
        grid.setColumnStretch(1, 1)

        screen._catalogue_label = BodyLabel("")
        screen._catalogue_edit = LineEdit()
        screen._catalogue_edit.setClearButtonEnabled(True)
        screen._catalogue_edit.editingFinished.connect(screen._paths_changed)
        screen._catalogue_btn = PushButton(FluentIcon.DOCUMENT, "")
        screen._catalogue_btn.clicked.connect(screen._browse_catalogue)

        screen._output_label = BodyLabel("")
        screen._output_edit = LineEdit()
        screen._output_edit.setClearButtonEnabled(True)
        screen._output_edit.editingFinished.connect(screen._paths_changed)
        screen._output_btn = PushButton(FluentIcon.FOLDER, "")
        screen._output_btn.clicked.connect(screen._browse_output)
        grid.addWidget(screen._catalogue_label, 0, 0)
        grid.addWidget(screen._catalogue_edit, 0, 1)
        grid.addWidget(screen._catalogue_btn, 0, 2)
        grid.addWidget(screen._output_label, 1, 0)
        grid.addWidget(screen._output_edit, 1, 1)
        grid.addWidget(screen._output_btn, 1, 2)

        # The Pimbo query is intentionally fixed and is not an actionable
        # setting, so retain it for configuration/tests without spending a
        # full visible form row on a disabled control.
        screen._search_label = BodyLabel("", card)
        screen._search_edit = LineEdit(card)
        screen._search_edit.setText("orbea")
        screen._search_edit.setReadOnly(True)
        screen._search_edit.setEnabled(False)
        screen._search_label.setVisible(False)
        screen._search_edit.setVisible(False)
        layout.addLayout(grid)

        screen._downloads_label = BodyLabel("")
        layout.addWidget(screen._downloads_label)
        download_options = FlowLayout()
        download_options.setHorizontalSpacing(CARD_SPACING)
        download_options.setVerticalSpacing(ROW_SPACING)
        screen._table_images_check = CheckBox("")
        screen._table_images_check.setChecked(True)
        screen._table_images_check.stateChanged.connect(
            screen._download_options_changed
        )
        screen._product_photos_check = CheckBox("")
        screen._product_photos_check.setChecked(True)
        screen._product_photos_check.stateChanged.connect(
            screen._download_options_changed
        )
        download_options.addWidget(screen._table_images_check)
        download_options.addWidget(screen._product_photos_check)
        screen._description_check = CheckBox("")
        screen._specifications_check = CheckBox("")
        for checkbox in (screen._description_check, screen._specifications_check):
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(screen._download_options_changed)
            download_options.addWidget(checkbox)
        layout.addLayout(download_options)
        from .browser_pool import BrowserCountControl
        self.browsers = BrowserCountControl(screen, self, downloads=True)
        screen._download_browsers = self.browsers
        layout.addWidget(self.browsers)
        screen._config_widgets.append(self.browsers.combo)
        screen._downloads_hint = CaptionLabel("")
        screen._downloads_hint.setWordWrap(True)
        screen._downloads_hint.setStyleSheet(
            f"color: {get_text_color(isDarkTheme(), 'secondary')};"
        )
        layout.addWidget(screen._downloads_hint)

        screen._config_widgets.extend([
            screen._catalogue_edit,
            screen._catalogue_btn,
            screen._output_edit,
            screen._output_btn,
            screen._table_images_check,
            screen._product_photos_check,
            screen._description_check,
            screen._specifications_check,
        ])


class FilterPanel(_WorkflowPanel):
    def __init__(self, screen):
        super().__init__(screen)
        card, layout = self, self.box
        top = QHBoxLayout()
        screen._filters_title = BodyLabel("")
        screen._filters_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        screen._filter_state_label = CaptionLabel("")
        screen._filter_state_label.setStyleSheet(f"color: {get_text_color(isDarkTheme(), 'secondary')};")
        screen._refresh_btn = PushButton(FluentIcon.SYNC, "")
        screen._refresh_btn.clicked.connect(screen.refresh_filter_options)
        top.addWidget(screen._filters_title)
        top.addWidget(screen._filter_state_label, 1)
        top.addWidget(screen._refresh_btn)
        layout.addLayout(top)

        screen._status_label = BodyLabel("")
        status_field = QWidget()
        status_box = QVBoxLayout(status_field)
        status_box.setContentsMargins(0, 0, 0, 0)
        status_box.setSpacing(4)
        status_box.addWidget(screen._status_label)
        screen._status_layout = FlowLayout()
        screen._status_layout.setHorizontalSpacing(ROW_SPACING)
        screen._status_layout.setVerticalSpacing(ROW_SPACING)
        status_box.addLayout(screen._status_layout)

        grid = QGridLayout()
        grid.setHorizontalSpacing(CARD_SPACING)
        grid.setVerticalSpacing(ROW_SPACING)
        screen._family_combo = ComboBox()
        screen._category_combo = ComboBox()
        screen._source_combo = ComboBox()
        screen._locale_combo = ComboBox()
        screen._sort_combo = ComboBox()
        screen._code_prefix_edit = LineEdit()
        screen._code_prefix_edit.setClearButtonEnabled(True)
        screen._family_field, screen._family_label = self._combo_field(screen._family_combo)
        screen._category_field, screen._category_label = self._combo_field(screen._category_combo)
        screen._source_field, screen._source_label = self._combo_field(screen._source_combo)
        screen._locale_field, screen._locale_label = self._combo_field(screen._locale_combo)
        screen._sort_field, screen._sort_label = self._combo_field(screen._sort_combo)
        screen._code_prefix_field, screen._code_prefix_label = self._combo_field(screen._code_prefix_edit)
        screen._code_prefix_label.setBuddy(screen._code_prefix_edit)
        grid.addWidget(screen._family_field, 0, 0)
        grid.addWidget(screen._category_field, 0, 1)
        grid.addWidget(screen._source_field, 0, 2)
        grid.addWidget(screen._locale_field, 1, 0)
        grid.addWidget(screen._sort_field, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        layout.addWidget(screen._code_prefix_field)

        screen._stock_label = BodyLabel("")
        stock_field = QWidget()
        stock_box = QVBoxLayout(stock_field)
        stock_box.setContentsMargins(0, 0, 0, 0)
        stock_box.setSpacing(4)
        stock_box.addWidget(screen._stock_label)
        screen._stock_layout = FlowLayout()
        screen._stock_layout.setHorizontalSpacing(ROW_SPACING)
        screen._stock_layout.setVerticalSpacing(ROW_SPACING)
        stock_box.addLayout(screen._stock_layout)
        basic = QGridLayout()
        basic.addWidget(status_field, 0, 0)
        basic.addWidget(stock_field, 0, 1)
        basic.setColumnStretch(0, 1)
        basic.setColumnStretch(1, 1)
        layout.addLayout(basic)

        screen._more_filters = OrbeaDisclosure(screen)
        layout.addWidget(screen._more_filters)
        screen._more_filters.body_layout.addLayout(grid)

        screen._bucket_label = BodyLabel("")
        screen._more_filters.body_layout.addWidget(screen._bucket_label)
        screen._bucket_layout = FlowLayout()
        screen._bucket_layout.setHorizontalSpacing(ROW_SPACING)
        screen._bucket_layout.setVerticalSpacing(ROW_SPACING)
        screen._more_filters.body_layout.addLayout(screen._bucket_layout)
        combos = [
            screen._family_combo,
            screen._category_combo,
            screen._source_combo,
            screen._locale_combo,
            screen._sort_combo,
        ]
        for combo in combos:
            combo.currentIndexChanged.connect(screen._filter_changed)
        screen._code_prefix_edit.textChanged.connect(screen._filter_changed)
        screen._config_widgets.extend([screen._refresh_btn, *combos, screen._code_prefix_edit])


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


class ActionPanel(_WorkflowPanel):
    def __init__(self, screen):
        super().__init__(screen)
        card, layout = self, self.box
        screen._actions_title = BodyLabel("")
        screen._actions_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(screen._actions_title)
        screen._start_btn = PrimaryPushButton(FluentIcon.SEARCH, "")
        screen._start_btn.setObjectName("orbeaPrimaryAction")
        screen._start_btn.clicked.connect(screen._on_start_stop)
        screen._resume_btn = PushButton(FluentIcon.UPDATE, "")
        screen._resume_btn.clicked.connect(screen._resume_interrupted_run)
        screen._resume_hint = CaptionLabel("")
        screen._resume_hint.setWordWrap(True)
        screen._download_mode = ComboBox()
        screen._download_mode.currentIndexChanged.connect(screen._update_action_states)
        screen._download_btn = PrimaryPushButton(FluentIcon.DOWNLOAD, "")
        screen._download_btn.clicked.connect(screen._download_selected)
        screen._download_summary = CaptionLabel("")
        screen._download_summary.setWordWrap(True)
        for widget in (screen._start_btn, screen._resume_btn, screen._resume_hint,
                       screen._download_mode, screen._download_summary, screen._download_btn):
            layout.addWidget(widget)
        for button in (screen._start_btn, screen._resume_btn, screen._download_btn):
            button.setMinimumHeight(38)
        screen._config_widgets.append(screen._download_mode)
        screen._open_excel_btn = PushButton(FluentIcon.DOCUMENT, "")
        screen._open_excel_btn.setEnabled(False)
        screen._open_excel_btn.clicked.connect(screen._open_excel)
        screen._open_folder_btn = PushButton(FluentIcon.FOLDER, "")
        screen._open_folder_btn.setEnabled(False)
        screen._open_folder_btn.clicked.connect(screen._open_folder)
        screen._excel_sort_btn = PushButton(FluentIcon.DOCUMENT, "")
        screen._excel_sort_btn.clicked.connect(screen._sort_existing_excel)
        screen._config_widgets.append(screen._excel_sort_btn)


class ProgressPanel(_WorkflowPanel):
    def __init__(self, screen):
        super().__init__(screen)
        card, layout = self, self.box
        screen._collection_progress_card = card
        card.setVisible(False)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        status_row = QHBoxLayout()
        screen._stage_label = BodyLabel("")
        screen._stage_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        screen._eta_label = CaptionLabel("")
        screen._eta_label.setStyleSheet(f"color: {get_text_color(isDarkTheme(), 'secondary')};")
        screen._progress_stop_btn = PushButton(FluentIcon.CLOSE, "")
        screen._progress_stop_btn.setObjectName("orbeaDangerAction")
        screen._progress_stop_btn.clicked.connect(screen.workflow_controller.request_stop)
        screen._progress_stop_btn.setVisible(False)
        status_row.addWidget(screen._stage_label, 1)
        status_row.addWidget(screen._eta_label)
        status_row.addWidget(screen._progress_stop_btn)
        layout.addLayout(status_row)
        screen._progress = ProgressBar()
        screen._progress.setRange(0, 100)
        screen._progress.setValue(0)
        layout.addWidget(screen._progress)
        screen._progress_label = CaptionLabel("")
        screen._progress_label.setWordWrap(True)
        screen._progress_label.setStyleSheet(f"color: {get_text_color(isDarkTheme(), 'secondary')};")
        layout.addWidget(screen._progress_label)

        stats = QGridLayout()
        stats.setHorizontalSpacing(CARD_SPACING)
        stats.setVerticalSpacing(ROW_SPACING)
        screen._stat_values: dict[str, BodyLabel] = {}
        screen._stat_labels: dict[str, CaptionLabel] = {}
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
            screen._stat_labels[key] = label
            screen._stat_values[key] = value
        screen._collection_details = OrbeaDisclosure(screen)
        layout.addWidget(screen._collection_details)
        screen._collection_details.body_layout.addLayout(stats)

        screen._log = PlainTextEdit()
        screen._log.setReadOnly(True)
        screen._log.setFixedHeight(140)
        screen._collection_details.body_layout.addWidget(screen._log)

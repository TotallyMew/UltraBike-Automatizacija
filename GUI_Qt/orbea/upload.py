"""Collected Orbea products and the selectable PIMBO editing workflow."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from Utilities.UploadResultsReport import result_record, upload_result_row, write_upload_results

from PySide6.QtCore import QEvent, QPointF, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFileDialog, QHeaderView, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CaptionLabel, CheckBox, ComboBox, FlowLayout, LineEdit, PlainTextEdit, PrimaryPushButton, PushButton, isDarkTheme

from GUI_Qt.kross.workers import KrossUploadWorker
from GUI_Qt.orbea.tabs import OrbeaDisclosure
from GUI_Qt.orbea.panels import ProductToolbar, translate_choices
from tools.orbea_automation.selected_downloads import product_identity, resolve_product_rows
from GUI_Qt.styles.theme_config import get_accent_colors, get_text_color
from tools.orbea_automation.upload import OrbeaUploadService, OrbeaWorkflowOptions, OrbeaUploadResult
from tools.orbea_automation.table_packages import geometry_needs_recollection
from tools.orbea_automation.photo_scan import PHOTO_STATUSES, photo_scan_matches, saved_product_rows, record_uploaded_photos
from GUI_Qt.orbea.photo_scan_workflow import OrbeaPhotoScanWorkflow


class OrbeaUploadWorker(KrossUploadWorker):
    completed = Signal(object)
    options_type = OrbeaWorkflowOptions
    result_type = OrbeaUploadResult

    def __init__(self, *args, retry_unfinished=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.retry_unfinished = retry_unfinished
        if retry_unfinished:
            self.matches = tuple(match for match in self.matches if not OrbeaUploadService.upload_finished(match))

    def _upload_one(self, service, match):
        if self.retry_unfinished:
            return service.upload_and_save(match, self.output_root, options=self.options,
                                           progress=self.progress_changed.emit, resume_completed=True)
        return super()._upload_one(service, match)

    def _emit_completed(self):
        ok = sum(result.succeeded for result in self.results)
        failed = len(self.results) - ok
        warnings = sum(bool(result.preparation.warnings) for result in self.results)
        pending = len(self.matches) - len(self.results)
        status = ("cancelled" if self._stop_requested and pending else
                  "failed" if self._batch_error or (not ok and (failed or pending)) else
                  "partial" if failed or warnings or pending else "succeeded")
        self.completed.emit({"status": status, "succeeded": ok, "failed": failed,
            "warnings": warnings, "unprocessed": pending,
            "error": self._batch_error or " | ".join(result.preparation.error for result in self.results if result.preparation.error),
            "output_path": str(self.output_root or (self.matches[0].local_folder if self.matches else ""))})


STAGE_LABELS = {
    "product_photos": "Upload product photos",
    "photo_order": "Arrange photos: side → front → back",
    "size_tables": "Upload size table",
    "geometry": "Upload geometry",
    "description_source": "Paste Orbea description",
    "description_magic_ai": "MagicAI description",
    "product_family": "Set family: Dviračiai",
    "brand": "Set brand: Orbea",
    "category_magic_ai": "MagicAI category",
    "translations": "Translate LT → EN / LV / EE",
    "save": "Save Draft product",
    "specifications_prefill": "Fill model, colour and frame sizes",
    "specifications_magic_ai": "MagicAI specifications",
}


class _ProductSelectionDelegate(QStyledItemDelegate):
    """Draw a larger centred checkbox and use its entire cell as the hit target."""
    def paint(self, painter, option, index):
        cell = QStyleOptionViewItem(option)
        self.initStyleOption(cell, index)
        cell.features &= ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        style = cell.widget.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, cell, painter, cell.widget)
        rect = QRect(0, 0, 24, 24)
        rect.moveCenter(cell.rect.center())
        checked = index.data(Qt.ItemDataRole.CheckStateRole) in (Qt.CheckState.Checked, Qt.CheckState.Checked.value)
        enabled = bool(index.flags() & Qt.ItemFlag.ItemIsUserCheckable and index.flags() & Qt.ItemFlag.ItemIsEnabled)
        accent = get_accent_colors(isDarkTheme())
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not enabled:
            painter.setOpacity(0.45)
        painter.setPen(QPen(QColor(accent["base"] if checked else get_text_color(isDarkTheme(), "secondary")), 1.5))
        painter.setBrush(QColor(accent["base"]) if checked else Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 4, 4)
        if checked:
            mark = QPainterPath(QPointF(rect.left() + 6, rect.top() + 12))
            mark.lineTo(rect.left() + 10, rect.top() + 16)
            mark.lineTo(rect.left() + 18, rect.top() + 8)
            painter.setPen(QPen(QColor(accent["text"]), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(mark)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if not index.flags() & Qt.ItemFlag.ItemIsUserCheckable or not index.flags() & Qt.ItemFlag.ItemIsEnabled:
            return False
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            return event.button() == Qt.MouseButton.LeftButton
        mouse = event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton
        key = event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Select)
        if mouse or key:
            checked = index.data(Qt.ItemDataRole.CheckStateRole) in (Qt.CheckState.Checked, Qt.CheckState.Checked.value)
            state = Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked
            return model.setData(index, state.value, Qt.ItemDataRole.CheckStateRole)
        return False


def _product_model(match):
    name = match.orbea_product_name or match.pimbo_product_name
    name = re.sub(r"^\s*Orbea\b[\s:-]*", "", name, flags=re.I).strip()
    return name.split()[0].strip("/:-").upper() if name else ""


class OrbeaUploadPanel(QWidget):
    def __init__(self, screen, service_factory=None, *, products_layout=None):
        super().__init__(screen)
        self.screen = screen
        self.service_factory = service_factory or (lambda: OrbeaUploadService(screen.main.driver))
        self.worker = None
        self.matches = ()
        self.results = []
        self._busy = False
        self._operation_id = None
        self._config = []
        self._finished_uploads = {}
        self._row_statuses = {}
        self._photo_statuses = {}
        self._selection_locked = None
        self.photo_scan = OrbeaPhotoScanWorkflow(self)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        self.products_card, layout = screen._card()
        self.products_card.setObjectName("orbeaSelectProductsCard")
        (products_layout or root).addWidget(self.products_card)
        self.title = BodyLabel(self)
        self.title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.hint = CaptionLabel(self)
        self.hint.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.hint)
        self.folder = LineEdit(self)
        self.folder.setText(str(screen._setting_get("orbea_upload_root", "") or ""))
        self.folder.hide()
        self.toolbar = ProductToolbar(self)
        layout.addWidget(self.toolbar)
        self.model_label = self.toolbar.model_label
        self.model_filter = self.toolbar.model_filter
        self.scan_photos = self.toolbar.scan_photos
        self.select_all = self.toolbar.select_all
        self.clear = self.toolbar.clear
        self._config.extend((self.toolbar.load_button, self.toolbar.select_button,
                             self.model_filter, self.scan_photos))
        self.selection_summary = CaptionLabel(self)
        self.selection_summary.setWordWrap(True)
        layout.addWidget(self.selection_summary)
        self.source_label = CaptionLabel(self)
        self.source_label.setWordWrap(True)
        self.source_label.hide()
        layout.addWidget(self.source_label)
        self.empty_hint = CaptionLabel(self)
        self.empty_hint.setWordWrap(True)
        layout.addWidget(self.empty_hint)
        self.table = QTableWidget(0, 6, self)
        self.table.setMinimumHeight(500)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.verticalHeader().setMinimumSectionSize(46)
        self.table.horizontalHeader().setMinimumHeight(46)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setItemDelegateForColumn(0, _ProductSelectionDelegate(self.table))
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 80)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)
        self.table.hide()

        self.steps_card, layout = screen._card()
        self.steps_card.setObjectName("orbeaUpdatePimboCard")
        root.addWidget(self.steps_card)
        self.steps_title = BodyLabel(self)
        self.steps_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.steps_hint = CaptionLabel(self)
        self.steps_hint.setWordWrap(True)
        layout.addWidget(self.steps_title)
        layout.addWidget(self.steps_hint)
        row = FlowLayout()
        layout.addLayout(row)
        self.all_steps = PushButton(self.steps_card)
        self.clear_steps = PushButton(self.steps_card)
        row.addWidget(self.all_steps)
        row.addWidget(self.clear_steps)
        self._config.extend((self.all_steps, self.clear_steps))
        self.checks = {}
        try:
            stored = screen._setting_get("orbea_workflow_options", {})
            stored = json.loads(stored) if isinstance(stored, str) else stored
            stored = stored if isinstance(stored, dict) else {}
        except (ValueError, TypeError):
            stored = {}
        ui_stages = tuple(stage for stage in OrbeaWorkflowOptions.STAGES if stage != "save") + ("save",)
        for index, stage in enumerate(ui_stages):
            check = CheckBox(self)
            value = stored.get(stage, getattr(OrbeaWorkflowOptions(), stage))
            check.setChecked(value if isinstance(value, bool) else str(value).casefold() in {"true", "1", "yes"})
            check.stateChanged.connect(self._options_changed)
            self.checks[stage] = check
        from GUI_Qt.widgets.workspace import grouped_stages
        layout.addWidget(grouped_stages(screen.main, self.checks))
        self._config.extend(self.checks.values())
        self.upload_mode = ComboBox(self)
        self.upload_mode.currentIndexChanged.connect(self.update_state)
        layout.addWidget(self.upload_mode)
        self._config.append(self.upload_mode)
        self.start = PrimaryPushButton(self)
        self.start.setMinimumHeight(38)
        layout.addWidget(self.start)
        self.stop = PushButton(self)
        layout.addWidget(self.stop)
        self.export_results = PushButton(self)
        self.export_results.clicked.connect(self._export_results)
        layout.addWidget(self.export_results)
        self.status = CaptionLabel(self)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.details = OrbeaDisclosure(self)
        layout.addWidget(self.details)
        self.log = PlainTextEdit(self)
        self.log.setReadOnly(True)
        self.log.setFixedHeight(140)
        self.log.setMaximumBlockCount(2500)
        self.details.body_layout.addWidget(self.log)
        self.all_steps.clicked.connect(lambda: self._select_steps(True))
        self.clear_steps.clicked.connect(lambda: self._select_steps(False))
        self.table.itemChanged.connect(self.update_state)
        self.start.clicked.connect(lambda: self.start_upload(retry_unfinished=self.upload_mode.currentData() == "retry"))
        self.stop.clicked.connect(self.request_stop)
        self.retranslate_ui()
        self.update_state()

    def _t(self, key, fallback, **kwargs):
        return self.screen._t(f"orbea.upload.{key}", fallback, **kwargs)

    def _status_text(self, status):
        fallback = {'geometry_outdated': 'Geometry needs updating',
                    'tables_pending': 'New tables need uploading'}.get(status, status.replace("_", " ").capitalize())
        return self._t(f"status.{status}", fallback)

    def _photo_status_text(self, state):
        status = state.get("status", "not_checked")
        text = self._t(f"photo_scan.status.{status}", PHOTO_STATUSES.get(status, status))
        return f"{text} ({state.get('photos', 0)})" if status == "has_photos" else text

    def retranslate_ui(self):
        self.title.setText(self._t("title", "2. Choose products"))
        self.hint.setText(self._t("hint", "Load or scan products, then check the rows to process. Actions use only checked products currently shown."))
        self.steps_title.setText(self._t("steps_title", "3. Update Pimbo"))
        self.steps_hint.setText(self._t("steps_hint", "Choose what to update, then upload. Only Draft products are edited. Geometry and size tables replace previous images and save automatically."))
        self.empty_hint.setText(self._t("empty", "Collect data above, or load products from a saved folder."))
        self.details.set_title(self._t("log", "Upload details and log"))
        self.folder.setPlaceholderText(self._t("folder", "Collected run or product folder"))
        self.toolbar.retranslate_ui()
        for button, key, fallback in (
            (self.start, "start_selected", "Upload selected"),
            (self.stop, "stop", "Stop after current product"),
            (self.export_results, "export_results", "Export upload results to Excel"),
            (self.all_steps, "all_steps", "Select all steps"), (self.clear_steps, "clear_steps", "Clear steps"),
        ):
            button.setText(self._t(key, fallback))
        translate_choices(self.upload_mode, (
            ("normal", "mode.normal", "Run selected steps"),
            ("retry", "mode.retry", "Retry unfinished steps"),
        ), self._t)
        self._populate_models()
        self.table.setHorizontalHeaderLabels([self._t(key, label) for key, label in (
            ("selected", "Select"), ("sku", "SKU"), ("product", "Product"), ("status", "Status"), ("details", "Details"), ("photo_scan.column", "Pimbo photos"))])
        for stage, check in self.checks.items():
            check.setText(self._t(f"stage.{stage}", STAGE_LABELS[stage]))

    def options(self):
        return OrbeaWorkflowOptions(**{stage: check.isChecked() for stage, check in self.checks.items()})

    def _options_changed(self):
        self._sync_table_save()
        self.screen._setting_set("orbea_workflow_options", json.dumps({stage: check.isChecked() for stage, check in self.checks.items()}))
        self.update_state()

    def _sync_table_save(self, locked=False):
        required = self.checks["geometry"].isChecked() or self.checks["size_tables"].isChecked()
        check = self.checks["save"]
        if required:
            check.blockSignals(True)
            check.setChecked(True)
            check.blockSignals(False)
        check.setEnabled(not locked and not required)
        check.setToolTip(self._t("table_save_required", "Table uploads always save automatically after uploading and verification.") if required else "")

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, self._t("folder", "Collected run or product folder"), self.folder.text())
        if folder:
            self.load_packages(folder)

    def _load_saved(self):
        self._load_current()

    def clear_products(self):
        self._finished_uploads = {}
        self._photo_statuses = {}
        self.matches = ()
        self.results = []
        self.table.setRowCount(0)
        self._populate_models()
        self.table.hide()
        self.empty_hint.show()
        self.source_label.hide()
        self.status.clear()
        self.update_state()

    def _load_current(self):
        root = self.screen.workflow_controller.source_root
        if root:
            self.load_packages(root, preserve_selection=True)

    def load_packages(self, root, *, preserve_selection=False, internal=False):
        if (self.screen.is_running() and not internal) or self.is_running() or not root:
            return
        path = Path(root)
        if not path.is_dir():
            self.screen._warn(self._t("title", "Pimbo workflow"), self._t("invalid_folder", "Choose a folder containing collected Orbea products."))
            return
        previous = self.screen.workflow_controller.remember_selection(self) if preserve_selection else {}
        try:
            matches = photo_scan_matches(path, OrbeaUploadService.load_local_packages(path))
            scan_rows = {(str(run / "run_checkpoint.json"), row["row_key"]): row
                         for run, row in saved_product_rows(path)}
        except (OSError, ValueError) as error:
            self.screen._error(self._t("title", "Pimbo workflow"), str(error))
            return
        self.matches = matches
        self.screen.workflow_controller.set_source(path)
        self.folder.setText(str(path))
        self.source_label.setText(str(path))
        self.source_label.show()
        self.screen._setting_set("orbea_upload_root", str(path))
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.matches))
        self._finished_uploads = {}
        self._row_statuses = {}
        self._photo_statuses = {}
        self._selection_locked = None
        for row, match in enumerate(self.matches):
            selection = QTableWidgetItem()
            selectable = bool(match.sku and match.status != "invalid")
            selection.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled if selectable else Qt.ItemFlag.NoItemFlags)
            finished = OrbeaUploadService.upload_finished(match) if match.ready else False
            self._finished_uploads[match.local_folder] = finished
            default = Qt.CheckState.Checked if selectable and not finished else Qt.CheckState.Unchecked
            selection.setCheckState(previous.get(product_identity(match), default if not preserve_selection else Qt.CheckState.Unchecked))
            self.table.setItem(row, 0, selection)
            prior = OrbeaUploadService.read_upload_result(match) if match.ready else None
            preparation = prior["preparation"] if prior else {}
            detail = " | ".join(filter(None, (match.note, preparation.get("error"), *preparation.get("warnings", []))))
            status = preparation.get("status") or match.status
            outdated_geometry = geometry_needs_recollection(Path(match.local_folder)) if match.ready else False
            pending_tables = OrbeaUploadService.pending_table_upload_stages(match) if match.ready else ()
            pending_saved_tables = bool(pending_tables and preparation.get('status') in {'saved_automatically', 'no_changes'})
            if pending_saved_tables:
                status = 'tables_pending'
                detail = ' | '.join(filter(None, (self._t('tables_pending_hint', 'Local table files need a verified upload. Upload Geometry or Size tables to replace the current Pimbo images.'), detail)))
            if outdated_geometry:
                status = "geometry_outdated"
                detail = " | ".join(filter(None, (self._t("geometry_recollect_hint", "Download the tables again to replace the old plain geometry layout."), detail)))
            self._row_statuses[match.local_folder] = {
                "status": "unprocessed" if outdated_geometry or pending_saved_tables else preparation.get("status") or ("unprocessed" if match.ready else "not_ready"),
                "warnings": bool(preparation.get("warnings")),
            }
            for column, value in enumerate((match.sku, match.pimbo_product_name or match.orbea_product_name, self._status_text(status), detail), start=1):
                item = QTableWidgetItem(value)
                item.setToolTip(f"{match.local_folder}\n{match.note}")
                self.table.setItem(row, column, item)
            state = scan_rows.get(product_identity(match), {}).get("pimbo_photo_scan", {})
            self._photo_statuses[match.local_folder] = state
            item = QTableWidgetItem(self._photo_status_text(state))
            item.setToolTip(state.get("error", ""))
            self.table.setItem(row, 5, item)
        self.table.blockSignals(False)
        self._populate_models()
        self.table.setVisible(bool(self.matches))
        self.empty_hint.setVisible(not self.matches)
        self.results = []
        self._report_batch_error = ""
        self.status.setText(self._t("loaded", "{count} saved product(s) loaded", count=len(self.matches)))
        self.update_state()

    def _export_results(self):
        path, _ = QFileDialog.getSaveFileName(self, self._t("export_results", "Export upload results to Excel"),
                                             str(Path(self.folder.text()) / "orbea-upload-results.xlsx"), "Excel (*.xlsx)")
        if not path:
            return
        current = {result.match.local_folder: result_record(result) for result in self.results}
        try:
            rows = [upload_result_row(match, current.get(match.local_folder) or OrbeaUploadService.read_upload_result(match), brand="Orbea") for match in self.matches]
            write_upload_results(path, rows, context={"Collection folder": self.folder.text(),
                "Batch stop reason": getattr(self, "_report_batch_error", "")})
            self.status.setText(self._t("export_saved", "Upload results exported to {path}", path=path))
        except Exception as error:
            self.screen._error(self._t("export_results", "Export upload results to Excel"), str(error))

    def _select(self, checked):
        self.screen.workflow_controller.select_visible(self, checked=checked)

    def _select_by_status(self, wanted):
        self.screen.workflow_controller.select_visible(self, status=wanted)

    def retry_unfinished_uploads(self):
        self.start_upload(retry_unfinished=True)

    def _select_steps(self, checked):
        for check in self.checks.values():
            check.setChecked(checked)

    def _populate_models(self):
        previous = self.model_filter.currentData()
        counts = Counter(_product_model(match) for match in self.matches)
        self.model_filter.blockSignals(True)
        self.model_filter.clear()
        self.model_filter.addItem(self._t("all_models", "All models"), userData="")
        for model, count in sorted(counts.items()):
            self.model_filter.addItem(f"{model or self._t('other_models', 'Other models')} ({count})", userData=model or "__other__")
        self.model_filter.setCurrentIndex(max(0, self.model_filter.findData(previous)))
        self.model_filter.blockSignals(False)
        self._apply_model_filter()

    def _apply_model_filter(self, *_args):
        wanted = self.model_filter.currentData()
        for row, match in enumerate(self.matches):
            model = _product_model(match) or "__other__"
            self.table.setRowHidden(row, bool(wanted and model != wanted))
        self.update_state()

    def _visible_rows(self):
        return ((row, match) for row, match in enumerate(self.matches) if not self.table.isRowHidden(row))

    def selected_matches(self):
        return self.screen.workflow_controller.selected_products(self, ready_only=True)

    def selected_products(self):
        return self.screen.workflow_controller.selected_products(self)

    def is_running(self):
        return self._busy or bool(self.worker and self.worker.isRunning())

    def _selected_photos_available(self, matches=None):
        if not self.options().product_photos:
            return True
        for match in (self.selected_products() if matches is None else matches):
            if self._photo_statuses.get(match.local_folder, {}).get("status") == "no_photos":
                try:
                    if not OrbeaUploadService.local_photo_candidates(match.local_folder):
                        return False
                except (OSError, ValueError, RuntimeError):
                    return False
        return True

    def set_locked(self, locked):
        for widget in self._config:
            widget.setEnabled(not locked)
        self._sync_table_save(locked)
        self.select_all.setEnabled(not locked and bool(self.matches))
        self.clear.setEnabled(not locked and bool(self.matches))
        for action in self.toolbar.status_actions.values():
            action.setEnabled(not locked and bool(self.matches))
        if locked != self._selection_locked:
            self._selection_locked = locked
            self.table.blockSignals(True)
            for row, match in enumerate(self.matches):
                flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                if match.sku and match.status != "invalid" and not locked:
                    flags |= Qt.ItemFlag.ItemIsUserCheckable
                self.table.item(row, 0).setFlags(flags)
            self.table.blockSignals(False)

    def update_state(self, *_args):
        activity = self.screen.workflow_controller.activity()
        locked = activity.name != "idle"
        self.set_locked(locked)
        products = self.selected_products()
        matches = self.selected_matches()
        retry = self.upload_mode.currentData() == "retry"
        targets = tuple(match for match in matches if not self._finished_uploads.get(match.local_folder, False)) if retry else matches
        self.start.setEnabled(bool(not locked and getattr(self.screen.main, "driver", None) is not None
                                   and targets and len(matches) == len(products) and self.options().any_selected
                                   and (len(targets) == 1 or self.options().allows_multiple_products)
                                   and self._selected_photos_available(targets)))
        try:
            can_scan = bool(products and resolve_product_rows(products)) if not locked else False
        except (OSError, ValueError, KeyError, TypeError):
            can_scan = False
        self.scan_photos.setEnabled(bool(not locked and can_scan and getattr(self.screen.main, "driver", None) is not None))
        self.toolbar.reload.setEnabled(not locked and self.screen.workflow_controller.source_root is not None)
        self.toolbar.select_button.setEnabled(not locked and bool(self.matches))
        self.export_results.setEnabled(bool(self.matches) and not locked)
        self.stop.setEnabled(self.is_running() and not activity.stopping)
        self.stop.setVisible(self.is_running())
        for widget in (self.model_label, self.model_filter, self.selection_summary):
            widget.setVisible(bool(self.matches))
        visible = sum(1 for _ in self._visible_rows())
        self.selection_summary.setText(self._t("selection_summary", "Showing {visible} of {total} products · {selected} selected",
            visible=visible, total=len(self.matches), selected=len(products)))
        if hasattr(self.screen, "_download_mode"):
            self.screen._update_download_state(locked)

    def start_upload(self, *, retry_unfinished=False):
        if self.screen.is_running():
            return
        selected, options = self.selected_matches(), self.options()
        matches = tuple(match for match in selected if not OrbeaUploadService.upload_finished(match)) if retry_unfinished else selected
        if len(selected) != len(self.selected_products()) or not self._selected_photos_available(matches):
            self.screen._warn(self._t("title", "Pimbo workflow"),
                              self._t("photo_scan.collect_first", "Download photos for the selected products before uploading."))
            return
        if not matches or not options.any_selected or getattr(self.screen.main, "driver", None) is None:
            return
        if len(matches) > 1 and not options.allows_multiple_products:
            self.screen._warn(self._t("title", "Pimbo workflow"), self._t("single_unsaved", "Without Save, select only one product when changing product details. Photos-only runs can include multiple products."))
            return
        if options.geometry:
            try:
                stale_count = sum(geometry_needs_recollection(Path(match.local_folder)) for match in matches)
            except (OSError, ValueError) as error:
                self.screen._warn(self._t("title", "Pimbo workflow"), str(error))
                return
            if stale_count:
                message = self._t("geometry_recollect", "{count} selected product(s) still have the old plain geometry layout. Choose Missing or failed data with Geometry + CM size tables, then upload the refreshed tables.", count=stale_count)
                self.status.setText(message)
                self.screen._warn(self._t("title", "Pimbo workflow"), message)
                return
        if options.specifications_magic_ai:
            try:
                stale_count = sum(OrbeaUploadService.specifications_need_recollection(match) for match in matches)
            except (OSError, ValueError) as error:
                self.screen._warn(self._t("title", "Pimbo workflow"), str(error))
                return
            if stale_count:
                message = self._t("specifications_recollect", "{count} selected product(s) have specifications from the old incomplete scrape. Choose Refresh selected data with Specifications to recollect them.", count=stale_count)
                self.status.setText(message)
                self.screen._warn(self._t("title", "Pimbo workflow"), message)
                return
        if not self.screen._acquire_browser():
            return
        self.results = []
        self._report_batch_error = ""
        self.log.clear()
        self._busy = True
        self.status.setText(self._t("running", "Running selected steps…"))
        self.screen.workflow_controller.start_job("upload",
            lambda: OrbeaUploadWorker(self.service_factory, matches, None, options, retry_unfinished=retry_unfinished),
            owner=self, attribute="worker", operation_attribute="_operation_id", kind="upload",
            details={"output_path": self.folder.text()},
            signals={"progress_changed": self._on_progress, "item_finished": self._item_finished,
                     "failed": self._failed, "completed": self._finish_activity},
            finished=self._finished, failed=self._failed)

    def _on_progress(self, message):
        self.log.appendPlainText(message)
        if self.worker._stop_requested:
            message = self._t("stopping", "Stopping after the current product…") + " " + message
        self.status.setText(message)

    def _item_finished(self, result):
        self.results.append(result)
        preparation = result.preparation
        try:
            photo_state = record_uploaded_photos(result)
        except (OSError, ValueError) as error:
            photo_state = None
            self.log.appendPlainText(f"Could not update the saved photo scan: {error}")
        self._row_statuses[result.match.local_folder] = {"status": preparation.status.value, "warnings": bool(preparation.warnings)}
        self._finished_uploads[result.match.local_folder] = OrbeaUploadService.upload_finished(result.match)
        detail = " | ".join(filter(None, (preparation.error, *preparation.warnings)))
        self.log.appendPlainText(f"{result.match.sku}: {preparation.status.value}" + (f" — {detail}" if detail else ""))
        for row, match in enumerate(self.matches):
            if match.local_folder == result.match.local_folder:
                if photo_state:
                    self._photo_statuses[match.local_folder] = photo_state
                    self.table.item(row, 5).setText(self._photo_status_text(photo_state))
                    self.table.item(row, 5).setToolTip("")
                self.table.item(row, 3).setText(self._status_text(preparation.status.value))
                self.table.item(row, 4).setText(detail)
                if result.succeeded:
                    self.table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
                break
        self.status.setText(self._t("progress", "{done}/{total} product(s) finished", done=len(self.results), total=len(self.worker.matches)))

    def _failed(self, error):
        self._report_batch_error = error
        self.status.setText(error)
        self.log.appendPlainText(error)
        self.screen._error(self._t("title", "Pimbo workflow"), error)

    def _finish_activity(self):
        tracker = getattr(self.screen.main, "operation_tracker", None)
        if tracker is None or not self._operation_id:
            return
        ok = sum(result.succeeded for result in self.results)
        failed = len(self.results) - ok
        warnings = sum(bool(result.preparation.warnings) for result in self.results)
        pending = len(self.worker.matches) - len(self.results)
        status = ("cancelled" if self.worker._stop_requested and pending else
                  "failed" if self.worker._batch_error or (not ok and (failed or pending)) else
                  "partial" if failed or warnings or pending else "succeeded")
        errors = self.worker._batch_error or " | ".join(result.preparation.error for result in self.results if result.preparation.error)
        tracker.finish(self._operation_id, status, summary={"succeeded": ok, "failed": failed,
            "warnings": warnings, "unprocessed": pending}, error_summary=errors, output_path=self.folder.text())

    def _finished(self):
        self._busy = False
        succeeded = sum(result.succeeded for result in self.results)
        warnings = sum(bool(result.preparation.warnings) for result in self.results)
        total = len(self.worker.matches)
        self.status.setText(self._t("finished", "Finished: {ok} successful, {failed} failed or blocked, {warnings} with warnings, {pending} unprocessed.",
            ok=succeeded, failed=len(self.results)-succeeded, warnings=warnings, pending=total-len(self.results)))
        reason = self.worker._batch_error or next((result.preparation.error for result in self.results if result.preparation.error), "")
        if reason:
            self.status.setText(self.status.text() + "\n" + self._t("failure_reason", "Reason: {reason}", reason=reason))
        root = Path(self.folder.text())
        if (root / "run_checkpoint.json").is_file() and any(self._photo_statuses.values()):
            try:
                from tools.orbea_automation.checkpoint import RunCheckpoint
                from tools.orbea_automation.report import write_report
                path = root / "run_checkpoint.json"
                report = write_report(RunCheckpoint(path, json.loads(path.read_text(encoding="utf-8")), resumed=True))
                self.screen._refresh_report_path(root)
                if report.name != "orbea_matches.xlsx":
                    self.log.appendPlainText(self.screen._t(
                        "orbea.report.updated_copy",
                        "The original Excel was open or read-only. Updated results are saved in: {path}",
                        path=str(report),
                    ))
            except (OSError, ValueError) as error:
                self.log.appendPlainText(f"Could not refresh the photo-scan Excel: {error}")
        self.screen._update_action_states()

    def request_stop(self):
        if self.worker and self.worker.isRunning():
            self.screen.workflow_controller.request_stop()
            self.stop.setEnabled(False)
            self.status.setText(self._t("stopping", "Stopping after the current product…"))

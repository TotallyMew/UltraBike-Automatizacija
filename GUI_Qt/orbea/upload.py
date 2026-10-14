"""Collected Orbea products and the selectable PIMBO editing workflow."""
from __future__ import annotations

import json
import re
import threading
from collections import Counter
from pathlib import Path
from Utilities.UploadResultsReport import result_record, upload_result_row, write_upload_results

from PySide6.QtCore import QEvent, QPointF, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFileDialog, QHeaderView, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CaptionLabel, CheckBox, ComboBox, FlowLayout, LineEdit, PlainTextEdit, PrimaryPushButton, PushButton, isDarkTheme

from GUI_Qt.kross.workers import KrossUploadWorker
from Managers.PimboProductEditor import PimPreparationResult, PimPreparationStatus
from GUI_Qt.orbea.tabs import OrbeaDisclosure
from GUI_Qt.orbea.panels import ProductToolbar, translate_choices
from tools.orbea_automation.selected_downloads import product_identity, resolve_product_rows
from GUI_Qt.styles.theme_config import get_accent_colors, get_text_color
from tools.orbea_automation.upload import OrbeaUploadService, OrbeaWorkflowOptions, OrbeaUploadResult
from tools.orbea_automation.table_packages import geometry_needs_recollection
from tools.orbea_automation.photo_scan import PHOTO_STATUSES, photo_scan_matches, saved_product_rows, record_uploaded_photos
from GUI_Qt.orbea.photo_scan_workflow import OrbeaPhotoScanWorkflow
from GUI_Qt.orbea.content_scan_workflow import OrbeaContentScanWorkflow
from GUI_Qt.orbea.manual_products import OrbeaManualProductWorkflow
from tools.orbea_automation.content_scan import CONTENT_STATUSES
from tools.orbea_automation.run_report import OrbeaRunReport, STAGE_LABELS, summarize_error
from GUI_Qt.orbea.run_report import OrbeaRunReportDialog
from GUI_Qt.orbea.browser_pool import BrowserCountControl, BrowserTaskQueue, ProductClaims, driver_service, upload_tasks


class _UploadProgress:
    """A text callback with optional structured stage notifications."""
    def __init__(self, worker, match, browser_number=None):
        self.worker, self.match, self.browser_number = worker, match, browser_number

    def __call__(self, message):
        prefix = f"[Browser {self.browser_number} · {self.match.sku}] " if self.browser_number else ""
        self.worker.progress_changed.emit(prefix + str(message))

    def stage_changed(self, stage, state, detail=""):
        self.worker.stage_changed.emit(self.match, stage, state, str(detail))


class OrbeaUploadWorker(KrossUploadWorker):
    completed = Signal(object)
    product_started = Signal(object)
    stage_changed = Signal(object, str, str, str)
    options_type = OrbeaWorkflowOptions
    result_type = OrbeaUploadResult

    def __init__(self, *args, retry_unfinished=False, browser_count=1,
                 browser_pool_factory=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.retry_unfinished = retry_unfinished
        self.browser_count = max(1, min(4, int(browser_count)))
        self.browser_pool_factory = browser_pool_factory
        self._results_lock = threading.Lock()
        if retry_unfinished:
            self.matches = tuple(match for match in self.matches if not OrbeaUploadService.upload_finished(match, self.options))

    def _upload_one(self, service, match):
        self.product_started.emit(match)
        progress = _UploadProgress(self, match)
        if self.retry_unfinished:
            return service.upload_and_save(match, self.output_root, options=self.options,
                                           progress=progress, resume_completed=True)
        return service.upload_and_save(match, self.output_root, options=self.options, progress=progress)

    def run(self):
        if self.browser_count <= 1 or len(self.matches) <= 1:
            return super().run()
        try:
            if not self.options.allows_multiple_products:
                raise ValueError("A run without Save can target only one PIMBO product at a time")
            if self.browser_pool_factory is None:
                raise RuntimeError("Parallel uploads require an authenticated browser pool")
            primary = self.service_factory()
            preflight = getattr(primary, "prepare_upload_batch", None)
            if callable(preflight):
                preflight(self.matches, progress=self.progress_changed.emit)
            tasks = upload_tasks(self.matches)
            queue = BrowserTaskQueue(tasks, lambda: self._stop_requested)
            claims = ProductClaims()
            count = min(self.browser_count, len(tasks))
            with self.browser_pool_factory(count, self.progress_changed.emit, queue.is_cancelled) as pool:
                services = {id(pool.drivers[0]): primary}
                for driver in pool.drivers[1:]:
                    service = driver_service(self.service_factory, driver)
                    if any(service is old for old in services.values()):
                        raise RuntimeError("Each parallel browser must have its own upload service")
                    preflight = getattr(service, "prepare_upload_batch", None)
                    if callable(preflight):
                        try:
                            preflight(self.matches, progress=self.progress_changed.emit)
                        except Exception:
                            pool.preserve(driver)
                            raise
                    services[id(driver)] = service

                def execute(number, driver, task):
                    key, matches = task
                    service = services[id(driver)]
                    service._parallel_product_claim = lambda product_id: claims.claim(product_id, key)
                    for match in matches:
                        if queue.is_cancelled():
                            break
                        self.product_started.emit(match)
                        service._upload_target = match
                        progress = _UploadProgress(self, match, number)
                        progress(f"Running selected stages ({len(self.results)}/{len(self.matches)} finished)")
                        try:
                            kwargs = {"resume_completed": True} if self.retry_unfinished else {}
                            result = service.upload_and_save(match, self.output_root, options=self.options,
                                                             progress=progress, **kwargs)
                        except Exception as error:
                            target = getattr(service, "_upload_target", match)
                            result = self.result_type(target, PimPreparationResult(target.sku, target.pimbo_product_id,
                                status=PimPreparationStatus.FAILED, final_url=target.pimbo_product_url, error=str(error)), options=self.options)
                        with self._results_lock:
                            self.results.append(result)
                            self.item_finished.emit(result)
                        if not result.succeeded:
                            try:
                                recovered = service.recover_after_failed_upload(result.match, progress=progress)
                            except Exception as error:
                                recovered = False
                                progress(f"Recovery failed: {error}")
                            if not recovered:
                                queue.fatal.set()
                                pool.preserve(driver)
                                raise RuntimeError(f"Browser {number}: could not safely recover {match.sku}; remaining products were not started")

                queue.run(pool.drivers, execute)
                if queue.errors:
                    raise RuntimeError(" | ".join(queue.errors))
        except Exception as error:
            self._batch_error = str(error)
            if not self._stop_requested:
                self.failed.emit(self._batch_error)
        finally:
            self._emit_completed()

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
        self.service_factory = service_factory or (lambda driver=None: OrbeaUploadService(driver if driver is not None else screen.main.driver))
        self.worker = None
        self.matches = ()
        self.results = []
        self.run_report = None
        self._busy = False
        self._operation_id = None
        self._config = []
        self._finished_uploads = {}
        self._finished_stages = {}
        self._row_statuses = {}
        self._photo_statuses = {}
        self._content_statuses = {}
        self._selection_locked = None
        self.photo_scan = OrbeaPhotoScanWorkflow(self)
        self.content_scan = OrbeaContentScanWorkflow(self)
        self.manual_products = OrbeaManualProductWorkflow(self)
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
        self.scan_content = self.toolbar.scan_content
        self.select_all = self.toolbar.select_all
        self.clear = self.toolbar.clear
        self._config.extend((self.toolbar.load_button, self.toolbar.select_button,
                             self.toolbar.add_product, self.toolbar.edit_product,
                             self.model_filter, self.scan_photos, self.scan_content,
                             self.toolbar.exclude_prefixes, self.toolbar.include_button, self.toolbar.exclude_button))
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
        self.table = QTableWidget(0, 7, self)
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
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
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
        self.browsers = BrowserCountControl(screen, self)
        layout.addWidget(self.browsers)
        self._config.append(self.browsers.combo)
        self.start = PrimaryPushButton(self)
        self.start.setMinimumHeight(38)
        layout.addWidget(self.start)
        self.stop = PushButton(self)
        layout.addWidget(self.stop)
        self.export_results = PushButton(self)
        self.export_results.clicked.connect(self._export_results)
        layout.addWidget(self.export_results)
        self.export_results.hide()
        self.status = CaptionLabel(self)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.open_report = PushButton(self)
        self.open_report.clicked.connect(self.open_run_report)
        layout.addWidget(self.open_report)
        self.run_report_dialog = OrbeaRunReportDialog(self)
        self.details = OrbeaDisclosure(self)
        layout.addWidget(self.details)
        self.log = PlainTextEdit(self)
        self.log.setReadOnly(True)
        self.log.setFixedHeight(140)
        self.log.setMaximumBlockCount(2500)
        self.details.body_layout.addWidget(self.log)
        self.details.hide()  # The small legacy log is used only by photo scanning.
        self.all_steps.clicked.connect(lambda: self._select_steps(True))
        self.clear_steps.clicked.connect(lambda: self._select_steps(False))
        self.table.itemChanged.connect(self.update_state)
        self.table.currentCellChanged.connect(self.update_state)
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

    def _content_status_text(self, state):
        status = state.get("status", "content_not_checked")
        text = self._t("content_scan.status." + status, CONTENT_STATUSES.get(status, status))
        count = len(state.get("missing_attributes", [])) + len(state.get("missing_specifications", []))
        return f"{text} ({count})" if status == "missing_content" else text

    def _content_details(self, state):
        details = []
        for key, label in (("missing_attributes", self._t("content_scan.attributes", "Required attributes")),
                           ("missing_specifications", "Bendra informacija")):
            if state.get(key):
                details.append(label + ": " + ", ".join(state[key]))
        if state.get("error"):
            details.append(state["error"])
        return "\n".join(details)

    def retranslate_ui(self):
        self.title.setText(self._t("title", "2. Choose products"))
        self.hint.setText(self._t("hint", "Load, scan or add products manually, then check the rows to process. Actions use only checked products currently shown."))
        self.steps_title.setText(self._t("steps_title", "3. Update Pimbo"))
        self.steps_hint.setText(self._t("steps_hint", "Choose what to update, then upload. Only Draft products are edited. Geometry and size tables replace previous images and save automatically."))
        self.empty_hint.setText(self._t("empty", "Scan or load products, or use Add product to enter your own finding."))
        self.details.set_title(self._t("log", "Upload details and log"))
        self.folder.setPlaceholderText(self._t("folder", "Collected run or product folder"))
        self.toolbar.retranslate_ui()
        self.browsers.retranslate_ui()
        for button, key, fallback in (
            (self.start, "start_selected", "Upload selected"),
            (self.stop, "stop", "Stop after current product"),
            (self.export_results, "export_results", "Export upload results to Excel"),
            (self.open_report, "open_report", "Open run report"),
            (self.all_steps, "all_steps", "Select all steps"), (self.clear_steps, "clear_steps", "Clear steps"),
        ):
            button.setText(self._t(key, fallback))
        translate_choices(self.upload_mode, (
            ("normal", "mode.normal", "Run selected steps"),
            ("retry", "mode.retry", "Retry unfinished steps"),
        ), self._t)
        self._populate_models()
        self.table.setHorizontalHeaderLabels([self._t(key, label) for key, label in (
            ("selected", "Select"), ("sku", "SKU"), ("product", "Product"), ("status", "Status"), ("details", "Details"), ("photo_scan.column", "Pimbo photos"), ("content_scan.column", "Pimbo data"))])
        for row, match in enumerate(self.matches):
            state = self._content_statuses.get(match.local_folder, {})
            self.table.item(row, 6).setText(self._content_status_text(state))
            self.table.item(row, 6).setToolTip(self._content_details(state))
        for stage, check in self.checks.items():
            check.setText(self._t(f"stage.{stage}", STAGE_LABELS[stage]))
        self.checks["publish_products"].setToolTip(self._t("publish_hint",
            "Runs last, after every other selected step succeeds. Changes Draft to Published, saves and verifies the status."))

    def options(self):
        return OrbeaWorkflowOptions(**{stage: check.isChecked() for stage, check in self.checks.items()})

    def _options_changed(self):
        self._sync_table_save()
        self.screen._setting_set("orbea_workflow_options", json.dumps({stage: check.isChecked() for stage, check in self.checks.items()}))
        self.update_state()

    def _sync_table_save(self, locked=False):
        publish = self.checks["publish_products"].isChecked()
        required = publish or self.checks["geometry"].isChecked() or self.checks["size_tables"].isChecked()
        check = self.checks["save"]
        if required:
            check.blockSignals(True)
            check.setChecked(True)
            check.blockSignals(False)
        check.setEnabled(not locked and not required)
        check.setToolTip(self._t("publish_save_required", "Publishing always saves automatically and verifies the Published status.") if publish
                         else self._t("table_save_required", "Table uploads always save automatically after uploading and verification.") if required else "")

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, self._t("folder", "Collected run or product folder"), self.folder.text())
        if folder:
            self.load_packages(folder)

    def _load_saved(self):
        self._load_current()

    def clear_products(self):
        self.toolbar.excluded_count = None
        self.toolbar.included_count = None
        self.toolbar.refresh_exclusion_hint()
        self._finished_uploads = {}
        self._finished_stages = {}
        self._photo_statuses = {}
        self._content_statuses = {}
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
        self.toolbar.excluded_count = None
        self.toolbar.included_count = None
        self.toolbar.refresh_exclusion_hint()
        self.screen.workflow_controller.set_source(path)
        self.folder.setText(str(path))
        self.source_label.setText(str(path))
        self.source_label.show()
        self.screen._setting_set("orbea_upload_root", str(path))
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.matches))
        self._finished_uploads = {}
        self._finished_stages = {}
        self._row_statuses = {}
        self._photo_statuses = {}
        self._content_statuses = {}
        self._selection_locked = None
        for row, match in enumerate(self.matches):
            selection = QTableWidgetItem()
            selectable = bool(match.sku and match.status != "invalid")
            selection.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled if selectable else Qt.ItemFlag.NoItemFlags)
            finished = OrbeaUploadService.upload_finished(match)
            self._finished_uploads[match.local_folder] = finished
            default = Qt.CheckState.Checked if selectable and not finished else Qt.CheckState.Unchecked
            selection.setCheckState(previous.get(product_identity(match), default if not preserve_selection else Qt.CheckState.Unchecked))
            self.table.setItem(row, 0, selection)
            prior = OrbeaUploadService.read_upload_result(match)
            preparation = prior["preparation"] if prior and match.status != "not_collected" else {}
            completed = set(prior.get("completed_stages", ())) if prior else set()
            if preparation.get("status") == "no_changes" and finished:
                completed.add("save")
            self._finished_stages[match.local_folder] = completed
            detail = " | ".join(filter(None, (match.note, preparation.get("error"), *preparation.get("warnings", []))))
            if scan_rows.get(product_identity(match), {}).get("manual_product"):
                detail = " | ".join(filter(None, (self._t("manual.source", "Manual product link"), detail)))
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
            content = scan_rows.get(product_identity(match), {}).get("pimbo_content_scan", {})
            self._content_statuses[match.local_folder] = content
            item = QTableWidgetItem(self._content_status_text(content))
            item.setToolTip(self._content_details(content))
            self.table.setItem(row, 6, item)
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

    def _select_by_status(self, wanted, *, checked=True):
        self.screen.workflow_controller.select_visible(self, status=wanted, checked=checked)

    def _exclude_by_code(self):
        count = self.screen.workflow_controller.exclude_code_prefixes(self, self.toolbar.exclude_prefixes.text())
        if count is not None:
            self.toolbar.excluded_count = count
            self.toolbar.included_count = None
            self.toolbar.refresh_exclusion_hint()

    def _include_by_code(self):
        count = self.screen.workflow_controller.include_code_prefixes(self, self.toolbar.exclude_prefixes.text())
        if count is not None:
            self.toolbar.included_count = count
            self.toolbar.excluded_count = None
            self.toolbar.refresh_exclusion_hint()

    def retry_unfinished_uploads(self):
        self.start_upload(retry_unfinished=True)

    def _select_steps(self, checked):
        # Clear Save after the stages that force it, and keep normal signals
        # so the grouped stage counter refreshes along with the checkboxes.
        for stage, check in self.checks.items():
            if stage != "save":
                check.setChecked(checked)
        self.checks["save"].setChecked(checked)
        self._options_changed()

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
        return self.screen.workflow_controller.selected_products(self, ready_only=not self.options().publish_only)

    def selected_products(self):
        return self.screen.workflow_controller.selected_products(self)

    def is_running(self):
        return self._busy or bool(self.worker and self.worker.isRunning())

    def _selected_photos_available(self, matches=None, *, options=None):
        if not (options or self.options()).product_photos:
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
        self.toolbar.select_status.set_available(not locked and bool(self.matches))
        self.toolbar.unselect_status.set_available(not locked and bool(self.matches))
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
        requested = set(self.options().selected_stages)
        targets = tuple(match for match in matches if not (self._finished_uploads.get(match.local_folder, False)
                        and requested <= self._finished_stages.get(match.local_folder, set()))) if retry else matches
        self.start.setEnabled(bool(not locked and getattr(self.screen.main, "driver", None) is not None
                                   and targets and len(matches) == len(products) and self.options().any_selected
                                   and (len(targets) == 1 or self.options().allows_multiple_products)
                                   and self._selected_photos_available(targets)))
        try:
            can_scan = bool(products and resolve_product_rows(products)) if not locked else False
        except (OSError, ValueError, KeyError, TypeError):
            can_scan = False
        self.scan_photos.setEnabled(bool(not locked and can_scan and getattr(self.screen.main, "driver", None) is not None))
        self.scan_content.setEnabled(self.scan_photos.isEnabled())
        self.toolbar.reload.setEnabled(not locked and self.screen.workflow_controller.source_root is not None)
        current = self.manual_products.current_product()
        self.toolbar.edit_product.setEnabled(not locked and current is not None and bool(current.checkpoint_path) and current.status != "invalid")
        self.toolbar.select_button.setEnabled(not locked and bool(self.matches))
        self.toolbar.exclude_button.setEnabled(not locked and bool(self.matches) and bool(self.toolbar.exclude_prefixes.text().strip(" \t\r\n,;")))
        self.toolbar.include_button.setEnabled(self.toolbar.exclude_button.isEnabled())
        self.export_results.setEnabled(bool(self.matches) and not locked)
        self.open_report.setEnabled(self.run_report is not None)
        if self.run_report is not None:
            self.run_report_dialog.retry_failed.setEnabled(not locked and self.run_report.finished and self.run_report.counts["failed"] > 0)
            self.run_report_dialog.retry_pending.setEnabled(not locked and self.run_report.finished and self.run_report.counts["not_started"] > 0)
        self.stop.setEnabled(self.is_running() and not activity.stopping)
        self.stop.setText(self.screen._t("orbea.browsers.stop", "Stop after active products") if self.browsers.count > 1
                          else self._t("stop", "Stop after current product"))
        self.stop.setVisible(self.is_running())
        for widget in (self.model_label, self.model_filter, self.selection_summary, self.toolbar.exclusion):
            widget.setVisible(bool(self.matches))
        visible = sum(1 for _ in self._visible_rows())
        self.selection_summary.setText(self._t("selection_summary", "Showing {visible} of {total} products · {selected} selected",
            visible=visible, total=len(self.matches), selected=len(products)))
        if hasattr(self.screen, "_download_mode"):
            self.screen._update_download_state(locked)

    def start_upload(self, *, retry_unfinished=False, report_targets=None, report_options=None):
        if self.screen.is_running():
            return
        selected, options = (tuple(report_targets), report_options) if report_targets is not None else (self.selected_matches(), self.options())
        matches = tuple(match for match in selected if not OrbeaUploadService.upload_finished(match, options)) if retry_unfinished else selected
        if (report_targets is None and len(selected) != len(self.selected_products())) or not self._selected_photos_available(matches, options=options):
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
        self.details.hide()
        report_root = (self.run_report.root if report_targets is not None and self.run_report is not None else
                       Path(self.folder.text()) if self.folder.text() else Path(matches[0].local_folder))
        self.run_report = OrbeaRunReport(matches, options, report_root, browser_count=self.browsers.count)
        self.run_report.add_log("info", f"Run started with {len(matches)} product(s)")
        self.run_report_dialog.set_report(self.run_report)
        self._busy = True
        self.status.setText(self._t("running", "Running selected steps…"))
        self.screen.workflow_controller.start_job("upload",
            lambda: OrbeaUploadWorker(self.service_factory, matches, None, options, retry_unfinished=retry_unfinished,
                browser_count=self.browsers.count, browser_pool_factory=self.screen.workflow_controller.make_browser_pool),
            owner=self, attribute="worker", operation_attribute="_operation_id", kind="upload",
            details={"output_path": self.folder.text()},
            signals={"progress_changed": self._on_progress, "item_finished": self._item_finished,
                     "product_started": self._product_started, "stage_changed": self._stage_changed,
                     "failed": self._failed, "completed": self._finish_activity},
            finished=self._finished, failed=self._failed)
        if self.worker is None:
            self.run_report.finish(batch_error=self._report_batch_error)
            self.run_report_dialog.refresh()
        self.open_run_report()

    def open_run_report(self):
        if self.run_report is not None:
            self.run_report_dialog.show()
            self.run_report_dialog.raise_()
            self.run_report_dialog.activateWindow()

    def _product_started(self, match):
        self.run_report.start_product(match)
        self.run_report_dialog.refresh()

    def _stage_changed(self, match, stage, state, detail):
        self.run_report.stage_changed(match, stage, state, detail)
        self.run_report_dialog.refresh()

    def _append_run_log(self, message, level="info"):
        if self.run_report is not None:
            summary = summarize_error(message)
            self.run_report.add_log(level, summary.headline, technical=summary.technical)
            self.run_report_dialog.refresh()
            if self.run_report.finished:
                self.run_report.save_snapshot()
                self.run_report_dialog._refresh_log()

    def _on_progress(self, message):
        message = summarize_error(message).headline
        if self.worker._stop_requested:
            message = self._stopping_text() + " " + message
        self.status.setText(message)
        if self.run_report is not None:
            self.run_report_dialog.live_line.setText(message)

    def _item_finished(self, result):
        self.results.append(result)
        preparation = result.preparation
        try:
            photo_state = record_uploaded_photos(result)
        except (OSError, ValueError) as error:
            photo_state = None
            self._append_run_log(f"Could not update the saved photo scan: {error}", "warning")
        self._row_statuses[result.match.local_folder] = {"status": preparation.status.value, "warnings": bool(preparation.warnings)}
        self._finished_uploads[result.match.local_folder] = OrbeaUploadService.upload_finished(result.match)
        self._finished_stages[result.match.local_folder] = set(result.completed_stages)
        if preparation.status == PimPreparationStatus.NO_CHANGES and self._finished_uploads[result.match.local_folder]:
            self._finished_stages[result.match.local_folder].add("save")
        detail = " | ".join(dict.fromkeys(summarize_error(text).headline for text in (preparation.error, *preparation.warnings) if text))
        if self.run_report is not None:
            self.run_report.add_result(result)
            self.run_report_dialog.refresh()
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
        self.status.setText(summarize_error(error).headline)
        self._append_run_log(error, "error")
        self.screen._error(self._t("title", "Pimbo workflow"), summarize_error(error).headline)

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
        total = len(self.worker.matches)
        stopped = getattr(self.worker, "_stop_requested", False)
        batch_error = self.worker._batch_error
        reason = batch_error or (self._t("stopped_by_user", "Stop was requested; remaining products were not processed.") if stopped and total > len(self.results) else "")
        if self.run_report is None:
            self.run_report = OrbeaRunReport(self.worker.matches, self.options(), self.folder.text() or None)
            for result in self.results:
                self.run_report.add_result(result)
            self.run_report_dialog.set_report(self.run_report)
        root = self.run_report.root or Path(self.folder.text())
        if (root / "run_checkpoint.json").is_file() and any(self._photo_statuses.values()):
            try:
                from tools.orbea_automation.checkpoint import RunCheckpoint
                from tools.orbea_automation.report import write_report
                path = root / "run_checkpoint.json"
                report = write_report(RunCheckpoint(path, json.loads(path.read_text(encoding="utf-8")), resumed=True))
                self.screen._refresh_report_path(root)
                if report.name != "orbea_matches.xlsx":
                    self._append_run_log(self.screen._t(
                        "orbea.report.updated_copy",
                        "The original Excel was open or read-only. Updated results are saved in: {path}",
                        path=str(report),
                    ))
            except (OSError, ValueError) as error:
                self._append_run_log(f"Could not refresh the photo-scan Excel: {error}", "warning")
        self._report_batch_error = reason
        self.run_report.finish(stop_requested=stopped, batch_error=batch_error)
        self.status.setText(self._t("report_ready", "{outcome}. Open run report for details.", outcome=self.run_report.outcome()[0]))
        self.run_report_dialog.refresh()
        self.run_report_dialog._refresh_log()
        self.open_run_report()
        self.screen._update_action_states()

    def request_stop(self):
        if self.worker and self.worker.isRunning():
            self.screen.workflow_controller.request_stop()
            self.stop.setEnabled(False)
            self.status.setText(self._stopping_text())
            if self.run_report is not None:
                self.run_report.stop_requested = True
                self.run_report.add_log("info", "Stop requested; finishing active products")
                self.run_report_dialog.refresh()

    def _stopping_text(self):
        if getattr(self.worker, "browser_count", 1) > 1:
            return self.screen._t("orbea.browsers.stopping", "Stopping after active products…")
        return self._t("stopping", "Stopping after the current product…")

    def retry_report_products(self, status):
        report = self.run_report
        if report is None or not report.finished or self.screen.is_running():
            return
        targets = tuple(match for match in report.matches if
            (status == "failed" and report.key(match) in report.results and not report.results[report.key(match)].succeeded)
            or (status == "not_started" and report.key(match) not in report.started_products))
        self.start_upload(retry_unfinished=status == "failed", report_targets=targets, report_options=report.options)

    def export_run_results(self):
        report = self.run_report
        if report is None or not report.finished:
            return
        path, _ = QFileDialog.getSaveFileName(self, self._t("export_results", "Export upload results to Excel"),
                                             str((report.root or Path(self.folder.text())) / "orbea-upload-results.xlsx"), "Excel (*.xlsx)")
        if path:
            try:
                rows = [upload_result_row(match, result_record(report.results[report.key(match)]) if report.key(match) in report.results else None, brand="Orbea") for match in report.matches]
                write_upload_results(path, rows, context={"Collection folder": str(report.root or self.folder.text()), "Batch stop reason": report.outcome()[1] if report.batch_error or report.stop_requested else ""})
                self._append_run_log(f"Upload results exported to {path}")
            except Exception as error:
                self.screen._error(self._t("export_results", "Export upload results to Excel"), str(error))

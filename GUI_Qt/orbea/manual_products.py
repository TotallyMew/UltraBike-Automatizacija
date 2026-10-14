"""Manual product entry and corrections alongside the scanned product list."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QVBoxLayout
from qfluentwidgets import BodyLabel, CaptionLabel, LineEdit, PrimaryPushButton, PushButton, TitleLabel

from GUI_Qt.styles.screen_theme import apply_screen_palette
from GUI_Qt.styles.theme_config import get_status_text_color, isDarkTheme
from tools.orbea_automation.manual_products import ManualProduct, import_manual_products_excel, save_manual_product
from tools.orbea_automation.selected_downloads import product_identity, resolve_product_rows
from tools.orbea_automation.website import template_code


class ManualProductDialog(QDialog):
    def __init__(self, panel, *, target=None):
        super().__init__(panel.screen)
        self.panel, self.target = panel, target
        self.saved = None
        self.imported = None
        tr = panel._t
        self.setWindowTitle(tr("manual.edit" if target else "manual.add", "Edit product" if target else "Add product"))
        self.setMinimumWidth(400)
        self.resize(560, 660 if target is None else 580)
        apply_screen_palette(self)
        box = QVBoxLayout(self)
        box.setContentsMargins(24, 24, 24, 24)
        box.setSpacing(10)
        box.addWidget(TitleLabel(self.windowTitle(), self))
        hint = CaptionLabel(tr("manual.hint", "Add your own finding to the product list. An existing SKU updates its row. Include the colour in the name for photo matching."), self)
        hint.setWordWrap(True)
        box.addWidget(hint)
        if target is None:
            self.import_excel = PushButton(tr("manual.excel", "Import Excel…"), self)
            self.import_excel.clicked.connect(lambda: self._import_excel())
            box.addWidget(self.import_excel)
            excel_hint = CaptionLabel(tr("manual.excel_hint", "Excel columns: A = SKU, B = name, C = TTCC code, E = Orbea URL. Headers are optional; D is ignored."), self)
            excel_hint.setWordWrap(True)
            box.addWidget(excel_hint)
        self.sku = LineEdit(self)
        self.code = LineEdit(self)
        self.name = LineEdit(self)
        self.url = LineEdit(self)
        for field, key, fallback, placeholder in (
            (self.sku, "sku", "Pimbo SKU (without TTCC)", "U10707SV"),
            (self.code, "code", "Model code (with TTCC)", "U107TTCC"),
            (self.name, "name", "Product name, including colour", "Orbea ORCA M30i Black"),
            (self.url, "url", "Orbea product URL", "https://www.orbea.com/…"),
        ):
            label = BodyLabel(tr("manual." + key, fallback), self)
            label.setWordWrap(True)
            label.setBuddy(field)
            field.setPlaceholderText(placeholder)
            field.setMinimumHeight(36)
            box.addWidget(label)
            box.addWidget(field)
        self.sku.textChanged.connect(self._suggest_code)
        if target is not None:
            _, row = resolve_product_rows((target,))[0]
            self.sku.setText(row["sku"])
            self.sku.setReadOnly(True)
            self.code.setText(row.get("catalogue_code") or template_code(row["sku"]))
            self.name.setText(row.get("title") or target.orbea_product_name)
            self.url.setText(row.get("catalogue_url", ""))
        note = CaptionLabel(tr("manual.source_hint", "Changing the name or link requires downloading the product again. Previous files and upload history are kept."), self)
        note.setWordWrap(True)
        box.addWidget(note)
        self.error = CaptionLabel(self)
        self.error.setWordWrap(True)
        self.error.setStyleSheet(f"color: {get_status_text_color('error', isDarkTheme())};")
        self.error.hide()
        box.addWidget(self.error)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel = PushButton(tr("manual.cancel", "Cancel"), self)
        self.save = PrimaryPushButton(tr("manual.save", "Save product"), self)
        buttons.addWidget(self.cancel)
        buttons.addWidget(self.save)
        box.addLayout(buttons)
        self.cancel.clicked.connect(self.reject)
        self.save.clicked.connect(self._save)
        self.save.setDefault(True)

    def _suggest_code(self, text):
        self.code.setText(template_code(text))

    def _save(self):
        screen = self.panel.screen
        if screen.is_running():
            return
        try:
            product = ManualProduct(self.sku.text(), self.name.text(), self.url.text(), self.code.text())
            root = screen.workflow_controller.source_root
            output = screen._output_edit.text().strip()
            if root is None and not output:
                raise ValueError(self.panel._t("manual.output_required", "Choose the Orbea output folder first"))
            self.saved = save_manual_product(product, output, source_root=root, target=self.target,
                browser_name=str(screen._setting_get("browser_choice", "Chrome") or "Chrome").lower())
        except Exception as error:
            self.error.setText(str(error))
            self.error.show()
            return
        self.accept()

    def _import_excel(self, path=None):
        panel, screen = self.panel, self.panel.screen
        if screen.is_running():
            return
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, panel._t("manual.excel_pick", "Choose products to add from Excel"),
                str(screen._setting_get("orbea_manual_excel", screen._output_edit.text()) or ""), "Excel (*.xlsx *.xlsm)")
        if not path:
            return
        try:
            self.imported = import_manual_products_excel(path, screen._output_edit.text().strip(),
                source_root=screen.workflow_controller.source_root,
                browser_name=str(screen._setting_get("browser_choice", "Chrome") or "Chrome").lower())
            if not self.imported.saved:
                raise ValueError("\n".join(self.imported.issues))
            screen._setting_set("orbea_manual_excel", str(path))
        except Exception as error:
            self.error.setText(str(error))
            self.error.show()
            return
        self.accept()


class OrbeaManualProductWorkflow:
    def __init__(self, panel):
        self.panel = panel

    def current_product(self):
        row = self.panel.table.currentRow()
        return self.panel.matches[row] if 0 <= row < len(self.panel.matches) and not self.panel.table.isRowHidden(row) else None

    def open(self, *, edit=False):
        panel, screen = self.panel, self.panel.screen
        if screen.is_running():
            return
        target = self.current_product() if edit else None
        if edit and target is None:
            return
        try:
            dialog = ManualProductDialog(panel, target=target)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            saved_products = dialog.imported.saved if dialog.imported else (dialog.saved,)
            saved = saved_products[-1]
            panel.load_packages(saved.source_root, preserve_selection=True)
            identities = {(str(item.result.checkpoint_path.resolve()), item.row_key) for item in saved_products}
            if any(product_identity(match) in identities and panel.table.isRowHidden(row)
                   for row, match in enumerate(panel.matches)):
                panel.model_filter.setCurrentIndex(0)
            blocked = panel.table.blockSignals(True)
            last_row = None
            for row, match in enumerate(panel.matches):
                if product_identity(match) in identities:
                    panel.table.item(row, 0).setCheckState(Qt.CheckState.Checked)
                    last_row = row
            if last_row is not None:
                panel.table.setCurrentCell(last_row, 1)
                panel.table.scrollToItem(panel.table.item(last_row, 1))
            panel.table.blockSignals(blocked)
            screen._run_dir = saved.result.run_dir
            screen._workbook_path = saved.result.workbook_path
            screen._download_selection = None
            screen._download_review_root = None
            screen._open_excel_btn.setEnabled(saved.result.workbook_path.is_file())
            screen._open_folder_btn.setEnabled(True)
            message = panel._t("manual.saved", "Product saved. Choose the data and use Download selected.")
            if dialog.imported:
                imported = dialog.imported
                message = panel._t("manual.excel_result", "Imported {count} products: {added} added, {updated} updated. {duplicates} duplicate rows ignored.",
                    count=len(imported.saved), added=imported.added, updated=imported.updated, duplicates=imported.duplicates)
                if imported.issues:
                    message += " " + panel._t("manual.excel_issues", "{count} row issue(s). See details below.", count=len(imported.issues))
                    panel.log.clear()
                    panel.log.appendPlainText("\n".join(imported.issues))
                    panel.details.show()
                    panel.details.set_expanded(True)
            panel.status.setText(message)
            report_errors = tuple(dict.fromkeys(item.report_error for item in saved_products if item.report_error))
            if report_errors:
                screen._warn(panel._t("manual.add", "Add product"), panel._t("manual.report_error", "Product saved, but Excel could not be refreshed: {error}", error="\n".join(report_errors)))
            screen._update_action_states()
        except Exception as error:
            screen._error(panel._t("manual.edit" if edit else "manual.add", "Edit product" if edit else "Add product"), str(error))

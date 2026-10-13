"""Manual bulk earning entry with a live product and payout preview."""

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDateTimeEdit, QDialog, QGridLayout, QHBoxLayout,
    QHeaderView, QPlainTextEdit, QTableWidget, QTableWidgetItem, QVBoxLayout,
)
from qfluentwidgets import (
    CaptionLabel, CheckBox, ComboBox, PrimaryPushButton, PushButton,
    StrongBodyLabel, isDarkTheme, qconfig,
)

from GUI_Qt.earnings.presentation import PRODUCT_TYPES, money
from GUI_Qt.earnings.widgets import configure_earnings_datetime_edit, apply_earnings_datetime_theme
from GUI_Qt.styles.theme_config import (
    SIZES, SPACING, get_dialog_button_style, get_dialog_table_style, get_form_dialog_style,
    get_form_input_style,
)
from Managers.EarningsManager import EarningsManager, BulkEarningResult
from Utilities.EarningBulkInput import BulkEarningInputError, parse_bulk_earning_input


class BulkEarningAddDialog(QDialog):
    def __init__(
        self, service: EarningsManager, parent=None, *, translate=None,
        brand_id=None, product_type="bicycle", earned_at=None,
    ):
        super().__init__(parent)
        self.service = service
        self._translate = translate
        self.result_data: BulkEarningResult | None = None
        self._rows = []
        self._saving = False
        self.setObjectName("earningsBulkAddDialog")
        self.setWindowTitle(self._t("earnings.bulk_add.title", "Add earnings in bulk"))
        self.setModal(True)
        self.resize(760, 690)
        self.setMinimumSize(620, 600)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"])
        layout.setSpacing(SPACING["sm"])
        layout.addWidget(StrongBodyLabel(self.windowTitle()))
        intro = CaptionLabel(self._t(
            "earnings.bulk_add.intro",
            "Paste one SKU per line, or copy two Excel columns: SKU and product name. Brand, type and date apply to every product.",
        ))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.products = QPlainTextEdit()
        self.products.setAccessibleName(self._t("earnings.bulk_add.products", "Products"))
        self.products.setPlaceholderText(self._t(
            "earnings.bulk_add.placeholder", "U35705XL\nU35705XM\nU35705XP",
        ))
        self.products.setMinimumHeight(100)
        self.products.setMaximumHeight(150)
        layout.addWidget(self.products)

        fields = QGridLayout()
        fields.setHorizontalSpacing(SPACING["md"])
        self.brand = ComboBox()
        self.brand.addItem(self._t("earnings.brand.none", "No brand"), userData=None)
        for brand in service.list_brands():
            self.brand.addItem(brand["name"], userData=brand["id"])
        self.brand.setCurrentIndex(max(0, self.brand.findData(brand_id)))
        self.type = ComboBox()
        for key, label in PRODUCT_TYPES:
            self.type.addItem(self._t(f"earnings.bulk_add.type.{key}", label), userData=key)
        self.type.setCurrentIndex(max(0, self.type.findData(product_type)))
        self.when = QDateTimeEdit(earned_at or datetime.now())
        configure_earnings_datetime_edit(self.when)
        for column, (key, label, control) in enumerate((
            ("earnings.field.brand", "Brand", self.brand),
            ("earnings.field.type", "Product type", self.type),
        )):
            fields.addWidget(CaptionLabel(self._t(key, label)), 0, column)
            fields.addWidget(control, 1, column)
            control.setAccessibleName(self._t(key, label))
            fields.setColumnStretch(column, 1)
        fields.addWidget(CaptionLabel(self._t("earnings.field.date", "Date and time")), 2, 0, 1, 2)
        fields.addWidget(self.when, 3, 0, 1, 2)
        layout.addLayout(fields)
        self.allow_duplicates = CheckBox(self._t(
            "earnings.bulk_add.duplicates", "Include duplicate SKUs as separate paid entries",
        ))
        layout.addWidget(self.allow_duplicates)
        self.summary = StrongBodyLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([
            "SKU", self._t("earnings.field.name", "Product name"),
            self._t("earnings.bulk_add.status", "Status"),
        ])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 140)
        self.table.setColumnWidth(2, 170)
        self.table.setMinimumHeight(130)
        layout.addWidget(self.table, 1)
        self.error = CaptionLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        footer = QHBoxLayout()
        footer.addStretch()
        self.cancel_button = PushButton(self._t("common.cancel", "Cancel"))
        self.save_button = PrimaryPushButton()
        for button in (self.cancel_button, self.save_button):
            button.setFixedHeight(SIZES["button_height"])
        self.cancel_button.setAutoDefault(False)
        self.save_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self._save)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.save_button)
        layout.addLayout(footer)
        self.products.textChanged.connect(self._update_preview)
        self.type.currentIndexChanged.connect(self._update_preview)
        self.allow_duplicates.toggled.connect(self._update_preview)
        qconfig.themeChangedFinished.connect(self._apply_theme)
        self._apply_theme()
        self._update_preview()

    def _t(self, key, fallback, **kwargs):
        if callable(self._translate):
            value = self._translate(key, **kwargs)
            if value != key:
                return value
        return fallback.format(**kwargs)

    def _update_preview(self, *_args):
        self.error.hide()
        self._rows = []
        preview = []
        try:
            rows = parse_bulk_earning_input(self.products.toPlainText())
            if rows:
                preview = self.service.preview_bulk_entries(
                    rows, allow_duplicates=self.allow_duplicates.isChecked(),
                )
            self._rows = rows
        except BulkEarningInputError as error:
            messages = {
                "columns": ("earnings.bulk_add.error.columns", "Row {row}: paste only the SKU and optional name columns."),
                "sku": ("earnings.bulk_add.error.sku", "Row {row}: an SKU is required."),
                "format": ("earnings.bulk_add.error.format", "The pasted Excel data has invalid quoting. Copy the cells again."),
            }
            key, fallback = messages[error.reason]
            self.error.setText(self._t(key, fallback, **({"row": error.row} if error.reason != "format" else {})))
            self.error.show()
        except Exception as error:
            self.error.setText(str(error))
            self.error.show()
        self.table.setRowCount(len(preview))
        count = sum(row["include"] for row in preview)
        total = count * self.service.get_rate_cents(self.type.currentData())
        for index, row in enumerate(preview):
            if not row["include"]:
                status = self._t("earnings.bulk_add.skipped", "Duplicate — skipped")
            elif row["duplicate"]:
                status = self._t("earnings.bulk_add.include_duplicate", "Add duplicate")
            else:
                status = self._t("earnings.bulk_add.ready", "Ready to add")
            for column, value in enumerate((row["sku"], row["product_name"] or "", status)):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(index, column, item)
        self.summary.setText(self._t(
            "earnings.bulk_add.summary", "{count:,} earnings • {amount} • {skipped:,} duplicates skipped",
            count=count, amount=money(total), skipped=len(preview) - count,
        ))
        self.save_button.setText(self._t("earnings.bulk_add.save", "Add {count:,} earnings", count=count))
        self.save_button.setEnabled(count > 0 and not self._saving)

    def _save(self):
        if self._saving or self.result_data is not None:
            return
        self._update_preview()
        if not self.save_button.isEnabled():
            return
        self._saving = True
        self.save_button.setEnabled(False)
        try:
            self.result_data = self.service.bulk_create_entries(
                self._rows, self.type.currentData(), brand_id=self.brand.currentData(),
                earned_at=self.when.dateTime().toPython(),
                allow_duplicates=self.allow_duplicates.isChecked(),
            )
        except Exception as error:
            self._saving = False
            self._update_preview()
            self.error.setText(self._t("earnings.bulk_add.failed", "Could not add earnings: {error}", error=str(error)))
            self.error.show()
            return
        self.accept()

    def _apply_theme(self):
        dark = isDarkTheme()
        self.setStyleSheet(get_form_dialog_style(dark, self.objectName()))
        self.products.setStyleSheet(get_form_input_style(dark, "QPlainTextEdit"))
        self.table.setStyleSheet(get_dialog_table_style(dark))
        self.cancel_button.setStyleSheet(get_dialog_button_style(dark, primary=False))
        self.save_button.setStyleSheet(get_dialog_button_style(dark, primary=True))
        apply_earnings_datetime_theme(self.when)

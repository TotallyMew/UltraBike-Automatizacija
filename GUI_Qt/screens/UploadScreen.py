"""
Upload Screen - Fluent Design System
Single product upload with Space Indigo/Lavender Grey color scheme
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout
from PySide6.QtCore import Qt, QThread, Signal, QEvent
from PySide6.QtGui import QFont
from qfluentwidgets import (
    LineEdit, ComboBox, CheckBox, PrimaryPushButton, PushButton,
    IndeterminateProgressRing, BodyLabel, TitleLabel, CaptionLabel,
    InfoBar, InfoBarPosition, TransparentToolButton, FluentIcon,
    CardWidget, isDarkTheme, StrongBodyLabel, qconfig
)
from uploaderFactory import getUploaderClass
from Managers.DescriptionManager import DescriptionManager
from GUI_Qt.styles.theme_config import COLORS, FONTS


class UploadWorker(QThread):
    """Background worker for upload process with non-blocking retry support"""
    finished = Signal(bool, str)  # success, message
    progress = Signal(str)  # status updates
    retry_request = Signal(str)  # operation_name
    retry_response = Signal(object)  # result from dialog (True, False, or new code)

    def __init__(self, uploader, tr):
        super().__init__()
        self.uploader = uploader
        self.tr = tr
        self._retry_result = None
        self._waiting_for_retry = False
        self.retry_response.connect(self._on_retry_response)

    def run(self):
        """Perform upload in background thread, using non-blocking retry."""
        try:
            self.progress.emit(self.tr("upload.status.starting"))
            # Patch uploader and navigation handler to use our non-blocking retry
            self.uploader.set_retry_callback(self._request_retry)
            self.uploader.run()
            self.finished.emit(True, self.tr("upload.done"))
        except Exception as e:
            self.finished.emit(False, self.tr("upload.failed", error=str(e)))

    def _request_retry(self, operation_name):
        """Called by uploader/navigation handler when a retry is needed."""
        self._retry_result = None
        self._waiting_for_retry = True
        self.retry_request.emit(operation_name)
        # Wait for response from GUI, but yield to event loop
        while self._waiting_for_retry:
            self.msleep(50)
        return self._retry_result

    def _on_retry_response(self, result):
        self._retry_result = result
        self._waiting_for_retry = False


class UploadScreen(QWidget):
    """Main upload screen with Fluent Design and responsive scaling"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        # Connect upload worker retry signal to dialog handler
        self._active_retry_dialog = None
        self.main = main_window
        self.upload_worker = None
        self.description_manager = DescriptionManager(self.main.db)

        # Available brands
        self.brands = [
            "KROSS", "Pinarello", "Basso", "Factor",
            "TREK", "Rondo", "Octane", "Rascal", "Lee Cougan"
        ]

        # Store references for responsive scaling
        self.form_card = None
        self.current_scale = 1.0

        self._init_ui()
        self._load_descriptions()

        # Connect to theme change signal
        qconfig.themeChangedFinished.connect(self._on_theme_changed)

    def _init_ui(self):
        """Initialize UI with Fluent Design"""
        # Apply background color
        is_dark = isDarkTheme()
        bg_color = COLORS['space_indigo'] if is_dark else COLORS['platinum']

        self.setStyleSheet(f"""
            UploadScreen {{
                background-color: {bg_color};
                font-family: {FONTS['family']};
            }}
        """)
        self.setAutoFillBackground(True)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 20, 40, 20)  # Fluent standard: 40px sides
        main_layout.setSpacing(20)

        # === HEADER SECTION ===
        header = QHBoxLayout()

        # Title with icon
        title_container = QHBoxLayout()
        title_container.setSpacing(12)

        title_icon = TransparentToolButton(FluentIcon.UP, self)
        title_icon.setFixedSize(32, 32)
        title_icon.setEnabled(False)

        self.title_label = TitleLabel("")
        title_label = self.title_label

        title_container.addWidget(title_icon)
        title_container.addWidget(title_label)

        header.addLayout(title_container)
        header.addStretch()

        main_layout.addLayout(header)

        # === FORM CARD ===
        self.form_card = CardWidget()
        self.form_card.setBorderRadius(8)
        self.form_card.setMinimumWidth(600)  # Minimum comfortable width
        # Remove max-width to allow full responsiveness

        card_layout = QVBoxLayout(self.form_card)
        card_layout.setContentsMargins(32, 32, 32, 32)
        card_layout.setSpacing(24)

        # Form grid
        form_grid = QGridLayout()
        form_grid.setSpacing(20)  # Horizontal spacing - Fluent standard
        form_grid.setVerticalSpacing(24)  # Vertical spacing - Fluent standard

        row = 0

        # Brand selection
        self.brand_label = BodyLabel("")
        brand_label = self.brand_label
        brand_label.setStyleSheet(f"font-weight: 500; color: {COLORS['text_secondary']};")
        self.brand_caption = CaptionLabel("")
        brand_caption = self.brand_caption
        brand_caption.setStyleSheet(f"color: {COLORS['text_tertiary']};")

        self.brand_combo = ComboBox()
        self.brand_combo.addItems(self.brands)
        self.brand_combo.currentTextChanged.connect(self._on_brand_change)

        form_grid.addWidget(brand_label, row, 0)
        form_grid.addWidget(brand_caption, row + 1, 0)
        form_grid.addWidget(self.brand_combo, row, 1)
        row += 2

        # Product code
        self.code_label = BodyLabel("")
        code_label = self.code_label
        code_label.setStyleSheet(f"font-weight: 500; color: {COLORS['text_secondary']};")
        self.code_caption = CaptionLabel("")
        code_caption = self.code_caption
        code_caption.setStyleSheet(f"color: {COLORS['text_tertiary']};")

        self.code_field = LineEdit()
        self.code_field.textChanged.connect(self._on_code_changed)

        form_grid.addWidget(code_label, row, 0)
        form_grid.addWidget(code_caption, row + 1, 0)
        form_grid.addWidget(self.code_field, row, 1)
        row += 2

        # URL/Code input
        self.url_label = BodyLabel("")
        url_label = self.url_label
        url_label.setStyleSheet(f"font-weight: 500; color: {COLORS['text_secondary']};")
        self.url_caption = CaptionLabel("")
        url_caption = self.url_caption
        url_caption.setStyleSheet(f"color: {COLORS['text_tertiary']};")

        self.url_field = LineEdit()
        self.url_field.textChanged.connect(self._on_url_changed)

        form_grid.addWidget(url_label, row, 0)
        form_grid.addWidget(url_caption, row + 1, 0)
        form_grid.addWidget(self.url_field, row, 1)
        row += 2

        # Description dropdown
        desc_label_row = QHBoxLayout()
        self.desc_label = BodyLabel("")
        desc_label = self.desc_label
        desc_label.setStyleSheet(f"font-weight: 500; color: {COLORS['text_secondary']};")

        self.refresh_desc_button = TransparentToolButton(FluentIcon.SYNC, self)
        self.refresh_desc_button.setFixedSize(24, 24)
        self.refresh_desc_button.clicked.connect(self._load_descriptions)

        desc_label_row.addWidget(desc_label)
        desc_label_row.addWidget(self.refresh_desc_button)
        desc_label_row.addStretch()

        self.desc_caption = CaptionLabel("")
        desc_caption = self.desc_caption
        desc_caption.setStyleSheet(f"color: {COLORS['text_tertiary']};")

        self.description_combo = ComboBox()
        self.description_combo.currentTextChanged.connect(self._on_description_changed)

        desc_label_widget = QWidget()
        desc_label_layout = QVBoxLayout(desc_label_widget)
        desc_label_layout.setContentsMargins(0, 0, 0, 0)
        desc_label_layout.setSpacing(4)
        desc_label_layout.addLayout(desc_label_row)
        desc_label_layout.addWidget(desc_caption)

        form_grid.addWidget(desc_label_widget, row, 0)
        form_grid.addWidget(self.description_combo, row, 1)
        row += 1

        card_layout.addLayout(form_grid)

        # === OPTIONS SECTION ===
        options_card = CardWidget()
        options_card.setBorderRadius(6)
        options_card.setStyleSheet(f"""
            CardWidget {{
                background-color: {'rgba(255,255,255,0.03)' if is_dark else 'rgba(0,0,0,0.02)'};
                border: 1px solid {COLORS['border_dark'] if is_dark else COLORS['border_light']};
            }}
        """)

        options_layout = QVBoxLayout(options_card)
        options_layout.setContentsMargins(20, 16, 20, 16)
        options_layout.setSpacing(12)

        self.options_title = StrongBodyLabel("")
        options_title = self.options_title
        options_title.setStyleSheet(f"color: {COLORS['text_secondary']};")
        options_layout.addWidget(options_title)

        # Disclaimer checkbox
        disclaimer_row = QHBoxLayout()
        disclaimer_row.setSpacing(8)

        self.disclaimer_checkbox = CheckBox("")
        disclaimer_info = TransparentToolButton(FluentIcon.INFO, self)
        self.disclaimer_info_btn = disclaimer_info
        disclaimer_info.setFixedSize(20, 20)
        disclaimer_info.clicked.connect(self._show_disclaimer_info)

        disclaimer_row.addWidget(self.disclaimer_checkbox)
        disclaimer_row.addWidget(disclaimer_info)
        disclaimer_row.addStretch()

        options_layout.addLayout(disclaimer_row)

        # Frameset checkbox (conditional - only for Pinarello)
        self.frameset_row = QWidget()
        frameset_layout = QHBoxLayout(self.frameset_row)
        frameset_layout.setContentsMargins(0, 0, 0, 0)
        frameset_layout.setSpacing(8)

        self.frameset_checkbox = CheckBox("")
        frameset_info = TransparentToolButton(FluentIcon.INFO, self)
        self.frameset_info_btn = frameset_info
        frameset_info.setFixedSize(20, 20)

        frameset_layout.addWidget(self.frameset_checkbox)
        frameset_layout.addWidget(frameset_info)
        frameset_layout.addStretch()

        options_layout.addWidget(self.frameset_row)
        self.frameset_row.setVisible(False)

        card_layout.addWidget(options_card)

        # === ACTION BUTTONS ===
        action_row = QHBoxLayout()
        action_row.setSpacing(12)

        self.upload_button = PrimaryPushButton("")
        self.upload_button.setIcon(FluentIcon.UP)
        self.upload_button.setEnabled(False)
        self.upload_button.setFixedHeight(40)
        self.upload_button.clicked.connect(self._handle_upload)

        self.progress_ring = IndeterminateProgressRing()
        self.progress_ring.setFixedSize(32, 32)
        self.progress_ring.setVisible(False)

        self.status_label = BodyLabel("")
        self.status_label.setStyleSheet(f"color: {COLORS['text_secondary']};")

        action_row.addWidget(self.upload_button)
        action_row.addWidget(self.progress_ring)
        action_row.addWidget(self.status_label)
        action_row.addStretch()

        card_layout.addLayout(action_row)

        # Center form card horizontally while allowing it to scale
        card_container = QHBoxLayout()
        card_container.addStretch()
        card_container.addWidget(self.form_card, 1)  # 1 = allow scaling
        card_container.addStretch()

        main_layout.addLayout(card_container)
        main_layout.addStretch()  # Push content up

        self.retranslate_ui()

    def retranslate_ui(self):
        tr = self.main.i18n.tr
        self.title_label.setText(tr("upload.title"))

        self.brand_label.setText(tr("upload.brand.label"))
        self.brand_caption.setText(tr("upload.brand.caption"))

        self.code_label.setText(tr("upload.code.label"))
        self.code_caption.setText(tr("upload.code.caption"))
        self.code_field.setPlaceholderText(tr("upload.code.placeholder"))

        self.url_label.setText(tr("upload.url.label"))
        self.url_caption.setText(tr("upload.url.caption"))
        self.url_field.setPlaceholderText(tr("upload.url.placeholder"))

        self.desc_label.setText(tr("upload.desc.label"))
        self.desc_caption.setText(tr("upload.desc.caption"))
        self.refresh_desc_button.setToolTip(tr("upload.desc.refresh"))

        self.options_title.setText(tr("upload.options.title"))
        self.disclaimer_checkbox.setText(tr("upload.disclaimer"))
        self.disclaimer_info_btn.setToolTip(tr("upload.disclaimer.tip"))
        self.frameset_checkbox.setText(tr("upload.frameset"))
        self.frameset_info_btn.setToolTip(tr("upload.frameset.tip"))

        self.upload_button.setText(tr("upload.button"))

    def resizeEvent(self, event):
        """Handle window resize to adjust card width dynamically"""
        super().resizeEvent(event)

        # Calculate available width (total width minus margins and stretches)
        available_width = self.width() - 80  # 40px margins on each side

        # Set card width to use ~85% of available width - don't be afraid to use space!
        target_width = int(available_width * 0.85)
        target_width = max(700, min(target_width, 1600))  # Clamp between 700-1600px

        if self.form_card:
            self.form_card.setFixedWidth(target_width)

    def _load_descriptions(self):
        """Load descriptions from database"""
        try:
            descriptions = self.description_manager.list_descriptions()
            self.description_combo.clear()
            self.description_combo.addItem(self.main.i18n.tr("upload.desc.select"))

            for desc in descriptions:
                self.description_combo.addItem(desc['name'])

            self.description_combo.setCurrentIndex(0)

        except Exception as e:
            InfoBar.error(
                title=self.main.i18n.tr("upload.load_failed.title"),
                content=self.main.i18n.tr("upload.load_failed.content", error=str(e)),
                parent=self,
                position=InfoBarPosition.TOP
            )

    def _on_brand_change(self, brand):
        """Handle brand selection change"""
        # Show frameset checkbox only for Pinarello
        is_pinarello = brand == "Pinarello"
        self.frameset_row.setVisible(is_pinarello)
        self._check_form_valid()

    def _on_code_changed(self, text):
        """Handle product code field change with validation"""
        self._check_form_valid()

    def _on_url_changed(self, text):
        """Handle URL field change with validation"""
        self._check_form_valid()

    def _on_description_changed(self, text):
        """Handle description dropdown change with validation"""
        self._check_form_valid()

    def _check_form_valid(self):
        """Check if form is valid and enable/disable upload button"""
        code = self.code_field.text().strip()
        url = self.url_field.text().strip()
        description = self.description_combo.currentText()

        # Description is optional - only check code and URL
        is_valid = bool(code and url)

        # Debug logging
        # Debug: Validation check and button state

        self.upload_button.setEnabled(is_valid)

        # Debug: Button enabled after and end of validation

    def _show_disclaimer_info(self):
        """Show disclaimer information"""
        InfoBar.info(
            title=self.main.i18n.tr("upload.disclaimer.info.title"),
            content=self.main.i18n.tr("upload.disclaimer.info.content"),
            parent=self,
            position=InfoBarPosition.TOP,
            duration=4000
        )

    def _handle_upload(self):
        """Handle upload button click"""
        if self.upload_worker and self.upload_worker.isRunning():
            InfoBar.warning(
                title=self.main.i18n.tr("upload.in_progress.title"),
                content=self.main.i18n.tr("upload.in_progress.content"),
                parent=self,
                position=InfoBarPosition.TOP
            )
            return

        # Get form data
        brand = self.brand_combo.currentText()
        code = self.code_field.text().strip()
        url = self.url_field.text().strip()
        description = self.description_combo.currentText()
        include_disclaimer = self.disclaimer_checkbox.isChecked()
        is_frameset = self.frameset_checkbox.isChecked() if self.frameset_row.isVisible() else False

        # Get uploader class
        try:
            uploader_class = getUploaderClass(brand)
        except ValueError as e:
            InfoBar.error(
                title=self.main.i18n.tr("upload.invalid_brand.title"),
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP
            )
            return

        # Create uploader instance
        try:
            uploader = uploader_class(
                driver=self.main.driver,
                db=self.main.db,
                settings_manager=self.main.settings,
                product_code=code,
                url_or_code=url,
                description_name=description,
                include_disclaimer=include_disclaimer,
                is_frameset=is_frameset if brand == "Pinarello" else None
            )
        except Exception as e:
            InfoBar.error(
                title=self.main.i18n.tr("upload.uploader_error.title"),
                content=self.main.i18n.tr("upload.uploader_error.content", error=str(e)),
                parent=self,
                position=InfoBarPosition.TOP
            )
            return

        # Start upload in background
        self.upload_worker = UploadWorker(uploader, self.main.i18n.tr)
        self.upload_worker.progress.connect(self._on_upload_progress)
        self.upload_worker.finished.connect(self._on_upload_finished)
        self.upload_worker.retry_request.connect(self._on_retry_request)

        # UI updates
        self.upload_button.setEnabled(False)
        self.progress_ring.setVisible(True)
        self.status_label.setText(self.main.i18n.tr("upload.status.uploading"))
        self.status_label.setStyleSheet(f"color: {COLORS['lavender_grey']};")

        self.upload_worker.start()

    def _on_retry_request(self, operation_name):
        # Show non-blocking Fluent dialog for retry with code entry
        if self._active_retry_dialog:
            self._active_retry_dialog.close()
        from qfluentwidgets import MessageBox
        from PySide6.QtWidgets import QLineEdit
        dialog = MessageBox(
            self.main.i18n.tr("upload.retry.title"),
            self.main.i18n.tr("upload.retry.content"),
            self
        )
        # Remove default content label and add input
        try:
            dialog.textLayout.removeWidget(dialog.contentLabel)
            dialog.contentLabel.deleteLater()
        except Exception:
            pass
        input_widget = QLineEdit()
        input_widget.setPlaceholderText(self.main.i18n.tr("upload.retry.placeholder"))
        input_widget.setMinimumWidth(420)
        input_widget.setStyleSheet(f"""
            background-color: {COLORS['lavender_grey']};
            color: #22223b;
            padding: 10px 12px;
            border-radius: 8px;
            font-size: 15px;
            font-family: {FONTS['family']};
            margin-top: 8px;
        """)
        dialog.textLayout.addWidget(input_widget)
        dialog.yesButton.setText(self.main.i18n.tr("upload.retry.yes"))
        dialog.cancelButton.setText(self.main.i18n.tr("upload.retry.cancel"))

        def _on_finished(result_code):
            from PySide6.QtWidgets import QDialog
            if result_code == QDialog.Accepted:
                new_code = input_widget.text().strip()
                if new_code:
                    self.upload_worker.retry_response.emit(new_code)
                else:
                    self.upload_worker.retry_response.emit(True)
            else:
                self.upload_worker.retry_response.emit(False)
            self._active_retry_dialog = None

        dialog.finished.connect(_on_finished)
        dialog.show()
        self._active_retry_dialog = dialog

    def _on_upload_progress(self, message):
        """Handle upload progress updates"""
        self.status_label.setText(message)

    def _on_upload_finished(self, success, message):
        """Handle upload completion"""
        self.progress_ring.setVisible(False)
        self.upload_button.setEnabled(True)

        if success:
            self.status_label.setText(message)
            self.status_label.setStyleSheet(f"color: {COLORS['success']};")

            InfoBar.success(
                title=self.main.i18n.tr("upload.success.title"),
                content=message,
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000
            )

            # Clear form
            self.code_field.clear()
            self.url_field.clear()
            self.description_combo.setCurrentIndex(0)
            self.disclaimer_checkbox.setChecked(False)
            self.frameset_checkbox.setChecked(False)

        else:
            self.status_label.setText(message)
            self.status_label.setStyleSheet(f"color: {COLORS['error']};")

            InfoBar.error(
                title=self.main.i18n.tr("upload.failed.title"),
                content=message,
                parent=self,
                position=InfoBarPosition.TOP,
                duration=5000
            )

    def _on_theme_changed(self):
        """Handle theme change event"""
        is_dark = isDarkTheme()
        bg_color = COLORS['space_indigo'] if is_dark else COLORS['platinum']

        self.setStyleSheet(f"""
            UploadScreen {{
                background-color: {bg_color};
                font-family: {FONTS['family']};
            }}
        """)

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
    """Background worker for upload process"""
    finished = Signal(bool, str)  # success, message
    progress = Signal(str)  # status updates

    def __init__(self, uploader):
        super().__init__()
        self.uploader = uploader

    def run(self):
        """Perform upload in background thread"""
        try:
            self.progress.emit("Starting upload...")
            self.uploader.run()
            self.finished.emit(True, "Upload completed successfully!")
        except Exception as e:
            self.finished.emit(False, f"Upload failed: {str(e)}")


class UploadScreen(QWidget):
    """Main upload screen with Fluent Design and responsive scaling"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
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

        title_label = TitleLabel("Upload Product")

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
        brand_label = BodyLabel("Brand")
        brand_label.setStyleSheet(f"font-weight: 500; color: {COLORS['text_secondary']};")
        brand_caption = CaptionLabel("Select the product manufacturer")
        brand_caption.setStyleSheet(f"color: {COLORS['text_tertiary']};")

        self.brand_combo = ComboBox()
        self.brand_combo.addItems(self.brands)
        self.brand_combo.currentTextChanged.connect(self._on_brand_change)

        form_grid.addWidget(brand_label, row, 0)
        form_grid.addWidget(brand_caption, row + 1, 0)
        form_grid.addWidget(self.brand_combo, row, 1)
        row += 2

        # Product code
        code_label = BodyLabel("Product Code")
        code_label.setStyleSheet(f"font-weight: 500; color: {COLORS['text_secondary']};")
        code_caption = CaptionLabel("Internal product identifier (e.g., UB-XXXX)")
        code_caption.setStyleSheet(f"color: {COLORS['text_tertiary']};")

        self.code_field = LineEdit()
        self.code_field.setPlaceholderText("UB-XXXX")
        self.code_field.textChanged.connect(self._on_code_changed)

        form_grid.addWidget(code_label, row, 0)
        form_grid.addWidget(code_caption, row + 1, 0)
        form_grid.addWidget(self.code_field, row, 1)
        row += 2

        # URL/Code input
        url_label = BodyLabel("Product URL or Code")
        url_label.setStyleSheet(f"font-weight: 500; color: {COLORS['text_secondary']};")
        url_caption = CaptionLabel("Manufacturer's product URL or code")
        url_caption.setStyleSheet(f"color: {COLORS['text_tertiary']};")

        self.url_field = LineEdit()
        self.url_field.setPlaceholderText("https://... or product code")
        self.url_field.textChanged.connect(self._on_url_changed)

        form_grid.addWidget(url_label, row, 0)
        form_grid.addWidget(url_caption, row + 1, 0)
        form_grid.addWidget(self.url_field, row, 1)
        row += 2

        # Description dropdown
        desc_label_row = QHBoxLayout()
        desc_label = BodyLabel("Description Template")
        desc_label.setStyleSheet(f"font-weight: 500; color: {COLORS['text_secondary']};")

        self.refresh_desc_button = TransparentToolButton(FluentIcon.SYNC, self)
        self.refresh_desc_button.setToolTip("Refresh descriptions")
        self.refresh_desc_button.setFixedSize(24, 24)
        self.refresh_desc_button.clicked.connect(self._load_descriptions)

        desc_label_row.addWidget(desc_label)
        desc_label_row.addWidget(self.refresh_desc_button)
        desc_label_row.addStretch()

        desc_caption = CaptionLabel("Select a description template")
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

        options_title = StrongBodyLabel("Upload Options")
        options_title.setStyleSheet(f"color: {COLORS['text_secondary']};")
        options_layout.addWidget(options_title)

        # Disclaimer checkbox
        disclaimer_row = QHBoxLayout()
        disclaimer_row.setSpacing(8)

        self.disclaimer_checkbox = CheckBox("Include disclaimer")
        disclaimer_info = TransparentToolButton(FluentIcon.INFO, self)
        disclaimer_info.setToolTip("Adds disclaimer text to product description")
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

        self.frameset_checkbox = CheckBox("Frameset only")
        frameset_info = TransparentToolButton(FluentIcon.INFO, self)
        frameset_info.setToolTip("Upload as frameset (Pinarello only)")
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

        self.upload_button = PrimaryPushButton("Upload Product")
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
            self.description_combo.addItem("Select description...")

            for desc in descriptions:
                self.description_combo.addItem(desc['name'])

            self.description_combo.setCurrentIndex(0)

        except Exception as e:
            InfoBar.error(
                title="Load Failed",
                content=f"Failed to load descriptions: {str(e)}",
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
        print(f"[UploadScreen] Validation check:")
        print(f"  Code: '{code}' (valid: {bool(code)})")
        print(f"  URL: '{url}' (valid: {bool(url)})")
        print(f"  Description: '{description}' (optional)")
        print(f"  Overall valid: {is_valid}")
        print(f"  Button enabled before: {self.upload_button.isEnabled()}")

        self.upload_button.setEnabled(is_valid)

        print(f"  Button enabled after: {self.upload_button.isEnabled()}")
        print()

    def _show_disclaimer_info(self):
        """Show disclaimer information"""
        InfoBar.info(
            title="Disclaimer Information",
            content="The disclaimer adds important legal and warranty information to the product description.",
            parent=self,
            position=InfoBarPosition.TOP,
            duration=4000
        )

    def _handle_upload(self):
        """Handle upload button click"""
        if self.upload_worker and self.upload_worker.isRunning():
            InfoBar.warning(
                title="Upload in Progress",
                content="Please wait for the current upload to complete",
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
                title="Invalid Brand",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP
            )
            return

        # Create uploader instance
        try:
            uploader = uploader_class(
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
                title="Uploader Error",
                content=f"Failed to create uploader: {str(e)}",
                parent=self,
                position=InfoBarPosition.TOP
            )
            return

        # Start upload in background
        self.upload_worker = UploadWorker(uploader)
        self.upload_worker.progress.connect(self._on_upload_progress)
        self.upload_worker.finished.connect(self._on_upload_finished)

        # UI updates
        self.upload_button.setEnabled(False)
        self.progress_ring.setVisible(True)
        self.status_label.setText("Uploading...")
        self.status_label.setStyleSheet(f"color: {COLORS['lavender_grey']};")

        self.upload_worker.start()

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
                title="Upload Successful",
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
                title="Upload Failed",
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

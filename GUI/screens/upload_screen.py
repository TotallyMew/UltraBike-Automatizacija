"""Upload screen component"""

import flet as ft
import threading
from uploaderFactory import getUploaderClass

class UploadScreen:
    def __init__(self, app):
        self.app = app
        self.page = app.page
    
    def build(self):
        """Build upload screen UI"""
        
        # Brand dropdown
        self.brand_dropdown = ft.Dropdown(
            label="Pasirinkite tiekėją",
            width=300,
            options=[
                ft.dropdown.Option("KROSS"),
                ft.dropdown.Option("Pinarello"),
                ft.dropdown.Option("Basso"),
                ft.dropdown.Option("Factor"),
                ft.dropdown.Option("LeeCougan"),
                ft.dropdown.Option("Rascal"),
                ft.dropdown.Option("Rondo"),
                ft.dropdown.Option("Octane"),
            ],
            on_change=self.handle_brand_change
        )
        
        # Product code input
        self.product_code_input = ft.TextField(
            label="Produkto kodas (UB-XXX)",
            width=300,
            hint_text="UB-XXXX",
            on_change=lambda e: self.check_upload_ready()
        )
        
        # URL input
        self.url_input = ft.TextField(
            label="URL arba kodas",
            width=500,
            hint_text="https://... arba konfigūracijos kodas",
            on_change=lambda e: self.check_upload_ready()
        )
        
        # Brand-specific options container
        self.brand_options_container = ft.Column([], visible=False)
        
        # Upload button
        self.upload_button = ft.ElevatedButton(
            "Įkelti dviratį",
            icon=ft.Icons.UPLOAD,
            on_click=self.handle_upload,
            width=300,
            disabled=True
        )
        
        # Progress indicator
        self.upload_progress = ft.ProgressRing(visible=False)
        
        # Status text
        self.upload_status = ft.Text("", size=14, width=600)
        
        # Build layout
        return ft.Column(
            [
                ft.Text("Dviračio Įkėlimas", size=24, weight=ft.FontWeight.BOLD),
                ft.Container(height=20),
                
                # Form fields
                self.brand_dropdown,
                ft.Container(height=10),
                self.product_code_input,
                ft.Container(height=10),
                self.url_input,
                ft.Container(height=10),
                
                # Brand-specific options
                self.brand_options_container,
                
                ft.Container(height=20),
                
                # Upload controls
                ft.Row([self.upload_button, self.upload_progress], spacing=20),
                
                ft.Container(height=10),
                self.upload_status
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True
        )
    
    def handle_brand_change(self, e):
        """Handle brand selection change"""
        brand = self.brand_dropdown.value
        
        # Clear brand-specific options
        self.brand_options_container.controls.clear()
        self.brand_options_container.visible = False
        
        # Add brand-specific options
        if brand == "Pinarello":
            self.pinarello_frameset_checkbox = ft.Checkbox(
                label="Tik frameset (Rėmas, Šakė, Balnakotis, Užspaustukas)",
                value=False
            )
            self.brand_options_container.controls.append(self.pinarello_frameset_checkbox)
            self.brand_options_container.visible = True
        
        elif brand == "Rascal":
            self.rascal_variant_note = ft.Text(
                "Jei yra keli variantai, bus paprašyta pasirinkti",
                size=12,
                color=ft.Colors.GREY_600
            )
            self.brand_options_container.controls.append(self.rascal_variant_note)
            self.brand_options_container.visible = True
        
        self.check_upload_ready()
        self.page.update()
    
    def check_upload_ready(self):
        """Check if all required fields are filled"""
        has_brand = self.brand_dropdown.value is not None
        has_code = len(self.product_code_input.value or "") > 0
        has_url = len(self.url_input.value or "") > 0
        
        self.upload_button.disabled = not (has_brand and has_code and has_url)
        self.page.update()
    
    def handle_upload(self, e):
        """Handle upload button click"""
        
        # Get values
        brand = self.brand_dropdown.value
        product_code = self.product_code_input.value.strip()
        url = self.url_input.value.strip()
        
        # Get brand-specific options
        brand_options = {}
        if brand == "Pinarello" and hasattr(self, 'pinarello_frameset_checkbox'):
            brand_options['frameset_only'] = self.pinarello_frameset_checkbox.value
        
        # Show progress
        self.upload_button.disabled = True
        self.upload_progress.visible = True
        self.upload_status.value = f"Apdorojamas {brand} dviratis..."
        self.upload_status.color = ft.Colors.BLUE
        self.page.update()
        
        # Process in background thread
        thread = threading.Thread(
            target=self.process_bike,
            args=(brand, product_code, url, brand_options)
        )
        thread.start()
    
    def process_bike(self, brand, product_code, url, brand_options):
        """Process bike upload (runs in background)"""
        try:
            # Get uploader class
            uploader_class = getUploaderClass(brand)
        
            if uploader_class is None:
                self.update_upload_status(
                    f"✗ Nežinomas tiekėjas: {brand}",
                    ft.Colors.RED,
                    False
                )
                return
        
            # Create uploader with brand_options
            uploader = uploader_class(
                self.app.driver,
                brand.upper(),
                ultraBikeCode=product_code,
                bicycleUrlOrCode=url,
                db_manager=self.app.db,
                brand_options=brand_options  # ← Add this parameter
            )
        
            # Update status
            self.update_upload_status("⏳ Scraping...", ft.Colors.BLUE, True)
        
            # Run upload
            uploader.run()
        
            # Success
            self.update_upload_status(
                f"✓ {brand} dviratis {product_code} sėkmingai įkeltas!",
                ft.Colors.GREEN,
                False
            )
        
            # Clear form
            self.clear_upload_form()
        
        except Exception as ex:
            # Error
            error_msg = str(ex)
            if "load_translations" in error_msg:
                error_msg = "Scraper klaida (Phase 2 refactoring nebaigtas)"
        
            self.update_upload_status(
                f"✗ Klaida: {error_msg}",
                ft.Colors.RED,
                False
            )
    
    def update_upload_status(self, message, color, show_progress):
        """Update upload status"""
        self.upload_status.value = message
        self.upload_status.color = color
        self.upload_progress.visible = show_progress
        self.upload_button.disabled = show_progress
        self.page.update()

    def clear_upload_form(self):
        """Clear form after successful upload"""
        self.product_code_input.value = ""
        self.url_input.value = ""
        self.check_upload_ready()
        self.page.update()
"""Upload screen with integrated description selection"""

import flet as ft
import threading
import re
from uploaderFactory import getUploaderClass
from Managers.DescriptionManager import DescriptionManager

class UploadScreen:
    def __init__(self, app):
        self.app = app
        self.page = app.page
        self.desc_manager = DescriptionManager(app.db, app.logger if hasattr(app, 'logger') else None)
    
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
        
        # Description selection
        self.description_dropdown = ft.Dropdown(
            label="Aprašymas (optional)",
            width=400,
            hint_text="Pasirinkite aprašymą arba palikite tuščią",
            options=[]
        )
        
        self.refresh_descriptions_button = ft.IconButton(
            icon=ft.Icons.REFRESH,
            tooltip="Atnaujinti aprašymų sąrašą",
            on_click=lambda e: self.load_descriptions_list()
        )
        
        self.clear_description_button = ft.IconButton(
            icon=ft.Icons.CLEAR,
            tooltip="Išvalyti pasirinkimą",
            on_click=lambda e: self.clear_description_selection()
        )

        # Disclaimer checkbox and info button
        self.disclaimer_checkbox = ft.Checkbox(
            label="Append color disclaimer",
            value=False
        )

        self.disclaimer_info_button = ft.IconButton(
            icon=ft.Icons.INFO_OUTLINE,
            tooltip="Preview disclaimer",
            on_click=lambda e: self.show_disclaimer_preview()
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

        # Load descriptions on startup (don't update page during build)
        self.load_descriptions_list(update_page=False)

        # Build layout
        self.screen_content = ft.Column(
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
                
                # Description selection
                ft.Row([
                    self.description_dropdown,
                    self.refresh_descriptions_button,
                    self.clear_description_button
                ], spacing=5),
                ft.Text(
                    "Aprašymas bus įkeltas automatiškai prieš savybes",
                    size=12,
                    color=ft.Colors.GREY_600
                ),
                ft.Container(height=10),

                # Disclaimer checkbox
                ft.Row([
                    self.disclaimer_checkbox,
                    self.disclaimer_info_button
                ], spacing=5),
                ft.Text(
                    "Adds disclaimer about color accuracy to description",
                    size=12,
                    color=ft.Colors.GREY_600
                ),
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
        return self.screen_content
    
    def show_disclaimer_preview(self):
        """Show disclaimer preview dialog"""

        # Strip HTML tags for preview
        def strip_html(html):
            return re.sub(r'<[^>]+>', '', html)

        lt_text = strip_html(self.desc_manager.DISCLAIMER_LT)
        en_text = strip_html(self.desc_manager.DISCLAIMER_EN)
        lv_text = strip_html(self.desc_manager.DISCLAIMER_LV)

        dialog = ft.AlertDialog(
            title=ft.Text("Color Disclaimer Preview"),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text("Lithuanian:", weight=ft.FontWeight.BOLD),
                        ft.Text(lt_text, size=12, italic=True),
                        ft.Container(height=10),

                        ft.Text("English:", weight=ft.FontWeight.BOLD),
                        ft.Text(en_text, size=12, italic=True),
                        ft.Container(height=10),

                        ft.Text("Latvian:", weight=ft.FontWeight.BOLD),
                        ft.Text(lv_text, size=12, italic=True),
                    ],
                    scroll=ft.ScrollMode.AUTO
                ),
                width=500,
                height=400
            ),
            actions=[
                ft.TextButton("Close", on_click=lambda e: self.page.close(dialog))
            ]
        )

        self.page.open(dialog)

    def load_descriptions_list(self, update_page=True):
        """Load available descriptions from database"""
        try:
            descriptions = self.desc_manager.list_descriptions()

            # Update dropdown options
            self.description_dropdown.options = [
                ft.dropdown.Option(desc['name']) for desc in descriptions
            ]

            if update_page:
                self.page.update()

        except Exception as e:
            print(f"Failed to load descriptions: {e}")
    

    #FLET BUG WORKAROUND - cannot clear dropdown selection directly
    def clear_description_selection(self):
        """Clear description dropdown selection"""
        # Get current descriptions
        try:
            descriptions = self.desc_manager.list_descriptions()
        except:
            descriptions = []
        
        # Create new dropdown with empty value
        new_dropdown = ft.Dropdown(
            label="Aprašymas (optional)",
            width=400,
            hint_text="Pasirinkite aprašymą arba palikite tuščią",
            options=[
                ft.dropdown.Option(desc['name']) for desc in descriptions
            ],
            value=None  # Empty, shows hint text
        )
        
        description_row = self.screen_content.controls[8]
        
        # Replace the dropdown widget
        description_row.controls[0] = new_dropdown
        self.description_dropdown = new_dropdown
        
        self.page.update()
    
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
        description_name = self.description_dropdown.value  # Can be None
        append_disclaimer = self.disclaimer_checkbox.value

        print(f"DEBUG UploadScreen: brand={brand}, code={product_code}, description={description_name}, disclaimer={append_disclaimer}")

        # Get brand-specific options
        brand_options = {}
        if brand == "Pinarello" and hasattr(self, 'pinarello_frameset_checkbox'):
            brand_options['frameset_only'] = self.pinarello_frameset_checkbox.value

        # Add description and disclaimer to brand_options
        if description_name:
            brand_options['description_name'] = description_name
            print(f"DEBUG UploadScreen: Added description to brand_options: {description_name}")

        brand_options['append_disclaimer'] = append_disclaimer
        print(f"DEBUG UploadScreen: Added disclaimer flag: {append_disclaimer}")

        print(f"DEBUG UploadScreen: brand_options = {brand_options}")
        
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
                brand_options=brand_options,
                logger=self.app.logger if hasattr(self.app, 'logger') else None
            )
        
            # Update status
            self.update_upload_status("⏳ Scraping...", ft.Colors.BLUE, True)
        
            # Run upload (includes description if provided)
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
        self.description_dropdown.value = None
        self.disclaimer_checkbox.value = False
        self.check_upload_ready()
        self.page.update()
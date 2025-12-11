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

        self.batch_button = ft.ElevatedButton(
            "Batch Upload",
            icon=ft.Icons.PLAYLIST_ADD,
            on_click=self.show_batch_modal,
            width=300
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
                
            ft.Row([self.upload_button, self.batch_button], spacing=20),  # ← Add batch_button here
            ft.Row([self.upload_progress], spacing=20),

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
                brand_options=brand_options,  # ← Add this parameter
                logger=self.app.logger
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

    def show_batch_modal(self, e):
        """Show batch upload modal"""
        from GUI.screens.batch_upload_screen import BatchUploadScreen
    
        def on_close():
            self.page.close(batch_modal)
    
        batch_screen = BatchUploadScreen(self.app, on_close)
        batch_modal = batch_screen.build()
    
        self.page.open(batch_modal)




    def show_batch_processing(self, items):
        """Show batch processing UI and start processing"""
        from Utilities.BatchProcessor import BatchProcessor
        from uploaderFactory import getUploaderClass
    
        # Clear existing content
        self.batch_queue = items
        self.batch_results = []
    
        # Create batch processor
        self.batch_processor = BatchProcessor(
            self.app.driver,
            self.app.db,
            logger=None  # Add logger if available
        )
    
        # Add items to queue
        for item in items:
            self.batch_processor.add_to_queue(
                item['brand'],
                item['code'],
                item['url']
            )
    
        # Build processing UI
        self.build_batch_processing_ui()
    
        # Start processing in background thread
        def process():
            def uploader_factory(driver, brand, code, url, db, batch_id):
                uploader_class = getUploaderClass(brand)
                return uploader_class(
                    driver,
                    brand.upper(),
                    ultraBikeCode=code,
                    bicycleUrlOrCode=url,
                    db_manager=db,
                    batch_id=batch_id
                )
        
            try:
                results = self.batch_processor.start_batch(uploader_factory)
                self.on_batch_complete(results)
            except Exception as e:
                self.on_batch_error(str(e))
    
        import threading
        thread = threading.Thread(target=process, daemon=True)
        thread.start()

    def build_batch_processing_ui(self):
        """Build UI for batch processing progress"""
    
        # Progress bar
        self.batch_progress_bar = ft.ProgressBar(width=600, value=0)
    
        # Status text
        self.batch_status_text = ft.Text(
            "Processing batch...",
            size=16,
            weight=ft.FontWeight.BOLD
        )
    
        # Current item text
        self.batch_current_text = ft.Text("", size=14)
    
        # Results list
        self.batch_results_list = ft.Column([], scroll=ft.ScrollMode.AUTO)
    
        # Stop button
        self.batch_stop_button = ft.ElevatedButton(
            "Stop After Current",
            icon=ft.Icons.STOP,
            on_click=self.handle_stop_batch,
            bgcolor=ft.Colors.RED_700,
            color=ft.Colors.WHITE
        )
    
        # Replace upload screen content with batch processing UI
        batch_ui = ft.Column(
            [
                ft.Text("Batch Processing", size=24, weight=ft.FontWeight.BOLD),
                ft.Container(height=20),
                self.batch_status_text,
                self.batch_current_text,
                ft.Container(height=10),
                self.batch_progress_bar,
                ft.Container(height=10),
                self.batch_stop_button,
                ft.Container(height=20),
                ft.Text("Results:", size=18, weight=ft.FontWeight.BOLD),
                ft.Container(height=10),
                ft.Container(
                    content=self.batch_results_list,
                    height=300,
                    border=ft.border.all(1, ft.Colors.GREY_300),
                    border_radius=5,
                    padding=10
                )
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True
        )
    
        # Update content area
        self.app.content_area.content = batch_ui
        self.page.update()
    
        # Start progress updater
        self.start_progress_updater()

    def start_progress_updater(self):
        """Update progress bar periodically"""
        import threading
        import time
    
        def update():
            while self.batch_processor.is_processing:
                current, total, percentage = self.batch_processor.get_progress()
            
                # Update UI on main thread
                self.batch_progress_bar.value = percentage / 100
                self.batch_status_text.value = f"Processing {current}/{total} bikes"
            
                # Show current item
                if current < len(self.batch_queue):
                    item = self.batch_queue[current]
                    self.batch_current_text.value = f"Current: {item['brand']} - {item['code']}"
            
                # Update results list
                self.update_results_list()
            
                self.page.update()
                time.sleep(0.5)
    
        thread = threading.Thread(target=update, daemon=True)
        thread.start()

    def update_results_list(self):
        """Update batch results list"""
        self.batch_results_list.controls.clear()
    
        for result in self.batch_processor.get_results():
            status_icon = "✓" if result['status'] == 'success' else "✗"
            status_color = ft.Colors.GREEN if result['status'] == 'success' else ft.Colors.RED
        
            result_row = ft.Row(
                [
                    ft.Text(status_icon, size=20, color=status_color, width=30),
                    ft.Text(f"{result['brand']} - {result['code']}", size=14, width=300),
                    ft.Text(
                        result['error'] if result['error'] else "Success",
                        size=12,
                        color=ft.Colors.RED_700 if result['error'] else ft.Colors.GREEN_700,
                        expand=True
                    )
                ]
            )
        
            self.batch_results_list.controls.append(result_row)

    def handle_stop_batch(self, e):
        """Stop batch processing after current item"""
        self.batch_processor.stop_batch()
        self.batch_stop_button.disabled = True
        self.page.update()

    def on_batch_complete(self, results):
        """Called when batch processing completes"""
        self.batch_status_text.value = f"✓ Batch Complete: {results['success']} succeeded, {results['failed']} failed"
        self.batch_status_text.color = ft.Colors.GREEN
        self.batch_stop_button.disabled = True
        self.batch_progress_bar.value = 1.0
    
        # Add export failed button if there are failures
        if results['failed'] > 0:
            export_button = ft.ElevatedButton(
                "Export Failed Items",
                icon=ft.Icons.DOWNLOAD,
                on_click=self.handle_export_failed
            )
            self.batch_results_list.controls.append(
                ft.Container(
                    content=export_button,
                    padding=ft.padding.only(top=20)
                )
            )
    
        self.page.update()

    def on_batch_error(self, error):
        """Called when batch processing errors"""
        self.batch_status_text.value = f"✗ Batch Error: {error}"
        self.batch_status_text.color = ft.Colors.RED
        self.batch_stop_button.disabled = True
        self.page.update()

    def handle_export_failed(self, e):
        """Export failed items to Excel"""
        from tkinter import Tk
        from tkinter.filedialog import asksaveasfilename
        import openpyxl
        from datetime import datetime
    
        failed_items = self.batch_processor.get_failed_items()
    
        if not failed_items:
            return
    
        # Open save dialog
        root = Tk()
        root.withdraw()
        root.attributes('-topmost', True)
    
        filename = asksaveasfilename(
            title="Export Failed Items",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            initialfile=f"failed_items_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )
    
        root.destroy()
    
        if filename:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Failed Items"
        
            # Headers
            ws.append(["Brand", "Product Code", "Error"])
        
            # Data
            for item in failed_items:
                ws.append([item['brand'], item['code'], item['error']])
        
            wb.save(filename)
            wb.close()
        
            # Show success
            self.batch_status_text.value += f" | Exported to {filename}"
            self.page.update()

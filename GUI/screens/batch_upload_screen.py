"""Batch upload screen - modal for uploading multiple bikes"""

import flet as ft
import openpyxl
from tkinter import Tk
from tkinter.filedialog import askopenfilename, asksaveasfilename
import threading
from Utilities.BatchProcessor import BatchProcessor
from uploaderFactory import getUploaderClass

class BatchUploadScreen:
    def __init__(self, app, on_close):
        self.app = app
        self.page = app.page
        self.on_close_callback = on_close
        self.batch_processor = None
        self.is_processing = False
    
    def build(self):
        """Build batch upload modal"""
        
        # Tab selection
        self.tab_bar = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            tabs=[
                ft.Tab(text="Manual Entry", icon=ft.Icons.EDIT),
                ft.Tab(text="Excel Upload", icon=ft.Icons.UPLOAD_FILE),
            ],
            on_change=self.handle_tab_change,
            expand=True
        )
        
        # Manual entry content
        self.manual_content = self.build_manual_entry()
        
        # Excel upload content
        self.excel_content = self.build_excel_upload()
        
        # Content area (switches based on tab)
        self.content_area = ft.Container(
            content=self.manual_content,
            padding=20,
            expand=True
        )
        
        # Bottom buttons
        self.start_button = ft.ElevatedButton(
            "Start Batch Upload",
            icon=ft.Icons.PLAY_ARROW,
            on_click=self.handle_start_batch,
            disabled=True
        )
        
        self.cancel_button = ft.TextButton(
            "Cancel",
            on_click=lambda e: self.on_close_callback()
        )
        
        # Modal dialog
        return ft.AlertDialog(
            modal=True,
            title=ft.Text("Batch Upload", size=20, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column(
                    [
                        self.tab_bar,
                        ft.Divider(),
                        self.content_area
                    ],
                    spacing=0,
                    expand=True
                ),
                width=800,
                height=500
            ),
            actions=[
                self.cancel_button,
                self.start_button
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )
    
    def handle_tab_change(self, e):
        """Switch between manual entry and excel upload"""
        if e.control.selected_index == 0:
            self.content_area.content = self.manual_content
        else:
            self.content_area.content = self.excel_content
        self.page.update()
    
    def build_manual_entry(self):
        """Build manual entry table"""
        
        # Table header
        header = ft.Row(
            [
                ft.Text("Brand", width=150, weight=ft.FontWeight.BOLD),
                ft.Text("Product Code", width=150, weight=ft.FontWeight.BOLD),
                ft.Text("URL or Code", width=350, weight=ft.FontWeight.BOLD),
                ft.Text("", width=50)  # Delete button column
            ],
            spacing=10
        )
        
        # Rows container
        self.manual_rows = ft.Column([], spacing=10, scroll=ft.ScrollMode.AUTO)
        
        # Add initial 10 rows
        for i in range(10):
            self.add_manual_row()
        
        # Add row button
        add_button = ft.ElevatedButton(
            "Add Row",
            icon=ft.Icons.ADD,
            on_click=lambda e: self.add_manual_row()
        )
        
        # Clear all button
        clear_button = ft.TextButton(
            "Clear All",
            icon=ft.Icons.CLEAR,
            on_click=lambda e: self.clear_manual_rows()
        )
        
        return ft.Column(
            [
                header,
                ft.Divider(),
                ft.Container(content=self.manual_rows, height=300, expand=True),
                ft.Row([add_button, clear_button], spacing=10)
            ],
            spacing=10
        )
    
    def add_manual_row(self):
        """Add a single row to manual entry table"""
        
        brand_dropdown = ft.Dropdown(
            width=150,
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
            on_change=lambda e: self.validate_manual_entry()
        )
        
        code_field = ft.TextField(
            width=150,
            hint_text="UB-XXXX",
            on_change=lambda e: self.validate_manual_entry()
        )
        
        url_field = ft.TextField(
            width=350,
            hint_text="https://... or config code",
            on_change=lambda e: self.validate_manual_entry()
        )
        
        delete_button = ft.IconButton(
            icon=ft.Icons.DELETE,
            icon_color=ft.Colors.RED,
            tooltip="Remove row",
            on_click=lambda e: self.remove_manual_row(row)
        )
        
        row = ft.Row(
            [brand_dropdown, code_field, url_field, delete_button],
            spacing=10
        )
        
        self.manual_rows.controls.append(row)
        self.page.update()
    
    def remove_manual_row(self, row):
        """Remove a row from manual entry table"""
        self.manual_rows.controls.remove(row)
        self.validate_manual_entry()
        self.page.update()
    
    def clear_manual_rows(self):
        """Clear all manual entry rows"""
        self.manual_rows.controls.clear()
        for i in range(10):
            self.add_manual_row()
        self.validate_manual_entry()
        self.page.update()
    
    def validate_manual_entry(self):
        """Check if manual entry has valid data"""
        valid_rows = 0
        
        for row in self.manual_rows.controls:
            brand = row.controls[0].value
            code = row.controls[1].value
            url = row.controls[2].value
            
            if brand and code and url:
                valid_rows += 1
        
        self.start_button.disabled = valid_rows == 0
        self.page.update()
    
    def build_excel_upload(self):
        """Build excel upload interface"""
        
        # File picker display
        self.excel_filename = ft.Text("No file selected", size=14, color=ft.Colors.GREY_600)
        
        # Browse button
        browse_button = ft.ElevatedButton(
            "Browse Excel File",
            icon=ft.Icons.FOLDER_OPEN,
            on_click=self.handle_browse_excel
        )
        
        # Download template button
        template_button = ft.TextButton(
            "Download Template",
            icon=ft.Icons.DOWNLOAD,
            on_click=self.handle_download_template
        )
        
        # Preview table
        self.excel_preview = ft.Column([], scroll=ft.ScrollMode.AUTO)
        
        # Validation status
        self.excel_status = ft.Text("", size=14)
        
        return ft.Column(
            [
                ft.Row([browse_button, template_button], spacing=10),
                ft.Container(height=10),
                self.excel_filename,
                ft.Container(height=10),
                ft.Text("Preview:", weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=self.excel_preview,
                    height=300,
                    border=ft.border.all(1, ft.Colors.GREY_300),
                    border_radius=5,
                    padding=10
                ),
                ft.Container(height=10),
                self.excel_status
            ],
            spacing=5
        )
    
    def handle_browse_excel(self, e):
        """Open file picker for Excel file"""
        root = Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        filename = askopenfilename(
            title="Select Excel File",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")]
        )
        
        root.destroy()
        
        if filename:
            self.excel_filename.value = filename
            self.load_excel_preview(filename)
        
        self.page.update()
    
    def load_excel_preview(self, filename):
        """Load and preview Excel file"""
        try:
            wb = openpyxl.load_workbook(filename)
            ws = wb.active
            
            # Clear preview
            self.excel_preview.controls.clear()
            
            # Find header row (first row with "Brand", "Product Code", "URL")
            header_row = None
            for idx, row in enumerate(ws.iter_rows(min_row=1, max_row=5), start=1):
                row_values = [str(cell.value).lower() if cell.value else "" for cell in row]
                if any("brand" in val for val in row_values) and \
                   any("code" in val or "product" in val for val in row_values):
                    header_row = idx
                    break
            
            if not header_row:
                self.excel_status.value = "⚠ Could not find header row (Brand, Product Code, URL)"
                self.excel_status.color = ft.Colors.ORANGE
                self.start_button.disabled = True
                self.page.update()
                return
            
            # Parse data
            valid_count = 0
            invalid_count = 0
            
            for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
                if not any(row):  # Skip empty rows
                    continue
                
                brand = str(row[0]) if len(row) > 0 and row[0] else ""
                code = str(row[1]) if len(row) > 1 and row[1] else ""
                url = str(row[2]) if len(row) > 2 and row[2] else ""
                
                # Validate
                is_valid = bool(brand and code and url)
                
                if is_valid:
                    valid_count += 1
                    row_color = ft.Colors.GREEN_50
                    status_icon = "✓"
                else:
                    invalid_count += 1
                    row_color = ft.Colors.RED_50
                    status_icon = "✗"
                
                # Add to preview
                preview_row = ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(status_icon, width=30),
                            ft.Text(brand, width=150),
                            ft.Text(code, width=150),
                            ft.Text(url, width=350)
                        ],
                        spacing=10
                    ),
                    bgcolor=row_color,
                    padding=5,
                    border_radius=3
                )
                
                self.excel_preview.controls.append(preview_row)
            
            # Update status
            if invalid_count > 0:
                self.excel_status.value = f"⚠ {valid_count} valid, {invalid_count} invalid rows. Fix invalid rows before starting."
                self.excel_status.color = ft.Colors.ORANGE
                self.start_button.disabled = True
            else:
                self.excel_status.value = f"✓ {valid_count} valid rows ready to upload"
                self.excel_status.color = ft.Colors.GREEN
                self.start_button.disabled = False
            
            wb.close()
            self.page.update()
            
        except Exception as ex:
            self.excel_status.value = f"✗ Error reading file: {str(ex)}"
            self.excel_status.color = ft.Colors.RED
            self.start_button.disabled = True
            self.page.update()
    
    def handle_download_template(self, e):
        """Download Excel template"""
        root = Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        filename = asksaveasfilename(
            title="Save Template As",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            initialfile="ultrabike_batch_template.xlsx"
        )
        
        root.destroy()
        
        if filename:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Batch Upload"
            
            # Header row
            ws.append(["Brand", "Product Code", "URL or Code"])
            
            # Example rows
            ws.append(["KROSS", "UB-1234", "https://kross.pl/..."])
            ws.append(["Pinarello", "UB-5678", "https://pinarello.com/..."])
            ws.append(["Basso", "UB-9012", "CONFIG-ABC-123"])
            
            # Style header
            from openpyxl.styles import Font, PatternFill
            for cell in ws[1]:
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
            
            wb.save(filename)
            wb.close()
            
            # Show success message
            self.excel_status.value = f"✓ Template saved to {filename}"
            self.excel_status.color = ft.Colors.GREEN
            self.page.update()
    
    def handle_start_batch(self, e):
        """Start batch processing"""
        # Collect items from active tab
        items = []
        
        if self.tab_bar.selected_index == 0:
            # Manual entry
            for row in self.manual_rows.controls:
                brand = row.controls[0].value
                code = row.controls[1].value
                url = row.controls[2].value
                
                if brand and code and url:
                    items.append({
                        'brand': brand,
                        'code': code,
                        'url': url
                    })
        else:
            # Excel upload
            filename = self.excel_filename.value
            if filename and filename != "No file selected":
                wb = openpyxl.load_workbook(filename)
                ws = wb.active
                
                # Find header row
                header_row = 1
                for idx, row in enumerate(ws.iter_rows(min_row=1, max_row=5), start=1):
                    row_values = [str(cell.value).lower() if cell.value else "" for cell in row]
                    if any("brand" in val for val in row_values):
                        header_row = idx
                        break
                
                # Parse rows
                for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
                    if not any(row):
                        continue
                    
                    brand = str(row[0]) if len(row) > 0 and row[0] else ""
                    code = str(row[1]) if len(row) > 1 and row[1] else ""
                    url = str(row[2]) if len(row) > 2 and row[2] else ""
                    
                    if brand and code and url:
                        items.append({
                            'brand': brand,
                            'code': code,
                            'url': url
                        })
                
                wb.close()
        
        if not items:
            return
        
        # Close modal and start processing
        self.on_close_callback()
        self.app.start_batch_processing(items)
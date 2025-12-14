"""
GUI/screens/descriptions_screen.py
Description editor with WYSIWYG HTML editing
"""

import flet as ft
from Managers.DescriptionManager import DescriptionManager
from Utilities.ProductNavigationHandler import ProductNavigationHandler

class DescriptionsScreen:
    def __init__(self, app):
        self.app = app
        self.page = app.page
        self.desc_manager = DescriptionManager(app.db, app.logger if hasattr(app, 'logger') else None)
        self.current_description_name = None
        
        # Track editor content
        self.lt_content = ""
        self.en_content = ""
        self.lv_content = ""
    
    def build(self):
        """Build descriptions screen UI"""
        
        # Top toolbar
        self.save_button = ft.ElevatedButton(
            "Save Description",
            icon=ft.Icons.SAVE,
            on_click=self.handle_save,
            disabled=True
        )
        
        self.load_button = ft.ElevatedButton(
            "Load Description",
            icon=ft.Icons.FOLDER_OPEN,
            on_click=self.handle_load
        )
        
        self.new_button = ft.ElevatedButton(
            "New Description",
            icon=ft.Icons.ADD,
            on_click=self.handle_new
        )
        
        self.delete_button = ft.ElevatedButton(
            "Delete",
            icon=ft.Icons.DELETE,
            on_click=self.handle_delete,
            disabled=True
        )
        
        self.upload_button = ft.ElevatedButton(
            "Upload to PrestaShop",
            icon=ft.Icons.UPLOAD,
            on_click=self.handle_upload,
            disabled=True
        )
        
        # Status text
        self.status_text = ft.Text("", size=14)
        
        # Current description name display
        self.name_display = ft.Text("", size=16, weight=ft.FontWeight.BOLD)
        
        # Language tabs with HTML editors
        self.lt_editor = self.create_html_editor('lt')
        self.en_editor = self.create_html_editor('en')
        self.lv_editor = self.create_html_editor('lv')
        
        self.tabs = ft.Tabs(
            selected_index=0,
            tabs=[
                ft.Tab(
                    text="Lietuvių",
                    icon=ft.Icons.EDIT,
                    content=self.lt_editor
                ),
                ft.Tab(
                    text="English",
                    icon=ft.Icons.EDIT,
                    content=self.en_editor
                ),
                ft.Tab(
                    text="Latviešu",
                    icon=ft.Icons.EDIT,
                    content=self.lv_editor
                ),
            ],
            expand=True
        )
        
        # Layout
        return ft.Column(
            [
                ft.Text("Aprašymų Redaktorius", size=24, weight=ft.FontWeight.BOLD),
                ft.Container(height=10),
                
                # Toolbar
                ft.Row(
                    [
                        self.new_button,
                        self.save_button,
                        self.load_button,
                        self.delete_button,
                        ft.VerticalDivider(),
                        self.upload_button
                    ],
                    spacing=10
                ),
                
                ft.Container(height=5),
                self.name_display,
                self.status_text,
                ft.Container(height=10),
                
                # Editors
                self.tabs
            ],
            expand=True
        )
    
    def create_html_editor(self, lang_code: str):
        """Create HTML textarea editor"""
        
        # HTML textarea
        html_textarea = ft.TextField(
            multiline=True,
            min_lines=25,
            max_lines=25,
            hint_text="Paste HTML here (e.g., <h1>Title</h1>, <p>Text</p>)...",
            on_change=lambda e: self.store_content(lang_code, e.control.value),
            expand=True,
            text_style=ft.TextStyle(font_family="Courier New", size=12)
        )
        
        # Store reference
        if lang_code == 'lt':
            self.lt_textarea = html_textarea
        elif lang_code == 'en':
            self.en_textarea = html_textarea
        elif lang_code == 'lv':
            self.lv_textarea = html_textarea
        
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.WARNING_AMBER, color=ft.Colors.ORANGE, size=20),
                            ft.Text(
                                "HTML only - paste from SVENG.txt, SVLT.txt, SVLV.txt",
                                size=12,
                                color=ft.Colors.ORANGE_700,
                                weight=ft.FontWeight.BOLD
                            )
                        ],
                        spacing=5
                    ),
                    html_textarea
                ],
                spacing=5
            ),
            padding=10,
            border=ft.border.all(1, ft.Colors.GREY_400),
            border_radius=5,
            expand=True
        )
    
    def store_content(self, lang_code: str, content: str):
        """Store content when user types"""
        if lang_code == 'lt':
            self.lt_content = content
        elif lang_code == 'en':
            self.en_content = content
        elif lang_code == 'lv':
            self.lv_content = content
        
        # Enable save button
        self.save_button.disabled = False
    
    def handle_new(self, e):
        """Create new description"""
        self.current_description_name = None
        self.name_display.value = "New Description (not saved)"
        
        # Clear content
        self.lt_content = ""
        self.en_content = ""
        self.lv_content = ""
        
        # Clear textareas
        self.lt_textarea.value = ""
        self.en_textarea.value = ""
        self.lv_textarea.value = ""
        
        # Update buttons
        self.save_button.disabled = False
        self.delete_button.disabled = True
        self.upload_button.disabled = True
        
        self.show_status("New description created", ft.Colors.GREEN)
        self.page.update()
    
    def handle_save(self, e):
        """Save current description"""
        
        # Prompt for name if new
        if not self.current_description_name:
            self.show_save_dialog()
        else:
            self.save_description(self.current_description_name)
    
    def show_save_dialog(self):
        """Show dialog to enter description name"""
        
        name_field = ft.TextField(
            label="Description Name",
            hint_text="e.g., Basso SV, KROSS Esker",
            width=300,
            autofocus=True
        )
        
        def save_clicked(e):
            name = name_field.value.strip()
            if not name:
                self.show_status("Name cannot be empty", ft.Colors.RED)
                return
            
            # Close dialog
            self.page.close(dialog)
            
            # Save
            self.save_description(name)
        
        def cancel_clicked(e):
            self.page.close(dialog)
        
        dialog = ft.AlertDialog(
            title=ft.Text("Save Description"),
            content=ft.Column(
                [
                    ft.Text("Enter a name for this description:"),
                    ft.Container(height=10),
                    name_field
                ],
                tight=True,
                width=300
            ),
            actions=[
                ft.TextButton("Cancel", on_click=cancel_clicked),
                ft.ElevatedButton("Save", on_click=save_clicked)
            ]
        )
        
        self.page.open(dialog)
    
    def validate_html(self, html_content: str) -> tuple:
        """
        Validate that content is HTML (has tags)
        Returns (is_valid, error_message)
        """
        if not html_content or not html_content.strip():
            return True, ""  # Empty is OK
        
        # Check for basic HTML tags
        import re
        has_html_tags = bool(re.search(r'<[a-zA-Z][^>]*>', html_content))
        
        if not has_html_tags:
            return False, "Content must be HTML (e.g., <h1>, <p>, <strong>). Plain text not supported."
        
        # Check for unclosed tags (basic validation)
        opening_tags = re.findall(r'<([a-zA-Z][a-zA-Z0-9]*)[^>]*>', html_content)
        closing_tags = re.findall(r'</([a-zA-Z][a-zA-Z0-9]*)>', html_content)
        
        # Self-closing tags that don't need closing
        self_closing = {'br', 'hr', 'img', 'input', 'meta', 'link'}
        
        # Count tags (excluding self-closing)
        opening_count = {}
        for tag in opening_tags:
            if tag.lower() not in self_closing:
                opening_count[tag.lower()] = opening_count.get(tag.lower(), 0) + 1
        
        closing_count = {}
        for tag in closing_tags:
            closing_count[tag.lower()] = closing_count.get(tag.lower(), 0) + 1
        
        # Check if counts match
        for tag, count in opening_count.items():
            if closing_count.get(tag, 0) != count:
                return False, f"Unclosed or mismatched HTML tag: <{tag}>"
        
        return True, ""
    
    def save_description(self, name: str):
        """Save description to database"""
        
        # Validate HTML for each language
        for lang_name, content in [
            ('Lithuanian', self.lt_content),
            ('English', self.en_content),
            ('Latvian', self.lv_content)
        ]:
            if content:  # Only validate non-empty
                is_valid, error_msg = self.validate_html(content)
                if not is_valid:
                    self.show_status(f"{lang_name}: {error_msg}", ft.Colors.RED)
                    return
        
        # Get content from textareas
        lt_html = self.lt_content
        en_html = self.en_content
        lv_html = self.lv_content
        
        success = self.desc_manager.save_description(name, lt_html, en_html, lv_html)
        
        if success:
            self.current_description_name = name
            self.name_display.value = f"Current: {name}"
            self.delete_button.disabled = False
            self.upload_button.disabled = False
            self.show_status(f"Description '{name}' saved successfully", ft.Colors.GREEN)
        else:
            self.show_status("Failed to save description", ft.Colors.RED)
    
    def handle_load(self, e):
        """Load existing description"""
        
        # Get list of descriptions
        descriptions = self.desc_manager.list_descriptions()
        
        if not descriptions:
            self.show_status("No saved descriptions found", ft.Colors.ORANGE)
            return
        
        # Show selection dialog
        self.show_load_dialog(descriptions)
    
    def show_load_dialog(self, descriptions):
        """Show dialog to select description to load"""
        
        # Create list of options
        options = [
            ft.ListTile(
                title=ft.Text(desc['name']),
                subtitle=ft.Text(f"Updated: {desc['updated_at']}", size=12),
                on_click=lambda e, name=desc['name']: self.load_description(name)
            )
            for desc in descriptions
        ]
        
        def cancel_clicked(e):
            self.page.close(dialog)
        
        dialog = ft.AlertDialog(
            title=ft.Text("Load Description"),
            content=ft.Column(
                options,
                scroll=ft.ScrollMode.AUTO,
                width=400,
                height=300
            ),
            actions=[
                ft.TextButton("Cancel", on_click=cancel_clicked)
            ]
        )
        
        self.page.open(dialog)
    
    def load_description(self, name: str):
        """Load description from database into editors"""
        
        # Close dialog
        for dialog in self.page.overlay[:]:
            if isinstance(dialog, ft.AlertDialog):
                self.page.close(dialog)
        
        desc = self.desc_manager.load_description(name)
        
        if desc:
            self.current_description_name = name
            self.name_display.value = f"Current: {name}"
            
            # Store content
            self.lt_content = desc['description_lt']
            self.en_content = desc['description_en']
            self.lv_content = desc['description_lv']
            
            # Set textarea values
            self.lt_textarea.value = self.lt_content
            self.en_textarea.value = self.en_content
            self.lv_textarea.value = self.lv_content
            
            self.save_button.disabled = False
            self.delete_button.disabled = False
            self.upload_button.disabled = False
            
            self.show_status(f"Loaded '{name}'", ft.Colors.GREEN)
            self.page.update()
        else:
            self.show_status("Failed to load description", ft.Colors.RED)
    
    def handle_delete(self, e):
        """Delete current description"""
        
        if not self.current_description_name:
            return
        
        def confirm_clicked(e):
            self.page.close(dialog)
            
            success = self.desc_manager.delete_description(self.current_description_name)
            
            if success:
                self.show_status(f"Deleted '{self.current_description_name}'", ft.Colors.GREEN)
                self.handle_new(None)  # Reset to new
            else:
                self.show_status("Failed to delete description", ft.Colors.RED)
        
        def cancel_clicked(e):
            self.page.close(dialog)
        
        dialog = ft.AlertDialog(
            title=ft.Text("Confirm Delete"),
            content=ft.Text(f"Delete description '{self.current_description_name}'?"),
            actions=[
                ft.TextButton("Cancel", on_click=cancel_clicked),
                ft.ElevatedButton("Delete", on_click=confirm_clicked, bgcolor=ft.Colors.RED)
            ]
        )
        
        self.page.open(dialog)
    
    def handle_upload(self, e):
        """Upload description to PrestaShop"""
        
        if not self.current_description_name:
            self.show_status("Save description first", ft.Colors.ORANGE)
            return
        
        # Show product code input dialog
        self.show_upload_dialog()
    
    def show_upload_dialog(self):
        """Show dialog to enter product code for upload"""

        code_field = ft.TextField(
            label="Product Code",
            hint_text="UB-XXXX",
            width=200,
            autofocus=True
        )

        # Add disclaimer checkbox
        disclaimer_checkbox = ft.Checkbox(
            label="Append color disclaimer",
            value=False
        )

        def upload_clicked(e):
            product_code = code_field.value.strip()
            if not product_code:
                self.show_status("Product code required", ft.Colors.RED)
                return

            append_disclaimer = disclaimer_checkbox.value

            # Close dialog
            self.page.close(dialog)

            # Upload
            self.upload_to_prestashop(product_code, append_disclaimer)

        def cancel_clicked(e):
            self.page.close(dialog)

        dialog = ft.AlertDialog(
            title=ft.Text("Upload to PrestaShop"),
            content=ft.Column(
                [
                    ft.Text("Enter product code to upload description:"),
                    ft.Container(height=10),
                    code_field,
                    ft.Container(height=10),
                    disclaimer_checkbox
                ],
                tight=True,
                width=250
            ),
            actions=[
                ft.TextButton("Cancel", on_click=cancel_clicked),
                ft.ElevatedButton("Upload", on_click=upload_clicked)
            ]
        )

        self.page.open(dialog)
    
    def upload_to_prestashop(self, product_code: str, append_disclaimer: bool = False):
        """Upload description to PrestaShop product"""

        # Validate HTML before upload
        for lang_name, content in [
            ('Lithuanian', self.lt_content),
            ('English', self.en_content),
            ('Latvian', self.lv_content)
        ]:
            if content:
                is_valid, error_msg = self.validate_html(content)
                if not is_valid:
                    self.show_status(f"{lang_name}: {error_msg}", ft.Colors.RED)
                    return

        self.show_status(f"Uploading to {product_code}...", ft.Colors.BLUE)

        try:
            # Navigate to product by code only (no brand needed)
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            driver = self.app.driver

            # Scroll to top
            driver.execute_script("window.scrollTo(0, 0);")
            import time
            time.sleep(0.5)

            # Clear all search fields
            search_name = driver.find_element(By.NAME, "filter_column_name")
            search_name.clear()
            search_category = driver.find_element(By.NAME, "filter_column_name_category")
            search_category.clear()
            search_ref = driver.find_element(By.NAME, "filter_column_reference")
            search_ref.clear()

            # Scroll search field into view
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", search_ref)
            time.sleep(0.3)

            # Search by product code
            search_ref.send_keys(product_code + Keys.ENTER)

            # Wait for results
            time.sleep(2)

            # Click product link in first result
            product_link = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "table.table tbody tr td:nth-child(4) a"))
            )
            product_link.click()

            # Wait for product page to load
            time.sleep(2)

            # Upload description with disclaimer flag
            success = self.desc_manager.upload_to_prestashop_raw(
                driver,
                product_code,
                self.lt_content,
                self.en_content,
                self.lv_content,
                append_disclaimer=append_disclaimer
            )

            if success:
                if append_disclaimer:
                    self.show_status(f"Uploaded to {product_code} with disclaimer", ft.Colors.GREEN)
                else:
                    self.show_status(f"Uploaded to {product_code} successfully", ft.Colors.GREEN)
            else:
                self.show_status("Upload failed", ft.Colors.RED)

        except Exception as ex:
            self.show_status(f"Upload error: {str(ex)}", ft.Colors.RED)
    
    def show_status(self, message: str, color):
        """Show status message"""
        self.status_text.value = message
        self.status_text.color = color
        self.page.update()
        
        # Clear after 3 seconds
        import threading
        def clear():
            import time
            time.sleep(3)
            self.status_text.value = ""
            self.page.update()
        
        threading.Thread(target=clear, daemon=True).start()

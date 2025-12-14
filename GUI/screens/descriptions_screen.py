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

        self.status_text = ft.Text("", size=14)
        self.name_display = ft.Text("", size=16, weight=ft.FontWeight.BOLD)

        self.lt_editor = self.create_html_editor('lt')
        self.en_editor = self.create_html_editor('en')
        self.lv_editor = self.create_html_editor('lv')

        self.tabs = ft.Tabs(
            selected_index=0,
            tabs=[
                ft.Tab(text="Lietuvių", icon=ft.Icons.EDIT, content=self.lt_editor),
                ft.Tab(text="English", icon=ft.Icons.EDIT, content=self.en_editor),
                ft.Tab(text="Latviešu", icon=ft.Icons.EDIT, content=self.lv_editor),
            ],
            expand=True
        )

        self.screen_content = ft.Column(
            [
                ft.Text("Aprašymų Redaktorius", size=24, weight=ft.FontWeight.BOLD),
                ft.Container(height=10),
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
                self.tabs
            ],
            expand=True
        )
        return self.screen_content

    def create_html_editor(self, lang_code: str):
        html_textarea = ft.TextField(
            multiline=True,
            min_lines=25,
            max_lines=25,
            hint_text="Paste HTML here (e.g., <h1>Title</h1>, <p>Text</p>)...",
            on_change=lambda e: self.store_content(lang_code, e.control.value),
            expand=True,
            text_style=ft.TextStyle(font_family="Courier New", size=12)
        )

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
        if lang_code == 'lt':
            self.lt_content = content
        elif lang_code == 'en':
            self.en_content = content
        elif lang_code == 'lv':
            self.lv_content = content

        has_content = bool(self.lt_content or self.en_content or self.lv_content)
        self.save_button.disabled = not has_content
        self.upload_button.disabled = not has_content
        self.page.update()

    def handle_new(self, e):
        self.current_description_name = None
        self.name_display.value = "New Description (not saved)"

        self.lt_content = ""
        self.en_content = ""
        self.lv_content = ""

        self.lt_textarea.value = ""
        self.en_textarea.value = ""
        self.lv_textarea.value = ""

        self.save_button.disabled = False
        self.delete_button.disabled = True
        self.upload_button.disabled = True

        self.show_status("New description created", ft.Colors.GREEN)
        self.page.update()

    def handle_save(self, e):
        if not self.current_description_name:
            self.show_save_dialog()
        else:
            self.save_description(self.current_description_name)

    def show_save_dialog(self):
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
            self.page.close(dialog)
            self.save_description(name)

        dialog = ft.AlertDialog(
            title=ft.Text("Save Description"),
            content=ft.Column([name_field], tight=True, width=300),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.page.close(dialog)),
                ft.ElevatedButton("Save", on_click=save_clicked)
            ]
        )
        self.page.open(dialog)

    def show_upload_dialog(self):
        code_field = ft.TextField(
            label="Product Code",
            hint_text="UB-XXXX",
            width=200,
            autofocus=True
        )

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
            self.page.close(dialog)
            self.upload_to_prestashop(product_code, append_disclaimer)

        dialog = ft.AlertDialog(
            title=ft.Text("Upload to PrestaShop"),
            content=ft.Column(
                [
                    code_field,
                    ft.Container(height=10),
                    disclaimer_checkbox
                ],
                tight=True,
                width=250
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.page.close(dialog)),
                ft.ElevatedButton("Upload", on_click=upload_clicked)
            ]
        )

        self.page.open(dialog)

    def upload_to_prestashop(self, product_code: str, append_disclaimer: bool = False):
        self.show_status(f"Uploading to {product_code}...", ft.Colors.BLUE)

        try:
            driver = self.app.driver
            success = self.desc_manager.upload_to_prestashop_raw(
                driver,
                product_code,
                self.lt_content,
                self.en_content,
                self.lv_content,
                append_disclaimer=append_disclaimer
            )

            if success:
                msg = "with disclaimer" if append_disclaimer else "successfully"
                self.show_status(f"Uploaded to {product_code} {msg}", ft.Colors.GREEN)
            else:
                self.show_status("Upload failed", ft.Colors.RED)

        except Exception as ex:
            self.show_status(f"Upload error: {str(ex)}", ft.Colors.RED)

    def show_status(self, message: str, color):
        self.status_text.value = message
        self.status_text.color = color
        self.page.update()

"""Master password screen for first-time setup"""

import flet as ft

class MasterPasswordScreen:
    def __init__(self, app, on_complete):
        self.app = app
        self.page = app.page
        self.on_complete = on_complete  # Callback when master password is set
    
    def build(self):
        """Build master password setup screen"""
        
        # Password field
        self.password_field = ft.TextField(
            label="Create Master Password",
            password=True,
            can_reveal_password=True,
            width=300,
            autofocus=True
        )
        
        # Confirm password field
        self.confirm_field = ft.TextField(
            label="Confirm Master Password",
            password=True,
            can_reveal_password=True,
            width=300,
            on_submit=lambda e: self.handle_create()
        )
        
        # Create button
        self.create_button = ft.ElevatedButton(
            "Create Master Password",
            on_click=lambda e: self.handle_create(),
            width=300
        )
        
        # Status text
        self.status_text = ft.Text("", size=14)
        
        # Layout
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "Setup Master Password",
                        size=32,
                        weight=ft.FontWeight.BOLD
                    ),
                    ft.Text(
                        "This password encrypts your PrestaShop credentials",
                        size=16,
                        color=ft.Colors.GREY_700
                    ),
                    ft.Container(height=20),
                    self.password_field,
                    self.confirm_field,
                    ft.Container(height=10),
                    self.create_button,
                    ft.Container(height=10),
                    self.status_text
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10
            ),
            padding=40,
            alignment=ft.alignment.center
        )
    
    def handle_create(self):
        """Handle create button click"""
        password = self.password_field.value
        confirm = self.confirm_field.value
        
        # Validate
        if not password or not confirm:
            self.status_text.value = "Įveskite abi slaptažodžio laukus"
            self.status_text.color = ft.Colors.RED
            self.page.update()
            return
        
        if len(password) < 8:
            self.status_text.value = "Slaptažodis turi būti bent 8 simboliai"
            self.status_text.color = ft.Colors.RED
            self.page.update()
            return
        
        if password != confirm:
            self.status_text.value = "Slaptažodžiai nesutampa"
            self.status_text.color = ft.Colors.RED
            self.page.update()
            return
        
        # Success
        self.status_text.value = "Pagrindinis slaptažodis sukurtas!"
        self.status_text.color = ft.Colors.GREEN
        self.page.update()
        
        import time
        time.sleep(1)
        
        # Callback with master password
        self.on_complete(password)
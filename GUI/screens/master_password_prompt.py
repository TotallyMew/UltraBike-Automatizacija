"""Master password prompt for decrypting credentials"""

import flet as ft

class MasterPasswordPrompt:
    def __init__(self, app, on_success, on_cancel=None):
        self.app = app
        self.page = app.page
        self.on_success = on_success  # Callback with (email, password)
    
    def build(self):
        """Build master password prompt screen"""
    
        # Password field
        self.password_field = ft.TextField(
            label="Master Password",
            password=True,
            can_reveal_password=True,
            width=300,
            autofocus=True,
            on_submit=lambda e: self.handle_unlock()
        )
    
        # Unlock button
        self.unlock_button = ft.ElevatedButton(
            "Unlock",
            on_click=lambda e: self.handle_unlock(),
            width=300
        )
    
        # Status text
        self.status_text = ft.Text("", size=14)
    
        # Layout
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "Enter Master Password",
                        size=32,
                        weight=ft.FontWeight.BOLD
                    ),
                    ft.Text(
                        "Your session has expired",
                        size=16,
                        color=ft.Colors.GREY_700
                    ),
                    ft.Container(height=20),
                    self.password_field,
                    ft.Container(height=10),
                    self.unlock_button,
                    ft.Container(height=10),
                    self.status_text
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10
            ),
            padding=40,
            alignment=ft.alignment.center
        )
    
    def handle_unlock(self):
        """Handle unlock button click"""
        master_password = self.password_field.value
        
        if not master_password:
            self.status_text.value = "Įveskite slaptažodį"
            self.status_text.color = ft.Colors.RED
            self.page.update()
            return
        
        # Verify master password and get credentials
        try:
            email, password = self.app.credential_manager.get_credentials_with_master(master_password)
            
            if email and password:
                self.status_text.value = "✓ Slaptažodis teisingas"
                self.status_text.color = ft.Colors.GREEN
                self.page.update()
                
                import time
                time.sleep(0.5)
                
                # Callback with credentials
                self.on_success(email, password)
            else:
                self.status_text.value = "Neteisingas slaptažodis"
                self.status_text.color = ft.Colors.RED
                self.page.update()
        except Exception as e:
            self.status_text.value = f"Klaida: {str(e)}"
            self.status_text.color = ft.Colors.RED
            self.page.update()
"""Loading screen shown during auto-login"""

import flet as ft

class LoadingScreen:
    def __init__(self, app, message="Loading..."):
        self.app = app
        self.page = app.page
        self.message = message
    
    def build(self):
        """Build loading screen UI"""
        return ft.Container(
            content=ft.Column(
                [
                    ft.ProgressRing(),
                    ft.Container(height=20),
                    ft.Text(
                        self.message,
                        size=16,
                        color=ft.Colors.GREY_700
                    )
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10
            ),
            padding=40,
            alignment=ft.alignment.center
        )
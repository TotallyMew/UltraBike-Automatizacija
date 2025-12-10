"""Top bar component"""

import flet as ft

class TopBar:
    def __init__(self, app, user_email, on_logout):
        self.app = app
        self.user_email = user_email
        self.on_logout_callback = on_logout
    
    def build(self):
        """Build top bar UI"""
        return ft.Container(
            content=ft.Row(
                [
                    ft.Text(
                        "UltraBike Automation",
                        size=20,
                        weight=ft.FontWeight.BOLD
                    ),
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.PERSON, size=20),
                            ft.Text(self.user_email, size=14),
                            ft.Container(width=10),
                            ft.IconButton(
                                icon=ft.Icons.LOGOUT,
                                tooltip="Atsijungti",
                                on_click=lambda e: self.on_logout_callback()
                            )
                        ],
                        spacing=5
                    )
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
            ),
            padding=20,
            bgcolor=ft.Colors.BLUE_50,
            border=ft.border.only(bottom=ft.BorderSide(1, ft.Colors.BLUE_200))
        )
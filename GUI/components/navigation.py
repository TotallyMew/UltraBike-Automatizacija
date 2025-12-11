"""Navigation rail component"""

import flet as ft

class NavigationRail:
    def __init__(self, app, on_change):
        self.app = app
        self.on_change_callback = on_change
    
    def build(self):
        """Build navigation rail UI"""
        return ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=100,
            min_extended_width=200,
            destinations=[
                ft.NavigationRailDestination(
                    icon=ft.Icons.UPLOAD,
                    selected_icon=ft.Icons.UPLOAD,
                    label="Įkelti"
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.HISTORY,
                    selected_icon=ft.Icons.HISTORY,
                    label="Istorija"
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.TRANSLATE,
                    selected_icon=ft.Icons.TRANSLATE,
                    label="Vertimai"
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.SETTINGS,
                    selected_icon=ft.Icons.SETTINGS,
                    label="Nustatymai"
                ),
            ],
            on_change=lambda e: self.on_change_callback(e.control.selected_index)
        )
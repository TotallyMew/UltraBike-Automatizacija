"""Translations management screen"""

import flet as ft

class TranslationsScreen:
    def __init__(self, app):
        self.app = app
        self.page = app.page
        self.current_translations = []
        self.current_page = 0
        self.page_size = 50  # Show 50 rows per page
        self.total_pages = 0
    
    def build(self):
        """Build translations screen UI"""
        
        # Filters
        self.source_lang_filter = ft.Dropdown(
            label="Source Language",
            width=150,
            options=[
                ft.dropdown.Option("All"),
                ft.dropdown.Option("EN"),
                ft.dropdown.Option("PL"),
                ft.dropdown.Option("LT"),
            ],
            value="All",
            on_change=lambda e: self.refresh_translations()
        )
        
        self.target_lang_filter = ft.Dropdown(
            label="Target Language",
            width=150,
            options=[
                ft.dropdown.Option("All"),
                ft.dropdown.Option("EN"),
                ft.dropdown.Option("PL"),
                ft.dropdown.Option("LT"),
            ],
            value="All",
            on_change=lambda e: self.refresh_translations()
        )
        
        self.category_filter = ft.Dropdown(
            label="Category",
            width=150,
            options=[
                ft.dropdown.Option("All"),
                ft.dropdown.Option("component"),
                ft.dropdown.Option("material"),
                ft.dropdown.Option("color"),
                ft.dropdown.Option("property"),
            ],
            value="All",
            on_change=lambda e: self.refresh_translations()
        )
        
        # Search field
        self.search_field = ft.TextField(
            label="Search",
            width=300,
            hint_text="Search source or target term...",
            on_change=lambda e: self.refresh_translations()
        )
        
        # Add translation button
        self.add_button = ft.ElevatedButton(
            "Add Translation",
            icon=ft.Icons.ADD,
            on_click=self.show_add_dialog
        )
        
        # Refresh button
        self.refresh_button = ft.IconButton(
            icon=ft.Icons.REFRESH,
            tooltip="Refresh",
            on_click=lambda e: self.refresh_translations()
        )
        
        # Pagination controls
        self.page_info = ft.Text("", size=12, color=ft.Colors.GREY_700)
        
        self.prev_button = ft.IconButton(
            icon=ft.Icons.ARROW_BACK,
            tooltip="Previous page",
            on_click=lambda e: self.change_page(-1),
            disabled=True
        )
        
        self.next_button = ft.IconButton(
            icon=ft.Icons.ARROW_FORWARD,
            tooltip="Next page",
            on_click=lambda e: self.change_page(1),
            disabled=True
        )
        
        # Translations table header
        header = ft.Row(
            [
                ft.Text("Source", width=150, weight=ft.FontWeight.BOLD),
                ft.Text("Target", width=150, weight=ft.FontWeight.BOLD),
                ft.Text("Lang", width=80, weight=ft.FontWeight.BOLD),
                ft.Text("Category", width=100, weight=ft.FontWeight.BOLD),
                ft.Text("Actions", width=150, weight=ft.FontWeight.BOLD),
            ],
            spacing=10
        )
        
        # Translations list
        self.translations_list = ft.Column(
            [],
            scroll=ft.ScrollMode.AUTO,
            expand=True
        )
        
        # Layout
        self.screen_content = ft.Column(
            [
                ft.Text("Vertimų Valdymas", size=24, weight=ft.FontWeight.BOLD),
                ft.Container(height=10),
                
                # Filters row
                ft.Row(
                    [
                        self.source_lang_filter,
                        ft.Icon(ft.Icons.ARROW_FORWARD, size=20),
                        self.target_lang_filter,
                        self.category_filter,
                        self.search_field,
                        self.refresh_button,
                        self.add_button
                    ],
                    spacing=10
                ),
                
                ft.Container(height=10),
                ft.Divider(),
                
                # Pagination controls
                ft.Row(
                    [
                        self.prev_button,
                        self.page_info,
                        self.next_button
                    ],
                    spacing=10
                ),
                
                # Table header
                header,
                ft.Divider(),
                
                # Translations list
                ft.Container(
                    content=self.translations_list,
                    expand=True
                )
            ],
            expand=True
        )
        
        return self.screen_content
    
    def refresh_translations(self):
        """Refresh translations list based on filters"""
        
        cursor = self.app.db.conn.cursor()
        
        # Build query
        query = "SELECT source_lang, target_lang, source_term, target_term, category FROM translations WHERE 1=1"
        params = []
        
        # Source language filter
        if self.source_lang_filter.value != "All":
            query += " AND source_lang = ?"
            params.append(self.source_lang_filter.value)
        
        # Target language filter
        if self.target_lang_filter.value != "All":
            query += " AND target_lang = ?"
            params.append(self.target_lang_filter.value)
        
        # Category filter
        if self.category_filter.value != "All":
            query += " AND category = ?"
            params.append(self.category_filter.value)
        
        # Search filter
        if self.search_field.value:
            query += " AND (source_term LIKE ? OR target_term LIKE ?)"
            search_term = f"%{self.search_field.value}%"
            params.extend([search_term, search_term])
        
        query += " ORDER BY source_term"
        
        # Execute query and store all results
        self.current_translations = cursor.execute(query, params).fetchall()
        
        # Calculate pagination
        self.total_pages = (len(self.current_translations) + self.page_size - 1) // self.page_size
        self.current_page = 0
        
        # Render first page
        self.render_page()
    
    def render_page(self):
        """Render current page of translations"""
        
        # Clear list
        self.translations_list.controls.clear()
        
        # Calculate slice
        start_idx = self.current_page * self.page_size
        end_idx = min(start_idx + self.page_size, len(self.current_translations))
        page_translations = self.current_translations[start_idx:end_idx]
        
        # Build rows for current page only
        if page_translations:
            for row in page_translations:
                self.translations_list.controls.append(
                    self.build_translation_row(row)
                )
        else:
            self.translations_list.controls.append(
                ft.Text("No translations found", color=ft.Colors.GREY_600)
            )
        
        # Update pagination controls
        self.page_info.value = f"Page {self.current_page + 1} of {self.total_pages} ({len(self.current_translations)} total)"
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1
        
        self.page.update()
    
    def change_page(self, delta):
        """Navigate between pages"""
        new_page = self.current_page + delta
        
        if 0 <= new_page < self.total_pages:
            self.current_page = new_page
            self.render_page()
    
    def build_translation_row(self, row):
        """Build a single translation row"""
        return ft.Container(
            content=ft.Row(
                [
                    ft.Text(row['source_term'], width=150),
                    ft.Text(row['target_term'], width=150),
                    ft.Text(f"{row['source_lang']}→{row['target_lang']}", width=80, size=12),
                    ft.Text(row['category'], width=100, size=12, color=ft.Colors.GREY_700),
                    ft.Row(
                        [
                            ft.IconButton(
                                icon=ft.Icons.EDIT,
                                icon_size=18,
                                tooltip="Edit",
                                on_click=lambda e, r=row: self.show_edit_dialog(r)
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE,
                                icon_size=18,
                                icon_color=ft.Colors.RED,
                                tooltip="Delete",
                                on_click=lambda e, r=row: self.show_delete_confirm(r)
                            )
                        ],
                        spacing=5
                    )
                ],
                spacing=10
            ),
            padding=5,
            border=ft.border.only(bottom=ft.BorderSide(1, ft.Colors.GREY_300))
        )
    
    def show_add_dialog(self, e):
        """Show add translation dialog"""
        
        source_lang = ft.Dropdown(
            label="Source Language",
            width=200,
            options=[
                ft.dropdown.Option("EN"),
                ft.dropdown.Option("PL"),
                ft.dropdown.Option("LT"),
            ],
            value="EN"
        )
        
        target_lang = ft.Dropdown(
            label="Target Language",
            width=200,
            options=[
                ft.dropdown.Option("EN"),
                ft.dropdown.Option("PL"),
                ft.dropdown.Option("LT"),
            ],
            value="LT"
        )
        
        source_term = ft.TextField(
            label="Source Term",
            width=400,
            hint_text="Enter source term (will be converted to UPPERCASE)"
        )
        
        target_term = ft.TextField(
            label="Target Term",
            width=400,
            hint_text="Enter target term"
        )
        
        category = ft.Dropdown(
            label="Category",
            width=200,
            options=[
                ft.dropdown.Option("component"),
                ft.dropdown.Option("material"),
                ft.dropdown.Option("color"),
                ft.dropdown.Option("property"),
            ],
            value="component"
        )
        
        status_text = ft.Text("", size=12)
        
        def handle_add(e):
            # Validate
            if not source_term.value or not target_term.value:
                status_text.value = "All fields required"
                status_text.color = ft.Colors.RED
                self.page.update()
                return
            
            # Normalize source term to UPPERCASE
            source_normalized = source_term.value.strip().upper()
            target_normalized = target_term.value.strip()
            
            # Insert into database
            try:
                cursor = self.app.db.conn.cursor()
                cursor.execute("""
                    INSERT INTO translations 
                    (source_lang, target_lang, source_term, target_term, category)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    source_lang.value,
                    target_lang.value,
                    source_normalized,
                    target_normalized,
                    category.value
                ))
                self.app.db.conn.commit()
                
                # Close dialog and refresh
                self.page.close(dialog)
                self.refresh_translations()
                
            except Exception as ex:
                status_text.value = f"Error: {str(ex)}"
                status_text.color = ft.Colors.RED
                self.page.update()
        
        dialog = ft.AlertDialog(
            title=ft.Text("Add Translation"),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Row([source_lang, ft.Icon(ft.Icons.ARROW_FORWARD), target_lang]),
                        source_term,
                        target_term,
                        category,
                        status_text
                    ],
                    spacing=15,
                    tight=True
                ),
                width=500
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.page.close(dialog)),
                ft.ElevatedButton("Add", on_click=handle_add)
            ]
        )
        
        self.page.open(dialog)
    
    def show_edit_dialog(self, row):
        """Show edit translation dialog"""
        
        target_term = ft.TextField(
            label="Target Term",
            width=400,
            value=row['target_term']
        )
        
        category = ft.Dropdown(
            label="Category",
            width=200,
            options=[
                ft.dropdown.Option("component"),
                ft.dropdown.Option("material"),
                ft.dropdown.Option("color"),
                ft.dropdown.Option("property"),
            ],
            value=row['category']
        )
        
        status_text = ft.Text("", size=12)
        
        def handle_save(e):
            if not target_term.value:
                status_text.value = "Target term required"
                status_text.color = ft.Colors.RED
                self.page.update()
                return
            
            try:
                cursor = self.app.db.conn.cursor()
                cursor.execute("""
                    UPDATE translations 
                    SET target_term = ?, category = ?
                    WHERE source_lang = ? AND target_lang = ? AND source_term = ?
                """, (
                    target_term.value.strip(),
                    category.value,
                    row['source_lang'],
                    row['target_lang'],
                    row['source_term']
                ))
                self.app.db.conn.commit()
                
                self.page.close(dialog)
                self.refresh_translations()
                
            except Exception as ex:
                status_text.value = f"Error: {str(ex)}"
                status_text.color = ft.Colors.RED
                self.page.update()
        
        dialog = ft.AlertDialog(
            title=ft.Text("Edit Translation"),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(f"Source: {row['source_term']}", weight=ft.FontWeight.BOLD),
                        ft.Text(f"Language: {row['source_lang']} → {row['target_lang']}", size=12),
                        ft.Container(height=10),
                        target_term,
                        category,
                        status_text
                    ],
                    spacing=15,
                    tight=True
                ),
                width=500
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.page.close(dialog)),
                ft.ElevatedButton("Save", on_click=handle_save)
            ]
        )
        
        self.page.open(dialog)
    
    def show_delete_confirm(self, row):
        """Show delete confirmation dialog"""
        
        def handle_delete(e):
            try:
                cursor = self.app.db.conn.cursor()
                cursor.execute("""
                    DELETE FROM translations 
                    WHERE source_lang = ? AND target_lang = ? AND source_term = ?
                """, (row['source_lang'], row['target_lang'], row['source_term']))
                self.app.db.conn.commit()
                
                self.page.close(dialog)
                self.refresh_translations()
                
            except Exception as ex:
                print(f"Delete error: {ex}")
        
        dialog = ft.AlertDialog(
            title=ft.Text("Confirm Delete"),
            content=ft.Text(
                f"Delete translation?\n\n{row['source_term']} → {row['target_term']}"
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.page.close(dialog)),
                ft.ElevatedButton(
                    "Delete",
                    bgcolor=ft.Colors.RED,
                    color=ft.Colors.WHITE,
                    on_click=handle_delete
                )
            ]
        )
        
        self.page.open(dialog)
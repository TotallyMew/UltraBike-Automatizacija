"""Settings, account, and music page layouts."""
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QGridLayout, QWidget, QBoxLayout
from qfluentwidgets import CaptionLabel, PushButton
from GUI_Qt.widgets.workspace import WorkspaceColumns, Disclosure, ancestor_card, clear_layout, bind_text, move_widget, connect_signal


def arrange_account(screen):
    layout = screen.content_widget.layout() if hasattr(screen, "content_widget") and screen.content_widget else screen.content.layout()
    while layout.count() > 1:
        layout.takeAt(1)
    workspace = WorkspaceColumns(sidebar_width=360)
    screen._workspace = workspace
    layout.addWidget(workspace)
    workspace.main_layout.addWidget(screen.admin_card)
    workspace.main_layout.addWidget(screen.brand_card)
    workspace.side_layout.addWidget(screen.profile_card)
    workspace.side_layout.addWidget(screen.security_card)
    admin = screen.admin_card.layout()
    clear_layout(admin)
    admin.addWidget(screen._ui["ps_title"])
    admin.addWidget(screen._ui["ps_caption"])
    fields = QGridLayout()
    fields.setHorizontalSpacing(16)
    for col, (label, control) in enumerate((
        (screen._ui["ps_email_label"], screen.admin_email),
        (screen._ui["ps_password_label"], screen.admin_password),
    )):
        fields.addWidget(label, 0, col)
        fields.addWidget(control, 1, col)
        fields.setColumnStretch(col, 1)
    admin.addLayout(fields)
    buttons = QHBoxLayout()
    buttons.addWidget(screen._ui["admin_save"])
    buttons.addWidget(screen._ui["admin_view"])
    buttons.addStretch()
    admin.addLayout(buttons)
    brands = screen.brand_card.layout()
    clear_layout(brands)
    brands.addWidget(screen._ui["brand_title"])
    brands.addWidget(screen._ui["brand_caption"])
    for prefix, username, password in (
        ("basso", screen.basso_username, screen.basso_password),
        ("lc", screen.lc_username, screen.lc_password),
    ):
        brands.addWidget(screen._ui[prefix + "_section"])
        details = Disclosure(screen.main, "layout.brand_edit")
        for widget in (screen._ui[prefix + "_user_label"], username,
                screen._ui[prefix + "_pass_label"], password,
                screen._ui[prefix + "_save"], screen._ui[prefix + "_view"]):
            move_widget(widget, details.body_layout)
        brands.addWidget(details)
    workspace.main_layout.addStretch()
    workspace.side_layout.addStretch()


def arrange_settings(screen):
    content = screen.content_widget.layout()
    names = ("lang_title", "browser_title", "paths_title", "features_title",
             "updates_title", "data_title", "info_title")
    cards = [ancestor_card(screen._ui[name]) for name in names]
    theme = ancestor_card(screen._ui["theme_title"])
    # Appearance and language share one section and retain preview/cancel behavior.
    theme_box = theme.layout()
    appearance = cards[0].layout()
    while theme_box.count():
        item = theme_box.takeAt(0)
        if item.widget():
            appearance.addWidget(item.widget())
        elif item.layout():
            appearance.addLayout(item.layout())
    theme.hide()
    while content.count() > 1:
        content.takeAt(1)
    for item in cards:
        content.addWidget(item)
    content.addStretch()

    root = screen.layout()
    root.removeWidget(screen.scroll)
    body = WorkspaceColumns(sidebar_width=256, threshold=900)
    # Here the small section list sits on the left; scroll remains the wide region.
    body.columns.removeWidget(body.main)
    body.columns.removeWidget(body.sidebar)
    body.columns.addWidget(body.sidebar)
    body.columns.addWidget(body.main, 1)
    body.side_layout.setContentsMargins(24, 24, 0, 24)
    body.main_layout.addWidget(screen.scroll)
    root.insertWidget(0, body, 1)
    screen._settings_workspace = body
    screen._section_buttons = []
    keys = ("layout.appearance", "settings.browser.title", "settings.paths.title",
            "settings.features.title", "settings.updates.title", "settings.data.title",
            "settings.about.title")
    for key, target in zip(keys, cards):
        button = bind_text(PushButton(), screen.main, key)
        button.setCheckable(True)
        def select(_checked=False, target=target, button=button):
            for item in screen._section_buttons:
                item.setChecked(item is button)
            screen.scroll.ensureWidgetVisible(target, 0, 24)
        button.clicked.connect(select)
        screen._section_buttons.append(button)
        body.side_layout.addWidget(button)
    body.side_layout.addStretch()
    screen._section_buttons[0].setChecked(True)
    status = CaptionLabel()
    screen._save_status = status
    footer = screen._ui["save_btn"].parentWidget().layout()
    footer.insertWidget(0, status)
    screen._update_save_status = lambda: status.setText(screen.main.i18n.tr(
        "layout.unsaved" if screen._is_dirty else "layout.saved"))
    screen._update_save_status()
    if hasattr(screen.main.i18n, "languageChanged"):
        connect_signal(screen.main.i18n.languageChanged, screen, lambda *_: screen._update_save_status())


def arrange_spotify(screen):
    workspace = WorkspaceColumns(sidebar_width=360)
    screen._workspace = workspace
    while screen.layout.count() > 1:
        screen.layout.takeAt(1)
    screen.layout.addWidget(workspace)
    workspace.main_layout.addWidget(screen.best_card)
    workspace.main_layout.addWidget(screen.work_tracks_card)
    workspace.main_layout.addWidget(screen.player_card)
    workspace.side_layout.addWidget(screen.connection_card)
    metrics = QWidget()
    box = QVBoxLayout(metrics)
    box.setContentsMargins(0, 0, 0, 0)
    box.addWidget(screen.analytics_title)
    box.addLayout(screen.metrics_grid)
    workspace.side_layout.addWidget(metrics)
    connection = screen.connection_card.layout()
    clear_layout(connection)
    connection.setDirection(QBoxLayout.Direction.TopToBottom)
    for widget in (screen.connection_title, screen.connection_detail,
            screen.connect_button, screen.disconnect_button):
        move_widget(widget, connection)
    workspace.main_layout.addStretch()
    workspace.side_layout.addStretch()

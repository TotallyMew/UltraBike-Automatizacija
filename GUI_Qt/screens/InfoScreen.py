"""Info Screen

Explains what the app is and how to use it.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy

from qfluentwidgets import (
    CardWidget,
    TitleLabel,
    StrongBodyLabel,
    BodyLabel,
    CaptionLabel,
    ScrollArea,
    TransparentToolButton,
    FluentIcon,
    isDarkTheme,
    qconfig,
    IconWidget,
)

from GUI_Qt.widgets.ResponsiveWidget import ResponsiveWidget
from GUI_Qt.styles.theme_config import (
    COLORS, FONTS, RADII, SIZES, get_details_card_bg, get_surface_color, get_text_color,
)
from GUI_Qt.styles.screen_theme import (
    PAGE_MARGINS,
    PAGE_SPACING,
    CARD_MARGINS,
    ICON_TEXT_GAP,
    ROW_SPACING,
    CONTENT_SPACING,
    DETAILS_MARGINS,
    apply_screen_theme,
    enforce_transparent_labels,
    get_responsive_margins,
    get_responsive_spacing,
    DETAILS_SPACING,
)


class InfoScreen(ResponsiveWidget):
    """Informational screen: purpose and usage."""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self._extra_expanded = False
        self._expanded: dict[str, bool] = {}
        self.scroll: ScrollArea | None = None
        self.content: QWidget | None = None
        self.content_widget = None  # Alias for consistency
        self._init_ui()
        qconfig.themeChangedFinished.connect(self._on_theme_changed)

    def _apply_theme(self):
        apply_screen_theme(
            self,
            "InfoScreen",
            scroll=self.scroll,
            content=self.content,
        )

        self._apply_extra_details_style()

        # Some QFluent widgets set per-label styles; enforce transparency.
        self._force_transparent_text_widgets()

    def _force_transparent_text_widgets(self):
        """Normalize labels once, outside Qt's style-event callbacks."""
        enforce_transparent_labels(self)

    def _apply_extra_details_style(self):
        if not hasattr(self, "extra_details_card"):
            return
        is_dark = isDarkTheme()
        self.extra_details_card.setStyleSheet(
            f"background-color: {get_details_card_bg(is_dark)};"
            f"border: 1px solid {COLORS['border_dark'] if is_dark else COLORS['border_light']};"
        )

    def _init_ui(self):
        self._apply_theme()
        self.setAutoFillBackground(True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(*PAGE_MARGINS)
        main_layout.setSpacing(PAGE_SPACING)

        # Header
        header = QHBoxLayout()
        title_container = QHBoxLayout()
        title_container.setSpacing(ICON_TEXT_GAP)

        title_icon = IconWidget(FluentIcon.INFO)
        title_icon.setFixedSize(SIZES['icon_lg'], SIZES['icon_lg'])

        self.title_label = TitleLabel("")
        title_container.addWidget(title_icon)
        title_container.addWidget(self.title_label)
        header.addLayout(title_container)
        header.addStretch()
        main_layout.addLayout(header)

        # Scrollable content area (this page can be long)
        self.scroll = ScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.content = QWidget()
        content_layout = QVBoxLayout(self.content)
        # Reserve a right-side gutter so the vertical scrollbar never overlaps cards.
        content_layout.setContentsMargins(0, 0, PAGE_SPACING, 0)
        content_layout.setSpacing(CONTENT_SPACING)

        def _make_card():
            c = CardWidget()
            c.setBorderRadius(RADII['md'])
            c.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            l = QVBoxLayout(c)
            l.setContentsMargins(*CARD_MARGINS)
            l.setSpacing(ROW_SPACING)
            return c, l

        def _add_dropdown(card_layout: QVBoxLayout, key: str):
            """Adds a collapsed details section to a card."""

            header = QHBoxLayout()
            header.setContentsMargins(0, 0, 0, 0)
            header.setSpacing(ROW_SPACING)

            title = StrongBodyLabel("")
            title.setObjectName(f"info_title_{key}")
            header.addWidget(title)
            header.addStretch(1)

            btn = TransparentToolButton(FluentIcon.DOWN, self)
            btn.setFixedSize(SIZES['icon_action'], SIZES['icon_action'])
            header.addWidget(btn)
            card_layout.addLayout(header)

            details_card = CardWidget()
            details_card.setVisible(False)
            details_layout = QVBoxLayout(details_card)
            details_layout.setContentsMargins(*DETAILS_MARGINS)
            details_layout.setSpacing(DETAILS_SPACING)

            details = BodyLabel("")
            details.setWordWrap(True)
            details.setStyleSheet(
                f"font-size: {FONTS['size_caption_sm']}; color: {COLORS['text_primary_dark'] if isDarkTheme() else COLORS['text_primary_light']};"
                "background-color: transparent;"
            )
            details_layout.addWidget(details)
            card_layout.addWidget(details_card)

            self._expanded.setdefault(key, False)

            def _toggle():
                self._expanded[key] = not self._expanded.get(key, False)
                details_card.setVisible(self._expanded[key])
                try:
                    btn.setIcon(FluentIcon.UP if self._expanded[key] else FluentIcon.DOWN)
                except Exception:
                    pass

            btn.clicked.connect(_toggle)
            return title, btn, details_card, details

        # Overview
        self.overview_card, ov = _make_card()
        self.overview_title, self.overview_toggle_btn, self.overview_details_card, self.overview_details = _add_dropdown(ov, "overview")
        self.overview_text = BodyLabel("")
        self.overview_text.setWordWrap(True)
        self.overview_note = CaptionLabel("")
        self.overview_note.setWordWrap(True)
        self.overview_note.setStyleSheet(f"color: {get_text_color(isDarkTheme(), 'secondary')}; background-color: transparent;")
        ov.insertWidget(1, self.overview_text)
        ov.insertWidget(2, self.overview_note)
        content_layout.addWidget(self.overview_card)

        # Screen-by-screen cards
        self.login_card, ll = _make_card()
        self.login_title, self.login_toggle_btn, self.login_details_card, self.login_details = _add_dropdown(ll, "login")
        self.login_text = BodyLabel("")
        self.login_text.setWordWrap(True)
        ll.insertWidget(1, self.login_text)
        content_layout.addWidget(self.login_card)

        self.upload_card, ul = _make_card()
        self.upload_title, self.upload_toggle_btn, self.upload_details_card, self.upload_details = _add_dropdown(ul, "upload")
        self.upload_text = BodyLabel("")
        self.upload_text.setWordWrap(True)
        ul.insertWidget(1, self.upload_text)
        content_layout.addWidget(self.upload_card)

        self.batch_card, bl = _make_card()
        self.batch_title, self.batch_toggle_btn, self.batch_details_card, self.batch_details = _add_dropdown(bl, "batch")
        self.batch_text = BodyLabel("")
        self.batch_text.setWordWrap(True)
        bl.insertWidget(1, self.batch_text)
        content_layout.addWidget(self.batch_card)

        self.history_card, hl = _make_card()
        self.history_title, self.history_toggle_btn, self.history_details_card, self.history_details = _add_dropdown(hl, "history")
        self.history_text = BodyLabel("")
        self.history_text.setWordWrap(True)
        hl.insertWidget(1, self.history_text)
        content_layout.addWidget(self.history_card)

        self.translations_card, tl = _make_card()
        self.translations_title, self.translations_toggle_btn, self.translations_details_card, self.translations_details = _add_dropdown(tl, "translations")
        self.translations_text = BodyLabel("")
        self.translations_text.setWordWrap(True)
        tl.insertWidget(1, self.translations_text)
        content_layout.addWidget(self.translations_card)

        self.descriptions_card, dl = _make_card()
        self.descriptions_title, self.descriptions_toggle_btn, self.descriptions_details_card, self.descriptions_details = _add_dropdown(dl, "descriptions")
        self.descriptions_text = BodyLabel("")
        self.descriptions_text.setWordWrap(True)
        dl.insertWidget(1, self.descriptions_text)
        content_layout.addWidget(self.descriptions_card)

        self.folders_card, fl = _make_card()
        self.folders_title, self.folders_toggle_btn, self.folders_details_card, self.folders_details = _add_dropdown(fl, "folders")
        self.folders_text = BodyLabel("")
        self.folders_text.setWordWrap(True)
        fl.insertWidget(1, self.folders_text)
        content_layout.addWidget(self.folders_card)

        self.settings_card, sl = _make_card()
        self.settings_title, self.settings_toggle_btn, self.settings_details_card, self.settings_details = _add_dropdown(sl, "settings")
        self.settings_text = BodyLabel("")
        self.settings_text.setWordWrap(True)
        sl.insertWidget(1, self.settings_text)
        content_layout.addWidget(self.settings_card)

        # Safety / best practices
        self.safety_card, sf = _make_card()
        self.safety_title, self.safety_toggle_btn, self.safety_details_card, self.safety_details = _add_dropdown(sf, "safety")
        self.safety_text = BodyLabel("")
        self.safety_text.setWordWrap(True)
        sf.insertWidget(1, self.safety_text)
        content_layout.addWidget(self.safety_card)

        # Extra steps dropdown
        self.extra_card, exl = _make_card()

        extra_header = QHBoxLayout()
        extra_header.setContentsMargins(0, 0, 0, 0)
        extra_header.setSpacing(ROW_SPACING)

        self.extra_title = StrongBodyLabel("")
        extra_header.addWidget(self.extra_title)
        extra_header.addStretch(1)

        self.extra_toggle_btn = TransparentToolButton(FluentIcon.DOWN, self)
        self.extra_toggle_btn.setFixedSize(SIZES['icon_action'], SIZES['icon_action'])
        self.extra_toggle_btn.clicked.connect(self._toggle_extra_steps)
        extra_header.addWidget(self.extra_toggle_btn)

        exl.addLayout(extra_header)

        self.extra_details_card = CardWidget()
        self.extra_details_card.setVisible(False)
        extra_details_layout = QVBoxLayout(self.extra_details_card)
        extra_details_layout.setContentsMargins(*DETAILS_MARGINS)
        extra_details_layout.setSpacing(DETAILS_SPACING)

        self.extra_text = BodyLabel("")
        self.extra_text.setWordWrap(True)
        self.extra_text.setStyleSheet(
            f"font-size: {FONTS['size_caption_sm']}; color: {COLORS['text_primary_dark'] if isDarkTheme() else COLORS['text_primary_light']};"
        )
        extra_details_layout.addWidget(self.extra_text)
        exl.addWidget(self.extra_details_card)
        content_layout.addWidget(self.extra_card)

        content_layout.addStretch(1)
        self.scroll.setWidget(self.content)
        main_layout.addWidget(self.scroll, 1)

        # Re-apply theme now that ScrollArea/content exist
        self._apply_theme()

        self.retranslate_ui()

        # Enforce transparent label backgrounds after building UI
        self._force_transparent_text_widgets()

    def _toggle_extra_steps(self):
        self._extra_expanded = not self._extra_expanded
        self.extra_details_card.setVisible(self._extra_expanded)
        try:
            self.extra_toggle_btn.setIcon(FluentIcon.UP if self._extra_expanded else FluentIcon.DOWN)
        except Exception:
            pass

    def retranslate_ui(self):
        tr = self.main.i18n.tr

        self.title_label.setText(tr("info.title"))

        self.overview_title.setText(tr("info.overview.title"))
        self.overview_text.setText(tr("info.overview.text"))
        self.overview_note.setText(tr("info.overview.note"))
        self.overview_details.setText(tr("info.overview.details"))
        self.overview_toggle_btn.setToolTip(tr("info.more.tooltip"))

        self.login_title.setText(tr("info.login.title"))
        self.login_text.setText(tr("info.login.text"))
        self.login_details.setText(tr("info.login.details"))
        self.login_toggle_btn.setToolTip(tr("info.more.tooltip"))

        self.upload_title.setText(tr("info.upload.title"))
        self.upload_text.setText(tr("info.upload.text"))
        self.upload_details.setText(tr("info.upload.details"))
        self.upload_toggle_btn.setToolTip(tr("info.more.tooltip"))

        self.batch_title.setText(tr("info.batch.title"))
        self.batch_text.setText(tr("info.batch.text"))
        self.batch_details.setText(tr("info.batch.details"))
        self.batch_toggle_btn.setToolTip(tr("info.more.tooltip"))

        self.history_title.setText(tr("info.history.title"))
        self.history_text.setText(tr("info.history.text"))
        self.history_details.setText(tr("info.history.details"))
        self.history_toggle_btn.setToolTip(tr("info.more.tooltip"))

        self.translations_title.setText(tr("info.translations.title"))
        self.translations_text.setText(tr("info.translations.text"))
        self.translations_details.setText(tr("info.translations.details"))
        self.translations_toggle_btn.setToolTip(tr("info.more.tooltip"))

        self.descriptions_title.setText(tr("info.descriptions.title"))
        self.descriptions_text.setText(tr("info.descriptions.text"))
        self.descriptions_details.setText(tr("info.descriptions.details"))
        self.descriptions_toggle_btn.setToolTip(tr("info.more.tooltip"))

        self.folders_title.setText(tr("info.folders.title"))
        self.folders_text.setText(tr("info.folders.text"))
        self.folders_details.setText(tr("info.folders.details"))
        self.folders_toggle_btn.setToolTip(tr("info.more.tooltip"))

        self.settings_title.setText(tr("info.settings.title"))
        self.settings_text.setText(tr("info.settings.text"))
        self.settings_details.setText(tr("info.settings.details"))
        self.settings_toggle_btn.setToolTip(tr("info.more.tooltip"))

        self.safety_title.setText(tr("info.safety.title"))
        self.safety_text.setText(tr("info.safety.text"))
        self.safety_details.setText(tr("info.safety.details"))
        self.safety_toggle_btn.setToolTip(tr("info.more.tooltip"))

        self.extra_title.setText(tr("info.extra.title"))
        self.extra_text.setText(tr("info.extra.text"))
        self.extra_toggle_btn.setToolTip(tr("info.extra.tooltip"))

    def _on_breakpoint_changed(self, breakpoint: str):
        """Respond to breakpoint changes - adjust margins and spacing."""
        margins = get_responsive_margins(breakpoint)
        spacing = get_responsive_spacing(breakpoint)
        if hasattr(self, 'content') and self.content and self.content.layout():
            self.content.layout().setContentsMargins(*margins)
            self.content.layout().setSpacing(spacing)

    def _on_theme_changed(self):
        self._apply_theme()

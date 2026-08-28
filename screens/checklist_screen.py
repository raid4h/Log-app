# screens/checklist_screen.py
#
# Main Checklist screen -- shows every checklist as a summary card
# (widgets/checklist_card.py). Tapping a card opens its items on
# screens/checklist_detail_screen.py. The add bar creates a new
# checklist (title, optional priority) rather than adding an item
# directly -- items are added inside the detail screen.
#
# Categories are user-defined and SHARED with the rest of the app via
# database/category_queries.py (the same table tasks/calendar use) --
# this file only ever calls its existing functions, never edits it.
#
# UI-only pass: (1) the "New Checklist" popup's priority button text
# ("No priority set" / a chosen priority) is now explicitly centered,
# both horizontally and vertically, instead of relying on MDButtonText's
# default layout, which was reading as left/top-leaning. (2) the empty
# -state icon circle (clipboard glyph) is removed -- just the heading
# and subtext remain, centered on their own.

from kivymd.uix.screen import MDScreen
from kivymd.uix.label import MDLabel
from kivymd.uix.card import MDCard
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.boxlayout import MDBoxLayout
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.graphics import Color, Rectangle
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.utils import get_color_from_hex

from theme.theme_manager import theme_manager
from theme.themed_screen import ThemedScreenMixin
from theme.palettes import (
    BACKGROUND, TEXT_PRIMARY, TEXT_SECONDARY, CARD_PRIMARY, CARD_SECONDARY,
    ACCENT, BORDER, BUTTON, BUTTON_TEXT,
)

from widgets.checklist_card import ChecklistCard

from services.checklist_store import (
    create_checklist,
    get_all_checklists,
    get_checklist_item_counts,
    delete_checklist,
)


def theme_rgba(token):
    return get_color_from_hex(theme_manager.get_color(token))


def _build_themed_button(text, style, bg_token, text_token):
    """
    Builds one MDButton + MDButtonText with its fill/text color set at
    CONSTRUCTION time -- confirmed on-device that setting an MDButton's
    md_bg_color AFTER construction can get silently reverted to
    KivyMD's Material default on some later frame, for style="filled"/
    "tonal" buttons specifically. The caller is still responsible for
    scheduling a delayed re-apply (see _apply_popup_button_colors) as
    a safety net, same pattern used in checklist_detail_screen.py.

    halign/valign="center" set explicitly here -- MDButtonText's
    default layout was reading as left/top-leaning inside the tonal
    priority button, so this pins it dead-center both ways.
    """
    button_text = MDButtonText(
        text=text,
        theme_text_color="Custom",
        text_color=theme_manager.get_color(text_token),
        halign="center",
        valign="middle",
    )
    button = MDButton(
        button_text,
        style=style,
        theme_bg_color="Custom",
        md_bg_color=theme_manager.get_color(bg_token),
    )
    button._theme_bg_token = bg_token
    button._theme_text_token = text_token
    button._theme_text_widget = button_text
    return button


def _apply_popup_button_colors(*buttons):
    """
    Safety-net re-apply, called once immediately and once shortly
    after the popup opens -- style-driven MDButton fill colors have
    been observed reverting to Material defaults on a later frame
    even when set at construction.
    """
    for button in buttons:
        button.md_bg_color = theme_manager.get_color(button._theme_bg_token)
        button.theme_bg_color = "Custom"
        button._theme_text_widget.text_color = theme_manager.get_color(button._theme_text_token)
        button._theme_text_widget.theme_text_color = "Custom"


PRIORITY_OPTIONS = ("Low", "Medium", "High")

class ChecklistScreen(ThemedScreenMixin, MDScreen):

    THEME_MAP = {
        "self":           ("md_bg_color", BACKGROUND),
        "back_button":    ("icon_color", TEXT_PRIMARY),
        "header_label":   ("text_color", TEXT_PRIMARY),
        "subtitle_label": ("text_color", TEXT_SECONDARY),
        "add_bar_label":  ("text_color", TEXT_SECONDARY),
    }

    def on_pre_enter(self, *args):
        self.load_checklists()

    def on_theme_applied(self):
        border_color = self.ids.get("add_bar_border_color")
        if border_color is not None:
            border_color.rgba = theme_rgba(BORDER)

        add_button = self.ids.get("add_button")
        if add_button is not None:
            add_button.md_bg_color = theme_manager.get_color(BUTTON)
            add_button.icon_color = theme_manager.get_color(BUTTON_TEXT)

    def go_back(self):
        App.get_running_app().root.current = "home"

    def _user_id(self):
        try:
            app = App.get_running_app()
            return getattr(app, "user_id", 1)
        except Exception:
            return 1

    # ── loading the list ──

    def load_checklists(self):
        self.ids.checklist_list.clear_widgets()

        checklists = get_all_checklists(self._user_id())

        if not checklists:
            self.ids.checklist_list.add_widget(self._build_empty_state())
            return

        for checklist in checklists:
            self.ids.checklist_list.add_widget(self._build_card(checklist))

    def _build_empty_state(self):
        # Icon circle removed per your note -- just heading + subtext,
        # centered on their own, no clipboard glyph above them.
        container = MDBoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=[dp(20), dp(48), dp(20), dp(48)],
            size_hint_y=None,
            adaptive_height=True,
        )

        heading = Label(
            text="No checklists yet",
            font_size=sp(17), bold=True,
            color=theme_rgba(TEXT_PRIMARY),
            halign="center", valign="middle",
            size_hint_y=None, height=dp(26),
        )
        heading.bind(size=heading.setter("text_size"))
        container.add_widget(heading)

        subtext = Label(
            text="Create your first checklist.",
            font_size=sp(13),
            color=theme_rgba(TEXT_SECONDARY),
            halign="center", valign="middle",
            size_hint_y=None, height=dp(20),
        )
        subtext.bind(size=subtext.setter("text_size"))
        container.add_widget(subtext)

        return container

    def _build_card(self, checklist):
        total, checked = get_checklist_item_counts(checklist["id"])
        card = ChecklistCard(
            title=checklist["title"],
            priority=checklist["priority"],
            item_count=total,
            checked_count=checked,
            checklist_id=checklist["id"],
        )
        card.on_tap = self.open_checklist_detail
        card.on_delete = self.delete_checklist_confirm
        return card

    def open_checklist_detail(self, checklist_id):
        detail_screen = self.manager.get_screen("checklist_detail")
        detail_screen.checklist_id = checklist_id
        self.manager.current = "checklist_detail"

    def delete_checklist_confirm(self, checklist_id):
        delete_checklist(checklist_id)
        self.load_checklists()

    # ── "New Checklist" popup, restyled to match Timer Settings ──

    def _build_section_label(self, icon_name, text):
        row = MDBoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(24))

        icon = MDIconButton(
            icon=icon_name, theme_icon_color="Custom",
            icon_color=theme_rgba(ACCENT), disabled=True,
            size_hint=(None, None), size=(dp(20), dp(20)),
            pos_hint={"center_y": 0.5},
        )
        row.add_widget(icon)

        label = Label(text=text, font_size=sp(12), bold=True, color=theme_rgba(TEXT_SECONDARY),
                       halign="left", valign="middle", size_hint_x=1)
        label.bind(size=label.setter("text_size"))
        row.add_widget(label)

        return row

    def open_new_checklist_popup(self):
        panel = MDCard(
            orientation="vertical",
            theme_bg_color="Custom",
            md_bg_color=theme_manager.get_color(CARD_SECONDARY),
            padding=dp(20),
            spacing=dp(16),
            radius=[26],
            elevation=0,
        )

        # -- header: icon circle + title + close button --
        header = MDBoxLayout(orientation="horizontal", spacing=dp(12), size_hint_y=None, height=dp(48))

        icon_circle = MDCard(
            theme_bg_color="Custom",
            md_bg_color=theme_manager.get_color(CARD_PRIMARY),
            size_hint=(None, None), size=(dp(48), dp(48)),
            radius=[24],
            pos_hint={"center_y": 0.5},
        )
        icon_circle.add_widget(MDIconButton(
            icon="playlist-plus", theme_icon_color="Custom",
            icon_color=theme_manager.get_color(ACCENT), disabled=True,
            size_hint=(None, None), size=(dp(30), dp(30)),
            pos_hint={"center_x": 0.5, "center_y": 0.5},
        ))
        header.add_widget(icon_circle)

        title_label = Label(
            text="New Checklist", font_size=sp(19), bold=True,
            color=theme_rgba(TEXT_PRIMARY), halign="left", valign="middle", size_hint_x=1,
        )
        title_label.bind(size=title_label.setter("text_size"))
        header.add_widget(title_label)

        close_btn = MDIconButton(
            icon="close", theme_icon_color="Custom",
            icon_color=theme_rgba(TEXT_SECONDARY), pos_hint={"center_y": 0.5},
        )
        header.add_widget(close_btn)

        panel.add_widget(header)

        # -- divider --
        divider = Widget(size_hint_y=None, height=dp(1))
        with divider.canvas:
            Color(*theme_rgba(BORDER))
            divider_rect = Rectangle(pos=divider.pos, size=divider.size)

        def _redraw_divider(inst, *_a, _rect=divider_rect):
            _rect.pos = inst.pos
            _rect.size = inst.size

        divider.bind(pos=_redraw_divider, size=_redraw_divider)
        panel.add_widget(divider)

        # -- title input --
        title_input = TextInput(
            hint_text="Checklist title (e.g. Shopping List)",
            multiline=False,
            size_hint_y=None,
            height=dp(48),
            background_color=theme_rgba(BACKGROUND),
            foreground_color=theme_rgba(TEXT_PRIMARY),
            hint_text_color=theme_rgba(TEXT_SECONDARY),
            cursor_color=theme_rgba(ACCENT),
            padding=[dp(10), dp(12), dp(10), dp(12)],
        )
        panel.add_widget(title_input)

        # -- priority (optional) --
        panel.add_widget(self._build_section_label("flag-outline", "PRIORITY (OPTIONAL)"))

        priority_state = {"value": ""}
        priority_btn = _build_themed_button(
            "No priority set", style="tonal", bg_token=CARD_PRIMARY, text_token=TEXT_PRIMARY
        )
        priority_btn.size_hint_y = None
        priority_btn.height = dp(48)
        panel.add_widget(priority_btn)

        error_label = Label(
            text="", font_size=sp(11), color=theme_rgba(TEXT_SECONDARY),
            size_hint_y=None, height=dp(18), halign="left", valign="middle",
        )
        error_label.bind(size=error_label.setter("text_size"))
        panel.add_widget(error_label)

        # -- cancel / create --
        actions = MDBoxLayout(orientation="horizontal", spacing=dp(12), size_hint_y=None, height=dp(52))

        cancel_text = MDButtonText(text="CANCEL", theme_text_color="Custom", text_color=theme_rgba(TEXT_PRIMARY))
        cancel_btn = MDButton(
            cancel_text, style="outlined", theme_line_color="Custom",
            line_color=theme_rgba(BORDER),
            size_hint_x=1, height=dp(52), radius=[26],
        )
        actions.add_widget(cancel_btn)

        create_text = MDButtonText(text="CREATE", theme_text_color="Custom", text_color=theme_rgba(BUTTON_TEXT))
        create_btn = MDButton(
            create_text, style="filled", theme_bg_color="Custom", md_bg_color=theme_rgba(BUTTON),
            size_hint_x=1, height=dp(52), radius=[26],
        )
        create_btn._theme_bg_token = BUTTON
        create_btn._theme_text_token = BUTTON_TEXT
        create_btn._theme_text_widget = create_text
        cancel_btn._theme_bg_token = None
        actions.add_widget(create_btn)

        panel.add_widget(actions)

        popup = Popup(
            title="",
            content=panel,
            size_hint=(0.9, None),
            height=dp(430),
            auto_dismiss=False,
            separator_height=0,
            background="",
            background_color=(0, 0, 0, 0.5),
        )

        close_btn.bind(on_release=lambda *_a: popup.dismiss())
        cancel_btn.bind(on_release=lambda *_a: popup.dismiss())

        def set_priority_label():
            new_text = MDButtonText(
                text=priority_state["value"] or "No priority set",
                theme_text_color="Custom",
                text_color=theme_manager.get_color(TEXT_PRIMARY),
                halign="center",
                valign="middle",
            )
            priority_btn.clear_widgets()
            priority_btn.add_widget(new_text)
            priority_btn._theme_text_widget = new_text

        priority_btn.bind(
            on_release=lambda *_a: self._open_inline_priority_picker(priority_state, set_priority_label)
        )

        def do_create(*_args):
            title = title_input.text.strip()
            if not title:
                error_label.text = "Please enter a title."
                return
            create_checklist(
                title=title,
                priority=priority_state["value"],
                user_id=self._user_id(),
            )
            popup.dismiss()
            self.load_checklists()

        create_btn.bind(on_release=do_create)

        popup.open()

        # Safety-net re-apply -- priority_btn's text widget can be
        # swapped by set_priority_label(), so it's only included in
        # the delayed pass, not the immediate one.
        _apply_popup_button_colors(create_btn)
        Clock.schedule_once(lambda dt: _apply_popup_button_colors(create_btn, priority_btn), 0.3)

    def _open_inline_priority_picker(self, priority_state, on_chosen):
        panel = MDCard(
            orientation="vertical",
            padding=dp(16),
            spacing=dp(8),
            theme_bg_color="Custom",
            md_bg_color=theme_manager.get_color(CARD_PRIMARY),
            radius=[18],
        )
        title = Label(
            text="Choose Priority",
            font_size=sp(15),
            bold=True,
            color=theme_rgba(TEXT_PRIMARY),
            size_hint_y=None,
            height=dp(28),
            halign="left",
            valign="middle",
        )
        title.bind(size=title.setter("text_size"))
        panel.add_widget(title)

        inner_popup = Popup(
            title="",
            content=panel,
            size_hint=(0.7, None),
            height=dp(260),
            auto_dismiss=True,
            separator_height=0,
            background="",
            background_color=(0, 0, 0, 0),
        )

        def choose(value):
            priority_state["value"] = value
            on_chosen()
            inner_popup.dismiss()

        none_btn = MDButton(style="tonal", on_release=lambda *_a: choose(""))
        none_btn.add_widget(MDButtonText(text="No priority"))
        panel.add_widget(none_btn)

        for value in PRIORITY_OPTIONS:
            btn = MDButton(style="tonal", on_release=lambda *_a, v=value: choose(v))
            btn.add_widget(MDButtonText(text=value))
            panel.add_widget(btn)

        inner_popup.open()
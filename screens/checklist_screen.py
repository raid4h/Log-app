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
# ("No priority set" / a chosen priority) is explicitly centered, both
# horizontally and vertically. (2) the empty-state icon circle
# (clipboard glyph) is removed -- just the heading and subtext remain.
# (3) the popup itself is restyled to match calendar_screen.py's Add
# Reminder popup: plain bold left-aligned heading, no avatar icon
# circle, no X close button, no divider line -- and the title field
# switched from a plain TextInput to an outlined MDTextField, same
# component and visual style Calendar's own popup uses, for a
# consistent look between the two features' "add" dialogs.

from kivymd.uix.screen import MDScreen
from kivymd.uix.label import MDLabel
from kivymd.uix.card import MDCard
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.textfield import MDTextField, MDTextFieldHintText
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
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


def _themed_text_field(hint, text=""):
    """
    Outlined themed text field -- same component and visual style as
    calendar_screen.py's own _themed_text_field, duplicated here
    (rather than imported cross-screen) since screens are kept
    independent of each other. Used for the "New Checklist" popup's
    title input, so both features' "add" popups share one consistent
    field look.
    """
    field = MDTextField(
        text=text,
        mode="outlined",
        size_hint_y=None,
        height=dp(52),
        theme_bg_color="Custom",
        md_bg_color=theme_rgba(CARD_SECONDARY),
        line_color_normal=theme_rgba(BORDER),
        line_color_focus=theme_rgba(ACCENT),
        theme_text_color="Custom",
        text_color_normal=theme_rgba(TEXT_PRIMARY),
        text_color_focus=theme_rgba(TEXT_PRIMARY),
    )

    hint_label = MDTextFieldHintText(
        text=hint,
        theme_text_color="Custom",
        text_color_normal=theme_rgba(TEXT_SECONDARY),
        text_color_focus=theme_rgba(TEXT_SECONDARY),
    )
    field.add_widget(hint_label)

    def _refresh(*_args):
        field.md_bg_color = theme_rgba(CARD_SECONDARY)
        field.line_color_normal = theme_rgba(BORDER)
        field.line_color_focus = theme_rgba(ACCENT)
        field.text_color_normal = theme_rgba(TEXT_PRIMARY)
        field.text_color_focus = theme_rgba(TEXT_PRIMARY)
        hint_label.text_color_normal = theme_rgba(TEXT_SECONDARY)
        hint_label.text_color_focus = theme_rgba(TEXT_SECONDARY)

    theme_manager.bind(theme_name=_refresh)
    return field


def _build_themed_button(text, style, bg_token, text_token, line_token=None):
    """
    Builds one MDButton + MDButtonText with its fill/text color set at
    CONSTRUCTION time -- confirmed on-device that setting an MDButton's
    md_bg_color AFTER construction can get silently reverted to
    KivyMD's Material default on some later frame, for style="filled"/
    "tonal" buttons specifically. The caller is still responsible for
    scheduling a delayed re-apply (see _apply_popup_button_colors) as
    a safety net.

    line_token, if given, sets a themed border color -- matches
    calendar_screen.py's tonal buttons, which draw a BORDER-colored
    outline.
    """
    button_text = MDButtonText(
        text=text,
        theme_text_color="Custom",
        text_color=theme_manager.get_color(text_token),
        halign="center",
        valign="middle",
    )
    kwargs = dict(
        style=style,
        theme_bg_color="Custom",
        md_bg_color=theme_manager.get_color(bg_token),
    )
    if line_token is not None:
        kwargs["theme_line_color"] = "Custom"
        kwargs["line_color"] = theme_manager.get_color(line_token)
    button = MDButton(button_text, **kwargs)
    button._theme_bg_token = bg_token
    button._theme_text_token = text_token
    button._theme_text_widget = button_text
    button._theme_line_token = line_token
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
        if getattr(button, "_theme_line_token", None) is not None:
            button.line_color = theme_manager.get_color(button._theme_line_token)
            button.theme_line_color = "Custom"


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

    # ── "New Checklist" popup -- matches calendar_screen.py's Add
    # Reminder popup: plain card, bold left-aligned heading, no avatar
    # icon, no close button, no divider. ──

    def open_new_checklist_popup(self):
        panel = MDCard(
            orientation="vertical",
            padding=[dp(16), dp(16), dp(16), dp(16)],
            spacing=dp(10),
            size_hint=(1, 1),
            theme_bg_color="Custom",
            md_bg_color=theme_rgba(CARD_PRIMARY),
            radius=[18],
        )

        heading = Label(
            text="New Checklist",
            font_size=sp(18),
            bold=True,
            color=theme_rgba(TEXT_PRIMARY),
            size_hint_y=None,
            height=dp(32),
            halign="left",
            valign="middle",
        )
        heading.bind(size=heading.setter("text_size"))
        panel.add_widget(heading)

        title_input = _themed_text_field("Checklist title (e.g. Shopping List)")
        panel.add_widget(title_input)

        priority_label = Label(
            text="Priority (optional)",
            font_size=sp(12),
            color=theme_rgba(TEXT_SECONDARY),
            size_hint_y=None,
            height=dp(22),
            halign="left",
            valign="middle",
        )
        priority_label.bind(size=priority_label.setter("text_size"))
        panel.add_widget(priority_label)

        priority_state = {"value": ""}
        priority_btn = _build_themed_button(
            "No priority set", style="tonal",
            bg_token=CARD_SECONDARY, text_token=TEXT_PRIMARY, line_token=BORDER,
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

        actions = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(8))

        cancel_btn = _build_themed_button(
            "Cancel", style="tonal", bg_token=CARD_SECONDARY, text_token=TEXT_PRIMARY, line_token=BORDER,
        )
        actions.add_widget(cancel_btn)

        create_btn = _build_themed_button(
            "Create", style="filled", bg_token=BUTTON, text_token=BUTTON_TEXT,
        )
        actions.add_widget(create_btn)

        panel.add_widget(actions)

        popup = Popup(
            title="",
            content=panel,
            size_hint=(0.94, None),
            height=dp(360),
            auto_dismiss=True,
            separator_height=0,
            background="",
            background_color=(0, 0, 0, 0),
        )

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

        _apply_popup_button_colors(cancel_btn, create_btn)
        Clock.schedule_once(
            lambda dt: _apply_popup_button_colors(cancel_btn, create_btn, priority_btn), 0.3
        )

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
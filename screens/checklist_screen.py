# screens/checklist_screen.py
#
# Main Checklist screen -- shows every checklist as a summary card
# (widgets/checklist_card.py). Tapping a card opens its items on
# screens/checklist_detail_screen.py. The add bar creates a new
# checklist (title, optional category, optional priority) rather than
# adding an item directly -- items are added inside the detail screen.
#
# Categories are user-defined and SHARED with the rest of the app via
# database/category_queries.py (the same table tasks/calendar use) --
# this file only ever calls its existing functions, never edits it.

from kivymd.uix.screen import MDScreen
from kivymd.uix.label import MDLabel
from kivymd.uix.card import MDCard
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.boxlayout import MDBoxLayout
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.utils import get_color_from_hex

from theme.theme_manager import theme_manager
from theme.themed_screen import ThemedScreenMixin
from theme.palettes import (
    BACKGROUND, TEXT_PRIMARY, TEXT_SECONDARY, CARD_PRIMARY,
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
        # add_bar's dashed border color and add_button's fill/icon
        # color both need more than THEME_MAP's one-property-per-id
        # can give a single MDIconButton, and the border is a raw
        # canvas Color instruction (not a widget property at all) --
        # same reasoning as every other custom-drawn theme element
        # in this app (dividers, dashboard tiles' accent dots, etc).
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
        """
        Icon-in-soft-circle + bold heading + secondary line, matching
        the reference image's empty state -- same information as the
        old single-line label ("no checklists yet, create one"), just
        laid out with more visual presence.
        """
        container = MDBoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=[dp(20), dp(36), dp(20), dp(36)],
            size_hint_y=None,
            adaptive_height=True,
        )

        icon_wrapper = AnchorLayout(
            anchor_x="center", anchor_y="center",
            size_hint_y=None, height=dp(96),
        )
        icon_circle = MDCard(
            theme_bg_color="Custom",
            md_bg_color=theme_manager.get_color(CARD_PRIMARY),
            size_hint=(None, None), size=(dp(88), dp(88)),
            radius=[44],
            elevation=0,
        )
        icon_circle.add_widget(MDIconButton(
            icon="clipboard-text-outline",
            theme_icon_color="Custom",
            icon_color=theme_manager.get_color(ACCENT),
            disabled=True,
            size_hint=(None, None), size=(dp(48), dp(48)),
            pos_hint={"center_x": 0.5, "center_y": 0.5},
        ))
        icon_wrapper.add_widget(icon_circle)
        container.add_widget(icon_wrapper)

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
        # Single tap on the trash icon deletes immediately -- no
        # separate confirmation popup, keeping this feature simple
        # per your instruction. If accidental deletes turn out to be
        # a problem in testing, an "Undo" snackbar would be the
        # lightest fix to add later.
        delete_checklist(checklist_id)
        self.load_checklists()

    # ── "+ New Checklist" popup ──

    def open_new_checklist_popup(self):
        panel = MDCard(
            orientation="vertical",
            padding=dp(18),
            spacing=dp(10),
            theme_bg_color="Custom",
            md_bg_color=theme_manager.get_color(CARD_PRIMARY),
            radius=[18],
        )

        heading = Label(
            text="New Checklist",
            font_size=sp(17),
            bold=True,
            color=theme_rgba(TEXT_PRIMARY),
            size_hint_y=None,
            height=dp(30),
            halign="left",
            valign="middle",
        )
        heading.bind(size=heading.setter("text_size"))
        panel.add_widget(heading)

        title_input = TextInput(
            hint_text="Checklist title (e.g. Shopping List)",
            multiline=False,
            size_hint_y=None,
            height=dp(46),
        )
        panel.add_widget(title_input)

        # -- priority picker row --
        priority_state = {"value": ""}
        priority_btn = MDButton(style="tonal", size_hint_y=None, height=dp(44))
        priority_btn.add_widget(MDButtonText(text="+ Priority (optional)"))
        panel.add_widget(priority_btn)

        error_label = Label(
            text="",
            font_size=sp(10),
            color=theme_rgba(TEXT_PRIMARY),
            size_hint_y=None,
            height=dp(20),
        )
        panel.add_widget(error_label)

        actions = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(8))

        popup = Popup(
            title="",
            content=panel,
            size_hint=(0.85, None),
            height=dp(340),
            auto_dismiss=False,
            separator_height=0,
            background="",
            background_color=(0, 0, 0, 0),
        )

        def set_priority_label():
            text = priority_state["value"] or "+ Priority (optional)"
            priority_btn.clear_widgets()
            priority_btn.add_widget(MDButtonText(text=text))


        priority_btn.bind(
            on_release=lambda *_a: self._open_inline_priority_picker(
                priority_state, set_priority_label
            )
        )

        cancel_btn = MDButton(style="tonal", on_release=lambda *_a: popup.dismiss())
        cancel_btn.add_widget(MDButtonText(text="Cancel"))
        actions.add_widget(cancel_btn)

        create_btn = MDButton(style="filled")
        create_btn.add_widget(MDButtonText(text="Create"))
        actions.add_widget(create_btn)

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
        panel.add_widget(actions)
        popup.open()

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
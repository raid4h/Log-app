# screens/checklist_detail_screen.py
#
# Shows the items (and sub-items) belonging to ONE checklist, opened
# by tapping a card on screens/checklist_screen.py. Items are split
# into an "active" list and a collapsible "N Checked Items" section,
# matching the reference layout -- checked items stay visible but
# tucked away until the user taps to expand them. Also lets the user
# edit the checklist's own title/priority via the pencil icon.
#
# v2: three new OPT-IN toggles/actions added to the edit popup, all
# per-checklist and OFF by default (see services/checklist_store.py's
# module docstring for the full storage-level rules):
#   - "Calculate Prices" switch -- the running-total calculator
#     (screens/editor/calculator.py) now only runs when this is on.
#     Previously it always ran automatically.
#   - "Add to Calendar" button -- opens a small date/time picker and
#     creates ONE calendar event titled after the checklist, linking
#     it via checklist_store.set_checklist_calendar_event(). Tapping
#     it again while already linked lets the user change or remove
#     the link.
#   - "Show in Today's Log" switch -- toggles
#     checklist_store.set_add_to_logs(). Whether items then show every
#     day or only on the linked calendar date is decided by
#     database/planner_queries.py, not this screen -- this screen only
#     sets the flag.
#
# Also runs the same calculator pass the note editor uses on note
# text (screens/editor/calculator.py) across every item's text, so a
# checklist doubling as a shopping list ("Milk 4.99", "Eggs 3.50")
# gets a running total for free -- a plain to-do checklist with no
# numbers in it just shows nothing, same "only appears if there's
# something to show" rule the note editor's grand total already uses.
# NOW GATED behind the checklist's own calculate_prices flag (see v2
# note above) rather than always running.
#
# No category anywhere in this feature -- the checklist's title is
# already the categorization, per your last change.
#
# FIX: the running-total label previously lived inside top_bar's
# fixed dp(64) title column (built and inserted from Python via
# _ensure_total_label), sharing space with header_label/subtitle_label.
# As the total's height changed with every item add/remove, that
# fixed-height box got squeezed and the checklist title visibly
# shifted position. It's now declared directly in the .kv file as
# total_label, inside content_column (adaptive_height, not fixed),
# so it can grow/shrink freely without moving anything in the header.
#
# FIX: the "N Checked Items" collapsible header's expand/collapse
# indicator was drawn as a raw Unicode triangle (\u25b8/\u25be) via a
# plain Label -- the app's font doesn't include those glyphs, so it
# rendered as a "tofu" placeholder box instead of an actual arrow.
# Replaced with a real MDIconButton (chevron-right/chevron-down),
# matching the same icon already used correctly for sub-item
# expansion in widgets/checklist_item.py, for both a working icon and
# a consistent expand/collapse visual language across the screen.
#
# FIX (crash): MDSwitch(active=initial_active, ...) crashed on
# construction -- passing active as a constructor kwarg fires
# on_active immediately, before the switch's own .kv-defined ids
# (ids.thumb) exist yet, since on_active tries to animate that thumb
# widget. Constructing with no active kwarg, then setting .active as
# a separate line afterward, avoids firing the callback before the
# widget is fully built.
#
# FIX (alignment): the priority button and the "Add to Calendar"
# button's text were rendering left-biased instead of centered,
# despite halign="center"/valign="middle" being set -- Kivy's
# halign/valign only take effect once text_size gives the label a
# fixed box to align WITHIN. text_size is now bound to each
# button-text widget's own size, so centering actually works.
#
# UI pass: edit popup restyled to match the confirmed reference --
# fully pill-shaped buttons/priority badge (radius = height/2 instead
# of a flat corner radius), a larger panel corner radius, and more
# vertical breathing room between each row/section. Purely spacing
# and radius values -- no layout structure, logic, or button behavior
# changed.

from datetime import datetime

from kivymd.uix.screen import MDScreen
from kivymd.uix.label import MDLabel
from kivymd.uix.card import MDCard
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.selectioncontrol import MDSwitch
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.properties import NumericProperty
from kivy.metrics import dp, sp
from kivy.utils import get_color_from_hex
from kivy.clock import Clock

from theme.theme_manager import theme_manager
from theme.themed_screen import ThemedScreenMixin
from theme.palettes import BACKGROUND, TEXT_PRIMARY, TEXT_SECONDARY, CARD_PRIMARY, ACCENT, BORDER, BUTTON, BUTTON_TEXT

from widgets.checklist_item import ChecklistItem  # noqa: F401

from services.checklist_store import (
    create_checklist_item,
    get_checklist_by_id,
    get_items_by_checklist,
    get_subtasks,
    set_checked,
    update_checklist,
    delete_checklist_item,
    set_calculate_prices,
    set_add_to_logs,
    set_checklist_calendar_event,
)

from database.calendar_queries import create_event, delete_event

from screens.editor.calculator import process_calculator_lines, format_calculated_number


# Standard height for every pill-shaped control in this screen's edit
# popup (priority badge, Add to Calendar, Cancel/Save) -- keeping one
# constant means every pill's radius (height/2, computed per-button
# below) stays visually consistent instead of drifting if one row's
# height is tweaked independently later.
_PILL_HEIGHT = dp(52)


def theme_rgba(token):
    return get_color_from_hex(theme_manager.get_color(token))


def _build_themed_button(text, style, bg_token, text_token):
    """
    Builds one MDButton + MDButtonText with its fill/text color set at
    CONSTRUCTION time -- confirmed on-device (timer_screen.py's Focus
    Timer Settings dialog) that setting an MDButton's md_bg_color
    AFTER construction can get silently reverted to KivyMD's Material
    default on some later frame, for style="filled"/"tonal" buttons
    specifically. Setting it as a constructor kwarg instead avoids
    that for the vast majority of cases; the caller is still
    responsible for scheduling a delayed re-apply (see
    _apply_popup_button_colors below) as a safety net, same pattern
    used there.

    FIX: text_size is now bound to the button text's own size, so
    halign="center"/valign="middle" (set below) actually take effect
    -- see the module docstring's FIX (alignment) note.

    UI: radius is now [_PILL_HEIGHT / 2] -- a true pill shape, height/
    2 rounding on a height=_PILL_HEIGHT button, matching the reference
    design. Callers that need a different height should override
    radius accordingly after construction.
    """
    button_text = MDButtonText(
        text=text,
        theme_text_color="Custom",
        text_color=theme_manager.get_color(text_token),
        halign="center",
        valign="middle",
    )
    button_text.bind(size=lambda inst, val: setattr(inst, "text_size", val))
    button = MDButton(
        button_text,
        style=style,
        theme_bg_color="Custom",
        md_bg_color=theme_manager.get_color(bg_token),
        size_hint_y=None,
        height=_PILL_HEIGHT,
        radius=[_PILL_HEIGHT / 2],
    )
    button._theme_bg_token = bg_token
    button._theme_text_token = text_token
    button._theme_text_widget = button_text
    return button


def _apply_popup_button_colors(*buttons):
    """
    Safety-net re-apply, called once immediately and once shortly
    after the popup opens -- same reasoning as timer_screen.py's
    dialog: style-driven MDButton fill colors have been observed to
    revert to Material defaults on a later frame even when set at
    construction, so the last write needs to happen after that frame
    has passed, not before it.
    """
    for button in buttons:
        button.md_bg_color = theme_manager.get_color(button._theme_bg_token)
        button.theme_bg_color = "Custom"
        button._theme_text_widget.text_color = theme_manager.get_color(button._theme_text_token)
        button._theme_text_widget.theme_text_color = "Custom"


def _build_toggle_row(label_text, initial_active, on_change):
    """
    One switch row matching calendar_screen.py's "Repeat daily until
    marked done" style -- a label on the left, an MDSwitch on the
    right. Used for both new switches in this screen's edit popup
    ("Calculate Prices", "Show in Today's Log").

    FIX: MDSwitch(active=initial_active, ...) crashed on construction
    -- passing active as a constructor kwarg fires on_active
    immediately, before the switch's own .kv-defined ids (ids.thumb)
    exist yet, since on_active tries to animate that thumb widget.
    Constructing with no active kwarg, then setting .active as a
    separate line afterward, avoids firing the callback before the
    widget is fully built.
    """
    row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(8))

    label = Label(
        text=label_text,
        font_size=sp(14.5),
        bold=True,
        color=theme_rgba(TEXT_SECONDARY),
        halign="left",
        valign="middle",
        size_hint_x=1,
    )
    label.bind(size=label.setter("text_size"))
    row.add_widget(label)

    switch = MDSwitch(pos_hint={"center_y": 0.5})
    switch.active = initial_active
    switch.bind(active=lambda _inst, value: on_change(value))
    row.add_widget(switch)

    return row, label


PRIORITY_OPTIONS = ("Low", "Medium", "High")


class _TappableRow(ButtonBehavior, BoxLayout):
    """Generic tappable row -- used for the 'N Checked Items' toggle header."""
    pass


class ChecklistDetailScreen(ThemedScreenMixin, MDScreen):

    checklist_id = NumericProperty(0)

    THEME_MAP = {
        "self":           ("md_bg_color", BACKGROUND),
        "back_button":    ("icon_color", TEXT_PRIMARY),
        "header_label":   ("text_color", TEXT_PRIMARY),
        "subtitle_label": ("text_color", TEXT_SECONDARY),
        "section_label":  ("text_color", TEXT_SECONDARY),
        "total_label":    ("text_color", TEXT_PRIMARY),
    }

    def __init__(self, **kwargs):
        self._checked_expanded = False
        super().__init__(**kwargs)

    def on_pre_enter(self, *args):
        self._checked_expanded = False
        self.load_checklist()

    def on_theme_applied(self):
        pass

    def go_back(self):
        self.manager.current = "checklist"

    def _user_id(self):
        from kivy.app import App
        try:
            app = App.get_running_app()
            return getattr(app, "user_id", 1)
        except Exception:
            return 1

    # ── loading ──

    def load_checklist(self):
        checklist = get_checklist_by_id(self.checklist_id)
        if checklist is None:
            self.go_back()
            return

        self.ids.header_label.text = checklist["title"]
        self.ids.subtitle_label.text = (
            f"{checklist['priority']} priority" if checklist["priority"] else "Tap the pencil to edit"
        )

        self.load_items()

    def load_items(self):
        items = get_items_by_checklist(self.checklist_id)
        active_items = [item for item in items if not item["checked"]]
        checked_items = [item for item in items if item["checked"]]

        # -- active items + inline "add another item" row --
        item_list = self.ids.item_list
        item_list.clear_widgets()

        if not active_items and not checked_items:
            item_list.add_widget(self._build_empty_label())
        else:
            for item in active_items:
                item_list.add_widget(self._build_item_row(item))

        item_list.add_widget(self._build_add_item_row())

        # -- collapsible checked section --
        checked_section = self.ids.checked_section
        checked_section.clear_widgets()

        if checked_items:
            checked_section.add_widget(self._build_checked_header(len(checked_items)))
            if self._checked_expanded:
                for item in checked_items:
                    checked_section.add_widget(self._build_item_row(item))

        # -- running total (see module docstring) -- only when the
        # checklist has calculate_prices turned on.
        checklist = get_checklist_by_id(self.checklist_id)
        if checklist and checklist.get("calculate_prices"):
            self._update_total(active_items)
        else:
            total_label = self.ids.total_label
            total_label.text = ""
            total_label.height = 0

    def _update_total(self, items):
        # get_items_by_checklist only returns top-level items -- that's
        # deliberate here too, same as get_checklist_item_counts on the
        # list screen: sub-item text (e.g. "2%" under "Milk") isn't
        # priced separately in this feature, so only top-level rows
        # feed the calculator.
        combined_text = "\n".join(item["text"] for item in items)
        _display_text, grand_total, uses_currency = process_calculator_lines(combined_text)

        total_label = self.ids.total_label
        if grand_total is None:
            total_label.text = ""
            total_label.height = 0
        else:
            currency_prefix = "$" if uses_currency else ""
            total_label.text = f"Total: {currency_prefix}{format_calculated_number(grand_total)}"
            total_label.texture_update()
            total_label.height = total_label.texture_size[1] + dp(6)

    def _build_empty_label(self):
        return MDLabel(
            text="No items yet -- add one below.",
            halign="center",
            theme_text_color="Custom",
            text_color=theme_manager.get_color(TEXT_SECONDARY),
            size_hint_y=None,
            height=dp(56),
        )

    # ── one item row: checkbox/title (ChecklistItem) + delete button ──

    def _build_item_row(self, item):
        item_widget = ChecklistItem(
            text=item["text"],
            checked=item["checked"],
        )
        item_widget.item_id = item["id"]

        subtasks = get_subtasks(item["id"])
        item_widget.subtasks = [
            {"id": s["id"], "text": s["text"], "checked": s["checked"]}
            for s in subtasks
        ]
        item_widget.bind(
            subtasks=lambda inst, val, iid=item["id"]: self._on_subtasks_changed(iid, val)
        )
        item_widget.on_toggle_complete = lambda checked, iid=item["id"]: self._toggle_item(iid, checked)

        # Extra breathing room between the item card and its delete
        # button, and a little right-side padding so the ✕ doesn't
        # crowd the screen edge -- purely spacing, same widgets/logic.
        row = BoxLayout(orientation="horizontal", size_hint_y=None, spacing=dp(6), padding=[0, 0, dp(4), 0])
        row.add_widget(item_widget)

        # AnchorLayout keeps the delete button pinned to the TOP of the
        # row regardless of how tall item_widget grows when its
        # sub-items are expanded -- a plain pos_hint on the button
        # alone would center it against the whole row's height instead.
        # A small top padding nudges the ✕ down so its visual center
        # lines up with the checkbox/title line instead of the card's
        # bare top edge.
        delete_anchor = AnchorLayout(
            size_hint=(None, 1), width=dp(36), anchor_x="center", anchor_y="top",
            padding=(0, dp(10), 0, 0),
        )
        delete_btn = MDIconButton(
            icon="close",
            theme_icon_color="Custom",
            icon_color=theme_rgba(TEXT_SECONDARY),
            size_hint=(None, None),
            size=(dp(30), dp(30)),
        )
        delete_btn.bind(on_release=lambda *_a, iid=item["id"]: self._delete_item(iid))
        delete_anchor.add_widget(delete_btn)
        row.add_widget(delete_anchor)

        item_widget.bind(height=lambda _inst, val: setattr(row, "height", val))
        row.height = item_widget.height

        return row

    def _toggle_item(self, item_id, checked):
        set_checked(item_id, checked)
        # An item moves between the active list and the checked
        # section the moment it's toggled, so the whole screen
        # rebuilds rather than just flipping a strikethrough in place.
        self.load_items()

    def _delete_item(self, item_id):
        delete_checklist_item(item_id)
        self.load_items()

    def _on_subtasks_changed(self, parent_id, subtasks):
        for subtask in subtasks:
            if "id" in subtask:
                set_checked(subtask["id"], subtask["checked"])
            else:
                new_id = create_checklist_item(self.checklist_id, subtask["text"], parent_id=parent_id)
                subtask["id"] = new_id

    # ── inline "add another item" row ──

    def _build_add_item_row(self):
        row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(10),
            padding=[dp(16), 0, dp(14), 0],
        )

        plus_label = Label(
            text="+",
            font_size=sp(19),
            bold=True,
            color=theme_rgba(ACCENT),
            size_hint=(None, None),
            size=(dp(20), dp(48)),
            valign="middle",
            halign="center",
        )
        plus_label.bind(size=plus_label.setter("text_size"))
        row.add_widget(plus_label)

        self._new_item_input = TextInput(
            hint_text="Add another item",
            multiline=False,
            size_hint_y=None,
            height=dp(40),
            background_color=(0, 0, 0, 0),
            foreground_color=theme_rgba(TEXT_PRIMARY),
            hint_text_color=theme_rgba(TEXT_SECONDARY),
            cursor_color=theme_rgba(ACCENT),
            font_size=sp(14.5),
            padding=[0, dp(10), 0, dp(10)],
            pos_hint={"center_y": 0.5},
        )
        self._new_item_input.bind(on_text_validate=lambda *_a: self._submit_new_item())
        row.add_widget(self._new_item_input)

        add_btn = MDIconButton(
            icon="plus",
            theme_icon_color="Custom",
            theme_bg_color="Custom",
            md_bg_color=theme_manager.get_color(BUTTON),
            icon_color=theme_manager.get_color(BUTTON_TEXT),
            radius=[10],
            size_hint=(None, None),
            size=(dp(40), dp(40)),
            pos_hint={"center_y": 0.5},
        )
        add_btn.bind(on_release=lambda *_a: self._submit_new_item())
        row.add_widget(add_btn)

        def _reapply_add_btn_theme(*_a):
            add_btn.md_bg_color = theme_manager.get_color(BUTTON)
            add_btn.icon_color = theme_manager.get_color(BUTTON_TEXT)

        Clock.schedule_once(_reapply_add_btn_theme, 0.3)
        theme_manager.bind(theme_name=_reapply_add_btn_theme)

        return row

    def _submit_new_item(self):
        text = self._new_item_input.text.strip()
        if not text:
            return
        create_checklist_item(self.checklist_id, text)
        self.load_items()

    # ── collapsible "N Checked Items" header ──

    def _build_checked_header(self, count):
        row = _TappableRow(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(42),
            spacing=dp(8),
            padding=[dp(10), 0, dp(10), 0],
        )

        chevron_btn = MDIconButton(
            icon="chevron-down" if self._checked_expanded else "chevron-right",
            theme_icon_color="Custom",
            icon_color=theme_rgba(TEXT_SECONDARY),
            size_hint=(None, None),
            size=(dp(30), dp(30)),
            pos_hint={"center_y": 0.5},
        )
        # The icon button consumes its own tap before it can reach the
        # row's on_release below -- tapping directly on the arrow was
        # doing nothing, only tapping the "N Checked Items" text
        # worked. Binding the same toggle function here directly means
        # both areas now do the same thing explicitly, rather than
        # relying on one event bubbling up into the other.
        chevron_btn.bind(on_release=lambda *_a: self._toggle_checked_section())
        row.add_widget(chevron_btn)

        label = Label(
            text=f"{count} Checked Item{'s' if count != 1 else ''}",
            font_size=sp(12.5),
            bold=True,
            color=theme_rgba(TEXT_SECONDARY),
            halign="left",
            valign="middle",
            size_hint_x=1,
        )
        label.bind(size=label.setter("text_size"))
        row.add_widget(label)

        row.bind(on_release=lambda *_a: self._toggle_checked_section())
        return row

    def _toggle_checked_section(self):
        self._checked_expanded = not self._checked_expanded
        self.load_items()

    # ── editing the checklist's own title/priority + v2 toggles ──

    def open_edit_checklist_popup(self):
        checklist = get_checklist_by_id(self.checklist_id)
        if checklist is None:
            return

        panel = MDCard(
            orientation="vertical",
            padding=dp(22),
            spacing=dp(20),
            theme_bg_color="Custom",
            md_bg_color=theme_manager.get_color(CARD_PRIMARY),
            radius=[28],
        )

        heading = Label(
            text="Edit Checklist",
            font_size=sp(22),
            bold=True,
            color=theme_rgba(TEXT_PRIMARY),
            size_hint_y=None,
            height=dp(34),
            halign="left",
            valign="middle",
        )
        heading.bind(size=heading.setter("text_size"))
        panel.add_widget(heading)

        title_input = TextInput(
            text=checklist["title"],
            multiline=False,
            size_hint_y=None,
            height=_PILL_HEIGHT,
            background_color=theme_rgba(BACKGROUND),
            foreground_color=theme_rgba(TEXT_PRIMARY),
            cursor_color=theme_rgba(ACCENT),
            font_size=sp(15),
            padding=[dp(14), dp(14), dp(14), dp(14)],
        )
        panel.add_widget(title_input)

        priority_state = {"value": checklist["priority"]}
        priority_btn = _build_themed_button(
            priority_state["value"] or "+ Priority (optional)",
            style="tonal",
            bg_token=BORDER,
            text_token=TEXT_PRIMARY,
        )
        panel.add_widget(priority_btn)

        # -- v2: Calculate Prices switch --
        calc_row, calc_label = _build_toggle_row(
            "Calculate Prices",
            checklist.get("calculate_prices", False),
            lambda value: set_calculate_prices(self.checklist_id, value),
        )
        panel.add_widget(calc_row)

        # -- v2: Add to Calendar button --
        calendar_button_state = {"linked": checklist.get("calendar_event_id") is not None}
        calendar_btn = _build_themed_button(
            "Remove from Calendar" if calendar_button_state["linked"] else "Add to Calendar",
            style="tonal",
            bg_token=BORDER,
            text_token=TEXT_PRIMARY,
        )

        def _refresh_calendar_button_label():
            new_text = MDButtonText(
                text="Remove from Calendar" if calendar_button_state["linked"] else "Add to Calendar",
                theme_text_color="Custom",
                text_color=theme_manager.get_color(TEXT_PRIMARY),
                halign="center",
                valign="middle",
            )
            new_text.bind(size=lambda inst, val: setattr(inst, "text_size", val))
            calendar_btn.clear_widgets()
            calendar_btn.add_widget(new_text)
            calendar_btn._theme_text_widget = new_text

        def _on_calendar_button(*_a):
            if calendar_button_state["linked"]:
                self._remove_checklist_from_calendar(checklist)
                calendar_button_state["linked"] = False
                _refresh_calendar_button_label()
            else:
                self._open_add_to_calendar_popup(checklist, calendar_button_state, _refresh_calendar_button_label)

        calendar_btn.bind(on_release=_on_calendar_button)
        panel.add_widget(calendar_btn)

        # -- v2: Show in Today's Log switch --
        logs_row, logs_label = _build_toggle_row(
            "Show in Today's Log",
            checklist.get("add_to_logs", False),
            lambda value: set_add_to_logs(self.checklist_id, value),
        )
        panel.add_widget(logs_row)

        actions = BoxLayout(orientation="horizontal", size_hint_y=None, height=_PILL_HEIGHT, spacing=dp(12))

        popup = Popup(
            title="",
            content=panel,
            size_hint=(0.88, None),
            height=dp(560),
            auto_dismiss=False,
            separator_height=0,
            background="",
            background_color=(0, 0, 0, 0),
        )

        def set_priority_label():
            # Rebuilds the button's text widget (same approach the
            # original code used) -- has to re-register it as
            # priority_btn._theme_text_widget too, or a later
            # _apply_popup_button_colors() call would still be
            # pointing at the OLD (now-discarded) text widget instead
            # of this new one.
            new_text = MDButtonText(
                text=priority_state["value"] or "+ Priority (optional)",
                theme_text_color="Custom",
                text_color=theme_manager.get_color(TEXT_PRIMARY),
                halign="center",
                valign="middle",
            )
            new_text.bind(size=lambda inst, val: setattr(inst, "text_size", val))
            priority_btn.clear_widgets()
            priority_btn.add_widget(new_text)
            priority_btn._theme_text_widget = new_text

        priority_btn.bind(
            on_release=lambda *_a: self._open_inline_priority_picker(priority_state, set_priority_label)
        )

        cancel_btn = _build_themed_button(
            "Cancel", style="tonal", bg_token=BORDER, text_token=TEXT_PRIMARY
        )
        actions.add_widget(cancel_btn)

        save_btn = _build_themed_button(
            "Save", style="filled", bg_token=BUTTON, text_token=BUTTON_TEXT
        )
        actions.add_widget(save_btn)

        cancel_btn.bind(on_release=lambda *_a: popup.dismiss())

        def do_save(*_args):
            title = title_input.text.strip() or checklist["title"]
            update_checklist(
                self.checklist_id,
                title=title,
                priority=priority_state["value"],
            )
            popup.dismiss()
            self.load_checklist()

        save_btn.bind(on_release=do_save)
        panel.add_widget(actions)
        popup.open()

        # Safety-net re-apply -- see _apply_popup_button_colors
        # docstring. priority_btn/calendar_btn aren't included here
        # since their text widgets can get swapped out by
        # set_priority_label()/_refresh_calendar_button_label(), and
        # this runs before the user could have triggered either.
        _apply_popup_button_colors(cancel_btn, save_btn)
        Clock.schedule_once(
            lambda dt: _apply_popup_button_colors(cancel_btn, save_btn, priority_btn, calendar_btn), 0.3
        )

    def _open_inline_priority_picker(self, priority_state, on_chosen):
        panel = MDCard(
            orientation="vertical", padding=dp(18), spacing=dp(12),
            theme_bg_color="Custom", md_bg_color=theme_manager.get_color(CARD_PRIMARY), radius=[28],
        )
        title = Label(
            text="Choose Priority", font_size=sp(17), bold=True, color=theme_rgba(TEXT_PRIMARY),
            size_hint_y=None, height=dp(30), halign="left", valign="middle",
        )
        title.bind(size=title.setter("text_size"))
        panel.add_widget(title)

        inner_popup = Popup(
            title="", content=panel, size_hint=(0.75, None), height=dp(330),
            auto_dismiss=True, separator_height=0, background="", background_color=(0, 0, 0, 0),
        )

        def choose(value):
            priority_state["value"] = value
            on_chosen()
            inner_popup.dismiss()

        picker_buttons = []

        none_btn = _build_themed_button("No priority", style="tonal", bg_token=BORDER, text_token=TEXT_PRIMARY)
        none_btn.bind(on_release=lambda *_a: choose(""))
        panel.add_widget(none_btn)
        picker_buttons.append(none_btn)

        for value in PRIORITY_OPTIONS:
            btn = _build_themed_button(value, style="tonal", bg_token=BORDER, text_token=TEXT_PRIMARY)
            btn.bind(on_release=lambda *_a, v=value: choose(v))
            panel.add_widget(btn)
            picker_buttons.append(btn)

        inner_popup.open()
        _apply_popup_button_colors(*picker_buttons)
        Clock.schedule_once(lambda dt: _apply_popup_button_colors(*picker_buttons), 0.3)

    # ── v2: Add to Calendar ──

    def _open_add_to_calendar_popup(self, checklist, calendar_button_state, on_linked):
        """
        Small date/time picker for linking this checklist to ONE
        calendar event (per your confirmed option (a) -- one event
        for the whole checklist, not one per item). The time field is
        optional ("putting a time limit on it if user wants to") --
        leaving it blank creates an all-day-style event with no
        event_time, same as calendar_screen.py already supports for a
        plain reminder with no time set.
        """
        panel = MDCard(
            orientation="vertical", padding=dp(20), spacing=dp(16),
            theme_bg_color="Custom", md_bg_color=theme_manager.get_color(CARD_PRIMARY), radius=[28],
        )

        title = Label(
            text="Add to Calendar", font_size=sp(19), bold=True, color=theme_rgba(TEXT_PRIMARY),
            size_hint_y=None, height=dp(30), halign="left", valign="middle",
        )
        title.bind(size=title.setter("text_size"))
        panel.add_widget(title)

        date_input = TextInput(
            hint_text="Date (YYYY-MM-DD)",
            text=datetime.now().strftime("%Y-%m-%d"),
            multiline=False,
            size_hint_y=None,
            height=_PILL_HEIGHT,
            background_color=theme_rgba(BACKGROUND),
            foreground_color=theme_rgba(TEXT_PRIMARY),
            cursor_color=theme_rgba(ACCENT),
            font_size=sp(15),
            padding=[dp(14), dp(14), dp(14), dp(14)],
        )
        panel.add_widget(date_input)

        time_input = TextInput(
            hint_text="Time limit (HH:MM, optional)",
            multiline=False,
            size_hint_y=None,
            height=_PILL_HEIGHT,
            background_color=theme_rgba(BACKGROUND),
            foreground_color=theme_rgba(TEXT_PRIMARY),
            cursor_color=theme_rgba(ACCENT),
            font_size=sp(15),
            padding=[dp(14), dp(14), dp(14), dp(14)],
        )
        panel.add_widget(time_input)

        error_label = Label(
            text="", font_size=sp(11.5), color=theme_rgba(TEXT_SECONDARY),
            size_hint_y=None, height=dp(18), halign="left", valign="middle",
        )
        error_label.bind(size=error_label.setter("text_size"))
        panel.add_widget(error_label)

        actions = BoxLayout(orientation="horizontal", size_hint_y=None, height=_PILL_HEIGHT, spacing=dp(12))

        inner_popup = Popup(
            title="", content=panel, size_hint=(0.88, None), height=dp(400),
            auto_dismiss=False, separator_height=0, background="", background_color=(0, 0, 0, 0),
        )

        cancel_btn = _build_themed_button("Cancel", style="tonal", bg_token=BORDER, text_token=TEXT_PRIMARY)
        cancel_btn.bind(on_release=lambda *_a: inner_popup.dismiss())
        actions.add_widget(cancel_btn)

        save_btn = _build_themed_button("Save", style="filled", bg_token=BUTTON, text_token=BUTTON_TEXT)

        def do_save(*_a):
            date_text = date_input.text.strip()
            time_text = time_input.text.strip() or None

            try:
                datetime.strptime(date_text, "%Y-%m-%d")
            except ValueError:
                error_label.text = "Enter a valid date (YYYY-MM-DD)."
                return

            if time_text:
                try:
                    datetime.strptime(time_text, "%H:%M")
                except ValueError:
                    error_label.text = "Enter a valid time (HH:MM) or leave it blank."
                    return

            new_event_id = create_event(
                user_id=self._user_id(),
                title=checklist["title"],
                event_date=date_text,
                event_time=time_text,
                event_link=None,
                is_recurring=False,
            )
            set_checklist_calendar_event(self.checklist_id, new_event_id)

            inner_popup.dismiss()
            calendar_button_state["linked"] = True
            on_linked()

        save_btn.bind(on_release=do_save)
        actions.add_widget(save_btn)
        panel.add_widget(actions)

        inner_popup.open()
        _apply_popup_button_colors(cancel_btn, save_btn)
        Clock.schedule_once(lambda dt: _apply_popup_button_colors(cancel_btn, save_btn), 0.3)

    def _remove_checklist_from_calendar(self, checklist):
        """
        Unlinks this checklist from its calendar event and deletes
        that event -- since the event only ever existed because of
        this checklist link (created exclusively via
        _open_add_to_calendar_popup above), there's no other owner of
        it to preserve.
        """
        existing_event_id = checklist.get("calendar_event_id")
        if existing_event_id is not None:
            try:
                delete_event(existing_event_id)
            except Exception:
                # If the event was already removed some other way
                # (e.g. deleted directly from the Calendar screen),
                # this shouldn't block unlinking it from the
                # checklist below.
                pass
        set_checklist_calendar_event(self.checklist_id, None)
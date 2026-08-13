# screens/checklist_detail_screen.py
#
# Shows the items (and sub-items) belonging to ONE checklist, opened
# by tapping a card on screens/checklist_screen.py. Items are split
# into an "active" list and a collapsible "N Checked Items" section,
# matching the reference layout -- checked items stay visible but
# tucked away until the user taps to expand them. Also lets the user
# edit the checklist's own title/priority via the pencil icon.
#
# Also runs the same calculator pass the note editor uses on note
# text (screens/editor/calculator.py) across every item's text, so a
# checklist doubling as a shopping list ("Milk 4.99", "Eggs 3.50")
# gets a running total for free -- a plain to-do checklist with no
# numbers in it just shows nothing, same "only appears if there's
# something to show" rule the note editor's grand total already uses.
#
# No category anywhere in this feature -- the checklist's title is
# already the categorization, per your last change.

from kivymd.uix.screen import MDScreen
from kivymd.uix.label import MDLabel
from kivymd.uix.card import MDCard
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.properties import NumericProperty
from kivy.metrics import dp, sp
from kivy.utils import get_color_from_hex

from theme.theme_manager import theme_manager
from theme.themed_screen import ThemedScreenMixin
from theme.palettes import BACKGROUND, TEXT_PRIMARY, TEXT_SECONDARY, CARD_PRIMARY, ACCENT, BORDER

from widgets.checklist_item import ChecklistItem  # noqa: F401

from services.checklist_store import (
    create_checklist_item,
    get_checklist_by_id,
    get_items_by_checklist,
    get_subtasks,
    set_checked,
    update_checklist,
    delete_checklist_item,
)

from screens.editor.calculator import process_calculator_lines, format_calculated_number


def theme_rgba(token):
    return get_color_from_hex(theme_manager.get_color(token))


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
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._checked_expanded = False
        # Not a KV id (no KV changes for this feature) -- built once,
        # in code, and inserted under subtitle_label the same way
        # NoteEditorScreen builds FormattingToolbar/preview widgets in
        # Python rather than in .kv. THEME_MAP can't reach it since
        # it has no id, so on_theme_applied below colors it by hand.
        self._total_label = None

    def on_pre_enter(self, *args):
        self._checked_expanded = False
        self.load_checklist()

    def on_theme_applied(self):
        if self._total_label is not None:
            self._total_label.color = theme_rgba(TEXT_PRIMARY)

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

        # -- running total (see module docstring) --
        self._update_total(active_items)

    def _update_total(self, items):
        # get_items_by_checklist only returns top-level items -- that's
        # deliberate here too, same as get_checklist_item_counts on the
        # list screen: sub-item text (e.g. "2%" under "Milk") isn't
        # priced separately in this feature, so only top-level rows
        # feed the calculator.
        combined_text = "\n".join(item["text"] for item in items)
        _display_text, grand_total, uses_currency = process_calculator_lines(combined_text)

        total_label = self._ensure_total_label()
        if grand_total is None:
            total_label.text = ""
            total_label.height = 0
        else:
            currency_prefix = "$" if uses_currency else ""
            total_label.text = f"Total: {currency_prefix}{format_calculated_number(grand_total)}"
            total_label.texture_update()
            total_label.height = total_label.texture_size[1] + dp(6)

    def _ensure_total_label(self):
        # Built once and cached -- inserted right under subtitle_label
        # in the header's vertical box (subtitle_label.parent), since
        # that box has no id of its own in KV and this KV file is
        # otherwise left untouched. size_hint_y=None with a manually
        # driven height (set in _update_total above) is what makes it
        # collapse to nothing when there's no total to show, standing
        # in for the adaptive_height a KV-defined label would get for
        # free.
        if self._total_label is None:
            label = Label(
                text="",
                font_size=sp(13.5),
                bold=True,
                color=theme_rgba(TEXT_PRIMARY),
                halign="left",
                valign="middle",
                size_hint_y=None,
                height=0,
                padding=(0, dp(2)),
            )
            label.bind(size=label.setter("text_size"))
            parent = self.ids.subtitle_label.parent
            parent.add_widget(label, index=len(parent.children) - 1)
            self._total_label = label
        return self._total_label

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
            padding=[dp(14), 0, dp(10), 0],
        )

        chevron = Label(
            text="\u25be" if self._checked_expanded else "\u25b8",
            font_size=sp(14),
            color=theme_rgba(TEXT_SECONDARY),
            size_hint=(None, None),
            size=(dp(18), dp(42)),
            valign="middle",
            halign="center",
        )
        chevron.bind(size=chevron.setter("text_size"))
        row.add_widget(chevron)

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

    # ── editing the checklist's own title/priority ──

    def open_edit_checklist_popup(self):
        checklist = get_checklist_by_id(self.checklist_id)
        if checklist is None:
            return

        panel = MDCard(
            orientation="vertical",
            padding=dp(18),
            spacing=dp(10),
            theme_bg_color="Custom",
            md_bg_color=theme_manager.get_color(CARD_PRIMARY),
            radius=[18],
        )

        heading = Label(
            text="Edit Checklist",
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
            text=checklist["title"],
            multiline=False,
            size_hint_y=None,
            height=dp(46),
        )
        panel.add_widget(title_input)

        priority_state = {"value": checklist["priority"]}
        priority_btn = MDButton(style="tonal", size_hint_y=None, height=dp(44))
        priority_btn.add_widget(MDButtonText(text=priority_state["value"] or "+ Priority (optional)"))
        panel.add_widget(priority_btn)

        actions = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(8))

        popup = Popup(
            title="",
            content=panel,
            size_hint=(0.85, None),
            height=dp(280),
            auto_dismiss=False,
            separator_height=0,
            background="",
            background_color=(0, 0, 0, 0),
        )

        def set_priority_label():
            priority_btn.clear_widgets()
            priority_btn.add_widget(MDButtonText(text=priority_state["value"] or "+ Priority (optional)"))

        priority_btn.bind(
            on_release=lambda *_a: self._open_inline_priority_picker(priority_state, set_priority_label)
        )

        cancel_btn = MDButton(style="tonal", on_release=lambda *_a: popup.dismiss())
        cancel_btn.add_widget(MDButtonText(text="Cancel"))
        actions.add_widget(cancel_btn)

        save_btn = MDButton(style="filled")
        save_btn.add_widget(MDButtonText(text="Save"))
        actions.add_widget(save_btn)

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

    def _open_inline_priority_picker(self, priority_state, on_chosen):
        panel = MDCard(
            orientation="vertical", padding=dp(16), spacing=dp(8),
            theme_bg_color="Custom", md_bg_color=theme_manager.get_color(CARD_PRIMARY), radius=[18],
        )
        title = Label(
            text="Choose Priority", font_size=sp(15), bold=True, color=theme_rgba(TEXT_PRIMARY),
            size_hint_y=None, height=dp(28), halign="left", valign="middle",
        )
        title.bind(size=title.setter("text_size"))
        panel.add_widget(title)

        inner_popup = Popup(
            title="", content=panel, size_hint=(0.7, None), height=dp(260),
            auto_dismiss=True, separator_height=0, background="", background_color=(0, 0, 0, 0),
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
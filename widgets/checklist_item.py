"""
widgets/checklist_item.py

Individual item/sub-item widgets used inside a single checklist's
detail screen (screens/checklist_detail_screen.py). Visual-only pass:
fixes the invisible expand chevron (icon_color was never set) and
aligns checkbox/title/sub-items on consistent indentation.

Public API unchanged (text, checked, subtasks, on_toggle_complete,
add_subtask) -- screens/checklist_detail_screen.py needs no edits.
"""

from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, ObjectProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.graphics import Color, Ellipse, Line, RoundedRectangle
from kivy.utils import get_color_from_hex

from kivymd.uix.button import MDIconButton

from theme.palettes import ACCENT, CARD_PRIMARY, TEXT_PRIMARY, TEXT_SECONDARY, BORDER
from theme.theme_manager import theme_manager


def theme_rgba(token):
    return get_color_from_hex(theme_manager.get_color(token))


# Indentation shared by every sub-item row and the "add a sub-item"
# input, so they all line up under the MAIN row's checkbox, not the
# container's left edge -- matches the reference image's nesting.
_MAIN_ROW_PADDING_LEFT = dp(12)
_EXPAND_BTN_WIDTH = dp(30)
_ROW_SPACING = dp(10)
_SUBITEM_INDENT = _MAIN_ROW_PADDING_LEFT + _EXPAND_BTN_WIDTH + _ROW_SPACING


class CheckCircle(ButtonBehavior, Widget):
    """Tappable circular checkbox, shared by ChecklistItem and SubChecklistItem."""

    checked = BooleanProperty(False)
    diameter = NumericProperty(dp(24))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (self.diameter, self.diameter)
        with self.canvas:
            self._fill_color = Color(0, 0, 0, 0)
            self._fill = Ellipse(pos=self.pos, size=self.size)
            self._ring_color = Color(0, 0, 0, 0)
            self._ring = Line(width=dp(1.4))
        self.bind(
            pos=self._redraw,
            size=self._redraw,
            diameter=self._sync_size,
            checked=self._refresh_theme,
        )
        theme_manager.bind(theme_name=self._refresh_theme)
        self._refresh_theme()

    def _sync_size(self, *_args):
        self.size = (self.diameter, self.diameter)

    def _redraw(self, *_args):
        self._fill.pos = self.pos
        self._fill.size = self.size
        self._ring.ellipse = (self.x, self.y, self.width, self.height)

    def _refresh_theme(self, *_args):
        accent = theme_rgba(ACCENT)
        self._ring_color.rgba = accent
        self._fill_color.rgba = accent if self.checked else (0, 0, 0, 0)
        self._redraw()


class SubChecklistItem(BoxLayout):
    """One sub-item row -- checkbox + label, indented to align under
    the parent item's checkbox (see _SUBITEM_INDENT above)."""

    text = StringProperty("")
    checked = BooleanProperty(False)
    on_toggle = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(34))
        kwargs.setdefault("spacing", _ROW_SPACING)
        kwargs.setdefault("padding", [_SUBITEM_INDENT, 0, dp(10), 0])
        super().__init__(**kwargs)

        self.check = CheckCircle(diameter=dp(18))
        self.check.checked = self.checked
        self.check.bind(on_release=lambda *_a: self._toggle())
        self.check.pos_hint = {"center_y": 0.5}
        self.add_widget(self.check)

        self.label = Label(
            markup=True,
            font_size=sp(12.5),
            halign="left",
            valign="middle",
            size_hint_x=1,
        )
        self.label.bind(size=self.label.setter("text_size"))
        self.add_widget(self.label)

        self.bind(checked=self._refresh, text=self._refresh)
        theme_manager.bind(theme_name=self._refresh)
        self._refresh()

    def _refresh(self, *_args):
        self.check.checked = self.checked
        self.label.text = f"[s]{self.text}[/s]" if self.checked else self.text
        self.label.color = (
            theme_rgba(TEXT_SECONDARY) if self.checked else theme_rgba(TEXT_PRIMARY)
        )

    def _toggle(self):
        self.checked = not self.checked
        if self.on_toggle:
            self.on_toggle(self.checked)


class ChecklistItem(BoxLayout):
    """One item within a checklist, as a themed rounded row/card, with
    an expandable sub-item section underneath."""

    text = StringProperty("")
    checked = BooleanProperty(False)
    subtasks = ListProperty([])
    expanded = BooleanProperty(False)

    on_toggle_complete = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("spacing", dp(2))
        super().__init__(**kwargs)
        self.bind(minimum_height=self.setter("height"))

        with self.canvas.before:
            self._card_bg = Color(0, 0, 0, 0)
            self._card_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(14)])
            self._card_border_color = Color(0, 0, 0, 0)
            self._card_border = Line(width=1)
        self.bind(pos=self._update_card_canvas, size=self._update_card_canvas)

        self._build_main_row()

        self.subtask_container = BoxLayout(
            orientation="vertical", size_hint_y=None, spacing=dp(2),
            padding=[0, dp(4), 0, dp(8)],
        )
        self.subtask_container.bind(minimum_height=self.subtask_container.setter("height"))
        self.add_widget(self.subtask_container)

        self.bind(
            checked=self._refresh_main,
            text=self._refresh_main,
            subtasks=self._rebuild_subtasks,
            expanded=self._rebuild_subtasks,
        )
        theme_manager.bind(theme_name=self._refresh_all)
        self._refresh_all()

    def _update_card_canvas(self, *_args):
        self._card_rect.pos = self.pos
        self._card_rect.size = self.size
        self._card_border.rounded_rectangle = (
            self.x, self.y, self.width, self.height, dp(14)
        )

    def _build_main_row(self):
        row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(50),
            spacing=_ROW_SPACING,
            padding=[_MAIN_ROW_PADDING_LEFT, 0, dp(12), 0],
        )

        self.expand_btn = MDIconButton(
            icon="chevron-right",
            theme_icon_color="Custom",
            icon_color=theme_rgba(TEXT_SECONDARY),
            size_hint=(None, None),
            size=(_EXPAND_BTN_WIDTH, _EXPAND_BTN_WIDTH),
            pos_hint={"center_y": 0.5},
            halign="center",
            valign="middle",
        )
        self.expand_btn.bind(
            on_release=lambda *_a: setattr(self, "expanded", not self.expanded)
        )
        row.add_widget(self.expand_btn)

        self.check = CheckCircle(diameter=dp(24))
        self.check.bind(on_release=lambda *_a: self._toggle_complete())
        self.check.pos_hint = {"center_y": 0.5}
        row.add_widget(self.check)

        self.title_label = Label(
            markup=True,
            font_size=sp(14.5),
            halign="left",
            valign="middle",
            size_hint_x=1,
            shorten=True,
            shorten_from="right",
        )
        self.title_label.bind(size=self.title_label.setter("text_size"))
        row.add_widget(self.title_label)

        self.add_widget(row)

    def _toggle_complete(self):
        self.checked = not self.checked
        if self.on_toggle_complete:
            self.on_toggle_complete(self.checked)

    def _refresh_all(self, *_args):
        self._refresh_main()
        self._rebuild_subtasks()
        self._card_bg.rgba = theme_rgba(CARD_PRIMARY)
        self._card_border_color.rgba = theme_rgba(BORDER)
        self.expand_btn.icon_color = theme_rgba(TEXT_SECONDARY)
        self._update_card_canvas()

    def _refresh_main(self, *_args):
        self.check.checked = self.checked
        self.title_label.text = f"[s]{self.text}[/s]" if self.checked else self.text
        self.title_label.color = (
            theme_rgba(TEXT_SECONDARY) if self.checked else theme_rgba(TEXT_PRIMARY)
        )

    def _rebuild_subtasks(self, *_args):
        self.subtask_container.clear_widgets()

        if not self.expanded:
            self.expand_btn.icon = "chevron-right"
            self.expand_btn.icon_color = theme_rgba(TEXT_SECONDARY)
            return

        self.expand_btn.icon = "chevron-down"
        self.expand_btn.icon_color = theme_rgba(ACCENT)

        for index, subtask in enumerate(self.subtasks):
            row = SubChecklistItem(
                text=subtask.get("text", ""),
                checked=bool(subtask.get("checked", False)),
            )
            row.bind(
                checked=lambda _inst, value, i=index: self._toggle_subtask(i, value)
            )
            self.subtask_container.add_widget(row)

        add_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(36),
            padding=[_SUBITEM_INDENT, 0, dp(10), 0],
        )
        self._add_subtask_input = TextInput(
            hint_text="Add a sub-item...",
            multiline=False,
            size_hint_y=None,
            height=dp(36),
            padding=[0, dp(9), 0, dp(9)],
            background_color=(0, 0, 0, 0),
            foreground_color=theme_rgba(TEXT_PRIMARY),
            hint_text_color=theme_rgba(TEXT_SECONDARY),
            cursor_color=theme_rgba(ACCENT),
        )
        self._add_subtask_input.bind(
            on_text_validate=lambda *_a: self._submit_new_subtask()
        )
        add_row.add_widget(self._add_subtask_input)
        self.subtask_container.add_widget(add_row)

    def _toggle_subtask(self, index, checked):
        updated = list(self.subtasks)
        if 0 <= index < len(updated):
            updated[index] = {**updated[index], "checked": checked}
        self.subtasks = updated

    def _submit_new_subtask(self):
        text = self._add_subtask_input.text.strip()
        if not text:
            return
        self.add_subtask(text)
        self._add_subtask_input.text = ""

    def add_subtask(self, text):
        self.subtasks = list(self.subtasks) + [{"text": text, "checked": False}]
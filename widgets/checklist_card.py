"""
widgets/checklist_card.py

Summary card for one checklist, shown on the main Checklist screen
(screens/checklist_screen.py). Displays title, an item-count summary,
and an optional priority chip -- tapping the card opens that
checklist's items on screens/checklist_detail_screen.py. A small
delete button sits in the corner rather than requiring a separate
screen/popup just to remove a checklist.

UI-only pass, round 4: top padding increased again (14 -> 18 -> 22dp)
to push the title/trash row further down from the card's top edge,
per your latest note. Alignment mechanism (AnchorLayout for both
title and delete button) is unchanged -- spacing only.
"""

from kivy.metrics import dp, sp
from kivy.properties import NumericProperty, ObjectProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.utils import get_color_from_hex
from kivy.uix.anchorlayout import AnchorLayout

from kivymd.uix.button import MDIconButton

from theme.palettes import CARD_PRIMARY, TEXT_PRIMARY, TEXT_SECONDARY, BORDER, CARD_SECONDARY
from theme.theme_manager import theme_manager


def theme_rgba(token):
    return get_color_from_hex(theme_manager.get_color(token))


PRIORITY_COLORS = {
    "Low": "#B7D6A8",
    "Medium": "#F0CD8A",
    "High": "#EFA394",
}
DEFAULT_CATEGORY_CHIP_COLOR = "#C9C0E8"


class _Chip(BoxLayout):
    """Small rounded pill, read-only display."""

    def __init__(self, label_text, bg_hex, **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (dp(80), dp(24)))
        kwargs.setdefault("padding", [dp(8), 0])
        super().__init__(**kwargs)
        with self.canvas.before:
            self._bg_color = Color(*get_color_from_hex(bg_hex))
            self._bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10)])
        label = Label(
            text=label_text,
            font_size=sp(10),
            bold=True,
            color=(0.16, 0.13, 0.09, 1),
            halign="center",
            valign="middle",
        )
        label.bind(size=label.setter("text_size"))
        self.add_widget(label)
        self.bind(pos=self._redraw, size=self._redraw)

    def _redraw(self, *_args):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size


class ChecklistCard(ButtonBehavior, BoxLayout):
    """
    One checklist's summary card on the main list screen.
    on_tap(checklist_id) opens the detail screen.
    on_delete(checklist_id) removes the checklist (with its items).
    """

    title = StringProperty("")
    priority = StringProperty("")
    item_count = NumericProperty(0)
    checked_count = NumericProperty(0)
    checklist_id = NumericProperty(0)

    on_tap = ObjectProperty(None, allownone=True)
    on_delete = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(108))
        kwargs.setdefault("spacing", dp(10))
        # top padding 18 -> 22dp: pushes the title/trash row further
        # down from the card's top edge, per your latest note.
        kwargs.setdefault("padding", [dp(16), dp(22), dp(12), dp(12)])
        super().__init__(**kwargs)

        with self.canvas.before:
            self._card_bg = Color(0, 0, 0, 0)
            self._card_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(16)])
            self._card_border_color = Color(0, 0, 0, 0)
            self._card_border = Line(width=1)
        self.bind(pos=self._update_canvas, size=self._update_canvas)

        top_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(34), spacing=dp(8))

        title_anchor = AnchorLayout(size_hint=(1, 1), anchor_x="left", anchor_y="center")
        self.title_label = Label(
            text=self.title,
            font_size=sp(16),
            bold=True,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(24),
            shorten=True,
            shorten_from="right",
        )
        self.title_label.bind(size=self.title_label.setter("text_size"))
        title_anchor.add_widget(self.title_label)
        top_row.add_widget(title_anchor)

        delete_anchor = AnchorLayout(size_hint=(None, None), size=(dp(40), dp(34)), anchor_x="right", anchor_y="center")
        self.delete_btn = MDIconButton(
            icon="trash-can-outline",
            theme_icon_color="Custom",
            style="standard",
            size_hint=(None, None),
            size=(dp(32), dp(32)),
        )
        self.delete_btn.bind(on_release=lambda *_a: self._request_delete())
        delete_anchor.add_widget(self.delete_btn)
        top_row.add_widget(delete_anchor)

        self.add_widget(top_row)

        self.chips_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(26), spacing=dp(8))
        self.add_widget(self.chips_row)

        self.summary_label = Label(
            text="",
            font_size=sp(11.5),
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(20),
        )
        self.summary_label.bind(size=self.summary_label.setter("text_size"))
        self.add_widget(self.summary_label)

        self.bind(
            title=self._refresh_text,
            priority=self._refresh_chips,
            item_count=self._refresh_text,
            checked_count=self._refresh_text,
        )
        theme_manager.bind(theme_name=self._refresh_all)
        self._refresh_all()

    def _update_canvas(self, *_args):
        self._card_rect.pos = self.pos
        self._card_rect.size = self.size
        self._card_border.rounded_rectangle = (
            self.x, self.y, self.width, self.height, dp(16)
        )

    def _request_delete(self):
        if self.on_delete:
            self.on_delete(self.checklist_id)

    def on_release(self):
        if self.on_tap:
            self.on_tap(self.checklist_id)

    def _refresh_all(self, *_args):
        self._card_bg.rgba = theme_rgba(CARD_PRIMARY)
        self._card_border_color.rgba = theme_rgba(BORDER)
        self.delete_btn.icon_color = theme_rgba(TEXT_SECONDARY)
        self._refresh_text()
        self._refresh_chips()
        self._update_canvas()

    def _refresh_text(self, *_args):
        self.title_label.text = self.title
        self.title_label.color = theme_rgba(TEXT_PRIMARY)
        if self.item_count:
            self.summary_label.text = f"{self.checked_count} of {self.item_count} done"
        else:
            self.summary_label.text = "No items yet"
        self.summary_label.color = theme_rgba(TEXT_SECONDARY)

    def _refresh_chips(self, *_args):
        self.chips_row.clear_widgets()
        if self.priority:
            self.chips_row.add_widget(
                _Chip(self.priority, PRIORITY_COLORS.get(self.priority, DEFAULT_CATEGORY_CHIP_COLOR))
            )
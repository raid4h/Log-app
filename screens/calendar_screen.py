"""
Calendar screen -- simple date-based reminders, with an optional
recurring mode: an incomplete recurring reminder shifts to today
every time the calendar is opened, and shows a "Missed N days" tag
until it's marked done.

UI lives in calendar_screen.kv.
Database access stays in database/calendar_queries.py.
"""

import calendar
import webbrowser
from datetime import datetime

from kivy.graphics import Color, Ellipse
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex

from kivymd.uix.screen import MDScreen
from kivymd.uix.card import MDCard
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.textfield import MDTextField, MDTextFieldHintText

from database.calendar_queries import (
    create_calendar_events_table,
    create_event,
    delete_event,
    get_all_event_dates,
    get_events_by_date,
    mark_event_completed,
    roll_forward_recurring_events,
    update_event,
)

from theme.palettes import (
    ACCENT,
    BACKGROUND,
    BORDER,
    BUTTON,
    BUTTON_TEXT,
    CARD_PRIMARY,
    CARD_SECONDARY,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

from theme.theme_manager import theme_manager
from theme.themed_screen import ThemedScreenMixin


# ============================================================================
# Theme helpers
# ============================================================================

def theme_rgba(token):
    return get_color_from_hex(
        theme_manager.get_color(token)
    )


# ============================================================================
# Themed text field
# ============================================================================

def _themed_text_field(hint, text=""):
    """
    Mobile-friendly themed outlined text field.

    The original 46dp height was too cramped with KivyMD's outlined
    field + floating hint. 52dp gives it enough breathing room.
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

    theme_manager.bind(
        theme_name=_refresh
    )

    return field


# ============================================================================
# Themed button
# ============================================================================

def _themed_button(text, style, on_release=None):
    """
    Create a theme-aware KivyMD button.

    filled:
        Uses BUTTON / BUTTON_TEXT.

    tonal:
        Uses CARD_SECONDARY / TEXT_PRIMARY.
    """

    if style == "filled":

        btn = MDButton(
            style="filled",
            theme_bg_color="Custom",
            md_bg_color=theme_rgba(BUTTON),
        )

        label = MDButtonText(
            text=text,
            theme_text_color="Custom",
            text_color=theme_rgba(BUTTON_TEXT),
        )

    else:

        btn = MDButton(
            style="tonal",
            theme_bg_color="Custom",
            md_bg_color=theme_rgba(CARD_SECONDARY),
            line_color=theme_rgba(BORDER),
        )

        label = MDButtonText(
            text=text,
            theme_text_color="Custom",
            text_color=theme_rgba(TEXT_PRIMARY),
        )

    btn.add_widget(label)

    if on_release:
        btn.bind(
            on_release=on_release
        )

    def _refresh(*_args):

        if style == "filled":

            btn.md_bg_color = theme_rgba(BUTTON)
            label.text_color = theme_rgba(BUTTON_TEXT)

        else:

            btn.md_bg_color = theme_rgba(CARD_SECONDARY)
            btn.line_color = theme_rgba(BORDER)
            label.text_color = theme_rgba(TEXT_PRIMARY)

    theme_manager.bind(
        theme_name=_refresh
    )

    return btn


# ============================================================================
# Time helpers
# ============================================================================

def _to_12h(value):
    """
    Convert stored HH:MM into:
        (hour_12, minute, AM/PM)

    Returns None for empty/invalid values.
    """

    if not value:
        return None

    try:
        h, m = value.split(":")

        h = int(h)
        m = int(m)

        if not 0 <= h <= 23:
            return None

        if not 0 <= m <= 59:
            return None

    except Exception:
        return None

    period = "AM" if h < 12 else "PM"

    h12 = h % 12

    if h12 == 0:
        h12 = 12

    return h12, m, period


# ============================================================================
# Time picker
# ============================================================================

class TimePickerRow(BoxLayout):
    """
    Compact 12-hour time picker.

    Mobile layout:

        [clock] [9:00 AM] [< >] [<< >>] [AM]

    The time label has a fixed width so it cannot collapse on
    narrow screens.
    """

    def __init__(self, initial_24h=None, **kwargs):

        kwargs.setdefault(
            "orientation",
            "horizontal",
        )

        kwargs.setdefault(
            "size_hint_y",
            None,
        )

        kwargs.setdefault(
            "height",
            dp(44),
        )

        kwargs.setdefault(
            "spacing",
            dp(2),
        )

        super().__init__(**kwargs)

        parsed = _to_12h(
            initial_24h
        )

        self.state = {
            "enabled": parsed is not None,
            "hour": parsed[0] if parsed else 9,
            "minute": parsed[1] if parsed else 0,
            "period": parsed[2] if parsed else "AM",
        }

        # ------------------------------------------------------------
        # Clock toggle
        # ------------------------------------------------------------

        self.enable_btn = MDIconButton(
            icon="clock-outline",
            theme_icon_color="Custom",
            size_hint=(None, None),
            size=(dp(38), dp(38)),
        )

        self.enable_btn.bind(
            on_release=lambda *_:
            self._toggle_enabled()
        )

        self.add_widget(
            self.enable_btn
        )

        # ------------------------------------------------------------
        # Time value
        # ------------------------------------------------------------

        self.value_label = Label(
            text="",
            font_size=sp(13),
            bold=True,

            halign="left",
            valign="middle",

            size_hint_x=None,
            width=dp(66),

            color=theme_rgba(TEXT_PRIMARY),
        )

        self.value_label.bind(
            size=self.value_label.setter(
                "text_size"
            )
        )

        self.add_widget(
            self.value_label
        )

        # ------------------------------------------------------------
        # Hour controls
        # ------------------------------------------------------------

        hour_group = BoxLayout(
            orientation="horizontal",
            size_hint_x=None,
            width=dp(64),
            spacing=0,
        )

        self.hour_down = MDIconButton(
            icon="chevron-left",
            theme_icon_color="Custom",
            size_hint=(None, None),
            size=(dp(32), dp(38)),
        )

        self.hour_down.bind(
            on_release=lambda *_:
            self._step_hour(-1)
        )

        self.hour_up = MDIconButton(
            icon="chevron-right",
            theme_icon_color="Custom",
            size_hint=(None, None),
            size=(dp(32), dp(38)),
        )

        self.hour_up.bind(
            on_release=lambda *_:
            self._step_hour(1)
        )

        hour_group.add_widget(
            self.hour_down
        )

        hour_group.add_widget(
            self.hour_up
        )

        self.add_widget(
            hour_group
        )

        # ------------------------------------------------------------
        # Minute controls
        # ------------------------------------------------------------

        minute_group = BoxLayout(
            orientation="horizontal",
            size_hint_x=None,
            width=dp(64),
            spacing=0,
        )

        self.minute_down = MDIconButton(
            icon="chevron-double-left",
            theme_icon_color="Custom",
            size_hint=(None, None),
            size=(dp(32), dp(38)),
        )

        self.minute_down.bind(
            on_release=lambda *_:
            self._step_minute(-5)
        )

        self.minute_up = MDIconButton(
            icon="chevron-double-right",
            theme_icon_color="Custom",
            size_hint=(None, None),
            size=(dp(32), dp(38)),
        )

        self.minute_up.bind(
            on_release=lambda *_:
            self._step_minute(5)
        )

        minute_group.add_widget(
            self.minute_down
        )

        minute_group.add_widget(
            self.minute_up
        )

        self.add_widget(
            minute_group
        )

        # ------------------------------------------------------------
        # AM / PM
        # ------------------------------------------------------------

        self.period_btn = _themed_button(
            "AM",
            "tonal",
            on_release=lambda *_:
            self._toggle_period(),
        )

        self.period_btn.size_hint = (
            None,
            None,
        )

        self.period_btn.size = (
            dp(54),
            dp(38),
        )

        self.add_widget(
            self.period_btn
        )

        theme_manager.bind(
            theme_name=self._refresh
        )

        self._refresh()

    # ----------------------------------------------------------------
    # Time manipulation
    # ----------------------------------------------------------------

    def _step_hour(self, delta):

        if not self.state["enabled"]:
            return

        self.state["hour"] = (
            (self.state["hour"] - 1 + delta)
            % 12
        ) + 1

        self._refresh()

    def _step_minute(self, delta):

        if not self.state["enabled"]:
            return

        self.state["minute"] = (
            self.state["minute"] + delta
        ) % 60

        self._refresh()

    def _toggle_period(self, *_args):

        if not self.state["enabled"]:
            return

        self.state["period"] = (
            "PM"
            if self.state["period"] == "AM"
            else "AM"
        )

        self._refresh()

    def _toggle_enabled(self):

        self.state["enabled"] = (
            not self.state["enabled"]
        )

        self._refresh()

    # ----------------------------------------------------------------
    # Refresh
    # ----------------------------------------------------------------

    def _refresh(self, *_args):

        enabled = self.state["enabled"]

        self.enable_btn.icon = (
            "clock-outline"
            if enabled
            else "clock-remove-outline"
        )

        self.enable_btn.icon_color = (
            theme_rgba(ACCENT)
            if enabled
            else theme_rgba(TEXT_SECONDARY)
        )

        if enabled:

            self.value_label.text = (
                f'{self.state["hour"]}:'
                f'{self.state["minute"]:02d} '
                f'{self.state["period"]}'
            )

            self.value_label.color = (
                theme_rgba(TEXT_PRIMARY)
            )

        else:

            self.value_label.text = (
                "Any time"
            )

            self.value_label.color = (
                theme_rgba(TEXT_SECONDARY)
            )

        if self.period_btn.children:
            self.period_btn.children[0].text = (
                self.state["period"]
            )

        buttons = (
            self.hour_down,
            self.hour_up,
            self.minute_down,
            self.minute_up,
            self.period_btn,
        )

        for btn in buttons:
            btn.disabled = not enabled
            btn.opacity = (
                1
                if enabled
                else 0.35
            )

        for btn in (
            self.hour_down,
            self.hour_up,
            self.minute_down,
            self.minute_up,
        ):
            btn.icon_color = (
                theme_rgba(TEXT_PRIMARY)
                if enabled
                else theme_rgba(TEXT_SECONDARY)
            )

    # ----------------------------------------------------------------
    # Database format
    # ----------------------------------------------------------------

    def get_24h(self):

        if not self.state["enabled"]:
            return None

        h = self.state["hour"] % 12

        if self.state["period"] == "PM":
            h += 12

        return (
            f'{h:02d}:'
            f'{self.state["minute"]:02d}'
        )


# ============================================================================
# Calendar day cell
# ============================================================================

class CalendarDayCell(
    ButtonBehavior,
    BoxLayout,
):

    day_number = StringProperty("")
    date_value = StringProperty("")

    is_today = BooleanProperty(False)
    is_selected = BooleanProperty(False)
    has_event = BooleanProperty(False)

    def __init__(self, **kwargs):

        super().__init__(**kwargs)

        self.orientation = "vertical"

        # ------------------------------------------------------------
        # Selection / today circle
        # ------------------------------------------------------------

        with self.canvas.before:

            self._fill_color = Color(
                0,
                0,
                0,
                0,
            )

            self._fill = Ellipse(
                pos=self.pos,
                size=self.size,
            )

        # ------------------------------------------------------------
        # Event dot
        # ------------------------------------------------------------

        with self.canvas.after:

            self._dot_color = Color(
                0,
                0,
                0,
                0,
            )

            self._dot = Ellipse(
                pos=self.pos,
                size=(dp(4), dp(4)),
            )

        # ------------------------------------------------------------
        # Number
        # ------------------------------------------------------------

        self.number_label = Label(
            text=self.day_number,
            font_size=sp(14),
            halign="center",
            valign="middle",
            color=theme_rgba(TEXT_PRIMARY),
        )

        self.number_label.bind(
            size=self.number_label.setter(
                "text_size"
            )
        )

        self.add_widget(
            self.number_label
        )

        # ------------------------------------------------------------
        # Bindings
        # ------------------------------------------------------------

        self.bind(
            pos=self._redraw,
            size=self._redraw,
            day_number=self._sync_text,
            is_today=self._refresh_theme,
            is_selected=self._refresh_theme,
            has_event=self._redraw,
        )

        theme_manager.bind(
            theme_name=self._refresh_theme
        )

        self._refresh_theme()

    def _sync_text(self, *_args):
        self.number_label.text = (
            self.day_number
        )

    def _redraw(self, *_args):

        side = min(
            self.width,
            dp(34),
        )

        cx = (
            self.center_x
            - side / 2
        )

        cy = (
            self.y
            + self.height * 0.48
            - side / 2
        )

        self._fill.pos = (
            cx,
            cy,
        )

        self._fill.size = (
            side,
            side,
        )

        self._dot.pos = (
            self.center_x - dp(2),
            cy - dp(7),
        )

        self._dot.size = (
            dp(4),
            dp(4),
        )

    def _refresh_theme(self, *_args):

        if self.is_selected:

            self._fill_color.rgba = (
                theme_rgba(ACCENT)
            )

        elif self.is_today:

            accent = theme_rgba(
                ACCENT
            )

            self._fill_color.rgba = (
                accent[0],
                accent[1],
                accent[2],
                0.28,
            )

        else:

            self._fill_color.rgba = (
                0,
                0,
                0,
                0,
            )

        self._dot_color.rgba = (
            theme_rgba(ACCENT)
            if self.has_event
            else (
                0,
                0,
                0,
                0,
            )
        )

        self.number_label.color = (
            theme_rgba(TEXT_PRIMARY)
        )

        self._redraw()


# ============================================================================
# Event row
# ============================================================================

class EventRow(
    ButtonBehavior,
    BoxLayout,
):

    def __init__(
        self,
        event,
        bar_token,
        on_tap,
        on_toggle_complete,
        **kwargs,
    ):

        kwargs.setdefault(
            "orientation",
            "horizontal",
        )

        kwargs.setdefault(
            "size_hint_y",
            None,
        )

        kwargs.setdefault(
            "height",
            dp(64),
        )

        kwargs.setdefault(
            "spacing",
            dp(10),
        )

        kwargs.setdefault(
            "padding",
            [
                dp(2),
                dp(8),
                dp(4),
                dp(8),
            ],
        )

        super().__init__(**kwargs)

        self.event = event
        self.on_tap = on_tap
        self.on_toggle_complete = (
            on_toggle_complete
        )

        completed = event.get(
            "completed",
            False,
        )

        # ------------------------------------------------------------
        # Left color bar
        # ------------------------------------------------------------

        bar = Widget(
            size_hint_x=None,
            width=dp(3),
        )

        with bar.canvas:

            bar_color = Color(
                *theme_rgba(bar_token)
            )

            from kivy.graphics import RoundedRectangle

            bar_rect = RoundedRectangle(
                pos=bar.pos,
                size=bar.size,
                radius=[dp(1.5)],
            )

        bar.bind(
            pos=lambda w, _v:
            setattr(
                bar_rect,
                "pos",
                w.pos,
            ),

            size=lambda w, _v:
            setattr(
                bar_rect,
                "size",
                w.size,
            ),
        )

        theme_manager.bind(
            theme_name=lambda *_a:
            setattr(
                bar_color,
                "rgba",
                theme_rgba(bar_token),
            )
        )

        self.add_widget(
            bar
        )

        # ------------------------------------------------------------
        # Checkbox
        # ------------------------------------------------------------

        self.check_btn = MDIconButton(
            icon=(
                "checkbox-marked"
                if completed
                else "checkbox-blank-outline"
            ),

            theme_icon_color="Custom",

            icon_color=(
                theme_rgba(ACCENT)
                if completed
                else theme_rgba(TEXT_SECONDARY)
            ),

            pos_hint={
                "center_y": 0.5
            },
        )

        self.check_btn.bind(
            on_release=lambda *_:
            self._toggle_complete()
        )

        self.add_widget(
            self.check_btn
        )

        # ------------------------------------------------------------
        # Text
        # ------------------------------------------------------------

        text_box = BoxLayout(
            orientation="vertical"
        )

        title = event.get(
            "title",
            "",
        )

        self.title_label = Label(
            text=(
                f"[s]{title}[/s]"
                if completed
                else title
            ),

            markup=True,

            font_size=sp(14),

            halign="left",
            valign="middle",

            color=theme_rgba(TEXT_PRIMARY),

            size_hint_y=None,
            height=dp(24),
        )

        self.title_label.bind(
            size=self.title_label.setter(
                "text_size"
            )
        )

        time_text = (
            event.get("event_time")
            or "Any time"
        )

        missed_days = (
            event.get("missed_days")
            or 0
        )

        if (
            not completed
            and missed_days
        ):

            missed_text = (
                "Missed yesterday"
                if missed_days == 1
                else f"Missed {missed_days} days"
            )

            meta_text = (
                f"{time_text}   •   "
                f"{missed_text}"
            )

        else:

            meta_text = time_text

        self.meta_label = Label(
            text=meta_text,
            font_size=sp(11),

            halign="left",
            valign="middle",

            color=theme_rgba(
                TEXT_SECONDARY
            ),

            size_hint_y=None,
            height=dp(20),
        )

        self.meta_label.bind(
            size=self.meta_label.setter(
                "text_size"
            )
        )

        text_box.add_widget(
            self.title_label
        )

        text_box.add_widget(
            self.meta_label
        )

        self.add_widget(
            text_box
        )

        # ------------------------------------------------------------
        # External link
        # ------------------------------------------------------------

        if event.get("event_link"):

            link_btn = MDIconButton(
                icon="open-in-new",
                theme_icon_color="Custom",
                icon_color=theme_rgba(ACCENT),
                pos_hint={
                    "center_y": 0.5
                },
            )

            link_btn.bind(
                on_release=lambda *_:
                self._open_link()
            )

            self.add_widget(
                link_btn
            )

    def _open_link(self):

        link = (
            self.event.get(
                "event_link"
            )
            or ""
        ).strip()

        if not link:
            return

        if not link.startswith(
            (
                "http://",
                "https://",
            )
        ):
            link = "https://" + link

        webbrowser.open(link)

    def _toggle_complete(self):

        if self.on_toggle_complete:
            self.on_toggle_complete(
                self.event
            )

    def on_release(self):

        if self.on_tap:
            self.on_tap(
                self.event
            )


# ============================================================================
# Calendar screen
# ============================================================================

class CalendarScreen(
    ThemedScreenMixin,
    MDScreen,
):

    THEME_MAP = {
        "self": (
            "md_bg_color",
            BACKGROUND,
        ),

        "title_label": (
            "text_color",
            TEXT_PRIMARY,
        ),

        "subtitle_label": (
            "text_color",
            TEXT_SECONDARY,
        ),

        "back_button": (
            "icon_color",
            TEXT_PRIMARY,
        ),

        "add_button": (
            "icon_color",
            ACCENT,
        ),

        "prev_button": (
            "icon_color",
            TEXT_PRIMARY,
        ),

        "next_button": (
            "icon_color",
            TEXT_PRIMARY,
        ),

        "today_button": (
            "icon_color",
            ACCENT,
        ),

        "month_label": (
            "text_color",
            TEXT_PRIMARY,
        ),

        "month_card": (
            "md_bg_color",
            CARD_PRIMARY,
        ),

        "agenda_card": (
            "md_bg_color",
            CARD_PRIMARY,
        ),

        "agenda_title": (
            "text_color",
            TEXT_PRIMARY,
        ),

        "view_all_label": (
            "text_color",
            ACCENT,
        ),

        "empty_label": (
            "text_color",
            TEXT_SECONDARY,
        ),
    }

    _BAR_TOKENS = (
        ACCENT,
        TEXT_SECONDARY,
    )

    # ----------------------------------------------------------------
    # Init
    # ----------------------------------------------------------------

    def __init__(self, **kwargs):

        create_calendar_events_table()

        now = datetime.now()

        self.current_year = now.year
        self.current_month = now.month

        self.selected_date = (
            now.strftime("%Y-%m-%d")
        )

        self.day_cells = {}

        # Compatibility with HomeScreen.
        self.selected_task_id = None

        super().__init__(**kwargs)

    # ----------------------------------------------------------------
    # User
    # ----------------------------------------------------------------

    def _user_id(self):

        try:

            from kivy.app import App

            app = App.get_running_app()

            return getattr(
                app,
                "user_id",
                1,
            )

        except Exception:

            return 1

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------

    def on_kv_post(
        self,
        base_widget,
    ):

        super().on_kv_post(
            base_widget
        )

        self._build_weekday_header()

        roll_forward_recurring_events(
            self._user_id()
        )

        self.build_month_grid()

        self.select_date(
            self.selected_date
        )

    def on_pre_enter(self, *_args):

        roll_forward_recurring_events(
            self._user_id()
        )

        self.build_month_grid()

        self.select_date(
            self.selected_date
        )

    # ----------------------------------------------------------------
    # Weekday header
    # ----------------------------------------------------------------

    def _build_weekday_header(self):

        header = self.ids.get(
            "weekday_header"
        )

        if header is None:
            return

        if header.children:
            return

        for name in (
            "Mon",
            "Tue",
            "Wed",
            "Thu",
            "Fri",
            "Sat",
            "Sun",
        ):

            header.add_widget(
                Label(
                    text=name,
                    font_size=sp(10),
                    bold=True,

                    color=theme_rgba(
                        TEXT_SECONDARY
                    ),

                    size_hint_y=None,
                    height=dp(20),
                )
            )

    # ----------------------------------------------------------------
    # Month grid
    # ----------------------------------------------------------------

    def build_month_grid(self):

        grid = self.ids.get(
            "day_grid"
        )

        if grid is None:
            return

        grid.clear_widgets()

        self.day_cells = {}

        first_day = datetime(
            self.current_year,
            self.current_month,
            1,
        )

        self.ids.month_label.text = (
            first_day.strftime(
                "%B %Y"
            )
        )

        event_dates = get_all_event_dates(
            self.current_year,
            self.current_month,
            self._user_id(),
        )

        weeks = calendar.monthcalendar(
            self.current_year,
            self.current_month,
        )

        while len(weeks) < 6:
            weeks.append(
                [0] * 7
            )

        today_value = (
            datetime.now()
            .strftime("%Y-%m-%d")
        )

        for week in weeks[:6]:

            for day in week:

                if day == 0:

                    grid.add_widget(
                        Widget()
                    )

                    continue

                date_value = (
                    f"{self.current_year:04d}-"
                    f"{self.current_month:02d}-"
                    f"{day:02d}"
                )

                cell = CalendarDayCell(
                    day_number=str(day),
                    date_value=date_value,

                    is_today=(
                        date_value
                        == today_value
                    ),

                    has_event=(
                        date_value
                        in event_dates
                    ),

                    is_selected=(
                        date_value
                        == self.selected_date
                    ),
                )

                cell.bind(
                    on_release=lambda
                    _cell,
                    selected=date_value:
                    self.select_date(
                        selected
                    )
                )

                self.day_cells[
                    date_value
                ] = cell

                grid.add_widget(
                    cell
                )

    # ----------------------------------------------------------------
    # Date selection
    # ----------------------------------------------------------------

    def select_date(
        self,
        date_value,
    ):

        self.selected_date = date_value

        for value, cell in self.day_cells.items():

            cell.is_selected = (
                value == date_value
            )

        selected = datetime.strptime(
            date_value,
            "%Y-%m-%d",
        )

        self.ids.agenda_title.text = (
            selected.strftime(
                "%A, %d %B"
            )
        )

        self.refresh_agenda()

    # ----------------------------------------------------------------
    # Agenda
    # ----------------------------------------------------------------

    def refresh_agenda(self):

        agenda_list = self.ids.get(
            "agenda_list"
        )

        if agenda_list is None:
            return

        agenda_list.clear_widgets()

        events = get_events_by_date(
            self.selected_date,
            self._user_id(),
        )

        if not events:

            empty = Label(
                text="No reminders for this date.",

                font_size=sp(12),

                color=theme_rgba(
                    TEXT_SECONDARY
                ),

                size_hint_y=None,
                height=dp(60),
            )

            agenda_list.add_widget(
                empty
            )

            return

        for index, event in enumerate(events):

            bar_token = (
                self._BAR_TOKENS[
                    index
                    % len(self._BAR_TOKENS)
                ]
            )

            agenda_list.add_widget(
                EventRow(
                    event=event,
                    bar_token=bar_token,

                    on_tap=(
                        self.open_edit_popup
                    ),

                    on_toggle_complete=(
                        self.toggle_event_completed
                    ),
                )
            )

    # ----------------------------------------------------------------
    # Complete
    # ----------------------------------------------------------------

    def toggle_event_completed(
        self,
        event,
    ):

        mark_event_completed(
            event["id"],
            not event.get(
                "completed",
                False,
            ),
        )

        self.build_month_grid()

        self.select_date(
            self.selected_date
        )

    # ----------------------------------------------------------------
    # Navigation
    # ----------------------------------------------------------------

    def go_back(self):

        if self.manager:
            self.manager.current = "home"

    def go_to_today(self):

        today = datetime.now()

        self.current_year = today.year
        self.current_month = today.month

        self.selected_date = (
            today.strftime("%Y-%m-%d")
        )

        self.build_month_grid()

        self.select_date(
            self.selected_date
        )

    def prev_month(self):

        if self.current_month == 1:

            self.current_month = 12
            self.current_year -= 1

        else:

            self.current_month -= 1

        self.selected_date = (
            f"{self.current_year:04d}-"
            f"{self.current_month:02d}-01"
        )

        self.build_month_grid()

        self.select_date(
            self.selected_date
        )

    def next_month(self):

        if self.current_month == 12:

            self.current_month = 1
            self.current_year += 1

        else:

            self.current_month += 1

        self.selected_date = (
            f"{self.current_year:04d}-"
            f"{self.current_month:02d}-01"
        )

        self.build_month_grid()

        self.select_date(
            self.selected_date
        )

    # ----------------------------------------------------------------
    # Add / edit
    # ----------------------------------------------------------------

    def open_add_popup(self):

        self._open_event_popup(
            mode="add"
        )

    def open_add_task_popup(
        self,
        activity_type=None,
    ):
        """
        Compatibility shim for HomeScreen Quick Add.
        """

        self.open_add_popup()

    def open_edit_popup(
        self,
        event,
    ):

        self._open_event_popup(
            mode="edit",
            event=event,
        )

    # ----------------------------------------------------------------
    # Popup
    # ----------------------------------------------------------------

    def _open_event_popup(
        self,
        mode,
        event=None,
    ):

        # ============================================================
        # Panel
        # ============================================================

        panel = MDCard(
            orientation="vertical",

            padding=[
                dp(16),
                dp(16),
                dp(16),
                dp(16),
            ],

            spacing=dp(8),

            size_hint=(1, 1),

            theme_bg_color="Custom",

            md_bg_color=theme_rgba(
                CARD_PRIMARY
            ),

            radius=[18],
        )

        # ============================================================
        # Heading
        # ============================================================

        heading = Label(
            text=(
                "Add Reminder"
                if mode == "add"
                else "Edit Reminder"
            ),

            font_size=sp(18),
            bold=True,

            color=theme_rgba(
                TEXT_PRIMARY
            ),

            size_hint_y=None,
            height=dp(32),

            halign="left",
            valign="middle",
        )

        heading.bind(
            size=heading.setter(
                "text_size"
            )
        )

        panel.add_widget(
            heading
        )

        # ============================================================
        # Title
        # ============================================================

        title_input = _themed_text_field(
            "Reminder title",

            (
                event.get(
                    "title",
                    "",
                )
                if event
                else ""
            ),
        )

        panel.add_widget(
            title_input
        )

        # ============================================================
        # Time
        # ============================================================

        time_picker = TimePickerRow(
            initial_24h=(
                event.get(
                    "event_time"
                )
                if event
                else None
            )
        )

        panel.add_widget(
            time_picker
        )

        # ============================================================
        # Link
        # ============================================================

        link_input = _themed_text_field(
            "Link (optional, e.g. https://...)",

            (
                event.get(
                    "event_link"
                )
                or ""
                if event
                else ""
            ),
        )

        panel.add_widget(
            link_input
        )

        # ============================================================
        # Recurring row
        # ============================================================

        recurring_row = BoxLayout(
            orientation="horizontal",

            size_hint_y=None,
            height=dp(44),

            spacing=dp(8),
        )

        recurring_state = {
            "value": (
                bool(
                    event.get(
                        "is_recurring"
                    )
                )
                if event
                else False
            )
        }

        recurring_label = Label(
            text="Repeat daily until marked done",

            font_size=sp(12),

            color=theme_rgba(
                TEXT_SECONDARY
            ),

            halign="left",
            valign="middle",
        )

        recurring_label.bind(
            size=recurring_label.setter(
                "text_size"
            )
        )

        recurring_toggle_btn = MDIconButton(
            icon=(
                "toggle-switch"
                if recurring_state["value"]
                else "toggle-switch-off-outline"
            ),

            theme_icon_color="Custom",

            icon_color=(
                theme_rgba(ACCENT)
                if recurring_state["value"]
                else theme_rgba(
                    TEXT_SECONDARY
                )
            ),

            size_hint=(None, None),
            size=(dp(44), dp(44)),
        )

        def toggle_recurring(*_args):

            recurring_state["value"] = (
                not recurring_state["value"]
            )

            recurring_toggle_btn.icon = (
                "toggle-switch"
                if recurring_state["value"]
                else "toggle-switch-off-outline"
            )

            recurring_toggle_btn.icon_color = (
                theme_rgba(ACCENT)
                if recurring_state["value"]
                else theme_rgba(
                    TEXT_SECONDARY
                )
            )

        recurring_toggle_btn.bind(
            on_release=toggle_recurring
        )

        recurring_row.add_widget(
            recurring_label
        )

        recurring_row.add_widget(
            recurring_toggle_btn
        )

        panel.add_widget(
            recurring_row
        )

        # ============================================================
        # Error
        # ============================================================

        error_label = Label(
            text="",

            font_size=sp(10),

            color=theme_rgba(
                TEXT_SECONDARY
            ),

            size_hint_y=None,
            height=dp(20),

            halign="left",
            valign="middle",
        )

        error_label.bind(
            size=error_label.setter(
                "text_size"
            )
        )

        panel.add_widget(
            error_label
        )

        # ============================================================
        # Popup
        # ============================================================

        popup = Popup(
            title="",

            content=panel,

            # Much wider than the old 82%.
            size_hint=(0.94, None),

            # Enough room for the complete form.
            height=(
                dp(430)
                if mode == "add"
                else dp(455)
            ),

            auto_dismiss=True,

            separator_height=0,

            background="",

            background_color=(
                0,
                0,
                0,
                0,
            ),
        )

        # ============================================================
        # Actions
        # ============================================================

        actions = BoxLayout(
            orientation="horizontal",

            size_hint_y=None,
            height=dp(48),

            spacing=dp(8),
        )

        cancel_btn = _themed_button(
            "Cancel",
            "tonal",

            on_release=lambda *_:
            popup.dismiss(),
        )

        actions.add_widget(
            cancel_btn
        )

        if mode == "edit":

            delete_btn = _themed_button(
                "Delete",
                "tonal",

                on_release=lambda *_:
                self._confirm_delete(
                    popup,
                    event["id"],
                ),
            )

            actions.add_widget(
                delete_btn
            )

        save_btn = _themed_button(
            "Save",
            "filled",
        )

        actions.add_widget(
            save_btn
        )

        # ============================================================
        # Save handler
        # ============================================================

        def do_save(*_args):

            title = (
                title_input.text.strip()
            )

            time_value = (
                time_picker.get_24h()
            )

            link_value = (
                link_input.text.strip()
            )

            is_recurring = (
                recurring_state["value"]
            )

            if not title:

                error_label.text = (
                    "Please enter a title."
                )

                return

            if mode == "add":

                create_event(
                    user_id=self._user_id(),

                    title=title,

                    event_date=(
                        self.selected_date
                    ),

                    event_time=(
                        time_value
                        or None
                    ),

                    event_link=(
                        link_value
                        or None
                    ),

                    is_recurring=is_recurring,
                )

            else:

                update_event(
                    event["id"],
                    title,
                    time_value or None,
                    link_value or None,
                    is_recurring,
                )

            popup.dismiss()

            self.build_month_grid()

            self.select_date(
                self.selected_date
            )

        save_btn.bind(
            on_release=do_save
        )

        panel.add_widget(
            actions
        )

        popup.open()

    # ----------------------------------------------------------------
    # Delete
    # ----------------------------------------------------------------

    def _confirm_delete(
        self,
        edit_popup,
        event_id,
    ):

        edit_popup.dismiss()

        delete_event(
            event_id
        )

        self.build_month_grid()

        self.select_date(
            self.selected_date
        )
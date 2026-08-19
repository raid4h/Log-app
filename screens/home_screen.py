from datetime import datetime, timedelta
import re

from kivymd.uix.screen import MDScreen
from kivy.utils import get_color_from_hex
from kivymd.app import MDApp
from kivy.properties import ListProperty
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.anchorlayout import MDAnchorLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.label import MDIcon
from kivy.uix.modalview import ModalView
from kivy.clock import Clock
from kivymd.uix.card import MDCard
from kivymd.uix.button import MDIconButton
from kivymd.uix.textfield import MDTextField
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.button import MDButton, MDButtonText

from theme.theme_manager import theme_manager
from theme.palettes import (
    BACKGROUND,
    CARD_PRIMARY,
    CARD_SECONDARY,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    ACCENT,
    BORDER,
    BUTTON,
    BUTTON_TEXT,
    TILE_ACCENT_POMODORO,
    TILE_ACCENT_TASKS,
)

from theme.themed_screen import ThemedScreenMixin
from widgets.dashboard_tile import DashboardTile

from database.planner_queries import (
    get_today_tasks,
    get_continue_studying,
    get_next_event,
    create_study_task,
    get_task_detail,
)

from services.checklist_store import (
    create_checklist,
    get_all_checklists,
)


# ============================================================
# ACTIVITY ICONS
# ============================================================

ACTIVITY_ICONS = {
    "study": "brain",
    "event": "calendar-outline",
    "task": "checkbox-marked-outline",
    "shopping": "cart-outline",
    "checklist_item": "checkbox-marked-outline",
}


SHOPPING_LIST_TITLE = "Shopping List"


# ============================================================
# TIME FORMATTING HELPER
# ============================================================

def _format_time_12h(value):
    """
    Extracts a time from a stored time/datetime value and displays it
    in 12-hour format, e.g. '18:00' -> '6:00 PM'.

    Handles values such as:
      18:00
      18:00:00
      2026-08-18 18:00
      2026-08-18 18:00:00
      2026-08-18T18:00:00+06:00
    """
    if value is None:
        return ""

    text = str(value).strip()
    if not text:
        return ""

    # Find HH:MM anywhere in the value. This also works when the
    # database stores the date and time together in one field.
    match = re.search(r"(?:^|[ T])([01]?\d|2[0-3]):([0-5]\d)", text)
    if not match:
        return ""

    hour = int(match.group(1))
    minute = int(match.group(2))

    period = "AM" if hour < 12 else "PM"
    hour_12 = hour % 12 or 12

    return f"{hour_12}:{minute:02d} {period}"


# ============================================================
# COLOR TINTING HELPER
# ============================================================

def _tint(icon_rgba, base_rgba, amount=0.16):
    """
    Blends an icon's accent color into a base card color at a low
    strength, so each quick-action tile gets its own tinted
    background.
    """
    return [
        base_rgba[0] * (1 - amount) + icon_rgba[0] * amount,
        base_rgba[1] * (1 - amount) + icon_rgba[1] * amount,
        base_rgba[2] * (1 - amount) + icon_rgba[2] * amount,
        1,
    ]


# ============================================================
# CLICKABLE TODAY-PLAN ROW
# ============================================================

class TappableRow(ButtonBehavior, MDBoxLayout):
    """
    A today-plan row that can be tapped to open its
    corresponding activity.
    """
    pass


# ============================================================
# CLICKABLE QUICK ACTION
# ============================================================

class QuickAction(ButtonBehavior, MDBoxLayout):
    """
    Small top-of-home action.

    The KV file uses root.open_notes(), root.open_checklist(),
    root.route_quick_add(), etc. Because `root` inside a
    QuickAction block refers to QuickAction itself, these proxy
    methods forward the request to HomeScreen.
    """

    def _get_home(self):
        app = MDApp.get_running_app()

        if app is None:
            return None

        try:
            return app.root.get_screen("home")
        except Exception:
            return None

    def open_notes(self):
        home = self._get_home()

        if home:
            home.open_notes()

    def open_checklist(self):
        home = self._get_home()

        if home:
            home.open_checklist()

    def route_quick_add(self, kind):
        home = self._get_home()

        if home:
            home.route_quick_add(kind)

    def open_study_session_popup(self):
        home = self._get_home()

        if home:
            home.open_study_session_popup()


# ============================================================
# HOME SCREEN
# ============================================================

class HomeScreen(ThemedScreenMixin, MDScreen):

    divider_color = ListProperty([0, 0, 0, 0])

    # ========================================================
    # THEME COLORS
    # ========================================================

    header_text_color = ListProperty([0, 0, 0, 1])
    header_secondary_color = ListProperty([0, 0, 0, 1])
    header_accent_color = ListProperty([0, 0, 0, 1])

    tile_accent_tasks_color = ListProperty([0, 0, 0, 1])
    tile_accent_pomodoro_color = ListProperty([0, 0, 0, 1])

    # Event gets its own color from TEXT_SECONDARY
    event_icon_color = ListProperty([0, 0, 0, 1])

    card_primary_color = ListProperty([1, 1, 1, 1])
    card_secondary_color = ListProperty([1, 1, 1, 1])
    fab_icon_color = ListProperty([1, 1, 1, 1])

    # ========================================================
    # QUICK ACTION TILE BACKGROUNDS
    # ========================================================

    quick_note_bg = ListProperty([0, 0, 0, 1])
    quick_checklist_bg = ListProperty([0, 0, 0, 1])
    quick_event_bg = ListProperty([0, 0, 0, 1])
    quick_focus_bg = ListProperty([0, 0, 0, 1])

    # ========================================================
    # INIT
    # ========================================================

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.bind(
            on_kv_post=lambda *x: self.apply_theme()
        )

        self._continue_studying_task_id = None
        self._next_event_id = None

    # ========================================================
    # THEME MAP
    # ========================================================

    THEME_MAP = {
        "self": ("md_bg_color", BACKGROUND),
        "drawer_layout": ("md_bg_color", BACKGROUND),

        "greeting_label": ("text_color", TEXT_PRIMARY),
        "date_label": ("text_color", TEXT_SECONDARY),
        "menu_button": ("icon_color", TEXT_PRIMARY),

        "next_up_label": ("text_color", TEXT_SECONDARY),
        "todays_log_label": ("text_color", TEXT_SECONDARY),
        "today_count_label": ("text_color", TEXT_SECONDARY),
    }

    # ========================================================
    # SCREEN ENTER
    # ========================================================

    def on_pre_enter(self, *args):

        self.apply_theme()

        self.set_greeting()

        # Rebuild the remaining Home sections from the database
        # whenever Home becomes visible.
        self.refresh_stats()
        self.build_today_plan()

    # ========================================================
    # THEME APPLICATION
    # ========================================================

    def on_theme_applied(self):
        """
        Updates HomeScreen colors using the existing theme system.

        Per-tile background distinction is achieved by tinting
        CARD_SECONDARY with each tile's own icon color at runtime.
        """

        try:

            self.header_text_color = get_color_from_hex(
                theme_manager.get_color(TEXT_PRIMARY)
            )

            self.header_secondary_color = get_color_from_hex(
                theme_manager.get_color(TEXT_SECONDARY)
            )

            self.header_accent_color = get_color_from_hex(
                theme_manager.get_color(ACCENT)
            )

            self.tile_accent_tasks_color = get_color_from_hex(
                theme_manager.get_color(TILE_ACCENT_TASKS)
            )

            self.tile_accent_pomodoro_color = get_color_from_hex(
                theme_manager.get_color(TILE_ACCENT_POMODORO)
            )

            # Event intentionally uses TEXT_SECONDARY so it remains
            # visually distinct from Note.
            self.event_icon_color = get_color_from_hex(
                theme_manager.get_color(TEXT_SECONDARY)
            )

            self.card_primary_color = get_color_from_hex(
                theme_manager.get_color(CARD_PRIMARY)
            )

            self.card_secondary_color = get_color_from_hex(
                theme_manager.get_color(CARD_SECONDARY)
            )

            self.fab_icon_color = get_color_from_hex(
                theme_manager.get_color(BUTTON_TEXT)
            )

            # ------------------------------------------------
            # QUICK ACTION TILE BACKGROUNDS
            # ------------------------------------------------

            self.quick_note_bg = _tint(
                self.header_accent_color,
                self.card_secondary_color,
            )

            self.quick_checklist_bg = _tint(
                self.tile_accent_tasks_color,
                self.card_secondary_color,
            )

            self.quick_event_bg = _tint(
                self.event_icon_color,
                self.card_secondary_color,
            )

            self.quick_focus_bg = _tint(
                self.tile_accent_pomodoro_color,
                self.card_secondary_color,
            )

            # ------------------------------------------------
            # DIVIDER / BORDER
            # ------------------------------------------------

            self.divider_color = get_color_from_hex(
                theme_manager.get_color(BORDER)
            )

        except Exception:
            # Prevent early theme application from crashing the screen.
            pass

    # ========================================================
    # GREETING
    # ========================================================

    def set_greeting(self):

        hour = datetime.now().hour

        if hour < 12:
            greeting = "Good morning"

        elif hour < 18:
            greeting = "Good afternoon"

        else:
            greeting = "Good evening"

        self.ids.greeting_label.text = greeting

        self.ids.date_label.text = datetime.now().strftime(
            "%A, %d %B"
        )

    # ========================================================
    # TODAY'S PLAN
    # ========================================================

    def build_today_plan(self):

        self.ids.today_plan_list.clear_widgets()

        app = MDApp.get_running_app()

        user_id = getattr(
            app,
            "user_id",
            1
        )

        today_str = datetime.now().strftime(
            "%Y-%m-%d"
        )

        tasks = get_today_tasks(
            user_id,
            today_str
        )

        text_color = get_color_from_hex(
            theme_manager.get_color(TEXT_PRIMARY)
        )

        subtext_color = get_color_from_hex(
            theme_manager.get_color(TEXT_SECONDARY)
        )

        accent_color = get_color_from_hex(
            theme_manager.get_color(ACCENT)
        )

        secondary_card_color = get_color_from_hex(
            theme_manager.get_color(CARD_SECONDARY)
        )

        # ====================================================
        # EMPTY STATE
        # ====================================================

        if not tasks:

            empty_box = MDBoxLayout(
                orientation="vertical",
                size_hint_y=None,
                height=dp(82),
                spacing=dp(4),
                padding=(dp(6), dp(8)),
            )

            empty_icon = MDIcon(
                icon="notebook-outline",
                theme_text_color="Custom",
                text_color=subtext_color,
                size_hint=(None, None),
                size=(dp(28), dp(28)),
            )

            empty_title = MDLabel(
                text="Your day is clear",
                font_style="Title",
                role="small",
                bold=True,
                theme_text_color="Custom",
                text_color=text_color,
                adaptive_height=True,
            )

            empty_subtitle = MDLabel(
                text="Nothing planned for today",
                font_style="Body",
                role="small",
                theme_text_color="Custom",
                text_color=subtext_color,
                adaptive_height=True,
            )

            empty_box.add_widget(empty_icon)
            empty_box.add_widget(empty_title)
            empty_box.add_widget(empty_subtitle)

            self.ids.today_plan_list.add_widget(
                empty_box
            )

            self.ids.today_count_label.text = ""

            return

        # ====================================================
        # COUNT
        # ====================================================

        count = len(tasks)

        self.ids.today_count_label.text = (
            f"{count} item"
            f"{'s' if count != 1 else ''}"
        )

        # ====================================================
        # BUILD EACH ROW
        # ====================================================

        for index, task in enumerate(tasks):

            kind = task.get(
                "activity_type",
                "task"
            )

            icon_name = ACTIVITY_ICONS.get(
                kind,
                "checkbox-marked-outline"
            )

            # ------------------------------------------------
            # META INFORMATION
            # ------------------------------------------------

            meta_parts = []

            if task.get("note_count"):

                note_count = task["note_count"]

                meta_parts.append(
                    f"{note_count} note"
                    f"{'s' if note_count != 1 else ''}"
                )

            if task.get("pomodoro_completed"):

                focus_count = task[
                    "pomodoro_completed"
                ]

                meta_parts.append(
                    f"{focus_count} focus"
                    f"{' sessions' if focus_count != 1 else ' session'}"
                )

            meta_text = " · ".join(
                meta_parts
            )

            # ------------------------------------------------
            # SUBTITLE
            # ------------------------------------------------

            subtitle_parts = []

            # Today's Log already tells the user this item is from today,
            # so do NOT show the date. Get the time from due_time when
            # available, otherwise extract it from due_date. Some database
            # records store the full datetime in due_date.
            stored_time = task.get("due_time") or task.get("due_date")
            time_display = _format_time_12h(stored_time)

            if time_display:
                subtitle_parts.append(time_display)

            # Metadata
            if meta_text:
                subtitle_parts.append(
                    meta_text
                )

            subtitle_text = " · ".join(
                subtitle_parts
            )

            # ------------------------------------------------
            # ROW HEIGHT
            # ------------------------------------------------

            row_height = (
                dp(72)
                if meta_text
                else dp(62)
            )

            # ------------------------------------------------
            # CLICKABLE ROW
            # ------------------------------------------------

            row = TappableRow(
                orientation="horizontal",
                spacing=dp(12),
                padding=(dp(6), dp(5)),
                size_hint_y=None,
                height=row_height,
            )

            row.bind(
                on_release=lambda inst, t=task:
                self.open_checklist_item(t)
                if t["activity_type"] == "checklist_item"
                else self.open_task_detail(t["id"])
            )

            # ------------------------------------------------
            # ICON COLOR
            # ------------------------------------------------

            if kind == "task":

                icon_color = get_color_from_hex(
                    theme_manager.get_color(
                        TILE_ACCENT_TASKS
                    )
                )

            elif kind == "study":

                icon_color = get_color_from_hex(
                    theme_manager.get_color(
                        TILE_ACCENT_POMODORO
                    )
                )

            elif kind == "event":

                icon_color = get_color_from_hex(
                    theme_manager.get_color(
                        TEXT_SECONDARY
                    )
                )

            else:

                icon_color = accent_color

            # ------------------------------------------------
            # ICON
            # ------------------------------------------------

            icon_box = MDAnchorLayout(
                size_hint=(None, 1),
                width=dp(38),
                anchor_x="center",
                anchor_y="center",
            )

            icon_box.add_widget(
                MDIcon(
                    icon=icon_name,
                    theme_text_color="Custom",
                    text_color=icon_color,
                    size_hint=(None, None),
                    size=(dp(28), dp(28)),
                )
            )

            row.add_widget(
                icon_box
            )

            # ------------------------------------------------
            # TEXT
            # ------------------------------------------------

            text_wrapper = MDAnchorLayout(
                size_hint_x=1,
                anchor_x="left",
                anchor_y="center",
            )

            text_box = MDBoxLayout(
                orientation="vertical",
                spacing=dp(2),
                size_hint=(1, None),
                adaptive_height=True,
            )

            title_label = MDLabel(
                text=str(task.get("title", "")),
                font_style="Title",
                role="small",
                bold=True,
                theme_text_color="Custom",
                text_color=text_color,
                adaptive_height=True,
                shorten=True,
                shorten_from="right",
            )

            text_box.add_widget(
                title_label
            )

            if subtitle_text:

                subtitle_label = MDLabel(
                    text=subtitle_text,
                    font_style="Body",
                    role="small",
                    theme_text_color="Custom",
                    text_color=subtext_color,
                    adaptive_height=True,
                    shorten=True,
                    shorten_from="right",
                )

                text_box.add_widget(
                    subtitle_label
                )

            text_wrapper.add_widget(
                text_box
            )

            row.add_widget(
                text_wrapper
            )

            # ------------------------------------------------
            # CHEVRON
            # ------------------------------------------------

            arrow_box = MDAnchorLayout(
                size_hint=(None, 1),
                width=dp(24),
                anchor_x="center",
                anchor_y="center",
            )

            arrow_box.add_widget(
                MDIcon(
                    icon="chevron-right",
                    theme_text_color="Custom",
                    text_color=subtext_color,
                    size_hint=(None, None),
                    size=(dp(22), dp(22)),
                )
            )

            row.add_widget(
                arrow_box
            )

            self.ids.today_plan_list.add_widget(
                row
            )

            # ------------------------------------------------
            # DIVIDER
            # ------------------------------------------------

            if index < len(tasks) - 1:

                divider = MDBoxLayout(
                    size_hint_y=None,
                    height=dp(1),
                    padding=(
                        dp(52),
                        0,
                        dp(4),
                        0,
                    ),
                )

                divider.add_widget(
                    MDCard(
                        theme_bg_color="Custom",
                        md_bg_color=secondary_card_color,
                        radius=[0],
                    )
                )

                self.ids.today_plan_list.add_widget(
                    divider
                )

    # ========================================================
    # OPEN TODAY-PLAN ITEM
    # ========================================================

    def open_task_detail(self, task_id):

        if isinstance(
            task_id,
            str
        ) and task_id.startswith("cal-"):

            calendar_screen = self.manager.get_screen(
                "calendar"
            )

            calendar_screen.selected_date = (
                datetime.now().strftime(
                    "%Y-%m-%d"
                )
            )

            self.manager.current = "calendar"

            return

        task = get_task_detail(
            task_id
        )

        if not task:
            return

        activity_type = task[
            "activity_type"
        ]

        if activity_type == "study":

            timer = self.manager.get_screen(
                "timer"
            )

            timer.current_task_id = task_id

            self.manager.current = "timer"

        elif activity_type == "shopping":

            editor = self.manager.get_screen(
                "note_editor"
            )

            if task["notes"]:

                editor.current_note_id = (
                    task["notes"][0][0]
                )

            else:

                editor.current_note_id = None

            self.manager.current = (
                "note_editor"
            )

        elif activity_type in (
            "event",
            "task",
        ):

            calendar = self.manager.get_screen(
                "calendar"
            )

            calendar.selected_task_id = (
                task_id
            )

            self.manager.current = (
                "calendar"
            )

    def open_checklist_item(self, task):
        """
        Routes a tapped 'checklist_item' row to its parent checklist.
        """

        detail_screen = self.manager.get_screen(
            "checklist_detail"
        )

        detail_screen.checklist_id = (
            task["_checklist_id"]
        )

        self.manager.current = (
            "checklist_detail"
        )

    # ========================================================
    # NEXT UP
    # ========================================================

    def refresh_stats(self):

        app = MDApp.get_running_app()

        user_id = getattr(
            app,
            "user_id",
            1
        )

        next_event = get_next_event(
            user_id
        )

        # ----------------------------------------------------
        # NO UPCOMING EVENT
        # ----------------------------------------------------

        if not next_event:

            self._next_event_id = None

            self.ids.next_up_title.text = (
                "Nothing scheduled"
            )

            self.ids.next_up_subtitle.text = (
                "Your schedule is clear"
            )

            self.ids.next_up_number.text = ""

            self.ids.next_up_unit.text = ""

            self.ids.next_up_icon.icon = (
                "calendar-blank-outline"
            )

            return

        # ----------------------------------------------------
        # STORE EVENT
        # ----------------------------------------------------

        self._next_event_id = (
            next_event["id"]
        )

        title = next_event[
            "title"
        ]

        due_date = next_event[
            "due_date"
        ]

        due_time = (
            next_event["due_time"]
            or ""
        )

        # ----------------------------------------------------
        # PARSE DATE/TIME
        # ----------------------------------------------------

        try:

            if due_time:

                due_datetime = datetime.strptime(
                    f"{due_date} {due_time}",
                    "%Y-%m-%d %H:%M"
                )

            else:

                due_datetime = datetime.strptime(
                    due_date,
                    "%Y-%m-%d"
                )

        except (ValueError, TypeError):

            self.ids.next_up_title.text = title
            self.ids.next_up_subtitle.text = str(
                due_date
            )
            self.ids.next_up_number.text = ""
            self.ids.next_up_unit.text = ""

            return

        # ----------------------------------------------------
        # ROLL FORWARD OVERDUE TIMED REMINDERS
        # ----------------------------------------------------

        now = datetime.now()

        if due_time:

            while due_datetime <= now:
                due_datetime += timedelta(
                    days=1
                )

        due_time_display = _format_time_12h(
            due_time
        )

        # ----------------------------------------------------
        # SUBTITLE
        # ----------------------------------------------------

        if due_datetime.date() == datetime.now().date():

            subtitle = (
                due_time_display
                or "Today"
            )

        else:

            subtitle = due_datetime.strftime(
                "%a, %d %b"
            )

            if due_time_display:

                subtitle += (
                    f" · {due_time_display}"
                )

        # ----------------------------------------------------
        # TIME REMAINING
        # ----------------------------------------------------

        seconds_until = max(
            int(
                (
                    due_datetime
                    - datetime.now()
                ).total_seconds()
            ),
            0
        )

        minutes_until = (
            seconds_until // 60
        )

        if seconds_until < 60:

            self.ids.next_up_number.text = (
                str(seconds_until)
            )

            self.ids.next_up_unit.text = (
                "sec"
            )

        elif minutes_until < 60:

            self.ids.next_up_number.text = (
                str(minutes_until)
            )

            self.ids.next_up_unit.text = (
                "min"
            )

        elif minutes_until < 1440:

            hours_until = (
                minutes_until // 60
            )

            self.ids.next_up_number.text = (
                str(hours_until)
            )

            self.ids.next_up_unit.text = (
                "hr"
                if hours_until == 1
                else "hrs"
            )

        else:

            days_until = (
                minutes_until // 1440
            )

            self.ids.next_up_number.text = (
                str(days_until)
            )

            self.ids.next_up_unit.text = (
                "day"
                if days_until == 1
                else "days"
            )

        # ----------------------------------------------------
        # UPDATE UI
        # ----------------------------------------------------

        self.ids.next_up_title.text = title

        self.ids.next_up_subtitle.text = (
            subtitle
        )

    # ========================================================
    # QUICK ACTIONS
    # ========================================================

    def open_notes(self):

        editor = self.manager.get_screen(
            "note_editor"
        )

        editor.current_note_id = None

        self.manager.current = (
            "note_editor"
        )

    def open_checklist(self):

        self.manager.current = (
            "checklist"
        )

    # ========================================================
    # STUDY SESSION POPUP
    # ========================================================

    def open_study_session_popup(self):

        bg_color = get_color_from_hex(
            theme_manager.get_color(
                CARD_PRIMARY
            )
        )

        card = MDCard(
            orientation="vertical",
            spacing=dp(15),
            padding=dp(20),
            radius=[18],
            size_hint=(None, None),
            size=(dp(360), dp(420)),
            theme_bg_color="Custom",
            md_bg_color=bg_color,
        )

        title = MDLabel(
            text="New Study Session",
            font_style="Title",
            role="medium",
            adaptive_height=True,
        )

        subject = MDTextField(
            hint_text="Subject"
        )

        goal = MDTextField(
            hint_text="Goal"
        )

        duration = MDTextField(
            hint_text="Duration (minutes)",
            text="25"
        )

        start_now = MDCheckbox(
            active=True
        )

        row = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(10),
            adaptive_height=True,
        )

        row.add_widget(
            start_now
        )

        row.add_widget(
            MDLabel(
                text="Start immediately",
                adaptive_height=True,
            )
        )

        button_row = MDBoxLayout(
            spacing=dp(10),
            adaptive_height=True,
        )

        cancel_btn = MDButton(
            MDButtonText(
                text="Cancel"
            ),
            style="outlined",
        )

        create_btn = MDButton(
            MDButtonText(
                text="Create"
            ),
            style="filled",
        )

        button_row.add_widget(
            cancel_btn
        )

        button_row.add_widget(
            create_btn
        )

        card.add_widget(
            title
        )

        card.add_widget(
            MDLabel(
                text="Subject",
                adaptive_height=True,
                font_style="Label",
                role="large",
            )
        )

        card.add_widget(
            subject
        )

        card.add_widget(
            MDLabel(
                text="Goal",
                adaptive_height=True,
                font_style="Label",
                role="large",
            )
        )

        card.add_widget(
            goal
        )

        card.add_widget(
            MDLabel(
                text="Duration (minutes)",
                adaptive_height=True,
                font_style="Label",
                role="large",
            )
        )

        card.add_widget(
            duration
        )

        card.add_widget(
            row
        )

        card.add_widget(
            button_row
        )

        modal = ModalView(
            auto_dismiss=False,
            background_color=(
                0,
                0,
                0,
                .45,
            ),
        )

        modal.add_widget(
            card
        )

        cancel_btn.bind(
            on_release=lambda *_:
            modal.dismiss()
        )

        create_btn.bind(
            on_release=lambda *_:
            self.create_study_session(
                modal,
                subject.text,
                goal.text,
                int(duration.text),
                start_now.active,
            )
        )

        modal.open()

    # ========================================================
    # CREATE STUDY SESSION
    # ========================================================

    def create_study_session(
        self,
        modal,
        subject,
        goal,
        duration,
        start_now,
    ):

        modal.dismiss()

        app = MDApp.get_running_app()

        user_id = getattr(
            app,
            "user_id",
            1
        )

        subject = (
            subject.strip()
            if subject
            else "Study Session"
        )

        goal = (
            goal.strip()
            if goal
            else "Focus Session"
        )

        title = (
            f"{subject} - {goal}"
        )

        task_id = create_study_task(
            user_id=user_id,
            title=title,
            duration=duration,
        )

        if start_now:

            timer = self.manager.get_screen(
                "timer"
            )

            timer.current_task_id = (
                task_id
            )

            self.manager.current = (
                "timer"
            )

        else:

            # Refresh only the Home sections that still exist.
            self.refresh_stats()
            self.build_today_plan()

    # ========================================================
    # RESUME STUDYING
    # ========================================================

    def resume_studying(self):

        if self._continue_studying_task_id is None:
            return

        timer = self.manager.get_screen(
            "timer"
        )

        timer.current_task_id = (
            self._continue_studying_task_id
        )

        self.manager.current = (
            "timer"
        )

    # ========================================================
    # GENERIC NAVIGATION
    # ========================================================

    def go_to(self, screen_name):

        self.manager.current = (
            screen_name
        )

    # ========================================================
    # SETTINGS
    # ========================================================

    def open_settings(self):

        self.manager.current = (
            "settings"
        )

    # ========================================================
    # QUICK ADD BOTTOM SHEET
    # ========================================================

    def open_quick_add(self):

        bg_color = get_color_from_hex(
            theme_manager.get_color(
                CARD_PRIMARY
            )
        )

        text_color = get_color_from_hex(
            theme_manager.get_color(
                TEXT_PRIMARY
            )
        )

        card = MDCard(
            orientation="vertical",
            theme_bg_color="Custom",
            md_bg_color=bg_color,
            size_hint=(1, None),
            adaptive_height=True,
            padding=dp(20),
            spacing=dp(12),
            radius=[24, 24, 0, 0],
        )

        card.add_widget(
            MDLabel(
                text="What do you want to add?",
                font_style="Title",
                role="medium",
                theme_text_color="Custom",
                text_color=text_color,
                adaptive_height=True,
            )
        )

        modal = ModalView(
            size_hint=(1, None),
            height=dp(1),
            pos_hint={
                "center_x": 0.5,
                "y": 0,
            },
            background_color=(
                0,
                0,
                0,
                0.5,
            ),
        )

        def choose(kind):

            modal.dismiss()

            self.route_quick_add(
                kind
            )

        # ----------------------------------------------------
        # STUDY
        # ----------------------------------------------------

        card.add_widget(
            QuickAddOption(
                "timer-outline",
                "Study Session",
                "Plan your study with Pomodoro",
                lambda: choose("study"),
            )
        )

        # ----------------------------------------------------
        # EVENT
        # ----------------------------------------------------

        card.add_widget(
            QuickAddOption(
                "calendar-outline",
                "Event",
                "Add to calendar",
                lambda: choose("event"),
            )
        )

        # ----------------------------------------------------
        # NOTE
        # ----------------------------------------------------

        card.add_widget(
            QuickAddOption(
                "note-text-outline",
                "Start Noting",
                "Jot something down",
                lambda: choose("note"),
            )
        )

        # ----------------------------------------------------
        # SHOPPING
        # ----------------------------------------------------

        card.add_widget(
            QuickAddOption(
                "cart-outline",
                "Shopping List",
                "Track items and budget",
                lambda: choose("shopping"),
            )
        )

        modal.add_widget(
            card
        )

        card.bind(
            height=lambda _inst, value:
            setattr(
                modal,
                "height",
                value
            )
        )

        modal.height = card.height

        modal.open()

    # ========================================================
    # ROUTE QUICK ADD
    # ========================================================

    def route_quick_add(self, kind):

        # ----------------------------------------------------
        # EVENT
        # ----------------------------------------------------

        if kind == "event":

            self.manager.current = (
                "calendar"
            )

            calendar_screen = (
                self.manager.get_screen(
                    "calendar"
                )
            )

            Clock.schedule_once(
                lambda _dt:
                calendar_screen.open_add_task_popup(
                    activity_type=kind
                ),
                0,
            )

        # ----------------------------------------------------
        # STUDY
        # ----------------------------------------------------

        elif kind == "study":

            self.open_study_session_popup()

        # ----------------------------------------------------
        # NOTE
        # ----------------------------------------------------

        elif kind == "note":

            editor = self.manager.get_screen(
                "note_editor"
            )

            editor.current_note_id = None

            self.manager.current = (
                "note_editor"
            )

        # ----------------------------------------------------
        # SHOPPING
        # ----------------------------------------------------

        elif kind == "shopping":

            self.open_shopping_list()

    # ========================================================
    # SHOPPING LIST
    # ========================================================

    def open_shopping_list(self):

        user_id = getattr(
            MDApp.get_running_app(),
            "user_id",
            1
        )

        existing = next(
            (
                c
                for c in get_all_checklists(
                    user_id
                )
                if c["title"] == SHOPPING_LIST_TITLE
            ),
            None,
        )

        if existing is not None:

            checklist_id = (
                existing["id"]
            )

        else:

            checklist_id = create_checklist(
                title=SHOPPING_LIST_TITLE,
                priority="",
                user_id=user_id,
            )

        detail_screen = (
            self.manager.get_screen(
                "checklist_detail"
            )
        )

        detail_screen.checklist_id = (
            checklist_id
        )

        self.manager.current = (
            "checklist_detail"
        )


# ============================================================
# QUICK ADD OPTION
# ============================================================

class QuickAddOption(
    ButtonBehavior,
    MDBoxLayout
):
    """
    One row in the Quick Add sheet:
    icon + title + subtitle.
    """

    def __init__(
        self,
        icon,
        title,
        subtitle,
        on_press,
        **kwargs
    ):

        kwargs.setdefault(
            "orientation",
            "horizontal"
        )

        kwargs.setdefault(
            "size_hint_y",
            None
        )

        kwargs.setdefault(
            "height",
            dp(64)
        )

        kwargs.setdefault(
            "spacing",
            dp(14)
        )

        kwargs.setdefault(
            "padding",
            [
                dp(4),
                dp(8),
                dp(4),
                dp(8),
            ]
        )

        super().__init__(
            **kwargs
        )

        self._on_press = on_press

        text_color = get_color_from_hex(
            theme_manager.get_color(
                TEXT_PRIMARY
            )
        )

        sub_color = get_color_from_hex(
            theme_manager.get_color(
                TEXT_SECONDARY
            )
        )

        chip_color = get_color_from_hex(
            theme_manager.get_color(
                CARD_SECONDARY
            )
        )

        accent_color = get_color_from_hex(
            theme_manager.get_color(
                ACCENT
            )
        )

        # ----------------------------------------------------
        # ICON CHIP
        # ----------------------------------------------------

        icon_card = MDCard(
            theme_bg_color="Custom",
            md_bg_color=chip_color,
            size_hint=(None, None),
            size=(
                dp(44),
                dp(44),
            ),
            radius=[14],
            pos_hint={
                "center_y": 0.5
            },
        )

        icon_card.add_widget(
            MDIcon(
                icon=icon,
                theme_text_color="Custom",
                text_color=accent_color,
                size_hint=(None, None),
                size=(
                    dp(24),
                    dp(24),
                ),
                pos_hint={
                    "center_x": 0.5,
                    "center_y": 0.5,
                },
                halign="center",
                valign="middle",
            )
        )

        self.add_widget(
            icon_card
        )

        # ----------------------------------------------------
        # TEXT
        # ----------------------------------------------------

        text_box = MDBoxLayout(
            orientation="vertical",
            spacing=dp(2),
            pos_hint={
                "center_y": 0.5
            },
        )

        text_box.add_widget(
            MDLabel(
                text=title,
                font_style="Title",
                role="small",
                theme_text_color="Custom",
                text_color=text_color,
                adaptive_height=True,
            )
        )

        text_box.add_widget(
            MDLabel(
                text=subtitle,
                font_style="Body",
                role="small",
                theme_text_color="Custom",
                text_color=sub_color,
                adaptive_height=True,
            )
        )

        self.add_widget(
            text_box
        )

    def on_release(self):

        if self._on_press:

            self._on_press()
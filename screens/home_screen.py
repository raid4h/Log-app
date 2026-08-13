from datetime import datetime
from kivymd.uix.screen import MDScreen
from kivy.utils import get_color_from_hex
from kivymd.app import MDApp
from kivy.properties import ListProperty
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivymd.uix.boxlayout import MDBoxLayout
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
    BACKGROUND, CARD_PRIMARY, CARD_SECONDARY,
    TEXT_PRIMARY, TEXT_SECONDARY, ACCENT, BORDER, BUTTON
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

from services.checklist_store import create_checklist, get_all_checklists

# Maps activity_type -> icon, since tasks created via different Quick
# Add options ("Study Session" / "Event" / "Task" / "Shopping") should
# read differently at a glance on Home, even though they're all just
# rows from the same tasks table.
ACTIVITY_ICONS = {
    "study": "brain",
    "event": "calendar-outline",
    "task": "checkbox-marked-outline",
    "shopping": "cart-outline",
}

# Title used for the auto-created checklist behind the "Shopping List"
# Quick Add option. Kept as a constant so the create path and the
# reuse-lookup path below can never drift out of sync with each other.
SHOPPING_LIST_TITLE = "Shopping List"


class TappableRow(ButtonBehavior, MDBoxLayout):
    """A today-plan row that can be tapped to open its ActivityDetailScreen."""
    pass


class HomeScreen(ThemedScreenMixin, MDScreen):

    divider_color = ListProperty([0, 0, 0, 0])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(on_kv_post=lambda *x: self.apply_theme())
        self._continue_studying_task_id = None

    THEME_MAP = {
        "self":              ("md_bg_color", BACKGROUND),
        "drawer_layout":     ("md_bg_color", BACKGROUND),
        "greeting_label":    ("text_color", TEXT_PRIMARY),
        "date_label":        ("text_color", TEXT_SECONDARY),
        "menu_button":       ("icon_color", TEXT_PRIMARY),
        "today_plan_card":   ("md_bg_color", CARD_PRIMARY),
        "next_up_label":     ("text_color", TEXT_PRIMARY),
        "todays_plan_label": ("text_color", TEXT_PRIMARY),
        "checklist_label":   ("text_color", TEXT_PRIMARY),
    }

    def on_pre_enter(self, *args):
        self.apply_theme()
        self.set_greeting()
        self.refresh_stats()
        self.build_today_plan()
        self.build_checklist_entry()

    def on_theme_applied(self):
        if hasattr(self.ids.up_next_tile, "apply_theme"):
            self.ids.up_next_tile.apply_theme()
    #    self.divider_color = get_color_from_hex(theme_manager.get_color(BORDER))

    def set_greeting(self):
        hour = datetime.now().hour
        if hour < 12:
            greeting = "Good morning"
        elif hour < 18:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"
        self.ids.greeting_label.text = greeting
        self.ids.date_label.text = datetime.now().strftime("%A, %d %B")

    def build_today_plan(self):
        self.ids.today_plan_list.clear_widgets()

        app = MDApp.get_running_app()
        user_id = getattr(app, "user_id", 1)
        today_str = datetime.now().strftime("%Y-%m-%d")

        tasks = get_today_tasks(user_id, today_str)

        text_color = get_color_from_hex(theme_manager.get_color(TEXT_PRIMARY))
        subtext_color = get_color_from_hex(theme_manager.get_color(TEXT_SECONDARY))

        if not tasks:
            empty_label = MDLabel(
                text="Nothing planned for today",
                font_style="Body", role="small",
                theme_text_color="Custom", text_color=subtext_color,
                size_hint_y=None, height=dp(28),
            )
            self.ids.today_plan_list.add_widget(empty_label)
            return

        for task in tasks:
            icon_name = ACTIVITY_ICONS.get(task["activity_type"], "checkbox-marked-outline")

            # Build the "note note · focus session" subtext -- this
            # one line is what actually sells "everything is linked"
            # on Home without opening anything.
            meta_parts = []
            if task["note_count"]:
                meta_parts.append(f"{task['note_count']} note{'s' if task['note_count'] != 1 else ''}")
            if task["pomodoro_completed"]:
                meta_parts.append(f"{task['pomodoro_completed']} focus session{'s' if task['pomodoro_completed'] != 1 else ''}")
            meta_text = " · ".join(meta_parts)

            row = TappableRow(
                orientation="vertical", spacing=dp(2),
                size_hint_y=None, height=dp(44) if meta_text else dp(28),
            )
            row.bind(on_release=lambda inst, tid=task["id"]: self.open_task_detail(tid))

            title_row = MDBoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(28))
            title_row.add_widget(MDIcon(
                icon=icon_name,
                theme_text_color="Custom", text_color=subtext_color,
                size_hint=(None, None), size=(dp(24), dp(24)),
            ))

            title_label = MDLabel(
                text=task["title"], font_style="Body", role="small",
                size_hint_x=1, shorten=True, shorten_from="right",
                theme_text_color="Custom", text_color=text_color,
            )
            title_label.bind(width=lambda inst, w: setattr(inst, "text_size", (w, None)))

            due_label = MDLabel(
                text=task["due_date"] or "", font_style="Label", role="small",
                halign="right", size_hint_x=None, width=dp(80),
                theme_text_color="Custom", text_color=subtext_color,
            )

            title_row.add_widget(title_label)
            title_row.add_widget(due_label)
            row.add_widget(title_row)

            if meta_text:
                meta_label = MDLabel(
                    text=meta_text, font_style="Label", role="small",
                    size_hint_x=1, theme_text_color="Custom", text_color=subtext_color,
                    padding=(dp(34), 0),
                )
                row.add_widget(meta_label)

            self.ids.today_plan_list.add_widget(row)

    def open_task_detail(self, task_id):
        task = get_task_detail(task_id)

        if task["activity_type"] == "study":
            timer = self.manager.get_screen("timer")
            timer.current_task_id = task_id
            self.manager.current = "timer"

        elif task["activity_type"] == "shopping":
            editor = self.manager.get_screen("note_editor")
            if task["notes"]:
                editor.current_note_id = task["notes"][0][0]   # first note id
            else:
                editor.current_note_id = None

            self.manager.current = "note_editor"

        elif task["activity_type"] in ("event", "task"):
            calendar = self.manager.get_screen("calendar")
            calendar.selected_task_id = task_id
            self.manager.current = "calendar"

    def refresh_stats(self):
        app = MDApp.get_running_app()
        user_id = getattr(app, "user_id", 1)

        self.ids.continue_studying_container.clear_widgets()
        self._continue_studying_task_id = None

        continue_studying = get_continue_studying(user_id)
        if continue_studying:
            self._continue_studying_task_id = continue_studying["task_id"]

            label = MDLabel(
                text="Continue Studying",
                theme_text_color="Custom",
                text_color=get_color_from_hex(theme_manager.get_color(TEXT_PRIMARY)),
                font_style="Title", role="small",
                adaptive_height=True,
            )

            tile = DashboardTile(
                label=continue_studying["task_title"],
                subtitle="Resume focus session",
                icon_name="book-open-page-variant-outline",
                size_hint_y=None,
                height=dp(110),
            )

            tile.on_release = self.resume_studying
            if hasattr(tile, "apply_theme"):
                tile.apply_theme()

            self.ids.continue_studying_container.add_widget(label)
            self.ids.continue_studying_container.add_widget(tile)

        next_event = get_next_event(user_id)
        if next_event:
            due_date = next_event["due_date"]
            due_time = next_event["due_time"] or ""

            if due_time:
                due_datetime = datetime.strptime(f"{due_date} {due_time}", "%Y-%m-%d %H:%M")
            else:
                due_datetime = datetime.strptime(due_date, "%Y-%m-%d")

            self.ids.up_next_tile.label = next_event["title"]
            self._next_event_id = next_event["id"]

            # Subtitle: bare time only if it's today, otherwise show the date too
            if due_datetime.date() == datetime.now().date():
                self.ids.up_next_tile.subtitle = due_time or "Today"
            else:
                self.ids.up_next_tile.subtitle = due_datetime.strftime("%a, %d %b") + (f" · {due_time}" if due_time else "")

            minutes_until = int((due_datetime - datetime.now()).total_seconds() // 60)
            hours_until = minutes_until // 60

            if minutes_until < 60:
                self.ids.up_next_tile.stat_number = str(max(minutes_until, 0))
                self.ids.up_next_tile.stat_label = "min"
            elif hours_until < 24:
                self.ids.up_next_tile.stat_number = str(hours_until)
                self.ids.up_next_tile.stat_label = "hr" if hours_until == 1 else "hrs"
            else:
                days_until = hours_until // 24
                self.ids.up_next_tile.stat_number = str(days_until)
                self.ids.up_next_tile.stat_label = "day" if days_until == 1 else "days"
        
        else:
            self.ids.up_next_tile.label = "Nothing scheduled"
            self.ids.up_next_tile.subtitle = ""
            self.ids.up_next_tile.stat_number = ""
            self.ids.up_next_tile.stat_label = ""
            self._next_event_id = None

    def build_checklist_entry(self):
        """
        Home's entry point into the Checklist feature -- one static
        DashboardTile, same construction pattern already used for the
        "Continue Studying" tile above: built in Python, on_release
        assigned directly as an instance attribute, apply_theme()
        called explicitly since it's created outside the normal
        .kv-driven theming pass.
        """
        self.ids.checklist_container.clear_widgets()

        tile = DashboardTile(
            label="Checklist",
            subtitle="Cross off your to-dos",
            icon_name="checkbox-marked-outline",
        )
        tile.on_release = self.open_checklist
        if hasattr(tile, "apply_theme"):
            tile.apply_theme()

        self.ids.checklist_container.add_widget(tile)

    def open_checklist(self):
        self.manager.current = "checklist"
    
    def open_study_session_popup(self):
        bg_color = get_color_from_hex(theme_manager.get_color(CARD_PRIMARY))

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

        start_now = MDCheckbox(active=True)

        row = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(10),
            adaptive_height=True,
        )

        row.add_widget(start_now)
        row.add_widget(
            MDLabel(
                text="Start immediately",
                adaptive_height=True
          )
        )

        button_row = MDBoxLayout(
            spacing=dp(10),
            adaptive_height=True
        )

        cancel_btn = MDButton(
            MDButtonText(text="Cancel"),
            style="outlined"
        )

        create_btn = MDButton(
            MDButtonText(text="Create"),
            style="filled"
        )

        button_row.add_widget(cancel_btn)
        button_row.add_widget(create_btn)

        card.add_widget(title)
        card.add_widget(
            MDLabel(
                text="Subject",
                adaptive_height=True,
                font_style="Label",
                role="large",
                )
            )
    
        card.add_widget(subject)
        card.add_widget(
            MDLabel(
                text="Goal",
                adaptive_height=True,
                font_style="Label",
                role="large",
            )
        )
    
        card.add_widget(goal)
        card.add_widget(
            MDLabel(
                text="Duration (minutes)",
                adaptive_height=True,
                font_style="Label",
                role="large",
            )
        )
    
        card.add_widget(duration)
    
        card.add_widget(row)
        
        card.add_widget(button_row)

        modal = ModalView(
            auto_dismiss=False,
            background_color=(0,0,0,.45)
        )

        modal.add_widget(card)

        cancel_btn.bind(on_release=lambda *_: modal.dismiss())

        create_btn.bind(
            on_release=lambda *_:
            self.create_study_session(
                modal,
                subject.text,
                goal.text,
                int(duration.text),
                start_now.active
         )
        )

        modal.open()
    
    def create_study_session(
        self,
        modal,
        subject,
        goal,
        duration,
        start_now,
    ):
        modal.dismiss()

        title = f"{subject} - {goal}"

        task_id = create_study_task(
            user_id=1,
            title=title,
            duration=duration,
        )

        if start_now:

            timer = self.manager.get_screen("timer")
            timer.current_task_id = task_id
            self.manager.current = "timer"

        else:

            self.refresh_stats()
            self.build_today_plan()
               
    def resume_studying(self):
      if self._continue_studying_task_id is None:
          return
      timer = self.manager.get_screen("timer")
      timer.current_task_id = self._continue_studying_task_id
      self.manager.current = "timer"        
            
    def go_to(self, screen_name):
        self.manager.current = screen_name

    def open_settings(self):
        self.manager.current = "settings"
        
    def open_quick_add(self):
        bg_color = get_color_from_hex(theme_manager.get_color(CARD_PRIMARY))
        text_color = get_color_from_hex(theme_manager.get_color(TEXT_PRIMARY))

        card = MDCard(
            orientation="vertical",
            theme_bg_color="Custom", md_bg_color=bg_color,
            size_hint=(1, None), adaptive_height=True,
            padding=dp(20), spacing=dp(12),
            radius=[24, 24, 0, 0],
        )
        card.add_widget(MDLabel(
            text="What do you want to add?",
            font_style="Title", role="medium",
            theme_text_color="Custom", text_color=text_color,
            adaptive_height=True,
        ))

        modal = ModalView(
            size_hint=(1, None), height=dp(1),
            pos_hint={"center_x": 0.5, "y": 0},
            background_color=(0, 0, 0, 0.5),
        )

        def choose(kind):
            modal.dismiss()
            self.route_quick_add(kind)

        card.add_widget(QuickAddOption("timer-outline", "Study Session",
                                    "Plan your study with Pomodoro", lambda: choose("study")))
        card.add_widget(QuickAddOption("calendar-outline", "Event",
                                    "Add to calendar", lambda: choose("event")))
        card.add_widget(QuickAddOption("note-text-outline", "Start Noting",
                                    "Jot something down", lambda: choose("note")))
        card.add_widget(QuickAddOption("cart-outline", "Shopping List",
                                    "Track items and budget", lambda: choose("shopping")))

        modal.add_widget(card)

        # Card sizes itself to its content (adaptive_height), so the modal's
        # height is set to match it *after* that layout pass runs, instead
        # of guessing a fixed height that content can outgrow and spill past.
        card.bind(height=lambda _inst, value: setattr(modal, "height", value))
        modal.height = card.height

        modal.open()

    def route_quick_add(self, kind):
        if kind == "event":
            self.manager.current = "calendar"
            calendar_screen = self.manager.get_screen("calendar")
            Clock.schedule_once(
                lambda _dt: calendar_screen.open_add_task_popup(activity_type=kind), 0
            )
        elif kind == "study":
            self.open_study_session_popup()
        elif kind == "note":
            editor = self.manager.get_screen("note_editor")
            editor.current_note_id = None      # create new note
            self.manager.current = "note_editor"
        elif kind == "shopping":
            self.open_shopping_list()

    def open_shopping_list(self):
        """
        Quick Add > Shopping List. Reuses the user's existing
        "Shopping List" checklist if one exists, instead of creating a
        new duplicate every tap -- only creates one the first time.
        """
        user_id = getattr(MDApp.get_running_app(), "user_id", 1)

        existing = next(
            (c for c in get_all_checklists(user_id) if c["title"] == SHOPPING_LIST_TITLE),
            None,
        )
        if existing is not None:
            checklist_id = existing["id"]
        else:
            checklist_id = create_checklist(
                title=SHOPPING_LIST_TITLE, priority="", user_id=user_id
            )

        detail_screen = self.manager.get_screen("checklist_detail")
        detail_screen.checklist_id = checklist_id
        self.manager.current = "checklist_detail"


class QuickAddOption(ButtonBehavior, MDBoxLayout):
    """One row in the Quick Add sheet: icon + title + subtitle."""

    def __init__(self, icon, title, subtitle, on_press, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(64))
        kwargs.setdefault("spacing", dp(14))
        kwargs.setdefault("padding", [dp(4), dp(8), dp(4), dp(8)])
        super().__init__(**kwargs)
        self._on_press = on_press

        text_color = get_color_from_hex(theme_manager.get_color(TEXT_PRIMARY))
        sub_color = get_color_from_hex(theme_manager.get_color(TEXT_SECONDARY))
        chip_color = get_color_from_hex(theme_manager.get_color(CARD_SECONDARY))
        accent_color = get_color_from_hex(theme_manager.get_color(ACCENT))

        icon_card = MDCard(
            theme_bg_color="Custom", md_bg_color=chip_color,
            size_hint=(None, None), size=(dp(44), dp(44)),
            radius=[14], pos_hint={"center_y": 0.5},
        )
        icon_card.add_widget(MDIconButton(
            icon=icon, theme_icon_color="Custom", icon_color=accent_color,
            size_hint=(None, None), size=(dp(32), dp(32)),
            pos_hint={"center_x": 0.5, "center_y": 0.5},
        ))
        self.add_widget(icon_card)

        text_box = MDBoxLayout(orientation="vertical", spacing=dp(2))
        text_box.add_widget(MDLabel(
            text=title, font_style="Title", role="small",
            theme_text_color="Custom", text_color=text_color, adaptive_height=True,
        ))
        text_box.add_widget(MDLabel(
            text=subtitle, font_style="Body", role="small",
            theme_text_color="Custom", text_color=sub_color, adaptive_height=True,
        ))
        self.add_widget(text_box)
        
    def on_release(self):
        if self._on_press:
            self._on_press()
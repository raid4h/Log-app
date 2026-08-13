from theme.theme_manager import theme_manager

from kivymd.uix.dialog import (
    MDDialog,
    MDDialogHeadlineText,
    MDDialogContentContainer,
    MDDialogButtonContainer,
)
from kivymd.uix.textfield import MDTextField
from kivymd.uix.button import MDButton, MDButtonText

from kivy.clock import Clock
from kivy.app import App

from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout

from widgets.hourglass import HourglassWidget

from theme.themed_screen import ThemedScreenMixin
from theme.palettes import (
    BACKGROUND,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    BUTTON,
)


class PomodoroTimer:
    def __init__(self):
        self.work_duration = 25 * 60
        self.break_duration = 5 * 60

        self.remaining = self.work_duration

        self.is_running = False
        self.is_break = False

        self._event = None

        self.completed_focus_sessions = 0
        self.max_focus_sessions = 2
        self.cycle_finished = False

    def start(self):
        if not self.is_running:
            self.is_running = True

            if self._event is None:
                self._event = Clock.schedule_interval(
                    self.update_timer,
                    1,
                )

    def pause(self):
        self.is_running = False

    def reset(self):
        self.is_running = False
        self.cycle_finished = False
        self.completed_focus_sessions = 0

        if self.is_break:
            self.remaining = self.break_duration
        else:
            self.remaining = self.work_duration

    def start_new_cycle(self):
        self.completed_focus_sessions = 0
        self.cycle_finished = False
        self.is_break = False
        self.remaining = self.work_duration
        self.start()

    def set_work_duration(self, minutes, seconds):
        total_seconds = (minutes * 60) + seconds

        if total_seconds <= 0:
            return

        self.work_duration = total_seconds

        if not self.is_break:
            self.remaining = self.work_duration

    def set_break_duration(self, minutes, seconds):
        total_seconds = (minutes * 60) + seconds

        if total_seconds <= 0:
            return

        self.break_duration = total_seconds

        if self.is_break:
            self.remaining = self.break_duration

    def tick(self):
        if self.remaining > 0:
            self.remaining -= 1
        else:
            self.switch_session()

    def switch_session(self):
        if not self.is_break:
            self.completed_focus_sessions += 1

            if self.completed_focus_sessions >= self.max_focus_sessions:
                self.is_running = False
                self.cycle_finished = True
                self.remaining = self.work_duration
                return

        self.is_break = not self.is_break

        if self.is_break:
            self.remaining = self.break_duration
        else:
            self.remaining = self.work_duration

    def update_timer(self, dt):
        if self.is_running:
            self.tick()

    def get_time(self):
        minutes = self.remaining // 60
        seconds = self.remaining % 60
        return f"{minutes:02}:{seconds:02}"

    def get_session(self):
        return "Break Time" if self.is_break else "Focus Time"

    def get_total_for_current_session(self):
        return self.break_duration if self.is_break else self.work_duration

    def get_progress_fraction(self):
        total = self.get_total_for_current_session()

        if total <= 0:
            return 0.0

        elapsed = total - self.remaining

        return max(
            0.0,
            min(1.0, elapsed / total)
        )


class TimerScreen(ThemedScreenMixin, MDScreen):

    THEME_MAP = {
        "self": ("md_bg_color", BACKGROUND),

        "header_label": ("text_color", TEXT_PRIMARY),
        "subtitle_label": ("text_color", TEXT_SECONDARY),

        "back_button": ("icon_color", TEXT_PRIMARY),

        "timer_label": ("text_color", TEXT_PRIMARY),

        "session_label": ("text_color", TEXT_PRIMARY),
        "session_sub_label": ("text_color", TEXT_SECONDARY),
        "status_label": ("text_color", TEXT_SECONDARY),

        "reset_button": ("icon_color", TEXT_SECONDARY),
        "toggle_button": ("icon_color", BUTTON),
        "settings_button": ("icon_color", TEXT_SECONDARY),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.timer = PomodoroTimer()
        self.dialog = None

        # Remembers the mode from the previous refresh tick, so we can
        # detect the exact moment work/break flips (a "transition").
        self._last_is_break = self.timer.is_break
        self._last_cycle_finished = self.timer.cycle_finished
        self._status_clear_event = None

        Clock.schedule_interval(self.refresh_ui, 0.2)

    def refresh_ui(self, dt):
        self.ids.timer_label.text = self.timer.get_time()

        self.ids.session_label.text = self.timer.get_session()

        self._update_session_sub_label()

        if "hourglass" in self.ids:
            self.ids.hourglass.progress = self.timer.get_progress_fraction()

        self.ids.toggle_button.icon = (
            "pause"
            if self.timer.is_running
            else "play"
        )

        if self.timer.is_break != self._last_is_break:
            self._on_session_transitioned()
            self._last_is_break = self.timer.is_break

        if self.timer.cycle_finished and not self._last_cycle_finished:
            self._show_status_message(
                "Nice work! Start another session when you're ready.",
                duration=None,
            )
            self._last_cycle_finished = True

    def _update_session_sub_label(self):
        total_minutes = self.timer.get_total_for_current_session() // 60

        if self.timer.cycle_finished:
            self.ids.session_sub_label.text = "Cycle complete"
        elif self.timer.is_break:
            self.ids.session_sub_label.text = f"{total_minutes} minute break"
        else:
            current_session_number = self.timer.completed_focus_sessions + 1
            self.ids.session_sub_label.text = (
                f"{total_minutes} minute session \u00b7 "
                f"Session {current_session_number} of {self.timer.max_focus_sessions}"
            )

    def _on_session_transitioned(self):
        """
        Called once, right when the timer flips between work and break.
        Picks a short, friendly status message for the new mode.
        """
        if self.timer.is_break:
            message = "Study/Work session over."
        else:
            message = "Break time over. Time to start focusing again."

        self._show_status_message(message)

    def _show_status_message(self, message, duration=4):
        status_label = self.ids.get("status_label")
        if status_label is None:
            return

        status_label.text = message

        if self._status_clear_event is not None:
            self._status_clear_event.cancel()
            self._status_clear_event = None

        if duration is not None:
            self._status_clear_event = Clock.schedule_once(
                lambda dt: self._clear_status_message(), duration
            )

    def _clear_status_message(self):
        status_label = self.ids.get("status_label")
        if status_label is not None:
            status_label.text = ""
        self._status_clear_event = None

    def toggle_timer(self):
        if self.timer.cycle_finished:
            self.timer.start_new_cycle()
            self._last_cycle_finished = False
            self._clear_status_message()
            return

        if self.timer.is_running:
            self.pause_timer()
        else:
            self.start_timer()

    def start_timer(self):
        self.timer.start()

    def pause_timer(self):
        self.timer.pause()

    def reset_timer(self):
        self.timer.reset()
        self._last_cycle_finished = False
        self._clear_status_message()

    def go_back(self):
        App.get_running_app().root.current = "home"

    def on_theme_applied(self):
        hourglass = self.ids.get("hourglass")

        if hourglass is not None:
            hourglass.glass_color = theme_manager.get_color(TEXT_SECONDARY)
            hourglass.sand_color = theme_manager.get_color(BUTTON)

    # ── timer settings dialog ──

    def open_timer_dialog(self):

        if self.dialog is None:

            self.minutes_field = MDTextField(
                mode="outlined",
                size_hint_x=None,
                width="95dp",
                size_hint_y=None,
                height="48dp",
                hint_text="Mins",
            )

            self.seconds_field = MDTextField(
                mode="outlined",
                size_hint_x=None,
                width="95dp",
                size_hint_y=None,
                height="48dp",
                hint_text="Secs",
            )

            self.break_minutes_field = MDTextField(
                mode="outlined",
                size_hint_x=None,
                width="95dp",
                size_hint_y=None,
                height="48dp",
                hint_text="Mins",
            )

            self.break_seconds_field = MDTextField(
                mode="outlined",
                size_hint_x=None,
                width="95dp",
                size_hint_y=None,
                height="48dp",
                hint_text="Secs",
            )

            focus_row = MDBoxLayout(
                orientation="horizontal",
                adaptive_height=True,
                adaptive_width=True,
                spacing="16dp",
                pos_hint={"center_x": 0.5},
            )

            focus_row.add_widget(self.minutes_field)
            focus_row.add_widget(self.seconds_field)

            break_row = MDBoxLayout(
                orientation="horizontal",
                adaptive_height=True,
                adaptive_width=True,
                spacing="16dp",
                pos_hint={"center_x": 0.5},
            )

            break_row.add_widget(self.break_minutes_field)
            break_row.add_widget(self.break_seconds_field)

            self.dialog = MDDialog(

                MDDialogHeadlineText(
                    text="Pomodoro Settings"
                ),

                MDDialogContentContainer(

                    MDDialogHeadlineText(
                        text="Set Focus Time"
                    ),

                    focus_row,

                    MDDialogHeadlineText(
                        text="Set Break Time"
                    ),

                    break_row,

                    orientation="vertical",
                ),

                MDDialogButtonContainer(

                    MDButton(
                        MDButtonText(text="Cancel"),
                        on_release=lambda x: self.dialog.dismiss(),
                    ),

                    MDButton(
                        MDButtonText(text="Set"),
                        style="filled",
                        on_release=self.apply_timer,
                    ),
                ),
            )

        self.dialog.open()

    def apply_timer(self, *args):

        work_minutes = (
            int(self.minutes_field.text)
            if self.minutes_field.text.isdigit()
            else 0
        )

        work_seconds = (
            int(self.seconds_field.text)
            if self.seconds_field.text.isdigit()
            else 0
        )

        break_minutes = (
            int(self.break_minutes_field.text)
            if self.break_minutes_field.text.isdigit()
            else 0
        )

        break_seconds = (
            int(self.break_seconds_field.text)
            if self.break_seconds_field.text.isdigit()
            else 0
        )

        work_seconds = min(work_seconds, 59)
        break_seconds = min(break_seconds, 59)

        self.timer.set_work_duration(
            work_minutes,
            work_seconds,
        )

        self.timer.set_break_duration(
            break_minutes,
            break_seconds,
        )

        self.dialog.dismiss()
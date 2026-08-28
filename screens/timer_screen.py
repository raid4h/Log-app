from theme.theme_manager import theme_manager

from kivy.uix.popup import Popup
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.uix.behaviors import ButtonBehavior
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.utils import get_color_from_hex
from kivy.metrics import dp, sp

from kivymd.uix.card import MDCard
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.boxlayout import MDBoxLayout

from kivy.clock import Clock
from kivy.app import App

from kivymd.uix.screen import MDScreen

from widgets.hourglass import HourglassWidget

from theme.themed_screen import ThemedScreenMixin
from theme.palettes import (
    BACKGROUND,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    BUTTON,
    BUTTON_TEXT,
    CARD_PRIMARY,
    CARD_SECONDARY,
    BORDER,
    ACCENT,
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


class _UnitSegment(ButtonBehavior, MDBoxLayout):
    """
    One tappable "NN unit" segment inside a duration row (e.g. "25 min"
    or "00 sec"). Tapping it calls on_tap() -- the row decides what
    that means (select this unit for the -/+ buttons to adjust).
    Highlight is a soft background tint drawn directly via
    Color/RoundedRectangle, same technique CalendarDayCell already
    uses for its "today" highlight -- refreshed explicitly by the
    screen, not automatically, since selection state lives on the
    screen, not on this widget.
    """

    def __init__(self, value_text, unit_text, on_tap, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("spacing", dp(6))
        kwargs.setdefault("padding", [dp(8), dp(4)])
        kwargs.setdefault("size_hint_x", None)
        kwargs.setdefault("width", dp(92))
        super().__init__(**kwargs)
        self._on_tap = on_tap

        with self.canvas.before:
            self.highlight_color = Color(0, 0, 0, 0)
            self._highlight_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(12)])
        self.bind(pos=self._redraw, size=self._redraw)

        self.value_label = Label(
            text=value_text, font_size=sp(28), bold=True,
            size_hint_x=None, width=dp(48), halign="right", valign="middle",
        )
        self.value_label.bind(size=self.value_label.setter("text_size"))
        self.add_widget(self.value_label)

        self.unit_label = Label(
            text=unit_text, font_size=sp(12),
            size_hint_x=None, width=dp(34), halign="left", valign="middle",
        )
        self.unit_label.bind(size=self.unit_label.setter("text_size"))
        self.add_widget(self.unit_label)

    def _redraw(self, *_a):
        self._highlight_rect.pos = self.pos
        self._highlight_rect.size = self.size

    def on_release(self):
        if self._on_tap:
            self._on_tap()


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

    # ── timer settings popup ──
    #
    # Each duration row's minutes/seconds are independently tappable
    # via _UnitSegment -- tapping one selects it, and the -/+ buttons
    # then adjust ONLY whichever unit is currently selected. The
    # underlying value stays a single total_seconds integer -- divmod()
    # already correctly carries across the minute/second boundary in
    # either direction. apply_timer() is unchanged: it still calls
    # timer.set_work_duration(minutes, seconds).
    #
    # MIN_DURATION_SECONDS is only a floor against a literal
    # zero-length session (which would complete instantly) -- there is
    # deliberately NO "must be at least 1 minute" restriction, so
    # 0 min : a few sec is a valid duration. MAX_DURATION_SECONDS caps
    # the upper end only, per spec ("threshold on the upper value, not
    # the least value") -- 60 minutes + up to 59 extra seconds.

    MIN_DURATION_SECONDS = 1
    MAX_DURATION_SECONDS = (60 * 60) + 59

    def _clamp_duration(self, total_seconds):
        return max(self.MIN_DURATION_SECONDS, min(total_seconds, self.MAX_DURATION_SECONDS))

    def _sync_stepper_from_timer(self):
        self._work_total_seconds = self.timer.work_duration
        self._break_total_seconds = self.timer.break_duration
        self._work_unit_state["selected"] = "minutes"
        self._break_unit_state["selected"] = "minutes"
        self._update_work_labels()
        self._update_break_labels()
        self._refresh_unit_selection("work")
        self._refresh_unit_selection("break")

    def _update_work_labels(self):
        minutes, seconds = divmod(self._work_total_seconds, 60)
        self._work_minutes_segment.value_label.text = f"{minutes:02d}"
        self._work_seconds_segment.value_label.text = f"{seconds:02d}"

    def _update_break_labels(self):
        minutes, seconds = divmod(self._break_total_seconds, 60)
        self._break_minutes_segment.value_label.text = f"{minutes:02d}"
        self._break_seconds_segment.value_label.text = f"{seconds:02d}"

    def _select_unit(self, kind, unit_name):
        state = self._work_unit_state if kind == "work" else self._break_unit_state
        state["selected"] = unit_name
        self._refresh_unit_selection(kind)

    def _step_duration(self, kind, sign):
        if kind == "work":
            unit = self._work_unit_state["selected"]
            step = 60 if unit == "minutes" else 1
            self._work_total_seconds = self._clamp_duration(self._work_total_seconds + sign * step)
            self._update_work_labels()
        else:
            unit = self._break_unit_state["selected"]
            step = 60 if unit == "minutes" else 1
            self._break_total_seconds = self._clamp_duration(self._break_total_seconds + sign * step)
            self._update_break_labels()

    def _refresh_unit_selection(self, kind):
        if kind == "work":
            unit_state = self._work_unit_state
            minutes_segment = self._work_minutes_segment
            seconds_segment = self._work_seconds_segment
        else:
            unit_state = self._break_unit_state
            minutes_segment = self._break_minutes_segment
            seconds_segment = self._break_seconds_segment

        accent_rgba = get_color_from_hex(theme_manager.get_color(ACCENT))
        text_primary_rgba = get_color_from_hex(theme_manager.get_color(TEXT_PRIMARY))
        text_secondary_rgba = get_color_from_hex(theme_manager.get_color(TEXT_SECONDARY))

        for segment, unit_name in ((minutes_segment, "minutes"), (seconds_segment, "seconds")):
            is_selected = unit_state["selected"] == unit_name
            segment.highlight_color.rgba = (
                (accent_rgba[0], accent_rgba[1], accent_rgba[2], 0.28)
                if is_selected else (0, 0, 0, 0)
            )
            label_color = text_primary_rgba if is_selected else text_secondary_rgba
            segment.value_label.color = label_color
            segment.unit_label.color = label_color

    def _build_divider(self):
        divider = Widget(size_hint_y=None, height=dp(1))
        with divider.canvas:
            color_instr = Color(0, 0, 0, 0)
            rect = Rectangle(pos=divider.pos, size=divider.size)

        def _redraw(inst, *_a, _rect=rect):
            _rect.pos = inst.pos
            _rect.size = inst.size

        divider.bind(pos=_redraw, size=_redraw)
        self._popup_theme_refs.append(("divider", color_instr))
        return divider

    def _build_section_label(self, icon_name, text):
        row = MDBoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(24))

        icon = MDIconButton(
            icon=icon_name, theme_icon_color="Custom", disabled=True,
            size_hint=(None, None), size=(dp(20), dp(20)),
            pos_hint={"center_y": 0.5},
        )
        self._popup_theme_refs.append(("icon_accent", icon))
        row.add_widget(icon)

        label = Label(text=text, font_size=sp(12), bold=True, halign="left", valign="middle", size_hint_x=1)
        label.bind(size=label.setter("text_size"))
        self._popup_theme_refs.append(("label_secondary", label))
        row.add_widget(label)

        return row

    def _build_duration_row(self, kind):
        unit_state = {"selected": "minutes"}
        if kind == "work":
            self._work_unit_state = unit_state
        else:
            self._break_unit_state = unit_state

        row = MDCard(
            orientation="horizontal",
            theme_bg_color="Custom",
            padding=[dp(6), dp(6)],
            spacing=dp(4),
            radius=[18],
            elevation=0,
            size_hint_y=None,
            height=dp(64),
        )
        self._popup_theme_refs.append(("soft_bg", row))

        minus_btn = MDIconButton(icon="minus", theme_icon_color="Custom")
        minus_btn.bind(on_release=lambda *_a: self._step_duration(kind, -1))
        self._popup_theme_refs.append(("icon_muted", minus_btn))
        row.add_widget(minus_btn)

        center = MDBoxLayout(orientation="horizontal", spacing=dp(4), padding=[dp(4), 0])

        minutes_segment = _UnitSegment("00", "min", lambda: self._select_unit(kind, "minutes"))
        center.add_widget(minutes_segment)

        vdivider = Widget(size_hint_x=None, width=dp(1))
        with vdivider.canvas:
            vdivider_color = Color(0, 0, 0, 0)
            vdivider_rect = Rectangle()

        def _redraw_vdivider(inst, *_a, _rect=vdivider_rect):
            _rect.pos = (inst.center_x - dp(0.5), inst.y + dp(6))
            _rect.size = (dp(1), max(inst.height - dp(12), 0))

        vdivider.bind(pos=_redraw_vdivider, size=_redraw_vdivider)
        self._popup_theme_refs.append(("divider", vdivider_color))
        center.add_widget(vdivider)

        seconds_segment = _UnitSegment("00", "sec", lambda: self._select_unit(kind, "seconds"))
        center.add_widget(seconds_segment)

        row.add_widget(center)

        plus_btn = MDIconButton(icon="plus", theme_icon_color="Custom")
        plus_btn.bind(on_release=lambda *_a: self._step_duration(kind, 1))
        self._popup_theme_refs.append(("icon_muted", plus_btn))
        row.add_widget(plus_btn)

        if kind == "work":
            self._work_minutes_segment = minutes_segment
            self._work_seconds_segment = seconds_segment
        else:
            self._break_minutes_segment = minutes_segment
            self._break_seconds_segment = seconds_segment

        return row

    def _build_timer_settings_popup(self):
        self._popup_theme_refs = []

        panel = MDCard(
            orientation="vertical",
            theme_bg_color="Custom",
            padding=dp(20),
            spacing=dp(16),
            radius=[26],
            elevation=0,
        )
        self._popup_theme_refs.append(("panel_bg", panel))

        # -- header: icon circle + title + close button --
        header = MDBoxLayout(orientation="horizontal", spacing=dp(12), size_hint_y=None, height=dp(48))

        icon_circle = MDCard(
            theme_bg_color="Custom",
            size_hint=(None, None), size=(dp(48), dp(48)),
            radius=[24],
            pos_hint={"center_y": 0.5},
        )
        header_icon = MDIconButton(
            icon="timer-outline", theme_icon_color="Custom", disabled=True,
            size_hint=(None, None), size=(dp(30), dp(30)),
            pos_hint={"center_x": 0.5, "center_y": 0.5},
        )
        icon_circle.add_widget(header_icon)
        self._popup_theme_refs.append(("soft_bg", icon_circle))
        self._popup_theme_refs.append(("icon_accent", header_icon))
        header.add_widget(icon_circle)

        title_label = Label(
            text="Timer Settings", font_size=sp(19), bold=True,
            halign="left", valign="middle", size_hint_x=1,
        )
        title_label.bind(size=title_label.setter("text_size"))
        self._popup_theme_refs.append(("label_primary", title_label))
        header.add_widget(title_label)

        close_btn = MDIconButton(icon="close", theme_icon_color="Custom", pos_hint={"center_y": 0.5})
        close_btn.bind(on_release=lambda *_a: self.dialog.dismiss())
        self._popup_theme_refs.append(("icon_muted", close_btn))
        header.add_widget(close_btn)

        panel.add_widget(header)
        panel.add_widget(self._build_divider())

        # -- focus time --
        panel.add_widget(self._build_section_label("leaf", "FOCUS TIME"))
        panel.add_widget(self._build_duration_row("work"))

        # -- break time --
        panel.add_widget(self._build_section_label("coffee-outline", "BREAK TIME"))
        panel.add_widget(self._build_duration_row("break"))

        # -- cancel / save --
        actions = MDBoxLayout(orientation="horizontal", spacing=dp(12), size_hint_y=None, height=dp(52))

        self.dialog_cancel_text = MDButtonText(text="CANCEL", theme_text_color="Custom")
        cancel_btn = MDButton(
            self.dialog_cancel_text, style="outlined", theme_line_color="Custom",
            size_hint_x=1, height=dp(52), radius=[26],
            on_release=lambda *_a: self.dialog.dismiss(),
        )
        self._popup_theme_refs.append(("cancel_button", cancel_btn))
        self._popup_theme_refs.append(("cancel_button_text", self.dialog_cancel_text))
        actions.add_widget(cancel_btn)

        self.dialog_save_text = MDButtonText(text="SAVE", theme_text_color="Custom")
        save_btn = MDButton(
            self.dialog_save_text, style="filled", theme_bg_color="Custom",
            size_hint_x=1, height=dp(52), radius=[26],
            on_release=self.apply_timer,
        )
        self._popup_theme_refs.append(("save_button", save_btn))
        self._popup_theme_refs.append(("save_button_text", self.dialog_save_text))
        actions.add_widget(save_btn)

        panel.add_widget(actions)

        self.dialog = Popup(
            title="",
            content=panel,
            size_hint=(0.92, None),
            height=dp(500),
            auto_dismiss=False,
            separator_height=0,
            background="",
            background_color=(0, 0, 0, 0.5),
        )
        self.dialog.bind(on_dismiss=self._on_dialog_dismissed)

    def open_timer_dialog(self):
        if self.dialog is None:
            self._build_timer_settings_popup()

        self._sync_stepper_from_timer()
        self._apply_popup_theme()
        theme_manager.bind(theme_name=self._on_theme_name_changed)
        self.dialog.open()

    def _on_theme_name_changed(self, *args):
        self._apply_popup_theme()

    def _on_dialog_dismissed(self, *args):
        theme_manager.unbind(theme_name=self._on_theme_name_changed)

    def _apply_popup_theme(self, *args):
        if self.dialog is None:
            return

        surface = theme_manager.get_color(CARD_SECONDARY)
        soft_surface = theme_manager.get_color(CARD_PRIMARY)
        border = theme_manager.get_color(BORDER)
        accent = theme_manager.get_color(ACCENT)
        text_primary = theme_manager.get_color(TEXT_PRIMARY)
        text_secondary = theme_manager.get_color(TEXT_SECONDARY)
        button_color = theme_manager.get_color(BUTTON)
        button_text_color = theme_manager.get_color(BUTTON_TEXT)

        text_primary_rgba = get_color_from_hex(text_primary)
        text_secondary_rgba = get_color_from_hex(text_secondary)
        border_rgba = get_color_from_hex(border)

        for kind, ref in self._popup_theme_refs:
            if kind == "panel_bg":
                ref.md_bg_color = surface
            elif kind == "soft_bg":
                ref.md_bg_color = soft_surface
            elif kind == "icon_muted":
                ref.icon_color = text_secondary
            elif kind == "icon_accent":
                ref.icon_color = accent
            elif kind == "label_primary":
                ref.color = text_primary_rgba
            elif kind == "label_secondary":
                ref.color = text_secondary_rgba
            elif kind == "divider":
                ref.rgba = border_rgba
            elif kind == "save_button":
                ref.md_bg_color = button_color
            elif kind == "save_button_text":
                ref.text_color = button_text_color
            elif kind == "cancel_button":
                ref.line_color = border
            elif kind == "cancel_button_text":
                ref.text_color = text_primary

        self._refresh_unit_selection("work")
        self._refresh_unit_selection("break")

    def apply_timer(self, *args):
        work_minutes, work_seconds = divmod(self._work_total_seconds, 60)
        break_minutes, break_seconds = divmod(self._break_total_seconds, 60)

        self.timer.set_work_duration(work_minutes, work_seconds)
        self.timer.set_break_duration(break_minutes, break_seconds)

        self.dialog.dismiss()
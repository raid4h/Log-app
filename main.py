from kivy.config import Config
Config.set('graphics', 'multisamples', '0')
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.anchorlayout import MDAnchorLayout
from kivymd.uix.button import MDIconButton
from kivymd.uix.label import MDLabel
from kivymd.uix.card import MDCard
from kivy.metrics import dp
from screens.home_screen import HomeScreen
from screens.notes_screen import NotesScreen
from screens.note_editor_screen import NoteEditorScreen
from screens.settings_screen import SettingsScreen
from screens.timer_screen import TimerScreen
from screens.calendar_screen import CalendarScreen
from database.db import create_tables
from database.calendar_queries import create_calendar_events_table
from screens.recently_deleted_screen import RecentlyDeletedScreen
from theme.theme_manager import theme_manager
from kivy.core.window import Window
from screens.checklist_screen import ChecklistScreen
from screens.checklist_detail_screen import ChecklistDetailScreen
from screens.privacy_settings_screen import PrivacySettingsScreen
from screens.terms_screen import TermsScreen
from screens.privacy_policy_screen import PrivacyPolicyScreen
from services.notification_service import collect_due_notifications, send_system_notification
from kivy.clock import Clock
from kivy.utils import platform

from legal_content import TERMS_VERSION
from services.legal_store import has_agreed_to_version

from theme.palettes import CARD_PRIMARY, TEXT_PRIMARY, TEXT_SECONDARY

# Left at the default ('') deliberately. 'below_target' (tried
# previously) pans the window once when a field GAINS focus, but
# doesn't keep re-adjusting as the cursor moves further down inside a
# field that's already focused -- exactly the case that matters here
# (typing continuously down a long note). That fought with
# note_editor_screen.py's own ScrollView-based keyboard-avoidance
# (which reads the REAL keyboard height via pyjnius, since
# Window.keyboard_height always returns 0 with SDL2 on Android)
# instead of cooperating with it. With this left at '', the app's own
# scroll logic is the only thing moving content -- nothing left to
# conflict with it.
Window.softinput_mode = ''


def _request_android_notification_permission():
    """
    buildozer.spec declaring POST_NOTIFICATIONS in android.permissions
    only adds it to the manifest -- on Android 13+ (API 33+) it's a
    "dangerous" runtime permission, same category as camera or
    location, and the app has to explicitly ask the user to grant it
    or it stays denied forever. Without this, plyer's
    notification.notify() (see services/notification_service.py)
    raises internally on every call, which send_system_notification's
    broad except swallows silently -- so reminders would just never
    appear, on any Android 13+ device, with no visible error anywhere.

    Guarded behind platform == "android" since the `android.permissions`
    module doesn't exist on desktop and would break `python main.py`
    during normal dev/testing on Windows otherwise. The inner
    try/except is defensive for older Android builds where the
    Permission.POST_NOTIFICATIONS constant may not exist (added
    alongside the API 33 runtime-permission requirement itself).
    """
    if platform != "android":
        return
    try:
        from android.permissions import (
            request_permissions,
            check_permission,
            Permission,
        )
        if not check_permission(Permission.POST_NOTIFICATIONS):
            request_permissions([Permission.POST_NOTIFICATIONS])
    except Exception:
        pass


class RootLayout(MDBoxLayout):
    """Wraps the ScreenManager + bottom nav bar. Proxies .get_screen()
    and .current to the real ScreenManager so any existing code that
    calls app.root.get_screen(...) or app.root.current keeps working
    unchanged, even though app.root is no longer the ScreenManager
    itself."""

    def get_screen(self, name):
        return self.sm.get_screen(name)

    @property
    def current(self):
        return self.sm.current

    @current.setter
    def current(self, value):
        self.sm.current = value


class LogApp(MDApp):
    def build(self):
        _request_android_notification_permission()
        create_tables()
        create_calendar_events_table()
        # Must run after create_tables() (so the database file
        # already exists) and before any screen is built -- screens
        # apply their theme the moment they're created below, so the
        # correct theme_name needs to already be set first.

        theme_manager.load_saved_theme()

        self.title = "Log"
        Builder.load_file("home_screen.kv")  # Tabshira: DashboardTile, SmallTile, HomeScreen
        Builder.load_file("notes.kv")  # Raidah: NoteCard, AttachmentThumbnail, NotesScreen, NoteEditorScreen, FormattingToolbar, RecentlyDeletedScreen
        Builder.load_file("settings_screen.kv")
        Builder.load_file("timer_screen.kv")
        Builder.load_file("calendar_screen.kv")
        Builder.load_file("checklist_screen.kv")
        Builder.load_file("checklist_detail_screen.kv")
        Builder.load_file("privacy_settings_screen.kv")
        Builder.load_file("terms_screen.kv")
        Builder.load_file("privacy_policy_screen.kv")

        self.sm = ScreenManager()
        self.sm.add_widget(HomeScreen(name="home"))
        self.sm.add_widget(NotesScreen(name="notes"))
        self.sm.add_widget(NoteEditorScreen(name="note_editor"))
        self.sm.add_widget(RecentlyDeletedScreen(name="recently_deleted"))
        self.sm.add_widget(SettingsScreen(name="settings"))
        self.sm.add_widget(TimerScreen(name="timer"))
        self.sm.add_widget(CalendarScreen(name="calendar"))
        self.sm.add_widget(ChecklistScreen(name="checklist"))
        self.sm.add_widget(ChecklistDetailScreen(name="checklist_detail"))
        self.sm.add_widget(PrivacySettingsScreen(name="privacy_settings"))
        self.sm.add_widget(TermsScreen(name="terms"))
        self.sm.add_widget(PrivacyPolicyScreen(name="privacy_policy"))

        # Gate: only go straight to "home" if the user has already
        # agreed to the CURRENT version of the terms. Otherwise --
        # first-ever launch, or an existing install after
        # legal_content.TERMS_VERSION was bumped -- land on "terms"
        # instead. TermsScreen.agree() is the only path that sets
        # sm.current to "home" from there, and there's no back button
        # on that screen, so this is a hard gate, not just a default
        # starting tab.
        if has_agreed_to_version(TERMS_VERSION):
            self.sm.current = "home"
        else:
            self.sm.current = "terms"

        root = RootLayout(orientation="vertical")
        root.sm = self.sm
        root.add_widget(self.sm)
        self.nav_bar = self.build_bottom_nav()
        root.add_widget(self.nav_bar)

        # The bottom nav bar sits OUTSIDE the ScreenManager (it's a
        # sibling in RootLayout, always on screen regardless of which
        # screen is current) -- so without this, a user on "terms"
        # could just tap Home/Calendar/Notes/Timer and bypass the
        # agreement gate entirely, never having agreed to anything.
        # Binding to sm.current keeps the nav bar's visibility in sync
        # with whatever screen is actually showing, closing that gap.
        self.sm.bind(current=self._on_screen_changed)
        self._update_nav_visibility(self.sm.current)
        Clock.schedule_interval(self._check_notifications, 30)

        # Shared back-navigation stack. Every screen that navigates
        # forward should call app.go_to_screen(name) instead of
        # setting app.root.current directly, so this stays accurate.
        # Both the hardware back key and any in-app back button
        # should call app.go_back() so behavior stays consistent.
        self.screen_history = []
        Window.bind(on_keyboard=self.on_key)

        return root

    def go_to_screen(self, screen_name):
        """Navigate forward and remember where we came from.
        Use this instead of app.root.current = 'x' anywhere the app
        navigates to a new screen."""
        current = self.root.current
        if current != screen_name:
            self.screen_history.append(current)
            self.root.current = screen_name

    def go_back(self):
        """Pop the last screen off the stack and go there. Returns
        True if it navigated, False if the stack was empty (caller
        can then decide to exit the app)."""
        if self.screen_history:
            self.root.current = self.screen_history.pop()
            return True
        return False

    def on_key(self, window, key, *args):
        """Intercepts the hardware/gesture back button. Returning
        True consumes the event so Android doesn't fall through to
        its default (which otherwise backgrounds/exits the app)."""
        if key == 27:  # Android back
            return self.go_back()
        return False

    def _on_screen_changed(self, instance, value):
        self._update_nav_visibility(value)
        if hasattr(self.nav_bar, "update_active_item"):
            self.nav_bar.update_active_item(value)

    def _update_nav_visibility(self, screen_name):
        is_gated_screen = screen_name == "terms"
        # height=0 removes it from layout (so the ScreenManager above
        # it expands to fill the freed space, rather than leaving a
        # blank bar-shaped gap); disabled=True additionally blocks
        # any touch from reaching the icon buttons underneath, since a
        # zero-height widget with children can still technically be
        # hit in some edge cases -- belt and suspenders for something
        # this important. opacity=0 is redundant with height=0 here
        # but kept for a clean instant fade if this is ever animated
        # later.
        if is_gated_screen:
            self.nav_bar.height = 0
            self.nav_bar.opacity = 0
            self.nav_bar.disabled = True
        else:
            self.nav_bar.height = dp(76)
            self.nav_bar.opacity = 1
            self.nav_bar.disabled = False

    def build_bottom_nav(self):
        nav = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(76),
            padding=(dp(10), dp(7), dp(10), dp(6)),
            spacing=dp(6),
            theme_bg_color="Custom",
            md_bg_color=theme_manager.get_color(CARD_PRIMARY),
        )

        nav_items = []

        def make_nav_button(icon, label, screen_name):
            # ---------------------------------------------------------
            # Individual navigation item
            # ---------------------------------------------------------
            item = MDBoxLayout(
                orientation="vertical",
                size_hint_x=1,
                spacing=dp(1),
                padding=(dp(2), 0, dp(2), 0),
            )

            # ---------------------------------------------------------
            # Icon
            # ---------------------------------------------------------
            icon_box = MDAnchorLayout(
                size_hint_y=None,
                height=dp(40),
                anchor_x="center",
                anchor_y="center",
            )

            btn = MDIconButton(
                icon=icon,
                theme_icon_color="Custom",
                icon_color=theme_manager.get_color(TEXT_PRIMARY),
                size_hint=(None, None),
                size=(dp(44), dp(40)),
                # FIX: was setattr(self.sm, "current", screen_name),
                # which set sm.current directly and never touched
                # self.screen_history. That's why Back from a screen
                # reached via the bottom nav had an empty stack and
                # fell through to Android's default exit-app behavior.
                # go_to_screen() pushes the outgoing screen first, so
                # go_back() / the hardware back key can pop it later.
                on_release=lambda x, s=screen_name: self.go_to_screen(s),
            )

            icon_box.add_widget(btn)

            # ---------------------------------------------------------
            # Label
            # ---------------------------------------------------------
            text = MDLabel(
                text=label,
                halign="center",
                valign="middle",
                font_style="Label",
                role="small",
                bold=False,
                theme_text_color="Custom",
                text_color=theme_manager.get_color(TEXT_PRIMARY),
                size_hint_y=None,
                height=dp(18),
            )

            # ---------------------------------------------------------
            # Active indicator
            # ---------------------------------------------------------
            indicator = MDCard(
                size_hint=(None, None),
                size=(dp(28), dp(3)),
                pos_hint={"center_x": 0.5},
                radius=[dp(2)],
                elevation=0,
                theme_bg_color="Custom",
                md_bg_color=theme_manager.get_color(TEXT_PRIMARY),
                opacity=0,
            )

            indicator_box = MDAnchorLayout(
                size_hint_y=None,
                height=dp(4),
                anchor_x="center",
                anchor_y="center",
            )

            indicator_box.add_widget(indicator)

            item.add_widget(icon_box)
            item.add_widget(text)
            item.add_widget(indicator_box)

            nav_items.append({
                "screen": screen_name,
                "button": btn,
                "label": text,
                "indicator": indicator,
            })

            return item

        nav.add_widget(
            make_nav_button(
                "home-outline",
                "Home",
                "home"
            )
        )

        nav.add_widget(
            make_nav_button(
                "calendar-outline",
                "Calendar",
                "calendar"
            )
        )

        nav.add_widget(
            make_nav_button(
                "notebook-outline",
                "Notes",
                "notes"
            )
        )

        nav.add_widget(
            make_nav_button(
                "timer-sand",
                "Timer",
                "timer"
            )
        )

        # -------------------------------------------------------------
        # Update selected navigation item
        # -------------------------------------------------------------
        def update_active_item(screen_name):
            # Clear visual hierarchy: the selected destination uses the
            # primary text color, while the rest remain intentionally muted.
            active_color = theme_manager.get_color(TEXT_PRIMARY)
            inactive_color = theme_manager.get_color(TEXT_SECONDARY)

            for item in nav_items:
                is_active = item["screen"] == screen_name

                if is_active:
                    item["button"].icon_color = active_color
                    item["label"].text_color = active_color
                    item["label"].bold = True
                    item["indicator"].md_bg_color = active_color
                    item["indicator"].opacity = 1
                else:
                    item["button"].icon_color = inactive_color
                    item["label"].text_color = inactive_color
                    item["label"].bold = False
                    item["indicator"].opacity = 0

        # Store this so _on_screen_changed can use it.
        nav.update_active_item = update_active_item

        # Apply the initial state.
        update_active_item(self.sm.current)

        # -------------------------------------------------------------
        # Theme updates
        # -------------------------------------------------------------
        def refresh_nav_theme(*_args):
            nav.md_bg_color = theme_manager.get_color(CARD_PRIMARY)

            update_active_item(self.sm.current)

        theme_manager.bind(theme_name=refresh_nav_theme)

        return nav

    def _check_notifications(self, dt):
        user_id = getattr(self, "user_id", 1)
        for note in collect_due_notifications(user_id=user_id):
            send_system_notification(note["title"], self._notification_message(note))

    def _notification_message(self, note):
        if note.get("due_time"):
            return f'At {note["due_time"]}'
        if note.get("due_date"):
            return f'Due {note["due_date"]}'
        return "Reminder"


if __name__ == "__main__":
    LogApp().run()
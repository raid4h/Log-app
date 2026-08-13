from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.anchorlayout import MDAnchorLayout
from kivymd.uix.button import MDIconButton
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

from legal_content import TERMS_VERSION
from services.legal_store import has_agreed_to_version

from theme.palettes import CARD_PRIMARY, TEXT_PRIMARY

# Tells Kivy to automatically resize the app's visible area so whatever
# text field currently has focus stays visible above the on-screen
# keyboard, instead of the keyboard covering it. Does nothing on
# desktop (there's no real on-screen keyboard here to trigger it) --
# this only takes effect once running on an actual Android device or
# emulator.
Window.softinput_mode = "below_target"


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


class NoteNestApp(MDApp):
    def build(self):
        create_tables()
        create_calendar_events_table()
        # Must run after create_tables() (so the database file
        # already exists) and before any screen is built -- screens
        # apply their theme the moment they're created below, so the
        # correct theme_name needs to already be set first.

        theme_manager.load_saved_theme()

        self.title = "NoteNest"
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

        return root

    def _on_screen_changed(self, instance, value):
        self._update_nav_visibility(value)

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
            self.nav_bar.height = dp(64)
            self.nav_bar.opacity = 1
            self.nav_bar.disabled = False

    def build_bottom_nav(self):
        nav = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(64),
            padding=dp(8),
            spacing=dp(4),
            theme_bg_color="Custom",
            md_bg_color=theme_manager.get_color(CARD_PRIMARY),
        )

        icon_buttons = []

        def make_nav_button(icon, screen_name):
            wrapper = MDAnchorLayout(size_hint_x=1, anchor_x="center", anchor_y="center")
            btn = MDIconButton(
                icon=icon,
                theme_icon_color="Custom",
                icon_color=theme_manager.get_color(TEXT_PRIMARY),
                on_release=lambda x: setattr(self.sm, "current", screen_name),
            )
            icon_buttons.append(btn)
            wrapper.add_widget(btn)
            return wrapper

        nav.add_widget(make_nav_button("home-outline", "home"))
        nav.add_widget(make_nav_button("calendar-outline", "calendar"))
        nav.add_widget(make_nav_button("notebook-outline", "notes"))
        nav.add_widget(make_nav_button("timer-sand", "timer"))

        def refresh_nav_theme(*_args):
            nav.md_bg_color = theme_manager.get_color(CARD_PRIMARY)
            for btn in icon_buttons:
                btn.icon_color = theme_manager.get_color(TEXT_PRIMARY)

        theme_manager.bind(theme_name=refresh_nav_theme)

        return nav


if __name__ == "__main__":
    NoteNestApp().run()
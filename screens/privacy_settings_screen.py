# screens/privacy_settings_screen.py
#
# Settings > Privacy. Shows the app's own actual runtime permission
# state (via services/permissions_service.py) -- what Log can
# currently access on this device, and why each permission exists.
# Purely local: no network calls, nothing sent anywhere.
#
# On Android: a "denied" permission shows an "Allow" button that
# triggers the OS's own request dialog. If the user has permanently
# denied it ("don't ask again"), that dialog won't reappear -- the
# "Open App Settings" button at the bottom is the fallback for that
# case, deep-linking to the OS's own App Info screen for NoteNest.
#
# On desktop: every permission reports as "not_applicable" (see
# permissions_service.py) -- shown as an informational note instead
# of a broken/empty permissions list.

from kivy.clock import Clock
from kivymd.uix.screen import MDScreen
from kivymd.uix.label import MDLabel
from kivymd.uix.card import MDCard
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.metrics import dp

from theme.theme_manager import theme_manager
from theme.themed_screen import ThemedScreenMixin
from theme.palettes import (
    BACKGROUND,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    CARD_PRIMARY,
    ACCENT,
    BORDER,
)

from services.permissions_service import (
    get_permission_statuses,
    request_permission,
    open_app_settings,
    is_android,
)


STATUS_DISPLAY = {
    "granted": ("Allowed", "#7FB77E"),
    "denied": ("Not allowed", "#E0A96D"),
    "not_applicable": ("Not applicable", "#9A9A9A"),
}

# Cap for the width-not-resolved-yet retry loop in _schedule_load.
# At 60 frames (roughly 1 second at 60fps) this is generous -- if the
# layout genuinely hasn't resolved a real width by then, something
# else is wrong and retrying forever just leaves a permanently blank
# screen with no visible signal. Load anyway past this point rather
# than loop silently -- cards may render a frame or two narrower than
# ideal, which is a far smaller problem than never rendering at all.
_MAX_WIDTH_RETRIES = 60


class PrivacySettingsScreen(ThemedScreenMixin, MDScreen):

    THEME_MAP = {
        "self":              ("md_bg_color", BACKGROUND),
        "back_button":       ("icon_color", TEXT_PRIMARY),
        "header_label":      ("text_color", TEXT_PRIMARY),
        "subtitle_label":    ("text_color", TEXT_SECONDARY),
        "desktop_note_label": ("text_color", TEXT_SECONDARY),
    }

    def on_enter(self, *args):
        # Fires after the screen transition has actually finished and
        # the screen is on-display -- unlike on_pre_enter, which fires
        # *before* the transition even starts. That distinction
        # matters here: permission_list's parent layout may not have
        # resolved a real width until the transition completes.
        # Building the MDCards while width is still 0 makes KivyMD's
        # ripple effect try to allocate a 0-sized FBO texture ->
        # "FBO Initialization failed: Incomplete attachment (36054)"
        # on some Android GPUs.
        #
        # on_enter alone isn't a hard guarantee either (custom
        # transitions, first-ever layout pass, etc. can still leave
        # width at 0 for a frame or two), so this also retries once
        # per frame until permission_list actually has a real width
        # -- capped at _MAX_WIDTH_RETRIES so a layout that never
        # resolves doesn't leave the screen silently blank forever.
        self._width_retry_count = 0
        self._schedule_load()

    def _schedule_load(self, *args):
        permission_list = self.ids.permission_list
        if permission_list.width <= 0 and self._width_retry_count < _MAX_WIDTH_RETRIES:
            self._width_retry_count += 1
            Clock.schedule_once(self._schedule_load, 0)
            return
        self.load_permissions()

    def go_back(self):
        App.get_running_app().root.current = "settings"

    def _show_snackbar(self, message):
        MDSnackbar(
            MDSnackbarText(text=message),
            y="24dp",
            pos_hint={"center_x": 0.5},
            size_hint_x=0.9,
        ).open()

    # ── loading the permission list ──

    def load_permissions(self):
        try:
            self.ids.permission_list.clear_widgets()

            if not is_android():
                self.ids.desktop_note_label.text = (
                    "Permissions only apply when NoteNest is running on an "
                    "Android device -- there's nothing to manage here on "
                    "desktop."
                )
                self.ids.desktop_note_label.height = dp(40)
            else:
                self.ids.desktop_note_label.text = ""
                self.ids.desktop_note_label.height = 0

            statuses = get_permission_statuses()
            for permission in statuses:
                try:
                    self.ids.permission_list.add_widget(
                        self._build_permission_card(permission)
                    )
                except Exception as exc:
                    # One malformed/unexpected permission entry
                    # shouldn't blank out every other card -- skip it
                    # and keep going, instead of the whole list dying
                    # partway through (which previously looked
                    # identical to nothing loading at all).
                    print(f"[privacy_settings] failed to build card for "
                          f"{permission.get('key')}: {exc}")
        except Exception as exc:
            # If something upstream of the per-card loop fails (e.g.
            # get_permission_statuses() itself), show that clearly
            # instead of leaving a blank list with only the static
            # "Open App Settings" button visible and no explanation.
            print(f"[privacy_settings] load_permissions failed: {exc}")
            self._show_snackbar(f"Couldn't load permissions: {exc}")

    def _build_permission_card(self, permission):
        card = MDCard(
            orientation="vertical",
            theme_bg_color="Custom",
            md_bg_color=theme_manager.get_color(CARD_PRIMARY),
            padding=dp(14),
            spacing=dp(8),
            adaptive_height=True,
            radius=[14],
        )

        top_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(26), spacing=dp(8))

        label = MDLabel(
            text=permission["label"],
            theme_text_color="Custom",
            text_color=theme_manager.get_color(TEXT_PRIMARY),
            font_style="Title",
            role="small",
            size_hint_x=1,
        )
        top_row.add_widget(label)

        status_text, status_hex = STATUS_DISPLAY[permission["status"]]
        status_label = MDLabel(
            text=status_text,
            theme_text_color="Custom",
            text_color=status_hex,
            font_style="Label",
            role="medium",
            halign="right",
            size_hint_x=None,
            width=dp(110),
        )
        top_row.add_widget(status_label)

        card.add_widget(top_row)

        description = MDLabel(
            text=permission["description"],
            theme_text_color="Custom",
            text_color=theme_manager.get_color(TEXT_SECONDARY),
            font_style="Body",
            role="small",
            adaptive_height=True,
        )
        card.add_widget(description)

        if permission["status"] == "denied":
            allow_btn = MDButton(style="tonal", size_hint_y=None, height=dp(38))
            allow_btn.add_widget(MDButtonText(text="Allow"))
            allow_btn.bind(
                on_release=lambda *_a, key=permission["key"]: self._request(key)
            )
            card.add_widget(allow_btn)

        return card

    def _request(self, key):
        def on_result(granted):
            # Comes back on Android's own callback thread/timing --
            # reloading here just re-reads the now-current state
            # rather than trying to guess and flip one row in place.
            self.load_permissions()

        request_permission(key, on_result=on_result)

    def open_app_settings_page(self):
        # Previously an unguarded call -- any exception inside
        # open_app_settings() (a bad autoclass lookup, a pyjnius
        # signature mismatch, anything) crashed the whole app with no
        # visible cause. Catching it here means the very next tap
        # either works, or shows you the real error text instead of a
        # crash -- either outcome tells us what to do next.
        try:
            open_app_settings()
        except Exception as exc:
            print(f"[privacy_settings] open_app_settings failed: {exc}")
            self._show_snackbar(f"Couldn't open settings: {exc}")
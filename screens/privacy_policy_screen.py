# screens/privacy_policy_screen.py
#
# Read-only Privacy Policy view, reachable from Settings > About at
# any time -- unlike screens/terms_screen.py, this one has a normal
# back button and no agreement gate, since the user has already
# agreed once (via TermsScreen) to get into the app at all. This
# screen exists purely so they can re-read the policy later.

from kivy.app import App
from kivymd.uix.screen import MDScreen

from theme.themed_screen import ThemedScreenMixin
from theme.palettes import BACKGROUND, TEXT_PRIMARY, TEXT_SECONDARY

from legal_content import PRIVACY_POLICY_TEXT


class PrivacyPolicyScreen(ThemedScreenMixin, MDScreen):

    THEME_MAP = {
        "self":            ("md_bg_color", BACKGROUND),
        "back_button":     ("icon_color", TEXT_PRIMARY),
        "header_label":    ("text_color", TEXT_PRIMARY),
        "subtitle_label":  ("text_color", TEXT_SECONDARY),
        "policy_label":    ("text_color", TEXT_PRIMARY),
    }

    def on_pre_enter(self, *args):
        self.ids.policy_label.text = PRIVACY_POLICY_TEXT

    def go_back(self):
        App.get_running_app().root.current = "settings"
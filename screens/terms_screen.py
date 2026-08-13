# screens/terms_screen.py
#
# The Terms & Conditions agreement gate. Shown by main.py on first
# launch (or again if legal_content.TERMS_VERSION is ever bumped,
# meaning the user's previous agreement no longer covers the current
# terms). Not reachable from anywhere else in the app's normal
# navigation -- there's no back button here on purpose.
#
# "I Agree" stays disabled until the checkbox is checked, and tapping
# it records the agreement (services/legal_store.py) before moving on
# to home. "Decline" asks for confirmation, then closes the app
# entirely -- since we can't legally let someone use the app without
# agreeing, the only other option besides agreeing is not using it.

import sys

from kivy.app import App
from kivy.utils import platform
from kivymd.uix.screen import MDScreen
from kivymd.uix.dialog import (
    MDDialog,
    MDDialogHeadlineText,
    MDDialogSupportingText,
    MDDialogButtonContainer,
)
from kivymd.uix.button import MDButton, MDButtonText

from theme.theme_manager import theme_manager
from theme.themed_screen import ThemedScreenMixin
from theme.palettes import BACKGROUND, TEXT_PRIMARY, TEXT_SECONDARY, ACCENT

from legal_content import TERMS_TEXT, TERMS_VERSION
from services.legal_store import record_agreement


class TermsScreen(ThemedScreenMixin, MDScreen):

    THEME_MAP = {
        "self":            ("md_bg_color", BACKGROUND),
        "header_label":    ("text_color", TEXT_PRIMARY),
        "subtitle_label":  ("text_color", TEXT_SECONDARY),
        "terms_label":     ("text_color", TEXT_PRIMARY),
        "agree_checkbox":  ("color_active", ACCENT),
        "checkbox_label":  ("text_color", TEXT_PRIMARY),
    }

    def on_pre_enter(self, *args):
        self.ids.terms_label.text = TERMS_TEXT
        self.ids.agree_checkbox.active = False

    def on_checkbox_toggled(self, active):
        self.ids.agree_button.disabled = not active

    def agree(self):
        if not self.ids.agree_checkbox.active:
            return
        record_agreement(TERMS_VERSION)
        App.get_running_app().root.current = "home"

    def decline(self):
        dialog = MDDialog(
            MDDialogHeadlineText(text="Decline Terms?"),
            MDDialogSupportingText(
                text=(
                    "NoteNest can't be used without agreeing to the "
                    "Terms & Conditions. Declining will close the app."
                )
            ),
            MDDialogButtonContainer(
                MDButton(
                    MDButtonText(text="Cancel"),
                    on_release=lambda x: dialog.dismiss(),
                ),
                MDButton(
                    MDButtonText(text="Close App"),
                    style="filled",
                    on_release=lambda x: self._close_app(dialog),
                ),
            ),
        )
        dialog.open()

    def _close_app(self, dialog):
        dialog.dismiss()
        App.get_running_app().stop()
        if platform == "android":
            # App.stop() alone doesn't reliably kill the process on
            # Android -- the activity can linger. os._exit forces the
            # process to actually end, same as the user backing out
            # of the app entirely.
            import os
            os._exit(0)
        else:
            sys.exit(0)
# screens/terms_screen.py
#
# The Terms & Conditions agreement gate. Shown by main.py on first
# launch (or again if legal_content.TERMS_VERSION is ever bumped,
# meaning the user's previous agreement no longer covers the current
# terms). Not reachable from anywhere else in the app's normal
# navigation -- there's no back button here on purpose.
#
# "I Agree" is dimmed (not disabled) until the checkbox is checked,
# and tapping it records the agreement (services/legal_store.py)
# before moving on to home. "Decline" asks for confirmation, then
# closes the app entirely -- since we can't legally let someone use
# the app without agreeing, the only other option besides agreeing is
# not using it.
#
# NOTE 1: agree_button is intentionally never given disabled=True/False
# after its initial kv state. Toggling KivyMD's MDButton.disabled off
# and back on (which the checkbox used to drive) was causing the
# button to silently swallow the first tap or several after being
# re-enabled -- a known class of Kivy/KivyMD ripple/touch-state bug.
# Since agree() already guards on agree_checkbox.active itself, the
# disabled toggle was redundant for correctness and only served the
# visual "grayed out" look -- which is now done with opacity in the
# .kv instead, so the button's touch handling is never disturbed.
#
# NOTE 2: bottom padding for the nav bar inset uses
# apply_bottom_inset_padding() (retries for ~0.5s) rather than a
# single get_bottom_inset() read -- see theme/safe_area.py. Fixes a
# device (Xiaomi/MIUI) where the single-read version returned 0
# because insets weren't dispatched yet at on_kv_post time, leaving
# "I Agree" partially covered by the system nav bar.

import sys

from kivy.app import App
from kivy.utils import platform
from kivy.metrics import dp
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
from theme.safe_area import apply_bottom_inset_padding

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

    def on_kv_post(self, base_widget):
        super().on_kv_post(base_widget)
        # Pads the bottom of the whole screen by the real system
        # gesture-nav-bar height, on top of the normal dp(20) design
        # padding -- so Decline/I Agree always sit fully above the
        # gesture zone instead of underneath it. Retries internally
        # rather than reading once -- see theme/safe_area.py.
        apply_bottom_inset_padding(self.ids.root_layout)

    def on_pre_enter(self, *args):
        self.ids.terms_label.text = TERMS_TEXT
        self.ids.agree_checkbox.active = False

    def on_checkbox_toggled(self, active):
        # Kept as a hook (e.g. for future haptics/analytics) but no
        # longer touches agree_button.disabled -- see NOTE 1 above.
        # Visual dimming is handled declaratively in the .kv via
        # agree_button's opacity binding to agree_checkbox.active.
        pass

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
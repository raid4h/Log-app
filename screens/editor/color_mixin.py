# screens/editor/color_mixin.py
# Text color: selecting text and choosing a color wraps the selection
# in a {{color:#RRGGBB}}...{{/color}} marker pair. Real foreground
# text color, chosen from a palette/hex picker -- replaces the old
# ==highlight== feature, which was a color-based approximation of a
# background highlight and has since been removed. Mirrors
# HyperlinkMixin's select-whole-marker-to-edit pattern rather than
# FormattingMixin's _wrap_selection, since color's open/close markers
# aren't symmetric the way **/__ are.

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.modalview import ModalView
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.textfield import MDTextField, MDTextFieldHintText

from screens.editor.markup import COLOR_TOKEN_PATTERN
from screens.safe_card import make_safe_card
from user_prefs import get_pref, set_pref

# Fixed starting palette shown above "recently used" -- deliberately
# small and high-contrast against the app's parchment/cream theme.
PALETTE_COLORS = [
    "#5B3A29",  # dark brown, close to the app's own TEXT_PRIMARY
    "#B8860B",  # matches the highlight approximation, for visual familiarity
    "#B03A2E",  # red
    "#1F618D",  # blue
    "#1E8449",  # green
    "#6C3483",  # purple
    "#D68910",  # orange
    "#000000",  # black
]

MAX_RECENT_COLORS = 6


class TextColorMixin:
    """Requires: self.ids.content_field, self._last_selection,
    self._pending_color_selection, self._active_color_modal
    (both set in __init__)."""

    def make_text_color(self):
        field = self.ids.content_field
        self._pending_color_selection = None
        current_hex = None

        if self._last_selection:
            selected, start, end = self._last_selection
            if field.text[start:end] == selected:
                match = COLOR_TOKEN_PATTERN.fullmatch(selected)
                if match:
                    # The ENTIRE selection is one existing colored
                    # span -- edit it in place, same idea as editing
                    # an existing link.
                    current_hex = match.group(1)
                    self._pending_color_selection = ("edit", selected, start, end)
                else:
                    self._pending_color_selection = ("wrap", selected, start, end)

        self._show_color_picker_popup(current_hex)

    def _convert_colors_to_markup(self, text):
        # Runs on already-escaped text, same as _convert_links_to_markup
        # -- {{ and }} aren't escape_markup-sensitive, so this is safe
        # to do after escaping just like links are.
        return COLOR_TOKEN_PATTERN.sub(
            lambda m: f"[color={m.group(1)}]{m.group(2)}[/color]", text
        )    

    def _show_color_picker_popup(self, current_hex):
        recent = get_pref("recent_text_colors") or []

        card = make_safe_card(MDCard,
            orientation="vertical", padding=dp(20), spacing=dp(14),
            radius=[16], size_hint=(None, None), size=(dp(320), dp(1)),
        )
        # Content here is variable ("Recently Used" only shows once a
        # color's been used), so a fixed guessed height either
        # overlapped content or left a blank gap. Let it size to
        # actual content instead.
        card.bind(minimum_height=card.setter("height"))

        card.add_widget(MDLabel(
            text="Text Color", halign="center", theme_text_color="Custom",
            size_hint_y=None, height=dp(28),
        ))

        card.add_widget(MDLabel(
            text="Palette", halign="left", theme_text_color="Custom",
            size_hint_y=None, height=dp(20),
        ))
        card.add_widget(self._build_color_grid(PALETTE_COLORS))

        if recent:
            card.add_widget(MDLabel(
                text="Recently Used", halign="left", theme_text_color="Custom",
                size_hint_y=None, height=dp(20),
            ))
            card.add_widget(self._build_color_grid(recent))

        card.add_widget(MDLabel(
            text="Hex Code", halign="left", theme_text_color="Custom",
            size_hint_y=None, height=dp(20),
        ))
        hex_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(48))
        hex_field = MDTextField(text=current_hex or "", size_hint_y=None, height=dp(48))
        hex_field.add_widget(MDTextFieldHintText(text="#RRGGBB"))
        apply_hex_button = MDButton(MDButtonText(text="Apply"), style="outlined")
        apply_hex_button.bind(on_release=lambda *_: self._apply_hex_input(hex_field.text))
        hex_row.add_widget(hex_field)
        hex_row.add_widget(apply_hex_button)
        card.add_widget(hex_row)

        button_row = BoxLayout(orientation="horizontal", spacing=dp(12), size_hint_y=None, height=dp(48))
        cancel_button = MDButton(MDButtonText(text="Cancel"), style="outlined")
        cancel_button.bind(on_release=lambda *_: modal.dismiss())
        button_row.add_widget(cancel_button)

        # Only offer "Remove Color" when editing an existing colored
        # span -- there's nothing to remove otherwise.
        if current_hex:
            remove_button = MDButton(MDButtonText(text="Remove Color"), style="outlined")
            remove_button.bind(on_release=lambda *_: self._remove_color())
            button_row.add_widget(remove_button)

        card.add_widget(button_row)

        modal = ModalView(
            size_hint=(None, None), size=(dp(320), card.height),
            auto_dismiss=True, background_color=(0, 0, 0, 0.5),
        )
        modal.add_widget(card)
        # Keep the backdrop size synced if the card's real height
        # changes after this point too.
        card.bind(height=modal.setter("height"))
        self._active_color_modal = modal
        modal.open()

    def _build_color_grid(self, hex_list):
        # size_hint_y=None + binding to minimum_height (instead of a
        # fixed dp(40)) lets the grid grow to a second row when there
        # are more colors than fit in one row -- a fixed height meant
        # any overflow row rendered overlapping whatever came next.
        grid = GridLayout(cols=6, spacing=dp(8), size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))
        for hex_value in hex_list:
            swatch = MDIconButton(icon="checkbox-blank-circle")
            # theme_icon_color must be explicit "Custom" or the
            # manually-set icon_color below is silently ignored --
            # same KivyMD quirk as md_bg_color elsewhere in the app.
            swatch.theme_icon_color = "Custom"
            swatch.icon_color = self._hex_to_rgba(hex_value)
            swatch.bind(on_release=lambda inst, hv=hex_value: self._apply_color(hv))
            grid.add_widget(swatch)
        return grid

    @staticmethod
    def _hex_to_rgba(hex_value):
        hex_value = hex_value.lstrip("#")
        r = int(hex_value[0:2], 16) / 255
        g = int(hex_value[2:4], 16) / 255
        b = int(hex_value[4:6], 16) / 255
        return (r, g, b, 1)

    def _apply_hex_input(self, text):
        text = text.strip()
        if not text.startswith("#"):
            text = "#" + text
        if len(text) == 7:
            try:
                int(text[1:], 16)  # validates it's really hex
                self._apply_color(text.upper())
            except ValueError:
                pass  # invalid hex -- dialog just stays open to retry

    def _apply_color(self, hex_value):
        field = self.ids.content_field
        open_tag = f"{{{{color:{hex_value}}}}}"
        close_tag = "{{/color}}"

        if self._pending_color_selection:
            kind, selected, start, end = self._pending_color_selection
            text = field.text
            if text[start:end] == selected:
                if kind == "edit":
                    inner = COLOR_TOKEN_PATTERN.fullmatch(selected).group(2)
                    token = f"{open_tag}{inner}{close_tag}"
                else:
                    token = f"{open_tag}{selected}{close_tag}"
                field.text = text[:start] + token + text[end:]
                field.cursor = field.get_cursor_from_index(start + len(token))
        else:
            field.insert_text(f"{open_tag}{close_tag}")
            index = field.cursor_index() - len(close_tag)
            field.cursor = field.get_cursor_from_index(index)

        self._pending_color_selection = None
        self._remember_recent_color(hex_value)
        if self._active_color_modal:
            self._active_color_modal.dismiss()
            self._active_color_modal = None
        self._refresh_preview_if_active()

    def _remove_color(self):
        if self._pending_color_selection and self._pending_color_selection[0] == "edit":
            _, selected, start, end = self._pending_color_selection
            field = self.ids.content_field
            inner = COLOR_TOKEN_PATTERN.fullmatch(selected).group(2)
            field.text = field.text[:start] + inner + field.text[end:]
            field.cursor = field.get_cursor_from_index(start + len(inner))
        self._pending_color_selection = None
        if self._active_color_modal:
            self._active_color_modal.dismiss()
            self._active_color_modal = None
        self._refresh_preview_if_active()

    def _remember_recent_color(self, hex_value):
        recent = get_pref("recent_text_colors") or []
        recent = [c for c in recent if c.upper() != hex_value.upper()]
        recent.insert(0, hex_value)
        set_pref("recent_text_colors", recent[:MAX_RECENT_COLORS])
# screens/editor/link_mixin.py
# Hyperlinks: selecting text and providing a URL wraps the selection
# in a {{link:URL|label}} marker. In Preview mode, that renders as
# tappable, underlined text.

from kivy.metrics import dp
from kivy.utils import platform, escape_markup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.textfield import MDTextField, MDTextFieldHintText
import webbrowser

from screens.editor.markup import LINK_TOKEN_PATTERN, escape_and_apply_format_markup
from screens.safe_card import make_safe_card


class HyperlinkMixin:
    """Requires: self.ids.content_field, self._last_selection,
    self._preview_link_map, self._link_ref_counter,
    self._pending_link_selection (set in __init__)."""

    def _convert_links_to_markup(self, text):
        def _replace(match):
            url, label = match.group(1), match.group(2)
            key = f"link{self._link_ref_counter}"
            self._link_ref_counter += 1
            self._preview_link_map[key] = url
            return f"[ref={key}][u][color=#3B6EA5]{label}[/color][/u][/ref]"
        return LINK_TOKEN_PATTERN.sub(_replace, text)

    def _convert_part_for_preview(self, text):
        # Order matters: escape first, THEN convert links (injects
        # real tags), THEN bold/italic/underline/highlight.
        text = escape_markup(text)
        text = self._convert_links_to_markup(text)
        text = escape_and_apply_format_markup(text)
        return text

    def _on_preview_link_pressed(self, instance, ref):
        url = self._preview_link_map.get(ref)
        if url:
            self._open_url(url)

    def _open_url(self, url):
        # On Android, opening a URL needs a system intent instead of
        # webbrowser.open() -- this only ever runs on an actual
        # Android build; desktop behavior is unaffected.
        if platform == "android":
            from jnius import autoclass  # type: ignore  -- Android-only import
            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            PythonActivity.mActivity.startActivity(intent)
        else:
            webbrowser.open(url)

    def make_link(self):
        field = self.ids.content_field
        if self._last_selection:
            selected, start, end = self._last_selection
            if field.text[start:end] == selected:
                self._pending_link_selection = (selected, start, end)
            else:
                self._pending_link_selection = None
        else:
            self._pending_link_selection = None

        self._show_link_url_popup()

    def _show_link_url_popup(self):
        card = make_safe_card(MDCard,
            orientation="vertical", padding=dp(20), spacing=dp(14),
            radius=[16], size_hint=(None, None), size=(dp(320), dp(180)),
        )

        prompt_label = MDLabel(
            text="Enter a URL to link to:", halign="center",
            theme_text_color="Custom", size_hint_y=None, height=dp(28),
        )
        card.add_widget(prompt_label)

        url_field = MDTextField(size_hint_y=None, height=dp(48))
        url_field.add_widget(MDTextFieldHintText(text="https://example.com"))
        card.add_widget(url_field)

        button_row = BoxLayout(orientation="horizontal", spacing=dp(12), size_hint_y=None, height=dp(48))
        cancel_button = MDButton(MDButtonText(text="Cancel"), style="outlined")
        cancel_button.bind(on_release=lambda *_: modal.dismiss())
        add_button = MDButton(MDButtonText(text="Add Link"), style="filled")
        add_button.bind(on_release=lambda *_: self._confirm_link(url_field.text, modal))
        button_row.add_widget(cancel_button)
        button_row.add_widget(add_button)
        card.add_widget(button_row)

        modal = ModalView(
            size_hint=(None, None), size=(dp(320), dp(180)),
            auto_dismiss=True, background_color=(0, 0, 0, 0.5),
        )
        modal.add_widget(card)
        modal.open()

    def _confirm_link(self, url, modal):
        modal.dismiss()
        url = url.strip()
        if not url:
            return

        if not (url.startswith("http://") or url.startswith("https://")):
            url = "https://" + url

        field = self.ids.content_field

        if self._pending_link_selection:
            selected, start, end = self._pending_link_selection
            if field.text[start:end] == selected:
                token = f"{{{{link:{url}|{selected}}}}}"
                field.text = field.text[:start] + token + field.text[end:]
                field.cursor = field.get_cursor_from_index(start + len(token))
                self._pending_link_selection = None
                return

        token = f"{{{{link:{url}|Link}}}}"
        field.insert_text(token)
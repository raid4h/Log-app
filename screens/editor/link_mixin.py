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

from screens.editor.markup import LINK_TOKEN_PATTERN, escape_and_apply_format_markup, extract_domain_label
from screens.safe_card import make_safe_card


class HyperlinkMixin:
    """Requires: self.ids.content_field, self._last_selection,
    self._preview_link_map, self._link_ref_counter,
    self._pending_link_selection, self._editing_link_span (both set in __init__)."""

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
        self._pending_link_selection = None
        self._editing_link_span = None

        if self._last_selection:
            selected, start, end = self._last_selection
            if field.text[start:end] == selected:
                # If the whole selection IS an existing {{link:...}}
                # marker, treat this as an edit: reopen the same
                # dialog pre-filled with the current URL/label instead
                # of wrapping the marker text as a NEW link's label.
                match = LINK_TOKEN_PATTERN.fullmatch(selected)
                if match:
                    existing_url, existing_label = match.group(1), match.group(2)
                    self._editing_link_span = (start, end)
                    self._show_link_url_popup(initial_url=existing_url, initial_label=existing_label)
                    return
                else:
                    self._pending_link_selection = (selected, start, end)

        self._show_link_url_popup()

    def _show_link_url_popup(self, initial_url="", initial_label=""):
        is_editing = bool(self._editing_link_span)

        card = make_safe_card(MDCard,
            orientation="vertical", padding=dp(20), spacing=dp(14),
            radius=[16], size_hint=(None, None), size=(dp(320), dp(260)),
        )

        prompt_label = MDLabel(
            text="Edit link:" if is_editing else "Enter a URL to link to:",
            halign="center", theme_text_color="Custom",
            size_hint_y=None, height=dp(28),
        )
        card.add_widget(prompt_label)

        url_field = MDTextField(text=initial_url, size_hint_y=None, height=dp(48))
        url_field.add_widget(MDTextFieldHintText(text="https://example.com"))
        card.add_widget(url_field)

        label_field = MDTextField(text=initial_label, size_hint_y=None, height=dp(48))
        label_field.add_widget(MDTextFieldHintText(text="Display text"))
        card.add_widget(label_field)

        # "state" tracks whether the label field should keep
        # auto-filling from the URL, or whether the user (or an
        # existing selection/edit) has already put real content there.
        # auto_filling guards against our OWN text-set below
        # re-triggering _on_label_text and falsely marking it "touched".
        state = {
            "label_touched": is_editing or bool(initial_label),
            "auto_filling": False,
        }

        def _on_url_text(instance, value):
            if state["label_touched"]:
                return
            state["auto_filling"] = True
            label_field.text = extract_domain_label(value)
            state["auto_filling"] = False

        def _on_label_text(instance, value):
            if state["auto_filling"]:
                return
            state["label_touched"] = True

        url_field.bind(text=_on_url_text)
        label_field.bind(text=_on_label_text)

        # Plain text was selected before tapping the link button --
        # that becomes the starting label, same as before, and counts
        # as "touched" so typing a URL afterward won't overwrite it.
        if self._pending_link_selection:
            label_field.text = self._pending_link_selection[0]
            state["label_touched"] = True

        button_row = BoxLayout(orientation="horizontal", spacing=dp(12), size_hint_y=None, height=dp(48))
        cancel_button = MDButton(MDButtonText(text="Cancel"), style="outlined")
        cancel_button.bind(on_release=lambda *_: modal.dismiss())
        add_button = MDButton(MDButtonText(text="Save" if is_editing else "Add Link"), style="filled")
        add_button.bind(on_release=lambda *_: self._confirm_link(url_field.text, label_field.text, modal))
        button_row.add_widget(cancel_button)
        button_row.add_widget(add_button)
        card.add_widget(button_row)

        modal = ModalView(
            size_hint=(None, None), size=(dp(320), dp(260)),
            auto_dismiss=True, background_color=(0, 0, 0, 0.5),
        )
        modal.add_widget(card)
        modal.open()

    def _confirm_link(self, url, label, modal):
        modal.dismiss()
        url = url.strip()
        label = label.strip()
        if not url:
            return

        if not (url.startswith("http://") or url.startswith("https://")):
            url = "https://" + url

        # Safety net: if they cleared the auto-filled label entirely,
        # don't save an empty display text -- fall back to the domain.
        if not label:
            label = extract_domain_label(url)

        field = self.ids.content_field
        token = f"{{{{link:{url}|{label}}}}}"

        if self._editing_link_span:
            start, end = self._editing_link_span
            field.text = field.text[:start] + token + field.text[end:]
            field.cursor = field.get_cursor_from_index(start + len(token))
            self._editing_link_span = None
            return

        if self._pending_link_selection:
            selected, start, end = self._pending_link_selection
            if field.text[start:end] == selected:
                field.text = field.text[:start] + token + field.text[end:]
                field.cursor = field.get_cursor_from_index(start + len(token))
                self._pending_link_selection = None
                return

        field.insert_text(token)
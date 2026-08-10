# screens/editor/export_mixin.py
# Exports the current note as a plain .txt file, letting the user pick
# the save location via a native file dialog.

import os
import re
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDButton, MDButtonText
from plyer import filechooser

from screens.editor.paths import get_exports_dir
from screens.editor.markup import strip_markers_for_export
from screens.safe_card import make_safe_card

_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')


class ExportMixin:
    """Requires: self.ids.title_field, self.ids.content_field."""

    def _sanitize_filename(self, name):
        cleaned = _INVALID_FILENAME_CHARS.sub("", name).strip()
        return cleaned if cleaned else "Untitled"

    def export_note_as_txt(self):
        title = self.ids.title_field.text.strip() or "Untitled"
        self._export_title = title
        self._export_clean_content = strip_markers_for_export(self.ids.content_field.text)

        safe_title = self._sanitize_filename(title)
        exports_dir = get_exports_dir()
        os.makedirs(exports_dir, exist_ok=True)

        self._cwd_before_export_picker = os.getcwd()

        filechooser.save_file(
            on_selection=self.on_export_location_selected,
            filters=[["Text files", "*.txt"]],
            path = os.path.join(exports_dir, f"{safe_title}.txt"),
        )

    def on_export_location_selected(self, selection):
        os.chdir(self._cwd_before_export_picker)
        Clock.schedule_once(lambda dt: self._write_export_file(selection))

    def _write_export_file(self, selection):
        if not selection:
            return

        export_path = selection[0]
        if not export_path.lower().endswith(".txt"):
            export_path += ".txt"

        with open(export_path, "w", encoding="utf-8") as f:
            f.write(f"{self._export_title}\n\n{self._export_clean_content}")

        self._show_export_confirmation(export_path)

    def _show_export_confirmation(self, export_path):
        card = make_safe_card(MDCard,
            orientation="vertical", padding=dp(20), spacing=dp(16),
            radius=[16], size_hint=(None, None), size=(dp(320), dp(170)),
        )

        message_label = MDLabel(
            text=f"Note exported to:\n{export_path}",
            halign="center", theme_text_color="Custom", size_hint_y=None,
        )
        message_label.bind(width=lambda inst, val: setattr(inst, "text_size", (val, None)))
        message_label.bind(texture_size=lambda inst, val: setattr(inst, "height", val[1]))
        card.add_widget(message_label)

        modal = ModalView(
            size_hint=(None, None), size=(dp(320), dp(170)),
            auto_dismiss=True, background_color=(0, 0, 0, 0.5),
        )

        ok_button = MDButton(MDButtonText(text="OK"), style="filled")
        ok_button.bind(on_release=lambda *_: modal.dismiss())

        button_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48))
        button_row.add_widget(ok_button)
        card.add_widget(button_row)

        modal.add_widget(card)
        modal.open()
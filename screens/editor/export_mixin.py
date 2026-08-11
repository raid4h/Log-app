# screens/editor/export_mixin.py
# Exports the current note as a plain .txt file, letting the user pick
# the save location via a native file dialog.

import os
import re
from kivy.utils import platform
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
# Arbitrary number Android uses to match the save dialog's result back
# to this specific request.
_ANDROID_SAVE_REQUEST_CODE = 4321


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

        if platform == "android":
            # plyer's save_file() has no real Android implementation --
            # it silently does nothing. So on Android we skip plyer and
            # ask Android's OWN native "Save As" dialog directly (the
            # same one Chrome/Gmail use, lets the user pick Downloads,
            # Drive, etc).
            self._android_save_as(f"{safe_title}.txt")
            return

        # Desktop (Windows/Linux) keeps using plyer's dialog, which
        # works fine there.
        exports_dir = get_exports_dir()
        os.makedirs(exports_dir, exist_ok=True)
        self._cwd_before_export_picker = os.getcwd()
        filechooser.save_file(
            on_selection=self.on_export_location_selected,
            filters=[["Text files", "*.txt"]],
            path=os.path.join(exports_dir, f"{safe_title}.txt"),
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

    def _android_save_as(self, filename):
        # jnius is the bridge that lets Python call real Android/Java
        # code. Imported HERE, not at the top of the file, so this file
        # can still be opened/tested on Windows without crashing --
        # these modules only exist inside an actual Android build.
        from android import activity
        from jnius import autoclass

        Intent = autoclass("android.content.Intent")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")

        # ACTION_CREATE_DOCUMENT is Android's built-in "Save As" dialog.
        intent = Intent(Intent.ACTION_CREATE_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType("text/plain")
        intent.putExtra(Intent.EXTRA_TITLE, filename)

        # Listen for Android's answer once the user finishes the dialog.
        activity.bind(on_activity_result=self._on_android_save_result)
        PythonActivity.mActivity.startActivityForResult(intent, _ANDROID_SAVE_REQUEST_CODE)

    def _on_android_save_result(self, requestCode, resultCode, data):
        if requestCode != _ANDROID_SAVE_REQUEST_CODE:
            return

        from android import activity
        from jnius import autoclass

        # Stop listening -- otherwise this would fire again on the
        # NEXT unrelated activity result too.
        activity.unbind(on_activity_result=self._on_android_save_result)

        Activity = autoclass("android.app.Activity")
        if resultCode != Activity.RESULT_OK or data is None:
            return  # user backed out of the save dialog -- do nothing

        uri = data.getData()  # the location the user picked

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        resolver = PythonActivity.mActivity.getContentResolver()
        output_stream = resolver.openOutputStream(uri)

        content_bytes = f"{self._export_title}\n\n{self._export_clean_content}".encode("utf-8")
        output_stream.write(content_bytes)
        output_stream.close()

        # Kivy widgets should be touched from Kivy's own thread, so we
        # hand the confirmation popup off to Clock instead of calling
        # it directly from this Android callback.
        Clock.schedule_once(lambda dt: self._show_export_confirmation(uri.toString()))

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
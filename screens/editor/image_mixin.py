# screens/editor/image_mixin.py
# Picking a photo, copying it into the app's own local folder,
# inserting an inline {{img:...}} marker, and cleaning up attachment
# records for images removed from a note's text later.
#
# On Android, this uses the system's Photo Picker (a built-in gallery
# picker) instead of a generic file browser -- it only ever shows
# photos/albums (never Downloads or other file sources), and always
# hands back something readable, unlike the old approach which failed
# silently on some phones/folders.

import os
import shutil
import uuid

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView
from kivy.utils import platform
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDButton, MDButtonText
from plyer import filechooser

from database.notes_queries import create_notes
from database.attachment_queries import create_attachment, get_all_attachments, delete_attachment
from screens.editor.paths import get_attachments_dir, DEFAULT_NOTEBOOK_ID
from screens.editor.markup import IMAGE_TOKEN_PATTERN
from screens.safe_card import make_safe_card

# Arbitrary number Android uses to match the picker's result back to
# this specific request.
_ANDROID_PICK_IMAGE_REQUEST_CODE = 7531

# Content URIs from the Photo Picker don't come with a normal filename
# -- this maps the picked image's reported type to a sensible file
# extension for the copy we save locally.
_MIME_TO_EXTENSION = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class ImageAttachmentMixin:
    """Requires: self.current_note_id, self.ids.content_field,
    self.ids.title_field."""

    def pick_image(self):
        if self.current_note_id is None:
            title = self.ids.title_field.text.strip() or "Untitled"
            content = self.ids.content_field.text
            self.current_note_id = create_notes(DEFAULT_NOTEBOOK_ID, title, content)
            if not self.ids.title_field.text.strip():
                self.ids.title_field.text = title

        if platform == "android":
            self._android_pick_image()
            return

        # Windows/Linux keep using plyer's picker, which works fine there.
        # Windows' native file dialog silently changes the working
        # directory to match wherever you picked a file from, which
        # breaks the database's relative path. Save/restore around it.
        self._cwd_before_picker = os.getcwd()
        filechooser.open_file(
            on_selection=self.on_image_selected,
            filters=[["Images", "*.png", "*.jpg", "*.jpeg"]],
        )

    def on_image_selected(self, selection):
        os.chdir(self._cwd_before_picker)
        Clock.schedule_once(lambda dt: self._insert_image_token(selection))

    def _insert_image_token(self, selection):
        # Desktop-only path (plyer). The Android path below
        # (_insert_image_from_uri) handles Android instead.
        if not selection or selection[0] is None:
            return
        original_path = selection[0]

        attachments_dir = get_attachments_dir()
        os.makedirs(attachments_dir, exist_ok=True)
        file_extension = os.path.splitext(original_path)[1]
        stored_filename = f"{uuid.uuid4().hex}{file_extension}"
        stored_path = os.path.join(attachments_dir, stored_filename)
        shutil.copy2(original_path, stored_path)

        create_attachment(self.current_note_id, stored_path)
        self._insert_token_into_editor(stored_path)

    def _android_pick_image(self):
        # jnius is the bridge that lets Python call real Android/Java
        # code. Imported HERE, not at the top of the file, so this
        # file can still be opened/edited on Windows without
        # complaint -- these modules only exist inside an actual
        # Android build, at runtime, on the device.
        from android import activity
        from jnius import autoclass

        Intent = autoclass("android.content.Intent")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        current_activity = PythonActivity.mActivity

        # ACTION_PICK_IMAGES is Android's built-in Photo Picker -- shows
        # ONLY the phone's own photos/albums, never Downloads or other
        # file sources, and always returns something readable.
        intent = Intent("android.provider.action.PICK_IMAGES")
        intent.setType("image/*")

        if intent.resolveActivity(current_activity.getPackageManager()) is None:
            # Very old/unusual phones without the Photo Picker -- fall
            # back to the old generic file browser instead of doing
            # nothing at all.
            self._cwd_before_picker = os.getcwd()
            filechooser.open_file(
                on_selection=self.on_image_selected,
                filters=[["Images", "*.png", "*.jpg", "*.jpeg"]],
            )
            return

        activity.bind(on_activity_result=self._on_android_image_result)
        current_activity.startActivityForResult(intent, _ANDROID_PICK_IMAGE_REQUEST_CODE)

    def _on_android_image_result(self, requestCode, resultCode, data):
        if requestCode != _ANDROID_PICK_IMAGE_REQUEST_CODE:
            return

        from android import activity
        from jnius import autoclass

        # Stop listening -- otherwise this would fire again on the
        # NEXT unrelated activity result too.
        activity.unbind(on_activity_result=self._on_android_image_result)

        Activity = autoclass("android.app.Activity")
        if resultCode != Activity.RESULT_OK or data is None:
            return  # user backed out of the picker -- do nothing

        uri = data.getData()
        Clock.schedule_once(lambda dt: self._insert_image_from_uri(uri))

    def _insert_image_from_uri(self, uri):
        from jnius import autoclass

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        resolver = PythonActivity.mActivity.getContentResolver()

        attachments_dir = get_attachments_dir()
        os.makedirs(attachments_dir, exist_ok=True)

        mime_type = resolver.getType(uri) or "image/jpeg"
        file_extension = _MIME_TO_EXTENSION.get(mime_type, ".jpg")
        stored_filename = f"{uuid.uuid4().hex}{file_extension}"
        stored_path = os.path.join(attachments_dir, stored_filename)

        try:
            input_stream = resolver.openInputStream(uri)
            buffer = bytearray(8192)
            with open(stored_path, "wb") as out_file:
                while True:
                    bytes_read = input_stream.read(buffer)
                    if bytes_read == -1:
                        break
                    out_file.write(bytes(buffer[:bytes_read]))
            input_stream.close()
        except Exception:
            # Picked photo couldn't actually be read -- e.g. a
            # cloud-only photo that hasn't downloaded to the phone
            # yet. Tell the user instead of silently doing nothing.
            self._show_image_message(
                "Couldn't attach that photo. Try one that's already "
                "downloaded to your phone."
            )
            return

        create_attachment(self.current_note_id, stored_path)
        self._insert_token_into_editor(stored_path)

    def _insert_token_into_editor(self, stored_path):
        token = f"{{{{img:{stored_path}}}}}"
        field = self.ids.content_field
        try:
            field.insert_text(token)
        except AttributeError:
            field.text = field.text + ("\n" if field.text else "") + token

    def _show_image_message(self, message_text):
        card = make_safe_card(MDCard,
            orientation="vertical", padding=dp(20), spacing=dp(16),
            radius=[16], size_hint=(None, None), size=(dp(300), dp(160)),
        )

        label = MDLabel(
            text=message_text, halign="center",
            theme_text_color="Custom", size_hint_y=None,
        )
        label.bind(width=lambda inst, val: setattr(inst, "text_size", (val, None)))
        label.bind(texture_size=lambda inst, val: setattr(inst, "height", val[1]))
        card.add_widget(label)

        modal = ModalView(
            size_hint=(None, None), size=(dp(300), dp(160)),
            auto_dismiss=True, background_color=(0, 0, 0, 0.5),
        )

        ok_button = MDButton(MDButtonText(text="OK"), style="filled")
        ok_button.bind(on_release=lambda *_: modal.dismiss())

        button_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48))
        button_row.add_widget(ok_button)
        card.add_widget(button_row)

        modal.add_widget(card)
        modal.open()

    def _cleanup_removed_attachments(self, content):
        remaining_paths = set(IMAGE_TOKEN_PATTERN.findall(content))
        for row in get_all_attachments(self.current_note_id):
            if row[2] not in remaining_paths:
                delete_attachment(row[0])
                # Only removes the database record -- the copied file
                # in note_attachments/ is left on disk untouched.
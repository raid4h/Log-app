# screens/editor/image_mixin.py
# Picking a photo, copying it into the app's own local folder,
# inserting an inline {{img:...}} marker, and cleaning up attachment
# records for images removed from a note's text later.

import os
import shutil
import uuid

from kivy.clock import Clock
from plyer import filechooser

from database.notes_queries import create_notes
from database.attachment_queries import create_attachment, get_all_attachments, delete_attachment
from screens.editor.paths import get_attachments_dir, DEFAULT_NOTEBOOK_ID
from screens.editor.markup import IMAGE_TOKEN_PATTERN


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

        token = f"{{{{img:{stored_path}}}}}"
        field = self.ids.content_field
        try:
            field.insert_text(token)
        except AttributeError:
            field.text = field.text + ("\n" if field.text else "") + token

    def _cleanup_removed_attachments(self, content):
        remaining_paths = set(IMAGE_TOKEN_PATTERN.findall(content))
        for row in get_all_attachments(self.current_note_id):
            if row[2] not in remaining_paths:
                delete_attachment(row[0])
                # Only removes the database record -- the copied file
                # in note_attachments/ is left on disk untouched.
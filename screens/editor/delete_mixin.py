# screens/editor/delete_mixin.py
# Delete confirmation popup, plus snapshotting the note into local
# trash before it's actually removed, so it can be recovered from
# Recently Deleted.

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDButton, MDButtonText

from screens.safe_card import make_safe_card
import trash_store
from database.notes_queries import get_notes_by_id, delete_notes


class DeleteConfirmationMixin:
    """Requires: self.current_note_id, self.go_back()."""

    def _build_delete_confirmation(self):
        card = make_safe_card(MDCard,
            orientation="vertical", padding=dp(20), spacing=dp(16),
            radius=[16], size_hint=(None, None), size=(dp(300), dp(160)),
        )

        warning_label = MDLabel(
            text="Are you sure you want to delete? Notes can be restored in Recently Deleted.",
            halign="center", theme_text_color="Custom", size_hint_y=None,
        )
        warning_label.bind(width=lambda inst, val: setattr(inst, "text_size", (val, None)))
        warning_label.bind(texture_size=lambda inst, val: setattr(inst, "height", val[1]))
        card.add_widget(warning_label)

        button_row = BoxLayout(orientation="horizontal", spacing=dp(12), size_hint_y=None, height=dp(48))
        cancel_button = MDButton(MDButtonText(text="Cancel"), style="outlined")
        cancel_button.bind(on_release=lambda *_: self._delete_modal.dismiss())
        confirm_button = MDButton(MDButtonText(text="Delete"), style="filled")
        confirm_button.bind(on_release=lambda *_: self._confirm_delete())
        button_row.add_widget(cancel_button)
        button_row.add_widget(confirm_button)
        card.add_widget(button_row)

        self._delete_modal = ModalView(
            size_hint=(None, None), size=(dp(300), dp(160)),
            auto_dismiss=True, background_color=(0, 0, 0, 0.5),
        )
        self._delete_modal.add_widget(card)

    def delete_note(self):
        if self.current_note_id is None:
            self.go_back()
            return

        if not hasattr(self, "_delete_modal"):
            self._build_delete_confirmation()
        self._delete_modal.open()

    def _confirm_delete(self):
        self._delete_modal.dismiss()

        note = get_notes_by_id(self.current_note_id)
        if note is not None:
            trash_store.add_to_trash(
                notebook_id=note[1], title=note[2],
                content=note[3] or "", category_id=note[8],
            )

        delete_notes(self.current_note_id)
        self.go_back()
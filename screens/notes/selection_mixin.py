# screens/notes/selection_mixin.py
# Multi-select mode: toggling it on/off, tracking checked notes, and
# bulk deletion (with the same recoverable trash snapshot as a single
# note delete).

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDButton, MDButtonText

from screens.safe_card import make_safe_card
import trash_store
from database.notes_queries import get_notes_by_id, delete_notes


class SelectionMixin:
    """Requires: self.selection_mode, self.selected_note_ids,
    self.load_notes(), self.ids."""

    def toggle_selection_mode(self):
        self.selection_mode = not self.selection_mode
        self.selected_note_ids = set()
        self._update_selection_label()
        self.load_notes()

    def on_card_selection_changed(self, note_id, is_selected):
        if is_selected:
            self.selected_note_ids.add(note_id)
        else:
            self.selected_note_ids.discard(note_id)
        self._update_selection_label()

    def _update_selection_label(self):
        if "selection_count_label" in self.ids:
            count = len(self.selected_note_ids)
            self.ids.selection_count_label.text = f"{count} selected"

    def delete_selected_notes(self):
        if not self.selected_note_ids:
            return
        self._show_bulk_delete_confirmation()

    def _show_bulk_delete_confirmation(self):
        count = len(self.selected_note_ids)
        card = make_safe_card(MDCard,
            orientation="vertical", padding=dp(20), spacing=dp(16),
            radius=[16], size_hint=(None, None), size=(dp(300), dp(160)),
        )
        warning_label = MDLabel(
            text=f"Delete {count} note{'s' if count != 1 else ''}? This can't be undone.",
            halign="center", theme_text_color="Custom", size_hint_y=None,
        )
        warning_label.bind(width=lambda inst, val: setattr(inst, "text_size", (val, None)))
        warning_label.bind(texture_size=lambda inst, val: setattr(inst, "height", val[1]))
        card.add_widget(warning_label)

        button_row = BoxLayout(orientation="horizontal", spacing=dp(12), size_hint_y=None, height=dp(48))
        cancel_button = MDButton(MDButtonText(text="Cancel"), style="outlined")
        cancel_button.bind(on_release=lambda *_: modal.dismiss())
        confirm_button = MDButton(MDButtonText(text="Delete"), style="filled")
        confirm_button.bind(on_release=lambda *_: self._confirm_bulk_delete(modal))
        button_row.add_widget(cancel_button)
        button_row.add_widget(confirm_button)
        card.add_widget(button_row)

        modal = ModalView(
            size_hint=(None, None), size=(dp(300), dp(160)),
            auto_dismiss=True, background_color=(0, 0, 0, 0.5),
        )
        modal.add_widget(card)
        modal.open()

    def _confirm_bulk_delete(self, modal):
        modal.dismiss()
        for note_id in list(self.selected_note_ids):
            note = get_notes_by_id(note_id)
            if note is not None:
                trash_store.add_to_trash(
                    notebook_id=note[1], title=note[2],
                    content=note[3] or "", category_id=note[8],
                )
            delete_notes(note_id)

        self.selection_mode = False
        self.selected_note_ids = set()
        self.load_notes()
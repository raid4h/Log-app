# screens/notes/list_mixin.py
# Loading, searching, sorting, and rendering the notes list in either
# list or grid layout. Also owns pin/archive/category-filtering, since
# all of these just mutate state then reload this same list.

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel

from widgets.note_card import NoteCard
from database.notes_queries import get_all_notes, search_notes as db_search_notes, archive_notes, pin_notes
from screens.notes.helpers import format_last_edited, clean_preview_text
from screens.category_helpers import list_categories, category_color_rgba, contrasting_text_color
import user_prefs

DEFAULT_NOTEBOOK_ID = 1
GRID_ROW_HEIGHT = dp(230)


class _FilterChip(MDCard):
    # No ButtonBehavior here -- MDCard already has its own built-in
    # tap handling (same reason DashboardTile/SmallTile respond to
    # on_release with no ButtonBehavior added). Combining the two
    # causes a Python MRO conflict, which is what actually crashed.
    pass


class NotesListMixin:
    """Requires: self.ids.notes_list, self.sort_by, self.view_mode,
    self.selection_mode, self.selected_note_ids, self.selected_category_id."""

    def load_notes(self):
        all_notes = get_all_notes(DEFAULT_NOTEBOOK_ID)
        visible = [n for n in all_notes if n[5] == 0]
        visible = self._filter_by_category(visible)
        pinned = [n for n in visible if n[4] == 1]
        unpinned = [n for n in visible if n[4] == 0]
        if self.sort_by == "title":
            unpinned.sort(key=lambda n: n[2].lower())
        self._populate_notes_list(pinned + unpinned)
        self._populate_category_filter_chips()

    def search_notes(self, query):
        if query.strip() == "":
            self.load_notes()
            return
        results = db_search_notes(query)
        results = self._filter_by_category(results)
        self._populate_notes_list(results)
        self._populate_category_filter_chips()

    def _filter_by_category(self, notes):
        if self.selected_category_id is None:
            return notes
        return [n for n in notes if n[8] == self.selected_category_id]

    def set_category_filter(self, category_id):
        self.selected_category_id = category_id
        self.load_notes()

    def _build_note_card(self, note, category_lookup, grid_mode=False):
        return NoteCard(
            title=note[2],
            preview=clean_preview_text(note[3]),
            note_id=note[0],
            is_pinned=bool(note[4]),
            last_edited=format_last_edited(note[7]),
            selection_mode=self.selection_mode,
            is_selected=note[0] in self.selected_note_ids,
            grid_mode=grid_mode,
            category_color=category_lookup.get(note[8]),
        )

    def _populate_notes_list(self, notes):
        self.ids.notes_list.clear_widgets()

        # Built once per render, not once per card -- avoids querying
        # the categories table repeatedly in a loop.
        category_lookup = {c[0]: category_color_rgba(c[2]) for c in list_categories()}

        if self.view_mode == "list":
            for note in notes:
                card = self._build_note_card(note, category_lookup, grid_mode=False)
                self.ids.notes_list.add_widget(card)
                if hasattr(card, "apply_theme"):
                    card.apply_theme()
        else:
            for i in range(0, len(notes), 2):
                row = BoxLayout(
                    orientation="horizontal", size_hint_y=None,
                    height=GRID_ROW_HEIGHT, spacing=dp(10),
                )
                for note in notes[i:i + 2]:
                    card = self._build_note_card(note, category_lookup, grid_mode=True)
                    row.add_widget(card)
                    if hasattr(card, "apply_theme"):
                        card.apply_theme()
                self.ids.notes_list.add_widget(row)

    def _populate_category_filter_chips(self):
        container = self.ids.get("category_filter_chips")
        if container is None:
            return
        container.clear_widgets()

        container.add_widget(self._build_filter_chip("All", None, (0.85, 0.85, 0.85, 1)))
        for cat in list_categories():
            cat_id, name, color_hex = cat[0], cat[1], cat[2]
            container.add_widget(self._build_filter_chip(name, cat_id, category_color_rgba(color_hex)))

    def _build_filter_chip(self, label_text, category_id, color_rgba):
        is_selected = self.selected_category_id == category_id

        label = MDLabel(
            text=label_text,
            theme_text_color="Custom",
            # Automatically switches to light text on dark-colored
            # chips (like brown), instead of always using dark text.
            text_color=contrasting_text_color(color_rgba),
            adaptive_size=True,
            size_hint=(None, None),
            bold=is_selected,
        )

        chip = _FilterChip(
            orientation="horizontal",
            size_hint=(None, None),
            adaptive_size=True,
            padding=(dp(12), dp(6)),
            radius=[16],
            elevation=3 if is_selected else 0,
            ripple_behavior=False,
            theme_bg_color="Custom",
            md_bg_color=color_rgba,
        )
        chip.add_widget(label)
        chip.bind(on_release=lambda inst, cid=category_id: self.set_category_filter(cid))
        return chip

    def toggle_view_mode(self):
        self.view_mode = "grid" if self.view_mode == "list" else "list"
        user_prefs.set_pref("view_mode", self.view_mode)
        self.load_notes()

    def sort_notes(self, mode):
        self.sort_by = mode
        self.load_notes()

    def archive_note(self, note_id):
        archive_notes(note_id, 1)
        self.load_notes()

    def toggle_pin_note(self, note_id, is_pinned):
        new_value = 0 if is_pinned else 1
        pin_notes(note_id, new_value)
        self.load_notes()
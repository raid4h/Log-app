# screens/editor/search_mixin.py
# Simple in-note text search, reusing content_field's own selection
# highlight to show the current match.

from kivy.clock import Clock


class SearchMixin:
    """Requires: self.ids.content_field, self.ids.search_query_field,
    self.ids.search_match_label, self.view_mode, self.set_view_mode(),
    self.show_search."""

    def toggle_search(self):
        self.show_search = not self.show_search
        field = self.ids.content_field

        if self.show_search:
            # Only forces a switch out of FULL preview -- content_field
            # is already visible and typeable in Split mode, so search
            # should just open in place there instead of collapsing
            # the split view back to edit-only. (Used to check
            # self.is_preview, which is True for both split and full
            # preview -- that incorrectly collapsed split mode too.)
            if self.view_mode == "preview":
                self.set_view_mode("edit")
            self.ids.search_query_field.text = ""
            self._search_matches = []
            self._search_match_index = -1
            self._update_search_match_label()
            Clock.schedule_once(lambda dt: setattr(self.ids.search_query_field, "focus", True))
        else:
            field.cancel_selection()

    def _find_all_matches(self, text, query):
        matches = []
        if not query:
            return matches
        lower_text = text.lower()
        lower_query = query.lower()
        start = 0
        while True:
            index = lower_text.find(lower_query, start)
            if index == -1:
                break
            matches.append((index, index + len(query)))
            start = index + 1
        return matches

    def on_search_text_change(self, query):
        field = self.ids.content_field
        self._search_matches = self._find_all_matches(field.text, query)
        self._search_match_index = 0 if self._search_matches else -1
        self._update_search_match_label()

        if self._search_matches:
            self._jump_to_match(self._search_match_index)
        else:
            field.cancel_selection()

    def search_next(self):
        if not self._search_matches:
            return
        self._search_match_index = (self._search_match_index + 1) % len(self._search_matches)
        self._jump_to_match(self._search_match_index)
        self._update_search_match_label()

    def search_prev(self):
        if not self._search_matches:
            return
        self._search_match_index = (self._search_match_index - 1) % len(self._search_matches)
        self._jump_to_match(self._search_match_index)
        self._update_search_match_label()

    def _jump_to_match(self, index):
        field = self.ids.content_field
        start, end = self._search_matches[index]
        field.cursor = field.get_cursor_from_index(start)
        field.select_text(start, end)

    def _update_search_match_label(self):
        if "search_match_label" not in self.ids:
            return
        if not self._search_matches:
            self.ids.search_match_label.text = "0/0"
        else:
            self.ids.search_match_label.text = f"{self._search_match_index + 1}/{len(self._search_matches)}"

    def _reset_search_state(self):
        # Called when a note (or blank new note) loads -- clears any
        # leftover query from whatever note was open before this one.
        self.show_search = False
        self._search_matches = []
        self._search_match_index = -1
        if "search_query_field" in self.ids:
            self.ids.search_query_field.text = ""
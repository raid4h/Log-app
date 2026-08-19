# screens/editor/formatting_mixin.py
# Bold/italic/underline (wrap or un-wrap selected text), font size,
# font family, and text alignment. Highlight (==...==) was REMOVED as
# a toolbar feature -- it was a deliberate color-based approximation
# of a background highlight, made redundant once real text color
# (TextColorMixin, color_mixin.py) shipped. See markup.py for how
# already-saved ==...== markers in existing notes are still handled.

from screens.editor.font_registry import FONT_SIZES, FONT_CHOICES


class FormattingMixin:
    """Requires: self.ids.content_field, self._last_selection (set in
    __init__), self._refresh_preview_if_active() (main screen class)."""

    def _track_selection(self, field, value):
        if value:
            start, end = sorted((field.selection_from, field.selection_to))
            self._last_selection = (value, start, end)

    def _wrap_selection(self, marker):
        field = self.ids.content_field

        if not self._last_selection:
            field.insert_text(marker + marker)
            index = field.cursor_index() - len(marker)
            field.cursor = field.get_cursor_from_index(index)
            return

        selected, start, end = self._last_selection
        text = field.text

        if text[start:end] != selected:
            self._last_selection = None
            field.insert_text(marker + marker)
            index = field.cursor_index() - len(marker)
            field.cursor = field.get_cursor_from_index(index)
            return

        m_len = len(marker)

        # Case 1: the selection ITSELF includes the markers -- strip them.
        if selected.startswith(marker) and selected.endswith(marker) and len(selected) >= 2 * m_len:
            inner = selected[m_len:-m_len]
            field.text = text[:start] + inner + text[end:]
            field.cursor = field.get_cursor_from_index(start + len(inner))
            self._last_selection = None
            return

        # Case 2: the markers sit just outside the selection -- the
        # natural way people reselect text to undo formatting.
        before = text[max(0, start - m_len):start]
        after = text[end:end + m_len]
        if before == marker and after == marker:
            field.text = text[:start - m_len] + selected + text[end + m_len:]
            field.cursor = field.get_cursor_from_index(start - m_len + len(selected))
            self._last_selection = None
            return

        # Neither case matched -- wrap it normally.
        field.text = text[:start] + marker + selected + marker + text[end:]
        field.cursor = field.get_cursor_from_index(end + 2 * m_len)
        self._last_selection = None

    def make_bold(self):
        self._wrap_selection("**")

    def make_italic(self):
        self._wrap_selection("*")

    def make_underline(self):
        self._wrap_selection("__")

    def increase_font_size(self):
        field = self.ids.content_field
        bigger = [s for s in FONT_SIZES if s > field.font_size]
        if bigger:
            field.font_size = bigger[0]
        self._refresh_preview_if_active()

    def decrease_font_size(self):
        field = self.ids.content_field
        smaller = [s for s in FONT_SIZES if s < field.font_size]
        if smaller:
            field.font_size = smaller[-1]
        self._refresh_preview_if_active()

    def cycle_font(self):
        field = self.ids.content_field
        try:
            current_index = FONT_CHOICES.index(field.font_name)
        except ValueError:
            current_index = -1
        field.font_name = FONT_CHOICES[(current_index + 1) % len(FONT_CHOICES)]
        self._refresh_preview_if_active()

    def set_align_left(self):
        self.ids.content_field.halign = "left"
        self._refresh_preview_if_active()

    def set_align_center(self):
        self.ids.content_field.halign = "center"
        self._refresh_preview_if_active()

    def set_align_right(self):
        self.ids.content_field.halign = "right"
        self._refresh_preview_if_active()
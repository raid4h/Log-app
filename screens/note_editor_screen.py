# screens/note_editor_screen.py
# The note editor screen. Core note lifecycle (load/save/duplicate,
# Preview mode) lives here; everything else is split into focused
# mixins under screens/editor/, so this file doesn't hold the entire
# feature set at once.

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.modalview import ModalView
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDButton, MDButtonText
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.properties import BooleanProperty
from kivymd.uix.screen import MDScreen
from kivy.core.window import Window
from screens.editor.formatting_toolbar import FormattingToolbar  # noqa: F401 -- registers the widget class with KV before app.kv loads it, same fix as the earlier DashboardTile "Unknown class" issue

from database.notes_queries import get_notes_by_id, create_notes, update_notes, duplicate_notes

from screens.safe_card import make_safe_card
from theme.theme_manager import theme_manager
from theme.themed_screen import ThemedScreenMixin
from theme.palettes import BACKGROUND, TEXT_PRIMARY, TEXT_SECONDARY, CARD_SECONDARY, CARD_PRIMARY, ACCENT

from screens.editor.paths import DEFAULT_NOTEBOOK_ID
from screens.editor.markup import IMAGE_TOKEN_PATTERN
from screens.editor.note_meta import (
    parse_note_meta, build_note_meta,
    DEFAULT_FONT_NAME, DEFAULT_FONT_SIZE, DEFAULT_ALIGN,
)
from screens.editor.formatting_mixin import FormattingMixin
from screens.editor.undo_redo_mixin import UndoRedoMixin
from screens.editor.search_mixin import SearchMixin
from screens.editor.image_mixin import ImageAttachmentMixin
from screens.editor.link_mixin import HyperlinkMixin
from screens.editor.color_mixin import TextColorMixin
from screens.editor.export_mixin import ExportMixin
from screens.editor.delete_mixin import DeleteConfirmationMixin
from screens.editor.category_mixin import CategoryMixin, CategoryPillButton  # noqa: F401
from screens.editor.delete_mixin import DeleteConfirmationMixin



class NoteEditorScreen(
    ThemedScreenMixin,
    FormattingMixin,
    UndoRedoMixin,
    SearchMixin,
    ImageAttachmentMixin,
    HyperlinkMixin,
    TextColorMixin,
    ExportMixin,
    DeleteConfirmationMixin,
    CategoryMixin,
    MDScreen,
):
    current_note_id = None
    is_preview = False
    show_search = BooleanProperty(False)
    is_compact = BooleanProperty(False)

    # NOTE: every key below was checked against the actual ids in
    # app.kv's <NoteEditorScreen>: rule. header_bar/title_bar/
    # decrease_font_button/increase_font_button/cycle_font_button were
    # wrong (the real ids are top_bar/title_field_container/
    # font_decrease_button/font_increase_button/font_cycle_button) --
    # fixed below. The nine formatting-toolbar entries (bold_button,
    # italic_button, underline_button, highlight_button, align_*,
    # font_* aside from the three above) have been REMOVED entirely --
    # those ids now live inside FormattingToolbar's own self.ids
    # (it's a separate widget class), so they were never reachable
    # from here and did nothing. See on_theme_applied below for how
    # the toolbar is themed instead.
    THEME_MAP = {
        "self":                ("md_bg_color", BACKGROUND),
        "back_button":         ("icon_color", TEXT_PRIMARY),
        "header_label":        ("text_color", TEXT_PRIMARY),
        "search_button":       ("icon_color", TEXT_PRIMARY),
        "image_button":        ("icon_color", TEXT_PRIMARY),
        "preview_button":      ("icon_color", TEXT_PRIMARY),
        "export_button":       ("icon_color", TEXT_PRIMARY),
        "duplicate_button":    ("icon_color", TEXT_PRIMARY),
        "delete_button":       ("icon_color", TEXT_PRIMARY),
        "save_button":         ("icon_color", TEXT_PRIMARY),
        "title_field_container": ("md_bg_color", BACKGROUND),
        "word_count_label":    ("text_color", TEXT_SECONDARY),
        "search_card":         ("md_bg_color", CARD_SECONDARY),
        "search_match_label":  ("text_color", TEXT_PRIMARY),
        "search_prev_button":  ("icon_color", TEXT_PRIMARY),
        "search_next_button":  ("icon_color", TEXT_PRIMARY),
        "search_close_button": ("icon_color", TEXT_PRIMARY),
        "content_card":        ("md_bg_color", CARD_PRIMARY),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._preview_content = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
        self._preview_content.bind(minimum_height=self._preview_content.setter("height"))
        self._preview_scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self._preview_scroll.add_widget(self._preview_content)

        # Formatting selection tracking (FormattingMixin)
        self._last_selection = None
        # NOTE: deliberately not binding on_kv_post here -- it fires
        # DURING super().__init__() above, before a bind placed here
        # would ever run. Overriding the method below is correct.
        # Category assignment (CategoryMixin)
        self._current_category_id = None

        # Undo/redo history (UndoRedoMixin)
        self._undo_stack = []
        self._redo_stack = []
        self._suppress_history = False
        self._history_debounce_event = None

        # In-note search state (SearchMixin)
        self._search_matches = []
        self._search_match_index = -1

        # Hyperlink state (HyperlinkMixin)
        self._preview_link_map = {}
        self._link_ref_counter = 0
        self._pending_link_selection = None
        self._editing_link_span = None  # (start, end) of an existing {{link:...}} marker being edited, or None

        # Text color state (TextColorMixin)
        self._pending_color_selection = None  # (kind, selected, start, end) or None -- kind is "edit" or "wrap"
        self._active_color_modal = None
        # Snapshot of (title, content, font, size, align, category) at
        # the moment a note was loaded or last saved -- compared
        # against the live state to detect unsaved changes on exit.
        self._loaded_snapshot = None

    def on_kv_post(self, base_widget):
        super().on_kv_post(base_widget)
        self.ids.content_field.bind(selection_text=self._track_selection)
        self.ids.content_field.bind(text=self._on_content_text_changed)
        # Keyboard avoidance is now handled at the Window level via
        # Window.softinput_mode = "below_target" (set in main.py) --
        # Window.keyboard_height is documented to always return 0
        # with SDL2 on Android, so the previous approach built on it
        # never actually worked. What's left here just keeps the
        # ScrollView itself scrolled to the cursor's row -- a plain
        # layout-containment check, no keyboard math involved.
        self.ids.content_field.bind(cursor_pos=self._scroll_to_cursor)
        # Retrigger once the field's own height actually settles --
        # TextInput recomputes minimum_height via its own internally
        # scheduled refresh, which can land a frame or two after
        # cursor_pos changes.
        self.ids.content_field.bind(height=self._scroll_to_cursor)


    def _current_snapshot(self):
        field = self.ids.content_field
        return (
            self.ids.title_field.text,
            field.text,
            field.font_name,
            field.font_size,
            field.halign,
            self._current_category_id,
        )

    def _has_unsaved_changes(self):
        if self._loaded_snapshot is None:
            return False
        return self._current_snapshot() != self._loaded_snapshot

    def on_theme_applied(self):
        field = self.ids.get("content_field")
        if field is not None:
            field.background_color = theme_manager.get_color(CARD_PRIMARY)
            field.foreground_color = theme_manager.get_color(TEXT_PRIMARY)
            field.hint_text_color = theme_manager.get_color(TEXT_SECONDARY)
            field.cursor_color = theme_manager.get_color(TEXT_PRIMARY)
            field.selection_color = self._faded(theme_manager.get_color(ACCENT), 0.4)

        # search_query_field is also a plain TextInput -- same
        # multi-property situation as content_field, so THEME_MAP
        # (one property per id) can't reach it either. background_color
        # deliberately stays transparent (0, 0, 0, 0) per the .kv
        # comment -- that's intentional layering, not a missed color.
        search_field = self.ids.get("search_query_field")
        if search_field is not None:
            search_field.foreground_color = theme_manager.get_color(TEXT_PRIMARY)
            search_field.hint_text_color = theme_manager.get_color(TEXT_SECONDARY)
            search_field.cursor_color = theme_manager.get_color(TEXT_PRIMARY)

        # FormattingToolbar is its own widget class with its own
        # self.ids -- THEME_MAP can never reach into it, the same way
        # THEME_MAP can't reach DashboardTile's or NoteCard's internal
        # ids. It needs its own apply_theme() method (mirroring that
        # same pattern) before this actually does anything -- the
        # hasattr guard means this is safe to leave in now and have it
        # start working the moment that method exists, same as Home's
        # dashboard-tile loop.
        toolbar = self.ids.get("formatting_toolbar")
        if toolbar is not None and hasattr(toolbar, "apply_theme"):
            toolbar.apply_theme()

        self._refresh_preview_if_active()

    def _reset_editing_state(self):
        # Called whenever a note (or a blank new note) is loaded --
        # starts a fresh undo history and clears any leftover search
        # query from whatever note was open before this one. Pulled
        # into one shared method since on_enter and load_note used to
        # each repeat this block separately.
        field = self.ids.content_field
        if self._history_debounce_event:
            self._history_debounce_event.cancel()
            self._history_debounce_event = None
        self._undo_stack = [field.text]
        self._redo_stack = []
        self._update_word_count(field.text)
        self._reset_search_state()

    def on_enter(self):
        self.is_preview = False
        if self.current_note_id is not None:
            self.load_note(self.current_note_id)
        else:
            field = self.ids.content_field
            self.ids.title_field.text = ""
            field.text = ""
            field.font_name = DEFAULT_FONT_NAME
            field.font_size = DEFAULT_FONT_SIZE
            field.halign = DEFAULT_ALIGN
            self._set_current_category(None)
            self._reset_editing_state()
            self._loaded_snapshot = self._current_snapshot()
        self.show_edit_mode()

    def load_note(self, note_id):
        note = get_notes_by_id(note_id)
        field = self.ids.content_field

        if note is None:
            self.ids.title_field.text = ""
            field.text = ""
            field.font_name = DEFAULT_FONT_NAME
            field.font_size = DEFAULT_FONT_SIZE
            field.halign = DEFAULT_ALIGN
        else:
            self.ids.title_field.text = note[2]
            stored_content = note[3] or ""
            font_name, font_size, halign, visible_content = parse_note_meta(stored_content)
            field.text = visible_content
            field.font_name = font_name
            field.font_size = font_size
            field.halign = halign

        self._set_current_category(note[8] if note is not None else None)
        self._reset_editing_state()
        self._loaded_snapshot = self._current_snapshot()

    def toggle_preview(self):
        self.is_preview = not self.is_preview
        if self.is_preview:
            self.show_preview_mode()
        else:
            self.show_edit_mode()

    def show_edit_mode(self):
        container = self.ids.content_container
        if self._preview_scroll.parent is not None:
            container.remove_widget(self._preview_scroll)
        if self.ids.content_scroll.parent is None:
            container.add_widget(self.ids.content_scroll)

        # Explicitly pin the view to the top on entry. Without this,
        # the guaranteed keyboard-space spacer (which always adds a
        # little extra scrollable height, even with the keyboard
        # closed) can leave the initial view not quite at the top by
        # default, clipping the first line / hint text. Scheduled a
        # frame later so it runs after this frame's height/layout
        # changes actually apply -- same reasoning as _scroll_to_cursor.
        Clock.schedule_once(self._reset_scroll_to_top, 0)

    def _reset_scroll_to_top(self, dt):
        scroll_view = self.ids.get("content_scroll")
        if scroll_view is not None:
            scroll_view.scroll_y = 1  # 1 = top of content, per Kivy's ScrollView convention

    def show_preview_mode(self):
        raw = self.ids.content_field.text
        self._preview_content.clear_widgets()
        self._preview_link_map = {}
        self._link_ref_counter = 0

        parts = IMAGE_TOKEN_PATTERN.split(raw)

        for i, part in enumerate(parts):
            if i % 2 == 1:
                align = self.ids.content_field.halign
                if align == "center":
                    img_pos_hint = {"center_x": 0.5}
                elif align == "right":
                    img_pos_hint = {"right": 1}
                else:
                    img_pos_hint = {"x": 0}

                img = Image(
                    source=part, size_hint=(None, None), size=(dp(220), dp(220)),
                    pos_hint=img_pos_hint, allow_stretch=True,
                )
                self._preview_content.add_widget(img)
            elif part.strip():
                label = Label(
                    text=self._convert_part_for_preview(part),
                    markup=True, size_hint_y=None, color=(0.29, 0.20, 0.15, 1),
                    halign=self.ids.content_field.halign, valign="top",
                    font_size=self.ids.content_field.font_size,
                    font_name=self.ids.content_field.font_name,
                )
                label.bind(width=lambda inst, val: setattr(inst, "text_size", (val, None)))
                label.bind(texture_size=lambda inst, val: setattr(inst, "height", val[1]))
                label.bind(on_ref_press=self._on_preview_link_pressed)
                self._preview_content.add_widget(label)


        container = self.ids.content_container
        if self.ids.content_scroll.parent is not None:
            container.remove_widget(self.ids.content_scroll)
        if self._preview_scroll.parent is None:
            container.add_widget(self._preview_scroll)

    def save_note(self):
        title = self.ids.title_field.text.strip()
        content = self.ids.content_field.text.strip()

        if not title:
            print("Please add a title")
            return

        if self._history_debounce_event:
            self._history_debounce_event.cancel()
            self._history_debounce_event = None
        self._push_history_snapshot(0)

        field = self.ids.content_field
        meta = build_note_meta(field.font_name, field.font_size, field.halign)
        content_to_store = meta + content

        if self.current_note_id is None:
            create_notes(DEFAULT_NOTEBOOK_ID, title, content_to_store)
        else:
            update_notes(self.current_note_id, title, content_to_store)
            self._cleanup_removed_attachments(content)

        self._loaded_snapshot = self._current_snapshot()
        self.go_back()

    def duplicate_note(self):
        if self.current_note_id is not None:
            duplicate_notes(self.current_note_id)
        self.go_back()

    def go_back(self):
        # Actual navigation, used once we've confirmed it's OK to
        # leave (either nothing changed, or the user chose Discard).
        self.ids.title_field.text = ""
        self.ids.content_field.text = ""
        self.current_note_id = None
        self.is_preview = False
        self.manager.current = "notes"

    def request_go_back(self):
        # Called from the back button in KV instead of go_back()
        # directly -- checks for unsaved changes first.
        if self._has_unsaved_changes():
            self._show_unsaved_changes_prompt()
        else:
            self.go_back()

    def _show_unsaved_changes_prompt(self):
        card = make_safe_card(MDCard,
            orientation="vertical", padding=dp(20), spacing=dp(16),
            radius=[16], size_hint=(None, None), size=(dp(340), dp(180)),
            theme_bg_color="Custom", md_bg_color=(0.97, 0.95, 0.90, 1),
        )

        warning_label = MDLabel(
            text="You have unsaved changes. Save before leaving?",
            halign="center", theme_text_color="Custom", size_hint_y=None,
        )
        warning_label.bind(width=lambda inst, val: setattr(inst, "text_size", (val, None)))
        warning_label.bind(texture_size=lambda inst, val: setattr(inst, "height", val[1]))
        card.add_widget(warning_label)

        button_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(48))

        # size_hint_x=1 on all three forces them to share the row's
        # fixed width equally instead of each sizing to its own label
        # -- without this, three buttons' combined natural width
        # exceeded the card's available space and Save got pushed
        # past the right edge instead of shrinking to fit.
        cancel_button = MDButton(MDButtonText(text="Cancel"), style="outlined", size_hint_x=1)
        cancel_button.bind(on_release=lambda *_: modal.dismiss())

        discard_button = MDButton(MDButtonText(text="Discard"), style="outlined", size_hint_x=1)
        def _on_discard(*_):
            modal.dismiss()
            self.go_back()
        discard_button.bind(on_release=_on_discard)

        save_button = MDButton(MDButtonText(text="Save"), style="filled", size_hint_x=1)
        def _on_save(*_):
            modal.dismiss()
            self.save_note()
        save_button.bind(on_release=_on_save)

        button_row.add_widget(cancel_button)
        button_row.add_widget(discard_button)
        button_row.add_widget(save_button)
        card.add_widget(button_row)

        modal = ModalView(
            size_hint=(None, None), size=(dp(340), dp(180)),
            auto_dismiss=True, background_color=(0, 0, 0, 0.5),
        )
        modal.add_widget(card)
        modal.open()

    def _refresh_preview_if_active(self):
        if self.is_preview:
            self.show_preview_mode()

    def _scroll_to_cursor(self, *args):
        # Runs one frame later, after the height changes above have
        # actually taken effect -- reading positions in the same
        # frame as a layout change can use stale numbers.
        Clock.schedule_once(self._do_scroll_to_cursor, 0)

    def _do_scroll_to_cursor(self, dt):
        scroll_view = self.ids.get("content_scroll")
        field = self.ids.get("content_field")
        if scroll_view is None or field is None:
            return

        # Cursor position and the scroll viewport's OWN bottom edge,
        # both converted to real window pixels via to_window() -- this
        # reflects whatever transforms are active in the widget tree,
        # including any panning from Window.softinput_mode, so it
        # stays correct without needing to know the keyboard's height.
        _, cursor_window_y = field.to_window(*field.cursor_pos)
        _, viewport_bottom_y = scroll_view.to_window(0, 0)
        visible_bottom = viewport_bottom_y + dp(12)

        content_widget = scroll_view.children[0] if scroll_view.children else None
        content_height = content_widget.height if content_widget else scroll_view.height

        # TEMP DEBUG -- remove once scrolling is confirmed correct on
        # device. Visible via `adb logcat` (filter for SCROLL_DEBUG).
        print(f"SCROLL_DEBUG cursor_y={cursor_window_y:.0f} visible_bottom={visible_bottom:.0f} "
              f"field_h={field.height:.0f} content_h={content_height:.0f} "
              f"viewport_h={scroll_view.height:.0f} scroll_y={scroll_view.scroll_y:.3f}")

        if cursor_window_y >= visible_bottom:
            return  # Cursor is already visible -- nothing to do.

        shortfall = visible_bottom - cursor_window_y
        scrollable_range = max(content_height - scroll_view.height, 1)
        scroll_view.scroll_y = max(0, scroll_view.scroll_y - shortfall / scrollable_range)
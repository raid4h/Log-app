# screens/editor/category_mixin.py
# Lets the user assign a category to a note while editing it, via a
# small pill under the title that opens a picker popup -- pick an
# existing category, create a new one, or clear it.

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.modalview import ModalView
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.textfield import MDTextField, MDTextFieldHintText
from kivymd.uix.boxlayout import MDBoxLayout
from kivy.uix.anchorlayout import AnchorLayout

from screens.editor.paths import DEFAULT_NOTEBOOK_ID
from screens.category_helpers import (
    list_categories, get_category, make_category, assign_category,
    category_color_rgba, CATEGORY_COLOR_PRESETS, delete_category, rename_category,
)
from screens.safe_card import make_safe_card
from database.notes_queries import create_notes


class _ColorSwatch(MDCard):
    # No ButtonBehavior here -- MDCard already has its own built-in
    # tap handling (same reason DashboardTile/SmallTile respond to
    # on_release with no ButtonBehavior added). Combining the two
    # causes a Python MRO conflict, which is what actually crashed.
    pass


class CategoryPillButton(ButtonBehavior, MDBoxLayout):
    # The small "+ Add category" / "[Category Name]" pill under the
    # title field -- tapping it opens the picker. MDBoxLayout-based,
    # not MDCard-based, so ButtonBehavior is safe here (no MRO
    # conflict like the MDCard-based widgets in this file had).
    pass


class _CategoryRow(ButtonBehavior, MDBoxLayout):
    pass



class CategoryMixin:
    """Requires: self.ids.category_pill_label, self.ids.title_field,
    self.ids.content_field, self.current_note_id."""

    def _set_current_category(self, category_id):
        self._current_category_id = category_id
        label = self.ids.get("category_pill_label")
        if label is None:
            return
        category = get_category(category_id)
        label.text = category[1] if category is not None else "+ Add category"

    def _ensure_note_exists(self):
        # Same pattern already used in pick_image() -- a category
        # can't be assigned to a note that doesn't have a database row
        # yet, so create one immediately if this is a brand-new note.
        if self.current_note_id is None:
            title = self.ids.title_field.text.strip() or "Untitled"
            content = self.ids.content_field.text
            self.current_note_id = create_notes(DEFAULT_NOTEBOOK_ID, title, content)
            if not self.ids.title_field.text.strip():
                self.ids.title_field.text = title

    def open_category_picker(self):
        row_height = dp(46)
        entries = list_categories()
        menu_height = row_height * (len(entries) + 2) + dp(16)
        menu_width = dp(270)  # widened slightly to fit the new delete icon

        card = make_safe_card(
            MDCard,
            orientation="vertical", padding=(dp(4), dp(8)),
            size_hint=(None, None), size=(menu_width, menu_height),
            radius=[16], elevation=4, theme_bg_color="Custom",
            md_bg_color=(0.97, 0.95, 0.90, 1),
        )
        modal = ModalView(
            size_hint=(None, None), size=(menu_width, menu_height),
            auto_dismiss=True, background_color=(0, 0, 0, 0.4),
        )

        def add_row(label_text, color_rgba, callback, category_id=None):
            row = _CategoryRow(
                orientation="horizontal", size_hint_y=None, height=row_height,
                padding=(dp(12), 0), spacing=dp(10),
            )
            dot = make_safe_card(MDCard,
                size_hint=(None, None), size=(dp(16), dp(16)),
                radius=[8], theme_bg_color="Custom", md_bg_color=color_rgba, elevation=0,
                # Fixed-size children in a BoxLayout sit flush at the
                # bottom by default -- this centers the dot against
                # the taller label next to it.
                pos_hint={"center_y": 0.5},
            )
            label = MDLabel(
                text=label_text, theme_text_color="Custom",
                text_color=(0.29, 0.20, 0.15, 1), valign="middle",
            )
            row.add_widget(dot)
            row.add_widget(label)

            # Only real categories get a delete icon -- "No category"
            # and "+ New category" aren't deletable rows.
            if category_id is not None:
                edit_button = MDIconButton(
                    icon="pencil-outline",
                    theme_icon_color="Custom",
                    icon_color=(0.29, 0.20, 0.15, 1),
                    size_hint=(None, None), size=(dp(32), dp(32)),
                    pos_hint={"center_y": 0.5},
                )
                edit_button.bind(
                    on_release=lambda inst, cid=category_id, name=label_text, col=color_rgba:
                        self._open_rename_category_popup(cid, name, col, modal)
                )
                row.add_widget(edit_button)

                delete_button = MDIconButton(
                    icon="trash-can-outline",
                    theme_icon_color="Custom",
                    icon_color=(0.29, 0.20, 0.15, 1),
                    size_hint=(None, None), size=(dp(32), dp(32)),
                    pos_hint={"center_y": 0.5},
                )
                delete_button.bind(
                    on_release=lambda inst, cid=category_id, name=label_text:
                        self._prompt_delete_category(cid, name, modal)
                )
                row.add_widget(delete_button)

            def _on_release(*_):
                modal.dismiss()
                callback()
            row.bind(on_release=_on_release)
            card.add_widget(row)

        add_row("No category", (0.85, 0.85, 0.85, 1), lambda: self._choose_category(None))
        for cat in entries:
            cat_id, name, color_hex = cat[0], cat[1], cat[2]
            add_row(
                name, category_color_rgba(color_hex),
                lambda cid=cat_id: self._choose_category(cid),
                category_id=cat_id,
            )
        add_row("+ New category", (0.72, 0.79, 0.54, 1), self._open_new_category_popup)

        modal.add_widget(card)
        modal.open()

    def _prompt_delete_category(self, category_id, category_name, parent_modal):
        card = make_safe_card(MDCard,
            orientation="vertical", padding=dp(20), spacing=dp(16),
            radius=[16], size_hint=(None, None), size=(dp(300), dp(170)),
            theme_bg_color="Custom", md_bg_color=(0.97, 0.95, 0.90, 1),
        )
        warning_label = MDLabel(
            text=f"Delete category \"{category_name}\"? Notes using it will become uncategorized.",
            halign="center", theme_text_color="Custom", size_hint_y=None,
        )
        warning_label.bind(width=lambda inst, val: setattr(inst, "text_size", (val, None)))
        warning_label.bind(texture_size=lambda inst, val: setattr(inst, "height", val[1]))
        card.add_widget(warning_label)

        button_row = BoxLayout(orientation="horizontal", spacing=dp(12), size_hint_y=None, height=dp(48))
        cancel_button = MDButton(MDButtonText(text="Cancel"), style="outlined")
        cancel_button.bind(on_release=lambda *_: confirm_modal.dismiss())
        confirm_button = MDButton(MDButtonText(text="Delete"), style="filled")

        def _on_confirm(*_):
            confirm_modal.dismiss()
            parent_modal.dismiss()
            delete_category(category_id)

            # If the note currently open was using this category,
            # reset its pill back to "+ Add category" immediately.
            if self._current_category_id == category_id:
                self._set_current_category(None)

            # Refresh the notes list too, so its filter chips and any
            # colored stripes stop referencing the deleted category.
            from kivymd.app import MDApp
            app = MDApp.get_running_app()
            notes_screen = app.root.get_screen("notes")
            if hasattr(notes_screen, "load_notes"):
                notes_screen.load_notes()

        confirm_button.bind(on_release=_on_confirm)
        button_row.add_widget(cancel_button)
        button_row.add_widget(confirm_button)
        card.add_widget(button_row)

        confirm_modal = ModalView(
            size_hint=(None, None), size=(dp(300), dp(170)),
            auto_dismiss=True, background_color=(0, 0, 0, 0.5),
        )
        confirm_modal.add_widget(card)
        confirm_modal.open()

    def _choose_category(self, category_id):
        self._ensure_note_exists()
        assign_category(self.current_note_id, category_id)
        self._set_current_category(category_id)

    def _open_new_category_popup(self):
        card = make_safe_card(MDCard,
            orientation="vertical", padding=dp(20), spacing=dp(14),
            radius=[16], size_hint=(None, None), size=(dp(300), dp(260)),
            ripple_behavior=True,
        )

        prompt = MDLabel(
            text="New category name:", halign="center",
            theme_text_color="Custom", size_hint_y=None, height=dp(24),
        )
        card.add_widget(prompt)

        name_field = MDTextField(size_hint_y=None, height=dp(48))
        name_field.add_widget(MDTextFieldHintText(text="e.g. Work, Personal"))
        card.add_widget(name_field)

        # Note: no visual highlight on the currently-selected swatch --
        # kept deliberately simple to avoid relying on an untested
        # dynamic-border property. First preset is used unless another
        # is tapped.
        swatch_row = BoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(44))
        selected_color = {"value": CATEGORY_COLOR_PRESETS[0][1]}
        ring_widgets = []

        def _select_swatch(index, color):
            selected_color["value"] = color
            # Only ONE ring is ever visible at a time -- the rest go
            # transparent -- so it's always clear which color is
            # currently chosen before hitting Create.
            for i, ring in enumerate(ring_widgets):
                ring.md_bg_color = (0.29, 0.20, 0.15, 1) if i == index else (0, 0, 0, 0)

        for index, (_, color) in enumerate(CATEGORY_COLOR_PRESETS):
            ring = make_safe_card(MDCard,
                size_hint=(None, None), size=(dp(38), dp(38)),
                radius=[19], elevation=0, theme_bg_color="Custom",
                md_bg_color=(0.29, 0.20, 0.15, 1) if index == 0 else (0, 0, 0, 0),
            )
            inner_wrap = AnchorLayout(anchor_x="center", anchor_y="center")
            swatch = make_safe_card(_ColorSwatch,
                size_hint=(None, None), size=(dp(28), dp(28)),
                radius=[14], theme_bg_color="Custom", md_bg_color=color, elevation=0,
                ripple_behavior=True,
            )
            swatch.bind(on_release=lambda inst, i=index, c=color: _select_swatch(i, c))
            inner_wrap.add_widget(swatch)
            ring.add_widget(inner_wrap)
            ring_widgets.append(ring)
            swatch_row.add_widget(ring)
        card.add_widget(swatch_row)

        button_row = BoxLayout(orientation="horizontal", spacing=dp(12), size_hint_y=None, height=dp(48))
        cancel_button = MDButton(MDButtonText(text="Cancel"), style="outlined")
        cancel_button.bind(on_release=lambda *_: modal.dismiss())
        create_button = MDButton(MDButtonText(text="Create"), style="filled")

        def _on_create(*_):
            name = name_field.text.strip()
            if not name:
                return
            new_id = make_category(name, selected_color["value"])
            modal.dismiss()
            self._choose_category(new_id)

        create_button.bind(on_release=_on_create)
        button_row.add_widget(cancel_button)
        button_row.add_widget(create_button)
        card.add_widget(button_row)

        modal = ModalView(
            size_hint=(None, None), size=(dp(300), dp(260)),
            auto_dismiss=True, background_color=(0, 0, 0, 0.5),
        )
        modal.add_widget(card)
        modal.open()

    def _open_rename_category_popup(self, category_id, current_name, current_color, parent_modal):
        parent_modal.dismiss()

        card = make_safe_card(MDCard,
            orientation="vertical", padding=dp(20), spacing=dp(14),
            radius=[16], size_hint=(None, None), size=(dp(300), dp(260)),
            theme_bg_color="Custom", md_bg_color=(0.97, 0.95, 0.90, 1),
        )

        prompt = MDLabel(
            text="Rename category:", halign="center",
            theme_text_color="Custom", size_hint_y=None, height=dp(24),
        )
        card.add_widget(prompt)

        name_field = MDTextField(text=current_name, size_hint_y=None, height=dp(48))
        name_field.add_widget(MDTextFieldHintText(text="Category name"))
        card.add_widget(name_field)

        swatch_row = BoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(44))
        # Pre-selects whichever preset matches the category's current
        # color, if it's one of the presets -- falls back to keeping
        # the current (possibly custom) color if no exact match.
        selected_color = {"value": current_color}
        ring_widgets = []

        def _select_swatch(index, color):
            selected_color["value"] = color
            for i, ring in enumerate(ring_widgets):
                ring.md_bg_color = (0.29, 0.20, 0.15, 1) if i == index else (0, 0, 0, 0)

        for index, (_, color) in enumerate(CATEGORY_COLOR_PRESETS):
            is_current = tuple(color) == tuple(current_color)
            ring = make_safe_card(MDCard,
                size_hint=(None, None), size=(dp(38), dp(38)),
                radius=[19], elevation=0, theme_bg_color="Custom",
                md_bg_color=(0.29, 0.20, 0.15, 1) if is_current else (0, 0, 0, 0),
            )
            inner_wrap = AnchorLayout(anchor_x="center", anchor_y="center")
            swatch = make_safe_card(_ColorSwatch,
                size_hint=(None, None), size=(dp(28), dp(28)),
                radius=[14], theme_bg_color="Custom", md_bg_color=color, elevation=0,
                ripple_behavior=True,
            )
            swatch.bind(on_release=lambda inst, i=index, c=color: _select_swatch(i, c))
            inner_wrap.add_widget(swatch)
            ring.add_widget(inner_wrap)
            ring_widgets.append(ring)
            swatch_row.add_widget(ring)
        card.add_widget(swatch_row)

        button_row = BoxLayout(orientation="horizontal", spacing=dp(12), size_hint_y=None, height=dp(48))
        cancel_button = MDButton(MDButtonText(text="Cancel"), style="outlined")
        cancel_button.bind(on_release=lambda *_: modal.dismiss())
        save_button = MDButton(MDButtonText(text="Save"), style="filled")

        def _on_save(*_):
            new_name = name_field.text.strip()
            if not new_name:
                return
            rename_category(category_id, new_name, selected_color["value"])
            modal.dismiss()

            # If this category is currently assigned to the open note,
            # refresh the pill to show the new name immediately.
            if self._current_category_id == category_id:
                self._set_current_category(category_id)

            from kivymd.app import MDApp
            app = MDApp.get_running_app()
            notes_screen = app.root.get_screen("notes")
            if hasattr(notes_screen, "load_notes"):
                notes_screen.load_notes()

        save_button.bind(on_release=_on_save)
        button_row.add_widget(cancel_button)
        button_row.add_widget(save_button)
        card.add_widget(button_row)

        modal = ModalView(
            size_hint=(None, None), size=(dp(300), dp(260)),
            auto_dismiss=True, background_color=(0, 0, 0, 0.5),
        )
        modal.add_widget(card)
        modal.open()
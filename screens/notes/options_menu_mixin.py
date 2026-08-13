# screens/notes/options_menu_mixin.py
# The "..." dropdown menu: view mode toggle, sort options, select
# notes. Anchored to the options button's actual on-screen position.

from kivy.metrics import dp
from kivy.core.window import Window
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.modalview import ModalView
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDIconButton

from screens.safe_card import make_safe_card


class _MenuRow(ButtonBehavior, MDBoxLayout):
    # A single tappable row inside the options menu.
    pass


class OptionsMenuMixin:
    """Requires: self.ids.options_button, self.view_mode,
    self.toggle_view_mode(), self.sort_notes(), self.toggle_selection_mode()."""

    def open_options_menu(self):
        button = self.ids.options_button

        button_x, button_y = button.to_window(0, 0)

        menu_width = dp(220)
        row_height = dp(46)
        # Extra space above the first row and below the last one, so
        # "View as Grid" doesn't sit flush against the top edge of the
        # rounded card.
        top_padding = dp(10)
        bottom_padding = dp(6)
        menu_height = (row_height * 4) + top_padding + bottom_padding

        target_x = min(button_x + button.width - menu_width, Window.width - menu_width - dp(8))
        target_x = max(target_x, dp(8))
        target_y = max(button_y - menu_height - dp(4), dp(8))

        card = make_safe_card(MDCard,
            orientation="vertical",
            size_hint=(None, None),
            size=(menu_width, menu_height),
            padding=(dp(4), top_padding, dp(4), bottom_padding),
            radius=[14],
            elevation=4,
            md_bg_color=(0.97, 0.95, 0.90, 1),
        )

        modal = ModalView(
            size_hint=(None, None),
            size=(menu_width, menu_height),
            pos=(target_x, target_y),
            auto_dismiss=True,
            background_color=(0, 0, 0, 0),
        )

        def add_row(icon_name, label_text, callback):
            row = _MenuRow(
                orientation="horizontal", size_hint_y=None, height=row_height,
                padding=(dp(10), 0), spacing=dp(10),
            )
            icon = MDIconButton(
                icon=icon_name, disabled=True,
                theme_icon_color="Custom", icon_color=(0.29, 0.20, 0.15, 1),
            )
            label = MDLabel(
                text=label_text, theme_text_color="Custom",
                text_color=(0.29, 0.20, 0.15, 1), valign="middle",
            )
            row.add_widget(icon)
            row.add_widget(label)

            def _on_release(*_):
                modal.dismiss()
                callback()
            row.bind(on_release=_on_release)
            card.add_widget(row)

        view_toggle_icon = "view-list" if self.view_mode == "grid" else "view-grid"
        view_toggle_label = "View as List" if self.view_mode == "grid" else "View as Grid"
        add_row(view_toggle_icon, view_toggle_label, self.toggle_view_mode)
        add_row("sort-alphabetical-ascending", "Sort Alphabetically", lambda: self.sort_notes("title"))
        add_row("sort-calendar-ascending", "Sort by Date", lambda: self.sort_notes("date"))
        add_row("checkbox-multiple-marked-outline", "Select Notes", self.toggle_selection_mode)

        modal.add_widget(card)
        modal.open()
from kivymd.uix.screen import MDScreen
from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText
from kivy.app import App

from theme.theme_manager import theme_manager
from theme.themed_screen import ThemedScreenMixin
from theme.palettes import (
    BACKGROUND,
    CARD_PRIMARY,
    CARD_SECONDARY,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    BUTTON,
    ACCENT,
)


class SettingsScreen(ThemedScreenMixin, MDScreen):

    THEME_MAP = {
        "self":           ("md_bg_color", BACKGROUND),
        "title_label":    ("text_color", TEXT_PRIMARY),
        "subtitle_label": ("text_color", TEXT_SECONDARY),
        "back_button":    ("icon_color", TEXT_PRIMARY),

        # Theme
        "theme_section_label": ("text_color", ACCENT),
        "default_button":    ("md_bg_color", BUTTON),
        "dark_button":       ("md_bg_color", BUTTON),
        "floral_button":     ("md_bg_color", BUTTON),
        "matcha_button":     ("md_bg_color", BUTTON),
        "monochrome_button": ("md_bg_color", BUTTON),

        # Backup & Restore -- Export/Import only. App is fully offline;
        # no Google account, no cloud backup/restore.
        "backup_card":          ("md_bg_color", CARD_PRIMARY),
        "backup_section_label": ("text_color", ACCENT),
        "export_row_label":     ("text_color", TEXT_PRIMARY),
        "import_row_label":     ("text_color", TEXT_PRIMARY),

        # Privacy
        "privacy_card":          ("md_bg_color", CARD_SECONDARY),
        "privacy_section_label": ("text_color", ACCENT),
        "privacy_row_label":     ("text_color", TEXT_PRIMARY),
        "privacy_row_subtitle":  ("text_color", TEXT_SECONDARY),

        # Notifications
        "notifications_card":          ("md_bg_color", CARD_PRIMARY),
        "notifications_section_label": ("text_color", ACCENT),
        "notifications_row_label":     ("text_color", TEXT_PRIMARY),

        # About
        "about_card":                ("md_bg_color", CARD_SECONDARY),
        "about_section_label":       ("text_color", ACCENT),
        "privacy_policy_row_label":  ("text_color", TEXT_PRIMARY),
        "footer_label":              ("text_color", TEXT_SECONDARY),

        # chevrons (row-tap affordance)
        "export_chevron":         ("icon_color", TEXT_SECONDARY),
        "import_chevron":         ("icon_color", TEXT_SECONDARY),
        "privacy_chevron":        ("icon_color", TEXT_SECONDARY),
        "privacy_policy_chevron": ("icon_color", TEXT_SECONDARY),
    }

    # ── theme ──
    def set_default_theme(self):
        theme_manager.set_default_theme()

    def set_dark_theme(self):
        theme_manager.set_dark_theme()

    def set_floral_theme(self):
        theme_manager.set_floral_theme()

    def set_monochrome_theme(self):
        theme_manager.set_monochrome_theme()

    def set_matcha_theme(self):
        theme_manager.set_matcha_theme()

    # ── small helper: user-visible feedback, replaces the old
    # print()-only callbacks. A snackbar is used rather than a dialog
    # since export/import success or failure doesn't need the user to
    # dismiss anything -- it's a brief confirmation, not a decision. ──
    def _show_snackbar(self, message):
        MDSnackbar(
            MDSnackbarText(text=message),
            y="24dp",
            pos_hint={"center_x": 0.5},
            size_hint_x=0.9,
        ).open()

    # ── backup: export/import only (offline app, no cloud) ──
    def export_to_file(self):
        # NOTE: the exported file is PLAIN, UNENCRYPTED JSON -- anyone
        # with access to it can read every note it contains.
        from services.manual_export import export_backup_to_file, ExportCancelled

        def on_success(file_path):
            self._show_snackbar("Backup exported successfully.")

        def on_error(exc):
            if isinstance(exc, ExportCancelled):
                # User just closed the picker -- not a real error,
                # nothing worth interrupting them about.
                return
            self._show_snackbar("Export failed. Please try again.")

        export_backup_to_file(on_success, on_error)

    def import_from_file(self):
        from services.manual_export import import_backup_from_file, ImportCancelled
        from services.restore_engine import RestoreError

        def on_success():
            self._show_snackbar("Backup imported successfully.")
            # TODO: consider refreshing/navigating away from any
            # screen currently showing now-stale data (e.g. if the
            # user imports while sitting on the Notes list).

        def on_error(exc):
            if isinstance(exc, ImportCancelled):
                return
            if isinstance(exc, RestoreError):
                self._show_snackbar(str(exc))
            else:
                self._show_snackbar("Import failed. Please try again.")

        import_backup_from_file(on_success, on_error)

    # ── privacy ──
    def open_privacy_settings(self):
        App.get_running_app().root.current = "privacy_settings"

    # ── notifications ──
    def toggle_notifications(self):
        pass

    # ── about ──
    def open_privacy_policy(self):
        App.get_running_app().root.current = "privacy_policy"

    # ── navigation ──
    def go_back(self):
        App.get_running_app().root.current = "home"
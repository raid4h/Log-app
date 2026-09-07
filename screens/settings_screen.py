from kivymd.uix.screen import MDScreen
from kivy.uix.modalview import ModalView
from kivy.uix.label import Label
from kivy.graphics import Color, RoundedRectangle
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.utils import get_color_from_hex
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


def theme_rgba(token):
    return get_color_from_hex(theme_manager.get_color(token))


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

        # Backup & Restore -- folder-based export/import. App is fully
        # offline; no Google account, no cloud backup/restore.
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
    # print()-only callbacks.
    #
    # FIX: previously used MDSnackbar, which triggered a real crash on
    # this device (Mali-G57 GPU) -- MDSnackbar's ripple/background
    # behaviors create an off-screen Fbo (framebuffer object) for
    # their ripple animation, and that Fbo creation fails on some
    # Mali driver builds with "FBO Initialization failed: Incomplete
    # attachment (36054)" -- an uncaught exception that killed the
    # whole app right after a successful export/import. Confirmed via
    # on-device traceback: the crash happened in
    # kivymd/uix/behaviors/ripple_behavior.py's init_fbos(), called
    # from MDSnackbar's own __init__ chain.
    #
    # Replaced with a plain ModalView + Label -- no MDCard, no ripple
    # behavior, no FBO of any kind, so this exact crash class can't
    # happen here. Auto-dismisses after 2 seconds, same "brief,
    # no-action-needed confirmation" feel as the snackbar it replaces.
    def _show_snackbar(self, message):
        modal = ModalView(
            size_hint=(0.85, None),
            height=dp(56),
            pos_hint={"center_x": 0.5, "y": 0.05},
            auto_dismiss=True,
            background_color=(0, 0, 0, 0),
        )

        label = Label(
            text=message,
            color=theme_rgba(TEXT_PRIMARY),
            halign="center",
            valign="middle",
        )
        label.bind(size=lambda inst, val: setattr(inst, "text_size", val))

        with modal.canvas.before:
            bg_color = Color(*theme_rgba(CARD_PRIMARY))
            bg_rect = RoundedRectangle(pos=modal.pos, size=modal.size, radius=[dp(12)])

        def _sync_bg(*_args):
            bg_rect.pos = modal.pos
            bg_rect.size = modal.size

        modal.bind(pos=_sync_bg, size=_sync_bg)

        modal.add_widget(label)
        modal.open()

        Clock.schedule_once(lambda dt: modal.dismiss(), 2)

    # ── backup: export/import as a FOLDER (backup.json + attachments/
    # subfolder with real copied image files) -- offline app, no
    # cloud. See services/manual_export.py for the actual folder I/O. ──
    def export_to_file(self):
        # NOTE: backup.json inside the exported folder is PLAIN,
        # UNENCRYPTED JSON -- anyone with access to it can read every
        # note it contains.
        from services.manual_export import export_backup_to_folder, ExportCancelled

        def on_success(folder_path):
            self._show_snackbar("Backup exported successfully.")

        def on_error(exc):
            if isinstance(exc, ExportCancelled):
                # User just closed the picker -- not a real error,
                # nothing worth interrupting them about.
                return
            self._show_snackbar("Export failed. Please try again.")

        export_backup_to_folder(on_success, on_error)

    def import_from_file(self):
        from services.manual_export import import_backup_from_folder, ImportCancelled
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

        import_backup_from_folder(on_success, on_error)

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
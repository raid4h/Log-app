# services/manual_export.py
#
# Wires Phase 1 (backup_builder) and Phase 2 (restore_engine) up to a
# plain file path the USER chooses themselves, via a native file
# picker -- no Google account, no network, involved at all. This is
# deliberately thin: almost everything it does is already implemented
# by the two services it calls.

import os

from plyer import filechooser

from services.backup_builder import build_backup_manifest, save_manifest_to_path
from services.restore_engine import restore_from_path, RestoreError


class ExportCancelled(Exception):
    """Raised when the user closes the file picker without choosing a location."""


class ImportCancelled(Exception):
    """Raised when the user closes the file picker without choosing a file."""


def export_backup_to_file(on_success, on_error):
    """
    Opens a native "Save As" dialog, and on confirmation, builds a
    fresh backup manifest and writes it to the chosen path.

    on_success(file_path) is called after a successful export.
    on_error(exception) is called if anything goes wrong, including
    the user cancelling the dialog (ExportCancelled).

    Callbacks are used here (rather than a return value) because the
    underlying plyer file picker is itself callback-based -- it opens
    a native OS dialog and reports back whenever the user finishes
    interacting with it, which may not be immediately.
    """
    cwd_before_picker = os.getcwd()

    def handle_selection(selection):
        os.chdir(cwd_before_picker)

        if not selection:
            on_error(ExportCancelled("Export cancelled -- no location chosen."))
            return

        destination_path = selection[0]
        if not destination_path.lower().endswith(".json"):
            destination_path += ".json"

        try:
            manifest = build_backup_manifest()
            save_manifest_to_path(manifest, destination_path)
        except Exception as exc:
            on_error(exc)
            return

        on_success(destination_path)

    filechooser.save_file(
        on_selection=handle_selection,
        filters=[["NoteNest Backup", "*.json"]],
        title="Export NoteNest Backup",
    )


def import_backup_from_file(on_success, on_error):
    """
    Opens a native "Open File" dialog, and on confirmation, restores
    the app's data from the chosen manifest file.

    on_success() is called after a successful restore.
    on_error(exception) is called if anything goes wrong -- including
    the user cancelling (ImportCancelled), the file being corrupted or
    from a newer app version (RestoreError, raised by restore_engine),
    or any other failure. In every error case, per restore_engine's
    own guarantee, the live database is left untouched.
    """
    cwd_before_picker = os.getcwd()

    def handle_selection(selection):
        os.chdir(cwd_before_picker)

        if not selection:
            on_error(ImportCancelled("Import cancelled -- no file chosen."))
            return

        source_path = selection[0]

        try:
            restore_from_path(source_path)
        except RestoreError as exc:
            on_error(exc)
            return
        except Exception as exc:
            on_error(exc)
            return

        on_success()

    filechooser.open_file(
        on_selection=handle_selection,
        filters=[["NoteNest Backup", "*.json"]],
        title="Import NoteNest Backup",
    )
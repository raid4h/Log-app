# services/manual_export.py
#
# Wires Phase 1 (backup_builder) and Phase 2 (restore_engine) up to a
# plain file path the USER chooses themselves, via a native file
# picker -- no Google account, no network, involved at all. This is
# deliberately thin: almost everything it does is already implemented
# by the two services it calls.
#
# NOTE on platform split for export:
# plyer's filechooser.save_file() has two genuinely different
# contracts depending on platform:
#   - Desktop/iOS: the callback kwarg is "on_selection" and it is
#     handed a list of chosen file paths, same shape as open_file().
#   - Android: the callback kwarg is "callback" (NOT "on_selection")
#     and it is handed an already-open java.io.FileOutputStream --
#     there is no path at all, because Android's Storage Access
#     Framework never exposes one to the app. You write bytes
#     directly into that stream instead of calling
#     save_manifest_to_path().
# Using the wrong kwarg name on Android causes plyer's
# AndroidFileChooser._save_file() to raise KeyError('callback')
# before the native picker even opens -- which is exactly the bug
# this file used to have.

import json
import os

from kivy.utils import platform

from plyer import filechooser

from services.backup_builder import (
    build_backup_manifest,
    save_manifest_to_path,
    manifest_to_json_bytes,
)
from services.restore_engine import restore_from_path, RestoreError


class ExportCancelled(Exception):
    """Raised when the user closes the file picker without choosing a location."""


class ImportCancelled(Exception):
    """Raised when the user closes the file picker without choosing a file."""


def export_backup_to_file(on_success, on_error):
    """
    Opens a native "Save As" dialog, and on confirmation, builds a
    fresh backup manifest and writes it to the chosen location.

    on_success(file_path) is called after a successful export.
    NOTE: on Android, file_path will always be None -- the Storage
    Access Framework never hands the app a real path, only a write
    stream. Callers displaying a success message should handle a
    None path gracefully (e.g. "Backup exported successfully" with
    no path shown) rather than assuming one is always present.

    on_error(exception) is called if anything goes wrong, including
    the user cancelling the dialog (ExportCancelled).

    Callbacks are used here (rather than a return value) because the
    underlying plyer file picker is itself callback-based -- it opens
    a native OS dialog and reports back whenever the user finishes
    interacting with it, which may not be immediately.
    """
    if platform == "android":
        _export_backup_android(on_success, on_error)
    else:
        _export_backup_desktop(on_success, on_error)


def _export_backup_desktop(on_success, on_error):
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


def _export_backup_android(on_success, on_error):
    def handle_save_stream(java_file_output_stream):
        try:
            manifest = build_backup_manifest()
            data = manifest_to_json_bytes(manifest)
            java_file_output_stream.write(data)
            java_file_output_stream.flush()
        except Exception as exc:
            on_error(exc)
            return

        # Android's SAF save flow never gives the app a usable path
        # or URI back -- only the write stream. Callers must not rely
        # on this being a real path.
        on_success(None)

    filechooser.save_file(
        callback=handle_save_stream,
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

    NOTE: unlike save_file(), plyer's open_file() has the SAME
    contract on every platform including Android -- "on_selection"
    kwarg, handed a list of real file paths. No platform split is
    needed here.
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
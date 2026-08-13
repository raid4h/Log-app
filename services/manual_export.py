# services/manual_export.py
#
# Wires Phase 1 (backup_builder) and Phase 2 (restore_engine) up to a
# plain file path the USER chooses themselves, via a native file
# picker -- no Google account, no network, involved at all. This is
# deliberately thin: almost everything it does is already implemented
# by the two services it calls.

import os
import traceback

from plyer import filechooser

from services.backup_builder import build_backup_manifest, save_manifest_to_path
from services.restore_engine import restore_from_path, RestoreError


# TEMP DEBUG: writes the full traceback of any export/import failure
# to a plain text file next to main.py, in addition to trying the
# console -- plyer's Windows file picker sometimes runs its callback
# on a background thread, which can make print() output easy to miss
# or lose in a terminal capture. Safe to remove once export/import
# are confirmed working end-to-end.
_DEBUG_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "backup_debug.log",
)


def _log_exception(context_label):
    try:
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n--- {context_label} ---\n")
            f.write(traceback.format_exc())
    except Exception:
        pass  # never let logging itself crash the app
    traceback.print_exc()


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
            _log_exception("EXPORT")
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
            # TEMP DEBUG: RestoreError is a deliberate, expected
            # rejection (bad checksum, too-new schema version) -- not
            # a crash -- but logging it here too means we can tell
            # THIS apart from a genuine unexpected exception below,
            # instead of guessing which branch actually fired.
            _log_exception(f"IMPORT (RestoreError: {exc})")
            on_error(exc)
            return
        except Exception as exc:
            _log_exception("IMPORT (unexpected exception)")
            on_error(exc)
            return

        on_success()

    filechooser.open_file(
        on_selection=handle_selection,
        filters=[["NoteNest Backup", "*.json"]],
        title="Import NoteNest Backup",
    )
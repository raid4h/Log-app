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
#
# NOTE on platform split for import:
# plyer's filechooser.open_file() has the SAME callback contract on
# every platform ("on_selection", a list of real file paths) -- but
# on Android, its INTERNAL URI-resolution code
# (plyer/platforms/android/filechooser.py, _handle_downloads_documents)
# assumes a picked document's id is always a plain integer. Newer
# Android versions (via the "Recent"/cross-app document view) can
# return an id like "msf:1000028553" instead -- a virtual/merged
# storage id -- which crashes plyer's own Long.parseLong() call on
# the Java side with a NumberFormatException, before this file's code
# ever runs. This is a bug inside plyer itself, not in this project.
# The fix is to bypass plyer entirely for Android's import path: open
# the system document picker directly via a raw Intent (the same
# pattern screens/editor/image_mixin.py already uses for the Photo
# Picker), and read the picked file's bytes ourselves through
# ContentResolver, instead of asking plyer to resolve a path for us.
# Desktop keeps using plyer's open_file() unchanged, since this bug
# is Android-specific.

import json
import os

from kivy.clock import Clock
from kivy.utils import platform

from plyer import filechooser

from services.backup_builder import (
    build_backup_manifest,
    save_manifest_to_path,
    manifest_to_json_bytes,
)
from services.restore_engine import restore_from_path, restore_from_manifest, RestoreError


# Arbitrary number Android uses to match the picker's result back to
# this specific request -- same technique as
# screens/editor/image_mixin.py's _ANDROID_PICK_IMAGE_REQUEST_CODE,
# just a different constant so the two don't collide if a result from
# one arrives while the other is still bound.
_ANDROID_PICK_BACKUP_REQUEST_CODE = 7532


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

    On Android, this bypasses plyer's open_file() entirely (see the
    module-level NOTE above) in favor of a raw system document picker
    intent, reading the picked file's bytes directly. On desktop,
    plyer's open_file() is used exactly as before -- unaffected by
    the Android-only bug this works around.
    """
    if platform == "android":
        _import_backup_android(on_success, on_error)
    else:
        _import_backup_desktop(on_success, on_error)


def _import_backup_desktop(on_success, on_error):
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


def _import_backup_android(on_success, on_error):
    # jnius/android imported HERE, not at module level, so this file
    # can still be opened/edited on Windows without complaint -- same
    # reasoning screens/editor/image_mixin.py already documents for
    # its own android/jnius imports: these modules only exist at
    # runtime on an actual Android build.
    from android import activity
    from jnius import autoclass

    Intent = autoclass("android.content.Intent")
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    current_activity = PythonActivity.mActivity

    intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
    intent.addCategory(Intent.CATEGORY_OPENABLE)
    # "*/*" rather than "application/json" -- backup files are saved
    # via Android's SAF write-stream path (_export_backup_android
    # above), which does not reliably tag the resulting file with a
    # proper JSON mime type on every device/file-provider combo.
    # Restricting to application/json risked the very file this
    # feature just exported not showing up in its own import picker.
    intent.setType("*/*")

    if intent.resolveActivity(current_activity.getPackageManager()) is None:
        # No document picker available at all -- extremely unlikely
        # on any real modern device, but fall back to plyer's picker
        # rather than doing nothing, same defensive pattern
        # image_mixin.py uses for its own picker fallback.
        _import_backup_desktop(on_success, on_error)
        return

    def handle_result(requestCode, resultCode, data):
        if requestCode != _ANDROID_PICK_BACKUP_REQUEST_CODE:
            return

        activity.unbind(on_activity_result=handle_result)

        Activity = autoclass("android.app.Activity")
        if resultCode != Activity.RESULT_OK or data is None:
            on_error(ImportCancelled("Import cancelled -- no file chosen."))
            return

        uri = data.getData()
        Clock.schedule_once(lambda dt: _restore_from_uri(uri, on_success, on_error))

    activity.bind(on_activity_result=handle_result)
    current_activity.startActivityForResult(intent, _ANDROID_PICK_BACKUP_REQUEST_CODE)


def _restore_from_uri(uri, on_success, on_error):
    from jnius import autoclass

    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    resolver = PythonActivity.mActivity.getContentResolver()

    try:
        input_stream = resolver.openInputStream(uri)
        chunks = []
        buffer = bytearray(8192)
        while True:
            bytes_read = input_stream.read(buffer)
            if bytes_read == -1:
                break
            chunks.append(bytes(buffer[:bytes_read]))
        input_stream.close()
        raw_bytes = b"".join(chunks)
    except Exception as exc:
        on_error(exc)
        return

    try:
        manifest = json.loads(raw_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        on_error(exc)
        return

    try:
        # restore_from_manifest() is called directly here rather than
        # restore_from_path() -- there is no real file path to give
        # it on Android (only a content URI, already fully read into
        # memory above), so the path-based entry point doesn't apply.
        restore_from_manifest(manifest)
    except RestoreError as exc:
        on_error(exc)
        return
    except Exception as exc:
        on_error(exc)
        return

    on_success()
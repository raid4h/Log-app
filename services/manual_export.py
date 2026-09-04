# services/manual_export.py
#
# Wires backup_builder (Phase 1) and restore_engine (Phase 2) up to a
# FOLDER the user chooses -- not a single file. A "Log Backup" folder
# contains:
#   backup.json        -- the authoritative, checksum-verified manifest
#   attachments/        -- real copied image files, one per attachment
#                          record, named by that attachment's
#                          "backup_filename" (see backup_builder.py)
#
# This is what makes attachments actually portable across devices --
# previously only a dangling file_path reference to the ORIGINAL
# device's filesystem was backed up. Now the real file travels with
# the backup, and import copies it into whatever device is restoring,
# rewriting file_path to the new local copy before handing the
# manifest to restore_engine.py -- which needs NO changes for any of
# this, since it only ever receives an already-correct manifest.
#
# Desktop uses plyer's filechooser.choose_dir() for the folder picker
# and plain os/shutil for reading/writing inside it.
#
# Android bypasses plyer entirely (same reasoning as the earlier
# Android import fix -- plyer's own file-picker code has repeatedly
# had platform-specific bugs) in favor of a raw
# Intent.ACTION_OPEN_DOCUMENT_TREE folder picker, and reads/writes
# inside the chosen folder via android.provider.DocumentsContract --
# the raw Android SDK API for SAF document trees, not the AndroidX
# DocumentFile helper library, since that library isn't guaranteed to
# be present in this project's pinned requirements.

import json
import os
import shutil

from kivy.clock import Clock
from kivy.utils import platform

from plyer import filechooser

from services.backup_builder import (
    build_backup_manifest,
    manifest_to_json_bytes,
    get_attachment_source_path,
    ATTACHMENTS_SUBFOLDER,
)
from services.restore_engine import restore_from_manifest, RestoreError


BACKUP_JSON_FILENAME = "backup.json"

# Arbitrary numbers Android uses to match a picker's result back to
# the specific request that opened it -- same technique as
# screens/editor/image_mixin.py's _ANDROID_PICK_IMAGE_REQUEST_CODE,
# just different constants so none of these collide if a result from
# one arrives while another is still bound.
_ANDROID_EXPORT_FOLDER_REQUEST_CODE = 7533
_ANDROID_IMPORT_FOLDER_REQUEST_CODE = 7534


class ExportCancelled(Exception):
    """Raised when the user closes the folder picker without choosing a location."""


class ImportCancelled(Exception):
    """Raised when the user closes the folder picker without choosing a folder."""


def _guess_mime_type(filename):
    extension = os.path.splitext(filename)[1].lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(extension, "application/octet-stream")


# ============================================================================
# Export
# ============================================================================

def export_backup_to_folder(on_success, on_error):
    """
    Opens a native folder picker, and on confirmation, writes a fresh
    backup.json plus every attachment's real image file into an
    attachments/ subfolder of the chosen folder.

    on_success(folder_path) is called after a successful export.
    NOTE: on Android, folder_path will always be None -- the Storage
    Access Framework never hands the app a real filesystem path for a
    picked folder, only an opaque tree URI. Callers displaying a
    success message should handle a None path gracefully.

    on_error(exception) is called if anything goes wrong, including
    the user cancelling the picker (ExportCancelled).
    """
    if platform == "android":
        _export_backup_folder_android(on_success, on_error)
    else:
        _export_backup_folder_desktop(on_success, on_error)


def _export_backup_folder_desktop(on_success, on_error):
    cwd_before_picker = os.getcwd()

    def handle_selection(selection):
        os.chdir(cwd_before_picker)

        if not selection:
            on_error(ExportCancelled("Export cancelled -- no folder chosen."))
            return

        folder_path = selection[0]

        try:
            manifest = build_backup_manifest()

            attachments_dir = os.path.join(folder_path, ATTACHMENTS_SUBFOLDER)
            os.makedirs(attachments_dir, exist_ok=True)

            for attachment in manifest["data"]["attachments"]:
                source_path = get_attachment_source_path(attachment)
                if source_path is None:
                    # The original image no longer exists on this
                    # device -- skip it rather than fail the whole
                    # export over one missing file.
                    continue
                dest_path = os.path.join(attachments_dir, attachment["backup_filename"])
                shutil.copy2(source_path, dest_path)

            json_path = os.path.join(folder_path, BACKUP_JSON_FILENAME)
            with open(json_path, "wb") as f:
                f.write(manifest_to_json_bytes(manifest))

        except Exception as exc:
            on_error(exc)
            return

        on_success(folder_path)

    filechooser.choose_dir(
        on_selection=handle_selection,
        title="Choose a folder for your Log Backup",
    )


def _export_backup_folder_android(on_success, on_error):
    from android import activity
    from jnius import autoclass

    Intent = autoclass("android.content.Intent")
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    current_activity = PythonActivity.mActivity

    intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)
    intent.addFlags(
        Intent.FLAG_GRANT_READ_URI_PERMISSION
        | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
        | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
    )

    def handle_result(requestCode, resultCode, data):
        if requestCode != _ANDROID_EXPORT_FOLDER_REQUEST_CODE:
            return
        activity.unbind(on_activity_result=handle_result)

        Activity = autoclass("android.app.Activity")
        if resultCode != Activity.RESULT_OK or data is None:
            on_error(ExportCancelled("Export cancelled -- no folder chosen."))
            return

        tree_uri = data.getData()
        Clock.schedule_once(lambda dt: _write_backup_to_tree(tree_uri, on_success, on_error))

    activity.bind(on_activity_result=handle_result)
    current_activity.startActivityForResult(intent, _ANDROID_EXPORT_FOLDER_REQUEST_CODE)


def _write_backup_to_tree(tree_uri, on_success, on_error):
    from jnius import autoclass

    try:
        DocumentsContract = autoclass("android.provider.DocumentsContract")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Intent = autoclass("android.content.Intent")
        resolver = PythonActivity.mActivity.getContentResolver()

        # Persists this folder's permission past the current app
        # session -- not used by this manual-export flow itself (which
        # re-picks a folder every time), but this is what will let the
        # planned Settings > auto-backup feature reuse a
        # once-chosen folder silently, without prompting the picker
        # again on every scheduled backup. Not fatal if it fails --
        # export still succeeds either way for THIS run.
        try:
            resolver.takePersistableUriPermission(
                tree_uri,
                Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
            )
        except Exception:
            pass

        root_doc_id = DocumentsContract.getTreeDocumentId(tree_uri)

        manifest = build_backup_manifest()
        json_bytes = manifest_to_json_bytes(manifest)

        _write_document_bytes(
            resolver, DocumentsContract, tree_uri, root_doc_id,
            BACKUP_JSON_FILENAME, "application/json", json_bytes,
        )

        attachments_doc_id = _ensure_child_directory(
            resolver, DocumentsContract, tree_uri, root_doc_id, ATTACHMENTS_SUBFOLDER
        )

        for attachment in manifest["data"]["attachments"]:
            source_path = get_attachment_source_path(attachment)
            if source_path is None:
                continue
            with open(source_path, "rb") as f:
                file_bytes = f.read()
            mime_type = _guess_mime_type(attachment["backup_filename"])
            _write_document_bytes(
                resolver, DocumentsContract, tree_uri, attachments_doc_id,
                attachment["backup_filename"], mime_type, file_bytes,
            )

    except Exception as exc:
        on_error(exc)
        return

    on_success(None)


# ============================================================================
# Import
# ============================================================================

def import_backup_from_folder(on_success, on_error):
    """
    Opens a native folder picker, and on confirmation, restores the
    app's data from that folder's backup.json -- copying each
    attachment's real image file (from the folder's attachments/
    subfolder) into this device's own local attachment storage first,
    and rewriting the manifest's file_path values to point at those
    new local copies, before handing the manifest to
    restore_engine.restore_from_manifest().

    on_success() is called after a successful restore.
    on_error(exception) is called if anything goes wrong -- including
    the user cancelling (ImportCancelled), the folder not containing a
    recognizable backup (RestoreError), or any other failure. Per
    restore_engine's own guarantee, the live database is left
    untouched in every error case.
    """
    if platform == "android":
        _import_backup_folder_android(on_success, on_error)
    else:
        _import_backup_folder_desktop(on_success, on_error)


def _import_backup_folder_desktop(on_success, on_error):
    cwd_before_picker = os.getcwd()

    def handle_selection(selection):
        os.chdir(cwd_before_picker)

        if not selection:
            on_error(ImportCancelled("Import cancelled -- no folder chosen."))
            return

        folder_path = selection[0]
        json_path = os.path.join(folder_path, BACKUP_JSON_FILENAME)

        if not os.path.isfile(json_path):
            on_error(RestoreError(
                f"No '{BACKUP_JSON_FILENAME}' found in that folder -- make sure "
                f"you selected a folder created by Log's backup export."
            ))
            return

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)

            attachments_dir = os.path.join(folder_path, ATTACHMENTS_SUBFOLDER)
            if os.path.isdir(attachments_dir):
                _restore_attachment_files_desktop(attachments_dir, manifest)

            restore_from_manifest(manifest)

        except RestoreError as exc:
            on_error(exc)
            return
        except Exception as exc:
            on_error(exc)
            return

        on_success()

    filechooser.choose_dir(
        on_selection=handle_selection,
        title="Select your Log Backup folder",
    )


def _restore_attachment_files_desktop(attachments_dir, manifest):
    from screens.editor.paths import get_attachments_dir
    import uuid

    local_attachments_dir = get_attachments_dir()
    os.makedirs(local_attachments_dir, exist_ok=True)

    for attachment in manifest.get("data", {}).get("attachments", []):
        backup_filename = attachment.get("backup_filename")
        if not backup_filename:
            # A pre-v4 backup, made before attachments carried real
            # files -- nothing to copy, file_path is left as-is (the
            # existing, already-accepted "only resolves on the
            # original device" limitation for backups that old).
            continue

        source_path = os.path.join(attachments_dir, backup_filename)
        if not os.path.isfile(source_path):
            # This particular image wasn't included when the backup
            # was made (e.g. it was already missing on export too) --
            # skip it rather than fail the whole restore.
            continue

        extension = os.path.splitext(backup_filename)[1]
        local_filename = f"{uuid.uuid4().hex}{extension}"
        local_path = os.path.join(local_attachments_dir, local_filename)
        shutil.copy2(source_path, local_path)

        attachment["file_path"] = local_path


def _import_backup_folder_android(on_success, on_error):
    from android import activity
    from jnius import autoclass

    Intent = autoclass("android.content.Intent")
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    current_activity = PythonActivity.mActivity

    intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)
    intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)

    def handle_result(requestCode, resultCode, data):
        if requestCode != _ANDROID_IMPORT_FOLDER_REQUEST_CODE:
            return
        activity.unbind(on_activity_result=handle_result)

        Activity = autoclass("android.app.Activity")
        if resultCode != Activity.RESULT_OK or data is None:
            on_error(ImportCancelled("Import cancelled -- no folder chosen."))
            return

        tree_uri = data.getData()
        Clock.schedule_once(lambda dt: _restore_from_tree(tree_uri, on_success, on_error))

    activity.bind(on_activity_result=handle_result)
    current_activity.startActivityForResult(intent, _ANDROID_IMPORT_FOLDER_REQUEST_CODE)


def _restore_from_tree(tree_uri, on_success, on_error):
    from jnius import autoclass

    try:
        DocumentsContract = autoclass("android.provider.DocumentsContract")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        resolver = PythonActivity.mActivity.getContentResolver()

        root_doc_id = DocumentsContract.getTreeDocumentId(tree_uri)

        json_doc_id = _find_child_document_id(
            resolver, DocumentsContract, tree_uri, root_doc_id, BACKUP_JSON_FILENAME
        )
        if json_doc_id is None:
            on_error(RestoreError(
                f"No '{BACKUP_JSON_FILENAME}' found in that folder -- make sure "
                f"you selected a folder created by Log's backup export."
            ))
            return

        json_uri = DocumentsContract.buildDocumentUriUsingTree(tree_uri, json_doc_id)
        json_bytes = _read_document_bytes(resolver, json_uri)
        manifest = json.loads(json_bytes.decode("utf-8"))

        attachments_doc_id = _find_child_document_id(
            resolver, DocumentsContract, tree_uri, root_doc_id, ATTACHMENTS_SUBFOLDER
        )
        if attachments_doc_id is not None:
            _restore_attachment_files_android(
                resolver, DocumentsContract, tree_uri, attachments_doc_id, manifest
            )

        restore_from_manifest(manifest)

    except RestoreError as exc:
        on_error(exc)
        return
    except Exception as exc:
        on_error(exc)
        return

    on_success()


def _restore_attachment_files_android(resolver, DocumentsContract, tree_uri, attachments_doc_id, manifest):
    from screens.editor.paths import get_attachments_dir
    import uuid

    local_attachments_dir = get_attachments_dir()
    os.makedirs(local_attachments_dir, exist_ok=True)

    for attachment in manifest.get("data", {}).get("attachments", []):
        backup_filename = attachment.get("backup_filename")
        if not backup_filename:
            continue

        child_doc_id = _find_child_document_id(
            resolver, DocumentsContract, tree_uri, attachments_doc_id, backup_filename
        )
        if child_doc_id is None:
            continue

        child_uri = DocumentsContract.buildDocumentUriUsingTree(tree_uri, child_doc_id)
        file_bytes = _read_document_bytes(resolver, child_uri)

        extension = os.path.splitext(backup_filename)[1]
        local_filename = f"{uuid.uuid4().hex}{extension}"
        local_path = os.path.join(local_attachments_dir, local_filename)
        with open(local_path, "wb") as f:
            f.write(file_bytes)

        attachment["file_path"] = local_path


# ============================================================================
# Android SAF (DocumentsContract) helpers
# ============================================================================
# All of these operate purely on document IDs within a single already-
# picked tree URI -- none of them open a picker or touch on_success/
# on_error, they just read/write/query the tree itself.

def _find_child_document_id(resolver, DocumentsContract, tree_uri, parent_doc_id, display_name):
    """
    Returns the document id of a direct child of parent_doc_id whose
    display name matches exactly, or None if no such child exists.
    SAF has no "get child by name" query -- this lists every child and
    scans for a match, which is fine at the scale a single backup
    folder (backup.json + one attachments/ folder, or a modest number
    of attachment files within it) actually has.
    """
    from jnius import autoclass

    Document = autoclass("android.provider.DocumentsContract$Document")
    children_uri = DocumentsContract.buildChildDocumentsUriUsingTree(tree_uri, parent_doc_id)

    projection = [Document.COLUMN_DOCUMENT_ID, Document.COLUMN_DISPLAY_NAME]
    cursor = resolver.query(children_uri, projection, None, None, None)
    if cursor is None:
        return None

    try:
        name_index = cursor.getColumnIndex(Document.COLUMN_DISPLAY_NAME)
        id_index = cursor.getColumnIndex(Document.COLUMN_DOCUMENT_ID)
        while cursor.moveToNext():
            if cursor.getString(name_index) == display_name:
                return cursor.getString(id_index)
        return None
    finally:
        cursor.close()


def _ensure_child_directory(resolver, DocumentsContract, tree_uri, parent_doc_id, name):
    """
    Returns the document id of a subfolder with the given name under
    parent_doc_id, reusing it if it already exists (so re-exporting
    doesn't create "attachments (1)"), or creating it if not.
    """
    from jnius import autoclass

    existing = _find_child_document_id(resolver, DocumentsContract, tree_uri, parent_doc_id, name)
    if existing is not None:
        return existing

    Document = autoclass("android.provider.DocumentsContract$Document")
    parent_uri = DocumentsContract.buildDocumentUriUsingTree(tree_uri, parent_doc_id)
    new_dir_uri = DocumentsContract.createDocument(resolver, parent_uri, Document.MIME_TYPE_DIR, name)
    if new_dir_uri is None:
        raise IOError(f"Could not create the '{name}' folder in the backup destination.")

    return DocumentsContract.getDocumentId(new_dir_uri)


def _write_document_bytes(resolver, DocumentsContract, tree_uri, parent_doc_id, filename, mime_type, data_bytes):
    """
    Writes data_bytes to a file named `filename` directly under
    parent_doc_id, overwriting cleanly if one already exists.
    SAF's createDocument() never overwrites -- it always creates a
    new, uniquely-named document (e.g. "backup (1).json") -- so any
    existing file with this exact name is deleted first, which is
    what actually gives export-into-the-same-folder its "overwrite"
    behavior instead of silently accumulating duplicates on every run.
    """
    existing_id = _find_child_document_id(resolver, DocumentsContract, tree_uri, parent_doc_id, filename)
    if existing_id is not None:
        existing_uri = DocumentsContract.buildDocumentUriUsingTree(tree_uri, existing_id)
        DocumentsContract.deleteDocument(resolver, existing_uri)

    parent_uri = DocumentsContract.buildDocumentUriUsingTree(tree_uri, parent_doc_id)
    new_uri = DocumentsContract.createDocument(resolver, parent_uri, mime_type, filename)
    if new_uri is None:
        raise IOError(f"Could not create '{filename}' in the backup destination.")

    output_stream = resolver.openOutputStream(new_uri)
    try:
        output_stream.write(data_bytes)
        output_stream.flush()
    finally:
        output_stream.close()


def _read_document_bytes(resolver, uri):
    input_stream = resolver.openInputStream(uri)
    chunks = []
    buffer = bytearray(8192)
    try:
        while True:
            bytes_read = input_stream.read(buffer)
            if bytes_read == -1:
                break
            chunks.append(bytes(buffer[:bytes_read]))
    finally:
        input_stream.close()
    return b"".join(chunks)
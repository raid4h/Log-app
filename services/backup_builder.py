# services/backup_builder.py
#
# Builds a single, versioned, checksummed JSON "manifest" describing
# a complete snapshot of the app's data -- notes, categories, tasks,
# reminders, attachment records, and anything currently sitting in
# Recently Deleted. This file NEVER writes its own SQL -- it only
# calls query functions that already exist in database/*_queries.py,
# so there is exactly one place in the whole app that knows how notes
# (or tasks, or reminders...) are actually stored.
#
# "Versioned" means every manifest carries a schema_version number.
# That's what lets a future version of the app -- one that's added
# new fields nobody has today -- still know how to safely read an
# older backup instead of guessing at what's missing.
#
# As of v4, this file is one piece of a FOLDER-based backup, not a
# single file: build_backup_manifest() still returns just the JSON
# data (this file never touches the filesystem beyond reading via
# existing query functions), but each attachment record now carries a
# "backup_filename" -- the name that attachment's actual image file
# should be copied to/read from inside a "attachments/" subfolder
# alongside backup.json. Actually COPYING those files (which differs
# by platform -- plain shutil on desktop, ContentResolver/
# DocumentsContract on Android's SAF folder tree) is
# services/manual_export.py's job, not this file's -- this file only
# decides WHAT the filename should be and exposes
# get_attachment_source_path() so the caller can find the real bytes
# to copy.

import hashlib
import json
import os
from datetime import datetime, timezone

from database.notes_queries import get_all_notes
from database.category_queries import get_all_categories
from database.task_queries import get_all_tasks
from database.reminder_queries import get_reminders_by_task
from database.attachment_queries import get_all_attachments
import trash_store

from models.note import Note
from models.category import Category
from models.task import Task
from models.reminder import Reminder

from database.calendar_queries import get_all_events

from services.checklist_store import get_all_checklists, get_all_items_flat

from screens.editor.paths import DEFAULT_NOTEBOOK_ID

# The current manifest format version. Bump this only when the
# structure of the "data" section below actually changes shape (a
# field added/removed/renamed) -- not for every code change.
SCHEMA_VERSION = 1

# The current manifest format version. Bump this only when the
# structure of the "data" section below actually changes shape (a
# field added/removed/renamed) -- not for every code change.
# v2: added "calendar_events" (date-based reminders from the
# Calendar feature, separate from the existing task-linked
# "reminders" list).
SCHEMA_VERSION = 2

# v3: added "checklists" and "checklist_items" (the Checklist
# feature's own tables, stored independently of every other table
# above via services/checklist_store.py -- previously missing from
# every backup entirely).
SCHEMA_VERSION = 3

# v4: each attachment record now carries "backup_filename" -- the
# name its actual image file is stored under inside a folder-based
# backup's "attachments/" subfolder, so a restored device can find and
# copy the real file back instead of only restoring a dangling
# file_path reference to the ORIGINAL device's filesystem.
SCHEMA_VERSION = 4

# The app doesn't yet have real multi-user accounts (no
# user_queries.py, no login screen) -- categories and tasks still
# require a user_id today only because the schema has the column.
# This mirrors the same "single implicit default" pattern the note
# editor already uses for DEFAULT_NOTEBOOK_ID. Update this the moment
# a real user system exists.
DEFAULT_USER_ID = 1

# The subfolder name, inside a folder-based backup, that holds actual
# copied attachment image files. Both manual_export.py (writing) and
# restore_engine.py (reading) need to agree on this exact name.
ATTACHMENTS_SUBFOLDER = "attachments"


def _note_to_dict(row):
    # Reuses the Note model class as the single source of truth for
    # field names/order, instead of redefining that mapping here too
    # -- if Tabshira ever reorders notes' columns, this line doesn't
    # need to change, only models/note.py does.
    return vars(Note(*row))


def _category_to_dict(row):
    return vars(Category(*row))


def _task_to_dict(row):
    return vars(Task(*row))


def _reminder_to_dict(row):
    return vars(Reminder(*row))


def _attachment_backup_filename(attachment_id, source_path):
    """
    Deterministic filename an attachment's real file is stored under
    inside the backup's attachments/ subfolder -- prefixed with the
    attachment's own id so two attachments that happened to share an
    original filename (e.g. two separately-picked "image.jpg" files)
    never collide once copied into the same flat backup folder.
    """
    extension = os.path.splitext(source_path)[1] if source_path else ""
    return f"{attachment_id}{extension}"


def _attachment_to_dict(row):
    # No Attachment model class exists yet -- built as a plain dict
    # here. Column order matches the "attachments" table in db.py:
    # id, note_id, file_path, created_at.
    attachment_id, note_id, file_path, created_at = row[0], row[1], row[2], row[3]
    return {
        "id": attachment_id,
        "note_id": note_id,
        "file_path": file_path,
        "created_at": created_at,
        # New in v4 -- see module docstring.
        "backup_filename": _attachment_backup_filename(attachment_id, file_path),
    }


def get_attachment_source_path(attachment_dict):
    """
    Returns the real, absolute path to an attachment's image file on
    THIS device, or None if that file no longer exists (e.g. it was
    deleted/moved outside the app since the attachment record was
    created). Callers (manual_export.py, when actually copying bytes
    into a backup folder) should skip an attachment entirely rather
    than fail the whole backup when this returns None -- a missing
    source image shouldn't block backing up everything else.
    """
    file_path = attachment_dict.get("file_path")
    if not file_path:
        return None
    if not os.path.isfile(file_path):
        return None
    return file_path


def _collect_notes():
    rows = get_all_notes(DEFAULT_NOTEBOOK_ID)
    return [_note_to_dict(row) for row in rows]


def _collect_categories():
    rows = get_all_categories(DEFAULT_USER_ID)
    return [_category_to_dict(row) for row in rows]


def _collect_tasks():
    rows = get_all_tasks(DEFAULT_USER_ID)
    return [_task_to_dict(row) for row in rows]


def _collect_reminders(tasks):
    # There's no get_all_reminders() -- only get_reminders_by_task().
    # Looping over every task and collecting its reminders reuses that
    # existing function rather than writing a new query, and still
    # captures inactive reminders too (get_active_reminders() would
    # have silently dropped those).
    reminders = []
    for task in tasks:
        rows = get_reminders_by_task(task["id"])
        reminders.extend(_reminder_to_dict(row) for row in rows)
    return reminders

def _collect_calendar_events():
    # calendar_queries.py already returns plain dicts (not raw tuples
    # like task_queries/reminder_queries), so no model-mapping step
    # is needed here -- just pass the list straight through.
    return get_all_events(DEFAULT_USER_ID)

def _collect_attachments(notes):
    # Same technique as _collect_reminders -- get_all_attachments()
    # needs a note_id, so we loop over every note and gather its
    # attachments. As of v4, this now also stamps each attachment
    # with its backup_filename (see _attachment_to_dict) -- but this
    # function still only returns METADATA, never touches or copies
    # the actual image bytes. See get_attachment_source_path() and
    # this module's docstring for how the real files get copied.
    attachments = []
    for note in notes:
        rows = get_all_attachments(note["id"])
        attachments.extend(_attachment_to_dict(row) for row in rows)
    return attachments


def _collect_trash():
    # trash_store already returns plain dicts (it's backed by JSON,
    # not SQLite), so no tuple-to-dict mapping is needed here.
    return trash_store.get_trash_entries()


def _collect_checklists():
    # checklist_store.py already returns plain dicts (same pattern as
    # calendar_queries.py) -- no model-mapping step needed. Scoped to
    # DEFAULT_USER_ID for the same reason categories/tasks are.
    return get_all_checklists(DEFAULT_USER_ID)


def _collect_checklist_items():
    # get_all_items_flat() returns EVERY item across EVERY checklist
    # (top-level and sub-items alike, in id order) in one call -- see
    # its own docstring, which already flags it as intended for this
    # exact use.
    return get_all_items_flat()


def _compute_checksum(data):
    # sort_keys=True is what makes this deterministic -- the same
    # data always produces the same checksum regardless of what order
    # Python happened to build the dictionary in. Without this, the
    # checksum would be useless for corruption detection, since it
    # could differ even when nothing actually changed.
    canonical = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_backup_manifest():
    """
    Builds and returns one complete manifest dictionary describing the
    current state of the app's data. Does not touch the network or the
    filesystem beyond reading via existing query functions -- this
    function never writes anything and never copies attachment image
    bytes; it only decides what EACH attachment's backup_filename
    should be. See get_attachment_source_path() for finding the real
    file to copy, and this module's docstring for the overall
    folder-backup design.
    """
    notes = _collect_notes()
    categories = _collect_categories()
    tasks = _collect_tasks()
    reminders = _collect_reminders(tasks)
    calendar_events = _collect_calendar_events()
    attachments = _collect_attachments(notes)
    trash = _collect_trash()
    checklists = _collect_checklists()
    checklist_items = _collect_checklist_items()

    data = {
        "notebooks": [],
        "categories": categories,
        "notes": notes,
        "tasks": tasks,
        "reminders": reminders,
        "calendar_events": calendar_events,
        "attachments": attachments,
        "trash": trash,
        "checklists": checklists,
        "checklist_items": checklist_items,
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "checksum": _compute_checksum(data),
        "encrypted": False,
        "data": data,
    }


def manifest_to_json_bytes(manifest):
    """
    Serializes a manifest to UTF-8 JSON bytes using the exact same
    json.dumps() settings as save_manifest_to_path() below, so that a
    manifest written via a file path (desktop) and one written via a
    raw byte stream (Android's SAF FileOutputStream) are byte-for-byte
    identical. Any caller that needs manifest bytes without a
    filesystem path -- e.g. writing into an already-open stream --
    should go through this function rather than reimplementing the
    json.dumps() call, so the two paths can never quietly drift apart
    in formatting.
    """
    text = json.dumps(manifest, indent=2)
    return text.encode("utf-8")


def save_manifest_to_path(manifest, file_path):
    """
    Writes a manifest dictionary to disk as a JSON file (backup.json,
    inside a folder-based backup). Kept separate from
    build_backup_manifest() so callers can build once and choose
    where the JSON portion goes.
    """
    with open(file_path, "wb") as f:
        f.write(manifest_to_json_bytes(manifest))


def verify_manifest_checksum(manifest):
    """
    Returns True if the manifest's stored checksum matches its actual
    data. Used before ever restoring a backup -- if this returns
    False, the file was corrupted or tampered with somewhere between
    being created and being read back.
    """
    return manifest.get("checksum") == _compute_checksum(manifest.get("data", {}))
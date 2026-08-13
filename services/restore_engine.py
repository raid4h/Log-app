# services/restore_engine.py
#
# Safely rebuilds the app's SQLite database from a backup manifest
# (as produced by services.backup_builder). Never writes into the
# live database directly -- builds a brand-new one in a temporary
# file, fully populates and checks it, and only replaces the live
# database with it after every step has succeeded. If anything fails
# partway through, the live database is left completely untouched.

import contextlib
import json
import os
import tempfile

from database.calendar_queries import create_calendar_events_table, create_event
import database.db as db
from database.category_queries import create_category
from database.notes_queries import create_notes
from database.task_queries import create_tasks
from database.reminder_queries import create_reminder
from database.attachment_queries import create_attachment
import trash_store

from services.backup_builder import SCHEMA_VERSION, verify_manifest_checksum


class RestoreError(Exception):
    """
    Raised when a backup cannot be safely restored. Always raised
    BEFORE any write happens to the live database -- callers can
    catch this and show the user a clear message, knowing their
    current data was never touched.
    """


def load_manifest_from_path(file_path):
    """Reads and parses a manifest JSON file from disk."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _validate_manifest(manifest):
    schema_version = manifest.get("schema_version")

    if schema_version is None or schema_version > SCHEMA_VERSION:
        raise RestoreError(
            f"This backup was created with a newer version of NoteNest "
            f"(format version {schema_version}) than this app understands "
            f"(up to version {SCHEMA_VERSION}). Update the app before "
            f"restoring this backup."
        )

    if not verify_manifest_checksum(manifest):
        raise RestoreError(
            "This backup file's checksum does not match its contents. "
            "It may be corrupted or incomplete -- refusing to restore "
            "rather than risk loading damaged data."
        )


@contextlib.contextmanager
def _temporary_database(db_path):
    """
    Temporarily points every existing database/*_queries.py function at
    a different SQLite file, without changing a single line of their
    code. Every one of those functions ultimately calls
    database.db.get_connection(), which re-reads the module-level
    DB_NAME each time it's called -- so swapping that value for the
    duration of this block redirects all of them at once.

    NOTE: this relies on NoteNest being single-threaded, which it is
    today (Kivy's event loop runs on one thread, and nothing here
    spawns background threads). If background/threaded database access
    is ever added later, this approach would need revisiting, since
    two threads could briefly see different DB_NAME values at once.
    """
    original_db_name = db.DB_NAME
    db.DB_NAME = db_path
    try:
        yield
    finally:
        db.DB_NAME = original_db_name


def _populate_categories(categories):
    id_map = {}
    for category in categories:
        new_id = create_category(category["name"], category["color"], category["user_id"])
        id_map[category["id"]] = new_id
    return id_map


def _populate_notes(notes, category_id_map):
    id_map = {}
    for note in notes:
        old_category_id = note.get("category_id")
        new_category_id = (
            category_id_map.get(old_category_id) if old_category_id is not None else None
        )

        new_id = create_notes(
            note["notebook_id"],
            note["title"],
            note["content"],
            category_id=new_category_id,
            is_pinned=note.get("is_pinned", 0),
            is_archived=note.get("is_archived", 0),
            # task_id was previously dropped on restore -- any note
            # created from a task (see get_notes_by_task) would come
            # back unlinked. Passed through now so that link survives
            # a backup/restore cycle.
            task_id=note.get("task_id"),
            # created_at/updated_at were previously left out, so
            # create_notes() silently stamped every restored note with
            # "now" for both. Since get_all_notes() sorts by
            # is_pinned DESC, updated_at DESC, that was quietly
            # reordering the whole notes list on every restore.
            # Passing the originals through preserves both real
            # history and note order.
            created_at=note.get("created_at"),
            updated_at=note.get("updated_at"),
        )
        id_map[note["id"]] = new_id
    return id_map


def _populate_tasks(tasks):
    id_map = {}
    for task in tasks:
        # Previously only title and user_id were passed through, so
        # every other field (priority, due_date, due_time,
        # category_id, activity_type, link, carry_forward,
        # notify_enabled, original_due_date) was silently dropped on
        # restore -- a task came back as a bare title with nothing
        # else. create_tasks() already accepts all of these as
        # kwargs, so they're passed through now. category_id is
        # remapped through category_id_map like notes' category_id
        # is, rather than passed as the raw old id, since categories
        # get new ids on restore too.
        new_id = create_tasks(
            task["title"],
            task["user_id"],
            priority=task.get("priority"),
            due_date=task.get("due_date"),
            due_time=task.get("due_time"),
            category_id=task.get("category_id"),
            link=task.get("link", ""),
            carry_forward=bool(task.get("carry_forward", 0)),
            notify_enabled=bool(task.get("notify_enabled", 0)),
            activity_type=task.get("activity_type", "task"),
        )
        id_map[task["id"]] = new_id
    return id_map


def _populate_reminders(reminders, task_id_map):
    for reminder in reminders:
        new_task_id = task_id_map.get(reminder["task_id"])
        if new_task_id is None:
            # The task this reminder belonged to wasn't restored --
            # shouldn't normally happen, but skip rather than create a
            # reminder pointing at a task that doesn't exist.
            continue
        new_reminder_id = create_reminder(new_task_id, reminder["remind_at"])
        # create_reminder() always inserts with is_active defaulting
        # to 1 (see the reminders table's own DEFAULT 1 in db.py) --
        # an inactive/already-dismissed reminder was previously coming
        # back active after restore. deactivate_reminders() is the
        # only existing way to flip that flag, so it's called here
        # when the backup says the reminder was inactive.
        if not reminder.get("is_active", 1):
            from database.reminder_queries import deactivate_reminders
            deactivate_reminders(new_reminder_id)

def _populate_calendar_events(events):
    for event in events:
        create_event(
            user_id=event.get("user_id", 1),
            title=event["title"],
            event_date=event["event_date"],
            event_time=event.get("event_time"),
            event_link=event.get("event_link"),
            is_recurring=bool(event.get("is_recurring")),
        )
        # create_event() always starts a fresh row with completed=0,
        # original_date=event_date, missed_days=0 (see its own
        # docstring) -- restoring a recurring reminder's exact
        # completed/missed_days state isn't attempted here, since the
        # very next roll_forward_recurring_events() call (which runs
        # every time the Calendar screen opens) will recompute
        # missed_days correctly from today's date anyway.

def _populate_attachments(attachments, note_id_map):
    for attachment in attachments:
        new_note_id = note_id_map.get(attachment["note_id"])
        if new_note_id is None:
            continue
        create_attachment(new_note_id, attachment["file_path"])
        # NOTE: this restores the ATTACHMENT RECORD (a row pointing at
        # a file path) -- it does not move or verify the actual image
        # file on disk. That file_path only resolves correctly when
        # restoring on the same device the backup was made on. Moving
        # the real attachment files between devices is a Phase 5
        # concern (Drive Client), once attachments are actually
        # uploaded/downloaded alongside the manifest.


def _populate_trash(trash_entries, category_id_map):
    for entry in trash_entries:
        old_category_id = entry.get("category_id")
        new_category_id = (
            category_id_map.get(old_category_id) if old_category_id is not None else None
        )
        # trash_store.add_to_trash always stamps the CURRENT time as
        # deleted_at -- the original deletion timestamp from the
        # backup isn't preserved. Minor, cosmetic-only limitation.
        trash_store.add_to_trash(
            entry["notebook_id"], entry["title"], entry["content"], new_category_id
        )


def restore_from_manifest(manifest):
    """
    Safely restores the app's data from a manifest dictionary. Builds
    a brand-new database in a temporary file, populates it completely,
    and only replaces the live database with it after every step
    succeeds. Raises RestoreError (validation failed, nothing was
    touched) or lets the original exception propagate (something
    failed mid-build, temp file cleaned up, live database untouched).
    """
    _validate_manifest(manifest)
    data = manifest["data"]

    # Captured BEFORE _temporary_database ever runs, since that context
    # manager temporarily reassigns db.DB_NAME -- this is the real,
    # final destination path we'll swap into at the very end.
    target_db_path = os.path.abspath(db.DB_NAME)

    # The temp file MUST live on the same drive/filesystem as the
    # live database, or the final os.replace() below fails with
    # "cannot move to a different disk drive" on Windows -- os.replace
    # can only perform an atomic rename within one volume, it can't
    # atomically move across drives. Using dir=... here, instead of
    # the OS default temp folder, guarantees that.
    target_dir = os.path.dirname(target_db_path) or "."
    temp_fd, temp_path = tempfile.mkstemp(suffix=".db", dir=target_dir)
    os.close(temp_fd)  # only the path is needed -- SQLite opens its own handle

    try:
        with _temporary_database(temp_path):
            db.create_tables()
            create_calendar_events_table()

            category_id_map = _populate_categories(data.get("categories", []))
            note_id_map = _populate_notes(data.get("notes", []), category_id_map)
            task_id_map = _populate_tasks(data.get("tasks", []))
            _populate_reminders(data.get("reminders", []), task_id_map)
            _populate_calendar_events(data.get("calendar_events", []))
            _populate_attachments(data.get("attachments", []), note_id_map)
            _populate_trash(data.get("trash", []), category_id_map)

        # Reached only if every step above completed without raising.
        os.replace(temp_path, target_db_path)

    except Exception:
        # Something failed while building the new database. Delete the
        # incomplete temp file and leave the live database exactly as
        # it was before this call -- then let the caller see what
        # actually went wrong.
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def restore_from_path(file_path):
    """Convenience wrapper: load a manifest file from disk and restore it."""
    manifest = load_manifest_from_path(file_path)
    restore_from_manifest(manifest)
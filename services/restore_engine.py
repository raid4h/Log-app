# services/restore_engine.py
#
# Safely rebuilds the app's SQLite database from a backup manifest
# (as produced by services.backup_builder). Never writes into the
# live database directly -- builds a brand-new one in a temporary
# file, fully populates and checks it, and only replaces the live
# database with it after every step has succeeded. If anything fails
# partway through, the live database is left completely untouched.
#
# Every table now MERGES on import instead of replacing: whatever
# currently exists live is combined with the backup's data (with
# basic duplicate detection per table -- see each _merge_* function
# below), so importing a backup can never silently erase something
# added after that backup was taken.
#
# Cross-table references (a note's category_id/task_id, a task's
# category_id, a reminder's task_id, an attachment's note_id, trash's
# category_id) are remapped using a "_merge_key" carried on every
# in-memory entry -- ("existing", <live id>) for something already in
# the database, ("backup", <backup id>) for something new from the
# backup file. This is needed because existing-live ids and backup
# ids come from two unrelated id sequences and could otherwise
# collide by coincidence. _merge_key is purely an in-memory identity
# used by this file's own populate functions -- it is never written
# to the database.

import contextlib
import json
import os
import tempfile

from database.calendar_queries import create_calendar_events_table, create_event, get_all_events
import database.db as db
from database.category_queries import create_category, get_all_categories
from database.notes_queries import create_notes, get_all_notes
from database.task_queries import create_tasks, get_all_tasks
from database.reminder_queries import create_reminder, get_reminders_by_task, deactivate_reminders
from database.attachment_queries import create_attachment, get_all_attachments
import trash_store

from screens.editor.paths import DEFAULT_NOTEBOOK_ID

from services.checklist_store import (
    ensure_checklist_tables,
    create_checklist,
    create_checklist_item,
    get_all_checklists,
    get_all_items_flat,
)

from services.backup_builder import (
    SCHEMA_VERSION,
    verify_manifest_checksum,
    DEFAULT_USER_ID,
    _note_to_dict,
    _category_to_dict,
    _task_to_dict,
    _reminder_to_dict,
    _attachment_to_dict,
)


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
    database.db.get_connection(), which calls database.db.get_db_path()
    (a plain module-level name lookup, resolved fresh every call) --
    so replacing THAT function for the duration of this block redirects
    every one of them at once.

    NOTE: this relies on NoteNest being single-threaded, which it is
    today (Kivy's event loop runs on one thread, and nothing here
    spawns background threads). If background/threaded database access
    is ever added later, this approach would need revisiting, since
    two threads could briefly see different get_db_path values at once.
    """
    original_get_db_path = db.get_db_path
    db.get_db_path = lambda: db_path
    try:
        yield
    finally:
        db.get_db_path = original_get_db_path


# ── gathering existing live data (called BEFORE the temp-db swap) ──

def _collect_existing_reminders(existing_tasks):
    reminders = []
    for task in existing_tasks:
        for row in get_reminders_by_task(task["id"]):
            reminders.append(_reminder_to_dict(row))
    return reminders


def _collect_existing_attachments(existing_notes):
    attachments = []
    for note in existing_notes:
        for row in get_all_attachments(note["id"]):
            attachments.append(_attachment_to_dict(row))
    return attachments


# ── merge: categories ──

def _merge_categories(existing_categories, backup_categories):
    """
    Dedup rule: same name (case-insensitive) = same category.
    Returns (merged_list, backup_id_to_target) -- the second value
    maps a BACKUP category's own id to whichever merge_key it should
    be treated as going forward (its own new entry, or an existing
    category it matched), so tasks/notes/trash below can remap their
    category_id references correctly regardless of which side "won".
    """
    merged = []
    backup_id_to_target = {}
    dedup_index = {}

    for c in existing_categories:
        mk = ("existing", c["id"])
        entry = dict(c)
        entry["_merge_key"] = mk
        merged.append(entry)
        dedup_index[(c.get("name") or "").casefold()] = mk

    for c in backup_categories:
        key = (c.get("name") or "").casefold()
        if key in dedup_index:
            backup_id_to_target[c["id"]] = dedup_index[key]
            continue
        mk = ("backup", c["id"])
        entry = dict(c)
        entry["_merge_key"] = mk
        merged.append(entry)
        dedup_index[key] = mk
        backup_id_to_target[c["id"]] = mk

    return merged, backup_id_to_target


def _populate_categories(categories):
    id_map = {}
    for category in categories:
        new_id = create_category(category["name"], category["color"], category["user_id"])
        id_map[category["_merge_key"]] = new_id
    return id_map


# ── merge: tasks ──

def _merge_tasks(existing_tasks, backup_tasks, backup_category_target):
    """Dedup rule: same title + due_date = same task."""
    merged = []
    backup_id_to_target = {}
    dedup_index = {}

    for t in existing_tasks:
        mk = ("existing", t["id"])
        entry = dict(t)
        entry["_merge_key"] = mk
        entry["_category_merge_key"] = (
            ("existing", t["category_id"]) if t.get("category_id") is not None else None
        )
        merged.append(entry)
        dedup_index[(t.get("title"), t.get("due_date"))] = mk

    for t in backup_tasks:
        key = (t.get("title"), t.get("due_date"))
        if key in dedup_index:
            backup_id_to_target[t["id"]] = dedup_index[key]
            continue
        mk = ("backup", t["id"])
        old_category_id = t.get("category_id")
        entry = dict(t)
        entry["_merge_key"] = mk
        entry["_category_merge_key"] = (
            backup_category_target.get(old_category_id) if old_category_id is not None else None
        )
        merged.append(entry)
        dedup_index[key] = mk
        backup_id_to_target[t["id"]] = mk

    return merged, backup_id_to_target


def _populate_tasks(tasks, category_id_map):
    id_map = {}
    for task in tasks:
        category_mk = task.get("_category_merge_key")
        new_category_id = category_id_map.get(category_mk) if category_mk is not None else None
        new_id = create_tasks(
            task["title"],
            task["user_id"],
            priority=task.get("priority"),
            due_date=task.get("due_date"),
            due_time=task.get("due_time"),
            category_id=new_category_id,
            link=task.get("link", ""),
            carry_forward=bool(task.get("carry_forward", 0)),
            notify_enabled=bool(task.get("notify_enabled", 0)),
            activity_type=task.get("activity_type", "task"),
        )
        id_map[task["_merge_key"]] = new_id
    return id_map


# ── merge: notes ──

def _merge_notes(existing_notes, backup_notes, backup_category_target, backup_task_target):
    """
    Dedup rule: same title + content exactly = same note.
    Known limitation: a note edited after the backup was taken won't
    match (different content), so importing that backup adds it as a
    second note rather than updating the first -- detecting "this is
    an edited version of that" reliably needs more than exact-match
    comparison, and isn't attempted here.
    """
    merged = []
    backup_id_to_target = {}
    dedup_index = {}

    for n in existing_notes:
        mk = ("existing", n["id"])
        entry = dict(n)
        entry["_merge_key"] = mk
        entry["_category_merge_key"] = (
            ("existing", n["category_id"]) if n.get("category_id") is not None else None
        )
        entry["_task_merge_key"] = (
            ("existing", n["task_id"]) if n.get("task_id") is not None else None
        )
        merged.append(entry)
        dedup_index[(n.get("title"), n.get("content"))] = mk

    for n in backup_notes:
        key = (n.get("title"), n.get("content"))
        if key in dedup_index:
            backup_id_to_target[n["id"]] = dedup_index[key]
            continue
        mk = ("backup", n["id"])
        old_category_id = n.get("category_id")
        old_task_id = n.get("task_id")
        entry = dict(n)
        entry["_merge_key"] = mk
        entry["_category_merge_key"] = (
            backup_category_target.get(old_category_id) if old_category_id is not None else None
        )
        entry["_task_merge_key"] = (
            backup_task_target.get(old_task_id) if old_task_id is not None else None
        )
        merged.append(entry)
        dedup_index[key] = mk
        backup_id_to_target[n["id"]] = mk

    return merged, backup_id_to_target


def _populate_notes(notes, category_id_map, task_id_map):
    id_map = {}
    for note in notes:
        category_mk = note.get("_category_merge_key")
        new_category_id = category_id_map.get(category_mk) if category_mk is not None else None
        task_mk = note.get("_task_merge_key")
        new_task_id = task_id_map.get(task_mk) if task_mk is not None else None

        new_id = create_notes(
            note["notebook_id"],
            note["title"],
            note["content"],
            category_id=new_category_id,
            is_pinned=note.get("is_pinned", 0),
            is_archived=note.get("is_archived", 0),
            task_id=new_task_id,
            created_at=note.get("created_at"),
            updated_at=note.get("updated_at"),
        )
        id_map[note["_merge_key"]] = new_id
    return id_map


# ── merge: reminders ──

def _merge_reminders(existing_reminders, backup_reminders, backup_task_target):
    """Dedup rule: same task + same remind_at = same reminder."""
    merged = []
    dedup_index = set()

    for r in existing_reminders:
        task_mk = ("existing", r["task_id"])
        entry = dict(r)
        entry["_task_merge_key"] = task_mk
        merged.append(entry)
        dedup_index.add((task_mk, r["remind_at"]))

    for r in backup_reminders:
        task_mk = backup_task_target.get(r["task_id"])
        if task_mk is None:
            # The task this reminder belonged to wasn't restored --
            # shouldn't normally happen, skip rather than create a
            # reminder pointing at a task that doesn't exist.
            continue
        key = (task_mk, r["remind_at"])
        if key in dedup_index:
            continue
        entry = dict(r)
        entry["_task_merge_key"] = task_mk
        merged.append(entry)
        dedup_index.add(key)

    return merged


def _populate_reminders(reminders, task_id_map):
    for reminder in reminders:
        new_task_id = task_id_map.get(reminder.get("_task_merge_key"))
        if new_task_id is None:
            continue
        new_reminder_id = create_reminder(new_task_id, reminder["remind_at"])
        if not reminder.get("is_active", 1):
            deactivate_reminders(new_reminder_id)


# ── merge: attachments ──

def _merge_attachments(existing_attachments, backup_attachments, backup_note_target):
    """Dedup rule: same note + same file_path = same attachment."""
    merged = []
    dedup_index = set()

    for a in existing_attachments:
        note_mk = ("existing", a["note_id"])
        entry = dict(a)
        entry["_note_merge_key"] = note_mk
        merged.append(entry)
        dedup_index.add((note_mk, a["file_path"]))

    for a in backup_attachments:
        note_mk = backup_note_target.get(a["note_id"])
        if note_mk is None:
            continue
        key = (note_mk, a["file_path"])
        if key in dedup_index:
            continue
        entry = dict(a)
        entry["_note_merge_key"] = note_mk
        merged.append(entry)
        dedup_index.add(key)

    return merged


def _populate_attachments(attachments, note_id_map):
    for attachment in attachments:
        new_note_id = note_id_map.get(attachment["_note_merge_key"])
        if new_note_id is None:
            continue
        create_attachment(new_note_id, attachment["file_path"])
        # NOTE: this restores the ATTACHMENT RECORD (a row pointing at
        # a file path) -- it does not move or verify the actual image
        # file on disk. That file_path only resolves correctly when
        # restoring on the same device the backup was made on.


# ── merge: trash ──

def _merge_trash(existing_trash, backup_trash, backup_category_target):
    """Dedup rule: same title + content = same trash entry."""
    merged = []
    dedup_index = set()

    for e in existing_trash:
        category_mk = (
            ("existing", e["category_id"]) if e.get("category_id") is not None else None
        )
        entry = dict(e)
        entry["_category_merge_key"] = category_mk
        merged.append(entry)
        dedup_index.add((e.get("title"), e.get("content")))

    for e in backup_trash:
        key = (e.get("title"), e.get("content"))
        if key in dedup_index:
            continue
        old_category_id = e.get("category_id")
        category_mk = (
            backup_category_target.get(old_category_id) if old_category_id is not None else None
        )
        entry = dict(e)
        entry["_category_merge_key"] = category_mk
        merged.append(entry)
        dedup_index.add(key)

    return merged


def _populate_trash(trash_entries, category_id_map):
    for entry in trash_entries:
        category_mk = entry.get("_category_merge_key")
        new_category_id = category_id_map.get(category_mk) if category_mk is not None else None
        # trash_store.add_to_trash always stamps the CURRENT time as
        # deleted_at -- the original deletion timestamp from the
        # backup isn't preserved. Minor, cosmetic-only limitation.
        trash_store.add_to_trash(
            entry["notebook_id"], entry["title"], entry["content"], new_category_id
        )


# ── merge: calendar events ──

def _merge_calendar_events(existing_events, backup_events):
    """Dedup rule: same title + event_date + event_time = same event."""
    merged = list(existing_events)
    seen_keys = {
        (e.get("title"), e.get("event_date"), e.get("event_time"))
        for e in existing_events
    }
    for event in backup_events:
        key = (event.get("title"), event.get("event_date"), event.get("event_time"))
        if key in seen_keys:
            continue
        merged.append(event)
        seen_keys.add(key)
    return merged


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
        # original_date=event_date, missed_days=0 -- the very next
        # roll_forward_recurring_events() call (which runs every time
        # the Calendar screen opens) recomputes missed_days correctly
        # from today's date anyway.


# ── merge: checklists & items ──

def _merge_checklists_and_items(existing_checklists, existing_items, backup_checklists, backup_items):
    """
    Dedup rule: checklists match on title+priority (items get merged
    into the matched EXISTING checklist rather than duplicating it);
    within a checklist, TOP-LEVEL items match on exact text (a
    matching item and its whole sub-item tree is skipped). Sub-items
    are not independently deduped beyond that.
    """
    merged_checklists = []
    checklist_merge_key_by_existing_id = {}

    for checklist in existing_checklists:
        mk = ("existing", checklist["id"])
        checklist_merge_key_by_existing_id[checklist["id"]] = mk
        entry = dict(checklist)
        entry["_merge_key"] = mk
        merged_checklists.append(entry)

    existing_checklist_index = {
        (c.get("title"), c.get("priority", "")): checklist_merge_key_by_existing_id[c["id"]]
        for c in existing_checklists
    }

    backup_checklist_target = {}
    for checklist in backup_checklists:
        dedup_key = (checklist.get("title"), checklist.get("priority", ""))
        if dedup_key in existing_checklist_index:
            backup_checklist_target[checklist["id"]] = existing_checklist_index[dedup_key]
            continue
        mk = ("backup", checklist["id"])
        backup_checklist_target[checklist["id"]] = mk
        entry = dict(checklist)
        entry["_merge_key"] = mk
        merged_checklists.append(entry)

    merged_items = []

    existing_item_merge_key_by_id = {}
    existing_top_level_index = {}
    for item in existing_items:
        checklist_mk = checklist_merge_key_by_existing_id.get(item["checklist_id"])
        if checklist_mk is None:
            continue
        mk = ("existing", item["id"])
        existing_item_merge_key_by_id[item["id"]] = mk
        entry = dict(item)
        entry["_merge_key"] = mk
        entry["_checklist_merge_key"] = checklist_mk
        entry["_parent_merge_key"] = (
            existing_item_merge_key_by_id.get(item["parent_id"])
            if item.get("parent_id") is not None else None
        )
        merged_items.append(entry)
        if item.get("parent_id") is None:
            existing_top_level_index[(checklist_mk, item["text"])] = True

    backup_item_merge_key_by_id = {}
    skipped_ids = set()
    for item in backup_items:
        old_id = item["id"]
        parent_old_id = item.get("parent_id")

        if parent_old_id is not None and parent_old_id in skipped_ids:
            skipped_ids.add(old_id)
            continue

        checklist_mk = backup_checklist_target.get(item["checklist_id"])
        if checklist_mk is None:
            skipped_ids.add(old_id)
            continue

        is_top_level = parent_old_id is None
        if is_top_level and (checklist_mk, item["text"]) in existing_top_level_index:
            skipped_ids.add(old_id)
            continue

        mk = ("backup", old_id)
        backup_item_merge_key_by_id[old_id] = mk
        entry = dict(item)
        entry["_merge_key"] = mk
        entry["_checklist_merge_key"] = checklist_mk
        entry["_parent_merge_key"] = (
            backup_item_merge_key_by_id.get(parent_old_id) if parent_old_id is not None else None
        )
        merged_items.append(entry)

    return merged_checklists, merged_items


def _populate_checklists(checklists):
    id_map = {}
    for checklist in checklists:
        new_id = create_checklist(
            checklist["title"],
            priority=checklist.get("priority", ""),
            user_id=checklist["user_id"],
            created_at=checklist.get("created_at"),
        )
        id_map[checklist["_merge_key"]] = new_id
    return id_map


def _populate_checklist_items(items, checklist_id_map):
    item_id_map = {}
    for item in items:
        new_checklist_id = checklist_id_map.get(item["_checklist_merge_key"])
        if new_checklist_id is None:
            continue

        parent_mk = item.get("_parent_merge_key")
        new_parent_id = item_id_map.get(parent_mk) if parent_mk is not None else None

        new_id = create_checklist_item(
            new_checklist_id,
            item["text"],
            parent_id=new_parent_id,
            checked=item.get("checked", False),
            created_at=item.get("created_at"),
            updated_at=item.get("updated_at"),
        )
        item_id_map[item["_merge_key"]] = new_id


def restore_from_manifest(manifest):
    """
    Safely restores the app's data from a manifest dictionary, MERGING
    it with whatever is currently live (see each _merge_* function
    above for per-table dedup rules) rather than replacing it. Builds
    a brand-new database in a temporary file, populates it completely
    with the merged data, and only replaces the live database with it
    after every step succeeds. Raises RestoreError (validation failed,
    nothing was touched) or lets the original exception propagate
    (something failed mid-build, temp file cleaned up, live database
    untouched).
    """
    _validate_manifest(manifest)
    data = manifest["data"]

    # Read from the LIVE database BEFORE _temporary_database ever
    # repoints db.get_db_path() at the new temp file -- this is what
    # gets merged with the backup below.
    existing_categories = [_category_to_dict(row) for row in get_all_categories(DEFAULT_USER_ID)]
    existing_notes = [_note_to_dict(row) for row in get_all_notes(DEFAULT_NOTEBOOK_ID)]
    existing_tasks = [_task_to_dict(row) for row in get_all_tasks(DEFAULT_USER_ID)]
    existing_reminders = _collect_existing_reminders(existing_tasks)
    existing_attachments = _collect_existing_attachments(existing_notes)
    existing_trash = trash_store.get_trash_entries()
    existing_calendar_events = get_all_events(DEFAULT_USER_ID)
    existing_checklists = get_all_checklists(DEFAULT_USER_ID)
    existing_checklist_items = get_all_items_flat()

    merged_categories, backup_category_target = _merge_categories(
        existing_categories, data.get("categories", [])
    )
    merged_tasks, backup_task_target = _merge_tasks(
        existing_tasks, data.get("tasks", []), backup_category_target
    )
    merged_notes, backup_note_target = _merge_notes(
        existing_notes, data.get("notes", []), backup_category_target, backup_task_target
    )
    merged_reminders = _merge_reminders(
        existing_reminders, data.get("reminders", []), backup_task_target
    )
    merged_attachments = _merge_attachments(
        existing_attachments, data.get("attachments", []), backup_note_target
    )
    merged_trash = _merge_trash(
        existing_trash, data.get("trash", []), backup_category_target
    )
    merged_calendar_events = _merge_calendar_events(
        existing_calendar_events, data.get("calendar_events", [])
    )
    merged_checklists, merged_checklist_items = _merge_checklists_and_items(
        existing_checklists, existing_checklist_items,
        data.get("checklists", []), data.get("checklist_items", []),
    )

    # Captured BEFORE _temporary_database ever runs, since that context
    # manager temporarily reassigns db.get_db_path -- this is the real,
    # final destination path we'll swap into at the very end.
    target_db_path = os.path.abspath(db.get_db_path())

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
            ensure_checklist_tables()

            # Order matters: categories before tasks (tasks reference
            # category_id), tasks before notes (notes reference both
            # category_id and task_id), notes before attachments
            # (attachments reference note_id).
            category_id_map = _populate_categories(merged_categories)
            task_id_map = _populate_tasks(merged_tasks, category_id_map)
            note_id_map = _populate_notes(merged_notes, category_id_map, task_id_map)
            _populate_reminders(merged_reminders, task_id_map)
            _populate_calendar_events(merged_calendar_events)
            _populate_attachments(merged_attachments, note_id_map)
            _populate_trash(merged_trash, category_id_map)
            checklist_id_map = _populate_checklists(merged_checklists)
            _populate_checklist_items(merged_checklist_items, checklist_id_map)

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
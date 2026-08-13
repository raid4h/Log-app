"""
database/calendar_queries.py

Data access layer for the Calendar feature's reminders/events.

Deliberately independent of `tasks` and `reminders` (which belong to
the Planner/notification features owned by other screens). This file
owns a single table, `calendar_events`, and is the only place that
table is created or queried -- nothing outside the calendar feature
should need to import from here, and this file should never import
from task_queries.py, reminder_queries.py, category_queries.py, etc.

Only `get_connection` is imported from database/db.py (read-only
import -- db.py itself is never modified by this feature).
"""

from datetime import date

from database.db import get_connection


def create_calendar_events_table():
    """
    Ensures the calendar_events table exists, and migrates in any
    columns added after the table was first created (event_link,
    then the recurring-reminder columns) -- CREATE TABLE IF NOT
    EXISTS alone won't add a column to a table that's already there,
    so each one is checked for explicitly.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS calendar_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            title TEXT NOT NULL,
            event_date TEXT NOT NULL,
            event_time TEXT,
            event_link TEXT,
            is_recurring INTEGER DEFAULT 0,
            completed INTEGER DEFAULT 0,
            original_date TEXT,
            missed_days INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute("PRAGMA table_info(calendar_events)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    migrations = {
        "event_link": "TEXT",
        "is_recurring": "INTEGER DEFAULT 0",
        "completed": "INTEGER DEFAULT 0",
        "original_date": "TEXT",
        "missed_days": "INTEGER DEFAULT 0",
    }
    for column_name, column_type in migrations.items():
        if column_name not in existing_columns:
            cursor.execute(
                f"ALTER TABLE calendar_events ADD COLUMN {column_name} {column_type}"
            )

    conn.commit()
    conn.close()


def create_event(user_id, title, event_date, event_time=None, event_link=None, is_recurring=False):
    """
    Adds one reminder/event on a given date. event_time and
    event_link are both optional. If is_recurring is True,
    original_date is stamped to event_date immediately -- this is
    what missed_days is later calculated against.
    Returns the new row's id.
    """
    conn = get_connection()
    cursor = conn.cursor()
    original_date = event_date if is_recurring else None
    cursor.execute('''
        INSERT INTO calendar_events(
            user_id, title, event_date, event_time, event_link,
            is_recurring, completed, original_date, missed_days
        )
        VALUES(?, ?, ?, ?, ?, ?, 0, ?, 0)
    ''', (
        user_id, title, event_date, event_time, event_link,
        1 if is_recurring else 0, original_date,
    ))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id


def get_events_by_date(event_date, user_id):
    """
    All reminders for one specific day (YYYY-MM-DD), for one user,
    ordered so untimed reminders come first and timed ones follow in
    time order -- matches how the reference UI lists "any time" items
    before scheduled ones.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, user_id, title, event_date, event_time, event_link,
               is_recurring, completed, original_date, missed_days, created_at
        FROM calendar_events
        WHERE event_date = ? AND user_id = ?
        ORDER BY
            CASE WHEN event_time IS NULL OR event_time = '' THEN 0 ELSE 1 END,
            event_time ASC
    ''', (event_date, user_id))
    rows = cursor.fetchall()
    conn.close()
    return [_row_to_dict(row) for row in rows]


def get_all_event_dates(year, month, user_id):
    """
    Returns a set of 'YYYY-MM-DD' strings for every date in the given
    month/year that has at least one reminder, for the given user.
    Used to draw the small dot under a date in the month grid.
    """
    conn = get_connection()
    cursor = conn.cursor()
    month_prefix = f"{year:04d}-{month:02d}-"
    cursor.execute('''
        SELECT DISTINCT event_date
        FROM calendar_events
        WHERE user_id = ? AND event_date LIKE ?
    ''', (user_id, f"{month_prefix}%"))
    rows = cursor.fetchall()
    conn.close()
    return {row[0] for row in rows}


def get_all_events(user_id):
    """
    All calendar events for a user, across every date -- unlike
    get_events_by_date/get_all_event_dates (scoped to one day or one
    month for the screen's own display), this returns everything.
    Used by services/backup_builder.py to include calendar reminders
    in a full backup.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, user_id, title, event_date, event_time, event_link,
               is_recurring, completed, original_date, missed_days, created_at
        FROM calendar_events
        WHERE user_id = ?
        ORDER BY event_date ASC, event_time ASC
    ''', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [_row_to_dict(row) for row in rows]


def get_event_by_id(event_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, user_id, title, event_date, event_time, event_link,
               is_recurring, completed, original_date, missed_days, created_at
        FROM calendar_events
        WHERE id = ?
    ''', (event_id,))
    row = cursor.fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def update_event(event_id, title, event_time=None, event_link=None, is_recurring=False):
    """
    Edits a reminder's title/time/link/recurring flag. Date is
    intentionally not editable here -- moving a reminder to a
    different date is a delete + recreate from the UI layer.

    Turning recurring ON for the first time stamps original_date so
    missed-day counts start counting from the right point. Turning it
    OFF clears original_date and resets missed_days, since a
    non-recurring reminder never rolls forward again.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT event_date, original_date, missed_days FROM calendar_events WHERE id = ?",
        (event_id,),
    )
    row = cursor.fetchone()
    event_date, original_date, missed_days = row if row else (None, None, 0)

    if is_recurring:
        if not original_date:
            original_date = event_date
    else:
        original_date = None
        missed_days = 0

    cursor.execute('''
        UPDATE calendar_events
        SET title = ?, event_time = ?, event_link = ?, is_recurring = ?,
            original_date = ?, missed_days = ?
        WHERE id = ?
    ''', (
        title, event_time, event_link, 1 if is_recurring else 0,
        original_date, missed_days, event_id,
    ))
    conn.commit()
    conn.close()


def mark_event_completed(event_id, completed):
    """Toggles the completed flag. Recurring reminders stop rolling
    forward once completed -- see roll_forward_recurring_events."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE calendar_events SET completed = ? WHERE id = ?",
        (1 if completed else 0, event_id),
    )
    conn.commit()
    conn.close()


def roll_forward_recurring_events(user_id):
    """
    Moves every recurring, incomplete reminder whose date has already
    passed straight to today, and recalculates missed_days as the gap
    between original_date and today. Meant to be called once each
    time the Calendar screen is opened (see CalendarScreen.on_pre_enter)
    -- cheap (one UPDATE per stale reminder), no background timer.
    """
    conn = get_connection()
    cursor = conn.cursor()
    today_str = date.today().isoformat()

    cursor.execute('''
        SELECT id, event_date, original_date
        FROM calendar_events
        WHERE user_id = ? AND is_recurring = 1 AND completed = 0 AND event_date < ?
    ''', (user_id, today_str))
    stale_events = cursor.fetchall()

    for event_id, event_date, original_date in stale_events:
        base_date = original_date or event_date
        try:
            missed = (
                date.fromisoformat(today_str) - date.fromisoformat(base_date)
            ).days
        except ValueError:
            missed = 0

        cursor.execute('''
            UPDATE calendar_events
            SET event_date = ?, missed_days = ?
            WHERE id = ?
        ''', (today_str, max(missed, 0), event_id))

    conn.commit()
    conn.close()


def delete_event(event_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        DELETE FROM calendar_events
        WHERE id = ?
    ''', (event_id,))
    conn.commit()
    conn.close()


def _row_to_dict(row):
    return {
        "id": row[0],
        "user_id": row[1],
        "title": row[2],
        "event_date": row[3],
        "event_time": row[4],
        "event_link": row[5],
        "is_recurring": bool(row[6]),
        "completed": bool(row[7]),
        "original_date": row[8],
        "missed_days": row[9],
        "created_at": row[10],
    }
    
def get_next_calendar_event(user_id):
    """
    Returns the soonest upcoming, not-completed calendar event for a
    user (today or later, ordered by date then time — untimed events
    on a given date sort before timed ones, same convention as
    get_events_by_date). Returns a dict, or None if there's nothing
    upcoming. Read-only addition for HomeScreen's "Next Up" card --
    does not affect any other calendar_queries function.
    """
    conn = get_connection()
    cursor = conn.cursor()
    today_str = date.today().isoformat()
    cursor.execute('''
        SELECT id, user_id, title, event_date, event_time, event_link,
               is_recurring, completed, original_date, missed_days, created_at
        FROM calendar_events
        WHERE user_id = ? AND completed = 0 AND event_date >= ?
        ORDER BY
            event_date ASC,
            CASE WHEN event_time IS NULL OR event_time = '' THEN 0 ELSE 1 END,
            event_time ASC
        LIMIT 1
    ''', (user_id, today_str))
    row = cursor.fetchone()
    conn.close()
    return _row_to_dict(row) if row else None
"""
One-time migration: adds the columns calendar_screen.py's "Add Task"
form needs, on top of activity_type from the earlier migration.
Safe to run multiple times.

due_time          - optional HH:MM string, task's due_date already exists
link              - optional URL string, shown as "Open link" in AgendaTaskCard
carry_forward     - 1/0, whether an incomplete task should roll to the next day
notify_enabled    - 1/0, whether to fire a reminder at due_time
original_due_date - set once at creation time, never changed after. Lets us
                    tell "is_carried" (current due_date != original_due_date)
                    apart from a task that was always due today.

Run this once: python migrate_add_calendar_fields.py
"""
from database.db import get_connection

NEW_COLUMNS = [
    ("due_time", "TEXT"),
    ("link", "TEXT"),
    ("carry_forward", "INTEGER DEFAULT 0"),
    ("notify_enabled", "INTEGER DEFAULT 0"),
    ("original_due_date", "TEXT"),
]

def migrate():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(tasks)")
    existing_columns = [row[1] for row in cursor.fetchall()]

    for column_name, column_def in NEW_COLUMNS:
        if column_name not in existing_columns:
            cursor.execute(f"ALTER TABLE tasks ADD COLUMN {column_name} {column_def}")
            print(f"added {column_name} to tasks")
        else:
            print(f"{column_name} already exists, skipping")

    # Backfill: any existing task without original_due_date gets its
    # current due_date as its "original" -- otherwise every pre-existing
    # task would look permanently "carried forward".
    cursor.execute('''
        UPDATE tasks SET original_due_date = due_date
        WHERE original_due_date IS NULL
    ''')

    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
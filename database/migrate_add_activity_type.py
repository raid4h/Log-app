"""
One-time migration: adds activity_type to the tasks table.
Safe to run multiple times - it checks if the column already exists first.

activity_type values we'll use: 'study', 'event', 'task', 'shopping'
(defaults to 'task' for anything already in the db / anything not set)

Run this once: python migrate_add_activity_type.py
"""
from database.db import get_connection

def migrate():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(tasks)")
    columns = [row[1] for row in cursor.fetchall()]

    if "activity_type" not in columns:
        cursor.execute('''
            ALTER TABLE tasks ADD COLUMN activity_type TEXT DEFAULT 'task'
        ''')
        conn.commit()
        print("added activity_type column to tasks")
    else:
        print("activity_type already exists, skipping")

    conn.close()

if __name__ == "__main__":
    migrate()
from database.db import get_connection
from datetime import datetime
from database.calendar_queries import get_next_calendar_event


def get_today_tasks(user_id, today_date):
    """
    Powers the Home screen 'Today's Plan' list.
    today_date should be a string 'YYYY-MM-DD' -- matched against the
    date portion of due_date (which now stores 'YYYY-MM-DD HH:MM').
    Only shows unfinished tasks/events -- completed ones drop off Home
    once checked off (they're still visible on the Calendar screen).
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT
            tasks.id, tasks.title, tasks.priority, tasks.is_completed,
            tasks.due_date, tasks.activity_type, tasks.category_id,
            categories.name, categories.color,
            (SELECT COUNT(*) FROM notes WHERE notes.task_id = tasks.id) as note_count,
            (SELECT COUNT(*) FROM pomodoro_sessions
                WHERE pomodoro_sessions.task_id = tasks.id AND completed=1) as pomodoro_completed
        FROM tasks
        LEFT JOIN categories ON tasks.category_id = categories.id
        WHERE tasks.user_id=? AND tasks.due_date LIKE ? AND tasks.is_completed=0
        ORDER BY tasks.due_date ASC
    ''', (user_id, f"{today_date}%"))

    rows = cursor.fetchall()
    conn.close()

    tasks = []
    for r in rows:
        tasks.append({
            "id": r[0],
            "title": r[1],
            "priority": r[2],
            "is_completed": r[3],
            "due_date": r[4],
            "activity_type": r[5],
            "category_id": r[6],
            "category_name": r[7],
            "category_color": r[8],
            "note_count": r[9],
            "pomodoro_completed": r[10],
        })
    return tasks


def get_task_detail(task_id):
    """
    Powers ActivityDetailScreen. One call gives you everything:
    task info, linked notes, pomodoro sessions/progress, reminders.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT tasks.id, tasks.title, tasks.priority, tasks.is_completed,
               tasks.due_date, tasks.activity_type, tasks.category_id,
               categories.name, categories.color
        FROM tasks
        LEFT JOIN categories ON tasks.category_id = categories.id
        WHERE tasks.id=?
    ''', (task_id,))
    task_row = cursor.fetchone()

    if task_row is None:
        conn.close()
        return None

    task = {
        "id": task_row[0],
        "title": task_row[1],
        "priority": task_row[2],
        "is_completed": task_row[3],
        "due_date": task_row[4],
        "activity_type": task_row[5],
        "category_id": task_row[6],
        "category_name": task_row[7],
        "category_color": task_row[8],
    }

    cursor.execute('''
        SELECT id, title, content, updated_at
        FROM notes
        WHERE task_id=?
        ORDER BY updated_at DESC
    ''', (task_id,))
    task["notes"] = cursor.fetchall()

    cursor.execute('''
        SELECT id, started_at, completed, duration
        FROM pomodoro_sessions
        WHERE task_id=?
        ORDER BY started_at DESC
    ''', (task_id,))
    sessions = cursor.fetchall()
    task["pomodoro_sessions"] = sessions
    task["pomodoro_completed_count"] = sum(1 for s in sessions if s[2] == 1)

    cursor.execute('''
        SELECT id, remind_at, is_active
        FROM reminders
        WHERE task_id=?
        ORDER BY remind_at ASC
    ''', (task_id,))
    task["reminders"] = cursor.fetchall()

    conn.close()
    return task


def get_continue_studying(user_id):
    """
    Powers the Home screen 'Continue Studying' card.
    Finds the most recent task that has an unfinished pomodoro session.
    Returns a dict or None if there's nothing to resume.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT tasks.id, tasks.title, pomodoro_sessions.id, pomodoro_sessions.started_at
        FROM pomodoro_sessions
        JOIN tasks ON pomodoro_sessions.task_id = tasks.id
        WHERE tasks.user_id=? AND pomodoro_sessions.completed=0
        ORDER BY pomodoro_sessions.started_at DESC
        LIMIT 1
    ''', (user_id,))
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return {
        "task_id": row[0],
        "task_title": row[1],
        "session_id": row[2],
        "started_at": row[3],
    }


def get_next_event(user_id):
    """
    Powers Home's "Next Up" card. Compares the soonest upcoming task
    (activity_type 'event' or 'task') against the soonest upcoming
    calendar reminder, and returns whichever comes first, normalized
    to due_date/due_time/title/id/category_id -- callers (HomeScreen)
    don't need to know or care which table it came from.
    """
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute('''
        SELECT id, title, due_date, due_time, category_id
        FROM tasks
        WHERE user_id=? AND activity_type IN ('event', 'task') AND is_completed=0
          AND (due_date || ' ' || COALESCE(due_time, '23:59')) >= ?
        ORDER BY due_date ASC, COALESCE(due_time, '23:59') ASC
        LIMIT 1
    ''', (user_id, now_str))
    task_row = cursor.fetchone()
    conn.close()

    task_candidate = None
    if task_row is not None:
        task_candidate = {
            "id": task_row[0], "title": task_row[1],
            "due_date": task_row[2], "due_time": task_row[3],
            "category_id": task_row[4],
        }

    calendar_row = get_next_calendar_event(user_id)
    calendar_candidate = None
    if calendar_row is not None:
        calendar_candidate = {
            "id": calendar_row["id"], "title": calendar_row["title"],
            "due_date": calendar_row["event_date"], "due_time": calendar_row["event_time"],
            "category_id": None,  # calendar_events has no category column
        }

    def sort_key(item):
        return f"{item['due_date']} {item['due_time'] or '23:59'}"

    if task_candidate and calendar_candidate:
        return task_candidate if sort_key(task_candidate) <= sort_key(calendar_candidate) else calendar_candidate
    return task_candidate or calendar_candidate

def create_study_task(user_id, title, duration):
    conn = get_connection()
    cursor = conn.cursor()

    today = datetime.now().strftime("%Y-%m-%d")
    time = datetime.now().strftime("%H:%M")

    cursor.execute("""
        INSERT INTO tasks
        (
            user_id,
            title,
            due_date,
            due_time,
            activity_type,
            priority,
            is_completed
        ) VALUES (?, ?, ?, ?, 'study', 'medium', 0)
    """, (user_id, title, today, time))

    task_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return task_id
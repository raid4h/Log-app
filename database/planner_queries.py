from database.db import get_connection
from datetime import datetime
from database.calendar_queries import get_next_calendar_event
from database.calendar_queries import get_events_by_date
from services.checklist_store import get_all_checklists, get_items_by_checklist

def get_today_tasks(user_id, today_date):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT
        tasks.id, tasks.title, tasks.priority, tasks.is_completed,
        tasks.due_date, tasks.activity_type, tasks.category_id,
        categories.name, categories.color,
        (SELECT COUNT(*) FROM notes WHERE notes.task_id = tasks.id) as note_count
    FROM tasks
    LEFT JOIN categories ON tasks.category_id = categories.id
    WHERE tasks.user_id=? AND tasks.due_date LIKE ?
    ORDER BY tasks.due_date DESC
    ''', (user_id, f"{today_date}%"))
    rows = cursor.fetchall()
    conn.close()

    tasks = []
    for r in rows:
        tasks.append({
            "id": r[0], "title": r[1], "priority": r[2], "is_completed": r[3],
            "due_date": r[4], "activity_type": r[5], "category_id": r[6],
            "category_name": r[7], "category_color": r[8],
            "note_count": r[9],
        })

    # -- calendar events due today --
    for event in get_events_by_date(today_date, user_id):
        if event.get("completed"):
            continue
        tasks.append({
            "id": f"cal-{event['id']}",
            "title": event.get("title", ""),
            "priority": None, "is_completed": 0,
            "due_date": f"{today_date} {event.get('event_time') or ''}".strip(),
            "activity_type": "event",
            "category_id": None, "category_name": None, "category_color": None,
            "note_count": 0,
        })
    # -- checklist items in Today's Log --
    # v2: previously this showed only items CREATED today, for every
    # checklist unconditionally. Replaced with the "Show in Today's
    # Log" opt-in rule from screens/checklist_detail_screen.py's edit
    # popup (stored on the checklist itself via
    # services/checklist_store.py's add_to_logs/calendar_event_id):
    #   - add_to_logs is OFF (default) -> skip this checklist entirely,
    #     regardless of when its items were created.
    #   - add_to_logs is ON and calendar_event_id is NOT set -> show
    #     every unchecked item, every day, no date restriction.
    #   - add_to_logs is ON and calendar_event_id IS set -> show items
    #     only on the day that matches the linked calendar event's
    #     own event_date (looked up via get_events_by_date, same
    #     helper already used above for the plain calendar-events
    #     block, so no new calendar lookup function is introduced).
    todays_calendar_event_ids = {
        event["id"] for event in get_events_by_date(today_date, user_id)
    }
    for checklist in get_all_checklists(user_id):
        if not checklist.get("add_to_logs"):
            continue

        linked_event_id = checklist.get("calendar_event_id")
        if linked_event_id is not None and linked_event_id not in todays_calendar_event_ids:
            # Linked to a specific date, and today isn't that date.
            continue

        for item in get_items_by_checklist(checklist["id"]):
            if item["checked"]:
                continue
            tasks.append({
                "id": f"chk-{item['id']}",
                "title": item["text"],
                "priority": None, "is_completed": 0,
                "due_date": item["created_at"],
                "activity_type": "checklist_item",
                "category_id": None, "category_name": None, "category_color": None,
                "note_count": 0,
                "_checklist_id": checklist["id"],  # needed so tapping the row can open the right checklist
                "_item_id": item["id"],  # raw checklist_items.id, so Home can toggle it directly via set_checked()
            })

    tasks.sort(key=lambda t: t["due_date"] or "")
    return tasks


def get_task_detail(task_id):
    """
    Powers ActivityDetailScreen. One call gives you everything:
    task info, linked notes, reminders.
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
        SELECT id, remind_at, is_active
        FROM reminders
        WHERE task_id=?
        ORDER BY remind_at ASC
    ''', (task_id,))
    task["reminders"] = cursor.fetchall()

    conn.close()
    return task


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
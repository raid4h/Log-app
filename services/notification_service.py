from database.reminder_queries import (
    deactivate_reminders,
    get_triggered_reminders,
)
from database.calendar_queries import (
    get_triggered_calendar_events,
    mark_calendar_event_notified,
)


def collect_due_notifications(user_id=1):
    """
    Return due notifications and atomically deactivate each reminder.

    The UI polls this function with Kivy Clock. Deactivation prevents the same
    reminder from appearing more than once.

    Merges two sources:
      - task reminders (database/reminder_queries.py, the `reminders` table)
      - calendar events (database/calendar_queries.py, the `calendar_events`
        table) -- only timed events fire; untimed/all-day events never
        appear here, see get_triggered_calendar_events's docstring.

    user_id defaults to 1 to match the single-user fallback used
    elsewhere (e.g. CalendarScreen._user_id()). Pass the real
    App.get_running_app().user_id from the caller once multi-user
    support exists.
    """
    notifications = []

    for row in get_triggered_reminders():
        reminder_id, task_id, remind_at, _, title, due_date, due_time = row
        deactivate_reminders(reminder_id)
        notifications.append(
            {
                "reminder_id": reminder_id,
                "task_id": task_id,
                "calendar_event_id": None,
                "title": title,
                "remind_at": remind_at,
                "due_date": due_date,
                "due_time": due_time,
            }
        )

    for event in get_triggered_calendar_events(user_id):
        mark_calendar_event_notified(event["id"])
        notifications.append(
            {
                "reminder_id": None,
                "task_id": None,
                "calendar_event_id": event["id"],
                "title": event["title"],
                "remind_at": f'{event["event_date"]} {event["event_time"]}',
                "due_date": event["event_date"],
                "due_time": event["event_time"],
            }
        )

    return notifications


def send_system_notification(title, message):
    """
    Use a native notification when Plyer is available.

    Returns False on desktop/development environments without Plyer so the
    caller can display an in-app popup instead.
    """
    try:
        from plyer import notification

        notification.notify(
            title=title,
            message=message,
            app_name="NoteNest",
            timeout=10,
        )
        return True
    except Exception:
        return False
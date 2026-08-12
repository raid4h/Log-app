class Task:
    def __init__(self, id, title, priority, is_completed, due_date, due_time, user_id,
                 category_id=None, activity_type="task", link="", carry_forward=0,
                 notify_enabled=0, original_due_date=None):
        self.id = id
        self.title = title
        self.priority = priority
        self.is_completed = is_completed
        self.due_date = due_date
        self.due_time = due_time
        self.user_id = user_id
        self.category_id = category_id
        self.activity_type = activity_type
        self.link = link
        self.carry_forward = carry_forward
        self.notify_enabled = notify_enabled
        self.original_due_date = original_due_date

    @classmethod
    def from_row(cls, row):
        """
        Builds a Task from a raw sqlite row, in the exact column order
        tasks is created in db.py:
        id, title, priority, is_completed, due_date, due_time, user_id,
        category_id, activity_type, link, carry_forward, notify_enabled,
        original_due_date
        """
        if row is None:
            return None
        return cls(
            id=row[0], title=row[1], priority=row[2], is_completed=row[3],
            due_date=row[4], due_time=row[5], user_id=row[6],
            category_id=row[7], activity_type=row[8] if len(row) > 8 else "task",
            link=row[9] if len(row) > 9 else "",
            carry_forward=row[10] if len(row) > 10 else 0,
            notify_enabled=row[11] if len(row) > 11 else 0,
            original_due_date=row[12] if len(row) > 12 else None,
        )
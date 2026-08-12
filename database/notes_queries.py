from database.db import get_connection
from datetime import datetime

def create_notes(notebook_id, title, content, category_id=None, is_pinned=0, is_archived=0, task_id=None, created_at=None, updated_at=None):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # created_at/updated_at default to None so every existing caller
    # (editor screens, duplicate_notes, etc.) keeps stamping "now" for
    # both exactly like before. Only restore_engine.py passes real
    # values through, to preserve a note's original timestamps across
    # a backup/restore cycle instead of resetting them to "now".
    final_created_at = created_at if created_at is not None else now
    final_updated_at = updated_at if updated_at is not None else now
    cursor.execute('''
    INSERT INTO notes (notebook_id, title, content, category_id, is_pinned, is_archived, created_at, updated_at, task_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (notebook_id, title, content, category_id, is_pinned, is_archived, final_created_at, final_updated_at, task_id))
    note_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return note_id
def get_all_notes(notebook_id):
    conn=get_connection()
    cursor=conn.cursor()
    cursor.execute('''
    SELECT * FROM notes
    WHERE notebook_id = ?
    ORDER BY is_pinned DESC, updated_at DESC
    ''', (notebook_id,))
    notes=cursor.fetchall()
    conn.close()
    return notes
def get_notes_by_id(note_id):
    conn=get_connection()
    cursor=conn.cursor()
    cursor.execute('''
    SELECT * FROM notes
    WHERE id=?
    ''',(note_id,))
    note=cursor.fetchone()
    conn.close()
    return note
def update_notes(note_id, title, content):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        UPDATE notes SET title=?, content=?, updated_at=?
        WHERE id=?
    ''', (title, content, now, note_id))
    conn.commit()
    conn.close()
def delete_notes(note_id):
    conn=get_connection()
    cursor=conn.cursor()
    cursor.execute('''
    DELETE FROM notes
    WHERE id=?
    ''',(note_id,))
    conn.commit()
    conn.close()
def search_notes(keyword):
    conn=get_connection()
    cursor=conn.cursor()
    cursor.execute('''
    SELECT * FROM notes
    WHERE title LIKE ? OR content LIKE ?
    ''',(f'%{keyword}%', f'%{keyword}%'))
    results=cursor.fetchall()
    conn.close()
    return results
def pin_notes(note_id,is_pinned):
    conn=get_connection()
    cursor=conn.cursor()
    cursor.execute('''
    UPDATE notes SET is_pinned=?
    WHERE id=?
    ''',(is_pinned,note_id))
    conn.commit()
    conn.close()
def archive_notes(note_id,is_archived):
    conn=get_connection()
    cursor=conn.cursor()
    cursor.execute('''
    UPDATE notes SET is_archived=?
    WHERE id=?
    ''',(is_archived,note_id))
    conn.commit()
    conn.close()
def sort_notes(notebook_id,sort_by="date"):
    if sort_by=="title":
      order_clause="title ASC"
    else:
      order_clause="updated_at DESC"
    conn=get_connection()
    cursor=conn.cursor()
    cursor.execute(f'''
      SELECT * FROM notes
      WHERE notebook_id=?
      ORDER BY {order_clause}
      ''',(notebook_id,))
    notes=cursor.fetchall()
    conn.close()
    return notes

def duplicate_notes(note_id):
    og_note=get_notes_by_id(note_id)
    notebook_id=og_note[1]
    title=og_note[2]
    content=og_note[3]
    category_id = og_note[8]

    create_notes(notebook_id,title,content,category_id=category_id)
def get_notes_by_task(task_id):
    conn=get_connection()
    cursor=conn.cursor()
    cursor.execute('''
    SELECT * FROM notes
    WHERE task_id=?
    ORDER BY updated_at DESC
    ''',(task_id,))
    notes=cursor.fetchall()
    conn.close()
    return notes
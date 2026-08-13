import sqlite3
import os
from kivy.app import App

def get_db_path():
    app = App.get_running_app()
    if app is not None:
        return os.path.join(app.user_data_dir, "MyApp.db")
    return "MyApp.db"  # fallback for scripts/tests run without a running App

def get_connection():
    conn= sqlite3.connect(get_db_path())
    return conn

def create_tables():
    conn=get_connection()
    cursor=conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name text not null,
            email text unique not null,
            password text not null
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notebooks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            name text not null,
            color text,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
            ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name text not null,
            color text,
            user_id INTEGER REFERENCES users(id)
        )
            ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notebook_id INTEGER REFERENCES notebooks(id),
            title text not null,
            content text,
            is_pinned INTEGER DEFAULT 0,
            is_archived INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            category_id INTEGER REFERENCES categories(id),
            task_id INTEGER REFERENCES tasks(id)
        )
            ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        priority TEXT,
        is_completed INTEGER DEFAULT 0,
        due_date TEXT,
        due_time TEXT,
        user_id INTEGER REFERENCES users(id),
        category_id INTEGER REFERENCES categories(id),
        activity_type TEXT DEFAULT 'task',
        link TEXT,
        carry_forward INTEGER DEFAULT 0,
        notify_enabled INTEGER DEFAULT 0,
        original_due_date TEXT
        )
            ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attachments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            note_id INTEGER REFERENCES notes(id),
            file_path text,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
            ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER REFERENCES tasks(id),
            remind_at TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
            ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pomodoro_sessions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER REFERENCES tasks(id),
            started_at TIMESTAMP,
            completed INTEGER DEFAULT 0,
            duration INTEGER
        )
            ''')
    conn.commit()
    conn.close()
    
if __name__ == "__main__":
    create_tables()
    print("Database and tables created successfully!") 
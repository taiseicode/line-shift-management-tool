import sqlite3

from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_tables():
    conn = get_conn()
    try:
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                line_user_id TEXT UNIQUE,
                name TEXT,
                active INTEGER NOT NULL DEFAULT 1
            )
        """)

        user_columns = [row["name"] for row in c.execute("PRAGMA table_info(users)").fetchall()]
        if "active" not in user_columns:
            c.execute("ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1")

        # off: 1=休み, 0=出勤
        c.execute("""
            CREATE TABLE IF NOT EXISTS shift_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                off INTEGER NOT NULL DEFAULT 0,
                start_time TEXT,
                end_time TEXT,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, date),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)

        # 日ごとの必要人数
        c.execute("""
            CREATE TABLE IF NOT EXISTS required_staff (
                date TEXT PRIMARY KEY,
                required_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        conn.commit()
    finally:
        conn.close()

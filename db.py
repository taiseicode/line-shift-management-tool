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
                active INTEGER NOT NULL DEFAULT 1,
                display_order INTEGER
            )
        """)

        user_columns = [row["name"] for row in c.execute("PRAGMA table_info(users)").fetchall()]
        if "active" not in user_columns:
            c.execute("ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
        if "display_order" not in user_columns:
            c.execute("ALTER TABLE users ADD COLUMN display_order INTEGER")
        users_without_order = c.execute("""
            SELECT id
            FROM users
            WHERE display_order IS NULL
            ORDER BY id
        """).fetchall()
        next_order_row = c.execute("SELECT COALESCE(MAX(display_order), 0) + 1 AS next_order FROM users").fetchone()
        next_order = int(next_order_row["next_order"] or 1)
        for row in users_without_order:
            c.execute("UPDATE users SET display_order = ? WHERE id = ?", (next_order, row["id"]))
            next_order += 1

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

        c.execute("""
            CREATE TABLE IF NOT EXISTS confirmed_shifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                is_assigned INTEGER NOT NULL DEFAULT 1,
                source_entry_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, date),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(source_entry_id) REFERENCES shift_entries(id)
            )
        """)

        confirmed_shift_columns = [row["name"] for row in c.execute("PRAGMA table_info(confirmed_shifts)").fetchall()]
        if "is_assigned" not in confirmed_shift_columns:
            c.execute("ALTER TABLE confirmed_shifts ADD COLUMN is_assigned INTEGER NOT NULL DEFAULT 1")
        c.execute("UPDATE confirmed_shifts SET is_assigned = 1 WHERE is_assigned IS NULL")

        c.execute("""
            CREATE TABLE IF NOT EXISTS user_pay_settings (
                user_id INTEGER PRIMARY KEY,
                hourly_wage INTEGER,
                break_rule TEXT NOT NULL DEFAULT 'legal_jp',
                night_enabled INTEGER NOT NULL DEFAULT 1,
                overtime_enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)

        conn.commit()
    finally:
        conn.close()

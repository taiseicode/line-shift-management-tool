import sqlite3
from threading import Lock

from config import DATABASE_URL, DB_PATH


USE_POSTGRES = bool(DATABASE_URL)
_db_mode_logged = False
_postgres_pool = None
_postgres_pool_lock = Lock()
_table_columns_cache = {}


def using_postgres() -> bool:
    return USE_POSTGRES


def _log_db_mode_once():
    global _db_mode_logged
    if _db_mode_logged:
        return
    if USE_POSTGRES:
        print("Using PostgreSQL database", flush=True)
    else:
        print(f"Using SQLite database: {DB_PATH}", flush=True)
    _db_mode_logged = True


def _convert_qmark_to_psycopg(sql: str) -> str:
    """Convert ? placeholders outside SQL strings to psycopg %s placeholders."""
    result = []
    in_single = False
    in_double = False
    index = 0
    while index < len(sql):
        char = sql[index]
        if char == "'" and not in_double:
            result.append(char)
            if in_single and index + 1 < len(sql) and sql[index + 1] == "'":
                result.append(sql[index + 1])
                index += 2
                continue
            in_single = not in_single
        elif char == '"' and not in_single:
            result.append(char)
            in_double = not in_double
        elif char == "?" and not in_single and not in_double:
            result.append("%s")
        else:
            result.append(char)
        index += 1
    return "".join(result)


class PostgresCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=None):
        self._cursor.execute(_convert_qmark_to_psycopg(sql), params)
        return self

    def executemany(self, sql, seq_of_params):
        self._cursor.executemany(_convert_qmark_to_psycopg(sql), seq_of_params)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def close(self):
        return self._cursor.close()

    def __iter__(self):
        return iter(self._cursor)


class PostgresConnection:
    def __init__(self, pool_context, conn):
        self._pool_context = pool_context
        self._conn = conn
        self._returned = False
        self._committed = False

    def cursor(self):
        return PostgresCursor(self._conn.cursor())

    def commit(self):
        self._committed = True
        return self._conn.commit()

    def rollback(self):
        self._committed = True
        return self._conn.rollback()

    def close(self):
        if self._returned:
            return
        try:
            if not self._committed:
                self._conn.rollback()
        finally:
            self._pool_context.__exit__(None, None, None)
            self._returned = True


def _get_postgres_pool():
    global _postgres_pool
    if _postgres_pool is not None:
        return _postgres_pool
    with _postgres_pool_lock:
        if _postgres_pool is not None:
            return _postgres_pool
        try:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
        except ImportError as exc:
            raise RuntimeError("DATABASE_URL is set, but psycopg pool support is not installed") from exc
        _postgres_pool = ConnectionPool(
            DATABASE_URL,
            min_size=1,
            max_size=3,
            timeout=10,
            kwargs={"row_factory": dict_row},
            open=True,
        )
        _postgres_pool.wait(timeout=10)
        return _postgres_pool


def get_conn():
    _log_db_mode_once()
    if USE_POSTGRES:
        pool_context = _get_postgres_pool().connection()
        conn = pool_context.__enter__()
        return PostgresConnection(pool_context, conn)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_table_columns(table_name: str):
    cache_key = table_name.strip()
    if cache_key in _table_columns_cache:
        return list(_table_columns_cache[cache_key])
    conn = get_conn()
    try:
        c = conn.cursor()
        if USE_POSTGRES:
            rows = c.execute(
                """
                SELECT column_name AS name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = ?
                ORDER BY ordinal_position
                """,
                (table_name,),
            ).fetchall()
        else:
            rows = c.execute(f"PRAGMA table_info({table_name})").fetchall()
        columns = [row["name"] for row in rows]
        _table_columns_cache[cache_key] = tuple(columns)
        return columns
    finally:
        conn.close()


def invalidate_table_columns_cache(table_name: str = None):
    if table_name is None:
        _table_columns_cache.clear()
    else:
        _table_columns_cache.pop(table_name.strip(), None)


def _get_table_columns_with_cursor(c, table_name: str):
    if USE_POSTGRES:
        rows = c.execute(
            """
            SELECT column_name AS name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = ?
            ORDER BY ordinal_position
            """,
            (table_name,),
        ).fetchall()
    else:
        rows = c.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [row["name"] for row in rows]


def _ensure_user_display_order(c):
    rows = c.execute("""
        SELECT id
        FROM users
        WHERE display_order IS NULL
        ORDER BY id
    """).fetchall()
    next_order_row = c.execute("SELECT COALESCE(MAX(display_order), 0) + 1 AS next_order FROM users").fetchone()
    next_order = int(next_order_row["next_order"] or 1)
    for row in rows:
        c.execute("UPDATE users SET display_order = ? WHERE id = ?", (next_order, row["id"]))
        next_order += 1


def _init_sqlite_tables(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            line_user_id TEXT UNIQUE,
            name TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            display_order INTEGER
        )
    """)

    user_columns = _get_table_columns_with_cursor(c, "users")
    if "active" not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
    if "display_order" not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN display_order INTEGER")
    _ensure_user_display_order(c)

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
            start_time TEXT,
            end_time TEXT,
            is_assigned INTEGER NOT NULL DEFAULT 1,
            source_entry_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, date),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(source_entry_id) REFERENCES shift_entries(id)
        )
    """)

    confirmed_shift_columns = _get_table_columns_with_cursor(c, "confirmed_shifts")
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


def _init_postgres_tables(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
            line_user_id TEXT UNIQUE,
            name TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            display_order INTEGER
        )
    """)
    c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS active INTEGER NOT NULL DEFAULT 1")
    c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS display_order INTEGER")
    _ensure_user_display_order(c)

    c.execute("""
        CREATE TABLE IF NOT EXISTS shift_entries (
            id INTEGER PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            date TEXT NOT NULL,
            off INTEGER NOT NULL DEFAULT 0,
            start_time TEXT,
            end_time TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, date)
        )
    """)

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
            id INTEGER PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            date TEXT NOT NULL,
            start_time TEXT,
            end_time TEXT,
            is_assigned INTEGER NOT NULL DEFAULT 1,
            source_entry_id INTEGER REFERENCES shift_entries(id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, date)
        )
    """)
    c.execute("ALTER TABLE confirmed_shifts ADD COLUMN IF NOT EXISTS is_assigned INTEGER NOT NULL DEFAULT 1")
    c.execute("UPDATE confirmed_shifts SET is_assigned = 1 WHERE is_assigned IS NULL")

    c.execute("""
        CREATE TABLE IF NOT EXISTS user_pay_settings (
            user_id INTEGER PRIMARY KEY REFERENCES users(id),
            hourly_wage INTEGER,
            break_rule TEXT NOT NULL DEFAULT 'legal_jp',
            night_enabled INTEGER NOT NULL DEFAULT 1,
            overtime_enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    c.execute("ALTER TABLE user_pay_settings ADD COLUMN IF NOT EXISTS hourly_wage INTEGER")
    c.execute("ALTER TABLE user_pay_settings ADD COLUMN IF NOT EXISTS break_rule TEXT NOT NULL DEFAULT 'legal_jp'")
    c.execute("ALTER TABLE user_pay_settings ADD COLUMN IF NOT EXISTS night_enabled INTEGER NOT NULL DEFAULT 1")
    c.execute("ALTER TABLE user_pay_settings ADD COLUMN IF NOT EXISTS overtime_enabled INTEGER NOT NULL DEFAULT 1")
    c.execute("ALTER TABLE user_pay_settings ADD COLUMN IF NOT EXISTS created_at TEXT")
    c.execute("ALTER TABLE user_pay_settings ADD COLUMN IF NOT EXISTS updated_at TEXT")


def init_tables():
    invalidate_table_columns_cache()
    conn = get_conn()
    try:
        c = conn.cursor()
        if USE_POSTGRES:
            _init_postgres_tables(c)
        else:
            _init_sqlite_tables(c)
        conn.commit()
    finally:
        conn.close()
    invalidate_table_columns_cache()

"""Remove dummy users and related dummy data from the SQLite database.

This script only deletes rows for users whose line_user_id starts with
``dummy_user_``. Existing real users and their shifts are left untouched.
Deletion order intentionally follows dependent data first:

1. confirmed_shifts
2. shift_entries
3. users
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is optional for this helper.
    load_dotenv = None


ROOT = Path(__file__).resolve().parents[1]
DUMMY_PREFIX = "dummy_user_"


def load_db_path() -> Path:
    """Load DB_PATH from .env/environment and resolve it from the repo root."""
    if load_dotenv:
        load_dotenv(ROOT / ".env")

    raw_path = os.getenv("DB_PATH", "shift.db").strip()
    db_path = Path(raw_path)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    return db_path


def ensure_database_exists(db_path: Path) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database was not found: {db_path}")


def count_dummy_users(cursor: sqlite3.Cursor) -> int:
    cursor.execute(
        "SELECT COUNT(*) FROM users WHERE line_user_id LIKE ?",
        (f"{DUMMY_PREFIX}%",),
    )
    return int(cursor.fetchone()[0])


def delete_related_rows(cursor: sqlite3.Cursor, table_name: str) -> int:
    cursor.execute(
        f"""
        DELETE FROM {table_name}
        WHERE user_id IN (
            SELECT id FROM users WHERE line_user_id LIKE ?
        )
        """,
        (f"{DUMMY_PREFIX}%",),
    )
    return cursor.rowcount


def delete_dummy_users(cursor: sqlite3.Cursor) -> int:
    cursor.execute(
        "DELETE FROM users WHERE line_user_id LIKE ?",
        (f"{DUMMY_PREFIX}%",),
    )
    return cursor.rowcount


def main() -> None:
    db_path = load_db_path()
    ensure_database_exists(db_path)

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        dummy_count = count_dummy_users(cursor)
        if dummy_count == 0:
            print("No dummy users found. Nothing to remove.")
            return

        cursor.execute("BEGIN")
        deleted_confirmed = delete_related_rows(cursor, "confirmed_shifts")
        deleted_entries = delete_related_rows(cursor, "shift_entries")
        deleted_users = delete_dummy_users(cursor)
        conn.commit()

        print(f"Removed dummy data from: {db_path}")
        print(f"Dummy users removed: {deleted_users}")
        print(f"confirmed_shifts removed: {deleted_confirmed}")
        print(f"shift_entries removed: {deleted_entries}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()

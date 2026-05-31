import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path
import os


try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


ROOT = Path(__file__).resolve().parents[1]
DUMMY_PREFIX = "dummy_user_"
DUMMY_COUNT = 20
SUBMITTED_PER_DAY = 15
DAYS = 7
RANDOM_SEED = 20260526

NAMES = [
    "佐藤大輔",
    "鈴木美咲",
    "高橋健太",
    "田中彩花",
    "伊藤翔太",
    "渡辺真由",
    "山本拓也",
    "中村優子",
    "小林直樹",
    "加藤里奈",
    "吉田悠人",
    "山田千尋",
    "佐々木亮",
    "松本奈々",
    "井上和也",
    "木村遥",
    "林誠",
    "清水愛",
    "山口航",
    "森田杏",
]

SHIFT_PATTERNS = [
    ("09:00", "14:00"),
    ("10:00", "17:00"),
    ("17:00", "22:00"),
    ("18:00", "23:00"),
    ("22:00", "02:00"),
]


def load_db_path() -> Path:
    if load_dotenv:
        load_dotenv(ROOT / ".env")
    db_path = os.getenv("DB_PATH", "shift.db")
    path = Path(db_path)
    if not path.is_absolute():
        path = ROOT / path
    return path


def table_columns(cursor, table_name: str):
    return {row["name"] for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()}


def ensure_database_exists(db_path: Path):
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")


def next_display_order(cursor):
    row = cursor.execute("SELECT COALESCE(MAX(display_order), 0) + 1 AS next_order FROM users").fetchone()
    return int(row["next_order"] or 1)


def upsert_dummy_users(cursor):
    user_columns = table_columns(cursor, "users")
    has_active = "active" in user_columns
    has_display_order = "display_order" in user_columns
    order_value = next_display_order(cursor) if has_display_order else None

    for index in range(1, DUMMY_COUNT + 1):
        line_user_id = f"{DUMMY_PREFIX}{index:03d}"
        name = NAMES[index - 1]
        existing = cursor.execute(
            "SELECT id, display_order FROM users WHERE line_user_id = ?",
            (line_user_id,),
        ).fetchone()

        if existing:
            assignments = ["name = ?"]
            params = [name]
            if has_active:
                assignments.append("active = 1")
            if has_display_order and existing["display_order"] is None:
                assignments.append("display_order = ?")
                params.append(order_value)
                order_value += 1
            params.append(line_user_id)
            cursor.execute(
                f"UPDATE users SET {', '.join(assignments)} WHERE line_user_id = ?",
                params,
            )
            continue

        columns = ["line_user_id", "name"]
        values = [line_user_id, name]
        if has_active:
            columns.append("active")
            values.append(1)
        if has_display_order:
            columns.append("display_order")
            values.append(order_value)
            order_value += 1

        placeholders = ", ".join(["?"] * len(values))
        cursor.execute(
            f"INSERT INTO users({', '.join(columns)}) VALUES({placeholders})",
            values,
        )


def dummy_user_rows(cursor):
    return cursor.execute(
        """
        SELECT id, line_user_id, name
        FROM users
        WHERE line_user_id LIKE ?
        ORDER BY line_user_id
        """,
        (f"{DUMMY_PREFIX}%",),
    ).fetchall()


def reset_dummy_entries_for_dates(cursor, user_ids, dates):
    if not user_ids:
        return
    placeholders = ", ".join(["?"] * len(user_ids))
    for target_date in dates:
        cursor.execute(
            f"DELETE FROM shift_entries WHERE user_id IN ({placeholders}) AND date = ?",
            [*user_ids, target_date],
        )


def insert_dummy_shift_entries(cursor, users, dates):
    rng = random.Random(RANDOM_SEED)
    overnight_inserted = 0

    for day_index, target_date in enumerate(dates):
        submitted_users = rng.sample(users, SUBMITTED_PER_DAY)
        for user_index, user in enumerate(submitted_users):
            # Roughly mix work and days off. Users not selected for this date are left unsubmitted.
            is_off = rng.random() < 0.25
            if is_off:
                cursor.execute(
                    """
                    INSERT INTO shift_entries(user_id, date, off, start_time, end_time, updated_at)
                    VALUES(?, ?, 1, NULL, NULL, datetime('now'))
                    ON CONFLICT(user_id, date) DO UPDATE SET
                      off = excluded.off,
                      start_time = excluded.start_time,
                      end_time = excluded.end_time,
                      updated_at = excluded.updated_at
                    """,
                    (user["id"], target_date),
                )
                continue

            pattern = rng.choice(SHIFT_PATTERNS)
            # Guarantee several overnight samples for timeline and payroll checks.
            if overnight_inserted < 4 and day_index < 4 and user_index == 0:
                pattern = ("22:00", "02:00")
                overnight_inserted += 1

            cursor.execute(
                """
                INSERT INTO shift_entries(user_id, date, off, start_time, end_time, updated_at)
                VALUES(?, ?, 0, ?, ?, datetime('now'))
                ON CONFLICT(user_id, date) DO UPDATE SET
                  off = excluded.off,
                  start_time = excluded.start_time,
                  end_time = excluded.end_time,
                  updated_at = excluded.updated_at
                """,
                (user["id"], target_date, pattern[0], pattern[1]),
            )


def main():
    db_path = load_db_path()
    ensure_database_exists(db_path)
    start_date = date.today()
    dates = [(start_date + timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(DAYS)]

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN")
        upsert_dummy_users(cursor)
        users = dummy_user_rows(cursor)
        user_ids = [row["id"] for row in users]
        reset_dummy_entries_for_dates(cursor, user_ids, dates)
        insert_dummy_shift_entries(cursor, users, dates)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"DB: {db_path}")
    print(f"Dummy users: {len(users)}")
    print(f"Dates: {dates[0]} - {dates[-1]}")
    print(f"Submitted entries: about {SUBMITTED_PER_DAY} users per day")
    print("Done. Remove with: python scripts/remove_dummy_data.py")


if __name__ == "__main__":
    main()

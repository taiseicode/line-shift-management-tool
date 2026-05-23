import os
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import DATABASE_URL, DB_PATH  # noqa: E402
from db import init_tables  # noqa: E402


TABLES = (
    "users",
    "shift_entries",
    "required_staff",
    "settings",
    "confirmed_shifts",
    "user_pay_settings",
)


def fetch_rows(conn, table_name):
    try:
        return conn.execute(f"SELECT * FROM {table_name}").fetchall()
    except sqlite3.OperationalError:
        return []


def main():
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL is not set. Set it before running this migration.")

    sqlite_path = Path(os.getenv("DB_PATH", DB_PATH))
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite DB not found: {sqlite_path}")

    print("SQLite -> PostgreSQL migration")
    print(f"Source SQLite: {sqlite_path}")
    print("Destination PostgreSQL: DATABASE_URL environment variable")
    print("Existing PostgreSQL rows with the same unique keys will be updated.")
    confirm = input("Continue? Type 'yes' to proceed: ").strip().lower()
    if confirm != "yes":
        raise SystemExit("Cancelled.")

    init_tables()

    import psycopg
    from psycopg.rows import dict_row

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    pg_conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)

    counts = {table: 0 for table in TABLES}
    user_id_map = {}
    shift_entry_id_map = {}

    try:
        with pg_conn.cursor() as c:
            for row in fetch_rows(sqlite_conn, "users"):
                if row["line_user_id"]:
                    inserted = c.execute(
                        """
                        INSERT INTO users(line_user_id, name, active, display_order)
                        VALUES(%s, %s, %s, %s)
                        ON CONFLICT(line_user_id) DO UPDATE SET
                          name=excluded.name,
                          active=excluded.active,
                          display_order=excluded.display_order
                        RETURNING id
                        """,
                        (row["line_user_id"], row["name"], row["active"], row["display_order"]),
                    ).fetchone()
                else:
                    inserted = c.execute(
                        """
                        INSERT INTO users(id, line_user_id, name, active, display_order)
                        VALUES(%s, %s, %s, %s, %s)
                        ON CONFLICT(id) DO UPDATE SET
                          line_user_id=excluded.line_user_id,
                          name=excluded.name,
                          active=excluded.active,
                          display_order=excluded.display_order
                        RETURNING id
                        """,
                        (row["id"], row["line_user_id"], row["name"], row["active"], row["display_order"]),
                    ).fetchone()
                user_id_map[int(row["id"])] = int(inserted["id"])
                counts["users"] += 1

            for row in fetch_rows(sqlite_conn, "shift_entries"):
                mapped_user_id = user_id_map.get(int(row["user_id"]))
                if not mapped_user_id:
                    continue
                inserted = c.execute(
                    """
                    INSERT INTO shift_entries(user_id, date, off, start_time, end_time, updated_at)
                    VALUES(%s, %s, %s, %s, %s, %s)
                    ON CONFLICT(user_id, date) DO UPDATE SET
                      off=excluded.off,
                      start_time=excluded.start_time,
                      end_time=excluded.end_time,
                      updated_at=excluded.updated_at
                    RETURNING id
                    """,
                    (mapped_user_id, row["date"], row["off"], row["start_time"], row["end_time"], row["updated_at"]),
                ).fetchone()
                shift_entry_id_map[int(row["id"])] = int(inserted["id"])
                counts["shift_entries"] += 1

            for row in fetch_rows(sqlite_conn, "required_staff"):
                c.execute(
                    """
                    INSERT INTO required_staff(date, required_count, updated_at)
                    VALUES(%s, %s, %s)
                    ON CONFLICT(date) DO UPDATE SET
                      required_count=excluded.required_count,
                      updated_at=excluded.updated_at
                    """,
                    (row["date"], row["required_count"], row["updated_at"]),
                )
                counts["required_staff"] += 1

            for row in fetch_rows(sqlite_conn, "settings"):
                c.execute(
                    """
                    INSERT INTO settings(key, value)
                    VALUES(%s, %s)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value
                    """,
                    (row["key"], row["value"]),
                )
                counts["settings"] += 1

            for row in fetch_rows(sqlite_conn, "confirmed_shifts"):
                mapped_user_id = user_id_map.get(int(row["user_id"]))
                if not mapped_user_id:
                    continue
                source_entry_id = row["source_entry_id"]
                mapped_source_entry_id = shift_entry_id_map.get(int(source_entry_id)) if source_entry_id else None
                c.execute(
                    """
                    INSERT INTO confirmed_shifts(
                      user_id, date, start_time, end_time, is_assigned,
                      source_entry_id, created_at, updated_at
                    )
                    VALUES(%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(user_id, date) DO UPDATE SET
                      start_time=excluded.start_time,
                      end_time=excluded.end_time,
                      is_assigned=excluded.is_assigned,
                      source_entry_id=excluded.source_entry_id,
                      updated_at=excluded.updated_at
                    """,
                    (
                        mapped_user_id,
                        row["date"],
                        row["start_time"],
                        row["end_time"],
                        row["is_assigned"],
                        mapped_source_entry_id,
                        row["created_at"],
                        row["updated_at"],
                    ),
                )
                counts["confirmed_shifts"] += 1

            for row in fetch_rows(sqlite_conn, "user_pay_settings"):
                mapped_user_id = user_id_map.get(int(row["user_id"]))
                if not mapped_user_id:
                    continue
                c.execute(
                    """
                    INSERT INTO user_pay_settings(
                      user_id, hourly_wage, break_rule, night_enabled,
                      overtime_enabled, created_at, updated_at
                    )
                    VALUES(%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(user_id) DO UPDATE SET
                      hourly_wage=excluded.hourly_wage,
                      break_rule=excluded.break_rule,
                      night_enabled=excluded.night_enabled,
                      overtime_enabled=excluded.overtime_enabled,
                      updated_at=excluded.updated_at
                    """,
                    (
                        mapped_user_id,
                        row["hourly_wage"],
                        row["break_rule"],
                        row["night_enabled"],
                        row["overtime_enabled"],
                        row["created_at"],
                        row["updated_at"],
                    ),
                )
                counts["user_pay_settings"] += 1

        pg_conn.commit()
    except Exception:
        pg_conn.rollback()
        raise
    finally:
        sqlite_conn.close()
        pg_conn.close()

    print("Migration complete.")
    for table_name in TABLES:
        print(f"{table_name}: {counts[table_name]} rows processed")


if __name__ == "__main__":
    main()

from datetime import datetime

from db import get_conn, using_postgres

USER_ORDER_SQL = "COALESCE(u.display_order, 999999), u.id"


def _empty_time_value_for_confirmed_shifts():
    if using_postgres():
        return None
    conn = get_conn()
    try:
        c = conn.cursor()
        columns = c.execute("PRAGMA table_info(confirmed_shifts)").fetchall()
        notnull = {row["name"]: int(row["notnull"] or 0) for row in columns}
        return "" if notnull.get("start_time") or notnull.get("end_time") else None
    finally:
        conn.close()


def get_confirmed_shifts_by_date(date_str: str):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT cs.id, cs.user_id, cs.date, cs.is_assigned, cs.source_entry_id,
                   COALESCE(NULLIF(cs.start_time, ''), se.start_time) AS start_time,
                   COALESCE(NULLIF(cs.end_time, ''), se.end_time) AS end_time,
                   cs.created_at, cs.updated_at, u.name, u.active
            FROM confirmed_shifts cs
            JOIN users u ON cs.user_id = u.id
            LEFT JOIN shift_entries se ON se.id = cs.source_entry_id
            WHERE cs.date = ? AND cs.is_assigned = 1 AND u.active = 1
            ORDER BY COALESCE(u.display_order, 999999), u.id
        """, (date_str,))
        return c.fetchall()
    finally:
        conn.close()


def get_confirmed_shift_by_id(confirmed_shift_id: int):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT cs.id, cs.user_id, cs.date, cs.start_time, cs.end_time, cs.is_assigned, cs.source_entry_id,
                   cs.created_at, cs.updated_at, u.name, u.active
            FROM confirmed_shifts cs
            JOIN users u ON cs.user_id = u.id
            WHERE cs.id = ?
        """, (confirmed_shift_id,))
        return c.fetchone()
    finally:
        conn.close()


def get_confirmed_shift_decisions_range(start_ymd: str, end_ymd: str):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT cs.id, cs.user_id, cs.date, cs.start_time, cs.end_time, cs.is_assigned, cs.source_entry_id,
                   cs.created_at, cs.updated_at, u.name, u.active
            FROM confirmed_shifts cs
            JOIN users u ON cs.user_id = u.id
            WHERE cs.date >= ? AND cs.date <= ? AND u.active = 1
            ORDER BY cs.date, COALESCE(u.display_order, 999999), u.id
        """, (start_ymd, end_ymd))
        return c.fetchall()
    finally:
        conn.close()


def get_confirmed_shift_decisions_by_date(date_str: str):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT cs.id, cs.user_id, cs.date, cs.start_time, cs.end_time, cs.is_assigned, cs.source_entry_id,
                   cs.created_at, cs.updated_at, u.name, u.active
            FROM confirmed_shifts cs
            JOIN users u ON cs.user_id = u.id
            WHERE cs.date = ? AND u.active = 1
            ORDER BY COALESCE(u.display_order, 999999), u.id
        """, (date_str,))
        return c.fetchall()
    finally:
        conn.close()


def get_confirmed_shifts_range(start_ymd: str, end_ymd: str):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT cs.id, cs.user_id, cs.date,
                   COALESCE(NULLIF(cs.start_time, ''), se.start_time) AS start_time,
                   COALESCE(NULLIF(cs.end_time, ''), se.end_time) AS end_time,
                   cs.is_assigned, cs.source_entry_id,
                   cs.created_at, cs.updated_at, u.name, u.active
            FROM confirmed_shifts cs
            JOIN users u ON cs.user_id = u.id
            LEFT JOIN shift_entries se ON se.id = cs.source_entry_id
            WHERE cs.date >= ? AND cs.date <= ? AND cs.is_assigned = 1 AND u.active = 1
            ORDER BY cs.date, COALESCE(u.display_order, 999999), u.id
        """, (start_ymd, end_ymd))
        return c.fetchall()
    finally:
        conn.close()


def upsert_confirmed_shift(
    user_id: int,
    date_str: str,
    start_time: str,
    end_time: str,
    source_entry_id=None,
    is_assigned: int = 1,
):
    if int(is_assigned) == 0:
        empty_time = _empty_time_value_for_confirmed_shifts()
        start_time = empty_time
        end_time = empty_time
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO confirmed_shifts(user_id, date, start_time, end_time, is_assigned, source_entry_id, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id, date) DO UPDATE SET
              start_time=excluded.start_time,
              end_time=excluded.end_time,
              is_assigned=excluded.is_assigned,
              source_entry_id=excluded.source_entry_id,
              updated_at=excluded.updated_at
        """, (user_id, date_str, start_time, end_time, int(is_assigned), source_entry_id, now, now))
        conn.commit()
    finally:
        conn.close()


def save_confirmed_shift_decisions_bulk(decisions):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    empty_time_value = _empty_time_value_for_confirmed_shifts()
    conn = get_conn()
    try:
        c = conn.cursor()
        for decision in decisions:
            if decision["status"] == "unconfirmed":
                c.execute(
                    "DELETE FROM confirmed_shifts WHERE user_id=? AND date=?",
                    (decision["user_id"], decision["date"]),
                )
                continue
            start_time = decision["start_time"]
            end_time = decision["end_time"]
            if int(decision["is_assigned"] or 0) == 0:
                start_time = empty_time_value
                end_time = empty_time_value

            c.execute("""
                INSERT INTO confirmed_shifts(user_id, date, start_time, end_time, is_assigned, source_entry_id, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(user_id, date) DO UPDATE SET
                  start_time=excluded.start_time,
                  end_time=excluded.end_time,
                  is_assigned=excluded.is_assigned,
                  source_entry_id=excluded.source_entry_id,
                  updated_at=excluded.updated_at
            """, (
                decision["user_id"],
                decision["date"],
                start_time,
                end_time,
                decision["is_assigned"],
                decision["source_entry_id"],
                now,
                now,
            ))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_confirmed_shift(confirmed_shift_id: int) -> int:
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM confirmed_shifts WHERE id=?", (confirmed_shift_id,))
        deleted = c.rowcount
        conn.commit()
        return deleted
    finally:
        conn.close()

from datetime import datetime

from db import get_conn

USER_ORDER_SQL = "COALESCE(u.display_order, 999999), u.id"


def upsert_shift_entry(user_id: int, date_str: str, off: int, start_time, end_time):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO shift_entries(user_id, date, off, start_time, end_time, updated_at)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(user_id, date) DO UPDATE SET
              off=excluded.off,
              start_time=excluded.start_time,
              end_time=excluded.end_time,
              updated_at=excluded.updated_at
        """, (user_id, date_str, int(off), start_time, end_time, now))
        conn.commit()


def delete_entry(user_id: int, date_str: str) -> int:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM shift_entries WHERE user_id=? AND date=?", (user_id, date_str))
        deleted = c.rowcount
        conn.commit()
        return deleted


def get_my_entries_range(user_id: int, start_ymd: str, end_ymd: str):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT se.date, se.off, se.start_time, se.end_time, se.updated_at
            FROM shift_entries se
            WHERE se.user_id=? AND se.date BETWEEN ? AND ?
            ORDER BY se.date
        """, (user_id, start_ymd, end_ymd))
        return c.fetchall()


def get_entries_range(start_ymd: str, end_ymd: str):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT se.id, se.user_id, se.date, u.name, u.active, se.off, se.start_time, se.end_time, se.updated_at
            FROM shift_entries se
            JOIN users u ON se.user_id = u.id
            WHERE se.date BETWEEN ? AND ?
            ORDER BY se.date, COALESCE(u.display_order, 999999), u.id
        """, (start_ymd, end_ymd))
        return c.fetchall()


def get_entries_for_date(target_ymd: str):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT se.user_id, se.date, se.off, se.start_time, se.end_time, u.name, u.active
            FROM shift_entries se
            JOIN users u ON se.user_id = u.id
            WHERE se.date = ? AND u.active = 1
            ORDER BY COALESCE(u.display_order, 999999), u.id
        """, (target_ymd,))
        return c.fetchall()


def get_entries_for_period(start_ymd: str, end_exclusive_ymd: str):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT se.user_id, se.date, se.off, se.start_time, se.end_time, u.name, u.active
            FROM shift_entries se
            JOIN users u ON se.user_id = u.id
            WHERE se.date >= ? AND se.date < ? AND u.active = 1
            ORDER BY COALESCE(u.display_order, 999999), u.id, se.date
        """, (start_ymd, end_exclusive_ymd))
        return c.fetchall()


def get_submission_entries_by_date(target_ymd: str):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT se.id, se.user_id, se.date, se.off, se.start_time, se.end_time, se.updated_at,
                   u.name, u.active
            FROM shift_entries se
            JOIN users u ON se.user_id = u.id
            WHERE se.date = ? AND u.active = 1
            ORDER BY COALESCE(u.display_order, 999999), u.id
        """, (target_ymd,))
        return c.fetchall()


def get_shift_entry_by_id(entry_id: int):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT se.id, se.user_id, se.date, se.off, se.start_time, se.end_time, se.updated_at,
                   u.name, u.active
            FROM shift_entries se
            JOIN users u ON se.user_id = u.id
            WHERE se.id = ?
        """, (entry_id,))
        return c.fetchone()

from datetime import datetime

from db import get_conn


def upsert_shift_entry(user_id: int, date_str: str, off: int, start_time, end_time):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    try:
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
    finally:
        conn.close()

def delete_entry(user_id: int, date_str: str) -> int:
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM shift_entries WHERE user_id=? AND date=?", (user_id, date_str))
        deleted = c.rowcount
        conn.commit()
        return deleted
    finally:
        conn.close()

def get_my_entries_range(user_id: int, start_ymd: str, end_ymd: str):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT se.date, se.off, se.start_time, se.end_time, se.updated_at
            FROM shift_entries se
            WHERE se.user_id=? AND se.date BETWEEN ? AND ?
            ORDER BY se.date
        """, (user_id, start_ymd, end_ymd))
        return c.fetchall()
    finally:
        conn.close()

def get_entries_range(start_ymd: str, end_ymd: str):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT se.date, u.name, u.active, se.off, se.start_time, se.end_time, se.updated_at
            FROM shift_entries se
            JOIN users u ON se.user_id = u.id
            WHERE se.date BETWEEN ? AND ?
            ORDER BY se.date, u.name
        """, (start_ymd, end_ymd))
        return c.fetchall()
    finally:
        conn.close()

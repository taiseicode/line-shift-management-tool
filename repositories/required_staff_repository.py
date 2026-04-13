from datetime import datetime

from db import get_conn


def upsert_required_staff(date_str: str, required_count: int):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO required_staff(date, required_count, updated_at)
            VALUES(?,?,?)
            ON CONFLICT(date) DO UPDATE SET
              required_count=excluded.required_count,
              updated_at=excluded.updated_at
        """, (date_str, int(required_count), now))
        conn.commit()
    finally:
        conn.close()

def get_required_staff_range(start_ymd: str, end_ymd: str):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT date, required_count, updated_at
            FROM required_staff
            WHERE date BETWEEN ? AND ?
            ORDER BY date
        """, (start_ymd, end_ymd))
        rows = c.fetchall()
        return {r["date"]: int(r["required_count"]) for r in rows}
    finally:
        conn.close()

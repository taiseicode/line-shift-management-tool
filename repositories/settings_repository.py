from db import get_conn


def get_setting(key: str):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = c.fetchone()
        return row["value"] if row else None
    finally:
        conn.close()

def upsert_setting(key: str, value: str):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO settings(key, value)
            VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET
              value=excluded.value
        """, (key, value))
        conn.commit()
    finally:
        conn.close()

def delete_setting(key: str):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM settings WHERE key=?", (key,))
        conn.commit()
    finally:
        conn.close()

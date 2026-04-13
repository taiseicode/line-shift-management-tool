from db import get_conn


def get_user_by_line_id(line_user_id: str):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE line_user_id=?", (line_user_id,))
        return c.fetchone()
    finally:
        conn.close()

def get_all_users(include_inactive: bool = True):
    conn = get_conn()
    try:
        c = conn.cursor()
        if include_inactive:
            c.execute("""
                SELECT id, line_user_id, name, active
                FROM users
                ORDER BY active DESC, name, id
            """)
        else:
            c.execute("""
                SELECT id, line_user_id, name, active
                FROM users
                WHERE active=1
                ORDER BY name, id
            """)
        return c.fetchall()
    finally:
        conn.close()

def upsert_user(line_user_id: str, name: str):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users(line_user_id, name) VALUES(?, ?)", (line_user_id, name))
        c.execute("UPDATE users SET name=? WHERE line_user_id=?", (name, line_user_id))
        conn.commit()
    finally:
        conn.close()

def set_user_active(user_id: int, active: int) -> int:
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("UPDATE users SET active=? WHERE id=?", (int(active), int(user_id)))
        updated = c.rowcount
        conn.commit()
        return updated
    finally:
        conn.close()

def update_user_name(user_id: int, name: str) -> int:
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("UPDATE users SET name=? WHERE id=?", (name, int(user_id)))
        updated = c.rowcount
        conn.commit()
        return updated
    finally:
        conn.close()

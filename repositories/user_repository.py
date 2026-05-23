from db import get_conn, get_table_columns, invalidate_table_columns_cache


USER_ORDER_BY = "COALESCE(display_order, 999999) ASC, id ASC"


def ensure_user_display_order():
    conn = get_conn()
    try:
        c = conn.cursor()
        columns = get_table_columns("users")
        if "display_order" not in columns:
            c.execute("ALTER TABLE users ADD COLUMN display_order INTEGER")
            invalidate_table_columns_cache("users")
        rows = c.execute("""
            SELECT id
            FROM users
            WHERE display_order IS NULL
            ORDER BY id
        """).fetchall()
        next_order_row = c.execute("SELECT COALESCE(MAX(display_order), 0) + 1 AS next_order FROM users").fetchone()
        next_order = int(next_order_row["next_order"] or 1)
        for row in rows:
            c.execute("UPDATE users SET display_order=? WHERE id=?", (next_order, row["id"]))
            next_order += 1
        conn.commit()
    finally:
        conn.close()


def get_user_by_line_id(line_user_id: str):
    ensure_user_display_order()
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE line_user_id=?", (line_user_id,))
        return c.fetchone()
    finally:
        conn.close()

def get_all_users(include_inactive: bool = True):
    ensure_user_display_order()
    conn = get_conn()
    try:
        c = conn.cursor()
        if include_inactive:
            c.execute(f"""
                SELECT id, line_user_id, name, active, display_order
                FROM users
                ORDER BY active DESC, {USER_ORDER_BY}
            """)
        else:
            c.execute(f"""
                SELECT id, line_user_id, name, active, display_order
                FROM users
                WHERE active=1
                ORDER BY {USER_ORDER_BY}
            """)
        return c.fetchall()
    finally:
        conn.close()

def upsert_user(line_user_id: str, name: str):
    ensure_user_display_order()
    conn = get_conn()
    try:
        c = conn.cursor()
        next_order_row = c.execute("SELECT COALESCE(MAX(display_order), 0) + 1 AS next_order FROM users").fetchone()
        next_order = int(next_order_row["next_order"] or 1)
        c.execute("""
            INSERT INTO users(line_user_id, name, display_order)
            VALUES(?, ?, ?)
            ON CONFLICT(line_user_id) DO NOTHING
        """, (line_user_id, name, next_order))
        c.execute("UPDATE users SET name=? WHERE line_user_id=?", (name, line_user_id))
        c.execute("UPDATE users SET display_order=? WHERE line_user_id=? AND display_order IS NULL", (next_order, line_user_id))
        conn.commit()
    finally:
        conn.close()

def set_user_active(user_id: int, active: int) -> int:
    ensure_user_display_order()
    conn = get_conn()
    try:
        c = conn.cursor()
        if int(active) == 1:
            next_order_row = c.execute("SELECT COALESCE(MAX(display_order), 0) + 1 AS next_order FROM users").fetchone()
            next_order = int(next_order_row["next_order"] or 1)
            c.execute("UPDATE users SET display_order=? WHERE id=? AND display_order IS NULL", (next_order, int(user_id)))
        c.execute("UPDATE users SET active=? WHERE id=?", (int(active), int(user_id)))
        updated = c.rowcount
        conn.commit()
        return updated
    finally:
        conn.close()

def update_user_name(user_id: int, name: str) -> int:
    ensure_user_display_order()
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("UPDATE users SET name=? WHERE id=?", (name, int(user_id)))
        updated = c.rowcount
        conn.commit()
        return updated
    finally:
        conn.close()


def move_active_user(user_id: int, direction: str) -> bool:
    ensure_user_display_order()
    conn = get_conn()
    try:
        c = conn.cursor()
        rows = c.execute(f"""
            SELECT id, display_order
            FROM users
            WHERE active=1
            ORDER BY {USER_ORDER_BY}
        """).fetchall()
        ids = [int(row["id"]) for row in rows]
        try:
            index = ids.index(int(user_id))
        except ValueError:
            return False
        target_index = index - 1 if direction == "up" else index + 1
        if target_index < 0 or target_index >= len(rows):
            return False
        current = rows[index]
        target = rows[target_index]
        c.execute("UPDATE users SET display_order=? WHERE id=?", (target["display_order"], current["id"]))
        c.execute("UPDATE users SET display_order=? WHERE id=?", (current["display_order"], target["id"]))
        conn.commit()
        return True
    finally:
        conn.close()

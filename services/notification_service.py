from datetime import datetime, timedelta

from db import get_conn, using_postgres
from repositories.settings_repository import get_settings, upsert_setting
from services.deadline_service import get_active_deadline_config, get_submission_deadline_status
from services.line_notify_service import send_line_message
from utils import is_valid_time_hhmm, now_jst, parse_ymd, to_ymd, today_jst


NOTIFY_DEADLINE_ENABLED_KEY = "notify_deadline_reminder_enabled"
NOTIFY_DEADLINE_TIME_KEY = "notify_deadline_reminder_time"
NOTIFY_CONFIRMED_ENABLED_KEY = "notify_confirmed_shift_reminder_enabled"
NOTIFY_CONFIRMED_TIME_KEY = "notify_confirmed_shift_reminder_time"
NOTIFICATION_SETTING_KEYS = (
    NOTIFY_DEADLINE_ENABLED_KEY,
    NOTIFY_DEADLINE_TIME_KEY,
    NOTIFY_CONFIRMED_ENABLED_KEY,
    NOTIFY_CONFIRMED_TIME_KEY,
)

TARGET_ALL = "all"
TARGET_UNSUBMITTED = "unsubmitted"
TARGET_ASSIGNED = "assigned"
TARGET_INDIVIDUAL = "individual"
TARGET_AUTO_DEADLINE = "auto_deadline_reminder"
TARGET_AUTO_CONFIRMED = "auto_confirmed_shift_reminder"


def _is_enabled(value) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _row_to_recipient(row):
    return {
        "user_id": int(row["id"]),
        "name": row["name"] or "",
        "line_user_id": row["line_user_id"] or "",
    }


def get_notification_settings():
    values = get_settings(NOTIFICATION_SETTING_KEYS)
    return {
        "deadline_enabled": _is_enabled(values.get(NOTIFY_DEADLINE_ENABLED_KEY)),
        "deadline_time": values.get(NOTIFY_DEADLINE_TIME_KEY) or "09:00",
        "confirmed_enabled": _is_enabled(values.get(NOTIFY_CONFIRMED_ENABLED_KEY)),
        "confirmed_time": values.get(NOTIFY_CONFIRMED_TIME_KEY) or "18:00",
    }


def save_notification_settings(deadline_enabled: bool, deadline_time: str, confirmed_enabled: bool, confirmed_time: str):
    if not is_valid_time_hhmm(deadline_time or ""):
        raise ValueError("提出期限リマインド時刻が不正です")
    if not is_valid_time_hhmm(confirmed_time or ""):
        raise ValueError("確定シフトリマインド時刻が不正です")
    upsert_setting(NOTIFY_DEADLINE_ENABLED_KEY, "1" if deadline_enabled else "0")
    upsert_setting(NOTIFY_DEADLINE_TIME_KEY, deadline_time)
    upsert_setting(NOTIFY_CONFIRMED_ENABLED_KEY, "1" if confirmed_enabled else "0")
    upsert_setting(NOTIFY_CONFIRMED_TIME_KEY, confirmed_time)


def get_recipients(target_type: str, target_date: str = "", user_ids=None):
    target_type = (target_type or "").strip()
    target_date = (target_date or "").strip()
    conn = get_conn()
    try:
        c = conn.cursor()
        if target_type == TARGET_ALL:
            rows = c.execute("""
                SELECT id, name, line_user_id
                FROM users
                WHERE active = 1 AND line_user_id IS NOT NULL AND line_user_id <> ''
                ORDER BY COALESCE(display_order, 999999), id
            """).fetchall()
            return [_row_to_recipient(row) for row in rows]

        if target_type == TARGET_UNSUBMITTED:
            rows = c.execute("""
                SELECT u.id, u.name, u.line_user_id
                FROM users u
                LEFT JOIN shift_entries se ON se.user_id = u.id AND se.date = ?
                WHERE u.active = 1
                  AND u.line_user_id IS NOT NULL AND u.line_user_id <> ''
                  AND se.id IS NULL
                ORDER BY COALESCE(u.display_order, 999999), u.id
            """, (target_date,)).fetchall()
            return [_row_to_recipient(row) for row in rows]

        if target_type == TARGET_ASSIGNED:
            rows = c.execute("""
                SELECT u.id, u.name, u.line_user_id
                FROM confirmed_shifts cs
                JOIN users u ON u.id = cs.user_id
                WHERE cs.date = ?
                  AND cs.is_assigned = 1
                  AND u.active = 1
                  AND u.line_user_id IS NOT NULL AND u.line_user_id <> ''
                ORDER BY COALESCE(u.display_order, 999999), u.id
            """, (target_date,)).fetchall()
            return [_row_to_recipient(row) for row in rows]

        if target_type == TARGET_INDIVIDUAL:
            ids = []
            for user_id in user_ids or []:
                try:
                    ids.append(int(user_id))
                except (TypeError, ValueError):
                    pass
            if not ids:
                return []
            placeholders = ", ".join(["?"] * len(ids))
            rows = c.execute(f"""
                SELECT id, name, line_user_id
                FROM users
                WHERE active = 1
                  AND line_user_id IS NOT NULL AND line_user_id <> ''
                  AND id IN ({placeholders})
                ORDER BY COALESCE(display_order, 999999), id
            """, ids).fetchall()
            return [_row_to_recipient(row) for row in rows]

        return []
    finally:
        conn.close()


def _insert_notification_log(c, title, message, target_type, target_date):
    if using_postgres():
        row = c.execute("""
            INSERT INTO notification_logs(title, message, target_type, target_date, sent_count, failed_count)
            VALUES(?, ?, ?, ?, 0, 0)
            RETURNING id
        """, (title, message, target_type, target_date or None)).fetchone()
        return int(row["id"])
    c.execute("""
        INSERT INTO notification_logs(title, message, target_type, target_date, sent_count, failed_count)
        VALUES(?, ?, ?, ?, 0, 0)
    """, (title, message, target_type, target_date or None))
    return int(c.lastrowid)


def send_notification(title: str, message: str, target_type: str, target_date: str = "", user_ids=None, recipient_target_type: str = None):
    recipients = get_recipients(recipient_target_type or target_type, target_date, user_ids)
    conn = get_conn()
    sent_count = 0
    failed_count = 0
    errors = []
    try:
        c = conn.cursor()
        log_id = _insert_notification_log(c, title, message, target_type, target_date)
        for recipient in recipients:
            ok, error = send_line_message(recipient["line_user_id"], message)
            status = "sent" if ok else "failed"
            if ok:
                sent_count += 1
            else:
                failed_count += 1
                if error:
                    errors.append(f'{recipient["name"] or recipient["user_id"]}: {error}')
            c.execute("""
                INSERT INTO notification_recipients(notification_log_id, user_id, line_user_id, status, error_text)
                VALUES(?, ?, ?, ?, ?)
            """, (
                log_id,
                recipient["user_id"],
                recipient["line_user_id"],
                status,
                error,
            ))
        error_text = "\n".join(errors) if errors else None
        c.execute("""
            UPDATE notification_logs
            SET sent_count = ?, failed_count = ?, error_text = ?
            WHERE id = ?
        """, (sent_count, failed_count, error_text, log_id))
        conn.commit()
        return {
            "log_id": log_id,
            "target_count": len(recipients),
            "sent_count": sent_count,
            "failed_count": failed_count,
            "error_text": error_text,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_notification_logs(limit: int = 20):
    conn = get_conn()
    try:
        c = conn.cursor()
        rows = c.execute("""
            SELECT id, title, message, target_type, target_date, sent_count, failed_count, error_text, created_at
            FROM notification_logs
            ORDER BY id DESC
            LIMIT ?
        """, (int(limit),)).fetchall()
        return [_format_notification_log(row) for row in rows]
    finally:
        conn.close()


def _format_notification_log(row):
    item = dict(row)
    created_at = item.get("created_at")
    if isinstance(created_at, datetime):
        item["created_at_display"] = created_at.strftime("%Y-%m-%d %H:%M")
        return item

    text = str(created_at or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            item["created_at_display"] = datetime.strptime(text, fmt).strftime("%Y-%m-%d %H:%M")
            return item
        except ValueError:
            pass
    item["created_at_display"] = text[:16] if len(text) >= 16 else text
    return item


def has_auto_notification_sent(target_type: str, target_date: str, run_date: str):
    conn = get_conn()
    try:
        c = conn.cursor()
        row = c.execute("""
            SELECT id
            FROM notification_logs
            WHERE target_type = ?
              AND COALESCE(target_date, '') = ?
              AND substr(CAST(created_at AS TEXT), 1, 10) = ?
            LIMIT 1
        """, (target_type, target_date or "", run_date)).fetchone()
        return row is not None
    finally:
        conn.close()


def _time_has_passed(setting_time: str, current) -> bool:
    if not is_valid_time_hhmm(setting_time or ""):
        return False
    return current.strftime("%H:%M") >= setting_time


def _find_shift_date_with_deadline_on(deadline_date):
    active_config = get_active_deadline_config()
    current = today_jst()
    for offset in range(0, 120):
        shift_date = current + timedelta(days=offset)
        status = get_submission_deadline_status(shift_date_obj=shift_date, active_config=active_config)
        deadline = status.get("deadline")
        if deadline and deadline.date() == deadline_date:
            return shift_date
    return None


def run_due_notifications(current=None):
    current = current or now_jst()
    run_date = to_ymd(current.date())
    tomorrow = current.date() + timedelta(days=1)
    settings = get_notification_settings()
    results = []

    if settings["deadline_enabled"] and _time_has_passed(settings["deadline_time"], current):
        shift_date = _find_shift_date_with_deadline_on(tomorrow)
        if shift_date:
            target_date = to_ymd(shift_date)
            if not has_auto_notification_sent(TARGET_AUTO_DEADLINE, target_date, run_date):
                results.append(send_notification(
                    "シフト提出リマインド",
                    "【シフト提出リマインド】\nシフト提出期限が近づいています。\nまだ提出していない方は、シフト便から提出をお願いします。",
                    TARGET_AUTO_DEADLINE,
                    target_date,
                    recipient_target_type=TARGET_UNSUBMITTED,
                ) | {"type": TARGET_AUTO_DEADLINE, "target_date": target_date})

    if settings["confirmed_enabled"] and _time_has_passed(settings["confirmed_time"], current):
        target_date = to_ymd(tomorrow)
        if not has_auto_notification_sent(TARGET_AUTO_CONFIRMED, target_date, run_date):
            recipients = get_recipients(TARGET_ASSIGNED, target_date)
            if recipients:
                results.append(send_notification(
                    "明日のシフト確認",
                    "【明日のシフト確認】\n明日は確定シフトがあります。\nシフト便で時間を確認してください。",
                    TARGET_AUTO_CONFIRMED,
                    target_date,
                    recipient_target_type=TARGET_ASSIGNED,
                ) | {"type": TARGET_AUTO_CONFIRMED, "target_date": target_date})

    return results

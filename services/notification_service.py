import json
from threading import Lock
from datetime import datetime, timedelta

from db import get_conn, using_postgres
from repositories.settings_repository import get_setting, get_settings, upsert_setting
from services.deadline_service import get_active_deadline_config, get_submission_deadline_status
from services.line_notify_service import send_line_message
from utils import APP_TIMEZONE, is_valid_time_hhmm, now_jst, parse_ymd, to_ymd, today_jst


NOTIFY_DEADLINE_ENABLED_KEY = "notify_deadline_reminder_enabled"
NOTIFY_DEADLINE_TIME_KEY = "notify_deadline_reminder_time"
NOTIFY_CONFIRMED_ENABLED_KEY = "notify_confirmed_shift_reminder_enabled"
NOTIFY_CONFIRMED_TIME_KEY = "notify_confirmed_shift_reminder_time"
LEGACY_RULES_MIGRATED_KEY = "notification_rules_legacy_migrated"
NOTIFICATION_SETTING_KEYS = (
    NOTIFY_DEADLINE_ENABLED_KEY,
    NOTIFY_DEADLINE_TIME_KEY,
    NOTIFY_CONFIRMED_ENABLED_KEY,
    NOTIFY_CONFIRMED_TIME_KEY,
)

SCHEDULE_DAILY = "daily"
SCHEDULE_WEEKLY = "weekly"
SCHEDULE_MONTHLY = "monthly"
SCHEDULE_TYPES = {SCHEDULE_DAILY, SCHEDULE_WEEKLY, SCHEDULE_MONTHLY}

TARGET_ALL = "all"
TARGET_UNSUBMITTED = "unsubmitted"
TARGET_ASSIGNED = "assigned"
TARGET_TOMORROW_ASSIGNED = "tomorrow_assigned"
TARGET_INDIVIDUAL = "individual"
RULE_TARGET_TYPES = {TARGET_ALL, TARGET_UNSUBMITTED, TARGET_TOMORROW_ASSIGNED, TARGET_INDIVIDUAL}

TARGET_DATE_TODAY = "today"
TARGET_DATE_TOMORROW = "tomorrow"
TARGET_DATE_DEADLINE_TOMORROW = "deadline_tomorrow"
TARGET_DATE_MODES = {TARGET_DATE_TODAY, TARGET_DATE_TOMORROW, TARGET_DATE_DEADLINE_TOMORROW}

WEEKDAY_LABELS = ["月", "火", "水", "木", "金", "土", "日"]
TARGET_LABELS = {
    TARGET_ALL: "全員",
    TARGET_UNSUBMITTED: "未提出者",
    TARGET_ASSIGNED: "出勤予定者",
    TARGET_TOMORROW_ASSIGNED: "明日出勤予定者",
    TARGET_INDIVIDUAL: "個別ユーザー",
}
SCHEDULE_LABELS = {
    SCHEDULE_DAILY: "毎日",
    SCHEDULE_WEEKLY: "毎週",
    SCHEDULE_MONTHLY: "毎月",
}
TIMEZONE_NAME = "Asia/Tokyo"
STATUS_CRON_NOT_RUN = "送信待ち"
STATUS_SENT = "送信済み"
STATUS_SKIPPED = "スキップ"
STATUS_FAILED = "送信失敗"

LOG_STATUS_PENDING = "pending"
LOG_STATUS_SENDING = "sending"
LOG_STATUS_SENT = "sent"
LOG_STATUS_FAILED = "failed"
LOG_STATUS_PARTIAL_FAILED = "partial_failed"
LOG_STATUS_FAILED_STALE = "failed_stale"
LOG_DELIVERED_STATUSES = {LOG_STATUS_SENT, LOG_STATUS_PARTIAL_FAILED, LOG_STATUS_FAILED}
LOG_ACTIVE_STATUSES = {LOG_STATUS_PENDING, LOG_STATUS_SENDING}
LOG_STALE_AFTER_MINUTES = 30

_run_notifications_lock = Lock()


def _is_enabled(value) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _row_to_recipient(row):
    return {
        "user_id": int(row["id"]),
        "name": row["name"] or "",
        "line_user_id": row["line_user_id"] or "",
    }


def _row_to_dict(row):
    return dict(row)


def _loads_user_ids(value):
    if not value:
        return []
    try:
        raw_values = json.loads(value)
    except Exception:
        raw_values = str(value).split(",")
    user_ids = []
    for raw_value in raw_values:
        try:
            user_ids.append(int(raw_value))
        except (TypeError, ValueError):
            pass
    return user_ids


def _dumps_user_ids(user_ids):
    normalized = []
    seen = set()
    for raw_value in user_ids or []:
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            continue
        if value not in seen:
            normalized.append(value)
            seen.add(value)
    return json.dumps(normalized, ensure_ascii=False)


def _format_dt(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass
    return text[:16] if len(text) >= 16 else text


def _normalize_current(current=None):
    if current is None:
        return now_jst()
    if getattr(current, "tzinfo", None) is not None:
        return current.astimezone(APP_TIMEZONE).replace(tzinfo=None)
    return current


def _next_rule_run_at(rule, current=None):
    current = _normalize_current(current)
    send_time = rule.get("send_time") or "00:00"
    if not is_valid_time_hhmm(send_time):
        return ""
    hour, minute = [int(part) for part in send_time.split(":", 1)]
    schedule_type = rule.get("schedule_type")

    for day_offset in range(0, 370):
        candidate_date = current.date() + timedelta(days=day_offset)
        if schedule_type == SCHEDULE_WEEKLY and rule.get("weekday") is not None:
            if candidate_date.weekday() != int(rule["weekday"]):
                continue
        if schedule_type == SCHEDULE_MONTHLY and rule.get("month_day") is not None:
            if candidate_date.day != int(rule["month_day"]):
                continue
        candidate = datetime(candidate_date.year, candidate_date.month, candidate_date.day, hour, minute)
        if candidate >= current:
            return candidate.strftime("%Y-%m-%d %H:%M")
    return ""


def _friendly_rule_status(item):
    if int(item.get("enabled") or 0) != 1:
        return "停止中"

    status = item.get("last_run_status") or ""
    reason = item.get("last_skip_reason") or ""
    failed_count = int(item.get("last_failed_count") or 0)

    if failed_count > 0 or status == STATUS_FAILED or reason in {"通知タイプが不正です"}:
        return "エラー"
    if reason == "対象ユーザーが0人のため送信しませんでした":
        return "対象者なし"
    if status == STATUS_SENT or reason == "本日は送信済みです":
        return "送信済み"
    if not item.get("last_checked_at"):
        return "送信待ち"
    if reason in {"送信時刻前です", "曜日が一致しません", "日付が一致しません"}:
        return "送信待ち"
    if reason in {"無効です"}:
        return "正常"
    if reason:
        return "エラー"
    return "正常"


def _format_rule(row):
    item = _row_to_dict(row)
    item["id"] = int(item["id"])
    item["enabled"] = int(item.get("enabled") or 0)
    item["weekday"] = None if item.get("weekday") is None else int(item["weekday"])
    item["month_day"] = None if item.get("month_day") is None else int(item["month_day"])
    item["user_id_values"] = _loads_user_ids(item.get("user_ids"))
    item["schedule_label"] = SCHEDULE_LABELS.get(item.get("schedule_type"), item.get("schedule_type") or "")
    item["target_label"] = TARGET_LABELS.get(item.get("target_type"), item.get("target_type") or "")
    item["timing_label"] = format_rule_timing(item)
    item["next_run_display"] = _next_rule_run_at(item)
    item["last_sent_display"] = _format_dt(item.get("last_sent_at")) or "未送信"
    item["last_checked_display"] = _format_dt(item.get("last_checked_at"))
    item["last_status_display"] = item.get("last_run_status") or STATUS_CRON_NOT_RUN
    item["last_skip_reason_display"] = item.get("last_skip_reason") or ""
    item["status_label"] = _friendly_rule_status(item)
    return item


def format_rule_timing(rule):
    schedule_type = rule.get("schedule_type")
    send_time = rule.get("send_time") or ""
    if schedule_type == SCHEDULE_DAILY:
        return send_time
    if schedule_type == SCHEDULE_WEEKLY:
        weekday = rule.get("weekday")
        try:
            weekday_label = WEEKDAY_LABELS[int(weekday)]
        except (TypeError, ValueError, IndexError):
            weekday_label = "-"
        return f"{weekday_label} {send_time}"
    if schedule_type == SCHEDULE_MONTHLY:
        month_day = rule.get("month_day")
        return f"{month_day or '-'}日 {send_time}"
    return send_time


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
    if target_type == TARGET_TOMORROW_ASSIGNED:
        target_type = TARGET_ASSIGNED
    with get_conn() as conn:
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


def _insert_notification_log(c, title, message, target_type, target_date, notification_rule_id=None, rule_run_key=None, status=LOG_STATUS_SENDING):
    created_at = now_jst().strftime("%Y-%m-%d %H:%M:%S")
    if using_postgres():
        row = c.execute("""
            INSERT INTO notification_logs(
                title, message, target_type, target_date, sent_count, failed_count, status,
                notification_rule_id, rule_run_key, created_at
            )
            VALUES(?, ?, ?, ?, 0, 0, ?, ?, ?, ?)
            ON CONFLICT(notification_rule_id, rule_run_key) DO NOTHING
            RETURNING id
        """, (title, message, target_type, target_date or None, status, notification_rule_id, rule_run_key, created_at)).fetchone()
        return int(row["id"]) if row else None
    c.execute("""
        INSERT INTO notification_logs(
            title, message, target_type, target_date, sent_count, failed_count, status,
            notification_rule_id, rule_run_key, created_at
        )
        VALUES(?, ?, ?, ?, 0, 0, ?, ?, ?, ?)
        ON CONFLICT(notification_rule_id, rule_run_key) DO NOTHING
    """, (title, message, target_type, target_date or None, status, notification_rule_id, rule_run_key, created_at))
    return int(c.lastrowid) if c.rowcount else None


def _get_notification_log_by_run_key(c, notification_rule_id, rule_run_key):
    if notification_rule_id is None or not rule_run_key:
        return None
    return c.execute("""
        SELECT id, status, created_at, sent_count, failed_count, error_text
        FROM notification_logs
        WHERE notification_rule_id = ?
          AND rule_run_key = ?
        LIMIT 1
    """, (int(notification_rule_id), rule_run_key)).fetchone()


def _mark_stale_notification_log(c, log_id):
    c.execute("""
        UPDATE notification_logs
        SET status = ?, error_text = COALESCE(NULLIF(error_text, ''), ?)
        WHERE id = ?
          AND status IN (?, ?)
    """, (
        LOG_STATUS_FAILED_STALE,
        "notification run became stale before completion; skipped to avoid duplicate sends",
        int(log_id),
        LOG_STATUS_PENDING,
        LOG_STATUS_SENDING,
    ))


def _create_notification_log(title, message, target_type, target_date, notification_rule_id=None, rule_run_key=None):
    with get_conn() as conn:
        c = conn.cursor()
        try:
            log_id = _insert_notification_log(
                c,
                title,
                message,
                target_type,
                target_date,
                notification_rule_id=notification_rule_id,
                rule_run_key=rule_run_key,
                status=LOG_STATUS_SENDING,
            )
            if log_id is None:
                existing = _get_notification_log_by_run_key(c, notification_rule_id, rule_run_key)
                existing_status = str(existing["status"] or "") if existing else ""
                if existing and str(existing["status"] or "") in LOG_ACTIVE_STATUSES:
                    cutoff = (now_jst() - timedelta(minutes=LOG_STALE_AFTER_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
                    if str(existing["created_at"] or "") < cutoff:
                        _mark_stale_notification_log(c, existing["id"])
                        existing_status = LOG_STATUS_FAILED_STALE
                conn.commit()
                return {
                    "claimed": False,
                    "log_id": int(existing["id"]) if existing else None,
                    "status": existing_status,
                    "skipped_reason": "notification run already claimed",
                }
            conn.commit()
            return {"claimed": True, "log_id": log_id, "status": LOG_STATUS_SENDING, "skipped_reason": None}
        except Exception:
            conn.rollback()
            raise


def _notification_log_final_status(sent_count, failed_count):
    if int(failed_count or 0) == 0:
        return LOG_STATUS_SENT
    if int(sent_count or 0) > 0:
        return LOG_STATUS_PARTIAL_FAILED
    return LOG_STATUS_FAILED


def _save_notification_results(log_id, recipients, delivery_results, sent_count, failed_count, error_text, status):
    with get_conn() as conn:
        c = conn.cursor()
        try:
            for recipient, result in zip(recipients, delivery_results):
                c.execute("""
                    INSERT INTO notification_recipients(notification_log_id, user_id, line_user_id, status, error_text)
                    VALUES(?, ?, ?, ?, ?)
                """, (
                    log_id,
                    recipient["user_id"],
                    recipient["line_user_id"],
                    result["status"],
                    result["error"],
                ))
            c.execute("""
                UPDATE notification_logs
                SET sent_count = ?, failed_count = ?, status = ?, error_text = ?
                WHERE id = ?
            """, (sent_count, failed_count, status, error_text, log_id))
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def _mark_notification_result_save_failed(log_id, sent_count, failed_count, error_text, save_error):
    final_status = _notification_log_final_status(sent_count, failed_count)
    combined_error = "\n".join(
        value for value in (
            error_text,
            f"result save failed after LINE send: {save_error}",
        )
        if value
    )
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE notification_logs
            SET sent_count = ?, failed_count = ?, status = ?, error_text = ?
            WHERE id = ?
        """, (sent_count, failed_count, final_status, combined_error, int(log_id)))
        conn.commit()


def send_notification(
    title: str,
    message: str,
    target_type: str,
    target_date: str = "",
    user_ids=None,
    recipient_target_type: str = None,
    notification_rule_id=None,
    rule_run_key: str = None,
    recipients=None,
):
    if recipients is None:
        recipients = get_recipients(recipient_target_type or target_type, target_date, user_ids)
    claim = _create_notification_log(
        title,
        message,
        target_type,
        target_date,
        notification_rule_id=notification_rule_id,
        rule_run_key=rule_run_key,
    )
    log_id = claim["log_id"]
    if not claim["claimed"]:
        return {
            "log_id": log_id,
            "target_count": len(recipients),
            "sent_count": 0,
            "failed_count": 0,
            "error_text": None,
            "status": claim["status"],
            "skipped": True,
            "skipped_reason": claim["skipped_reason"],
        }

    sent_count = 0
    failed_count = 0
    errors = []
    delivery_results = []
    for recipient in recipients:
        ok, error = send_line_message(recipient["line_user_id"], message)
        status = "sent" if ok else "failed"
        if ok:
            sent_count += 1
        else:
            failed_count += 1
            if error:
                errors.append(f'{recipient["name"] or recipient["user_id"]}: {error}')
        delivery_results.append({"status": status, "error": error})

    error_text = "\n".join(errors) if errors else None
    final_status = _notification_log_final_status(sent_count, failed_count)
    try:
        _save_notification_results(log_id, recipients, delivery_results, sent_count, failed_count, error_text, final_status)
    except Exception as exc:
        try:
            _mark_notification_result_save_failed(log_id, sent_count, failed_count, error_text, exc)
        except Exception:
            pass
        raise
    return {
        "log_id": log_id,
        "target_count": len(recipients),
        "sent_count": sent_count,
        "failed_count": failed_count,
        "error_text": error_text,
        "status": final_status,
        "skipped": False,
        "skipped_reason": None,
    }


def _cron_already_running_result(current):
    return {
        "ok": True,
        "now": current.strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": TIMEZONE_NAME,
        "checked_rules": 0,
        "matched_rules": 0,
        "sent_rules": 0,
        "sent_notifications": 0,
        "skipped_rules": 0,
        "skipped_reason": "previous notification run is still running",
        "results": [],
    }


def _legacy_rule_exists(c, name):
    row = c.execute("SELECT id FROM notification_rules WHERE name = ? LIMIT 1", (name,)).fetchone()
    return row is not None


def ensure_legacy_notification_rules_migrated():
    if get_setting(LEGACY_RULES_MIGRATED_KEY) == "1":
        return
    values = get_settings(NOTIFICATION_SETTING_KEYS)
    has_legacy_value = any(values.get(key) is not None for key in NOTIFICATION_SETTING_KEYS)
    if not has_legacy_value:
        upsert_setting(LEGACY_RULES_MIGRATED_KEY, "1")
        return

    now_text = now_jst().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        c = conn.cursor()
        if (
            values.get(NOTIFY_DEADLINE_ENABLED_KEY) is not None or
            values.get(NOTIFY_DEADLINE_TIME_KEY) is not None
        ) and not _legacy_rule_exists(c, "シフト提出リマインド"):
            c.execute("""
                INSERT INTO notification_rules(
                    name, enabled, schedule_type, send_time, target_type, target_date_mode,
                    title, message, user_ids, created_at, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "シフト提出リマインド",
                1 if _is_enabled(values.get(NOTIFY_DEADLINE_ENABLED_KEY)) else 0,
                SCHEDULE_DAILY,
                values.get(NOTIFY_DEADLINE_TIME_KEY) or "09:00",
                TARGET_UNSUBMITTED,
                TARGET_DATE_DEADLINE_TOMORROW,
                "シフト提出リマインド",
                "【シフト提出リマインド】\nシフト提出期限が近づいています。\nまだ提出していない方は、シフト便から提出をお願いします。",
                "[]",
                now_text,
                now_text,
            ))
        if (
            values.get(NOTIFY_CONFIRMED_ENABLED_KEY) is not None or
            values.get(NOTIFY_CONFIRMED_TIME_KEY) is not None
        ) and not _legacy_rule_exists(c, "明日のシフト確認"):
            c.execute("""
                INSERT INTO notification_rules(
                    name, enabled, schedule_type, send_time, target_type, target_date_mode,
                    title, message, user_ids, created_at, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "明日のシフト確認",
                1 if _is_enabled(values.get(NOTIFY_CONFIRMED_ENABLED_KEY)) else 0,
                SCHEDULE_DAILY,
                values.get(NOTIFY_CONFIRMED_TIME_KEY) or "18:00",
                TARGET_TOMORROW_ASSIGNED,
                TARGET_DATE_TOMORROW,
                "明日のシフト確認",
                "【明日のシフト確認】\n明日は確定シフトがあります。\nシフト便で時間を確認してください。",
                "[]",
                now_text,
                now_text,
            ))
        conn.commit()
    upsert_setting(LEGACY_RULES_MIGRATED_KEY, "1")


def get_notification_rules():
    ensure_legacy_notification_rules_migrated()
    with get_conn() as conn:
        c = conn.cursor()
        rows = c.execute("""
            SELECT *
            FROM notification_rules
            ORDER BY enabled DESC, id DESC
        """).fetchall()
        return [_format_rule(row) for row in rows]


def get_notification_rule(rule_id: int):
    ensure_legacy_notification_rules_migrated()
    with get_conn() as conn:
        c = conn.cursor()
        row = c.execute("SELECT * FROM notification_rules WHERE id = ?", (int(rule_id),)).fetchone()
        return _format_rule(row) if row else None


def _validate_rule_payload(data):
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("通知名を入力してください")
    schedule_type = (data.get("schedule_type") or "").strip()
    if schedule_type not in SCHEDULE_TYPES:
        raise ValueError("通知タイプが不正です")
    send_time = (data.get("send_time") or "").strip()
    if not is_valid_time_hhmm(send_time):
        raise ValueError("送信時刻が不正です")

    weekday = None
    month_day = None
    if schedule_type == SCHEDULE_WEEKLY:
        try:
            weekday = int(data.get("weekday"))
        except (TypeError, ValueError):
            raise ValueError("曜日を選択してください")
        if weekday < 0 or weekday > 6:
            raise ValueError("曜日を選択してください")
    if schedule_type == SCHEDULE_MONTHLY:
        try:
            month_day = int(data.get("month_day"))
        except (TypeError, ValueError):
            raise ValueError("日付を入力してください")
        if month_day < 1 or month_day > 31:
            raise ValueError("日付は1から31で入力してください")

    target_type = (data.get("target_type") or "").strip()
    if target_type not in RULE_TARGET_TYPES:
        raise ValueError("対象者が不正です")
    target_date_mode = (data.get("target_date_mode") or "").strip()
    if target_date_mode not in TARGET_DATE_MODES:
        target_date_mode = TARGET_DATE_TOMORROW if target_type == TARGET_TOMORROW_ASSIGNED else TARGET_DATE_DEADLINE_TOMORROW
    title = (data.get("title") or "").strip()
    message = (data.get("message") or "").strip()
    if not message:
        raise ValueError("メッセージ本文を入力してください")
    user_ids = data.get("user_ids") or []
    if target_type == TARGET_INDIVIDUAL and not _loads_user_ids(_dumps_user_ids(user_ids)):
        raise ValueError("個別ユーザーを選択してください")

    return {
        "name": name,
        "enabled": 1 if data.get("enabled") else 0,
        "schedule_type": schedule_type,
        "weekday": weekday,
        "month_day": month_day,
        "send_time": send_time,
        "target_type": target_type,
        "target_date_mode": target_date_mode,
        "title": title,
        "message": message,
        "user_ids": _dumps_user_ids(user_ids),
    }


def save_notification_rule(data, rule_id=None):
    ensure_legacy_notification_rules_migrated()
    values = _validate_rule_payload(data)
    now_text = now_jst().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        c = conn.cursor()
        if rule_id:
            c.execute("""
                UPDATE notification_rules
                SET name = ?, enabled = ?, schedule_type = ?, weekday = ?, month_day = ?, send_time = ?,
                    target_type = ?, target_date_mode = ?, title = ?, message = ?, user_ids = ?, updated_at = ?
                WHERE id = ?
            """, (
                values["name"],
                values["enabled"],
                values["schedule_type"],
                values["weekday"],
                values["month_day"],
                values["send_time"],
                values["target_type"],
                values["target_date_mode"],
                values["title"],
                values["message"],
                values["user_ids"],
                now_text,
                int(rule_id),
            ))
            if c.rowcount == 0:
                raise ValueError("通知ルールが見つかりません")
            saved_id = int(rule_id)
        elif using_postgres():
            row = c.execute("""
                INSERT INTO notification_rules(
                    name, enabled, schedule_type, weekday, month_day, send_time, target_type,
                    target_date_mode, title, message, user_ids, created_at, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
            """, (
                values["name"],
                values["enabled"],
                values["schedule_type"],
                values["weekday"],
                values["month_day"],
                values["send_time"],
                values["target_type"],
                values["target_date_mode"],
                values["title"],
                values["message"],
                values["user_ids"],
                now_text,
                now_text,
            )).fetchone()
            saved_id = int(row["id"])
        else:
            c.execute("""
                INSERT INTO notification_rules(
                    name, enabled, schedule_type, weekday, month_day, send_time, target_type,
                    target_date_mode, title, message, user_ids, created_at, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                values["name"],
                values["enabled"],
                values["schedule_type"],
                values["weekday"],
                values["month_day"],
                values["send_time"],
                values["target_type"],
                values["target_date_mode"],
                values["title"],
                values["message"],
                values["user_ids"],
                now_text,
                now_text,
            ))
            saved_id = int(c.lastrowid)
        conn.commit()
        return saved_id


def set_notification_rule_enabled(rule_id: int, enabled: bool):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE notification_rules
            SET enabled = ?, updated_at = ?
            WHERE id = ?
        """, (1 if enabled else 0, now_jst().strftime("%Y-%m-%d %H:%M:%S"), int(rule_id)))
        updated = c.rowcount
        conn.commit()
        return updated


def delete_notification_rule(rule_id: int):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM notification_rules WHERE id = ?", (int(rule_id),))
        deleted = c.rowcount
        conn.commit()
        return deleted


def get_notification_logs(limit: int = 20):
    with get_conn() as conn:
        c = conn.cursor()
        rows = c.execute("""
            SELECT id, title, message, target_type, target_date, sent_count, failed_count, error_text,
                   notification_rule_id, rule_run_key, status, created_at
            FROM notification_logs
            ORDER BY id DESC
            LIMIT ?
        """, (int(limit),)).fetchall()
        return [_format_notification_log(row) for row in rows]


def _format_notification_log(row):
    item = dict(row)
    if item.get("notification_rule_id"):
        item["target_type_display"] = "自動ルール"
    else:
        item["target_type_display"] = TARGET_LABELS.get(item.get("target_type"), item.get("target_type") or "")
    item["created_at_display"] = _format_dt(item.get("created_at"))
    return item


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


def _rule_match_status(rule, current):
    if int(rule.get("enabled") or 0) != 1:
        return False, "無効です"
    if not _time_has_passed(rule.get("send_time") or "", current):
        return False, "送信時刻前です"
    schedule_type = rule.get("schedule_type")
    if schedule_type == SCHEDULE_DAILY:
        return True, None
    if schedule_type == SCHEDULE_WEEKLY:
        if rule.get("weekday") is not None and int(rule["weekday"]) == current.weekday():
            return True, None
        return False, "曜日が一致しません"
    if schedule_type == SCHEDULE_MONTHLY:
        if rule.get("month_day") is not None and int(rule["month_day"]) == current.day:
            return True, None
        return False, "日付が一致しません"
    return False, "通知タイプが不正です"


def _rule_run_key(rule, current):
    return f"{int(rule['id'])}:{rule['schedule_type']}:{current.strftime('%Y-%m-%d')}:{rule['send_time']}"


def _has_rule_run_sent(rule_id: int, run_key: str):
    with get_conn() as conn:
        c = conn.cursor()
        row = c.execute("""
            SELECT id
            FROM notification_logs
            WHERE notification_rule_id = ?
              AND rule_run_key = ?
              AND status IN (?, ?)
            LIMIT 1
        """, (int(rule_id), run_key, LOG_STATUS_SENT, LOG_STATUS_PARTIAL_FAILED)).fetchone()
        return row is not None


def _update_rule_last_sent(rule_id: int, sent_at):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE notification_rules
            SET last_sent_at = ?, updated_at = ?
            WHERE id = ?
        """, (
            sent_at.strftime("%Y-%m-%d %H:%M:%S"),
            now_jst().strftime("%Y-%m-%d %H:%M:%S"),
            int(rule_id),
        ))
        conn.commit()


def _update_rule_run_result(rule_id: int, current, status: str, skip_reason: str = None, target_count: int = 0, sent_count: int = 0, failed_count: int = 0, mark_sent: bool = False):
    checked_at = current.strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        c = conn.cursor()
        if mark_sent:
            c.execute("""
                UPDATE notification_rules
                SET last_checked_at = ?, last_sent_at = ?, last_run_status = ?, last_skip_reason = ?,
                    last_target_count = ?, last_sent_count = ?, last_failed_count = ?, updated_at = ?
                WHERE id = ?
            """, (
                checked_at,
                checked_at,
                status,
                skip_reason,
                int(target_count or 0),
                int(sent_count or 0),
                int(failed_count or 0),
                now_jst().strftime("%Y-%m-%d %H:%M:%S"),
                int(rule_id),
            ))
        else:
            c.execute("""
                UPDATE notification_rules
                SET last_checked_at = ?, last_run_status = ?, last_skip_reason = ?,
                    last_target_count = ?, last_sent_count = ?, last_failed_count = ?, updated_at = ?
                WHERE id = ?
            """, (
                checked_at,
                status,
                skip_reason,
                int(target_count or 0),
                int(sent_count or 0),
                int(failed_count or 0),
                now_jst().strftime("%Y-%m-%d %H:%M:%S"),
                int(rule_id),
            ))
        conn.commit()


def _resolve_rule_target(rule, current):
    target_type = rule.get("target_type")
    mode = rule.get("target_date_mode") or TARGET_DATE_TODAY
    if target_type == TARGET_ALL:
        return "", TARGET_ALL, []
    if target_type == TARGET_INDIVIDUAL:
        return "", TARGET_INDIVIDUAL, rule.get("user_id_values") or []
    if target_type == TARGET_TOMORROW_ASSIGNED:
        return to_ymd(current.date() + timedelta(days=1)), TARGET_ASSIGNED, []
    if target_type == TARGET_UNSUBMITTED:
        if mode == TARGET_DATE_TODAY:
            return to_ymd(current.date()), TARGET_UNSUBMITTED, []
        if mode == TARGET_DATE_TOMORROW:
            return to_ymd(current.date() + timedelta(days=1)), TARGET_UNSUBMITTED, []
        shift_date = _find_shift_date_with_deadline_on(current.date() + timedelta(days=1))
        return (to_ymd(shift_date) if shift_date else ""), TARGET_UNSUBMITTED, []
    return "", target_type, []


def _run_due_notifications_legacy_unused(current=None):
    current = _normalize_current(current)
    if not _run_notifications_lock.acquire(blocking=False):
        return _cron_already_running_result(current)

    try:
        ensure_legacy_notification_rules_migrated()
        rules = get_notification_rules()
        results = []

        for rule in rules:
            matched, reason = _rule_match_status(rule, current)
            base = {
                "rule_id": rule["id"],
                "name": rule["name"],
                "matched": matched,
                "target_count": 0,
                "sent_count": 0,
                "failed_count": 0,
                "skipped_reason": reason,
            }
            if not matched:
                _update_rule_run_result(rule["id"], current, STATUS_SKIPPED, reason)
                results.append(base)
                continue

            run_key = _rule_run_key(rule, current)
            if _has_rule_run_sent(rule["id"], run_key):
                reason = "本日は送信済みです"
                _update_rule_run_result(rule["id"], current, STATUS_SKIPPED, reason)
                results.append({**base, "skipped_reason": reason})
                continue

            target_date, recipient_target_type, user_ids = _resolve_rule_target(rule, current)
            if rule["target_type"] in {TARGET_UNSUBMITTED, TARGET_TOMORROW_ASSIGNED} and not target_date:
                reason = "対象日が見つかりません"
                _update_rule_run_result(rule["id"], current, STATUS_SKIPPED, reason)
                results.append({**base, "target_date": target_date, "skipped_reason": reason})
                continue

            recipients = get_recipients(recipient_target_type, target_date, user_ids)
            if not recipients:
                reason = "対象ユーザーが0人のため送信しませんでした"
                _update_rule_run_result(rule["id"], current, STATUS_SKIPPED, reason, target_count=0)
                results.append({**base, "target_date": target_date, "skipped_reason": reason})
                continue

            result = send_notification(
                rule.get("title") or rule["name"],
                rule["message"],
                f"rule:{rule['id']}",
                target_date,
                user_ids,
                recipient_target_type=recipient_target_type,
                notification_rule_id=rule["id"],
                rule_run_key=run_key,
                recipients=recipients,
            )
            status = STATUS_SENT if int(result["failed_count"] or 0) == 0 else STATUS_FAILED
            _update_rule_run_result(
                rule["id"],
                current,
                status,
                None,
                target_count=result["target_count"],
                sent_count=result["sent_count"],
                failed_count=result["failed_count"],
                mark_sent=True,
            )
            results.append({
                **base,
                **result,
                "target_date": target_date,
                "skipped_reason": None,
            })

        sent_rules = sum(1 for item in results if item["matched"] and item["skipped_reason"] is None)
        skipped_rules = sum(1 for item in results if item["skipped_reason"])
        return {
            "ok": True,
            "now": current.strftime("%Y-%m-%d %H:%M:%S"),
            "timezone": TIMEZONE_NAME,
            "checked_rules": len(rules),
            "matched_rules": sum(1 for item in results if item["matched"]),
            "sent_rules": sent_rules,
            "sent_notifications": sum(int(item.get("sent_count") or 0) for item in results),
            "skipped_rules": skipped_rules,
            "results": results,
        }
    finally:
        _run_notifications_lock.release()


def run_due_notifications(current=None):
    current = _normalize_current(current)
    if not _run_notifications_lock.acquire(blocking=False):
        return _cron_already_running_result(current)

    try:
        ensure_legacy_notification_rules_migrated()
        rules = get_notification_rules()
        results = []

        for rule in rules:
            matched, reason = _rule_match_status(rule, current)
            base = {
                "rule_id": rule["id"],
                "name": rule["name"],
                "matched": matched,
                "target_count": 0,
                "sent_count": 0,
                "failed_count": 0,
                "skipped_reason": reason,
            }
            if not matched:
                _update_rule_run_result(rule["id"], current, STATUS_SKIPPED, reason)
                results.append(base)
                continue

            run_key = _rule_run_key(rule, current)
            target_date, recipient_target_type, user_ids = _resolve_rule_target(rule, current)
            if rule["target_type"] in {TARGET_UNSUBMITTED, TARGET_TOMORROW_ASSIGNED} and not target_date:
                reason = "target date was not found"
                _update_rule_run_result(rule["id"], current, STATUS_SKIPPED, reason)
                results.append({**base, "target_date": target_date, "skipped_reason": reason})
                continue

            recipients = get_recipients(recipient_target_type, target_date, user_ids)
            if not recipients:
                reason = "no notification recipients"
                _update_rule_run_result(rule["id"], current, STATUS_SKIPPED, reason, target_count=0)
                results.append({**base, "target_date": target_date, "skipped_reason": reason})
                continue

            result = send_notification(
                rule.get("title") or rule["name"],
                rule["message"],
                f"rule:{rule['id']}",
                target_date,
                user_ids,
                recipient_target_type=recipient_target_type,
                notification_rule_id=rule["id"],
                rule_run_key=run_key,
                recipients=recipients,
            )
            if result.get("skipped"):
                reason = result.get("skipped_reason") or "notification run already claimed"
                _update_rule_run_result(rule["id"], current, STATUS_SKIPPED, reason)
                results.append({
                    **base,
                    **result,
                    "target_date": target_date,
                    "skipped_reason": reason,
                })
                continue

            status = STATUS_SENT if result.get("status") == LOG_STATUS_SENT else STATUS_FAILED
            _update_rule_run_result(
                rule["id"],
                current,
                status,
                None,
                target_count=result["target_count"],
                sent_count=result["sent_count"],
                failed_count=result["failed_count"],
                mark_sent=True,
            )
            results.append({
                **base,
                **result,
                "target_date": target_date,
                "skipped_reason": None,
            })

        sent_rules = sum(1 for item in results if item["matched"] and item["skipped_reason"] is None)
        skipped_rules = sum(1 for item in results if item["skipped_reason"])
        return {
            "ok": True,
            "now": current.strftime("%Y-%m-%d %H:%M:%S"),
            "timezone": TIMEZONE_NAME,
            "checked_rules": len(rules),
            "matched_rules": sum(1 for item in results if item["matched"]),
            "sent_rules": sent_rules,
            "sent_notifications": sum(int(item.get("sent_count") or 0) for item in results),
            "skipped_rules": skipped_rules,
            "results": results,
        }
    finally:
        _run_notifications_lock.release()

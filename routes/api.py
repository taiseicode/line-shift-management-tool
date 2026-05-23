import os
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from db import get_conn, get_table_columns, invalidate_table_columns_cache, using_postgres
from repositories.shift_repository import get_my_entries_range, upsert_shift_entry, delete_entry
from repositories.user_repository import get_user_by_line_id, upsert_user
from services.auth_service import require_verified_line_claims, reject_if_user_inactive, verify_line_id_token
from services.deadline_service import build_deadline_status_payload, get_active_deadline_config, reject_if_submission_closed_for_date
from utils import parse_ymd, to_ymd, is_valid_time_hhmm, hhmm_to_minutes


api_bp = Blueprint("api", __name__)
CONFIRMED_SHIFT_LOCK_MESSAGE = "この日はすでにシフトが確定しているため、変更できません。"
API_DEBUG_MODE = os.getenv("DEBUG_MODE", "").strip().lower() in ("1", "true", "yes", "on")


def get_verified_line_user_for_api():
    claims, data, error_response = require_verified_line_claims()
    if error_response:
        return None, data, error_response
    line_user_id = (claims.get("sub") or "").strip()
    if not line_user_id:
        return None, data, (jsonify({"error": "LINE認証に失敗しました"}), 401)
    return claims, data, None


def _weekday_jp(date_obj):
    return ["日", "月", "火", "水", "木", "金", "土"][(date_obj.weekday() + 1) % 7]


def _row_to_dict(row):
    return {key: row[key] for key in row.keys()}


def _get_table_columns(table_name: str):
    return get_table_columns(table_name)


def _get_my_confirmed_decisions(user_id: int, start_ymd: str, end_ymd: str):
    confirmed_columns = _get_table_columns("confirmed_shifts")
    start_expr = "cs.confirmed_start_time" if "confirmed_start_time" in confirmed_columns else "cs.start_time"
    end_expr = "cs.confirmed_end_time" if "confirmed_end_time" in confirmed_columns else "cs.end_time"
    sql = f"""
        SELECT cs.id, cs.user_id, u.line_user_id, u.name, u.active,
               cs.date,
               {start_expr} AS confirmed_start_time,
               {end_expr} AS confirmed_end_time,
               cs.start_time AS raw_start_time,
               cs.end_time AS raw_end_time,
               cs.is_assigned,
               cs.source_entry_id
        FROM confirmed_shifts cs
        LEFT JOIN users u ON u.id = cs.user_id
        WHERE cs.user_id = ?
          AND cs.date >= ?
          AND cs.date <= ?
        ORDER BY cs.date
    """
    params = (int(user_id), start_ymd, end_ymd)
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute(sql, params)
        rows = [_row_to_dict(row) for row in c.fetchall()]
        return {
            "table": "confirmed_shifts",
            "columns": confirmed_columns,
            "sql": " ".join(sql.split()),
            "params": list(params),
            "rows": rows,
            "count": len(rows),
        }
    finally:
        conn.close()


def _get_my_confirmed_decisions_all(user_id: int):
    confirmed_columns = _get_table_columns("confirmed_shifts")
    start_expr = "cs.confirmed_start_time" if "confirmed_start_time" in confirmed_columns else "cs.start_time"
    end_expr = "cs.confirmed_end_time" if "confirmed_end_time" in confirmed_columns else "cs.end_time"
    sql = f"""
        SELECT cs.id, cs.user_id, u.line_user_id, u.name, u.active,
               cs.date,
               {start_expr} AS confirmed_start_time,
               {end_expr} AS confirmed_end_time,
               cs.start_time AS raw_start_time,
               cs.end_time AS raw_end_time,
               cs.is_assigned,
               cs.source_entry_id
        FROM confirmed_shifts cs
        LEFT JOIN users u ON u.id = cs.user_id
        WHERE cs.user_id = ?
        ORDER BY cs.date
    """
    params = (int(user_id),)
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute(sql, params)
        rows = [_row_to_dict(row) for row in c.fetchall()]
        return {
            "sql": " ".join(sql.split()),
            "params": list(params),
            "rows": rows,
            "count": len(rows),
        }
    finally:
        conn.close()


def _confirmed_decision_to_item(decision):
    confirmed_start_time = decision.get("confirmed_start_time")
    confirmed_end_time = decision.get("confirmed_end_time")
    shift_d = parse_ymd(decision.get("date"))
    return {
        "id": decision.get("id"),
        "date": decision.get("date"),
        "weekday": _weekday_jp(shift_d) if shift_d else "",
        "status": "confirmed",
        "start_time": confirmed_start_time,
        "end_time": confirmed_end_time,
        "confirmed_start_time": confirmed_start_time,
        "confirmed_end_time": confirmed_end_time,
    }


def _is_confirmed_decision(decision):
    return (
        decision
        and int(decision.get("is_assigned") or 0) == 1
        and decision.get("confirmed_start_time")
        and decision.get("confirmed_end_time")
    )


def _ensure_user_pay_settings_table():
    conn = get_conn()
    try:
        c = conn.cursor()
        if using_postgres():
            c.execute("""
                CREATE TABLE IF NOT EXISTS user_pay_settings (
                    user_id INTEGER PRIMARY KEY REFERENCES users(id),
                    hourly_wage INTEGER,
                    break_rule TEXT NOT NULL DEFAULT 'legal_jp',
                    night_enabled INTEGER NOT NULL DEFAULT 1,
                    overtime_enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
        else:
            c.execute("""
                CREATE TABLE IF NOT EXISTS user_pay_settings (
                    user_id INTEGER PRIMARY KEY,
                    hourly_wage INTEGER,
                    break_rule TEXT NOT NULL DEFAULT 'legal_jp',
                    night_enabled INTEGER NOT NULL DEFAULT 1,
                    overtime_enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            """)
        if using_postgres():
            c.execute("ALTER TABLE user_pay_settings ADD COLUMN IF NOT EXISTS hourly_wage INTEGER")
            c.execute("ALTER TABLE user_pay_settings ADD COLUMN IF NOT EXISTS break_rule TEXT NOT NULL DEFAULT 'legal_jp'")
            c.execute("ALTER TABLE user_pay_settings ADD COLUMN IF NOT EXISTS night_enabled INTEGER NOT NULL DEFAULT 1")
            c.execute("ALTER TABLE user_pay_settings ADD COLUMN IF NOT EXISTS overtime_enabled INTEGER NOT NULL DEFAULT 1")
            c.execute("ALTER TABLE user_pay_settings ADD COLUMN IF NOT EXISTS created_at TEXT")
            c.execute("ALTER TABLE user_pay_settings ADD COLUMN IF NOT EXISTS updated_at TEXT")
            invalidate_table_columns_cache("user_pay_settings")
        else:
            columns = get_table_columns("user_pay_settings")
            schema_changed = False
            if "hourly_wage" not in columns:
                c.execute("ALTER TABLE user_pay_settings ADD COLUMN hourly_wage INTEGER")
                schema_changed = True
            if "break_rule" not in columns:
                c.execute("ALTER TABLE user_pay_settings ADD COLUMN break_rule TEXT NOT NULL DEFAULT 'legal_jp'")
                schema_changed = True
            if "night_enabled" not in columns:
                c.execute("ALTER TABLE user_pay_settings ADD COLUMN night_enabled INTEGER NOT NULL DEFAULT 1")
                schema_changed = True
            if "overtime_enabled" not in columns:
                c.execute("ALTER TABLE user_pay_settings ADD COLUMN overtime_enabled INTEGER NOT NULL DEFAULT 1")
                schema_changed = True
            if "created_at" not in columns:
                c.execute("ALTER TABLE user_pay_settings ADD COLUMN created_at TEXT")
                schema_changed = True
            if "updated_at" not in columns:
                c.execute("ALTER TABLE user_pay_settings ADD COLUMN updated_at TEXT")
                schema_changed = True
            if schema_changed:
                invalidate_table_columns_cache("user_pay_settings")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("UPDATE user_pay_settings SET break_rule = 'legal_jp' WHERE break_rule IS NULL OR break_rule = '' OR break_rule = 'over_6h_1h'")
        c.execute("UPDATE user_pay_settings SET night_enabled = 1 WHERE night_enabled IS NULL")
        c.execute("UPDATE user_pay_settings SET overtime_enabled = 1 WHERE overtime_enabled IS NULL")
        c.execute("UPDATE user_pay_settings SET created_at = ? WHERE created_at IS NULL OR created_at = ''", (now,))
        c.execute("UPDATE user_pay_settings SET updated_at = ? WHERE updated_at IS NULL OR updated_at = ''", (now,))
        conn.commit()
    finally:
        conn.close()


def _get_verified_user_from_headers():
    line_user_id = (request.headers.get("X-Line-User-Id") or "").strip()
    id_token = (request.headers.get("X-Line-Id-Token") or "").strip()
    if not id_token:
        return None, None, (jsonify({"error": "id_token is required"}), 401)
    try:
        claims = verify_line_id_token(id_token)
    except RuntimeError:
        return None, None, (jsonify({"error": "LINE auth server settings are missing"}), 500)
    except ValueError:
        return None, None, (jsonify({"error": "LINE auth failed"}), 401)

    token_line_user_id = (claims.get("sub") or "").strip()
    if not line_user_id:
        line_user_id = token_line_user_id
    if not line_user_id:
        return None, None, (jsonify({"error": "LINE user ID could not be resolved"}), 401)
    if token_line_user_id != line_user_id:
        return None, None, (jsonify({"error": "LINE auth failed"}), 401)

    user = get_user_by_line_id(line_user_id)
    inactive_response = reject_if_user_inactive(user)
    if inactive_response:
        return None, None, inactive_response
    if not user:
        upsert_user(line_user_id, (claims.get("name") or "未設定").strip() or "未設定")
        user = get_user_by_line_id(line_user_id)
    elif not (user["name"] or "").strip():
        upsert_user(line_user_id, (claims.get("name") or "未設定").strip() or "未設定")
        user = get_user_by_line_id(line_user_id)
    return user, claims, None

def _default_pay_settings():
    return {
        "hourly_wage": None,
        "break_rule": "legal_jp",
        "night_enabled": True,
        "overtime_enabled": True,
    }


def _normalize_break_rule(value):
    if value == "over_6h_1h":
        return "legal_jp"
    if value in ("none", "legal_jp"):
        return value
    return "legal_jp"


def _to_bool_flag(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return int(value) == 1
    return str(value).strip().lower() in ("1", "true", "on", "yes")


def _pay_settings_to_dict(row, user_id=None):
    settings = _default_pay_settings()
    if user_id is not None:
        settings["user_id"] = int(user_id)
    if not row:
        return settings
    settings.update({
        "user_id": int(row["user_id"]) if "user_id" in row.keys() else settings.get("user_id"),
        "hourly_wage": int(row["hourly_wage"]) if row["hourly_wage"] is not None else None,
        "break_rule": _normalize_break_rule(row["break_rule"]),
        "night_enabled": int(row["night_enabled"] or 0) == 1,
        "overtime_enabled": int(row["overtime_enabled"] or 0) == 1,
    })
    return settings


def _pay_settings_found(user_id: int):
    _ensure_user_pay_settings_table()
    conn = get_conn()
    try:
        c = conn.cursor()
        row = c.execute(
            "SELECT 1 FROM user_pay_settings WHERE user_id = ? LIMIT 1",
            (int(user_id),),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _get_pay_settings(user_id: int):
    _ensure_user_pay_settings_table()
    conn = get_conn()
    try:
        c = conn.cursor()
        row = c.execute(
            "SELECT user_id, hourly_wage, break_rule, night_enabled, overtime_enabled FROM user_pay_settings WHERE user_id = ?",
            (int(user_id),),
        ).fetchone()
        return _pay_settings_to_dict(row, user_id)
    finally:
        conn.close()


def _get_pay_settings_row(user_id: int):
    _ensure_user_pay_settings_table()
    conn = get_conn()
    try:
        c = conn.cursor()
        row = c.execute(
            "SELECT user_id, hourly_wage, break_rule, night_enabled, overtime_enabled FROM user_pay_settings WHERE user_id = ?",
            (int(user_id),),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def _pay_settings_debug(line_user_id: str, user, saved_row=None):
    return {
        "received_line_user_id": line_user_id,
        "resolved_user_id": int(user["id"]) if user else None,
        "settings_found": saved_row is not None,
        "saved_row": saved_row,
    }


def _month_bounds(month_value: str):
    try:
        start = datetime.strptime(month_value, "%Y-%m").date().replace(day=1)
    except Exception:
        return None, None
    if start.month == 12:
        next_month = start.replace(year=start.year + 1, month=1)
    else:
        next_month = start.replace(month=start.month + 1)
    end = next_month - timedelta(days=1)
    return start, end


def _time_to_minutes(value: str):
    if not is_valid_time_hhmm(value or ""):
        return None
    return hhmm_to_minutes(value)


def _overlap_minutes(start_a, end_a, start_b, end_b):
    start = max(start_a, start_b)
    end = min(end_a, end_b)
    if end <= start:
        return 0
    return int((end - start).total_seconds() // 60)


def _night_minutes_for_shift(start_dt, end_dt):
    total = 0
    current_day = start_dt.date() - timedelta(days=1)
    last_day = end_dt.date()
    while current_day <= last_day:
        night_start = datetime.combine(current_day, datetime.min.time()) + timedelta(hours=22)
        night_end = datetime.combine(current_day + timedelta(days=1), datetime.min.time()) + timedelta(hours=5)
        total += _overlap_minutes(start_dt, end_dt, night_start, night_end)
        current_day += timedelta(days=1)
    return total


def _calculate_shift_pay_minutes(row, settings):
    start_minutes = _time_to_minutes(row["start_time"])
    end_minutes = _time_to_minutes(row["end_time"])
    shift_date = parse_ymd(row["date"])
    if start_minutes is None or end_minutes is None or not shift_date:
        return None

    start_dt = datetime.combine(shift_date, datetime.min.time()) + timedelta(minutes=start_minutes)
    end_dt = datetime.combine(shift_date, datetime.min.time()) + timedelta(minutes=end_minutes)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)

    scheduled_minutes = max(0, int((end_dt - start_dt).total_seconds() // 60))
    break_minutes = 0
    if settings["break_rule"] == "legal_jp":
        if scheduled_minutes > 480:
            break_minutes = 60
        elif scheduled_minutes > 360:
            break_minutes = 45
    paid_minutes = max(0, scheduled_minutes - break_minutes)
    overtime_minutes = max(0, paid_minutes - 480) if settings["overtime_enabled"] else 0
    night_minutes = _night_minutes_for_shift(start_dt, end_dt) if settings["night_enabled"] else 0
    night_minutes = min(night_minutes, paid_minutes)

    return {
        "scheduled_minutes": scheduled_minutes,
        "break_minutes": break_minutes,
        "paid_minutes": paid_minutes,
        "overtime_minutes": overtime_minutes,
        "night_minutes": night_minutes,
    }


def _count_confirmed_by_line_user_id(line_user_id: str, confirmed_columns):
    if "line_user_id" in confirmed_columns:
        sql = "SELECT COUNT(*) AS count FROM confirmed_shifts WHERE line_user_id = ?"
    else:
        sql = """
            SELECT COUNT(*) AS count
            FROM confirmed_shifts cs
            JOIN users u ON u.id = cs.user_id
            WHERE u.line_user_id = ?
        """
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute(sql, (line_user_id,))
        row = c.fetchone()
        return int(row["count"] or 0) if row else 0
    finally:
        conn.close()


def _build_confirmed_debug_details(line_user_id: str, user, confirmed_columns):
    resolved_user_id = int(user["id"]) if user else None
    conn = get_conn()
    try:
        c = conn.cursor()
        total_row = c.execute("SELECT COUNT(*) AS count FROM confirmed_shifts").fetchone()
        count_for_user_id = 0
        sample_rows = []
        if resolved_user_id is not None:
            count_row = c.execute(
                "SELECT COUNT(*) AS count FROM confirmed_shifts WHERE user_id = ?",
                (resolved_user_id,),
            ).fetchone()
            count_for_user_id = int(count_row["count"] or 0) if count_row else 0
            sample_rows = [
                _row_to_dict(row)
                for row in c.execute("""
                    SELECT cs.*, u.line_user_id, u.name, u.active
                    FROM confirmed_shifts cs
                    LEFT JOIN users u ON u.id = cs.user_id
                    WHERE cs.user_id = ?
                    ORDER BY cs.date
                    LIMIT 10
                """, (resolved_user_id,)).fetchall()
            ]
        if "line_user_id" in confirmed_columns:
            line_count_row = c.execute(
                "SELECT COUNT(*) AS count FROM confirmed_shifts WHERE line_user_id = ?",
                (line_user_id,),
            ).fetchone()
        else:
            line_count_row = c.execute("""
                SELECT COUNT(*) AS count
                FROM confirmed_shifts cs
                JOIN users u ON u.id = cs.user_id
                WHERE u.line_user_id = ?
            """, (line_user_id,)).fetchone()
        return {
            "received_line_user_id": line_user_id,
            "resolved_user_id": resolved_user_id,
            "confirmed_table_columns": confirmed_columns,
            "confirmed_all_count_total": int(total_row["count"] or 0) if total_row else 0,
            "confirmed_count_for_user_id": count_for_user_id,
            "confirmed_count_for_line_user_id": int(line_count_row["count"] or 0) if line_count_row else 0,
            "confirmed_sample_rows": sample_rows,
        }
    finally:
        conn.close()


def _build_my_confirmed_shift_payload(line_user_id: str, user, start_d, end_d, entries=None):
    start_ymd = to_ymd(start_d)
    end_ymd = to_ymd(end_d)
    today_ymd = to_ymd(datetime.now().date())
    entries = entries or {}

    confirmed_columns = _get_table_columns("confirmed_shifts")
    debug_payload = None
    if API_DEBUG_MODE:
        debug_payload = {
            "line_user_id": line_user_id,
            "user_id": int(user["id"]) if user else None,
            "start": start_ymd,
            "end": end_ymd,
            "range_count": 0,
            "all_count": 0,
            "table": "confirmed_shifts",
            "sql": "",
            "params": [],
            "columns": confirmed_columns,
            "raw_rows": [],
            "all_sql": "",
            "all_params": [],
            "all_raw_rows_sample": [],
            "upcoming_base": today_ymd,
        }
        debug_payload.update(_build_confirmed_debug_details(line_user_id, user, confirmed_columns))

    days = []
    for i in range((end_d - start_d).days + 1):
        d = start_d + timedelta(days=i)
        days.append({
            "date": to_ymd(d),
            "weekday": _weekday_jp(d),
            "status": "none",
        })

    if not user:
        payload = {
            "ok": True,
            "week_start": start_ymd,
            "week_end": end_ymd,
            "shifts": days,
            "confirmed_shifts": [],
            "upcoming_shifts": [],
            "next_shift": None,
            "all_shifts": [],
        }
        if API_DEBUG_MODE:
            payload["debug"] = debug_payload
        return payload

    confirmed_query = _get_my_confirmed_decisions(int(user["id"]), start_ymd, end_ymd)
    confirmed_all_query = _get_my_confirmed_decisions_all(int(user["id"]))
    decisions = {r["date"]: r for r in confirmed_query["rows"]}

    if API_DEBUG_MODE and debug_payload is not None:
        debug_payload.update({
            "sql": confirmed_query["sql"],
            "params": confirmed_query["params"],
            "columns": confirmed_query["columns"],
            "range_count": confirmed_query["count"],
            "count": confirmed_query["count"],
            "raw_rows": confirmed_query["rows"],
            "all_sql": confirmed_all_query["sql"],
            "all_params": confirmed_all_query["params"],
            "all_count": confirmed_all_query["count"],
            "all_raw_rows_sample": confirmed_all_query["rows"][:5],
        })

    all_shifts = [
        _confirmed_decision_to_item(decision)
        for decision in confirmed_all_query["rows"]
        if _is_confirmed_decision(decision)
    ]
    upcoming_shifts = [
        item
        for item in all_shifts
        if item.get("date") and item["date"] >= today_ymd
    ]
    next_shift = dict(upcoming_shifts[0]) if upcoming_shifts else None

    shifts = []
    confirmed_shifts = []
    for day in days:
        date_str = day["date"]
        item = dict(day)
        decision = decisions.get(date_str)
        entry = entries.get(date_str)

        if _is_confirmed_decision(decision):
            item.update(_confirmed_decision_to_item(decision))
            confirmed_shifts.append(dict(item))
        elif decision and int(decision.get("is_assigned") or 0) == 0:
            item["status"] = "none"
        elif entry and int(entry["off"]) == 1:
            item["status"] = "off"
        elif entry:
            item["status"] = "pending"

        shifts.append(item)

    payload = {
        "ok": True,
        "week_start": start_ymd,
        "week_end": end_ymd,
        "shifts": shifts,
        "confirmed_shifts": confirmed_shifts,
        "upcoming_shifts": upcoming_shifts,
        "next_shift": next_shift,
        "all_shifts": all_shifts,
    }
    if API_DEBUG_MODE:
        payload["debug"] = debug_payload
    return payload


def _is_user_shift_confirmed(user_id: int, date_str: str) -> bool:
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT 1
            FROM confirmed_shifts
            WHERE user_id = ?
              AND date = ?
              AND is_assigned = 1
              AND COALESCE(NULLIF(start_time, ''), '') <> ''
              AND COALESCE(NULLIF(end_time, ''), '') <> ''
            LIMIT 1
        """, (user_id, date_str))
        return c.fetchone() is not None
    finally:
        conn.close()


def _reject_if_user_shift_confirmed(user, date_str: str):
    if user and _is_user_shift_confirmed(int(user["id"]), date_str):
        return jsonify({"error": CONFIRMED_SHIFT_LOCK_MESSAGE}), 403
    return None


def _api_debug(message, **extra):
    if not API_DEBUG_MODE:
        return
    try:
        print(f"[my_confirmed_shifts] {message} {extra}", flush=True)
    except Exception:
        pass


@api_bp.route("/api/my_confirmed_shifts", methods=["GET"])
def api_my_confirmed_shifts():
    line_user_id = (request.headers.get("X-Line-User-Id") or "").strip()
    _api_debug("request_received", line_user_id=line_user_id, start=request.args.get("start"), end=request.args.get("end"))
    if not line_user_id:
        return jsonify({"error": "LINEユーザーIDが取得できませんでした"}), 401
    id_token = (request.headers.get("X-Line-Id-Token") or "").strip()
    if not id_token:
        return jsonify({"error": "id_token が必要です"}), 401
    try:
        claims = verify_line_id_token(id_token)
    except RuntimeError:
        return jsonify({"error": "LINE認証のサーバー設定が不足しています"}), 500
    except ValueError:
        return jsonify({"error": "LINE認証に失敗しました"}), 401
    if (claims.get("sub") or "").strip() != line_user_id:
        _api_debug("line_user_id_mismatch", header=line_user_id, token_sub=(claims.get("sub") or "").strip())
        return jsonify({"error": "LINE認証に失敗しました"}), 401

    start = (request.args.get("start") or "").strip()
    end = (request.args.get("end") or "").strip()
    start_d = parse_ymd(start)
    end_d = parse_ymd(end)
    if not start_d or not end_d or end_d < start_d:
        return jsonify({"error": "start / end が不正です"}), 400

    user = get_user_by_line_id(line_user_id)
    _api_debug(
        "user_lookup",
        found=bool(user),
        user_id=(int(user["id"]) if user else None),
        line_user_id=line_user_id,
    )
    inactive_response = reject_if_user_inactive(user)
    if inactive_response:
        return inactive_response

    entries = {
        r["date"]: r
        for r in get_my_entries_range(user["id"], to_ymd(start_d), to_ymd(end_d))
    } if user else {}
    payload = _build_my_confirmed_shift_payload(line_user_id, user, start_d, end_d, entries)
    _api_debug(
        "response_ready",
        user_id=(int(user["id"]) if user else None),
        confirmed_response_count=len(payload["confirmed_shifts"]),
        upcoming_count=len(payload["upcoming_shifts"]),
        next_shift_date=(payload["next_shift"] or {}).get("date"),
    )
    return jsonify(payload)


@api_bp.route("/api/my_week", methods=["POST"])
def api_my_week():
    claims, data, error_response = get_verified_line_user_for_api()
    if error_response:
        return error_response
    line_user_id = (claims.get("sub") or "").strip()
    start = (data.get("start") or "").strip()
    start_d = parse_ymd(start)
    if not start_d:
        return jsonify({"error": "start が不正です"}), 400

    user = get_user_by_line_id(line_user_id)
    inactive_response = reject_if_user_inactive(user)
    if inactive_response:
        return inactive_response
    if not user:
        upsert_user(line_user_id, (claims.get("name") or "未設定").strip() or "未設定")
        user = get_user_by_line_id(line_user_id)
    elif not (user["name"] or "").strip():
        upsert_user(line_user_id, (claims.get("name") or "未設定").strip() or "未設定")
        user = get_user_by_line_id(line_user_id)

    end_d = start_d + timedelta(days=6)
    rows = get_my_entries_range(user["id"], to_ymd(start_d), to_ymd(end_d))

    entries = {}
    deadline_statuses = {}
    active_deadline_config = get_active_deadline_config()
    for i in range(7):
        d = start_d + timedelta(days=i)
        entries[to_ymd(d)] = None
        deadline_statuses[to_ymd(d)] = build_deadline_status_payload(d, active_config=active_deadline_config)

    for r in rows:
        entries[r["date"]] = {
            "off": int(r["off"]) == 1,
            "start_time": r["start_time"],
            "end_time": r["end_time"],
            "updated_at": r["updated_at"],
        }

    confirmed_payload = _build_my_confirmed_shift_payload(line_user_id, user, start_d, end_d, entries)
    return jsonify({
        **confirmed_payload,
        "entries": entries,
        "deadline_statuses": deadline_statuses,
    })


@api_bp.route("/api/my_pay_settings", methods=["GET", "POST"])
def api_my_pay_settings():
    user, claims, error_response = _get_verified_user_from_headers()
    if error_response:
        response, status = error_response
        data = response.get_json(silent=True) or {}
        return jsonify({"ok": False, "error": data.get("error") or "LINE認証に失敗しました"}), status
    _ensure_user_pay_settings_table()
    user_id = int(user["id"])
    received_line_user_id = (request.headers.get("X-Line-User-Id") or "").strip()

    if request.method == "GET":
        saved_row = _get_pay_settings_row(user_id)
        settings = _pay_settings_to_dict(saved_row, user_id)
        payload = {
            "ok": True,
            "settings": settings,
            **settings,
        }
        if API_DEBUG_MODE:
            payload["debug"] = _pay_settings_debug(received_line_user_id, user, saved_row)
        return jsonify(payload)

    data = request.get_json(silent=True) or {}
    try:
        hourly_wage = int(data.get("hourly_wage"))
    except Exception:
        return jsonify({"ok": False, "error": "基本時給は正の整数で入力してください"}), 400
    if hourly_wage <= 0:
        return jsonify({"ok": False, "error": "基本時給は正の整数で入力してください"}), 400

    break_rule = _normalize_break_rule((data.get("break_rule") or "legal_jp").strip())
    if break_rule not in ("none", "legal_jp"):
        return jsonify({"ok": False, "error": "休憩ルールが不正です"}), 400

    night_enabled = 1 if _to_bool_flag(data.get("night_enabled")) else 0
    overtime_enabled = 1 if _to_bool_flag(data.get("overtime_enabled")) else 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO user_pay_settings(user_id, hourly_wage, break_rule, night_enabled, overtime_enabled, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
              hourly_wage=excluded.hourly_wage,
              break_rule=excluded.break_rule,
              night_enabled=excluded.night_enabled,
              overtime_enabled=excluded.overtime_enabled,
              updated_at=excluded.updated_at
        """, (user_id, hourly_wage, break_rule, night_enabled, overtime_enabled, now, now))
        conn.commit()
    finally:
        conn.close()

    saved_row = _get_pay_settings_row(user_id)
    settings = _pay_settings_to_dict(saved_row, user_id)
    payload = {
        "ok": True,
        "settings": settings,
        **settings,
    }
    if API_DEBUG_MODE:
        payload["debug"] = _pay_settings_debug(received_line_user_id, user, saved_row)
    return jsonify(payload)


@api_bp.route("/api/my_pay_summary", methods=["GET"])
def api_my_pay_summary():
    user, claims, error_response = _get_verified_user_from_headers()
    if error_response:
        return error_response
    received_line_user_id = (request.headers.get("X-Line-User-Id") or "").strip()
    month = (request.args.get("month") or datetime.now().strftime("%Y-%m")).strip()
    month_start, month_end = _month_bounds(month)
    if not month_start or not month_end:
        return jsonify({"error": "month は YYYY-MM 形式で指定してください"}), 400

    settings_found = _pay_settings_found(int(user["id"]))
    settings = _get_pay_settings(int(user["id"]))
    conn = get_conn()
    try:
        c = conn.cursor()
        rows = [
            _row_to_dict(row)
            for row in c.execute("""
                SELECT id, user_id, date, start_time, end_time
                FROM confirmed_shifts
                WHERE user_id = ?
                  AND date >= ?
                  AND date <= ?
                  AND is_assigned = 1
                  AND COALESCE(NULLIF(start_time, ''), '') <> ''
                  AND COALESCE(NULLIF(end_time, ''), '') <> ''
                ORDER BY date
            """, (int(user["id"]), to_ymd(month_start), to_ymd(month_end))).fetchall()
        ]
    finally:
        conn.close()

    total_scheduled_minutes = 0
    break_minutes = 0
    paid_work_minutes = 0
    overtime_minutes = 0
    night_minutes = 0
    for row in rows:
        calculated = _calculate_shift_pay_minutes(row, settings)
        if not calculated:
            continue
        total_scheduled_minutes += calculated["scheduled_minutes"]
        break_minutes += calculated["break_minutes"]
        paid_work_minutes += calculated["paid_minutes"]
        overtime_minutes += calculated["overtime_minutes"]
        night_minutes += calculated["night_minutes"]

    normal_minutes = max(0, paid_work_minutes - overtime_minutes)
    hourly_wage = settings["hourly_wage"]
    estimated_pay = None
    if hourly_wage:
        base_pay = paid_work_minutes * hourly_wage / 60
        overtime_premium = overtime_minutes * hourly_wage * 0.25 / 60
        night_premium = night_minutes * hourly_wage * 0.25 / 60
        estimated_pay = int(round(base_pay + overtime_premium + night_premium))

    payload = {
        "ok": True,
        "month": month,
        "hourly_wage": hourly_wage,
        "confirmed_shift_count": len(rows),
        "total_scheduled_minutes": total_scheduled_minutes,
        "break_minutes": break_minutes,
        "paid_work_minutes": paid_work_minutes,
        "normal_minutes": normal_minutes,
        "overtime_minutes": overtime_minutes,
        "night_minutes": night_minutes,
        "estimated_pay": estimated_pay,
        "settings": {
            "break_rule": settings["break_rule"],
            "night_enabled": settings["night_enabled"],
            "overtime_enabled": settings["overtime_enabled"],
        },
    }
    if API_DEBUG_MODE:
        payload["debug"] = {
            "received_line_user_id": received_line_user_id,
            "resolved_user_id": int(user["id"]),
            "month": month,
            "month_start": to_ymd(month_start),
            "month_end": to_ymd(month_end),
            "confirmed_shift_count": len(rows),
            "sample_confirmed_rows": rows[:5],
            "hourly_wage": hourly_wage,
            "settings_found": settings_found,
        }
    return jsonify(payload)


@api_bp.route("/api/save_day", methods=["POST"])
def api_save_day():
    claims, data, error_response = get_verified_line_user_for_api()
    if error_response:
        return error_response
    line_user_id = (claims.get("sub") or "").strip()
    date_str = (data.get("date") or "").strip()
    off = bool(data.get("off"))
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    name = ((data.get("name") or claims.get("name") or "未設定").strip() or "未設定")

    shift_date_obj = parse_ymd(date_str)
    if not shift_date_obj:
        return jsonify({"error": "date が不正です"}), 400
    if shift_date_obj < datetime.now().date():
        return jsonify({
            "ok": False,
            "error": "過去日は変更できません"
        }), 403

    user = get_user_by_line_id(line_user_id)
    inactive_response = reject_if_user_inactive(user)
    if inactive_response:
        return inactive_response

    confirmed_lock_response = _reject_if_user_shift_confirmed(user, date_str)
    if confirmed_lock_response:
        return confirmed_lock_response

    closed_response = reject_if_submission_closed_for_date(date_str)
    if closed_response:
        return closed_response

    if not user:
        upsert_user(line_user_id, name)
        user = get_user_by_line_id(line_user_id)
    elif not (user["name"] or "").strip():
        upsert_user(line_user_id, name)
        user = get_user_by_line_id(line_user_id)

    if off:
        upsert_shift_entry(user["id"], date_str, 1, None, None)
    else:
        if not (is_valid_time_hhmm(start_time or "") and is_valid_time_hhmm(end_time or "")):
            return jsonify({"error": "時間形式が不正です（HH:MM）"}), 400
        if hhmm_to_minutes(end_time) <= hhmm_to_minutes(start_time):
            return jsonify({"error": "終了は開始より後にしてください"}), 400
        upsert_shift_entry(user["id"], date_str, 0, start_time, end_time)

    rows = get_my_entries_range(user["id"], date_str, date_str)
    r = rows[0] if rows else None
    entry = None
    if r:
        entry = {
            "off": int(r["off"]) == 1,
            "start_time": r["start_time"],
            "end_time": r["end_time"],
            "updated_at": r["updated_at"],
        }

    return jsonify({
        "ok": True,
        "entry": entry,
        "deadline_status": build_deadline_status_payload(shift_date_obj) if shift_date_obj else None
    })

@api_bp.route("/api/delete_day", methods=["POST"])
def api_delete_day():
    claims, data, error_response = get_verified_line_user_for_api()
    if error_response:
        return error_response
    line_user_id = (claims.get("sub") or "").strip()
    date_str = (data.get("date") or "").strip()
    shift_date_obj = parse_ymd(date_str)
    if not shift_date_obj:
        return jsonify({"error": "date が不正です"}), 400
    if shift_date_obj < datetime.now().date():
        return jsonify({
            "ok": False,
            "error": "過去日は変更できません"
        }), 403

    user = get_user_by_line_id(line_user_id)
    inactive_response = reject_if_user_inactive(user)
    if inactive_response:
        return inactive_response

    confirmed_lock_response = _reject_if_user_shift_confirmed(user, date_str)
    if confirmed_lock_response:
        return confirmed_lock_response

    closed_response = reject_if_submission_closed_for_date(date_str)
    if closed_response:
        return closed_response

    if not user:
        return jsonify({
            "ok": True,
            "deleted": 0,
            "deadline_status": build_deadline_status_payload(shift_date_obj) if shift_date_obj else None
        })

    deleted = delete_entry(user["id"], date_str)
    return jsonify({
        "ok": True,
        "deleted": deleted,
        "deadline_status": build_deadline_status_payload(shift_date_obj) if shift_date_obj else None
    })

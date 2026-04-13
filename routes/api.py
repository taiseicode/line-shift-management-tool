from datetime import timedelta

from flask import Blueprint, jsonify

from repositories.shift_repository import get_my_entries_range, upsert_shift_entry, delete_entry
from repositories.user_repository import get_user_by_line_id, upsert_user
from services.auth_service import require_verified_line_claims, reject_if_user_inactive
from services.deadline_service import build_deadline_status_payload, reject_if_submission_closed_for_date
from utils import parse_ymd, to_ymd, is_valid_time_hhmm, hhmm_to_minutes


api_bp = Blueprint("api", __name__)


def get_verified_line_user_for_api():
    claims, data, error_response = require_verified_line_claims()
    if error_response:
        return None, data, error_response
    line_user_id = (claims.get("sub") or "").strip()
    if not line_user_id:
        return None, data, (jsonify({"error": "LINE認証に失敗しました"}), 401)
    return claims, data, None

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
    for i in range(7):
        d = start_d + timedelta(days=i)
        entries[to_ymd(d)] = None
        deadline_statuses[to_ymd(d)] = build_deadline_status_payload(d)

    for r in rows:
        entries[r["date"]] = {
            "off": int(r["off"]) == 1,
            "start_time": r["start_time"],
            "end_time": r["end_time"],
            "updated_at": r["updated_at"],
        }

    return jsonify({"entries": entries, "deadline_statuses": deadline_statuses})

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

    if not parse_ymd(date_str):
        return jsonify({"error": "date が不正です"}), 400

    closed_response = reject_if_submission_closed_for_date(date_str)
    if closed_response:
        return closed_response

    user = get_user_by_line_id(line_user_id)
    if not user:
        upsert_user(line_user_id, name)
        user = get_user_by_line_id(line_user_id)
    elif not (user["name"] or "").strip():
        upsert_user(line_user_id, name)
        user = get_user_by_line_id(line_user_id)
    inactive_response = reject_if_user_inactive(user)
    if inactive_response:
        return inactive_response

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
    shift_date_obj = parse_ymd(date_str)

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
    if not parse_ymd(date_str):
        return jsonify({"error": "date が不正です"}), 400

    closed_response = reject_if_submission_closed_for_date(date_str)
    if closed_response:
        return closed_response

    user = get_user_by_line_id(line_user_id)
    inactive_response = reject_if_user_inactive(user)
    if inactive_response:
        return inactive_response
    if not user:
        shift_date_obj = parse_ymd(date_str)
        return jsonify({
            "ok": True,
            "deleted": 0,
            "deadline_status": build_deadline_status_payload(shift_date_obj) if shift_date_obj else None
        })

    deleted = delete_entry(user["id"], date_str)
    shift_date_obj = parse_ymd(date_str)
    return jsonify({
        "ok": True,
        "deleted": deleted,
        "deadline_status": build_deadline_status_payload(shift_date_obj) if shift_date_obj else None
    })

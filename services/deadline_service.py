from datetime import datetime, timedelta, date

from flask import jsonify

from config import (
    SUBMISSION_DEADLINE_SETTING_KEY,
    DEADLINE_MODE_SETTING_KEY,
    DEADLINE_DAYS_BEFORE_SETTING_KEY,
    DEADLINE_TIME_SETTING_KEY,
)
from repositories.settings_repository import get_setting, upsert_setting, delete_setting
from utils import (
    parse_submission_deadline,
    parse_int_or_none,
    is_valid_time_hhmm,
    to_ymd,
    format_submission_deadline,
    format_relative_deadline,
    parse_ymd,
)


def get_submission_deadline():
    raw_value = get_setting(SUBMISSION_DEADLINE_SETTING_KEY) or ""
    return parse_submission_deadline(raw_value)

def set_submission_deadline(deadline):
    if deadline is None:
        delete_setting(SUBMISSION_DEADLINE_SETTING_KEY)
        return
    upsert_setting(
        SUBMISSION_DEADLINE_SETTING_KEY,
        deadline.strftime("%Y-%m-%d %H:%M:%S")
    )

def get_deadline_mode():
    return (get_setting(DEADLINE_MODE_SETTING_KEY) or "").strip()

def set_deadline_mode(mode: str):
    normalized = (mode or "").strip()
    if not normalized:
        delete_setting(DEADLINE_MODE_SETTING_KEY)
        return
    upsert_setting(DEADLINE_MODE_SETTING_KEY, normalized)

def get_deadline_days_before():
    return parse_int_or_none(get_setting(DEADLINE_DAYS_BEFORE_SETTING_KEY))

def set_deadline_days_before(days_before):
    if days_before is None:
        delete_setting(DEADLINE_DAYS_BEFORE_SETTING_KEY)
        return
    upsert_setting(DEADLINE_DAYS_BEFORE_SETTING_KEY, str(int(days_before)))

def get_deadline_time():
    value = (get_setting(DEADLINE_TIME_SETTING_KEY) or "").strip()
    return value if is_valid_time_hhmm(value) else None

def set_deadline_time(hhmm):
    value = (hhmm or "").strip()
    if not value:
        delete_setting(DEADLINE_TIME_SETTING_KEY)
        return
    upsert_setting(DEADLINE_TIME_SETTING_KEY, value)

def get_relative_deadline_settings():
    return {
        "days_before": get_deadline_days_before(),
        "time": get_deadline_time(),
    }

def build_relative_deadline(shift_date_obj: date, days_before: int, hhmm: str):
    if shift_date_obj is None or days_before is None or days_before < 0 or not is_valid_time_hhmm(hhmm or ""):
        return None
    base_date = shift_date_obj - timedelta(days=days_before)
    return datetime.strptime(f"{to_ymd(base_date)} {hhmm}", "%Y-%m-%d %H:%M")

def get_active_deadline_config():
    fixed_deadline = get_submission_deadline()
    relative_settings = get_relative_deadline_settings()
    relative_valid = (
        relative_settings["days_before"] is not None and
        relative_settings["days_before"] >= 0 and
        is_valid_time_hhmm(relative_settings["time"] or "")
    )
    mode = get_deadline_mode()

    if mode == "fixed":
        return {
            "mode": "fixed",
            "fixed_deadline": fixed_deadline,
            "relative_days_before": relative_settings["days_before"],
            "relative_time": relative_settings["time"],
            "is_configured": fixed_deadline is not None,
            "display": format_submission_deadline(fixed_deadline),
        }
    if mode == "relative":
        return {
            "mode": "relative",
            "fixed_deadline": fixed_deadline,
            "relative_days_before": relative_settings["days_before"],
            "relative_time": relative_settings["time"],
            "is_configured": relative_valid,
            "display": format_relative_deadline(relative_settings["days_before"], relative_settings["time"]),
        }
    if fixed_deadline is not None:
        return {
            "mode": "fixed",
            "fixed_deadline": fixed_deadline,
            "relative_days_before": relative_settings["days_before"],
            "relative_time": relative_settings["time"],
            "is_configured": True,
            "display": format_submission_deadline(fixed_deadline),
        }
    if relative_valid:
        return {
            "mode": "relative",
            "fixed_deadline": fixed_deadline,
            "relative_days_before": relative_settings["days_before"],
            "relative_time": relative_settings["time"],
            "is_configured": True,
            "display": format_relative_deadline(relative_settings["days_before"], relative_settings["time"]),
        }
    return {
        "mode": "",
        "fixed_deadline": fixed_deadline,
        "relative_days_before": relative_settings["days_before"],
        "relative_time": relative_settings["time"],
        "is_configured": False,
        "display": "未設定",
    }

def get_submission_deadline_status(shift_date_obj=None, now=None):
    active_config = get_active_deadline_config()
    current = now or datetime.now()
    mode = active_config["mode"]
    deadline = None
    label = ""

    if mode == "fixed":
        deadline = active_config["fixed_deadline"]
        label = format_submission_deadline(deadline)
    elif mode == "relative" and shift_date_obj is not None:
        deadline = build_relative_deadline(
            shift_date_obj,
            active_config["relative_days_before"],
            active_config["relative_time"],
        )
        label = format_submission_deadline(deadline)

    is_closed = bool(deadline and current > deadline)
    message = f"提出期限を過ぎています（期限: {label}）" if is_closed and deadline else ""

    return {
        "mode": mode,
        "deadline": deadline,
        "is_closed": is_closed,
        "message": message,
        "display": label if deadline else active_config["display"],
        "is_configured": active_config["is_configured"],
        "relative_days_before": active_config["relative_days_before"],
        "relative_time": active_config["relative_time"],
    }

def build_deadline_status_payload(shift_date_obj: date):
    status = get_submission_deadline_status(shift_date_obj=shift_date_obj)
    return {
        "is_closed": status["is_closed"],
        "message": status["message"],
        "deadline_display": format_submission_deadline(status["deadline"]) if status["deadline"] else "",
        "mode": status["mode"],
        "is_configured": status["is_configured"],
    }

def reject_if_submission_closed_for_date(date_str: str):
    shift_date_obj = parse_ymd(date_str)
    if not shift_date_obj:
        return None
    deadline_status = get_submission_deadline_status(shift_date_obj=shift_date_obj)
    if deadline_status["is_closed"]:
        return jsonify({"error": deadline_status["message"]}), 403
    return None

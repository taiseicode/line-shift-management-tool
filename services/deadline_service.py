import calendar
from datetime import datetime, timedelta, date

from flask import jsonify

from config import (
    SUBMISSION_DEADLINE_SETTING_KEY,
    DEADLINE_MODE_SETTING_KEY,
    DEADLINE_DAYS_BEFORE_SETTING_KEY,
    DEADLINE_TIME_SETTING_KEY,
)
from repositories.settings_repository import get_setting, get_settings, upsert_setting, delete_setting
from utils import (
    parse_submission_deadline,
    parse_int_or_none,
    is_valid_time_hhmm,
    to_ymd,
    format_submission_deadline,
    format_relative_deadline,
    parse_ymd,
    now_jst,
)


MONTHLY_DEADLINE_DAY_KEY = "MONTHLY_DEADLINE_DAY"
MONTHLY_TARGET_KEY = "MONTHLY_TARGET"
MONTHLY_DEADLINE_TIME_KEY = "MONTHLY_DEADLINE_TIME"
MONTHLY_TARGET_CURRENT = "current_month"
MONTHLY_TARGET_NEXT = "next_month"
DEADLINE_SETTING_KEYS = (
    SUBMISSION_DEADLINE_SETTING_KEY,
    DEADLINE_MODE_SETTING_KEY,
    DEADLINE_DAYS_BEFORE_SETTING_KEY,
    DEADLINE_TIME_SETTING_KEY,
    MONTHLY_DEADLINE_DAY_KEY,
    MONTHLY_TARGET_KEY,
    MONTHLY_DEADLINE_TIME_KEY,
)


def get_deadline_settings_values():
    return get_settings(DEADLINE_SETTING_KEYS)


def _read_setting(settings_values, key: str):
    if settings_values is None:
        return get_setting(key)
    return settings_values.get(key)


def get_submission_deadline(settings_values=None):
    raw_value = _read_setting(settings_values, SUBMISSION_DEADLINE_SETTING_KEY) or ""
    return parse_submission_deadline(raw_value)

def set_submission_deadline(deadline):
    if deadline is None:
        delete_setting(SUBMISSION_DEADLINE_SETTING_KEY)
        return
    upsert_setting(
        SUBMISSION_DEADLINE_SETTING_KEY,
        deadline.strftime("%Y-%m-%d %H:%M:%S")
    )

def get_deadline_mode(settings_values=None):
    return (_read_setting(settings_values, DEADLINE_MODE_SETTING_KEY) or "").strip()

def set_deadline_mode(mode: str):
    normalized = (mode or "").strip()
    if not normalized:
        upsert_setting(DEADLINE_MODE_SETTING_KEY, "none")
        return
    upsert_setting(DEADLINE_MODE_SETTING_KEY, normalized)

def get_deadline_days_before(settings_values=None):
    return parse_int_or_none(_read_setting(settings_values, DEADLINE_DAYS_BEFORE_SETTING_KEY))

def set_deadline_days_before(days_before):
    if days_before is None:
        delete_setting(DEADLINE_DAYS_BEFORE_SETTING_KEY)
        return
    upsert_setting(DEADLINE_DAYS_BEFORE_SETTING_KEY, str(int(days_before)))

def get_deadline_time(settings_values=None):
    value = (_read_setting(settings_values, DEADLINE_TIME_SETTING_KEY) or "").strip()
    return value if is_valid_time_hhmm(value) else None

def set_deadline_time(hhmm):
    value = (hhmm or "").strip()
    if not value:
        delete_setting(DEADLINE_TIME_SETTING_KEY)
        return
    upsert_setting(DEADLINE_TIME_SETTING_KEY, value)

def get_relative_deadline_settings(settings_values=None):
    return {
        "days_before": get_deadline_days_before(settings_values),
        "time": get_deadline_time(settings_values),
    }

def get_monthly_deadline_day(settings_values=None):
    return parse_int_or_none(_read_setting(settings_values, MONTHLY_DEADLINE_DAY_KEY))

def set_monthly_deadline_day(day):
    if day is None:
        delete_setting(MONTHLY_DEADLINE_DAY_KEY)
        return
    upsert_setting(MONTHLY_DEADLINE_DAY_KEY, str(int(day)))

def get_monthly_target(settings_values=None):
    value = (_read_setting(settings_values, MONTHLY_TARGET_KEY) or MONTHLY_TARGET_NEXT).strip()
    return value if value in (MONTHLY_TARGET_CURRENT, MONTHLY_TARGET_NEXT) else MONTHLY_TARGET_NEXT

def set_monthly_target(target: str):
    value = (target or MONTHLY_TARGET_NEXT).strip()
    if value not in (MONTHLY_TARGET_CURRENT, MONTHLY_TARGET_NEXT):
        value = MONTHLY_TARGET_NEXT
    upsert_setting(MONTHLY_TARGET_KEY, value)

def get_monthly_deadline_time(settings_values=None):
    value = (_read_setting(settings_values, MONTHLY_DEADLINE_TIME_KEY) or "").strip()
    return value if is_valid_time_hhmm(value) else None

def set_monthly_deadline_time(hhmm):
    value = (hhmm or "").strip()
    if not value:
        delete_setting(MONTHLY_DEADLINE_TIME_KEY)
        return
    upsert_setting(MONTHLY_DEADLINE_TIME_KEY, value)

def get_monthly_deadline_settings(settings_values=None):
    return {
        "day": get_monthly_deadline_day(settings_values),
        "target": get_monthly_target(settings_values),
        "time": get_monthly_deadline_time(settings_values),
    }

def _add_months(year: int, month: int, offset: int):
    month_index = (year * 12 + (month - 1)) + offset
    return month_index // 12, month_index % 12 + 1

def _month_range(year: int, month: int):
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)

def _clamp_day(year: int, month: int, day: int) -> int:
    return min(int(day), calendar.monthrange(year, month)[1])

def build_monthly_fixed_deadline(shift_date_obj: date, deadline_day: int, target: str, hhmm: str):
    if (
        shift_date_obj is None or
        deadline_day is None or
        deadline_day < 1 or
        deadline_day > 31 or
        target not in (MONTHLY_TARGET_CURRENT, MONTHLY_TARGET_NEXT) or
        not is_valid_time_hhmm(hhmm or "")
    ):
        return None

    offset = 0 if target == MONTHLY_TARGET_CURRENT else -1
    deadline_year, deadline_month = _add_months(shift_date_obj.year, shift_date_obj.month, offset)
    deadline_date = date(
        deadline_year,
        deadline_month,
        _clamp_day(deadline_year, deadline_month, deadline_day),
    )
    return datetime.strptime(f"{to_ymd(deadline_date)} {hhmm}", "%Y-%m-%d %H:%M")

def format_monthly_target(target: str) -> str:
    return "当月シフト" if target == MONTHLY_TARGET_CURRENT else "翌月シフト"

def format_monthly_deadline(day, target, hhmm):
    if day is None or not is_valid_time_hhmm(hhmm or ""):
        return "未設定"
    return f"毎月{int(day)}日 {hhmm} までに{format_monthly_target(target)}を提出"

def format_monthly_acceptance_text(shift_date_obj: date, deadline):
    if not shift_date_obj or not deadline:
        return ""
    start_d, end_d = _month_range(shift_date_obj.year, shift_date_obj.month)
    return (
        f"現在提出受付中：{start_d.year}年{start_d.month}月{start_d.day}日〜"
        f"{end_d.year}年{end_d.month}月{end_d.day}日\n"
        f"締切：{deadline.year}年{deadline.month}月{deadline.day}日 {deadline.strftime('%H:%M')}"
    )

def build_relative_deadline(shift_date_obj: date, days_before: int, hhmm: str):
    if shift_date_obj is None or days_before is None or days_before < 0 or not is_valid_time_hhmm(hhmm or ""):
        return None
    base_date = shift_date_obj - timedelta(days=days_before)
    return datetime.strptime(f"{to_ymd(base_date)} {hhmm}", "%Y-%m-%d %H:%M")

def get_active_deadline_config(settings_values=None):
    fixed_deadline = get_submission_deadline(settings_values)
    relative_settings = get_relative_deadline_settings(settings_values)
    monthly_settings = get_monthly_deadline_settings(settings_values)
    relative_valid = (
        relative_settings["days_before"] is not None and
        relative_settings["days_before"] >= 0 and
        is_valid_time_hhmm(relative_settings["time"] or "")
    )
    monthly_valid = (
        monthly_settings["day"] is not None and
        1 <= monthly_settings["day"] <= 31 and
        monthly_settings["target"] in (MONTHLY_TARGET_CURRENT, MONTHLY_TARGET_NEXT) and
        is_valid_time_hhmm(monthly_settings["time"] or "")
    )
    mode = get_deadline_mode(settings_values)
    base = {
        "monthly_day": monthly_settings["day"],
        "monthly_target": monthly_settings["target"],
        "monthly_time": monthly_settings["time"],
    }

    if mode in ("none", "unset"):
        return {
            **base,
            "mode": "",
            "fixed_deadline": fixed_deadline,
            "relative_days_before": relative_settings["days_before"],
            "relative_time": relative_settings["time"],
            "is_configured": False,
            "display": "未設定",
        }
    if mode == "fixed":
        return {
            **base,
            "mode": "fixed",
            "fixed_deadline": fixed_deadline,
            "relative_days_before": relative_settings["days_before"],
            "relative_time": relative_settings["time"],
            "is_configured": fixed_deadline is not None,
            "display": format_submission_deadline(fixed_deadline),
        }
    if mode == "relative":
        return {
            **base,
            "mode": "relative",
            "fixed_deadline": fixed_deadline,
            "relative_days_before": relative_settings["days_before"],
            "relative_time": relative_settings["time"],
            "is_configured": relative_valid,
            "display": format_relative_deadline(relative_settings["days_before"], relative_settings["time"]),
        }
    if mode == "monthly_fixed":
        return {
            **base,
            "mode": "monthly_fixed",
            "fixed_deadline": fixed_deadline,
            "relative_days_before": relative_settings["days_before"],
            "relative_time": relative_settings["time"],
            "is_configured": monthly_valid,
            "display": format_monthly_deadline(
                monthly_settings["day"],
                monthly_settings["target"],
                monthly_settings["time"],
            ),
        }
    if fixed_deadline is not None:
        return {
            **base,
            "mode": "fixed",
            "fixed_deadline": fixed_deadline,
            "relative_days_before": relative_settings["days_before"],
            "relative_time": relative_settings["time"],
            "is_configured": True,
            "display": format_submission_deadline(fixed_deadline),
        }
    if relative_valid:
        return {
            **base,
            "mode": "relative",
            "fixed_deadline": fixed_deadline,
            "relative_days_before": relative_settings["days_before"],
            "relative_time": relative_settings["time"],
            "is_configured": True,
            "display": format_relative_deadline(relative_settings["days_before"], relative_settings["time"]),
        }
    return {
        **base,
        "mode": "",
        "fixed_deadline": fixed_deadline,
        "relative_days_before": relative_settings["days_before"],
        "relative_time": relative_settings["time"],
        "is_configured": False,
        "display": "未設定",
    }

def get_submission_deadline_status(shift_date_obj=None, now=None, active_config=None):
    active_config = active_config or get_active_deadline_config()
    current = now or now_jst()
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
    elif mode == "monthly_fixed" and shift_date_obj is not None:
        deadline = build_monthly_fixed_deadline(
            shift_date_obj,
            active_config["monthly_day"],
            active_config["monthly_target"],
            active_config["monthly_time"],
        )
        label = format_monthly_acceptance_text(shift_date_obj, deadline)

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
        "monthly_day": active_config["monthly_day"],
        "monthly_target": active_config["monthly_target"],
        "monthly_time": active_config["monthly_time"],
    }

def build_deadline_status_payload(shift_date_obj: date, active_config=None):
    status = get_submission_deadline_status(shift_date_obj=shift_date_obj, active_config=active_config)
    return {
        "is_closed": status["is_closed"],
        "message": status["message"],
        "deadline_display": format_submission_deadline(status["deadline"]) if status["deadline"] else "",
        "deadline_detail": status["display"],
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

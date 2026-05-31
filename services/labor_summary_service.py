from datetime import date, datetime, timedelta

from repositories.confirmed_shift_repository import get_confirmed_shifts_range
from repositories.settings_repository import get_setting, upsert_setting


DEFAULT_HOURLY_WAGE = 1210
BASE_HOURLY_WAGE_KEY = "BASE_HOURLY_WAGE"
BREAK_ENABLED_KEY = "BREAK_ENABLED"
OVERTIME_ENABLED_KEY = "OVERTIME_ENABLED"
NIGHT_ENABLED_KEY = "NIGHT_ENABLED"


def _get_bool_setting(key: str, default: bool = True) -> bool:
    raw_value = get_setting(key)
    if raw_value is None:
        return default
    return str(raw_value).strip().lower() == "true"


def _set_bool_setting(key: str, value: bool):
    upsert_setting(key, "true" if value else "false")


def get_labor_settings():
    raw_value = get_setting(BASE_HOURLY_WAGE_KEY)
    if raw_value is None:
        raw_value = get_setting("hourly_wage")

    try:
        base_hourly_wage = int(raw_value) if raw_value is not None else DEFAULT_HOURLY_WAGE
    except Exception:
        base_hourly_wage = DEFAULT_HOURLY_WAGE

    return {
        "base_hourly_wage": base_hourly_wage,
        "break_enabled": _get_bool_setting(BREAK_ENABLED_KEY, True),
        "overtime_enabled": _get_bool_setting(OVERTIME_ENABLED_KEY, True),
        "night_enabled": _get_bool_setting(NIGHT_ENABLED_KEY, True),
    }


def save_labor_settings(base_hourly_wage: int, break_enabled: bool, overtime_enabled: bool, night_enabled: bool):
    upsert_setting(BASE_HOURLY_WAGE_KEY, str(int(base_hourly_wage)))
    # Keep the old key in sync so older screens or scripts still see the latest value.
    upsert_setting("hourly_wage", str(int(base_hourly_wage)))
    _set_bool_setting(BREAK_ENABLED_KEY, break_enabled)
    _set_bool_setting(OVERTIME_ENABLED_KEY, overtime_enabled)
    _set_bool_setting(NIGHT_ENABLED_KEY, night_enabled)


def get_hourly_wage() -> int:
    return get_labor_settings()["base_hourly_wage"]


def set_hourly_wage(value: int):
    settings = get_labor_settings()
    save_labor_settings(
        value,
        settings["break_enabled"],
        settings["overtime_enabled"],
        settings["night_enabled"],
    )


def minutes_to_hours(minutes: int) -> float:
    return round(int(minutes) / 60, 2)


def calculate_wage_from_minutes(minutes: int, hourly_wage: int) -> int:
    return (int(minutes) * int(hourly_wage)) // 60


def _parse_shift_datetimes(target_ymd: str, start_time: str, end_time: str):
    try:
        start_dt = datetime.strptime(f"{target_ymd} {start_time}", "%Y-%m-%d %H:%M")
        end_dt = datetime.strptime(f"{target_ymd} {end_time}", "%Y-%m-%d %H:%M")
    except Exception:
        return None, None
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    return start_dt, end_dt


def _overlap_minutes(start_dt: datetime, end_dt: datetime, window_start: datetime, window_end: datetime) -> int:
    overlap_start = max(start_dt, window_start)
    overlap_end = min(end_dt, window_end)
    if overlap_end <= overlap_start:
        return 0
    return int((overlap_end - overlap_start).total_seconds() // 60)


def _calculate_night_minutes(start_dt: datetime, end_dt: datetime) -> int:
    total = 0
    cursor_day = start_dt.date() - timedelta(days=1)
    last_day = end_dt.date()
    while cursor_day <= last_day:
        total += _overlap_minutes(
            start_dt,
            end_dt,
            datetime.combine(cursor_day, datetime.min.time()).replace(hour=22),
            datetime.combine(cursor_day + timedelta(days=1), datetime.min.time()).replace(hour=5),
        )
        cursor_day += timedelta(days=1)
    return total


def _calculate_break_minutes(gross_minutes: int, break_enabled: bool) -> int:
    if not break_enabled:
        return 0
    if gross_minutes > 8 * 60:
        return 60
    if gross_minutes > 6 * 60:
        return 45
    return 0


def calculate_shift_cost(row, settings):
    hourly_wage = settings["base_hourly_wage"]
    start_time = row["start_time"] or ""
    end_time = row["end_time"] or ""
    start_dt, end_dt = _parse_shift_datetimes(row["date"], start_time, end_time)
    if not start_dt or not end_dt:
        return None

    gross_minutes = max(0, int((end_dt - start_dt).total_seconds() // 60))
    break_minutes = _calculate_break_minutes(gross_minutes, settings["break_enabled"])
    actual_minutes = max(0, gross_minutes - break_minutes)
    overtime_minutes = max(0, actual_minutes - 8 * 60) if settings["overtime_enabled"] else 0
    normal_minutes = max(0, actual_minutes - overtime_minutes)
    night_minutes = _calculate_night_minutes(start_dt, end_dt) if settings["night_enabled"] else 0

    normal_wage = calculate_wage_from_minutes(actual_minutes, hourly_wage)
    overtime_extra_wage = calculate_wage_from_minutes(overtime_minutes, hourly_wage) // 4
    night_extra_wage = calculate_wage_from_minutes(night_minutes, hourly_wage) // 4
    total_wage = normal_wage + overtime_extra_wage + night_extra_wage

    return {
        "date": row["date"],
        "name": row["name"] or "",
        "shift_time": f"{start_time} - {end_time}",
        "gross_minutes": gross_minutes,
        "gross_hours": minutes_to_hours(gross_minutes),
        "break_minutes": break_minutes,
        "break_label": f"{break_minutes}分" if settings["break_enabled"] else "無効",
        "actual_minutes": actual_minutes,
        "actual_hours": minutes_to_hours(actual_minutes),
        "minutes": actual_minutes,
        "hours": minutes_to_hours(actual_minutes),
        "normal_minutes": normal_minutes,
        "normal_hours": minutes_to_hours(normal_minutes),
        "overtime_minutes": overtime_minutes,
        "overtime_hours": minutes_to_hours(overtime_minutes),
        "overtime_label": f"{minutes_to_hours(overtime_minutes):.2f}時間" if settings["overtime_enabled"] else "無効",
        "night_minutes": night_minutes,
        "night_hours": minutes_to_hours(night_minutes),
        "night_label": f"{minutes_to_hours(night_minutes):.2f}時間" if settings["night_enabled"] else "無効",
        "normal_wage": normal_wage,
        "overtime_extra_wage": overtime_extra_wage,
        "night_extra_wage": night_extra_wage,
        "wage": total_wage,
    }


def _summary_base(label_key: str, label_value: str, settings, users):
    total_minutes = sum(user["actual_minutes"] for user in users)
    total_labor_cost = sum(user["wage"] for user in users)
    return {
        label_key: label_value,
        "hourly_wage": settings["base_hourly_wage"],
        "base_hourly_wage": settings["base_hourly_wage"],
        "break_enabled": settings["break_enabled"],
        "overtime_enabled": settings["overtime_enabled"],
        "night_enabled": settings["night_enabled"],
        "total_minutes": total_minutes,
        "total_hours": minutes_to_hours(total_minutes),
        "total_labor_cost": total_labor_cost,
        "users": users,
    }


def build_daily_summary(target_date: date):
    target_ymd = target_date.strftime("%Y-%m-%d")
    rows = get_confirmed_shifts_range(target_ymd, target_ymd)
    return build_daily_summary_from_rows(target_date, rows)


def build_daily_summary_from_rows(target_date: date, rows):
    target_ymd = target_date.strftime("%Y-%m-%d")
    settings = get_labor_settings()
    users = []

    for row in rows:
        item = calculate_shift_cost(row, settings)
        if item:
            users.append(item)

    return _summary_base("date", target_ymd, settings, users)


def build_monthly_summary(start_date: date, end_exclusive_date: date, month_text: str):
    settings = get_labor_settings()
    rows = get_confirmed_shifts_range(
        start_date.strftime("%Y-%m-%d"),
        (end_exclusive_date - timedelta(days=1)).strftime("%Y-%m-%d"),
    )

    totals_by_user = {}
    for row in rows:
        item = calculate_shift_cost(row, settings)
        if not item:
            continue
        user_total = totals_by_user.setdefault(row["name"] or "", {
            "name": row["name"] or "",
            "shift_time": "月合計",
            "gross_minutes": 0,
            "break_minutes": 0,
            "actual_minutes": 0,
            "normal_minutes": 0,
            "overtime_minutes": 0,
            "night_minutes": 0,
            "normal_wage": 0,
            "overtime_extra_wage": 0,
            "night_extra_wage": 0,
            "wage": 0,
        })
        for key in (
            "gross_minutes",
            "break_minutes",
            "actual_minutes",
            "normal_minutes",
            "overtime_minutes",
            "night_minutes",
            "normal_wage",
            "overtime_extra_wage",
            "night_extra_wage",
            "wage",
        ):
            user_total[key] += item[key]

    users = []
    for name in sorted(totals_by_user.keys()):
        item = totals_by_user[name]
        item.update({
            "gross_hours": minutes_to_hours(item["gross_minutes"]),
            "break_label": f"{item['break_minutes']}分" if settings["break_enabled"] else "無効",
            "actual_hours": minutes_to_hours(item["actual_minutes"]),
            "minutes": item["actual_minutes"],
            "hours": minutes_to_hours(item["actual_minutes"]),
            "normal_hours": minutes_to_hours(item["normal_minutes"]),
            "overtime_hours": minutes_to_hours(item["overtime_minutes"]),
            "overtime_label": f"{minutes_to_hours(item['overtime_minutes']):.2f}時間" if settings["overtime_enabled"] else "無効",
            "night_hours": minutes_to_hours(item["night_minutes"]),
            "night_label": f"{minutes_to_hours(item['night_minutes']):.2f}時間" if settings["night_enabled"] else "無効",
        })
        users.append(item)

    return _summary_base("month", month_text, settings, users)

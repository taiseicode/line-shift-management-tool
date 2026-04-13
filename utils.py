import re
from datetime import datetime, timedelta, date


def to_ymd(d: date) -> str:
    return d.strftime("%Y-%m-%d")

def parse_ymd(s: str):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

def parse_submission_deadline(s: str):
    if not s:
        return None
    normalized = s.strip()
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(normalized, fmt)
        except Exception:
            pass
    return None

def parse_int_or_none(value):
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except Exception:
        return None

def to_datetime_local_value(dt):
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%dT%H:%M")

def format_submission_deadline(dt):
    if not dt:
        return "未設定"
    return dt.strftime("%Y-%m-%d %H:%M")

def format_relative_deadline(days_before, hhmm):
    if days_before is None or not is_valid_time_hhmm(hhmm or ""):
        return "未設定"
    return f"各シフト日の{days_before}日前 {hhmm}"

def daterange_inclusive(start_d: date, end_d: date):
    cur = start_d
    while cur <= end_d:
        yield cur
        cur += timedelta(days=1)

def html_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def is_valid_time_hhmm(s: str) -> bool:
    return bool(re.match(r"^\d{2}:\d{2}$", s)) and 0 <= int(s[:2]) <= 23 and 0 <= int(s[3:]) <= 59

def hhmm_to_minutes(s: str) -> int:
    h = int(s[:2])
    m = int(s[3:])
    return h * 60 + m

def get_weekday_jp(d: date) -> str:
    return ["月", "火", "水", "木", "金", "土", "日"][d.weekday()]

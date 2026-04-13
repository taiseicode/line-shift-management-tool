from datetime import date

from db import get_conn
from repositories.required_staff_repository import get_required_staff_range
from repositories.shift_repository import get_entries_range
from utils import daterange_inclusive, to_ymd


def calculate_staff_summary(start_d: date, end_d: date):
    start_ymd = to_ymd(start_d)
    end_ymd = to_ymd(end_d)

    rows = get_entries_range(start_ymd, end_ymd)
    required_map = get_required_staff_range(start_ymd, end_ymd)

    by_date = {}
    for d in daterange_inclusive(start_d, end_d):
        ymd = to_ymd(d)
        by_date[ymd] = {
            "date": ymd,
            "required": int(required_map.get(ymd, 0)),
            "submitted_count": 0,
            "working_count": 0,
            "off_count": 0,
            "not_submitted_count": 0,
            "entries": []
        }

    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) AS cnt FROM users WHERE active=1")
        total_users = int(c.fetchone()["cnt"])
    finally:
        conn.close()

    for r in rows:
        if int(r["active"]) != 1:
            continue
        ymd = r["date"]
        if ymd not in by_date:
            continue
        by_date[ymd]["entries"].append(r)
        by_date[ymd]["submitted_count"] += 1
        if int(r["off"]) == 1:
            by_date[ymd]["off_count"] += 1
        else:
            by_date[ymd]["working_count"] += 1

    for ymd in by_date:
        by_date[ymd]["not_submitted_count"] = max(0, total_users - by_date[ymd]["submitted_count"])
        by_date[ymd]["is_shortage"] = by_date[ymd]["required"] > 0 and by_date[ymd]["working_count"] < by_date[ymd]["required"]
        by_date[ymd]["shortage_count"] = max(0, by_date[ymd]["required"] - by_date[ymd]["working_count"])

    return by_date

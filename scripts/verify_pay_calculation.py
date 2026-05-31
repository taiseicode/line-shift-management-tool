import os
import sys
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("LINE_CHANNEL_SECRET", "dummy")
os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "dummy")

from routes.api import _calculate_shift_pay_minutes  # noqa: E402


BASE_SETTINGS = {
    "hourly_wage": 1200,
    "break_rule": "legal_jp",
    "night_enabled": True,
    "overtime_enabled": True,
}


def row(date, start, end):
    return {
        "date": date,
        "start_time": start,
        "end_time": end,
    }


def expected_pay(expected, hourly_wage):
    if hourly_wage is None:
        return None
    base = expected["paid_work_minutes"] * hourly_wage / 60
    overtime = expected["overtime_minutes"] * hourly_wage * 0.25 / 60
    night = expected["night_minutes"] * hourly_wage * 0.25 / 60
    return int(round(base + overtime + night))


def summarize(rows, settings):
    total = {
        "confirmed_shift_count": len(rows),
        "total_scheduled_minutes": 0,
        "break_minutes": 0,
        "paid_work_minutes": 0,
        "normal_minutes": 0,
        "overtime_minutes": 0,
        "night_minutes": 0,
        "estimated_pay": None,
    }
    for item in rows:
        calculated = _calculate_shift_pay_minutes(item, settings)
        if calculated is None:
            continue
        total["total_scheduled_minutes"] += calculated["scheduled_minutes"]
        total["break_minutes"] += calculated["break_minutes"]
        total["paid_work_minutes"] += calculated["paid_minutes"]
        total["overtime_minutes"] += calculated["overtime_minutes"]
        total["night_minutes"] += calculated["night_minutes"]

    total["normal_minutes"] = max(0, total["paid_work_minutes"] - total["overtime_minutes"])
    hourly_wage = settings.get("hourly_wage")
    if hourly_wage:
        total["estimated_pay"] = expected_pay(total, hourly_wage)
    return total


def settings(**overrides):
    data = deepcopy(BASE_SETTINGS)
    data.update(overrides)
    return data


CASES = [
    {
        "name": "4 hours, no break",
        "rows": [row("2026-06-01", "09:00", "13:00")],
        "settings": settings(),
        "expected": {
            "confirmed_shift_count": 1,
            "total_scheduled_minutes": 240,
            "break_minutes": 0,
            "paid_work_minutes": 240,
            "normal_minutes": 240,
            "overtime_minutes": 0,
            "night_minutes": 0,
            "estimated_pay": 4800,
        },
    },
    {
        "name": "exactly 6 hours, no break",
        "rows": [row("2026-06-01", "09:00", "15:00")],
        "settings": settings(),
        "expected": {
            "confirmed_shift_count": 1,
            "total_scheduled_minutes": 360,
            "break_minutes": 0,
            "paid_work_minutes": 360,
            "normal_minutes": 360,
            "overtime_minutes": 0,
            "night_minutes": 0,
            "estimated_pay": 7200,
        },
    },
    {
        "name": "6 hours 1 minute, legal break 45 minutes",
        "rows": [row("2026-06-01", "09:00", "15:01")],
        "settings": settings(),
        "expected": {
            "confirmed_shift_count": 1,
            "total_scheduled_minutes": 361,
            "break_minutes": 45,
            "paid_work_minutes": 316,
            "normal_minutes": 316,
            "overtime_minutes": 0,
            "night_minutes": 0,
            "estimated_pay": 6320,
        },
    },
    {
        "name": "exactly 8 hours, legal break 45 minutes",
        "rows": [row("2026-06-01", "09:00", "17:00")],
        "settings": settings(),
        "expected": {
            "confirmed_shift_count": 1,
            "total_scheduled_minutes": 480,
            "break_minutes": 45,
            "paid_work_minutes": 435,
            "normal_minutes": 435,
            "overtime_minutes": 0,
            "night_minutes": 0,
            "estimated_pay": 8700,
        },
    },
    {
        "name": "8 hours 1 minute, legal break 60 minutes",
        "rows": [row("2026-06-01", "09:00", "17:01")],
        "settings": settings(),
        "expected": {
            "confirmed_shift_count": 1,
            "total_scheduled_minutes": 481,
            "break_minutes": 60,
            "paid_work_minutes": 421,
            "normal_minutes": 421,
            "overtime_minutes": 0,
            "night_minutes": 0,
            "estimated_pay": 8420,
        },
    },
    {
        "name": "crosses 22:00 night boundary",
        "rows": [row("2026-06-01", "21:00", "23:00")],
        "settings": settings(),
        "expected": {
            "confirmed_shift_count": 1,
            "total_scheduled_minutes": 120,
            "break_minutes": 0,
            "paid_work_minutes": 120,
            "normal_minutes": 120,
            "overtime_minutes": 0,
            "night_minutes": 60,
            "estimated_pay": 2700,
        },
    },
    {
        "name": "night only, date crossing",
        "rows": [row("2026-06-01", "23:00", "05:00")],
        "settings": settings(),
        "expected": {
            "confirmed_shift_count": 1,
            "total_scheduled_minutes": 360,
            "break_minutes": 0,
            "paid_work_minutes": 360,
            "normal_minutes": 360,
            "overtime_minutes": 0,
            "night_minutes": 360,
            "estimated_pay": 9000,
        },
    },
    {
        "name": "night and overtime premiums can overlap",
        "rows": [row("2026-06-01", "20:00", "06:00")],
        "settings": settings(),
        "expected": {
            "confirmed_shift_count": 1,
            "total_scheduled_minutes": 600,
            "break_minutes": 60,
            "paid_work_minutes": 540,
            "normal_minutes": 480,
            "overtime_minutes": 60,
            "night_minutes": 420,
            "estimated_pay": 13200,
        },
    },
    {
        "name": "break disabled for 8 hours 1 minute",
        "rows": [row("2026-06-01", "09:00", "17:01")],
        "settings": settings(break_rule="none"),
        "expected": {
            "confirmed_shift_count": 1,
            "total_scheduled_minutes": 481,
            "break_minutes": 0,
            "paid_work_minutes": 481,
            "normal_minutes": 480,
            "overtime_minutes": 1,
            "night_minutes": 0,
            "estimated_pay": 9625,
        },
    },
    {
        "name": "night disabled",
        "rows": [row("2026-06-01", "21:00", "23:00")],
        "settings": settings(night_enabled=False),
        "expected": {
            "confirmed_shift_count": 1,
            "total_scheduled_minutes": 120,
            "break_minutes": 0,
            "paid_work_minutes": 120,
            "normal_minutes": 120,
            "overtime_minutes": 0,
            "night_minutes": 0,
            "estimated_pay": 2400,
        },
    },
    {
        "name": "overtime disabled",
        "rows": [row("2026-06-01", "09:00", "18:01")],
        "settings": settings(break_rule="none", overtime_enabled=False),
        "expected": {
            "confirmed_shift_count": 1,
            "total_scheduled_minutes": 541,
            "break_minutes": 0,
            "paid_work_minutes": 541,
            "normal_minutes": 541,
            "overtime_minutes": 0,
            "night_minutes": 0,
            "estimated_pay": 10820,
        },
    },
    {
        "name": "hourly wage change",
        "rows": [row("2026-06-01", "09:00", "13:00")],
        "settings": settings(hourly_wage=1500),
        "expected": {
            "confirmed_shift_count": 1,
            "total_scheduled_minutes": 240,
            "break_minutes": 0,
            "paid_work_minutes": 240,
            "normal_minutes": 240,
            "overtime_minutes": 0,
            "night_minutes": 0,
            "estimated_pay": 6000,
        },
    },
    {
        "name": "zero confirmed shifts",
        "rows": [],
        "settings": settings(),
        "expected": {
            "confirmed_shift_count": 0,
            "total_scheduled_minutes": 0,
            "break_minutes": 0,
            "paid_work_minutes": 0,
            "normal_minutes": 0,
            "overtime_minutes": 0,
            "night_minutes": 0,
            "estimated_pay": 0,
        },
    },
    {
        "name": "multiple days total",
        "rows": [
            row("2026-06-01", "09:00", "13:00"),
            row("2026-06-02", "21:00", "23:00"),
        ],
        "settings": settings(),
        "expected": {
            "confirmed_shift_count": 2,
            "total_scheduled_minutes": 360,
            "break_minutes": 0,
            "paid_work_minutes": 360,
            "normal_minutes": 360,
            "overtime_minutes": 0,
            "night_minutes": 60,
            "estimated_pay": 7500,
        },
    },
]


def compare(expected, actual):
    mismatches = {}
    for key, expected_value in expected.items():
        actual_value = actual.get(key)
        if actual_value != expected_value:
            mismatches[key] = {
                "expected": expected_value,
                "actual": actual_value,
            }
    return mismatches


def main():
    print("Pay calculation verification")
    print("Rules: legal_jp break >6h=45m, >8h=60m; overtime after paid work >8h; night 22:00-05:00; premiums overlap.")
    failed = []
    for case in CASES:
        actual = summarize(case["rows"], case["settings"])
        mismatches = compare(case["expected"], actual)
        if mismatches:
            failed.append((case["name"], mismatches, actual))
            print(f"FAIL: {case['name']}")
            for key, values in mismatches.items():
                print(f"  {key}: expected={values['expected']} actual={values['actual']}")
        else:
            print(f"OK: {case['name']}")

    print(f"\nTotal: {len(CASES)}, passed: {len(CASES) - len(failed)}, failed: {len(failed)}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

from repositories.confirmed_shift_repository import (
    save_confirmed_shift_decisions_bulk,
    upsert_confirmed_shift,
)
from repositories.shift_repository import get_shift_entry_by_id
from utils import hhmm_to_minutes, is_valid_time_hhmm


CONFIRM_STATUS_UNCONFIRMED = "unconfirmed"
CONFIRM_STATUS_ASSIGNED = "assigned"
CONFIRM_STATUS_REST = "rest"
CONFIRM_STATUS_EXCLUDED = "excluded"
VALID_CONFIRM_STATUSES = {
    CONFIRM_STATUS_UNCONFIRMED,
    CONFIRM_STATUS_ASSIGNED,
    CONFIRM_STATUS_REST,
    CONFIRM_STATUS_EXCLUDED,
}
QUARTER_HOUR_MINUTES = {0, 15, 30, 45}


def is_quarter_hour_time(value: str) -> bool:
    return is_valid_time_hhmm(value or "") and int(value[3:]) in QUARTER_HOUR_MINUTES


def round_time_to_quarter(value: str) -> str:
    if not is_valid_time_hhmm(value or ""):
        return value or ""
    total_minutes = hhmm_to_minutes(value)
    rounded = int(round(total_minutes / 15) * 15) % (24 * 60)
    return f"{rounded // 60:02d}:{rounded % 60:02d}"


def can_confirm_submission_entry(entry) -> bool:
    if not entry:
        return False
    if int(entry["off"]) == 1:
        return False
    if not entry["start_time"] or not entry["end_time"]:
        return False
    return True


def validate_confirmed_shift_time(start_time: str, end_time: str):
    if not (is_valid_time_hhmm(start_time or "") and is_valid_time_hhmm(end_time or "")):
        return "時刻の形式が不正です（HH:MM）"
    if not (is_quarter_hour_time(start_time) and is_quarter_hour_time(end_time)):
        return "確定時間は15分単位（00 / 15 / 30 / 45）で入力してください"
    if hhmm_to_minutes(end_time) <= hhmm_to_minutes(start_time):
        return "終了時間は開始時間より後にしてください"
    return None


def validate_submission_entry_for_confirmation(entry, start_time: str, end_time: str):
    if not entry:
        return "提出シフトが見つかりません"
    if int(entry["off"]) == 1:
        return "休みの希望シフトは確定できません"
    if not entry["start_time"] or not entry["end_time"]:
        return "開始時間または終了時間が未入力の希望シフトは確定できません"
    return validate_confirmed_shift_time(start_time, end_time)


def validate_confirmed_shift_for_assignment(start_time: str, end_time: str):
    return validate_confirmed_shift_time(start_time, end_time)


def validate_submission_entry_for_exclusion(entry):
    if not entry:
        return "提出シフトが見つかりません"
    if int(entry["off"]) == 1:
        return "休みとして保存済みです"
    if not entry["start_time"] or not entry["end_time"]:
        return "開始時間または終了時間が未入力です"
    return None

def save_confirmed_shift_from_entry(entry, start_time: str, end_time: str):
    upsert_confirmed_shift(
        user_id=int(entry["user_id"]),
        date_str=entry["date"],
        start_time=start_time,
        end_time=end_time,
        source_entry_id=entry["id"],
        is_assigned=1,
    )


def save_excluded_shift_from_entry(entry):
    upsert_confirmed_shift(
        user_id=int(entry["user_id"]),
        date_str=entry["date"],
        start_time="",
        end_time="",
        source_entry_id=entry["id"],
        is_assigned=0,
    )


def validate_and_save_confirmed_shifts_bulk(target_date: str, submitted_items, save_unsubmitted_as_rest: bool = False):
    decisions = []
    seen_user_ids = set()

    for item in submitted_items:
        entry_id = item.get("entry_id")
        user_id = item.get("user_id")
        status = item.get("status")
        start_time = (item.get("start_time") or "").strip()
        end_time = (item.get("end_time") or "").strip()

        entry = get_shift_entry_by_id(entry_id) if entry_id else None

        if status == "" and save_unsubmitted_as_rest and not entry:
            status = CONFIRM_STATUS_REST
        if status == CONFIRM_STATUS_EXCLUDED:
            status = CONFIRM_STATUS_REST
        if status == "":
            status = CONFIRM_STATUS_UNCONFIRMED
        if not user_id or status not in VALID_CONFIRM_STATUSES:
            return "確定状態が不正です", 400
        if user_id in seen_user_ids:
            continue
        seen_user_ids.add(user_id)

        if entry_id and (not entry or entry["date"] != target_date or int(entry["user_id"]) != int(user_id)):
            return "提出シフトが不正です", 400

        if status == CONFIRM_STATUS_ASSIGNED:
            error_message = validate_confirmed_shift_for_assignment(start_time, end_time)
            if error_message:
                return error_message, 400
            is_assigned = 1
        elif status == CONFIRM_STATUS_REST:
            start_time = None
            end_time = None
            is_assigned = 0
        else:
            start_time = ""
            end_time = ""
            is_assigned = None

        decisions.append({
            "status": status,
            "user_id": int(user_id),
            "date": target_date,
            "start_time": start_time,
            "end_time": end_time,
            "is_assigned": is_assigned,
            "source_entry_id": int(entry["id"]) if entry else None,
        })

    save_confirmed_shift_decisions_bulk(decisions)
    return None, 200

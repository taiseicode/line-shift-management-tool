import json
import urllib.error
import urllib.request

from config import LINE_CHANNEL_ACCESS_TOKEN


LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
LINE_MULTICAST_URL = "https://api.line.me/v2/bot/message/multicast"


def _post_line_message(url: str, payload: dict) -> tuple[bool, str | None]:
    if not LINE_CHANNEL_ACCESS_TOKEN:
        return False, "LINE_CHANNEL_ACCESS_TOKEN is not set"

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if 200 <= int(response.status) < 300:
                return True, None
            body = response.read().decode("utf-8", errors="replace")
            return False, f"LINE API returned {response.status}: {body}"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return False, f"LINE API returned {exc.code}: {body}"
    except Exception as exc:
        return False, str(exc)


def send_line_message(line_user_id: str, message: str) -> tuple[bool, str | None]:
    line_user_id = (line_user_id or "").strip()
    if not line_user_id:
        return False, "line_user_id is empty"
    payload = {
        "to": line_user_id,
        "messages": [{"type": "text", "text": message or ""}],
    }
    return _post_line_message(LINE_PUSH_URL, payload)


def send_line_multicast(line_user_ids: list[str], message: str) -> tuple[int, int, str | None]:
    ids = []
    seen = set()
    for line_user_id in line_user_ids or []:
        value = (line_user_id or "").strip()
        if value and value not in seen:
            ids.append(value)
            seen.add(value)

    sent_count = 0
    failed_count = 0
    errors = []
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        ok, error = _post_line_message(
            LINE_MULTICAST_URL,
            {
                "to": chunk,
                "messages": [{"type": "text", "text": message or ""}],
            },
        )
        if ok:
            sent_count += len(chunk)
        else:
            failed_count += len(chunk)
            if error:
                errors.append(error)
    return sent_count, failed_count, "\n".join(errors) if errors else None

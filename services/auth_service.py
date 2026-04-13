import base64
import hmac
import json
import secrets
import time
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from flask import request, jsonify, session

from config import (
    FLASK_SECRET_KEY,
    ADMIN_PASSWORD,
    LIFF_ID,
    LINE_LOGIN_CHANNEL_ID,
    LINE_ID_TOKEN_VERIFY_URL,
    UNSAFE_SECRET_KEY_VALUES,
    UNSAFE_ADMIN_PASSWORD_VALUES,
    LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    LOGIN_RATE_LIMIT_MAX_FAILURES,
    LOGIN_RATE_LIMIT_BLOCK_SECONDS,
)

login_attempt_state = {}


def validate_runtime_security():
    errors = []
    if FLASK_SECRET_KEY in UNSAFE_SECRET_KEY_VALUES or len(FLASK_SECRET_KEY) < 32:
        errors.append("FLASK_SECRET_KEY must be set to a strong random value (32+ chars) in .env")
    if ADMIN_PASSWORD in UNSAFE_ADMIN_PASSWORD_VALUES or len(ADMIN_PASSWORD) < 12:
        errors.append("ADMIN_PASSWORD must be set to a strong non-default value (12+ chars) in .env")
    if LIFF_ID and not LINE_LOGIN_CHANNEL_ID:
        errors.append("LINE_LOGIN_CHANNEL_ID must be set in .env when LIFF_ID is enabled")
    if errors:
        raise Exception("Security configuration error: " + " / ".join(errors))

def get_client_ip():
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return forwarded or request.remote_addr or "unknown"

def _get_login_attempt_bucket(ip_addr: str):
    now_ts = time.time()
    state = login_attempt_state.get(ip_addr, {"failures": [], "blocked_until": 0})
    failures = [ts for ts in state["failures"] if now_ts - ts <= LOGIN_RATE_LIMIT_WINDOW_SECONDS]
    blocked_until = state.get("blocked_until", 0)
    if blocked_until and blocked_until <= now_ts:
        blocked_until = 0
    state = {"failures": failures, "blocked_until": blocked_until}
    login_attempt_state[ip_addr] = state
    return state

def get_login_block_remaining(ip_addr: str):
    state = _get_login_attempt_bucket(ip_addr)
    remaining = max(0, int(state["blocked_until"] - time.time()))
    return remaining

def register_login_failure(ip_addr: str):
    state = _get_login_attempt_bucket(ip_addr)
    state["failures"].append(time.time())
    if len(state["failures"]) >= LOGIN_RATE_LIMIT_MAX_FAILURES:
        state["blocked_until"] = time.time() + LOGIN_RATE_LIMIT_BLOCK_SECONDS
    login_attempt_state[ip_addr] = state

def clear_login_failures(ip_addr: str):
    login_attempt_state.pop(ip_addr, None)

def get_or_create_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token

def rotate_csrf_token():
    session["_csrf_token"] = secrets.token_urlsafe(32)
    return session["_csrf_token"]

def validate_csrf_or_400():
    expected = session.get("_csrf_token", "")
    provided = (request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or "").strip()
    if not expected or not provided or not hmac.compare_digest(expected, provided):
        return "CSRF token が不正です", 400
    return None

def decode_jwt_payload_unverified(id_token: str):
    parts = (id_token or "").split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8")
        return json.loads(decoded)
    except Exception:
        return {}

def verify_line_id_token(id_token: str):
    if not id_token:
        raise ValueError("Missing id_token")
    if not LINE_LOGIN_CHANNEL_ID:
        raise RuntimeError("LINE_LOGIN_CHANNEL_ID is not configured")

    body = urllib_parse.urlencode({
        "id_token": id_token,
        "client_id": LINE_LOGIN_CHANNEL_ID,
    }).encode("utf-8")
    req = urllib_request.Request(
        LINE_ID_TOKEN_VERIFY_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValueError("Failed to verify LINE id_token") from exc

    sub = (payload.get("sub") or "").strip()
    if not sub:
        raise ValueError("LINE id_token did not contain sub")

    decoded = decode_jwt_payload_unverified(id_token)
    if decoded.get("sub") and decoded.get("sub") != sub:
        raise ValueError("LINE id_token sub mismatch")
    if decoded.get("aud") and str(decoded.get("aud")) != str(LINE_LOGIN_CHANNEL_ID):
        raise ValueError("LINE id_token aud mismatch")
    if decoded.get("name") and not payload.get("name"):
        payload["name"] = decoded.get("name")
    return payload

def require_verified_line_claims():
    data = request.get_json(silent=True) or {}
    id_token = (data.get("id_token") or "").strip()
    if not id_token:
        return None, data, (jsonify({"error": "id_token が必要です"}), 401)
    try:
        claims = verify_line_id_token(id_token)
    except RuntimeError:
        return None, data, (jsonify({"error": "LINE認証のサーバー設定が不足しています"}), 500)
    except ValueError:
        return None, data, (jsonify({"error": "LINE認証に失敗しました"}), 401)
    return claims, data, None

def reject_if_user_inactive(user):
    if user and int(user["active"]) != 1:
        return jsonify({"error": "このユーザーは現在無効化されています"}), 403
    return None

from time import monotonic
from threading import Lock

from db import get_conn


_SETTING_CACHE_TTL_SECONDS = 5
_settings_cache = {}
_settings_cache_lock = Lock()


def _get_cached_setting(key: str):
    with _settings_cache_lock:
        item = _settings_cache.get(key)
        if not item:
            return False, None
        cached_at, value = item
        if monotonic() - cached_at > _SETTING_CACHE_TTL_SECONDS:
            _settings_cache.pop(key, None)
            return False, None
        return True, value


def _set_cached_setting(key: str, value):
    with _settings_cache_lock:
        _settings_cache[key] = (monotonic(), value)


def _invalidate_setting_cache(key: str = None):
    with _settings_cache_lock:
        if key is None:
            _settings_cache.clear()
        else:
            _settings_cache.pop(key, None)


def get_setting(key: str):
    found, value = _get_cached_setting(key)
    if found:
        return value
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = c.fetchone()
        value = row["value"] if row else None
        _set_cached_setting(key, value)
        return value


def get_settings(keys):
    unique_keys = []
    for key in keys:
        normalized = str(key)
        if normalized not in unique_keys:
            unique_keys.append(normalized)

    result = {}
    missing_keys = []
    for key in unique_keys:
        found, value = _get_cached_setting(key)
        if found:
            result[key] = value
        else:
            missing_keys.append(key)

    if not missing_keys:
        return result

    with get_conn() as conn:
        c = conn.cursor()
        placeholders = ", ".join(["?"] * len(missing_keys))
        rows = c.execute(
            f"SELECT key, value FROM settings WHERE key IN ({placeholders})",
            missing_keys,
        ).fetchall()
        fetched = {row["key"]: row["value"] for row in rows}
        for key in missing_keys:
            value = fetched.get(key)
            result[key] = value
            _set_cached_setting(key, value)
        return result


def upsert_setting(key: str, value: str):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO settings(key, value)
            VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET
              value=excluded.value
        """, (key, value))
        conn.commit()
        _invalidate_setting_cache(key)


def delete_setting(key: str):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM settings WHERE key=?", (key,))
        conn.commit()
        _invalidate_setting_cache(key)

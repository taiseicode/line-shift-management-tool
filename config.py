import os
from linebot import LineBotApi, WebhookHandler
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "shift.db")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5000"))
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "change-this-super-secret-key")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LIFF_ID = os.getenv("LIFF_ID", "")
LINE_LOGIN_CHANNEL_ID = (os.getenv("LINE_LOGIN_CHANNEL_ID", "") or os.getenv("LINE_CHANNEL_ID", "")).strip()
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "1").strip().lower() in ("1", "true", "yes", "on")

if not LINE_CHANNEL_SECRET or not LINE_CHANNEL_ACCESS_TOKEN:
    raise Exception("LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN must be set in environment")

SUBMISSION_DEADLINE_SETTING_KEY = "submission_deadline"
DEADLINE_MODE_SETTING_KEY = "deadline_mode"
DEADLINE_DAYS_BEFORE_SETTING_KEY = "deadline_days_before"
DEADLINE_TIME_SETTING_KEY = "deadline_time"

LINE_ID_TOKEN_VERIFY_URL = "https://api.line.me/oauth2/v2.1/verify"
UNSAFE_SECRET_KEY_VALUES = {"", "change-this-super-secret-key", "secret", "dev", "development"}
UNSAFE_ADMIN_PASSWORD_VALUES = {"", "admin123", "password", "12345678", "changeme"}
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 15 * 60
LOGIN_RATE_LIMIT_MAX_FAILURES = 5
LOGIN_RATE_LIMIT_BLOCK_SECONDS = 15 * 60

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

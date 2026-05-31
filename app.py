import os
from datetime import timedelta
from time import perf_counter

from flask import Flask, g, request

from config import FLASK_SECRET_KEY, SESSION_COOKIE_SECURE, HOST, PORT
from db import init_tables
from routes.admin import admin_bp
from routes.api import api_bp
from routes.liff import liff_bp
from routes.webhook import webhook_bp
from services.auth_service import validate_runtime_security


ADMIN_TIMING_PATHS = {
    "/admin",
    "/admin/confirm",
    "/admin/cost",
    "/admin/deadline",
    "/admin/users",
    "/admin/manual",
}


def create_app():
    app = Flask(__name__)
    app.secret_key = FLASK_SECRET_KEY
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = timedelta(hours=12)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = SESSION_COOKIE_SECURE
    app.config["SESSION_REFRESH_EACH_REQUEST"] = False
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)

    @app.before_request
    def _start_request_timer():
        if request.path in ADMIN_TIMING_PATHS:
            g.request_started_at = perf_counter()

    @app.after_request
    def _add_cache_and_timing_headers(response):
        if request.endpoint == "static":
            if request.path.startswith("/static/manual/"):
                response.headers["Cache-Control"] = "public, max-age=604800"
            else:
                response.headers.setdefault("Cache-Control", "public, max-age=43200")

        started_at = getattr(g, "request_started_at", None)
        if started_at is not None and os.getenv("ADMIN_TIMING_LOG", "1").strip().lower() in ("1", "true", "yes", "on"):
            elapsed_seconds = perf_counter() - started_at
            sql_count = int(getattr(g, "sql_query_count", 0))
            print(
                f"[admin timing] {request.method} {request.path} {response.status_code} {elapsed_seconds:.3f}s sql={sql_count}",
                flush=True,
            )
        return response

    validate_runtime_security()
    init_tables()

    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(liff_bp)
    app.register_blueprint(webhook_bp)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=True)


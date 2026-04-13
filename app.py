from datetime import timedelta

from flask import Flask

from config import FLASK_SECRET_KEY, SESSION_COOKIE_SECURE, HOST, PORT
from db import init_tables
from routes.admin import admin_bp
from routes.api import api_bp
from routes.liff import liff_bp
from routes.webhook import webhook_bp
from services.auth_service import validate_runtime_security


def create_app():
    app = Flask(__name__)
    app.secret_key = FLASK_SECRET_KEY
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = SESSION_COOKIE_SECURE
    app.config["SESSION_REFRESH_EACH_REQUEST"] = False
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)

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


from datetime import timedelta
from urllib.parse import urlencode

from flask import Blueprint, jsonify, make_response, redirect, render_template, request, session

from config import CRON_SECRET
from repositories.user_repository import get_all_users
from services.auth_service import get_or_create_csrf_token, validate_csrf_or_400
from services.notification_service import (
    TARGET_ALL,
    TARGET_ASSIGNED,
    TARGET_INDIVIDUAL,
    TARGET_TOMORROW_ASSIGNED,
    TARGET_UNSUBMITTED,
    delete_notification_rule,
    get_notification_logs,
    get_notification_rule,
    get_notification_rules,
    get_recipients,
    run_due_notifications,
    save_notification_rule,
    send_notification,
    set_notification_rule_enabled,
)
from utils import parse_ymd, to_ymd, today_jst


notifications_bp = Blueprint("notifications", __name__)


def _notifications_context(status="", error=""):
    today = today_jst()
    start_d = parse_ymd(request.args.get("start")) or today
    end_d = parse_ymd(request.args.get("end")) or (start_d + timedelta(days=6))
    if start_d > end_d:
        start_d, end_d = end_d, start_d
    target_date = request.args.get("target_date") or to_ymd(today)
    users = [
        user for user in get_all_users(include_inactive=False)
        if (user["line_user_id"] or "").strip()
    ]
    edit_rule_id = (request.args.get("edit_rule_id") or "").strip()
    edit_rule = None
    if edit_rule_id:
        try:
            edit_rule = get_notification_rule(int(edit_rule_id))
        except (TypeError, ValueError):
            edit_rule = None
    return {
        "active_nav": "notifications",
        "csrf_token_value": get_or_create_csrf_token(),
        "start_value": to_ymd(start_d),
        "end_value": to_ymd(end_d),
        "confirm_date_value": target_date,
        "confirm_sort": request.args.get("sort") or "display",
        "target_date_value": target_date,
        "users": users,
        "logs": get_notification_logs(20),
        "rules": get_notification_rules(),
        "edit_rule": edit_rule,
        "status": status,
        "error": error,
    }


def _redirect_with_message(status="", error="", target_date=""):
    params = {}
    if status:
        params["status"] = status
    if error:
        params["error"] = error
    if target_date:
        params["target_date"] = target_date
    query = urlencode(params)
    return redirect(f"/admin/notifications?{query}" if query else "/admin/notifications")


@notifications_bp.route("/admin/notifications", methods=["GET"])
def admin_notifications():
    if not session.get("logged_in"):
        return redirect("/login")
    ctx = _notifications_context(
        status=request.args.get("status") or "",
        error=request.args.get("error") or "",
    )
    return make_response(render_template("admin_notifications.html", **ctx))


@notifications_bp.route("/admin/notifications/send", methods=["POST"])
def admin_notifications_send():
    if not session.get("logged_in"):
        return redirect("/login")
    csrf_error = validate_csrf_or_400()
    if csrf_error:
        return csrf_error

    title = (request.form.get("title") or "").strip()
    message = (request.form.get("message") or "").strip()
    target_type = (request.form.get("target_type") or "").strip()
    target_date = (request.form.get("target_date") or "").strip()
    user_ids = request.form.getlist("user_ids")

    if not message:
        return _redirect_with_message(error="本文を入力してください。", target_date=target_date)
    if target_type not in {TARGET_ALL, TARGET_UNSUBMITTED, TARGET_ASSIGNED, TARGET_INDIVIDUAL}:
        return _redirect_with_message(error="対象者の指定が不正です。", target_date=target_date)
    if target_type in {TARGET_UNSUBMITTED, TARGET_ASSIGNED} and not parse_ymd(target_date):
        return _redirect_with_message(error="対象日を選択してください。", target_date=target_date)
    if target_type == TARGET_INDIVIDUAL and not user_ids:
        return _redirect_with_message(error="個別ユーザーを選択してください。", target_date=target_date)

    try:
        result = send_notification(title, message, target_type, target_date, user_ids)
    except Exception as exc:
        return _redirect_with_message(error=f"送信中にエラーが発生しました: {exc}", target_date=target_date)

    status = f"送信完了: 成功 {result['sent_count']} 件 / 失敗 {result['failed_count']} 件"
    return _redirect_with_message(status=status, target_date=target_date)


@notifications_bp.route("/admin/notifications/rules/save", methods=["POST"])
def admin_notifications_rules_save():
    if not session.get("logged_in"):
        return redirect("/login")
    csrf_error = validate_csrf_or_400()
    if csrf_error:
        return csrf_error

    rule_id = (request.form.get("rule_id") or "").strip()
    try:
        save_notification_rule(
            {
                "name": request.form.get("name"),
                "enabled": bool(request.form.get("enabled")),
                "schedule_type": request.form.get("schedule_type"),
                "weekday": request.form.get("weekday"),
                "month_day": request.form.get("month_day"),
                "send_time": request.form.get("send_time"),
                "target_type": request.form.get("rule_target_type"),
                "target_date_mode": request.form.get("target_date_mode"),
                "title": request.form.get("rule_title"),
                "message": request.form.get("rule_message"),
                "user_ids": request.form.getlist("rule_user_ids"),
            },
            rule_id=int(rule_id) if rule_id else None,
        )
    except Exception as exc:
        return _redirect_with_message(error=str(exc))
    return _redirect_with_message(status="自動通知ルールを保存しました。")


@notifications_bp.route("/admin/notifications/rules/toggle", methods=["POST"])
def admin_notifications_rules_toggle():
    if not session.get("logged_in"):
        return redirect("/login")
    csrf_error = validate_csrf_or_400()
    if csrf_error:
        return csrf_error
    try:
        rule_id = int(request.form.get("rule_id") or "0")
        enabled = bool(request.form.get("enabled"))
        set_notification_rule_enabled(rule_id, enabled)
    except Exception as exc:
        return _redirect_with_message(error=str(exc))
    return _redirect_with_message(status="自動通知ルールを更新しました。")


@notifications_bp.route("/admin/notifications/rules/delete", methods=["POST"])
def admin_notifications_rules_delete():
    if not session.get("logged_in"):
        return redirect("/login")
    csrf_error = validate_csrf_or_400()
    if csrf_error:
        return csrf_error
    try:
        rule_id = int(request.form.get("rule_id") or "0")
        delete_notification_rule(rule_id)
    except Exception as exc:
        return _redirect_with_message(error=str(exc))
    return _redirect_with_message(status="自動通知ルールを削除しました。")


@notifications_bp.route("/admin/notifications/preview-count", methods=["GET"])
def admin_notifications_preview_count():
    if not session.get("logged_in"):
        return jsonify({"error": "unauthorized"}), 401
    target_type = (request.args.get("target_type") or "").strip()
    target_date = (request.args.get("target_date") or "").strip()
    user_ids = request.args.getlist("user_ids")
    if target_type == TARGET_TOMORROW_ASSIGNED:
        target_type = TARGET_ASSIGNED
    recipients = get_recipients(target_type, target_date, user_ids)
    return jsonify({"count": len(recipients)})


@notifications_bp.route("/internal/run-notifications", methods=["GET"])
def internal_run_notifications():
    if CRON_SECRET:
        if not request.args.get("secret") or request.args.get("secret") != CRON_SECRET:
            return jsonify({"error": "forbidden"}), 403
    elif not session.get("logged_in"):
        return jsonify({"error": "unauthorized"}), 401

    try:
        results = run_due_notifications()
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, "results": results})

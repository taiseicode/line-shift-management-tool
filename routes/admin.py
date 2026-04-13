import hmac
from datetime import datetime, timedelta, date
from io import BytesIO

from flask import Blueprint, request, redirect, session, send_file
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Side, PatternFill, Font
from openpyxl.utils import get_column_letter

from config import ADMIN_PASSWORD
from db import get_conn
from repositories.required_staff_repository import upsert_required_staff, get_required_staff_range
from repositories.shift_repository import get_entries_range
from repositories.user_repository import get_all_users, set_user_active, update_user_name
from services.auth_service import (
    get_or_create_csrf_token,
    validate_csrf_or_400,
    get_client_ip,
    get_login_block_remaining,
    clear_login_failures,
    rotate_csrf_token,
    register_login_failure,
)
from services.deadline_service import (
    get_active_deadline_config,
    get_submission_deadline,
    set_deadline_mode,
    set_submission_deadline,
    set_deadline_days_before,
    set_deadline_time,
)
from services.summary_service import calculate_staff_summary
from utils import (
    parse_ymd,
    to_ymd,
    parse_submission_deadline,
    parse_int_or_none,
    to_datetime_local_value,
    format_submission_deadline,
    format_relative_deadline,
    daterange_inclusive,
    html_escape,
    get_weekday_jp,
    is_valid_time_hhmm,
)


admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    error_html = ""
    csrf_token_value = get_or_create_csrf_token()
    if request.method == "POST":
        csrf_error = validate_csrf_or_400()
        if csrf_error:
            return csrf_error
        ip_addr = get_client_ip()
        remaining = get_login_block_remaining(ip_addr)
        if remaining > 0:
            minutes_left = max(1, remaining // 60)
            error_html = f'<div class="alert alert-danger py-2 mb-3">ログイン試行が多すぎます。{minutes_left}分ほど待ってから再試行してください。</div>'
        else:
            pw = request.form.get("password", "")
            if hmac.compare_digest(pw, ADMIN_PASSWORD):
                clear_login_failures(ip_addr)
                session.clear()
                session["logged_in"] = True
                session.permanent = False
                rotate_csrf_token()
                return redirect("/admin")
            register_login_failure(ip_addr)
            error_html = '<div class="alert alert-danger py-2 mb-3">パスワードが違います</div>'

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>管理者ログイン</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
  <div class="container py-5" style="max-width: 460px;">
    <div class="card shadow-sm border-0">
      <div class="card-body p-4">
        <h2 class="mb-1">管理者ログイン</h2>
        <div class="text-muted mb-4">シフト管理ツール 管理画面</div>
        {error_html}
        <form method="POST">
          <input type="hidden" name="csrf_token" value="{csrf_token_value}">
          <div class="mb-3">
            <label class="form-label">パスワード</label>
            <input type="password" class="form-control" name="password" placeholder="パスワード">
          </div>
          <button type="submit" class="btn btn-dark w-100">ログイン</button>
        </form>
        <div class="small text-muted mt-3">※管理者パスワードは .env に安全な値を設定してください。</div>
      </div>
    </div>
  </div>
</body>
</html>
"""

@admin_bp.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect("/login")

@admin_bp.route("/admin/update_required", methods=["POST"])
def admin_update_required():
    if not session.get("logged_in"):
        return redirect("/login")
    csrf_error = validate_csrf_or_400()
    if csrf_error:
        return csrf_error

    start = request.form.get("start", "").strip()
    end = request.form.get("end", "").strip()

    start_d = parse_ymd(start)
    end_d = parse_ymd(end)
    if not start_d or not end_d:
        return "日付が不正です", 400

    if start_d > end_d:
        start_d, end_d = end_d, start_d

    for d in daterange_inclusive(start_d, end_d):
        ymd = to_ymd(d)
        raw = request.form.get(f"required_{ymd}", "").strip()
        if raw == "":
            required_count = 0
        else:
            try:
                required_count = int(raw)
            except Exception:
                required_count = 0

        if required_count < 0:
            required_count = 0

        upsert_required_staff(ymd, required_count)

    return redirect(f"/admin?start={to_ymd(start_d)}&end={to_ymd(end_d)}")

@admin_bp.route("/admin/update_submission_deadline", methods=["POST"])
def admin_update_submission_deadline():
    if not session.get("logged_in"):
        return redirect("/login")
    csrf_error = validate_csrf_or_400()
    if csrf_error:
        return csrf_error

    start = request.form.get("start", "").strip()
    end = request.form.get("end", "").strip()
    deadline_mode = (request.form.get("deadline_mode") or "").strip()
    deadline_raw = request.form.get("submission_deadline", "").strip()
    days_before_raw = request.form.get("deadline_days_before", "").strip()
    deadline_time = (request.form.get("deadline_time") or "").strip()
    deadline = parse_submission_deadline(deadline_raw)
    days_before = parse_int_or_none(days_before_raw) if days_before_raw != "" else None

    if deadline_mode not in ("", "fixed", "relative"):
        return "提出期限の設定方式が不正です", 400
    if deadline_raw and not deadline:
        return "提出期限の形式が不正です", 400
    if days_before_raw != "" and days_before is None:
        return "何日前の形式が不正です", 400
    if days_before is not None and days_before < 0:
        return "何日前は0以上で入力してください", 400
    if deadline_time and not is_valid_time_hhmm(deadline_time):
        return "締切時刻の形式が不正です（HH:MM）", 400
    if deadline_mode == "fixed" and deadline is None:
        return "固定日時方式を使う場合は締切日時を入力してください", 400
    if deadline_mode == "relative" and (days_before is None or not deadline_time):
        return "相対期限方式を使う場合は何日前と締切時刻を入力してください", 400

    set_deadline_mode(deadline_mode)
    set_submission_deadline(deadline)
    set_deadline_days_before(days_before)
    set_deadline_time(deadline_time or None)

    redirect_start = start or to_ymd(datetime.now().date())
    redirect_end = end or redirect_start
    return redirect(f"/admin?start={redirect_start}&end={redirect_end}")

@admin_bp.route("/admin/users/deactivate", methods=["POST"])
def admin_users_deactivate():
    if not session.get("logged_in"):
        return redirect("/login")
    csrf_error = validate_csrf_or_400()
    if csrf_error:
        return csrf_error

    user_id = parse_int_or_none(request.form.get("user_id"))
    if not user_id:
        return "user_id が不正です", 400

    updated = set_user_active(user_id, 0)
    if updated <= 0:
        return "対象ユーザーが見つかりません", 404
    start = (request.form.get("start") or "").strip()
    end = (request.form.get("end") or "").strip()
    redirect_start = start or to_ymd(datetime.now().date())
    redirect_end = end or redirect_start
    return redirect(f"/admin?start={redirect_start}&end={redirect_end}")

@admin_bp.route("/admin/users/activate", methods=["POST"])
def admin_users_activate():
    if not session.get("logged_in"):
        return redirect("/login")
    csrf_error = validate_csrf_or_400()
    if csrf_error:
        return csrf_error

    user_id = parse_int_or_none(request.form.get("user_id"))
    if not user_id:
        return "user_id が不正です", 400

    updated = set_user_active(user_id, 1)
    if updated <= 0:
        return "対象ユーザーが見つかりません", 404
    start = (request.form.get("start") or "").strip()
    end = (request.form.get("end") or "").strip()
    redirect_start = start or to_ymd(datetime.now().date())
    redirect_end = end or redirect_start
    return redirect(f"/admin?start={redirect_start}&end={redirect_end}")

@admin_bp.route("/admin/users/update_name", methods=["POST"])
def admin_users_update_name():
    if not session.get("logged_in"):
        return redirect("/login")
    csrf_error = validate_csrf_or_400()
    if csrf_error:
        return csrf_error

    user_id = parse_int_or_none(request.form.get("user_id"))
    new_name = (request.form.get("new_name") or "").strip()
    if not user_id:
        return "user_id が不正です", 400
    if not new_name:
        return "new_name は必須です", 400

    updated = update_user_name(user_id, new_name)
    if updated <= 0:
        return "対象ユーザーが見つかりません", 404

    start = (request.form.get("start") or "").strip()
    end = (request.form.get("end") or "").strip()
    redirect_start = start or to_ymd(datetime.now().date())
    redirect_end = end or redirect_start
    return redirect(f"/admin?start={redirect_start}&end={redirect_end}")

@admin_bp.route("/admin", methods=["GET"])
def admin():
    if not session.get("logged_in"):
        return redirect("/login")
    csrf_token_value = get_or_create_csrf_token()

    today = datetime.now().date()
    start = request.args.get("start", "").strip()
    end = request.args.get("end", "").strip()

    start_d = parse_ymd(start) or today
    end_d = parse_ymd(end) or (start_d + timedelta(days=6))
    if start_d > end_d:
        start_d, end_d = end_d, start_d

    start_value = to_ymd(start_d)
    end_value = to_ymd(end_d)
    active_deadline_config = get_active_deadline_config()
    submission_deadline = get_submission_deadline()
    submission_deadline_text = format_submission_deadline(submission_deadline)
    submission_deadline_value = to_datetime_local_value(submission_deadline)
    deadline_days_before_value = (
        "" if active_deadline_config["relative_days_before"] is None else str(active_deadline_config["relative_days_before"])
    )
    deadline_time_value = active_deadline_config["relative_time"] or ""
    deadline_mode_value = active_deadline_config["mode"] or ""
    deadline_mode_labels = {
        "fixed": "固定日時方式",
        "relative": "相対期限方式",
        "": "未設定",
    }
    submission_status_text = deadline_mode_labels.get(deadline_mode_value, "未設定")
    submission_status_badge = (
        '<span class="badge bg-warning text-dark">未設定</span>'
        if not active_deadline_config["is_configured"]
        else f'<span class="badge bg-primary">{html_escape(submission_status_text)}</span>'
    )

    rows = get_entries_range(start_value, end_value)
    summary_by_date = calculate_staff_summary(start_d, end_d)
    admin_users = get_all_users(include_inactive=True)
    active_admin_users = [user for user in admin_users if int(user["active"]) == 1]
    inactive_admin_users = [user for user in admin_users if int(user["active"]) != 1]

    by_date = {}
    for r in rows:
        if int(r["active"]) != 1:
            continue
        by_date.setdefault(r["date"], []).append(r)

    table_rows = ""
    for d in daterange_inclusive(start_d, end_d):
        ymd = to_ymd(d)
        items = by_date.get(ymd, [])
        summary = summary_by_date[ymd]

        if summary["required"] <= 0:
            status_badge = '<span class="badge bg-secondary">必要人数未設定</span>'
        elif summary["is_shortage"]:
            status_badge = f'<span class="badge bg-danger">不足 {summary["shortage_count"]}人</span>'
        else:
            status_badge = '<span class="badge bg-success">充足</span>'

        if not items:
            submit_html = "<div class='text-muted'>（提出なし）</div>"
        else:
            lines = []
            for r in items:
                name = html_escape(r["name"] or "")
                if int(r["off"]) == 1:
                    lines.append(
                        f"<div class='border rounded p-2 mb-2 bg-white'>"
                        f"<b>{name}</b>：<span class='badge bg-secondary'>休み</span>"
                        f"</div>"
                    )
                else:
                    st = html_escape(r["start_time"] or "")
                    et = html_escape(r["end_time"] or "")
                    lines.append(
                        f"<div class='border rounded p-2 mb-2 bg-white'>"
                        f"<b>{name}</b>：<span class='badge bg-primary'>{st}-{et}</span>"
                        f"</div>"
                    )
            submit_html = "".join(lines)

        table_rows += f"""
        <tr>
          <td style="width:220px;">
            <div class="fw-semibold">{d.month}/{d.day}（{get_weekday_jp(d)}）</div>
            <div class="small text-muted">{ymd}</div>
          </td>
          <td style="width:180px;">
            <input type="number"
                   class="form-control form-control-sm"
                   min="0"
                   name="required_{ymd}"
                   value="{summary["required"]}">
          </td>
          <td style="width:220px;">
            <div class="mb-1">{status_badge}</div>
            <div class="small">
              <div>出勤予定：<b>{summary["working_count"]}</b>人</div>
              <div>休み：<b>{summary["off_count"]}</b>人</div>
              <div>未提出：<b>{summary["not_submitted_count"]}</b>人</div>
            </div>
          </td>
          <td>{submit_html}</td>
        </tr>
        """

    active_user_table_rows = ""
    for user in active_admin_users:
        active_user_table_rows += f"""
        <tr>
          <td>{html_escape(user["name"] or "")}</td>
          <td><code>{html_escape(user["line_user_id"] or "")}</code></td>
          <td><span class="badge bg-success">有効</span></td>
          <td>
            <div class="d-grid gap-2">
              <form method="POST" action="/admin/users/deactivate" onsubmit="return confirm('このユーザーを無効化しますか？');">
                <input type="hidden" name="csrf_token" value="{csrf_token_value}">
                <input type="hidden" name="start" value="{start_value}">
                <input type="hidden" name="end" value="{end_value}">
                <input type="hidden" name="user_id" value="{user["id"]}">
                <button type="submit" class="btn btn-sm btn-outline-danger">無効化</button>
              </form>
              <form method="POST" action="/admin/users/update_name" class="d-flex gap-2">
                <input type="hidden" name="csrf_token" value="{csrf_token_value}">
                <input type="hidden" name="start" value="{start_value}">
                <input type="hidden" name="end" value="{end_value}">
                <input type="hidden" name="user_id" value="{user["id"]}">
                <input type="text" class="form-control form-control-sm" name="new_name" value="{html_escape(user["name"] or "")}" placeholder="新しい名前">
                <button type="submit" class="btn btn-sm btn-outline-primary">更新</button>
              </form>
            </div>
          </td>
        </tr>
        """
    if not active_user_table_rows:
        active_user_table_rows = """
        <tr>
          <td colspan="4" class="text-muted">有効ユーザーはまだいません。</td>
        </tr>
        """

    inactive_user_table_rows = ""
    for user in inactive_admin_users:
        inactive_user_table_rows += f"""
        <tr>
          <td>{html_escape(user["name"] or "")}</td>
          <td><code>{html_escape(user["line_user_id"] or "")}</code></td>
          <td><span class="badge bg-secondary">無効</span></td>
          <td>
            <div class="d-grid gap-2">
              <form method="POST" action="/admin/users/activate" onsubmit="return confirm('このユーザーを再有効化しますか？');">
                <input type="hidden" name="csrf_token" value="{csrf_token_value}">
                <input type="hidden" name="start" value="{start_value}">
                <input type="hidden" name="end" value="{end_value}">
                <input type="hidden" name="user_id" value="{user["id"]}">
                <button type="submit" class="btn btn-sm btn-outline-success">再有効化</button>
              </form>
              <form method="POST" action="/admin/users/update_name" class="d-flex gap-2">
                <input type="hidden" name="csrf_token" value="{csrf_token_value}">
                <input type="hidden" name="start" value="{start_value}">
                <input type="hidden" name="end" value="{end_value}">
                <input type="hidden" name="user_id" value="{user["id"]}">
                <input type="text" class="form-control form-control-sm" name="new_name" value="{html_escape(user["name"] or "")}" placeholder="新しい名前">
                <button type="submit" class="btn btn-sm btn-outline-primary">更新</button>
              </form>
            </div>
          </td>
        </tr>
        """
    if not inactive_user_table_rows:
        inactive_user_table_rows = """
        <tr>
          <td colspan="4" class="text-muted">無効ユーザーはいません。</td>
        </tr>
        """

    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shift Admin</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
  body {{
    background: #f5f7fb;
  }}
  .hero-card {{
    border: 0;
    box-shadow: 0 10px 30px rgba(0,0,0,.06);
    border-radius: 18px;
  }}
  .section-card {{
    border: 0;
    box-shadow: 0 8px 24px rgba(0,0,0,.05);
    border-radius: 18px;
  }}
  .summary-box {{
    border-radius: 16px;
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
    border: 1px solid rgba(0,0,0,.06);
    padding: 16px;
    height: 100%;
  }}
  .table thead th {{
    white-space: nowrap;
  }}
</style>
</head>
<body>
<div class="container py-4 py-md-5">

  <div class="card hero-card mb-4">
    <div class="card-body p-4 p-md-5">
      <div class="d-flex flex-column flex-md-row justify-content-between align-items-md-center gap-3">
        <div>
          <div class="text-uppercase small text-muted mb-2">Shift Management Dashboard</div>
          <h2 class="mb-1">シフト管理画面</h2>
          <div class="text-muted">提出状況、必要人数、不足状況をまとめて確認できます。</div>
        </div>
        <div class="d-flex gap-2">
          <a class="btn btn-success" href="/admin_export?start={start_value}&end={end_value}">Excel出力</a>
          <a class="btn btn-outline-secondary" href="/logout">ログアウト</a>
        </div>
      </div>
    </div>
  </div>

  <div class="row g-3 mb-4">
    <div class="col-md-4">
      <div class="summary-box">
        <div class="text-muted small">表示期間</div>
        <div class="fs-5 fw-semibold">{start_value} 〜 {end_value}</div>
      </div>
    </div>
    <div class="col-md-4">
      <div class="summary-box">
        <div class="text-muted small">対象日数</div>
        <div class="fs-5 fw-semibold">{(end_d - start_d).days + 1}日間</div>
      </div>
    </div>
    <div class="col-md-4">
      <div class="summary-box">
        <div class="text-muted small">機能</div>
        <div class="fs-6 fw-semibold">必要人数設定 / 不足確認 / Excel出力</div>
      </div>
    </div>
  </div>

  <div class="card section-card mb-4">
    <div class="card-body">
      <h5 class="card-title mb-3">表示期間</h5>
      <form method="GET" class="row g-3">
        <div class="col-md-4">
          <label class="form-label">開始日</label>
          <input type="date" class="form-control" name="start" value="{start_value}">
        </div>
        <div class="col-md-4">
          <label class="form-label">終了日</label>
          <input type="date" class="form-control" name="end" value="{end_value}">
        </div>
        <div class="col-md-2 d-flex align-items-end">
          <button type="submit" class="btn btn-dark w-100">表示</button>
        </div>
        <div class="col-md-2 d-flex align-items-end">
          <a class="btn btn-outline-dark w-100" href="/admin">今日から7日</a>
        </div>
      </form>
    </div>
  </div>

  <div class="card section-card mb-4">
    <div class="card-body">
      <div class="d-flex flex-column flex-md-row justify-content-between align-items-md-center gap-3 mb-3">
        <div>
          <h5 class="card-title mb-1">登録ユーザー一覧</h5>
          <div class="text-muted small">退職者などは無効化にすると、未提出人数などの運用対象から外れます。過去のシフト履歴は削除されません。</div>
        </div>
      </div>

      <div class="table-responsive">
        <table class="table table-striped align-middle">
          <thead>
            <tr>
              <th>名前</th>
              <th>line_user_id</th>
              <th>状態</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {active_user_table_rows}
          </tbody>
        </table>
      </div>

      <details class="mt-3">
        <summary class="fw-semibold">無効ユーザーを表示</summary>
        <div class="table-responsive mt-3">
          <table class="table table-striped align-middle mb-0">
            <thead>
              <tr>
                <th>名前</th>
                <th>line_user_id</th>
                <th>状態</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {inactive_user_table_rows}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  </div>

  <div class="card section-card mb-4">
    <div class="card-body">
      <div class="d-flex flex-column flex-md-row justify-content-between align-items-md-center gap-3 mb-3">
        <div>
          <h5 class="card-title mb-1">シフト提出期限</h5>
          <div class="text-muted small">固定日時方式と、シフト日の何日前かで締める相対期限方式を切り替えて設定できます。</div>
        </div>
        <div>{submission_status_badge}</div>
      </div>

      <div class="row g-3 mb-3">
        <div class="col-md-6">
          <div class="summary-box">
            <div class="text-muted small">現在有効な方式</div>
            <div class="fs-5 fw-semibold">{html_escape(submission_status_text)}</div>
            <div class="small text-muted mt-2">現在のルール: {html_escape(active_deadline_config["display"])}</div>
          </div>
        </div>
        <div class="col-md-6">
          <div class="summary-box">
            <div class="text-muted small">固定日時設定</div>
            <div class="fs-6 fw-semibold">{html_escape(submission_deadline_text)}</div>
            <div class="small text-muted mt-2">相対期限設定: {html_escape(format_relative_deadline(active_deadline_config["relative_days_before"], active_deadline_config["relative_time"]))}</div>
          </div>
        </div>
      </div>

      <form method="POST" action="/admin/update_submission_deadline" class="row g-3">
        <input type="hidden" name="csrf_token" value="{csrf_token_value}">
        <input type="hidden" name="start" value="{start_value}">
        <input type="hidden" name="end" value="{end_value}">
        <div class="col-12">
          <label class="form-label d-block mb-2">締切方式</label>
          <div class="d-flex flex-column flex-md-row gap-3">
            <div class="form-check">
              <input class="form-check-input" type="radio" name="deadline_mode" id="deadlineModeNone" value="" {"checked" if deadline_mode_value == "" else ""}>
              <label class="form-check-label" for="deadlineModeNone">未設定</label>
            </div>
            <div class="form-check">
              <input class="form-check-input" type="radio" name="deadline_mode" id="deadlineModeFixed" value="fixed" {"checked" if deadline_mode_value == "fixed" else ""}>
              <label class="form-check-label" for="deadlineModeFixed">固定日時方式</label>
            </div>
            <div class="form-check">
              <input class="form-check-input" type="radio" name="deadline_mode" id="deadlineModeRelative" value="relative" {"checked" if deadline_mode_value == "relative" else ""}>
              <label class="form-check-label" for="deadlineModeRelative">相対期限方式</label>
            </div>
          </div>
        </div>
        <div class="col-md-4">
          <label class="form-label">固定日時の締切</label>
          <input type="datetime-local" class="form-control" name="submission_deadline" value="{submission_deadline_value}">
          <div class="form-text">固定日時方式で使う締切です。</div>
        </div>
        <div class="col-md-3">
          <label class="form-label">何日前</label>
          <input type="number" class="form-control" name="deadline_days_before" min="0" value="{deadline_days_before_value}">
          <div class="form-text">相対期限方式で使います。</div>
        </div>
        <div class="col-md-2">
          <label class="form-label">締切時刻</label>
          <input type="time" class="form-control" name="deadline_time" value="{deadline_time_value}">
          <div class="form-text">例: 23:59</div>
        </div>
        <div class="col-md-3 d-flex align-items-end">
          <button type="submit" class="btn btn-primary w-100">提出期限を保存</button>
        </div>
        <div class="col-12">
          <div class="form-text">
            固定日時方式は全日共通の締切です。相対期限方式は「各シフト日のN日前 HH:MM」を締切として自動判定します。
          </div>
        </div>
      </form>
    </div>
  </div>

  <form method="POST" action="/admin/update_required">
    <input type="hidden" name="csrf_token" value="{csrf_token_value}">
    <input type="hidden" name="start" value="{start_value}">
    <input type="hidden" name="end" value="{end_value}">

    <div class="card section-card">
      <div class="card-body">
        <div class="d-flex flex-column flex-md-row justify-content-between align-items-md-center gap-3 mb-3">
          <div>
            <h5 class="card-title mb-1">提出一覧・必要人数設定</h5>
            <div class="text-muted small">必要人数を日ごとに入力して保存できます。必要人数に対して出勤予定人数が足りない日は自動で不足表示になります。</div>
          </div>
          <button type="submit" class="btn btn-primary">必要人数を保存</button>
        </div>

        <div class="table-responsive">
          <table class="table table-striped align-middle">
            <thead>
              <tr>
                <th>日付</th>
                <th>必要人数</th>
                <th>状況</th>
                <th>提出一覧</th>
              </tr>
            </thead>
            <tbody>
              {table_rows}
            </tbody>
          </table>
        </div>

        <div class="mt-3">
          <button type="submit" class="btn btn-primary">必要人数を保存</button>
        </div>
      </div>
    </div>
  </form>

</div>
</body>
</html>
"""

@admin_bp.route("/export", methods=["GET"])
@admin_bp.route("/admin_export", methods=["GET"])
def admin_export():
    if not session.get("logged_in"):
        return redirect("/login")

    start_d = parse_ymd(request.args.get("start"))
    end_d = parse_ymd(request.args.get("end"))
    if not start_d or not end_d:
        return "start / end が不正です", 400
    if start_d > end_d:
        return "start は end 以下で指定してください", 400

    rows = get_entries_range(to_ymd(start_d), to_ymd(end_d))
    required_map = get_required_staff_range(to_ymd(start_d), to_ymd(end_d))
    export_days = list(daterange_inclusive(start_d, end_d))

    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("SELECT name FROM users WHERE active=1 ORDER BY name")
        user_names = [r["name"] for r in c.fetchall()]
    finally:
        conn.close()

    entry_map = {}
    for r in rows:
        if int(r["active"]) != 1:
            continue
        key = (r["name"], r["date"])
        if int(r["off"]) == 1:
            entry_map[key] = "休"
        elif r["start_time"] and r["end_time"]:
            entry_map[key] = f'{r["start_time"]}-{r["end_time"]}'
        else:
            entry_map[key] = ""

    wb = Workbook()
    ws = wb.active
    ws.title = "シフト表"

    thin_side = Side(style="thin", color="B8C2CF")
    border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    center = Alignment(horizontal="center", vertical="center")
    left = Alignment(horizontal="left", vertical="center")
    cell_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True, shrink_to_fit=True)
    title_font = Font(size=16, bold=True)
    header_font = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="E8EEF7")
    saturday_fill = PatternFill("solid", fgColor="DDEEFE")
    sunday_fill = PatternFill("solid", fgColor="F7E4DE")
    name_fill = PatternFill("solid", fgColor="F8FAFC")

    ws["A1"] = f"シフト表（{to_ymd(start_d)}〜{to_ymd(end_d)}）"
    ws["B1"] = ""
    ws["A1"].font = title_font
    ws["B1"].font = title_font

    ws["A4"] = "スタッフ"
    ws["A5"] = ""
    for row_idx in (4, 5):
        cell = ws.cell(row=row_idx, column=1)
        cell.alignment = center
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border

    weekday_labels = ["月", "火", "水", "木", "金", "土", "日"]

    for idx, current_date in enumerate(export_days, start=1):
        col = idx + 1
        weekday = current_date.weekday()
        fill = header_fill
        if weekday == 5:
            fill = saturday_fill
        elif weekday == 6:
            fill = sunday_fill

        ws.cell(row=4, column=col, value=current_date.day)
        ws.cell(row=5, column=col, value=weekday_labels[weekday])

        for row_idx in (4, 5):
            cell = ws.cell(row=row_idx, column=col)
            cell.alignment = center
            cell.font = header_font
            cell.fill = fill
            cell.border = border

    start_row = 6
    for idx, name in enumerate(user_names):
        row_num = start_row + idx
        name_cell = ws.cell(row=row_num, column=1, value=name)
        name_cell.alignment = left
        name_cell.font = Font(bold=True)
        name_cell.fill = name_fill
        name_cell.border = border

        for idx, current_date in enumerate(export_days, start=1):
            ymd = to_ymd(current_date)
            value = entry_map.get((name, ymd), "")
            cell = ws.cell(row=row_num, column=idx + 1, value=value)
            cell.alignment = cell_alignment
            cell.border = border

            weekday = current_date.weekday()
            if weekday == 5:
                cell.fill = saturday_fill
            elif weekday == 6:
                cell.fill = sunday_fill

    ws.freeze_panes = "B6"
    ws.column_dimensions["A"].width = 18
    for idx, _ in enumerate(export_days, start=1):
        ws.column_dimensions[get_column_letter(idx + 1)].width = 11

    ws.row_dimensions[1].height = 24
    ws.row_dimensions[4].height = 24
    ws.row_dimensions[5].height = 22
    for row_num in range(start_row, start_row + max(len(user_names), 1)):
        ws.row_dimensions[row_num].height = 28

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    return send_file(
        stream,
        as_attachment=True,
        download_name=f"shift_{to_ymd(start_d)}_{to_ymd(end_d)}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

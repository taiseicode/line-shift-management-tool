from flask import Blueprint, request, make_response

from config import LIFF_ID
from services.deadline_service import get_active_deadline_config
from utils import parse_ymd, to_ymd, html_escape, today_jst


liff_bp = Blueprint("liff", __name__)


@liff_bp.route("/liff/submit", methods=["GET"])
def liff_submit():
    if not LIFF_ID:
        return "LIFF_ID が .env に設定されていません", 500

    today = today_jst()
    start_value = request.args.get("start", "").strip()
    start_d = parse_ymd(start_value) or today
    start_value = to_ymd(start_d)

    active_config = get_active_deadline_config()
    rule_text = active_config["display"] if active_config["is_configured"] else "未設定"

    if active_config["is_configured"]:
        submission_message_html = f'<div class="alert alert-warning py-2 small mb-3">提出期限：{html_escape(rule_text)}</div>'
    else:
        submission_message_html = '<div class="alert alert-success py-2 small mb-3">現在はいつでも提出できます。</div>'


    response = make_response(f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate, max-age=0"/>
  <meta http-equiv="Pragma" content="no-cache"/>
  <meta http-equiv="Expires" content="0"/>
  <title>シフト提出</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <script src="https://static.line-scdn.net/liff/edge/2/sdk.js"></script>
  <style>
    :root {{
      --app-bg: #f5f7fb;
      --panel-bg: #ffffff;
      --panel-border: rgba(15, 23, 42, 0.08);
      --panel-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
      --text-main: #18212f;
      --text-sub: #69768a;
      --line-soft: rgba(96, 112, 134, 0.18);
      --brand: #2f6fdd;
      --brand-soft: rgba(47, 111, 221, 0.10);
      --off-soft: rgba(100, 116, 139, 0.14);
      --danger-soft: rgba(209, 67, 67, 0.09);
      --radius-xl: 18px;
      --radius-lg: 14px;
      --radius-md: 10px;
    }}
    body {{
      background: var(--app-bg);
      color: var(--text-main);
      min-height: 100vh;
      font-size: 0.94rem;
    }}
    .liff-shell {{
      max-width: 720px;
    }}
    .hero-panel,
    .guide-card,
    .modal-content {{
      background: var(--panel-bg);
      border: 1px solid var(--panel-border);
      box-shadow: var(--panel-shadow);
    }}
    .hero-panel {{
      border-radius: var(--radius-xl);
      padding: 16px;
      margin-bottom: 12px;
    }}
    .hero-eyebrow {{
      display: none;
    }}
    .hero-title {{
      font-size: 1.22rem;
      font-weight: 800;
      margin: 0;
      letter-spacing: 0;
    }}
    .hero-sub,
    .range-text,
    .section-note {{
      color: var(--text-sub);
    }}
    .hero-sub {{
      font-size: 0.86rem;
      line-height: 1.45;
      margin-top: 5px;
      margin-bottom: 0;
    }}
    .staff-name {{
      color: var(--text-sub);
      font-size: 0.78rem;
      margin-top: 6px;
    }}
    .range-text {{
      font-size: 0.86rem;
      font-weight: 700;
      margin-top: 8px;
    }}
    .top-action,
    .week-nav .btn {{
      min-height: 40px;
      border-radius: 12px;
      font-weight: 600;
      border-width: 1px;
    }}
    .top-action {{
      min-width: 42px;
      min-height: 36px;
      padding: 0 12px;
    }}
    .week-nav {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 12px;
    }}
    .guide-card {{
      border-radius: var(--radius-lg);
      padding: 12px 13px;
      margin-bottom: 10px;
    }}
    .guide-title {{
      font-size: 0.88rem;
      font-weight: 800;
      margin-bottom: 3px;
    }}
    .submission-wrap .alert {{
      border: 0;
      border-radius: 12px;
      padding: 9px 11px;
      box-shadow: none;
      font-size: 0.82rem;
    }}
    .shift-list {{
      display: grid;
      gap: 9px;
    }}
    .shift-card {{
      width: 100%;
      border: 1px solid var(--panel-border);
      border-radius: var(--radius-lg);
      background: #fff;
      box-shadow: var(--panel-shadow);
      padding: 0;
      overflow: hidden;
    }}
    .shift-card:disabled {{
      cursor: not-allowed;
    }}
    .shift-card:not(:disabled):active {{
      transform: scale(0.995);
    }}
    .shift-card:not(:disabled):hover {{
      border-color: rgba(47, 111, 221, 0.24);
    }}
    .shift-card-inner {{
      padding: 12px 13px;
      text-align: left;
    }}
    .shift-card-header {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 8px;
    }}
    .shift-date {{
      font-size: 0.98rem;
      font-weight: 800;
      letter-spacing: 0;
      color: var(--text-main);
    }}
    .shift-date-sub {{
      font-size: 0.72rem;
      color: var(--text-sub);
      margin-top: 1px;
    }}
    .shift-status-tag {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 58px;
      min-height: 24px;
      padding: 0 9px;
      border-radius: 999px;
      font-size: 0.7rem;
      font-weight: 700;
      border: 1px solid transparent;
      flex-shrink: 0;
    }}
    .tag-empty {{
      color: #475569;
      background: rgba(148, 163, 184, 0.14);
      border-color: rgba(148, 163, 184, 0.2);
    }}
    .tag-off {{
      color: #556274;
      background: var(--off-soft);
      border-color: rgba(100, 116, 139, 0.2);
    }}
    .tag-work {{
      color: #1554b7;
      background: var(--brand-soft);
      border-color: rgba(47, 111, 221, 0.16);
    }}
    .tag-closed {{
      color: #9f2d2d;
      background: var(--danger-soft);
      border-color: rgba(209, 67, 67, 0.18);
    }}
    .shift-user-row {{
      display: none;
    }}
    .shift-state {{
      border-radius: 12px;
      padding: 9px 10px;
      border: 1px solid transparent;
    }}
    .state-empty {{
      background: rgba(148, 163, 184, 0.10);
      border-color: rgba(148, 163, 184, 0.16);
    }}
    .state-off {{
      background: var(--off-soft);
      border-color: rgba(100, 116, 139, 0.18);
    }}
    .state-work {{
      background: var(--brand-soft);
      border-color: rgba(31, 94, 255, 0.18);
    }}
    .state-closed {{
      background: linear-gradient(180deg, rgba(209, 67, 67, 0.10), rgba(209, 67, 67, 0.06));
      border-color: rgba(209, 67, 67, 0.18);
    }}
    .shift-state-label {{
      display: block;
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0;
      margin-bottom: 2px;
    }}
    .shift-state-detail {{
      font-size: 0.88rem;
      font-weight: 700;
      letter-spacing: 0;
    }}
    .deadline-note {{
      display: inline-flex;
      align-items: center;
      margin-top: 8px;
      font-size: 0.72rem;
      line-height: 1.35;
      padding: 4px 8px;
      border-radius: 999px;
      border: 1px solid transparent;
    }}
    .note-open {{
      color: #5b687a;
      background: rgba(148, 163, 184, 0.09);
      border-color: rgba(148, 163, 184, 0.14);
    }}
    .note-closed {{
      color: #a33434;
      background: rgba(209, 67, 67, 0.09);
      border-color: rgba(209, 67, 67, 0.16);
    }}
    .shift-closed {{
      opacity: 0.62;
      box-shadow: none;
    }}
    .modal-dialog {{
      padding: 12px;
    }}
    .modal-content {{
      border-radius: 24px;
      overflow: hidden;
    }}
    .modal-header,
    .modal-body {{
      padding-left: 20px;
      padding-right: 20px;
    }}
    .modal-header {{
      padding-top: 20px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--line-soft);
    }}
    .modal-body {{
      padding-top: 18px;
      padding-bottom: 20px;
    }}
    .modal-title {{
      font-size: 1.12rem;
      font-weight: 700;
    }}
    .btn-group > .btn {{
      min-height: 42px;
      font-weight: 600;
    }}
    .form-select,
    .form-control {{
      min-height: 42px;
      border-radius: 12px;
      border-color: rgba(96, 112, 134, 0.22);
    }}
    .action-row {{
      display: flex;
      gap: 8px;
      margin-top: 14px;
    }}
    .action-row .btn {{
      min-height: 42px;
      border-radius: 12px;
      font-weight: 700;
    }}
    .liff-tabs {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
      margin: 0 0 10px;
    }}
    .liff-tab-btn {{
      min-height: 38px;
      border-radius: 12px;
      border: 1px solid rgba(96, 112, 134, 0.22);
      background: rgba(255, 255, 255, 0.88);
      color: var(--text-sub);
      font-weight: 700;
      font-size: 0.86rem;
    }}
    .liff-tab-btn.active {{
      color: #fff;
      background: var(--brand);
      border-color: var(--brand);
      box-shadow: none;
    }}
    .tab-panel[hidden] {{ display: none !important; }}
    .confirmed-list {{ display: grid; gap: 10px; }}
    .confirmed-card {{
      border: 1px solid rgba(96, 112, 134, 0.14);
      border-radius: 12px;
      background: rgba(248, 250, 252, 0.9);
      padding: 10px 11px;
    }}
    .confirmed-card.confirmed {{
      background: rgba(34, 197, 94, 0.10);
      border-color: rgba(34, 197, 94, 0.22);
    }}
    .confirmed-date {{ font-weight: 700; color: var(--text-main); }}
    .confirmed-time {{ font-size: 1.05rem; font-weight: 700; margin-top: 4px; }}
    .confirmed-badge {{
      display: inline-flex;
      align-items: center;
      min-height: 26px;
      padding: 0 10px;
      border-radius: 999px;
      font-size: 0.74rem;
      font-weight: 700;
      color: #087f3f;
      background: rgba(34, 197, 94, 0.18);
    }}
    .pay-summary-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 10px;
    }}
    .pay-summary-item {{
      border: 1px solid rgba(96, 112, 134, 0.14);
      border-radius: 12px;
      background: rgba(248, 250, 252, 0.88);
      padding: 8px 10px;
    }}
    .pay-summary-label {{
      font-size: 0.74rem;
      color: var(--text-sub);
      font-weight: 700;
      margin-bottom: 3px;
    }}
    .pay-summary-value {{ font-size: 0.98rem; font-weight: 700; }}
    .pay-amount {{ font-size: 1.75rem; font-weight: 800; letter-spacing: 0; }}
    @media (max-width: 575.98px) {{
      .hero-panel {{
        padding: 18px 16px 16px;
      }}
      .hero-title {{
        font-size: 1.34rem;
      }}
      .shift-card-inner {{
        padding: 15px 14px 14px;
      }}
      .shift-status-tag {{
        min-width: 64px;
        padding: 0 10px;
      }}
      .modal-header,
      .modal-body {{
        padding-left: 16px;
        padding-right: 16px;
      }}
    }}
  </style>
</head>
<body>
<div class="container liff-shell py-3 py-md-4">
  <div class="hero-panel">
    <div class="d-flex align-items-start justify-content-between gap-3">
      <div class="flex-grow-1">
        <div class="hero-eyebrow"></div>
        <h4 class="hero-title">今週のシフト</h4>
        <p class="hero-sub">出勤できる日と時間を入力してください</p>
        <div class="staff-name" id="staffNameText"></div>
        <div class="range-text" id="rangeText"></div>
      </div>
      <button id="btnClose" class="btn btn-outline-secondary top-action" aria-label="閉じる">×</button>
    </div>
    <div class="week-nav">
      <button type="button" id="btnPrevWeek" class="btn btn-outline-secondary">前の週</button>
      <button type="button" id="btnNextWeek" class="btn btn-primary">次の週</button>
    </div>
  </div>

  <div class="liff-tabs" role="tablist" aria-label="表示切り替え">
    <button type="button" id="tabSubmit" class="liff-tab-btn active" role="tab" aria-selected="true">シフト提出</button>
    <button type="button" id="tabConfirmed" class="liff-tab-btn" role="tab" aria-selected="false">確定シフト</button>
  </div>

  <div id="submitTabPanel" class="tab-panel">
    <div class="guide-card">
      <div class="section-note small">出勤できる日を選び、時間を入力してください。</div>
    </div>
    <div class="submission-wrap mb-3">{submission_message_html}</div>
    <div id="list" class="shift-list"></div>
  </div>

  <div id="confirmedTabPanel" class="tab-panel" hidden>
    <div class="guide-card">
      <div class="guide-title">次回勤務</div>
      <div id="nextConfirmedShift" class="section-note small">読み込み中...</div>
    </div>
    <div class="guide-card">
      <div class="d-flex align-items-start justify-content-between gap-2">
        <div>
          <div class="guide-title">今月の見込み給料</div>
          <div id="paySummaryMonth" class="section-note small"></div>
        </div>
        <button type="button" id="btnOpenPaySettings" class="btn btn-outline-primary btn-sm">給与設定を変更</button>
      </div>
      <div id="paySummaryMessage" class="section-note small mt-2"></div>
      <div id="paySummaryAmount" class="pay-amount mt-2"></div>
      <div id="paySummaryGrid" class="pay-summary-grid"></div>
      <div class="week-nav mt-3">
        <button type="button" id="btnPayPrevMonth" class="btn btn-outline-secondary">前月</button>
        <button type="button" id="btnPayNextMonth" class="btn btn-outline-secondary">翌月</button>
      </div>
    </div>
    <div class="guide-card">
      <div class="guide-title">今週の確定シフト</div>
      <div id="confirmedThisWeekList" class="confirmed-list"></div>
    </div>
    <div class="guide-card">
      <div class="guide-title">勤務履歴</div>
      <div id="confirmedHistoryRange" class="section-note small mb-2"></div>
      <div class="week-nav mb-3">
        <button type="button" id="btnConfirmedHistoryPrev" class="btn btn-outline-secondary">前の週</button>
        <button type="button" id="btnConfirmedHistoryNext" class="btn btn-outline-secondary">次の週</button>
      </div>
      <div id="confirmedHistoryList" class="confirmed-list"></div>
    </div>
  </div>
</div>

<div class="modal fade" id="paySettingsModal" tabindex="-1" aria-hidden="true">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content border-0 shadow">
      <div class="modal-header">
        <div>
          <h5 class="modal-title mb-0">給与設定</h5>
          <div class="small text-muted">見込み給料の計算に使います</div>
        </div>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>
      <div class="modal-body">
        <label class="form-label">基本時給</label>
        <input id="payHourlyWage" class="form-control mb-3" type="number" min="1" step="1" inputmode="numeric" placeholder="例: 1210">
        <label class="form-label">休憩ルール</label>
        <select id="payBreakRule" class="form-select mb-3">
          <option value="none">休憩なし</option>
          <option value="legal_jp">法定休憩</option>
        </select>
        <div class="form-text mb-3">法定休憩: 6時間超45分・8時間超60分</div>
        <div class="form-check form-switch mb-2">
          <input class="form-check-input" type="checkbox" role="switch" id="payNightEnabled">
          <label class="form-check-label" for="payNightEnabled">深夜手当 ON</label>
        </div>
        <div class="form-check form-switch mb-3">
          <input class="form-check-input" type="checkbox" role="switch" id="payOvertimeEnabled">
          <label class="form-check-label" for="payOvertimeEnabled">8時間超過手当 ON</label>
        </div>
        <div class="action-row">
          <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">閉じる</button>
          <button type="button" id="btnSavePaySettings" class="btn btn-primary flex-grow-1">保存</button>
        </div>
        <div class="small text-danger mt-2" id="paySettingsError" style="display:none;"></div>
      </div>
    </div>
  </div>
</div>

<!-- Modal -->
<div class="modal fade" id="editModal" tabindex="-1" aria-hidden="true">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content border-0 shadow">
      <div class="modal-header">
        <div>
          <h5 class="modal-title mb-0" id="modalTitle">入力</h5>
          <div class="small text-muted" id="modalSub"></div>
          <div class="small text-muted" id="modalDeadlineText"></div>
        </div>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>

      <div class="modal-body">
        <div class="btn-group w-100 mb-3" role="group" aria-label="mode">
          <input type="radio" class="btn-check" name="mode" id="modeWork" autocomplete="off" checked>
          <label class="btn btn-outline-primary" for="modeWork">出勤</label>

          <input type="radio" class="btn-check" name="mode" id="modeOff" autocomplete="off">
          <label class="btn btn-outline-secondary" for="modeOff">休み</label>
        </div>

        <div id="timeBox">
          <div class="row g-2">
            <div class="col-6">
              <label class="form-label">開始</label>
              <select id="startTime" class="form-select"></select>
            </div>
            <div class="col-6">
              <label class="form-label">終了</label>
              <select id="endTime" class="form-select"></select>
            </div>
          </div>
          <div class="form-text mt-2">
            ※15分刻み。日をまたぐ勤務も入力できます。
          </div>
        </div>

        <div class="action-row">
          <button id="btnDelete" class="btn btn-outline-danger">この日の入力を削除</button>
          <button id="btnSave" class="btn btn-primary flex-grow-1">保存</button>
        </div>

        <div class="small text-danger mt-2" id="errText" style="display:none;"></div>
      </div>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
<script>
const LIFF_ID = {LIFF_ID!r};
const START = {start_value!r};
const API_BASE_URL = {request.host_url.rstrip("/")!r};

let LINE_USER_ID = "";
let ID_TOKEN = "";
let DISPLAY_NAME = "";
let entries = {{}};
let deadlineStatuses = {{}};
let currentWeekStart = "";
let currentDate = "";
let isLoadingWeek = false;
let activeTab = "submit";
let confirmedShifts = [];
let confirmedAllShifts = [];
let confirmedHistoryWeekStart = "";
let paySummaryMonth = "";
let paySettings = null;
let paySummary = null;
let paySummaryCache = {{}};
let paySummaryCacheToken = 0;
let paySummaryRequestId = 0;
let modal = null;
let paySettingsModal = null;

function debugLog(message, extra = null) {{
}}


function apiUrl(path) {{
  const finalUrl = String(path || "");
  return finalUrl;
}}

function absoluteApiUrl(path) {{
  const finalUrl = new URL(String(path || ""), window.location.origin).toString();
  return finalUrl;
}}

function buildWeekApiUrl(normalizedStart) {{
  const href = window.location.href;
  const origin = window.location.origin;
  try {{
    const finalFetchUrl = `/api/my_week?start=${{encodeURIComponent(normalizedStart)}}`;
    debugLog("週API URL生成", {{
      href,
      origin,
      apiBaseUrl: API_BASE_URL,
      finalFetchUrl,
      sameOrigin: true
    }});
    return finalFetchUrl;
  }} catch (urlError) {{
    debugLog("週API URL生成失敗", {{
      href,
      origin,
      name: urlError && urlError.name ? urlError.name : "UnknownError",
      message: urlError && urlError.message ? urlError.message : String(urlError)
    }});
    throw urlError;
  }}
}}

function pad2(n) {{
  return String(n).padStart(2, "0");
}}

function parseYmdParts(ymd) {{
  const m = /^(\\d{{4}})-(\\d{{2}})-(\\d{{2}})$/.exec(String(ymd || "").trim());
  if (!m) return null;

  const year = Number(m[1]);
  const month = Number(m[2]);
  const day = Number(m[3]);

  if (!year || month < 1 || month > 12 || day < 1 || day > 31) return null;
  return {{ year, month, day }};
}}

function ymdToDateLocal(ymd) {{
  const parts = parseYmdParts(ymd);
  if (!parts) return null;
  return new Date(parts.year, parts.month - 1, parts.day);
}}

function dateToYmdLocal(dateObj) {{
  return `${{dateObj.getFullYear()}}-${{pad2(dateObj.getMonth() + 1)}}-${{pad2(dateObj.getDate())}}`;
}}

function ymdToSlash(ymd) {{
  return String(ymd || "").replaceAll("-", "/");
}}

function normalizeWeekStart(startYmd) {{
  const dateObj = ymdToDateLocal(startYmd);
  if (!dateObj) return "";
  return dateToYmdLocal(dateObj);
}}

function getSundayOfWeek(dateObj) {{
  const d = new Date(dateObj);
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - d.getDay());
  return d;
}}

function normalizeWeekStartToSunday(startYmd) {{
  const dateObj = ymdToDateLocal(startYmd);
  if (!dateObj) return "";
  return dateToYmdLocal(getSundayOfWeek(dateObj));
}}

function todayYmd() {{
  return dateToYmdLocal(new Date());
}}

function isPastDateYmd(ymd) {{
  const normalized = normalizeWeekStart(ymd);
  return !!normalized && normalized < todayYmd();
}}

function addDaysToYmd(ymd, days) {{
  const normalized = normalizeWeekStart(ymd);
  if (!normalized) return "";
  const dateObj = ymdToDateLocal(normalized);
  if (!dateObj) return "";
  dateObj.setDate(dateObj.getDate() + Number(days || 0));
  return dateToYmdLocal(dateObj);
}}

function getWeekDates(startYmd) {{
  const normalizedStart = normalizeWeekStart(startYmd);
  if (!normalizedStart) return [];
  const dates = [];
  for (let i = 0; i < 7; i += 1) {{
    const ymd = addDaysToYmd(normalizedStart, i);
    if (!ymd) return [];
    dates.push(ymd);
  }}
  return dates;
}}

function ymdToLabel(ymd) {{
  const d = ymdToDateLocal(ymd);
  if (!d) return ymd;
  const w = ["日", "月", "火", "水", "木", "金", "土"][d.getDay()];
  return `${{d.getMonth() + 1}}/${{d.getDate()}}(${{w}})`;
}}

function buildTimes(stepMin = 15) {{
  const arr = [];
  for (let h = 0; h < 24; h += 1) {{
    for (let m = 0; m < 60; m += stepMin) {{
      arr.push(`${{pad2(h)}}:${{pad2(m)}}`);
    }}
  }}
  return arr;
}}

function minutes(hhmm) {{
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}}

function getEntryStateMeta(entry, status) {{
  if (status && status.is_closed) {{
    return {{
      tagClass: "tag-closed",
      tagText: "締切済",
      stateClass: "state-closed",
      label: "変更不可",
      detail: "受付終了"
    }};
  }}
  if (!entry) {{
    return {{
      tagClass: "tag-empty",
      tagText: "未入力",
      stateClass: "state-empty",
      label: "未入力",
      detail: "出勤または休みを選択"
    }};
  }}
  if (entry.off) {{
    return {{
      tagClass: "tag-off",
      tagText: "休み",
      stateClass: "state-off",
      label: "休み",
      detail: "提出済み"
    }};
  }}
  return {{
    tagClass: "tag-work",
    tagText: "出勤",
    stateClass: "state-work",
    label: "出勤",
    detail: `${{entry.start_time}} - ${{entry.end_time}}`
  }};
}}

function statusTagHtml(entry, status) {{
  const meta = getEntryStateMeta(entry, status);
  return `<span class="shift-status-tag ${{meta.tagClass}}">${{meta.tagText}}</span>`;
}}

function badgeHtml(entry, status) {{
  const meta = getEntryStateMeta(entry, status);
  return `
    <div class="shift-state ${{meta.stateClass}}">
      <span class="shift-state-label">${{meta.label}}</span>
      <div class="shift-state-detail">${{meta.detail}}</div>
    </div>
  `;
}}

function deadlineStatusHtml(status) {{
  if (!status) return "";
  if (status.is_closed) {{
    return `<div class="deadline-note note-closed">締切済</div>`;
  }}
  if (status.deadline_display) {{
    return `<div class="deadline-note note-open">締切: ${{status.deadline_display}}</div>`;
  }}
  return `<div class="deadline-note note-open">提出可能</div>`;
}}

function availabilityNoteHtml(ymd, status) {{
  if (isPastDateYmd(ymd)) {{
    return `<div class="deadline-note note-closed">変更不可</div>`;
  }}
  return deadlineStatusHtml(status);
}}

function setError(msg) {{
  const el = document.getElementById("errText");
  if (!el) return;

  if (!msg) {{
    el.style.display = "none";
    el.textContent = "";
    return;
  }}

  el.style.display = "block";
  el.textContent = msg;
}}

function fillSelectOptions(select, times) {{
  select.innerHTML = "";
  for (const t of times) {{
    const opt = document.createElement("option");
    opt.value = t;
    opt.textContent = t;
    select.appendChild(opt);
  }}
}}

function getDeadlineStatus(ymd) {{
  return deadlineStatuses[ymd] || null;
}}

function shiftWeek(startYmd, diffWeeks) {{
  const normalizedStart = normalizeWeekStartToSunday(startYmd);
  if (!normalizedStart) {{
    console.error("shiftWeek invalid start", {{ startYmd, diffWeeks }});
    return "";
  }}
  return addDaysToYmd(normalizedStart, Number(diffWeeks || 0) * 7);
}}

function updateWeekNav() {{
  const prevBtn = document.getElementById("btnPrevWeek");
  const nextBtn = document.getElementById("btnNextWeek");
  if (!prevBtn || !nextBtn) return;

  prevBtn.disabled = isLoadingWeek;
  nextBtn.disabled = isLoadingWeek;
  prevBtn.textContent = "前の週";
  nextBtn.textContent = isLoadingWeek ? "読み込み中..." : "次の週";
}}

function renderWeek(startYmd) {{
  const normalizedStart = normalizeWeekStartToSunday(startYmd);
  const weekDates = getWeekDates(normalizedStart);
  const list = document.getElementById("list");
  const rangeText = document.getElementById("rangeText");

  if (!list || !rangeText) return;

  list.innerHTML = "";

  if (!normalizedStart || weekDates.length !== 7) {{
    console.error("renderWeek invalid dates", {{ startYmd, normalizedStart, weekDates }});
    rangeText.textContent = "週の日付形式が不正です";
    updateWeekNav();
    return;
  }}

  rangeText.textContent = `${{ymdToSlash(weekDates[0])}} - ${{ymdToSlash(weekDates[6])}}`;

  for (const ymd of weekDates) {{
    const entry = entries[ymd] || null;
    const status = getDeadlineStatus(ymd);
    const isPast = isPastDateYmd(ymd);

    const card = document.createElement("button");
    card.type = "button";
    card.className = "shift-card text-start";
    card.dataset.date = ymd;
    card.onclick = () => openModal(card.dataset.date);

    if (isPast || (status && status.is_closed)) {{
      card.disabled = true;
      card.classList.add("shift-closed");
    }}

    card.innerHTML = `
      <div class="shift-card-inner">
        <div class="shift-card-header">
          <div>
            <div class="shift-date">${{ymdToLabel(ymd)}}</div>
            <div class="shift-date-sub">${{ymdToSlash(ymd)}}</div>
          </div>
          ${{statusTagHtml(entry, status)}}
        </div>
        ${{badgeHtml(entry, status)}}
        ${{availabilityNoteHtml(ymd, status)}}
      </div>
    `;
    list.appendChild(card);
  }}

  updateWeekNav();
}}

function setActiveTab(tabName) {{
  activeTab = tabName === "confirmed" ? "confirmed" : "submit";
  const isConfirmed = activeTab === "confirmed";
  document.getElementById("tabSubmit").classList.toggle("active", !isConfirmed);
  document.getElementById("tabConfirmed").classList.toggle("active", isConfirmed);
  document.getElementById("tabSubmit").setAttribute("aria-selected", isConfirmed ? "false" : "true");
  document.getElementById("tabConfirmed").setAttribute("aria-selected", isConfirmed ? "true" : "false");
  document.getElementById("submitTabPanel").hidden = isConfirmed;
  document.getElementById("confirmedTabPanel").hidden = !isConfirmed;
}}

function confirmedRange() {{
  const start = normalizeWeekStartToSunday(currentWeekStart) || normalizeWeekStartToSunday(START) || dateToYmdLocal(getSundayOfWeek(new Date()));
  return {{ start, end: addDaysToYmd(start, 13) }};
}}

function updateStaffNameText() {{
  const el = document.getElementById("staffNameText");
  if (!el) return;
  const name = DISPLAY_NAME && DISPLAY_NAME !== "未設定" && DISPLAY_NAME !== "読み込み中..." ? DISPLAY_NAME : "";
  el.textContent = name ? `${{name}}さんのシフト` : "";
}}

function currentConfirmedWeekStart() {{
  return normalizeWeekStartToSunday(currentWeekStart) || normalizeWeekStartToSunday(START) || dateToYmdLocal(getSundayOfWeek(new Date()));
}}

function resetConfirmedHistoryWeek() {{
  confirmedHistoryWeekStart = addDaysToYmd(currentConfirmedWeekStart(), -7);
}}

function normalizeConfirmedShiftItem(item) {{
  const startTime = item && (item.start_time || item.confirmed_start_time || item.raw_start_time || "");
  const endTime = item && (item.end_time || item.confirmed_end_time || item.raw_end_time || "");
  return {{ ...(item || {{}}), status: "confirmed", start_time: startTime, end_time: endTime }};
}}

function renderConfirmedCard(item) {{
  return `
    <div class="confirmed-card confirmed">
      <div class="d-flex align-items-start justify-content-between gap-2">
        <div>
          <div class="confirmed-date">${{ymdToLabel(item.date)}}</div>
          <div class="small text-muted">${{item.date}}</div>
        </div>
        <span class="confirmed-badge">確定</span>
      </div>
      <div class="confirmed-time">${{item.start_time}} - ${{item.end_time}}</div>
    </div>
  `;
}}

function renderConfirmedList(element, rows, emptyMessage) {{
  if (!element) return;
  element.innerHTML = rows.length ? rows.map(renderConfirmedCard).join("") : `<div class="section-note small">${{emptyMessage}}</div>`;
}}

function setConfirmedLoading(message) {{
  document.getElementById("nextConfirmedShift").textContent = message;
  document.getElementById("confirmedThisWeekList").innerHTML = "";
  document.getElementById("confirmedHistoryRange").textContent = "";
  document.getElementById("confirmedHistoryList").innerHTML = "";
}}

function unwrapConfirmedPayload(data) {{
  if (data && data.payload && typeof data.payload === "object") return data.payload;
  if (data && data.data && typeof data.data === "object") return data.data;
  return data || {{}};
}}

function confirmedRowsFromPayload(payload, keyName) {{
  if (Array.isArray(payload)) return payload;
  if (!payload || typeof payload !== "object") return [];
  if (Array.isArray(payload[keyName])) return payload[keyName];
  return [];
}}

function renderConfirmedHistory() {{
  if (!confirmedHistoryWeekStart) resetConfirmedHistoryWeek();
  const start = confirmedHistoryWeekStart;
  const end = addDaysToYmd(start, 6);
  const todayYmd = dateToYmdLocal(new Date());
  document.getElementById("confirmedHistoryRange").textContent = `${{start}} - ${{end}}`;
  const historyRows = confirmedAllShifts
    .filter(item => item.date >= start && item.date <= end && item.date < todayYmd)
    .sort((a, b) => a.date.localeCompare(b.date));
  renderConfirmedList(document.getElementById("confirmedHistoryList"), historyRows, "この週の勤務履歴はありません");
  const nextStart = addDaysToYmd(start, 7);
  document.getElementById("btnConfirmedHistoryNext").disabled = !nextStart || nextStart >= todayYmd;
}}

function renderConfirmedShifts(data) {{
  const payload = unwrapConfirmedPayload(data);
  const confirmedRows = confirmedRowsFromPayload(payload, "confirmed_shifts");
  const shiftRows = confirmedRowsFromPayload(payload, "shifts");
  const primaryRows = confirmedRows.length ? confirmedRows : shiftRows;
  const upcomingRows = confirmedRowsFromPayload(payload, "upcoming_shifts");
  const allRows = confirmedRowsFromPayload(payload, "all_shifts");
  confirmedShifts = primaryRows.map(normalizeConfirmedShiftItem).filter(item => item.start_time && item.end_time);
  const upcomingShifts = upcomingRows.map(normalizeConfirmedShiftItem).filter(item => item.start_time && item.end_time);
  const allShifts = allRows.map(normalizeConfirmedShiftItem).filter(item => item.start_time && item.end_time);
  confirmedAllShifts = (allShifts.length ? allShifts : [...confirmedShifts, ...upcomingShifts])
    .filter((item, index, rows) => item.date && rows.findIndex(row => row.date === item.date && row.start_time === item.start_time && row.end_time === item.end_time) === index)
    .sort((a, b) => a.date.localeCompare(b.date));
  const todayYmd = dateToYmdLocal(new Date());
  const apiNextShift = normalizeConfirmedShiftItem(payload.next_shift || null);
  const nextShift = (apiNextShift.start_time && apiNextShift.end_time ? apiNextShift : null) || upcomingShifts.find(item => item.date >= todayYmd) || null;
  const nextEl = document.getElementById("nextConfirmedShift");
  nextEl.innerHTML = nextShift ? `<strong>${{ymdToLabel(nextShift.date)}}</strong><br>${{nextShift.start_time}} - ${{nextShift.end_time}}` : "次回勤務はまだありません";
  const weekStart = currentConfirmedWeekStart();
  const weekEnd = addDaysToYmd(weekStart, 6);
  const thisWeek = confirmedShifts.filter(item => item.date >= weekStart && item.date <= weekEnd).sort((a, b) => a.date.localeCompare(b.date));
  renderConfirmedList(document.getElementById("confirmedThisWeekList"), thisWeek, "今週の確定シフトはありません");
  renderConfirmedHistory();
}}



function currentMonthValue() {{
  const weekStart = ymdToDateLocal(currentConfirmedWeekStart());
  const d = weekStart || new Date();
  return `${{d.getFullYear()}}-${{pad2(d.getMonth() + 1)}}`;
}}

function normalizeMonthValue(monthValue) {{
  return /^\\d{{4}}-\\d{{2}}$/.test(String(monthValue || "")) ? monthValue : currentMonthValue();
}}

function shiftMonth(monthValue, diffMonths) {{
  const m = /^(\\d{{4}})-(\\d{{2}})$/.exec(normalizeMonthValue(monthValue));
  if (!m) return currentMonthValue();
  const d = new Date(Number(m[1]), Number(m[2]) - 1 + Number(diffMonths || 0), 1);
  return `${{d.getFullYear()}}-${{pad2(d.getMonth() + 1)}}`;
}}

function formatMinutes(totalMinutes) {{
  const minutesValue = Number(totalMinutes || 0);
  const hours = Math.floor(minutesValue / 60);
  const minutesPart = minutesValue % 60;
  return minutesPart ? `${{hours}}\u6642\u9593${{minutesPart}}\u5206` : `${{hours}}\u6642\u9593`;
}}

function formatHoursDecimal(totalMinutes) {{
  const hours = Number(totalMinutes || 0) / 60;
  return `${{Number.isInteger(hours) ? hours.toFixed(0) : hours.toFixed(1)}}\u6642\u9593`;
}}

function formatCurrency(value) {{
  if (value === null || value === undefined || value === "") return "";
  return `${{Number(value).toLocaleString("ja-JP")}}\u5186`;
}}

function hasHourlyWage(value) {{
  return value !== null && value !== undefined && value !== "";
}}

function breakRuleLabel(value) {{
  return value === "none" ? "\u4f11\u61a9\u306a\u3057" : "\u6cd5\u5b9a\u4f11\u61a9";
}}

function onOffLabel(value) {{
  return value ? "ON" : "OFF";
}}

function setPaySettingsError(message, isSuccess = false) {{
  const el = document.getElementById("paySettingsError");
  if (!el) return;
  el.style.display = message ? "block" : "none";
  el.className = `small mt-2 ${{isSuccess ? "text-success" : "text-danger"}}`;
  el.textContent = message || "";
}}

function setPaySummaryMessage(message) {{
  const el = document.getElementById("paySummaryMessage");
  if (el) el.textContent = message || "";
}}

function parsePayApiJson(text, fallbackMessage) {{
  try {{
    return text ? JSON.parse(text) : {{}};
  }} catch (e) {{
    throw new Error(fallbackMessage || "\u30c7\u30fc\u30bf\u306e\u8aad\u307f\u53d6\u308a\u306b\u5931\u6557\u3057\u307e\u3057\u305f");
  }}
}}

function apiHeaders() {{
  const headers = {{
    "Content-Type": "application/json",
    "X-Line-User-Id": LINE_USER_ID,
    "X-Line-Id-Token": ID_TOKEN,
    "ngrok-skip-browser-warning": "true"
  }};
  return headers;
}}

function buildAuthHeaders() {{
  return apiHeaders();
}}

function normalizePaySettingsResponse(data) {{
  const root = data && typeof data === "object" ? data : {{}};
  const nested = root.settings && typeof root.settings === "object" ? root.settings : root;
  return {{
    user_id: nested.user_id,
    hourly_wage: hasHourlyWage(nested.hourly_wage) ? Number(nested.hourly_wage) : null,
    break_rule: nested.break_rule === "over_6h_1h" ? "legal_jp" : (nested.break_rule || "legal_jp"),
    night_enabled: nested.night_enabled === true || nested.night_enabled === 1 || nested.night_enabled === "1",
    overtime_enabled: nested.overtime_enabled === true || nested.overtime_enabled === 1 || nested.overtime_enabled === "1"
  }};
}}

async function apiGetPaySettings() {{
  const res = await fetch(absoluteApiUrl("/api/my_pay_settings"), {{
    method: "GET",
    headers: apiHeaders(),
    cache: "no-store"
  }});
  const data = parsePayApiJson(await res.text(), "\u7d66\u4e0e\u8a2d\u5b9a\u306e\u53d6\u5f97\u306b\u5931\u6557\u3057\u307e\u3057\u305f");
  if (!res.ok || data.ok === false) throw new Error(data.error || "\u7d66\u4e0e\u8a2d\u5b9a\u306e\u53d6\u5f97\u306b\u5931\u6557\u3057\u307e\u3057\u305f");
  if (!data.settings) {{
    return normalizePaySettingsResponse({{ settings: {{ hourly_wage: null, break_rule: "legal_jp", night_enabled: true, overtime_enabled: true }} }});
  }}
  return normalizePaySettingsResponse(data);
}}

async function apiSavePaySettings(payload) {{
  const res = await fetch(absoluteApiUrl("/api/my_pay_settings"), {{
    method: "POST",
    headers: apiHeaders(),
    body: JSON.stringify(payload),
    cache: "no-store"
  }});
  const data = parsePayApiJson(await res.text(), "\u7d66\u4e0e\u8a2d\u5b9a\u306e\u4fdd\u5b58\u306b\u5931\u6557\u3057\u307e\u3057\u305f");
  if (!res.ok || data.ok === false) throw new Error(data.error || "\u7d66\u4e0e\u8a2d\u5b9a\u306e\u4fdd\u5b58\u306b\u5931\u6557\u3057\u307e\u3057\u305f");
  return {{ ...data, settings: normalizePaySettingsResponse(data) }};
}}

async function fetchPaySettings(options = {{}}) {{
  const settings = await apiGetPaySettings();
  return {{ ok: true, settings }};
}}

async function fetchPaySummary(options = {{}}) {{
  const month = normalizeMonthValue(options.month || paySummaryMonth || currentMonthValue());
  paySummaryMonth = month;
  if (!options.force && paySummaryCache[month]) {{
    return paySummaryCache[month];
  }}
  const cacheToken = paySummaryCacheToken;
  const data = await apiGetPaySummary(month);
  if (cacheToken === paySummaryCacheToken) {{
    paySummaryCache[month] = data;
  }}
  return data;
}}

async function apiGetPaySummary(monthValue) {{
  const normalizedMonth = normalizeMonthValue(monthValue);
  const res = await fetch(absoluteApiUrl(`/api/my_pay_summary?month=${{encodeURIComponent(normalizedMonth)}}`), {{
    method: "GET",
    headers: apiHeaders(),
    cache: "no-store"
  }});
  const data = parsePayApiJson(await res.text(), "\u898b\u8fbc\u307f\u7d66\u6599\u306e\u53d6\u5f97\u306b\u5931\u6557\u3057\u307e\u3057\u305f");
  if (!res.ok || data.ok !== true) throw new Error(data.error || "\u898b\u8fbc\u307f\u7d66\u6599\u306e\u53d6\u5f97\u306b\u5931\u6557\u3057\u307e\u3057\u305f");
  return data;
}}

function renderPaySettings(settings) {{
  paySettings = normalizePaySettingsResponse({{ settings: settings || paySettings || {{}} }});
}}

function renderPaySummary(summary) {{
  const summarySettings = normalizePaySettingsResponse({{ settings: {{ ...(paySettings || {{}}), ...((summary && summary.settings) || {{}}), hourly_wage: summary && summary.hourly_wage }} }});
  const hourlyWage = hasHourlyWage(summary.hourly_wage) ? Number(summary.hourly_wage) : summarySettings.hourly_wage;
  renderPaySettings(summarySettings);
  document.getElementById("paySummaryMonth").textContent = `\u5bfe\u8c61\u6708: ${{summary.month || paySummaryMonth}}`;
  const confirmedCount = Number(summary.confirmed_shift_count || 0);
  const estimatedPay = summary.estimated_pay;
  if (!hasHourlyWage(hourlyWage)) {{
    document.getElementById("paySummaryMessage").textContent = "\u6642\u7d66\u3092\u8a2d\u5b9a\u3059\u308b\u3068\u898b\u8fbc\u307f\u7d66\u6599\u3092\u8868\u793a\u3067\u304d\u307e\u3059";
    document.getElementById("paySummaryAmount").textContent = "";
  }} else if (confirmedCount === 0) {{
    document.getElementById("paySummaryMessage").textContent = "\u78ba\u5b9a\u30b7\u30d5\u30c8\u672a\u767b\u9332";
    document.getElementById("paySummaryAmount").textContent = "0\u5186";
  }} else {{
    document.getElementById("paySummaryMessage").textContent = "\u6982\u7b97\u306e\u898b\u8fbc\u307f\u91d1\u984d\u3067\u3059";
    document.getElementById("paySummaryAmount").textContent = estimatedPay === null || estimatedPay === undefined ? "" : formatCurrency(estimatedPay);
  }}
  document.getElementById("paySummaryGrid").innerHTML = `
    <div class="pay-summary-item"><div class="pay-summary-label">\u78ba\u5b9a\u30b7\u30d5\u30c8\u6570</div><div class="pay-summary-value">${{confirmedCount}}\u4ef6</div></div>
    <div class="pay-summary-item"><div class="pay-summary-label">\u5b9f\u52b4\u50cd\u6642\u9593</div><div class="pay-summary-value">${{formatHoursDecimal(summary.paid_work_minutes)}}</div></div>
  `;
}}

function renderPaySummaryLoading(month, mode = "initial") {{
  document.getElementById("paySummaryMonth").textContent = `\u5bfe\u8c61\u6708: ${{month}}`;
  document.getElementById("paySummaryMessage").textContent = mode === "update" ? "\u66f4\u65b0\u4e2d..." : "\u8a08\u7b97\u4e2d...";
  if (!paySummary) {{
    document.getElementById("paySummaryAmount").textContent = "";
    document.getElementById("paySummaryGrid").innerHTML = "";
  }}
}}

function renderPaySummaryFailure(month, message) {{
  document.getElementById("paySummaryMonth").textContent = `\u5bfe\u8c61\u6708: ${{month}}`;
  document.getElementById("paySummaryMessage").textContent = message || "\u53d6\u5f97\u5931\u6557";
  if (!paySummary) {{
    document.getElementById("paySummaryAmount").textContent = "";
    document.getElementById("paySummaryGrid").innerHTML = "";
  }}
}}

async function loadPaySummary(options = {{}}) {{
  const month = normalizeMonthValue(options.month || paySummaryMonth);
  paySummaryMonth = month;
  const requestId = ++paySummaryRequestId;
  const cached = !options.force && paySummaryCache[month];
  if (cached) {{
    paySummary = cached;
    renderPaySummary(cached);
    return cached;
  }}

  renderPaySummaryLoading(month, paySummary ? "update" : "initial");
  try {{
    const settingsJson = await fetchPaySettings({{ force: true }});
    if (requestId !== paySummaryRequestId) return null;
    renderPaySettings(settingsJson.settings);
    const summaryJson = await fetchPaySummary({{ force: !!options.force, month }});
    if (requestId !== paySummaryRequestId) return null;
    paySummary = summaryJson;
    renderPaySummary(paySummary);
    return paySummary;
  }} catch (e) {{
    if (requestId !== paySummaryRequestId) return null;
    console.error("[LIFF pay] loadPaySummary failed", e);
    renderPaySummaryFailure(month, "\u53d6\u5f97\u5931\u6557");
    return null;
  }}
}}

async function openPaySettingsModal() {{
  setPaySettingsError("");
  const settings = await apiGetPaySettings();
  renderPaySettings(settings);
  document.getElementById("payHourlyWage").value = hasHourlyWage(settings.hourly_wage) ? settings.hourly_wage : "";
  document.getElementById("payBreakRule").value = settings.break_rule === "over_6h_1h" ? "legal_jp" : (settings.break_rule || "legal_jp");
  document.getElementById("payNightEnabled").checked = !!settings.night_enabled;
  document.getElementById("payOvertimeEnabled").checked = !!settings.overtime_enabled;
  paySettingsModal.show();
}}

async function savePaySettings() {{
  setPaySettingsError("");
  setPaySummaryMessage("");

  try {{
    const hourlyWage = Number(document.getElementById("payHourlyWage").value);
    if (!Number.isInteger(hourlyWage) || hourlyWage <= 0) {{
      setPaySettingsError("\u57fa\u672c\u6642\u7d66\u306f\u6b63\u306e\u6574\u6570\u3067\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044");
      return;
    }}

    const payload = {{
      hourly_wage: hourlyWage,
      break_rule: document.getElementById("payBreakRule").value,
      night_enabled: document.getElementById("payNightEnabled").checked,
      overtime_enabled: document.getElementById("payOvertimeEnabled").checked
    }};

    const postJson = await apiSavePaySettings(payload);
    if (postJson.ok === false) {{
      setPaySettingsError(postJson.error || "\u4fdd\u5b58\u306b\u5931\u6557\u3057\u307e\u3057\u305f");
      return;
    }}

    const settingsJson = await fetchPaySettings({{ force: true }});
    paySummaryMonth = normalizeMonthValue(paySummaryMonth || currentMonthValue());
    paySummaryCacheToken += 1;
    paySummaryCache = {{}};

    paySettings = settingsJson.settings;
    renderPaySettings(paySettings);
    await loadPaySummary({{ force: true, month: paySummaryMonth }});

    const reloadedMatches = Number(paySettings.hourly_wage) === hourlyWage
      && paySettings.break_rule === (payload.break_rule === "over_6h_1h" ? "legal_jp" : payload.break_rule)
      && paySettings.night_enabled === payload.night_enabled
      && paySettings.overtime_enabled === payload.overtime_enabled;
    if (!reloadedMatches) {{
      throw new Error("\u4fdd\u5b58\u5f8c\u306e\u8a2d\u5b9a\u78ba\u8a8d\u306b\u5931\u6557\u3057\u307e\u3057\u305f");
    }}

    setPaySettingsError("\u4fdd\u5b58\u3057\u307e\u3057\u305f", true);
    setPaySummaryMessage("\u4fdd\u5b58\u3057\u307e\u3057\u305f");
  }} catch (e) {{
    console.error("[LIFF pay] save failed", e);
    setPaySettingsError(e && e.message ? e.message : "\u7d66\u4e0e\u8a2d\u5b9a\u306e\u4fdd\u5b58\u306b\u5931\u6557\u3057\u307e\u3057\u305f");
  }}
}}

async function loadConfirmedShifts(resetHistory = false) {{
  const range = confirmedRange();
  if (resetHistory || !confirmedHistoryWeekStart) resetConfirmedHistoryWeek();
  paySummaryMonth = normalizeMonthValue(paySummaryMonth || currentMonthValue());
  setConfirmedLoading("\u8aad\u307f\u8fbc\u307f\u4e2d...");
  const data = await apiGetMyWeek(LINE_USER_ID, range.start);
  renderConfirmedShifts(data);
  await loadPaySummary();
}}

async function apiGetMyWeek(lineUserId, startYmd) {{
  const normalizedStart = normalizeWeekStartToSunday(startYmd);
  if (!normalizedStart) {{
    console.error("apiGetMyWeek invalid start", {{ lineUserId, startYmd }});
    throw new Error("週開始日の形式が不正です");
  }}
  if (!ID_TOKEN) {{
    throw new Error("LINE認証情報の取得に失敗しました");
  }}

  try {{
    const finalFetchUrl = buildWeekApiUrl(normalizedStart);
    debugLog("api呼び出し前", {{
      lineUserId,
      normalizedStart,
      href: window.location.href,
      origin: window.location.origin,
      apiBaseUrl: API_BASE_URL,
      url: finalFetchUrl,
      sameOrigin: finalFetchUrl.startsWith("/")
    }});
    debugLog("fetch実行直前", {{
      finalFetchUrl,
      finalFetchUrlType: typeof finalFetchUrl
    }});

    let res;
    try {{
      res = await fetch(finalFetchUrl, {{
        method: "POST",
        headers: {{
          "Content-Type": "application/json",
          "ngrok-skip-browser-warning": "true"
        }},
        body: JSON.stringify({{
          id_token: ID_TOKEN,
          start: normalizedStart
        }})
      }});
    }} catch (fetchError) {{
      debugLog("fetch実行失敗", {{
        url: finalFetchUrl,
        name: fetchError && fetchError.name ? fetchError.name : "UnknownError",
        message: fetchError && fetchError.message ? fetchError.message : String(fetchError)
      }});
      throw fetchError;
    }}

    if (!res.ok) {{
      const errData = await res.json().catch(() => ({{}}));
      throw new Error(errData.error || "データ取得に失敗しました");
    }}
    return await res.json();
  }} catch (err) {{
    debugLog("apiGetMyWeek失敗", {{
      url: (() => {{
        try {{
          return buildWeekApiUrl(normalizedStart);
        }} catch (e) {{
          return "";
        }}
      }})(),
      name: err && err.name ? err.name : "UnknownError",
      message: err && err.message ? err.message : String(err)
    }});
    console.error("apiGetMyWeek failed", {{ lineUserId, startYmd, normalizedStart, err }});
    throw err;
  }}
}}

async function apiSaveDay(lineUserId, payload) {{
  if (!ID_TOKEN) {{
    throw new Error("LINE認証情報の取得に失敗しました");
  }}
  const url = apiUrl("/api/save_day");
  debugLog("save API呼び出し前", {{ url, date: payload && payload.date }});
  const res = await fetch(url, {{
    method: "POST",
    headers: {{
      "Content-Type": "application/json",
      "ngrok-skip-browser-warning": "true"
    }},
    body: JSON.stringify({{
      ...payload,
      id_token: ID_TOKEN
    }})
  }});
  const data = await res.json().catch(() => ({{}}));
  if (!res.ok) throw new Error(data.error || "保存に失敗しました");
  return data;
}}

async function apiDeleteDay(lineUserId, dateYmd) {{
  if (!ID_TOKEN) {{
    throw new Error("LINE認証情報の取得に失敗しました");
  }}
  const url = apiUrl("/api/delete_day");
  debugLog("delete API呼び出し前", {{ url, date: dateYmd }});
  const res = await fetch(url, {{
    method: "POST",
    headers: {{
      "Content-Type": "application/json",
      "ngrok-skip-browser-warning": "true"
    }},
    body: JSON.stringify({{ date: dateYmd, id_token: ID_TOKEN }})
  }});
  const data = await res.json().catch(() => ({{}}));
  if (!res.ok) throw new Error(data.error || "削除に失敗しました");
  return data;
}}

function openModal(ymd) {{
  currentDate = normalizeWeekStart(ymd);
  const status = getDeadlineStatus(currentDate);
  const isPast = isPastDateYmd(currentDate);

  setError(isPast ? "過去日は変更できません" : (status && status.is_closed ? (status.message || "提出期限を過ぎています") : ""));

  document.getElementById("modalTitle").textContent = `${{ymdToLabel(currentDate)}} の入力`;
  document.getElementById("modalSub").textContent = currentDate;
  document.getElementById("modalDeadlineText").textContent =
    isPast ? "過去日は変更できません" : (status && status.deadline_display ? `締切: ${{status.deadline_display}}` : "締切: 未設定");

  const entry = entries[currentDate] || null;
  const startSel = document.getElementById("startTime");
  const endSel = document.getElementById("endTime");

  document.getElementById("modeWork").checked = true;
  document.getElementById("modeOff").checked = false;

  if (entry) {{
    if (entry.off) {{
      document.getElementById("modeOff").checked = true;
      document.getElementById("modeWork").checked = false;
    }} else {{
      startSel.value = entry.start_time || "09:00";
      endSel.value = entry.end_time || "18:00";
    }}
  }} else {{
    startSel.value = "09:00";
    endSel.value = "18:00";
  }}

  toggleTimeBox();
  const disabled = isPast || !!(status && status.is_closed);
  document.getElementById("modeWork").disabled = disabled;
  document.getElementById("modeOff").disabled = disabled;
  startSel.disabled = disabled;
  endSel.disabled = disabled;
  document.getElementById("btnSave").disabled = disabled;
  document.getElementById("btnDelete").disabled = disabled;
  modal.show();
}}

function toggleTimeBox() {{
  const off = document.getElementById("modeOff").checked;
  document.getElementById("timeBox").style.display = off ? "none" : "block";
}}

async function loadWeek(startYmd) {{
  const normalizedStart = normalizeWeekStartToSunday(startYmd);
  if (!normalizedStart) {{
    console.error("loadWeek invalid start", {{ startYmd }});
    throw new Error("週開始日の形式が不正です");
  }}

  debugLog("loadWeek開始", {{ startYmd, normalizedStart }});
  currentWeekStart = normalizedStart;
  isLoadingWeek = true;
  updateWeekNav();
  document.getElementById("rangeText").textContent = `${{normalizedStart}} - 読み込み中...`;

  try {{
    if (ID_TOKEN) {{
      const data = await apiGetMyWeek(LINE_USER_ID, normalizedStart);
      entries = data.entries || {{}};
      deadlineStatuses = data.deadline_statuses || {{}};
    }} else {{
      entries = {{}};
      deadlineStatuses = {{}};
    }}
    renderWeek(normalizedStart);
  }} catch (err) {{
    debugLog("loadWeek失敗", {{
      startYmd,
      normalizedStart,
      name: err && err.name ? err.name : "UnknownError",
      message: err && err.message ? err.message : String(err)
    }});
    console.error("loadWeek failed", {{ startYmd, normalizedStart, err }});
    document.getElementById("rangeText").textContent = `${{normalizedStart}} - 読み込み失敗`;
    throw err;
  }} finally {{
    isLoadingWeek = false;
    updateWeekNav();
  }}
}}

async function main() {{
  ID_TOKEN = "";
  DISPLAY_NAME = "読み込み中...";
  updateStaffNameText();
  entries = {{}};
  deadlineStatuses = {{}};
  currentWeekStart = normalizeWeekStartToSunday(START) || dateToYmdLocal(getSundayOfWeek(new Date()));
  renderWeek(currentWeekStart);

  try {{
    await liff.init({{ liffId: LIFF_ID }});
    debugLog("liff.init完了", {{ liffId: LIFF_ID }});
  }} catch (error) {{
    const initErrorInfo = {{
      name: error && error.name ? error.name : "UnknownError",
      message: error && error.message ? error.message : String(error),
      liffId: LIFF_ID,
      typeofLiff: typeof liff,
      typeofLiffInit: typeof (window.liff && window.liff.init),
      href: window.location.href,
      userAgent: navigator.userAgent
    }};
    debugLog("liff.init失敗", initErrorInfo);
    alert(`LIFF init error: ${{initErrorInfo.name}}: ${{initErrorInfo.message}}`);
    throw error;
  }}

  if (!liff.isLoggedIn()) {{
    liff.login();
    return;
  }}

  LINE_USER_ID = "";
  ID_TOKEN = liff.getIDToken() || "";
  DISPLAY_NAME = "未設定";
  debugLog("idToken取得", {{ available: !!ID_TOKEN }});

  let decodedToken = null;
  let decodedTokenAvailable = false;
  let decodedSubAvailable = false;
  let profileStatus = "not_called";

  try {{
    decodedToken = liff.getDecodedIDToken();
    decodedTokenAvailable = !!decodedToken;
    decodedSubAvailable = !!(decodedToken && decodedToken.sub);
    if (decodedSubAvailable) {{
      LINE_USER_ID = decodedToken.sub;
    }}
    if (decodedToken && decodedToken.name) {{
      DISPLAY_NAME = decodedToken.name;
      updateStaffNameText();
    }}
    debugLog("decodedIDToken確認", {{
      tokenAvailable: decodedTokenAvailable,
      subAvailable: decodedSubAvailable,
      lineUserId: LINE_USER_ID || ""
    }});
  }} catch (e) {{
    debugLog("decodedIDToken取得失敗", {{
      message: e && e.message ? e.message : String(e)
    }});
  }}

  try {{
    const profile = await liff.getProfile();
    profileStatus = "success";
    if (!LINE_USER_ID && profile && profile.userId) {{
      LINE_USER_ID = profile.userId;
    }}
    if (DISPLAY_NAME === "未設定" && profile && profile.displayName) {{
      DISPLAY_NAME = profile.displayName;
      updateStaffNameText();
    }}
  }} catch (e) {{
    profileStatus = "failed";
    debugLog("getProfile失敗", {{
      message: e && e.message ? e.message : String(e)
    }});
  }}

  debugLog("プロフィール取得結果", {{
    decodedTokenAvailable,
    decodedSubAvailable,
    profileStatus,
    lineUserId: LINE_USER_ID || "",
    displayName: DISPLAY_NAME
  }});
  updateStaffNameText();

  const times = buildTimes(15);
  fillSelectOptions(document.getElementById("startTime"), times);
  fillSelectOptions(document.getElementById("endTime"), times);

  modal = new bootstrap.Modal(document.getElementById("editModal"));
  paySettingsModal = new bootstrap.Modal(document.getElementById("paySettingsModal"));

  document.getElementById("btnClose").onclick = () => liff.closeWindow();
  document.getElementById("tabSubmit").onclick = () => setActiveTab("submit");
  document.getElementById("tabConfirmed").onclick = async () => {{
    setActiveTab("confirmed");
    try {{
      paySummaryMonth = currentMonthValue();
      await loadConfirmedShifts(true);
    }} catch (e) {{
      setConfirmedLoading(e.message || "確定シフトの取得に失敗しました");
    }}
  }};
  document.getElementById("btnConfirmedHistoryPrev").onclick = () => {{
    confirmedHistoryWeekStart = addDaysToYmd(confirmedHistoryWeekStart || addDaysToYmd(currentConfirmedWeekStart(), -7), -7);
    renderConfirmedHistory();
  }};
  document.getElementById("btnConfirmedHistoryNext").onclick = () => {{
    const nextHistoryWeek = addDaysToYmd(confirmedHistoryWeekStart || addDaysToYmd(currentConfirmedWeekStart(), -7), 7);
    const todayYmd = dateToYmdLocal(new Date());
    if (nextHistoryWeek && nextHistoryWeek < todayYmd) {{
      confirmedHistoryWeekStart = nextHistoryWeek;
      renderConfirmedHistory();
    }}
  }};

  document.getElementById("btnOpenPaySettings").onclick = async () => {{
    try {{
      await openPaySettingsModal();
    }} catch (e) {{
      setPaySettingsError(e.message || "\u7d66\u4e0e\u8a2d\u5b9a\u306e\u53d6\u5f97\u306b\u5931\u6557\u3057\u307e\u3057\u305f");
      paySettingsModal.show();
    }}
  }};
  document.getElementById("btnPayPrevMonth").onclick = async () => {{
    paySummaryMonth = shiftMonth(paySummaryMonth || currentMonthValue(), -1);
    await loadPaySummary();
  }};
  document.getElementById("btnPayNextMonth").onclick = async () => {{
    paySummaryMonth = shiftMonth(paySummaryMonth || currentMonthValue(), 1);
    await loadPaySummary();
  }};
  document.getElementById("btnSavePaySettings").onclick = savePaySettings;

  document.getElementById("btnPrevWeek").onclick = async () => {{
    const prevWeek = shiftWeek(currentWeekStart, -1);
    debugLog("前週クリック", {{ currentWeekStart, prevWeek }});
    try {{
      await loadWeek(prevWeek);
      if (activeTab === "confirmed") await loadConfirmedShifts(true);
    }} catch (e) {{
      setError(e.message || "週データの取得に失敗しました");
    }}
  }};

  document.getElementById("btnNextWeek").onclick = async () => {{
    const nextWeek = shiftWeek(currentWeekStart, 1);
    debugLog("次週クリック", {{ currentWeekStart, nextWeek }});
    try {{
      await loadWeek(nextWeek);
      if (activeTab === "confirmed") await loadConfirmedShifts(true);
    }} catch (e) {{
      setError(e.message || "週データの取得に失敗しました");
    }}
  }};

  document.getElementById("modeWork").addEventListener("change", toggleTimeBox);
  document.getElementById("modeOff").addEventListener("change", toggleTimeBox);
  debugLog("イベント登録完了", {{ currentWeekStart }});

  document.getElementById("btnSave").onclick = async () => {{
    setError("");
    if (isPastDateYmd(currentDate)) {{
      setError("過去日は変更できません");
      return;
    }}
    const status = getDeadlineStatus(currentDate);
    if (status && status.is_closed) {{
      setError(status.message || "提出期限を過ぎています");
      return;
    }}

    if (!ID_TOKEN) {{
      setError("LINE認証情報が取得できませんでした。LIFFから開いているか確認してください。");
      return;
    }}

    const off = document.getElementById("modeOff").checked;
    const start = document.getElementById("startTime").value;
    const end = document.getElementById("endTime").value;

    if (!off && minutes(end) === minutes(start)) {{
      setError("開始時間と終了時間が同じです。");
      return;
    }}

    try {{
      const payload = {{
        date: currentDate,
        off: off,
        start_time: off ? null : start,
        end_time: off ? null : end,
        name: DISPLAY_NAME
      }};
      const r = await apiSaveDay(LINE_USER_ID, payload);
      entries[currentDate] = r.entry;
      if (r.deadline_status) {{
        deadlineStatuses[currentDate] = r.deadline_status;
      }}
      renderWeek(currentWeekStart);
      modal.hide();
    }} catch (e) {{
      setError(e.message || "保存に失敗しました");
    }}
  }};

  document.getElementById("btnDelete").onclick = async () => {{
    setError("");
    if (isPastDateYmd(currentDate)) {{
      setError("過去日は変更できません");
      return;
    }}
    const status = getDeadlineStatus(currentDate);
    if (status && status.is_closed) {{
      setError(status.message || "提出期限を過ぎています");
      return;
    }}

    if (!ID_TOKEN) {{
      setError("LINE認証情報が取得できませんでした。LIFFから開いているか確認してください。");
      return;
    }}

    try {{
      const r = await apiDeleteDay(LINE_USER_ID, currentDate);
      delete entries[currentDate];
      if (r.deadline_status) {{
        deadlineStatuses[currentDate] = r.deadline_status;
      }}
      renderWeek(currentWeekStart);
      modal.hide();
    }} catch (e) {{
      setError(e.message || "削除に失敗しました");
    }}
  }};

  await loadWeek(currentWeekStart);
}}

main().catch(err => {{
  const message = "エラー: " + (err.message || err);
  debugLog("main.catch", {{ message }});
  alert(message);
}});
</script>

</body>
</html>
""")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

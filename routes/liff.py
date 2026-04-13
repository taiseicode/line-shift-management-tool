from datetime import datetime

from flask import Blueprint, request, make_response

from config import LIFF_ID
from services.deadline_service import get_active_deadline_config
from utils import parse_ymd, to_ymd, html_escape


liff_bp = Blueprint("liff", __name__)


@liff_bp.route("/liff/submit", methods=["GET"])
def liff_submit():
    if not LIFF_ID:
        return "LIFF_ID が .env に設定されていません", 500

    today = datetime.now().date()
    build_id = datetime.now().strftime("%Y-%m-%d-%H%M")
    start_value = request.args.get("start", "").strip()
    start_d = parse_ymd(start_value) or today
    start_value = to_ymd(start_d)

    active_config = get_active_deadline_config()
    mode_labels = {
        "fixed": "固定日時方式",
        "relative": "相対期限方式",
        "": "未設定",
    }
    mode_text = mode_labels.get(active_config["mode"], "未設定")
    rule_text = active_config["display"] if active_config["is_configured"] else "未設定"

    if active_config["mode"] == "fixed" and active_config["is_configured"]:
        submission_message_html = f'<div class="alert alert-warning py-2 small mb-3">現在の提出期限: {html_escape(rule_text)}</div>'
    elif active_config["mode"] == "relative" and active_config["is_configured"]:
        submission_message_html = f'<div class="alert alert-warning py-2 small mb-3">現在の提出ルール: {html_escape(rule_text)}</div>'
    else:
        submission_message_html = '<div class="alert alert-success py-2 small mb-3">提出期限は未設定です。現在はいつでも提出できます。</div>'

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
      --app-bg: #f3f6fb;
      --panel-bg: rgba(255, 255, 255, 0.94);
      --panel-border: rgba(15, 23, 42, 0.08);
      --panel-shadow: 0 18px 42px rgba(15, 23, 42, 0.08);
      --text-main: #18212f;
      --text-sub: #607086;
      --line-soft: rgba(96, 112, 134, 0.18);
      --brand: #1f5eff;
      --brand-soft: rgba(31, 94, 255, 0.12);
      --off-soft: rgba(100, 116, 139, 0.14);
      --danger-soft: rgba(209, 67, 67, 0.12);
      --radius-xl: 24px;
      --radius-lg: 18px;
      --radius-md: 14px;
    }}
    body {{
      background:
        radial-gradient(circle at top left, rgba(31, 94, 255, 0.10), transparent 34%),
        linear-gradient(180deg, #f8fbff 0%, var(--app-bg) 100%);
      color: var(--text-main);
      min-height: 100vh;
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
      backdrop-filter: blur(14px);
    }}
    .hero-panel {{
      border-radius: var(--radius-xl);
      padding: 22px 20px 18px;
      margin-bottom: 16px;
    }}
    .hero-eyebrow {{
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-weight: 700;
      color: var(--brand);
      margin-bottom: 6px;
    }}
    .hero-title {{
      font-size: 1.5rem;
      font-weight: 700;
      margin: 0;
      letter-spacing: -0.02em;
    }}
    .hero-sub,
    .range-text,
    .section-note,
    .debug-chip {{
      color: var(--text-sub);
    }}
    .hero-sub {{
      font-size: 0.95rem;
      line-height: 1.6;
      margin-top: 8px;
      margin-bottom: 0;
    }}
    .range-text {{
      font-size: 0.96rem;
      font-weight: 600;
      margin-top: 12px;
    }}
    .hero-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 14px;
    }}
    .meta-chip {{
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 0 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.9);
      border: 1px solid var(--line-soft);
      font-size: 12px;
      color: var(--text-sub);
    }}
    .top-action,
    .week-nav .btn {{
      min-height: 48px;
      border-radius: 14px;
      font-weight: 600;
      border-width: 1px;
    }}
    .top-action {{
      min-width: 84px;
    }}
    .week-nav {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-top: 16px;
    }}
    .guide-card {{
      border-radius: var(--radius-lg);
      padding: 14px 16px;
      margin-bottom: 14px;
    }}
    .guide-title {{
      font-size: 0.92rem;
      font-weight: 700;
      margin-bottom: 4px;
    }}
    .submission-wrap .alert {{
      border: 0;
      border-radius: 16px;
      padding: 14px 16px;
      box-shadow: 0 12px 28px rgba(15, 23, 42, 0.06);
    }}
    .debug-chip {{
      font-size: 12px;
      padding: 8px 12px;
      border-radius: 12px;
      background: rgba(255, 255, 255, 0.7);
      border: 1px dashed rgba(96, 112, 134, 0.24);
      margin-bottom: 12px;
      word-break: break-word;
    }}
    .shift-list {{
      display: grid;
      gap: 12px;
    }}
    .shift-card {{
      width: 100%;
      border: 1px solid var(--panel-border);
      border-radius: var(--radius-lg);
      background: rgba(255, 255, 255, 0.97);
      box-shadow: 0 14px 30px rgba(15, 23, 42, 0.06);
      padding: 0;
      overflow: hidden;
      transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
    }}
    .shift-card:disabled {{
      cursor: not-allowed;
    }}
    .shift-card:not(:disabled):active {{
      transform: scale(0.995);
    }}
    .shift-card:not(:disabled):hover {{
      border-color: rgba(31, 94, 255, 0.28);
      box-shadow: 0 20px 36px rgba(15, 23, 42, 0.10);
    }}
    .shift-card-inner {{
      padding: 16px 16px 15px;
      text-align: left;
    }}
    .shift-card-header {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }}
    .shift-date {{
      font-size: 1.04rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      color: var(--text-main);
    }}
    .shift-date-sub {{
      font-size: 0.78rem;
      color: var(--text-sub);
      margin-top: 3px;
    }}
    .shift-status-tag {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 72px;
      min-height: 30px;
      padding: 0 12px;
      border-radius: 999px;
      font-size: 0.76rem;
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
      color: #0f4cc9;
      background: var(--brand-soft);
      border-color: rgba(31, 94, 255, 0.18);
    }}
    .tag-closed {{
      color: #9f2d2d;
      background: var(--danger-soft);
      border-color: rgba(209, 67, 67, 0.18);
    }}
    .shift-user-row {{
      font-size: 0.84rem;
      color: var(--text-sub);
      margin-bottom: 10px;
    }}
    .shift-state {{
      border-radius: 16px;
      padding: 14px 14px 12px;
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
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      margin-bottom: 4px;
    }}
    .shift-state-detail {{
      font-size: 0.98rem;
      font-weight: 700;
      letter-spacing: -0.01em;
    }}
    .deadline-note {{
      margin-top: 10px;
      font-size: 0.82rem;
      line-height: 1.5;
      padding: 10px 12px;
      border-radius: 12px;
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
      opacity: 0.72;
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
      min-height: 48px;
      font-weight: 600;
    }}
    .form-select,
    .form-control {{
      min-height: 48px;
      border-radius: 14px;
      border-color: rgba(96, 112, 134, 0.22);
    }}
    .action-row {{
      display: flex;
      gap: 10px;
      margin-top: 18px;
    }}
    .action-row .btn {{
      min-height: 48px;
      border-radius: 14px;
      font-weight: 700;
    }}
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
        <div class="hero-eyebrow">Shift Submission</div>
        <h4 class="hero-title">シフト提出</h4>
        <p class="hero-sub">1週間分のシフトを入力してください</p>
        <div class="range-text" id="rangeText"></div>
      </div>
      <button id="btnClose" class="btn btn-outline-secondary top-action">閉じる</button>
    </div>
    <div class="hero-meta">
      <div class="meta-chip">有効な締切方式: {html_escape(mode_text)}</div>
      <div class="meta-chip">build: {build_id}</div>
    </div>
    <div class="week-nav">
      <button type="button" id="btnPrevWeek" class="btn btn-outline-secondary">前の週</button>
      <button type="button" id="btnNextWeek" class="btn btn-primary">次の週</button>
    </div>
  </div>

  <div class="guide-card">
    <div class="guide-title">使い方</div>
    <div class="section-note small">各日のカードから「出勤 / 休み」を選び、必要な日は開始・終了時刻を保存してください。</div>
  </div>
  <div class="submission-wrap mb-3">{submission_message_html}</div>
  <div id="debugText" class="debug-chip">debug: 初期化前</div>

  <div id="list" class="shift-list"></div>
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
            ※15分刻み。終了は開始より後にしてください。
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
const BUILD_ID = {build_id!r};
const API_BASE_URL = {request.host_url.rstrip("/")!r};

let LINE_USER_ID = "";
let ID_TOKEN = "";
let DISPLAY_NAME = "";
let entries = {{}};
let deadlineStatuses = {{}};
let currentWeekStart = "";
let currentDate = "";
let isLoadingWeek = false;
let modal = null;

function debugLog(message, extra = null) {{
  const text = extra ? `${{message}} | ${{JSON.stringify(extra)}}` : message;
  console.log(`[LIFF ${{BUILD_ID}}] ${{text}}`);
  const debugEl = document.getElementById("debugText");
  if (debugEl) {{
    debugEl.textContent = `debug: ${{text}}`;
  }}
}}

function apiUrl(path) {{
  const href = window.location.href;
  const origin = window.location.origin;
  const finalUrl = String(path || "");
  debugLog("fetch URL生成", {{
    href,
    origin,
    apiBaseUrl: API_BASE_URL,
    path,
    url: finalUrl,
    sameOrigin: finalUrl.startsWith("/")
  }});
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

function normalizeWeekStart(startYmd) {{
  const dateObj = ymdToDateLocal(startYmd);
  if (!dateObj) return "";
  return dateToYmdLocal(dateObj);
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
      tagText: "締切超過",
      stateClass: "state-closed",
      label: "受付終了",
      detail: "提出期限を過ぎています"
    }};
  }}
  if (!entry) {{
    return {{
      tagClass: "tag-empty",
      tagText: "未入力",
      stateClass: "state-empty",
      label: "未入力",
      detail: "まだ勤務予定が登録されていません"
    }};
  }}
  if (entry.off) {{
    return {{
      tagClass: "tag-off",
      tagText: "休み",
      stateClass: "state-off",
      label: "休み",
      detail: "この日はお休みで提出済みです"
    }};
  }}
  return {{
    tagClass: "tag-work",
    tagText: "出勤",
    stateClass: "state-work",
    label: "勤務時間",
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
    return `<div class="deadline-note note-closed">提出期限を過ぎています</div>`;
  }}
  if (status.deadline_display) {{
    return `<div class="deadline-note note-open">締切: ${{status.deadline_display}}</div>`;
  }}
  return `<div class="deadline-note note-open">提出可能</div>`;
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
  const normalizedStart = normalizeWeekStart(startYmd);
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

  const initialWeekStart = normalizeWeekStart(START) || START;
  const normalizedCurrent = normalizeWeekStart(currentWeekStart) || initialWeekStart;

  prevBtn.disabled = isLoadingWeek || normalizedCurrent === initialWeekStart;
  nextBtn.disabled = isLoadingWeek;
  prevBtn.textContent = "前の週";
  nextBtn.textContent = isLoadingWeek ? "読み込み中..." : "次の週";
}}

function renderWeek(startYmd) {{
  const normalizedStart = normalizeWeekStart(startYmd);
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

  rangeText.textContent = `${{weekDates[0]}} ? ${{weekDates[6]}}`;

  for (const ymd of weekDates) {{
    const entry = entries[ymd] || null;
    const status = getDeadlineStatus(ymd);

    const card = document.createElement("button");
    card.type = "button";
    card.className = "shift-card text-start";
    card.dataset.date = ymd;
    card.onclick = () => openModal(card.dataset.date);

    if (status && status.is_closed) {{
      card.disabled = true;
      card.classList.add("shift-closed");
    }}

    card.innerHTML = `
      <div class="shift-card-inner">
        <div class="shift-card-header">
          <div>
            <div class="shift-date">${{ymdToLabel(ymd)}}</div>
            <div class="shift-date-sub">${{ymd}}</div>
          </div>
          ${{statusTagHtml(entry, status)}}
        </div>
        <div class="shift-user-row">ユーザー: ${{DISPLAY_NAME || "未設定"}}</div>
        ${{badgeHtml(entry, status)}}
        ${{deadlineStatusHtml(status)}}
      </div>
    `;
    list.appendChild(card);
  }}

  updateWeekNav();
}}

async function apiGetMyWeek(lineUserId, startYmd) {{
  const normalizedStart = normalizeWeekStart(startYmd);
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
          "Content-Type": "application/json"
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
      "Content-Type": "application/json"
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
      "Content-Type": "application/json"
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

  setError(status && status.is_closed ? (status.message || "提出期限を過ぎています") : "");

  document.getElementById("modalTitle").textContent = `${{ymdToLabel(currentDate)}} の入力`;
  document.getElementById("modalSub").textContent = currentDate;
  document.getElementById("modalDeadlineText").textContent =
    status && status.deadline_display ? `締切: ${{status.deadline_display}}` : "締切: 未設定";

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
  document.getElementById("btnSave").disabled = !!(status && status.is_closed);
  document.getElementById("btnDelete").disabled = !!(status && status.is_closed);
  modal.show();
}}

function toggleTimeBox() {{
  const off = document.getElementById("modeOff").checked;
  document.getElementById("timeBox").style.display = off ? "none" : "block";
}}

async function loadWeek(startYmd) {{
  const normalizedStart = normalizeWeekStart(startYmd);
  if (!normalizedStart) {{
    console.error("loadWeek invalid start", {{ startYmd }});
    throw new Error("週開始日の形式が不正です");
  }}

  debugLog("loadWeek開始", {{ startYmd, normalizedStart }});
  currentWeekStart = normalizedStart;
  isLoadingWeek = true;
  updateWeekNav();
  document.getElementById("rangeText").textContent = `${{normalizedStart}} ～ 読み込み中...`;

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
    document.getElementById("rangeText").textContent = `${{normalizedStart}} ～ 読み込み失敗`;
    throw err;
  }} finally {{
    isLoadingWeek = false;
    updateWeekNav();
  }}
}}

async function main() {{
  debugLog("main開始", {{
    start: START,
    build: BUILD_ID,
    href: window.location.href,
    origin: window.location.origin
  }});
  ID_TOKEN = "";
  DISPLAY_NAME = "読み込み中...";
  entries = {{}};
  deadlineStatuses = {{}};
  currentWeekStart = normalizeWeekStart(START) || START;
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

  const times = buildTimes(15);
  fillSelectOptions(document.getElementById("startTime"), times);
  fillSelectOptions(document.getElementById("endTime"), times);

  modal = new bootstrap.Modal(document.getElementById("editModal"));

  document.getElementById("btnClose").onclick = () => liff.closeWindow();

  document.getElementById("btnPrevWeek").onclick = async () => {{
    const prevWeek = shiftWeek(currentWeekStart, -1);
    debugLog("前週クリック", {{ currentWeekStart, prevWeek }});
    try {{
      await loadWeek(prevWeek);
    }} catch (e) {{
      setError(e.message || "週データの取得に失敗しました");
    }}
  }};

  document.getElementById("btnNextWeek").onclick = async () => {{
    const nextWeek = shiftWeek(currentWeekStart, 1);
    debugLog("次週クリック", {{ currentWeekStart, nextWeek }});
    try {{
      await loadWeek(nextWeek);
    }} catch (e) {{
      setError(e.message || "週データの取得に失敗しました");
    }}
  }};

  document.getElementById("modeWork").addEventListener("change", toggleTimeBox);
  document.getElementById("modeOff").addEventListener("change", toggleTimeBox);
  debugLog("イベント登録完了", {{ currentWeekStart }});

  document.getElementById("btnSave").onclick = async () => {{
    setError("");
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

    if (!off && minutes(end) <= minutes(start)) {{
      setError("終了は開始より後にしてください。");
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

/* 서울 날씨 AI 비서 — 바닐라 JavaScript (프레임워크 없음) */
"use strict";

const API_BASE = ((window.APP_CONFIG && window.APP_CONFIG.API_BASE_URL) || "http://localhost:8000").replace(/\/+$/, "");
const PAGE_SIZE = 20;

const state = {
  conversationId: null,
  conversations: [],
  data: [],            // 날짜 내림차순 전체 목록
  shown: PAGE_SIZE,
  editingId: null,
  summary: null,
  series: [],
  sending: false,
};

const $ = (id) => document.getElementById(id);

/* ───────────── 공통: API 호출 ───────────── */
class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function api(path, { method = "GET", body, timeout = 30000 } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  let res;
  try {
    res = await fetch(API_BASE + path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });
  } catch (e) {
    if (e.name === "AbortError") throw new ApiError("서버 응답이 너무 늦어요. 잠시 후 다시 시도해 주세요.", 0);
    throw new ApiError(await diagnoseConnection(), 0);
  } finally {
    clearTimeout(timer);
  }
  let payload = null;
  const text = await res.text();
  try { payload = text ? JSON.parse(text) : null; } catch { payload = text; }
  if (!res.ok) {
    let msg = `요청 실패 (${res.status})`;
    if (payload && typeof payload.detail === "string") msg = payload.detail;
    else if (payload && Array.isArray(payload.detail)) {   // Pydantic 검증 오류(422)
      msg = "입력값 오류: " + payload.detail.map((d) => `${(d.loc || []).slice(1).join(".")} ${d.msg}`).join(", ");
    }
    throw new ApiError(msg, res.status);
  }
  return payload;
}

/* 연결 실패 원인 진단: 브라우저는 '서버 꺼짐'과 'CORS 차단'을 같은 오류로 보여 주므로 직접 구분한다.
   no-cors 요청은 CORS 검사 없이 서버 도달 여부만 확인할 수 있다. */
async function diagnoseConnection() {
  const here = location.origin;
  if (location.protocol === "file:") {
    return "index.html을 파일로 직접 열었어요. 브라우저가 이 경우 요청을 막습니다.\n" +
      "frontend 폴더에서 `python -m http.server 5500` 실행 후 http://localhost:5500 으로 접속하세요.";
  }
  if (location.protocol === "https:" && API_BASE.startsWith("http://") && !API_BASE.includes("localhost")) {
    return `https 페이지에서 http 주소(${API_BASE})는 호출할 수 없어요. API_BASE_URL을 https:// 주소로 바꾸세요.`;
  }
  let reachable = false;
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 8000);
    await fetch(API_BASE + "/health", { mode: "no-cors", signal: ctrl.signal });
    clearTimeout(t);
    reachable = true;
  } catch { reachable = false; }
  if (reachable) {
    return `서버(${API_BASE})는 켜져 있지만 브라우저가 응답을 막았어요 (CORS).\n` +
      `백엔드 환경 변수 ALLOWED_ORIGINS에 현재 주소 "${here}" 를 정확히 추가하세요 (끝에 / 없이). ` +
      "추가했는데도 같다면 서버 로그에서 500 오류를 확인하세요.";
  }
  return `서버(${API_BASE})에 연결할 수 없어요.\n` +
    (API_BASE.includes("localhost") || API_BASE.includes("127.0.0.1")
      ? "백엔드가 실행 중인지 확인하세요: backend 폴더에서 `python -m uvicorn main:app --reload`"
      : "주소(API_BASE_URL)가 맞는지, Render 서비스가 배포 완료(Live) 상태인지 확인하세요. 잠들어 있으면 1분 후 다시 시도하세요.");
}

/* ───────────── 공통: UI 도우미 ───────────── */
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null) node.setAttribute(k, v);
  }
  for (const c of children) if (c != null) node.append(c);
  return node;
}

let toastTimer;
function toast(message, isError = false) {
  const t = $("toast");
  t.textContent = message;
  t.className = "toast" + (isError ? " error" : "");
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), isError ? 5000 : 2500);
}

const unit = () => (state.summary && state.summary.unit) || "";
const fmt = (v, d = 1) => (v === null || v === undefined ? "-" : Number(v).toFixed(d));
function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? "" : d.toLocaleString("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

/* ───────────── 서버 깨우기 (Render 콜드스타트 대응) ───────────── */
async function wakeServer() {
  const pill = $("serverStatus");
  const bannerTimer = setTimeout(() => ($("wakeBanner").hidden = false), 2500);
  let lastError = "";
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const h = await api("/health", { timeout: 70000 });
      clearTimeout(bannerTimer);
      $("wakeBanner").hidden = true;
      pill.textContent = h.openai_configured ? "서버 연결됨" : "서버 연결됨 (AI 키 없음)";
      pill.className = "status-pill " + (h.openai_configured ? "status-ok" : "status-pending");
      return true;
    } catch (e) {
      lastError = e.message;
      if (/CORS|파일로 직접|https 페이지/.test(e.message)) break;   // 기다려도 해결되지 않는 원인
      pill.textContent = `서버 깨우는 중… (${attempt}/3)`;
    }
  }
  clearTimeout(bannerTimer);
  pill.textContent = "서버 연결 실패";
  pill.className = "status-pill status-error";
  const banner = $("wakeBanner");
  banner.replaceChildren(el("span", { class: "diag", text: "⚠️ " + (lastError || "백엔드 서버에 연결하지 못했어요.") }));
  banner.hidden = false;
  return false;
}

/* ───────────── 요약 ───────────── */
async function loadSummary() {
  try {
    state.summary = await api("/api/data/summary");
    renderSummary();
  } catch (e) {
    $("summaryGrid").replaceChildren(el("p", { class: "empty", text: "요약을 불러오지 못했어요: " + e.message }));
  }
}

/* 과거 데이터일 때 기준일 안내: '이번 달', '최근'은 데이터 마지막 날 기준으로 답한다는 것을 알려 준다 */
function renderReference(s) {
  const ref = s.reference_date;
  const note = welcomeNode && welcomeNode.querySelector("#refNote");
  if (s.is_historical && ref) {
    const [y, m] = ref.split("-");
    $("sumRef").textContent = `기준일 ${ref}`;
    $("sumRef").hidden = false;
    if (note) {
      note.textContent = `📅 과거 데이터예요. '이번 달', '최근'은 데이터 기준일(${ref}) 기준, 즉 ${y}년 ${Number(m)}월로 답해요.`;
      note.hidden = false;
    }
  } else {
    $("sumRef").hidden = true;
    if (note) note.hidden = true;
  }
}

/* 추천 질문을 실제 데이터 기간에 맞춰 만든다 (데이터 밖 기간을 묻는 버튼이 생기지 않도록) */
function renderSuggestions(s) {
  const box = welcomeNode && welcomeNode.querySelector("#suggestions");
  if (!box || !s.metrics || !s.monthly.length) return;
  const isTemp = s.unit === "℃";
  const noun = isTemp ? "기온" : s.title;
  const topic = isTemp ? "기온은" : `${s.title}은(는)`;
  const label = (ym) => { const [y, m] = ym.split("-"); return `${y}년 ${Number(m)}월`; };
  const months = s.monthly.map((m) => m.month);
  const prev = months.length > 1 ? months[months.length - 2] : months[0];
  const peak = s.monthly.reduce((a, b) => (b.average > a.average ? b : a)).month;
  const questions = [
    `이번 달 ${topic} 어때?`,
    `가장 ${isTemp ? "더웠던" : "높았던"} 날 TOP 3 알려줘`,
    `${label(prev)} 평균 ${topic} ${isTemp ? "몇 도였어?" : "얼마였어?"}`,
    `${label(peak)} 1일부터 7일까지 ${noun} 알려줘`,
  ];
  box.replaceChildren(...questions.map((q) => el("button", { type: "button", class: "suggestion", text: q })));
}

function trendClass(dir) { return dir === "상승" ? "trend-up" : dir === "하락" ? "trend-down" : ""; }

function renderSummary() {
  const s = state.summary;
  const u = s.unit;
  document.querySelectorAll(".unit").forEach((n) => (n.textContent = u));
  if (welcomeNode) welcomeNode.querySelector("#welcomeTitle").textContent = s.title;
  renderReference(s);
  renderSuggestions(s);
  const dir = s.trend_detail.direction;
  const arrow = { "상승": "↗", "하락": "↘", "유지": "→" }[dir] || "";

  $("sumPeriod").textContent = s.start ? `${s.start.slice(2)} ~ ${s.end.slice(2)}` : "-";
  $("sumCount").textContent = `${s.count}개`;
  $("sumAvg").textContent = s.metrics ? `${fmt(s.metrics.average)}${u}` : "-";
  $("sumTrend").textContent = `${arrow} ${dir}`;
  $("sumTrend").className = trendClass(dir);

  const grid = $("summaryGrid");
  if (!s.metrics) {
    grid.replaceChildren(el("p", { class: "empty", text: "데이터가 없어요. '데이터 관리'에서 추가해 주세요." }));
    $("monthlyTable").replaceChildren();
    return;
  }
  const m = s.metrics;
  const card = (label, value, sub, extra = "") =>
    el("div", { class: "stat-card " + extra }, el("div", { class: "label", text: label }),
      el("div", { class: "value", text: value }), sub ? el("div", { class: "sub", text: sub }) : null);
  const td = s.trend_detail;
  grid.replaceChildren(
    card("기간", s.period, `${s.count}개 데이터`, "wide"),
    card("평균", `${fmt(m.average)}${u}`, `중앙값 ${fmt(m.median)}${u} · 표준편차 ${fmt(m.std)}${u}`),
    card("최근 값", `${fmt(m.latest.value)}${u}`, m.latest.date),
    card("최고", `${fmt(m.max.value)}${u}`, m.max.date),
    card("최저", `${fmt(m.min.value)}${u}`, m.min.date),
    (() => {
      const c = card(`최근 추세 (${td.window_days}일 vs 직전 ${td.window_days}일)`, `${arrow} ${dir}`,
        td.change != null ? `최근 평균 ${fmt(td.recent_average)}${u} · 변화 ${td.change > 0 ? "+" : ""}${fmt(td.change)}${u}` : "데이터 부족", "wide");
      c.querySelector(".value").classList.add(trendClass(dir) || "x");
      return c;
    })(),
  );

  const head = el("tr", {}, ...["월", "평균", "최고", "최저", "일수"].map((h, i) => el("th", { class: i ? "num" : "", text: h })));
  const rows = [...s.monthly].reverse().map((mo) => el("tr", {},
    el("td", { text: mo.month }), el("td", { class: "num", text: fmt(mo.average) + u }),
    el("td", { class: "num", text: fmt(mo.max) + u }), el("td", { class: "num", text: fmt(mo.min) + u }),
    el("td", { class: "num", text: mo.count })));
  $("monthlyTable").replaceChildren(el("thead", {}, head), el("tbody", {}, ...rows));
}

/* ───────────── 그래프 (보너스: canvas 직접 그리기) ───────────── */
async function loadStatistics() {
  try {
    const st = await api("/api/data/statistics?ma_window=7");
    state.series = st.series || [];
    drawChart();
  } catch (e) {
    state.series = [];
    drawChart();
  }
}

let chartGeom = null;
function drawChart() {
  const canvas = $("chart");
  const wrap = canvas.parentElement;
  const dpr = window.devicePixelRatio || 1;
  const W = wrap.clientWidth, H = wrap.clientHeight;
  canvas.width = W * dpr; canvas.height = H * dpr;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);

  const css = getComputedStyle(document.documentElement);
  const color = (v) => css.getPropertyValue(v).trim();
  const range = $("chartRange").value;
  const data = range === "all" ? state.series : state.series.slice(-Number(range));
  chartGeom = null;
  if (data.length < 2) {
    ctx.fillStyle = color("--muted");
    ctx.font = "13px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("그래프를 그릴 데이터가 부족해요", W / 2, H / 2);
    return;
  }

  const pad = { l: 40, r: 10, t: 10, b: 24 };
  const vals = data.flatMap((d) => [d.value, d.moving_average].filter((v) => v != null));
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const span = hi - lo || 1;
  lo -= span * 0.08; hi += span * 0.08;
  const x = (i) => pad.l + (i / (data.length - 1)) * (W - pad.l - pad.r);
  const y = (v) => pad.t + (1 - (v - lo) / (hi - lo)) * (H - pad.t - pad.b);

  // 격자와 y축 눈금
  ctx.strokeStyle = color("--border");
  ctx.fillStyle = color("--muted");
  ctx.font = "11px sans-serif";
  ctx.lineWidth = 1;
  ctx.textAlign = "right";
  for (let k = 0; k <= 4; k++) {
    const v = lo + ((hi - lo) * k) / 4;
    const yy = y(v);
    ctx.beginPath(); ctx.moveTo(pad.l, yy); ctx.lineTo(W - pad.r, yy); ctx.stroke();
    ctx.fillText(v.toFixed(0), pad.l - 6, yy + 4);
  }
  // x축: 월이 바뀌는 지점마다 라벨
  ctx.textAlign = "center";
  let lastLabelX = -999;
  data.forEach((d, i) => {
    const isMonthStart = i === 0 || d.date.slice(0, 7) !== data[i - 1].date.slice(0, 7);
    if (isMonthStart && x(i) - lastLabelX > 40) {
      ctx.fillText(d.date.slice(2, 7).replace("-", "."), x(i), H - 6);
      lastLabelX = x(i);
    }
  });

  const line = (key, stroke, width) => {
    ctx.strokeStyle = stroke; ctx.lineWidth = width; ctx.beginPath();
    let started = false;
    data.forEach((d, i) => {
      if (d[key] == null) { started = false; return; }
      if (!started) { ctx.moveTo(x(i), y(d[key])); started = true; } else ctx.lineTo(x(i), y(d[key]));
    });
    ctx.stroke();
  };
  line("value", color("--chart-value"), 1.2);
  line("moving_average", color("--chart-ma"), 2.2);
  chartGeom = { data, x, y, pad, W };
}

function onChartHover(ev) {
  const tip = $("chartTooltip");
  if (!chartGeom) { tip.hidden = true; return; }
  const { data, x, y, pad, W } = chartGeom;
  const rect = $("chart").getBoundingClientRect();
  const mx = ev.clientX - rect.left;
  const ratio = (mx - pad.l) / (W - pad.l - pad.r);
  const i = Math.round(ratio * (data.length - 1));
  if (i < 0 || i >= data.length) { tip.hidden = true; return; }
  const d = data[i];
  tip.textContent = `${d.date} · ${fmt(d.value)}${unit()}` + (d.moving_average != null ? ` (7일 평균 ${fmt(d.moving_average)}${unit()})` : "");
  tip.hidden = false;
  const left = Math.min(Math.max(x(i) - tip.offsetWidth / 2, 0), W - tip.offsetWidth);
  tip.style.left = left + "px";
  tip.style.top = Math.max(y(d.value) - 34, 0) + "px";
}

/* ───────────── 데이터 관리 (CRUD) ───────────── */
async function loadData(flashId) {
  try {
    state.data = await api("/api/data?order=desc");
    renderDataTable(flashId);
  } catch (e) {
    $("dataTable").replaceChildren(el("tr", {}, el("td", { class: "empty", text: "목록을 불러오지 못했어요: " + e.message })));
  }
}

function renderDataTable(flashId) {
  $("dataCount").textContent = `(${state.data.length}개)`;
  const head = el("tr", {}, el("th", { text: "날짜" }), el("th", { class: "num", text: "값" }), el("th", { text: "메모" }), el("th", { text: "" }));
  const rows = state.data.slice(0, state.shown).map((r) => {
    const tr = el("tr", { "data-id": r.id },
      el("td", { text: r.date }),
      el("td", { class: "num", text: fmt(r.value) + unit() }),
      el("td", { class: "memo-cell", text: r.memo || "", title: r.memo || "" }),
      el("td", { class: "row-actions" },
        el("button", { type: "button", text: "수정", title: "수정", onclick: () => startEdit(r) }),
        el("button", { type: "button", class: "del", text: "삭제", title: "삭제", onclick: () => deleteData(r) })));
    if (r.id === state.editingId) tr.classList.add("editing");
    if (r.id === flashId) tr.classList.add("flash");
    return tr;
  });
  if (!rows.length) rows.push(el("tr", {}, el("td", { colspan: 4, class: "empty", text: "데이터가 없어요." })));
  $("dataTable").replaceChildren(el("thead", {}, head), el("tbody", {}, ...rows));
  $("moreBtn").hidden = state.shown >= state.data.length;
}

function startEdit(r) {
  state.editingId = r.id;
  $("fDate").value = r.date;
  $("fValue").value = r.value;
  $("fMemo").value = r.memo || "";
  $("dataSubmit").textContent = "수정 저장";
  $("dataCancel").hidden = false;
  renderDataTable();
  $("dataForm").scrollIntoView({ behavior: "smooth", block: "nearest" });
  $("fValue").focus();
}

function resetForm() {
  state.editingId = null;
  $("dataForm").reset();
  $("fDate").value = new Date().toISOString().slice(0, 10);
  $("dataSubmit").textContent = "추가";
  $("dataCancel").hidden = true;
  renderDataTable();
}

async function submitData(ev) {
  ev.preventDefault();
  const body = { date: $("fDate").value, value: Number($("fValue").value), memo: $("fMemo").value.trim() };
  if (!body.date || $("fValue").value === "" || !Number.isFinite(body.value)) {
    toast("날짜와 값을 올바르게 입력해 주세요.", true);
    return;
  }
  const btn = $("dataSubmit");
  btn.disabled = true;
  try {
    let saved;
    if (state.editingId) {
      saved = await api(`/api/data/${encodeURIComponent(state.editingId)}`, { method: "PUT", body });
      toast(`✅ ${saved.date} 데이터를 수정했어요.`);
    } else {
      saved = await api("/api/data", { method: "POST", body });
      toast(`✅ ${saved.date} 데이터를 추가했어요.`);
    }
    resetForm();
    await refreshAfterChange(saved.id);
  } catch (e) {
    toast(e.message, true);
  } finally {
    btn.disabled = false;
  }
}

async function deleteData(r) {
  if (!confirm(`${r.date} (${fmt(r.value)}${unit()}) 데이터를 삭제할까요?`)) return;
  try {
    await api(`/api/data/${encodeURIComponent(r.id)}`, { method: "DELETE" });
    if (state.editingId === r.id) resetForm();
    toast(`🗑 ${r.date} 데이터를 삭제했어요.`);
    await refreshAfterChange();
  } catch (e) {
    toast(e.message, true);
  }
}

async function refreshAfterChange(flashId) {
  await Promise.all([loadData(flashId), loadSummary(), loadStatistics()]);
}

/* 내보내기 (보너스) */
function download(filename, content, type) {
  const blob = new Blob([content], { type });
  const a = el("a", { href: URL.createObjectURL(blob), download: filename });
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
}

function exportCsv() {
  const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const rows = [...state.data].reverse().map((r) => [r.date, r.value, esc(r.memo)].join(","));
  download(`data_${today()}.csv`, "﻿" + ["date,value,memo", ...rows].join("\n"), "text/csv;charset=utf-8");
}

function exportJson() {
  const rows = [...state.data].reverse().map(({ date, value, memo }) => ({ date, value, memo }));
  download(`data_${today()}.json`, JSON.stringify({ summary: state.summary, data: rows }, null, 2), "application/json");
}
const today = () => new Date().toISOString().slice(0, 10);

/* ───────────── 대화 기록 ───────────── */
async function loadConversations() {
  try {
    state.conversations = await api("/api/conversations?limit=50");
  } catch (e) {
    state.conversations = [];
    toast("대화 기록을 불러오지 못했어요: " + e.message, true);
  }
  renderConversations();
}

function renderConversations() {
  const list = $("conversationList");
  const items = state.conversations.map((c) => el("li", {
    class: "conv-item" + (c.id === state.conversationId ? " active" : ""),
    tabindex: 0,
    onclick: () => openConversation(c.id),
    onkeydown: (e) => { if (e.key === "Enter") openConversation(c.id); },
  },
  el("div", { class: "conv-main" },
    el("div", { class: "conv-title", text: c.title, title: c.title }),
    el("div", { class: "conv-meta", text: `${fmtTime(c.updated_at)} · 메시지 ${c.message_count}개` })),
  el("button", {
    class: "conv-del", type: "button", title: "대화 삭제", "aria-label": "대화 삭제", text: "✕",
    onclick: (e) => { e.stopPropagation(); deleteConversation(c); },
  })));
  list.replaceChildren(...items);
  $("conversationEmpty").hidden = items.length > 0;
}

async function openConversation(id) {
  if (state.sending) return;
  try {
    const conv = await api(`/api/conversations/${encodeURIComponent(id)}`);
    state.conversationId = conv.id;
    $("chatTitle").textContent = conv.title;
    const box = $("messages");
    box.replaceChildren();
    conv.messages.forEach((m) => box.append(messageNode(m.role, m.content, m.tool_calls, m.timestamp)));
    box.scrollTop = box.scrollHeight;
    renderConversations();
  } catch (e) {
    toast("대화를 불러오지 못했어요: " + e.message, true);
  }
}

async function deleteConversation(c) {
  if (!confirm(`'${c.title}' 대화를 삭제할까요?`)) return;
  try {
    await api(`/api/conversations/${encodeURIComponent(c.id)}`, { method: "DELETE" });
    if (state.conversationId === c.id) newChat();
    toast("대화를 삭제했어요.");
    loadConversations();
  } catch (e) {
    toast(e.message, true);
  }
}

function newChat() {
  state.conversationId = null;
  $("chatTitle").textContent = "새 대화";
  $("messages").replaceChildren(welcomeNode);
  renderConversations();
  $("chatInput").focus();
}

/* ───────────── 채팅 ───────────── */
let welcomeNode;

function messageNode(role, content, toolCalls = [], timestamp, extraMeta) {
  const node = el("div", { class: `msg ${role}` }, el("div", { class: "bubble", text: content }));
  const meta = el("div", { class: "msg-meta" });
  if (timestamp) meta.append(el("span", { text: fmtTime(timestamp) }));
  if (extraMeta) meta.append(el("span", { text: extraMeta }));
  (toolCalls || []).forEach((t) => {
    const args = Object.values(t.arguments || {}).join(" ~ ");
    meta.append(el("span", { class: "tool-chip", title: "AI가 호출한 도구", text: `🔧 ${t.name}${args ? "(" + args + ")" : ""}` }));
  });
  if (meta.childNodes.length) node.append(meta);
  return node;
}

function typingNode() {
  const text = el("span", { class: "typing-text", text: "데이터를 확인하고 답변을 만드는 중…" });
  const node = el("div", { class: "msg assistant", id: "typing" },
    el("div", { class: "bubble" }, el("span", { class: "typing", "aria-label": "답변 생성 중" }, el("i"), el("i"), el("i")), text));
  node._timer = setTimeout(() => (text.textContent = "서버가 깨어나는 중이면 조금 더 걸릴 수 있어요…"), 10000);
  return node;
}

async function sendMessage(text) {
  text = text.trim();
  if (!text || state.sending) return;
  state.sending = true;
  $("sendBtn").disabled = true;
  $("chatInput").value = "";
  autoGrow();

  const box = $("messages");
  if (welcomeNode.isConnected) welcomeNode.remove();
  box.append(messageNode("user", text, [], new Date().toISOString()));
  const typing = typingNode();
  box.append(typing);
  box.scrollTop = box.scrollHeight;

  try {
    const res = await api("/api/chat", { method: "POST", body: { message: text, conversation_id: state.conversationId }, timeout: 120000 });
    const s = res.summary_used || {};
    typing.replaceWith(messageNode("assistant", res.reply, res.tool_calls, new Date().toISOString(),
      `📊 요약 반영: ${s.period || "-"} · ${s.count ?? 0}개` + (s.is_historical ? ` · 기준일 ${s.reference_date}` : "")));
    if (!res.saved) toast("답변은 받았지만 대화 저장에 실패했어요.", true);
    const isNew = !state.conversationId;
    state.conversationId = res.conversation_id;
    if (isNew) $("chatTitle").textContent = text.length > 30 ? text.slice(0, 30) + "…" : text;
    loadConversations();
  } catch (e) {
    typing.replaceWith(el("div", { class: "msg assistant error" }, el("div", { class: "bubble", text: "⚠️ " + e.message })));
  } finally {
    clearTimeout(typing._timer);
    state.sending = false;
    $("sendBtn").disabled = false;
    box.scrollTop = box.scrollHeight;
    $("chatInput").focus();
  }
}

function autoGrow() {
  const ta = $("chatInput");
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 140) + "px";
}

/* ───────────── 테마 / 탭 ───────────── */
function applyThemeIcon() {
  const dark = document.documentElement.dataset.theme === "dark";
  $("themeToggle").textContent = dark ? "☀️" : "🌙";
}

function toggleTheme() {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("theme", next); } catch { /* 저장 불가 환경은 무시 */ }
  applyThemeIcon();
  drawChart();
}

function switchTab(id) {
  document.querySelectorAll(".tab").forEach((t) => {
    const on = t.dataset.tab === id;
    t.classList.toggle("active", on);
    t.setAttribute("aria-selected", on);
  });
  document.querySelectorAll(".tab-body").forEach((b) => (b.hidden = b.id !== id));
  if (id === "summaryTab") drawChart();
}

/* ───────────── 초기화 ───────────── */
function bindEvents() {
  $("chatForm").addEventListener("submit", (e) => { e.preventDefault(); sendMessage($("chatInput").value); });
  $("chatInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendMessage($("chatInput").value); }
  });
  $("chatInput").addEventListener("input", autoGrow);
  $("suggestions").addEventListener("click", (e) => {   // 버튼이 다시 그려져도 동작하도록 위임 방식
    const b = e.target.closest(".suggestion");
    if (b) sendMessage(b.textContent);
  });
  $("newChatBtn").addEventListener("click", newChat);
  $("themeToggle").addEventListener("click", toggleTheme);
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => switchTab(t.dataset.tab)));
  $("dataForm").addEventListener("submit", submitData);
  $("dataCancel").addEventListener("click", resetForm);
  $("moreBtn").addEventListener("click", () => { state.shown += PAGE_SIZE; renderDataTable(); });
  $("exportCsv").addEventListener("click", exportCsv);
  $("exportJson").addEventListener("click", exportJson);
  $("chartRange").addEventListener("change", drawChart);
  $("chart").addEventListener("mousemove", onChartHover);
  $("chart").addEventListener("mouseleave", () => ($("chartTooltip").hidden = true));
  if ("ResizeObserver" in window) new ResizeObserver(() => drawChart()).observe($("chart").parentElement);
}

async function init() {
  console.info("[설정] API_BASE_URL =", API_BASE, "| 현재 페이지 origin =", location.origin);
  welcomeNode = $("welcome");
  $("docsLink").href = API_BASE + "/docs";
  $("fDate").value = today();
  applyThemeIcon();
  bindEvents();
  drawChart();
  const ok = await wakeServer();
  if (!ok) return;
  await Promise.all([loadSummary(), loadStatistics(), loadData(), loadConversations()]);
}

document.addEventListener("DOMContentLoaded", init);

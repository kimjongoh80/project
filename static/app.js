"use strict";

const state = {
  data: null,
  band: "all",
  chanBand: "2.4",
  timeSec: 300,
  search: "",
  hideHidden: false,
  hideStale: true,
  sortKey: "rssi",
  sortAsc: false,
  selected: new Set(),
  paused: false,
};
const STALE_SEC = 30;
const $ = (s) => document.querySelector(s);

// ---------------------------------------------------------------- 테마
// state.theme: "system" | "light" | "dark"
state.theme = "system";
const _lightMQ = window.matchMedia("(prefers-color-scheme: light)");
let _cssCache = {};
function cssVar(name) {
  if (!(name in _cssCache)) _cssCache[name] = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return _cssCache[name];
}
function isLight() {
  return state.theme === "light" || (state.theme === "system" && _lightMQ.matches);
}
function applyTheme(t, save) {
  state.theme = ["light", "dark"].includes(t) ? t : "system";
  if (state.theme === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = state.theme;
  _cssCache = {};
  const sel = document.getElementById("themeSel");
  if (sel) sel.value = state.theme;
  if (save) {
    fetch("/api/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme: state.theme }),
    }).catch(() => {});
  }
  if (typeof render === "function") render();
}
// Windows 라이트/다크 전환 시 즉시 반영
_lightMQ.addEventListener("change", () => { _cssCache = {}; render(); });

// ---------------------------------------------------------------- 유틸
function colorFor(bssid) {
  let h = 0;
  for (const c of bssid) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return isLight() ? `hsl(${h % 360}, 75%, 40%)` : `hsl(${h % 360}, 80%, 60%)`;
}
function withAlpha(hsl, a) { return hsl.replace("hsl(", "hsla(").replace(")", `, ${a})`); }
function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function sigColor(r) {
  if (r >= -60) return "var(--good)";
  if (r >= -70) return "var(--ok)";
  if (r >= -80) return "var(--weak)";
  return "var(--bad)";
}
function ssidLabel(n) { return n.ssid || "(숨김)"; }

function filtered() {
  if (!state.data) return [];
  const q = state.search.trim().toLowerCase();
  return state.data.networks.filter((n) => {
    if (state.band !== "all" && n.band !== state.band) return false;
    if (state.hideHidden && !n.ssid) return false;
    if (state.hideStale && n.age > STALE_SEC) return false;
    if (q && !(`${n.ssid} ${n.bssid} ${n.vendor || ""} ${n.ap_label} ${n.model_label} ${n.security} ${n.phy}`.toLowerCase().includes(q))) return false;
    return true;
  });
}

function sortList(list) {
  const k = state.sortKey, dir = state.sortAsc ? 1 : -1;
  return [...list].sort((a, b) => {
    let x = a[k], y = b[k];
    if (x == null) x = typeof y === "string" ? "" : -Infinity;
    if (y == null) y = typeof x === "string" ? "" : -Infinity;
    if (typeof x === "string") return x.localeCompare(y, "ko") * dir;
    return (x - y) * dir;
  });
}

// 사용자 지정 이름/모델 (settings.aliases[bssid] = {name, model})
state.aliases = {};
function decorate(nets) {
  for (const n of nets) {
    const a = state.aliases[n.bssid] || {};
    n.ap_label = a.name || n.ap_name || "";
    n.model_label = a.model || n.model || "";
    n.group_key = n.ssid || n.bssid;      // 숨김 SSID는 BSSID별로 따로
  }
}

function vendorText(n) {
  if (n.vendor) return n.vendor + (n.vendor_guess ? " (추정)" : "");
  return n.virtual_mac ? "가상 MAC" : "";
}

// ---------------------------------------------------------------- 표: 열 정의
// k: 정렬 키, w: 기본 너비(px), cls: td 클래스(문자열 또는 함수), cell: 내용 HTML
const COLUMNS = [
  { k: "ssid", label: "SSID", w: 230,
    cell: (n) => `<button class="scope" data-group="${esc(n.group_key)}" title="이 SSID의 AP 목록 보기">🔭</button><span class="sw" style="background:${colorFor(n.bssid)}"></span>${n.ssid ? esc(n.ssid) : '<span class="hidden-ssid">(숨김)</span>'}${n.connected ? '<span class="star" title="현재 연결됨">★</span>' : ""}`,
    title: (n) => ssidLabel(n) },
  { k: "ap_label", label: "AP 이름", w: 140, cell: (n) => esc(n.ap_label) || '<span class="muted">-</span>', title: (n) => n.ap_label },
  { k: "bssid", label: "BSSID", w: 145, cls: "mono", cell: (n) => n.bssid },
  { k: "vendor", label: "제조사", w: 190, cls: (n) => (n.vendor && !n.vendor_guess ? "" : "muted"),
    cell: (n) => esc(vendorText(n)) || "-", title: (n) => vendorText(n) },
  { k: "rssi", label: "신호", w: 150, num: true,
    cell: (n) => {
      const pct = Math.max(0, Math.min(100, (n.rssi + 100) * 100 / 70));
      return `<span class="sig">${n.rssi} dBm<span class="bar"><i style="width:${pct}%;background:${sigColor(n.rssi)}"></i></span></span>`;
    } },
  { k: "channel", label: "채널", w: 80, num: true,
    cell: (n) => (n.width > 20 && n.center_channel !== n.channel ? `${n.channel} <span class="muted">(${n.center_channel})</span>` : n.channel) },
  { k: "band", label: "대역", w: 75, cell: (n) => `${n.band} GHz` },
  { k: "width", label: "폭", w: 80, num: true, cell: (n) => `${n.width_label} MHz` },
  { k: "security", label: "보안", w: 160,
    cell: (n) => {
      const c = n.security === "Open" ? "open" : n.security.includes("WPA3") ? "wpa3" : "";
      return `<span class="tag ${c}" title="${esc((n.akm || []).join(", "))} ${esc((n.ciphers || []).join(", "))}">${esc(n.security)}</span>`;
    } },
  { k: "phy", label: "규격", w: 145, cell: (n) => `802.11${n.phy}${n.generation ? ` <span class="muted">${n.generation}</span>` : ""}` },
  { k: "model_label", label: "모델", w: 150, cell: (n) => esc(n.model_label) || '<span class="muted">-</span>', title: (n) => n.model_label },
  { k: "max_rate", label: "최대속도", w: 100, num: true, cell: (n) => (n.max_rate != null ? n.max_rate + " Mbps" : "-") },
  { k: "stations", label: "단말", w: 60, num: true, cell: (n) => n.stations ?? "-" },
  { k: "utilization", label: "사용률", w: 70, num: true, cell: (n) => (n.utilization != null ? n.utilization + "%" : "-") },
  { k: "age", label: "확인", w: 75, num: true, cls: "muted", cell: (n) => (n.age < 1 ? "방금" : Math.round(n.age) + "초 전") },
];
const COL = Object.fromEntries(COLUMNS.map((c) => [c.k, c]));
const MIN_COL_W = 45;
const cols = { order: COLUMNS.map((c) => c.k), widths: Object.fromEntries(COLUMNS.map((c) => [c.k, c.w])) };

function applyColSettings(s) {
  if (!s || typeof s !== "object") return;
  if (Array.isArray(s.order)) {
    const known = s.order.filter((k) => COL[k]);
    cols.order = [...new Set(known), ...COLUMNS.map((c) => c.k).filter((k) => !known.includes(k))];
  }
  if (s.widths && typeof s.widths === "object") {
    for (const k in s.widths) if (COL[k] && Number.isFinite(s.widths[k])) cols.widths[k] = Math.max(MIN_COL_W, Math.min(1000, s.widths[k]));
  }
}

let _saveTimer = null;
function saveColSettings() {
  clearTimeout(_saveTimer);
  _saveTimer = setTimeout(() => {
    fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ columns: { order: cols.order, widths: cols.widths } }),
    }).catch(() => {});
  }, 400);
}

function resetColumns() {
  cols.order = COLUMNS.map((c) => c.k);
  cols.widths = Object.fromEntries(COLUMNS.map((c) => [c.k, c.w]));
  buildHead(); render(); saveColSettings();
  toast("열 순서와 너비를 기본값으로 되돌렸습니다.");
}

function tableWidth() { return cols.order.reduce((s, k) => s + cols.widths[k], 0); }

function applyWidths() {
  document.querySelectorAll("#nets col").forEach((c) => (c.style.width = cols.widths[c.dataset.k] + "px"));
  $("#nets").style.width = tableWidth() + "px";
}

function buildHead() {
  $("#nets colgroup").innerHTML = cols.order.map((k) => `<col data-k="${k}">`).join("");
  $("#nets thead tr").innerHTML = cols.order.map((k) => {
    const c = COL[k];
    return `<th data-k="${k}" class="${c.num ? "num" : ""}" title="드래그: 순서 이동 · 클릭: 정렬"><span class="th-label">${c.label}</span><span class="resizer" title="드래그: 너비 조절 · 더블클릭: 기본 너비"></span></th>`;
  }).join("");
  applyWidths();
}

// ---------------------------------------------------------------- 표: 렌더
function renderTable(list) {
  const k = state.sortKey;
  list = sortList(list);
  document.querySelectorAll("#nets thead th").forEach((th) => {
    th.classList.toggle("sorted", th.dataset.k === k);
    th.classList.toggle("asc", th.dataset.k === k && state.sortAsc);
  });
  const rows = list.map((n) => {
    const cls = [state.selected.has(n.bssid) ? "sel" : "", n.age > STALE_SEC ? "stale" : ""].join(" ");
    const tds = cols.order.map((key) => {
      const c = COL[key];
      const extra = typeof c.cls === "function" ? c.cls(n) : c.cls || "";
      const title = c.title ? ` title="${esc(c.title(n))}"` : "";
      return `<td class="${c.num ? "num " : ""}${extra}"${title}>${c.cell(n)}</td>`;
    }).join("");
    return `<tr data-b="${n.bssid}" class="${cls}">${tds}</tr>`;
  });
  $("#nets tbody").innerHTML = rows.join("");
}

// ---------------------------------------------------------------- 표: 열 이동 / 크기 조절 (마우스 이벤트 직접 처리)
function sortBy(k) {
  if (state.sortKey === k) state.sortAsc = !state.sortAsc;
  else { state.sortKey = k; state.sortAsc = ["ssid", "ap_label", "model_label", "bssid", "vendor", "band", "security", "phy", "age", "channel"].includes(k); }
  render();
}

function initColumnUI() {
  const head = $("#nets thead");
  const ind = $("#dropIndicator");

  head.addEventListener("dblclick", (e) => {
    const r = e.target.closest(".resizer");
    if (!r) return;
    const k = r.parentElement.dataset.k;
    cols.widths[k] = COL[k].w;
    applyWidths(); saveColSettings();
  });

  head.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    const th = e.target.closest("th");
    if (!th) return;
    e.preventDefault();
    const k = th.dataset.k;
    const startX = e.clientX;

    // 1) 크기 조절
    if (e.target.classList.contains("resizer")) {
      const startW = cols.widths[k];
      document.body.classList.add("col-resizing");
      const move = (ev) => {
        cols.widths[k] = Math.max(MIN_COL_W, Math.min(1000, Math.round(startW + ev.clientX - startX)));
        applyWidths();
      };
      const up = () => {
        document.removeEventListener("mousemove", move);
        document.removeEventListener("mouseup", up);
        document.body.classList.remove("col-resizing");
        saveColSettings();
      };
      document.addEventListener("mousemove", move);
      document.addEventListener("mouseup", up);
      return;
    }

    // 2) 순서 이동 (5px 이상 움직이면 드래그, 아니면 클릭 = 정렬)
    let ghost = null, target = null;
    const move = (ev) => {
      if (!ghost) {
        if (Math.abs(ev.clientX - startX) < 5) return;
        ghost = document.createElement("div");
        ghost.className = "col-ghost";
        ghost.textContent = COL[k].label;
        document.body.appendChild(ghost);
        th.classList.add("dragging");
        document.body.classList.add("col-dragging");
      }
      ghost.style.left = ev.clientX + 12 + "px";
      ghost.style.top = ev.clientY + 12 + "px";
      // 마우스 위치에서 가장 가까운 열 경계 찾기
      const ths = [...head.querySelectorAll("th")];
      let best = null;
      ths.forEach((t, i) => {
        const r = t.getBoundingClientRect();
        for (const [x, idx] of [[r.left, i], [r.right, i + 1]]) {
          const d = Math.abs(ev.clientX - x);
          if (!best || d < best.d) best = { d, x, idx };
        }
      });
      target = best.idx;
      const wrap = $(".tablewrap").getBoundingClientRect();
      const x = Math.max(wrap.left, Math.min(wrap.right - 2, best.x));
      Object.assign(ind.style, { display: "block", left: x - 1 + "px", top: wrap.top + "px", height: wrap.height + "px" });
    };
    const up = () => {
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", up);
      if (!ghost) { sortBy(k); return; }
      ghost.remove();
      ind.style.display = "none";
      document.body.classList.remove("col-dragging");
      const from = cols.order.indexOf(k);
      let to = target;
      if (to != null && to !== from && to !== from + 1) {
        cols.order.splice(from, 1);
        if (to > from) to--;
        cols.order.splice(to, 0, k);
        saveColSettings();
      }
      buildHead(); render();
    };
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
  });
}

// ---------------------------------------------------------------- 캔버스 공통
const Y_MIN = -100, Y_MAX = -20;
const PAD = { l: 44, r: 12, t: 14, b: 28 };

function setupCanvas(cv) {
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight;
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
    cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
  }
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return { ctx, w, h };
}
function yAxis(ctx, w, h, lo = Y_MIN, hi = Y_MAX) {
  const y = (v) => PAD.t + (hi - v) * (h - PAD.t - PAD.b) / (hi - lo);
  ctx.font = "11px Segoe UI, Malgun Gothic, -apple-system, Apple SD Gothic Neo, sans-serif";
  ctx.textAlign = "right"; ctx.textBaseline = "middle";
  for (let v = lo; v <= hi; v += 10) {
    ctx.strokeStyle = cssVar("--grid"); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(PAD.l, y(v) + 0.5); ctx.lineTo(w - PAD.r, y(v) + 0.5); ctx.stroke();
    ctx.fillStyle = cssVar("--axis"); ctx.fillText(v, PAD.l - 6, y(v));
  }
  return y;
}
function alphaFor(n) {
  if (state.selected.size === 0) return 1;
  return state.selected.has(n.bssid) ? 1 : 0.12;
}

// ---------------------------------------------------------------- 채널 그래프
const BANDS = {
  "2.4": { lo: 2399, hi: 2497, ticks: [...Array(14)].map((_, i) => i + 1), f: (c) => (c === 14 ? 2484 : 2407 + 5 * c) },
  "5": {
    lo: 5150, hi: 5895,
    ticks: [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140, 144, 149, 153, 157, 161, 165, 169, 173, 177],
    f: (c) => 5000 + 5 * c,
  },
  "6": { lo: 5925, hi: 7125, ticks: [...Array(59)].map((_, i) => 1 + 4 * i), f: (c) => 5950 + 5 * c },
};

function drawChannels(list) {
  const cv = $("#chanGraph");
  const { ctx, w, h } = setupCanvas(cv);
  const B = BANDS[state.chanBand];
  const y = yAxis(ctx, w, h);
  const x = (mhz) => PAD.l + (mhz - B.lo) * (w - PAD.l - PAD.r) / (B.hi - B.lo);

  // x 눈금 (픽셀 간격에 따라 라벨 생략)
  ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.fillStyle = cssVar("--axis");
  let lastX = -1e9;
  for (const c of B.ticks) {
    const px = x(B.f(c));
    ctx.strokeStyle = cssVar("--grid2");
    ctx.beginPath(); ctx.moveTo(px + 0.5, PAD.t); ctx.lineTo(px + 0.5, h - PAD.b); ctx.stroke();
    if (px - lastX >= 22) { ctx.fillText(c, px, h - PAD.b + 6); lastX = px; }
  }

  const nets = list.filter((n) => n.band === state.chanBand).sort((a, b) => a.rssi - b.rssi);
  const base = y(Y_MIN);
  const labels = [];
  for (const n of nets) {
    const lo = n.center_freq - n.width / 2, hi = n.center_freq + n.width / 2;
    const top = y(Math.max(Y_MIN, Math.min(Y_MAX, n.rssi)));
    const slope = Math.min(4, n.width * 0.12);
    const x0 = x(lo), x1 = x(lo + slope), x2 = x(hi - slope), x3 = x(hi);
    const col = colorFor(n.bssid), a = alphaFor(n);
    ctx.beginPath();
    ctx.moveTo(x0, base);
    ctx.bezierCurveTo(x0 + (x1 - x0) * 0.6, base, x0 + (x1 - x0) * 0.4, top, x1, top);
    ctx.lineTo(x2, top);
    ctx.bezierCurveTo(x2 + (x3 - x2) * 0.6, top, x2 + (x3 - x2) * 0.4, base, x3, base);
    ctx.fillStyle = withAlpha(col, 0.10 * a);
    ctx.fill();
    ctx.strokeStyle = withAlpha(col, a);
    ctx.lineWidth = state.selected.has(n.bssid) || n.connected ? 2.5 : 1.3;
    ctx.stroke();
    if (a === 1) labels.push({ x: (x1 + x2) / 2, y: top - 4, t: ssidLabel(n), col });
  }

  // 라벨: 겹치지 않게 간단 배치 (강한 신호 우선)
  ctx.font = "11px Segoe UI, Malgun Gothic, -apple-system, Apple SD Gothic Neo, sans-serif";
  ctx.textAlign = "center"; ctx.textBaseline = "bottom";
  const placed = [];
  for (const L of labels.reverse()) {
    const tw = ctx.measureText(L.t).width;
    let ly = L.y;
    for (let tries = 0; tries < 6; tries++) {
      const hit = placed.some((p) => Math.abs(p.x - L.x) < (p.w + tw) / 2 + 2 && Math.abs(p.y - ly) < 12);
      if (!hit) break;
      ly += 12;
    }
    if (ly > h - PAD.b - 4) continue;
    placed.push({ x: L.x, y: ly, w: tw });
    ctx.fillStyle = L.col;
    ctx.fillText(L.t, L.x, ly);
  }

  if (!nets.length) {
    ctx.fillStyle = cssVar("--axis"); ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(`${state.chanBand} GHz 대역에서 감지된 AP가 없습니다`, w / 2, h / 2);
  }
}

// ---------------------------------------------------------------- 시간 그래프
// opts: { cv, span, auto(세로축 자동 범위), plain(선택 강조 무시) }
function drawTime(list, opts = {}) {
  const cv = opts.cv || $("#timeGraph");
  const { ctx, w, h } = setupCanvas(cv);
  const span = opts.span || state.timeSec;
  let lo = Y_MIN, hi = Y_MAX;
  if (opts.auto) {
    const vals = list.flatMap((n) => n.history.filter(([t, r]) => t >= -span && r != null).map(([, r]) => r));
    if (vals.length) {
      lo = Math.max(-100, Math.floor((Math.min(...vals) - 5) / 10) * 10);
      hi = Math.min(-10, Math.ceil((Math.max(...vals) + 5) / 10) * 10);
      if (hi - lo < 30) lo = Math.max(-100, hi - 30);
    }
  }
  const y = yAxis(ctx, w, h, lo, hi);
  const alpha = opts.plain ? () => 1 : alphaFor;
  const x = (t) => PAD.l + (t + span) * (w - PAD.l - PAD.r) / span;

  ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.fillStyle = cssVar("--axis");
  const step = span <= 60 ? 10 : span <= 300 ? 60 : 120;
  for (let t = -span; t <= 0; t += step) {
    const px = x(t);
    ctx.strokeStyle = cssVar("--grid2");
    ctx.beginPath(); ctx.moveTo(px + 0.5, PAD.t); ctx.lineTo(px + 0.5, h - PAD.b); ctx.stroke();
    const label = t === 0 ? "지금" : span <= 60 ? `${-t}초` : `${-t / 60}분`;
    ctx.fillText(label, px, h - PAD.b + 6);
  }

  ctx.save();
  ctx.beginPath(); ctx.rect(PAD.l, PAD.t, w - PAD.l - PAD.r, h - PAD.t - PAD.b); ctx.clip();
  const order = [...list].sort((a, b) => alpha(a) - alpha(b));
  for (const n of order) {
    const col = colorFor(n.bssid), a = alpha(n);
    ctx.strokeStyle = withAlpha(col, a);
    ctx.lineWidth = opts.plain ? 2.2 : state.selected.has(n.bssid) || n.connected ? 2.5 : 1.3;
    ctx.beginPath();
    let pen = false;
    for (const [t, r] of n.history) {
      if (t < -span - 10 || r == null) { pen = false; continue; }
      const px = x(t), py = y(Math.max(lo, r));
      if (pen) ctx.lineTo(px, py); else { ctx.moveTo(px, py); pen = true; }
    }
    ctx.stroke();
    // 점 하나만 있을 때도 보이게
    const last = n.history[n.history.length - 1];
    if (last && last[1] != null) {
      ctx.fillStyle = withAlpha(col, a);
      ctx.beginPath(); ctx.arc(x(last[0]), y(Math.max(lo, last[1])), 2.5, 0, Math.PI * 2); ctx.fill();
    }
  }
  ctx.restore();
  if (!list.length || !list.some((n) => n.history.some(([t, r]) => t >= -span && r != null))) {
    ctx.fillStyle = cssVar("--axis"); ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText("표시할 신호 기록이 없습니다", w / 2, h / 2);
  }
}

// ---------------------------------------------------------------- 헤더
function renderHeader(d) {
  $("#iface").textContent = d.interface || "어댑터 확인 중…";
  $("#conn").innerHTML = d.connected
    ? `연결: <b>${esc(d.connected.ssid)}</b> <span class="muted mono">${d.connected.bssid}</span> · ${d.connected.rx_mbps} Mbps`
    : '<span class="muted">연결 안 됨</span>';
  $("#status").textContent = `스캔 ${d.scan_count}회 · ${d.interval}초 주기`;
  const err = $("#error");
  err.hidden = !d.error;
  err.textContent = d.error || "";

  const all = d.networks.filter((n) => !state.hideStale || n.age <= STALE_SEC);
  const counts = { all: all.length, "2.4": 0, "5": 0, "6": 0 };
  all.forEach((n) => (counts[n.band] = (counts[n.band] || 0) + 1));
  document.querySelectorAll("#bandChips button").forEach((b) => {
    const k = b.dataset.band;
    b.textContent = `${k === "all" ? "전체" : k + " GHz"} (${counts[k] || 0})`;
  });
}

function render() {
  if (!state.data) return;
  const list = filtered();
  renderHeader(state.data);
  renderTable(list);
  drawChannels(list);
  drawTime(list);
  $("#count").textContent = `${list.length}개 표시`;
  $("#clearSel").hidden = state.selected.size === 0;
}

async function poll() {
  if (!state.paused) {
    try {
      const r = await fetch("/api/state", { cache: "no-store" });
      state.data = await r.json();
      decorate(state.data.networks);
      render();
    } catch (e) {
      const err = $("#error");
      err.hidden = false;
      err.textContent = "서버에 연결할 수 없습니다. server.py가 실행 중인지 확인하세요.";
    }
  }
  setTimeout(poll, 2000);
}

// ---------------------------------------------------------------- CSV 내보내기
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.hidden = true), 5000);
}

function buildCsv(list) {
  const cols = [
    ["SSID", (n) => n.ssid], ["BSSID", (n) => n.bssid], ["제조사", vendorText],
    ["RSSI(dBm)", (n) => n.rssi], ["신호품질(%)", (n) => n.quality],
    ["채널", (n) => n.channel], ["중심채널", (n) => n.center_channel], ["대역(GHz)", (n) => n.band],
    ["주파수(MHz)", (n) => n.freq], ["채널폭(MHz)", (n) => n.width_label],
    ["보안", (n) => n.security], ["AKM", (n) => (n.akm || []).join(" ")], ["암호화", (n) => (n.ciphers || []).join(" ")],
    ["AP 이름", (n) => n.ap_label], ["모델", (n) => n.model_label],
    ["규격", (n) => "802.11" + n.phy], ["모드", (n) => n.modes], ["세대", (n) => n.generation],
    ["최대속도(Mbps)", (n) => n.max_rate], ["공간 스트림", (n) => n.nss], ["기본 속도", (n) => (n.basic_rates || []).join(" ")],
    ["단말 수", (n) => n.stations], ["채널사용률(%)", (n) => n.utilization], ["국가", (n) => n.country],
    ["비콘주기", (n) => n.beacon], ["연결됨", (n) => (n.connected ? "Y" : "")],
    ["최초 확인", (n) => new Date(n.first_seen * 1000).toLocaleString("ko-KR")],
    ["마지막 확인", (n) => new Date(n.last_seen * 1000).toLocaleString("ko-KR")],
  ];
  const cell = (v) => {
    if (v == null) return "";
    if (typeof v === "number") return String(v);
    const s = String(v);
    return /[",\n\r]/.test(s) || /^[=+\-@]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [cols.map((c) => c[0]).join(",")];
  for (const n of list) lines.push(cols.map(([, f]) => cell(f(n))).join(","));
  return lines.join("\r\n") + "\r\n";
}

async function exportCsv() {
  const list = sortList(filtered());
  if (!list.length) return toast("저장할 항목이 없습니다.");
  const csv = buildCsv(list);
  const d = new Date(), p = (x) => String(x).padStart(2, "0");
  const name = `wifi_scan_${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}.csv`;
  if (window.pywebview && window.pywebview.api && window.pywebview.api.save_csv) {
    try {
      const path = await window.pywebview.api.save_csv(csv, name);
      if (path) toast(`${list.length}개 저장됨: ${path}`);
    } catch (e) {
      toast("저장 실패: " + e);
    }
    return;
  }
  // 브라우저 모드: BOM을 붙여 엑셀에서 한글이 깨지지 않게
  const url = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast(`${list.length}개 저장: ${name}`);
}

// ---------------------------------------------------------------- 이벤트
$("#exportCsv").addEventListener("click", exportCsv);
function chipGroup(sel, attr, apply) {
  document.querySelectorAll(`${sel} button`).forEach((b) =>
    b.addEventListener("click", () => {
      document.querySelectorAll(`${sel} button`).forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      apply(b.dataset[attr]);
      render();
    }));
}
chipGroup("#bandChips", "band", (v) => {
  state.band = v;
  if (v !== "all") {
    state.chanBand = v;
    document.querySelectorAll("#chanChips button").forEach((x) => x.classList.toggle("on", x.dataset.band === v));
  }
});
chipGroup("#chanChips", "band", (v) => (state.chanBand = v));
chipGroup("#timeChips", "sec", (v) => (state.timeSec = +v));

$("#search").addEventListener("input", (e) => { state.search = e.target.value; render(); });
$("#hideHidden").addEventListener("change", (e) => { state.hideHidden = e.target.checked; render(); });
$("#hideStale").addEventListener("change", (e) => { state.hideStale = e.target.checked; render(); });
$("#clearSel").addEventListener("click", () => { state.selected.clear(); render(); });
$("#pause").addEventListener("click", (e) => {
  state.paused = !state.paused;
  e.target.textContent = state.paused ? "▶ 재개" : "⏸ 일시정지";
  e.target.classList.toggle("on", state.paused);
});
// ---------------------------------------------------------------- 그래프 영역 높이 조절 (표 ↕ 그래프 사이 막대)
state.graphH = null;   // px, null = 기본(창 높이의 32%)
const GRAPH_MIN = 140;
function graphHeight() {
  const def = Math.max(180, Math.round(window.innerHeight * 0.32));
  const max = Math.max(GRAPH_MIN, window.innerHeight - 300);   // 표가 최소한 보이도록
  return Math.min(max, Math.max(GRAPH_MIN, state.graphH ?? def));
}
function applyGraphHeight() {
  document.documentElement.style.setProperty("--graphs-h", graphHeight() + "px");
}
function saveGraphHeight() {
  fetch("/api/settings", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ graphHeight: state.graphH }),
  }).catch(() => {});
}
(function initGraphSplit() {
  const bar = $("#graphSplit");
  let raf = 0;
  bar.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const startY = e.clientY, startH = graphHeight();
    document.body.classList.add("row-resizing");
    const move = (ev) => {
      state.graphH = startH - (ev.clientY - startY);   // 위로 끌면 그래프가 커짐
      state.graphH = graphHeight();
      applyGraphHeight();
      if (!raf) raf = requestAnimationFrame(() => { raf = 0; render(); });
    };
    const up = () => {
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", up);
      document.body.classList.remove("row-resizing");
      saveGraphHeight();
    };
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
  });
  bar.addEventListener("dblclick", () => {
    state.graphH = null;
    applyGraphHeight(); render(); saveGraphHeight();
    toast("그래프 높이를 기본값으로 되돌렸습니다.");
  });
})();

$("#resetCols").addEventListener("click", resetColumns);
$("#themeSel").addEventListener("change", (e) => applyTheme(e.target.value, true));
$("#nets tbody").addEventListener("click", (e) => {
  const tr = e.target.closest("tr");
  if (!tr) return;
  const b = tr.dataset.b;
  if (e.ctrlKey || e.metaKey) {
    state.selected.has(b) ? state.selected.delete(b) : state.selected.add(b);
  } else if (state.selected.size === 1 && state.selected.has(b)) {
    state.selected.clear();
  } else {
    state.selected = new Set([b]);
  }
  render();
});
window.addEventListener("resize", () => { applyGraphHeight(); render(); });
applyGraphHeight();

// 시작: 저장된 열 설정을 불러온 뒤 표 머리글을 만들고 갱신 시작
(async () => {
  try {
    const s = await (await fetch("/api/settings", { cache: "no-store" })).json();
    applyColSettings(s.columns);
    if (s.aliases && typeof s.aliases === "object") state.aliases = s.aliases;
    applyTheme(s.theme, false);
    if (Number.isFinite(s.graphHeight)) { state.graphH = s.graphHeight; applyGraphHeight(); }
  } catch (e) { /* 설정이 없으면 기본값 */ }
  buildHead();
  initColumnUI();
  poll();
})();

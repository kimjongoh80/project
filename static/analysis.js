"use strict";
// 채널 혼잡도 분석 + 추천 채널. app.js의 state / render / setupCanvas / esc 를 사용한다.

const ana = { exMine: true, width: 80, incDfs: false };
const AVG_SEC = 60;

const CH5 = [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140, 144, 149, 153, 157, 161, 165];
const STARTS5 = {
  20: CH5,
  40: [36, 44, 52, 60, 100, 108, 116, 124, 132, 140, 149, 157],
  80: [36, 52, 100, 116, 132, 149],
  160: [36, 100],
};
const chFreq = (band, c) => (band === "2.4" ? (c === 14 ? 2484 : 2407 + 5 * c) : band === "5" ? 5000 + 5 * c : 5950 + 5 * c);

// 후보 채널(블록) 목록
function candidates(band, width) {
  const out = [];
  const mk = (start, n) => {
    const chans = [...Array(n)].map((_, i) => start + 4 * i);
    const center = start + 2 * (n - 1);
    const cf = chFreq(band, center);
    return {
      band, chans, center, width: n * 20,
      lo: cf - n * 10, hi: cf + n * 10,
      label: n === 1 ? String(start) : `${start}–${chans[n - 1]}`,
      dfs: band === "5" && chans.some((c) => c >= 52 && c <= 144),
    };
  };
  if (band === "2.4") {
    for (let c = 1; c <= 13; c++) {
      const b = mk(c, 1);
      b.eligible = [1, 6, 11].includes(c);
      out.push(b);
    }
    return out;
  }
  const n = width / 20;
  if (band === "5") {
    for (const s of STARTS5[width]) out.push(mk(s, n));
  } else if (width === 20) {
    for (let c = 5; c <= 229; c += 16) out.push(mk(c, 1));      // PSC 채널
  } else {
    for (let s = 1; s + 4 * (n - 1) <= 233; s += 4 * n) out.push(mk(s, n));
  }
  out.forEach((b) => (b.eligible = !(b.dfs && !ana.incDfs)));
  return out;
}

// 최근 60초 평균 수신 전력(mW)
function avgPower(n) {
  let sum = 0, cnt = 0;
  for (const [t, r] of n.history || []) {
    if (t >= -AVG_SEC && r != null) { sum += Math.pow(10, r / 10); cnt++; }
  }
  return cnt ? sum / cnt : Math.pow(10, n.rssi / 10);
}

function isMine(n, conn) {
  if (!conn) return false;
  const c = conn.bssid;
  return n.bssid === c || n.bssid.slice(3) === c.slice(3) || n.bssid.slice(0, 14) === c.slice(0, 14);
}

function scoreSpan(lo, hi, nets) {
  let total = 0, count = 0;
  const contrib = [];
  for (const n of nets) {
    let alo = n.center_freq - n.width / 2, ahi = n.center_freq + n.width / 2;
    if (n.band === "2.4") { alo -= 1; ahi += 1; }   // 2.4 GHz 실제 점유폭 ≈ 22 MHz
    const ov = Math.min(hi, ahi) - Math.max(lo, alo);
    if (ov <= 0) continue;
    const p = n._p * ov / (ahi - alo);
    total += p; count++;
    contrib.push({ n, p });
  }
  contrib.sort((a, b) => b.p - a.p);
  return { total, count, dbm: total > 0 ? 10 * Math.log10(total) : null, top: contrib.slice(0, 3) };
}

function level(dbm) {
  if (dbm == null) return { t: "비어 있음", c: "var(--good)", k: 0 };
  if (dbm <= -85) return { t: "좋음", c: "var(--good)", k: 1 };
  if (dbm <= -75) return { t: "양호", c: "var(--ok)", k: 2 };
  if (dbm <= -65) return { t: "혼잡", c: "var(--weak)", k: 3 };
  return { t: "매우 혼잡", c: "var(--bad)", k: 4 };
}
const fmtDbm = (d) => (d == null ? "간섭 없음" : `${d.toFixed(0)} dBm`);

function analyzeBand(band, nets, mine) {
  const width = band === "2.4" ? 20 : ana.width;
  const bandNets = nets.filter((n) => n.band === band);
  const cands = candidates(band, width).map((b) => Object.assign(b, scoreSpan(b.lo, b.hi, bandNets)));
  const pick = cands.filter((b) => b.eligible).sort((a, b) =>
    (a.total - b.total) || (a.count - b.count) || (a.dfs - b.dfs) || (a.center - b.center))[0] || null;
  let current = null;
  if (mine && mine.band === band) {
    const s = scoreSpan(mine.center_freq - mine.width / 2, mine.center_freq + mine.width / 2, bandNets);
    current = Object.assign(s, { net: mine });
  }
  return { band, width, cands, pick, current, apCount: bandNets.length };
}

// ---------------------------------------------------------------- 카드
function cardHtml(r) {
  const title = `${r.band} GHz${r.band === "2.4" ? "" : ` · ${r.width} MHz`}`;
  if (!r.pick) {
    return `<div class="card"><h3>${title}</h3><div class="big">추천 불가</div>
      <div class="row muted">${r.band === "5" && r.width === 160
        ? "5 GHz 160 MHz 채널(36–64, 100–128)은 모두 DFS 채널을 포함합니다. 위의 'DFS 채널도 추천'을 켜세요."
        : "조건에 맞는 후보 채널이 없습니다. 'DFS 채널도 추천' 옵션을 확인하세요."}</div></div>`;
  }
  const L = level(r.pick.dbm);
  const pickCh = r.pick.chans.length > 1 ? `${r.pick.label}` : `채널 ${r.pick.label}`;
  let html = `<div class="card" style="border-left-color:${L.c}">
    <h3>${title} 추천</h3>
    <div class="big">${pickCh}${r.pick.dfs ? "<small>DFS</small>" : ""}</div>
    <div class="row">${fmtDbm(r.pick.dbm)} · 겹치는 AP ${r.pick.count}개 · <span class="lv" style="color:${L.c}">${L.t}</span></div>`;
  if (r.apCount === 0) {
    html += `<div class="row muted">이 대역에서 감지된 AP가 없어 어느 채널이든 깨끗합니다.</div>`;
  } else if (r.pick.top.length) {
    html += `<div class="row muted">주요 간섭원: ${r.pick.top.map((c) => esc(c.n.ssid || "(숨김)")).join(", ")}</div>`;
  }
  if (r.band === "5" && !ana.incDfs) {
    const d = r.cands.filter((b) => b.dfs).sort((a, b) => a.total - b.total)[0];
    const gain = d ? (r.pick.dbm ?? -100) - (d.dbm ?? -100) : 0;
    if (d && gain >= 6) {
      html += `<div class="row muted">참고: DFS 채널 <b>${d.label}</b>은(는) ${d.dbm == null ? "간섭이 없습니다" : fmtDbm(d.dbm)}${d.dbm == null ? "" : `로 약 ${gain.toFixed(0)} dB 더 깨끗합니다`}.
        DFS는 레이더 감지 시 AP가 채널을 옮기고 일부 단말이 지원하지 않을 수 있어 기본 추천에서 제외했습니다.</div>`;
    }
  }
  if (r.current) {
    const n = r.current.net, CL = level(r.current.dbm);
    const curLabel = n.width > 20 ? `ch ${n.channel} (${n.width_label} MHz)` : `ch ${n.channel}`;
    const inPick = r.pick.chans.includes(n.channel) && (r.band === "2.4" || n.width === r.width);
    let diff = "";
    if (inPick) diff = " · <b style='color:var(--good)'>이미 최적 채널입니다</b>";
    else {
      const a = r.current.dbm ?? -100, b = r.pick.dbm ?? -100;
      const d = a - b;
      if (r.pick.dbm == null && r.current.dbm != null) diff = " · 추천 채널로 바꾸면 <b>간섭이 거의 없어집니다</b>";
      else diff = d >= 3 ? ` · 추천 채널로 바꾸면 간섭 약 <b>${d.toFixed(0)} dB</b> 감소` : " · 현재 채널도 충분히 괜찮습니다";
    }
    html += `<div class="cur">현재 연결: <b>${esc(n.ssid)}</b> ${curLabel} — ${fmtDbm(r.current.dbm)}, 겹치는 AP ${r.current.count}개,
      <span class="lv" style="color:${CL.c}">${CL.t}</span>${diff}</div>`;
  }
  return html + "</div>";
}

// ---------------------------------------------------------------- 막대 그래프
function drawBars(cv, r) {
  const { ctx, w, h } = setupCanvas(cv);
  const P = { l: 44, r: 12, t: 22, b: 34 };
  const YMIN = -100, YMAX = -30;
  const y = (v) => P.t + (YMAX - v) * (h - P.t - P.b) / (YMAX - YMIN);
  ctx.font = "11px Segoe UI, Malgun Gothic, -apple-system, Apple SD Gothic Neo, sans-serif";
  ctx.textAlign = "right"; ctx.textBaseline = "middle";
  for (let v = YMIN; v <= YMAX; v += 10) {
    ctx.strokeStyle = cssVar("--grid");
    ctx.beginPath(); ctx.moveTo(P.l, y(v) + 0.5); ctx.lineTo(w - P.r, y(v) + 0.5); ctx.stroke();
    ctx.fillStyle = cssVar("--axis"); ctx.fillText(v, P.l - 6, y(v));
  }
  const css = getComputedStyle(document.documentElement);
  const color = (L) => css.getPropertyValue(L.c.slice(4, -1)).trim();
  const N = r.cands.length, slot = (w - P.l - P.r) / N, bw = Math.min(42, slot * 0.7);
  const mine = r.current && r.current.net;

  r.cands.forEach((b, i) => {
    const cx = P.l + slot * (i + 0.5);
    const L = level(b.dbm);
    const v = b.dbm == null ? YMIN : Math.max(YMIN, Math.min(YMAX, b.dbm));
    const top = y(v), base = y(YMIN);
    ctx.globalAlpha = b.eligible ? 1 : 0.35;
    ctx.fillStyle = color(L);
    ctx.fillRect(cx - bw / 2, top, bw, Math.max(2, base - top));
    if (r.pick === b) {
      ctx.globalAlpha = 1;
      ctx.strokeStyle = cssVar("--strong"); ctx.lineWidth = 2;
      ctx.strokeRect(cx - bw / 2 - 2, top - 2, bw + 4, Math.max(2, base - top) + 4);
    }
    ctx.globalAlpha = b.eligible ? 1 : 0.5;
    ctx.fillStyle = cssVar("--strong"); ctx.textAlign = "center"; ctx.textBaseline = "bottom";
    ctx.fillText(b.count, cx, top - 4);
    ctx.fillStyle = cssVar("--axis"); ctx.textBaseline = "top";
    ctx.fillText(b.label, cx, h - P.b + 5);
    const isCur = mine && (r.band === "2.4" ? b.chans[0] === mine.channel : b.chans.includes(mine.channel));
    if (isCur) {
      ctx.globalAlpha = 1; ctx.fillStyle = cssVar("--accent");
      ctx.fillText("▲ 현재", cx, h - P.b + 18);
    }
    ctx.globalAlpha = 1;
  });
}

// ---------------------------------------------------------------- 렌더
function renderAnalysis() {
  if (!state.data || $("#viewAnalysis").hidden) return;
  const conn = state.data.connected;
  const all = state.data.networks.filter((n) => n.age <= 30);
  const mine = all.find((n) => n.connected) || null;
  const nets = all.filter((n) => !(ana.exMine && isMine(n, conn)));
  nets.forEach((n) => (n._p = avgPower(n)));

  const res = ["2.4", "5", "6"].map((b) => analyzeBand(b, nets, mine));
  $("#anaCards").innerHTML = res.map(cardHtml).join("");
  drawBars($("#ana24"), res[0]);
  drawBars($("#ana5"), res[1]);
  drawBars($("#ana6"), res[2]);
  $("#ana5note").textContent = `${ana.width} MHz 블록 · ${ana.incDfs ? "DFS 포함" : "흐린 막대 = DFS(추천 제외)"}`;
  $("#ana6note").textContent = ana.width === 20 ? "PSC 채널" : `${ana.width} MHz 블록`;
}

// app.js의 render()가 호출될 때마다 분석 화면도 갱신
const _baseRender = render;
render = function () { _baseRender(); renderAnalysis(); };

document.querySelectorAll("#viewTabs button").forEach((btn) =>
  btn.addEventListener("click", () => {
    state.detail = null;
    showView(btn.dataset.view);
  }));

// 화면 전환 (상세 화면은 '네트워크' 탭에 속함)
function showView(id) {
  document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== id));
  const tab = id === "viewAnalysis" ? "viewAnalysis" : "viewNetworks";
  document.querySelectorAll("#viewTabs button").forEach((b) => b.classList.toggle("on", b.dataset.view === tab));
  render();
}
$("#exMine").addEventListener("change", (e) => { ana.exMine = e.target.checked; renderAnalysis(); });
$("#incDfs").addEventListener("change", (e) => { ana.incDfs = e.target.checked; renderAnalysis(); });
$("#anaWidth").addEventListener("change", (e) => { ana.width = +e.target.value; renderAnalysis(); });

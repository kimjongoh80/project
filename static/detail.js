"use strict";
// 상세 화면: 네트워크 › SSID 그룹(같은 SSID의 AP 목록) › AP 상세
// app.js / analysis.js 의 state, render, showView, drawTime, esc, colorFor 등을 사용한다.

state.detail = null;          // null | { type: "group", key } | { type: "ap", key, bssid }
state.detailSpan = 300;
const editing = { field: null };   // 편집 중에는 상세 패널을 다시 그리지 않음

function groupNets(key) {
  return (state.data ? state.data.networks : []).filter((n) => n.group_key === key);
}
function findNet(bssid) {
  return state.data ? state.data.networks.find((n) => n.bssid === bssid) : null;
}
function groupTitle(key) {
  const n = groupNets(key)[0];
  return n && n.ssid ? n.ssid : `(숨김) ${key}`;
}
function radioLabel(n) { return n.ap_label || n.bssid; }
function ago(age) { return age < 1 ? "방금" : age < 60 ? `${Math.round(age)}초 전` : `${Math.round(age / 60)}분 전`; }
function rateList(a) { return a && a.length ? a.join(", ") : "-"; }

function openGroup(key) { state.detail = { type: "group", key }; showView("viewGroup"); }
function openAP(bssid) {
  const n = findNet(bssid);
  if (!n) return;
  state.detail = { type: "ap", key: n.group_key, bssid };
  showView("viewAP");
}
function navTo(where) {
  editing.field = null;
  if (where === "group" && state.detail) openGroup(state.detail.key);
  else { state.detail = null; showView("viewNetworks"); }
}

// ---------------------------------------------------------------- SSID 그룹 화면
function renderGroup() {
  const d = state.detail;
  const nets = groupNets(d.key).sort((a, b) => b.rssi - a.rssi);
  $("#gTitle").textContent = groupTitle(d.key);
  $("#gTable tbody").innerHTML = nets.map((n) => `
    <tr data-b="${n.bssid}" class="${n.age > STALE_SEC ? "stale" : ""}">
      <td><span class="sw" style="background:${colorFor(n.bssid)}"></span><b>${esc(radioLabel(n))}</b>${n.connected ? '<span class="star" title="현재 연결됨">★</span>' : ""}
        ${n.model_label ? `<span class="muted small"> · ${esc(n.model_label)}</span>` : ""}</td>
      <td class="mono">${n.bssid}</td>
      <td class="num" style="color:${sigColor(n.rssi)};font-weight:600">${n.rssi} dBm</td>
      <td class="num">${n.stations ?? "-"}</td>
      <td class="num">${n.channel}</td>
      <td class="num">${n.width_label} MHz</td>
      <td><span class="tag">${esc(n.security)}</span></td>
      <td>${esc(n.modes || n.phy)}</td>
      <td class="num">${rateList(n.basic_rates)}</td>
      <td class="num">${n.max_rate ?? "-"}</td>
      <td class="num muted">${ago(n.age)}</td>
    </tr>`).join("") || `<tr><td colspan="11" class="muted">이 SSID의 AP가 더 이상 보이지 않습니다.</td></tr>`;
  drawTime(nets, { cv: $("#gGraph"), span: state.detailSpan, auto: true, plain: true });
}

// ---------------------------------------------------------------- AP 상세 화면
function row(label, value, cls = "") {
  return `<div class="kv ${cls}"><span class="k">${label}</span><span class="v">${value}</span></div>`;
}
function editable(field, n, value, placeholder) {
  if (editing.field === field) {
    return `<span class="editbox"><input id="editInput" data-field="${field}" value="${esc(value)}" placeholder="${esc(placeholder)}" maxlength="64">
      <button class="mini" data-act="save">저장</button><button class="mini" data-act="cancel">취소</button></span>`;
  }
  const custom = state.aliases[n.bssid] && state.aliases[n.bssid][field];
  return `${value ? esc(value) : `<span class="muted">${esc(placeholder)}</span>`}
    ${custom ? '<span class="badge" title="직접 지정한 값">사용자</span>' : ""}
    <button class="pencil" data-edit="${field}" title="직접 입력">✎</button>`;
}

function renderAP(force = false) {
  const d = state.detail;
  const n = findNet(d.bssid);
  $("#aGroup").textContent = groupTitle(d.key);
  if (!n) {
    $("#aTitle").textContent = d.bssid;
    $("#apInfo").innerHTML = `<p class="muted">이 AP가 더 이상 보이지 않습니다.</p>`;
    drawTime([], { cv: $("#apGraph"), span: state.detailSpan });
    return;
  }
  $("#aTitle").textContent = radioLabel(n);
  drawTime([n], { cv: $("#apGraph"), span: state.detailSpan, auto: true, plain: true });
  if (editing.field && !force) return;   // 입력 중에는 패널을 갱신하지 않음

  const wps = n.wps || {};
  const autoName = n.ap_name || "";
  const siblings = state.data.networks.filter((x) => x.bssid !== n.bssid &&
    (x.bssid.slice(3) === n.bssid.slice(3) || x.bssid.slice(0, 14) === n.bssid.slice(0, 14) ||
     (n.ap_name && x.ap_name === n.ap_name)));
  const util = n.utilization;
  const feats = n.features && n.features.length ? n.features.map((f) => `<span class="tag">${f}</span>`).join(" ") : "-";

  $("#apInfo").innerHTML = `
    <h4>식별 정보</h4>
    ${row("SSID", n.ssid ? esc(n.ssid) : '<span class="hidden-ssid">(숨김)</span>')}
    ${row("AP 이름", editable("name", n, n.ap_label, autoName ? autoName : "방송되지 않음"))}
    ${row("MAC 주소", `<span class="mono">${n.bssid.toUpperCase()}</span>${n.virtual_mac ? ' <span class="muted small">(가상 MAC)</span>' : ""}`)}
    ${row("제조사", esc(vendorText(n)) || "-")}
    ${row("모델", editable("model", n, n.model_label, n.model || "알 수 없음"))}
    ${wps.device_name || wps.manufacturer ? row("WPS 장치", esc([wps.device_name, wps.manufacturer].filter(Boolean).join(" / "))) : ""}

    <h4>상태</h4>
    ${row("신호", `<b style="color:${sigColor(n.rssi)}">${n.rssi} dBm</b> <span class="muted">(품질 ${n.quality}%)</span>`)}
    ${row("채널 사용률", util != null ? `${util}% <span class="ubar"><i style="width:${util}%"></i></span> <span class="muted small">AP 보고값</span>` : '<span class="muted">방송되지 않음</span>')}
    ${row("단말 수", n.stations ?? '<span class="muted">방송되지 않음</span>')}
    ${row("연결 상태", n.connected ? '<b style="color:var(--good)">현재 연결됨 ★</b>' : "-")}
    ${row("처음 / 마지막 확인", `${new Date(n.first_seen * 1000).toLocaleTimeString("ko-KR")} / ${ago(n.age)}`)}

    <h4>구성</h4>
    ${row("채널", `<b>${n.channel}</b> · ${n.width_label} MHz${n.width > 20 ? ` <span class="muted">(중심 ${n.center_channel})</span>` : ""}`)}
    ${row("대역 / 주파수", `${n.band} GHz / ${n.freq} MHz`)}
    ${row("보안", `<b>${esc(n.security)}</b>${n.akm && n.akm.length ? ` <span class="muted">${esc(n.akm.join(", "))}</span>` : ""}`)}
    ${row("암호화", esc((n.ciphers || []).join(", ")) || "-")}
    ${row("PMF (802.11w)", n.pmf || "-")}
    ${row("기본 속도", `${rateList(n.basic_rates)} Mbps`)}
    ${row("지원 속도", `${rateList(n.rates)} Mbps`)}
    ${row("국가", n.country || "-")}
    ${row("비콘 주기", `${n.beacon} TU${n.dtim ? ` · DTIM ${n.dtim}` : ""}`)}

    <h4>기능</h4>
    ${row("Wi-Fi 모드", `<b>${esc(n.modes || n.phy)}</b> <span class="muted">${n.generation || ""}</span>`)}
    ${row("최대 데이터 속도", n.max_rate != null ? `<b>${n.max_rate} Mbps</b>` : "-")}
    ${row("공간 스트림", n.nss ?? "-")}
    ${row("최대 MCS", n.max_mcs ?? "-")}
    ${row("추가 기능", feats)}

    ${siblings.length ? `<h4>같은 장비의 다른 무선</h4>${siblings.map((s) =>
      `<a class="sib" data-open="${s.bssid}"><span class="sw" style="background:${colorFor(s.bssid)}"></span>${esc(s.ssid || "(숨김)")} <span class="muted mono">${s.bssid}</span> <span class="muted">${s.band} GHz ch${s.channel}</span></a>`).join("")}` : ""}
  `;
}

// ---------------------------------------------------------------- 사용자 지정 이름/모델 저장
function saveAlias(bssid, field, value) {
  const a = Object.assign({}, state.aliases[bssid] || {});
  value = value.trim();
  if (value) a[field] = value; else delete a[field];
  if (Object.keys(a).length) state.aliases[bssid] = a; else delete state.aliases[bssid];
  fetch("/api/settings", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ aliases: state.aliases }),
  }).catch(() => toast("설정 저장에 실패했습니다."));
  decorate(state.data.networks);
  toast(value ? `${field === "name" ? "AP 이름" : "모델"}을(를) "${value}"(으)로 저장했습니다.` : "직접 지정한 값을 지웠습니다. (자동 감지 값 사용)");
}

function commitEdit(save) {
  const inp = $("#editInput");
  const field = editing.field;
  editing.field = null;
  if (save && inp && state.detail) saveAlias(state.detail.bssid, field, inp.value);
  render();
}

// ---------------------------------------------------------------- 이벤트
$("#apInfo").addEventListener("click", (e) => {
  const ed = e.target.closest("[data-edit]");
  if (ed) {
    editing.field = ed.dataset.edit;
    renderAP(true);                      // 편집칸을 포함해 최신 값으로 다시 그림
    const inp = $("#editInput");
    if (inp) { inp.focus(); inp.select(); }
    return;
  }
  const act = e.target.closest("[data-act]");
  if (act) return commitEdit(act.dataset.act === "save");
  const sib = e.target.closest("[data-open]");
  if (sib) openAP(sib.dataset.open);
});
$("#apInfo").addEventListener("keydown", (e) => {
  if (e.target.id !== "editInput") return;
  if (e.key === "Enter") commitEdit(true);
  else if (e.key === "Escape") { e.stopPropagation(); commitEdit(false); }
});

document.querySelectorAll(".crumbs [data-nav]").forEach((el) => el.addEventListener("click", () => navTo(el.dataset.nav)));
document.querySelectorAll(".timeSpan").forEach((g) => g.addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  state.detailSpan = +b.dataset.sec;
  document.querySelectorAll(".timeSpan button").forEach((x) => x.classList.toggle("on", x.dataset.sec === b.dataset.sec));
  render();
}));
$("#gTable tbody").addEventListener("click", (e) => {
  const tr = e.target.closest("tr[data-b]");
  if (tr) openAP(tr.dataset.b);
});

// 메인 표: 🔭 클릭 → SSID 그룹, 행 더블클릭 → AP 상세
$("#nets").addEventListener("click", (e) => {
  const sc = e.target.closest(".scope");
  if (!sc) return;
  e.stopPropagation();
  openGroup(sc.dataset.group);
}, true);
$("#nets").addEventListener("dblclick", (e) => {
  const tr = e.target.closest("tbody tr[data-b]");
  if (tr) openAP(tr.dataset.b);
});

// Esc: 한 단계 위로
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || !state.detail || e.target.tagName === "INPUT") return;
  navTo(state.detail.type === "ap" ? "group" : "list");
});

// render() 확장: 상세 화면이 열려 있으면 그 화면을 갱신
const _renderBeforeDetail = render;
render = function () {
  _renderBeforeDetail();
  if (!state.data || !state.detail) return;
  if (state.detail.type === "group") renderGroup();
  else renderAP();
};

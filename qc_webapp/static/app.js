"use strict";

const $ = (id) => document.getElementById(id);
let VARS = [];          // 변수 수집현황
let curVar = null;      // 현재 선택 변수 key
let curUnit = "";       // 현재 변수 단위
let lastAnalysis = "";  // 직전 분석 텍스트

function params() {
  return {
    range_min: $("range_min").value,
    range_max: $("range_max").value,
    window: $("window").value,
    mad_k: $("mad_k").value,
  };
}
function qs(extra) {
  return new URLSearchParams({ var: curVar, ...params(), ...(extra || {}) }).toString();
}
function esc(s) {
  return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

// ── 변수 수집현황 ─────────────────────────────────────────────
async function loadVariables() {
  VARS = await (await fetch("/api/variables")).json();
  // 카드
  $("var-cards").innerHTML = VARS.map((v) => {
    const on = v.collected;
    const period = on && v.start ? `${v.start} ~ ${v.end}` : "—";
    return `<div class="var-card ${on ? "" : "empty"} ${v.key === curVar ? "active" : ""}" data-var="${v.key}" data-on="${on}">
      <span class="vc-badge ${on ? "on" : "off"}">${on ? "수집됨" : "미수집"}</span>
      <div class="vc-name">${esc(v.name)} <span class="vc-unit">(${esc(v.unit)})</span></div>
      <div class="vc-meta">
        <div>관측소 <b>${v.n_stations}</b>개소</div>
        <div>총 관측점 <b>${v.total_points.toLocaleString()}</b></div>
        <div>기간 <b style="font-weight:600">${period}</b></div>
      </div>
    </div>`;
  }).join("");
  $("var-cards").querySelectorAll(".var-card").forEach((el) => {
    el.addEventListener("click", () => {
      if (el.dataset.on !== "true") return;
      selectVar(el.dataset.var);
    });
  });
  // 드롭다운(수집된 변수만)
  const sel = $("variable");
  sel.innerHTML = VARS.map((v) =>
    `<option value="${v.key}" ${v.collected ? "" : "disabled"}>${esc(v.name)} (${esc(v.unit)})${v.collected ? "" : " · 미수집"}</option>`
  ).join("");
  // 최초 선택: 수집된 첫 변수
  const first = VARS.find((v) => v.collected);
  if (first) await selectVar(first.key);
}

async function selectVar(key) {
  curVar = key;
  const v = VARS.find((x) => x.key === key);
  curUnit = v ? v.unit : "";
  $("variable").value = key;
  // 변수 기본 QC 파라미터로 입력란 초기화
  if (v && v.qc) {
    $("range_min").value = v.qc.range_min;
    $("range_max").value = v.qc.range_max;
    $("window").value = v.qc.window;
    $("mad_k").value = v.qc.mad_k;
  }
  // 카드 active 갱신
  $("var-cards").querySelectorAll(".var-card").forEach((el) =>
    el.classList.toggle("active", el.dataset.var === key));
  lastAnalysis = ""; $("report").disabled = true;
  await loadStations();
  await applyAll();
}

// ── 관측소 ────────────────────────────────────────────────────
async function loadStations() {
  const list = await (await fetch(`/api/stations?var=${curVar}`)).json();
  const sel = $("station");
  sel.innerHTML = list.map((s) =>
    `<option value="${s.obsCode}">${esc(s.name)} (${s.obsCode})</option>`).join("");
}

// ── QC ────────────────────────────────────────────────────────
async function loadQC() {
  const obs = $("station").value;
  if (!obs || !curVar) return;
  $("status").textContent = "QC 계산 중…";
  const d = await (await fetch(`/api/qc?${qs({ obs })}`)).json();
  if (d.error) { $("status").textContent = d.error; return; }
  curUnit = d.unit || curUnit;
  renderStats(d.qc);
  renderChart(d);
  $("chart-sub").textContent = `· ${d.varName} (${d.unit})`;
  $("status").textContent = `${d.name} · ${d.qc.n}점 중 이상치 ${d.qc.n_flagged}점`;
}

function renderStats(qc) {
  const f = qc.flags || {};
  const cards = [
    ["total", "전체", qc.n],
    ["ok", "정상", f.ok || 0],
    ["spike", "급변", f.spike || 0],
    ["range", "범위초과", f.range || 0],
    ["missing", "결측", f.missing || 0],
  ];
  $("stats").innerHTML = cards.map(([cls, lbl, num]) =>
    `<div class="stat-card ${cls}"><div class="num">${num}</div><div class="lbl">${lbl}</div></div>`).join("");
}

function renderChart(d) {
  const v = d.qc.values, u = d.unit || "";
  const x = v.map((p) => p.date);
  const yAll = v.map((p) => p.value);
  const yOk = v.map((p) => (p.flag === "ok" ? p.value : null));
  const mk = (flag, color, name, sym) => {
    const fv = v.filter((p) => p.flag === flag && p.value != null);
    return {
      x: fv.map((p) => p.date), y: fv.map((p) => p.value),
      mode: "markers", type: "scatter", name,
      marker: { color, size: 10, symbol: sym, line: { width: 1.5, color } },
      hovertemplate: `%{x}<br>%{y:.2f}${u}<br>${name}<extra></extra>`,
    };
  };
  const traces = [
    { x, y: yAll, mode: "lines", type: "scatter", name: "원본",
      line: { color: "#c3ccd6", width: 1 }, hoverinfo: "skip" },
    { x, y: yOk, mode: "lines+markers", type: "scatter", name: "QC 통과",
      line: { color: "#1e88e5", width: 2 }, marker: { size: 4, color: "#1e88e5" },
      hovertemplate: `%{x}<br>%{y:.2f}${u}<extra></extra>` },
    mk("spike", "#e0403f", "급변(이상치)", "x"),
    mk("range", "#e09020", "범위초과", "diamond"),
  ];
  const layout = {
    paper_bgcolor: "#fff", plot_bgcolor: "#fff",
    font: { color: "#1c2530", size: 12, family: "Pretendard, sans-serif" },
    margin: { l: 52, r: 16, t: 10, b: 40 },
    xaxis: { gridcolor: "#eef1f5" },
    yaxis: { title: `${d.varName} (${u})`, gridcolor: "#eef1f5" },
    legend: { orientation: "h", y: 1.1 },
    hovermode: "closest",
  };
  Plotly.react("chart", traces, layout, { responsive: true, displaylogo: false });
}

async function loadSummary() {
  const d = await (await fetch(`/api/qc/summary?${qs()}`)).json();
  const rows = d.stations.map((s) => {
    const cls = s.n_flagged === 0 ? "zero" : s.n_flagged <= 2 ? "some" : "many";
    const sp = s.flags.spike || 0, rg = s.flags.range || 0, ms = s.flags.missing || 0;
    return `<tr data-obs="${s.obsCode}">
      <td>${esc(s.name)}</td><td>${s.obsCode}</td>
      <td class="num">${s.n}</td>
      <td class="num"><span class="badge ${cls}">${s.n_flagged}</span></td>
      <td class="num">${sp}</td><td class="num">${rg}</td><td class="num">${ms}</td></tr>`;
  }).join("");
  $("summary").innerHTML = `<table>
    <thead><tr><th>관측소</th><th>코드</th><th class="num">전체</th>
      <th class="num">이상치</th><th class="num">급변</th><th class="num">범위</th><th class="num">결측</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
  $("summary").querySelectorAll("tr[data-obs]").forEach((tr) => {
    tr.addEventListener("click", () => {
      $("station").value = tr.dataset.obs;
      loadQC();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
}

async function applyAll() { await loadQC(); await loadSummary(); updateChatTarget(); }

// ── 우측 AI 채팅 패널 ────────────────────────────────────────
let lastQuestion = "";   // 마지막 질문(보고서 입력용)

function currentScope() { return $("scope_all").checked ? "__ALL__" : $("station").value; }

function updateChatTarget() {
  const v = VARS.find((x) => x.key === curVar);
  const vn = v ? v.name : "";
  const stSel = $("station");
  const stName = stSel.options[stSel.selectedIndex] ? stSel.options[stSel.selectedIndex].text : "";
  $("chat-target").textContent = $("scope_all").checked ? `전국 ${vn} 통합` : `${stName} · ${vn}`;
}

function showEmptyState() {
  $("messages").innerHTML = `<div class="empty-state">
    <div class="es-ic">💬</div>
    <div class="es-title">데이터 기반 AI 분석</div>
    <div class="es-desc">선택한 자료의 QC 결과를 근거로 답합니다.<br>질문을 비우고 전송하면 전반적 품질 진단을 수행합니다.</div>
  </div>`;
}

function renderMarkdown(text) {
  const lines = text.split("\n");
  let html = "", inList = false;
  const close = () => { if (inList) { html += "</ul>"; inList = false; } };
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith("#")) { close(); html += `<h3>${esc(line.replace(/^#+\s*/, ""))}</h3>`; }
    else if (/^[-•·*]\s/.test(line)) {
      if (!inList) { html += "<ul>"; inList = true; }
      const sub = /^\s{2,}/.test(raw);
      html += `<li class="${sub ? "sub" : ""}">${esc(line.replace(/^[-•·*]\s*/, ""))}</li>`;
    } else { close(); html += `<p>${esc(line)}</p>`; }
  }
  close();
  return html;
}

function addMsg(role, text) {
  const div = document.createElement("div");
  div.className = "msg " + role;
  div.textContent = text;
  $("messages").appendChild(div);
  $("messages").scrollTop = $("messages").scrollHeight;
  return div;
}

async function askAI() {
  const obs = currentScope();
  if (!obs || !curVar) return;
  const q = $("question").value.trim();
  lastQuestion = q;
  const m = $("messages");
  if (m.querySelector(".empty-state")) m.innerHTML = "";
  addMsg("user", q || "(전반적 QC 품질 진단)");
  $("question").value = "";
  $("ask").disabled = true; $("report").disabled = true; $("report-status").textContent = "";

  const typing = document.createElement("div");
  typing.className = "typing";
  typing.innerHTML = "AI가 분석 중<span>.</span><span>.</span><span>.</span>";
  m.appendChild(typing); m.scrollTop = m.scrollHeight;

  try {
    const d = await (await fetch("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ var: curVar, obs, message: q, params: params() }),
    })).json();
    typing.remove();
    if (!d.ok) { addMsg("bot", d.error || "분석 실패"); return; }
    lastAnalysis = d.analysis;
    const bot = document.createElement("div");
    bot.className = "msg bot";
    bot.innerHTML = renderMarkdown(d.analysis) +
      (d.fallback ? `<p class="warn">⚠ LLM 응답 실패로 통계 기반 임시 요약입니다.</p>` : "");
    m.appendChild(bot); m.scrollTop = m.scrollHeight;
    $("report").disabled = false;
  } catch (e) {
    typing.remove(); addMsg("bot", "오류: " + e);
  } finally { $("ask").disabled = false; }
}

async function makeReport() {
  const obs = currentScope();
  if (!obs || !curVar) return;
  $("report").disabled = true;
  $("report-status").innerHTML = "보고서 생성 중…";
  try {
    const d = await (await fetch("/api/report", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ var: curVar, obs, message: lastQuestion, analysis: lastAnalysis, params: params() }),
    })).json();
    if (!d.ok) { $("report-status").textContent = d.error || "보고서 생성 실패"; }
    else { $("report-status").innerHTML = `✅ <a href="${d.url}" download>${d.filename} 내려받기</a>`; }
  } catch (e) { $("report-status").textContent = "오류: " + e; }
  finally { $("report").disabled = false; }
}

$("apply").addEventListener("click", applyAll);
$("variable").addEventListener("change", (e) => selectVar(e.target.value));
$("station").addEventListener("change", () => {
  loadQC(); lastAnalysis = ""; $("report").disabled = true; updateChatTarget();
});
$("scope_all").addEventListener("change", () => { lastAnalysis = ""; $("report").disabled = true; updateChatTarget(); });
$("ask").addEventListener("click", askAI);
$("report").addEventListener("click", makeReport);
$("question").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); askAI(); }
});

(async function init() { showEmptyState(); await loadVariables(); })();

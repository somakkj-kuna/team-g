"use strict";

const $ = (id) => document.getElementById(id);
let SRC = null;                 // /api/sources
let curView = "main";           // main | vars | series
let curAgency = null, curAgencyName = "";
let curStation = null, curStationName = "";
let curVar = null, curUnit = "", curVarName = "";
let VARSTATUS = null;           // {agency, agencyName, station, name, variables:[...]}
let curStations = [];           // [{station_id, name, lat, lon}]
let curPeriod = "all";
let lastAnalysis = "", lastQuestion = "";
let lastAnalysisKey = "";        // lastAnalysis가 속한 기관|관측소|변수|기간 (선택 일치 시 보고서 재사용)
let lastAnalysisQuestion = "";   // lastAnalysis를 만든 질문(재사용 시 보고서 '분석 요청' 라벨 일치용)
let SEARCH_INDEX = [];           // 전역 검색 인덱스 [{kind, agency, agencyName, station, stationName, var?, varName?, unit?}]
let GS_HITS = [];                // 현재 표시중 검색 결과
let gsActive = -1;               // 키보드 하이라이트 인덱스
let indexReady = false;          // 검색 인덱스 빌드 완료 여부
let drawSeq = 0;                 // 시계열 fetch 경쟁 방지 토큰
let reportBusy = false;          // 보고서 생성 중 재진입·중복요청 방지
let CATALOG = null;              // /api/catalog (다운로드 범위·기관)
let dlAgency = "all";            // 다운로드 모달 기관 필터(all/기관코드)

const enc = encodeURIComponent;

const PERIOD_LABEL = { "1m": "최근 1개월", "1y": "최근 1년", "all": "전체 기간" };
const CHART_RE = /시계열|그래프|차트|추이|그려|plot|그림/i;
const ANALYSIS_RE = /분석|판단|평가|진단|이상치|품질|설명|알려|왜|어때|요약|보고/i;
const CAT_TAG = { Numerical: "NUMS", Observation: "OBS", Satellite: "SATE" };

const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function getJSON(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.json()).error || ""; } catch (e) { /* ignore */ }
    throw new Error("HTTP " + res.status + (detail ? " · " + detail : ""));
  }
  const ct = res.headers.get("content-type") || "";
  if (!ct.includes("json")) throw new Error("JSON 아님 (" + ct + ")");
  return res.json();
}

// ── 수집 현황 로드 ───────────────────────────────────────────
async function loadSources() {
  try {
    SRC = await getJSON("/api/sources");
  } catch (e) {
    renderLoadError(e);
    return;
  }
  renderSummary(SRC.summary);
  if (curView === "main") renderMatrix();
  await setupChat();
}

function renderLoadError(e) {
  const msg = esc(String((e && e.message) || e));
  $("summary-cards").innerHTML = "";
  $("matrix").innerHTML = `<div class="ingest-card" style="text-align:center; padding:42px 24px">
    <div style="font-size:39px">⚠️</div>
    <h2 class="ih-title" style="margin:12px 0 8px">수집 현황을 불러오지 못했습니다</h2>
    <p class="muted" style="margin:0 0 6px"><code>/api/sources</code> 응답 오류: ${msg}</p>
    <p class="muted" style="margin:0">서버가 최신 코드로 재시작됐는지 확인하고, 강력 새로고침(Ctrl+Shift+R)을 해 주세요.</p>
  </div>`;
}

function renderSummary(s) {
  $("summary-cards").innerHTML = `
    <div class="sum-card tracked"><div class="sc-lbl">SOURCES TRACKED</div><div class="sc-num">${s.tracked}<span class="sc-unit">ENTITIES</span></div></div>
    <div class="sum-card healthy"><div class="sc-lbl">HEALTHY</div><div class="sc-num">${String(s.healthy).padStart(2, "0")}</div></div>
    <div class="sum-card pending"><div class="sc-lbl">ERRORS</div><div class="sc-num">${String(s.errors).padStart(2, "0")}</div></div>`;
}

// ── 메인: 수집 현황 매트릭스(§01 INGEST MATRIX) ──────────────
function renderMatrix() {
  purgeSeriesChart();
  curView = "main";
  const s = SRC.summary;
  const sections = SRC.categories.map(catSection).join("");
  $("matrix").innerHTML = `<div class="ingest-card">
    <div class="ingest-head">
      <div class="ih-left">
        <div class="ih-kicker"><span class="ih-sec">§ 01</span><span class="ih-tag">INGEST MATRIX</span></div>
        <h2 class="ih-title">기관별 수집·품질관리 <span class="muted">현황 요약</span></h2>
      </div>
      <div class="ih-right">
        <div class="ih-window">통합 모니터링</div>
        <div class="ih-stat"><b class="ok">${s.healthy}</b> healthy · <b class="err">${s.errors}</b> errors · <b>0</b> idle</div>
      </div>
    </div>
    ${sections}
  </div>`;
  bindMatrixClicks();
}

function catSection(c) {
  const tag = CAT_TAG[c.key] || c.key.toUpperCase();
  const cls = c.key.toLowerCase();
  let cards;
  if (c.pending) {
    cards = `<div class="cat-pending">
      <span class="cp-ic">⏳</span>
      <div><b>데이터 준비중</b><div class="cp-desc">${esc(c.desc)}</div></div>
    </div>`;
  } else {
    cards = c.sources.map(srcCard).join("")
      || `<div class="cat-pending"><span class="cp-ic">○</span><div><b>표시할 소스가 없습니다</b></div></div>`;
  }
  const stat = c.pending
    ? `<div><span class="muted">데이터 준비중</span></div>`
    : `<div><span class="ok">${String(c.on_time).padStart(2, "0")} on time</span> · <span class="err">${c.critical} critical</span></div>`;
  return `<section class="cat-row${c.pending ? " pending" : ""}">
    <div class="cat-label">
      <span class="cl-tag ${cls}">${tag}</span>
      <div class="cl-name">${esc(c.en || c.label)}</div>
      <div class="cl-desc">${esc(c.en_desc || c.desc)}</div>
      <div class="cl-stat">
        <div><b>${String(c.n).padStart(2, "0")}</b> sources</div>
        ${stat}
      </div>
    </div>
    <div class="cat-cards">${cards}</div>
  </section>`;
}

// 메인 소스 카드 = 기관(KHOA/KMA/NIFS)
function srcCard(it) {
  const err = !it.healthy;
  const n = it.bar.length;
  const bar = it.bar.map((st, i) => `<i class="${st === "none" ? "" : st}${i === n - 1 ? " cur" : ""}"></i>`).join("");
  return `<div class="src-card real" data-agency="${esc(it.agency)}">
    <span class="sc-dot ${err ? "err" : ""}"></span>
    <div class="sc-src">${esc(it.source)}</div>
    <div class="sc-ds">${esc(it.dataset)}</div>
    <div class="sc-row"><span class="sc-ratio ${err ? "err" : "ok"}">${esc(it.ratio)}</span><span class="sc-elapsed">${esc(it.elapsed || "—")}</span></div>
    <div class="sc-bar">${bar}</div>
    <div class="sc-real">변수 ${it.n_vars}종 · ${Number(it.total_points || 0).toLocaleString()}점</div>
    <div class="sc-hint">→ 변수별 현황 · 시계열</div>
  </div>`;
}

function bindMatrixClicks() {
  $("matrix").querySelectorAll(".src-card.real").forEach((el) =>
    el.addEventListener("click", () => openVars(el.dataset.agency)));
}

// ── 드릴다운 1: 기관 → 변수 박스 ─────────────────────────────
async function openVars(agency) {
  curView = "vars";
  try {
    await loadAgencyContext(agency);
  } catch (e) {
    $("matrix").innerHTML = `<div class="ingest-card"><p class="muted">변수 현황을 불러오지 못했습니다: ${esc(e.message || e)}</p></div>`;
    return;
  }
  renderVarsView();
}

function varBar(v) {
  const N = 20;
  if (!v.n) return Array(N).fill("<i></i>").join("");
  const nok = Math.max(0, Math.min(N, Math.round(N * v.retained / v.n)));
  let s = "";
  for (let i = 0; i < N; i++) s += `<i class="${i < nok ? "ok" : "warn"}"></i>`;
  return s;
}

function varCard(v) {
  if (!v.collected) {
    return `<div class="src-card"><span class="warn-badge pending">○ 미수집</span>
      <div class="sc-src">${esc(v.name)}</div><div class="sc-ds">${esc(v.unit)}</div>
      <div class="sc-real" style="color:var(--muted)">데이터 없음</div></div>`;
  }
  const warn = v.flag_rate_pct >= 20 ? "outlier" : null;
  const corner = warn ? `<span class="warn-badge outlier">⚠ 제거 과다</span>` : `<span class="sc-dot"></span>`;
  return `<div class="src-card real ${warn ? "warn-" + warn : ""}" data-var="${esc(v.key)}">
    ${corner}
    <div class="sc-src">${esc(v.name)}</div>
    <div class="sc-ds">${esc(v.unit)}</div>
    <div class="sc-row"><span class="sc-ratio ok">${v.retained.toLocaleString()}<small> 보존</small></span><span class="sc-elapsed">${v.n.toLocaleString()}점</span></div>
    <div class="sc-bar">${varBar(v)}</div>
    <div class="sc-real">제거 ${v.flagged.toLocaleString()}점 · ${v.flag_rate_pct}% <span class="muted">(불량 ${v.bad}·결측 ${v.missing})</span></div>
    <div class="sc-hint">→ 시계열 보기</div>
  </div>`;
}

function renderVarsView() {
  purgeSeriesChart();
  const vars = (VARSTATUS.variables || []);
  const nCol = vars.filter((v) => v.collected).length;
  $("matrix").innerHTML = `
    <div class="drill-head">
      <button id="back-main" class="btn-ghost">← 수집 현황</button>
      <div>
        <div class="kicker khoa">${esc(curAgencyName)} · ${esc(VARSTATUS.name)} (${esc(VARSTATUS.station)})</div>
        <h2 class="drill-title">변수별 QC 현황 <span class="muted" style="font-size:15px">${nCol}개 변수 · 변수를 누르면 시계열을 봅니다</span></h2>
      </div>
    </div>
    <section class="cat-section"><div class="src-grid">${vars.map(varCard).join("")}</div></section>`;
  $("back-main").addEventListener("click", () => { curView = "main"; renderMatrix(); });
  $("matrix").querySelectorAll(".src-card.real").forEach((el) =>
    el.addEventListener("click", () => openSeries(el.dataset.var)));
}

// ── 드릴다운 2: 변수 → QC 시계열 ─────────────────────────────
async function openSeries(varKey) {
  curView = "series"; curVar = varKey;
  const vm = (VARSTATUS.variables || []).find((v) => v.key === varKey);
  curUnit = vm ? vm.unit : ""; curVarName = vm ? vm.name : varKey;
  syncChatSelectors();
  renderSeriesView();
}

function renderSeriesView() {
  purgeSeriesChart();
  const cols = (VARSTATUS.variables || []).filter((v) => v.collected);
  const vtabs = cols.map((v) =>
    `<button class="var-tab ${v.key === curVar ? "active" : ""}" data-var="${esc(v.key)}"><span class="vt-dot"></span>${esc(v.name)}<span class="vt-unit">${esc(v.unit)}</span></button>`).join("");
  const stabs = curStations.map((s) =>
    `<button class="station-tab ${s.station_id === curStation ? "active" : ""}" data-station="${esc(s.station_id)}">${esc(s.name)}</button>`).join("");
  $("matrix").innerHTML = `
    <div class="drill-head">
      <button id="back-vars" class="btn-ghost">← 변수별 현황</button>
      <div>
        <div class="kicker khoa">${esc(curAgencyName)} · ${esc(curVarName)} 시계열</div>
        <h2 class="drill-title">QC 시계열 <span class="muted" style="font-size:15px">보존된 데이터와 QC 제거 자료를 함께 표시</span></h2>
      </div>
    </div>
    <div class="var-tabs">${vtabs}</div>
    <div class="sec-title">관측소 선택 <span class="muted">(${curStations.length}개소)</span></div>
    <div class="station-tabs">${stabs || '<span class="muted">관측소 자료 없음</span>'}</div>
    <div id="series-stats" class="stats"></div>
    <div class="series-chart-card">
      <div class="chart-toolbar">
        <span class="ct-title">QC 시계열 차트</span>
        <div class="ct-zoom">
          <button class="ct-btn" id="zoom-in" type="button" title="확대 (마우스 휠로도 가능)">＋ 확대</button>
          <button class="ct-btn" id="zoom-out" type="button" title="축소 (마우스 휠로도 가능)">－ 축소</button>
          <button class="ct-btn" id="zoom-reset" type="button" title="전체 기간·범위로 되돌리기">⤢ 전체</button>
          <span class="ct-tip">🖱 휠 확대·축소 · 드래그로 이동</span>
        </div>
      </div>
      <div id="series-chart"></div>
    </div>
    <div id="series-legend" class="qc-legend"></div>
    <div id="series-collect" class="collect-note"></div>`;
  $("back-vars").addEventListener("click", () => { curView = "vars"; renderVarsView(); });
  $("matrix").querySelectorAll(".var-tab").forEach((b) =>
    b.addEventListener("click", () => openSeries(b.dataset.var)));
  $("matrix").querySelectorAll(".station-tab").forEach((b) =>
    b.addEventListener("click", async () => {
      curStation = b.dataset.station;
      const sm = curStations.find((s) => s.station_id === curStation);
      curStationName = sm ? sm.name : "";
      lastAnalysis = "";
      syncChatSelectors();
      $("matrix").querySelectorAll(".station-tab").forEach((x) => x.classList.toggle("active", x === b));
      b.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
      drawDetailChart();
      // 보고서 탭 변수 목록도 새 관측소 기준으로 동기화(VARSTATUS 갱신)
      try {
        VARSTATUS = await getJSON(`/api/variables?agency=${enc(curAgency)}&station=${enc(curStation)}`);
        fillChatSelectors();
      } catch (e) { /* 갱신 실패 시 기존 목록 유지 */ }
    }));
  if ($("zoom-in")) $("zoom-in").addEventListener("click", () => zoomChart(0.6));
  if ($("zoom-out")) $("zoom-out").addEventListener("click", () => zoomChart(1 / 0.6));
  if ($("zoom-reset")) $("zoom-reset").addEventListener("click", resetChart);
  drawDetailChart();
}

async function drawDetailChart() {
  purgeSeriesChart();
  const clearCollect = () => { if ($("series-collect")) $("series-collect").innerHTML = ""; };
  if (!curStation) { $("series-chart").innerHTML = '<div class="chart-empty">관측소를 선택하세요.</div>'; clearCollect(); return; }
  const reqId = ++drawSeq;   // 이 요청의 토큰. 더 최신 요청이 시작되면 응답을 폐기한다.
  $("series-chart").innerHTML = '<div class="chart-empty">불러오는 중…</div>';
  let d;
  try {
    d = await getJSON(`/api/qc?agency=${encodeURIComponent(curAgency)}&station=${encodeURIComponent(curStation)}&var=${encodeURIComponent(curVar)}&period=${curPeriod}`);
  } catch (e) {
    if (reqId !== drawSeq) return;   // 경쟁 응답(구버전) — 무시
    $("series-chart").innerHTML = `<div class="chart-empty">자료를 불러오지 못했습니다 (${esc(e.message || e)})</div>`;
    $("series-stats").innerHTML = ""; $("series-legend").innerHTML = ""; clearCollect();
    return;
  }
  if (reqId !== drawSeq) return;     // 경쟁 응답(구버전) — 무시
  const u = d.unit || "";
  const s = d.series;
  $("series-stats").innerHTML = `
    <div class="stat-card"><div class="num">${d.n.toLocaleString()}</div><div class="lbl">전체 관측</div></div>
    <div class="stat-card ok"><div class="num">${d.retained.toLocaleString()}</div><div class="lbl">보존 (good+suspect)</div></div>
    <div class="stat-card spike"><div class="num">${d.flagged.toLocaleString()}</div><div class="lbl">제거 (불량+결측)</div></div>
    <div class="stat-card range"><div class="num">${d.flag_rate_pct}%</div><div class="lbl">제거 비율</div></div>`;

  const x = s.map((p) => p.time);
  const retained = s.map((p) => ((p.flag === 1 || p.flag === 2 || p.flag === 4) ? p.value : null));
  const mk = (pred, color, name, sym) => {
    const fv = s.filter((p) => pred(p.flag) && p.value != null);
    return {
      x: fv.map((p) => p.time), y: fv.map((p) => p.value), mode: "markers", type: "scatter", name,
      marker: { color, size: 8, symbol: sym, line: { width: 1, color: "#fff" } },
      hovertemplate: `%{x}<br>%{y:.2f}${esc(u)}<br>${name}<extra></extra>`,
    };
  };
  const traces = [
    { x, y: s.map((p) => p.value), mode: "lines", name: "원본 신호", line: { color: "#d3dae2", width: 1 }, hoverinfo: "skip" },
    {
      x, y: retained, mode: "lines", name: "보존 (QC 통과)", line: { color: "#1f9d55", width: 1.6 },
      connectgaps: false, hovertemplate: `%{x}<br>%{y:.2f}${esc(u)}<br>보존<extra></extra>`,
    },
    mk((f) => f === 2, "#e09020", "주의 (suspect)", "diamond"),
    mk((f) => f === 3, "#e0403f", "불량 (bad)", "x"),
    mk((f) => f === 4, "#1e88e5", "보간 (interpolated)", "circle"),
  ];
  Plotly.newPlot("series-chart", traces, {
    paper_bgcolor: "#fff", plot_bgcolor: "#fff", font: { size: 12, family: "Pretendard, sans-serif" },
    margin: { l: 56, r: 16, t: 10, b: 40 },
    xaxis: { gridcolor: "#eef1f5", type: "date" },
    yaxis: { title: `${esc(d.varName)} (${esc(u)})`, gridcolor: "#eef1f5" },
    showlegend: true, legend: { orientation: "h", y: -0.16, x: 0, font: { size: 12 } }, hovermode: "closest",
    dragmode: "pan",   // 좌클릭 드래그 = 이동(pan), 휠 = 확대/축소(scrollZoom)
  }, {
    responsive: true, displaylogo: false, scrollZoom: true, displayModeBar: true,
    modeBarButtonsToRemove: ["lasso2d", "select2d", "toImage", "sendDataToCloud"],
  });

  $("series-legend").innerHTML = `
    <span class="lg-item"><i class="lg-line ok"></i> <b>보존</b> — QC 통과(good·suspect·보간)로 분석에 사용</span>
    <span class="lg-item"><i class="lg-mk range"></i> <b>주의(suspect)</b> — 의심값(보존하되 표시)</span>
    <span class="lg-item"><i class="lg-mk spike"></i> <b>불량(bad)</b> — QC 제거</span>
    <span class="lg-item"><i class="lg-mk interp"></i> <b>보간(interpolated)</b> — 결측 보간값</span>
    <span class="lg-item"><i class="lg-mk miss"></i> <b>결측(missing)</b> — 값 없음(미표시)</span>`;

  renderCollectNote(s);
}

// 결측 자료 재수집 상태 표시: 최근 1주 이내 결측=수집 진행중, 1주 경과=수집 안 함(미수집 확정).
// 기준 '현재'는 표시 시계열의 최신 시점(데이터가 2025 고정이므로 실시간 today가 아님).
function renderCollectNote(series) {
  const el = $("series-collect");
  if (!el) return;
  const WEEK_MS = 7 * 24 * 3600 * 1000;
  const missing = series.filter((p) => p.flag === 9 && p.time);
  if (!missing.length) {
    el.classList.remove("has-missing");
    el.innerHTML = `<div class="cn-head"><span class="cn-ic ok">✓</span>결측 자료 없음 — 표시 기간 내 모든 시점이 수집되었습니다.</div>`;
    return;
  }
  let latest = 0;
  for (const p of series) {
    if (p.time) { const t = new Date(p.time).getTime(); if (t > latest) latest = t; }
  }
  const cutoff = latest - WEEK_MS;
  let prog = 0, done = 0;
  for (const p of missing) {
    if (new Date(p.time).getTime() >= cutoff) prog++; else done++;
  }
  el.classList.add("has-missing");
  el.innerHTML = `
    <div class="cn-head"><span class="cn-ic">ℹ️</span><b>결측 자료 수집 상태</b>
      <span class="cn-sub">결측 발생 후 약 1주간 재수집을 진행하고, 1주가 지나면 재수집하지 않습니다.</span></div>
    <div class="cn-rows">
      <div class="cn-row prog"><span class="cn-dot"></span><b>자료 수집 진행중</b><span class="cn-desc">최근 1주 이내 결측 · 재수집 진행</span><span class="cn-n">${prog.toLocaleString()}점</span></div>
      <div class="cn-row done"><span class="cn-dot"></span><b>자료 수집 안 함</b><span class="cn-desc">1주 경과 결측 · 미수집 확정</span><span class="cn-n">${done.toLocaleString()}점</span></div>
    </div>`;
}

// ── 시계열 줌(확대/축소/전체) ───────────────────────────────
// 축 range를 중심 기준으로 factor 배 스케일. date/숫자축 모두 대응(Plotly r2l/l2r 우선).
function axZoom(ax, factor) {
  if (!ax || !ax.range) return null;
  let toL, fromL;
  if (typeof ax.r2l === "function" && typeof ax.l2r === "function") {
    toL = (v) => ax.r2l(v); fromL = (v) => ax.l2r(v);
  } else if (ax.type === "date") {
    toL = (v) => new Date(v).getTime(); fromL = (v) => new Date(v).toISOString();
  } else {
    toL = (v) => Number(v); fromL = (v) => v;
  }
  const l0 = toL(ax.range[0]), l1 = toL(ax.range[1]);
  if (!isFinite(l0) || !isFinite(l1) || l0 === l1) return null;
  const c = (l0 + l1) / 2, half = Math.abs(l1 - l0) / 2 * factor;
  const lo = c - half, hi = c + half;
  return [fromL(Math.min(lo, hi)), fromL(Math.max(lo, hi))];
}

function zoomChart(factor) {
  const gd = $("series-chart");
  if (!gd || !gd._fullLayout || !gd.data || !gd.data.length) return;
  const upd = {};
  const xr = axZoom(gd._fullLayout.xaxis, factor);
  const yr = axZoom(gd._fullLayout.yaxis, factor);
  if (xr) { upd["xaxis.range"] = xr; upd["xaxis.autorange"] = false; }
  if (yr) { upd["yaxis.range"] = yr; upd["yaxis.autorange"] = false; }
  if (Object.keys(upd).length) Plotly.relayout(gd, upd);
}

function resetChart() {
  const gd = $("series-chart");
  if (!gd || !gd._fullLayout || !gd.data) return;
  Plotly.relayout(gd, { "xaxis.autorange": true, "yaxis.autorange": true });
}

// 차트 노드를 placeholder/뷰 전환으로 버리기 전에 호출 — Plotly 내부상태(_fullLayout 등)와
// responsive resize 리스너를 정리해, ①줌 버튼이 stale 노드에 동작 ②resize 리스너 누수를 방지.
function purgeSeriesChart() {
  const gd = $("series-chart");
  if (gd && gd._fullLayout && window.Plotly) {
    try { Plotly.purge(gd); } catch (e) { /* ignore */ }
  }
}

// ── 우측 AI 컨텍스트 ─────────────────────────────────────────
async function setupChat() {
  const obs = (SRC.categories.find((c) => c.key === "Observation") || {}).sources || [];
  $("chat-agency").innerHTML = obs.map((a) =>
    `<option value="${esc(a.agency)}">${esc(a.source)} · ${esc(a.dataset)}</option>`).join("")
    || `<option value="">기관 없음</option>`;
  if (obs.length && !curAgency) {
    await loadAgencyContext(obs[0].agency);
  } else {
    syncChatSelectors();
  }
}

async function loadAgencyContext(agency) {
  curAgency = agency;
  curStations = await getJSON(`/api/stations?agency=${encodeURIComponent(agency)}`);
  curStation = curStations.length ? curStations[0].station_id : null;
  curStationName = curStations.length ? curStations[0].name : "";
  VARSTATUS = await getJSON(`/api/variables?agency=${encodeURIComponent(agency)}&station=${encodeURIComponent(curStation || "")}`);
  curAgencyName = VARSTATUS.agencyName || agency.toUpperCase();
  const cols = (VARSTATUS.variables || []).filter((v) => v.collected);
  if (cols.length && (!curVar || !cols.find((v) => v.key === curVar))) {
    curVar = cols[0].key; curUnit = cols[0].unit; curVarName = cols[0].name;
  }
  fillChatSelectors();
}

// 특정 기관·관측소·변수로 분석 컨텍스트 고정(품질평가 설정 카드 → askAI 전 호출)
async function setContextTo(agency, station, varKey) {
  curAgency = agency;
  curStations = await getJSON(`/api/stations?agency=${enc(agency)}`);
  const sm = curStations.find((s) => s.station_id === station) || curStations[0] || null;
  curStation = sm ? sm.station_id : station;
  curStationName = sm ? sm.name : station;
  VARSTATUS = await getJSON(`/api/variables?agency=${enc(agency)}&station=${enc(curStation || "")}`);
  curAgencyName = VARSTATUS.agencyName || agency.toUpperCase();
  const cols = (VARSTATUS.variables || []).filter((v) => v.collected);
  const vm = cols.find((v) => v.key === varKey) || cols[0] || null;
  if (vm) { curVar = vm.key; curUnit = vm.unit; curVarName = vm.name; }
  fillChatSelectors();
}

// "자료 품질 평가" 예시 → 즉시 분석 대신 분석할 관측소·변수를 먼저 선택받는 카드
async function startQualityEval() {
  if ($("messages").querySelector(".empty-state")) $("messages").innerHTML = "";
  const wrap = document.createElement("div");
  wrap.className = "msg bot qe-setup";
  wrap.innerHTML =
    `<div class="qe-q">어떤 관측소와 변수를 분석할까요?</div>`
    + `<div class="qe-row"><span class="qe-lab">기관</span><select class="qe-agency"></select></div>`
    + `<div class="qe-row"><span class="qe-lab">관측소</span><select class="qe-station"></select></div>`
    + `<div class="qe-row"><span class="qe-lab">변수</span><select class="qe-var"></select></div>`
    + `<button class="btn qe-go" type="button" disabled>이 선택으로 품질 평가</button>`;
  $("messages").appendChild(wrap);
  $("messages").scrollTop = $("messages").scrollHeight;
  const aSel = wrap.querySelector(".qe-agency");
  const sSel = wrap.querySelector(".qe-station");
  const vSel = wrap.querySelector(".qe-var");
  const goBtn = wrap.querySelector(".qe-go");
  const obs = (SRC && SRC.categories
    ? (SRC.categories.find((c) => c.key === "Observation") || {}).sources : null) || [];
  aSel.innerHTML = obs.map((a) => `<option value="${esc(a.agency)}">${esc(a.source || a.agency)}</option>`).join("")
    || `<option value="">기관 없음</option>`;
  async function loadVars() {
    vSel.innerHTML = `<option>불러오는 중…</option>`; goBtn.disabled = true;
    let vs = [];
    try {
      const vd = await getJSON(`/api/variables?agency=${enc(aSel.value)}&station=${enc(sSel.value)}`);
      vs = (vd.variables || []).filter((v) => v.collected);
    } catch (e) { vs = []; }
    vSel.innerHTML = vs.map((v) => `<option value="${esc(v.key)}">${esc(v.name)}</option>`).join("")
      || `<option value="">변수 없음</option>`;
    goBtn.disabled = !(sSel.value && vs.length);
  }
  async function loadStations() {
    sSel.innerHTML = `<option>불러오는 중…</option>`; vSel.innerHTML = `<option>—</option>`; goBtn.disabled = true;
    let sts = [];
    try { sts = await getJSON(`/api/stations?agency=${enc(aSel.value)}`); } catch (e) { sts = []; }
    sSel.innerHTML = sts.map((s) =>
      `<option value="${esc(s.station_id)}">${esc(s.name)} (${esc(s.station_id)})</option>`).join("")
      || `<option value="">관측소 없음</option>`;
    await loadVars();
  }
  aSel.addEventListener("change", loadStations);
  sSel.addEventListener("change", loadVars);
  goBtn.addEventListener("click", async () => {
    if (!sSel.value || !vSel.value) return;
    goBtn.disabled = true;
    [aSel, sSel, vSel].forEach((el) => { el.disabled = true; });
    wrap.classList.add("done");
    await setContextTo(aSel.value, sSel.value, vSel.value);
    $("question").value = "이 관측소 자료의 QC 품질을 평가해줘";
    askAI();
  });
  // 현재 컨텍스트로 프리필
  if (curAgency) aSel.value = curAgency;
  await loadStations();
  if (curStation && Array.from(sSel.options).some((o) => o.value === curStation)) {
    sSel.value = curStation; await loadVars();
  }
  if (curVar && Array.from(vSel.options).some((o) => o.value === curVar)) vSel.value = curVar;
}

function fillChatSelectors() {
  const cols = ((VARSTATUS && VARSTATUS.variables) || []).filter((v) => v.collected);
  // 보고서 탭 변수: 체크박스 드롭다운(다중선택)
  renderCkPanel($("report-vars"), cols.map((v) => ({ key: v.key, name: v.name, unit: v.unit })),
    () => { updateCkTrigger("report-var-dd", "report-vars"); updateReportEnabled(); });
  if ($("report-station")) {
    $("report-station").innerHTML = curStations.map((s) =>
      `<option value="${esc(s.station_id)}">${esc(s.name)} (${esc(s.station_id)})</option>`).join("")
      || `<option value="">관측소 없음</option>`;
  }
  syncChatSelectors();
  updateReportEnabled();
}

function updateReportEnabled() {
  const n = ckCheckedKeys("report-vars").length;
  if ($("report")) $("report").disabled = reportBusy || !(curStation && n);
}

// 보고서 대상으로 체크된 변수 [{key,name}]
function reportCheckedVars() {
  const meta = {};
  ((VARSTATUS && VARSTATUS.variables) || []).forEach((v) => { meta[v.key] = v; });
  return ckCheckedKeys("report-vars").map((k) => ({ key: k, name: (meta[k] || {}).name || k }));
}

function syncChatSelectors() {
  if ($("chat-agency") && curAgency) $("chat-agency").value = curAgency;
  if ($("report-station") && curStation) $("report-station").value = curStation;
}

// 보고서 설정에서 관측소 변경 → 해당 관측소 변수 재로딩(선택에 따라 분석 대상 전환)
async function selectReportStation(stationId) {
  curStation = stationId;
  const sm = curStations.find((s) => s.station_id === stationId);
  curStationName = sm ? sm.name : stationId;
  try {
    VARSTATUS = await getJSON(`/api/variables?agency=${enc(curAgency)}&station=${enc(stationId)}`);
  } catch (e) { /* 기존 VARSTATUS 유지 */ }
  const cols = ((VARSTATUS && VARSTATUS.variables) || []).filter((v) => v.collected);
  if (cols.length && (!curVar || !cols.find((v) => v.key === curVar))) {
    curVar = cols[0].key; curUnit = cols[0].unit; curVarName = cols[0].name;
  }
  lastAnalysis = "";
  fillChatSelectors();
  if (curView === "series") openSeries(curVar);
}

// ── 전역 타이핑 검색 ─────────────────────────────────────────
// 3기관의 관측소 + 변수(수집된 것)를 인덱싱해 입력 즉시 필터·점프.
async function buildSearchIndex() {
  // 카탈로그 1회 호출로 인덱싱(대규모 관측소에서도 빠름). vars는 카탈로그가 이미 포함.
  let cat = [];
  try { cat = await getJSON("/api/catalog"); } catch (e) { cat = []; }
  const idx = [];
  for (const s of cat) {
    const base = {
      agency: s.agency,
      agencyName: s.agencyName || s.agency,
      agencyCode: (s.agency || "").toUpperCase(),
      station: s.station, stationName: s.name,
    };
    idx.push({ ...base, kind: "station" });
    for (const v of (s.vars || [])) {
      idx.push({ ...base, kind: "var", var: v.key, varName: v.name, unit: v.unit });
    }
  }
  SEARCH_INDEX = idx;
  indexReady = true;
  // 빌드 중 이미 입력해둔 질의가 있으면 즉시 재검색
  if ($("global-q") && $("global-q").value.trim()) runSearch($("global-q").value);
}

function gsRow(e, i) {
  if (e.kind === "var") {
    return `<div class="gs-item" data-i="${i}">
      <span class="gs-tag var">변수</span>
      <span class="gs-main">${esc(e.varName)}${e.unit ? ` <small>${esc(e.unit)}</small>` : ""}</span>
      <span class="gs-sub">${esc(e.stationName)} · ${esc(e.agencyName)}</span></div>`;
  }
  return `<div class="gs-item" data-i="${i}">
    <span class="gs-tag st">관측소</span>
    <span class="gs-main">${esc(e.stationName)} <small>${esc(e.station)}</small></span>
    <span class="gs-sub">${esc(e.agencyName)}</span></div>`;
}

function runSearch(raw) {
  const q = (raw || "").trim().toLowerCase();
  const box = $("global-results");
  if (!box) return;
  gsActive = -1;
  if (!q) { box.hidden = true; box.innerHTML = ""; GS_HITS = []; return; }
  if (!indexReady) {
    box.innerHTML = `<div class="gs-empty">🔄 검색 인덱스를 준비 중입니다…</div>`;
    box.hidden = false; GS_HITS = []; return;
  }
  const hits = SEARCH_INDEX.filter((e) => {
    const hay = [e.stationName, e.station, e.agencyName, e.agency, e.agencyCode, e.varName, e.var]
      .filter(Boolean).join(" ").toLowerCase();
    return hay.includes(q);
  }).slice(0, 12);
  GS_HITS = hits;
  if (!hits.length) {
    box.innerHTML = `<div class="gs-empty">‘${esc(raw.trim())}’ 검색 결과가 없습니다</div>`;
    box.hidden = false; return;
  }
  box.innerHTML = hits.map(gsRow).join("");
  box.hidden = false;
  box.querySelectorAll(".gs-item").forEach((el) => {
    const i = Number(el.dataset.i);
    el.addEventListener("mousedown", (ev) => { ev.preventDefault(); selectSearchHit(i); });
    el.addEventListener("mousemove", () => setGsActive(i));
  });
}

function setGsActive(i) {
  gsActive = i;
  const box = $("global-results");
  if (!box) return;
  const items = box.querySelectorAll(".gs-item");
  items.forEach((el, j) => el.classList.toggle("active", j === i));
  if (items[i]) items[i].scrollIntoView({ block: "nearest" });
}

async function selectSearchHit(i) {
  const e = GS_HITS[i];
  if (!e) return;
  const box = $("global-results");
  if ($("global-q")) $("global-q").value = "";
  if (box) { box.hidden = true; box.innerHTML = ""; }
  GS_HITS = []; gsActive = -1;
  await gotoStation(e.agency, e.station, e.kind === "var" ? e.var : null);
}

// 검색 결과 → 해당 기관/관측소(/변수) 시계열로 점프
async function gotoStation(agency, station, varKey) {
  try {
    if (agency !== curAgency || !curStations.length) {
      curAgency = agency;
      curStations = await getJSON(`/api/stations?agency=${enc(agency)}`);
    }
    curStation = station;
    const sm = curStations.find((s) => s.station_id === station);
    curStationName = sm ? sm.name : station;
    VARSTATUS = await getJSON(`/api/variables?agency=${enc(agency)}&station=${enc(station)}`);
    curAgencyName = VARSTATUS.agencyName || agency.toUpperCase();
    const cols = (VARSTATUS.variables || []).filter((v) => v.collected);
    const pick = varKey && cols.find((v) => v.key === varKey);
    if (pick) { curVar = pick.key; curUnit = pick.unit; curVarName = pick.name; }
    else if (cols.length && (!curVar || !cols.find((v) => v.key === curVar))) {
      curVar = cols[0].key; curUnit = cols[0].unit; curVarName = cols[0].name;
    }
    lastAnalysis = "";
    fillChatSelectors();
    openSeries(curVar);
    const sc = document.querySelector(".content");
    if (sc) sc.scrollTo({ top: 0, behavior: "smooth" });
  } catch (err) {
    $("matrix").innerHTML =
      `<div class="ingest-card"><p class="muted">관측소로 이동하지 못했습니다: ${esc(err.message || err)}</p></div>`;
  }
}

// ── 데이터 다운로드 모달 ─────────────────────────────────────
async function loadCatalog() {
  if (!CATALOG) CATALOG = await getJSON("/api/catalog");
  return CATALOG;
}

function dlScopeStations() {
  const all = CATALOG || [];
  return dlAgency === "all" ? all.slice() : all.filter((s) => s.agency === dlAgency);
}

// 기관 탭(전체 + 카탈로그의 각 기관) 렌더
function renderDlAgencies() {
  const box = $("dl-agencies");
  if (!box) return;
  const seen = new Set(), agencies = [];
  (CATALOG || []).forEach((s) => {
    if (!seen.has(s.agency)) { seen.add(s.agency); agencies.push({ agency: s.agency, name: s.agencyName || s.agency }); }
  });
  if (dlAgency !== "all" && !seen.has(dlAgency)) dlAgency = "all";
  box.innerHTML = `<button type="button" class="dl-region ${dlAgency === "all" ? "active" : ""}" data-agency="all">전체</button>`
    + agencies.map((a) => `<button type="button" class="dl-region ${dlAgency === a.agency ? "active" : ""}" data-agency="${esc(a.agency)}">${esc(a.name)}</button>`).join("");
  box.querySelectorAll(".dl-region").forEach((b) =>
    b.addEventListener("click", () => {
      dlAgency = b.dataset.agency;
      box.querySelectorAll(".dl-region").forEach((x) => x.classList.toggle("active", x === b));
      renderDlStations();
      fillDlVars();
    }));
}

function openDownloadModal() {
  const m = $("dl-modal");
  if (!m) return;
  m.hidden = false;
  // 변수 드롭다운·날짜 선택기는 항상 접힌 상태로 시작(이전 Esc 종료 시 펼침 잔존 방지)
  m.querySelectorAll(".ck-dd.open, .wdate.open").forEach((o) => {
    o.classList.remove("open");
    const p = o.querySelector(".ck-panel, .wdate-panel");
    if (p) p.hidden = true;
  });
  $("dl-stations").innerHTML = `<div class="dl-empty">불러오는 중…</div>`;
  if ($("dl-go")) $("dl-go").disabled = true;
  if ($("dl-summary")) $("dl-summary").textContent = "관측소 목록 불러오는 중…";
  loadCatalog()
    .then(() => { renderDlAgencies(); renderDlStations(); fillDlVars(); })
    .catch((e) => {
      $("dl-stations").innerHTML = `<div class="dl-empty">목록을 불러오지 못했습니다: ${esc(e.message || e)}</div>`;
      updateDlSummary();
    });
}

function closeDownloadModal() { const m = $("dl-modal"); if (m) m.hidden = true; }

function renderDlStations() {
  const box = $("dl-stations");
  if (!box) return;
  const sts = dlScopeStations();
  if (!sts.length) {
    box.innerHTML = `<div class="dl-empty">표시할 관측소가 없습니다.</div>`;
    updateDlSummary(); return;
  }
  box.innerHTML = sts.map((s) => `
    <label class="dl-st-row">
      <input type="checkbox" class="dl-st-ck" value="${esc(s.agency)}:${esc(s.station)}" checked>
      <span class="dl-st-name">${esc(s.name)}<span class="dl-st-region">${esc(s.region)}</span></span>
      <span class="dl-st-meta">${esc(s.agencyName)} · ${esc(s.station)} · 변수 ${(s.vars || []).length}종</span>
    </label>`).join("");
  box.querySelectorAll(".dl-st-ck").forEach((ck) => ck.addEventListener("change", updateDlSummary));
  updateDlSummary();
}

// 변수: 선택 범위(기관)의 변수 합집합을 체크박스로. 이전 체크상태 보존, 신규는 기본 체크.
// ── 변수 다중선택 드롭다운(공용) ────────────────────────────
// items=[{key,name,unit}]. 이전 체크상태 보존(신규는 기본 체크). onChange는 변경 시마다 호출.
function renderCkPanel(panel, items, onChange) {
  if (!panel) return;
  const prev = {}; let hadPrev = false;
  panel.querySelectorAll(".ck-item").forEach((c) => { prev[c.value] = c.checked; hadPrev = true; });
  if (!items.length) { panel.innerHTML = `<div class="ck-empty">표시할 변수가 없습니다.</div>`; if (onChange) onChange(); return; }
  panel.innerHTML =
    `<label class="ck-row ck-allrow"><input type="checkbox" class="ck-all" checked><span class="ck-name">전체 변수</span><span class="ck-meta">${items.length}종</span></label>`
    + items.map((v) => {
        const on = hadPrev ? (prev[v.key] !== false) : true;
        return `<label class="ck-row"><input type="checkbox" class="ck-item" value="${esc(v.key)}"${on ? " checked" : ""}>`
          + `<span class="ck-name">${esc(v.name)}<span class="ck-key">${esc(v.key)}</span></span>`
          + `<span class="ck-meta">${esc(v.unit || "")}</span></label>`;
      }).join("");
  const all = panel.querySelector(".ck-all");
  const cks = Array.from(panel.querySelectorAll(".ck-item"));
  const syncAll = () => { if (all) all.checked = cks.length > 0 && cks.every((c) => c.checked); };
  if (all) all.addEventListener("change", () => { cks.forEach((c) => { c.checked = all.checked; }); if (onChange) onChange(); });
  cks.forEach((c) => c.addEventListener("change", () => { syncAll(); if (onChange) onChange(); }));
  syncAll();
  if (onChange) onChange();
}

function ckCheckedKeys(panelId) {
  const p = $(panelId);
  return p ? Array.from(p.querySelectorAll(".ck-item:checked")).map((c) => c.value) : [];
}
function ckTotal(panelId) {
  const p = $(panelId);
  return p ? p.querySelectorAll(".ck-item").length : 0;
}
function updateCkTrigger(ddId, panelId) {
  const dd = $(ddId);
  if (!dd) return;
  const tx = dd.querySelector(".ck-tx");
  if (!tx) return;
  const total = ckTotal(panelId), checked = ckCheckedKeys(panelId).length;
  tx.textContent = !total ? "변수 없음"
    : checked === total ? `전체 변수 (${total}종)`
    : checked === 0 ? "변수 선택 안 함"
    : `변수 ${checked}종 선택`;
}
function bindCkDropdown(ddId) {
  const dd = $(ddId);
  if (!dd) return;
  const trigger = dd.querySelector(".ck-trigger"), panel = dd.querySelector(".ck-panel");
  if (!trigger || !panel) return;
  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    const willOpen = panel.hidden;
    document.querySelectorAll(".ck-dd.open").forEach((o) => {
      if (o !== dd) { o.classList.remove("open"); const p = o.querySelector(".ck-panel"); if (p) p.hidden = true; }
    });
    panel.hidden = !willOpen;
    dd.classList.toggle("open", willOpen);
  });
}

function fillDlVars() {
  const map = new Map();
  dlScopeStations().forEach((s) => (s.vars || []).forEach((v) => { if (!map.has(v.key)) map.set(v.key, v); }));
  renderCkPanel($("dl-vars"), Array.from(map.values()),
    () => { updateCkTrigger("dl-var-dd", "dl-vars"); updateDlSummary(); });
}

function updateDlSummary() {
  const sbox = $("dl-stations");
  const ns = sbox ? sbox.querySelectorAll(".dl-st-ck:checked").length : 0;
  const nv = ckCheckedKeys("dl-vars").length;
  const sum = $("dl-summary");
  if (sum) {
    if (!ns) sum.innerHTML = "관측소를 1개 이상 선택하세요";
    else if (!nv) sum.innerHTML = "변수를 1개 이상 선택하세요";
    else sum.innerHTML = `관측소 <b>${ns}</b>개소 · 변수 <b>${nv}</b>종`;
  }
  const go = $("dl-go");
  if (go) go.disabled = (ns === 0 || nv === 0);
}

function doDownload() {
  const sbox = $("dl-stations");
  if (!sbox) return;
  const targets = Array.from(sbox.querySelectorAll(".dl-st-ck:checked")).map((c) => c.value);
  const checkedVk = ckCheckedKeys("dl-vars");
  if (!targets.length || !checkedVk.length) return;
  // 전부 체크면 'all'(서버가 전체 변수로 처리), 일부면 체크한 키만
  const vars = (checkedVk.length === ckTotal("dl-vars")) ? "all" : checkedVk.join(",");
  const qs = new URLSearchParams({
    targets: targets.join(","),
    vars,
    maxflag: $("dl-maxflag").value || "9",
  });
  const start = $("dl-start").value, end = $("dl-end").value;
  if (start) qs.set("start", start);
  if (end) qs.set("end", end);
  const a = document.createElement("a");
  a.href = "/api/download?" + qs.toString();
  a.download = "";
  document.body.appendChild(a); a.click(); a.remove();
}

// 휠 스크롤 연·월·일 날짜 선택기. 값은 hidden input(YYYY-MM-DD)에 기록(doDownload가 읽음).
function setupWheelDate(boxId, hiddenId, label) {
  const box = $(boxId), hidden = $(hiddenId);
  if (!box || !hidden) return;
  const Y0 = 2015, Y1 = 2027;
  const years = []; for (let y = Y0; y <= Y1; y++) years.push(y);
  const months = []; for (let m = 1; m <= 12; m++) months.push(m);
  const daysIn = (y, m) => new Date(y, m, 0).getDate();   // m=1..12 → 해당 월 마지막 일
  const st = { y: null, m: null, d: null };
  const init = (hidden.value || "").split("-");
  if (init.length === 3) { st.y = +init[0] || null; st.m = +init[1] || null; st.d = +init[2] || null; }

  box.innerHTML =
    `<button type="button" class="wdate-trigger"><span class="wdate-tx"></span><span class="ck-caret">▾</span></button>`
    + `<div class="wdate-panel" hidden>`
    +   `<div class="wdate-cols">`
    +     `<div class="wd-col"><div class="wd-title">연</div><div class="wd-list" data-k="y"></div></div>`
    +     `<div class="wd-col"><div class="wd-title">월</div><div class="wd-list" data-k="m"></div></div>`
    +     `<div class="wd-col"><div class="wd-title">일</div><div class="wd-list" data-k="d"></div></div>`
    +   `</div>`
    +   `<div class="wdate-foot"><button type="button" class="wdate-clear">지우기</button>`
    +     `<button type="button" class="wdate-done">적용</button></div>`
    + `</div>`;
  const trigger = box.querySelector(".wdate-trigger");
  const txEl = box.querySelector(".wdate-tx");
  const panel = box.querySelector(".wdate-panel");
  const lists = { y: box.querySelector('[data-k="y"]'), m: box.querySelector('[data-k="m"]'), d: box.querySelector('[data-k="d"]') };

  const fmt = () => (st.y && st.m && st.d)
    ? `${st.y}-${String(st.m).padStart(2, "0")}-${String(st.d).padStart(2, "0")}` : "";
  const syncTrigger = () => { txEl.textContent = hidden.value || label; };  // 트리거는 '적용된' 값(hidden) 표시
  const commit = () => { hidden.value = fmt(); syncTrigger(); };

  function fillList(key) {
    let vals;
    if (key === "y") vals = years;
    else if (key === "m") vals = months;
    else { const n = daysIn(st.y || 2025, st.m || 1); vals = []; for (let d = 1; d <= n; d++) vals.push(d); }
    lists[key].innerHTML = vals.map((v) =>
      `<div class="wd-item${v === st[key] ? " sel" : ""}" data-v="${v}">${v}</div>`).join("");
  }
  function center(key) {
    const sel = lists[key].querySelector(".wd-item.sel");
    if (sel) lists[key].scrollTop = sel.offsetTop - (lists[key].clientHeight - sel.clientHeight) / 2;
  }
  function setVal(key, v) {
    st[key] = v;
    if (key === "y" || key === "m") {       // 월/연 변경 시 일수 보정·재구성
      const dn = daysIn(st.y || 2025, st.m || 1);
      if (st.d && st.d > dn) st.d = dn;
      fillList("d"); center("d");
    }
    fillList(key); center(key);
    commit();
  }
  function step(key, dir) {
    const vals = Array.from(lists[key].querySelectorAll(".wd-item")).map((it) => +it.dataset.v);
    if (!vals.length) return;
    let i = vals.indexOf(st[key]); if (i < 0) i = 0;
    setVal(key, vals[Math.min(vals.length - 1, Math.max(0, i + dir))]);
  }
  function openPanel() {
    if (st.y == null) { st.y = 2025; st.m = st.m || 1; st.d = st.d || 1; }   // 기본 시작값
    ["y", "m", "d"].forEach(fillList);
    // 다른 드롭다운/선택기 닫기
    document.querySelectorAll(".ck-dd.open").forEach((o) => { o.classList.remove("open"); const p = o.querySelector(".ck-panel"); if (p) p.hidden = true; });
    document.querySelectorAll(".wdate.open").forEach((o) => { if (o !== box) { o.classList.remove("open"); const p = o.querySelector(".wdate-panel"); if (p) p.hidden = true; } });
    panel.hidden = false; box.classList.add("open");
    ["y", "m", "d"].forEach(center);
    syncTrigger();        // 열기만으로는 미적용(스크롤·클릭·적용 시 commit)
  }
  function closePanel() { panel.hidden = true; box.classList.remove("open"); }

  trigger.addEventListener("click", (e) => { e.stopPropagation(); if (panel.hidden) openPanel(); else closePanel(); });
  ["y", "m", "d"].forEach((key) => {
    lists[key].addEventListener("wheel", (e) => { e.preventDefault(); step(key, e.deltaY > 0 ? 1 : -1); }, { passive: false });
    lists[key].addEventListener("click", (e) => { const it = e.target.closest(".wd-item"); if (it) setVal(key, +it.dataset.v); });
  });
  box.querySelector(".wdate-clear").addEventListener("click", (e) => {
    e.stopPropagation(); st.y = st.m = st.d = null; ["y", "m", "d"].forEach(fillList); commit(); closePanel();
  });
  box.querySelector(".wdate-done").addEventListener("click", (e) => { e.stopPropagation(); commit(); closePanel(); });
  syncTrigger();
}

// ── 채팅 ─────────────────────────────────────────────────────
function showEmptyState() {
  $("messages").innerHTML = `<div class="empty-state">
    <div class="es-ic">💬</div>
    <div class="es-title">관측자료 QC 분석</div>
    <div class="es-desc">상단 검색으로 관측소를 찾거나 좌측에서 기관→변수→관측소를 고른 뒤 질문하세요.<br>분석 결과는 한글(HWPX) 보고서로 저장할 수 있습니다.</div>
    <div class="es-examples"><div class="es-label">대표 질문</div>
      <button class="es-chip" data-q="수온 시계열을 보여줘"><span class="es-chip-ic">📈</span><span class="es-chip-tx">수온 시계열 보기</span><span class="es-chip-go">→</span></button>
      <button class="es-chip" data-setup="quality"><span class="es-chip-ic">📊</span><span class="es-chip-tx">자료 품질 평가</span><span class="es-chip-go">→</span></button>
      <button class="es-chip" data-q="QC에서 제거된 자료가 계측 오류인지 실제 현상인지 분석해줘"><span class="es-chip-ic">🔍</span><span class="es-chip-tx">제거 자료 원인 분석</span><span class="es-chip-go">→</span></button>
    </div></div>`;
  $("messages").querySelectorAll(".es-chip").forEach((b) =>
    b.addEventListener("click", () => {
      if (b.dataset.setup === "quality") { startQualityEval(); return; }
      $("question").value = b.dataset.q; askAI();
    }));
}

function addMsg(role, text) {
  const d = document.createElement("div"); d.className = "msg " + role; d.textContent = text;
  $("messages").appendChild(d); $("messages").scrollTop = $("messages").scrollHeight; return d;
}
function addBot(html) {
  const d = document.createElement("div"); d.className = "msg bot"; d.innerHTML = html;
  $("messages").appendChild(d); $("messages").scrollTop = $("messages").scrollHeight; return d;
}

// AI 사고중 표시 — 회전 스피너 + "결과를 분석 중…"
function showThinking() {
  const d = document.createElement("div");
  d.className = "thinking";
  d.innerHTML = `<span class="ai-spinner" aria-hidden="true"></span>`
    + `<span class="thinking-tx">결과를 분석 중<span class="dots"><i>.</i><i>.</i><i>.</i></span></span>`;
  $("messages").appendChild(d); $("messages").scrollTop = $("messages").scrollHeight;
  return d;
}

function renderMarkdown(text) {
  const lines = text.split("\n"); let html = "", inList = false;
  const close = () => { if (inList) { html += "</ul>"; inList = false; } };
  for (const raw of lines) {
    const line = raw.trim(); if (!line) continue;
    if (line.startsWith("#")) { close(); html += `<h3>${esc(line.replace(/^#+\s*/, ""))}</h3>`; }
    else if (/^[-•·*]\s/.test(line)) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li class="${/^\s{2,}/.test(raw) ? "sub" : ""}">${esc(line.replace(/^[-•·*]\s*/, ""))}</li>`;
    } else { close(); html += `<p>${esc(line)}</p>`; }
  }
  close(); return html;
}

// 완료된 분석 결과 아래에 "한글(HWPX) 저장" 버튼을 붙인다(해당 분석·컨텍스트를 클로저로 고정).
function addAnalysisActions(analysisText, question, ctx) {
  const wrap = document.createElement("div");
  wrap.className = "analysis-actions";
  wrap.innerHTML = `<button class="btn-save-hwpx" type="button">📄 이 분석을 한글(HWPX)로 저장</button>`
    + `<span class="aa-status"></span>`;
  $("messages").appendChild(wrap);
  $("messages").scrollTop = $("messages").scrollHeight;
  const btn = wrap.querySelector(".btn-save-hwpx");
  const status = wrap.querySelector(".aa-status");
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    status.innerHTML = `<span class="ai-spinner" aria-hidden="true"></span> 한글 보고서 생성 중… (수십 초)`;
    try {
      const r = await (await fetch("/api/report", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agency: ctx.agency, station: ctx.station, var: ctx.var,
          period: ctx.period, message: question, analysis: analysisText }),
      })).json();
      if (!r.ok) { status.textContent = r.error || "생성 실패"; btn.disabled = false; }
      else {
        btn.remove();
        status.innerHTML = `✅ <a href="${esc(r.url)}" download>${esc(r.filename)} 내려받기</a>`;
      }
    } catch (e) { status.textContent = "오류: " + esc(String(e)); btn.disabled = false; }
  });
}

async function askAI() {
  if (!curVar) { addBot("먼저 좌측에서 변수를 선택하세요."); return; }
  const q = $("question").value.trim();
  lastQuestion = q;
  if ($("messages").querySelector(".empty-state")) $("messages").innerHTML = "";
  addMsg("user", q || "(전반적 QC 품질 진단)");
  $("question").value = "";
  const wantChart = CHART_RE.test(q);
  const wantAnalysis = !wantChart || ANALYSIS_RE.test(q);

  $("ask").disabled = true;
  try {
    if (wantChart) {
      await openSeries(curVar);
      addBot(`좌측에 <b>${esc(curVarName)}</b> 시계열을 표시했습니다. (보존 데이터 / QC 제거 자료 구분)`);
    }
    if (wantAnalysis) {
      const think = showThinking();
      let d;
      try {
        d = await (await fetch("/api/chat", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ agency: curAgency, station: curStation, var: curVar, message: q, period: curPeriod }),
        })).json();
      } finally { think.remove(); }
      if (!d.ok) { addBot(esc(d.error || "분석 실패")); }
      else {
        lastAnalysis = d.analysis;
        lastAnalysisKey = `${curAgency}|${curStation}|${curVar}|${curPeriod}`;
        lastAnalysisQuestion = q;
        addBot(renderMarkdown(d.analysis) + (d.fallback ? `<p class="warn">⚠ LLM 응답 실패로 통계 기반 임시 요약입니다.</p>` : ""));
        addAnalysisActions(d.analysis, q, { agency: curAgency, station: curStation, var: curVar, period: curPeriod });
      }
    }
    updateReportEnabled();
  } catch (e) { addBot("오류: " + esc(e)); }
  finally { $("ask").disabled = false; }
}

// 체크된 변수들을 하나의 통합 한글(HWPX) 보고서로 생성(선택 일치 분석은 재사용).
async function makeReport() {
  if (reportBusy) return;                       // 생성 중 중복요청 차단
  const vars = reportCheckedVars();
  if (!curStation || !vars.length) return;
  // 생성 시작 시점의 컨텍스트를 고정(생성 중 기관/관측소/기간이 바뀌어도 영향 없음)
  const ag = curAgency, sta = curStation, per = curPeriod, staName = curStationName;
  reportBusy = true;
  const rbtn = $("report");
  const rbtnLabel = rbtn ? rbtn.textContent : "";
  if (rbtn) { rbtn.disabled = true; rbtn.classList.add("is-busy"); rbtn.textContent = "보고서 생성 중…"; }
  const st = $("report-status");
  // 현재 선택과 일치하는 변수만 기존 분석을 재사용(나머지는 서버가 새로 분석)
  const analyses = {};
  vars.forEach((v) => {
    if (lastAnalysis && lastAnalysisKey === `${ag}|${sta}|${v.key}|${per}`) {
      analyses[v.key] = lastAnalysis;
    }
  });
  const vnames = vars.map((v) => v.name).join(", ");
  if (st) {
    st.innerHTML = `<span class="ai-spinner" aria-hidden="true"></span> `
      + `<b>${esc(staName)}</b> · ${PERIOD_LABEL[per]} · ${esc(vnames)} (${vars.length}종) `
      + `분석·통합 보고서 생성 중… <span class="rs-dim">변수 수에 따라 수십 초~수 분 소요</span>`;
  }
  try {
    const d = await (await fetch("/api/report", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        agency: ag, station: sta,
        vars: vars.map((v) => v.key), analyses,
        period: per, message: "",
      }),
    })).json();
    if (!d.ok) { if (st) st.textContent = d.error || "보고서 생성 실패"; }
    else if (st) {
      const note = (d.n_vars > 1) ? ` <span class="rs-dim">(${d.n_vars}개 변수 통합 보고서)</span>` : "";
      st.innerHTML = `✅ <a href="${esc(d.url)}" download>${esc(d.filename)} 내려받기</a>${note}`;
    }
  } catch (e) { if (st) st.textContent = "오류: " + esc(String(e)); }
  finally {
    reportBusy = false;
    if (rbtn) { rbtn.classList.remove("is-busy"); rbtn.textContent = rbtnLabel; }
    updateReportEnabled();
  }
}

// 우측 패널 탭 전환(LLM 분석 / 품질 결과 보고서)
function switchPanelTab(tab) {
  document.querySelectorAll(".panel-tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  if ($("pane-llm")) $("pane-llm").hidden = tab !== "llm";
  if ($("pane-report")) $("pane-report").hidden = tab !== "report";
}

// ── 이벤트 ───────────────────────────────────────────────────
$("refresh").addEventListener("click", loadSources);
$("chat-agency").addEventListener("change", async (e) => {
  await loadAgencyContext(e.target.value);
  if (curView === "series") openSeries(curVar);
  else if (curView === "vars") renderVarsView();
});
if ($("report-station")) $("report-station").addEventListener("change", (e) => selectReportStation(e.target.value));
document.querySelectorAll(".panel-tab").forEach((b) =>
  b.addEventListener("click", () => switchPanelTab(b.dataset.tab)));
// 변수 다중선택 드롭다운(다운로드 모달 + 보고서 탭) 열기/닫기
bindCkDropdown("dl-var-dd");
bindCkDropdown("report-var-dd");
// 휠 연·월·일 날짜 선택기(다운로드 모달)
setupWheelDate("wd-start", "dl-start", "시작일 선택");
setupWheelDate("wd-end", "dl-end", "종료일 선택");
document.addEventListener("click", (e) => {
  if (!e.target.closest(".ck-dd")) {
    document.querySelectorAll(".ck-dd.open").forEach((o) => {
      o.classList.remove("open");
      const p = o.querySelector(".ck-panel");
      if (p) p.hidden = true;
    });
  }
  if (!e.target.closest(".wdate")) {
    document.querySelectorAll(".wdate.open").forEach((o) => {
      o.classList.remove("open");
      const p = o.querySelector(".wdate-panel");
      if (p) p.hidden = true;
    });
  }
});
$("ask").addEventListener("click", askAI);
$("report").addEventListener("click", makeReport);
$("question").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); askAI(); } });
document.querySelectorAll(".period-btn").forEach((b) =>
  b.addEventListener("click", () => {
    curPeriod = b.dataset.p;
    document.querySelectorAll(".period-btn").forEach((x) => x.classList.toggle("active", x === b));
    if (curView === "series") drawDetailChart();
  }));

// 전역 타이핑 검색 이벤트
if ($("global-q")) {
  $("global-q").addEventListener("input", (e) => runSearch(e.target.value));
  $("global-q").addEventListener("focus", (e) => { if (e.target.value.trim()) runSearch(e.target.value); });
  $("global-q").addEventListener("keydown", (e) => {
    const n = GS_HITS.length;
    if (e.key === "ArrowDown") { e.preventDefault(); if (n) setGsActive(gsActive < 0 ? 0 : (gsActive + 1) % n); }
    else if (e.key === "ArrowUp") { e.preventDefault(); if (n) setGsActive(gsActive <= 0 ? n - 1 : gsActive - 1); }
    else if (e.key === "Enter") { e.preventDefault(); if (n) selectSearchHit(gsActive >= 0 ? gsActive : 0); }
    else if (e.key === "Escape") { const box = $("global-results"); if (box) box.hidden = true; gsActive = -1; e.target.blur(); }
  });
}
document.addEventListener("click", (e) => {
  if (!e.target.closest(".global-search")) {
    const box = $("global-results");
    if (box) box.hidden = true;
  }
});

// 다운로드 모달 이벤트
if ($("open-download")) $("open-download").addEventListener("click", openDownloadModal);
if ($("dl-modal")) {
  $("dl-modal").querySelectorAll("[data-close]").forEach((el) =>
    el.addEventListener("click", closeDownloadModal));
}
if ($("dl-go")) $("dl-go").addEventListener("click", doDownload);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && $("dl-modal") && !$("dl-modal").hidden) closeDownloadModal();
});

(async function init() {
  showEmptyState();
  await loadSources();
  await buildSearchIndex();
})();

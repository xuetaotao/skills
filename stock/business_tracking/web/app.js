/* 周期行业观测台 前端逻辑（V1） */
"use strict";

/* ---------- 基础工具 ---------- */
const $ = (sel, el) => (el || document).querySelector(sel);
const $$ = (sel, el) => Array.from((el || document).querySelectorAll(sel));
const api = (p, opt) => fetch(p, opt).then((r) => r.json());
const post = (p) => fetch(p, { method: "POST" }).then((r) => r.json());
const esc = (s) => String(s == null ? "" : s).replace(/</g, "&lt;");

const fmtNum = (v) =>
  v == null ? "—" : Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("en-US") : Math.round(v * 100) / 100;
const fmtPct = (v) =>
  v == null ? "—" : (v > 0 ? "+" : "") + v + "%";
const pctCls = (v) => (v == null ? "" : v > 0 ? "up" : v < 0 ? "down" : "");
const qPct = (q) => (q == null ? "—" : Math.round(q * 100) + "%");

function qTagClass(q) {
  if (q == null) return "";
  if (q < 0.1) return "q-extreme-low";
  if (q < 0.25) return "q-low";
  if (q < 0.5) return "q-mid-low";
  if (q < 0.75) return "q-mid-high";
  if (q < 0.9) return "q-high";
  return "q-extreme-high";
}
function stageClass(stage) {
  if (["高位强势", "高位回落"].includes(stage)) return "stage-high";
  if (stage === "上行中段") return "stage-mid";
  if (["低位回升", "低位寻底"].includes(stage)) return "stage-low";
  return "stage-flat";
}

/* ---------- 术语悬停（铁律3） ---------- */
let GLOSSARY = [];
function rich(text) {
  let html = esc(text);
  for (const g of GLOSSARY) {
    const idx = html.indexOf(g.term);
    if (idx >= 0 && g.term.length > 1) {
      const tip = `<b>${esc(g.term)}（${esc(g.en)}）</b>${esc(g.plain)}`;
      const span = `<span class="term">${g.term}<span class="tip">${tip}</span></span>`;
      html = html.slice(0, idx) + span + html.slice(idx + g.term.length);
    }
  }
  return html;
}

/* ---------- 状态栏 + 主动刷新 ---------- */
let STATUS = null;
async function loadStatus() {
  STATUS = await api("/api/status");
  $("#dataAsOf").textContent = STATUS.data_as_of || "—";
  $("#lastRefresh").textContent = STATUS.last_refresh || "—";
  const busy = STATUS.updating;
  $("#btnRefresh").disabled = busy;
  $("#spinIcon").style.display = busy ? "inline" : "none";
  $("#refreshText").textContent = busy ? "刷新中…" : "刷新数据";
  const errBox = $("#refreshError");
  if (STATUS.last_error && !busy) {
    errBox.style.display = "block";
    errBox.textContent = "部分数据源更新失败：" + STATUS.last_error;
  } else errBox.style.display = "none";
  return STATUS;
}

let pollTimer = null;
async function doRefresh() {
  await post("/api/refresh");
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    const s = await loadStatus();
    if (!s.updating) {
      clearInterval(pollTimer);
      pollTimer = null;
      route(); // 刷新完重载当前页数据
    }
  }, 2500);
}

/* ---------- 图表工具 ---------- */
const charts = {};
function mkChart(id) {
  let el = document.getElementById(id);
  if (!el) return null;
  if (charts[id]) charts[id].dispose();
  const c = echarts.init(el);
  charts[id] = c;
  return c;
}
window.addEventListener("resize", () => Object.values(charts).forEach((c) => c.resize()));

const AXIS_STYLE = {
  axisLabel: { color: "#5b6572", fontSize: 11 },
  splitLine: { lineStyle: { color: "#eef0f3" } },
};
const TOOLTIP = { trigger: "axis", textStyle: { fontSize: 12 } };

/* 价格走势 + 分位通道（铁律2/5） */
function drawPriceChart(id, name, points, channel) {
  const c = mkChart(id);
  if (!c) return;
  const markLines = [];
  if (channel)
    for (const [k, label] of [["p10", "10%分位"], ["p25", "25%"], ["p50", "50%中位"], ["p75", "75%"], ["p90", "90%分位"]])
      if (channel[k] != null) markLines.push({ yAxis: channel[k], name: label });
  c.setOption({
    title: { text: name, left: 10, top: 6, textStyle: { fontSize: 14 } },
    tooltip: TOOLTIP,
    grid: { left: 70, right: 30, top: 40, bottom: 50 },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 20, bottom: 8 }],
    xAxis: { type: "category", data: points.map((p) => p[0]), ...AXIS_STYLE },
    yAxis: { type: "value", scale: true, ...AXIS_STYLE },
    series: [{
      type: "line", name, data: points.map((p) => p[1]),
      showSymbol: false, lineStyle: { width: 1.6, color: "#2563eb" },
      markLine: {
        silent: true, symbol: "none",
        lineStyle: { type: "dashed", color: "#999", width: 1 },
        label: { formatter: "{b}", fontSize: 10, color: "#888" },
        data: markLines,
      },
    }],
  });
}

/* 多线图（库存/对比等，normalized 可选） */
function drawMultiChart(id, name, seriesList, normalized) {
  const c = mkChart(id);
  if (!c) return;
  const legend = seriesList.map((s) => s.name);
  let x = seriesList.length ? seriesList[0].points.map((p) => p[0]) : [];
  const series = seriesList.map((s) => {
    let vals = s.points.map((p) => p[1]);
    if (normalized && s.points.length) {
      const base = s.points[0][1] || 1;
      vals = vals.map((v) => Math.round((v / base) * 1000) / 10);
    }
    return { type: "line", name: s.name, data: vals, showSymbol: false, lineStyle: { width: 1.5 } };
  });
  c.setOption({
    title: { text: name + (normalized ? "（起点=100）" : ""), left: 10, top: 6, textStyle: { fontSize: 14 } },
    tooltip: TOOLTIP,
    legend: { top: 8, right: 10, textStyle: { fontSize: 11 } },
    grid: { left: 60, right: 30, top: 44, bottom: 50 },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 20, bottom: 8 }],
    xAxis: { type: "category", data: x, ...AXIS_STYLE },
    yAxis: { type: "value", scale: true, ...AXIS_STYLE },
    series,
  });
}

/* 动量条形图 */
function drawMomentumChart(id, members) {
  const c = mkChart(id);
  if (!c) return;
  const names = members.map((m) => m.name);
  c.setOption({
    title: { text: "动量对比（区间涨跌幅 %）", left: 10, top: 6, textStyle: { fontSize: 14 } },
    tooltip: TOOLTIP,
    legend: { top: 8, right: 10, textStyle: { fontSize: 11 } },
    grid: { left: 60, right: 30, top: 44, bottom: 50 },
    xAxis: { type: "category", data: names, ...AXIS_STYLE, axisLabel: { rotate: 20, fontSize: 10 } },
    yAxis: { type: "value", ...AXIS_STYLE },
    series: ["1M", "3M", "6M", "1Y"].map((k, i) => ({
      name: k, type: "bar", barGap: 0,
      itemStyle: { color: ["#93b8f5", "#2563eb", "#1e40af", "#0f2a66"][i] },
      data: members.map((m) => (m.momentum ? m.momentum[k] : null)),
    })),
  });
}

/* ---------- 页面：总览（铁律1：结论先行） ---------- */
const SECTORS = { metals: "有色金属", energy: "能源", shipping: "航运" };

function sectorSentence(sec) {
  const cores = sec.members.filter((m) =>
    ["SHFE_CU", "SHFE_AL", "COMEX_HG", "WTI", "BRENT", "INE_SC", "PPI_COAL", "JM", "BDI", "BCI", "BPI"].includes(m.code));
  const parts = cores.slice(0, 3).map((m) => {
    const mom = m.momentum && m.momentum["3M"];
    return `${m.name}处于${m.q_window || "近10年"}第${qPct(m.q10y)}分位（${m.q10y_label}），3个月${mom == null ? "—" : fmtPct(mom)}`;
  });
  return `${sec.name}综合评分 ${sec.score == null ? "—" : sec.score}/100，判定为「${sec.stage}」。核心依据：${parts.join("；")}。`;
}

async function renderOverview() {
  const ov = await api("/api/overview");
  const cards = Object.entries(ov).map(([key, sec]) => {
    const core = sec.members.filter((m) =>
      ["SHFE_CU", "WTI", "BDI"].includes(m.code));
    const rows = core.map((m) => {
      const mom = m.momentum && m.momentum["1Y"];
      return `<div class="row"><span>${esc(m.name)} 1年</span>
        <b class="${pctCls(mom)}">${fmtPct(mom)}</b></div>
        <div class="row"><span>${esc(m.name)} ${m.q_window || "近10年"}分位</span>
        <b><span class="qtag ${qTagClass(m.q10y)}">${qPct(m.q10y)} ${m.q10y_label}</span></b></div>`;
    }).join("");
    return `<div class="sector-card" onclick="location.hash='#/${key}'">
      <div class="hd"><span class="name">${esc(sec.name)}</span>
        <span class="stage-badge ${stageClass(sec.stage)}">${esc(sec.stage)}</span></div>
      <div class="score">${sec.score == null ? "—" : sec.score}<small> /100</small></div>
      <div class="rows">${rows}</div>
      <div class="note">点击进入 ${esc(sec.name)} 详情 →</div>
    </div>`;
  }).join("");

  const table = Object.entries(ov).map(([key, sec]) =>
    sec.members.map((m) => `<tr>
      <td><a href="#/${key}">${esc(sec.name)}</a> · ${esc(m.name)}</td>
      <td>${fmtNum(m.latest)} <span class="muted">(${m.latest_date})</span></td>
      <td class="${pctCls(m.momentum && m.momentum["1M"])}">${fmtPct(m.momentum && m.momentum["1M"])}</td>
      <td class="${pctCls(m.momentum && m.momentum["3M"])}">${fmtPct(m.momentum && m.momentum["3M"])}</td>
      <td class="${pctCls(m.momentum && m.momentum["1Y"])}">${fmtPct(m.momentum && m.momentum["1Y"])}</td>
      <td><span class="qtag ${qTagClass(m.q10y)}">${qPct(m.q10y)} ${m.q10y_label}</span></td>
      <td>${esc(m.stage)}</td></tr>`).join("")
  ).join("");

  $("#view").innerHTML = `
    <h1 class="page-title">总览 · 三板块周期位置（结论先行）</h1>
    <div class="card verdict"><h2>一句话结论</h2>
      <p>${ov.metals ? rich(sectorSentence(ov.metals)) : ""}</p>
      <p>${ov.energy ? rich(sectorSentence(ov.energy)) : ""}</p>
      <p>${ov.shipping ? rich(sectorSentence(ov.shipping)) : ""}</p>
    </div>
    <div class="sector-grid">${cards}</div>
    <div class="card"><h2>全部指标信号明细</h2>
      <table><tr><th>板块 · 指标</th><th>最新值</th><th>1M</th><th>3M</th><th>1Y</th><th>历史分位</th><th>阶段</th></tr>
      ${table}</table>
      <div class="note">评分口径：品种得分 = 60×近10年价格分位 + 40×动量分（3个月涨跌幅，±20%满量程）；板块评分取核心品种均值，不含黄金等货币属性品种。阶段判定规则见「术语百科→价格分位数」。</div>
    </div>`;
}

/* ---------- 页面：板块详情（铁律5：图形优先） ---------- */
let boardState = { tab: "trend", series: null };

const BOARD_CFG = {
  metals: { trendSel: ["SHFE_CU", "SHFE_AL", "SHFE_ZN", "SHFE_NI", "XAU", "XAG", "COMEX_HG", "LME_AL", "LME_NI", "LME_ZN"], inv: ["LME_STOCK_CU", "LME_STOCK_AL", "LME_STOCK_ZN", "LME_STOCK_PB", "LME_STOCK_NI", "LME_STOCK_SN"], cmp: [["SHFE_CU", "沪铜"], ["COMEX_HG", "COMEX铜"]] },
  energy: { trendSel: ["WTI", "BRENT", "INE_SC", "PPI_COAL", "JM", "J", "QHD_Q5500"], inv: ["EIA_PROD"], invLabel: "原油产量", invTitle: "美国原油产量（供给端）", cmp: [["INE_SC", "上海原油SC"], ["WTI", "WTI"]] },
  shipping: { trendSel: ["BDI", "BCI", "BPI", "BSI", "BDTI"], inv: null, cmp: [["BDI", "BDI"], ["BDTI", "BDTI"]] },
};

async function renderBoard(sector) {
  const sec = await api("/api/board/" + sector);
  const cfg = BOARD_CFG[sector];
  boardState = { tab: boardState.tab || "trend", series: boardState.series || cfg.trendSel[0] };

  const verdict = rich(sectorSentence(sec));
  const invText = cfg.inv ? "库存是周期判断里比价格更接近真相的指标（详见术语百科「去库/累库」）。" : "航运无库存概念，用分船型运价的分化观察需求结构。";

  $("#view").innerHTML = `
    <h1 class="page-title">${esc(sec.name)} · 板块详情 <span class="muted">数据截至 ${esc(sec.last_date || "—")}</span></h1>
    <div class="card verdict"><h2>本板块结论</h2>
      <p><span class="stage-badge ${stageClass(sec.stage)}">${esc(sec.stage)}</span> ${verdict}</p>
      <p class="muted" style="margin-top:6px">${rich(invText)}</p></div>
    <div class="card">
      <div class="chart-tabs" id="tabs">
        <button class="tab" data-tab="trend">走势+分位通道</button>
        ${cfg.inv ? `<button class="tab" data-tab="inv">${cfg.invLabel || "库存"}</button>` : '<button class="tab" data-tab="inv">分船型对比</button>'}
        <button class="tab" data-tab="cmp">国内vs国际</button>
        <button class="tab" data-tab="mom">动量</button>
        <select id="seriesSel">${cfg.trendSel.map((c) => {
          const m = sec.members.find((x) => x.code === c);
          return m ? `<option value="${c}">${esc(m.name)}</option>` : "";
        }).join("")}</select>
        <button class="tab" id="toggleTable">图表/数据表</button>
      </div>
      <div id="boardChart" class="chart"></div>
      <div id="boardTable" style="display:none"></div>
    </div>
    <div class="card"><h2>指标一览</h2>
      <table><tr><th>指标</th><th>最新值</th><th>1M</th><th>3M</th><th>6M</th><th>1Y</th><th>历史分位</th><th>阶段</th></tr>
      ${sec.members.map((m) => `<tr>
        <td>${esc(m.name)} <span class="muted">${esc(m.unit || "")}</span></td>
        <td>${fmtNum(m.latest)}</td>
        <td class="${pctCls(m.momentum && m.momentum["1M"])}">${fmtPct(m.momentum && m.momentum["1M"])}</td>
        <td class="${pctCls(m.momentum && m.momentum["3M"])}">${fmtPct(m.momentum && m.momentum["3M"])}</td>
        <td class="${pctCls(m.momentum && m.momentum["6M"])}">${fmtPct(m.momentum && m.momentum["6M"])}</td>
        <td class="${pctCls(m.momentum && m.momentum["1Y"])}">${fmtPct(m.momentum && m.momentum["1Y"])}</td>
        <td><span class="qtag ${qTagClass(m.q10y)}">${qPct(m.q10y)} ${m.q10y_label}</span></td>
        <td>${esc(m.stage)}</td></tr>`).join("")}</table>
    </div>`;

  $("#seriesSel").value = boardState.series;
  $("#seriesSel").onchange = (e) => { boardState.series = e.target.value; drawBoardTab(sec, cfg); };
  $$("#tabs .tab[data-tab]").forEach((b) => {
    b.onclick = () => { boardState.tab = b.dataset.tab; drawBoardTab(sec, cfg); };
  });
  $("#toggleTable").onclick = () => {
    const t = $("#boardTable");
    t.style.display = t.style.display === "none" ? "block" : "none";
    if (t.style.display === "block") fillBoardTable(boardState.series);
  };
  drawBoardTab(sec, cfg);
}

async function drawBoardTab(sec, cfg) {
  $$("#tabs .tab[data-tab]").forEach((b) => b.classList.toggle("active", b.dataset.tab === boardState.tab));
  const sector = sec.name === "有色金属" ? "metals" : sec.name === "能源" ? "energy" : "shipping";
  if (boardState.tab === "trend") {
    const code = boardState.series;
    $("#seriesSel").style.display = "inline";
    const [pts, stats] = await Promise.all([
      api("/api/series/" + code), api("/api/series/" + code + "/stats").catch(() => null),
    ]);
    const name = sec.members.find((m) => m.code === code) ? sec.members.find((m) => m.code === code).name : code;
    drawPriceChart("boardChart", name, pts.points, stats ? stats.channel : null);
  } else if (boardState.tab === "inv") {
    $("#seriesSel").style.display = "none";
    const list = cfg.inv || ["BDI", "BCI", "BPI", "BSI"];
    const datas = await Promise.all(list.map((c) => api("/api/series/" + c)));
    const names = (sec.members || []);
    drawMultiChart("boardChart", cfg.invTitle || (cfg.inv ? "库存趋势" : "分船型运价对比"),
      datas.map((d) => ({ name: (names.find((m) => m.code === d.code) || {}).name || d.code, points: d.points })), !cfg.inv);
  } else if (boardState.tab === "cmp") {
    $("#seriesSel").style.display = "none";
    const datas = await Promise.all(cfg.cmp.map(([c]) => api("/api/series/" + c)));
    drawMultiChart("boardChart", "国内 vs 国际定价",
      datas.map((d, i) => ({ name: cfg.cmp[i][1], points: d.points })), true);
  } else if (boardState.tab === "mom") {
    $("#seriesSel").style.display = "none";
    const members = sec.members.filter((m) => m.momentum && m.momentum["1M"] != null).slice(0, 10);
    drawMomentumChart("boardChart", members);
  }
}

async function fillBoardTable(code) {
  const pts = await api("/api/series/" + code);
  const rows = pts.points.slice(-30).reverse().map((p) => `<tr><td>${p[0]}</td><td>${fmtNum(p[1])}</td></tr>`).join("");
  $("#boardTable").innerHTML = `<table><tr><th>日期</th><th>数值</th></tr>${rows}</table>
    <div class="note">仅显示最近 30 个交易日，完整数据可导出（V2）。</div>`;
}

/* ---------- 页面：股商对照 ---------- */
async function renderCompare() {
  $("#view").innerHTML = `
    <h1 class="page-title">股商对照 · 商品价格 vs 板块股票指数</h1>
    <div class="card">
      <div class="chart-tabs">
        <select id="cmpA"><option value="SHFE_CU">沪铜</option><option value="SHFE_AL">沪铝</option><option value="WTI">WTI原油</option><option value="JM">焦煤</option><option value="BDI">BDI</option></select>
        <span class="muted"> vs </span>
        <select id="cmpB"><option value="SW_METALS">申万有色指数</option><option value="SW_COAL">申万煤炭指数</option></select>
      </div>
      <div id="cmpChart" class="chart"></div>
      <div class="note" id="cmpNote"></div>
    </div>
    <div class="card"><h2>怎么用这张图</h2>
      <p>${rich("商品价格与对应板块股票指数长期同向，当两者方向相反时叫「股商背离」。股价先于商品见顶/见底是 A 股周期股的常见现象（通常领先 1-3 个月）。图下方的滚动相关性跌破 0.3 时要格外警惕：说明市场开始不认可商品涨价的持续性。")}</p></div>`;
  const draw = async () => {
    const a = $("#cmpA").value, b = $("#cmpB").value;
    const [da, dbb] = await Promise.all([api("/api/series/" + a), api("/api/series/" + b)]);
    // 按日期对齐
    const bMap = Object.fromEntries(dbb.points.map((p) => p));
    const alignA = da.points.filter((p) => bMap[p[0]] != null);
    const alignB = alignA.map((p) => [p[0], bMap[p[0]]]);
    drawDualChart("cmpChart", $("#cmpA").selectedOptions[0].text, alignA, $("#cmpB").selectedOptions[0].text, alignB);
    $("#cmpNote").textContent = "对齐区间: " + (alignA[0] ? alignA[0][0] : "—") + " ~ " + (alignA.length ? alignA[alignA.length - 1][0] : "—") + "，共 " + alignA.length + " 个交易日。";
  };
  $("#cmpA").onchange = draw; $("#cmpB").onchange = draw;
  await draw();
}

function drawDualChart(id, nameA, ptsA, nameB, ptsB) {
  const c = mkChart(id);
  if (!c) return;
  const x = ptsA.map((p) => p[0]);
  c.setOption({
    tooltip: TOOLTIP,
    legend: { top: 8, textStyle: { fontSize: 12 } },
    grid: { left: 70, right: 70, top: 40, bottom: 50 },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 20, bottom: 8 }],
    xAxis: { type: "category", data: x, ...AXIS_STYLE },
    yAxis: [
      { type: "value", scale: true, name: nameA, ...AXIS_STYLE },
      { type: "value", scale: true, name: nameB, ...AXIS_STYLE },
    ],
    series: [
      { type: "line", name: nameA, data: ptsA.map((p) => p[1]), showSymbol: false, lineStyle: { color: "#2563eb" } },
      { type: "line", name: nameB, yAxisIndex: 1, data: ptsB.map((p) => p[1]), showSymbol: false, lineStyle: { color: "#d97706" } },
    ],
  });
}

/* ---------- 页面：研判报告 ---------- */
async function renderReports() {
  const list = await api("/api/reports");
  $("#view").innerHTML = `
    <h1 class="page-title">研判报告</h1>
    <div class="cols-2">
      <div class="card report-list" style="align-self:start">
        <h2>报告列表</h2>
        ${list.length ? list.map((n, i) => `<a href="#" data-r="${n}" class="${i === 0 ? "active" : ""}">${esc(n.replace(".html", ""))}</a>`).join("") : '<p class="muted">暂无报告</p>'}
      </div>
      <div>${list.length ? '<iframe id="repFrame" class="report-frame" src="/reports/' + encodeURIComponent(list[0]) + '"></iframe>' : ""}</div>
    </div>`;
  $$(".report-list a").forEach((a) => {
    a.onclick = (e) => {
      e.preventDefault();
      $$(".report-list a").forEach((x) => x.classList.remove("active"));
      a.classList.add("active");
      $("#repFrame").src = "/reports/" + encodeURIComponent(a.dataset.r);
    };
  });
}

/* ---------- 页面：术语百科 ---------- */
async function renderGlossary() {
  if (!GLOSSARY.length) GLOSSARY = await api("/api/glossary");
  $("#view").innerHTML = `
    <h1 class="page-title">术语百科</h1>
    <div class="glossary-grid">
      ${GLOSSARY.map((g) => `<div class="card">
        <h2>${esc(g.term)}</h2>
        <p class="muted">${esc(g.en)}</p>
        <p style="margin-top:8px">${esc(g.plain)}</p>
        <p class="why"><b>为什么重要：</b>${esc(g.why)}</p>
        <p class="where"><b>在哪看：</b>${esc(g.where)}</p>
      </div>`).join("")}
    </div>`;
}

/* ---------- 路由 ---------- */
const ROUTES = {
  overview: renderOverview, metals: () => renderBoard("metals"),
  energy: () => renderBoard("energy"), shipping: () => renderBoard("shipping"),
  compare: renderCompare, reports: renderReports, glossary: renderGlossary,
};

async function route() {
  const key = (location.hash || "#/overview").replace("#/", "").split("?")[0] || "overview";
  $$("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.nav === key));
  $("#view").innerHTML = '<div class="loading">加载中…</div>';
  const fn = ROUTES[key] || renderOverview;
  try { await fn(); } catch (e) {
    $("#view").innerHTML = `<div class="card" style="color:#d93025">加载失败：${esc(e.message)}</div>`;
  }
  window.scrollTo(0, 0);
}

async function boot() {
  await loadStatus();
  GLOSSARY = await api("/api/glossary").catch(() => []);
  $("#btnRefresh").onclick = doRefresh;
  window.addEventListener("hashchange", route);
  await route();
}
boot();

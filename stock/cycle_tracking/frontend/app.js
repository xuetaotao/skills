"use strict";

/* ================= 基础工具 ================= */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const app = $("#app");

const state = {
  meta: null, glossary: [], termRe: null, termIndex: {},
  status: null, polling: null, charts: [], token: 0, initMode: false,
};

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch { /* 非 JSON */ }
    const e = new Error(msg);
    e.status = r.status;
    throw e;
  }
  return r.json();
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function fmtNum(v) {
  if (v == null || !isFinite(v)) return "—";
  const a = Math.abs(v);
  const d = a >= 1000 ? 0 : a >= 1 ? 2 : 3;
  return v.toLocaleString("zh-CN", { minimumFractionDigits: d, maximumFractionDigits: d });
}

function compact(v) {
  const a = Math.abs(v);
  if (a >= 1e8) return (v / 1e8).toFixed(1) + "亿";
  if (a >= 1e4) return (v / 1e4).toFixed(a >= 1e5 ? 0 : 1) + "万";
  return fmtNum(v);
}

const signedTxt = (v, d = 1) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`);
const chg = (v) => (v == null ? `<span class="muted">—</span>`
  : `<span class="${v > 0 ? "up" : v < 0 ? "down" : ""}">${signedTxt(v)}</span>`);
const pctText = (q) => (q == null ? "—" : `${Math.round(q * 100)}%`);
const shortDate = (d) => (d ? d.slice(5) : "—");

const ROLE = { price: "价格", inventory: "库存", supply: "供给", equity: "股票指数", freight: "运价", macro: "综合指数" };
const SOURCE = {
  sina_main: "新浪 · 国内期货", sina_foreign: "新浪 · 外盘", lme_stock: "LME 库存", eia_crude: "EIA",
  cn_index: "AKShare 宏观指数", sw: "申万指数", shipping: "航运指数", ppi_vane: "生意社",
  ppi_qhd: "生意社（档案）", manual: "手动录入",
};
const LEVEL = { risk: "风险", watch: "留意", positive: "积极", info: "提示" };

function tempColor(t) {
  if (t == null) return "var(--muted)";
  return t >= 80 ? "var(--hot)" : t >= 60 ? "var(--warm)" : t >= 25 ? "var(--mid)" : "var(--cold)";
}

const stageTone = (stage) => state.meta?.stages?.[stage]?.tone || "flat";
const stageBadge = (stage, small) => (!stage || stage === "数据不足"
  ? `<span class="stage tone-none${small ? " sm" : ""}">数据不足</span>`
  : `<span class="stage tone-${stageTone(stage)}${small ? " sm" : ""}">${esc(stage)}</span>`);

function toast(text, kind = "ok", ms = 4000) {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = text;
  $("#toasts").appendChild(el);
  setTimeout(() => el.classList.add("out"), ms);
  setTimeout(() => el.remove(), ms + 400);
}

/* ================= 术语悬停解释 ================= */

function buildTerms() {
  const keys = [];
  state.glossary.forEach((g, i) => (g.keys || [g.term]).forEach((k) => {
    keys.push(k);
    state.termIndex[k] = i;
  }));
  keys.sort((a, b) => b.length - a.length);
  const pat = keys.map((k) => esc(k).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  state.termRe = pat ? new RegExp(pat, "g") : null;
}

/** 转义文本，并给每个术语的第一次出现加上悬停解释（单次扫描，不会嵌套替换） */
function rich(text) {
  const html = esc(text);
  if (!state.termRe) return html;
  const seen = new Set();
  return html.replace(state.termRe, (m) => {
    const i = state.termIndex[m];
    if (i == null || seen.has(i)) return m;
    seen.add(i);
    return `<span class="term" data-term="${i}">${m}</span>`;
  });
}

function setupTooltip() {
  const tip = $("#tip");
  document.addEventListener("mouseover", (e) => {
    const t = e.target.closest?.(".term");
    if (!t) { tip.hidden = true; return; }
    const g = state.glossary[+t.dataset.term];
    if (!g) return;
    tip.innerHTML = `<div class="tip-title">${esc(g.term)}<small>${esc(g.en || "")}</small></div>
      <p>${esc(g.plain)}</p><p class="tip-why">${esc(g.why)}</p>`;
    tip.hidden = false;
    const r = t.getBoundingClientRect();
    const w = tip.offsetWidth, h = tip.offsetHeight;
    let left = Math.min(Math.max(8, r.left), window.innerWidth - w - 8);
    let top = r.bottom + 8;
    if (top + h > window.innerHeight - 8) top = r.top - h - 8;
    tip.style.left = `${left}px`;
    tip.style.top = `${Math.max(8, top)}px`;
  });
  window.addEventListener("scroll", () => { tip.hidden = true; }, { passive: true });
}

/* ================= 状态、刷新与首次初始化 ================= */

async function refreshStatus() {
  state.status = await api("/api/status");
  renderStatus();
  return state.status;
}

function renderStatus() {
  const s = state.status;
  const pill = $("#statusPill"), bar = $("#progress"), btn = $("#btnRefresh");
  if (!s) return;
  if (s.updating) {
    pill.innerHTML = `<span class="spinner"></span>刷新中 ${s.done}/${s.total}`;
    pill.className = "status-pill busy";
    bar.hidden = false;
    $("i", bar).style.width = `${s.total ? (s.done / s.total) * 100 : 5}%`;
    btn.disabled = true;
  } else {
    const staleN = s.stale?.length || 0;
    pill.innerHTML = s.empty ? "暂无数据"
      : `<span class="dot ${staleN ? "amber" : "ok"}"></span>数据截至 ${shortDate(s.data_as_of)} · ${staleN ? `${staleN} 项滞后` : "全部正常"}`;
    pill.className = `status-pill${staleN ? " warn" : ""}`;
    pill.title = `上次刷新：${s.last_refresh || "从未"}${staleN ? `\n滞后：${s.stale.map((x) => x.name).join("、")}` : ""}\n点击查看数据健康`;
    bar.hidden = true;
    btn.disabled = false;
  }
  if (state.initMode) renderInit();
}

function startPolling() {
  if (state.polling) return;
  state.polling = setInterval(async () => {
    let s;
    try { s = await refreshStatus(); } catch { return; }
    if (s.updating) return;
    clearInterval(state.polling);
    state.polling = null;
    if (s.empty) { renderInit(); return; }
    if (s.last_error) toast(`刷新完成，但有问题：${s.last_error}`, "warn", 8000);
    else toast("数据已更新到最新", "ok");
    state.initMode = false;
    render();
  }, 1500);
}

async function manualRefresh() {
  try {
    const r = await api("/api/refresh", { method: "POST" });
    toast(r.started ? "开始刷新，大约需要 1–2 分钟，可以继续浏览" : "已经在刷新中", "info");
    await refreshStatus();
    startPolling();
  } catch (e) {
    toast(`刷新失败：${e.message}`, "warn");
  }
}

function renderInit() {
  const s = state.status || {};
  if (!s.updating) {
    app.innerHTML = `
      <section class="init">
        <h1>数据还没有准备好</h1>
        <p>初始化没有成功获取到数据，可能是网络或数据源暂时不可用。</p>
        ${s.last_error ? `<p class="warn-text">${esc(s.last_error)}</p>` : ""}
        <button class="btn primary" id="btnRetry">重试</button>
      </section>`;
    $("#btnRetry").onclick = manualRefresh;
    return;
  }
  const pct = s.total ? Math.round((s.done / s.total) * 100) : 0;
  app.innerHTML = `
    <section class="init">
      <h1>正在初始化数据</h1>
      <p>首次运行需要从各数据源下载十几年的历史数据，大约 2–5 分钟。完成后页面会自动刷新。</p>
      <div class="init-bar"><i style="width:${pct}%"></i></div>
      <p class="muted">${s.done || 0} / ${s.total || "…"} ${s.current_name ? `· 正在获取：${esc(s.current_name)}` : ""}</p>
      ${s.last_error ? `<p class="warn-text">${esc(s.last_error)}</p>` : ""}
    </section>`;
}

/* ================= 图表管理 ================= */

function makeChart(el) {
  const c = echarts.init(el, null, { renderer: "canvas" });
  state.charts.push(c);
  return c;
}

function disposeCharts() {
  state.charts.forEach((c) => c.dispose());
  state.charts = [];
}

window.addEventListener("resize", () => state.charts.forEach((c) => c.resize()));

const AXIS_STYLE = {
  axisLine: { lineStyle: { color: "#d5dae1" } },
  axisLabel: { color: "#6b7482", fontSize: 11 },
  splitLine: { lineStyle: { color: "#eef1f4" } },
};

function zoomTo(chart, range, lastDate, xAxisIndex) {
  if (range === "all") {
    chart.dispatchAction({ type: "dataZoom", start: 0, end: 100, xAxisIndex });
    return;
  }
  const end = new Date(lastDate);
  const start = new Date(end);
  start.setFullYear(end.getFullYear() - Number(range));
  chart.dispatchAction({ type: "dataZoom", startValue: start.getTime(), endValue: end.getTime(), xAxisIndex });
}

const rangeButtons = (active) => `<div class="seg-btns" data-role="range">
  ${[["1", "1年"], ["3", "3年"], ["5", "5年"], ["10", "10年"], ["all", "全部"]]
    .map(([v, t]) => `<button data-range="${v}" class="${v === active ? "on" : ""}">${t}</button>`).join("")}</div>`;

/* ================= 通用组件 ================= */

function sparkline(pts, w = 120, h = 30) {
  if (!pts || pts.length < 2) return `<div class="spark empty"></div>`;
  const vs = pts.map((p) => p[1]);
  const min = Math.min(...vs), max = Math.max(...vs), span = max - min || 1;
  const d = pts.map((p, i) => `${((i / (pts.length - 1)) * w).toFixed(1)},${(h - 2 - ((p[1] - min) / span) * (h - 4)).toFixed(1)}`).join(" ");
  const up = vs[vs.length - 1] >= vs[0];
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><polyline points="${d}" class="${up ? "up" : "down"}"/></svg>`;
}

function tempBar(t, prev) {
  if (t == null) return `<div class="tbar-empty">数据不足，无法计算温度</div>`;
  const ticks = [[25, "25"], [50, "50"], [80, "80"]];
  return `<div class="tbar">
    <div class="tbar-track">
      ${prev != null && prev !== t ? `<span class="tbar-prev" style="left:${prev}%" title="一个月前：${prev}"></span>` : ""}
      <span class="tbar-mark" style="left:${t}%"></span>
    </div>
    <div class="tbar-scale"><span style="left:0">冷</span>${ticks.map(([p, l]) => `<span style="left:${p}%">${l}</span>`).join("")}<span style="left:100%">热</span></div>
  </div>`;
}

function tempDelta(t, prev) {
  if (t == null || prev == null) return "";
  const d = t - prev;
  if (d === 0) return `<span class="muted">较上月持平</span>`;
  return `<span class="muted">较上月</span> <span class="${d > 0 ? "up" : "down"}">${d > 0 ? "+" : ""}${d}</span>`;
}

function qBar(s) {
  if (s.q == null) return `<div class="qbar na">样本不足，暂无分位</div>`;
  const p = Math.round(s.q * 100);
  return `<div class="qbar">
    <div class="qbar-track${s.role === "inventory" ? " inv" : ""}"><i style="left:${p}%"></i></div>
    <div class="qbar-label">${esc(s.window)}第 <b>${p}%</b> 分位 · ${esc(s.level)}</div>
  </div>`;
}

function freshBadge(s) {
  if (s.archive) return `<span class="badge gray" title="已停更的历史档案，只展示，不参与当前判断">档案</span>`;
  if (s.stale) return `<span class="badge amber" title="最新数据 ${s.latest_date}，已滞后 ${s.lag_days} 天，不参与结论">滞后 ${s.lag_days} 天</span>`;
  return `<span class="badge ok" title="最新数据日期 ${s.latest_date}">${shortDate(s.latest_date)}</span>`;
}

function signalLink(s) {
  const codes = s.codes || [];
  const roleOf = (c) => state.meta.series.find((x) => x.code === c)?.role;
  if (codes.length === 2 && roleOf(codes[1]) === "equity") return `#/compare/${codes[0]}/${codes[1]}`;
  return codes.length ? `#/sector/${s.sector}/${codes[0]}` : `#/sector/${s.sector}`;
}

function signalItem(s, withSector) {
  const sec = withSector ? `<span class="sig-sector">${esc(state.meta.sectors[s.sector] || "")}</span>` : "";
  return `<a class="signal lv-${s.level}" href="${signalLink(s)}">
    <span class="lv">${LEVEL[s.level]}</span>
    <div class="sig-body"><div class="sig-title">${sec}${esc(s.title)}</div><div class="sig-text">${rich(s.text)}</div></div>
    <span class="sig-go">›</span>
  </a>`;
}

function signalList(list, withSector, empty = "暂无需要特别关注的信号。") {
  return list.length ? `<div class="signals">${list.map((s) => signalItem(s, withSector)).join("")}</div>`
    : `<div class="empty">${empty}</div>`;
}

/* 周期轮盘：顺时针为周期运行方向，上半圈偏热、下半圈偏冷，中心为中位震荡 */
const WHEEL_ANGLE = { "高位回落": -60, "下行中段": 0, "低位寻底": 60, "低位回升": 120, "上行中段": 180, "高位强势": 240 };

function cycleWheel(items, size = 300) {
  const c = size / 2, R = size * 0.43, r = size * 0.23;
  const xy = (deg, rad) => [c + rad * Math.cos((deg * Math.PI) / 180), c + rad * Math.sin((deg * Math.PI) / 180)];
  const f = (n) => n.toFixed(1);
  let svg = "";
  for (const [st, a] of Object.entries(WHEEL_ANGLE)) {
    const a0 = a - 29, a1 = a + 29;
    const [x0, y0] = xy(a0, R), [x1, y1] = xy(a1, R), [x2, y2] = xy(a1, r), [x3, y3] = xy(a0, r);
    const active = items.some((i) => i.stage === st);
    const meaning = state.meta.stages[st]?.meaning || "";
    svg += `<path class="wseg tone-${stageTone(st)}${active ? " active" : ""}"
      d="M${f(x0)},${f(y0)} A${R},${R} 0 0 1 ${f(x1)},${f(y1)} L${f(x2)},${f(y2)} A${r},${r} 0 0 0 ${f(x3)},${f(y3)} Z"><title>${st}：${meaning}</title></path>`;
    const [lx, ly] = xy(a, (R + r) / 2);
    svg += `<text x="${f(lx)}" y="${f(ly)}" class="wlabel${active ? " active" : ""}">${st}</text>`;
  }
  // 方向箭头（每段之间）
  for (const a of [-90, -30, 30, 90, 150, 210]) {
    const [ax, ay] = xy(a, R + 6);
    svg += `<text x="${f(ax)}" y="${f(ay)}" class="warrow" transform="rotate(${a + 90} ${f(ax)} ${f(ay)})">›</text>`;
  }
  const flat = items.some((i) => i.stage === "中位震荡");
  svg += `<circle cx="${c}" cy="${c}" r="${r - 10}" class="wcenter${flat ? " active" : ""}"><title>中位震荡：${state.meta.stages["中位震荡"]?.meaning || ""}</title></circle>
    <text x="${c}" y="${c}" class="wlabel${flat ? " active" : ""}">中位震荡</text>`;

  // 板块标记：同一阶段的多个板块错开角度
  const byStage = {};
  items.forEach((i) => (byStage[i.stage] = byStage[i.stage] || []).push(i));
  for (const [st, list] of Object.entries(byStage)) {
    list.forEach((it, k) => {
      const col = tempColor(it.temp);
      if (st === "中位震荡") {
        const y = c + 18 + k * 18;
        svg += `<a href="${it.href}"><circle cx="${c}" cy="${y}" r="5" fill="${col}"/><text x="${c + 9}" y="${y}" class="wmark">${esc(it.label)}</text></a>`;
        return;
      }
      if (!(st in WHEEL_ANGLE)) return;
      const a = WHEEL_ANGLE[st] + (k - (list.length - 1) / 2) * 16;
      const [mx, my] = xy(a, R);
      const [tx, ty] = xy(a, R + 20);
      const anchor = Math.cos((a * Math.PI) / 180) > 0.2 ? "start" : Math.cos((a * Math.PI) / 180) < -0.2 ? "end" : "middle";
      svg += `<a href="${it.href}"><circle cx="${f(mx)}" cy="${f(my)}" r="8" fill="${col}" class="wdot"/>
        <text x="${f(tx)}" y="${f(ty)}" class="wmark" text-anchor="${anchor}">${esc(it.label)}</text></a>`;
    });
  }
  const pad = 70;
  return `<svg class="wheel" viewBox="${-pad} ${-20} ${size + pad * 2} ${size + 40}">${svg}</svg>`;
}

/* ================= 总览 ================= */

async function renderOverview(token) {
  const d = await api("/api/overview");
  if (token !== state.token) return;
  const sectors = Object.values(d.sectors);
  const st = state.status || {};
  const staleNote = st.stale?.length
    ? `<a class="notice" href="#/health"><b>${st.stale.length} 个指标数据滞后</b>（${esc(st.stale.slice(0, 4).map((x) => x.name).join("、"))}${st.stale.length > 4 ? " 等" : ""}），已自动排除出结论，点击查看 ›</a>` : "";

  app.innerHTML = `
    <section class="hero card">
      <div class="hero-text">
        <div class="eyebrow">今日结论 · ${esc(d.today)}</div>
        <h1>${rich(d.headline)}</h1>
        ${staleNote}
      </div>
      <div class="hero-wheel">
        ${cycleWheel(sectors.map((s) => ({ stage: s.stage, temp: s.temp, label: `${s.name} ${s.temp ?? "—"}`, href: `#/sector/${s.key}` })))}
        <div class="wheel-cap">周期轮盘：顺时针运行，上半圈偏热、下半圈偏冷</div>
      </div>
    </section>

    <section class="sector-grid">${sectors.map(sectorCard).join("")}</section>

    <section class="card">
      <div class="card-head"><h2>需要关注</h2><span class="muted">按重要程度排序，点击查看依据</span></div>
      ${signalList(d.highlights, true)}
    </section>

    <details class="card method">
      <summary>这些结论是怎么得出的？</summary>
      <div class="method-body">
        <p><b>${rich("周期温度")}</b>：板块核心商品价格在近 10 年中所处位置的平均（0 最便宜，100 最贵）。板块内先按品类分组计温再平均，避免某一类品种数量多就主导结论。</p>
        <p><b>${rich("周期阶段")}</b>：温度 ≥ 80 为高位、< 25 为低位；近 3 个月涨跌超过 ±3% 才算有方向。位置 × 方向组合成七个阶段，每个阶段附带决策提示。</p>
        <p><b>信号</b>：价格与库存的配合（价涨库降、价涨库增等）、供给水平、板块股票与商品是否背离、组内品种是否分化、与一个月前相比阶段是否改变。</p>
        <p><b>${rich("数据新鲜度")}</b>：过期数据和停更档案只展示、不参与结论；数据源偶发的串列、漏位等坏点在分析时剔除（数据库保留原值），详见「数据健康」。</p>
      </div>
    </details>`;
}

function sectorCard(s) {
  const groups = s.groups.map((g) => `
    <div class="mini-group">
      <span class="mg-name">${esc(g.name)}</span>
      <span class="mg-temp" style="color:${tempColor(g.temp)}">${g.temp ?? "—"}</span>
      ${stageBadge(g.stage, true)}
      <span class="mg-m3">3个月 ${chg(g.m3)}</span>
      ${g.confidence === "低" ? `<span class="badge amber" title="参与计算的品种历史较短或数据不全">可信度低</span>` : ""}
    </div>`).join("");
  const top = s.signals.filter((x) => x.level !== "info").slice(0, 2);
  return `
    <a class="card sector-card tone-${s.tone}" href="#/sector/${s.key}">
      <div class="sc-head">
        <h2>${esc(s.name)}</h2>
        ${stageBadge(s.stage)}
      </div>
      <div class="sc-temp">
        <div class="temp-num" style="color:${tempColor(s.temp)}">${s.temp ?? "—"}<small>/100</small></div>
        <div class="sc-temp-side">
          <div>周期温度 · ${tempDelta(s.temp, s.prev_temp)}</div>
          <div>3个月趋势 ${chg(s.m3)} · ${esc(s.trend)}</div>
        </div>
      </div>
      ${tempBar(s.temp, s.prev_temp)}
      <p class="sc-meaning">${esc(s.stage_meaning)}${s.stage_changed ? `<span class="badge blue">上月为「${esc(s.prev_stage)}」</span>` : ""}</p>
      <div class="hint"><b>决策提示</b>${esc(s.hint)}</div>
      <div class="mini-groups">${groups}</div>
      ${top.length ? `<ul class="sc-signals">${top.map((x) => `<li class="lv-${x.level}"><span class="lv">${LEVEL[x.level]}</span>${esc(x.title)}</li>`).join("")}</ul>` : ""}
      <div class="sc-foot"><span class="muted">数据截至 ${esc(s.last_date || "—")}</span><span class="go">查看详情 ›</span></div>
    </a>`;
}

/* ================= 板块页 ================= */

async function renderSector(token, key, code) {
  const s = await api(`/api/sector/${encodeURIComponent(key)}`);
  if (token !== state.token) return;
  const byCode = Object.fromEntries(s.members.map((m) => [m.code, m]));
  const used = new Set();
  const sections = s.groups.map((g) => {
    const codes = [...g.core, ...g.aux].filter((c) => byCode[c]);
    codes.forEach((c) => used.add(c));
    return { title: g.name, desc: "标「计温」的是核心价格，参与温度和阶段；其余为辅助信号指标", codes, core: new Set(g.core) };
  }).filter((sec) => sec.codes.length);
  const equity = s.members.filter((m) => m.role === "equity" && !used.has(m.code));
  equity.forEach((m) => used.add(m.code));
  if (equity.length) sections.push({ title: "板块股票", desc: "用于股商对照，不参与温度", codes: equity.map((m) => m.code), core: new Set() });
  const rest = s.members.filter((m) => !used.has(m.code));
  if (rest.length) sections.push({ title: "其他参考", desc: "不参与温度，帮助理解全貌（如贵金属、其他品种、综合指数、历史档案）", codes: rest.map((m) => m.code), core: new Set() });

  const selected = code && byCode[code] ? code : s.groups[0]?.core.find((c) => byCode[c]) || s.members[0]?.code;

  const groupCards = s.groups.map((g) => `
    <div class="group-card">
      <div class="gc-head"><b>${esc(g.name)}</b>${stageBadge(g.stage, true)}</div>
      <div class="gc-temp"><span style="color:${tempColor(g.temp)}">${g.temp ?? "—"}</span><small>温度</small>
        <span class="gc-m3">3个月 ${chg(g.m3)}</span></div>
      ${tempBar(g.temp)}
      <div class="gc-meta">计温品种：${g.core.map((c) => esc(byCode[c]?.name || c)).join("、")} · 可信度 ${esc(g.confidence)}</div>
      ${g.excluded.length ? `<div class="gc-excl">${g.excluded.map((x) => `${esc(x.name)}：${esc(x.reason)}`).join("<br>")}</div>` : ""}
    </div>`).join("");

  const eq = s.equity;
  const equityCard = eq ? `
    <a class="card equity-card" href="#/compare/${eq.codes[0]}/${eq.codes[1]}">
      <div class="card-head"><h2>${rich("股商对照")}</h2><span class="go">打开对照图 ›</span></div>
      <div class="eq-row">
        <div><small>${esc(eq.commodity)}</small><b>${chg(eq.ret_commodity)}</b></div>
        <div class="vs">vs</div>
        <div><small>${esc(eq.equity)}</small><b>${chg(eq.ret_equity)}</b></div>
        <div><small>${eq.horizon} 日相关系数</small><b>${eq.corr == null ? "—" : eq.corr.toFixed(2)}</b></div>
      </div>
      <p class="muted">近 ${eq.horizon} 个交易日的涨跌幅。股票往往领先商品反映预期，两者明显背离时值得留意。</p>
    </a>` : "";

  app.innerHTML = `
    <div class="crumb"><a href="#/">总览</a> › ${esc(s.name)}</div>
    <section class="card verdict tone-${s.tone}">
      <div class="verdict-main">
        <div class="eyebrow">${esc(s.name)} · ${esc(s.brief)}</div>
        <div class="verdict-row">
          <div class="temp-num big" style="color:${tempColor(s.temp)}">${s.temp ?? "—"}<small>/100</small></div>
          <div>
            <div class="verdict-stage">${stageBadge(s.stage)} <span class="muted">${esc(s.stage_meaning)}</span></div>
            <div class="verdict-sub">周期温度 · ${tempDelta(s.temp, s.prev_temp)} · 3个月趋势 ${chg(s.m3)}（${esc(s.trend)}）· 数据截至 ${esc(s.last_date || "—")}</div>
          </div>
        </div>
        ${tempBar(s.temp, s.prev_temp)}
        <div class="hint big"><b>决策提示</b>${esc(s.hint)}</div>
      </div>
      <div class="verdict-wheel">${cycleWheel([{ stage: s.stage, temp: s.temp, label: `${s.temp ?? "—"}`, href: `#/sector/${s.key}` }], 240)}</div>
    </section>

    <section class="group-grid">${groupCards}</section>

    <section class="two-col">
      <div class="card">
        <div class="card-head"><h2>信号</h2><span class="muted">点击定位到相关指标</span></div>
        ${signalList(s.signals, false)}
      </div>
      ${equityCard || `<div class="card"><div class="card-head"><h2>股商对照</h2></div><div class="empty">该板块暂无对应的 A 股行业指数。</div></div>`}
    </section>

    <section class="card" id="chartCard">
      <div class="card-head">
        <h2 id="chartTitle">走势</h2>
        <div class="chart-tools">
          ${rangeButtons("5")}
          <label class="chk"><input type="checkbox" id="optChannel" checked>分位线</label>
          <label class="chk"><input type="checkbox" id="optOutliers">坏点</label>
          <button class="btn sm" id="optTable">数据表</button>
        </div>
      </div>
      <p class="chart-verdict" id="chartVerdict"></p>
      <div class="chart" id="seriesChart"></div>
      <div id="seriesTable" hidden></div>
      <p class="muted small" id="chartNote"></p>
    </section>

    ${sections.map((sec) => `
      <section class="series-section">
        <div class="section-head"><h3>${esc(sec.title)}</h3><span class="muted">${esc(sec.desc)}</span></div>
        <div class="series-grid">${sec.codes.map((c) => seriesCard(byCode[c], c === selected, sec.core.has(c))).join("")}</div>
      </section>`).join("")}`;

  $$(".scard").forEach((el) => el.addEventListener("click", () => {
    $$(".scard.selected").forEach((x) => x.classList.remove("selected"));
    el.classList.add("selected");
    history.replaceState(null, "", `#/sector/${key}/${el.dataset.code}`);
    loadSeries(el.dataset.code, byCode[el.dataset.code], token);
    $("#chartCard").scrollIntoView({ behavior: "smooth", block: "start" });
  }));
  if (selected) {
    await loadSeries(selected, byCode[selected], token);
    if (code) $("#chartCard")?.scrollIntoView({ block: "start" });
  }
}

function seriesCard(s, selected, isCore) {
  const m = s.momentum || {};
  let tags = "";
  if (isCore) tags += `<span class="tag core" title="参与周期温度与阶段计算">计温</span>`;
  if (s.role === "inventory") tags += `<span class="tag">${esc(s.inv_dir)}</span><span class="tag">${esc(s.inv_level)}</span>`;
  else if ((s.role === "price" || s.role === "freight") && s.stage) tags += stageBadge(s.stage, true);
  else tags += `<span class="tag">${ROLE[s.role] || s.role}</span>`;
  return `
    <button class="scard${selected ? " selected" : ""}${s.stale ? " is-stale" : ""}" data-code="${s.code}">
      <div class="scard-head"><span class="scard-name">${esc(s.name)}</span>${freshBadge(s)}</div>
      <div class="scard-value"><b>${fmtNum(s.latest)}</b><small>${esc(s.unit)}</small></div>
      ${sparkline(s.spark)}
      ${qBar(s)}
      <div class="scard-mom"><span>1月 ${chg(m["1M"])}</span><span>3月 ${chg(m["3M"])}</span><span>1年 ${chg(m["1Y"])}</span></div>
      <div class="scard-tags">${tags}${s.note ? `<span class="note-dot" title="${esc(s.note)}">口径说明</span>` : ""}</div>
    </button>`;
}

function seriesVerdict(s) {
  let t = `${s.name}最新 ${fmtNum(s.latest)} ${s.unit}（${s.latest_date}）`;
  if (s.q != null) t += `，处于${s.window}第 ${pctText(s.q)} 分位（${s.level}）`;
  if (s.momentum["3M"] != null) t += `，近 3 个月 ${signedTxt(s.momentum["3M"])}`;
  if (s.role === "inventory") t += `，${s.inv_dir}，${s.inv_level}`;
  else if ((s.role === "price" || s.role === "freight") && s.stage) t += `，处于「${s.stage}」阶段`;
  t += "。";
  if (s.archive) t += "这是已停更的历史档案，不参与当前判断。";
  else if (s.stale) t += `注意：数据已滞后 ${s.lag_days} 天，不参与当前结论。`;
  if (!s.reliable && s.q != null) t += `历史只有 ${s.span_years} 年，分位的参考价值有限。`;
  return t;
}

async function loadSeries(code, stats, token) {
  const d = await api(`/api/series/${encodeURIComponent(code)}`);
  if (token !== state.token) return;
  const s = d.stats;
  $("#chartTitle").textContent = `${s.name}（${s.unit}）`;
  $("#chartVerdict").innerHTML = rich(seriesVerdict(s));
  const notes = [];
  if (s.channel) notes.push(`虚线自上而下为${s.window}的 90/75/50/25/10 分位线`);
  if (d.outliers.length) notes.push(`已剔除 ${d.outliers.length} 个坏点（勾选「坏点」可在图上查看）`);
  if (s.note) notes.push(s.note);
  notes.push(`数据 ${s.first_date} ~ ${s.latest_date}，共 ${s.points} 个点`);
  $("#chartNote").textContent = notes.join("；");

  const el = $("#seriesChart");
  const old = state.charts.find((c) => c.getDom() === el);
  if (old) { old.dispose(); state.charts = state.charts.filter((c) => c !== old); }
  const chart = makeChart(el);
  const opts = () => ({ channel: $("#optChannel").checked, outliers: $("#optOutliers").checked });
  const draw = () => {
    chart.setOption(seriesOption(d, s, opts()), true);
    zoomTo(chart, $("[data-role=range] .on")?.dataset.range || "5", s.latest_date);
  };
  draw();

  $("#optChannel").onchange = draw;
  $("#optOutliers").onchange = draw;
  $$("[data-role=range] button").forEach((b) => (b.onclick = () => {
    $$("[data-role=range] button").forEach((x) => x.classList.toggle("on", x === b));
    zoomTo(chart, b.dataset.range, s.latest_date);
  }));
  const table = $("#seriesTable");
  table.hidden = true;
  $("#optTable").onclick = () => {
    table.hidden = !table.hidden;
    if (!table.hidden) table.innerHTML = dataTable(d.points, s.unit);
  };
}

function seriesOption(d, s, o) {
  const series = [{
    type: "line", name: s.name, data: d.points, showSymbol: false, sampling: "lttb",
    lineStyle: { width: 1.6, color: "#2f6fdb" }, areaStyle: { color: "rgba(47,111,219,0.06)" },
  }];
  if (o.channel && s.channel) {
    series[0].markLine = {
      symbol: "none", silent: true,
      label: { formatter: "{b}", position: "insideEndTop", fontSize: 10, color: "#8b95a5" },
      lineStyle: { type: "dashed", width: 1 },
      data: [["p90", "P90", "#e3a5a0", true], ["p75", "P75", "#e9c3a0", false], ["p50", "中位数", "#b7c0cc", true],
        ["p25", "P25", "#a9c4e8", false], ["p10", "P10", "#8fb1e3", true]]
        .map(([k, n, c, label]) => ({
          name: n, yAxis: s.channel[k], lineStyle: { color: c },
          label: { show: label, position: k === "p10" ? "insideEndBottom" : "insideEndTop" },
        })),
    };
  }
  if (o.outliers && d.outliers.length) {
    series.push({ type: "scatter", name: "已剔除的坏点", data: d.outliers, symbol: "diamond", symbolSize: 8, itemStyle: { color: "#d64532" } });
  }
  return {
    animation: false,
    grid: { left: 64, right: 28, top: 20, bottom: 70 },
    tooltip: { trigger: "axis", valueFormatter: (v) => fmtNum(v) },
    xAxis: { type: "time", ...AXIS_STYLE, splitLine: { show: false } },
    yAxis: { type: "value", scale: true, ...AXIS_STYLE, axisLabel: { ...AXIS_STYLE.axisLabel, formatter: compact } },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 22, bottom: 18, borderColor: "#e3e7ec" }],
    series,
  };
}

function dataTable(points, unit) {
  const rows = points.slice(-60).reverse();
  return `<div class="table-wrap"><table class="tbl"><thead><tr><th>日期</th><th>数值（${esc(unit)}）</th><th>较前值</th></tr></thead><tbody>
    ${rows.map((p, i) => {
      const prev = rows[i + 1];
      const c = prev && prev[1] > 0 ? ((p[1] / prev[1]) - 1) * 100 : null;
      return `<tr><td>${p[0]}</td><td>${fmtNum(p[1])}</td><td>${chg(c)}</td></tr>`;
    }).join("")}</tbody></table></div><p class="muted small">显示最近 60 个数据点。</p>`;
}

/* ================= 股商对照 ================= */

async function renderCompare(token, a, b) {
  const pairs = state.meta.compare_pairs;
  if (!a || !b) {
    if (!pairs.length) { app.innerHTML = `<div class="empty">没有可对照的指标。</div>`; return; }
    location.replace(`#/compare/${pairs[0].commodity}/${pairs[0].equity}`);
    return;
  }
  const nameOf = (c) => state.meta.series.find((x) => x.code === c)?.name || c;
  const options = (sel) => Object.entries(state.meta.sectors).map(([k, n]) => `<optgroup label="${esc(n)}">
    ${state.meta.series.filter((x) => x.sector === k).map((x) => `<option value="${x.code}"${x.code === sel ? " selected" : ""}>${esc(x.name)}</option>`).join("")}
  </optgroup>`).join("");

  app.innerHTML = `
    <div class="crumb"><a href="#/">总览</a> › 股商对照</div>
    <section class="card">
      <div class="card-head"><h2>${rich("股商对照")}</h2><span class="muted">商品价格与板块股票指数是否同步</span></div>
      <div class="cmp-tools">
        <div class="chips">${pairs.map((p) => `<a class="chip${p.commodity === a && p.equity === b ? " on" : ""}" href="#/compare/${p.commodity}/${p.equity}">${esc(nameOf(p.commodity))} vs ${esc(nameOf(p.equity))}</a>`).join("")}</div>
        <div class="cmp-select">
          <span class="muted">自选：</span>
          <select id="selA">${options(a)}</select><span class="muted">vs</span><select id="selB">${options(b)}</select>
        </div>
      </div>
      <div id="cmpVerdict" class="cmp-verdict"><div class="loading">计算中…</div></div>
      <div class="card-head sub"><span></span>${rangeButtons("5")}</div>
      <div class="chart tall" id="cmpChart"></div>
      <p class="muted small">上图：两条走势（左轴 / 右轴），红色底色为背离区间——近 60 个交易日一涨一跌且涨跌幅相差 10 个百分点以上。
        下图：60 日滚动相关系数（基于日收益率），越接近 1 越同步，低于 0.2 视为基本脱钩。</p>
    </section>`;
  const go = () => { location.hash = `#/compare/${$("#selA").value}/${$("#selB").value}`; };
  $("#selA").onchange = go;
  $("#selB").onchange = go;

  const r = await api(`/api/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
  if (token !== state.token) return;
  $("#cmpVerdict").innerHTML = compareVerdict(r);
  if (!r.dates.length) return;
  const chart = makeChart($("#cmpChart"));
  chart.setOption(compareOption(r));
  const last = r.dates[r.dates.length - 1];
  zoomTo(chart, "5", last, [0, 1]);
  $$("[data-role=range] button").forEach((btn) => (btn.onclick = () => {
    $$("[data-role=range] button").forEach((x) => x.classList.toggle("on", x === btn));
    zoomTo(chart, btn.dataset.range, last, [0, 1]);
  }));
}

function corrWord(c) {
  if (c == null) return "样本不足";
  if (c >= 0.6) return "高度同步";
  if (c >= 0.3) return "中等相关";
  if (c >= 0) return "相关性弱，基本脱钩";
  return "负相关，走势相反";
}

function compareVerdict(r) {
  if (!r.dates.length || r.latest_corr == null) {
    return `<div class="empty">两个指标的重叠交易日太少，无法对照。</div>`;
  }
  const items = [];
  const diff = r.ret_b - r.ret_a;
  items.push(`<div class="kv"><small>近 ${r.horizon} 个交易日</small><b>${esc(r.name_a)} ${chg(r.ret_a)}</b><b>${esc(r.name_b)} ${chg(r.ret_b)}</b></div>`);
  items.push(`<div class="kv"><small>${r.window} 日相关系数</small><b>${r.latest_corr.toFixed(2)}</b><span>${corrWord(r.latest_corr)}</span></div>`);
  const valid = r.corr.filter((c) => c != null);
  const avg = valid.reduce((x, y) => x + y, 0) / valid.length;
  items.push(`<div class="kv"><small>历史平均相关</small><b>${avg.toFixed(2)}</b><span>${corrWord(avg)}</span></div>`);

  const lines = [];
  if (r.ret_a != null && r.ret_b != null) {
    if (Math.abs(diff) >= 10) {
      lines.push(`${r.name_b}${diff < 0 ? "跑输" : "跑赢"}${r.name_a} ${Math.abs(diff).toFixed(1)} 个百分点。` +
        (diff < 0 ? "商品涨幅没有传导到股价，可能是市场怀疑价格的持续性，或板块受到商品以外的影响。"
          : "股价走在商品前面，可能在提前反映预期好转，留意商品能否跟上。"));
    } else {
      lines.push("两者近期涨跌幅接近，没有明显背离。");
    }
  }
  if (r.latest_corr < avg - 0.25) lines.push(`当前相关性明显低于历史平均（${avg.toFixed(2)}），股价的驱动因素可能正在偏离商品。`);
  const spans = r.divergence;
  const last = r.dates[r.dates.length - 1];
  if (spans.length) {
    const lastSpan = spans[spans.length - 1];
    if (lastSpan[1] === last) lines.push(`当前正处于背离区间（自 ${lastSpan[0]} 起）。`);
    else lines.push(`最近一次背离：${lastSpan[0]} ~ ${lastSpan[1]}。`);
    const since = new Date(last);
    since.setFullYear(since.getFullYear() - 3);
    const recent = spans.filter((sp) => new Date(sp[1]) >= since).length;
    lines.push(`近 3 年共出现 ${recent} 段背离。`);
  } else {
    lines.push("历史上没有出现过持续的背离。");
  }
  return `<div class="kv-row">${items.join("")}</div><p class="cmp-text">${rich(lines.join(""))}</p>`;
}

function compareOption(r) {
  const A = r.dates.map((d, i) => [d, r.a[i]]);
  const B = r.dates.map((d, i) => [d, r.b[i]]);
  const C = r.dates.map((d, i) => [d, r.corr[i]]);
  return {
    animation: false,
    legend: { top: 0, data: [r.name_a, r.name_b], textStyle: { color: "#4a5361" } },
    tooltip: { trigger: "axis", axisPointer: { link: [{ xAxisIndex: "all" }] }, valueFormatter: (v) => (v == null ? "—" : fmtNum(v)) },
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    grid: [{ left: 64, right: 64, top: 36, height: "56%" }, { left: 64, right: 64, top: "74%", height: "14%" }],
    xAxis: [
      { type: "time", gridIndex: 0, ...AXIS_STYLE, splitLine: { show: false }, axisLabel: { show: false } },
      { type: "time", gridIndex: 1, ...AXIS_STYLE, splitLine: { show: false } },
    ],
    yAxis: [
      { type: "value", gridIndex: 0, scale: true, name: r.unit_a, ...AXIS_STYLE, axisLabel: { ...AXIS_STYLE.axisLabel, formatter: compact } },
      { type: "value", gridIndex: 0, scale: true, name: r.unit_b, position: "right", ...AXIS_STYLE, splitLine: { show: false }, axisLabel: { ...AXIS_STYLE.axisLabel, formatter: compact } },
      { type: "value", gridIndex: 1, min: -1, max: 1, interval: 1, name: "相关", ...AXIS_STYLE },
    ],
    dataZoom: [{ type: "inside", xAxisIndex: [0, 1] }, { type: "slider", xAxisIndex: [0, 1], height: 20, bottom: 6, borderColor: "#e3e7ec" }],
    series: [
      {
        type: "line", name: r.name_a, data: A, showSymbol: false, sampling: "lttb", lineStyle: { width: 1.5, color: "#d6773a" }, itemStyle: { color: "#d6773a" },
        markArea: { silent: true, itemStyle: { color: "rgba(214,69,50,0.09)" }, data: r.divergence.map(([s, e]) => [{ xAxis: s }, { xAxis: e }]) },
      },
      { type: "line", name: r.name_b, data: B, yAxisIndex: 1, showSymbol: false, sampling: "lttb", lineStyle: { width: 1.5, color: "#2f6fdb" }, itemStyle: { color: "#2f6fdb" } },
      {
        type: "line", name: "滚动相关", data: C, xAxisIndex: 1, yAxisIndex: 2, showSymbol: false, lineStyle: { width: 1, color: "#6b7482" },
        areaStyle: { color: "rgba(107,116,130,0.12)", origin: 0 },
        markLine: { symbol: "none", silent: true, label: { formatter: "{b}", fontSize: 10, color: "#8b95a5" }, lineStyle: { type: "dashed", color: "#c9a0a0" }, data: [{ name: "0.2", yAxis: 0.2 }] },
      },
    ],
  };
}

/* ================= 数据健康 ================= */

async function renderHealth(token) {
  const h = await api("/api/health");
  if (token !== state.token) return;
  const st = state.status || {};
  const secName = (k) => state.meta.sectors[k] || k;
  const rows = h.rows.map((r) => `
    <tr class="${r.status}">
      <td><a href="#/sector/${r.sector}/${r.code}">${esc(r.name)}</a>${r.note ? `<div class="muted small">${esc(r.note)}</div>` : ""}</td>
      <td>${esc(secName(r.sector))}</td>
      <td>${ROLE[r.role] || r.role}</td>
      <td>${esc(SOURCE[r.source] || r.source)}</td>
      <td>${r.freq === "W" ? "周" : "日"}</td>
      <td>${r.first_date || "—"}</td>
      <td>${r.latest_date || "—"}</td>
      <td class="num">${r.lag_days ?? "—"}</td>
      <td class="num">${r.points?.toLocaleString() ?? "—"}</td>
      <td>${r.issues.length ? r.issues.map((x) => `<span class="badge ${r.status === "missing" ? "red" : x.startsWith("剔除") ? "gray" : "amber"}"
          ${x.startsWith("剔除") ? `title="${esc(r.outliers.slice(0, 30).join("、"))}${r.outliers.length > 30 ? " …" : ""}"` : ""}>${esc(x)}</span>`).join(" ")
        : `<span class="badge ok">正常</span>`}</td>
    </tr>`).join("");

  app.innerHTML = `
    <div class="crumb"><a href="#/">总览</a> › 数据健康</div>
    <section class="stat-row">
      <div class="card stat"><small>正常更新</small><b>${h.fresh} / ${h.total}</b><span class="muted">不含历史档案</span></div>
      <div class="card stat"><small>上次刷新</small><b>${esc(st.last_refresh || "—")}</b><span class="muted">每天首次启动时自动刷新</span></div>
      <div class="card stat"><small>上次刷新失败</small><b>${h.failed.length}</b><span class="muted">${esc(h.failed.slice(0, 2).join("；")) || "无"}</span></div>
    </section>
    <section class="card">
      <div class="card-head"><h2>全部指标</h2>
        <div class="chart-tools"><span class="muted">点击名称查看走势</span>
          <div class="seg-btns" id="healthFilter"><button data-f="all" class="on">全部</button><button data-f="issue">只看有问题的</button></div>
        </div>
      </div>
      <div class="table-wrap"><table class="tbl health">
        <thead><tr><th>指标</th><th>板块</th><th>用途</th><th>数据源</th><th>频率</th><th>起始</th><th>最新</th><th>滞后天数</th><th>数据点</th><th>状态</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
    </section>
    <section class="card method-body">
      <h2>数据质量规则</h2>
      <p><b>过期</b>：日度数据超过 10 天、周度数据超过 21 天没有新数据，视为过期，不参与温度、阶段和多数信号（个别库存信号会注明数据日期）。</p>
      <p><b>坏点</b>：相对上一个有效值偏离 40% 以上、且随后 3 个数据点内又回到原水平 10% 以内的点，判定为数据源的偶发错误（如 LME 铅、锌库存在 2015–2017 年多次串列）。分析时剔除，数据库保留原值。运价指数波动天然剧烈，不做剔除。</p>
      <p><b>历史长度</b>：历史不足 3 年的价格只参与动量，不参与温度；不足 10 年的分位按实际年限计算并标注。</p>
      <p><b>手动补录</b>：没有免费接口的指标（如 SCFI）可以写入 <code>data/manual.csv</code>（列：code,date,value），下次刷新时导入。</p>
    </section>`;
  $$("#healthFilter button").forEach((btn) => (btn.onclick = () => {
    $$("#healthFilter button").forEach((x) => x.classList.toggle("on", x === btn));
    $$(".tbl.health tbody tr").forEach((tr) => (tr.hidden = btn.dataset.f === "issue" && tr.classList.contains("ok")));
  }));
}

/* ================= 术语与报告 ================= */

async function renderGlossary(token) {
  if (token !== state.token) return;
  const card = (g) => `<div class="card gl" data-text="${esc([g.term, g.en, g.plain, ...(g.keys || [])].join(" ").toLowerCase())}">
    <h3>${esc(g.term)}<small>${esc(g.en || "")}</small></h3>
    <p>${esc(g.plain)}</p>
    <p><b>为什么重要：</b>${esc(g.why)}</p>
    <p class="muted"><b>在哪看：</b>${esc(g.where)}</p>
  </div>`;
  app.innerHTML = `
    <div class="crumb"><a href="#/">总览</a> › 术语百科</div>
    <div class="gl-search"><input id="glq" placeholder="搜索术语，如 分位、库存、BDI…" autocomplete="off"></div>
    <section class="gl-grid">${state.glossary.map(card).join("")}</section>
    <p class="muted small">正文中带虚线下划线的词，鼠标悬停即可查看解释。</p>`;
  $("#glq").addEventListener("input", (e) => {
    const q = e.target.value.trim().toLowerCase();
    $$(".gl").forEach((el) => (el.hidden = q && !el.dataset.text.includes(q)));
  });
}

async function renderReports(token) {
  const list = await api("/api/reports");
  if (token !== state.token) return;
  app.innerHTML = `
    <div class="crumb"><a href="#/">总览</a> › 研判报告</div>
    <section class="card">
      <div class="card-head"><h2>研判报告</h2><span class="muted">放在 reports/ 目录下的 HTML 报告，最新的在前</span></div>
      ${list.length ? `<ul class="report-list">${list.map((n) => `<li><a href="/reports/${encodeURIComponent(n)}" target="_blank" rel="noopener">${esc(n.replace(/\.html$/, ""))}</a></li>`).join("")}</ul>`
        : `<div class="empty">还没有报告。</div>`}
    </section>`;
}

/* ================= 新手指引 ================= */

const GUIDE_KEY = "cycle_guide_v2";

function guideSteps() {
  return [
    {
      title: "欢迎使用周期行业观测台",
      body: `<p>它回答一个问题：<b>有色金属、能源、航运这三个周期板块，现在处在周期的哪个位置，接下来该关注什么？</b></p>
        <p>建议的使用顺序：先看<b>总览</b>的今日结论和三张板块卡片，再点进感兴趣的板块看依据，最后用<b>股商对照</b>检查股票是否认可商品的走势。</p>`,
    },
    {
      title: "周期温度：现在贵不贵",
      body: `<p>把板块核心商品价格放进近 10 年的历史里排队，取平均位置，换算成 0–100。</p>
        ${tempBar(82, 70)}
        <p>上面的例子表示温度 82（处于历史偏高位置），浅色小刻度表示一个月前是 70。<b>80 以上算高位，25 以下算低位。</b></p>`,
    },
    {
      title: "周期阶段：往哪个方向走",
      body: `<div class="guide-wheel">${cycleWheel([], 240)}</div>
        <p>同样是高价，还在上涨（高位强势）和已经回落（高位回落）完全不同。阶段 = 位置 × 近 3 个月方向，每个阶段都附带一条<b>决策提示</b>。</p>`,
    },
    {
      title: "信号与数据可信度",
      body: `<p>信号分四级：<span class="lvtag lv-risk">风险</span> <span class="lvtag lv-watch">留意</span> <span class="lvtag lv-positive">积极</span> <span class="lvtag lv-info">提示</span>，点击可定位到相关指标或对照图。</p>
        <p>过期数据和停更档案只展示、不参与结论；数据源的偶发坏点会自动剔除。右上角显示数据日期和正常更新的指标数，点击可查看详情。</p>
        <p>每天第一次启动会自动更新数据，也可以随时点「刷新数据」。带虚线的词悬停可以看解释。</p>`,
    },
  ];
}

function openGuide(step = 0) {
  const steps = guideSteps();
  const s = steps[step];
  const modal = $("#modal");
  modal.innerHTML = `<div class="modal-box">
    <div class="modal-step">${step + 1} / ${steps.length}</div>
    <h2>${s.title}</h2>
    <div class="modal-body">${s.body}</div>
    <div class="modal-foot">
      <button class="btn ghost" data-act="skip">${step === steps.length - 1 ? "关闭" : "跳过"}</button>
      <span>
        ${step > 0 ? `<button class="btn" data-act="prev">上一步</button>` : ""}
        <button class="btn primary" data-act="next">${step === steps.length - 1 ? "开始使用" : "下一步"}</button>
      </span>
    </div>
  </div>`;
  modal.hidden = false;
  modal.onclick = (e) => {
    const act = e.target.dataset?.act;
    if (e.target === modal || act === "skip" || (act === "next" && step === steps.length - 1)) closeGuide();
    else if (act === "next") openGuide(step + 1);
    else if (act === "prev") openGuide(step - 1);
  };
}

function closeGuide() {
  $("#modal").hidden = true;
  localStorage.setItem(GUIDE_KEY, "1");
}

document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#modal").hidden) closeGuide(); });

/* ================= 路由与启动 ================= */

function renderNav(page, key) {
  const links = [["", "总览"], ...Object.entries(state.meta.sectors).map(([k, n]) => [`sector/${k}`, n]),
    ["compare", "股商对照"], ["health", "数据健康"], ["glossary", "术语"], ["reports", "报告"]];
  const cur = page === "sector" ? `sector/${key}` : page || "";
  $("#nav").innerHTML = links.map(([h, t]) => `<a href="#/${h}" class="${h === cur ? "on" : ""}">${t}</a>`).join("");
}

async function render() {
  if (state.initMode) { renderInit(); return; }
  const token = ++state.token;
  disposeCharts();
  const [page, a, b] = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  renderNav(page, a);
  app.innerHTML = `<div class="loading">加载中…</div>`;
  window.scrollTo(0, 0);
  try {
    if (!page) await renderOverview(token);
    else if (page === "sector") await renderSector(token, a, b);
    else if (page === "compare") await renderCompare(token, a, b);
    else if (page === "health") await renderHealth(token);
    else if (page === "glossary") await renderGlossary(token);
    else if (page === "reports") await renderReports(token);
    else location.replace("#/");
  } catch (e) {
    if (token !== state.token) return;
    if (e.status === 503) {
      state.initMode = true;
      await refreshStatus().catch(() => null);
      renderInit();
      if (state.status?.updating) startPolling();
      return;
    }
    app.innerHTML = `<div class="card error"><h2>加载失败</h2><p>${esc(e.message)}</p>
      <p class="muted">请确认服务正在运行（双击 scripts/start_server.bat），然后刷新页面。</p></div>`;
  }
}

async function boot() {
  setupTooltip();
  $("#btnRefresh").onclick = manualRefresh;
  $("#btnGuide").onclick = () => openGuide(0);
  try {
    const [meta, glossary] = await Promise.all([api("/api/meta"), api("/api/glossary")]);
    state.meta = meta;
    state.glossary = glossary;
    buildTerms();
    await refreshStatus();
  } catch (e) {
    app.innerHTML = `<div class="card error"><h2>无法连接服务</h2><p>${esc(e.message)}</p>
      <p class="muted">请双击 scripts/start_server.bat 启动服务，并通过 http://127.0.0.1:8321 打开页面（不要直接双击 index.html）。</p></div>`;
    $("#statusPill").textContent = "未连接";
    return;
  }
  window.addEventListener("hashchange", render);
  if (state.status.empty) {
    state.initMode = true;
    renderInit();
  } else {
    await render();
  }
  if (state.status.updating) startPolling();
  if (!localStorage.getItem(GUIDE_KEY)) openGuide(0);
}

boot();

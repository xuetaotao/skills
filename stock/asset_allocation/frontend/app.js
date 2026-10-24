"use strict";

/* ================= 基础工具 ================= */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const app = $("#app");

const state = {
  meta: null, glossary: [], termRe: null, termIndex: {},
  status: null, polling: null, charts: [], token: 0, initMode: false,
  lab: null, labW: null, labSrc: null, labPeriod: "all", labBench: "csi300", labLog: true,
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

/** 小数 → 百分比文本；sign=true 时正数带 + 号 */
function pct(v, d = 1, sign = true) {
  if (v == null || !isFinite(v)) return "—";
  const s = (v * 100).toFixed(d);
  if (Number(s) === 0) return `${(0).toFixed(d)}%`;
  return `${sign && v > 0 ? "+" : ""}${s}%`;
}
const pctPlain = (v, d = 1) => pct(v, d, false);
const colored = (v, d = 1) => (v == null ? `<span class="muted">—</span>`
  : `<span class="${v > 0 ? "up" : v < 0 ? "down" : ""}">${pct(v, d)}</span>`);
const shortDate = (d) => (d ? d.slice(5) : "—");
const money = (v) => (v == null || !isFinite(v) ? "—" : Math.round(v).toLocaleString("zh-CN"));
const fix = (v, d = 2) => (v == null || !isFinite(v) ? "—" : Number(v).toFixed(d));

/** 收益热力色块：红涨绿跌，scale 为颜色饱和时的收益幅度 */
function heat(v, scale = 0.3, d = 1) {
  if (v == null) return `<span class="heat muted">—</span>`;
  const a = (Math.min(Math.abs(v) / scale, 1) * 0.5).toFixed(2);
  const bg = v >= 0 ? `rgba(217,54,62,${a})` : `rgba(24,147,90,${a})`;
  return `<span class="heat" style="background:${bg}">${pct(v, d)}</span>`;
}

const COLORS = {
  CSI300: "#d64532", CSI500: "#e0862f", CSI1000: "#f2b63c", CSIDIV: "#a3402a", CHINEXT: "#c27ba0", STAR50: "#9c6ade",
  CSIA500: "#b8322a", STARGEM50: "#6f4fb8",
  CNBOND: "#3f9f8f", SPX: "#2f6fdb", NDX: "#69a1f5", N225: "#7b5ea7", FTSE: "#1f8fb8", DAX: "#4a5361",
  HSI: "#b0703c", TWII: "#16a085", KOSPI: "#7e9b32", GOLD: "#e0b23f",
};
const colorOf = (c) => COLORS[c] || "#8b95a5";
const assetOf = (c) => state.meta.assets.find((a) => a.code === c) || { code: c, name: c };
const nameOf = (c) => assetOf(c).name;
const assetName = (c) => `<span class="asset-name"><i style="background:${colorOf(c)}"></i>${esc(nameOf(c))}</span>`;
const GROUP_ORDER = ["A股", "债券", "海外股票", "商品"];
const basisBadge = (b) => `<span class="badge ${/估算|不含/.test(b || "") ? "amber" : "gray"}" title="${esc(b)}">${esc((b || "—").split("（")[0])}</span>`;
const LEVEL = { risk: "风险", watch: "留意", positive: "积极", info: "提示" };

function toast(text, kind = "ok", ms = 4000) {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = text;
  $("#toasts").appendChild(el);
  setTimeout(() => el.classList.add("out"), ms);
  setTimeout(() => el.remove(), ms + 400);
}

/* ================= 本地存储（目标组合与持仓只存在本浏览器） ================= */

const TARGET_KEY = "aa_target_v1";
const HOLD_KEY = "aa_holdings_v1";
const GUIDE_KEY = "aa_guide_v1";

const store = {
  get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
  set(k, v) { localStorage.setItem(k, JSON.stringify(v)); },
};

/** 可选的目标组合：我的目标（若已保存）+ 预设 */
function targetOptions() {
  const out = [];
  const mine = store.get(TARGET_KEY, null);
  if (mine?.weights) out.push({ key: "mine", name: "我的目标组合", weights: mine.weights, mine: true });
  (state.lab?.presets || []).forEach((p) => out.push({ key: p.key, name: p.name, weights: p.weights }));
  return out;
}

function currentTarget(key) {
  const opts = targetOptions();
  return opts.find((o) => o.key === key) || opts.find((o) => o.mine)
    || opts.find((o) => o.key === state.lab?.default_target) || opts[0];
}

/* ================= 术语悬停解释 ================= */

function buildTerms() {
  const keys = [];
  state.glossary.forEach((g, i) => (g.keys || [g.term]).forEach((k) => {
    keys.push(k);
    state.termIndex[k] = i;
  }));
  state.glossary.forEach((g, i) => { state.termIndex[g.term] ??= i; });
  keys.sort((a, b) => b.length - a.length);
  const pat = keys.map((k) => esc(k).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  state.termRe = pat ? new RegExp(pat, "g") : null;
}

/** 转义文本，并给每个术语的第一次出现加上悬停解释 */
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

/** 表头等短标签：整段作为术语 */
const termLabel = (label, key = label) => (state.termIndex[key] == null ? esc(label)
  : `<span class="term" data-term="${state.termIndex[key]}">${esc(label)}</span>`);

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
    const left = Math.min(Math.max(8, r.left), window.innerWidth - w - 8);
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
    if (s.updating || !state.polling) return;  // 刷新刚结束时状态接口要重算分析，可能有两个请求同时在途
    clearInterval(state.polling);
    state.polling = null;
    if (s.empty) { renderInit(); return; }
    if (s.last_error) toast(`刷新完成，但有问题：${s.last_error}`, "warn", 8000);
    else toast("数据已更新到最新", "ok");
    state.initMode = false;
    state.lab = null;
    render();
  }, 1500);
}

async function manualRefresh() {
  try {
    const r = await api("/api/refresh", { method: "POST" });
    toast(r.started ? "开始刷新，大约需要 1–3 分钟，可以继续浏览" : "已经在刷新中", "info");
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
  const pct0 = s.total ? Math.round((s.done / s.total) * 100) : 0;
  app.innerHTML = `
    <section class="init">
      <h1>正在初始化数据</h1>
      <p>首次运行需要下载全球 18 类资产近 20 年的历史数据，大约 3–5 分钟（中国银行汇率接口较慢）。完成后页面会自动刷新。</p>
      <div class="init-bar"><i style="width:${pct0}%"></i></div>
      <p class="muted">${s.done || 0} / ${s.total || "…"} ${s.current_name ? `· 正在获取：${esc(s.current_name)}` : ""}</p>
      ${s.last_error ? `<p class="warn-text">${esc(s.last_error)}</p>` : ""}
    </section>`;
}

/* ================= 图表 ================= */

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

/** 月度标签 YYYY-MM → 时间轴可用的日期 */
const mdate = (m) => (m.length === 7 ? `${m}-01` : m);
const fmtMonth = (t) => echarts.format.formatTime("yyyy-MM", t);
const fmtDay = (t) => echarts.format.formatTime("yyyy-MM-dd", t);

function zoomTo(chart, range, lastDate) {
  if (range === "all") {
    chart.dispatchAction({ type: "dataZoom", start: 0, end: 100 });
    return;
  }
  const end = new Date(lastDate);
  const start = new Date(end);
  start.setFullYear(end.getFullYear() - Number(range));
  chart.dispatchAction({ type: "dataZoom", startValue: start.getTime(), endValue: end.getTime() });
}

const segButtons = (role, items, active) => `<div class="seg-btns" data-role="${role}">
  ${items.map(([v, t]) => `<button data-v="${v}" class="${String(v) === String(active) ? "on" : ""}">${t}</button>`).join("")}</div>`;

function onSeg(root, role, fn) {
  const box = $(`.seg-btns[data-role="${role}"]`, root);
  if (!box) return;
  box.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    $$("button", box).forEach((x) => x.classList.toggle("on", x === b));
    fn(b.dataset.v);
  });
}

/* ================= 通用组件 ================= */

/** 可排序表格。排序循环：降序 → 升序 → 恢复默认（按分组） */
function sortableTable(el, cols, rows, opt = {}) {
  let sort = null;
  const cmp = (a, b) => (a == null ? 1 : b == null ? -1 : a < b ? -1 : a > b ? 1 : 0);
  const draw = () => {
    let list = rows.slice();
    if (sort) {
      const c = cols.find((x) => x.key === sort.key);
      list.sort((a, b) => {
        const va = c.val(a), vb = c.val(b);
        if (va == null || vb == null) return cmp(va, vb);
        return cmp(va, vb) * sort.dir;
      });
    }
    const head = cols.map((c) => {
      const on = sort && sort.key === c.key;
      return `<th class="${c.num ? "num" : ""}${c.val ? " sortable" : ""}${on ? " sorted" : ""}" data-k="${c.key}"
        ${c.title ? `title="${esc(c.title)}"` : ""}>${c.label}${on ? (sort.dir > 0 ? " ↑" : " ↓") : ""}</th>`;
    }).join("");
    let body = "", lastG = null;
    for (const r of list) {
      if (opt.group && !sort) {
        const g = opt.group(r);
        if (g !== lastG) { body += `<tr class="group"><td colspan="${cols.length}">${esc(g)}</td></tr>`; lastG = g; }
      }
      body += `<tr class="${opt.rowClass?.(r) || ""}${opt.onRow ? " link" : ""}" data-code="${esc(r.code || "")}">
        ${cols.map((c) => `<td class="${c.num ? "num" : ""}${c.cls ? ` ${c.cls}` : ""}">${c.fmt(r)}</td>`).join("")}</tr>`;
    }
    el.innerHTML = `<div class="table-wrap"><table class="tbl ${opt.tblClass || ""}"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
    $$("th.sortable", el).forEach((th) => th.onclick = () => {
      const k = th.dataset.k;
      sort = sort && sort.key === k ? (sort.dir < 0 ? { key: k, dir: 1 } : null) : { key: k, dir: -1 };
      draw();
    });
    if (opt.onRow) $$("tbody tr[data-code]", el).forEach((tr) => tr.onclick = (e) => {
      if (!e.target.closest(".term") && tr.dataset.code) opt.onRow(tr.dataset.code);
    });
  };
  draw();
}

const groupSort = (a, b) => GROUP_ORDER.indexOf(a.group) - GROUP_ORDER.indexOf(b.group);

function signalList(list, empty = "暂无需要特别关注的信号。") {
  if (!list.length) return `<div class="empty">${empty}</div>`;
  return `<div class="signals">${list.map((s) => `<a class="signal lv-${s.level}" href="${s.link || "#/"}">
    <span class="lv">${LEVEL[s.level]}</span>
    <div class="sig-body"><div class="sig-title">${esc(s.title)}</div><div class="sig-text">${rich(s.text)}</div></div>
    <span class="sig-go">›</span></a>`).join("")}</div>`;
}

/** 估值“便宜程度”条：左高估、右低估 */
function valueBar(cheap) {
  if (cheap == null) return `<div class="muted small">数据不足</div>`;
  return `<div class="vbar"><div class="vbar-track"><span class="vbar-mark" style="left:${(cheap * 100).toFixed(1)}%"></span></div>
    <div class="vbar-scale"><span style="left:0">高估</span><span style="left:25%">偏高</span><span style="left:50%">适中</span>
    <span style="left:75%">偏低</span><span style="left:100%">低估</span></div></div>`;
}

function pctBar(q, inverse) {
  if (q == null) return `<span class="muted">—</span>`;
  return `<span class="pbar"><span class="pbar-track${inverse ? " inv" : ""}"><i style="left:${(q * 100).toFixed(0)}%"></i></span>${Math.round(q * 100)}%</span>`;
}

/** 权重条 + 图例 */
function weightBar(weights, withLegend = true) {
  const list = Object.entries(weights).filter(([, w]) => w > 0.0005).sort((a, b) => b[1] - a[1]);
  const total = list.reduce((s, [, w]) => s + w, 0) || 1;
  return `<div class="wbar">${list.map(([c, w]) => `<i style="width:${(w / total) * 100}%;background:${colorOf(c)}" title="${esc(nameOf(c))} ${pctPlain(w / total, 0)}"></i>`).join("")}</div>
    ${withLegend ? `<div class="wlegend">${list.map(([c, w]) => `<span><i style="background:${colorOf(c)}"></i>${esc(nameOf(c))} ${pctPlain(w / total, 0)}</span>`).join("")}</div>` : ""}`;
}

/* ================= 组合计算（与后端 perf() 口径一致） ================= */

async function loadLab() {
  if (!state.lab) state.lab = await api("/api/lab");
  return state.lab;
}

function normW(w) {
  const s = Object.values(w).reduce((a, x) => a + (x > 0 ? x : 0), 0);
  const out = {};
  if (s > 0) for (const [c, x] of Object.entries(w)) if (x > 0) out[c] = x / s;
  return out;
}

/** 固定权重、每月再平衡的回测。fromLabel：基期月份（净值 = 1），之后逐月累乘 */
function backtest(weights, fromLabel) {
  const lab = state.lab;
  const w = normW(weights);
  const codes = Object.keys(w).filter((c) => lab.returns[c]);
  if (!codes.length) return null;
  let i0 = 0;
  if (fromLabel) while (i0 < lab.dates.length && lab.dates[i0] <= fromLabel) i0++;
  const late = codes.filter((c) => lab.returns[c][i0] == null);
  while (i0 < lab.dates.length && codes.some((c) => lab.returns[c][i0] == null)) i0++;
  const base = i0 > 0 ? lab.dates[i0 - 1] : lab.start;
  const curve = [[base, 1]];
  const rets = [];
  let v = 1;
  for (let i = i0; i < lab.dates.length; i++) {
    let r = 0;
    for (const c of codes) r += w[c] * (lab.returns[c][i] ?? 0);
    v *= 1 + r;
    rets.push(r);
    curve.push([lab.dates[i], v]);
  }
  return { curve, rets, i0, weights: w, late };
}

/** 回测起点被历史较短的资产推迟时的说明 */
function lateNote(bt) {
  if (!bt?.late?.length) return "";
  const lab = state.lab;
  const names = bt.late.map((c) => `${nameOf(c)}（${lab.since[c]} 起）`).join("、");
  return `回测从 ${bt.curve[0][0]} 开始：${names}的历史较短，区间按所选资产都有数据的月份截取。想看更长的历史，可以先把它们的权重设为 0。`;
}

function perfOf(curve, rf = state.lab?.rf ?? 0.02) {
  const v = curve.map((p) => p[1]);
  const n = v.length - 1;
  if (n < 12) return null;
  const r = [];
  for (let i = 1; i <= n; i++) r.push(v[i] / v[i - 1] - 1);
  const yrs = n / 12;
  const cagr = (v[n] / v[0]) ** (1 / yrs) - 1;
  const mean = r.reduce((a, x) => a + x, 0) / n;
  const vol = Math.sqrt(r.reduce((a, x) => a + (x - mean) ** 2, 0) / (n - 1)) * Math.sqrt(12);
  let peak = v[0], mdd = 0;
  const dd = v.map((x) => { peak = Math.max(peak, x); const d = x / peak - 1; mdd = Math.min(mdd, d); return d; });
  let worst12 = null, best12 = null, wins = 0, cnt = 0;
  for (let i = 12; i <= n; i++) {
    const x = v[i] / v[i - 12] - 1;
    worst12 = worst12 == null ? x : Math.min(worst12, x);
    best12 = best12 == null ? x : Math.max(best12, x);
  }
  for (let i = 60; i <= n; i++) { cnt++; if (v[i] > v[i - 60]) wins++; }
  const sub = (k) => (v.length > k ? (v[n] / v[n - k]) ** (12 / k) - 1 : null);
  return {
    cagr, vol, sharpe: vol > 0 ? (cagr - rf) / vol : null, mdd, calmar: mdd < 0 ? cagr / -mdd : null,
    worst12, best12, cagr10: sub(120), cagr5: sub(60), win5: cnt ? wins / cnt : null, cur_dd: dd[n], dd,
    years: yrs, start: curve[0][0], end: curve[n][0],
  };
}

function riskContrib(weights, i0) {
  const lab = state.lab;
  const w = normW(weights);
  const codes = Object.keys(w);
  const n = lab.dates.length - i0;
  if (n < 13) return {};
  const mean = {};
  codes.forEach((c) => { let s = 0; for (let i = i0; i < lab.dates.length; i++) s += lab.returns[c][i] ?? 0; mean[c] = s / n; });
  const cov = (a, b) => {
    let s = 0;
    for (let i = i0; i < lab.dates.length; i++) s += ((lab.returns[a][i] ?? 0) - mean[a]) * ((lab.returns[b][i] ?? 0) - mean[b]);
    return s / (n - 1);
  };
  const sw = {};
  codes.forEach((a) => { sw[a] = codes.reduce((s, b) => s + cov(a, b) * w[b], 0); });
  const total = codes.reduce((s, a) => s + w[a] * sw[a], 0);
  const out = {};
  codes.forEach((a) => { out[a] = total > 0 ? (w[a] * sw[a]) / total : 0; });
  return out;
}

/** 日历年收益；第一年若不完整，标记 partial */
function yearlyOf(curve) {
  const last = new Map();
  curve.forEach(([m, v]) => last.set(+m.slice(0, 4), v));
  const years = [...last.keys()];
  const out = [];
  const baseYear = +curve[0][0].slice(0, 4), baseMonth = +curve[0][0].slice(5, 7);
  for (let k = 0; k < years.length; k++) {
    const y = years[k];
    if (k === 0) {
      if (y === baseYear && curve.length > 1 && +curve[1][0].slice(0, 4) === y) {
        out.push({ year: y, ret: last.get(y) / curve[0][1] - 1, partial: baseMonth !== 12 });
      }
      continue;
    }
    const lastLabel = curve.filter(([m]) => +m.slice(0, 4) === y).pop()[0];
    out.push({ year: y, ret: last.get(y) / last.get(years[k - 1]) - 1, partial: lastLabel.slice(5, 7) !== "12" });
  }
  return out;
}

function ytdOf(curve) {
  const lastYear = +curve[curve.length - 1][0].slice(0, 4);
  const prev = curve.filter(([m]) => +m.slice(0, 4) < lastYear).pop();
  return prev ? curve[curve.length - 1][1] / prev[1] - 1 : null;
}

/** 持仓偏离与操作建议 */
function rebalancePlan(amounts, target, threshold, newCash) {
  const codes = state.lab.codes;
  const total = codes.reduce((s, c) => s + (amounts[c] || 0), 0);
  const tw = normW(target);
  const after = total + (newCash || 0);
  const rows = codes.map((c) => {
    const cur = amounts[c] || 0;
    const cw = total > 0 ? cur / total : 0;
    const t = tw[c] || 0;
    return { code: c, amount: cur, cw, tw: t, dev: cw - t, trade: t * total - cur };
  });
  // 新增资金：先补足各资产到目标金额的缺口（按缺口比例），有剩余再按目标权重分配
  const gaps = rows.map((r) => Math.max(0, r.tw * after - r.amount));
  const gapSum = gaps.reduce((s, x) => s + x, 0);
  rows.forEach((r, i) => {
    if (!newCash) { r.add = 0; return; }
    r.add = gapSum >= newCash ? (gapSum > 0 ? (gaps[i] / gapSum) * newCash : 0) : gaps[i] + (newCash - gapSum) * r.tw;
    r.devAfterAdd = after > 0 ? (r.amount + r.add) / after - r.tw : 0;
  });
  const th = threshold / 100;
  const over = rows.filter((r) => Math.abs(r.dev) > th);
  const maxDev = rows.reduce((m, r) => (Math.abs(r.dev) > Math.abs(m) ? r.dev : m), 0);
  const fixedByCash = newCash > 0 && rows.every((r) => Math.abs(r.devAfterAdd) <= th);
  return { rows, total, over, maxDev, fixedByCash, after };
}

/* ================= 总览 ================= */

async function renderOverview(token) {
  const [ov] = await Promise.all([api("/api/overview"), loadLab()]);
  if (token !== state.token) return;
  const v = ov.verdict;
  const target = currentTarget(store.get(HOLD_KEY, {}).target);
  const bt = target && backtest(target.weights);
  const tp = bt && perfOf(bt.curve);
  const hold = store.get(HOLD_KEY, null);
  const hasHold = hold && Object.values(hold.amounts || {}).some((x) => x > 0);
  const plan = hasHold ? rebalancePlan(hold.amounts, target.weights, hold.threshold ?? 5, 0) : null;

  app.innerHTML = `
    <section class="card hero">
      <div>
        <div class="eyebrow">今日结论 · ${esc(ov.today)}</div>
        <h1>${rich(ov.headline)}</h1>
      </div>
      <a class="gauge-box" href="#/valuation">
        ${v ? `<div class="gauge-title"><span>A 股估值（沪深300）</span><b class="tone-${v.tone}">${esc(v.label)}</b></div>
          ${valueBar(v.cheapness)}
          <div class="gauge-sub">滚动市盈率 ${fix(v.pe)}（近 10 年第 ${Math.round(v.pe_pct * 100)}% 分位）·
            股债利差 ${v.ebs != null ? pctPlain(v.ebs, 2) : "—"}（第 ${v.ebs_pct != null ? Math.round(v.ebs_pct * 100) : "—"}% 分位）</div>`
          : `<div class="muted">估值数据不足</div>`}
      </a>
    </section>

    <section class="dash">
      <div class="card dash-card">
        <div class="card-head" style="margin:0"><h2>${esc(target?.name || "目标组合")}</h2>
          <span class="muted small">${target?.mine ? "在组合实验室保存" : "示例组合，可在组合实验室调整"}</span></div>
        ${target ? weightBar(target.weights) : ""}
        ${tp ? `<div class="kv-row">
          <div class="kv"><small>${termLabel("年化收益")}</small><b>${pctPlain(tp.cagr)}</b><span>${esc(tp.start)} 起</span></div>
          <div class="kv"><small>${termLabel("最大回撤")}</small><b class="down">${pct(tp.mdd)}</b><span>当前 ${pct(tp.cur_dd)}</span></div>
          <div class="kv"><small>今年以来</small><b>${colored(ytdOf(bt.curve))}</b><span>人民币计价</span></div>
          <div class="kv"><small>${termLabel("最差 12 个月")}</small><b>${pct(tp.worst12)}</b><span>历史最难熬的一年</span></div>
        </div>` : ""}
        <div class="cta"><a class="btn" href="#/lab">在组合实验室调整</a></div>
      </div>
      <div class="card dash-card">
        <div class="card-head" style="margin:0"><h2>我的持仓</h2><span class="muted small">只保存在本浏览器</span></div>
        ${plan ? `
          <div class="kv-row">
            <div class="kv"><small>持仓总额（元）</small><b>${money(plan.total)}</b><span>对照：${esc(target.name)}</span></div>
            <div class="kv"><small>最大偏离（百分点）</small><b class="${plan.over.length ? "warn-text" : ""}">${plan.maxDev > 0 ? "+" : ""}${(plan.maxDev * 100).toFixed(1)}</b>
              <span>阈值 ±${hold.threshold ?? 5}</span></div>
          </div>
          <div class="hint">${plan.over.length
            ? `<b>建议${termLabel("再平衡")}：</b>${plan.over.map((r) => `${esc(nameOf(r.code))}${r.dev > 0 ? "超配" : "低配"} ${Math.abs(r.dev * 100).toFixed(1)} 个百分点`).join("，")}。`
            : `<b>无需操作：</b>各资产偏离都在阈值以内，继续持有即可。`}</div>
          <div class="cta"><a class="btn" href="#/holdings">查看买卖金额</a></div>`
          : `<p class="muted">录入各类资产的持有金额后，这里会显示当前配置与目标的偏离，以及需要买卖多少才能回到目标。</p>
          <div class="cta"><a class="btn primary" href="#/holdings">录入我的持仓</a></div>`}
      </div>
    </section>

    <section class="card">
      <div class="card-head"><h2>近期表现（人民币计价）</h2>
        <span class="muted small">点击表头排序，点击行查看资产详情 · <a href="#/assets">长期风险收益对比 ›</a></span></div>
      <div id="recentTable"></div>
    </section>

    <section class="card">
      <div class="card-head"><h2>信号</h2><span class="muted small">按重要程度排序，点击查看依据</span></div>
      ${signalList(ov.signals)}
    </section>

    <details class="card method">
      <summary>这些结论是怎么得出的？</summary>
      <div class="method-body"><ul>
        <li>${rich("所有收益都是人民币计价：海外资产按中国银行折算价（新台币、韩元用美元交叉汇率）换算。")}</li>
        <li>${rich("收益口径尽量使用总收益：A 股、标普500、DAX、债券用全收益指数（科创50、科创创业50 没有全收益指数，用价格指数），纳指100 用 QQQ 复权价，日经、富时、恒生、台湾、韩国用价格指数加 ETF 股息估算。")}</li>
        <li>${rich("创业板指、科创50、科创创业50 历史较短：组合回测从所选资产都有数据的月份开始，滚动优化在它们攒够 60 个月数据后才纳入候选。")}</li>
        <li>${rich("A 股估值结论综合沪深300 滚动市盈率在近 10 年的分位（越低越便宜）和股债利差分位（越高越便宜）。")}</li>
        <li>${rich("组合回测按月再平衡，不计交易成本、税费和 QDII 溢价；历史表现不代表未来。")}</li>
        <li>每次启动服务时自动更新数据，也可以随时点右上角「刷新数据」；单个数据源失败时保留旧数据，并在「数据健康」页列出。</li>
      </ul></div>
    </details>`;

  const rows = ov.assets.slice().sort(groupSort);
  const r = (k) => (a) => a.recent?.[k];
  sortableTable($("#recentTable"), [
    { key: "name", label: "资产", fmt: (a) => `${assetName(a.code)}${a.core ? "" : ` <span class="badge gray" title="不参与组合实验室">参考</span>`}` },
    { key: "date", label: "最新日期", fmt: (a) => (a.stale ? `<span class="badge amber" title="已滞后 ${a.lag_days} 天">${shortDate(a.recent?.last_date)}</span>` : `<span class="muted">${shortDate(a.recent?.last_date)}</span>`) },
    ...[["m1", "近 1 月", 0.1], ["m3", "近 3 月", 0.15], ["ytd", "今年以来", 0.3], ["y1", "近 1 年", 0.3]].map(([k, l, s]) =>
      ({ key: k, label: l, num: true, val: r(k), fmt: (a) => heat(a.recent?.[k], s) })),
    { key: "y3", label: "近 3 年年化", num: true, val: r("y3"), fmt: (a) => colored(a.recent?.y3) },
    { key: "from_peak", label: "距历史高点", num: true, val: r("from_peak"), title: "人民币计价净值相对历史最高点的跌幅",
      fmt: (a) => (a.recent ? `<span title="高点：${a.recent.peak_date}">${a.recent.from_peak > -0.005 ? `<span class="badge blue">创新高</span>` : pct(a.recent.from_peak)}</span>` : "—") },
  ], rows, { group: (a) => a.group, onRow: (c) => { location.hash = `#/assets/${c}`; }, rowClass: (a) => (a.core ? "" : "dim") });
}

/* ================= 资产对比 ================= */

async function renderAssets(token) {
  const d = await api("/api/assets");
  if (token !== state.token) return;
  const rows = d.assets.slice().sort(groupSort);
  app.innerHTML = `
    <div class="crumb"><a href="#/">总览</a> › 资产对比</div>
    <section class="card">
      <div class="card-head"><h2>长期风险收益（人民币计价，${esc(d.start)} 起，月度数据）</h2>
        <span class="muted small">起点晚于 ${esc(d.start)} 的资产按实际数据计算 · 点击行查看详情</span></div>
      <div id="perfTable"></div>
      <p class="muted small" style="margin-top:8px">${rich("汇率贡献 = 人民币计价年化 − 本币计价年化，负数表示人民币升值拖累了海外资产的回报。")}</p>
    </section>

    <section class="card">
      <div class="card-head"><h2>净值走势（人民币计价，起点 = 1）</h2>
        <div class="chart-tools">${segButtons("range", [["5", "5年"], ["10", "10年"], ["all", "全部"]], "all")}
          <label class="chk"><input type="checkbox" id="logAxis" checked>对数坐标</label></div></div>
      <div id="curveChart" class="chart tall"></div>
      <p class="muted small">点击图例可显示 / 隐藏资产。对数坐标下，同样的斜率代表同样的年化收益。</p>
    </section>

    <section class="card">
      <div class="card-head"><h2>每年谁最好？日历年收益</h2><span class="muted small">人民币计价，今年为今年以来；红涨绿跌，红框为当年最好、绿框为当年最差</span></div>
      <div id="quilt" class="table-wrap"></div>
    </section>

    <section class="card">
      <div class="card-head"><h2>${termLabel("相关系数", "相关系数")}（月收益）</h2>
        <div class="chart-tools">${segButtons("corr", [["full", "全样本"], ["recent", "近 5 年"]], "full")}</div></div>
      <div id="corrChart" class="chart tall"></div>
      <p class="muted small" id="corrNote"></p>
    </section>`;

  const p = (k) => (a) => a.perf?.[k];
  sortableTable($("#perfTable"), [
    { key: "name", label: "资产", fmt: (a) => `${assetName(a.code)}${a.core ? "" : ` <span class="badge gray">参考</span>`}` },
    { key: "basis", label: termLabel("收益口径", "总收益"), fmt: (a) => basisBadge(a.basis) },
    { key: "cagr", label: termLabel("年化收益"), num: true, val: p("cagr"), fmt: (a) => colored(a.perf?.cagr) },
    { key: "fx", label: termLabel("汇率贡献"), num: true, val: (a) => (a.local_cagr == null ? null : a.perf.cagr - a.local_cagr),
      fmt: (a) => (a.local_cagr == null ? `<span class="muted">—</span>` : `<span title="本币年化 ${pct(a.local_cagr)}">${colored(a.perf.cagr - a.local_cagr)}</span>`) },
    { key: "vol", label: termLabel("波动率"), num: true, val: p("vol"), fmt: (a) => pctPlain(a.perf?.vol) },
    { key: "sharpe", label: termLabel("夏普"), num: true, val: p("sharpe"), fmt: (a) => fix(a.perf?.sharpe) },
    { key: "mdd", label: termLabel("最大回撤"), num: true, val: p("mdd"), fmt: (a) => pct(a.perf?.mdd) },
    { key: "worst12", label: termLabel("最差 12 个月"), num: true, val: p("worst12"), fmt: (a) => pct(a.perf?.worst12) },
    { key: "win5", label: termLabel("5 年胜率"), num: true, val: p("win5"), fmt: (a) => pctPlain(a.perf?.win5, 0) },
    { key: "cagr10", label: "近 10 年", num: true, val: p("cagr10"), fmt: (a) => colored(a.perf?.cagr10) },
    { key: "cagr5", label: "近 5 年", num: true, val: p("cagr5"), fmt: (a) => colored(a.perf?.cagr5) },
    { key: "start", label: "起点", fmt: (a) => `<span class="muted">${esc(a.perf?.start || "—")}</span>` },
  ], rows, { group: (a) => a.group, onRow: (c) => { location.hash = `#/assets/${c}`; }, rowClass: (a) => (a.core ? "" : "dim") });

  // 净值走势
  const chart = makeChart($("#curveChart"));
  const defaultOn = new Set(["CSI300", "CSIDIV", "CNBOND", "SPX", "NDX", "N225", "TWII", "GOLD"]);
  const codes = rows.map((a) => a.code).filter((c) => d.curves[c]);
  const draw = (log) => chart.setOption({
    animation: false, color: codes.map(colorOf),
    legend: { type: "scroll", top: 0, data: codes.map(nameOf), selected: Object.fromEntries(codes.map((c) => [nameOf(c), defaultOn.has(c)])) },
    grid: { left: 50, right: 20, top: 40, bottom: 60 },
    tooltip: { trigger: "axis", order: "valueDesc", valueFormatter: (x) => fix(x),
      axisPointer: { label: { formatter: (o) => fmtMonth(o.value) } } },
    xAxis: { type: "time", ...AXIS_STYLE, splitLine: { show: false } },
    yAxis: { type: log ? "log" : "value", ...AXIS_STYLE, scale: true, logBase: 2 },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 18, bottom: 10 }],
    series: codes.map((c) => ({ name: nameOf(c), type: "line", showSymbol: false, data: d.curves[c].map(([m, x]) => [mdate(m), x]),
      lineStyle: { width: c === "CNBOND" || c === "GOLD" ? 2 : 1.6 } })),
  }, true);
  draw(true);
  $("#logAxis").onchange = (e) => draw(e.target.checked);
  const lastM = d.curves.CSI300?.slice(-1)[0]?.[0];
  onSeg(app, "range", (v) => zoomTo(chart, v, mdate(lastM)));

  // 日历年收益
  const years = d.yearly.years;
  const qcodes = rows.filter((a) => a.core).map((a) => a.code);
  $("#quilt").innerHTML = `<table class="tbl compact quilt"><thead><tr><th>资产</th>${years.map((y) => `<th class="num">${y}</th>`).join("")}</tr></thead>
    <tbody>${qcodes.map((c) => {
      const vals = d.yearly.rows[c] || [];
      return `<tr class="link" data-code="${c}"><td>${assetName(c)}</td>${years.map((y, i) => {
        const x = vals[i];
        const ranks = qcodes.map((k) => d.yearly.rows[k]?.[i]).filter((z) => z != null).sort((a, b) => b - a);
        const best = x != null && x === ranks[0], worst = x != null && x === ranks[ranks.length - 1];
        return `<td class="q${best ? " best" : worst ? " worst" : ""}" title="${y} 年 ${esc(nameOf(c))} ${pct(x)}${best ? "（当年最好）" : worst ? "（当年最差）" : ""}">${heat(x, 0.4, 0)}</td>`;
      }).join("")}</tr>`;
    }).join("")}</tbody></table>`;
  $$("#quilt tr[data-code]").forEach((tr) => tr.onclick = () => { location.hash = `#/assets/${tr.dataset.code}`; });

  // 相关性
  const cc = makeChart($("#corrChart"));
  const drawCorr = (which) => {
    const m = d.corr[which];
    const labels = d.corr.labels;
    const data = [];
    m.forEach((row, i) => row.forEach((x, j) => data.push([j, i, x])));
    cc.setOption({
      animation: false,
      tooltip: { formatter: (o) => `${labels[o.value[1]]} × ${labels[o.value[0]]}<br>相关系数 <b>${fix(o.value[2])}</b>` },
      grid: { left: 80, right: 30, top: 10, bottom: 90 },
      xAxis: { type: "category", data: labels, axisLabel: { rotate: 45, fontSize: 11, color: "#4a5361" }, splitArea: { show: true } },
      yAxis: { type: "category", data: labels, inverse: true, axisLabel: { fontSize: 11, color: "#4a5361" }, splitArea: { show: true } },
      visualMap: { min: -1, max: 1, calculable: false, orient: "horizontal", left: "center", bottom: 0, itemHeight: 220,
        inRange: { color: ["#2f6fdb", "#9fbdf0", "#f4f6f9", "#f2b5a9", "#d64532"] }, text: ["同涨同跌 1", "-1 此涨彼跌"] },
      series: [{ type: "heatmap", data, label: { show: true, fontSize: 10, formatter: (o) => fix(o.value[2], 1) } }],
    }, true);
    const range = d.corr[`${which}_range`];
    const short = (d.corr.short || []).map((x) => `${x.name}（${x.since} 起）`).join("、");
    $("#corrNote").innerHTML = rich(`区间 ${range[0]} 至 ${range[1]}${short && which === "full" ? `；${short}历史较短，与它们有关的系数按两者的共同区间计算` : ""}。相关系数越低（偏蓝），放在一起越能分散风险；A 股内部各指数高度相关，海外股票之间也偏高，债券和黄金与股票相关性低。`);
  };
  drawCorr("full");
  onSeg(app, "corr", drawCorr);
}

async function renderAssetDetail(token, code) {
  const d = await api(`/api/asset/${encodeURIComponent(code)}`);
  if (token !== state.token) return;
  const p = d.perf || {}, r = d.recent || {};
  const fxEff = d.local_cagr != null && p.cagr != null ? p.cagr - d.local_cagr : null;
  app.innerHTML = `
    <div class="crumb"><a href="#/">总览</a> › <a href="#/assets">资产对比</a> › ${esc(d.name)}</div>
    <section class="card">
      <div class="card-head"><h2>${assetName(code)} <span class="badge gray">${esc(d.group)}</span>
        ${basisBadge(d.basis)}
        ${d.core ? "" : `<span class="badge gray">参考资产，不参与组合实验室</span>`}</h2>
        <span class="muted small">最新数据 ${esc(r.last_date || "—")}${d.stale ? ` · <span class="warn-text">已滞后 ${d.lag_days} 天</span>` : ""}</span></div>
      <div class="kv-row">
        <div class="kv"><small>${termLabel("年化收益")}（人民币）</small><b>${colored(p.cagr)}</b><span>${esc(p.start || "")} 起，${p.years ?? "—"} 年</span></div>
        ${d.ccy !== "CNY" ? `<div class="kv"><small>本币年化（${esc(d.ccy)}）</small><b>${pct(d.local_cagr)}</b><span>${termLabel("汇率贡献")} ${pct(fxEff)}</span></div>` : ""}
        <div class="kv"><small>${termLabel("波动率")}</small><b>${pctPlain(p.vol)}</b><span>${termLabel("夏普")} ${fix(p.sharpe)}</span></div>
        <div class="kv"><small>${termLabel("最大回撤")}</small><b class="down">${pct(p.mdd)}</b><span>距高点 ${pct(r.from_peak)}</span></div>
        <div class="kv"><small>今年以来</small><b>${colored(r.ytd)}</b><span>近 1 年 ${pct(r.y1)}</span></div>
        <div class="kv"><small>近 5 年年化</small><b>${colored(r.y5)}</b><span>近 3 年 ${pct(r.y3)}</span></div>
      </div>
    </section>
    <section class="card">
      <div class="card-head"><h2>净值与回撤${d.ccy !== "CNY" ? "：人民币计价 vs 本币计价" : ""}</h2>
        <div class="chart-tools">${segButtons("range", [["3", "3年"], ["5", "5年"], ["10", "10年"], ["all", "全部"]], "all")}</div></div>
      <div id="navChart" class="chart tall"></div>
      ${d.ccy !== "CNY" && fxEff != null ? `<p class="muted small">${rich(`两条线的差距就是汇率影响。这段时间${d.ccy}对人民币${fxEff >= 0 ? "升值，人民币计价线在上方，汇率放大了收益" : "贬值，人民币计价线在下方，汇率拖累了收益"}（每年约 ${pct(fxEff)}）。`)}</p>` : ""}
    </section>
    <section class="${d.fx ? "grid2" : ""}">
      <div class="card"><div class="card-head"><h2>日历年收益（人民币计价）</h2></div><div id="yearChart" class="chart short"></div></div>
      ${d.fx ? `<div class="card"><div class="card-head"><h2>汇率：1 ${esc(d.ccy)} 兑人民币</h2><span class="muted small">周度</span></div><div id="fxChart" class="chart short"></div></div>` : ""}
    </section>`;

  const base = d.cny[0]?.[1] || 1;
  const cny = d.cny.map(([t, v]) => [t, v / base]);
  let peak = 0;
  const dd = d.cny.map(([t, v]) => { peak = Math.max(peak, v); return [t, v / peak - 1]; });
  const series = [{ name: "人民币计价", type: "line", showSymbol: false, data: cny, lineStyle: { width: 1.8 }, color: colorOf(code) }];
  if (d.local) {
    const lb = d.local.find(([t]) => t >= d.cny[0][0])?.[1] || 1;
    series.push({ name: `本币计价（${d.ccy}）`, type: "line", showSymbol: false, color: "#9aa4b2", lineStyle: { width: 1.2 },
      data: d.local.filter(([t]) => t >= d.cny[0][0]).map(([t, v]) => [t, v / lb]) });
  }
  series.push({ name: "回撤", type: "line", showSymbol: false, xAxisIndex: 1, yAxisIndex: 1, data: dd, color: "#18935a",
    lineStyle: { width: 1 }, areaStyle: { opacity: 0.15 } });
  const nav = makeChart($("#navChart"));
  nav.setOption({
    animation: false, legend: { top: 0 },
    tooltip: { trigger: "axis", axisPointer: { label: { formatter: (o) => fmtDay(o.value) } },
      formatter: (ps) => `${fmtDay(ps[0].value[0])}<br>${ps.map((x) => `${x.marker}${x.seriesName} ${x.seriesName === "回撤" ? pct(x.value[1]) : fix(x.value[1], 3)}`).join("<br>")}` },
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    grid: [{ left: 50, right: 20, top: 36, height: "52%" }, { left: 50, right: 20, top: "70%", bottom: 50 }],
    xAxis: [{ type: "time", ...AXIS_STYLE, splitLine: { show: false } }, { type: "time", gridIndex: 1, ...AXIS_STYLE, splitLine: { show: false } }],
    yAxis: [{ type: "log", logBase: 2, scale: true, ...AXIS_STYLE }, { gridIndex: 1, max: 0, ...AXIS_STYLE, axisLabel: { ...AXIS_STYLE.axisLabel, formatter: (x) => pctPlain(x, 0) } }],
    dataZoom: [{ type: "inside", xAxisIndex: [0, 1] }, { type: "slider", xAxisIndex: [0, 1], height: 18, bottom: 10 }],
    series,
  });
  onSeg(app, "range", (v) => zoomTo(nav, v, d.cny[d.cny.length - 1][0]));

  const yc = makeChart($("#yearChart"));
  const ys = d.yearly.years.map((y, i) => [String(y), d.yearly.values[i]]).filter(([, x]) => x != null);
  yc.setOption({
    animation: false, grid: { left: 50, right: 10, top: 10, bottom: 30 },
    tooltip: { trigger: "axis", valueFormatter: (x) => pct(x) },
    xAxis: { type: "category", data: ys.map((x) => x[0]), ...AXIS_STYLE },
    yAxis: { ...AXIS_STYLE, axisLabel: { ...AXIS_STYLE.axisLabel, formatter: (x) => pctPlain(x, 0) } },
    series: [{ type: "bar", data: ys.map(([, x]) => ({ value: x, itemStyle: { color: x >= 0 ? "#d9363e" : "#18935a" } })) }],
  });
  if (d.fx) {
    const fc = makeChart($("#fxChart"));
    fc.setOption({
      animation: false, grid: { left: 50, right: 10, top: 10, bottom: 30 },
      tooltip: { trigger: "axis", valueFormatter: (x) => fix(x, 4) },
      xAxis: { type: "time", ...AXIS_STYLE, splitLine: { show: false } }, yAxis: { scale: true, ...AXIS_STYLE },
      series: [{ type: "line", showSymbol: false, data: d.fx, color: "#6b7482" }],
    });
  }
}

/* ================= 组合实验室 ================= */

function labInitWeights() {
  if (state.labW) return;
  const t = currentTarget(null);
  state.labW = Object.fromEntries(state.lab.codes.map((c) => [c, Math.round((t?.weights[c] || 0) * 1000) / 10]));
  state.labSrc = t?.key || null;
}

function loadWeights(weights, src) {
  state.labW = Object.fromEntries(state.lab.codes.map((c) => [c, Math.round((weights[c] || 0) * 1000) / 10]));
  state.labSrc = src;
}

const PERIODS = [["all", "全部"], ["10", "近 10 年"], ["5", "近 5 年"]];

function periodFrom(period) {
  const lab = state.lab;
  if (period === "all") return null;
  const k = Number(period) * 12;
  return lab.dates.length > k ? lab.dates[lab.dates.length - k - 1] : null;
}

async function renderLab(token) {
  await loadLab();
  if (token !== state.token) return;
  labInitWeights();
  const lab = state.lab;
  const groups = GROUP_ORDER.map((g) => [g, lab.codes.filter((c) => lab.groups[c] === g)]).filter(([, cs]) => cs.length);
  const benchOpts = lab.presets.map((p) => `<option value="${p.key}" ${p.key === state.labBench ? "selected" : ""}>${esc(p.name)}</option>`).join("");

  app.innerHTML = `
    <div class="crumb"><a href="#/">总览</a> › 组合实验室</div>
    <section class="card">
      <div class="card-head"><h2>从这里开始</h2>
        <span class="muted small">选一个起点，再拖动左侧滑块调整权重，右侧结果实时更新</span></div>
      <div class="chips" id="srcChips"></div>
    </section>
    <section class="lab">
      <div class="card lab-side">
        <div class="card-head" style="margin-bottom:4px"><h2>权重</h2>
          <span><button class="btn sm" id="btnEqual">等权</button> <button class="btn sm ghost" id="btnClear">清空</button></span></div>
        <div id="weights">${groups.map(([g, cs]) => `<div class="wgroup"><div class="wgroup-name"><span>${g}</span><span data-gsum="${g}"></span></div>
          ${cs.map((c) => `<div class="wrow"><label title="${esc(lab.names[c])}"><i style="background:${colorOf(c)}"></i>${esc(lab.names[c])}</label>
            <input type="range" min="0" max="100" step="1" data-c="${c}"><input type="number" min="0" max="100" step="0.5" data-n="${c}"></div>`).join("")}</div>`).join("")}</div>
        <div class="wtotal"><span>合计 <b id="wSum"></b></span><button class="btn sm" id="btnNorm" title="按比例缩放到 100%">调整到 100%</button></div>
        <p class="muted small" id="wNote" style="margin-top:6px"></p>
        <div class="cta" style="margin-top:10px"><button class="btn primary" id="btnSave">设为我的目标组合</button><a class="btn" href="#/holdings">去对照我的持仓</a></div>
      </div>
      <div style="display:flex;flex-direction:column;gap:16px;min-width:0">
        <div class="card">
          <div class="card-head"><h2>回测结果</h2>
            <div class="chart-tools">${segButtons("period", PERIODS, state.labPeriod)}
              <label class="chk">对比 <select id="benchSel">${benchOpts}</select></label></div></div>
          <p class="hint small" id="lateNote" hidden></p>
          <div class="metric-grid" id="metrics"></div>
          <div id="cmpTable" style="margin-top:12px"></div>
        </div>
        <div class="card">
          <div class="card-head"><h2>净值与回撤</h2><label class="chk"><input type="checkbox" id="labLog" ${state.labLog ? "checked" : ""}>对数坐标</label></div>
          <div id="labChart" class="chart tall"></div>
        </div>
        <div class="grid2">
          <div class="card"><div class="card-head"><h2>${termLabel("风险贡献")}</h2><span class="muted small"><i style="display:inline-block;width:10px;height:7px;background:#c9d6ea;border-radius:2px"></i> 权重
            <i style="display:inline-block;width:10px;height:7px;background:var(--warm);border-radius:2px;margin-left:6px"></i> 风险贡献</span></div>
            <div id="rcBox"></div></div>
          <div class="card"><div class="card-head"><h2>日历年收益</h2><span class="muted small">* 表示不完整年份</span></div><div id="yearBox" class="table-wrap"></div></div>
        </div>
        <div class="card">
          <div class="card-head"><h2>${termLabel("滚动优化")}参考</h2><span class="muted small">${rich("每年末只用过去 60 个月数据计算权重，避免用未来数据挑权重")}</span></div>
          <div id="dynBox"></div>
        </div>
      </div>
    </section>`;

  // 起点选择
  const drawChips = () => {
    const mine = store.get(TARGET_KEY, null);
    const items = [];
    if (mine?.weights) items.push({ key: "mine", name: "我的目标组合", cls: "mine", w: mine.weights });
    lab.presets.forEach((p) => items.push({ key: p.key, name: p.name, w: p.weights, title: p.desc }));
    lab.dynamic.forEach((d) => items.push({ key: `dyn_${d.key}`, name: `${d.name}·最新权重`, w: d.latest, title: d.desc }));
    $("#srcChips").innerHTML = items.map((it) => `<button class="chip ${it.cls || ""} ${state.labSrc === it.key ? "on" : ""}" data-k="${it.key}" title="${esc(it.title || "")}">${esc(it.name)}</button>`).join("")
      + (state.labSrc === "custom" ? `<span class="chip on" style="cursor:default">自定义（未保存）</span>` : "");
    $$("#srcChips button").forEach((b) => b.onclick = () => {
      const it = items.find((x) => x.key === b.dataset.k);
      loadWeights(it.w, it.key);
      syncInputs();
      drawChips();
      update();
    });
  };

  const syncInputs = () => {
    lab.codes.forEach((c) => {
      $(`input[data-c="${c}"]`).value = state.labW[c];
      $(`input[data-n="${c}"]`).value = state.labW[c];
    });
  };

  const chart = makeChart($("#labChart"));
  let pending = false;
  const update = () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; compute(); });
  };

  const compute = () => {
    const W = state.labW;
    const sum = Object.values(W).reduce((a, x) => a + x, 0);
    $("#wSum").textContent = `${Math.round(sum * 10) / 10}%`;
    $("#wSum").className = Math.abs(sum - 100) > 0.05 ? "bad" : "";
    $("#wNote").textContent = sum <= 0 ? "请至少给一个资产设置权重。"
      : Math.abs(sum - 100) > 0.05 ? `合计不是 100%，回测按比例折算（例如 ${nameOf(lab.codes.find((c) => W[c] > 0))} 实际占 ${pctPlain(W[lab.codes.find((c) => W[c] > 0)] / sum)}）。` : "";
    groups.forEach(([g, cs]) => { $(`[data-gsum="${g}"]`).textContent = `${Math.round(cs.reduce((a, c) => a + W[c], 0) * 10) / 10}%`; });
    if (sum <= 0) { $("#metrics").innerHTML = ""; $("#cmpTable").innerHTML = ""; chart.clear(); $("#rcBox").innerHTML = ""; $("#yearBox").innerHTML = ""; return; }

    const from = periodFrom(state.labPeriod);
    const me = backtest(W, from);
    const benchP = lab.presets.find((p) => p.key === state.labBench);
    const bench = backtest(benchP.weights, me.curve[0][0]);
    const pm = perfOf(me.curve), pb = perfOf(bench.curve);
    const ln = lateNote(me);
    $("#lateNote").hidden = !ln;
    $("#lateNote").textContent = ln;
    const cmpTxt = (a, b, better) => (a == null || b == null ? "" : `<span class="${(a - b) * better > 0 ? "up" : "down"}">${a - b > 0 ? "+" : ""}${((a - b) * 100).toFixed(1)}</span> 个百分点 vs 对比`);
    $("#metrics").innerHTML = pm ? `
      <div class="metric"><small>${termLabel("年化收益")}</small><b>${pctPlain(pm.cagr)}</b><span>${cmpTxt(pm.cagr, pb?.cagr, 1)}</span></div>
      <div class="metric"><small>${termLabel("波动率")}</small><b>${pctPlain(pm.vol)}</b><span>${cmpTxt(pm.vol, pb?.vol, -1)}</span></div>
      <div class="metric"><small>${termLabel("最大回撤")}</small><b class="down">${pct(pm.mdd)}</b><span>${cmpTxt(pm.mdd, pb?.mdd, 1)}</span></div>
      <div class="metric"><small>${termLabel("最差 12 个月")}</small><b>${pct(pm.worst12)}</b><span>最好 ${pct(pm.best12)}</span></div>`
      : `<div class="muted">区间太短，无法计算指标。</div>`;
    const row = (name, p, bold) => (p ? `<tr class="${bold ? "total" : ""}"><td>${name}</td><td class="num">${pctPlain(p.cagr)}</td><td class="num">${pctPlain(p.vol)}</td>
      <td class="num">${fix(p.sharpe)}</td><td class="num">${pct(p.mdd)}</td><td class="num">${fix(p.calmar)}</td><td class="num">${pctPlain(p.win5, 0)}</td>
      <td class="num">${pct(p.cur_dd)}</td></tr>` : "");
    $("#cmpTable").innerHTML = `<div class="table-wrap"><table class="tbl compact"><thead><tr><th>${esc(me.curve[0][0])} 至 ${esc(me.curve[me.curve.length - 1][0])}</th>
      <th class="num">年化</th><th class="num">波动率</th><th class="num">${termLabel("夏普")}</th><th class="num">最大回撤</th><th class="num">${termLabel("卡玛")}</th>
      <th class="num">${termLabel("5 年胜率")}</th><th class="num">当前回撤</th></tr></thead>
      <tbody>${row("当前组合", pm, true)}${row(esc(benchP.name), pb)}</tbody></table></div>`;

    const log = state.labLog;
    chart.setOption({
      animation: false, legend: { top: 0 }, color: ["#2f6fdb", "#9aa4b2"],
      tooltip: { trigger: "axis", axisPointer: { label: { formatter: (o) => fmtMonth(o.value) } },
        formatter: (ps) => `${fmtMonth(ps[0].value[0])}<br>${ps.map((x) => `${x.marker}${x.seriesName} ${x.seriesName.includes("回撤") ? pct(x.value[1]) : fix(x.value[1], 3)}`).join("<br>")}` },
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      grid: [{ left: 50, right: 20, top: 36, height: "55%" }, { left: 50, right: 20, top: "73%", bottom: 24 }],
      xAxis: [{ type: "time", ...AXIS_STYLE, splitLine: { show: false } }, { type: "time", gridIndex: 1, ...AXIS_STYLE, splitLine: { show: false } }],
      yAxis: [{ type: log ? "log" : "value", logBase: 2, scale: true, ...AXIS_STYLE },
        { gridIndex: 1, max: 0, ...AXIS_STYLE, axisLabel: { ...AXIS_STYLE.axisLabel, formatter: (x) => pctPlain(x, 0) } }],
      series: [
        { name: "当前组合", type: "line", showSymbol: false, lineStyle: { width: 2 }, data: me.curve.map(([m, v]) => [mdate(m), v]) },
        { name: benchP.name, type: "line", showSymbol: false, lineStyle: { width: 1.3 }, data: bench.curve.map(([m, v]) => [mdate(m), v]) },
        { name: "当前组合回撤", type: "line", showSymbol: false, xAxisIndex: 1, yAxisIndex: 1, color: "#2f6fdb", areaStyle: { opacity: 0.15 }, lineStyle: { width: 1 },
          data: me.curve.map(([m], i) => [mdate(m), pm?.dd[i] ?? 0]) },
        { name: `${benchP.name}回撤`, type: "line", showSymbol: false, xAxisIndex: 1, yAxisIndex: 1, color: "#9aa4b2", lineStyle: { width: 1, type: "dashed" },
          data: bench.curve.map(([m], i) => [mdate(m), pb?.dd[i] ?? 0]) },
      ],
    }, true);

    // 风险贡献
    const rc = riskContrib(W, me.i0);
    const nw = normW(W);
    const rcCodes = Object.keys(nw).sort((a, b) => (rc[b] || 0) - (rc[a] || 0));
    const top = rcCodes[0];
    $("#rcBox").innerHTML = rcCodes.map((c) => `<div class="rc-row"><span>${assetName(c)}</span>
      <div class="rc-bars"><i class="w" style="width:${nw[c] * 100}%"></i><i class="r" style="width:${Math.max(0, rc[c] || 0) * 100}%"></i></div>
      <span class="rc-num">${pctPlain(nw[c], 0)} → ${pctPlain(rc[c], 0)}</span></div>`).join("")
      + (top && rc[top] > nw[top] + 0.1 ? `<p class="hint" style="margin-top:10px">${rich(`${nameOf(top)}只占 ${pctPlain(nw[top], 0)} 的权重，却贡献了 ${pctPlain(rc[top], 0)} 的风险，组合涨跌主要由它决定。`)}</p>` : "");

    // 日历年收益
    const ys = yearlyOf(me.curve), yb = new Map(yearlyOf(bench.curve).map((x) => [x.year, x.ret]));
    $("#yearBox").innerHTML = `<table class="tbl compact"><thead><tr><th>年份</th><th class="num">当前组合</th><th class="num">${esc(benchP.name)}</th></tr></thead>
      <tbody>${ys.slice().reverse().map((y) => `<tr><td>${y.year}${y.partial ? "*" : ""}</td><td class="num">${heat(y.ret, 0.3)}</td><td class="num">${heat(yb.get(y.year), 0.3)}</td></tr>`).join("")}</tbody></table>`;

    drawDynamic();
  };

  const drawDynamic = () => {
    const me = backtest(state.labW, lab.wf_start);
    const pm = me && perfOf(me.curve);
    const top = (w) => Object.entries(w).filter(([, x]) => x > 0.005).sort((a, b) => b[1] - a[1]).slice(0, 5)
      .map(([c, x]) => `${esc(nameOf(c))} ${pctPlain(x, 0)}`).join("、");
    $("#dynBox").innerHTML = `<div class="table-wrap"><table class="tbl compact"><thead><tr><th>${esc(lab.wf_start)} 起</th><th class="num">年化</th><th class="num">波动率</th>
      <th class="num">最大回撤</th><th class="num">夏普</th><th>最新权重（用最近 60 个月数据）</th><th></th></tr></thead><tbody>
      ${lab.dynamic.map((d) => `<tr><td title="${esc(d.desc)}">${termLabel(d.name, d.name.replace("滚动·", ""))}</td><td class="num">${pctPlain(d.perf.cagr)}</td>
        <td class="num">${pctPlain(d.perf.vol)}</td><td class="num">${pct(d.perf.mdd)}</td><td class="num">${fix(d.perf.sharpe)}</td>
        <td class="wrap small">${top(d.latest)}</td><td><button class="btn sm" data-dyn="${d.key}">载入</button></td></tr>`).join("")}
      ${pm ? `<tr class="total"><td>${me.curve[0][0] > lab.wf_start ? `当前组合（${esc(me.curve[0][0])} 起，区间较短）` : "当前组合（同期）"}</td><td class="num">${pctPlain(pm.cagr)}</td><td class="num">${pctPlain(pm.vol)}</td><td class="num">${pct(pm.mdd)}</td>
        <td class="num">${fix(pm.sharpe)}</td><td class="wrap small muted">固定权重、每月再平衡</td><td></td></tr>` : ""}
      </tbody></table></div>
      <details style="margin-top:10px"><summary class="small">查看每年的优化权重</summary>${lab.dynamic.map((d) => {
        const yrs = Object.keys(d.history);
        const used = lab.codes.filter((c) => yrs.some((y) => d.history[y][c] > 0.005));
        return `<div class="card-head sub"><h3>${esc(d.name)}</h3></div><div class="table-wrap"><table class="tbl compact"><thead><tr><th>年份</th>
          ${used.map((c) => `<th class="num">${esc(nameOf(c))}</th>`).join("")}</tr></thead><tbody>
          ${yrs.map((y) => `<tr><td>${y}</td>${used.map((c) => `<td class="num">${d.history[y][c] > 0.005 ? pctPlain(d.history[y][c], 0) : `<span class="muted">·</span>`}</td>`).join("")}</tr>`).join("")}
          </tbody></table></div>`;
      }).join("")}</details>
      <p class="muted small" style="margin-top:8px">${rich("最大夏普对历史收益非常敏感，权重每年变化很大；风险平价和最小方差会重仓债券。它们更适合作为“思路参考”，而不是直接照抄。")}</p>`;
    $$("#dynBox button[data-dyn]").forEach((b) => b.onclick = () => {
      const d = lab.dynamic.find((x) => x.key === b.dataset.dyn);
      loadWeights(d.latest, `dyn_${d.key}`);
      syncInputs();
      drawChips();
      update();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  };

  // 事件
  $("#weights").addEventListener("input", (e) => {
    const c = e.target.dataset.c || e.target.dataset.n;
    if (!c) return;
    const v = Math.max(0, Math.min(100, Number(e.target.value) || 0));
    state.labW[c] = v;
    if (e.target.dataset.c) $(`input[data-n="${c}"]`).value = v;
    else $(`input[data-c="${c}"]`).value = v;
    if (state.labSrc !== "custom") { state.labSrc = "custom"; drawChips(); }
    update();
  });
  $("#btnNorm").onclick = () => {
    const s = Object.values(state.labW).reduce((a, x) => a + x, 0);
    if (s <= 0) return;
    lab.codes.forEach((c) => { state.labW[c] = Math.round((state.labW[c] / s) * 1000) / 10; });
    syncInputs();
    update();
  };
  $("#btnEqual").onclick = () => { lab.codes.forEach((c) => { state.labW[c] = Math.round(1000 / lab.codes.length) / 10; }); state.labSrc = "custom"; syncInputs(); drawChips(); update(); };
  $("#btnClear").onclick = () => { lab.codes.forEach((c) => { state.labW[c] = 0; }); state.labSrc = "custom"; syncInputs(); drawChips(); update(); };
  $("#btnSave").onclick = () => {
    const w = normW(state.labW);
    if (!Object.keys(w).length) { toast("请先设置权重", "warn"); return; }
    store.set(TARGET_KEY, { weights: w, saved_at: new Date().toISOString() });
    const hold = store.get(HOLD_KEY, {});
    store.set(HOLD_KEY, { ...hold, target: "mine" });
    state.labSrc = "mine";
    drawChips();
    toast("已保存为我的目标组合，总览和「我的持仓」会以它为准", "ok");
  };
  onSeg(app, "period", (v) => { state.labPeriod = v; update(); });
  $("#benchSel").onchange = (e) => { state.labBench = e.target.value; update(); };
  $("#labLog").onchange = (e) => { state.labLog = e.target.checked; update(); };

  syncInputs();
  drawChips();
  compute();
}

/* ================= 我的持仓与再平衡 ================= */

async function renderHoldings(token) {
  await loadLab();
  if (token !== state.token) return;
  const lab = state.lab;
  const hold = { amounts: {}, threshold: 5, newCash: 0, ...store.get(HOLD_KEY, {}) };
  const opts = targetOptions();
  if (!opts.find((o) => o.key === hold.target)) hold.target = currentTarget(null)?.key;
  const save = () => store.set(HOLD_KEY, hold);
  const groups = GROUP_ORDER.map((g) => [g, lab.codes.filter((c) => lab.groups[c] === g)]).filter(([, cs]) => cs.length);

  app.innerHTML = `
    <div class="crumb"><a href="#/">总览</a> › 我的持仓与再平衡</div>
    <section class="card">
      <div class="card-head"><h2>我的持仓与再平衡</h2><span class="muted small">🔒 数据只保存在本浏览器（localStorage），不会上传</span></div>
      <div class="hold-tools">
        <label>对照目标 <select id="tgtSel">${opts.map((o) => `<option value="${o.key}" ${o.key === hold.target ? "selected" : ""}>${esc(o.name)}</option>`).join("")}</select></label>
        <label>偏离阈值 ± <input type="number" id="thIn" min="1" max="30" step="1" value="${hold.threshold}" style="width:60px"> 个百分点</label>
        <label>本次新增资金 <input type="number" id="cashIn" min="0" step="1000" value="${hold.newCash || ""}" placeholder="0" style="width:120px"> 元</label>
        <a class="go" href="#/lab">调整目标组合 ›</a>
      </div>
      <div id="tgtBar" style="margin-top:12px"></div>
    </section>
    <section class="summary-strip" id="summary"></section>
    <section class="card">
      <div class="card-head"><h2>逐项对照</h2><span class="muted small">按基金市值填写，例如沪深300 指数基金填入“沪深300”；没有的留空</span></div>
      <div class="table-wrap"><table class="tbl" id="holdTbl"><thead><tr>
        <th>资产</th><th class="num">持有金额（元）</th><th class="num">当前占比</th><th class="num">目标占比</th><th>偏离</th>
        <th class="num">${termLabel("再平衡")}操作</th><th class="num" id="addHead">新增资金分配</th></tr></thead>
        <tbody>${groups.map(([g, cs]) => `<tr class="group"><td colspan="7">${g}</td></tr>${cs.map((c) => `<tr data-row="${c}">
          <td>${assetName(c)}</td><td class="num"><input type="number" min="0" step="1000" data-amt="${c}" value="${hold.amounts[c] || ""}" placeholder="0"></td>
          <td class="num" data-f="cw"></td><td class="num" data-f="tw"></td><td data-f="dev"></td><td class="num" data-f="trade"></td><td class="num" data-f="add"></td></tr>`).join("")}`).join("")}
        <tr class="total"><td>合计</td><td class="num" id="totAmt"></td><td class="num">100%</td><td class="num">100%</td><td></td><td></td><td class="num" id="totAdd"></td></tr>
        </tbody></table></div>
      <p class="muted small" style="margin-top:8px">${rich("再平衡操作 = 把每项调回目标占比需要买入（红）或卖出（绿）的金额，已取整到百元。只用新增资金时，优先买入低配的资产，不需要卖出。实际操作时可以只处理超出阈值的项目，以减少交易成本。")}</p>
    </section>
    <section class="card">
      <div class="card-head"><h2>当前配置 vs 目标：历史表现</h2><span class="muted small">按当前占比固定权重、每月再平衡回测，两者取相同区间</span></div>
      <div id="holdPerf"></div>
    </section>`;

  const r100 = (x) => Math.round(x / 100) * 100;
  const compute = () => {
    const tgt = currentTarget(hold.target);
    $("#tgtBar").innerHTML = weightBar(tgt.weights);
    const plan = rebalancePlan(hold.amounts, tgt.weights, hold.threshold, hold.newCash || 0);
    const th = hold.threshold / 100;
    plan.rows.forEach((r) => {
      const tr = $(`tr[data-row="${r.code}"]`);
      const f = (k) => $(`[data-f="${k}"]`, tr);
      f("cw").textContent = plan.total > 0 ? pctPlain(r.cw) : "—";
      f("tw").textContent = r.tw ? pctPlain(r.tw) : "—";
      const over = Math.abs(r.dev) > th;
      const w = Math.min(Math.abs(r.dev) / 0.2, 1) * 50;
      f("dev").innerHTML = plan.total > 0 ? `<span class="dev"><span class="dev-track"><i style="${r.dev >= 0 ? `left:50%;width:${w}%` : `left:${50 - w}%;width:${w}%`};background:${over ? "var(--warm)" : "#b8c2cf"}"></i></span>
        <span class="${over ? "warn-text" : "muted"}">${r.dev > 0 ? "+" : ""}${(r.dev * 100).toFixed(1)}</span>${over ? ` <span class="badge amber">${r.dev > 0 ? "超配" : "低配"}</span>` : ""}</span>` : "";
      const t = r100(r.trade);
      f("trade").innerHTML = plan.total <= 0 || t === 0 ? `<span class="muted">—</span>`
        : `<span class="${t > 0 ? "trade-buy" : "trade-sell"}${over ? "" : " muted"}" style="${over ? "" : "font-weight:400"}">${t > 0 ? "买入" : "卖出"} ${money(Math.abs(t))}</span>`;
      const a = r100(r.add || 0);
      f("add").innerHTML = hold.newCash > 0 ? (a > 0 ? `<span class="trade-buy">买入 ${money(a)}</span>` : `<span class="muted">—</span>`) : "";
    });
    $("#totAmt").textContent = money(plan.total);
    $("#totAdd").textContent = hold.newCash > 0 ? money(hold.newCash) : "";
    $("#addHead").style.opacity = hold.newCash > 0 ? 1 : 0.4;

    let advice;
    if (plan.total <= 0) advice = "先在下表录入各资产的持有金额。";
    else if (!plan.over.length) advice = "各资产偏离都在阈值以内，<b>无需操作</b>。";
    else if (plan.fixedByCash) advice = `有 ${plan.over.length} 项超出阈值，<b>按右列分配新增资金即可纠偏</b>，不需要卖出。`;
    else advice = `有 ${plan.over.length} 项超出阈值，<b>建议再平衡</b>：卖出超配的部分、买入低配的部分${hold.newCash > 0 ? "（新增资金不足以单独纠偏）" : "，或用后续新增资金优先补低配"}。`;
    $("#summary").innerHTML = `
      <div class="metric"><small>持仓总额（元）</small><b>${money(plan.total)}</b><span>${hold.newCash > 0 ? `加上新增资金后 ${money(plan.after)}` : "人民币"}</span></div>
      <div class="metric"><small>最大偏离</small><b class="${plan.over.length ? "warn-text" : ""}">${plan.total > 0 ? `${plan.maxDev > 0 ? "+" : ""}${(plan.maxDev * 100).toFixed(1)}` : "—"}</b><span>个百分点（阈值 ±${hold.threshold}）</span></div>
      <div class="metric"><small>超出阈值</small><b>${plan.total > 0 ? plan.over.length : "—"}</b><span>项资产</span></div>
      <div class="metric"><small>建议</small><span style="font-size:13px;color:var(--text);margin-top:4px">${advice}</span></div>`;

    // 历史表现
    if (plan.total > 0) {
      const cw = Object.fromEntries(plan.rows.map((r) => [r.code, r.cw]));
      const a0 = backtest(cw), b0 = backtest(tgt.weights);
      const s0 = a0.curve[0][0] > b0.curve[0][0] ? a0.curve[0][0] : b0.curve[0][0];
      const a = backtest(cw, s0), b = backtest(tgt.weights, s0);
      const pa = perfOf(a.curve), pb = perfOf(b.curve);
      const late = [...new Set([...a0.late, ...b0.late])];
      const ln = lateNote({ late, curve: a.curve });
      const row = (n, p) => `<tr><td>${n}</td><td class="num">${pctPlain(p.cagr)}</td><td class="num">${pctPlain(p.vol)}</td><td class="num">${pct(p.mdd)}</td>
        <td class="num">${pct(p.worst12)}</td><td class="num">${fix(p.sharpe)}</td></tr>`;
      $("#holdPerf").innerHTML = pa && pb ? `<div class="table-wrap"><table class="tbl compact"><thead><tr><th>${esc(a.curve[0][0])} 起</th><th class="num">年化</th><th class="num">波动率</th>
        <th class="num">最大回撤</th><th class="num">最差 12 个月</th><th class="num">夏普</th></tr></thead>
        <tbody>${row("当前配置", pa)}${row(esc(tgt.name), pb)}</tbody></table></div>
        ${ln ? `<p class="muted small" style="margin-top:6px">${esc(ln)}</p>` : ""}
        <p class="hint" style="margin-top:10px">${pa.mdd < pb.mdd - 0.05 ? `当前配置的历史最大回撤比目标深 ${((pb.mdd - pa.mdd) * 100).toFixed(0)} 个百分点，风险明显高于目标。`
          : pa.mdd > pb.mdd + 0.05 ? `当前配置比目标更保守，历史最大回撤浅 ${((pa.mdd - pb.mdd) * 100).toFixed(0)} 个百分点，长期收益也可能更低。`
          : "当前配置与目标的风险水平接近。"}</p>` : `<div class="muted">区间太短。</div>`;
    } else {
      $("#holdPerf").innerHTML = `<div class="empty">录入持仓后显示。</div>`;
    }
  };

  $("#holdTbl").addEventListener("input", (e) => {
    const c = e.target.dataset.amt;
    if (!c) return;
    const v = Number(e.target.value);
    if (v > 0) hold.amounts[c] = v; else delete hold.amounts[c];
    save();
    compute();
  });
  $("#tgtSel").onchange = (e) => { hold.target = e.target.value; save(); compute(); };
  $("#thIn").oninput = (e) => { hold.threshold = Math.max(1, Number(e.target.value) || 5); save(); compute(); };
  $("#cashIn").oninput = (e) => { hold.newCash = Math.max(0, Number(e.target.value) || 0); save(); compute(); };
  compute();
}

/* ================= A 股估值 ================= */

async function renderValuation(token) {
  const v = await api("/api/valuation");
  if (token !== state.token) return;
  const vd = v.verdict;
  app.innerHTML = `
    <div class="crumb"><a href="#/">总览</a> › A 股估值</div>
    <section class="card hero">
      <div>
        <div class="eyebrow">${termLabel("估值结论")} · 沪深300</div>
        ${vd ? `<h1><b class="tone-${vd.tone}">${esc(vd.label)}</b>　${rich(vd.hint)}</h1>
          <div class="kv-row" style="margin-top:12px">
            <div class="kv"><small>${termLabel("滚动市盈率")}</small><b>${fix(vd.pe)}</b><span>近 10 年第 ${Math.round(vd.pe_pct * 100)}% 分位</span></div>
            <div class="kv"><small>${termLabel("股债利差")}</small><b>${vd.ebs != null ? pctPlain(vd.ebs, 2) : "—"}</b><span>近 10 年第 ${vd.ebs_pct != null ? Math.round(vd.ebs_pct * 100) : "—"}% 分位</span></div>
            ${v.bond ? `<div class="kv"><small>10 年期国债收益率</small><b>${fix(v.bond.latest)}%</b><span>近 10 年第 ${Math.round(v.bond.pct10 * 100)}% 分位</span></div>` : ""}
          </div>` : `<h1 class="muted">估值数据不足</h1>`}
      </div>
      <div class="gauge-box">${vd ? `<div class="gauge-title"><span>${termLabel("便宜程度")}</span><b>${fix(vd.cheapness)}</b></div>${valueBar(vd.cheapness)}
        <div class="gauge-sub">${rich("便宜程度 = （1 − 市盈率分位 + 股债利差分位）÷ 2。估值只决定长期赔率，不决定短期涨跌。")}</div>` : ""}</div>
    </section>

    <section class="card">
      <div class="card-head"><h2>主要指数${termLabel("滚动市盈率")}</h2><span class="muted small">乐咕乐股月度数据 · 点击行查看走势</span></div>
      <div id="peTable"></div>
      <div class="card-head sub"><h3 id="peTitle"></h3>${segButtons("perange", [["10", "近 10 年"], ["all", "全部"]], "10")}</div>
      <div id="peChart" class="chart"></div>
    </section>

    <section class="grid2">
      <div class="card"><div class="card-head"><h2>${termLabel("股债利差")}（沪深300）</h2><span class="muted small">越高越便宜，虚线为近 10 年 20/50/80% 分位</span></div>
        <div id="ebsChart" class="chart short"></div></div>
      <div class="card"><div class="card-head"><h2>10 年期国债收益率</h2><span class="muted small">%，周度</span></div>
        <div id="bondChart" class="chart short"></div></div>
    </section>

    <section class="grid2">
      <div class="card"><div class="card-head"><h2>${termLabel("股息率")} vs 国债</h2><span class="muted small">中证指数官网口径，${esc(v.dividend[0]?.date || "")}</span></div>
        ${v.dividend.length ? `<table class="tbl compact"><thead><tr><th>指数</th><th class="num">股息率</th><th class="num">市盈率（官网）</th><th class="num">股息率 − 国债</th></tr></thead>
        <tbody>${v.dividend.map((x) => `<tr><td>${esc(x.name)}</td><td class="num">${fix(x.dividend_yield)}%</td><td class="num">${fix(x.pe)}</td>
          <td class="num ${x.spread > 0 ? "up" : "down"}">${x.spread > 0 ? "+" : ""}${fix(x.spread)}%</td></tr>`).join("")}</tbody></table>
        <p class="muted small" style="margin-top:8px">${rich("股息率高于国债收益率时，光拿分红就跑赢国债。官网市盈率与乐咕乐股的滚动市盈率算法不同，数值会有差异。")}</p>`
        : `<div class="empty">暂无数据</div>`}</div>
      <div class="card"><div class="card-head"><h2>持有多久才赚钱？</h2><span class="muted small">任意一天买入并持有，人民币全收益，日度滚动</span></div>
        <table class="tbl compact"><thead><tr><th>指数</th>${[1, 3, 5, 10].map((y) => `<th class="num">${y} 年</th>`).join("")}</tr></thead>
        <tbody>${v.holding.map((h) => `<tr><td>${esc(h.name)} <span class="muted small">${esc(h.since)} 起</span></td>${[1, 3, 5, 10].map((y) =>
          `<td class="num" title="年化收益中位数 ${pct(h[`med${y}`])}">${h[`win${y}`] == null ? "—" : `<b>${pctPlain(h[`win${y}`], 0)}</b> <span class="muted small">${pct(h[`med${y}`], 1)}</span>`}</td>`).join("")}</tr>`).join("")}</tbody></table>
        <p class="muted small" style="margin-top:8px">${rich("粗体为盈利概率，灰色为年化收益中位数。持有越久，赚钱的概率越高；但即使持有 5 年，A 股宽基仍有一成多的时间是亏的。")}</p></div>
    </section>

    <section class="card">
      <div class="card-head"><h2>申万一级行业估值</h2><span class="muted small">更新于 ${esc(v.sw_at || "—")} · 点击表头排序</span></div>
      <div id="swTable"></div>
    </section>`;

  // 市盈率表与走势
  const peChart = makeChart($("#peChart"));
  let curPe = v.pe[0]?.code, peRange = "10";
  const drawPe = () => {
    const r = v.pe.find((x) => x.code === curPe);
    if (!r) return;
    $("#peTitle").textContent = `${r.name} 滚动市盈率`;
    const hist = r.history;
    const lastT = new Date(mdate(hist[hist.length - 1][0]));
    const cut = new Date(lastT); cut.setFullYear(lastT.getFullYear() - 10);
    const w10 = hist.filter(([m]) => new Date(mdate(m)) >= cut).map(([, x]) => x).sort((a, b) => a - b);
    const q = (p) => w10[Math.min(w10.length - 1, Math.floor(p * w10.length))];
    const data = (peRange === "10" ? hist.filter(([m]) => new Date(mdate(m)) >= cut) : hist).map(([m, x]) => [mdate(m), x]);
    peChart.setOption({
      animation: false, grid: { left: 50, right: 90, top: 16, bottom: 30 },
      tooltip: { trigger: "axis", axisPointer: { label: { formatter: (o) => fmtMonth(o.value) } }, valueFormatter: (x) => fix(x) },
      xAxis: { type: "time", ...AXIS_STYLE, splitLine: { show: false } }, yAxis: { scale: true, ...AXIS_STYLE },
      series: [{ type: "line", name: "滚动市盈率", showSymbol: false, data, color: "#2f6fdb",
        markLine: { symbol: "none", silent: true, label: { formatter: "{b} {c}", fontSize: 11 },
          data: [["近10年 20%", 0.2, "#2f6fdb"], ["中位数", 0.5, "#8b95a5"], ["80%", 0.8, "#d64532"]]
            .map(([n, p, c]) => ({ name: n, yAxis: Number(q(p).toFixed(1)), lineStyle: { type: "dashed", color: c } })) } }],
    }, true);
  };
  sortableTable($("#peTable"), [
    { key: "name", label: "指数", fmt: (r) => `<b>${esc(r.name)}</b>` },
    { key: "latest", label: "最新", num: true, val: (r) => r.latest, fmt: (r) => fix(r.latest) },
    { key: "pct10", label: termLabel("近 10 年分位", "估值分位"), num: true, val: (r) => r.pct10, fmt: (r) => pctBar(r.pct10) },
    { key: "pct_all", label: "全历史分位", num: true, val: (r) => r.pct_all, fmt: (r) => `${Math.round(r.pct_all * 100)}%` },
    { key: "median10", label: "近 10 年中位数", num: true, val: (r) => r.median10, fmt: (r) => fix(r.median10) },
    { key: "range", label: "近 10 年区间", num: true, fmt: (r) => `${fix(r.min10)} – ${fix(r.max10)}` },
    { key: "since", label: "数据起点", fmt: (r) => `<span class="muted">${esc(r.since)}${r.code === "PE_ZZ1000" ? "（不足 10 年按实际）" : ""}</span>` },
  ], v.pe, { onRow: (c) => { curPe = c; drawPe(); } });
  drawPe();
  onSeg(app, "perange", (x) => { peRange = x; drawPe(); });

  const ln = (el, data, opt) => {
    const c = makeChart(el);
    c.setOption({
      animation: false, grid: { left: 50, right: 70, top: 16, bottom: 50 },
      tooltip: { trigger: "axis", axisPointer: { label: { formatter: (o) => fmtDay(o.value) } }, valueFormatter: opt.fmt },
      xAxis: { type: "time", ...AXIS_STYLE, splitLine: { show: false } },
      yAxis: { scale: true, ...AXIS_STYLE, axisLabel: { ...AXIS_STYLE.axisLabel, formatter: opt.fmt } },
      dataZoom: [{ type: "inside" }, { type: "slider", height: 16, bottom: 6 }],
      series: [{ type: "line", showSymbol: false, data, color: opt.color, markLine: opt.marks }],
    });
  };
  if (v.ebs) {
    ln($("#ebsChart"), v.ebs.history, {
      fmt: (x) => pctPlain(x, 1), color: "#3f9f8f",
      marks: { symbol: "none", silent: true, label: { formatter: (o) => `${o.name} ${pctPlain(o.value, 1)}`, fontSize: 11 },
        data: [["20%", v.ebs.p20, "#d64532"], ["50%", v.ebs.p50, "#8b95a5"], ["80%", v.ebs.p80, "#2f6fdb"]].map(([n, y, c]) => ({ name: n, yAxis: y, lineStyle: { type: "dashed", color: c } })) },
    });
  }
  if (v.bond) ln($("#bondChart"), v.bond.history, { fmt: (x) => `${fix(x)}%`, color: "#6b7482" });

  sortableTable($("#swTable"), [
    { key: "name", label: "行业", fmt: (r) => esc(r.name) },
    { key: "count", label: "成份股", num: true, val: (r) => r.count, fmt: (r) => r.count ?? "—" },
    { key: "pe_ttm", label: termLabel("滚动市盈率"), num: true, val: (r) => (r.pe_ttm > 0 ? r.pe_ttm : null), fmt: (r) => (r.pe_ttm > 0 ? fix(r.pe_ttm) : `<span class="muted">亏损</span>`) },
    { key: "pb", label: "市净率", num: true, val: (r) => r.pb, fmt: (r) => fix(r.pb) },
    { key: "dividend_yield", label: termLabel("股息率"), num: true, val: (r) => r.dividend_yield, fmt: (r) => (r.dividend_yield != null ? `${fix(r.dividend_yield)}%` : "—") },
  ], v.sw, { tblClass: "compact" });
}

/* ================= 数据健康 ================= */

const KIND = { price: "价格", div_yield: "股息率", fx: "汇率", valuation: "估值" };
const SOURCE = {
  csindex: "中证指数", sina_index: "新浪 · 指数", yahoo: "Yahoo Finance", yahoo_div: "Yahoo · ETF 分红",
  sina_xau: "新浪 · 伦敦金", boc_fx: "中国银行", pe_lg: "乐咕乐股", ebs_lg: "乐咕乐股", bond_cn10y: "中国债券信息网",
};
const FREQ = { D: "日", M: "月", Y: "年" };

async function renderHealth(token) {
  const h = await api("/api/health");
  if (token !== state.token) return;
  const st = state.status || {};
  app.innerHTML = `
    <div class="crumb"><a href="#/">总览</a> › 数据健康</div>
    <section class="card stat-row">
      <div class="stat"><small>正常更新的序列</small><b>${h.fresh} / ${h.total}</b></div>
      <div class="stat"><small>上次刷新</small><b>${esc(st.last_refresh || "—")}</b></div>
      <div class="stat"><small>上次刷新失败</small><b class="${h.failed.length ? "warn-text" : ""}">${h.failed.length} 项</b></div>
    </section>
    ${h.failed.length ? `<section class="card"><div class="card-head"><h2>上次刷新失败的项目</h2><span class="muted small">数据库里保留了之前的数据</span></div>
      <ul>${h.failed.map((f) => `<li class="small">${esc(f)}</li>`).join("")}</ul></section>` : ""}
    <section class="card">
      <div class="card-head"><h2>全部数据序列</h2>${segButtons("filter", [["all", "全部"], ["issue", "只看有问题的"]], "all")}</div>
      <div id="hTable"></div>
      <p class="muted small" style="margin-top:8px">过期标准：日度 10 天、月度 45 天、年度 400 天。坏点指相对前值跳变超过阈值（价格 25%、汇率 10%）且几天内又回到原水平的点，只在分析时剔除，原始数据不改。</p>
    </section>`;
  const draw = (f) => sortableTable($("#hTable"), [
    { key: "name", label: "序列", fmt: (r) => `${esc(r.name)}<br><span class="muted small">${esc(r.code)}${r.symbol && r.symbol !== r.code ? ` · ${esc(r.symbol)}` : ""}</span>` },
    { key: "kind", label: "类型", fmt: (r) => KIND[r.kind] || r.kind },
    { key: "source", label: "来源", fmt: (r) => SOURCE[r.source] || r.source },
    { key: "freq", label: "频率", fmt: (r) => FREQ[r.freq] || r.freq },
    { key: "first", label: "起始", val: (r) => r.first_date, fmt: (r) => esc(r.freq === "Y" ? r.first_date?.slice(0, 4) || "—" : r.first_date || "—") },
    { key: "latest", label: "最新", val: (r) => r.latest_date, fmt: (r) => (r.freq === "Y" && r.latest_date
      ? `${r.latest_date.slice(0, 4)}${+r.latest_date.slice(0, 4) === new Date().getFullYear() ? ` <span class="muted small">近 12 个月</span>` : ""}` : esc(r.latest_date || "—")) },
    { key: "points", label: "数据点", num: true, val: (r) => r.points, fmt: (r) => r.points },
    { key: "status", label: "状态", val: (r) => r.issues.length, fmt: (r) => (r.status === "ok" ? `<span class="badge ok">正常</span>`
      : `${r.status === "missing" ? `<span class="badge red">缺失</span>` : `<span class="badge amber">注意</span>`} <span class="small">${esc(r.issues.join("；"))}</span>`
        + (r.outliers.length ? `<br><span class="muted small">坏点日期：${esc(r.outliers.slice(0, 5).join("、"))}${r.outliers.length > 5 ? " 等" : ""}</span>` : "")) },
  ], f === "issue" ? h.rows.filter((r) => r.status !== "ok") : h.rows, { tblClass: "health" });
  draw("all");
  onSeg(app, "filter", draw);
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
    <div class="gl-search"><input id="glq" placeholder="搜索术语，如 回撤、夏普、股债利差…" autocomplete="off"></div>
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
    <div class="crumb"><a href="#/">总览</a> › 研究报告</div>
    <section class="card">
      <div class="card-head"><h2>研究报告</h2><span class="muted small">放在 reports/ 目录下的报告，最新的在前</span></div>
      ${list.length ? `<ul class="report-list">${list.map((n) => `<li><a href="/reports/${encodeURIComponent(n)}" target="_blank" rel="noopener">${esc(n.replace(/\.(html|txt)$/, ""))}</a>
        <span class="muted small">${n.endsWith(".txt") ? "文本" : "网页"}</span></li>`).join("")}</ul>`
        : `<div class="empty">还没有报告。</div>`}
    </section>`;
}

/* ================= 新手指引 ================= */

function guideSteps() {
  return [
    {
      title: "欢迎使用全球资产配置台",
      body: `<p>它回答两个问题：<b>我的钱应该怎样在 A 股、海外股票、债券和黄金之间分配？现在需不需要调整？</b></p>
        <p>建议顺序：先看<b>总览</b>的今日结论 → 在<b>组合实验室</b>调出自己的目标组合 → 在<b>我的持仓</b>录入持仓，看偏离和买卖金额 → 以后每隔一段时间回来看一眼。</p>`,
    },
    {
      title: "全部按人民币计价",
      body: `<p>覆盖 18 类资产：A 股宽基、红利与科创成长、中国债券、黄金，以及<b>美国、日本、英国、德国、香港、台湾、韩国</b>股市。</p>
        <p>海外资产按当日汇率换算成人民币，并尽量计入分红（总收益）。所以这里看到的就是“用人民币投资能拿到的回报”，汇率的影响单独列出。</p>`,
    },
    {
      title: "组合实验室与我的持仓",
      body: `<p>在组合实验室拖动滑块，回测结果实时更新：年化收益、最大回撤、最差的一年、风险主要来自谁。满意后点“设为我的目标组合”。</p>
        ${weightBar({ CSIDIV: 0.15, CSI300: 0.1, SPX: 0.15, NDX: 0.05, N225: 0.05, HSI: 0.05, CNBOND: 0.35, GOLD: 0.1 })}
        <p>在「我的持仓」填入各资产的金额，就能看到偏离多少、该买卖多少，以及新增资金怎么分配。<b>持仓只保存在本浏览器，不会上传。</b></p>`,
    },
    {
      title: "估值、信号与数据",
      body: `<p>A 股估值综合市盈率分位和股债利差，给出从“高估”到“低估”的结论：</p>${valueBar(0.69)}
        <p>信号分四级：<span class="lvtag lv-risk">风险</span> <span class="lvtag lv-watch">留意</span> <span class="lvtag lv-positive">积极</span> <span class="lvtag lv-info">提示</span>，点击可查看依据。</p>
        <p>每次启动服务会自动更新数据，右上角显示数据日期。带虚线的词悬停可以看解释。</p>`,
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

function renderNav(page) {
  const links = [["", "总览"], ["assets", "资产对比"], ["lab", "组合实验室"], ["holdings", "我的持仓"],
    ["valuation", "A股估值"], ["health", "数据健康"], ["glossary", "术语"], ["reports", "报告"]];
  $("#nav").innerHTML = links.map(([h, t]) => `<a href="#/${h}" class="${h === (page || "") ? "on" : ""}">${t}</a>`).join("");
}

async function render() {
  if (state.initMode) { renderInit(); return; }
  const token = ++state.token;
  disposeCharts();
  const [page, a] = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  renderNav(page);
  app.innerHTML = `<div class="loading">加载中…</div>`;
  window.scrollTo(0, 0);
  try {
    if (!page) await renderOverview(token);
    else if (page === "assets") await (a ? renderAssetDetail(token, a) : renderAssets(token));
    else if (page === "lab") await renderLab(token);
    else if (page === "holdings") await renderHoldings(token);
    else if (page === "valuation") await renderValuation(token);
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
    console.error(e);
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
      <p class="muted">请双击 scripts/start_server.bat 启动服务，并通过 http://127.0.0.1:8322 打开页面（不要直接双击 index.html）。</p></div>`;
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

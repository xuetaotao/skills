"use strict";

/* ================= 基础工具 ================= */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const app = $("#app");

const state = {
  meta: null, mmap: {}, glossary: [], termRe: null, termIndex: {},
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
const send = (path, method, body) => api(path, {
  method, headers: { "Content-Type": "application/json" }, body: body == null ? undefined : JSON.stringify(body),
});

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const shortDate = (d) => (d ? d.slice(5) : "—");
const ok = (v) => v != null && isFinite(v);
const LEVEL = { risk: "风险", watch: "留意", positive: "积极", info: "提示" };
const PNAME = { "03-31": "一季报", "06-30": "中报", "09-30": "三季报", "12-31": "年报" };
const pname = (d) => (d ? `${d.slice(0, 4)}${PNAME[d.slice(5, 10)] || ""}` : "—");
const PALETTE = ["#2f6fdb", "#e0862f", "#18935a", "#9c6ade", "#d64532", "#16a085", "#b0703c", "#c27ba0", "#7e9b32", "#4a5361"];

/** 右下角提示；action = { label, fn } 时带一个按钮（如“撤销”），点了就关闭 */
function toast(text, kind = "ok", ms = 4000, action = null) {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = text;
  if (action) {
    const b = document.createElement("button");
    b.className = "toast-act";
    b.textContent = action.label;
    b.onclick = () => { el.remove(); action.fn(); };
    el.appendChild(b);
  }
  $("#toasts").appendChild(el);
  setTimeout(() => el.classList.add("out"), ms);
  setTimeout(() => el.remove(), ms + 400);
}

const GUIDE_KEY = "fr_guide_v1";

const median = (xs) => {
  const v = xs.filter(ok).sort((a, b) => a - b);
  if (!v.length) return null;
  const m = v.length >> 1;
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
};

/** 坐标轴范围：远离主体（超出 10%–90% 分位区间 1.5 倍）的极端值不纳入，避免把其余点挤成一团 */
function robustRange(vals) {
  const s = vals.filter(ok).sort((a, b) => a - b);
  if (s.length < 6) return {};
  const q = (p) => s[Math.round(p * (s.length - 1))];
  const lo = q(0.1), hi = q(0.9), span = hi - lo || Math.abs(hi) || 1;
  return { min: s[0] < lo - 1.5 * span ? lo - 0.5 * span : null, max: s[s.length - 1] > hi + 1.5 * span ? hi + 0.5 * span : null };
}

/* ================= 指标格式化 ================= */

const M = (k) => state.mmap[k] || { key: k, name: k, short: k, unit: "", digits: 2 };
const isGrowth = (k) => /TZ$|_YOY$/.test(k);
/** 这些比率很小，变化用基点表达 */
const BP_KEYS = new Set(["NET_INTEREST_MARGIN", "NET_INTEREST_SPREAD", "NONPERLOAN", "LOAN_PROVISION_RATIO"]);
/** 报告期累计的比率：不同季度之间不可比，走势默认看历年同期 */
const CUM_RATIO = new Set(["ROEJQ", "EPSJB", "ROIC"]);

const fmtNum = (v, d) => (ok(v) ? Number(v).toLocaleString("zh-CN", { minimumFractionDigits: d, maximumFractionDigits: d }) : "—");

function bigYi(v, d = 2) {
  if (!ok(v)) return "—";
  if (Math.abs(v) >= 10000) return `${fmtNum(v / 10000, 2)} 万亿`;
  return `${fmtNum(v, Math.abs(v) >= 1000 ? 0 : d)} 亿`;
}

/** 按指标单位格式化；unit=false 时不带单位（表格里用） */
function fmt(k, v, unit = true) {
  if (!ok(v)) return "—";
  const m = M(k);
  if (m.unit === "%") return `${isGrowth(k) && v > 0 ? "+" : ""}${v.toFixed(m.digits)}%`;
  if (m.unit === "亿") return unit ? bigYi(v, m.digits) : fmtNum(v, Math.abs(v) >= 1000 ? 0 : m.digits);
  if (m.unit === "x") return `${v.toFixed(2)}${unit ? " 倍" : ""}`;
  if (m.unit === "天") return `${v.toFixed(1)}${unit ? " 天" : ""}`;
  if (m.unit === "元") return `${v.toFixed(m.digits)}${unit ? " 元" : ""}`;
  return v.toFixed(m.digits);
}

/** 增速类指标按 A 股惯例着色：涨红跌绿 */
function fmtC(k, v, unit = true) {
  const t = fmt(k, v, unit);
  if (!isGrowth(k) || !ok(v) || v === 0) return t === "—" ? `<span class="muted">—</span>` : t;
  return `<span class="${v > 0 ? "up" : "down"}">${t}</span>`;
}

/** 与基期相比的变化文字 */
function delta(k, cur, base) {
  if (!ok(cur) || !ok(base)) return null;
  const m = M(k), d = cur - base;
  if (m.unit === "%") {
    if (BP_KEYS.has(k)) {
      const bp = Math.round(d * 100);
      return bp === 0 ? "持平" : `${bp > 0 ? "+" : ""}${bp} 基点`;
    }
    return Math.abs(d) < 0.005 ? "持平" : `${d > 0 ? "+" : ""}${d.toFixed(2)} 个百分点`;
  }
  if (!base) return null;
  const r = (cur / Math.abs(base) - (base < 0 ? -1 : 1)) * 100;
  return `${r > 0 ? "+" : ""}${r.toFixed(1)}%`;
}

/** 行业排名徽章：前 20% 绿、后 20% 橙 */
function rankBadge(k, pr, compact = false) {
  if (!pr || !M(k).better) return "";
  const top = pr.rank <= Math.max(1, Math.round(pr.n * 0.2));
  const bottom = pr.rank > pr.n - Math.max(1, Math.round(pr.n * 0.2));
  return `<span class="badge ${top ? "ok" : bottom ? "amber" : "gray"}" title="同行业 ${pr.n} 家中排第 ${pr.rank}（${M(k).better === "low" ? "越低越好" : "越高越好"}）；中位数 ${fmt(k, pr.median)}">${compact ? "" : "第 "}${pr.rank}/${pr.n}</span>`;
}

/** 归母净利增速被一次性损益扭曲时，旁边标出扣非增速 */
function oneoffTag(oo) {
  const tip = `非经常性损益：上年同期 ${oo.nr_ly.toFixed(2)} 亿（占归母净利 ${oo.share_ly}%），本期 ${oo.nr.toFixed(2)} 亿（占 ${oo.share}%）。`
    + (oo.kind === "base" ? "归母增速被一次性因素压低，扣非口径更能代表主业。" : "归母增速被一次性因素抬高，扣非口径更能代表主业。");
  return `<span class="badge blue" title="${esc(tip)}">扣非 ${oo.gk > 0 ? "+" : ""}${oo.gk.toFixed(2)}%</span>`;
}

/** 企业性质标签；悬停看东方财富的原始分类、控股股东和实际控制人 */
function natureTag(n) {
  if (!n) return "";
  const tip = `企业性质：${n.raw}\n控股股东：${n.controller || "无"}\n实际控制人：${n.real || "无"}\n（东方财富 F10 口径）`;
  return `<span class="ntag n-${n.cls}" title="${esc(tip)}">${esc(n.name)}</span>`;
}

const sgn = (v, d = 2) => (ok(v) ? `${v > 0 ? "+" : ""}${v.toFixed(d)}%` : "—");
const upDown = (v, text = sgn(v)) => (ok(v) && v !== 0 ? `<span class="${v > 0 ? "up" : "down"}">${text}</span>` : ok(v) ? text : `<span class="muted">—</span>`);

/** 区间涨跌幅（复权，含分红送转）；悬停看起算日、纯股价涨跌和年化 */
function perfCell(x) {
  if (!x || !ok(x.ret)) return `<span class="muted" title="上市时间不足这个区间，或没有股价数据">—</span>`;
  const tip = `${x.base} 收盘起算\n含分红（复权）：${sgn(x.ret)}\n纯股价（不复权）：${sgn(x.raw)}${ok(x.ann) ? `\n年化：${sgn(x.ann)}` : ""}`;
  return `<span class="${x.ret > 0 ? "up" : x.ret < 0 ? "down" : ""}" title="${esc(tip)}">${sgn(x.ret)}</span>`;
}

const MARKET = { mcap: "总市值", pe: "市盈率", pb: "市净率", dy: "股息率" };
/** 分红指标（横向对比“分红”视图、排名图、散点图）：分位和利差来自股息率历史，其余是最近一个完整财年 */
const DIV = {
  d_pct: { label: "股息率分位", get: (x) => x.stats?.pct, fmt: (v) => `${Math.round(v * 100)}%` },
  d_spread: { label: "股债利差", get: (x) => x.stats?.spread, fmt: (v) => sgn(v) },
  d_dps: { label: "每股分红", get: (x) => x.summary?.dps, fmt: (v) => `${v.toFixed(3)} 元` },
  d_payout: { label: "分红率", get: (x) => x.summary?.payout, fmt: (v) => `${v.toFixed(1)}%` },
  d_years: { label: "连续分红年数", get: (x) => x.summary?.years, fmt: (v) => `${v} 年` },
  d_cagr3: { label: "每股分红3年增速", get: (x) => x.summary?.cagr3, fmt: (v) => sgn(v, 1) },
};
const isPerf = (k) => k.startsWith("r_");
const perfLabel = (k) => state.meta.perf_periods.find((p) => p.key === k.slice(2))?.label || k;
const getAny = (r, k) => (isPerf(k) ? r.perf?.[k.slice(2)]?.ret : k in MARKET ? r.market?.[k] : k in DIV ? DIV[k].get(r.div || {}) : r.values?.[k]);
function fmtAny(k, v) {
  if (isPerf(k)) return sgn(v);
  if (k in DIV) return ok(v) ? DIV[k].fmt(v) : "—";
  if (!(k in MARKET)) return fmt(k, v);
  if (!ok(v)) return "—";
  if (k === "mcap") return bigYi(v, 0);
  if (k === "dy") return `${v.toFixed(2)}%`;
  return v.toFixed(2);
}
const labelAny = (k) => (isPerf(k) ? `${perfLabel(k)}涨跌幅` : MARKET[k] || DIV[k]?.label || M(k).name);
/** 股息率在近几年里的分位：越高说明相对分红股价越便宜（与估值分位方向相反，所以用反向配色） */
const dyPct = (div) => (ok(div?.stats?.pct) ? pctBar(div.stats.pct, true) : `<span class="muted">—</span>`);
const changeTxt = (v) => (ok(v) ? `<span class="${v > 0 ? "up" : v < 0 ? "down" : ""}">${v > 0 ? "+" : ""}${v.toFixed(2)}%</span>` : "");

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

/** 指标名：能对上术语百科的加悬停解释 */
function metricLabel(k, short = true) {
  const m = M(k), label = short ? m.short : m.name;
  for (const c of [m.short, m.name]) if (state.termIndex[c] != null) return termLabel(label, c);
  const hit = state.termRe && m.name.match(state.termRe);
  return hit ? termLabel(label, hit[0]) : esc(label);
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
    pill.innerHTML = `<span class="spinner"></span>${s.reason === "添加自选股" ? "下载新股数据" : "更新中"} ${s.done}/${s.total || "…"}`;
    pill.className = "status-pill busy";
    pill.title = s.current ? `正在获取：${s.current}` : "";
    bar.hidden = false;
    $("i", bar).style.width = `${s.total ? (s.done / s.total) * 100 : 5}%`;
    btn.disabled = true;
  } else {
    pill.innerHTML = s.empty ? "暂无数据"
      : `<span class="dot ${s.failed ? "amber" : "ok"}"></span>股价截至 ${shortDate(s.trade_date)} · ${s.failed ? `${s.failed} 项失败` : "全部正常"}`;
    pill.className = `status-pill${s.failed ? " warn" : ""}`;
    pill.title = `上次完整刷新：${s.last_refresh || "从未"}\n点击查看数据健康`;
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
    if (s.updating || !state.polling) return;
    clearInterval(state.polling);
    state.polling = null;
    if (s.empty) { renderInit(); return; }
    if (s.last_error) toast(`更新完成，但有问题：${s.last_error}`, "warn", 8000);
    else toast(s.reason === "添加自选股" ? "新自选股的同行业、估值和分红数据已就绪" : "数据已更新到最新", "ok");
    state.initMode = false;
    render();
  }, 1500);
}

async function manualRefresh() {
  try {
    const r = await api("/api/refresh", { method: "POST" });
    toast(r.started ? "开始刷新，大约需要半分钟到一分钟，可以继续浏览" : "已经在刷新中", "info");
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
      <p>首次运行会下载默认自选股（国有六大行）及其同行业公司的历年财报、2018 年以来的估值和分红记录，大约半分钟到一分钟。完成后页面会自动刷新。</p>
      <div class="init-bar"><i style="width:${pct0}%"></i></div>
      <p class="muted">${s.done || 0} / ${s.total || "…"} ${s.current ? `· 正在获取：${esc(s.current)}` : ""}</p>
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

/** 可排序表格。排序循环：降序 → 升序 → 恢复默认；opt.foot 为固定在底部的汇总行；opt.sort / opt.onSort 用于记住排序；
 *  opt.group 分组时在组内排序；opt.empty 为没有行时的提示 */
function sortableTable(el, cols, rows, opt = {}) {
  let sort = opt.sort && cols.some((c) => c.key === opt.sort.key && c.val) ? opt.sort : null;
  const cmp = (a, b) => (a == null ? 1 : b == null ? -1 : a < b ? -1 : a > b ? 1 : 0);
  const cells = (r) => cols.map((c) => `<td class="${c.num ? "num" : ""}${c.cls ? ` ${c.cls}` : ""}">${c.fmt(r)}</td>`).join("");
  const gOrder = new Map();
  if (opt.group) rows.forEach((r) => { const g = opt.group(r); if (!gOrder.has(g)) gOrder.set(g, gOrder.size); });
  const draw = () => {
    let list = rows.slice();
    if (sort) {
      const c = cols.find((x) => x.key === sort.key);
      list.sort((a, b) => {
        const dg = opt.group ? gOrder.get(opt.group(a)) - gOrder.get(opt.group(b)) : 0;
        if (dg) return dg;
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
      if (opt.group) {
        const g = opt.group(r);
        if (g !== lastG) { body += `<tr class="group"><td colspan="${cols.length}">${esc(g)}</td></tr>`; lastG = g; }
      }
      body += `<tr class="${opt.rowClass?.(r) || ""}${opt.onRow ? " link" : ""}" data-code="${esc(r.code || "")}">${cells(r)}</tr>`;
    }
    if (!list.length && opt.empty) body = `<tr><td colspan="${cols.length}" class="empty">${opt.empty}</td></tr>`;
    const foot = opt.foot && list.length ? `<tfoot><tr class="total">${cells(opt.foot)}</tr></tfoot>` : "";
    const left = $(".table-wrap", el)?.scrollLeft || 0;
    el.innerHTML = `<div class="table-wrap"><table class="tbl ${opt.tblClass || ""}"><thead><tr>${head}</tr></thead><tbody>${body}</tbody>${foot}</table></div>`;
    $(".table-wrap", el).scrollLeft = left;
    $$("th.sortable", el).forEach((th) => th.onclick = () => {
      const k = th.dataset.k;
      sort = sort && sort.key === k ? (sort.dir < 0 ? { key: k, dir: 1 } : null) : { key: k, dir: -1 };
      opt.onSort?.(sort);
      draw();
    });
    if (opt.onRow) $$("tbody tr[data-code]", el).forEach((tr) => tr.onclick = (e) => {
      if (!e.target.closest(".term") && tr.dataset.code) opt.onRow(tr.dataset.code);
    });
  };
  draw();
}

/** 结论列表；linkable(s) 为真的渲染成可点的链接（点击切到对应指标走势），其余是普通文字 */
function signalList(list, linkable, empty = "暂无需要特别关注的信号。") {
  if (!list.length) return `<div class="empty">${empty}</div>`;
  return `<div class="signals">${list.map((s) => {
    const body = `<span class="lv">${LEVEL[s.level]}</span>
    <div class="sig-body"><div class="sig-title">${esc(s.title)}${s.cat ? ` <span class="cat">${esc(s.cat)}</span>` : ""}</div><div class="sig-text">${rich(s.text)}</div></div>`;
    return linkable(s) ? `<a class="signal lv-${s.level}" href="#trendCard" data-metric="${esc(s.metric)}">${body}<span class="sig-go">›</span></a>`
      : `<div class="signal lv-${s.level}">${body}</div>`;
  }).join("")}</div>`;
}

function pctBar(q, inverse) {
  if (q == null) return `<span class="muted">—</span>`;
  return `<span class="pbar"><span class="pbar-track${inverse ? " inv" : ""}"><i style="left:${(q * 100).toFixed(0)}%"></i></span>${Math.round(q * 100)}%</span>`;
}

/* ================= 自选股管理 ================= */

async function addWatch(code, name) {
  try {
    toast(`正在添加 ${name || code}…`, "info", 2500);
    const r = await send("/api/watchlist", "POST", { code });
    if (r.existed) toast(`${name || code} 已经在自选股里`, "info");
    else toast(`已添加 ${r.name || name || code}，正在下载同行业、估值和分红数据`, "ok", 5000);
    state.watchOrder = null;
    await refreshStatus();
    startPolling();
    render();
  } catch (e) {
    toast(`添加失败：${e.message}`, "warn", 6000);
  }
}

async function removeWatch(code, name) {
  const order = (state.watchOrder || []).map((x) => x.code);
  try {
    await send(`/api/watchlist/${code}`, "DELETE");
    toast(`已移除 ${name || code}`, "ok", 8000, { label: "撤销", fn: () => undoRemove(code, name, order) });
    state.watchOrder = null;
    render();
  } catch (e) {
    toast(`移除失败：${e.message}`, "warn");
  }
}

/** 撤销移除：加回自选股并放回原来的位置 */
async function undoRemove(code, name, order) {
  try {
    const r = await send("/api/watchlist", "POST", { code, undo: true });
    if (order.includes(code)) await send("/api/watchlist", "PUT", { codes: order });
    toast(`已恢复 ${name || code}`, "ok");
    state.watchOrder = null;
    if (r.refresh) { await refreshStatus(); startPolling(); }
    render();
  } catch (e) {
    toast(`恢复失败：${e.message}`, "warn");
  }
}

/** 搜索框：输入代码、名称或拼音，↑ ↓ 选择，回车或点击结果添加 */
function setupSearch(box) {
  const input = $("input", box), list = $(".sugg", box);
  let timer = null, results = [], resultsQ = null, active = 0, seq = 0;
  const show = (msg) => {
    if (msg != null) { list.innerHTML = `<div class="sugg-empty">${esc(msg)}</div>`; list.hidden = false; return; }
    list.hidden = !results.length;
    list.innerHTML = results.map((r, i) => `<div class="sugg-item${i === active ? " on" : ""}" data-i="${i}">
      <b>${esc(r.name)}</b><span class="muted">${esc(r.code)} · ${esc(r.market || "")}</span>
      ${r.watched ? `<span class="badge gray">已在自选</span>` : `<span class="badge blue">添加</span>`}</div>`).join("");
  };
  const clear = () => { results = []; resultsQ = null; active = 0; show(); };
  const pick = (r) => {
    if (!r) return;
    input.value = "";
    clear();
    if (!r.watched) addWatch(r.code, r.name);
    else location.hash = `#/stock/${r.code}`;
  };
  /** 搜索 q；期间又输入了别的内容就丢弃结果，返回 null */
  const search = async (q) => {
    clearTimeout(timer);
    const my = ++seq;
    try {
      const res = await api(`/api/search?q=${encodeURIComponent(q)}`);
      if (my !== seq) return null;
      results = res; resultsQ = q; active = 0;
      if (res.length) show(); else show("没有找到 A 股股票");
      return res;
    } catch (e) {
      if (my === seq) show(e.message);
      return null;
    }
  };
  const move = (step) => {
    if (!results.length) return;
    active = (active + step + results.length) % results.length;
    $$(".sugg-item", list).forEach((x, i) => x.classList.toggle("on", i === active));
    $$(".sugg-item", list)[active]?.scrollIntoView({ block: "nearest" });
  };
  input.addEventListener("input", () => {
    clearTimeout(timer);
    ++seq;
    const q = input.value.trim();
    if (!q) { clear(); return; }
    timer = setTimeout(() => search(q), 250);
  });
  input.addEventListener("keydown", async (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      move(e.key === "ArrowDown" ? 1 : -1);
    } else if (e.key === "Enter") {
      const q = input.value.trim();
      if (!q) return;
      // 结果必须对应当前输入：还在防抖或请求中时，先按当前内容搜完再选
      const res = resultsQ === q ? results : await search(q);
      if (res == null || input.value.trim() !== q) return;
      if (res.length) pick(res[active]);
      else if (/^\d{6}$/.test(q)) { input.value = ""; clear(); addWatch(q); }
    } else if (e.key === "Escape") { clear(); }
  });
  list.addEventListener("mousedown", (e) => {
    const it = e.target.closest(".sugg-item");
    if (it) { e.preventDefault(); pick(results[+it.dataset.i]); }
  });
  list.addEventListener("mousemove", (e) => {
    const it = e.target.closest(".sugg-item");
    if (it && +it.dataset.i !== active) move(+it.dataset.i - active);
  });
  input.addEventListener("blur", () => setTimeout(() => { list.hidden = true; }, 150));
  input.addEventListener("focus", () => { if (results.length) list.hidden = false; });
}

/** 自选股标签：拖动排序、× 移除；排序保存后调用 onReorder(codes) */
function setupChips(el, onReorder) {
  let dragging = null, before = "";
  el.addEventListener("click", (e) => {
    const b = e.target.closest("[data-del]");
    if (!b) return;
    e.preventDefault();
    const chip = b.closest(".wchip");
    removeWatch(chip.dataset.code, chip.dataset.name);
  });
  el.addEventListener("dragstart", (e) => {
    dragging = e.target.closest(".wchip");
    if (!dragging) return;
    dragging.classList.add("dragging");
    before = $$(".wchip", el).map((c) => c.dataset.code).join();
    e.dataTransfer.effectAllowed = "move";
  });
  el.addEventListener("dragover", (e) => {
    if (!dragging) return;
    e.preventDefault();
    const over = e.target.closest(".wchip");
    if (!over || over === dragging) return;
    const r = over.getBoundingClientRect();
    el.insertBefore(dragging, e.clientX > r.left + r.width / 2 ? over.nextSibling : over);
  });
  el.addEventListener("dragend", async () => {
    if (!dragging) return;
    dragging.classList.remove("dragging");
    dragging = null;
    const codes = $$(".wchip", el).map((c) => c.dataset.code);
    if (codes.join() === before) return;
    try {
      await send("/api/watchlist", "PUT", { codes });
      onReorder(codes);
    } catch (e) {
      toast(`排序保存失败：${e.message}`, "warn");
    }
  });
}

/* ================= 总览 ================= */

function stockCard(c) {
  const mk = c.market || {};
  const v = c.val?.[c.focus];
  const sub = c.sub || c.group?.name || "";
  const metrics = c.metrics.map((m) => {
    const note = isGrowth(m.key) ? (ok(m.prev) ? `上期 ${fmt(m.key, m.prev)}` : "")
      : (delta(m.key, m.value, m.ly) ? `同比 ${delta(m.key, m.value, m.ly)}` : "");
    const oo = m.key === "PARENTNETPROFITTZ" && c.oneoff;
    return `<div class="sm"><div class="sm-top"><small>${metricLabel(m.key)}</small>${oo ? oneoffTag(oo) : rankBadge(m.key, m.peer)}</div>
      <b>${fmtC(m.key, m.value)}</b><span>${esc(note)}</span></div>`;
  }).join("");
  const top = c.signals.filter((s) => s.level !== "info").slice(0, 3);
  return `<a class="scard" href="#/stock/${c.code}" data-code="${c.code}">
    <div class="scard-head">
      <div><b class="scard-name">${esc(c.name)}</b> <span class="muted small">${c.code}</span>
        <div class="small muted">${esc(sub)}${sub ? " · " : ""}${esc(c.type_name)} ${natureTag(c.nature)}</div></div>
      <div class="scard-px"><b>${ok(mk.close) ? mk.close.toFixed(2) : "—"}</b>${changeTxt(mk.change)}</div>
    </div>
    <div class="scard-period">最新财报 <b>${esc(c.period.name)}</b>${c.period.notice ? ` · ${shortDate(c.period.notice)} 披露` : ""}
      ${c.period.new ? `<span class="badge red">新</span>` : ""}
      ${c.next.due ? `<span class="muted">· ${esc(c.next.name)}截止 ${shortDate(c.next.deadline)}</span>` : ""}</div>
    <div class="scard-metrics">${metrics}</div>
    <div class="scard-val">
      <span>${termLabel(c.focus === "pb" ? "市净率" : "市盈率")} <b>${v ? v.cur.toFixed(2) : fmtAny(c.focus, mk[c.focus])}</b></span>
      ${v ? `<span title="${v.since.slice(0, 4)} 年以来的分位">${termLabel("分位")} ${pctBar(v.pct)}</span>` : ""}
      <span>${termLabel("股息率")} <b>${ok(mk.dy) ? `${mk.dy.toFixed(2)}%` : "—"}</b>${ok(c.div?.stats?.pct)
        ? ` <span class="muted small" title="近 5 年股息率分位：越高，相对分红股价越便宜">分位 ${Math.round(c.div.stats.pct * 100)}%</span>` : ""}</span>
      <span>市值 <b>${bigYi(mk.mcap, 0)}</b></span>
    </div>
    <div class="scard-sig">${top.length ? top.map((s) => `<div><span class="lvtag lv-${s.level}">${LEVEL[s.level]}</span>${esc(s.title)}</div>`).join("")
      : `<div class="muted">没有需要特别留意的变化</div>`}</div>
  </a>`;
}

const OV_KEY = "fr_overview_v1";
const ovPrefs = { view: "list", group: false, sort: null, ...JSON.parse(localStorage.getItem(OV_KEY) || "{}") };
const saveOvPrefs = () => localStorage.setItem(OV_KEY, JSON.stringify(ovPrefs));

const SIG_WEIGHT = { risk: 100, watch: 10, positive: -1 };

/** 列表视图：一只股票一行，通用的三个指标单独成列，按公司类型不同的三个指标合在一列 */
function renderWatchTable(el, cards) {
  const label0 = cards[0].metrics.slice(0, 3).map((m) => m.key);
  const sigOf = (c) => c.signals.filter((s) => s.level !== "info");
  const metricCol = (i) => ({
    key: `m${i}`, label: metricLabel(label0[i]), num: true,
    val: (c) => c.metrics[i]?.value,
    fmt: (c) => {
      const m = c.metrics[i];
      if (!m) return "—";
      const oo = m.key === "PARENTNETPROFITTZ" && c.oneoff;
      return `<b>${fmtC(m.key, m.value)}</b><div>${oo ? oneoffTag(oo) : rankBadge(m.key, m.peer, true)}</div>`;
    },
  });
  const cols = [
    { key: "name", label: "公司", val: (c) => c.name,
      fmt: (c) => `<div class="wl-name"><b>${esc(c.name)}</b> <span class="muted small">${c.code}</span></div>
        <div class="small muted">${esc(c.sub || c.group?.name || "")}${c.sub || c.group ? " · " : ""}${esc(c.type_name)} ${natureTag(c.nature)}</div>` },
    { key: "px", label: "股价", num: true, val: (c) => c.market?.change,
      fmt: (c) => `<b>${ok(c.market?.close) ? c.market.close.toFixed(2) : "—"}</b><div class="small">${changeTxt(c.market?.change)}</div>` },
    { key: "period", label: "最新财报", val: (c) => c.period.date,
      fmt: (c) => `${esc(c.period.name)}${c.period.new ? ` <span class="badge red">新</span>` : ""}
        <div class="small muted" title="${c.next.due ? `${esc(c.next.name)}法定截止日 ${c.next.deadline}` : ""}">${c.next.due ? `下期 ${shortDate(c.next.deadline)} 截止` : c.period.notice ? `${shortDate(c.period.notice)} 披露` : ""}</div>` },
    metricCol(0), metricCol(1), metricCol(2),
    { key: "special", label: "行业特色指标",
      fmt: (c) => `<div class="wl-sp">${c.metrics.slice(3).map((m) => `<span title="${esc(M(m.key).name)}"><small>${esc(M(m.key).short)}</small> ${fmt(m.key, m.value)}</span>`).join("")}</div>` },
    { key: "val", label: `估值 · ${termLabel("分位")}`, val: (c) => c.val?.[c.focus]?.pct,
      fmt: (c) => { const v = c.val?.[c.focus]; return `<span class="small muted">${c.focus === "pb" ? "PB" : "PE"}</span> <b>${v ? v.cur.toFixed(2) : fmtAny(c.focus, c.market?.[c.focus])}</b>
        ${v ? `<div>${pctBar(v.pct)}</div>` : ""}`; } },
    { key: "dy", label: `${termLabel("股息率")} · ${termLabel("分位", "股息率分位")}`, num: true, val: (c) => c.market?.dy,
      fmt: (c) => `<b>${fmtAny("dy", c.market?.dy)}</b>${ok(c.div?.stats?.pct) ? `<div>${dyPct(c.div)}</div>` : ""}` },
    { key: "mcap", label: "市值", num: true, val: (c) => c.market?.mcap, fmt: (c) => bigYi(c.market?.mcap, 0) },
    { key: "sig", label: "需要留意", val: (c) => sigOf(c).reduce((s, x) => s + SIG_WEIGHT[x.level], 0),
      fmt: (c) => { const s = sigOf(c); return s.length ? `<div class="wl-sig" title="${esc(s.map((x) => `${LEVEL[x.level]}：${x.title}`).join("\n"))}">
        ${s.slice(0, 2).map((x) => `<div><span class="lvtag lv-${x.level}">${LEVEL[x.level]}</span>${esc(x.title)}</div>`).join("")}
        ${s.length > 2 ? `<div class="muted small">还有 ${s.length - 2} 条</div>` : ""}</div>` : `<span class="muted small">无</span>`; } },
  ];
  let rows = cards;
  if (ovPrefs.group) {
    const order = [];
    cards.forEach((c) => { const g = c.group?.name || "未分类"; if (!order.includes(g)) order.push(g); });
    rows = order.flatMap((g) => cards.filter((c) => (c.group?.name || "未分类") === g));
  }
  sortableTable(el, cols, rows, {
    tblClass: "wl", sort: ovPrefs.sort,
    onSort: (s) => { ovPrefs.sort = s; saveOvPrefs(); },
    group: ovPrefs.group ? (c) => `${c.group?.name || "未分类"}${c.group ? ` · 申万${["", "一", "二", "三"][c.group.path.length]}级` : ""}` : null,
    onRow: (code) => { location.hash = `#/stock/${code}`; },
  });
}

const TREND = { up: "上升趋势", down: "下降趋势", range: "震荡" };
const trendTag = (t) => (t ? `<span class="trend t-${t.trend}" title="按 20 / 60 / 250 日均线判断（后复权收盘价）">${TREND[t.trend]}</span>` : "");
/** 技术面一行：趋势、相对年线、相对一年高低点、RSI */
const techLine = (t, full = false) => (t ? `${trendTag(t)} <span class="muted small">${termLabel("年线")} ${sgn(t.ma250, 1)}
  · 距一年高点 ${sgn(t.dd, 1)}${full ? ` · 距一年低点 ${sgn(t.up_low, 1)} · 20 日线 ${sgn(t.ma20, 1)} · 60 日线 ${sgn(t.ma60, 1)}
  · ${termLabel("RSI")} ${t.rsi.toFixed(0)}` : ""}</span>` : "");
const sigSide = (s) => (s.level === "positive" ? "chance" : (s.level === "risk" || s.level === "watch") && s.cat !== "披露" ? "risk" : null);

/** 个股页的“风险与机会”：综合判断、技术面，再把结论分成风险（风险 / 留意）、机会（积极）和其他提示三组 */
function riskOpp(c, linkable) {
  const risks = c.signals.filter((s) => sigSide(s) === "risk"), chances = c.signals.filter((s) => sigSide(s) === "chance");
  const rest = c.signals.filter((s) => !sigSide(s));
  const group = (title, cls, xs) => `<h3 class="ro-h ${cls}">${title} <span class="muted small">${xs.length}</span></h3>
    ${xs.length ? signalList(xs, linkable) : `<p class="muted small ro-none">无</p>`}`;
  return `${c.insight ? `<div class="al-insight ${c.insight.kind}"><b>${c.insight.kind === "risk" ? "综合：偏风险" : "综合：偏机会"}</b>${rich(c.insight.text)}</div>` : ""}
    ${c.tech ? `<p class="tech-line">技术面（${shortDate(c.tech.asof)}）：${techLine(c.tech, true)}</p>` : ""}
    ${group("风险", "risk", risks)}${group("机会", "chance", chances)}${rest.length ? group("其他提示", "", rest) : ""}
    <p class="muted small ro-note">按财报、估值、股息、股价和技术面的规则自动生成；技术面只用日收盘价（后复权），不含成交量。只提示值得留意的变化，不构成买卖建议。</p>`;
}

async function renderOverview(token) {
  const ov = await api("/api/overview");
  if (token !== state.token) return;
  state.watchOrder = ov.cards.map((c) => ({ code: c.code, name: c.name }));
  const h = ov.headline;
  const chips = ov.cards.map((c) => `<span class="wchip" draggable="true" data-code="${c.code}" data-name="${esc(c.name)}">
      <a href="#/stock/${c.code}" draggable="false">${esc(c.name)}</a><button data-del title="移除">×</button></span>`).join("")
    + ov.missing.map((c) => `<span class="wchip pending" draggable="true" data-code="${c}" data-name="${c}">
      ${c} <span class="muted small">获取中</span><button data-del title="移除">×</button></span>`).join("");
  app.innerHTML = `
    <section class="card">
      <div class="eyebrow">自选股财报速览 · 股价截至 ${esc(ov.trade_date || "—")}</div>
      <h1 class="headline">${rich(h.text)}</h1>
      ${h.bullets.length ? `<ul class="bullets">${h.bullets.map((b) => `<li>${rich(b)}</li>`).join("")}</ul>` : ""}
    </section>
    <section class="card">
      <div class="card-head"><h2>我的自选股 <span class="muted small">${ov.cards.length + ov.missing.length} 只</span></h2>
        <span class="muted small">拖动标签调整顺序 · 列表保存在本地数据库，每次启动服务自动更新它们的数据</span></div>
      <div class="watch-bar">
        <div class="search-box"><input type="text" placeholder="添加股票：输入代码、名称或拼音首字母，如 600519 / 茅台 / gzmt" autocomplete="off">
          <div class="sugg" hidden></div></div>
        <div class="wchips" id="chips">${chips || `<span class="muted small">还没有自选股</span>`}</div>
      </div>
    </section>
    ${ov.cards.length ? `
    <div class="view-bar">
      ${segButtons("view", [["list", "列表"], ["cards", "卡片"]], ovPrefs.view)}
      <label class="small view-opt" ${ovPrefs.view === "list" ? "" : "hidden"}><input type="checkbox" id="optGroup" ${ovPrefs.group ? "checked" : ""}> 按行业分组</label>
      <span class="muted small" id="viewHint"></span>
    </div>
    ${ovPrefs.view === "list" ? `<section class="card wl-card" id="wlTable"></section>` : `<section class="cards"></section>`}`
      : `<section class="card empty">在上方搜索框输入股票代码或名称，添加你想跟踪的公司。</section>`}
    <p class="muted small">数字都是最新一期财报的“报告期累计”口径；增速类看“上期”，比率类看“同比”（和上年同一报告期比）。
      排名是在申万同行业里的位置，<span class="badge ok">绿</span> 前 20%，<span class="badge amber">橙</span> 后 20%。</p>`;
  const drawList = () => {
    $("#viewHint").textContent = ovPrefs.view !== "list" ? "点卡片查看详情"
      : ovPrefs.group ? "点表头在每个行业内排序，点一行查看详情" : "点表头排序，点一行查看详情";
    if (ovPrefs.view === "list") renderWatchTable($("#wlTable"), ov.cards);
    else $(".cards").innerHTML = ov.cards.map(stockCard).join("");
  };
  setupSearch($(".search-box"));
  setupChips($("#chips"), (codes) => {
    ov.cards.sort((a, b) => codes.indexOf(a.code) - codes.indexOf(b.code));
    state.watchOrder = ov.cards.map((c) => ({ code: c.code, name: c.name }));
    if (ovPrefs.view === "list" && ovPrefs.sort) {
      ovPrefs.sort = null;
      saveOvPrefs();
      toast("已按拖动后的顺序显示（取消了表头排序）", "info");
    }
    if (ov.cards.length) drawList();
  });
  if (!ov.cards.length) return;
  drawList();
  onSeg(app, "view", (v) => { ovPrefs.view = v; saveOvPrefs(); render(); });
  $("#optGroup").onchange = (e) => { ovPrefs.group = e.target.checked; saveOvPrefs(); drawList(); };
}

/* ================= 横向对比 ================= */

/** 对比页的视图、图表指标、排序和每个范围的筛选：本标签页内记住，进详情再返回、后台刷新重绘后都不丢 */
const CMP_KEY = "fr_compare_v1";
const cmpPrefs = { col: "core", bar: "ROEJQ", sx: null, sy: "ROEJQ", sort: null, filters: {}, ...JSON.parse(sessionStorage.getItem(CMP_KEY) || "{}") };
const saveCmpPrefs = () => sessionStorage.setItem(CMP_KEY, JSON.stringify(cmpPrefs));

/** 图表没有可画的数据时，在中间显示一句说明 */
function chartEmpty(ch, text) {
  ch.setOption({ title: { text, left: "center", top: "middle", textStyle: { color: "#8b95a5", fontSize: 13, fontWeight: "normal" } } }, true);
}

async function renderCompare(token, scope = "watch", period) {
  const q = new URLSearchParams({ scope });
  if (period) q.set("period", period);
  const d = await api(`/api/compare?${q}`);
  if (token !== state.token) return;
  const g = d.group;
  const subColor = (s) => PALETTE[Math.max(0, d.subs.indexOf(s)) % PALETTE.length];
  const coreKeys = [...new Set(["TOTALOPERATEREVE", "TOTALOPERATEREVETZ", "PARENTNETPROFIT", "PARENTNETPROFITTZ", "KCFJCXSYJLR", "KCFJCXSYJLRTZ",
    ...d.types.flatMap((t) => state.meta.key_metrics[t])])].filter((k) => d.keys.includes(k));
  const focus = d.types.every((t) => state.meta.val_focus[t] === "pb") ? "pb" : "pe";
  const nats = Object.keys(state.meta.natures).filter((k) => d.rows.some((r) => r.nature?.cls === k));
  const perfKeys = state.meta.perf_periods.map((p) => p.key);
  const hasAll = d.keys.length > coreKeys.length;
  const saved = cmpPrefs.filters[d.scope] || {};
  let sub = d.subs.includes(saved.sub) ? saved.sub : "all";
  let nat = nats.includes(saved.nat) ? saved.nat : "all";
  let colSet = cmpPrefs.col === "all" && !hasAll ? "core" : cmpPrefs.col;
  const scopeChips = d.scopes.map((s) => `<a class="chip${s.key === d.scope ? " on" : ""}" href="#/compare/${s.key}"
      title="${s.mine ? `自选股：${esc(s.mine.join("、"))}` : ""}">${esc(s.name)} <span class="small">${s.n}</span></a>`).join("");
  const scopeNote = g
    ? `申万${["", "一", "二", "三"][g.level]}级行业「${esc(g.path.join(" › "))}」${g.total > d.total ? `共 ${g.total} 家，这里取市值最大的 ${d.total} 家（自选股始终保留）` : `共 ${d.total} 家`}。`
    : "你的全部自选股（可能跨行业，只比较各类公司共有的核心指标）。";
  app.innerHTML = `
    <div class="crumb"><a href="#/">总览</a> › 横向对比</div>
    <section class="card">
      <div class="card-head"><h2>对比范围</h2>
        <label class="small">报告期 <select id="period">${d.periods.map((p) => `<option value="${p.date}"${p.date === d.period ? " selected" : ""}>
          ${p.name}（${p.n}/${d.total} 家已披露）</option>`).join("")}</select></label></div>
      <div class="chips">${scopeChips}</div>
      <p class="muted small" style="margin:10px 0 0">${scopeNote}默认选择至少 70% 公司已披露的最新报告期。</p>
      ${d.subs.length > 1 ? `<div class="chips" id="subChips" style="margin-top:10px">
        <button class="chip" data-sub="all">全部 <span class="cnt"></span></button>
        ${d.subs.map((s) => `<button class="chip" data-sub="${esc(s)}"><i class="dotc" style="background:${subColor(s)}"></i>${esc(s)} <span class="cnt"></span></button>`).join("")}</div>` : ""}
      ${nats.length > 1 ? `<div class="chips" id="natChips" style="margin-top:10px">
        <span class="small muted chips-label">${termLabel("企业性质")}</span>
        <button class="chip" data-nat="all">全部 <span class="cnt"></span></button>
        ${nats.map((k) => `<button class="chip" data-nat="${k}">${esc(state.meta.natures[k])} <span class="cnt"></span></button>`).join("")}</div>` : ""}
    </section>
    <section class="card">
      <div class="card-head"><h2 id="cmpTitle"></h2>
        ${segButtons("cols", [["core", "核心指标"], ...(hasAll ? [["all", "全部指标"]] : []), ["perf", "股价表现"], ["div", "分红"]], colSet)}</div>
      <div id="cmpTable"></div>
      <p class="muted small" style="margin-top:8px" id="cmpNote"></p>
    </section>
    <section class="grid2">
      <div class="card"><div class="card-head"><h2>排名</h2><select id="barKey"></select></div><div id="barChart" class="chart"></div></div>
      <div class="card"><div class="card-head"><h2>散点</h2>
        <span class="small">横轴 <select id="sx"></select> 纵轴 <select id="sy"></select></span></div><div id="scatter" class="chart"></div>
        <p class="muted small" id="scNote"></p></div>
    </section>`;
  $("#period").onchange = (e) => { location.hash = `#/compare/${d.scope}/${e.target.value}`; };

  const opts = [...Object.keys(MARKET), ...Object.keys(DIV), ...perfKeys.map((k) => `r_${k}`), ...d.keys];
  const optHtml = (sel) => opts.map((k) => `<option value="${k}"${k === sel ? " selected" : ""}>${esc(labelAny(k))}</option>`).join("");
  const pickOpt = (k, dflt) => (opts.includes(k) ? k : dflt);
  $("#barKey").innerHTML = optHtml(pickOpt(cmpPrefs.bar, "ROEJQ"));
  $("#sx").innerHTML = optHtml(pickOpt(cmpPrefs.sx, focus));
  $("#sy").innerHTML = optHtml(pickOpt(cmpPrefs.sy, "ROEJQ"));
  const bar = makeChart($("#barChart")), sc = makeChart($("#scatter"));
  const inSub = (r) => sub === "all" || r.sub === sub, inNat = (r) => nat === "all" || r.nature?.cls === nat;
  const rowsNow = () => d.rows.filter((r) => inSub(r) && inNat(r));
  /** 筛选标签：高亮当前选择；数量按另一组筛选过滤后的结果，选了“地方国企”后各子行业显示的是其中地方国企的家数 */
  const syncChips = () => {
    $$("#subChips .chip").forEach((b) => {
      b.classList.toggle("on", b.dataset.sub === sub);
      const n = d.rows.filter((r) => inNat(r) && (b.dataset.sub === "all" || r.sub === b.dataset.sub)).length;
      $(".cnt", b).textContent = n;
      b.classList.toggle("zero", !n);
    });
    $$("#natChips .chip").forEach((b) => {
      b.classList.toggle("on", b.dataset.nat === nat);
      const n = d.rows.filter((r) => inSub(r) && (b.dataset.nat === "all" || r.nature?.cls === b.dataset.nat)).length;
      $(".cnt", b).textContent = n;
      b.classList.toggle("zero", !n);
    });
    cmpPrefs.filters[d.scope] = { sub, nat };
    saveCmpPrefs();
  };

  const drawTable = () => {
    const rows = rowsNow();
    const perf = colSet === "perf", div = colSet === "div";
    const keys = perf || div ? [] : colSet === "core" ? coreKeys : d.keys;
    const foot = { foot: true, name: "中位数", code: "", market: {}, values: {}, perf: {}, div: { stats: {}, summary: {} }, has: true };
    Object.keys(MARKET).forEach((k) => { foot.market[k] = median(rows.map((r) => r.market[k]).filter((v) => k !== "pe" || v > 0)); });
    keys.forEach((k) => { foot.values[k] = median(rows.filter((r) => r.has).map((r) => r.values[k])); });
    perfKeys.forEach((k) => { foot.perf[k] = { ret: median(rows.map((r) => r.perf[k]?.ret)) }; });
    ["pct", "spread"].forEach((k) => { foot.div.stats[k] = median(rows.map((r) => r.div?.stats?.[k])); });
    ["dps", "payout", "years", "cagr3"].forEach((k) => { foot.div.summary[k] = median(rows.map((r) => r.div?.summary?.[k])); });
    const bond = d.bond ? `10 年期国债收益率 ${d.bond.y10.toFixed(2)}%（${d.bond.date}）` : "";
    $("#cmpTitle").textContent = perf ? `区间涨跌幅${d.perf_asof ? `（截至 ${d.perf_asof}）` : ""}`
      : div ? `分红与股息率${bond ? ` · ${bond}` : ""}` : `${d.period_name || ""} 对比表`;
    $("#cmpNote").innerHTML = perf
      ? `★ 为自选股。涨跌幅按${termLabel("复权")}价计算（含现金分红和送转股，相当于分红再投入），即这段时间持有的总收益；悬停数字可看起算日、纯股价涨跌和年化。上市不足的区间显示“—”。`
      : div ? `★ 为自选股。${termLabel("股息率")}是最近四个季度每股派现 ÷ 最新股价；${termLabel("分位", "股息率分位")}是近 5 年里股息率不高于现在的交易日占比，越高说明相对分红股价越便宜；
        ${termLabel("股债利差")} = 股息率 − 10 年期国债收益率。每股分红、${termLabel("分红率")}、增速按最近一个完整财年（中期、三季度、年度分红合计，含已公告的预案）。`
      : "★ 为自选股。市值、市盈率、市净率、股息率是最新交易日的数据，其余是所选报告期的财报数据（报告期累计）。点击表头排序，点击行查看个股。";
    const dcol = (k, extra = {}) => ({ key: k, label: termLabel(DIV[k].label), num: true, val: (r) => getAny(r, k), fmt: (r) => fmtAny(k, getAny(r, k)), ...extra });
    const divCols = [
      { key: "dy", label: termLabel("股息率"), num: true, val: (r) => r.market.dy, fmt: (r) => `<b>${fmtAny("dy", r.market.dy)}</b>` },
      dcol("d_pct", { label: termLabel("近 5 年分位", "股息率分位"), fmt: (r) => dyPct(r.div) }),
      dcol("d_spread", { fmt: (r) => upDown(getAny(r, "d_spread")) }),
      dcol("d_dps", { title: "最近一个完整财年的每股税前派现", fmt: (r) => (r.foot ? fmtAny("d_dps", getAny(r, "d_dps"))
        : `${fmtAny("d_dps", getAny(r, "d_dps"))}${r.div?.summary?.year ? ` <span class="muted small">${r.div.summary.year}</span>` : ""}`) }),
      dcol("d_payout", { fmt: (r) => { const v = getAny(r, "d_payout"); return ok(v) && v > 100 ? `<span class="warn-text">${fmtAny("d_payout", v)}</span>` : fmtAny("d_payout", v); } }),
      dcol("d_years", { label: "连续分红", fmt: (r) => (ok(getAny(r, "d_years")) ? `${r.div?.summary?.more ? "≥" : ""}${Math.round(getAny(r, "d_years"))} 年` : "—") }),
      dcol("d_cagr3", { label: "每股分红 3 年增速", title: "最近一个完整财年相对 3 年前的年化增速", fmt: (r) => upDown(getAny(r, "d_cagr3"), sgn(getAny(r, "d_cagr3"), 1)) }),
    ];
    const cols = [
      { key: "name", label: "公司", val: (r) => r.name, fmt: (r) => (r.foot ? `<b>中位数</b> <span class="muted small">${rows.length} 家</span>`
        : `${r.watched ? `<span class="star">★</span>` : ""}<b>${esc(r.name)}</b> <span class="muted small">${r.code}</span>`) },
      ...(d.subs.length > 1 || !g ? [{ key: "sub", label: g ? "子行业" : "行业", val: (r) => (g ? r.sub : r.group?.name),
        fmt: (r) => (r.foot ? "" : g ? `<i class="dotc" style="background:${subColor(r.sub)}"></i>${esc(r.sub || "—")}` : esc(r.sub || r.group?.name || "—")) }] : []),
      { key: "nature", label: termLabel("性质", "企业性质"), val: (r) => (r.nature ? Object.keys(state.meta.natures).indexOf(r.nature.cls) : null),
        fmt: (r) => (r.foot ? "" : natureTag(r.nature) || `<span class="muted">—</span>`) },
      ...(perf || div ? [] : [{ key: "notice", label: "披露日", val: (r) => r.notice, fmt: (r) => (r.foot ? "" : r.has ? shortDate(r.notice) : `<span class="badge amber">未披露</span>`) }]),
      { key: "mcap", label: "市值", num: true, val: (r) => r.market.mcap, fmt: (r) => bigYi(r.market.mcap, 0) },
      ...(div ? divCols : perf ? perfKeys.map((k) => ({ key: `r_${k}`, label: perfLabel(`r_${k}`), num: true, val: (r) => r.perf[k]?.ret,
        fmt: (r) => (r.foot ? upDown(r.perf[k]?.ret) : perfCell(r.perf[k])) })) : [
        { key: "pe", label: termLabel("市盈率"), num: true, val: (r) => r.market.pe, fmt: (r) => fmtAny("pe", r.market.pe) },
        { key: "pb", label: termLabel("市净率"), num: true, val: (r) => r.market.pb, fmt: (r) => fmtAny("pb", r.market.pb) },
        { key: "dy", label: termLabel("股息率"), num: true, val: (r) => r.market.dy, fmt: (r) => fmtAny("dy", r.market.dy) },
        ...keys.map((k) => ({ key: k, label: metricLabel(k), title: `${M(k).name}${M(k).unit === "亿" ? "（亿元）" : ""}`, num: true,
          val: (r) => r.values[k], fmt: (r) => fmtC(k, r.values[k], false) }))]),
    ];
    sortableTable($("#cmpTable"), cols, rows, {
      foot, onRow: (c) => { location.hash = `#/stock/${c}`; },
      rowClass: (r) => `${r.watched ? "mine" : ""}${r.has || perf || div ? "" : " dim"}`, tblClass: "compact cmp",
      sort: cmpPrefs.sort, onSort: (s) => { cmpPrefs.sort = s; saveCmpPrefs(); },
      empty: `没有同时符合所选子行业和企业性质的公司。 <button class="btn" data-reset>清除筛选</button>`,
    });
  };

  const drawBar = () => {
    const k = $("#barKey").value;
    const list = rowsNow().filter((r) => ok(getAny(r, k)) && (k !== "pe" || getAny(r, k) > 0))
      .sort((a, b) => getAny(b, k) - getAny(a, k));
    if (!list.length) { chartEmpty(bar, rowsNow().length ? `这些公司都没有“${labelAny(k)}”数据` : "没有符合筛选条件的公司"); return; }
    const med = median(list.map((r) => getAny(r, k)));
    bar.setOption({
      grid: { left: 56, right: 16, top: 28, bottom: list.length > 8 ? 96 : 40 },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v) => fmtAny(k, v) },
      xAxis: { type: "category", data: list.map((r) => (r.watched ? `★${r.name}` : r.name)), ...AXIS_STYLE,
        axisLabel: { ...AXIS_STYLE.axisLabel, interval: 0, rotate: list.length > 8 ? 60 : 0,
          formatter: (v) => (v.startsWith("★") ? `{w|${v.slice(1)}}` : v), rich: { w: { color: "#2f6fdb", fontWeight: "bold", fontSize: 11 } } } },
      yAxis: { type: "value", scale: !isPerf(k) && !(k in MARKET) && !(k in DIV) && !M(k).flow && M(k).unit !== "亿", ...AXIS_STYLE },
      series: [{
        type: "bar", name: labelAny(k), barMaxWidth: 26,
        data: list.map((r) => ({ value: getAny(r, k), itemStyle: { color: r.watched ? "#2f6fdb" : (d.subs.length > 1 ? `${subColor(r.sub)}66` : "#c3cbd6") } })),
        markLine: med == null ? undefined : { symbol: "none", silent: true, lineStyle: { type: "dashed", color: "#8b95a5" },
          label: { formatter: `中位数 ${fmtAny(k, med)}`, color: "#6b7482", position: "insideEndTop" }, data: [{ yAxis: med }] },
      }],
    }, true);
  };

  const drawScatter = () => {
    const kx = $("#sx").value, ky = $("#sy").value;
    const valid = (r, k) => ok(getAny(r, k)) && (k !== "pe" || getAny(r, k) > 0);
    const all = rowsNow().filter((r) => valid(r, kx) && valid(r, ky));
    if (!all.length) {
      $("#scNote").textContent = "";
      chartEmpty(sc, rowsNow().length ? "这些公司没有同时具备这两项数据" : "没有符合筛选条件的公司");
      return;
    }
    const lx = robustRange(all.map((r) => getAny(r, kx))), ly = robustRange(all.map((r) => getAny(r, ky)));
    const inside = (v, l) => (l.min == null || v >= l.min) && (l.max == null || v <= l.max);
    const pts = all.filter((r) => inside(getAny(r, kx), lx) && inside(getAny(r, ky), ly));
    const hidden = all.filter((r) => !pts.includes(r));
    $("#scNote").textContent = hidden.length ? `极端值未显示：${hidden.map((r) => `${r.name}（${fmtAny(kx, getAny(r, kx))}，${fmtAny(ky, getAny(r, ky))}）`).join("、")}` : "";
    const groups = d.subs.length > 1 ? d.subs.filter((s) => pts.some((r) => r.sub === s)) : [null];
    sc.setOption({
      grid: { left: 56, right: 24, top: groups[0] ? 56 : 36, bottom: 44 },
      legend: groups[0] ? { top: 0, textStyle: { fontSize: 11 } } : undefined,
      tooltip: { formatter: (p) => `<b>${esc(p.data[2])}</b><br>${esc(labelAny(kx))}：${fmtAny(kx, p.data[0])}<br>${esc(labelAny(ky))}：${fmtAny(ky, p.data[1])}` },
      xAxis: { type: "value", scale: true, name: labelAny(kx), nameLocation: "middle", nameGap: 26, ...AXIS_STYLE },
      yAxis: { type: "value", scale: true, name: labelAny(ky), nameGap: 12, nameTextStyle: { align: "left", color: "#6b7482" }, ...AXIS_STYLE },
      series: groups.map((s) => ({
        type: "scatter", name: s || "公司", color: s ? subColor(s) : PALETTE[0],
        data: pts.filter((r) => !s || r.sub === s).map((r) => [getAny(r, kx), getAny(r, ky), r.name, r.code, r.watched]),
        symbolSize: (v) => (v[4] ? 14 : 9),
        itemStyle: { borderColor: "#fff", borderWidth: 1 },
        label: { show: true, position: "right", fontSize: 11, color: "#1f2733", formatter: (p) => (p.data[4] || pts.length <= 12 ? p.data[2] : "") },
        labelLayout: { hideOverlap: true },
      })),
    }, true);
  };
  sc.on("click", (p) => { if (p.data?.[3]) location.hash = `#/stock/${p.data[3]}`; });

  const drawAll = () => { syncChips(); drawTable(); drawBar(); drawScatter(); };
  drawAll();
  $("#barKey").onchange = () => { cmpPrefs.bar = $("#barKey").value; saveCmpPrefs(); drawBar(); };
  $("#sx").onchange = () => { cmpPrefs.sx = $("#sx").value; saveCmpPrefs(); drawScatter(); };
  $("#sy").onchange = () => { cmpPrefs.sy = $("#sy").value; saveCmpPrefs(); drawScatter(); };
  onSeg(app, "cols", (v) => {
    colSet = cmpPrefs.col = v;
    saveCmpPrefs();
    drawTable();
    if (v === "div" && !(DIV[$("#barKey").value] || $("#barKey").value === "dy")) { $("#barKey").value = "dy"; $("#barKey").onchange(); }
  });
  $("#subChips")?.addEventListener("click", (e) => {
    const b = e.target.closest("[data-sub]");
    if (!b) return;
    sub = b.dataset.sub;
    drawAll();
  });
  $("#natChips")?.addEventListener("click", (e) => {
    const b = e.target.closest("[data-nat]");
    if (!b) return;
    nat = b.dataset.nat;
    drawAll();
  });
  $("#cmpTable").addEventListener("click", (e) => {
    if (!e.target.closest("[data-reset]")) return;
    sub = nat = "all";
    drawAll();
  });
}

/* ================= 个股详情 ================= */

/** 详情页的“上一只 / 下一只”：按自选股顺序浏览，不用回到总览 */
function stockPager(code) {
  const list = state.watchOrder || [];
  const i = list.findIndex((x) => x.code === code);
  if (i < 0 || list.length < 2) return "";
  const p = list[(i - 1 + list.length) % list.length], n = list[(i + 1) % list.length];
  return `<span class="pager" title="键盘 ← → 也可以切换">
    <a class="btn" href="#/stock/${p.code}" data-pager="prev">‹ ${esc(p.name)}</a>
    <span class="muted small">自选股 ${i + 1} / ${list.length}</span>
    <a class="btn" href="#/stock/${n.code}" data-pager="next">${esc(n.name)} ›</a></span>`;
}

/** 个股页的区间涨跌幅：含分红（复权）、纯股价、年化，以及在同行业里的位置 */
function perfTable(p, g) {
  if (!p) return `<div class="empty">还没有股价数据，下次刷新数据时会自动下载。</div>`;
  const ps = p.periods;
  const dash = `<span class="muted">—</span>`;
  const row = (label, f) => `<tr><td class="fin-name">${label}</td>${ps.map((x) => `<td class="num">${f(x)}</td>`).join("")}</tr>`;
  const rank = (x) => {
    if (!x.rank) return dash;
    const cut = Math.max(1, Math.round(x.n * 0.2));
    return `<span class="badge ${x.rank <= cut ? "ok" : x.rank > x.n - cut ? "amber" : "gray"}">${x.rank}/${x.n}</span>`;
  };
  const diff = (x) => (ok(x.ret) && ok(x.median) ? upDown(x.ret - x.median, `${x.ret > x.median ? "+" : ""}${(x.ret - x.median).toFixed(2)}`) : dash);
  return `<div class="table-wrap"><table class="tbl compact perf"><thead><tr><th>区间</th>
      ${ps.map((x) => `<th class="num">${esc(x.label)}</th>`).join("")}</tr></thead><tbody>
    ${row("<b>涨跌幅（含分红）</b>", (x) => `<b>${perfCell(x)}</b>`)}
    ${row(`纯股价（${termLabel("不复权", "复权")}）`, (x) => upDown(x.raw))}
    ${row("年化", (x) => (ok(x.ann) ? upDown(x.ann) : dash))}
    ${g ? row(termLabel("同行业中位数"), (x) => upDown(x.median)) : ""}
    ${g ? row("相对中位数（百分点）", diff) : ""}
    ${g ? row("行业排名", rank) : ""}
  </tbody></table></div>
  <p class="muted small" style="margin-top:8px">起点是回看日当天或之前最近一个交易日的收盘价，“今年以来”从上年最后一个交易日算起；上市不足的区间显示“—”。
    ${g ? `同行业指${esc(g.name)}，排名按含分红涨跌幅从高到低。` : ""}</p>`;
}

/** 个股页分红摘要：股息率及其历史位置、股债利差、分红率、连续分红、每股分红增速、同行业位置 */
function divKpis(dv, mk, g) {
  const st = dv?.stats || {}, sm = dv?.summary || {}, peer = dv?.peer || {};
  const kv = (label, val, note = "") => `<div class="kv"><small>${label}</small><b>${val}</b>${note ? `<span>${note}</span>` : ""}</div>`;
  return `<div class="kv-row" style="margin-bottom:10px">
    ${kv(termLabel("股息率（TTM）", "股息率"), fmtAny("dy", mk.dy), ok(mk.dps) && mk.dps ? `最近四个季度每股 ${mk.dps.toFixed(3)} 元` : "近期没有现金分红")}
    ${kv(`${termLabel("分位", "股息率分位")}（${st.since ? `${st.since.slice(0, 4)} 年以来` : "近 5 年"}）`, dyPct(dv),
      ok(st.median) ? `中位数 ${st.median.toFixed(2)}% · 区间 ${st.low.toFixed(2)}%–${st.high.toFixed(2)}%` : "")}
    ${kv(termLabel("股债利差"), ok(st.spread) ? upDown(st.spread) : "—",
      ok(st.y10) ? `10 年期国债 ${st.y10.toFixed(2)}%${ok(st.spread_pct) ? ` · 利差处于 ${Math.round(st.spread_pct * 100)}% 分位` : ""}` : "")}
    ${kv(`${termLabel("分红率")}${sm.year ? `（${sm.year}）` : ""}`, ok(sm.payout) ? (sm.payout > 100 ? `<span class="warn-text">${sm.payout.toFixed(1)}%</span>` : `${sm.payout.toFixed(1)}%`) : "—",
      ok(sm.dps) ? `每股分红 ${sm.dps.toFixed(3)} 元 · 每股收益 ${ok(sm.eps) ? sm.eps.toFixed(3) : "—"} 元` : "")}
    ${kv("连续分红", ok(sm.years) ? `${sm.more ? "≥" : ""}${sm.years} 年` : "—",
      ok(sm.cagr3) ? `每股分红近 3 年年化 ${sgn(sm.cagr3, 1)}` : ok(sm.chg1) ? `每股分红同比 ${sgn(sm.chg1, 1)}` : "")}
    ${g ? kv("同行业股息率中位数", ok(peer.median) ? `${peer.median.toFixed(2)}%` : "—", peer.rank ? `${esc(g.name)}有分红的 ${peer.n} 家中排第 ${peer.rank}` : "") : ""}
  </div>`;
}

document.addEventListener("keydown", (e) => {
  if (!["ArrowLeft", "ArrowRight"].includes(e.key) || e.altKey || e.ctrlKey || e.metaKey) return;
  if (e.target.closest("input, select, textarea") || !$("#modal").hidden) return;
  const a = $(`.pager [data-pager="${e.key === "ArrowLeft" ? "prev" : "next"}"]`);
  if (a) { e.preventDefault(); location.hash = a.getAttribute("href"); }
});

async function renderStock(token, code) {
  const [d] = await Promise.all([
    api(`/api/stock/${encodeURIComponent(code)}`),
    state.watchOrder ? null : api("/api/overview").then((ov) => { state.watchOrder = ov.cards.map((c) => ({ code: c.code, name: c.name })); }).catch(() => null),
  ]);
  if (token !== state.token) return;
  const c = d.card, mk = c.market || {}, g = c.group;
  // 走势、估值、财务表的切换按股票记住（本次打开期间），后台刷新重绘或返回时不丢
  const ui = (state.stockUi ??= {})[c.code] ??= {};
  ui.val ??= c.focus;
  ui.fin ??= "all";
  const latest = d.dates[d.dates.length - 1];
  const ranks = d.ranks;
  const keyTiles = c.metrics.map((m) => {
    const note = isGrowth(m.key) ? (ok(m.prev) ? `上期 ${fmt(m.key, m.prev)}` : "")
      : (delta(m.key, m.value, m.ly) ? `比上年同期 ${delta(m.key, m.value, m.ly)}` : "");
    const oo = m.key === "PARENTNETPROFITTZ" && c.oneoff;
    return `<div class="metric"><small>${metricLabel(m.key, false)}</small><b>${fmtC(m.key, m.value)}</b>
      <span>${esc(note)}${oo ? ` · ${oneoffTag(oo)}` : ""}</span><span>${rankBadge(m.key, m.peer)}${m.peer ? ` <span class="muted">中位数 ${fmt(m.key, m.peer.median)}</span>` : ""}</span></div>`;
  }).join("");
  app.innerHTML = `
    <div class="crumb-row"><div class="crumb"><a href="#/">‹ 总览</a> › ${g ? `<a href="#/compare/${g.key}">${esc(g.name)}</a> › ` : ""}${esc(c.name)}</div>${stockPager(c.code)}</div>
    <section class="card stock-head">
      <div>
        <h1>${esc(c.name)} <small>${c.code} · ${esc(c.type_name)}</small></h1>
        <div class="small">${g ? `${termLabel("申万行业")}：${esc(g.path.join(" › "))}${c.sub && !g.path.includes(c.sub) ? ` · ${esc(c.sub)}` : ""}
          · <a href="#/compare/${g.key}">同行业 ${g.size} 家对比 ›</a>` : `<span class="muted">没有申万行业分类</span>`}</div>
        ${c.nature ? `<div class="small">${termLabel("企业性质")}：${natureTag(c.nature)} ${esc(c.nature.raw)}
          <span class="muted">· 控股股东 ${esc(c.nature.controller || "无")} · 实际控制人 ${esc(c.nature.real || "无")}</span></div>` : ""}
        <div class="small muted">最新财报 ${esc(c.period.name)}${c.period.notice ? `（${c.period.notice} 披露）` : ""}
          ${c.period.new ? `<span class="badge red">新</span>` : ""} · 下一期 ${esc(c.next.name)}，${termLabel("法定截止日")} ${c.next.deadline}</div>
      </div>
      <div class="stock-side">
        <div class="kv-row">
          <div class="kv"><small>股价 · ${shortDate(mk.trade_date)}</small><b>${ok(mk.close) ? mk.close.toFixed(2) : "—"}</b><span>${changeTxt(mk.change)}</span></div>
          <div class="kv"><small>总市值</small><b>${bigYi(mk.mcap, 0)}</b></div>
          <div class="kv"><small>${termLabel("市盈率")}</small><b>${fmtAny("pe", mk.pe)}</b></div>
          <div class="kv"><small>${termLabel("市净率")}</small><b>${fmtAny("pb", mk.pb)}</b></div>
          <div class="kv"><small>${termLabel("股息率")}</small><b>${fmtAny("dy", mk.dy)}</b>${ok(mk.dps) && mk.dps ? `<span>每股 ${mk.dps.toFixed(3)} 元</span>` : ""}</div>
        </div>
        <button class="btn ${c.watched ? "" : "primary"}" id="btnWatch">${c.watched ? "移出自选股" : "加入自选股"}</button>
      </div>
    </section>
    <section class="grid2">
      <div class="card"><div class="card-head"><h2>风险与机会</h2><span class="muted small">${esc(c.period.name)} · 点击查看对应指标走势</span></div>
        ${riskOpp(c, (s) => d.keys.includes(s.metric))}</div>
      <div class="card"><div class="card-head"><h2>核心指标</h2><span class="muted small">${esc(c.period.name)}${g ? ` · 排名范围：${esc(g.name)} ${g.size} 家` : ""}</span></div>
        <div class="metric-grid kgrid">${keyTiles}</div></div>
    </section>
    <section class="card">
      <div class="card-head"><h2>股价表现</h2><span class="muted small">${d.perf ? `截至 ${d.perf.asof} · 按${termLabel("复权")}价计算，含分红送转` : ""}</span></div>
      <div id="perfBox">${perfTable(d.perf, g)}</div>
    </section>
    <section class="card" id="trendCard">
      <div class="card-head"><h2>指标走势</h2>
        <div class="chart-tools"><select id="tKey">${d.keys.map((k) => `<option value="${k}">${esc(M(k).name)}</option>`).join("")}</select>
          <span id="tModeBox"></span>
          ${segButtons("range", [["5", "近 5 年"], ["10", "近 10 年"], ["all", "全部"]], ui.range || "5")}</div></div>
      <div id="trend" class="chart"></div>
      <p class="muted small" id="tNote"></p>
    </section>
    <section class="card">
      <div class="card-head"><h2>估值历史</h2>${segButtons("val", [["pb", "市净率"], ["pe", "市盈率"]], ui.val)}</div>
      <div id="valBox"></div>
    </section>
    <section class="card">
      <div class="card-head"><h2>财务数据</h2>${segButtons("fin", [["all", "最近 12 个报告期"], ["annual", "历年年报"]], ui.fin)}</div>
      <div id="finTable"></div>
      <p class="muted small" style="margin-top:8px">金额单位：亿元。利润表项目都是报告期累计。数据来自东方财富 F10「主要指标」。</p>
    </section>
    <section class="card" id="divCard">
      <div class="card-head"><h2>分红与股息率</h2>${g ? `<a class="go" href="#/compare/${g.key}">同行业分红对比 ›</a>` : ""}</div>
      ${divKpis(d.div, mk, g)}
      <div id="dyChart" class="chart short"></div>
      <p class="muted small">股息率按每个交易日当时已知的最近四个季度分红 ÷ 当天收盘价计算，新一期分红除息时会跳升、旧的一期移出时回落。
        ${termLabel("分位", "股息率分位")}越高，说明相对分红股价比过去多数时候便宜；两条线之间的距离就是${termLabel("股债利差")}。</p>
    </section>
    <section class="grid2">
      <div class="card"><div class="card-head"><h2>历年分红</h2><span class="muted small">按财年汇总：中期 + 三季度 + 年度</span></div><div id="annTable"></div></div>
      <div class="card"><div class="card-head"><h2>分红记录</h2><span class="muted small">每股税前派现</span></div><div id="divTable"></div></div>
    </section>
    <section class="card"><div class="card-head"><h2>同行业公司</h2>${g ? `<a class="go" href="#/compare/${g.key}">完整对比 ›</a>` : ""}</div>
      ${d.peers.length ? `<div class="peer-list">${d.peers.map((p) => `<a href="#/stock/${p.code}"><b>${esc(p.name)}</b>
        <span class="muted small">${esc(p.sub || "")} · ${bigYi(p.mcap, 0)}</span></a>`).join("")}</div>` : `<div class="empty">没有同行业数据</div>`}
    </section>`;

  $("#btnWatch").onclick = () => (c.watched ? removeWatch(c.code, c.name) : addWatch(c.code, c.name));

  // ---- 走势图 ----
  const trend = makeChart($("#trend"));
  let key = d.keys.includes(ui.key) ? ui.key : d.keys.includes("PARENTNETPROFIT") ? "PARENTNETPROFIT" : d.keys[0], mode = null, range = ui.range || "5";
  const modesOf = (k) => (M(k).flow ? [["q", "单季"], ["same", "历年同期"], ["annual", "年报"]]
    : CUM_RATIO.has(k) ? [["same", "历年同期"], ["annual", "年报"], ["all", "全部报告期"]]
      : [["all", "全部报告期"], ["same", "历年同期"], ["annual", "年报"]]);
  const setKey = (k, m) => {
    key = ui.key = k;
    $("#tKey").value = k;
    const modes = modesOf(k);
    mode = ui.mode = modes.some((x) => x[0] === m) ? m : modes[0][0];
    $("#tModeBox").innerHTML = segButtons("mode", modes, mode);
    onSeg($("#tModeBox"), "mode", (v) => { mode = ui.mode = v; drawTrend(); });
    drawTrend();
  };
  const drawTrend = () => {
    const m = M(key), s = d.series[key];
    let idx = d.dates.map((_, i) => i);
    if (mode === "annual") idx = idx.filter((i) => d.dates[i].endsWith("12-31"));
    else if (mode === "same") idx = idx.filter((i) => d.dates[i].slice(5) === latest.slice(5));
    if (range !== "all") {
      const from = `${+latest.slice(0, 4) - +range}${latest.slice(4)}`;
      idx = idx.filter((i) => d.dates[i] > from);
    }
    const vals = mode === "q" ? s.quarter : s.values;
    const asBar = m.flow || isGrowth(key);
    const series = [{
      name: c.name, type: asBar ? "bar" : "line", barMaxWidth: 26, symbolSize: 5,
      data: idx.map((i) => ({ value: vals?.[i] ?? null,
        itemStyle: isGrowth(key) ? { color: (vals?.[i] ?? 0) >= 0 ? "#d9363e" : "#18935a" } : undefined })),
      color: "#2f6fdb", lineStyle: { width: 2 },
    }];
    if (s.median && mode !== "q") {
      series.push({ name: "同行业中位数", type: "line", data: idx.map((i) => s.median[i]), color: "#8b95a5",
        lineStyle: { type: "dashed", width: 1.5 }, symbol: "circle", symbolSize: 4 });
    }
    const qName = (x) => `${x.slice(0, 4)}Q${{ "03-31": 1, "06-30": 2, "09-30": 3, "12-31": 4 }[x.slice(5)]}`;
    const rotate = idx.length > 14 ? 45 : 0;
    trend.setOption({
      grid: { left: 64, right: 20, top: 36, bottom: rotate ? 72 : 40 },
      legend: { top: 0, textStyle: { fontSize: 12 } },
      tooltip: { trigger: "axis", valueFormatter: (v) => fmt(key, v) },
      xAxis: { type: "category", data: idx.map((i) => (mode === "q" ? qName(d.dates[i]) : d.names[i])), ...AXIS_STYLE,
        axisLabel: { ...AXIS_STYLE.axisLabel, rotate } },
      yAxis: { type: "value", scale: !asBar, ...AXIS_STYLE,
        axisLabel: { ...AXIS_STYLE.axisLabel, formatter: (v) => (m.unit === "%" ? `${v}%` : m.unit === "亿" && Math.abs(v) >= 10000 ? `${v / 10000}万亿` : v) } },
      series,
    }, true);
    const notes = {
      q: "单季 = 本期累计 − 同年上一期累计（一季度就是一季报本身）。看最新一个季度有没有变化，比累计数更早发现拐点。",
      same: `只看每年的${PNAME[latest.slice(5)]}，同一报告期之间才可比。`,
      annual: "只看年报（全年数据）。",
      all: CUM_RATIO.has(key) ? "注意：这是报告期累计值，一季报约为全年的四分之一，不同季度之间不能直接比。" : "",
    };
    $("#tNote").textContent = `${notes[mode] || ""}${s.median && mode !== "q" ? ` 虚线是${g ? g.name : "同行业"}各公司同一报告期的中位数。` : ""}`;
  };
  $("#tKey").onchange = (e) => setKey(e.target.value);
  onSeg(app, "range", (v) => { range = ui.range = v; drawTrend(); });
  setKey(key, ui.mode);
  $$("a.signal", app).forEach((a) => a.addEventListener("click", (e) => {
    e.preventDefault();
    setKey(a.dataset.metric);
    $("#trendCard").scrollIntoView({ behavior: "smooth", block: "start" });
  }));

  // ---- 估值历史 ----
  let valCh = null;
  const drawVal = (vk) => {
    if (valCh) { valCh.dispose(); state.charts = state.charts.filter((x) => x !== valCh); valCh = null; }
    const box = $("#valBox");
    const rows = d.valuation.rows;
    const st = d.valuation.stats?.[vk];
    if (!rows.length) {
      box.innerHTML = `<div class="empty">${c.watched ? "估值历史还在下载中，稍后刷新页面。" : "估值历史只为自选股下载。加入自选股后会自动获取 2018 年以来的数据。"}</div>`;
      return;
    }
    const label = vk === "pb" ? "市净率" : "市盈率";
    box.innerHTML = `${st ? `<div class="kv-row" style="margin-bottom:8px">
        <div class="kv"><small>当前${label}</small><b>${st.cur.toFixed(2)}</b></div>
        <div class="kv"><small>${termLabel("分位", "估值分位")}（${st.since.slice(0, 4)} 年以来）</small><b>${pctBar(st.pct)}</b></div>
        <div class="kv"><small>中位数</small><b>${st.median.toFixed(2)}</b></div>
        <div class="kv"><small>最低 / 最高</small><b>${st.low.toFixed(2)} / ${st.high.toFixed(2)}</b></div></div>`
      : `<p class="muted small">${vk === "pe" ? "亏损期间市盈率没有意义，或" : ""}历史数据不足一年，无法计算分位。</p>`}
      <div id="valChart" class="chart short"></div>`;
    const ch = valCh = makeChart($("#valChart"));
    const i = vk === "pb" ? 3 : 2;
    ch.setOption({
      grid: { left: 52, right: 56, top: 28, bottom: 52 },
      legend: { top: 0, textStyle: { fontSize: 12 } },
      tooltip: { trigger: "axis", valueFormatter: (v) => (v == null ? "—" : Number(v).toFixed(2)) },
      dataZoom: [{ type: "inside" }, { type: "slider", height: 16, bottom: 6 }],
      xAxis: { type: "time", ...AXIS_STYLE },
      yAxis: [{ type: "value", scale: true, name: label, ...AXIS_STYLE }, { type: "value", scale: true, name: "股价", ...AXIS_STYLE, splitLine: { show: false } }],
      series: [
        { name: label, type: "line", showSymbol: false, color: "#2f6fdb", data: rows.map((r) => [r[0], r[i] > 0 ? r[i] : null]),
          areaStyle: { color: "rgba(47,111,219,.08)" },
          markLine: st ? { symbol: "none", silent: true, lineStyle: { type: "dashed", color: "#8b95a5" },
            label: { formatter: `中位数 ${st.median.toFixed(2)}`, color: "#6b7482", position: "insideEndTop" }, data: [{ yAxis: st.median }] } : undefined },
        { name: "股价（不复权）", type: "line", showSymbol: false, yAxisIndex: 1, color: "#c3cbd6", lineStyle: { width: 1 }, data: rows.map((r) => [r[0], r[1]]) },
      ],
    });
  };
  drawVal(ui.val);
  onSeg(app, "val", (v) => drawVal(ui.val = v));

  // ---- 财务数据表 ----
  const drawFin = (f) => {
    let idx = d.dates.map((_, i) => i).reverse();
    idx = f === "annual" ? idx.filter((i) => d.dates[i].endsWith("12-31")).slice(0, 10) : idx.slice(0, 12);
    let lastG = null, body = "";
    for (const k of d.keys) {
      const m = M(k);
      if (m.group !== lastG) { body += `<tr class="group"><td colspan="${idx.length + 1}">${esc(m.group)}</td></tr>`; lastG = m.group; }
      body += `<tr><td class="fin-name">${metricLabel(k, false)}</td>${idx.map((i) => `<td class="num">${fmtC(k, d.series[k].values[i], false)}</td>`).join("")}</tr>`;
    }
    $("#finTable").innerHTML = `<div class="table-wrap"><table class="tbl compact fin"><thead><tr><th>指标</th>
      ${idx.map((i) => `<th class="num">${esc(d.names[i])}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table></div>`;
  };
  drawFin(ui.fin);
  onSeg(app, "fin", (v) => drawFin(ui.fin = v));

  // ---- 分红 ----
  const dv = d.div || {};
  if (dv.series?.length) {
    const ch = makeChart($("#dyChart"));
    const med = dv.stats?.median;
    const pctFmt = (v) => (v == null ? "—" : `${Number(v).toFixed(2)}%`);
    ch.setOption({
      grid: { left: 52, right: 20, top: 28, bottom: 52 },
      legend: { top: 0, textStyle: { fontSize: 12 } },
      tooltip: { trigger: "axis", valueFormatter: pctFmt },
      dataZoom: [{ type: "inside" }, { type: "slider", height: 16, bottom: 6 }],
      xAxis: { type: "time", ...AXIS_STYLE },
      yAxis: { type: "value", ...AXIS_STYLE, axisLabel: { ...AXIS_STYLE.axisLabel, formatter: (v) => `${v}%` } },
      series: [
        { name: "股息率（TTM）", type: "line", showSymbol: false, color: "#d9363e", data: dv.series.map((r) => [r[0], r[1]]),
          areaStyle: { color: "rgba(217,54,62,.06)" },
          markLine: ok(med) ? { symbol: "none", silent: true, lineStyle: { type: "dashed", color: "#8b95a5" },
            label: { formatter: `中位数 ${med.toFixed(2)}%`, color: "#6b7482", position: "insideEndTop" }, data: [{ yAxis: med }] } : undefined },
        { name: "10 年期国债收益率", type: "line", showSymbol: false, color: "#8b95a5", lineStyle: { width: 1.5 }, data: dv.series.map((r) => [r[0], r[2]]) },
      ],
    });
  } else {
    $("#dyChart").outerHTML = `<div class="empty">还没有股价数据，下次刷新数据时会自动下载。</div>`;
  }
  const ann = (dv.annual || []).slice().reverse().filter((a) => a.done || a.dps).slice(0, 12);
  const prevDps = (a) => dv.annual.find((x) => +x.year === +a.year - 1)?.dps;
  sortableTable($("#annTable"), [
    { key: "year", label: "财年", fmt: (r) => `${r.year}${r.done ? "" : ` <span class="badge gray" title="年报还没出，只含已公告的中期 / 季度分红">进行中</span>`}
      ${r.plan ? ` <span class="badge amber" title="含董事会或股东大会已通过、尚未实施的分红预案">含预案</span>` : ""}` },
    { key: "dps", label: "每股分红", num: true, fmt: (r) => (r.dps ? `${r.dps.toFixed(4)} 元` : `<span class="muted">未分红</span>`) },
    { key: "chg", label: "同比", num: true, fmt: (r) => { const p = prevDps(r); return r.done && p && r.dps ? upDown((r.dps / p - 1) * 100, sgn((r.dps / p - 1) * 100, 1)) : "—"; } },
    { key: "eps", label: "基本每股收益", num: true, fmt: (r) => (ok(r.eps) ? `${r.eps.toFixed(3)} 元` : "—") },
    { key: "payout", label: termLabel("分红率"), num: true, fmt: (r) => (ok(r.payout) ? (r.payout > 100 ? `<span class="warn-text">${r.payout.toFixed(1)}%</span>` : `${r.payout.toFixed(1)}%`) : "—") },
  ], ann, { tblClass: "compact" });
  if (!ann.length) $("#annTable").innerHTML = `<div class="empty">没有分红数据</div>`;
  sortableTable($("#divTable"), [
    { key: "report", label: "所属报告期", fmt: (r) => esc(pname(r.report_date)) },
    { key: "dps", label: "每股派现", num: true, fmt: (r) => `${r.dps.toFixed(4)} 元` },
    { key: "ex", label: "除息日", fmt: (r) => esc(r.ex_date || "—") },
    { key: "yield", label: "当时股息率", num: true, title: "单次派现 ÷ 除息日收盘价", fmt: (r) => (ok(r.yield_at) ? `${r.yield_at.toFixed(2)}%` : "—") },
    { key: "progress", label: "进度", fmt: (r) => esc(r.progress || "—") },
  ], d.dividends.slice(0, 16), { tblClass: "compact" });
  if (!d.dividends.length) $("#divTable").innerHTML = `<div class="empty">没有现金分红记录</div>`;
}

/* ================= 数据健康 ================= */

async function renderHealth(token) {
  const h = await api("/api/health");
  if (token !== state.token) return;
  const bad = h.rows.filter((r) => r.ok === false);
  app.innerHTML = `
    <div class="crumb"><a href="#/">总览</a> › 数据健康</div>
    <section class="card stat-row four">
      <div class="stat"><small>跟踪的公司（自选 + 同行业）</small><b>${h.rows.length}</b></div>
      <div class="stat"><small>上次完整刷新</small><b>${esc(h.last_refresh || "—")}</b></div>
      <div class="stat"><small>股价 / 估值日期</small><b>${esc(h.trade_date || "—")}</b></div>
      <div class="stat"><small>上次刷新失败</small><b class="${h.failed.length ? "warn-text" : ""}">${h.failed.length} 项</b></div>
    </section>
    ${h.failed.length ? `<section class="card"><div class="card-head"><h2>上次刷新失败的项目</h2><span class="muted small">数据库里保留了之前的数据</span></div>
      <ul>${h.failed.map((f) => `<li class="small">${esc(f)}</li>`).join("")}</ul></section>` : ""}
    <section class="card">
      <div class="card-head"><h2>同行业分组</h2><span class="muted small">申万行业分类更新于 ${esc(h.sw_updated || "—")}，每周检查一次</span></div>
      <div id="gTable"></div>
    </section>
    <section class="card">
      <div class="card-head"><h2>各公司数据</h2>${segButtons("filter", [["all", "全部"], ["watch", "只看自选股"], ["issue", `只看有问题的 ${bad.length}`]], "all")}</div>
      <div id="hTable"></div>
      <p class="muted small" style="margin-top:8px">财报数据每次刷新都整段重下（东方财富会修订历史数据）；估值历史只为自选股增量下载；分红记录、企业性质、近 5 年日收盘价和复权因子覆盖全部跟踪的公司。
        10 年期国债收益率（算股债利差）每次刷新增量下载，最新一天：${esc(h.bond ? `${h.bond.date}，${h.bond.y10.toFixed(2)}%` : "暂无")}。</p>
    </section>`;
  sortableTable($("#gTable"), [
    { key: "name", label: "分组", fmt: (r) => esc(r.path.join(" › ")) },
    { key: "level", label: "级别", fmt: (r) => `申万${["", "一", "二", "三"][r.level]}级` },
    { key: "n", label: "纳入", num: true, fmt: (r) => `${r.n} 家` },
    { key: "total", label: "行业总数", num: true, fmt: (r) => (r.total ? `${r.total} 家` : "—") },
  ], h.groups, { tblClass: "compact" });
  const draw = (f) => sortableTable($("#hTable"), [
    { key: "name", label: "公司", val: (r) => r.name, fmt: (r) => `${r.watched ? `<span class="star">★</span>` : ""}${esc(r.name)} <span class="muted small">${r.code}</span>` },
    { key: "group", label: "分组", val: (r) => r.group, fmt: (r) => esc(r.group || "—") },
    { key: "type", label: "类型", val: (r) => r.type, fmt: (r) => esc(r.type) },
    { key: "nature", label: "企业性质", val: (r) => r.nature?.raw, fmt: (r) => (r.nature ? `${natureTag(r.nature)} <span class="muted small">${esc(r.nature.raw)}</span>` : `<span class="warn-text">无</span>`) },
    { key: "latest", label: "最新财报", val: (r) => r.latest, fmt: (r) => esc(r.latest_name || "—") },
    { key: "notice", label: "披露日", val: (r) => r.notice, fmt: (r) => esc(r.notice || "—") },
    { key: "periods", label: "报告期数", num: true, val: (r) => r.periods, fmt: (r) => r.periods },
    { key: "quote", label: "股价日期", val: (r) => r.quote, fmt: (r) => (r.quote === h.trade_date ? esc(r.quote) : `<span class="warn-text">${esc(r.quote || "无")}</span>`) },
    { key: "perf", label: "涨跌幅数据", title: "日收盘价与复权因子算出的区间涨跌幅截至哪天", val: (r) => r.perf,
      fmt: (r) => (r.perf === h.trade_date ? esc(r.perf) : `<span class="warn-text">${esc(r.perf || "无")}</span>`) },
    { key: "ok", label: "状态", val: (r) => (r.ok === false ? 0 : 1), fmt: (r) => (r.ok === false ? `<span class="badge red">失败</span> <span class="small">${esc(r.error || "")}</span>`
      : r.ok ? `<span class="badge ok">正常</span> <span class="muted small">${esc(r.at || "")}</span>` : `<span class="badge gray">未更新</span>`) },
  ], f === "issue" ? bad : f === "watch" ? h.rows.filter((r) => r.watched) : h.rows, { tblClass: "compact health", onRow: (c) => { location.hash = `#/stock/${c}`; } });
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
    <div class="gl-search"><input id="glq" placeholder="搜索术语，如 净息差、拨备、单季、分位…" autocomplete="off"></div>
    <section class="gl-grid">${state.glossary.map(card).join("")}</section>
    <div class="card empty" id="glEmpty" hidden>没有匹配的术语，换个关键词试试。</div>
    <p class="muted small">正文中带虚线下划线的词，鼠标悬停即可查看解释。</p>`;
  $("#glq").addEventListener("input", (e) => {
    const q = e.target.value.trim().toLowerCase();
    $$(".gl").forEach((el) => (el.hidden = q && !el.dataset.text.includes(q)));
    $("#glEmpty").hidden = $$(".gl").some((el) => !el.hidden);
  });
}

async function renderReports(token) {
  const list = await api("/api/reports");
  if (token !== state.token) return;
  app.innerHTML = `
    <div class="crumb"><a href="#/">总览</a> › 研究报告</div>
    <section class="card">
      <div class="card-head"><h2>研究报告</h2><span class="muted small">放在 reports/ 目录下的报告，最新的在前</span></div>
      ${list.length ? `<ul class="report-list">${list.map((n) => `<li><a href="/reports/${encodeURIComponent(n)}" target="_blank" rel="noopener">${esc(n.replace(/\.html$/, ""))}</a></li>`).join("")}</ul>`
        : `<div class="empty">还没有报告。</div>`}
    </section>`;
}

/* ================= 新手指引 ================= */

function guideSteps() {
  return [
    {
      title: "欢迎使用财报追踪台",
      body: `<p>它帮你盯住<b>自己关心的几家公司</b>：每次打开都能看到它们最新一期财报的关键数字、和同行比处在什么位置、有哪些值得留意的变化。</p>
        <p>默认已经放好了<b>国有六大行</b>（工、农、建、中、交、邮储），你可以随时增删任何 A 股公司——银行、保险、券商或一般企业都可以，指标会按公司类型自动切换。</p>`,
    },
    {
      title: "管理自选股",
      body: `<p>在总览页的搜索框输入<b>代码、名称或拼音首字母</b>（如 600519、茅台、gzmt），回车或点击结果即可添加。</p>
        <p>拖动标签可以调整顺序，点 × 移除。列表保存在本地数据库，<b>每次启动服务都会自动更新</b>这些公司及其同行业的数据。</p>
        <p>自选股默认以<b>列表</b>显示，一只一行、可排序、可按行业分组；也可以切换成卡片。详情页右上角可以直接切到上一只 / 下一只（键盘 ← →）。</p>`,
    },
    {
      title: "同行业对比",
      body: `<p>同行业按<b>申万行业分类</b>确定：一级行业不超过 60 家就整个一级一起比（比如银行 42 家，再按国有大行、股份行、城商行、农商行分组）；否则用更细的二级、三级行业。</p>
        <p>「横向对比」页可以切换范围和报告期，看对比表、排名图和散点图（比如市净率 vs ROE），中位数代表行业一般水平。</p>`,
    },
    {
      title: "自动结论与数据口径",
      body: `<p>结论分四级：<span class="lvtag lv-risk">风险</span> <span class="lvtag lv-watch">留意</span> <span class="lvtag lv-positive">积极</span> <span class="lvtag lv-info">提示</span>，比如利润增速转负、不良率上升、估值处于历史低位、新财报已披露等。</p>
        <p>A 股财报是<b>报告期累计</b>口径（中报 = 1–6 月），所以只和上年同期比；营收和利润可以拆成单季看趋势。带虚线的词悬停可以看解释。</p>`,
    },
  ];
}

function openGuide(step = 0) {
  const steps = guideSteps();
  const s = steps[step];
  const modal = $("#modal");
  if (modal.hidden) state.guideReturn = document.activeElement;
  modal.innerHTML = `<div class="modal-box" role="dialog" aria-modal="true" aria-labelledby="guideTitle">
    <div class="modal-step">${step + 1} / ${steps.length}</div>
    <h2 id="guideTitle">${s.title}</h2>
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
  $("[data-act=next]", modal).focus();
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
  state.guideReturn?.focus?.();
  state.guideReturn = null;
}

/** 指引打开时：Esc 关闭；Tab 只在弹窗里的按钮之间循环 */
document.addEventListener("keydown", (e) => {
  const modal = $("#modal");
  if (modal.hidden) return;
  if (e.key === "Escape") closeGuide();
  else if (e.key === "Tab") {
    const btns = $$("button", modal);
    const i = btns.indexOf(document.activeElement);
    e.preventDefault();
    btns[(i + (e.shiftKey ? -1 : 1) + btns.length) % btns.length].focus();
  }
});

/* ================= 路由与启动 ================= */

function renderNav(page) {
  const links = [["", "总览"], ["compare", "横向对比"], ["health", "数据健康"], ["glossary", "术语"], ["reports", "报告"]];
  const cur = page === "stock" ? "" : page || "";
  $("#nav").innerHTML = links.map(([h, t]) => `<a href="#/${h}" class="${h === cur ? "on" : ""}">${t}</a>`).join("");
}

/* 滚动位置：离开页面时按地址记下，回来时恢复。
   列表类页面（总览、对比等）无论怎么回来都恢复；个股详情只在浏览器前进 / 后退时恢复，点链接新打开的从顶部开始 */
const SCROLL_KEY = "fr_scroll_v1";
state.scroll = JSON.parse(sessionStorage.getItem(SCROLL_KEY) || "{}");
history.scrollRestoration = "manual";
function saveScroll(hash = location.hash || "#/") {
  state.scroll[hash] = window.scrollY;
  sessionStorage.setItem(SCROLL_KEY, JSON.stringify(state.scroll));
}
window.addEventListener("pagehide", () => saveScroll());

/** 从个股详情回到总览时，标出刚才看的那只 */
function flashReturned(code) {
  const el = code && $(`.scard[data-code="${code}"], tr[data-code="${code}"]`, app);
  if (!el) return;
  const r = el.getBoundingClientRect();
  if (r.top < 60 || r.bottom > window.innerHeight) el.scrollIntoView({ block: "center" });
  el.classList.add("flash");
  setTimeout(() => el.classList.remove("flash"), 2000);
}

async function render() {
  if (state.initMode) { renderInit(); return; }
  const token = ++state.token;
  disposeCharts();
  const hash = location.hash || "#/";
  const [page, a, b] = hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  renderNav(page);
  const prev = state.lastHash;
  const same = prev === hash;
  if (prev && !same) saveScroll(prev);
  const fromStock = prev && !same ? (prev.match(/^#\/stock\/(\w+)/) || [])[1] : null;
  const revisit = !!history.state?.fr;
  if (!revisit) history.replaceState({ ...history.state, fr: 1 }, "");
  state.lastHash = hash;
  const y = same ? window.scrollY : (revisit || page !== "stock") ? state.scroll[hash] || 0 : 0;
  app.innerHTML = `<div class="loading">加载中…</div>`;
  try {
    if (!page) await renderOverview(token);
    else if (page === "compare") await renderCompare(token, a, b);
    else if (page === "stock" && a) await renderStock(token, a);
    else if (page === "health") await renderHealth(token);
    else if (page === "glossary") await renderGlossary(token);
    else if (page === "reports") await renderReports(token);
    else location.replace("#/");
    if (token !== state.token) return;
    window.scrollTo(0, y);
    if (!page && fromStock) flashReturned(fromStock);
  } catch (e) {
    if (token !== state.token) return;
    if (e.status === 503) {
      state.initMode = true;
      await refreshStatus().catch(() => null);
      renderInit();
      if (state.status?.updating) startPolling();
      return;
    }
    // 服务返回的 4xx 是“没有这项数据”，只有连不上或服务出错才提示检查服务
    const notFound = e.status >= 400 && e.status < 500;
    if (!notFound) console.error(e);
    const canAdd = e.status === 404 && page === "stock" && /^\d{6}$/.test(a || "");
    app.innerHTML = `<div class="card error"><h2>${notFound ? "没有找到" : "加载失败"}</h2><p>${esc(e.message)}</p>
      ${notFound ? `<p class="err-act">${canAdd ? `<button class="btn primary" id="errAdd">把 ${esc(a)} 加入自选股</button>` : ""}<a class="btn" href="#/">返回总览</a></p>`
        : `<p class="muted">请确认服务正在运行（双击 scripts/start_server.bat），然后刷新页面。</p>`}</div>`;
    if (canAdd) $("#errAdd").onclick = () => addWatch(a);
  }
}

function setupToTop() {
  const btn = $("#toTop");
  const update = () => { btn.hidden = window.scrollY < 500; };
  window.addEventListener("scroll", update, { passive: true });
  btn.onclick = () => window.scrollTo({ top: 0, behavior: "smooth" });
  update();
}

/** 吸顶表头：表格的表头滚出窗口后，顶栏下方显示一份同列宽、同横向位置的表头；点它和点原表头一样排序 */
function stickyHead(wrap, table) {
  const thead = table.tHead;
  const head = document.createElement("div");
  head.className = "sticky-head";
  head.innerHTML = `<div class="sticky-head-in" hidden><table class="${table.className}"></table></div>`;
  const inner = head.firstChild, copy = inner.firstChild;
  copy.appendChild(thead.cloneNode(true));
  wrap.before(head);
  const src = [...thead.rows[0].cells], dst = [...copy.tHead.rows[0].cells];
  dst.forEach((th, i) => th.addEventListener("click", () => src[i].click()));
  const widths = () => {
    copy.style.width = `${table.offsetWidth}px`;
    src.forEach((th, i) => { const w = `${th.getBoundingClientRect().width}px`; Object.assign(dst[i].style, { width: w, minWidth: w, maxWidth: w }); });
  };
  const place = () => {
    const top = $(".topbar").offsetHeight;
    head.style.top = `${top}px`;
    const h = thead.getBoundingClientRect(), t = table.getBoundingClientRect();
    const show = h.top < top && t.bottom > top + h.height * 3;
    if (show && inner.hidden) widths();
    inner.hidden = !show;
    if (show) inner.scrollLeft = wrap.scrollLeft;
  };
  wrap.addEventListener("scroll", () => { if (!inner.hidden) inner.scrollLeft = wrap.scrollLeft; }, { passive: true });
  return { place, widths };
}

/** 页面上所有吸顶表头；随页面滚动统一更新，表格被重绘（排序、切换视图）后自动移除 */
const stickyHeads = new Set();
function placeStickyHeads() {
  stickyHeads.forEach((s) => (s.wrap.isConnected ? s.place() : stickyHeads.delete(s)));
}

/** 所有表格：放不下时横向滚动条吸附在窗口底部（原生滚动条隐藏，由代理滚动条同步），不用先滚到表格最下面才能左右拖；
 *  表头滚出窗口后吸顶 */
function enhanceTable(wrap) {
  wrap.dataset.hs = "1";
  const table = wrap.querySelector("table");
  const bar = document.createElement("div");
  bar.className = "hscroll";
  bar.innerHTML = "<i></i>";
  wrap.after(bar);
  const sync = (from, to) => () => { if (to.scrollLeft !== from.scrollLeft) to.scrollLeft = from.scrollLeft; };
  bar.addEventListener("scroll", sync(bar, wrap), { passive: true });
  wrap.addEventListener("scroll", sync(wrap, bar), { passive: true });
  const sh = table?.tHead ? { wrap, ...stickyHead(wrap, table) } : null;
  if (sh) { stickyHeads.add(sh); sh.place(); }
  const fit = () => {
    const over = wrap.scrollWidth > wrap.clientWidth + 1;
    wrap.classList.toggle("hs-on", over);
    bar.hidden = !over;
    bar.firstChild.style.width = `${wrap.scrollWidth}px`;
    bar.scrollLeft = wrap.scrollLeft;
    if (sh) { sh.widths(); sh.place(); }
  };
  fit();
  new ResizeObserver(fit).observe(wrap);
}

function setupTables() {
  new MutationObserver(() => $$(".table-wrap:not([data-hs])", app).forEach(enhanceTable))
    .observe(app, { childList: true, subtree: true });
  window.addEventListener("scroll", placeStickyHeads, { passive: true });
  window.addEventListener("resize", placeStickyHeads);
}

async function boot() {
  setupTooltip();
  setupToTop();
  setupTables();
  $("#btnRefresh").onclick = manualRefresh;
  $("#btnGuide").onclick = () => openGuide(0);
  try {
    const [meta, glossary] = await Promise.all([api("/api/meta"), api("/api/glossary")]);
    state.meta = meta;
    meta.metrics.forEach((m) => { state.mmap[m.key] = m; });
    state.glossary = glossary;
    buildTerms();
    await refreshStatus();
  } catch (e) {
    app.innerHTML = `<div class="card error"><h2>无法连接服务</h2><p>${esc(e.message)}</p>
      <p class="muted">请双击 scripts/start_server.bat 启动服务，并通过 http://127.0.0.1:8323 打开页面（不要直接双击 index.html）。</p></div>`;
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

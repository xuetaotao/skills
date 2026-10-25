"use strict";

/* ================= 基础工具 ================= */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const app = $("#app");

const state = {
  meta: null, glossary: [], termRe: null, termIndex: {},
  status: null, polling: null, charts: [], token: 0, initMode: false, list: null,
  sorts: {}, scrolls: {}, push: false,
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
const shortDate = (d) => (d ? d.slice(5) : "—");
const ok = (v) => v != null && isFinite(v);
const num = (v, d = 2) => (ok(v) ? Number(v).toLocaleString("zh-CN", { minimumFractionDigits: d, maximumFractionDigits: d }) : "—");
const DASH = `<span class="muted">—</span>`;
const signed = (v, d = 2, suf = "") => (ok(v)
  ? `<span class="${v > 0 ? "up" : v < 0 ? "down" : ""}">${v > 0 ? "+" : ""}${num(v, d)}${suf}</span>` : DASH);
const pctS = (v, d = 1) => (ok(v) ? signed(v * 100, d, "%") : DASH);

const CAT_COLOR = { "A股": "#2f6fdb", "港股": "#d64532", "海外": "#9c6ade", "债券": "#18935a", "商品": "#e0862f", "货币": "#8b95a5" };
const WIN_LABEL = { w1: "近1周", m1: "近1月", m3: "近3月" };
const catBadge = (c) => `<span class="badge gray"><span class="dotc" style="background:${CAT_COLOR[c] || "#999"}"></span>${esc(c)}</span>`;
/** 类型标签：宽基蓝、窄基（行业 / 主题）橙、策略紫，债券、商品、货币灰 */
const STYLE_CLASS = { "宽基": "blue", "行业": "amber", "主题": "amber", "策略": "purple" };
const styleTag = (s) => (s ? `<span class="badge ${STYLE_CLASS[s] || "gray"}"${STYLE_CLASS[s] === "amber" ? ` title="窄基：${s}"` : ""}>${esc(s)}</span>` : "");
const ANNUAL_YEARS = { y2: 2, y3: 3 };
const annualize = (r, years) => (ok(r) && r > -1 ? (1 + r) ** (1 / years) - 1 : null);
/** 区间收益单元格：两年及以上附年化 */
const retCell = (r, k) => (ok(r[`r_${k}`]) ? `${pctS(r[`r_${k}`])}${ANNUAL_YEARS[k] ? `<div class="small muted">年化 ${(annualize(r[`r_${k}`], ANNUAL_YEARS[k]) * 100).toFixed(1)}%</div>` : ""}` : DASH);
const median = (xs) => {
  const v = xs.filter(ok).sort((a, b) => a - b);
  if (!v.length) return null;
  const m = v.length >> 1;
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
};
/** 分位条：左低右高 */
const pctBar = (q, label = true) => (ok(q) ? `<span class="pbar"><span class="pbar-track"><i style="left:${(q * 100).toFixed(0)}%"></i></span>${label ? `${Math.round(q * 100)}%` : ""}</span>` : DASH);
const zoneTag = (q) => (!ok(q) ? "" : q <= 0.2 ? `<span class="badge ok">低位</span>` : q >= 0.8 ? `<span class="badge red">高位</span>` : "");

function toast(text, kind = "ok", ms = 4000) {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = text;
  $("#toasts").appendChild(el);
  setTimeout(() => el.classList.add("out"), ms);
  setTimeout(() => el.remove(), ms + 400);
}

const GUIDE_KEY = "etf_guide_v1";
const PREF_KEY = "etf_prefs_v1";
const prefs = { threshold: null, dedup: true, cat: "", kind: "", view: "scale", win: "w1", money: false, ...JSON.parse(localStorage.getItem(PREF_KEY) || "{}") };
const savePrefs = () => localStorage.setItem(PREF_KEY, JSON.stringify(prefs));

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
    pill.innerHTML = `<span class="spinner"></span>更新中 ${s.done}/${s.total || "…"}`;
    pill.className = "status-pill busy";
    pill.title = s.current ? `正在获取：${s.current}` : "";
    bar.hidden = false;
    $("i", bar).style.width = `${s.total ? (s.done / s.total) * 100 : 5}%`;
    btn.disabled = true;
  } else {
    pill.innerHTML = s.empty ? "暂无数据"
      : `<span class="dot ${s.failed ? "amber" : "ok"}"></span>份额截至 ${shortDate(s.snapshot_date)} · ${s.failed ? `${s.failed} 项有问题` : "全部正常"}`;
    pill.className = `status-pill${s.failed ? " warn" : ""}`;
    pill.title = `上次刷新：${s.last_refresh || "从未"}\n点击查看数据健康`;
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
    else toast("数据已更新到最新", "ok");
    state.initMode = false;
    state.list = null;
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
        <p>初始化没有成功获取到数据，可能是网络或交易所网站暂时不可用。</p>
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
      <p>首次运行会下载沪深两个交易所的全部 ETF 列表、份额和最新价格，从中证、国证官网补齐指数名称和类别，再取区间收益和宽基指数近 10 年的估值，大约一两分钟。完成后页面会自动刷新。</p>
      <div class="init-bar"><i style="width:${pct0}%"></i></div>
      <p class="muted">${s.done || 0} / ${s.total || "…"} ${s.current ? `· 正在获取：${esc(s.current)}` : ""}</p>
      ${s.last_error ? `<p class="warn-text">${esc(s.last_error)}</p>` : ""}
    </section>`;
}

/* ================= 图表与通用组件 ================= */

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

/** 可排序表格。排序循环：降序 → 升序 → 恢复默认。传入 opt.sortState（对象）可让排序在表格重绘（筛选、切换）后保留 */
function sortableTable(el, cols, rows, opt = {}) {
  const st = opt.sortState || {};
  let sort = st.v && cols.some((c) => c.key === st.v.key && c.val) ? st.v : null;
  const cmp = (a, b) => (a == null ? 1 : b == null ? -1 : a < b ? -1 : a > b ? 1 : 0);
  const cells = (r) => cols.map((c) => `<td class="${c.num ? "num" : ""}">${c.fmt(r)}</td>`).join("");
  const draw = () => {
    const list = rows.slice();
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
    const body = list.map((r) => `<tr class="${opt.rowClass?.(r) || ""}${opt.onRow ? " link" : ""}" data-code="${esc(r.code || "")}">${cells(r)}</tr>`).join("");
    const foot = opt.foot ? `<tfoot>${[].concat(opt.foot).map((f) => `<tr class="total">${cells(f)}</tr>`).join("")}</tfoot>` : "";
    const left = $(".table-wrap", el)?.scrollLeft || 0;
    el.innerHTML = `<div class="table-wrap"><table class="tbl ${opt.tblClass || ""}"><thead><tr>${head}</tr></thead><tbody>${body}</tbody>${foot}</table></div>`;
    $(".table-wrap", el).scrollLeft = left;
    $$("th.sortable", el).forEach((th) => th.onclick = () => {
      const k = th.dataset.k;
      sort = sort && sort.key === k ? (sort.dir < 0 ? { key: k, dir: 1 } : null) : { key: k, dir: -1 };
      st.v = sort;
      draw();
    });
    if (opt.onRow) $$("tbody tr[data-code]", el).forEach((tr) => tr.onclick = (e) => {
      if (!e.target.closest(".term, a") && tr.dataset.code) opt.onRow(tr.dataset.code);
    });
  };
  draw();
}

/** 页内跳转：标记为“前进”，新页面从顶部开始；浏览器后退 / 前进则恢复离开时的滚动位置 */
function nav(hash) {
  state.push = true;
  location.hash = hash;
}
const openEtf = (code) => nav(`#/etf/${code}`);

/* ================= 清单数据 ================= */

async function loadList() {
  if (!state.list) {
    const d = await api("/api/list");
    const groups = new Map();
    d.rows.forEach((r) => {
      const k = r.ik || `#${r.code}`;
      if (!groups.has(k)) groups.set(k, { members: [], total: 0 });
      const g = groups.get(k);
      r.rankInGroup = g.members.length + 1;
      g.members.push(r);
      g.total += r.scale || 0;
    });
    d.rows.forEach((r) => { r.group = groups.get(r.ik || `#${r.code}`); });
    d.groups = groups;
    state.list = d;
  }
  return state.list;
}

const idxText = (r) => (r.ik ? r.iname || r.ik : "无跟踪指数");
const detailHash = (r) => `#/etf/${r.code}`;
const guessMark = (r) => (r.guess ? `<span class="guess" title="交易所和中证、国证官网都查不到这个指数的名称，暂用 ETF 简称代替">*</span>` : "");

/** 当前门槛 / 去重下的候选（未按分类和搜索过滤） */
function candidates(d, threshold) {
  return d.rows.filter((r) => (r.scale || 0) >= threshold && (!prefs.dedup || r.rankInGroup === 1));
}

function matchQuery(r, q) {
  if (!q) return true;
  return [r.code, r.name, r.short, r.iname, r.ik, r.manager].some((x) => x && String(x).toLowerCase().includes(q));
}

function exportCsv(rows, win) {
  const periods = state.list.perf_periods;
  const head = ["代码", "名称", "交易所", "跟踪指数代码", "跟踪指数", "分类", "类型", "管理人", "规模(亿元)", "份额(亿份)", "价格", "成交额(亿元)",
    `${WIN_LABEL[win]}规模变化(亿元)`, `${WIN_LABEL[win]}净申赎(亿元)`, "同指数ETF数", "同指数合计规模(亿元)", "上市日期",
    ...periods.map(([, t]) => `${t}收益(%)`), "成立来收益(%)", "指数滚动市盈率", "市盈率分位(%)"];
  const cell = (v) => (v == null ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : v);
  const pct = (v) => (ok(v) ? (v * 100).toFixed(2) : null);
  const lines = rows.map((r) => [r.code, r.name, r.ex, r.ik || "", idxText(r), r.cat, r.style, r.manager, r.scale, r.shares, r.price, r.amount,
    r[`${win}_chg`], r[`${win}_flow`], r.group.members.length, r.group.total.toFixed(2), r.listed,
    ...periods.map(([k]) => pct(r[`r_${k}`])), pct(r.r_since), r.pe, pct(r.pe_pct)].map(cell).join(","));
  const blob = new Blob(["\ufeff" + [head.join(","), ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `ETF清单_${state.list.day}_${prefs.threshold}亿${prefs.dedup ? "_去重" : ""}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/* ================= 清单页 ================= */

async function renderList(token) {
  const d = await loadList();
  if (token !== state.token) return;
  if (!ok(prefs.threshold)) prefs.threshold = d.threshold;
  if (!d.windows[prefs.win]) prefs.win = "w1";
  if (!["scale", "perf", "val"].includes(prefs.view)) prefs.view = "scale";
  let q = "";
  app.innerHTML = `
    <section class="card filters">
      <div class="frow">
        <label class="fitem">${termLabel("规模")}不低于 <input type="number" id="thr" min="0" step="5" value="${prefs.threshold}"> 亿元</label>
        <span class="fitem">${termLabel("按指数去重", "去重")} ${segButtons("dedup", [["1", "每个指数只留最大的一只"], ["0", "显示全部"]], prefs.dedup ? "1" : "0")}</span>
        <span class="fitem">显示 ${segButtons("view", [["scale", "规模"], ["perf", "收益"], ["val", "估值"]], prefs.view)}</span>
        <span class="fitem" id="winBox">规模变化 ${segButtons("win", Object.keys(d.windows).map((w) => [w, WIN_LABEL[w]]), prefs.win)}</span>
        <span class="grow"></span>
        <button class="btn" id="btnCsv" title="导出当前筛选结果（含收益和估值），Excel 可直接打开">导出 CSV</button>
      </div>
      <div class="frow">
        <div class="chips" id="cats"></div>
        <span class="grow"></span>
        <label class="fitem qbox"><input type="text" class="q" id="q" placeholder="搜索代码、名称、指数或管理人" autocomplete="off"></label>
      </div>
      <div class="frow"><span class="chips-label">${termLabel("类型")}</span><div class="chips" id="kinds"></div></div>
    </section>
    <section class="card summary" id="summary"></section>
    <section class="card">
      <div class="card-head"><h2 id="listTitle"></h2><span class="muted small" id="listNote"></span></div>
      <div id="winNote"></div>
      <div id="table"></div>
    </section>`;

  const draw = () => {
    const base = candidates(d, prefs.threshold);
    // 分类和类型的数量互相按对方的筛选计算：选了“宽基”后，分类标签上是各分类里宽基的只数
    const byKind = base.filter((r) => !prefs.kind || r.kind === prefs.kind);
    const byCat = base.filter((r) => !prefs.cat || r.cat === prefs.cat);
    const counts = {}, kcounts = {};
    byKind.forEach((r) => { counts[r.cat] = (counts[r.cat] || 0) + 1; });
    byCat.forEach((r) => { kcounts[r.kind] = (kcounts[r.kind] || 0) + 1; });
    $("#cats").innerHTML = [["", "全部", byKind.length], ...d.categories.map((c) => [c, c, counts[c] || 0])].map(([v, t, n]) =>
      `<button class="chip${prefs.cat === v ? " on" : ""}${n ? "" : " zero"}" data-v="${v}">${v ? `<span class="dotc" style="background:${CAT_COLOR[v]}"></span>` : ""}${t}<small>${n}</small></button>`).join("");
    const kinds = d.kinds.filter((k) => kcounts[k] || k === prefs.kind);
    $("#kinds").innerHTML = [["", "全部", byCat.length], ...kinds.map((k) => [k, k, kcounts[k] || 0])].map(([v, t, n]) =>
      `<button class="chip${prefs.kind === v ? " on" : ""}${n ? "" : " zero"}" data-v="${v}" ${v === "窄基" ? `title="行业 + 主题"` : ""}>${t}<small>${n}</small></button>`).join("");
    const rows = base.filter((r) => (!prefs.cat || r.cat === prefs.cat) && (!prefs.kind || r.kind === prefs.kind) && matchQuery(r, q));
    rows.forEach((r, i) => { r.pos = i + 1; });
    drawSummary(d, base, rows);
    drawTable(d, rows);
    state.visible = rows;
  };

  const drawSummary = (d, base, rows) => {
    const total = rows.reduce((s, r) => s + (r.scale || 0), 0);
    const all = prefs.dedup ? null : d.rows.filter((r) => (r.scale || 0) >= prefs.threshold);
    const inFilter = (r) => (!prefs.cat || r.cat === prefs.cat) && (!prefs.kind || r.kind === prefs.kind);
    const near = d.rows.filter((r) => (!prefs.dedup || r.rankInGroup === 1) && inFilter(r)
      && r.scale >= prefs.threshold * 0.9 && r.scale < prefs.threshold * 1.1).length;
    const byCat = {};
    rows.forEach((r) => { byCat[r.cat] = (byCat[r.cat] || 0) + (r.scale || 0); });
    const cats = d.categories.filter((c) => byCat[c]);
    const dedupBefore = prefs.dedup ? d.rows.filter((r) => (r.scale || 0) >= prefs.threshold && inFilter(r)).length : null;
    $("#summary").innerHTML = `
      <div class="stat"><small>入选</small><b>${rows.length} 只</b><span class="muted small">${prefs.dedup ? `去重前 ${dedupBefore} 只` : `共 ${all.length} 只达到门槛`}</span></div>
      <div class="stat"><small>合计规模</small><b>${num(total, 0)} 亿</b><span class="muted small">份额截至 ${esc(d.day)}</span></div>
      <div class="stat"><small>最大的一只</small><b>${rows[0] ? num(rows[0].scale, 0) + " 亿" : "—"}</b><span class="muted small">${esc(rows[0]?.name || "")}</span></div>
      <div class="stat"><small>门槛上下 10% 内</small><b>${near} 只</b><span class="muted small">${num(prefs.threshold * 0.9, 0)}–${num(prefs.threshold * 1.1, 0)} 亿，门槛稍调就会进出</span></div>
      <div>
        <div class="catbar">${cats.map((c) => `<i style="width:${(byCat[c] / total) * 100}%;background:${CAT_COLOR[c]}" title="${c} ${num(byCat[c], 0)} 亿"></i>`).join("")}</div>
        <div class="catlegend">${cats.map((c) => `<span><span class="dotc" style="background:${CAT_COLOR[c]}"></span>${c} <b>${num(byCat[c], 0)}</b> 亿 · ${((byCat[c] / total) * 100).toFixed(0)}%</span>`).join("")}</div>
      </div>`;
  };

  const drawTable = (d, rows) => {
    const w = prefs.win, info = d.windows[w], view = prefs.view;
    $("#winBox").hidden = view !== "scale";
    $("#listTitle").textContent = `${prefs.cat || "全部"}${prefs.kind ? ` · ${prefs.kind}` : ""} ETF · 规模 ≥ ${prefs.threshold} 亿${prefs.dedup ? " · 按指数去重" : ""}`;
    $("#listNote").textContent = {
      scale: "规模 = 份额 × 最新价；点击一行查看同指数的全部 ETF",
      perf: `按复权净值计算，含分红；净值日期 ${d.nav_date || "—"}；底部是当前列表的中位数`,
      val: "跟踪指数的滚动市盈率在近 10 年里的分位；点击一行看估值走势",
    }[view];
    const valRows = rows.filter((r) => ok(r.pe)).length;
    $("#winNote").innerHTML = view === "scale" ? (info.base ? ""
      : `<p class="notice" style="margin-bottom:12px">${WIN_LABEL[w]}的变化需要一份 ${esc(info.days)} 天前或更早的${termLabel("快照")}，本地最早的快照是 ${esc(d.dates[0] || "—")}。
        每次启动服务或点“刷新数据”都会存一份当天快照，用上几天就能看到变化。</p>`)
      : view === "val" ? `<p class="notice" style="margin-bottom:12px">估值只覆盖 ${termLabel("宽基")}指数：A 股宽基取中证指数官网每日的滚动市盈率，
        创业板指、深证100 等深证系列取乐咕乐股的月末数据；港股、海外宽基（恒生指数、纳指100、标普500 等）没有找到公开的历史估值，暂缺。
        当前列表 ${rows.length} 只中有 ${valRows} 只有估值。${prefs.kind !== "宽基" ? ` <a href="#" id="onlyBroad">只看宽基 ›</a>` : ""}</p>` : "";
    $("#onlyBroad")?.addEventListener("click", (e) => { e.preventDefault(); prefs.kind = "宽基"; savePrefs(); draw(); });
    const base = info.base ? `（对比 ${shortDate(info.base)}）` : "";
    const head = [
      { key: "pos", label: "#", num: true, val: (r) => r.pos, fmt: (r) => (r.foot ? "" : `<span class="muted">${r.pos}</span>`) },
      { key: "name", label: "ETF", val: (r) => r.name, fmt: (r) => (r.foot ? `<b>中位数</b><small class="muted"> ${r.n} 只</small>`
        : `<span class="etf-name" title="${esc(r.name)}"><b>${esc(r.name)}</b><small>${r.code}</small></span>`) },
      { key: "idx", label: termLabel("跟踪指数"), val: (r) => idxText(r), fmt: (r) => (r.foot ? ""
        : `<span class="idx" title="${esc(idxText(r))} ${esc(r.ik || "")}">${esc(idxText(r))}${guessMark(r)}<small>${esc(r.ik || "")}</small></span>`) },
      { key: "cat", label: `分类 · ${termLabel("类型")}`, val: (r) => d.categories.indexOf(r.cat) * 100 + d.kinds.indexOf(r.kind),
        fmt: (r) => (r.foot ? "" : `${catBadge(r.cat)} ${styleTag(r.style)}`) },
    ];
    const scaleCol = { key: "scale", label: "规模（亿）", num: true, val: (r) => r.scale, fmt: (r) => (r.foot ? "" : `<b>${num(r.scale)}</b>`) };
    const cols = {
      scale: () => [
        { key: "mgr", label: "管理人", val: (r) => r.manager, fmt: (r) => esc(r.manager || "—") },
        scaleCol,
        { key: "shares", label: `${termLabel("份额")}（亿份）`, num: true, val: (r) => r.shares, fmt: (r) => num(r.shares) },
        { key: "amount", label: "成交额（亿）", num: true, val: (r) => r.amount, fmt: (r) => num(r.amount) },
        ...(info.base ? [
          { key: "chg", label: `${WIN_LABEL[w]}规模变化`, title: `规模变化${base}，包含价格涨跌和资金进出`, num: true, val: (r) => r[`${w}_chg`],
            fmt: (r) => (ok(r[`${w}_chg`]) ? `${signed(r[`${w}_chg`])} <span class="small">${pctS(r[`${w}_pct`])}</span>` : DASH) },
          { key: "flow", label: `${WIN_LABEL[w]}${termLabel("净申赎")}`, title: `净申赎${base} = 份额变化 × 最新价，正数为净流入`, num: true, val: (r) => r[`${w}_flow`], fmt: (r) => signed(r[`${w}_flow`]) },
        ] : []),
        { key: "grp", label: termLabel("同指数"), num: true, val: (r) => r.group.members.length,
          fmt: (r) => (r.group.members.length < 2 ? DASH : prefs.dedup
            ? `<span class="grp">${r.group.members.length} 只 · 合计 ${num(r.group.total, 0)} 亿</span>`
            : `<span class="grp">第 ${r.rankInGroup} / ${r.group.members.length}</span>`) },
      ],
      perf: () => [
        scaleCol,
        ...d.perf_periods.map(([k, t]) => ({ key: `r_${k}`, label: k === "w1" ? termLabel(t, "区间收益") : t, num: true, val: (r) => r[`r_${k}`], fmt: (r) => retCell(r, k) })),
        { key: "r_since", label: "成立来", num: true, val: (r) => r.r_since,
          fmt: (r) => (r.foot ? "" : ok(r.r_since) ? `${pctS(r.r_since)}<div class="small muted" title="成立日期 ${esc(r.inception || "")}">${esc((r.inception || "").slice(0, 7))} 起</div>` : DASH) },
      ],
      val: () => {
        const v = (r) => d.vals[r.ik];
        return [
          scaleCol,
          { key: "pe", label: termLabel("滚动市盈率", "市盈率"), num: true, val: (r) => r.pe, fmt: (r) => (ok(r.pe) ? `<b>${num(r.pe)}</b>` : DASH) },
          { key: "pct", label: termLabel("估值分位"), num: true, val: (r) => r.pe_pct, fmt: (r) => (ok(r.pe_pct) ? `${pctBar(r.pe_pct)} ${zoneTag(r.pe_pct)}`
            : ok(r.pe) ? `<span class="muted small">历史不足 1 年</span>` : DASH) },
          { key: "med", label: "中位数", num: true, val: (r) => v(r)?.median, fmt: (r) => (v(r) ? num(v(r).median) : DASH) },
          { key: "band", label: "20%–80% 分位", num: true, fmt: (r) => (v(r) ? `${num(v(r).p20)}–${num(v(r).p80)}` : DASH) },
          { key: "range", label: "最低–最高", num: true, fmt: (r) => (v(r) ? `${num(v(r).lo)}–${num(v(r).hi)}` : DASH) },
          { key: "since", label: "统计区间", val: (r) => v(r)?.since,
            fmt: (r) => (v(r) ? `${v(r).years} 年<div class="muted small">${esc(v(r).since.slice(0, 7))} 起 · ${esc(v(r).freq)}</div>` : DASH) },
        ];
      },
    }[view]();
    let foot = null;
    if (view === "perf" && rows.length > 1) {
      foot = { foot: true, n: rows.length };
      d.perf_periods.forEach(([k]) => { foot[`r_${k}`] = median(rows.map((r) => r[`r_${k}`])); });
    }
    sortableTable($("#table"), [...head, ...cols], rows, { tblClass: `etf compact v-${view}`, foot, onRow: openEtf, sortState: (state.sorts[`list.${view}`] ??= {}) });
    if (!rows.length) $("#table").innerHTML = `<div class="empty">没有符合条件的 ETF。可以调低门槛、换个分类或类型，或清空搜索。</div>`;
  };

  let tm = null;
  $("#thr").addEventListener("input", (e) => {
    clearTimeout(tm);
    tm = setTimeout(() => {
      const v = parseFloat(e.target.value);
      if (!ok(v) || v < 0) return;
      prefs.threshold = v;
      savePrefs();
      draw();
    }, 250);
  });
  onSeg(app, "dedup", (v) => { prefs.dedup = v === "1"; savePrefs(); draw(); });
  onSeg(app, "view", (v) => { prefs.view = v; savePrefs(); draw(); });
  onSeg(app, "win", (v) => { prefs.win = v; savePrefs(); draw(); });
  const chipFilter = (box, key) => $(box).addEventListener("click", (e) => {
    const b = e.target.closest(".chip");
    if (!b) return;
    prefs[key] = b.dataset.v;
    savePrefs();
    draw();
  });
  chipFilter("#cats", "cat");
  chipFilter("#kinds", "kind");
  $("#q").addEventListener("input", (e) => { q = e.target.value.trim().toLowerCase(); draw(); });
  $("#btnCsv").onclick = () => exportCsv(state.visible || [], prefs.win);
  draw();
}

/* ================= 指数 / ETF 详情 ================= */

async function renderDetail(token, code) {
  const [g, d] = await Promise.all([api(`/api/etf/${encodeURIComponent(code)}`), loadList()]);
  if (token !== state.token) return;
  const w = prefs.win, info = g.windows[w];
  const top = g.members[0];
  const focus = g.members.find((m) => m.code === g.focus);
  const sumBy = (k) => (g.members.some((m) => ok(m[k])) ? g.members.reduce((s, m) => s + (m[k] || 0), 0) : null);
  const flow = sumBy(`${w}_flow`), chg = sumBy(`${w}_chg`);
  const ps = g.perf_periods, peer = g.peer;
  const hasPerf = g.members.some((m) => ps.some(([k]) => ok(m[`r_${k}`])));
  const dview = hasPerf && prefs.view === "perf" ? "perf" : "scale";
  const multi = g.key && g.members.length > 1;
  const note = dview === "perf"
    ? `同类 = ${esc(peer.label)}的 ${peer.n} 个指数，每个指数取规模最大的一只 ETF 比较，排名从高到低；同类排名是本组规模最大的${esc(top.name)}的名次。
      ${multi ? "同一指数的 ETF 收益差别主要来自费率和跟踪误差。" : ""}净值收益和场内价格涨跌之间还差一个折溢价。`
    : multi ? "同一指数的 ETF 持仓几乎一样，通常选规模最大、成交最活跃的一只即可；费率可在基金公司官网或天天基金查询。" : "";
  app.innerHTML = `
    <div class="crumb"><a href="#/">清单</a> › ${esc(g.key ? g.name : focus.name)}</div>
    <section class="card">
      <div class="head-row">
        <div>
          <h1>${esc(g.key ? g.name : focus.name)}${guessMark(top)}<small>${esc(g.key || focus.code)}</small></h1>
          <div>${catBadge(g.cat)} ${styleTag(g.style)} <span class="muted small">${g.key ? `跟踪这个指数的 ETF 共 ${g.members.length} 只` : "货币 ETF，没有跟踪指数"}</span></div>
        </div>
        <div class="kv-row">
          <div class="kv"><small>合计规模</small><b>${num(g.total)} 亿</b><span>份额截至 ${esc(d.day)}</span></div>
          ${g.key ? `<div class="kv"><small>规模最大</small><b>${esc(top.name)}</b><span>${num(top.scale)} 亿 · 占 ${((top.scale / g.total) * 100).toFixed(0)}%</span></div>` : ""}
          ${ok(top.r_y1) ? `<div class="kv"><small>近1年收益</small><b>${pctS(top.r_y1)}</b><span>${g.peer.rank?.y1 ? `${esc(g.peer.label)} 第 ${g.peer.rank.y1[0]} / ${g.peer.rank.y1[1]}` : "&nbsp;"}</span></div>` : ""}
          ${g.val ? `<div class="kv"><small>${termLabel("滚动市盈率", "市盈率")}</small><b>${num(g.val.cur)}</b>
            <span>${ok(g.val.pct) ? `近 ${g.val.years} 年 ${Math.round(g.val.pct * 100)}% 分位` : "历史不足 1 年"}</span></div>` : ""}
          <div class="kv"><small>${WIN_LABEL[w]}${termLabel("净申赎")}</small><b>${signed(flow)}${ok(flow) ? " 亿" : ""}</b><span>${info.base ? `对比 ${esc(info.base)}` : "快照不足，暂无"}</span></div>
          <div class="kv"><small>${WIN_LABEL[w]}规模变化</small><b>${signed(chg)}${ok(chg) ? " 亿" : ""}</b><span>${ok(chg) && ok(flow) ? `其中价格涨跌约 ${num(chg - flow)} 亿` : "&nbsp;"}</span></div>
        </div>
      </div>
      ${top.guess ? `<p class="notice" style="margin-top:12px">交易所和中证、国证官网都查不到代码 ${esc(g.key)} 的指数名称（多为境外指数），上面的名称取自 ETF 简称。</p>` : ""}
    </section>
    <section class="card">
      <div class="card-head"><h2>${g.key ? "同指数 ETF" : "ETF 信息"}</h2><span class="chart-tools">
        ${hasPerf ? segButtons("dview", [["scale", "规模"], ["perf", "收益"]], dview) : ""}
        ${dview === "perf" ? `<span class="muted small">${termLabel("区间收益")}按复权净值计算，含分红 · 净值日期 ${esc(g.nav_date || "—")}</span>`
          : `规模变化 ${segButtons("win", Object.keys(g.windows).map((x) => [x, WIN_LABEL[x]]), w)}`}</span></div>
      <div id="mTable"></div>
      ${note ? `<p class="muted small" style="margin-top:8px">${note}</p>` : ""}
      ${!hasPerf && g.cat === "货币" ? `<p class="muted small" style="margin-top:8px">货币 ETF 不在东方财富的场内基金排行里，没有区间收益。</p>` : ""}
    </section>
    ${g.val || (g.style === "宽基" && ["A股", "港股", "海外"].includes(g.cat)) ? `<section class="card">
      <div class="card-head"><h2>${termLabel("估值分位")}</h2><span class="muted small">${g.val ? `${esc(g.val.src)} · ${esc(g.val.freq)}数据 · 截至 ${esc(g.val.asof)}` : ""}</span></div>
      <div id="valBox"></div>
    </section>` : ""}
    <section class="grid2">
      ${g.members.length > 1 ? `<div class="card"><div class="card-head"><h2>规模对比</h2><span class="muted small">亿元</span></div><div id="cBar" class="chart short"></div></div>` : ""}
      <div class="card"${g.members.length > 1 ? "" : ` style="grid-column:1/-1"`}><div class="card-head"><h2>规模走势</h2><span class="muted small">来自本地每日快照</span></div>
        ${g.history.length >= 2 ? `<div id="cHist" class="chart short"></div>`
          : `<p class="notice">目前只有 ${g.history.length} 份快照（${esc(g.history.map((h) => h[0]).join("、") || "无")}）。交易所只公布当天份额、不提供历史，走势要靠每次刷新积累，用上几天就能看到。</p>`}
      </div>
    </section>`;

  const head = [
    { key: "rank", label: "#", num: true, val: (r) => g.members.indexOf(r), fmt: (r) => (r.foot ? "" : `<span class="muted">${g.members.indexOf(r) + 1}</span>`) },
    { key: "name", label: "ETF", val: (r) => r.name, fmt: (r) => (r.foot === "med" ? `<b>同类中位数</b><small class="muted"> ${esc(peer.label)} · ${peer.n} 个指数</small>`
      : r.foot === "rank" ? `<b>同类排名</b>`
      : `<span class="etf-name"><b>${esc(r.name)}</b><small>${r.code} · ${r.ex === "SH" ? "上交所" : "深交所"}</small></span>`) },
  ];
  const perfCols = [
    { key: "scale", label: "规模（亿）", num: true, val: (r) => r.scale, fmt: (r) => (r.foot ? "" : num(r.scale)) },
    ...ps.map(([k, t]) => ({ key: `r_${k}`, label: t, num: true, val: (r) => r[`r_${k}`],
      fmt: (r) => (r.foot === "rank" ? (peer.rank[k] ? `第 ${peer.rank[k][0]} / ${peer.rank[k][1]}` : DASH) : retCell(r, k)) })),
    { key: "r_since", label: "成立来", num: true, val: (r) => r.r_since,
      fmt: (r) => (r.foot ? "" : ok(r.r_since) ? `${pctS(r.r_since)}<div class="small muted" title="成立日期 ${esc(r.inception || "")}">${esc((r.inception || "").slice(0, 7))} 起</div>` : DASH) },
  ];
  const med = { foot: "med" };
  ps.forEach(([k]) => { med[`r_${k}`] = peer.median[k]; });
  const perfFoot = [med, ...(ps.some(([k]) => peer.rank[k]) ? [{ foot: "rank" }] : [])];
  if (dview === "perf") {
    sortableTable($("#mTable"), [...head, ...perfCols], g.members, { tblClass: "compact", foot: perfFoot, rowClass: (r) => (r.code === g.focus ? "hl" : ""),
      sortState: (state.sorts["detail.perf"] ??= {}) });
  }
  const drawTable = (w) => sortableTable($("#mTable"), [
    ...head,
    { key: "mgr", label: "管理人", val: (r) => r.manager, fmt: (r) => esc(r.manager || "—") },
    { key: "scale", label: "规模（亿）", num: true, val: (r) => r.scale, fmt: (r) => `<b>${num(r.scale)}</b>` },
    { key: "share", label: "占比", num: true, val: (r) => r.scale, fmt: (r) => (g.total ? `${(((r.scale || 0) / g.total) * 100).toFixed(1)}%` : "—") },
    { key: "shares", label: "份额（亿份）", num: true, val: (r) => r.shares, fmt: (r) => num(r.shares) },
    { key: "price", label: "价格", num: true, val: (r) => r.price, fmt: (r) => num(r.price, 3) },
    { key: "amount", label: "成交额（亿）", num: true, val: (r) => r.amount, fmt: (r) => num(r.amount) },
    ...(g.windows[w].base ? [
      { key: "chg", label: `${WIN_LABEL[w]}规模变化`, num: true, val: (r) => r[`${w}_chg`], fmt: (r) => (ok(r[`${w}_chg`]) ? `${signed(r[`${w}_chg`])} <span class="small">${pctS(r[`${w}_pct`])}</span>` : DASH) },
      { key: "flow", label: `${WIN_LABEL[w]}净申赎`, num: true, val: (r) => r[`${w}_flow`], fmt: (r) => signed(r[`${w}_flow`]) },
    ] : []),
    { key: "listed", label: "上市日期", val: (r) => r.listed, fmt: (r) => esc(r.listed || "—") },
  ], g.members, { tblClass: "compact", rowClass: (r) => (r.code === g.focus ? "hl" : ""), sortState: (state.sorts["detail.scale"] ??= {}) });
  if (dview === "scale") drawTable(w);
  onSeg(app, "win", (v) => { prefs.win = v; savePrefs(); render(); });
  onSeg(app, "dview", (v) => { prefs.view = v; savePrefs(); render(); });
  if ($("#valBox")) drawVal(g);

  if ($("#cBar")) {
    const ms = g.members.slice(0, 20).reverse();
    $("#cBar").style.height = `${Math.max(220, ms.length * 28 + 40)}px`;
    makeChart($("#cBar")).setOption({
      grid: { left: 8, right: 60, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v) => `${num(v)} 亿` },
      xAxis: { type: "value", ...AXIS_STYLE },
      yAxis: { type: "category", data: ms.map((m) => m.name), ...AXIS_STYLE, axisLabel: { color: "#4a5361", fontSize: 12 } },
      series: [{ type: "bar", data: ms.map((m) => ({ value: m.scale, itemStyle: { color: m.code === g.focus ? "#e0862f" : "#2f6fdb", borderRadius: [0, 4, 4, 0] } })),
        barMaxWidth: 18, label: { show: true, position: "right", formatter: (p) => num(p.value, 1), color: "#4a5361", fontSize: 11 } }],
    });
  }
  if ($("#cHist")) {
    const dates = g.history.map((h) => h[0]);
    const lines = g.members.slice(0, 5).map((m, i) => {
      const mp = Object.fromEntries((g.member_history[m.code] || []).map(([dd, v]) => [dd, v]));
      return { name: m.name, type: "line", symbol: "circle", symbolSize: 5, data: dates.map((dd) => mp[dd] ?? null), lineStyle: { width: 1.5 },
        color: ["#2f6fdb", "#e0862f", "#18935a", "#9c6ade", "#16a085"][i] };
    });
    const series = g.members.length > 1
      ? [{ name: "合计", type: "line", symbol: "circle", symbolSize: 6, data: g.history.map((h) => h[1]), lineStyle: { width: 2.5 }, color: "#1f2733" }, ...lines] : lines;
    makeChart($("#cHist")).setOption({
      grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
      legend: { top: 0, textStyle: { fontSize: 11 } },
      tooltip: { trigger: "axis", valueFormatter: (v) => (ok(v) ? `${num(v)} 亿` : "—") },
      xAxis: { type: "category", data: dates.map(shortDate), ...AXIS_STYLE },
      yAxis: { type: "value", scale: true, ...AXIS_STYLE },
      series,
    });
  }
}

/** 详情页估值：当前滚动市盈率、分位、历史区间，以及走势图（中位数和 20% / 80% 分位线） */
function drawVal(g) {
  const box = $("#valBox"), v = g.val;
  if (!v) {
    box.innerHTML = `<p class="notice">${esc(g.name)}是${esc(g.cat)}宽基指数，但中证、国证官网和乐咕乐股都没有它的历史估值，暂时算不了分位。
      目前有估值的是 A 股宽基和部分中证编制的港股通宽基。</p>`;
    return;
  }
  const unit = v.freq === "日" ? "交易日" : "月末";
  const pct = ok(v.pct) ? Math.round(v.pct * 100) : null;
  const say = pct == null ? `${esc(g.name)}的估值历史不到一年，暂不计算分位。`
    : `当前市盈率高于统计区间里 ${pct}% 的${unit}${v.pct <= 0.2 ? "，处于历史低位：相对自身历史比较便宜" : v.pct >= 0.8 ? "，处于历史高位：相对自身历史比较贵" : ""}。`;
  box.innerHTML = `
    <div class="stat-row six">
      <div class="stat"><small>${termLabel("滚动市盈率", "市盈率")}</small><b>${num(v.cur)}</b><span class="muted small">${esc(v.asof)}</span></div>
      <div class="stat"><small>分位</small><b>${pct == null ? "—" : `${pct}%`} ${zoneTag(v.pct)}</b><span class="small">${ok(v.pct) ? pctBar(v.pct, false) : `<span class="muted">历史不足 1 年</span>`}</span></div>
      <div class="stat"><small>中位数</small><b>${num(v.median)}</b></div>
      <div class="stat"><small>20% / 80% 分位</small><b>${num(v.p20)} / ${num(v.p80)}</b></div>
      <div class="stat"><small>最低 / 最高</small><b>${num(v.lo)} / ${num(v.hi)}</b></div>
      <div class="stat"><small>统计区间</small><b>${v.years} 年</b><span class="muted small">${esc(v.since)} 起 · ${v.n} 个${unit}</span></div>
    </div>
    <p class="small" style="margin:12px 0 0">${say}分位只说明相对自身历史的位置；指数的成分和盈利周期变了，历史区间不一定可比${v.years < 5 ? `，这个指数只有 ${v.years} 年数据，参考意义有限` : ""}。</p>
    <div id="cVal" class="chart short"></div>`;
  const line = (val, name, color) => ({ yAxis: val, name, lineStyle: { color, type: "dashed" }, label: { formatter: `${name} ${num(val)}`, color, fontSize: 11 } });
  makeChart($("#cVal")).setOption({
    grid: { left: 8, right: 90, top: 16, bottom: 8, containLabel: true },
    tooltip: { trigger: "axis", valueFormatter: (x) => num(x) },
    xAxis: { type: "category", data: v.series.map((s) => s[0]), ...AXIS_STYLE },
    yAxis: { type: "value", scale: true, ...AXIS_STYLE },
    series: [{ name: "滚动市盈率", type: "line", data: v.series.map((s) => s[1]), symbol: v.freq === "日" ? "none" : "circle", symbolSize: 4,
      sampling: "lttb", lineStyle: { width: 1.5 }, color: "#2f6fdb",
      markLine: { symbol: "none", silent: true, data: [line(v.p80, "80%", "#d64532"), line(v.median, "中位数", "#6b7482"), line(v.p20, "20%", "#18935a")] } }],
  });
}

/* ================= 资金流向 ================= */

async function renderFlows(token, win) {
  const d = await loadList();
  if (token !== state.token) return;
  const w = d.windows[win] ? win : prefs.win;
  const info = d.windows[w];
  app.innerHTML = `
    <div class="crumb"><a href="#/">清单</a> › 资金流向</div>
    <section class="card">
      <div class="card-head">
        <h2>${termLabel("资金流向")} · ${WIN_LABEL[w]}</h2>
        <span class="chart-tools">${segButtons("win", Object.keys(d.windows).map((x) => [x, WIN_LABEL[x]]), w)}
          <label class="fitem small"><input type="checkbox" id="money" ${prefs.money ? "checked" : ""}> 含货币 ETF</label></span>
      </div>
      <p class="muted small">净申赎 = 份额变化 × 最新价，剔除了价格涨跌，反映通过申购赎回真正进出的资金；正数为净流入。
        ${info.base ? `本期 ${esc(d.day)}，对比 ${esc(info.base)} 的快照。` : ""}货币 ETF 是现金管理工具，申赎量大且频繁，默认不计入。</p>
      <div id="flowBody"></div>
    </section>`;
  onSeg(app, "win", (v) => { location.hash = `#/flows/${v}`; });
  $("#money").onchange = (e) => { prefs.money = e.target.checked; savePrefs(); draw(); };

  const draw = () => {
    const body = $("#flowBody");
    if (!info.base) {
      body.innerHTML = `<p class="notice">${WIN_LABEL[w]}的资金流向需要一份 ${info.days} 天前或更早的${termLabel("快照")}。本地现有快照：${esc(d.dates.join("、") || "无")}。<br>
        深交所只公布当天份额、不提供历史，所以流向要靠每次刷新积累：每次启动服务或点“刷新数据”都会存一份当天快照。
        ${d.dates.length ? `大约 ${esc(addDays(d.dates[0], info.days))} 之后可以看到${WIN_LABEL[w]}的数据。` : ""}</p>`;
      return;
    }
    const rows = d.rows.filter((r) => ok(r[`${w}_flow`]) && (prefs.money || r.cat !== "货币"));
    const cats = d.categories.filter((c) => prefs.money || c !== "货币").map((c) => {
      const rs = rows.filter((r) => r.cat === c);
      const flow = rs.reduce((s, r) => s + r[`${w}_flow`], 0), chg = rs.reduce((s, r) => s + (r[`${w}_chg`] || 0), 0);
      const scale = rs.reduce((s, r) => s + (r.scale || 0), 0);
      return { code: c, cat: c, n: rs.length, flow, chg, price: chg - flow, scale, ratio: scale ? flow / (scale - chg) : null };
    });
    const idx = new Map();
    rows.forEach((r) => {
      const k = r.ik || `#${r.code}`;
      if (!idx.has(k)) idx.set(k, { code: r.code, name: idxText(r), ik: r.ik, cat: r.cat, n: 0, flow: 0, chg: 0, scale: 0, guess: r.guess });
      const g = idx.get(k);
      g.n += 1; g.flow += r[`${w}_flow`]; g.chg += r[`${w}_chg`] || 0; g.scale += r.scale || 0;
    });
    const groups = [...idx.values()];
    groups.forEach((g) => { g.ratio = g.scale - g.chg ? g.flow / (g.scale - g.chg) : null; });
    const ins = groups.filter((g) => g.flow > 0).sort((a, b) => b.flow - a.flow).slice(0, 15);
    const outs = groups.filter((g) => g.flow < 0).sort((a, b) => a.flow - b.flow).slice(0, 15);
    const tot = cats.reduce((s, c) => s + c.flow, 0);
    body.innerHTML = `
      <div class="stat-row four" style="margin:8px 0 16px">
        <div class="stat"><small>合计净申赎</small><b>${signed(tot)} 亿</b></div>
        <div class="stat"><small>净流入的指数</small><b>${groups.filter((g) => g.flow > 0.005).length} 个</b></div>
        <div class="stat"><small>净流出的指数</small><b>${groups.filter((g) => g.flow < -0.005).length} 个</b></div>
        <div class="stat"><small>参与计算的 ETF</small><b>${rows.length} 只</b></div>
      </div>
      <div id="catTable"></div>
      <div class="grid2" style="margin-top:16px">
        <div><h3>净流入最多的指数</h3><div id="cIn" class="chart"></div></div>
        <div><h3>净流出最多的指数</h3><div id="cOut" class="chart"></div></div>
      </div>
      <h3 style="margin:16px 0 8px">按指数汇总</h3>
      <div id="idxTable"></div>`;
    sortableTable($("#catTable"), [
      { key: "cat", label: "分类", fmt: (r) => catBadge(r.cat) },
      { key: "n", label: "ETF 数", num: true, fmt: (r) => r.n },
      { key: "scale", label: "当前规模（亿）", num: true, fmt: (r) => num(r.scale, 0) },
      { key: "flow", label: "净申赎（亿）", num: true, fmt: (r) => signed(r.flow) },
      { key: "price", label: "价格涨跌带来（亿）", num: true, fmt: (r) => signed(r.price) },
      { key: "chg", label: "规模变化（亿）", num: true, fmt: (r) => signed(r.chg) },
      { key: "ratio", label: "净申赎 / 期初规模", num: true, fmt: (r) => pctS(r.ratio, 2) },
    ], cats, { tblClass: "compact" });
    const bar = (el, list, color) => {
      const ls = list.slice().reverse();
      makeChart(el).setOption({
        grid: { left: 8, right: 56, top: 8, bottom: 8, containLabel: true },
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v) => `${num(v)} 亿` },
        xAxis: { type: "value", ...AXIS_STYLE, inverse: color === "#18935a" },
        yAxis: { type: "category", data: ls.map((g) => g.name), ...AXIS_STYLE, axisLabel: { color: "#4a5361", fontSize: 11, width: 150, overflow: "truncate" },
          position: color === "#18935a" ? "right" : "left" },
        series: [{ type: "bar", data: ls.map((g) => Math.abs(g.flow)), itemStyle: { color }, barMaxWidth: 16,
          label: { show: true, position: color === "#18935a" ? "left" : "right", formatter: (p) => num(p.value, 1), fontSize: 11, color: "#4a5361" } }],
      });
    };
    if (ins.length) bar($("#cIn"), ins, "#d9363e"); else $("#cIn").outerHTML = `<div class="empty">没有净流入的指数</div>`;
    if (outs.length) bar($("#cOut"), outs, "#18935a"); else $("#cOut").outerHTML = `<div class="empty">没有净流出的指数</div>`;
    sortableTable($("#idxTable"), [
      { key: "name", label: "指数", val: (r) => r.name, fmt: (r) => `${esc(r.name)}${guessMark(r)} <span class="muted small">${esc(r.ik || "")}</span>` },
      { key: "cat", label: "分类", val: (r) => d.categories.indexOf(r.cat), fmt: (r) => catBadge(r.cat) },
      { key: "n", label: "ETF 数", num: true, val: (r) => r.n, fmt: (r) => r.n },
      { key: "scale", label: "当前规模（亿）", num: true, val: (r) => r.scale, fmt: (r) => num(r.scale) },
      { key: "flow", label: "净申赎（亿）", num: true, val: (r) => r.flow, fmt: (r) => signed(r.flow) },
      { key: "chg", label: "规模变化（亿）", num: true, val: (r) => r.chg, fmt: (r) => signed(r.chg) },
      { key: "ratio", label: "净申赎 / 期初规模", num: true, val: (r) => r.ratio, fmt: (r) => pctS(r.ratio, 2) },
    ], groups.sort((a, b) => Math.abs(b.flow) - Math.abs(a.flow)).slice(0, 100), { tblClass: "compact", onRow: openEtf, sortState: (state.sorts.flows ??= {}) });
  };
  draw();
}

function addDays(day, n) {
  const t = new Date(`${day}T00:00:00`);
  t.setDate(t.getDate() + n);
  return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")}`;
}

/* ================= 数据健康 ================= */

async function renderHealth(token) {
  const h = await api("/api/health");
  if (token !== state.token) return;
  const s = h.sources || {}, cc = h.crosscheck || {};
  const warn = state.meta.crosscheck_warn;
  const list = (rows, empty) => (rows.length ? `<div class="table-wrap"><table class="tbl compact"><thead><tr><th>ETF</th><th>跟踪指数</th><th>分类</th><th class="num">规模（亿）</th></tr></thead><tbody>
    ${rows.map((r) => `<tr class="link" data-code="${r.code}"><td>${esc(r.name)} <span class="muted small">${r.code}</span></td><td>${esc(r.iname || "—")}</td><td>${catBadge(r.cat)}</td><td class="num">${num(r.scale)}</td></tr>`).join("")}
    </tbody></table></div>` : `<div class="empty">${empty}</div>`);
  app.innerHTML = `
    <div class="crumb"><a href="#/">清单</a> › 数据健康</div>
    <section class="card stat-row four">
      <div class="stat"><small>份额日期（快照）</small><b>${esc(h.day || "—")}</b></div>
      <div class="stat"><small>ETF 总数</small><b>${h.total} 只</b><span class="muted small">上交所 ${h.sh} · 深交所 ${h.sz}</span></div>
      <div class="stat"><small>上次刷新</small><b>${esc(h.last_refresh || "—")}</b></div>
      <div class="stat"><small>上次刷新的问题</small><b class="${h.failed.length ? "warn-text" : ""}">${h.failed.length} 项</b></div>
    </section>
    ${h.failed.length ? `<section class="card"><div class="card-head"><h2>上次刷新的问题</h2><span class="muted small">核心数据不完整时不会写入，页面显示的仍是上一次的数据</span></div>
      <ul>${h.failed.map((f) => `<li class="small">${esc(f)}</li>`).join("")}</ul></section>` : ""}
    <section class="card">
      <div class="card-head"><h2>数据来源</h2></div>
      <div class="table-wrap"><table class="tbl compact health"><thead><tr><th>数据</th><th>来源</th><th class="num">条数</th><th>日期</th><th>说明</th></tr></thead><tbody>
        <tr><td>上交所 ETF 列表</td><td>上交所基金列表</td><td class="num">${s.sse_list ?? "—"}</td><td>—</td><td>代码、简称、管理人、跟踪指数、类别、上市日期</td></tr>
        <tr><td>上交所份额</td><td>上交所 ETF 规模</td><td class="num">${s.sse_shares ?? "—"}</td><td>${esc(s.sse_date || "—")}</td><td>不含货币 ETF（见下方“补充数据”）</td></tr>
        <tr><td>深交所 ETF 列表与份额</td><td>深交所 ETF 列表、基金列表</td><td class="num">${s.szse_list ?? "—"}</td><td>${esc(s.szse_date || "—")}</td><td>拟合指数、当前规模、投资类别、上市日期。交易所注明 T 日晚间的份额仅供参考，以 T+1 日早间更新的为准；同一天再次刷新会覆盖当天快照</td></tr>
        <tr><td>价格与成交额</td><td>新浪财经 ETF 行情</td><td class="num">${s.sina ?? "—"}</td><td>${esc(h.day || "—")}</td><td>非交易时间为最近一个交易日的收盘价</td></tr>
        <tr><td>指数名称与类别</td><td>中证指数、国证指数官网</td><td class="num">${s.index_names ?? "—"}</td><td>${esc((h.index_names_at || "—").slice(0, 10))}</td><td>每周更新一次；深交所 399 开头的行情代码按名称对到中证官方代码后去重；指数类别（规模 / 行业 / 主题 / 策略 / 风格）决定类型</td></tr>
        <tr><td>区间收益</td><td>东方财富场内基金排行</td><td class="num">${s.perf ?? "—"}</td><td>${esc(s.perf_date || "—")}</td><td>按复权净值计算，含分红；货币 ETF 和刚上市的 ETF 没有</td></tr>
        <tr><td>宽基估值</td><td>中证指数官网 / 乐咕乐股</td><td class="num">${(s.val_cs ?? 0) + (s.val_lg ?? 0)} 个指数</td><td>${esc(h.val_ok[0]?.asof || "—")}</td><td>中证 ${s.val_cs ?? 0} 个（每日滚动市盈率），乐咕乐股 ${s.val_lg ?? 0} 个（深证、国证系列，月末数据）；只更新还没有当天数据的指数</td></tr>
      </tbody></table></div>
    </section>
    <section class="card">
      <div class="card-head"><h2>${termLabel("交叉核对")}：腾讯行情</h2><span class="muted small">${esc(cc.at || "")}</span></div>
      <p>规模最大的 ${cc.n ?? "—"} 只中，${cc.matched ?? "—"} 只在腾讯行情查到总市值；两者相差的中位数为 <b>${ok(cc.median) ? (cc.median * 100).toFixed(3) + "%" : "—"}</b>，
        相差超过 ${(warn * 100).toFixed(0)}% 的有 <b class="${cc.flagged?.length ? "warn-text" : ""}">${cc.flagged?.length ?? 0}</b> 只。</p>
      <p class="muted small">交易所份额是官方数据；腾讯的份额有时会晚一两天更新，大额申赎的日子两者差得最多，此时以交易所为准。</p>
      <div id="ccTable"></div>
    </section>
    <section class="card">
      <div class="card-head"><h2>补充数据与推断</h2></div>
      <h3 style="margin-bottom:6px">份额由腾讯行情反推（${h.from_tencent.length} 只）</h3>
      <p class="muted small">上交所份额接口不含货币 ETF，这些 ETF 的规模直接取腾讯行情的总市值，份额 = 总市值 ÷ 价格。</p>
      ${list(h.from_tencent, "没有")}
      <h3 style="margin:16px 0 6px">跟踪指数名称用 ETF 简称代替（${h.guess.length} 只）</h3>
      <p class="muted small">交易所只给了指数代码，中证、国证官网也查不到名称（多为境外指数，如标普、纳斯达克、日经系列）。去重仍按代码进行，不受影响。</p>
      ${list(h.guess, "没有")}
      <h3 style="margin:16px 0 6px">类型按名称判断的指数（${h.style_kw.length} 个）</h3>
      <p class="muted small">中证、国证官网查不到类别的指数（多为港股、海外指数）按名称关键词判断：含红利、低波、价值、成长等算策略，纳指100、标普500、恒生指数等算宽基，
        含银行、证券、医药、消费等算行业，其余算主题。债券按名称分利率债（国债、政金债、地方债）、可转债和信用债。每个指数列出规模最大的一只。</p>
      ${h.style_kw.length ? `<div class="table-wrap"><table class="tbl compact"><thead><tr><th>跟踪指数</th><th>分类 · 类型</th><th>规模最大的 ETF</th><th class="num">规模（亿）</th></tr></thead><tbody>
        ${h.style_kw.map((r) => `<tr class="link" data-code="${r.code}"><td>${esc(r.iname || "—")}</td><td>${catBadge(r.cat)} ${styleTag(r.style)}</td><td>${esc(r.name)} <span class="muted small">${r.code}</span></td><td class="num">${num(r.scale)}</td></tr>`).join("")}
        </tbody></table></div>` : `<div class="empty">没有</div>`}
      <h3 style="margin:16px 0 6px">没有估值数据的宽基指数（${h.val_none.length} 个）</h3>
      <p class="muted small">港股、海外宽基没有公开的历史估值来源；部分深证、国证指数乐咕乐股也没有收录。</p>
      ${list(h.val_none, "没有")}
      ${h.no_price.length ? `<h3 style="margin:16px 0 6px">没有价格（${h.no_price.length} 只）</h3>${list(h.no_price, "")}` : ""}
      ${h.no_shares.length ? `<h3 style="margin:16px 0 6px">没有份额（${h.no_shares.length} 只）</h3>${list(h.no_shares, "")}` : ""}
    </section>
    <section class="card">
      <div class="card-head"><h2>本地快照</h2><span class="muted small">共 ${h.dates.length} 份</span></div>
      <p>${esc(h.dates.join("、") || "无")}</p>
      <p class="muted small">规模变化、资金流向和规模走势都基于这些快照。交易所不提供历史份额，所以只能从开始使用这个工具起积累；同一天多次刷新只保留最后一次。</p>
    </section>`;
  sortableTable($("#ccTable"), [
    { key: "name", label: "ETF", val: (r) => r.name, fmt: (r) => `${esc(r.name)} <span class="muted small">${r.code}</span>` },
    { key: "ours", label: "本站规模（亿）", num: true, val: (r) => r.ours, fmt: (r) => num(r.ours) },
    { key: "tencent", label: "腾讯总市值（亿）", num: true, val: (r) => r.tencent, fmt: (r) => num(r.tencent) },
    { key: "diff", label: "相差", num: true, val: (r) => Math.abs(r.diff), fmt: (r) => `<span class="warn-text">${r.diff > 0 ? "+" : ""}${(r.diff * 100).toFixed(1)}%</span>` },
  ], cc.flagged || [], { tblClass: "compact", onRow: openEtf });
  if (!cc.flagged?.length) $("#ccTable").innerHTML = "";
  $$("tr.link[data-code]", app).forEach((tr) => { if (!tr.onclick) tr.onclick = () => openEtf(tr.dataset.code); });
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
    <div class="crumb"><a href="#/">清单</a> › 术语百科</div>
    <div class="gl-search"><input id="glq" placeholder="搜索术语，如 净申赎、份额、去重…" autocomplete="off"></div>
    <section class="gl-grid">${state.glossary.map(card).join("")}</section>
    <div class="empty" id="glNone" hidden>没有找到相关术语，换个词试试。</div>
    <p class="muted small">正文中带虚线下划线的词，鼠标悬停即可查看解释。</p>`;
  $("#glq").addEventListener("input", (e) => {
    const q = e.target.value.trim().toLowerCase();
    $$(".gl").forEach((el) => (el.hidden = !!q && !el.dataset.text.includes(q)));
    $("#glNone").hidden = $$(".gl").some((el) => !el.hidden);
  });
}

async function renderReports(token) {
  const list = await api("/api/reports");
  if (token !== state.token) return;
  app.innerHTML = `
    <div class="crumb"><a href="#/">清单</a> › 报告</div>
    <section class="card">
      <div class="card-head"><h2>报告</h2><span class="muted small">放在 reports/ 目录下的 HTML 报告，最新的在前</span></div>
      ${list.length ? `<ul class="report-list">${list.map((n) => `<li><a href="/reports/${encodeURIComponent(n)}" target="_blank" rel="noopener">${esc(n.replace(/\.html$/, ""))}</a></li>`).join("")}</ul>`
        : `<div class="empty">还没有报告。</div>`}
    </section>`;
}

/* ================= 新手指引 ================= */

function guideSteps() {
  return [
    {
      title: "欢迎使用 ETF 规模筛选",
      body: `<p>它列出沪深两市<b>全部 ETF</b> 的最新规模，帮你按规模门槛筛出值得关注的那些，并且<b>按跟踪指数去重</b>：同一个指数往往有好几只 ETF，默认只保留规模最大的一只。</p>
        <p>份额来自上交所、深交所官网，价格来自新浪行情，<b>每次启动服务都会自动更新</b>。</p>`,
    },
    {
      title: "调门槛、筛分类",
      body: `<p>清单页顶部可以改<b>规模门槛</b>（默认 50 亿）、切换去重、按分类（A股、港股、海外、债券、商品、货币）和<b>类型</b>（宽基、窄基、策略、利率债等）筛选或搜索。这些设置保存在浏览器里，下次打开还在。</p>
        <p>点击任意一行，可以看到跟踪同一指数的全部 ETF 及各自的规模、成交额。结果可以导出成 CSV 用 Excel 打开。</p>`,
    },
    {
      title: "收益与估值",
      body: `<p>清单上方的「显示」可以切换三组列：<b>规模</b>、<b>收益</b>（近 1 周到近 3 年，按复权净值计算，含分红）和<b>估值</b>（宽基指数的滚动市盈率在近 10 年里的分位）。</p>
        <p>详情页还有同类中位数和排名（比如在 A股宽基里排第几），以及宽基指数的市盈率走势图。</p>`,
    },
    {
      title: "规模变化与资金流向",
      body: `<p>每次刷新都会在本地存一份当天<b>快照</b>。有了几天前的快照，就能看到近 1 周、1 月、3 月的规模变化和<b>净申赎</b>（份额变化 × 价格，剔除了涨跌的影响）。</p>
        <p>交易所不提供历史份额，所以这部分要从今天起慢慢积累。</p>`,
    },
    {
      title: "数据口径",
      body: `<p>规模用<b>市值口径</b>：最新份额 × 最新价。基金定期报告里的“净资产规模”滞后一个季度左右，两者可能相差 10% 以上。</p>
        <p>「数据健康」页列出各来源的条数和日期，以及与腾讯行情的交叉核对结果。带虚线的词悬停可以看解释。</p>`,
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
  const links = [["", "清单"], ["flows", "资金流向"], ["health", "数据健康"], ["glossary", "术语"], ["reports", "报告"]];
  const cur = page === "etf" ? "" : page || "";
  $("#nav").innerHTML = links.map(([h, t]) => `<a href="#/${h}" class="${h === cur ? "on" : ""}">${t}</a>`).join("");
}

async function render() {
  if (state.initMode) { renderInit(); return; }
  const token = ++state.token;
  disposeCharts();
  const [page, a] = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  renderNav(page);
  const keepScroll = state.lastHash === location.hash;
  if (state.lastHash != null) state.scrolls[state.lastHash] = window.scrollY;
  state.lastHash = location.hash;
  const y = keepScroll ? window.scrollY : state.push ? 0 : state.scrolls[location.hash] || 0;
  state.push = false;
  app.innerHTML = `<div class="loading">加载中…</div>`;
  try {
    if (!page) await renderList(token);
    else if (page === "etf" && a) await renderDetail(token, a);
    else if (page === "flows") await renderFlows(token, a);
    else if (page === "health") await renderHealth(token);
    else if (page === "glossary") await renderGlossary(token);
    else if (page === "reports") await renderReports(token);
    else location.replace("#/");
    window.scrollTo(0, y);
  } catch (e) {
    if (token !== state.token) return;
    if (e.status === 503) {
      state.initMode = true;
      await refreshStatus().catch(() => null);
      renderInit();
      if (state.status?.updating) startPolling();
      return;
    }
    if (e.status === 404) {
      app.innerHTML = `<div class="card error"><h2>找不到</h2><p>${esc(e.message)}。可能代码输错了，或这只 ETF 已退市、不在交易所的列表里。</p>
        <p><a href="#/">返回清单</a>，用搜索框按代码、名称或指数查找。</p></div>`;
      return;
    }
    console.error(e);
    app.innerHTML = `<div class="card error"><h2>加载失败</h2><p>${esc(e.message)}</p>
      <p class="muted">请确认服务正在运行（双击 scripts/start_server.bat），然后刷新页面。</p></div>`;
  }
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
    const top = Math.max(0, $(".topbar").getBoundingClientRect().bottom);
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

/** 页面上所有吸顶表头；随页面滚动统一更新，表格被重绘（排序、筛选）后自动移除 */
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
  setupTables();
  $("#btnRefresh").onclick = manualRefresh;
  $("#btnGuide").onclick = () => openGuide(0);
  document.addEventListener("click", (e) => { if (e.target.closest?.('a[href^="#"]')) state.push = true; }, true);
  try {
    const [meta, glossary] = await Promise.all([api("/api/meta"), api("/api/glossary")]);
    state.meta = meta;
    state.glossary = glossary;
    buildTerms();
    await refreshStatus();
  } catch (e) {
    app.innerHTML = `<div class="card error"><h2>无法连接服务</h2><p>${esc(e.message)}</p>
      <p class="muted">请双击 scripts/start_server.bat 启动服务，并通过 http://127.0.0.1:8324 打开页面（不要直接双击 index.html）。</p></div>`;
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

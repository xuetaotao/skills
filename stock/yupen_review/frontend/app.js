"use strict";

/* ================= 基础工具 ================= */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const app = $("#app");

const state = {
  meta: null, glossary: [], termRe: null, termIndex: {},
  status: null, polling: null, charts: [], token: 0, initMode: false,
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
  return (r.headers.get("content-type") || "").includes("json") ? r.json() : r.text();
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const shortDate = (d) => (d ? d.slice(5) : "—");
const ok = (v) => v != null && isFinite(v);
const num = (v, d = 2) => (ok(v) ? Number(v).toLocaleString("zh-CN", { minimumFractionDigits: d, maximumFractionDigits: d }) : "—");
const DASH = `<span class="muted">—</span>`;
const signed = (v, d = 2, suf = "") => (ok(v)
  ? `<span class="${v > 0 ? "up" : v < 0 ? "down" : ""}">${v > 0 ? "+" : ""}${num(v, d)}${suf}</span>` : DASH);
const pctS = (v, d = 2) => (ok(v) ? signed(v * 100, d, "%") : DASH);
const bpS = (v) => (ok(v) ? signed(v, 0, "bp") : DASH);
const yieldS = (v) => (ok(v) ? `${num(v, 2)}%` : DASH);

const GROUP_COLOR = { "A股": "#d64532", "港股": "#e0862f", "美股": "#2f6fdb", "日韩台": "#9c6ade", "其他海外": "#4f8f88", "大宗商品": "#b08a2e", "行业与个股": "#a0527a" };
const groupDot = (g) => `<span class="dotc" style="background:${GROUP_COLOR[g] || "#999"}"></span>`;
const statusTag = (s) => (s === "YES" ? `<span class="st yes">YES</span>` : s === "NO" ? `<span class="st no">NO</span>` : DASH);
const SIGNALS = ["强力买入", "买入", "观望", "谨慎", "卖出"];
const sigTag = (s) => (s ? `<span class="sig sig${SIGNALS.indexOf(s)}">${esc(s)}</span>` : "");
const pctInt = (v) => (ok(v) ? `${Math.round(v * 100)}%` : "—");
const valTip = (v) => (v ? `PE ${num(v.pe, 2)}（历史百分位 ${pctInt(v.pe_pct)}）· PB ${num(v.pb, 2)}（${pctInt(v.pb_pct)}）${v.ref ? ` · 参照${v.ref}` : ""} · 蛋卷基金 ${v.date}` : "");
const valCell = (v) => (v && ok(v.pe_pct) ? `<span title="${esc(valTip(v))}"><b>${pctInt(v.pe_pct)}</b><div class="small muted">PE ${num(v.pe, 1)}${v.ref ? ` · ${esc(v.ref)}` : ""}</div></span>` : DASH);

function toast(text, kind = "ok", ms = 4000) {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = text;
  $("#toasts").appendChild(el);
  setTimeout(() => el.classList.add("out"), ms);
  setTimeout(() => el.remove(), ms + 400);
}

const GUIDE_KEY = "review_guide_v1";
const PREF_KEY = "review_prefs_v1";
const prefs = { version: "simple", wmode: "dev", wn: 8, range: "y1", term: "10年", ...JSON.parse(localStorage.getItem(PREF_KEY) || "{}") };
const savePrefs = () => localStorage.setItem(PREF_KEY, JSON.stringify(prefs));

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
}

function download(name, text, type = "text/markdown;charset=utf-8") {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
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
    pill.innerHTML = `<span class="spinner"></span>更新中 ${s.done}/${s.total || "…"}`;
    pill.className = "status-pill busy";
    pill.title = s.current ? `正在获取：${s.current}` : "";
    bar.hidden = false;
    $("i", bar).style.width = `${s.total ? (s.done / s.total) * 100 : 5}%`;
    btn.disabled = true;
  } else {
    pill.innerHTML = s.empty ? "暂无数据"
      : `<span class="dot ${s.failed ? "amber" : "ok"}"></span>数据截至 ${shortDate(s.data_date)} · ${s.failed ? `${s.failed} 项获取失败` : "全部正常"}`;
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
    else toast("数据已更新到最新，outputs 下的复盘汇总也已重写", "ok");
    state.initMode = false;
    state.meta = await api("/api/meta").catch(() => state.meta);
    render();
  }, 1500);
}

async function manualRefresh() {
  try {
    const r = await api("/api/refresh", { method: "POST" });
    toast(r.started ? "开始刷新，大约需要半分钟，可以继续浏览" : "已经在刷新中", "info");
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
      <p>首次运行会下载各个指数、商品和个股自 2015 年以来的日线，以及美元指数、中美国债收益率和估值，大约一分钟。完成后页面会自动刷新。</p>
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
const C_UP = "#d9363e", C_DOWN = "#18935a", C_BRAND = "#2f6fdb", C_WARM = "#e0862f";

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

/** 可排序表格。排序循环：降序 → 升序 → 恢复默认。传入 opt.sortState（对象）可让排序在表格重绘后保留 */
function sortableTable(el, cols, rows, opt = {}) {
  const st = opt.sortState || {};
  let sort = st.v && cols.some((c) => c.key === st.v.key && c.val) ? st.v : null;
  const cmp = (a, b) => (a == null ? 1 : b == null ? -1 : a < b ? -1 : a > b ? 1 : 0);
  const cells = (r) => cols.map((c) => `<td class="${c.num ? "num" : ""}${c.cls ? ` ${c.cls}` : ""}">${c.fmt(r)}</td>`).join("");
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
      return `<th class="${c.num ? "num" : ""}${c.val ? " sortable" : ""}${on ? " sorted" : ""}${c.cls ? ` ${c.cls}` : ""}" data-k="${c.key}"
        ${c.title ? `title="${esc(c.title)}"` : ""}>${c.label}${on ? (sort.dir > 0 ? " ↑" : " ↓") : ""}</th>`;
    }).join("");
    const body = list.map((r) => `<tr class="${opt.rowClass?.(r) || ""}${opt.onRow ? " link" : ""}" data-code="${esc(r.code || "")}">${cells(r)}</tr>`).join("")
      || `<tr><td colspan="${cols.length}" class="empty">${opt.empty || "暂无数据"}</td></tr>`;
    const left = $(".table-wrap", el)?.scrollLeft || 0;
    el.innerHTML = `<div class="table-wrap"><table class="tbl ${opt.tblClass || ""}"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
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
const openInst = (code) => nav(`#/i/${encodeURIComponent(code)}`);

/** 偏离度迷你走势（近 60 个交易日），零轴即临界值 */
function spark(vals) {
  const v = (vals || []).filter(ok);
  if (v.length < 2) return "";
  const w = 72, h = 22;
  const lo = Math.min(0, ...v), hi = Math.max(0, ...v);
  const span = hi - lo || 1;
  const y = (x) => (h - 2 - ((x - lo) / span) * (h - 4)).toFixed(1);
  const pts = v.map((x, i) => `${((i / (v.length - 1)) * w).toFixed(1)},${y(x)}`).join(" ");
  const last = v[v.length - 1];
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}"><line x1="0" x2="${w}" y1="${y(0)}" y2="${y(0)}" class="zero"/>
    <polyline points="${pts}" class="${last >= 0 ? "pos" : "neg"}"/></svg>`;
}

/** 偏离度条：以 0 为中点，±15% 封顶 */
function devBar(v) {
  if (!ok(v)) return DASH;
  const cap = 0.15, w = Math.min(Math.abs(v), cap) / cap * 50;
  return `<span class="devbar"><span class="devbar-track"><i class="${v >= 0 ? "pos" : "neg"}" style="${v >= 0 ? "left:50%" : `left:${50 - w}%`};width:${w}%"></i></span>${pctS(v)}</span>`;
}

function badges(r) {
  const b = [];
  if (r.changed_today) b.push(`<span class="badge amber" title="数据日期当天发生状态转变">今日转变</span>`);
  else if (r.changed_week) b.push(`<span class="badge amber" title="上周末 ${r.prev_status} → 本周 ${r.status}">本周转变</span>`);
  if ((r.week_flips || []).length >= 2) b.push(`<span class="badge gray" title="${r.week_flips.map((f) => `${f.date.slice(5)} 转为 ${f.to}`).join("；")}">本周反复</span>`);
  if (r.stale) b.push(`<span class="badge gray" title="比整体数据日期落后超过 4 天：可能休市或取数失败">数据截至 ${shortDate(r.date)}</span>`);
  return b.join(" ");
}

const nameCell = (r) => `<b>${esc(r.name)}</b> <small class="muted">${esc(r.code)}</small> ${badges(r)}`;

/* ================= Markdown（周报、新闻候选、AI 素材） ================= */

function inlineMd(s) {
  let h = esc(s);
  h = h.replace(/`([^`]+)`/g, "<code>$1</code>");
  h = h.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  h = h.replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<i>$2</i>");
  h = h.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, `<a href="$2" target="_blank" rel="noopener">$1</a>`);
  h = h.replace(/(^|[\s（(：:])(https?:\/\/[^\s<）)，。；]+)/g, `$1<a href="$2" target="_blank" rel="noopener">$2</a>`);
  return h;
}

function renderMd(text) {
  const lines = text.replace(/<!--[\s\S]*?-->/g, "").replace(/\r/g, "").split("\n");
  const out = [];
  let i = 0;
  const isTable = (l) => /^\s*\|.*\|\s*$/.test(l);
  while (i < lines.length) {
    const l = lines[i];
    if (/^```/.test(l)) {
      const buf = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      i++;
      out.push(`<pre><code>${esc(buf.join("\n"))}</code></pre>`);
      continue;
    }
    const hm = l.match(/^(#{1,4})\s+(.*)$/);
    if (hm) { out.push(`<h${hm[1].length}>${inlineMd(hm[2])}</h${hm[1].length}>`); i++; continue; }
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(l)) { out.push("<hr>"); i++; continue; }
    if (isTable(l) && isTable(lines[i + 1] || "") && /^[\s|:-]+$/.test(lines[i + 1])) {
      const split = (x) => x.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const head = split(l);
      i += 2;
      const body = [];
      while (i < lines.length && isTable(lines[i])) body.push(split(lines[i++]));
      out.push(`<div class="table-wrap"><table class="tbl md-tbl"><thead><tr>${head.map((c) => `<th>${inlineMd(c)}</th>`).join("")}</tr></thead>
        <tbody>${body.map((r) => `<tr>${r.map((c) => `<td>${inlineMd(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
      continue;
    }
    if (/^\s*>/.test(l)) {
      const buf = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ""));
      out.push(`<blockquote>${buf.map(inlineMd).join("<br>")}</blockquote>`);
      continue;
    }
    if (/^\s*([-*]|\d+\.)\s+/.test(l)) {
      const ordered = /^\s*\d+\./.test(l);
      const buf = [];
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
        let item = lines[i++].replace(/^\s*([-*]|\d+\.)\s+/, "");
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !/^\s*([-*]|\d+\.)\s+/.test(lines[i])) item += " " + lines[i++].trim();
        buf.push(`<li>${inlineMd(item)}</li>`);
      }
      out.push(ordered ? `<ol>${buf.join("")}</ol>` : `<ul>${buf.join("")}</ul>`);
      continue;
    }
    if (!l.trim()) { i++; continue; }
    const buf = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|```|\s*>|\s*([-*]|\d+\.)\s+|\s*(-{3,}|\*{3,})\s*$)/.test(lines[i]) && !isTable(lines[i])) buf.push(lines[i++]);
    if (!buf.length) { out.push(`<p>${inlineMd(lines[i++])}</p>`); continue; }
    out.push(`<p>${buf.map(inlineMd).join("<br>")}</p>`);
  }
  return out.join("\n");
}

/* ================= 总览 ================= */

function weekOptions(cur) {
  const ends = (state.meta?.week_ends || []).slice().reverse();
  const latest = ends[0];
  const extra = cur && !ends.includes(cur) ? `<option value="${esc(cur)}" selected>${esc(cur)} 那一周</option>` : "";
  return ends.map((d, i) => `<option value="${i === 0 ? "" : d}" ${(cur || latest) === d ? "selected" : ""}>${i === 0 ? `本周（${d}）` : `${d} 那一周`}</option>`).join("") + extra;
}

function visible(rows, simple) {
  const set = new Set(simple);
  return rows.filter((r) => !r.nodata && (prefs.version === "full" || set.has(r.code)));
}

/** 按市场分组的要点：YES 个数、本周平均涨跌、偏离度变化、最强最弱、本周转变 */
function insights(rows, groups) {
  const lis = [];
  groups.forEach((g) => {
    const xs = rows.filter((r) => r.group === g);
    if (!xs.length) return;
    const yes = xs.filter((r) => r.status === "YES").length;
    const by = xs.slice().sort((a, b) => (b.dev ?? -9) - (a.dev ?? -9));
    const wtd = xs.map((r) => r.wtd).filter(ok);
    const dd = xs.filter((r) => ok(r.dev) && ok(r.prev_dev)).map((r) => r.dev - r.prev_dev);
    const avg = (a) => a.reduce((s, x) => s + x, 0) / a.length;
    const ups = xs.filter((r) => r.changed_week && r.status === "YES").map((r) => r.name);
    const downs = xs.filter((r) => r.changed_week && r.status === "NO").map((r) => r.name);
    const parts = [];
    parts.push(xs.length === 1 ? `${statusTag(xs[0].status)} 偏离度 ${pctS(xs[0].dev)}`
      : yes === xs.length ? `${xs.length} 个全部 YES` : yes === 0 ? `${xs.length} 个全部 NO` : `${xs.length} 个中 <b>${yes}</b> 个 YES`);
    if (wtd.length) parts.push(`本周平均 ${pctS(avg(wtd))}`);
    if (dd.length) {
      const a = avg(dd);
      parts.push(Math.abs(a) < 0.002 ? "偏离度与上周持平" : `偏离度较上周平均${a > 0 ? "<span class=\"up\">改善</span>" : "<span class=\"down\">走弱</span>"} ${num(Math.abs(a) * 100, 1)} 个百分点`);
    }
    if (xs.length > 1) parts.push(`最强 ${esc(by[0].name)} ${pctS(by[0].dev)}，最弱 ${esc(by[by.length - 1].name)} ${pctS(by[by.length - 1].dev)}`);
    if (ups.length) parts.push(`<span class="up">转为 YES：${ups.map(esc).join("、")}</span>`);
    if (downs.length) parts.push(`<span class="down">转为 NO：${downs.map(esc).join("、")}</span>`);
    lis.push(`<li>${groupDot(g)}<b>${g}</b>：${parts.join("；")}</li>`);
  });
  return `<ul class="insights">${lis.join("")}</ul>`;
}

/** 标的在清单里的顺序（按市场分组排列），用于“市场”列排序 */
const instOrder = (code) => state.meta.instruments.findIndex((x) => x.code === code);

function instCols(kind, rows) {
  const hasVal = rows.some((r) => r.val && ok(r.val.pe_pct));
  const cols = [
    { key: "rank", label: "#", num: true, fmt: (r) => `<span class="rank">${r.rank}</span>`, val: (r) => -r.rank },
    ...(kind === "stock" ? [{ key: "region", label: "市场", fmt: (r) => `${groupDot(r.group)}${esc(r.region)}`, val: (r) => -instOrder(r.code) }] : []),
    { key: "name", label: "名称", fmt: (r) => nameCell(r), cls: "namec" },
    { key: "price", label: "现价", num: true, fmt: (r) => num(r.price), val: (r) => r.price },
    { key: "chg", label: termLabel("当日", "当日涨跌"), num: true, fmt: (r) => pctS(r.chg), val: (r) => r.chg },
    { key: "wtd", label: termLabel("本周", "本周涨跌"), num: true, fmt: (r) => (r.idle_week ? `<span class="muted">休市</span>` : pctS(r.wtd)), val: (r) => r.wtd },
    { key: "m1", label: "近1月", num: true, fmt: (r) => pctS(r.m1), val: (r) => r.m1 },
    { key: "ma", label: termLabel("临界值"), num: true, fmt: (r) => num(r.ma), val: (r) => r.ma },
    { key: "status", label: `${termLabel("状态")} / ${termLabel("信号")}`, fmt: (r) => `${statusTag(r.status)} ${sigTag(r.signal)}`, val: (r) => (r.status === "YES" ? 1 : 0) },
    { key: "dev", label: termLabel("偏离度"), fmt: (r) => devBar(r.dev), val: (r) => r.dev },
    ...(hasVal ? [{ key: "pe", label: termLabel("PE 百分位"), num: true, fmt: (r) => valCell(r.val), val: (r) => r.val?.pe_pct, title: "市盈率在自身历史中的百分位，越低越便宜；悬停看 PE、PB 和日期" }] : []),
    { key: "spark", label: "近 60 日偏离度", fmt: (r) => spark(r.spark) },
    { key: "slope", label: termLabel("均线方向"), num: true, fmt: (r) => (ok(r.ma_slope) ? `${r.ma_slope > 0.002 ? "↗" : r.ma_slope < -0.002 ? "↘" : "→"} ${pctS(r.ma_slope, 1)}` : DASH), val: (r) => r.ma_slope, title: "20 日均线最近 5 个交易日的变化" },
    { key: "days", label: termLabel("状态持续"), num: true, fmt: (r) => `${r.days} 天<div class="small muted">自 ${esc(r.since)}</div>`, val: (r) => r.days },
    { key: "flips", label: termLabel("近一年切换"), num: true, fmt: (r) => `${r.flips_1y} 次`, val: (r) => r.flips_1y },
  ];
  return cols;
}

function rankRows(rows) {
  return rows.slice().sort((a, b) => (b.dev ?? -9) - (a.dev ?? -9)).map((r, i) => ({ ...r, rank: i + 1 }));
}

function macroCard(m, compact = true) {
  if (!m) return "";
  const x = m.dxy;
  const bondRows = (m.bonds || []).map((b) => `<tr><td><b>${b.term}</b></td>
    <td class="num">${yieldS(b.cn)}</td><td class="num">${bpS(b.cn_wtd)}</td>${compact ? "" : `<td class="num">${bpS(b.cn_m1)}</td>`}
    <td class="num">${yieldS(b.us)}</td><td class="num">${bpS(b.us_wtd)}</td>${compact ? "" : `<td class="num">${bpS(b.us_m1)}</td>`}
    <td class="num">${bpS(b.spread)}</td></tr>`).join("");
  return `
    <div class="macro-grid">
      <div>
        <h3>中美${termLabel("国债收益率")} <small class="muted">截至 ${esc(m.bond_date || "—")}</small></h3>
        <div class="table-wrap"><table class="tbl compact">
          <thead><tr><th>期限</th><th class="num">中国</th><th class="num">本周</th>${compact ? "" : `<th class="num">近1月</th>`}
            <th class="num">美国</th><th class="num">本周</th>${compact ? "" : `<th class="num">近1月</th>`}<th class="num">${termLabel("中美利差")}</th></tr></thead>
          <tbody>${bondRows}</tbody></table></div>
        <p class="small muted" style="margin-top:8px">${termLabel("期限利差")}（10年−2年）：美国 ${bpS(m.us_curve)}，中国 ${bpS(m.cn_curve)}。收益率单位为 %，变化单位为${termLabel("基点")}。</p>
      </div>
      ${x ? `<div class="dxy">
        <h3>${termLabel("美元指数")} <small class="muted">截至 ${esc(x.date)}</small></h3>
        <div class="dxy-val">${num(x.price)}</div>
        <div class="kv-row">
          <div class="kv"><small>当日</small><b>${pctS(x.chg)}</b></div>
          <div class="kv"><small>本周</small><b>${pctS(x.wtd)}</b></div>
          <div class="kv"><small>近1月</small><b>${pctS(x.m1)}</b></div>
        </div>
        <p class="small" style="margin-top:10px">${x.status === "YES" ? "高于" : "低于"} 20 日均线 ${num(x.ma)}（${pctS(x.dev)}），自 ${esc(x.since)} 起${x.status === "YES" ? "走强" : "走弱"}</p>
      </div>` : ""}
    </div>`;
}

async function renderOverview(token, asof) {
  const d = await api(`/api/overview${asof ? `?asof=${asof}` : ""}`);
  if (token !== state.token) return;
  const isPast = !!asof;
  app.innerHTML = `
    <section class="card filters">
      <div class="frow">
        <span class="fitem">${segButtons("ver", [["simple", "精简版"], ["full", "完整版"]], prefs.version)}</span>
        <label class="fitem">${termLabel("回看")} <select id="asof">${weekOptions(asof)}</select></label>
        <span class="grow"></span>
        <button class="btn" id="btnEdit" title="选择精简版包含哪些标的；AI 周报默认读取精简版">编辑精简版</button>
        <a class="btn" id="btnShot" target="_blank" title="原 review 模块风格的汇总页，适合截图放进周报">截图版 ↗</a>
        <button class="btn primary" id="btnCopy" title="复制给 AI 写周报用的 Markdown（三张表 + 本周变化）">复制 AI 素材</button>
      </div>
      ${isPast ? `<div class="notice">正在回看 <b>${esc(d.date)}</b> 那一周：所有数值都按当时能看到的数据重新计算。<a href="#/">回到本周</a></div>` : ""}
    </section>
    <section class="card summary" id="summary"></section>
    <section class="card"><div class="card-head"><h2>本周要点 <small class="muted">${esc(d.week_start)} ~ ${esc(d.date)}</small></h2>
      <span class="small muted">按周报的市场分段汇总，自动生成</span></div><div id="insights"></div></section>
    <section class="card">
      <div class="card-head"><h2>全球股市</h2><span class="small muted">按${termLabel("偏离度")}由强到弱排名；点击一行看走势和历次状态转变</span></div>
      <div id="tStock"></div>
    </section>
    <section class="card">
      <div class="card-head"><h2>大宗商品</h2></div>
      <div id="tCom"></div>
    </section>
    <section class="card" id="cardWatch">
      <div class="card-head"><h2>${termLabel("行业与个股")}</h2><span class="small muted">单独排名，不计入上面的 YES 统计；个股按前复权价格计算</span></div>
      <div id="tWatch"></div>
    </section>
    <section class="card">
      <div class="card-head"><h2>美元指数与国债收益率</h2><a class="go" href="#/macro">看走势 →</a></div>
      ${macroCard(d.macro)}
    </section>`;

  const draw = () => {
    const rows = visible(d.rows, d.simple);
    const stocks = rankRows(rows.filter((r) => r.kind === "stock"));
    const coms = rankRows(rows.filter((r) => r.kind === "commodity"));
    const watch = rankRows(rows.filter((r) => r.kind === "watch"));
    drawSummary(d, stocks, coms);
    $("#insights").innerHTML = insights(rows, state.meta.groups);
    const rowClass = (r) => (r.changed_today || r.changed_week ? "hl" : "");
    sortableTable($("#tStock"), instCols("stock", stocks), stocks, { onRow: openInst, rowClass, sortState: (state.sorts.stock ??= {}), tblClass: "inst" });
    sortableTable($("#tCom"), instCols("commodity", coms), coms, { onRow: openInst, rowClass, sortState: (state.sorts.com ??= {}), tblClass: "inst" });
    $("#cardWatch").hidden = !watch.length;
    if (watch.length) sortableTable($("#tWatch"), instCols("watch", watch), watch, { onRow: openInst, rowClass, sortState: (state.sorts.watch ??= {}), tblClass: "inst" });
    const ver = prefs.version;
    $("#btnShot").href = `/report/${ver}${asof ? `?asof=${asof}` : ""}`;
  };

  const drawSummary = (d, stocks, coms) => {
    const all = stocks.concat(coms);
    const yesS = stocks.filter((r) => r.status === "YES").length;
    const yesC = coms.filter((r) => r.status === "YES").length;
    const ups = all.filter((r) => r.changed_week && r.status === "YES");
    const downs = all.filter((r) => r.changed_week && r.status === "NO");
    const names = (xs) => (xs.length ? xs.map((r) => `<a href="#/i/${encodeURIComponent(r.code)}">${esc(r.name)}</a>`).join("、") : `<span class="muted">无</span>`);
    const x = d.macro?.dxy, ten = (d.macro?.bonds || []).find((b) => b.term === "10年");
    $("#summary").innerHTML = `
      <div class="stat"><small>股市 YES</small><b>${yesS} / ${stocks.length}</b>
        <span class="yesbar"><i style="width:${stocks.length ? (yesS / stocks.length) * 100 : 0}%"></i></span></div>
      <div class="stat"><small>商品 YES</small><b>${yesC} / ${coms.length}</b>
        <span class="yesbar"><i style="width:${coms.length ? (yesC / coms.length) * 100 : 0}%"></i></span></div>
      <div class="stat"><small>本周转为 YES</small><span class="names">${names(ups)}</span></div>
      <div class="stat"><small>本周转为 NO</small><span class="names">${names(downs)}</span></div>
      <div class="stat"><small>美元指数</small><b>${x ? num(x.price) : "—"}</b><span class="small">本周 ${x ? pctS(x.wtd) : DASH}</span></div>
      <div class="stat"><small>美债 10 年</small><b>${ten ? yieldS(ten.us) : "—"}</b><span class="small">本周 ${ten ? bpS(ten.us_wtd) : DASH} · 利差 ${ten ? bpS(ten.spread) : DASH}</span></div>`;
  };

  draw();
  onSeg(app, "ver", (v) => { prefs.version = v; savePrefs(); draw(); });
  $("#asof").onchange = (e) => nav(e.target.value ? `#/at/${e.target.value}` : "#/");
  $("#btnEdit").onclick = () => openSimpleEditor(d.simple);
  $("#btnCopy").onclick = async () => {
    try {
      const text = await api(`/api/material?version=${prefs.version}${asof ? `&asof=${asof}` : ""}`);
      await copyText(text);
      toast(`已复制${prefs.version === "simple" ? "精简版" : "完整版"}素材（${text.length} 字），可以直接粘贴给 AI`, "ok");
    } catch (e) {
      toast(`复制失败：${e.message}`, "warn");
    }
  };
}

function openSimpleEditor(current) {
  const set = new Set(current);
  const insts = state.meta.instruments;
  const modal = $("#modal");
  modal.innerHTML = `<div class="modal-box wide">
    <h2>编辑精简版</h2>
    <div class="modal-body">
      <p class="small muted">精简版是周报默认使用的版本，AI 读取的 outputs/latest_review_simple.md 也按这里的选择生成。保存后立即重写该文件。</p>
      ${state.meta.groups.map((g) => `<div class="pick-group"><div class="pick-title">${groupDot(g)}${g}</div><div class="pick-items">
        ${insts.filter((x) => x.group === g).map((x) => `<label class="pick"><input type="checkbox" value="${esc(x.code)}" ${set.has(x.code) ? "checked" : ""}> ${esc(x.name)}</label>`).join("")}
      </div></div>`).join("")}
    </div>
    <div class="modal-foot">
      <button class="btn ghost" data-act="reset">恢复默认</button>
      <span><button class="btn" data-act="cancel">取消</button><button class="btn primary" data-act="save">保存</button></span>
    </div></div>`;
  modal.hidden = false;
  modal.onclick = async (e) => {
    const act = e.target.dataset?.act;
    if (e.target === modal || act === "cancel") { modal.hidden = true; return; }
    if (act !== "save" && act !== "reset") return;
    try {
      const codes = $$("input:checked", modal).map((x) => x.value);
      if (act === "save" && !codes.length) { toast("精简版至少要保留一个标的", "warn"); return; }
      const r = act === "save"
        ? await api("/api/simple", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(codes) })
        : await api("/api/simple", { method: "DELETE" });
      state.meta.simple = r.simple;
      modal.hidden = true;
      toast(act === "save" ? `精简版已保存（${r.simple.length} 个标的），outputs 下的汇总已重写` : "已恢复默认的精简版", "ok");
      render();
    } catch (err) {
      toast(`保存失败：${err.message}`, "warn");
    }
  };
}

/* ================= 近期走势（周度对比） ================= */

function heatColor(v) {
  if (!ok(v)) return "transparent";
  const a = Math.min(Math.abs(v) / 0.1, 1) * 0.55 + 0.06;
  return v >= 0 ? `rgba(217,54,62,${a.toFixed(2)})` : `rgba(24,147,90,${a.toFixed(2)})`;
}

async function renderWeeks(token, asof) {
  const n = [8, 12, 26].includes(+prefs.wn) ? +prefs.wn : 8;
  const [w, ov] = await Promise.all([api(`/api/weeks?n=${n}${asof ? `&asof=${asof}` : ""}`), api(`/api/overview${asof ? `?asof=${asof}` : ""}`)]);
  if (token !== state.token) return;
  app.innerHTML = `
    <section class="card filters">
      <div class="frow">
        <span class="fitem">${segButtons("ver", [["simple", "精简版"], ["full", "完整版"]], prefs.version)}</span>
        <span class="fitem">显示 ${segButtons("wmode", [["dev", "偏离度"], ["wret", "周涨跌"]], prefs.wmode)}</span>
        <span class="fitem">${segButtons("wn", [["8", "8 周"], ["12", "12 周"], ["26", "半年"]], n)}</span>
        <label class="fitem">截至 <select id="asof">${weekOptions(asof)}</select></label>
      </div>
    </section>
    <section class="card">
      <div class="card-head"><h2>每周末的状态</h2><span class="small muted">每格是当周最后一个交易日；红色 = 在临界值上方（YES），绿色 = 下方（NO），颜色越深偏离越大；带框的格子表示较前一周发生了状态转变</span></div>
      <div id="heat"></div>
    </section>
    <section class="card">
      <div class="card-head"><h2>宏观</h2><span class="small muted">美元指数为周涨跌，国债收益率为周变化（基点）</span></div>
      <div id="heatMacro"></div>
    </section>
    <section class="card">
      <div class="card-head"><h2>本周 vs 上周</h2><span class="small muted">${esc(ov.week_start)} ~ ${esc(ov.date)}</span></div>
      <div id="wk"></div>
    </section>`;

  const draw = () => {
    const set = new Set(ov.simple);
    const rows = w.rows.filter((r) => prefs.version === "full" || set.has(r.code));
    const heads = w.weeks.map((x) => `<th class="num" title="${x.start} ~ ${x.end}">${x.end.slice(5)}</th>`).join("");
    const body = state.meta.groups.map((g) => {
      const xs = rows.filter((r) => r.group === g);
      if (!xs.length) return "";
      return `<tr class="group"><td colspan="${w.weeks.length + 1}">${groupDot(g)}${g}</td></tr>` + xs.map((r) => `<tr class="link" data-code="${esc(r.code)}">
        <td class="sticky-col"><b>${esc(r.name)}</b></td>
        ${r.cells.map((c) => {
          if (!c) return `<td class="hcell">${DASH}</td>`;
          const v = prefs.wmode === "dev" ? c.dev : c.wret;
          const tip = `${c.date} · ${c.status} · 偏离度 ${(c.dev * 100).toFixed(2)}%${ok(c.wret) ? ` · 周涨跌 ${(c.wret * 100).toFixed(2)}%` : ""}${c.idle ? " · 当周休市" : ""}`;
          return `<td class="hcell num${c.flip ? " flip" : ""}${c.idle ? " idle" : ""}" style="background:${heatColor(c.dev)}" title="${esc(tip)}">
            ${ok(v) ? `${v > 0 ? "+" : ""}${(v * 100).toFixed(1)}%` : "—"}${c.flip ? `<span class="flip-mark">${c.status === "YES" ? "↑" : "↓"}</span>` : ""}</td>`;
        }).join("")}</tr>`).join("");
    }).join("");
    $("#heat").innerHTML = `<div class="table-wrap"><table class="tbl heat"><thead><tr><th class="sticky-col">名称</th>${heads}</tr></thead><tbody>${body}</tbody></table></div>`;
    $$("#heat tr[data-code]").forEach((tr) => tr.onclick = () => openInst(tr.dataset.code));
    $("#heatMacro").innerHTML = `<div class="table-wrap"><table class="tbl heat"><thead><tr><th class="sticky-col">序列</th>${heads}</tr></thead><tbody>
      ${w.macro.map((m) => `<tr><td class="sticky-col"><b>${esc(m.label)}</b></td>${m.cells.map((c) => `<td class="num">
        ${ok(c.value) ? (m.unit === "pct" ? num(c.value) : `${num(c.value)}%`) : "—"}<div class="small">${m.unit === "pct" ? pctS(c.chg, 1) : bpS(c.chg)}</div></td>`).join("")}</tr>`).join("")}
      </tbody></table></div>`;
    const vis = visible(ov.rows, ov.simple);
    sortableTable($("#wk"), [
      { key: "name", label: "名称", fmt: (r) => `${groupDot(r.group)}${nameCell(r)}` },
      { key: "wtd", label: termLabel("本周涨跌"), num: true, fmt: (r) => (r.idle_week ? `<span class="muted">休市</span>` : pctS(r.wtd)), val: (r) => r.wtd },
      { key: "st", label: "上周末 → 本周", fmt: (r) => `${statusTag(r.prev_status)} → ${statusTag(r.status)}`, val: (r) => (r.changed_week ? 1 : 0) },
      { key: "pd", label: "上周末偏离度", num: true, fmt: (r) => pctS(r.prev_dev), val: (r) => r.prev_dev },
      { key: "dev", label: "本周偏离度", num: true, fmt: (r) => pctS(r.dev), val: (r) => r.dev },
      { key: "dd", label: "变化", num: true, fmt: (r) => (ok(r.dev) && ok(r.prev_dev) ? signed((r.dev - r.prev_dev) * 100, 2, " 个百分点") : DASH), val: (r) => (ok(r.dev) && ok(r.prev_dev) ? r.dev - r.prev_dev : null) },
    ], vis, { onRow: openInst, rowClass: (r) => (r.changed_week ? "hl" : ""), sortState: (state.sorts.wk ??= {}) });
  };
  draw();
  onSeg(app, "ver", (v) => { prefs.version = v; savePrefs(); draw(); });
  onSeg(app, "wmode", (v) => { prefs.wmode = v; savePrefs(); draw(); });
  onSeg(app, "wn", (v) => { prefs.wn = +v; savePrefs(); render(); });
  $("#asof").onchange = (e) => nav(e.target.value ? `#/weeks/${e.target.value}` : "#/weeks");
}

/* ================= 标的详情 ================= */

const RANGES = [["m3", "3 月", 92], ["m6", "6 月", 183], ["y1", "1 年", 365], ["y3", "3 年", 1096], ["all", "全部", 1e5]];

async function renderInst(token, code) {
  const d = await api(`/api/instrument/${encodeURIComponent(code)}`);
  if (token !== state.token) return;
  const r = d.row, s = d.stats;
  if (!RANGES.some(([k]) => k === prefs.range)) prefs.range = "y1";
  app.innerHTML = `
    <div class="crumb"><a href="#/">总览</a> / ${esc(r.group)} / ${esc(r.name)}</div>
    <section class="card">
      <div class="head-row">
        <div>
          <div class="eyebrow">${groupDot(r.group)}${esc(r.region)} · ${esc(r.code)} · 数据截至 ${esc(r.date)}</div>
          <h1>${esc(r.name)} ${statusTag(r.status)} ${sigTag(r.signal)} ${badges(r)}</h1>
          <p class="sub">${r.status === "YES" ? "收盘价在临界值上方" : "收盘价在临界值下方"}，已持续 <b>${r.days}</b> 个交易日（自 ${esc(r.since)}），本轮涨跌 ${pctS(r.run_ret)}。</p>
        </div>
        <div class="kv-row">
          <div class="kv"><small>现价</small><b>${num(r.price)}</b><span>当日 ${pctS(r.chg)}</span></div>
          <div class="kv"><small>${termLabel("临界值")}</small><b>${num(r.ma)}</b><span>${termLabel("均线方向")} ${pctS(r.ma_slope, 1)}</span></div>
          <div class="kv"><small>${termLabel("偏离度")}</small><b>${pctS(r.dev)}</b><span>上周末 ${pctS(r.prev_dev)}</span></div>
          <div class="kv"><small>本周</small><b>${r.idle_week ? "休市" : pctS(r.wtd)}</b><span>近1月 ${pctS(r.m1)}</span></div>
          <div class="kv"><small>今年以来</small><b>${pctS(r.ytd)}</b><span>&nbsp;</span></div>
          ${r.val && ok(r.val.pe_pct) ? `<div class="kv" title="${esc(valTip(r.val))}"><small>${termLabel("PE 百分位")}</small><b>${pctInt(r.val.pe_pct)}</b>
            <span>PE ${num(r.val.pe, 1)} · PB 百分位 ${pctInt(r.val.pb_pct)}${r.val.ref ? ` · 参照${esc(r.val.ref)}` : ""}</span></div>` : ""}
        </div>
      </div>
    </section>
    <section class="card">
      <div class="card-head"><h2>价格与临界值</h2><div class="chart-tools">${segButtons("range", RANGES.map(([k, t]) => [k, t]), prefs.range)}</div></div>
      <div id="cPrice" class="chart"></div>
      <div id="cDev" class="chart short"></div>
      <p class="small muted">上图浅红底色为 YES 区间；下图是每天的偏离度，零轴就是临界值。</p>
    </section>
    <section class="card">
      <div class="card-head"><h2>近一年的状态特征</h2></div>
      <div class="stat-row six">
        <div class="stat"><small>YES 天数占比</small><b>${ok(s.yes_ratio_1y) ? `${Math.round(s.yes_ratio_1y * 100)}%` : "—"}</b></div>
        <div class="stat"><small>${termLabel("近一年切换")}</small><b>${s.flips_1y} 次</b></div>
        <div class="stat"><small>YES 平均持续</small><b>${num(s.avg_yes_days, 1)} 天</b></div>
        <div class="stat"><small>NO 平均持续</small><b>${num(s.avg_no_days, 1)} 天</b></div>
        <div class="stat"><small>最大偏离度</small><b>${pctS(s.dev_max_1y)}</b></div>
        <div class="stat"><small>最小偏离度</small><b>${pctS(s.dev_min_1y)}</b></div>
      </div>
      <p class="small muted" style="margin-top:10px">切换越频繁、平均持续越短，说明这个标的常在临界值附近来回震荡，鱼盆信号容易“打脸”；反之趋势性更好。</p>
    </section>
    <div class="grid2">
      <section class="card"><div class="card-head"><h2>近 12 周</h2></div><div id="tWeeks"></div></section>
      <section class="card"><div class="card-head"><h2>历次状态区间</h2><span class="small muted" id="runsNote"></span></div><div id="tRuns"></div>
        <div class="more"><button class="btn" id="btnRuns">展开更早的区间</button></div></section>
    </div>`;

  const drawCharts = () => {
    disposeCharts();
    const days = RANGES.find(([k]) => k === prefs.range)[2];
    const h = d.hist;
    const cut = new Date(new Date(h.dates[h.dates.length - 1]).getTime() - days * 864e5).toISOString().slice(0, 10);
    let i0 = h.dates.findIndex((x) => x >= cut);
    if (i0 < 0) i0 = 0;
    const dates = h.dates.slice(i0), close = h.close.slice(i0), ma = h.ma.slice(i0), dev = h.dev.slice(i0);
    const areas = [];
    let st = null;
    dev.forEach((v, i) => {
      const yes = v > 0;
      if (yes && st == null) st = i;
      if ((!yes || i === dev.length - 1) && st != null) { areas.push([{ xAxis: dates[st] }, { xAxis: dates[yes ? i : i - 1] }]); st = null; }
    });
    const grid = { left: 56, right: 20, top: 30, bottom: 30 };
    const c1 = makeChart($("#cPrice"));
    c1.setOption({
      animation: false, grid, legend: { top: 0, data: ["收盘价", "临界值（MA20）"] },
      tooltip: { trigger: "axis", valueFormatter: (v) => num(v) },
      xAxis: { type: "category", data: dates, ...AXIS_STYLE, boundaryGap: false },
      yAxis: { type: "value", scale: true, ...AXIS_STYLE },
      series: [
        { name: "收盘价", type: "line", data: close, symbol: "none", lineStyle: { width: 1.6, color: C_BRAND }, itemStyle: { color: C_BRAND },
          markArea: { silent: true, itemStyle: { color: "rgba(217,54,62,.07)" }, data: areas } },
        { name: "临界值（MA20）", type: "line", data: ma, symbol: "none", lineStyle: { width: 1.2, type: "dashed", color: C_WARM }, itemStyle: { color: C_WARM } },
      ],
    });
    const c2 = makeChart($("#cDev"));
    c2.setOption({
      animation: false, grid: { ...grid, top: 16 },
      tooltip: { trigger: "axis", valueFormatter: (v) => `${(v * 100).toFixed(2)}%` },
      xAxis: { type: "category", data: dates, ...AXIS_STYLE },
      yAxis: { type: "value", ...AXIS_STYLE, axisLabel: { ...AXIS_STYLE.axisLabel, formatter: (v) => `${(v * 100).toFixed(0)}%` } },
      series: [{ name: "偏离度", type: "bar", data: dev.map((v) => ({ value: v, itemStyle: { color: v >= 0 ? C_UP : C_DOWN } })), barCategoryGap: "10%" }],
    });
    echarts.connect([c1, c2]);
  };
  drawCharts();
  onSeg(app, "range", (v) => { prefs.range = v; savePrefs(); drawCharts(); });

  if (d.weeks) {
    const wr = d.weeks.weeks.map((w, i) => ({ ...w, ...(d.weeks.cells[i] || {}) })).reverse();
    sortableTable($("#tWeeks"), [
      { key: "end", label: "周末", fmt: (x) => esc(x.end) },
      { key: "st", label: "状态", fmt: (x) => `${statusTag(x.status)}${x.flip ? ` <span class="badge amber">转变</span>` : ""}` },
      { key: "dev", label: "偏离度", num: true, fmt: (x) => pctS(x.dev) },
      { key: "wret", label: "周涨跌", num: true, fmt: (x) => (x.idle ? `<span class="muted">休市</span>` : pctS(x.wret)) },
    ], wr, { tblClass: "compact" });
  }
  const runCols = [
    { key: "status", label: "状态", fmt: (x) => statusTag(x.status) },
    { key: "start", label: "区间", fmt: (x) => `${esc(x.start)} ~ ${x.end === r.date && x.start === r.since ? "至今" : esc(x.end)}` },
    { key: "days", label: "天数", num: true, fmt: (x) => x.days },
    { key: "ret", label: "区间涨跌", num: true, fmt: (x) => pctS(x.ret) },
    { key: "peak", label: "偏离度区间", num: true, fmt: (x) => `${pctS(x.trough, 1)} ~ ${pctS(x.peak, 1)}` },
  ];
  const drawRuns = (all) => {
    const xs = all ? d.runs : d.runs.slice(0, 12);
    sortableTable($("#tRuns"), runCols, xs, { tblClass: "compact" });
    $("#runsNote").textContent = xs.length === d.runs.length ? `全部 ${xs.length} 段` : `最近 ${xs.length} 段，共 ${d.runs.length} 段`;
    $("#btnRuns").parentElement.hidden = all || d.runs.length <= 12;
  };
  drawRuns(false);
  $("#btnRuns").onclick = () => drawRuns(true);
}

/* ================= 宏观 ================= */

async function renderMacro(token) {
  const m = await api("/api/macro");
  if (token !== state.token) return;
  const terms = ["2年", "5年", "10年", "30年"];
  if (!terms.includes(prefs.term)) prefs.term = "10年";
  app.innerHTML = `
    <section class="card">
      <div class="card-head"><h2>最新读数</h2><span class="small muted">截至 ${esc(m.bond_date || m.date)}</span></div>
      ${macroCard(m, false)}
    </section>
    <section class="card">
      <div class="card-head"><h2>${termLabel("美元指数")}</h2><span class="small muted">近 3 年；虚线为 20 日均线</span></div>
      <div id="cDxy" class="chart"></div>
    </section>
    <section class="card">
      <div class="card-head"><h2>中美${termLabel("国债收益率")}</h2><div class="chart-tools">${segButtons("term", terms.map((t) => [t, t]), prefs.term)}</div></div>
      <div id="cYield" class="chart"></div>
      <div id="cSpread" class="chart short"></div>
      <p class="small muted">收益率是利率而不是价格：上升对股票估值是压力，所以不套用鱼盆的 YES / NO 信号。下图是同期限的中美利差（中国 − 美国，基点）。</p>
    </section>`;
  if (m.dxy_hist) {
    const c = makeChart($("#cDxy"));
    c.setOption({
      animation: false, grid: { left: 50, right: 20, top: 30, bottom: 60 }, legend: { top: 0 },
      tooltip: { trigger: "axis", valueFormatter: (v) => num(v) },
      xAxis: { type: "category", data: m.dxy_hist.dates, ...AXIS_STYLE, boundaryGap: false },
      yAxis: { type: "value", scale: true, ...AXIS_STYLE },
      dataZoom: [{ type: "slider", start: 67, end: 100, height: 18, bottom: 12 }, { type: "inside" }],
      series: [
        { name: "美元指数", type: "line", data: m.dxy_hist.close, symbol: "none", lineStyle: { width: 1.6, color: C_BRAND }, itemStyle: { color: C_BRAND } },
        { name: "20 日均线", type: "line", data: m.dxy_hist.ma, symbol: "none", lineStyle: { width: 1.2, type: "dashed", color: C_WARM }, itemStyle: { color: C_WARM } },
      ],
    });
  }
  const drawYield = () => {
    state.charts.filter((c) => c.getDom().id !== "cDxy").forEach((c) => c.dispose());
    state.charts = state.charts.filter((c) => !c.isDisposed());
    const cn = m.bond_hist[`CN${prefs.term}`] || [], us = m.bond_hist[`US${prefs.term}`] || [];
    const map = new Map();
    cn.forEach(([dt, v]) => map.set(dt, { cn: v }));
    us.forEach(([dt, v]) => map.set(dt, { ...(map.get(dt) || {}), us: v }));
    const dates = [...map.keys()].sort();
    const ffill = (k) => { let last = null; return dates.map((dt) => { const v = map.get(dt)[k]; if (v != null) last = v; return last; }); };
    const cnv = ffill("cn"), usv = ffill("us");
    const spread = dates.map((_, i) => (cnv[i] != null && usv[i] != null ? +((cnv[i] - usv[i]) * 100).toFixed(1) : null));
    const zoom = [{ type: "slider", start: 67, end: 100, height: 18, bottom: 12 }, { type: "inside" }];
    const c1 = makeChart($("#cYield"));
    c1.setOption({
      animation: false, grid: { left: 50, right: 20, top: 30, bottom: 60 }, legend: { top: 0 },
      tooltip: { trigger: "axis", valueFormatter: (v) => (v == null ? "—" : `${num(v)}%`) },
      xAxis: { type: "category", data: dates, ...AXIS_STYLE, boundaryGap: false },
      yAxis: { type: "value", scale: true, ...AXIS_STYLE, axisLabel: { ...AXIS_STYLE.axisLabel, formatter: "{value}%" } },
      dataZoom: zoom,
      series: [
        { name: `中国${prefs.term}`, type: "line", data: cnv, symbol: "none", lineStyle: { width: 1.6, color: C_UP }, itemStyle: { color: C_UP } },
        { name: `美国${prefs.term}`, type: "line", data: usv, symbol: "none", lineStyle: { width: 1.6, color: C_BRAND }, itemStyle: { color: C_BRAND } },
      ],
    });
    const c2 = makeChart($("#cSpread"));
    c2.setOption({
      animation: false, grid: { left: 50, right: 20, top: 16, bottom: 60 },
      tooltip: { trigger: "axis", valueFormatter: (v) => (v == null ? "—" : `${v}bp`) },
      xAxis: { type: "category", data: dates, ...AXIS_STYLE, boundaryGap: false },
      yAxis: { type: "value", ...AXIS_STYLE, axisLabel: { ...AXIS_STYLE.axisLabel, formatter: "{value}bp" } },
      dataZoom: zoom,
      series: [{ name: "中美利差", type: "line", data: spread, symbol: "none", areaStyle: { opacity: 0.12 }, lineStyle: { width: 1.4, color: "#6b7482" }, itemStyle: { color: "#6b7482" } }],
    });
    echarts.connect([c1, c2]);
  };
  drawYield();
  onSeg(app, "term", (v) => { prefs.term = v; savePrefs(); drawYield(); });
}

/* ================= 周报存档 ================= */

const KIND_TAG = { "周报": "blue", "新闻候选": "amber" };
const reviewLabel = (x) => `${x.date || x.name}${x.note ? `（${x.note}）` : ""}`;

/** 周报日期（通常是周日）对应的那一周：不晚于该日期的最后一个周末交易日 */
function weekFor(date) {
  const ends = state.meta?.week_ends || [];
  let hit = null;
  ends.forEach((e) => { if (e <= date) hit = e; });
  return hit;
}

async function renderReviews(token) {
  const list = await api("/api/reviews");
  if (token !== state.token) return;
  const byDate = new Map();
  list.forEach((x) => {
    const k = x.date || "其他";
    if (!byDate.has(k)) byDate.set(k, []);
    byDate.get(k).push(x);
  });
  app.innerHTML = `
    <section class="card">
      <div class="card-head"><h2>本周 AI 素材</h2><span class="small muted">数据截至 ${esc(state.status?.data_date || "—")}</span></div>
      <p>写周报时，把素材交给 AI，并让它按 <code>prompts/</code> 下 <code>鱼盆模型周度复盘模版.md</code> 和 <code>review_preferences.md</code> 的要求先出新闻候选、再写正文。素材每次刷新都会自动写到 <code>outputs/latest_review_simple.md</code>，AI 也可以直接读这个文件。</p>
      <div class="frow" style="margin-top:10px">
        ${segButtons("ver", [["simple", "精简版"], ["full", "完整版"]], prefs.version)}
        <button class="btn primary" id="mCopy">复制素材</button>
        <button class="btn" id="mDown">下载 .md</button>
        <button class="btn" id="mView">预览</button>
        <a class="btn" id="mShot" target="_blank">截图版 ↗</a>
      </div>
      <div id="mPrev" class="md" hidden></div>
    </section>
    <section class="card">
      <div class="card-head"><h2>历史周报</h2><span class="small muted">outputs 目录下 AI 写的周报和新闻候选，共 ${list.length} 份</span></div>
      ${list.length ? `<div class="table-wrap"><table class="tbl">
        <thead><tr><th>日期</th><th>类型</th><th>标题</th><th>当周数据</th></tr></thead>
        <tbody>${[...byDate.entries()].map(([dt, xs]) => xs.map((x, i) => `<tr class="link" data-name="${esc(x.name)}">
          <td>${i === 0 ? esc(dt) : ""}</td>
          <td><span class="badge ${KIND_TAG[x.kind]}">${x.kind}</span>${x.note ? ` <small class="muted">${esc(x.note)}</small>` : ""}</td>
          <td class="wrap">${esc(x.title || x.name)}</td>
          <td>${x.date && weekFor(x.date) ? `<a href="#/at/${weekFor(x.date)}" title="回看 ${weekFor(x.date)} 那一周的总览">回看 ${weekFor(x.date).slice(5)}</a>` : DASH}</td>
        </tr>`).join("")).join("")}</tbody></table></div>`
        : `<p class="muted">还没有周报。AI 写好的 weekly_review_YYYYMMDD.md 和 news_candidates_YYYYMMDD.md 放在 outputs 目录下就会出现在这里。</p>`}
    </section>`;
  $$("tr[data-name]").forEach((tr) => tr.onclick = (e) => { if (!e.target.closest("a")) nav(`#/reviews/${encodeURIComponent(tr.dataset.name)}`); });
  const mat = () => api(`/api/material?version=${prefs.version}`);
  const setShot = () => { $("#mShot").href = `/report/${prefs.version}`; };
  setShot();
  onSeg(app, "ver", async (v) => {
    prefs.version = v; savePrefs(); setShot();
    if (!$("#mPrev").hidden) $("#mPrev").innerHTML = renderMd(await mat());
  });
  $("#mCopy").onclick = async () => {
    try { const t = await mat(); await copyText(t); toast(`已复制素材（${t.length} 字）`, "ok"); } catch (e) { toast(`复制失败：${e.message}`, "warn"); }
  };
  $("#mDown").onclick = async () => {
    try {
      const t = await mat();
      download(`${prefs.version === "simple" ? "latest_review_simple" : "latest_review"}_${state.status?.data_date || ""}.md`, t);
    } catch (e) {
      toast(`下载失败：${e.message}`, "warn");
    }
  };
  $("#mView").onclick = async () => {
    const box = $("#mPrev");
    if (!box.hidden) { box.hidden = true; $("#mView").textContent = "预览"; return; }
    box.innerHTML = renderMd(await mat());
    box.hidden = false;
    $("#mView").textContent = "收起预览";
  };
}

async function renderReview(token, name) {
  const [text, list] = await Promise.all([api(`/api/reviews/${encodeURIComponent(name)}`), api("/api/reviews")]);
  if (token !== state.token) return;
  const me = list.find((x) => x.name === name) || {};
  const same = list.filter((x) => x.kind === me.kind);
  const i = same.findIndex((x) => x.name === name);
  const newer = same[i - 1], older = same[i + 1];
  const sib = list.filter((x) => x.date && x.date === me.date && x.name !== name);
  const wk = me.date ? weekFor(me.date) : null;
  app.innerHTML = `
    <div class="crumb"><a href="#/reviews">周报</a> / ${esc(me.kind || "")} ${esc(me.date ? reviewLabel(me) : "")}</div>
    <section class="card">
      <div class="card-head">
        <span>${me.kind ? `<span class="badge ${KIND_TAG[me.kind]}">${me.kind}</span>` : ""} <span class="muted small">${esc(name)}</span></span>
        <span class="chart-tools">
          ${sib.map((x) => `<a class="btn" href="#/reviews/${encodeURIComponent(x.name)}">${x.kind === me.kind ? `另一版${x.kind}${x.note ? `（${esc(x.note)}）` : ""}` : `同期${x.kind}`}</a>`).join("")}
          ${wk ? `<a class="btn" href="#/at/${wk}">回看当周数据（${wk.slice(5)}）</a>` : ""}
          <button class="btn" id="rCopy">复制原文</button>
        </span>
      </div>
      <article class="md">${renderMd(text)}</article>
      <div class="pager">
        ${newer ? `<a href="#/reviews/${encodeURIComponent(newer.name)}">← 较新：${esc(reviewLabel(newer))}</a>` : "<span></span>"}
        ${older ? `<a href="#/reviews/${encodeURIComponent(older.name)}">较早：${esc(reviewLabel(older))} →</a>` : "<span></span>"}
      </div>
    </section>`;
  $("#rCopy").onclick = async () => { await copyText(text); toast("已复制原文", "ok"); };
}

/* ================= 数据健康 ================= */

async function renderHealth(token) {
  const h = await api("/api/health");
  if (token !== state.token) return;
  const failed = h.failed || [];
  const stale = h.items.filter((x) => x.stale);
  const big = h.items.filter((x) => (x.big_moves || []).length);
  const statusOf = (x) => (x.ok === 0 ? `<span class="badge red" title="${esc(x.error || "")}">获取失败</span>`
    : x.stale ? `<span class="badge amber">未更新到最新</span>` : x.gap ? `<span class="badge amber">有断档</span>` : `<span class="badge ok">正常</span>`);
  app.innerHTML = `
    <section class="card">
      <div class="stat-row four">
        <div class="stat"><small>${termLabel("数据日期")}</small><b>${esc(h.date || "—")}</b></div>
        <div class="stat"><small>上次刷新</small><b>${esc(h.last_refresh || "从未")}</b><span class="small muted">${h.duration ? `用时 ${h.duration} 秒` : ""}</span></div>
        <div class="stat"><small>本次获取失败</small><b class="${failed.length ? "warn-text" : ""}">${failed.length} 项</b><span class="small muted">${esc(failed.join("、"))}</span></div>
        <div class="stat"><small>需要留意</small><b>${stale.length + big.length} 项</b><span class="small muted">未更新 ${stale.length} · ${termLabel("大幅波动")} ${big.length}</span></div>
      </div>
      <div class="notice" style="margin-top:14px">获取失败时保留数据库里的旧数据，表格和 AI 素材会标出“数据截至”；命令行更新会以失败状态退出，提醒 AI 不要把旧数据当作最新行情。
        单日涨跌超过 ${Math.round(h.thresholds.big * 100)}% 的日子列在下面，多数是真实行情，偶尔是数据源的问题，可到行情软件核对。</div>
    </section>
    <section class="card"><div class="card-head"><h2>指数、商品与个股</h2><span class="small muted">落后天数 = 整体数据日期 − 该标的最新日期（自然日）</span></div><div id="hInst"></div></section>
    <section class="card"><div class="card-head"><h2>美元指数、国债收益率与估值</h2><span class="small muted">估值只是参考，获取失败不影响命令行更新的退出码</span></div><div id="hMacro"></div></section>`;
  sortableTable($("#hInst"), [
    { key: "name", label: "名称", fmt: (x) => `${groupDot(x.group)}<b>${esc(x.name)}</b> <small class="muted">${esc(x.key)}</small>`, val: (x) => x.name },
    { key: "source", label: "来源", fmt: (x) => esc(x.source || "—"), val: (x) => x.source },
    { key: "rows", label: "条数", num: true, fmt: (x) => num(x.rows, 0), val: (x) => x.rows },
    { key: "first", label: "起始", fmt: (x) => esc(x.first || "—"), val: (x) => x.first },
    { key: "last", label: "最新", fmt: (x) => esc(x.last || "—"), val: (x) => x.last },
    { key: "lag", label: "落后", num: true, fmt: (x) => (ok(x.lag) ? `${x.lag} 天` : DASH), val: (x) => x.lag },
    { key: "gap", label: "近 120 天最大间隔", num: true, fmt: (x) => (ok(x.max_gap) ? `${x.max_gap} 天` : DASH), val: (x) => x.max_gap },
    { key: "big", label: "近 60 天大幅波动", fmt: (x) => ((x.big_moves || []).map((b) => `${b.date.slice(5)} ${pctS(b.ret, 1)}`).join("<br>") || `<span class="muted">无</span>`), val: (x) => (x.big_moves || []).length },
    { key: "st", label: "状态", fmt: (x) => `${statusOf(x)}${x.ok === 0 && x.error ? `<div class="small muted wrap">${esc(x.error)}</div>` : ""}`, val: (x) => (x.ok === 0 ? 3 : x.stale ? 2 : x.gap ? 1 : 0) },
  ], h.items, { tblClass: "health", sortState: (state.sorts.health ??= {}), onRow: openInst });
  sortableTable($("#hMacro"), [
    { key: "name", label: "序列", fmt: (x) => `<b>${esc(x.name)}</b>` },
    { key: "source", label: "来源", fmt: (x) => esc(x.source || "—") },
    { key: "rows", label: "条数", num: true, fmt: (x) => num(x.rows, 0) },
    { key: "first", label: "起始", fmt: (x) => esc(x.first || "—") },
    { key: "last", label: "最新", fmt: (x) => esc(x.last || "—") },
    { key: "lag", label: "落后", num: true, fmt: (x) => (ok(x.lag) ? `${x.lag} 天` : DASH) },
    { key: "st", label: "状态", fmt: (x) => `${statusOf(x)}${x.ok === 0 && x.error ? `<div class="small muted wrap">${esc(x.error)}</div>` : ""}` },
  ], h.macro, { tblClass: "health" });
}

/* ================= 术语 ================= */

async function renderGlossary(token) {
  if (token !== state.token) return;
  app.innerHTML = `
    <section class="card gl-search"><input id="glq" placeholder="搜索术语，例如：偏离度、利差" autocomplete="off"></section>
    <div class="gl-grid" id="gl"></div>`;
  const draw = (q) => {
    const xs = state.glossary.filter((g) => !q || [g.term, g.en, g.plain, g.why, ...(g.keys || [])].some((x) => x && x.toLowerCase().includes(q)));
    $("#gl").innerHTML = xs.map((g) => `<section class="card gl">
      <h3>${esc(g.term)}<small>${esc(g.en || "")}</small></h3>
      <p>${esc(g.plain)}</p><p><b>为什么要看：</b>${esc(g.why)}</p>${g.where ? `<p class="small muted">在哪里看到：${esc(g.where)}</p>` : ""}
    </section>`).join("") || `<section class="card empty">没有找到“${esc(q)}”相关的术语，换个关键词试试。</section>`;
  };
  draw("");
  $("#glq").oninput = (e) => draw(e.target.value.trim().toLowerCase());
}

/* ================= 使用指引 ================= */

function guideSteps() {
  return [
    {
      title: "这是什么",
      body: `<p>这是<b>鱼盆模型周度复盘</b>的本地网站：全球主要股指、大宗商品，以及几个 A 股行业指数和个股，每天按<b>收盘价在 20 日均线上方还是下方</b>判断 YES / NO，按偏离度排出强弱，并分成 5 档信号。</p>
        <p>数据来自新浪、中证、国证、台湾证交所、东方财富和腾讯，估值来自蛋卷基金。<b>每次启动服务都会自动更新</b>，并重写 <code>outputs/latest_review_simple.md</code> 供 AI 写周报。</p>`,
    },
    {
      title: "总览：本周发生了什么",
      body: `<p>顶部是 YES 个数、本周转为 YES / NO 的标的、美元和美债；下面的<b>本周要点</b>按周报的市场分段（A股、港股、美股、日韩台、商品）自动汇总。</p>
        <p>表格里的<b>本周</b>是真正的周涨跌（原来的汇总只有当日涨跌）；橙色底色表示本周发生了状态转变。点击任意一行看走势和历次转变。</p>`,
    },
    {
      title: "近期走势与回看",
      body: `<p><b>近期走势</b>页把最近 8–26 周每周末的状态排成一张热力表，哪些市场在转强、哪些在转弱一目了然。</p>
        <p>总览和近期走势都可以<b>回看</b>过去任意一周：按当时的数据重新计算，和当时看到的一致。想看以前某一周的情况时用它。</p>`,
    },
    {
      title: "写周报",
      body: `<p><b>周报</b>页可以复制、下载 AI 素材，或打开<b>截图版</b>（原来的汇总样式）。素材除了三张表，还有“本周变化”（本周涨跌、本周转变、美元和国债的周变化）。更早的走势在<b>近期走势</b>页看。</p>
        <p>AI 写好的周报和新闻候选放在 outputs 目录下，会自动出现在历史列表里，并能一键回看当周数据。</p>`,
    },
    {
      title: "精简版、数据健康和术语",
      body: `<p><b>精简版</b>是周报默认使用的标的组合，可以在总览页点“编辑精简版”修改。</p>
        <p><b>数据健康</b>页列出每个来源的条数、最新日期、断档和大幅波动；带虚线的词悬停可以看解释，完整列表在<b>术语</b>页。颜色按 A 股习惯：红涨绿跌，YES 为红、NO 为绿。</p>`,
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

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || $("#modal").hidden) return;
  if ($(".modal-step", $("#modal"))) closeGuide();
  else $("#modal").hidden = true;
});

/* ================= 路由与启动 ================= */

function renderNav(page) {
  const links = [["", "总览"], ["weeks", "近期走势"], ["macro", "宏观"], ["reviews", "周报"], ["health", "数据健康"], ["glossary", "术语"]];
  const cur = { at: "", i: "", weeks: "weeks", reviews: "reviews" }[page] ?? (page || "");
  $("#nav").innerHTML = links.map(([h, t]) => `<a href="#/${h}" class="${h === cur ? "on" : ""}">${t}</a>`).join("");
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

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
    if (!page) await renderOverview(token, null);
    else if (page === "at" && a && DATE_RE.test(a)) await renderOverview(token, a === state.meta.week_ends.at(-1) ? null : a);
    else if (page === "weeks") await renderWeeks(token, a && DATE_RE.test(a) && a !== state.meta.week_ends.at(-1) ? a : null);
    else if (page === "i" && a) await renderInst(token, a);
    else if (page === "macro") await renderMacro(token);
    else if (page === "reviews" && a) await renderReview(token, a);
    else if (page === "reviews") await renderReviews(token);
    else if (page === "health") await renderHealth(token);
    else if (page === "glossary") await renderGlossary(token);
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
      app.innerHTML = `<div class="card error"><h2>找不到</h2><p>${esc(e.message)}。</p>
        <p><a href="#/">返回总览</a></p></div>`;
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

/** 所有表格：放不下时横向滚动条吸附在窗口底部（原生滚动条隐藏，由代理滚动条同步）；表头滚出窗口后吸顶 */
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
  const sh = table?.tHead && !wrap.closest(".md, .modal") ? { wrap, ...stickyHead(wrap, table) } : null;
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
      <p class="muted">请双击 scripts/start_server.bat 启动服务，并通过 http://127.0.0.1:8325 打开页面（不要直接双击 index.html）。</p></div>`;
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

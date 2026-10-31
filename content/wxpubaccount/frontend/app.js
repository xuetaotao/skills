"use strict";

/* ================= 基础工具 ================= */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const app = $("#app");

const state = {
  meta: null, glossary: [], termRe: null, termIndex: {}, status: null, charts: [], token: 0,
  sorts: {}, polling: null, scrapeWasRunning: false, prefill: null, recTimer: null,
};

async function api(path, opts) {
  if (opts && opts.json !== undefined) {
    opts = { method: opts.method || "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(opts.json) };
  }
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
const ok = (v) => v != null && isFinite(v);
const DASH = `<span class="muted">—</span>`;
const n0 = (v) => (ok(v) ? Number(v).toLocaleString("zh-CN") : DASH);
const pct = (v, d = 1) => (ok(v) ? `${Number(v).toFixed(d)}%` : DASH);

function toast(text, kind = "ok", ms = 4000) {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = text;
  $("#toasts").appendChild(el);
  setTimeout(() => el.classList.add("out"), ms);
  setTimeout(() => el.remove(), ms + 400);
}

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

const PREF_KEY = "wxpub_prefs_v1";
const prefs = { details: "missing_recent", showBrowser: false, day: "周二", ...JSON.parse(localStorage.getItem(PREF_KEY) || "{}") };
const savePrefs = () => localStorage.setItem(PREF_KEY, JSON.stringify(prefs));

function modeText(mode) {
  if (!mode || mode === "all") return "已抓取的全部文章";
  if (mode.startsWith("nl:")) return mode.slice(3);
  if (mode === "custom") return "自定义日期";
  const m = mode.match(/^last(\d+)d$/);
  return m ? `最近 ${m[1]} 天` : mode;
}

/* ================= 术语悬停 ================= */

function buildTerms() {
  const keys = [];
  state.glossary.forEach((g, i) => [g.term, ...(g.keys || [])].forEach((k) => { keys.push(k); state.termIndex[k] ??= i; }));
  keys.sort((a, b) => b.length - a.length);
  const pat = keys.map((k) => esc(k).replace(/[.*+?^${}()|[\]\\/]/g, "\\$&")).join("|");
  state.termRe = pat ? new RegExp(pat, "g") : null;
}

const termLabel = (label, key = label) => (state.termIndex[key] == null ? esc(label)
  : `<span class="term" data-term="${state.termIndex[key]}">${esc(label)}</span>`);

function setupTooltip() {
  const tip = $("#tip");
  document.addEventListener("mouseover", (e) => {
    const t = e.target.closest?.(".term");
    if (!t) { tip.hidden = true; return; }
    const g = state.glossary[+t.dataset.term];
    if (!g) return;
    tip.innerHTML = `<div class="tip-title">${esc(g.term)}</div><p>${esc(g.plain)}</p><p class="tip-why">${esc(g.why)}</p>`;
    tip.hidden = false;
    const r = t.getBoundingClientRect();
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = `${Math.min(Math.max(8, r.left), window.innerWidth - w - 8)}px`;
    let top = r.bottom + 8;
    if (top + h > window.innerHeight - 8) top = r.top - h - 8;
    tip.style.top = `${Math.max(8, top)}px`;
  });
  window.addEventListener("scroll", () => { tip.hidden = true; }, { passive: true });
}

/* ================= 图表、表格 ================= */

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
const AXIS = {
  axisLine: { lineStyle: { color: "#d5dae1" } },
  axisLabel: { color: "#6b7482", fontSize: 11 },
  splitLine: { lineStyle: { color: "#eef1f4" } },
};
const C_BRAND = "#2f6fdb", C_WARM = "#e0862f", C_GREEN = "#18935a";
const PIE_COLORS = ["#2f6fdb", "#18935a", "#e0862f", "#9c6ade", "#4f8f88", "#b08a2e", "#a0527a"];

function sortableTable(el, cols, rows, opt = {}) {
  const st = opt.sortState || {};
  let sort = st.v && cols.some((c) => c.key === st.v.key && c.val) ? st.v : null;
  const cmp = (a, b) => (a == null ? 1 : b == null ? -1 : a < b ? -1 : a > b ? 1 : 0);
  const draw = () => {
    const list = rows.slice();
    if (sort) {
      const c = cols.find((x) => x.key === sort.key);
      list.sort((a, b) => {
        const va = c.val(a), vb = c.val(b);
        return va == null || vb == null ? cmp(va, vb) : cmp(va, vb) * sort.dir;
      });
    }
    const head = cols.map((c) => {
      const on = sort && sort.key === c.key;
      return `<th class="${c.num ? "num" : ""}${c.val ? " sortable" : ""}${on ? " sorted" : ""}" data-k="${c.key}">${c.label}${on ? (sort.dir > 0 ? " ↑" : " ↓") : ""}</th>`;
    }).join("");
    const body = list.map((r) => `<tr class="${opt.rowClass?.(r) || ""}${opt.onRow ? " link" : ""}" data-id="${esc(r.id ?? "")}">
      ${cols.map((c) => `<td class="${c.num ? "num" : ""}${c.cls ? ` ${c.cls}` : ""}">${c.fmt(r)}</td>`).join("")}</tr>`).join("")
      || `<tr><td colspan="${cols.length}" class="empty">${opt.empty || "暂无数据"}</td></tr>`;
    el.innerHTML = `<div class="table-wrap"><table class="tbl ${opt.tblClass || ""}"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
    $$("th.sortable", el).forEach((th) => th.onclick = () => {
      const k = th.dataset.k;
      sort = sort && sort.key === k ? (sort.dir < 0 ? { key: k, dir: 1 } : null) : { key: k, dir: -1 };
      st.v = sort;
      draw();
    });
    if (opt.onRow) $$("tbody tr[data-id]", el).forEach((tr) => tr.onclick = (e) => {
      if (!e.target.closest(".term, a, button") && tr.dataset.id) opt.onRow(tr.dataset.id);
    });
  };
  draw();
}

function barList(items, { color = C_BRAND, max, suffix = "%", digits = 1 } = {}) {
  if (!items.length) return `<div class="empty">暂无数据</div>`;
  const top = max ?? (Math.max(0, ...items.map((x) => x[1])) || 1);
  return `<div class="bar-list">${items.map(([k, v]) => `<div class="row"><span class="lab" title="${esc(k)}">${esc(k)}</span>
    <span class="track"><i style="width:${Math.min(100, (v / top) * 100).toFixed(1)}%;background:${color}"></i></span>
    <span class="val">${ok(v) ? Number(v).toFixed(digits).replace(/\.0+$/, "") : "—"}${suffix}</span></div>`).join("")}</div>`;
}

const tagBadges = (tags) => (tags || []).map((t) => `<span class="badge ${t === "具名主体" ? "blue" : t === "冲突" ? "red" : t === "复盘" ? "gray" : "purple"}">${esc(t)}</span>`).join(" ");

function nav(hash) { location.hash = hash; }

/* ================= 状态 ================= */

async function refreshStatus() {
  state.status = await api("/api/status");
  renderStatus();
  return state.status;
}

function renderStatus() {
  const s = state.status;
  if (!s) return;
  const pill = $("#statusPill"), bar = $("#progress"), btn = $("#btnScrape");
  const j = s.job;
  if (j.running) {
    pill.innerHTML = j.waiting_qr ? `<span class="spinner"></span>等待扫码` : `<span class="spinner"></span>${esc(phaseText(j.phase))} ${j.total ? `${j.done}/${j.total}` : ""}`;
    pill.className = "status-pill busy";
    pill.title = j.message || "";
    bar.hidden = false;
    $("i", bar).style.width = `${j.total ? (j.done / j.total) * 100 : 8}%`;
    btn.disabled = true;
  } else {
    const sc = s.scrape;
    const stale = sc.days_since != null && sc.days_since >= 7;
    pill.innerHTML = !s.has_raw ? "还没有抓取过"
      : `<span class="dot ${stale ? "amber" : "ok"}"></span>抓取于 ${esc(sc.last_scrape?.slice(5) || "—")}${sc.days_since ? ` · ${sc.days_since} 天前` : ""}`;
    pill.className = `status-pill${stale || !s.has_raw ? " warn" : ""}`;
    pill.title = `上次分析：${s.last_analysis || "从未"}\n分析范围：${modeText(s.window?.mode)}\n点击打开数据抓取`;
    bar.hidden = true;
    btn.disabled = false;
  }
  const running = j.running;
  if (running) startPolling();
  if (state.scrapeWasRunning && !running) {
    if (j.error) toast(`抓取没有完成：${j.error}`, "warn", 8000);
    else toast("抓取完成，已重新分析并生成报告", "ok", 6000);
    if (!location.hash.startsWith("#/scrape")) render();
  }
  state.scrapeWasRunning = running;
}

const PHASES = { start: "启动浏览器", login: "登录", publish: "发表记录", overview: "总览", details: "详情页", analyze: "分析", done: "完成", failed: "失败", cancelled: "已取消" };
const phaseText = (p) => PHASES[p] || p || "";

function startPolling() {
  if (state.polling) return;
  state.polling = setInterval(async () => {
    let s;
    try { s = await refreshStatus(); } catch { return; }
    if (!s.job.running) { clearInterval(state.polling); state.polling = null; }
  }, 2000);
}

function needDataCard(e) {
  const s = state.status || {};
  return `<section class="init"><h1>还没有分析数据</h1>
    <p class="muted">${esc(e?.message || "")}</p>
    <p>${s.has_raw ? "data/raw 里已经有抓取过的原始快照，可以直接分析；也可以先抓一次最新数据。" : "先扫码登录公众号后台抓一次数据，大约 1~3 分钟（首次会把每篇文章的详情页都抓一遍，会久一些）。"}</p>
    <div class="actions" style="justify-content:center;margin-top:16px">
      ${s.has_raw ? `<button class="btn primary" id="btnAnalyzeNow">用已有快照分析</button>` : ""}
      <a class="btn ${s.has_raw ? "" : "primary"}" href="#/scrape">去抓取数据</a></div></section>`;
}

function bindNeedData() {
  const b = $("#btnAnalyzeNow");
  if (b) b.onclick = async () => {
    b.disabled = true;
    try {
      await api("/api/analyze", { json: { mode: "all" } });
      toast("分析完成");
      await refreshStatus();
      render();
    } catch (e) { toast(e.message, "warn"); b.disabled = false; }
  };
}

/* ================= 总览 ================= */

async function renderOverview(token) {
  const o = await api("/api/overview");
  if (token !== state.token) return;
  const k = o.kpi, w = o.window;
  const kpi = (val, label, sub = "") => `<div class="kpi"><small>${label}</small><b>${val}</b>${sub ? `<span>${sub}</span>` : ""}</div>`;
  app.innerHTML = `
  <section class="card">
    <div class="card-head"><div><div class="eyebrow">分析范围 ${esc(w.since)} ~ ${esc(w.until)} · ${esc(modeText(w.mode))}</div><h2>总览</h2></div>
      <div class="actions"><a class="btn" href="#/reports">换分析范围 / 看完整报告</a><a class="btn" href="#/recommend">选题推荐</a><a class="btn primary" href="#/predict">标题评分</a></div></div>
    <div class="kpis">
      ${kpi(n0(k.articles), "发文篇数", `${k.with_detail} 篇有${termLabel("详情快照")}`)}
      ${kpi(n0(k.total_reads), `累计${termLabel("阅读")}`, `头部 3 篇占 ${k.top3_share}%`)}
      ${kpi(k.week_avg, "周均发文", "近一年口径")}
      ${kpi(n0(k.fans), "累计关注", k.growth_month_pct != null ? `月增 ${k.growth_month_pct}%` : "")}
      ${kpi(k.months_to_100 ?? "—", "距 100 粉（月）", "解锁账号级画像")}
      ${kpi(`${k.lift || "—"}×`, termLabel("具名主体") + "杠杆", "平均阅读倍数")}
      ${kpi(`${k.tue_share}%`, "周二阅读占比", "")}
      ${kpi(k.avg_engagement != null ? `${k.avg_engagement}%` : "—", `平均${termLabel("互动率")}`, `${k.total_follows} 个关注来自有详情的文章`)}
    </div>
  </section>
  <section class="card"><h2 style="margin-bottom:10px">要点</h2><ul class="insights">${o.insights.map((x) => `<li>${x}</li>`).join("") || "<li class='muted'>数据太少，暂无结论</li>"}</ul></section>
  <section class="card"><div class="card-head"><h2>每篇阅读</h2><span class="muted small">点柱子打开文章详情 · 橙色是周二发的</span></div><div class="chart short" id="cTimeline"></div></section>
  <div class="grid2">
    <section class="card"><h2>发布星期</h2><div class="chart short" id="cWeekday"></div></section>
    <section class="card"><h2>标题类型 vs 平均阅读</h2><p class="muted small">${termLabel("具名主体")}、${termLabel("冲突词", "冲突词")}、问号、复盘四种标记的组合</p>
      ${barList(o.taxonomy.map((t) => [`${t[0]}（${t[1]}篇）`, t[2]]), { color: "#7a4fc4", suffix: "", digits: 1 })}</section>
  </div>
  <div class="grid2">
    <section class="card"><h2>流量来源</h2><p class="muted small">账号级，阅读总人数 ${n0(o.total_readers)} · 内容分析快照 ${esc(o.snapshots.content_analysis || "—")}</p><div class="chart short" id="cTraffic"></div></section>
    <section class="card"><h2>${termLabel("互动率")}排行</h2><p class="muted small">新增关注与阅读 r=${o.correlations.read}，与完读×分享 r=${o.correlations.completion_x_share}（${o.correlations.n} 篇）</p><div id="tEng"></div></section>
  </div>
  <section class="card"><h2>读者画像</h2><p class="muted small">推荐占比 ≥ 50%、阅读 ≥ 50 的单篇按阅读加权聚合，样本 ${o.profile.sample} 篇（粉丝不到 100 时后台不给账号级画像）</p>
    <div class="grid3" style="margin-top:10px">
      <div><h3 style="margin-bottom:8px">年龄</h3>${barList(o.profile.age, { color: "#7a4fc4" })}</div>
      <div><h3 style="margin-bottom:8px">性别</h3>${barList(Object.entries(o.profile.gender), { color: "#d53f8a" })}</div>
      <div><h3 style="margin-bottom:8px">地域 Top</h3>${barList(o.profile.region, { color: "#319795" })}</div>
    </div></section>`;

  const tl = o.timeline;
  const c1 = makeChart($("#cTimeline"));
  c1.setOption({
    grid: { left: 50, right: 16, top: 16, bottom: 50 },
    tooltip: { trigger: "axis", formatter: (p) => `${esc(tl[p[0].dataIndex].date)}<br><b>${esc(tl[p[0].dataIndex].title)}</b><br>阅读 ${n0(tl[p[0].dataIndex].reads)}` },
    xAxis: { type: "category", data: tl.map((a) => a.date), ...AXIS },
    yAxis: { type: "value", ...AXIS },
    dataZoom: tl.length > 40 ? [{ type: "inside", start: 40, end: 100 }, { type: "slider", height: 16, bottom: 6 }] : [],
    series: [{ type: "bar", data: tl.map((a) => ({ value: a.reads ?? 0, itemStyle: { color: new Date(a.date).getDay() === 2 ? C_WARM : C_BRAND } })) }],
  });
  c1.on("click", (p) => { const a = tl[p.dataIndex]; if (a?.id) nav(`#/a/${encodeURIComponent(a.id)}`); });

  const wd = o.weekday;
  makeChart($("#cWeekday")).setOption({
    grid: { left: 44, right: 44, top: 30, bottom: 26 },
    legend: { top: 0, textStyle: { fontSize: 12 } },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: wd.map((x) => x.day), ...AXIS },
    yAxis: [{ type: "value", name: "篇数", ...AXIS }, { type: "value", name: "均阅读", ...AXIS, splitLine: { show: false } }],
    series: [
      { name: "篇数", type: "bar", data: wd.map((x) => x.n), itemStyle: { color: "#a9c4f2" } },
      { name: "单篇平均阅读", type: "line", yAxisIndex: 1, data: wd.map((x) => x.avg), itemStyle: { color: C_WARM }, smooth: true },
    ],
  });

  makeChart($("#cTraffic")).setOption({
    tooltip: { trigger: "item", formatter: "{b}：{d}%" },
    color: PIE_COLORS,
    series: [{ type: "pie", radius: ["45%", "72%"], label: { formatter: "{b} {d}%" }, data: o.traffic.map((x) => ({ name: x.name, value: x.value })) }],
  });

  sortableTable($("#tEng"), [
    { key: "title", label: "文章", fmt: (r) => `<span title="${esc(r.title)}">${esc(r.title.slice(0, 18))}</span>` },
    { key: "reads", label: "阅读", num: true, val: (r) => r.reads, fmt: (r) => n0(r.reads) },
    { key: "rate", label: "互动率", num: true, val: (r) => r.rate, fmt: (r) => `<b class="${r.rate >= 5 ? "warn-text" : ""}">${r.rate}%</b>` },
    { key: "completion", label: "完读率", num: true, val: (r) => r.completion, fmt: (r) => pct(r.completion, 0) },
    { key: "follows", label: "关注", num: true, val: (r) => r.follows, fmt: (r) => n0(r.follows) },
  ], o.engagement.slice(0, 10), { tblClass: "compact", onRow: (id) => nav(`#/a/${encodeURIComponent(id)}`), sortState: state.sorts.eng ??= {} });
}

/* ================= 文章 ================= */

async function renderArticles(token) {
  const rows = await api("/api/articles");
  if (token !== state.token) return;
  const withDetail = rows.filter((r) => r.has_detail).length;
  app.innerHTML = `<section class="card">
    <div class="card-head"><div><h2>文章</h2><span class="muted small">${rows.length} 篇，${withDetail} 篇有${termLabel("详情快照")}。点一行看详情。</span></div>
      <div class="actions"><input type="text" id="q" placeholder="搜标题" style="width:200px">
      <label class="fitem"><input type="checkbox" id="onlyDetail"> 只看有详情的</label></div></div>
    <div id="tbl"></div></section>`;
  const cols = [
    { key: "publish", label: "发布", val: (r) => r.publish, fmt: (r) => `${esc(r.publish)} <span class="muted small">${esc(r.weekday || "")}</span>` },
    { key: "title", label: "标题", cls: "wrap", fmt: (r) => `${esc(r.title)} ${tagBadges(r.tags)}${r.has_detail ? "" : ` <span class="badge gray" title="${r.has_id ? "还没抓这篇的详情页" : "转载或旧文，没有 appmsg_id，抓不了详情"}">无详情</span>`}` },
    { key: "reads", label: termLabel("阅读"), num: true, val: (r) => r.reads, fmt: (r) => n0(r.reads) },
    { key: "completion", label: termLabel("完读率"), num: true, val: (r) => r.completion, fmt: (r) => pct(r.completion, 0) },
    { key: "shares", label: "分享", num: true, val: (r) => r.shares, fmt: (r) => n0(r.shares) },
    { key: "engagement_rate", label: termLabel("互动率"), num: true, val: (r) => r.engagement_rate, fmt: (r) => (r.has_detail ? `<span class="${r.engagement_rate >= 5 ? "warn-text" : ""}">${r.engagement_rate}%</span>` : DASH) },
    { key: "new_follows", label: "新增关注", num: true, val: (r) => r.new_follows, fmt: (r) => (r.new_follows ? `<b>${r.new_follows}</b>` : n0(r.new_follows)) },
    { key: "follow_per_k", label: termLabel("关注/千读"), num: true, val: (r) => r.follow_per_k, fmt: (r) => (r.has_detail ? r.follow_per_k : DASH) },
  ];
  const draw = () => {
    const q = $("#q").value.trim().toLowerCase(), only = $("#onlyDetail").checked;
    const list = rows.filter((r) => (!q || r.title.toLowerCase().includes(q)) && (!only || r.has_detail));
    sortableTable($("#tbl"), cols, list, { onRow: (id) => nav(`#/a/${encodeURIComponent(id)}`), sortState: state.sorts.articles ??= {}, rowClass: (r) => (r.has_detail ? "" : "dim") });
  };
  $("#q").oninput = draw;
  $("#onlyDetail").onchange = draw;
  draw();
}

async function renderArticle(token, id) {
  const d = await api(`/api/articles/${encodeURIComponent(id)}`);
  if (token !== state.token) return;
  const kv = (label, val, sub = "") => `<div class="kv"><small>${label}</small><b>${val}</b>${sub ? `<span>${sub}</span>` : ""}</div>`;
  const has = d.completion != null;
  app.innerHTML = `
  <div class="crumb"><a href="#/articles">文章</a> / ${esc(d.title.slice(0, 30))}</div>
  <section class="card"><div class="head-row"><div><h1 style="font-size:20px">${esc(d.title)}</h1>
    <div class="sub">${esc(d.publish)} ${tagBadges(d.tags)}</div></div>
    <div class="actions"><button class="btn" id="btnScore">给这个标题打分</button></div></div>
    ${has ? `<div class="kv-row" style="margin-top:14px">
      ${kv(termLabel("阅读"), n0(d.reads), d.reads_d2 != null && d.reads_d2 !== d.reads ? `详情页快照 ${d.reads_d2}` : "")}
      ${kv(termLabel("完读率"), pct(d.completion, 0))}
      ${kv("新增关注", n0(d.new_follows), `${termLabel("关注/千读")} ${d.follow_per_k}`)}
      ${kv("分享", n0(d.shares), `朋友圈 ${d.moments ?? 0} · 转发 ${d.forwards ?? 0}`)}
      ${kv("留言 / 收藏", `${d.comments ?? 0} / ${d.collections ?? 0}`)}
      ${kv(termLabel("互动率"), `${d.engagement_rate}%`, d.engagement_rate >= 5 ? "高互动" : "")}
      ${kv(termLabel("粉丝活跃度"), `${d.fan_active}%`, `送达 ${d.reach ?? "—"} · 消息阅读 ${d.msg_reads ?? "—"}`)}
      ${kv(termLabel("分享传播力"), `${d.share_spread}%`)}
      ${d.listen_full != null ? kv("听全文", n0(d.listen_full)) : ""}
    </div>` : `<div class="notice" style="margin-top:12px">这篇只有发表记录里的阅读数 <b>${n0(d.reads)}</b>，没有${termLabel("详情快照")}。
      ${String(d.id).startsWith("noid|") ? "它是转载或旧文，后台没有 appmsg_id，抓不了详情。" : `到 <a href="#/scrape">数据抓取</a> 选「只补抓缺详情的文章」即可补上。`}</div>`}
  </section>
  ${has ? `<div class="grid2">
    <section class="card"><h2>阅读渠道</h2><div class="chart short" id="cCh"></div></section>
    <section class="card"><h2>读者</h2><div class="grid2" style="margin-top:10px"><div><h3 style="margin-bottom:6px">年龄</h3>${barList(Object.entries(d.age || {}), { color: "#7a4fc4" })}</div>
      <div><h3 style="margin-bottom:6px">性别</h3>${barList(Object.entries(d.gender || {}), { color: "#d53f8a" })}
      <h3 style="margin:12px 0 6px">地域</h3>${barList(d.region ? d.region.map(([k, v]) => [k, parseFloat(v)]) : [], { color: "#319795" })}</div></div>
      <p class="muted small" style="margin-top:8px">单篇画像样本小（几十个阅读时一个人就是几个百分点），看趋势别看小数点。</p></section></div>` : ""}`;
  $("#btnScore").onclick = () => { state.prefill = { title: d.title }; nav("#/predict"); };
  if (has && d.channels) {
    makeChart($("#cCh")).setOption({
      tooltip: { trigger: "item", formatter: "{b}：{c}%" }, color: PIE_COLORS,
      series: [{ type: "pie", radius: ["45%", "72%"], label: { formatter: "{b} {c}%" },
        data: Object.entries(d.channels).filter(([, v]) => v > 0).map(([k, v]) => ({ name: k, value: +v.toFixed(1) })) }],
    });
  }
}

/* ================= 标题评分 ================= */

async function renderPredict(token) {
  const base = await api("/api/baseline");
  if (token !== state.token) return;
  const topics = [...new Set([...base.platform_relevance.account_positioning.main, ...base.platform_relevance.high_follow_topics, ...base.title_formula.brand_keywords])];
  const pre = state.prefill || {};
  state.prefill = null;
  const tf = base.title_formula, wp = base.weekday_pattern, fm = base.follow_mechanism;
  app.innerHTML = `<div class="grid2" style="grid-template-columns:minmax(0,1.5fr) minmax(0,1fr)">
  <section class="card"><h2 style="margin-bottom:12px">标题评分</h2>
    <div class="form-grid">
      <label for="titles">标题草稿</label><textarea id="titles" rows="4" placeholder="每行一个，可以一次比较几个写法">${esc(pre.title || "")}</textarea>
      <label for="topics">主题关键词</label><div><input type="text" id="topics" placeholder="逗号分隔，如 微信,AI,工具" value="${esc(pre.topics || "")}">
        <div class="chips" style="margin-top:6px">${topics.map((t) => `<span class="chip" data-t="${esc(t)}">${esc(t)}</span>`).join("")}</div></div>
      <label>计划发文</label><div class="seg-btns" data-role="day">${state.meta.weekdays.map((d) => `<button data-v="${d}" class="${d === prefs.day ? "on" : ""}">${d}</button>`).join("")}</div>
      <label></label><label class="fitem"><input type="checkbox" id="sat" checked> 计入${termLabel("饱和度")}（近期写过同主题会扣分）</label>
      <label></label><div class="actions"><button class="btn primary" id="btnPredict">评分</button><span class="muted small">Ctrl+Enter 也可以</span></div>
    </div>
    <div id="result" style="margin-top:16px"></div>
  </section>
  <section class="card"><h2>评分依据</h2><p class="muted small">爆款预测基准 · ${esc(base.generated_at)} · ${esc(base.data_window.start)} ~ ${esc(base.data_window.end)}，${base.data_window.n_articles} 篇（${base.data_window.n_with_detail} 篇有详情）</p>
    <ul class="insights" style="margin-top:8px">
      <li>📈 阅读 = 标题公式（50）+ 时机（30）+ 话题热度（20）。${termLabel("具名主体")}平均阅读 ${tf.brand_avg_reads}，不具名 ${tf.nonb_avg_reads}（≈${tf.lift}×）。</li>
      <li>📅 周二 ${wp.tue_n} 篇贡献 ${wp.tue_share_pct}% 阅读（单篇均 ${wp.tue_avg_reads}）。</li>
      <li>💚 涨粉 = ${termLabel("平台相关度")}（40）+ 完读分享（30）+ 标题时机（30）。关注与阅读 r=${fm.r_read_vs_follow}，与完读×分享 r=${fm.r_completion_x_share_vs_follow}。</li>
      <li>🔥 互动潜力：方法论 20 / 冲突 15 / 复盘 12 / 普通 8。</li>
      <li>✅ 通过线：阅读 ≥ 70 且涨粉 ≥ 60。评分是参考不是门槛，有价值的题照样可以写。</li>
    </ul>
    <h3 style="margin:14px 0 6px">有效角度（历史互动率高的结构）</h3>
    ${barList(base.angle_patterns.effective_angles.map((a) => [`${a.angle}（${a.n}篇）`, a.avg_engagement_rate]), { color: C_WARM })}
  </section></div>`;
  let day = prefs.day;
  $$(".seg-btns[data-role=day] button").forEach((b) => b.onclick = () => {
    $$(".seg-btns[data-role=day] button").forEach((x) => x.classList.toggle("on", x === b));
    day = prefs.day = b.dataset.v;
    savePrefs();
  });
  $$(".chip").forEach((c) => c.onclick = () => {
    const cur = $("#topics").value.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
    if (!cur.includes(c.dataset.t)) cur.push(c.dataset.t);
    $("#topics").value = cur.join(",");
  });
  const run = async () => {
    const titles = $("#titles").value.split("\n").map((s) => s.trim()).filter(Boolean);
    const tp = $("#topics").value.trim();
    if (!titles.length || !tp) { toast("标题和主题关键词都要填", "warn"); return; }
    $("#result").innerHTML = `<div class="loading">评分中…</div>`;
    try {
      const res = await Promise.all(titles.map((title) => api("/api/predict", { json: { title, topics: tp, day, saturation: $("#sat").checked } })));
      res.sort((a, b) => (b.prediction_pass - a.prediction_pass) || (b.total_score - a.total_score));
      $("#result").innerHTML = (res.length > 1 ? `<p class="muted small">通过预测的在前，再按综合分排序</p>` : "") + res.map(scoreCard).join("");
      $$("[data-copy]", $("#result")).forEach((b) => b.onclick = () => copyText(b.dataset.copy).then(() => toast("已复制评分卡")));
    } catch (e) { $("#result").innerHTML = `<div class="notice">${esc(e.message)}</div>`; }
  };
  $("#btnPredict").onclick = run;
  $("#titles").onkeydown = (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) run(); };
  if (pre.title && pre.topics) run();
}

function meter(label, val, max, cls, parts) {
  return `<div class="meter ${cls}"><small>${label}</small><b>${val}</b><span class="muted small">/${max}</span>
    <div class="track"><i style="width:${Math.min(100, (val / max) * 100)}%"></i></div>${parts ? `<div class="parts">${parts}</div>` : ""}</div>`;
}

function scoreCard(r) {
  return `<div class="score-card">
    <h3>《${esc(r.title)}》 ${r.prediction_pass ? `<span class="badge ok">通过</span>` : `<span class="badge amber">未通过</span>`} <span class="badge ${r.positioning_status.startsWith("✅") ? "blue" : "red"}">${esc(r.positioning_status)}</span></h3>
    <div class="muted small">标题标记：${r.title_tags.length ? tagBadges(r.title_tags) : "普通"} · ${esc(r.topics.join("、"))} · ${esc(r.day)} · 综合 ${r.total_score}</div>
    <div class="meters">
      ${meter("📈 阅读爆款潜力", r.read_score, 100, "read", `标题 ${r.title_score}/50 · 时机 ${r.day_score}/30 · 话题 ${r.topic_heat}/20`)}
      ${meter("💚 涨粉潜力", r.follow_score, 100, "follow", `相关度 ${r.relevance}/40 · 完读分享 ${r.engage}/30`)}
      ${meter("🔥 互动潜力", r.interaction, 20, "inter")}
    </div>
    <div class="verdict">${esc(r.verdict)}</div>
    <p class="small" style="color:var(--sub)">${esc(r.reason)}</p>
    ${r.saturation_notes?.length ? `<div class="notice small">⚠️ ${r.saturation_notes.map(esc).join("<br>")}</div>` : ""}
    <p class="small" style="color:var(--sub);margin-top:6px">📍 ${esc(r.positioning_note)}</p>
    <b class="small">优化建议</b><ul class="tight small">${r.suggestions.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>
    ${r.similar_hits?.length || r.similar_follow?.length ? `<b class="small">相似的历史文章</b><ul class="tight small">
      ${(r.similar_hits || []).map((s) => `<li>《${esc(s.title)}》${s.reads} 读 / ${s.new_follows} 关注</li>`).join("")}
      ${(r.similar_follow || []).map((s) => `<li>《${esc(s.title)}》${s.reads} 读 / ${s.follows} 关注 / 完读 ${s.completion}%</li>`).join("")}</ul>` : ""}
    <div class="actions" style="margin-top:8px"><button class="btn ghost" data-copy="${esc(r.card)}">复制文字版评分卡</button></div>
  </div>`;
}

/* ================= 选题推荐 ================= */

const ASK_EXAMPLES = ["给我推荐3个偏实用的选题，下周二发", "推荐几个非热点但有长期价值的AI选题", "偏微信生态和搜一搜的选题", "理财和商业决策方向的选题"];

async function renderRecommend(token) {
  const [hist, cur] = await Promise.all([api("/api/recommendations"), api("/api/recommend")]);
  if (token !== state.token) return;
  app.innerHTML = `<div class="grid2" style="grid-template-columns:minmax(0,1.6fr) minmax(0,1fr)">
  <section class="card"><h2 style="margin-bottom:12px">选题推荐</h2>
    <div class="form-grid">
      <label for="ask">想要什么样的题</label><div><textarea id="ask" rows="2" placeholder="一句话说清楚，例如：给我推荐3个偏实用的选题，下周二发"></textarea>
        <div class="chips" style="margin-top:6px">${ASK_EXAMPLES.map((t) => `<span class="chip" data-t="${esc(t)}">${esc(t)}</span>`).join("")}</div></div>
      <label for="queries">热点检索词</label><input type="text" id="queries" placeholder="可选，逗号分隔；不填用默认词 + 历史高频主题">
      <label>数量 / 发文日</label><div class="actions"><input type="number" id="count" min="1" max="12" placeholder="6" style="width:80px">
        <select id="day"><option value="">按需求里说的（默认周二）</option>${state.meta.weekdays.map((d) => `<option>${d}</option>`).join("")}</select>
        <label class="fitem"><input type="checkbox" id="offline"> 不抓热点，只出价值型选题</label></div>
      <label></label><div class="actions"><button class="btn primary" id="btnRec">开始推荐</button><span id="recMsg" class="muted small"></span></div>
    </div>
    <p class="muted small" style="margin-top:10px">抓热点要访问 Bing / Google News 和 36氪、虎嗅、极客公园的 RSS，大约 10~60 秒；网络不通时会自动只出价值型选题。结果同时存到 data/topic_recommendations/。</p>
  </section>
  <section class="card"><h2>历史推荐</h2><div id="hist" style="margin-top:8px"></div></section></div>
  <section class="card" id="recOut" hidden></section>`;
  $$(".chip").forEach((c) => c.onclick = () => { $("#ask").value = c.dataset.t; });
  drawHist(hist);
  $("#btnRec").onclick = async () => {
    try {
      await api("/api/recommend", { json: { ask: $("#ask").value.trim(), queries: $("#queries").value.trim(), count: $("#count").value, day: $("#day").value, offline: $("#offline").checked } });
      pollRec(token);
    } catch (e) { toast(e.message, "warn"); }
  };
  if (cur.running) pollRec(token);
  else if (cur.result) showRec(cur.result);
}

function pollRec(token) {
  $("#btnRec").disabled = true;
  clearInterval(state.recTimer);
  const tick = async () => {
    if (token !== state.token) { clearInterval(state.recTimer); return; }
    const s = await api("/api/recommend").catch(() => null);
    if (!s) return;
    $("#recMsg").innerHTML = s.running ? `<span class="spinner" style="display:inline-block"></span> ${esc(s.message)}` : "";
    if (s.running) return;
    clearInterval(state.recTimer);
    $("#btnRec").disabled = false;
    if (s.error) toast(`推荐失败：${s.error}`, "warn", 8000);
    else if (s.result) { showRec(s.result); toast("推荐完成"); api("/api/recommendations").then(drawHist).catch(() => null); }
  };
  state.recTimer = setInterval(tick, 1500);
  tick();
}

function drawHist(hist) {
  const box = $("#hist");
  if (!box) return;
  box.innerHTML = hist.length ? `<table class="tbl compact"><tbody>${hist.slice(0, 15).map((h) => `<tr class="link" data-n="${esc(h.name)}">
    <td>${esc(h.time)}</td><td class="wrap">${esc(h.ask || "（默认）")}<div class="muted small">${h.passed} 个通过 · ${h.exceptions} 个保留</div></td></tr>`).join("")}</tbody></table>` : `<div class="empty">还没有推荐记录</div>`;
  $$("tr[data-n]", box).forEach((tr) => tr.onclick = async () => showRec(await api(`/api/recommendations/${encodeURIComponent(tr.dataset.n)}`)));
}

function showRec(p) {
  const out = $("#recOut");
  if (!out) return;
  out.hidden = false;
  const angles = (p.effective_angles || []).map((a) => `${a.angle}（${a.avg_engagement_rate}%）`).join("、");
  const card = (c, i) => {
    const pr = c.prediction;
    return `<div class="cand"><h3>${i + 1}. ${esc(pr.title)}</h3>
      <div class="meta"><span class="badge ${c.source_type === "热点型" ? "red" : "blue"}">${esc(c.source_type)}</span><span class="badge purple">${esc(c.angle_type)}</span>
        ${pr.prediction_pass ? `<span class="badge ok">通过爆款预测</span>` : `<span class="badge amber">未通过预测，建议保留观察</span>`}
        <span class="badge gray">阅读 ${pr.read_score} · 涨粉 ${pr.follow_score} · 互动 ${pr.interaction}</span><span class="badge gray">${esc(pr.positioning_status)}</span></div>
      <p class="small" style="color:var(--sub)">${esc(c.why)}</p>
      ${c.source_url ? `<p class="small">热点来源：<a href="${esc(c.source_url)}" target="_blank" rel="noopener">${esc(c.source_title)}</a> <span class="muted">${esc(c.source)} · ${esc(c.published_at)}</span></p>` : ""}
      ${c.request_notes?.length ? `<p class="small">贴合你的要求：${esc(c.request_notes.join("；"))}</p>` : ""}
      ${pr.saturation_notes?.length ? `<p class="small warn-text">⚠️ ${esc(pr.saturation_notes.join("；"))}</p>` : ""}
      <details><summary>备选标题、写作要点</summary>
        <b class="small">备选标题</b><ul class="tight small">${(c.title_options || []).slice(1, 7).map(([t, a]) => `<li>[${esc(a)}] ${esc(t)}</li>`).join("")}</ul>
        <b class="small">写作要点</b><ul class="tight small">${(c.writing_points || []).map((t) => `<li>${esc(t)}</li>`).join("")}</ul>
        <b class="small">评分建议</b><ul class="tight small">${(pr.suggestions || []).map((t) => `<li>${esc(t)}</li>`).join("")}</ul>
      </details>
      <div class="actions" style="margin-top:8px"><button class="btn ghost" data-copy="${esc(pr.title)}">复制标题</button>
        <button class="btn ghost" data-score="${esc(pr.title)}" data-topics="${esc(pr.topics.join(","))}">去评分页调整</button></div></div>`;
  };
  out.innerHTML = `<div class="card-head"><div><h2>推荐结果</h2><span class="muted small">${esc(p.generated_at)} · ${esc(p.request_context?.raw || "默认需求")} · 发文日 ${esc(p.day)}</span></div></div>
    <p class="muted small">热点 ${p.raw_news.length} 条，过滤后 ${p.filtered_news.length} 条${p.offline ? "（本次没抓热点）" : ""}；历史推荐去重剔除 ${p.history_dropped.length} 个。套用的有效角度：${esc(angles || "—")}</p>
    <h3 style="margin:14px 0 8px">通过爆款预测（优先写）</h3>${p.passed.map(card).join("") || `<div class="empty">这次没有通过预测的题</div>`}
    <h3 style="margin:18px 0 8px">未通过但值得保留</h3>${p.exceptions.map((c, i) => card(c, i)).join("") || `<div class="empty">暂无</div>`}`;
  $$("[data-copy]", out).forEach((b) => b.onclick = () => copyText(b.dataset.copy).then(() => toast("已复制")));
  $$("[data-score]", out).forEach((b) => b.onclick = () => { state.prefill = { title: b.dataset.score, topics: b.dataset.topics }; nav("#/predict"); });
  out.scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ================= 报告与分析范围 ================= */

async function renderReports(token) {
  const reports = await api("/api/reports");
  if (token !== state.token) return;
  const w = state.status?.window || {};
  const ex = state.meta.range_examples;
  app.innerHTML = `
  <section class="card"><div class="card-head"><div><h2>${termLabel("分析窗口")}</h2><span class="muted small">当前：${esc(w.since || "—")} ~ ${esc(w.until || "—")} · ${esc(modeText(w.mode))} · 上次分析 ${esc(state.status?.last_analysis || "—")}</span></div></div>
    <div class="form-grid">
      <label>范围</label><div class="seg-btns" data-role="mode">${[["all", "全部已抓取"], ["nl", "口语描述"], ["custom", "指定日期"], ["window", "最近 N 天"]].map(([v, t]) => `<button data-v="${v}">${t}</button>`).join("")}</div>
      <label class="m m-nl">时间描述</label><div class="m m-nl"><input type="text" id="nl" placeholder="例如：近一个月 / 2026年至今 / 2026年5月">
        <div class="chips" style="margin-top:6px">${ex.map((t) => `<span class="chip" data-t="${esc(t)}">${esc(t)}</span>`).join("")}</div></div>
      <label class="m m-custom">日期</label><div class="m m-custom actions"><input type="date" id="since" style="width:170px"> 到 <input type="date" id="until" style="width:170px"></div>
      <label class="m m-window">最近</label><div class="m m-window actions"><input type="number" id="win" min="1" value="90" style="width:100px"> 天</div>
      <label></label><div class="actions"><button class="btn primary" id="btnAnalyze">重新分析并生成报告</button><span class="muted small">只读本地快照，不联网，一两秒完成</span></div>
    </div>
    <div id="anaOut"></div>
    <p class="muted small" style="margin-top:10px">${termLabel("详情快照")}只覆盖抓过详情页的文章：选更早的时段时，完读、分享、关注、画像只统计有快照的那部分。</p>
  </section>
  <section class="card"><div class="card-head"><h2>报告</h2><span class="muted small">reports/ 下的 HTML，日期最新的就是当前报告；旧的可以删掉</span></div><div id="rlist"></div>
    ${reports.length ? `<iframe class="report-frame" id="rframe" src="/reports/${encodeURIComponent(reports[0].name)}" style="margin-top:12px"></iframe>` : ""}</section>`;
  let mode = w.mode?.startsWith("nl:") ? "nl" : w.mode === "custom" ? "custom" : /^last\d+d$/.test(w.mode || "") ? "window" : "all";
  if (mode === "nl") $("#nl").value = w.mode.slice(3);
  if (mode === "custom") { $("#since").value = w.since; $("#until").value = w.until; }
  if (mode === "window") $("#win").value = w.mode.match(/\d+/)[0];
  const setMode = (m) => {
    mode = m;
    $$(".seg-btns[data-role=mode] button").forEach((b) => b.classList.toggle("on", b.dataset.v === m));
    $$(".m").forEach((el) => { el.hidden = !el.classList.contains(`m-${m}`); });
  };
  setMode(mode);
  $$(".seg-btns[data-role=mode] button").forEach((b) => b.onclick = () => setMode(b.dataset.v));
  $$(".chip").forEach((c) => c.onclick = () => { $("#nl").value = c.dataset.t; });
  $("#btnAnalyze").onclick = async () => {
    const body = { mode, nl: $("#nl").value, since: $("#since").value, until: $("#until").value, window: $("#win").value };
    $("#btnAnalyze").disabled = true;
    try {
      const r = await api("/api/analyze", { json: body });
      const win = r.window;
      toast(`分析完成：${win.since} ~ ${win.until}，${win.articles} 篇`);
      if (win.warning) toast(win.warning, "warn", 8000);
      await refreshStatus();
      await render();
    } catch (e) { toast(e.message, "warn"); $("#btnAnalyze").disabled = false; }
  };
  sortableTable($("#rlist"), [
    { key: "name", label: "文件", fmt: (r) => `<a href="/reports/${encodeURIComponent(r.name)}" target="_blank">${esc(r.name)}</a>` },
    { key: "size", label: "大小", num: true, fmt: (r) => `${Math.round(r.size / 1024)} KB` },
    { key: "act", label: "", fmt: (r, i) => `<button class="btn ghost" data-show="${esc(r.name)}">在下方查看</button> <button class="btn ghost" data-del="${esc(r.name)}">删除</button>` },
  ], reports, { tblClass: "compact", empty: "还没有报告" });
  $$("[data-show]").forEach((b) => b.onclick = () => { $("#rframe").src = `/reports/${encodeURIComponent(b.dataset.show)}`; });
  $$("[data-del]").forEach((b) => b.onclick = async () => {
    if (!confirm(`删除 ${b.dataset.del}？`)) return;
    await api(`/api/reports/${encodeURIComponent(b.dataset.del)}`, { method: "DELETE" });
    render();
  });
}

/* ================= 数据抓取 ================= */

async function renderScrape(token) {
  const [job, st] = await Promise.all([api("/api/scrape"), refreshStatus()]);
  if (token !== state.token) return;
  const sc = st.scrape;
  const modes = state.meta.detail_modes;
  app.innerHTML = `<div class="grid2">
  <section class="card"><h2 style="margin-bottom:10px">抓取最新数据</h2>
    <p class="muted small">打开公众号后台（无界面浏览器），抓发表记录（自动翻页到底）、用户分析、内容分析和选定的单篇详情页，然后按当前${termLabel("分析窗口")}重新分析。登录状态会保存下来，有效期内不用重新扫码。</p>
    <div class="stat-row" style="margin:12px 0">
      <div class="stat"><small>上次抓取</small><b style="font-size:16px">${esc(sc.last_scrape || "从未")}</b>${sc.days_since != null ? `<span class="muted small">${sc.days_since} 天前</span>` : ""}</div>
      <div class="stat"><small>${termLabel("详情快照")}</small><b>${sc.detail_files}</b><span class="muted small">篇</span></div>
      <div class="stat"><small>登录状态</small><b style="font-size:16px">${sc.logged_in_before ? "保存过" : "需要扫码"}</b></div>
    </div>
    <h3 style="margin-bottom:6px">详情页抓哪些</h3>
    <div class="radio-list">${Object.entries(modes).map(([k, v]) => `<label><input type="radio" name="dm" value="${k}" ${k === prefs.details ? "checked" : ""}> ${esc(v)}</label>`).join("")}</div>
    <p class="muted small" style="margin-top:6px">后台详情页只统计发表后 30 天的数据，这段时间内的文章数字还在变，所以默认每次重抓；更早的抓过一次就够了。每篇约 5 秒。</p>
    <label class="fitem" style="margin-top:10px"><input type="checkbox" id="showBrowser" ${prefs.showBrowser ? "checked" : ""}> 显示浏览器窗口（扫码遇到问题、或想看抓取过程时勾上）</label>
    <div class="actions" style="margin-top:14px"><button class="btn primary" id="btnStart">开始抓取</button><button class="btn" id="btnCancel" hidden>取消</button></div>
    <p class="muted small" style="margin-top:12px">被覆盖的旧快照会移到 data/raw/history/，不会丢。命令行：<code>python -m backend scrape</code></p>
  </section>
  <section class="card"><h2 style="margin-bottom:10px">进度</h2><div id="jobView"></div></section></div>`;
  $$("input[name=dm]").forEach((r) => r.onchange = () => { prefs.details = r.value; savePrefs(); });
  $("#showBrowser").onchange = (e) => { prefs.showBrowser = e.target.checked; savePrefs(); };
  $("#btnStart").onclick = async () => {
    try {
      await api("/api/scrape", { json: { details: prefs.details, show_browser: prefs.showBrowser } });
      state.scrapeWasRunning = true;
      startPolling();
      watchJob(token);
    } catch (e) { toast(e.message, "warn"); }
  };
  $("#btnCancel").onclick = () => api("/api/scrape/cancel", { method: "POST" }).then(() => toast("正在取消…", "info"));
  drawJob(job);
  if (job.running) watchJob(token);
}

let lastQr = -1;
function drawJob(j) {
  const v = $("#jobView");
  if (!v) return;
  $("#btnStart").disabled = j.running;
  $("#btnCancel").hidden = !j.running;
  if (!j.started) { v.innerHTML = `<div class="empty">还没有开始</div>`; return; }
  const head = j.running
    ? `<p><span class="spinner" style="display:inline-block"></span> <b>${esc(phaseText(j.phase))}</b> ${j.total ? `${j.done}/${j.total}` : ""} · ${esc(j.message)}</p>`
    : j.error ? `<div class="notice" style="color:var(--risk)"><b>没有完成：</b>${esc(j.error)}</div>`
      : `<div class="notice"><b>完成</b> · ${j.result ? `${j.result.articles} 篇发表记录，详情页成功 ${j.result.details_ok} 篇${j.result.details_failed ? `、失败 ${j.result.details_failed} 篇` : ""}，用时 ${j.result.seconds} 秒` : ""}
        <div class="actions" style="margin-top:8px"><a class="btn" href="#/">看总览</a><a class="btn" href="#/reports">看报告</a></div></div>`;
  const qr = j.running && j.waiting_qr
    ? `<div class="qr-box"><p><b>请用微信扫码登录公众号后台</b></p><img id="qrImg" src="/api/scrape/qr?v=${j.qr_version}" alt="登录二维码"><p class="muted small">扫完在手机上确认；二维码过期会自动刷新</p></div>` : "";
  if (qr && $("#qrImg") && lastQr !== j.qr_version) {
    $("#qrImg").src = `/api/scrape/qr?v=${j.qr_version}`;
    lastQr = j.qr_version;
  }
  if (!(qr && $("#qrImg"))) {
    v.innerHTML = `${head}${qr}<div class="log" id="jobLog"></div>`;
    lastQr = j.qr_version;
  } else {
    v.firstElementChild.outerHTML = head;
  }
  const log = $("#jobLog");
  log.textContent = (j.log || []).join("\n");
  log.scrollTop = log.scrollHeight;
  if (j.warnings?.length && !j.running) log.textContent += `\n\n⚠ 提醒：\n${j.warnings.join("\n")}`;
}

function watchJob(token) {
  const tick = async () => {
    if (token !== state.token) return;
    const j = await api("/api/scrape").catch(() => null);
    if (!j) return;
    drawJob(j);
    if (j.running) setTimeout(tick, 1500);
    else refreshStatus();
  };
  tick();
}

/* ================= 术语 ================= */

function renderGlossary() {
  app.innerHTML = `<section class="card"><h2 style="margin-bottom:12px">术语</h2><div class="gl-grid">${state.glossary.map((g) => `<div class="gl"><h3>${esc(g.term)}</h3><p>${esc(g.plain)}</p><p class="muted">${esc(g.why)}</p></div>`).join("")}</div></section>`;
}

/* ================= 指引 ================= */

const GUIDE = [
  ["抓取数据", "右上角「抓取最新数据」进入抓取页，点开始后用微信扫页面上的二维码。登录状态会保存，有效期内下次不用扫。抓完自动重新分析。"],
  ["看总览和文章", "总览给出阅读、关注、互动和读者画像；「文章」页可以按任一列排序，点一行看单篇的完读、分享、渠道和画像。"],
  ["写之前：评分和推荐", "「标题评分」一次可以比较多个标题写法；「选题推荐」一句话说需求，结果分「通过预测」和「值得保留」两组。评分只是参考，选题由你决定。"],
  ["报告与分析范围", "「报告」页可以把分析范围换成「近一个月」「2026年至今」等，重新生成 HTML 报告。原始快照在 data/raw，删前请三思。"],
];
function openGuide(i = 0) {
  const m = $("#modal");
  const [t, body] = GUIDE[i];
  m.innerHTML = `<div class="modal-box"><div class="modal-step">${i + 1} / ${GUIDE.length}</div><h2>${esc(t)}</h2><div class="modal-body"><p>${esc(body)}</p></div>
    <div class="modal-foot"><button class="btn ghost" id="gClose">关闭</button><span>${i ? `<button class="btn" id="gPrev">上一步</button>` : ""}
    ${i < GUIDE.length - 1 ? `<button class="btn primary" id="gNext">下一步</button>` : `<button class="btn primary" id="gDone">开始使用</button>`}</span></div></div>`;
  m.hidden = false;
  const close = () => { m.hidden = true; localStorage.setItem("wxpub_guide_v1", "1"); };
  $("#gClose").onclick = close;
  if ($("#gDone")) $("#gDone").onclick = close;
  if ($("#gPrev")) $("#gPrev").onclick = () => openGuide(i - 1);
  if ($("#gNext")) $("#gNext").onclick = () => openGuide(i + 1);
}
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") $("#modal").hidden = true; });

/* ================= 路由 ================= */

const LINKS = [["", "总览"], ["articles", "文章"], ["predict", "标题评分"], ["recommend", "选题推荐"], ["reports", "报告"], ["scrape", "数据抓取"], ["glossary", "术语"]];

async function render() {
  const token = ++state.token;
  disposeCharts();
  const [page, a] = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  const cur = page === "a" ? "articles" : page || "";
  $("#nav").innerHTML = LINKS.map(([h, t]) => `<a href="#/${h}" class="${h === cur ? "on" : ""}">${t}</a>`).join("");
  app.innerHTML = `<div class="loading">加载中…</div>`;
  try {
    if (!page) await renderOverview(token);
    else if (page === "articles") await renderArticles(token);
    else if (page === "a" && a) await renderArticle(token, a);
    else if (page === "predict") await renderPredict(token);
    else if (page === "recommend") await renderRecommend(token);
    else if (page === "reports") await renderReports(token);
    else if (page === "scrape") await renderScrape(token);
    else if (page === "glossary") renderGlossary();
    else location.replace("#/");
    window.scrollTo(0, 0);
  } catch (e) {
    if (token !== state.token) return;
    if (e.status === 503) { app.innerHTML = needDataCard(e); bindNeedData(); return; }
    app.innerHTML = `<div class="card error"><h2>${e.status === 404 ? "找不到" : "加载失败"}</h2><p>${esc(e.message)}</p>
      <p class="muted">请确认服务正在运行（双击 scripts\\start_server.bat），然后刷新页面。<a href="#/">返回总览</a></p></div>`;
  }
}

async function boot() {
  setupTooltip();
  $("#btnScrape").onclick = () => nav("#/scrape");
  $("#btnGuide").onclick = () => openGuide(0);
  try {
    const [meta, glossary] = await Promise.all([api("/api/meta"), api("/api/glossary")]);
    state.meta = meta;
    state.glossary = glossary;
    $("#brandName").textContent = `${meta.account} · 公众号分析`;
    buildTerms();
    await refreshStatus();
  } catch (e) {
    app.innerHTML = `<div class="card error"><h2>无法连接服务</h2><p>${esc(e.message)}</p>
      <p class="muted">请双击 scripts\\start_server.bat 启动服务，并通过 http://127.0.0.1:8332 打开页面。</p></div>`;
    $("#statusPill").textContent = "未连接";
    return;
  }
  window.addEventListener("hashchange", render);
  await render();
  if (!localStorage.getItem("wxpub_guide_v1")) openGuide(0);
}

boot();

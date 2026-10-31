"use strict";

/* ================= 基础工具 ================= */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const app = $("#app");
const state = { meta: null, token: 0, draft: null, dirty: false, lastHash: null, sorts: {} };

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

function toast(text, kind = "ok", ms = 3500) {
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

/** 中文按字、英文按词，和后端 count_chars 一致 */
const countChars = (t) => ((t || "").match(/[\u4e00-\u9fff]/g) || []).length
  + ((t || "").match(/[A-Za-z0-9]+(?:[.'-][A-Za-z0-9]+)*/g) || []).length;

const COMPOSE_KEY = "writing_compose_v1";
const compose = { stage: "draft", topic: "", ideas: "", article: "", notes: "", feedback: {}, ...JSON.parse(localStorage.getItem(COMPOSE_KEY) || "{}") };
const saveCompose = () => localStorage.setItem(COMPOSE_KEY, JSON.stringify(compose));

const STATUS_BADGE = { "构思": "gray", "初稿": "blue", "修改中": "amber", "定稿": "ok", "已发表": "purple" };
const statusBadge = (s) => `<span class="badge ${STATUS_BADGE[s] || "gray"}">${esc(s || "—")}</span>`;

/* ================= Markdown ================= */

function inlineMd(s) {
  let h = esc(s);
  h = h.replace(/`([^`]+)`/g, "<code>$1</code>");
  h = h.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  h = h.replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<i>$2</i>");
  h = h.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, `<a href="$2" target="_blank" rel="noopener">$1</a>`);
  h = h.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, "$1");
  return h;
}

function renderMd(text) {
  const lines = (text || "").replace(/<!--[\s\S]*?-->/g, "").replace(/\r/g, "").split("\n");
  const out = [];
  let i = 0;
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
    if (/^\s*>/.test(l)) {
      const buf = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ""));
      out.push(`<blockquote>${buf.map(inlineMd).join("<br>")}</blockquote>`);
      continue;
    }
    if (/^\s*([-*]|\d+\.)\s+/.test(l)) {
      const ordered = /^\s*\d+\./.test(l);
      const buf = [];
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) buf.push(`<li>${inlineMd(lines[i++].replace(/^\s*([-*]|\d+\.)\s+/, ""))}</li>`);
      out.push(ordered ? `<ol>${buf.join("")}</ol>` : `<ul>${buf.join("")}</ul>`);
      continue;
    }
    if (!l.trim()) { i++; continue; }
    const buf = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|```|\s*>|\s*([-*]|\d+\.)\s+)/.test(lines[i])) buf.push(lines[i++]);
    out.push(`<p>${buf.map(inlineMd).join("<br>")}</p>`);
  }
  return out.join("\n");
}

/* ================= 版本对比 ================= */

function lcs(a, b) {
  const n = a.length, m = b.length;
  const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const ops = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { ops.push(["=", a[i]]); i++; j++; } else if (dp[i + 1][j] >= dp[i][j + 1]) ops.push(["-", a[i++]]); else ops.push(["+", b[j++]]);
  }
  while (i < n) ops.push(["-", a[i++]]);
  while (j < m) ops.push(["+", b[j++]]);
  return ops;
}

/** 按段落对比；一段删一段加且都不太长时，再做逐字对比 */
function diffHtml(oldText, newText) {
  const pa = oldText.split("\n").filter((x) => x.trim()), pb = newText.split("\n").filter((x) => x.trim());
  if (pa.length * pb.length > 4e6) return `<div class="notice">文章太长，无法对比</div>`;
  const ops = lcs(pa, pb);
  const out = [];
  for (let k = 0; k < ops.length; k++) {
    const [op, t] = ops[k];
    if (op === "-" && ops[k + 1]?.[0] === "+" && t.length < 700 && ops[k + 1][1].length < 700) {
      const chars = lcs([...t], [...ops[k + 1][1]]);
      const runs = [];
      chars.forEach(([o, c]) => { if (runs.length && runs.at(-1)[0] === o) runs.at(-1)[1] += c; else runs.push([o, c]); });
      out.push(`<p>${runs.map(([o, c]) => (o === "=" ? esc(c) : o === "-" ? `<del>${esc(c)}</del>` : `<ins>${esc(c)}</ins>`)).join("")}</p>`);
      k++;
    } else if (op === "=") out.push(`<p>${esc(t)}</p>`);
    else out.push(`<p class="${op === "+" ? "add" : "del"}">${esc(t)}</p>`);
  }
  return `<div class="diff">${out.join("")}</div>`;
}

/* ================= 写作台：拼 Prompt ================= */

function stageCards(active) {
  return `<div class="stages">${state.meta.stages.map((s) => `<button class="stage ${s.key === active ? "on" : ""}" data-stage="${s.key}">
    <span class="step">${esc(s.step)}</span><b>${esc(s.name)}</b><small>${esc(s.when)}</small></button>`).join("")}</div>`;
}

function feedbackFields(fb) {
  return `<div class="fb-grid">${state.meta.feedback_keys.map((k) => `<div><label>${esc(k)}</label><input type="text" data-fb="${esc(k)}" value="${esc(fb[k] || "")}"></div>`).join("")}</div>
    <div style="margin-top:8px"><label class="muted small">也可以直接用自然语言写</label><textarea data-fb="free" rows="3" placeholder="这版整体可以，但第二部分太泛，第三部分要更尖锐，结尾要收回来……">${esc(fb.free || "")}</textarea></div>`;
}

/** 渲染 Prompt 生成区。ctx 是可读写的状态对象（写作台用 compose，文章页用文章自己的） */
function promptPanel(root, ctx, { fixedArticle = null, onChange } = {}) {
  const draw = () => {
    const s = state.meta.stages.find((x) => x.key === ctx.stage) || state.meta.stages[1];
    const needs = s.needs;
    root.innerHTML = `${stageCards(s.key)}
      <div class="form-grid" style="margin-top:16px">
        ${needs.includes("topic") ? `<label>主题</label><input type="text" data-k="topic" value="${esc(ctx.topic)}" placeholder="一句话说清楚写什么">` : ""}
        ${needs.includes("ideas") ? `<label>我的想法</label><textarea data-k="ideas" rows="6" placeholder="口语化、片段式都可以，AI 的任务是帮你结构化">${esc(ctx.ideas)}</textarea>` : ""}
        ${needs.includes("feedback") ? `<label>修改意见</label><div>${feedbackFields(ctx.feedback || {})}</div>` : ""}
        ${needs.includes("article") && fixedArticle == null ? `<label>文章正文</label><textarea data-k="article" rows="8" placeholder="粘贴当前版本全文；会附在 Prompt 末尾">${esc(ctx.article)}</textarea>` : ""}
        ${needs.includes("article") && fixedArticle != null ? `<label>文章正文</label><div class="muted small" style="padding-top:6px">自动附上当前版本（${countChars(fixedArticle)} 字）${fixedArticle.trim() ? "" : "——还没有正文，先在「正文」里保存一版"}</div>` : ""}
        <label>补充说明</label><input type="text" data-k="notes" value="${esc(ctx.notes || "")}" placeholder="可选，例如：控制在 2000 字以内 / 面向公众号读者">
      </div>
      <div class="actions" style="margin:14px 0 10px"><button class="btn primary" id="pCopy">复制 Prompt</button><span class="muted small" id="pInfo"></span></div>
      <div class="prompt-out" id="pOut"></div>`;
    $$(".stage", root).forEach((b) => b.onclick = () => { ctx.stage = b.dataset.stage; onChange?.(); draw(); });
    $$("[data-k]", root).forEach((el) => el.oninput = () => { ctx[el.dataset.k] = el.value; onChange?.(); refresh(); });
    $$("[data-fb]", root).forEach((el) => el.oninput = () => { (ctx.feedback ||= {})[el.dataset.fb] = el.value; onChange?.(); refresh(); });
    $("#pCopy", root).onclick = async () => { await copyText($("#pOut", root).textContent); toast("已复制，粘贴到 AI 对话框即可"); };
    refresh();
  };
  let timer;
  const refresh = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      try {
        const text = await api("/api/prompt", { json: { stage: ctx.stage, topic: ctx.topic, ideas: ctx.ideas, article: fixedArticle ?? ctx.article, feedback: ctx.feedback, notes: ctx.notes } });
        $("#pOut", root).textContent = text;
        $("#pInfo", root).textContent = `${text.length} 字符`;
      } catch (e) { $("#pOut", root).textContent = e.message; }
    }, 150);
  };
  draw();
}

async function renderCompose() {
  app.innerHTML = `<section class="card"><div class="card-head"><div><h2>写作台</h2><span class="muted small">选阶段 → 填主题和想法 → 复制 Prompt 粘贴给 AI。内容会自动记住，也可以存成文章继续改。</span></div>
    <div class="actions"><button class="btn" id="toArticle">存为新文章</button><button class="btn ghost" id="clear">清空</button></div></div>
    <div id="panel"></div></section>`;
  promptPanel($("#panel"), compose, { onChange: saveCompose });
  $("#clear").onclick = () => {
    if (!confirm("清空写作台的输入？")) return;
    Object.assign(compose, { topic: "", ideas: "", article: "", notes: "", feedback: {} });
    saveCompose();
    render();
  };
  $("#toArticle").onclick = () => openNew({ topic: compose.topic, ideas: compose.ideas, text: compose.article });
}

/* ================= 文章库 ================= */

async function renderArticles(token) {
  const list = await api("/api/articles");
  if (token !== state.token) return;
  app.innerHTML = `<section class="card"><div class="card-head"><div><h2>文章</h2><span class="muted small">${list.length} 篇 · 保存在 ${esc(state.meta.articles_dir)}</span></div>
    <div class="actions"><input type="text" id="q" placeholder="搜标题或主题" style="width:200px"><select id="st"><option value="">全部状态</option>${state.meta.statuses.map((s) => `<option>${s}</option>`).join("")}</select></div></div>
    <div id="tbl"></div></section>`;
  const draw = () => {
    const q = $("#q").value.trim().toLowerCase(), st = $("#st").value;
    const rows = list.filter((a) => (!q || `${a.title} ${a.topic}`.toLowerCase().includes(q)) && (!st || a.status === st));
    $("#tbl").innerHTML = rows.length ? `<div class="table-wrap"><table class="tbl"><thead><tr><th>标题</th><th>状态</th><th class="num">字数</th><th class="num">版本</th><th>更新</th><th>发表</th></tr></thead><tbody>
      ${rows.map((a) => `<tr class="link" data-id="${esc(a.id)}"><td class="wrap"><b>${esc(a.title)}</b>${a.topic && a.topic !== a.title ? `<div class="muted small">${esc(a.topic)}</div>` : ""}</td>
        <td>${statusBadge(a.status)}</td><td class="num">${a.chars || "—"}</td><td class="num">${a.versions}</td><td>${esc((a.updated || "").slice(0, 16))}</td><td>${esc(a.publish_date || "")}</td></tr>`).join("")}
      </tbody></table></div>` : `<div class="empty">${list.length ? "没有符合条件的文章" : "还没有文章。点右上角「新建文章」，或在写作台填好主题后「存为新文章」。"}</div>`;
    $$("tr[data-id]").forEach((tr) => tr.onclick = () => { location.hash = `#/a/${encodeURIComponent(tr.dataset.id)}`; });
  };
  $("#q").oninput = draw;
  $("#st").onchange = draw;
  draw();
}

function openNew(pre = {}) {
  const m = $("#modal");
  m.innerHTML = `<div class="modal-box wide"><h2>新建文章</h2><div class="modal-body">
    <div class="form-grid"><label>标题</label><input type="text" id="nTitle" value="${esc(pre.title || "")}" placeholder="可以先写个暂定标题">
    <label>主题</label><input type="text" id="nTopic" value="${esc(pre.topic || "")}">
    <label>我的想法</label><textarea id="nIdeas" rows="6">${esc(pre.ideas || "")}</textarea></div>
    ${pre.text ? `<p class="muted small" style="margin-top:8px">写作台里的正文（${countChars(pre.text)} 字）会存为第一个版本。</p>` : ""}</div>
    <div class="modal-foot"><button class="btn ghost" id="nCancel">取消</button><span><button class="btn primary" id="nOk">创建</button></span></div></div>`;
  m.hidden = false;
  $("#nTitle").focus();
  $("#nCancel").onclick = () => { m.hidden = true; };
  $("#nOk").onclick = async () => {
    try {
      const a = await api("/api/articles", { json: { title: $("#nTitle").value, topic: $("#nTopic").value, ideas: $("#nIdeas").value, text: pre.text || "" } });
      m.hidden = true;
      toast("已创建");
      location.hash = `#/a/${encodeURIComponent(a.id)}`;
    } catch (e) { toast(e.message, "warn"); }
  };
}

/* ================= 单篇文章 ================= */

const TABS = [["edit", "正文"], ["prompt", "生成 Prompt"], ["check", "自检"], ["titles", "标题评分"], ["versions", "版本"], ["info", "信息"]];

async function renderArticle(token, id, tab = "edit") {
  const a = await api(`/api/articles/${encodeURIComponent(id)}`);
  if (token !== state.token) return;
  if (!state.draft || state.draft.id !== id) state.draft = { id, text: a.current, ctx: { stage: a.versions.length ? "revise" : "draft", topic: a.topic, ideas: a.ideas, notes: "", feedback: {} } };
  const last = a.versions.at(-1);
  app.innerHTML = `<div class="crumb"><a href="#/articles">文章</a> / ${esc(a.title)}</div>
  <section class="card"><div class="head-row"><div><h1 style="font-size:20px">${esc(a.title)} ${statusBadge(a.status)}</h1>
    <div class="sub muted small">${a.versions.length ? `当前 v${last.n} · ${last.chars} 字 · ${esc(last.source)} · ${esc(last.time.slice(0, 16))}` : "还没有正文"} · 创建于 ${esc(a.created.slice(0, 10))}${a.has_final ? " · 已另存 final.md" : ""}</div></div>
    <div class="actions"><select class="status-sel" id="status">${state.meta.statuses.map((s) => `<option ${s === a.status ? "selected" : ""}>${s}</option>`).join("")}</select></div></div>
    <div class="tabs">${TABS.map(([k, t]) => `<button data-tab="${k}" class="${k === tab ? "on" : ""}">${t}</button>`).join("")}</div>
    <div id="tab"></div></section>`;
  $$(".tabs button").forEach((b) => b.onclick = () => { location.hash = `#/a/${encodeURIComponent(id)}/${b.dataset.tab}`; });
  $("#status").onchange = async (e) => {
    const r = await api(`/api/articles/${encodeURIComponent(id)}`, { method: "PUT", json: { status: e.target.value } });
    toast(r.has_final && ["定稿", "已发表"].includes(r.status) ? `状态改为「${r.status}」，当前版本已另存为 final.md` : `状态改为「${r.status}」`);
    render();
  };
  const box = $("#tab");
  if (tab === "edit") tabEdit(box, a);
  else if (tab === "prompt") tabPrompt(box, a);
  else if (tab === "check") tabCheck(box, a);
  else if (tab === "titles") tabTitles(box, a);
  else if (tab === "versions") await tabVersions(box, a);
  else if (tab === "info") tabInfo(box, a);
}

function tabEdit(box, a) {
  const d = state.draft;
  box.innerHTML = `<div class="actions" style="margin-bottom:10px">
      <select id="vSource">${state.meta.sources.map((s) => `<option>${s}</option>`).join("")}</select>
      <input type="text" id="vNote" placeholder="这一版改了什么（可选）" style="width:280px">
      <button class="btn primary" id="vSave">保存为新版本</button><span class="muted small">Ctrl+S</span>
      <span id="dirty" class="dirty"></span><span class="grow"></span>
      <label class="fitem"><input type="checkbox" id="pv" checked> 预览</label><span class="muted small" id="wc"></span></div>
    <div class="split" id="split"><textarea class="editor" id="ed" placeholder="把 AI 给的初稿或你自己写的正文贴在这里（支持 Markdown）">${esc(d.text)}</textarea><div class="preview md" id="pvBox"></div></div>`;
  const ed = $("#ed");
  const upd = () => {
    d.text = ed.value;
    state.dirty = d.text !== a.current;
    $("#dirty").textContent = state.dirty ? "● 有未保存的修改" : "";
    $("#wc").textContent = `${countChars(d.text)} 字 · 约 ${Math.max(1, Math.round(countChars(d.text) / 400))} 分钟`;
    if ($("#pv").checked) $("#pvBox").innerHTML = renderMd(d.text);
  };
  ed.oninput = upd;
  $("#pv").onchange = () => { $("#pvBox").hidden = !$("#pv").checked; $("#split").style.gridTemplateColumns = $("#pv").checked ? "" : "1fr"; upd(); };
  if (!a.versions.length) $("#vSource").value = "AI 初稿";
  const save = async () => {
    try {
      await api(`/api/articles/${encodeURIComponent(a.id)}/versions`, { json: { text: ed.value, note: $("#vNote").value, source: $("#vSource").value } });
      state.dirty = false;
      toast("已保存为新版本");
      render();
    } catch (e) { toast(e.message, "warn"); }
  };
  $("#vSave").onclick = save;
  ed.onkeydown = (e) => { if (e.key === "s" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); save(); } };
  upd();
}

function tabPrompt(box, a) {
  box.innerHTML = `<p class="muted small" style="margin-bottom:10px">主题和想法取自「信息」页；修改反馈和质量检查会自动附上${state.dirty ? "编辑器里（含未保存修改）" : "当前版本"}的正文。AI 回复后，把新稿贴回「正文」存为新版本。</p><div id="panel"></div>`;
  promptPanel($("#panel"), state.draft.ctx, { fixedArticle: state.draft.text });
}

function issueHtml(it) {
  const ex = esc(it.excerpt || "").replace(/【/g, "<mark>").replace(/】/g, "</mark>");
  return `<div class="issue k-${esc(it.kind.replace(/\s/g, ""))}"><b>${esc(it.kind)}</b> <span class="muted small">${it.para ? `第 ${it.para} 段` : "全文"} · ${esc(it.text)}</span>
    ${ex ? `<div>${ex}</div>` : ""}<div class="why">${esc(it.note)}</div></div>`;
}

function checkResult(r) {
  const st = r.stats;
  const kinds = Object.entries(r.summary);
  return `<div class="stat-row four" style="margin-bottom:12px">
      <div class="stat"><small>字数</small><b>${st.chars}</b></div><div class="stat"><small>段落</small><b>${st.paragraphs}</b><span class="muted small">平均 ${st.avg_paragraph} 字</span></div>
      <div class="stat"><small>阅读时长</small><b>${st.minutes}</b><span class="muted small">分钟</span></div>
      <div class="stat"><small>提示</small><b>${r.issues.length}</b><span class="muted small">${kinds.map(([k, n]) => `${esc(k)} ${n}`).join(" · ") || "无"}</span></div></div>
    ${r.title_notes.map((t) => `<div class="notice small" style="margin-bottom:8px">标题：${esc(t)}</div>`).join("")}
    <div class="grid2"><div><h3 style="margin-bottom:6px">表达</h3>${r.issues.map(issueHtml).join("") || `<div class="empty">规则没扫到问题</div>`}</div>
    <div><h3 style="margin-bottom:6px">需要查证的句子（${r.facts.length}）</h3><p class="muted small">含具体数字、时间、引用来源或公司动态。不确定就改成更稳妥的说法，或明确是作者判断。</p>
      ${r.facts.map((f) => `<div class="issue"><span class="muted small">第 ${f.para} 段 · ${esc(f.signals.join(" / "))}</span><div>${esc(f.sentence)}</div></div>`).join("") || `<div class="empty">没有</div>`}</div></div>
    <p class="muted small" style="margin-top:12px">规则自检只是初筛：引用原话、刻意的修辞都可能被误报。基本满意后，用「质量检查」Prompt 让 AI 做反方审稿和事实风险扫描。</p>`;
}

async function tabCheck(box, a) {
  box.innerHTML = `<div class="loading">检查中…</div>`;
  const r = await api("/api/check", { json: { text: state.draft.text, title: a.title } });
  box.innerHTML = (state.dirty ? `<div class="notice small" style="margin-bottom:10px">检查的是编辑器里的内容（含未保存的修改）</div>` : "") + checkResult(r);
}

function tabTitles(box, a) {
  const t = state.meta.titles;
  if (!t.ok) {
    box.innerHTML = `<div class="notice">${esc(t.reason)}</div><p class="muted small" style="margin-top:8px">标题评分借用公众号工作空间（content/wxpubaccount）的爆款预测器，基于你账号的历史数据。</p>`;
    return;
  }
  const ctx = state.draft;
  ctx.titles ??= a.title;
  box.innerHTML = `<div class="form-grid">
      <label>候选标题</label><textarea id="tt" rows="4" placeholder="每行一个">${esc(ctx.titles)}</textarea>
      <label>主题关键词</label><input type="text" id="tp" value="${esc(a.topics || "")}" placeholder="逗号分隔，如 微信,AI,工具">
      <label>计划发文</label><div class="actions"><select id="td">${state.meta.weekdays.map((d) => `<option ${d === (a.day || "周二") ? "selected" : ""}>${d}</option>`).join("")}</select>
        <button class="btn primary" id="tGo">评分</button><span class="muted small">基准日期 ${esc(t.baseline_date || "—")} · 评分是参考，不是门槛</span></div></div>
    <div id="tOut" style="margin-top:14px"></div>`;
  $("#tt").oninput = () => { ctx.titles = $("#tt").value; };
  $("#tGo").onclick = async () => {
    const titles = $("#tt").value.split("\n").map((s) => s.trim()).filter(Boolean);
    try {
      await api(`/api/articles/${encodeURIComponent(a.id)}`, { method: "PUT", json: { topics: $("#tp").value, day: $("#td").value } });
      a.topics = $("#tp").value;
      a.day = $("#td").value;
      const res = await api("/api/titles", { json: { titles, topics: $("#tp").value, day: $("#td").value } });
      $("#tOut").innerHTML = `<div class="table-wrap"><table class="tbl"><thead><tr><th>标题</th><th class="num">阅读</th><th class="num">涨粉</th><th class="num">互动</th><th>判断</th><th></th></tr></thead><tbody>
        ${res.map((r) => `<tr><td class="wrap"><b>${esc(r.title)}</b> ${r.prediction_pass ? `<span class="badge ok">通过</span>` : `<span class="badge amber">未通过</span>`} <span class="badge gray">${esc(r.positioning_status)}</span>
          <div class="muted small">${r.suggestions.map(esc).join("；")}${r.saturation_notes.length ? `<br>⚠️ ${esc(r.saturation_notes[0])}` : ""}</div></td>
          <td class="num">${r.read_score}</td><td class="num">${r.follow_score}</td><td class="num">${r.interaction}</td><td class="wrap">${esc(r.verdict)}</td>
          <td><button class="btn ghost" data-use="${esc(r.title)}">${r.title === a.title ? "当前标题" : "用这个"}</button></td></tr>`).join("")}</tbody></table></div>`;
      $$("[data-use]").forEach((b) => b.onclick = async () => {
        await api(`/api/articles/${encodeURIComponent(a.id)}`, { method: "PUT", json: { title: b.dataset.use } });
        toast("标题已更新");
        render();
      });
    } catch (e) { $("#tOut").innerHTML = `<div class="notice">${esc(e.message)}</div>`; }
  };
}

async function tabVersions(box, a) {
  if (!a.versions.length) { box.innerHTML = `<div class="empty">还没有版本</div>`; return; }
  const vs = a.versions.slice().reverse();
  box.innerHTML = `<div class="grid2" style="grid-template-columns:minmax(0,1fr) minmax(0,2fr)"><div class="ver-list"><table class="tbl compact"><tbody>
    ${vs.map((v) => `<tr class="link" data-n="${v.n}"><td><b>v${v.n}</b></td><td>${esc(v.source)}<div class="muted small">${esc(v.time.slice(5, 16))} · ${v.chars} 字${v.note ? ` · ${esc(v.note)}` : ""}</div></td></tr>`).join("")}
    </tbody></table></div><div id="vView"><div class="empty">点左边的版本查看，和上一版逐段对比</div></div></div>`;
  const show = async (n) => {
    $$("tr[data-n]", box).forEach((tr) => tr.classList.toggle("hl", +tr.dataset.n === n));
    const cur = await api(`/api/articles/${encodeURIComponent(a.id)}/versions/${n}`);
    const prevV = a.versions.filter((v) => v.n < n).at(-1);
    const prev = prevV ? await api(`/api/articles/${encodeURIComponent(a.id)}/versions/${prevV.n}`) : null;
    let mode = prev ? "diff" : "text";
    const draw = () => {
      $("#vView").innerHTML = `<div class="actions" style="margin-bottom:10px">${prev ? `<div class="seg-btns"><button data-m="diff" class="${mode === "diff" ? "on" : ""}">对比 v${prevV.n}</button><button data-m="text" class="${mode === "text" ? "on" : ""}">全文</button></div>` : ""}
        <button class="btn" id="vCopy">复制这一版</button>${n !== a.versions.at(-1).n ? `<button class="btn" id="vRestore">恢复为最新版本</button>` : ""}</div>
        ${mode === "diff" ? diffHtml(prev, cur) : `<div class="md">${renderMd(cur)}</div>`}`;
      $$("[data-m]").forEach((b) => b.onclick = () => { mode = b.dataset.m; draw(); });
      $("#vCopy").onclick = () => copyText(cur).then(() => toast("已复制"));
      if ($("#vRestore")) $("#vRestore").onclick = async () => {
        await api(`/api/articles/${encodeURIComponent(a.id)}/versions`, { json: { text: cur, note: `恢复自 v${n}`, source: "我写的" } });
        state.draft = null;
        toast(`已把 v${n} 存为最新版本`);
        render();
      };
    };
    draw();
  };
  $$("tr[data-n]", box).forEach((tr) => tr.onclick = () => show(+tr.dataset.n));
  show(vs[0].n);
}

function tabInfo(box, a) {
  box.innerHTML = `<div class="form-grid">
    <label>标题</label><input type="text" id="iTitle" value="${esc(a.title)}">
    <label>主题</label><input type="text" id="iTopic" value="${esc(a.topic)}">
    <label>我的想法</label><textarea id="iIdeas" rows="8">${esc(a.ideas)}</textarea>
    <label>备注</label><textarea id="iNotes" rows="3" placeholder="资料链接、待查证的事实、审稿意见……">${esc(a.notes || "")}</textarea>
    <label>发表日期</label><input type="date" id="iDate" value="${esc(a.publish_date || "")}" style="width:180px">
    <label>文章链接</label><input type="url" id="iUrl" value="${esc(a.url || "")}" placeholder="发表后填上，方便回到公众号复盘">
    <label></label><div class="actions"><button class="btn primary" id="iSave">保存</button><button class="btn ghost" id="iDel">删除文章</button>
      <span class="muted small">目录：${esc(a.path)}</span></div></div>`;
  $("#iSave").onclick = async () => {
    const r = await api(`/api/articles/${encodeURIComponent(a.id)}`, { method: "PUT", json: { title: $("#iTitle").value, topic: $("#iTopic").value, ideas: $("#iIdeas").value, notes: $("#iNotes").value, publish_date: $("#iDate").value, url: $("#iUrl").value } });
    Object.assign(state.draft.ctx, { topic: r.topic, ideas: r.ideas });
    toast("已保存");
    render();
  };
  $("#iDel").onclick = async () => {
    if (!confirm(`把《${a.title}》移到 articles/_trash？`)) return;
    await api(`/api/articles/${encodeURIComponent(a.id)}`, { method: "DELETE" });
    state.draft = null;
    toast("已移到回收目录");
    location.hash = "#/articles";
  };
}

/* ================= 自检（任意文本） ================= */

function renderCheck() {
  app.innerHTML = `<section class="card"><div class="card-head"><div><h2>自检</h2><span class="muted small">粘贴任意稿子，扫一遍 AI 腔、绝对化表述、长句长段和需要查证的句子</span></div></div>
    <div class="form-grid"><label>标题</label><input type="text" id="cTitle"><label>正文</label><textarea id="cText" rows="12"></textarea>
    <label></label><div class="actions"><button class="btn primary" id="cGo">检查</button></div></div><div id="cOut" style="margin-top:16px"></div></section>`;
  $("#cGo").onclick = async () => {
    const r = await api("/api/check", { json: { text: $("#cText").value, title: $("#cTitle").value } });
    $("#cOut").innerHTML = checkResult(r);
  };
}

/* ================= 工作流说明 ================= */

async function renderWorkflow(token) {
  const md = await api("/api/workflow");
  if (token !== state.token) return;
  app.innerHTML = `<section class="card"><div class="md">${renderMd(md)}</div></section>`;
}

/* ================= 指引 ================= */

const GUIDE = [
  ["写作台", "选一个阶段（观点拓展 / 轻量初稿 / 极简初稿 / 修改反馈 / 质量检查），填主题和想法，右侧实时拼好完整 Prompt，复制粘贴给任意 AI。输入会自动记住。"],
  ["文章", "想认真写的稿子存成文章：AI 每给一版就贴进「正文」存为新版本，版本只增不改，可以逐段对比、随时恢复。"],
  ["自检和标题", "「自检」用规则扫 AI 腔、绝对化、长句和需查证的句子；「标题评分」借用公众号的爆款预测器比较几个标题。都是参考，取舍在你。"],
  ["定稿", "把状态改成「定稿」或「已发表」，当前版本会另存为 final.md。发表后在「信息」里填上日期和链接，之后去公众号分析复盘。"],
];
function openGuide(i = 0) {
  const m = $("#modal");
  const [t, body] = GUIDE[i];
  m.innerHTML = `<div class="modal-box"><div class="modal-step">${i + 1} / ${GUIDE.length}</div><h2>${esc(t)}</h2><div class="modal-body"><p>${esc(body)}</p></div>
    <div class="modal-foot"><button class="btn ghost" id="gClose">关闭</button><span>${i ? `<button class="btn" id="gPrev">上一步</button>` : ""}
    ${i < GUIDE.length - 1 ? `<button class="btn primary" id="gNext">下一步</button>` : `<button class="btn primary" id="gDone">开始使用</button>`}</span></div></div>`;
  m.hidden = false;
  const close = () => { m.hidden = true; localStorage.setItem("writing_guide_v1", "1"); };
  $("#gClose").onclick = close;
  if ($("#gDone")) $("#gDone").onclick = close;
  if ($("#gPrev")) $("#gPrev").onclick = () => openGuide(i - 1);
  if ($("#gNext")) $("#gNext").onclick = () => openGuide(i + 1);
}
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") $("#modal").hidden = true; });

/* ================= 路由 ================= */

const LINKS = [["", "写作台"], ["articles", "文章"], ["check", "自检"], ["workflow", "工作流"]];

async function render() {
  const token = ++state.token;
  const [page, a, b] = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  const cur = page === "a" ? "articles" : page || "";
  $("#nav").innerHTML = LINKS.map(([h, t]) => `<a href="#/${h}" class="${h === cur ? "on" : ""}">${t}</a>`).join("");
  if (page !== "a" || (state.draft && state.draft.id !== a)) { state.draft = null; state.dirty = false; }
  try {
    if (!page) await renderCompose();
    else if (page === "articles") await renderArticles(token);
    else if (page === "a" && a) await renderArticle(token, a, TABS.some(([k]) => k === b) ? b : "edit");
    else if (page === "check") renderCheck();
    else if (page === "workflow") await renderWorkflow(token);
    else location.replace("#/");
  } catch (e) {
    if (token !== state.token) return;
    app.innerHTML = `<div class="card error"><h2>${e.status === 404 ? "找不到" : "加载失败"}</h2><p>${esc(e.message)}</p>
      <p class="muted">请确认服务正在运行（双击 scripts\\start_server.bat），然后刷新页面。<a href="#/">回到写作台</a></p></div>`;
  }
}

/** 离开有未保存修改的文章时确认 */
window.addEventListener("hashchange", (e) => {
  const leaving = state.draft && state.dirty && !location.hash.startsWith(`#/a/${encodeURIComponent(state.draft.id)}`);
  if (leaving && !confirm("正文有未保存的修改，确定离开？（选「取消」留在这里）")) {
    history.replaceState(null, "", e.oldURL);
    return;
  }
  render();
});
window.addEventListener("beforeunload", (e) => { if (state.dirty) { e.preventDefault(); e.returnValue = ""; } });

async function boot() {
  $("#btnNew").onclick = () => openNew();
  $("#btnGuide").onclick = () => openGuide(0);
  try {
    state.meta = await api("/api/meta");
  } catch (e) {
    app.innerHTML = `<div class="card error"><h2>无法连接服务</h2><p>${esc(e.message)}</p>
      <p class="muted">请双击 scripts\\start_server.bat 启动服务，并通过 http://127.0.0.1:8331 打开页面。</p></div>`;
    return;
  }
  await render();
  if (!localStorage.getItem("writing_guide_v1")) openGuide(0);
}

boot();

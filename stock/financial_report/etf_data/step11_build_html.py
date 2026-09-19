# -*- coding: utf-8 -*-
"""Step11: 生成交互式 HTML 清单"""
import json
from collections import Counter, defaultdict
from pathlib import Path

IN = "etf_final_merged.json"
OUT = Path(__file__).resolve().parent.parent / "output" / "etf-50yi-dedup.html"

with open(IN, encoding="utf-8") as f:
    rows = json.load(f)

# 精简字段
data = []
for r in rows:
    data.append({
        "rank": r["rank"],
        "code": r["code"],
        "name": r["name"],
        "track": r["track"],
        "mv": round(r["mv"] / 1e8, 2),
        "cat": r["category"],
        "mgfee": (r.get("mgfee") or "").replace("（每年）", ""),
        "gsize": r["group_size"],
        "gtotal": round(r["group_total"] / 1e8, 2),
        "rivals": [{"code": x["code"], "name": x["name"], "mv": round(x["mv"] / 1e8, 2)}
                   for x in r.get("rivals", [])],
        "tx": round(r["tx_mv"], 2) if r.get("tx_mv") else None,
    })

cat_stat = Counter(r["cat"] for r in data)
cat_sum = defaultdict(float)
for r in data:
    cat_sum[r["cat"]] += r["mv"]
total_mv = sum(r["mv"] for r in data)

payload = json.dumps(data, ensure_ascii=False)
stat = json.dumps({k: {"n": v, "sum": round(cat_sum[k], 0)}
                   for k, v in cat_stat.items()}, ensure_ascii=False)

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A股规模超50亿ETF清单（按跟踪指数去重）</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:"Microsoft YaHei","PingFang SC","Helvetica Neue",Arial,sans-serif;
background:#f4f6f9;color:#1f2937;line-height:1.6;padding:24px}}
.wrap{{max-width:1400px;margin:0 auto}}
h1{{font-size:24px;font-weight:700;color:#0f172a;margin-bottom:6px}}
.sub{{color:#64748b;font-size:13px;margin-bottom:20px}}
.note{{background:#fff;border:1px solid #e2e8f0;border-left:4px solid #2563eb;
border-radius:8px;padding:16px 18px;margin-bottom:20px;font-size:13px;color:#475569}}
.note b{{color:#0f172a}}
.note ul{{margin:8px 0 0 18px}}
.note li{{margin-bottom:4px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:20px}}
.card{{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:14px 16px}}
.card .k{{font-size:12px;color:#64748b;margin-bottom:4px}}
.card .v{{font-size:22px;font-weight:700;color:#0f172a}}
.card .u{{font-size:12px;color:#94a3b8;font-weight:400;margin-left:3px}}
.bar{{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:14px 16px;margin-bottom:14px;
display:flex;flex-wrap:wrap;gap:10px;align-items:center}}
.bar input{{flex:1;min-width:220px;padding:9px 12px;border:1px solid #cbd5e1;border-radius:7px;
font-size:14px;outline:none;font-family:inherit}}
.bar input:focus{{border-color:#2563eb;box-shadow:0 0 0 3px rgba(37,99,235,.1)}}
.chip{{padding:7px 14px;border:1px solid #cbd5e1;border-radius:20px;font-size:13px;cursor:pointer;
background:#fff;color:#475569;transition:.15s;user-select:none;white-space:nowrap}}
.chip:hover{{border-color:#2563eb;color:#2563eb}}
.chip.on{{background:#2563eb;border-color:#2563eb;color:#fff;font-weight:600}}
.tbox{{background:#fff;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden}}
table{{width:100%;border-collapse:collapse;font-size:13.5px}}
th{{background:#f8fafc;padding:11px 10px;text-align:left;font-weight:600;color:#475569;
border-bottom:2px solid #e2e8f0;cursor:pointer;user-select:none;white-space:nowrap;font-size:13px}}
th:hover{{background:#eef2f7;color:#2563eb}}
th .ar{{color:#94a3b8;font-size:10px;margin-left:3px}}
td{{padding:10px;border-bottom:1px solid #f1f5f9;vertical-align:middle}}
tbody tr:hover{{background:#f8fafc}}
tbody tr.exp{{background:#eff6ff}}
.num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
.code{{font-family:ui-monospace,Consolas,monospace;color:#475569;font-size:13px}}
.nm{{font-weight:600;color:#0f172a}}
.tk{{color:#475569;font-size:12.5px}}
.tag{{display:inline-block;padding:2px 9px;border-radius:5px;font-size:11.5px;font-weight:600;white-space:nowrap}}
.t-a{{background:#dbeafe;color:#1d4ed8}}
.t-hk{{background:#ede9fe;color:#6d28d9}}
.t-q{{background:#fef3c7;color:#b45309}}
.t-b{{background:#d1fae5;color:#047857}}
.t-m{{background:#fce7f3;color:#be185d}}
.t-c{{background:#ffedd5;color:#c2410c}}
.badge{{background:#f1f5f9;color:#475569;padding:1px 7px;border-radius:4px;font-size:11.5px;cursor:pointer}}
.badge:hover{{background:#e2e8f0;color:#0f172a}}
.rv{{display:none;background:#f8fafc;padding:9px 12px}}
.rv.show{{display:table-row}}
.rvi{{font-size:12.5px;color:#64748b;padding:3px 0}}
.rvi b{{color:#334155}}
.foot{{margin-top:18px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:16px 18px;
font-size:12.5px;color:#64748b}}
.foot b{{color:#334155}}
.foot ul{{margin:8px 0 0 18px}}
.foot li{{margin-bottom:5px}}
.cnt{{font-size:13px;color:#64748b;padding:10px 12px 0}}
</style>
</head>
<body>
<div class="wrap">
<h1>A股规模超 50 亿 ETF 清单</h1>
<div class="sub">按跟踪指数去重（同一指数仅保留规模最大的一只）　·　数据截至 2026-09-04 收盘　·　共 __TOTAL__ 只</div>

<div class="note">
<b>数据口径说明（请先读这段）</b>
<ul>
<li><b>规模 = 场内总市值</b>（最新份额 × 现价），反映当前实际规模。已用腾讯行情第三方交叉验证：
东财与腾讯市值差异<b>中位数 0.05%</b>，两者一致。</li>
<li><b>为什么不用"基金资产净值"</b>：东财 F10 的净资产规模是<b>定期报告口径</b>，
截止 2026-06-30，滞后两个多月。例：沪深300ETF华泰柏瑞报告口径 948.72 亿，实时市值口径 1067.25 亿。</li>
<li><b>去重规则</b>：按跟踪指数名称精确匹配分组，组内取市值最大者。已逐个核对 108 个指数名称，
确认无"同一指数、不同写法"的情况（例："中证红利低波动指数"与"中证红利低波动100指数"是两个不同指数，未合并）。</li>
<li><b>货币 ETF</b>（银华日利、华宝添益、货币ETF建信）<b>没有跟踪指数</b>，不适用去重规则，因此全部列出。</li>
<li>点击"同指数 N 只"可展开查看被淘汰的同指数竞品及其规模。</li>
</ul>
</div>

<div class="cards">
<div class="card"><div class="k">入选 ETF</div><div class="v">__TOTAL__<span class="u">只</span></div></div>
<div class="card"><div class="k">覆盖跟踪指数</div><div class="v">__NIDX__<span class="u">个</span></div></div>
<div class="card"><div class="k">合计规模</div><div class="v">__SUM__<span class="u">亿</span></div></div>
<div class="card"><div class="k">原始候选</div><div class="v">209<span class="u">只</span></div></div>
</div>

<div class="bar">
<input id="q" placeholder="搜索：代码 / 名称 / 跟踪指数，如 510300、沪深300、半导体">
<span class="chip on" data-c="all">全部 __TOTAL__</span>
__CHIPS__
</div>

<div class="tbox">
<div class="cnt" id="cnt"></div>
<table>
<thead><tr>
<th data-s="rank">#<span class="ar">↕</span></th>
<th data-s="code">代码<span class="ar">↕</span></th>
<th data-s="name">名称<span class="ar">↕</span></th>
<th data-s="track">跟踪指数<span class="ar">↕</span></th>
<th data-s="mv" class="num">规模(亿)<span class="ar">↕</span></th>
<th data-s="gsize" class="num">同指数<span class="ar">↕</span></th>
<th data-s="mgfee">管理费<span class="ar">↕</span></th>
<th data-s="cat">类别<span class="ar">↕</span></th>
</tr></thead>
<tbody id="tb"></tbody>
</table>
</div>

<div class="foot">
<b>核对说明（数据怎么来的、哪些已验证、哪些有保留）</b>
<ul>
<li><b>数据源</b>：东方财富行情接口（延时节点）+ 天天基金全市场基金表 + 东财 F10 基金概况页，
并以腾讯行情接口做第三方交叉验证。</li>
<li><b>覆盖性已修正</b>：东财 ETF 板块<b>不含债券 ETF</b>，初版遗漏了 48 只规模超 50 亿的 ETF
（其中短融ETF海富通 851 亿、可转债ETF博时 635 亿），已通过全市场基金表差集补齐。</li>
<li><b>已排除</b>：59 只 2026 年新发的未上市 ETF —— 东财与腾讯均无行情数据，
F10 查到的净资产规模均在 2~4.3 亿，远低于 50 亿门槛。</li>
<li><b>50 亿边界较拥挤</b>：有 29 只 ETF 集中在 45~55 亿区间，入选线上下仅差 0.9 亿
（上海国企ETF汇添富 50.81 亿入选 vs 恒生医疗ETF博时 49.88 亿落选）。份额数据每日变动，
边界附近几只的入选状态可能随日更新而翻转，使用时请留意。</li>
<li><b>未核实项</b>：跟踪指数名称取自东财 F10"跟踪标的"字段，未与中证/国证指数公司官网逐一比对；
管理费率取自 F10，仅供排序参考。</li>
<li><b>口径差异已标注</b>：净值口径与市值口径的差异源于份额披露滞后，非数据错误。</li>
</ul>
<div style="margin-top:12px;padding-top:12px;border-top:1px solid #e2e8f0">
本清单仅为数据整理，不构成任何投资建议。基金规模随申赎每日变动，请以基金公司公告为准。
</div>
</div>
</div>

<script>
const DATA = __PAYLOAD__;
const STAT = __STAT__;
let cur = "all", kw = "", sortKey = "mv", sortAsc = false;

const CATCLS = {"境内股票(A股)":"t-a","境内股票(港股通)":"t-hk","跨境/境外(QDII)":"t-q",
"债券":"t-b","货币":"t-m","商品":"t-c"};

function filt(){
  let r = DATA.filter(d => cur==="all" || d.cat===cur);
  if(kw){
    const k = kw.toLowerCase();
    r = r.filter(d => (d.code+d.name+(d.track||"")+d.cat).toLowerCase().includes(k));
  }
  const s = sortKey;
  r.sort((a,b)=>{
    let x=a[s], y=b[s];
    if(x===null||x===undefined) x = s==="mv"?0:"";
    if(y===null||y===undefined) y = s==="mv"?0:"";
    if(typeof x==="string") return sortAsc? x.localeCompare(y,"zh") : y.localeCompare(x,"zh");
    return sortAsc? x-y : y-x;
  });
  return r;
}

function render(){
  const r = filt();
  const tb = document.getElementById("tb");
  tb.innerHTML = r.map(d=>{
    const rv = d.rivals.length ? `
      <tr class="rv" id="rv-${d.code}"><td colspan="8">
      <div class="rvi"><b>同指数竞品（${d.rivals.length} 只，合计 ${d.gtotal} 亿）：</b></div>
      ${d.rivals.map(x=>`<div class="rvi">· ${x.code}　${x.name}　<b>${x.mv} 亿</b></div>`).join("")}
      </div></td></tr>` : "";
    const badge = d.gsize>1 ? `<span class="badge" onclick="tg('${d.code}')">同指数 ${d.gsize} 只 ▾</span>`
                            : `<span style="color:#cbd5e1;font-size:11.5px">独家</span>`;
    return `<tr>
      <td class="num" style="color:#94a3b8">${d.rank}</td>
      <td class="code">${d.code}</td>
      <td class="nm">${d.name||""}</td>
      <td class="tk">${d.track||"<span style='color:#cbd5e1'>—</span>"}</td>
      <td class="num" style="font-weight:700;color:#0f172a">${d.mv.toFixed(2)}</td>
      <td class="num">${badge}</td>
      <td style="color:#64748b;font-size:12.5px">${d.mgfee||"—"}</td>
      <td><span class="tag ${CATCLS[d.cat]||"t-a"}">${d.cat}</span></td>
    </tr>${rv}`;
  }).join("");
  const sum = r.reduce((a,b)=>a+b.mv,0);
  document.getElementById("cnt").innerHTML =
    `显示 <b style="color:#0f172a">${r.length}</b> 只，合计 <b style="color:#0f172a">${sum.toFixed(0)}</b> 亿元`;
}

function tg(code){
  const el = document.getElementById("rv-"+code);
  if(el) el.classList.toggle("show");
}

document.getElementById("q").addEventListener("input", e=>{kw=e.target.value.trim();render();});
document.querySelectorAll(".chip").forEach(c=>{
  c.addEventListener("click", ()=>{
    document.querySelectorAll(".chip").forEach(x=>x.classList.remove("on"));
    c.classList.add("on"); cur=c.dataset.c; render();
  });
});
document.querySelectorAll("th[data-s]").forEach(th=>{
  th.addEventListener("click", ()=>{
    const k = th.dataset.s;
    if(sortKey===k) sortAsc=!sortAsc; else {sortKey=k; sortAsc=(k==="code"||k==="name"||k==="track"||k==="cat");}
    render();
  });
});
render();
</script>
</body>
</html>"""

chips = "".join(
    '<span class="chip" data-c="{k}">{k} {n}</span>'.format(k=k, n=cat_stat[k])
    for k in sorted(cat_stat, key=lambda x: -cat_stat[x])
)

html = (HTML.replace("__PAYLOAD__", payload)
        .replace("__STAT__", stat)
        .replace("__CHIPS__", chips)
        .replace("__TOTAL__", str(len(data)))
        .replace("__NIDX__", str(len({r["track"] for r in data if r["track"]})))
        .replace("__SUM__", "{:,.0f}".format(total_mv)))

with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)
print("已生成: {}".format(OUT))
print("入选 {} 只, 覆盖 {} 个跟踪指数, 合计 {:,.0f} 亿".format(
    len(data), len({r["track"] for r in data if r["track"]}), total_mv))

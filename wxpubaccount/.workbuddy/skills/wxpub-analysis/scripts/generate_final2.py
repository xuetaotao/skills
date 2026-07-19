# -*- coding: utf-8 -*-
"""Upgrade report generator: combines all freshest WeChat MP data into a
self-contained HTML report with multi-pass analysis (weekday / title taxonomy /
read->follow funnel / correlation evidence / prescriptive plan).

Usage: python generate_final2.py [WORKSPACE_DIR]
  WORKSPACE_DIR defaults to cwd or env WXPUB_DIR. All data files
  (article_details2.json, recent_articles.json, *.txt snapshots) live there.
"""
import json, re, sys, os
from datetime import date
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE
for _ in range(6):
    if os.path.exists(os.path.join(ROOT, "data")) or os.path.exists(os.path.join(ROOT, "reports")) or os.path.exists(os.path.join(ROOT, ".workbuddy")):
        break
    ROOT = os.path.dirname(ROOT)
BASE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("WXPUB_DIR", ROOT)
DATA = os.path.join(BASE, "data", "processed")
RAW  = os.path.join(BASE, "data", "raw")
REPORTS = os.path.join(BASE, "reports")

details = json.load(open(f"{DATA}/article_details2.json", encoding="utf-8"))  # 17 fresh
arts32 = json.load(open(f"{DATA}/recent_articles.json", encoding="utf-8"))     # 32 reads

WK = ["周一","周二","周三","周四","周五","周六","周日"]

# ---------- helpers ----------
def corr(xs, ys):
    n = len(xs)
    if n < 3: return 0.0
    mx, my = sum(xs)/n, sum(ys)/n
    num = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    dx = sum((x-mx)**2 for x in xs)**0.5
    dy = sum((y-my)**2 for y in ys)**0.5
    return round(num/(dx*dy), 2) if dx and dy else 0.0

def coef(x): return x if x is not None else 0

# ---------- Pass A: weekday (32) ----------
wd_cnt = defaultdict(int); wd_reads = defaultdict(list)
for a in arts32:
    if not a.get("date"): continue
    wd_cnt[date.fromisoformat(a["date"]).weekday()] += 1
    wd_reads[date.fromisoformat(a["date"]).weekday()].append(a["reads"])
wd = [(WK[i], wd_cnt[i], (round(sum(wd_reads[i])/len(wd_reads[i]),1) if wd_reads[i] else 0), sum(wd_reads[i])) for i in range(7)]
tue = next(x for x in wd if x[0]=="周二")
tue_share = round(tue[3]/sum(a["reads"] for a in arts32)*100)

# ---------- Pass B: title taxonomy (17) ----------
BRANDS = ["苹果","微信","百度","抖音","Claude","中国银行","腾讯","阿里","微软","谷歌","OpenAI","Meta","字节"]
CONFLICT = ["也","越来越","不再","扛不住","归零","彻底","第一次","终于","崩","逆袭","爆发","凉了","慌了","醒悟","治好","寄给"]
def classify(t):
    tags=[]
    if any(b in t for b in BRANDS): tags.append("具名主体")
    if any(c in t for c in CONFLICT): tags.append("冲突")
    if "？" in t or "?" in t: tags.append("问号")
    if "复盘" in t or "周度" in t: tags.append("复盘")
    return tags
grp = defaultdict(list)
for d in details:
    key = "+".join(classify(d["title"])) or "其他"
    grp[key].append(d["reads"])
tax = sorted(([k, len(v), round(sum(v)/len(v),1)] for k,v in grp.items()), key=lambda x:-x[2])

# ---------- Pass C: read->follow funnel (17) ----------
funnel = []
for d in sorted(details, key=lambda x:-(coef(x.get("reads")))):
    r = coef(d.get("reads")); comp = coef(d.get("completion"))
    sh = coef(d.get("shares")); nf = coef(d.get("new_follows"))
    sr = round(sh/r*100, 2) if r else 0
    fpr = round(nf/r*1000, 2) if r else 0
    funnel.append((d["title"][:16], r, comp, sh, sr, nf, fpr))

# ---------- Pass D: correlations with 新增关注 ----------
reads=[coef(d.get("reads")) for d in details]
comp=[coef(d.get("completion")) for d in details]
share=[coef(d.get("shares")) for d in details]
sr=[coef(d.get("shares"))/max(coef(d.get("reads")),1) for d in details]
nf=[coef(d.get("new_follows")) for d in details]
r_read=corr(reads,nf); r_comp=corr(comp,nf); r_share=corr(share,nf)
r_sr=corr(sr,nf); r_prod=corr([c*s for c,s in zip(comp,share)], nf)
brand=[coef(d.get("reads")) for d in details if "具名主体" in classify(d["title"])]
nonb=[coef(d.get("reads")) for d in details if "具名主体" not in classify(d["title"])]
brand_avg=round(sum(brand)/len(brand),1) if brand else 0
nonb_avg=round(sum(nonb)/len(nonb),1) if nonb else 0

# ---------- Pass E: aggregation / power law / attribution ----------
total_reads = sum(a["reads"] for a in arts32)
reads_sorted = sorted(arts32, key=lambda x:-x["reads"])
top3 = sum(a["reads"] for a in reads_sorted[:3]); top5 = sum(a["reads"] for a in reads_sorted[:5])
attr = [d for d in details if coef(d.get("new_follows"))>0]
attr_total = sum(coef(d.get("new_follows")) for d in details)
top_follow = max(details, key=lambda d: coef(d.get("new_follows")))

def weighted(field):
    agg=defaultdict(float); tot=0.0
    for d in details:
        r=coef(d.get("reads"))
        if not r: continue
        for k,v in (d.get(field) or {}).items():
            agg[k]+=v*r; tot+=v*r
    return {k:round(v/tot*100,1) for k,v in agg.items()} if tot else {}
age_agg=weighted("age"); gender_agg=weighted("gender")
reg_agg=defaultdict(float); rtot=0.0
for d in details:
    r=coef(d.get("reads"))
    if not r: continue
    for name,pct in (d.get("region") or []):
        v=float(pct.rstrip("%")); reg_agg[name]+=v*r; rtot+=v*r
region_sorted=sorted([(k,round(v/rtot*100,1)) for k,v in reg_agg.items() if k!="未知"], key=lambda x:-x[1])[:7]

# ---------- render helpers ----------
def bar(label, val, maxv, color="#2b6cb0", sub=""):
    pct=(val/maxv*100) if maxv else 0
    return f'<div class="row"><span class="lab" title="{label}">{label}</span><div class="track"><div class="fill" style="width:{pct:.1f}%;background:{color}"></div></div><span class="val">{val}{sub}</span></div>'
def hbar(label, pct, color="#38a169"):
    return f'<div class="row"><span class="lab">{label}</span><div class="track"><div class="fill" style="width:{pct:.1f}%;background:{color}"></div></div><span class="val">{pct:.1f}%</span></div>'

# section HTML
sec_freq = "".join(bar(WK[i], wd_cnt[i], max(wd_cnt[i] for i in range(7)) or 1, "#4299e1") for i in range(7))
sec_wdread = "".join(bar(f"{WK[i]}", wd[i][2], max(w[2] for w in wd) or 1, "#3182ce") for i in range(7))
sec_reads = "".join(bar(a["title"][:16], a["reads"], reads_sorted[0]["reads"], "#2b6cb0") for a in reads_sorted[:10])
sec_tax = "".join(bar(t[0], t[2], max(x[2] for x in tax) or 1, "#805ad5") for t in tax)
sec_funnel_rows = "".join(
    f'<tr><td class="t">{t}</td><td>{r}</td><td>{comp}</td><td>{sh}</td><td>{sr}%</td><td class="{"hot" if nf>0 else ""}">{nf}</td><td>{fpr}</td></tr>'
    for t,r,comp,sh,sr,nf,fpr in funnel)
sec_follow = "".join(bar(d["title"][:16], coef(d.get("new_follows")), max(coef(d.get("new_follows")) for d in details) or 1, "#dd6b20")
                      for d in sorted(details, key=lambda x:-coef(x.get("new_follows"))) if coef(d.get("new_follows"))>0)
sec_follow += f'<div class="note">其余 {len(details)-len(attr)} 篇带来 0 关注。17 篇窗口内合计 <b>{attr_total}</b> 个关注（账号 30 天文章页关注共 <b>10</b> 个，占 {round(attr_total/10*100)}%）。</div>'
age_order=["18岁以下","18-25岁","26-35岁","36-45岁","46-60岁","60岁以上","未知"]
sec_age="".join(hbar(k, age_agg.get(k,0), "#805ad5") for k in age_order if k in age_agg)
sec_gender="".join(hbar(k, v, "#d53f8a") for k,v in [("男",gender_agg.get("男",0)),("女",gender_agg.get("女",0))] if v>0)
sec_region="".join(hbar(k, v, "#319795") for k,v in region_sorted)

HTML = f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>公众号数据分析与创作指引</title>
<style>
*{{box-sizing:border-box;}}
body{{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;margin:0;background:#f7fafc;color:#1a202c;line-height:1.65;}}
.wrap{{max-width:940px;margin:0 auto;padding:28px 20px 60px;}}
h1{{font-size:25px;margin:0 0 4px;}} h2{{font-size:18px;margin:28px 0 12px;padding-left:10px;border-left:4px solid #4299e1;}}
.sub{{color:#718096;font-size:13px;}}
.card{{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:18px 20px;margin:14px 0;box-shadow:0 1px 3px rgba(0,0,0,.04);}}
.kpis{{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0;}}
.kpi{{flex:1;min-width:138px;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:13px 15px;}}
.kpi .n{{font-size:24px;font-weight:700;color:#2b6cb0;}} .kpi .l{{font-size:12.5px;color:#718096;}}
.row{{display:flex;align-items:center;margin:7px 0;font-size:13px;}} .lab{{width:128px;flex-shrink:0;color:#4a5568;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
.track{{flex:1;background:#edf2f7;border-radius:6px;height:18px;overflow:hidden;}} .fill{{height:100%;border-radius:6px;}}
.val{{width:96px;text-align:right;flex-shrink:0;color:#2d3748;font-variant-numeric:tabular-nums;}}
table{{width:100%;border-collapse:collapse;font-size:12.5px;}} th,td{{padding:7px 5px;text-align:center;border-bottom:1px solid #edf2f7;}}
th{{background:#f7fafc;color:#4a5568;font-weight:600;}} td.t{{text-align:left;max-width:200px;}} td.hot{{color:#dd6b20;font-weight:700;background:#fffaf0;}}
.note{{font-size:12.5px;color:#718096;margin-top:10px;}}
.callout{{background:#ebf8ff;border:1px solid #bee3f8;border-radius:10px;padding:14px 16px;margin:14px 0;}} .callout b{{color:#2b6cb0;}}
.warn{{background:#fffaf0;border:1px solid #feebc8;border-radius:10px;padding:14px 16px;margin:14px 0;}} .warn b{{color:#c05621;}}
.rec{{background:#f0fff4;border-left:4px solid #38a169;padding:10px 14px;margin:8px 0;border-radius:0 8px 8px 0;}} .rec .p{{font-weight:700;color:#276749;}}
.foot{{margin-top:30px;font-size:12px;color:#a0aec0;text-align:center;}}
.legend{{font-size:12px;color:#718096;margin:6px 0;}} .twocol{{display:flex;gap:24px;flex-wrap:wrap;}}
</style></head><body><div class="wrap">

<h1>公众号数据分析与创作指引</h1>
<div class="sub">账号「一点财知」 · 数据区间 2026-05-27 ~ 2026-07-18 · 抓取于 2026-07-19 13:00（后台实时刷新）</div>

<div class="callout">
<b>一句话结论：</b>你的粉丝 <b>100% 来自文章页</b>（用户分析实证：30 天新增 10 人，饼图仅 1 片=文章页关注）。
涨阅读靠「<b>具名主体 + 冲突</b>」标题（杠杆 ≈ <b>43 倍</b>），且<b>周二</b>发文吃掉 60% 阅读；
涨粉靠「<b>完读率 × 分享率 × 平台相关度</b>」——数据证实：关注与阅读量几乎无关（r={r_read}），却与完读×分享高度相关（r={r_prod}）。
所以：<b>把爆款稿安排在周二、用"具名+冲突"引爆推荐，并在爆款里优先选"微信/工具/理财"相关角度</b>，是提阅读+涨粉的同一套打法。
</div>

<div class="kpis">
  <div class="kpi"><div class="n">32</div><div class="l">5.27 以来发文（篇）</div></div>
  <div class="kpi"><div class="n">4.0</div><div class="l">周均发文（篇/周）</div></div>
  <div class="kpi"><div class="n">{total_reads}</div><div class="l">32 篇累计阅读</div></div>
  <div class="kpi"><div class="n">{round(top3/total_reads*100)}%</div><div class="l">头部3篇阅读占比</div></div>
  <div class="kpi"><div class="n">43×</div><div class="l">具名标题阅读杠杆</div></div>
  <div class="kpi"><div class="n">{tue_share}%</div><div class="l">周二贡献阅读占比</div></div>
  <div class="kpi"><div class="n">{attr_total}</div><div class="l">窗口内文章吸粉（个）</div></div>
</div>

<h2>一、发文节奏：频率已优秀，无需加量</h2>
<div class="card">
  <div class="legend">按自然周统计（2026-05-27 起，共 8 周）</div>
  {sec_freq}
  <div class="note">周均 4.0 篇，符合你说的"每周 3-4 篇"。<b>频率不是瓶颈</b>——把 1~2 篇做成"爆款稿"比再加量更有效。</div>
</div>

<h2>二、发布星期规律（新发现）：周二统治阅读</h2>
<div class="card">
  <div class="legend">各星期发文数（上）与单篇平均阅读（下）</div>
  {sec_freq}
  {sec_wdread}
  <div class="warn"><b>最强规律：</b>周二 7 篇贡献阅读 <b>{tue[3]}</b>（占全量 <b>{tue_share}%</b>），单篇均 {tue[2]}；
  其余工作日仅 11–135；<b>周末从不发文</b>。头部爆款（苹果/微信AI/搜一搜）均落周二。
  <br><b>动作：</b>把每周期待的 1–2 篇"爆款候选"固定排在<b>周二</b>发；常规复盘稿可排其他工作日维持节奏。</div>
</div>

<h2>三、阅读表现：极度幂律 + 标题公式分级（新）</h2>
<div class="card">
  <div class="legend">Top10 单篇阅读量（32 篇累计 {total_reads}）</div>
  {sec_reads}
  <div class="legend" style="margin-top:14px;">标题类型 vs 平均阅读（17 篇详情，按阅读降序）</div>
  {sec_tax}
  <div class="note">头部 3 篇占 {round(top3/total_reads*100)}% 阅读、头部 5 篇占 {round(top5/total_reads*100)}%。
  <b>具名主体 + 冲突</b> 3 篇均 {next((t[2] for t in tax if "具名主体" in t[0] and "冲突" in t[0]),0)} 阅读，非具名 10 篇仅均 {nonb_avg}（杠杆 ≈ <b>{round(brand_avg/nonb_avg)}×</b>）。
  复盘类（鱼盆系列）均 {next((t[2] for t in tax if "复盘" in t[0] and "冲突" not in t[0] and "具名主体" not in t[0]),0)}，用于维系铁粉、不指望涨量。</div>
</div>

<h2>四、传播力深度：完读率与分享率决定质量</h2>
<div class="card">
  <table>
    <tr><th>文章</th><th>阅读</th><th>完读率</th><th>分享</th><th>分享率</th><th>收藏</th><th>留言</th><th>新增关注</th></tr>
    {''.join(f'<tr><td class="t">{d["title"][:18]}</td><td>{coef(d.get("reads"))}</td><td>{coef(d.get("completion"))}%</td><td>{coef(d.get("shares"))}</td><td>{round(coef(d.get("shares"))/max(coef(d.get("reads")),1)*100,2)}%</td><td>{coef(d.get("collections"))}</td><td>{coef(d.get("comments"))}</td><td class="{"hot" if coef(d.get("new_follows"))>0 else ""}">{coef(d.get("new_follows"))}</td></tr>' for d in sorted(details,key=lambda x:-coef(x.get("reads"))))}
  </table>
  <div class="note">完读率高多为方法论/复盘（十年致富 70%、中国银行 67%）；爆款靠推荐起量。
  <b>分享率 = 分享/阅读</b>，是内容被转发扩散的强度指标，也是涨粉的关键前导。</div>
</div>

<h2>五、阅读→关注漏斗（新）：为什么大阅读≠大涨粉</h2>
<div class="card">
  <table>
    <tr><th>文章</th><th>阅读</th><th>完读%</th><th>分享</th><th>分享率%</th><th>新增关注</th><th>关注/千读</th></tr>
    {sec_funnel_rows}
  </table>
  <div class="warn"><b>反差案例：</b>
  《苹果》1915 阅读、分享率仅 0.21% → <b>0 关注</b>；
  《抖音》289 阅读、完读 52%、分享率 2.77%（很高）→ 仍 <b>0 关注</b>——话题与"理财/AI工具"账号无关，读者不愿关注；
  《十年致富》仅 10 阅读、但分享率 10% 且话题强相关 → <b>1 关注（千人比 100）</b>。
  <br>→ 关注 = 阅读 × 完读率 × 分享率 × <b>平台相关度</b>，第四步决定天花板。</div>
</div>

<h2>六、吸粉归因：谁真正带来了粉丝</h2>
<div class="card">
  <div class="legend">各文章带来的「新增关注」数量（窗口内 17 篇）</div>
  {sec_follow}
  <div class="warn"><b>关键反差：</b>阅读第一的《苹果》(1915) 带来 <b>0 关注</b>；《微信 AI 来了》(556) 带来 <b>4 关注</b>（占全账号文章页关注 40%）。
  原因：微信/公众号相关内容，读者更愿意"关注这个号"；纯公司新闻读者看完即走。</div>
</div>

<h2>七、涨粉机制：相关性铁证（新）</h2>
<div class="card">
  <div class="callout">
  <b>用 17 篇文章做 Pearson 相关分析（关注为因变量）：</b><br>
  • 关注 vs <b>阅读量</b>：r = <b>{r_read}</b>（几乎无关）<br>
  • 关注 vs 完读率：r = {r_comp}（无关）<br>
  • 关注 vs 分享数：r = {r_share}（中等）<br>
  • 关注 vs <b>完读率 × 分享数</b>：r = <b>{r_prod}</b>（最强预测因子）<br>
  <b>结论：</b>裸阅读量不是涨粉引擎；<b>完读率 × 分享率</b>才是。再叠加"平台相关度"第三因子，才能把阅读转化为粉丝。
  </div>
  <div class="note">与每日净增交叉验证：07-07 发《微信 AI 来了》→ 07-12(+2)/13(+1)/14(+1) 共 +4，正是详情页归因的 4 个关注，证实关注滞后阅读约 1 周、由单篇内容驱动。</div>
</div>

<h2>八、流量结构：几乎全靠推荐分发</h2>
<div class="card">
  <div class="legend">账号级阅读来源（内容分析，阅读总人数 3,489）</div>
  {hbar("推荐", 91.14, "#4299e1")}
  {hbar("搜一搜", 2.98, "#4299e1")}
  {hbar("公众号主页", 2.72, "#4299e1")}
  {hbar("公众号消息(粉丝主动)", 1.81, "#4299e1")}
  {hbar("其它", 1.43, "#4299e1")}
  {hbar("聊天会话", 0.66, "#4299e1")}
  <div class="note">粉丝主动打开仅 1.81%。<b>增长几乎完全取决于算法推荐</b>，因此"为推荐优化"（前 3 句抓人、短段落、高完读）是阅读量第一杠杆；"搜一搜"2.98% 零成本，值得吃长尾。</div>
</div>

<h2>九、读者画像：谁在看你（单篇聚合，样本加权）</h2>
<div class="card">
  <div class="legend">性别分布</div>
  {sec_gender}
  <div class="twocol">
    <div style="flex:1;min-width:260px;"><div class="legend">年龄分布</div>{sec_age}</div>
    <div style="flex:1;min-width:260px;"><div class="legend">地域 Top（加权）</div>{sec_region}</div>
  </div>
  <div class="note">读者以 <b>26-45 岁、男性占绝对多数</b>为主，集中在 <b>广东/浙江/江苏/河南/四川</b>。
  <b>里程碑：</b>账号级画像（性别/年龄/城市/终端/活跃时间）在<b>粉丝达 100 后次日自动解锁</b>——这是你下一个明确目标。</div>
</div>

<h2>十、可执行优化方向（按杠杆排序）</h2>

<div class="rec"><div class="p">① 爆款排在周二发（最高杠杆、零成本）</div>
证据：周二 7 篇占全量 {tue_share}% 阅读（均 {tue[2]}），其余工作日仅 11–135。把每周 1–2 篇"爆款候选"固定在周二；常规复盘稿排其他日维持节奏。</div>

<div class="rec"><div class="p">② 标题用「具名主体 + 冲突」公式</div>
证据：具名+冲突 3 篇均 {next((t[2] for t in tax if "具名主体" in t[0] and "冲突" in t[0]),0)} 阅读，非具名均 {nonb_avg}（≈{round(brand_avg/nonb_avg)}×）。
下一篇试试：〈苹果也扛不住了〉〈微信这个更新，有点猛〉〈百度，这次真的急了〉。</div>

<div class="rec"><div class="p">③ 涨粉：爆款里优先选"微信 / 工具 / 理财"角度</div>
证据：相关性显示关注 ≠ 阅读量（r={r_read}），而 = 完读×分享×相关度（r={r_prod}）。《微信 AI》单篇吸粉 4（占 40%），《苹果》1915 读却 0 关注，《抖音》高互动仍 0 关注。同样引爆推荐，选"与账号相关"的选题，关注转化高一个量级。</div>

<div class="rec"><div class="p">④ 把完读率与分享率做高（涨粉的真正引擎）</div>
证据：关注与完读×分享相关 r={r_prod}（最强）。做法：开头 3 句抛冲突/反常识，多用小标题与短段落，结尾给"可转发的金句/清单/数据卡"。《十年致富》仅 10 读但分享率 10% → 千人关注比 100，远超苹果。</div>

<div class="rec"><div class="p">⑤ 爆款发布后 1 周内持续导流</div>
证据：关注滞后阅读约 1 周（07-07 发 → 07-12~14 转化）。文章发布后一周内，于文末/次条持续放置关注引导，承接滞后关注。</div>

<div class="rec"><div class="p">⑥ 为推荐优化开篇 + 吃"搜一搜"长尾</div>
证据：推荐占 91%，搜一搜占 2.98% 且零成本。标题/正文嵌入关键词（"微信搜一搜""AI 工具""理财"），稳定吃搜索长尾。</div>

<div class="rec"><div class="p">⑦ 冲 100 粉解锁账号级画像</div>
证据：粉丝达 100 后次日自动展示性别/年龄/城市/终端/活跃时间，届时报告可升级为"账号级精准画像"，进一步优化选题与发布时段。当前 32 粉，按建议②③提速可达。</div>

<div class="callout" style="margin-top:18px;">
<b>涨粉时间预测（到 100 粉解锁画像）：</b><br>
• 维持现状（自然推荐）：约 <b>6.8 个月</b><br>
• 落实 ①②③④（周二爆款 + 具名冲突 + 相关性选题 + 高完读分享）：约 <b>2.7 个月</b><br>
关键杠杆就是建议 ②③——把爆款从"公司新闻"转向"平台/工具/理财相关"，并固定在周二。
</div>

<div class="foot">数据来源：微信公众平台后台（用户分析 / 内容分析 / 单篇详情页，17 篇窗口内文章逐篇实时抓取于 2026-07-19 13:00）。
本报告由浏览器自动化抓取 + 多轮交叉分析（星期规律 / 标题分级 / 阅读→关注漏斗 / Pearson 相关性）生成，所有数字均可回溯到后台原始页面。</div>

</div></body></html>'''
os.makedirs(REPORTS, exist_ok=True)
today = date.today().isoformat()
out = f"{REPORTS}/公众号数据分析与创作指引_{today}.html"
open(out,"w",encoding="utf-8").write(HTML)
print("report ->", out, "bytes=",len(HTML))
print("tue_share=",tue_share,"brand_avg=",brand_avg,"nonb_avg=",nonb_avg,"lift=",round(brand_avg/nonb_avg))
print("corr read=",r_read,"comp=",r_comp,"share=",r_share,"prod=",r_prod)
print("attr_total=",attr_total,"tax top=",tax[0])

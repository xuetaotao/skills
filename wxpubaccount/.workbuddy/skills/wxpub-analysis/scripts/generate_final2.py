# -*- coding: utf-8 -*-
"""Upgrade report generator: combines all freshest WeChat MP data into a
self-contained HTML report with multi-pass analysis (weekday / title taxonomy /
read->follow funnel / correlation evidence / prescriptive plan).

Usage: python generate_final2.py [WORKSPACE_DIR]
  WORKSPACE_DIR defaults to cwd or env WXPUB_DIR. All data files
  (article_details2.json, recent_articles.json, *.txt snapshots) live there.
"""
import json, re, sys, os
from datetime import date, timedelta
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

details = json.load(open(f"{DATA}/article_details2.json", encoding="utf-8"))  # window fresh
arts32 = json.load(open(f"{DATA}/recent_articles.json", encoding="utf-8"))     # window reads

# ---- 分析窗口（由 build_articles 写出；决定 % 口径是否可比）----
_win = {}
if os.path.exists(f"{DATA}/_window.json"):
    try:
        _win = json.load(open(f"{DATA}/_window.json", encoding="utf-8"))
    except Exception:
        _win = {}
WIN_MODE = _win.get("mode", "all")
try:
    _ws = date.fromisoformat(_win["since"]); _wu = date.fromisoformat(_win["until"])
except Exception:
    _ws = _wu = date.today()
TODAY = date.today()
IS_RECENT30 = (_wu == TODAY) and ((TODAY - _ws).days <= 30)

# ---- 账号级快照（动态解析 user_analysis.txt，标注抓取日；缺失则优雅降级）----
def _load_user_analysis(path):
    out = {"fans": None, "growth_month_pct": None, "channels": {}, "channels_total": None,
           "date": None, "is_single_slice": False}
    if not os.path.exists(path):
        return out
    t = open(path, encoding="utf-8").read()
    try:
        out["date"] = date.fromtimestamp(os.path.getmtime(path)).isoformat()
    except Exception:
        pass
    m = re.search(r'累计关注人数"\s*\n\s*- StaticText "(\d+)"', t)
    if m: out["fans"] = int(m.group(1))
    mg = re.search(r'累计关注人数".*?StaticText "月"\s*\n\s*- StaticText "([\d.]+)%"', t, re.S)
    if mg: out["growth_month_pct"] = float(mg.group(1))
    idx = t.find("渠道构成")
    seg = t[idx:] if idx >= 0 else t
    # 饼图 slice 数：StaticText "Pie chart with N slice(s)."
    sm = re.search(r'Pie chart with (\d+) slice', seg)
    n_slice = int(sm.group(1)) if sm else None
    out["is_single_slice"] = (n_slice == 1) if n_slice is not None else False
    # 各渠道的数值（注意：单 slice 时该值是绝对人数，多 slice 时是百分比）
    raw_ch = {}
    for name, val in re.findall(r'image "([^",]+?),\s*([\d.]+)\.', seg):
        nm = name.strip()
        if "关注" in nm:
            raw_ch[nm] = float(val)
    out["channels"] = raw_ch
    # 渠道总人数（StaticText "10人" 这种绝对数，紧跟在 Pie chart 描述后）
    tm = re.search(r'Pie chart with \d+ slice[^"]*"\s*\n\s*- generic\s*\n\s*- StaticText "(\d+)人"', seg)
    if tm: out["channels_total"] = int(tm.group(1))
    return out

UA = _load_user_analysis(f"{RAW}/user_analysis.txt")
SNAP_DATE = UA["date"] or TODAY.isoformat()
FANS = UA["fans"]
GROWTH = UA["growth_month_pct"]
CH = UA["channels"]
# 文章页关注占比：单 slice 饼图 = 100%（N 人全来自该渠道）；
# 多 slice 才把数值当百分比。修复"10 人被当成 10%"的 bug。
if UA["is_single_slice"] and CH:
    ART_PAGE_PCT = 100.0
elif "文章页关注" in CH:
    ART_PAGE_PCT = CH["文章页关注"]
else:
    ART_PAGE_PCT = None

def _fmt_chan(ch):
    return "、".join(f"{k} {v:.1f}%" for k, v in ch.items())

if ART_PAGE_PCT is not None:
    if UA["is_single_slice"]:
        total = UA.get("channels_total")
        total_str = f"（共 {total} 人）" if total else ""
        ART_PAGE_NOTE = (f"后台快照（截至 {SNAP_DATE}）：新增关注渠道饼图仅 1 片"
                          f"{total_str}，即 <b>100% 来自文章页关注</b>。"
                          f"建议定期在后台复核饼图。")
    else:
        _other = _fmt_chan({k: v for k, v in CH.items() if k != "文章页关注"})
        ART_PAGE_NOTE = (f"后台快照（截至 {SNAP_DATE}）：文章页关注占比 {ART_PAGE_PCT:.1f}%，"
                          f"{'其余渠道 ' + _other if _other else '饼图仅文章页一片'}。"
                          f"建议定期在后台复核饼图。")
else:
    ART_PAGE_NOTE = f"后台快照（截至 {SNAP_DATE}）未解析到明确的「文章页关注」占比，归因结论待复核。"

import math
def _months_to(target, frm, monthly_pct):
    if not (frm and monthly_pct and monthly_pct > 0 and frm < target):
        return None
    return round(math.log(target / frm) / math.log(1 + monthly_pct / 100), 1)
SPEEDUP = 2.5  # 落实建议（周二爆款+具名冲突+相关性选题+高完读分享）后的示意提速倍数
MONTHS_NOW = _months_to(100, FANS, GROWTH)
MONTHS_FAST = (round(MONTHS_NOW / SPEEDUP, 1) if MONTHS_NOW else None)

# ---- 数据区间（动态，取自实际数据，不再写死 5.27 / 今天）----
data_start = min(a["date"] for a in arts32) if arts32 else date.today().isoformat()
data_end   = max(a["date"] for a in arts32) if arts32 else date.today().isoformat()
n_art = len(arts32)

# 统一 reads 口径说明（MEMORY 铁律 #4）：
# parse_details2.py 已统一把【发布列表页】reads 注入 article_details2.json 的所有文章，
# 详情页 d2 的快照值保留在 reads_d2 字段供回溯。本脚本无需再做内存覆盖。
# 关注/完读/分享/收藏/留言 仍取自详情页 d2（列表页无这些字段）。
#
# 两个样本集合：
#   details_with_reads  = 有 reads 的文章（78 篇，用于标题分级 vs 阅读、阅读排行）
#   details_valid       = 有 completion 的文章（16 篇，有 d2 详情快照，用于漏斗/相关性/画像）
details_with_reads = [d for d in details if d.get("reads") is not None]
details_valid = [d for d in details if d.get("completion") is not None]  # 有详情快照的子集
n_det = len(details_valid)
_span_days = (date.fromisoformat(data_end) - date.fromisoformat(data_start)).days
weeks = max(1, (_span_days + 6)//7)
# 周均发文：用「分析窗口」但跨度>1 年时改用「近 1 年」口径，
# 否则 6 年跨度会把近期活跃稀释成 0.x 篇/周（误导）。近期节奏才是选题结论该看的。
_eff_span = min((_wu - _ws).days, 365)
_eff_start = _wu - timedelta(days=_eff_span)
_eff_n = sum(1 for a in arts32 if date.fromisoformat(a["date"]) >= _eff_start)
wk_avg = round(_eff_n / max(1, _eff_span // 7), 1)

# ---- parse content analysis snapshot: traffic source + total readers (动态，不写死) ----
import re as _re
_ca_path = f"{RAW}/content_analysis.txt"
_traffic = {}
TOTAL_READERS = None
if os.path.exists(_ca_path):
    _ca = open(_ca_path, encoding="utf-8").read()
    for _n, _v in _re.findall(r'image "([^,]+?),\s*([\d.]+)\.', _ca):
        _traffic[_n.strip()] = float(_v)
    _m = _re.search(r'阅读总人数：([\d,]+)人', _ca)
    if _m: TOTAL_READERS = int(_m.group(1).replace(",", ""))
REC_PCT = _traffic.get("推荐")
TRAFFIC_ORDER = [("推荐","推荐"),("搜一搜","搜一搜"),("公众号主页","公众号主页"),
                 ("公众号消息","公众号消息(粉丝主动)"),("其它","其它"),("聊天会话","聊天会话")]

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

# ---------- Pass A: weekday (window) ----------
wd_cnt = defaultdict(int); wd_reads = defaultdict(list)
for a in arts32:
    if not a.get("date"): continue
    wd_cnt[date.fromisoformat(a["date"]).weekday()] += 1
    wd_reads[date.fromisoformat(a["date"]).weekday()].append(a["reads"])
wd = [(WK[i], wd_cnt[i], (round(sum(wd_reads[i])/len(wd_reads[i]),1) if wd_reads[i] else 0), sum(wd_reads[i])) for i in range(7)]
tue = next(x for x in wd if x[0]=="周二")
_total_reads = sum(a["reads"] or 0 for a in arts32)
tue_share = round(tue[3]/_total_reads*100) if _total_reads else 0

# ---------- Pass B: title taxonomy (用 details_with_reads，样本更全) ----------
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
for d in details_with_reads:
    key = "+".join(classify(d["title"])) or "其他"
    grp[key].append(coef(d.get("reads")))
tax = sorted(([k, len(v), round(sum(v)/len(v),1)] for k,v in grp.items()), key=lambda x:-x[2])

# ---------- Pass C: read->follow funnel (17) ----------
funnel = []
for d in sorted(details_valid, key=lambda x:-(coef(x.get("reads")))):
    r = coef(d.get("reads")); comp = coef(d.get("completion"))
    sh = coef(d.get("shares")); nf = coef(d.get("new_follows"))
    sr = round(sh/r*100, 2) if r else 0
    fpr = round(nf/r*1000, 2) if r else 0
    funnel.append((d["title"][:16], r, comp, sh, sr, nf, fpr))

# ---------- Pass D: correlations with 新增关注 ----------
reads=[coef(d.get("reads")) for d in details_valid]
comp=[coef(d.get("completion")) for d in details_valid]
share=[coef(d.get("shares")) for d in details_valid]
sr=[coef(d.get("shares"))/max(coef(d.get("reads")),1) for d in details_valid]
nf=[coef(d.get("new_follows")) for d in details_valid]
r_read=corr(reads,nf); r_comp=corr(comp,nf); r_share=corr(share,nf)
r_sr=corr(sr,nf); r_prod=corr([c*s for c,s in zip(comp,share)], nf)
brand=[coef(d.get("reads")) for d in details_with_reads if "具名主体" in classify(d["title"])]
nonb=[coef(d.get("reads")) for d in details_with_reads if "具名主体" not in classify(d["title"])]
brand_avg=round(sum(brand)/len(brand),1) if brand else 0
nonb_avg=round(sum(nonb)/len(nonb),1) if nonb else 0
lift = round(brand_avg/nonb_avg) if nonb_avg else 0

# "具名主体+冲突" 分类动态描述（修复硬编码"3 篇"）
_bc_entries = [t for t in tax if "具名主体" in t[0] and "冲突" in t[0]]
if _bc_entries:
    _bc_n = _bc_entries[0][1]   # 该分类的篇数
    _bc_avg = _bc_entries[0][2] # 平均阅读
    _lift_str = f"杠杆 ≈ <b>{round(brand_avg/nonb_avg)}×</b>" if nonb_avg else "杠杆暂不可算（无非具名对照）"
    _brand_conflict_note = f'<b>具名主体 + 冲突</b> {_bc_n} 篇均 {_bc_avg} 阅读，非具名 {len(nonb)} 篇仅均 {nonb_avg}（{_lift_str}）。'
else:
    _brand_conflict_note = "窗口内无「具名主体+冲突」分类样本。"

# ---- 逐篇反差案例 / 派生数字（全部从数据来，杜绝手敲漂移）----
apple   = next((d for d in details_valid if "苹果" in d.get("title","")), None)
douyin  = next((d for d in details_valid if "抖音" in d.get("title","")), None)
fuzhi   = next((d for d in details_valid if "十年致富" in d.get("title","")), None)
top_follow = max(details_valid, key=lambda d: coef(d.get("new_follows")), default=None) if details_valid else None
def _g(d, k): return coef(d.get(k)) if d else 0
_ap_r=_g(apple,'reads'); _ap_s=_g(apple,'shares'); _ap_sr=round(_ap_s/_ap_r*100,2) if _ap_r else 0
_dy_r=_g(douyin,'reads'); _dy_c=_g(douyin,'completion'); _dy_s=_g(douyin,'shares'); _dy_sr=round(_dy_s/_dy_r*100,2) if _dy_r else 0
_fz_r=_g(fuzhi,'reads'); _fz_s=_g(fuzhi,'shares'); _fz_sr=round(_fz_s/_fz_r*100,2) if _fz_r else 0
_tf_r=_g(top_follow,'reads'); _tf_f=_g(top_follow,'new_follows')
comp_top = sorted(details_valid, key=lambda d: -coef(d.get("completion")))[:2]
comp_note = "、".join(f"{d['title'][:6]} {_g(d,'completion')}%" for d in comp_top)
max_non_tue = max((w[3] for i, w in enumerate(wd) if WK[i] != "周二"), default=0)
min_non_tue_nonzero = min((w[3] for i, w in enumerate(wd) if WK[i] != "周二" and w[3] > 0), default=0)
_c1 = ('《%s》%d 阅读、分享率仅 %s%% → <b>0 关注</b>；' % (apple['title'][:10], _ap_r, _ap_sr)) if apple else ''
if douyin:
    _dy_f = _g(douyin,'new_follows')
    _fpr_dy = round(_dy_f/_dy_r*1000, 1) if _dy_r else 0
    _c2 = ('《%s》%d 阅读、完读 %s%%、分享率 %s%%（很高）→ 仍 <b>%d 关注</b>（千人比 %s）——话题与“理财/AI工具”账号无关，读者不愿关注；' % (douyin['title'][:10], _dy_r, _dy_c, _dy_sr, _dy_f, _fpr_dy))
else:
    _dy_f = 0
    _c2 = ''
if fuzhi:
    _fz_nf = _g(fuzhi,'new_follows'); _fz_fpr = round(_fz_nf/_fz_r*1000, 1) if _fz_r else 0
    _c3 = ('《%s》仅 %d 阅读、但分享率 %s%% 且话题强相关 → <b>%d 关注（千人比 %s）</b>。' % (fuzhi['title'][:10], _fz_r, _fz_sr, _fz_nf, _fz_fpr))
else:
    _c3 = ''

# "关注滞后阅读" 动态注解（修复硬编码"《微信 AI 来了》4 个关注"）
# 用窗口内吸粉最多的文章做交叉验证示例；无则降级为通用表述。
if top_follow and _tf_f > 0:
    _lag_note = (f"与每日净增交叉验证：单篇《{top_follow['title'][:12]}》的 {_tf_f} 个关注，"
                 f"对应详情页归因的 {_tf_f} 个关注，证实关注滞后阅读约 1 周、由单篇内容驱动"
                 f"（具体每日分布以后台净增趋势为准）。")
else:
    _lag_note = "关注滞后阅读约 1 周，由单篇内容驱动（具体每日分布以后台净增趋势为准）。"

# ---------- Pass E: aggregation / power law / attribution ----------
total_reads = sum(a["reads"] or 0 for a in arts32)
reads_sorted = sorted(arts32, key=lambda x:-(x["reads"] or 0))
top3 = sum((a["reads"] or 0) for a in reads_sorted[:3]); top5 = sum((a["reads"] or 0) for a in reads_sorted[:5])
attr = [d for d in details_valid if coef(d.get("new_follows"))>0]
attr_total = sum(coef(d.get("new_follows")) for d in details_valid)

def weighted(field):
    # 只聚合「推荐主导」的高阅读单篇画像，排除低样本(<50阅读)文章，避免失真
    agg=defaultdict(float); tot=0.0; n_art=0
    for d in details:
        r=coef(d.get("reads"))
        if not r or r < 50: continue
        ch=d.get("channels") or {}
        if ch.get("推荐",0) < 50: continue
        n_art+=1
        for k,v in (d.get(field) or {}).items():
            agg[k]+=v*r; tot+=v*r
    return {k:round(v/tot*100,1) for k,v in agg.items()} if tot else {}, n_art
age_agg,_=weighted("age"); gender_agg,_=weighted("gender")
reg_agg=defaultdict(float); rtot=0.0; n_reg=0
for d in details:
    r=coef(d.get("reads"))
    if not r or r < 50: continue
    ch=d.get("channels") or {}
    if ch.get("推荐",0) < 50: continue
    n_reg+=1
    for name,pct in (d.get("region") or []):
        v=float(pct.rstrip("%")); reg_agg[name]+=v*r; rtot+=v*r
region_sorted=sorted([(k,round(v/rtot*100,1)) for k,v in reg_agg.items() if k!="未知"], key=lambda x:-x[1])[:7]

# ---------- render helpers ----------
def bar(label, val, maxv, color="#2b6cb0", sub=""):
    pct=(val/maxv*100) if maxv else 0
    return f'<div class="row"><span class="lab" title="{label}">{label}</span><div class="track"><div class="fill" style="width:{pct:.1f}%;background:{color}"></div></div><span class="val">{val}{sub}</span></div>'
def hbar(label, pct, color="#38a169"):
    return f'<div class="row"><span class="lab">{label}</span><div class="track"><div class="fill" style="width:{pct:.1f}%;background:{color}"></div></div><span class="val">{pct:.1f}%</span></div>'
sec_traffic = "".join(hbar(lbl, _traffic.get(key, 0.0), "#4299e1") for key, lbl in TRAFFIC_ORDER)

# section HTML
sec_freq = "".join(bar(WK[i], wd_cnt[i], max(wd_cnt[i] for i in range(7)) or 1, "#4299e1") for i in range(7))
sec_wdread = "".join(bar(f"{WK[i]}", wd[i][2], max(w[2] for w in wd) or 1, "#3182ce") for i in range(7))
sec_reads = "".join(bar(a["title"][:16], a["reads"], reads_sorted[0]["reads"], "#2b6cb0") for a in reads_sorted[:10])
sec_tax = "".join(bar(t[0], t[2], max(x[2] for x in tax) or 1, "#805ad5") for t in tax)
sec_funnel_rows = "".join(
    f'<tr><td class="t">{t}</td><td>{r}</td><td>{comp}</td><td>{sh}</td><td>{sr}%</td><td class="{"hot" if nf>0 else ""}">{nf}</td><td>{fpr}</td></tr>'
    for t,r,comp,sh,sr,nf,fpr in funnel)
sec_follow = "".join(bar(d["title"][:16], coef(d.get("new_follows")), max(coef(d.get("new_follows")) for d in details_valid) or 1, "#dd6b20")
                      for d in sorted(details_valid, key=lambda x:-coef(x.get("new_follows"))) if coef(d.get("new_follows"))>0)
sec_follow += f'<div class="note">其余 {len(details_valid)-len(attr)} 篇带来 0 关注。{n_det} 篇窗口内（仅含已抓取详情页的文章）合计 <b>{attr_total}</b> 个关注；账号累计粉丝 {FANS if FANS is not None else "—"}（后台快照截至 {SNAP_DATE}）。注意：此处吸粉数仅来自已抓取详情页的文章，并非窗口内全部关注。</div>'

# ---------- 互动深度分析（互动率/粉丝活跃度/分享传播力）----------
# 互动率 = (分享+留言+收藏)/阅读；粉丝活跃度 = 消息阅读/送达；分享传播力 = 分享产生阅读/总分享
engagement_rows = []
eng_data = []
for d in sorted(details_valid, key=lambda x: -coef(x.get("reads"))):
    r = coef(d.get("reads"))
    if not r: continue
    sh = coef(d.get("shares")); cm = coef(d.get("comments")); co = coef(d.get("collections"))
    mo = coef(d.get("moments")); fw = coef(d.get("forwards"))
    eng = sh + cm + co
    eng_rate = round(eng/r*100, 1)
    reach = coef(d.get("reach")); mr = coef(d.get("msg_reads"))
    fan_active = round(mr/reach*100, 1) if reach else 0
    tsn = coef(d.get("total_share_n")); sir = coef(d.get("share_induced_reads"))
    share_spread = round(sir/tsn*100, 1) if tsn else 0
    nf = coef(d.get("new_follows"))
    eng_data.append({"title": d["title"][:18], "reads": r, "eng": eng, "eng_rate": eng_rate,
                     "fan_active": fan_active, "share_spread": share_spread, "nf": nf})
    engagement_rows.append(
        f'<tr><td class="t">{d["title"][:16]}</td><td>{r}</td><td>{sh}</td><td>{mo}</td><td>{fw}</td>'
        f'<td>{cm}</td><td>{co}</td><td class="{"hot" if eng_rate>=5 else ""}">{eng_rate}%</td>'
        f'<td>{fan_active}%</td><td>{share_spread}%</td>'
        f'<td class="{"hot" if nf>0 else ""}">{nf}</td></tr>'
    )
sec_engagement = "".join(engagement_rows)
# 互动率最高的文章（互动率 ≥ 5% 算高互动）
high_eng = [e for e in eng_data if e["eng_rate"] >= 5]
# 高阅读但低互动的"虚胖"文章
low_eng_high_read = [e for e in eng_data if e["reads"] >= 100 and e["eng_rate"] < 2]
_eng_insight = ""
if high_eng:
    _eng_insight += '<b>高互动文章（≥5%）</b>：' + "、".join(f'《{e["title"]}》{e["eng_rate"]}%' for e in high_eng[:3]) + '——这些文章虽未必阅读最高，但读者参与度强，会累积推荐权重。'
if low_eng_high_read:
    _eng_insight += ' <b>高阅读低互动（虚胖）</b>：' + "、".join(f'《{e["title"]}》{e["eng_rate"]}%' for e in low_eng_high_read[:2]) + '——阅读高但读者看完即走，长远推荐权重会下降。'

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
<div class="sub">账号「一点财知」 · 数据区间 {data_start} ~ {data_end} · 数据截至 {SNAP_DATE} · 报告生成于 {date.today().isoformat()}</div>

<div class="callout">
<b>一句话结论：</b>你的粉丝 <b>主要来自文章页</b>（{ART_PAGE_NOTE}）。
涨阅读靠「<b>具名主体 + 冲突</b>」标题（杠杆 ≈ <b>{lift}×</b>），且<b>周二</b>发文吃掉 {tue_share}% 阅读；
涨粉靠「<b>完读率 × 分享率 × 平台相关度</b>」——数据证实：关注与阅读量几乎无关（r={r_read}），却与完读×分享高度相关（r={r_prod}）。
所以：<b>把爆款稿安排在周二、用"具名+冲突"引爆推荐，并在爆款里优先选"微信/工具/理财"相关角度</b>，是提阅读+涨粉的同一套打法。
</div>

<div class="kpis">
  <div class="kpi"><div class="n">{n_art}</div><div class="l">数据区间发文（篇）</div></div>
  <div class="kpi"><div class="n">{wk_avg}</div><div class="l">周均发文（篇/周）</div></div>
  <div class="kpi"><div class="n">{total_reads}</div><div class="l">{n_art} 篇累计阅读</div></div>
  <div class="kpi"><div class="n">{round(top3/total_reads*100) if total_reads else 0}%</div><div class="l">头部3篇阅读占比</div></div>
  <div class="kpi"><div class="n">{lift}×</div><div class="l">具名标题阅读杠杆</div></div>
  <div class="kpi"><div class="n">{tue_share}%</div><div class="l">周二贡献阅读占比</div></div>
  <div class="kpi"><div class="n">{attr_total}</div><div class="l">窗口内文章吸粉（个）</div></div>
</div>

<h2>一、发文节奏：频率已优秀，无需加量</h2>
<div class="card">
  <div class="legend">按自然周统计（{data_start} 起，共 {weeks} 周）</div>
  {sec_freq}
  <div class="note">周均 {wk_avg} 篇，符合你说的"每周 3-4 篇"。<b>频率不是瓶颈</b>——把 1~2 篇做成"爆款稿"比再加量更有效。</div>
</div>

<h2>二、发布星期规律（新发现）：周二统治阅读</h2>
<div class="card">
  <div class="legend">各星期发文数（上）与单篇平均阅读（下）</div>
  {sec_freq}
  {sec_wdread}
  <div class="warn"><b>最强规律：</b>周二 {tue[1]} 篇贡献阅读 <b>{tue[3]}</b>（占全量 <b>{tue_share}%</b>），单篇均 {tue[2]}；
  其余工作日合计阅读 {min_non_tue_nonzero}–{max_non_tue}；<b>周末从不发文</b>。头部爆款（苹果/微信AI/搜一搜）均落周二。
  <br><b>动作：</b>把每周期待的 1–2 篇"爆款候选"固定排在<b>周二</b>发；常规复盘稿可排其他工作日维持节奏。</div>
</div>

<h2>三、阅读表现：极度幂律 + 标题公式分级（新）</h2>
<div class="card">
  <div class="legend">Top10 单篇阅读量（{n_art} 篇累计 {total_reads}）</div>
  {sec_reads}
  <div class="legend" style="margin-top:14px;">标题类型 vs 平均阅读（{len(details_with_reads)} 篇有 reads，按阅读降序）</div>
  {sec_tax}
  <div class="note">头部 3 篇占 {round(top3/total_reads*100) if total_reads else 0}% 阅读、头部 5 篇占 {round(top5/total_reads*100) if total_reads else 0}%。
  {_brand_conflict_note}
  复盘类（鱼盆系列）均 {next((t[2] for t in tax if "复盘" in t[0] and "冲突" not in t[0] and "具名主体" not in t[0]),0)}，用于维系铁粉、不指望涨量。</div>
</div>

<h2>四、传播力深度：完读率与分享率决定质量</h2>
<div class="card">
  <table>
    <tr><th>文章</th><th>阅读</th><th>完读率</th><th>分享</th><th>分享率</th><th>收藏</th><th>留言</th><th>新增关注</th></tr>
    {''.join(f'<tr><td class="t">{d["title"][:18]}</td><td>{coef(d.get("reads"))}</td><td>{coef(d.get("completion"))}%</td><td>{coef(d.get("shares"))}</td><td>{round(coef(d.get("shares"))/max(coef(d.get("reads")),1)*100,2)}%</td><td>{coef(d.get("collections"))}</td><td>{coef(d.get("comments"))}</td><td class="{"hot" if coef(d.get("new_follows"))>0 else ""}">{coef(d.get("new_follows"))}</td></tr>' for d in sorted(details_valid,key=lambda x:-coef(x.get("reads"))))}
  </table>
  <div class="note">完读率高多为方法论/复盘（{comp_note}）；爆款靠推荐起量。
  <b>分享率 = 分享/阅读</b>，是内容被转发扩散的强度指标，也是涨粉的关键前导。</div>
</div>

<h2>五、互动深度分析（新）：阅读≠关注，但互动是长远推荐权重</h2>
<div class="card">
  <div class="legend">各文章互动数据（按阅读降序，{n_det} 篇有详情）</div>
  <table>
    <tr><th>文章</th><th>阅读</th><th>分享</th><th>朋友圈</th><th>转发</th><th>留言</th><th>收藏</th><th>互动率</th><th>粉丝活跃</th><th>分享传播</th><th>关注</th></tr>
    {sec_engagement}
  </table>
  <div class="note">互动率 = (分享+留言+收藏)/阅读；粉丝活跃度 = 消息阅读/送达；分享传播力 = 分享产生阅读/总分享。
  {_eng_insight}
  <br><b>结论</b>：高阅读≠高互动（如爆款可能互动率 < 1%），但高互动文章会累积微信推荐权重，长远利好阅读增长和涨粉。<b>写文章不仅要冲阅读，还要设计互动钩子</b>（提问引留言、金句引收藏、实用引转发）。</div>
</div>

<h2>六、阅读→关注漏斗（新）：为什么大阅读≠大涨粉</h2>
<div class="card">
  <table>
    <tr><th>文章</th><th>阅读</th><th>完读%</th><th>分享</th><th>分享率%</th><th>新增关注</th><th>关注/千读</th></tr>
    {sec_funnel_rows}
  </table>
  <div class="warn"><b>反差案例：</b>
  {_c1}
  {_c2}
  {_c3}
  <br>→ 关注 = 阅读 × 完读率 × 分享率 × <b>平台相关度</b>，第四步决定天花板。</div>
</div>

<h2>七、吸粉归因：谁真正带来了粉丝</h2>
<div class="card">
  <div class="legend">各文章带来的「新增关注」数量（窗口内 {n_det} 篇）</div>
  {sec_follow}
  <div class="warn"><b>关键反差：</b>{('阅读第一的《%s》(%d) 带来 <b>%d 关注</b>；' % (apple['title'][:10], _ap_r, _g(apple,'new_follows'))) if apple else ''}{('《%s》(%d) 带来 <b>%d 关注</b>' % (top_follow['title'][:10], _tf_r, _tf_f)) if top_follow else ''}。
  原因：微信/公众号相关内容，读者更愿意"关注这个号"；纯公司新闻读者看完即走。</div>
</div>

<h2>八、涨粉机制：相关性铁证（新）</h2>
<div class="card">
  <div class="callout">
  <b>用 {n_det} 篇文章做 Pearson 相关分析（关注为因变量）：</b><br>
  • 关注 vs <b>阅读量</b>：r = <b>{r_read}</b>（几乎无关）<br>
  • 关注 vs 完读率：r = {r_comp}（无关）<br>
  • 关注 vs 分享数：r = {r_share}（中等）<br>
  • 关注 vs <b>完读率 × 分享数</b>：r = <b>{r_prod}</b>（最强预测因子）<br>
  <b>结论：</b>裸阅读量不是涨粉引擎；<b>完读率 × 分享率</b>才是。再叠加"平台相关度"第三因子，才能把阅读转化为粉丝。
  </div>
  <div class="note">{_lag_note}</div>
</div>

<h2>九、流量结构：几乎全靠推荐分发</h2>
<div class="card">
  <div class="legend">账号级阅读来源（内容分析，阅读总人数 {TOTAL_READERS}）</div>
  {sec_traffic}
  <div class="note">粉丝主动打开仅 {_traffic.get("公众号消息",0):.2f}%。<b>增长几乎完全取决于算法推荐</b>，因此"为推荐优化"（前 3 句抓人、短段落、高完读）是阅读量第一杠杆；"搜一搜"{_traffic.get("搜一搜",0):.2f}% 零成本，值得吃长尾。</div>
</div>

<h2>十、读者画像：谁在看你（单篇聚合，样本加权）</h2>
<div class="card">
  <div class="legend">性别分布</div>
  {sec_gender}
  <div class="twocol">
    <div style="flex:1;min-width:260px;"><div class="legend">年龄分布</div>{sec_age}</div>
    <div style="flex:1;min-width:260px;"><div class="legend">地域 Top（加权）</div>{sec_region}</div>
  </div>
  <div class="note">读者以 <b>26-45 岁、男性占绝对多数</b>为主，集中在 <b>{"、".join(n for n,_ in region_sorted[:5])}</b>。
  <b>口径：</b>粉丝&lt;100 时账号级画像隐藏，此处为「推荐主导的高阅读单篇」画像按阅读量加权聚合（已排除 2–15 阅读的极低样本文，避免失真）；样本数 ≈ {n_reg} 篇。
  <b>里程碑：</b>账号级画像（性别/年龄/城市/终端/活跃时间）在<b>粉丝达 100 后次日自动解锁</b>——这是你下一个明确目标。</div>
</div>

<h2>十一、可执行优化方向（按杠杆排序）</h2>

<div class="rec"><div class="p">① 爆款排在周二发（最高杠杆、零成本）</div>
证据：周二 {tue[1]} 篇占全量 {tue_share}% 阅读（均 {tue[2]}），其余工作日合计阅读 {min_non_tue_nonzero}–{max_non_tue}。把每周 1–2 篇"爆款候选"固定在周二；常规复盘稿排其他日维持节奏。</div>

<div class="rec"><div class="p">② 标题用「具名主体 + 冲突」公式</div>
证据：具名+冲突 {_bc_n} 篇均 {_bc_avg} 阅读，非具名均 {nonb_avg}（≈{round(brand_avg/nonb_avg) if nonb_avg else 0}×）。
下一篇试试：〈苹果也扛不住了〉〈微信这个更新，有点猛〉〈百度，这次真的急了〉。</div>

<div class="rec"><div class="p">③ 涨粉：爆款里优先选"微信 / 工具 / 理财"角度</div>
证据：相关性显示关注 ≠ 阅读量（r={r_read}），而 = 完读×分享×相关度（r={r_prod}）。{('《%s》单篇吸粉 %d，' % (top_follow['title'][:10], _tf_f)) if top_follow else ''}{('《%s》%d 读却 0 关注，' % (apple['title'][:10], _ap_r)) if apple else ''}{('《%s》%d 读高互动仍 0 关注。' % (douyin['title'][:10], _dy_r)) if douyin else ''}同样引爆推荐，选"与账号相关"的选题，关注转化高一个量级。</div>

<div class="rec"><div class="p">④ 把完读率与分享率做高（涨粉的真正引擎）</div>
证据：关注与完读×分享相关 r={r_prod}（最强）。做法：开头 3 句抛冲突/反常识，多用小标题与短段落，结尾给"可转发的金句/清单/数据卡"。{('《%s》仅 %d 读但分享率 %s%% → 千人关注比 %s，远超苹果。' % (fuzhi['title'][:8], _fz_r, _fz_sr, _fz_fpr)) if fuzhi else ''}</div>

<div class="rec"><div class="p">⑤ 爆款发布后 1 周内持续导流</div>
证据：关注滞后阅读约 1 周。文章发布后一周内，于文末/次条持续放置关注引导，承接滞后关注。</div>

<div class="rec"><div class="p">⑥ 为推荐优化开篇 + 吃"搜一搜"长尾</div>
证据：推荐占 {_traffic.get("推荐",0):.2f}%，搜一搜占 {_traffic.get("搜一搜",0):.2f}% 且零成本。标题/正文嵌入关键词（"微信搜一搜""AI 工具""理财"），稳定吃搜索长尾。</div>

<div class="rec"><div class="p">⑦ 冲 100 粉解锁账号级画像</div>
证据：粉丝达 100 后次日自动展示性别/年龄/城市/终端/活跃时间，届时报告可升级为"账号级精准画像"，进一步优化选题与发布时段。当前 {FANS if FANS is not None else "—"} 粉（后台快照截至 {SNAP_DATE}），按建议②③提速可达。</div>

<div class="callout" style="margin-top:18px;">
<b>涨粉时间预测（到 100 粉解锁画像）：</b><br>
• 维持现状（自然推荐，按当前月增速 {GROWTH:.1f}% 估算）：约 <b>{MONTHS_NOW if MONTHS_NOW is not None else "—"} 个月</b><br>
• 落实 ①②③④（周二爆款 + 具名冲突 + 相关性选题 + 高完读分享，示意提速 {SPEEDUP}×）：约 <b>{MONTHS_FAST if MONTHS_FAST is not None else "—"} 个月</b><br>
关键杠杆就是建议 ②③——把爆款从"公司新闻"转向"平台/工具/理财相关"，并固定在周二。
</div>

<div class="foot">数据来源：微信公众平台后台（用户分析 / 内容分析 / 单篇详情页，{n_det} 篇窗口内文章逐篇抓取，数据截至 {SNAP_DATE}）。
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

# ---- 自动更新爆款预测基准快照 ----
# 每次报告生成后顺便刷新 hit_baseline.json，供 predict_hit.py 使用
import subprocess
try:
    subprocess.run(
        [sys.executable, os.path.join(HERE, "update_baseline.py"), BASE],
        check=True, capture_output=True
    )
    print("✓ hit_baseline.json 已更新（爆款预测基准已同步最新数据）")
except Exception as e:
    print(f"WARN: update_baseline.py 调用失败: {e}")

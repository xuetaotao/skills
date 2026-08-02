# -*- coding: utf-8 -*-
"""从最新抓取的数据生成「爆款预测基准快照」data/processed/hit_baseline.json。

每次数据复盘后由 generate_final2.py 自动调用，也可单独跑：
  python update_baseline.py [WORKSPACE_DIR]

基准快照是 predict_hit.py 的数据源，包含：
  - 标题公式规律（具名+冲突杠杆）
  - 发布星期规律（周二优势）
  - 涨粉机制（相关性阈值）
  - 流量来源结构
  - 平台相关度关键词 + 正反案例
  - 读者画像
  - 粉丝状态
"""
import json, os, re, sys
from datetime import date, timedelta
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE
for _ in range(6):
    if os.path.exists(os.path.join(ROOT, "data")) or os.path.exists(os.path.join(ROOT, ".workbuddy")):
        break
    ROOT = os.path.dirname(ROOT)
BASE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("WXPUB_DIR", ROOT)
DATA = os.path.join(BASE, "data", "processed")
RAW  = os.path.join(BASE, "data", "raw")

# ---- 加载数据 ----
details = json.load(open(f"{DATA}/article_details2.json", encoding="utf-8"))
arts = json.load(open(f"{DATA}/recent_articles.json", encoding="utf-8"))
details_with_reads = [d for d in details if d.get("reads") is not None]
details_full = [d for d in details if d.get("completion") is not None]  # 有 d2 详情快照

def coef(x): return x if x is not None else 0

# ---- 1. 标题公式 ----
BRANDS = ["苹果","微信","百度","抖音","Claude","中国银行","腾讯","阿里","微软","谷歌","OpenAI","Meta","字节"]
CONFLICT = ["也","越来越","不再","扛不住","归零","彻底","第一次","终于","崩","逆袭","爆发","凉了","慌了","醒悟","治好","寄给"]
def classify(t):
    tags=[]
    if any(b in t for b in BRANDS): tags.append("具名主体")
    if any(c in t for c in CONFLICT): tags.append("冲突")
    if "？" in t or "?" in t: tags.append("问号")
    if "复盘" in t or "周度" in t: tags.append("复盘")
    return tags

brand_reads = [coef(d.get("reads")) for d in details_with_reads if "具名主体" in classify(d["title"])]
nonb_reads  = [coef(d.get("reads")) for d in details_with_reads if "具名主体" not in classify(d["title"])]
brand_avg = round(sum(brand_reads)/len(brand_reads),1) if brand_reads else 0
nonb_avg  = round(sum(nonb_reads)/len(nonb_reads),1) if nonb_reads else 0

# 具名+冲突 样本（爆款候选参考）
brand_conflict_samples = []
for d in details_with_reads:
    tags = classify(d["title"])
    if "具名主体" in tags and "冲突" in tags:
        brand_conflict_samples.append({
            "title": d["title"][:30], "reads": coef(d.get("reads")),
            "new_follows": coef(d.get("new_follows")), "shares": coef(d.get("shares"))
        })
brand_conflict_samples.sort(key=lambda x: -x["reads"])

# ---- 2. 星期规律 ----
WK = ["周一","周二","周三","周四","周五","周六","周日"]
wd_cnt = defaultdict(int); wd_reads = defaultdict(list)
for a in arts:
    if not a.get("date"): continue
    wd = date.fromisoformat(a["date"]).weekday()
    wd_cnt[wd] += 1
    wd_reads[wd].append(a.get("reads") or 0)
tue = next(i for i, w in enumerate(WK) if w == "周二")
total_reads = sum(a["reads"] or 0 for a in arts)
tue_share = round(wd_reads[tue] and sum(wd_reads[tue])/total_reads*100) if total_reads else 0
other_totals = [sum(wd_reads[i]) for i in range(7) if i != tue and wd_reads[i]]
other_range = [min(other_totals), max(other_totals)] if other_totals else [0, 0]

# ---- 3. 涨粉机制（Pearson 相关）----
def corr(xs, ys):
    n = len(xs)
    if n < 3: return 0.0
    mx, my = sum(xs)/n, sum(ys)/n
    num = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    dx = sum((x-mx)**2 for x in xs)**0.5
    dy = sum((y-my)**2 for y in ys)**0.5
    return round(num/(dx*dy), 2) if dx and dy else 0.0

reads = [coef(d.get("reads")) for d in details_full]
comp  = [coef(d.get("completion")) for d in details_full]
share = [coef(d.get("shares")) for d in details_full]
nf    = [coef(d.get("new_follows")) for d in details_full]

# ---- 4. 平台相关度（正反案例）----
# 吸粉多的文章 = 高相关度；高阅读 0 关注 = 低相关度
follow_samples = sorted(details_full, key=lambda d: -coef(d.get("new_follows")))[:5]
zero_follow_high_read = sorted(
    [d for d in details_full if coef(d.get("new_follows")) == 0 and coef(d.get("reads")) >= 30],
    key=lambda d: -coef(d.get("reads"))
)[:5]

# 从吸粉文章标题提取高频词，作为"高相关度话题"线索
# 对齐账号定位：科技 / 商业 / 金融（用户 2026-07-19 明确）
HIGH_FOLLOW_TOPICS = ["科技", "商业", "金融", "理财", "投资", "基金", "股票", "财经",
                      "AI", "人工智能", "微信", "工具", "互联网", "技术", "经济",
                      "省钱", "技巧", "方法", "搜一搜", "App", "银行"]

# ---- 5. 流量来源（从 content_analysis.txt）----
_traffic = {}
TOTAL_READERS = None
_ca_path = f"{RAW}/content_analysis.txt"
if os.path.exists(_ca_path):
    _ca = open(_ca_path, encoding="utf-8").read()
    for _n, _v in re.findall(r'image "([^,]+?),\s*([\d.]+)\.', _ca):
        _traffic[_n.strip()] = float(_v)
    _m = re.search(r'阅读总人数：([\d,]+)人', _ca)
    if _m: TOTAL_READERS = int(_m.group(1).replace(",", ""))

# ---- 6. 读者画像（加权聚合）----
def weighted(field):
    agg = defaultdict(float); tot = 0.0; n = 0
    for d in details:
        r = coef(d.get("reads"))
        if not r or r < 50: continue
        ch = d.get("channels") or {}
        if ch.get("推荐", 0) < 50: continue
        n += 1
        for k, v in (d.get(field) or {}).items():
            agg[k] += v*r; tot += v*r
    return {k: round(v/tot*100, 1) for k, v in agg.items()} if tot else {}, n

age_agg, n_age = weighted("age")
gender_agg, n_gender = weighted("gender")

# ---- 7. 粉丝状态（从 user_analysis.txt）----
fans = None; growth_month = None
_ua_path = f"{RAW}/user_analysis.txt"
if os.path.exists(_ua_path):
    _ua = open(_ua_path, encoding="utf-8").read()
    m = re.search(r'累计关注人数"\s*\n\s*- StaticText "(\d+)"', _ua)
    if m: fans = int(m.group(1))
    mg = re.search(r'累计关注人数".*?StaticText "月"\s*\n\s*- StaticText "([\d.]+)%"', _ua, re.S)
    if mg: growth_month = float(mg.group(1))

import math
def months_to(target, frm, pct):
    if not (frm and pct and pct > 0 and frm < target): return None
    return round(math.log(target / frm) / math.log(1 + pct / 100), 1)
months_100 = months_to(100, fans, growth_month) if fans and growth_month else None

# ---- 7.5 互动深度基准 ----
eng_data = []
for d in details_full:
    r = coef(d.get("reads"))
    if not r: continue
    sh = coef(d.get("shares")); cm = coef(d.get("comments")); co = coef(d.get("collections"))
    eng = sh + cm + co
    eng_rate = round(eng/r*100, 1)
    reach = coef(d.get("reach")); mr = coef(d.get("msg_reads"))
    fan_active = round(mr/reach*100, 1) if reach else 0
    tsn = coef(d.get("total_share_n")); sir = coef(d.get("share_induced_reads"))
    share_spread = round(sir/tsn*100, 1) if tsn else 0
    eng_data.append({"title": d["title"][:20], "reads": r, "eng_rate": eng_rate,
                     "fan_active": fan_active, "share_spread": share_spread,
                     "new_follows": coef(d.get("new_follows"))})

avg_eng_rate = round(sum(e["eng_rate"] for e in eng_data)/len(eng_data), 1) if eng_data else 0
avg_fan_active = round(sum(e["fan_active"] for e in eng_data)/len(eng_data), 1) if eng_data else 0
# 互动率与关注转化的关系：高互动文章是否涨粉更好？
high_eng_follows = sum(e["new_follows"] for e in eng_data if e["eng_rate"] >= 5)
low_eng_follows = sum(e["new_follows"] for e in eng_data if e["eng_rate"] < 5)

# ---- 7.6 有效角度模式（从历史数据学"角度规律"，不学"话题"）----
# 关键设计：话题开放（任何新热点都能套），角度从历史数据学（什么结构/切口有效）
ANGLE_MARKERS = [
    ("方法论/科普体", ["一文看懂", "如何", "方法", "技巧", "指南", "体系", "入门", "科普", "原理"]),
    ("复盘体",       ["复盘", "周度", "总结", "回顾", "这件事", "这一周"]),
    ("对比/选择体",  [" vs ", "还是", "该选", "怎么选", "和", "对比", "区别"]),
    ("清单/数字体",  ["3个", "三个", "5个", "几个", "清单", "步骤", "件事", "动作"]),
    ("冲突/风险体",  ["撕下", "归零", "扛不住", "崩", "慌了", "危险", "陷阱", "别再", "误区"]),
    ("机会/判断体",  ["机会", "值得", "该不该", "到底", "真正", "信号", "趋势", "下一步"]),
    ("平台生态体",   ["来了", "更新", "发布", "上线", "改版", "接入", "开放"]),
    ("决策框架体",   ["判断", "框架", "标准", "怎么算", "该不该", "值不值"]),
]

def detect_angles(title):
    tags = []
    t = title.lower()
    for angle_name, markers in ANGLE_MARKERS:
        if any(m.lower() in t for m in markers):
            tags.append(angle_name)
    return tags or ["普通"]

# 统计每种角度的平均互动率/完读率/关注转化
angle_stats = defaultdict(lambda: {"n":0, "eng_rates":[], "completions":[], "follow_conv":[], "titles":[]})
for d in details_full:
    r = coef(d.get("reads"))
    if not r: continue
    sh = coef(d.get("shares")); cm = coef(d.get("comments")); co = coef(d.get("collections"))
    nf_one = coef(d.get("new_follows")); comp_one = coef(d.get("completion"))
    eng_rate = round((sh+cm+co)/r*100, 1)
    follow_conv = round(nf_one/r*100, 2)
    for angle in detect_angles(d["title"]):
        s = angle_stats[angle]
        s["n"] += 1
        s["eng_rates"].append(eng_rate)
        s["completions"].append(comp_one)
        s["follow_conv"].append(follow_conv)
        s["titles"].append(d["title"][:24])

# 挑出表现好的角度（互动率或关注转化高于平均）
effective_angles = []
for angle, s in angle_stats.items():
    if s["n"] == 0: continue
    avg_eng = round(sum(s["eng_rates"])/s["n"], 1)
    avg_comp = round(sum(s["completions"])/s["n"], 1)
    avg_fc = round(sum(s["follow_conv"])/s["n"], 2)
    # 角度有效性信号：互动率>=5 或 关注转化>=0.5 或 完读>=40
    effective = avg_eng >= 5 or avg_fc >= 0.5 or avg_comp >= 40
    effective_angles.append({
        "angle": angle,
        "n": s["n"],
        "avg_engagement_rate": avg_eng,
        "avg_completion": avg_comp,
        "avg_follow_conv_pct": avg_fc,
        "effective": effective,
        "example_titles": s["titles"][:3],
    })
effective_angles.sort(key=lambda x: -(x["avg_engagement_rate"] + x["avg_follow_conv_pct"]*2 + x["avg_completion"]/5))

# 零关注高阅读的"虚胖"模式（避坑）
zero_follow_patterns = []
for d in details_full:
    r = coef(d.get("reads")); nf_zf = coef(d.get("new_follows"))
    if r >= 30 and nf_zf == 0:
        zero_follow_patterns.append({
            "title": d["title"][:30], "reads": r,
            "angles": detect_angles(d["title"]),
            "warning": "高阅读0关注，话题与账号定位无关或停留在公司新闻层面",
        })

# ---- 8. 读者地域 Top ----
reg_agg = defaultdict(float); rtot = 0.0
for d in details:
    r = coef(d.get("reads"))
    if not r or r < 50: continue
    ch = d.get("channels") or {}
    if ch.get("推荐", 0) < 50: continue
    for name, pct in (d.get("region") or []):
        v = float(pct.rstrip("%")); reg_agg[name] += v*r; rtot += v*r
region_top = sorted([(k, round(v/rtot*100, 1)) for k, v in reg_agg.items() if k != "未知"],
                    key=lambda x: -x[1])[:5] if rtot else []

# ---- 输出基准快照 ----
baseline = {
    "generated_at": date.today().isoformat(),
    "data_window": {
        "start": arts[0]["date"] if arts else None,
        "end": arts[-1]["date"] if arts else None,
        "n_articles": len(arts),
        "n_with_detail": len(details_full),
    },
    "title_formula": {
        "brand_keywords": BRANDS,
        "conflict_keywords": CONFLICT,
        "brand_avg_reads": brand_avg,
        "nonb_avg_reads": nonb_avg,
        "lift": round(brand_avg/nonb_avg) if nonb_avg else 0,
        "brand_conflict_samples": brand_conflict_samples[:5],
    },
    "weekday_pattern": {
        "tue_share_pct": tue_share,
        "tue_n": wd_cnt[tue],
        "tue_avg_reads": round(sum(wd_reads[tue])/len(wd_reads[tue]), 1) if wd_reads[tue] else 0,
        "tue_total_reads": sum(wd_reads[tue]),
        "other_weekday_range": other_range,
        "weekend_total_reads": sum(wd_reads[5]) + sum(wd_reads[6]),
    },
    "follow_mechanism": {
        "r_read_vs_follow": corr(reads, nf),
        "r_completion_vs_follow": corr(comp, nf),
        "r_share_vs_follow": corr(share, nf),
        "r_completion_x_share_vs_follow": corr([c*s for c, s in zip(comp, share)], nf),
        "n_sample": len(details_full),
        "interpretation": "关注与阅读量几乎无关(r_read低)，与完读×分享高度相关(r_prod高)。即：裸阅读量不涨粉，完读率×分享率才是涨粉引擎。",
    },
    "traffic": {
        "recommend_pct": _traffic.get("推荐", 0),
        "s1s_pct": _traffic.get("搜一搜", 0),
        "msg_pct": _traffic.get("公众号消息", 0),
        "total_readers": TOTAL_READERS,
    },
    "platform_relevance": {
        "high_follow_topics": HIGH_FOLLOW_TOPICS,
        "account_positioning": {
            "main": ["科技", "商业", "金融"],
            "description": "账号核心定位：围绕科技/商业/金融产出优质内容",
            "occasional_rule": "偶尔极少数写社会现象类，但必须与定位相关（如苹果AI账单=科技+商业）",
            "related_topics": HIGH_FOLLOW_TOPICS,
            "deviation_impact": "频繁偏离定位会稀释账号认知，影响长期推荐权重和粉丝转化",
        },
        "high_follow_samples": [
            {"title": d["title"][:30], "reads": coef(d.get("reads")),
             "follows": coef(d.get("new_follows")), "shares": coef(d.get("shares")),
             "completion": coef(d.get("completion"))}
            for d in follow_samples if coef(d.get("new_follows")) > 0
        ],
        "zero_follow_high_read_samples": [
            {"title": d["title"][:30], "reads": coef(d.get("reads")),
             "follows": 0, "shares": coef(d.get("shares")),
             "completion": coef(d.get("completion"))}
            for d in zero_follow_high_read
        ],
        "rule": "与账号主题(微信/AI/工具/理财)相关 → 高完读×高分享 → 转化粉丝；纯公司新闻或话题无关 → 高阅读也 0 关注。",
    },
    "reader_profile": {
        "age_top": max(age_agg.items(), key=lambda x: x[1])[0] if age_agg else None,
        "age_dist": age_agg,
        "gender_top": "男" if gender_agg.get("男", 0) > gender_agg.get("女", 0) else "女",
        "gender_dist": gender_agg,
        "region_top5": region_top,
        "sample_n": n_age,
    },
    "engagement": {
        "avg_engagement_rate": avg_eng_rate,
        "avg_fan_active_rate": avg_fan_active,
        "high_eng_follows": high_eng_follows,
        "low_eng_follows": low_eng_follows,
        "samples": sorted(eng_data, key=lambda x: -x["eng_rate"])[:5],
        "interpretation": "互动率=(分享+留言+收藏)/阅读。高互动文章累积推荐权重，长远利好阅读增长和涨粉。高互动(≥5%)文章合计关注 vs 低互动(<5%)文章合计关注，可看出互动对涨粉的间接作用。",
    },
    "angle_patterns": {
        "effective_angles": [a for a in effective_angles if a["effective"]],
        "all_angles": effective_angles,
        "zero_follow_patterns": zero_follow_patterns[:5],
        "design_note": "话题开放（任何新热点/定位内方向都能套），角度从历史数据学（什么结构/切口有效）。推荐器用 effective_angles 生成价值型选题，不限定话题。",
    },
    "fan_status": {
        "fans": fans,
        "growth_month_pct": growth_month,
        "months_to_100": months_100,
        "milestone": "粉丝达 100 后次日自动解锁账号级精准画像",
    },
}

out = f"{DATA}/hit_baseline.json"
json.dump(baseline, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"✓ 基准快照已生成: {out}")
print(f"  数据窗口: {baseline['data_window']['start']} ~ {baseline['data_window']['end']} ({baseline['data_window']['n_articles']} 篇)")
print(f"  标题杠杆: {baseline['title_formula']['lift']}× (具名均 {brand_avg} vs 非具名均 {nonb_avg})")
print(f"  周二占比: {baseline['weekday_pattern']['tue_share_pct']}% ({baseline['weekday_pattern']['tue_n']} 篇)")
print(f"  涨粉相关: r_read={baseline['follow_mechanism']['r_read_vs_follow']} r_prod={baseline['follow_mechanism']['r_completion_x_share_vs_follow']}")
print(f"  有效角度: {', '.join(a['angle']+'('+str(a['avg_engagement_rate'])+'%)' for a in baseline['angle_patterns']['effective_angles'][:4])}")
print(f"  粉丝: {fans} (月增 {growth_month}%), 距 100 粉约 {months_100} 个月")

"""爆款预测基准快照 data/processed/hit_baseline.json（原 update_baseline.py）。

每次分析都会重建；prediction.py（标题评分）和 recommend.py（选题推荐）都读它。
"""

import json
from collections import defaultdict
from datetime import date

from . import dataset
from .analysis import brand_lift, classify, coef, follow_correlations, follow_months, region_profile, weekday_stats, weighted
from .config import BRANDS, CONFLICT, HIGH_FOLLOW_TOPICS, POSITIONING, PROCESSED_DIR

BASELINE_PATH = PROCESSED_DIR / "hit_baseline.json"

# 有效角度：从历史数据学「什么结构/切口有效」，话题保持开放
ANGLE_MARKERS = [
    ("方法论/科普体", ["一文看懂", "如何", "方法", "技巧", "指南", "体系", "入门", "科普", "原理"]),
    ("复盘体", ["复盘", "周度", "总结", "回顾", "这件事", "这一周"]),
    ("对比/选择体", [" vs ", "还是", "该选", "怎么选", "和", "对比", "区别"]),
    ("清单/数字体", ["3个", "三个", "5个", "几个", "清单", "步骤", "件事", "动作"]),
    ("冲突/风险体", ["撕下", "归零", "扛不住", "崩", "慌了", "危险", "陷阱", "别再", "误区"]),
    ("机会/判断体", ["机会", "值得", "该不该", "到底", "真正", "信号", "趋势", "下一步"]),
    ("平台生态体", ["来了", "更新", "发布", "上线", "改版", "接入", "开放"]),
    ("决策框架体", ["判断", "框架", "标准", "怎么算", "该不该", "值不值"]),
]


def detect_angles(title):
    t = title.lower()
    tags = [name for name, markers in ANGLE_MARKERS if any(m.lower() in t for m in markers)]
    return tags or ["普通"]


def build() -> dict:
    details = dataset.load_details()
    arts = dataset.load_recent()
    with_reads = [d for d in details if d.get("reads") is not None]
    full = [d for d in details if d.get("completion") is not None]
    ua = dataset.load_user_analysis()
    ca = dataset.load_content_analysis()

    lf = brand_lift(with_reads)
    bc_samples = sorted(
        ({"title": d["title"][:30], "reads": coef(d.get("reads")), "new_follows": coef(d.get("new_follows")),
          "shares": coef(d.get("shares"))}
         for d in with_reads if {"具名主体", "冲突"} <= set(classify(d["title"]))),
        key=lambda x: -x["reads"])

    wd = weekday_stats(arts)
    tue = wd[1]
    total_reads = sum(a.get("reads") or 0 for a in arts)
    other_totals = [w["total"] for i, w in enumerate(wd) if i != 1 and w["n"]]

    follow_samples = sorted(full, key=lambda d: -coef(d.get("new_follows")))[:5]
    zero_follow_high_read = sorted(
        [d for d in full if coef(d.get("new_follows")) == 0 and coef(d.get("reads")) >= 30],
        key=lambda d: -coef(d.get("reads")))[:5]

    age_agg, n_age = weighted(details, "age")
    gender_agg, _ = weighted(details, "gender")
    region_top, _ = region_profile(details, top=5)

    eng_data = []
    for d in full:
        r = coef(d.get("reads"))
        if not r:
            continue
        eng = coef(d.get("shares")) + coef(d.get("comments")) + coef(d.get("collections"))
        reach, mr = coef(d.get("reach")), coef(d.get("msg_reads"))
        tsn, sir = coef(d.get("total_share_n")), coef(d.get("share_induced_reads"))
        eng_data.append({"title": d["title"][:20], "reads": r, "eng_rate": round(eng / r * 100, 1),
                         "fan_active": round(mr / reach * 100, 1) if reach else 0,
                         "share_spread": round(sir / tsn * 100, 1) if tsn else 0,
                         "new_follows": coef(d.get("new_follows"))})

    angle_stats = defaultdict(lambda: {"n": 0, "eng": [], "comp": [], "fc": [], "titles": []})
    for d in full:
        r = coef(d.get("reads"))
        if not r:
            continue
        eng_rate = round((coef(d.get("shares")) + coef(d.get("comments")) + coef(d.get("collections"))) / r * 100, 1)
        for angle in detect_angles(d["title"]):
            s = angle_stats[angle]
            s["n"] += 1
            s["eng"].append(eng_rate)
            s["comp"].append(coef(d.get("completion")))
            s["fc"].append(round(coef(d.get("new_follows")) / r * 100, 2))
            s["titles"].append(d["title"][:24])
    angles = []
    for angle, s in angle_stats.items():
        avg_eng = round(sum(s["eng"]) / s["n"], 1)
        avg_comp = round(sum(s["comp"]) / s["n"], 1)
        avg_fc = round(sum(s["fc"]) / s["n"], 2)
        angles.append({"angle": angle, "n": s["n"], "avg_engagement_rate": avg_eng, "avg_completion": avg_comp,
                       "avg_follow_conv_pct": avg_fc, "effective": avg_eng >= 5 or avg_fc >= 0.5 or avg_comp >= 40,
                       "example_titles": s["titles"][:3]})
    angles.sort(key=lambda x: -(x["avg_engagement_rate"] + x["avg_follow_conv_pct"] * 2 + x["avg_completion"] / 5))
    zero_follow_patterns = [
        {"title": d["title"][:30], "reads": coef(d.get("reads")), "angles": detect_angles(d["title"]),
         "warning": "高阅读0关注，话题与账号定位无关或停留在公司新闻层面"}
        for d in full if coef(d.get("reads")) >= 30 and coef(d.get("new_follows")) == 0]

    c = follow_correlations(full)
    fans, growth = ua.get("fans"), ua.get("growth_month_pct")
    traffic = ca.get("traffic", {})
    return {
        "generated_at": date.today().isoformat(),
        "data_window": {"start": arts[0]["date"] if arts else None, "end": arts[-1]["date"] if arts else None,
                        "n_articles": len(arts), "n_with_detail": len(full)},
        "title_formula": {
            "brand_keywords": BRANDS, "conflict_keywords": CONFLICT,
            "brand_avg_reads": lf["brand_avg"], "nonb_avg_reads": lf["nonb_avg"], "lift": lf["lift"],
            "brand_conflict_samples": bc_samples[:5],
        },
        "weekday_pattern": {
            "tue_share_pct": round(tue["total"] / total_reads * 100) if total_reads else 0,
            "tue_n": tue["n"], "tue_avg_reads": tue["avg"], "tue_total_reads": tue["total"],
            "other_weekday_range": [min(other_totals), max(other_totals)] if other_totals else [0, 0],
            "weekend_total_reads": wd[5]["total"] + wd[6]["total"],
        },
        "follow_mechanism": {
            "r_read_vs_follow": c["read"], "r_completion_vs_follow": c["completion"], "r_share_vs_follow": c["share"],
            "r_completion_x_share_vs_follow": c["completion_x_share"], "n_sample": len(full),
            "interpretation": "关注与阅读量几乎无关(r_read低)，与完读×分享高度相关(r_prod高)。即：裸阅读量不涨粉，完读率×分享率才是涨粉引擎。",
        },
        "traffic": {"recommend_pct": traffic.get("推荐", 0), "s1s_pct": traffic.get("搜一搜", 0),
                    "msg_pct": traffic.get("公众号消息", 0), "total_readers": ca.get("total_readers")},
        "platform_relevance": {
            "high_follow_topics": HIGH_FOLLOW_TOPICS,
            "account_positioning": {
                "main": POSITIONING,
                "description": "账号核心定位：围绕科技/商业/金融产出优质内容",
                "occasional_rule": "偶尔极少数写社会现象类，但必须与定位相关（如苹果AI账单=科技+商业）",
                "related_topics": HIGH_FOLLOW_TOPICS,
                "deviation_impact": "频繁偏离定位会稀释账号认知，影响长期推荐权重和粉丝转化",
            },
            "high_follow_samples": [
                {"title": d["title"][:30], "reads": coef(d.get("reads")), "follows": coef(d.get("new_follows")),
                 "shares": coef(d.get("shares")), "completion": coef(d.get("completion"))}
                for d in follow_samples if coef(d.get("new_follows")) > 0],
            "zero_follow_high_read_samples": [
                {"title": d["title"][:30], "reads": coef(d.get("reads")), "follows": 0,
                 "shares": coef(d.get("shares")), "completion": coef(d.get("completion"))}
                for d in zero_follow_high_read],
            "rule": "与账号主题(微信/AI/工具/理财)相关 → 高完读×高分享 → 转化粉丝；纯公司新闻或话题无关 → 高阅读也 0 关注。",
        },
        "reader_profile": {
            "age_top": max(age_agg.items(), key=lambda x: x[1])[0] if age_agg else None, "age_dist": age_agg,
            "gender_top": "男" if gender_agg.get("男", 0) > gender_agg.get("女", 0) else "女", "gender_dist": gender_agg,
            "region_top5": region_top, "sample_n": n_age,
        },
        "engagement": {
            "avg_engagement_rate": round(sum(e["eng_rate"] for e in eng_data) / len(eng_data), 1) if eng_data else 0,
            "avg_fan_active_rate": round(sum(e["fan_active"] for e in eng_data) / len(eng_data), 1) if eng_data else 0,
            "high_eng_follows": sum(e["new_follows"] for e in eng_data if e["eng_rate"] >= 5),
            "low_eng_follows": sum(e["new_follows"] for e in eng_data if e["eng_rate"] < 5),
            "samples": sorted(eng_data, key=lambda x: -x["eng_rate"])[:5],
            "interpretation": "互动率=(分享+留言+收藏)/阅读。高互动文章累积推荐权重，长远利好阅读增长和涨粉。高互动(≥5%)文章合计关注 vs 低互动(<5%)文章合计关注，可看出互动对涨粉的间接作用。",
        },
        "angle_patterns": {
            "effective_angles": [a for a in angles if a["effective"]], "all_angles": angles,
            "zero_follow_patterns": zero_follow_patterns[:5],
            "design_note": "话题开放（任何新热点/定位内方向都能套），角度从历史数据学（什么结构/切口有效）。推荐器用 effective_angles 生成价值型选题，不限定话题。",
        },
        "fan_status": {"fans": fans, "growth_month_pct": growth, "months_to_100": follow_months(fans, growth),
                       "milestone": "粉丝达 100 后次日自动解锁账号级精准画像"},
    }


def write() -> dict:
    b = build()
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(b, ensure_ascii=False, indent=1), encoding="utf-8")
    return b


def load():
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

"""共用的分析口径：标题分类、相关系数、互动指标、读者画像，以及网页总览 / 文章列表的数据。

两个样本集合：
  有 reads 的文章        → 标题分级、阅读排行、星期规律（列表页就有）
  有 completion 的文章   → 漏斗、相关性、互动、画像（只有抓过详情页的才有）
"""

from collections import defaultdict
from datetime import date, timedelta

from . import dataset
from .config import (AGE_ORDER, BRANDS, CONFLICT, DETAIL_RECENT_DAYS, HIGH_ENGAGEMENT, PROFILE_MIN_READS,
                     PROFILE_MIN_RECOMMEND, TRAFFIC_SOURCES, WEEKDAYS)


def coef(x):
    return x if x is not None else 0


def classify(title: str) -> list:
    tags = []
    if any(b in title for b in BRANDS):
        tags.append("具名主体")
    if any(c in title for c in CONFLICT):
        tags.append("冲突")
    if "？" in title or "?" in title:
        tags.append("问号")
    if "复盘" in title or "周度" in title:
        tags.append("复盘")
    return tags


def corr(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return round(num / (dx * dy), 2) if dx and dy else 0.0


def _profile_sample(details):
    for d in details:
        r = coef(d.get("reads"))
        if not r or r < PROFILE_MIN_READS:
            continue
        if (d.get("channels") or {}).get("推荐", 0) < PROFILE_MIN_RECOMMEND:
            continue
        yield d, r


def weighted(details, field):
    """推荐主导、阅读够多的单篇画像按阅读量加权聚合，返回 ({类别: 占比%}, 样本篇数)。"""
    agg, tot, n = defaultdict(float), 0.0, 0
    for d, r in _profile_sample(details):
        n += 1
        for k, v in (d.get(field) or {}).items():
            agg[k] += v * r
            tot += v * r
    return ({k: round(v / tot * 100, 1) for k, v in agg.items()} if tot else {}), n


def region_profile(details, top=7):
    agg, tot, n = defaultdict(float), 0.0, 0
    for d, r in _profile_sample(details):
        n += 1
        for name, pct in d.get("region") or []:
            v = float(str(pct).rstrip("%"))
            agg[name] += v * r
            tot += v * r
    items = sorted(((k, round(v / tot * 100, 1)) for k, v in agg.items() if k != "未知"), key=lambda x: -x[1])
    return items[:top] if tot else [], n


def metrics(d) -> dict:
    """单篇派生指标（统一用列表页 reads 计算）。"""
    r = coef(d.get("reads"))
    sh, cm, co = coef(d.get("shares")), coef(d.get("comments")), coef(d.get("collections"))
    nf = coef(d.get("new_follows"))
    reach, mr = coef(d.get("reach")), coef(d.get("msg_reads"))
    tsn, sir = coef(d.get("total_share_n")), coef(d.get("share_induced_reads"))
    return {
        "share_rate": round(sh / r * 100, 2) if r else 0,
        "engagement": sh + cm + co,
        "engagement_rate": round((sh + cm + co) / r * 100, 1) if r else 0,
        "follow_per_k": round(nf / r * 1000, 2) if r else 0,
        "fan_active": round(mr / reach * 100, 1) if reach else 0,
        "share_spread": round(sir / tsn * 100, 1) if tsn else 0,
    }


def weekday_stats(arts):
    cnt, reads = defaultdict(int), defaultdict(list)
    for a in arts:
        if not a.get("date"):
            continue
        wd = date.fromisoformat(a["date"]).weekday()
        cnt[wd] += 1
        reads[wd].append(a.get("reads") or 0)
    total = sum(a.get("reads") or 0 for a in arts)
    return [{"day": WEEKDAYS[i], "n": cnt[i], "avg": round(sum(reads[i]) / len(reads[i]), 1) if reads[i] else 0,
             "total": sum(reads[i]), "share": round(sum(reads[i]) / total * 100, 1) if total else 0} for i in range(7)]


def taxonomy(details_with_reads):
    grp = defaultdict(list)
    for d in details_with_reads:
        grp["+".join(classify(d["title"])) or "其他"].append(coef(d.get("reads")))
    return sorted(([k, len(v), round(sum(v) / len(v), 1)] for k, v in grp.items()), key=lambda x: -x[2])


def brand_lift(details_with_reads):
    brand = [coef(d.get("reads")) for d in details_with_reads if "具名主体" in classify(d["title"])]
    nonb = [coef(d.get("reads")) for d in details_with_reads if "具名主体" not in classify(d["title"])]
    b = round(sum(brand) / len(brand), 1) if brand else 0
    nb = round(sum(nonb) / len(nonb), 1) if nonb else 0
    return {"brand_n": len(brand), "brand_avg": b, "nonb_n": len(nonb), "nonb_avg": nb,
            "lift": round(b / nb) if nb else 0}


def follow_correlations(details_valid):
    reads = [coef(d.get("reads")) for d in details_valid]
    comp = [coef(d.get("completion")) for d in details_valid]
    share = [coef(d.get("shares")) for d in details_valid]
    sr = [coef(d.get("shares")) / max(coef(d.get("reads")), 1) for d in details_valid]
    nf = [coef(d.get("new_follows")) for d in details_valid]
    return {"n": len(details_valid), "read": corr(reads, nf), "completion": corr(comp, nf), "share": corr(share, nf),
            "share_rate": corr(sr, nf), "completion_x_share": corr([c * s for c, s in zip(comp, share)], nf)}


def follow_months(fans, growth_pct, target=100):
    import math
    if not (fans and growth_pct and growth_pct > 0 and fans < target):
        return None
    return round(math.log(target / fans) / math.log(1 + growth_pct / 100), 1)


# ---------------- 网页数据 ----------------

def article_rows() -> list:
    details = dataset.load_details()
    have_raw = dataset.detail_files()
    today = date.today()
    rows = []
    for d in details:
        pub = d.get("publish")
        row = {k: d.get(k) for k in ("id", "title", "publish", "reads", "reads_d2", "completion", "new_follows", "shares",
                                     "moments", "forwards", "comments", "collections", "appreciation", "listen_full")}
        row["tags"] = classify(d.get("title", ""))
        row["has_detail"] = d.get("completion") is not None
        row["has_id"] = not str(d.get("id", "")).startswith("noid|")
        row["raw_detail"] = str(d.get("id")) in have_raw
        row["in_30d"] = bool(pub) and (today - date.fromisoformat(pub)).days <= DETAIL_RECENT_DAYS
        row["weekday"] = WEEKDAYS[date.fromisoformat(pub).weekday()] if pub else None
        if row["has_detail"]:
            row.update(metrics(d))
        rows.append(row)
    rows.sort(key=lambda r: r.get("publish") or "", reverse=True)
    return rows


def article_detail(aid: str):
    d = next((x for x in dataset.load_details() if str(x.get("id")) == aid), None)
    if d is None:
        return None
    out = {k: v for k, v in d.items() if not k.startswith("_")}
    out["tags"] = classify(d.get("title", ""))
    if d.get("completion") is not None:
        out.update(metrics(d))
    out["age"] = {k: d["age"][k] for k in AGE_ORDER if k in (d.get("age") or {})}
    return out


def overview() -> dict:
    arts = dataset.load_recent()
    details = dataset.load_details()
    win = dataset.load_window()
    ua = dataset.load_user_analysis()
    ca = dataset.load_content_analysis()
    with_reads = [d for d in details if d.get("reads") is not None]
    valid = [d for d in details if d.get("completion") is not None]

    total_reads = sum(a.get("reads") or 0 for a in arts)
    ranked = sorted(arts, key=lambda a: -(a.get("reads") or 0))
    top3 = sum(a.get("reads") or 0 for a in ranked[:3])

    # 周均发文：跨度超过一年时只看近一年，避免多年跨度把近期节奏稀释
    week_avg = 0
    if win.get("since") and win.get("until"):
        ws, wu = date.fromisoformat(win["since"]), date.fromisoformat(win["until"])
        span = min((wu - ws).days, 365)
        start = wu - timedelta(days=span)
        n = sum(1 for a in arts if date.fromisoformat(a["date"]) >= start)
        week_avg = round(n / max(1, span // 7), 1)

    eng = []
    for d in valid:
        if coef(d.get("reads")):
            m = metrics(d)
            eng.append({"id": d["id"], "title": d["title"], "reads": d["reads"], "rate": m["engagement_rate"],
                        "follows": coef(d.get("new_follows")), "completion": d.get("completion")})
    age, n_age = weighted(details, "age")
    gender, _ = weighted(details, "gender")
    region, _ = region_profile(details)
    lift = brand_lift(with_reads)
    corrs = follow_correlations(valid)
    wd = weekday_stats(arts)
    tue = wd[1]

    insights = []
    if total_reads:
        insights.append(f"头部 3 篇占全部阅读的 <b>{round(top3 / total_reads * 100)}%</b>，阅读高度集中在少数爆款。")
    if tue["n"]:
        insights.append(f"周二发了 {tue['n']} 篇，贡献 <b>{tue['share']}%</b> 的阅读（单篇均 {tue['avg']}）。")
    if lift["lift"]:
        insights.append(f"标题带具名主体（苹果、微信等）的文章平均阅读是不带的 <b>{lift['lift']}×</b>"
                        f"（{lift['brand_avg']} vs {lift['nonb_avg']}）。")
    if corrs["n"] >= 3:
        insights.append(f"新增关注与阅读量相关 r={corrs['read']}，与完读率×分享数相关 <b>r={corrs['completion_x_share']}</b>"
                        f"（{corrs['n']} 篇有详情）：涨粉看完读和分享，不看裸阅读。")
    hi = [e for e in eng if e["rate"] >= HIGH_ENGAGEMENT]
    if hi:
        insights.append(f"互动率 ≥ {HIGH_ENGAGEMENT:g}% 的有 {len(hi)} 篇，例如《{hi[0]['title'][:16]}》{hi[0]['rate']}%。")
    rec = ca["traffic"].get("推荐")
    if rec:
        insights.append(f"账号阅读 <b>{rec:.1f}%</b> 来自推荐，开头前三句决定能不能被继续推荐。")

    return {
        "window": win,
        "kpi": {
            "articles": len(arts), "with_detail": len(valid), "total_reads": total_reads, "week_avg": week_avg,
            "top3_share": round(top3 / total_reads * 100) if total_reads else 0,
            "fans": ua.get("fans"), "growth_month_pct": ua.get("growth_month_pct"),
            "months_to_100": follow_months(ua.get("fans"), ua.get("growth_month_pct")),
            "total_follows": sum(coef(d.get("new_follows")) for d in valid),
            "avg_engagement": round(sum(e["rate"] for e in eng) / len(eng), 1) if eng else None,
            "tue_share": tue["share"], "lift": lift["lift"],
        },
        "timeline": [{"date": a["date"], "title": a["title"], "reads": a.get("reads"), "id": a.get("appmsg_id")}
                     for a in arts],
        "weekday": wd,
        "taxonomy": taxonomy(with_reads),
        "lift": lift,
        "correlations": corrs,
        "engagement": sorted(eng, key=lambda e: -e["rate"]),
        "traffic": [{"name": k, "value": ca["traffic"].get(k, 0)} for k in TRAFFIC_SOURCES if k in ca["traffic"]],
        "total_readers": ca.get("total_readers"),
        "profile": {"age": [[k, age[k]] for k in AGE_ORDER if k in age], "gender": gender, "region": region,
                    "sample": n_age},
        "snapshots": {"user_analysis": ua.get("date"), "content_analysis": ca.get("date")},
        "insights": insights,
    }


def diagnostics() -> str:
    """命令行诊断输出（原 analyze_extra.py）。"""
    arts = dataset.load_recent()
    details = dataset.load_details()
    with_reads = [d for d in details if d.get("reads") is not None]
    valid = [d for d in details if d.get("completion") is not None]
    lines = [f"== 发布星期分布（{len(arts)}篇）=="]
    for w in weekday_stats(arts):
        lines.append(f"  {w['day']}: {w['n']}篇, 平均阅读 {w['avg']}, 合计 {w['total']}")
    lines.append(f"\n== 标题类型 vs 阅读（{len(with_reads)}篇有 reads）==")
    for k, n, avg in taxonomy(with_reads):
        lines.append(f"  [{k}] n={n} 均阅读={avg}")
    lines.append(f"\n== 阅读→关注 漏斗（{len(valid)}篇）==")
    lines.append(f"  {'标题':<16}{'阅读':>6}{'完读%':>6}{'分享':>5}{'分享率%':>8}{'关注':>5}{'关注/千读':>9}")
    for d in sorted(valid, key=lambda x: -coef(x.get("reads"))):
        m = metrics(d)
        lines.append(f"  {d['title'][:15]:<16}{coef(d.get('reads')):>6}{coef(d.get('completion')):>6}"
                     f"{coef(d.get('shares')):>5}{m['share_rate']:>8}{coef(d.get('new_follows')):>5}{m['follow_per_k']:>9}")
    c = follow_correlations(valid)
    lines.append("\n== 与「新增关注」的相关性（Pearson）==")
    lines += [f"  阅读量 r={c['read']}", f"  完读率 r={c['completion']}", f"  分享数 r={c['share']}",
              f"  分享率 r={c['share_rate']}", f"  完读率×分享率(乘积) r={c['completion_x_share']}"]
    lf = brand_lift(with_reads)
    lines.append("\n== 具名主体 阅读杠杆 ==")
    lines.append(f"  具名主体 {lf['brand_n']}篇 均={lf['brand_avg']}")
    lines.append(f"  非具名   {lf['nonb_n']}篇 均={lf['nonb_avg']}")
    return "\n".join(lines)

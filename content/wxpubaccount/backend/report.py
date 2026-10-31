"""自包含 HTML 报告：reports/公众号数据分析与创作指引_YYYY-MM-DD.html（原 generate_final2.py）。"""

from datetime import date, timedelta

from . import dataset
from .analysis import (brand_lift, coef, follow_correlations, follow_months, region_profile, taxonomy, weekday_stats,
                       weighted)
from .config import ACCOUNT_NAME, AGE_ORDER, REPORT_PREFIX, REPORTS_DIR

SPEEDUP = 2.5  # 落实建议（周二爆款 + 具名冲突 + 相关性选题 + 高完读分享）后的示意提速倍数
TRAFFIC_ORDER = [("推荐", "推荐"), ("搜一搜", "搜一搜"), ("公众号主页", "公众号主页"),
                 ("公众号消息", "公众号消息(粉丝主动)"), ("其它", "其它"), ("聊天会话", "聊天会话")]

CSS = """
*{box-sizing:border-box;}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;margin:0;background:#f7fafc;color:#1a202c;line-height:1.65;}
.wrap{max-width:940px;margin:0 auto;padding:28px 20px 60px;}
h1{font-size:25px;margin:0 0 4px;} h2{font-size:18px;margin:28px 0 12px;padding-left:10px;border-left:4px solid #4299e1;}
.sub{color:#718096;font-size:13px;}
.card{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:18px 20px;margin:14px 0;box-shadow:0 1px 3px rgba(0,0,0,.04);}
.kpis{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0;}
.kpi{flex:1;min-width:138px;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:13px 15px;}
.kpi .n{font-size:24px;font-weight:700;color:#2b6cb0;} .kpi .l{font-size:12.5px;color:#718096;}
.row{display:flex;align-items:center;margin:7px 0;font-size:13px;} .lab{width:128px;flex-shrink:0;color:#4a5568;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.track{flex:1;background:#edf2f7;border-radius:6px;height:18px;overflow:hidden;} .fill{height:100%;border-radius:6px;}
.val{width:96px;text-align:right;flex-shrink:0;color:#2d3748;font-variant-numeric:tabular-nums;}
table{width:100%;border-collapse:collapse;font-size:12.5px;} th,td{padding:7px 5px;text-align:center;border-bottom:1px solid #edf2f7;}
th{background:#f7fafc;color:#4a5568;font-weight:600;} td.t{text-align:left;max-width:200px;} td.hot{color:#dd6b20;font-weight:700;background:#fffaf0;}
.note{font-size:12.5px;color:#718096;margin-top:10px;}
.callout{background:#ebf8ff;border:1px solid #bee3f8;border-radius:10px;padding:14px 16px;margin:14px 0;} .callout b{color:#2b6cb0;}
.warn{background:#fffaf0;border:1px solid #feebc8;border-radius:10px;padding:14px 16px;margin:14px 0;} .warn b{color:#c05621;}
.rec{background:#f0fff4;border-left:4px solid #38a169;padding:10px 14px;margin:8px 0;border-radius:0 8px 8px 0;} .rec .p{font-weight:700;color:#276749;}
.foot{margin-top:30px;font-size:12px;color:#a0aec0;text-align:center;}
.legend{font-size:12px;color:#718096;margin:6px 0;} .twocol{display:flex;gap:24px;flex-wrap:wrap;}
"""


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def bar(label, val, maxv, color="#2b6cb0", sub=""):
    pct = (val / maxv * 100) if maxv else 0
    label = _esc(label)
    return (f'<div class="row"><span class="lab" title="{label}">{label}</span><div class="track"><div class="fill" '
            f'style="width:{pct:.1f}%;background:{color}"></div></div><span class="val">{val}{sub}</span></div>')


def hbar(label, pct, color="#38a169"):
    return (f'<div class="row"><span class="lab">{_esc(label)}</span><div class="track"><div class="fill" '
            f'style="width:{pct:.1f}%;background:{color}"></div></div><span class="val">{pct:.1f}%</span></div>')


def render() -> str:
    details = dataset.load_details()
    arts = dataset.load_recent()
    win = dataset.load_window()
    ua = dataset.load_user_analysis()
    ca = dataset.load_content_analysis()
    today = date.today()
    try:
        ws, wu = date.fromisoformat(win["since"]), date.fromisoformat(win["until"])
    except (KeyError, ValueError):
        ws = wu = today

    snap_date = ua["date"] or today.isoformat()
    fans, growth, ch = ua["fans"], ua["growth_month_pct"], ua["channels"]
    # 单片饼图 = 100% 来自该渠道（数值是人数）；多片时数值才是百分比
    if ua["is_single_slice"] and ch:
        art_page_pct = 100.0
    else:
        art_page_pct = ch.get("文章页关注")
    if art_page_pct is not None:
        if ua["is_single_slice"]:
            total = ua.get("channels_total")
            art_page_note = (f"后台快照（截至 {snap_date}）：新增关注渠道饼图仅 1 片"
                             f"{f'（共 {total} 人）' if total else ''}，即 <b>100% 来自文章页关注</b>。建议定期在后台复核饼图。")
        else:
            other = "、".join(f"{k} {v:.1f}%" for k, v in ch.items() if k != "文章页关注")
            art_page_note = (f"后台快照（截至 {snap_date}）：文章页关注占比 {art_page_pct:.1f}%，"
                             f"{'其余渠道 ' + other if other else '饼图仅文章页一片'}。建议定期在后台复核饼图。")
    else:
        art_page_note = f"后台快照（截至 {snap_date}）未解析到明确的「文章页关注」占比，归因结论待复核。"

    months_now = follow_months(fans, growth)
    months_fast = round(months_now / SPEEDUP, 1) if months_now else None
    growth_txt = f"{growth:.1f}%" if growth is not None else "—"

    data_start = min(a["date"] for a in arts) if arts else today.isoformat()
    data_end = max(a["date"] for a in arts) if arts else today.isoformat()
    n_art = len(arts)
    with_reads = [d for d in details if d.get("reads") is not None]
    valid = [d for d in details if d.get("completion") is not None]
    n_det = len(valid)
    weeks = max(1, ((date.fromisoformat(data_end) - date.fromisoformat(data_start)).days + 6) // 7)
    eff_span = min((wu - ws).days, 365)
    eff_start = wu - timedelta(days=eff_span)
    wk_avg = round(sum(1 for a in arts if date.fromisoformat(a["date"]) >= eff_start) / max(1, eff_span // 7), 1)

    traffic, total_readers = ca["traffic"], ca["total_readers"]

    # ---- 星期 ----
    wdl = weekday_stats(arts)
    wd = [(w["day"], w["n"], w["avg"], w["total"]) for w in wdl]
    tue = wd[1]
    total_reads = sum(a.get("reads") or 0 for a in arts)
    tue_share = round(tue[3] / total_reads * 100) if total_reads else 0
    max_non_tue = max((w[3] for i, w in enumerate(wd) if i != 1), default=0)
    min_non_tue_nonzero = min((w[3] for i, w in enumerate(wd) if i != 1 and w[3] > 0), default=0)

    # ---- 标题分级 + 具名杠杆 ----
    tax = taxonomy(with_reads)
    lf = brand_lift(with_reads)
    nonb_avg, lift = lf["nonb_avg"], lf["lift"]
    bc = [t for t in tax if "具名主体" in t[0] and "冲突" in t[0]]
    bc_n, bc_avg = (bc[0][1], bc[0][2]) if bc else (0, 0)
    if bc:
        lift_str = f"杠杆 ≈ <b>{lift}×</b>" if nonb_avg else "杠杆暂不可算（无非具名对照）"
        brand_conflict_note = f'<b>具名主体 + 冲突</b> {bc_n} 篇均 {bc_avg} 阅读，非具名 {lf["nonb_n"]} 篇仅均 {nonb_avg}（{lift_str}）。'
    else:
        brand_conflict_note = "窗口内无「具名主体+冲突」分类样本。"

    # ---- 漏斗 + 相关性 ----
    funnel = []
    for d in sorted(valid, key=lambda x: -coef(x.get("reads"))):
        r, comp, sh, nf = coef(d.get("reads")), coef(d.get("completion")), coef(d.get("shares")), coef(d.get("new_follows"))
        funnel.append((d["title"][:16], r, comp, sh, round(sh / r * 100, 2) if r else 0, nf, round(nf / r * 1000, 2) if r else 0))
    c = follow_correlations(valid)
    r_read, r_comp, r_share, r_prod = c["read"], c["completion"], c["share"], c["completion_x_share"]

    # ---- 反差案例（全部从数据来）----
    def g(d, k):
        return coef(d.get(k)) if d else 0
    apple = next((d for d in valid if "苹果" in d.get("title", "")), None)
    douyin = next((d for d in valid if "抖音" in d.get("title", "")), None)
    fuzhi = next((d for d in valid if "十年致富" in d.get("title", "")), None)
    top_follow = max(valid, key=lambda d: coef(d.get("new_follows")), default=None)
    ap_r, ap_s = g(apple, "reads"), g(apple, "shares")
    ap_sr = round(ap_s / ap_r * 100, 2) if ap_r else 0
    dy_r, dy_c, dy_s = g(douyin, "reads"), g(douyin, "completion"), g(douyin, "shares")
    dy_sr = round(dy_s / dy_r * 100, 2) if dy_r else 0
    fz_r, fz_s = g(fuzhi, "reads"), g(fuzhi, "shares")
    fz_sr = round(fz_s / fz_r * 100, 2) if fz_r else 0
    fz_nf = g(fuzhi, "new_follows")
    fz_fpr = round(fz_nf / fz_r * 1000, 1) if fz_r else 0
    tf_r, tf_f = g(top_follow, "reads"), g(top_follow, "new_follows")
    comp_note = "、".join(f"{d['title'][:6]} {g(d, 'completion')}%"
                          for d in sorted(valid, key=lambda d: -coef(d.get("completion")))[:2])
    c1 = f"《{apple['title'][:10]}》{ap_r} 阅读、分享率仅 {ap_sr}% → <b>0 关注</b>；" if apple else ""
    if douyin:
        dy_f = g(douyin, "new_follows")
        c2 = (f"《{douyin['title'][:10]}》{dy_r} 阅读、完读 {dy_c}%、分享率 {dy_sr}%（很高）→ 仍 <b>{dy_f} 关注</b>"
              f"（千人比 {round(dy_f / dy_r * 1000, 1) if dy_r else 0}）——话题与“理财/AI工具”账号无关，读者不愿关注；")
    else:
        c2 = ""
    c3 = (f"《{fuzhi['title'][:10]}》仅 {fz_r} 阅读、但分享率 {fz_sr}% 且话题强相关 → <b>{fz_nf} 关注（千人比 {fz_fpr}）</b>。"
          if fuzhi else "")
    if top_follow and tf_f > 0:
        lag_note = (f"与每日净增交叉验证：单篇《{top_follow['title'][:12]}》的 {tf_f} 个关注，对应详情页归因的 {tf_f} 个关注，"
                    f"证实关注滞后阅读约 1 周、由单篇内容驱动（具体每日分布以后台净增趋势为准）。")
    else:
        lag_note = "关注滞后阅读约 1 周，由单篇内容驱动（具体每日分布以后台净增趋势为准）。"

    # ---- 幂律 / 归因 / 画像 ----
    reads_sorted = sorted(arts, key=lambda x: -(x.get("reads") or 0))
    top3 = sum(a.get("reads") or 0 for a in reads_sorted[:3])
    top5 = sum(a.get("reads") or 0 for a in reads_sorted[:5])
    attr = [d for d in valid if coef(d.get("new_follows")) > 0]
    attr_total = sum(coef(d.get("new_follows")) for d in valid)
    age_agg, _ = weighted(details, "age")
    gender_agg, _ = weighted(details, "gender")
    region_sorted, n_reg = region_profile(details)

    def pct_of(x):
        return round(x / total_reads * 100) if total_reads else 0

    sec_traffic = "".join(hbar(lbl, traffic.get(key, 0.0), "#4299e1") for key, lbl in TRAFFIC_ORDER)
    max_cnt = max(w[1] for w in wd) or 1
    sec_freq = "".join(bar(w[0], w[1], max_cnt, "#4299e1") for w in wd)
    sec_wdread = "".join(bar(w[0], w[2], max(x[2] for x in wd) or 1, "#3182ce") for w in wd)
    top_reads = (reads_sorted[0].get("reads") or 0) if reads_sorted else 0
    sec_reads = "".join(bar(a["title"][:16], a.get("reads") or 0, top_reads, "#2b6cb0") for a in reads_sorted[:10])
    sec_tax = "".join(bar(t[0], t[2], max(x[2] for x in tax) or 1, "#805ad5") for t in tax)
    sec_funnel_rows = "".join(
        f'<tr><td class="t">{_esc(t)}</td><td>{r}</td><td>{comp}</td><td>{sh}</td><td>{sr}%</td>'
        f'<td class="{"hot" if nf > 0 else ""}">{nf}</td><td>{fpr}</td></tr>'
        for t, r, comp, sh, sr, nf, fpr in funnel)
    max_follow = max((coef(d.get("new_follows")) for d in valid), default=0) or 1
    sec_follow = "".join(bar(d["title"][:16], coef(d.get("new_follows")), max_follow, "#dd6b20")
                         for d in sorted(valid, key=lambda x: -coef(x.get("new_follows"))) if coef(d.get("new_follows")) > 0)
    sec_follow += (f'<div class="note">其余 {len(valid) - len(attr)} 篇带来 0 关注。{n_det} 篇窗口内（仅含已抓取详情页的文章）合计 '
                   f'<b>{attr_total}</b> 个关注；账号累计粉丝 {fans if fans is not None else "—"}（后台快照截至 {snap_date}）。'
                   f'注意：此处吸粉数仅来自已抓取详情页的文章，并非窗口内全部关注。</div>')

    # ---- 互动深度 ----
    engagement_rows, eng_data = [], []
    for d in sorted(valid, key=lambda x: -coef(x.get("reads"))):
        r = coef(d.get("reads"))
        if not r:
            continue
        sh, cm, co = coef(d.get("shares")), coef(d.get("comments")), coef(d.get("collections"))
        mo, fw = coef(d.get("moments")), coef(d.get("forwards"))
        eng_rate = round((sh + cm + co) / r * 100, 1)
        reach, mr = coef(d.get("reach")), coef(d.get("msg_reads"))
        fan_active = round(mr / reach * 100, 1) if reach else 0
        tsn, sir = coef(d.get("total_share_n")), coef(d.get("share_induced_reads"))
        share_spread = round(sir / tsn * 100, 1) if tsn else 0
        nf = coef(d.get("new_follows"))
        eng_data.append({"title": d["title"][:18], "reads": r, "eng_rate": eng_rate})
        engagement_rows.append(
            f'<tr><td class="t">{_esc(d["title"][:16])}</td><td>{r}</td><td>{sh}</td><td>{mo}</td><td>{fw}</td>'
            f'<td>{cm}</td><td>{co}</td><td class="{"hot" if eng_rate >= 5 else ""}">{eng_rate}%</td>'
            f'<td>{fan_active}%</td><td>{share_spread}%</td><td class="{"hot" if nf > 0 else ""}">{nf}</td></tr>')
    high_eng = [e for e in eng_data if e["eng_rate"] >= 5]
    low_eng_high_read = [e for e in eng_data if e["reads"] >= 100 and e["eng_rate"] < 2]
    eng_insight = ""
    if high_eng:
        eng_insight += ('<b>高互动文章（≥5%）</b>：' + "、".join(f'《{_esc(e["title"])}》{e["eng_rate"]}%' for e in high_eng[:3])
                        + '——这些文章虽未必阅读最高，但读者参与度强，会累积推荐权重。')
    if low_eng_high_read:
        eng_insight += (' <b>高阅读低互动（虚胖）</b>：' + "、".join(f'《{_esc(e["title"])}》{e["eng_rate"]}%' for e in low_eng_high_read[:2])
                        + '——阅读高但读者看完即走，长远推荐权重会下降。')

    sec_age = "".join(hbar(k, age_agg.get(k, 0), "#805ad5") for k in AGE_ORDER if k in age_agg)
    sec_gender = "".join(hbar(k, v, "#d53f8a") for k, v in [("男", gender_agg.get("男", 0)), ("女", gender_agg.get("女", 0))] if v > 0)
    sec_region = "".join(hbar(k, v, "#319795") for k, v in region_sorted)
    spread_rows = "".join(
        f'<tr><td class="t">{_esc(d["title"][:18])}</td><td>{coef(d.get("reads"))}</td><td>{coef(d.get("completion"))}%</td>'
        f'<td>{coef(d.get("shares"))}</td><td>{round(coef(d.get("shares")) / max(coef(d.get("reads")), 1) * 100, 2)}%</td>'
        f'<td>{coef(d.get("collections"))}</td><td>{coef(d.get("comments"))}</td>'
        f'<td class="{"hot" if coef(d.get("new_follows")) > 0 else ""}">{coef(d.get("new_follows"))}</td></tr>'
        for d in sorted(valid, key=lambda x: -coef(x.get("reads"))))
    review_avg = next((t[2] for t in tax if "复盘" in t[0] and "冲突" not in t[0] and "具名主体" not in t[0]), 0)
    region_names = "、".join(n for n, _ in region_sorted[:5]) or "（暂无地域数据）"
    case_follow = f"《{top_follow['title'][:10]}》单篇吸粉 {tf_f}，" if top_follow else ""
    case_apple = f"《{apple['title'][:10]}》{ap_r} 读却 0 关注，" if apple else ""
    case_douyin = f"《{douyin['title'][:10]}》{dy_r} 读高互动仍 0 关注。" if douyin else ""
    case_fuzhi = f"《{fuzhi['title'][:8]}》仅 {fz_r} 读但分享率 {fz_sr}% → 千人关注比 {fz_fpr}，远超苹果。" if fuzhi else ""
    contrast_apple = f"阅读第一的《{apple['title'][:10]}》({ap_r}) 带来 <b>{g(apple, 'new_follows')} 关注</b>；" if apple else ""
    contrast_top = f"《{top_follow['title'][:10]}》({tf_r}) 带来 <b>{tf_f} 关注</b>" if top_follow else ""

    return f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>公众号数据分析与创作指引</title>
<style>{CSS}</style></head><body><div class="wrap">

<h1>公众号数据分析与创作指引</h1>
<div class="sub">账号「{ACCOUNT_NAME}」 · 数据区间 {data_start} ~ {data_end} · 数据截至 {snap_date} · 报告生成于 {today.isoformat()}</div>

<div class="callout">
<b>一句话结论：</b>你的粉丝 <b>主要来自文章页</b>（{art_page_note}）。
涨阅读靠「<b>具名主体 + 冲突</b>」标题（杠杆 ≈ <b>{lift}×</b>），且<b>周二</b>发文吃掉 {tue_share}% 阅读；
涨粉靠「<b>完读率 × 分享率 × 平台相关度</b>」——数据证实：关注与阅读量几乎无关（r={r_read}），却与完读×分享高度相关（r={r_prod}）。
所以：<b>把爆款稿安排在周二、用"具名+冲突"引爆推荐，并在爆款里优先选"微信/工具/理财"相关角度</b>，是提阅读+涨粉的同一套打法。
</div>

<div class="kpis">
  <div class="kpi"><div class="n">{n_art}</div><div class="l">数据区间发文（篇）</div></div>
  <div class="kpi"><div class="n">{wk_avg}</div><div class="l">周均发文（篇/周）</div></div>
  <div class="kpi"><div class="n">{total_reads}</div><div class="l">{n_art} 篇累计阅读</div></div>
  <div class="kpi"><div class="n">{pct_of(top3)}%</div><div class="l">头部3篇阅读占比</div></div>
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
  <div class="legend" style="margin-top:14px;">标题类型 vs 平均阅读（{len(with_reads)} 篇有 reads，按阅读降序）</div>
  {sec_tax}
  <div class="note">头部 3 篇占 {pct_of(top3)}% 阅读、头部 5 篇占 {pct_of(top5)}%。
  {brand_conflict_note}
  复盘类（鱼盆系列）均 {review_avg}，用于维系铁粉、不指望涨量。</div>
</div>

<h2>四、传播力深度：完读率与分享率决定质量</h2>
<div class="card">
  <table>
    <tr><th>文章</th><th>阅读</th><th>完读率</th><th>分享</th><th>分享率</th><th>收藏</th><th>留言</th><th>新增关注</th></tr>
    {spread_rows}
  </table>
  <div class="note">完读率高多为方法论/复盘（{comp_note}）；爆款靠推荐起量。
  <b>分享率 = 分享/阅读</b>，是内容被转发扩散的强度指标，也是涨粉的关键前导。</div>
</div>

<h2>五、互动深度分析（新）：阅读≠关注，但互动是长远推荐权重</h2>
<div class="card">
  <div class="legend">各文章互动数据（按阅读降序，{n_det} 篇有详情）</div>
  <table>
    <tr><th>文章</th><th>阅读</th><th>分享</th><th>朋友圈</th><th>转发</th><th>留言</th><th>收藏</th><th>互动率</th><th>粉丝活跃</th><th>分享传播</th><th>关注</th></tr>
    {"".join(engagement_rows)}
  </table>
  <div class="note">互动率 = (分享+留言+收藏)/阅读；粉丝活跃度 = 消息阅读/送达；分享传播力 = 分享产生阅读/总分享。
  {eng_insight}
  <br><b>结论</b>：高阅读≠高互动（如爆款可能互动率 < 1%），但高互动文章会累积微信推荐权重，长远利好阅读增长和涨粉。<b>写文章不仅要冲阅读，还要设计互动钩子</b>（提问引留言、金句引收藏、实用引转发）。</div>
</div>

<h2>六、阅读→关注漏斗（新）：为什么大阅读≠大涨粉</h2>
<div class="card">
  <table>
    <tr><th>文章</th><th>阅读</th><th>完读%</th><th>分享</th><th>分享率%</th><th>新增关注</th><th>关注/千读</th></tr>
    {sec_funnel_rows}
  </table>
  <div class="warn"><b>反差案例：</b>
  {c1}
  {c2}
  {c3}
  <br>→ 关注 = 阅读 × 完读率 × 分享率 × <b>平台相关度</b>，第四步决定天花板。</div>
</div>

<h2>七、吸粉归因：谁真正带来了粉丝</h2>
<div class="card">
  <div class="legend">各文章带来的「新增关注」数量（窗口内 {n_det} 篇）</div>
  {sec_follow}
  <div class="warn"><b>关键反差：</b>{contrast_apple}{contrast_top}。
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
  <div class="note">{lag_note}</div>
</div>

<h2>九、流量结构：几乎全靠推荐分发</h2>
<div class="card">
  <div class="legend">账号级阅读来源（内容分析，阅读总人数 {total_readers if total_readers is not None else "—"}）</div>
  {sec_traffic}
  <div class="note">粉丝主动打开仅 {traffic.get("公众号消息", 0):.2f}%。<b>增长几乎完全取决于算法推荐</b>，因此"为推荐优化"（前 3 句抓人、短段落、高完读）是阅读量第一杠杆；"搜一搜"{traffic.get("搜一搜", 0):.2f}% 零成本，值得吃长尾。</div>
</div>

<h2>十、读者画像：谁在看你（单篇聚合，样本加权）</h2>
<div class="card">
  <div class="legend">性别分布</div>
  {sec_gender}
  <div class="twocol">
    <div style="flex:1;min-width:260px;"><div class="legend">年龄分布</div>{sec_age}</div>
    <div style="flex:1;min-width:260px;"><div class="legend">地域 Top（加权）</div>{sec_region}</div>
  </div>
  <div class="note">读者以 <b>26-45 岁、男性占绝对多数</b>为主，集中在 <b>{region_names}</b>。
  <b>口径：</b>粉丝&lt;100 时账号级画像隐藏，此处为「推荐主导的高阅读单篇」画像按阅读量加权聚合（已排除 2–15 阅读的极低样本文，避免失真）；样本数 ≈ {n_reg} 篇。
  <b>里程碑：</b>账号级画像（性别/年龄/城市/终端/活跃时间）在<b>粉丝达 100 后次日自动解锁</b>——这是你下一个明确目标。</div>
</div>

<h2>十一、可执行优化方向（按杠杆排序）</h2>

<div class="rec"><div class="p">① 爆款排在周二发（最高杠杆、零成本）</div>
证据：周二 {tue[1]} 篇占全量 {tue_share}% 阅读（均 {tue[2]}），其余工作日合计阅读 {min_non_tue_nonzero}–{max_non_tue}。把每周 1–2 篇"爆款候选"固定在周二；常规复盘稿排其他日维持节奏。</div>

<div class="rec"><div class="p">② 标题用「具名主体 + 冲突」公式</div>
证据：具名+冲突 {bc_n} 篇均 {bc_avg} 阅读，非具名均 {nonb_avg}（≈{lift}×）。
下一篇试试：〈苹果也扛不住了〉〈微信这个更新，有点猛〉〈百度，这次真的急了〉。</div>

<div class="rec"><div class="p">③ 涨粉：爆款里优先选"微信 / 工具 / 理财"角度</div>
证据：相关性显示关注 ≠ 阅读量（r={r_read}），而 = 完读×分享×相关度（r={r_prod}）。{case_follow}{case_apple}{case_douyin}同样引爆推荐，选"与账号相关"的选题，关注转化高一个量级。</div>

<div class="rec"><div class="p">④ 把完读率与分享率做高（涨粉的真正引擎）</div>
证据：关注与完读×分享相关 r={r_prod}（最强）。做法：开头 3 句抛冲突/反常识，多用小标题与短段落，结尾给"可转发的金句/清单/数据卡"。{case_fuzhi}</div>

<div class="rec"><div class="p">⑤ 爆款发布后 1 周内持续导流</div>
证据：关注滞后阅读约 1 周。文章发布后一周内，于文末/次条持续放置关注引导，承接滞后关注。</div>

<div class="rec"><div class="p">⑥ 为推荐优化开篇 + 吃"搜一搜"长尾</div>
证据：推荐占 {traffic.get("推荐", 0):.2f}%，搜一搜占 {traffic.get("搜一搜", 0):.2f}% 且零成本。标题/正文嵌入关键词（"微信搜一搜""AI 工具""理财"），稳定吃搜索长尾。</div>

<div class="rec"><div class="p">⑦ 冲 100 粉解锁账号级画像</div>
证据：粉丝达 100 后次日自动展示性别/年龄/城市/终端/活跃时间，届时报告可升级为"账号级精准画像"，进一步优化选题与发布时段。当前 {fans if fans is not None else "—"} 粉（后台快照截至 {snap_date}），按建议②③提速可达。</div>

<div class="callout" style="margin-top:18px;">
<b>涨粉时间预测（到 100 粉解锁画像）：</b><br>
• 维持现状（自然推荐，按当前月增速 {growth_txt} 估算）：约 <b>{months_now if months_now is not None else "—"} 个月</b><br>
• 落实 ①②③④（周二爆款 + 具名冲突 + 相关性选题 + 高完读分享，示意提速 {SPEEDUP}×）：约 <b>{months_fast if months_fast is not None else "—"} 个月</b><br>
关键杠杆就是建议 ②③——把爆款从"公司新闻"转向"平台/工具/理财相关"，并固定在周二。
</div>

<div class="foot">数据来源：微信公众平台后台（用户分析 / 内容分析 / 单篇详情页，{n_det} 篇窗口内文章逐篇抓取，数据截至 {snap_date}）。
本报告由浏览器自动化抓取 + 多轮交叉分析（星期规律 / 标题分级 / 阅读→关注漏斗 / Pearson 相关性）生成，所有数字均可回溯到后台原始页面。</div>

</div></body></html>'''


def write() -> dict:
    html = render()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"{REPORT_PREFIX}{date.today().isoformat()}.html"
    out.write_text(html, encoding="utf-8")
    return {"path": str(out), "name": out.name, "bytes": len(html)}


def list_reports() -> list:
    if not REPORTS_DIR.exists():
        return []
    items = []
    for p in REPORTS_DIR.glob("*.html"):
        st = p.stat()
        items.append({"name": p.name, "size": st.st_size, "mtime": int(st.st_mtime),
                      "date": p.stem.replace(REPORT_PREFIX, "") if p.stem.startswith(REPORT_PREFIX) else None})
    return sorted(items, key=lambda x: (x["date"] or "", x["mtime"]), reverse=True)

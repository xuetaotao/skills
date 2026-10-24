# -*- coding: utf-8 -*-
"""分析引擎：单指标统计 → 分组/板块的周期温度与阶段 → 信号与决策提示。

口径（页面同步展示）:
- 分位：最新值在近 10 年（不足 10 年用全部历史）中的百分位，0~1。
- 动量：最新值相对 N 天前的涨跌幅（%），1M/3M/6M/1Y。
- 趋势：3 个月涨跌幅 > +3% 为上行，< -3% 为下行，否则走平。
- 阶段：分位 × 趋势 → 七个阶段（见 STAGES）。
- 周期温度：分组内核心价格的分位平均；板块温度为各分组温度的平均，0~100。
- 只用新鲜（未过期）、非档案的数据下结论；历史不足 3 年的序列不参与温度。
- 短暂坏点（偏离 40% 以上、几天内又回到原水平）在分析时剔除，数据库保留原值，见 clean()。
"""
import bisect
import math
import threading
from datetime import date, timedelta

from . import db
from .config import NOTES, SECTORS, SERIES, SERIES_MAP, STALE_DAYS

WINDOW_YEARS = 10
MIN_POINTS = 60
RELIABLE_YEARS = 3
TREND_BAND = 3.0
MOMENTUM_DAYS = {"1M": 30, "3M": 91, "6M": 182, "1Y": 365}

# 七个阶段按周期顺序排列（order 用于周期轮盘），hint 是决策提示
STAGES = {
    "低位寻底": dict(order=0, tone="cold", meaning="价格在历史低位，且还没有企稳",
                 hint="便宜但还在跌。适合放进观察清单，等动量转正或库存开始下降等企稳信号，再考虑分批布局。"),
    "低位回升": dict(order=1, tone="cold", meaning="从历史低位开始回升，周期可能处在早期",
                 hint="赔率相对较好的阶段。可以关注分批布局的机会，同时确认回升能否持续（库存、股票指数是否配合）。"),
    "上行中段": dict(order=2, tone="warm", meaning="趋势向上，位置居中",
                 hint="顺周期阶段。已持有可继续跟踪，重点看库存和需求能否继续支撑，避免在加速上涨时追加仓位。"),
    "高位强势": dict(order=3, tone="hot", meaning="价格在历史高位，且仍然强势",
                 hint="位置偏高，追高的赔率在下降。已持有者可提前设定止盈纪律或分批兑现，新进需要控制仓位。"),
    "高位回落": dict(order=4, tone="hot", meaning="从历史高位开始回落，周期拐点风险上升",
                 hint="需要警惕的阶段。如果库存同时回升，或者股票先行走弱，回落可能延续，宜谨慎并逐步降低暴露。"),
    "下行中段": dict(order=5, tone="warm", meaning="从中间位置继续下行",
                 hint="下行趋势还没扭转，过早抄底的风险较大。耐心等待价格进入低位区，或出现企稳信号。"),
    "中位震荡": dict(order=6, tone="flat", meaning="位置居中，方向不明",
                 hint="缺少明确信号，以跟踪为主，关注向上或向下的突破。"),
}
LEVEL_PRIORITY = {"risk": 0, "watch": 1, "positive": 2, "info": 3}


# ---------------- 单指标 ----------------

def clean(points, role=None):
    """剔除短暂坏点，返回 (保留的点, 剔除的点)。

    判定：相对上一个保留点偏离 40% 以上，且后面 3 个点内有值回到上一个保留点 10% 以内
    （能识别数据源偶发的串列，如 LME 铅库存某几天填成了锌库存）。
    阈值取 40% 是为了放过真实的剧烈行情，例如 2020-04-21 布伦特单日 -25.6%。
    运价指数接近零时真实日波动可能很大，不做剔除。
    """
    if role == "freight" or len(points) < 3:
        return list(points), []
    keep, outliers = [points[0]], []
    for i in range(1, len(points) - 1):
        p, v = keep[-1][1], points[i][1]
        if p > 0 and v > 0 and abs(v / p - 1) > 0.40:
            ahead = (points[j][1] for j in range(i + 1, min(i + 4, len(points))))
            if any(n > 0 and abs(n / p - 1) < 0.10 for n in ahead):
                outliers.append(points[i])
                continue
        keep.append(points[i])
    keep.append(points[-1])
    return keep, outliers


def pct_rank(value, sorted_values):
    return bisect.bisect_right(sorted_values, value) / len(sorted_values) if sorted_values else None


def level_label(q):
    if q is None:
        return "—"
    for bound, label in ((0.10, "极低位"), (0.25, "低位"), (0.50, "中低位"), (0.75, "中高位"), (0.90, "高位")):
        if q < bound:
            return label
    return "极高位"


def trend_of(m3):
    """按页面显示精度（0.1%）判断，避免显示 -3.0% 却判成下行。"""
    if m3 is None:
        return "—"
    m3 = round(m3, 1)
    return "上行" if m3 > TREND_BAND else "下行" if m3 < -TREND_BAND else "走平"


def stage_of(q, m3):
    """q 按页面显示精度（整数百分位）判断，避免显示温度 80 却不算高位。"""
    if q is None:
        return "数据不足"
    q = round(q * 100) / 100
    t = trend_of(m3)
    if q >= 0.8:
        return "高位回落" if t == "下行" else "高位强势"
    if q < 0.25:
        return "低位回升" if t == "上行" else "低位寻底"
    return {"上行": "上行中段", "下行": "下行中段"}.get(t, "中位震荡")


def momentum(dates, values, days):
    """最新值相对 days 天前（取不晚于该日的最后一个点）的涨跌幅 %；基准非正时无意义，返回 None。"""
    target = (date.fromisoformat(dates[-1]) - timedelta(days=days)).isoformat()
    i = bisect.bisect_right(dates, target) - 1
    if i < 0:
        return None
    base, last = values[i], values[-1]
    if base <= 0 or last <= 0:
        return None
    return round((last / base - 1) * 100, 1)


def window_label(span_years):
    if span_years >= WINDOW_YEARS - 0.5:
        return f"近{WINDOW_YEARS}年"
    if span_years >= 1:
        return f"近{round(span_years)}年"
    return f"近{max(1, round(span_years * 12))}个月"


def spark(dates, values, n=60):
    start = (date.fromisoformat(dates[-1]) - timedelta(days=365)).isoformat()
    i = bisect.bisect_left(dates, start)
    d, v = dates[i:], values[i:]
    step = max(1, len(d) // n)
    idx = list(range(0, len(d), step))
    if idx and idx[-1] != len(d) - 1:
        idx.append(len(d) - 1)
    return [[d[k], v[k]] for k in idx]


def series_stats(cfg, points, today, asof=None):
    """单指标完整统计；asof='YYYY-MM-DD' 时只用该日及以前的数据（用于对比上月）。"""
    if asof:
        points = [p for p in points if p[0] <= asof]
    pts, outliers = clean(points, cfg["role"])
    if not pts:
        return None
    dates = [d for d, _ in pts]
    values = [v for _, v in pts]
    latest_d, latest_v = pts[-1]
    last_dt = date.fromisoformat(latest_d)
    lag = (today - last_dt).days
    span = (last_dt - date.fromisoformat(dates[0])).days / 365.25

    start = (last_dt - timedelta(days=round(WINDOW_YEARS * 365.25))).isoformat()
    window = sorted(values[bisect.bisect_left(dates, start):])
    q = pct_rank(latest_v, window) if len(window) >= MIN_POINTS else None
    channel = None
    if len(window) >= 30:
        channel = {f"p{p}": round(window[min(int(p / 100 * (len(window) - 1)), len(window) - 1)], 4)
                   for p in (10, 25, 50, 75, 90)}
    mom = {k: momentum(dates, values, d) for k, d in MOMENTUM_DAYS.items()}
    m3 = mom["3M"]

    st = dict(
        code=cfg["code"], name=cfg["name"], unit=cfg["unit"], role=cfg["role"], sector=cfg["sector"],
        freq=cfg["freq"], archive=cfg["archive"], note=NOTES.get(cfg["code"], ""),
        latest=latest_v, latest_date=latest_d, first_date=dates[0], points=len(pts),
        lag_days=lag, stale=cfg["archive"] or lag > STALE_DAYS[cfg["freq"]],
        span_years=round(span, 1), reliable=span >= RELIABLE_YEARS, window=window_label(span),
        q=round(q, 3) if q is not None else None, level=level_label(q),
        momentum=mom, trend=trend_of(m3), channel=channel,
        outliers=[d for d, _ in outliers],
    )
    if cfg["role"] == "inventory":
        st["inv_dir"] = "—" if m3 is None else "去库" if m3 < -10 else "累库" if m3 > 10 else "持平"
        st["inv_level"] = ("—" if q is None else "库存偏低（供应偏紧）" if q < 0.25
                           else "库存偏高（供应宽松）" if q > 0.75 else "库存中等")
        st["stage"] = None
    else:
        st["stage"] = stage_of(q, m3)
    if not asof:
        st["spark"] = spark(dates, values)
    return st


# ---------------- 分组与板块 ----------------

def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def pct(q):
    return "—" if q is None else f"{round(q * 100)}%"


def signed(v):
    return "—" if v is None else f"{v:+.1f}%"


def group_view(g, stats):
    core = [stats[c] for c in g["core"] if c in stats]
    usable = [s for s in core if not s["stale"] and s["q"] is not None]
    reliable = [s for s in usable if s["reliable"]]
    basis = reliable or usable
    temp = _mean(s["q"] for s in basis)
    m3 = _mean(s["momentum"]["3M"] for s in usable)
    confidence = ("高" if basis and len(reliable) == len(core) else "中" if reliable else "低") if basis else "无"
    return dict(key=g["key"], name=g["name"], temp=temp, m3=m3, trend=trend_of(m3), stage=stage_of(temp, m3),
                confidence=confidence, core=[s["code"] for s in core],
                aux=[c for c in (g.get("inventory"), g.get("supply"), *g.get("structure", [])) if c],
                excluded=[dict(code=s["code"], name=s["name"],
                               reason="数据已过期" if s["stale"] else "历史不足 3 年，只参与动量")
                          for s in core if s not in reliable])


def _sig(level, title, text, codes, sector=None):
    return dict(level=level, title=title, text=text, codes=codes, sector=sector)


def _stale_note(s):
    return f"（{s['name']}数据截至 {s['latest_date']}，滞后 {s['lag_days']} 天，仅供参考）" if s["stale"] else ""


def group_signals(g, gv, stats):
    out = []
    if gv["temp"] is not None and gv["temp"] >= 0.95:
        out.append(_sig("risk", f"{g['name']}处于极端高位",
                        f"{g['name']}核心价格平均处于历史第 {pct(gv['temp'])} 分位，接近历史最高区间，周期性回落的风险需要重视。",
                        gv["core"]))
    elif gv["temp"] is not None and gv["temp"] <= 0.05:
        out.append(_sig("positive", f"{g['name']}处于极端低位",
                        f"{g['name']}核心价格平均处于历史第 {pct(gv['temp'])} 分位，接近历史最低区间，可以开始留意企稳信号。",
                        gv["core"]))

    inv = stats.get(g.get("inventory"))
    if inv and inv["momentum"]["3M"] is not None and gv["m3"] is not None:
        ic, pm = inv["momentum"]["3M"], gv["m3"]
        note = _stale_note(inv)
        pair = f"近 3 个月{g['name']}价格 {signed(pm)}，{inv['name']} {signed(ic)}"
        if pm > TREND_BAND and ic < -10:
            out.append(_sig("positive", f"{g['name']}价涨库降", f"{pair}。价格上涨伴随去库，说明需求有支撑。{note}", [inv["code"]]))
        elif pm > TREND_BAND and ic > 10:
            out.append(_sig("risk", f"{g['name']}价涨库增", f"{pair}。价格上涨但库存在累积，上涨可能缺乏真实需求支撑。{note}", [inv["code"]]))
        elif pm < -TREND_BAND and ic > 10:
            out.append(_sig("risk", f"{g['name']}价跌库增", f"{pair}。价格下跌同时累库，需求在走弱。{note}", [inv["code"]]))
        elif pm < -TREND_BAND and ic < -10:
            out.append(_sig("watch", f"{g['name']}价跌库降", f"{pair}。价格下跌但库存在减少，下跌动能可能在衰减。{note}", [inv["code"]]))
        if inv["q"] is not None and inv["q"] < 0.15:
            out.append(_sig("watch", f"{inv['name']}处于历史低位",
                            f"{inv['name']}处于{inv['window']}第 {pct(inv['q'])} 分位，供应偏紧，供给端任何扰动都容易放大价格波动。{note}",
                            [inv["code"]]))
        elif inv["q"] is not None and inv["q"] > 0.85:
            out.append(_sig("info", f"{inv['name']}处于历史高位",
                            f"{inv['name']}处于{inv['window']}第 {pct(inv['q'])} 分位，供应宽松，对价格上行形成拖累。{note}",
                            [inv["code"]]))

    sup = stats.get(g.get("supply"))
    if sup and not sup["stale"] and sup["q"] is not None and sup["q"] >= 0.85:
        out.append(_sig("watch", f"{sup['name']}处于历史高位",
                        f"{sup['name']}处于{sup['window']}第 {pct(sup['q'])} 分位，近 3 个月 {signed(sup['momentum']['3M'])}。"
                        "供给充足会压制价格中枢，高油价可能刺激产量进一步释放。", [sup["code"]]))

    core = [stats[c] for c in gv["core"] if not stats[c]["stale"] and stats[c]["momentum"]["3M"] is not None]
    if len(core) >= 2:
        hi = max(core, key=lambda s: s["momentum"]["3M"])
        lo = min(core, key=lambda s: s["momentum"]["3M"])
        if hi["momentum"]["3M"] - lo["momentum"]["3M"] >= 10:
            out.append(_sig("info", f"{g['name']}内部走势分化",
                            f"近 3 个月{hi['name']} {signed(hi['momentum']['3M'])}，{lo['name']} {signed(lo['momentum']['3M'])}。"
                            "差距较大时，可能是品种差异、区域供需、汇率或运费在起作用，单看其中一个容易误判。",
                            [hi["code"], lo["code"]]))

    struct = [stats[c] for c in g.get("structure", []) if c in stats and not stats[c]["stale"]
              and stats[c]["momentum"]["3M"] is not None]
    if len(struct) >= 2:
        hi = max(struct, key=lambda s: s["momentum"]["3M"])
        lo = min(struct, key=lambda s: s["momentum"]["3M"])
        if hi["momentum"]["3M"] - lo["momentum"]["3M"] >= 20:
            reading = {"BCI": "大船主要运铁矿石，铁矿贸易相对更强", "BPI": "巴拿马型主要运煤炭和粮食，这类需求相对更强",
                       "BSI": "超灵便型跑小宗散货航线，零散需求相对更强"}.get(hi["code"], "")
            out.append(_sig("info", "干散货分船型分化",
                            f"近 3 个月{hi['name']} {signed(hi['momentum']['3M'])}，{lo['name']} {signed(lo['momentum']['3M'])}。{reading}。",
                            [hi["code"], lo["code"]]))
    return out


def align(a, b):
    bm = dict(b)
    common = [(d, v, bm[d]) for d, v in a if d in bm]
    return [c[0] for c in common], [c[1] for c in common], [c[2] for c in common]


def rolling_corr(xs, ys, window):
    """日收益率的滚动相关系数，返回与收益率等长的列表（前 window-1 个为 None）。"""
    out = [None] * len(xs)
    for i in range(window - 1, len(xs)):
        a, b = xs[i - window + 1:i + 1], ys[i - window + 1:i + 1]
        ma, mb = sum(a) / window, sum(b) / window
        cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        va = sum((x - ma) ** 2 for x in a)
        vb = sum((y - mb) ** 2 for y in b)
        out[i] = round(cov / math.sqrt(va * vb), 3) if va > 0 and vb > 0 else None
    return out


def compare_pair(points_a, points_b, role_a=None, role_b=None, window=60, horizon=60):
    """两序列按日期对齐：滚动相关 + 背离区间（近 horizon 个交易日涨跌方向相反且相差 10 个百分点以上）。"""
    dates, va, vb = align(clean(points_a, role_a)[0], clean(points_b, role_b)[0])
    if len(dates) < window + 2:
        return dict(dates=dates, a=va, b=vb, corr=[], divergence=[], latest_corr=None, ret_a=None, ret_b=None)
    ra = [math.log(va[i] / va[i - 1]) if va[i] > 0 and va[i - 1] > 0 else 0.0 for i in range(1, len(va))]
    rb = [math.log(vb[i] / vb[i - 1]) if vb[i] > 0 and vb[i - 1] > 0 else 0.0 for i in range(1, len(vb))]
    corr = [None] + rolling_corr(ra, rb, window)
    flags = []
    for i in range(horizon, len(dates)):
        ca = (va[i] / va[i - horizon] - 1) * 100 if va[i - horizon] > 0 else 0
        cb = (vb[i] / vb[i - horizon] - 1) * 100 if vb[i - horizon] > 0 else 0
        if ca * cb < 0 and abs(ca - cb) >= 10:
            flags.append(i)
    # 相隔不超过 10 个交易日的合并，短于 5 个交易日的丢弃，避免图上碎片化
    runs = []
    for i in flags:
        if runs and i - runs[-1][1] <= 10:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    spans = [[dates[s], dates[e]] for s, e in runs if e - s >= 4]
    ret = lambda v: round((v[-1] / v[-1 - horizon] - 1) * 100, 1) if v[-1 - horizon] > 0 else None
    return dict(dates=dates, a=va, b=vb, corr=corr, divergence=spans,
                latest_corr=next((c for c in reversed(corr) if c is not None), None),
                ret_a=ret(va), ret_b=ret(vb), horizon=horizon, window=window)


def equity_signals(sector_cfg, stats, points):
    eq = sector_cfg.get("equity")
    if not eq or eq["code"] not in points or eq["vs"] not in points:
        return [], None
    s_eq, s_c = stats[eq["code"]], stats[eq["vs"]]
    if s_eq["stale"] or s_c["stale"]:
        return [], None
    cp = compare_pair(points[eq["vs"]], points[eq["code"]], s_c["role"], s_eq["role"])
    summary = dict(commodity=s_c["name"], equity=s_eq["name"], ret_commodity=cp["ret_a"], ret_equity=cp["ret_b"],
                   corr=cp["latest_corr"], horizon=cp.get("horizon"), codes=[eq["vs"], eq["code"]])
    out = []
    rc, re_, corr = cp["ret_a"], cp["ret_b"], cp["latest_corr"]
    if rc is not None and re_ is not None:
        pair = f"近 60 个交易日{s_c['name']} {signed(rc)}，{s_eq['name']} {signed(re_)}"
        if rc > 5 and re_ < -5:
            out.append(_sig("risk", "股商背离：商品涨、股票跌",
                            f"{pair}。股票往往领先商品反映预期，这可能说明市场在怀疑涨价的持续性。", summary["codes"]))
        elif re_ - rc <= -10:
            out.append(_sig("risk", "板块股票明显跑输商品",
                            f"{pair}，相差 {abs(re_ - rc):.1f} 个百分点。商品价格没有传导到股价，"
                            "可能是市场认为当前价格难以持续，或者板块受到商品以外的利空。", summary["codes"]))
        elif rc < -5 and re_ > 5:
            out.append(_sig("watch", "股商背离：股票先于商品走强",
                            f"{pair}。股票可能在提前反映周期好转，可以留意商品价格是否跟随企稳。", summary["codes"]))
        elif re_ - rc >= 10:
            out.append(_sig("watch", "板块股票明显跑赢商品",
                            f"{pair}，相差 {re_ - rc:.1f} 个百分点。股价可能在提前反映商品的预期好转，留意商品是否跟上。",
                            summary["codes"]))
    if corr is not None and corr < 0.2:
        out.append(_sig("info", "股票与商品走势脱钩",
                        f"{s_c['name']}与{s_eq['name']}近 60 个交易日的日收益相关系数只有 {corr:.2f}，"
                        "板块股价当前更多受商品以外的因素驱动。", summary["codes"]))
    return out, summary


def _sector_m3(groups):
    """板块趋势：各分组 3 个月动量截断到 ±30% 后平均，避免单个分组的暴涨暴跌主导方向判断。"""
    return _mean(None if g["m3"] is None else max(-30.0, min(30.0, g["m3"])) for g in groups)


def sector_view(key, cfg, stats, prev_stats, points):
    groups = [group_view(g, stats) for g in cfg["groups"]]
    temp = _mean(g["temp"] for g in groups)
    m3 = _sector_m3(groups)
    stage = stage_of(temp, m3)
    prev_groups = [group_view(g, prev_stats) for g in cfg["groups"]]
    prev_temp = _mean(g["temp"] for g in prev_groups)
    prev_m3 = _sector_m3(prev_groups)
    prev_stage = stage_of(prev_temp, prev_m3)
    # 温度在阈值附近小幅波动造成的阶段跳变不算变化
    stage_changed = (prev_stage != stage and "数据不足" not in (prev_stage, stage)
                     and (abs(temp - prev_temp) >= 0.05 or trend_of(m3) != trend_of(prev_m3)))

    signals = []
    for g, gv in zip(cfg["groups"], groups):
        signals += group_signals(g, gv, stats)
    eq_sigs, equity = equity_signals(cfg, stats, points)
    signals += eq_sigs
    if stage_changed:
        signals.insert(0, _sig("info", f"阶段变化：{prev_stage} → {stage}",
                               f"与一个月前相比，{cfg['name']}的周期阶段从「{prev_stage}」变为「{stage}」"
                               f"（温度 {round(prev_temp * 100)} → {round(temp * 100)}）。", []))
    for s in signals:
        s["sector"] = key
    signals.sort(key=lambda s: LEVEL_PRIORITY[s["level"]])

    members = [stats[s["code"]] for s in SERIES if s["sector"] == key and s["code"] in stats]
    info = STAGES.get(stage, {})
    return dict(
        key=key, name=cfg["name"], brief=cfg["brief"],
        temp=None if temp is None else round(temp * 100), m3=None if m3 is None else round(m3, 1),
        trend=trend_of(m3), stage=stage, stage_meaning=info.get("meaning", ""), hint=info.get("hint", ""),
        tone=info.get("tone", "flat"), order=info.get("order"),
        prev_temp=None if prev_temp is None else round(prev_temp * 100), prev_stage=prev_stage,
        stage_changed=stage_changed,
        groups=[dict(g, temp=None if g["temp"] is None else round(g["temp"] * 100),
                     m3=None if g["m3"] is None else round(g["m3"], 1)) for g in groups],
        signals=signals, equity=equity, members=members,
        last_date=max((m["latest_date"] for m in members if not m["stale"]), default=None),
    )


def headline(sectors):
    ranked = sorted((s for s in sectors.values() if s["temp"] is not None), key=lambda s: -s["temp"])
    if not ranked:
        return "暂无足够数据形成结论。"
    parts = [f"{s['name']}（温度 {s['temp']}，{s['stage']}）" for s in ranked]
    text = "按周期温度由高到低：" + "、".join(parts) + "。"
    changes = [f"{s['name']}由「{s['prev_stage']}」转为「{s['stage']}」" for s in ranked if s["stage_changed"]]
    if changes:
        text += "过去一个月，" + "；".join(changes) + "。"
    risks = sum(1 for s in ranked for x in s["signals"] if x["level"] == "risk")
    if risks:
        text += f"当前共有 {risks} 条风险信号，详见下方。"
    return text


def health(stats, failed):
    rows = []
    for cfg in SERIES:
        s = stats.get(cfg["code"])
        issue = []
        if s is None:
            issue.append("暂无数据")
        else:
            if cfg["archive"]:
                issue.append("历史档案")
            elif s["stale"]:
                issue.append(f"滞后 {s['lag_days']} 天")
            if not s["reliable"]:
                issue.append(f"历史仅 {s['span_years']} 年")
            if s["outliers"]:
                issue.append(f"剔除坏点 {len(s['outliers'])} 个")
        rows.append(dict(code=cfg["code"], name=cfg["name"], sector=cfg["sector"], role=cfg["role"],
                         source=cfg["source"], freq=cfg["freq"], note=NOTES.get(cfg["code"], ""),
                         first_date=s and s["first_date"], latest_date=s and s["latest_date"],
                         lag_days=s and s["lag_days"], points=s and s["points"], stale=bool(s and s["stale"]),
                         archive=cfg["archive"], outliers=s["outliers"] if s else [],
                         status="ok" if not issue else "warn" if s else "missing", issues=issue))
    active = [r for r in rows if not r["archive"]]
    return dict(rows=rows, fresh=sum(1 for r in active if r["latest_date"] and not r["stale"]),
                total=len(active), failed=failed,
                stale=[r for r in active if r["stale"] or not r["latest_date"]])


# ---------------- 快照与缓存 ----------------

_cache = dict(key=None, data=None)
_lock = threading.Lock()


def _compute():
    import json
    today = date.today()
    month_ago = today - timedelta(days=30)
    points = db.load_all_points()
    stats, prev = {}, {}
    for cfg in SERIES:
        pts = points.get(cfg["code"])
        if not pts:
            continue
        stats[cfg["code"]] = series_stats(cfg, pts, today)
        p = series_stats(cfg, pts, month_ago, asof=month_ago.isoformat())
        if p:
            prev[cfg["code"]] = p
    sectors = {k: sector_view(k, c, stats, prev, points) for k, c in SECTORS.items() if k}
    highlights = sorted((s for sec in sectors.values() for s in sec["signals"]),
                        key=lambda s: LEVEL_PRIORITY[s["level"]])[:6]
    failed = json.loads(db.get_meta("last_refresh_failed", "[]") or "[]")
    return dict(today=today.isoformat(), points=points, stats=stats, sectors=sectors,
                headline=headline(sectors), highlights=highlights, health=health(stats, failed))


def snapshot():
    """按数据版本号缓存（每次更新结束时写入），刷新进行中不会反复重算。"""
    key = (db.get_meta("data_version"), date.today().isoformat())
    with _lock:
        if _cache["key"] != key:
            _cache["data"] = _compute()
            _cache["key"] = key
        return _cache["data"]

# -*- coding: utf-8 -*-
"""分析引擎：分位数、动量、周期阶段判定、板块评分卡。

口径说明（页面上同步展示）:
- 分位数: 当前值在近 10 年（历史不足 10 年则用全历史）中的百分位排名
- 动量: 区间涨跌幅（1M/3M/6M/1Y）
- 阶段: 分位数 × 动量 的规则映射（六阶段）
- 板块评分: 核心品种 score = 60×分位 + 40×动量分，板块取核心品种均值
"""
import math
from datetime import datetime

from . import db
from .config import SECTOR_CORE, SECTORS


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct_rank(value, history):
    """value 在 history(升序 list[float]) 中的百分位，0~1。"""
    if not history:
        return None
    below = sum(1 for x in history if x <= value)
    return below / len(history)


def _level_label(q):
    if q is None:
        return "—"
    if q < 0.10:
        return "极低位"
    if q < 0.25:
        return "低位"
    if q < 0.50:
        return "中低位"
    if q < 0.75:
        return "中高位"
    if q < 0.90:
        return "高位"
    return "极高位"


def _momentum(series_dates_values, days):
    """days 天前的价格到现在 的涨跌幅（%）。用最接近目标的交易日。"""
    if len(series_dates_values) < 2:
        return None
    latest_d, latest_v = series_dates_values[-1]
    latest_dt = datetime.strptime(latest_d, "%Y-%m-%d")
    target = latest_dt
    for d, v in reversed(series_dates_values):
        dt = datetime.strptime(d, "%Y-%m-%d")
        if (latest_dt - dt).days >= days:
            target = dt
            break
    else:
        return None  # 历史不足
    base = None
    for d, v in series_dates_values:
        if d == target.strftime("%Y-%m-%d"):
            base = v
            break
    if not base or base == 0:
        return None
    return round((latest_v / base - 1) * 100, 1)


def series_stats(code):
    """单指标完整统计。"""
    rows = db.get_points(code)
    data = [(d, v) for d, v in rows if v is not None]
    if not data:
        return None
    values = [v for _, v in data]
    latest_d, latest_v = data[-1]

    # 近10年窗口（历史不足 10 年则用全历史）
    import datetime as dtmod
    latest_dt = dtmod.datetime.strptime(latest_d, "%Y-%m-%d")
    ten_years_ago = (latest_dt - dtmod.timedelta(days=3650)).strftime("%Y-%m-%d")
    win10 = [v for d, v in data if d >= ten_years_ago]

    q10 = _pct_rank(latest_v, sorted(win10)) if len(win10) >= 60 else None
    q_full = _pct_rank(latest_v, sorted(values))

    mom = {}
    for label, days in (("1M", 30), ("3M", 91), ("6M", 182), ("1Y", 365)):
        mom[label] = _momentum(data, days)

    # 分位通道线（近10年）
    def _pct_line(p):
        if len(win10) < 30:
            return None
        s = sorted(win10)
        idx = min(int(p * (len(s) - 1)), len(s) - 1)
        return round(s[idx], 2)

    channel = {"p10": _pct_line(0.10), "p25": _pct_line(0.25), "p50": _pct_line(0.50),
               "p75": _pct_line(0.75), "p90": _pct_line(0.90)}

    m3 = mom.get("3M")
    stage, score = _stage_score(q10, m3)

    # 分位窗口如实标注：历史不足 10 年的序列显示实际窗口
    first_d = data[0][0]
    span_days = (latest_dt - datetime.strptime(first_d, "%Y-%m-%d")).days
    window_label = "近10年" if span_days >= 3300 else f"近{max(1, round(span_days / 365))}年"

    return dict(
        code=code, latest_date=latest_d, latest=latest_v,
        q10y=round(q10, 3) if q10 is not None else None,
        q10y_label=_level_label(q10), q_full=round(q_full, 3),
        q_window=window_label,
        momentum=mom, stage=stage, score=score, channel=channel,
    )


def _stage_score(q, m3):
    """(阶段, 评分 0-100)。q=近10年分位, m3=3个月涨跌幅%。"""
    if q is None:
        return "数据不足", None
    # 动量分：3M 涨跌幅映射到 0-100（±20% 满量程截断）
    if m3 is None:
        m_score = 50.0
    else:
        m_score = max(0.0, min(100.0, 50 + m3 * 2.5))
    score = round(0.6 * (q * 100) + 0.4 * m_score)

    if q >= 0.90 and m3 is not None and m3 < 0:
        stage = "高位回落"
    elif q >= 0.80:
        stage = "高位强势"
    elif q >= 0.60 and m3 is not None and m3 > 0:
        stage = "上行中段"
    elif q < 0.10 and m3 is not None and m3 < 0:
        stage = "低位寻底"
    elif q < 0.25 and m3 is not None and m3 > 0:
        stage = "低位回升"
    else:
        stage = "中位震荡"
    return stage, score


def sector_overview():
    """三板块总览：评分 + 阶段 + 核心指标 + 各指标统计。"""
    result = {}
    for sector, sname in SECTORS.items():
        members, core_stats = [], []
        for s in db.all_series_meta():
            if s["sector"] != sector:
                continue
            st = series_stats(s["code"])
            if st is None:
                continue
            st["name"], st["unit"] = s["name"], s["unit"]
            members.append(st)
            if s["code"] in SECTOR_CORE.get(sector, []):
                core_stats.append(st)

        if core_stats:
            scores = [c["score"] for c in core_stats if c["score"] is not None]
            score = round(sum(scores) / len(scores)) if scores else None
            # 板块阶段取核心品种阶段众数
            from collections import Counter
            stages = Counter(c["stage"] for c in core_stats if c["stage"] != "数据不足")
            stage = stages.most_common(1)[0][0] if stages else "数据不足"
        else:
            score, stage = None, "数据不足"

        # 最新更新时间
        last_dates = [m["latest_date"] for m in members] or [None]
        result[sector] = dict(
            name=sname, score=score, stage=stage,
            last_date=max(last_dates), members=members,
        )
    return result

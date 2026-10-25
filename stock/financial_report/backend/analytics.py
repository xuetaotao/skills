# -*- coding: utf-8 -*-
"""分析引擎：把数据库里的原始财报字段整理成卡片、对比表、个股详情和自动结论。

约定：
- 财务数据都是“报告期累计”口径（一季报 = 1–3 月，中报 = 1–6 月……）。同比、ROE 只和上年同一报告期比。
- 流量指标（营收、净利润等）可拆成单季：本期累计 − 同年上一期累计。
- 结论分四级：risk 风险 / watch 留意 / positive 积极 / info 提示。
- 区间涨跌幅按复权价计算（含现金分红和送转），同时给出不复权的纯股价变化。
"""
import bisect
import calendar
import math
import statistics
import threading
from datetime import date, datetime, timedelta

from . import db
from .config import (KEY_METRICS, METRIC_MAP, METRICS, NATURES, NEW_DAYS, ORG_TYPES, PERF_PERIODS, PERIODS, TYPE_NAMES,
                     VAL_FOCUS, VALUATION_START, nature_class)

LEVEL_ORDER = {"risk": 0, "watch": 1, "positive": 2, "info": 3}
_cache = {"key": None, "snap": None}
_lock = threading.Lock()


def num(v, d=4):
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return round(v, d) if math.isfinite(v) else None


def type_of(org_type):
    return ORG_TYPES.get(org_type or "", "general")


def metrics_for(t):
    return [m for m in METRICS if t in m["types"]]


def value(row, key):
    """按指标单位换算后的数值：亿 = 元 ÷ 1e8；scale 用于把小数换成百分数。"""
    if not row:
        return None
    m = METRIC_MAP[key]
    v = num(row.get(key), 8)
    if v is None:
        return None
    if m["unit"] == "亿":
        v /= 1e8
    return v * m["scale"]


# ---------- 报告期 ----------

def period_name(d):
    return f"{d[:4]}{PERIODS[d[5:]][0]}"


def same_period_last_year(d):
    return f"{int(d[:4]) - 1}{d[4:]}"


def prev_period(d):
    y, md = int(d[:4]), d[5:]
    order = list(PERIODS)
    i = order.index(md)
    return f"{y - 1}-12-31" if i == 0 else f"{y}-{order[i - 1]}"


def next_period(d):
    y, md = int(d[:4]), d[5:]
    order = list(PERIODS)
    i = order.index(md)
    return f"{y + 1}-03-31" if i == 3 else f"{y}-{order[i + 1]}"


def deadline(d):
    """法定披露截止日：一季报 4-30、中报 8-31、三季报 10-31、年报次年 4-30。"""
    y, md = int(d[:4]), d[5:]
    return f"{y + 1 if md == '12-31' else y}-{PERIODS[md][1]}"


def single_quarter(rows, key):
    """{报告期: 单季值}。一季报的单季就是累计值；缺少同年上一期时无法拆分。"""
    by = {r["REPORT_DATE"][:10]: value(r, key) for r in rows}
    out = {}
    for d, v in by.items():
        if v is None:
            continue
        if d[5:] == "03-31":
            out[d] = v
        else:
            p = by.get(prev_period(d))
            if p is not None:
                out[d] = v - p
    return out


# ---------- 汇总一只股票 ----------

def _median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def _rank(v, values, better):
    """名次（1 = 最好）与样本数；better=None 时按从大到小。"""
    vals = [x for x in values if x is not None]
    if v is None or not vals:
        return None, len(vals)
    if better == "low":
        return 1 + sum(1 for x in vals if x < v), len(vals)
    return 1 + sum(1 for x in vals if x > v), len(vals)


def _stale(anchor, day):
    """年度分红从报告期末到下一次除息常常超过 18 个月（如 2021 年报的分红 2022 年 7 月中旬才除息），按 2 年判断。"""
    return anchor < (date.fromisoformat(day) - timedelta(days=730)).isoformat()


def ttm_dps(divs, day):
    """day 当天已知的最近四个季度每股派现（元）与其最近的报告期：最近一次已除息分红所属报告期往前一年内的合计。

    按报告期而不是除息日统计：一年分两次的公司（如工行的中期 + 年度分红），除息日可能在 12 个月里出现三次。
    最近一次分红的报告期距 day 超过 2 年时视为近期没有分红。
    从只分年度改为一年分两次的那一年（如工行 2024 年起加了中期分红），窗口会同时含上一年的全年分红和今年的中期分红，
    上一年上半年被算了两次；这时只发年度分红的那一年按窗口覆盖的月份折算，但合计不低于那一年的全年分红
    （中期分红占比各家差别很大：工行约一半，长江电力约两成，单纯按月份折算会低估后者）。
    """
    done = [d for d in divs if d.get("ex_date") and d["ex_date"] <= day and "实施" in (d.get("progress") or "")]
    if not done:
        return 0.0, None
    anchor = max(d["report_date"] for d in done)
    if _stale(anchor, day):
        return 0.0, anchor
    start = f"{int(anchor[:4]) - 1}{anchor[4:]}"
    total = floor = 0.0
    for d in done:
        rd = d["report_date"]
        if not start < rd <= anchor:
            continue
        v = d["per10"] / 10
        if rd[5:] == "12-31" and rd[:4] == start[:4] and not any(x["report_date"][:4] == rd[:4] and x["report_date"] < rd for x in done):
            floor = v
            v *= (12 - int(start[5:7])) / 12
        total += v
    return max(total, floor), anchor


def dividend_ttm(divs, close, trade_date):
    """股息率 TTM（%）= 最近四个季度每股派现 ÷ 最新收盘价；返回 (股息率, 每股派现)。"""
    if not close or not trade_date:
        return None, 0.0
    per_share, _ = ttm_dps(divs, trade_date)
    return (per_share / close * 100 if per_share else None), per_share


def dividend_history(divs, prices):
    """每个交易日的股息率 TTM（%）[(日期, 股息率)]：当天已知的最近四个季度每股派现 ÷ 当天收盘价，没有分红时为 0。"""
    exs = sorted({d["ex_date"] for d in divs if d.get("ex_date")})
    cache, out = {}, []
    for day, close in prices:
        i = bisect.bisect_right(exs, day)
        if i not in cache:  # 两个除息日之间已知的分红不变
            cache[i] = ttm_dps(divs, exs[i - 1]) if i else (0.0, None)
        ps, anchor = cache[i]
        if anchor and _stale(anchor, day):
            ps = 0.0
        out.append((day, ps / close * 100 if close else 0.0))
    return out


def _dist(vals, cur):
    """当前值在历史里的位置：分位（历史上不高于当前值的比例）、中位数、最低、最高。"""
    r2 = lambda v: num(v, 2) + 0.0  # 去掉 -0.0
    return dict(pct=num(sum(1 for x in vals if x <= cur) / len(vals), 4), median=r2(statistics.median(vals)),
                low=r2(min(vals)), high=r2(max(vals)))


def dividend_stats(hist, dy_now, bonds):
    """股息率与股债利差（股息率 − 10 年期国债收益率）在近几年里的位置。分位越高，股价相对分红越便宜。

    当前没有分红（股息率为空）时不算分位：大量 0 值会让“0%”看起来处于高位。
    """
    if len(hist) < 250:
        return None
    cur = dy_now or 0.0
    out = dict(since=hist[0][0], cur=num(cur, 2), **(_dist([v for _, v in hist], cur) if cur else {}))
    if bonds:
        bdates = [b[0] for b in bonds]
        y10 = bonds[-1][1]
        out.update(y10=num(y10, 4), y10_date=bonds[-1][0], spread=num(cur - y10, 2) if cur else None)
        spreads = [v - bonds[i][1] for d, v in hist if (i := bisect.bisect_right(bdates, d) - 1) >= 0]
        if cur and len(spreads) >= 250:
            s = _dist(spreads, cur - y10)
            out.update(spread_pct=s["pct"], spread_median=s["median"], spread_low=s["low"], spread_high=s["high"])
    return out


DIV_VOID = ("否决", "停止", "终止", "取消", "未通过")


def annual_dividends(divs, by_date):
    """按财年汇总分红：每股分红 = 该财年各报告期（中期、三季度、年度）的派现合计，含已公告、尚未实施的预案；
    分红率 = 每股分红 ÷ 基本每股收益。财年没有年报时 done=False（当年还没结束，或年报未披露）。"""
    years = {}
    for d in divs:
        prog = d.get("progress") or ""
        if any(w in prog for w in DIV_VOID):
            continue
        y = years.setdefault(d["report_date"][:4], dict(dps=0.0, plan=False))
        y["dps"] += d["per10"] / 10
        y["plan"] |= "实施" not in prog
    for d in by_date:
        if d[5:] == "12-31":
            years.setdefault(d[:4], dict(dps=0.0, plan=False))
    out = []
    for y in sorted(years):
        row = by_date.get(f"{y}-12-31")
        eps = num(row.get("EPSJB"), 4) if row else None
        dps = years[y]["dps"]
        out.append(dict(year=y, dps=num(dps, 4), eps=eps, done=row is not None, plan=years[y]["plan"],
                        payout=num(dps / eps * 100, 1) if eps and eps > 0 else None))
    return out


def dividend_summary(annual):
    """最近一个完整财年的分红率、连续分红年数（到最早有数据的年份为止时 more=True）、每股分红 1 年和 3 年变化。"""
    done = [a for a in annual if a["done"]]
    if not done:
        return {}
    last = done[-1]
    years = 0
    for a in reversed(done):
        if not a["dps"]:
            break
        years += 1
    by = {a["year"]: a["dps"] for a in done}
    prev, base = by.get(str(int(last["year"]) - 1)), by.get(str(int(last["year"]) - 3))
    return dict(year=last["year"], payout=last["payout"], dps=last["dps"], eps=last["eps"], plan=last["plan"],
                years=years, more=years == len(done),
                chg1=num((last["dps"] / prev - 1) * 100, 1) if prev and last["dps"] else None,
                cagr3=num(((last["dps"] / base) ** (1 / 3) - 1) * 100, 1) if base and last["dps"] else None)


def valuation_stats(rows):
    """估值历史 → 当前值、分位（历史上不高于当前值的比例）、中位数。PE 只统计正值。"""
    out = {}
    for i, k in ((2, "pe"), (3, "pb")):
        hist = [r[i] for r in rows if r[i] is not None and r[i] > 0]
        if len(hist) < 250:
            out[k] = None
            continue
        cur = rows[-1][i]
        pct = None if cur is None or cur <= 0 else sum(1 for x in hist if x <= cur) / len(hist)
        out[k] = dict(cur=num(cur, 3), pct=num(pct, 4), median=num(statistics.median(hist), 3),
                      low=num(min(hist), 3), high=num(max(hist), 3), since=rows[0][0])
    return out


def months_back(d, n):
    y, m = divmod(d.year * 12 + d.month - 1 - n, 12)
    return date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


def price_perf(prices, factors, listing=None):
    """区间涨跌幅（%）。终点是最后一个交易日，起点是回看日当天或之前最近的交易日（今年以来 = 上年最后一个交易日）。

    ret：复权价之比 − 1，复权价 = 收盘价 × 当日适用的后复权因子，相当于分红在除息日再投入，即持有期总收益；
    raw：不复权的纯股价变化；ann：两年及以上区间的年化收益。上市晚于回看日时为空。没有复权因子时整体为空。
    """
    if not prices or not factors:
        return None
    dates = [p[0] for p in prices]
    fdates = [f[0] for f in factors]

    def adj(i):
        j = bisect.bisect_right(fdates, dates[i]) - 1
        return prices[i][1] * factors[max(j, 0)][1]

    end = date.fromisoformat(dates[-1])
    out = {}
    for key, _, n in PERF_PERIODS:
        target = (end - timedelta(days=7) if n < 0 else date(end.year - 1, 12, 31) if n == 0 else months_back(end, n)).isoformat()
        i = bisect.bisect_right(dates, target) - 1
        if i < 0 or (listing and listing > target):
            out[key] = None
            continue
        r = adj(len(dates) - 1) / adj(i) - 1
        out[key] = dict(ret=num(r * 100, 2), raw=num((prices[-1][1] / prices[i][1] - 1) * 100, 2), base=dates[i],
                        ann=num(((1 + r) ** (12 / n) - 1) * 100, 2) if n >= 24 and r > -1 else None)
    return dict(asof=dates[-1], periods=out)


def adj_closes(prices, factors):
    """后复权收盘价：分红、送转不会让价格断崖，均线、高低点和回撤才前后可比。没有复权因子时用原始收盘价。"""
    if not factors:
        return [p[1] for p in prices]
    fdates = [f[0] for f in factors]
    return [px * factors[max(bisect.bisect_right(fdates, d) - 1, 0)][1] for d, px in prices]


def _rsi(xs, n=14):
    """RSI（Wilder 平滑）：近期上涨幅度占涨跌总幅度的比例，0–100。"""
    gain = loss = 0.0
    for i in range(1, len(xs)):
        ch = xs[i] - xs[i - 1]
        g, l = max(ch, 0.0), max(-ch, 0.0)
        if i <= n:
            gain += g / n
            loss += l / n
        else:
            gain = (gain * (n - 1) + g) / n
            loss = (loss * (n - 1) + l) / n
    return 100.0 if not loss else 100 - 100 / (1 + gain / loss)


def tech_state(prices, factors):
    """股价技术面。只有日收盘价（没有成交量和日内高低价），所以只看收盘价能判断的：
    均线趋势（20 / 60 / 250 日，250 日即年线）、最近 10 个交易日是否穿越年线、一年内高低点与回撤、近一周涨跌、14 日 RSI。

    trend：up = 收盘价在年线上方且 20 日 > 60 日 > 年线（多头排列）；down = 反过来（空头排列）；其余 range（震荡）。
    """
    if not prices or len(prices) < 260:
        return None
    a = adj_closes(prices, factors)
    n = len(a)
    ma = lambda k, end=n: sum(a[end - k:end]) / k
    cur, m20, m60, m250 = a[-1], ma(20), ma(60), ma(250)
    trend = ("up" if cur > m250 and m20 > m60 > m250 else "down" if cur < m250 and m20 < m60 < m250 else "range")
    # 穿越年线：现在在年线哪一侧，10 个交易日前在另一侧；离年线不足 1% 的不算（贴着年线来回波动）
    dev = cur / m250 - 1
    was = a[-11] / ma(250, n - 10) - 1
    cross = "up" if dev >= 0.01 and was < 0 else "down" if dev <= -0.01 and was > 0 else None
    year = a[-250:]
    hi, lo = max(year), min(year)
    hi_ago = 249 - year.index(hi)
    lo_ago = 249 - year.index(lo)
    return dict(asof=prices[-1][0], trend=trend, cross=cross,
                ma20=num((cur / m20 - 1) * 100, 2), ma60=num((cur / m60 - 1) * 100, 2), ma250=num(dev * 100, 2),
                dd=num((cur / hi - 1) * 100, 2), hi_ago=hi_ago, up_low=num((cur / lo - 1) * 100, 2), lo_ago=lo_ago,
                new_high=hi_ago <= 4, new_low=lo_ago <= 4,
                w1=num((a[-1] / a[-6] - 1) * 100, 2), m1=num((a[-1] / a[-21] - 1) * 100, 2), rsi=num(_rsi(a[-120:]), 1))


TREND_NAMES = {"up": "上升", "down": "下降", "range": "震荡"}


class Snapshot:
    def __init__(self):
        self.today = date.today().isoformat()
        self.watch = db.watchlist()
        self.stocks = db.load_stocks()
        self.reports = db.load_reports()
        self.quotes = db.load_quotes()
        self.divs = db.load_dividends()
        self.groups = db.get_json("groups", {})
        self.stock_group = db.get_json("stock_group", {})
        self.trade_date = db.get_meta("trade_date")
        self.by_date = {c: {r["REPORT_DATE"][:10]: r for r in rows} for c, rows in self.reports.items()}
        self.sub = {}
        for g in self.groups.values():
            for c, s in g["sub"].items():
                self.sub.setdefault(c, s)
        self.group_of = {}
        for k, g in self.groups.items():
            for c in g["members"]:
                self.group_of.setdefault(c, k)
        self.group_of.update(self.stock_group)
        self.val = {c: db.load_valuation(c) for c in self.watch}
        self.factors = factors = db.load_factors()
        self.prices = db.load_prices()
        self.perf = {c: price_perf(p, factors.get(c), (self.stocks.get(c) or {}).get("listing_date"))
                     for c, p in self.prices.items()}
        self._tech = {}
        self.bonds = db.load_bond_yields()
        self.dy_hist = {c: dividend_history(self.divs.get(c, []), p) for c, p in self.prices.items()}
        self.divinfo = {c: self.dividend_info(c) for c in set(self.reports) | set(self.prices)}
        self.cards = {c: self.card(c) for c in self.watch if c in self.reports}

    # ----- 基本信息 -----
    def name(self, c):
        return (self.stocks.get(c) or {}).get("name") or (self.quotes.get(c) or {}).get("name") or c

    def type(self, c):
        return type_of((self.stocks.get(c) or {}).get("org_type"))

    def group(self, c):
        return self.groups.get(self.group_of.get(c))

    def row(self, c, d):
        return self.by_date.get(c, {}).get(d)

    def latest(self, c):
        rows = self.reports.get(c)
        return rows[-1] if rows else None

    def market(self, c):
        q = self.quotes.get(c) or {}
        dy, dps = dividend_ttm(self.divs.get(c, []), q.get("close"), q.get("trade_date"))
        return dict(close=num(q.get("close"), 3), change=num(q.get("change"), 2), trade_date=q.get("trade_date"),
                    mcap=num((q.get("mcap") or 0) / 1e8, 1) if q.get("mcap") else None,
                    pe=num(q.get("pe_ttm"), 2), pb=num(q.get("pb"), 3), dy=num(dy, 2), dps=num(dps, 4))

    def dividend_info(self, c):
        """股息率的历史位置、股债利差、按财年的分红汇总（个股页另取 annual 明细）。"""
        annual = annual_dividends(self.divs.get(c, []), self.by_date.get(c, {}))
        return dict(stats=dividend_stats(self.dy_hist.get(c) or [], self.market(c)["dy"], self.bonds),
                    summary=dividend_summary(annual), annual=annual)

    def div_brief(self, c):
        x = self.divinfo.get(c) or {}
        return dict(stats=x.get("stats"), summary=x.get("summary") or {})

    def tech(self, c):
        if c not in self._tech:
            self._tech[c] = tech_state(self.prices.get(c), self.factors.get(c))
        return self._tech[c]

    def nature(self, c):
        s = self.stocks.get(c) or {}
        cls = nature_class(s.get("nature"))
        return cls and dict(cls=cls, name=NATURES[cls], raw=s.get("nature"), controller=s.get("controller"),
                            real=s.get("real_controller"))

    def info(self, c):
        g = self.group(c)
        t = self.type(c)
        return dict(code=c, name=self.name(c), type=t, type_name=TYPE_NAMES[t], watched=c in self.watch,
                    group=g and dict(key=self.group_of.get(c), name=g["name"], path=g["path"], size=len(g["members"])),
                    sub=self.sub.get(c), nature=self.nature(c))

    def perf_detail(self, c):
        """个股页：各区间涨跌幅 + 同行业中位数与排名（涨得多排前面）。"""
        p = self.perf.get(c)
        if not p:
            return None
        g = self.group(c)
        members = [self.perf.get(m) for m in g["members"]] if g else []
        out = []
        for key, label, _ in PERF_PERIODS:
            x = p["periods"].get(key)
            vals = [m["periods"][key]["ret"] for m in members if m and m["periods"].get(key)]
            r, n = _rank(x and x["ret"], vals, "high")
            out.append(dict(key=key, label=label, **(x or {}), median=num(_median(vals), 2), rank=r, n=n))
        return dict(asof=p["asof"], periods=out)

    # ----- 同行业统计 -----
    def peer_values(self, c, d, key):
        g = self.group(c)
        if not g:
            return []
        return [value(self.row(m, d), key) for m in g["members"]]

    def peer_rank(self, c, d, key):
        vals = self.peer_values(c, d, key)
        r, n = _rank(value(self.row(c, d), key), vals, METRIC_MAP[key]["better"])
        return dict(rank=r, n=n, median=num(_median(vals), 4)) if r else None

    # ----- 卡片 -----
    def metric_brief(self, c, d, key):
        row = self.row(c, d)
        return dict(key=key, value=num(value(row, key), 4), ly=num(value(self.row(c, same_period_last_year(d)), key), 4),
                    prev=num(value(self.row(c, prev_period(d)), key), 4), peer=self.peer_rank(c, d, key))

    def card(self, c):
        latest = self.latest(c)
        d = latest["REPORT_DATE"][:10]
        t = self.type(c)
        notice = (latest.get("NOTICE_DATE") or "")[:10] or None
        nxt = next_period(d)
        val = valuation_stats(self.val.get(c) or [])
        focus = VAL_FOCUS[t]
        sig = self.signals(c, d, val, focus)
        return dict(self.info(c), period=dict(date=d, name=period_name(d), notice=notice,
                                              new=bool(notice and (date.fromisoformat(self.today) - date.fromisoformat(notice)).days <= NEW_DAYS)),
                    next=dict(date=nxt, name=period_name(nxt), deadline=deadline(nxt), due=self.today > nxt),
                    metrics=[self.metric_brief(c, d, k) for k in KEY_METRICS[t]],
                    market=self.market(c), val=val, focus=focus, signals=sig, oneoff=self.oneoff(c, d),
                    div=self.div_brief(c), tech=self.tech(c), insight=self.insight(c, d, sig, val, focus))

    # ----- 一次性损益 -----
    def oneoff(self, c, d):
        """归母净利与扣非净利的增速相差 10 个百分点以上、且某一期非经常性损益占归母净利 10% 以上时，说明增速被一次性因素扭曲。

        kind = base：归母净利下降，但扣非好得多（上年同期一次性收益大，如资产处置、坏账转回；或本期一次性损失大）；
        kind = inflated：归母增速明显好于扣非（本期一次性收益大，或上年同期一次性损失大）。"""
        row, row_ly = self.row(c, d), self.row(c, same_period_last_year(d))
        g, gk = value(row, "PARENTNETPROFITTZ"), value(row, "KCFJCXSYJLRTZ")
        p, k = value(row, "PARENTNETPROFIT"), value(row, "KCFJCXSYJLR")
        p_ly, k_ly = value(row_ly, "PARENTNETPROFIT"), value(row_ly, "KCFJCXSYJLR")
        if None in (g, gk, p, k, p_ly, k_ly) or not p or not p_ly:
            return None
        nr, nr_ly = p - k, p_ly - k_ly
        if max(abs(nr) / abs(p), abs(nr_ly) / abs(p_ly)) < 0.1:
            return None
        kind = None
        if g < 0 and gk - g >= 10 and nr_ly > nr:
            kind = "base"
        elif g - gk >= 10 and nr > nr_ly:
            kind = "inflated"
        if not kind:
            return None
        return dict(kind=kind, g=num(g, 2), gk=num(gk, 2), nr=num(nr, 2), nr_ly=num(nr_ly, 2),
                    share=num(nr / abs(p) * 100, 0), share_ly=num(nr_ly / abs(p_ly) * 100, 0))

    # ----- 自动结论 -----
    def signals(self, c, d, val, focus):
        t = self.type(c)
        out = []
        cur = lambda k: value(self.row(c, d), k)
        ly = lambda k: value(self.row(c, same_period_last_year(d)), k)
        prev = lambda k: value(self.row(c, prev_period(d)), k)
        pname = period_name(d)
        sec = {"cat": "财报"}  # 类别：财报 / 估值 / 股息 / 股价 / 技术 / 行业 / 披露，按所在段落设置

        def add(level, title, text, key=None, cat=None):
            out.append(dict(level=level, title=title, text=text, metric=key, cat=cat or sec["cat"]))

        # 利润增长：增速被一次性损益扭曲时，改按扣非净利判断
        g, gp = cur("PARENTNETPROFITTZ"), prev("PARENTNETPROFITTZ")
        oo = self.oneoff(c, d)
        if oo:
            gk = oo["gk"]
            why = (f"{pname}归母净利同比 {g:+.2f}%，扣非净利同比 {gk:+.2f}%。非经常性损益：上年同期 {oo['nr_ly']:.2f} 亿"
                   f"（占当期归母净利 {oo['share_ly']:.0f}%），本期 {oo['nr']:.2f} 亿（占 {oo['share']:.0f}%）。")
            lv = "risk" if gk < -10 else "watch"
            if oo["kind"] == "base" and gk >= 0:
                add("info", "归母净利下降主要受一次性损益影响", why + "剔除一次性因素后主业利润仍在增长。", "KCFJCXSYJLRTZ")
            elif oo["kind"] == "base":
                add(lv, "扣非净利同比下降", why + "剔除一次性因素后降幅小一些，但主业利润确实在下滑。", "KCFJCXSYJLRTZ")
            elif gk >= 0:
                add("info", "利润增速含一次性收益", why + "归母增速被一次性因素抬高，扣非口径更能代表主业。", "KCFJCXSYJLRTZ")
            elif g >= 0:
                add(lv, "利润增长主要来自一次性收益", why + "剔除一次性因素后主业利润在下滑，这部分收益通常不可持续。", "KCFJCXSYJLRTZ")
            else:
                add(lv, "扣非净利降幅更大", why + "一次性收益掩盖了一部分主业下滑。", "KCFJCXSYJLRTZ")
        elif g is not None:
            if g < 0 and gp is not None and gp >= 0:
                add("risk" if g <= -5 else "watch", "归母净利同比转负", f"{pname}归母净利同比 {g:+.2f}%，上一期还是 {gp:+.2f}%。",
                    "PARENTNETPROFITTZ")
            elif g < 0:
                add("risk" if g < -10 else "watch", "归母净利同比下降", f"{pname}归母净利同比 {g:+.2f}%。", "PARENTNETPROFITTZ")
            elif gp is not None and gp < 0:
                add("positive", "归母净利同比转正", f"{pname}归母净利同比 {g:+.2f}%，上一期为 {gp:+.2f}%。", "PARENTNETPROFITTZ")
            elif gp is not None and g - gp >= 5:
                add("positive", "利润增速加快", f"归母净利同比从上一期的 {gp:+.2f}% 提高到 {g:+.2f}%。", "PARENTNETPROFITTZ")
            elif gp is not None and gp - g >= 5:
                add("watch", "利润增速放缓", f"归母净利同比从上一期的 {gp:+.2f}% 降到 {g:+.2f}%。", "PARENTNETPROFITTZ")
        q = cur("DJD_DPNP_YOY")
        if d[5:] != "03-31" and q is not None and q < 0 and (g or 0) >= 0:
            add("watch", "最新单季利润下滑", f"{pname}累计归母净利同比为正，但最新一个季度同比 {q:+.2f}%。", "DJD_DPNP_YOY")
        r = cur("TOTALOPERATEREVETZ")
        if r is not None and r < 0:
            add("watch", "营收同比下降", f"{pname}营业总收入同比 {r:+.2f}%。", "TOTALOPERATEREVETZ")

        # ROE（同一报告期比较，相对变化超过 10% 才提示）
        roe, roe_ly = cur("ROEJQ"), ly("ROEJQ")
        if roe is not None and roe_ly not in (None, 0) and abs(roe - roe_ly) / abs(roe_ly) >= 0.1:
            up = roe > roe_ly
            text = f"{pname} ROE {roe:.2f}%，上年同期 {roe_ly:.2f}%（{roe - roe_ly:+.2f} 个百分点）。"
            if oo and ((oo["kind"] == "base" and not up) or (oo["kind"] == "inflated" and up)):
                add("info", f"ROE {'提升' if up else '下降'}（受一次性损益影响）",
                    text + ("上年同期含一次性收益，基数偏高。" if not up else "本期含一次性收益，不代表盈利能力改善。"), "ROEJQ")
            else:
                add("positive" if up else "watch", f"ROE {'提升' if up else '下降'}", text, "ROEJQ")

        if t == "general":
            gm, gm_ly = cur("XSMLL"), ly("XSMLL")
            if gm is not None and gm_ly is not None and abs(gm - gm_ly) >= 2:
                up = gm > gm_ly
                add("positive" if up else "watch", f"毛利率{'提升' if up else '下滑'}",
                    f"毛利率 {gm:.2f}%，上年同期 {gm_ly:.2f}%（{gm - gm_ly:+.2f} 个百分点）。", "XSMLL")
            cf, np_ = cur("NCO_NETPROFIT"), cur("PARENTNETPROFIT")
            if d[5:] != "03-31" and cf is not None and np_ and np_ > 0 and cf < 0.5:
                add("watch", "利润的现金含量偏低", f"经营现金流只有净利润的 {cf:.2f} 倍，利润里有较多应收或存货等尚未收回的部分。",
                    "NCO_NETPROFIT")
            dr, dr_ly = cur("ZCFZL"), ly("ZCFZL")
            if dr is not None and dr_ly is not None and dr > 70 and dr - dr_ly >= 3:
                add("watch", "负债率偏高且在上升", f"资产负债率 {dr:.1f}%，比上年同期高 {dr - dr_ly:.1f} 个百分点。", "ZCFZL")

        if t == "bank":
            npl, npl_ly = cur("NONPERLOAN"), ly("NONPERLOAN")
            if npl is not None and npl_ly is not None:
                bp = round((npl - npl_ly) * 100)
                if bp >= 5:
                    add("watch", "不良率上升", f"不良贷款率 {npl:.2f}%，比上年同期高 {bp} 个基点。", "NONPERLOAN")
                elif bp <= -3:
                    add("positive", "不良率下降", f"不良贷款率 {npl:.2f}%，比上年同期低 {-bp} 个基点。", "NONPERLOAN")
            cov, cov_ly = cur("BLDKBBL"), ly("BLDKBBL")
            if cov is not None and cov < 150:
                add("risk", "拨备覆盖率偏低", f"拨备覆盖率 {cov:.1f}%，低于 150% 的常见监管参考线，抵御坏账的缓冲较薄。", "BLDKBBL")
            elif cov is not None and cov_ly is not None and abs(cov - cov_ly) >= 15:
                up = cov > cov_ly
                add("positive" if up else "watch", f"拨备覆盖率{'提高' if up else '下降'}",
                    f"拨备覆盖率 {cov:.1f}%，上年同期 {cov_ly:.1f}%。{'' if up else '拨备在被消耗，或在用拨备释放利润。'}", "BLDKBBL")
            nim, nim_ly = cur("NET_INTEREST_MARGIN"), ly("NET_INTEREST_MARGIN")
            if nim is not None and nim_ly is not None:
                bp = round((nim - nim_ly) * 100)
                if bp <= -10:
                    add("watch", "净息差收窄", f"净息差 {nim:.2f}%，比上年同期低 {-bp} 个基点。", "NET_INTEREST_MARGIN")
                elif bp >= 3:
                    add("positive", "净息差回升", f"净息差 {nim:.2f}%，比上年同期高 {bp} 个基点。", "NET_INTEREST_MARGIN")
                elif abs(bp) <= 2:
                    add("info", "净息差基本持平", f"净息差 {nim:.2f}%，上年同期 {nim_ly:.2f}%。", "NET_INTEREST_MARGIN")
            cet1 = cur("HXYJBCZL")
            if cet1 is not None and cet1 < 9:
                add("watch", "核心一级资本偏紧", f"核心一级资本充足率 {cet1:.2f}%，离监管底线（系统重要性银行约 8%–8.5%）不远，"
                                          "扩张或分红可能受限。", "HXYJBCZL")

        if t == "insurance":
            nbv, nbv_ly = cur("NBV_LIFE"), ly("NBV_LIFE")
            if nbv and nbv_ly:
                chg = (nbv / nbv_ly - 1) * 100
                if abs(chg) >= 10:
                    add("positive" if chg > 0 else "watch", f"新业务价值{'增长' if chg > 0 else '下降'}",
                        f"寿险新业务价值 {nbv:.1f} 亿，同比 {chg:+.1f}%。", "NBV_LIFE")
            sol = cur("SOLVENCY_AR")
            if sol is not None and sol < 150:
                add("watch", "偿付能力偏低", f"综合偿付能力充足率 {sol:.1f}%。", "SOLVENCY_AR")

        if t == "broker":
            rc = cur("RISK_COVERAGE")
            if rc is not None and rc < 130:
                add("watch", "风险覆盖率偏低", f"风险覆盖率 {rc:.1f}%（监管预警线 120%）。", "RISK_COVERAGE")

        # 估值与股息：估值分位和股息率分位指向同一方向时合并成一条
        sec["cat"] = "估值"
        mk = self.market(c)
        dv = self.divinfo.get(c) or {}
        ds, sm = dv.get("stats") or {}, dv.get("summary") or {}
        dpct = ds.get("pct")
        dy_pos = f"股息率 {ds['cur']:.2f}%，处于 {ds['since'][:4]} 年以来的 {dpct * 100:.0f}% 分位（中位数 {ds['median']:.2f}%）。" if dpct is not None else ""
        v = val.get(focus) if val else None
        label = "市净率" if focus == "pb" else "市盈率"
        if v and v["pct"] is not None:
            pos = f"{label} {v['cur']:.2f}，处于 {v['since'][:4]} 年以来的 {v['pct'] * 100:.0f}% 分位（中位数 {v['median']:.2f}）。"
            if v["pct"] <= 0.2:
                both = dpct is not None and dpct >= 0.8
                add("positive", "估值处于历史低位" + ("，股息率处于高位" if both else ""), pos + (dy_pos if both else ""))
                dpct = None if both else dpct
            elif v["pct"] >= 0.8:
                both = dpct is not None and dpct <= 0.2
                add("watch", "估值处于历史高位" + ("，股息率处于低位" if both else ""), pos + (dy_pos if both else ""))
                dpct = None if both else dpct
        sec["cat"] = "股息"
        vs_bond = f"，比 10 年期国债收益率（{ds['y10']:.2f}%）高 {ds['spread']:.2f} 个百分点" if ds.get("spread") is not None else ""
        if mk["dy"] and mk["dy"] >= 5:
            add("positive", "股息率较高", f"股息率 {mk['dy']:.2f}%（最近四个季度每股派现 {mk['dps']:.3f} 元 ÷ 最新股价）{vs_bond}。")
        if dpct is not None and dpct >= 0.8:
            add("positive", "股息率处于近年高位", dy_pos + "相对分红，股价比过去多数时候便宜；前提是分红能维持。")
        elif dpct is not None and dpct <= 0.2:
            add("watch", "股息率处于近年低位", dy_pos + "相对分红，股价比过去多数时候贵。")
        if sm.get("payout") is not None and sm["payout"] > 100:
            add("watch", "分红超过当年利润", f"{sm['year']} 年每股分红 {sm['dps']:.3f} 元，基本每股收益 {sm['eps']:.3f} 元，分红率 {sm['payout']:.0f}%，"
                                    "靠留存利润或借款分红难以长期维持。")
        elif sm.get("dps") and sm.get("eps") is not None and sm["eps"] <= 0:
            add("watch", "亏损年度仍在分红", f"{sm['year']} 年基本每股收益 {sm['eps']:.3f} 元，每股分红 {sm['dps']:.3f} 元。")
        if sm.get("chg1") is not None and sm["chg1"] <= -10:
            add("watch", "每股分红减少", f"{sm['year']} 年每股分红 {sm['dps']:.3f} 元，比上一年少 {-sm['chg1']:.0f}%（送转、增发会摊薄每股金额，可对照分红总额判断）。")
        elif sm and not sm.get("dps") and any(a["dps"] for a in dv["annual"] if a["done"] and a["year"] < sm["year"]):
            add("watch", "上一财年没有分红", f"{sm['year']} 年没有现金分红（或方案尚未公告），之前的年份有分红。")

        self.price_signals(c, add)

        # 同行业位置
        sec["cat"] = "行业"
        g = self.group(c)
        if g and len(g["members"]) >= 5:
            growth = ("KCFJCXSYJLRTZ", "扣非净利增速") if oo else ("PARENTNETPROFITTZ", "归母净利增速")
            for key, label in (("ROEJQ", "ROE"), growth):
                if key == "ROEJQ" and oo and oo["kind"] == "inflated":
                    continue
                pr = self.peer_rank(c, d, key)
                if pr and pr["n"] >= 5:
                    if pr["rank"] <= max(1, round(pr["n"] * 0.2)):
                        add("positive", f"{label}行业前列", f"{pname}{label}在{g['name']} {pr['n']} 家中排第 {pr['rank']}。", key)
                    elif pr["rank"] > pr["n"] - max(1, round(pr["n"] * 0.2)):
                        add("watch", f"{label}行业靠后", f"{pname}{label}在{g['name']} {pr['n']} 家中排第 {pr['rank']}。", key)

        # 披露
        sec["cat"] = "披露"
        latest = self.latest(c)
        notice = (latest.get("NOTICE_DATE") or "")[:10]
        if notice and (date.fromisoformat(self.today) - date.fromisoformat(notice)).days <= NEW_DAYS:
            add("info", f"新披露 {pname}", f"{notice} 披露。")
        nxt = next_period(d)
        if self.today > nxt:
            dl = deadline(nxt)
            add("info", f"{period_name(nxt)}待披露", f"法定截止日 {dl}{'，已逾期' if self.today > dl else ''}。")
        out.sort(key=lambda s: LEVEL_ORDER[s["level"]])
        return out

    def price_signals(self, c, add):
        """股价与技术面结论，都按后复权收盘价（含分红）计算。"""
        t = self.tech(c)
        if not t:
            return
        w1, dd = t["w1"], t["dd"]
        if w1 <= -8:
            add("risk" if w1 <= -15 else "watch", "近一周大跌", f"近 5 个交易日下跌 {-w1:.1f}%，先看有没有公告、财报或行业消息。", cat="股价")
        elif w1 >= 12:
            add("watch", "近一周涨幅较大", f"近 5 个交易日上涨 {w1:.1f}%，短期追高的风险变大。", cat="股价")
        if t["new_low"]:
            add("risk" if dd <= -30 else "watch", "股价创一年新低", f"收盘价接近近一年最低，较一年内高点回撤 {-dd:.1f}%。", cat="股价")
        elif dd <= -20:
            add("risk" if dd <= -30 else "watch", "较一年高点回撤较大",
                f"较一年内高点（{t['hi_ago']} 个交易日前）回撤 {-dd:.1f}%，比一年内低点高 {t['up_low']:.1f}%。", cat="股价")
        elif t["new_high"]:
            add("positive", "股价创一年新高", f"收盘价接近近一年最高，比一年内低点高 {t['up_low']:.1f}%。", cat="股价")
        g, p = self.group(c), self.perf_detail(c)
        m3 = next((x for x in p["periods"] if x["key"] == "m3"), None) if p and g else None
        if m3 and m3.get("ret") is not None and m3.get("median") is not None and m3["n"] >= 5:
            diff = m3["ret"] - m3["median"]
            if abs(diff) >= 15:
                add("positive" if diff > 0 else "watch", f"近 3 个月明显{'跑赢' if diff > 0 else '跑输'}同行",
                    f"近 3 个月涨跌 {m3['ret']:+.1f}%，{g['name']}中位数 {m3['median']:+.1f}%，相差 {diff:+.1f} 个百分点"
                    f"（{m3['n']} 家中排第 {m3['rank']}）。", cat="股价")

        pos = f"收盘价{'高于' if t['ma250'] >= 0 else '低于'}年线 {abs(t['ma250']):.1f}%"
        if t["cross"] == "up":
            add("positive", "股价站上年线", f"最近两周从年线下方回到上方，{pos}。年线（250 日均线）常被看作中期强弱的分界，还要看之后几周能否站稳。", cat="技术")
        elif t["cross"] == "down":
            add("watch", "股价跌破年线", f"最近两周跌到年线下方，{pos}。中期走势转弱，几周内收不回来的话下跌可能延续。", cat="技术")
        if t["ma250"] >= 30:
            add("watch", "股价远高于年线", f"{pos}，涨得较急，回落到均线附近的可能性变大。", cat="技术")
        if t["rsi"] >= 75:
            add("watch", "短期超买", f"14 日 RSI {t['rsi']:.0f}（≥75），短期涨势过急，容易回调或横盘。", cat="技术")
        elif t["rsi"] <= 25:
            add("positive", "短期超卖", f"14 日 RSI {t['rsi']:.0f}（≤25），短期跌得过急，常有技术性反弹，但不代表趋势反转。", cat="技术")

    def insight(self, c, d, sig, val, focus):
        """综合判断：把估值、股息、财报和股价走势放在一起，给一句结论（kind = risk / chance）；没有明确组合时返回 None。
        规则按顺序匹配第一条：便宜但业绩或分红走弱（价值陷阱）→ 高估值配业绩下滑 → 业绩和股价一起走弱 → 业绩下滑而股价向上
        → 估值高位或股息率低位、股价又很强（创新高、超买、远离年线、一周急涨）→ 便宜且趋势向上 → 便宜但仍在下跌
        → 业绩改善而股价走弱 → 业绩和股价共振 → 便宜、无明显趋势。"""
        t = self.tech(c) or {}
        mk = self.market(c)
        ds = (self.divinfo.get(c) or {}).get("stats") or {}
        v = (val or {}).get(focus)
        label = "市净率" if focus == "pb" else "市盈率"
        vpct = v["pct"] if v and v["pct"] is not None else None
        cheap = []
        if vpct is not None and vpct <= 0.2:
            cheap.append(f"{label}处于近年 {vpct * 100:.0f}% 分位")
        if mk["dy"] and (mk["dy"] >= 5 or (ds.get("pct") or 0) >= 0.8):
            cheap.append(f"股息率 {mk['dy']:.2f}%" + (f"（近 5 年 {ds['pct'] * 100:.0f}% 分位）" if ds.get("pct") is not None else ""))
        cheap = "，".join(cheap)
        pricey = vpct is not None and vpct >= 0.8
        dear = "，".join(x for x in (pricey and f"{label}处于近年 {vpct * 100:.0f}% 分位",
                                    mk["dy"] and ds.get("pct") is not None and ds["pct"] <= 0.2 and f"股息率降到近 5 年 {ds['pct'] * 100:.0f}% 分位（{mk['dy']:.2f}%）") if x)

        oo = self.oneoff(c, d)
        gname, g = ("扣非净利", oo["gk"]) if oo else ("归母净利", value(self.row(c, d), "PARENTNETPROFITTZ"))
        gtxt = f"{period_name(d)}{gname}同比 {g:+.1f}%" if g is not None else ""
        fin_risk = [s["title"] for s in sig if s["cat"] == "财报" and s["level"] == "risk"]
        fin_bad = (gtxt if g is not None and g <= -10 else
                   f"{period_name(d)}{fin_risk[0]}（{g:+.1f}%）" if fin_risk and g is not None and "净利" in fin_risk[0]
                   else fin_risk[0] if fin_risk else "")
        fin_good = not fin_bad and g is not None and g >= 10
        fin_ok = ("财报没有明显风险" if g is None else f"业绩小幅下滑（{gtxt}）" if g < 0
                  else f"业绩平稳（{gtxt}）" if g < 10 else f"业绩增长（{gtxt}）")
        div_bad = [s["title"] for s in sig if s["cat"] == "股息" and s["title"] in ("分红超过当年利润", "亏损年度仍在分红", "每股分红减少", "上一财年没有分红")]

        trend, dd = t.get("trend"), t.get("dd")
        weak = trend == "down" or (dd is not None and dd <= -20)
        tparts = []
        if t:
            if trend != "range":
                tparts.append(f"股价处于{TREND_NAMES[trend]}趋势")
            tparts.append(f"收盘价{'高于' if t['ma250'] >= 0 else '低于'}年线 {abs(t['ma250']):.1f}%")
            if dd <= -20:
                tparts.append(f"较一年高点回撤 {-dd:.1f}%")
        ttxt = "，".join(tparts)
        hot = "、".join(x for x in (t and t["new_high"] and "股价创一年新高",
                                    t and t["rsi"] >= 75 and f"14 日 RSI {t['rsi']:.0f}",
                                    t and t["ma250"] >= 30 and f"高于年线 {t['ma250']:.1f}%",
                                    t and t["w1"] >= 12 and f"近一周涨 {t['w1']:.1f}%") if x)

        risk = lambda text: dict(kind="risk", text=text)
        chance = lambda text: dict(kind="chance", text=text)
        if cheap and (fin_bad or div_bad):
            why = "、".join(([fin_bad] if fin_bad else []) + div_bad)
            return risk(f"看起来便宜（{cheap}），但{why}：低估值可能是市场在提前反映业绩或分红下滑，小心价值陷阱，先确认利润能否企稳。")
        if pricey and fin_bad:
            return risk(f"{label}处于近年 {vpct * 100:.0f}% 分位的高位，但{fin_bad}：估值和业绩背离，回调风险较大。")
        if fin_bad and weak and ttxt:
            return risk(f"{fin_bad}，同时{ttxt}：业绩和股价一起走弱，风险信号一致。")
        if fin_bad and trend == "up":
            return risk(f"{fin_bad}，但{ttxt}：股价和业绩背离，上涨更多来自市场或行业情绪，后续财报不改善的话持续性存疑。")
        if dear and hot:
            return risk(f"{dear}，{hot}：涨多之后估值或股息率已不便宜，追高的性价比下降，更适合等回调。")
        if cheap and trend == "up":
            return chance(f"{cheap}，{fin_ok}，{ttxt}：估值有吸引力，股价趋势也向上，几方面没有明显矛盾。")
        if cheap and weak and ttxt:
            return chance(f"{cheap}，{fin_ok}，但{ttxt}：可以分批关注，不必急于一次买入，等股价止跌企稳更稳妥。")
        if fin_good and weak and ttxt:
            return chance(f"{gtxt}，但{ttxt}：下跌不是财报的原因，可能来自市场或行业情绪，值得跟踪。")
        if fin_good and trend == "up" and not pricey:
            return chance(f"{gtxt}，{ttxt}：业绩和股价共振向上。")
        if cheap:
            return chance(f"{cheap}，{fin_ok}{f'，{ttxt}，股价没有明显趋势' if ttxt else ''}：适合耐心观察。")
        return None

    # ----- 总览结论 -----
    def headline(self):
        cards = [self.cards[c] for c in self.watch if c in self.cards]
        if not cards:
            return dict(text="还没有自选股。在上方搜索框输入代码或名称添加。", bullets=[])
        latest_dates = [x["period"]["date"] for x in cards]
        common = max(set(latest_dates), key=lambda d: (latest_dates.count(d), d))
        newest = max(latest_dates)
        n = len(cards)
        parts = [f"{n} 只自选股的最新财报以{period_name(common)}为主（{latest_dates.count(common)}/{n}）"]
        if newest > common:
            done = [x["name"] for x in cards if x["period"]["date"] == newest]
            parts.append(f"{period_name(newest)}已披露 {len(done)} 只（{'、'.join(done[:3])}{' 等' if len(done) > 3 else ''}），"
                         f"其余法定截止日 {deadline(newest)}")
        grow = [(x["name"], value(self.row(x["code"], common), "PARENTNETPROFITTZ"), self.oneoff(x["code"], common)) for x in cards]
        grow = [x for x in grow if x[1] is not None]
        bullets = []
        if grow:
            up = sum(1 for _, g, _ in grow if g > 0)
            parts.append(f"{period_name(common)}归母净利同比增长 {up} 只、下降 {len(grow) - up} 只")
            note = lambda x: f"（扣非 {x[2]['gk']:+.2f}%，受一次性损益影响）" if x[2] else ""
            best, worst = max(grow, key=lambda x: x[1]), min(grow, key=lambda x: x[1])
            if len(grow) > 1:
                bullets.append(f"利润增速最快：{best[0]} {best[1]:+.2f}%{note(best)}；最慢：{worst[0]} {worst[1]:+.2f}%{note(worst)}。")
            distorted = [x for x in grow if x[2] and (len(grow) < 2 or x not in (best, worst))]
            if distorted:
                bullets.append("归母净利增速受一次性损益扭曲：" + "、".join(
                    f"{nm} 归母 {g:+.2f}% / 扣非 {oo['gk']:+.2f}%" for nm, g, oo in distorted) + "，按扣非净利判断更准确。")
        risky = [x["name"] for x in cards if any(s["level"] == "risk" for s in x["signals"])]
        if risky:
            bullets.append(f"有风险信号：{'、'.join(risky)}，点进个股详情页的“风险与机会”查看具体原因。")
        cheap = [x["name"] for x in cards if (x["val"].get(x["focus"]) or {}).get("pct") is not None
                 and x["val"][x["focus"]]["pct"] <= 0.2]
        if cheap:
            bullets.append(f"估值处于 {VALUATION_START[:4]} 年以来低位（≤20% 分位）：{'、'.join(cheap)}。")
        dys = sorted(((x["name"], x["market"]["dy"]) for x in cards if x["market"]["dy"]), key=lambda x: -x[1])
        if dys:
            bond = f"（10 年期国债 {self.bonds[-1][1]:.2f}%）" if self.bonds else ""
            bullets.append(f"股息率最高：{'、'.join(f'{nm} {v:.2f}%' for nm, v in dys[:3])}{bond}。")
        high = [x["name"] for x in cards if ((x["div"]["stats"] or {}).get("pct") or 0) >= 0.8]
        if high:
            bullets.append(f"股息率处于近 5 年高位（≥80% 分位）：{'、'.join(high)}。")
        newly = [f"{x['name']}（{x['period']['name']}）" for x in cards if x["period"]["new"]]
        if newly:
            bullets.append(f"近 {NEW_DAYS} 天新披露：{'、'.join(newly)}。")
        return dict(text="；".join(parts) + "。", bullets=bullets, common=common)

    # ----- 横向对比 -----
    def scope_codes(self, scope):
        if scope == "watch":
            return [c for c in self.watch if c in self.reports], None
        g = self.groups.get(scope)
        if not g:
            return None, None
        return [c for c in g["members"] if c in self.reports], g

    def compare(self, scope, period=None):
        codes, g = self.scope_codes(scope)
        if codes is None:
            return None
        counts = {}
        for c in codes:
            for d in self.by_date.get(c, {}):
                counts[d] = counts.get(d, 0) + 1
        periods = sorted(counts, reverse=True)[:12]
        if not period or period not in counts:
            period = next((d for d in periods if counts[d] >= 0.7 * len(codes)), periods[0] if periods else None)
        types = sorted({self.type(c) for c in codes}, key=lambda t: list(TYPE_NAMES).index(t))
        if len(types) == 1:
            keys = [m["key"] for m in metrics_for(types[0])]
        else:  # 跨类型：各类公司共有的指标 + 每类的核心指标
            key_set = {k for t in types for k in KEY_METRICS[t]}
            keys = [m["key"] for m in METRICS if set(types) <= set(m["types"]) or m["key"] in key_set]
        rows = []
        for c in codes:
            row = self.row(c, period)
            rows.append(dict(self.info(c), market=self.market(c), has=row is not None,
                             notice=(row.get("NOTICE_DATE") or "")[:10] if row else None,
                             values={k: num(value(row, k), 4) for k in keys},
                             perf=(self.perf.get(c) or {}).get("periods") or {}, div=self.div_brief(c)))
        med = {k: num(_median([r["values"][k] for r in rows if r["has"]]), 4) for k in keys}
        for k in ("pe", "pb", "dy", "mcap"):
            med[k] = num(_median([r["market"][k] for r in rows if r["market"][k] is not None and (k != "pe" or r["market"][k] > 0)]), 4)
        subs = []
        if g:
            subs = list(dict.fromkeys(g["sub"].get(c) for c in codes if g["sub"].get(c)))
        asof = [p["asof"] for p in (self.perf.get(c) for c in codes) if p]
        return dict(scope=scope, group=g and dict(name=g["name"], path=g["path"], level=g["level"], total=g.get("total")),
                    perf_asof=max(asof) if asof else None, period=period, period_name=period and period_name(period),
                    periods=[dict(date=d, name=period_name(d), n=counts[d]) for d in periods], total=len(codes),
                    types=types, keys=keys, rows=rows, median=med, subs=subs, bond=self.bond())

    def bond(self):
        return dict(y10=num(self.bonds[-1][1], 4), date=self.bonds[-1][0]) if self.bonds else None

    def scopes(self):
        out = [dict(key="watch", name="自选股", n=len([c for c in self.watch if c in self.reports]))]
        for k, g in self.groups.items():
            mine = [self.name(c) for c in self.watch if self.group_of.get(c) == k]
            if mine:
                out.append(dict(key=k, name=g["name"], n=len(g["members"]), level=g["level"], mine=mine))
        return out

    # ----- 个股详情 -----
    def stock(self, c):
        if c not in self.reports:
            return None
        t = self.type(c)
        rows = self.reports[c]
        latest = rows[-1]
        d = latest["REPORT_DATE"][:10]
        val_rows = self.val.get(c) or []
        card = self.cards.get(c)
        if not card:
            val = {}
            sig = self.signals(c, d, val, VAL_FOCUS[t])
            card = dict(self.info(c), period=dict(date=d, name=period_name(d), notice=(latest.get("NOTICE_DATE") or "")[:10],
                                                  new=False),
                        next=dict(date=next_period(d), name=period_name(next_period(d)), deadline=deadline(next_period(d)),
                                  due=self.today > next_period(d)),
                        metrics=[self.metric_brief(c, d, k) for k in KEY_METRICS[t]], market=self.market(c), val=val,
                        focus=VAL_FOCUS[t], signals=sig, div=self.div_brief(c), tech=self.tech(c),
                        insight=self.insight(c, d, sig, val, VAL_FOCUS[t]))
        mets = metrics_for(t)
        dates = [r["REPORT_DATE"][:10] for r in rows]
        g = self.group(c)
        series = {}
        for m in mets:
            k = m["key"]
            s = dict(values=[num(value(r, k), 4) for r in rows])
            if m["flow"]:
                sq = single_quarter(rows, k)
                s["quarter"] = [num(sq.get(x), 4) for x in dates]
            if g:
                s["median"] = [num(_median(self.peer_values(c, x, k)), 4) for x in dates]
            series[k] = s
        divs = []
        close_on = dict(self.prices.get(c) or []) | {r[0]: r[1] for r in val_rows}
        for dv in reversed(self.divs.get(c, [])):
            px = close_on.get(dv["ex_date"]) if dv.get("ex_date") else None
            divs.append(dict(dv, dps=num(dv["per10"] / 10, 4), yield_at=num(dv["per10"] / 10 / px * 100, 2) if px else None))
        weekly = []
        for i, r in enumerate(val_rows):
            if i == len(val_rows) - 1 or date.fromisoformat(val_rows[i + 1][0]).isocalendar()[1] != date.fromisoformat(r[0]).isocalendar()[1]:
                weekly.append([r[0], num(r[1], 3), num(r[2], 3), num(r[3], 3)])
        peers = []
        if g:
            for m in g["members"]:
                if m == c:
                    continue
                q = self.quotes.get(m) or {}
                peers.append(dict(code=m, name=self.name(m), sub=g["sub"].get(m), mcap=num((q.get("mcap") or 0) / 1e8, 1)))
            peers.sort(key=lambda x: -(x["mcap"] or 0))
        return dict(card=card, keys=[m["key"] for m in mets], dates=dates, names=[period_name(x) for x in dates],
                    series=series, ranks={m["key"]: self.peer_rank(c, d, m["key"]) for m in mets}, perf=self.perf_detail(c),
                    valuation=dict(rows=weekly, stats=valuation_stats(val_rows)), dividends=divs, peers=peers[:30],
                    div=self.div_detail(c))

    def div_detail(self, c):
        """个股页：股息率与 10 年期国债收益率的周线（每周最后一个交易日）、同行业股息率中位数与排名、按财年的分红明细。"""
        x = self.divinfo.get(c) or {}
        hist = self.dy_hist.get(c) or []
        bdates = [b[0] for b in self.bonds]
        series = []
        for i, (d, v) in enumerate(hist):
            if i == len(hist) - 1 or date.fromisoformat(hist[i + 1][0]).isocalendar()[1] != date.fromisoformat(d).isocalendar()[1]:
                j = bisect.bisect_right(bdates, d) - 1
                series.append([d, num(v, 3), num(self.bonds[j][1], 4) if j >= 0 else None])
        g = self.group(c)
        vals = [self.market(m)["dy"] for m in g["members"]] if g else []
        r, n = _rank(self.market(c)["dy"], vals, "high")
        return dict(x, series=series, peer=dict(median=num(_median(vals), 2), rank=r, n=len([v for v in vals if v])))

    # ----- 数据健康 -----
    def health(self):
        status = db.get_json("fetch_status", {})
        codes = list(dict.fromkeys(self.watch + [c for g in self.groups.values() for c in g["members"]]))
        rows = []
        for c in codes:
            latest = self.latest(c)
            st = status.get(c, {})
            rows.append(dict(code=c, name=self.name(c), watched=c in self.watch, group=(self.group(c) or {}).get("name"),
                             type=TYPE_NAMES[self.type(c)], latest=latest and latest["REPORT_DATE"][:10],
                             latest_name=latest and period_name(latest["REPORT_DATE"][:10]),
                             notice=latest and (latest.get("NOTICE_DATE") or "")[:10],
                             periods=len(self.reports.get(c, [])), ok=st.get("ok"), error=st.get("error"), at=st.get("at"),
                             quote=(self.quotes.get(c) or {}).get("trade_date"), nature=self.nature(c),
                             perf=(self.perf.get(c) or {}).get("asof")))
        return dict(rows=rows, failed=db.get_json("last_refresh_failed", []), last_refresh=db.get_meta("last_refresh"),
                    trade_date=self.trade_date, sw_updated=db.get_meta("sw_updated"), bond=self.bond(),
                    groups=[dict(key=k, name=g["name"], level=g["level"], n=len(g["members"]), total=g.get("total"),
                                 path=g["path"]) for k, g in self.groups.items()])


def snapshot():
    key = (db.get_meta("data_version"), db.get_meta("watch_version"))
    with _lock:
        if _cache["key"] != key or _cache["snap"] is None:
            _cache["snap"] = Snapshot()
            _cache["key"] = key
        return _cache["snap"]


def reorder_watch(codes):
    """自选股只是换了顺序时，直接改缓存快照里的顺序；成员变了返回 False，由调用方让快照重建。"""
    with _lock:
        s = _cache["snap"]
        if s is None or set(codes) != set(s.watch):
            return False
        s.watch = list(codes)
        return True

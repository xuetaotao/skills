# -*- coding: utf-8 -*-
"""鱼盆信号与周度对比

鱼盆模型：收盘价在 20 日均线（临界值）之上为 YES、之下为 NO；偏离度 = (收盘价 − MA20) / MA20。
所有结果都可以按任意历史日期（asof）回看：均线只用当天及以前的数据，截断后重算的结果与当时一致。
"""
import math
import threading
from datetime import timedelta

import pandas as pd

from . import db
from .config import BIG_MOVE, BOND_TERMS, GAP_DAYS, GROUPS, INST, INSTRUMENTS, MA_PERIOD, MACRO, STALE_DAYS, WEEKS

_cache = {"ver": object()}
_lock = threading.Lock()


def _f(x, n=6):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else round(x, n)


def _ds(ts):
    return ts.strftime("%Y-%m-%d") if ts is not None else None


def signal_frame(s):
    df = pd.DataFrame({"close": s})
    df["ma"] = df["close"].rolling(MA_PERIOD).mean()
    df = df.dropna(subset=["ma"]).copy()
    df["dev"] = df["close"] / df["ma"] - 1
    df["yes"] = df["close"] > df["ma"]
    df["run"] = (df["yes"] != df["yes"].shift()).cumsum()
    return df


def _series(rows):
    return pd.Series([v for _, v in rows], index=pd.to_datetime([d for d, _ in rows]), dtype=float)


def data():
    """按数据版本缓存：{frames: {代码: 信号表}, raw: {代码: 收盘序列}, macro: {序列: Series}}"""
    ver = db.get_meta("data_version")
    with _lock:
        if _cache.get("ver") != ver:
            raw = {c: _series(r) for c, r in db.load_prices().items() if c in INST}
            _cache.clear()
            _cache.update(ver=ver, raw=raw, frames={c: signal_frame(s) for c, s in raw.items()},
                          macro={k: _series(r) for k, r in db.load_macro().items()}, views={})
        return _cache


def simple_codes():
    saved = db.get_json("simple_codes")
    if saved is None:
        return [c for c, *_rest in INSTRUMENTS if INST[c]["simple"]]
    return [c for c in saved if c in INST]


def _memo(key, fn):
    d = data()
    if key not in d["views"]:
        if len(d["views"]) > 64:
            d["views"].clear()
        d["views"][key] = fn()
    return d["views"][key]


# ---------------- 日期 ---------------- #

def data_date(asof=None):
    """整体数据日期：所有标的里最新的交易日（不超过 asof）。"""
    d = data()
    cut = pd.Timestamp(asof) if asof else None
    last = None
    for s in d["raw"].values():
        x = s.loc[:cut] if cut is not None else s
        if len(x) and (last is None or x.index[-1] > last):
            last = x.index[-1]
    return last


def week_start(ts):
    return (ts - timedelta(days=ts.weekday())).normalize()


def week_ends(n=52, asof=None):
    """最近 n 个自然周各自的最后一个交易日（所有标的合并），升序。"""
    d = data()
    D = data_date(asof)
    if D is None:
        return []
    idx = sorted(set().union(*[set(s.index) for s in d["raw"].values()]))
    idx = [t for t in idx if t <= D]
    ends = {}
    for t in idx:
        ends[week_start(t)] = t
    return [ends[k] for k in sorted(ends)][-n:]


# ---------------- 单个标的 ---------------- #

def _row(code, D):
    inst = INST[code]
    base = {k: inst[k] for k in ("code", "name", "region", "flag", "group", "kind", "order")}
    df = data()["frames"].get(code)
    d = df.loc[:D] if df is not None else None
    if d is None or d.empty:
        return {**base, "nodata": True}
    last, date = d.iloc[-1], d.index[-1]
    ws = week_start(D)
    prev = d.iloc[-2] if len(d) > 1 else None
    pw = d[d.index < ws]
    pwl = pw.iloc[-1] if len(pw) else None
    run = d[d["run"] == last["run"]]
    since = run.index[0]
    before = d[d.index < since]
    run_base = before["close"].iloc[-1] if len(before) else None
    m1 = d.loc[:D - pd.DateOffset(months=1), "close"]
    ytd = d.loc[:pd.Timestamp(D.year - 1, 12, 31), "close"]
    y1 = d.loc[D - timedelta(days=365):]
    flips_1y = int((y1["run"] != y1["run"].shift()).iloc[1:].sum()) if len(y1) > 1 else 0
    this_week = d.loc[ws:]
    wk_flips = []
    if len(this_week):
        seq = d.loc[(pw.index[-1] if len(pw) else ws):]
        ch = seq["yes"] != seq["yes"].shift()
        wk_flips = [dict(date=_ds(t), to="YES" if seq.at[t, "yes"] else "NO") for t in seq.index[1:] if ch.at[t]]
    ma5 = d["ma"].iloc[-6] if len(d) > 5 else None
    return {
        **base,
        "date": _ds(date),
        "price": _f(last["close"]),
        "ma": _f(last["ma"]),
        "dev": _f(last["dev"]),
        "status": "YES" if last["yes"] else "NO",
        "since": _ds(since),
        "days": int(len(run)),
        "run_ret": _f(last["close"] / run_base - 1) if run_base else None,
        "chg": _f(last["close"] / prev["close"] - 1) if prev is not None else None,
        "changed_today": bool(prev is not None and since == date),
        "wtd": _f(last["close"] / pwl["close"] - 1) if pwl is not None and date >= ws else None,
        "idle_week": bool(date < ws),
        "prev_status": ("YES" if pwl["yes"] else "NO") if pwl is not None else None,
        "prev_dev": _f(pwl["dev"]) if pwl is not None else None,
        "changed_week": bool(pwl is not None and bool(pwl["yes"]) != bool(last["yes"])),
        "week_flips": wk_flips,
        "m1": _f(last["close"] / m1.iloc[-1] - 1) if len(m1) else None,
        "ytd": _f(last["close"] / ytd.iloc[-1] - 1) if len(ytd) else None,
        "ma_slope": _f(last["ma"] / ma5 - 1) if ma5 else None,
        "flips_1y": flips_1y,
        "stale": (D - date).days > STALE_DAYS,
        "spark": [_f(x, 4) for x in d["dev"].iloc[-60:]],
    }


def rows(asof=None):
    def build():
        D = data_date(asof)
        if D is None:
            return None
        return dict(date=_ds(D), week_start=_ds(week_start(D)), rows=[_row(c, D) for c, *_ in INSTRUMENTS])
    return _memo(("rows", asof), build)


# ---------------- 宏观 ---------------- #

def _bp(a, b):
    return _f((a - b) * 100, 1) if a is not None and b is not None else None


def macro(asof=None, history=False):
    def build():
        d = data()
        D = data_date(asof)
        if D is None:
            return None
        ws = week_start(D)
        out = {"date": _ds(D)}
        s = d["macro"].get("DXY")
        if s is not None and len(s.loc[:D]):
            f = signal_frame(s.loc[:D])
            last = f.iloc[-1]
            pw = f[f.index < ws]
            m1 = f.loc[:D - pd.DateOffset(months=1), "close"]
            run = f[f["run"] == last["run"]]
            out["dxy"] = dict(
                date=_ds(f.index[-1]), price=_f(last["close"]), ma=_f(last["ma"]), dev=_f(last["dev"]),
                status="YES" if last["yes"] else "NO", since=_ds(run.index[0]),
                chg=_f(last["close"] / f["close"].iloc[-2] - 1) if len(f) > 1 else None,
                wtd=_f(last["close"] / pw["close"].iloc[-1] - 1) if len(pw) else None,
                m1=_f(last["close"] / m1.iloc[-1] - 1) if len(m1) else None,
                stale=(D - f.index[-1]).days > STALE_DAYS)
            if history:
                f = f.loc[D - timedelta(days=365 * 3):]
                out["dxy_hist"] = dict(dates=[_ds(t) for t in f.index], close=[_f(x, 3) for x in f["close"]],
                                       ma=[_f(x, 3) for x in f["ma"]])
        bonds = []
        latest = {}
        for term in BOND_TERMS:
            row = {"term": term}
            for p in ("CN", "US"):
                s = d["macro"].get(f"{p}{term}")
                s = s.loc[:D].dropna() if s is not None else None
                if s is None or not len(s):
                    continue
                v = s.iloc[-1]
                pw = s[s.index < ws]
                m1 = s.loc[:D - pd.DateOffset(months=1)]
                row[p.lower()] = _f(v, 4)
                row[f"{p.lower()}_date"] = _ds(s.index[-1])
                row[f"{p.lower()}_d1"] = _bp(v, s.iloc[-2]) if len(s) > 1 else None
                row[f"{p.lower()}_wtd"] = _bp(v, pw.iloc[-1]) if len(pw) else None
                row[f"{p.lower()}_m1"] = _bp(v, m1.iloc[-1]) if len(m1) else None
                latest[f"{p}{term}"] = v
            if "cn" in row and "us" in row:
                row["spread"] = _bp(row["cn"], row["us"])
            bonds.append(row)
        out["bonds"] = bonds
        out["bond_date"] = max([r.get("cn_date") or "" for r in bonds] + [r.get("us_date") or "" for r in bonds]) or None
        if "US10年" in latest and "US2年" in latest:
            out["us_curve"] = _bp(latest["US10年"], latest["US2年"])
        if "CN10年" in latest and "CN2年" in latest:
            out["cn_curve"] = _bp(latest["CN10年"], latest["CN2年"])
        if history:
            start = D - timedelta(days=365 * 3)
            hist = {}
            for k in MACRO:
                if k == "DXY" or k not in d["macro"]:
                    continue
                s = d["macro"][k].loc[start:D].dropna()
                hist[k] = [[_ds(t), _f(v, 4)] for t, v in s.items()]
            out["bond_hist"] = hist
        return out
    return _memo(("macro", asof, history), build)


# ---------------- 周度对比 ---------------- #

def weeks(n=WEEKS, asof=None):
    """最近 n 周每周最后一个交易日的状态、偏离度和周涨跌。"""
    def build():
        d = data()
        ends = week_ends(n + 1, asof)
        if not ends:
            return None
        cols = ends[1:] if len(ends) > n else ends
        out_rows = []
        for code, *_ in INSTRUMENTS:
            df = d["frames"].get(code)
            inst = INST[code]
            cells = []
            prev = None
            for i, end in enumerate(ends):
                x = df.loc[:end] if df is not None else None
                if x is None or x.empty:
                    cell = None
                else:
                    last = x.iloc[-1]
                    cell = dict(close=last["close"], dev=last["dev"], yes=bool(last["yes"]),
                                idle=bool(x.index[-1] < week_start(end)), date=_ds(x.index[-1]))
                if end in cols:
                    if cell is None:
                        cells.append(None)
                    else:
                        cells.append(dict(
                            dev=_f(cell["dev"]), status="YES" if cell["yes"] else "NO", idle=cell["idle"], date=cell["date"],
                            wret=_f(cell["close"] / prev["close"] - 1) if prev else None,
                            flip=bool(prev and prev["yes"] != cell["yes"])))
                prev = cell or prev
            out_rows.append({k: inst[k] for k in ("code", "name", "region", "flag", "group", "kind")} | {"cells": cells})
        macro_rows = []
        for key, label, unit in [("DXY", "美元指数", "pct"), ("US10年", "美国10年期国债", "bp"), ("CN10年", "中国10年期国债", "bp"),
                                 ("US2年", "美国2年期国债", "bp")]:
            s = d["macro"].get(key)
            if s is None:
                continue
            cells, prev = [], None
            for end in ends:
                x = s.loc[:end].dropna()
                v = x.iloc[-1] if len(x) else None
                if end in cols:
                    chg = None
                    if v is not None and prev is not None:
                        chg = _f(v / prev - 1) if unit == "pct" else _bp(v, prev)
                    cells.append(dict(value=_f(v, 4), chg=chg))
                prev = v if v is not None else prev
            macro_rows.append(dict(key=key, label=label, unit=unit, cells=cells))
        return dict(weeks=[dict(end=_ds(e), start=_ds(week_start(e))) for e in cols], rows=out_rows, macro=macro_rows)
    return _memo(("weeks", n, asof), build)


# ---------------- 标的详情 ---------------- #

def instrument(code):
    if code not in INST:
        return None
    df = data()["frames"].get(code)
    if df is None or df.empty:
        return None
    D = data_date()
    row = _row(code, D)
    runs = []
    for _, g in df.groupby("run", sort=True):
        start, end = g.index[0], g.index[-1]
        before = df[df.index < start]
        base = before["close"].iloc[-1] if len(before) else g["close"].iloc[0]
        runs.append(dict(status="YES" if g["yes"].iloc[0] else "NO", start=_ds(start), end=_ds(end), days=len(g),
                         ret=_f(g["close"].iloc[-1] / base - 1), peak=_f(g["dev"].max()), trough=_f(g["dev"].min())))
    y1 = df.loc[D - timedelta(days=365):]
    runs_1y = [r for r in runs if r["end"] >= _ds(D - timedelta(days=365))]
    stats = dict(
        yes_ratio_1y=_f(y1["yes"].mean()) if len(y1) else None,
        flips_1y=row.get("flips_1y"),
        avg_yes_days=_f(sum(r["days"] for r in runs_1y if r["status"] == "YES") / max(1, sum(1 for r in runs_1y if r["status"] == "YES")), 1),
        avg_no_days=_f(sum(r["days"] for r in runs_1y if r["status"] == "NO") / max(1, sum(1 for r in runs_1y if r["status"] == "NO")), 1),
        dev_max_1y=_f(y1["dev"].max()), dev_min_1y=_f(y1["dev"].min()),
    )
    wk = weeks(12)
    wrow = next((r for r in wk["rows"] if r["code"] == code), None) if wk else None
    return dict(
        row=row, stats=stats, runs=runs[::-1],
        hist=dict(dates=[_ds(t) for t in df.index], close=[_f(x, 4) for x in df["close"]],
                  ma=[_f(x, 4) for x in df["ma"]], dev=[_f(x, 5) for x in df["dev"]]),
        weeks=dict(weeks=wk["weeks"], cells=wrow["cells"]) if wrow else None,
    )


# ---------------- 数据健康 ---------------- #

def health():
    d = data()
    D = data_date()
    src = db.load_sources()
    items = []
    for code, *_ in INSTRUMENTS:
        inst = INST[code]
        s = d["raw"].get(code)
        info = src.get(code, {})
        it = dict(key=code, name=inst["name"], group=inst["group"], source=info.get("source"), ok=info.get("ok"),
                  error=info.get("error"), updated_at=info.get("updated_at"), fetched=info.get("fetched"))
        if s is not None and len(s):
            recent = s.loc[D - timedelta(days=120):] if D is not None else s
            gaps = recent.index.to_series().diff().dt.days
            ret = s.pct_change()
            big = ret[(ret.abs() > BIG_MOVE) & (ret.index >= D - timedelta(days=60))]
            it.update(rows=int(len(s)), first=_ds(s.index[0]), last=_ds(s.index[-1]),
                      lag=(D - s.index[-1]).days, stale=(D - s.index[-1]).days > STALE_DAYS,
                      max_gap=int(gaps.max()) if len(gaps.dropna()) else None,
                      gap=bool(len(gaps.dropna()) and gaps.max() > GAP_DAYS),
                      big_moves=[dict(date=_ds(t), ret=_f(v)) for t, v in big.items()])
        items.append(it)
    macro_items = []
    for key, label in MACRO.items():
        s = d["macro"].get(key)
        info = src.get(key if key == "DXY" else "BONDS", {})
        it = dict(key=key, name=label, source=info.get("source"), ok=info.get("ok"), error=info.get("error"),
                  updated_at=info.get("updated_at"))
        if s is not None and len(s.dropna()):
            s = s.dropna()
            it.update(rows=int(len(s)), first=_ds(s.index[0]), last=_ds(s.index[-1]),
                      lag=(D - s.index[-1]).days if D is not None else None,
                      stale=bool(D is not None and (D - s.index[-1]).days > STALE_DAYS))
        macro_items.append(it)
    return dict(date=_ds(D), last_refresh=db.get_meta("last_refresh"), failed=db.get_json("last_refresh_failed", []),
                duration=db.get_meta("last_refresh_seconds"), items=items, macro=macro_items,
                groups=GROUPS, thresholds=dict(stale=STALE_DAYS, big=BIG_MOVE, gap=GAP_DAYS))

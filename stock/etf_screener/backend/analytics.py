# -*- coding: utf-8 -*-
"""把最新快照整理成清单、指数分组、资金流向和数据健康。

- 规模 = 份额 × 最新价（市值口径），单位亿元。
- 规模变化与净申赎按回看窗口计算：取不晚于“快照日 − N 天”的最近一次快照作基期。
  净申赎 = (本期份额 − 基期份额) × 本期价格，剔除了价格涨跌的影响；规模变化里则两者都有。
- 区间收益来自东财场内基金排行（复权净值，含分红）；同类比较在“分类 + 类型”相同的指数之间进行，每个指数取规模最大的一只。
- 估值分位：最近 VAL_YEARS 年里不高于当前滚动市盈率的比例，历史不足一年时不算分位。
"""
import statistics
import threading
from datetime import date, timedelta

from . import db
from .config import CATEGORIES, CHANGE_WINDOWS, DEFAULT_THRESHOLD, KINDS, PERF_PERIODS, STYLE_KIND, VAL_YEARS

PKEYS = [k for k, _ in PERF_PERIODS]
VAL_SOURCE = {"csindex": ("中证指数官网", "日"), "legulegu": ("乐咕乐股", "月末")}

_cache = {"key": None, "snap": None}
_lock = threading.Lock()
YI = 1e8


def r2(v, d=2):
    return None if v is None else round(v, d)


def base_date(dates, day, days):
    target = (date.fromisoformat(day) - timedelta(days=days)).isoformat()
    older = [d for d in dates if d <= target]
    return older[-1] if older else None


def kind_of(style):
    return STYLE_KIND.get(style, style) if style else None


def valuation(series, years=VAL_YEARS):
    """市盈率序列 [(日期, 值)] → 当前值、分位、中位数、20% / 80% 分位值、最低最高。只用正值。"""
    if not series:
        return None
    last = series[-1][0]
    start = (date.fromisoformat(last) - timedelta(days=round(365.25 * years))).isoformat()
    pts = [(d, v) for d, v in series if d >= start and v and v > 0]
    if not pts:
        return None
    vals = sorted(v for _, v in pts)
    cur = pts[-1][1]
    span = (date.fromisoformat(last) - date.fromisoformat(pts[0][0])).days
    q = lambda p: vals[round(p * (len(vals) - 1))]
    return dict(cur=r2(cur), asof=last, since=pts[0][0], n=len(pts), years=round(span / 365.25, 1),
                pct=r2(sum(1 for v in vals if v <= cur) / len(vals), 4) if span >= 365 else None,
                median=r2(statistics.median(vals)), p20=r2(q(.2)), p80=r2(q(.8)), lo=r2(vals[0]), hi=r2(vals[-1]))


class Snapshot:
    def __init__(self):
        self.etfs = db.load_etfs()
        self.day = db.get_meta("snapshot_date")
        self.dates = db.snapshot_dates()
        self.cur = db.load_snapshot(self.day) if self.day else {}
        src = db.get_json("sources", {})
        guess = set(src.get("index_guess", []))
        self.windows = {}
        for w, days in CHANGE_WINDOWS.items():
            b = base_date(self.dates, self.day, days) if self.day else None
            self.windows[w] = dict(days=days, base=b, snap=db.load_snapshot(b) if b else None)
        self.perf = db.load_perf()
        self.nav_date = max((p["nav_date"] for p in self.perf.values() if p["nav_date"]), default=None)
        self.pe = db.load_pe()
        val_src = db.get_json("val_sources", {})
        self.val = {}
        for k, src in val_src.items():
            v = valuation(self.pe.get(k)) if src else None
            if v:
                v["src"], v["freq"] = VAL_SOURCE[src]
                self.val[k] = v
        self.rows = []
        for code, e in self.etfs.items():
            s = self.cur.get(code) or {}
            p = self.perf.get(code) or {}
            v = self.val.get(e["index_key"])
            row = dict(code=code, name=e["name"], short=e["short"], ex=e["exchange"], manager=_short_mgr(e["manager"]),
                       ik=e["index_key"], iname=e["index_name"], guess=code in guess, cat=e["category"], listed=e["list_date"],
                       style=e.get("style"), kind=kind_of(e.get("style")),
                       shares=r2((s.get("shares") or 0) / YI, 4) if s.get("shares") else None, price=s.get("price"),
                       scale=r2(s["scale"] / YI) if s.get("scale") else None, amount=r2((s.get("amount") or 0) / YI, 3),
                       nav_date=p.get("nav_date"), r_since=p.get("since"), inception=p.get("inception"),
                       pe=v["cur"] if v else None, pe_pct=v["pct"] if v else None)
            for k in PKEYS:
                row[f"r_{k}"] = p.get(k)
            for w, info in self.windows.items():
                b = (info["snap"] or {}).get(code)
                if b and b.get("scale") and s.get("scale"):
                    row[f"{w}_chg"] = r2((s["scale"] - b["scale"]) / YI)
                    row[f"{w}_pct"] = r2(s["scale"] / b["scale"] - 1, 4)
                    row[f"{w}_flow"] = r2((s["shares"] - b["shares"]) * s["price"] / YI) if b.get("shares") and s.get("shares") else None
            self.rows.append(row)
        self.rows.sort(key=lambda r: -(r["scale"] or 0))
        self.groups = {}
        for r in self.rows:
            if r["ik"]:
                self.groups.setdefault(r["ik"], []).append(r)
        # 同类：分类 + 类型相同的指数，每个指数取规模最大的一只（货币 ETF 各自算一个）
        reps = [g[0] for g in self.groups.values()] + [r for r in self.rows if not r["ik"]]
        self.peers = {}
        for r in reps:
            self.peers.setdefault((r["cat"], r["kind"]), []).append(r)

    def peer(self, row):
        """row 在同类指数中的各区间收益中位数和排名（从高到低）。"""
        reps = self.peers.get((row["cat"], row["kind"])) or []
        med, rank = {}, {}
        for k in PKEYS:
            vals = sorted((r[f"r_{k}"] for r in reps if r[f"r_{k}"] is not None), reverse=True)
            med[k] = r2(statistics.median(vals), 4) if vals else None
            v = row[f"r_{k}"]
            rank[k] = [vals.index(v) + 1, len(vals)] if v is not None and vals else None
        return dict(label=f"{row['cat']} · {row['kind']}", n=len(reps), median=med, rank=rank)

    def listing(self):
        return dict(day=self.day, rows=self.rows, categories=CATEGORIES, threshold=DEFAULT_THRESHOLD, kinds=KINDS,
                    perf_periods=PERF_PERIODS, nav_date=self.nav_date, vals=self.val,
                    windows={w: dict(days=i["days"], base=i["base"]) for w, i in self.windows.items()}, dates=self.dates)

    def index(self, key):
        return self._group(key, self.groups.get(key))

    def etf(self, code):
        """单只 ETF：有跟踪指数的返回整个指数分组，没有的（货币 ETF）当作只有一只的分组。"""
        row = next((r for r in self.rows if r["code"] == code), None)
        if not row:
            return None
        return dict(self._group(row["ik"], self.groups[row["ik"]] if row["ik"] else [row]), focus=code)

    def _group(self, key, members):
        if not members:
            return None
        hist = db.load_history([m["code"] for m in members])
        total = {}
        for rows in hist.values():
            for d, _, sc in rows:
                if sc:
                    total[d] = total.get(d, 0) + sc / YI
        top = members[0]
        v = self.val.get(key) if key else None
        return dict(key=key, name=top["iname"] if key else top["name"], cat=top["cat"], style=top["style"], kind=top["kind"],
                    guess=top["guess"], members=members, perf_periods=PERF_PERIODS, nav_date=self.nav_date,
                    peer=self.peer(top), val=dict(v, series=[[d, r2(pe)] for d, pe in self.pe[key] if d >= v["since"]]) if v else None,
                    total=r2(sum(m["scale"] or 0 for m in members)),
                    history=[[d, r2(v)] for d, v in sorted(total.items())],
                    member_history={c: [[d, r2((sc or 0) / YI)] for d, _, sc in rows] for c, rows in hist.items()},
                    windows={w: dict(days=i["days"], base=i["base"]) for w, i in self.windows.items()})

    def health(self):
        src = db.get_json("sources", {})
        by = {r["code"]: r for r in self.rows}
        pick = lambda codes: [dict(code=c, name=by[c]["name"], scale=by[c]["scale"], iname=by[c]["iname"], cat=by[c]["cat"])
                              for c in codes if c in by]
        groups = lambda keys: [dict(code=m["code"], name=m["name"], scale=m["scale"], iname=m["iname"], cat=m["cat"], style=m["style"])
                               for m in ((self.groups.get(k) or [by.get(k)])[0] for k in keys) if m]
        kw = sorted(groups(src.get("style_kw", [])), key=lambda m: -(m["scale"] or 0))
        return dict(style_kw=kw, val_none=groups(src.get("val_none", [])),
                    val_ok=[dict(key=k, name=(self.groups.get(k) or [{}])[0].get("iname"), **{x: v[x] for x in ("src", "freq", "since", "asof", "n")})
                            for k, v in self.val.items()],
                    day=self.day, dates=self.dates, last_refresh=db.get_meta("last_refresh"),
                    failed=db.get_json("last_refresh_failed", []), crosscheck=db.get_json("crosscheck"),
                    sources={k: v for k, v in src.items() if not isinstance(v, list)},
                    no_price=pick(src.get("no_price", [])), no_shares=pick(src.get("no_shares", [])),
                    from_tencent=pick(src.get("shares_from_tencent", [])), guess=pick(src.get("index_guess", [])),
                    total=len(self.rows), sh=sum(1 for r in self.rows if r["ex"] == "SH"), sz=sum(1 for r in self.rows if r["ex"] == "SZ"),
                    index_names_at=db.get_meta("index_names_at"))


def _short_mgr(m):
    for suf in ("基金管理股份有限公司", "基金管理有限公司", "资产管理有限公司", "基金管理有限责任公司", "有限公司"):
        if m and m.endswith(suf):
            return m[: -len(suf)]
    return m


def snapshot():
    key = db.get_meta("data_version")
    with _lock:
        if _cache["key"] != key or _cache["snap"] is None:
            _cache["snap"] = Snapshot()
            _cache["key"] = key
        return _cache["snap"]

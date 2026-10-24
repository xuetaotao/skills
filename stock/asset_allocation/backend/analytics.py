# -*- coding: utf-8 -*-
"""分析引擎：原始序列 → 人民币总收益序列 → 风险收益、相关性、组合回测、A 股估值、信号。

口径（页面同步展示）:
- 人民币计价：外币资产 × 当日汇率（汇率缺失时沿用最近 35 天内的值）。
- 总收益：A 股、标普500、DAX、债券用官方全收益指数；纳指100 用 QQQ 复权价；
  日经、富时、恒生、台湾、韩国用“价格指数 + 对应 ETF 年度股息率按交易日均匀计提”近似。
- 长期统计用月末数据，组合按月再平衡，不计交易成本、税费和 QDII 溢价。
- 坏点：日度序列中相对上一个有效值跳变超过阈值、几天内又回到原水平的点视为数据错误，分析时剔除。
"""
import bisect
import json
import math
import threading
from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import db
from .config import (ASSET_MAP, ASSETS, CORE, FX_SERIES, LOOKBACK, PRESETS, RF, SERIES, SERIES_MAP, STALE_DAYS,
                     START, WEIGHT_CAP)

# 跳变阈值 / 回到原水平的最小容差。价格阈值高于 A 股 20% 的单日涨跌幅限制，避免误伤真实行情
SPIKE = {"price": (0.25, 0.03), "fx": (0.10, 0.015)}
# 汇率缺失时沿用最近值的最长天数（数据源偶有整月缺失，如中行 2015 年 1 月）
FX_FFILL_DAYS = 35


def num(x, nd=4):
    """转成可 JSON 序列化的浮点数，NaN/inf → None。"""
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, nd) if math.isfinite(x) else None


# ---------------- 序列准备 ----------------

def clean(points, kind):
    """剔除短暂坏点：跳变超过阈值，且之后 3 个点内回到跳变幅度 1/3 以内。返回 (保留的点, 剔除的点)。"""
    if kind not in SPIKE or len(points) < 3:
        return list(points), []
    jump, back = SPIKE[kind]
    keep, out = [points[0]], []
    for i in range(1, len(points) - 1):
        p, v = keep[-1][1], points[i][1]
        dev = abs(v / p - 1) if p > 0 else 0
        if dev > jump:
            tol = max(back, dev / 3)
            ahead = (points[j][1] for j in range(i + 1, min(i + 4, len(points))))
            if any(abs(n / p - 1) < tol for n in ahead):
                out.append(points[i])
                continue
        keep.append(points[i])
    keep.append(points[-1])
    return keep, out


def to_series(points):
    if not points:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in points], index=pd.to_datetime([d for d, _ in points]), dtype=float)


def add_dividend(price, yields):
    """价格 + 年度股息率按交易日均匀计提，近似总收益。缺失年份用有效年份的中位数。"""
    if price.empty:
        return price
    fill = float(np.median(list(yields.values()))) if yields else 0.0
    r = price.pct_change().fillna(0)
    y = pd.Series(r.index.year, index=r.index).map(lambda yr: yields.get(yr, fill))
    n = r.groupby(r.index.year).transform("size").clip(lower=200)
    return price.iloc[0] * (1 + r + y / n).cumprod()


class Data:
    """从数据库载入并清洗全部序列，构建各资产的人民币日度 / 月度总收益序列。"""

    def __init__(self, points):
        self.raw = points
        self.cleaned, self.outliers = {}, {}
        for cfg in SERIES:
            pts = points.get(cfg["code"], [])
            keep, out = clean(pts, cfg["kind"])
            self.cleaned[cfg["code"]] = keep
            self.outliers[cfg["code"]] = [d for d, _ in out]
        self.fx = {ccy: self._fx(ccy) for ccy in FX_SERIES}
        self.local, self.cny = {}, {}
        for a in ASSETS:
            loc = self._local(a)
            self.local[a["code"]] = loc
            self.cny[a["code"]] = self._to_cny(loc, a["ccy"])
        self.monthly = pd.DataFrame({k: v.resample("ME").last() for k, v in self.cny.items() if not v.empty})
        self.monthly_local = pd.DataFrame({k: v.resample("ME").last() for k, v in self.local.items() if not v.empty})

    def s(self, code):
        return to_series(self.cleaned.get(code, []))

    def _fx(self, ccy):
        src = FX_SERIES[ccy]
        if isinstance(src, str):
            return self.s(src)
        a, b = self.s(src[0]), self.s(src[1])
        if a.empty or b.empty:
            return pd.Series(dtype=float)
        idx = a.index.union(b.index)
        x = a.reindex(idx).ffill(limit=FX_FFILL_DAYS) / b.reindex(idx).ffill(limit=FX_FFILL_DAYS)
        return x.dropna()

    def _local(self, a):
        price = self.s(a["price"])
        if a.get("div"):
            yields = {int(d[:4]): v for d, v in self.cleaned.get(a["div"], [])}
            price = add_dividend(price, yields)
        return price

    def _to_cny(self, local, ccy):
        if ccy == "CNY" or local.empty:
            return local
        fx = self.fx.get(ccy)
        if fx is None or fx.empty:
            return pd.Series(dtype=float)
        f = fx.reindex(fx.index.union(local.index)).ffill(limit=FX_FFILL_DAYS).reindex(local.index)
        return (local * f).dropna()


# ---------------- 指标 ----------------

def perf(s, rf=RF):
    """月度净值序列的风险收益指标（与前端实验室的 JS 实现保持一致）。"""
    s = s.dropna()
    if len(s) < 13:
        return None
    r = s.pct_change().dropna()
    yrs = len(r) / 12
    cagr = (s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1
    vol = r.std() * math.sqrt(12)
    dd = s / s.cummax() - 1
    roll12 = (s / s.shift(12) - 1).dropna()
    roll60 = (s / s.shift(60) - 1).dropna()

    def sub(n):
        return (s.iloc[-1] / s.iloc[-1 - n]) ** (12 / n) - 1 if len(s) > n else None

    mdd = dd.min()
    return dict(
        start=s.index[0].strftime("%Y-%m"), end=s.index[-1].strftime("%Y-%m"), years=num(yrs, 1),
        cagr=num(cagr), vol=num(vol), sharpe=num((cagr - rf) / vol if vol > 0 else None, 2),
        mdd=num(mdd), calmar=num(cagr / abs(mdd) if mdd < 0 else None, 2),
        worst12=num(roll12.min() if len(roll12) else None), best12=num(roll12.max() if len(roll12) else None),
        cagr10=num(sub(120)), cagr5=num(sub(60)),
        win5=num((roll60 > 0).mean() if len(roll60) else None, 3), cur_dd=num(dd.iloc[-1]),
    )


def recent(d):
    """日度序列的近期表现：1/3/6 个月、今年以来、1 年、3/5 年年化、距历史高点。"""
    d = d.dropna()
    if len(d) < 2:
        return None
    last_dt = d.index[-1]

    def since(dt):
        base = d[d.index <= dt]
        return d.iloc[-1] / base.iloc[-1] - 1 if len(base) else None

    def ann(years):
        r = since(last_dt - timedelta(days=round(365.25 * years)))
        return None if r is None or d.index[0] > last_dt - timedelta(days=round(365.25 * years) - 7) \
            else (1 + r) ** (1 / years) - 1

    peak_i = d.idxmax()
    return dict(
        last_date=last_dt.strftime("%Y-%m-%d"), m1=num(since(last_dt - timedelta(days=30))),
        m3=num(since(last_dt - timedelta(days=91))), m6=num(since(last_dt - timedelta(days=182))),
        ytd=num(since(pd.Timestamp(last_dt.year - 1, 12, 31))), y1=num(since(last_dt - timedelta(days=365))),
        y3=num(ann(3)), y5=num(ann(5)),
        from_peak=num(d.iloc[-1] / d.max() - 1), peak_date=peak_i.strftime("%Y-%m-%d"),
    )


def ser(s, nd=4):
    return [[d.strftime("%Y-%m-%d"), num(v, nd)] for d, v in s.dropna().items()]


def monthly_ser(s, nd=4):
    return [[d.strftime("%Y-%m"), num(v, nd)] for d, v in s.dropna().items()]


# ---------------- 组合 ----------------

def project(v, cap):
    """投影到 {0 ≤ w ≤ cap, Σw = 1}：Σclip(v−τ, 0, cap) 关于 τ 分段线性递减，在断点间精确插值。"""
    bps = np.sort(np.concatenate([v, v - cap]))
    sums = np.clip(v[None, :] - bps[:, None], 0, cap).sum(axis=1)
    i = int(np.searchsorted(-sums, -1.0))
    if i == 0:
        tau = bps[0]
    else:
        s0, s1 = sums[i - 1], sums[i]
        tau = bps[i - 1] + (s0 - 1) / (s0 - s1) * (bps[i] - bps[i - 1]) if s0 > s1 else bps[i]
    return np.clip(v - tau, 0, cap)


def w_minvar(R, cap=WEIGHT_CAP, iters=1500):
    """加速投影梯度（FISTA）求 min wᵀΣw。"""
    S = R.cov().values * 12
    n = len(S)
    step = 1 / (2 * np.linalg.eigvalsh(S).max())
    w = y = project(np.ones(n) / n, cap)
    t = 1.0
    for _ in range(iters):
        w_new = project(y - step * 2 * (S @ y), cap)
        t_new = (1 + math.sqrt(1 + 4 * t * t)) / 2
        y = w_new + (t - 1) / t_new * (w_new - w)
        w, t = w_new, t_new
    return w


def w_maxsharpe(R, cap=WEIGHT_CAP, rf=RF, iters=600):
    """投影梯度上升 + 回溯步长。夏普比率在约束集上拟凹，局部最优即全局最优。"""
    mu = R.mean().values * 12
    S = R.cov().values * 12
    n = len(S)

    def sharpe(w):
        return (w @ mu - rf) / math.sqrt(max(w @ S @ w, 1e-12))

    w = project(np.ones(n) / n, cap)
    f, step = sharpe(w), 1.0
    for _ in range(iters):
        sig = math.sqrt(max(w @ S @ w, 1e-12))
        g = mu / sig - (w @ mu - rf) * (S @ w) / sig ** 3
        while step > 1e-9:
            w2 = project(w + step * g, cap)
            f2 = sharpe(w2)
            if f2 > f:
                break
            step /= 2
        else:
            break
        gain = f2 - f
        w, f, step = w2, f2, step * 2
        if gain < 1e-10:
            break
    return w


def w_riskparity(R, sweeps=300):
    """循环坐标下降求解 min ½yᵀΣy − Σ(1/n)·ln y，归一化后各资产风险贡献相等。"""
    S = R.cov().values * 12
    n = len(S)
    y = 1 / np.sqrt(np.diag(S))
    b = 1 / n
    for _ in range(sweeps):
        for i in range(n):
            c = S[i] @ y - S[i, i] * y[i]
            y[i] = (-c + math.sqrt(c * c + 4 * S[i, i] * b)) / (2 * S[i, i])
    return y / y.sum()


METHODS = [
    ("minvar", "滚动·最小方差", w_minvar, "每年末用过去 60 个月数据，求波动最小的权重（单资产不超过 35%）。"),
    ("riskparity", "滚动·风险平价", w_riskparity, "每年末用过去 60 个月数据，让每个资产贡献的风险相同。"),
    ("maxsharpe", "滚动·最大夏普", w_maxsharpe, "每年末用过去 60 个月数据，求夏普比率最高的权重（单资产不超过 35%）。对历史收益很敏感，权重变化大。"),
]


def normalize(w):
    w = np.clip(np.asarray(w, dtype=float), 0, None)
    w = np.where(w < 0.005, 0, w)
    return w / w.sum()


def complete_cols(est):
    """估计窗口内每个月都有数据的资产；历史较短的资产攒够窗口长度后才进入候选。"""
    return [c for c in est.columns if est[c].notna().all()]


def optimize(est, fn):
    """只在数据完整的资产上求解，返回覆盖全部列的权重（其余为 0）。"""
    cols = complete_cols(est)
    w = pd.Series(0.0, index=est.columns)
    w[cols] = normalize(fn(est[cols]))
    return w


def walk_forward(R, fn, lookback=LOOKBACK):
    """每年末用过去 lookback 个月数据估计权重，持有下一年（月度再平衡回目标权重）。"""
    out, weights = [], {}
    for y in sorted(set(R.index.year)):
        est = R[R.index < pd.Timestamp(f"{y}-01-01")].tail(lookback)
        test = R[R.index.year == y]
        if len(est) < lookback or test.empty:
            continue
        w = optimize(est, fn)
        weights[y] = w.values
        out.append((test.fillna(0) * w).sum(axis=1))
    return pd.concat(out), pd.DataFrame(weights, index=R.columns).T


def full_history(R):
    """从统计起点就有数据的资产。"""
    return [c for c in R.columns if R[c].first_valid_index() == R.index[0]]


def preset_returns(R, w):
    """预设组合在其用到的资产都有数据的区间内回测，返回 (月收益, 资产, 归一化权重)。"""
    codes = [c for c, x in w.items() if x > 0 and c in R.columns]
    Rp = R[codes].dropna()
    wv = np.array([w[c] for c in codes], dtype=float)
    wv = wv / wv.sum()
    return (Rp * wv).sum(axis=1), Rp, codes, wv


def curve(returns, start_label):
    c = (1 + returns).cumprod()
    return pd.concat([pd.Series([1.0], index=[start_label]), c])


def risk_contrib(R, w):
    S = R.cov().values * 12
    w = np.asarray(w)
    port_var = w @ S @ w
    return (w * (S @ w)) / port_var if port_var > 0 else np.zeros_like(w)


def preset_weights(p, codes):
    """codes：等权组合的成员（长历史资产）。"""
    if p["weights"] == "equal":
        return {c: round(1 / len(codes), 4) for c in codes}
    return dict(p["weights"])


# ---------------- A 股估值 ----------------

def pct_rank(value, values):
    v = sorted(values)
    return bisect.bisect_right(v, value) / len(v) if v else None


def window(s, years):
    return s[s.index >= s.index[-1] - pd.DateOffset(years=years)] if len(s) else s


def valuation(data, snapshots):
    pe_rows = []
    for code in ("PE_HS300", "PE_SZ50", "PE_ZZ500", "PE_ZZ1000", "PE_CYB50"):
        s = data.s(code)
        if s.empty:
            continue
        w10 = window(s, 10)
        pe_rows.append(dict(
            code=code, name=SERIES_MAP[code]["name"].replace(" 滚动市盈率", ""), latest=num(s.iloc[-1], 2),
            date=s.index[-1].strftime("%Y-%m-%d"), pct10=num(pct_rank(s.iloc[-1], w10.values), 3),
            pct_all=num(pct_rank(s.iloc[-1], s.values), 3), median10=num(w10.median(), 2),
            min10=num(w10.min(), 2), max10=num(w10.max(), 2), since=s.index[0].strftime("%Y-%m"),
            history=monthly_ser(s, 2)))
    ebs = data.s("EBS_HS300")
    bond = data.s("CN10Y")
    ebs_info = bond_info = None
    if not ebs.empty:
        w10 = window(ebs, 10)
        ebs_info = dict(latest=num(ebs.iloc[-1], 5), date=ebs.index[-1].strftime("%Y-%m-%d"),
                        pct10=num(pct_rank(ebs.iloc[-1], w10.values), 3), pct_all=num(pct_rank(ebs.iloc[-1], ebs.values), 3),
                        p20=num(w10.quantile(.2), 5), p50=num(w10.median(), 5), p80=num(w10.quantile(.8), 5),
                        history=ser(ebs.resample("W").last(), 5))
    if not bond.empty:
        w10 = window(bond, 10)
        bond_info = dict(latest=num(bond.iloc[-1], 3), date=bond.index[-1].strftime("%Y-%m-%d"),
                         pct10=num(pct_rank(bond.iloc[-1], w10.values), 3), min10=num(w10.min(), 3),
                         max10=num(w10.max(), 3), history=ser(bond.resample("W").last(), 3))

    hs = next((r for r in pe_rows if r["code"] == "PE_HS300"), None)
    verdict = valuation_verdict(hs, ebs_info)
    csv_ = (snapshots or {}).get("csindex_value", {})
    dividend = []
    if bond_info:
        for name, v in csv_.items():
            dividend.append(dict(name=name, dividend_yield=v["dividend_yield"], pe=v["pe"], date=v["date"],
                                 spread=num(v["dividend_yield"] - bond_info["latest"], 2)))
    hp = [dict(code=c, name=ASSET_MAP[c]["name"], **holding_periods(data.cny[c]))
          for c in ("CSI300", "CSIA500", "CSI500", "CSI1000", "CSIDIV", "CHINEXT") if not data.cny[c].empty]
    return dict(verdict=verdict, pe=pe_rows, ebs=ebs_info, bond=bond_info, dividend=dividend,
                sw=(snapshots or {}).get("sw_industry", []), sw_at=(snapshots or {}).get("fetched_at"),
                holding=hp)


VERDICT_TEXT = {
    "低估": ("cold", "估值处于近 10 年偏低区域，股票相对债券的性价比高。适合按计划分批增加 A 股仓位，并做好继续下跌的心理准备。"),
    "偏低": ("cold", "估值略低于近 10 年中枢，长期配置的赔率尚可。可以维持或小幅提高 A 股仓位。"),
    "适中": ("flat", "估值处于近 10 年中间水平，没有明显的高估或低估信号。按目标权重再平衡即可。"),
    "偏高": ("hot", "估值略高于近 10 年中枢，新增资金宜放慢节奏，避免一次性大额买入。"),
    "高估": ("hot", "估值处于近 10 年偏高区域，股票相对债券的性价比低。可以考虑把超出目标的部分逐步兑现。"),
}


def valuation_verdict(hs, ebs):
    """沪深300：市盈率分位越低越便宜，股债利差分位越高越便宜，两者平均成“便宜程度”。"""
    if not hs or hs["pct10"] is None:
        return None
    cheap = [1 - hs["pct10"]]
    if ebs and ebs["pct10"] is not None:
        cheap.append(ebs["pct10"])
    score = sum(cheap) / len(cheap)
    label = "低估" if score >= 0.75 else "偏低" if score >= 0.6 else "高估" if score <= 0.25 else "偏高" if score <= 0.4 else "适中"
    tone, hint = VERDICT_TEXT[label]
    return dict(label=label, tone=tone, hint=hint, cheapness=num(score, 3),
                pe=hs["latest"], pe_pct=hs["pct10"], ebs=ebs and ebs["latest"], ebs_pct=ebs and ebs["pct10"])


def holding_periods(d):
    """任意一天买入、持有 N 年的盈利概率与年化收益中位数（日度数据，滚动窗口）。"""
    d = d.dropna()
    out = {}
    for y in (1, 3, 5, 10):
        n = 252 * y
        if len(d) > n + 50:
            rr = (d.shift(-n) / d - 1).dropna()
            out[f"win{y}"] = num((rr > 0).mean(), 3)
            out[f"med{y}"] = num((1 + rr.median()) ** (1 / y) - 1)
        else:
            out[f"win{y}"] = out[f"med{y}"] = None
    out["since"] = d.index[0].strftime("%Y-%m") if len(d) else None
    return out


# ---------------- 汇总 ----------------

def series_health(data, failed):
    today = date.today()
    rows = []
    for cfg in SERIES:
        pts = data.raw.get(cfg["code"], [])
        issues = []
        first = last = lag = None
        stale = False
        if not pts:
            issues.append("暂无数据")
        else:
            first, last = pts[0][0], pts[-1][0]
            lag = (today - date.fromisoformat(last)).days
            stale = lag > STALE_DAYS[cfg["freq"]]
            if stale:
                issues.append(f"滞后 {lag} 天")
        if data.outliers.get(cfg["code"]):
            issues.append(f"剔除坏点 {len(data.outliers[cfg['code']])} 个")
        rows.append(dict(code=cfg["code"], name=cfg["name"], kind=cfg["kind"], source=cfg["source"],
                         symbol=cfg.get("symbol", ""), freq=cfg["freq"], first_date=first, latest_date=last,
                         lag_days=lag, points=len(pts), stale=stale, outliers=data.outliers.get(cfg["code"], []),
                         status="missing" if not pts else "warn" if issues else "ok", issues=issues))
    return dict(rows=rows, fresh=sum(1 for r in rows if r["latest_date"] and not r["stale"]),
                total=len(rows), failed=failed, stale=[r for r in rows if r["stale"] or not r["latest_date"]])


def signals(assets_recent, val, data):
    out = []

    def sig(level, title, text, link):
        out.append(dict(level=level, title=title, text=text, link=link))

    v = val.get("verdict")
    if v:
        level = "positive" if v["label"] in ("低估", "偏低") else "risk" if v["label"] in ("高估", "偏高") else "info"
        sig(level, f"A 股估值{v['label']}",
            f"沪深300 滚动市盈率 {v['pe']}，处于近 10 年第 {round(v['pe_pct'] * 100)}% 分位"
            + (f"；股债利差 {v['ebs'] * 100:.2f}%，处于近 10 年第 {round(v['ebs_pct'] * 100)}% 分位" if v.get("ebs") is not None else "")
            + f"。{v['hint']}", "#/valuation")
    b = val.get("bond")
    if b and b["pct10"] is not None and b["pct10"] <= 0.1:
        sig("watch", "国债收益率处于历史低位",
            f"10 年期国债收益率 {b['latest']:.2f}%，处于近 10 年第 {round(b['pct10'] * 100)}% 分位。"
            "债券未来的票息回报有限，利率一旦回升，债券基金会有阶段性亏损。", "#/valuation")
    for code, r in assets_recent.items():
        a = ASSET_MAP[code]
        if not r or not a["core"]:
            continue
        deep = r["from_peak"] is not None and r["from_peak"] <= -0.3
        surge = r["y1"] is not None and r["y1"] >= 0.4
        if deep and surge:
            sig("watch", f"{a['name']}大起大落",
                f"{a['name']}近一年（人民币计价）上涨 {r['y1'] * 100:.1f}%，但已从 {r['peak_date']} 的高点回落 "
                f"{-r['from_peak'] * 100:.1f}%。波动明显放大，仓位不宜超过目标权重。", f"#/assets/{code}")
            continue
        if deep:
            sig("watch", f"{a['name']}处于深度回撤",
                f"{a['name']}（人民币计价）距 {r['peak_date']} 的历史高点 {r['from_peak'] * 100:.1f}%。"
                "长期看好的资产在深度回撤时，按目标权重再平衡往往意味着逢低补仓。", f"#/assets/{code}")
        if surge:
            sig("watch", f"{a['name']}过去一年大涨 {r['y1'] * 100:.0f}%",
                f"{a['name']}近一年（人民币计价）上涨 {r['y1'] * 100:.1f}%，在组合中的占比可能已明显超过目标，"
                "注意检查是否需要再平衡，避免追高。", f"#/assets/{code}")
    usd = data.fx.get("USD")
    if usd is not None and len(usd) > 260:
        base = usd[usd.index <= usd.index[-1] - timedelta(days=365)]
        if len(base):
            ch = usd.iloc[-1] / base.iloc[-1] - 1
            if abs(ch) >= 0.04:
                sig("info", f"人民币对美元一年{'贬值' if ch > 0 else '升值'} {abs(ch) * 100:.1f}%",
                    f"美元兑人民币从 {base.iloc[-1]:.3f} 变为 {usd.iloc[-1]:.3f}。"
                    + ("人民币贬值会抬高海外资产的人民币回报。" if ch > 0 else "人民币升值会压低海外资产的人民币回报，持有的海外资产换算回来会少一些。"),
                    "#/assets")
    m = data.monthly
    if {"CSI300", "SPX"} <= set(m.columns):
        R = m[["CSI300", "SPX"]].dropna().pct_change().dropna()
        if len(R) > 72:
            c_all, c_3y = R.corr().iloc[0, 1], R.tail(36).corr().iloc[0, 1]
            if c_3y - c_all >= 0.2:
                sig("info", "A 股与美股的相关性上升",
                    f"近 3 年沪深300 与标普500 的月收益相关系数为 {c_3y:.2f}，高于长期的 {c_all:.2f}，两者互相分散风险的效果在减弱。",
                    "#/assets")
    order = {"risk": 0, "watch": 1, "positive": 2, "info": 3}
    return sorted(out, key=lambda s: order[s["level"]])


def _compute():
    today = date.today()
    data = Data(db.load_all_points())
    snapshots = json.loads(db.get_meta("snapshots", "{}") or "{}")
    failed = json.loads(db.get_meta("last_refresh_failed", "[]") or "[]")

    # 单资产
    m = data.monthly[data.monthly.index >= START]
    ml = data.monthly_local[data.monthly_local.index >= START]
    assets = []
    rec = {}
    for a in ASSETS:
        c = a["code"]
        r = recent(data.cny[c]) if not data.cny[c].empty else None
        rec[c] = r
        p = perf(m[c]) if c in m else None
        pl = perf(ml[c]) if c in ml and a["ccy"] != "CNY" else None
        lag = (today - date.fromisoformat(r["last_date"])).days if r else None
        assets.append(dict(code=c, name=a["name"], group=a["group"], region=a["region"], ccy=a["ccy"],
                           basis=a["basis"], core=a["core"], perf=p, recent=r,
                           local_cagr=pl and pl["cagr"], stale=lag is None or lag > STALE_DAYS["D"], lag_days=lag))

    # 月收益：历史较短的资产在起点之前为 NaN；长历史资产缺数的月份整行剔除
    mc = m[CORE]
    R = (mc / mc.shift(1) - 1).iloc[1:]
    full = full_history(R)
    R = R[R[full].notna().all(axis=1)]
    # 起点按净值基期（首个收益月的上一个月）标注，与资产对比页的“起点”一致
    since = {c: (R[c].first_valid_index() - pd.offsets.MonthEnd(1)).strftime("%Y-%m") for c in CORE if R[c].notna().any()}
    short = [dict(code=c, name=ASSET_MAP[c]["name"], since=since[c]) for c in CORE if c not in full and c in since]

    # 相关性：每对资产按共同区间计算
    recent_R = R.tail(60)
    corr = dict(labels=[ASSET_MAP[c]["name"] for c in CORE], codes=CORE,
                full=[[num(x, 2) for x in row] for row in R.corr(min_periods=24).values],
                recent=[[num(x, 2) for x in row] for row in recent_R.corr(min_periods=24).values],
                full_range=[R.index[0].strftime("%Y-%m"), R.index[-1].strftime("%Y-%m")],
                recent_range=[recent_R.index[0].strftime("%Y-%m"), R.index[-1].strftime("%Y-%m")], short=short)

    # 组合：预设固定权重 + 滚动优化
    presets = []
    for p in PRESETS:
        w = preset_weights(p, full)
        rets, Rp, codes, wv = preset_returns(R, w)
        cv = curve(rets, Rp.index[0] - pd.offsets.MonthEnd(1))
        rc = dict(zip(codes, risk_contrib(Rp, wv)))
        presets.append(dict(key=p["key"], name=p["name"], desc=p["desc"], weights=w, perf=perf(cv),
                            risk={c: num(rc.get(c, 0), 3) for c in CORE},
                            ytd=num(cv.iloc[-1] / cv[cv.index <= pd.Timestamp(cv.index[-1].year - 1, 12, 31)].iloc[-1] - 1)
                            if (cv.index <= pd.Timestamp(cv.index[-1].year - 1, 12, 31)).any() else None))
    dynamic = []
    for key, name, fn, desc in METHODS:
        rets, wh = walk_forward(R, fn)
        t0 = rets.index[0] - pd.offsets.MonthEnd(1)
        cv = curve(rets, t0)
        latest = optimize(R.tail(LOOKBACK), fn)
        dynamic.append(dict(key=key, name=name, desc=desc, perf=perf(cv), curve=monthly_ser(cv),
                            latest={c: num(latest[c], 3) for c in CORE},
                            history={str(y): dict(zip(CORE, [num(x, 3) for x in row])) for y, row in wh.iterrows()}))
    wf_start = min(d["curve"][0][0] for d in dynamic) if dynamic else None

    # 日历年收益（年末 / 上年末；当年为今年以来）
    ye = data.monthly.groupby(data.monthly.index.year).last()
    yearly_ret = (ye / ye.shift(1) - 1).loc[int(START[:4]) + 1:]
    yearly = dict(years=[int(y) for y in yearly_ret.index],
                  rows={c: [num(x) for x in yearly_ret[c]] for c in yearly_ret.columns})

    val = valuation(data, snapshots)
    sigs = signals(rec, val, data)
    health = series_health(data, failed)
    return dict(today=today.isoformat(), data=data, assets=assets, recent=rec, corr=corr, R=R, since=since,
                presets=presets, dynamic=dynamic, wf_start=wf_start, valuation=val, signals=sigs, yearly=yearly,
                health=health, headline=headline(assets, val, presets))


def headline(assets, val, presets):
    parts = []
    v = val.get("verdict")
    if v:
        parts.append(f"A 股估值{v['label']}（沪深300 滚动市盈率 {v['pe']}，近 10 年第 {round(v['pe_pct'] * 100)}% 分位）")
    ytd = [(a["name"], a["recent"]["ytd"]) for a in assets if a["core"] and a["recent"] and a["recent"]["ytd"] is not None]
    if ytd:
        best, worst = max(ytd, key=lambda x: x[1]), min(ytd, key=lambda x: x[1])
        parts.append(f"今年以来人民币计价表现最好的是{best[0]}（{best[1] * 100:+.1f}%），最差的是{worst[0]}（{worst[1] * 100:+.1f}%）")
    return "；".join(parts) + "。" if parts else "暂无足够数据形成结论。"


_cache = dict(key=None, data=None)
_lock = threading.Lock()


def snapshot():
    """按数据版本号缓存（每次更新结束时写入），刷新进行中不会反复重算。"""
    key = (db.get_meta("data_version"), date.today().isoformat())
    with _lock:
        if _cache["key"] != key:
            _cache["data"] = _compute()
            _cache["key"] = key
        return _cache["data"]

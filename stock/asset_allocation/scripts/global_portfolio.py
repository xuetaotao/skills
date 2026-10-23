# -*- coding: utf-8 -*-
"""全球大类资产风险收益对比与组合构建（统一人民币计价、尽量含分红）。

资产口径：
  A股      中证官网全收益指数（H00300/H00905/H00852/H00922）；创业板指、科创50 为价格指数
  标普500  ^SP500TR 官方全收益指数（Yahoo）
  纳指100  QQQ 复权价（Yahoo，含分红、扣 0.2% 费率）
  日经225  ^N225 价格 + 1321.T 实际年度股息率估算
  富时100  ^FTSE 价格 + ISF.L 实际年度股息率估算
  黄金     伦敦金现货 XAU（新浪外盘）
  汇率     中国银行折算价（新浪），全部换算为人民币
所有统计基于月末数据、月度再平衡、不计交易成本与税费。
"""
import json
import os
import time
import warnings
from datetime import datetime

import numpy as np
import pandas as pd
import requests
from scipy.optimize import minimize

import akshare as ak

warnings.filterwarnings("ignore")
pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 30)

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
CACHE = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "output")
os.makedirs(CACHE, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

RF = 0.02
START = "2006-11-01"
CAP = 0.35
TODAY = datetime.now().strftime("%Y%m%d")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126"}


# ---------------- 数据抓取 ----------------

def cached(name, fn, max_age_h=12):
    path = os.path.join(CACHE, f"{name}.csv")
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age_h * 3600:
        return pd.read_csv(path, index_col=0, parse_dates=True).iloc[:, 0]
    s = fn().astype(float).dropna().sort_index()
    s = s[~s.index.duplicated(keep="last")]
    s.to_frame(name).to_csv(path)
    return s


def csindex(code):
    df = ak.stock_zh_index_hist_csindex(symbol=code, start_date="20000101", end_date=TODAY)
    s = pd.Series(df["收盘"].astype(float).values, index=pd.to_datetime(df["日期"]))
    gaps = s.index.to_series().diff().dt.days
    big = gaps[gaps > 30]
    if len(big):  # 首行常为基日占位，剔除断档之前的部分
        s = s[s.index >= big.index[-1]]
    return s


def sina_index(symbol):
    df = ak.stock_zh_index_daily(symbol=symbol)
    return pd.Series(df["close"].astype(float).values, index=pd.to_datetime(df["date"]))


def _yahoo_raw(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = dict(period1=946684800, period2=int(time.time()) + 86400, interval="1d", events="div,split")
    return requests.get(url, params=params, headers=UA, timeout=30).json()["chart"]["result"][0]


def yahoo(symbol, field="adjclose"):
    j = _yahoo_raw(symbol)
    idx = pd.to_datetime(j["timestamp"], unit="s").normalize()
    v = j["indicators"]["adjclose"][0]["adjclose"] if field == "adjclose" else j["indicators"]["quote"][0]["close"]
    return pd.Series(v, index=idx, dtype=float)


def etf_div_yield(symbol):
    """按自然年计算 ETF 实际股息率：当年分红合计 / 当年均价；当年用近 12 个月分红 / 最新价。

    Yahoo 的 close 已做拆股调整但拆股前的分红金额未调整（如 1321.T 2026-10 的 100:1 拆股），
    需按拆股比例还原；不在 0.3%~8% 合理区间的年份视为缺失（NaN）。
    """
    j = _yahoo_raw(symbol)
    idx = pd.to_datetime(j["timestamp"], unit="s").normalize()
    close = pd.Series(j["indicators"]["quote"][0]["close"], index=idx, dtype=float).dropna()
    ev = j.get("events", {})
    d = pd.Series({pd.to_datetime(int(v["date"]), unit="s").normalize(): float(v["amount"])
                   for v in ev.get("dividends", {}).values()}).sort_index()
    for sp in ev.get("splits", {}).values():
        num, den = (float(x) for x in sp["splitRatio"].split(":"))
        sd = pd.to_datetime(int(sp["date"]), unit="s").normalize()
        d[d.index < sd] = d[d.index < sd] * den / num
    cur = close.index[-1].year
    out = {}
    for y in range(close.index[0].year + 1, cur):
        out[y] = d[d.index.year == y].sum() / close[close.index.year == y].mean()
    out[cur] = d[d.index > close.index[-1] - pd.Timedelta(days=365)].sum() / close.iloc[-1]
    s = pd.Series(out)
    return s.where((s >= 0.003) & (s <= 0.08))


def boc_fx(name):
    df = ak.currency_boc_sina(symbol=name, start_date="20000101", end_date=TODAY)
    v = pd.to_numeric(df["中行折算价"], errors="coerce").fillna(pd.to_numeric(df["央行中间价"], errors="coerce"))
    return pd.Series(v.values, index=pd.to_datetime(df["日期"])) / 100


def xau():
    df = ak.futures_foreign_hist(symbol="XAU")
    return pd.Series(df["close"].astype(float).values, index=pd.to_datetime(df["date"]))


def add_dividend(price, yld):
    """价格指数 + 年度股息率按交易日均匀计提，近似全收益。缺失年份用有效年份中位数。"""
    yld = yld.fillna(yld.median())
    fill = yld.median()
    r = price.pct_change().fillna(0)
    y = pd.Series(r.index.year, index=r.index).map(lambda yr: yld.get(yr, fill))
    n = r.groupby(r.index.year).transform("size").clip(lower=200)
    return price.iloc[0] * (1 + r + y / n).cumprod()


def load():
    fx = {c: cached(f"fx_{c}", lambda c=c: boc_fx(n)) for c, n in [("USD", "美元"), ("JPY", "日元"), ("GBP", "英镑")]}
    for c, s in fx.items():
        jump = s.pct_change().abs()
        if (jump > 0.05).any():
            print(f"[警告] {c} 汇率存在单日 >5% 跳变:", jump[jump > 0.05].head().to_dict())

    nk_y = cached("div_1321T", lambda: etf_div_yield("1321.T"), max_age_h=24 * 7)
    uk_y = cached("div_ISFL", lambda: etf_div_yield("ISF.L"), max_age_h=24 * 7)
    for y in (nk_y, uk_y):  # 首次抓取为整数年份，读缓存时会被解析成日期
        y.index = y.index.year if isinstance(y.index, pd.DatetimeIndex) else y.index.astype(int)

    local = {
        "沪深300": (cached("H00300", lambda: csindex("H00300")), None),
        "中证500": (cached("H00905", lambda: csindex("H00905")), None),
        "中证1000": (cached("H00852", lambda: csindex("H00852")), None),
        "中证红利": (cached("H00922", lambda: csindex("H00922")), None),
        "创业板指": (cached("sz399006", lambda: sina_index("sz399006")), None),
        "科创50": (cached("000688", lambda: csindex("000688")), None),
        "标普500": (cached("SP500TR", lambda: yahoo("^SP500TR")), "USD"),
        "纳指100": (cached("QQQ", lambda: yahoo("QQQ")), "USD"),
        "日经225": (add_dividend(cached("N225", lambda: yahoo("^N225", "close")), nk_y), "JPY"),
        "富时100": (add_dividend(cached("FTSE", lambda: yahoo("^FTSE", "close")), uk_y), "GBP"),
        "黄金": (cached("XAU", xau), "USD"),
    }
    m_local, m_cny = {}, {}
    for name, (s, ccy) in local.items():
        ml = s.resample("ME").last().dropna()
        m_local[name] = ml
        if ccy:
            f = fx[ccy].resample("ME").last().reindex(ml.index).ffill()
            m_cny[name] = (ml * f).dropna()
        else:
            m_cny[name] = ml
    return pd.DataFrame(m_local), pd.DataFrame(m_cny), nk_y, uk_y


# ---------------- 统计 ----------------

def perf(s, rf=RF):
    s = s.dropna()
    r = s.pct_change().dropna()
    yrs = len(r) / 12
    cagr = (s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1
    vol = r.std() * np.sqrt(12)
    dd = s / s.cummax() - 1
    roll12 = (s / s.shift(12) - 1).dropna()
    roll60 = (s / s.shift(60) - 1).dropna()

    def sub(n):
        return (s.iloc[-1] / s.iloc[-1 - n]) ** (12 / n) - 1 if len(s) > n else np.nan

    return {
        "起始": s.index[0].strftime("%Y-%m"), "年数": round(yrs, 1),
        "年化收益": cagr, "年化波动": vol, "夏普": (cagr - rf) / vol,
        "最大回撤": dd.min(), "卡玛比": cagr / abs(dd.min()) if dd.min() < 0 else np.nan,
        "最差12月": roll12.min(), "近10年年化": sub(120), "近5年年化": sub(60),
        "5年滚动盈利概率": (roll60 > 0).mean() if len(roll60) else np.nan,
    }


def fmt_table(rows):
    df = pd.DataFrame(rows).T
    pct = ["年化收益", "年化波动", "最大回撤", "最差12月", "近10年年化", "近5年年化", "5年滚动盈利概率"]
    out = df.copy()
    for c in pct:
        out[c] = df[c].map(lambda x: "" if pd.isna(x) else f"{x:.1%}")
    for c in ["夏普", "卡玛比"]:
        out[c] = df[c].map(lambda x: "" if pd.isna(x) else f"{x:.2f}")
    return out


# ---------------- 组合优化 ----------------

def _cons(n, cap):
    return [{"type": "eq", "fun": lambda w: w.sum() - 1}], [(0, cap)] * n


def w_minvar(R, cap=CAP):
    S = R.cov().values * 12
    n = len(S)
    cons, b = _cons(n, cap)
    return minimize(lambda w: w @ S @ w, np.ones(n) / n, bounds=b, constraints=cons, method="SLSQP").x


def w_maxsharpe(R, cap=CAP, rf=RF):
    mu = R.mean().values * 12
    S = R.cov().values * 12
    n = len(S)
    cons, b = _cons(n, cap)
    f = lambda w: -(w @ mu - rf) / np.sqrt(w @ S @ w)
    return minimize(f, np.ones(n) / n, bounds=b, constraints=cons, method="SLSQP").x


def w_riskparity(R, cap=1.0):
    S = R.cov().values * 12
    n = len(S)
    cons, b = _cons(n, cap)

    def f(w):
        rc = w * (S @ w)
        return ((rc - rc.sum() / n) ** 2).sum() * 1e4

    return minimize(f, np.ones(n) / n, bounds=[(1e-4, cap)] * n, constraints=cons, method="SLSQP").x


def backtest(R, w):
    """固定目标权重、月度再平衡。"""
    pr = (R * pd.Series(w, index=R.columns)).sum(axis=1)
    return (1 + pr).cumprod()


def walk_forward(R, fn, lookback=60):
    """每年末用过去 lookback 个月数据估计权重，持有下一年（月度再平衡回目标权重）。"""
    out, weights = [], {}
    years = sorted(set(R.index.year))
    for y in years:
        est = R[R.index < pd.Timestamp(f"{y}-01-01")].tail(lookback)
        test = R[R.index.year == y]
        if len(est) < lookback or test.empty:
            continue
        w = fn(est)
        weights[y] = w
        out.append((test * w).sum(axis=1))
    pr = pd.concat(out)
    return (1 + pr).cumprod(), pd.DataFrame(weights, index=R.columns).T


def main():
    m_local, m_cny, nk_y, uk_y = load()
    print("日经225 估算股息率(1321.T):", nk_y.round(4).to_dict())
    print("富时100 估算股息率(ISF.L):", uk_y.round(4).to_dict())

    m_cny = m_cny[m_cny.index >= START]
    m_local = m_local[m_local.index >= START]
    last = m_cny.index[-1]

    # 1) 单资产对比（各自可得区间，人民币计价）
    rows = {k: perf(m_cny[k]) for k in m_cny.columns}
    tbl = fmt_table(rows)
    fx_eff = {}
    for k in ["标普500", "纳指100", "日经225", "富时100", "黄金"]:
        a = perf(m_local[k])["年化收益"]
        fx_eff[k] = f"本币 {a:.1%} → 人民币 {rows[k]['年化收益']:.1%}"
    print(f"\n=== 单资产风险收益（人民币计价，{START[:7]} ~ {last:%Y-%m}，月度数据）===")
    print(tbl.to_string())
    print("\n汇率影响：")
    for k, v in fx_eff.items():
        print(f"  {k}: {v}")

    # 2) 相关性（共同区间，排除历史太短的创业板/科创50）
    core = ["沪深300", "中证500", "中证1000", "中证红利", "标普500", "纳指100", "日经225", "富时100", "黄金"]
    R = m_cny[core].dropna().pct_change().dropna()
    corr = R.corr()
    print(f"\n=== 月收益相关系数（{R.index[0]:%Y-%m} ~ {R.index[-1]:%Y-%m}）===")
    print(corr.round(2).to_string())

    # 3) 组合：全样本（后视镜）与滚动样本外（真实可复制）
    fixed = {"中证红利": .20, "沪深300": .10, "中证1000": .10, "标普500": .20,
             "纳指100": .10, "日经225": .05, "富时100": .05, "黄金": .20}
    w_fixed = np.array([fixed.get(c, 0) for c in core])
    w_eq = np.ones(len(core)) / len(core)
    w_300 = np.array([1.0 if c == "沪深300" else 0 for c in core])

    ins = {"全样本-最小方差": w_minvar(R), "全样本-最大夏普": w_maxsharpe(R), "全样本-风险平价": w_riskparity(R)}
    print("\n=== 全样本优化权重（含后视镜偏差，仅供参考）===")
    print(pd.DataFrame(ins, index=core).T.map(lambda x: f"{x:.0%}").to_string())

    wf = {}
    wf_w = {}
    for nm, fn in [("滚动-最小方差", w_minvar), ("滚动-最大夏普", w_maxsharpe), ("滚动-风险平价", w_riskparity)]:
        wf[nm], wf_w[nm] = walk_forward(R, fn)
    t0 = min(s.index[0] for s in wf.values())
    Rt = R[R.index >= t0]

    curves = {
        "100%沪深300": backtest(Rt, w_300),
        "100%标普500": backtest(Rt, np.array([1.0 if c == "标普500" else 0 for c in core])),
        "等权9资产": backtest(Rt, w_eq),
        "均衡配置(事先设定)": backtest(Rt, w_fixed),
        **{k: backtest(Rt, w) for k, w in ins.items()},
        **{k: v[v.index >= t0] for k, v in wf.items()},
    }
    prow = {}
    for k, c in curves.items():
        c = pd.concat([pd.Series([1.0], index=[t0 - pd.offsets.MonthEnd(1)]), c])
        curves[k] = c
        prow[k] = perf(c)
    ptbl = fmt_table(prow).drop(columns=["起始", "年数"])
    print(f"\n=== 组合回测（{t0:%Y-%m} ~ {last:%Y-%m}，人民币，月度再平衡，不计成本）===")
    print(ptbl.to_string())

    print("\n=== 滚动-风险平价 最新一年权重 / 滚动-最大夏普 最新一年权重 ===")
    print(pd.DataFrame({"风险平价": wf_w["滚动-风险平价"].iloc[-1], "最大夏普": wf_w["滚动-最大夏普"].iloc[-1],
                        "均衡配置": pd.Series(w_fixed, index=core)}).map(lambda x: f"{x:.0%}").to_string())

    # 4) 输出 JSON 给 HTML 报告
    def ser(s):
        return [[d.strftime("%Y-%m"), round(float(v), 4)] for d, v in s.dropna().items()]

    base = m_cny[core + ["创业板指", "科创50"]]
    norm = {k: ser(base[k].dropna() / base[k].dropna().iloc[0]) for k in base.columns}
    dd = {k: ser(c / c.cummax() - 1) for k, c in curves.items()}
    payload = {
        "asOf": f"{last:%Y-%m}", "start": START[:7], "testStart": f"{t0:%Y-%m}",
        "assetTable": json.loads(tbl.reset_index().rename(columns={"index": "资产"}).to_json(orient="records", force_ascii=False)),
        "fxEffect": fx_eff,
        "corr": {"labels": core, "data": [[i, j, round(float(corr.iloc[i, j]), 2)] for i in range(len(core)) for j in range(len(core))]},
        "assetCurves": norm,
        "portTable": json.loads(ptbl.reset_index().rename(columns={"index": "组合"}).to_json(orient="records", force_ascii=False)),
        "portCurves": {k: ser(c) for k, c in curves.items()},
        "portDD": dd,
        "weights": {
            "均衡配置(事先设定)": {c: round(float(w), 3) for c, w in zip(core, w_fixed)},
            **{k: {c: round(float(w), 3) for c, w in zip(core, v)} for k, v in ins.items()},
            "滚动-风险平价(最新)": {c: round(float(w), 3) for c, w in wf_w["滚动-风险平价"].iloc[-1].items()},
            "滚动-最大夏普(最新)": {c: round(float(w), 3) for c, w in wf_w["滚动-最大夏普"].iloc[-1].items()},
        },
        "divYield": {"日经225": {int(k): round(float(v), 4) for k, v in nk_y.items()},
                     "富时100": {int(k): round(float(v), 4) for k, v in uk_y.items()}},
    }
    with open(os.path.join(OUT, "global_portfolio.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    with open(os.path.join(HERE, "templates", "global_portfolio.html"), encoding="utf-8") as f:
        html = f.read().replace("__DATA__", json.dumps(payload, ensure_ascii=False))
    report = os.path.join(BASE, "reports", f"{datetime.now():%Y-%m-%d}-全球资产配置对比.html")
    os.makedirs(os.path.dirname(report), exist_ok=True)
    with open(report, "w", encoding="utf-8") as f:
        f.write(html)
    print("\n已写出 output/global_portfolio.json 与", os.path.relpath(report, BASE))


if __name__ == "__main__":
    main()

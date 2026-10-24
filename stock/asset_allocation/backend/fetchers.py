# -*- coding: utf-8 -*-
"""数据抓取层：把各数据源统一规整成 [(YYYY-MM-DD, float)]（日期升序、同日去重）。

每个数据源都显式指定日期列和数值列，接口改版导致列名变化时直接报错，
宁可更新失败（保留旧数据），也不悄悄取错列。曾经踩过的坑：
- 乐咕市盈率表同时有“等权滚动市盈率”和“滚动市盈率”，按关键词猜列会取到等权口径（两者相差一倍多）。
- 中证官网全收益指数的第一行常是 2000-01-01 的基日占位，不剔除会把年化收益算低。
"""
import time
import warnings
from datetime import datetime, timedelta

import pandas as pd
import requests

import akshare as ak

warnings.filterwarnings("ignore")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126"}


def to_points(df, date_col, value_col, scale=1.0):
    """DataFrame -> [(YYYY-MM-DD, float)]。列不存在时抛错。"""
    if df is None or len(df) == 0:
        return []
    missing = [c for c in (date_col, value_col) if c not in df.columns]
    if missing:
        raise ValueError(f"接口返回缺少列 {missing}，实际列为 {list(df.columns)[:10]}")
    dates = pd.to_datetime(df[date_col], errors="coerce")
    values = pd.to_numeric(df[value_col], errors="coerce")
    ok = dates.notna() & values.notna()
    dedup = dict(zip(dates[ok].dt.strftime("%Y-%m-%d"), values[ok].astype(float) * scale))
    return sorted(dedup.items())


def _today():
    return datetime.now().strftime("%Y%m%d")


def _ymd(start):
    return start.replace("-", "") if start else "20000101"


def drop_placeholder(points, gap_days=30):
    """剔除最后一个超过 gap_days 的日期断档之前的点（基日占位行）。"""
    cut = 0
    for i in range(1, len(points)):
        if (datetime.fromisoformat(points[i][0]) - datetime.fromisoformat(points[i - 1][0])).days > gap_days:
            cut = i
    return points[cut:]


# ---------- 各数据源 ----------

def fetch_csindex(cfg, start=None):
    df = ak.stock_zh_index_hist_csindex(symbol=cfg["symbol"], start_date=_ymd(start), end_date=_today())
    pts = to_points(df, "日期", "收盘")
    return pts if start else drop_placeholder(pts)


def fetch_sina_index(cfg, start=None):
    return to_points(ak.stock_zh_index_daily(symbol=cfg["symbol"]), "date", "close")


def _yahoo_chart(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = dict(period1=946684800, period2=int(time.time()) + 86400, interval="1d", events="div,split")
    r = requests.get(url, params=params, headers=UA, timeout=30)
    r.raise_for_status()
    res = r.json()["chart"]["result"]
    if not res:
        raise ValueError(f"Yahoo 没有返回 {symbol} 的数据")
    return res[0]


def fetch_yahoo(cfg, start=None):
    j = _yahoo_chart(cfg["symbol"])
    if cfg.get("field") == "adjclose":
        values = j["indicators"]["adjclose"][0]["adjclose"]
    else:
        values = j["indicators"]["quote"][0]["close"]
    df = pd.DataFrame({"date": pd.to_datetime(j["timestamp"], unit="s").normalize(), "value": values})
    return to_points(df, "date", "value")


def fetch_yahoo_div(cfg, start=None):
    """ETF 年度股息率：当年分红合计 / 当年均价；当年用近 12 个月分红 / 最新价，记在当年 12-31。

    Yahoo 的价格已做拆股调整，但拆股前的分红金额没有调整（如 1321.T 2026-10 的拆股），需按拆股比例还原。
    不在 0.3%~8% 合理区间的年份视为异常，不入库（分析时用有效年份的中位数补齐）。
    """
    j = _yahoo_chart(cfg["symbol"])
    idx = pd.to_datetime(j["timestamp"], unit="s").normalize()
    close = pd.Series(j["indicators"]["quote"][0]["close"], index=idx, dtype=float).dropna()
    ev = j.get("events", {})
    divs = pd.Series({pd.to_datetime(int(v["date"]), unit="s").normalize(): float(v["amount"])
                      for v in ev.get("dividends", {}).values()}, dtype=float).sort_index()
    if divs.empty or close.empty:
        return []
    ratios = []
    for sp in ev.get("splits", {}).values():
        num, den = (float(x) for x in sp["splitRatio"].split(":"))
        sd = pd.to_datetime(int(sp["date"]), unit="s").normalize()
        divs[divs.index < sd] = divs[divs.index < sd] * den / num
        ratios.append(num / den)
    # Yahoo 偶尔对个别分红重复做拆股调整：单笔股息率不合理时尝试按拆股比例修正
    px = close.reindex(close.index.union(divs.index)).ffill()
    for d, amt in divs.items():
        y0 = amt / px[d] if px[d] > 0 else 0
        if 0.0005 <= y0 <= 0.1:
            continue
        fixes = [amt * r ** k for r in ratios for k in (1, -1, 2, -2)]
        divs[d] = next((f for f in fixes if 0.0005 <= f / px[d] <= 0.1), float("nan"))
    divs = divs.dropna()
    if divs.empty:
        return []
    first_div_year = divs.index[0].year
    cur = close.index[-1].year
    out = []
    for y in range(max(close.index[0].year + 1, first_div_year), cur):
        yld = divs[divs.index.year == y].sum() / close[close.index.year == y].mean()
        out.append((f"{y}-12-31", yld))
    ttm = divs[divs.index > close.index[-1] - pd.Timedelta(days=365)].sum() / close.iloc[-1]
    out.append((f"{cur}-12-31", ttm))
    return [(d, float(v)) for d, v in out if 0.003 <= v <= 0.08]


def fetch_sina_xau(cfg, start=None):
    return to_points(ak.futures_foreign_hist(symbol="XAU"), "date", "close")


def fetch_boc_fx(cfg, start=None):
    """中行折算价（缺失时用央行中间价），牌价单位是每 100 外币，换算成每 1 单位外币。"""
    df = ak.currency_boc_sina(symbol=cfg["symbol"], start_date=_ymd(start), end_date=_today())
    for col in ("日期", "中行折算价", "央行中间价"):
        if col not in df.columns:
            raise ValueError(f"接口返回缺少列 {col}，实际列为 {list(df.columns)}")
    df = df.assign(v=pd.to_numeric(df["中行折算价"], errors="coerce")
                   .fillna(pd.to_numeric(df["央行中间价"], errors="coerce")))
    return to_points(df, "日期", "v", scale=0.01)


def fetch_pe_lg(cfg, start=None):
    return to_points(ak.stock_index_pe_lg(symbol=cfg["symbol"]), "日期", "滚动市盈率")


def fetch_ebs_lg(cfg, start=None):
    return to_points(ak.stock_ebs_lg(), "日期", "股债利差")


def fetch_bond_cn10y(cfg, start=None):
    return to_points(ak.bond_zh_us_rate(start_date=_ymd(start or "2002-01-01")), "日期", "中国国债收益率10年")


_DISPATCH = {
    "csindex": fetch_csindex,
    "sina_index": fetch_sina_index,
    "yahoo": fetch_yahoo,
    "yahoo_div": fetch_yahoo_div,
    "sina_xau": fetch_sina_xau,
    "boc_fx": fetch_boc_fx,
    "pe_lg": fetch_pe_lg,
    "ebs_lg": fetch_ebs_lg,
    "bond_cn10y": fetch_bond_cn10y,
}
# 只有这些数据源支持按起始日期增量抓取，其余每次取全量后按日期覆盖
INCREMENTAL = {"csindex", "boc_fx", "bond_cn10y"}


def fetch_by_cfg(cfg, start=None):
    fn = _DISPATCH.get(cfg["source"])
    if fn is None:
        raise ValueError(f"未知数据源 {cfg['source']}")
    return fn(cfg, start if cfg["source"] in INCREMENTAL else None)


def incremental_start(last_date, buffer_days=14):
    """从最后日期往前回溯 buffer_days 天，覆盖数据源对近期数据的修订。"""
    if not last_date:
        return None
    return (datetime.fromisoformat(last_date) - timedelta(days=buffer_days)).strftime("%Y-%m-%d")


# ---------- 快照类数据（只有最新值，没有历史） ----------

def fetch_snapshots():
    """中证官网指数估值（最近 20 个交易日）与申万一级行业估值。单项失败不影响其他项。"""
    out, errors = {}, []
    idx = {}
    for code, name in [("000300", "沪深300"), ("000510", "中证A500"), ("000922", "中证红利"), ("000905", "中证500"),
                       ("000852", "中证1000"), ("000688", "科创50"), ("931643", "科创创业50")]:
        try:
            df = ak.stock_zh_index_value_csindex(symbol=code)
            for col in ("日期", "市盈率2", "股息率2"):
                if col not in df.columns:
                    raise ValueError(f"缺少列 {col}")
            row = df.sort_values("日期").iloc[-1]
            idx[name] = dict(date=str(pd.to_datetime(row["日期"]).date()),
                             pe=float(row["市盈率2"]), dividend_yield=float(row["股息率2"]))
        except Exception as e:
            errors.append(f"中证估值 {name}: {type(e).__name__} {str(e)[:80]}")
    out["csindex_value"] = idx
    try:
        df = ak.sw_index_first_info()
        cols = ["行业名称", "成份个数", "TTM(滚动)市盈率", "市净率", "静态股息率"]
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise ValueError(f"缺少列 {missing}")
        out["sw_industry"] = [dict(name=r["行业名称"], count=int(r["成份个数"]), pe_ttm=float(r["TTM(滚动)市盈率"]),
                                   pb=float(r["市净率"]), dividend_yield=float(r["静态股息率"]))
                              for _, r in df.iterrows()]
    except Exception as e:
        errors.append(f"申万行业估值: {type(e).__name__} {str(e)[:80]}")
    out["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    return out, errors

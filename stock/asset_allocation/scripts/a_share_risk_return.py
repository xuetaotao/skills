# -*- coding: utf-8 -*-
"""A 股主要指数风险收益、估值与申万行业估值一览（数据源 AKShare）。"""
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

import akshare as ak

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)
pd.set_option("display.max_rows", 100)


def stats(name, s, rf=0.02):
    s = s.dropna()
    s = s[s > 0]
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    cagr = (s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1
    r = s.pct_change().dropna()
    vol = r.std() * np.sqrt(252)
    dd = s / s.cummax() - 1
    trough = dd.idxmin()
    peak = s[:trough].idxmax()
    res = {"指数": name, "起": s.index[0].date(), "止": s.index[-1].date(),
           "最新": round(s.iloc[-1], 1), "年数": round(yrs, 1),
           "年化": f"{cagr:.2%}", "年化波动": f"{vol:.1%}",
           "夏普(rf2%)": round((cagr - rf) / vol, 2),
           "最大回撤": f"{dd.min():.1%}", "回撤区间": f"{peak.date()}~{trough.date()}",
           "距历史高点": f"{s.iloc[-1] / s.max() - 1:.1%}"}
    for y in (1, 3, 5, 10):
        n = 252 * y
        if len(s) > n + 50:
            rr = (s.shift(-n) / s - 1).dropna()
            res[f"持{y}年盈利概率"] = f"{(rr > 0).mean():.0%}"
            res[f"持{y}年年化中位"] = f"{((1 + rr.median()) ** (1 / y) - 1):.1%}"
    return res


def idx(symbol):
    df = ak.stock_zh_index_daily(symbol=symbol)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")["close"].astype(float)


def main():
    rows, series = [], {}
    for sym, nm in [("sh000001", "上证指数"), ("sh000300", "沪深300"),
                    ("sh000905", "中证500"), ("sz399006", "创业板指"),
                    ("sh000922", "中证红利")]:
        try:
            s = idx(sym)
            series[nm] = s
            rows.append(stats(nm, s))
        except Exception as e:
            print("ERR", nm, e)

    for code, nm in [("H00300", "沪深300全收益"), ("H00922", "中证红利全收益")]:
        try:
            df = ak.stock_zh_index_hist_csindex(symbol=code, start_date="20000101",
                                                end_date=datetime.now().strftime("%Y%m%d"))
            df["日期"] = pd.to_datetime(df["日期"])
            rows.append(stats(nm, df.set_index("日期")["收盘"].astype(float)))
        except Exception as e:
            print("ERR", nm, e)

    print("=== 指数风险收益 ===")
    print(pd.DataFrame(rows).set_index("指数").T.to_string())

    if "上证指数" in series:
        s = series["上证指数"]
        print("\n上证 2007-10-16 收盘:", s.loc["2007-10-16"], " 最新:", s.iloc[-1])
        yearly = s.resample("YE").last().pct_change().dropna()
        print("上证年度涨跌%(近12年):")
        print((yearly.tail(12) * 100).round(1).to_string())

    print("\n=== 估值 ===")
    for nm in ["沪深300", "中证500", "上证50", "创业板50"]:
        try:
            df = ak.stock_index_pe_lg(symbol=nm)
            col = [c for c in df.columns if "滚动市盈率" in c and "中位" not in c][0]
            v = df[col].astype(float)
            d = pd.to_datetime(df["日期"])
            last10 = v[d >= d.max() - pd.Timedelta(days=3652)]
            print(nm, df["日期"].iloc[-1], col, round(v.iloc[-1], 2),
                  "近10年分位", f"{(last10 < v.iloc[-1]).mean():.0%}")
        except Exception as e:
            print("ERR pe", nm, e)

    try:
        df = ak.stock_ebs_lg()
        print("\n股债利差(沪深300):")
        print(df.tail(3).to_string())
        c = [x for x in df.columns if "利差" in x and "均线" not in x][0]
        v = df[c].astype(float)
        print("当前", round(v.iloc[-1], 4), "全历史分位", f"{(v < v.iloc[-1]).mean():.0%}")
    except Exception as e:
        print("ERR ebs", e)

    try:
        df = ak.bond_zh_us_rate(start_date="20250101")
        print("\n中国10年国债:", df[["日期", "中国国债收益率10年"]].dropna().tail(1).to_string(index=False))
    except Exception as e:
        print("ERR bond", e)

    print("\n=== 申万一级行业估值 ===")
    try:
        print(ak.sw_index_first_info().to_string())
    except Exception as e:
        print("ERR sw", e)


if __name__ == "__main__":
    main()

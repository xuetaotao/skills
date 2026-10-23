# -*- coding: utf-8 -*-
"""探测全球指数 / 黄金 / 汇率数据接口可用性与历史长度。"""
import warnings

import akshare as ak

warnings.filterwarnings("ignore")


def show(name, fn):
    try:
        df = fn()
        print(f"OK  {name}: {len(df)} 行, 列={list(df.columns)[:8]}")
        print("    首:", df.iloc[0].tolist()[:6])
        print("    末:", df.iloc[-1].tolist()[:6])
        return df
    except Exception as e:
        print(f"ERR {name}: {type(e).__name__} {str(e)[:150]}")


for nm in ["日经225", "英国富时100"]:
    show(f"东财全球 {nm}", lambda nm=nm: ak.index_global_hist_em(symbol=nm))

raw = show("SPY raw", lambda: ak.stock_us_daily(symbol="SPY", adjust=""))
show("SPY qfq-factor", lambda: ak.stock_us_daily(symbol="SPY", adjust="qfq-factor"))
ewj = show("EWJ raw", lambda: ak.stock_us_daily(symbol="EWJ", adjust=""))
if ewj is not None:
    r = ewj.set_index("date")["close"].pct_change()
    print("EWJ 单日涨跌幅绝对值>25%:", r[r.abs() > 0.25].to_dict())
qqq = show("QQQ raw", lambda: ak.stock_us_daily(symbol="QQQ", adjust=""))
if qqq is not None:
    r = qqq.set_index("date")["close"].pct_change()
    print("QQQ 单日涨跌幅绝对值>25%:", r[r.abs() > 0.25].to_dict())

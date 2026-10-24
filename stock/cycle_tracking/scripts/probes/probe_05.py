# -*- coding: utf-8 -*-
"""第五轮：东财全球期货历史（WTI/Brent/LME铜）+ 能源指数替代"""
import akshare as ak
import inspect
import warnings
warnings.filterwarnings("ignore")

print("futures_global_hist_em 签名:", inspect.signature(ak.futures_global_hist_em))
print("index_global_hist_sina 签名:", inspect.signature(ak.index_global_hist_sina))
print("macro_china_energy_index 签名:", inspect.signature(ak.macro_china_energy_index))
print("macro_china_commodity_price_index 签名:", inspect.signature(ak.macro_china_commodity_price_index))
print()

def show(tag, fn):
    try:
        df = fn()
        if df is None or len(df) == 0:
            print(f"[{tag}] EMPTY")
            return
        print(f"[{tag}] OK rows={len(df)} cols={list(df.columns)[:8]}")
        print(f"    head: {df.head(2).to_dict('records')}")
        print(f"    tail: {df.tail(1).to_dict('records')}")
    except Exception as e:
        print(f"[{tag}] FAIL: {type(e).__name__}: {str(e)[:120]}")
    print()

# 东财全球期货历史
show("全球期货名表(东财)", lambda: ak.futures_global_spot_em())
show("WTI原油(东财全球期货)", lambda: ak.futures_global_hist_em(symbol="WTI原油"))
show("布伦特原油(东财全球期货)", lambda: ak.futures_global_hist_em(symbol="布伦特原油"))
show("LME铜(东财全球期货)", lambda: ak.futures_global_hist_em(symbol="LME铜"))
show("COMEX铜(东财全球期货)", lambda: ak.futures_global_hist_em(symbol="COMEX铜"))
show("纽卡斯尔动力煤(东财全球期货)", lambda: ak.futures_global_hist_em(symbol="纽卡斯尔动力煤"))

# 能源/大宗指数替代
show("中国能源指数", lambda: ak.macro_china_energy_index())
show("大宗商品价格指数", lambda: ak.macro_china_commodity_price_index())

print("done")

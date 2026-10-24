# -*- coding: utf-8 -*-
"""第十一轮：用新浪外盘代码测历史接口（XAU/XAG/HG/LHC/CL）"""
import akshare as ak
import inspect
import warnings
warnings.filterwarnings("ignore")

print("futures_foreign_hist 签名:", inspect.signature(ak.futures_foreign_hist))
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
        print(f"[{tag}] FAIL: {type(e).__name__}: {str(e)[:130]}")
    print()

show("伦敦金XAU(新浪外盘)", lambda: ak.futures_foreign_hist(symbol="XAU"))
show("伦敦银XAG(新浪外盘)", lambda: ak.futures_foreign_hist(symbol="XAG"))
show("COMEX铜HG(新浪外盘)", lambda: ak.futures_foreign_hist(symbol="HG"))
show("LME铜LHC(新浪外盘)", lambda: ak.futures_foreign_hist(symbol="LHC"))
show("WTI原油CL(新浪外盘)", lambda: ak.futures_foreign_hist(symbol="CL"))
show("LME铝AHD(新浪外盘)", lambda: ak.futures_foreign_hist(symbol="AHD"))

# 实时接口也验证一下（多品种）
show("外盘实时XAU+XAG+HG(新浪)", lambda: ak.futures_foreign_commodity_realtime(symbol=["XAU", "XAG", "HG"]))
print("done")

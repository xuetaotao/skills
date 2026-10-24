# -*- coding: utf-8 -*-
"""第八轮：申万行业指数替代源（对照分析用）"""
import akshare as ak
import inspect
import warnings
warnings.filterwarnings("ignore")

print("index_hist_sw 签名:", inspect.signature(ak.index_hist_sw))
print()

def show(tag, fn):
    try:
        df = fn()
        if df is None or len(df) == 0:
            print(f"[{tag}] EMPTY")
            return
        print(f"[{tag}] OK rows={len(df)} cols={list(df.columns)[:8]}")
        print(f"    head: {df.head(1).to_dict('records')}")
        print(f"    tail: {df.tail(1).to_dict('records')}")
    except Exception as e:
        print(f"[{tag}] FAIL: {type(e).__name__}: {str(e)[:130]}")
    print()

show("申万-有色金属指数", lambda: ak.index_hist_sw(symbol="801050", period="day"))
show("申万-煤炭指数", lambda: ak.index_hist_sw(symbol="801950", period="day"))
show("申万-航运指数", lambda: ak.index_hist_sw(symbol="801073", period="day"))
print("done")

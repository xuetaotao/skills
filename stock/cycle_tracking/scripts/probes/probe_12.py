# -*- coding: utf-8 -*-
"""第十二轮：OIL(布伦特?)/LME镍锌锡铅"""
import akshare as ak
import warnings
warnings.filterwarnings("ignore")

def show(tag, fn):
    try:
        df = fn()
        if df is None or len(df) == 0:
            print(f"[{tag}] EMPTY")
            return
        print(f"[{tag}] OK rows={len(df)}")
        print(f"    head: {df.head(1).to_dict('records')}")
        print(f"    tail: {df.tail(1).to_dict('records')}")
    except Exception as e:
        print(f"[{tag}] FAIL: {type(e).__name__}: {str(e)[:130]}")
    print()

show("OIL(布伦特?)", lambda: ak.futures_foreign_hist(symbol="OIL"))
show("LME镍NID", lambda: ak.futures_foreign_hist(symbol="NID"))
show("LME锌ZSD", lambda: ak.futures_foreign_hist(symbol="ZSD"))
show("LME锡SND", lambda: ak.futures_foreign_hist(symbol="SND"))
show("LME铅PBD", lambda: ak.futures_foreign_hist(symbol="PBD"))
show("COMEX金GC", lambda: ak.futures_foreign_hist(symbol="GC"))
print("done")

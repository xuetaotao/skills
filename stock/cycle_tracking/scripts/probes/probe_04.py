# -*- coding: utf-8 -*-
"""第四轮：动力煤现货(生意社)、SCFI、WTI/Brent 历史替代源"""
import akshare as ak
import warnings
warnings.filterwarnings("ignore")

# 1) 搜接口名
for kw in ['wti', 'brent', 'global', 'world', 'export', 'sinabr', 'shanghai_index', 'sse_de']:
    names = sorted(n for n in dir(ak) if kw in n.lower())
    if names:
        print(f"--- {kw} ---")
        for n in names[:15]:
            print(" ", n)
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

import inspect
print("spot_price_qh 签名:", inspect.signature(ak.spot_price_qh))
print("spot_price_table_qh 签名:", inspect.signature(ak.spot_price_table_qh))
print()

# 2) 生意社现货品种表
show("生意社现货品种表", lambda: ak.spot_price_table_qh())

# 3) 动力煤现货历史
show("动力煤现货(生意社)", lambda: ak.spot_price_qh(symbol="动力煤"))
show("炼焦煤现货(生意社)", lambda: ak.spot_price_qh(symbol="炼焦煤"))
show("铜现货(生意社)", lambda: ak.spot_price_qh(symbol="铜"))
show("WTI原油现货(生意社)", lambda: ak.spot_price_qh(symbol="WTI原油"))
show("Brent原油现货(生意社)", lambda: ak.spot_price_qh(symbol="布伦特原油"))

print("done")

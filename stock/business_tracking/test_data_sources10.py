# -*- coding: utf-8 -*-
"""第十轮：上海银/世界黄金协会/新浪外盘品种表"""
import akshare as ak
import inspect
import warnings
warnings.filterwarnings("ignore")

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

# 1) 上金所白银
show("上金所Ag99.99(上海银)", lambda: ak.spot_hist_sge(symbol="Ag99.99"))

# 2) 新浪外盘品种表（list 原样打印）
try:
    lst = ak.futures_foreign_commodity_subscribe_exchange_symbol()
    print(f"[外盘品种表] type={type(lst).__name__} len={len(lst)}")
    print("前30项:", lst[:30] if isinstance(lst, list) else lst)
except Exception as e:
    print(f"[外盘品种表] FAIL: {type(e).__name__}: {str(e)[:130]}")
print()

# 3) 外盘实时接口签名
print("futures_foreign_commodity_realtime 签名:", inspect.signature(ak.futures_foreign_commodity_realtime))
print()

# 4) 世界黄金协会（可能含伦敦金）
show("世界黄金协会-金价", lambda: ak.macro_cons_gold())
show("世界白银协会-银价", lambda: ak.macro_cons_silver())

print("done")

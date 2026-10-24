# -*- coding: utf-8 -*-
"""第九轮：国际定价数据源探测——伦敦金/银/铜（LME）"""
import akshare as ak
import inspect
import warnings
warnings.filterwarnings("ignore")

# 1) 搜接口名
for kw in ['gold', 'silver', 'xau', 'lme', 'london', 'sge', 'precious', 'newyork']:
    names = sorted(n for n in dir(ak) if kw in n.lower())
    if names:
        print(f"--- {kw} ---")
        for n in names[:12]:
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
        print(f"[{tag}] FAIL: {type(e).__name__}: {str(e)[:130]}")
    print()

# 2) 新浪外盘实时品种表（看有没有伦敦金/银/LME铜）
show("外盘品种表(新浪)", lambda: ak.futures_foreign_commodity_subscribe_exchange_symbol())
show("外盘实时行情(新浪)", lambda: ak.futures_foreign_commodity_realtime(subscribe_list=""))

# 3) 上金所（国内金/银现货，与国际价联动）
print("spot_hist_sge 签名:", inspect.signature(ak.spot_hist_sge))
show("上金所Au99.99(上海金)", lambda: ak.spot_hist_sge(symbol="Au99.99"))
show("上金所Ag99.99(上海银)", lambda: ak.spot_hist_sge(symbol="Au(T+D)"))

print("done")

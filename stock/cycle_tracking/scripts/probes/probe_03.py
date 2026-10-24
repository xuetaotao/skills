# -*- coding: utf-8 -*-
"""第三轮：原油接口签名、SCFI替代、现货品种清单、国内期货全覆盖"""
import akshare as ak
import inspect
import warnings
warnings.filterwarnings("ignore")

# 1) energy_oil_hist 签名
print("energy_oil_hist 签名:", inspect.signature(ak.energy_oil_hist))
print("energy_oil_detail 签名:", inspect.signature(ak.energy_oil_detail))
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

# 2) 原油历史（布鲁塞尔能源，无参）
show("energy_oil_hist()", lambda: ak.energy_oil_hist())

# 3) 国内关键期货主力连续（新浪，已验证稳定）
for code, name in [("SC0", "上海原油"), ("FU0", "燃料油"), ("ZC0", "动力煤"),
                   ("JM0", "焦煤"), ("J0", "焦炭"), ("AL0", "沪铝"), ("ZN0", "沪锌"),
                   ("NI0", "沪镍"), ("AU0", "沪金")]:
    show(f"{name}({code})", lambda c=code: ak.futures_main_sina(
        symbol=c, start_date="20160101", end_date="20260919"))

print("done")

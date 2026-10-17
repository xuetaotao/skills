# -*- coding: utf-8 -*-
"""补测：SCFI、煤价、原油历史价格等接口"""
import akshare as ak
import warnings
warnings.filterwarnings("ignore")

# 1) 找 SCFI / 集装箱 / 煤 相关接口名
for kw in ['scfi', 'container', 'cci', 'export_container', 'qh_', 'coal', 'thermal']:
    names = sorted(n for n in dir(ak) if kw in n.lower())
    if names:
        print(f"--- {kw} ---")
        for n in names:
            print(" ", n)
print()

def show(tag, fn):
    try:
        df = fn()
        if df is None or len(df) == 0:
            print(f"[{tag}] EMPTY")
            return
        cols = list(df.columns)
        print(f"[{tag}] OK rows={len(df)} cols={cols[:8]}")
        print(f"    head: {df.head(2).to_dict('records')}")
        print(f"    tail: {df.tail(1).to_dict('records')}")
    except Exception as e:
        print(f"[{tag}] FAIL: {type(e).__name__}: {str(e)[:120]}")
    print()

# 2) 原油历史
show("能源油历史(WTI/Brent等)", lambda: ak.energy_oil_hist(symbol="WTI原油期货价格"))
show("国际原油(布鲁塞尔能源)", lambda: ak.futures_foreign_hist(symbol="WTI原油"))

# 3) 美国原油库存另一接口
show("EIA分项原油库存", lambda: ak.macro_usa_crude_inner())

# 4) LME铜 别的写法
show("LME铜(外盘)", lambda: ak.futures_foreign_hist(symbol="LME铜"))
show("COMEX铜(外盘)", lambda: ak.futures_foreign_hist(symbol="COMEX铜"))
print("done")

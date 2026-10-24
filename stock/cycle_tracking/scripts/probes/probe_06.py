# -*- coding: utf-8 -*-
"""第六轮：代理排查 + 东财push2his直连 + 环渤海煤价/SCFI搜索"""
import os
import akshare as ak
import warnings
warnings.filterwarnings("ignore")

# 1) 代理环境变量
for k in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'NO_PROXY', 'no_proxy', 'ALL_PROXY']:
    v = os.environ.get(k)
    if v:
        print(f"ENV {k}={v}")
print()

# 2) 禁用代理后重试 futures_global_hist_em
os.environ['NO_PROXY'] = '*'
try:
    df = ak.futures_global_hist_em(symbol="B26Z")  # 布伦特原油
    print(f"[布伦特原油 直连] OK rows={len(df)} cols={list(df.columns)[:8]}")
    print(f"    head: {df.head(2).to_dict('records')}")
    print(f"    tail: {df.tail(1).to_dict('records')}")
except Exception as e:
    print(f"[布伦特原油 直连] FAIL: {type(e).__name__}: {str(e)[:150]}")
print()

# 3) 搜环渤海/秦皇岛/SCFI 相关
for kw in ['bohai', 'qhd', 'cctd', 'fenwei', 'pug', 'shenergy', 'sse_net']:
    names = sorted(n for n in dir(ak) if kw in n.lower())
    if names:
        print(f"--- {kw} ---")
        for n in names:
            print(" ", n)

# 4) 全球指数名表里找运价/商品指数
try:
    tb = ak.index_global_name_table()
    print("[全球指数名表] rows=", len(tb), "cols=", list(tb.columns))
    mask = tb.apply(lambda r: r.astype(str).str.contains('SCFI|运价|原油|波罗|BDI|商品|CRB', case=False).any(), axis=1)
    print(tb[mask].to_dict('records'))
except Exception as e:
    print(f"[全球指数名表] FAIL: {type(e).__name__}: {str(e)[:120]}")
print("done")

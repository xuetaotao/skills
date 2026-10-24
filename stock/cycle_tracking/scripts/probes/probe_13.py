# -*- coding: utf-8 -*-
"""第十三轮（2026-10-24）：补数据局限的候选源。在项目根目录运行：python scripts/probes/probe_13.py

实测结论：
- Westmetall：LME 官方现货结算价 + 库存，2008 年起按年分页，当日更新 → 替代滞后的金十 LME 库存
- EIA 官网：WCESTUS1 美国商业原油库存（周度，1982 起）、RWTC / RBRTE 现货价（日度，1986/1987 起）
- 上海航运交易所英文站 currentIndex：只有当期与上期，历史需登录 → 靠每周刷新累积
- 申万二级 801992 航运港口：2021-12 起，仍在更新
- 不可用：东方财富期货库存只回溯到 2026-07；金十上期所周报返回空；FRED 访问超时；
  futures_spot_price 无动力煤（ZC）；akshare 的 EIA/API 库存接口停在 2025-09
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend import fetchers  # noqa: E402


def show(tag, fn):
    try:
        rows = fn()
        print(f"[{tag}] OK {len(rows)} 点  {rows[0]} ~ {rows[-1]}")
    except Exception as e:
        print(f"[{tag}] FAIL: {type(e).__name__}: {str(e)[:130]}")


show("Westmetall 铜价(今年)", lambda: fetchers.fetch_westmetall("LME_Cu_cash", "price", "20260101"))
show("Westmetall 铜库存(今年)", lambda: fetchers.fetch_westmetall("LME_Cu_cash", "stock", "20260101"))
show("EIA 商业原油库存", lambda: fetchers.fetch_eia("WCESTUS1", "W"))
show("EIA WTI 现货", lambda: fetchers.fetch_eia("RWTC", "D"))
show("EIA 布伦特现货", lambda: fetchers.fetch_eia("RBRTE", "D"))
show("SSE SCFI", lambda: fetchers.fetch_sse("scfi", "SCFI"))
show("申万航运港口", lambda: fetchers.fetch_sw("801992"))
print("done")

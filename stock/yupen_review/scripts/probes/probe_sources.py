# -*- coding: utf-8 -*-
"""逐个探测数据源（不写数据库）：python scripts/probes/probe_sources.py [代码 ...]

输出每个标的的来源、条数、起止日期、近 60 个交易日最大间隔和最后两根收盘，用来排查某个来源变慢、断档或改版。
"""
import os
import sys
import time
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from backend import fetchers  # noqa: E402
from backend.config import INST, INSTRUMENTS  # noqa: E402


def gap(rows):
    ds = [date.fromisoformat(d) for d, _ in rows[-61:]]
    return max(((b - a).days for a, b in zip(ds, ds[1:])), default=0)


def main():
    codes = sys.argv[1:] or [c for c, *_ in INSTRUMENTS]
    for code in codes:
        inst = INST.get(code)
        if not inst:
            print(f"{code}: 不在标的清单里")
            continue
        t = time.time()
        try:
            src, rows = fetchers.fetch_instrument(inst)
            print(f"{inst['name']:<10} {src:<16} {len(rows):>5} 条 {rows[0][0]} ~ {rows[-1][0]} 最大间隔 {gap(rows)} 天 "
                  f"最后两根 {rows[-2][1]:.2f} → {rows[-1][1]:.2f}  {time.time() - t:.1f}s")
        except Exception as e:  # noqa: BLE001
            print(f"{inst['name']:<10} 失败：{type(e).__name__}: {e}")
    if not sys.argv[1:]:
        for label, fn in (("美元指数", fetchers.fetch_dxy), ("中美国债", lambda: fetchers.fetch_bonds("20260101")),
                          ("蛋卷估值", fetchers.fetch_valuation)):
            t = time.time()
            try:
                src, data = fn()
                n = len(data) if isinstance(data, list) or label == "蛋卷估值" else {k: len(v) for k, v in data.items()}
                print(f"{label:<10} {src} {n}  {time.time() - t:.1f}s")
            except Exception as e:  # noqa: BLE001
                print(f"{label:<10} 失败：{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()

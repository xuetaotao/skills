# -*- coding: utf-8 -*-
"""逐个探测已注册的数据序列和估值快照接口是否可用，只打印结果，不写数据库。

用法（在项目根目录）:
  python scripts/probes/probe_sources.py            # 全部序列（中行汇率较慢，约 3 分钟）
  python scripts/probes/probe_sources.py HSI FX_USD # 指定序列
"""
import os
import sys
import time
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
warnings.filterwarnings("ignore")

from backend import fetchers  # noqa: E402
from backend.config import SERIES, find_series  # noqa: E402


def main():
    codes = sys.argv[1:]
    targets = [find_series(c) for c in codes] if codes else SERIES
    for cfg in targets:
        if cfg is None:
            continue
        t = time.time()
        try:
            rows = fetchers.fetch_by_cfg(cfg, None)
            span = f"{rows[0][0]} → {rows[-1][0]}，{len(rows)} 点，最新值 {rows[-1][1]:.4g}" if rows else "空"
            print(f"OK  {cfg['code']:<12} {cfg['name']:<20} {span}  ({time.time() - t:.1f}s)")
        except Exception as e:
            print(f"ERR {cfg['code']:<12} {cfg['name']:<20} {type(e).__name__}: {str(e)[:150]}")
    if not codes:
        snap, errors = fetchers.fetch_snapshots()
        print(f"{'OK ' if not errors else 'ERR'} SNAPSHOTS    中证估值 {len(snap.get('csindex_value', {}))} 项，"
              f"申万行业 {len(snap.get('sw_industry', []))} 项 {'；'.join(errors)}")


if __name__ == "__main__":
    main()

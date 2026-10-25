# -*- coding: utf-8 -*-
"""逐个探测各数据接口是否可用，只打印结果，不写数据库。

用法（在项目根目录）:
  python scripts/probes/probe_sources.py
"""
import os
import sys
import time
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
warnings.filterwarnings("ignore")

from backend import fetchers  # noqa: E402


def probe(name, fn):
    t = time.time()
    try:
        msg = fn()
        print(f"OK  {name:<16} {msg}  ({time.time() - t:.1f}s)")
    except Exception as e:
        print(f"ERR {name:<16} {type(e).__name__}: {str(e)[:150]}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    probe("上交所 ETF 列表", lambda: f"{len(fetchers.sse_list())} 只")
    probe("上交所份额", lambda: (lambda d, s: f"{len(s)} 只，统计日 {d}，510300 = {s.get('510300', 0) / 1e8:.2f} 亿份")(*fetchers.sse_shares()))
    probe("深交所 ETF 列表", lambda: (lambda rows: f"{len(rows)} 只，有份额 {sum(1 for r in rows if r['shares'])} 只")(fetchers.szse_list()))
    probe("深交所份额日期", lambda: fetchers.szse_shares_date() or "空")
    probe("新浪行情", lambda: (lambda p: f"{len(p)} 只，510300 = {p.get('510300', ('—',))[0]}")(fetchers.sina_prices()))
    probe("腾讯行情", lambda: "、".join(f"{c} {v / 1e8:.1f}亿" for c, v in fetchers.tencent_mcap(["510300", "159915", "511880"]).items()))
    probe("东财黄金跟踪标的", lambda: f"518880 = {fetchers.em_benchmark('518880')}")
    probe("中证指数名称", lambda: f"{len(fetchers.csindex_names())} 个")
    probe("国证指数名称", lambda: f"{len(fetchers.cnindex_names())} 个")


if __name__ == "__main__":
    main()

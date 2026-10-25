# -*- coding: utf-8 -*-
"""逐个探测各数据接口是否可用，只打印结果，不写数据库。

用法（在项目根目录）:
  python scripts/probes/probe_sources.py           # 默认用工商银行、贵州茅台、中国平安、中信证券各测一遍
  python scripts/probes/probe_sources.py 600900    # 指定股票
"""
import os
import sys
import time
import warnings
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
warnings.filterwarnings("ignore")

from backend import fetchers  # noqa: E402


def probe(name, fn):
    t = time.time()
    try:
        msg = fn()
        print(f"OK  {name:<24} {msg}  ({time.time() - t:.1f}s)")
    except Exception as e:
        print(f"ERR {name:<24} {type(e).__name__}: {str(e)[:150]}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    codes = sys.argv[1:] or ["601398", "600519", "601318", "600030"]
    for c in codes:
        def ind(c=c):
            rows = fetchers.fetch_indicators(c)
            if not rows:
                return "空（代码不对，或不是 A 股）"
            latest = max(rows, key=lambda r: r["REPORT_DATE"])
            return (f"{latest['SECURITY_NAME_ABBR']} {latest['ORG_TYPE']}，{len(rows)} 个报告期，"
                    f"最新 {latest['REPORT_DATE'][:10]}（{latest.get('NOTICE_DATE', '')[:10]} 披露）")
        probe(f"财务指标 {c}", ind)
    td = {}
    probe("最新交易日", lambda: td.setdefault("d", fetchers.latest_trade_date(codes[0])) or "空")
    if td.get("d"):
        probe("当日估值", lambda: f"{len(fetchers.fetch_quotes(codes, td['d']))}/{len(codes)} 只")
    probe(f"估值历史 {codes[0]}", lambda: f"{len(fetchers.fetch_valuation_history(codes[0], '2025-01-01'))} 天（2025 年以来）")
    probe("日收盘价", lambda: f"{len(fetchers.fetch_closes(codes, '2026-01-01'))} 条（{len(codes)} 只，2026 年以来）")
    probe(f"复权因子 {codes[0]}", lambda: f"{len(fetchers.fetch_adj_factors(codes[0]))} 个，最近 {fetchers.fetch_adj_factors(codes[0])[-1]}")
    probe("企业性质", lambda: "、".join(f"{r['code']} {r['nature']}" for r in fetchers.fetch_org_info(codes)))
    probe("分红", lambda: f"{len(fetchers.fetch_dividends(codes))} 条")
    probe("10 年期国债收益率", lambda: (lambda r: f"{len(r)} 天，最新 {r[-1][0]} {r[-1][1]}%")(
        fetchers.fetch_cgb10((date.today() - timedelta(days=30)).isoformat())))
    probe("申万行业分类", lambda: f"{len(fetchers.fetch_sw_class())} 只股票")
    probe("申万行业名称", lambda: f"{len(fetchers.fetch_sw_names())} 个行业")
    probe("搜索 gzmt", lambda: "、".join(f"{r['name']}({r['code']})" for r in fetchers.search("gzmt")) or "空")


if __name__ == "__main__":
    main()

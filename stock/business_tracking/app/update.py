# -*- coding: utf-8 -*-
"""数据更新入口。

用法（在项目根目录）:
  venv python -m app.update            # 增量更新全部指标
  venv python -m app.update --full     # 全量重建（慎用，会先清空）
  venv python -m app.update BDI WTI    # 只更新指定指标

输出更新小结：每个指标新增行数 / 最新日期 / 失败原因。
"""
import sys
import time
from datetime import datetime

from . import db, fetchers
from .config import SERIES, find


def update_series(code, full=False):
    cfg = find(code)
    if cfg is None:
        return dict(code=code, ok=False, error="未注册的指标代码")
    last = None if full else db.get_last_date(code)
    start = fetchers.incremental_start(last) if last else None
    try:
        rows = fetchers.fetch_by_cfg(cfg, start)
    except Exception as e:
        return dict(code=code, ok=False, error=f"{type(e).__name__}: {str(e)[:120]}")

    if not rows:
        # 手动补录数据可能尚未提供
        return dict(code=code, ok=True, new=0, last_date=last or "—",
                    note="接口无新数据（或手动补录未提供）")

    if full:
        import sqlite3
        with db.conn() as c:
            c.execute("DELETE FROM points WHERE code=?", (code,))
    new_n = db.upsert_points(code, rows)
    db.set_series_meta(code, cfg["name"], cfg["sector"], cfg["unit"],
                       "W" if cfg["code"] in ("EIA_PROD",) else "D")
    new_last = db.get_last_date(code)
    return dict(code=code, ok=True, new=new_n, last_date=new_last)


def run_update(codes=None, full=False):
    targets = SERIES if not codes else [c for c in (find(x) or dict(code=x) for x in codes)]
    report, failed = [], []
    for cfg in targets:
        code = cfg["code"] if isinstance(cfg, dict) else cfg
        r = update_series(code, full=full)
        report.append(r)
        if not r.get("ok"):
            failed.append(r)
        time.sleep(0.4)  # 对接口友好
    db.set_meta("last_refresh", datetime.now().strftime("%Y-%m-%d %H:%M"))
    return dict(
        at=db.get_meta("last_refresh"),
        total=len(report),
        failed=[f"{r['code']}: {r['error']}" for r in failed],
        detail=report,
    )


def main():
    args = sys.argv[1:]
    full = "--full" in args
    codes = [a for a in args if not a.startswith("--")]
    db.init_db()
    rep = run_update(codes or None, full=full)
    print(f"=== 更新完成 {rep['at']} | 指标 {rep['total']} 个 ===")
    for r in rep["detail"]:
        flag = "✓" if r.get("ok") else "✗"
        print(f" {flag} {r['code']:<14} new={r.get('new','—'):<6} 最新={r.get('last_date','—')} "
              f"{r.get('note') or r.get('error','')}")
    if rep["failed"]:
        print("失败项:", "; ".join(rep["failed"]))


if __name__ == "__main__":
    main()

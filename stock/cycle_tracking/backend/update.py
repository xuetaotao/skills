# -*- coding: utf-8 -*-
"""数据更新入口。

用法（在项目根目录）:
  python -m backend.update              # 增量更新全部指标
  python -m backend.update BDI WTI      # 只更新指定指标
  python -m backend.update --full WTI   # 清空后全量重建指定指标（不带代码则重建全部，慎用）
"""
import json
import math
import sys
import time
from datetime import datetime

from . import db, fetchers
from .config import SERIES, find


def validate(cfg, rows):
    """剔除明显无效的点：非有限数；除运价外不允许 <= 0（运价指数可能为负）。"""
    ok, dropped = [], 0
    for d, v in rows:
        if v is None or not math.isfinite(v) or (cfg["role"] != "freight" and v <= 0):
            dropped += 1
        else:
            ok.append((d, v))
    return ok, dropped


def update_series(cfg, full=False):
    code = cfg["code"]
    last = None if full else db.get_last_date(code)
    try:
        rows = fetchers.fetch_by_cfg(cfg, fetchers.incremental_start(last))
    except Exception as e:
        return dict(code=code, ok=False, error=f"{type(e).__name__}: {str(e)[:160]}")
    rows, dropped = validate(cfg, rows)
    if not rows:
        note = "手动补录文件中没有该指标" if cfg["source"] == "manual" else "接口没有返回新数据"
        return dict(code=code, ok=True, new=0, last_date=last, note=note)
    new = db.replace_points(code, rows, clear=full and not cfg["accumulate"])
    db.set_series_meta(cfg)
    note = f"剔除 {dropped} 个无效点" if dropped else ""
    return dict(code=code, ok=True, new=new, last_date=db.get_last_date(code), note=note)


def run_update(codes=None, full=False, progress=None):
    """progress(done, total, code) 在每个指标开始前回调。"""
    db.init_db()
    targets = [find(c) for c in codes] if codes else SERIES
    unknown = [c for c, t in zip(codes or [], targets) if t is None]
    targets = [t for t in targets if t is not None]
    detail = [dict(code=c, ok=False, error="未注册的指标代码") for c in unknown]
    for i, cfg in enumerate(targets):
        if progress:
            progress(i, len(targets), cfg["code"])
        detail.append(update_series(cfg, full=full))
        time.sleep(0.3)  # 对接口友好
    failed = [f"{r['code']}: {r['error']}" for r in detail if not r["ok"]]
    at = db.now_str()
    if not codes:  # 只更新部分指标时不算一次完整刷新，“上次刷新”时间保持不变
        db.set_meta("last_refresh", at)
        db.set_meta("last_refresh_failed", json.dumps(failed, ensure_ascii=False))
    db.set_meta("data_version", datetime.now().isoformat(timespec="seconds"))
    if progress:
        progress(len(targets), len(targets), None)
    return dict(at=at, total=len(detail), failed=failed, detail=detail)


def main():
    args = sys.argv[1:]
    full = "--full" in args
    codes = [a for a in args if not a.startswith("--")]
    rep = run_update(codes or None, full=full)
    print(f"=== 更新完成 {rep['at']} | 指标 {rep['total']} 个 | 失败 {len(rep['failed'])} 个 ===")
    for r in rep["detail"]:
        flag = "✓" if r["ok"] else "✗"
        print(f" {flag} {r['code']:<14} 新增={r.get('new', '—'):<6} 最新={r.get('last_date') or '—':<10} "
              f"{r.get('note') or r.get('error', '')}")


if __name__ == "__main__":
    main()

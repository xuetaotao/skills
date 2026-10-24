# -*- coding: utf-8 -*-
"""数据更新入口。某个序列抓取失败时保留数据库里的旧数据，并在结果和页面上列出。

用法（在项目根目录）:
  python -m backend.update              # 增量更新全部序列和估值快照
  python -m backend.update HSI FX_USD   # 只更新指定序列
  python -m backend.update --full HSI   # 清空后全量重建指定序列（不带代码则重建全部，慎用）
"""
import json
import math
import sys
import time
from datetime import datetime

from . import db, fetchers
from .config import SERIES, find_series


def validate(cfg, rows):
    """剔除无效点：非有限数；股债利差可以为负，其余必须为正。"""
    ok, dropped = [], 0
    for d, v in rows:
        if v is None or not math.isfinite(v) or (cfg["code"] != "EBS_HS300" and v <= 0):
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
        return dict(code=code, ok=True, new=0, last_date=last, note="接口没有返回新数据")
    new = db.replace_points(code, rows, clear=full)
    db.set_series_meta(cfg)
    return dict(code=code, ok=True, new=new, last_date=db.get_last_date(code),
                note=f"剔除 {dropped} 个无效点" if dropped else "")


def update_snapshots():
    snap, errors = fetchers.fetch_snapshots()
    old = json.loads(db.get_meta("snapshots", "{}") or "{}")
    # 单项失败时沿用上次的结果
    for key in ("csindex_value", "sw_industry"):
        if not snap.get(key) and old.get(key):
            snap[key] = old[key]
    db.set_meta("snapshots", json.dumps(snap, ensure_ascii=False))
    return errors


def run_update(codes=None, full=False, progress=None):
    """progress(done, total, code) 在每个序列开始前回调。不指定 codes 时最后一步更新估值快照。"""
    db.init_db()
    targets = [find_series(c) for c in codes] if codes else SERIES
    unknown = [c for c, t in zip(codes or [], targets) if t is None]
    targets = [t for t in targets if t is not None]
    detail = [dict(code=c, ok=False, error="未注册的序列代码") for c in unknown]
    total = len(targets) + (0 if codes else 1)
    for i, cfg in enumerate(targets):
        if progress:
            progress(i, total, cfg["code"])
        detail.append(update_series(cfg, full=full))
        time.sleep(0.3)  # 对接口友好
    if not codes:
        if progress:
            progress(len(targets), total, "SNAPSHOTS")
        for err in update_snapshots():
            detail.append(dict(code="SNAPSHOTS", ok=False, error=err))
    failed = [f"{r['code']}: {r['error']}" for r in detail if not r["ok"]]
    at = db.now_str()
    if not codes:  # 只更新部分序列时不算完整刷新，“上次刷新”时间保持不变
        db.set_meta("last_refresh", at)
        db.set_meta("last_refresh_failed", json.dumps(failed, ensure_ascii=False))
    db.set_meta("data_version", datetime.now().isoformat(timespec="seconds"))
    if progress:
        progress(total, total, None)
    return dict(at=at, total=len(detail), failed=failed, detail=detail)


def main():
    args = sys.argv[1:]
    full = "--full" in args
    codes = [a for a in args if not a.startswith("--")]
    rep = run_update(codes or None, full=full)
    print(f"=== 更新完成 {rep['at']} | 序列 {rep['total']} 个 | 失败 {len(rep['failed'])} 个 ===")
    for r in rep["detail"]:
        flag = "✓" if r["ok"] else "✗"
        print(f" {flag} {r['code']:<12} 新增={r.get('new', '—'):<6} 最新={r.get('last_date') or '—':<10} "
              f"{r.get('note') or r.get('error', '')}")


if __name__ == "__main__":
    main()

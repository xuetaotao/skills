# -*- coding: utf-8 -*-
"""数据更新：python -m backend.update

逐个获取指数、商品日线和美元指数、中美国债收益率，增量写入 SQLite；某个来源失败时保留数据库里的旧数据。
完成后重写 outputs/latest_review(_simple).md/html。有失败项时以退出码 1 结束，便于 AI 工作流判断数据是否可用。
"""
import logging
import os
import sys
import time
from datetime import datetime, timedelta

from . import db, fetchers, report
from .config import HISTORY_START, INSTRUMENTS, INST

log = logging.getLogger(__name__)


def run_update(progress=None):
    db.init_db()
    t0 = time.time()
    steps = [("inst", c) for c, *_ in INSTRUMENTS] + [("dxy", "DXY"), ("bonds", "BONDS"), ("report", None)]
    failed, ok = [], 0

    def tick(i, label):
        if progress:
            progress(i, len(steps), label)

    for i, (kind, key) in enumerate(steps):
        if kind == "inst":
            inst = INST[key]
            tick(i, inst["name"])
            try:
                source, rows = fetchers.fetch_instrument(inst)
                db.save_prices(key, rows)
                db.save_source(key, source, len(rows), rows[0][0], rows[-1][0], True)
                ok += 1
            except Exception as e:  # noqa: BLE001
                msg = f"{type(e).__name__}: {str(e)[:160]}"
                db.save_source(key, None, 0, None, None, False, msg)
                failed.append(inst["name"])
                log.warning("%s 获取失败：%s", inst["name"], msg)
        elif kind == "dxy":
            tick(i, "美元指数")
            try:
                source, rows = fetchers.fetch_dxy()
                db.save_macro("DXY", rows)
                db.save_source("DXY", source, len(rows), rows[0][0], rows[-1][0], True)
            except Exception as e:  # noqa: BLE001
                db.save_source("DXY", None, 0, None, None, False, f"{type(e).__name__}: {str(e)[:160]}")
                failed.append("美元指数")
        elif kind == "bonds":
            tick(i, "中美国债收益率")
            last = db.last_macro_date("US10年")
            start = (datetime.strptime(last, "%Y-%m-%d") - timedelta(days=20)).strftime("%Y%m%d") if last \
                else HISTORY_START.replace("-", "")
            try:
                source, series = fetchers.fetch_bonds(start)
                n, first, lastd = 0, None, None
                for k, rows in series.items():
                    db.save_macro(k, rows)
                    if rows:
                        n = max(n, len(rows))
                        first = min(first or rows[0][0], rows[0][0])
                        lastd = max(lastd or rows[-1][0], rows[-1][0])
                db.save_source("BONDS", source, n, first, lastd, True)
            except Exception as e:  # noqa: BLE001
                db.save_source("BONDS", None, 0, None, None, False, f"{type(e).__name__}: {str(e)[:160]}")
                failed.append("中美国债收益率")
        else:
            tick(i, "生成复盘汇总")
            db.set_meta("data_version", str(time.time()))
            if db.has_data():
                try:
                    report.write_outputs(missing=failed)
                except Exception as e:  # noqa: BLE001
                    failed.append(f"生成复盘汇总（{type(e).__name__}: {str(e)[:120]}）")
    tick(len(steps), "完成")
    db.set_meta("last_refresh", db.now_str())
    db.set_meta("last_refresh_seconds", f"{time.time() - t0:.0f}")
    db.set_json("last_refresh_failed", failed)
    db.set_meta("data_version", str(time.time()))
    return dict(ok=ok, total=len(INSTRUMENTS), failed=failed, seconds=round(time.time() - t0))


def main():
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    def progress(i, total, label):
        print(f"[{i}/{total}] {label}", flush=True)

    rep = run_update(progress)
    from . import analytics
    data = analytics.rows()
    print(f"\n完成：{rep['ok']}/{rep['total']} 个标的更新成功，用时 {rep['seconds']} 秒；数据日期 {data['date'] if data else '无'}")
    print(f"已写入 {os.path.join(report.OUTPUTS, 'latest_review_simple.md')} 等文件")
    if rep["failed"]:
        print(f"失败：{'、'.join(rep['failed'])}（表中为数据库里的旧数据，复盘前请先确认）")
        sys.exit(1)


if __name__ == "__main__":
    main()

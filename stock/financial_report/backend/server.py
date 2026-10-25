# -*- coding: utf-8 -*-
"""FastAPI 服务：uvicorn backend.server:app --port 8323

提供页面、数据 API 和后台刷新。每次启动都会在后台更新自选股及其同行业的数据（数据库为空时全量下载）；
设置环境变量 FIN_AUTO_REFRESH=0 可关闭（首次初始化除外）。
"""
import os
import re
import threading
import traceback
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import analytics, db, fetchers, glossary
from .config import (DEFAULT_WATCHLIST, KEY_METRICS, METRICS, NATURES, NEW_DAYS, PEER_MAX, PEER_MAX_L1, PERF_PERIODS,
                     TYPE_NAMES, VAL_FOCUS, VALUATION_START)
from .update import run_update

BASE = Path(__file__).resolve().parent.parent
FRONTEND = BASE / "frontend"
REPORTS = BASE / "reports"

_state = dict(updating=False, reason=None, done=0, total=0, current=None, last_error=None, queue=[])
_state_lock = threading.Lock()


def start_refresh(reason, codes=None):
    """后台线程更新。codes=None 为完整刷新；正在刷新时把 codes 排进队列，当前任务结束后接着更新。"""
    with _state_lock:
        if _state["updating"]:
            if codes:
                _state["queue"] = list(dict.fromkeys(_state["queue"] + list(codes)))
            return False
        _state.update(updating=True, reason=reason, done=0, total=0, current=None, last_error=None)

    def progress(done, total, label):
        _state.update(done=done, total=total, current=label)

    def job(todo):
        errors = []
        try:
            while True:
                rep = run_update(todo, progress=progress)
                errors += rep["failed"]
                with _state_lock:
                    todo = _state["queue"]
                    _state["queue"] = []
                    if not todo:
                        break
                    _state.update(reason="添加自选股", done=0, total=0)
            if errors:
                _state["last_error"] = f"{len(errors)} 项有问题：" + "；".join(errors[:3])
        except Exception:
            _state["last_error"] = traceback.format_exc()[-300:]
        finally:
            _state.update(updating=False, current=None)

    threading.Thread(target=job, args=(codes,), daemon=True).start()
    return True


def _needs_auto_refresh():
    if not db.has_data():
        return "首次运行，正在初始化数据"
    if os.environ.get("FIN_AUTO_REFRESH", "1") == "0":
        return None
    return "启动时自动更新"


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    db.ensure_default_watchlist(DEFAULT_WATCHLIST)
    reason = _needs_auto_refresh()
    if reason:
        start_refresh(reason)
    yield


app = FastAPI(title="财报追踪台", lifespan=lifespan)


def _snap():
    if not db.has_data():
        raise HTTPException(503, "数据初始化中，请稍候")
    return analytics.snapshot()


def _touch_watch():
    db.set_meta("watch_version", datetime.now().isoformat(timespec="microseconds"))


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/api/status")
def status():
    return dict(
        updating=_state["updating"], reason=_state["reason"], done=_state["done"], total=_state["total"],
        current=_state["current"], last_error=_state["last_error"], queue=_state["queue"],
        last_refresh=db.get_meta("last_refresh"), empty=not db.has_data(), trade_date=db.get_meta("trade_date"),
        failed=len(db.get_json("last_refresh_failed", [])), watch=len(db.watchlist()),
    )


@app.post("/api/refresh")
def refresh():
    started = start_refresh("手动刷新")
    return dict(started=started, reason=None if started else "已在刷新中")


@app.get("/api/meta")
def meta():
    return dict(metrics=METRICS, types=TYPE_NAMES, key_metrics=KEY_METRICS, val_focus=VAL_FOCUS,
                valuation_start=VALUATION_START, new_days=NEW_DAYS, peer_max=PEER_MAX, peer_max_l1=PEER_MAX_L1,
                perf_periods=[dict(key=k, label=lb) for k, lb, _ in PERF_PERIODS], natures=NATURES)


# ---------- 自选股 ----------

class CodeIn(BaseModel):
    code: str
    undo: bool = False  # 撤销刚才的移除：数据都还在，不必重新下载


class OrderIn(BaseModel):
    codes: list[str]


@app.get("/api/search")
def search(q: str):
    try:
        res = fetchers.search(q)
    except Exception as e:
        raise HTTPException(502, f"搜索服务暂时不可用：{e}")
    watch = set(db.watchlist())
    return [dict(r, watched=r["code"] in watch) for r in res]


@app.post("/api/watchlist")
def add_watch(body: CodeIn):
    code = re.sub(r"\D", "", body.code)
    if not re.fullmatch(r"\d{6}", code):
        raise HTTPException(400, "请输入 6 位股票代码，或在搜索结果里选择")
    if code in db.watchlist():
        return dict(ok=True, code=code, existed=True)
    if code not in db.report_codes():
        try:
            rows = fetchers.fetch_indicators(code)
        except Exception as e:
            raise HTTPException(502, f"获取财报失败：{e}")
        if not rows:
            raise HTTPException(400, f"{code} 没有找到 A 股财报数据（B 股、基金、已退市股票不支持）")
        db.save_reports(code, rows)
        latest = max(rows, key=lambda r: r["REPORT_DATE"])
        db.upsert_stock(code, latest.get("SECURITY_NAME_ABBR"), latest.get("ORG_TYPE"))
        db.set_meta("data_version", datetime.now().isoformat(timespec="seconds"))
    db.add_watch(code)
    _touch_watch()
    refresh = not (body.undo and db.load_valuation(code))
    if refresh:
        start_refresh("添加自选股", codes=[code])
    return dict(ok=True, code=code, name=(db.load_stocks().get(code) or {}).get("name"), refresh=refresh)


@app.delete("/api/watchlist/{code}")
def remove_watch(code: str):
    db.remove_watch(code)
    _touch_watch()
    return dict(ok=True)


@app.put("/api/watchlist")
def reorder_watch(body: OrderIn):
    db.reorder_watch(body.codes)
    if not analytics.reorder_watch(db.watchlist()):
        _touch_watch()
    return dict(ok=True)


# ---------- 页面数据 ----------

@app.get("/api/overview")
def overview():
    s = _snap()
    return dict(headline=s.headline(), cards=[s.cards[c] for c in s.watch if c in s.cards],
                missing=[c for c in s.watch if c not in s.cards], trade_date=s.trade_date)


@app.get("/api/compare")
def compare(scope: str = "watch", period: str = None):
    s = _snap()
    res = s.compare(scope, period)
    if res is None:
        raise HTTPException(404, "没有这个对比范围")
    return dict(res, scopes=s.scopes())


@app.get("/api/stock/{code}")
def stock(code: str):
    res = _snap().stock(code)
    if res is None:
        raise HTTPException(404, f"没有 {code} 的数据。可以先把它加入自选股。")
    return res


@app.get("/api/health")
def health():
    return _snap().health()


@app.get("/api/glossary")
def glossary_api():
    return glossary.GLOSSARY


@app.get("/api/reports")
def reports_list():
    if not REPORTS.exists():
        return []
    return sorted((p.name for p in REPORTS.iterdir() if p.suffix == ".html"), reverse=True)


app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")
app.mount("/reports", StaticFiles(directory=str(REPORTS)), name="reports")

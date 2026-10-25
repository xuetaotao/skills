# -*- coding: utf-8 -*-
"""FastAPI 服务：uvicorn backend.server:app --port 8324

每次启动都会在后台更新 ETF 列表、份额和价格并保存当日快照；设置环境变量 ETF_AUTO_REFRESH=0 可关闭（首次初始化除外）。
"""
import os
import threading
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import analytics, db, glossary
from .config import CATEGORIES, CHANGE_WINDOWS, CROSSCHECK_TOP, CROSSCHECK_WARN, DEFAULT_THRESHOLD
from .update import run_update

BASE = Path(__file__).resolve().parent.parent
FRONTEND = BASE / "frontend"
REPORTS = BASE / "reports"

_state = dict(updating=False, reason=None, done=0, total=0, current=None, last_error=None)
_state_lock = threading.Lock()


def start_refresh(reason):
    with _state_lock:
        if _state["updating"]:
            return False
        _state.update(updating=True, reason=reason, done=0, total=0, current=None, last_error=None)

    def progress(done, total, label):
        _state.update(done=done, total=total, current=label)

    def job():
        try:
            rep = run_update(progress=progress)
            if rep["failed"]:
                _state["last_error"] = f"{len(rep['failed'])} 项有问题：" + "；".join(rep["failed"][:3])
        except Exception:
            _state["last_error"] = traceback.format_exc()[-300:]
        finally:
            _state.update(updating=False, current=None)

    threading.Thread(target=job, daemon=True).start()
    return True


def _needs_auto_refresh():
    if not db.has_data():
        return "首次运行，正在初始化数据"
    if os.environ.get("ETF_AUTO_REFRESH", "1") == "0":
        return None
    return "启动时自动更新"


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    reason = _needs_auto_refresh()
    if reason:
        start_refresh(reason)
    yield


app = FastAPI(title="ETF 规模筛选", lifespan=lifespan)


def _snap():
    if not db.has_data():
        raise HTTPException(503, "数据初始化中，请稍候")
    return analytics.snapshot()


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
        current=_state["current"], last_error=_state["last_error"], empty=not db.has_data(),
        last_refresh=db.get_meta("last_refresh"), snapshot_date=db.get_meta("snapshot_date"),
        failed=len(db.get_json("last_refresh_failed", [])),
    )


@app.post("/api/refresh")
def refresh():
    started = start_refresh("手动刷新")
    return dict(started=started, reason=None if started else "已在刷新中")


@app.get("/api/meta")
def meta():
    return dict(categories=CATEGORIES, threshold=DEFAULT_THRESHOLD, windows=CHANGE_WINDOWS,
                crosscheck_top=CROSSCHECK_TOP, crosscheck_warn=CROSSCHECK_WARN)


@app.get("/api/list")
def listing():
    return _snap().listing()


@app.get("/api/index/{key}")
def index_detail(key: str):
    res = _snap().index(key)
    if res is None:
        raise HTTPException(404, f"没有跟踪 {key} 的 ETF")
    return res


@app.get("/api/etf/{code}")
def etf_detail(code: str):
    res = _snap().etf(code)
    if res is None:
        raise HTTPException(404, f"没有 {code} 这只 ETF")
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

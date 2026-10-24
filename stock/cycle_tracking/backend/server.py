# -*- coding: utf-8 -*-
"""FastAPI 服务：uvicorn backend.server:app --port 8321

提供页面、数据 API 和后台刷新。每次启动都会在后台自动增量更新（数据库为空时全量下载）；
设置环境变量 CYCLE_AUTO_REFRESH=0 可关闭（首次初始化除外）。
"""
import os
import threading
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import analyzer, db, glossary
from .config import SECTORS, SERIES, find
from .update import run_update

BASE = Path(__file__).resolve().parent.parent
FRONTEND = BASE / "frontend"
REPORTS = BASE / "reports"

_state = dict(updating=False, reason=None, done=0, total=0, current=None, last_error=None)
_state_lock = threading.Lock()


def start_refresh(reason):
    """后台线程增量更新；已在刷新时返回 False。"""
    with _state_lock:
        if _state["updating"]:
            return False
        _state.update(updating=True, reason=reason, done=0, total=len(SERIES), current=None, last_error=None)

    def progress(done, total, code):
        _state.update(done=done, total=total, current=code)

    def job():
        try:
            rep = run_update(progress=progress)
            if rep["failed"]:
                _state["last_error"] = f"{len(rep['failed'])} 个指标更新失败：" + "；".join(rep["failed"][:3])
        except Exception:
            _state["last_error"] = traceback.format_exc()[-300:]
        finally:
            _state.update(updating=False, current=None)

    threading.Thread(target=job, daemon=True).start()
    return True


def _needs_auto_refresh():
    if db.point_count() == 0:
        return "首次运行，正在初始化数据"
    if os.environ.get("CYCLE_AUTO_REFRESH", "1") == "0":
        return None
    return "启动时自动更新"


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    reason = _needs_auto_refresh()
    if reason:
        start_refresh(reason)
    yield


app = FastAPI(title="周期行业观测台", lifespan=lifespan)


def _snapshot():
    if db.point_count() == 0:
        raise HTTPException(503, "数据初始化中，请稍候")
    return analyzer.snapshot()


def _sector_summary(s):
    return {k: v for k, v in s.items() if k != "members"}


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/api/status")
def status():
    empty = db.point_count() == 0
    h = None if empty else analyzer.snapshot()["health"]
    return dict(
        updating=_state["updating"], reason=_state["reason"], done=_state["done"], total=_state["total"],
        current=_state["current"], current_name=(find(_state["current"]) or {}).get("name"),
        last_error=_state["last_error"], last_refresh=db.get_meta("last_refresh"), empty=empty,
        fresh=h and h["fresh"], active_total=h and h["total"],
        stale=[dict(code=r["code"], name=r["name"], latest_date=r["latest_date"]) for r in h["stale"]] if h else [],
        data_as_of=None if empty else max((s["latest_date"] for s in analyzer.snapshot()["stats"].values()
                                           if not s["stale"]), default=None),
    )


@app.post("/api/refresh")
def refresh():
    started = start_refresh("手动刷新")
    return dict(started=started, reason=None if started else "已在刷新中")


@app.get("/api/overview")
def overview():
    snap = _snapshot()
    return dict(headline=snap["headline"], highlights=snap["highlights"], today=snap["today"],
                sectors={k: _sector_summary(s) for k, s in snap["sectors"].items()},
                stages=analyzer.STAGES)


@app.get("/api/sector/{key}")
def sector(key: str):
    snap = _snapshot()
    if key not in snap["sectors"]:
        raise HTTPException(404, "unknown sector")
    return dict(snap["sectors"][key], stages=analyzer.STAGES)


@app.get("/api/series/{code}")
def series(code: str):
    cfg = find(code)
    if cfg is None:
        raise HTTPException(404, f"unknown series {code}")
    snap = _snapshot()
    raw = snap["points"].get(code, [])
    pts, outliers = analyzer.clean(raw, cfg["role"])
    return dict(code=code, stats=snap["stats"].get(code), points=pts, outliers=outliers)


@app.get("/api/compare")
def compare(a: str, b: str):
    ca, cb = find(a), find(b)
    if ca is None or cb is None:
        raise HTTPException(404, "unknown series")
    snap = _snapshot()
    if a not in snap["points"] or b not in snap["points"]:
        raise HTTPException(404, "series has no data")
    res = analyzer.compare_pair(snap["points"][a], snap["points"][b], ca["role"], cb["role"])
    return dict(res, name_a=ca["name"], name_b=cb["name"], unit_a=ca["unit"], unit_b=cb["unit"])


@app.get("/api/meta")
def meta():
    pairs = [dict(sector=k, commodity=c["equity"]["vs"], equity=c["equity"]["code"])
             for k, c in SECTORS.items() if c.get("equity")]
    return dict(
        sectors={k: c["name"] for k, c in SECTORS.items()},
        series=[dict(code=s["code"], name=s["name"], sector=s["sector"], role=s["role"], archive=s["archive"])
                for s in SERIES],
        compare_pairs=pairs, stages=analyzer.STAGES,
    )


@app.get("/api/health")
def health():
    return _snapshot()["health"]


@app.get("/api/glossary")
def glossary_api():
    return glossary.GLOSSARY


@app.get("/api/reports")
def reports_list():
    if not REPORTS.exists():
        return []
    return sorted((p.name for p in REPORTS.glob("*.html")), reverse=True)


app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")
app.mount("/reports", StaticFiles(directory=str(REPORTS)), name="reports")

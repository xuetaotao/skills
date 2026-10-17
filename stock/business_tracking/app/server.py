# -*- coding: utf-8 -*-
"""FastAPI 服务：uvicorn app.server:app --port 8321

提供: 静态页面 / 数据 API / 主动刷新（后台线程）/ 更新状态。
"""
import threading
import traceback
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import analyzer, db, glossary
from .config import SECTORS, find
from .update import run_update

BASE = Path(__file__).resolve().parent.parent
WEB = BASE / "web"
REPORTS = BASE / "reports"

app = FastAPI(title="周期行业观测台")

_state = dict(updating=False, last_error=None)


@app.on_event("startup")
def _startup():
    db.init_db()


# ---------- 页面 ----------

@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


# ---------- 数据 API ----------

@app.get("/api/overview")
def overview():
    return analyzer.sector_overview()


@app.get("/api/series/{code}")
def series_points(code: str, start: str = None, end: str = None):
    if find(code) is None:
        raise HTTPException(404, f"unknown series {code}")
    rows = db.get_points(code, start, end)
    return dict(code=code, points=[list(r) for r in rows])


@app.get("/api/series/{code}/stats")
def series_stats(code: str):
    if find(code) is None:
        raise HTTPException(404, f"unknown series {code}")
    st = analyzer.series_stats(code)
    if st is None:
        raise HTTPException(404, f"series {code} has no data yet")
    cfg = find(code)
    st["name"], st["unit"] = cfg["name"], cfg["unit"]
    return st


@app.get("/api/status")
def status():
    dates = db.last_dates_all()
    last = max((v["last_date"] for v in dates.values() if v["last_date"]), default=None)
    return dict(
        updating=_state["updating"],
        last_error=_state["last_error"],
        last_refresh=db.get_meta("last_refresh"),
        data_as_of=last,
        series={k: v for k, v in dates.items()},
    )


@app.post("/api/refresh")
def refresh():
    """主动刷新：后台线程跑增量更新，前端轮询 /api/status。"""
    if _state["updating"]:
        return JSONResponse(dict(started=False, reason="已在刷新中"))
    _state["updating"] = True
    _state["last_error"] = None

    def _job():
        try:
            rep = run_update()
            if rep["failed"]:
                _state["last_error"] = "; ".join(rep["failed"][:3])
        except Exception:
            _state["last_error"] = traceback.format_exc()[-300:]
        finally:
            _state["updating"] = False

    threading.Thread(target=_job, daemon=True).start()
    return JSONResponse(dict(started=True))


@app.get("/api/glossary")
def glossary_api():
    return glossary.GLOSSARY


@app.get("/api/reports")
def reports_list():
    if not REPORTS.exists():
        return []
    return sorted(p.name for p in REPORTS.glob("*.html"))


@app.get("/api/board/{sector}")
def board(sector: str):
    if sector not in SECTORS:
        raise HTTPException(404, "unknown sector")
    return analyzer.sector_overview()[sector]


# ---------- 静态资源（放最后，避免吞掉 /api） ----------

app.mount("/static", StaticFiles(directory=str(WEB)), name="static")
app.mount("/reports", StaticFiles(directory=str(REPORTS)), name="reports")

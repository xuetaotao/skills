# -*- coding: utf-8 -*-
"""FastAPI 服务：uvicorn backend.server:app --port 8322

提供页面、数据 API 和后台刷新。每次启动都会在后台自动增量更新（数据库为空时全量下载）；
设置环境变量 ASSET_AUTO_REFRESH=0 可关闭（首次初始化除外）。
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
from .analytics import monthly_ser, ser
from .config import (ASSET_MAP, ASSETS, CORE, DEFAULT_TARGET, LOOKBACK, PRESETS, RF, SERIES, START,
                     WEIGHT_CAP, find_series)
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
        _state.update(updating=True, reason=reason, done=0, total=len(SERIES) + 1, current=None, last_error=None)

    def progress(done, total, code):
        _state.update(done=done, total=total, current=code)

    def job():
        try:
            rep = run_update(progress=progress)
            if rep["failed"]:
                _state["last_error"] = f"{len(rep['failed'])} 项更新失败：" + "；".join(rep["failed"][:3])
        except Exception:
            _state["last_error"] = traceback.format_exc()[-300:]
        finally:
            _state.update(updating=False, current=None)

    threading.Thread(target=job, daemon=True).start()
    return True


def _needs_auto_refresh():
    if db.point_count() == 0:
        return "首次运行，正在初始化数据"
    if os.environ.get("ASSET_AUTO_REFRESH", "1") == "0":
        return None
    return "启动时自动更新"


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    reason = _needs_auto_refresh()
    if reason:
        start_refresh(reason)
    yield


app = FastAPI(title="全球资产配置台", lifespan=lifespan)


def _snapshot():
    if db.point_count() == 0:
        raise HTTPException(503, "数据初始化中，请稍候")
    return analytics.snapshot()


def _current_name(code):
    if code == "SNAPSHOTS":
        return "A 股估值快照"
    return (find_series(code) or {}).get("name")


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/api/status")
def status():
    empty = db.point_count() == 0
    snap = None if empty else analytics.snapshot()
    h = snap and snap["health"]
    as_of = None
    if snap:
        core_dates = [a["recent"]["last_date"] for a in snap["assets"] if a["core"] and a["recent"] and not a["stale"]]
        as_of = min(core_dates) if core_dates else None
    return dict(
        updating=_state["updating"], reason=_state["reason"], done=_state["done"], total=_state["total"],
        current=_state["current"], current_name=_current_name(_state["current"]),
        last_error=_state["last_error"], last_refresh=db.get_meta("last_refresh"), empty=empty,
        fresh=h and h["fresh"], series_total=h and h["total"],
        stale=[dict(code=r["code"], name=r["name"], latest_date=r["latest_date"]) for r in h["stale"]] if h else [],
        data_as_of=as_of,
    )


@app.post("/api/refresh")
def refresh():
    started = start_refresh("手动刷新")
    return dict(started=started, reason=None if started else "已在刷新中")


def _asset_brief(a):
    return {k: a[k] for k in ("code", "name", "group", "region", "ccy", "core", "recent", "stale", "lag_days")}


@app.get("/api/overview")
def overview():
    snap = _snapshot()
    return dict(
        today=snap["today"], headline=snap["headline"], verdict=snap["valuation"]["verdict"],
        assets=[_asset_brief(a) for a in snap["assets"]], signals=snap["signals"],
        presets=[{k: p[k] for k in ("key", "name", "weights", "perf", "ytd")} for p in snap["presets"]],
        bond=snap["valuation"]["bond"] and {k: v for k, v in snap["valuation"]["bond"].items() if k != "history"},
    )


@app.get("/api/assets")
def assets():
    snap = _snapshot()
    m = snap["data"].monthly
    m = m[m.index >= START]
    curves = {c: monthly_ser(m[c].dropna() / m[c].dropna().iloc[0]) for c in m.columns if m[c].notna().any()}
    return dict(assets=snap["assets"], corr=snap["corr"], curves=curves, yearly=snap["yearly"], start=START[:7])


@app.get("/api/asset/{code}")
def asset(code: str):
    a = ASSET_MAP.get(code)
    if a is None:
        raise HTTPException(404, f"unknown asset {code}")
    snap = _snapshot()
    data = snap["data"]
    cny, loc = data.cny[code], data.local[code]
    cny, loc = cny[cny.index >= START], loc[loc.index >= START]
    info = next(x for x in snap["assets"] if x["code"] == code)
    fx = None
    if a["ccy"] != "CNY":
        f = data.fx.get(a["ccy"])
        if f is not None and not f.empty and len(cny):
            fx = ser(f[f.index >= cny.index[0]].resample("W").last(), 5)
    return dict(info, cny=ser(cny, 4), local=ser(loc, 4) if a["ccy"] != "CNY" else None, fx=fx,
                yearly=dict(years=snap["yearly"]["years"], values=snap["yearly"]["rows"].get(code, [])))


@app.get("/api/lab")
def lab():
    snap = _snapshot()
    R = snap["R"]
    return dict(
        codes=CORE, names={c: ASSET_MAP[c]["name"] for c in CORE}, groups={c: ASSET_MAP[c]["group"] for c in CORE},
        start=(R.index[0] - analytics.pd.offsets.MonthEnd(1)).strftime("%Y-%m"),
        dates=[d.strftime("%Y-%m") for d in R.index],
        returns={c: [analytics.num(x, 6) for x in R[c]] for c in CORE}, since=snap["since"],
        presets=[{k: p[k] for k in ("key", "name", "desc", "weights", "perf", "risk")} for p in snap["presets"]],
        dynamic=snap["dynamic"], wf_start=snap["wf_start"], default_target=DEFAULT_TARGET,
        rf=RF, cap=WEIGHT_CAP, lookback=LOOKBACK,
    )


@app.get("/api/valuation")
def valuation():
    return _snapshot()["valuation"]


@app.get("/api/meta")
def meta():
    return dict(
        assets=[{k: a[k] for k in ("code", "name", "group", "region", "ccy", "basis", "core")} for a in ASSETS],
        core=CORE, presets=[dict(key=p["key"], name=p["name"]) for p in PRESETS], default_target=DEFAULT_TARGET,
        start=START, rf=RF, cap=WEIGHT_CAP, lookback=LOOKBACK,
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
    return sorted((p.name for p in REPORTS.iterdir() if p.suffix in (".html", ".txt")), reverse=True)


app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")
app.mount("/reports", StaticFiles(directory=str(REPORTS)), name="reports")

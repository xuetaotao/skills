# -*- coding: utf-8 -*-
"""FastAPI 服务：uvicorn backend.server:app --port 8325

每次启动都会在后台更新行情并重写 outputs/latest_review*；设置环境变量 REVIEW_AUTO_REFRESH=0 可关闭（首次初始化除外）。
"""
import os
import re
import threading
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from . import analytics, db, glossary, report
from .config import GROUPS, INST, INSTRUMENTS, MA_PERIOD, WEEKS
from .update import run_update

BASE = Path(__file__).resolve().parent.parent
FRONTEND = BASE / "frontend"
OUTPUTS = Path(report.OUTPUTS)

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
                _state["last_error"] = f"{len(rep['failed'])} 项获取失败：" + "、".join(rep["failed"][:4])
        except Exception:
            _state["last_error"] = traceback.format_exc()[-300:]
        finally:
            _state.update(updating=False, current=None)

    threading.Thread(target=job, daemon=True).start()
    return True


def _needs_auto_refresh():
    if not db.ready():
        return "首次运行，正在初始化数据"
    if os.environ.get("REVIEW_AUTO_REFRESH", "1") == "0":
        return None
    return "启动时自动更新"


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    reason = _needs_auto_refresh()
    if reason:
        start_refresh(reason)
    yield


app = FastAPI(title="鱼盆复盘", lifespan=lifespan)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _asof(asof):
    if not asof:
        return None
    if not DATE_RE.match(asof):
        raise HTTPException(400, "日期格式应为 YYYY-MM-DD")
    return asof


def _need_data():
    if not db.ready():
        raise HTTPException(503, "数据初始化中，请稍候")


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/api/status")
def status():
    has = db.ready()
    return dict(
        updating=_state["updating"], reason=_state["reason"], done=_state["done"], total=_state["total"],
        current=_state["current"], last_error=_state["last_error"], empty=not has,
        last_refresh=db.get_meta("last_refresh"), failed=len(db.get_json("last_refresh_failed", [])),
        data_date=(analytics.rows() or {}).get("date") if has else None,
    )


@app.post("/api/refresh")
def refresh():
    started = start_refresh("手动刷新")
    return dict(started=started, reason=None if started else "已在刷新中")


@app.get("/api/meta")
def meta():
    has = db.ready()
    return dict(
        groups=GROUPS, ma=MA_PERIOD, weeks=WEEKS,
        instruments=[{k: INST[c][k] for k in ("code", "name", "region", "flag", "group", "kind")} for c, *_ in INSTRUMENTS],
        simple=analytics.simple_codes(),
        week_ends=[analytics._ds(t) for t in analytics.week_ends(60)] if has else [],
    )


@app.get("/api/overview")
def overview(asof: str = None):
    _need_data()
    asof = _asof(asof)
    data = analytics.rows(asof)
    if not data:
        raise HTTPException(404, "这个日期之前没有数据")
    return dict(**data, macro=analytics.macro(asof), simple=analytics.simple_codes(), asof=asof)


@app.get("/api/weeks")
def weeks(n: int = WEEKS, asof: str = None):
    _need_data()
    return analytics.weeks(max(2, min(n, 26)), _asof(asof))


@app.get("/api/instrument/{code}")
def instrument(code: str):
    _need_data()
    res = analytics.instrument(code)
    if res is None:
        raise HTTPException(404, f"标的清单里没有 {code}")
    return res


@app.get("/api/macro")
def macro_api():
    _need_data()
    return analytics.macro(None, history=True)


@app.get("/api/health")
def health():
    _need_data()
    return analytics.health()


@app.get("/api/glossary")
def glossary_api():
    return glossary.GLOSSARY


@app.put("/api/simple")
def set_simple(codes: list = Body(...)):
    codes = [c for c in codes if c in INST]
    if not codes:
        raise HTTPException(400, "精简版至少要保留一个标的")
    db.set_json("simple_codes", codes)
    if db.has_data():
        report.write_outputs(missing=db.get_json("last_refresh_failed", []))
    return dict(simple=analytics.simple_codes())


@app.delete("/api/simple")
def reset_simple():
    with db.conn() as c:
        c.execute("DELETE FROM meta WHERE key = 'simple_codes'")
    if db.has_data():
        report.write_outputs(missing=db.get_json("last_refresh_failed", []))
    return dict(simple=analytics.simple_codes())


@app.get("/api/material", response_class=PlainTextResponse)
def material(version: str = "simple", asof: str = None):
    _need_data()
    text = report.build("full" if version == "full" else "simple", "md", _asof(asof),
                        missing=None if asof else db.get_json("last_refresh_failed", []))
    if text is None:
        raise HTTPException(404, "这个日期之前没有数据")
    return text


@app.get("/report/{version}", response_class=HTMLResponse)
def report_html(version: str, asof: str = None):
    _need_data()
    if version not in ("simple", "full"):
        raise HTTPException(404, "版本只能是 simple 或 full")
    text = report.build(version, "html", _asof(asof))
    if text is None:
        raise HTTPException(404, "这个日期之前没有数据")
    return text


# ---------------- 周报存档（outputs 下 AI 写的 Markdown） ---------------- #

KINDS = [
    (re.compile(r"^weekly_review_(\d{8})(.*)\.md$"), "周报"),
    (re.compile(r"^news_candidates_(\d{8})(.*)\.md$"), "新闻候选"),
]
NOTES = {"revised": "修订版"}


def _review_meta(p):
    for pat, kind in KINDS:
        m = pat.match(p.name)
        if not m:
            continue
        g = m.group(1)
        date = f"{g[:4]}-{g[4:6]}-{g[6:]}"
        title = ""
        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("# "):
                    title = line[2:].replace("**", "").strip()
                    break
        note = m.group(2).strip("_")
        note = NOTES.get(note, note)
        return dict(name=p.name, kind=kind, date=date, title=title, note=note, size=p.stat().st_size,
                    mtime=int(p.stat().st_mtime))
    return None


@app.get("/api/reviews")
def reviews():
    if not OUTPUTS.exists():
        return []
    items = [x for x in (_review_meta(p) for p in OUTPUTS.iterdir() if p.is_file()) if x]
    return sorted(items, key=lambda x: (x["date"] or "", x["name"]), reverse=True)


@app.get("/api/reviews/{name}", response_class=PlainTextResponse)
def review_file(name: str):
    p = OUTPUTS / name
    if "/" in name or "\\" in name or not p.is_file() or _review_meta(p) is None:
        raise HTTPException(404, f"outputs 目录里没有 {name}")
    return p.read_text(encoding="utf-8", errors="replace")


app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")

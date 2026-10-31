"""FastAPI 服务：uvicorn backend.server:app --port 8332

抓取（需要扫码、要几分钟）和选题推荐（要联网抓热点）在后台线程跑，网页轮询状态；
分析只读本地文件，同步完成。
"""

import re
import threading
import traceback
from datetime import datetime

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from . import analysis, dataset, pipeline, prediction, recommend, report, scraper
from .baseline import load as load_baseline
from .config import ACCOUNT_NAME, DETAIL_MODES, FRONTEND_DIR, QR_PATH, REPORTS_DIR, WEEKDAYS
from .daterange import EXAMPLES
from .glossary import GLOSSARY

app = FastAPI(title="公众号数据分析")

scrape_job = scraper.Job()
_rec = dict(running=False, message="", error=None, result=None, started=None)
_rec_lock = threading.Lock()
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _need_data():
    if not dataset.load_details():
        raise HTTPException(503, "还没有分析数据：先抓取一次，或在已有原始快照时点「重新分析」")


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/api/meta")
def meta():
    return dict(account=ACCOUNT_NAME, weekdays=WEEKDAYS, detail_modes=DETAIL_MODES, range_examples=EXAMPLES)


@app.get("/api/glossary")
def glossary_api():
    return GLOSSARY


@app.get("/api/status")
def status():
    last = pipeline.last_analysis()
    b = load_baseline()
    reports = report.list_reports()
    job = scrape_job.snapshot()
    return dict(
        has_raw=bool(dataset.publish_pages()),
        has_data=bool(dataset.load_details()),
        window=dataset.load_window(),
        last_analysis=last["time"] if last else None,
        baseline=b["generated_at"] if b else None,
        latest_report=reports[0]["name"] if reports else None,
        scrape=scraper.status_summary(),
        job={k: job[k] for k in ("running", "phase", "message", "done", "total", "waiting_qr", "qr_version", "error")},
        recommending=_rec["running"],
    )


# ---------------- 分析 ----------------

@app.post("/api/analyze")
def analyze(body: dict = Body(default={})):
    if not dataset.publish_pages():
        raise HTTPException(400, "data/raw 里还没有发表记录，先抓取一次")
    mode = body.get("mode") or "all"
    args = {}
    if mode == "nl":
        if not (body.get("nl") or "").strip():
            raise HTTPException(400, "请填写时间范围，例如：近一个月")
        args["nl"] = body["nl"].strip()
    elif mode == "custom":
        since, until = body.get("since") or "", body.get("until") or ""
        if not DATE_RE.match(since) or (until and not DATE_RE.match(until)):
            raise HTTPException(400, "日期格式应为 YYYY-MM-DD")
        args.update(since=since, until=until or None)
    elif mode == "window":
        try:
            args["window"] = max(1, int(body.get("window")))
        except (TypeError, ValueError):
            raise HTTPException(400, "最近天数应为正整数") from None
    elif mode == "last":
        args = pipeline.current_range()
    else:
        args["all_"] = True
    try:
        return pipeline.analyze(use_env=False, **args)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@app.get("/api/overview")
def overview():
    _need_data()
    return analysis.overview()


@app.get("/api/articles")
def articles():
    _need_data()
    return analysis.article_rows()


@app.get("/api/articles/{aid}")
def article(aid: str):
    _need_data()
    d = analysis.article_detail(aid)
    if d is None:
        raise HTTPException(404, "分析窗口里没有这篇文章")
    return d


# ---------------- 报告 ----------------

@app.get("/api/reports")
def reports():
    return report.list_reports()


def _report_path(name):
    p = REPORTS_DIR / name
    if "/" in name or "\\" in name or not name.endswith(".html") or not p.is_file():
        raise HTTPException(404, f"reports 目录里没有 {name}")
    return p


@app.get("/reports/{name}", response_class=HTMLResponse)
def report_file(name: str):
    return _report_path(name).read_text(encoding="utf-8")


@app.delete("/api/reports/{name}")
def delete_report(name: str):
    _report_path(name).unlink()
    return report.list_reports()


# ---------------- 抓取 ----------------

@app.post("/api/scrape")
def start_scrape(body: dict = Body(default={})):
    if scrape_job.snapshot()["running"]:
        raise HTTPException(409, "已经在抓取中")
    details = body.get("details") or "missing_recent"
    if details not in DETAIL_MODES:
        raise HTTPException(400, "详情页范围不对")
    scraper.run_in_thread(scrape_job, details, bool(body.get("show_browser")), after=pipeline.rerun_last)
    return scrape_job.snapshot()


@app.get("/api/scrape")
def scrape_state():
    return scrape_job.snapshot()


@app.post("/api/scrape/cancel")
def cancel_scrape():
    scrape_job.cancel_requested = True
    return scrape_job.snapshot()


@app.get("/api/scrape/qr")
def scrape_qr():
    if not QR_PATH.exists():
        raise HTTPException(404, "现在不需要扫码")
    return FileResponse(QR_PATH, media_type="image/png", headers={"Cache-Control": "no-store"})


# ---------------- 标题评分 ----------------

@app.get("/api/baseline")
def baseline_api():
    b = load_baseline()
    if b is None:
        raise HTTPException(503, "还没有爆款预测基准：先运行一次分析")
    return b


@app.post("/api/predict")
def predict(body: dict = Body(...)):
    b = load_baseline()
    if b is None:
        raise HTTPException(503, "还没有爆款预测基准：先运行一次分析")
    title = (body.get("title") or "").strip()
    topics = prediction.split_topics(body.get("topics") or "")
    day = body.get("day") if body.get("day") in WEEKDAYS else "周二"
    if not title or not topics:
        raise HTTPException(400, "标题和主题关键词都要填")
    recent = dataset.load_recent() if body.get("saturation") else None
    res = prediction.score_topic_idea(title, topics, day, b, recent_articles=recent)
    card = prediction.render_prediction_card(res, b)
    res.pop("baseline", None)
    res["card"] = card
    return res


# ---------------- 选题推荐 ----------------

@app.post("/api/recommend")
def start_recommend(body: dict = Body(default={})):
    with _rec_lock:
        if _rec["running"]:
            raise HTTPException(409, "已经在推荐中")
        if load_baseline() is None:
            raise HTTPException(503, "还没有爆款预测基准：先运行一次分析")
        _rec.update(running=True, message="开始", error=None, result=None,
                    started=datetime.now().strftime("%H:%M:%S"))

    def count(v):
        try:
            return max(1, min(int(v), 12)) if v else None
        except (TypeError, ValueError):
            return None

    def job():
        try:
            r = recommend.run(ask=body.get("ask") or "", queries=body.get("queries") or None, count=count(body.get("count")),
                              day=body.get("day") if body.get("day") in WEEKDAYS else None,
                              offline=bool(body.get("offline")), save=True,
                              progress=lambda m: _rec.update(message=m))
            _rec.update(result=r["payload"], message="完成")
        except Exception as e:  # noqa: BLE001 - 错误显示在网页上
            _rec.update(error=f"{e}", message="失败")
            traceback.print_exc()
        finally:
            _rec.update(running=False)

    threading.Thread(target=job, daemon=True).start()
    return {k: v for k, v in _rec.items() if k != "result"}


@app.get("/api/recommend")
def recommend_state():
    return dict(_rec)


@app.get("/api/recommendations")
def recommendations():
    return recommend.list_history()


@app.get("/api/recommendations/{name}")
def recommendation(name: str):
    r = recommend.load_result(name)
    if r is None:
        raise HTTPException(404, f"没有 {name}")
    return r


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

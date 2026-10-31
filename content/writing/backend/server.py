"""FastAPI 服务：uvicorn backend.server:app --port 8331"""

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from . import articles, checks, prompts, titles
from .config import ARTICLES_DIR, FRONTEND_DIR, SOURCES, STAGES, STATUSES, WEEKDAYS, WORKFLOW_MD

app = FastAPI(title="写作工作台")


def _article(fn, *a):
    try:
        return fn(*a)
    except KeyError:
        raise HTTPException(404, "没有这篇文章") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/api/meta")
def meta():
    return dict(stages=STAGES, statuses=STATUSES, sources=SOURCES, weekdays=WEEKDAYS, feedback_keys=prompts.FEEDBACK_KEYS,
                articles_dir=str(ARTICLES_DIR), titles=titles.available())


@app.get("/api/prompts")
def prompt_list():
    return prompts.list_prompts()


@app.post("/api/prompt", response_class=PlainTextResponse)
def build_prompt(body: dict = Body(...)):
    try:
        return prompts.build(body.get("stage"), body.get("topic") or "", body.get("ideas") or "", body.get("article") or "",
                             body.get("feedback") or {}, body.get("notes") or "")
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(400, str(e)) from None


@app.get("/api/workflow", response_class=PlainTextResponse)
def workflow():
    return WORKFLOW_MD.read_text(encoding="utf-8")


@app.get("/api/articles")
def article_list():
    return articles.list_articles()


@app.post("/api/articles")
def article_create(body: dict = Body(...)):
    if not any((body.get(k) or "").strip() for k in ("title", "topic")):
        raise HTTPException(400, "标题和主题至少填一个")
    a = articles.create(body.get("title") or "", body.get("topic") or "", body.get("ideas") or "")
    if (body.get("text") or "").strip():
        a = articles.save_version(a["id"], body["text"], "新建时带入", body.get("source") or "我写的")
    return a


@app.get("/api/articles/{aid}")
def article_get(aid: str):
    return _article(articles.get, aid)


@app.put("/api/articles/{aid}")
def article_update(aid: str, body: dict = Body(...)):
    return _article(articles.update, aid, body)


@app.delete("/api/articles/{aid}")
def article_delete(aid: str):
    return {"moved_to": _article(articles.delete, aid)}


@app.post("/api/articles/{aid}/versions")
def version_save(aid: str, body: dict = Body(...)):
    text = body.get("text") or ""
    if not text.strip():
        raise HTTPException(400, "正文是空的")
    source = body.get("source") if body.get("source") in SOURCES else "我写的"
    return _article(articles.save_version, aid, text, body.get("note") or "", source)


@app.get("/api/articles/{aid}/versions/{n}", response_class=PlainTextResponse)
def version_get(aid: str, n: int):
    return _article(articles.get_version, aid, n)


@app.post("/api/check")
def run_check(body: dict = Body(...)):
    return checks.check(body.get("text") or "", body.get("title") or "")


@app.post("/api/titles")
def score_titles(body: dict = Body(...)):
    ts = [t for t in (body.get("titles") or []) if str(t).strip()]
    if not ts or not (body.get("topics") or "").strip():
        raise HTTPException(400, "标题和主题关键词都要填")
    day = body.get("day") if body.get("day") in WEEKDAYS else "周二"
    try:
        return titles.score(ts, body["topics"], day, bool(body.get("saturation", True)))
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from None


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

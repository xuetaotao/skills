"""文章清单：发表记录 → 分析窗口 → 合并单篇详情。

  data/raw/publish_p*.txt          发表记录（每页 20 条，extract_pub.js 的输出）
  data/raw/d2_<appmsg_id>.txt      单篇详情页快照
  → data/processed/recent_articles.json   窗口内文章（title/date/reads/appmsg_id）
  → data/processed/article_details.json   同窗口底表（id/title/publish）
  → data/processed/_window.json           窗口范围
  → data/processed/article_details2.json  底表 + 详情字段

阅读量口径（MEMORY 铁律 #4）：reads 一律取发表记录列表页的值（= 后台实时看到的数），
详情页快照里的阅读量放在 reads_d2 供回溯；完读、分享、关注等只有详情页有。
"""

import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import snapshot
from .config import PROCESSED_DIR, RAW_DIR
from .daterange import resolve as resolve_nl

BEIJING = timezone(timedelta(hours=8))


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def load_publish_page(path: Path) -> list:
    """兼容三种形态：普通 JSON 数组；整体是 JSON 字符串；数组里包着一个 JSON 字符串（agent-browser 重定向产物）。"""
    try:
        d = json.loads(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return []
    try:
        if isinstance(d, list) and d and isinstance(d[0], str):
            d = json.loads(d[0])
        elif isinstance(d, str):
            d = json.loads(d)
    except ValueError:
        return []
    return d if isinstance(d, list) else []


def publish_pages() -> list:
    def page_no(p):
        m = re.search(r"publish_p(\d+)\.txt$", p.name)
        return int(m.group(1)) if m else 0
    return sorted(RAW_DIR.glob("publish_p*.txt"), key=page_no)


def all_articles() -> list:
    """发表记录里全部有发文时间的文章，按日期升序。没有 send_time 的（已删除）跳过；
    没有 appmsg_id 的（转载、旧文）仍计入汇总分析，只是没有详情快照。"""
    seen = {}
    for p in publish_pages():
        for c in load_publish_page(p):
            if not c.get("send_time"):
                continue
            aid = c.get("appmsg_id") or f"noid|{c.get('title', '')}|{c.get('send_time')}"
            title = (c.get("title") or "").replace("\u200b", "").replace("\xa0", " ").strip()
            pub = datetime.fromtimestamp(int(c["send_time"]), BEIJING).date()
            reads = None
            if c.get("stats"):
                try:
                    reads = int(str(c["stats"][0]).replace(",", ""))
                except ValueError:
                    reads = None
            seen[aid] = {"id": aid, "title": title, "publish": pub.isoformat(), "reads": reads,
                         "has_id": bool(c.get("appmsg_id"))}
    return sorted(seen.values(), key=lambda x: x["publish"])


def resolve_window(articles, nl=None, since=None, until=None, window=None, all_=False, today=None, use_env=True):
    """返回 (since, until, mode, warning)。优先级：口语短语 > 全部 > since/until > 最近 N 天 > 默认全部。"""
    today = today or date.today()
    earliest = date.fromisoformat(articles[0]["publish"]) if articles else today
    env = os.environ if use_env else {}
    if nl:
        r = resolve_nl(nl, today)
        if r is None:
            return earliest, today, "all", f"无法识别「{nl}」，已按全部已抓取文章分析"
        if r == ("ALL",):
            return earliest, today, "all", None
        return r[0], r[1], f"nl:{nl}", None
    if all_ or env.get("WXPUB_RANGE") == "all":
        return earliest, today, "all", None
    if since or env.get("WXPUB_SINCE"):
        s = date.fromisoformat(since or env.get("WXPUB_SINCE"))
        u = date.fromisoformat(until or env.get("WXPUB_UNTIL") or today.isoformat())
        return s, u, "custom", None
    if window is not None or env.get("WXPUB_WINDOW"):
        n = int(window if window is not None else env.get("WXPUB_WINDOW"))
        return today - timedelta(days=n), today, f"last{n}d", None
    return earliest, today, "all", None


def build_window(**range_args) -> dict:
    """生成 recent_articles.json / article_details.json / _window.json。范围里一篇都没有时不写任何文件。"""
    arts = all_articles()
    since, until, mode, warning = resolve_window(arts, **range_args)
    window = [a for a in arts if since <= date.fromisoformat(a["publish"]) <= until]
    if not window:
        latest = arts[-1]["publish"] if arts else None
        raise ValueError(f"{since} ~ {until} 之间没有已抓取的文章"
                         + (f"（已抓取的最新一篇发于 {latest}），换个范围，或先抓取最新数据" if latest else "，先抓取一次数据"))
    recent = [{"title": a["title"], "date": a["publish"], "reads": a["reads"], "appmsg_id": a["id"]} for a in window]
    base = [{"id": a["id"], "title": a["title"], "publish": a["publish"]} for a in window]
    _write_json(PROCESSED_DIR / "recent_articles.json", recent)
    _write_json(PROCESSED_DIR / "article_details.json", base)
    _write_json(PROCESSED_DIR / "_window.json", {"since": since.isoformat(), "until": until.isoformat(), "mode": mode})
    return {"since": since.isoformat(), "until": until.isoformat(), "mode": mode, "warning": warning,
            "articles": len(window), "scraped_total": len(arts)}


def detail_files() -> dict:
    out = {}
    for p in RAW_DIR.glob("d2_*.txt"):
        m = re.match(r"d2_(\d+)\.txt$", p.name)
        if m:
            out[m.group(1)] = p
    return out


def parse_details() -> dict:
    """把 d2_*.txt 详情合并进窗口底表，写 article_details2.json。派生率由使用方用统一后的 reads 现算。"""
    base = _read_json(PROCESSED_DIR / "article_details.json", [])
    by_id = {a["id"]: a for a in base}
    by_title = {}
    for a in _read_json(PROCESSED_DIR / "recent_articles.json", []):
        if a.get("reads") is None:
            continue
        if a.get("appmsg_id") in by_id:
            by_id[a["appmsg_id"]]["reads"] = a["reads"]
        by_title[(a.get("title") or "").strip()] = a["reads"]
    injected = 0
    for a in by_id.values():
        if a.get("reads") is None:
            a["reads"] = by_title.get((a.get("title") or "").strip())
        if a.get("reads") is not None:
            injected += 1
        else:
            a.pop("reads", None)

    fresh, outside, empty = 0, [], []
    for aid, path in detail_files().items():
        if aid not in by_id:
            outside.append(aid)
            continue
        parsed = snapshot.parse_detail(path.read_text(encoding="utf-8"))
        if not parsed:
            empty.append(aid)
            continue
        by_id[aid].update(parsed)
        by_id[aid]["_fresh"] = True
        fresh += 1

    merged = list(by_id.values())
    _write_json(PROCESSED_DIR / "article_details2.json", merged)
    mismatch = [{"id": a["id"], "title": a["title"], "reads": a.get("reads"), "reads_d2": a.get("reads_d2")}
                for a in merged if a.get("_fresh") and a.get("reads") != a.get("reads_d2")]
    return {"merged": len(merged), "with_detail": fresh, "reads_injected": injected,
            "outside_window": len(outside), "empty_parse": empty, "reads_mismatch": mismatch}


# ---------------- 读取（分析、报告、接口共用） ----------------

def load_window() -> dict:
    return _read_json(PROCESSED_DIR / "_window.json", {}) or {}


def load_recent() -> list:
    return _read_json(PROCESSED_DIR / "recent_articles.json", []) or []


def load_details() -> list:
    return _read_json(PROCESSED_DIR / "article_details2.json", []) or []


def load_user_analysis() -> dict:
    path = RAW_DIR / "user_analysis.txt"
    if not path.exists():
        return {"fans": None, "growth_month_pct": None, "channels": {}, "channels_total": None,
                "is_single_slice": False, "date": None}
    out = snapshot.parse_user_analysis(path.read_text(encoding="utf-8"))
    out["date"] = date.fromtimestamp(path.stat().st_mtime).isoformat()
    return out


def load_content_analysis() -> dict:
    path = RAW_DIR / "content_analysis.txt"
    if not path.exists():
        return {"traffic": {}, "total_readers": None, "date": None}
    out = snapshot.parse_content_analysis(path.read_text(encoding="utf-8"))
    out["date"] = date.fromtimestamp(path.stat().st_mtime).isoformat()
    return out

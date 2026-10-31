"""文章库：articles/<YYYY-MM-DD>_<标题>/

  meta.json        标题、主题、想法、状态、发表信息、版本列表
  versions/v001.md 每次「保存为新版本」一份，按顺序编号，从不覆盖
  final.md         状态改成「定稿」「已发表」时，当前版本另存一份

删除只是移到 articles/_trash/，需要时可以手动找回。
"""

import json
import re
import shutil
from datetime import date, datetime

from .config import ARTICLES_DIR, FINAL_STATUSES, STATUSES, TRASH_DIR

META_FIELDS = ("title", "topic", "ideas", "status", "notes", "publish_date", "url", "topics", "day")


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def count_chars(text: str) -> int:
    """中文按字、英文按词计数，接近公众号后台的字数。"""
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text or ""))
    words = len(re.findall(r"[A-Za-z0-9]+(?:[.'-][A-Za-z0-9]+)*", text or ""))
    return cjk + words


def _slug(title):
    s = re.sub(r'[\\/:*?"<>|\s]+', "_", title.strip())[:40].strip("._")
    return s or "未命名"


def _dir(aid):
    if not re.match(r"^[^\\/]+$", aid or "") or aid.startswith(("_", ".")):
        raise KeyError(aid)
    d = ARTICLES_DIR / aid
    if not (d / "meta.json").exists():
        raise KeyError(aid)
    return d


def _read_meta(d):
    return json.loads((d / "meta.json").read_text(encoding="utf-8"))


def _write_meta(d, meta):
    meta["updated"] = _now()
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


def list_articles():
    if not ARTICLES_DIR.exists():
        return []
    out = []
    for d in ARTICLES_DIR.iterdir():
        if not d.is_dir() or d.name.startswith(("_", ".")) or not (d / "meta.json").exists():
            continue
        try:
            m = _read_meta(d)
        except (OSError, ValueError):
            continue
        last = (m.get("versions") or [{}])[-1]
        out.append({"id": d.name, "title": m.get("title", d.name), "status": m.get("status"), "topic": m.get("topic", ""),
                    "created": m.get("created"), "updated": m.get("updated"), "versions": len(m.get("versions") or []),
                    "chars": last.get("chars", 0), "publish_date": m.get("publish_date")})
    return sorted(out, key=lambda x: x["updated"] or "", reverse=True)


def create(title, topic="", ideas="") -> dict:
    title = (title or "").strip() or (topic or "").strip()[:30] or "未命名"
    base = f"{date.today().isoformat()}_{_slug(title)}"
    aid, n = base, 2
    while (ARTICLES_DIR / aid).exists():
        aid, n = f"{base}_{n}", n + 1
    d = ARTICLES_DIR / aid
    (d / "versions").mkdir(parents=True)
    meta = {"title": title, "topic": topic.strip(), "ideas": ideas.strip(), "status": "构思", "notes": "",
            "publish_date": "", "url": "", "topics": "", "day": "周二", "created": _now(), "versions": []}
    _write_meta(d, meta)
    return get(aid)


def get(aid) -> dict:
    d = _dir(aid)
    m = _read_meta(d)
    versions = m.get("versions") or []
    current = (d / "versions" / versions[-1]["file"]).read_text(encoding="utf-8") if versions else ""
    return dict(m, id=aid, current=current, has_final=(d / "final.md").exists(), path=str(d))


def update(aid, fields: dict) -> dict:
    d = _dir(aid)
    m = _read_meta(d)
    for k in META_FIELDS:
        if k in fields and fields[k] is not None:
            m[k] = str(fields[k]).strip() if k != "ideas" else str(fields[k])
    if m.get("status") not in STATUSES:
        m["status"] = "构思"
    _write_meta(d, m)
    if m["status"] in FINAL_STATUSES and m.get("versions"):
        shutil.copyfile(d / "versions" / m["versions"][-1]["file"], d / "final.md")
    return get(aid)


def save_version(aid, text, note="", source="我写的") -> dict:
    d = _dir(aid)
    m = _read_meta(d)
    versions = m.setdefault("versions", [])
    if versions:
        last = (d / "versions" / versions[-1]["file"]).read_text(encoding="utf-8")
        if last == text:
            raise ValueError("和当前版本完全一样，不用另存")
    n = (versions[-1]["n"] + 1) if versions else 1
    name = f"v{n:03d}.md"
    (d / "versions" / name).write_text(text, encoding="utf-8")
    versions.append({"n": n, "file": name, "time": _now(), "note": note.strip(), "source": source, "chars": count_chars(text)})
    if m.get("status") == "构思":
        m["status"] = "初稿"
    _write_meta(d, m)
    if m["status"] in FINAL_STATUSES:
        shutil.copyfile(d / "versions" / name, d / "final.md")
    return get(aid)


def get_version(aid, n: int) -> str:
    d = _dir(aid)
    v = next((x for x in _read_meta(d).get("versions", []) if x["n"] == n), None)
    if v is None:
        raise KeyError(n)
    return (d / "versions" / v["file"]).read_text(encoding="utf-8")


def delete(aid):
    d = _dir(aid)
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    dest = TRASH_DIR / f"{aid}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    shutil.move(str(d), str(dest))
    return str(dest)

# -*- coding: utf-8 -*-
"""Build the two inventory JSON files the analysis needs, from the publish-list
raw extractions (data/raw/publish_pN.txt produced by the extract_pub.js eval):

  - data/processed/recent_articles.json : ALL articles since account start
    (title / date / reads / appmsg_id)  -> weekday + aggregate analysis (32篇)
  - data/processed/article_details.json : 30-day-window base (id/title/publish)
    -> merged with d2_*.txt detail snapshots by parse_details2.py (17篇)

Usage: python build_articles.py [WORKSPACE_DIR]
  WORKSPACE_DIR defaults to cwd or env WXPUB_DIR.
"""
import json, os, glob, sys
from datetime import date, datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE
for _ in range(6):
    if os.path.exists(os.path.join(ROOT, "data")) or os.path.exists(os.path.join(ROOT, "reports")) or os.path.exists(os.path.join(ROOT, ".workbuddy")):
        break
    ROOT = os.path.dirname(ROOT)
BASE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("WXPUB_DIR", ROOT)
RAW = os.path.join(BASE, "data", "raw")
PROC = os.path.join(BASE, "data", "processed")

def load(p):
    raw = open(p, encoding="utf-8").read().strip()
    return json.loads(json.loads(raw)) if raw.startswith('"') else json.loads(raw)

def date_of(ts):
    return datetime.fromtimestamp(int(ts), timezone.utc).date()

# account start (5.27 起规律更新); 30天窗口相对"今天"
START = date(2026, 5, 27)
TODAY = date.today()
WINDOW = 30

cards = []
for p in sorted(glob.glob(os.path.join(RAW, "publish_p*.txt"))):
    cards += load(p)

seen = {}
for c in cards:
    if not c.get("appmsg_id") or not c.get("send_time"):
        continue
    aid = c["appmsg_id"]
    title = c["title"].replace("\u200b", "").replace("\xa0", " ").strip()
    pub = date_of(c["send_time"])
    seen[aid] = {
        "id": aid,
        "title": title,
        "publish": pub.isoformat(),
        "reads": int(c["stats"][0].replace(",", "")) if c.get("stats") else None,
    }

all_articles = sorted(seen.values(), key=lambda x: x["publish"])
since_start = [a for a in all_articles if date.fromisoformat(a["publish"]) >= START]
window = [a for a in since_start if (TODAY - date.fromisoformat(a["publish"])).days <= WINDOW]

recent = [{"title": a["title"], "date": a["publish"], "reads": a["reads"], "appmsg_id": a["id"]} for a in since_start]
details_base = [{"id": a["id"], "title": a["title"], "publish": a["publish"]} for a in window]

os.makedirs(PROC, exist_ok=True)
json.dump(recent, open(os.path.join(PROC, "recent_articles.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(details_base, open(os.path.join(PROC, "article_details.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("since_start:", len(since_start), "| 30d window:", len(window))
print("recent_articles.json ->", os.path.join(PROC, "recent_articles.json"))
print("article_details.json ->", os.path.join(PROC, "article_details.json"))

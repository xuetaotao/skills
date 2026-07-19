# -*- coding: utf-8 -*-
"""Build the two inventory JSON files the analysis needs, from the publish-list
raw extractions (data/raw/publish_pN.txt produced by the extract_pub.js eval):

  - data/processed/recent_articles.json : articles in the analysis window
    (title / date / reads / appmsg_id)  -> weekday + aggregate analysis
  - data/processed/article_details.json : SAME window base (id/title/publish)
    -> merged with d2_*.txt detail snapshots by parse_details2.py

===== 分析时间范围（同时作用于两个文件，单一窗口）=====
  默认：全部【已抓取】的发表记录（= data/raw/publish_p*.txt 里的所有卡片）。
        由 scripts/scrape_publish.sh 自动翻页抓到尾页（目前实测 82 篇 / 5 页，
        覆盖 2020-06-14 ~ 今天，2020-06-14 为最早一篇）。不指定任何参数即走这个范围。
        ⚠️ 详情解析（parse_details2）只覆盖 data/raw 下存在 d2_<APPMSGID>.txt 快照的
        文章（当前 17 篇）；要扩到全部文章的逐篇详情，需用浏览器把更早文章的详情页也抓一遍。
  --all / WXPUB_RANGE="all"            -> 同默认：data/raw/publish_p*.txt 里的全部卡片
  --nl "短语"                          -> 中文日期短语，例如：
        "近一个月"  "最近7天"  "2026年至今"  "今年"
        "2026年5月"  "本月"  "上周"  "2026-05-27 到 2026-07-01"
        （解析规则见 resolve_range.py；无法识别时回退到"已抓取全部"并打印 WARN）
  --since YYYY-MM-DD / WXPUB_SINCE     -> 下界（含）；可配合 --until 指定任意时段
  --until YYYY-MM-DD / WXPUB_UNTIL     -> 上界（含，默认今天）
  --window N / WXPUB_WINDOW=N          -> 最近 N 天（仅在显式给定时才生效，否则走全量）
  第一个位置参数 = WORKSPACE_DIR（也可设 WXPUB_DIR）。

注意：详情解析（parse_details2）只覆盖 data/raw 下存在 d2_<APPMSGID>.txt 快照的
文章。要分析超出已抓取范围的时段，需先用浏览器重新抓取该时段的详情页。
"""
import json, os, glob, sys, argparse, re
from datetime import date, datetime, timezone, timedelta
from resolve_range import resolve as resolve_nl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE
for _ in range(6):
    if os.path.exists(os.path.join(ROOT, "data")) or os.path.exists(os.path.join(ROOT, "reports")) or os.path.exists(os.path.join(ROOT, ".workbuddy")):
        break
    ROOT = os.path.dirname(ROOT)
BASE_DEFAULT = os.environ.get("WXPUB_DIR", ROOT)

ap = argparse.ArgumentParser()
ap.add_argument("workspace", nargs="?", default=BASE_DEFAULT)
ap.add_argument("--all", action="store_true", help="analyze entire scraped history")
ap.add_argument("--nl", help="natural-language date phrase, e.g. '近一个月' / '2026年至今'")
ap.add_argument("--since", help="lower bound YYYY-MM-DD (inclusive)")
ap.add_argument("--until", help="upper bound YYYY-MM-DD (inclusive), default today")
ap.add_argument("--window", type=int, default=None,
                help="days back (only if explicitly given; else default = ALL)")
args = ap.parse_args()
BASE = args.workspace
RAW = os.path.join(BASE, "data", "raw")
PROC = os.path.join(BASE, "data", "processed")

def load(p):
    raw = open(p, encoding="utf-8").read().strip()
    # 兼容三种形态：
    #  1) 外层是 JSON 字符串（以 " 开头） -> json.loads 两次
    #  2) 外层是数组、其首元素是 JSON 字符串（以 [ 开头，agent-browser 文件重定向产物）
    #  3) 已是普通 JSON 数组
    try:
        d = json.loads(raw)
    except Exception:
        return []
    if isinstance(d, list) and d and isinstance(d[0], str):
        try:
            d = json.loads(d[0])
        except Exception:
            return []
    elif isinstance(d, str):
        try:
            d = json.loads(d)
        except Exception:
            return []
    return d if isinstance(d, list) else []

def date_of(ts):
    return datetime.fromtimestamp(int(ts), timezone(timedelta(hours=8))).date()  # 微信时间戳为北京时间

cards = []
for p in sorted(glob.glob(os.path.join(RAW, "publish_p*.txt"))):
    cards += load(p)

seen = {}
for c in cards:
    # 只跳过没有 send_time 的（无法定位到时间）；appmsg_id 为空（转载/旧文）仍可计入
    # 聚合分析，只是没有逐篇详情快照而已。
    if not c.get("send_time"):
        continue
    raw_aid = c.get("appmsg_id")
    aid = raw_aid if raw_aid else f"noid|{c.get('title','')}|{c.get('send_time')}"
    title = (c.get("title") or "").replace("\u200b", "").replace("\xa0", " ").strip()
    pub = date_of(c["send_time"])
    seen[aid] = {
        "id": aid,
        "title": title,
        "publish": pub.isoformat(),
        "reads": None,
    }
    if c.get("stats") and len(c["stats"]) >= 1:
        seen[aid]["reads"] = int(c["stats"][0].replace(",", ""))

all_articles = sorted(seen.values(), key=lambda x: x["publish"])
TODAY = date.today()
EARLIEST = date.fromisoformat(min(a["publish"] for a in all_articles)) if all_articles else TODAY

# ---- 确定 [SINCE, UNTIL] 单一窗口 ----
# 优先级：--nl（口语）> --all/环境变量 > --since/--until > --window > 默认=全部
SINCE, UNTIL, mode = EARLIEST, TODAY, "all"   # 默认就是全量
explicit = False

if args.nl:
    r = resolve_nl(args.nl, TODAY)
    if r == ("ALL",):
        SINCE, UNTIL, mode = EARLIEST, TODAY, "all"
    elif r is None:
        print(f"WARN: 无法解析短语 {args.nl!r}，回退为全部历史")
        SINCE, UNTIL, mode = EARLIEST, TODAY, "all"
    else:
        SINCE, UNTIL, mode = r[0], r[1], f"nl:{args.nl}"
    explicit = True

if not explicit and (args.all or os.environ.get("WXPUB_RANGE") == "all"):
    SINCE, UNTIL, mode = EARLIEST, TODAY, "all"
    explicit = True

if not explicit and (args.since or os.environ.get("WXPUB_SINCE")):
    SINCE = date.fromisoformat(args.since or os.environ.get("WXPUB_SINCE"))
    UNTIL = date.fromisoformat(args.until or os.environ.get("WXPUB_UNTIL") or TODAY.isoformat())
    mode = "custom"
    explicit = True

if not explicit and (args.window is not None or os.environ.get("WXPUB_WINDOW")):
    n = args.window if args.window is not None else int(os.environ.get("WXPUB_WINDOW"))
    SINCE, UNTIL, mode = TODAY - timedelta(days=n), TODAY, f"last{n}d"
    explicit = True

window = [a for a in all_articles if SINCE <= date.fromisoformat(a["publish"]) <= UNTIL]
recent = [{"title": a["title"], "date": a["publish"], "reads": a["reads"], "appmsg_id": a["id"]} for a in window]
details_base = [{"id": a["id"], "title": a["title"], "publish": a["publish"]} for a in window]

os.makedirs(PROC, exist_ok=True)
json.dump(recent, open(os.path.join(PROC, "recent_articles.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(details_base, open(os.path.join(PROC, "article_details.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
# 记录分析窗口，供下游（generate_final2）判断"是否近30天、百分比口径是否可比"
json.dump({"since": SINCE.isoformat(), "until": UNTIL.isoformat(), "mode": mode},
          open(os.path.join(PROC, "_window.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"mode={mode} SINCE={SINCE} UNTIL={UNTIL}")
print("articles in window:", len(window))
print("recent_articles.json ->", os.path.join(PROC, "recent_articles.json"))
print("article_details.json ->", os.path.join(PROC, "article_details.json"))

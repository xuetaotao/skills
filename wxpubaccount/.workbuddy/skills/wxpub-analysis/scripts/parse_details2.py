# -*- coding: utf-8 -*-
"""Parse fresh d2_*.txt WeChat article-detail snapshots into JSON,
merging with article_details.json (keeps id/title/publish).

Usage: python parse_details2.py [WORKSPACE_DIR]
  WORKSPACE_DIR defaults to cwd or env WXPUB_DIR.
"""
import re, json, os, glob, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE
for _ in range(6):
    if os.path.exists(os.path.join(ROOT, "data")) or os.path.exists(os.path.join(ROOT, "reports")) or os.path.exists(os.path.join(ROOT, ".workbuddy")):
        break
    ROOT = os.path.dirname(ROOT)
BASE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("WXPUB_DIR", ROOT)
DATA = os.path.join(BASE, "data", "processed")
RAW  = os.path.join(BASE, "data", "raw")

def first(t, pat):
    m = re.search(pat, t)
    return m.group(1) if m else None

def parse_file(path):
    t = open(path, encoding="utf-8").read()
    out = {}
    # reads: 阅读 -> generic -> "556 人"
    m = re.search(r'StaticText "阅读"\s*\n\s*- generic\s*\n\s*- StaticText "(\d+) 人"', t)
    if m: out["reads"] = int(m.group(1))
    # 完读率 -> "48%"
    m = re.search(r'完读率"\s*\n\s*- StaticText "(\d+(?:\.\d+)?)%"', t)
    if m: out["completion"] = float(m.group(1))
    # 新增关注 -> "4 人" (optional generic in between)
    m = re.search(r'新增关注"\s*(?:\n\s*- generic\s*\n)?\s*- StaticText "(\d+) 人"', t)
    if m: out["new_follows"] = int(m.group(1))
    # 分享 / 留言 / 收藏 (互动 block, plain numbers)
    m = re.search(r'分享"\s*\n\s*- StaticText "(\d+)"', t)
    if m: out["shares"] = int(m.group(1))
    m = re.search(r'留言"\s*\n\s*- StaticText "(\d+)"', t)
    if m: out["comments"] = int(m.group(1))
    m = re.search(r'收藏"\s*\n\s*- StaticText "(\d+)"', t)
    if m: out["collections"] = int(m.group(1))
    # 听全文 (context metric)
    m = re.search(r'听全文"\s*\n\s*- StaticText "(\d+) 人"', t)
    if m: out["listen_full"] = int(m.group(1))
    # 渠道 (chart images): image "推荐, 91.007."
    ch = {}
    for name, val in re.findall(r'image "([^,]+?),\s*([\d.]+)\.', t):
        ch[name.strip()] = float(val)
    if ch: out["channels"] = ch
    # 性别: StaticText "女 6.83%女 6.83%"
    g = {}
    for k, v in re.findall(r'(男|女|未知)\s+(\d+(?:\.\d+)?)%', t):
        g[k] = float(v)
    if g: out["gender"] = g
    # 年龄: image "60岁以上, 5.24."
    age = {}
    for name in ['18岁以下','18-25岁','26-35岁','36-45岁','46-60岁','60岁以上','未知']:
        m = re.search(r'image "'+re.escape(name)+r',\s*([\d.]+)\.', t)
        if m: age[name] = float(m.group(1))
    if age: out["age"] = age
    # 地域: table cell "广东省" / "21.22%"
    reg = re.findall(r'cell "([^"]+)"\s*\n\s*- cell "([\d.]+)%"', t)
    if reg: out["region"] = [[n, p+"%"] for n, p in reg]
    return out

base = json.load(open(f"{DATA}/article_details.json", encoding="utf-8"))
by_id = {a["id"]: a for a in base}

for fp in glob.glob(f"{RAW}/d2_*.txt"):
    fid = re.search(r"d2_(\d+)\.txt", fp).group(1)
    if fid not in by_id:
        print("WARN unmatched id", fid); continue
    fresh = parse_file(fp)
    if not fresh:
        print("WARN empty parse", fid); continue
    by_id[fid].update(fresh)
    by_id[fid]["_fresh"] = True

merged = list(by_id.values())
# derived rates
for a in merged:
    r = a.get("reads") or 0
    if r:
        a["share_rate"] = round((a.get("shares") or 0)/r*100, 2)
        a["coll_rate"] = round((a.get("collections") or 0)/r*100, 2)
        a["follow_rate"] = round((a.get("new_follows") or 0)/r*100, 2)

json.dump(merged, open(f"{DATA}/article_details2.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("merged", len(merged), "fresh-updated:", sum(1 for a in merged if a.get("_fresh")))

# delta vs morning for key metrics
print("\n--- deltas vs morning (reads / new_follows) ---")
for a in merged:
    if a.get("_fresh"):
        print(f'{a["id"]} {a["title"][:14]:<16} reads={a.get("reads")} comp={a.get("completion")} follow={a.get("new_follows")} share={a.get("shares")} coll={a.get("collections")} comm={a.get("comments")}')

# -*- coding: utf-8 -*-
"""Parse fresh d2_*.txt WeChat article-detail snapshots into JSON,
merging with article_details.json (keeps id/title/publish).

关键口径（见 MEMORY.md 铁律 #4）：
  - reads 字段 = 【发布列表页】阅读量（=用户在微信后台实时看到的当前值），
    从 recent_articles.json 按 id 注入到所有文章。
  - reads_d2 字段 = 详情页 d2 抓取时刻的快照（保留供回溯，可能比 reads 高几个）。
  - 关注/完读/分享/收藏/留言 仍取自详情页 d2（列表页无这些字段）。
  - 派生率（share_rate/coll_rate/follow_rate）不在本脚本预算，留给
    generate_final2.py 现场用统一后的 reads 计算，避免口径不一致。

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
    # reads: 阅读 -> generic -> "1,925 人" (大数带千分位逗号)
    m = re.search(r'StaticText "阅读"\s*\n\s*- generic\s*\n\s*- StaticText "([\d,]+) 人"', t)
    if m: out["reads_d2"] = int(m.group(1).replace(",", ""))
    # 完读率 -> "48%"
    m = re.search(r'完读率"\s*\n\s*- StaticText "(\d+(?:\.\d+)?)%"', t)
    if m: out["completion"] = float(m.group(1))
    # 新增关注 -> "4 人" (optional generic in between)
    m = re.search(r'新增关注"\s*(?:\n\s*- generic\s*\n)?\s*- StaticText "([\d,]+) 人"', t)
    if m: out["new_follows"] = int(m.group(1).replace(",", ""))
    # 分享 / 留言 / 收藏 (互动 block, plain numbers, 大数可能带逗号)
    # 分享区块有 3 个数字：分享总数 / 朋友圈分享 / 转发（按微信后台 UI 顺序）
    # 抓"分享"到"赞赏"之间的所有 StaticText 数字
    share_block = re.search(r'分享"\s*(.*?)\n\s*- StaticText "赞赏"', t, re.S)
    if share_block:
        share_nums = re.findall(r'StaticText "([\d,]+)"', share_block.group(1))
        if share_nums:
            out["shares"] = int(share_nums[0].replace(",", ""))            # 分享总数
        if len(share_nums) >= 2:
            out["moments"] = int(share_nums[1].replace(",", ""))           # 朋友圈分享
        if len(share_nums) >= 3:
            out["forwards"] = int(share_nums[2].replace(",", ""))          # 转发（好友/群）
    m = re.search(r'留言"\s*\n\s*- StaticText "([\d,]+)"', t)
    if m: out["comments"] = int(m.group(1).replace(",", ""))
    m = re.search(r'收藏"\s*\n\s*- StaticText "([\d,]+)"', t)
    if m: out["collections"] = int(m.group(1).replace(",", ""))
    # 赞赏金额（元）
    m = re.search(r'赞赏"\s*\n\s*- StaticText "([\d,]+)"', t)
    if m: out["appreciation"] = int(m.group(1).replace(",", ""))
    # 听全文 (context metric)
    m = re.search(r'听全文"\s*\n\s*- StaticText "(\d+) 人"', t)
    if m: out["listen_full"] = int(m.group(1))
    # 传播指标（分享扩散分析区块，image 格式，只取"首次传播"）
    # 送达人数 / 消息阅读人数 / 首次分享人数 / 总分享人数 / 分享产生的阅读人数
    for name, key in [("送达人数","reach"), ("消息阅读人数","msg_reads"),
                      ("首次分享人数","first_share_n"),
                      ("总分享人数","total_share_n"),
                      ("分享产生的阅读人数","share_induced_reads")]:
        m = re.search(r'image "'+re.escape(name)+r',\s*(\d+)\.\s*首次传播', t)
        if m: out[key] = int(m.group(1))
    # 渠道 (chart images): image "推荐, 91.007." —— 只保留真实流量来源，
    # 排除"送达人数/消息阅读人数/首次分享人数/总分享人数/分享产生的阅读人数"等干扰指标
    TRAFFIC = {"推荐","搜一搜","公众号主页","公众号消息","其它","聊天会话","朋友圈"}
    ch = {}
    for name, val in re.findall(r'image "([^,]+?),\s*([\d.]+)\.', t):
        nm = name.strip()
        if nm in TRAFFIC:
            ch[nm] = float(val)
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

# ---- 1) 读底表（article_details.json：id/title/publish，无 reads）----
base = json.load(open(f"{DATA}/article_details.json", encoding="utf-8"))
by_id = {a["id"]: a for a in base}

# ---- 2) 读列表页 reads（recent_articles.json：title/date/reads/appmsg_id）----
# 按 id(=appmsg_id) 注入到所有文章，统一 reads 口径为【发布列表页】值。
# 无 appmsg_id 的文章（noid|...）也按 id 直接匹配，因为 build_articles 写出的
# recent_articles.appmsg_id 与 article_details.id 同源。
list_reads_by_id = {}
list_reads_by_title = {}   # 兜底：极少数 id 不一致时按 title 匹配
if os.path.exists(f"{DATA}/recent_articles.json"):
    for a in json.load(open(f"{DATA}/recent_articles.json", encoding="utf-8")):
        r = a.get("reads")
        if r is None:
            continue
        aid = a.get("appmsg_id")
        title = (a.get("title") or "").strip()
        if aid:
            list_reads_by_id[aid] = r
        if title:
            list_reads_by_title[title] = r

n_injected = 0
for aid, a in by_id.items():
    r = list_reads_by_id.get(aid)
    if r is None:
        # 兜底：按 title 匹配（id 为 noid|... 时 appmsg_id 也是同样的 noid|...，应能命中；
        # 但若两边 id 格式偶有不一致，title 兜底）
        r = list_reads_by_title.get((a.get("title") or "").strip())
    if r is not None:
        a["reads"] = r
        n_injected += 1

# ---- 3) 解析 d2_*.txt 详情快照，合并详情字段（完读/分享/关注/渠道/画像等）----
n_fresh = 0
for fp in glob.glob(f"{RAW}/d2_*.txt"):
    fid = re.search(r"d2_(\d+)\.txt", fp).group(1)
    if fid not in by_id:
        print("WARN unmatched id", fid); continue
    fresh = parse_file(fp)
    if not fresh:
        print("WARN empty parse", fid); continue
    # reads_d2 来自详情页快照；reads 已由步骤 2 注入列表页值，不覆盖
    by_id[fid].update(fresh)
    by_id[fid]["_fresh"] = True
    n_fresh += 1

merged = list(by_id.values())

# ---- 4) 写回 article_details2.json ----
# 注意：本脚本不预算派生率（share_rate/coll_rate/follow_rate）。
# generate_final2.py 会现场用统一后的 reads 计算，确保口径一致。
json.dump(merged, open(f"{DATA}/article_details2.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"merged {len(merged)} articles, fresh-detail: {n_fresh}, list-reads injected: {n_injected}")

# ---- 5) 诊断打印：reads 口径一致性检查 ----
print("\n--- reads 口径检查 (reads=列表页, reads_d2=详情页快照) ---")
for a in merged:
    if a.get("_fresh"):
        r = a.get("reads"); r2 = a.get("reads_d2")
        flag = "" if r == r2 else f"  Δ={r2-r:+d}" if (r is not None and r2 is not None) else "  (缺一边)"
        print(f'{a["id"]} {a["title"][:14]:<16} reads={r} reads_d2={r2}{flag}')

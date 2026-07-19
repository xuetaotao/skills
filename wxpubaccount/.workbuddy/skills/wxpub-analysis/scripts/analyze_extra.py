# -*- coding: utf-8 -*-
"""Extra diagnostic passes: weekday, title taxonomy, read->follow funnel.

Usage: python analyze_extra.py [WORKSPACE_DIR]
  WORKSPACE_DIR defaults to cwd or env WXPUB_DIR.
"""
import json, re, sys, os
from datetime import date
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE
for _ in range(6):
    if os.path.exists(os.path.join(ROOT, "data")) or os.path.exists(os.path.join(ROOT, "reports")) or os.path.exists(os.path.join(ROOT, ".workbuddy")):
        break
    ROOT = os.path.dirname(ROOT)
BASE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("WXPUB_DIR", ROOT)
DATA = os.path.join(BASE, "data", "processed")

details = json.load(open(f"{DATA}/article_details2.json", encoding="utf-8"))
arts32 = json.load(open(f"{DATA}/recent_articles.json", encoding="utf-8"))

WK = ["周一","周二","周三","周四","周五","周六","周日"]

# details 里可能有些文章没有 reads 字段（无 d2 详情快照）。
# 用 .get() 兜底，避免 KeyError 崩溃。
# 两个样本集合（与 generate_final2.py 一致）：
#   details_with_reads = 有 reads 的（78 篇，用于标题分级/杠杆）
#   details_valid      = 有 completion 的（16 篇有 d2 详情快照，用于漏斗/相关性）
details_with_reads = [d for d in details if d.get("reads") is not None]
details_valid = [d for d in details if d.get("completion") is not None]

# ---- Pass 1: weekday of all articles ----
wd_cnt = defaultdict(int); wd_reads = defaultdict(list)
for a in arts32:
    if not a.get("date"): continue
    d = date.fromisoformat(a["date"])
    wd_cnt[d.weekday()] += 1
    wd_reads[d.weekday()].append(a.get("reads") or 0)
print(f"== 发布星期分布（{len(arts32)}篇）==")
for i in range(7):
    rs = wd_reads[i]
    avg = round(sum(rs)/len(rs),1) if rs else 0
    print(f"  {WK[i]}: {wd_cnt[i]}篇, 平均阅读 {avg}, 合计 {sum(rs)}")

# ---- Pass 2: title taxonomy ----
BRANDS = ["苹果","微信","百度","抖音","Claude","中国银行","腾讯","阿里","微软","谷歌","OpenAI","Meta","字节"]
CONFLICT = ["也","越来越","不再","扛不住","归零","彻底","第一次","终于","崩","逆袭","爆发","凉了","慌了","醒悟","治好"]
def classify(t):
    has_brand = any(b in t for b in BRANDS)
    has_conf = any(c in t for c in CONFLICT)
    is_q = "？" in t or "?" in t
    is_review = "复盘" in t or "周度" in t
    tags=[]
    if has_brand: tags.append("具名主体")
    if has_conf: tags.append("冲突")
    if is_q: tags.append("问号")
    if is_review: tags.append("复盘")
    return tags, has_brand, has_conf
print(f"\n== 标题类型 vs 阅读（{len(details_with_reads)}篇有 reads）==")
grp = defaultdict(list)
for d in details_with_reads:
    tags,_,_ = classify(d["title"])
    key = "+".join(tags) if tags else "其他"
    grp[key].append(d.get("reads") or 0)
for k,v in sorted(grp.items(), key=lambda x:-sum(x[1])/len(x[1]) if x[1] else 0):
    print(f"  [{k}] n={len(v)} 均阅读={round(sum(v)/len(v),1)}")

# ---- Pass 3: read->follow funnel (per article) ----
print(f"\n== 阅读→关注 漏斗（{len(details_valid)}篇）==")
print(f"  {'标题':<16}{'阅读':>6}{'完读%':>6}{'分享':>5}{'分享率%':>8}{'关注':>5}{'关注/千读':>9}")
fun = []
for d in sorted(details_valid, key=lambda x:-(x.get('reads') or 0)):
    r=d.get('reads') or 0; comp=d.get('completion') or 0
    sh=d.get('shares') or 0; nf=d.get('new_follows') or 0
    sr = round(sh/r*100,2) if r else 0
    fpr = round(nf/r*1000,2) if r else 0
    fun.append((d['title'][:15],r,comp,sh,sr,nf,fpr))
    print(f"  {d['title'][:15]:<16}{r:>6}{comp:>6}{sh:>5}{sr:>8}{nf:>5}{fpr:>9}")

# ---- Pass 4: what predicts follows? corr of nf with metrics ----
def corr(xs, ys):
    n=len(xs)
    if n<3: return 0
    mx=sum(xs)/n; my=sum(ys)/n
    num=sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    dx=sum((x-mx)**2 for x in xs)**0.5; dy=sum((y-my)**2 for y in ys)**0.5
    return round(num/(dx*dy),2) if dx and dy else 0
reads=[d.get('reads') or 0 for d in details_valid]
comp=[d.get('completion') or 0 for d in details_valid]
share=[d.get('shares') or 0 for d in details_valid]
sr=[ (d.get('shares') or 0)/(d.get('reads') or 1) for d in details_valid]
nf=[d.get('new_follows') or 0 for d in details_valid]
print("\n== 与「新增关注」的相关性（Pearson）==")
print(f"  阅读量 r={corr(reads,nf)}")
print(f"  完读率 r={corr(comp,nf)}")
print(f"  分享数 r={corr(share,nf)}")
print(f"  分享率 r={corr(sr,nf)}")
print(f"  完读率×分享率(乘积) r={corr([c*s for c,s in zip(comp,share)], nf)}")

# ---- Pass 5: brand vs non-brand read lift (用 details_with_reads，样本更全) ----
brand_reads=[]; non_reads=[]
for d in details_with_reads:
    tags,_,_ = classify(d["title"])
    (brand_reads if "具名主体" in tags else non_reads).append(d.get("reads") or 0)
print("\n== 具名主体 阅读杠杆 ==")
print(f"  具名主体 {len(brand_reads)}篇 均={round(sum(brand_reads)/len(brand_reads),1) if brand_reads else 0}")
print(f"  非具名   {len(non_reads)}篇 均={round(sum(non_reads)/len(non_reads),1) if non_reads else 0}")

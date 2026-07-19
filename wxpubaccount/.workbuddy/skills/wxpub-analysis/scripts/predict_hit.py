# -*- coding: utf-8 -*-
"""爆款预测器：基于历史数据规律，判断"想写的文章"是否能成爆款。

用法：
  python predict_hit.py --title "标题草稿" --topics "微信,AI,工具" [--day 周二]
  python predict_hit.py                    # 交互式输入

输出：评分卡（阅读爆款潜力 / 涨粉潜力 / 综合建议 / 历史相似案例）

评分依据 hit_baseline.json（由 update_baseline.py 生成，每次数据复盘后自动更新）。
"""
import json, os, sys, argparse
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE
for _ in range(6):
    if os.path.exists(os.path.join(ROOT, "data")) or os.path.exists(os.path.join(ROOT, ".workbuddy")):
        break
    ROOT = os.path.dirname(ROOT)
BASE = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else os.environ.get("WXPUB_DIR", ROOT)
DATA = os.path.join(BASE, "data", "processed")

# ---- 加载基准快照 ----
baseline_path = f"{DATA}/hit_baseline.json"
if not os.path.exists(baseline_path):
    print("❌ 未找到 hit_baseline.json，请先跑 update_baseline.py 或 generate_final2.py")
    sys.exit(1)
B = json.load(open(baseline_path, encoding="utf-8"))

# ---- 解析参数 ----
ap = argparse.ArgumentParser(description="爆款预测器")
ap.add_argument("--title", help="标题草稿")
ap.add_argument("--topics", help="主题关键词，逗号分隔，如 '微信,AI,工具'")
ap.add_argument("--day", default="周二", help="计划发文星期（周一~周日），默认周二")
args = ap.parse_args()

title = args.title or input("📝 标题草稿（可粗略）: ").strip()
topics_raw = args.topics or input("📝 主题关键词（逗号分隔，如 微信,AI,理财）: ").strip()
day = args.day
topics = [t.strip() for t in topics_raw.split(",") if t.strip()]

if not title or not topics:
    print("❌ 标题和主题关键词都不能为空")
    sys.exit(1)

# ---- 评分 ----
TF = B["title_formula"]
WM = B["weekday_pattern"]
FM = B["follow_mechanism"]
PR = B["platform_relevance"]

# 1. 标题公式分（0-50）
def classify_title(t):
    tags = []
    if any(b in t for b in TF["brand_keywords"]): tags.append("具名主体")
    if any(c in t for c in TF["conflict_keywords"]): tags.append("冲突")
    if "？" in t or "?" in t: tags.append("问号")
    if "复盘" in t or "周度" in t: tags.append("复盘")
    return tags

title_tags = classify_title(title)
title_score = 10  # 基础分
if "具名主体" in title_tags and "冲突" in title_tags:
    title_score = 50
elif "具名主体" in title_tags:
    title_score = 35
elif "冲突" in title_tags:
    title_score = 30
elif "问号" in title_tags:
    title_score = 20
elif "复盘" in title_tags:
    title_score = 10

# 2. 时机分（0-30）
day_scores = {"周二": 30, "周三": 15, "周四": 15, "周一": 10, "周五": 10, "周六": 0, "周日": 0}
day_score = day_scores.get(day, 15)

# 3. 话题热度分（0-20）
brand_hit = any(any(b in t for b in TF["brand_keywords"]) for t in topics)
follow_hit = any(t in PR["high_follow_topics"] for t in topics)
if brand_hit:
    topic_heat = 20
elif follow_hit:
    topic_heat = 15
else:
    topic_heat = 5

# 4. 平台相关度分（0-40）
if follow_hit:
    relevance = 40
elif brand_hit:
    relevance = 20
else:
    relevance = 10

# 检测零关注高风险话题（公司新闻/无关话题）
zero_follow_titles = [s["title"] for s in PR.get("zero_follow_high_read_samples", [])]
zero_follow_hit = any(t in title for t in zero_follow_titles) or any("公司" in t or "财报" in t for t in topics)
if zero_follow_hit:
    relevance = 0

# ---- 账号定位匹配检查 ----
# 主定位：科技/商业/金融；细分话题：high_follow_topics
POSITIONING = PR.get("account_positioning", {})
MAIN_TOPICS = POSITIONING.get("main", ["科技", "商业", "金融"])
RELATED_TOPICS = PR.get("high_follow_topics", [])
DEV_IMPACT = POSITIONING.get("deviation_impact", "频繁偏离定位会稀释账号认知")

positioning_match = []   # 命中的定位维度
positioning_miss = []    # 未命中的 topics
for t in topics:
    # 先查主定位（科技/商业/金融）
    main_hit = None
    for m in MAIN_TOPICS:
        # 宽松匹配：topic 包含主定位词，或主定位词包含 topic
        if m in t or t in m or (len(t) >= 2 and any(c in m for c in t)):
            main_hit = m
            break
    if main_hit:
        positioning_match.append(f"{t}→{main_hit}")
    elif t in RELATED_TOPICS or any(r in t or t in r for r in RELATED_TOPICS if len(r) >= 2):
        positioning_match.append(f"{t}→细分话题")
    else:
        positioning_miss.append(t)

if positioning_match:
    positioning_status = "✅ 在定位内"
    positioning_note = f"命中定位: {', '.join(positioning_match)}。与账号核心定位（{'/'.join(MAIN_TOPICS)}）一致，有利于长期推荐权重和粉丝认知。"
else:
    positioning_status = "⚠️ 偏离定位"
    positioning_note = f"话题「{', '.join(positioning_miss)}」不在账号定位（{'/'.join(MAIN_TOPICS)}）内。{DEV_IMPACT}。偶尔写可以建立人格，但不要成为主线；如果调整角度往科技/商业/金融靠，可回归定位。"

# 5. 完读分享潜力分（0-30）
method_words = ["如何", "方法", "技巧", "教程", "指南", "总结", "一文看懂"]
conflict_words = TF["conflict_keywords"]
review_words = ["复盘", "周度", "总结"]
if any(w in title for w in method_words):
    engage = 30  # 方法论高完读→高互动
elif any(w in title for w in conflict_words):
    engage = 25  # 冲突高分享
elif any(w in title for w in review_words):
    engage = 20  # 复盘高完读低分享
else:
    engage = 15

# 6. 互动潜力分（0-20，新增维度）
# 互动率 = (分享+留言+收藏)/阅读，高互动文章累积推荐权重
# 方法论/教程类→高互动（读者想收藏/留言提问）；冲突类→中互动（分享多但留言少）；新闻类→低互动
ENG = B.get("engagement", {})
avg_eng = ENG.get("avg_engagement_rate", 5)
if any(w in title for w in method_words):
    interaction = 20  # 方法论最容易引发互动（收藏+留言）
elif any(w in title for w in conflict_words):
    interaction = 15  # 冲突引发分享
elif any(w in title for w in review_words):
    interaction = 12  # 复盘引发收藏
else:
    interaction = 8   # 普通文章互动低

# 综合分
read_score = title_score + day_score + topic_heat                # 0-100
follow_score = relevance + engage + title_score*0.3 + day_score*0.5  # 0-100
follow_score = round(follow_score)

# ---- 综合建议（动态生成，引用实际命中维度和调整预期）----
# 计算各维度的"调整潜力"：如果改成最优配置能涨多少分
title_potential = 50 - title_score if title_score < 50 else 0       # 标题改到具名+冲突能涨
day_potential = 30 - day_score if day_score < 30 else 0             # 改周二能涨
topic_potential = 20 - topic_heat if topic_heat < 20 else 0         # 换话题能涨
relevance_potential = 40 - relevance if relevance < 40 else 0       # 换角度能涨

# 命中维度清单
hits = []
misses = []
if "具名主体" in title_tags: hits.append("具名主体")
else: misses.append("具名主体（品牌名）")
if "冲突" in title_tags: hits.append("冲突词")
else: misses.append("冲突词（也/扛不住/归零等）")
if day == "周二": hits.append("周二发文")
else: misses.append(f"周二（当前选{day}）")
if follow_hit: hits.append("高相关度话题")
else: misses.append("高相关度话题（微信/AI/工具/理财）")
if zero_follow_hit: misses.append("⚠️ 命中零关注风险话题")

# 历史案例引用
def pick_sample(samples, n=1):
    return samples[:n] if samples else []
hit_sample = pick_sample(TF.get("brand_conflict_samples", []))
follow_sample = pick_sample(PR.get("high_follow_samples", []))
zero_sample = pick_sample(PR.get("zero_follow_high_read_samples", []))

if read_score >= 70 and follow_score >= 60:
    verdict = "🌟 强烈推荐写"
    reason_lines = [
        f"标题公式({title_score}/50) + 时机({day_score}/30) + 话题({topic_heat}/20) 三重命中，既有爆款阅读潜力又能转化粉丝。",
        f"命中维度: {', '.join(hits)}。",
    ]
    if hit_sample:
        s = hit_sample[0]
        reason_lines.append(f"历史参考: 《{s['title']}》拿到 {s['reads']} 阅读（具名+冲突类均值 {TF['brand_conflict_avg'] if 'brand_conflict_avg' in TF else TF['brand_avg_reads']}）。")
    if follow_sample:
        s = follow_sample[0]
        reason_lines.append(f"涨粉参考: 《{s['title']}》{s['reads']} 读转化 {s['follows']} 关注（高相关度话题）。")
    reason_lines.append("保持当前配置，注意开头 3 句抛冲突、多用短段落提完读率。")
    reason = " ".join(reason_lines)

elif read_score >= 70 and follow_score < 60:
    verdict = "📈 适合冲阅读，但涨粉有限"
    reason_lines = [
        f"阅读能起量({read_score}/100)，但涨粉潜力低({follow_score}/100)——话题与账号相关度不够，读者看完即走。",
    ]
    if zero_follow_hit and zero_sample:
        s = zero_sample[0]
        reason_lines.append(f"⚠️ 此类话题历史 0 关注: 《{s['title']}》{s['reads']} 读 / 0 关注。")
    reason_lines.append(f"未命中: {', '.join([m for m in misses if '风险' not in m])}。")
    if relevance_potential > 0:
        reason_lines.append(f"💡 调整建议: 把角度往'微信/AI/工具/理财'靠，涨粉分可 +{relevance_potential}（从 {follow_score} 提到 {follow_score + relevance_potential}）。")
    reason = " ".join(reason_lines)

elif read_score < 70 and follow_score >= 60:
    verdict = "💚 阅读可能不爆，但能涨粉"
    reason_lines = [
        f"阅读量可能不爆({read_score}/100)，但话题相关度高({follow_score}/100)，能稳定转化粉丝。",
        f"未命中: {', '.join(misses)}。",
    ]
    if follow_sample:
        s = follow_sample[0]
        reason_lines.append(f"历史参考: 《{s['title']}》{s['reads']} 读 / {s['follows']} 关注（小阅读也能涨粉）。")
    potential = title_potential + day_potential
    if potential > 0:
        parts = []
        if title_potential > 0: parts.append(f"加具名+冲突(+{title_potential})")
        if day_potential > 0: parts.append(f"改周二(+{day_potential})")
        reason_lines.append(f"💡 调整建议: {' + '.join(parts)}，阅读分可从 {read_score} 提到 {read_score + potential}（达爆款线 70）。")
    reason = " ".join(reason_lines)

else:
    verdict = "⚠️ 建议调整"
    reason_lines = [
        f"阅读({read_score}/100)和涨粉({follow_score}/100)都偏低，按当前配置写出来大概率平庸。",
        f"未命中: {', '.join(misses)}。",
    ]
    total_potential = title_potential + day_potential + topic_potential + relevance_potential
    if total_potential > 0:
        parts = []
        if title_potential > 0: parts.append(f"标题改具名+冲突(+{title_potential}阅读)")
        if day_potential > 0: parts.append(f"改周二(+{day_potential}阅读)")
        if relevance_potential > 0: parts.append(f"换相关度话题(+{relevance_potential}涨粉)")
        reason_lines.append(f"💡 调整建议: {' + '.join(parts)}，综合可 +{total_potential} 分。")
    else:
        reason_lines.append("当前已是较优配置，但样本数据有限，建议参考历史案例谨慎判断。")
    reason = " ".join(reason_lines)

# ---- 历史相似案例 ----
def find_similar(title, samples, n=3):
    """从样本里找标题关键词重合度高的"""
    title_words = set(title)  # 简单字符级
    scored = []
    for s in samples:
        st = s.get("title", "")
        # 计算共同字符数
        common = len(set(st) & title_words)
        scored.append((common, s))
    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored[:n] if _ > 0]

similar_hits = find_similar(title, TF.get("brand_conflict_samples", []))
similar_follow = find_similar(title, PR.get("high_follow_samples", []))

# ---- 输出评分卡 ----
print(f"""
╔══════════════════════════════════════════════════════════╗
║              📊 爆款预测评分卡                            ║
╚══════════════════════════════════════════════════════════╝

📝 输入：
   标题: 《{title}》
   主题: {", ".join(topics)}
   计划发文: {day}

🏷️  标题分类: {"+".join(title_tags) if title_tags else "普通"}

┌─────────────────────────────────────────────────────────┐
│  📈 阅读爆款潜力: {read_score:>3}/100                              │
│    ├─ 标题公式: {title_score:>3}/50  ({", ".join(title_tags) if title_tags else "普通"})           │
│    ├─ 时机分:   {day_score:>3}/30  ({day})                  │
│    └─ 话题热度: {topic_heat:>3}/20                            │
├─────────────────────────────────────────────────────────┤
│  💚 涨粉潜力:    {follow_score:>3}/100                              │
│    ├─ 平台相关度: {relevance:>3}/40                            │
│    ├─ 完读分享:   {engage:>3}/30                            │
│    └─ 标题+时机: {round(title_score*0.3 + day_score*0.5):>3}/30                           │
├─────────────────────────────────────────────────────────┤
│  🔥 互动潜力:    {interaction:>3}/20  ({'方法论→高收藏留言' if interaction>=18 else '冲突→高分享' if interaction>=13 else '普通'})              │
├─────────────────────────────────────────────────────────┤
│  📍 定位匹配:    {positioning_status}                              │
└─────────────────────────────────────────────────────────┘

🎯 综合判断: {verdict}
   {reason}

📍 定位说明: {positioning_note}

📊 数据基准（{B['data_window']['start']} ~ {B['data_window']['end']}，{B['data_window']['n_articles']} 篇样本）:
   • 具名+冲突标题杠杆 ≈ {TF['lift']}× (具名均 {TF['brand_avg_reads']} vs 非具名均 {TF['nonb_avg_reads']})
   • {day}历史贡献: {WM['tue_share_pct'] if day=='周二' else '其他工作日'}% 阅读{f"（{WM['tue_n']} 篇均 {WM['tue_avg_reads']}）" if day=='周二' else f"（合计 {WM['other_weekday_range'][0]}–{WM['other_weekday_range'][1]}）"}
   • 涨粉机制: 关注与阅读 r={FM['r_read_vs_follow']}（弱），与完读×分享 r={FM['r_completion_x_share_vs_follow']}（强）
   • 互动基准: 平均互动率 {ENG.get('avg_engagement_rate', '?')}%，高互动(≥5%)文章累积推荐权重
   • 当前粉丝: {B['fan_status']['fans']} (月增 {B['fan_status']['growth_month_pct']}%)""")

# 互动潜力高时的额外提示
if interaction >= 15 and read_score < 70:
    print(f"""
💡 互动提示: 此文互动潜力高({interaction}/20)，虽然阅读可能不爆，但高互动会累积推荐权重，长远利好后续文章的曝光。""")

if similar_hits:
    print(f"""
📚 历史爆款参考（具名+冲突类）:""")
    for s in similar_hits:
        print(f"   • 《{s['title']}》 {s['reads']} 读 / {s['new_follows']} 关注 / {s['shares']} 分享")

if similar_follow:
    print(f"""
💚 历史涨粉参考（高关注转化）:""")
    for s in similar_follow:
        print(f"   • 《{s['title']}》 {s['reads']} 读 / {s['follows']} 关注 / 完读 {s.get('completion','?')}%")

# 具体建议
suggestions = []
if "具名主体" not in title_tags:
    suggestions.append("标题加具名主体（苹果/微信/百度/Claude 等品牌名），杠杆可放大 ~29×")
if "冲突" not in title_tags and "复盘" not in title_tags:
    suggestions.append("标题加冲突词（也/扛不住/归零/终于/崩 等），强化反差感")
if day != "周二" and day in ["周六", "周日"]:
    suggestions.append("周末从不发文，建议改周二（占 52% 阅读）或工作日")
if not follow_hit and not zero_follow_hit:
    suggestions.append("话题不在'微信/AI/工具/理财'高相关度列表，涨粉转化可能偏低")
if zero_follow_hit:
    suggestions.append("⚠️ 此话题历史 0 关注（如纯公司新闻），建议转角度到'对读者有用'的工具/理财视角")
if not suggestions:
    suggestions.append("配置优秀，按计划写即可。注意开头 3 句抛冲突，多用短段落提完读率。")

print(f"""
💡 优化建议:""")
for i, s in enumerate(suggestions, 1):
    print(f"   {i}. {s}")

print(f"""
─────────────────────────────────────────────────────────
基准快照生成于 {B['generated_at']} | 每次数据复盘后自动更新
""")

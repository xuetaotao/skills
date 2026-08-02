# -*- coding: utf-8 -*-
"""爆款预测核心逻辑。"""
import json
import os
from typing import Any, Dict, List, Optional


WEEKDAY_SCORES = {
    "周一": 10,
    "周二": 30,
    "周三": 15,
    "周四": 15,
    "周五": 10,
    "周六": 0,
    "周日": 0,
}

METHOD_WORDS = ["如何", "方法", "技巧", "教程", "指南", "总结", "一文看懂"]
REVIEW_WORDS = ["复盘", "周度", "总结"]


def find_workspace_root(start: Optional[str] = None) -> str:
    root = os.path.abspath(start or os.path.dirname(__file__))
    for _ in range(6):
        if os.path.exists(os.path.join(root, "data")) or os.path.exists(os.path.join(root, ".workbuddy")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    return os.path.abspath(start or os.path.dirname(__file__))


def resolve_base_dir(base: Optional[str] = None) -> str:
    if base:
        return os.path.abspath(base)
    return find_workspace_root()


def load_baseline(base_dir: Optional[str] = None) -> Dict[str, Any]:
    base = resolve_base_dir(base_dir)
    baseline_path = os.path.join(base, "data", "processed", "hit_baseline.json")
    if not os.path.exists(baseline_path):
        raise FileNotFoundError("未找到 hit_baseline.json，请先跑 update_baseline.py 或 generate_final2.py")
    with open(baseline_path, encoding="utf-8") as f:
        return json.load(f)


def split_topics(raw: str) -> List[str]:
    return [t.strip() for t in (raw or "").replace("，", ",").split(",") if t.strip()]


def normalize_topic(topic: str) -> str:
    """归一化主题词用于去重比较。"""
    return (topic or "").strip().lower()


def extract_topics_from_title(title: str, baseline: Dict[str, Any]) -> List[str]:
    """从标题里抽取命中的主题词（用于饱和度判断）。"""
    if not title:
        return []
    norm = title.lower()
    pool = baseline.get("platform_relevance", {}).get("high_follow_topics", []) + \
           baseline.get("title_formula", {}).get("brand_keywords", [])
    return [w for w in pool if w.lower() in norm]


def classify_title(title: str, title_formula: Dict[str, Any]) -> List[str]:
    tags: List[str] = []
    if any(word in title for word in title_formula.get("brand_keywords", [])):
        tags.append("具名主体")
    if any(word in title for word in title_formula.get("conflict_keywords", [])):
        tags.append("冲突")
    if "？" in title or "?" in title:
        tags.append("问号")
    if "复盘" in title or "周度" in title:
        tags.append("复盘")
    return tags


def _pick_sample(samples: List[Dict[str, Any]], n: int = 1) -> List[Dict[str, Any]]:
    return samples[:n] if samples else []


def find_similar(title: str, samples: List[Dict[str, Any]], n: int = 3) -> List[Dict[str, Any]]:
    title_words = set(title)
    scored = []
    for sample in samples:
        sample_title = sample.get("title", "")
        common = len(set(sample_title) & title_words)
        scored.append((common, sample))
    scored.sort(key=lambda item: -item[0])
    return [sample for common, sample in scored[:n] if common > 0]


def score_topic_idea(title: str, topics: List[str], day: str = "周二", baseline: Optional[Dict[str, Any]] = None, recent_articles: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    if not title or not topics:
        raise ValueError("标题和主题关键词都不能为空")

    baseline = baseline or load_baseline()
    title_formula = baseline["title_formula"]
    weekday_pattern = baseline["weekday_pattern"]
    follow_mechanism = baseline["follow_mechanism"]
    platform = baseline["platform_relevance"]
    engagement_base = baseline.get("engagement", {})

    title_tags = classify_title(title, title_formula)

    # 标题分细粒度化（不是只有 35/50 两档）
    has_brand = "具名主体" in title_tags
    has_conflict = "冲突" in title_tags
    has_question = "问号" in title_tags
    has_method = any(word in title for word in METHOD_WORDS)
    has_review = "复盘" in title or "周度" in title

    if has_brand and has_conflict:
        title_score = 50
    elif has_brand and has_method:
        title_score = 42  # 具名+方法论：次优组合
    elif has_brand and has_question:
        title_score = 38  # 具名+反问
    elif has_brand:
        title_score = 35
    elif has_conflict and has_method:
        title_score = 33
    elif has_conflict:
        title_score = 30
    elif has_method:
        title_score = 25  # 纯方法论也有一定阅读力
    elif has_question:
        title_score = 20
    elif has_review:
        title_score = 10
    else:
        title_score = 10

    day_score = WEEKDAY_SCORES.get(day, 15)

    brand_hit = any(any(brand in topic for brand in title_formula.get("brand_keywords", [])) for topic in topics)
    follow_hit = any(topic in platform.get("high_follow_topics", []) for topic in topics)
    if brand_hit:
        topic_heat = 20
    elif follow_hit:
        topic_heat = 15
    else:
        topic_heat = 5

    if follow_hit:
        relevance = 40
    elif brand_hit:
        relevance = 20
    else:
        relevance = 10

    zero_follow_titles = [sample["title"] for sample in platform.get("zero_follow_high_read_samples", [])]
    zero_follow_hit = any(sample_title in title for sample_title in zero_follow_titles) or any("公司" in topic or "财报" in topic for topic in topics)
    if zero_follow_hit:
        relevance = 0

    # 饱和度惩罚：最近 30 天已写过同主题词的文章扣分（推荐器专用，predict_hit 不传则不生效）
    saturation_penalty = 0
    saturation_notes: List[str] = []
    if recent_articles:
        topic_set = set(normalize_topic(t) for t in topics)
        recent_overlap = []
        for art in recent_articles[-30:]:
            art_title = art.get("title", "")
            art_topics = set(normalize_topic(t) for t in extract_topics_from_title(art_title, baseline))
            overlap = topic_set & art_topics
            if overlap:
                recent_overlap.append((art_title[:20], overlap))
        if recent_overlap:
            # 每篇同主题文章扣 8 分，最多扣 24
            saturation_penalty = min(len(recent_overlap) * 8, 24)
            saturation_notes.append(f"最近30天有 {len(recent_overlap)} 篇同主题文章，扣 {saturation_penalty} 分")
            for art_title, overlap in recent_overlap[:2]:
                saturation_notes.append(f"  - 《{art_title}》重叠话题：{', '.join(overlap)}")

    positioning = platform.get("account_positioning", {})
    main_topics = positioning.get("main", ["科技", "商业", "金融"])
    related_topics = platform.get("high_follow_topics", [])
    deviation_impact = positioning.get("deviation_impact", "频繁偏离定位会稀释账号认知")

    positioning_match: List[str] = []
    positioning_miss: List[str] = []
    for topic in topics:
        main_hit = None
        for main_topic in main_topics:
            if main_topic in topic or topic in main_topic or (len(topic) >= 2 and any(ch in main_topic for ch in topic)):
                main_hit = main_topic
                break
        if main_hit:
            positioning_match.append(f"{topic}→{main_hit}")
        elif topic in related_topics or any(rel in topic or topic in rel for rel in related_topics if len(rel) >= 2):
            positioning_match.append(f"{topic}→细分话题")
        else:
            positioning_miss.append(topic)

    if positioning_match:
        positioning_status = "✅ 在定位内"
        positioning_note = (
            f"命中定位: {', '.join(positioning_match)}。"
            f"与账号核心定位（{'/'.join(main_topics)}）一致，有利于长期推荐权重和粉丝认知。"
        )
    else:
        positioning_status = "⚠️ 偏离定位"
        positioning_note = (
            f"话题「{', '.join(positioning_miss)}」不在账号定位（{'/'.join(main_topics)}）内。"
            f"{deviation_impact}。偶尔写可以建立人格，但不要成为主线；如果调整角度往科技/商业/金融靠，可回归定位。"
        )

    conflict_words = title_formula.get("conflict_keywords", [])
    if any(word in title for word in METHOD_WORDS):
        engage = 30
    elif any(word in title for word in conflict_words):
        engage = 25
    elif any(word in title for word in REVIEW_WORDS):
        engage = 20
    else:
        engage = 15

    if any(word in title for word in METHOD_WORDS):
        interaction = 20
    elif any(word in title for word in conflict_words):
        interaction = 15
    elif any(word in title for word in REVIEW_WORDS):
        interaction = 12
    else:
        interaction = 8

    read_score = title_score + day_score + topic_heat
    follow_score = round(relevance + engage + title_score * 0.3 + day_score * 0.5)

    # 应用饱和度惩罚（推荐器专用，predict_hit 不传 recent_articles 则不生效）
    if saturation_penalty > 0:
        read_score = max(read_score - saturation_penalty, 0)
        follow_score = max(follow_score - saturation_penalty // 2, 0)

    title_potential = 50 - title_score if title_score < 50 else 0
    day_potential = 30 - day_score if day_score < 30 else 0
    topic_potential = 20 - topic_heat if topic_heat < 20 else 0
    relevance_potential = 40 - relevance if relevance < 40 else 0

    hits: List[str] = []
    misses: List[str] = []
    if "具名主体" in title_tags:
        hits.append("具名主体")
    else:
        misses.append("具名主体（品牌名）")
    if "冲突" in title_tags:
        hits.append("冲突词")
    else:
        misses.append("冲突词（也/扛不住/归零等）")
    if day == "周二":
        hits.append("周二发文")
    else:
        misses.append(f"周二（当前选{day}）")
    if follow_hit:
        hits.append("高相关度话题")
    else:
        misses.append("高相关度话题（微信/AI/工具/理财）")
    if zero_follow_hit:
        misses.append("⚠️ 命中零关注风险话题")

    hit_sample = _pick_sample(title_formula.get("brand_conflict_samples", []))
    follow_sample = _pick_sample(platform.get("high_follow_samples", []))
    zero_sample = _pick_sample(platform.get("zero_follow_high_read_samples", []))

    if read_score >= 70 and follow_score >= 60:
        verdict = "🌟 强烈推荐写"
        reason_lines = [
            f"标题公式({title_score}/50) + 时机({day_score}/30) + 话题({topic_heat}/20) 三重命中，既有爆款阅读潜力又能转化粉丝。",
            f"命中维度: {', '.join(hits)}。",
        ]
        if hit_sample:
            sample = hit_sample[0]
            avg_reads = title_formula.get("brand_conflict_avg", title_formula.get("brand_avg_reads", 0))
            reason_lines.append(f"历史参考: 《{sample['title']}》拿到 {sample['reads']} 阅读（具名+冲突类均值 {avg_reads}）。")
        if follow_sample:
            sample = follow_sample[0]
            reason_lines.append(f"涨粉参考: 《{sample['title']}》{sample['reads']} 读转化 {sample['follows']} 关注（高相关度话题）。")
        reason_lines.append("保持当前配置，注意开头 3 句抛冲突、多用短段落提完读率。")
        reason = " ".join(reason_lines)
    elif read_score >= 70 and follow_score < 60:
        verdict = "📈 适合冲阅读，但涨粉有限"
        reason_lines = [
            f"阅读能起量({read_score}/100)，但涨粉潜力低({follow_score}/100)——话题与账号相关度不够，读者看完即走。"
        ]
        if zero_follow_hit and zero_sample:
            sample = zero_sample[0]
            reason_lines.append(f"⚠️ 此类话题历史 0 关注: 《{sample['title']}》{sample['reads']} 读 / 0 关注。")
        reason_lines.append(f"未命中: {', '.join([m for m in misses if '风险' not in m])}。")
        if relevance_potential > 0:
            reason_lines.append(
                f"💡 调整建议: 把角度往'微信/AI/工具/理财'靠，涨粉分可 +{relevance_potential}（从 {follow_score} 提到 {follow_score + relevance_potential}）。"
            )
        reason = " ".join(reason_lines)
    elif read_score < 70 and follow_score >= 60:
        verdict = "💚 阅读可能不爆，但能涨粉"
        reason_lines = [
            f"阅读量可能不爆({read_score}/100)，但话题相关度高({follow_score}/100)，能稳定转化粉丝。",
            f"未命中: {', '.join(misses)}。",
        ]
        if follow_sample:
            sample = follow_sample[0]
            reason_lines.append(f"历史参考: 《{sample['title']}》{sample['reads']} 读 / {sample['follows']} 关注（小阅读也能涨粉）。")
        potential = title_potential + day_potential
        if potential > 0:
            parts = []
            if title_potential > 0:
                parts.append(f"加具名+冲突(+{title_potential})")
            if day_potential > 0:
                parts.append(f"改周二(+{day_potential})")
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
            if title_potential > 0:
                parts.append(f"标题改具名+冲突(+{title_potential}阅读)")
            if day_potential > 0:
                parts.append(f"改周二(+{day_potential}阅读)")
            if relevance_potential > 0:
                parts.append(f"换相关度话题(+{relevance_potential}涨粉)")
            reason_lines.append(f"💡 调整建议: {' + '.join(parts)}，综合可 +{total_potential} 分。")
        else:
            reason_lines.append("当前已是较优配置，但样本数据有限，建议参考历史案例谨慎判断。")
        reason = " ".join(reason_lines)

    similar_hits = find_similar(title, title_formula.get("brand_conflict_samples", []))
    similar_follow = find_similar(title, platform.get("high_follow_samples", []))

    suggestions: List[str] = []
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

    total_score = round(read_score * 0.45 + follow_score * 0.45 + interaction * 0.5, 1)

    return {
        "title": title,
        "topics": topics,
        "day": day,
        "baseline": baseline,
        "title_tags": title_tags,
        "title_score": title_score,
        "day_score": day_score,
        "topic_heat": topic_heat,
        "relevance": relevance,
        "engage": engage,
        "interaction": interaction,
        "read_score": read_score,
        "follow_score": follow_score,
        "total_score": total_score,
        "brand_hit": brand_hit,
        "follow_hit": follow_hit,
        "zero_follow_hit": zero_follow_hit,
        "positioning_status": positioning_status,
        "positioning_note": positioning_note,
        "verdict": verdict,
        "reason": reason,
        "hits": hits,
        "misses": misses,
        "similar_hits": similar_hits,
        "similar_follow": similar_follow,
        "suggestions": suggestions,
        "weekday_pattern": weekday_pattern,
        "follow_mechanism": follow_mechanism,
        "engagement_base": engagement_base,
        "prediction_pass": read_score >= 70 and follow_score >= 60,
        "saturation_penalty": saturation_penalty,
        "saturation_notes": saturation_notes,
    }


def render_prediction_card(result: Dict[str, Any], baseline: Optional[Dict[str, Any]] = None) -> str:
    baseline = baseline or result["baseline"]
    title_formula = baseline["title_formula"]
    weekday_pattern = baseline["weekday_pattern"]
    follow_mechanism = baseline["follow_mechanism"]
    engagement_base = baseline.get("engagement", {})

    title = result["title"]
    topics = result["topics"]
    day = result["day"]
    title_tags = result["title_tags"]

    output = [
        f"""
╔══════════════════════════════════════════════════════════╗
║              📊 爆款预测评分卡                            ║
╚══════════════════════════════════════════════════════════╝

📝 输入：
   标题: 《{title}》
   主题: {", ".join(topics)}
   计划发文: {day}

🏷️  标题分类: {"+".join(title_tags) if title_tags else "普通"}

┌─────────────────────────────────────────────────────────┐
│  📈 阅读爆款潜力: {result['read_score']:>3}/100                              │
│    ├─ 标题公式: {result['title_score']:>3}/50  ({", ".join(title_tags) if title_tags else "普通"})           │
│    ├─ 时机分:   {result['day_score']:>3}/30  ({day})                  │
│    └─ 话题热度: {result['topic_heat']:>3}/20                            │
├─────────────────────────────────────────────────────────┤
│  💚 涨粉潜力:    {result['follow_score']:>3}/100                              │
│    ├─ 平台相关度: {result['relevance']:>3}/40                            │
│    ├─ 完读分享:   {result['engage']:>3}/30                            │
│    └─ 标题+时机: {round(result['title_score'] * 0.3 + result['day_score'] * 0.5):>3}/30                           │
├─────────────────────────────────────────────────────────┤
│  🔥 互动潜力:    {result['interaction']:>3}/20  ({'方法论→高收藏留言' if result['interaction'] >= 18 else '冲突→高分享' if result['interaction'] >= 13 else '普通'})              │
├─────────────────────────────────────────────────────────┤
│  📍 定位匹配:    {result['positioning_status']}                              │
└─────────────────────────────────────────────────────────┘

🎯 综合判断: {result['verdict']}
   {result['reason']}

📍 定位说明: {result['positioning_note']}

📊 数据基准（{baseline['data_window']['start']} ~ {baseline['data_window']['end']}，{baseline['data_window']['n_articles']} 篇样本）:
   • 具名+冲突标题杠杆 ≈ {title_formula['lift']}× (具名均 {title_formula['brand_avg_reads']} vs 非具名均 {title_formula['nonb_avg_reads']})
   • {day}历史贡献: {weekday_pattern['tue_share_pct'] if day == '周二' else '其他工作日'}% 阅读{f"（{weekday_pattern['tue_n']} 篇均 {weekday_pattern['tue_avg_reads']}）" if day == '周二' else f"（合计 {weekday_pattern['other_weekday_range'][0]}–{weekday_pattern['other_weekday_range'][1]}）"}
   • 涨粉机制: 关注与阅读 r={follow_mechanism['r_read_vs_follow']}（弱），与完读×分享 r={follow_mechanism['r_completion_x_share_vs_follow']}（强）
   • 互动基准: 平均互动率 {engagement_base.get('avg_engagement_rate', '?')}%，高互动(≥5%)文章累积推荐权重
   • 当前粉丝: {baseline['fan_status']['fans']} (月增 {baseline['fan_status']['growth_month_pct']}%)"""
    ]

    if result["interaction"] >= 15 and result["read_score"] < 70:
        output.append(f"""
💡 互动提示: 此文互动潜力高({result['interaction']}/20)，虽然阅读可能不爆，但高互动会累积推荐权重，长远利好后续文章的曝光。""")

    if result["similar_hits"]:
        output.append("\n📚 历史爆款参考（具名+冲突类）:")
        for sample in result["similar_hits"]:
            output.append(f"   • 《{sample['title']}》 {sample['reads']} 读 / {sample['new_follows']} 关注 / {sample['shares']} 分享")

    if result["similar_follow"]:
        output.append("\n💚 历史涨粉参考（高关注转化）:")
        for sample in result["similar_follow"]:
            output.append(f"   • 《{sample['title']}》 {sample['reads']} 读 / {sample['follows']} 关注 / 完读 {sample.get('completion', '?')}%")

    output.append("\n💡 优化建议:")
    for idx, suggestion in enumerate(result["suggestions"], 1):
        output.append(f"   {idx}. {suggestion}")

    output.append(f"""

─────────────────────────────────────────────────────────
基准快照生成于 {baseline['generated_at']} | 每次数据复盘后自动更新
""")
    return "\n".join(output).strip()

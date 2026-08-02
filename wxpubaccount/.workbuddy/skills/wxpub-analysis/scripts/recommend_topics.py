# -*- coding: utf-8 -*-
"""选题推荐器 v2：数据驱动的"有效角度 × 开放话题"模式。

设计原则（用户 2026-07-20 明确）：
- 话题开放：不限定在"微信搜一搜/微信AI"等已验证方向，任何新热点/定位内方向都能推荐
- 角度学习：从历史数据学"什么结构/切口有效"（复盘体/方法论/冲突体等），而非学话题
- 预测器有区分度：带饱和度惩罚，已写过的同主题扣分，避免橡皮图章
- 例外机制生效：未通过预测但角度好/互动潜力高的也保留
- 输出精简：选题卡片（选题+角度+要点+素材线索+5-8备选标题），不假装生成初稿
"""
import argparse
import json
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from prediction_core import find_workspace_root, load_baseline, score_topic_idea, split_topics, normalize_topic


def configure_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ============================================================
# 热点源（扩展：Bing/Google + 36氪/虎嗅/极客公园 RSS）
# ============================================================
RSS_SOURCES = [
    "https://www.bing.com/news/search?q={query}&format=RSS&mkt=zh-CN",
    "https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
]

# 科技媒体 RSS（中文科技资讯覆盖更好）
TECH_RSS_FEEDS = [
    "https://36kr.com/feed",
    "https://www.huxiu.com/rss/0.xml",
    "https://www.geekpark.net/rss",
]

DEFAULT_QUERIES = [
    "微信 AI",
    "AI 搜索",
    "OpenAI agent",
    "苹果 AI",
    "腾讯 AI 财报",
    "抖音 视频号",
    "科技 商业",
    "金融 理财",
]

NOISE_KEYWORDS = [
    "足球", "nba", "比赛", "明星", "电视剧", "电影", "综艺",
    "旅游", "房价", "楼市", "汽车", "新车", "球员", "八卦", "娱乐",
]

UTILITY_KEYWORDS = [
    "工具", "方法", "效率", "工作流", "搜索", "订阅", "隐私",
    "财报", "广告", "视频号", "理财", "Agent", "决策", "框架",
]

# ============================================================
# 标题公式池（8 种结构，替换单一"X不再只是Y"公式）
# 每种 2 个模板，按话题+品牌填充
# ============================================================
TITLE_FORMULAS: List[Tuple[str, List[str]]] = [
    ("反问", [
        "{brand}这次的{topic}动作，普通人到底该不该跟？",
        "{topic}越来越热，但多数人搞错了重点？",
    ]),
    ("清单", [
        "关于{topic}，普通人最该先补上的3个判断",
        "{topic}最值得先做的3件事",
    ]),
    ("判断", [
        "{brand}卷{topic}，普通人最先被改写的是这件事",
        "{topic}的真相：不是热闹，而是这件事",
    ]),
    ("方法论", [
        "一文看懂{topic}：普通人最该先搞清的3个问题",
        "如何判断{topic}值不值得跟：一套决策框架",
    ]),
    ("冲突", [
        "{brand}也扛不住{topic}了",
        "{brand}不再只是{old}：{topic}正在改写{field}",
    ]),
    ("对比", [
        "{topic} vs {topic2}：普通人该怎么选",
        "{brand}和{brand2}都在卷{topic}，差别在哪里",
    ]),
    ("故事", [
        "我用{tool}跑了一周{topic}，结论是…",
        "当{brand}开始{action}，普通人最先该做什么",
    ]),
    ("机会", [
        "{topic}的机会可能不在流量，而在这件事",
        "{brand}这次的{topic}，真正值得盯的是这个信号",
    ]),
]

# 角度→写作要点映射（从历史数据学的有效结构）
ANGLE_WRITING_POINTS = {
    "方法论/科普体": [
        "先给一个读者能感知的困惑或误区，再展开体系。",
        "拆成3个层次，每层配一个具体例子。",
        "结尾给一份可执行清单，促进收藏。",
    ],
    "复盘体": [
        "先说结论，再倒推过程，避免流水账。",
        "诚实写出哪里没做好，增强可信度。",
        "结尾提炼可复用的经验，不要只讲自己的事。",
    ],
    "冲突/风险体": [
        "用一个反差场景开头，抓住注意力。",
        "写清楚风险的具体表现，不要空泛讲伦理。",
        "结尾给出规避动作，落到读者决策。",
    ],
    "机会/判断体": [
        "先说为什么现在值得关注，再给判断。",
        "把趋势翻译成读者能感知的变化。",
        "结尾给一个现在就能做的小动作。",
    ],
    "对比/选择体": [
        "先讲用户已感受到的差异，再讲商业逻辑。",
        "把读者分2-3类，给出不同建议。",
        "结尾回到读者该怎么做，不要只做平台评论。",
    ],
    "清单/数字体": [
        "每条先给判断，再给依据，不要平铺。",
        "3条之间要有递进，不要并列堆砌。",
        "结尾留一个可回答的问题，争取留言。",
    ],
    "平台生态体": [
        "先讲这次变化是什么，再说为什么比功能本身更重要。",
        "拆成用户价值、创作者价值、平台意图三个层次。",
        "结尾给一份可以立刻试用的清单。",
    ],
    "决策框架体": [
        "先定义判断维度，不要直接给结论。",
        "用真实场景做取舍示范，增强可信度。",
        "结尾强调提高决策质量本身就是长期回报。",
    ],
}

REQUEST_PROFILE_KEYWORDS = {
    "practical": ["实用", "方法", "工具", "可执行", "操作", "教程", "指南"],
    "evergreen": ["价值", "长期", "非热点", "常青", "长期有效", "不追热点"],
    "hot": ["热点", "新闻", "热搜", "借势"],
    "workflow": ["工作流", "效率", "系统", "流程"],
    "finance": ["理财", "商业", "付费", "订阅", "成本"],
    "wechat": ["微信", "搜一搜", "视频号"],
}

ZH_NUM_MAP = {"一": 1, "二": 2, "两": 2, "俩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


# ============================================================
# 工具函数
# ============================================================
def chinese_num_to_int(raw: str) -> Optional[int]:
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)
    if raw in ZH_NUM_MAP:
        return ZH_NUM_MAP[raw]
    if raw == "十":
        return 10
    if len(raw) == 2 and raw[0] == "十" and raw[1] in ZH_NUM_MAP:
        return 10 + ZH_NUM_MAP[raw[1]]
    if len(raw) == 2 and raw[1] == "十" and raw[0] in ZH_NUM_MAP:
        return ZH_NUM_MAP[raw[0]] * 10
    if len(raw) == 3 and raw[1] == "十" and raw[0] in ZH_NUM_MAP and raw[2] in ZH_NUM_MAP:
        return ZH_NUM_MAP[raw[0]] * 10 + ZH_NUM_MAP[raw[2]]
    return None


def detect_count_from_prompt(prompt: str) -> Optional[int]:
    match = re.search(r"([0-9]+|[一二两俩三四五六七八九十]+)\s*(个|篇|条)?\s*(选题|题目|方向)", prompt)
    if match:
        return chinese_num_to_int(match.group(1))
    if "几个" in prompt or "一些" in prompt:
        return 6
    return None


def detect_day_from_prompt(prompt: str) -> Optional[str]:
    match = re.search(r"(周|星期)([一二三四五六日天])", prompt)
    if not match:
        return None
    day = match.group(2)
    return f"周{'日' if day in ['日', '天'] else day}"


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def unique_keep_order(items: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def jaccard_char(a: str, b: str) -> float:
    sa = set(normalize_text(a))
    sb = set(normalize_text(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def recency_score(published_at: Optional[datetime]) -> int:
    if not published_at:
        return 6
    now = datetime.now(timezone.utc)
    delta_days = max((now - published_at).days, 0)
    if delta_days <= 1:
        return 20
    if delta_days <= 3:
        return 16
    if delta_days <= 7:
        return 12
    return 8


def parse_rss_datetime(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def split_query_terms(query: str) -> List[str]:
    return [token for token in re.split(r"[\s,，/|+]+", query or "") if token]


def fmt_dt(dt: Optional[datetime]) -> str:
    if not dt:
        return "-"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


# ============================================================
# 自然语言请求解析
# ============================================================
def infer_profiles_from_prompt(prompt: str) -> List[str]:
    norm = normalize_text(prompt)
    profiles = []
    negative_hot = any(token in norm for token in [normalize_text(word) for word in ["非热点", "不追热点", "不要热点", "只要价值", "只看价值"]])
    for name, words in REQUEST_PROFILE_KEYWORDS.items():
        if name == "hot" and negative_hot:
            continue
        if any(normalize_text(word) in norm for word in words):
            profiles.append(name)
    return profiles


def parse_ask_request(prompt: str) -> Dict[str, Any]:
    if not prompt:
        return {"raw": "", "count": None, "day": None, "queries": [], "offline": False, "profiles": []}
    norm = normalize_text(prompt)
    offline = any(token in norm for token in [normalize_text(word) for word in ["只看价值", "只要价值", "纯价值", "不追热点", "不要热点", "离线"]])
    return {
        "raw": prompt.strip(),
        "count": detect_count_from_prompt(prompt),
        "day": detect_day_from_prompt(prompt),
        "queries": [],
        "offline": offline,
        "profiles": infer_profiles_from_prompt(prompt),
    }


def load_recent_articles(base: str) -> List[Dict[str, Any]]:
    path = os.path.join(base, "data", "processed", "recent_articles.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# 动态检索词：从历史文章抽高频主题词 + 默认词 + 用户补充
# ============================================================
def extract_history_topics(recent_articles: List[Dict[str, Any]], baseline: Dict[str, Any]) -> List[str]:
    """从历史文章标题里抽高频主题词，作为检索词补充。"""
    pool = set(baseline.get("platform_relevance", {}).get("high_follow_topics", []) +
               baseline.get("title_formula", {}).get("brand_keywords", []))
    freq = {}
    for art in recent_articles[-40:]:  # 最近40篇
        title = art.get("title", "")
        for word in pool:
            if word.lower() in title.lower():
                freq[word] = freq.get(word, 0) + 1
    # 频次>=2 的主题词作为检索补充
    return [w for w, c in sorted(freq.items(), key=lambda x: -x[1]) if c >= 2][:6]


def find_undertouched_directions(recent_articles: List[Dict[str, Any]], baseline: Dict[str, Any]) -> List[str]:
    """找定位内"写得少但有潜力"的方向（写过1-2次，属于科技/商业/金融）。"""
    positioning = baseline.get("platform_relevance", {}).get("account_positioning", {})
    main_topics = positioning.get("main", ["科技", "商业", "金融"])
    related = baseline.get("platform_relevance", {}).get("high_follow_topics", [])
    freq = {}
    for art in recent_articles:
        title = art.get("title", "")
        for word in related:
            if word.lower() in title.lower():
                freq[word] = freq.get(word, 0) + 1
    # 写过1-2次的（有基础但未饱和）
    return [w for w, c in freq.items() if 1 <= c <= 2][:5]


# ============================================================
# 热点抓取（扩展源）
# ============================================================
def fetch_rss_items(query: str, raw_limit: int = 6, timeout: int = 10) -> List[Dict[str, Any]]:
    headers = {"User-Agent": "Mozilla/5.0"}
    context = ssl.create_default_context()
    results: List[Dict[str, Any]] = []
    encoded_query = urllib.parse.quote(query)

    for template in RSS_SOURCES:
        url = template.format(query=encoded_query)
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
                content = resp.read()
            root = ET.fromstring(content)
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub_date = parse_rss_datetime(item.findtext("pubDate"))
                description = (item.findtext("description") or "").strip()
                if not title or not link:
                    continue
                results.append({
                    "query": query, "title": title, "link": link,
                    "published_at": pub_date, "summary": description,
                    "source": urllib.parse.urlparse(link).netloc or "rss",
                })
                if len(results) >= raw_limit:
                    return results
        except Exception:
            continue
    return results


def fetch_tech_feeds(raw_limit: int = 8, timeout: int = 10) -> List[Dict[str, Any]]:
    """抓取科技媒体 RSS（36氪/虎嗅/极客公园）。"""
    headers = {"User-Agent": "Mozilla/5.0"}
    context = ssl.create_default_context()
    results: List[Dict[str, Any]] = []
    for feed_url in TECH_RSS_FEEDS:
        try:
            req = urllib.request.Request(feed_url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
                content = resp.read()
            root = ET.fromstring(content)
            for item in root.findall(".//item")[:raw_limit]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub_date = parse_rss_datetime(item.findtext("pubDate"))
                if not title or not link:
                    continue
                results.append({
                    "query": "科技媒体", "title": title, "link": link,
                    "published_at": pub_date, "summary": "",
                    "source": urllib.parse.urlparse(link).netloc or feed_url.split("/")[2],
                })
            if len(results) >= raw_limit:
                break
        except Exception:
            continue
    return results


def collect_news_items(queries: List[str], raw_limit_per_query: int = 6, include_tech: bool = True) -> List[Dict[str, Any]]:
    dedup: Dict[str, Dict[str, Any]] = {}
    for query in queries:
        for item in fetch_rss_items(query=query, raw_limit=raw_limit_per_query):
            key = f"{query}::{normalize_text(item['title'])}"
            if key not in dedup:
                dedup[key] = item
    if include_tech:
        for item in fetch_tech_feeds(raw_limit=8):
            key = f"tech::{normalize_text(item['title'])}"
            if key not in dedup:
                dedup[key] = item
    return list(dedup.values())


# ============================================================
# 主题词提取 + 热点过滤
# ============================================================
def extract_topics(text: str, baseline: Dict[str, Any]) -> List[str]:
    pool = baseline["platform_relevance"].get("high_follow_topics", []) + baseline["title_formula"].get("brand_keywords", [])
    norm = normalize_text(text)
    matches = [word for word in unique_keep_order(pool) if normalize_text(word) in norm]
    if "wechat" in norm and "微信" not in matches:
        matches.insert(0, "微信")
    if "ai" in norm and "AI" not in matches:
        matches.insert(0, "AI")
    if "agent" in norm and "Agent" not in matches:
        matches.append("Agent")
    return unique_keep_order(matches)


def build_positioning_pool(baseline: Dict[str, Any]) -> List[str]:
    positioning = baseline.get("platform_relevance", {}).get("account_positioning", {})
    return unique_keep_order(
        positioning.get("main", [])
        + baseline.get("platform_relevance", {}).get("high_follow_topics", [])
        + baseline.get("title_formula", {}).get("brand_keywords", [])
    )


def assess_news_item(item: Dict[str, Any], baseline: Dict[str, Any]) -> Dict[str, Any]:
    text = f"{item['query']} {item['title']} {item.get('summary', '')}"
    extracted_topics = extract_topics(text, baseline)
    query_terms = split_query_terms(item["query"])
    norm_text = normalize_text(text)
    query_hits = sum(1 for term in query_terms if normalize_text(term) in norm_text)
    utility_hits = sum(1 for word in UTILITY_KEYWORDS if normalize_text(word) in norm_text)
    positioning_hits = sum(1 for word in build_positioning_pool(baseline) if normalize_text(word) in norm_text)
    noise_hits = sum(1 for word in NOISE_KEYWORDS if normalize_text(word) in norm_text)

    relevance_score = query_hits * 18 + min(len(extracted_topics), 4) * 10 + min(utility_hits, 3) * 5 + min(positioning_hits, 3) * 4
    relevance_score -= min(noise_hits, 2) * 15

    reasons: List[str] = []
    if query_hits:
        reasons.append(f"命中检索词 {query_hits} 项")
    if extracted_topics:
        reasons.append(f"抽取到主题词：{', '.join(extracted_topics[:4])}")
    if utility_hits:
        reasons.append("带有方法/工具/决策等可转写信号")
    if noise_hits:
        reasons.append("包含疑似噪音词")

    keep = relevance_score >= 40 and noise_hits == 0

    annotated = dict(item)
    annotated.update({
        "extracted_topics": extracted_topics,
        "relevance_score": relevance_score,
        "keep": keep,
        "filter_reasons": reasons,
    })
    return annotated


def filter_news_items(news_items: List[Dict[str, Any]], baseline: Dict[str, Any], keep_per_query: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    dropped: List[Dict[str, Any]] = []
    for item in news_items:
        assessed = assess_news_item(item, baseline)
        if assessed["keep"]:
            grouped.setdefault(assessed["query"], []).append(assessed)
        else:
            assessed["drop_stage"] = "low_relevance"
            dropped.append(assessed)

    kept: List[Dict[str, Any]] = []
    for query, items in grouped.items():
        items.sort(key=lambda c: (-c["relevance_score"], -(c["published_at"].timestamp() if c.get("published_at") else 0)))
        for c in items[:keep_per_query]:
            c["drop_stage"] = "selected"
            kept.append(c)
        for c in items[keep_per_query:]:
            c["drop_stage"] = "overflow"
            dropped.append(c)
    return kept, dropped


# ============================================================
# 标题生成（8 种公式动态套用，每题生成 5-8 个备选）
# ============================================================
def generate_titles(topic_words: List[str], baseline: Dict[str, Any], count: int = 6) -> List[Tuple[str, str]]:
    """根据话题词动态生成标题候选，返回 (标题, 角度类型) 列表。"""
    brands = [b for b in baseline["title_formula"].get("brand_keywords", []) if any(b.lower() in t.lower() for t in topic_words)]
    brand = brands[0] if brands else (topic_words[0] if topic_words else "")
    topic = topic_words[0] if topic_words else "AI"
    topic2 = topic_words[1] if len(topic_words) > 1 else "微信"
    brand2 = brands[1] if len(brands) > 1 else (topic_words[1] if len(topic_words) > 1 else "百度")

    fill = {
        "brand": brand, "topic": topic, "topic2": topic2, "brand2": brand2,
        "old": "聊天工具", "field": "内容分发", "tool": topic, "task": topic, "action": f"做{topic}",
    }
    candidates: List[Tuple[str, str]] = []
    brand_eq_topic = (brand == topic)
    for angle, templates in TITLE_FORMULAS:
        for tpl in templates:
            # 如果 brand==topic 且模板同时引用 {brand} 和 {topic}，跳过（会产生"X这次的X"重复）
            if brand_eq_topic and "{brand}" in tpl and "{topic}" in tpl:
                continue
            try:
                title = tpl.format(**fill)
                # 通顺性检查：跳过连续重复字符（如"苹果苹果"）
                if re.search(r"(.)\1{2,}", title):
                    continue
                # 跳过 brand 空导致的怪标题
                if title.startswith("这次") or "这次的，" in title or "卷，" in title or "也扛不住了" in title:
                    continue
                # 跳过同一词重复出现 2 次以上的（如"微信...微信"）
                words_in_title = re.findall(r"[\u4e00-\u9fa5]{2,}", title)
                word_counts = {}
                skip = False
                for w in words_in_title:
                    word_counts[w] = word_counts.get(w, 0) + 1
                    if word_counts[w] >= 2 and len(w) >= 2:
                        skip = True
                        break
                if skip:
                    continue
                candidates.append((title, angle))
            except Exception:
                continue
    # 去重 + 截断
    seen = set()
    unique = []
    for title, angle in candidates:
        key = normalize_text(title)
        if key in seen:
            continue
        seen.add(key)
        unique.append((title, angle))
    return unique[:count]


# ============================================================
# 候选构建
# ============================================================
def score_title_options(titles: List[Tuple[str, str]], topics: List[str], day: str, baseline: Dict[str, Any], recent_articles: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    scored = []
    for title, angle in titles:
        result = dict(score_topic_idea(title=title, topics=topics, day=day, baseline=baseline, recent_articles=recent_articles))
        result.pop("baseline", None)
        result["angle_type"] = angle
        scored.append(result)
    scored.sort(key=lambda item: (item["prediction_pass"], item["total_score"], item["follow_score"], item["read_score"]), reverse=True)
    return scored


def build_writing_points(angle_type: str) -> List[str]:
    """根据角度类型返回写作要点。"""
    for key, points in ANGLE_WRITING_POINTS.items():
        if key in angle_type or angle_type in key:
            return points
    return ANGLE_WRITING_POINTS["机会/判断体"]


def build_candidate(
    source_type: str,
    topics: List[str],
    angle_type: str,
    source_title: str,
    source_url: str,
    source_query: str,
    source: str,
    published_at: Optional[datetime],
    why: str,
    baseline: Dict[str, Any],
    day: str,
    recent_articles: List[Dict[str, Any]],
    source_relevance: int = 50,
) -> Dict[str, Any]:
    """通用候选构建（热点型 + 价值型共用）。"""
    title_pairs = generate_titles(topics, baseline, count=8)
    scored_titles = score_title_options(title_pairs, topics, day, baseline, recent_articles)
    if not scored_titles:
        return None
    prediction = scored_titles[0]
    writing_points = build_writing_points(angle_type)
    candidate = {
        "source_type": source_type,
        "angle_type": angle_type,
        "source_title": source_title,
        "source_url": source_url,
        "source_query": source_query,
        "source": source,
        "published_at": published_at,
        "why": why,
        "angle": f"套用历史有效的「{angle_type}」结构，话题开放不限定。",
        "writing_points": writing_points,
        "prediction": prediction,
        "title_options": [(entry["title"], entry["angle_type"]) for entry in scored_titles],
        "prediction_variants": [
            {
                "title": entry["title"], "angle": entry["angle_type"],
                "read_score": entry["read_score"], "follow_score": entry["follow_score"],
                "interaction": entry["interaction"], "prediction_pass": entry["prediction_pass"],
            }
            for entry in scored_titles
        ],
        "source_relevance": source_relevance,
        "filter_reasons": [],
    }
    return candidate


def build_hot_candidate(item: Dict[str, Any], baseline: Dict[str, Any], day: str, recent_articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    topics = unique_keep_order(item.get("extracted_topics", []) + split_query_terms(item["query"]))[:5]
    if not topics:
        topics = ["AI", "科技"]
    # 热点型默认用机会/判断体（借势但要落到读者价值）
    angle_type = "机会/判断体"
    return build_candidate(
        source_type="热点型",
        topics=topics,
        angle_type=angle_type,
        source_title=item["title"],
        source_url=item["link"],
        source_query=item["query"],
        source=item.get("source", "rss"),
        published_at=item.get("published_at"),
        why=f"来自近期热点检索「{item['query']}」，相关度 {item['relevance_score']} 分。话题是新的，但套用历史有效的「{angle_type}」结构来写。",
        baseline=baseline,
        day=day,
        recent_articles=recent_articles,
        source_relevance=item["relevance_score"],
    )


def build_value_candidates(baseline: Dict[str, Any], day: str, recent_articles: List[Dict[str, Any]], hot_topics: List[str], request_context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """数据驱动的价值型选题：有效角度 × 开放话题。

    话题来源（不限死在微信AI/搜一搜）：
    1. 当前热点 RSS 抓到的（已去重的话题）
    2. 定位内"未写透"方向（历史写过1-2次但有潜力）
    3. 用户 --ask 里提到的方向
    角度来源：baseline.angle_patterns.effective_angles（历史验证有效的结构）
    """
    angle_patterns = baseline.get("angle_patterns", {})
    effective_angles = angle_patterns.get("effective_angles", [])
    if not effective_angles:
        effective_angles = [{"angle": "机会/判断体"}, {"angle": "方法论/科普体"}]

    # 话题池（开放）
    undertouched = find_undertouched_directions(recent_articles, baseline)
    ask_queries = (request_context or {}).get("queries", [])
    # 组合话题池：热点 + 未写透 + 用户补充
    topic_pool = []
    for ht in hot_topics[:6]:
        topic_pool.append(("热点话题", ht))
    for ut in undertouched:
        topic_pool.append(("未写透方向", ut))
    for aq in ask_queries:
        topic_pool.append(("用户指定", aq))
    # 定位内兜底方向（保证有候选）
    for main in baseline.get("platform_relevance", {}).get("account_positioning", {}).get("main", ["科技", "商业", "金融"]):
        topic_pool.append(("定位核心", main))

    candidates = []
    seen_topics = set()
    # 每个有效角度 × 每个话题 = 一个候选
    for angle_info in effective_angles[:4]:  # 取前4个有效角度
        angle_name = angle_info.get("angle", "机会/判断体")
        # 角度名映射到 ANGLE_WRITING_POINTS 的 key
        angle_key = angle_name
        for source_label, topic in topic_pool:
            topic_key = normalize_topic(topic)
            if topic_key in seen_topics:
                continue
            # 跳过最近30天写过3次以上的（饱和）
            recent_count = sum(1 for a in recent_articles[-30:] if topic.lower() in a.get("title", "").lower())
            if recent_count >= 3:
                continue
            seen_topics.add(topic_key)
            topics = [topic] + (["科技", "商业"] if topic not in ["科技", "商业"] else ["AI", "工具"])
            why = f"话题「{topic}」来自{source_label}，套用历史有效的「{angle_name}」角度（历史互动率 {angle_info.get('avg_engagement_rate', '?')}%/完读 {angle_info.get('avg_completion', '?')}%）。话题开放，不限定历史爆款方向。"
            if recent_count >= 1:
                why += f" 最近30天写过 {recent_count} 篇同主题，角度需差异化。"
            cand = build_candidate(
                source_type="价值型",
                topics=topics,
                angle_type=angle_key,
                source_title=f"{angle_name}×{topic}",
                source_url="",
                source_query=source_label,
                source="internal",
                published_at=None,
                why=why,
                baseline=baseline,
                day=day,
                recent_articles=recent_articles,
                source_relevance=70 + (10 if recent_count == 0 else 0),
            )
            if cand:
                candidates.append(cand)
    return candidates


# ============================================================
# 评分 + 去重 + 例外（放宽）
# ============================================================
def calc_request_bonus(candidate: Dict[str, Any], request_context: Optional[Dict[str, Any]]) -> Tuple[int, List[str]]:
    if not request_context:
        return 0, []
    bonus = 0
    reasons: List[str] = []
    profiles = set(request_context.get("profiles", []))
    request_queries = request_context.get("queries", [])
    candidate_topics = candidate["prediction"]["topics"]
    joined_topics = normalize_text(" ".join(candidate_topics + [candidate["angle_type"], candidate["source_type"]]))

    if request_queries:
        for query in request_queries:
            if any(normalize_text(token) in joined_topics for token in split_query_terms(query)):
                bonus += 8
                reasons.append(f"贴合你提到的方向：{query}")
                break
    if "practical" in profiles and any(word in candidate_topics for word in ["工具", "方法", "效率", "搜索"]):
        bonus += 8
        reasons.append("偏实用/方法型")
    if "evergreen" in profiles and candidate["source_type"] == "价值型":
        bonus += 8
        reasons.append("偏长期价值方向")
    if "hot" in profiles and candidate["source_type"] == "热点型":
        bonus += 8
        reasons.append("偏热点借势")
    if "workflow" in profiles and any(word in candidate_topics for word in ["效率", "工具", "方法", "Agent"]):
        bonus += 6
        reasons.append("偏工作流/效率")
    if "finance" in profiles and any(word in candidate_topics for word in ["商业", "理财", "金融", "订阅"]):
        bonus += 6
        reasons.append("偏商业/理财决策")
    if "wechat" in profiles and any(word in candidate_topics for word in ["微信", "搜一搜", "视频号"]):
        bonus += 6
        reasons.append("偏微信生态")
    if request_context.get("raw") and "不要热点" in request_context["raw"] and candidate["source_type"] == "热点型":
        bonus -= 10
    return bonus, reasons


def enrich_candidate(candidate: Dict[str, Any], recent_titles: List[str], request_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    prediction = candidate["prediction"]
    max_similarity = max((jaccard_char(prediction["title"], title) for title in recent_titles), default=0.0)
    novelty_penalty = 18 if max_similarity >= 0.6 else 10 if max_similarity >= 0.45 else 0
    freshness = recency_score(candidate.get("published_at")) if candidate["source_type"] == "热点型" else 10
    value_bonus = 8 if candidate["source_type"] == "价值型" else 0
    source_bonus = min(int(candidate.get("source_relevance", 0) / 6), 12)
    request_bonus, request_notes = calc_request_bonus(candidate, request_context)

    # 例外机制放宽：未通过预测，但满足以下任一即保留
    #   - 涨粉分>=45（话题相关度还行）
    #   - 阅读分>=60（标题+时机还行）
    #   - 互动潜力>=15（方法论/冲突类，长远利好）
    pred = prediction
    exception_keep = (not pred["prediction_pass"]) and (
        pred["follow_score"] >= 45 or pred["read_score"] >= 60 or pred["interaction"] >= 15
    ) and pred["positioning_status"].startswith("✅")

    rank_score = round(pred["total_score"] + freshness + value_bonus + source_bonus + request_bonus - novelty_penalty, 1)
    candidate.update({
        "max_similarity": round(max_similarity, 2),
        "novelty_penalty": novelty_penalty,
        "freshness": freshness,
        "value_bonus": value_bonus,
        "source_bonus": source_bonus,
        "request_bonus": request_bonus,
        "request_notes": request_notes,
        "exception_keep": exception_keep,
        "rank_score": rank_score,
    })
    return candidate


def dedupe_by_prediction_title(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best_by_title: Dict[str, Dict[str, Any]] = {}
    for item in items:
        key = normalize_text(item["prediction"]["title"])
        current = best_by_title.get(key)
        if current is None or item["rank_score"] > current["rank_score"]:
            best_by_title[key] = item
    return list(best_by_title.values())


def load_history_recommendations(output_dir: str) -> List[str]:
    """读历史推荐过的标题，用于去重。"""
    history_titles: List[str] = []
    if not os.path.exists(output_dir):
        return history_titles
    for fname in os.listdir(output_dir):
        if not fname.endswith(".json") or fname == "latest.json":
            continue
        try:
            with open(os.path.join(output_dir, fname), encoding="utf-8") as f:
                data = json.load(f)
            for cand in data.get("passed", []) + data.get("exceptions", []):
                pred = cand.get("prediction", {})
                if pred.get("title"):
                    history_titles.append(pred["title"])
        except Exception:
            continue
    return history_titles


def filter_already_recommended(candidates: List[Dict[str, Any]], history_titles: List[str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """过滤掉和历史上推荐过的标题高度相似的候选。"""
    if not history_titles:
        return candidates, []
    kept = []
    dropped = []
    for cand in candidates:
        title = cand["prediction"]["title"]
        max_sim = max((jaccard_char(title, ht) for ht in history_titles), default=0.0)
        if max_sim >= 0.7:
            cand["drop_reason"] = f"与历史推荐标题相似度 {max_sim:.2f}，去重"
            dropped.append(cand)
        else:
            kept.append(cand)
    return kept, dropped


def choose_candidates(candidates: List[Dict[str, Any]], count: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    passed = dedupe_by_prediction_title([c for c in candidates if c["prediction"]["prediction_pass"]])
    exceptions = dedupe_by_prediction_title([c for c in candidates if not c["prediction"]["prediction_pass"] and c["exception_keep"]])
    passed.sort(key=lambda c: (-c["rank_score"], -c["prediction"]["follow_score"], -c["prediction"]["read_score"]))
    exceptions.sort(key=lambda c: (-c["rank_score"], -c["prediction"]["follow_score"], -c["prediction"]["read_score"]))
    return passed[:count], exceptions[:max(2, count // 2)]


# ============================================================
# 输出渲染（精简为选题卡片，去掉假装的初稿）
# ============================================================
def ensure_output_dir(base: str, output_dir: Optional[str]) -> str:
    path = os.path.abspath(output_dir) if output_dir else os.path.join(base, "data", "topic_recommendations")
    os.makedirs(path, exist_ok=True)
    return path


def serialize_news_item(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "query": item["query"], "title": item["title"], "link": item["link"],
        "published_at": fmt_dt(item.get("published_at")), "source": item.get("source", "rss"),
        "relevance_score": item.get("relevance_score"), "keep": item.get("keep"),
        "filter_reasons": item.get("filter_reasons", []), "drop_stage": item.get("drop_stage", ""),
    }


def serialize_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    prediction = candidate["prediction"]
    return {
        "source_type": candidate["source_type"],
        "angle_type": candidate.get("angle_type", ""),
        "source_title": candidate["source_title"],
        "source_url": candidate["source_url"],
        "source_query": candidate["source_query"],
        "source": candidate["source"],
        "published_at": fmt_dt(candidate.get("published_at")),
        "why": candidate["why"],
        "angle": candidate["angle"],
        "writing_points": candidate["writing_points"],
        "title_options": candidate["title_options"],
        "source_relevance": candidate.get("source_relevance"),
        "rank_score": candidate.get("rank_score"),
        "max_similarity": candidate.get("max_similarity"),
        "request_notes": candidate.get("request_notes", []),
        "prediction": {
            "title": prediction["title"],
            "topics": prediction["topics"],
            "read_score": prediction["read_score"],
            "follow_score": prediction["follow_score"],
            "interaction": prediction["interaction"],
            "total_score": prediction["total_score"],
            "verdict": prediction["verdict"],
            "reason": prediction["reason"],
            "prediction_pass": prediction["prediction_pass"],
            "positioning_status": prediction["positioning_status"],
            "saturation_penalty": prediction.get("saturation_penalty", 0),
            "saturation_notes": prediction.get("saturation_notes", []),
            "suggestions": prediction["suggestions"],
        },
    }


def save_outputs(output_dir: str, markdown: str, payload: Dict[str, Any]) -> Dict[str, str]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = os.path.join(output_dir, f"topic_recommendations_{stamp}.md")
    json_path = os.path.join(output_dir, f"topic_recommendations_{stamp}.json")
    latest_md_path = os.path.join(output_dir, "latest.md")
    latest_json_path = os.path.join(output_dir, "latest.json")
    for path, content in [(md_path, markdown), (latest_md_path, markdown)]:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    for path in [json_path, latest_json_path]:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    return {"md": md_path, "json": json_path, "latest_md": latest_md_path, "latest_json": latest_json_path}


def render_candidate_card(candidate: Dict[str, Any], idx: int) -> List[str]:
    """精简的选题卡片输出。"""
    prediction = candidate["prediction"]
    lines = []
    lines.append(f"### {idx}. {prediction['title']}")
    lines.append(f"- 类型: {candidate['source_type']}（{candidate.get('angle_type', '')}）")
    if candidate["source_type"] == "热点型":
        lines.append(f"- 热点来源: {candidate['source_title']} ({candidate['source']}, {fmt_dt(candidate.get('published_at'))})")
        if candidate["source_url"]:
            lines.append(f"- 来源链接: {candidate['source_url']}")
    else:
        lines.append(f"- 选题来源: {candidate['source_query']}")
    lines.append(f"- 主题词: {', '.join(prediction['topics'])}")
    lines.append(f"- 推荐理由: {candidate['why']}")
    lines.append(f"- 写作角度: {candidate['angle']}")
    lines.append(f"- 爆款预测: 阅读 {prediction['read_score']}/100，涨粉 {prediction['follow_score']}/100，互动 {prediction['interaction']}/20，结论 {prediction['verdict']}")
    if prediction.get("saturation_penalty", 0) > 0:
        lines.append(f"- ⚠️ 饱和度提醒: {'；'.join(prediction.get('saturation_notes', []))}")
    if candidate.get("request_notes"):
        lines.append(f"- 为什么适合你这次的要求: {'；'.join(candidate['request_notes'])}")
    if candidate["novelty_penalty"]:
        lines.append(f"- 注意: 和近期标题相似度较高（{candidate['max_similarity']}），建议换一个切口。")

    # 备选标题（5-8个，覆盖不同公式）
    alt_titles = candidate.get("title_options", [])
    if len(alt_titles) > 1:
        lines.append("- 备选标题（覆盖不同公式）:")
        for title, angle in alt_titles[1:6]:
            lines.append(f"  - [{angle}] {title}")

    lines.append("- 写作要点:")
    for point in candidate["writing_points"]:
        lines.append(f"  - {point}")

    # 素材线索（精简，不假装生成初稿）
    lines.append("- 素材线索:")
    lines.append(f"  - 补 1 个你自己的真实观察或使用场景，避免二手整理。")
    lines.append(f"  - 准备 1 个反例或边界条件，增强可信度。")
    lines.append(f"  - 围绕 {', '.join(prediction['topics'][:3])} 至少准备 2 个具体例子。")
    if candidate["source_type"] == "热点型":
        lines.append("  - 保留热点原始链接，开头只引用 1 句核心事实，不要整段复述。")

    lines.append("- 发文提醒:")
    lines.append(f"  - 优先按 {prediction.get('day', '周二')} 的阅读规律安排发布。")
    lines.append("  - 开头前三句就给判断，不要先铺背景。")
    lines.append("  - 文末留一个可回答的问题，争取留言与收藏。")

    if not prediction["prediction_pass"]:
        lines.append("- ⚠️ 备注: 未通过爆款预测（" + prediction.get("verdict", "") + "），但因角度有效/互动潜力高/定位匹配，建议保留观察。")
    lines.append("")
    return lines


def render_output(
    base: str, queries: List[str], passed: List[Dict[str, Any]], exceptions: List[Dict[str, Any]],
    raw_news: List[Dict[str, Any]], filtered_news: List[Dict[str, Any]], dropped_news: List[Dict[str, Any]],
    history_dropped: List[Dict[str, Any]], output_dir: Optional[str], saved_paths: Optional[Dict[str, str]],
    request_context: Optional[Dict[str, Any]], effective_angles: List[Dict[str, Any]],
) -> str:
    lines = []
    lines.append("# 选题推荐结果（v2 数据驱动）")
    lines.append("")
    lines.append(f"- 工作空间: `{base}`")
    lines.append(f"- 热点检索词: {', '.join(queries)}")
    lines.append(f"- 热点原始条目: {len(raw_news)}（含科技媒体 RSS）")
    lines.append(f"- 过滤后保留: {len(filtered_news)}")
    lines.append(f"- 过滤掉的疑似低相关/噪音条目: {len(dropped_news)}")
    if history_dropped:
        lines.append(f"- 历史推荐去重剔除: {len(history_dropped)}")
    if effective_angles:
        lines.append(f"- 本次套用的有效角度（从历史数据学）: {', '.join(a['angle']+'('+str(a.get('avg_engagement_rate','?'))+'%)' for a in effective_angles[:4])}")
    if request_context and request_context.get("raw"):
        lines.append(f"- 对话请求: {request_context['raw']}")
        if request_context.get("profiles"):
            lines.append(f"- 偏好解析: {', '.join(request_context['profiles'])}")
    if output_dir:
        lines.append(f"- 输出目录: `{output_dir}`")
    if saved_paths:
        lines.append(f"- Markdown: `{saved_paths['md']}`")
        lines.append(f"- JSON: `{saved_paths['json']}`")
    lines.append("")

    if dropped_news:
        lines.append("## 热点过滤说明")
        lines.append("以下条目未进入正式候选：相关度不足或含噪音词。")
        lines.append("")
        for item in dropped_news[:6]:
            stage = item.get("drop_stage", "")
            stage_text = "相关度不足/噪音" if stage == "low_relevance" else "名额外淘汰" if stage == "overflow" else "未入选"
            lines.append(f"- {item['title']}（{item['query']}，相关度 {item.get('relevance_score','?')}，状态：{stage_text}，原因：{'；'.join(item.get('filter_reasons', [])) or '无'}）")
        lines.append("")

    def render_section(title: str, items: List[Dict[str, Any]], note: str) -> None:
        lines.append(f"## {title}")
        lines.append(note)
        lines.append("")
        if not items:
            lines.append("暂无。")
            lines.append("")
            return
        for idx, candidate in enumerate(items, 1):
            lines.extend(render_candidate_card(candidate, idx))

    render_section("通过爆款预测器的选题", passed, "优先输出通过预测的候选，适合直接进入提纲或写作。")
    render_section("未通过预测但值得保留", exceptions, "这些题未达强推荐线，但角度有效/互动潜力高/定位匹配，建议保留观察（已备注未通过原因）。")
    return "\n".join(lines).strip() + "\n"


# ============================================================
# main
# ============================================================
def main() -> int:
    configure_stdout()
    root = find_workspace_root(os.path.dirname(os.path.abspath(__file__)))

    ap = argparse.ArgumentParser(description="选题推荐器 v2（数据驱动）")
    ap.add_argument("workspace", nargs="?", help="工作空间目录，可省略")
    ap.add_argument("--ask", help="自然语言需求，例如：给我推荐3个偏实用的选题，下周二发")
    ap.add_argument("--queries", help="热点检索词，逗号分隔")
    ap.add_argument("--count", type=int, help="输出通过预测的选题数量")
    ap.add_argument("--day", help="计划发文星期，默认周二")
    ap.add_argument("--news-per-query", type=int, help="每个检索词最终保留的热点数量")
    ap.add_argument("--offline", action="store_true", help="仅基于历史数据生成价值型选题（不抓热点）")
    ap.add_argument("--output-dir", help="输出目录，默认写入 data/topic_recommendations")
    ap.add_argument("--json-out", help="额外再写一份结构化 JSON 到指定路径")
    ap.add_argument("--no-save", action="store_true", help="只打印，不落盘")
    args = ap.parse_args()

    request_context = parse_ask_request(args.ask or "")
    base = os.path.abspath(args.workspace or os.environ.get("WXPUB_DIR", root))
    baseline = load_baseline(base)
    recent_articles = load_recent_articles(base)
    recent_titles = [article["title"] for article in recent_articles[-15:]]

    # 动态检索词：默认词 + 历史高频词 + 用户补充
    history_topics = extract_history_topics(recent_articles, baseline)
    default_queries = split_topics(args.queries) if args.queries else (request_context.get("queries") or DEFAULT_QUERIES)
    queries = unique_keep_order(default_queries + history_topics)

    count = args.count or request_context.get("count") or 6
    day = args.day or request_context.get("day") or "周二"
    news_per_query = args.news_per_query or 2
    offline = args.offline or request_context.get("offline", False)

    raw_news = [] if offline else collect_news_items(queries, raw_limit_per_query=max(news_per_query * 4, 6), include_tech=True)
    filtered_news, dropped_news = filter_news_items(raw_news, baseline, keep_per_query=news_per_query) if raw_news else ([], [])

    # 热点话题（给价值型选题做话题池）
    hot_topics = unique_keep_order([t for item in filtered_news for t in item.get("extracted_topics", [])])

    hot_candidates = [build_hot_candidate(item, baseline, day, recent_articles) for item in filtered_news]
    hot_candidates = [c for c in hot_candidates if c]
    value_candidates = build_value_candidates(baseline, day, recent_articles, hot_topics, request_context)

    all_candidates = hot_candidates + value_candidates
    enriched = [enrich_candidate(c, recent_titles, request_context) for c in all_candidates]

    # 历史推荐去重
    output_dir_for_history = None if args.no_save else ensure_output_dir(base, args.output_dir)
    history_titles = load_history_recommendations(output_dir_for_history) if output_dir_for_history else []
    if history_titles:
        enriched, history_dropped = filter_already_recommended(enriched, history_titles)
    else:
        history_dropped = []

    passed, exceptions = choose_candidates(enriched, count)

    effective_angles = baseline.get("angle_patterns", {}).get("effective_angles", [])

    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "workspace": base,
        "version": "v2-data-driven",
        "request_context": request_context,
        "queries": queries,
        "day": day,
        "count": count,
        "effective_angles": effective_angles[:4],
        "output_dir": output_dir_for_history,
        "raw_news": [serialize_news_item(item) for item in raw_news],
        "filtered_news": [serialize_news_item(item) for item in filtered_news],
        "dropped_news": [serialize_news_item(item) for item in dropped_news],
        "history_dropped": [{"title": c["prediction"]["title"], "drop_reason": c.get("drop_reason", "")} for c in history_dropped],
        "passed": [serialize_candidate(item) for item in passed],
        "exceptions": [serialize_candidate(item) for item in exceptions],
    }

    saved_paths = None
    markdown = render_output(base, queries, passed, exceptions, raw_news, filtered_news, dropped_news, history_dropped, output_dir_for_history, None, request_context, effective_angles)

    if output_dir_for_history:
        saved_paths = save_outputs(output_dir_for_history, markdown, payload)
        payload["output_files"] = saved_paths
        markdown = render_output(base, queries, passed, exceptions, raw_news, filtered_news, dropped_news, history_dropped, output_dir_for_history, saved_paths, request_context, effective_angles)
        with open(saved_paths["md"], "w", encoding="utf-8") as f:
            f.write(markdown)
        with open(saved_paths["latest_md"], "w", encoding="utf-8") as f:
            f.write(markdown)
        with open(saved_paths["json"], "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        with open(saved_paths["latest_json"], "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    if args.json_out:
        json_out = os.path.abspath(args.json_out)
        os.makedirs(os.path.dirname(json_out), exist_ok=True)
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

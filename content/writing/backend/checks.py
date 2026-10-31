"""本地快速自检：在把稿子交给「质量检查 Prompt」之前，先用规则扫一遍明显的问题。

只做提示，不改稿；规则对应写作原则里的「不要 AI 腔」「趋势判断保留边界」「事实不确定不要写死」。
命中不等于一定要改，比如引用别人的原话、故意的排比，判断仍然在作者手里。
"""

import re

from .articles import count_chars

# (短语, 说明)。短语支持正则
AI_PHRASES = [
    (r"值得注意的是|需要指出的是|不难发现|不可否认", "报告腔的过渡语，删掉通常更自然"),
    (r"总而言之|综上所述|总的来说|总之，", "收尾套话，结尾直接落到判断或动作上"),
    (r"在当今|在这个.{1,12}的时代|随着.{1,16}的(?:发展|普及|到来)", "万能开头，换成一个具体场景或事实"),
    (r"赋能|抓手|闭环|底层逻辑|顶层设计|颗粒度|打法|心智|范式|重塑|助力|全方位|多维度|深度融合", "咨询/白皮书词汇，换成说人话的表达"),
    (r"让我们|一起来看看|接下来我们", "主持人腔，观点文不需要带读者“出发”"),
    (r"这不仅(?:仅)?是.{1,20}更是", "“不仅是…更是…”是典型 AI 句式"),
    (r"毋庸置疑|显而易见|众所周知", "替读者下结论，容易显得空"),
    (r"首先.{0,200}其次.{0,200}(?:最后|再次)", "首先/其次/最后的流水账结构，考虑用小标题或自然过渡"),
]
ABSOLUTE = (r"一定|必然|必将|绝对|毫无疑问|永远|彻底改变|所有人|每个人都|唯一的|100%|注定|从来没有|没有任何|完全不",
            "绝对化表述：趋势判断最好留边界（可能、大概率、至少在…范围内）")
FACT_SIGNALS = [
    (r"\d+(?:\.\d+)?\s*(?:%|％|亿|万|千|百万|美元|元|倍|个百分点)", "具体数字"),
    (r"(?:19|20)\d{2}\s*年|\d{1,2}\s*月\s*\d{1,2}\s*日", "具体时间"),
    (r"据.{0,12}(?:报道|统计|数据)|数据显示|研究(?:表明|显示|发现)|报告(?:显示|指出)|调查显示|官方(?:称|表示|宣布)", "引用来源"),
    (r"发布了|宣布|推出了|上线了|收购|裁员|财报", "公司动态"),
]
LONG_SENTENCE = 90
LONG_PARAGRAPH = 320
DASH_PER_K = 3  # 每千字超过这么多个破折号就提示


def _paragraphs(text):
    return [p for p in re.split(r"\n\s*\n|\n", text) if p.strip()]


def _sentences(par):
    return [s for s in re.split(r"(?<=[。！？!?；;])", par) if s.strip()]


def _excerpt(par, start, end, pad=18):
    a, b = max(0, start - pad), min(len(par), end + pad)
    return ("…" if a else "") + par[a:start] + "【" + par[start:end] + "】" + par[end:b] + ("…" if b < len(par) else "")


def check(text: str, title: str = "") -> dict:
    pars = _paragraphs(text)
    issues = []

    def add(kind, i, par, m, note):
        issues.append({"kind": kind, "para": i + 1, "text": m.group(0)[:40], "excerpt": _excerpt(par, m.start(), m.end()),
                       "note": note})

    fact_lines = []
    for i, par in enumerate(pars):
        if par.lstrip().startswith(("#", ">")) and len(par) < 60:
            continue
        for pat, note in AI_PHRASES:
            for m in re.finditer(pat, par):
                add("AI 腔", i, par, m, note)
        for m in re.finditer(ABSOLUTE[0], par):
            add("绝对化", i, par, m, ABSOLUTE[1])
        for s in _sentences(par):
            hits = [label for pat, label in FACT_SIGNALS if re.search(pat, s)]
            if hits:
                fact_lines.append({"para": i + 1, "sentence": s.strip()[:160], "signals": hits})
            if count_chars(s) > LONG_SENTENCE:
                issues.append({"kind": "长句", "para": i + 1, "text": f"{count_chars(s)} 字", "excerpt": s.strip()[:80] + "…",
                               "note": f"一句超过 {LONG_SENTENCE} 字，读者容易断气，考虑拆开"})
        if count_chars(par) > LONG_PARAGRAPH:
            issues.append({"kind": "长段", "para": i + 1, "text": f"{count_chars(par)} 字", "excerpt": par.strip()[:60] + "…",
                           "note": f"一段超过 {LONG_PARAGRAPH} 字，手机上是一整屏，推荐流读者容易划走"})
        sents = [s.strip() for s in _sentences(par)]
        for j in range(len(sents) - 2):
            heads = {s[:2] for s in sents[j:j + 3]}
            if len(heads) == 1 and len(sents[j]) > 4:
                issues.append({"kind": "排比", "para": i + 1, "text": sents[j][:2], "excerpt": "".join(sents[j:j + 3])[:80] + "…",
                               "note": "连续三句同样开头，刻意排比容易显得像 AI，留一处就够"})
                break

    chars = count_chars(text)
    dashes = text.count("——")
    if chars and dashes / chars * 1000 > DASH_PER_K and dashes >= 3:
        issues.append({"kind": "AI 腔", "para": 0, "text": f"{dashes} 个破折号", "excerpt": "",
                       "note": f"破折号偏多（每千字 {dashes / chars * 1000:.1f} 个），AI 稿常见，换成句号或逗号"})
    exclaims = len(re.findall(r"[！!]", text))
    if exclaims >= 4:
        issues.append({"kind": "AI 腔", "para": 0, "text": f"{exclaims} 个感叹号", "excerpt": "",
                       "note": "感叹号偏多，观点文用判断本身的力度，不靠标点"})

    title_notes = []
    if title:
        n = len(title)
        if n > 30:
            title_notes.append(f"标题 {n} 字，订阅号消息列表里会被截断（大约 20 字以内能完整显示）")
        if n < 6:
            title_notes.append("标题偏短，信息量可能不够")

    kinds = {}
    for it in issues:
        kinds[it["kind"]] = kinds.get(it["kind"], 0) + 1
    return {
        "stats": {"chars": chars, "paragraphs": len(pars), "minutes": round(chars / 400, 1) if chars else 0,
                  "avg_paragraph": round(chars / len(pars)) if pars else 0, "dashes": dashes},
        "summary": kinds,
        "issues": issues,
        "facts": fact_lines,
        "title_notes": title_notes,
    }


def render_text(result: dict) -> str:
    st = result["stats"]
    lines = [f"字数 {st['chars']} · {st['paragraphs']} 段 · 约 {st['minutes']} 分钟读完"]
    for note in result["title_notes"]:
        lines.append(f"标题：{note}")
    if not result["issues"]:
        lines.append("没有发现规则能扫到的问题。")
    for it in result["issues"]:
        where = f"第 {it['para']} 段" if it["para"] else "全文"
        lines.append(f"[{it['kind']}] {where}：{it['excerpt'] or it['text']}\n    → {it['note']}")
    if result["facts"]:
        lines.append(f"\n需要查证的句子（{len(result['facts'])} 句）：")
        for f in result["facts"]:
            lines.append(f"  第 {f['para']} 段 [{'/'.join(f['signals'])}] {f['sentence']}")
    return "\n".join(lines)

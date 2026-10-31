"""读取 prompts/*.md，把主题、想法、正文、修改意见填进去，得到可以直接粘贴给 AI 的完整 Prompt。

prompts/ 下的 Markdown 是唯一来源：改 Prompt 只改那里，这里只负责「填空」。
"""

import re

from .config import PROMPTS_DIR, STAGE, STAGES

FEEDBACK_KEYS = ["保留", "删除", "加强", "弱化", "需要改得更准确的地方", "需要更像我表达的地方"]


def _parse(path):
    text = path.read_text(encoding="utf-8")
    m = re.search(r"```text\n(.*?)```", text, re.S)
    scene = re.search(r"## 适用场景\s*\n(.*?)\n## ", text, re.S)
    return {"template": (m.group(1) if m else text).strip(), "scene": scene.group(1).strip() if scene else ""}


def list_prompts():
    out = []
    for s in STAGES:
        p = PROMPTS_DIR / s["file"]
        item = dict(s, exists=p.exists())
        if p.exists():
            item.update(_parse(p))
        out.append(item)
    return out


def _fill_line(text, label, value, block=False):
    """把模板里单独一行的「label：」填上内容。block=True 时内容另起一行。"""
    if not value or not value.strip():
        return text
    value = value.strip()
    pat = re.compile(rf"^(\s*(?:\d+\.\s*)?){re.escape(label)}：[ \t]*$", re.M)
    sep = "\n" if block else ""
    return pat.sub(lambda m: f"{m.group(1)}{label}：{sep}{value}", text, count=1)


def build(stage, topic="", ideas="", article="", feedback=None, notes="") -> str:
    """feedback 可以是 {保留: ..., 删除: ..., free: 自然语言意见}。"""
    s = STAGE.get(stage)
    if s is None:
        raise ValueError(f"没有这个阶段：{stage}")
    path = PROMPTS_DIR / s["file"]
    if not path.exists():
        raise FileNotFoundError(f"缺少 prompts/{s['file']}")
    text = _parse(path)["template"]
    text = _fill_line(text, "主题", topic)
    text = _fill_line(text, "我的想法", ideas, block=True)
    if stage == "revise":
        fb = feedback or {}
        for key in FEEDBACK_KEYS:
            text = _fill_line(text, key, fb.get(key, ""))
        free = (fb.get("free") or "").strip()
        if free:
            text = text.replace("\n\n请根据这些意见", f"\n\n补充意见：\n{free}\n\n请根据这些意见", 1)
    if notes and notes.strip():
        text += f"\n\n补充说明：\n{notes.strip()}"
    if "article" in s["needs"] and article and article.strip():
        label = "当前版本全文" if stage == "revise" else "文章全文"
        text += f"\n\n{label}：\n\n{article.strip()}"
    return text

"""标题评分：按文件路径加载公众号工作空间的 backend/prediction.py（纯标准库），读它的爆款预测基准。

两个项目保持独立：这里不导入公众号的其它模块，也不写它的任何文件。
"""

import importlib.util
import json

from .config import WXPUB_DIR

_PRED = WXPUB_DIR / "backend" / "prediction.py"
_BASELINE = WXPUB_DIR / "data" / "processed" / "hit_baseline.json"
_RECENT = WXPUB_DIR / "data" / "processed" / "recent_articles.json"
_module = None


def _load():
    global _module
    if _module is None:
        spec = importlib.util.spec_from_file_location("wxpub_prediction", _PRED)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _module = mod
    return _module


def available() -> dict:
    if not _PRED.exists():
        return {"ok": False, "reason": f"没找到公众号工作空间（{WXPUB_DIR}）"}
    if not _BASELINE.exists():
        return {"ok": False, "reason": "公众号工作空间还没有爆款预测基准：先在公众号分析里运行一次「分析」"}
    try:
        generated = json.loads(_BASELINE.read_text(encoding="utf-8")).get("generated_at")
    except (OSError, ValueError):
        generated = None
    return {"ok": True, "baseline_date": generated}


def score(titles, topics, day="周二", saturation=True) -> list:
    st = available()
    if not st["ok"]:
        raise FileNotFoundError(st["reason"])
    mod = _load()
    baseline = mod.load_baseline(str(WXPUB_DIR))
    recent = None
    if saturation and _RECENT.exists():
        recent = json.loads(_RECENT.read_text(encoding="utf-8"))
    topic_list = mod.split_topics(topics) if isinstance(topics, str) else list(topics)
    out = []
    for t in titles:
        t = t.strip()
        if not t:
            continue
        r = mod.score_topic_idea(t, topic_list, day, baseline, recent_articles=recent)
        out.append({k: r[k] for k in ("title", "read_score", "follow_score", "interaction", "total_score", "verdict",
                                      "prediction_pass", "positioning_status", "title_tags", "suggestions",
                                      "saturation_notes", "reason")})
    out.sort(key=lambda r: (r["prediction_pass"], r["total_score"]), reverse=True)
    return out

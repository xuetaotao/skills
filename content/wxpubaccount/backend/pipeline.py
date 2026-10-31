"""一次完整分析：分析窗口 → 合并详情 → HTML 报告 → 爆款预测基准。几毫秒到一两秒，同步执行。"""

import json
from datetime import datetime

from . import baseline, dataset, report
from .config import PROCESSED_DIR

STATE_PATH = PROCESSED_DIR / "_last_analysis.json"


def analyze(nl=None, since=None, until=None, window=None, all_=False, use_env=True) -> dict:
    win = dataset.build_window(nl=nl or None, since=since or None, until=until or None, window=window,
                               all_=all_, use_env=use_env)
    merged = dataset.parse_details()
    rep = report.write()
    b = baseline.write()
    result = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "window": win,
        "details": merged,
        "report": rep,
        "baseline": {"lift": b["title_formula"]["lift"], "tue_share_pct": b["weekday_pattern"]["tue_share_pct"],
                     "effective_angles": [a["angle"] for a in b["angle_patterns"]["effective_angles"]]},
    }
    STATE_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def last_analysis():
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def current_range() -> dict:
    """上次分析用的范围，换成 analyze() 的参数。口语短语和「最近 N 天」按今天重新计算。"""
    w = dataset.load_window()
    mode = w.get("mode") or "all"
    if mode.startswith("nl:"):
        return {"nl": mode[3:]}
    if mode == "custom":
        return {"since": w.get("since"), "until": w.get("until")}
    if mode.startswith("last") and mode.endswith("d") and mode[4:-1].isdigit():
        return {"window": int(mode[4:-1])}
    return {"all_": True}


def rerun_last() -> dict:
    return analyze(use_env=False, **current_range())

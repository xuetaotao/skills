"""yupen 数据源适配层

把 yupen 鱼盆模型当作库直接调用，跑一遍它的多 Agent pipeline，
再把内存里的分析结果（含 JSON 输出里没有的 market 与状态转变时间）
归一化成扁平的行情记录，供汇总表使用。
"""

import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
# stock/review -> ../../yupen/src
YUPEN_SRC = os.path.abspath(os.path.join(_HERE, "..", "..", "yupen", "src"))


def _ensure_yupen_on_path() -> None:
    if YUPEN_SRC not in sys.path:
        sys.path.insert(0, YUPEN_SRC)


def _fmt_date(value: Any) -> str:
    """把日期统一成 YYYY-MM-DD 字符串。"""
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    text = str(value)
    if "T" in text:
        text = text.split("T")[0]
    return text


def fetch_records(lookback_days: int = 60) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """运行 yupen pipeline，返回 (行情记录列表, 市场概览)。

    每条记录字段：
        name / market / code / price / change / ma20 / status /
        deviation(float) / deviation_str / status_change_date /
        data_date / changed_today
    数据采集失败的标的会被跳过。
    """
    _ensure_yupen_on_path()
    from orchestrator import MultiAgentOrchestrator  # type: ignore
    from config import INDICES  # type: ignore

    orchestrator = MultiAgentOrchestrator()
    orchestrator.run_workflow(indices=INDICES, lookback_days=lookback_days)

    context = orchestrator.context
    analyzed: Dict[str, Any] = context.get("analyzed_data", {})
    raw: Dict[str, Any] = context.get("raw_data", {})
    summary: Dict[str, Any] = context.get("summary", {})

    records: List[Dict[str, Any]] = []
    for name, analysis in analyzed.items():
        price = analysis.get("当前价格")
        if price is None:
            # 数据获取失败，不纳入汇总
            continue

        data_date = _fmt_date(analysis.get("数据日期", "N/A")) or "N/A"
        change_date = _fmt_date(analysis.get("状态开始日期"))

        records.append(
            {
                "name": name,
                "market": raw.get(name, {}).get("market"),
                "code": analysis.get("code"),
                "price": price,
                "change": analysis.get("涨跌幅"),
                "ma20": analysis.get("MA20"),
                "status": analysis.get("状态"),
                "deviation": analysis.get("偏离度"),
                "deviation_str": analysis.get("偏离度百分比", "N/A"),
                "status_change_date": change_date,
                "data_date": data_date,
                "changed_today": bool(change_date) and change_date == data_date,
            }
        )

    return records, summary


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

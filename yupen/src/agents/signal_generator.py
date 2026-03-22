"""
交易信号生成Agent
负责根据鱼盆模型生成交易信号
"""

from typing import Dict, Any, List
from datetime import datetime

from .base import BaseAgent


class SignalGeneratorAgent(BaseAgent):
    def __init__(self):
        super().__init__("SignalGeneratorAgent")

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.log_info("开始生成交易信号...")

        analyzed_data = context.get("analyzed_data", {})

        signals = {}
        for index_name, analysis in analyzed_data.items():
            signal = self._generate_signal(index_name, analysis)
            signals[index_name] = signal

        ranked_signals = self._rank_signals(signals)

        summary = self._generate_summary(ranked_signals)

        data_dates = [analysis.get("数据日期") for analysis in analyzed_data.values() if analysis.get("数据日期")]
        unique_dates = sorted(set(d for d in data_dates if d and d != 'N/A'), reverse=True)
        summary["数据日期"] = unique_dates[0] if unique_dates else datetime.now().strftime('%Y-%m-%d')

        result = {
            "status": "success",
            "signals": signals,
            "ranked_signals": ranked_signals,
            "summary": summary,
            "timestamp": datetime.now().isoformat()
        }

        self.log_info(f"信号生成完成，共生成 {len(signals)} 个交易信号")
        return result

    def _generate_signal(self, index_name: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        偏离度 = analysis.get("偏离度", 0) or 0
        状态 = analysis.get("状态", "NO")

        if 偏离度 >= 0.03:
            信号 = "🟢 强力买入"
            建议 = "积极持有/买入，趋势强劲"
        elif 偏离度 >= 0.01:
            信号 = "🟢 买入"
            建议 = "持有为主，可适当加仓"
        elif 偏离度 >= 0:
            信号 = "🟡 观望"
            建议 = "谨慎持有，等待明确信号"
        elif 偏离度 >= -0.01:
            信号 = "🟠 谨慎"
            建议 = "考虑减仓，控制风险"
        else:
            信号 = "🔴 卖出"
            建议 = "及时止损或减仓"

        if 状态 == "YES":
            操作建议 = "持有/买入"
        elif 状态 is None:
            操作建议 = "待修复"
            信号 = "❌ 数据获取失败"
            建议 = "数据获取失败，无法生成信号"
        else:
            操作建议 = "卖出/观望"

        return {
            "指数名称": index_name,
            "当前信号": 信号,
            "状态": 状态,
            "偏离度": 偏离度,
            "偏离度百分比": analysis.get("偏离度百分比", "0.00%"),
            "操作建议": 操作建议,
            "详细建议": 建议,
            "趋势强度": analysis.get("趋势强度", 0),
            "MA20": analysis.get("MA20", 0),
            "当前价格": analysis.get("当前价格", 0)
        }

    def _rank_signals(self, signals: Dict[str, Any]) -> List[Dict[str, Any]]:
        signal_list = []

        for name, signal in signals.items():
            偏离度 = signal.get("偏离度")
            if 偏离度 is None:
                偏离度 = -999

            signal_list.append({
                "指数名称": name,
                "信号": signal.get("当前信号", "❌ 数据获取失败"),
                "状态": signal.get("状态"),
                "偏离度": 偏离度,
                "操作建议": signal.get("操作建议", "待修复")
            })

        signal_list.sort(key=lambda x: x["偏离度"], reverse=True)

        for i, item in enumerate(signal_list):
            item["趋势强度排名"] = i + 1

        return signal_list

    def _generate_summary(self, ranked_signals: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not ranked_signals:
            return {"整体趋势": "无法判断", "市场情绪": "未知"}

        valid_signals = [s for s in ranked_signals if s["状态"] is not None]
        failed_signals = [s for s in ranked_signals if s["状态"] is None]

        yes_count = sum(1 for s in valid_signals if s["状态"] == "YES")
        no_count = len(valid_signals) - yes_count

        if valid_signals:
            avg_偏离度 = sum(s["偏离度"] for s in valid_signals if s["偏离度"] is not None) / len(valid_signals)
        else:
            avg_偏离度 = 0

        top_strength = valid_signals[0] if valid_signals else None

        total_count = len(valid_signals)
        if total_count == 0:
            整体趋势 = "无法判断"
            市场情绪 = "未知"
        elif yes_count >= total_count * 0.7:
            整体趋势 = "强势上涨"
            市场情绪 = "乐观"
        elif yes_count >= total_count * 0.5:
            整体趋势 = "震荡偏强"
            市场情绪 = "谨慎乐观"
        elif yes_count >= total_count * 0.3:
            整体趋势 = "震荡偏弱"
            市场情绪 = "谨慎"
        else:
            整体趋势 = "弱势下跌"
            市场情绪 = "悲观"

        return {
            "整体趋势": 整体趋势,
            "市场情绪": 市场情绪,
            "YES数量": yes_count,
            "NO数量": no_count,
            "平均偏离度": f"{avg_偏离度 * 100:.2f}%",
            "最强指数": top_strength["指数名称"] if top_strength and top_strength["偏离度"] != -999 else "无",
            "最强偏离度": f"{top_strength['偏离度'] * 100:.2f}%" if top_strength and top_strength["偏离度"] != -999 else "0.00%",
            "数据获取失败": len(failed_signals)
        }
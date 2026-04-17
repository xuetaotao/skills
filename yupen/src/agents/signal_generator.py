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

    # 不参与排名的 market 类型
    EXCLUDE_FROM_RANK = {"stock"}

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.log_info("开始生成交易信号...")

        analyzed_data = context.get("analyzed_data", {})
        raw_data = context.get("raw_data", {})

        signals = {}
        for index_name, analysis in analyzed_data.items():
            signal = self._generate_signal(index_name, analysis)
            signals[index_name] = signal

        ranked_signals = self._rank_signals(signals, raw_data)

        summary = self._generate_summary(ranked_signals)

        summary["简要解读"] = self._generate_brief_interpretation(summary, ranked_signals)

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

    def _rank_signals(self, signals: Dict[str, Any], raw_data: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        signal_list = []
        raw_data = raw_data or {}

        for name, signal in signals.items():
            market = raw_data.get(name, {}).get("market", "")
            偏离度 = signal.get("偏离度")
            if 偏离度 is None:
                偏离度 = -999

            signal_list.append({
                "指数名称": name,
                "信号": signal.get("当前信号", "❌ 数据获取失败"),
                "状态": signal.get("状态"),
                "偏离度": 偏离度,
                "操作建议": signal.get("操作建议", "待修复"),
                "market": market,
            })

        # 不参与排名的条目排到末尾，其余按偏离度降序
        signal_list.sort(
            key=lambda x: (x["market"] in self.EXCLUDE_FROM_RANK, -x["偏离度"])
        )

        rank = 1
        for item in signal_list:
            if item["market"] in self.EXCLUDE_FROM_RANK:
                item["趋势强度排名"] = "--"
            else:
                item["趋势强度排名"] = rank
                rank += 1

        return signal_list

    def _generate_summary(self, ranked_signals: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not ranked_signals:
            return {"整体趋势": "无法判断", "市场情绪": "未知"}

        # 个股不计入整体趋势统计
        ranked_for_summary = [s for s in ranked_signals if s.get("market") not in self.EXCLUDE_FROM_RANK]
        valid_signals = [s for s in ranked_for_summary if s["状态"] is not None]
        failed_signals = [s for s in ranked_for_summary if s["状态"] is None]

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

    def _generate_brief_interpretation(self, summary: Dict[str, Any], ranked_signals: List[Dict[str, Any]]) -> List[str]:
        suggestions: List[str] = []

        yes_count = summary.get("YES数量", 0)
        no_count = summary.get("NO数量", 0)
        total = yes_count + no_count

        ranked_ex = [s for s in ranked_signals if s.get("market") not in self.EXCLUDE_FROM_RANK]
        valid_signals = [s for s in ranked_ex if s.get("状态") is not None]
        yes_signals = [s for s in valid_signals if s.get("状态") == "YES"]
        no_signals = [s for s in valid_signals if s.get("状态") == "NO"]

        if total == 0:
            return ["数据不足，建议先修复数据源后再做交易决策。"]

        yes_ratio = yes_count / total

        if yes_ratio >= 0.7:
            suggestions.append("仓位建议：可保持偏高仓位，以持有和顺势加仓为主。")
        elif yes_ratio >= 0.5:
            suggestions.append("仓位建议：维持中性偏多仓位，优先持有强势标的，新增仓位分批进行。")
        elif yes_ratio >= 0.3:
            suggestions.append("仓位建议：控制在中低仓位，减小进攻性仓位，耐心等待更清晰信号。")
        else:
            suggestions.append("仓位建议：以防守为主，降低总体仓位，优先保留现金。")

        if yes_signals:
            leaders = "、".join([s["指数名称"] for s in yes_signals[:3]])
            suggestions.append(f"方向建议：重点跟踪强势指数 {leaders}，仅在回踩关键均线后考虑分批介入。")

        if no_signals:
            laggards = "、".join([s["指数名称"] for s in no_signals[:3]])
            suggestions.append(f"风控建议：对弱势指数 {laggards} 以减仓/观望为主，避免逆势补仓。")

        strong_deviation = [s for s in yes_signals if s.get("偏离度") is not None and s["偏离度"] > 0.03]
        if strong_deviation:
            names = "、".join([s["指数名称"] for s in strong_deviation[:3]])
            suggestions.append(f"节奏建议：{names} 已明显偏离均线，避免追高，优先等待回撤后的低风险位置。")

        oversold_signals = [s for s in no_signals if s.get("偏离度") is not None and s["偏离度"] < -0.1]
        if oversold_signals:
            names = "、".join([s["指数名称"] for s in oversold_signals[:3]])
            suggestions.append(f"交易纪律：{names} 如需博弈反弹，仅建议小仓位试错并设置明确止损。")

        failed_count = summary.get("数据获取失败", 0)
        if failed_count:
            suggestions.append(f"执行提醒：当前有 {failed_count} 个指数数据异常，重要操作前请先确认数据完整性。")

        return suggestions
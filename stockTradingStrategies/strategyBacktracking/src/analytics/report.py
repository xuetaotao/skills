"""
报告生成器
生成文本摘要和JSON格式报告
"""
import json
import os
from datetime import datetime

from src.config import OUTPUTS_DIR


def generate_report(backtest_result: dict, metrics: dict) -> str:
    """
    生成回测报告
    返回: 报告输出目录路径
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(OUTPUTS_DIR, f"backtest_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)

    # 1. 生成文本摘要
    summary = _generate_summary(backtest_result, metrics)
    summary_path = os.path.join(output_dir, "summary.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)

    # 2. 生成JSON报告
    json_data = {
        "timestamp": timestamp,
        "strategy": {
            "name": backtest_result.get("strategy_name", ""),
            "description": backtest_result.get("description", ""),
            "symbols": backtest_result.get("symbols", []),
            "start_date": backtest_result.get("start_date", ""),
            "end_date": backtest_result.get("end_date", ""),
            "initial_capital": backtest_result.get("initial_capital", 0),
            "final_assets": backtest_result.get("final_assets", 0),
        },
        "metrics": metrics,
        "nav_history": backtest_result.get("nav_history", []),
        "benchmark_nav": backtest_result.get("benchmark_nav", {}),
        "trades": backtest_result.get("trades", []),
        "strategy_rules": backtest_result.get("strategy_rules", {}),
    }
    json_path = os.path.join(output_dir, "report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2, default=str)

    return output_dir


def _generate_summary(result: dict, metrics: dict) -> str:
    """生成文本摘要"""
    lines = []
    lines.append("=" * 60)
    lines.append("  策略回测报告")
    lines.append("=" * 60)
    lines.append("")

    # 基本信息
    lines.append("【基本信息】")
    lines.append(f"  策略名称: {result.get('strategy_name', 'N/A')}")
    lines.append(f"  策略描述: {result.get('description', 'N/A')[:100]}")
    lines.append(f"  投资标的: {', '.join(result.get('symbols', []))}")
    lines.append(f"  回测区间: {result.get('start_date', '')} ~ {result.get('end_date', '')}")
    lines.append(f"  初始资金: ¥{result.get('initial_capital', 0):,.0f}")
    lines.append(f"  期末资产: ¥{result.get('final_assets', 0):,.2f}")
    lines.append("")

    # 核心指标
    lines.append("【核心绩效指标】")
    lines.append(f"  总收益率:     {metrics.get('total_return_pct', 'N/A')}")
    lines.append(f"  年化收益率:   {metrics.get('annual_return_pct', 'N/A')}")
    lines.append(f"  最大回撤:     {metrics.get('max_drawdown_pct', 'N/A')}")
    lines.append(f"  夏普比率:     {metrics.get('sharpe_ratio', 'N/A')}")
    lines.append(f"  索提诺比率:   {metrics.get('sortino_ratio', 'N/A')}")
    lines.append(f"  卡尔玛比率:   {metrics.get('calmar_ratio', 'N/A')}")
    lines.append(f"  年化波动率:   {metrics.get('annual_volatility_pct', 'N/A')}")
    lines.append(f"  Alpha:        {metrics.get('alpha', 'N/A')}")
    lines.append(f"  Beta:         {metrics.get('beta', 'N/A')}")
    lines.append("")

    # 交易统计
    lines.append("【交易统计】")
    lines.append(f"  总交易次数:   {metrics.get('total_trades', 0)}")
    lines.append(f"  买入次数:     {metrics.get('buy_trades', 0)}")
    lines.append(f"  卖出次数:     {metrics.get('sell_trades', 0)}")
    lines.append(f"  胜率:         {metrics.get('win_rate_pct', 'N/A')}")
    lines.append(f"  盈亏比:       {metrics.get('profit_loss_ratio', 'N/A')}")
    lines.append(f"  平均盈利:     ¥{metrics.get('avg_profit', 0):,.2f}")
    lines.append(f"  平均亏损:     ¥{metrics.get('avg_loss', 0):,.2f}")
    lines.append(f"  总交易成本:   ¥{metrics.get('total_commission', 0) + metrics.get('total_tax', 0):,.2f}")
    lines.append("")

    # 回撤详情
    if metrics.get("max_drawdown_start"):
        lines.append("【最大回撤区间】")
        lines.append(f"  起始日期: {metrics.get('max_drawdown_start', '')}")
        lines.append(f"  结束日期: {metrics.get('max_drawdown_end', '')}")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)

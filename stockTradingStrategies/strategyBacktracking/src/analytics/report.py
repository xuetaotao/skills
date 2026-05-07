"""
报告生成器
生成文本摘要和JSON格式报告，文件名含时间戳和策略概括
"""
import json
import os
import re
from datetime import datetime

from src.config import OUTPUTS_DIR


def _sanitize_name(name: str, max_len: int = 20) -> str:
    """将策略名转为安全的文件名片段"""
    # 去除特殊字符，保留中文/字母/数字
    name = re.sub(r'[\\/:*?"<>|]', '', name)
    name = name.strip().replace(' ', '_')
    if len(name) > max_len:
        name = name[:max_len]
    return name if name else "strategy"


def generate_report(backtest_result: dict, metrics: dict) -> str:
    """
    生成回测报告
    返回: 报告输出目录路径
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    strategy_name = backtest_result.get("strategy_name", "")
    strategy_slug = _sanitize_name(strategy_name)

    # 输出目录：backtest_20260507_002350_均线趋势/
    output_dir = os.path.join(OUTPUTS_DIR, f"backtest_{timestamp}_{strategy_slug}")
    os.makedirs(output_dir, exist_ok=True)

    # 文件名前缀：backtest_20260507_002350_均线趋势
    file_prefix = f"backtest_{timestamp}_{strategy_slug}"

    # 1. 生成文本摘要
    summary = _generate_summary(backtest_result, metrics)
    summary_path = os.path.join(output_dir, f"{file_prefix}_summary.txt")
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
    json_path = os.path.join(output_dir, f"{file_prefix}_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2, default=str)

    # 3. 生成 latest 快捷文件（参考 yupen）
    latest_summary = os.path.join(OUTPUTS_DIR, "latest_summary.txt")
    latest_json = os.path.join(OUTPUTS_DIR, "latest_report.json")
    with open(latest_summary, "w", encoding="utf-8") as f:
        f.write(summary)
    with open(latest_json, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2, default=str)

    # 4. 生成 index.html 跳转页
    index_html = os.path.join(OUTPUTS_DIR, "index.html")
    index_content = """<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="refresh" content="0; url=latest_report.html">
    <title>策略回测报告</title>
</head>
<body>
    <p>正在跳转到最新报告...</p>
    <p>如果没有自动跳转，请<a href="latest_report.html">点击这里</a></p>
</body>
</html>"""
    with open(index_html, "w", encoding="utf-8") as f:
        f.write(index_content)

    return output_dir


def get_file_prefix(output_dir: str) -> str:
    """从输出目录名中提取文件名前缀"""
    return os.path.basename(output_dir)


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

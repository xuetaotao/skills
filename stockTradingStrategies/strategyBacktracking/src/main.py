"""
CLI 入口
股票策略回测系统主程序
"""
import argparse
import json
import logging
import os
import sys

from src.config import OUTPUTS_DIR, BENCHMARK_INDICES
from src.data.fetcher import DataFetcher
from src.engine.backtester import Backtester
from src.strategy.models import StrategyRules
from src.llm.parser import StrategyParser
from src.analytics.metrics import calc_all_metrics
from src.analytics.report import generate_report
from src.visualization.chart import plot_all

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def interactive_mode():
    """交互式输入模式"""
    print()
    print("📊 股票策略回测系统")
    print("━" * 40)
    print()

    # 投资标的
    symbols_input = input("请输入投资标的（逗号分隔代码或名称）: ").strip()
    symbols = [s.strip() for s in symbols_input.split(",") if s.strip()]
    if not symbols:
        print("❌ 必须输入至少一个标的")
        return

    # 回测区间
    date_input = input("请输入回测时间区间（YYYY-MM-DD ~ YYYY-MM-DD）: ").strip()
    try:
        parts = date_input.replace("~", "-").replace("至", "-").split("-")
        parts = [p.strip() for p in parts if p.strip()]
        start_date = f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
        end_date = f"{parts[3]}-{parts[4].zfill(2)}-{parts[5].zfill(2)}"
    except (IndexError, ValueError):
        print("❌ 日期格式错误，使用默认 2022-01-01 ~ 2025-12-31")
        start_date = "2022-01-01"
        end_date = "2025-12-31"

    # 初始资金
    capital_input = input("请输入初始资金（默认100万）: ").strip()
    initial_capital = float(capital_input) if capital_input else 1000000

    # 对比基准
    print(f"\n可选基准: {', '.join(BENCHMARK_INDICES.keys())}")
    benchmark_input = input("请输入对比基准（逗号分隔，默认沪深300）: ").strip()
    if benchmark_input:
        benchmark_names = [b.strip() for b in benchmark_input.split(",")]
    else:
        benchmark_names = ["沪深300"]

    # 策略描述
    print("\n请描述你的交易策略（支持任意自然语言，输入空行结束）:")
    strategy_lines = []
    while True:
        line = input("> " if not strategy_lines else "  ")
        if not line.strip():
            break
        strategy_lines.append(line)
    strategy_description = "\n".join(strategy_lines)

    if not strategy_description.strip():
        print("❌ 必须输入策略描述")
        return

    # 解析策略
    print("\n🤖 正在解析策略...")
    parser = StrategyParser()
    rules = parser.parse(strategy_description, symbols, start_date, end_date)

    # 展示解析结果
    _display_parsed_rules(rules)

    confirm = input("\n   确认执行回测？(Y/n) ").strip().lower()
    if confirm == "n":
        print("已取消")
        return

    # 执行回测
    _run_backtest(symbols, rules, start_date, end_date,
                  initial_capital, benchmark_names)


def command_mode(args):
    """命令行参数模式"""
    # 读取策略文件
    rules = None
    if args.rules:
        with open(args.rules, "r", encoding="utf-8") as f:
            rules_data = json.load(f)
        rules = StrategyRules.from_dict(rules_data)
    elif args.strategy:
        # 自然语言策略
        parser = StrategyParser()
        rules = parser.parse(
            args.strategy,
            args.symbols.split(","),
            args.start,
            args.end,
        )
    else:
        print("❌ 请指定策略（--rules 或 --strategy）")
        return

    symbols = args.symbols.split(",") if args.symbols else []
    benchmarks = args.benchmarks.split(",") if args.benchmarks else ["沪深300"]

    _run_backtest(symbols, rules, args.start, args.end,
                  args.capital, benchmarks)


def _run_backtest(symbols: list, rules: StrategyRules,
                  start_date: str, end_date: str,
                  initial_capital: float, benchmark_names: list):
    """执行回测并输出结果"""
    print("\n📈 正在获取数据...")

    # 获取基准代码
    benchmark_codes = []
    for name in benchmark_names:
        if name in BENCHMARK_INDICES:
            benchmark_codes.append(name)
        else:
            print(f"  ⚠️ 未知基准: {name}")

    print("⚙️  正在回测...")

    try:
        backtester = Backtester(initial_capital)
        result = backtester.run(
            symbols=symbols,
            strategy_rules=rules,
            start_date=start_date,
            end_date=end_date,
            benchmarks=benchmark_codes,
        )
    except Exception as e:
        print(f"❌ 回测失败: {e}")
        logger.exception("回测异常")
        return

    # 计算指标
    print("📊 生成报告中...")
    metrics = calc_all_metrics(
        result["nav_history"],
        result["trades"],
        result["benchmark_nav"],
    )

    # 生成报告
    output_dir = generate_report(result, metrics)

    # 生成图表
    plot_all(
        result["nav_history"],
        result["benchmark_nav"],
        metrics,
        output_dir,
        rules.strategy_name,
    )

    # 输出结果摘要
    _display_results(metrics, output_dir)


def _display_parsed_rules(rules: StrategyRules):
    """展示解析后的策略规则"""
    print("\n✅ 策略解析完成：")
    print(f"   ├─ 策略名称: {rules.strategy_name}")

    for i, rule in enumerate(rules.entry_rules):
        conds = ", ".join(c.description for c in rule.conditions)
        print(f"   ├─ 入场条件 {i+1}: {conds}")

    for i, rule in enumerate(rules.exit_rules):
        conds = ", ".join(c.description for c in rule.conditions)
        sell_info = f"（卖出{rule.sell_ratio:.0%}）" if rule.sell_ratio < 1 else ""
        print(f"   ├─ 退出条件 {i+1}: {conds} {sell_info}")

    risk = rules.risk_rules
    risk_items = []
    if risk.stop_loss:
        risk_items.append(f"止损{risk.stop_loss:.0%}")
    if risk.take_profit:
        risk_items.append(f"止盈{risk.take_profit:.0%}")
    if risk.trailing_stop:
        risk_items.append(f"移动止损{risk.trailing_stop:.0%}")
    if risk_items:
        print(f"   ├─ 风控条件: {', '.join(risk_items)}")

    ps = rules.position_sizing
    print(f"   └─ 仓位管理: {ps.description or ps.method.value}")


def _display_results(metrics: dict, output_dir: str):
    """展示回测结果摘要"""
    print()
    print("━" * 50)
    print("  回测结果")
    print("━" * 50)
    print(f"  年化收益率:   {metrics.get('annual_return_pct', 'N/A')}")
    print(f"  最大回撤:     {metrics.get('max_drawdown_pct', 'N/A')}")
    print(f"  夏普比率:     {metrics.get('sharpe_ratio', 'N/A')}")
    print(f"  卡尔玛比率:   {metrics.get('calmar_ratio', 'N/A')}")
    print(f"  索提诺比率:   {metrics.get('sortino_ratio', 'N/A')}")
    print(f"  年化波动率:   {metrics.get('annual_volatility_pct', 'N/A')}")
    print(f"  Alpha:        {metrics.get('alpha', 'N/A')}")
    print(f"  Beta:         {metrics.get('beta', 'N/A')}")
    print(f"  胜率:         {metrics.get('win_rate_pct', 'N/A')}")
    print(f"  盈亏比:       {metrics.get('profit_loss_ratio', 'N/A')}")
    print(f"  总交易次数:   {metrics.get('total_trades', 0)}")
    print("━" * 50)
    print(f"\n📁 结果已保存至: {output_dir}")
    print("   ├── backtest_*_summary.txt      # 文本摘要")
    print("   ├── backtest_*_report.json       # 完整数据报告")
    print("   ├── backtest_*_equity_curve.png  # 收益曲线 + 回撤图")
    print("   └── backtest_*_monthly_heatmap.png  # 月度收益热力图")


def main():
    parser = argparse.ArgumentParser(
        description="📊 股票策略回测系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 交互模式
  python -m src.main

  # 命令行模式 - 使用自然语言策略
  python -m src.main --symbols "510300,510500" --start 2022-01-01 --end 2025-12-31 --strategy "收盘价上穿20日均线买入，下穿卖出"

  # 命令行模式 - 使用规则文件
  python -m src.main --symbols "510300" --start 2022-01-01 --end 2025-12-31 --rules my_strategy.json
        """,
    )

    parser.add_argument("--symbols", "-s", help="投资标的，逗号分隔")
    parser.add_argument("--start", default="2022-01-01", help="回测开始日期")
    parser.add_argument("--end", default="2025-12-31", help="回测结束日期")
    parser.add_argument("--capital", "-c", type=float, default=1000000, help="初始资金")
    parser.add_argument("--benchmarks", "-b", help="对比基准，逗号分隔")
    parser.add_argument("--rules", "-r", help="策略规则JSON文件路径")
    parser.add_argument("--strategy", help="自然语言策略描述")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志")
    parser.add_argument("--api-key", help="OpenAI API Key")
    parser.add_argument("--model", help="LLM 模型名称")
    parser.add_argument("--base-url", help="OpenAI 兼容 API Base URL")

    args = parser.parse_args()
    setup_logging(args.verbose)

    # 环境变量设置
    if args.api_key:
        os.environ["OPENAI_API_KEY"] = args.api_key
    if args.base_url:
        os.environ["OPENAI_BASE_URL"] = args.base_url

    # 确保输出目录存在
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    # 选择模式
    if args.symbols and (args.rules or args.strategy):
        command_mode(args)
    else:
        interactive_mode()


if __name__ == "__main__":
    main()

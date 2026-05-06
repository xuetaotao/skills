"""
回测引擎
核心回测循环：逐日遍历行情 → 策略生成信号 → 模拟成交 → 记录净值
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from src.data.fetcher import DataFetcher
from src.engine.portfolio import Portfolio
from src.strategy.indicators import IndicatorCalculator
from src.strategy.models import StrategyRules, Signal, Action

logger = logging.getLogger(__name__)


class Backtester:
    """回测引擎"""

    def __init__(self, initial_capital: float = 1000000):
        self.initial_capital = initial_capital
        self.fetcher = DataFetcher()
        self.indicator_calc = IndicatorCalculator()

    def run(self, symbols: List[str], strategy_rules: StrategyRules,
            start_date: str, end_date: str,
            benchmarks: List[str] = None) -> dict:
        """
        执行回测

        Args:
            symbols: 标的代码/名称列表
            strategy_rules: LLM解析后的策略规则
            start_date: 回测开始日期 YYYY-MM-DD
            end_date: 回测结束日期 YYYY-MM-DD
            benchmarks: 对比基准名称列表

        Returns:
            回测结果字典
        """
        logger.info(f"开始回测: 标的={symbols}, 区间={start_date}~{end_date}")
        logger.info(f"策略: {strategy_rules.strategy_name}")

        # 1. 获取数据
        logger.info("正在获取行情数据...")
        data_dict = {}
        symbol_info = {}

        for symbol in symbols:
            try:
                df = self.fetcher.fetch(symbol, start_date, end_date)
                info = self.fetcher.resolve_symbol(symbol)
                data_dict[info["code"]] = df
                symbol_info[info["code"]] = {
                    "code": info["code"],
                    "market": info["market"],
                    "name": info.get("name", symbol),
                    "original_symbol": symbol,
                }
            except Exception as e:
                logger.error(f"获取 {symbol} 数据失败: {e}")

        if not data_dict:
            raise ValueError("所有标的数据获取失败，无法回测")

        # 2. 计算技术指标
        logger.info("正在计算技术指标...")
        indicators_needed = strategy_rules.indicators_needed
        # 默认加上MA20用于基础判断
        if not any("MA" in ind for ind in indicators_needed):
            indicators_needed.append("MA(20)")

        for code, df in data_dict.items():
            data_dict[code] = self.indicator_calc.compute_all(df, indicators_needed)

        # 3. 获取基准数据
        logger.info("正在获取基准数据...")
        benchmark_data = {}
        if benchmarks:
            for bm_name in benchmarks:
                try:
                    bm_df = self.fetcher.fetch(bm_name, start_date, end_date)
                    benchmark_data[bm_name] = bm_df
                except Exception as e:
                    logger.warning(f"获取基准 {bm_name} 数据失败: {e}")

        # 4. 执行回测
        logger.info("正在执行回测...")
        portfolio = Portfolio(self.initial_capital)
        daily_records = []

        # 构建统一交易日历（取所有标的的交集）
        all_dates = None
        for code, df in data_dict.items():
            dates = set(df['date'].dt.strftime('%Y-%m-%d').tolist())
            if all_dates is None:
                all_dates = dates
            else:
                all_dates = all_dates & dates

        if not all_dates:
            raise ValueError("标的之间没有共同的交易日")

        trading_dates = sorted(all_dates)

        # 导入规则引擎
        from src.strategy.rule_engine import RuleEngine
        rule_engine = RuleEngine(strategy_rules)

        # 按标的预计算数据索引
        data_indexed = {}
        for code, df in data_dict.items():
            df_indexed = df.set_index('date')
            data_indexed[code] = df_indexed

        # 逐日回测
        prev_date = None
        for date_str in trading_dates:
            date = pd.Timestamp(date_str)

            # 获取当日行情
            daily_prices = {}
            daily_bars = {}

            for code, df_idx in data_indexed.items():
                if date in df_idx.index:
                    bar = df_idx.loc[date]
                    if isinstance(bar, pd.DataFrame):
                        bar = bar.iloc[0]
                    daily_prices[code] = float(bar['close'])
                    daily_bars[code] = bar

            if not daily_prices:
                continue

            # 生成交易信号（使用前一日收盘数据，避免前视偏差）
            signals = []
            if prev_date is not None:
                for code in data_indexed:
                    df_idx = data_indexed[code]
                    if prev_date in df_idx.index and code in daily_prices:
                        prev_bar = df_idx.loc[prev_date]
                        if isinstance(prev_bar, pd.DataFrame):
                            prev_bar = prev_bar.iloc[0]

                        position = portfolio.get_position(code)
                        signal = rule_engine.generate_signal(
                            code=code,
                            current_date=date_str,
                            prev_bar=prev_bar,
                            current_price=daily_prices[code],
                            position=position,
                            portfolio=portfolio,
                            all_data=df_idx,
                        )
                        if signal is not None:
                            signals.append(signal)

            # 按优先级排序信号（风控 > 退出 > 入场）
            signals.sort(key=lambda s: s.priority, reverse=True)

            # 执行信号
            for signal in signals:
                symbol_name = signal.symbol
                info = symbol_info.get(symbol_name, {})
                original = info.get("original_symbol", symbol_name)

                if signal.is_buy:
                    portfolio.execute_buy(
                        symbol=symbol_name,
                        date=date_str,
                        price=daily_prices[symbol_name],
                        ratio=signal.ratio,
                        quantity=signal.quantity,
                        reason=signal.reason,
                    )
                elif signal.is_sell:
                    portfolio.execute_sell(
                        symbol=symbol_name,
                        date=date_str,
                        price=daily_prices[symbol_name],
                        ratio=signal.ratio if signal.ratio > 0 else 1.0,
                        quantity=signal.quantity,
                        reason=signal.reason,
                    )

            # 收盘结算
            portfolio.on_day_end(date_str, daily_prices)

            prev_date = date

        # 5. 汇总结果
        logger.info("回测完成，生成报告...")
        nav_history = portfolio.get_nav_history()

        # 构建基准净值
        benchmark_nav = {}
        for bm_name, bm_df in benchmark_data.items():
            bm_nav = self._calc_benchmark_nav(bm_df, start_date, end_date)
            benchmark_nav[bm_name] = bm_nav

        result = {
            "strategy_name": strategy_rules.strategy_name,
            "description": strategy_rules.description,
            "symbols": [info["original_symbol"] for info in symbol_info.values()],
            "symbol_details": list(symbol_info.values()),
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": self.initial_capital,
            "final_assets": portfolio.total_assets,
            "nav_history": nav_history,
            "benchmark_nav": benchmark_nav,
            "trades": portfolio.get_trade_history(),
            "positions": portfolio.get_positions_snapshot(),
            "strategy_rules": strategy_rules.to_dict(),
        }

        return result

    @staticmethod
    def _calc_benchmark_nav(df: pd.DataFrame, start_date: str, end_date: str) -> list:
        """计算基准的归一化净值"""
        df = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()
        if len(df) == 0:
            return []

        first_close = df['close'].iloc[0]
        nav_list = []
        for _, row in df.iterrows():
            nav_list.append({
                "date": row['date'].strftime('%Y-%m-%d'),
                "nav": row['close'] / first_close,
            })
        return nav_list

"""
规则引擎
执行 LLM 生成的结构化交易规则，逐日评估条件并生成交易信号
"""
import logging
from typing import Optional

import numpy as np
import pandas as pd

from src.strategy.models import (
    StrategyRules, EntryRule, ExitRule, RiskRule,
    Condition, ConditionType, Signal, Action, PositionSizing,
)

logger = logging.getLogger(__name__)


class RuleEngine:
    """规则引擎：将策略规则转为逐日交易信号"""

    def __init__(self, rules: StrategyRules):
        self.rules = rules
        # 金字塔加仓状态追踪 {symbol: {"level": int, "high_price": float, ...}}
        self._pyramid_state = {}

    def generate_signal(self, code: str, current_date: str, prev_bar: pd.Series,
                        current_price: float, position, portfolio,
                        all_data: pd.DataFrame) -> Optional[Signal]:
        """
        评估所有条件，返回当日交易信号（基于前一日数据，避免前视偏差）

        优先级：风控 > 退出 > 入场
        """
        # 1. 检查风控条件（最高优先级）
        signal = self._check_risk_rules(code, current_date, current_price, position, portfolio)
        if signal is not None:
            return signal

        # 2. 检查退出条件
        signal = self._check_exit_rules(code, current_date, prev_bar, current_price, position, all_data)
        if signal is not None:
            return signal

        # 3. 检查入场条件
        signal = self._check_entry_rules(code, current_date, prev_bar, current_price, position, portfolio, all_data)
        if signal is not None:
            return signal

        return None

    def _check_risk_rules(self, code: str, date: str, current_price: float,
                          position, portfolio) -> Optional[Signal]:
        """检查风控条件"""
        risk = self.rules.risk_rules
        if position is None or position.quantity <= 0:
            return None

        # 止损
        if risk.stop_loss and risk.stop_loss > 0:
            loss_pct = -position.profit_pct
            if loss_pct >= risk.stop_loss:
                return Signal(
                    action=Action.SELL,
                    symbol=code,
                    ratio=1.0,
                    reason=f"触发止损: 亏损{loss_pct:.1%} >= 止损线{risk.stop_loss:.1%}",
                    priority=100,
                )

        # 止盈
        if risk.take_profit and risk.take_profit > 0:
            gain_pct = position.profit_pct
            if gain_pct >= risk.take_profit:
                return Signal(
                    action=Action.SELL,
                    symbol=code,
                    ratio=1.0,
                    reason=f"触发止盈: 盈利{gain_pct:.1%} >= 止盈线{risk.take_profit:.1%}",
                    priority=90,
                )

        # 移动止损
        if risk.trailing_stop and risk.trailing_stop > 0:
            drawdown = -position.high_water_mark_pct
            if drawdown >= risk.trailing_stop:
                return Signal(
                    action=Action.SELL,
                    symbol=code,
                    ratio=1.0,
                    reason=f"触发移动止损: 从高点回撤{drawdown:.1%} >= {risk.trailing_stop:.1%}",
                    priority=95,
                )

        # 单标的最大仓位限制
        if risk.max_position and risk.max_position < 1.0:
            total_assets = portfolio.total_assets
            if total_assets > 0:
                pos_ratio = position.market_value / total_assets
                if pos_ratio > risk.max_position:
                    # 减仓到最大仓位
                    target_ratio = risk.max_position
                    sell_ratio = 1.0 - target_ratio / pos_ratio
                    if sell_ratio > 0.05:  # 只在超出5%时才减仓
                        return Signal(
                            action=Action.SELL,
                            symbol=code,
                            ratio=sell_ratio,
                            reason=f"仓位超限减仓: {pos_ratio:.1%} > 最大{risk.max_position:.1%}",
                            priority=80,
                        )

        return None

    def _check_exit_rules(self, code: str, date: str, prev_bar: pd.Series,
                          current_price: float, position, all_data: pd.DataFrame) -> Optional[Signal]:
        """检查退出条件"""
        if position is None or position.quantity <= 0:
            return None

        for rule in self.rules.exit_rules:
            all_met = True
            for condition in rule.conditions:
                if not self._evaluate_condition(condition, prev_bar, current_price, position, all_data, code):
                    all_met = False
                    break

            if all_met:
                return Signal(
                    action=Action.SELL,
                    symbol=code,
                    ratio=rule.sell_ratio,
                    reason=rule.description or "触发退出条件",
                    priority=50,
                )

        return None

    def _check_entry_rules(self, code: str, date: str, prev_bar: pd.Series,
                           current_price: float, position, portfolio,
                           all_data: pd.DataFrame) -> Optional[Signal]:
        """检查入场条件"""
        for rule in self.rules.entry_rules:
            all_met = True
            for condition in rule.conditions:
                if not self._evaluate_condition(condition, prev_bar, current_price, position, all_data, code):
                    all_met = False
                    break

            if all_met:
                # 确定仓位
                ps = self.rules.position_sizing
                ratio, quantity = self._calc_position_size(ps, rule, position, portfolio, code, current_price)

                return Signal(
                    action=Action.BUY,
                    symbol=code,
                    ratio=ratio,
                    quantity=quantity,
                    reason=rule.description or "触发入场条件",
                    priority=10,
                )

        return None

    def _evaluate_condition(self, condition: Condition, prev_bar: pd.Series,
                            current_price: float, position, all_data: pd.DataFrame,
                            code: str) -> bool:
        """评估单个条件"""
        ct = condition.type if isinstance(condition.type, ConditionType) else ConditionType(condition.type)
        params = condition.params

        try:
            if ct == ConditionType.INDICATOR_CROSS_ABOVE:
                return self._check_cross_above(prev_bar, params)
            elif ct == ConditionType.INDICATOR_CROSS_BELOW:
                return self._check_cross_below(prev_bar, params)
            elif ct == ConditionType.INDICATOR_ABOVE:
                return self._check_indicator_above(prev_bar, params)
            elif ct == ConditionType.INDICATOR_BELOW:
                return self._check_indicator_below(prev_bar, params)
            elif ct == ConditionType.PRICE_DROP_FROM_HIGH:
                return self._check_price_drop_from_high(prev_bar, params)
            elif ct == ConditionType.PRICE_DROP_FROM_PREV_BUY:
                return self._check_price_drop_from_prev_buy(current_price, position, params)
            elif ct == ConditionType.PRICE_RISE_FROM_COST:
                return self._check_price_rise_from_cost(current_price, position, params)
            elif ct == ConditionType.PRICE_RISE_FROM_LOW:
                return self._check_price_rise_from_low(prev_bar, params)
            elif ct == ConditionType.RSI_OVERBOUGHT:
                return self._check_rsi_overbought(prev_bar, params)
            elif ct == ConditionType.RSI_OVERSOLD:
                return self._check_rsi_oversold(prev_bar, params)
            elif ct == ConditionType.MACD_GOLDEN_CROSS:
                return self._check_macd_golden_cross(prev_bar)
            elif ct == ConditionType.MACD_DEATH_CROSS:
                return self._check_macd_death_cross(prev_bar)
            elif ct == ConditionType.BOLL_BREAK_UPPER:
                return self._check_boll_break_upper(prev_bar)
            elif ct == ConditionType.BOLL_BREAK_LOWER:
                return self._check_boll_break_lower(prev_bar)
            elif ct == ConditionType.VOLUME_SURGE:
                return self._check_volume_surge(prev_bar, params)
            elif ct == ConditionType.NO_POSITION:
                return position is None or position.quantity <= 0
            elif ct == ConditionType.HAS_POSITION:
                return position is not None and position.quantity > 0
            elif ct == ConditionType.HOLDING_DAYS:
                return self._check_holding_days(position, params)
            elif ct == ConditionType.PRICE_ABOVE:
                return current_price > params.get("threshold", 0)
            elif ct == ConditionType.PRICE_BELOW:
                return current_price < params.get("threshold", float('inf'))
            else:
                logger.warning(f"未实现的条件类型: {ct}")
                return False
        except Exception as e:
            logger.debug(f"评估条件 {ct} 失败: {e}")
            return False

    # ────────────────── 条件评估实现 ──────────────────

    @staticmethod
    def _get_val(bar: pd.Series, col: str) -> float:
        """安全获取bar中的值"""
        if col in bar.index:
            val = bar[col]
            if pd.notna(val):
                return float(val)
        return np.nan

    def _check_cross_above(self, bar: pd.Series, params: dict) -> bool:
        """检查指标上穿（简化：当前值>目标值即可，交叉需要前后两天数据，这里用近似）"""
        indicator = params.get("indicator", "close")
        target = params.get("target", "MA20")

        ind_val = self._get_val(bar, indicator)
        tgt_val = self._get_val(bar, target)

        if np.isnan(ind_val) or np.isnan(tgt_val):
            return False
        return ind_val > tgt_val

    def _check_cross_below(self, bar: pd.Series, params: dict) -> bool:
        """检查指标下穿"""
        indicator = params.get("indicator", "close")
        target = params.get("target", "MA20")

        ind_val = self._get_val(bar, indicator)
        tgt_val = self._get_val(bar, target)

        if np.isnan(ind_val) or np.isnan(tgt_val):
            return False
        return ind_val < tgt_val

    def _check_indicator_above(self, bar: pd.Series, params: dict) -> bool:
        indicator = params.get("indicator", "close")
        threshold = params.get("threshold", 0)
        val = self._get_val(bar, indicator)
        return val > threshold if not np.isnan(val) else False

    def _check_indicator_below(self, bar: pd.Series, params: dict) -> bool:
        indicator = params.get("indicator", "close")
        threshold = params.get("threshold", 0)
        val = self._get_val(bar, indicator)
        return val < threshold if not np.isnan(val) else False

    def _check_price_drop_from_high(self, bar: pd.Series, params: dict) -> bool:
        """从高点回撤超过阈值"""
        threshold = params.get("threshold", 0.05)

        # 尝试使用预计算的最高价
        high_col = None
        for col in bar.index:
            if col.startswith("MAX_HIGH"):
                high_col = col
                break

        if high_col and high_col in bar.index:
            high = self._get_val(bar, high_col)
            close = self._get_val(bar, "close")
            if not np.isnan(high) and high > 0:
                drop = (high - close) / high
                return drop >= threshold

        # 备用：用当前bar的high近似
        return False

    @staticmethod
    def _check_price_drop_from_prev_buy(current_price: float, position, params: dict) -> bool:
        """距上次买入价格再跌一定比例"""
        if position is None or position.last_buy_price <= 0:
            return False
        threshold = params.get("threshold", 0.05)
        drop = (position.last_buy_price - current_price) / position.last_buy_price
        return drop >= threshold

    @staticmethod
    def _check_price_rise_from_cost(current_price: float, position, params: dict) -> bool:
        """浮盈超过阈值"""
        if position is None or position.avg_cost <= 0:
            return False
        threshold = params.get("threshold", 0.3)
        gain = (current_price - position.avg_cost) / position.avg_cost
        return gain >= threshold

    def _check_price_rise_from_low(self, bar: pd.Series, params: dict) -> bool:
        """从低点反弹超过阈值"""
        threshold = params.get("threshold", 0.1)
        low_col = None
        for col in bar.index:
            if col.startswith("MIN_LOW"):
                low_col = col
                break

        if low_col and low_col in bar.index:
            low = self._get_val(bar, low_col)
            close = self._get_val(bar, "close")
            if not np.isnan(low) and low > 0:
                rise = (close - low) / low
                return rise >= threshold
        return False

    def _check_rsi_overbought(self, bar: pd.Series, params: dict) -> bool:
        period = params.get("period", 14)
        threshold = params.get("threshold", 70)
        rsi_val = self._get_val(bar, f"RSI{period}")
        return rsi_val > threshold if not np.isnan(rsi_val) else False

    def _check_rsi_oversold(self, bar: pd.Series, params: dict) -> bool:
        period = params.get("period", 14)
        threshold = params.get("threshold", 30)
        rsi_val = self._get_val(bar, f"RSI{period}")
        return rsi_val < threshold if not np.isnan(rsi_val) else False

    def _check_macd_golden_cross(self, bar: pd.Series) -> bool:
        """MACD金叉：DIF > DEA"""
        dif = self._get_val(bar, "MACD_DIF")
        dea = self._get_val(bar, "MACD_DEA")
        if np.isnan(dif) or np.isnan(dea):
            return False
        return dif > dea

    def _check_macd_death_cross(self, bar: pd.Series) -> bool:
        """MACD死叉：DIF < DEA"""
        dif = self._get_val(bar, "MACD_DIF")
        dea = self._get_val(bar, "MACD_DEA")
        if np.isnan(dif) or np.isnan(dea):
            return False
        return dif < dea

    def _check_boll_break_upper(self, bar: pd.Series) -> bool:
        close = self._get_val(bar, "close")
        upper = self._get_val(bar, "BOLL_UPPER")
        return close > upper if not np.isnan(close) and not np.isnan(upper) else False

    def _check_boll_break_lower(self, bar: pd.Series) -> bool:
        close = self._get_val(bar, "close")
        lower = self._get_val(bar, "BOLL_LOWER")
        return close < lower if not np.isnan(close) and not np.isnan(lower) else False

    def _check_volume_surge(self, bar: pd.Series, params: dict) -> bool:
        ratio = params.get("ratio", 2.0)
        vol = self._get_val(bar, "volume")
        vol_ma_col = None
        for col in bar.index:
            if col.startswith("VOL_MA"):
                vol_ma_col = col
                break
        if vol_ma_col:
            vol_ma = self._get_val(bar, vol_ma_col)
            return vol > vol_ma * ratio if not np.isnan(vol) and not np.isnan(vol_ma) else False
        return False

    @staticmethod
    def _check_holding_days(position, params: dict) -> bool:
        if position is None or not position.buy_date:
            return False
        import datetime
        buy_dt = datetime.datetime.strptime(position.buy_date, "%Y-%m-%d")
        # 简化计算，不排除非交易日
        days = (datetime.datetime.now() - buy_dt).days
        min_days = params.get("min", 0)
        max_days = params.get("max", float('inf'))
        return min_days <= days <= max_days

    # ────────────────── 仓位计算 ──────────────────

    def _calc_position_size(self, ps: PositionSizing, rule: EntryRule,
                            position, portfolio, code: str, current_price: float) -> tuple:
        """
        计算买入仓位，返回 (ratio, quantity)
        ratio: 使用可用资金的比例
        quantity: 指定数量（0=按ratio计算）
        """
        if ps.method.value == "fixed_ratio":
            return ps.value, 0
        elif ps.method.value == "all_in":
            return 0.95, 0  # 留5%现金
        elif ps.method.value == "equal_weight":
            # 等权分配
            n_symbols = len(set(t.symbol for t in portfolio.trades)) or 1
            ratio = min(1.0 / n_symbols, 0.5)  # 不超过50%
            return ratio, 0
        elif ps.method.value == "pyramid":
            return self._calc_pyramid_size(ps, position, portfolio, code)
        elif ps.method.value == "kelly":
            # 简化的凯利公式
            return min(ps.value, 0.5), 0  # 半凯利，上限50%
        else:
            return ps.value or 0.3, 0

    def _calc_pyramid_size(self, ps: PositionSizing, position, portfolio, code: str) -> tuple:
        """金字塔加仓仓位计算"""
        if code not in self._pyramid_state:
            self._pyramid_state[code] = {"level": 0}

        state = self._pyramid_state[code]
        level = state["level"]
        ratios = ps.ratios or [1, 1, 1.5, 2, 2, 2.5]

        if level >= len(ratios):
            return 0, 0  # 已达最大加仓次数

        # 当前层的资金比例
        current_ratio = ratios[level] * (ps.unit_ratio or 0.05)
        current_ratio = min(current_ratio, 0.5)  # 单次不超过50%

        # 更新加仓层级
        state["level"] = level + 1

        return current_ratio, 0

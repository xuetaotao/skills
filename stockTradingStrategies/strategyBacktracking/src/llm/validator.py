"""
规则校验器
校验 LLM 输出的策略规则完整性和逻辑一致性
"""
import logging
from typing import List, Tuple

from src.strategy.models import (
    StrategyRules, EntryRule, ExitRule, RiskRule,
    Condition, ConditionType, PositionSizing,
)

logger = logging.getLogger(__name__)


class RuleValidator:
    """策略规则校验器"""

    def validate(self, rules: StrategyRules) -> Tuple[bool, List[str]]:
        """
        校验策略规则
        返回: (是否通过, 错误信息列表)
        """
        errors = []

        # 1. 基本完整性检查
        if not rules.strategy_name:
            errors.append("缺少策略名称")

        if not rules.entry_rules:
            errors.append("缺少入场规则（entry_rules）")

        if not rules.exit_rules:
            errors.append("缺少退出规则（exit_rules）")

        # 2. 入场规则检查
        for i, rule in enumerate(rules.entry_rules):
            if not rule.conditions:
                errors.append(f"入场规则 {i+1} 没有条件")
            for j, cond in enumerate(rule.conditions):
                cond_errors = self._validate_condition(cond, f"入场规则{i+1}.条件{j+1}")
                errors.extend(cond_errors)

        # 3. 退出规则检查
        for i, rule in enumerate(rules.exit_rules):
            if not rule.conditions:
                errors.append(f"退出规则 {i+1} 没有条件")
            if rule.sell_ratio <= 0 or rule.sell_ratio > 1:
                errors.append(f"退出规则 {i+1} 的 sell_ratio 应在 (0, 1] 范围内")
            for j, cond in enumerate(rule.conditions):
                cond_errors = self._validate_condition(cond, f"退出规则{i+1}.条件{j+1}")
                errors.extend(cond_errors)

        # 4. 风控规则检查
        risk = rules.risk_rules
        if risk.stop_loss is not None and risk.stop_loss <= 0:
            errors.append("止损比例必须为正数")
        if risk.take_profit is not None and risk.take_profit <= 0:
            errors.append("止盈比例必须为正数")
        if risk.max_position <= 0 or risk.max_position > 1:
            errors.append("最大仓位比例应在 (0, 1] 范围内")
        if risk.trailing_stop is not None and risk.trailing_stop <= 0:
            errors.append("移动止损比例必须为正数")

        # 5. 仓位管理检查
        ps = rules.position_sizing
        if ps.method.value == "fixed_ratio" and (ps.value <= 0 or ps.value > 1):
            errors.append("固定比例仓位应在 (0, 1] 范围内")
        if ps.method.value == "pyramid" and not ps.ratios:
            errors.append("金字塔策略必须指定 ratios 列表")
        if ps.method.value == "pyramid" and ps.unit_ratio <= 0:
            errors.append("金字塔策略的 unit_ratio 必须为正数")

        # 6. 指标需求检查
        if not rules.indicators_needed:
            # 自动补充所需指标
            rules.indicators_needed = self._infer_indicators(rules)

        # 7. 逻辑一致性检查
        logic_errors = self._check_logic_consistency(rules)
        errors.extend(logic_errors)

        passed = len(errors) == 0
        if not passed:
            logger.warning(f"规则校验发现 {len(errors)} 个问题: {errors}")
        else:
            logger.info("规则校验通过")

        return passed, errors

    @staticmethod
    def _validate_condition(condition: Condition, path: str) -> List[str]:
        """校验单个条件"""
        errors = []
        try:
            ct = condition.type if isinstance(condition.type, ConditionType) else ConditionType(condition.type)
        except ValueError:
            errors.append(f"{path}: 未知条件类型 '{condition.type}'")
            return errors

        # 检查必要参数
        if ct in (ConditionType.INDICATOR_CROSS_ABOVE, ConditionType.INDICATOR_CROSS_BELOW):
            if "indicator" not in condition.params:
                errors.append(f"{path}: 缺少 indicator 参数")
            if "target" not in condition.params:
                errors.append(f"{path}: 缺少 target 参数")

        elif ct == ConditionType.PRICE_DROP_FROM_HIGH:
            if "threshold" not in condition.params:
                errors.append(f"{path}: 缺少 threshold 参数")

        elif ct == ConditionType.PRICE_DROP_FROM_PREV_BUY:
            if "threshold" not in condition.params:
                errors.append(f"{path}: 缺少 threshold 参数")

        elif ct == ConditionType.PRICE_RISE_FROM_COST:
            if "threshold" not in condition.params:
                errors.append(f"{path}: 缺少 threshold 参数")

        elif ct == ConditionType.RSI_OVERBOUGHT or ct == ConditionType.RSI_OVERSOLD:
            if "period" not in condition.params:
                condition.params.setdefault("period", 14)
            if "threshold" not in condition.params:
                if ct == ConditionType.RSI_OVERBOUGHT:
                    condition.params.setdefault("threshold", 70)
                else:
                    condition.params.setdefault("threshold", 30)

        return errors

    @staticmethod
    def _check_logic_consistency(rules: StrategyRules) -> List[str]:
        """检查逻辑一致性"""
        errors = []

        # 检查是否有"只买不卖"的风险
        has_exit = len(rules.exit_rules) > 0
        has_risk_exit = (rules.risk_rules.stop_loss is not None or
                         rules.risk_rules.trailing_stop is not None)

        if not has_exit and not has_risk_exit:
            errors.append("策略没有退出机制（无退出规则且无止损），可能导致只买不卖")

        return errors

    @staticmethod
    def _infer_indicators(rules: StrategyRules) -> List[str]:
        """从条件中推断需要的指标"""
        indicators = set()

        all_conditions = []
        for rule in rules.entry_rules:
            all_conditions.extend(rule.conditions)
        for rule in rules.exit_rules:
            all_conditions.extend(rule.conditions)

        for cond in all_conditions:
            ct = cond.type if isinstance(cond.type, ConditionType) else ConditionType(cond.type)
            params = cond.params

            if ct in (ConditionType.INDICATOR_CROSS_ABOVE, ConditionType.INDICATOR_CROSS_BELOW,
                      ConditionType.INDICATOR_ABOVE, ConditionType.INDICATOR_BELOW):
                for key in ("indicator", "target"):
                    val = params.get(key, "")
                    if val and val != "close" and val != "volume":
                        indicators.add(val)

            elif ct == ConditionType.RSI_OVERBOUGHT or ct == ConditionType.RSI_OVERSOLD:
                period = params.get("period", 14)
                indicators.add(f"RSI({period})")

            elif ct == ConditionType.MACD_GOLDEN_CROSS or ct == ConditionType.MACD_DEATH_CROSS:
                indicators.add("MACD(12,26,9)")

            elif ct == ConditionType.BOLL_BREAK_UPPER or ct == ConditionType.BOLL_BREAK_LOWER:
                indicators.add("BOLL(20,2)")

            elif ct == ConditionType.PRICE_DROP_FROM_HIGH:
                indicators.add("MAX_HIGH(252)")

            elif ct == ConditionType.PRICE_RISE_FROM_LOW:
                indicators.add("MIN_LOW(252)")

            elif ct == ConditionType.VOLUME_SURGE:
                indicators.add("VOL_MA(5)")

        # 补充指标名映射（如 MA20 -> MA(20)）
        resolved = set()
        for ind in indicators:
            if ind in ("MA20", "ma20"):
                resolved.add("MA(20)")
            elif ind in ("MA5", "ma5"):
                resolved.add("MA(5)")
            elif ind in ("MA60", "ma60"):
                resolved.add("MA(60)")
            elif ind in ("EMA12", "ema12"):
                resolved.add("EMA(12)")
            elif ind in ("EMA26", "ema26"):
                resolved.add("EMA(26)")
            else:
                resolved.add(ind)

        return sorted(list(resolved))

    def auto_fix(self, rules: StrategyRules) -> StrategyRules:
        """
        自动修正一些常见问题
        """
        # 如果没有止损，默认加8%止损
        if rules.risk_rules.stop_loss is None:
            rules.risk_rules.stop_loss = 0.08
            rules.risk_rules.description = "自动补充：默认8%止损"
            logger.info("自动补充：8%止损")

        # 如果没有仓位管理，默认30%固定比例
        if not rules.position_sizing.method or rules.position_sizing.method.value == "fixed_ratio":
            if rules.position_sizing.value <= 0:
                rules.position_sizing.value = 0.3
                logger.info("自动补充：30%固定比例仓位")

        # 自动推断指标
        if not rules.indicators_needed:
            rules.indicators_needed = self._infer_indicators(rules)

        return rules

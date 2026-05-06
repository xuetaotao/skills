"""
LLM 策略解析器
调用 LLM 将用户自然语言策略转为结构化交易规则
"""
import json
import logging
import os
from typing import Optional

from src.config import LLM_CONFIG
from src.strategy.models import StrategyRules
from src.llm.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from src.llm.validator import RuleValidator

logger = logging.getLogger(__name__)


class StrategyParser:
    """策略解析器：自然语言 → 结构化规则"""

    def __init__(self, api_key: str = None, model: str = None, base_url: str = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model or LLM_CONFIG["model"]
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL", None)
        self.max_retries = LLM_CONFIG["max_retries"]
        self.validator = RuleValidator()

    def parse(self, strategy_description: str, symbols: list,
              start_date: str, end_date: str) -> StrategyRules:
        """
        解析自然语言策略
        返回校验通过的 StrategyRules 对象
        """
        # 如果没有 API Key，尝试使用内置规则解析
        if not self.api_key:
            logger.warning("未设置 OPENAI_API_KEY，尝试使用内置关键词匹配解析")
            return self._fallback_parse(strategy_description, symbols)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            strategy_description=strategy_description,
            symbols=", ".join(symbols),
            start_date=start_date,
            end_date=end_date,
        )

        # 尝试调用 LLM
        for attempt in range(self.max_retries):
            try:
                logger.info(f"尝试解析策略 (第{attempt+1}次)...")
                result_text = self._call_llm(user_prompt)
                rules = self._parse_response(result_text)

                # 校验
                passed, errors = self.validator.validate(rules)
                if passed:
                    logger.info(f"策略解析成功: {rules.strategy_name}")
                    return rules

                # 尝试自动修正
                logger.warning(f"校验发现问题，尝试自动修正: {errors}")
                rules = self.validator.auto_fix(rules)
                passed, errors = self.validator.validate(rules)
                if passed:
                    logger.info(f"自动修正后通过: {rules.strategy_name}")
                    return rules

                # 修正后仍有问题，重试
                if attempt < self.max_retries - 1:
                    logger.warning(f"修正后仍不通过，重试... 剩余问题: {errors}")

            except Exception as e:
                logger.warning(f"第{attempt+1}次解析失败: {e}")
                if attempt == self.max_retries - 1:
                    logger.error("所有尝试均失败，使用内置解析")
                    return self._fallback_parse(strategy_description, symbols)

        return self._fallback_parse(strategy_description, symbols)

    def _call_llm(self, user_prompt: str) -> str:
        """调用 LLM API"""
        try:
            from openai import OpenAI

            client_kwargs = {"api_key": self.api_key}
            if self.base_url:
                client_kwargs["base_url"] = self.base_url

            client = OpenAI(**client_kwargs)

            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=LLM_CONFIG["temperature"],
            )

            return response.choices[0].message.content.strip()

        except ImportError:
            raise RuntimeError("请安装 openai 库: pip install openai")
        except Exception as e:
            raise RuntimeError(f"LLM 调用失败: {e}")

    def _parse_response(self, text: str) -> StrategyRules:
        """解析 LLM 返回的文本为 StrategyRules"""
        # 去除可能的 markdown 代码块包裹
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # 去掉首尾的 ``` 行
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # 尝试提取 JSON 部分
            import re
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError(f"无法解析 LLM 返回的 JSON: {text[:200]}")

        return StrategyRules.from_dict(data)

    def _fallback_parse(self, description: str, symbols: list) -> StrategyRules:
        """
        内置关键词匹配解析（当 LLM 不可用时的降级方案）
        支持常见的策略描述模式
        """
        from src.strategy.models import (
            Condition, ConditionType, EntryRule, ExitRule,
            RiskRule, PositionSizing, PositionSizingMethod,
        )

        desc = description.lower()

        # 默认规则
        entry_rules = []
        exit_rules = []
        risk_rules = RiskRule(stop_loss=0.08, max_position=0.6)
        position_sizing = PositionSizing(
            method=PositionSizingMethod.FIXED_RATIO,
            value=0.3,
        )
        indicators_needed = ["MA(20)"]

        # ── 检测均线策略 ──
        if any(kw in desc for kw in ["均线", "ma", "ma20", "20日均线"]):
            cross_above = any(kw in desc for kw in ["上穿", "突破", "站上", "金叉", "cross above"])
            cross_below = any(kw in desc for kw in ["下穿", "跌破", "死叉", "cross below"])

            if cross_above:
                entry_rules.append(EntryRule(
                    conditions=[Condition(
                        type=ConditionType.INDICATOR_CROSS_ABOVE,
                        params={"indicator": "close", "target": "MA20"},
                        description="收盘价上穿20日均线",
                    )],
                    description="均线上穿买入",
                ))

            if cross_below:
                exit_rules.append(ExitRule(
                    conditions=[Condition(
                        type=ConditionType.INDICATOR_CROSS_BELOW,
                        params={"indicator": "close", "target": "MA20"},
                        description="收盘价下穿20日均线",
                    )],
                    sell_ratio=1.0,
                    description="均线下穿卖出",
                ))

            # 检测长期均线
            if any(kw in desc for kw in ["60日", "ma60", "60均线"]):
                indicators_needed.append("MA(60)")
            if any(kw in desc for kw in ["5日", "ma5", "5均线"]):
                indicators_needed.append("MA(5)")

        # ── 检测RSI策略 ──
        if any(kw in desc for kw in ["rsi", "相对强弱"]):
            indicators_needed.append("RSI(14)")
            if any(kw in desc for kw in ["超买", "高于70", ">70"]):
                exit_rules.append(ExitRule(
                    conditions=[Condition(
                        type=ConditionType.RSI_OVERBOUGHT,
                        params={"period": 14, "threshold": 70},
                        description="RSI超买",
                    )],
                    sell_ratio=0.5,
                    description="RSI超买卖出",
                ))
            if any(kw in desc for kw in ["超卖", "低于30", "<30"]):
                entry_rules.append(EntryRule(
                    conditions=[Condition(
                        type=ConditionType.RSI_OVERSOLD,
                        params={"period": 14, "threshold": 30},
                        description="RSI超卖",
                    )],
                    description="RSI超卖买入",
                ))

        # ── 检测MACD策略 ──
        if any(kw in desc for kw in ["macd"]):
            indicators_needed.append("MACD(12,26,9)")
            if any(kw in desc for kw in ["金叉", "dif上穿dea"]):
                entry_rules.append(EntryRule(
                    conditions=[Condition(
                        type=ConditionType.MACD_GOLDEN_CROSS,
                        params={},
                        description="MACD金叉",
                    )],
                    description="MACD金叉买入",
                ))
            if any(kw in desc for kw in ["死叉", "dif下穿dea"]):
                exit_rules.append(ExitRule(
                    conditions=[Condition(
                        type=ConditionType.MACD_DEATH_CROSS,
                        params={},
                        description="MACD死叉",
                    )],
                    sell_ratio=1.0,
                    description="MACD死叉卖出",
                ))

        # ── 检测金字塔策略 ──
        if any(kw in desc for kw in ["金字塔", "越跌越买", "大跌大买", "加仓"]):
            indicators_needed.append("MAX_HIGH(252)")

            # 解析加仓间距
            interval = 0.025
            if "5%" in desc or "5％" in desc:
                interval = 0.05
            elif "8%" in desc or "8％" in desc:
                interval = 0.08
            elif "10%" in desc or "10％" in desc:
                interval = 0.10

            # 解析触发跌幅
            trigger = 0.065
            if "30%" in desc or "30％" in desc:
                trigger = 0.30
            elif "20%" in desc or "20％" in desc:
                trigger = 0.20
            elif "10%" in desc or "10％" in desc:
                trigger = 0.10

            entry_rules.append(EntryRule(
                conditions=[
                    Condition(
                        type=ConditionType.PRICE_DROP_FROM_HIGH,
                        params={"threshold": trigger},
                        description=f"从高点下跌{trigger:.0%}首次建仓",
                    ),
                    Condition(
                        type=ConditionType.NO_POSITION,
                        params={},
                        description="当前无仓位",
                    ),
                ],
                description="金字塔策略首次建仓",
            ))

            entry_rules.append(EntryRule(
                conditions=[
                    Condition(
                        type=ConditionType.PRICE_DROP_FROM_PREV_BUY,
                        params={"threshold": interval},
                        description=f"距上次买入再跌{interval:.0%}加仓",
                    ),
                    Condition(
                        type=ConditionType.HAS_POSITION,
                        params={},
                        description="当前有仓位",
                    ),
                ],
                description="金字塔策略加仓",
            ))

            position_sizing = PositionSizing(
                method=PositionSizingMethod.PYRAMID,
                ratios=[1, 1, 1.5, 2, 2, 2.5],
                unit_ratio=0.05,
                description="金字塔递增加仓 1:1:1.5:2:2:2.5",
            )

        # ── 检测布林带策略 ──
        if any(kw in desc for kw in ["布林", "boll", "bollinger"]):
            indicators_needed.append("BOLL(20,2)")
            if any(kw in desc for kw in ["下轨", "跌破下轨"]):
                entry_rules.append(EntryRule(
                    conditions=[Condition(
                        type=ConditionType.BOLL_BREAK_LOWER,
                        params={},
                        description="跌破布林下轨",
                    )],
                    description="布林下轨买入",
                ))
            if any(kw in desc for kw in ["上轨", "突破上轨"]):
                exit_rules.append(ExitRule(
                    conditions=[Condition(
                        type=ConditionType.BOLL_BREAK_UPPER,
                        params={},
                        description="突破布林上轨",
                    )],
                    sell_ratio=0.5,
                    description="布林上轨卖出",
                ))

        # ── 检测止损 ──
        import re
        stop_match = re.search(r'止损\s*(\d+)[%％]', description)
        if stop_match:
            risk_rules.stop_loss = int(stop_match.group(1)) / 100

        # ── 检测止盈 ──
        profit_match = re.search(r'止盈\s*(\d+)[%％]', description)
        if profit_match:
            risk_rules.take_profit = int(profit_match.group(1)) / 100

        # ── 如果没有匹配到任何规则，使用默认的均线策略 ──
        if not entry_rules:
            entry_rules.append(EntryRule(
                conditions=[Condition(
                    type=ConditionType.INDICATOR_CROSS_ABOVE,
                    params={"indicator": "close", "target": "MA20"},
                    description="收盘价上穿20日均线（默认）",
                )],
                description="默认均线策略买入",
            ))

        if not exit_rules:
            exit_rules.append(ExitRule(
                conditions=[Condition(
                    type=ConditionType.INDICATOR_CROSS_BELOW,
                    params={"indicator": "close", "target": "MA20"},
                    description="收盘价下穿20日均线（默认）",
                )],
                sell_ratio=1.0,
                description="默认均线策略卖出",
            ))

        rules = StrategyRules(
            strategy_name="内置解析策略",
            description=description[:200],
            entry_rules=entry_rules,
            exit_rules=exit_rules,
            risk_rules=risk_rules,
            position_sizing=position_sizing,
            indicators_needed=indicators_needed,
        )

        # 自动修正
        rules = self.validator.auto_fix(rules)
        logger.info(f"内置解析完成: {len(entry_rules)}条入场规则, {len(exit_rules)}条退出规则")
        return rules

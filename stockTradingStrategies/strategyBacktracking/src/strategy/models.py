"""
策略规则数据模型
定义 LLM 输出的结构化交易规则格式，以及回测引擎使用的信号模型
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class Action(Enum):
    """交易动作"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class ConditionType(Enum):
    """条件类型"""
    # 趋势类
    INDICATOR_CROSS_ABOVE = "indicator_cross_above"       # 指标上穿
    INDICATOR_CROSS_BELOW = "indicator_cross_below"       # 指标下穿
    INDICATOR_ABOVE = "indicator_above"                   # 指标在上方
    INDICATOR_BELOW = "indicator_below"                   # 指标在下方

    # 价格类
    PRICE_DROP_FROM_HIGH = "price_drop_from_high"          # 从高点回撤
    PRICE_DROP_FROM_PREV_BUY = "price_drop_from_prev_buy"  # 距上次买入再跌
    PRICE_RISE_FROM_COST = "price_rise_from_cost"          # 浮盈比例
    PRICE_RISE_FROM_LOW = "price_rise_from_low"            # 从低点反弹
    PRICE_ABOVE = "price_above"                            # 价格高于阈值
    PRICE_BELOW = "price_below"                            # 价格低于阈值

    # 振荡器类
    RSI_OVERBOUGHT = "rsi_overbought"                      # RSI超买
    RSI_OVERSOLD = "rsi_oversold"                          # RSI超卖
    MACD_GOLDEN_CROSS = "macd_golden_cross"                # MACD金叉
    MACD_DEATH_CROSS = "macd_death_cross"                  # MACD死叉

    # 布林带类
    BOLL_BREAK_UPPER = "boll_break_upper"                  # 突破布林上轨
    BOLL_BREAK_LOWER = "boll_break_lower"                  # 跌破布林下轨

    # 成交量类
    VOLUME_SURGE = "volume_surge"                          # 放量

    # 持仓类
    HOLDING_DAYS = "holding_days"                          # 持仓天数
    NO_POSITION = "no_position"                            # 当前无仓位
    HAS_POSITION = "has_position"                          # 当前有仓位

    # 自定义
    CUSTOM_EXPRESSION = "custom_expression"                # 自定义Python表达式


class PositionSizingMethod(Enum):
    """仓位管理方法"""
    FIXED_RATIO = "fixed_ratio"           # 固定比例（如每次用30%可用资金）
    FIXED_AMOUNT = "fixed_amount"         # 固定金额
    EQUAL_WEIGHT = "equal_weight"         # 等权（多标的平均分配）
    PYRAMID = "pyramid"                   # 金字塔递增
    KELLY = "kelly"                       # 凯利公式
    ALL_IN = "all_in"                     # 全仓


@dataclass
class Condition:
    """交易条件"""
    type: ConditionType
    params: dict = field(default_factory=dict)
    description: str = ""

    def __post_init__(self):
        if isinstance(self.type, str):
            self.type = ConditionType(self.type)


@dataclass
class Signal:
    """交易信号（回测引擎使用）"""
    action: Action
    symbol: str = ""
    quantity: int = 0           # 数量（股），0表示由仓位管理决定
    ratio: float = 0.0          # 资金比例，如0.3表示用30%可用资金
    reason: str = ""            # 信号原因（用于报告）
    priority: int = 0           # 优先级（风控>退出>入场）

    @property
    def is_buy(self) -> bool:
        return self.action == Action.BUY

    @property
    def is_sell(self) -> bool:
        return self.action == Action.SELL


@dataclass
class EntryRule:
    """入场规则"""
    conditions: list = field(default_factory=list)  # List[Condition]，所有条件AND
    action: Action = Action.BUY
    position_sizing: dict = field(default_factory=dict)  # 仓位管理参数
    description: str = ""


@dataclass
class ExitRule:
    """退出规则"""
    conditions: list = field(default_factory=list)  # List[Condition]
    action: Action = Action.SELL
    sell_ratio: float = 1.0      # 卖出比例，1.0=全部卖出
    description: str = ""


@dataclass
class RiskRule:
    """风控规则"""
    stop_loss: Optional[float] = None        # 止损比例，如0.08=8%
    take_profit: Optional[float] = None      # 止盈比例
    max_position: float = 0.8                # 单标的最大仓位占比
    max_drawdown: Optional[float] = None     # 最大回撤限制
    trailing_stop: Optional[float] = None    # 移动止损比例
    description: str = ""


@dataclass
class PositionSizing:
    """仓位管理配置"""
    method: PositionSizingMethod = PositionSizingMethod.FIXED_RATIO
    value: float = 0.3                      # 固定比例/金额
    ratios: list = field(default_factory=list)  # 金字塔比例列表
    unit_ratio: float = 0.05                # 金字塔单位比例
    description: str = ""

    def __post_init__(self):
        if isinstance(self.method, str):
            self.method = PositionSizingMethod(self.method)


@dataclass
class StrategyRules:
    """
    完整策略规则（LLM的输出格式）
    这是 LLM 解析自然语言策略后生成的结构化对象
    """
    strategy_name: str = ""
    description: str = ""
    entry_rules: list = field(default_factory=list)    # List[EntryRule]
    exit_rules: list = field(default_factory=list)     # List[ExitRule]
    risk_rules: RiskRule = field(default_factory=RiskRule)
    position_sizing: PositionSizing = field(default_factory=PositionSizing)
    indicators_needed: list = field(default_factory=list)  # 需要的指标列表

    def to_dict(self) -> dict:
        """序列化为字典（用于JSON输出）"""
        import dataclasses
        result = {}
        for k, v in dataclasses.asdict(self).items():
            if isinstance(v, Enum):
                result[k] = v.value
            else:
                result[k] = v
        return result

    @classmethod
    def from_dict(cls, d: dict) -> "StrategyRules":
        """从字典反序列化"""
        # 处理嵌套对象
        entry_rules = []
        for er in d.get("entry_rules", []):
            conditions = [Condition(**c) if isinstance(c, dict) else c for c in er.get("conditions", [])]
            er["conditions"] = conditions
            entry_rules.append(EntryRule(**er))

        exit_rules = []
        for er in d.get("exit_rules", []):
            conditions = [Condition(**c) if isinstance(c, dict) else c for c in er.get("conditions", [])]
            er["conditions"] = conditions
            exit_rules.append(ExitRule(**er))

        risk_data = d.get("risk_rules", {})
        risk_rules = RiskRule(**risk_data) if isinstance(risk_data, dict) else risk_data

        ps_data = d.get("position_sizing", {})
        position_sizing = PositionSizing(**ps_data) if isinstance(ps_data, dict) else ps_data

        return cls(
            strategy_name=d.get("strategy_name", ""),
            description=d.get("description", ""),
            entry_rules=entry_rules,
            exit_rules=exit_rules,
            risk_rules=risk_rules,
            position_sizing=position_sizing,
            indicators_needed=d.get("indicators_needed", []),
        )

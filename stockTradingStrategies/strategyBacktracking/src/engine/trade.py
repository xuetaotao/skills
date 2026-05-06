"""
交易记录模型
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Trade:
    """单笔交易记录"""
    trade_id: int = 0
    symbol: str = ""
    action: str = ""          # "buy" / "sell"
    date: str = ""            # 成交日期
    price: float = 0.0        # 成交价格
    quantity: int = 0          # 成交数量（股）
    amount: float = 0.0       # 成交金额
    commission: float = 0.0   # 佣金
    stamp_tax: float = 0.0    # 印花税
    slippage_cost: float = 0.0  # 滑点成本
    total_cost: float = 0.0   # 总成本（含佣金印花税滑点）
    reason: str = ""          # 交易原因
    profit: Optional[float] = None  # 卖出时的盈亏

    @property
    def is_buy(self) -> bool:
        return self.action == "buy"

    @property
    def is_sell(self) -> bool:
        return self.action == "sell"

    def to_dict(self) -> dict:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "action": self.action,
            "date": self.date,
            "price": self.price,
            "quantity": self.quantity,
            "amount": round(self.amount, 2),
            "commission": round(self.commission, 2),
            "stamp_tax": round(self.stamp_tax, 2),
            "slippage_cost": round(self.slippage_cost, 2),
            "total_cost": round(self.total_cost, 2),
            "reason": self.reason,
            "profit": round(self.profit, 2) if self.profit is not None else None,
        }


@dataclass
class Position:
    """持仓信息"""
    symbol: str = ""
    quantity: int = 0          # 持仓数量
    avg_cost: float = 0.0      # 平均成本
    current_price: float = 0.0 # 当前价格
    buy_date: str = ""         # 首次买入日期
    last_buy_date: str = ""    # 最近一次买入日期
    last_buy_price: float = 0.0  # 最近一次买入价格
    highest_price: float = 0.0   # 持仓期间最高价（用于移动止损）

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def cost_value(self) -> float:
        return self.quantity * self.avg_cost

    @property
    def profit_loss(self) -> float:
        return self.market_value - self.cost_value

    @property
    def profit_pct(self) -> float:
        if self.avg_cost == 0:
            return 0.0
        return (self.current_price - self.avg_cost) / self.avg_cost

    @property
    def high_water_mark_pct(self) -> float:
        """从最高点回撤比例"""
        if self.highest_price == 0:
            return 0.0
        return (self.current_price - self.highest_price) / self.highest_price

    def update_on_buy(self, quantity: int, price: float, date: str):
        """买入后更新持仓"""
        total_cost = self.avg_cost * self.quantity + price * quantity
        total_qty = self.quantity + quantity
        if total_qty > 0:
            self.avg_cost = total_cost / total_qty
        self.quantity = total_qty
        self.last_buy_date = date
        self.last_buy_price = price
        if not self.buy_date:
            self.buy_date = date
        self.highest_price = max(self.highest_price, price)

    def update_on_sell(self, quantity: int, price: float) -> Optional[float]:
        """卖出后更新持仓，返回本次卖出盈亏"""
        profit = (price - self.avg_cost) * quantity
        self.quantity -= quantity
        if self.quantity <= 0:
            self.quantity = 0
            self.avg_cost = 0.0
        return profit

    def update_price(self, price: float):
        """更新当前价格和最高价"""
        self.current_price = price
        if price > self.highest_price:
            self.highest_price = price

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "avg_cost": round(self.avg_cost, 4),
            "current_price": round(self.current_price, 4),
            "market_value": round(self.market_value, 2),
            "cost_value": round(self.cost_value, 2),
            "profit_loss": round(self.profit_loss, 2),
            "profit_pct": f"{self.profit_pct:.2%}",
            "buy_date": self.buy_date,
        }

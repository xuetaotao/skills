"""
组合管理器
管理资金、持仓、交易记录
"""
import logging
from typing import Dict, List, Optional

from src.config import TRADING_CONFIG
from src.engine.trade import Trade, Position

logger = logging.getLogger(__name__)


class Portfolio:
    """投资组合管理器"""

    def __init__(self, initial_capital: float = 1000000):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self._trade_counter = 0
        self._frozen_cash = 0.0  # 冻结资金（T+1限制，当日买入不可卖出）

        # 交易成本参数
        self.commission_rate = TRADING_CONFIG["commission_rate"]
        self.commission_min = TRADING_CONFIG["commission_min"]
        self.stamp_tax_rate = TRADING_CONFIG["stamp_tax_rate"]
        self.slippage = TRADING_CONFIG["slippage"]

        # 每日净值记录
        self._nav_history: List[dict] = []

    @property
    def total_assets(self) -> float:
        """总资产 = 现金 + 持仓市值"""
        return self.cash + sum(p.market_value for p in self.positions.values())

    @property
    def available_cash(self) -> float:
        """可用资金"""
        return max(0, self.cash - self._frozen_cash)

    @property
    def position_value(self) -> float:
        """持仓总市值"""
        return sum(p.market_value for p in self.positions.values())

    @property
    def position_ratio(self) -> float:
        """仓位比例"""
        total = self.total_assets
        return self.position_value / total if total > 0 else 0.0

    def get_position(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)

    def has_position(self, symbol: str) -> bool:
        pos = self.positions.get(symbol)
        return pos is not None and pos.quantity > 0

    def execute_buy(self, symbol: str, date: str, price: float,
                    ratio: float = 0.0, quantity: int = 0,
                    reason: str = "") -> Optional[Trade]:
        """
        执行买入
        ratio: 使用可用资金的比例（如0.3 = 30%），quantity为0时按ratio计算
        quantity: 指定买入数量，优先于ratio
        """
        # 计算滑点后的实际价格
        actual_price = price * (1 + self.slippage)

        if quantity <= 0 and ratio > 0:
            # 按资金比例计算数量
            invest_amount = self.available_cash * ratio
            quantity = int(invest_amount / (actual_price * 100)) * 100  # A股100股整手
            if quantity <= 0:
                logger.debug(f"资金不足买入1手: {symbol}, 可用={self.available_cash:.0f}, 需要={actual_price*100:.0f}")
                return None
        elif quantity <= 0:
            return None

        amount = actual_price * quantity
        commission = max(amount * self.commission_rate, self.commission_min)
        total_cost = amount + commission

        if total_cost > self.available_cash:
            # 资金不足，减少数量
            quantity = int(self.available_cash / (actual_price * 100)) * 100
            if quantity <= 0:
                return None
            amount = actual_price * quantity
            commission = max(amount * self.commission_rate, self.commission_min)
            total_cost = amount + commission

        # 执行
        self._trade_counter += 1
        trade = Trade(
            trade_id=self._trade_counter,
            symbol=symbol,
            action="buy",
            date=date,
            price=actual_price,
            quantity=quantity,
            amount=amount,
            commission=commission,
            total_cost=total_cost,
            reason=reason,
        )

        self.cash -= total_cost
        # T+1冻结（标记当日买入的市值，次日解冻）
        self._frozen_cash += total_cost

        # 更新持仓
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)
        self.positions[symbol].update_on_buy(quantity, actual_price, date)

        self.trades.append(trade)
        logger.debug(f"买入 {symbol}: {quantity}股 @ {actual_price:.2f}, 原因={reason}")
        return trade

    def execute_sell(self, symbol: str, date: str, price: float,
                     ratio: float = 1.0, quantity: int = 0,
                     reason: str = "") -> Optional[Trade]:
        """
        执行卖出
        ratio: 卖出持仓的比例（1.0=全部卖出）
        quantity: 指定卖出数量，优先于ratio
        """
        pos = self.positions.get(symbol)
        if pos is None or pos.quantity <= 0:
            return None

        # T+1限制：当日买入的不能卖出（简化处理，不考虑日内分笔）
        sellable_qty = pos.quantity  # 实际应该减去当日买入量，这里简化处理

        if quantity > 0:
            sell_qty = min(quantity, sellable_qty)
        else:
            sell_qty = int(sellable_qty * ratio / 100) * 100
            sell_qty = max(sell_qty, min(sellable_qty, 100))  # 至少卖100股（或全部）

        if sell_qty <= 0:
            return None

        # 滑点
        actual_price = price * (1 - self.slippage)
        amount = actual_price * sell_qty
        commission = max(amount * self.commission_rate, self.commission_min)
        stamp_tax = amount * self.stamp_tax_rate
        total_cost = commission + stamp_tax

        # 计算盈亏
        profit = pos.update_on_sell(sell_qty, actual_price)

        self._trade_counter += 1
        trade = Trade(
            trade_id=self._trade_counter,
            symbol=symbol,
            action="sell",
            date=date,
            price=actual_price,
            quantity=sell_qty,
            amount=amount,
            commission=commission,
            stamp_tax=stamp_tax,
            total_cost=total_cost,
            reason=reason,
            profit=profit,
        )

        self.cash += amount - total_cost

        # 清理空仓
        if pos.quantity <= 0:
            del self.positions[symbol]

        self.trades.append(trade)
        logger.debug(f"卖出 {symbol}: {sell_qty}股 @ {actual_price:.2f}, 盈亏={profit:.2f}, 原因={reason}")
        return trade

    def on_day_end(self, date: str, prices: Dict[str, float]):
        """
        每日收盘后：更新持仓价格、解冻资金、记录净值
        prices: {symbol: close_price}
        """
        # 解冻资金（T+1：昨天的冻结今天解冻）
        self._frozen_cash = 0.0

        # 更新持仓价格
        for symbol, price in prices.items():
            if symbol in self.positions:
                self.positions[symbol].update_price(price)

        # 记录每日净值
        total = self.total_assets
        self._nav_history.append({
            "date": date,
            "nav": total / self.initial_capital,  # 归一化净值
            "total_assets": total,
            "cash": self.cash,
            "position_value": self.position_value,
            "position_ratio": self.position_ratio,
        })

    def get_nav_history(self) -> list:
        """获取每日净值历史"""
        return self._nav_history

    def get_trade_history(self) -> list:
        """获取交易记录"""
        return [t.to_dict() for t in self.trades]

    def get_positions_snapshot(self) -> list:
        """获取当前持仓快照"""
        return [p.to_dict() for p in self.positions.values()]

    def reset(self):
        """重置组合"""
        self.cash = self.initial_capital
        self.positions.clear()
        self.trades.clear()
        self._trade_counter = 0
        self._frozen_cash = 0.0
        self._nav_history.clear()

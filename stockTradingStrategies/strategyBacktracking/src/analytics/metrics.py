"""
绩效指标计算
"""
import numpy as np
import pandas as pd
from typing import List, Optional

from src.config import TRADING_CONFIG


def calc_all_metrics(nav_history: list, trades: list, benchmark_nav: dict = None) -> dict:
    """
    计算全部绩效指标
    nav_history: [{date, nav, total_assets, ...}, ...]
    trades: [{action, date, price, quantity, profit, ...}, ...]
    benchmark_nav: {name: [{date, nav}, ...]}
    """
    if not nav_history:
        return {}

    navs = [h["nav"] for h in nav_history]
    dates = [h["date"] for h in nav_history]
    total_assets = [h["total_assets"] for h in nav_history]

    # 基本收益
    total_return = navs[-1] - 1.0
    trading_days = len(navs)
    annual_return = _annualized_return(navs, trading_days)

    # 波动率
    daily_returns = _daily_returns(navs)
    annual_volatility = _annualized_volatility(daily_returns)

    # 最大回撤
    max_drawdown, max_dd_start, max_dd_end = _max_drawdown(navs, dates)

    # 夏普比率
    risk_free_rate = TRADING_CONFIG["risk_free_rate"]
    sharpe = _sharpe_ratio(annual_return, annual_volatility, risk_free_rate)

    # 索提诺比率
    sortino = _sortino_ratio(daily_returns, risk_free_rate)

    # 卡尔玛比率
    calmar = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0

    # 交易统计
    trade_stats = _trade_statistics(trades)

    # Alpha / Beta
    alpha, beta = 0, 0
    if benchmark_nav:
        for bm_name, bm_data in benchmark_nav.items():
            alpha, beta = _alpha_beta(navs, dates, bm_data, risk_free_rate)
            break  # 取第一个基准

    metrics = {
        "total_return": total_return,
        "total_return_pct": f"{total_return:.2%}",
        "annual_return": annual_return,
        "annual_return_pct": f"{annual_return:.2%}",
        "trading_days": trading_days,
        "annual_volatility": annual_volatility,
        "annual_volatility_pct": f"{annual_volatility:.2%}",
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": f"{max_drawdown:.2%}",
        "max_drawdown_start": max_dd_start,
        "max_drawdown_end": max_dd_end,
        "sharpe_ratio": round(sharpe, 4),
        "sortino_ratio": round(sortino, 4),
        "calmar_ratio": round(calmar, 4),
        "alpha": round(alpha, 4),
        "beta": round(beta, 4),
        **trade_stats,
    }

    return metrics


def _annualized_return(navs: list, trading_days: int) -> float:
    """年化收益率"""
    if trading_days <= 0 or navs[0] <= 0:
        return 0.0
    total = navs[-1] / navs[0]
    years = trading_days / TRADING_CONFIG["trading_days_per_year"]
    if years <= 0:
        return 0.0
    return total ** (1 / years) - 1


def _daily_returns(navs: list) -> np.ndarray:
    """日收益率序列"""
    nav_arr = np.array(navs)
    return np.diff(nav_arr) / nav_arr[:-1]


def _annualized_volatility(daily_returns: np.ndarray) -> float:
    """年化波动率"""
    if len(daily_returns) < 2:
        return 0.0
    return float(np.std(daily_returns, ddof=1) * np.sqrt(TRADING_CONFIG["trading_days_per_year"]))


def _max_drawdown(navs: list, dates: list) -> tuple:
    """
    最大回撤
    返回: (最大回撤比例, 开始日期, 结束日期)
    """
    nav_arr = np.array(navs)
    peak = nav_arr[0]
    max_dd = 0.0
    dd_start = dates[0]
    dd_end = dates[0]
    temp_start = dates[0]

    for i in range(len(nav_arr)):
        if nav_arr[i] > peak:
            peak = nav_arr[i]
            temp_start = dates[i]
        dd = (peak - nav_arr[i]) / peak
        if dd > max_dd:
            max_dd = dd
            dd_start = temp_start
            dd_end = dates[i]

    return max_dd, dd_start, dd_end


def _sharpe_ratio(annual_return: float, annual_volatility: float,
                  risk_free_rate: float) -> float:
    """夏普比率"""
    if annual_volatility <= 0:
        return 0.0
    return (annual_return - risk_free_rate) / annual_volatility


def _sortino_ratio(daily_returns: np.ndarray, risk_free_rate: float) -> float:
    """索提诺比率"""
    if len(daily_returns) < 2:
        return 0.0
    daily_rf = risk_free_rate / TRADING_CONFIG["trading_days_per_year"]
    downside = daily_returns[daily_returns < daily_rf] - daily_rf
    if len(downside) == 0:
        return 0.0
    downside_vol = np.sqrt(np.mean(downside ** 2)) * np.sqrt(TRADING_CONFIG["trading_days_per_year"])
    annual_return = float(np.mean(daily_returns)) * TRADING_CONFIG["trading_days_per_year"]
    if downside_vol <= 0:
        return 0.0
    return (annual_return - risk_free_rate) / downside_vol


def _alpha_beta(navs: list, dates: list, benchmark_data: list,
                risk_free_rate: float) -> tuple:
    """计算 Alpha 和 Beta"""
    # 对齐日期
    bm_dict = {d["date"]: d["nav"] for d in benchmark_data}

    aligned_strategy = []
    aligned_benchmark = []
    for i, date in enumerate(dates):
        if date in bm_dict:
            aligned_strategy.append(navs[i])
            aligned_benchmark.append(bm_dict[date])

    if len(aligned_strategy) < 10:
        return 0, 0

    strat_returns = np.diff(aligned_strategy) / np.array(aligned_strategy[:-1])
    bm_returns = np.diff(aligned_benchmark) / np.array(aligned_benchmark[:-1])

    if len(strat_returns) < 2 or np.var(bm_returns) < 1e-10:
        return 0, 0

    # Beta = Cov(strategy, benchmark) / Var(benchmark)
    beta = float(np.cov(strat_returns, bm_returns)[0, 1] / np.var(bm_returns))

    # Alpha = strategy_return - (rf + beta * (benchmark_return - rf))
    strat_annual = float(np.mean(strat_returns)) * TRADING_CONFIG["trading_days_per_year"]
    bm_annual = float(np.mean(bm_returns)) * TRADING_CONFIG["trading_days_per_year"]
    alpha = strat_annual - (risk_free_rate + beta * (bm_annual - risk_free_rate))

    return alpha, beta


def _trade_statistics(trades: list) -> dict:
    """交易统计"""
    if not trades:
        return {
            "total_trades": 0,
            "buy_trades": 0,
            "sell_trades": 0,
            "win_rate": 0,
            "win_rate_pct": "0.00%",
            "profit_loss_ratio": 0,
            "avg_profit": 0,
            "avg_loss": 0,
        }

    buy_trades = [t for t in trades if t["action"] == "buy"]
    sell_trades = [t for t in trades if t["action"] == "sell"]

    # 计算盈亏
    profits = [t["profit"] for t in sell_trades if t.get("profit") is not None]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p <= 0]

    win_rate = len(wins) / len(profits) if profits else 0
    avg_profit = np.mean(wins) if wins else 0
    avg_loss = abs(np.mean(losses)) if losses else 0
    pl_ratio = avg_profit / avg_loss if avg_loss > 0 else 0

    total_commission = sum(t.get("commission", 0) for t in trades)
    total_tax = sum(t.get("stamp_tax", 0) for t in trades)

    return {
        "total_trades": len(trades),
        "buy_trades": len(buy_trades),
        "sell_trades": len(sell_trades),
        "win_rate": win_rate,
        "win_rate_pct": f"{win_rate:.2%}",
        "profit_loss_ratio": round(pl_ratio, 4),
        "avg_profit": round(float(avg_profit), 2),
        "avg_loss": round(float(avg_loss), 2),
        "total_commission": round(total_commission, 2),
        "total_tax": round(total_tax, 2),
        "total_profit_from_sells": round(sum(profits), 2) if profits else 0,
    }

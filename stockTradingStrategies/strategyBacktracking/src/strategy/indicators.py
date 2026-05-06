"""
技术指标计算器
根据策略需要的指标列表，预计算所有技术指标并附加到DataFrame上
"""
import logging
import re
from typing import List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class IndicatorCalculator:
    """技术指标计算器"""

    # 支持的指标及其参数解析
    INDICATOR_REGISTRY = {
        "MA": {"func": "ma", "params": ["period"]},
        "SMA": {"func": "ma", "params": ["period"]},
        "EMA": {"func": "ema", "params": ["period"]},
        "RSI": {"func": "rsi", "params": ["period"]},
        "MACD": {"func": "macd", "params": ["fast", "slow", "signal"]},
        "BOLL": {"func": "boll", "params": ["period", "std_dev"]},
        "ATR": {"func": "atr", "params": ["period"]},
        "VWAP": {"func": "vwap", "params": []},
        "MAX_HIGH": {"func": "max_high", "params": ["period"]},
        "MIN_LOW": {"func": "min_low", "params": ["period"]},
        "VOL_MA": {"func": "vol_ma", "params": ["period"]},
    }

    def compute_all(self, df: pd.DataFrame, indicators: List[str]) -> pd.DataFrame:
        """
        批量计算指标并附加到DataFrame
        indicators: 如 ["MA(20)", "RSI(14)", "MACD(12,26,9)", "BOLL(20,2)"]
        """
        df = df.copy()

        for indicator_spec in indicators:
            try:
                name, params = self._parse_indicator(indicator_spec)
                if name is None:
                    continue

                reg = self.INDICATOR_REGISTRY.get(name.upper())
                if reg is None:
                    logger.warning(f"不支持的指标: {name}")
                    continue

                func = getattr(self, f"_calc_{reg['func']}")
                df = func(df, **params)
                logger.info(f"计算指标 {indicator_spec} 完成")
            except Exception as e:
                logger.warning(f"计算指标 {indicator_spec} 失败: {e}")

        return df

    @staticmethod
    def _parse_indicator(spec: str) -> tuple:
        """
        解析指标字符串
        "MA(20)" -> ("MA", {"period": 20})
        "MACD(12,26,9)" -> ("MACD", {"fast": 12, "slow": 26, "signal": 9})
        "BOLL(20,2)" -> ("BOLL", {"period": 20, "std_dev": 2})
        """
        match = re.match(r'^(\w+)\(([^)]*)\)$', spec.strip())
        if not match:
            # 无参数指标，如 "close", "volume" 等，不需要计算
            return None, {}

        name = match.group(1)
        param_str = match.group(2).strip()

        if not param_str:
            return name, {}

        raw_params = [p.strip() for p in param_str.split(',')]

        # 根据指标名称映射参数名
        param_names = {
            "MA": ["period"],
            "SMA": ["period"],
            "EMA": ["period"],
            "RSI": ["period"],
            "MACD": ["fast", "slow", "signal"],
            "BOLL": ["period", "std_dev"],
            "ATR": ["period"],
            "MAX_HIGH": ["period"],
            "MIN_LOW": ["period"],
            "VOL_MA": ["period"],
        }

        names = param_names.get(name.upper(), [f"p{i}" for i in range(len(raw_params))])
        params = {}
        for i, val in enumerate(raw_params):
            if i < len(names):
                try:
                    params[names[i]] = float(val) if '.' in val else int(val)
                except ValueError:
                    params[names[i]] = val

        return name, params

    # ────────────────── 指标计算实现 ──────────────────

    @staticmethod
    def _calc_ma(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        col = f"MA{period}"
        df[col] = df['close'].rolling(window=period, min_periods=1).mean()
        return df

    @staticmethod
    def _calc_ema(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        col = f"EMA{period}"
        df[col] = df['close'].ewm(span=period, adjust=False).mean()
        return df

    @staticmethod
    def _calc_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        col = f"RSI{period}"
        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df[col] = 100 - (100 / (1 + rs))
        df[col] = df[col].fillna(50)
        return df

    @staticmethod
    def _calc_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
        ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=signal, adjust=False).mean()
        macd_hist = 2 * (dif - dea)

        df['MACD_DIF'] = dif
        df['MACD_DEA'] = dea
        df['MACD_HIST'] = macd_hist
        return df

    @staticmethod
    def _calc_boll(df: pd.DataFrame, period: int = 20, std_dev: float = 2) -> pd.DataFrame:
        mid = df['close'].rolling(window=period, min_periods=1).mean()
        std = df['close'].rolling(window=period, min_periods=1).std()
        df['BOLL_MID'] = mid
        df['BOLL_UPPER'] = mid + std_dev * std
        df['BOLL_LOWER'] = mid - std_dev * std
        return df

    @staticmethod
    def _calc_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df[f'ATR{period}'] = tr.rolling(window=period, min_periods=1).mean()
        return df

    @staticmethod
    def _calc_vwap(df: pd.DataFrame) -> pd.DataFrame:
        typical = (df['high'] + df['low'] + df['close']) / 3
        cum_vol = df['volume'].cumsum()
        cum_vol_price = (typical * df['volume']).cumsum()
        df['VWAP'] = cum_vol_price / cum_vol.replace(0, np.nan)
        return df

    @staticmethod
    def _calc_max_high(df: pd.DataFrame, period: int = 252) -> pd.DataFrame:
        df[f'MAX_HIGH{period}'] = df['high'].rolling(window=period, min_periods=1).max()
        return df

    @staticmethod
    def _calc_min_low(df: pd.DataFrame, period: int = 252) -> pd.DataFrame:
        df[f'MIN_LOW{period}'] = df['low'].rolling(window=period, min_periods=1).min()
        return df

    @staticmethod
    def _calc_vol_ma(df: pd.DataFrame, period: int = 5) -> pd.DataFrame:
        df[f'VOL_MA{period}'] = df['volume'].rolling(window=period, min_periods=1).mean()
        return df

"""
数据获取模块
复用 yupen 项目的 akshare 数据源方案，支持多市场多数据源自动降级
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

import akshare as ak
import numpy as np
import pandas as pd

from src.config import NAME_TO_CODE
from src.data.cache import DataCache

logger = logging.getLogger(__name__)


class DataFetcher:
    """统一数据获取器，支持 A股指数/个股/ETF、美股、港股等"""

    def __init__(self):
        self.cache = DataCache()

    def resolve_symbol(self, symbol: str) -> dict:
        """
        解析用户输入的标的代码或名称
        支持格式: "000300", "sh000300", "沪深300", "510300"
        返回: {"code": str, "market": str, "name": str}
        """
        symbol = symbol.strip()

        # 先尝试名称映射
        if symbol in NAME_TO_CODE:
            info = NAME_TO_CODE[symbol]
            return {"code": info["code"], "market": info["market"], "name": symbol}

        # 尝试解析 "sh000300" 这种带前缀的格式
        if symbol[:2] in ("sh", "sz") and len(symbol) > 2:
            market = symbol[:2]
            code = symbol[2:]
            return {"code": code, "market": market, "name": symbol}

        # 纯数字代码，自动判断市场
        code = symbol
        if code.startswith("6") or code.startswith("5"):
            # 6开头=沪市个股, 5开头=沪市ETF/基金
            market = "sh"
        elif code.startswith("0") or code.startswith("3") or code.startswith("1"):
            # 0开头=深市主板, 3开头=创业板, 159xxx=深市ETF
            if len(code) == 6 and code.startswith("159"):
                market = "sz"
            elif code.startswith("0") or code.startswith("3"):
                market = "stock"  # 个股
            else:
                market = "sz"
        elif code.startswith("."):
            market = "us"
        elif code.isalpha():
            market = "hk"
        else:
            market = "sh"  # 默认沪市

        return {"code": code, "market": market, "name": symbol}

    def fetch(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取标的行情数据
        symbol: 代码或名称
        start_date/end_date: YYYY-MM-DD 格式
        返回: DataFrame[date, open, high, low, close, volume]
        """
        info = self.resolve_symbol(symbol)
        code = info["code"]
        market = info["market"]

        # 先尝试从缓存读取
        cached = self.cache.get(code, market, start_date, end_date)
        if cached is not None:
            return cached

        # 计算需要获取的天数范围（多取一些确保覆盖）
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        days = (end_dt - start_dt).days + 60  # 多取60天确保均线等指标有前置数据
        fetch_start = start_dt - timedelta(days=max(days, 120))

        # 按市场类型选择数据源
        df = self._fetch_by_market(code, market, fetch_start, end_dt)
        if df is None or len(df) == 0:
            raise ValueError(f"无法获取 {symbol} 的数据，所有数据源均失败")

        # 统一列名
        df = self._normalize_columns(df)

        # 保存到缓存
        self.cache.save(code, market, df)

        # 截取所需区间
        df = df[df['date'] >= pd.Timestamp(start_date)]
        df = df.reset_index(drop=True)

        logger.info(f"获取 {symbol} 数据成功: {len(df)} 条, {df['date'].min()} ~ {df['date'].max()}")
        return df

    def _fetch_by_market(self, code: str, market: str,
                         start_dt: datetime, end_dt: datetime) -> Optional[pd.DataFrame]:
        """按市场类型选择数据源优先级"""
        if market == "stock":
            return self._try_sources(code, market, [
                ("akshare个股", self._fetch_stock),
            ], start_dt, end_dt)
        elif market == "us":
            return self._try_sources(code, market, [
                ("新浪美股", self._fetch_us_index),
            ], start_dt, end_dt)
        elif market == "hk":
            return self._try_sources(code, market, [
                ("新浪港股", self._fetch_hk_sina),
                ("东方财富港股", self._fetch_hk_em),
            ], start_dt, end_dt)
        else:  # sh, sz - 指数
            return self._try_sources(code, market, [
                ("东方财富", self._fetch_eastmoney_index),
                ("中证CSIndex", self._fetch_csindex),
                ("新浪财经", self._fetch_sina),
                ("腾讯财经", self._fetch_tencent),
            ], start_dt, end_dt)

    def _try_sources(self, code: str, market: str, sources: list,
                     start_dt: datetime, end_dt: datetime) -> Optional[pd.DataFrame]:
        """依次尝试多个数据源"""
        for source_name, fetch_func in sources:
            try:
                logger.info(f"尝试从 {source_name} 获取 {code}...")
                df = fetch_func(code, market, start_dt, end_dt)
                if df is not None and len(df) > 0:
                    logger.info(f"{source_name} 获取 {code} 成功: {len(df)} 条")
                    return df
            except Exception as e:
                logger.warning(f"{source_name} 获取 {code} 失败: {e}")
                continue
        return None

    # ────────────────── 各数据源实现 ──────────────────

    def _fetch_eastmoney_index(self, code: str, market: str,
                               start_dt: datetime, end_dt: datetime) -> Optional[pd.DataFrame]:
        """东方财富 - A股指数/ETF"""
        df = ak.index_zh_a_hist(
            symbol=code,
            period='daily',
            start_date=start_dt.strftime('%Y%m%d'),
            end_date=end_dt.strftime('%Y%m%d')
        )
        if df is None or len(df) == 0:
            return None
        col_map = {
            '日期': 'date', '开盘': 'open', '最高': 'high',
            '最低': 'low', '收盘': 'close', '成交量': 'volume',
        }
        df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        return df

    def _fetch_csindex(self, code: str, market: str,
                       start_dt: datetime, end_dt: datetime) -> Optional[pd.DataFrame]:
        """中证指数公司"""
        try:
            df = ak.stock_zh_index_hist_csindex(
                symbol=code,
                start_date=start_dt.strftime('%Y%m%d'),
                end_date=end_dt.strftime('%Y%m%d')
            )
            if df is None or len(df) == 0:
                return None
            col_map = {
                '日期': 'date', '开盘': 'open', '最高': 'high',
                '最低': 'low', '收盘': 'close', '成交量': 'volume',
            }
            df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)
            return df
        except Exception:
            return None

    def _fetch_sina(self, code: str, market: str,
                    start_dt: datetime, end_dt: datetime) -> Optional[pd.DataFrame]:
        """新浪财经 - A股指数"""
        symbol = f"{market}{code}"
        df = ak.stock_zh_index_daily(symbol=symbol)
        if df is None or len(df) == 0:
            return None
        if 'date' not in df.columns:
            if '日期' in df.columns:
                df.rename(columns={'日期': 'date'}, inplace=True)
            else:
                return None
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        return df

    def _fetch_tencent(self, code: str, market: str,
                       start_dt: datetime, end_dt: datetime) -> Optional[pd.DataFrame]:
        """腾讯财经 - A股指数"""
        symbol = f"{market}{code}"
        df = ak.stock_zh_index_daily_tx(symbol=symbol)
        if df is None or len(df) == 0:
            return None
        if 'date' not in df.columns:
            if '日期' in df.columns:
                df.rename(columns={'日期': 'date'}, inplace=True)
            else:
                return None
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        return df

    def _fetch_stock(self, code: str, market: str,
                     start_dt: datetime, end_dt: datetime) -> Optional[pd.DataFrame]:
        """akshare - A股个股（前复权）"""
        prefix = "sh" if code.startswith("6") else "sz"
        symbol = f"{prefix}{code}"
        df = ak.stock_zh_a_daily(symbol=symbol, adjust="qfq",
                                  start_date=start_dt.strftime('%Y%m%d'),
                                  end_date=end_dt.strftime('%Y%m%d'))
        if df is None or len(df) == 0:
            return None
        if 'date' not in df.columns:
            if '日期' in df.columns:
                df.rename(columns={'日期': 'date'}, inplace=True)
            else:
                return None
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        return df

    def _fetch_us_index(self, code: str, market: str,
                        start_dt: datetime, end_dt: datetime) -> Optional[pd.DataFrame]:
        """新浪美股指数"""
        df = ak.index_us_stock_sina(symbol=code)
        if df is None or len(df) == 0:
            return None
        if 'date' not in df.columns:
            return None
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        return df

    def _fetch_hk_sina(self, code: str, market: str,
                       start_dt: datetime, end_dt: datetime) -> Optional[pd.DataFrame]:
        """新浪港股指数"""
        df = ak.stock_hk_index_daily_sina(symbol=code)
        if df is None or len(df) == 0:
            return None
        if 'date' not in df.columns:
            return None
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        return df

    def _fetch_hk_em(self, code: str, market: str,
                     start_dt: datetime, end_dt: datetime) -> Optional[pd.DataFrame]:
        """东方财富港股指数"""
        df = ak.stock_hk_index_daily_em(symbol=code)
        if df is None or len(df) == 0:
            return None
        col_map = {
            '日期': 'date', '今开': 'open', '开盘': 'open',
            '最新价': 'close', '收盘': 'close',
            '最高': 'high', '最低': 'low', '成交量': 'volume',
        }
        df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)
        if 'date' not in df.columns:
            return None
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        return df

    # ────────────────── 工具方法 ──────────────────

    @staticmethod
    def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        """统一列名和数据类型"""
        required = ['date', 'open', 'high', 'low', 'close', 'volume']
        for col in required:
            if col not in df.columns:
                raise ValueError(f"缺少必要列: {col}")

        df['date'] = pd.to_datetime(df['date'])
        for col in ['open', 'high', 'low', 'close']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')

        df = df.dropna(subset=['close']).reset_index(drop=True)
        return df[required]

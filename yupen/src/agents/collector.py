"""
数据采集Agent
负责从数据源获取股票/指数数据，支持多数据源备用
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import os
import akshare as ak

import requests

from .base import BaseAgent
from config import PE_INDEX_MAP

logger = logging.getLogger(__name__)

_DANJUAN_PE_CACHE = None
_DANJUAN_PE_CACHE_TIME = None

def _fetch_danjuan_pe_data() -> Optional[Dict[str, Dict]]:
    global _DANJUAN_PE_CACHE, _DANJUAN_PE_CACHE_TIME
    
    now = datetime.now()
    if _DANJUAN_PE_CACHE and _DANJUAN_PE_CACHE_TIME:
        if (now - _DANJUAN_PE_CACHE_TIME).total_seconds() < 3600:
            return _DANJUAN_PE_CACHE
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        url = 'https://danjuanapp.com/djapi/index_eva/dj'
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        
        result = {}
        for item in data['data']['items']:
            name = item.get('name', '')
            pe = item.get('pe', 0)
            pe_percentile = item.get('pe_percentile', 0)
            pb = item.get('pb', 0)
            pb_percentile = item.get('pb_percentile', 0)
            
            if pe_percentile <= 1:
                pe_percentile = pe_percentile * 100
            if pb_percentile <= 1:
                pb_percentile = pb_percentile * 100
            
            result[name] = {
                'PE': round(pe, 2) if pe else None,
                'PE百分位': round(pe_percentile, 2) if pe_percentile else None,
                'PB': round(pb, 2) if pb else None,
                'PB百分位': round(pb_percentile, 2) if pb_percentile else None,
            }
        
        _DANJUAN_PE_CACHE = result
        _DANJUAN_PE_CACHE_TIME = now
        return result
    except Exception as e:
        logger.warning(f"获取蛋卷基金PE数据失败: {e}")
        return None


def fetch_pe_percentile(index_name: str) -> Optional[Dict[str, Any]]:
    if index_name not in PE_INDEX_MAP:
        return None
    
    danjuan_name = PE_INDEX_MAP[index_name]
    
    pe_data = _fetch_danjuan_pe_data()
    if not pe_data:
        return None
    
    if danjuan_name not in pe_data:
        logger.warning(f"蛋卷基金没有 {danjuan_name} 的PE数据")
        return None
    
    result = pe_data[danjuan_name]
    if result.get('PE') is None:
        return None
    
    return {
        "PE": result['PE'],
        "PE百分位": result['PE百分位'],
        "PB": result.get('PB'),
        "PB百分位": result.get('PB百分位'),
        "PE日期": datetime.now().strftime("%Y-%m-%d")
    }


class DataSourceManager:
    def __init__(self):
        self.sources_tried = {}

    def fetch_index_data(self, code: str, market: str, days: int) -> Optional[Dict]:
        if market == "us":
            sources = [("新浪美股指数", self._fetch_from_us_index)]
        elif market == "jp":
            sources = [("新浪全球指数", self._fetch_from_jp_index)]
        elif market == "hk":
            sources = [
                ("东方财富港股指数", self._fetch_from_hk_index_em),
                ("新浪港股指数", self._fetch_from_hk_index_sina),
            ]
        elif market == "metal":
            sources = [("外盘商品期货", self._fetch_from_metal)]
        else:
            sources = [
                ("新浪财经", self._fetch_from_sina),
                ("中证CSIndex", self._fetch_from_csindex),
                ("Baostock", self._fetch_from_baostock),
                ("东方财富", self._fetch_from_eastmoney),
                ("腾讯财经", self._fetch_from_tencent),
            ]

        for source_name, fetch_func in sources:
            try:
                logger.info(f"尝试从 {source_name} 获取 {code} 数据...")
                result = fetch_func(code, market, days)

                if result is not None and len(result.get('data', pd.DataFrame())) > 0:
                    result['数据源'] = source_name
                    result['采集时间'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                    if len(result['data']) > 0 and 'date' in result['data'].columns:
                        latest_date = result['data']['date'].max()
                        result['数据日期'] = latest_date.strftime('%Y-%m-%d') if hasattr(latest_date, 'strftime') else str(latest_date)
                    else:
                        result['数据日期'] = 'N/A'

                    logger.info(f"{source_name} 获取成功: {code}, 数据日期: {result['数据日期']}")
                    return result

            except Exception as e:
                logger.warning(f"{source_name} 获取 {code} 失败: {e}")
                continue

        logger.error(f"所有数据源都无法获取 {code} 数据")
        return None

    def _fetch_from_sina(self, code: str, market: str, days: int) -> Optional[Dict]:
        import akshare as ak

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
        return {'data': df, 'symbol': symbol}

    def _fetch_from_baostock(self, code: str, market: str, days: int) -> Optional[Dict]:
        import baostock as bs

        lg = bs.login()
        if lg.error_code != '0':
            return None

        try:
            bs_market = "sh" if market == "sh" else "sz"
            bs_code = f"{bs_market}.{code}"
            rs = bs.query_history_k_data_plus(
                bs_code,
                'date,open,high,low,close,volume',
                start_date=(datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d'),
                end_date=datetime.now().strftime('%Y-%m-%d'),
                frequency='d'
            )

            if rs.error_code != '0':
                return None

            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())

            if len(data_list) == 0:
                return None

            df = pd.DataFrame(data_list, columns=rs.fields)
            df['date'] = pd.to_datetime(df['date'])
            df['open'] = pd.to_numeric(df['open'], errors='coerce')
            df['high'] = pd.to_numeric(df['high'], errors='coerce')
            df['low'] = pd.to_numeric(df['low'], errors='coerce')
            df['close'] = pd.to_numeric(df['close'], errors='coerce')
            df['volume'] = pd.to_numeric(df['volume'], errors='coerce')

            return {'data': df, 'symbol': bs_code}
        finally:
            bs.logout()

    def _fetch_from_eastmoney(self, code: str, market: str, days: int) -> Optional[Dict]:
        import akshare as ak

        symbol = code
        df = ak.index_zh_a_hist(symbol=symbol, period='daily',
                                 start_date=(datetime.now() - timedelta(days=days*2)).strftime('%Y%m%d'),
                                 end_date=datetime.now().strftime('%Y%m%d'))

        if df is None or len(df) == 0:
            return None

        if '日期' in df.columns:
            df.rename(columns={'日期': 'date'}, inplace=True)
        elif 'date' not in df.columns:
            return None

        df['date'] = pd.to_datetime(df['date'])

        if '开盘' in df.columns:
            df.rename(columns={'开盘': 'open'}, inplace=True)
        if '最高' in df.columns:
            df.rename(columns={'最高': 'high'}, inplace=True)
        if '最低' in df.columns:
            df.rename(columns={'最低': 'low'}, inplace=True)
        if '收盘' in df.columns:
            df.rename(columns={'收盘': 'close'}, inplace=True)
        if '成交量' in df.columns:
            df.rename(columns={'成交量': 'volume'}, inplace=True)

        return {'data': df, 'symbol': symbol}

    def _fetch_from_tencent(self, code: str, market: str, days: int) -> Optional[Dict]:
        import akshare as ak

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
        return {'data': df, 'symbol': symbol}

    def _fetch_from_csindex(self, code: str, market: str, days: int) -> Optional[Dict]:
        import akshare as ak

        try:
            df = ak.stock_zh_index_hist_csindex(
                symbol=code,
                start_date=(datetime.now() - timedelta(days=days)).strftime('%Y%m%d'),
                end_date=datetime.now().strftime('%Y%m%d')
            )

            if df is None or len(df) == 0:
                return None

            if '日期' in df.columns:
                df.rename(columns={'日期': 'date'}, inplace=True)
            elif 'date' not in df.columns:
                return None

            df['date'] = pd.to_datetime(df['date'])

            if '开盘' in df.columns:
                df.rename(columns={'开盘': 'open'}, inplace=True)
            if '最高' in df.columns:
                df.rename(columns={'最高': 'high'}, inplace=True)
            if '最低' in df.columns:
                df.rename(columns={'最低': 'low'}, inplace=True)
            if '收盘' in df.columns:
                df.rename(columns={'收盘': 'close'}, inplace=True)
            if '成交量' in df.columns:
                df.rename(columns={'成交量': 'volume'}, inplace=True)

            return {'data': df, 'symbol': code}
        except Exception as e:
            logger.warning(f"中证CSIndex 获取 {code} 失败: {e}")
            return None

    def _fetch_from_us_index(self, code: str, market: str, days: int) -> Optional[Dict]:
        import akshare as ak

        try:
            df = ak.index_us_stock_sina(symbol=code)

            if df is None or len(df) == 0:
                return None

            if 'date' not in df.columns:
                return None

            df['date'] = pd.to_datetime(df['date'])

            if 'date' in df.columns and len(df) > days:
                df = df.tail(days)

            return {'data': df, 'symbol': code}
        except Exception as e:
            logger.warning(f"新浪美股指数 获取 {code} 失败: {e}")
            return None

    def _fetch_from_metal(self, code: str, market: str, days: int) -> Optional[Dict]:
        import akshare as ak

        try:
            df = ak.futures_foreign_hist(symbol=code)

            if df is None or len(df) == 0:
                return None

            if 'date' not in df.columns:
                return None

            df['date'] = pd.to_datetime(df['date'])

            if 'date' in df.columns and len(df) > days:
                df = df.tail(days)

            return {'data': df, 'symbol': code}
        except Exception as e:
            logger.warning(f"外盘商品期货 获取 {code} 失败: {e}")
            return None

    # 新浪全球指数的中文名称映射（code → akshare symbol）
    _JP_CODE_TO_SINA_SYMBOL = {
        "N225": "日经225指数",
    }

    def _fetch_from_jp_index(self, code: str, market: str, days: int) -> Optional[Dict]:
        import akshare as ak

        try:
            sina_symbol = self._JP_CODE_TO_SINA_SYMBOL.get(code, code)
            df = ak.index_global_hist_sina(symbol=sina_symbol)

            if df is None or len(df) == 0:
                return None

            col_map = {
                '日期': 'date',
                '今开': 'open',
                '最新价': 'close',
                '最高': 'high',
                '最低': 'low',
                '开盘': 'open',
                '收盘': 'close',
                '成交量': 'volume',
            }
            df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)

            if 'date' not in df.columns:
                return None

            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)

            if len(df) > days:
                df = df.tail(days)

            return {'data': df, 'symbol': code}
        except Exception as e:
            logger.warning(f"东方财富日本指数 获取 {code} 失败: {e}")
            return None

    def _fetch_from_hk_index_em(self, code: str, market: str, days: int) -> Optional[Dict]:
        import akshare as ak

        try:
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

            if len(df) > days:
                df = df.tail(days)

            return {'data': df, 'symbol': code}
        except Exception as e:
            logger.warning(f"东方财富港股指数 获取 {code} 失败: {e}")
            return None

    def _fetch_from_hk_index_sina(self, code: str, market: str, days: int) -> Optional[Dict]:
        import akshare as ak

        try:
            df = ak.stock_hk_index_daily_sina(symbol=code)

            if df is None or len(df) == 0:
                return None

            if 'date' not in df.columns:
                return None

            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)

            if len(df) > days:
                df = df.tail(days)

            return {'data': df, 'symbol': code}
        except Exception as e:
            logger.warning(f"新浪港股指数 获取 {code} 失败: {e}")
            return None


class DataCollectorAgent(BaseAgent):
    def __init__(self):
        super().__init__("DataCollectorAgent")
        self.data_source_manager = DataSourceManager()

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.log_info("开始采集指数数据...")

        indices = context.get("indices", [])
        days = context.get("lookback_days", 60)

        all_data = {}
        failed_indices = []
        successful_count = 0

        for index_info in indices:
            name = index_info["name"]
            code = index_info["code"]
            market = index_info["market"]

            self.log_info(f"正在采集 {name} ({code}) 数据...")

            result = self.data_source_manager.fetch_index_data(code, market, days)

            if result is not None and result.get('data') is not None and len(result['data']) > 0:
                all_data[name] = {
                    "code": code,
                    "market": market,
                    "data": result['data'],
                    "数据源": result.get('数据源', '未知'),
                    "数据日期": result.get('数据日期', 'N/A'),
                    "采集时间": result.get('采集时间', 'N/A')
                }
                
                pe_data = fetch_pe_percentile(name)
                if pe_data:
                    all_data[name]["PE"] = pe_data.get("PE")
                    all_data[name]["PE百分位"] = pe_data.get("PE百分位")
                    all_data[name]["PE日期"] = pe_data.get("PE日期")
                
                successful_count += 1
                self.log_info(f"{name} 数据采集成功 (数据源: {result.get('数据源', '未知')}, 数据日期: {result.get('数据日期', 'N/A')})")
            else:
                self.log_error(f"{name} 数据采集失败")
                failed_indices.append(name)
                all_data[name] = {
                    "code": code,
                    "market": market,
                    "data": None,
                    "数据源": "获取失败",
                    "数据日期": "N/A",
                    "采集时间": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }

        result = {
            "status": "partial_success" if successful_count > 0 else "failed",
            "collected_indices": list(all_data.keys()),
            "successful_indices": [k for k, v in all_data.items() if v["data"] is not None],
            "failed_indices": failed_indices,
            "successful_count": successful_count,
            "total_count": len(indices),
            "data": all_data,
            "timestamp": datetime.now().isoformat()
        }

        return result

    def _fetch_index_data(self, code: str, market: str, days: int):
        pass
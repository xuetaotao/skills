"""
数据分析Agent
负责计算均线、偏离度、趋势强度等指标
"""

from typing import Dict, Any, List
import pandas as pd
import numpy as np
from datetime import datetime

from .base import BaseAgent


class DataAnalyzerAgent(BaseAgent):
    def __init__(self):
        super().__init__("DataAnalyzerAgent")

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.log_info("开始分析指数数据...")

        raw_data = context.get("raw_data", {})
        ma_period = context.get("ma_period", 20)

        analyzed_results = {}

        for index_name, index_data in raw_data.items():
            self.log_info(f"正在分析 {index_name}...")

            df = index_data.get("data")
            if df is None or len(df) == 0:
                self.log_warning(f"{index_name} 数据为空/无效，跳过详细分析")
                analyzed_results[index_name] = {
                    "name": index_name,
                    "code": index_data.get("code"),
                    "当前价格": None,
                    "MA20": None,
                    "偏离度": None,
                    "偏离度百分比": "N/A",
                    "状态": None,
                    "状态开始日期": None,
                    "趋势强度": None,
                    "数据状态": "获取失败",
                    "数据源": index_data.get("数据源", "获取失败"),
                    "数据日期": index_data.get("数据日期", "N/A"),
                    "采集时间": index_data.get("采集时间", "N/A")
                }
                continue

            analysis = self._analyze_index(df, ma_period)
            analysis["name"] = index_name
            analysis["code"] = index_data.get("code")
            analysis["数据状态"] = "成功"
            analysis["数据源"] = index_data.get("数据源", "未知")
            analysis["数据日期"] = index_data.get("数据日期", "N/A")
            analysis["采集时间"] = index_data.get("采集时间", "N/A")
            
            if index_data.get("PE"):
                analysis["PE"] = index_data.get("PE")
                analysis["PE百分位"] = index_data.get("PE百分位")
                analysis["PE日期"] = index_data.get("PE日期")

            analyzed_results[index_name] = analysis

        result = {
            "status": "success",
            "analyzed_data": analyzed_results,
            "timestamp": datetime.now().isoformat()
        }

        self.log_info(f"分析完成，共处理 {len(analyzed_results)} 个指数")
        return result

    def _analyze_index(self, df: pd.DataFrame, ma_period: int) -> Dict[str, Any]:
        if 'close' not in df.columns:
            if 'Close' in df.columns:
                df = df.rename(columns={'Close': 'close'})
            else:
                return self._empty_analysis()

        df = df.copy()
        df['ma'] = df['close'].rolling(window=ma_period).mean()

        latest = df.iloc[-1]
        ma_value = latest['ma']
        close_price = latest['close']

        偏离度 = (close_price - ma_value) / ma_value if ma_value > 0 else 0

        df['偏离度'] = (df['close'] - df['ma']) / df['ma']

        status = "YES" if close_price > ma_value else "NO"

        status_start_date = self._find_status_change_date(df, 'close', 'ma')

        return {
            "当前价格": close_price,
            "MA20": ma_value,
            "偏离度": 偏离度,
            "偏离度百分比": f"{偏离度 * 100:.2f}%",
            "状态": status,
            "状态开始日期": status_start_date,
            "趋势强度": 0,
            "历史数据": df.tail(20).to_dict('records')
        }

    def _find_status_change_date(self, df: pd.DataFrame, price_col: str, ma_col: str) -> str:
        if len(df) < 2:
            return datetime.now().strftime('%Y-%m-%d')

        latest_status = df.iloc[-1][price_col] > df.iloc[-1][ma_col]

        for i in range(len(df) - 2, -1, -1):
            current_status = df.iloc[i][price_col] > df.iloc[i][ma_col]
            if current_status != latest_status:
                return df.iloc[i + 1]['date'] if 'date' in df.columns else datetime.now().strftime('%Y-%m-%d')

        return df.iloc[0]['date'] if 'date' in df.columns else datetime.now().strftime('%Y-%m-%d')

    def _empty_analysis(self) -> Dict[str, Any]:
        return {
            "当前价格": 0,
            "MA20": 0,
            "偏离度": 0,
            "偏离度百分比": "0.00%",
            "状态": "NO",
            "状态开始日期": datetime.now().strftime('%Y-%m-%d'),
            "趋势强度": 0,
            "历史数据": []
        }
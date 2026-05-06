"""
数据缓存管理
将获取的行情数据缓存到本地CSV，避免重复请求
"""
import os
import pandas as pd
import logging
from datetime import datetime, timedelta
from src.config import CACHE_DIR, CACHE_EXPIRE_SECONDS

logger = logging.getLogger(__name__)


class DataCache:
    """本地CSV缓存管理器"""

    def __init__(self, cache_dir: str = None):
        self.cache_dir = cache_dir or CACHE_DIR
        os.makedirs(self.cache_dir, exist_ok=True)

    def _get_cache_path(self, code: str, market: str) -> str:
        filename = f"{market}_{code}.csv"
        return os.path.join(self.cache_dir, filename)

    def get(self, code: str, market: str, start_date: str = None,
            end_date: str = None) -> pd.DataFrame | None:
        """
        从缓存读取数据，如果缓存存在且未过期则返回数据
        start_date/end_date 用于截取所需区间
        """
        cache_path = self._get_cache_path(code, market)

        if not os.path.exists(cache_path):
            return None

        # 检查缓存文件是否过期
        file_mtime = datetime.fromtimestamp(os.path.getmtime(cache_path))
        if datetime.now() - file_mtime > timedelta(seconds=CACHE_EXPIRE_SECONDS):
            logger.info(f"缓存已过期: {cache_path}")
            return None

        try:
            df = pd.read_csv(cache_path, parse_dates=['date'])
            df = df.sort_values('date').reset_index(drop=True)

            if start_date:
                df = df[df['date'] >= pd.Timestamp(start_date)]
            if end_date:
                df = df[df['date'] <= pd.Timestamp(end_date)]

            if len(df) == 0:
                return None

            logger.info(f"从缓存读取 {market}:{code} 数据，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.warning(f"读取缓存失败: {cache_path}, {e}")
            return None

    def save(self, code: str, market: str, df: pd.DataFrame) -> None:
        """保存数据到缓存"""
        if df is None or len(df) == 0:
            return

        cache_path = self._get_cache_path(code, market)
        try:
            # 合并已有缓存（去重）
            existing = None
            if os.path.exists(cache_path):
                existing = pd.read_csv(cache_path, parse_dates=['date'])

            if existing is not None and len(existing) > 0:
                combined = pd.concat([existing, df], ignore_index=True)
                combined = combined.drop_duplicates(subset=['date'], keep='last')
                combined = combined.sort_values('date').reset_index(drop=True)
            else:
                combined = df

            combined.to_csv(cache_path, index=False)
            logger.info(f"缓存已保存: {cache_path}, 共 {len(combined)} 条")
        except Exception as e:
            logger.warning(f"保存缓存失败: {cache_path}, {e}")

    def clear(self, code: str = None, market: str = None) -> None:
        """清除缓存"""
        if code and market:
            cache_path = self._get_cache_path(code, market)
            if os.path.exists(cache_path):
                os.remove(cache_path)
        else:
            for f in os.listdir(self.cache_dir):
                if f.endswith('.csv'):
                    os.remove(os.path.join(self.cache_dir, f))

"""宏观数据：美元指数 + 中美国债收益率

这两类数据不走 yupen 的指数 pipeline，直接在本模块取数（汇率/利率不适合套鱼盆信号）：
  - 美元指数（DXY）：新浪 DINIW 为主、东财 secid 100.UDI 回退；只取当日现价 + 涨跌幅。
  - 中美国债收益率：akshare bond_zh_us_rate；按期限列出当日中/美收益率与中美利差。
"""

import logging
import time
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

_BOND_TERMS = ["2年", "5年", "10年", "30年"]
_HTTP_RETRIES = 4


# ----------------------------- 美元指数 ----------------------------- #

_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}


def _fetch_dxy_sina() -> Optional[pd.DataFrame]:
    """新浪美元指数日线（DINIW），返回 date/open/high/low/close。字段序：日期,开,低,高,收。"""
    url = ("https://vip.stock.finance.sina.com.cn/forex/api/jsonp.php/"
           "var%20_=/NewForexService.getDayKLine?symbol=DINIW")
    resp = requests.get(url, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    text = resp.text
    marker = text.find("var _=(")
    if marker < 0:
        return None
    payload = text[marker + 7:].strip().rstrip(");").strip().strip('"')
    rows = []
    for record in payload.split("|"):
        parts = record.split(",")
        if len(parts) < 5:
            continue
        rows.append({
            "date": parts[0],
            "open": float(parts[1]),
            "low": float(parts[2]),
            "high": float(parts[3]),
            "close": float(parts[4]),
        })
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def _fetch_dxy_eastmoney() -> Optional[pd.DataFrame]:
    """东财美元指数日线（secid 100.UDI），字段序：日期,开,收,高,低。"""
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": "100.UDI",
        "fields1": "f1,f2,f3,f4,f5",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
        "klt": "101", "fqt": "0", "beg": "20240101", "end": "20500101", "lmt": "1000",
    }
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    resp.raise_for_status()
    klines = resp.json().get("data", {}).get("klines", [])
    if not klines:
        return None
    rows = []
    for line in klines:
        parts = line.split(",")
        rows.append({
            "date": parts[0], "open": float(parts[1]), "close": float(parts[2]),
            "high": float(parts[3]), "low": float(parts[4]),
        })
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def _fetch_usd_index_df() -> Optional[pd.DataFrame]:
    """美元指数日线：优先新浪（稳定），失败回退东财。各源带重试。"""
    for source_name, fetch in (("新浪", _fetch_dxy_sina), ("东财", _fetch_dxy_eastmoney)):
        last_error: Optional[Exception] = None
        for attempt in range(_HTTP_RETRIES):
            try:
                df = fetch()
                if df is not None and len(df) > 0:
                    return df
                last_error = ValueError("空数据")
            except Exception as error:  # noqa: BLE001
                last_error = error
                time.sleep(1.0 * (attempt + 1))
        logger.warning("美元指数·%s源获取失败（重试 %d 次）: %s", source_name, _HTTP_RETRIES, last_error)
    return None


def fetch_usd_index() -> Optional[Dict[str, Any]]:
    """返回美元指数当日快照（现价 + 较前一交易日涨跌幅），失败返回 None。"""
    df = _fetch_usd_index_df()
    if df is None or len(df) == 0:
        return None

    latest = df.iloc[-1]
    close = float(latest["close"])

    change = None
    if len(df) >= 2:
        prev_close = float(df.iloc[-2]["close"])
        if prev_close > 0:
            change = (close - prev_close) / prev_close

    return {
        "name": "美元指数",
        "code": "DXY",
        "price": close,
        "change": change,
        "data_date": latest["date"].strftime("%Y-%m-%d"),
    }


# ----------------------------- 中美国债收益率 ----------------------------- #

def _safe(value: Any) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    return float(value)


def fetch_bond_yields() -> Optional[Dict[str, Any]]:
    """返回中美国债收益率面板，失败返回 None。

    结构：{"data_date": str, "rows": [{term, cn, us, spread, cn_bp, us_bp}, ...]}
    收益率单位为百分比；cn_bp/us_bp 为较前一交易日变化（基点）。
    """
    try:
        import akshare as ak

        df = ak.bond_zh_us_rate(start_date="20260101")
    except Exception as error:  # noqa: BLE001
        logger.warning("中美国债收益率获取失败: %s", error)
        return None

    if df is None or len(df) == 0:
        return None

    df = df.dropna(subset=["中国国债收益率10年", "美国国债收益率10年"]).reset_index(drop=True)
    if df.empty:
        return None

    latest = df.iloc[-1]

    rows: List[Dict[str, Any]] = []
    for term in _BOND_TERMS:
        rows.append({
            "term": term,
            "cn": _safe(latest.get(f"中国国债收益率{term}")),
            "us": _safe(latest.get(f"美国国债收益率{term}")),
        })

    return {"data_date": str(latest["日期"])[:10], "rows": rows}

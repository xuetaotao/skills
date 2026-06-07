"""汇总分组与排序

把扁平行情记录拆成两组：
  - 全球股市（A股宽基 / 美股 / 日经 / 韩国 / 台湾 / 印度 / 英国 / 德国 / 港股）
  - 大宗商品（黄金 / 白银 / 铜 / 原油）
各组内部按偏离度从高到低排序并赋予排名。窄基、个股不纳入。
"""

from typing import Any, Dict, List, Tuple

# 纳入"全球股市"表的 market 及其展示（地区名, 国旗代码）
STOCK_MARKET_DISPLAY: Dict[str, Tuple[str, str]] = {
    "sh": ("A股", "cn"),
    "sz": ("A股", "cn"),
    "us": ("美股", "us"),
    "jp": ("日经", "jp"),
    "kr": ("韩国", "kr"),
    "tw": ("台湾", "tw"),
    "in": ("印度", "in"),
    "uk": ("英国", "uk"),
    "de": ("德国", "de"),
    "hk": ("港股", "hk"),
}

# 纳入"大宗商品"表的 market
COMMODITY_MARKETS = {"metal"}

# 显式排除：窄基行业、A股个股
EXCLUDED_MARKETS = {"narrow", "stock"}


def _deviation_key(record: Dict[str, Any]) -> float:
    value = record.get("deviation")
    return value if isinstance(value, (int, float)) else float("-inf")


def rank(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按偏离度由强到弱排序，并重新赋予 1..N 排名。

    返回独立副本，避免完整版/精简版共享同一记录对象时排名互相覆盖。
    """
    ordered = sorted(records, key=_deviation_key, reverse=True)
    result: List[Dict[str, Any]] = []
    for index, record in enumerate(ordered, start=1):
        item = dict(record)
        item["rank"] = index
        result.append(item)
    return result


def split_groups(records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """按市场拆成 (全球股市, 大宗商品)，附加地区/国旗，未排序未过滤。"""
    stocks: List[Dict[str, Any]] = []
    commodities: List[Dict[str, Any]] = []

    for record in records:
        market = record.get("market")
        if market in EXCLUDED_MARKETS:
            continue
        if market in STOCK_MARKET_DISPLAY:
            region, flag = STOCK_MARKET_DISPLAY[market]
            record["region"] = region
            record["flag"] = flag
            stocks.append(record)
        elif market in COMMODITY_MARKETS:
            commodities.append(record)

    return stocks, commodities


def filter_for_version(records: List[Dict[str, Any]], display_map: Dict[str, Dict[str, bool]],
                       version_key: str, default: bool) -> List[Dict[str, Any]]:
    """按 watchlist 里某个版本（完整版/精简版）的开关过滤。

    display_map: {名称: {"完整版": bool, "精简版": bool}}
    未列出的标的用 default 决定是否显示。
    """
    result: List[Dict[str, Any]] = []
    for record in records:
        config = display_map.get(record["name"])
        show = config.get(version_key, default) if config else default
        if show:
            result.append(record)
    return result

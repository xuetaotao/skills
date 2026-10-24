# -*- coding: utf-8 -*-
"""数据抓取层：把各数据源统一规整成 [(date, value)]（日期升序、同日去重）。

每个数据源都显式指定日期列和数值列。接口改版导致列名变化时直接报错，
宁可更新失败，也不悄悄取错列（曾因按关键词猜列，把外盘的开盘价当成收盘价）。
接口调用方式来自 2026-09-19 的实测（见 scripts/probes/）；Westmetall、EIA 官网、
上海航运交易所三个网页源为 2026-10-24 实测（见 scripts/probes/probe_13.py）。
"""
import csv
import os
import re
import time
import warnings
from datetime import datetime, timedelta

import pandas as pd
import requests

import akshare as ak

warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANUAL_CSV = os.path.join(BASE, "data", "manual.csv")  # 表头: code,date,value
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}


def to_points(df, date_col, value_col):
    """DataFrame -> [(YYYY-MM-DD, float)]。列不存在时抛错。"""
    if df is None or len(df) == 0:
        return []
    missing = [c for c in (date_col, value_col) if c not in df.columns]
    if missing:
        raise ValueError(f"接口返回缺少列 {missing}，实际列为 {list(df.columns)[:10]}")
    dates = pd.to_datetime(df[date_col], errors="coerce")
    values = pd.to_numeric(df[value_col], errors="coerce")
    ok = dates.notna() & values.notna()
    dedup = dict(zip(dates[ok].dt.strftime("%Y-%m-%d"), values[ok].astype(float)))
    return sorted(dedup.items())


def _today():
    return datetime.now().strftime("%Y%m%d")


# ---------- 各数据源 ----------

def fetch_sina_main(symbol, start=None):
    df = ak.futures_main_sina(symbol=symbol, start_date=start or "20140101", end_date=_today())
    return to_points(df, "日期", "收盘价")


def fetch_sina_foreign(symbol, start=None):
    # 接口只能取全量历史，落库时按日期覆盖
    return to_points(ak.futures_foreign_hist(symbol=symbol), "date", "close")


def fetch_eia_crude(start=None):
    return to_points(ak.macro_usa_crude_inner(), "日期", "美国国内原油总量-产量")


def fetch_cn_index(fn, start=None):
    return to_points(getattr(ak, fn)(), "日期", "最新值")


def fetch_sw(symbol, start=None):
    return to_points(ak.index_hist_sw(symbol=symbol), "日期", "收盘")


def fetch_shipping(fn, start=None):
    return to_points(getattr(ak, fn)(), "日期", "最新值")


def fetch_manual(code, start=None):
    """从 data/manual.csv 读取手动补录数据；文件不存在时返回空。"""
    if not os.path.exists(MANUAL_CSV):
        return []
    out = {}
    with open(MANUAL_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("code", "").strip() != code:
                continue
            try:
                out[pd.to_datetime(row["date"].strip()).strftime("%Y-%m-%d")] = float(row["value"])
            except (KeyError, ValueError, TypeError):
                continue
    return sorted(out.items())


def _cells(row):
    return [re.sub(r"<[^>]+>|&nbsp;", " ", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]


def _num(s):
    s = s.replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


# ---------- Westmetall：LME 官方现货结算价与库存（2008 年起，按年分页） ----------

_WM_URL = "https://www.westmetall.com/en/markdaten.php?action=table&field={}&year={}"
_WM_FIRST_YEAR = 2008
_WM_COLS = {"price": 1, "stock": 3}  # 表格列：日期 | 现货结算价 | 三月期 | 库存
_WM_CACHE = {}  # 同一页同时供价格和库存两个指标使用
_WM_TTL = 600


def _wm_year(field, year):
    key = (field, year)
    hit = _WM_CACHE.get(key)
    if hit and time.time() - hit[0] < _WM_TTL:
        return hit[1]
    html = requests.get(_WM_URL.format(field, year), headers=UA, timeout=40).text
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        c = _cells(row)
        if len(c) < 4:
            continue
        try:
            d = datetime.strptime(c[0], "%d. %B %Y").strftime("%Y-%m-%d")
        except ValueError:
            continue
        rows.append((d, c))
    _WM_CACHE[key] = (time.time(), rows)
    time.sleep(0.5)
    return rows


def fetch_westmetall(field, col, start=None):
    """field 形如 LME_Cu_cash；col: price（美元/吨）或 stock（吨）。增量时只取起点所在年份至今。"""
    idx = _WM_COLS[col]
    first = int(start[:4]) if start else _WM_FIRST_YEAR
    out = {}
    for year in range(first, datetime.now().year + 1):
        for d, c in _wm_year(field, year):
            v = _num(c[idx])
            if v is not None:
                out[d] = v
    if not out and not start:
        raise ValueError("Westmetall 页面结构可能已变化，未解析到数据")
    return sorted(out.items())


# ---------- EIA 官网历史数据表（无需 API key） ----------

_EIA_URL = "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s={}&f={}"


def fetch_eia(series_id, freq, scale=1.0, start=None):
    """周度表每行是一个月，含 (MM/DD, 值) 若干对；日度表每行是一周，含周一至周五 5 个值。"""
    html = requests.get(_EIA_URL.format(series_id, freq), headers=UA, timeout=60).text
    out = {}
    for row in re.findall(r"<tr>(.*?)</tr>", html, re.S):
        c = _cells(row)
        if not c:
            continue
        if freq == "W":
            m = re.fullmatch(r"(\d{4})-[A-Za-z]{3}", c[0])
            if not m:
                continue
            for md, val in zip(c[1::2], c[2::2]):
                v = _num(val)
                if re.fullmatch(r"\d{2}/\d{2}", md) and v is not None:
                    out[f"{m.group(1)}-{md[:2]}-{md[3:]}"] = v * scale
        else:
            m = re.fullmatch(r"(\d{4}) ([A-Za-z]{3})-(\d{2}) to .*", c[0])
            if not m:
                continue
            monday = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%Y %b %d")
            for k, val in enumerate(c[1:6]):
                v = _num(val)
                if v is not None:
                    out[(monday + timedelta(days=k)).strftime("%Y-%m-%d")] = v * scale
    if not out:
        raise ValueError(f"EIA 页面结构可能已变化，{series_id} 未解析到数据")
    return sorted(out.items())


# ---------- 上海航运交易所：只公布当期与上期，靠每次刷新累积历史 ----------

def fetch_sse(index, code, start=None):
    """更早的历史只能手动补录，manual.csv 中同代码的数据会一并导入。"""
    r = requests.get("https://en.sse.net.cn/currentIndex", params={"indexName": index}, headers=UA, timeout=30)
    data = r.json()["data"]
    line = next((x for x in data["lineDataList"] if x.get("dataItemTypeName") == f"{index.upper()}_T"), None)
    if line is None:
        raise ValueError(f"上海航运交易所接口中没有 {index.upper()} 综合指数")
    out = dict(fetch_manual(code))
    out[data["lastDate"]] = float(line["lastContent"])
    out[data["currentDate"]] = float(line["currentContent"])
    return sorted(out.items())


# ---------- 生意社（100ppi.com）：全站有 HW_CHECK JS 挑战 ----------

_PPI_SESSION = None
_PPI_ITEM = re.compile(
    r'href="https://www\.100ppi\.com/news/detail-(\d{8})-\d+\.html"[^>]*>([^<]*动力煤基准价[^<]*)</a>')
_PPI_PRICE = re.compile(r"基准价为?([\d.]+)元/吨")
_PPI_LIST = "https://www.100ppi.com/news/list-11-1217-816-{}.html"


def _ppi_get(url, tries=5):
    """每次响应内嵌新的挑战哈希，解析后带 cookie 重放即可通过。"""
    global _PPI_SESSION
    if _PPI_SESSION is None:
        _PPI_SESSION = requests.Session()
        _PPI_SESSION.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126",
            "Referer": "https://www.100ppi.com/",
        })
    for _ in range(tries):
        r = _PPI_SESSION.get(url, timeout=30)
        if "HW_CHECK" not in r.text:
            return r.text
        m = re.search(r'var _0x2 = "([0-9a-f]+)"', r.text)
        if m:
            _PPI_SESSION.cookies.set("HW_CHECK", m.group(1), domain=".100ppi.com")
        time.sleep(0.6)
    return ""


def _ymd(s):
    return f"{s[:4]}-{s[4:6]}-{s[6:]}"


def fetch_ppi_coal(start=None):
    """动力煤交易基准价（全国综合现货价，日度，2025-08 起）。

    列表页文章标题形如「M月D日生意社动力煤基准价为XXX.XX元/吨」，URL 含完整日期。
    start: 'YYYYMMDD' 增量起点；None = 全量回补（最多 160 页）。
    """
    start_cmp = _ymd(start) if start else None
    out = {}
    for page in range(1, 161):
        html = _ppi_get(_PPI_LIST.format(page))
        items = _PPI_ITEM.findall(html) if html else []
        if not items:
            break
        reached_start = False
        for ymd, title in items:
            date = _ymd(ymd)
            if start_cmp and date < start_cmp:
                reached_start = True
                continue
            m = _PPI_PRICE.search(title)
            if m:
                out[date] = float(m.group(1))  # 同日多条（转载/修订）取后出现者
        if reached_start:
            break
        time.sleep(0.5)
    return sorted(out.items())


def fetch_ppi_qhd(start=None):
    """秦皇岛港动力煤现货（5500 大卡）历史档案，2021-06 ~ 2022-02。

    来源是「动力煤商品报价动态」文章中的分港口报价表，该栏目此后改为坑口报价，
    已无新数据，增量更新时直接返回空。
    """
    if start:
        return []
    art_re = re.compile(
        r'href="(https://www\.100ppi\.com/news/detail-(\d{8})-\d+\.html)"[^>]*>(动力煤商品报价动态[^<]*)</a>')
    qhd_re = re.compile(r"秦皇岛港动力煤市场[\s\S]{0,300}?([\d.]+)元/吨")
    out = {}
    # 列表页里两类文章混排且不严格按时间排序，空页不能提前终止，需扫满档案所在页区间
    for page in range(5, 13):
        html = _ppi_get(_PPI_LIST.format(page))
        for url, ymd, _title in (art_re.findall(html) if html else []):
            date = _ymd(ymd)
            if not ("2021-06-01" <= date <= "2022-07-01"):
                continue
            body = _ppi_get(url)
            if not body:  # 被限流时等待后重试一次
                time.sleep(6)
                body = _ppi_get(url)
            m = qhd_re.search(re.sub(r"<[^>]+>", "", body)) if body else None
            if m:
                out[date] = float(m.group(1))
            time.sleep(0.8)
    return sorted(out.items())


# ---------- 按配置分发 ----------

_DISPATCH = {
    "sina_main": lambda c, s: fetch_sina_main(c["symbol"], s),
    "sina_foreign": lambda c, s: fetch_sina_foreign(c["symbol"], s),
    "westmetall": lambda c, s: fetch_westmetall(c["field"], c["col"], s),
    "eia_crude": lambda c, s: fetch_eia_crude(s),
    "eia": lambda c, s: fetch_eia(c["sid"], c["freq"], c.get("scale", 1.0), s),
    "sse": lambda c, s: fetch_sse(c["index"], c["code"], s),
    "cn_index": lambda c, s: fetch_cn_index(c["fn"], s),
    "sw": lambda c, s: fetch_sw(c["symbol"], s),
    "shipping": lambda c, s: fetch_shipping(c["fn"], s),
    "manual": lambda c, s: fetch_manual(c["code"], s),
    "ppi_vane": lambda c, s: fetch_ppi_coal(s),
    "ppi_qhd": lambda c, s: fetch_ppi_qhd(s),
}


def fetch_by_cfg(cfg, start=None):
    """cfg: config.SERIES 的一项；start: 'YYYYMMDD' 增量起点（只能全量取的接口会忽略）。"""
    fn = _DISPATCH.get(cfg["source"])
    if fn is None:
        raise ValueError(f"未知数据源: {cfg['source']}")
    return fn(cfg, start)


def incremental_start(last_date, buffer_days=14):
    """增量抓取起点 = 已有最后日期 - 缓冲天数（覆盖数据源对近期数据的修订）。"""
    if not last_date:
        return None
    return (datetime.strptime(last_date, "%Y-%m-%d") - timedelta(days=buffer_days)).strftime("%Y%m%d")

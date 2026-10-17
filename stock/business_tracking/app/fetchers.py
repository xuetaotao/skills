# -*- coding: utf-8 -*-
"""数据抓取层：把各 AKShare 接口统一规整成 [(date, value)] 并落库。

所有接口调用方式均来自 2026-09-19 的 12 轮实测（见 test_data_sources*.py）。
"""
import csv
import os
import re
import time
import warnings
from datetime import datetime, timedelta

import pandas as pd

import akshare as ak

warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANUAL_CSV = os.path.join(BASE, "data", "manual.csv")

# 手动补录 CSV 表头: code,date,value


def _date_col(df):
    for c in df.columns:
        if "日期" in str(c) or "date" in str(c).lower():
            return c
    return df.columns[0]


def _value_col(df, prefer=None):
    cols = list(df.columns)
    if prefer:
        for p in prefer:
            for c in cols:
                if p in str(c):
                    return c
    for key in ("收盘价", "收盘", "指数", "库存", "value", "值"):
        for c in cols:
            if key in str(c):
                return c
    for c in cols[1:]:
        s = pd.to_numeric(df[c], errors="coerce")
        if s.notna().mean() > 0.8:
            return c
    return cols[-1]


def normalize(df, prefer=None):
    """任意接口返回的 DataFrame -> [(date_str, float), ...] 按日期升序。"""
    if df is None or len(df) == 0:
        return []
    dc, vc = _date_col(df), _value_col(df, prefer)
    out = []
    for _, r in df.iterrows():
        try:
            d = pd.to_datetime(str(r[dc])).strftime("%Y-%m-%d")
        except Exception:
            continue
        try:
            v = float(pd.to_numeric(r[vc], errors="coerce"))
        except Exception:
            v = float("nan")
        if pd.notna(v):
            out.append((d, v))
    out.sort(key=lambda x: x[0])
    return out


def _days_back(n):
    return (datetime.now() - timedelta(days=n)).strftime("%Y%m%d")


def _today():
    return datetime.now().strftime("%Y%m%d")


# ---------- 各数据源抓取函数：均返回 [(date, value)] ----------

def fetch_sina_main(symbol, start=None):
    start = start or "20140101"
    df = ak.futures_main_sina(symbol=symbol, start_date=start, end_date=_today())
    return normalize(df, prefer=["收盘价"])


def fetch_sina_foreign(symbol, start=None):
    # 新浪外盘接口返回全量历史，直接全量抓 + 落库去重
    df = ak.futures_foreign_hist(symbol=symbol)
    return normalize(df, prefer=["收盘价"])


def fetch_lme_stock(col, start=None):
    df = ak.macro_euro_lme_stock()
    target = f"{col}-库存"  # 实测列名形如 "铜-库存"
    if df is None or len(df) == 0 or target not in df.columns:
        return []
    return normalize(df[[df.columns[0], target]], prefer=[target])


def fetch_eia_crude(start=None):
    df = ak.macro_usa_crude_inner()
    return normalize(df, prefer=["库存"])


def fetch_cn_index(fn, start=None):
    df = getattr(ak, fn)()
    return normalize(df, prefer=["指数", "值"])


def fetch_sw(symbol, start=None):
    df = ak.index_hist_sw(symbol=symbol)
    return normalize(df, prefer=["收盘"])


def fetch_shipping(fn, start=None):
    df = getattr(ak, fn)()
    return normalize(df, prefer=["指数", "值"])


def fetch_manual(code, start=None):
    """从 data/manual.csv 读取手动补录数据。"""
    if not os.path.exists(MANUAL_CSV):
        return []
    out = []
    with open(MANUAL_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("code", "").strip() == code:
                try:
                    d = pd.to_datetime(row["date"].strip()).strftime("%Y-%m-%d")
                    out.append((d, float(row["value"])))
                except Exception:
                    continue
    out.sort(key=lambda x: x[0])
    return out


# ---------- 生意社动力煤基准价（HW_CHECK 挑战动态破解） ----------

_PPI_SESSION = None
_PPI_ITEM = None
_PPI_PRICE = None


def _ppi_get(url, tries=5):
    """生意社全站有 HW_CHECK JS 挑战：每次响应内嵌新哈希，解析后带 cookie 重放即可收敛。"""
    global _PPI_SESSION, _PPI_ITEM, _PPI_PRICE
    import re as _re
    import requests as _rq
    if _PPI_SESSION is None:
        _PPI_SESSION = _rq.Session()
        _PPI_SESSION.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126",
            "Referer": "https://www.100ppi.com/",
        })
        _PPI_ITEM = _re.compile(
            r'href="https://www\.100ppi\.com/news/detail-(\d{8})-\d+\.html"[^>]*>'
            r'([^<]*动力煤基准价[^<]*)</a>')
        _PPI_PRICE = _re.compile(r"基准价为?([\d.]+)元/吨")
    for _ in range(tries):
        r = _PPI_SESSION.get(url, timeout=30)
        if "HW_CHECK" not in r.text:
            return r.text
        m = _re.search(r'var _0x2 = "([0-9a-f]+)"', r.text)
        if m:
            _PPI_SESSION.cookies.set("HW_CHECK", m.group(1), domain=".100ppi.com")
        time.sleep(0.6)
    return ""


def fetch_ppi_coal(start=None):
    """生意社动力煤交易基准价（全国综合现货价，日度）。

    数据源：100ppi.com「动力煤基准价」专栏列表页（list-11-1217-816-N.html），
    文章标题即含「M月D日生意社动力煤基准价为XXX.XX元/吨」，URL 含完整日期。
    start: 'YYYYMMDD' 增量起点（含缓冲）；None = 全量回补（最多 160 页）。
    """
    start_cmp = None
    if start:
        start_cmp = f"{start[:4]}-{start[4:6]}-{start[6:]}"
    out, stop = [], False
    for page in range(1, 161):
        html = _ppi_get(f"https://www.100ppi.com/news/list-11-1217-816-{page}.html")
        items = _PPI_ITEM.findall(html) if html else []
        if not items:
            break
        for ymd, title in items:
            date = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"
            if start_cmp and date < start_cmp:
                stop = True
                continue
            m = _PPI_PRICE.search(title)
            if m:
                out.append((date, float(m.group(1))))
        if stop:
            break
        time.sleep(0.5)
    # 同日多条（转载/修订）取后出现者，并按日期升序
    dedup = {}
    for d, v in out:
        dedup[d] = v
    return sorted(dedup.items())


def fetch_ppi_qhd(start=None):
    """秦皇岛港动力煤现货（5500Kcal/kg）历史档案。

    数据源：100ppi「动力煤商品报价动态」文章中的分港口报价表，
    档案区间 2021-12-27 ~ 2022-06-15（此后该栏目停发，2025-08 起改为
    基准价发布，现行动力煤日度价见 PPI_COAL）。已封存的历史栏目：
    增量更新时若无早于 start 的新数据则返回空。
    """
    art_re = re.compile(
        r'href="(https://www\.100ppi\.com/news/detail-(\d{8})-\d+\.html)"[^>]*>'
        r"(动力煤商品报价动态[^<]*)</a>")
    qhd_re = re.compile(r"秦皇岛港动力煤市场[\s\S]{0,300}?([\d.]+)元/吨")
    out = []
    start_cmp = None
    if start:
        start_cmp = f"{start[:4]}-{start[4:6]}-{start[6:]}"
        if start_cmp > "2022-07-01":  # 封存档案，无新数据
            return []
    for page in range(5, 13):
        html = _ppi_get(f"https://www.100ppi.com/news/list-11-1217-816-{page}.html")
        arts = art_re.findall(html) if html else []
        # 注意：列表页里两类文章混排且顺序非严格时间序，空页不能提前终止，
        # 必须扫满整个页区间（报价动态档案在第 6-11 页，2021-06-15~2022-06-15）。
        for url, ymd, _title in arts:
            date = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"
            if date < "2021-06-01" or date > "2022-07-01":
                continue
            if start_cmp and date >= start_cmp:
                continue
            body = _ppi_get(url)
            if not body:  # 限流等失败，等待后重试一次
                time.sleep(6)
                body = _ppi_get(url)
            if body:
                m = qhd_re.search(re.sub(r"<[^>]+>", "", body))
                if m:
                    out.append((date, float(m.group(1))))
            time.sleep(0.8)  # 放慢节奏，避免触发限流
    dedup = {}
    for d, v in out:
        dedup[d] = v
    return sorted(dedup.items())


# ---------- 按配置分发 ----------

def fetch_by_cfg(cfg, start=None):
    """cfg: config.SERIES 的一项；start: 'YYYYMMDD' 增量起点（外盘/lme/eia 忽略，全量抓取后去重）。"""
    src = cfg["source"]
    if src == "sina_main":
        return fetch_sina_main(cfg["symbol"], start)
    if src == "sina_foreign":
        return fetch_sina_foreign(cfg["symbol"], start)
    if src == "lme_stock":
        return fetch_lme_stock(cfg["col"], start)
    if src == "eia_crude":
        return fetch_eia_crude(start)
    if src == "cn_index":
        return fetch_cn_index(cfg["fn"], start)
    if src == "sw":
        return fetch_sw(cfg["symbol"], start)
    if src == "shipping":
        return fetch_shipping(cfg["fn"], start)
    if src == "manual":
        return fetch_manual(cfg["code"], start)
    if src == "ppi_vane":
        return fetch_ppi_coal(start)
    if src == "ppi_qhd":
        return fetch_ppi_qhd(start)
    raise ValueError(f"unknown source: {src}")


def incremental_start(last_date, buffer_days=14):
    """有历史数据时，增量抓取起点 = 最后日期 - 缓冲天数。"""
    if not last_date:
        return None
    d = datetime.strptime(last_date, "%Y-%m-%d") - timedelta(days=buffer_days)
    return d.strftime("%Y%m%d")

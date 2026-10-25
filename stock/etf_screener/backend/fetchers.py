# -*- coding: utf-8 -*-
"""取数：交易所官方 ETF 列表与份额、新浪行情、腾讯行情（交叉核对）、中证 / 国证指数名称。

每个函数只负责取数和改列名，列名写死：接口改版时报错，而不是悄悄取错列。
"""
import io
import re
import time
import warnings
from datetime import date, timedelta

import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}


def _get(url, params=None, headers=None, retries=3, timeout=20, method="GET", json=None):
    last = None
    for i in range(retries):
        try:
            r = requests.request(method, url, params=params, json=json, headers={**UA, **(headers or {})}, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


# ---------- 上交所 ----------

SSE_REF = {"Referer": "https://www.sse.com.cn/"}


def sse_list():
    """上交所 ETF 列表：代码、简称、管理人、跟踪指数、子类别、上市日期。"""
    r = _get("https://query.sse.com.cn/commonSoaQuery.do", headers=SSE_REF,
             params={"isPagination": "true", "pageHelp.pageSize": "3000", "pageHelp.pageNo": "1", "sqlId": "FUND_LIST", "fundType": "00"})
    rows = r.json()["result"]
    return [dict(code=x["fundCode"], name=x["secNameFull"] or x["fundAbbr"], short=x["fundAbbr"], exchange="SH",
                 manager=x["companyName"], index_code=(x["INDEX_CODE"] or "").strip(), index_name=(x["INDEX_NAME"] or "").strip(),
                 sub_class=x["subClass"], list_date=_ymd(x["listingDate"])) for x in rows]


def sse_shares(max_back=10):
    """上交所 ETF 份额（份）。从今天往前找最近一个有数据的统计日，返回 (日期, {代码: 份额})。"""
    d = date.today()
    for _ in range(max_back):
        r = _get("https://query.sse.com.cn/commonQuery.do", headers=SSE_REF,
                 params={"isPagination": "true", "pageHelp.pageSize": "10000", "pageHelp.pageNo": "1", "pageHelp.beginPage": "1",
                         "pageHelp.cacheSize": "1", "pageHelp.endPage": "1",
                         "sqlId": "COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L", "STAT_DATE": d.strftime("%Y%m%d")})
        rows = r.json().get("result") or []
        if rows:
            return rows[0]["STAT_DATE"], {x["SEC_CODE"]: float(x["TOT_VOL"]) * 1e4 for x in rows if x.get("TOT_VOL")}
        d -= timedelta(days=1)
        time.sleep(0.5)
    return None, {}


# ---------- 深交所 ----------

SZSE_REF = {"Referer": "https://www.szse.cn/"}


def _szse_xlsx(catalog):
    r = _get("https://www.szse.cn/api/report/ShowReport", headers=SZSE_REF, timeout=30,
             params={"SHOWTYPE": "xlsx", "CATALOGID": catalog, "TABKEY": "tab1"})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")   # 深交所导出的 xlsx 没有默认样式，openpyxl 会警告
        return pd.read_excel(io.BytesIO(r.content), dtype=str)


def szse_shares_date():
    """深交所 ETF 列表里“当前规模”对应的日期（写在表头里）。"""
    r = _get("https://www.szse.cn/api/report/ShowReport/data", headers=SZSE_REF,
             params={"SHOWTYPE": "JSON", "CATALOGID": "1945", "TABKEY": "tab1", "PAGENO": 1})
    m = re.search(r"\d{4}-\d{2}-\d{2}", r.json()[0]["metadata"]["cols"]["dqgm"])
    return m.group(0) if m else None


def szse_list():
    """深交所 ETF：代码、简称、管理人、拟合指数、份额（份），以及基金列表里的投资类别和上市日期。"""
    etf = _szse_xlsx("1945")
    etf.columns = ["code", "name", "idx", "shares", "manager"]
    funds = _szse_xlsx("1105")
    funds = funds[funds["基金类别"] == "ETF"][["基金代码", "投资类别", "上市日期"]]
    funds.columns = ["code", "tzlb", "list_date"]
    df = etf.merge(funds, on="code", how="left")
    out = []
    for r in df.itertuples():
        idx = (r.idx if isinstance(r.idx, str) else "").strip()
        parts = idx.split(maxsplit=1)
        out.append(dict(code=r.code.strip(), name=r.name.strip(), short=r.name.strip(), exchange="SZ", manager=r.manager.strip() if isinstance(r.manager, str) else "",
                        index_code=parts[0] if parts else "", index_name=parts[1].replace(" ", "") if len(parts) > 1 else "",
                        tzlb=r.tzlb if isinstance(r.tzlb, str) else None,
                        list_date=r.list_date if isinstance(r.list_date, str) else None,
                        shares=float(str(r.shares).replace(",", "")) if isinstance(r.shares, str) and r.shares.strip() else None))
    return out


# ---------- 行情 ----------

def sina_prices():
    """新浪 ETF 行情：{代码: (最新价, 成交额 元)}。非交易时间是最近一个交易日的收盘价。"""
    import akshare as ak
    df = ak.fund_etf_category_sina("ETF基金")
    out = {}
    for r in df[["代码", "最新价", "成交额"]].itertuples(index=False):
        px = pd.to_numeric(r[1], errors="coerce")
        if pd.notna(px) and px > 0:
            out[str(r[0])[2:]] = (float(px), float(pd.to_numeric(r[2], errors="coerce") or 0))
    return out


def tencent_mcap(codes, batch=30):
    """腾讯行情的总市值（元），用于交叉核对。批量查询会偶尔丢行，缺的再逐只补查。"""
    def query(cs):
        r = _get("https://qt.gtimg.cn/q=" + ",".join(cs), timeout=10)
        got = {}
        for line in r.content.decode("gbk", errors="ignore").split(";"):
            f = line.split("~")
            if len(f) > 45 and f[45]:
                try:
                    got[f[2]] = float(f[45]) * 1e8
                except ValueError:
                    pass
        return got

    sym = {c: ("sh" if c.startswith(("5", "6")) else "sz") + c for c in codes}
    out = {}
    for i in range(0, len(codes), batch):
        out.update(query([sym[c] for c in codes[i:i + batch]]))
        time.sleep(0.2)
    for c in [c for c in codes if c not in out]:
        out.update(query([sym[c]]))
        time.sleep(0.2)
    return out


def em_benchmark(code):
    """东财基金 F10 的“跟踪标的”。上交所列表里黄金 ETF 没有指数代码，靠它区分黄金9999 和上海金。"""
    r = _get(f"https://fundf10.eastmoney.com/jbgk_{code}.html", timeout=15)
    m = re.search(r"<th>跟踪标的</th><td>(.*?)</td>", r.text)
    return re.sub(r"<.*?>", "", m.group(1)).strip() if m else None


# ---------- 指数名称 ----------

CS_REF = {"Referer": "https://www.csindex.com.cn/"}


def csindex_names():
    """中证指数官网全部指数：{代码: (简称, 资产类别, 地区, 指数类别)}。指数类别如 规模 / 行业 / 主题 / 策略 / 风格 / 利率债。"""
    r = _get("https://www.csindex.com.cn/csindex-home/index-list/query-index-item", method="POST", timeout=30, headers=CS_REF,
             json={"sorter": {"sortField": "null", "sortOrder": None}, "pager": {"pageNum": 1, "pageSize": 10000},
                   "indexFilter": {"ifCustomized": None, "ifTracked": None, "ifWeightCapped": None, "indexCompliance": None,
                                   "hotSpot": None, "indexClassify": None, "currency": None, "region": None, "indexSeries": None,
                                   "undefined": None}})
    return {x["indexCode"]: (x["indexName"], x.get("assetsClassify"), x.get("region"), x.get("indexClassify"))
            for x in r.json()["data"]}


def cnindex_names():
    """国证指数官网全部指数（深证、国证系列）：{代码: (简称, 类型代码)}。类型代码末两位：00 规模、01 行业、02 风格、03 主题、04 策略、05 综合。"""
    r = _get("http://www.cnindex.com.cn/index/indexList", params={"channelCode": "-1", "rows": "5000", "pageNum": "1"},
             headers={"Referer": "http://www.cnindex.com.cn/"}, timeout=30)
    return {x["indexcode"]: (x["indexname"], x.get("indextype")) for x in r.json()["data"]["rows"]}


# ---------- 区间收益 ----------

EM_RANK_COLS = {"基金代码": "code", "日期": "nav_date", "单位净值": "nav", "累计净值": "acc_nav", "近1周": "w1", "近1月": "m1",
                "近3月": "m3", "近6月": "m6", "今年来": "ytd", "近1年": "y1", "近2年": "y2", "近3年": "y3", "成立来": "since",
                "成立日期": "inception"}


def em_exchange_rank():
    """东财“场内交易基金排行”：每只 ETF 的净值和区间收益。收益按复权净值计算（含分红），原始单位为 %，这里换成小数。"""
    import akshare as ak
    df = ak.fund_exchange_rank_em()
    df = df[list(EM_RANK_COLS)].rename(columns=EM_RANK_COLS)
    out = []
    for r in df.to_dict("records"):
        row = dict(code=str(r["code"]).zfill(6), nav_date=_iso(r["nav_date"]), inception=_iso(r["inception"]))
        for k in ("nav", "acc_nav"):
            row[k] = _num(r[k])
        for k in ("w1", "m1", "m3", "m6", "ytd", "y1", "y2", "y3", "since"):
            v = _num(r[k])
            row[k] = None if v is None else v / 100
        out.append(row)
    return out


# ---------- 指数估值 ----------

def csindex_pe(code, start):
    """中证指数日行情里的滚动市盈率（peg）：[(日期, 市盈率)]。start 为 date。"""
    r = _get("https://www.csindex.com.cn/csindex-home/perf/index-perf", headers=CS_REF, timeout=30,
             params={"indexCode": code, "startDate": start.strftime("%Y%m%d"), "endDate": date.today().strftime("%Y%m%d")})
    return [(_ymd(x["tradeDate"]), float(x["peg"])) for x in r.json()["data"] or [] if x.get("peg")]


def legulegu_session():
    """乐咕乐股的 cookie 和 csrf 头（生成方式借用 akshare），一次刷新里共用。"""
    from akshare.stock_feature.stock_a_indicator import get_cookie_csrf
    return get_cookie_csrf(url="https://legulegu.com/stockdata/sz50-ttm-lyr")


def legulegu_pe(code, session):
    """乐咕乐股的指数市盈率（月末 + 最新一天）：[(日期, 加权滚动市盈率)]。用于中证官网没有的深证、国证指数，code 如 399006；
    不支持的指数返回空列表。

    接口字段 ttmPe 是等权市盈率，addTtmPe 才是常用的加权滚动市盈率（沪深300 2026-10-23：12.15，中证官网 12.74）。
    """
    from akshare.stock_feature.stock_a_indicator import get_token_lg
    r = requests.get("https://legulegu.com/api/stockdata/index-basic-pe", params={"token": get_token_lg(), "indexCode": f"{code}.SZ"},
                     timeout=20, **session)
    r.raise_for_status()
    return [(x["date"], float(x["addTtmPe"])) for x in r.json().get("data") or [] if x.get("addTtmPe")]


def _num(v):
    v = pd.to_numeric(v, errors="coerce")
    return None if pd.isna(v) else float(v)


def _iso(v):
    if v is None or pd.isna(v):
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)[:10]


def _ymd(s):
    s = (s or "").strip()
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 and s.isdigit() else (s or None)

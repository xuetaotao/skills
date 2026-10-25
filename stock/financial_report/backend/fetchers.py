# -*- coding: utf-8 -*-
"""数据源。全部用显式字段名取数，接口改版时报错而不是悄悄取错列。

- 财务指标：东方财富 F10「主要指标」RPT_F10_FINANCE_MAINFINADATA（每只股票一次请求，含全部历史报告期）
- 估值与市值：东方财富数据中心 RPT_VALUEANALYSIS_DET（每日 PE/PB/市值，2018 年起）
- 分红：东方财富数据中心 RPT_SHAREBONUS_DET
- 10 年期国债收益率：东方财富数据中心 RPTA_WEB_TREASURYYIELD（中债国债到期收益率）
- 企业性质、控股股东、实际控制人：东方财富 F10「公司概况」RPT_F10_ORG_BASICINFO
- 复权因子：新浪财经后复权因子（等比复权，含现金分红、送转、配股）
- 申万行业：申万宏源研究官网的股票分类表 + 巨潮资讯的行业代码名称表
- 搜索：东方财富代码表搜索，失败时用新浪 suggest
"""
import io
import re
import time
import warnings

import requests

from .config import STORE_FIELDS

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"}
DC_WEB = "https://datacenter-web.eastmoney.com/api/data/v1/get"
DC_F10 = "https://datacenter.eastmoney.com/securities/api/data/get"


def _get(url, params=None, retries=3, timeout=20, headers=None, **kw):
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers=headers or UA, timeout=timeout, **kw)
            r.raise_for_status()
            return r
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(1.0 * (i + 1))


def secucode(code):
    """6 位代码 → 带交易所后缀：6/9 开头沪市，0/2/3 开头深市，其余（4/8/92）北交所。"""
    if code.startswith(("6", "900")):
        return f"{code}.SH"
    if code.startswith(("0", "2", "3")):
        return f"{code}.SZ"
    return f"{code}.BJ"


def _in(codes):
    return "(" + ",".join(f'"{c}"' for c in codes) + ")"


def dc_query(report, flt, columns="ALL", sort="SECURITY_CODE", order=1, page_size=500, max_pages=40):
    """sort / order 可以是多列，如 "SECURITY_CODE,TRADE_DATE" / "1,1"；单列排序时分页可能重复或漏行。"""
    out, page = [], 1
    while page <= max_pages:
        j = _get(DC_WEB, dict(reportName=report, columns=columns, filter=flt, pageNumber=page, pageSize=page_size,
                              sortColumns=sort, sortTypes=order, source="WEB", client="WEB")).json()
        res = j.get("result")
        if not res or not res.get("data"):
            break
        out.extend(res["data"])
        if page >= (res.get("pages") or 1):
            break
        page += 1
    return out


# ---------- 财务指标 ----------

def fetch_indicators(code):
    """全部报告期的主要指标，只保留 STORE_FIELDS。股票不存在或无数据时返回 []。"""
    j = _get(DC_F10, dict(type="RPT_F10_FINANCE_MAINFINADATA", sty="APP_F10_MAINFINADATA", quoteColumns="",
                          filter=f'(SECUCODE="{secucode(code)}")', p=1, ps=200, sr=-1, st="REPORT_DATE",
                          source="HSF10", client="PC")).json()
    rows = (j.get("result") or {}).get("data") or []
    return [{k: r.get(k) for k in STORE_FIELDS} for r in rows if r.get("REPORT_DATE")]


# ---------- 企业性质 ----------

def _blank(v):
    return None if v in (None, "", "无", "--", "-") else v


def fetch_org_info(codes):
    """企业性质（东财原值，如 央企子公司 / 地方国有企业 / 大型民企）、控股股东、实际控制人、上市日期。"""
    out = []
    codes = list(codes)
    for i in range(0, len(codes), 100):
        flt = "(SECUCODE in (" + ",".join(f'"{secucode(c)}"' for c in codes[i:i + 100]) + "))"
        j = _get(DC_F10, dict(type="RPT_F10_ORG_BASICINFO", sty="SECURITY_CODE,ORG_FORM,CONTROL_HOLDER,REAL_CONTROLER,LISTING_DATE",
                              filter=flt, p=1, ps=500, source="HSF10", client="PC")).json()
        for r in (j.get("result") or {}).get("data") or []:
            out.append(dict(code=r["SECURITY_CODE"], nature=_blank(r.get("ORG_FORM")), controller=_blank(r.get("CONTROL_HOLDER")),
                            real_controller=_blank(r.get("REAL_CONTROLER")), listing_date=(r.get("LISTING_DATE") or "")[:10] or None))
    return out


# ---------- 估值、市值 ----------

def latest_trade_date(code="601398"):
    rows = dc_query("RPT_VALUEANALYSIS_DET", f'(SECURITY_CODE="{code}")', columns="TRADE_DATE",
                    sort="TRADE_DATE", order=-1, page_size=1, max_pages=1)
    return rows[0]["TRADE_DATE"][:10] if rows else None


QUOTE_COLS = "SECURITY_CODE,SECURITY_NAME_ABBR,TRADE_DATE,CLOSE_PRICE,CHANGE_RATE,PE_TTM,PB_MRQ,PS_TTM,TOTAL_MARKET_CAP"


def fetch_quotes(codes, trade_date):
    """指定交易日的估值快照；停牌等没有当天数据的股票不返回。"""
    out = []
    codes = list(codes)
    for i in range(0, len(codes), 50):
        rows = dc_query("RPT_VALUEANALYSIS_DET", f"(SECURITY_CODE in {_in(codes[i:i + 50])})(TRADE_DATE='{trade_date}')",
                        columns=QUOTE_COLS)
        out += [dict(code=r["SECURITY_CODE"], trade_date=r["TRADE_DATE"][:10], name=r["SECURITY_NAME_ABBR"],
                     close=r["CLOSE_PRICE"], change=r["CHANGE_RATE"], pe_ttm=r["PE_TTM"], pb=r["PB_MRQ"],
                     ps_ttm=r["PS_TTM"], mcap=r["TOTAL_MARKET_CAP"]) for r in rows]
    return out


def fetch_valuation_history(code, start):
    rows = dc_query("RPT_VALUEANALYSIS_DET", f"(SECURITY_CODE=\"{code}\")(TRADE_DATE>='{start}')",
                    columns="TRADE_DATE,CLOSE_PRICE,PE_TTM,PB_MRQ,TOTAL_MARKET_CAP", sort="TRADE_DATE", page_size=5000)
    return [(r["TRADE_DATE"][:10], r["CLOSE_PRICE"], r["PE_TTM"], r["PB_MRQ"], r["TOTAL_MARKET_CAP"]) for r in rows]


def fetch_closes(codes, start):
    """[(code, date, 不复权收盘价)]，start 起的每个交易日。按代码 + 日期排序，保证分页不重不漏。"""
    rows = dc_query("RPT_VALUEANALYSIS_DET", f"(SECURITY_CODE in {_in(codes)})(TRADE_DATE>='{start}')",
                    columns="SECURITY_CODE,TRADE_DATE,CLOSE_PRICE", sort="SECURITY_CODE,TRADE_DATE", order="1,1",
                    page_size=5000, max_pages=100)
    return [(r["SECURITY_CODE"], r["TRADE_DATE"][:10], r["CLOSE_PRICE"]) for r in rows if r.get("CLOSE_PRICE")]


def fetch_adj_factors(code):
    """新浪后复权因子 [(除权除息日, 累计因子)]，升序。复权价 = 收盘价 × 当日适用的因子（最近一个不晚于当日的因子）。

    东财行情接口的前/后复权是“减去分红”的加减法复权，长区间的涨跌幅会明显失真，所以不用。
    """
    sym = {"SH": "sh", "SZ": "sz", "BJ": "bj"}[secucode(code)[-2:]] + code
    t = _get(f"https://finance.sina.com.cn/realstock/company/{sym}/hfq.js",
             headers={**UA, "Referer": "https://finance.sina.com.cn"}, timeout=15).text
    rows = sorted((d, float(f)) for d, f in re.findall(r'"d"\s*:\s*"(\d{4}-\d{2}-\d{2})"\s*,\s*"f"\s*:\s*"([\d.]+)"', t))
    if not rows:
        raise ValueError("新浪没有返回复权因子")
    return rows


# ---------- 分红 ----------

def fetch_dividends(codes):
    """全部历史分红（现金分红，每 10 股含税金额）。"""
    out = []
    codes = list(codes)
    for i in range(0, len(codes), 50):
        rows = dc_query("RPT_SHAREBONUS_DET", f"(SECURITY_CODE in {_in(codes[i:i + 50])})", sort="REPORT_DATE",
                        columns="SECURITY_CODE,REPORT_DATE,PLAN_NOTICE_DATE,EX_DIVIDEND_DATE,PRETAX_BONUS_RMB,"
                                "ASSIGN_PROGRESS,IMPL_PLAN_PROFILE")
        for r in rows:
            if not r.get("PRETAX_BONUS_RMB"):
                continue  # 只送转、不派现
            out.append(dict(code=r["SECURITY_CODE"], report_date=r["REPORT_DATE"][:10],
                            notice_date=(r.get("PLAN_NOTICE_DATE") or "")[:10] or None,
                            ex_date=(r.get("EX_DIVIDEND_DATE") or "")[:10] or None, per10=r["PRETAX_BONUS_RMB"],
                            progress=r.get("ASSIGN_PROGRESS"), plan=r.get("IMPL_PLAN_PROFILE")))
    return out


def fetch_cgb10(start):
    """中国 10 年期国债收益率（%）[(日期, 收益率)]，start 起；节假日接口返回空值，跳过。"""
    rows = dc_query("RPTA_WEB_TREASURYYIELD", f"(SOLAR_DATE>='{start}')", columns="SOLAR_DATE,EMM00166466",
                    sort="SOLAR_DATE", order=1, page_size=5000, max_pages=5)
    return [(r["SOLAR_DATE"][:10], r["EMM00166466"]) for r in rows if r.get("EMM00166466") is not None]


# ---------- 申万行业 ----------

SW_CLASS_URL = "https://www.swsresearch.com/swindex/pdf/SwClass2021/StockClassifyUse_stock.xls"


def fetch_sw_class():
    """[(股票代码, 三级行业代码, 计入日期)]，每只股票取最近一次计入的分类（即申万 2021 版）。

    申万官网的证书链在部分 Python 环境里校验不过，这里关闭校验；文件是公开的分类表，不含敏感信息。
    """
    import pandas as pd
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r = _get(SW_CLASS_URL, timeout=60, verify=False)
    df = pd.read_excel(io.BytesIO(r.content), dtype=str)
    df = df.rename(columns={"股票代码": "code", "计入日期": "since", "行业代码": "sw3"})[["code", "since", "sw3"]]
    df = df.dropna().sort_values(["code", "since"]).groupby("code").tail(1)
    return [(c, s3, s[:10]) for c, s, s3 in zip(df["code"], df["since"], df["sw3"])]


def fetch_sw_names():
    """[(行业代码, 名称, 级别)]，代码与分类表一致（一级 2 位、二级 4 位、三级 6 位），只保留现行类目。"""
    import akshare as ak
    import pandas as pd
    df = ak.stock_industry_category_cninfo(symbol="申银万国行业分类标准")
    df = df[pd.isna(df["终止日期"])]
    out = []
    for code, name in zip(df["类目编码"], df["类目名称"]):
        c = str(code).lstrip("S")
        if len(c) in (2, 4, 6) and c.isdigit():
            out.append((c, str(name), {2: 1, 4: 2, 6: 3}[len(c)]))
    return out


# ---------- 搜索 ----------

A_TYPES = {"沪A", "深A", "京A"}


def search(q, limit=10):
    q = q.strip()
    if not q:
        return []
    try:
        j = _get("https://search-codetable.eastmoney.com/codetable/search/web",
                 dict(client="web", clientType="webSuggest", clientVersion="lastest", keyword=q, pageIndex=1,
                      pageSize=20, securityFilter=""), retries=1, timeout=8).json()
        out = [dict(code=x["code"], name=x["shortName"], market=x.get("securityTypeName"))
               for x in j.get("result") or [] if x.get("securityTypeName") in A_TYPES]
        if out:
            return out[:limit]
    except Exception:
        pass
    r = _get(f"https://suggest3.sinajs.cn/suggest/type=11&key={q}&name=s",
             headers={**UA, "Referer": "https://finance.sina.com.cn"}, retries=1, timeout=8)
    body = r.text.split('"')[1] if '"' in r.text else ""
    out = []
    for item in body.split(";"):
        f = item.split(",")
        if len(f) > 4 and f[2].isdigit():
            out.append(dict(code=f[2], name=f[4], market={"sh": "沪A", "sz": "深A", "bj": "京A"}.get(f[3][:2], "")))
    return out[:limit]

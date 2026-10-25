# -*- coding: utf-8 -*-
"""数据源

每个市场按顺序尝试多个来源，返回 (来源名, [(日期, 收盘价)])，日期升序。全部失败时抛出最后一个错误。
个股用前复权价格，分红送转不会造成假的跌破。
"""
import logging
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

from .config import HISTORY_START

log = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _ak():
    import akshare as ak
    return ak


def _rows(df):
    """DataFrame → [(YYYY-MM-DD, close)]，去掉空值与重复日期，只保留 HISTORY_START 之后。"""
    if df is None or len(df) == 0:
        return []
    for a, b in (("日期", "date"), ("收盘", "close"), ("收盘价", "close"), ("最新价", "close"), ("latest", "close")):
        if a in df.columns and b not in df.columns:
            df = df.rename(columns={a: b})
    if "date" not in df.columns or "close" not in df.columns:
        return []
    d = pd.DataFrame({"date": pd.to_datetime(df["date"], errors="coerce"),
                      "close": pd.to_numeric(df["close"], errors="coerce")}).dropna()
    d = d[(d["close"] > 0) & (d["date"] >= HISTORY_START)]
    d = d.drop_duplicates("date", keep="last").sort_values("date")
    return [(x.strftime("%Y-%m-%d"), float(c)) for x, c in zip(d["date"], d["close"])]


def _try(sources, retries=2):
    last = None
    for name, fn in sources:
        for attempt in range(retries):
            try:
                rows = fn()
                if rows:
                    return name, rows
                last = ValueError(f"{name} 返回空数据")
                break
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(0.8 * (attempt + 1))
        log.warning("%s 失败：%s", name, last)
    raise last or ValueError("没有可用的数据源")


# ---------------- A 股指数 ---------------- #

def _a_index(code, market):
    ak = _ak()
    start = HISTORY_START.replace("-", "")
    end = datetime.now().strftime("%Y%m%d")
    return _try([
        ("新浪财经", lambda: _rows(ak.stock_zh_index_daily(symbol=f"{market}{code}"))),
        ("中证指数", lambda: _rows(ak.stock_zh_index_hist_csindex(symbol=code, start_date=start, end_date=end))),
        ("东方财富", lambda: _rows(ak.index_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end))),
        ("腾讯财经", lambda: _rows(ak.stock_zh_index_daily_tx(symbol=f"{market}{code}"))),
    ])


def _cni_index(code):
    """国证指数（如自由现金流 980092）：国证官网有回溯到 2015 年的历史，新浪、腾讯只有发布后的数据。"""
    ak = _ak()
    return _try([
        ("国证指数", lambda: _rows(ak.index_hist_cni(symbol=code, start_date=HISTORY_START.replace("-", ""),
                                                  end_date=datetime.now().strftime("%Y%m%d")))),
        ("新浪财经", lambda: _rows(ak.stock_zh_index_daily(symbol=f"sz{code}"))),
        ("腾讯财经", lambda: _rows(ak.stock_zh_index_daily_tx(symbol=f"sz{code}"))),
    ])


def _csi_index(code):
    """中证指数的非数字代码（如红利低波 H30269），新浪、腾讯不收录。"""
    ak = _ak()
    return _try([("中证指数", lambda: _rows(ak.stock_zh_index_hist_csindex(
        symbol=code, start_date=HISTORY_START.replace("-", ""), end_date=datetime.now().strftime("%Y%m%d"))))])


def _a_stock(code):
    ak = _ak()
    symbol = ("sh" if code.startswith("6") else "sz") + code
    return _try([
        ("新浪财经（前复权）", lambda: _rows(ak.stock_zh_a_daily(symbol=symbol, adjust="qfq"))),
        ("腾讯财经（前复权）", lambda: _rows(ak.stock_zh_a_hist_tx(symbol=symbol, start_date=HISTORY_START.replace("-", ""),
                                                            end_date="20500101", adjust="qfq"))),
    ])


# ---------------- 海外指数 ---------------- #

SINA_GLOBAL = {
    "N225": "日经225指数", "KS11": "首尔综合指数", "TWII": "中国台湾加权指数",
    "SENSEX": "印度孟买SENSEX指数", "UKX": "英国富时100指数", "DAX": "德国DAX 30种股价指数",
}


def _us_index(code):
    ak = _ak()
    return _try([("新浪美股指数", lambda: _rows(ak.index_us_stock_sina(symbol=code)))])


def _global_index(code):
    ak = _ak()
    return _try([("新浪全球指数", lambda: _rows(ak.index_global_hist_sina(symbol=SINA_GLOBAL[code])))])


def _twse_month(day):
    """台湾证交所某月的加权指数日线（民国纪年日期）。"""
    r = requests.get("https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST",
                     params={"date": day.strftime("%Y%m01"), "response": "json"},
                     headers={**UA, "Referer": "https://www.twse.com.tw/"}, timeout=20)
    r.raise_for_status()
    js = r.json()
    if js.get("stat") != "OK" or not js.get("data"):
        return []
    fields = js["fields"]
    di, ci = fields.index("日期"), fields.index("收盤指數")
    out = []
    for row in js["data"]:
        y, m, d = str(row[di]).split("/")
        close = float(str(row[ci]).replace(",", ""))
        out.append((f"{int(y) + 1911:04d}-{int(m):02d}-{int(d):02d}", close))
    return out


def _tw_index(code):
    """新浪提供长历史；台湾证交所官方数据覆盖最近两个月（新浪偶尔滞后或缺日）。两者任一成功即可。"""
    name, rows, err = None, [], None
    try:
        name, rows = _global_index(code)
    except Exception as e:  # noqa: BLE001
        err = e
    recent = []
    first = datetime.now().replace(day=1)
    for month in ((first - timedelta(days=1)).replace(day=1), first):
        try:
            recent += _twse_month(month)
        except Exception as e:  # noqa: BLE001
            log.warning("台湾证交所 %s 失败：%s", month.strftime("%Y-%m"), e)
    if recent:
        merged = dict(rows)
        merged.update(recent)
        rows = sorted(merged.items())
        name = f"{name} + 台湾证交所" if name else "台湾证交所"
    if not rows:
        raise err or ValueError("台湾加权指数两个来源都失败")
    return name, rows


def _hk_index(code):
    ak = _ak()
    return _try([
        ("新浪港股指数", lambda: _rows(ak.stock_hk_index_daily_sina(symbol=code))),
        ("东方财富港股指数", lambda: _rows(ak.stock_hk_index_daily_em(symbol=code))),
    ])


def _commodity(code):
    ak = _ak()
    return _try([("新浪外盘期货", lambda: _rows(ak.futures_foreign_hist(symbol=code)))])


def fetch_instrument(inst):
    m, code = inst["market"], inst["code"]
    if m in ("sh", "sz"):
        return _a_index(code, m)
    if m == "cni":
        return _cni_index(code)
    if m == "csi":
        return _csi_index(code)
    if m == "stock":
        return _a_stock(code)
    if m == "us":
        return _us_index(code)
    if m == "tw":
        return _tw_index(code)
    if m in ("jp", "kr", "in", "uk", "de"):
        return _global_index(code)
    if m == "hk":
        return _hk_index(code)
    if m == "metal":
        return _commodity(code)
    raise ValueError(f"未知市场 {m}")


# ---------------- 美元指数 ---------------- #

def _dxy_sina():
    url = "https://vip.stock.finance.sina.com.cn/forex/api/jsonp.php/var%20_=/NewForexService.getDayKLine?symbol=DINIW"
    r = requests.get(url, headers={**UA, "Referer": "https://finance.sina.com.cn"}, timeout=20)
    r.raise_for_status()
    text = r.text
    i = text.find("var _=(")
    if i < 0:
        return []
    out = []
    for rec in text[i + 7:].strip().rstrip(");").strip().strip('"').split("|"):
        p = rec.split(",")
        if len(p) >= 5 and p[0] >= HISTORY_START:
            out.append((p[0][:10], float(p[4])))  # 字段序：日期,开,低,高,收
    return sorted(dict(out).items())


def _dxy_eastmoney():
    r = requests.get("https://push2his.eastmoney.com/api/qt/stock/kline/get", headers=UA, timeout=20, params={
        "secid": "100.UDI", "fields1": "f1,f2,f3,f4,f5", "fields2": "f51,f52,f53,f54,f55",
        "klt": "101", "fqt": "0", "beg": HISTORY_START.replace("-", ""), "end": "20500101", "lmt": "5000"})
    r.raise_for_status()
    kl = (r.json().get("data") or {}).get("klines") or []
    return [(p[0], float(p[2])) for p in (x.split(",") for x in kl)]  # 字段序：日期,开,收,高,低


def fetch_dxy():
    return _try([("新浪外汇", _dxy_sina), ("东方财富", _dxy_eastmoney)], retries=3)


# ---------------- 中美国债收益率 ---------------- #

def fetch_bonds(start):
    """{序列代码: [(日期, 收益率%)]}，start 为 YYYYMMDD。"""
    ak = _ak()
    last = None
    for attempt in range(3):
        try:
            df = ak.bond_zh_us_rate(start_date=start)
            break
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    else:
        raise last
    out = {}
    for country, prefix in (("中国", "CN"), ("美国", "US")):
        for term in ("2年", "5年", "10年", "30年"):
            col = f"{country}国债收益率{term}"
            if col in df.columns:
                out[f"{prefix}{term}"] = _rows(df[["日期", col]].rename(columns={"日期": "date", col: "close"}))
    if not any(out.values()):
        raise ValueError("中美国债收益率返回空数据")
    return "东方财富（akshare bond_zh_us_rate）", out


# ---------------- 估值（蛋卷基金） ---------------- #

def fetch_valuation():
    """当天的 PE / PB 及其历史百分位（0–1）。接口只给最新一天，历史靠每次刷新累积。"""
    def get():
        r = requests.get("https://danjuanapp.com/djapi/index_eva/dj", headers=UA, timeout=20)
        r.raise_for_status()
        out = {}
        for it in r.json()["data"]["items"]:
            ts = it.get("ts")
            if not it.get("index_code") or not ts:
                continue
            out[it["index_code"]] = dict(
                date=datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d"), name=it.get("name"),
                pe=it.get("pe") or None, pe_pct=it.get("pe_percentile"), pb=it.get("pb") or None,
                pb_pct=it.get("pb_percentile"))
        return out
    return _try([("蛋卷基金", get)], retries=3)

# -*- coding: utf-8 -*-
"""SQLite 数据层。

watchlist  自选股（保存在本地数据库，重启后保留）
stocks     股票基本信息：名称、公司类型、企业性质、控股股东、实际控制人、上市日期
sw_class   全市场申万行业归属（股票 → 三级行业代码）；sw_names 行业代码 → 名称
reports    各报告期的财务指标（东财主要指标接口的原始字段，JSON）
quotes     最新一个交易日的估值与市值
valuation  自选股的每日估值历史（2018 年起）
prices     自选股和同行业的每日收盘价（不复权，近 PRICE_YEARS 年），算区间涨跌幅
adj_factors 复权因子（新浪后复权因子，除权除息日 → 累计因子）
dividends  分红记录
bond_yield 中国 10 年期国债收益率（每日，近 PRICE_YEARS 年），算股债利差
meta       全局状态（上次刷新、失败项、数据版本等）
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE, "data", "financial.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist(code TEXT PRIMARY KEY, pos INTEGER, added_at TEXT);
CREATE TABLE IF NOT EXISTS stocks(
    code TEXT PRIMARY KEY, name TEXT, org_type TEXT, updated_at TEXT,
    nature TEXT, controller TEXT, real_controller TEXT, listing_date TEXT
);
CREATE TABLE IF NOT EXISTS sw_class(code TEXT PRIMARY KEY, sw3 TEXT, since TEXT);
CREATE TABLE IF NOT EXISTS sw_names(code TEXT PRIMARY KEY, name TEXT, level INTEGER);
CREATE TABLE IF NOT EXISTS reports(
    code TEXT, report_date TEXT, name TEXT, notice_date TEXT, data TEXT,
    PRIMARY KEY(code, report_date)
);
CREATE TABLE IF NOT EXISTS quotes(
    code TEXT PRIMARY KEY, trade_date TEXT, name TEXT, close REAL, change REAL,
    pe_ttm REAL, pb REAL, ps_ttm REAL, mcap REAL
);
CREATE TABLE IF NOT EXISTS valuation(
    code TEXT, date TEXT, close REAL, pe_ttm REAL, pb REAL, mcap REAL,
    PRIMARY KEY(code, date)
);
CREATE TABLE IF NOT EXISTS prices(code TEXT, date TEXT, close REAL, PRIMARY KEY(code, date));
CREATE TABLE IF NOT EXISTS adj_factors(code TEXT, date TEXT, factor REAL, PRIMARY KEY(code, date));
CREATE TABLE IF NOT EXISTS dividends(
    code TEXT, report_date TEXT, notice_date TEXT, ex_date TEXT, per10 REAL, progress TEXT, plan TEXT,
    PRIMARY KEY(code, report_date)
);
CREATE TABLE IF NOT EXISTS bond_yield(date TEXT PRIMARY KEY, y10 REAL);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""


@contextmanager
def conn():
    """事务内执行，结束时提交并关闭连接（sqlite3 自带的 with 只提交不关闭）。"""
    c = sqlite3.connect(DB_PATH, timeout=30)
    try:
        c.execute("PRAGMA journal_mode=WAL")
        yield c
        c.commit()
    finally:
        c.close()


ADDED_COLUMNS = {"stocks": ["nature", "controller", "real_controller", "listing_date"]}


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with conn() as c:
        c.executescript(SCHEMA)
        for table, cols in ADDED_COLUMNS.items():  # 旧版本建的库没有这些列
            have = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
            for col in cols:
                if col not in have:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ---------- meta ----------

def set_meta(key, value):
    with conn() as c:
        c.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (key, value))


def get_meta(key, default=None):
    with conn() as c:
        row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def get_json(key, default):
    try:
        return json.loads(get_meta(key) or "null") or default
    except ValueError:
        return default


def set_json(key, value):
    set_meta(key, json.dumps(value, ensure_ascii=False))


# ---------- 自选股 ----------

def watchlist():
    with conn() as c:
        return [r[0] for r in c.execute("SELECT code FROM watchlist ORDER BY pos, added_at")]


def add_watch(code):
    with conn() as c:
        pos = c.execute("SELECT COALESCE(MAX(pos), -1) + 1 FROM watchlist").fetchone()[0]
        c.execute("INSERT OR IGNORE INTO watchlist(code,pos,added_at) VALUES(?,?,?)", (code, pos, now_str()))


def remove_watch(code):
    with conn() as c:
        c.execute("DELETE FROM watchlist WHERE code=?", (code,))


def reorder_watch(codes):
    with conn() as c:
        c.executemany("UPDATE watchlist SET pos=? WHERE code=?", [(i, code) for i, code in enumerate(codes)])


def ensure_default_watchlist(codes):
    """数据库里从未设置过自选股时写入默认列表；用户删空后不再自动补回。"""
    if get_meta("watchlist_init"):
        return
    for code in codes:
        add_watch(code)
    set_meta("watchlist_init", now_str())


# ---------- 行业 ----------

def save_sw(classes, names):
    with conn() as c:
        if classes:
            c.execute("DELETE FROM sw_class")
            c.executemany("INSERT INTO sw_class(code,sw3,since) VALUES(?,?,?)", classes)
        if names:
            c.execute("DELETE FROM sw_names")
            c.executemany("INSERT INTO sw_names(code,name,level) VALUES(?,?,?)", names)


def load_sw():
    with conn() as c:
        cls = {code: sw3 for code, sw3 in c.execute("SELECT code, sw3 FROM sw_class")}
        names = {code: name for code, name in c.execute("SELECT code, name FROM sw_names")}
    return cls, names


# ---------- 股票与财报 ----------

def upsert_stock(code, name, org_type):
    with conn() as c:
        c.execute("INSERT INTO stocks(code,name,org_type,updated_at) VALUES(?,?,?,?) ON CONFLICT(code) DO UPDATE SET "
                  "name=COALESCE(excluded.name, stocks.name), org_type=COALESCE(excluded.org_type, stocks.org_type), "
                  "updated_at=excluded.updated_at", (code, name, org_type, now_str()))


def save_org_info(rows):
    """rows: fetchers.fetch_org_info 的结果。只更新已有的股票（财报还没取到的股票不建档）。"""
    with conn() as c:
        c.executemany("UPDATE stocks SET nature=:nature, controller=:controller, real_controller=:real_controller, "
                      "listing_date=:listing_date WHERE code=:code", rows)


def load_stocks():
    with conn() as c:
        c.row_factory = sqlite3.Row
        return {r["code"]: dict(r) for r in c.execute("SELECT * FROM stocks")}


def save_reports(code, rows):
    """rows: 接口原始行（dict）。同一报告期覆盖，旧报告期保留。"""
    with conn() as c:
        c.executemany(
            "INSERT OR REPLACE INTO reports(code,report_date,name,notice_date,data) VALUES(?,?,?,?,?)",
            [(code, r["REPORT_DATE"][:10], r.get("REPORT_DATE_NAME"), (r.get("NOTICE_DATE") or "")[:10] or None,
              json.dumps(r, ensure_ascii=False)) for r in rows])


def load_reports(codes=None):
    """{code: [row, ...]}，按报告期升序。"""
    sql = "SELECT code, data FROM reports"
    args = ()
    if codes is not None:
        codes = list(codes)
        if not codes:
            return {}
        sql += f" WHERE code IN ({','.join('?' * len(codes))})"
        args = codes
    out = {}
    with conn() as c:
        for code, data in c.execute(sql + " ORDER BY code, report_date", args):
            out.setdefault(code, []).append(json.loads(data))
    return out


def report_codes():
    with conn() as c:
        return {r[0] for r in c.execute("SELECT DISTINCT code FROM reports")}


# ---------- 行情、估值与分红 ----------

def save_quotes(rows):
    with conn() as c:
        c.executemany("INSERT OR REPLACE INTO quotes(code,trade_date,name,close,change,pe_ttm,pb,ps_ttm,mcap) "
                      "VALUES(:code,:trade_date,:name,:close,:change,:pe_ttm,:pb,:ps_ttm,:mcap)", rows)


def load_quotes():
    with conn() as c:
        c.row_factory = sqlite3.Row
        return {r["code"]: dict(r) for r in c.execute("SELECT * FROM quotes")}


def save_valuation(code, rows):
    with conn() as c:
        c.executemany("INSERT OR REPLACE INTO valuation(code,date,close,pe_ttm,pb,mcap) VALUES(?,?,?,?,?,?)",
                      [(code, *r) for r in rows])


def last_valuation_date(code):
    with conn() as c:
        return c.execute("SELECT MAX(date) FROM valuation WHERE code=?", (code,)).fetchone()[0]


def load_valuation(code):
    with conn() as c:
        return c.execute("SELECT date, close, pe_ttm, pb, mcap FROM valuation WHERE code=? ORDER BY date",
                         (code,)).fetchall()


def save_prices(rows):
    """rows: [(code, date, close)]"""
    with conn() as c:
        c.executemany("INSERT OR REPLACE INTO prices(code,date,close) VALUES(?,?,?)", rows)


def last_price_dates():
    with conn() as c:
        return dict(c.execute("SELECT code, MAX(date) FROM prices GROUP BY code"))


def trim_prices(before):
    with conn() as c:
        c.execute("DELETE FROM prices WHERE date < ?", (before,))


def load_prices():
    """{code: [(date, close), ...]}，按日期升序。"""
    out = {}
    with conn() as c:
        for code, d, close in c.execute("SELECT code, date, close FROM prices ORDER BY code, date"):
            out.setdefault(code, []).append((d, close))
    return out


def save_factors(code, rows):
    """整只股票替换：新浪会因送转、更正等调整整段因子。"""
    with conn() as c:
        c.execute("DELETE FROM adj_factors WHERE code=?", (code,))
        c.executemany("INSERT INTO adj_factors(code,date,factor) VALUES(?,?,?)", [(code, d, f) for d, f in rows])


def load_factors():
    out = {}
    with conn() as c:
        for code, d, f in c.execute("SELECT code, date, factor FROM adj_factors ORDER BY code, date"):
            out.setdefault(code, []).append((d, f))
    return out


def save_dividends(rows):
    with conn() as c:
        c.executemany("INSERT OR REPLACE INTO dividends(code,report_date,notice_date,ex_date,per10,progress,plan) "
                      "VALUES(:code,:report_date,:notice_date,:ex_date,:per10,:progress,:plan)", rows)


def load_dividends(codes=None):
    out = {}
    with conn() as c:
        c.row_factory = sqlite3.Row
        for r in c.execute("SELECT * FROM dividends ORDER BY code, report_date"):
            if codes is None or r["code"] in codes:
                out.setdefault(r["code"], []).append(dict(r))
    return out


def save_bond_yields(rows):
    """rows: [(date, 10 年期收益率 %)]"""
    with conn() as c:
        c.executemany("INSERT OR REPLACE INTO bond_yield(date,y10) VALUES(?,?)", rows)


def load_bond_yields():
    with conn() as c:
        return c.execute("SELECT date, y10 FROM bond_yield ORDER BY date").fetchall()


def has_data():
    with conn() as c:
        return c.execute("SELECT 1 FROM reports LIMIT 1").fetchone() is not None

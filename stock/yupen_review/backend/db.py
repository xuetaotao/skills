# -*- coding: utf-8 -*-
"""SQLite 存储：data/review.db

- prices：各指数、商品的日收盘价（增量写入，取数失败时保留旧数据）
- macro：美元指数与中美国债收益率日序列
- valuation：蛋卷基金每天的 PE / PB 及历史百分位（接口只有当天，每次刷新累积一条）
- sources：每个标的 / 宏观序列最近一次取数的来源、条数、起止日期、错误
- meta：刷新时间、数据版本、精简版设置等
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE, "data", "review.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices(code TEXT, date TEXT, close REAL, PRIMARY KEY(code, date));
CREATE TABLE IF NOT EXISTS macro(series TEXT, date TEXT, value REAL, PRIMARY KEY(series, date));
CREATE TABLE IF NOT EXISTS valuation(
  code TEXT, date TEXT, pe REAL, pe_pct REAL, pb REAL, pb_pct REAL, PRIMARY KEY(code, date));
CREATE TABLE IF NOT EXISTS sources(
  key TEXT PRIMARY KEY, source TEXT, fetched INTEGER, first TEXT, last TEXT, ok INTEGER, error TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""


@contextmanager
def conn():
    """事务内执行，结束时提交并关闭连接（sqlite3 自带的 with 只提交不关闭）。DB_PATH 在调用时读取，测试可替换。"""
    c = sqlite3.connect(DB_PATH, timeout=30)
    try:
        c.execute("PRAGMA journal_mode=WAL")
        yield c
        c.commit()
    finally:
        c.close()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with conn() as c:
        c.executescript(SCHEMA)


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def set_meta(key, value):
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO meta VALUES(?, ?)", (key, value))


def get_meta(key, default=None):
    with conn() as c:
        row = c.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_json(key, obj):
    set_meta(key, json.dumps(obj, ensure_ascii=False))


def get_json(key, default=None):
    v = get_meta(key)
    return json.loads(v) if v else default


def save_prices(code, rows):
    with conn() as c:
        c.executemany("INSERT OR REPLACE INTO prices VALUES(?, ?, ?)", [(code, d, v) for d, v in rows])


def save_macro(series, rows):
    with conn() as c:
        c.executemany("INSERT OR REPLACE INTO macro VALUES(?, ?, ?)", [(series, d, v) for d, v in rows])


def load_prices():
    """{代码: [(日期, 收盘)]}，按日期升序。"""
    out = {}
    with conn() as c:
        for code, d, v in c.execute("SELECT code, date, close FROM prices ORDER BY code, date"):
            out.setdefault(code, []).append((d, v))
    return out


def load_macro():
    out = {}
    with conn() as c:
        for s, d, v in c.execute("SELECT series, date, value FROM macro ORDER BY series, date"):
            out.setdefault(s, []).append((d, v))
    return out


def save_valuation(rows):
    """rows：[(代码, 日期, pe, pe_pct, pb, pb_pct)]"""
    with conn() as c:
        c.executemany("INSERT OR REPLACE INTO valuation VALUES(?, ?, ?, ?, ?, ?)", rows)


def load_valuation():
    """{代码: [(日期, {pe, pe_pct, pb, pb_pct})]}，按日期升序。"""
    out = {}
    with conn() as c:
        for code, d, pe, pep, pb, pbp in c.execute("SELECT * FROM valuation ORDER BY code, date"):
            out.setdefault(code, []).append((d, dict(pe=pe, pe_pct=pep, pb=pb, pb_pct=pbp)))
    return out


def last_macro_date(series):
    with conn() as c:
        row = c.execute("SELECT MAX(date) FROM macro WHERE series = ?", (series,)).fetchone()
    return row[0] if row else None


def save_source(key, source, fetched, first, last, ok, error=None):
    with conn() as c:
        if ok:
            c.execute("INSERT OR REPLACE INTO sources VALUES(?, ?, ?, ?, ?, 1, NULL, ?)",
                      (key, source, fetched, first, last, now_str()))
        else:
            # 失败时保留上一次成功的来源和日期，只记下错误
            c.execute("INSERT OR IGNORE INTO sources(key) VALUES(?)", (key,))
            c.execute("UPDATE sources SET ok = 0, error = ?, updated_at = ? WHERE key = ?", (error, now_str(), key))


def load_sources():
    cols = ["key", "source", "fetched", "first", "last", "ok", "error", "updated_at"]
    with conn() as c:
        return {r[0]: dict(zip(cols, r)) for r in c.execute(f"SELECT {','.join(cols)} FROM sources")}


def has_data():
    with conn() as c:
        return c.execute("SELECT 1 FROM prices LIMIT 1").fetchone() is not None


def ready():
    """至少完整刷新过一次且有数据；首次初始化进行到一半时为 False，页面继续显示初始化进度。"""
    return get_meta("last_refresh") is not None and has_data()

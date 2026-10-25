# -*- coding: utf-8 -*-
"""SQLite 存储：data/etf.db

- etfs：ETF 基本信息（每次刷新整表替换，已退市的 ETF 随之消失，历史快照保留）
- snapshots：每个统计日每只 ETF 的份额、价格、规模，用来算规模变化和净申赎
- index_names：中证、国证指数名称和类别缓存
- perf：每只 ETF 的区间收益（每次刷新整表替换）
- index_pe：宽基指数的滚动市盈率历史，增量更新
- meta：刷新时间、数据版本、来源统计、交叉核对结果等
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE, "data", "etf.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS etfs(
  code TEXT PRIMARY KEY, name TEXT, short TEXT, exchange TEXT, manager TEXT,
  index_code TEXT, index_name TEXT, index_key TEXT, category TEXT, list_date TEXT, updated_at TEXT, style TEXT);
CREATE TABLE IF NOT EXISTS snapshots(
  date TEXT, code TEXT, shares REAL, price REAL, scale REAL, amount REAL, PRIMARY KEY(date, code));
CREATE TABLE IF NOT EXISTS index_names(code TEXT PRIMARY KEY, name TEXT, source TEXT, asset TEXT, region TEXT, classify TEXT);
CREATE TABLE IF NOT EXISTS perf(
  code TEXT PRIMARY KEY, nav_date TEXT, nav REAL, acc_nav REAL, w1 REAL, m1 REAL, m3 REAL, m6 REAL, ytd REAL,
  y1 REAL, y2 REAL, y3 REAL, since REAL, inception TEXT);
CREATE TABLE IF NOT EXISTS index_pe(code TEXT, date TEXT, pe REAL, PRIMARY KEY(code, date));
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""
# 旧库补列：(表, 列, 类型)
MIGRATIONS = [("etfs", "style", "TEXT"), ("index_names", "classify", "TEXT")]


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


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with conn() as c:
        c.executescript(SCHEMA)
        for table, col, typ in MIGRATIONS:
            if col not in [r[1] for r in c.execute(f"PRAGMA table_info({table})")]:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")


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


ETF_COLS = ["code", "name", "short", "exchange", "manager", "index_code", "index_name", "index_key", "category", "list_date", "style"]


def save_etfs(rows):
    ts = now_str()
    with conn() as c:
        c.execute("DELETE FROM etfs")
        c.executemany(f"INSERT INTO etfs({','.join(ETF_COLS)}, updated_at) VALUES({','.join('?' * (len(ETF_COLS) + 1))})",
                      [tuple(r.get(k) for k in ETF_COLS) + (ts,) for r in rows])


def load_etfs():
    with conn() as c:
        rows = c.execute(f"SELECT {','.join(ETF_COLS)}, updated_at FROM etfs").fetchall()
    return {r[0]: dict(zip(ETF_COLS + ["updated_at"], r)) for r in rows}


PERF_COLS = ["code", "nav_date", "nav", "acc_nav", "w1", "m1", "m3", "m6", "ytd", "y1", "y2", "y3", "since", "inception"]


def save_perf(rows):
    """rows: [dict]，整表替换。"""
    with conn() as c:
        c.execute("DELETE FROM perf")
        c.executemany(f"INSERT INTO perf VALUES({','.join('?' * len(PERF_COLS))})", [tuple(r.get(k) for k in PERF_COLS) for r in rows])


def load_perf():
    with conn() as c:
        rows = c.execute(f"SELECT {','.join(PERF_COLS)} FROM perf").fetchall()
    return {r[0]: dict(zip(PERF_COLS, r)) for r in rows}


def save_pe(code, rows, replace=False):
    """rows: [(日期, 市盈率)]；replace=True 时先删掉这个指数的全部历史（月度来源每次整段重下）。"""
    with conn() as c:
        if replace:
            c.execute("DELETE FROM index_pe WHERE code = ?", (code,))
        c.executemany("INSERT OR REPLACE INTO index_pe VALUES(?, ?, ?)", [(code, d, pe) for d, pe in rows])


def last_pe_dates():
    with conn() as c:
        return dict(c.execute("SELECT code, MAX(date) FROM index_pe GROUP BY code").fetchall())


def load_pe():
    """{指数代码: [(日期, 市盈率)]}，按日期升序。"""
    out = {}
    with conn() as c:
        for code, d, pe in c.execute("SELECT code, date, pe FROM index_pe ORDER BY code, date"):
            out.setdefault(code, []).append((d, pe))
    return out


def save_snapshot(day, rows):
    """rows: [(code, shares, price, scale, amount)]；同一天重复刷新时整天替换。"""
    with conn() as c:
        c.execute("DELETE FROM snapshots WHERE date = ?", (day,))
        c.executemany("INSERT INTO snapshots VALUES(?, ?, ?, ?, ?, ?)", [(day,) + tuple(r) for r in rows])


def snapshot_dates():
    with conn() as c:
        return [r[0] for r in c.execute("SELECT DISTINCT date FROM snapshots ORDER BY date")]


def load_snapshot(day):
    with conn() as c:
        rows = c.execute("SELECT code, shares, price, scale, amount FROM snapshots WHERE date = ?", (day,)).fetchall()
    return {r[0]: dict(shares=r[1], price=r[2], scale=r[3], amount=r[4]) for r in rows}


def load_history(codes):
    """{代码: [(日期, 份额, 规模)]}，按日期升序。"""
    if not codes:
        return {}
    out = {}
    with conn() as c:
        q = f"SELECT code, date, shares, scale FROM snapshots WHERE code IN ({','.join('?' * len(codes))}) ORDER BY date"
        for code, d, sh, sc in c.execute(q, list(codes)):
            out.setdefault(code, []).append((d, sh, sc))
    return out


def save_index_names(rows):
    """rows: [(code, name, source, asset, region, classify)]"""
    with conn() as c:
        c.executemany("INSERT OR REPLACE INTO index_names(code, name, source, asset, region, classify) VALUES(?, ?, ?, ?, ?, ?)", rows)


def load_index_names():
    with conn() as c:
        rows = c.execute("SELECT code, name, source, asset, region, classify FROM index_names").fetchall()
    return {r[0]: dict(name=r[1], source=r[2], asset=r[3], region=r[4], classify=r[5]) for r in rows}


def has_data():
    with conn() as c:
        return c.execute("SELECT 1 FROM snapshots LIMIT 1").fetchone() is not None

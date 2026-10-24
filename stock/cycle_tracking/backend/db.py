# -*- coding: utf-8 -*-
"""SQLite 数据层：series（指标元数据）+ points（时间序列点）+ meta（全局状态）。"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE, "data", "cycles.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS series(
    code TEXT PRIMARY KEY,
    name TEXT, sector TEXT, unit TEXT, freq TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS points(
    code TEXT, date TEXT, value REAL,
    PRIMARY KEY(code, date)
);
CREATE TABLE IF NOT EXISTS meta(
    key TEXT PRIMARY KEY, value TEXT
);
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


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with conn() as c:
        c.executescript(SCHEMA)


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def replace_points(code, rows, clear=False):
    """写入 [(date, value)]，同日覆盖。clear=True 时先清空该指标。返回日期晚于原最后日期的新增条数。"""
    with conn() as c:
        last = None if clear else c.execute("SELECT MAX(date) FROM points WHERE code=?", (code,)).fetchone()[0]
        if clear:
            c.execute("DELETE FROM points WHERE code=?", (code,))
        c.executemany("INSERT OR REPLACE INTO points(code, date, value) VALUES(?,?,?)",
                      [(code, d, v) for d, v in rows])
    return sum(1 for d, _ in rows if last is None or d > last)


def set_series_meta(cfg):
    with conn() as c:
        c.execute(
            "INSERT INTO series(code,name,sector,unit,freq,updated_at) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(code) DO UPDATE SET name=excluded.name, sector=excluded.sector, "
            "unit=excluded.unit, freq=excluded.freq, updated_at=excluded.updated_at",
            (cfg["code"], cfg["name"], cfg["sector"], cfg["unit"], cfg["freq"], now_str()),
        )


def get_last_date(code):
    with conn() as c:
        return c.execute("SELECT MAX(date) FROM points WHERE code=?", (code,)).fetchone()[0]


def load_all_points():
    """一次读出全部序列：{code: [(date, value), ...]}，按日期升序。"""
    out = {}
    with conn() as c:
        for code, d, v in c.execute("SELECT code, date, value FROM points ORDER BY code, date"):
            out.setdefault(code, []).append((d, v))
    return out


def series_updated_at():
    with conn() as c:
        return dict(c.execute("SELECT code, updated_at FROM series").fetchall())


def point_count():
    with conn() as c:
        return c.execute("SELECT COUNT(*) FROM points").fetchone()[0]


def set_meta(key, value):
    with conn() as c:
        c.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (key, value))


def get_meta(key, default=None):
    with conn() as c:
        row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else default

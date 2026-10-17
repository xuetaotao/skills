# -*- coding: utf-8 -*-
"""SQLite 数据层：series（指标元数据）+ points（时间序列点）+ meta（全局状态）。"""
import os
import sqlite3
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
CREATE INDEX IF NOT EXISTS idx_points_code_date ON points(code, date);
"""


def conn():
    c = sqlite3.connect(DB_PATH)
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_db():
    with conn() as c:
        c.executescript(SCHEMA)


def upsert_points(code, rows):
    """rows: list[(date:str 'YYYY-MM-DD', value:float)]"""
    if not rows:
        return 0
    with conn() as c:
        c.executemany(
            "INSERT OR REPLACE INTO points(code, date, value) VALUES(?,?,?)",
            [(code, d, v) for d, v in rows if d and v is not None],
        )
    return len(rows)


def set_series_meta(code, name, sector, unit, freq):
    with conn() as c:
        c.execute(
            "INSERT INTO series(code,name,sector,unit,freq,updated_at) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(code) DO UPDATE SET name=excluded.name, sector=excluded.sector, "
            "unit=excluded.unit, freq=excluded.freq, updated_at=excluded.updated_at",
            (code, name, sector, unit, freq, datetime.now().strftime("%Y-%m-%d %H:%M")),
        )


def get_last_date(code):
    with conn() as c:
        row = c.execute(
            "SELECT MAX(date) FROM points WHERE code=?", (code,)
        ).fetchone()
    return row[0] if row and row[0] else None


def get_points(code, start=None, end=None):
    sql = "SELECT date, value FROM points WHERE code=?"
    args = [code]
    if start:
        sql += " AND date>=?"
        args.append(start)
    if end:
        sql += " AND date<=?"
        args.append(end)
    sql += " ORDER BY date"
    with conn() as c:
        return c.execute(sql, args).fetchall()


def set_meta(key, value):
    with conn() as c:
        c.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_meta(key, default=None):
    with conn() as c:
        row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def all_series_meta():
    with conn() as c:
        rows = c.execute(
            "SELECT code,name,sector,unit,freq,updated_at FROM series ORDER BY sector, code"
        ).fetchall()
    keys = ["code", "name", "sector", "unit", "freq", "updated_at"]
    return [dict(zip(keys, r)) for r in rows]


def last_dates_all():
    """每个指标的最近数据日期 + 最后更新时间（用于页面显示“数据更新至”）。"""
    with conn() as c:
        rows = c.execute(
            "SELECT p.code, MAX(p.date), s.updated_at FROM points p "
            "LEFT JOIN series s ON s.code=p.code GROUP BY p.code"
        ).fetchall()
    return {r[0]: {"last_date": r[1], "updated_at": r[2]} for r in rows}

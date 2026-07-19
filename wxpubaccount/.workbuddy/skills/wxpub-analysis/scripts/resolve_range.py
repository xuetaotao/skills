# -*- coding: utf-8 -*-
"""把常见中文日期短语解析成 (since, until) 两个 date 对象。

支持的口语（大小写/空格宽松）：
  - 全部 / 所有 / 全部历史 / 全部内容  -> 返回哨兵 ("ALL",) 表示走全量
  - 近一个月 / 最近 1 个月 / 近3个月     -> today - N*30 天 ~ today（"个月"按 30 天近似）
  - 近30天 / 最近 7 天 / 近2周          -> today - N 天 / N*7 天 ~ today
  - 2026年至今 / 今年以来 / 今年         -> 当年 1/1 ~ today
  - 2026年                              -> 2026-01-01 ~ 2026-12-31
  - 2026年5月 / 2026年5月1日            -> 该月/该日 ~ 当月末/当天
  - 本月                                -> 当月 1 号 ~ today
  - 上周                                -> 上周一 ~ 上周日
  - 2026-05-27 到/至/~/— 2026-07-01     -> 显式区间

纯标准库实现，today 可注入便于测试。无法识别返回 None。
"""
import re
from datetime import date, timedelta

_CN = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
       "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _cn_int(s):
    s = s.strip()
    if s.isdigit():
        return int(s)
    if s in _CN:
        return _CN[s]
    if "十" in s:
        a, _, b = s.partition("十")
        tens = _CN.get(a, 1) if a else 1
        ones = _CN.get(b, 0) if b else 0
        return tens * 10 + ones
    return None


def _parse_ymd(text):
    """从文本里抠出第一个 YYYY年M月D日 / YYYY-M-D，返回 date。"""
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})?\s*月\s*(\d{1,2})?\s*日?", text)
    if m:
        y = int(m.group(1))
        mo = int(m.group(2)) if m.group(2) else 1
        d = int(m.group(3)) if m.group(3) else 1
        return date(y, mo, d)
    m2 = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m2:
        return date(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
    return None


def _month_end(d):
    ny = d.year + 1 if d.month == 12 else d.year
    nm = 1 if d.month == 12 else d.month + 1
    return date(ny, nm, 1) - timedelta(days=1)


def resolve(phrase, today=None):
    today = today or date.today()
    p = (phrase or "").strip()

    # 全量哨兵
    if re.search(r"^(全部|所有|全部历史|全部内容|所有文章|全量|整个历史)$", p.replace(" ", "")):
        return ("ALL",)

    # 显式区间：A 到/至/~/-  B
    m = re.search(r"(.+?)\s*(?:到|至|~|—|-)\s*(.+)", p)
    if m:
        a = _parse_ymd(m.group(1)) or _parse_ymd(p)
        b = _parse_ymd(m.group(2))
        if a and b:
            return (a, b)

    # 今年 / 某年至今 / 以来
    ym = re.search(r"(\d{4})\s*年", p)
    if "至今" in p or "以来" in p or "今年" in p or "本年" in p:
        y = int(ym.group(1)) if (ym and "今年" not in p and "本年" not in p) else today.year
        return (date(y, 1, 1), today)

    # 整年：2026年
    if re.search(r"^\d{4}\s*年$", p.replace(" ", "")):
        y = int(ym.group(1))
        return (date(y, 1, 1), date(y, 12, 31))

    # 某年某月 / 某年某月某日
    md = _parse_ymd(p)
    if md and re.search(r"\d{4}\s*年", p) and "月" in p:
        if re.search(r"\d{1,2}\s*日", p):        # 带了具体日 -> 当天为 until
            return (md, md)
        return (md, _month_end(md))              # 只到月 -> 当月末

    # 近 N 天 / 周 / 个月
    near = re.search(r"近\s*(\d+|[一二两三四五六七八九十]+)\s*(天|周|个月|月)", p)
    if near:
        n = _cn_int(near.group(1))
        if n is None:
            return None
        unit = near.group(2)
        if "天" in unit:
            return (today - timedelta(days=n), today)
        if "周" in unit:
            return (today - timedelta(days=n * 7), today)
        if "月" in unit:                          # "个月" 按 30 天近似
            return (today - timedelta(days=n * 30), today)

    # 本月
    if "本月" in p:
        return (date(today.year, today.month, 1), today)

    # 上周（上周一~上周日）
    if "上周" in p:
        this_mon = today - timedelta(days=today.weekday())
        last_sun = this_mon - timedelta(days=1)
        last_mon = last_sun - timedelta(days=6)
        return (last_mon, last_sun)

    return None


if __name__ == "__main__":
    import sys
    ph = sys.argv[1] if len(sys.argv) > 1 else "近一个月"
    r = resolve(ph)
    print(f"phrase={ph!r} -> {r}")

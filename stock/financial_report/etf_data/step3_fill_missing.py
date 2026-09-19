# -*- coding: utf-8 -*-
"""
Step3: 串行补抓
  a) 失败的 F10 概况页(跟踪标的/基金类型)
  b) 全部缺失的 mobapi 资产净值(ENDNAV) —— 并发会被风控, 改为串行 + 延迟
"""
import json
import random
import re
import time
from urllib.request import Request, urlopen

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
IN_FILE = "etf_detail.json"
OUT_FILE = "etf_detail.json"

PAT_TRACK = re.compile(r"<th>跟踪标的</th><td>(.*?)</td>", re.S)
PAT_FTYPE = re.compile(r"<th>基金类型</th><td>(.*?)</td>", re.S)
PAT_MGFEE = re.compile(r"<th>管理费率</th><td>(.*?)</td>", re.S)


def http_get(url, headers=None, timeout=25, retries=4):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    for i in range(retries):
        try:
            req = Request(url, headers=h)
            with urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            if i == retries - 1:
                return None
            time.sleep(1.0 * (i + 1) + random.random())
    return None


def strip_tag(s):
    if s is None:
        return None
    s = re.sub(r"<[^>]+>", "", s)
    return s.replace("&nbsp;", " ").strip()


def fetch_f10(code):
    raw = http_get("https://fundf10.eastmoney.com/jbgk_{}.html".format(code),
                   headers={"Referer": "https://fundf10.eastmoney.com/"})
    if raw is None:
        return None
    html = raw.decode("utf-8", errors="ignore")
    m = PAT_TRACK.search(html)
    t = PAT_FTYPE.search(html)
    g = PAT_MGFEE.search(html)
    return {
        "track": strip_tag(m.group(1)) if m else None,
        "ftype": strip_tag(t.group(1)) if t else None,
        "mgfee": strip_tag(g.group(1)) if g else None,
    }


def fetch_mobapi(code):
    url = ("https://fundmobapi.eastmoney.com/FundMNewApi/FundMNBasicInformation"
           "?FCODE={}&deviceid=1&plat=Android&product=EFund&version=6.2.8".format(code))
    raw = http_get(url, headers={"Referer": "https://fund.eastmoney.com/"})
    if raw is None:
        return None
    try:
        d = json.loads(raw.decode("utf-8", errors="ignore"))
    except Exception:
        return None
    dd = d.get("Datas") or {}
    if not dd.get("FCODE"):
        return None
    return {
        "endnav": dd.get("ENDNAV"),
        "dwjz": dd.get("DWJZ"),
        "fsrq": dd.get("FSRQ"),
        "jjgs": dd.get("JJGS"),
        "ftype_m": dd.get("FTYPE"),
    }


def main():
    with open(IN_FILE, encoding="utf-8") as f:
        rows = json.load(f)

    need_f10 = [r for r in rows if not r.get("ftype")]
    need_api = [r for r in rows if not r.get("endnav")]
    print("需补 F10: {} 只; 需补资产净值: {} 只\n".format(len(need_f10), len(need_api)))

    ok_f10 = ok_api = 0
    for i, r in enumerate(rows, 1):
        if not r.get("ftype"):
            d = fetch_f10(r["code"])
            time.sleep(0.3 + random.random() * 0.4)
            if d:
                r.update(d)
                ok_f10 += 1
        if not r.get("endnav"):
            d = fetch_mobapi(r["code"])
            time.sleep(0.35 + random.random() * 0.5)
            if d:
                r.update(d)
                ok_api += 1
        if i % 25 == 0:
            print("  进度 {}/{}  (补F10成功{}, 补净值成功{})".format(i, len(rows), ok_f10, ok_api))

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)

    print("\n补抓完成: F10 {}, 资产净值 {}".format(ok_f10, ok_api))
    miss_t = [r["code"] for r in rows if not r.get("ftype")]
    miss_n = [r["code"] for r in rows if not r.get("endnav")]
    print("仍缺基金类型: {}".format(miss_t))
    print("仍缺资产净值: {}".format(miss_n))

    print("\n=== 口径对比: 市值 vs 资产净值 (前15只, 按市值降序) ===")
    print("{:<8} {:<18} {:>10} {:>10} {:>8}  {}".format(
        "代码", "名称", "市值(亿)", "净值(亿)", "差异%", "净值日期"))
    for r in rows[:15]:
        mv = r.get("mv_total") or 0
        try:
            navf = float(r.get("endnav"))
        except (TypeError, ValueError):
            navf = 0.0
        diff = (mv / navf - 1) * 100 if navf else float("nan")
        print("{:<8} {:<18} {:>10.2f} {:>10.2f} {:>8.2f}  {}".format(
            r["code"], (r["name"] or "")[:18], mv / 1e8, navf / 1e8, diff, r.get("fsrq")))

    both = []
    for r in rows:
        try:
            navf = float(r.get("endnav"))
        except (TypeError, ValueError):
            continue
        if navf and r.get("mv_total"):
            both.append((r["mv_total"] / navf - 1) * 100)
    if both:
        both.sort()
        print("\n差异% 分布: 最小{:.2f} 中位{:.2f} 最大{:.2f} (n={})".format(
            both[0], both[len(both) // 2], both[-1], len(both)))


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
Step8: 对 119 只遗漏候选逐只查询市值(批量接口会丢数据), 确保无遗漏
"""
import json
import random
import re
import time
from urllib.request import Request, urlopen

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
PAT_TRACK = re.compile(r"<th>跟踪标的</th><td>(.*?)</td>", re.S)
PAT_FTYPE = re.compile(r"<th>基金类型</th><td>(.*?)</td>", re.S)
PAT_MGFEE = re.compile(r"<th>管理费率</th><td>(.*?)</td>", re.S)
THRESHOLD = 5e9


def market_of(code):
    return "sh" if code.startswith("5") else "sz"


def tx_one(code, retries=3):
    url = "https://qt.gtimg.cn/q={}{}".format(market_of(code), code)
    for i in range(retries):
        try:
            req = Request(url, headers={"User-Agent": UA, "Referer": "https://gu.qq.com/"})
            with urlopen(req, timeout=20) as r:
                raw = r.read().decode("gbk", errors="ignore")
            m = re.search(r'v_[a-z]{2}(\d{6})="(.*)"', raw)
            if not m:
                return None
            f = m.group(2).split("~")
            if len(f) < 47:
                return None
            return {"mv": float(f[45]) * 1e8, "name": f[1], "price": float(f[3]),
                    "dtype": f[46]}
        except Exception:
            if i == retries - 1:
                return None
            time.sleep(1.0 * (i + 1))
    return None


def http_get(url, headers=None, timeout=25, retries=3):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    for i in range(retries):
        try:
            req = Request(url, headers=h)
            with urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:
            if i == retries - 1:
                return None
            time.sleep(1.0 * (i + 1))
    return None


def strip_tag(s):
    if s is None:
        return None
    return re.sub(r"<[^>]+>", "", s).replace("&nbsp;", " ").strip()


def fetch_f10(code):
    raw = http_get("https://fundf10.eastmoney.com/jbgk_{}.html".format(code),
                   headers={"Referer": "https://fundf10.eastmoney.com/"})
    if raw is None:
        return {}
    html = raw.decode("utf-8", errors="ignore")
    m, t, g = PAT_TRACK.search(html), PAT_FTYPE.search(html), PAT_MGFEE.search(html)
    return {"track": strip_tag(m.group(1)) if m else None,
            "ftype": strip_tag(t.group(1)) if t else None,
            "mgfee": strip_tag(g.group(1)) if g else None}


def main():
    with open("etf_missing_cand.json", encoding="utf-8") as f:
        cand = json.load(f)
    print("逐只查询 {} 只候选...".format(len(cand)))

    ok, fail = [], []
    for i, c in enumerate(cand, 1):
        t = tx_one(c["code"])
        if t is None:
            fail.append(c["code"])
        else:
            d = dict(c)
            d.update({"mv_total": t["mv"], "price": t["price"], "dtype": t["dtype"]})
            ok.append(d)
        time.sleep(0.12 + random.random() * 0.1)
        if i % 30 == 0:
            print("  进度 {}/{}".format(i, len(cand)))

    print("\n查到: {} 只; 查不到: {} 只 {}".format(len(ok), len(fail), fail))

    big = [c for c in ok if c["mv_total"] > THRESHOLD]
    big.sort(key=lambda x: -x["mv_total"])
    print("规模>50亿: {} 只".format(len(big)))

    # 与 step7 结果合并去重
    try:
        with open("etf_missing_big.json", encoding="utf-8") as f:
            prev = json.load(f)
    except FileNotFoundError:
        prev = []
    merged = {c["code"]: c for c in prev}
    for c in big:
        merged.setdefault(c["code"], c)
    merged = sorted(merged.values(), key=lambda x: -x["mv_total"])
    print("与 step7 合并后: {} 只".format(len(merged)))

    # 补抓缺失的 F10
    need = [c for c in merged if not c.get("ftype")]
    print("需补 F10: {} 只".format(len(need)))
    for i, c in enumerate(need, 1):
        c.update(fetch_f10(c["code"]))
        time.sleep(0.25 + random.random() * 0.25)

    with open("etf_missing_final.json", "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=1)

    print("\n=== 遗漏且>50亿的最终清单 ({} 只) ===".format(len(merged)))
    for c in merged:
        print("  {:<8} {:<22} {:<30} {:>9.2f}亿".format(
            c["code"], c["name"][:22], str(c.get("track"))[:30], c["mv_total"] / 1e8))

    nomv = [c["code"] for c in merged if not c.get("mv_total")]
    notrack = [c["code"] for c in merged if not c.get("track")]
    print("\n缺规模: {}  缺跟踪指数: {}".format(nomv, notrack))


if __name__ == "__main__":
    main()

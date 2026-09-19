# -*- coding: utf-8 -*-
"""
Step7: 对遗漏的 119 只候选 ETF, 用腾讯批量行情查市值, 筛出>50亿, 并补抓 F10 跟踪指数
"""
import json
import re
import time
import random
from urllib.request import Request, urlopen

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
PAT_TRACK = re.compile(r"<th>跟踪标的</th><td>(.*?)</td>", re.S)
PAT_FTYPE = re.compile(r"<th>基金类型</th><td>(.*?)</td>", re.S)
PAT_MGFEE = re.compile(r"<th>管理费率</th><td>(.*?)</td>", re.S)


def market_of(code):
    return "sh" if code.startswith("5") else "sz"


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


def tx_batch(codes, retries=3):
    q = ",".join("{}{}".format(market_of(c), c) for c in codes)
    url = "https://qt.gtimg.cn/q=" + q
    out = {}
    for i in range(retries):
        try:
            req = Request(url, headers={"User-Agent": UA, "Referer": "https://gu.qq.com/"})
            with urlopen(req, timeout=30) as r:
                raw = r.read().decode("gbk", errors="ignore")
            break
        except Exception:
            if i == retries - 1:
                return out
            time.sleep(1.5 * (i + 1))
    for line in raw.split(";"):
        line = line.strip()
        m = re.match(r'v_[a-z]{2}(\d{6})="(.*)"', line)
        if not m:
            continue
        code, body = m.group(1), m.group(2)
        f = body.split("~")
        try:
            if len(f) > 46 and f[46] == "ETF":
                out[code] = {"mv": float(f[45]) * 1e8, "name": f[1], "price": float(f[3])}
            elif len(f) > 45:
                out[code] = {"mv": float(f[45]) * 1e8, "name": f[1], "price": float(f[3])}
        except (IndexError, ValueError):
            pass
    return out


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
    return {
        "track": strip_tag(m.group(1)) if m else None,
        "ftype": strip_tag(t.group(1)) if t else None,
        "mgfee": strip_tag(g.group(1)) if g else None,
    }


def main():
    with open("etf_missing_cand.json", encoding="utf-8") as f:
        cand = json.load(f)
    print("候选: {}".format(len(cand)))

    # 1) 腾讯批量查市值
    tx = {}
    for i in range(0, len(cand), 40):
        batch = [c["code"] for c in cand[i:i + 40]]
        tx.update(tx_batch(batch))
        time.sleep(0.3)
    print("腾讯返回: {} 只".format(len(tx)))

    got = []
    for c in cand:
        t = tx.get(c["code"])
        if not t:
            continue
        c = dict(c)
        c["mv_total"] = t["mv"]
        c["price"] = t["price"]
        got.append(c)
    print("有市值数据: {} 只".format(len(got)))

    big = [c for c in got if c["mv_total"] > 5e9]
    big.sort(key=lambda x: -x["mv_total"])
    print("\n=== 遗漏候选中规模>50亿的: {} 只 ===".format(len(big)))
    for c in big:
        print("  {:<8} {:<24} {:>9.2f}亿  {}".format(
            c["code"], c["name"][:24], c["mv_total"] / 1e8, c["ftype"]))

    # 2) 补抓 F10
    print("\n补抓 F10 跟踪指数...")
    for i, c in enumerate(big, 1):
        d = fetch_f10(c["code"])
        c.update(d)
        time.sleep(0.3 + random.random() * 0.3)
        if i % 15 == 0:
            print("  进度 {}/{}".format(i, len(big)))

    with open("etf_missing_big.json", "w", encoding="utf-8") as f:
        json.dump(big, f, ensure_ascii=False, indent=1)

    print("\n=== 补抓结果(前30) ===")
    for c in big[:30]:
        print("  {:<8} {:<22} {:<26} {:>9.2f}亿".format(
            c["code"], c["name"][:22], str(c.get("track"))[:26], c["mv_total"] / 1e8))
    miss = [c["code"] for c in big if not c.get("ftype")]
    print("\n仍缺基金类型: {}".format(miss))


if __name__ == "__main__":
    main()

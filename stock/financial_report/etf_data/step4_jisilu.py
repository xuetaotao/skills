# -*- coding: utf-8 -*-
"""
Step4: 从集思录拉全市场 ETF 列表
集思录是专业 ETF 数据源, 单接口同时提供: 规模 / 跟踪指数(代码+名称) / 份额 / 净值 / 净值日期
"""
import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
URL = "https://www.jisilu.cn/data/etf/etf_list/"
OUT = "jisilu_etf.json"


def post(params, retries=4):
    url = URL + "?" + urlencode(params)
    data = urlencode({}).encode()
    for i in range(retries):
        try:
            req = Request(url, data=data, headers={
                "User-Agent": UA,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://www.jisilu.cn/data/etf/",
            })
            with urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode("utf-8", errors="ignore"))
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(1.5 * (i + 1))
    return None


def main():
    ts = int(time.time() * 1000)
    all_rows, page = [], 1
    while True:
        d = post({"___jsl": "LST___t=" + str(ts), "rp": 500, "page": page})
        rows = d.get("rows") or []
        if not rows:
            break
        all_rows.extend([r["cell"] for r in rows])
        total = d.get("total")
        print("  page {} -> {} / {}".format(page, len(all_rows), total))
        if len(all_rows) >= (total or 0):
            break
        page += 1
        time.sleep(0.4)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, ensure_ascii=False, indent=1)
    print("\n集思录 ETF 总数: {}".format(len(all_rows)))

    print("\n=== 字段样例(510300) ===")
    for r in all_rows:
        if r.get("fund_id") == "510300":
            print(json.dumps(r, ensure_ascii=False, indent=1))
            break

    print("\n=== amount 单位校验: 用 净值x份额 反推 ===")
    print("{:<8} {:<18} {:>12} {:>10} {:>12} {:>10}".format(
        "代码", "名称", "amount", "份额(亿)", "净值x份额(亿)", "比值"))
    cnt = 0
    for r in all_rows:
        try:
            amt = float(r.get("amount"))
            unit = float(r.get("unit_total"))       # 单位: 亿份
            nav = float(r.get("fund_nav"))
        except (TypeError, ValueError):
            continue
        if nav <= 0 or unit <= 0:
            continue
        implied_yi = nav * unit                     # 亿元
        ratio = amt / implied_yi if implied_yi else float("nan")
        print("{:<8} {:<18} {:>12.0f} {:>10.2f} {:>12.2f} {:>10.4f}".format(
            r.get("fund_id", ""), (r.get("fund_nm") or "")[:18],
            amt, unit, implied_yi, ratio))
        cnt += 1
        if cnt >= 8:
            break


if __name__ == "__main__":
    main()

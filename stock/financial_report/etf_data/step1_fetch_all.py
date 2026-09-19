# -*- coding: utf-8 -*-
"""
Step1: 从东方财富延时行情接口拉全市场 ETF 列表 + 规模数据
数据源: push2delay.eastmoney.com (push2 主域在本机网络被拦截, 延时节点可用)
f20 = 总市值(元), f21 = 流通市值(元); 对 ETF 而言 f20 = 最新价 x 总份额
"""
import json
import time
import urllib.request

BASE = "https://push2delay.eastmoney.com/api/qt/clist/get"
FS = "b:MK0021,b:MK0022,b:MK0023,b:MK0024"
FIELDS = "f12,f14,f2,f3,f20,f21"
OUT = "etf_all.json"


def fetch_page(pn, pz=100, retries=3):
    url = "{}?pn={}&pz={}&po=1&np=1&fltt=2&invt=2&fid=f20&fs={}&fields={}".format(
        BASE, pn, pz, FS, FIELDS
    )
    for i in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
                    "Referer": "https://quote.eastmoney.com/",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(1.5 * (i + 1))


def main():
    rows, pn, total = [], 1, None
    while True:
        d = fetch_page(pn)
        if not d.get("data") or not d["data"].get("diff"):
            break
        total = d["data"]["total"]
        rows.extend(d["data"]["diff"])
        print("  page {} -> {} / {}".format(pn, len(rows), total))
        if len(rows) >= total:
            break
        pn += 1
        time.sleep(0.25)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)

    print("\n总计抓取: {} 只, 接口声明 total={}".format(len(rows), total))
    big = [r for r in rows if isinstance(r.get("f20"), (int, float)) and r["f20"] > 5e9]
    print("规模 > 50 亿 (按 f20 口径): {} 只".format(len(big)))
    print("\nTop15 预览:")
    for r in sorted(big, key=lambda x: -x["f20"])[:15]:
        print("  {:8} {:<22} {:>10.2f} 亿".format(
            r["f12"], r["f14"], r["f20"] / 1e8))


if __name__ == "__main__":
    main()

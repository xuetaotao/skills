# -*- coding: utf-8 -*-
"""
Step9: 验证腾讯查不到的 59 只候选是否为"未上市/无行情"状态
双路验证: a) 东财 ulist.np 指定代码查行情  b) F10 gmbd 查净资产规模(定期报告口径)
"""
import json
import re
import time
from urllib.request import Request, urlopen

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

PAT_NAV = re.compile(r"净资产规模：<span>\s*([\d,\.]+)亿元?\s*（截止至：([\d\-]+)）", re.S)

CODES = ['158013', '158022', '158023', '158025', '158026', '158028', '158030',
         '158031', '158032', '158037', '158038', '158039', '158041', '158042',
         '158043', '158046', '158047', '158049', '158050', '158052', '158053',
         '158055', '158056', '158057', '158058', '158059', '158061', '158063',
         '159025', '159047', '159089', '512470', '512740', '515293', '515440',
         '515470', '515540', '515940', '516040', '516163', '526020', '526090',
         '560430', '561070', '561270', '561610', '561650', '561690', '562110',
         '562150', '562170', '562200', '562400', '562420', '562450', '589450',
         '589480', '589490', '589510']


def market_id(code):
    return "1" if code.startswith("5") else "0"


def em_ulist(codes):
    secids = ",".join("{}.{}".format(market_id(c), c) for c in codes)
    url = ("https://push2delay.eastmoney.com/api/qt/ulist.np/get?secids={}"
           "&fields=f12,f14,f20,f2&fltt=2&invt=2".format(secids))
    try:
        req = Request(url, headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"})
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        return {"err": str(e)}


def gmbd_nav(code):
    url = "https://fundf10.eastmoney.com/gmbd_{}.html".format(code)
    try:
        req = Request(url, headers={"User-Agent": UA,
                                    "Referer": "https://fundf10.eastmoney.com/"})
        with urlopen(req, timeout=25) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except Exception:
        return None
    m = PAT_NAV.search(html)
    if m:
        try:
            return {"nav_yi": float(m.group(1).replace(",", "")), "asof": m.group(2)}
        except ValueError:
            return None
    return None


def main():
    print("验证 {} 只候选是否为未上市/无行情\n".format(len(CODES)))

    # a) 东财行情
    em = {}
    for i in range(0, len(CODES), 15):
        batch = CODES[i:i + 15]
        d = em_ulist(batch)
        for it in ((d.get("data") or {}).get("diff") or []):
            em[it.get("f12")] = {"name": it.get("f14"), "mv": it.get("f20"),
                                 "price": it.get("f2")}
        time.sleep(0.3)
    print("东财返回行情: {} / {}".format(len(em), len(CODES)))

    has_price = {c: v for c, v in em.items() if v.get("price") not in (None, "-", "")}
    print("其中有有效价格的: {} 只".format(len(has_price)))

    # b) F10 净资产规模
    print("\n查 F10 净资产规模(定期报告口径)...")
    navs = {}
    for i, c in enumerate(CODES, 1):
        r = gmbd_nav(c)
        if r:
            navs[c] = r
        time.sleep(0.2)
        if i % 20 == 0:
            print("  进度 {}/{}".format(i, len(CODES)))

    print("\n=== 有净资产规模数据的(定期报告口径) ===")
    rows = []
    for c, v in navs.items():
        rows.append((c, v["nav_yi"], v["asof"]))
        print("  {:<8} {:>10.2f}亿  截止 {}".format(c, v["nav_yi"], v["asof"]))
    if not rows:
        print("  (无)")

    big = [r for r in rows if r[1] > 50]
    print("\n定期报告口径>50亿: {} 只 {}".format(len(big), big))

    out = {
        "em_quote": em,
        "has_price": has_price,
        "gmbd_nav": navs,
        "nav_over_50": big,
    }
    with open("unlisted_check.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\n结果已存 unlisted_check.json")


if __name__ == "__main__":
    main()

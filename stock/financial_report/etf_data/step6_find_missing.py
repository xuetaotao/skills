# -*- coding: utf-8 -*-
"""
Step6: 用天天基金全市场基金代码表, 找出我此前板块抓取遗漏的场内 ETF
背景: 东财 MK0021-0024 板块不含债券 ETF, 已确认 511090(30年国债ETF, 350亿) 被漏掉
"""
import json
import re
from urllib.request import Request, urlopen

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def fetch_codes():
    url = "https://fund.eastmoney.com/js/fundcode_search.js"
    req = Request(url, headers={"User-Agent": UA,
                                "Referer": "https://fund.eastmoney.com/"})
    with urlopen(req, timeout=60) as r:
        raw = r.read().decode("utf-8", errors="ignore")
    return raw


def main():
    raw = fetch_codes()
    pat = re.compile(r'\["(\d{6})","[^"]*","([^"]*)","([^"]*)"')
    allf = pat.findall(raw)
    print("全市场基金条目: {}".format(len(allf)))

    # 场内 ETF 代码规则: 沪市 5xxxxx / 深市 15xxxx、16xxxx
    def is_exchange_code(c):
        return c.startswith("5") or c.startswith("15") or c.startswith("16")

    # 候选: 交易所代码 + 简称含 ETF + 排除联接/LOF/定开
    cand = []
    for code, name, ftype in allf:
        if not is_exchange_code(code):
            continue
        if "ETF" not in name:
            continue
        if any(k in name for k in ("联接", "LOF", "定开", "发起", "指数")):
            # 简称里带"指数"的多为场外指数基金, 但 ETF 简称一般不会; 保守排除"联接"
            if "联接" in name:
                continue
        cand.append({"code": code, "name": name, "ftype": ftype})

    print("代码规则+含ETF的候选: {}".format(len(cand)))

    with open("etf_all.json", encoding="utf-8") as f:
        have = {r["f12"] for r in json.load(f)}
    print("此前已抓取: {}".format(len(have)))

    missing = [c for c in cand if c["code"] not in have]
    print("遗漏候选: {}".format(len(missing)))

    with open("etf_missing_cand.json", "w", encoding="utf-8") as f:
        json.dump(missing, f, ensure_ascii=False, indent=1)

    from collections import Counter
    print("\n遗漏候选的类型分布(top15):")
    for k, v in Counter(c["ftype"] for c in missing).most_common(15):
        print("  {:<20} {}".format(k, v))
    print("\n遗漏候选样例(前25):")
    for c in missing[:25]:
        print("  {:<8} {:<24} {}".format(c["code"], c["name"][:24], c["ftype"]))


if __name__ == "__main__":
    main()

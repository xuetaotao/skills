# -*- coding: utf-8 -*-
"""
Step10: 合并两批数据 -> 按跟踪指数去重 -> 生成最终清单
  A批: etf_detail.json       161 只 (东财 MK0021-0024 板块, 市值口径>50亿)
  B批: etf_missing_final.json 48 只 (天天基金全表差集, 主要为债券ETF)
  已排除: 59 只未上市新ETF(无行情, 净资产规模均<5亿)
"""
import json
from collections import defaultdict, Counter

CAT_A = "境内股票(A股)"
CAT_HK = "境内股票(港股通)"
CAT_QDII = "跨境/境外(QDII)"
CAT_BOND = "债券"
CAT_COMM = "商品"
CAT_MM = "货币"


def classify(r):
    ft = r.get("ftype") or ""
    tk = r.get("track") or ""
    if "货币" in ft:
        return CAT_MM
    if "海外股票" in ft:
        return CAT_QDII
    if "固收" in ft:
        return CAT_BOND
    if tk in ("黄金9999", "上海金"):
        return CAT_COMM
    if any(k in tk for k in ("上期", "豆粕", "原油", "有色金属期货")):
        return CAT_COMM
    if "其他" in ft:
        return CAT_COMM
    # 注: 不把"中华交易服务"当港股通 —— 中华半导体芯片(990001)成分股为沪深A股
    if any(k in tk for k in ("港股", "恒生", "香港")):
        return CAT_HK
    return CAT_A


def norm(r, src):
    return {
        "code": r["code"],
        "name": r.get("name"),
        "track": r.get("track"),
        "ftype": r.get("ftype"),
        "mgfee": r.get("mgfee"),
        "mv": r.get("mv_total"),       # 口径: 场内总市值(元)
        "tx_mv": r.get("tx_mv"),       # 腾讯交叉验证(亿元), A批有
        "price": r.get("price"),
        "src": src,
    }


def main():
    with open("etf_detail.json", encoding="utf-8") as f:
        a = json.load(f)
    with open("etf_missing_final.json", encoding="utf-8") as f:
        b = json.load(f)

    rows = [norm(r, "A") for r in a] + [norm(r, "B") for r in b]
    # B批的 code 字段同样存在
    print("A批 {} 只 + B批 {} 只 = {} 只 (均为市值口径>50亿)".format(
        len(a), len(b), len(rows)))

    # 去重(同一代码可能两批都有)
    bycode = {}
    for r in rows:
        bycode.setdefault(r["code"], r)
    rows = list(bycode.values())
    print("按代码去重后: {} 只".format(len(rows)))

    for r in rows:
        r["category"] = classify(r)

    # 按跟踪指数分组
    groups = defaultdict(list)
    no_track = []
    for r in rows:
        if r["track"]:
            groups[r["track"]].append(r)
        else:
            no_track.append(r)

    picked = []
    for tk, lst in groups.items():
        lst.sort(key=lambda x: -(x.get("mv") or 0))
        win = dict(lst[0])
        win["group_size"] = len(lst)
        win["group_total"] = sum(x["mv"] for x in lst)
        win["rivals"] = [{"code": x["code"], "name": x["name"], "mv": x["mv"]}
                         for x in lst[1:]]
        picked.append(win)
    for r in no_track:
        r = dict(r)
        r["group_size"] = len(no_track)
        r["group_total"] = sum(x["mv"] for x in no_track)
        r["rivals"] = [{"code": x["code"], "name": x["name"], "mv": x["mv"]}
                       for x in no_track if x["code"] != r["code"]]
        picked.append(r)

    picked.sort(key=lambda x: -(x.get("mv") or 0))
    for i, r in enumerate(picked, 1):
        r["rank"] = i

    with open("etf_final_merged.json", "w", encoding="utf-8") as f:
        json.dump(picked, f, ensure_ascii=False, indent=1)

    print("\n跟踪指数组数: {} (含 {} 只无跟踪指数的货币ETF单独列出)".format(
        len(groups), len(no_track)))
    print("最终清单: {} 只".format(len(picked)))

    print("\n分类分布:")
    for k, v in Counter(r["category"] for r in picked).most_common():
        s = sum(r["mv"] for r in picked if r["category"] == k) / 1e8
        print("  {:<20} {:>3} 只  合计 {:>8.0f} 亿".format(k, v, s))

    print("\n=== Top25 ===")
    print("{:>3} {:<8} {:<20} {:<26} {:>9} {:>4}".format(
        "#", "代码", "名称", "跟踪指数", "市值(亿)", "同指"))
    for r in picked[:25]:
        print("{:>3} {:<8} {:<20} {:<26} {:>9.1f} {:>4}".format(
            r["rank"], r["code"], (r["name"] or "")[:20], str(r["track"])[:26],
            r["mv"] / 1e8, r["group_size"]))

    print("\n=== 尾10 (边界附近) ===")
    for r in picked[-10:]:
        print("{:>3} {:<8} {:<20} {:<26} {:>9.1f} {:>4} {}".format(
            r["rank"], r["code"], (r["name"] or "")[:20], str(r["track"])[:26],
            r["mv"] / 1e8, r["group_size"], r["category"]))


if __name__ == "__main__":
    main()

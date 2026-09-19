# -*- coding: utf-8 -*-
"""
Step5: 按跟踪指数去重(保留市值最大的一只) + 腾讯行情交叉验证
规则:
  - 跟踪指数名称精确匹配分组(已人工核验 87 个名称无同指异名)
  - 组内取 场内总市值(f20) 最大者
  - 无跟踪指数的(货币 ETF)单独成组, 不适用去重规则, 全部保留
"""
import json
import re
import time
from collections import defaultdict
from urllib.request import Request, urlopen

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
IN_FILE = "etf_detail.json"
OUT_JSON = "etf_final.json"

# 跟踪指数 -> 资产大类
CAT_QDII = "跨境/境外(QDII)"
CAT_COMM = "商品"


def market_of(code):
    """判断交易所: 5/56/58/52 开头为沪市, 15/16/17 开头为深市"""
    return "sh" if code.startswith("5") else "sz"


def tx_batch(codes, retries=3):
    """腾讯行情批量接口, 返回 {code: 总市值(亿)}"""
    q = ",".join("{}{}".format(market_of(c), c) for c in codes)
    url = "https://qt.gtimg.cn/q=" + q
    out = {}
    for i in range(retries):
        try:
            req = Request(url, headers={"User-Agent": UA,
                                        "Referer": "https://gu.qq.com/"})
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
            # 腾讯字段44/45 = 流通市值/总市值, 单位: 亿元
            out[code] = float(f[45])
        except (IndexError, ValueError):
            pass
    return out


def classify(r):
    """资产大类划分"""
    ft = r.get("ftype") or ""
    tk = r.get("track") or ""
    if "货币" in ft:
        return "货币"
    if "海外股票" in ft:
        return CAT_QDII
    if "其他" in ft:  # 指数型-其他: 黄金9999 / 上海金 等商品
        return CAT_COMM
    if tk in ("黄金9999", "上海金"):
        return CAT_COMM
    # 指数型-股票: 区分 A股 / 港股通
    if any(k in tk for k in ("港股", "恒生", "香港", "中华交易服务")):
        return "境内股票(港股通标的)"
    return "境内股票(A股)"


def main():
    with open(IN_FILE, encoding="utf-8") as f:
        rows = json.load(f)
    print("原始: {} 只 (规模>50亿, 市值口径)".format(len(rows)))

    # ---- 腾讯交叉验证 ----
    print("\n用腾讯行情交叉验证市值...")
    tx = {}
    for i in range(0, len(rows), 40):
        batch = [r["code"] for r in rows[i:i + 40]]
        tx.update(tx_batch(batch))
        time.sleep(0.3)
    print("  腾讯返回 {} 只".format(len(tx)))

    diffs = []
    for r in rows:
        c = r["code"]
        r["tx_mv"] = tx.get(c)
        if tx.get(c) and r.get("mv_total"):
            diffs.append(abs(r["mv_total"] / 1e8 - tx[c]) / tx[c] * 100)
    if diffs:
        diffs.sort()
        print("  东财 vs 腾讯 市值差异: 中位{:.2f}% 最大{:.2f}% (n={})".format(
            diffs[len(diffs) // 2], diffs[-1], len(diffs)))
        over3 = [r for r in rows
                 if r.get("tx_mv") and r.get("mv_total")
                 and abs(r["mv_total"] / 1e8 - r["tx_mv"]) / r["tx_mv"] * 100 > 3]
        print("  差异>3% 的: {} 只 {}".format(
            len(over3), [(r["code"], r["name"], round(r["mv_total"] / 1e8, 1),
                          r["tx_mv"]) for r in over3[:8]]))

    # ---- 分类 ----
    for r in rows:
        r["category"] = classify(r)

    # ---- 按跟踪指数去重 ----
    groups = defaultdict(list)
    no_track = []
    for r in rows:
        tk = r.get("track")
        if tk:
            groups[tk].append(r)
        else:
            no_track.append(r)

    picked = []
    for tk, lst in groups.items():
        lst.sort(key=lambda x: -(x.get("mv_total") or 0))
        win = lst[0]
        win = dict(win)
        win["group_size"] = len(lst)
        win["group_total_mv"] = sum(x["mv_total"] for x in lst)
        win["rivals"] = [{"code": x["code"], "name": x["name"],
                          "mv": x["mv_total"]} for x in lst[1:]]
        picked.append(win)

    for r in no_track:
        r = dict(r)
        r["group_size"] = len(no_track)
        r["group_total_mv"] = sum(x["mv_total"] for x in no_track)
        r["rivals"] = [{"code": x["code"], "name": x["name"], "mv": x["mv_total"]}
                       for x in no_track if x["code"] != r["code"]]
        r["track"] = None
        picked.append(r)

    picked.sort(key=lambda x: -(x.get("mv_total") or 0))

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(picked, f, ensure_ascii=False, indent=1)

    print("\n去重后: {} 只 (87个跟踪指数 -> 保留最大, 外加 {} 只无跟踪指数)".format(
        len(picked), len(no_track)))
    from collections import Counter
    print("\n分类分布:")
    for k, v in Counter(r["category"] for r in picked).most_common():
        print("  {:<24} {}".format(k, v))

    print("\n=== 最终清单 Top20 ===")
    print("{:<8} {:<20} {:<26} {:>9} {:>5} {}".format(
        "代码", "名称", "跟踪指数", "市值(亿)", "同指", "类别"))
    for r in picked[:20]:
        print("{:<8} {:<20} {:<26} {:>9.1f} {:>5} {}".format(
            r["code"], (r["name"] or "")[:20], str(r.get("track"))[:26],
            r["mv_total"] / 1e8, r["group_size"], r["category"]))


if __name__ == "__main__":
    main()

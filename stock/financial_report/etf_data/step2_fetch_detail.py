# -*- coding: utf-8 -*-
"""
Step2: 对规模>50亿的 ETF, 抓取
  a) F10 概况页 -> 跟踪标的 / 基金类型 / 成立日期 / 管理费率
  b) 东财移动端接口 -> ENDNAV(基金资产净值) / DWJZ(单位净值) / FSRQ(净值日期) / 基金公司
用于: 跟踪指数去重 + 规模口径交叉核对
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
IN_FILE = "etf_all.json"
OUT_FILE = "etf_detail.json"
THRESHOLD = 5e9  # 50 亿

PAT_TRACK = re.compile(r"<th>跟踪标的</th><td>(.*?)</td>", re.S)
PAT_FTYPE = re.compile(r"<th>基金类型</th><td>(.*?)</td>", re.S)
PAT_MGFEE = re.compile(r"<th>管理费率</th><td>(.*?)</td>", re.S)


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
            time.sleep(1.2 * (i + 1))
    return None


def strip_tag(s):
    if s is None:
        return None
    s = re.sub(r"<[^>]+>", "", s)
    return s.replace("&nbsp;", " ").strip()


def fetch_f10(code):
    url = "https://fundf10.eastmoney.com/jbgk_{}.html".format(code)
    raw = http_get(url, headers={"Referer": "https://fundf10.eastmoney.com/"})
    if raw is None:
        return {}
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
        return {}
    try:
        d = json.loads(raw.decode("utf-8", errors="ignore"))
    except Exception:
        return {}
    dd = d.get("Datas") or {}
    return {
        "endnav": dd.get("ENDNAV"),
        "dwjz": dd.get("DWJZ"),
        "fsrq": dd.get("FSRQ"),
        "jjgs": dd.get("JJGS"),
        "shortname": dd.get("SHORTNAME"),
        "ftype_m": dd.get("FTYPE"),
    }


def work(item):
    code = item["f12"]
    out = {
        "code": code,
        "name": item["f14"],
        "price": item.get("f2"),
        "mv_total": item.get("f20"),   # 口径A: 场内总市值 = 最新价 x 总份额
        "mv_float": item.get("f21"),
    }
    out.update(fetch_f10(code))
    out.update(fetch_mobapi(code))
    return out


def main():
    with open(IN_FILE, encoding="utf-8") as f:
        rows = json.load(f)
    big = [r for r in rows if isinstance(r.get("f20"), (int, float)) and r["f20"] > THRESHOLD]
    big.sort(key=lambda x: -x["f20"])
    print("待抓取明细: {} 只\n".format(len(big)))

    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(work, it): it["f12"] for it in big}
        for fu in as_completed(futs):
            try:
                results.append(fu.result())
            except Exception as e:
                print("  FAIL {} : {}".format(futs[fu], e))
            done += 1
            if done % 20 == 0:
                print("  进度 {}/{}".format(done, len(big)))

    results.sort(key=lambda x: -(x.get("mv_total") or 0))
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)

    miss_t = [r for r in results if not r.get("track")]
    print("\n抓取完成: {} 只; 缺跟踪标的: {} 只".format(len(results), len(miss_t)))
    print("\n=== 规模口径对比 (前12只) ===")
    print("{:<8} {:<20} {:>11} {:>11} {:>8}".format("代码", "名称", "市值(亿)", "资产净值(亿)", "差异%"))
    for r in results[:12]:
        mv = r.get("mv_total") or 0
        nav = r.get("endnav")
        try:
            navf = float(nav)
        except (TypeError, ValueError):
            navf = 0.0
        diff = (mv / navf - 1) * 100 if navf else float("nan")
        print("{:<8} {:<20} {:>11.2f} {:>11.2f} {:>8.2f}".format(
            r["code"], (r["name"] or "")[:20], mv / 1e8, navf / 1e8, diff))

    print("\n=== 基金类型分布 ===")
    from collections import Counter
    c = Counter((r.get("ftype") or "未知") for r in results)
    for k, v in c.most_common():
        print("  {:<20} {}".format(k, v))


if __name__ == "__main__":
    main()

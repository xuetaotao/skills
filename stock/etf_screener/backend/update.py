# -*- coding: utf-8 -*-
"""更新：交易所 ETF 列表与份额 + 新浪价格 → 当日规模快照；腾讯行情交叉核对。

命令行：python -m backend.update

交易所列表、份额或价格任何一项取不到时，本次不写入（保留上次的数据），避免一个交易所的 ETF 整体“消失”。
"""
import re
import statistics
import sys
import time
import traceback
from datetime import date, datetime, timedelta

from . import db, fetchers
from .config import CROSSCHECK_TOP, CROSSCHECK_WARN, EQUITY, HK_WORDS, SSE_SUBCLASS, VAL_STYLES, VAL_YEARS

INDEX_NAMES_REFRESH_DAYS = 7
COMMODITY_RE = re.compile(r"黄金ETF|金ETF|上海金|黄金9999|豆粕|期货|能源化工|白银")
# 两种黄金现货基准：深交所用这两个代码，上交所只能从东财 F10 的“跟踪标的”判断
GOLD = {"AU9999": "黄金9999（上金所 Au99.99 现货）", "SHAU": "上海金（上金所集中定价合约）"}

# 官方指数类别 → 类型。中证给中文类别；国证给类型代码，看末两位
CS_STYLE = {"规模": "宽基", "综合": "宽基", "行业": "行业", "主题": "主题", "策略": "策略", "风格": "策略",
            "利率债": "利率债", "信用债": "信用债", "可转债": "可转债"}
CN_STYLE = {"00": "宽基", "05": "宽基", "01": "行业", "03": "主题", "02": "策略", "04": "策略"}
# 官网查不到类别时（多为港股、海外指数）按名称判断，依次匹配：策略 → 宽基 → 行业，其余算主题
STRATEGY_RE = re.compile(r"红利|股息|低波|价值|成长|质量|现金流|基本面|等权|动量")
BROAD_RE = re.compile(r"纳斯达克100|纳指100|标准普尔500|标普500|恒生指数|恒指|恒生中国企业|恒生中国（香港上市）|恒生港股通50|日经225|"
                      r"道琼斯工业|东证|DAX|^德国|CAC40|富时100|富时中国A50|MSCI中国A50|MSCI中国A股|美国50|亚太精选|新兴亚洲|"
                      r"沙特|巴西|中证100")
INDUSTRY_RE = re.compile(r"银行|证券|保险|非银|金融|地产|医疗保健|医药|生物科技|消费|石油|天然气|能源|有色|电网|公用事业|通信|半导体")
LEGULEGU_GAP = 3            # 乐咕乐股连续请求十几次会被限流（429 / 504），每次间隔几秒
LEGULEGU_RETRY_GAP = 10     # 被限流的最后再各重试一次
VAL_RECHECK_DAYS = 7        # 两个来源都没有数据的指数，隔几天再查一次


def norm(name):
    """指数名称归一化，用于把深交所行情代码（如 399300）对到中证官方代码（000300）。"""
    s = re.sub(r"\s|指数$|（.*?）|\(.*?\)", "", name or "")
    return s.replace("指数", "").upper()


def classify(e):
    """分类：A股 / 港股 / 海外 / 债券 / 商品 / 货币。港股只认“港股、恒生、香港”三个关键词。"""
    if e["exchange"] == "SH":
        cat = SSE_SUBCLASS.get(e.get("sub_class"), "A股")
    else:
        t = e.get("tzlb") or ""
        cat = {"债券基金": "债券", "货币市场基金": "货币"}.get(t)
        if not cat:
            if COMMODITY_RE.search(e["name"]) and "黄金股" not in e["name"]:
                cat = "商品"
            elif t == "其它基金":
                cat = "海外"
            else:
                cat = "A股"
    if cat in ("A股", "海外") and any(w in f"{e['index_name']}{e['name']}" for w in HK_WORDS):
        cat = "港股"
    return cat


def style_of(e, names):
    """类型，返回 (类型, 是否官方类别)。股票类：宽基 / 行业 / 主题 / 策略；债券：利率债 / 信用债 / 可转债；商品按标的；货币。"""
    cat, key = e["category"], e.get("index_key")
    info = names.get(key) or {}
    cls = info.get("classify") or ""
    official = CS_STYLE.get(cls) if info.get("source") == "csindex" else CN_STYLE.get(cls[-2:]) if cls else None
    text = f"{e['index_name']} {e['name']}"
    if cat in EQUITY:
        if official in ("宽基", "行业", "主题", "策略"):
            return official, True
        for style, rx in (("策略", STRATEGY_RE), ("宽基", BROAD_RE), ("行业", INDUSTRY_RE)):
            if rx.search(text):
                return style, False
        return "主题", False
    if cat == "债券":
        if official in ("利率债", "信用债", "可转债"):
            return official, True
        if "转债" in text:
            return "可转债", False
        if re.search(r"国债|政金|国开|政策性|地方政府|地方债|利率", text):
            return "利率债", False
        return "信用债", False
    if cat == "商品":
        if key in GOLD or re.search(r"黄金|上海金|金ETF", text):
            return "黄金", True
        return next((w for w in ("白银", "豆粕", "有色", "能源化工") if w in text), "其他商品"), True
    return "货币", True


def update_index_names(failed):
    """中证、国证指数名称和类别，每周更新一次；失败时沿用缓存。缓存里还没有类别（旧版本建的库）时立即重下。"""
    at = db.get_meta("index_names_at")
    cached = db.load_index_names()
    if cached and at and datetime.fromisoformat(at) > datetime.now() - timedelta(days=INDEX_NAMES_REFRESH_DAYS) \
            and any(v["classify"] for v in cached.values()):
        return cached
    rows = []
    try:
        rows += [(c, v[0], "csindex", v[1], v[2], v[3]) for c, v in fetchers.csindex_names().items()]
    except Exception as e:
        failed.append(f"中证指数名称：{type(e).__name__} {str(e)[:80]}")
    try:
        cs = {r[0] for r in rows} or {c for c, v in cached.items() if v["source"] == "csindex"}
        rows += [(c, v[0], "cnindex", None, None, v[1]) for c, v in fetchers.cnindex_names().items() if c not in cs]
    except Exception as e:
        failed.append(f"国证指数名称：{type(e).__name__} {str(e)[:80]}")
    if len(rows) > 1000:
        db.save_index_names(rows)
        db.set_meta("index_names_at", datetime.now().isoformat(timespec="seconds"))
    return db.load_index_names()


def gold_benchmarks(etfs, failed):
    """上交所黄金 ETF 的跟踪标的（结果缓存，新上市的才去查）。"""
    cache = db.get_json("gold_benchmark", {})
    for e in etfs:
        if e["exchange"] == "SH" and e.get("sub_class") == "06" and not e["index_code"]:
            if e["code"] not in cache:
                try:
                    cache[e["code"]] = fetchers.em_benchmark(e["code"])
                except Exception as ex:
                    failed.append(f"黄金 ETF 跟踪标的 {e['code']}：{type(ex).__name__}")
            b = cache.get(e["code"]) or ""
            if "上海金" in b:
                e["index_code"] = "SHAU"
            elif "9999" in b:
                e["index_code"] = "AU9999"
    db.set_json("gold_benchmark", cache)


def resolve_indexes(etfs, names):
    """给每只 ETF 定 index_key（去重用的规范指数代码）和展示用的指数名称。

    交易所和中证、国证官网都查不到名称的（多为境外指数，如 SPXNTR、DAX），用 ETF 简称去掉“ETF + 管理人”代替。
    """
    for e in etfs:
        # 少数指数代码写成“000903/399903”“931024（港元）/931028（人民币）”，取第一个
        e["index_code"] = re.split(r"[/（(]", e["index_code"] or "")[0].strip()
    sse_names = {}
    for e in etfs:
        if e["exchange"] == "SH" and e["index_code"] and e["index_name"]:
            sse_names.setdefault(e["index_code"].upper(), e["index_name"])
    by_norm = {}
    for code, n in sse_names.items():
        by_norm.setdefault(norm(n), code)
    for code, v in names.items():
        if v["source"] == "csindex":
            by_norm.setdefault(norm(v["name"]), code)
    known = set(sse_names) | {c for c, v in names.items() if v["source"] == "csindex"}
    for e in etfs:
        code = (e["index_code"] or "").upper()
        if not code:
            e["index_key"] = None
            continue
        key = code
        # 官网都查不到的深市 3999xx 是中证 0009xx 指数的行情代码（399903 = 000903），中证改名后（中证100 → 中证A100）按名称对不上。
        # 399975、399986 这类本身就是中证指数代码，不能这样对
        if code not in known and code not in names and re.fullmatch(r"3999\d\d", code) and f"0009{code[4:]}" in known:
            key = f"0009{code[4:]}"
        elif code not in known:
            for n in (e["index_name"], (names.get(code) or {}).get("name")):
                if n and norm(n) in by_norm:
                    key = by_norm[norm(n)]
                    break
        e["index_key"] = key
        official = sse_names.get(key) or GOLD.get(key) or (names.get(key) or {}).get("name") or e["index_name"]
        e["index_name"] = official or re.split(r"ETF", e["short"])[0]
        e["index_guess"] = not official


def update_perf(failed):
    """区间收益整表替换；取不到或明显不全时保留上一次的。返回净值日期。"""
    try:
        rows = fetchers.em_exchange_rank()
    except Exception as e:
        failed.append(f"区间收益：{type(e).__name__} {str(e)[:120]}")
        return None
    if len(rows) < 500:
        failed.append(f"区间收益：只取到 {len(rows)} 只，没有写入")
        return None
    db.save_perf(rows)
    return max((r["nav_date"] for r in rows if r["nav_date"]), default=None)


def update_valuations(etfs, names, day, failed):
    """宽基指数的滚动市盈率历史。中证系列取中证官网日数据（增量），深证、国证系列取乐咕乐股月末数据（整段重下）；
    港股、海外指数没有公开的历史估值来源，跳过。返回 {指数代码: 来源}。"""
    keys = sorted({e["index_key"] for e in etfs if e.get("index_key") and e["style"] in VAL_STYLES and e["category"] in EQUITY})
    last = db.last_pe_dates()
    start = date.today() - timedelta(days=365 * VAL_YEARS + 30)
    src = db.get_json("val_sources", {})
    checked = db.get_json("val_checked", {})
    recheck = (date.today() - timedelta(days=VAL_RECHECK_DAYS)).isoformat()
    lg, lg_failed = None, []
    for k in keys:
        source = (names.get(k) or {}).get("source")
        if source not in ("csindex", "cnindex"):
            src[k] = None
            continue
        if (last.get(k) and last[k] >= day) or (not last.get(k) and checked.get(k, "") > recheck):
            continue
        if source == "cnindex":
            if lg is None:
                try:
                    lg = fetchers.legulegu_session()
                except Exception:
                    lg = False
            elif lg:
                time.sleep(LEGULEGU_GAP)
            if lg is False:
                lg_failed.append(k)
                continue
        try:
            if source == "csindex":
                since = date.fromisoformat(last[k]) - timedelta(days=10) if last.get(k) else start
                rows = fetchers.csindex_pe(k, since)
                if rows:
                    db.save_pe(k, rows)
                time.sleep(0.3)
            else:
                rows = [r for r in fetchers.legulegu_pe(k, lg) if r[0] >= start.isoformat()]
                if rows:
                    db.save_pe(k, rows, replace=True)
            if rows or last.get(k):
                src[k] = "csindex" if source == "csindex" else "legulegu"
            else:
                src[k] = None
                checked[k] = date.today().isoformat()
        except Exception as e:
            if source == "csindex":
                failed.append(f"指数估值 {k}：{type(e).__name__} {str(e)[:80]}")
            else:
                lg_failed.append(k)
    for k in list(lg_failed) if lg else []:
        time.sleep(LEGULEGU_RETRY_GAP)
        try:
            rows = [r for r in fetchers.legulegu_pe(k, lg) if r[0] >= start.isoformat()]
        except Exception:
            continue
        lg_failed.remove(k)
        if rows:
            db.save_pe(k, rows, replace=True)
            src[k] = "legulegu"
        elif not last.get(k):
            src[k] = None
            checked[k] = date.today().isoformat()
    if lg_failed:
        failed.append(f"乐咕乐股估值：{len(lg_failed)} 个指数没取到（{'、'.join(lg_failed[:6])}{' 等' if len(lg_failed) > 6 else ''}），"
                      "多为限流，下次刷新再取")
    src = {k: src.get(k) for k in keys}
    db.set_json("val_sources", src)
    db.set_json("val_checked", checked)
    return src


def crosscheck(rows, etfs):
    """规模最大的 CROSSCHECK_TOP 只与腾讯行情的总市值比对。"""
    top = sorted((r for r in rows if r[3]), key=lambda r: -r[3])[:CROSSCHECK_TOP]
    tx = fetchers.tencent_mcap([r[0] for r in top])
    diffs, flagged = [], []
    for code, _, _, scale, _ in top:
        t = tx.get(code)
        if not t:
            continue
        d = scale / t - 1
        diffs.append(abs(d))
        if abs(d) > CROSSCHECK_WARN:
            flagged.append(dict(code=code, name=etfs[code]["name"], ours=round(scale / 1e8, 2), tencent=round(t / 1e8, 2), diff=round(d, 4)))
    return dict(n=len(top), matched=len(diffs), missing=[r[0] for r in top if r[0] not in tx],
                median=round(statistics.median(diffs), 5) if diffs else None, flagged=flagged,
                at=datetime.now().strftime("%Y-%m-%d %H:%M"))


def run_update(progress=None):
    db.init_db()
    steps = ["指数名称", "上交所 ETF 列表", "上交所份额", "深交所 ETF 列表", "新浪行情", "腾讯行情核对", "区间收益", "宽基估值"]
    failed = []
    say = (lambda i: progress(i, len(steps), steps[i] if i < len(steps) else None)) if progress else (lambda i: None)

    say(0)
    names = update_index_names(failed)
    core = {}
    for i, (key, fn) in enumerate([("sse", fetchers.sse_list), ("sse_shares", fetchers.sse_shares),
                                   ("szse", fetchers.szse_list), ("sina", fetchers.sina_prices)], start=1):
        say(i if key != "sina" else 4)
        try:
            core[key] = fn()
        except Exception as e:
            failed.append(f"{steps[i if key != 'sina' else 4]}：{type(e).__name__} {str(e)[:120]}")
    try:
        szse_date = fetchers.szse_shares_date()
    except Exception:
        szse_date = None

    sse_date, sse_sh = core.get("sse_shares") or (None, {})
    if any(k not in core for k in ("sse", "szse", "sina")) or not sse_sh or len(core.get("sse", [])) < 300 or len(core.get("szse", [])) < 300:
        failed.append("核心数据不完整，本次没有写入，保留上次的数据")
        _finish(failed, None)
        return dict(failed=failed, n=0)

    etfs = core["sse"] + core["szse"]
    gold_benchmarks(etfs, failed)
    resolve_indexes(etfs, names)
    style_kw = set()
    for e in etfs:
        e["category"] = classify(e)
        e["style"], official = style_of(e, names)
        if not official:
            style_kw.add(e["index_key"] or e["code"])
    by_code = {e["code"]: e for e in etfs}
    prices = core["sina"]
    day = max(d for d in (sse_date, szse_date) if d)
    shares = {e["code"]: sse_sh.get(e["code"]) if e["exchange"] == "SH" else e.get("shares") for e in etfs}
    # 上交所份额接口不含货币 ETF：用腾讯行情的总市值反推份额
    lack = [c for c, s in shares.items() if not s and c in prices]
    from_tx = {}
    if lack:
        try:
            from_tx = fetchers.tencent_mcap(lack)
            for c, mcap in from_tx.items():
                shares[c] = mcap / prices[c][0]
        except Exception as e:
            failed.append(f"腾讯行情补份额：{type(e).__name__} {str(e)[:80]}")
    rows = []
    for e in etfs:
        sh = shares.get(e["code"])
        px, amount = prices.get(e["code"], (None, None))
        rows.append((e["code"], sh, px, sh * px if sh and px else None, amount))
    db.save_etfs(etfs)
    db.save_snapshot(day, rows)

    say(5)
    try:
        cc = crosscheck(rows, by_code)
        db.set_json("crosscheck", cc)
    except Exception as e:
        failed.append(f"腾讯行情核对：{type(e).__name__} {str(e)[:120]}")

    say(6)
    perf_date = update_perf(failed)
    say(7)
    val_src = update_valuations(etfs, names, day, failed)

    old = db.get_json("sources", {})
    db.set_json("sources", dict(
        sse_list=len(core["sse"]), sse_shares=len(sse_sh), sse_date=sse_date, szse_list=len(core["szse"]), szse_date=szse_date,
        sina=len(prices), index_names=len(names),
        perf=len(db.load_perf()), perf_date=perf_date or old.get("perf_date"),
        val_cs=sum(1 for v in val_src.values() if v == "csindex"), val_lg=sum(1 for v in val_src.values() if v == "legulegu"),
        val_none=sorted(k for k, v in val_src.items() if not v),
        style_kw=sorted(style_kw),
        no_price=[e["code"] for e in etfs if e["code"] not in prices],
        no_shares=[r[0] for r in rows if not r[1]],
        shares_from_tencent=sorted(from_tx),
        index_guess=[e["code"] for e in etfs if e.get("index_guess")],
    ))
    db.set_meta("snapshot_date", day)
    say(len(steps))
    _finish(failed, day)
    return dict(failed=failed, n=len(rows), day=day)


def _finish(failed, day):
    db.set_meta("last_refresh", db.now_str())
    db.set_json("last_refresh_failed", failed)
    db.set_meta("data_version", datetime.now().isoformat(timespec="seconds"))


def main():
    db.init_db()
    t = time.time()
    try:
        rep = run_update(progress=lambda d, n, label: label and print(f"  [{d}/{n}] {label}"))
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    print(f"完成：{rep['n']} 只 ETF，快照日期 {rep.get('day')}，用时 {time.time() - t:.0f}s")
    for f in rep["failed"]:
        print("  失败：", f)


if __name__ == "__main__":
    main()

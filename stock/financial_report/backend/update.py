# -*- coding: utf-8 -*-
"""数据更新入口。单项失败时保留数据库里的旧数据，并在结果和页面上列出。

步骤：申万行业分类（每周一次）→ 确定每只自选股的同行业范围 → 最新估值与市值 →
自选股与同行业的财务指标 → 企业性质 → 日收盘价与复权因子（算区间涨跌幅）→ 自选股的估值历史 → 分红记录 →
10 年期国债收益率（算股债利差）。

用法（在项目根目录）:
  python -m backend.update               # 更新全部自选股及其同行业
  python -m backend.update 600036 000333 # 只更新指定股票及其同行业（不必在自选股里）
"""
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

from . import db, fetchers
from .config import DEFAULT_WATCHLIST, FETCH_WORKERS, PRICE_YEARS, SW_REFRESH_DAYS, VALUATION_START
from .peers import cap_members, peer_group


def _err(e):
    return f"{type(e).__name__}: {str(e)[:160]}"


def update_sw(force=False):
    """申万分类每 SW_REFRESH_DAYS 天刷新一次；失败时沿用旧表。返回错误信息或 None。"""
    at = db.get_meta("sw_updated")
    cls, _ = db.load_sw()
    if cls and at and not force and datetime.now() - datetime.fromisoformat(at) < timedelta(days=SW_REFRESH_DAYS):
        return None
    try:
        classes = fetchers.fetch_sw_class()
        names = fetchers.fetch_sw_names()
    except Exception as e:
        return f"申万行业分类: {_err(e)}"
    if len(classes) < 3000 or len(names) < 100:
        return f"申万行业分类: 返回数据过少（{len(classes)} 只股票 / {len(names)} 个行业），沿用旧表"
    db.save_sw(classes, names)
    db.set_meta("sw_updated", datetime.now().isoformat(timespec="seconds"))
    return None


def fetch_one(code):
    rows = fetchers.fetch_indicators(code)
    if not rows:
        raise ValueError("接口没有返回财报数据")
    db.save_reports(code, rows)
    latest = max(rows, key=lambda r: r["REPORT_DATE"])
    db.upsert_stock(code, latest.get("SECURITY_NAME_ABBR"), latest.get("ORG_TYPE"))
    return latest


def update_prices(codes):
    """近 PRICE_YEARS 年的日收盘价：新股票整段下载，已有的从最后一天往前 10 天开始补。返回错误列表。"""
    start = (date.today() - timedelta(days=365 * PRICE_YEARS + 30)).isoformat()
    last = db.last_price_dates()
    new = [c for c in codes if c not in last]
    old = sorted((c for c in codes if c in last), key=lambda c: last[c])
    jobs = [(new[i:i + 20], start) for i in range(0, len(new), 20)]
    for i in range(0, len(old), 50):
        batch = old[i:i + 50]
        jobs.append((batch, max(start, (date.fromisoformat(last[batch[0]]) - timedelta(days=10)).isoformat())))
    errors = []
    with ThreadPoolExecutor(FETCH_WORKERS) as pool:
        futs = {pool.submit(fetchers.fetch_closes, b, s): b for b, s in jobs}
        for f in as_completed(futs):
            try:
                db.save_prices(f.result())
            except Exception as e:
                errors.append(f"日收盘价（{len(futs[f])} 只）: {_err(e)}")
    db.trim_prices(start)
    return errors


def update_factors(codes, names):
    """新浪复权因子，每只股票每天最多取一次。返回错误列表。"""
    done = db.get_json("factor_at", {})
    today = date.today().isoformat()
    todo = [c for c in codes if done.get(c) != today]
    bad = []
    with ThreadPoolExecutor(2) as pool:
        futs = {pool.submit(fetchers.fetch_adj_factors, c): c for c in todo}
        for f in as_completed(futs):
            c = futs[f]
            try:
                db.save_factors(c, f.result())
                done[c] = today
            except Exception:
                bad.append(c)
    db.set_json("factor_at", done)
    if not bad:
        return []
    have = db.load_factors()
    lost = [c for c in bad if c not in have]
    msg = f"复权因子 {len(bad)} 只没有取到（{'、'.join(names.get(c, c) for c in bad[:5])}{' 等' if len(bad) > 5 else ''}）"
    return [msg + (f"，其中 {len(lost)} 只没有旧数据，区间涨跌幅暂缺" if lost else "，沿用上次的因子")]


def run_update(codes=None, progress=None):
    """codes=None 时更新全部自选股（完整刷新）；否则只更新这些股票及其同行业。

    progress(done, total, label) 在每一步开始前回调。
    """
    db.init_db()
    db.ensure_default_watchlist(DEFAULT_WATCHLIST)
    full = codes is None
    watch = db.watchlist() if full else list(dict.fromkeys(codes))
    failed, status = [], db.get_json("fetch_status", {})
    step = [0, 3]

    def tick(label):
        if progress:
            progress(step[0], step[1], label)
        step[0] += 1

    # 1. 行业分类
    tick("申万行业分类")
    err = update_sw()
    if err:
        failed.append(err)
    cls, names = db.load_sw()

    # 2. 同行业范围与最新估值
    tick("最新估值与市值")
    raw = {}
    stock_group = {}
    for w in watch:
        g = peer_group(w, cls, names)
        if g:
            raw.setdefault(g["key"], g)
            stock_group[w] = g["key"]
    universe = set(watch).union(*[g["members"] for g in raw.values()]) if raw else set(watch)
    quotes, trade_date = [], None
    try:
        trade_date = fetchers.latest_trade_date(watch[0] if watch else "601398")
        if trade_date:
            quotes = fetchers.fetch_quotes(sorted(universe), trade_date)
            db.save_quotes(quotes)
        else:
            failed.append("估值: 没有取到最新交易日")
    except Exception as e:
        failed.append(f"估值: {_err(e)}")
    mcap = {q["code"]: q["mcap"] for q in quotes}
    if not mcap:  # 估值失败时用上次的市值决定同行业范围
        mcap = {c: q["mcap"] for c, q in db.load_quotes().items()}
    groups = {k: cap_members(g, mcap, [w for w in watch if stock_group.get(w) == k]) for k, g in raw.items()}
    targets = list(dict.fromkeys(watch + [c for g in groups.values() for c in g["members"]]))

    # 3. 财务指标（并发）
    step[1] = 7 + len(targets) + len(watch)
    names_now = {q["code"]: q["name"] for q in quotes}
    with ThreadPoolExecutor(FETCH_WORKERS) as pool:
        futs = {pool.submit(fetch_one, c): c for c in targets}
        for f in as_completed(futs):
            c = futs[f]
            tick(f"{names_now.get(c, c)} 财报")
            try:
                latest = f.result()
                status[c] = dict(at=db.now_str(), ok=True, latest=latest["REPORT_DATE"][:10])
            except Exception as e:
                status[c] = dict(status.get(c, {}), at=db.now_str(), ok=False, error=_err(e))
                if c in watch:
                    failed.append(f"{names_now.get(c, c)}（{c}）财报: {_err(e)}")
    peer_fail = [c for c in targets if c not in watch and not status.get(c, {}).get("ok")]
    if peer_fail:
        failed.append(f"同行业 {len(peer_fail)} 只股票的财报没有取到（{'、'.join(names_now.get(c, c) for c in peer_fail[:5])}"
                      f"{' 等' if len(peer_fail) > 5 else ''}），对比时缺这些公司")

    # 4. 企业性质、日收盘价、复权因子
    tick("企业性质")
    try:
        db.save_org_info(fetchers.fetch_org_info(targets))
    except Exception as e:
        failed.append(f"企业性质: {_err(e)}")
    tick("日收盘价")
    failed += update_prices(targets)
    tick("复权因子")
    failed += update_factors(targets, names_now)

    # 5. 自选股估值历史（增量）
    for w in watch:
        tick(f"{names_now.get(w, w)} 估值历史")
        last = db.last_valuation_date(w)
        start = (datetime.fromisoformat(last) - timedelta(days=10)).date().isoformat() if last else VALUATION_START
        try:
            db.save_valuation(w, fetchers.fetch_valuation_history(w, start))
        except Exception as e:
            failed.append(f"{names_now.get(w, w)} 估值历史: {_err(e)}")

    # 6. 分红与 10 年期国债收益率（股债利差）
    tick("分红记录")
    try:
        db.save_dividends(fetchers.fetch_dividends(targets))
    except Exception as e:
        failed.append(f"分红: {_err(e)}")
    tick("10 年期国债收益率")
    have = db.load_bond_yields()
    start = (date.fromisoformat(have[-1][0]) - timedelta(days=10)).isoformat() if have \
        else (date.today() - timedelta(days=365 * PRICE_YEARS + 30)).isoformat()
    try:
        db.save_bond_yields(fetchers.fetch_cgb10(start))
    except Exception as e:
        failed.append(f"10 年期国债收益率: {_err(e)}" + ("（沿用旧数据）" if have else "，股债利差暂缺"))

    # 7. 保存分组与状态
    old_groups, old_map = db.get_json("groups", {}), db.get_json("stock_group", {})
    if full:
        new_groups, new_map = groups, stock_group
    else:
        new_map = dict(old_map, **stock_group)
        new_groups = dict(old_groups, **groups)
    used = set(new_map.values())
    db.set_json("groups", {k: g for k, g in new_groups.items() if k in used})
    db.set_json("stock_group", new_map)
    db.set_json("fetch_status", status)
    at = db.now_str()
    if trade_date:
        db.set_meta("trade_date", trade_date)
    if full:  # 只更新部分股票时不算完整刷新
        db.set_meta("last_refresh", at)
        db.set_json("last_refresh_failed", failed)
    db.set_meta("data_version", datetime.now().isoformat(timespec="seconds"))
    if progress:
        progress(step[1], step[1], None)
    return dict(at=at, targets=len(targets), watch=len(watch), failed=failed)


def main():
    codes = [a for a in sys.argv[1:] if not a.startswith("--")]
    db.init_db()
    t = time.time()
    try:
        rep = run_update(codes or None, progress=lambda d, n, label: label and print(f"  [{d}/{n}] {label}"))
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    print(f"=== 更新完成 {rep['at']} | 自选 {rep['watch']} 只 | 含同行业共 {rep['targets']} 只 | "
          f"失败 {len(rep['failed'])} 项 | 用时 {time.time() - t:.0f}s ===")
    for f in rep["failed"]:
        print("  ✗", f)


if __name__ == "__main__":
    main()

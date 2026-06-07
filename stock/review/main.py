"""行情复盘汇总 - 主程序

运行方式（需用 yupen 的虚拟环境，内含 akshare/pandas 等依赖）：
    yupen/.venv/bin/python stock/review/main.py
或使用一键脚本：
    bash stock/review/run.sh
"""

import os
import sys
from collections import Counter
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import macro  # noqa: E402
import render  # noqa: E402
import summary  # noqa: E402
import watchlist  # noqa: E402
import yupen_source  # noqa: E402

OUTPUT_DIR = os.path.join(_HERE, "outputs")


def _resolve_data_date(records, market_summary) -> str:
    summary_date = market_summary.get("数据日期")
    if summary_date and summary_date != "N/A":
        return str(summary_date)
    dates = [r["data_date"] for r in records if r.get("data_date") and r["data_date"] != "N/A"]
    if not dates:
        return "N/A"
    return Counter(dates).most_common(1)[0][0]


def main() -> int:
    print("=" * 56)
    print("🌍 全球行情复盘汇总")
    print("=" * 56)
    print("正在调用鱼盆模型采集与分析数据...\n")

    records, market_summary = yupen_source.fetch_records(lookback_days=60)
    stocks_all, commodities_all = summary.split_groups(records)

    data_date = _resolve_data_date(records, market_summary)
    generated_at = yupen_source.now_text()

    # 完整版：未列出的标的默认显示
    full_stocks = summary.rank(
        summary.filter_for_version(stocks_all, watchlist.STOCK_DISPLAY, "完整版", default=True))
    full_commodities = summary.rank(
        summary.filter_for_version(commodities_all, watchlist.COMMODITY_DISPLAY, "完整版", default=True))

    # 精简版：未列出的标的默认隐藏
    simple_stocks = summary.rank(
        summary.filter_for_version(stocks_all, watchlist.STOCK_DISPLAY, "精简版", default=False))
    simple_commodities = summary.rank(
        summary.filter_for_version(commodities_all, watchlist.COMMODITY_DISPLAY, "精简版", default=False))

    # 宏观面板：汇率与利率（不进 yupen，直接取数；两个版本一致）
    usd = macro.fetch_usd_index() if watchlist.MACRO_DISPLAY.get("美元指数", True) else None
    bonds = macro.fetch_bond_yields() if watchlist.MACRO_DISPLAY.get("中美国债", True) else None

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    variants = [
        ("", full_stocks, full_commodities, "latest_review", f"review_{stamp}"),
        ("（精简版）", simple_stocks, simple_commodities, "latest_review_simple", f"review_simple_{stamp}"),
    ]
    for suffix, vstocks, vcommodities, latest_name, stamped_name in variants:
        html = render.render_html(vstocks, vcommodities, data_date, generated_at, suffix, usd, bonds)
        markdown = render.render_markdown(vstocks, vcommodities, data_date, generated_at, suffix, usd, bonds)
        for filename, content in (
            (f"{latest_name}.html", html),
            (f"{latest_name}.md", markdown),
            (f"{stamped_name}.html", html),
            (f"{stamped_name}.md", markdown),
        ):
            with open(os.path.join(OUTPUT_DIR, filename), "w", encoding="utf-8") as handle:
                handle.write(content)

    print(f"数据日期：{data_date}")
    print(f"完整版 → 全球股市 {len(full_stocks)} · 大宗 {len(full_commodities)}")
    print(f"精简版 → 全球股市 {len(simple_stocks)} · 大宗 {len(simple_commodities)}\n")
    print("趋势强度排名（完整版 · 全球股市）：")
    for record in full_stocks:
        flag = " ⚡" if record.get("changed_today") else ""
        print(f"  {record['rank']:>2}. {record['region']:<3} {record['name']:<12} "
              f"{record['status']:<3} {record['deviation_str']:>8}{flag}")

    if usd:
        chg = f"{usd['change'] * 100:+.2f}%" if usd.get("change") is not None else "--"
        print(f"\n💵 美元指数：{usd['price']:.2f}（{chg}）")
    if bonds:
        ten = next((r for r in bonds["rows"] if r["term"] == "10年"), None)
        if ten and isinstance(ten.get("cn"), (int, float)) and isinstance(ten.get("us"), (int, float)):
            print(f"🏛️ 10年期国债：中国 {ten['cn']:.2f}% / 美国 {ten['us']:.2f}%")

    print("\n📁 报告已保存：")
    print(f"   完整版 HTML: {os.path.join(OUTPUT_DIR, 'latest_review.html')}")
    print(f"   精简版 HTML: {os.path.join(OUTPUT_DIR, 'latest_review_simple.html')}")
    print(f"   （另有同名 .md 及带时间戳的历史文件）")
    print("=" * 56)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""命令行：python -m backend <命令>

  scrape     扫码登录公众号后台，抓发表记录、总览和详情页，然后重新分析
  analyze    按分析范围重建清单、报告和爆款预测基准（不联网）
  diagnose   打印星期规律、标题分级、漏斗和相关性
  predict    给标题打分（爆款预测）
  recommend  选题推荐
  range      试一下口语日期短语会被解析成什么区间
"""

import argparse
import json
import os
import sys

from . import analysis, pipeline, prediction, recommend, scraper
from .baseline import load as load_baseline
from .config import DETAIL_MODES, QR_PATH, WEEKDAYS
from .daterange import EXAMPLES, resolve


def _range_args(p):
    p.add_argument("--nl", help="口语时段，如 近一个月 / 2026年至今 / 2026年5月 / 2026-05-27 到 2026-07-01")
    p.add_argument("--since", help="起始日期 YYYY-MM-DD（含）")
    p.add_argument("--until", help="结束日期 YYYY-MM-DD（含，默认今天）")
    p.add_argument("--window", type=int, help="最近 N 天")
    p.add_argument("--all", action="store_true", help="已抓取的全部文章（默认）")


def _print_analysis(r):
    w = r["window"]
    if w.get("warning"):
        print(f"⚠ {w['warning']}")
    print(f"分析范围 {w['since']} ~ {w['until']}（{w['mode']}）：{w['articles']} 篇 / 已抓取 {w['scraped_total']} 篇")
    d = r["details"]
    print(f"有详情的 {d['with_detail']} 篇" + (f"，{len(d['empty_parse'])} 个详情快照解析为空" if d["empty_parse"] else ""))
    print(f"报告：{r['report']['path']}")
    b = r["baseline"]
    print(f"基准：具名标题杠杆 {b['lift']}×，周二占阅读 {b['tue_share_pct']}%，有效角度 {('、'.join(b['effective_angles']) or '无')}")


def cmd_scrape(args):
    job = scraper.Job(echo=True)
    job.update(running=True)
    if args.headless:
        print(f"后台运行浏览器；需要扫码时会打开二维码图片（{QR_PATH}）")

        def watch():
            import time
            opened = -1
            while job.state["running"]:
                rnd = job.state["qr_round"]
                if job.state["waiting_qr"] and rnd != opened and QR_PATH.exists() and hasattr(os, "startfile"):
                    os.startfile(str(QR_PATH))  # noqa: S606 - 打开二维码图片给用户扫
                    opened = rnd
                time.sleep(1)
        import threading
        threading.Thread(target=watch, daemon=True).start()
    try:
        r = scraper.run(job, args.details, show_browser=not args.headless)
    except scraper.ScrapeError as e:
        print(f"错误：{e}")
        return 1
    except scraper.Cancelled:
        return 130
    finally:
        job.update(running=False)
    print(f"\n抓取完成：{r['articles']} 篇发表记录，详情页成功 {r['details_ok']} 篇，失败 {r['details_failed']} 篇，用时 {r['seconds']} 秒")
    if r["archived"]:
        print(f"被覆盖的旧快照已移到 {r['archived']}")
    if not args.no_analyze:
        print()
        try:
            _print_analysis(pipeline.rerun_last())
        except ValueError as e:
            print(f"数据已抓好，但没有重新分析：{e}")
    return 1 if r["details_failed"] else 0


def cmd_analyze(args):
    try:
        r = pipeline.analyze(nl=args.nl, since=args.since, until=args.until, window=args.window, all_=args.all)
    except ValueError as e:
        print(f"错误：{e}")
        return 1
    _print_analysis(r)
    return 0


def cmd_predict(args):
    title = args.title or input("标题草稿：").strip()
    topics = prediction.split_topics(args.topics or input("主题关键词（逗号分隔，如 微信,AI,理财）：").strip())
    if not title or not topics:
        print("标题和主题关键词都不能为空")
        return 1
    b = load_baseline()
    if b is None:
        print("还没有爆款预测基准，先运行：python -m backend analyze")
        return 1
    print(prediction.render_prediction_card(prediction.score_topic_idea(title, topics, args.day, b), b))
    return 0


def cmd_recommend(args):
    try:
        r = recommend.run(ask=args.ask or "", queries=args.queries, count=args.count, day=args.day,
                          news_per_query=args.news_per_query, offline=args.offline, save=not args.no_save,
                          output_dir=args.output_dir, progress=lambda m: print(f"… {m}", file=sys.stderr))
    except FileNotFoundError as e:
        print(e)
        return 1
    if args.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(r["payload"], f, ensure_ascii=False, indent=2)
    print(r["markdown"])
    return 0


def cmd_range(args):
    for phrase in args.phrases or EXAMPLES:
        r = resolve(phrase)
        txt = "无法识别（会按全部分析）" if r is None else "全部" if r == ("ALL",) else f"{r[0]} ~ {r[1]}"
        print(f"{phrase} → {txt}")
    return 0


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="python -m backend", description="公众号数据分析（不带命令时等同 --help）")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("scrape", help="扫码登录后台，抓取最新数据并重新分析")
    p.add_argument("--details", default="missing_recent", choices=list(DETAIL_MODES),
                   help="详情页范围：" + "；".join(f"{k}={v}" for k, v in DETAIL_MODES.items()))
    p.add_argument("--headless", action="store_true", help="不显示浏览器窗口，需要扫码时打开二维码图片")
    p.add_argument("--no-analyze", action="store_true", help="抓完不重新分析")
    p.set_defaults(fn=cmd_scrape)

    p = sub.add_parser("analyze", help="重建分析清单、报告和爆款预测基准")
    _range_args(p)
    p.set_defaults(fn=cmd_analyze)

    p = sub.add_parser("diagnose", help="打印诊断：星期规律 / 标题分级 / 漏斗 / 相关性")
    p.set_defaults(fn=lambda _a: print(analysis.diagnostics()) or 0)

    p = sub.add_parser("predict", help="爆款预测：给标题草稿打分")
    p.add_argument("--title", help="标题草稿")
    p.add_argument("--topics", help="主题关键词，逗号分隔")
    p.add_argument("--day", default="周二", choices=WEEKDAYS, help="计划发文星期（默认周二）")
    p.set_defaults(fn=cmd_predict)

    p = sub.add_parser("recommend", help="选题推荐（热点 + 价值型方向）")
    p.add_argument("--ask", help="自然语言需求，如：给我推荐3个偏实用的选题，下周二发")
    p.add_argument("--queries", help="热点检索词，逗号分隔")
    p.add_argument("--count", type=int, help="通过预测的选题数量（默认 6）")
    p.add_argument("--day", help="计划发文星期（默认周二）")
    p.add_argument("--news-per-query", type=int, help="每个检索词保留的热点数")
    p.add_argument("--offline", action="store_true", help="不抓热点，只出价值型选题")
    p.add_argument("--output-dir", help="输出目录（默认 data/topic_recommendations）")
    p.add_argument("--json-out", help="另存一份结构化 JSON")
    p.add_argument("--no-save", action="store_true", help="只打印，不写文件")
    p.set_defaults(fn=cmd_recommend)

    p = sub.add_parser("range", help="测试口语时段解析")
    p.add_argument("phrases", nargs="*", help="不给就跑一遍内置示例")
    p.set_defaults(fn=cmd_range)

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(0)
    try:
        sys.exit(args.fn(args))
    except KeyboardInterrupt:
        print("\n已取消")
        sys.exit(130)

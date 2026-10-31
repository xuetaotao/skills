"""命令行：python -m backend <命令>

  prompt  按阶段拼出完整 Prompt（打印，并复制到剪贴板）
  new     新建文章
  list    列出文章
  save    把一个 Markdown 文件存为某篇文章的新版本
  check   本地自检一篇稿子（AI 腔、绝对化、长句长段、需查证的句子）
  titles  给标题打分（借用公众号工作空间的爆款预测器）
"""

import argparse
import subprocess
import sys
from pathlib import Path

from . import articles, checks, prompts, titles
from .config import SOURCES, STAGE, WEEKDAYS


def _read(path):
    return Path(path).read_text(encoding="utf-8-sig") if path else ""


def _clip(text):
    try:
        if sys.platform == "win32":
            subprocess.run("clip", input=text.encode("utf-16le"), check=True)
        elif sys.platform == "darwin":
            subprocess.run("pbcopy", input=text.encode(), check=True)
        else:
            return False
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def cmd_prompt(a):
    article_text = _read(a.file)
    topic, ideas = a.topic or "", a.ideas or ""
    if a.article:
        art = articles.get(a.article)
        topic, ideas = topic or art["topic"], ideas or art["ideas"]
        article_text = article_text or art["current"]
    text = prompts.build(a.stage, topic, ideas, article_text, {"free": a.feedback or ""})
    print(text)
    if not a.no_copy and _clip(text):
        print("\n（已复制到剪贴板）", file=sys.stderr)
    return 0


def cmd_new(a):
    art = articles.create(a.title or "", a.topic or "", a.ideas or "")
    print(f"已新建：{art['path']}")
    return 0


def cmd_list(_a):
    items = articles.list_articles()
    if not items:
        print("还没有文章。python -m backend new --title ... 或在网页上新建")
    for x in items:
        print(f"{x['id']:<40} {x['status']:<4} v{x['versions']:<3} {x['chars']:>6} 字  更新 {x['updated']}")
    return 0


def cmd_save(a):
    art = articles.save_version(a.article, _read(a.file), a.note or "", a.source)
    print(f"已存为 v{art['versions'][-1]['n']}（{art['versions'][-1]['chars']} 字）")
    return 0


def cmd_check(a):
    if a.article:
        art = articles.get(a.article)
        text, title = art["current"], art["title"]
    else:
        text, title = _read(a.file), a.title or ""
    print(checks.render_text(checks.check(text, title)))
    return 0


def cmd_titles(a):
    try:
        res = titles.score(a.titles, a.topics, a.day)
    except FileNotFoundError as e:
        print(e)
        return 1
    for r in res:
        flag = "通过" if r["prediction_pass"] else "未通过"
        print(f"《{r['title']}》 阅读 {r['read_score']} · 涨粉 {r['follow_score']} · 互动 {r['interaction']} · {flag} · {r['verdict']}")
        for s in r["suggestions"]:
            print(f"    - {s}")
    return 0


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="python -m backend", description="写作工作台命令行（网页：scripts\\start_server.bat）")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("prompt", help="拼出某个阶段的完整 Prompt")
    p.add_argument("stage", choices=list(STAGE), help="；".join(f"{k}={v['name']}" for k, v in STAGE.items()))
    p.add_argument("--topic", help="主题")
    p.add_argument("--ideas", help="我的想法")
    p.add_argument("--file", help="正文 Markdown（质量检查 / 修改反馈用）")
    p.add_argument("--article", help="从文章库取主题、想法和当前版本（文章 id，即目录名）")
    p.add_argument("--feedback", help="修改意见（修改反馈用）")
    p.add_argument("--no-copy", action="store_true", help="不复制到剪贴板")
    p.set_defaults(fn=cmd_prompt)

    p = sub.add_parser("new", help="新建文章")
    p.add_argument("--title")
    p.add_argument("--topic")
    p.add_argument("--ideas")
    p.set_defaults(fn=cmd_new)

    sub.add_parser("list", help="列出文章").set_defaults(fn=cmd_list)

    p = sub.add_parser("save", help="把 Markdown 文件存为文章的新版本")
    p.add_argument("article", help="文章 id（目录名）")
    p.add_argument("file", help="Markdown 文件")
    p.add_argument("--note", help="版本说明")
    p.add_argument("--source", default="我写的", choices=SOURCES)
    p.set_defaults(fn=cmd_save)

    p = sub.add_parser("check", help="本地自检")
    p.add_argument("file", nargs="?", help="Markdown 文件")
    p.add_argument("--article", help="改为检查文章库里某篇的当前版本")
    p.add_argument("--title", help="标题（顺便检查长度）")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("titles", help="标题评分")
    p.add_argument("titles", nargs="+", help="一个或多个标题")
    p.add_argument("--topics", required=True, help="主题关键词，逗号分隔")
    p.add_argument("--day", default="周二", choices=WEEKDAYS)
    p.set_defaults(fn=cmd_titles)

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(0)
    if args.cmd == "check" and not (args.file or args.article):
        parser.error("给一个文件，或用 --article 指定文章")
    try:
        sys.exit(args.fn(args))
    except KeyError:
        print("没有这篇文章：用 python -m backend list 看文章 id")
        sys.exit(1)
    except (ValueError, FileNotFoundError) as e:
        print(f"错误：{e}")
        sys.exit(1)

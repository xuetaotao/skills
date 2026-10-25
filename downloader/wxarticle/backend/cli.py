"""命令行：python -m backend <文章链接> [更多链接 ...]"""

import argparse
import asyncio
import sys
from pathlib import Path

from .config import OUTPUT_DIR, SCALE
from .core import Reporter, download_articles, extract_urls
from .fetcher import ArticleError


def read_url_file(path: str) -> list:
    lines = Path(path).read_text(encoding='utf-8-sig').splitlines()
    return [line for line in lines if not line.lstrip().startswith('#')]


def prompt_urls() -> list:
    print('粘贴文章链接（可多行，每行一个或多个），直接回车结束：')
    lines = []
    while True:
        try:
            line = input('> ').strip()
        except EOFError:
            break
        if not line:
            break
        lines.append(line)
    return lines


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd()))
    except ValueError:
        return str(path)


class PrintReporter(Reporter):
    def start(self, index, total, url):
        print(f'\n[{index + 1}/{total}] {url}')

    def article(self, index, article):
        when = f'，{article.publish_time}' if article.publish_time else ''
        print(f'  {article.title}（{article.account or "未知公众号"}{when}）')
        note = f'，{article.failed_images} 张没加载出来' if article.failed_images else ''
        print(f'  图片 {article.images} 张{note}')

    def finished(self, index, result):
        if not result.ok:
            print(f'  失败：{result.error}')
            return
        if result.pdf:
            print(f'  PDF：{_rel(result.pdf)}')
        for path in result.screenshots:
            print(f'  截图：{_rel(path)}')
        print(f'  用时 {result.seconds:.1f} 秒')


async def run(urls, output_dir, pdf, screenshot, headless, scale) -> int:
    results = await download_articles(urls, output_dir, pdf, screenshot, headless, scale, PrintReporter())
    failed = [r.url for r in results if not r.ok]
    print(f'\n完成：成功 {len(results) - len(failed)} 篇，失败 {len(failed)} 篇')
    for url in failed:
        print(f'  失败：{url}')
    return 1 if failed else 0


def main():
    sys.stdout.reconfigure(errors='replace')
    parser = argparse.ArgumentParser(
        prog='python -m backend',
        description='把微信公众号文章保存成 PDF 和长截图。不给链接时会提示粘贴。')
    parser.add_argument('urls', nargs='*', metavar='URL', help='文章链接，可以一次给多个')
    parser.add_argument('-f', '--file', help='从文本文件读链接（每行一个，# 开头的行忽略）')
    parser.add_argument('-o', '--output', type=Path, default=OUTPUT_DIR,
                        help=f'输出目录（默认 {_rel(OUTPUT_DIR)}）')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--pdf-only', action='store_true', help='只生成 PDF')
    group.add_argument('--screenshot-only', action='store_true', help='只生成截图')
    parser.add_argument('--scale', type=float, default=SCALE,
                        help=f'截图像素倍率（默认 {SCALE}，1 文件更小）')
    parser.add_argument('--show', action='store_true',
                        help='显示浏览器窗口（遇到“环境异常”验证时可以手动处理）')
    args = parser.parse_args()

    texts = list(args.urls)
    if args.file:
        try:
            texts += read_url_file(args.file)
        except OSError as e:
            parser.error(f'读不了链接文件：{e}')
    if not texts and sys.stdin.isatty():
        texts = prompt_urls()
    urls = extract_urls(texts)
    if not urls:
        parser.error('没有找到文章链接')

    try:
        code = asyncio.run(run(urls, args.output, not args.screenshot_only, not args.pdf_only,
                               not args.show, args.scale))
    except ArticleError as e:
        print(f'错误：{e}')
        code = 1
    except KeyboardInterrupt:
        print('\n已取消')
        code = 130
    sys.exit(code)

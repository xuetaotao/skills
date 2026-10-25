# -*- coding: utf-8 -*-
"""命令行：python -m backend <网页地址> [选项]"""

import argparse
import sys

from .config import NUM_THREADS, OUTPUT_DIR, TIMEOUT


def build_parser():
    p = argparse.ArgumentParser(
        prog="python -m backend",
        description="批量下载网页里的图片（图形界面：python -m frontend）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python -m backend "https://example.com/post/123"
  python -m backend "https://example.com/gallery/1" --auto-pagination -m 20 --min-size 30
""")
    p.add_argument("url", help="网页地址")
    p.add_argument("-o", "--output", default=OUTPUT_DIR, help="输出根目录 (默认: 项目下的 outputs/)")
    p.add_argument("-j", "--num-threads", type=int, default=NUM_THREADS, help=f"并发下载数 (默认: {NUM_THREADS})")
    p.add_argument("-t", "--timeout", type=int, default=TIMEOUT, help=f"单个请求超时秒数 (默认: {TIMEOUT})")
    p.add_argument("--keep-names", action="store_true", help="文件名带上原文件名 (001_xxx.jpg)")
    p.add_argument("--auto-pagination", action="store_true", help="自动翻页下载")
    p.add_argument("-m", "--max-pages", type=int, default=None, help="最多下载的页数 (默认不限)")
    p.add_argument("--min-size", type=int, default=0, help="跳过小于该大小(KB)的图片 (默认: 0 不过滤)")
    p.add_argument("--keep-duplicates", action="store_true", help="保留内容重复的图片 (默认跳过)")
    return p


def main():
    args = build_parser().parse_args()
    from .core import WebpageImageDownloader
    downloader = WebpageImageDownloader(
        url=args.url,
        output_dir=args.output,
        num_threads=args.num_threads,
        timeout=args.timeout,
        use_sequential_naming=not args.keep_names,
        auto_pagination=args.auto_pagination,
        max_pages=args.max_pages,
        min_image_size_kb=args.min_size,
        dedupe=not args.keep_duplicates,
    )
    try:
        success = downloader.run()
    except KeyboardInterrupt:
        downloader.cancel()
        print("\n[!] 已中断")
        success = False
    sys.exit(0 if success else 1)

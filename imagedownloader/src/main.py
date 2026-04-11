#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网页图片下载工具 - 主入口
支持 CLI 和 GUI 两种使用方式
"""

import sys
import argparse


def main():
    parser = argparse.ArgumentParser(
        description="网页图片下载工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  网页图片批量下载:
    python -m src webpage "https://example.com" -o ./output -j 4

  启动GUI:
    python -m src gui
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    
    # 网页图片下载子命令
    webpage_parser = subparsers.add_parser("webpage", help="从网页批量下载图片")
    webpage_parser.add_argument("url", help="网页地址")
    webpage_parser.add_argument("-o", "--output", default="./output",
                                help="输出目录 (默认: ./output)")
    webpage_parser.add_argument("-j", "--num-threads", type=int, default=4,
                                help="并发线程数 (默认: 4)")
    webpage_parser.add_argument("-t", "--timeout", type=int, default=10,
                                help="下载超时时间，单位秒 (默认: 10)")
    webpage_parser.add_argument("--keep-names", action="store_true",
                                help="保留原文件名 (默认使用递增编号)")
    webpage_parser.add_argument("--auto-pagination", action="store_true",
                                help="自动翻页下载")
    webpage_parser.add_argument("-m", "--max-pages", type=int, default=None,
                                help="最多下载的页数 (默认无限制)")
    
    # GUI 子命令
    gui_parser = subparsers.add_parser("gui", help="启动图形界面")
    
    args = parser.parse_args()
    
    if args.command == "webpage":
        from .webpage_downloader.core import WebpageImageDownloader
        downloader = WebpageImageDownloader(
            url=args.url,
            output_dir=args.output,
            num_threads=args.num_threads,
            timeout=args.timeout,
            use_sequential_naming=not args.keep_names,
            auto_pagination=args.auto_pagination,
            max_pages=args.max_pages
        )
        success = downloader.run()
        sys.exit(0 if success else 1)
    
    elif args.command == "gui":
        from .webpage_downloader.gui_main import main
        main()
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()

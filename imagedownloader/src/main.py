#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片下载工具集 - 统一主入口
支持两种模式：搜索引擎图片下载、网页图片批量下载
"""

import sys
import argparse


def main():
    parser = argparse.ArgumentParser(
        description="图片下载工具集",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  搜索引擎图片下载:
    python -m src search "关键词" -e Bing -d api -n 100 -o ./output

  网页图片批量下载:
    python -m src webpage "https://example.com" -o ./output -j 4

  启动GUI:
    python -m src gui
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    
    # 搜索引擎图片下载子命令
    search_parser = subparsers.add_parser("search", help="从搜索引擎下载图片")
    search_parser.add_argument("keywords", type=str, help='搜索关键词')
    search_parser.add_argument("--engine", "-e", type=str, default="Google",
                               help="搜索引擎", choices=["Google", "Bing", "Baidu"])
    search_parser.add_argument("--driver", "-d", type=str, default="chrome_headless",
                               help="驱动模式", choices=["chrome_headless", "chrome", "api"])
    search_parser.add_argument("--max-number", "-n", type=int, default=100,
                               help="最大下载数量")
    search_parser.add_argument("--num-threads", "-j", type=int, default=50,
                               help="并发线程数")
    search_parser.add_argument("--timeout", "-t", type=int, default=10,
                               help="下载超时时间(秒)")
    search_parser.add_argument("--output", "-o", type=str, default="./output/search",
                               help="输出目录")
    search_parser.add_argument("--safe-mode", "-S", action="store_true", default=False,
                               help="安全模式(仅Google)")
    search_parser.add_argument("--face-only", "-F", action="store_true", default=False,
                               help="仅人脸图片")
    search_parser.add_argument("--proxy_http", "-ph", type=str, default=None,
                               help="HTTP代理")
    search_parser.add_argument("--proxy_socks5", "-ps", type=str, default=None,
                               help="Socks5代理")
    search_parser.add_argument("--type", "-ty", type=str, default=None,
                               help="图片类型", choices=["clipart", "linedrawing", "photograph"])
    search_parser.add_argument("--color", "-cl", type=str, default=None,
                               help="图片颜色过滤")
    
    # 网页图片下载子命令
    webpage_parser = subparsers.add_parser("webpage", help="从网页批量下载图片")
    webpage_parser.add_argument("url", help="网页地址")
    webpage_parser.add_argument("-o", "--output", default="./webpage_images",
                                help="输出目录 (默认: ./webpage_images)")
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
    gui_parser.add_argument("--tool", type=str, default="launcher",
                            choices=["launcher", "search", "webpage"],
                            help="启动指定工具的GUI (默认: launcher)")
    
    args = parser.parse_args()
    
    if args.command == "search":
        from .search_downloader import image_downloader_cli
        image_downloader_cli.main(sys.argv[2:])
    
    elif args.command == "webpage":
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
        if args.tool == "search":
            from .search_downloader.gui import main
            main()
        elif args.tool == "webpage":
            from .webpage_downloader.gui_main import main
            main()
        else:
            # 统一启动器
            from .launcher import main
            main()
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()

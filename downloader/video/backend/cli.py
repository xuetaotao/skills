# -*- coding: utf-8 -*-
"""命令行：python -m backend {video,audio,info,douyin} <地址> [选项]"""

import argparse
import sys

from .config import AUDIO_FORMATS, OUTPUT_DIR, QUALITY_FORMATS, SUB_LANGS, THREADS, TIMEOUT


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m backend",
        description="音视频下载工具（图形界面：python -m frontend）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python -m backend video "https://www.bilibili.com/video/BVxxx"
  python -m backend video "https://www.youtube.com/watch?v=xxx" -q 720 --subtitle
  python -m backend audio "https://www.youtube.com/watch?v=xxx" --audio-format mp3
  python -m backend video "https://v.douyin.com/xxx/"          (抖音链接自动用专用下载器)
  python -m backend douyin "https://v.douyin.com/xxx/" --mode audio
  python -m backend info "https://www.youtube.com/watch?v=xxx"
""")
    sub = parser.add_subparsers(dest="command", help="子命令")

    net = argparse.ArgumentParser(add_help=False)
    net.add_argument("--proxy", default=None, help="代理地址 (如 socks5://127.0.0.1:1080)")
    net.add_argument("--cookie-file", default=None,
                     help="Cookie 文件：浏览器导出的 cookies.txt，或内容为 a=1; b=2 的文本文件")
    out = argparse.ArgumentParser(add_help=False)
    out.add_argument("-o", "--output", default=OUTPUT_DIR, help="输出根目录 (默认: 项目下的 outputs/)")
    out.add_argument("-t", "--timeout", type=int, default=TIMEOUT, help=f"网络超时秒数 (默认: {TIMEOUT})")
    out.add_argument("--threads", type=int, default=THREADS, help=f"m3u8 分片并发数 (默认: {THREADS})")

    p = sub.add_parser("video", parents=[out, net], help="下载视频")
    p.add_argument("url", help="视频地址")
    p.add_argument("-q", "--quality", choices=list(QUALITY_FORMATS), default="best",
                   help="画质: best=最高, 2160/1080/720/480/360=不超过该高度, single=最佳单文件 (默认: best)")
    p.add_argument("-f", "--format", default=None, help="自定义 yt-dlp 格式字符串，优先于 --quality")
    p.add_argument("--merge-output-format", default="mp4", choices=["mp4", "mkv", "webm"],
                   help="音视频合并格式 (默认: mp4)")
    p.add_argument("--subtitle", action="store_true", help="下载字幕")
    p.add_argument("--sub-langs", default=SUB_LANGS,
                   help=f"字幕语言，逗号分隔，支持正则 (默认: {SUB_LANGS}；all=全部)")
    p.add_argument("--thumbnail", action="store_true", help="下载封面图")
    p.add_argument("--playlist", action="store_true", help="下载整个播放列表 (默认只下第一个)")

    p = sub.add_parser("audio", parents=[out, net], help="下载音频")
    p.add_argument("url", help="音视频地址")
    p.add_argument("--audio-format", default="best", choices=AUDIO_FORMATS, help="音频格式 (默认: best 原始格式)")
    p.add_argument("--audio-quality", default="0", help="音频质量 0(最好)-9(最差) (默认: 0)")
    p.add_argument("--embed-thumbnail", action="store_true", help="把封面嵌入音频文件")
    p.add_argument("--playlist", action="store_true", help="下载整个播放列表 (默认只下第一个)")

    p = sub.add_parser("info", parents=[net], help="查看视频信息和可用格式 (不下载)")
    p.add_argument("url", help="视频地址")

    p = sub.add_parser("douyin", parents=[out, net], help="抖音专用下载器 (无水印)")
    p.add_argument("url", help="抖音视频/分享链接")
    p.add_argument("--mode", default="video", choices=["video", "audio", "info"], help="下载模式 (默认: video)")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "douyin":
        from .douyin import DouyinDownloader
        downloader = DouyinDownloader(output_dir=args.output, proxy=args.proxy, cookie=args.cookie_file,
                                      timeout=args.timeout)
        run = lambda: downloader.run(args.url, mode=args.mode)
        cancel = downloader.reporter.cancel_event.set

    elif args.command in ("video", "audio", "info"):
        from .core import MediaDownloader
        kwargs = dict(url=args.url, mode=args.command, proxy=args.proxy, cookie_file=args.cookie_file)
        if args.command != "info":
            kwargs.update(output_dir=args.output, timeout=args.timeout, threads=args.threads,
                          download_playlist=args.playlist)
        if args.command == "video":
            kwargs.update(format_spec=args.format or QUALITY_FORMATS[args.quality],
                          merge_output_format=args.merge_output_format,
                          download_subtitle=args.subtitle, sub_langs=args.sub_langs,
                          download_thumbnail=args.thumbnail)
        elif args.command == "audio":
            kwargs.update(audio_format=args.audio_format, audio_quality=args.audio_quality,
                          embed_thumbnail=args.embed_thumbnail)
        downloader = MediaDownloader(**kwargs)
        run, cancel = downloader.run, downloader.cancel

    else:
        parser.print_help()
        sys.exit(1)

    try:
        success = run()
    except KeyboardInterrupt:
        cancel()
        print("\n[!] 已中断")
        success = False
    sys.exit(0 if success else 1)

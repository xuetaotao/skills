#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音视频下载工具 - 主入口
支持 CLI 和 GUI 两种使用方式
"""

import sys
import argparse


def main():
    parser = argparse.ArgumentParser(
        description="音视频下载工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  下载视频:
    python -m src video "https://www.youtube.com/watch?v=xxx" -o ./output
    python -m src video "https://www.bilibili.com/video/BVxxx" -o ./output --format best

  下载音频:
    python -m src audio "https://www.youtube.com/watch?v=xxx" -o ./output
    python -m src audio "https://music.163.com/xxx" -o ./output --audio-format flac

  查看视频信息:
    python -m src info "https://www.youtube.com/watch?v=xxx"

  启动GUI:
    python -m src gui
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # 视频下载子命令
    video_parser = subparsers.add_parser("video", help="下载视频")
    video_parser.add_argument("url", help="视频地址")
    video_parser.add_argument("-o", "--output", default="./output",
                              help="输出目录 (默认: ./output)")
    video_parser.add_argument("-f", "--format", default="bestvideo+bestaudio/best",
                              help="视频格式 (默认: bestvideo+bestaudio/best)")
    video_parser.add_argument("--merge-output-format", default="mp4",
                              help="合并输出格式 (默认: mp4)")
    video_parser.add_argument("--subtitle", action="store_true",
                              help="下载字幕 (默认不下载)")
    video_parser.add_argument("--thumbnail", action="store_true",
                              help="下载缩略图 (默认不下载)")
    video_parser.add_argument("--playlist", action="store_true",
                              help="下载整个播放列表 (默认只下载单个视频)")
    video_parser.add_argument("--proxy", default=None,
                              help="代理地址 (如 socks5://127.0.0.1:1080)")
    video_parser.add_argument("--cookie-file", default=None,
                              help="Cookie 文件路径 (用于需要登录的网站)")
    video_parser.add_argument("-t", "--timeout", type=int, default=30,
                              help="下载超时时间，单位秒 (默认: 30)")

    # 音频下载子命令
    audio_parser = subparsers.add_parser("audio", help="下载音频")
    audio_parser.add_argument("url", help="音视频地址 (自动提取音频)")
    audio_parser.add_argument("-o", "--output", default="./output",
                             help="输出目录 (默认: ./output)")
    audio_parser.add_argument("--audio-format", default="best",
                             help="音频格式: best/mp3/wav/flac/aac/m4a/opus (默认: best)")
    audio_parser.add_argument("--audio-quality", default="0",
                             help="音频质量 0(最好)-9(最差) (默认: 0)")
    audio_parser.add_argument("--embed-thumbnail", action="store_true",
                             help="嵌入缩略图到音频文件 (默认不嵌入)")
    audio_parser.add_argument("--playlist", action="store_true",
                             help="下载整个播放列表 (默认只下载单个)")
    audio_parser.add_argument("--proxy", default=None,
                             help="代理地址 (如 socks5://127.0.0.1:1080)")
    audio_parser.add_argument("--cookie-file", default=None,
                             help="Cookie 文件路径 (用于需要登录的网站)")
    audio_parser.add_argument("-t", "--timeout", type=int, default=30,
                             help="下载超时时间，单位秒 (默认: 30)")

    # 信息查看子命令
    info_parser = subparsers.add_parser("info", help="查看视频/音频信息")
    info_parser.add_argument("url", help="视频/音频地址")
    info_parser.add_argument("--proxy", default=None,
                            help="代理地址")
    info_parser.add_argument("--cookie-file", default=None,
                            help="Cookie 文件路径")

    # GUI 子命令
    gui_parser = subparsers.add_parser("gui", help="启动图形界面")

    args = parser.parse_args()

    if args.command == "video":
        from .media_downloader.core import MediaDownloader
        downloader = MediaDownloader(
            url=args.url,
            output_dir=args.output,
            mode='video',
            format_spec=args.format,
            merge_output_format=args.merge_output_format,
            download_subtitle=args.subtitle,
            download_thumbnail=args.thumbnail,
            download_playlist=args.playlist,
            proxy=args.proxy,
            cookie_file=args.cookie_file,
            timeout=args.timeout,
        )
        success = downloader.run()
        sys.exit(0 if success else 1)

    elif args.command == "audio":
        from .media_downloader.core import MediaDownloader
        downloader = MediaDownloader(
            url=args.url,
            output_dir=args.output,
            mode='audio',
            audio_format=args.audio_format,
            audio_quality=args.audio_quality,
            embed_thumbnail=args.embed_thumbnail,
            download_playlist=args.playlist,
            proxy=args.proxy,
            cookie_file=args.cookie_file,
            timeout=args.timeout,
        )
        success = downloader.run()
        sys.exit(0 if success else 1)

    elif args.command == "info":
        from .media_downloader.core import MediaDownloader
        downloader = MediaDownloader(
            url=args.url,
            output_dir='./output',
            mode='info',
            proxy=args.proxy,
            cookie_file=args.cookie_file,
        )
        success = downloader.run()
        sys.exit(0 if success else 1)

    elif args.command == "gui":
        from .media_downloader.gui_main import main
        main()

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()

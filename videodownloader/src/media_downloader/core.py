# -*- coding: utf-8 -*-
"""
音视频下载工具
基于 yt-dlp，支持视频/音频下载、格式选择、字幕下载等功能
"""

import os
import sys
import re
import time
import shutil
from datetime import datetime
from urllib.parse import urlparse

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

from .douyin import DouyinDownloader
from .maccms import MacCMSDownloader
from .rouvideo import RouVideoDownloader


class MediaDownloader:
    """音视频下载器，封装 yt-dlp 功能，并内置抖音专用下载器"""

    # 音频格式到 yt-dlp 格式字符串的映射
    AUDIO_FORMAT_MAP = {
        'best': 'bestaudio/best',
        'mp3': 'bestaudio/best',
        'wav': 'bestaudio/best',
        'flac': 'bestaudio/best',
        'aac': 'bestaudio/best',
        'm4a': 'bestaudio/best',
        'opus': 'bestaudio/best',
    }

    def __init__(self, url, output_dir='./output', mode='video',
                 format_spec=None, merge_output_format='mp4',
                 audio_format='best', audio_quality='0',
                 download_subtitle=False, download_thumbnail=False,
                 download_playlist=False, embed_thumbnail=False,
                 proxy=None, cookie_file=None, timeout=30,
                 progress_callback=None):
        """
        初始化音视频下载器

        Args:
            url: 视频/音频地址
            output_dir: 输出根目录
            mode: 下载模式 - 'video'/'audio'/'info'
            format_spec: 视频格式 (yt-dlp 格式字符串)
            merge_output_format: 视频合并格式 (mp4/mkv/webm)
            audio_format: 音频格式 (best/mp3/wav/flac/aac/m4a/opus)
            audio_quality: 音频质量 0(最好)-9(最差)
            download_subtitle: 是否下载字幕
            download_thumbnail: 是否下载缩略图
            download_playlist: 是否下载整个播放列表
            embed_thumbnail: 是否嵌入缩略图到音频文件
            proxy: 代理地址
            cookie_file: Cookie 文件路径
            timeout: 下载超时时间（秒）
            progress_callback: 进度回调函数 callback(msg: str)
        """
        self.url = url
        self.output_base_dir = output_dir
        self.output_dir = output_dir
        self.mode = mode
        self.format_spec = format_spec or 'bestvideo+bestaudio/best'
        self.merge_output_format = merge_output_format
        self.audio_format = audio_format
        self.audio_quality = audio_quality
        self.download_subtitle = download_subtitle
        self.download_thumbnail = download_thumbnail
        self.download_playlist = download_playlist
        self.embed_thumbnail = embed_thumbnail
        self.proxy = proxy
        self.cookie_file = cookie_file
        self.timeout = timeout
        self.progress_callback = progress_callback

        # 下载统计
        self.downloaded_count = 0
        self.failed_count = 0

    def _log(self, msg):
        """输出日志"""
        if self.progress_callback:
            self.progress_callback(msg)
        else:
            print(msg)

    @staticmethod
    def generate_subdir_name(url, info_dict=None):
        """
        根据视频信息生成子目录名

        格式: {域名}-{标题前20字}-{时间}
        示例: youtube.com-Beautiful_Video-20260412_131500
        """
        # 提取域名
        parsed = urlparse(url)
        domain = parsed.netloc
        if domain.startswith('www.'):
            domain = domain[4:]

        # 提取标题
        title_part = ""
        if info_dict:
            title = info_dict.get('title', '')
            if title:
                # 清洗标题
                cleaned = re.sub(r'[\\/:*?"<>|]', '', title)
                cleaned = re.sub(r'\s+', '_', cleaned)
                title_part = cleaned[:20].rstrip('_')

        # 时间戳
        time_str = datetime.now().strftime('%Y%m%d_%H%M%S')

        parts = [p for p in [domain, title_part, time_str] if p]
        return '-'.join(parts)

    def _build_ydl_opts(self, output_template=None):
        """构建 yt-dlp 选项"""
        if yt_dlp is None:
            raise RuntimeError("yt-dlp 未安装，请运行 pip install yt-dlp")

        opts = {
            'outtmpl': output_template or os.path.join(self.output_dir, '%(title)s.%(ext)s'),
            'restrictfilenames': True,  # 限制文件名为 ASCII 安全字符
            'nooverwrites': True,       # 不覆盖已存在的文件
            'continuedl': True,         # 续传
            'noplaylist': not self.download_playlist,  # 是否下载播放列表
            'socket_timeout': self.timeout,
        }

        # 代理
        if self.proxy:
            opts['proxy'] = self.proxy

        # Cookie
        if self.cookie_file:
            opts['cookiefile'] = self.cookie_file

        if self.mode == 'video':
            opts['format'] = self.format_spec
            opts['merge_output_format'] = self.merge_output_format

            # 字幕
            if self.download_subtitle:
                opts['writesubtitles'] = True
                opts['writeautomaticsub'] = True
                opts['subtitleslangs'] = ['all']
                opts['subtitleformat'] = 'srt'

            # 缩略图
            if self.download_thumbnail:
                opts['writethumbnail'] = True

            # 进度钩子
            opts['progress_hooks'] = [self._progress_hook]

        elif self.mode == 'audio':
            opts['format'] = self.AUDIO_FORMAT_MAP.get(self.audio_format, 'bestaudio/best')

            # 后处理：提取音频并转换格式
            postprocessors = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': self.audio_format if self.audio_format != 'best' else None,
                'preferredquality': self.audio_quality,
            }]

            # 嵌入缩略图
            if self.embed_thumbnail:
                opts['writethumbnail'] = True
                postprocessors.append({
                    'key': 'FFmpegMetadata',
                })
                postprocessors.append({
                    'key': 'EmbedThumbnail',
                })

            opts['postprocessors'] = postprocessors
            opts['progress_hooks'] = [self._progress_hook]

        elif self.mode == 'info':
            opts['quiet'] = True
            opts['no_warnings'] = True
            opts['skip_download'] = True

        return opts

    def _progress_hook(self, d):
        """yt-dlp 下载进度钩子"""
        if d['status'] == 'downloading':
            # 下载中
            percent = d.get('_percent_str', 'N/A')
            speed = d.get('_speed_str', 'N/A')
            eta = d.get('_eta_str', 'N/A')
            filename = os.path.basename(d.get('filename', ''))
            self._log(f"  ↓ {filename}: {percent} 速度: {speed} 剩余: {eta}")

        elif d['status'] == 'finished':
            filename = os.path.basename(d.get('filename', ''))
            self._log(f"  ✓ 下载完成: {filename}")
            self.downloaded_count += 1

        elif d['status'] == 'error':
            filename = os.path.basename(d.get('filename', ''))
            self._log(f"  ✗ 下载失败: {filename}")
            self.failed_count += 1

    def fetch_info(self):
        """
        获取视频/音频信息（不下载）

        Returns:
            dict: yt-dlp 返回的信息字典，失败返回 None
        """
        self._log(f"[*] 正在获取信息: {self.url}")
        opts = self._build_ydl_opts()

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                return info
        except Exception as e:
            self._log(f"[-] 获取信息失败: {e}")
            return None

    def print_info(self, info):
        """格式化打印视频/音频信息"""
        if not info:
            self._log("[-] 无信息可显示")
            return

        self._log("=" * 60)
        self._log(f"标题: {info.get('title', 'N/A')}")
        self._log(f"时长: {self._format_duration(info.get('duration', 0))}")
        self._log(f"上传者: {info.get('uploader', 'N/A')}")
        self._log(f"上传日期: {info.get('upload_date', 'N/A')}")
        self._log(f"播放量: {info.get('view_count', 'N/A')}")
        self._log(f"点赞数: {info.get('like_count', 'N/A')}")
        self._log(f"描述: {(info.get('description', '') or 'N/A')[:200]}")

        # 可用格式列表
        formats = info.get('formats', [])
        if formats:
            self._log(f"\n可用格式 (共 {len(formats)} 个):")
            self._log("-" * 60)
            self._log(f"{'格式ID':<12} {'扩展名':<8} {'分辨率':<14} {'大小':<12} {'备注'}")
            self._log("-" * 60)

            seen = set()
            for f in formats:
                fmt_id = f.get('format_id', 'N/A')
                ext = f.get('ext', 'N/A')

                # 分辨率
                width = f.get('width')
                height = f.get('height')
                if width and height:
                    resolution = f"{width}x{height}"
                elif height:
                    resolution = f"{height}p"
                else:
                    resolution = 'audio only' if f.get('vcodec') == 'none' else 'N/A'

                # 文件大小
                filesize = f.get('filesize')
                if filesize:
                    size_str = f"{filesize / 1024 / 1024:.1f}MB"
                else:
                    size_str = 'N/A'

                # 备注
                note_parts = []
                vcodec = f.get('vcodec', 'none')
                acodec = f.get('acodec', 'none')
                if vcodec != 'none':
                    note_parts.append(f"v:{vcodec[:8]}")
                if acodec != 'none':
                    note_parts.append(f"a:{acodec[:8]}")
                tbr = f.get('tbr')
                if tbr:
                    note_parts.append(f"{tbr:.0f}k")
                note = ' '.join(note_parts)

                # 去重
                key = (fmt_id, ext, resolution)
                if key in seen:
                    continue
                seen.add(key)

                self._log(f"{fmt_id:<12} {ext:<8} {resolution:<14} {size_str:<12} {note}")

        self._log("=" * 60)

    @staticmethod
    def _format_duration(seconds):
        """格式化时长"""
        if not seconds:
            return "N/A"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    def _check_ffmpeg(self):
        """检查 ffmpeg 是否可用（合并视频+音频需要）"""
        return shutil.which('ffmpeg') is not None

    def _is_douyin_url(self):
        """判断当前 URL 是否是抖音链接"""
        return DouyinDownloader.is_douyin_url(self.url)

    def _is_maccms_url(self):
        """判断当前 URL 是否是 MacCMS 站点"""
        return MacCMSDownloader.is_maccms_url(self.url)

    def _is_rouvideo_url(self):
        """判断当前 URL 是否是 rou.video 链接"""
        return RouVideoDownloader.is_rouvideo_url(self.url)

    def _run_douyin(self):
        """使用抖音专用下载器"""
        douyin = DouyinDownloader(
            output_dir=self.output_base_dir,
            proxy=self.proxy,
            cookie=self.cookie_file,
            timeout=self.timeout,
            progress_callback=self._log,
        )
        mode = self.mode
        if mode == 'info':
            mode = 'info'
        elif mode == 'audio':
            mode = 'audio'
        else:
            mode = 'video'
        success = douyin.run(self.url, mode=mode)
        # 同步下载统计
        self.downloaded_count = douyin.downloaded_count
        self.failed_count = douyin.failed_count
        return success

    def _run_maccms(self):
        """使用 MacCMS 专用下载器"""
        maccms = MacCMSDownloader(
            output_dir=self.output_base_dir,
            proxy=self.proxy,
            cookie=self.cookie_file,
            timeout=self.timeout,
            progress_callback=self._log,
        )
        mode = self.mode
        if mode == 'audio':
            mode = 'video'  # MacCMS 暂不支持纯音频提取
        success = maccms.run(self.url, mode=mode)
        self.downloaded_count = maccms.downloaded_count
        self.failed_count = maccms.failed_count
        return success

    def _run_rouvideo(self):
        """使用 RouVideo 专用下载器"""
        rouvideo = RouVideoDownloader(
            output_dir=self.output_base_dir,
            proxy=self.proxy,
            cookie=self.cookie_file,
            timeout=self.timeout,
            progress_callback=self._log,
        )
        mode = self.mode
        if mode == 'audio':
            mode = 'video'  # RouVideo 暂不支持纯音频提取
        success = rouvideo.run(self.url, mode=mode)
        self.downloaded_count = rouvideo.downloaded_count
        self.failed_count = rouvideo.failed_count
        return success

    def run(self):
        """
        运行下载流程

        Returns:
            bool: 是否成功
        """
        # 抖音链接使用专用下载器
        if self._is_douyin_url():
            self._log("[*] 检测到抖音链接，使用抖音专用下载器")
            return self._run_douyin()

        # MacCMS 站点使用专用下载器
        if self._is_maccms_url():
            self._log("[*] 检测到 MacCMS 视频站，使用专用解析器")
            return self._run_maccms()

        # RouVideo 站点使用专用下载器
        if self._is_rouvideo_url():
            self._log("[*] 检测到 RouVideo 链接，使用专用解析器")
            return self._run_rouvideo()

        # 其他链接需要 yt-dlp
        if yt_dlp is None:
            self._log("[-] 缺少依赖: yt-dlp，请运行 pip install yt-dlp")
            return False

        mode_names = {'video': '视频', 'audio': '音频', 'info': '信息查看'}
        self._log("=" * 60)
        self._log(f"音视频下载工具 - {mode_names.get(self.mode, self.mode)}模式")
        self._log("=" * 60)
        self._log(f"地址: {self.url}")
        self._log(f"输出目录: {os.path.abspath(self.output_base_dir)}")
        if self.mode == 'video':
            self._log(f"视频格式: {self.format_spec}")
            self._log(f"合并格式: {self.merge_output_format}")
        elif self.mode == 'audio':
            self._log(f"音频格式: {self.audio_format}")
            self._log(f"音频质量: {self.audio_quality}")
        self._log("=" * 60)

        # 检查 ffmpeg
        if self.mode == 'video' and 'bestvideo+bestaudio' in self.format_spec:
            if not self._check_ffmpeg():
                self._log("[!] 警告: 未检测到 ffmpeg，无法合并最佳视频+音频")
                self._log("[!] 将回退到 best 格式（可能不是最高画质）")
                self.format_spec = 'best'

        if self.mode == 'audio' and (self.audio_format != 'best' or self.embed_thumbnail):
            if not self._check_ffmpeg():
                self._log("[!] 警告: 未检测到 ffmpeg，音频格式转换可能失败")
                self._log("[!] 将以最佳原始格式下载音频")

        # 信息查看模式
        if self.mode == 'info':
            info = self.fetch_info()
            if info:
                self.print_info(info)
                return True
            return False

        # 获取视频信息（用于生成子目录名）
        self._log("[*] 正在获取媒体信息...")
        info = self.fetch_info()
        if not info:
            self._log("[-] 无法获取媒体信息")
            return False

        # 生成子目录名并创建输出目录
        subdir_name = self.generate_subdir_name(self.url, info)
        self.output_dir = os.path.join(self.output_base_dir, subdir_name)
        os.makedirs(self.output_dir, exist_ok=True)
        self._log(f"[+] 输出目录: {os.path.abspath(self.output_dir)}")

        # 处理播放列表
        is_playlist = info.get('_type') == 'playlist' or info.get('entries')
        if is_playlist and not self.download_playlist:
            entry_count = len(info.get('entries', []))
            self._log(f"[!] 检测到播放列表 ({entry_count} 个视频)")
            self._log("[!] 如需下载整个播放列表，请使用 --playlist 参数")
            # 下载第一个视频
            entries = info.get('entries', [])
            if entries and entries[0]:
                first_entry = entries[0]
                if isinstance(first_entry, dict):
                    self.url = first_entry.get('webpage_url', first_entry.get('url', self.url))
                else:
                    self.url = str(first_entry)
                self._log(f"[*] 将下载第一个视频: {self.url}")
                # 重新获取单个视频信息
                info = self.fetch_info()

        # 显示视频信息摘要
        self._log(f"[+] 标题: {info.get('title', 'N/A')}")
        self._log(f"[+] 时长: {self._format_duration(info.get('duration', 0))}")

        # 构建输出模板
        # 播放列表时添加序号
        if self.download_playlist and is_playlist:
            output_template = os.path.join(
                self.output_dir,
                '%(playlist_index)03d - %(title)s.%(ext)s'
            )
        else:
            output_template = os.path.join(self.output_dir, '%(title)s.%(ext)s')

        # 开始下载
        self._log("\n[*] 开始下载...")
        start_time = time.time()

        opts = self._build_ydl_opts(output_template)

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([self.url])
        except Exception as e:
            self._log(f"[-] 下载失败: {e}")
            return False

        elapsed_time = time.time() - start_time

        # 打印统计
        self._log("\n" + "=" * 60)
        self._log("下载完成!")
        self._log(f"成功: {self.downloaded_count}")
        self._log(f"失败: {self.failed_count}")
        self._log(f"总耗时: {elapsed_time:.2f} 秒")
        self._log(f"保存位置: {os.path.abspath(self.output_dir)}")
        self._log("=" * 60)

        return self.downloaded_count > 0

    def run_with_info_callback(self, info_callback=None, progress_callback=None):
        """
        运行下载流程（GUI 专用，支持回调）

        Args:
            info_callback: 信息回调 (用于返回视频信息给 GUI)
            progress_callback: 进度回调 (替代构造时传入的 callback)

        Returns:
            bool: 是否成功
        """
        if progress_callback:
            self.progress_callback = progress_callback

        # 抖音链接使用专用下载器
        if self._is_douyin_url():
            self._log("[*] 检测到抖音链接，使用抖音专用下载器")
            return self._run_douyin()

        # MacCMS 站点使用专用下载器
        if self._is_maccms_url():
            self._log("[*] 检测到 MacCMS 视频站，使用专用解析器")
            return self._run_maccms()

        # RouVideo 站点使用专用下载器
        if self._is_rouvideo_url():
            self._log("[*] 检测到 RouVideo 链接，使用专用解析器")
            return self._run_rouvideo()

        # 其他链接需要 yt-dlp
        if yt_dlp is None:
            self._log("[-] 缺少依赖: yt-dlp，请运行 pip install yt-dlp")
            return False

        # 获取信息
        self._log("[*] 正在获取媒体信息...")
        info = self.fetch_info()
        if not info:
            self._log("[-] 无法获取媒体信息")
            return False

        if info_callback:
            info_callback(info)

        # 生成子目录名
        subdir_name = self.generate_subdir_name(self.url, info)
        self.output_dir = os.path.join(self.output_base_dir, subdir_name)
        os.makedirs(self.output_dir, exist_ok=True)
        self._log(f"[+] 输出目录: {os.path.abspath(self.output_dir)}")

        # 显示摘要
        self._log(f"[+] 标题: {info.get('title', 'N/A')}")
        self._log(f"[+] 时长: {self._format_duration(info.get('duration', 0))}")

        # 输出模板
        is_playlist = info.get('_type') == 'playlist' or info.get('entries')
        if self.download_playlist and is_playlist:
            output_template = os.path.join(
                self.output_dir,
                '%(playlist_index)03d - %(title)s.%(ext)s'
            )
        else:
            output_template = os.path.join(self.output_dir, '%(title)s.%(ext)s')

        # 检查 ffmpeg
        if self.mode == 'video' and 'bestvideo+bestaudio' in self.format_spec:
            if not self._check_ffmpeg():
                self._log("[!] 警告: 未检测到 ffmpeg，将使用 best 格式")
                self.format_spec = 'best'

        # 开始下载
        self._log("\n[*] 开始下载...")
        start_time = time.time()

        opts = self._build_ydl_opts(output_template)

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([self.url])
        except Exception as e:
            self._log(f"[-] 下载失败: {e}")
            return False

        elapsed_time = time.time() - start_time

        self._log(f"\n[+] 下载完成！总耗时: {elapsed_time:.2f} 秒")
        self._log(f"[+] 保存位置: {os.path.abspath(self.output_dir)}")

        return self.downloaded_count > 0


def main():
    """独立运行入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="音视频下载工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  下载视频:
    python core.py video "https://www.youtube.com/watch?v=xxx" -o ./output
  下载音频:
    python core.py audio "https://www.youtube.com/watch?v=xxx" -o ./output --audio-format mp3
  查看信息:
    python core.py info "https://www.youtube.com/watch?v=xxx"
        """
    )

    subparsers = parser.add_subparsers(dest="command")

    video_parser = subparsers.add_parser("video", help="下载视频")
    video_parser.add_argument("url", help="视频地址")
    video_parser.add_argument("-o", "--output", default="./output")
    video_parser.add_argument("-f", "--format", default="bestvideo+bestaudio/best")
    video_parser.add_argument("--merge-output-format", default="mp4")
    video_parser.add_argument("--subtitle", action="store_true")
    video_parser.add_argument("--thumbnail", action="store_true")
    video_parser.add_argument("--playlist", action="store_true")
    video_parser.add_argument("--proxy", default=None)
    video_parser.add_argument("--cookie-file", default=None)

    audio_parser = subparsers.add_parser("audio", help="下载音频")
    audio_parser.add_argument("url", help="音视频地址")
    audio_parser.add_argument("-o", "--output", default="./output")
    audio_parser.add_argument("--audio-format", default="best")
    audio_parser.add_argument("--audio-quality", default="0")
    audio_parser.add_argument("--embed-thumbnail", action="store_true")
    audio_parser.add_argument("--playlist", action="store_true")
    audio_parser.add_argument("--proxy", default=None)
    audio_parser.add_argument("--cookie-file", default=None)

    info_parser = subparsers.add_parser("info", help="查看信息")
    info_parser.add_argument("url", help="地址")
    info_parser.add_argument("--proxy", default=None)
    info_parser.add_argument("--cookie-file", default=None)

    args = parser.parse_args()

    if args.command == "video":
        downloader = MediaDownloader(
            url=args.url, output_dir=args.output, mode='video',
            format_spec=args.format, merge_output_format=args.merge_output_format,
            download_subtitle=args.subtitle, download_thumbnail=args.thumbnail,
            download_playlist=args.playlist, proxy=args.proxy,
            cookie_file=args.cookie_file,
        )
        success = downloader.run()
        sys.exit(0 if success else 1)

    elif args.command == "audio":
        downloader = MediaDownloader(
            url=args.url, output_dir=args.output, mode='audio',
            audio_format=args.audio_format, audio_quality=args.audio_quality,
            embed_thumbnail=args.embed_thumbnail,
            download_playlist=args.playlist, proxy=args.proxy,
            cookie_file=args.cookie_file,
        )
        success = downloader.run()
        sys.exit(0 if success else 1)

    elif args.command == "info":
        downloader = MediaDownloader(
            url=args.url, output_dir='./output', mode='info',
            proxy=args.proxy, cookie_file=args.cookie_file,
        )
        info = downloader.fetch_info()
        if info:
            downloader.print_info(info)
            sys.exit(0)
        sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()

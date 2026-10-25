# -*- coding: utf-8 -*-
"""
音视频下载核心
抖音 / RouVideo / MacCMS 走内置解析器，其它网站交给 yt-dlp
"""

import os
import time
from datetime import datetime

try:
    import yt_dlp
    from yt_dlp.utils import DownloadCancelled, DownloadError
except ImportError:
    yt_dlp = None

from .common import (Cancelled, Reporter, format_duration, format_size, has_ffmpeg,
                     is_netscape_cookie_file, make_session, url_domain)
from .config import JS_RUNTIMES, OUTPUT_DIR, QUALITY_FORMATS, SUB_LANGS, THREADS, TIMEOUT
from .douyin import DouyinDownloader
from .maccms import MacCMSDownloader
from .rouvideo import RouVideoDownloader


class _YdlLogger:
    """yt-dlp 的警告转到日志；错误由调用方从异常里输出，避免重复"""

    def __init__(self, log):
        self.log = log

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        if 'Falling back on generic' not in msg:
            self.log(f"[!] {msg}")

    def error(self, msg):
        pass


class MediaDownloader:
    """音视频下载器"""

    def __init__(self, url, output_dir=OUTPUT_DIR, mode='video',
                 format_spec=None, merge_output_format='mp4',
                 audio_format='best', audio_quality='0',
                 download_subtitle=False, download_thumbnail=False,
                 download_playlist=False, embed_thumbnail=False,
                 proxy=None, cookie_file=None, timeout=TIMEOUT,
                 progress_callback=None, progress=None, info_callback=None,
                 sub_langs=SUB_LANGS, threads=THREADS):
        """
        Args:
            url: 视频/音频地址
            output_dir: 输出根目录，每次下载在其下新建子目录
            mode: 'video' / 'audio' / 'info'
            format_spec: yt-dlp 格式字符串，默认最高画质
            merge_output_format: 音视频合并格式 mp4/mkv/webm
            audio_format: best/mp3/m4a/flac/wav/aac/opus
            audio_quality: 0(最好)-9(最差)
            download_subtitle / download_thumbnail / download_playlist / embed_thumbnail: 开关
            proxy: 代理地址
            cookie_file: cookies.txt 路径，或 "a=1; b=2" 字符串
            timeout: 网络超时（秒）
            progress_callback: 日志回调 log(str)，默认 print
            progress: 进度回调 progress(fraction 或 None, text)
            info_callback: 拿到媒体信息后回调 info_callback(dict)
            sub_langs: 字幕语言，逗号分隔，支持正则，如 "zh.*,en.*" 或 "all"
            threads: 分片并发数
        """
        self.url = url.strip()
        self.output_base_dir = output_dir
        self.output_dir = None
        self.mode = mode
        self.format_spec = format_spec or QUALITY_FORMATS['best']
        self.merge_output_format = merge_output_format
        self.audio_format = audio_format
        self.audio_quality = str(audio_quality)
        self.download_subtitle = download_subtitle
        self.download_thumbnail = download_thumbnail
        self.download_playlist = download_playlist
        self.embed_thumbnail = embed_thumbnail
        self.proxy = proxy or None
        self.cookie_file = cookie_file or None
        self.timeout = timeout
        self.info_callback = info_callback
        self.sub_langs = [s.strip() for s in (sub_langs or SUB_LANGS).split(',') if s.strip()]
        self.threads = threads

        self.reporter = Reporter(progress_callback, progress)
        self._log = self.reporter.log
        self.cancel_event = self.reporter.cancel_event
        self.downloaded_count = 0
        self.failed_count = 0
        self.saved_files = []
        self.info = None
        self._announced = set()

    def cancel(self):
        self.cancel_event.set()

    # ------------------------------------------------------------ 内置解析器

    def _site_class(self):
        if DouyinDownloader.is_douyin_url(self.url):
            return DouyinDownloader, "抖音链接，使用抖音专用下载器（无水印）"
        if RouVideoDownloader.is_rouvideo_url(self.url):
            return RouVideoDownloader, "RouVideo 链接，使用专用解析器"
        if MacCMSDownloader.is_maccms_url(self.url):
            return MacCMSDownloader, "MacCMS 视频站，使用专用解析器"
        return None, None

    def _run_site(self, cls, **run_kwargs):
        site = cls(output_dir=self.output_base_dir, proxy=self.proxy, cookie=self.cookie_file,
                   timeout=self.timeout, progress_callback=self._log,
                   progress=self.reporter._progress_cb, cancel_event=self.cancel_event,
                   threads=self.threads)
        mode = self.mode
        if mode == 'audio' and cls is not DouyinDownloader:
            self._log("[!] 该站点不支持单独下载音频，改为下载视频")
            mode = 'video'
        try:
            success = site.run(self.url, mode=mode, **run_kwargs)
        except Cancelled:
            self._log("[!] 已取消")
            success = False
        site.remove_empty_save_dir()
        self.downloaded_count, self.failed_count = site.downloaded_count, site.failed_count
        self.saved_files, self.output_dir = site.saved_files, site.save_dir
        self.info = getattr(site, 'info', None)
        if self.info and self.info_callback:
            self.info_callback(self._normalize_site_info(self.info))
        return success

    @staticmethod
    def _normalize_site_info(info):
        return {
            'title': info.get('title') or info.get('nameZh') or info.get('name') or '',
            'duration': info.get('duration') or 0,
            'uploader': info.get('author') or info.get('from') or '',
            'view_count': (info.get('statistics') or {}).get('play_count') or info.get('viewCount'),
        }

    def _try_maccms_by_content(self):
        """yt-dlp 不认识的网址：看页面里有没有 MacCMS 的 player_aaaa"""
        try:
            session = make_session(proxy=self.proxy, cookie=self.cookie_file, log=lambda m: None)
            resp = session.get(self.url, timeout=(10, self.timeout))
            if resp.ok and MacCMSDownloader.looks_like_maccms(resp.text):
                if 'charset' not in resp.headers.get('content-type', '').lower():
                    resp.encoding = resp.apparent_encoding or 'utf-8'
                self._log("[*] 页面是 MacCMS 视频站，改用专用解析器")
                return self._run_site(MacCMSDownloader, html=resp.text)
        except Exception:
            pass
        return None

    # ------------------------------------------------------------ yt-dlp

    def _base_opts(self):
        opts = {
            'quiet': True,
            'noprogress': True,
            'logger': _YdlLogger(self._log),
            'socket_timeout': self.timeout,
            'noplaylist': not self.download_playlist,
            'js_runtimes': JS_RUNTIMES,
        }
        if self.proxy:
            opts['proxy'] = self.proxy
        if self.cookie_file:
            if os.path.isfile(self.cookie_file) and is_netscape_cookie_file(self.cookie_file):
                opts['cookiefile'] = self.cookie_file
            else:
                session = make_session(cookie=self.cookie_file, log=lambda m: None)
                if session.headers.get('Cookie'):
                    opts['http_headers'] = {'Cookie': session.headers['Cookie']}
        return opts

    def _output_template(self):
        base = os.path.abspath(self.output_base_dir).replace('%', '%%')
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        folder = f"{url_domain(self.url)}-%(playlist_title,title).20s-{ts}"
        name = '%(title).80s.%(ext)s'
        if self.download_playlist:
            name = '%(playlist_index&{:03d} - |)s' + name
        return os.path.join(base, folder, name)

    def _download_opts(self):
        opts = self._base_opts()
        opts.update({
            'outtmpl': self._output_template(),
            'windowsfilenames': True,
            'overwrites': False,
            'continuedl': True,
            'retries': 5,
            'fragment_retries': 5,
            'concurrent_fragment_downloads': 4,
            'progress_hooks': [self._progress_hook],
            'post_hooks': [self._post_hook],
        })
        if not self.download_playlist:
            opts['playlist_items'] = '1'
        ffmpeg = has_ffmpeg()
        postprocessors = []

        if self.mode == 'video':
            spec = self.format_spec
            if '+' in spec and not ffmpeg:
                spec = '/'.join(p for p in spec.split('/') if '+' not in p) or 'best'
                self._log(f"[!] 未检测到 ffmpeg，无法合并音视频流，改用单文件格式: {spec}")
            opts['format'] = spec
            opts['merge_output_format'] = self.merge_output_format
            if self.download_subtitle:
                opts.update(writesubtitles=True, writeautomaticsub=True,
                            subtitleslangs=self.sub_langs, subtitlesformat='srt/best')
                if ffmpeg:
                    postprocessors.append({'key': 'FFmpegSubtitlesConvertor', 'format': 'srt'})
            if self.download_thumbnail:
                opts['writethumbnail'] = True

        elif self.mode == 'audio':
            opts['format'] = 'bestaudio/best'
            if ffmpeg:
                postprocessors.append({
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': None if self.audio_format == 'best' else self.audio_format,
                    'preferredquality': self.audio_quality,
                })
                if self.embed_thumbnail:
                    opts['writethumbnail'] = True
                    postprocessors += [{'key': 'FFmpegMetadata'}, {'key': 'EmbedThumbnail'}]
            elif self.audio_format != 'best' or self.embed_thumbnail:
                self._log("[!] 未检测到 ffmpeg，无法转换格式/嵌入封面，将保存原始音频")

        if postprocessors:
            opts['postprocessors'] = postprocessors
        return opts

    def _progress_hook(self, d):
        if self.cancel_event.is_set():
            raise DownloadCancelled()
        info = d.get('info_dict') or {}
        key = info.get('id') or info.get('title')
        if key and key not in self._announced:
            self._announced.add(key)
            self.reporter.end_progress()
            self._log(f"[+] {info.get('title', 'N/A')}  时长 {format_duration(info.get('duration'))}")
            if self.info is None:
                self.info = info
                if self.info_callback:
                    self.info_callback(info)
        if d['status'] == 'downloading':
            vcodec, acodec = info.get('vcodec'), info.get('acodec')
            kind = '音频' if vcodec == 'none' else '视频' if acodec == 'none' else ''
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            done = d.get('downloaded_bytes') or 0
            speed = f"{format_size(d['speed'])}/s" if d.get('speed') else ''
            eta = f"剩余 {format_duration(d['eta'])}" if d.get('eta') else ''
            text = '  '.join(t for t in (kind, f"{format_size(done)} / {format_size(total)}", speed, eta) if t)
            self.reporter.progress(done, total, text)
        elif d['status'] == 'finished':
            self.reporter.end_progress()

    def _post_hook(self, path):
        self.reporter.end_progress()
        self.downloaded_count += 1
        self.saved_files.append(path)
        self.output_dir = os.path.dirname(path)
        size = os.path.getsize(path) if os.path.exists(path) else 0
        self._log(f"[+] 已保存: {os.path.basename(path)} ({format_size(size)})")

    def fetch_info(self):
        """只解析不下载，失败返回 None"""
        opts = self._base_opts()
        opts['extract_flat'] = 'in_playlist'
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.sanitize_info(ydl.extract_info(self.url, download=False))
        except Exception as e:
            self._log(f"[-] 获取信息失败: {self._error_text(e)}")
            return None

    @staticmethod
    def _error_text(e):
        msg = str(e).replace('ERROR: ', '').strip()
        hints = (
            ('Unsupported URL', '不支持该网址'),
            ('HTTP Error 403', '服务器拒绝访问，可能需要 Cookie 或代理'),
            ('HTTP Error 429', '请求过于频繁，稍后再试或换代理'),
            ('Sign in to confirm', '需要登录，请提供 Cookie 文件'),
            ('Private video', '私密视频，需要有权限账号的 Cookie'),
            ('timed out', '网络超时，检查网络或代理'),
        )
        for key, hint in hints:
            if key in msg:
                return f"{hint}（{msg[:200]}）"
        return msg[:300]

    def print_info(self, info):
        if not info:
            return
        self._log("=" * 60)
        self._log(f"标题: {info.get('title', 'N/A')}")
        if info.get('_type') == 'playlist':
            entries = info.get('entries') or []
            self._log(f"类型: 播放列表，共 {len(entries)} 个")
            for i, e in enumerate(entries[:20], 1):
                self._log(f"  {i:3d}. {e.get('title') or e.get('url')}")
            if len(entries) > 20:
                self._log(f"  …… 其余 {len(entries) - 20} 个")
            self._log("=" * 60)
            return
        self._log(f"时长: {format_duration(info.get('duration'))}    上传者: {info.get('uploader', 'N/A')}")
        self._log(f"上传日期: {info.get('upload_date', 'N/A')}    播放量: {info.get('view_count', 'N/A')}    "
                  f"点赞数: {info.get('like_count', 'N/A')}")
        self._log(f"描述: {(info.get('description') or 'N/A')[:200]}")
        formats = info.get('formats') or []
        if formats:
            self._log(f"\n可用格式 (共 {len(formats)} 个):")
            self._log(f"{'格式ID':<14}{'扩展名':<7}{'分辨率':<12}{'大小':<10}备注")
            self._log("-" * 60)
            for f in formats:
                if f.get('width') and f.get('height'):
                    res = f"{f['width']}x{f['height']}"
                elif f.get('height'):
                    res = f"{f['height']}p"
                else:
                    res = 'audio only' if f.get('vcodec') == 'none' else 'N/A'
                size = f.get('filesize') or f.get('filesize_approx')
                notes = []
                if f.get('vcodec') not in (None, 'none'):
                    notes.append(f"v:{f['vcodec'][:10]}")
                if f.get('acodec') not in (None, 'none'):
                    notes.append(f"a:{f['acodec'][:10]}")
                if f.get('tbr'):
                    notes.append(f"{f['tbr']:.0f}k")
                self._log(f"{str(f.get('format_id')):<14}{str(f.get('ext')):<7}{res:<12}"
                          f"{format_size(size) if size else 'N/A':<10}{' '.join(notes)}")
        self._log("=" * 60)

    def _run_ytdlp(self):
        if yt_dlp is None:
            self._log("[-] 缺少依赖 yt-dlp，请运行 pip install -r requirements.txt")
            return False
        if self.mode == 'info':
            info = self.fetch_info()
            if info and self.info_callback:
                self.info_callback(info)
            self.print_info(info)
            return info is not None

        names = {'video': '视频', 'audio': '音频'}
        self._log("=" * 60)
        self._log(f"{names.get(self.mode, self.mode)}下载    地址: {self.url}")
        self._log(f"输出根目录: {os.path.abspath(self.output_base_dir)}")
        if self.mode == 'video':
            self._log(f"格式: {self.format_spec}    合并为: {self.merge_output_format}")
        else:
            self._log(f"音频格式: {self.audio_format}    质量: {self.audio_quality}")
        self._log("=" * 60)

        start = time.time()
        self._log("[*] 正在解析…")
        try:
            with yt_dlp.YoutubeDL(self._download_opts()) as ydl:
                result = ydl.extract_info(self.url, download=True)
        except DownloadCancelled:
            self.reporter.end_progress()
            self._log("[!] 已取消（未完成的 .part 文件保留，下次可续传）")
            return False
        except DownloadError as e:
            self.reporter.end_progress()
            if 'Unsupported URL' in str(e):
                fallback = self._try_maccms_by_content()
                if fallback is not None:
                    return fallback
            self._log(f"[-] 下载失败: {self._error_text(e)}")
            self.failed_count += 1
            return False
        except Exception as e:
            self.reporter.end_progress()
            self._log(f"[-] 下载失败: {self._error_text(e)}")
            self.failed_count += 1
            return False

        if (result and result.get('_type') == 'playlist' and not self.download_playlist
                and (result.get('playlist_count') or 0) > 1):
            self._log("[!] 这是播放列表，只下载了第一个；勾选“下载播放列表”或加 --playlist 可下载全部")

        self._log("\n" + "=" * 60)
        self._log(f"下载完成! 文件: {self.downloaded_count} 个    耗时: {time.time() - start:.1f} 秒")
        if self.output_dir:
            self._log(f"保存位置: {self.output_dir}")
        self._log("=" * 60)
        return self.downloaded_count > 0

    def run(self):
        """按网址选择下载方式并执行，成功返回 True"""
        cls, note = self._site_class()
        if cls:
            self._log(f"[*] 检测到{note}")
            return self._run_site(cls)
        return self._run_ytdlp()

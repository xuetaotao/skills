# -*- coding: utf-8 -*-
"""
RouVideo (rou.video) 视频下载器
支持解析 rou.video 视频页面，解密加密的视频源 URL，下载 HLS 视频流

工作机制：
1. 请求视频页面 HTML
2. 从 __NEXT_DATA__ 中提取 ev 加密数据 (d, k)
3. 解密：base64_decode(d) → 每字节减 k → JSON 解析 → 得到 videoUrl (m3u8)
4. 使用 yt-dlp / ffmpeg / 自有下载器下载 m3u8 视频

注意：
- videoUrl 实际是 m3u8 文件但伪装为 .jpg 后缀
- m3u8 中的 TS 分片也伪装为 .jpg 后缀
- CDN 需要带 Referer: https://rou.video/
- auth 参数有时效性 (exp 字段为 Unix 时间戳)
"""

import os
import re
import json
import base64
import time
import requests
from datetime import datetime
from urllib.parse import urlparse


class RouVideoDownloader:
    """RouVideo (rou.video) 视频下载器"""

    PC_UA = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )

    def __init__(self, output_dir='./output', proxy=None, cookie=None,
                 timeout=30, progress_callback=None):
        """
        初始化 RouVideo 下载器

        Args:
            output_dir: 输出目录
            proxy: 代理地址
            cookie: Cookie 字符串或文件路径
            timeout: 请求超时时间
            progress_callback: 进度回调函数
        """
        self.output_dir = output_dir
        self.proxy = proxy
        self.cookie = cookie
        self.timeout = timeout
        self.progress_callback = progress_callback

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.PC_UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })

        if proxy:
            self.session.proxies = {
                'http': proxy,
                'https': proxy,
            }

        if cookie:
            self._setup_cookie(cookie)

        # 下载统计
        self.downloaded_count = 0
        self.failed_count = 0
        self._source_origin = ''

    def _log(self, msg):
        """输出日志"""
        if self.progress_callback:
            self.progress_callback(msg)
        else:
            print(msg)

    def _setup_cookie(self, cookie):
        """设置 Cookie"""
        if os.path.isfile(cookie):
            try:
                with open(cookie, 'r', encoding='utf-8') as f:
                    cookie_str = f.read().strip()
                self.session.headers['Cookie'] = cookie_str
            except Exception as e:
                self._log(f"[-] 读取 Cookie 文件失败: {e}")
        else:
            self.session.headers['Cookie'] = cookie

    @staticmethod
    def is_rouvideo_url(url):
        """判断 URL 是否是 rou.video 链接"""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        return domain == 'rou.video' or domain == 'www.rou.video'

    def _fetch_page(self, url):
        """获取页面内容"""
        try:
            self._log(f"[*] 请求页面: {url}")
            parsed = urlparse(url)
            self._source_origin = f'{parsed.scheme}://{parsed.netloc}/'
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            if resp.encoding and resp.encoding.lower() != 'utf-8':
                resp.encoding = resp.apparent_encoding or 'utf-8'
            return resp.text
        except Exception as e:
            self._log(f"[-] 请求页面失败: {e}")
            return None

    def _extract_next_data(self, html):
        """
        从 HTML 中提取 __NEXT_DATA__ JSON 数据

        Returns:
            dict: 解析后的 JSON 数据，失败返回 None
        """
        pattern = re.compile(
            r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            re.DOTALL
        )
        match = pattern.search(html)
        if not match:
            self._log("[-] 未找到 __NEXT_DATA__")
            return None

        try:
            data = json.loads(match.group(1))
            return data
        except json.JSONDecodeError as e:
            self._log(f"[-] 解析 __NEXT_DATA__ 失败: {e}")
            return None

    def _extract_video_info(self, html):
        """
        从页面 HTML 提取视频信息和加密数据

        Returns:
            dict: 包含视频信息和加密数据的字典，失败返回 None
        """
        next_data = self._extract_next_data(html)
        if not next_data:
            return None

        page_props = next_data.get('props', {}).get('pageProps', {})
        video_data = page_props.get('video', {})
        ev_data = page_props.get('ev', {})

        if not video_data:
            self._log("[-] 未找到视频数据")
            return None

        info = {
            'id': video_data.get('id', ''),
            'name': video_data.get('name', ''),
            'nameZh': video_data.get('nameZh', ''),
            'description': video_data.get('description', ''),
            'tags': video_data.get('tags', []),
            'duration': video_data.get('duration', 0),
            'viewCount': video_data.get('viewCount', 0),
            'likeCount': video_data.get('likeCount', 0),
            'createdAt': video_data.get('createdAt', ''),
            'coverImageUrl': video_data.get('coverImageUrl', ''),
            'sources': video_data.get('sources', []),
            'ev': ev_data,
            'page_url': '',
            'videoUrl': None,
            'thumbVTTUrl': None,
        }

        # 解密视频 URL
        if ev_data and 'd' in ev_data and 'k' in ev_data:
            decrypted = self._decrypt_ev(ev_data['d'], ev_data['k'])
            if decrypted:
                info['videoUrl'] = decrypted.get('videoUrl')
                info['thumbVTTUrl'] = decrypted.get('thumbVTTUrl')

        return info

    def _decrypt_ev(self, d, k):
        """
        解密 rou.video 的加密视频数据

        解密逻辑 (等价于前端 JS):
        JSON.parse(atob(d).split("").map(e => String.fromCharCode(e.charCodeAt(0) - k)).join(""))

        Args:
            d: Base64 编码的加密数据
            k: 偏移量密钥 (整数)

        Returns:
            dict: 解密后的数据，包含 videoUrl 和 thumbVTTUrl，失败返回 None
        """
        try:
            # Step 1: Base64 解码
            decoded_bytes = base64.b64decode(d)

            # Step 2: 每个字节减去 k，然后转为字符
            decrypted_chars = []
            for b in decoded_bytes:
                decrypted_chars.append(chr(b - k))
            decrypted_str = ''.join(decrypted_chars)

            # Step 3: JSON 解析
            result = json.loads(decrypted_str)
            return result

        except Exception as e:
            self._log(f"[-] 解密视频数据失败: {e}")
            return None

    def fetch_video_info(self, url):
        """
        获取视频信息

        Args:
            url: 视频页面 URL

        Returns:
            dict: 视频信息，失败返回 None
        """
        html = self._fetch_page(url)
        if not html:
            return None

        info = self._extract_video_info(html)
        if info:
            info['page_url'] = url
        return info

    def download_with_ytdlp(self, video_url, output_dir, title=''):
        """
        使用 yt-dlp 下载视频（支持 m3u8）

        Returns:
            bool: 是否成功
        """
        try:
            import yt_dlp
        except ImportError:
            self._log("[-] yt-dlp 未安装，无法下载 m3u8 视频")
            return False

        safe_title = re.sub(r'[\\/:*?"<>|]', '', title)[:50].rstrip()
        if not safe_title:
            safe_title = 'video'

        output_template = os.path.join(output_dir, f'{safe_title}.%(ext)s')

        ydl_opts = {
            'outtmpl': output_template,
            'nocheckcertificate': True,
            'http_headers': {
                'Referer': self._source_origin or 'https://rou.video/',
                'Origin': 'https://rou.video',
                'User-Agent': self.PC_UA,
            },
        }

        if self.proxy:
            ydl_opts['proxy'] = self.proxy

        def progress_hook(d):
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                if total:
                    percent = downloaded / total * 100
                    speed = d.get('speed', 0)
                    speed_mb = speed / 1024 / 1024 if speed else 0
                    self._log(f"    下载进度: {percent:.0f}%, 速度: {speed_mb:.1f}MB/s")
            elif d['status'] == 'finished':
                self._log(f"[+] 视频下载完成")

        ydl_opts['progress_hooks'] = [progress_hook]

        try:
            self._log(f"[*] 使用 yt-dlp 下载: {video_url[:80]}...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
            self.downloaded_count += 1
            return True
        except Exception as e:
            self._log(f"[-] yt-dlp 下载失败: {e}")
            return False

    def download_with_ffmpeg(self, video_url, output_dir, title=''):
        """
        使用 ffmpeg 下载 m3u8 视频

        Returns:
            bool: 是否成功
        """
        import subprocess
        import shutil as _shutil

        ffmpeg_path = _shutil.which('ffmpeg')
        if not ffmpeg_path:
            self._log("[-] ffmpeg 未安装")
            return False

        safe_title = re.sub(r'[\\/:*?"<>|]', '', title)[:50].rstrip()
        if not safe_title:
            safe_title = 'video'
        filepath = os.path.join(output_dir, f'{safe_title}.mp4')

        if os.path.exists(filepath):
            self._log(f"[~] 文件已存在，跳过: {safe_title}.mp4")
            return True

        cmd = [
            ffmpeg_path,
            '-y',
            '-user_agent', self.PC_UA,
            '-headers', f'Referer: {self._source_origin or "https://rou.video/"}\r\n',
            '-i', video_url,
            '-c', 'copy',
            '-bsf:a', 'aac_adtstoasc',
            filepath,
        ]

        try:
            self._log(f"[*] 使用 ffmpeg 下载: {video_url[:80]}...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode == 0:
                file_size_mb = os.path.getsize(filepath) / 1024 / 1024
                self._log(f"[+] 下载完成: {safe_title}.mp4 ({file_size_mb:.1f}MB)")
                self.downloaded_count += 1
                return True
            else:
                self._log(f"[-] ffmpeg 错误: {result.stderr[:200]}")
                return False
        except Exception as e:
            self._log(f"[-] ffmpeg 下载失败: {e}")
            return False

    def _download_m3u8(self, m3u8_url, output_dir, title=''):
        """
        自有 m3u8 下载器

        解析 m3u8 文件，逐个下载 TS 分片，最后合并为 mp4

        Returns:
            bool: 是否成功
        """
        safe_title = re.sub(r'[\\/:*?"<>|]', '', title)[:50].rstrip()
        if not safe_title:
            safe_title = 'video'

        ts_dir = os.path.join(output_dir, f'{safe_title}_ts')
        os.makedirs(ts_dir, exist_ok=True)

        download_headers = {
            'Referer': self._source_origin or 'https://rou.video/',
            'User-Agent': self.PC_UA,
        }

        # 1. 下载 m3u8 文件
        try:
            self._log(f"[*] 获取 m3u8 播放列表: {m3u8_url[:80]}...")
            resp = self.session.get(m3u8_url, headers=download_headers,
                                    timeout=self.timeout)
            resp.raise_for_status()

            if '#EXTM3U' not in resp.text:
                self._log(f"[-] 返回内容不是 m3u8 格式")
                return False

        except Exception as e:
            self._log(f"[-] 获取 m3u8 失败: {e}")
            return False

        # 2. 解析 m3u8
        lines = resp.text.strip().split('\n')
        ts_urls = []

        # m3u8 中的 TS URL 可能是完整的 https URL
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                ts_urls.append(line)

        if not ts_urls:
            self._log("[-] m3u8 中没有 TS 分片")
            return False

        self._log(f"[+] 发现 {len(ts_urls)} 个 TS 分片")

        # 3. 下载 TS 分片
        ts_files = []
        failed_ts = []

        for i, ts_url in enumerate(ts_urls):
            ts_filename = f'{i:05d}.ts'
            ts_filepath = os.path.join(ts_dir, ts_filename)

            if os.path.exists(ts_filepath):
                ts_files.append(ts_filepath)
                continue

            try:
                ts_resp = self.session.get(ts_url, headers=download_headers,
                                           timeout=self.timeout)
                ts_resp.raise_for_status()

                with open(ts_filepath, 'wb') as f:
                    f.write(ts_resp.content)

                ts_files.append(ts_filepath)

                # 进度提示
                if (i + 1) % 10 == 0 or (i + 1) == len(ts_urls):
                    percent = (i + 1) / len(ts_urls) * 100
                    self._log(f"    TS 分片进度: {i+1}/{len(ts_urls)} ({percent:.0f}%)")

            except Exception as e:
                self._log(f"[-] TS 分片 {i} 下载失败: {e}")
                failed_ts.append(i)

        if len(ts_files) < len(ts_urls) * 0.5:
            self._log(f"[-] 超过半数 TS 分片下载失败")
            for f in ts_files:
                if os.path.exists(f):
                    os.remove(f)
            try:
                os.rmdir(ts_dir)
            except OSError:
                pass
            return False

        # 4. 合并 TS 分片为 MP4
        output_path = os.path.join(output_dir, f'{safe_title}.mp4')

        if os.path.exists(output_path):
            self._log(f"[~] 文件已存在，跳过合并")
        else:
            self._log(f"[*] 合并 {len(ts_files)} 个 TS 分片...")
            try:
                with open(output_path, 'wb') as outf:
                    for ts_file in ts_files:
                        if os.path.exists(ts_file):
                            with open(ts_file, 'rb') as inf:
                                outf.write(inf.read())

                file_size_mb = os.path.getsize(output_path) / 1024 / 1024
                self._log(f"[+] 合并完成: {safe_title}.mp4 ({file_size_mb:.1f}MB)")

            except Exception as e:
                self._log(f"[-] 合并失败: {e}")
                if os.path.exists(output_path):
                    os.remove(output_path)
                for f in ts_files:
                    if os.path.exists(f):
                        os.remove(f)
                try:
                    os.rmdir(ts_dir)
                except OSError:
                    pass
                return False

        # 5. 清理 TS 分片
        try:
            for f in ts_files:
                if os.path.exists(f):
                    os.remove(f)
            os.rmdir(ts_dir)
        except OSError:
            pass

        self.downloaded_count += 1
        return True

    def _generate_subdir_name(self, video_info):
        """生成子目录名"""
        title = video_info.get('nameZh', '') or video_info.get('name', '')
        safe_title = re.sub(r'[\\/:*?"<>|]', '', title)[:20].rstrip()
        time_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        parts = [p for p in ['rouvideo', safe_title, time_str] if p]
        return '-'.join(parts)

    def _print_video_info(self, info):
        """打印视频信息"""
        self._log("=" * 60)
        self._log(f"标题: {info.get('name', 'N/A')}")
        self._log(f"中文标题: {info.get('nameZh', 'N/A')}")
        self._log(f"视频 ID: {info.get('id', 'N/A')}")
        self._log(f"时长: {self._format_duration(info.get('duration', 0))}")
        self._log(f"播放量: {info.get('viewCount', 'N/A')}")
        self._log(f"点赞数: {info.get('likeCount', 'N/A')}")
        self._log(f"标签: {', '.join(info.get('tags', []))}")
        self._log(f"创建时间: {info.get('createdAt', 'N/A')}")

        video_url = info.get('videoUrl')
        if video_url:
            self._log(f"视频地址: {video_url[:100]}...")
        else:
            self._log("视频地址: 未获取到（可能需要登录）")

        sources = info.get('sources', [])
        if sources:
            resolutions = [s.get('resolution', '?') for s in sources]
            self._log(f"可用分辨率: {resolutions}")

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

    def run(self, url, mode='video'):
        """
        运行下载流程

        Args:
            url: rou.video 视频 URL
            mode: 下载模式 - 'video'/'info'

        Returns:
            bool: 是否成功
        """
        self._log("=" * 60)
        self._log(f"RouVideo 下载器 - {mode} 模式")
        self._log("=" * 60)
        self._log(f"地址: {url}")
        self._log(f"输出目录: {os.path.abspath(self.output_dir)}")
        self._log("=" * 60)

        # 获取视频信息
        video_info = self.fetch_video_info(url)
        if not video_info:
            self._log("[-] 无法获取视频信息")
            return False

        # 信息查看模式
        if mode == 'info':
            self._print_video_info(video_info)
            return True

        video_url = video_info.get('videoUrl')
        title = video_info.get('nameZh', '') or video_info.get('name', '') or '未命名'

        if not video_url:
            self._log("[-] 无法获取视频下载地址")
            self._log("[!] 可能原因：")
            self._log("    1) 页面结构变更，加密数据格式改变")
            self._log("    2) 视频需要登录才能观看")
            self._log("    3) 视频已被删除")
            return False

        # 生成子目录
        subdir_name = self._generate_subdir_name(video_info)
        save_dir = os.path.join(self.output_dir, subdir_name)
        os.makedirs(save_dir, exist_ok=True)

        # 显示信息
        self._log(f"[+] 标题: {title}")
        self._log(f"[+] 时长: {self._format_duration(video_info.get('duration', 0))}")
        self._log(f"[+] 播放量: {video_info.get('viewCount', 'N/A')}")
        self._log(f"[+] 视频地址: {video_url[:80]}...")

        # 下载
        start_time = time.time()
        success = False

        # m3u8 格式（rou.video 的 videoUrl 是伪装为 .jpg 的 m3u8）
        # 优先用自有下载器（保持 session cookies 和 Referer），备选 yt-dlp/ffmpeg
        success = self._download_m3u8(video_url, save_dir, title)
        if not success:
            self._log("[*] 自有下载器失败，尝试 yt-dlp...")
            success = self.download_with_ytdlp(video_url, save_dir, title)
        if not success:
            self._log("[*] yt-dlp 下载失败，尝试 ffmpeg...")
            success = self.download_with_ffmpeg(video_url, save_dir, title)

        elapsed_time = time.time() - start_time

        # 统计
        self._log("\n" + "=" * 60)
        self._log("下载完成!" if success else "下载失败!")
        self._log(f"成功: {self.downloaded_count}")
        self._log(f"失败: {self.failed_count}")
        self._log(f"总耗时: {elapsed_time:.2f} 秒")
        if save_dir:
            self._log(f"保存位置: {os.path.abspath(save_dir)}")
        self._log("=" * 60)

        if not success:
            self.failed_count += 1

        return success

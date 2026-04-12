# -*- coding: utf-8 -*-
"""
MacCMS (苹果CMS) 视频站解析器
支持解析基于 MacCMS 模板的视频网站，自动提取 m3u8/mp4 视频地址
并使用 yt-dlp 或 ffmpeg 下载

MacCMS URL 模式:
- /index.php/vod/play/id/{id}/sid/{sid}/nid/{nid}.html
- /vod/play/id/{id}/sid/{sid}/nid/{nid}.html

player_aaaa 变量中的 encrypt 字段:
- 0: 无加密，url 直接是视频地址
- 1: 单层 URL 编码
- 2: Base64 + 双层 URL 编码
"""

import os
import re
import json
import base64
import time
import requests
from urllib.parse import unquote, urlparse
from datetime import datetime


class MacCMSDownloader:
    """MacCMS (苹果CMS) 视频站解析下载器"""

    # 请求头
    PC_UA = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )

    def __init__(self, output_dir='./output', proxy=None, cookie=None,
                 timeout=30, progress_callback=None):
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

        self.downloaded_count = 0
        self.failed_count = 0
        self._source_origin = ''  # 源站 origin，用作下载 Referer

    def _log(self, msg):
        if self.progress_callback:
            self.progress_callback(msg)
        else:
            print(msg)

    def _setup_cookie(self, cookie):
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
    def is_maccms_url(url):
        """判断 URL 是否是 MacCMS 站点"""
        parsed = urlparse(url)
        path = parsed.path.lower()

        # MacCMS 典型路径模式
        maccms_patterns = [
            r'/index\.php/vod/play/',
            r'/vod/play/',
            r'/play/',
            r'/index\.php/vod/detail/',
            r'/vod/detail/',
        ]
        for pattern in maccms_patterns:
            if re.search(pattern, path):
                return True

        return False

    def _fetch_page(self, url):
        """获取页面内容"""
        try:
            self._log(f"[*] 请求页面: {url}")
            # 保存源站 URL 作为 Referer
            parsed = urlparse(url)
            self._source_origin = f'{parsed.scheme}://{parsed.netloc}/'
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            # 尝试检测编码
            if resp.encoding and resp.encoding.lower() != 'utf-8':
                resp.encoding = resp.apparent_encoding or 'utf-8'
            return resp.text
        except Exception as e:
            self._log(f"[-] 请求页面失败: {e}")
            return None

    def _extract_player_data(self, html):
        """
        从页面 HTML 中提取 player_aaaa 数据

        Returns:
            dict: player_aaaa 数据，失败返回 None
        """
        # 匹配 player_aaaa 变量
        pattern = re.compile(
            r'var\s+player_aaaa\s*=\s*(\{.*?\})\s*;?\s*</script>',
            re.DOTALL
        )
        match = pattern.search(html)
        if not match:
            # 尝试另一种格式
            pattern2 = re.compile(
                r'player_aaaa\s*=\s*(\{.*?\})\s*;?\s*\n',
                re.DOTALL
            )
            match = pattern2.search(html)

        if not match:
            self._log("[-] 未找到 player_aaaa 变量")
            return None

        try:
            data = json.loads(match.group(1))
            return data
        except json.JSONDecodeError as e:
            self._log(f"[-] 解析 player_aaaa 失败: {e}")
            return None

    def _decrypt_url(self, url, encrypt):
        """
        解密 MacCMS 加密的视频 URL

        Args:
            url: 加密的 URL 字符串
            encrypt: 加密级别 (0/1/2)

        Returns:
            str: 解密后的视频 URL
        """
        if encrypt == 0:
            # 无加密
            return url
        elif encrypt == 1:
            # 单层 URL 编码
            return unquote(url)
        elif encrypt == 2:
            # Base64 + 双层 URL 编码
            # 步骤: 双层 URL 解码 -> Base64 解码 -> 双层 URL 解码
            try:
                d1 = unquote(unquote(url))
                d2 = base64.b64decode(d1).decode('utf-8')
                d3 = unquote(unquote(d2))
                return d3
            except Exception as e:
                self._log(f"[-] encrypt=2 解密失败: {e}")
                # 降级尝试: 直接 Base64 + URL 解码
                try:
                    d1 = base64.b64decode(url).decode('utf-8')
                    return unquote(unquote(d1))
                except:
                    return url
        else:
            self._log(f"[!] 未知加密级别: {encrypt}，尝试直接解码")
            # 尝试各种解码方式
            for attempt in [
                lambda u: unquote(u),
                lambda u: unquote(unquote(u)),
                lambda u: unquote(base64.b64decode(u).decode('utf-8')),
                lambda u: unquote(unquote(base64.b64decode(u).decode('utf-8'))),
            ]:
                try:
                    result = attempt(url)
                    if result.startswith('http'):
                        return result
                except:
                    continue
            return url

    def _extract_vod_info(self, html, player_data):
        """
        从页面提取视频信息

        Returns:
            dict: 视频信息
        """
        info = {
            'title': '',
            'cover': '',
            'video_url': '',
            'from': '',
            'vod_id': '',
        }

        # 从 player_data 获取基本信息
        vod_data = player_data.get('vod_data', {})
        info['title'] = vod_data.get('vod_name', '')
        info['from'] = player_data.get('from', '')
        info['vod_id'] = player_data.get('id', '')

        # 解密视频 URL
        encrypt = player_data.get('encrypt', 0)
        encrypted_url = player_data.get('url', '')
        if encrypted_url:
            info['video_url'] = self._decrypt_url(encrypted_url, encrypt)

        # 从页面提取封面
        cover_match = re.search(r'MacPlayer\.Pic\s*=\s*["\']([^"\']+)["\']', html)
        if cover_match:
            info['cover'] = cover_match.group(1)

        # 如果标题为空，从页面 title 标签提取
        if not info['title']:
            title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
            if title_match:
                # 去掉网站后缀
                title = title_match.group(1)
                title = re.split(r'[-_|]', title)[0].strip()
                info['title'] = title

        return info

    def fetch_video_info(self, url):
        """
        获取视频信息

        Returns:
            dict: 视频信息，失败返回 None
        """
        html = self._fetch_page(url)
        if not html:
            return None

        player_data = self._extract_player_data(html)
        if not player_data:
            return None

        info = self._extract_vod_info(html, player_data)
        info['page_url'] = url
        info['player_data'] = player_data

        return info

    def download_with_ytdlp(self, video_url, output_dir, title=''):
        """
        使用 yt-dlp 下载视频（支持 m3u8/mp4）

        Returns:
            bool: 是否成功
        """
        try:
            import yt_dlp
        except ImportError:
            self._log("[-] yt-dlp 未安装，无法下载 m3u8 视频")
            return False

        # 生成文件名
        safe_title = re.sub(r'[\\/:*?"<>|]', '', title)[:50].rstrip()
        if not safe_title:
            safe_title = 'video'

        output_template = os.path.join(output_dir, f'{safe_title}.%(ext)s')

        # 从 session 提取 cookies 传给 yt-dlp
        cookie_dict = dict(self.session.cookies)

        ydl_opts = {
            'outtmpl': output_template,
            'nocheckcertificate': True,
            'quiet': True,
            'no_warnings': True,
            'http_headers': {
                'Referer': self._source_origin or '',
            },
        }

        # 传入 session cookies
        if cookie_dict:
            ydl_opts['cookiefile'] = None
            # 直接通过 http_headers 设置 cookie
            cookie_str = '; '.join(f'{k}={v}' for k, v in cookie_dict.items())
            ydl_opts['http_headers']['Cookie'] = cookie_str

        if self.proxy:
            ydl_opts['proxy'] = self.proxy

        # 进度回调
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
            self._log(f"[*] 使用 yt-dlp 下载: {video_url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
            self.downloaded_count += 1
            return True
        except Exception as e:
            self._log(f"[-] yt-dlp 下载失败: {e}")
            return False

    def _download_m3u8(self, m3u8_url, output_dir, title=''):
        """
        自有 m3u8 下载器，使用同一 session 保持 cookies

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
            'Referer': self._source_origin or '',
        }

        # 1. 下载 m3u8 文件
        try:
            self._log(f"[*] 获取 m3u8 播放列表: {m3u8_url}")
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
        base_url = m3u8_url.rsplit('/', 1)[0] + '/'

        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                if line.startswith('http'):
                    ts_urls.append(line)
                else:
                    ts_urls.append(base_url + line)

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
            # 清理
            for f in ts_files:
                if os.path.exists(f):
                    os.remove(f)
            os.rmdir(ts_dir)
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
                # 清理 TS
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
            '-headers', f'Referer: {self._source_origin or self.session.headers.get("Referer", "")}\r\n',
            '-i', video_url,
            '-c', 'copy',
            '-bsf:a', 'aac_adtstoasc',
            filepath,
        ]

        try:
            self._log(f"[*] 使用 ffmpeg 下载: {video_url}")
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

    def download_with_requests(self, video_url, output_dir, title=''):
        """
        使用 requests 直接下载 mp4 视频

        Returns:
            bool: 是否成功
        """
        safe_title = re.sub(r'[\\/:*?"<>|]', '', title)[:50].rstrip()
        if not safe_title:
            safe_title = 'video'

        # 根据 URL 判断格式
        ext = '.mp4'
        if '.m3u8' in video_url:
            # m3u8 不能用 requests 直接下载
            self._log("[-] m3u8 格式需要 yt-dlp 或 ffmpeg 下载")
            return False

        filepath = os.path.join(output_dir, f'{safe_title}{ext}')

        if os.path.exists(filepath):
            self._log(f"[~] 文件已存在，跳过: {safe_title}{ext}")
            return True

        download_headers = {
            'Referer': self._source_origin or '',
        }

        try:
            self._log(f"[*] 下载视频: {safe_title}{ext}")
            resp = self.session.get(video_url, headers=download_headers,
                                    timeout=self.timeout, stream=True, verify=False)
            resp.raise_for_status()

            total_size = int(resp.headers.get('content-length', 0))
            downloaded = 0

            with open(filepath, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size and downloaded % (512 * 1024) < 8192:
                            percent = downloaded / total_size * 100
                            self._log(f"    下载进度: {percent:.0f}%")

            file_size_mb = downloaded / 1024 / 1024
            if file_size_mb < 0.01:
                os.remove(filepath)
                self._log(f"[-] 下载文件过小，可能失败")
                return False

            self._log(f"[+] 下载完成: {safe_title}{ext} ({file_size_mb:.1f}MB)")
            self.downloaded_count += 1
            return True

        except Exception as e:
            self._log(f"[-] 下载失败: {e}")
            if os.path.exists(filepath):
                os.remove(filepath)
            return False

    def _generate_subdir_name(self, video_info):
        """生成子目录名"""
        title = video_info.get('title', '')
        safe_title = re.sub(r'[\\/:*?"<>|]', '', title)[:20].rstrip()
        time_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        parts = [p for p in ['maccms', safe_title, time_str] if p]
        return '-'.join(parts)

    def run(self, url, mode='video'):
        """
        运行下载流程

        Args:
            url: MacCMS 视频 URL
            mode: 下载模式 - 'video'/'audio'/'info'

        Returns:
            bool: 是否成功
        """
        import shutil

        self._log("=" * 60)
        self._log(f"MacCMS 视频下载器 - {mode} 模式")
        self._log("=" * 60)
        self._log(f"地址: {url}")
        self._log(f"输出目录: {os.path.abspath(self.output_dir)}")
        self._log("=" * 60)

        # 获取视频信息
        video_info = self.fetch_video_info(url)
        if not video_info:
            self._log("[-] 无法获取视频信息")
            self._log("[!] 该网站可能不是 MacCMS 站点或页面结构已变更")
            return False

        video_url = video_info.get('video_url', '')
        title = video_info.get('title', '未命名')

        # 信息查看模式
        if mode == 'info':
            self._print_video_info(video_info)
            return True

        if not video_url:
            self._log("[-] 无法提取视频下载地址")
            return False

        # 生成子目录
        subdir_name = self._generate_subdir_name(video_info)
        save_dir = os.path.join(self.output_dir, subdir_name)
        os.makedirs(save_dir, exist_ok=True)

        # 显示信息
        self._log(f"[+] 标题: {title}")
        self._log(f"[+] 播放源: {video_info.get('from', 'N/A')}")
        self._log(f"[+] 视频地址: {video_url}")

        # 下载
        start_time = time.time()
        success = False

        if video_url.endswith('.m3u8') or '.m3u8?' in video_url:
            # m3u8 格式，优先用自有下载器（保持 session cookies），备选 yt-dlp/ffmpeg
            success = self._download_m3u8(video_url, save_dir, title)
            if not success:
                self._log("[*] 自有下载器失败，尝试 yt-dlp...")
                success = self.download_with_ytdlp(video_url, save_dir, title)
            if not success:
                self._log("[*] yt-dlp 下载失败，尝试 ffmpeg...")
                success = self.download_with_ffmpeg(video_url, save_dir, title)
        else:
            # mp4 等直接下载格式
            success = self.download_with_requests(video_url, save_dir, title)
            if not success:
                # 降级到 yt-dlp
                success = self.download_with_ytdlp(video_url, save_dir, title)

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

    def _print_video_info(self, info):
        """打印视频信息"""
        self._log("=" * 60)
        self._log(f"标题: {info.get('title', 'N/A')}")
        self._log(f"视频 ID: {info.get('vod_id', 'N/A')}")
        self._log(f"播放源: {info.get('from', 'N/A')}")
        self._log(f"视频地址: {info.get('video_url', 'N/A')}")
        self._log(f"封面: {info.get('cover', 'N/A')}")
        self._log(f"页面: {info.get('page_url', 'N/A')}")
        if info.get('player_data'):
            pd = info['player_data']
            self._log(f"加密级别: {pd.get('encrypt', 'N/A')}")
            self._log(f"原始 URL: {pd.get('url', '')[:80]}...")
        self._log("=" * 60)

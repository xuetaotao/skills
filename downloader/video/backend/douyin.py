# -*- coding: utf-8 -*-
"""
抖音下载器（不依赖 yt-dlp）
- 单视频无水印下载、图集下载、背景音乐下载
- 短链接 v.douyin.com 自动解析
"""

import json
import os
import re
import subprocess
import time
from urllib.parse import urlparse

import requests

from .common import (MOBILE_UA, Cancelled, SiteDownloader, format_duration, has_ffmpeg, make_save_dir,
                     safe_name)

HEADERS = {'User-Agent': MOBILE_UA, 'Referer': 'https://www.douyin.com/'}


class DouyinDownloader(SiteDownloader):
    USER_AGENT = MOBILE_UA

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session.headers['Referer'] = 'https://www.douyin.com/'
        self._warmed = False

    def _warm_up(self):
        """分享页只有带着首页下发的 __ac_nonce / ttwid Cookie 访问才会返回视频数据"""
        if self._warmed:
            return
        self._warmed = True
        try:
            self.session.get('https://www.iesdouyin.com/', headers=HEADERS, timeout=self.timeouts)
        except Exception as e:
            self._log(f"[!] 获取访问 Cookie 失败: {e}")

    @staticmethod
    def is_douyin_url(url):
        domain = urlparse(url).netloc.lower()
        return domain == 'douyin.com' or domain.endswith('.douyin.com') or domain.endswith('iesdouyin.com')

    @staticmethod
    def classify_url(url):
        """返回 'video' / 'user' / 'note' / 'short' / 'unknown'"""
        u = url.lower()
        if 'modal_id=' in u or '/video/' in u:
            return 'video'
        if '/user/' in u:
            return 'user'
        if '/note/' in u:
            return 'note'
        if 'v.douyin.com' in u:
            return 'short'
        return 'unknown'

    def _resolve_short_url(self, url):
        """v.douyin.com 短链接 → 真实地址"""
        self._log(f"[*] 解析短链接: {url}")
        try:
            location = url
            for _ in range(5):
                resp = self.session.get(location, allow_redirects=False, timeout=self.timeouts)
                nxt = resp.headers.get('Location')
                if not nxt:
                    break
                location = requests.compat.urljoin(location, nxt)
                if '/video/' in location or '/note/' in location:
                    break
            self._log(f"[+] 真实地址: {location}")
            return location
        except Exception as e:
            self._log(f"[-] 解析短链接失败: {e}")
            return url

    @staticmethod
    def _extract_video_id(url):
        for pattern in (r'modal_id=(\d+)', r'/video/(\d+)', r'/note/(\d+)', r'/share/video/(\d+)'):
            m = re.search(pattern, url)
            if m:
                return m.group(1)
        return None

    def fetch_video_info(self, video_id):
        """通过 iesdouyin.com 分享页获取视频数据"""
        url = f'https://www.iesdouyin.com/share/video/{video_id}/'
        self._log(f"[*] 获取视频信息: {video_id}")
        self._warm_up()
        try:
            resp = self.session.get(url, headers=HEADERS, timeout=self.timeouts)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            self._log(f"[-] HTTP 错误: {e}")
            if e.response is not None and e.response.status_code == 404:
                self._log("[-] 视频可能已被删除或设为私密")
            return None
        except Exception as e:
            self._log(f"[-] 获取视频信息失败: {e}")
            return None

        m = re.search(r'window\._ROUTER_DATA\s*=\s*(.*?)</script>', resp.text, re.DOTALL)
        if m:
            return self._parse_router_data(m.group(1).strip())
        if 'RENDER_DATA' in resp.text:
            self._log("[-] 页面为 RENDER_DATA 格式，暂不支持自动解析，可尝试提供 Cookie")
        self._log("[-] 未找到视频数据（页面结构可能已变更，或需要登录 Cookie）")
        return None

    def _parse_router_data(self, json_str):
        try:
            loader = json.loads(json_str).get('loaderData', {})
        except json.JSONDecodeError:
            self._log("[-] 视频数据 JSON 解析失败")
            return None
        for value in loader.values():
            if isinstance(value, dict) and isinstance(value.get('videoInfoRes'), dict):
                res = value['videoInfoRes']
                items = res.get('item_list') or []
                if items and isinstance(items[0], dict):
                    return self._parse_video_item(items[0])
                for f in res.get('filter_list') or []:
                    self._log(f"[-] 抖音提示: {f.get('notice', '')} {f.get('detail_msg', '')}".rstrip())
                    return None
        self._log(f"[-] 页面里没有视频数据节点，可用 keys: {list(loader.keys())}")
        return None

    @staticmethod
    def _parse_video_item(item):
        author = item.get('author') or {}
        stats = item.get('statistics') or {}
        info = {
            'video_id': item.get('aweme_id', ''),
            'title': item.get('desc', ''),
            'author': author.get('nickname', ''),
            'author_id': author.get('unique_id') or author.get('sec_uid', ''),
            'create_time': item.get('create_time', 0),
            'duration': (item.get('duration') or 0) / 1000,
            'statistics': {k: stats.get(k, 0) for k in ('digg_count', 'comment_count', 'share_count', 'play_count')},
            'video_url': None,
            'video_urls': [],
            'cover_url': None,
            'music_url': None,
            'images': [],
            'is_image_set': False,
        }
        video = item.get('video') or {}
        play_addr = video.get('play_addr') or {}

        # 1. play_addr.uri 构造无水印地址（最可靠）
        if play_addr.get('uri'):
            info['video_url'] = f"https://www.douyin.com/aweme/v1/play/?video_id={play_addr['uri']}"
        # 2. url_list 里 playwm → play
        backups = [u.replace('playwm', 'play') for u in play_addr.get('url_list') or []]
        # 3. bit_rate 里的最高码率
        if not info['video_url'] and video.get('bit_rate'):
            best = max(video['bit_rate'], key=lambda x: x.get('bit_rate', 0)).get('play_addr') or {}
            if best.get('uri'):
                info['video_url'] = f"https://www.douyin.com/aweme/v1/play/?video_id={best['uri']}"
            backups = [u.replace('playwm', 'play') for u in best.get('url_list') or []] or backups
        info['video_urls'] = [u for u in [info['video_url']] + backups if u]
        info['video_url'] = info['video_url'] or (backups[0] if backups else None)

        covers = (video.get('cover') or {}).get('url_list') or []
        info['cover_url'] = covers[0] if covers else None
        info['music_url'] = ((item.get('music') or {}).get('play_url') or {}).get('url') or None
        for img in item.get('images') or []:
            if img.get('url_list'):
                info['images'].append(img['url_list'][0])
        info['is_image_set'] = bool(info['images'])
        return info

    def _title(self, info, default):
        return safe_name(info.get('title'), 60, default=info.get('video_id') or default)

    def download_video(self, info, save_dir):
        urls = list(dict.fromkeys(info.get('video_urls') or [info.get('video_url')]))
        urls = [u for u in urls if u]
        if not urls:
            self._log("[-] 无视频下载地址")
            return False
        filename = f"{self._title(info, 'video')}.mp4"
        path = os.path.join(save_dir, filename)
        if os.path.exists(path):
            self._log(f"[~] 文件已存在，跳过: {filename}")
            return True
        for i, url in enumerate(urls):
            self.reporter.check_cancel()
            self._log(f"[*] 下载视频: {filename}" + (f"（备选链接 {i}）" if i else ''))
            try:
                size = self.stream_download(url, path, HEADERS, accept=('video', 'octet-stream'))
                self._log(f"[+] 下载完成: {filename} ({size / 1024 / 1024:.1f} MB)")
                self.record_saved(path)
                return True
            except Cancelled:
                raise
            except Exception as e:
                self._log(f"[-] 下载失败（链接 {i}）: {e}")
        self._log("[-] 所有下载链接均失败")
        self.failed_count += 1
        return False

    def download_images(self, info, save_dir):
        title = self._title(info, 'images')
        ok = 0
        for i, url in enumerate(info.get('images') or []):
            self.reporter.check_cancel()
            filename = f"{title}_{i + 1:03d}.jpg"
            path = os.path.join(save_dir, filename)
            if os.path.exists(path):
                ok += 1
                continue
            try:
                self.stream_download(url, path, HEADERS, min_bytes=1024)
                self._log(f"[+] 下载完成: {filename}")
                self.record_saved(path)
                ok += 1
            except Cancelled:
                raise
            except Exception as e:
                self._log(f"[-] 下载失败: {filename} - {e}")
                self.failed_count += 1
        return ok > 0

    def _extract_audio_from_video(self, info, save_dir):
        """分享页不再提供原声地址时，下载视频后用 ffmpeg 提取音轨（不重新编码）"""
        if not has_ffmpeg():
            self._log("[-] 该视频没有单独的音频地址，提取音轨需要安装 ffmpeg；也可以改用视频模式")
            return False
        title = self._title(info, 'audio')
        audio_path = os.path.join(save_dir, f"{title}.m4a")
        if os.path.exists(audio_path):
            self._log(f"[~] 文件已存在，跳过: {os.path.basename(audio_path)}")
            return True
        tmp_video = os.path.join(save_dir, f"{title}.video.mp4")
        self._log("[*] 没有单独的音频地址，先下载视频再提取音轨")
        for url in [u for u in info.get('video_urls') or [] if u]:
            try:
                self.stream_download(url, tmp_video, HEADERS, accept=('video', 'octet-stream'))
                break
            except Cancelled:
                raise
            except Exception as e:
                self._log(f"[-] 视频下载失败: {e}")
        if not os.path.exists(tmp_video):
            self.failed_count += 1
            return False
        result = subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', tmp_video, '-vn', '-c:a', 'copy',
                                 audio_path], capture_output=True, text=True, encoding='utf-8', errors='replace')
        os.remove(tmp_video)
        if result.returncode != 0:
            self._log(f"[-] 提取音轨失败: {result.stderr.strip()[:200]}")
            self.failed_count += 1
            return False
        self._log(f"[+] 已保存: {os.path.basename(audio_path)} ({os.path.getsize(audio_path) / 1024 / 1024:.1f} MB)")
        self.record_saved(audio_path)
        return True

    def download_audio(self, info, save_dir):
        if not info.get('music_url'):
            return self._extract_audio_from_video(info, save_dir)
        filename = f"{self._title(info, 'audio')}.mp3"
        path = os.path.join(save_dir, filename)
        if os.path.exists(path):
            self._log(f"[~] 文件已存在，跳过: {filename}")
            return True
        try:
            self._log(f"[*] 下载音频: {filename}")
            size = self.stream_download(info['music_url'], path, HEADERS, min_bytes=1024)
            self._log(f"[+] 下载完成: {filename} ({size / 1024 / 1024:.1f} MB)")
            self.record_saved(path)
            return True
        except Cancelled:
            raise
        except Exception as e:
            self._log(f"[-] 下载失败: {filename} - {e}")
            self.failed_count += 1
            return False

    def run(self, url, mode='video'):
        """mode: 'video' / 'audio' / 'info'"""
        self._log("=" * 60)
        self._log(f"抖音下载器 - {mode} 模式    地址: {url}")
        self._log("=" * 60)
        start = time.time()

        if self.classify_url(url) == 'short':
            url = self._resolve_short_url(url)
        url_type = self.classify_url(url)
        video_id = self._extract_video_id(url)
        if not video_id:
            if url_type == 'user':
                self._log("[-] 用户主页链接无法批量下载，请复制单个视频的分享链接")
                self._log("[!] 在抖音 App 中打开视频 → 分享 → 复制链接")
            else:
                self._log("[-] 无法从链接中提取视频 ID，请使用视频分享链接，例如:")
                self._log("    https://v.douyin.com/xxxxxx/")
                self._log("    https://www.douyin.com/video/7620404072419577134")
            return False

        info = self.fetch_video_info(video_id)
        if not info:
            self._log("[-] 无法获取视频信息。可能原因：视频已删除/私密、需要登录 Cookie、网络或地区限制")
            return False
        self.info = info
        if mode == 'info':
            self._print_video_info(info)
            return True

        self._log(f"[+] 标题: {info.get('title') or 'N/A'}")
        self._log(f"[+] 作者: {info.get('author') or 'N/A'}    类型: {'图集' if info['is_image_set'] else '视频'}")
        self.save_dir = make_save_dir(self.output_dir, 'douyin', safe_name(info.get('author'), 20, ''),
                                      safe_name(info.get('title'), 15, ''))
        if info['is_image_set']:
            success = self.download_images(info, self.save_dir)
        elif mode == 'audio':
            success = self.download_audio(info, self.save_dir)
        else:
            success = self.download_video(info, self.save_dir)
        self.summary(success, start)
        return success

    def _print_video_info(self, info):
        stats = info.get('statistics', {})
        self._log("=" * 60)
        self._log(f"视频 ID: {info.get('video_id', 'N/A')}")
        self._log(f"标题: {info.get('title') or 'N/A'}")
        self._log(f"作者: {info.get('author') or 'N/A'} (ID: {info.get('author_id') or 'N/A'})")
        self._log(f"时长: {format_duration(info.get('duration'))}    类型: {'图集' if info.get('is_image_set') else '视频'}")
        self._log(f"播放 {stats.get('play_count')}  点赞 {stats.get('digg_count')}  "
                  f"评论 {stats.get('comment_count')}  分享 {stats.get('share_count')}")
        if info.get('is_image_set'):
            self._log(f"图片数: {len(info.get('images', []))}")
        else:
            self._log(f"视频链接: {str(info.get('video_url'))[:100]}")
        self._log(f"音乐链接: {str(info.get('music_url') or 'N/A')[:80]}")
        self._log("=" * 60)

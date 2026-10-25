# -*- coding: utf-8 -*-
"""
RouVideo (rou.video) 下载器

1. 请求视频页，从路由数据（新版 seroval 序列化，旧版 __NEXT_DATA__）取出加密数据 ev = {d, k}
2. 解密：base64 解码 → 每字节减 k → JSON，得到 videoUrl
3. 按 HLS 下载分片并合并；新版 CDN 把 m3u8 和分片包在 PNG 里，下载时先用 unwrap_png 剥掉外壳

CDN 需要 Referer: https://rou.video/，地址里的 auth 参数会过期。
"""

import base64
import json
import os
import re
import time
import zlib
from urllib.parse import urljoin, urlparse

from .common import Cancelled, SiteDownloader, format_duration, make_save_dir, safe_name
from .hls import HLSDownloader, HLSError, download_with_ffmpeg, download_with_ytdlp

ORIGIN = 'https://rou.video'
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
PAYLOAD_CHUNK = b'roUd'


def unwrap_png(data):
    """新版 CDN 把 m3u8 和分片藏在 PNG 的 roUd 块里：首字节为标志位，bit0=1 表示其余内容经 zlib 压缩"""
    if not data.startswith(PNG_SIGNATURE):
        return data
    pos = len(PNG_SIGNATURE)
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], 'big')
        ctype = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if len(body) < length:
            break
        if ctype == PAYLOAD_CHUNK and body:
            return zlib.decompress(body[1:]) if body[0] & 1 else body[1:]
        pos += 12 + length
    raise ValueError("PNG 外壳里没有找到视频数据块")


class RouVideoDownloader(SiteDownloader):

    @staticmethod
    def is_rouvideo_url(url):
        return urlparse(url).netloc.lower() in ('rou.video', 'www.rou.video')

    def _fetch_page(self, url):
        try:
            self._log(f"[*] 请求页面: {url}")
            resp = self.session.get(url, timeout=self.timeouts)
            resp.raise_for_status()
            resp.encoding = 'utf-8'
            return resp.text
        except Exception as e:
            self._log(f"[-] 请求页面失败: {e}")
            return None

    def _decrypt_ev(self, d, k):
        """等价于前端 JSON.parse(atob(d).split('').map(c => String.fromCharCode(c.charCodeAt(0) - k)).join(''))"""
        try:
            return json.loads(''.join(chr(b - int(k)) for b in base64.b64decode(d)))
        except Exception as e:
            self._log(f"[-] 解密视频数据失败: {e}")
            return None

    @staticmethod
    def _js_str(s):
        return json.loads('"' + re.sub(r'\\x([0-9a-fA-F]{2})', r'\\u00\1', s) + '"')

    def _parse_seroval(self, html):
        """新版页面（TanStack Start）把路由数据序列化成 $R[n]={video:...,ev:{d,k}} 形式的 JS"""
        start = html.find('{video:$R[')
        if start < 0:
            return {}, {}
        end = html.find('relatedVideos:', start)
        block = html[start:end if end > 0 else start + 5000]
        video = {}
        for key in ('id', 'name', 'nameZh', 'description', 'createdAt', 'coverImageUrl'):
            m = re.search(rf'[{{,]{key}:"((?:[^"\\]|\\.)*)"', block)
            if m:
                video[key] = self._js_str(m.group(1))
        for key in ('duration', 'viewCount', 'likeCount'):
            m = re.search(rf'[{{,]{key}:([\d.]+)', block)
            if m:
                video[key] = float(m.group(1)) if '.' in m.group(1) else int(m.group(1))
        m = re.search(r'[{,]tags:(?:\$R\[\d+\]=)?\[([^\]]*)\]', block)
        if m:
            video['tags'] = [self._js_str(t) for t in re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))]
        ev = {}
        m = re.search(r'[{,]ev:(?:\$R\[\d+\]=)?\{d:"([^"]+)",k:(\d+)\}', html)
        if m:
            ev = {'d': m.group(1), 'k': int(m.group(2))}
        return video, ev

    def fetch_video_info(self, url):
        html = self._fetch_page(url)
        if not html:
            return None
        m = re.search(r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if m:
            try:
                props = json.loads(m.group(1)).get('props', {}).get('pageProps', {})
            except json.JSONDecodeError as e:
                self._log(f"[-] 解析 __NEXT_DATA__ 失败: {e}")
                return None
            video, ev = props.get('video') or {}, props.get('ev') or {}
        else:
            video, ev = self._parse_seroval(html)
        if not video:
            self._log("[-] 页面里没有找到视频数据（页面结构可能又变了）")
            return None
        info = {k: video.get(k, d) for k, d in (
            ('id', ''), ('name', ''), ('nameZh', ''), ('description', ''), ('tags', []),
            ('duration', 0), ('viewCount', 0), ('likeCount', 0), ('createdAt', ''),
            ('coverImageUrl', ''), ('sources', []))}
        info.update(page_url=url, videoUrl=None, thumbVTTUrl=None)
        if 'd' in ev and 'k' in ev:
            decrypted = self._decrypt_ev(ev['d'], ev['k'])
            if decrypted:
                for key in ('videoUrl', 'thumbVTTUrl'):
                    if decrypted.get(key):
                        info[key] = urljoin(ORIGIN + '/', decrypted[key])
        return info

    def run(self, url, mode='video'):
        """mode: 'video' / 'info'"""
        self._log("=" * 60)
        self._log(f"RouVideo 下载器 - {mode} 模式    地址: {url}")
        self._log("=" * 60)
        start = time.time()

        info = self.fetch_video_info(url)
        if not info:
            self._log("[-] 无法获取视频信息")
            return False
        self.info = info
        if mode == 'info':
            self._print_video_info(info)
            return True
        video_url = info.get('videoUrl')
        if not video_url:
            self._log("[-] 无法获取视频地址。可能原因：页面加密方式变更、需要登录、视频已删除")
            return False

        raw_title = info.get('nameZh') or info.get('name') or '未命名'
        title = safe_name(raw_title, 60, '未命名')
        self._log(f"[+] 标题: {title}    时长: {format_duration(info.get('duration'))}")
        self.save_dir = make_save_dir(self.output_dir, 'rouvideo', safe_name(raw_title, 20, ''))
        out_base = os.path.join(self.save_dir, title)
        headers = {'Referer': ORIGIN + '/', 'Origin': ORIGIN, 'User-Agent': self.USER_AGENT}

        success = False
        try:
            hls = HLSDownloader(self.session, self.reporter, headers, self.threads, self.timeout, unwrap=unwrap_png)
            try:
                self.record_saved(hls.download(video_url, out_base, os.path.join(self.output_dir, '.hls_cache')))
                success = True
            except HLSError as e:
                self._log(f"[-] 自有下载器失败: {e}")
            if not success:
                path = download_with_ytdlp(video_url, out_base + '.%(ext)s', headers, self.reporter, self.proxy)
                if path:
                    self.record_saved(path)
                    success = True
            if not success and download_with_ffmpeg(video_url, out_base + '.mp4', headers, self.reporter):
                self.record_saved(out_base + '.mp4')
                success = True
        except Cancelled:
            self._log("[!] 已取消")
            return False

        if not success:
            self.failed_count += 1
        self.summary(success, start)
        return success

    def _print_video_info(self, info):
        self._log("=" * 60)
        self._log(f"标题: {info.get('name') or 'N/A'}")
        self._log(f"中文标题: {info.get('nameZh') or 'N/A'}")
        self._log(f"视频 ID: {info.get('id') or 'N/A'}    时长: {format_duration(info.get('duration'))}")
        self._log(f"播放量: {info.get('viewCount')}    点赞数: {info.get('likeCount')}")
        self._log(f"标签: {', '.join(info.get('tags') or [])}    创建时间: {info.get('createdAt') or 'N/A'}")
        self._log(f"视频地址: {(info.get('videoUrl') or '未获取到（可能需要登录）')[:100]}")
        if info.get('sources'):
            self._log(f"可用分辨率: {[s.get('resolution', '?') for s in info['sources']]}")
        self._log("=" * 60)

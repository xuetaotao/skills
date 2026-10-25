# -*- coding: utf-8 -*-
"""
MacCMS (苹果CMS) 视频站解析器
从播放页的 player_aaaa 变量取出视频地址（m3u8 / mp4）并下载

常见 URL:
- /index.php/vod/play/id/{id}/sid/{sid}/nid/{nid}.html
- /vodplay/{id}-{sid}-{nid}.html、/play/{id}-{sid}-{nid}.html（伪静态）
- 详情页 /vod/detail/id/{id}.html、/voddetail/{id}.html 会自动跳到第一集

player_aaaa.encrypt:
- 0: 明文
- 1: URL 编码
- 2: Base64 + 双层 URL 编码
"""

import base64
import json
import os
import re
import time
from urllib.parse import unquote, urljoin, urlparse

from .common import Cancelled, SiteDownloader, make_save_dir, safe_name
from .hls import HLSDownloader, HLSError, download_with_ffmpeg, download_with_ytdlp

PLAY_PATTERNS = (r'/vod/play/', r'/vodplay/', r'/play/\d+-\d+-\d+\.html', r'/play/id/\d+')
DETAIL_PATTERNS = (r'/vod/detail/', r'/voddetail/', r'/detail/\d+\.html', r'/detail/id/\d+')


class MacCMSDownloader(SiteDownloader):

    @staticmethod
    def is_maccms_url(url):
        path = urlparse(url).path.lower()
        return any(re.search(p, path) for p in PLAY_PATTERNS + DETAIL_PATTERNS)

    @staticmethod
    def looks_like_maccms(html):
        return bool(html) and 'player_aaaa' in html

    def _fetch_page(self, url):
        try:
            self._log(f"[*] 请求页面: {url}")
            resp = self.session.get(url, timeout=self.timeouts)
            resp.raise_for_status()
            if 'charset' not in resp.headers.get('content-type', '').lower():
                resp.encoding = resp.apparent_encoding or 'utf-8'
            return resp.text
        except Exception as e:
            self._log(f"[-] 请求页面失败: {e}")
            return None

    def _extract_player_data(self, html):
        m = (re.search(r'var\s+player_aaaa\s*=\s*(\{.*?\})\s*;?\s*</script>', html, re.DOTALL)
             or re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*;?\s*\n', html, re.DOTALL))
        if not m:
            return None
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError as e:
            self._log(f"[-] 解析 player_aaaa 失败: {e}")
            return None

    def _first_play_link(self, html, page_url):
        for href in re.findall(r'href=["\']([^"\']+)["\']', html):
            path = urlparse(urljoin(page_url, href)).path.lower()
            if any(re.search(p, path) for p in PLAY_PATTERNS):
                return urljoin(page_url, href)
        return None

    def _decrypt_url(self, url, encrypt):
        try:
            encrypt = int(encrypt)
        except (TypeError, ValueError):
            encrypt = -1
        if encrypt == 0:
            return url
        if encrypt == 1:
            return unquote(url)
        if encrypt == 2:
            try:
                return unquote(unquote(base64.b64decode(unquote(unquote(url))).decode('utf-8')))
            except Exception:
                pass
        for attempt in (lambda u: unquote(u),
                        lambda u: unquote(unquote(u)),
                        lambda u: unquote(base64.b64decode(u).decode('utf-8')),
                        lambda u: unquote(unquote(base64.b64decode(u).decode('utf-8')))):
            try:
                result = attempt(url)
                if result.startswith('http'):
                    return result
            except Exception:
                continue
        self._log(f"[!] 无法解密视频地址 (encrypt={encrypt})")
        return url

    def fetch_video_info(self, url, html=None):
        html = html or self._fetch_page(url)
        if not html:
            return None
        player = self._extract_player_data(html)
        if not player:
            play_url = self._first_play_link(html, url)
            if play_url and play_url != url:
                self._log(f"[*] 这是详情页，转到第一集播放页: {play_url}")
                return self.fetch_video_info(play_url)
            self._log("[-] 未找到 player_aaaa 变量")
            return None

        vod = player.get('vod_data') or {}
        info = {
            'title': vod.get('vod_name', ''),
            'from': player.get('from', ''),
            'vod_id': player.get('id', ''),
            'video_url': self._decrypt_url(player.get('url', ''), player.get('encrypt', 0)) if player.get('url') else '',
            'cover': '',
            'page_url': url,
            'player_data': player,
        }
        m = re.search(r'MacPlayer\.Pic\s*=\s*["\']([^"\']+)["\']', html)
        if m:
            info['cover'] = m.group(1)
        if not info['title']:
            m = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
            if m:
                info['title'] = re.split(r'[-_|]', m.group(1))[0].strip()
        nid = player.get('nid')
        if nid and str(nid) != '1':
            info['title'] = f"{info['title']} 第{nid}集"
        return info

    def run(self, url, mode='video', html=None):
        """mode: 'video' / 'info'（MacCMS 没有单独的音频）"""
        self._log("=" * 60)
        self._log(f"MacCMS 视频站解析 - {mode} 模式    地址: {url}")
        self._log("=" * 60)
        start = time.time()

        info = self.fetch_video_info(url, html)
        if not info:
            self._log("[-] 无法获取视频信息（可能不是 MacCMS 站点，或页面结构已变更）")
            return False
        self.info = info
        if mode == 'info':
            self._print_video_info(info)
            return True
        video_url = info['video_url']
        if not video_url.startswith('http'):
            self._log(f"[-] 未得到可下载的视频地址: {video_url[:100]}")
            self._log("[!] 该播放源可能需要站点自带的解析接口，暂不支持")
            return False

        title = safe_name(info['title'], 60, '未命名')
        self._log(f"[+] 标题: {title}    播放源: {info.get('from') or 'N/A'}")
        self._log(f"[+] 视频地址: {video_url}")
        self.save_dir = make_save_dir(self.output_dir, 'maccms', safe_name(info['title'], 20, ''))
        p = urlparse(info['page_url'])
        # Referer 必须带末尾斜杠，否则部分站点的 CDN 返回 403
        headers = {'Referer': f"{p.scheme}://{p.netloc}/", 'User-Agent': self.USER_AGENT}
        out_base = os.path.join(self.save_dir, title)

        success = False
        try:
            if '.m3u8' in video_url.lower():
                success = self._download_hls(video_url, out_base, headers)
            else:
                try:
                    self._log(f"[*] 直接下载: {title}.mp4")
                    self.stream_download(video_url, out_base + '.mp4', headers)
                    self.record_saved(out_base + '.mp4')
                    success = True
                except Cancelled:
                    raise
                except Exception as e:
                    self._log(f"[-] 直接下载失败: {e}")
                if not success:
                    path = download_with_ytdlp(video_url, out_base + '.%(ext)s', headers, self.reporter, self.proxy)
                    if path:
                        self.record_saved(path)
                        success = True
        except Cancelled:
            self._log("[!] 已取消")
            return False

        if not success:
            self.failed_count += 1
        self.summary(success, start)
        return success

    def _download_hls(self, m3u8_url, out_base, headers):
        """自有 HLS 下载器（共用 session cookie，可绕过 Cloudflare）→ yt-dlp → ffmpeg"""
        hls = HLSDownloader(self.session, self.reporter, headers, self.threads, self.timeout)
        try:
            path = hls.download(m3u8_url, out_base, os.path.join(self.output_dir, '.hls_cache'))
            self.record_saved(path)
            return True
        except HLSError as e:
            self._log(f"[-] 自有下载器失败: {e}")
        except Cancelled:
            raise
        except Exception as e:
            self._log(f"[-] 自有下载器出错: {e}")
        cookie = '; '.join(f'{c.name}={c.value}' for c in self.session.cookies)
        if cookie:
            headers = {**headers, 'Cookie': cookie}
        path = download_with_ytdlp(m3u8_url, out_base + '.%(ext)s', headers, self.reporter, self.proxy)
        if path:
            self.record_saved(path)
            return True
        if download_with_ffmpeg(m3u8_url, out_base + '.mp4', headers, self.reporter):
            self.record_saved(out_base + '.mp4')
            return True
        return False

    def _print_video_info(self, info):
        pd = info.get('player_data') or {}
        self._log("=" * 60)
        self._log(f"标题: {info.get('title') or 'N/A'}")
        self._log(f"视频 ID: {info.get('vod_id') or 'N/A'}    播放源: {info.get('from') or 'N/A'}")
        self._log(f"视频地址: {info.get('video_url') or 'N/A'}")
        self._log(f"封面: {info.get('cover') or 'N/A'}")
        self._log(f"页面: {info.get('page_url')}")
        self._log(f"加密级别: {pd.get('encrypt', 'N/A')}    原始 URL: {str(pd.get('url', ''))[:80]}")
        self._log("=" * 60)

# -*- coding: utf-8 -*-
"""
HLS (m3u8) 下载
- 主播放列表自动选最高码率
- AES-128 解密、fMP4 初始化分片 (#EXT-X-MAP)
- 分片并发下载 + 重试，分片缓存在 {输出根目录}/.hls_cache/ 下，失败后重跑可续传
- 有 ffmpeg 时转封装为 mp4，否则保存为 .ts
另含 yt-dlp / ffmpeg 两种兜底下载方式。
"""

import hashlib
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

from .common import Cancelled, format_size, has_ffmpeg
from .config import HLS_RETRIES, THREADS, TIMEOUT


class HLSError(Exception):
    pass


def _aes_cbc_decrypt(data, key, iv):
    try:
        from Cryptodome.Cipher import AES
        out = AES.new(key, AES.MODE_CBC, iv).decrypt(data)
    except ImportError:
        from yt_dlp.aes import aes_cbc_decrypt_bytes
        out = aes_cbc_decrypt_bytes(data, key, iv)
    pad = out[-1] if out else 0
    if 1 <= pad <= 16 and out.endswith(bytes([pad]) * pad):
        out = out[:-pad]
    return out


def _attrs(line):
    """解析 #EXT-X-KEY:METHOD=AES-128,URI="..." 这类属性列表"""
    return {k.upper(): v.strip('"') for k, v in re.findall(r'([A-Za-z0-9-]+)=("[^"]*"|[^,]*)', line.split(':', 1)[1])}


class HLSDownloader:
    def __init__(self, session, reporter, headers=None, threads=THREADS, timeout=TIMEOUT, retries=HLS_RETRIES,
                 unwrap=None):
        """unwrap: 可选，bytes -> bytes，用于剥掉站点给播放列表/分片套的伪装外壳"""
        self.session = session
        self.reporter = reporter
        self.headers = headers or {}
        self.threads = max(1, threads)
        self.timeout = timeout
        self.retries = retries
        self.unwrap = unwrap or (lambda data: data)
        self._keys = {}

    @property
    def _log(self):
        return self.reporter.log

    def _get(self, url):
        resp = self.session.get(url, headers=self.headers, timeout=(min(self.timeout, 15), self.timeout))
        resp.raise_for_status()
        return resp

    def _media_playlist(self, url, depth=0):
        """返回 (媒体播放列表 URL, 文本)，遇到主播放列表时选最高码率"""
        resp = self._get(url)
        url = resp.url or url
        text = self.unwrap(resp.content).decode('utf-8', errors='replace')
        if '#EXTM3U' not in text:
            raise HLSError("返回内容不是 m3u8 播放列表")
        if '#EXT-X-STREAM-INF' not in text:
            return url, text
        if depth >= 3:
            raise HLSError("主播放列表嵌套过深")
        variants, pending = [], None
        for line in text.splitlines():
            line = line.strip()
            if line.startswith('#EXT-X-STREAM-INF'):
                pending = _attrs(line)
            elif line and not line.startswith('#') and pending is not None:
                res = re.match(r'(\d+)x(\d+)', pending.get('RESOLUTION', ''))
                height = int(res.group(2)) if res else 0
                variants.append((int(pending.get('BANDWIDTH', 0) or 0), height, urljoin(url, line)))
                pending = None
        if not variants:
            raise HLSError("主播放列表里没有可用的码率")
        bandwidth, height, best = max(variants)
        desc = f"{height}p, " if height else ''
        self._log(f"[*] 共 {len(variants)} 路码率，选择 {desc}{bandwidth // 1000} kbps")
        return self._media_playlist(best, depth + 1)

    def parse(self, m3u8_url):
        """解析为 (初始化分片 URL 或 None, [(序号, 分片 URL, key 信息 或 None)])"""
        url, text = self._media_playlist(m3u8_url)
        sequence, key, init_url, segments = 0, None, None, []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith('#EXT-X-MEDIA-SEQUENCE'):
                sequence = int(line.split(':', 1)[1] or 0)
            elif line.startswith('#EXT-X-KEY'):
                a = _attrs(line)
                method = a.get('METHOD', 'NONE').upper()
                if method == 'NONE':
                    key = None
                elif method == 'AES-128':
                    key = {'uri': urljoin(url, a['URI']), 'iv': a.get('IV')}
                else:
                    raise HLSError(f"暂不支持的加密方式: {method}")
            elif line.startswith('#EXT-X-MAP'):
                init_url = urljoin(url, _attrs(line)['URI'])
            elif line.startswith('#EXT-X-BYTERANGE'):
                raise HLSError("暂不支持 BYTERANGE 分片")
            elif not line.startswith('#'):
                segments.append((sequence + len(segments), urljoin(url, line), key))
        if not segments:
            raise HLSError("m3u8 里没有分片")
        return init_url, segments

    def _key_bytes(self, uri):
        if uri not in self._keys:
            data = self._get(uri).content
            if len(data) != 16:
                raise HLSError(f"AES 密钥长度异常（{len(data)} 字节）")
            self._keys[uri] = data
        return self._keys[uri]

    def _fetch_segment(self, url, key, seq, path):
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return os.path.getsize(path)
        last_err = None
        for attempt in range(self.retries):
            self.reporter.check_cancel()
            try:
                data = self.unwrap(self._get(url).content)
                if key:
                    iv = bytes.fromhex(key['iv'][2:].zfill(32)) if key.get('iv') else seq.to_bytes(16, 'big')
                    data = _aes_cbc_decrypt(data, self._key_bytes(key['uri']), iv)
                tmp = path + '.tmp'
                with open(tmp, 'wb') as f:
                    f.write(data)
                os.replace(tmp, path)
                return len(data)
            except Cancelled:
                raise
            except Exception as e:
                last_err = e
                time.sleep(min(2 ** attempt, 8))
        raise HLSError(f"分片 {seq} 下载失败: {last_err}")

    def download(self, m3u8_url, out_base, cache_root):
        """
        下载并合并，返回最终文件路径（out_base + .mp4 或 .ts）。
        cache_root 下按 m3u8 路径（忽略会过期的查询参数）建分片缓存目录。
        """
        self._log("[*] 解析 m3u8 播放列表…")
        init_url, segments = self.parse(m3u8_url)
        encrypted = any(k for _, _, k in segments)
        self._log(f"[+] 共 {len(segments)} 个分片" + ("（AES-128 加密）" if encrypted else ''))

        p = urlparse(m3u8_url)
        cache = os.path.join(cache_root, hashlib.md5(f"{p.netloc}{p.path}".encode()).hexdigest()[:16])
        os.makedirs(cache, exist_ok=True)
        cached = sum(1 for i in range(len(segments)) if os.path.exists(os.path.join(cache, f'{i:05d}.seg')))
        if cached:
            self._log(f"[*] 发现 {cached} 个已缓存的分片，继续下载剩余部分")

        init_path = None
        if init_url:
            init_path = os.path.join(cache, 'init.mp4')
            self._fetch_segment(init_url, None, 0, init_path)

        done, total_bytes, failures = 0, 0, []
        pool = ThreadPoolExecutor(max_workers=self.threads)
        try:
            futures = {pool.submit(self._fetch_segment, url, key, seq, os.path.join(cache, f'{i:05d}.seg')): i
                       for i, (seq, url, key) in enumerate(segments)}
            for fut in as_completed(futures):
                try:
                    total_bytes += fut.result()
                except Cancelled:
                    raise
                except Exception as e:
                    failures.append(str(e))
                done += 1
                self.reporter.progress(done, len(segments),
                                       f"分片 {done}/{len(segments)}  {format_size(total_bytes)}")
        except Cancelled:
            pool.shutdown(wait=True, cancel_futures=True)
            self.reporter.end_progress()
            self._log(f"[!] 已取消，已下载的分片保存在 {cache}，重新下载同一视频会继续")
            raise
        pool.shutdown(wait=True)
        self.reporter.end_progress()
        if failures:
            self._log(f"[-] {failures[0]}")
            raise HLSError(f"{len(failures)}/{len(segments)} 个分片下载失败，"
                           f"已下载的分片保留在缓存中，重新运行会继续")

        merged = out_base + ('.mp4' if init_path else '.ts')
        self._log(f"[*] 合并 {len(segments)} 个分片…")
        with open(merged, 'wb') as out:
            for path in ([init_path] if init_path else []) + [os.path.join(cache, f'{i:05d}.seg') for i in range(len(segments))]:
                with open(path, 'rb') as f:
                    shutil.copyfileobj(f, out, 1024 * 1024)
        shutil.rmtree(cache, ignore_errors=True)

        if merged.endswith('.ts'):
            if has_ffmpeg():
                mp4 = out_base + '.mp4'
                if remux_to_mp4(merged, mp4, self._log):
                    os.remove(merged)
                    merged = mp4
            else:
                self._log("[!] 未安装 ffmpeg，保存为 .ts（主流播放器可直接播放）")
        self._log(f"[+] 已保存: {os.path.basename(merged)} ({format_size(os.path.getsize(merged))})")
        return merged


def remux_to_mp4(src, dst, log):
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-i', src, '-c', 'copy', '-bsf:a', 'aac_adtstoasc',
           '-movflags', '+faststart', dst]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode != 0:
        log(f"[!] 转封装 mp4 失败，保留 .ts: {result.stderr.strip()[:200]}")
        if os.path.exists(dst):
            os.remove(dst)
        return False
    return True


def download_with_ffmpeg(url, out_path, headers, reporter):
    """用 ffmpeg 直接拉流保存，可取消，不设总时长上限"""
    if not has_ffmpeg():
        reporter.log("[-] 未安装 ffmpeg")
        return False
    header_lines = ''.join(f"{k}: {v}\r\n" for k, v in headers.items() if k.lower() != 'user-agent')
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-stats']
    if headers.get('User-Agent'):
        cmd += ['-user_agent', headers['User-Agent']]
    if header_lines:
        cmd += ['-headers', header_lines]
    cmd += ['-i', url, '-c', 'copy', '-bsf:a', 'aac_adtstoasc', out_path]
    reporter.log("[*] 使用 ffmpeg 下载…")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            text=True, encoding='utf-8', errors='replace')
    tail = []
    try:
        for line in iter(proc.stderr.readline, ''):
            if reporter.cancel_event.is_set():
                proc.kill()
                raise Cancelled()
            line = line.strip()
            if line.startswith('frame=') or 'time=' in line:
                m = re.search(r'size=\s*(\S+).*?time=(\S+)', line)
                if m:
                    reporter.progress(0, 0, f"ffmpeg 已下载 {m.group(1)}，进度 {m.group(2)}", force=True)
            elif line:
                tail = (tail + [line])[-5:]
        proc.wait()
    finally:
        reporter.end_progress()
        if proc.poll() is None:
            proc.kill()
    if proc.returncode == 0 and os.path.exists(out_path):
        reporter.log(f"[+] 已保存: {os.path.basename(out_path)} ({format_size(os.path.getsize(out_path))})")
        return True
    reporter.log(f"[-] ffmpeg 失败: {' | '.join(tail)[:300]}")
    if os.path.exists(out_path):
        os.remove(out_path)
    return False


def download_with_ytdlp(url, out_template, headers, reporter, proxy=None):
    """用 yt-dlp 的通用下载器（m3u8 / 直链）"""
    try:
        import yt_dlp
        from yt_dlp.utils import DownloadCancelled
    except ImportError:
        reporter.log("[-] 未安装 yt-dlp")
        return None

    saved = []

    class SilentLogger:
        def debug(self, msg):
            pass

        warning = error = info = debug

    def hook(d):
        if reporter.cancel_event.is_set():
            raise DownloadCancelled()
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            done = d.get('downloaded_bytes') or 0
            reporter.progress(done, total, f"yt-dlp {format_size(done)} / {format_size(total)}")

    opts = {
        'outtmpl': out_template,
        'quiet': True,
        'no_warnings': True,
        'noprogress': True,
        'logger': SilentLogger(),
        'nocheckcertificate': True,
        'http_headers': headers,
        'progress_hooks': [hook],
        'post_hooks': [saved.append],
        'concurrent_fragment_downloads': 8,
    }
    if proxy:
        opts['proxy'] = proxy
    reporter.log("[*] 使用 yt-dlp 下载…")
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except DownloadCancelled:
        raise Cancelled()
    except Exception as e:
        reporter.log(f"[-] yt-dlp 失败: {str(e)[:300]}")
        return None
    finally:
        reporter.end_progress()
    return saved[-1] if saved else None

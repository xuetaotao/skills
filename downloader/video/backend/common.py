# -*- coding: utf-8 -*-
"""
各下载器共用的工具：网络会话、Cookie、文件名、日志 / 进度 / 取消、直链下载
"""

import os
import re
import shutil
import sys
import threading
import time
from datetime import datetime
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import MOBILE_UA, OUTPUT_DIR, PC_UA, THREADS, TIMEOUT  # noqa: F401  MOBILE_UA 供站点下载器导入


class Cancelled(Exception):
    """用户取消了下载"""


def has_ffmpeg():
    return shutil.which('ffmpeg') is not None


def format_duration(seconds):
    if not seconds:
        return "N/A"
    seconds = int(seconds)
    h, m, s = seconds // 3600, seconds % 3600 // 60, seconds % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def format_size(n):
    if not n:
        return "0 B"
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f"{n:.0f} {unit}" if unit in ('B', 'KB') else f"{n:.1f} {unit}"
        n /= 1024


_RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}


def safe_name(text, max_len=80, default='video'):
    """转成 Windows 可用的文件名，保留中文"""
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '', str(text or ''))
    text = re.sub(r'\s+', ' ', text).strip()[:max_len].rstrip(' .')
    if not text or text.upper() in _RESERVED:
        return default
    return text


def unique_dir(path):
    candidate, n = path, 2
    while True:
        try:
            os.makedirs(candidate)
            return candidate
        except FileExistsError:
            candidate, n = f"{path}_{n}", n + 1


def make_save_dir(base_dir, *parts):
    """在 base_dir 下创建 {部分1}-{部分2}-…-{时间} 子目录"""
    names = [p for p in parts if p] + [datetime.now().strftime('%Y%m%d_%H%M%S')]
    return unique_dir(os.path.join(base_dir, '-'.join(names)))


def url_domain(url):
    domain = urlparse(url).netloc.lower().replace(':', '_')
    return domain[4:] if domain.startswith('www.') else domain


# ---------------------------------------------------------------- Cookie

def parse_netscape_cookies(text):
    """解析 Netscape cookies.txt（浏览器扩展 Get cookies.txt 导出的格式）"""
    cookies = []
    for line in text.splitlines():
        if line.startswith('#HttpOnly_'):
            line = line[len('#HttpOnly_'):]
        elif not line.strip() or line.startswith('#'):
            continue
        fields = line.rstrip('\r\n').split('\t')
        if len(fields) == 7:
            domain, _, path, secure, _, name, value = fields
            cookies.append({'domain': domain, 'path': path or '/', 'secure': secure.upper() == 'TRUE',
                            'name': name, 'value': value})
    return cookies


def is_netscape_cookie_file(path):
    try:
        with open(path, encoding='utf-8', errors='ignore') as f:
            return bool(parse_netscape_cookies(f.read()))
    except OSError:
        return False


def load_cookies(session, cookie, log=print):
    """
    cookie 可以是：Netscape cookies.txt 文件、内容为 "a=1; b=2" 的文本文件，或直接是 "a=1; b=2" 字符串
    """
    text = cookie
    if os.path.isfile(cookie):
        try:
            with open(cookie, encoding='utf-8', errors='ignore') as f:
                text = f.read()
        except OSError as e:
            log(f"[-] 读取 Cookie 文件失败: {e}")
            return
        parsed = parse_netscape_cookies(text)
        if parsed:
            for c in parsed:
                session.cookies.set(c['name'], c['value'], domain=c['domain'], path=c['path'],
                                    secure=c['secure'])
            log(f"[+] 已从 cookies.txt 加载 {len(parsed)} 个 Cookie")
            return
    text = text.strip()
    if text.lower().startswith('cookie:'):
        text = text[7:].strip()
    if text:
        session.headers['Cookie'] = text


def make_session(user_agent=PC_UA, proxy=None, cookie=None, log=print, pool_size=16):
    session = requests.Session()
    # 不理会 Retry-After：Cloudflare 502 常要求等 60 秒
    retry = Retry(total=3, backoff_factor=0.6, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=('GET', 'HEAD'), raise_on_status=False,
                  respect_retry_after_header=False)
    adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=pool_size)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.headers.update({
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    })
    if proxy:
        session.proxies = {'http': proxy, 'https': proxy}
    if cookie:
        load_cookies(session, cookie, log)
    return session


# ---------------------------------------------------------------- 日志 / 进度 / 取消

class Reporter:
    """
    log(str) 输出日志；progress(fraction 或 None, text) 报告进度。
    没有 progress 回调时（命令行），进度在终端同一行刷新。
    """

    def __init__(self, log=None, progress=None, cancel_event=None):
        self.log = log or print
        self._progress_cb = progress
        self.cancel_event = cancel_event or threading.Event()
        self._last_emit = 0.0
        self._line_open = False

    def check_cancel(self):
        if self.cancel_event.is_set():
            raise Cancelled()

    def progress(self, done, total, text='', force=False):
        now = time.monotonic()
        finished = bool(total) and done >= total
        if not (force or finished) and now - self._last_emit < 0.25:
            return
        self._last_emit = now
        fraction = min(done / total, 1.0) if total else None
        if self._progress_cb:
            self._progress_cb(fraction, text)
            return
        pct = f"{fraction * 100:5.1f}% " if fraction is not None else ''
        sys.stdout.write(f"\r    {pct}{text}".ljust(78)[:120])
        sys.stdout.flush()
        self._line_open = True
        if finished:
            self.end_progress()

    def end_progress(self):
        if self._line_open:
            sys.stdout.write('\n')
            sys.stdout.flush()
            self._line_open = False


class SiteDownloader:
    """站点专用下载器的基类"""

    USER_AGENT = PC_UA

    def __init__(self, output_dir=OUTPUT_DIR, proxy=None, cookie=None, timeout=TIMEOUT,
                 progress_callback=None, progress=None, cancel_event=None, threads=THREADS):
        """
        Args:
            output_dir: 输出根目录，每次下载在其下新建子目录
            proxy: 代理地址
            cookie: Cookie 文件路径或 "a=1; b=2" 字符串
            timeout: 请求超时（秒）
            progress_callback: 日志回调 log(str)，默认 print
            progress: 进度回调 progress(fraction 或 None, text)
            cancel_event: threading.Event，set() 后尽快停止
            threads: m3u8 分片并发数
        """
        self.output_dir = output_dir
        self.proxy = proxy
        self.cookie = cookie
        self.timeout = timeout
        self.threads = threads
        self.reporter = Reporter(progress_callback, progress, cancel_event)
        self._log = self.reporter.log
        self.session = make_session(self.USER_AGENT, proxy, cookie, self._log)
        self.downloaded_count = 0
        self.failed_count = 0
        self.save_dir = None
        self.saved_files = []

    @property
    def timeouts(self):
        return (min(self.timeout, 15), self.timeout)

    def stream_download(self, url, path, headers=None, min_bytes=10 * 1024, accept=None):
        """
        流式下载到 path（先写 .part，支持断点续传），返回文件大小。
        accept: 允许的 Content-Type 关键字，如 ('video', 'octet-stream')
        """
        part = path + '.part'
        headers = dict(headers or {})
        offset = os.path.getsize(part) if os.path.exists(part) else 0
        if offset:
            headers['Range'] = f'bytes={offset}-'
        with self.session.get(url, headers=headers, timeout=self.timeouts, stream=True) as resp:
            if resp.status_code == 416:
                offset = 0
                os.remove(part)
                return self.stream_download(url, path, headers={k: v for k, v in headers.items() if k != 'Range'},
                                            min_bytes=min_bytes, accept=accept)
            resp.raise_for_status()
            ctype = resp.headers.get('content-type', '').lower()
            if accept and ctype and not any(a in ctype for a in accept):
                raise ValueError(f"返回内容类型异常: {ctype}")
            if resp.status_code != 206:
                offset = 0
            total = int(resp.headers.get('content-length') or 0) + offset
            done = offset
            label = os.path.basename(path)
            with open(part, 'ab' if offset else 'wb') as f:
                for chunk in resp.iter_content(chunk_size=256 * 1024):
                    self.reporter.check_cancel()
                    if chunk:
                        f.write(chunk)
                        done += len(chunk)
                        self.reporter.progress(done, total, f"{format_size(done)} / {format_size(total)}  {label}")
        self.reporter.end_progress()
        if done < min_bytes:
            os.remove(part)
            raise ValueError(f"下载的文件过小（{format_size(done)}），可能失败")
        os.replace(part, path)
        return done

    def record_saved(self, path):
        self.downloaded_count += 1
        self.saved_files.append(path)

    def remove_empty_save_dir(self):
        if self.save_dir and os.path.isdir(self.save_dir) and not os.listdir(self.save_dir):
            os.rmdir(self.save_dir)
            self.save_dir = None

    def summary(self, success, start_time):
        self.remove_empty_save_dir()
        self._log("\n" + "=" * 60)
        self._log("下载完成!" if success else "下载失败!")
        self._log(f"成功: {self.downloaded_count}    失败: {self.failed_count}    "
                  f"耗时: {time.time() - start_time:.1f} 秒")
        if self.save_dir:
            self._log(f"保存位置: {os.path.abspath(self.save_dir)}")
        self._log("=" * 60)

# -*- coding: utf-8 -*-
"""
网页图片下载核心
从网页（可自动翻页）收集正文图片，并发下载到 output_dir/{域名}-{标题}-{时间}/
"""

import hashlib
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import (CONTENT_AREA_KEYWORDS, EXCLUDED_AREA_KEYWORDS, ICON_KEYWORDS, IMAGE_EXTS, LAZY_ATTRS,
                     NUM_THREADS, RETRIES, TIMEOUT, USER_AGENT)


def _keyword_pattern(keywords):
    """关键词只在 class/id 的词首或 -/_ 之后匹配，避免 'ad-' 命中 'thread-' 这类误判"""
    return re.compile(r'(?<![a-z0-9])(?:' + '|'.join(map(re.escape, keywords)) + ')')


ICON_PATTERN = _keyword_pattern(ICON_KEYWORDS)
EXCLUDED_AREA_PATTERN = _keyword_pattern(EXCLUDED_AREA_KEYWORDS)
CONTENT_AREA_PATTERN = _keyword_pattern(CONTENT_AREA_KEYWORDS)


def sniff_image_ext(data):
    """按文件头判断图片格式，不是图片返回 None"""
    if data[:3] == b'\xff\xd8\xff':
        return 'jpg'
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp'
    if data[:2] == b'BM':
        return 'bmp'
    if data[4:8] == b'ftyp':
        brand = data[8:12]
        if brand in (b'avif', b'avis'):
            return 'avif'
        if brand in (b'heic', b'heix', b'mif1', b'msf1'):
            return 'heic'
    if data[:4] in (b'II*\x00', b'MM\x00*'):
        return 'tif'
    return None


def _class_id_text(tag):
    cls = tag.get('class', [])
    cls_str = ' '.join(cls) if isinstance(cls, list) else str(cls)
    return f"{cls_str} {tag.get('id', '')}".lower()


class Cancelled(Exception):
    pass


class WebpageImageDownloader:
    def __init__(self, url, output_dir, num_threads=NUM_THREADS, timeout=TIMEOUT, use_sequential_naming=True,
                 auto_pagination=True, max_pages=None, min_image_size_kb=0, dedupe=True,
                 log=None, progress=None):
        """
        Args:
            url: 网页地址
            output_dir: 输出根目录，图片保存到 output_dir/{子目录名}/
            num_threads: 并发下载线程数
            timeout: 单个请求的超时（秒）
            use_sequential_naming: True 命名为 001.jpg；False 为 001_原文件名.jpg
            auto_pagination: 是否自动翻页
            max_pages: 最多处理的页数，None 不限制
            min_image_size_kb: 小于该大小的图片跳过，0 不过滤
            dedupe: 内容完全相同的图片只保留一张
            log: 日志回调 log(str)，默认 print
            progress: 下载进度回调 progress(done, total)
        """
        self.url = url
        self.output_base_dir = output_dir
        self.output_dir = None
        self.num_threads = max(1, int(num_threads))
        self.timeout = timeout
        self.use_sequential_naming = use_sequential_naming
        self.auto_pagination = auto_pagination
        self.max_pages = max_pages
        self.min_image_size_kb = min_image_size_kb
        self.dedupe = dedupe
        self.log = log or print
        self.progress = progress

        self.stop_event = threading.Event()
        self.stats = {'ok': 0, 'failed': 0, 'small': 0, 'duplicate': 0}
        self.page_count = 0
        self._hashes = set()
        self._lock = threading.Lock()
        self.session = self._make_session()

    @property
    def downloaded_count(self):
        return self.stats['ok']

    @property
    def failed_count(self):
        return self.stats['failed']

    def cancel(self):
        self.stop_event.set()

    def _check_cancel(self):
        if self.stop_event.is_set():
            raise Cancelled()

    def _make_session(self):
        session = requests.Session()
        # 不理会 Retry-After：Cloudflare 502 会要求等 60 秒，3 次重试就是 3 分钟
        retry = Retry(total=RETRIES, backoff_factor=0.6, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=('GET', 'HEAD'), raise_on_status=False,
                      respect_retry_after_header=False)
        adapter = HTTPAdapter(max_retries=retry, pool_connections=4,
                              pool_maxsize=max(10, self.num_threads))
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        return session

    @property
    def _timeouts(self):
        return (min(self.timeout, 10), self.timeout)

    # ------------------------------------------------------------------ 页面

    @staticmethod
    def generate_subdir_name(url, soup=None):
        """{域名}-{标题前20字}-{时间}，如 github.com-BeautifulSoup文档-20260411_220700"""
        domain = urlparse(url).netloc.replace(':', '_')
        if domain.startswith('www.'):
            domain = domain[4:]
        title_part = ''
        if soup is not None and soup.title:
            cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]', '', soup.title.get_text(strip=True))
            cleaned = re.sub(r'\s+', '_', cleaned)
            title_part = cleaned[:20].strip('_. ')
        time_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        return '-'.join(p for p in (domain, title_part, time_str) if p)

    def fetch_page(self, url, referer=None):
        """返回 (最终 URL, BeautifulSoup)，失败返回 (None, None)"""
        self.log(f"[*] 正在获取网页: {url}")
        headers = {'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8'}
        if referer:
            headers['Referer'] = referer
        try:
            resp = self.session.get(url, timeout=self._timeouts, headers=headers)
            resp.raise_for_status()
        except Exception as e:
            self.log(f"[-] 获取网页失败: {e}")
            return None, None
        # 响应头没写 charset 时交给 BeautifulSoup 按 <meta charset> 判断，避免中文标题乱码
        has_charset = 'charset' in resp.headers.get('content-type', '').lower()
        soup = BeautifulSoup(resp.content, 'html.parser',
                             from_encoding=resp.encoding if has_charset else None)
        self.log(f"[+] 网页获取成功，大小: {len(resp.content) // 1024} KB")
        return resp.url, soup

    @staticmethod
    def _best_from_srcset(srcset):
        best_url, best_score = None, -1.0
        for part in srcset.split(','):
            bits = part.strip().split()
            if not bits:
                continue
            score = 1.0
            if len(bits) > 1:
                m = re.match(r'^([\d.]+)([wx])$', bits[1])
                if m:
                    score = float(m.group(1))
            if score > best_score:
                best_url, best_score = bits[0], score
        return best_url

    @staticmethod
    def _url_ext(url):
        ext = os.path.splitext(urlparse(url).path)[1].lower().lstrip('.')
        return ext

    def _full_image_link(self, img):
        """<a href="大图.jpg"><img src="缩略图"></a> 时返回大图地址（<a> 须紧包 img）"""
        node = img.parent
        for _ in range(3):
            if node is None or node.name in ('div', 'li', 'ul', 'figure', 'p', 'section',
                                             'article', 'main', 'body'):
                return None
            if node.name == 'a':
                break
            node = node.parent
        else:
            return None
        href = (node.get('href') or '').strip()
        if href and self._url_ext(href) in IMAGE_EXTS:
            return href
        return None

    def _img_src(self, img):
        for attr in LAZY_ATTRS:
            val = (img.get(attr) or '').strip()
            if val and not val.startswith('data:'):
                return val
        srcset = (img.get('data-srcset') or img.get('srcset') or '').strip()
        if srcset:
            best = self._best_from_srcset(srcset)
            if best and not best.startswith('data:'):
                return best
        src = (img.get('src') or '').strip()
        if src and not src.startswith('data:'):
            return src
        return None

    @staticmethod
    def _is_small_icon_image(img):
        """width/height < 50，或 class/id 带 icon/logo/avatar 等词"""
        for attr in ('width', 'height'):
            m = re.match(r'^\s*(\d+)', str(img.get(attr, '')))
            if m and int(m.group(1)) < 50:
                return True
        return bool(ICON_PATTERN.search(_class_id_text(img)))

    @staticmethod
    def _is_in_excluded_area(img):
        """位于推荐/侧边栏/评论等区域（向上 10 层内），且不在正文容器里"""
        in_content = False
        for depth, parent in enumerate(img.parents):
            if depth >= 10 or parent.name in (None, '[document]'):
                break
            if parent.name not in ('div', 'section', 'article', 'aside', 'nav', 'footer',
                                   'header', 'main'):
                continue
            text = _class_id_text(parent)
            if CONTENT_AREA_PATTERN.search(text):
                in_content = True
            if not in_content and EXCLUDED_AREA_PATTERN.search(text):
                return True
        return False

    def extract_image_urls(self, soup, page_url):
        """提取正文图片的绝对地址（页内去重）"""
        urls, seen, skipped = [], set(), 0
        for img in soup.find_all('img'):
            full = self._full_image_link(img)
            if full is None and (self._is_small_icon_image(img) or self._is_in_excluded_area(img)):
                skipped += 1
                continue
            src = full or self._img_src(img)
            if not src:
                continue
            if self._url_ext(src) in ('svg', 'ico'):
                skipped += 1
                continue
            absolute = urljoin(page_url, src)
            if absolute.startswith(('http://', 'https://')) and absolute not in seen:
                seen.add(absolute)
                urls.append(absolute)
        if skipped:
            self.log(f"[*] 已过滤 {skipped} 张图标/推荐区图片")
        self.log(f"[+] 本页找到 {len(urls)} 张图片")
        return urls

    # ------------------------------------------------------------------ 翻页

    def _is_pagination_link(self, href, current_url):
        """
        是否当前文章的分页链接（满足任一）：
        1. 同路径 + ?page=N
        2. 当前路径后追加 /数字（/article/123/2）
        3. 当前路径含 .html，链接为 .html/数字（/article.html/2）
        推荐文章、品牌页等其它链接都会被排除。
        """
        if not href:
            return False
        link = urlparse(urljoin(current_url, href))
        current = urlparse(current_url)
        if link.netloc != current.netloc:
            return False
        link_path = link.path.rstrip('/')
        current_path = current.path.rstrip('/')
        if link_path == current_path and re.search(r'(^|&)page=\d+', link.query, re.I):
            return True
        if link_path.startswith(current_path + '/') and re.match(r'^/\d+$', link_path[len(current_path):]):
            return True
        if '.html' in current_path and re.sub(r'/\d+$', '', link_path) == current_path:
            return True
        return False

    def _extract_page_num_from_link(self, link, current_url):
        text = link.get_text(strip=True)
        href = link.get('href', '')
        m = re.match(r'^(?:Page)?(\d+)$', text, re.I)
        if m and self._is_pagination_link(href, current_url):
            return int(m.group(1))
        if href:
            m = re.search(r'[?&]page=(\d+)', href, re.I)
            if m:
                return int(m.group(1))
        return None

    def detect_total_pages(self, soup, current_url):
        """优先从分页容器里找最大页码，找不到再扫描全页链接"""
        max_page = 1
        containers = soup.find_all(['div', 'nav', 'ul', 'ol', 'span'],
                                   class_=re.compile(r'paginat|page-num|pager|nav-page', re.I))
        for scope in (containers, [soup]):
            for container in scope:
                for link in container.find_all('a'):
                    num = self._extract_page_num_from_link(link, current_url)
                    if num and num > max_page:
                        max_page = num
            if max_page > 1:
                break
        if max_page == 1:
            self.log("[*] 未检测到页码，将按“下一页”链接翻页")
            return None
        self.log(f"[+] 检测到总页数: {max_page}")
        return max_page

    def find_next_page_url(self, soup, current_url, current_page_num, total_pages=None):
        if total_pages is not None and current_page_num >= total_pages:
            self.log(f"[+] 已到最后一页 ({current_page_num}/{total_pages})")
            return None

        links = soup.find_all('a')
        next_page = current_page_num + 1

        # 1. 文本为下一页页码（"2"、"Page2"）
        for link in links:
            text = link.get_text(strip=True)
            if text in (str(next_page), f'Page{next_page}'):
                href = link.get('href')
                if href and self._is_pagination_link(href, current_url):
                    return urljoin(current_url, href)

        # 2. 文本含"下一页 / next / »"等
        next_texts = ('下一页', '下页', 'next', '>>>', '»', '→', '>')
        for link in links:
            text = link.get_text(strip=True).lower()
            if text and any(t in text for t in next_texts):
                href = link.get('href')
                if href and self._is_pagination_link(href, current_url):
                    return urljoin(current_url, href)

        # 3. rel="next"
        rel_next = soup.find(['a', 'link'], rel='next')
        if rel_next and rel_next.get('href') and self._is_pagination_link(rel_next['href'], current_url):
            return urljoin(current_url, rel_next['href'])

        # 4. 按 URL 规律推算
        if total_pages is None or next_page <= total_pages:
            parsed = urlparse(current_url)
            base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if re.search(r'(^|&)page=\d+', parsed.query, re.I):
                return base + '?' + re.sub(r'page=\d+', f'page={next_page}', parsed.query, flags=re.I)
            if current_page_num == 1 and not parsed.query:
                return f"{base}?page={next_page}"
            m = re.search(r'/(\d+)/?$', parsed.path)
            if m:
                return f"{parsed.scheme}://{parsed.netloc}{parsed.path[:m.start()]}/{next_page}"

        self.log(f"[-] 未找到第 {next_page} 页的链接")
        return None

    def collect_image_urls(self):
        """逐页收集图片，返回 ([(图片地址, 来源页)], 首页 soup)"""
        items, seen = [], set()
        current_url, page_num, total_pages = self.url, 1, None
        first_soup, visited, referer = None, set(), None

        while current_url and (self.max_pages is None or self.page_count < self.max_pages):
            self._check_cancel()
            if current_url in visited:
                self.log("[+] 检测到页面循环，停止翻页")
                break
            visited.add(current_url)
            self.page_count += 1
            self.log(f"\n[*] 第 {self.page_count} 页: {current_url}")

            final_url, soup = self.fetch_page(current_url, referer)
            if soup is None:
                break
            if final_url != current_url:
                if final_url in visited:
                    self.log("[+] 页面被重定向回已访问的页，停止翻页")
                    self.page_count -= 1
                    break
                visited.add(final_url)
            if first_soup is None:
                first_soup = soup
                if self.auto_pagination:
                    total_pages = self.detect_total_pages(soup, final_url)

            new = [u for u in self.extract_image_urls(soup, final_url) if u not in seen]
            seen.update(new)
            items.extend((u, final_url) for u in new)

            if not self.auto_pagination:
                break
            if not new and self.page_count > 1:
                self.log("[+] 本页没有新图片，判定翻页结束")
                break

            next_url = self.find_next_page_url(soup, final_url, page_num, total_pages)
            if not next_url or next_url == final_url:
                break
            referer, current_url, page_num = final_url, next_url, page_num + 1

        return items, first_soup

    # ------------------------------------------------------------------ 下载

    def _original_stem(self, url):
        stem = os.path.splitext(os.path.basename(urlparse(url).path))[0]
        return re.sub(r'[\\/:*?"<>|]', '_', stem)[:50]

    def _download_one(self, index, url, referer):
        """下载一张图片到临时文件名，返回 (状态, 临时路径, 大小)"""
        if self.stop_event.is_set():
            return 'cancelled', None, 0
        headers = {'Referer': referer,
                   'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8'}
        resp = self.session.get(url, timeout=self._timeouts, headers=headers)
        resp.raise_for_status()
        data = resp.content
        ext = sniff_image_ext(data)
        if ext is None:
            ctype = resp.headers.get('content-type', '?').split(';')[0]
            raise ValueError(f"返回的不是图片（{ctype}），可能被防盗链拦截")
        if self.min_image_size_kb and len(data) < self.min_image_size_kb * 1024:
            return 'small', None, len(data)
        if self.dedupe:
            digest = hashlib.md5(data).hexdigest()
            with self._lock:
                if digest in self._hashes:
                    return 'duplicate', None, len(data)
                self._hashes.add(digest)
        path = os.path.join(self.output_dir, f"~{index:05d}.{ext}")
        with open(path, 'wb') as f:
            f.write(data)
        return 'ok', path, len(data)

    def download_all(self, items):
        """并发下载，完成后按页面顺序重新编号为 001、002…（跳过的图片不占编号）"""
        total = len(items)
        self.log(f"\n[*] 开始下载 {total} 张图片，{self.num_threads} 个线程")
        saved, done = {}, 0
        pool = ThreadPoolExecutor(max_workers=self.num_threads)
        futures = {pool.submit(self._download_one, i, url, ref): (i, url)
                   for i, (url, ref) in enumerate(items)}
        try:
            for fut in as_completed(futures):
                i, url = futures.pop(fut)
                done += 1
                try:
                    status, path, size = fut.result()
                except Exception as e:
                    status, path, size = 'failed', None, 0
                    self.log(f"[-] 第 {i + 1} 张下载失败: {str(e)[:80]}  {url}")
                if status == 'ok':
                    saved[i] = (path, url)
                    self.log(f"[{done}/{total}] ✓ 第 {i + 1} 张 ({size // 1024} KB)")
                elif status == 'small':
                    self.log(f"[{done}/{total}] ~ 第 {i + 1} 张太小，跳过 ({size // 1024} KB)")
                elif status == 'duplicate':
                    self.log(f"[{done}/{total}] ~ 第 {i + 1} 张与已下载的图片重复，跳过")
                if status in self.stats:
                    self.stats[status] += 1
                if self.progress:
                    self.progress(done, total)
                if self.stop_event.is_set():
                    break
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
        # 取消时仍在进行的下载也可能已经落盘
        for fut, (i, url) in futures.items():
            if fut.done() and not fut.cancelled() and fut.exception() is None:
                status, path, _ = fut.result()
                if status == 'ok':
                    saved[i] = (path, url)
                    self.stats['ok'] += 1
        self._finalize_names(saved)

    def _finalize_names(self, saved):
        for n, i in enumerate(sorted(saved), start=1):
            tmp, url = saved[i]
            ext = os.path.splitext(tmp)[1]
            stem = '' if self.use_sequential_naming else self._original_stem(url)
            name = f"{n:03d}_{stem}{ext}" if stem else f"{n:03d}{ext}"
            os.replace(tmp, os.path.join(self.output_dir, name))

    @staticmethod
    def _unique_dir(path):
        candidate, n = path, 2
        while True:
            try:
                os.makedirs(candidate)
                return candidate
            except FileExistsError:
                candidate, n = f"{path}_{n}", n + 1

    def run(self):
        """完整流程：收集 → 下载 → 统计。有图片下载成功返回 True"""
        self.log("=" * 60)
        self.log(f"网页地址: {self.url}")
        self.log(f"输出根目录: {os.path.abspath(self.output_base_dir)}")
        pages = '是' + (f'（最多 {self.max_pages} 页）' if self.max_pages else '') if self.auto_pagination else '否'
        self.log(f"线程数: {self.num_threads}    自动翻页: {pages}")
        self.log("=" * 60)
        start = time.time()
        cancelled = False
        try:
            items, first_soup = self.collect_image_urls()
            if not items:
                self.log("[-] 未找到任何图片")
                return False
            self.output_dir = self._unique_dir(
                os.path.join(self.output_base_dir, self.generate_subdir_name(self.url, first_soup)))
            self.log(f"\n[+] 输出目录: {os.path.abspath(self.output_dir)}")
            self.download_all(items)
            cancelled = self.stop_event.is_set()
        except Cancelled:
            cancelled = True
            items = []

        s = self.stats
        self.log("\n" + "=" * 60)
        self.log("已取消" if cancelled else "下载完成")
        self.log(f"页数: {self.page_count}    图片: {len(items)}    成功: {s['ok']}    失败: {s['failed']}")
        if s['small'] or s['duplicate']:
            self.log(f"跳过: 太小 {s['small']} 张，重复 {s['duplicate']} 张")
        self.log(f"耗时: {time.time() - start:.1f} 秒")
        if self.output_dir:
            self.log(f"保存位置: {os.path.abspath(self.output_dir)}")
        self.log("=" * 60)
        return s['ok'] > 0

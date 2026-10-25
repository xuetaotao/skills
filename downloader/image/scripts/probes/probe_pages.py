# -*- coding: utf-8 -*-
"""逐个探测网页（不下载、不写文件）：python scripts/probes/probe_pages.py [网址 ...]

不带参数时读取项目根目录 test_sites.md 里的网址。每个网址只取第一页，输出标题、正文图片数、
识别到的总页数和下一页地址，并抽查第一张图片的真实格式，用来排查某个网站改版、防盗链或翻页失效。
"""
import os
import re
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)
from backend.core import WebpageImageDownloader, sniff_image_ext  # noqa: E402


def site_urls():
    path = os.path.join(PROJECT_DIR, 'test_sites.md')
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return re.findall(r'^\s*-\s*(https?://[^\s（(]+)', f.read(), re.M)


def probe(url):
    t = time.time()
    d = WebpageImageDownloader(url, output_dir=PROJECT_DIR, log=lambda m: None)
    final, soup = d.fetch_page(url)
    if soup is None:
        return f"失败：网页打不开  {time.time() - t:.1f}s"
    title = (soup.title.get_text(strip=True) if soup.title else '')[:30]
    images = d.extract_image_urls(soup, final)
    total = d.detect_total_pages(soup, final)
    nxt = d.find_next_page_url(soup, final, 1, total)
    first = '无图片'
    if images:
        try:
            resp = d.session.get(images[0], headers={'Referer': final}, timeout=d._timeouts)
            first = f"首图 {sniff_image_ext(resp.content[:32]) or '不是图片（可能防盗链）'} {len(resp.content) // 1024} KB"
        except Exception as e:  # noqa: BLE001
            first = f"首图失败：{type(e).__name__}"
    return (f"{title}  图片 {len(images)} 张  总页数 {total or '未识别'}  下一页 {'有' if nxt else '无'}  "
            f"{first}  {time.time() - t:.1f}s")


def main():
    urls = sys.argv[1:] or site_urls()
    if not urls:
        print("用法：python scripts/probes/probe_pages.py <网址> ...（或在 test_sites.md 里列出网址）")
        return
    for url in urls:
        try:
            result = probe(url)
        except Exception as e:  # noqa: BLE001
            result = f"失败：{type(e).__name__}: {e}"
        print(f"{url}\n    {result}")


if __name__ == "__main__":
    main()

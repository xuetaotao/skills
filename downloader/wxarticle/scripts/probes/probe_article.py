# -*- coding: utf-8 -*-
"""探测文章能不能抓（只打开、不保存）：python scripts/probes/probe_article.py <链接> [...]

每个链接输出标题、公众号、发布时间、正文高度、图片数和用时；打不开时输出微信提示页上的原因
（隐私设置 / 已删除 / 环境异常等），用来排查某篇文章为什么下载失败，或者微信页面结构是否改版。
"""
import asyncio
import os
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)
from backend.core import extract_urls  # noqa: E402
from backend.fetcher import ArticleError, ArticleFetcher  # noqa: E402


async def probe(urls):
    async with ArticleFetcher(scale=1) as fetcher:
        for url in urls:
            start = time.time()
            try:
                a = await fetcher.fetch(url)
            except ArticleError as e:
                print(f'失败  {url}\n      {e}（{time.time() - start:.1f}s）')
                continue
            height = await a.page.evaluate("document.querySelector('#js_content').offsetHeight")
            await a.page.close()
            print(f'成功  {url}\n      {a.title} | {a.account or "?"} | {a.publish_time or "?"} '
                  f'(ct={a.timestamp}) | 正文 {height}px | 图片 {a.images} 张'
                  f'{f"（{a.failed_images} 张失败）" if a.failed_images else ""}（{time.time() - start:.1f}s）')


if __name__ == '__main__':
    sys.stdout.reconfigure(errors='replace')
    links = extract_urls(sys.argv[1:])
    if not links:
        sys.exit(__doc__.strip().splitlines()[0])
    try:
        asyncio.run(probe(links))
    except ArticleError as e:
        sys.exit(f'错误：{e}')

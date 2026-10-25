"""批量下载流程：一个浏览器依次处理多篇文章，命令行和图形界面共用。"""

import re
import time
from dataclasses import dataclass, field

from playwright.async_api import Error as PlaywrightError

from .config import SCALE
from .fetcher import Article, ArticleError, ArticleFetcher, first_line
from .generator import OutputGenerator

URL_RE = re.compile(r'https?://[^\s"\'<>，。（）]+')


def extract_urls(texts) -> list:
    """从任意文本里抠出链接并去重（保留顺序），方便直接粘贴“标题 + 链接”。"""
    urls = []
    for text in texts:
        for url in URL_RE.findall(text):
            if url not in urls:
                urls.append(url)
    return urls


@dataclass
class Result:
    url: str
    ok: bool = False
    title: str = ''
    account: str = ''
    publish_time: str = ''
    images: int = 0
    failed_images: int = 0
    pdf: object = None                              # Path，没生成为 None
    screenshots: list = field(default_factory=list)  # 一般一张，超长时多张
    error: str = ''
    seconds: float = 0.0


class Reporter:
    """进度回调，默认什么都不做；命令行打印，图形界面转成 Qt 信号。"""

    def start(self, index: int, total: int, url: str):
        pass

    def article(self, index: int, article: Article):
        """打开成功、图片加载完，开始保存之前。"""

    def finished(self, index: int, result: Result):
        pass


async def download_articles(urls, output_dir=None, pdf=True, screenshot=True,
                            headless=True, scale=SCALE, reporter=None) -> list:
    """逐篇下载，单篇失败记进结果继续下一篇。

    浏览器启动失败（如没装 Chromium）抛 ArticleError；取消时抛 asyncio.CancelledError，
    已完成的文件保留。
    """
    reporter = reporter or Reporter()
    generator = OutputGenerator(output_dir)
    results = []
    async with ArticleFetcher(headless=headless, scale=scale) as fetcher:
        for index, url in enumerate(urls):
            reporter.start(index, len(urls), url)
            result = Result(url)
            start = time.perf_counter()
            try:
                article = await fetcher.fetch(url)
                try:
                    result.title, result.account = article.title, article.account
                    result.publish_time = article.publish_time
                    result.images, result.failed_images = article.images, article.failed_images
                    reporter.article(index, article)
                    files = await generator.generate(article, pdf=pdf, screenshot=screenshot)
                finally:
                    await article.page.close()
                result.pdf = files.get('pdf')
                result.screenshots = files.get('screenshot', [])
                result.ok = True
            except (ArticleError, PlaywrightError, OSError) as e:
                result.error = first_line(e)
            result.seconds = time.perf_counter() - start
            results.append(result)
            reporter.finished(index, result)
    return results

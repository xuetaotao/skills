"""用 Playwright 打开公众号文章，等正文和图片都加载完。"""

from dataclasses import dataclass

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

from .config import (BLOCKED_HINTS, CONTENT_TIMEOUT, IMAGE_TIMEOUT, NAV_TIMEOUT, SCALE,
                     SCROLL_PAUSE, USER_AGENT, VIEWPORT)


class ArticleError(Exception):
    """文章拿不到（隐私设置、已删除、超时、浏览器没装等），消息直接给用户看。"""


@dataclass
class Article:
    url: str
    title: str
    account: str
    publish_time: str      # 页面上显示的时间，如 “2025年12月2日 08:47”
    timestamp: int         # 页面脚本里的发布时间戳，拿不到为 0
    page: Page
    images: int = 0
    failed_images: int = 0


# 返回 'ok' 表示正文已出现；返回字符串表示命中了微信提示页；返回 false 继续等
READY_JS = """(hints) => {
  if (document.querySelector('#js_content')) return 'ok';
  const lines = (document.body ? document.body.innerText : '').split(/\\n+/).map(s => s.trim());
  const hit = lines.find(line => hints.some(h => line.includes(h)));
  return hit ? hit.slice(0, 60) : false;
}"""

INFO_JS = """() => {
  const pick = sels => {
    for (const s of sels) {
      const el = document.querySelector(s);
      const t = el && el.textContent.replace(/\\s+/g, ' ').trim();
      if (t) return t;
    }
    return '';
  };
  const meta = p => (document.querySelector(`meta[property="${p}"]`) || {}).content || '';
  const ct = document.documentElement.innerHTML.match(/var\\s+ct\\s*=\\s*"(\\d{10})"/);
  return {
    title: pick(['#activity-name', '.rich_media_title']) || meta('og:title') || document.title,
    account: pick(['#js_name', '.rich_media_meta_nickname', '#profileBt .profile_nickname', '.profile_nickname'])
             || meta('og:article:author'),
    publish_time: pick(['#publish_time']),
    timestamp: ct ? Number(ct[1]) : 0,
  };
}"""

# 懒加载图片：把 data-src 直接写进 src，再滚一遍页面让微信自己的懒加载（背景图等）也跑起来，
# 最后等所有图片 load/error，超时就带着没加载完的继续
LOAD_JS = """async ([pause, timeout]) => {
  const box = document.querySelector('#js_content');
  box.style.visibility = 'visible';
  box.style.opacity = '1';
  const imgs = [...box.querySelectorAll('img')];
  for (const img of imgs) {
    const real = img.getAttribute('data-src');
    const cur = img.getAttribute('src') || '';
    if (real && (!cur || cur.startsWith('data:'))) img.src = real;
    img.loading = 'eager';
  }
  const deadline = Date.now() + timeout;
  for (let y = 0; y < document.documentElement.scrollHeight && Date.now() < deadline; y += innerHeight) {
    scrollTo(0, y);
    await new Promise(r => setTimeout(r, pause));
  }
  scrollTo(0, 0);
  const pending = imgs.filter(i => !i.complete).map(i => new Promise(r => {
    i.addEventListener('load', r, {once: true});
    i.addEventListener('error', r, {once: true});
  }));
  await Promise.race([
    Promise.all([...pending, document.fonts.ready]),
    new Promise(r => setTimeout(r, Math.max(0, deadline - Date.now()))),
  ]);
  return {
    total: imgs.length,
    failed: imgs.filter(i => !i.complete || i.naturalWidth === 0).length,
  };
}"""


def first_line(err: Exception) -> str:
    return str(err).strip().splitlines()[0] if str(err).strip() else type(err).__name__


class ArticleFetcher:
    """一个浏览器实例，可以连续抓多篇文章（每篇一个新标签页）。"""

    def __init__(self, headless: bool = True, scale: float = SCALE):
        self.headless = headless
        self.scale = scale
        self._playwright = None
        self._browser = None
        self._context = None

    async def __aenter__(self):
        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
        except PlaywrightError as e:
            await self._playwright.stop()
            if "Executable doesn't exist" in str(e):
                raise ArticleError('没有找到 Playwright 自带的 Chromium，请先运行：'
                                   'python -m playwright install chromium') from None
            raise
        self._context = await self._browser.new_context(
            user_agent=USER_AGENT, locale='zh-CN', viewport=VIEWPORT,
            device_scale_factor=self.scale)
        return self

    async def __aexit__(self, *exc):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def fetch(self, url: str) -> Article:
        """打开文章并等加载完。返回的 page 由调用方用完后关闭。"""
        page = await self._context.new_page()
        try:
            await self._open(page, url)
            info = await page.evaluate(INFO_JS)
            stats = await page.evaluate(LOAD_JS, [SCROLL_PAUSE, IMAGE_TIMEOUT])
        except BaseException:
            await page.close()
            raise
        return Article(url=url, page=page, images=stats['total'],
                       failed_images=stats['failed'], **info)

    async def _open(self, page: Page, url: str):
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=NAV_TIMEOUT)
        except PlaywrightTimeout:
            raise ArticleError(f'打开页面超时（{NAV_TIMEOUT // 1000} 秒），请检查网络') from None
        except PlaywrightError as e:
            raise ArticleError(f'打开页面失败：{first_line(e)}') from None

        try:
            handle = await page.wait_for_function(
                READY_JS, arg=list(BLOCKED_HINTS), timeout=CONTENT_TIMEOUT, polling=200)
        except PlaywrightTimeout:
            text = await page.evaluate(
                "document.body ? document.body.innerText.replace(/\\s+/g, ' ').trim().slice(0, 60) : ''")
            hint = f'，页面显示：{text}' if text else ''
            raise ArticleError(f'{CONTENT_TIMEOUT // 1000} 秒内没有等到正文{hint}') from None
        result = await handle.json_value()
        if result != 'ok':
            raise ArticleError(f'文章无法查看：{result}')

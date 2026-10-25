"""把已加载好的文章页保存成 PDF 和长截图。"""

import math
import re
from datetime import datetime
from pathlib import Path

from playwright.async_api import Page

from .config import MAX_SCREENSHOT_HEIGHT, OUTPUT_DIR, PDF_MARGIN
from .fetcher import Article

# 只在打印（PDF）时生效：去掉正文后面的“作者提示 / 上一篇下一篇”和右侧二维码
PRINT_CSS = """
@media print {
  #img-content ~ *, .rich_media_area_extra, .qr_code_pc_outer,
  body:has(> #js_article) > :not(#js_article) { display: none !important; }
  body, #page-content, .rich_media_area_primary_inner, #img-content, #js_content {
    padding-bottom: 0 !important; margin-bottom: 0 !important; min-height: 0 !important;
  }
}
"""

# 截图区域：正文栏（标题到正文结束），左右各留一点白边
CLIP_JS = """() => {
  const content = document.querySelector('#js_content');
  const column = document.querySelector('#img-content') || content;
  const title = document.querySelector('#activity-name, .rich_media_title');
  const col = column.getBoundingClientRect();
  const top = Math.max(0, Math.floor((title || content).getBoundingClientRect().top + scrollY - 20));
  const bottom = Math.ceil(content.getBoundingClientRect().bottom + scrollY + 30);
  const x = Math.max(0, Math.floor(col.left - 24));
  const width = Math.min(Math.ceil(col.width + 48), document.documentElement.scrollWidth - x);
  return {x, y: top, width, height: bottom - top};
}"""

# 视口拉到正文高度后，底部悬浮栏（赞 / 分享 / 写留言）会正好盖在正文末尾；
# 用透明而不是 display:none，sticky 元素还占着位置，不会让排版跳动
HIDE_FLOATING_JS = """() => {
  const box = document.querySelector('#js_content');
  let n = 0;
  for (const el of document.querySelectorAll('body *')) {
    if (box.contains(el)) continue;
    const pos = getComputedStyle(el).position;
    if (pos === 'fixed' || pos === 'sticky') {
      el.style.setProperty('opacity', '0', 'important');
      n++;
    }
  }
  return n;
}"""

TIME_FORMATS = ('%Y年%m月%d日 %H:%M', '%Y年%m月%d日', '%Y-%m-%d %H:%M', '%Y-%m-%d')


def sanitize_filename(name: str, limit: int = 80) -> str:
    """去掉 Windows 文件名里不允许的字符，过长截断。"""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    name = re.sub(r'\s+', ' ', name).strip().strip('.')
    return name[:limit]


def publish_stamp(article: Article) -> str:
    """文件名里的时间：优先页面脚本里的时间戳，其次页面显示的时间，都没有就用当前时间。"""
    if article.timestamp:
        return datetime.fromtimestamp(article.timestamp).strftime('%Y%m%d_%H%M')
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(article.publish_time, fmt).strftime('%Y%m%d_%H%M')
        except ValueError:
            continue
    return datetime.now().strftime('%Y%m%d_%H%M%S')


def base_name(article: Article) -> str:
    """{公众号}-{标题}-{发布时间}，公众号拿不到就省略。"""
    parts = [sanitize_filename(article.account), sanitize_filename(article.title) or '无标题',
             publish_stamp(article)]
    return '-'.join(p for p in parts if p)


class OutputGenerator:
    def __init__(self, output_dir=None):
        self.output_dir = Path(output_dir) if output_dir else OUTPUT_DIR

    async def generate(self, article: Article, pdf: bool = True, screenshot: bool = True) -> dict:
        """先出 PDF 再截图（截图会改视口高度，影响打印排版）。"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        name = base_name(article)
        result = {}
        if pdf:
            result['pdf'] = await self.save_pdf(article.page, self.output_dir / f'{name}.pdf')
        if screenshot:
            result['screenshot'] = await self.save_screenshot(article.page, self.output_dir / f'{name}.png')
        return result

    async def save_pdf(self, page: Page, path: Path) -> Path:
        await page.add_style_tag(content=PRINT_CSS)
        await page.evaluate(HIDE_FLOATING_JS)
        margin = {side: PDF_MARGIN for side in ('top', 'bottom', 'left', 'right')}
        await page.pdf(path=str(path), format='A4', print_background=True, margin=margin)
        return path

    async def save_screenshot(self, page: Page, path: Path) -> list:
        """返回生成的图片列表：一般一张；太长时按 MAX_SCREENSHOT_HEIGHT 拆成 _1、_2 ……"""
        clip = await page.evaluate(CLIP_JS)
        ratio = await page.evaluate('devicePixelRatio')
        if clip['height'] * ratio <= MAX_SCREENSHOT_HEIGHT:
            scale, step = 'device', clip['height']
        else:
            scale, step = 'css', MAX_SCREENSHOT_HEIGHT
        count = math.ceil(clip['height'] / step)
        paths = [path] if count == 1 else [path.with_name(f'{path.stem}_{i}{path.suffix}')
                                            for i in range(1, count + 1)]

        # 截图只截得到视口里的内容（超出部分会是空白），所以每段都把视口拉到这段的高度再滚过去
        width = page.viewport_size['width']
        for i, part in enumerate(paths):
            top = clip['y'] + i * step
            height = min(step, clip['y'] + clip['height'] - top)
            await page.set_viewport_size({'width': width, 'height': math.ceil(height)})
            scroll_y = await page.evaluate(f'(scrollTo(0, {top}), scrollY)')
            await page.wait_for_timeout(300)
            await page.evaluate(HIDE_FLOATING_JS)
            await page.screenshot(path=str(part), scale=scale, clip={
                'x': clip['x'], 'y': top - scroll_y, 'width': clip['width'], 'height': height})
        return paths

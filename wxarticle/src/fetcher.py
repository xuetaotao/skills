"""Article fetcher module for WeChat public account articles."""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, Browser, Page


class ArticleFetcher:
    """Fetches WeChat public account articles using Playwright."""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser: Browser = None
        self.page: Page = None
        
    async def __aenter__(self):
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context()
        # Set user agent to mimic real browser
        await self.context.set_extra_http_headers({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self.page = await self.context.new_page()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
    
    async def fetch_article(self, url: str) -> dict:
        """
        Fetch article content from WeChat public account.
        
        Args:
            url: WeChat article URL
            
        Returns:
            dict with 'title', 'content', 'url' keys
        """
        print(f"Fetching article: {url}")
        
        # Navigate to the article
        await self.page.goto(url, wait_until='networkidle', timeout=60000)
        
        # Wait for main content to load
        await self.page.wait_for_selector('#js_content', timeout=30000)
        
        # Get article title
        title = await self.page.title()
        # Clean up title - remove common suffixes
        for suffix in [' - 公众号', ' - 微信', ' | 微信公众平台']:
            title = title.replace(suffix, '')
        title = title.strip()
        
        # Scroll to trigger lazy-loaded images
        await self._scroll_page()
        
        # Force all lazy-loaded images to load
        await self._force_load_images()
        
        # Wait for images to fully render
        await self._wait_for_images()
        
        # Expand viewport to fit all content before screenshot
        await self._expand_viewport_for_screenshot()
        
        print(f"Article fetched: {title}")
        
        return {
            'title': title,
            'url': url,
            'page': self.page
        }
    
    async def _scroll_page(self):
        """Scroll page to trigger lazy-loaded content."""
        scroll_height = await self.page.evaluate('document.body.scrollHeight')
        viewport_height = await self.page.evaluate('window.innerHeight')
        
        # Scroll down in small steps to trigger all lazy content
        current_position = 0
        step = viewport_height // 3
        
        while current_position < scroll_height:
            await self.page.evaluate(f'window.scrollTo(0, {current_position})')
            await asyncio.sleep(0.5)
            current_position += step
            scroll_height = await self.page.evaluate('document.body.scrollHeight')
        
        # Scroll to the very bottom and wait
        await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await asyncio.sleep(1)
        
        # Scroll back to top
        await self.page.evaluate('window.scrollTo(0, 0)')
        await asyncio.sleep(0.5)
    
    async def _force_load_images(self):
        """Force all lazy-loaded images to load by copying data-src to src."""
        # WeChat articles use data-src for lazy loading
        # Copy data-src to src for all images that haven't loaded yet
        count = await self.page.evaluate("""() => {
            const images = document.querySelectorAll('#js_content img[data-src]');
            let loaded = 0;
            images.forEach(img => {
                if (!img.src || img.src === '' || img.src.includes('data:image')) {
                    img.src = img.getAttribute('data-src');
                    loaded++;
                }
                // Ensure image is visible
                img.style.opacity = '1';
                img.style.visibility = 'visible';
                img.style.display = '';
            });
            return loaded;
        }""")
        if count > 0:
            print(f"Forced {count} lazy images to load")
            await asyncio.sleep(2)
    
    async def _wait_for_images(self):
        """Wait for all images to load."""
        images = await self.page.query_selector_all('#js_content img')
        print(f"Found {len(images)} images, waiting for them to load...")
        
        for i, img in enumerate(images):
            try:
                await img.wait_for_element_state('visible', timeout=5000)
                await asyncio.sleep(0.05)
            except Exception:
                pass
        
        await asyncio.sleep(1)
    
    async def _expand_viewport_for_screenshot(self):
        """Expand viewport to fit all content, preventing scroll-based content loss."""
        # Get the full content height
        content_height = await self.page.evaluate("""() => {
            const content = document.querySelector('#js_content');
            if (!content) return 0;
            
            // Force all content to be visible
            content.style.overflow = 'visible';
            
            // Get full height including overflow
            const rect = content.getBoundingClientRect();
            const scrollHeight = content.scrollHeight;
            const clientHeight = content.clientHeight;
            
            return Math.max(rect.height, scrollHeight, clientHeight);
        }""")
        
        print(f"Content height: {content_height}px")
        
        # Set viewport to fit all content (width 1280 for good readability)
        # Add some buffer to ensure nothing is cut off
        viewport_width = 1280
        viewport_height = int(content_height) + 200  # Add 200px buffer
        
        print(f"Setting viewport to {viewport_width}x{viewport_height}")
        await self.page.set_viewport_size({'width': viewport_width, 'height': viewport_height})
        
        # Wait for layout to stabilize
        await asyncio.sleep(1)
        
        # Scroll to top to ensure we're at the beginning
        await self.page.evaluate('window.scrollTo(0, 0)')
        await asyncio.sleep(0.5)

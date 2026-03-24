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
        
        # Wait for images to load
        await self._wait_for_images()
        
        print(f"Article fetched: {title}")
        
        return {
            'title': title,
            'url': url,
            'page': self.page
        }
    
    async def _scroll_page(self):
        """Scroll page to trigger lazy-loaded content."""
        # Get scroll height
        scroll_height = await self.page.evaluate('document.body.scrollHeight')
        viewport_height = await self.page.evaluate('window.innerHeight')
        
        # Scroll down in steps
        current_position = 0
        step = viewport_height // 2
        
        while current_position < scroll_height:
            await self.page.evaluate(f'window.scrollTo(0, {current_position})')
            await asyncio.sleep(0.3)
            current_position += step
            # Update scroll height as content might expand
            scroll_height = await self.page.evaluate('document.body.scrollHeight')
        
        # Scroll back to top
        await self.page.evaluate('window.scrollTo(0, 0)')
        await asyncio.sleep(0.5)
    
    async def _wait_for_images(self):
        """Wait for all images to load."""
        images = await self.page.query_selector_all('#js_content img')
        print(f"Found {len(images)} images, waiting for them to load...")
        
        for i, img in enumerate(images):
            try:
                await img.wait_for_element_state('visible', timeout=5000)
                await asyncio.sleep(0.1)
            except Exception:
                # Image might not load, continue
                pass
        
        # Additional wait for images
        await asyncio.sleep(1)

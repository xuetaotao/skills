"""PDF and screenshot generator module."""

import re
from datetime import datetime
from pathlib import Path
from playwright.async_api import Page


def sanitize_filename(name: str) -> str:
    """Remove invalid characters from filename."""
    # Replace invalid characters with underscore
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Remove leading/trailing spaces and dots
    name = name.strip().strip('.')
    # Limit length
    return name[:100] if len(name) > 100 else name


def _format_publish_time(publish_time: str) -> str:
    """Format publish time string for use in filename."""
    if not publish_time:
        return datetime.now().strftime('%Y%m%d_%H%M%S')
    # Try to parse common WeChat publish time formats
    for fmt in ['%Y-%m-%d %H:%M', '%Y-%m-%d', '%Y年%m月%d日 %H:%M', '%Y年%m月%d日']:
        try:
            dt = datetime.strptime(publish_time, fmt)
            return dt.strftime('%Y%m%d_%H%M')
        except ValueError:
            continue
    # If parsing fails, sanitize and use as-is
    return sanitize_filename(publish_time)


class OutputGenerator:
    """Generates PDF and screenshot from article page."""
    
    def __init__(self, output_dir: str = None):
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            # Default to output directory in project root
            self.output_dir = Path(__file__).parent.parent / 'output'
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    async def generate_pdf(self, page: Page, title: str, account_name: str = '', publish_time: str = '') -> str:
        """
        Generate PDF from page.
        
        Args:
            page: Playwright page object
            title: Article title for filename
            account_name: WeChat account name for filename
            publish_time: Article publish time for filename
            
        Returns:
            Path to generated PDF file
        """
        time_str = _format_publish_time(publish_time)
        safe_title = sanitize_filename(title)
        safe_account = sanitize_filename(account_name) if account_name else ''
        if safe_account:
            filename = f"{safe_account}-{safe_title}-{time_str}.pdf"
        else:
            filename = f"{safe_title}-{time_str}.pdf"
        output_path = self.output_dir / filename
        
        print(f"Generating PDF: {filename}")
        
        await page.pdf(
            path=str(output_path),
            format='A4',
            print_background=True,
            margin={
                'top': '20px',
                'bottom': '20px',
                'left': '20px',
                'right': '20px'
            }
        )
        
        print(f"PDF saved: {output_path}")
        return str(output_path)
    
    async def generate_screenshot(self, page: Page, title: str, account_name: str = '', publish_time: str = '') -> str:
        """
        Generate full-page screenshot.
        
        Args:
            page: Playwright page object
            title: Article title for filename
            account_name: WeChat account name for filename
            publish_time: Article publish time for filename
            
        Returns:
            Path to generated screenshot file
        """
        time_str = _format_publish_time(publish_time)
        safe_title = sanitize_filename(title)
        safe_account = sanitize_filename(account_name) if account_name else ''
        if safe_account:
            filename = f"{safe_account}-{safe_title}-{time_str}.png"
        else:
            filename = f"{safe_title}-{time_str}.png"
        output_path = self.output_dir / filename
        
        print(f"Generating screenshot: {filename}")
        
        # Get the article area (title + content), excluding footer
        article_box = await page.evaluate("""() => {
            // Find title element
            const titleEl = document.querySelector('#activity_name') || 
                           document.querySelector('.rich_media_title') ||
                           document.querySelector('h1.rich_media_title');
            
            // Find content element
            const contentEl = document.querySelector('#js_content');
            
            if (!contentEl) return null;
            
            const contentRect = contentEl.getBoundingClientRect();
            
            // Start from top of page (0) to include title, or from title if found
            let startY = 0;
            if (titleEl) {
                const titleRect = titleEl.getBoundingClientRect();
                startY = Math.max(0, titleRect.top - 20);  // 20px padding above title
            }
            
            // End at bottom of content
            const endY = contentRect.bottom;
            
            // Use full page width
            const pageWidth = Math.max(
                document.documentElement.scrollWidth,
                document.body.scrollWidth
            );
            
            return {
                x: 0,
                y: startY,
                width: pageWidth,
                height: endY - startY + 50  // 50px padding below content
            };
        }""")
        
        if article_box:
            await page.screenshot(
                path=str(output_path),
                clip=article_box,
                full_page=False
            )
        else:
            # Fallback to full page screenshot
            await page.screenshot(
                path=str(output_path),
                full_page=True
            )
        
        print(f"Screenshot saved: {output_path}")
        return str(output_path)
    
    async def generate_all(self, page: Page, title: str, account_name: str = '', publish_time: str = '',
                           pdf: bool = True, screenshot: bool = True) -> dict:
        """
        Generate both PDF and screenshot.
        
        Args:
            page: Playwright page object
            title: Article title for filename
            account_name: WeChat account name for filename
            publish_time: Article publish time for filename
            pdf: Whether to generate PDF
            screenshot: Whether to generate screenshot
            
        Returns:
            dict with paths to generated files
        """
        result = {}
        
        if pdf:
            result['pdf'] = await self.generate_pdf(page, title, account_name, publish_time)
        
        if screenshot:
            result['screenshot'] = await self.generate_screenshot(page, title, account_name, publish_time)
        
        return result

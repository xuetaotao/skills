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


class OutputGenerator:
    """Generates PDF and screenshot from article page."""
    
    def __init__(self, output_dir: str = None):
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            # Default to output directory in project root
            self.output_dir = Path(__file__).parent.parent / 'output'
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    async def generate_pdf(self, page: Page, title: str) -> str:
        """
        Generate PDF from page.
        
        Args:
            page: Playwright page object
            title: Article title for filename
            
        Returns:
            Path to generated PDF file
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_title = sanitize_filename(title)
        filename = f"{timestamp}_{safe_title}.pdf"
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
    
    async def generate_screenshot(self, page: Page, title: str) -> str:
        """
        Generate full-page screenshot.
        
        Args:
            page: Playwright page object
            title: Article title for filename
            
        Returns:
            Path to generated screenshot file
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_title = sanitize_filename(title)
        filename = f"{timestamp}_{safe_title}.png"
        output_path = self.output_dir / filename
        
        print(f"Generating screenshot: {filename}")
        
        await page.screenshot(
            path=str(output_path),
            full_page=True
        )
        
        print(f"Screenshot saved: {output_path}")
        return str(output_path)
    
    async def generate_all(self, page: Page, title: str, 
                           pdf: bool = True, screenshot: bool = True) -> dict:
        """
        Generate both PDF and screenshot.
        
        Args:
            page: Playwright page object
            title: Article title for filename
            pdf: Whether to generate PDF
            screenshot: Whether to generate screenshot
            
        Returns:
            dict with paths to generated files
        """
        result = {}
        
        if pdf:
            result['pdf'] = await self.generate_pdf(page, title)
        
        if screenshot:
            result['screenshot'] = await self.generate_screenshot(page, title)
        
        return result

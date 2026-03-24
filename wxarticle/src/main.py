#!/usr/bin/env python3
"""Command-line interface for WeChat article downloader."""

import asyncio
import sys
from pathlib import Path

import click

from .fetcher import ArticleFetcher
from .generator import OutputGenerator


async def async_main(url: str, output_dir: str, pdf: bool, screenshot: bool):
    """Main async function."""
    if not pdf and not screenshot:
        print("Error: At least one output format (PDF or screenshot) is required.")
        sys.exit(1)
    
    async with ArticleFetcher() as fetcher:
        try:
            # Fetch article
            article = await fetcher.fetch_article(url)
            
            # Generate outputs
            generator = OutputGenerator(output_dir)
            results = await generator.generate_all(
                page=article['page'],
                title=article['title'],
                pdf=pdf,
                screenshot=screenshot
            )
            
            print("\n" + "=" * 50)
            print("Download completed!")
            print(f"Title: {article['title']}")
            if 'pdf' in results:
                print(f"PDF: {results['pdf']}")
            if 'screenshot' in results:
                print(f"Screenshot: {results['screenshot']}")
            print("=" * 50)
            
            return results
            
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)


@click.command()
@click.argument('url')
@click.option('-o', '--output', 'output_dir', 
              default=None,
              help='Output directory (default: wxarticle/output)')
@click.option('--pdf-only', 'pdf_only',
              is_flag=True,
              help='Generate only PDF')
@click.option('--screenshot-only', 'screenshot_only',
              is_flag=True,
              help='Generate only screenshot')
def main(url: str, output_dir: str, pdf_only: bool, screenshot_only: bool):
    """
    Download WeChat public account article as PDF and/or screenshot.
    
    URL: WeChat article URL (e.g., https://mp.weixin.qq.com/s/...)
    
    Examples:
        wxarticle https://mp.weixin.qq.com/s/xxxxx
        wxarticle https://mp.weixin.qq.com/s/xxxxx -o ./my_output
        wxarticle https://mp.weixin.qq.com/s/xxxxx --pdf-only
    """
    pdf = not screenshot_only
    screenshot = not pdf_only
    
    asyncio.run(async_main(url, output_dir, pdf, screenshot))


if __name__ == '__main__':
    main()

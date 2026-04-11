# -*- coding: utf-8 -*-
"""
网页图片下载工具
从指定网页地址下载所有图片到指定目录
"""

import os
import sys
import re
import argparse
import requests
from urllib.parse import urljoin, urlparse
from pathlib import Path
from datetime import datetime
import time
from bs4 import BeautifulSoup
from threading import Thread, Lock
from queue import Queue

class WebpageImageDownloader:
    def __init__(self, url, output_dir, num_threads=4, timeout=10, use_sequential_naming=True, 
                 auto_pagination=True, max_pages=None, min_image_size_kb=0):
        """
        初始化网页图片下载器
        
        Args:
            url: 网页地址
            output_dir: 输出根目录，实际文件保存到 output_dir/{子目录名}/ 下
            num_threads: 并发下载线程数
            timeout: 下载超时时间（秒）
            use_sequential_naming: 是否使用递增编号命名 (001, 002, ...) 默认True
            auto_pagination: 是否自动翻页下载 默认True
            max_pages: 最多下载的页数 默认None（无限制）
            min_image_size_kb: 最小图片大小阈值（KB），小于此值的图片将被过滤掉 默认0（不过滤）
        """
        self.url = url
        self.output_base_dir = output_dir
        self.output_dir = output_dir  # 实际下载目录，在 run() 中根据网页信息动态生成
        self.num_threads = num_threads
        self.timeout = timeout
        self.use_sequential_naming = use_sequential_naming
        self.auto_pagination = auto_pagination
        self.max_pages = max_pages
        self.min_image_size_kb = min_image_size_kb
        
        # 下载统计
        self.download_queue = Queue()
        self.downloaded_count = 0
        self.failed_count = 0
        self.lock = Lock()
        self.index_counter = 0  # 递增编号计数器
        self.all_image_urls = []  # 保存所有收集到的图片URL
        self.worker_threads = []  # 工作线程列表（多页下载时保持线程存活）
        self.threads_started = False  # 标记线程是否已启动
        
        # User-Agent 和 Referer
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': url,  # 关键：添加 Referer 绕过防盗链
            'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
        }
    
    @staticmethod
    def generate_subdir_name(url, html_content=None):
        """
        根据网页信息生成子目录名
        
        格式: {域名}-{标题前20字}-{时间}
        示例: github.com-BeautifulSoup文档-20260411_220700
        """
        # 提取域名
        parsed = urlparse(url)
        domain = parsed.netloc
        # 去掉 www. 前缀
        if domain.startswith('www.'):
            domain = domain[4:]
        
        # 提取标题
        title_part = ""
        if html_content:
            try:
                soup = BeautifulSoup(html_content, 'html.parser')
                title_tag = soup.find('title')
                if title_tag:
                    raw_title = title_tag.get_text(strip=True)
                    # 清洗：移除特殊字符、多余空白、文件系统非法字符
                    cleaned = re.sub(r'[\\/:*?"<>|]', '', raw_title)
                    cleaned = re.sub(r'\s+', '_', cleaned)
                    # 截取前 20 个字符
                    title_part = cleaned[:20].rstrip('_')
            except Exception:
                pass
        
        # 时间戳
        time_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 组合
        parts = [p for p in [domain, title_part, time_str] if p]
        return '-'.join(parts)
    
    def fetch_webpage(self):
        """获取网页内容"""
        print(f"[*] 正在获取网页: {self.url}")
        try:
            response = requests.get(self.url, timeout=self.timeout, headers=self.headers)
            response.raise_for_status()
            print(f"[+] 网页获取成功，大小: {len(response.content)} bytes")
            return response.text
        except Exception as e:
            print(f"[-] 获取网页失败: {e}")
            return None
    
    def _is_small_icon_image(self, img_tag):
        """
        通过HTML属性判断是否为小图标/UI元素图片
        
        过滤条件：
        - width/height 属性值小于 50px 的
        - class 或 id 包含 icon/logo/avatar/btn/button/arrow/nav 等关键词的
        """
        # 检查 width/height 属性
        for attr in ['width', 'height']:
            val = img_tag.get(attr, '')
            if val:
                # 提取数值（可能带 px 等单位）
                num_match = re.match(r'^(\d+)', str(val))
                if num_match and int(num_match.group(1)) < 50:
                    return True
        
        # 检查 class 和 id 中的小图标关键词
        skip_keywords = ['icon', 'logo', 'avatar', 'btn', 'button', 'arrow', 'nav', 
                         'emoji', 'smiley', 'loading', 'placeholder', 'lazy', 'badge',
                         'favicon', 'gravatar', 'thumbnail']
        for attr in ['class', 'id']:
            val = img_tag.get(attr, '')
            if val:
                val_lower = ' '.join(val) if isinstance(val, list) else str(val).lower()
                for keyword in skip_keywords:
                    if keyword in val_lower:
                        return True
        
        return False
    
    def extract_image_urls(self, html_content):
        """从HTML中提取所有图片URL"""
        print("[*] 正在解析图片URL...")
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            img_tags = soup.find_all('img')
            
            image_urls = []
            seen_urls = set()  # 去重
            skipped_count = 0  # 被HTML属性过滤掉的图片数
            
            for img in img_tags:
                # 通过HTML属性过滤小图标/UI元素
                if self._is_small_icon_image(img):
                    skipped_count += 1
                    continue
                
                # 优先使用懒加载属性（这些属性包含真实的图片URL）
                # 支持多种懒加载方式：data-original、data-src、data-lazy-src、src
                src = (img.get('data-original') or 
                       img.get('data-src') or 
                       img.get('data-lazy-src') or 
                       img.get('src'))
                
                if src:
                    # 跳过 data:URI 格式的内联图片
                    if src.startswith('data:'):
                        continue
                    
                    # 跳过图标类格式（SVG、ICO 几乎都是图标，不可能是照片）
                    src_lower = src.lower().split('?')[0]  # 去掉查询参数后检查扩展名
                    if src_lower.endswith('.svg') or src_lower.endswith('.ico'):
                        skipped_count += 1
                        continue
                    
                    # 处理相对URL
                    absolute_url = urljoin(self.url, src)
                    
                    # 去重
                    if absolute_url not in seen_urls:
                        image_urls.append(absolute_url)
                        seen_urls.add(absolute_url)
            
            if skipped_count > 0:
                print(f"[*] 已通过HTML属性过滤掉 {skipped_count} 张小图标/UI图片")
            print(f"[+] 找到 {len(image_urls)} 张图片")
            return image_urls
        except Exception as e:
            print(f"[-] 解析图片URL失败: {e}")
            return []
    
    def _get_base_path(self, url):
        """
        提取URL的基础路径（去掉页码后缀和查询参数）
        用于判断分页链接是否属于同一文章
        
        例如:
          https://xiutaku.com/18426?page=2  -> /18426
          https://www.1y.is/xiuren/no-9189-sophisticated.html/3  -> /xiuren/no-9189-sophisticated.html
          https://example.com/page/2  -> /page
        """
        parsed = urlparse(url)
        path = parsed.path
        # 去掉末尾的页码（如 /3, .html/3）
        path = re.sub(r'/\d+/?$', '', path)
        return path
    
    def _is_pagination_link(self, href, current_url):
        """
        判断一个链接是否是当前页面的分页链接
        
        分页链接的条件（满足任一）：
        1. href 包含 ?page=N 或 &page=N 查询参数，且路径与当前URL相同
        2. href 路径是在当前URL路径之后追加分页数字（如 /article/123/2）
        3. href 路径以当前URL的 .html 路径 + /数字 结尾（如 /article.html/2）
        
        不符合分页条件的链接（如推荐文章 /18393、品牌 /brand/1 等）会被排除。
        """
        if not href:
            return False
        
        link_url = urljoin(current_url, href)
        link_parsed = urlparse(link_url)
        current_parsed = urlparse(current_url)
        
        # 域名必须相同
        if link_parsed.netloc != current_parsed.netloc:
            return False
        
        link_path = link_parsed.path.rstrip('/')
        current_path = current_parsed.path.rstrip('/')
        
        # 条件1: href 使用 ?page=N 且路径完全相同
        # query 属性不包含 ? 前缀，所以直接匹配 page=N
        if link_path == current_path and re.search(r'(^|&)page=\d+', link_parsed.query, re.I):
            return True
        
        # 条件2: href 路径以当前路径为前缀 + /数字（如 /article/123/2）
        if link_path.startswith(current_path + '/'):
            suffix = link_path[len(current_path):]
            if re.match(r'^/\d+$', suffix):
                return True
        
        # 条件3: 当前路径包含 .html，href 路径去掉末尾数字后与当前路径相同
        # （如当前 /article.html，href /article.html/2）
        if '.html' in current_path:
            base_path = re.sub(r'/\d+$', '', link_path)
            if base_path == current_path:
                return True
        
        return False
    
    def _extract_page_num_from_link(self, link, current_url):
        """
        从一个 <a> 标签中提取页码数字
        
        提取优先级：
        1. 链接文本为纯数字（如 "2", "17"），且是分页链接
        2. 链接文本为 "PageX" 格式，且是分页链接
        3. href 中的 ?page=N 查询参数
        4. href 路径末尾的分页数字（如 /3, .html/3），且是分页链接
        
        Returns:
            int 或 None
        """
        link_text = link.get_text(strip=True)
        href = link.get('href', '')
        
        # 1. 纯数字文本 + 分页链接验证
        match = re.match(r'^(\d+)$', link_text)
        if match and self._is_pagination_link(href, current_url):
            return int(match.group(1))
        
        # 2. PageX 格式 + 分页链接验证
        page_match = re.match(r'^Page(\d+)$', link_text, re.IGNORECASE)
        if page_match and self._is_pagination_link(href, current_url):
            return int(page_match.group(1))
        
        # 3. ?page=N 查询参数
        if href:
            query_match = re.search(r'[?&]page=(\d+)', href, re.IGNORECASE)
            if query_match:
                return int(query_match.group(1))
        
        return None
    
    def detect_total_pages(self, html_content, current_url):
        """
        从HTML中检测总页数
        
        策略：
        1. 优先从分页容器（class 含 pagination/page-num/pager/nav-page）中的链接提取
        2. 只提取分页链接（通过 _is_pagination_link 验证）
        3. 回退：从页面所有分页链接中提取最大页码
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            max_page = 1
            
            # 策略1: 从分页容器中查找
            pagination_containers = soup.find_all(
                ['div', 'nav', 'ul', 'ol', 'span'],
                class_=re.compile(r'paginat|page-num|pager|nav-page', re.I)
            )
            
            if pagination_containers:
                for container in pagination_containers:
                    links = container.find_all('a')
                    for link in links:
                        page_num = self._extract_page_num_from_link(link, current_url)
                        if page_num is not None and page_num > max_page:
                            max_page = page_num
            
            # 策略2: 如果分页容器没找到有效页码，从所有链接中查找
            if max_page == 1:
                all_links = soup.find_all('a')
                for link in all_links:
                    page_num = self._extract_page_num_from_link(link, current_url)
                    if page_num is not None and page_num > max_page:
                        max_page = page_num
            
            print(f"[+] 检测到总页数: {max_page}")
            return max_page
        except Exception as e:
            print(f"[-] 检测总页数失败: {e}，将不限制页数")
            return None
    
    def find_next_page_url(self, html_content, current_url, current_page_num, total_pages=None):
        """从HTML中查找下一页的URL
        
        Args:
            html_content: 页面HTML内容
            current_url: 当前页面URL
            current_page_num: 当前页码（由调用方维护）
            total_pages: 检测到的总页数，None表示未检测到
        """
        try:
            # 如果已知总页数，且当前已是最后一页，直接返回
            if total_pages is not None and current_page_num >= total_pages:
                print(f"[+] 已到最后一页 (当前: {current_page_num}/{total_pages})，停止翻页")
                return None
            
            soup = BeautifulSoup(html_content, 'html.parser')
            all_links = soup.find_all('a')
            next_page = current_page_num + 1
            
            # 方法 1: 查找文本为下一页页码的链接（如 "2", "Page2"）
            # 且链接必须是当前页面的分页链接
            for link in all_links:
                link_text = link.get_text(strip=True)
                if link_text == f'Page{next_page}' or link_text == f'{next_page}':
                    href = link.get('href')
                    if href and self._is_pagination_link(href, current_url):
                        next_url = urljoin(current_url, href)
                        print(f"[+] 通过页码文本找到下一页: {next_url}")
                        return next_url
            
            # 方法 2: 查找 <a> 标签，文本包含 "下一页"、"next"、">>>" 等
            # 且链接必须是当前页面的分页链接
            next_texts = ['下一页', 'next', '>>>', '»', '→', '→', 'next page', '下页', '>']
            for link in all_links:
                link_text = link.get_text(strip=True).lower()
                for next_text in next_texts:
                    if next_text.lower() in link_text:
                        href = link.get('href')
                        if href and self._is_pagination_link(href, current_url):
                            next_url = urljoin(current_url, href)
                            print(f"[+] 通过关键词方法找到下一页: {next_url}")
                            return next_url
            
            # 方法 3: 查找 rel="next" 的链接
            next_link = soup.find('a', rel='next')
            if next_link and next_link.get('href'):
                href = next_link['href']
                if self._is_pagination_link(href, current_url):
                    next_url = urljoin(current_url, href)
                    print(f"[+] 通过 rel=next 方法找到下一页: {next_url}")
                    return next_url
            
            # 方法 4: URL 模式识别 - 自动推算下一页URL
            if total_pages is None or next_page <= total_pages:
                parsed = urlparse(current_url)
                path = parsed.path
                query = parsed.query
                
                # 4a: 当前 URL 使用 ?page=N 查询参数
                query_page_match = re.search(r'page=(\d+)', query, re.IGNORECASE)
                if query_page_match:
                    new_query = re.sub(r'page=\d+', f'page={next_page}', query, flags=re.IGNORECASE)
                    next_url = f"{parsed.scheme}://{parsed.netloc}{path}?{new_query}"
                    print(f"[+] 通过 ?page=N 模式找到下一页: {next_url}")
                    return next_url
                
                # 4b: 当前 URL 没有查询参数，尝试添加 ?page=2
                if current_page_num == 1 and not query:
                    next_url = f"{parsed.scheme}://{parsed.netloc}{path}?page={next_page}"
                    print(f"[+] 通过添加 ?page=N 模式找到下一页: {next_url}")
                    return next_url
                
                # 4c: 当前 URL 路径末尾有页码数字（如 /xiuren/no-9189.html/3）
                current_page_match = re.search(r'/(\d+)(?:/)?$', path)
                if current_page_match:
                    next_path = path.replace(f'/{current_page_match.group(1)}', f'/{next_page}')
                    next_url = current_url.replace(path, next_path)
                    print(f"[+] 通过 URL 路径页码递增找到下一页: {next_url}")
                    return next_url
            
            print(f"[-] 未找到下一页链接 (当前页: {current_page_num}, 寻找页: {next_page})")
            return None
        except Exception as e:
            print(f"[-] 查找下一页失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_image_filename(self, image_url, index):
        """从URL生成文件名 - 使用递增编号避免重名"""
        try:
            # 获取文件扩展名
            ext = self._get_file_extension(image_url)
            
            # 如果使用递增编号模式，直接用编号命名
            if self.use_sequential_naming:
                return f"{index + 1:03d}.{ext}"
            else:
                # 尝试使用原文件名，但添加编号前缀避免重名
                parsed_url = urlparse(image_url)
                original_name = os.path.basename(parsed_url.path)
                
                if original_name and len(original_name) > 2:
                    # 移除原扩展名，使用检测到的扩展名
                    name_without_ext = os.path.splitext(original_name)[0]
                    # 限制名字长度，避免过长
                    if len(name_without_ext) > 50:
                        name_without_ext = name_without_ext[:50]
                    return f"{index + 1:03d}_{name_without_ext}.{ext}"
                else:
                    return f"{index + 1:03d}.{ext}"
        except:
            return f"{index + 1:03d}.jpg"
    
    def _get_file_extension(self, image_url):
        """从URL和HTTP头推断文件扩展名"""
        try:
            # 首先尝试从URL路径获取
            parsed_url = urlparse(image_url)
            url_path = parsed_url.path.lower()
            
            for ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'ico', 'tiff']:
                if f'.{ext}' in url_path:
                    return 'jpg' if ext == 'jpeg' else ext
            
            # 再尝试从HTTP头的Content-Type获取
            try:
                head_response = requests.head(image_url, timeout=5, headers=self.headers)
                content_type = head_response.headers.get('content-type', 'image/jpeg').lower()
                
                if 'jpeg' in content_type or 'jpg' in content_type:
                    return 'jpg'
                elif 'png' in content_type:
                    return 'png'
                elif 'gif' in content_type:
                    return 'gif'
                elif 'webp' in content_type:
                    return 'webp'
                elif 'bmp' in content_type:
                    return 'bmp'
                else:
                    return 'jpg'
            except:
                return 'jpg'
        except:
            return 'jpg'
    
    def download_image(self, image_url, filename):
        """下载单个图片"""
        try:
            response = requests.get(image_url, timeout=self.timeout, headers=self.headers)
            response.raise_for_status()
            
            file_size = len(response.content)
            
            # 文件大小过滤：如果设置了最小大小阈值，且文件小于阈值，则跳过
            if self.min_image_size_kb > 0 and file_size < self.min_image_size_kb * 1024:
                print(f"[~] 跳过小图片: {filename} ({file_size} bytes < {self.min_image_size_kb}KB)")
                return True  # 返回True避免计入失败，但也不计入成功
            
            filepath = os.path.join(self.output_dir, filename)
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            with self.lock:
                self.downloaded_count += 1
                print(f"[{self.downloaded_count}/{self.downloaded_count + self.failed_count}] ✓ {filename} ({file_size} bytes)")
            
            return True
        except Exception as e:
            with self.lock:
                self.failed_count += 1
                print(f"[-] 下载失败: {filename} - {str(e)[:50]}")
            return False
    
    def worker(self):
        """工作线程"""
        while True:
            item = self.download_queue.get()
            if item is None:
                break
            
            image_url, filename, index = item
            self.download_image(image_url, filename)
            self.download_queue.task_done()
    
    def start_download(self, image_urls):
        """开始并发下载 - 使用递增编号避免重名"""
        print(f"\n[*] 开始下载，使用 {self.num_threads} 个线程...")
        print(f"[*] 命名方式: {'递增编号 (001.jpg, 002.jpg, ...)' if self.use_sequential_naming else '原名+编号'}")
        
        # 将任务放入队列，预先分配编号（重要：确保编号唯一性）
        # 使用 self.index_counter 来跟踪全局编号，支持多页下载时编号连续
        for relative_index, url in enumerate(image_urls):
            global_index = self.index_counter + relative_index
            filename = self.get_image_filename(url, global_index)
            self.download_queue.put((url, filename, global_index))
        
        # 更新计数器以保持递增编号连续性
        self.index_counter += len(image_urls)
        
        # 仅在第一次下载时启动工作线程（多页下载时线程保持存活）
        if not self.threads_started:
            for _ in range(self.num_threads):
                t = Thread(target=self.worker, daemon=True)
                t.start()
                self.worker_threads.append(t)
            self.threads_started = True
    
    def wait_download_complete(self):
        """等待所有下载任务完成"""
        self.download_queue.join()
    
    def run(self):
        """运行下载流程"""
        print("=" * 60)
        print("网页图片下载工具")
        print("=" * 60)
        print(f"网页地址: {self.url}")
        print(f"输出根目录: {os.path.abspath(self.output_base_dir)}")
        print(f"线程数: {self.num_threads}")
        print(f"自动翻页: {'是' if self.auto_pagination else '否'}")
        if self.auto_pagination and self.max_pages:
            print(f"最大页数: {self.max_pages}")
        print("=" * 60)
        
        # 多页下载逻辑
        current_url = self.url
        page_count = 0
        current_page_num = 1  # 当前页码
        total_pages = None     # 检测到的总页数
        all_image_urls = []
        first_html = None
        visited_urls = set()   # 已访问的URL，用于循环检测
        
        while current_url and (self.max_pages is None or page_count < self.max_pages):
            # 循环检测：如果URL已访问过，说明翻页回绕了
            if current_url in visited_urls:
                print(f"[+] 检测到页面循环 (URL已访问过)，停止翻页")
                break
            visited_urls.add(current_url)
            
            page_count += 1
            print(f"\n[*] 正在处理第 {page_count} 页 (页码: {current_page_num}): {current_url}")
            
            # 获取网页
            html_content = self.fetch_webpage()
            if not html_content:
                print("[-] 无法获取网页内容")
                break
            
            # 保存第一页 HTML 用于生成子目录名
            if first_html is None:
                first_html = html_content
                # 在第一页检测总页数
                if self.auto_pagination:
                    total_pages = self.detect_total_pages(html_content, current_url)
            
            # 提取图片URL
            image_urls = self.extract_image_urls(html_content)
            if not image_urls:
                print("[-] 当前页面未找到图片")
            else:
                all_image_urls.extend(image_urls)
            
            # 如果不启用自动翻页，则停止
            if not self.auto_pagination:
                break
            
            # 查找下一页
            next_url = self.find_next_page_url(html_content, current_url, current_page_num, total_pages)
            if not next_url or next_url == current_url:
                print("[+] 已到最后一页，停止翻页")
                break
            
            current_url = next_url
            current_page_num += 1
            # 更新 self.url 以便查找相对链接时使用正确的基准URL
            self.url = next_url
            self.headers['Referer'] = next_url
        
        if not all_image_urls:
            print("[-] 未找到任何图片，退出")
            return False
        
        # 根据网页信息生成子目录名，创建实际输出目录
        subdir_name = self.generate_subdir_name(self.url, first_html)
        self.output_dir = os.path.join(self.output_base_dir, subdir_name)
        os.makedirs(self.output_dir, exist_ok=True)
        print(f"\n[+] 输出目录: {os.path.abspath(self.output_dir)}")
        
        # 开始下载（不阻塞，下载在后台进行）
        start_time = time.time()
        self.start_download(all_image_urls)
        
        # 等待所有下载完成
        self.wait_download_complete()
        elapsed_time = time.time() - start_time
        
        # 停止工作线程
        for _ in range(self.num_threads):
            self.download_queue.put(None)
        
        for t in self.worker_threads:
            t.join()
        
        # 打印统计
        print("\n" + "=" * 60)
        print(f"下载完成!")
        print(f"总页数: {page_count}")
        print(f"总图片数: {len(all_image_urls)}")
        print(f"成功: {self.downloaded_count}")
        print(f"失败: {self.failed_count}")
        print(f"总耗时: {elapsed_time:.2f} 秒")
        print(f"保存位置: {os.path.abspath(self.output_dir)}")
        print("=" * 60)
        
        return self.downloaded_count > 0


def main():
    parser = argparse.ArgumentParser(
        description="从网页下载所有图片",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python webpage_image_downloader.py "https://example.com/page.html" -o ./downloads
  python webpage_image_downloader.py "https://example.com/page.html" -o ./downloads -j 8 -t 15
  python webpage_image_downloader.py "https://example.com/page.html" -o ./downloads --keep-names
  python webpage_image_downloader.py "https://example.com/page.html" -o ./downloads --auto-pagination -m 10
  python webpage_image_downloader.py "https://example.com/page.html" -o ./downloads --min-size 10
        """
    )
    
    parser.add_argument("url", help="网页地址 (URL)")
    parser.add_argument("-o", "--output", default="./output", help="输出目录 (默认: ./output)")
    parser.add_argument("-j", "--num-threads", type=int, default=4, help="并发线程数 (默认: 4)")
    parser.add_argument("-t", "--timeout", type=int, default=10, help="下载超时时间，单位秒 (默认: 10)")
    parser.add_argument("--keep-names", action="store_true", help="保留原文件名 (默认使用递增编号)")
    parser.add_argument("--auto-pagination", action="store_true", help="自动翻页下载 (默认关闭)")
    parser.add_argument("-m", "--max-pages", type=int, default=None, help="最多下载的页数 (默认无限制)")
    parser.add_argument("--min-size", type=int, default=0, help="最小图片大小阈值(KB)，小于此值的图片将被过滤 (默认: 0，不过滤)")
    
    args = parser.parse_args()
    
    downloader = WebpageImageDownloader(
        url=args.url,
        output_dir=args.output,
        num_threads=args.num_threads,
        timeout=args.timeout,
        use_sequential_naming=not args.keep_names,
        auto_pagination=args.auto_pagination,
        max_pages=args.max_pages,
        min_image_size_kb=args.min_size
    )
    
    success = downloader.run()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
